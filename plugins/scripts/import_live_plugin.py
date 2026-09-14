#!/usr/bin/env python3
"""Turn a live DragnCards table dump into a club plugin folder (jsons + TSV).

The dump is the plugin object the official client already downloaded:
{id, name, version, repo_url, game_def, card_db}.

Also accepts a My Plugins download zip (`{pluginName}_game_definition.zip`)
or a lone `layouts.json`.

  python plugins/scripts/import_live_plugin.py ~/Downloads/SomeGame-live-dump.json
  python plugins/scripts/collect_hosted_images.py --allow-s3 some-game-live-import

  # Pull only the table back into an existing workbench plugin:
  python plugins/scripts/import_live_plugin.py --layouts-only \\
      --out plugins/legend-of-the-five-rings \\
      ~/Downloads/Legend_of_the_Five_Rings_game_definition.zip
"""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from image_names import folder_slug  # noqa: E402

REQUIRED_TSV = ["databaseId", "name", "imageUrl", "cardBack", "type"]
SET_COLUMNS = ("set", "packName", "setName", "expansion", "cycle")


def unwrap_json(data: object) -> object:
    if isinstance(data, str):
        return json.loads(gzip.decompress(base64.b64decode(data)))
    return data


def merge_split_jsons(files: dict[str, dict]) -> dict:
    game_def: dict = {}
    for name, payload in files.items():
        if not isinstance(payload, dict):
            continue
        if name == "main.json":
            game_def.update(payload)
            continue
        if len(payload) == 1:
            key = next(iter(payload))
            game_def[key] = payload[key]
        else:
            game_def.update(payload)
    return game_def


def load_zip_game_def(path: Path) -> dict:
    files: dict[str, dict] = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".json"):
                continue
            payload = json.loads(archive.read(info).decode("utf-8"))
            files[Path(info.filename).name] = payload
    game_def = merge_split_jsons(files)
    if not game_def:
        raise SystemExit(f"{path} zip had no JSON game definition files")
    return {"game_def": game_def, "card_db": {}}


def load_dump(path: Path) -> dict:
    path = path.expanduser().resolve()
    if path.suffix.lower() == ".zip":
        return load_zip_game_def(path)
    raw = path.read_text(encoding="utf-8").strip()
    data = unwrap_json(json.loads(raw))
    if isinstance(data, dict) and "game_def" not in data and isinstance(data.get("data"), dict):
        data = data["data"]
    if isinstance(data, dict) and "layouts" in data and "game_def" not in data:
        if set(data.keys()) <= {"layouts"} or "pluginName" in data or "groups" in data:
            return {"game_def": data, "card_db": {}}
    if not isinstance(data, dict) or "game_def" not in data:
        raise SystemExit(f"{path} is not a plugin dump, game-definition zip, or layouts.json")
    data.setdefault("card_db", {})
    return data


def write_layouts_only(game_def: dict, out: Path) -> None:
    layouts = game_def.get("layouts")
    if not isinstance(layouts, dict) or not layouts:
        raise SystemExit("No layouts object in that export")
    jsons = out / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    dest = jsons / "layouts.json"
    write_json(dest, {"layouts": layouts})
    ids = ", ".join(layouts)
    try:
        shown = dest.relative_to(ROOT)
    except ValueError:
        shown = dest
    print(f"Wrote {shown}")
    print(f"  layout ids: {ids}")
    print("Cards, automation, decks, and hotkeys were left alone.")
    print("Re-upload jsons/layouts.json (or Load Game Definition for that file) when you want the site to match.")


def cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")
    return text.strip()


def clean_key(name: object) -> str:
    return str(name or "").replace("\r", "").replace("\n", "").strip()


def normalize_face(face: dict) -> dict:
    return {clean_key(k): v for k, v in face.items() if clean_key(k)}


def is_stub_face(face: dict, card_back: str) -> bool:
    if not face:
        return True
    name = str(face.get("name") or "").strip()
    if name and name != (card_back or "").strip():
        return False
    skip = {"name", "databaseId"}
    for key, value in face.items():
        if key in skip:
            continue
        if value is None or value == "":
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return False
    return True


def tsv_columns(card_db: dict) -> list[str]:
    keys: set[str] = set()
    for faces in card_db.values():
        if not isinstance(faces, dict):
            continue
        for face in faces.values():
            if isinstance(face, dict):
                keys.update(normalize_face(face).keys())
    ordered = [k for k in REQUIRED_TSV if k in keys]
    rest = sorted(k for k in keys if k not in REQUIRED_TSV)
    return ordered + rest


