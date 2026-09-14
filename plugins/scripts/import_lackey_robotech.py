#!/usr/bin/env python3
"""Build a DragnCards Robotech CCG plugin from the LackeyCCG plugin.

  python plugins/scripts/import_lackey_robotech.py
  python plugins/scripts/collect_hosted_images.py robotech-ccg
"""

from __future__ import annotations

import json
import re
import struct
import xml.etree.ElementTree as ET
import zlib
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))
from image_names import TOYBOX_PREFIX, plugin_art_rel, stamp_lobby_art, toybox_url  # noqa: E402

LACKEY = Path("/Volumes/Expand/MegaNZ/LackeyCCG/plugins/RobotechCCG")
OUT = ROOT / "robotech-ccg"
GAME_FOLDER = "robotech-ccg"
GAME_PASCAL = "RobotechCcg"

CARD_BACK = "https://raw.githubusercontent.com/wishmstr/RobotechCCG/main/sets/setimages/general/cardback.png"

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "subtype",
    "battleType",
    "keyword",
    "protoCost",
    "basic",
    "solo",
    "transform",
    "packName",
    "set",
    "loadGroupId",
]

MOVE_GROUPS = [
    "playerNHand",
    "playerNDeck",
    "playerNDiscard",
    "playerNPlay",
    "playerN+1Play",
    "sharedLocations",
    "sharedSetAside",
]


