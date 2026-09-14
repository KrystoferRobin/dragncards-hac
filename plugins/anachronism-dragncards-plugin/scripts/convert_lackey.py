#!/usr/bin/env python3
"""Convert the LackeyCCG Anachronism plugin into DragnCards TSV + table JSON."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from image_names import stamp_lobby_art  # noqa: E402

LACKEY_DIR = Path(r"C:\Users\chris\Documents\e-Sword\tests\LackeyCCG\plugins\anachronism")
PLUGIN_DIR = Path(r"C:\Users\chris\Documents\e-Sword\dragncards\anachronism-dragncards-plugin")
CARDDATA = LACKEY_DIR / "sets" / "carddata.txt"
TSV_OUT = PLUGIN_DIR / "tsvs" / "cards.tsv"
JSONS_DIR = PLUGIN_DIR / "jsons"
GAME_FOLDER = "anachronism"

IMAGE_BASE = "http://www.drivehq.com/file/df.aspx/publish/carapippino/anachronism"

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "set",
    "culture",
    "element",
    "traits",
    "initiative",
    "life",
    "speed",
    "experience",
    "damage",
    "setNumbers",
    "text",
    "loadGroupId",
]

INT_FIELDS = ("initiative", "life", "speed", "experience", "damage")

SAMPLE_ARMIES = [
    (
        "achilles",
        "Sample: Achilles",
        [
            ("set1_01-091", "playerNWarrior"),
            ("set1_01-002", "playerNPool"),
            ("set1_01-013", "playerNPool"),
            ("set1_01-004", "playerNPool"),
            ("set1_01-010", "playerNPool"),
        ],
    ),
    (
        "musashi",
        "Sample: Miyamoto Musashi",
        [
            ("set1_01-039", "playerNWarrior"),
            ("set1_01-034", "playerNPool"),
            ("set1_01-035", "playerNPool"),
            ("set1_01-024", "playerNPool"),
            ("set1_01-029", "playerNPool"),
        ],
    ),
    (
        "caesar",
        "Sample: Julius Caesar",
        [
            ("set1_01-069", "playerNWarrior"),
            ("set1_01-070", "playerNPool"),
            ("set1_01-071", "playerNPool"),
            ("set1_01-084", "playerNPool"),
            ("set1_01-085", "playerNPool"),
        ],
    ),
]


def sanitize(value: str) -> str:
    return (
        (value or "")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("\t", " ")
        .strip()
    )


def as_int_string(value: str) -> str:
    text = sanitize(value)
    if text == "":
        return "0"
    try:
        return str(int(text))
    except ValueError:
        return "0"


def card_type(traits: str) -> str:
    head = sanitize(traits).split("/")[0].strip().lower()
    return {
        "warrior": "Warrior",
        "inspiration": "Inspiration",
        "armor": "Armor",
        "weapon": "Weapon",
        "special": "Special",
    }.get(head, "")


def load_cards() -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    seen: set[str] = set()
    with CARDDATA.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            name = sanitize(row.get("Name", ""))
            set_name = sanitize(row.get("Set", ""))
            image_file = sanitize(row.get("ImageFile", ""))
            traits = sanitize(row.get("Traits", ""))
            if not name or not set_name or not image_file:
                errors.append(f"Skipping incomplete row: {name!r} {set_name!r} {image_file!r}")
                continue
            kind = card_type(traits)
            if not kind:
                errors.append(f"Unknown traits {traits!r} for {name}")
                continue
            database_id = f"{set_name}_{image_file}"
            if database_id in seen:
                errors.append(f"Duplicate databaseId {database_id}")
                continue
            seen.add(database_id)
            cards.append(
                {
                    "databaseId": database_id,
                    "name": name,
                    "imageUrl": f"{IMAGE_BASE}/{image_file}.jpg",
                    "cardBack": "default",
                    "type": kind,
                    "set": set_name,
                    "culture": sanitize(row.get("Culture", "")),
                    "element": sanitize(row.get("Element", "")),
                    "traits": traits,
                    "initiative": as_int_string(row.get("Initiative", "")),
                    "life": as_int_string(row.get("Life", "")),
                    "speed": as_int_string(row.get("Speed", "")),
                    "experience": as_int_string(row.get("Experience", "")),
                    "damage": as_int_string(row.get("Damage", "")),
                    "setNumbers": sanitize(row.get("Set Numbers", "")),
                    "text": sanitize(row.get("Text", "")),
                    "loadGroupId": "playerNWarrior" if kind == "Warrior" else "playerNPool",
                }
            )
    return cards, errors


def write_tsv(cards: list[dict[str, str]]) -> None:
    TSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = ["\t".join(TSV_COLUMNS)]
    for card in cards:
        lines.append("\t".join(sanitize(card.get(col, "")) for col in TSV_COLUMNS))
    TSV_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(name: str, payload: dict) -> None:
    JSONS_DIR.mkdir(parents=True, exist_ok=True)
    path = JSONS_DIR / name
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def make_groups() -> dict:
    groups: dict[str, dict] = {
        "sharedSetAside": {
            "groupType": "aside",
            "label": "Set Aside",
            "tableLabel": "Set Aside",
            "onCardEnter": {"controller": "shared"},
        }
    }
    for row in range(1, 5):
        for col in range(1, 5):
            group_id = f"sharedArenaR{row}C{col}"
            groups[group_id] = {
                "groupType": "arena",
                "label": f"Arena {row},{col}",
                "tableLabel": f"{row},{col}",
                "canHaveAttachments": False,
                "onCardEnter": {
                    "controller": "shared",
                    "inPlay": True,
                    "currentSide": "A",
                },
            }
    for player in (1, 2):
        pid = f"player{player}"
        groups[f"{pid}Warrior"] = {
            "groupType": "pile",
            "label": f"Player {player} Warrior",
            "tableLabel": "Warrior",
            "onCardEnter": {
                "controller": pid,
                "currentSide": "A",
                "inPlay": False,
                "discardGroupId": f"{pid}Discard",
            },
        }
        groups[f"{pid}Pool"] = {
            "groupType": "pool",
            "label": f"Player {player} Support Pool",
            "tableLabel": "Pool",
            "canHaveAttachments": True,
            "onCardEnter": {
                "controller": pid,
                "currentSide": "B",
                "inPlay": True,
                "discardGroupId": f"{pid}Discard",
            },
        }
        groups[f"{pid}Discard"] = {
            "groupType": "discard",
            "label": f"Player {player} Discard",
            "tableLabel": "Discard",
            "onCardEnter": {
                "controller": pid,
                "deckGroupId": f"{pid}Pool",
                "discardGroupId": f"{pid}Discard",
            },
        }
    return {"groups": groups}


def region_style(background: str, border: str) -> dict:
    return {
        "background": background,
        "border": border,
        "boxSizing": "border-box",
    }


def make_layouts() -> dict:
    grid_left = 20.0
    grid_top = 16.0
    cell_w = 11.0
    cell_h = 13.5
    zone_border = "1px solid rgba(210, 210, 210, 0.55)"
    arena_border = "1px solid rgba(230, 210, 150, 0.95)"
    regions = {
        "playerN+1Pool": {
            "groupId": "playerN+1Pool",
            "type": "row",
            "direction": "horizontal",
            "left": "20%",
            "top": "1%",
            "width": "44%",
            "height": "14%",
            "style": region_style("rgba(80, 20, 20, 0.28)", zone_border),
        },
        "playerNPool": {
            "groupId": "playerNPool",
            "type": "row",
            "direction": "horizontal",
            "left": "20%",
            "top": "71%",
            "width": "44%",
            "height": "16%",
            "style": region_style("rgba(20, 40, 80, 0.32)", zone_border),
        },
        "playerN+1Warrior": {
            "groupId": "playerN+1Warrior",
            "type": "pile",
            "direction": "horizontal",
            "left": "66%",
            "top": "16%",
            "width": "8%",
            "height": "16%",
            "style": region_style("rgba(0, 0, 0, 0.35)", zone_border),
        },
        "playerN+1Discard": {
            "groupId": "playerN+1Discard",
            "type": "pile",
            "direction": "horizontal",
            "left": "66%",
            "top": "33%",
            "width": "8%",
            "height": "16%",
            "style": region_style("rgba(0, 0, 0, 0.35)", zone_border),
        },
        "playerNWarrior": {
            "groupId": "playerNWarrior",
            "type": "pile",
            "direction": "horizontal",
            "left": "66%",
            "top": "50%",
            "width": "8%",
            "height": "16%",
            "style": region_style("rgba(0, 0, 0, 0.35)", zone_border),
        },
        "playerNDiscard": {
            "groupId": "playerNDiscard",
            "type": "pile",
            "direction": "horizontal",
            "left": "66%",
            "top": "67%",
            "width": "8%",
            "height": "16%",
            "style": region_style("rgba(0, 0, 0, 0.35)", zone_border),
        },
        "sideRegion": {
            "groupId": "sharedSetAside",
            "type": "fan",
            "direction": "vertical",
            "left": "0%",
            "top": "16%",
            "width": "9%",
            "height": "54%",
            "style": region_style("rgba(0, 0, 0, 0.45)", zone_border),
            "visible": False,
        },
    }
    # Row 4 is the top of the screen (player 2 start); row 1 is the bottom (player 1 start).
    for row in range(1, 5):
        for col in range(1, 5):
            screen_row = 4 - row
            left = grid_left + (col - 1) * cell_w
            top = grid_top + screen_row * cell_h
            group_id = f"sharedArenaR{row}C{col}"
            fill = "rgba(70, 62, 32, 0.48)" if (row + col) % 2 == 0 else "rgba(28, 26, 16, 0.58)"
            regions[group_id] = {
                "groupId": group_id,
                "type": "pile",
                "direction": "horizontal",
                "left": f"{left:.1f}%",
                "top": f"{top:.1f}%",
                "width": f"{cell_w:.1f}%",
                "height": f"{cell_h:.1f}%",
                "hideTitle": True,
                "style": region_style(fill, arena_border),
            }

    text_boxes = {
        "p2Start": {
            "label": "P2 start (face South)",
            "left": "20%",
            "top": "15%",
            "width": "44%",
            "height": "2%",
        },
        "p1Start": {
            "label": "P1 start (face North)",
            "left": "20%",
            "top": "69.5%",
            "width": "44%",
            "height": "2%",
        },
    }

    table_buttons = {
        "rollAttack": {
            "actionList": "rollAttack",
            "label": "2d6 Atk",
            "left": "76%",
            "top": "16%",
            "width": "10%",
            "height": "4%",
        },
        "rollDefense": {
            "actionList": "rollDefense",
            "label": "2d6 Def",
            "left": "87%",
            "top": "16%",
            "width": "10%",
            "height": "4%",
        },
        "roll1d6": {
            "actionList": "roll1d6",
            "label": "1d6",
            "left": "76%",
            "top": "21%",
            "width": "10%",
            "height": "4%",
        },
        "roll3d6": {
            "actionList": "roll3d6",
            "label": "3d6",
            "left": "87%",
            "top": "21%",
            "width": "10%",
            "height": "4%",
        },
        "lifeUp": {
            "actionList": "increaseLife",
            "label": "Life +",
            "left": "76%",
            "top": "26%",
            "width": "10%",
            "height": "4%",
        },
        "lifeDown": {
            "actionList": "decreaseLife",
            "label": "Life -",
            "left": "87%",
            "top": "26%",
            "width": "10%",
            "height": "4%",
        },
        "sharedSetAside": {
            "actionList": ["TOGGLE_SIDE_REGION", "sharedSetAside"],
            "label": "SA",
            "left": "97%",
            "top": "68%",
            "width": "2%",
            "height": "3%",
        },
    }

    return {
        "layouts": {
            "default": {
                "cardSize": 10,
                "rowSpacing": 1,
                "chat": {"left": "76%", "top": "72%", "width": "23%", "height": "27%"},
                "regions": regions,
                "textBoxes": text_boxes,
                "tableButtons": table_buttons,
            }
        }
    }


def make_prebuilts(known_ids: set[str]) -> tuple[dict, dict, list[str]]:
    errors: list[str] = []
    decks: dict[str, dict] = {}
    for deck_id, label, cards in SAMPLE_ARMIES:
        load_cards = []
        for database_id, load_group in cards:
            if database_id not in known_ids:
                errors.append(f"{deck_id}: unknown card {database_id}")
                continue
            load_cards.append(
                {"databaseId": database_id, "quantity": 1, "loadGroupId": load_group}
            )
        decks[deck_id] = {"label": label, "cards": load_cards}
    menu = {
        "subMenus": [
            {
                "label": "Sample Armies",
                "deckLists": [
                    {"label": label, "deckListId": deck_id}
                    for deck_id, label, _cards in SAMPLE_ARMIES
                    if deck_id in decks
                ],
            }
        ]
    }
    return {"preBuiltDecks": decks}, {"deckMenu": menu}, errors


def main() -> int:
    cards, errors = load_cards()
    write_tsv(cards)
    write_json("groups.json", make_groups())
    write_json("layouts.json", make_layouts())
    prebuilts, menu, deck_errors = make_prebuilts({card["databaseId"] for card in cards})
    errors.extend(deck_errors)
    write_json("preBuiltDecks.json", prebuilts)
    write_json("deckMenu.json", menu)
    stamp_lobby_art(JSONS_DIR, GAME_FOLDER)

    types = sorted({card["type"] for card in cards})
    sets = sorted({card["set"] for card in cards})
    print(f"Wrote {len(cards)} cards to {TSV_OUT}")
    print(f"Sets: {', '.join(sets)}")
    print(f"Types: {', '.join(types)}")
    if errors:
        print(f"\n{len(errors)} issue(s):")
        for err in errors:
            print(f"  - {err}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
