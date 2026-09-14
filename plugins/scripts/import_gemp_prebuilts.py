#!/usr/bin/env python3
"""Extract GEMP sample/starter decks into DragnCards preBuiltDecks + deckMenu.

  python plugins/scripts/import_gemp_prebuilts.py
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SWCCG_PLUGIN = ROOT / "star-wars-ccg-decipher"
SWCCG_SQL = ROOT / "star-wars-decipher" / "gemp-swccg" / "src" / "db-scripts"
LOTR_PLUGIN = ROOT / "lotr-ccg-gemp"
LOTR_PRODUCT = (
    ROOT
    / "lotrccg-gemp-conversion"
    / "gemp-lotr-master"
    / "gemp-lotr"
    / "gemp-lotr-cards"
    / "src"
    / "main"
    / "resources"
    / "product"
)

INSERT_RE = re.compile(
    r"INSERT INTO deck \(player_id, name, contents\) VALUES\(\(SELECT id FROM player WHERE name='Librarian'\),\s*(?:'((?:[^']|'')*)'|\"([^\"]*)\"),\s*'([^']*)'\)",
    re.I,
)
HJSON_NAME_RE = re.compile(r"^name:\s*(.+?)\s*$")
HJSON_TYPE_RE = re.compile(r"^type:\s*(\w+)")
HJSON_ITEM_RE = re.compile(r"^(\d+)x(\S+)")
BLUEPRINT_RE = re.compile(r"^\d+_\d+$")

SWCCG_SQL_FILES = ("sample_decks.sql", "utinni_sample_decks.sql")

LOTR_STARTER_FILES = [
    ("01-FOTR-Starters.hjson", "Fellowship of the Ring"),
    ("02-MOM-Starters.hjson", "Mines of Moria"),
    ("03-ROTEL-Starters.hjson", "Realms of the Elf-lords"),
    ("04-TTT-Starters.hjson", "The Two Towers"),
    ("05-BOHD-Starters.hjson", "Battle of Helm's Deep"),
    ("06-EOF-Starters.hjson", "Ents of Fangorn"),
    ("07-ROTK-Starters.hjson", "Return of the King"),
    ("08-SOG-Starters.hjson", "Siege of Gondor"),
    ("10-MD-Starters.hjson", "Mount Doom"),
    ("11-SH-Starters.hjson", "Shadows"),
    ("12-BR-Starters.hjson", "Black Rider"),
    ("13-BL-Starters.hjson", "Bloodlines"),
    ("15-TH-Starters.hjson", "The Hunters"),
    ("17-ROS-Starters.hjson", "Rise of Saruman"),
    ("Movie-Special-Starters.hjson", "Movie Special"),
    ("V1-SotP-Starters.hjson", "Shadows of the Past"),
    ("SHELBI - Starters.hjson", "SHELBI"),
    ("SARU-Starters.hjson", "SARU"),
]


def dump_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_cards(tsv: Path) -> dict[str, dict[str, str]]:
    lines = tsv.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    idx = {name: i for i, name in enumerate(header)}
    cards: dict[str, dict[str, str]] = {}
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) <= idx["databaseId"]:
            continue
        cards[parts[idx["databaseId"]]] = {
            "name": parts[idx["name"]],
            "type": parts[idx["type"]],
        }
    return cards


def slug(name: str, used: dict[str, int]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:80] or "deck"
    n = used.get(base, 0)
    used[base] = n + 1
    return base if n == 0 else f"{base}-{n + 1}"


def collapse(entries: list[tuple[str, str, str, int]]) -> list[dict]:
    order: list[tuple[str, str]] = []
    counts: dict[tuple[str, str], dict] = {}
    for database_id, name, group, qty in entries:
        key = (database_id, group)
        if key not in counts:
            order.append(key)
            counts[key] = {
                "databaseId": database_id,
                "loadGroupId": group,
                "quantity": 0,
            }
        counts[key]["quantity"] += qty
    return [counts[key] for key in order]


def menu_payload(groups: list[tuple[str, list[tuple[str, str]]]]) -> dict:
    sub_menus = []
    for label, decks in groups:
        if not decks:
            continue
        sub_menus.append(
            {
                "label": label,
                "deckLists": [{"deckListId": deck_id, "label": deck_label} for deck_id, deck_label in decks],
            }
        )
    return {"deckMenu": {"subMenus": sub_menus}}


def swccg_group(name: str) -> str:
    if name.startswith("Precon"):
        return "Preconstructed"
    if name.startswith("Classic"):
        return "Classic"
    if name.startswith("Decipher Only"):
        return "Decipher Only"
    if name.startswith("Legacy"):
        return "Legacy"
    if name.startswith("Utinni"):
        return "Utinni"
    if name.startswith("Open"):
        return "Open"
    if name.startswith("P-"):
        return "Period constructed"
    return "Other"


SWCCG_GROUP_ORDER = [
    "Preconstructed",
    "Classic",
    "Decipher Only",
    "Legacy",
    "Open",
    "Period constructed",
    "Utinni",
    "Other",
]


def parse_swccg_sql(path: Path) -> list[tuple[str, str, str]]:
    text = path.read_text(encoding="utf-8")
    decks = []
    for match in INSERT_RE.finditer(text):
        name = (match.group(1) or match.group(2) or "").replace("''", "'")
        contents = match.group(3)
        reserve, _, outside = contents.partition("|")
        decks.append((name, reserve, outside))
    return decks


def write_swccg_prebuilts(plugin: Path = SWCCG_PLUGIN) -> dict[str, int]:
    cards = load_cards(plugin / "tsvs" / "cards.tsv")
    prebuilt: dict[str, dict] = {}
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
    used_ids: dict[str, int] = {}
    missing_ids: set[str] = set()
    skipped_empty = 0

    for sql_name in SWCCG_SQL_FILES:
        sql_path = SWCCG_SQL / sql_name
        if not sql_path.exists():
            continue
        for name, reserve, outside in parse_swccg_sql(sql_path):
            entries: list[tuple[str, str, str, int]] = []
            for raw, group in ((reserve, "playerNReserve"), (outside, "playerNPlayArea")):
                for card_id in raw.split(","):
                    card_id = card_id.strip()
                    if not card_id:
                        continue
                    card = cards.get(card_id)
                    if not card:
                        missing_ids.add(card_id)
                        continue
                    entries.append((card_id, card["name"], group, 1))
            collapsed = collapse(entries)
            if not collapsed:
                skipped_empty += 1
                continue
            deck_id = slug(name, used_ids)
            prebuilt[deck_id] = {"label": name, "cards": collapsed}
            grouped[swccg_group(name)].append((deck_id, name))

    group_list = [(label, grouped.get(label, [])) for label in SWCCG_GROUP_ORDER]
    dump_json(plugin / "jsons" / "preBuiltDecks.json", {"preBuiltDecks": prebuilt})
    dump_json(plugin / "jsons" / "deckMenu.json", menu_payload(group_list))
    return {
        "decks": len(prebuilt),
        "missing": len(missing_ids),
        "skipped": skipped_empty,
    }


def parse_lotr_packs(path: Path) -> list[tuple[str, list[tuple[int, str]]]]:
    packs: list[tuple[str, list[tuple[int, str]]]] = []
    name = ""
    pack_type = ""
    items: list[tuple[int, str]] = []
    in_items = False

    def flush() -> None:
        nonlocal name, pack_type, items
        if name and pack_type == "pack" and items:
            packs.append((name, items))
        name = ""
        pack_type = ""
        items = []

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = HJSON_NAME_RE.match(stripped)
        if match and not in_items:
            flush()
            name = match.group(1).strip().strip('"').strip("'")
            continue
        match = HJSON_TYPE_RE.match(stripped)
        if match and not in_items:
            pack_type = match.group(1)
            continue
        if stripped.startswith("items:"):
            in_items = True
            continue
        if in_items:
            if stripped.startswith("]"):
                in_items = False
                continue
            match = HJSON_ITEM_RE.match(stripped)
            if match:
                items.append((int(match.group(1)), match.group(2).rstrip(",")))
    flush()
    return packs


def lotr_label(name: str, group: str) -> str:
    if group == "Movie Special" and re.fullmatch(r"Special-\d+", name):
        return f"Movie Special {name.split('-', 1)[1]}"
    return name


def lotr_group_id(card_type: str) -> str:
    if card_type in {"SITE", "METASITE"}:
        return "playerNAdventureDeck"
    return "playerNDeck"


def write_lotr_prebuilts(plugin: Path = LOTR_PLUGIN) -> dict[str, int]:
    cards = load_cards(plugin / "tsvs" / "cards.tsv")
    prebuilt: dict[str, dict] = {}
    group_list: list[tuple[str, list[tuple[str, str]]]] = []
    used_ids: dict[str, int] = {}
    missing_ids: set[str] = set()
    skipped_empty = 0

    for filename, group_label in LOTR_STARTER_FILES:
        path = LOTR_PRODUCT / filename
        if not path.exists():
            continue
        decks: list[tuple[str, str]] = []
        for name, items in parse_lotr_packs(path):
            entries: list[tuple[str, str, str, int]] = []
            for qty, card_id in items:
                if not BLUEPRINT_RE.match(card_id):
                    continue
                card = cards.get(card_id)
                if not card:
                    missing_ids.add(card_id)
                    continue
                entries.append((card_id, card["name"], lotr_group_id(card["type"]), qty))
            collapsed = collapse(entries)
            if not collapsed:
                skipped_empty += 1
                continue
            label = lotr_label(name, group_label)
            deck_id = slug(label, used_ids)
            prebuilt[deck_id] = {"label": label, "cards": collapsed}
            decks.append((deck_id, label))
        group_list.append((group_label, decks))

    dump_json(plugin / "jsons" / "preBuiltDecks.json", {"preBuiltDecks": prebuilt})
    dump_json(plugin / "jsons" / "deckMenu.json", menu_payload(group_list))
    return {
        "decks": len(prebuilt),
        "missing": len(missing_ids),
        "skipped": skipped_empty,
    }


def append_source_note(path: Path, line: str) -> None:
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    prefix = line.split(":", 1)[0] + ":"
    lines = [existing for existing in lines if not existing.startswith(prefix)]
    while lines and not lines[-1].strip():
        lines.pop()
    lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    swccg = write_swccg_prebuilts()
    lotr = write_lotr_prebuilts()
    append_source_note(
        SWCCG_PLUGIN / "SOURCE.txt",
        f"Prebuilts: {swccg['decks']} GEMP Librarian sample decks (reserve + outside/play-area).",
    )
    append_source_note(
        LOTR_PLUGIN / "SOURCE.txt",
        f"Prebuilts: {lotr['decks']} GEMP starter packs (draw deck + adventure deck sites).",
    )
    print(f"SWCCG: {swccg['decks']} decks  missing ids: {swccg['missing']}  empty skipped: {swccg['skipped']}")
    print(f"LOTR:  {lotr['decks']} decks  missing ids: {lotr['missing']}  empty skipped: {lotr['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