def dump_json(path: Path, payload: dict | list) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sanitize(value: str) -> str:
    return (value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()


def write_color_png(path: Path, rgb: tuple[int, int, int], size: int = 48) -> None:
    red, green, blue = rgb
    raw = b"".join(b"\x00" + bytes([red, green, blue]) * size for _ in range(size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def load_image_urls(path: Path) -> dict[str, str]:
    urls: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("CardImageURLs"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        rel = parts[0].strip().replace("\\", "/")
        url = parts[1].strip().replace("/sets/rulescards/", "/sets/setimages/rulescards/")
        if not rel or not url:
            continue
        lower = rel.lower()
        urls[lower] = url
        filename = lower.split("/")[-1]
        urls[filename] = url
        urls[filename.rsplit(".", 1)[0]] = url
    return urls


def lookup_image(urls: dict[str, str], set_name: str, image_file: str) -> str:
    for key in (
        f"{set_name}/{image_file}".lower(),
        image_file.lower(),
        image_file.lower().rsplit(".", 1)[0],
    ):
        if key in urls:
            return urls[key]
    return ""


def pack_name(set_name: str, image_file: str) -> str:
    stem = image_file.rsplit(".", 1)[0]
    if set_name.lower() == "rulescards" or stem.startswith("000"):
        return "Rules"
    if stem.startswith("MS"):
        return "Macross Saga"
    if stem.startswith("NG"):
        return "New Generation"
    if stem.startswith("RM"):
        return "Robotech Masters"
    return set_name.title()


def load_group(card_type: str) -> str:
    if card_type == "Rules":
        return "sharedSetAside"
    if card_type == "Location":
        return "sharedLocations"
    return "playerNDeck"


def load_cards(carddata: Path, urls: dict[str, str]) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    seen: set[str] = set()
    lines = carddata.read_text(encoding="utf-8", errors="replace").splitlines()
    header = [h.strip() for h in lines[0].split("\t")]
    expected = [
        "Name",
        "set",
        "ImageFile",
        "ProtoCost",
        "CardType",
        "CardType2",
        "BattleType",
        "Keyword1",
        "Basic",
        "Solo",
        "Transform",
    ]
    if [h.lower() for h in header[:11]] != [h.lower() for h in expected]:
        errors.append(f"Unexpected carddata header: {header}")

    for line_no, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        cols = line.split("\t")
        while len(cols) < 11:
            cols.append("")
        name, set_name, image_file, proto, card_type, subtype, battle, keyword, basic, solo, transform = [
            sanitize(c) for c in cols[:11]
        ]
        if not name or not image_file:
            errors.append(f"Line {line_no}: missing name or ImageFile")
            continue
        database_id = f"{set_name}_{image_file}"
        if database_id in seen:
            errors.append(f"Duplicate {database_id} at line {line_no}")
            continue
        seen.add(database_id)
        if not card_type:
            card_type = "Rules"
        image_url = lookup_image(urls, set_name, image_file)
        if not image_url:
            errors.append(f"Missing image URL for {database_id}")
        cards.append(
            {
                "databaseId": database_id,
                "name": name,
                "imageUrl": image_url,
                "cardBack": "default",
                "type": card_type,
                "subtype": subtype,
                "battleType": battle,
                "keyword": keyword,
                "protoCost": proto,
                "basic": basic,
                "solo": solo,
                "transform": transform,
                "packName": pack_name(set_name, image_file),
                "set": set_name,
                "loadGroupId": load_group(card_type),
            }
        )
    return cards, errors


def write_tsv(cards: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["\t".join(TSV_COLUMNS)]
    rows.extend("\t".join(sanitize(card.get(col, "")) for col in TSV_COLUMNS) for card in cards)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "deck"


def parse_dek(path: Path) -> Counter:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        root = ET.fromstring(f"<root>{text}</root>")
    counts: Counter = Counter()
    for card in root.findall(".//superzone/card"):
        name_el = card.find("name")
        set_el = card.find("set")
        if name_el is None or set_el is None:
            continue
        image_id = (name_el.attrib.get("id") or "").strip()
        set_name = (set_el.text or "").strip()
        if image_id and set_name:
            counts[f"{set_name}_{image_id}"] += 1
    return counts


def convert_decks(cards: list[dict[str, str]]) -> tuple[dict, dict, list[str]]:
    known = {card["databaseId"] for card in cards}
    load_by_id = {card["databaseId"]: card["loadGroupId"] for card in cards}
    errors: list[str] = []
    prebuilt: OrderedDict[str, dict] = OrderedDict()
    menu: list[dict] = []
    for dek in sorted((LACKEY / "decks").glob("*.dek")):
        label = dek.stem.replace("_", " ")
        deck_id = slug(label)
        counts = parse_dek(dek)
        entries = []
        for database_id, quantity in counts.items():
            if database_id not in known:
                errors.append(f"{dek.name}: unknown card {database_id}")
                continue
            group = load_by_id[database_id]
            if group == "sharedSetAside":
                group = "sharedSetAside"
            elif group == "sharedLocations":
                group = "sharedLocations"
            else:
                group = "playerNDeck"
            entries.append({"databaseId": database_id, "quantity": quantity, "loadGroupId": group})
        prebuilt[deck_id] = {"label": label, "cards": entries}
        menu.append({"deckListId": deck_id, "label": label})
    return (
        {"preBuiltDecks": dict(prebuilt)},
        {"deckMenu": {"subMenus": [{"label": "Starter Decks", "deckLists": menu}]}},
        errors,
    )


def player_group(player: str, kind: str, group_type: str, table_label: str, **extra) -> tuple[str, dict]:
    key = f"{player}{kind}"
    payload = {
        "groupType": group_type,
        "label": f"Player {player[-1]} {table_label}" if player.startswith("player") else table_label,
        "tableLabel": table_label,
        "onCardEnter": {
            "controller": player,
            "deckGroupId": f"{player}Deck",
            "discardGroupId": f"{player}Discard",
        },
    }
    payload.update(extra)
    return key, payload


def build_groups() -> dict:
    groups: dict[str, dict] = {
        "sharedSetAside": {
            "groupType": "aside",
            "label": "Set Aside",
            "tableLabel": "Set Aside",
            "onCardEnter": {"controller": "shared"},
        },
        "sharedLocations": {
            "groupType": "inPlay",
            "label": "Locations",
            "tableLabel": "Locations",
            "canHaveAttachments": True,
            "onCardEnter": {"controller": "shared", "inPlay": True},
        },
    }
    for player in ("player1", "player2"):
        for kind, group_type, label, extra in (
            ("Deck", "deck", "Deck", {}),
            ("Discard", "discard", "Discard", {}),
            ("Hand", "hand", "Hand", {}),
            ("Play", "inPlay", "Play", {"canHaveAttachments": True}),
        ):
            key, payload = player_group(player, kind, group_type, label, **extra)
            groups[key] = payload
    return {"groups": groups}


def region(group_id: str, rtype: str, left: str, top: str, width: str, height: str, **extra) -> dict:
    payload = {
        "groupId": group_id,
        "type": rtype,
        "direction": "free" if rtype == "free" else "horizontal",
        "left": left,
        "top": top,
        "width": width,
        "height": height,
        "style": {
            "background": "rgba(0, 0, 0, 0.22)",
            "border": "1px solid rgba(50, 50, 50, 0.4)",
            "boxSizing": "border-box",
        },
    }
    payload.update(extra)
    return payload


def build_layouts() -> dict:
    return {
        "layouts": {
            "default": {
                "cardSize": 10,
                "rowSpacing": 2,
                "chat": {"left": "76%", "top": "78%", "width": "23%", "height": "21%"},
                "regions": {
                    "playerN+1Hand": region("playerN+1Hand", "fan", "0%", "0%", "75%", "10%", disableDroppableAttachments=True),
                    "playerN+1Play": region("playerN+1Play", "free", "0%", "10%", "75%", "26%"),
                    "sharedLocations": region("sharedLocations", "row", "0%", "36%", "75%", "10%"),
                    "playerNPlay": region("playerNPlay", "free", "0%", "46%", "75%", "26%"),
                    "playerNHand": region("playerNHand", "fan", "0%", "82%", "58%", "17%", disableDroppableAttachments=True),
                    "playerN+1Deck": region("playerN+1Deck", "pile", "76%", "10%", "11%", "16%"),
                    "playerN+1Discard": region("playerN+1Discard", "pile", "88%", "10%", "11%", "16%"),
                    "sharedSetAside": region("sharedSetAside", "pile", "76%", "27%", "23%", "14%"),
                    "playerNDeck": region("playerNDeck", "pile", "76%", "58%", "11%", "16%"),
                    "playerNDiscard": region("playerNDiscard", "pile", "88%", "58%", "11%", "16%"),
                },
                "tableButtons": {
                    "drawDeck": {"actionList": "drawDeck", "label": "Draw", "left": "76%", "top": "46%", "width": "11%", "height": "3.2%"},
                    "readyAll": {"actionList": "readyAll", "label": "Ready All", "left": "88%", "top": "46%", "width": "11%", "height": "3.2%"},
                    "flipCoin": {"actionList": "flipCoin", "label": "Coin", "left": "76%", "top": "50%", "width": "11%", "height": "3.2%"},
                    "increaseBattle": {"actionList": "increaseBattle", "label": "BP +1", "left": "88%", "top": "50%", "width": "11%", "height": "3.2%"},
                },
            }
        }
    }


def write_plugin_jsons(cards: list[dict[str, str]], decks: dict, menu: dict) -> None:
    jsons = OUT / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    types = sorted({card["type"] for card in cards})
    dump_json(jsons / "main.json", {
        "pluginName": "Robotech CCG",
        "author": "Lackey / wishmstr",
        "tutorialUrl": "https://github.com/wishmstr/RobotechCCG",
        "announcements": [
            "Tabletop plugin from the Lackey Robotech CCG set. No rules engine — Draw, Ready/Spend, Battle Points, and counters are shortcuts.",
            "D = draw. R = ready all. T = spend (rotate 90). K = ready one. X = discard. 1/2 = green/red counters.",
        ],
        "loadPreBuiltOnNewGame": False,
    })
    stamp_lobby_art(jsons, GAME_FOLDER)
    dump_json(jsons / "announcements.json", {"announcements": [
        "Robotech CCG tabletop: load a starter, draw, and play. Rules are reminders, not enforced.",
    ]})
    dump_json(jsons / "imageUrlPrefix.json", {"imageUrlPrefix": {"Default": TOYBOX_PREFIX}})
    dump_json(jsons / "cardBacks.json", {"cardBacks": {"default": {"width": 0.72, "height": 1.0, "imageUrl": CARD_BACK}}})
    dump_json(jsons / "cardTypes.json", {"cardTypes": {name: {"width": 0.72, "height": 1.0, "tokens": ["green", "red"]} for name in types}})
    dump_json(jsons / "groups.json", build_groups())
    dump_json(jsons / "layouts.json", build_layouts())
    dump_json(jsons / "groupTypes.json", {"groupTypes": {
        "deck": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": True, "onCardEnter": {"currentSide": "B", "inPlay": False, "rotation": 0}},
        "discard": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
        "hand": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
        "inPlay": {"canHaveAttachments": True, "canHaveTokens": True, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": True, "rotation": 0}},
        "aside": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
    }})
    dump_json(jsons / "playerCountMenu.json", {"playerCountMenu": [{"label": "2", "numPlayers": 2, "layoutId": "default"}]})
    dump_json(jsons / "phases.json", {
        "phases": {
            "regroup": {"label": "Regroup", "height": "25%"},
            "proto": {"label": "Proto", "height": "25%"},
            "mobilize": {"label": "Mobilize", "height": "25%"},
            "battle": {"label": "Battle", "height": "25%"},
        },
        "phaseOrder": ["regroup", "proto", "mobilize", "battle"],
    })
    dump_json(jsons / "steps.json", {
        "steps": {
            "regroupStep": {"phaseId": "regroup", "label": "Regroup"},
            "protoStep": {"phaseId": "proto", "label": "Proto"},
            "mobilizeStep": {"phaseId": "mobilize", "label": "Mobilize"},
            "battleStep": {"phaseId": "battle", "label": "Battle"},
        },
        "stepOrder": ["regroupStep", "protoStep", "mobilizeStep", "battleStep"],
    })
    dump_json(jsons / "playerProperties.json", {"playerProperties": {
        "battlePoints": {"label": "Battle Points", "type": "integer", "default": 0, "min": 0},
    }})
    dump_json(jsons / "gameProperties.json", {"gameProperties": {}})
    dump_json(jsons / "topBarCounters.json", {"topBarCounters": {
        "shared": [{"label": "Round", "imageUrl": "", "gameProperty": "roundNumber"}],
        "player": [{"label": "BP", "imageUrl": "", "playerProperty": "battlePoints"}],
    }})
    green_rel = plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "token-green", ".png")
    red_rel = plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "token-red", ".png")
    dump_json(jsons / "tokens.json", {"tokens": {
        "green": {"label": "Green", "left": "72%", "top": "4%", "width": "4vh", "height": "4vh", "imageUrl": toybox_url(green_rel), "canBeNegative": True},
        "red": {"label": "Red", "left": "50%", "top": "4%", "width": "4vh", "height": "4vh", "imageUrl": toybox_url(red_rel), "canBeNegative": True},
    }})
    dump_json(jsons / "functions.json", {"functions": {
        "DISCARD": {"args": ["$CARD_ID"], "code": [
            ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
            ["COND", ["EQUAL", "$CARD.discardGroupId", None],
             ["LOG", "{{$ALIAS_N}} failed to discard {{$CARD.currentFace.name}} because it has no discard pile."],
             ["TRUE"], [["LOG", "{{$ALIAS_N}} discarded {{$CARD.sides.A.name}}."], ["MOVE_CARD", "$CARD.id", "$CARD.discardGroupId", 0]]],
        ]},
        "FLIP": {"args": ["$CARD_ID"], "code": [
            ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
            ["COND", ["EQUAL", "$CARD.currentSide", "A"],
             [["LOG", "{{$ALIAS_N}} flipped {{$CARD.currentFace.name}} facedown."], ["SET", "/cardById/$CARD.id/currentSide", "B"]],
             ["TRUE"], [["SET", "/cardById/$CARD.id/currentSide", "A"], ["LOG", "{{$ALIAS_N}} flipped {{$CARD.currentFace.name}} faceup."]]],
        ]},
        "DETACH": {"args": ["$CARD_ID"], "code": [
            ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
            ["COND", ["GREATER_THAN", "$CARD.cardIndex", 0],
             [["MOVE_CARD", "$CARD.id", "$CARD.groupId", ["ADD", "$CARD.stackIndex", 1]], ["LOG", "{{$ALIAS_N}} detached {{$CARD.currentFace.name}}."]]],
        ]},
        "SHUFFLE_INTO_DECK": {"args": ["$CARD_ID"], "code": [
            ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
            ["VAR", "$GROUP_ID", "$CARD.deckGroupId"],
            ["COND", ["EQUAL", "$GROUP_ID", None],
             ["LOG", "{{$ALIAS_N}} failed to shuffle {{$CARD.currentFace.name}} into a deck."],
             ["TRUE"], [["MOVE_CARD", "$CARD.id", "$CARD.deckGroupId", 0], ["SHUFFLE_GROUP", "$GROUP_ID"],
                        ["LOG", "{{$ALIAS_N}} shuffled {{$CARD.currentFace.name}} into {{$GAME.groupById.$GROUP_ID.label}}."]]],
        ]},
    }})
    dump_json(jsons / "actionLists.json", {"actionLists": {
        "drawDeck": [[
            "COND",
            ["GROUP_EMPTY", "{{$PLAYER_N}}Deck"],
            ["LOG", "{{$ALIAS_N}} tried to draw from an empty deck."],
            ["TRUE"],
            [
                ["MOVE_STACKS", "{{$PLAYER_N}}Deck", "{{$PLAYER_N}}Hand", 1, "bottom"],
                ["LOG", "{{$ALIAS_N}} drew a card."],
            ],
        ]],
        "shuffleDeck": [["SHUFFLE_GROUP", "{{$PLAYER_N}}Deck"], ["LOG", "{{$ALIAS_N}} shuffled their deck."]],
        "readyAll": [[
            "FOR_EACH_KEY_VAL", "$CARD_ID", "$CARD", "$GAME.cardById",
            ["COND", ["EQUAL", "$CARD.controller", "$PLAYER_N"], ["SET", "/cardById/{{$CARD_ID}}/rotation", 0]],
        ], ["LOG", "{{$ALIAS_N}} readied all their cards."]],
        "spendCard": [["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 90], ["LOG", "{{$ALIAS_N}} spent {{$ACTIVE_FACE.name}}."]],
        "readyCard": [["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 0], ["LOG", "{{$ALIAS_N}} readied {{$ACTIVE_FACE.name}}."]],
        "flipCoin": [["VAR", "$FLIP", ["RANDOM_INT", 0, 1]], [
            "COND",
            ["EQUAL", "$FLIP", 0],
            ["LOG", "{{$ALIAS_N}} flipped a coin: Heads."],
            ["TRUE"],
            ["LOG", "{{$ALIAS_N}} flipped a coin: Tails."],
        ]],
        "increaseBattle": [["INCREASE_VAL", "/playerData/$PLAYER_N/battlePoints", 1], ["LOG", "{{$ALIAS_N}} gained 1 Battle Point."]],
        "decreaseBattle": [[
            "COND",
            ["GREATER_THAN", "$GAME.playerData.$PLAYER_N.battlePoints", 0],
            [
                ["DECREASE_VAL", "/playerData/$PLAYER_N/battlePoints", 1],
                ["LOG", "{{$ALIAS_N}} spent 1 Battle Point."],
            ],
            ["TRUE"],
            ["LOG", "{{$ALIAS_N}} has no Battle Points to spend."],
        ]],
        "flipCard": [["FLIP", "$ACTIVE_CARD_ID"]],
        "discardCard": [["DISCARD", "$ACTIVE_CARD_ID"]],
        "detachCard": [["DETACH", "$ACTIVE_CARD_ID"]],
        "shuffleIntoDeck": [["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"]],
        "mulligan": [["MOVE_STACKS", "{{$PLAYER_N}}Hand", "{{$PLAYER_N}}Deck", 99, "bottom"], ["SHUFFLE_GROUP", "{{$PLAYER_N}}Deck"],
                      ["LOG", "{{$ALIAS_N}} mulliganed (hand to bottom of deck, shuffle)."]],
    }})
    dump_json(jsons / "hotkeys.json", {"hotkeys": {
        "game": [
            {"key": "D", "actionList": "drawDeck", "label": "Draw"},
            {"key": "S", "actionList": "shuffleDeck", "label": "Shuffle deck"},
            {"key": "R", "actionList": "readyAll", "label": "Ready all"},
            {"key": "I", "actionList": "flipCoin", "label": "Flip a coin"},
            {"key": "B", "actionList": "increaseBattle", "label": "Battle Point +1"},
            {"key": "N", "actionList": "decreaseBattle", "label": "Battle Point -1"},
            {"key": "M", "actionList": "mulligan", "label": "Mulligan"},
        ],
        "card": [
            {"key": "T", "actionList": "spendCard", "label": "Spend"},
            {"key": "K", "actionList": "readyCard", "label": "Ready"},
            {"key": "F", "actionList": ["FLIP", "$ACTIVE_CARD_ID"], "label": "Flip"},
            {"key": "X", "actionList": ["DISCARD", "$ACTIVE_CARD_ID"], "label": "Discard"},
            {"key": "A", "actionList": ["DETACH", "$ACTIVE_CARD_ID"], "label": "Detach"},
            {"key": "H", "actionList": ["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"], "label": "Shuffle into deck"},
        ],
        "token": [
            {"key": "1", "tokenType": "green", "label": "Green counter"},
            {"key": "2", "tokenType": "red", "label": "Red counter"},
        ],
    }})
    dump_json(jsons / "pluginMenu.json", {"pluginMenu": {"options": [
        {"label": "Draw", "actionList": "drawDeck"},
        {"label": "Shuffle deck", "actionList": "shuffleDeck"},
        {"label": "Ready all", "actionList": "readyAll"},
        {"label": "Flip a coin", "actionList": "flipCoin"},
        {"label": "Battle Point +1", "actionList": "increaseBattle"},
        {"label": "Battle Point -1", "actionList": "decreaseBattle"},
        {"label": "Mulligan", "actionList": "mulligan"},
    ]}})
    dump_json(jsons / "cardMenu.json", {"cardMenu": {"moveToGroupIds": MOVE_GROUPS, "options": [
        {"label": "Spend", "actionList": "spendCard"},
        {"label": "Ready", "actionList": "readyCard"},
        {"label": "Flip", "actionList": "flipCard"},
        {"label": "Discard", "actionList": "discardCard"},
        {"label": "Detach", "actionList": "detachCard"},
        {"label": "Shuffle into deck", "actionList": "shuffleIntoDeck"},
    ]}})
    dump_json(jsons / "groupMenu.json", {"groupMenu": {"moveToGroupIds": MOVE_GROUPS, "options": []}})
    dump_json(jsons / "browse.json", {"browse": {
        "filterPropertySideA": "type",
        "filterValuesSideA": types,
        "textPropertiesSideA": ["name", "subtype", "keyword", "packName"],
    }})
    dump_json(jsons / "deckbuilder.json", {"deckbuilder": {
        "addButtons": [1, 2, 3, 4],
        "columns": [
            {"propName": "name", "label": "Name"},
            {"propName": "type", "label": "Type"},
            {"propName": "subtype", "label": "Subtype"},
            {"propName": "protoCost", "label": "Proto"},
            {"propName": "packName", "label": "Set"},
        ],
        "spawnGroups": [{"loadGroupId": "playerNDeck", "label": "My Deck"}],
    }})
    dump_json(jsons / "spawnExistingCardModal.json", {"spawnExistingCardModal": {
        "columnProperties": ["name", "type", "packName", "protoCost"],
        "loadGroupIds": ["player1Deck", "player1Play", "player1Hand", "sharedLocations", "sharedSetAside", "player2Deck", "player2Play"],
    }})
    dump_json(jsons / "faceProperties.json", {"faceProperties": {
        "subtype": {"label": "Subtype", "type": "string", "default": ""},
        "battleType": {"label": "Battle Type", "type": "string", "default": ""},
        "keyword": {"label": "Keyword", "type": "string", "default": ""},
        "protoCost": {"label": "Proto Cost", "type": "string", "default": ""},
        "basic": {"label": "Basic", "type": "string", "default": ""},
        "solo": {"label": "Solo", "type": "string", "default": ""},
        "transform": {"label": "Transform", "type": "string", "default": ""},
        "packName": {"label": "Set", "type": "string", "default": ""},
        "set": {"label": "Lackey Set", "type": "string", "default": ""},
        "loadGroupId": {"label": "Load Group", "type": "string", "default": ""},
    }})
    dump_json(jsons / "cardProperties.json", {"cardProperties": {}})
    dump_json(jsons / "defaultActions.json", {"defaultActions": []})
    dump_json(jsons / "automation.json", {"automation": {
        "postNewGameActionList": [["LOG", "Robotech CCG table created. Load a starter from Menu → Load. No rules are enforced."]],
        "gameRules": {},
    }})
    dump_json(jsons / "labels.json", {"labels": {}})
    dump_json(jsons / "preferences.json", {"preferences": {"game": [], "player": []}})
    dump_json(jsons / "prompts.json", {"prompts": {}})
    dump_json(jsons / "touchBar.json", {"touchBar": []})
    dump_json(jsons / "closeRoomOptions.json", {"closeRoomOptions": [{"label": "Just close", "actionList": []}]})
    dump_json(jsons / "clearTableOptions.json", {"clearTableOptions": [
        {"label": "Player 1 wins", "actionList": ["SET", "/victoryState", "player1Win"]},
        {"label": "Player 2 wins", "actionList": ["SET", "/victoryState", "player2Win"]},
        {"label": "Tie", "actionList": ["SET", "/victoryState", "tie"]},
        {"label": "Incomplete", "actionList": ["SET", "/victoryState", "incomplete"]},
    ]})
    dump_json(jsons / "preBuiltDecks.json", decks)
    dump_json(jsons / "deckMenu.json", menu)


def write_tokens() -> None:
    images = ROOT / "images" / GAME_FOLDER / "_plugin"
    write_color_png(images / f"{GAME_PASCAL}-TokenGreen.png", (46, 184, 72))
    write_color_png(images / f"{GAME_PASCAL}-TokenRed.png", (196, 48, 48))


def main() -> int:
    if not (LACKEY / "sets" / "carddata.txt").exists():
        raise SystemExit(f"Lackey plugin not found: {LACKEY}")
    urls = load_image_urls(LACKEY / "CardImageURLs1.txt")
    cards, errors = load_cards(LACKEY / "sets" / "carddata.txt", urls)
    (OUT / "tsvs").mkdir(parents=True, exist_ok=True)
    write_tsv(cards, OUT / "tsvs" / "cards.tsv")
    decks, menu, deck_errors = convert_decks(cards)
    errors.extend(deck_errors)
    write_plugin_jsons(cards, decks, menu)
    write_tokens()
    (OUT / "SOURCE.txt").write_text(
        "\n".join(
            [
                f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from LackeyCCG RobotechCCG.",
                f"Source: {LACKEY}",
                "Art: GitHub wishmstr/RobotechCCG raw setimages.",
                "Author credit: Lackey / wishmstr",
                "",
                "Tabletop plugin only — Lackey has no rules engine to port.",
                f"TSV rows: {len(cards)}  missing image URLs: {sum(1 for c in cards if not c['imageUrl'])}",
                f"Prebuilts: {len(decks['preBuiltDecks'])} Lackey starter decks.",
                "Drop banner.jpg and logo.jpg into images/robotech-ccg/_plugin/.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUT.name}")
    print(f"  pluginName: Robotech CCG")
    print(f"  tsv rows: {len(cards)}  missing urls: {sum(1 for c in cards if not c['imageUrl'])}")
    print(f"  prebuilt decks: {len(decks['preBuiltDecks'])}")
    print(f"  types: {', '.join(sorted({c['type'] for c in cards}))}")
    if errors:
        print(f"\n{len(errors)} issue(s):")
        for err in errors[:40]:
            print(f"  - {err}")
        if len(errors) > 40:
            print(f"  … {len(errors) - 40} more")
        return 1
    print()
    print("Next:")
    print("  python plugins/scripts/collect_hosted_images.py robotech-ccg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
