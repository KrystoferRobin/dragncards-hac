#!/usr/bin/env python3
"""Convert the LackeyCCG Wyvern plugin into DragnCards TSV + pre-built decks."""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from image_names import stamp_lobby_art  # noqa: E402

LACKEY_DIR = Path(r"C:\Users\chris\Documents\e-Sword\tests\LackeyCCG\plugins\Wyvern")
PLUGIN_DIR = Path(r"C:\Users\chris\Documents\e-Sword\dragncards\wyvern-dragncards-plugin")
CARDDATA = LACKEY_DIR / "sets" / "carddata.txt"
IMAGE_URLS = LACKEY_DIR / "CardImageURLs1.txt"
DECKS_DIR = LACKEY_DIR / "decks"
TSV_OUT = PLUGIN_DIR / "tsvs" / "cards.tsv"
DECKS_OUT = PLUGIN_DIR / "jsons" / "preBuiltDecks.json"
DECK_MENU_OUT = PLUGIN_DIR / "jsons" / "deckMenu.json"
JSONS_DIR = PLUGIN_DIR / "jsons"
GAME_FOLDER = "wyvern"

TYPE_ALIASES = {
    "Dragon Slayer Action Action": "Dragon Slayer Action",
}

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "gold",
    "set",
    "number",
    "rarity",
    "text",
    "lore",
    "strength",
    "strengthModifier",
    "loadGroupId",
]

DECK_FILES = [
    ("worldChamp1995", "1995 World Champ Deck", "1995_World_Champ_Deck.dek"),
    ("themeHelp", "Theme Deck: Help", "Theme_Deck_Help.dek"),
    ("themeNativeTerrain", "Theme Deck: Native Terrain", "Theme_Deck_Native_Terrain.dek"),
]

SUPERZONE_TO_GROUP = {
    "Treasure Horde": "playerNTreasureHorde",
    "Dragon Lair": "playerNDragonLair",
}

STRENGTH_RE = re.compile(r"STRENGTH:\s*(-?\d+)", re.IGNORECASE)
MODIFIER_RE = re.compile(r"STRENGTH\s+MODIFIER:\s*([+-]?\d+)", re.IGNORECASE)


def sanitize(value: str) -> str:
    return (
        (value or "")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("\t", " ")
        .strip()
    )


def parse_strength(text: str) -> tuple[str, str]:
    strength = ""
    modifier = ""
    mod_match = MODIFIER_RE.search(text or "")
    if mod_match:
        modifier = mod_match.group(1)
    # Avoid treating "STRENGTH MODIFIER" as a base strength.
    strength_text = MODIFIER_RE.sub("", text or "")
    str_match = STRENGTH_RE.search(strength_text)
    if str_match:
        strength = str_match.group(1)
    return strength, modifier


