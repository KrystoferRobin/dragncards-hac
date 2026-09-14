#!/usr/bin/env python3
"""Download hosted plugin art into images/{game}/{set}/Game-Set-Cardname and retarget plugins at toybox.

Resolved card URLs are prefix + relative path:

  https://toybox.hundredacre.club/cards/{game}/{set}/{Game}-{Set}-{Cardname}.ext

TSV / cardBack imageUrl values stay {game}/... (no cards/ in the relative path).
Pass --retarget to rewrite already-collected plugins without downloading.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import shutil
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from image_names import (  # noqa: E402
    TOYBOX_PREFIX,
    apply_lobby_art,
    card_rel_path,
    ext_from_url,
    folder_slug,
    pascal,
    plugin_art_rel,
    rewrite_toybox_url,
    toybox_url,
)

IMAGES = ROOT / "images"
CACHE = IMAGES / "_download-cache"
FAILURES = IMAGES / "_download-failures.tsv"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Only needed when folder/pascal from pluginName would not match already-hosted art.
OVERRIDES = {
    "vtes-dragncards-plugin": {"pascal": "Vtes"},
    "lotrlcg-plugin-main": {
        "folder": "lord-of-the-rings-lcg",
        "pascal": "LordOfTheRingsLcg",
        "tsv": "cardDb.tsv",
        "set_column": "packName",
        "prefix_languages": ["English", "French", "Spanish", "Italian", "German", "Chinese"],
    },
    "wars-trading-card-game-live-import": {
        "set_column": "packName",
    },
    "arkham-horror-living-card-game-live-import": {
        "set_column": "packName",
        "prefix_languages": ["English", "Italian"],
    },
    "war-of-the-ring-card-game-live-import": {
        "folder": "war-of-the-ring-card-game",
        "pascal": "WarOfTheRingCardGame",
    },
    "earthborne-rangers-live-import": {
        "folder": "earthborne-rangers",
        "pascal": "EarthborneRangers",
        "set_column": "pack_code",
        "prefix_languages": ["English", "Italian"],
    },
    "marvel-champions-the-card-game-live-import": {
        "folder": "marvel-champions",
        "pascal": "MarvelChampions",
        "prefix_languages": ["English", "Italian", "Portuguese"],
    },
    "star-wars-deckbuilding-game-live-import": {
        "folder": "star-wars-deckbuilding-game",
        "pascal": "StarWarsDeckbuildingGame",
    },
    "robotech-ccg": {
        "folder": "robotech-ccg",
        "pascal": "RobotechCcg",
        "set_column": "packName",
    },
    "vs-system-2pcg": {
        "folder": "vs-system-2pcg",
        "pascal": "VsSystem2pcg",
        "set_column": "packName",
    },
    "fight-klub": {
        "folder": "fight-klub",
        "pascal": "FightKlub",
        "set_column": "packName",
    },
    "sailor-moon-tcg": {
        "folder": "sailor-moon-tcg",
        "pascal": "SailorMoonTcg",
        "set_column": "packName",
    },
    "mythos": {
        "folder": "mythos",
        "pascal": "Mythos",
        "set_column": "packName",
    },
    "inwo": {
        "folder": "inwo",
        "pascal": "Inwo",
        "set_column": "packName",
    },
    "call-of-cthulhu-lcg": {
        "folder": "call-of-cthulhu-lcg",
        "pascal": "CallOfCthulhuLcg",
        "set_column": "packName",
    },
    "star-trek-ccg-1e": {
        "folder": "star-trek-ccg-1e",
        "pascal": "StarTrekCcg1e",
        "set_column": "packName",
    },
    "magic": {
        "folder": "magic",
        "pascal": "Magic",
        "set_column": "packName",
        "skip_cards": True,
    },
    "star-wars-ccg-decipher": {
        "folder": "star-wars-ccg",
        "pascal": "StarWarsCcg",
        "set_column": "packName",
    },
    "lotr-ccg-gemp": {
        "folder": "lord-of-the-rings-ccg",
        "pascal": "LordOfTheRingsTcg",
        "set_column": "packName",
    },
    "rifts-ccg": {
        "folder": "rifts-ccg",
        "pascal": "RiftsCcg",
        "set_column": "packName",
    },
    "gundam-ms-war-ccg": {
        "folder": "gundam-ms-war-ccg",
        "pascal": "GundamMsWarCcg",
        "set_column": "packName",
    },
    "legend-of-mana-ccg": {
        "folder": "legend-of-mana-ccg",
        "pascal": "LegendOfManaCcg",
        "set_column": "packName",
    },
    "maple-story": {
        "folder": "maple-story",
        "pascal": "MapleStory",
        "set_column": "packName",
    },
    "nightmare-before-christmas": {
        "folder": "nightmare-before-christmas",
        "pascal": "NightmareBeforeChristmas",
        "set_column": "packName",
    },
    "mmtcg": {
        "folder": "mmtcg",
        "pascal": "Mmtcg",
        "set_column": "packName",
    },
    "fpg-guardians": {
        "folder": "fpg-guardians",
        "pascal": "FpgGuardians",
        "set_column": "packName",
    },
    "doomtown": {
        "folder": "doomtown",
        "pascal": "Doomtown",
        "set_column": "packName",
    },
    "mlp-ccg": {
        "folder": "mlp-ccg",
        "pascal": "MlpCcg",
        "set_column": "packName",
    },
    "monty-python-ccg": {
        "folder": "monty-python-ccg",
        "pascal": "MontyPythonCcg",
        "set_column": "packName",
    },
    "netrunner-1996": {
        "folder": "netrunner-1996",
        "pascal": "Netrunner1996",
        "set_column": "packName",
    },
    "x-files-ccg": {
        "folder": "x-files-ccg",
        "pascal": "XFilesCcg",
        "set_column": "packName",
    },
    "doomtown-reloaded": {
        "folder": "doomtown-reloaded",
        "pascal": "DoomtownReloaded",
        "set_column": "packName",
    },
    "shadowfist": {
        "folder": "shadowfist",
        "pascal": "Shadowfist",
        "set_column": "packName",
    },
    "fe-cipher": {
        "folder": "fe-cipher",
        "pascal": "FeCipher",
        "set_column": "packName",
    },
    "star-trek-tcg": {
        "folder": "star-trek-tcg",
        "pascal": "StarTrekTcg",
        "set_column": "packName",
    },
    "force-of-will": {
        "folder": "force-of-will",
        "pascal": "ForceOfWill",
        "set_column": "packName",
    },
    "legend-of-the-five-rings": {
        "folder": "legend-of-the-five-rings",
        "pascal": "LegendOfTheFiveRings",
        "set_column": "packName",
    },
}

print_lock = threading.Lock()
fail_lock = threading.Lock()
failures: list[str] = []


def log(msg: str) -> None:
    with print_lock:
        print(msg, flush=True)


def parse_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return [], []
    header = [h.replace("\r", "").strip() for h in lines[0].split("\t")]
    rows = []
    for line in lines[1:]:
        if not line.strip():
            continue
        row = [c.replace("\r", "") for c in line.split("\t")]
        while len(row) < len(header):
            row.append("")
        rows.append(row)
    return header, rows


def write_tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    out = ["\t".join(header)]
    for row in rows:
        out.append("\t".join(row[: len(header)]))
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def col_index(header: list[str], *names: str) -> int:
    lowered = [h.lower() for h in header]
    for name in names:
        if name.lower() in lowered:
            return lowered.index(name.lower())
    raise KeyError(names)


def unique_rel(rel: str, used: dict[str, int]) -> str:
    key = rel.casefold()
    used[key] = used.get(key, 0) + 1
    if used[key] == 1:
        return rel
    path = Path(rel)
    return str(path.with_name(f"{path.stem}-{used[key]}{path.suffix}")).replace("\\", "/")


def cache_path(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return CACHE / f"{digest}{ext_from_url(url)}"


def ensure_https(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("//"):
        return "https:" + url
    if url and not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


_allow_s3 = False


def is_remote_source(url: str) -> bool:
    url = ensure_https(url)
    if not url.startswith(("http://", "https://")):
        return False
    if "toybox.hundredacre.club" in url:
        return False
    if "dragncards-core.s3" in url and not _allow_s3:
        return False
    return True


def resolve_card_url(url: str, prefix: str) -> str:
    """Turn a TSV imageUrl into an absolute URL. Relative names use imageUrlPrefix.Default."""
    url = (url or "").strip()
    if not url:
        return ""
    url = ensure_https(url) if url.startswith(("http://", "https://", "//")) else url
    if url.startswith(("http://", "https://")):
        return url
    prefix = (prefix or "").strip()
    if not prefix:
        return url
    return ensure_https(prefix.rstrip("/") + "/" + url.lstrip("/"))


def plugin_image_prefix(plugin_dir: Path) -> str:
    path = plugin_dir / "jsons" / "imageUrlPrefix.json"
    if not path.exists():
        return ""
    payload = load_json(path)
    prefixes = payload.get("imageUrlPrefix") or {}
    return (prefixes.get("Default") or prefixes.get("English") or "").strip()


SKIP_ROOT_DIRS = {"scripts", "images", "uploaded", "live_dumps"}


def iter_plugin_dirs() -> list[Path]:
    """New work lives in plugins/; finished games are moved to plugins/uploaded/."""
    dirs: list[Path] = []
    for path in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        if path.name in SKIP_ROOT_DIRS or path.name.startswith("."):
            continue
        dirs.append(path)
    uploaded = ROOT / "uploaded"
    if uploaded.is_dir():
        dirs.extend(sorted(p for p in uploaded.iterdir() if p.is_dir() and not p.name.startswith(".")))
    return dirs


def discover_games() -> list[dict]:
    games: list[dict] = []
    for plugin_dir in iter_plugin_dirs():
        override = OVERRIDES.get(plugin_dir.name, {})
        tsv_name = override.get("tsv", "cards.tsv")
        main_path = plugin_dir / "jsons" / "main.json"
        tsv_path = plugin_dir / "tsvs" / tsv_name
        if not main_path.exists() or not tsv_path.exists():
            continue
        plugin_name = load_json(main_path).get("pluginName") or plugin_dir.name
        games.append(
            {
                "plugin": plugin_dir.name,
                "path": plugin_dir,
                "folder": override.get("folder") or folder_slug(plugin_name),
                "pascal": override.get("pascal") or pascal(plugin_name),
                "tsv": tsv_name,
                "set_column": override.get("set_column", "set"),
                "prefix_languages": override.get("prefix_languages") or [],
                "skip_cards": bool(override.get("skip_cards")),
            }
        )
    return games


def fetch_url(url: str) -> str:
    url = ensure_https(url)
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/%+!*'(),-_.:@")
    url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
    suffix = Path(path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}:
        return url + ".jpg"
    return url


def download(url: str, dest: Path, retries: int = 3) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    request_url = fetch_url(url)
    cache = cache_path(request_url)
    if cache.exists() and cache.stat().st_size > 0:
        shutil.copy2(cache, dest)
        return True
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(request_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=45) as response:
                data = response.read()
            if not data:
                last_error = "empty body"
                continue
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_suffix(cache.suffix + ".part")
            tmp.write_bytes(data)
            tmp.replace(cache)
            shutil.copy2(cache, dest)
            return True
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, http.client.HTTPException) as exc:
            last_error = str(exc)
            time.sleep(min(2 * attempt, 6))
    with fail_lock:
        failures.append(f"{request_url}\t{dest}\t{last_error}")
    return False


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def rewrite_json_image_urls(obj: object) -> bool:
    changed = False
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in {"imageUrl", "backgroundUrl", "bannerUrl", "logoUrl"} and isinstance(value, str):
                rewritten = rewrite_toybox_url(value)
                if rewritten != value:
                    obj[key] = rewritten
                    changed = True
            elif rewrite_json_image_urls(value):
                changed = True
    elif isinstance(obj, list):
        for item in obj:
            if rewrite_json_image_urls(item):
                changed = True
    return changed


def retarget_plugin(plugin_dir: Path, folder: str | None = None, tsv_name: str = "cards.tsv", prefix_languages: list[str] | None = None) -> None:
    """Point a collected plugin at https://toybox.hundredacre.club/cards/."""
    jsons = plugin_dir / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    prefixes = {"Default": TOYBOX_PREFIX}
    for lang in prefix_languages or []:
        prefixes[lang] = TOYBOX_PREFIX
    dump_json(jsons / "imageUrlPrefix.json", {"imageUrlPrefix": prefixes})
    if folder:
        main_path = jsons / "main.json"
        if main_path.exists():
            payload = load_json(main_path)
            apply_lobby_art(payload, folder)
            dump_json(main_path, payload)

    tsv_path = plugin_dir / "tsvs" / tsv_name
    if tsv_path.exists():
        header, rows = parse_tsv(tsv_path)
        try:
            url_i = col_index(header, "imageUrl")
        except KeyError:
            url_i = None
        if url_i is not None:
            changed = False
            extra_cols = []
            for name in ("zoomImageUrl", "imageUrlHq"):
                try:
                    extra_cols.append(col_index(header, name))
                except KeyError:
                    pass
            for row in rows:
                for index in [url_i, *extra_cols]:
                    rewritten = rewrite_toybox_url(row[index])
                    if rewritten != row[index]:
                        row[index] = rewritten
                        changed = True
            if changed:
                write_tsv(tsv_path, header, rows)

    for name in ("cardBacks.json", "tokens.json", "main.json"):
        path = jsons / name
        if not path.exists():
            continue
        payload = load_json(path)
        if rewrite_json_image_urls(payload):
            dump_json(path, payload)