def card_db_to_rows(card_db: dict, header: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for db_id in sorted(card_db, key=lambda x: str(x)):
        faces = card_db[db_id]
        if not isinstance(faces, dict):
            continue
        face_a = normalize_face(faces.get("A") or {})
        if not face_a:
            continue
        if "databaseId" not in face_a:
            face_a = {**face_a, "databaseId": db_id}
        rows.append([cell(face_a.get(col, "")) for col in header])
        card_back = cell(face_a.get("cardBack", ""))
        if card_back != "multi_sided":
            continue
        for side in "BCDEFGHI":
            face = normalize_face(faces.get(side) or {})
            if not face or is_stub_face(face, card_back):
                continue
            if "databaseId" not in face:
                face = {**face, "databaseId": db_id}
            rows.append([cell(face.get(col, "")) for col in header])
    return rows


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def split_game_def(game_def: dict, jsons_dir: Path) -> None:
    main: dict = {}
    for key, value in game_def.items():
        if isinstance(value, dict):
            write_json(jsons_dir / f"{key}.json", {key: value})
        else:
            main[key] = value
    if "pluginName" not in main and game_def.get("pluginName"):
        main["pluginName"] = game_def["pluginName"]
    write_json(jsons_dir / "main.json", main)


def write_source(path: Path, dump: dict, dump_path: Path) -> None:
    game_def = dump.get("game_def") or {}
    lines = [
        f"Imported {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from a live DragnCards table dump.",
        f"Dump file: {dump_path.name}",
        f"Official plugin id: {dump.get('id')}",
        f"Official name: {dump.get('name') or game_def.get('pluginName')}",
        f"Official version: {dump.get('version')}",
        f"repo_url: {dump.get('repo_url') or ''}",
        "",
        "This is a compiled snapshot (merged game_def + card_db), not original source files.",
        "Run collect_hosted_images.py --allow-s3 on this folder so art lives on toybox.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path, help="live-dump.json, My Plugins zip, or layouts.json")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Plugin folder (default: plugins/{slug}-live-import)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing folder")
    parser.add_argument(
        "--layouts-only",
        action="store_true",
        help="Replace jsons/layouts.json in --out and leave everything else alone",
    )
    args = parser.parse_args()

    dump = load_dump(args.dump.expanduser().resolve())
    game_def = dump["game_def"] or {}
    card_db = dump.get("card_db") or {}
    plugin_name = game_def.get("pluginName") or dump.get("name") or "live-plugin"
    default_dir = ROOT / (
        folder_slug(plugin_name) if args.layouts_only else f"{folder_slug(plugin_name)}-live-import"
    )
    out = (args.out or default_dir).expanduser().resolve()
    if args.layouts_only:
        if not out.is_dir():
            raise SystemExit(f"{out} is not an existing plugin folder")
        write_layouts_only(game_def, out)
        return 0
    if out.exists() and not args.force:
        raise SystemExit(f"{out} already exists (pass --force to overwrite)")
    out.mkdir(parents=True, exist_ok=True)

    split_game_def(game_def, out / "jsons")
    header = tsv_columns(card_db)
    for col in REQUIRED_TSV:
        if col not in header:
            header.append(col)
    if not any(c in header for c in SET_COLUMNS):
        header.append("set")
        for faces in card_db.values():
            if isinstance(faces, dict) and isinstance(faces.get("A"), dict):
                faces["A"].setdefault("set", "cards")
    rows = card_db_to_rows(card_db, header)
    tsv_dir = out / "tsvs"
    tsv_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = tsv_dir / "cards.tsv"
    lines = ["\t".join(header)]
    lines.extend("\t".join(row[: len(header)]) for row in rows)
    tsv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_source(out / "SOURCE.txt", dump, args.dump)

    set_col = next((c for c in SET_COLUMNS if c in header), None)
    print(f"Wrote {out.name}")
    print(f"  pluginName: {plugin_name}")
    print(f"  official id/version: {dump.get('id')} / {dump.get('version')}")
    print(f"  json files: {len(list((out / 'jsons').glob('*.json')))}")
    print(f"  tsv rows: {len(rows)}  columns: {len(header)}" + (f"  set column: {set_col}" if set_col else "  (no set column)"))
    if set_col and set_col != "set":
        print(f"  collector override: add set_column {set_col!r} for {out.name}")
    print()
    print("Next:")
    print(f"  python plugins/scripts/collect_hosted_images.py --allow-s3 {out.name}")
    print("Then rsync images/{game}/ to toybox and Load Game Definition + Upload card database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
