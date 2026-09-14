#!/usr/bin/env python3
"""Build a DragnCards Call of Cthulhu LCG plugin from the LackeyCCG plugin.

  python3 plugins/scripts/import_lackey_coc_lcg.py
  python3 plugins/scripts/collect_hosted_images.py call-of-cthulhu-lcg
"""

from __future__ import annotations

import json
import re
import struct
import urllib.request
import zlib
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))
from image_names import (  # noqa: E402
    TOYBOX_PREFIX,
    card_rel_path,
    clear_image_url_prefix,
    plugin_art_rel,
    stamp_lobby_art,
    toybox_url,
)

LACKEY = Path("/Applications/LackeyCCG/plugins/CoC_LCG")
OUT = ROOT / "call-of-cthulhu-lcg"
GAME_FOLDER = "call-of-cthulhu-lcg"
GAME_PASCAL = "CallOfCthulhuLcg"
IMAGES = ROOT / "images"
IMAGE_BASE = "https://raw.githubusercontent.com/Tragic-zz/lackey-CoCLCG/master/cards/"
ART_ROOT = "https://raw.githubusercontent.com/Tragic-zz/lackey-CoCLCG/master/"
MAX_PLAYERS = 2
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

SET_LABELS = {
    "Core": "Core Set",
    "FL": "Forgotten Lore",
    "SotD": "Summons of the Deep",
    "DL": "Dreamlands",
    "TYC": "The Yuggoth Contract",
    "tRotO": "The Rituals of the Order",
    "REV": "Revelations",
    "AR": "Ancient Relics",
    "tOotST": "Order of the Silver Twilight",
    "SOK": "Seekers of Knowledge",
    "Key": "The Key and the Gate",
    "TIV": "Terror in Venice",
    "DOTU": "Denizens of the Underworld",
    "TSB": "The Sleeper Below",
    "FGG": "For the Greater Good",
    "TTY": "The Thousand Young",
    "MOM": "The Mark of Madness",
    "SoA": "Secrets of Arkham",
    "Stories": "Stories",
    "Domains": "Domains",
}

FACTION_ALIASES = {
    "Miskatonic": "Miskatonic University",
    "Silver": "Silver Twilight",
}

STORY_DECKS = {
    ".story.LCG-Core.Set.dek": "LCG Core Stories",
    ".story.LCG-Secrets.of.Arkham.dek": "LCG Secrets of Arkham Stories",
    ".story.LCG-Ancient.Relics.dek": "LCG Ancient Relics Stories",
    ".story.CCG-Arkham.Edition.dek": "CCG Arkham Edition Stories",
    ".story.CCG-Eldritch.Edition.dek": "CCG Eldritch Edition Stories",
    ".story-ALL.dek": "All Stories",
}

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "subtype",
    "faction",
    "unique",
    "cost",
    "terror",
    "combat",
    "arcane",
    "investigation",
    "skill",
    "text",
    "errata",
    "restricted",
    "cycle",
    "packName",
    "set",
    "edition",
    "loadGroupId",
]

MOVE_GROUPS = [
    "playerNHand",
    "playerNDeck",
    "playerNDiscard",
    "playerNPlay",
    "playerNDomains",
    "playerNWon",
    "playerN+1Play",
    "playerN+1Domains",
    "playerN+1Won",
    "sharedStories",
    "sharedStoryDeck",
    "sharedSetAside",
]

PHASES = [
    ("refresh", "Refresh"),
    ("draw", "Draw"),
    ("resource", "Resource"),
    ("operations", "Operations"),
    ("youCommit", "You Commit"),
    ("enemyCommit", "Enemy Commits"),
    ("terror", "Terror"),
    ("combat", "Combat"),
    ("arcane", "Arcane"),
    ("investigation", "Investigation"),
    ("success", "Determine Success"),
    ("responses", "Responses/Actions"),
    ("uncommit", "Uncommit"),
    ("end", "End"),
]


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


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "deck"


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read()


def write_color_png(path: Path, rgb: tuple[int, int, int], width: int = 48, height: int = 48) -> None:
    red, green, blue = rgb
    raw = b"".join(b"\x00" + bytes([red, green, blue]) * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    )


def card_image_url(image_file: str) -> str:
    image_file = sanitize(image_file)
    if not image_file:
        return ""
    name = Path(image_file).name
    if "." not in name:
        image_file = f"{image_file}.jpg"
    return IMAGE_BASE + quote(image_file, safe="-_.")


def normalize_faction(value: str, card_type: str) -> str:
    value = sanitize(value)
    if card_type == "Domain":
        return "Neutral"
    return FACTION_ALIASES.get(value, value)