def rewrite_text_urls(plugin_dir: Path, replacements: dict[str, str]) -> None:
    """Replace leftover remote URLs in json/jsonnet (hotkeys icon(), touchBar, etc.)."""
    if not replacements:
        return
    jsons = plugin_dir / "jsons"
    if not jsons.exists():
        return
    for path in list(jsons.glob("*.json")) + list(jsons.glob("*.jsonnet")):
        text = path.read_text(encoding="utf-8")
        updated = text
        for old, new in replacements.items():
            if old and old != new:
                updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            log(f"  rewrote URLs in {path.name}")


def process_game(game: dict, workers: int) -> None:
    plugin_dir = Path(game.get("path") or ROOT / game["plugin"])
    folder = game["folder"]
    pascal_name = game["pascal"]
    tsv_name = game.get("tsv") or "cards.tsv"
    set_column = game.get("set_column") or "set"
    tsv_path = plugin_dir / "tsvs" / tsv_name
    header, rows = parse_tsv(tsv_path)
    name_i = col_index(header, "name")
    set_i = col_index(header, set_column, "set", "packName")
    url_i = col_index(header, "imageUrl")
    used: dict[str, int] = {}
    seen_remote: dict[str, str] = {}
    card_jobs: list[tuple[str, Path, int, str]] = []
    url_map: dict[str, str] = {}
    default_prefix = plugin_image_prefix(plugin_dir)

    if not game.get("skip_cards"):
        for index, row in enumerate(rows):
            raw = row[url_i].strip()
            name = row[name_i].strip()
            set_name = row[set_i].strip() or "unknown"
            remote = resolve_card_url(raw, default_prefix)
            if not remote:
                continue
            if is_remote_source(remote):
                if remote in seen_remote:
                    rel = seen_remote[remote]
                else:
                    rel = unique_rel(
                        card_rel_path(folder, pascal_name, set_name, name, ext_from_url(remote)),
                        used,
                    )
                    seen_remote[remote] = rel
                dest = IMAGES / rel
                card_jobs.append((remote, dest, index, rel.replace("\\", "/")))
            else:
                used[raw.casefold()] = used.get(raw.casefold(), 0) + 1

        log(f"{game['plugin']}: downloading {len(card_jobs)} card images")
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(download, url, dest): (url, dest, index, rel)
                for url, dest, index, rel in card_jobs
            }
            for future in as_completed(futures):
                url, dest, index, rel = futures[future]
                ok = future.result()
                if ok:
                    rows[index][url_i] = rel
                    url_map[url] = toybox_url(rel)
                done += 1
                if done % 100 == 0 or not ok:
                    log(f"  {game['folder']}: {done}/{len(card_jobs)}")
        write_tsv(tsv_path, header, rows)

        extra_image_cols: list[tuple[int, str]] = []
        for name, suffix in (("zoomImageUrl", " Master"), ("imageUrlHq", " Master")):
            try:
                extra_image_cols.append((col_index(header, name), suffix))
            except KeyError:
                pass
        extra_jobs: list[tuple[str, Path, int, int, str]] = []
        for col_i, suffix in extra_image_cols:
            for index, row in enumerate(rows):
                raw = row[col_i].strip()
                name = f"{row[name_i].strip()}{suffix}"
                set_name = row[set_i].strip() or "unknown"
                remote = resolve_card_url(raw, default_prefix)
                if not remote or not is_remote_source(remote):
                    continue
                if remote in seen_remote:
                    rel = seen_remote[remote]
                else:
                    rel = unique_rel(
                        card_rel_path(folder, pascal_name, set_name, name, ext_from_url(remote)),
                        used,
                    )
                    seen_remote[remote] = rel
                extra_jobs.append((remote, IMAGES / rel, index, col_i, rel.replace("\\", "/")))
        if extra_jobs:
            log(f"{game['plugin']}: downloading {len(extra_jobs)} preview images")
            done = 0
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(download, url, dest): (url, dest, index, col_i, rel)
                    for url, dest, index, col_i, rel in extra_jobs
                }
                for future in as_completed(futures):
                    url, dest, index, col_i, rel = futures[future]
                    if future.result():
                        rows[index][col_i] = rel
                        url_map[url] = toybox_url(rel)
                    done += 1
                    if done % 100 == 0:
                        log(f"  {game['folder']} preview: {done}/{len(extra_jobs)}")
            write_tsv(tsv_path, header, rows)

    jsons = plugin_dir / "jsons"
    backs_path = jsons / "cardBacks.json"
    if backs_path.exists():
        payload = load_json(backs_path)
        for key, back in payload.get("cardBacks", {}).items():
            url = ensure_https(back.get("imageUrl") or "")
            if is_remote_source(url):
                rel = plugin_art_rel(folder, pascal_name, f"cardback-{key}", ext_from_url(url))
                if download(url, IMAGES / rel):
                    back["imageUrl"] = rel.replace("\\", "/")
                    url_map[url] = toybox_url(rel)
        dump_json(backs_path, payload)

    tokens_path = jsons / "tokens.json"
    if tokens_path.exists():
        payload = load_json(tokens_path)
        for key, token in payload.get("tokens", {}).items():
            url = ensure_https(token.get("imageUrl") or "")
            if is_remote_source(url):
                rel = plugin_art_rel(folder, pascal_name, f"token-{key}", ext_from_url(url, ".png"))
                if download(url, IMAGES / rel):
                    new_url = toybox_url(rel)
                    token["imageUrl"] = new_url
                    url_map[url] = new_url
        dump_json(tokens_path, payload)

    main_path = jsons / "main.json"
    if main_path.exists():
        payload = load_json(main_path)
        url = ensure_https(payload.get("backgroundUrl") or "")
        if is_remote_source(url):
            rel = plugin_art_rel(folder, pascal_name, "background", ext_from_url(url))
            if download(url, IMAGES / rel):
                new_url = toybox_url(rel)
                payload["backgroundUrl"] = new_url
                url_map[url] = new_url
                dump_json(main_path, payload)

    extra_map: dict[str, str] = {}
    for old, new in url_map.items():
        extra_map[old.replace("s3.amazonaws.com", "s3.us-east-1.amazonaws.com")] = new
        extra_map[old.replace("s3.us-east-1.amazonaws.com", "s3.amazonaws.com")] = new
    url_map.update(extra_map)
    rewrite_text_urls(plugin_dir, url_map)
    retarget_plugin(
        plugin_dir,
        folder,
        tsv_name=tsv_name,
        prefix_languages=game.get("prefix_languages") or [],
    )
    log(f"{game['plugin']}: done")


