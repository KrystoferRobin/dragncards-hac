#!/usr/bin/env python3
"""Load official Magic starter/theme decks from MTGJSON into the plugin.

Reads the existing Lackey TSV (no full reimport). Nested Menu → Load:
block → set when the set has a block, otherwise just the set.

  python3 plugins/scripts/import_magic_precons.py
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
import zipfile
from collections import OrderedDict, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "uploaded" / "magic"
CACHE = ROOT / "Magic" / "mtgjson"
DECK_ZIP = CACHE / "AllDeckFiles.zip"
SET_LIST = CACHE / "SetList.json"
DECK_LIST = CACHE / "DeckList.json"

INCLUDE_TYPES = {
    "Theme Deck",
    "Intro Pack",
    "Welcome Deck",
    "Planeswalker Deck",
    "Event Deck",
    "Challenger Deck",
    "Starter Deck",
    "Welcome Booster",
    "Game Night Deck",
    "Starter Kit",
    "Advanced Deck",
    "Guild Kit",
    "Clash Pack",
    "Advanced Pack",
    "Pioneer Challenger Deck",
    "Demo Deck",
    "Spellslinger Starter Kit",
    "Challenge Deck",
}

KEEP_EXISTING_PREFIXES = ("battle-the-horde", "defeat-a-god", "face-the-hydra")


def dump_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "deck"


def norm_name(value: str) -> str:
    text = (value or "").split("//")[0]
    text = text.replace("\u2019", "'").replace("`", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()
    return text


def norm_set(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def collector_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def load_catalog(tsv: Path) -> list[dict[str, str]]:
    with tsv.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def build_indexes(cards: list[dict[str, str]]) -> tuple[dict, dict]:
    by_set: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    by_name: dict[str, list[dict[str, str]]] = defaultdict(list)
    for card in cards:
        name = norm_name(card.get("name") or "")
        if not name:
            continue
        by_name[name].append(card)
        for raw in (card.get("actualSet"), card.get("packName"), card.get("set")):
            key = norm_set(raw or "")
            if key:
                by_set[(name, key)].append(card)
    return by_set, by_name


def pick_card(card: dict, by_set: dict, by_name: dict) -> dict[str, str] | None:
    name = norm_name(card.get("name") or "")
    set_key = norm_set(card.get("setCode") or "")
    number = collector_key(card.get("number") or "")
    candidates = list(by_set.get((name, set_key), []))
    if not candidates:
        candidates = list(by_name.get(name, []))
    if not candidates:
        return None
    if number:
        numbered = []
        for row in candidates:
            url = (row.get("imageUrl") or "").lower()
            dbid = (row.get("databaseId") or "").lower()
            if url.endswith(f"/{number}.jpg") or url.endswith(f"/{number}.png"):
                numbered.append(row)
            elif f"-{number}" in dbid or dbid.endswith(number):
                numbered.append(row)
        if numbered:
            candidates = numbered
    if set_key:
        same = [row for row in candidates if set_key in {norm_set(row.get("actualSet") or ""), norm_set(row.get("packName") or "")}]
        if same:
            candidates = same
    return candidates[0]


def load_set_index() -> dict[str, dict]:
    payload = json.loads(SET_LIST.read_text(encoding="utf-8"))
    index = {}
    for entry in payload.get("data") or []:
        index[entry.get("code") or ""] = {
            "name": entry.get("name") or entry.get("code") or "Unknown set",
            "block": (entry.get("block") or "").strip(),
            "releaseDate": entry.get("releaseDate") or "9999-99-99",
            "type": entry.get("type") or "",
        }
    return index


def zip_member_map(archive: zipfile.ZipFile) -> dict[str, str]:
    mapping = {}
    for name in archive.namelist():
        if not name.lower().endswith(".json"):
            continue
        mapping[Path(name).stem] = name
    return mapping


def board_entries(cards: list[dict], group: str, by_set: dict, by_name: dict) -> tuple[list[dict], list[str]]:
    entries: list[dict] = []
    missing: list[str] = []
    merged: dict[tuple[str, str], int] = OrderedDict()
    names: dict[tuple[str, str], str] = {}
    for card in cards or []:
        if "Token" in (card.get("types") or []):
            continue
        row = pick_card(card, by_set, by_name)
        qty = int(card.get("count") or 1)
        if not row:
            missing.append(f"{card.get('count')} {card.get('name')} ({card.get('setCode')})")
            continue
        key = (row["databaseId"], group)
        merged[key] = merged.get(key, 0) + qty
        names[key] = row.get("name") or card.get("name") or row["databaseId"]
    for (database_id, load_group), quantity in merged.items():
        entries.append({"databaseId": database_id, "quantity": quantity, "loadGroupId": load_group})
    return entries, missing


def convert() -> tuple[dict, dict, dict]:
    cards = load_catalog(PLUGIN / "tsvs" / "cards.tsv")
    by_set, by_name = build_indexes(cards)
    sets = load_set_index()
    existing = json.loads((PLUGIN / "jsons" / "preBuiltDecks.json").read_text(encoding="utf-8"))
    keep = {
        deck_id: deck
        for deck_id, deck in (existing.get("preBuiltDecks") or {}).items()
        if deck_id in KEEP_EXISTING_PREFIXES or deck_id.startswith(KEEP_EXISTING_PREFIXES)
    }

    listing = json.loads(DECK_LIST.read_text(encoding="utf-8")).get("data") or []
    wanted = [item for item in listing if item.get("type") in INCLUDE_TYPES]
    prebuilt = OrderedDict(keep)
    stats = {
        "wanted": len(wanted),
        "included": 0,
        "skipped_empty": 0,
        "missing_lines": 0,
        "matched_cards": 0,
        "missing_examples": [],
    }
    menu_rows: list[dict] = []

    with zipfile.ZipFile(DECK_ZIP) as archive:
        members = zip_member_map(archive)
        for item in wanted:
            file_name = item.get("fileName") or ""
            member = members.get(file_name)
            if not member:
                stats["skipped_empty"] += 1
                continue
            payload = json.loads(archive.read(member))
            deck = payload.get("data") or payload
            entries: list[dict] = []
            missing: list[str] = []
            for group, key in (
                ("playerNDeck", "mainBoard"),
                ("playerNSideboard", "sideBoard"),
                ("playerNCommand", "commander"),
                ("playerNCommand", "displayCommander"),
            ):
                batch, miss = board_entries(deck.get(key) or [], group, by_set, by_name)
                entries.extend(batch)
                missing.extend(miss)
            if not entries:
                stats["skipped_empty"] += 1
                continue
            deck_id = slug(file_name)
            if deck_id in prebuilt:
                deck_id = slug(f"{file_name}-{item.get('code')}")
            label = deck.get("name") or item.get("name") or file_name
            code = deck.get("code") or item.get("code") or ""
            set_info = sets.get(code) or {"name": code or "Unknown set", "block": "", "releaseDate": item.get("releaseDate") or "9999-99-99"}
            prebuilt[deck_id] = {"label": label, "cards": entries}
            menu_rows.append(
                {
                    "id": deck_id,
                    "label": label,
                    "type": item.get("type") or deck.get("type") or "",
                    "code": code,
                    "setName": set_info["name"],
                    "block": set_info.get("block") or "",
                    "releaseDate": set_info.get("releaseDate") or item.get("releaseDate") or "9999-99-99",
                }
            )
            stats["included"] += 1
            stats["matched_cards"] += sum(card["quantity"] for card in entries)
            stats["missing_lines"] += len(missing)
            if missing and len(stats["missing_examples"]) < 12:
                stats["missing_examples"].append(f"{label}: {missing[0]}")

    menu = build_menu(menu_rows, keep)
    return {"preBuiltDecks": dict(prebuilt)}, menu, stats


def build_menu(rows: list[dict], keep: dict) -> dict:
    by_block: dict[str, dict] = OrderedDict()
    block_dates: dict[str, str] = {}
    for row in rows:
        block = row["block"]
        bucket = block or row["setName"]
        block_dates[bucket] = min(block_dates.get(bucket, "9999-99-99"), row["releaseDate"])
        info = by_block.setdefault(bucket, {"has_block": bool(block), "sets": OrderedDict()})
        set_bucket = info["sets"].setdefault(
            row["code"],
            {"label": row["setName"], "releaseDate": row["releaseDate"], "decks": []},
        )
        set_bucket["releaseDate"] = min(set_bucket["releaseDate"], row["releaseDate"])
        set_bucket["decks"].append(row)

    submenus = []
    if keep:
        submenus.append(
            {
                "label": "Challenge Decks",
                "deckLists": [{"deckListId": deck_id, "label": deck["label"]} for deck_id, deck in keep.items()],
            }
        )

    for bucket, _date in sorted(block_dates.items(), key=lambda item: (item[1], item[0])):
        info = by_block[bucket]
        sets = sorted(info["sets"].values(), key=lambda item: (item["releaseDate"], item["label"]))
        if info["has_block"] and len(sets) >= 1:
            children = []
            for set_info in sets:
                decks = sorted(set_info["decks"], key=lambda item: item["label"])
                children.append(
                    {
                        "label": set_info["label"],
                        "deckLists": [{"deckListId": deck["id"], "label": deck["label"]} for deck in decks],
                    }
                )
            submenus.append({"label": bucket, "subMenus": children})
        else:
            decks = sorted((deck for set_info in sets for deck in set_info["decks"]), key=lambda item: item["label"])
            submenus.append(
                {
                    "label": bucket,
                    "deckLists": [{"deckListId": deck["id"], "label": deck["label"]} for deck in decks],
                }
            )
    return {"deckMenu": {"subMenus": submenus}}


def main() -> int:
    if not (PLUGIN / "tsvs" / "cards.tsv").exists():
        raise SystemExit(f"Missing catalog: {PLUGIN / 'tsvs' / 'cards.tsv'}")
    if not DECK_ZIP.exists() or not SET_LIST.exists() or not DECK_LIST.exists():
        raise SystemExit(f"Missing MTGJSON cache under {CACHE} (DeckList.json, SetList.json, AllDeckFiles.zip)")
    decks, menu, stats = convert()
    dump_json(PLUGIN / "jsons" / "preBuiltDecks.json", decks)
    dump_json(PLUGIN / "jsons" / "deckMenu.json", menu)
    print(f"wanted {stats['wanted']}  included {stats['included']}  empty {stats['skipped_empty']}")
    print(f"matched cards {stats['matched_cards']}  unmatched lines {stats['missing_lines']}")
    print(f"menu groups {len(menu['deckMenu']['subMenus'])}")
    for example in stats["missing_examples"]:
        print(f"  miss: {example}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