def pack_label(set_name: str, cycle: str, pack: str) -> str:
    pack = sanitize(pack)
    cycle = sanitize(cycle)
    if pack.startswith("Deluxe") or pack.startswith("(S)"):
        if pack.startswith("(S)"):
            rest = pack[3:].strip(" ()")
            return f"{rest} Stories" if rest else "Stories"
        return cycle or SET_LABELS.get(set_name, set_name)
    if pack:
        return pack
    if cycle and cycle not in {"Token", "Stories"}:
        return cycle
    return SET_LABELS.get(set_name, set_name)


def load_group(card_type: str) -> str:
    if card_type == "Story":
        return "sharedStoryDeck"
    if card_type == "Domain":
        return "playerNDomains"
    return "playerNDeck"


def load_cards() -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    seen: set[str] = set()
    path = LACKEY / "sets" / "CardDataFile.txt"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    header = [h.strip() for h in lines[0].split("\t")]
    expected = [
        "Name",
        "Set",
        "ImageFile",
        "Errata",
        "Restricted",
        "Cycle",
        "Pack",
        "Release Order",
        "Edition",
        "Unique",
        "Faction",
        "Type",
        "SubType",
        "Cost",
        "Terror",
        "Combat",
        "Arcane",
        "Investigation",
        "Skill",
        "Text",
    ]
    if header[:20] != expected:
        errors.append(f"Unexpected carddata header: {header}")

    for line_no, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        cols = line.split("\t")
        while len(cols) < 20:
            cols.append("")
        name = sanitize(cols[0])
        set_name = sanitize(cols[1])
        image_file = sanitize(cols[2])
        if not name or not image_file:
            errors.append(f"Line {line_no}: missing name or ImageFile")
            continue
        card_type = sanitize(cols[11]) or ("Domain" if set_name == "Domains" else "Unknown")
        stem = Path(image_file).stem
        database_id = f"{set_name}_{stem}"
        if database_id in seen:
            database_id = f"{database_id}_{slug(name)}"
        if database_id in seen:
            errors.append(f"Duplicate {database_id} at line {line_no}")
            continue
        seen.add(database_id)
        if card_type == "Domain":
            image_url = card_rel_path(GAME_FOLDER, GAME_PASCAL, "Domains", name, ".png")
        else:
            image_url = card_image_url(image_file)
        cards.append(
            {
                "databaseId": database_id,
                "name": name,
                "imageUrl": image_url,
                "cardBack": "default",
                "type": card_type,
                "subtype": sanitize(cols[12]).rstrip("."),
                "faction": normalize_faction(cols[10], card_type),
                "unique": "*" if sanitize(cols[9]) == "*" else "",
                "cost": sanitize(cols[13]),
                "terror": sanitize(cols[14]),
                "combat": sanitize(cols[15]),
                "arcane": sanitize(cols[16]),
                "investigation": sanitize(cols[17]),
                "skill": sanitize(cols[18]),
                "text": sanitize(cols[19]),
                "errata": sanitize(cols[3]),
                "restricted": sanitize(cols[4]),
                "cycle": sanitize(cols[5]),
                "packName": pack_label(set_name, cols[5], cols[6]),
                "set": set_name,
                "edition": sanitize(cols[8]) or ("Token" if card_type == "Domain" else ""),
                "loadGroupId": load_group(card_type),
                "_stem": stem,
                "_image": image_file,
            }
        )
    return cards, errors


