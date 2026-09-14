"""Unpack HEX .harc archives and pull Texture2D portraits with UnityPy."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

INDEX_NAME = "harc_index.json"


def parse_harc_dir(path: Path) -> tuple[bytes, int, list[tuple[int, int, str]]]:
    data = path.read_bytes()
    if not data.startswith(b"HARC"):
        return data, 0, []
    index = 6
    entries: list[tuple[int, int, str]] = []
    while index < len(data):
        nl = data.find(b"\n", index)
        if nl < 0:
            break
        line = data[index:nl].decode("latin1").rstrip("\r")
        index = nl + 1
        if not line:
            break
        parts = line.split(",", 2)
        if len(parts) < 3:
            continue
        entries.append((int(parts[0]), int(parts[1]), parts[2].lstrip("./")))
    return data, index, entries


def build_index(cardsets: Path, cache: Path) -> dict[str, list]:
    cached = cache / INDEX_NAME
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    index: dict[str, list] = {}
    for harc in sorted(cardsets.glob("*.harc")):
        _data, base, entries = parse_harc_dir(harc)
        for off, size, name in entries:
            stem = Path(name).stem.lower()
            if stem.endswith("_dr") or stem == "atlas":
                continue
            index.setdefault(stem, []).append([str(harc), base + off, size])
    cache.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(index), encoding="utf-8")
    return index


def _extract_one(job: tuple[str, str]) -> tuple[str, bool, str]:
    ab_path, dest = job
    dest_path = Path(dest)
    if dest_path.exists() and dest_path.stat().st_size > 80:
        return dest_path.stem, True, "cached"
    try:
        import UnityPy

        env = UnityPy.load(ab_path)
        for obj in env.objects:
            if obj.type.name != "Texture2D":
                continue
            image = obj.read().image
            if not image:
                continue
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            image.convert("RGBA").save(dest_path)
            return dest_path.stem, True, "ok"
        return dest_path.stem, False, "no texture"
    except Exception as exc:
        return dest_path.stem, False, str(exc)


def extract_portraits(
    cardsets: Path,
    dest: Path,
    art_ids: set[str],
    workers: int = 6,
) -> dict[str, Path]:
    dest.mkdir(parents=True, exist_ok=True)
    raw_dir = dest / "_ab"
    raw_dir.mkdir(exist_ok=True)
    index = build_index(cardsets, dest)
    needed: dict[str, list] = {}
    found: dict[str, Path] = {}
    for art_id in art_ids:
        key = art_id.lower()
        png = dest / f"{key}.png"
        if png.exists() and png.stat().st_size > 80:
            found[key] = png
            continue
        locs = index.get(key)
        if not locs:
            continue
        harc, off, size = locs[0]
        needed.setdefault(harc, []).append((off, size, key))

    jobs = []
    for harc, items in needed.items():
        data = Path(harc).read_bytes()
        for off, size, key in items:
            ab = raw_dir / f"{key}.ab"
            if not ab.exists() or ab.stat().st_size != size:
                ab.write_bytes(data[off : off + size])
            jobs.append((str(ab), str(dest / f"{key}.png")))

    if not jobs:
        return found
    ok = fail = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_extract_one, job) for job in jobs]
        for fut in as_completed(futures):
            stem, success, _msg = fut.result()
            if success:
                ok += 1
                found[stem] = dest / f"{stem}.png"
            else:
                fail += 1
    print(f"  extracted {ok} portraits  failed {fail}  already had {len(found) - ok}")
    return found