def load_image_urls(path: Path) -> dict[str, str]:
    urls: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("CardImageURLs"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        rel_path = parts[0].strip().replace("\\", "/")
        url = parts[1].strip()
        if not rel_path or not url:
            continue
        lower = rel_path.lower()
        urls[lower] = url
        filename = lower.split("/")[-1]
        urls[filename] = url
        urls[filename.rsplit(".", 1)[0]] = url
    return urls


def lookup_image_url(urls: dict[str, str], set_name: str, image_file: str) -> str | None:
    candidates = [
        f"{set_name}/{image_file}".lower(),
        f"{set_name}/{image_file}.jpg".lower(),
        image_file.lower(),
        f"{image_file.lower()}.jpg",
        image_file.lower().rsplit(".", 1)[0],
    ]
    for key in candidates:
        if key in urls:
            return urls[key]
    return None


def load_cards(carddata_path: Path, urls: dict[str, str]) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    lines = carddata_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        raise SystemExit(f"Empty card data: {carddata_path}")

    header = [h.strip() for h in lines[0].split("\t")]
    expected = ["Name", "Set", "ImageFile", "Type", "Gold", "Number", "Rarity", "Text", "Lore"]
    if header[:9] != expected:
        errors.append(f"Unexpected carddata header: {header}")

    for line_no, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        cols = line.split("\t")
        # Pad so Lore can be missing.
        while len(cols) < 9:
            cols.append("")
        name, set_name, image_file, card_type, gold, number, rarity, text, lore = [
            sanitize(c) for c in cols[:9]
        ]
        card_type = TYPE_ALIASES.get(card_type, card_type)
        database_id = f"{set_name}_{image_file}"
        if database_id in seen_ids:
            errors.append(f"Duplicate databaseId {database_id} at line {line_no}")
            continue
        seen_ids.add(database_id)

        image_url = lookup_image_url(urls, set_name, image_file)
        if not image_url:
            errors.append(f"Missing image URL for {database_id} ({set_name}/{image_file})")
            image_url = ""

        strength, modifier = parse_strength(text)
        load_group = "playerNDragonLair" if card_type == "Dragon" else "playerNTreasureHorde"

        cards.append(
            {
                "databaseId": database_id,
                "name": name,
                "imageUrl": image_url,
                "cardBack": "default",
                "type": card_type,
                "gold": gold,
                "set": set_name,
                "number": number,
                "rarity": rarity,
                "text": text,
                "lore": lore,
                "strength": strength,
                "strengthModifier": modifier,
                "loadGroupId": load_group,
            }
        )

    return cards, errors


def write_tsv(cards: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["\t".join(TSV_COLUMNS)]
    for card in cards:
        rows.append("\t".join(sanitize(card.get(col, "")) for col in TSV_COLUMNS))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def parse_dek(path: Path) -> dict[str, Counter]:
    """Return {superzone: Counter(databaseId)}."""
    text = path.read_text(encoding="utf-8", errors="replace")
    # Lackey files are not always strictly valid XML; wrap if needed.
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        root = ET.fromstring(f"<root>{text}</root>")

    zones: dict[str, Counter] = {}
    for superzone in root.findall(".//superzone"):
        zone_name = superzone.attrib.get("name", "").strip()
        counts: Counter = Counter()
        for card in superzone.findall("card"):
            name_el = card.find("name")
            set_el = card.find("set")
            if name_el is None or set_el is None:
                continue
            image_id = (name_el.attrib.get("id") or "").strip()
            set_name = (set_el.text or "").strip()
            if not image_id or not set_name:
                continue
            counts[f"{set_name}_{image_id}"] += 1
        zones[zone_name] = counts
    return zones


def convert_decks(cards: list[dict[str, str]]) -> tuple[dict, list[str]]:
    known_ids = {card["databaseId"] for card in cards}
    errors: list[str] = []
    prebuilt: OrderedDict[str, dict] = OrderedDict()

    for deck_id, label, filename in DECK_FILES:
        dek_path = DECKS_DIR / filename
        if not dek_path.exists():
            errors.append(f"Missing deck file: {dek_path}")
            continue
        zones = parse_dek(dek_path)
        load_cards = []
        for zone_name, counts in zones.items():
            load_group = SUPERZONE_TO_GROUP.get(zone_name)
            if not load_group:
                errors.append(f"{filename}: unknown superzone '{zone_name}'")
                continue
            for database_id, quantity in counts.items():
                if database_id not in known_ids:
                    errors.append(f"{filename}: unknown card {database_id}")
                    continue
                load_cards.append(
                    {
                        "databaseId": database_id,
                        "quantity": quantity,
                        "loadGroupId": load_group,
                    }
                )
        prebuilt[deck_id] = {"label": label, "cards": load_cards}

    deck_menu = {
        "subMenus": [
            {
                "label": "Sample Decks",
                "deckLists": [
                    {"label": label, "deckListId": deck_id}
                    for deck_id, label, _filename in DECK_FILES
                    if deck_id in prebuilt
                ],
            }
        ]
    }
    return {"preBuiltDecks": dict(prebuilt), "deckMenu": deck_menu}, errors


def main() -> int:
    urls = load_image_urls(IMAGE_URLS)
    cards, errors = load_cards(CARDDATA, urls)
    write_tsv(cards, TSV_OUT)

    generated, deck_errors = convert_decks(cards)
    errors.extend(deck_errors)
    DECKS_OUT.parent.mkdir(parents=True, exist_ok=True)
    DECKS_OUT.write_text(
        json.dumps({"preBuiltDecks": generated["preBuiltDecks"]}, indent=2) + "\n",
        encoding="utf-8",
    )
    DECK_MENU_OUT.write_text(
        json.dumps({"deckMenu": generated["deckMenu"]}, indent=2) + "\n",
        encoding="utf-8",
    )
    stamp_lobby_art(JSONS_DIR, GAME_FOLDER)

    types = sorted({card["type"] for card in cards})
    sets = sorted({card["set"] for card in cards})
    missing_urls = sum(1 for card in cards if not card["imageUrl"])
    print(f"Wrote {len(cards)} cards to {TSV_OUT}")
    print(f"Sets: {', '.join(sets)}")
    print(f"Types: {', '.join(types)}")
    print(f"Missing image URLs: {missing_urls}")
    print(f"Wrote {DECKS_OUT.name} and {DECK_MENU_OUT.name}")
    if errors:
        print(f"\n{len(errors)} issue(s):")
        for err in errors:
            print(f"  - {err}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