def write_tsv(cards: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["\t".join(TSV_COLUMNS)]
    rows.extend("\t".join(sanitize(card.get(col, "")) for col in TSV_COLUMNS) for card in cards)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def parse_dek(text: str) -> dict[str, list[tuple[str, str, str]]]:
    zones: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for zone_name, body in re.findall(r'<superzone name="([^"]+)">(.*?)</superzone>', text, flags=re.S | re.I):
        for match in re.finditer(r"<card>(.*?)</card>", body, flags=re.S | re.I):
            chunk = match.group(1)
            name_el = re.search(r"<name([^>]*)>(.*?)</name>", chunk, flags=re.S | re.I)
            set_el = re.search(r"<set>(.*?)</set>", chunk, flags=re.I)
            if name_el is None or set_el is None:
                continue
            image_id = ""
            id_attr = re.search(r'\bid="([^"]+)"', name_el.group(1) or "")
            if id_attr:
                image_id = sanitize(id_attr.group(1))
            name = unescape(re.sub(r"<[^>]+>", "", name_el.group(2)))
            set_name = unescape(set_el.group(1))
            if name:
                zones[zone_name].append((name, set_name, image_id))
    return zones


def build_card_index(cards: list[dict[str, str]]) -> dict:
    by_image: dict[tuple[str, str], dict] = {}
    by_name_set: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_name: dict[str, list[dict]] = defaultdict(list)
    for card in cards:
        stem = (card.get("_stem") or "").casefold()
        image = (card.get("_image") or "").casefold()
        by_image[(card["set"].casefold(), stem)] = card
        if image:
            by_image[(card["set"].casefold(), image)] = card
        by_name_set[(card["name"].casefold(), card["set"].casefold())].append(card)
        by_name[card["name"].casefold()].append(card)
    return {"image": by_image, "name_set": by_name_set, "name": by_name}


def resolve_card(index: dict, name: str, set_name: str, image_id: str) -> dict | None:
    if image_id:
        stem = Path(image_id).stem.casefold()
        hit = index["image"].get((set_name.casefold(), image_id.casefold())) or index["image"].get(
            (set_name.casefold(), stem)
        )
        if hit:
            return hit
    hits = index["name_set"].get((name.casefold(), set_name.casefold()), [])
    if len(hits) == 1:
        return hits[0]
    name_hits = index["name"].get(name.casefold(), [])
    if len(name_hits) == 1:
        return name_hits[0]
    return None


ZONE_TO_GROUP = {
    "Story": "sharedStoryDeck",
    "Deck": "playerNDeck",
    "Domains": "playerNDomains",
}


def convert_decks(cards: list[dict[str, str]]) -> tuple[dict, dict, list[str]]:
    index = build_card_index(cards)
    errors: list[str] = []
    prebuilt: OrderedDict[str, dict] = OrderedDict()
    story_menu: list[dict] = []
    piece_menu: list[dict] = []

    domains = [card for card in cards if card["type"] == "Domain"]
    if domains:
        starter = domains[:3]
        prebuilt["starting-domains"] = {
            "label": "Starting Domains (3)",
            "cards": [
                {"databaseId": card["databaseId"], "quantity": 1, "loadGroupId": "playerNDomains"}
                for card in starter
            ],
        }
        piece_menu.append({"deckListId": "starting-domains", "label": "Starting Domains (3)"})

    for filename, label in STORY_DECKS.items():
        url = ART_ROOT + "decks/" + quote(filename)
        try:
            text = fetch_bytes(url).decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{filename}: download failed ({exc})")
            continue
        deck_id = slug(label)
        entries = []
        for zone_name, rows in parse_dek(text).items():
            load_group = ZONE_TO_GROUP.get(zone_name, "sharedStoryDeck")
            counts: Counter[str] = Counter()
            for name, set_name, image_id in rows:
                card = resolve_card(index, name, set_name, image_id)
                if card is None:
                    errors.append(f"{filename}: unknown card {name!r} [{set_name} {image_id}]")
                    continue
                counts[card["databaseId"]] += 1
            for database_id, quantity in counts.items():
                entries.append({"databaseId": database_id, "quantity": quantity, "loadGroupId": load_group})
        prebuilt[deck_id] = {"label": label, "cards": entries}
        story_menu.append({"deckListId": deck_id, "label": label})

    sub = []
    if story_menu:
        sub.append({"label": "Story Decks", "deckLists": story_menu})
    if piece_menu:
        sub.append({"label": "Starting Pieces", "deckLists": piece_menu})
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
        },
        "sharedStoryDeck": {
            "groupType": "deck",
            "label": "Story Deck",
            "tableLabel": "Story Deck",
            "onCardEnter": {"controller": "shared", "deckGroupId": "sharedStoryDeck"},
        },
        "sharedStories": {
            "groupType": "inPlay",
            "label": "Stories",
            "tableLabel": "Stories",
            "canHaveAttachments": True,
            "onCardEnter": {"controller": "shared", "inPlay": True},
        },
    }
    for n in range(1, MAX_PLAYERS + 1):
        player = f"player{n}"
        for kind, group_type, label, extra in (
            ("Deck", "deck", "Deck", {}),
            ("Discard", "discard", "Discard", {}),
            ("Hand", "hand", "Hand", {}),
            ("Play", "inPlay", "Play", {"canHaveAttachments": True}),
            ("Domains", "inPlay", "Domains", {"canHaveAttachments": True}),
            ("Won", "won", "Won Stories", {}),
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
                "cardSize": 9,
                "rowSpacing": 2,
                "chat": {"left": "74%", "top": "80%", "width": "25%", "height": "19%"},
                "regions": {
                    "playerN+1Hand": region(
                        "playerN+1Hand", "fan", "0%", "0%", "73%", "8%", disableDroppableAttachments=True
                    ),
                    "playerN+1Play": region("playerN+1Play", "free", "0%", "8%", "73%", "17%"),
                    "playerN+1Domains": region("playerN+1Domains", "row", "0%", "25%", "73%", "8%"),
                    "sharedStories": region("sharedStories", "row", "0%", "33%", "73%", "13%"),
                    "playerNDomains": region("playerNDomains", "row", "0%", "46%", "73%", "8%"),
                    "playerNPlay": region("playerNPlay", "free", "0%", "54%", "73%", "20%"),
                    "playerNHand": region(
                        "playerNHand", "fan", "0%", "81%", "55%", "18%", disableDroppableAttachments=True
                    ),
                    "playerN+1Deck": region("playerN+1Deck", "pile", "74%", "8%", "12%", "14%"),
                    "playerN+1Discard": region("playerN+1Discard", "pile", "87%", "8%", "12%", "14%"),
                    "sharedStoryDeck": region("sharedStoryDeck", "pile", "74%", "24%", "12%", "12%"),
                    "sharedSetAside": region("sharedSetAside", "pile", "87%", "24%", "12%", "12%"),
                    "playerN+1Won": region("playerN+1Won", "pile", "74%", "37%", "12%", "10%"),
                    "playerNWon": region("playerNWon", "pile", "87%", "37%", "12%", "10%"),
                    "playerNDeck": region("playerNDeck", "pile", "74%", "57%", "12%", "14%"),
                    "playerNDiscard": region("playerNDiscard", "pile", "87%", "57%", "12%", "14%"),
                },
                "tableButtons": {
                    "drawDeck": {
                        "actionList": "drawDeck",
                        "label": "Draw",
                        "left": "74%",
                        "top": "48%",
                        "width": "12%",
                        "height": "3.2%",
                    },
                    "readyAll": {
                        "actionList": "readyAll",
                        "label": "Refresh",
                        "left": "87%",
                        "top": "48%",
                        "width": "12%",
                        "height": "3.2%",
                    },
                    "drawStory": {
                        "actionList": "drawStory",
                        "label": "Story",
                        "left": "74%",
                        "top": "52%",
                        "width": "12%",
                        "height": "3.2%",
                    },
                    "increaseStories": {
                        "actionList": "increaseStories",
                        "label": "Won +1",
                        "left": "87%",
                        "top": "52%",
                        "width": "12%",
                        "height": "3.2%",
                    },
                },
            }
        }
    }


