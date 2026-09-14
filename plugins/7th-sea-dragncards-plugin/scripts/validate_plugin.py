#!/usr/bin/env python3
"""Validate the generated 7th Sea DragnCards plugin."""

from __future__ import annotations

import json
import re
from pathlib import Path

PLUGIN_DIR = Path(r"C:\Users\chris\Documents\e-Sword\dragncards\7th-sea-dragncards-plugin")
JSONS_DIR = PLUGIN_DIR / "jsons"
TSV_PATH = PLUGIN_DIR / "tsvs" / "cards.tsv"
IMAGES_ROOT = Path(r"C:\Users\chris\Documents\e-Sword\dragncards\images")

REQUIRED_GAMEDEF_KEYS = [
    "pluginName",
    "playerCountMenu",
    "browse",
    "cardBacks",
    "cardTypes",
    "groups",
    "layouts",
    "playerProperties",
    "spawnExistingCardModal",
]

REQUIRED_TSV_COLUMNS = ["databaseId", "name", "imageUrl", "cardBack", "type"]


def deep_merge(obj1: dict, obj2: dict) -> dict:
    for key, val in obj2.items():
        if key not in obj1:
            obj1[key] = val
        elif isinstance(obj1[key], list) and isinstance(val, list):
            obj1[key] = obj1[key] + val
        elif isinstance(obj1[key], dict) and isinstance(val, dict):
            deep_merge(obj1[key], val)
        else:
            obj1[key] = val
    return obj1


def merge_jsons(jsons_dir: Path) -> dict:
    merged: dict = {}
    for path in sorted(jsons_dir.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise SystemExit(f"{path.name} is not a JSON object")
        deep_merge(merged, data)
    return merged


def parse_tsv(text: str) -> list[list[str]]:
    tokens = text.split("\t")
    num_columns = len(text.split("\n")[0].split("\t"))
    array_2d: list[list[str]] = []
    current_row: list[str] = []
    for token in tokens:
        if len(current_row) == num_columns - 1:
            values = token.split("\n")
            prefix = "\n".join(values[:-1])
            suffix = values[-1]
            current_row.append(prefix)
            array_2d.append(current_row)
            current_row = [suffix]
        else:
            current_row.append(token)
    if len(current_row) == num_columns:
        array_2d.append(current_row)
    return array_2d


def resolve_group_id(group_id: str) -> str:
    group_id = re.sub(r"\{playerN(\+\d+)?\}", "player1", group_id)
    group_id = re.sub(r"playerN(\+\d+)?", "player1", group_id)
    return group_id


def main() -> int:
    errors: list[str] = []
    game_def = merge_jsons(JSONS_DIR)

    if game_def.get("pluginName") != "7th Sea":
        errors.append(f"pluginName should be '7th Sea', got {game_def.get('pluginName')!r}")

    for key in REQUIRED_GAMEDEF_KEYS:
        if key not in game_def:
            errors.append(f"Missing required gameDef key: {key}")

    tsv_text = TSV_PATH.read_text(encoding="utf-8")
    rows = parse_tsv(tsv_text)
    if not rows:
        raise SystemExit("TSV parsed to zero rows")
    header = [col.replace("\r", "") for col in rows[0]]
    for col in REQUIRED_TSV_COLUMNS:
        if col not in header:
            errors.append(f"TSV missing required column: {col}")

    cards = []
    seen_ids: set[str] = set()
    missing_files = 0
    for row in rows[1:]:
        if len(row) == 1 and row[0] == "":
            continue
        if len(row) != len(header):
            errors.append(f"TSV row has {len(row)} columns, expected {len(header)}: {row[:3]!r}")
            continue
        face = {header[i].replace("\r", ""): row[i].replace("\r", "") for i in range(len(header))}
        db_id = face.get("databaseId", "")
        if not db_id:
            errors.append("Card missing databaseId")
            continue
        if db_id in seen_ids:
            errors.append(f"Duplicate databaseId: {db_id}")
        seen_ids.add(db_id)
        image_url = face.get("imageUrl", "")
        if image_url and not image_url.startswith("http"):
            local = IMAGES_ROOT / image_url
            if not local.exists():
                missing_files += 1
                if missing_files <= 15:
                    errors.append(f"{db_id}: image file missing at {local}")
        cards.append(face)

    card_types = set(game_def.get("cardTypes", {}))
    card_backs = set(game_def.get("cardBacks", {}))
    groups = set(game_def.get("groups", {}))
    tokens = set(game_def.get("tokens", {}))
    group_types = set(game_def.get("groupTypes", {}))

    for card in cards:
        if not card.get("name"):
            errors.append(f"{card.get('databaseId')}: missing name")
        if not card.get("imageUrl"):
            errors.append(f"{card.get('databaseId')}: missing imageUrl")
        card_type = card.get("type", "")
        if card_type not in card_types:
            errors.append(f"{card.get('databaseId')}: type {card_type!r} not in cardTypes")
        card_back = card.get("cardBack", "")
        if card_back != "multi_sided" and card_back not in card_backs:
            errors.append(f"{card.get('databaseId')}: cardBack {card_back!r} not in cardBacks")

    for type_name, type_def in game_def.get("cardTypes", {}).items():
        for token_id in type_def.get("tokens", []):
            if token_id not in tokens:
                errors.append(f"cardTypes.{type_name} token {token_id!r} not in tokens")

    for group_id, group in game_def.get("groups", {}).items():
        gtype = group.get("groupType")
        if gtype and gtype not in group_types:
            errors.append(f"groups.{group_id} groupType {gtype!r} not in groupTypes")

    for layout_id, layout in game_def.get("layouts", {}).items():
        for region_id, region in layout.get("regions", {}).items():
            resolved = resolve_group_id(region.get("groupId", ""))
            if resolved not in groups:
                errors.append(
                    f"layouts.{layout_id}.regions.{region_id} groupId "
                    f"{region.get('groupId')!r} -> {resolved!r} not in groups"
                )

    for option in game_def.get("playerCountMenu", []):
        layout_id = option.get("layoutId")
        if layout_id not in game_def.get("layouts", {}):
            errors.append(f"playerCountMenu layoutId {layout_id!r} not in layouts")

    known_ids = {card["databaseId"] for card in cards}
    for deck_id, deck in game_def.get("preBuiltDecks", {}).items():
        if not deck.get("cards"):
            errors.append(f"preBuiltDecks.{deck_id} has no cards")
        for item in deck.get("cards", []):
            if item["databaseId"] not in known_ids:
                errors.append(f"preBuiltDecks.{deck_id} unknown card {item['databaseId']}")
            load_group = item["loadGroupId"]
            if not (load_group.startswith("playerN") or load_group in groups):
                errors.append(f"preBuiltDecks.{deck_id} bad loadGroupId {load_group}")

    print(f"Merged {len(list(JSONS_DIR.glob('*.json')))} JSON files")
    print(f"pluginName: {game_def.get('pluginName')}")
    print(f"imageUrlPrefix: {game_def.get('imageUrlPrefix')}")
    print(f"Parsed {len(cards)} cards from TSV")
    print(f"Groups: {len(groups)}")
    print(f"Layouts: {list(game_def.get('layouts', {}))}")
    print(f"Pre-built decks: {len(game_def.get('preBuiltDecks', {}))}")
    if missing_files > 15:
        errors.append(f"... {missing_files - 15} more missing image files")
    if errors:
        print(f"\n{len(errors)} error(s):")
        for err in errors[:80]:
            print(f"  - {err}")
        if len(errors) > 80:
            print(f"  ... {len(errors) - 80} more")
        return 1
    print("\nValidation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