def repair_known_fallbacks() -> None:
    src = IMAGES / "middle-earth-ccg/wizards/MiddleEarthCCG-Wizards-PlagueOfWights.jpg"
    dst = IMAGES / "middle-earth-ccg/lidlesseye/MiddleEarthCCG-LidlessEye-PlagueOfWights.jpg"
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        tsv = ROOT / "uploaded" / "middle-earth-ccg-dragncards-plugin" / "tsvs" / "cards.tsv"
        if not tsv.exists():
            tsv = ROOT / "middle-earth-ccg-dragncards-plugin" / "tsvs" / "cards.tsv"
        header, rows = parse_tsv(tsv)
        name_i = col_index(header, "name")
        set_i = col_index(header, "set")
        url_i = col_index(header, "imageUrl")
        rel = "middle-earth-ccg/lidlesseye/MiddleEarthCCG-LidlessEye-PlagueOfWights.jpg"
        changed = False
        for row in rows:
            if row[name_i] == "Plague of Wights" and row[set_i] == "LidlessEye" and row[url_i].startswith("http"):
                row[url_i] = rel
                changed = True
        if changed:
            write_tsv(tsv, header, rows)
            log("Copied Wizards Plague of Wights art onto the Lidless Eye printing.")


def main() -> int:
    global _allow_s3
    workers = 16
    retarget_only = "--retarget" in sys.argv
    _allow_s3 = "--allow-s3" in sys.argv
    only = next((arg for arg in sys.argv[1:] if not arg.startswith("-")), None)
    games = discover_games()
    if only:
        games = [game for game in games if only in (game["plugin"], game["folder"], game["pascal"])]
        if not games:
            log(f"No plugin matched {only!r}")
            return 1
    if retarget_only:
        for game in games:
            retarget_plugin(
                Path(game.get("path") or ROOT / game["plugin"]),
                game["folder"],
                tsv_name=game.get("tsv") or "cards.tsv",
                prefix_languages=game.get("prefix_languages") or [],
            )
            log(f"{game['plugin']}: retargeted to {TOYBOX_PREFIX}")
        log("Retarget finished.")
        return 0
    CACHE.mkdir(parents=True, exist_ok=True)
    for game in games:
        process_game(game, workers)
    repair_known_fallbacks()
    kept: list[str] = []
    for line in failures:
        parts = line.split("\t")
        dest = Path(parts[1]) if len(parts) > 1 else None
        if dest and dest.exists() and dest.stat().st_size > 0:
            continue
        kept.append(line)
    failures.clear()
    failures.extend(kept)
    if failures:
        FAILURES.write_text("url\tdest\terror\n" + "\n".join(failures) + "\n", encoding="utf-8")
        log(f"{len(failures)} download failure(s) written to {FAILURES}")
        return 1
    if FAILURES.exists():
        FAILURES.unlink()
    log("All image collection finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
