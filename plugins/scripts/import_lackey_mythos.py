#!/usr/bin/env python3
"""Build a DragnCards Mythos plugin from the LackeyCCG GitHub plugin.

  python plugins/scripts/import_lackey_mythos.py
  python plugins/scripts/collect_hosted_images.py mythos
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import struct
import xml.etree.ElementTree as ET
import zlib
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))
from image_names import (  # noqa: E402
    TOYBOX_PREFIX,
    card_rel_path,
    plugin_art_rel,
    stamp_lobby_art,
    toybox_url,
)

LACKEY = ROOT / "mythos-lackey-source"
OUT = ROOT / "mythos"
GAME_FOLDER = "mythos"
GAME_PASCAL = "Mythos"
IMAGES = ROOT / "images"

SET_LABELS = {
    "B1MU": "Miskatonic University",
    "B2CR": "Cthulhu Rising",
    "B3LN": "Legends of the Necronomicon",
    "Dreamlands": "Dreamlands",
    "Limited": "Limited",
    "Movieland": "Movieland",
    "NewAeon": "New Aeon",
    "Repointed": "Repointed",
    "Scooby": "Scooby",
    "StdC": "Standard Corrupted",
    "StdS": "Standard Steadfast",
}

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "attributes",
    "languages",
    "value",
    "sanity",
    "summon",
    "unique",
    "dimension",
    "past",
    "region",
    "city",
    "beginningSanity",
    "maxSanity",
    "education",
    "handSize",
    "minimum",
    "maximum",
    "rarity",
    "text",
    "packName",
    "set",
    "loadGroupId",
]

MOVE_GROUPS = [
    "playerNHand",
    "playerNDeck",
    "playerNDiscard",
    "playerNPlay",
    "playerNStory",
    "playerNInvestigator",
    "playerN+1Play",
    "sharedSetAside",
]

SUPERZONE_TO_GROUP = {
    "Deck": "playerNDeck",
    "Investigator": "playerNInvestigator",
}

DEK_SET_ALIASES = {code.lower(): code for code in SET_LABELS}
DEK_SET_ALIASES.update({label.lower(): code for code, label in SET_LABELS.items()})


def dump_json(path: Path, payload: dict | list) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sanitize(value: str) -> str:
    return (value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip().strip('"')


def write_color_png(path: Path, rgb: tuple[int, int, int], size: int = 48) -> None:
    red, green, blue = rgb
    raw = b"".join(b"\x00" + bytes([red, green, blue]) * size for _ in range(size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    )


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "deck"


def unique_headers(header: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for raw in header:
        name = raw.strip() or "col"
        if name.lower() == "expansion":
            name = "Set"
        n = seen.get(name, 0)
        seen[name] = n + 1
        out.append(name if n == 0 else f"{name}_{n + 1}")
    return out


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
        url = parts[1].strip()
        if not rel or not url:
            continue
        lower = rel.lower()
        urls[lower] = url
        filename = lower.split("/")[-1]
        urls[filename] = url
        urls[filename.rsplit(".", 1)[0]] = url
    return urls


def lookup_image(urls: dict[str, str], set_name: str, image: str) -> str:
    stem = image.rsplit(".", 1)[0]
    for key in (
        f"{set_name}/{image}".lower(),
        f"{set_name}/{stem}.jpg".lower(),
        image.lower(),
        f"{stem}.jpg",
        stem.lower(),
    ):
        if key in urls:
            return urls[key]
    return ""


def find_local_image(set_name: str, image: str) -> Path | None:
    folder = LACKEY / "sets" / "setimages" / set_name
    stem = image.rsplit(".", 1)[0]
    names = [image]
    if "." not in image:
        names.extend(f"{stem}{ext}" for ext in (".jpg", ".jpeg", ".png", ".gif"))
    else:
        names.append(stem + Path(image).suffix)
    for name in names:
        path = folder / name
        if path.exists():
            return path
    return None


def unique_rel(rel: str, used: dict[str, int]) -> str:
    key = rel.casefold()
    used[key] = used.get(key, 0) + 1
    if used[key] == 1:
        return rel
    path = Path(rel)
    return str(path.with_name(f"{path.stem}-{used[key]}{path.suffix}")).replace("\\", "/")


def load_group(card_type: str) -> str:
    if card_type == "Investigator":
        return "playerNInvestigator"
    return "playerNDeck"


def load_cards(urls: dict[str, str]) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    seen: set[str] = set()
    used_rels: dict[str, int] = {}

    for path in sorted((LACKEY / "sets").glob("*.txt")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines:
            continue
        header = unique_headers(lines[0].split("\t"))
        reader = csv.DictReader(lines[1:], fieldnames=header, delimiter="\t", restval="")
        for line_no, row in enumerate(reader, start=2):
            name = sanitize(row.get("Name") or "")
            set_name = sanitize(row.get("Set") or path.stem)
            image = sanitize(row.get("Image") or "")
            card_type = sanitize(row.get("Type") or "")
            if not name or not image:
                errors.append(f"{path.name}:{line_no} missing name/image")
                continue
            database_id = f"{set_name}_{image}"
            if database_id in seen:
                errors.append(f"Duplicate {database_id} in {path.name}:{line_no}")
                continue
            seen.add(database_id)
            pack = SET_LABELS.get(set_name, set_name)
            local = find_local_image(set_name, image)
            github = lookup_image(urls, set_name, image)
            image_url = github
            if local:
                ext = local.suffix or ".jpg"
                rel = unique_rel(card_rel_path(GAME_FOLDER, GAME_PASCAL, pack, name, ext), used_rels)
                dest = IMAGES / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists() or dest.stat().st_size != local.stat().st_size:
                    shutil.copy2(local, dest)
                image_url = rel
            elif not github:
                errors.append(f"Missing art for {database_id}")
            cards.append(
                {
                    "databaseId": database_id,
                    "name": name,
                    "imageUrl": image_url,
                    "cardBack": "default",
                    "type": card_type or "Unknown",
                    "attributes": sanitize(row.get("Attributes") or ""),
                    "languages": sanitize(row.get("Languages") or ""),
                    "value": sanitize(row.get("Value") or ""),
                    "sanity": sanitize(row.get("Sanity") or ""),
                    "summon": sanitize(row.get("Summon") or ""),
                    "unique": sanitize(row.get("Unique") or ""),
                    "dimension": sanitize(row.get("Dimension") or ""),
                    "past": sanitize(row.get("Past") or ""),
                    "region": sanitize(row.get("Region") or ""),
                    "city": sanitize(row.get("City") or ""),
                    "beginningSanity": sanitize(row.get("Beginning Sanity") or ""),
                    "maxSanity": sanitize(row.get("Max Sanity") or ""),
                    "education": sanitize(row.get("Education") or ""),
                    "handSize": sanitize(row.get("Hand Size") or ""),
                    "minimum": sanitize(row.get("Minuimum") or row.get("Minimum") or ""),
                    "maximum": sanitize(row.get("Maximum") or ""),
                    "rarity": sanitize(row.get("Rarity") or ""),
                    "text": sanitize(row.get("Text") or ""),
                    "packName": pack,
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
            if name_el is None or set_el is None:
                continue
            image_id = (name_el.attrib.get("id") or "").strip()
            set_name = (set_el.text or "").strip()
            set_code = DEK_SET_ALIASES.get(set_name.lower(), set_name)
            if image_id and set_code:
                counts[f"{set_code}_{image_id}"] += 1
        zones[zone_name] = counts
    return zones


def deck_label(filename: str) -> str:
    if filename.startswith("Sample.The.Dunwich"):
        return "Sample: The Dunwich Horror"
    stem = Path(filename).stem.replace("..", ".")
    label = stem.replace(".", " ").strip()
    if label.startswith("Sample "):
        return "Sample: " + label[len("Sample ") :]
    return label


def convert_decks(cards: list[dict[str, str]]) -> tuple[dict, dict, list[str]]:
    known = {card["databaseId"] for card in cards}
    errors: list[str] = []
    prebuilt: OrderedDict[str, dict] = OrderedDict()
    sample: list[dict] = []
    standard: list[dict] = []
    for dek in sorted((LACKEY / "decks").glob("*.dek")):
        label = deck_label(dek.name)
        deck_id = slug(label)
        entries = []
        for zone_name, counts in parse_dek(dek).items():
            load_group = SUPERZONE_TO_GROUP.get(zone_name)
            if not load_group:
                errors.append(f"{dek.name}: unknown superzone {zone_name!r}")
                continue
            for database_id, quantity in counts.items():
                if database_id not in known:
                    errors.append(f"{dek.name}: unknown card {database_id}")
                    continue
                entries.append({"databaseId": database_id, "quantity": quantity, "loadGroupId": load_group})
        prebuilt[deck_id] = {"label": label, "cards": entries}
        item = {"deckListId": deck_id, "label": label}
        if label.startswith("Sample"):
            sample.append(item)
        else:
            standard.append(item)
    sub = []
    if standard:
        sub.append({"label": "Standard", "deckLists": standard})
    if sample:
        sub.append({"label": "Sample Decks", "deckLists": sample})
    return {"preBuiltDecks": dict(prebuilt)}, {"deckMenu": {"subMenus": sub}}, errors


def player_group(player: str, kind: str, group_type: str, table_label: str, **extra) -> tuple[str, dict]:
    payload = {
        "groupType": group_type,
        "label": f"Player {player[-1]} {table_label}",
        "tableLabel": table_label,
        "onCardEnter": {
            "controller": player,
            "deckGroupId": f"{player}Deck",
            "discardGroupId": f"{player}Discard",
        },
    }
    payload.update(extra)
    return f"{player}{kind}", payload


def build_groups() -> dict:
    groups: dict[str, dict] = {
        "sharedSetAside": {
            "groupType": "aside",
            "label": "Set Aside",
            "tableLabel": "Set Aside",
            "onCardEnter": {"controller": "shared"},
        }
    }
    for player in ("player1", "player2"):
        for kind, group_type, label, extra in (
            ("Deck", "deck", "Deck", {}),
            ("Discard", "discard", "Discard", {}),
            ("Hand", "hand", "Hand", {}),
            ("Play", "inPlay", "Play", {"canHaveAttachments": True}),
            ("Story", "inPlay", "Story", {"canHaveAttachments": False}),
            ("Investigator", "investigator", "Investigator", {"canHaveAttachments": True}),
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
                    "playerN+1Hand": region("playerN+1Hand", "fan", "0%", "0%", "75%", "9%", disableDroppableAttachments=True),
                    "playerN+1Story": region("playerN+1Story", "row", "0%", "9%", "60%", "11%"),
                    "playerN+1Investigator": region("playerN+1Investigator", "pile", "61%", "9%", "14%", "11%"),
                    "playerN+1Play": region("playerN+1Play", "free", "0%", "20%", "75%", "22%"),
                    "playerNPlay": region("playerNPlay", "free", "0%", "44%", "75%", "22%"),
                    "playerNStory": region("playerNStory", "row", "0%", "66%", "60%", "11%"),
                    "playerNInvestigator": region("playerNInvestigator", "pile", "61%", "66%", "14%", "11%"),
                    "playerNHand": region("playerNHand", "fan", "0%", "82%", "58%", "17%", disableDroppableAttachments=True),
                    "playerN+1Deck": region("playerN+1Deck", "pile", "76%", "10%", "11%", "16%"),
                    "playerN+1Discard": region("playerN+1Discard", "pile", "88%", "10%", "11%", "16%"),
                    "sharedSetAside": region("sharedSetAside", "pile", "76%", "27%", "23%", "14%"),
                    "playerNDeck": region("playerNDeck", "pile", "76%", "58%", "11%", "16%"),
                    "playerNDiscard": region("playerNDiscard", "pile", "88%", "58%", "11%", "16%"),
                },
                "tableButtons": {
                    "drawDeck": {"actionList": "drawDeck", "label": "Draw", "left": "76%", "top": "44%", "width": "11%", "height": "3.2%"},
                    "readyAll": {"actionList": "readyAll", "label": "Ready All", "left": "88%", "top": "44%", "width": "11%", "height": "3.2%"},
                    "rollD6": {"actionList": "rollD6", "label": "d6", "left": "76%", "top": "48%", "width": "11%", "height": "3.2%"},
                    "rollD20": {"actionList": "rollD20", "label": "d20", "left": "88%", "top": "48%", "width": "11%", "height": "3.2%"},
                    "increaseSanity": {"actionList": "increaseSanity", "label": "Sanity +1", "left": "76%", "top": "52%", "width": "11%", "height": "3.2%"},
                    "decreaseSanity": {"actionList": "decreaseSanity", "label": "Sanity -1", "left": "88%", "top": "52%", "width": "11%", "height": "3.2%"},
                },
            }
        }
    }


def write_plugin_jsons(cards: list[dict[str, str]], decks: dict, menu: dict) -> None:
    jsons = OUT / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    types = sorted({card["type"] for card in cards})
    back_src = LACKEY / "sets" / "setimages" / "general" / "cardback.jpg"
    back_rel = plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "cardback-default", ".jpg")
    if back_src.exists():
        dest = IMAGES / back_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(back_src, dest)
        back_url = back_rel
    else:
        back_url = "https://raw.githubusercontent.com/Sillywiz04/Mythos/main/sets/setimages/general/cardback.jpg"

    dump_json(jsons / "main.json", {
        "pluginName": "Mythos",
        "author": "Lackey / Sillywiz04",
        "tutorialUrl": "https://github.com/Sillywiz04/Mythos",
        "announcements": [
            "Tabletop plugin from the Lackey Mythos set. No rules engine — Sanity, APs, Story, and Investigator piles are shortcuts.",
            "D = draw. R = ready all. T = rotate. X = discard. 6 = d6. 0 = d20. Y/U = Sanity. O/P = Action Points.",
        ],
        "loadPreBuiltOnNewGame": False,
    })
    stamp_lobby_art(jsons, GAME_FOLDER)
    dump_json(jsons / "announcements.json", {"announcements": [
        "Mythos tabletop: load a sample or standard deck. Investigator cards go to the Investigator pile. Adventures completed belong on Story.",
    ]})
    dump_json(jsons / "imageUrlPrefix.json", {"imageUrlPrefix": {"Default": TOYBOX_PREFIX}})
    dump_json(jsons / "cardBacks.json", {"cardBacks": {"default": {"width": 0.72, "height": 1.0, "imageUrl": back_url}}})
    dump_json(jsons / "cardTypes.json", {"cardTypes": {
        name: {"width": 0.72, "height": 1.0, "tokens": ["red", "yellow", "green"]} for name in types
    }})
    dump_json(jsons / "groups.json", build_groups())
    dump_json(jsons / "layouts.json", build_layouts())
    dump_json(jsons / "groupTypes.json", {"groupTypes": {
        "deck": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": True, "onCardEnter": {"currentSide": "B", "inPlay": False, "rotation": 0}},
        "discard": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
        "hand": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
        "inPlay": {"canHaveAttachments": True, "canHaveTokens": True, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": True, "rotation": 0}},
        "investigator": {"canHaveAttachments": True, "canHaveTokens": True, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": True, "rotation": 0}},
        "aside": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
    }})
    dump_json(jsons / "playerCountMenu.json", {"playerCountMenu": [{"label": "2", "numPlayers": 2, "layoutId": "default"}]})
    dump_json(jsons / "phases.json", {
        "phases": {
            "actions": {"label": "Actions", "height": "16%"},
            "commitMonster": {"label": "Commit Monster", "height": "16%"},
            "commitAllies": {"label": "Commit Allies", "height": "17%"},
            "spellsArtifacts": {"label": "Spells/Artifacts", "height": "17%"},
            "combat": {"label": "Combat", "height": "17%"},
            "endRound": {"label": "End of Round", "height": "17%"},
        },
        "phaseOrder": ["actions", "commitMonster", "commitAllies", "spellsArtifacts", "combat", "endRound"],
    })
    dump_json(jsons / "steps.json", {
        "steps": {
            "actionsStep": {"phaseId": "actions", "label": "Actions"},
            "commitMonsterStep": {"phaseId": "commitMonster", "label": "Commit Monster"},
            "commitAlliesStep": {"phaseId": "commitAllies", "label": "Commit Allies"},
            "spellsArtifactsStep": {"phaseId": "spellsArtifacts", "label": "Spells/Artifacts"},
            "combatStep": {"phaseId": "combat", "label": "Combat"},
            "endRoundStep": {"phaseId": "endRound", "label": "End of Round"},
        },
        "stepOrder": ["actionsStep", "commitMonsterStep", "commitAlliesStep", "spellsArtifactsStep", "combatStep", "endRoundStep"],
    })
    dump_json(jsons / "playerProperties.json", {"playerProperties": {
        "sanity": {"label": "Sanity", "type": "integer", "default": 20, "min": 0},
        "actionPoints": {"label": "APs", "type": "integer", "default": 0, "min": 0},
    }})
    dump_json(jsons / "gameProperties.json", {"gameProperties": {}})
    dump_json(jsons / "topBarCounters.json", {"topBarCounters": {
        "shared": [{"label": "Round", "imageUrl": "", "gameProperty": "roundNumber"}],
        "player": [
            {"label": "Sanity", "imageUrl": "", "playerProperty": "sanity"},
            {"label": "APs", "imageUrl": "", "playerProperty": "actionPoints"},
        ],
    }})
    red_rel = plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "token-red", ".png")
    yellow_rel = plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "token-yellow", ".png")
    green_rel = plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "token-green", ".png")
    dump_json(jsons / "tokens.json", {"tokens": {
        "red": {"label": "Red", "left": "15%", "top": "4%", "width": "4vh", "height": "4vh", "imageUrl": toybox_url(red_rel), "canBeNegative": True},
        "yellow": {"label": "Yellow", "left": "50%", "top": "4%", "width": "4vh", "height": "4vh", "imageUrl": toybox_url(yellow_rel), "canBeNegative": True},
        "green": {"label": "Green", "left": "85%", "top": "4%", "width": "4vh", "height": "4vh", "imageUrl": toybox_url(green_rel), "canBeNegative": True},
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
            [["MOVE_STACKS", "{{$PLAYER_N}}Deck", "{{$PLAYER_N}}Hand", 1, "bottom"], ["LOG", "{{$ALIAS_N}} drew a card."]],
        ]],
        "shuffleDeck": [["SHUFFLE_GROUP", "{{$PLAYER_N}}Deck"], ["LOG", "{{$ALIAS_N}} shuffled their deck."]],
        "readyAll": [[
            "FOR_EACH_KEY_VAL", "$CARD_ID", "$CARD", "$GAME.cardById",
            ["COND", ["EQUAL", "$CARD.controller", "$PLAYER_N"], ["SET", "/cardById/{{$CARD_ID}}/rotation", 0]],
        ], ["LOG", "{{$ALIAS_N}} readied all their cards."]],
        "rotateCard": [["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 90], ["LOG", "{{$ALIAS_N}} rotated {{$ACTIVE_FACE.name}}."]],
        "unrotateCard": [["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 0], ["LOG", "{{$ALIAS_N}} unrotated {{$ACTIVE_FACE.name}}."]],
        "flipCoin": [["VAR", "$FLIP", ["RANDOM_INT", 0, 1]], [
            "COND", ["EQUAL", "$FLIP", 0], ["LOG", "{{$ALIAS_N}} flipped a coin: Heads."], ["TRUE"], ["LOG", "{{$ALIAS_N}} flipped a coin: Tails."],
        ]],
        "rollD6": [["VAR", "$D1", ["RANDOM_INT", 1, 6]], ["LOG", "{{$ALIAS_N}} rolled 1d6: {{$D1}}."]],
        "rollD20": [["VAR", "$D1", ["RANDOM_INT", 1, 20]], ["LOG", "{{$ALIAS_N}} rolled 1d20: {{$D1}}."]],
        "increaseSanity": [["INCREASE_VAL", "/playerData/$PLAYER_N/sanity", 1], ["LOG", "{{$ALIAS_N}} gained 1 Sanity."]],
        "decreaseSanity": [[
            "COND",
            ["GREATER_THAN", "$GAME.playerData.$PLAYER_N.sanity", 0],
            [["DECREASE_VAL", "/playerData/$PLAYER_N/sanity", 1], ["LOG", "{{$ALIAS_N}} lost 1 Sanity."]],
            ["TRUE"],
            ["LOG", "{{$ALIAS_N}} has no Sanity left."],
        ]],
        "increaseAP": [["INCREASE_VAL", "/playerData/$PLAYER_N/actionPoints", 1], ["LOG", "{{$ALIAS_N}} gained 1 AP."]],
        "decreaseAP": [[
            "COND",
            ["GREATER_THAN", "$GAME.playerData.$PLAYER_N.actionPoints", 0],
            [["DECREASE_VAL", "/playerData/$PLAYER_N/actionPoints", 1], ["LOG", "{{$ALIAS_N}} spent 1 AP."]],
            ["TRUE"],
            ["LOG", "{{$ALIAS_N}} has no APs to spend."],
        ]],
        "flipCard": [["FLIP", "$ACTIVE_CARD_ID"]],
        "discardCard": [["DISCARD", "$ACTIVE_CARD_ID"]],
        "detachCard": [["DETACH", "$ACTIVE_CARD_ID"]],
        "shuffleIntoDeck": [["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"]],
        "toStory": [["MOVE_CARD", "$ACTIVE_CARD_ID", "{{$PLAYER_N}}Story", 0], ["LOG", "{{$ALIAS_N}} moved a card to Story."]],
    }})
    dump_json(jsons / "hotkeys.json", {"hotkeys": {
        "game": [
            {"key": "D", "actionList": "drawDeck", "label": "Draw"},
            {"key": "S", "actionList": "shuffleDeck", "label": "Shuffle deck"},
            {"key": "R", "actionList": "readyAll", "label": "Ready all"},
            {"key": "6", "actionList": "rollD6", "label": "Roll d6"},
            {"key": "0", "actionList": "rollD20", "label": "Roll d20"},
            {"key": "I", "actionList": "flipCoin", "label": "Flip a coin"},
            {"key": "Y", "actionList": "increaseSanity", "label": "Sanity +1"},
            {"key": "U", "actionList": "decreaseSanity", "label": "Sanity -1"},
            {"key": "O", "actionList": "increaseAP", "label": "AP +1"},
            {"key": "P", "actionList": "decreaseAP", "label": "AP -1"},
        ],
        "card": [
            {"key": "T", "actionList": "rotateCard", "label": "Rotate"},
            {"key": "K", "actionList": "unrotateCard", "label": "Unrotate"},
            {"key": "F", "actionList": ["FLIP", "$ACTIVE_CARD_ID"], "label": "Flip"},
            {"key": "X", "actionList": ["DISCARD", "$ACTIVE_CARD_ID"], "label": "Discard"},
            {"key": "A", "actionList": ["DETACH", "$ACTIVE_CARD_ID"], "label": "Detach"},
            {"key": "H", "actionList": ["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"], "label": "Shuffle into deck"},
            {"key": "Q", "actionList": "toStory", "label": "Move to Story"},
        ],
        "token": [
            {"key": "1", "tokenType": "red", "label": "Red counter"},
            {"key": "2", "tokenType": "yellow", "label": "Yellow counter"},
            {"key": "3", "tokenType": "green", "label": "Green counter"},
        ],
    }})
    dump_json(jsons / "pluginMenu.json", {"pluginMenu": {"options": [
        {"label": "Draw", "actionList": "drawDeck"},
        {"label": "Shuffle deck", "actionList": "shuffleDeck"},
        {"label": "Ready all", "actionList": "readyAll"},
        {"label": "Roll d6", "actionList": "rollD6"},
        {"label": "Roll d20", "actionList": "rollD20"},
        {"label": "Flip a coin", "actionList": "flipCoin"},
        {"label": "Sanity +1", "actionList": "increaseSanity"},
        {"label": "Sanity -1", "actionList": "decreaseSanity"},
        {"label": "AP +1", "actionList": "increaseAP"},
        {"label": "AP -1", "actionList": "decreaseAP"},
    ]}})
    dump_json(jsons / "cardMenu.json", {"cardMenu": {"moveToGroupIds": MOVE_GROUPS, "options": [
        {"label": "Rotate", "actionList": "rotateCard"},
        {"label": "Unrotate", "actionList": "unrotateCard"},
        {"label": "Flip", "actionList": "flipCard"},
        {"label": "Discard", "actionList": "discardCard"},
        {"label": "Move to Story", "actionList": "toStory"},
        {"label": "Detach", "actionList": "detachCard"},
        {"label": "Shuffle into deck", "actionList": "shuffleIntoDeck"},
    ]}})
    dump_json(jsons / "groupMenu.json", {"groupMenu": {"moveToGroupIds": MOVE_GROUPS, "options": []}})
    dump_json(jsons / "browse.json", {"browse": {
        "filterPropertySideA": "type",
        "filterValuesSideA": types,
        "textPropertiesSideA": ["name", "attributes", "text", "packName", "region", "city"],
    }})
    dump_json(jsons / "deckbuilder.json", {"deckbuilder": {
        "addButtons": [1, 2, 3, 4],
        "columns": [
            {"propName": "name", "label": "Name"},
            {"propName": "type", "label": "Type"},
            {"propName": "value", "label": "Value"},
            {"propName": "packName", "label": "Set"},
            {"propName": "region", "label": "Region"},
        ],
        "spawnGroups": [
            {"loadGroupId": "playerNDeck", "label": "My Deck"},
            {"loadGroupId": "playerNInvestigator", "label": "My Investigator"},
        ],
    }})
    dump_json(jsons / "spawnExistingCardModal.json", {"spawnExistingCardModal": {
        "columnProperties": ["name", "type", "packName", "value"],
        "loadGroupIds": [
            "player1Deck", "player1Investigator", "player1Play", "player1Story", "player1Hand",
            "sharedSetAside", "player2Deck", "player2Investigator", "player2Play", "player2Story",
        ],
    }})
    dump_json(jsons / "faceProperties.json", {"faceProperties": {
        "attributes": {"label": "Attributes", "type": "string", "default": ""},
        "languages": {"label": "Languages", "type": "string", "default": ""},
        "value": {"label": "Value", "type": "string", "default": ""},
        "sanity": {"label": "Sanity", "type": "string", "default": ""},
        "summon": {"label": "Summon", "type": "string", "default": ""},
        "unique": {"label": "Unique", "type": "string", "default": ""},
        "dimension": {"label": "Dimension", "type": "string", "default": ""},
        "past": {"label": "Past", "type": "string", "default": ""},
        "region": {"label": "Region", "type": "string", "default": ""},
        "city": {"label": "City", "type": "string", "default": ""},
        "beginningSanity": {"label": "Beginning Sanity", "type": "string", "default": ""},
        "maxSanity": {"label": "Max Sanity", "type": "string", "default": ""},
        "education": {"label": "Education", "type": "string", "default": ""},
        "handSize": {"label": "Hand Size", "type": "string", "default": ""},
        "minimum": {"label": "Minimum", "type": "string", "default": ""},
        "maximum": {"label": "Maximum", "type": "string", "default": ""},
        "rarity": {"label": "Rarity", "type": "string", "default": ""},
        "text": {"label": "Text", "type": "string", "default": ""},
        "packName": {"label": "Set", "type": "string", "default": ""},
        "set": {"label": "Lackey Set", "type": "string", "default": ""},
        "loadGroupId": {"label": "Load Group", "type": "string", "default": ""},
    }})
    dump_json(jsons / "cardProperties.json", {"cardProperties": {}})
    dump_json(jsons / "defaultActions.json", {"defaultActions": []})
    dump_json(jsons / "automation.json", {"automation": {
        "postNewGameActionList": [["LOG", "Mythos table created. Load a sample or standard deck. No rules are enforced."]],
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
    images = IMAGES / GAME_FOLDER / "_plugin"
    write_color_png(images / f"{GAME_PASCAL}-TokenRed.png", (196, 48, 48))
    write_color_png(images / f"{GAME_PASCAL}-TokenYellow.png", (212, 176, 40))
    write_color_png(images / f"{GAME_PASCAL}-TokenGreen.png", (46, 184, 72))


def main() -> int:
    if not (LACKEY / "sets" / "Limited.txt").exists():
        raise SystemExit(
            "Mythos Lackey source not found. Clone it with:\n"
            "  git clone --depth 1 https://github.com/Sillywiz04/Mythos.git plugins/mythos-lackey-source"
        )
    urls = load_image_urls(LACKEY / "CardImageURLs1.txt")
    cards, errors = load_cards(urls)
    write_tsv(cards, OUT / "tsvs" / "cards.tsv")
    decks, menu, deck_errors = convert_decks(cards)
    errors.extend(deck_errors)
    write_plugin_jsons(cards, decks, menu)
    write_tokens()
    missing = sum(1 for card in cards if not card["imageUrl"])
    remote = sum(1 for card in cards if card["imageUrl"].startswith("http"))
    (OUT / "SOURCE.txt").write_text(
        "\n".join(
            [
                f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from LackeyCCG Mythos (Sillywiz04).",
                "Source clone: plugins/mythos-lackey-source (https://github.com/Sillywiz04/Mythos)",
                "Author credit: Lackey / Sillywiz04",
                "",
                "Tabletop plugin only — Lackey has no rules engine to port.",
                f"TSV rows: {len(cards)}  missing art: {missing}  still remote: {remote}",
                f"Prebuilts: {len(decks['preBuiltDecks'])} Lackey sample/standard decks.",
                "Lobby banner.jpg / logo.jpg live in images/mythos/_plugin/.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUT.name}")
    print("  pluginName: Mythos")
    print(f"  tsv rows: {len(cards)}  missing art: {missing}  still remote: {remote}")
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
    print("  python plugins/scripts/collect_hosted_images.py mythos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