def download_lobby_art() -> None:
    dest_dir = IMAGES / GAME_FOLDER / "_plugin"
    dest_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        dest_dir / "banner.jpg": ART_ROOT + "images/backgrounds/Cthulhu_background_v4.jpg",
        dest_dir / "logo.jpg": ART_ROOT + "root/bot.jpg",
    }
    for dest, url in mapping.items():
        if dest.exists() and dest.stat().st_size > 0:
            continue
        dest.write_bytes(fetch_bytes(url))


def write_domain_art(cards: list[dict[str, str]]) -> None:
    palette = [
        (18, 42, 38),
        (28, 52, 44),
        (22, 36, 48),
        (36, 28, 44),
        (44, 32, 28),
        (24, 44, 36),
        (32, 28, 40),
        (20, 40, 52),
        (40, 36, 24),
        (30, 30, 34),
    ]
    for index, card in enumerate(card for card in cards if card["type"] == "Domain"):
        rel = card["imageUrl"]
        dest = IMAGES / rel
        write_color_png(dest, palette[index % len(palette)], 360, 504)


def write_plugin_jsons(cards: list[dict[str, str]], decks: dict, menu: dict) -> None:
    jsons = OUT / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    types = sorted({card["type"] for card in cards})
    dump_json(
        jsons / "main.json",
        {
            "pluginName": "Call of Cthulhu LCG",
            "author": "Lackey / Tragic-zz",
            "tutorialUrl": "https://github.com/Tragic-zz/lackey-CoCLCG",
            "announcements": [
                "Tabletop plugin from the Lackey Call of Cthulhu LCG set. No rules engine — Draw, Refresh, story draws, and tokens are shortcuts.",
                "Load a story deck plus Starting Domains from Menu → Load. D = draw. R = refresh all. Y = draw a story. T = exhaust. I = insane. 1/2/3/4 = success / struggle / wound / drain.",
            ],
            "loadPreBuiltOnNewGame": False,
            "backgroundUrl": ART_ROOT + "images/backgrounds/Cthulhu_background_v4.jpg",
        },
    )
    stamp_lobby_art(jsons, GAME_FOLDER)
    dump_json(
        jsons / "announcements.json",
        {
            "announcements": [
                "Call of Cthulhu LCG tabletop: load stories and domains, then play. Rules are reminders, not enforced.",
            ]
        },
    )
    clear_image_url_prefix(jsons)
    dump_json(
        jsons / "cardBacks.json",
        {
            "cardBacks": {
                "default": {
                    "width": 0.72,
                    "height": 1.0,
                    "imageUrl": ART_ROOT + "root/cardback.jpg",
                },
                "spawned": {
                    "width": 0.72,
                    "height": 1.0,
                    "imageUrl": ART_ROOT + "root/spawned.jpg",
                },
            }
        },
    )
    dump_json(
        jsons / "cardTypes.json",
        {
            "cardTypes": {
                name: {"width": 0.72, "height": 1.0, "tokens": ["success", "struggle", "wound", "drain"]}
                for name in types
            }
        },
    )
    dump_json(jsons / "groups.json", build_groups())
    dump_json(jsons / "layouts.json", build_layouts())
    dump_json(
        jsons / "groupTypes.json",
        {
            "groupTypes": {
                "deck": {
                    "canHaveAttachments": False,
                    "canHaveTokens": False,
                    "shuffleOnLoad": True,
                    "onCardEnter": {"currentSide": "B", "inPlay": False, "rotation": 0},
                },
                "discard": {
                    "canHaveAttachments": False,
                    "canHaveTokens": False,
                    "shuffleOnLoad": False,
                    "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0},
                },
                "hand": {
                    "canHaveAttachments": False,
                    "canHaveTokens": False,
                    "shuffleOnLoad": False,
                    "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0},
                },
                "inPlay": {
                    "canHaveAttachments": True,
                    "canHaveTokens": True,
                    "shuffleOnLoad": False,
                    "onCardEnter": {"currentSide": "A", "inPlay": True, "rotation": 0},
                },
                "won": {
                    "canHaveAttachments": False,
                    "canHaveTokens": False,
                    "shuffleOnLoad": False,
                    "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0},
                },
                "aside": {
                    "canHaveAttachments": False,
                    "canHaveTokens": False,
                    "shuffleOnLoad": False,
                    "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0},
                },
            }
        },
    )
    dump_json(
        jsons / "playerCountMenu.json",
        {"playerCountMenu": [{"label": "2", "numPlayers": 2, "layoutId": "default"}]},
    )
    dump_json(
        jsons / "phases.json",
        {
            "phases": {key: {"label": label, "height": "7%"} for key, label in PHASES},
            "phaseOrder": [key for key, _ in PHASES],
        },
    )
    dump_json(
        jsons / "steps.json",
        {
            "steps": {f"{key}Step": {"phaseId": key, "label": label} for key, label in PHASES},
            "stepOrder": [f"{key}Step" for key, _ in PHASES],
        },
    )
    dump_json(
        jsons / "playerProperties.json",
        {
            "playerProperties": {
                "storiesWon": {"label": "Stories", "type": "integer", "default": 0, "min": 0},
            }
        },
    )
    dump_json(jsons / "gameProperties.json", {"gameProperties": {}})
    dump_json(
        jsons / "topBarCounters.json",
        {
            "topBarCounters": {
                "shared": [{"label": "Round", "imageUrl": "", "gameProperty": "roundNumber"}],
                "player": [{"label": "Stories", "imageUrl": "", "playerProperty": "storiesWon"}],
            }
        },
    )
    dump_json(
        jsons / "tokens.json",
        {
            "tokens": {
                "success": {
                    "label": "Success",
                    "left": "80%",
                    "top": "46%",
                    "width": "4vh",
                    "height": "4vh",
                    "imageUrl": ART_ROOT + "images/images/countergreen.png",
                    "canBeNegative": True,
                },
                "struggle": {
                    "label": "Struggle",
                    "left": "18%",
                    "top": "46%",
                    "width": "4vh",
                    "height": "4vh",
                    "imageUrl": ART_ROOT + "images/images/counterred.png",
                    "canBeNegative": True,
                },
                "wound": {
                    "label": "Wound",
                    "left": "48%",
                    "top": "18%",
                    "width": "4vh",
                    "height": "4vh",
                    "imageUrl": ART_ROOT + "images/images/counteryellow.png",
                    "canBeNegative": True,
                },
                "drain": {
                    "label": "Drain",
                    "left": "48%",
                    "top": "48%",
                    "width": "4vh",
                    "height": "4vh",
                    "imageUrl": ART_ROOT + "images/images/counterblue.png",
                    "canBeNegative": True,
                },
            }
        },
    )
    dump_json(
        jsons / "functions.json",
        {
            "functions": {
                "DISCARD": {
                    "args": ["$CARD_ID"],
                    "code": [
                        ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
                        [
                            "COND",
                            ["EQUAL", "$CARD.discardGroupId", None],
                            ["LOG", "{{$ALIAS_N}} failed to discard {{$CARD.currentFace.name}} because it has no discard pile."],
                            ["TRUE"],
                            [
                                ["LOG", "{{$ALIAS_N}} discarded {{$CARD.sides.A.name}}."],
                                ["MOVE_CARD", "$CARD.id", "$CARD.discardGroupId", 0],
                            ],
                        ],
                    ],
                },
                "FLIP": {
                    "args": ["$CARD_ID"],
                    "code": [
                        ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
                        [
                            "COND",
                            ["EQUAL", "$CARD.currentSide", "A"],
                            [
                                ["LOG", "{{$ALIAS_N}} flipped {{$CARD.currentFace.name}} facedown."],
                                ["SET", "/cardById/$CARD.id/currentSide", "B"],
                            ],
                            ["TRUE"],
                            [
                                ["SET", "/cardById/$CARD.id/currentSide", "A"],
                                ["LOG", "{{$ALIAS_N}} flipped {{$CARD.currentFace.name}} faceup."],
                            ],
                        ],
                    ],
                },
                "DETACH": {
                    "args": ["$CARD_ID"],
                    "code": [
                        ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
                        [
                            "COND",
                            ["GREATER_THAN", "$CARD.cardIndex", 0],
                            [
                                ["MOVE_CARD", "$CARD.id", "$CARD.groupId", ["ADD", "$CARD.stackIndex", 1]],
                                ["LOG", "{{$ALIAS_N}} detached {{$CARD.currentFace.name}}."],
                            ],
                        ],
                    ],
                },
                "SHUFFLE_INTO_DECK": {
                    "args": ["$CARD_ID"],
                    "code": [
                        ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
                        ["VAR", "$GROUP_ID", "$CARD.deckGroupId"],
                        [
                            "COND",
                            ["EQUAL", "$GROUP_ID", None],
                            ["LOG", "{{$ALIAS_N}} failed to shuffle {{$CARD.currentFace.name}} into a deck."],
                            ["TRUE"],
                            [
                                ["MOVE_CARD", "$CARD.id", "$CARD.deckGroupId", 0],
                                ["SHUFFLE_GROUP", "$GROUP_ID"],
                                [
                                    "LOG",
                                    "{{$ALIAS_N}} shuffled {{$CARD.currentFace.name}} into {{$GAME.groupById.$GROUP_ID.label}}.",
                                ],
                            ],
                        ],
                    ],
                },
            }
        },
    )
    dump_json(
        jsons / "actionLists.json",
        {
            "actionLists": {
                "drawDeck": [
                    [
                        "COND",
                        ["GROUP_EMPTY", "{{$PLAYER_N}}Deck"],
                        ["LOG", "{{$ALIAS_N}} tried to draw from an empty deck."],
                        ["TRUE"],
                        [
                            ["MOVE_STACKS", "{{$PLAYER_N}}Deck", "{{$PLAYER_N}}Hand", 1, "bottom"],
                            ["LOG", "{{$ALIAS_N}} drew a card."],
                        ],
                    ]
                ],
                "shuffleDeck": [["SHUFFLE_GROUP", "{{$PLAYER_N}}Deck"], ["LOG", "{{$ALIAS_N}} shuffled their deck."]],
                "drawStory": [
                    [
                        "COND",
                        ["GROUP_EMPTY", "sharedStoryDeck"],
                        ["LOG", "{{$ALIAS_N}} tried to draw a story from an empty story deck."],
                        ["TRUE"],
                        [
                            ["MOVE_STACKS", "sharedStoryDeck", "sharedStories", 1, "bottom"],
                            ["LOG", "{{$ALIAS_N}} revealed a story."],
                        ],
                    ]
                ],
                "readyAll": [
                    [
                        "FOR_EACH_KEY_VAL",
                        "$CARD_ID",
                        "$CARD",
                        "$GAME.cardById",
                        [
                            "COND",
                            ["EQUAL", "$CARD.controller", "$PLAYER_N"],
                            ["SET", "/cardById/{{$CARD_ID}}/rotation", 0],
                        ],
                    ],
                    ["LOG", "{{$ALIAS_N}} refreshed all their cards."],
                ],
                "exhaustCard": [
                    ["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 90],
                    ["LOG", "{{$ALIAS_N}} exhausted {{$ACTIVE_FACE.name}}."],
                ],
                "insaneCard": [
                    ["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 180],
                    ["LOG", "{{$ALIAS_N}} drove {{$ACTIVE_FACE.name}} insane."],
                ],
                "readyCard": [
                    ["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 0],
                    ["LOG", "{{$ALIAS_N}} refreshed {{$ACTIVE_FACE.name}}."],
                ],
                "increaseStories": [
                    ["INCREASE_VAL", "/playerData/$PLAYER_N/storiesWon", 1],
                    ["LOG", "{{$ALIAS_N}} won a story."],
                ],
                "decreaseStories": [
                    [
                        "COND",
                        ["GREATER_THAN", "$GAME.playerData.$PLAYER_N.storiesWon", 0],
                        [
                            ["DECREASE_VAL", "/playerData/$PLAYER_N/storiesWon", 1],
                            ["LOG", "{{$ALIAS_N}} lost a story victory."],
                        ],
                        ["TRUE"],
                        ["LOG", "{{$ALIAS_N}} has no story victories to remove."],
                    ]
                ],
                "flipCard": [["FLIP", "$ACTIVE_CARD_ID"]],
                "discardCard": [["DISCARD", "$ACTIVE_CARD_ID"]],
                "detachCard": [["DETACH", "$ACTIVE_CARD_ID"]],
                "shuffleIntoDeck": [["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"]],
                "mulligan": [
                    ["MOVE_STACKS", "{{$PLAYER_N}}Hand", "{{$PLAYER_N}}Deck", 99, "bottom"],
                    ["SHUFFLE_GROUP", "{{$PLAYER_N}}Deck"],
                    ["LOG", "{{$ALIAS_N}} mulliganed (hand to bottom of deck, shuffle)."],
                ],
            }
        },
    )
    dump_json(
        jsons / "hotkeys.json",
        {
            "hotkeys": {
                "game": [
                    {"key": "D", "actionList": "drawDeck", "label": "Draw"},
                    {"key": "S", "actionList": "shuffleDeck", "label": "Shuffle deck"},
                    {"key": "R", "actionList": "readyAll", "label": "Refresh all"},
                    {"key": "Y", "actionList": "drawStory", "label": "Draw story"},
                    {"key": "B", "actionList": "increaseStories", "label": "Story +1"},
                    {"key": "N", "actionList": "decreaseStories", "label": "Story -1"},
                    {"key": "M", "actionList": "mulligan", "label": "Mulligan"},
                ],
                "card": [
                    {"key": "T", "actionList": "exhaustCard", "label": "Exhaust"},
                    {"key": "I", "actionList": "insaneCard", "label": "Insane"},
                    {"key": "K", "actionList": "readyCard", "label": "Refresh"},
                    {"key": "F", "actionList": ["FLIP", "$ACTIVE_CARD_ID"], "label": "Flip"},
                    {"key": "X", "actionList": ["DISCARD", "$ACTIVE_CARD_ID"], "label": "Discard"},
                    {"key": "A", "actionList": ["DETACH", "$ACTIVE_CARD_ID"], "label": "Detach"},
                    {"key": "H", "actionList": ["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"], "label": "Shuffle into deck"},
                ],
                "token": [
                    {"key": "1", "tokenType": "success", "label": "Success token"},
                    {"key": "2", "tokenType": "struggle", "label": "Struggle token"},
                    {"key": "3", "tokenType": "wound", "label": "Wound"},
                    {"key": "4", "tokenType": "drain", "label": "Drain"},
                ],
            }
        },
    )
    dump_json(
        jsons / "pluginMenu.json",
        {
            "pluginMenu": {
                "options": [
                    {"label": "Draw", "actionList": "drawDeck"},
                    {"label": "Shuffle deck", "actionList": "shuffleDeck"},
                    {"label": "Refresh all", "actionList": "readyAll"},
                    {"label": "Draw story", "actionList": "drawStory"},
                    {"label": "Story +1", "actionList": "increaseStories"},
                    {"label": "Story -1", "actionList": "decreaseStories"},
                    {"label": "Mulligan", "actionList": "mulligan"},
                ]
            }
        },
    )
    dump_json(
        jsons / "cardMenu.json",
        {
            "cardMenu": {
                "moveToGroupIds": MOVE_GROUPS,
                "options": [
                    {"label": "Exhaust", "actionList": "exhaustCard"},
                    {"label": "Insane", "actionList": "insaneCard"},
                    {"label": "Refresh", "actionList": "readyCard"},
                    {"label": "Flip", "actionList": "flipCard"},
                    {"label": "Discard", "actionList": "discardCard"},
                    {"label": "Detach", "actionList": "detachCard"},
                    {"label": "Shuffle into deck", "actionList": "shuffleIntoDeck"},
                ],
            }
        },
    )
    dump_json(jsons / "groupMenu.json", {"groupMenu": {"moveToGroupIds": MOVE_GROUPS, "options": []}})
    dump_json(
        jsons / "browse.json",
        {
            "browse": {
                "filterPropertySideA": "type",
                "filterValuesSideA": types,
                "textPropertiesSideA": ["name", "faction", "subtype", "text", "packName"],
            }
        },
    )
    dump_json(
        jsons / "deckbuilder.json",
        {
            "deckbuilder": {
                "addButtons": [1, 2, 3],
                "columns": [
                    {"propName": "name", "label": "Name"},
                    {"propName": "type", "label": "Type"},
                    {"propName": "faction", "label": "Faction"},
                    {"propName": "cost", "label": "Cost"},
                    {"propName": "skill", "label": "Skill"},
                    {"propName": "terror", "label": "T"},
                    {"propName": "combat", "label": "C"},
                    {"propName": "arcane", "label": "A"},
                    {"propName": "investigation", "label": "I"},
                    {"propName": "packName", "label": "Set"},
                ],
                "spawnGroups": [
                    {"loadGroupId": "playerNDeck", "label": "My Deck"},
                    {"loadGroupId": "playerNDomains", "label": "My Domains"},
                    {"loadGroupId": "sharedStoryDeck", "label": "Story Deck"},
                ],
            }
        },
    )
    dump_json(
        jsons / "spawnExistingCardModal.json",
        {
            "spawnExistingCardModal": {
                "columnProperties": ["name", "type", "faction", "cost", "packName"],
                "loadGroupIds": [
                    "player1Deck",
                    "player1Play",
                    "player1Hand",
                    "player1Domains",
                    "sharedStories",
                    "sharedStoryDeck",
                    "sharedSetAside",
                    "player2Deck",
                    "player2Play",
                    "player2Domains",
                ],
            }
        },
    )
    dump_json(
        jsons / "faceProperties.json",
        {
            "faceProperties": {
                "subtype": {"label": "Subtype", "type": "string", "default": ""},
                "faction": {"label": "Faction", "type": "string", "default": ""},
                "unique": {"label": "Unique", "type": "string", "default": ""},
                "cost": {"label": "Cost", "type": "string", "default": ""},
                "terror": {"label": "Terror", "type": "string", "default": ""},
                "combat": {"label": "Combat", "type": "string", "default": ""},
                "arcane": {"label": "Arcane", "type": "string", "default": ""},
                "investigation": {"label": "Investigation", "type": "string", "default": ""},
                "skill": {"label": "Skill", "type": "string", "default": ""},
                "text": {"label": "Text", "type": "string", "default": ""},
                "errata": {"label": "Errata", "type": "string", "default": ""},
                "restricted": {"label": "Restricted", "type": "string", "default": ""},
                "cycle": {"label": "Cycle", "type": "string", "default": ""},
                "packName": {"label": "Set", "type": "string", "default": ""},
                "set": {"label": "Lackey Set", "type": "string", "default": ""},
                "edition": {"label": "Edition", "type": "string", "default": ""},
                "loadGroupId": {"label": "Load Group", "type": "string", "default": ""},
            }
        },
    )
    dump_json(jsons / "cardProperties.json", {"cardProperties": {}})
    dump_json(jsons / "defaultActions.json", {"defaultActions": []})
    dump_json(
        jsons / "automation.json",
        {
            "automation": {
                "postNewGameActionList": [
                    [
                        "LOG",
                        "Call of Cthulhu LCG table created. Load stories and domains from Menu → Load. No rules are enforced.",
                    ]
                ],
                "gameRules": {},
            }
        },
    )
    dump_json(jsons / "labels.json", {"labels": {}})
    dump_json(jsons / "preferences.json", {"preferences": {"game": [], "player": []}})
    dump_json(jsons / "prompts.json", {"prompts": {}})
    dump_json(jsons / "touchBar.json", {"touchBar": []})
    dump_json(jsons / "closeRoomOptions.json", {"closeRoomOptions": [{"label": "Just close", "actionList": []}]})
    dump_json(
        jsons / "clearTableOptions.json",
        {
            "clearTableOptions": [
                {"label": "Player 1 wins", "actionList": ["SET", "/victoryState", "player1Win"]},
                {"label": "Player 2 wins", "actionList": ["SET", "/victoryState", "player2Win"]},
                {"label": "Tie", "actionList": ["SET", "/victoryState", "tie"]},
                {"label": "Incomplete", "actionList": ["SET", "/victoryState", "incomplete"]},
            ]
        },
    )
    dump_json(jsons / "preBuiltDecks.json", decks)
    dump_json(jsons / "deckMenu.json", menu)


def main() -> int:
    if not (LACKEY / "sets" / "CardDataFile.txt").exists():
        raise SystemExit(f"Lackey plugin not found: {LACKEY}")
    cards, errors = load_cards()
    (OUT / "tsvs").mkdir(parents=True, exist_ok=True)
    write_domain_art(cards)
    write_tsv(cards, OUT / "tsvs" / "cards.tsv")
    decks, menu, deck_errors = convert_decks(cards)
    errors.extend(deck_errors)
    download_lobby_art()
    write_plugin_jsons(cards, decks, menu)
    missing_urls = sum(1 for card in cards if not card["imageUrl"])
    (OUT / "SOURCE.txt").write_text(
        "\n".join(
            [
                f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from LackeyCCG CoC_LCG.",
                f"Source: {LACKEY}",
                "Art: GitHub Tragic-zz/lackey-CoCLCG raw cards/ (localized to Toybox).",
                "Author credit: Lackey / Tragic-zz",
                "",
                "Tabletop plugin only — Lackey has no rules engine to port.",
                f"TSV rows: {len(cards)}  missing image URLs: {missing_urls}",
                f"Prebuilts: {len(decks['preBuiltDecks'])} story decks + starting domains.",
                "Domain markers are not in the Lackey GitHub dump; those ten faces are generated locally.",
                "Lobby banner is the Lackey Cthulhu table background; logo is bot.jpg.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUT.name}")
    print("  pluginName: Call of Cthulhu LCG")
    print(f"  tsv rows: {len(cards)}  missing urls: {missing_urls}")
    print(f"  prebuilt decks: {len(decks['preBuiltDecks'])}")
    print(f"  types: {', '.join(sorted({card['type'] for card in cards}))}")
    if errors:
        print(f"\n{len(errors)} issue(s):")
        for err in errors[:40]:
            print(f"  - {err}")
        if len(errors) > 40:
            print(f"  … {len(errors) - 40} more")
        return 1
    print()
    print("Next:")
    print("  python3 plugins/scripts/collect_hosted_images.py call-of-cthulhu-lcg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
