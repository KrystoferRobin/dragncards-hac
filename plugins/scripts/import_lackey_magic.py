#!/usr/bin/env python3
"""Build a DragnCards Magic plugin from the LackeyCCG plugin.

Card art stays on the Lackey HTTPS host (68k images — do not collect).

  python3 plugins/scripts/import_lackey_magic.py
  python3 plugins/scripts/collect_hosted_images.py magic
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import struct
import zlib
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))
from image_names import TOYBOX_PREFIX, plugin_art_rel, stamp_lobby_art, toybox_url  # noqa: E402

LACKEY = Path("/Applications/LackeyCCG/plugins/magic")
OUT = ROOT / "magic"
GAME_FOLDER = "magic"
GAME_PASCAL = "Magic"
IMAGES = ROOT / "images"
IMAGE_BASE = "https://magicplugin.normalitycomics.com/cardimages/"
MAX_PLAYERS = 4

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "typeLine",
    "color",
    "colorId",
    "cost",
    "manaValue",
    "power",
    "toughness",
    "loyalty",
    "rarity",
    "text",
    "packName",
    "set",
    "actualSet",
    "loadGroupId",
]

MOVE_GROUPS = [
    "playerSHand",
    "playerSDeck",
    "playerSGraveyard",
    "playerSExile",
    "playerSPlay",
    "playerSCommand",
    "playerSEmblem",
    "playerSTokens",
    "playerSSideboard",
    "playerLPlay",
    "sharedSetAside",
]

SUPERZONE_TO_GROUP = {
    "Deck": "playerNDeck",
    "Command": "playerNCommand",
    "Sideboard": "playerNSideboard",
}

# Same header on every file so My Plugins can merge them in one upload.
TSV_CHUNKS = [
    (
        "cards-01-core-premodern.tsv",
        "Core sets + premodern expansions",
        [
            "premodern-core-sets.txt",
            "modern-core-sets.txt",
            "modern-core-sets2.txt",
            "premodern-expansions.txt",
            "premodern-expansions2.txt",
        ],
    ),
    (
        "cards-02-modern-early.tsv",
        "Modern expansions (early files)",
        ["modern-expansions.txt", "modern-expansions2.txt"],
    ),
    (
        "cards-03-modern-late.tsv",
        "Modern expansions 3 + modern-only",
        ["modern-expansions3.txt", "modern-only-sets.txt"],
    ),
    (
        "cards-04-commander.tsv",
        "Commander products",
        ["commander.txt"],
    ),
    (
        "cards-05-special-reprints-tokens.tsv",
        "Supplemental, reprints, promos, silver-border, tokens",
        [
            "intro-sets.txt",
            "silver-border-and-special.txt",
            "supplemental.txt",
            "eternal-only-sets.txt",
            "reprint-only-sets.txt",
            "promos-and-alternates.txt",
            "custom-tokens-for-lackeyccg.txt",
        ],
    ),
]

PRIMARY_TYPES = (
    ("emblem", "Emblem"),
    ("dungeon", "Dungeon"),
    ("scheme", "Scheme"),
    ("phenomenon", "Phenomenon"),
    ("vanguard", "Vanguard"),
    ("conspiracy", "Conspiracy"),
    ("battle", "Battle"),
    ("universewalker", "Planeswalker"),
    ("planeswalker", "Planeswalker"),
    ("plane", "Plane"),
    ("token", "Token"),
    ("eaturecray", "Creature"),
    ("summon", "Creature"),
    ("creature", "Creature"),
    ("land", "Land"),
    ("instant", "Instant"),
    ("sorcery", "Sorcery"),
    ("enchantment", "Enchantment"),
    ("artifact", "Artifact"),
)


def dump_json(path: Path, payload: dict | list) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sanitize(value: str) -> str:
    return (value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()


def unescape(value: str) -> str:
    return (
        sanitize(value)
        .replace("&amp;", "&")
        .replace("&apos;", "'")
        .replace("&quot;", '"')
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )


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


def listed_carddata_files() -> list[Path]:
    listing = LACKEY / "ListOfCardDataFiles.txt"
    names = re.findall(r"<filetoinclude>(.*?)</filetoinclude>", listing.read_text(encoding="utf-8", errors="replace"))
    files = [LACKEY / "sets" / name for name in names if (LACKEY / "sets" / name).exists()]
    if files:
        return files
    return sorted((LACKEY / "sets").glob("*.txt"))


def primary_type(type_line: str) -> str:
    lowered = type_line.lower()
    for needle, label in PRIMARY_TYPES:
        if needle in lowered:
            return label
    return type_line.split(" — ")[0].split(" - ")[0].strip() or "Other"


def default_load_group(type_line: str) -> str:
    lowered = type_line.lower()
    if "emblem" in lowered:
        return "playerNEmblem"
    if "token" in lowered:
        return "playerNTokens"
    return "playerNDeck"


def image_url(image_file: str) -> str:
    stem = image_file.strip()
    if stem.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        return IMAGE_BASE + quote(stem, safe="/-_.")
    return IMAGE_BASE + quote(stem, safe="/-_.") + ".jpg"


def make_database_id(set_name: str, image_file: str) -> str:
    return f"{set_name}_{image_file.replace('/', '-')}"


def load_cards() -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    seen: dict[str, str] = {}
    skipped_dups = 0
    for path in listed_carddata_files():
        with path.open(encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t", restval="")
            if not reader.fieldnames:
                errors.append(f"{path.name}: empty header")
                continue
            for line_no, row in enumerate(reader, start=2):
                name = sanitize(row.get("Name") or "")
                set_name = sanitize(row.get("Set") or "")
                image_file = sanitize(row.get("ImageFile") or "")
                if not name or not image_file:
                    continue
                type_line = sanitize(row.get("Type") or "")
                database_id = make_database_id(set_name, image_file)
                if database_id in seen:
                    if seen[database_id] == name:
                        skipped_dups += 1
                        continue
                    database_id = f"{database_id}-{slug(name)}"
                    if database_id in seen:
                        skipped_dups += 1
                        continue
                seen[database_id] = name
                actual = sanitize(row.get("ActualSet") or "") or set_name
                cards.append(
                    {
                        "_source": path.name,
                        "databaseId": database_id,
                        "name": name,
                        "imageUrl": image_url(image_file),
                        "cardBack": "default",
                        "type": primary_type(type_line),
                        "typeLine": type_line,
                        "color": sanitize(row.get("Color") or ""),
                        "colorId": sanitize(row.get("ColorID") or ""),
                        "cost": sanitize(row.get("Cost") or ""),
                        "manaValue": sanitize(row.get("ManaValue") or ""),
                        "power": sanitize(row.get("Power") or ""),
                        "toughness": sanitize(row.get("Toughness") or ""),
                        "loyalty": sanitize(row.get("Loyalty") or ""),
                        "rarity": sanitize(row.get("Rarity") or ""),
                        "text": sanitize(row.get("Text") or ""),
                        "packName": actual.upper() if len(actual) <= 4 else actual,
                        "set": set_name,
                        "actualSet": actual,
                        "loadGroupId": default_load_group(type_line),
                    }
                )
    if skipped_dups:
        errors.append(f"Skipped {skipped_dups} duplicate printings with the same set+image.")
    return cards, errors


def write_tsv(cards: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("\t".join(TSV_COLUMNS) + "\n")
        for card in cards:
            handle.write("\t".join(sanitize(card.get(col, "")) for col in TSV_COLUMNS) + "\n")


def write_tsv_chunks(cards: list[dict[str, str]], tsv_dir: Path) -> list[tuple[str, str, int]]:
    tsv_dir.mkdir(parents=True, exist_ok=True)
    by_source: dict[str, list[dict[str, str]]] = {}
    for card in cards:
        by_source.setdefault(card.get("_source") or "", []).append(card)
    written: list[tuple[str, str, int]] = []
    assigned = 0
    for filename, label, sources in TSV_CHUNKS:
        chunk: list[dict[str, str]] = []
        for source in sources:
            chunk.extend(by_source.get(source, []))
        write_tsv(chunk, tsv_dir / filename)
        written.append((filename, label, len(chunk)))
        assigned += len(chunk)
    leftover = len(cards) - assigned
    if leftover:
        raise SystemExit(f"TSV chunk mapping missed {leftover} cards — update TSV_CHUNKS.")
    return written


def parse_dek(path: Path) -> dict[str, Counter]:
    text = path.read_text(encoding="utf-8", errors="replace")
    zones: dict[str, Counter] = {}
    for zone_name, body in re.findall(r'<superzone name="([^"]+)">(.*?)</superzone>', text, flags=re.S | re.I):
        counts: Counter = Counter()
        for match in re.finditer(r"<card>(.*?)</card>", body, flags=re.S | re.I):
            chunk = match.group(1)
            name_el = re.search(r'<name(?:\s+id="([^"]*)")?>(.*?)</name>', chunk, flags=re.S | re.I)
            set_el = re.search(r"<set>(.*?)</set>", chunk, flags=re.I)
            if name_el is None or set_el is None:
                continue
            image_id = (name_el.group(1) or "").strip()
            set_name = unescape(set_el.group(1))
            if image_id and set_name:
                counts[(set_name, image_id)] += 1
        zones[zone_name] = counts
    return zones


def convert_decks(cards: list[dict[str, str]]) -> tuple[dict, dict, list[str]]:
    known = {card["databaseId"] for card in cards}
    errors: list[str] = []
    prebuilt: OrderedDict[str, dict] = OrderedDict()
    menu: list[dict] = []
    decks_dir = LACKEY / "decks"
    if not decks_dir.exists():
        return {"preBuiltDecks": {}}, {"deckMenu": {"subMenus": []}}, errors
    for dek in sorted(decks_dir.glob("*.dek")):
        label = dek.stem.replace("_", " ")
        deck_id = slug(label)
        entries = []
        for zone_name, counts in parse_dek(dek).items():
            load_group = SUPERZONE_TO_GROUP.get(zone_name)
            if not load_group:
                errors.append(f"{dek.name}: unknown superzone {zone_name!r}")
                continue
            for (set_name, image_id), quantity in counts.items():
                database_id = make_database_id(set_name, image_id)
                if database_id not in known:
                    errors.append(f"{dek.name}: unknown card {database_id}")
                    continue
                entries.append({"databaseId": database_id, "quantity": quantity, "loadGroupId": load_group})
        prebuilt[deck_id] = {"label": label, "cards": entries}
        menu.append({"deckListId": deck_id, "label": label})
    return (
        {"preBuiltDecks": dict(prebuilt)},
        {"deckMenu": {"subMenus": [{"label": "Challenge Decks", "deckLists": menu}] if menu else []}},
        errors,
    )


def player_group(player: str, kind: str, group_type: str, table_label: str, enter: dict, **extra) -> tuple[str, dict]:
    payload = {
        "groupType": group_type,
        "label": f"Player {player[-1]} {table_label}",
        "tableLabel": table_label,
        "onCardEnter": enter,
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
    for n in range(1, MAX_PLAYERS + 1):
        player = f"player{n}"
        grave = f"{player}Graveyard"
        deck = f"{player}Deck"
        specs = (
            ("Deck", "deck", "Library", {"controller": player, "deckGroupId": deck, "discardGroupId": grave}, {}),
            ("Graveyard", "discard", "Graveyard", {"controller": player, "deckGroupId": deck, "discardGroupId": grave}, {}),
            ("Exile", "exile", "Exile", {"controller": player, "deckGroupId": deck, "discardGroupId": grave}, {}),
            ("Hand", "hand", "Hand", {"controller": player, "deckGroupId": deck, "discardGroupId": grave, "currentSide": "B", "peeking": {player: True}}, {}),
            ("Play", "inPlay", "Battlefield", {"controller": player, "deckGroupId": deck, "discardGroupId": grave}, {"canHaveAttachments": True}),
            ("Command", "command", "Command", {"controller": player, "deckGroupId": deck, "discardGroupId": grave}, {"canHaveAttachments": True}),
            ("Emblem", "command", "Emblems", {"controller": player, "discardGroupId": grave}, {"canHaveAttachments": False}),
            ("Tokens", "inPlay", "Tokens", {"controller": player, "discardGroupId": grave}, {"canHaveAttachments": True}),
            ("Sideboard", "aside", "Sideboard", {"controller": player, "deckGroupId": deck, "discardGroupId": grave}, {}),
        )
        for kind, group_type, label, enter, extra in specs:
            key, payload = player_group(player, kind, group_type, label, enter, **extra)
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


def table_buttons() -> dict:
    return {
        "drawDeck": {"actionList": "drawDeck", "label": "Draw", "left": "75%", "top": "38%", "width": "12%", "height": "3.2%"},
        "untapAll": {"actionList": "untapAll", "label": "Untap All", "left": "87%", "top": "38%", "width": "12%", "height": "3.2%"},
        "mill": {"actionList": "mill", "label": "Mill", "left": "75%", "top": "42%", "width": "12%", "height": "3.2%"},
        "playCommand": {"actionList": "playCommand", "label": "Play Cmd", "left": "87%", "top": "42%", "width": "12%", "height": "3.2%"},
        "increaseLife": {"actionList": "increaseLife", "label": "Life +1", "left": "75%", "top": "46%", "width": "12%", "height": "3.2%"},
        "decreaseLife": {"actionList": "decreaseLife", "label": "Life -1", "left": "87%", "top": "46%", "width": "12%", "height": "3.2%"},
        "toggleCommander": {
            "actionList": "toggleCommanderSlots",
            "label": "Cmd / Emblem",
            "left": "75%",
            "top": "78.2%",
            "width": "24%",
            "height": "3.2%",
        },
    }


def rail_regions() -> dict:
    return {
        "playerLDeck": region("playerLDeck", "pile", "75%", "8%", "12%", "14%"),
        "playerLGraveyard": region("playerLGraveyard", "pile", "87%", "8%", "12%", "14%"),
        "playerLExile": region("playerLExile", "pile", "75%", "23%", "12%", "13%"),
        "playerLTokens": region("playerLTokens", "pile", "87%", "23%", "12%", "13%"),
        "playerSDeck": region("playerSDeck", "pile", "75%", "50%", "12%", "14%"),
        "playerSGraveyard": region("playerSGraveyard", "pile", "87%", "50%", "12%", "14%"),
        "playerSExile": region("playerSExile", "pile", "75%", "65%", "12%", "12%"),
        "playerSTokens": region("playerSTokens", "pile", "87%", "65%", "12%", "12%"),
    }


def build_layouts() -> dict:
    shared_hands = {
        "playerLHand": region("playerLHand", "fan", "0%", "0%", "74%", "8%", disableDroppableAttachments=True),
        "playerSHand": region("playerSHand", "fan", "0%", "82%", "74%", "17%", disableDroppableAttachments=True),
    }
    standard = {
        "cardSize": 9,
        "rowSpacing": 2,
        "chat": {"left": "75%", "top": "82%", "width": "24%", "height": "17%"},
        "regions": {
            **shared_hands,
            "playerLPlay": region("playerLPlay", "free", "0%", "8%", "74%", "25%"),
            "playerSPlay": region("playerSPlay", "free", "0%", "33%", "74%", "48%"),
            **rail_regions(),
        },
        "tableButtons": table_buttons(),
    }
    commander = {
        "cardSize": 9,
        "rowSpacing": 2,
        "chat": {"left": "75%", "top": "82%", "width": "24%", "height": "17%"},
        "regions": {
            **shared_hands,
            "playerLCommand": region("playerLCommand", "pile", "0%", "8%", "9%", "13%"),
            "playerLPlay": region("playerLPlay", "free", "9.5%", "8%", "64.5%", "25%"),
            "playerLEmblem": region("playerLEmblem", "pile", "0%", "21%", "9%", "12%"),
            "playerSCommand": region("playerSCommand", "pile", "0%", "33%", "9%", "14%"),
            "playerSPlay": region("playerSPlay", "free", "9.5%", "33%", "64.5%", "48%"),
            "playerSEmblem": region("playerSEmblem", "pile", "0%", "67%", "9%", "14%"),
            **rail_regions(),
        },
        "tableButtons": table_buttons(),
    }
    return {"layouts": {"standard": standard, "commander": commander}}


def copy_plugin_art() -> str:
    dest_dir = IMAGES / GAME_FOLDER / "_plugin"
    dest_dir.mkdir(parents=True, exist_ok=True)
    back_rel = plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "cardback-default", ".jpg")
    src = LACKEY / "cardback.jpg"
    dest = IMAGES / back_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.copy2(src, dest)
    banner = dest_dir / "banner.jpg"
    logo = dest_dir / "logo.jpg"
    if (LACKEY / "bot.jpg").exists() and not banner.exists():
        shutil.copy2(LACKEY / "bot.jpg", banner)
    if src.exists() and not logo.exists():
        shutil.copy2(src, logo)
    return back_rel if src.exists() else IMAGE_BASE + "cardback.jpg"


def write_plugin_jsons(cards: list[dict[str, str]], decks: dict, menu: dict, back_rel: str) -> None:
    jsons = OUT / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    types = sorted({card["type"] for card in cards})
    dump_json(jsons / "main.json", {
        "pluginName": "Magic",
        "author": "Lackey / normalitycomics",
        "tutorialUrl": "https://magicplugin.normalitycomics.com/",
        "announcements": [
            "Tabletop Magic from the Lackey plugin. No rules engine. Card art stays on the Lackey image host.",
            "D = draw. T = tap. K = untap. R = untap all. X = graveyard. E = exile. M = mill. Cmd/Emblem toggles both players' slots.",
        ],
        "loadPreBuiltOnNewGame": False,
    })
    stamp_lobby_art(jsons, GAME_FOLDER)
    dump_json(jsons / "announcements.json", {"announcements": [
        "Magic tabletop: load a deck, draw, tap. Commander and emblem slots start hidden — use Cmd/Emblem on the right edge to show both players' slots.",
    ]})
    dump_json(jsons / "imageUrlPrefix.json", {"imageUrlPrefix": {"Default": TOYBOX_PREFIX}})
    dump_json(jsons / "cardBacks.json", {"cardBacks": {"default": {"width": 0.72, "height": 1.0, "imageUrl": back_rel}}})
    dump_json(jsons / "cardTypes.json", {"cardTypes": {
        name: {"width": 0.72, "height": 1.0, "tokens": ["green", "red", "blue"]} for name in types
    }})
    dump_json(jsons / "groups.json", build_groups())
    dump_json(jsons / "layouts.json", build_layouts())
    dump_json(jsons / "groupTypes.json", {"groupTypes": {
        "deck": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": True, "onCardEnter": {"currentSide": "B", "inPlay": False, "rotation": 0}},
        "discard": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
        "exile": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
        "hand": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "B", "inPlay": False, "rotation": 0}},
        "inPlay": {"canHaveAttachments": True, "canHaveTokens": True, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": True, "rotation": 0}},
        "command": {"canHaveAttachments": True, "canHaveTokens": True, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
        "aside": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
    }})
    dump_json(jsons / "playerCountMenu.json", {"playerCountMenu": [
        {"label": str(n), "numPlayers": n, "layoutId": "standard"} for n in (2, 3, 4)
    ]})
    dump_json(jsons / "phases.json", {
        "phases": {
            "untap": {"label": "Untap", "height": "12%"},
            "upkeep": {"label": "Upkeep", "height": "12%"},
            "draw": {"label": "Draw", "height": "12%"},
            "main1": {"label": "Main 1", "height": "13%"},
            "combat": {"label": "Combat", "height": "13%"},
            "main2": {"label": "Main 2", "height": "13%"},
            "end": {"label": "End", "height": "13%"},
            "cleanup": {"label": "Discard", "height": "12%"},
        },
        "phaseOrder": ["untap", "upkeep", "draw", "main1", "combat", "main2", "end", "cleanup"],
    })
    dump_json(jsons / "steps.json", {
        "steps": {
            "untapStep": {"phaseId": "untap", "label": "Untap"},
            "upkeepStep": {"phaseId": "upkeep", "label": "Upkeep"},
            "drawStep": {"phaseId": "draw", "label": "Draw"},
            "main1Step": {"phaseId": "main1", "label": "Main 1"},
            "combatStep": {"phaseId": "combat", "label": "Combat"},
            "main2Step": {"phaseId": "main2", "label": "Main 2"},
            "endStep": {"phaseId": "end", "label": "End"},
            "cleanupStep": {"phaseId": "cleanup", "label": "Discard"},
        },
        "stepOrder": ["untapStep", "upkeepStep", "drawStep", "main1Step", "combatStep", "main2Step", "endStep", "cleanupStep"],
    })
    dump_json(jsons / "playerProperties.json", {"playerProperties": {
        "life": {"label": "Life", "type": "integer", "default": 20},
    }})
    dump_json(jsons / "gameProperties.json", {"gameProperties": {}})
    dump_json(jsons / "topBarCounters.json", {"topBarCounters": {
        "shared": [{"label": "Round", "imageUrl": "", "gameProperty": "roundNumber"}],
        "player": [{"label": "Life", "imageUrl": "", "playerProperty": "life"}],
    }})
    token_rel = {
        "green": plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "token-green", ".png"),
        "red": plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "token-red", ".png"),
        "blue": plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "token-blue", ".png"),
    }
    dump_json(jsons / "tokens.json", {"tokens": {
        "green": {"label": "+1/+1", "left": "28%", "top": "3%", "width": "4vh", "height": "4vh", "imageUrl": toybox_url(token_rel["green"]), "canBeNegative": True},
        "red": {"label": "Damage", "left": "50%", "top": "3%", "width": "4vh", "height": "4vh", "imageUrl": toybox_url(token_rel["red"]), "canBeNegative": True},
        "blue": {"label": "Other", "left": "72%", "top": "3%", "width": "4vh", "height": "4vh", "imageUrl": toybox_url(token_rel["blue"]), "canBeNegative": True},
    }})
    dump_json(jsons / "functions.json", {"functions": {
        "DISCARD": {"args": ["$CARD_ID"], "code": [
            ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
            ["COND", ["EQUAL", "$CARD.discardGroupId", None],
             ["LOG", "{{$ALIAS_N}} failed to put {{$CARD.currentFace.name}} in the graveyard."],
             ["TRUE"], [["LOG", "{{$ALIAS_N}} put {{$CARD.sides.A.name}} into the graveyard."], ["MOVE_CARD", "$CARD.id", "$CARD.discardGroupId", 0]]],
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
             ["LOG", "{{$ALIAS_N}} failed to shuffle {{$CARD.currentFace.name}} into a library."],
             ["TRUE"], [["MOVE_CARD", "$CARD.id", "$CARD.deckGroupId", 0], ["SHUFFLE_GROUP", "$GROUP_ID"],
                        ["LOG", "{{$ALIAS_N}} shuffled {{$CARD.currentFace.name}} into {{$GAME.groupById.$GROUP_ID.label}}."]]],
        ]},
    }})
    dump_json(jsons / "actionLists.json", {"actionLists": {
        "drawDeck": [[
            "COND", ["GROUP_EMPTY", "{{$PLAYER_N}}Deck"],
            ["LOG", "{{$ALIAS_N}} tried to draw from an empty library."],
            ["TRUE"], [["MOVE_STACKS", "{{$PLAYER_N}}Deck", "{{$PLAYER_N}}Hand", 1, "bottom"], ["LOG", "{{$ALIAS_N}} drew a card."]],
        ]],
        "shuffleDeck": [["SHUFFLE_GROUP", "{{$PLAYER_N}}Deck"], ["LOG", "{{$ALIAS_N}} shuffled their library."]],
        "untapAll": [[
            "FOR_EACH_KEY_VAL", "$CARD_ID", "$CARD", "$GAME.cardById",
            ["COND", ["EQUAL", "$CARD.controller", "$PLAYER_N"], ["SET", "/cardById/{{$CARD_ID}}/rotation", 0]],
        ], ["LOG", "{{$ALIAS_N}} untapped all their permanents."]],
        "tapAll": [[
            "FOR_EACH_KEY_VAL", "$CARD_ID", "$CARD", "$GAME.cardById",
            ["COND", ["EQUAL", "$CARD.controller", "$PLAYER_N"], ["SET", "/cardById/{{$CARD_ID}}/rotation", 90]],
        ], ["LOG", "{{$ALIAS_N}} tapped all their permanents."]],
        "tapCard": [["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 90], ["LOG", "{{$ALIAS_N}} tapped {{$ACTIVE_FACE.name}}."]],
        "untapCard": [["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 0], ["LOG", "{{$ALIAS_N}} untapped {{$ACTIVE_FACE.name}}."]],
        "mill": [[
            "COND", ["GROUP_EMPTY", "{{$PLAYER_N}}Deck"],
            ["LOG", "{{$ALIAS_N}} tried to mill an empty library."],
            ["TRUE"], [["MOVE_STACKS", "{{$PLAYER_N}}Deck", "{{$PLAYER_N}}Graveyard", 1, "top"], ["LOG", "{{$ALIAS_N}} milled a card."]],
        ]],
        "playCommand": [[
            "COND", ["GROUP_EMPTY", "{{$PLAYER_N}}Command"],
            ["LOG", "{{$ALIAS_N}} has no card in the command zone."],
            ["TRUE"], [["MOVE_STACKS", "{{$PLAYER_N}}Command", "{{$PLAYER_N}}Play", 1, "top"], ["LOG", "{{$ALIAS_N}} moved their commander onto the battlefield."]],
        ]],
        "increaseLife": [["INCREASE_VAL", "/playerData/$PLAYER_N/life", 1], ["LOG", "{{$ALIAS_N}} gained 1 life."]],
        "decreaseLife": [["DECREASE_VAL", "/playerData/$PLAYER_N/life", 1], ["LOG", "{{$ALIAS_N}} lost 1 life."]],
        "rollD6": [["VAR", "$D1", ["RANDOM_INT", 1, 6]], ["LOG", "{{$ALIAS_N}} rolled 1d6: {{$D1}}."]],
        "rollD20": [["VAR", "$D1", ["RANDOM_INT", 1, 20]], ["LOG", "{{$ALIAS_N}} rolled 1d20: {{$D1}}."]],
        "flipCoin": [["VAR", "$FLIP", ["RANDOM_INT", 0, 1]], [
            "COND", ["EQUAL", "$FLIP", 0], ["LOG", "{{$ALIAS_N}} flipped a coin: Heads."], ["TRUE"], ["LOG", "{{$ALIAS_N}} flipped a coin: Tails."],
        ]],
        "toggleCommanderSlots": [[
            "COND",
            ["EQUAL", "$GAME.layoutId", "commander"],
            [["SET_LAYOUT", "shared", "standard"], ["LOG", "{{$ALIAS_N}} hid commander and emblem slots for both players."]],
            ["TRUE"],
            [["SET_LAYOUT", "shared", "commander"], ["LOG", "{{$ALIAS_N}} showed commander and emblem slots for both players."]],
        ]],
        "flipCard": [["FLIP", "$ACTIVE_CARD_ID"]],
        "discardCard": [["DISCARD", "$ACTIVE_CARD_ID"]],
        "exileCard": [["MOVE_CARD", "$ACTIVE_CARD_ID", "{{$PLAYER_N}}Exile", 0], ["LOG", "{{$ALIAS_N}} exiled {{$ACTIVE_FACE.name}}."]],
        "toCommand": [["MOVE_CARD", "$ACTIVE_CARD_ID", "{{$PLAYER_N}}Command", 0], ["LOG", "{{$ALIAS_N}} moved a card to the command zone."]],
        "toEmblem": [["MOVE_CARD", "$ACTIVE_CARD_ID", "{{$PLAYER_N}}Emblem", 0], ["LOG", "{{$ALIAS_N}} moved a card to emblems."]],
        "toTokens": [["MOVE_CARD", "$ACTIVE_CARD_ID", "{{$PLAYER_N}}Tokens", 0], ["LOG", "{{$ALIAS_N}} moved a card to the token pile."]],
        "detachCard": [["DETACH", "$ACTIVE_CARD_ID"]],
        "shuffleIntoDeck": [["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"]],
    }})
    dump_json(jsons / "hotkeys.json", {"hotkeys": {
        "game": [
            {"key": "D", "actionList": "drawDeck", "label": "Draw"},
            {"key": "S", "actionList": "shuffleDeck", "label": "Shuffle library"},
            {"key": "R", "actionList": "untapAll", "label": "Untap all"},
            {"key": "M", "actionList": "mill", "label": "Mill"},
            {"key": "C", "actionList": "toggleCommanderSlots", "label": "Toggle commander/emblem"},
            {"key": "Y", "actionList": "increaseLife", "label": "Life +1"},
            {"key": "U", "actionList": "decreaseLife", "label": "Life -1"},
            {"key": "6", "actionList": "rollD6", "label": "Roll d6"},
            {"key": "0", "actionList": "rollD20", "label": "Roll d20"},
            {"key": "I", "actionList": "flipCoin", "label": "Flip a coin"},
        ],
        "card": [
            {"key": "T", "actionList": "tapCard", "label": "Tap"},
            {"key": "K", "actionList": "untapCard", "label": "Untap"},
            {"key": "F", "actionList": ["FLIP", "$ACTIVE_CARD_ID"], "label": "Flip"},
            {"key": "X", "actionList": ["DISCARD", "$ACTIVE_CARD_ID"], "label": "Graveyard"},
            {"key": "E", "actionList": "exileCard", "label": "Exile"},
            {"key": "L", "actionList": "toCommand", "label": "To command"},
            {"key": "A", "actionList": ["DETACH", "$ACTIVE_CARD_ID"], "label": "Detach"},
            {"key": "H", "actionList": ["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"], "label": "Shuffle into library"},
        ],
        "token": [
            {"key": "1", "tokenType": "green", "label": "+1/+1"},
            {"key": "2", "tokenType": "red", "label": "Damage"},
            {"key": "3", "tokenType": "blue", "label": "Other"},
        ],
    }})
    dump_json(jsons / "pluginMenu.json", {"pluginMenu": {"options": [
        {"label": "Draw", "actionList": "drawDeck"},
        {"label": "Shuffle library", "actionList": "shuffleDeck"},
        {"label": "Untap all", "actionList": "untapAll"},
        {"label": "Tap all", "actionList": "tapAll"},
        {"label": "Mill", "actionList": "mill"},
        {"label": "Play commander", "actionList": "playCommand"},
        {"label": "Toggle commander / emblem slots", "actionList": "toggleCommanderSlots"},
        {"label": "Life +1", "actionList": "increaseLife"},
        {"label": "Life -1", "actionList": "decreaseLife"},
        {"label": "Roll d6", "actionList": "rollD6"},
        {"label": "Roll d20", "actionList": "rollD20"},
        {"label": "Flip a coin", "actionList": "flipCoin"},
    ]}})
    dump_json(jsons / "cardMenu.json", {"cardMenu": {"moveToGroupIds": MOVE_GROUPS, "options": [
        {"label": "Tap", "actionList": "tapCard"},
        {"label": "Untap", "actionList": "untapCard"},
        {"label": "Flip", "actionList": "flipCard"},
        {"label": "Graveyard", "actionList": "discardCard"},
        {"label": "Exile", "actionList": "exileCard"},
        {"label": "To command", "actionList": "toCommand"},
        {"label": "To emblems", "actionList": "toEmblem"},
        {"label": "To tokens", "actionList": "toTokens"},
        {"label": "Detach", "actionList": "detachCard"},
        {"label": "Shuffle into library", "actionList": "shuffleIntoDeck"},
    ]}})
    dump_json(jsons / "groupMenu.json", {"groupMenu": {"moveToGroupIds": MOVE_GROUPS, "options": []}})
    dump_json(jsons / "browse.json", {"browse": {
        "filterPropertySideA": "type",
        "filterValuesSideA": types,
        "textPropertiesSideA": ["name", "typeLine", "text", "packName", "cost"],
    }})
    dump_json(jsons / "deckbuilder.json", {"deckbuilder": {
        "addButtons": [1, 2, 3, 4],
        "columns": [
            {"propName": "name", "label": "Name"},
            {"propName": "type", "label": "Type"},
            {"propName": "cost", "label": "Cost"},
            {"propName": "packName", "label": "Set"},
            {"propName": "color", "label": "Color"},
        ],
        "spawnGroups": [
            {"loadGroupId": "playerNDeck", "label": "My Library"},
            {"loadGroupId": "playerNCommand", "label": "My Command"},
            {"loadGroupId": "playerNSideboard", "label": "My Sideboard"},
            {"loadGroupId": "playerNTokens", "label": "My Tokens"},
            {"loadGroupId": "playerNEmblem", "label": "My Emblems"},
        ],
    }})
    dump_json(jsons / "spawnExistingCardModal.json", {"spawnExistingCardModal": {
        "columnProperties": ["name", "type", "packName", "cost"],
        "loadGroupIds": [
            "player1Deck", "player1Command", "player1Play", "player1Hand", "player1Tokens", "player1Emblem",
            "sharedSetAside", "player2Deck", "player2Command", "player2Play", "player2Tokens",
        ],
    }})
    dump_json(jsons / "faceProperties.json", {"faceProperties": {
        "typeLine": {"label": "Type line", "type": "string", "default": ""},
        "color": {"label": "Color", "type": "string", "default": ""},
        "colorId": {"label": "Color ID", "type": "string", "default": ""},
        "cost": {"label": "Cost", "type": "string", "default": ""},
        "manaValue": {"label": "Mana value", "type": "string", "default": ""},
        "power": {"label": "Power", "type": "string", "default": ""},
        "toughness": {"label": "Toughness", "type": "string", "default": ""},
        "loyalty": {"label": "Loyalty", "type": "string", "default": ""},
        "rarity": {"label": "Rarity", "type": "string", "default": ""},
        "text": {"label": "Text", "type": "string", "default": ""},
        "packName": {"label": "Set", "type": "string", "default": ""},
        "set": {"label": "Lackey Set", "type": "string", "default": ""},
        "actualSet": {"label": "Actual Set", "type": "string", "default": ""},
        "loadGroupId": {"label": "Load Group", "type": "string", "default": ""},
    }})
    dump_json(jsons / "cardProperties.json", {"cardProperties": {}})
    dump_json(jsons / "defaultActions.json", {"defaultActions": []})
    dump_json(jsons / "automation.json", {"automation": {
        "postNewGameActionList": [["LOG", "Magic table created. Load a deck. Commander/emblem slots start hidden — Cmd/Emblem toggles both players."]],
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
    write_color_png(images / f"{GAME_PASCAL}-TokenGreen.png", (46, 184, 72))
    write_color_png(images / f"{GAME_PASCAL}-TokenRed.png", (196, 48, 48))
    write_color_png(images / f"{GAME_PASCAL}-TokenBlue.png", (48, 96, 196))


def main() -> int:
    if "--decks-only" in sys.argv:
        from import_magic_precons import main as import_precons

        return import_precons()
    if not (LACKEY / "ListOfCardDataFiles.txt").exists():
        raise SystemExit(f"Lackey plugin not found: {LACKEY}")
    cards, errors = load_cards()
    write_tsv(cards, OUT / "tsvs" / "cards.tsv")
    chunks = write_tsv_chunks(cards, OUT / "tsvs")
    decks, menu, deck_errors = convert_decks(cards)
    errors.extend(deck_errors)
    back_rel = copy_plugin_art()
    write_plugin_jsons(cards, decks, menu, back_rel)
    write_tokens()
    remote = sum(1 for card in cards if card["imageUrl"].startswith("http"))
    chunk_lines = [f"  {name}  {count} cards  ({label})" for name, label, count in chunks]
    (OUT / "tsvs" / "README.txt").write_text(
        "\n".join(
            [
                "Upload these five files together in My Plugins → Upload card database.",
                "Select all five .tsv files at once. DragnCards merges them.",
                "Do not upload cards.tsv (that is the full combined file for rebuilds).",
                "",
                *chunk_lines,
                "",
            ]
        ),
        encoding="utf-8",
    )
    (OUT / "SOURCE.txt").write_text(
        "\n".join(
            [
                f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from LackeyCCG magic.",
                f"Source: {LACKEY}",
                "Art: HTTPS hotlink to magicplugin.normalitycomics.com/cardimages/ (not downloaded).",
                "Author credit: Lackey / normalitycomics",
                "",
                "Tabletop plugin only — Lackey has no rules engine to port.",
                f"TSV rows: {len(cards)}  remote art URLs: {remote}",
                f"Prebuilts: {len(decks['preBuiltDecks'])} Lackey challenge decks.",
                "Commander/emblem slots toggle for both players via Cmd/Emblem (layout standard ↔ commander).",
                "",
                "Card database is split into five TSVs (same header). Upload all five at once:",
                *chunk_lines,
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUT.name}")
    print("  pluginName: Magic")
    print(f"  tsv rows: {len(cards)}  remote urls: {remote}")
    for name, label, count in chunks:
        print(f"  {name}: {count}  ({label})")
    print(f"  prebuilt decks: {len(decks['preBuiltDecks'])}")
    print(f"  types: {', '.join(sorted({c['type'] for c in cards}))}")
    if errors:
        print(f"\n{len(errors)} issue(s):")
        for err in errors[:40]:
            print(f"  - {err}")
        if len(errors) > 40:
            print(f"  … {len(errors) - 40} more")
        # Duplicate skips are informational.
        if any("unknown card" in err or "unknown superzone" in err or "empty header" in err for err in errors):
            return 1
    print()
    print("Next:")
    print("  python3 plugins/scripts/collect_hosted_images.py magic")
    print("  (skip_cards is on — only cardback/tokens/lobby art are local)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
