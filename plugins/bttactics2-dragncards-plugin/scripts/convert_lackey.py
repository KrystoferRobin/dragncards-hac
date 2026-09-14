#!/usr/bin/env python3
"""Convert the LackeyCCG BT Tactics 2 plugin into a DragnCards dumb table."""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from image_names import stamp_lobby_art  # noqa: E402

LACKEY_DIR = Path(r"C:\Users\chris\Documents\e-Sword\tests\LackeyCCG\plugins\bttactics2")
PLUGIN_DIR = Path(r"C:\Users\chris\Documents\e-Sword\dragncards\bttactics2-dragncards-plugin")
SETS_DIR = LACKEY_DIR / "sets"
DECKS_DIR = LACKEY_DIR / "decks"
JSONS_DIR = PLUGIN_DIR / "jsons"
TSV_OUT = PLUGIN_DIR / "tsvs" / "cards.tsv"
GAME_FOLDER = "battletech-tactics-2"

IMAGE_BASE = "https://www.knightsoftheinnersphere.com/lackey/bttactics2/cardimages/"
CARD_BACK_URL = "https://www.knightsoftheinnersphere.com/lackey/bttactics2/images/cardback.jpg"
TOKEN_BASE = "https://www.knightsoftheinnersphere.com/lackey/bttactics2/images/"

ZONE_BORDER = "1px solid rgba(210, 210, 210, 0.55)"

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "set",
    "legal",
    "rarity",
    "keywords",
    "alignment",
    "affiliation",
    "cost",
    "asset",
    "attack",
    "armor",
    "structure",
    "speed",
    "mass",
    "armament",
    "text",
    "loadGroupId",
]

SUPERZONE_TO_GROUP = {
    "Deck": "playerNStockpile",
    "Sideboard": "playerNSideboard",
    "Main Deck": "playerNStockpile",
    "Resource Deck": "playerNStockpile",
}


