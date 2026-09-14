#!/usr/bin/env python3
"""Convert the OCTGN 7th Sea CCG definition into a DragnCards dumb table.

Copies card images out of the OCTGN GUID folders into a centralized
images/7th-sea/{set}/ tree named Game-Set-Cardname, and writes TSV + generated JSON.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from image_names import TOYBOX_PREFIX, stamp_lobby_art  # noqa: E402

OCTGN_GAME = Path(r"C:\Games\octgn\Data\GameDatabase\844ed56c-2048-41a6-97b0-3515185e1634")
OCTGN_IMAGES = Path(r"C:\Games\octgn\Data\ImageDatabase\844ed56c-2048-41a6-97b0-3515185e1634")
PLUGIN_DIR = Path(r"C:\Users\chris\Documents\e-Sword\dragncards\7th-sea-dragncards-plugin")
IMAGES_ROOT = Path(r"C:\Users\chris\Documents\e-Sword\dragncards\images")
JSONS_DIR = PLUGIN_DIR / "jsons"
TSV_OUT = PLUGIN_DIR / "tsvs" / "cards.tsv"
MANIFEST_OUT = IMAGES_ROOT / "7th-sea" / "_manifest.tsv"

GAME_LABEL = "7th Sea"
GAME_FOLDER = "7th-sea"
GAME_PASCAL = "7thSea"

ZONE_BORDER = "1px solid rgba(210, 210, 210, 0.55)"

TYPE_MAP = {
    "crew": "Crew",
    "captains": "Captain",
    "captain": "Captain",
    "ships": "Ship",
    "ship": "Ship",
    "actions": "Action",
    "action": "Action",
    "attachments": "Attachment",
    "attachment": "Attachment",
    "adventures": "Adventure",
    "adventure": "Adventure",
    "chanteys": "Chantey",
    "chantey": "Chantey",
    "seas": "Sea",
    "sea": "Sea",
}

LOAD_BY_TYPE = {
    "Ship": "playerNShip",
    "Captain": "playerNCaptain",
    "Sea": "sharedSetAside",
}

SEA_ORDER = [
    ("7a5eea90-fbf1-428b-8a77-276f9595c895", "sharedTradeSea", "Trade Sea"),
    ("9b8f6f87-20b9-4ef3-b2e8-9073ac23f4e8", "sharedFrothingSea", "Frothing Sea"),
    ("aa019c17-0c60-4d80-be22-88a1356ea71f", "sharedLaBoca", "La Boca"),
    ("130ec464-b05d-4dfc-91fe-b880432b38dd", "sharedForbiddenSea", "Forbidden Sea"),
    ("99fc650e-522b-402d-b776-18ec9ce8514d", "sharedTheMirror", "The Mirror"),
]

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "set",
    "faction",
    "cost",
    "costType",
    "cancel",
    "cancelType",
    "wealth",
    "attack",
    "parry",
    "cannon",
    "sailing",
    "adventuring",
    "influence",
    "swashbuckling",
    "crewMax",
    "moveCost",
    "rarity",
    "text",
    "loadGroupId",
]


def sanitize(value: str) -> str:
    return (value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()


def folder_slug(name: str) -> str:
    cleaned = name.replace("'", "").replace("\u2019", "")
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", cleaned).strip("-").lower()
    return cleaned or "set"


def pascal(name: str) -> str:
    cleaned = name.replace("'", "").replace("\u2019", "")
    parts = re.sub(r"[^A-Za-z0-9]+", " ", cleaned).split()
    if not parts:
        return "Card"
    return "".join(part[:1].upper() + part[1:] for part in parts)


def file_stem(set_name: str, card_name: str) -> str:
    return f"{GAME_PASCAL}-{pascal(set_name)}-{pascal(card_name)}"


def normalize_type(raw: str) -> str:
    return TYPE_MAP.get((raw or "").strip().casefold(), "Crew" if not raw else pascal(raw))


def prop(card: ET.Element, name: str) -> str:
    for child in card.findall("property"):
        if child.attrib.get("name") == name:
            return sanitize(child.attrib.get("value", ""))
    return ""


def pick_image(set_id: str, card_id: str) -> Path | None:
    cards_dir = OCTGN_IMAGES / "Sets" / set_id / "Cards"
    if not cards_dir.exists():
        return None
    candidates: list[Path] = []
    for path in cards_dir.iterdir():
        if not path.is_file():
            continue
        if path.stem.lower() == card_id.lower() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            candidates.append(path)
    if not candidates:
        return None
    candidates.sort(key=lambda p: (p.stat().st_size, p.suffix.lower() == ".png"), reverse=True)
    return candidates[0]


def copy_plugin_art() -> dict[str, str]:
    dest_dir = IMAGES_ROOT / GAME_FOLDER / "_plugin"
    dest_dir.mkdir(parents=True, exist_ok=True)
    mapping = {}
    sources = {
        "7thSea-cardback.jpg": OCTGN_GAME / "Card" / "cardback.jpg",
        "7thSea-TheahBackground.jpg": OCTGN_GAME / "Background" / "Theah_background.jpg",
    }
    for name, source in sources.items():
        if source.exists():
            dest = dest_dir / name
            shutil.copy2(source, dest)
            mapping[name] = f"{GAME_FOLDER}/_plugin/{name}"
    return mapping


def load_cards() -> tuple[list[dict[str, str]], list[str], list[tuple[str, str, Path]]]:
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    copies: list[tuple[str, str, Path]] = []
    used_names: dict[str, int] = {}
    plugin_art = copy_plugin_art()
    cardback_rel = plugin_art.get("7thSea-cardback.jpg", f"{GAME_FOLDER}/_plugin/7thSea-cardback.jpg")

    for set_path in sorted((OCTGN_GAME / "Sets").glob("*/set.xml")):
        root = ET.parse(set_path).getroot()
        set_name = root.attrib.get("name", set_path.parent.name)
        set_id = root.attrib.get("id", "")
        set_folder = folder_slug(set_name)
        for card_el in root.findall("cards/card"):
            card_id = card_el.attrib.get("id", "").strip()
            name = sanitize(card_el.attrib.get("name", ""))
            if not card_id or not name:
                errors.append(f"{set_name}: missing id or name")
                continue
            card_type = normalize_type(prop(card_el, "Type"))
            source = pick_image(set_id, card_id)
            stem = file_stem(set_name, name)
            key = f"{set_folder}/{stem}".casefold()
            used_names[key] = used_names.get(key, 0) + 1
            if used_names[key] > 1:
                stem = f"{stem}-{used_names[key]}"
            ext = source.suffix.lower() if source else ".jpg"
            if ext == ".jpeg":
                ext = ".jpg"
            rel = f"{GAME_FOLDER}/{set_folder}/{stem}{ext}"
            if source:
                copies.append((rel, f"{set_name}\t{name}\t{card_id}\t{source}", source))
            else:
                errors.append(f"Missing image: {set_name} / {name} ({card_id})")
                rel = cardback_rel
            cards.append(
                {
                    "databaseId": card_id,
                    "name": name,
                    "imageUrl": rel.replace("\\", "/"),
                    "cardBack": "default",
                    "type": card_type,
                    "set": set_name,
                    "faction": prop(card_el, "Faction"),
                    "cost": prop(card_el, "Cost"),
                    "costType": prop(card_el, "Cost Type"),
                    "cancel": prop(card_el, "Cancel"),
                    "cancelType": prop(card_el, "Cancel Type"),
                    "wealth": prop(card_el, "Wealth"),
                    "attack": prop(card_el, "Attack"),
                    "parry": prop(card_el, "Parry"),
                    "cannon": prop(card_el, "Cannon"),
                    "sailing": prop(card_el, "Sailing"),
                    "adventuring": prop(card_el, "Adventuring"),
                    "influence": prop(card_el, "Influence"),
                    "swashbuckling": prop(card_el, "Swashbuckling"),
                    "crewMax": prop(card_el, "Crew Max"),
                    "moveCost": prop(card_el, "Move Cost"),
                    "rarity": prop(card_el, "Rarity"),
                    "text": prop(card_el, "Text"),
                    "loadGroupId": LOAD_BY_TYPE.get(card_type, "playerNDeck"),
                }
            )
    return cards, errors, copies


def copy_images(copies: list[tuple[str, str, Path]]) -> None:
    IMAGES_ROOT.mkdir(parents=True, exist_ok=True)
    rows = ["relativePath\tset\tname\toctgnId\toctgnSource"]
    for rel, meta, source in copies:
        dest = IMAGES_ROOT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        rows.append(f"{rel}\t{meta}\t{source}")
    MANIFEST_OUT.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_OUT.write_text("\n".join(rows) + "\n", encoding="utf-8")


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


def pile(group_id: str, left: float, top: float, width: float = 8.0, height: float = 11.0) -> dict:
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
            "deckGroupId": f"{pid}Deck",
            "discardGroupId": f"{pid}Discard",
        }
        if extra:
            data.update(extra)
        return data

    return {
        f"{pid}Deck": {
            "groupType": "deck",
            "label": f"Player {n} Deck",
            "tableLabel": "Deck",
            "onCardEnter": enter(),
        },
        f"{pid}Discard": {
            "groupType": "discard",
            "label": f"Player {n} Discard",
            "tableLabel": "Discard",
            "onCardEnter": enter(),
        },
        f"{pid}Sunk": {
            "groupType": "sunk",
            "label": f"Player {n} Sunk",
            "tableLabel": "Sunk",
            "onCardEnter": enter(),
        },
        f"{pid}Hand": {
            "groupType": "hand",
            "label": f"Player {n} Hand",
            "tableLabel": "Hand",
            "onCardEnter": enter(),
        },
        f"{pid}Crew": {
            "groupType": "inPlay",
            "label": f"Player {n} Crew",
            "tableLabel": "Crew",
            "canHaveAttachments": True,
            "onCardEnter": enter({"inPlay": True}),
        },
        f"{pid}Ship": {
            "groupType": "inPlay",
            "label": f"Player {n} Ship",
            "tableLabel": "Ship",
            "canHaveAttachments": True,
            "onCardEnter": enter({"inPlay": True}),
        },
        f"{pid}Captain": {
            "groupType": "inPlay",
            "label": f"Player {n} Captain",
            "tableLabel": "Captain",
            "canHaveAttachments": True,
            "onCardEnter": enter({"inPlay": True}),
        },
        f"{pid}Adventures": {
            "groupType": "inPlay",
            "label": f"Player {n} Adventures",
            "tableLabel": "Adv",
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
    for _card_id, group_id, label in SEA_ORDER:
        groups[group_id] = {
            "groupType": "sea",
            "label": label,
            "tableLabel": label,
            "canHaveAttachments": True,
            "onCardEnter": {"controller": "shared", "inPlay": True},
        }
    groups.update(player_groups("player1", "1"))
    groups.update(player_groups("player2", "2"))
    return {"groups": groups}


def make_layouts() -> dict:
    play_w = 81.0
    pile_w = 8.0
    col1, col2 = 82.0, 91.0
    hand_w = 64.0
    sea_w = play_w / 5.0
    regions = {
        "playerN+1Hand": row_region("playerN+1Hand", 0, 0, play_w, 7, "rgba(0, 0, 0, 0.32)", "fan", True),
        "playerN+1Adventures": row_region("playerN+1Adventures", 0, 7, 51, 9, "rgba(70, 50, 20, 0.36)", "row", True),
        "playerN+1Ship": row_region("playerN+1Ship", 51, 7, 15, 9, "rgba(30, 50, 70, 0.40)", "row", True),
        "playerN+1Captain": row_region("playerN+1Captain", 66, 7, 15, 9, "rgba(70, 40, 30, 0.40)"),
        "playerN+1Crew": row_region("playerN+1Crew", 0, 16, play_w, 16, "rgba(30, 55, 45, 0.36)"),
        "playerNCrew": row_region("playerNCrew", 0, 44, play_w, 16, "rgba(30, 55, 45, 0.36)"),
        "playerNAdventures": row_region("playerNAdventures", 0, 60, 51, 9, "rgba(70, 50, 20, 0.36)", "row", True),
        "playerNShip": row_region("playerNShip", 51, 60, 15, 9, "rgba(30, 50, 70, 0.40)", "row", True),
        "playerNCaptain": row_region("playerNCaptain", 66, 60, 15, 9, "rgba(70, 40, 30, 0.40)"),
        "playerNHand": row_region("playerNHand", 0, 69, hand_w, 31, "rgba(0, 0, 0, 0.32)", "fan", True),
        "playerN+1Deck": pile("playerN+1Deck", col1, 7.0, pile_w),
        "playerN+1Discard": pile("playerN+1Discard", col2, 7.0, pile_w),
        "playerN+1Sunk": pile("playerN+1Sunk", col1, 19.0, pile_w),
        "playerNDeck": pile("playerNDeck", col1, 60.0, pile_w),
        "playerNDiscard": pile("playerNDiscard", col2, 60.0, pile_w),
        "playerNSunk": pile("playerNSunk", col1, 71.5, pile_w),
        "playerNTokens": pile("playerNTokens", col2, 71.5, pile_w),
        "sharedSetAside": row_region(
            "sharedSetAside", col1, 88.0, pile_w * 2 + 1, 12.0, "rgba(0, 0, 0, 0.45)", "fan", True
        ),
    }
    for index, (_card_id, group_id, _label) in enumerate(SEA_ORDER):
        regions[group_id] = row_region(
            group_id, index * sea_w, 32, sea_w, 12, "rgba(20, 45, 80, 0.42)"
        )
    table_buttons = {
        "drawDeck": {
            "actionList": "drawDeck",
            "label": "Draw",
            "left": pct(col1),
            "top": "48%",
            "width": pct(pile_w),
            "height": "4%",
        },
        "shuffleDeck": {
            "actionList": "shuffleDeck",
            "label": "Shuf",
            "left": pct(col2),
            "top": "48%",
            "width": pct(pile_w),
            "height": "4%",
        },
        "untackAll": {
            "actionList": "untackAll",
            "label": "Untack",
            "left": pct(col1),
            "top": "52.5%",
            "width": pct(pile_w),
            "height": "4%",
        },
        "roll1d6": {
            "actionList": "roll1d6",
            "label": "d6",
            "left": pct(col2),
            "top": "52.5%",
            "width": pct(pile_w),
            "height": "4%",
        },
    }
    return {
        "layouts": {
            "default": {
                "cardSize": 9,
                "rowSpacing": 1,
                "chat": {"left": pct(hand_w), "top": "69%", "width": pct(play_w - hand_w), "height": "31%"},
                "regions": regions,
                "tableButtons": table_buttons,
            }
        }
    }


def make_card_types(cards: list[dict[str, str]]) -> dict:
    types = {
        kind: {"width": 0.72, "height": 1.0, "tokens": ["hits", "generic"]}
        for kind in sorted({card["type"] for card in cards})
    }
    return {"cardTypes": types}


def make_card_backs() -> dict:
    return {
        "cardBacks": {
            "default": {
                "width": 0.72,
                "height": 1.0,
                "imageUrl": f"{GAME_FOLDER}/_plugin/7thSea-cardback.jpg",
            }
        }
    }


def make_browse(cards: list[dict[str, str]]) -> dict:
    order = ["Captain", "Ship", "Crew", "Action", "Attachment", "Adventure", "Chantey", "Sea"]
    present = {card["type"] for card in cards}
    filter_values = [kind for kind in order if kind in present]
    extra = sorted(present - set(filter_values))
    return {
        "browse": {
            "filterPropertySideA": "type",
            "filterValuesSideA": filter_values + extra,
            "textPropertiesSideA": ["name", "text", "faction", "set", "cost"],
        }
    }


def make_seas_deck() -> tuple[dict, dict]:
    cards = [
        {"databaseId": card_id, "quantity": 1, "loadGroupId": group_id}
        for card_id, group_id, _label in SEA_ORDER
    ]
    return (
        {"preBuiltDecks": {"theahSeas": {"label": "Theah Seas", "cards": cards}}},
        {"deckMenu": {"subMenus": []}},
    )


def main() -> int:
    cards, errors, copies = load_cards()
    copy_images(copies)
    write_tsv(cards)
    write_json("groups.json", make_groups())
    write_json("layouts.json", make_layouts())
    write_json("cardTypes.json", make_card_types(cards))
    write_json("cardBacks.json", make_card_backs())
    write_json("browse.json", make_browse(cards))
    write_json("imageUrlPrefix.json", {"imageUrlPrefix": {"Default": TOYBOX_PREFIX}})
    prebuilts, menu = make_seas_deck()
    write_json("preBuiltDecks.json", prebuilts)
    write_json("deckMenu.json", menu)
    stamp_lobby_art(JSONS_DIR, GAME_FOLDER)

    types = sorted({card["type"] for card in cards})
    sets = sorted({card["set"] for card in cards})
    print(f"Wrote {len(cards)} cards to {TSV_OUT}")
    print(f"Copied {len(copies)} images to {IMAGES_ROOT / GAME_FOLDER}")
    print(f"Sets ({len(sets)}): {', '.join(sets)}")
    print(f"Types: {', '.join(types)}")
    missing = [err for err in errors if err.startswith("Missing image")]
    other = [err for err in errors if not err.startswith("Missing image")]
    if missing:
        print(f"\n{len(missing)} card(s) using cardback fallback:")
        for err in missing:
            print(f"  - {err}")
    if other:
        print(f"\n{len(other)} issue(s):")
        for err in other[:40]:
            print(f"  - {err}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