def sanitize(value: str) -> str:
    return (value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()


def fold_name(value: str) -> str:
    text = sanitize(value)
    text = text.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return text.casefold()


def image_url(image_file: str) -> str:
    name = sanitize(image_file)
    if not name:
        return ""
    if "." not in Path(name).name:
        name = f"{name}.jpg"
    return IMAGE_BASE + name.replace("\\", "/")


def slug(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", text).strip()
    parts = cleaned.split()
    if not parts:
        return "deck"
    return parts[0].lower() + "".join(part.title() for part in parts[1:])


def col(row: dict[str, str], *names: str) -> str:
    for name in names:
        if name in row:
            return sanitize(row[name])
    return ""


def load_cards() -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for path in sorted(SETS_DIR.glob("*.txt")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines:
            continue
        header = [h.strip() for h in lines[0].split("\t")]
        for line_no, line in enumerate(lines[1:], start=2):
            if not line.strip():
                continue
            values = line.split("\t")
            while len(values) < len(header):
                values.append("")
            row = {header[i]: values[i] for i in range(len(header))}
            name = col(row, "Name")
            set_name = col(row, "Set")
            image_file = col(row, "ImageFile")
            card_type = col(row, "Type") or "Unit"
            if not name or not image_file:
                errors.append(f"{path.name}:{line_no} missing name or ImageFile")
                continue
            database_id = image_file
            if database_id in seen_ids:
                errors.append(f"Duplicate databaseId {database_id} at {path.name}:{line_no}")
                continue
            seen_ids.add(database_id)
            affiliation = col(row, "Affiliation").replace("|", " ").strip()
            cards.append(
                {
                    "databaseId": database_id,
                    "name": name,
                    "imageUrl": image_url(image_file),
                    "cardBack": "default",
                    "type": card_type,
                    "set": set_name,
                    "legal": col(row, "Legal"),
                    "rarity": col(row, "Rarity"),
                    "keywords": col(row, "Keywords"),
                    "alignment": col(row, "Alignment"),
                    "affiliation": affiliation,
                    "cost": col(row, "Cost"),
                    "asset": col(row, "Asset"),
                    "attack": col(row, "Attack"),
                    "armor": col(row, "Armor"),
                    "structure": col(row, "Structure"),
                    "speed": col(row, "Speed"),
                    "mass": col(row, "Mass"),
                    "armament": col(row, "Armament", "Armaments"),
                    "text": col(row, "Text"),
                    "loadGroupId": "playerNStockpile",
                }
            )
    return cards, errors


def write_tsv(cards: list[dict[str, str]]) -> None:
    TSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = ["\t".join(TSV_COLUMNS)]
    for card in cards:
        rows.append("\t".join(sanitize(card.get(column, "")) for column in TSV_COLUMNS))
    TSV_OUT.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_json(name: str, payload: dict) -> None:
    JSONS_DIR.mkdir(parents=True, exist_ok=True)
    path = JSONS_DIR / name
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def pct(value: float) -> str:
    return f"{value:g}%"


def region_style(background: str, border: str = ZONE_BORDER) -> dict:
    return {"background": background, "border": border, "boxSizing": "border-box"}


def pile(group_id: str, left: float, top: float, width: float = 6.0, height: float = 11.0) -> dict:
    return {
        "groupId": group_id,
        "type": "pile",
        "direction": "horizontal",
        "left": pct(left),
        "top": pct(top),
        "width": pct(width),
        "height": pct(height),
        "style": region_style("rgba(0, 0, 0, 0.35)"),
    }


def row_region(
    group_id: str,
    left: float,
    top: float,
    width: float,
    height: float,
    background: str,
    region_type: str = "row",
    disable_attachments: bool = False,
) -> dict:
    region = {
        "groupId": group_id,
        "type": region_type,
        "direction": "horizontal",
        "left": pct(left),
        "top": pct(top),
        "width": pct(width),
        "height": pct(height),
        "style": region_style(background),
    }
    if disable_attachments:
        region["disableDroppableAttachments"] = True
    return region


def player_groups(pid: str, n: str) -> dict:
    def enter(extra: dict | None = None) -> dict:
        data = {
            "controller": pid,
            "deckGroupId": f"{pid}Stockpile",
            "discardGroupId": f"{pid}Scrapheap",
        }
        if extra:
            data.update(extra)
        return data

    return {
        f"{pid}Stockpile": {
            "groupType": "stockpile",
            "label": f"Player {n} Stockpile",
            "tableLabel": "Stockpile",
            "onCardEnter": enter(),
        },
        f"{pid}Scrapheap": {
            "groupType": "scrapheap",
            "label": f"Player {n} Scrapheap",
            "tableLabel": "Scrap",
            "onCardEnter": enter(),
        },
        f"{pid}Removed": {
            "groupType": "removed",
            "label": f"Player {n} Removed",
            "tableLabel": "RFG",
            "onCardEnter": enter(),
        },
        f"{pid}Sideboard": {
            "groupType": "sideboard",
            "label": f"Player {n} Sideboard",
            "tableLabel": "Side",
            "onCardEnter": enter(),
        },
        f"{pid}Hand": {
            "groupType": "hand",
            "label": f"Player {n} Hand",
            "tableLabel": "Hand",
            "onCardEnter": enter(),
        },
        f"{pid}Resources": {
            "groupType": "inPlay",
            "label": f"Player {n} Resources",
            "tableLabel": "Resources",
            "canHaveAttachments": False,
            "onCardEnter": enter({"inPlay": True}),
        },
        f"{pid}Units": {
            "groupType": "inPlay",
            "label": f"Player {n} Units",
            "tableLabel": "Units",
            "canHaveAttachments": True,
            "onCardEnter": enter({"inPlay": True}),
        },
        f"{pid}Commands": {
            "groupType": "inPlay",
            "label": f"Player {n} Commands",
            "tableLabel": "Cmd",
            "canHaveAttachments": False,
            "onCardEnter": enter({"inPlay": True}),
        },
        f"{pid}Tokens": {
            "groupType": "tokens",
            "label": f"Player {n} Tokens",
            "tableLabel": "Tokens",
            "onCardEnter": enter(),
        },
    }


def make_groups() -> dict:
    groups = {
        "sharedSetAside": {
            "groupType": "aside",
            "label": "Set Aside",
            "tableLabel": "Set Aside",
            "onCardEnter": {"controller": "shared"},
        }
    }
    groups.update(player_groups("player1", "1"))
    groups.update(player_groups("player2", "2"))
    return {"groups": groups}


def make_layouts() -> dict:
    play_w = 87.0
    pile_w = 6.0
    col1, col2 = 88.0, 94.0
    hand_w = 69.6
    chat_left = hand_w
    chat_w = play_w - chat_left
    hand_bg = "rgba(0, 0, 0, 0.32)"
    res_bg = "rgba(70, 55, 20, 0.36)"
    unit_bg = "rgba(30, 55, 40, 0.36)"
    cmd_bg = "rgba(40, 30, 70, 0.36)"
    regions = {
        "playerN+1Hand": row_region("playerN+1Hand", 0, 0, play_w, 8, hand_bg, "fan", True),
        "playerN+1Resources": row_region("playerN+1Resources", 0, 8, play_w, 9, res_bg, "row", True),
        "playerN+1Units": row_region("playerN+1Units", 0, 17, play_w, 14, unit_bg),
        "playerN+1Commands": row_region("playerN+1Commands", 0, 31, play_w, 7, cmd_bg, "row", True),
        "playerNCommands": row_region("playerNCommands", 0, 38, play_w, 7, cmd_bg, "row", True),
        "playerNUnits": row_region("playerNUnits", 0, 45, play_w, 14, unit_bg),
        "playerNResources": row_region("playerNResources", 0, 59, play_w, 9, res_bg, "row", True),
        "playerNHand": row_region("playerNHand", 0, 68, chat_left, 32, hand_bg, "fan", True),
        "playerN+1Stockpile": pile("playerN+1Stockpile", col1, 8.0, pile_w),
        "playerN+1Scrapheap": pile("playerN+1Scrapheap", col2, 8.0, pile_w),
        "playerN+1Removed": pile("playerN+1Removed", col1, 19.5, pile_w),
        "playerN+1Sideboard": pile("playerN+1Sideboard", col2, 19.5, pile_w),
        "playerN+1Tokens": pile("playerN+1Tokens", col1, 31.0, pile_w),
        "playerNStockpile": pile("playerNStockpile", col1, 56.0, pile_w),
        "playerNScrapheap": pile("playerNScrapheap", col2, 56.0, pile_w),
        "playerNRemoved": pile("playerNRemoved", col1, 67.5, pile_w),
        "playerNSideboard": pile("playerNSideboard", col2, 67.5, pile_w),
        "playerNTokens": pile("playerNTokens", col1, 79.0, pile_w),
        "sharedSetAside": row_region("sharedSetAside", col1, 90.0, pile_w * 2, 10.0, "rgba(0, 0, 0, 0.45)", "fan", True),
    }
    table_buttons = {
        "drawStockpile": {
            "actionList": "drawStockpile",
            "label": "Draw",
            "left": pct(col1),
            "top": "47%",
            "width": pct(pile_w),
            "height": "4%",
        },
        "shuffleStockpile": {
            "actionList": "shuffleStockpile",
            "label": "Shuf",
            "left": pct(col2),
            "top": "47%",
            "width": pct(pile_w),
            "height": "4%",
        },
        "untapAll": {
            "actionList": "untapAll",
            "label": "Untap",
            "left": pct(col1),
            "top": "51.5%",
            "width": "6%",
            "height": "4%",
        },
        "roll1d6": {
            "actionList": "roll1d6",
            "label": "d6",
            "left": "94%",
            "top": "51.5%",
            "width": "6%",
            "height": "4%",
        },
    }
    return {
        "layouts": {
            "default": {
                "cardSize": 9,
                "rowSpacing": 1,
                "chat": {"left": pct(chat_left), "top": "68%", "width": pct(chat_w), "height": "32%"},
                "regions": regions,
                "tableButtons": table_buttons,
            }
        }
    }


def make_card_types(cards: list[dict[str, str]]) -> dict:
    types = {
        kind: {"width": 0.72, "height": 1.0, "tokens": ["damage", "construction", "generic"]}
        for kind in sorted({card["type"] for card in cards})
    }
    return {"cardTypes": types}


def make_card_backs() -> dict:
    return {"cardBacks": {"default": {"width": 0.72, "height": 1.0, "imageUrl": CARD_BACK_URL}}}


def make_browse(_cards: list[dict[str, str]]) -> dict:
    return {
        "browse": {
            "filterPropertySideA": "type",
            "filterValuesSideA": ["Unit", "Command", "Mission", "Box Power"],
            "textPropertiesSideA": ["name", "text", "keywords", "affiliation", "set", "cost"],
        }
    }


def parse_dek(path: Path) -> dict[str, Counter]:
    text = path.read_text(encoding="utf-8", errors="replace")
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
            if name_el is None:
                continue
            image_id = (name_el.attrib.get("id") or "").strip()
            card_name = sanitize(name_el.text or "")
            set_name = sanitize(set_el.text if set_el is not None else "")
            counts[(image_id, card_name, set_name)] += 1
        zones[zone_name] = counts
    return zones


def resolve_card(
    image_id: str,
    card_name: str,
    set_name: str,
    by_id: dict[str, str],
    by_name_set: dict[tuple[str, str], str],
    by_name: dict[str, list[str]],
) -> str | None:
    if image_id and image_id in by_id:
        return by_id[image_id]
    key = (fold_name(card_name), fold_name(set_name))
    if key in by_name_set:
        return by_name_set[key]
    matches = by_name.get(fold_name(card_name), [])
    if len(matches) == 1:
        return matches[0]
    return None


def make_prebuilts(cards: list[dict[str, str]]) -> tuple[dict, dict, list[str]]:
    by_id = {card["databaseId"]: card["databaseId"] for card in cards}
    by_name_set = {(fold_name(card["name"]), fold_name(card["set"])): card["databaseId"] for card in cards}
    by_name: dict[str, list[str]] = {}
    for card in cards:
        by_name.setdefault(fold_name(card["name"]), []).append(card["databaseId"])
    errors: list[str] = []
    prebuilts: dict[str, dict] = {}
    menus = [
        ("Beginner", "Beginner Decks", "Beginner."),
        ("F20", "F20 Decks", "F20."),
    ]
    menu: list[dict] = []
    for _key, section, prefix in menus:
        section_lists: list[dict] = []
        for path in sorted(DECKS_DIR.glob("*.dek")):
            if not path.name.startswith(prefix):
                continue
            label = path.stem.replace("Beginner.", "").replace("F20.", "").replace("_", " ").replace(".", " ")
            deck_id = slug(path.stem)
            zones = parse_dek(path)
            load_list: list[dict] = []
            for zone_name, counts in zones.items():
                load_group = SUPERZONE_TO_GROUP.get(zone_name)
                if not load_group:
                    errors.append(f"{path.name}: unknown superzone '{zone_name}'")
                    continue
                for (image_id, card_name, set_name), quantity in counts.items():
                    database_id = resolve_card(image_id, card_name, set_name, by_id, by_name_set, by_name)
                    if not database_id:
                        errors.append(f"{path.name}: unknown card {card_name!r} ({set_name}/{image_id})")
                        continue
                    load_list.append(
                        {"databaseId": database_id, "quantity": quantity, "loadGroupId": load_group}
                    )
            if not load_list:
                errors.append(f"{path.name}: no cards loaded")
                continue
            prebuilts[deck_id] = {"label": label, "cards": load_list}
            section_lists.append({"label": label, "deckListId": deck_id})
        if section_lists:
            menu.append({"label": section, "deckLists": section_lists})
    return {"preBuiltDecks": prebuilts}, {"deckMenu": {"subMenus": menu}}, errors


def main() -> int:
    cards, errors = load_cards()
    write_tsv(cards)
    write_json("groups.json", make_groups())
    write_json("layouts.json", make_layouts())
    write_json("cardTypes.json", make_card_types(cards))
    write_json("cardBacks.json", make_card_backs())
    write_json("browse.json", make_browse(cards))
    prebuilts, menu, deck_errors = make_prebuilts(cards)
    errors.extend(deck_errors)
    write_json("preBuiltDecks.json", prebuilts)
    write_json("deckMenu.json", menu)
    stamp_lobby_art(JSONS_DIR, GAME_FOLDER)

    types = sorted({card["type"] for card in cards})
    sets = sorted({card["set"] for card in cards})
    print(f"Wrote {len(cards)} cards to {TSV_OUT}")
    print(f"Sets ({len(sets)}): {', '.join(sets)}")
    print(f"Types: {', '.join(types)}")
    print(f"Pre-built decks: {len(prebuilts['preBuiltDecks'])}")
    if errors:
        print(f"\n{len(errors)} issue(s):")
        for err in errors[:80]:
            print(f"  - {err}")
        if len(errors) > 80:
            print(f"  ... {len(errors) - 80} more")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
