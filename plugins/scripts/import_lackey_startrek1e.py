#!/usr/bin/env python3
"""Build a DragnCards Star Trek CCG 1E plugin from the LackeyCCG plugin.

  python3 plugins/scripts/import_lackey_startrek1e.py
  python3 plugins/scripts/collect_hosted_images.py star-trek-ccg-1e
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
from image_names import TOYBOX_PREFIX, plugin_art_rel, stamp_lobby_art, toybox_url  # noqa: E402

LACKEY = Path("/Applications/LackeyCCG/plugins/startrek1e")
OUT = ROOT / "star-trek-ccg-1e"
GAME_FOLDER = "star-trek-ccg-1e"
IMAGES = ROOT / "images"
IMAGE_BASE = "https://raw.githubusercontent.com/eberlems/startrek1e/playable/sets/setimages/general/"
ART_ROOT = "https://raw.githubusercontent.com/eberlems/startrek1e/playable/"
MAX_PLAYERS = 2
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

CARD_FILES = ["Physical.txt", "Virtual.txt", "Rework.txt", "Overlays.txt"]

SET_LABELS = {
    "PR": "Premiere",
    "PT": "Premiere Traditional",
    "au": "Alternate Universe",
    "AU": "Alternate Universe",
    "qc": "Q-Continuum",
    "ds9": "Deep Space Nine",
    "voy": "Voyager",
    "fc": "First Contact",
    "tmp": "The Motion Pictures",
    "TMPR": "The Motion Pictures Remastered",
    "borg": "The Borg",
    "twt": "The Trouble With Tribbles",
    "ha": "Holodeck Adventures",
    "dom": "The Dominion",
    "mm": "Mirror, Mirror",
    "roa": "Rules of Acquisition",
    "bog": "Blaze of Glory",
    "SE": "Starter Deck II",
    "VP": "Virtual Promos",
    "Ref": "Referee",
    "TNG": "The Next Generation",
    "TNG+": "The Next Generation",
    "En": "Enhanced Premiere",
    "brokenbow": "Broken Bow",
    "CA": "Coming Attractions",
    "Emissary": "Emissary",
    "Emissary+": "Emissary",
    "crossovers": "Crossover",
    "crossover": "Crossover",
    "llap": "Live Long and Prosper",
    "terran": "The Terran Empire",
    "metamorpho": "Metamorphosis",
    "Cage": "The Cage",
    "Maquis": "The Maquis",
    "dow": "Dogs of War",
    "SaS": "Straight and Steady",
    "lfl": "Life From Lifelessness",
    "tgq": "The Gamma Quadrant",
    "coldfront": "Cold Front",
    "SoG": "The Sky's the Limit",
    "ENGAGE": "Engage",
    "tstl": "These Are The Voyages",
    "tnz": "The Neutral Zone",
    "NEM": "Nemesis",
    "lookinggla": "Through the Looking Glass",
    "NE": "Necessary Evil",
    "BG": "The Borg",
    "HF2": "Homefront II",
    "HF6": "Homefront VI",
    "plw": "Homefront",
    "CL": "Captain's Log",
    "20th": "20th Anniversary",
    "BP": "Borderless Promos",
    "PreWarp": "Pre-Warp",
    "FCE": "First Contact",
    "IC": "In a Mirror, Darkly",
    "SotL": "The Sky's the Limit",
}

AFFIL_ICONS = {
    "[FED]": "Federation",
    "[KLI]": "Klingon",
    "[ROM]": "Romulan",
    "[CAR]": "Cardassian",
    "[BAJ]": "Bajoran",
    "[DOM]": "Dominion",
    "[FER]": "Ferengi",
    "[BOR]": "Borg",
    "[STA]": "Starfleet",
    "[VUL]": "Vulcan",
    "[HIR]": "Hirogen",
    "[KAZ]": "Kazon",
}

DECK_ZONES = {
    "Deck": "playerNDeck",
    "Missions": "playerNMissions",
    "Seed+Dil": "playerNSeed",
    "QsTent": "playerNTent",
    "Ref": "playerNRef",
    "Dyson": "playerNDyson",
    "Flash": "playerNFlash",
    "Tactics": "playerNTactics",
    "Tribbles": "playerNTribbles",
    "Sites": "playerNSites",
    "Outside": "playerNRemoved",
    "Aside": "playerNAside",
}

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "missionType",
    "affiliation",
    "classification",
    "integrity",
    "cunning",
    "strength",
    "points",
    "span",
    "quadrant",
    "region",
    "icons",
    "uniqueness",
    "keywords",
    "text",
    "lore",
    "rarity",
    "property",
    "packName",
    "set",
    "printing",
    "loadGroupId",
]

MOVE_GROUPS = [
    "playerNHand",
    "playerNDeck",
    "playerNDiscard",
    "playerNPlay",
    "playerNSeed",
    "playerNMissions",
    "playerNSites",
    "playerNTent",
    "playerNTactics",
    "playerNRemoved",
    "playerN+1Play",
    "sharedSpaceline",
    "sharedSetAside",
]


def dump_json(path: Path, payload: dict | list) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sanitize(value: str) -> str:
    return (value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "deck"


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


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read()


def card_image_url(image_file: str) -> str:
    image_file = sanitize(image_file)
    if not image_file:
        return ""
    name = Path(image_file).name
    if "." not in name:
        image_file = f"{image_file}.jpg"
    return IMAGE_BASE + quote(image_file, safe="-_.")


def pack_label(release: str) -> str:
    release = sanitize(release)
    if release in SET_LABELS:
        return SET_LABELS[release]
    cleaned = re.sub(r"[_+]+", " ", release).strip()
    if cleaned.isupper() and len(cleaned) <= 5:
        return cleaned
    return cleaned[:1].upper() + cleaned[1:] if cleaned else "Unknown"


def normalize_affiliation(value: str) -> str:
    value = sanitize(value)
    if not value:
        return ""
    if value.startswith("Any "):
        return value
    icons = re.findall(r"\[[A-Za-z0-9-]+\]", value)
    if icons and value.replace("".join(icons), "").strip() == "":
        mapped = [AFFIL_ICONS.get(icon, icon) for icon in icons]
        return "/".join(dict.fromkeys(mapped))
    return value


def load_group(card_type: str) -> str:
    if card_type in {"Mission", "Time Location", "Q Mission"}:
        return "playerNMissions"
    if card_type == "Site":
        return "playerNSites"
    if card_type in {"Dilemma", "Q Dilemma"}:
        return "playerNSeed"
    if card_type in {"Tactic", "Trouble", "Damage Marker"}:
        return "playerNTactics"
    if card_type == "Tribble":
        return "playerNTribbles"
    if card_type in {"Q Event", "Q Interrupt", "Q Artifact"}:
        return "playerNFlash"
    if card_type in {"Doorway", "Incident", "Objective", "Artifact"}:
        return "playerNSeed"
    if card_type in {"Overlay", "Facility"}:
        return "playerNAside" if card_type == "Overlay" else "playerNSeed"
    return "playerNDeck"


def parse_faces(image_file: str) -> tuple[str, str]:
    parts = [sanitize(part) for part in (image_file or "").split(",")]
    front = parts[0] if parts else ""
    back = parts[1] if len(parts) > 1 else ""
    return front, back


def load_cards() -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    raw: list[dict[str, str]] = []
    seen: set[str] = set()
    for fname in CARD_FILES:
        path = LACKEY / "sets" / fname
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        header = [h.strip() for h in lines[0].split("\t")]
        if header[:3] != ["Name", "Set", "ImageFile"]:
            errors.append(f"{fname}: unexpected header {header[:8]}")
        printing = fname.rsplit(".", 1)[0]
        for line_no, line in enumerate(lines[1:], start=2):
            if not line.strip():
                continue
            cols = line.split("\t")
            while len(cols) < 28:
                cols.append("")
            name = sanitize(cols[0])
            image_file = sanitize(cols[2])
            if not name or not image_file or image_file.lower() == "renamed":
                continue
            card_type = sanitize(cols[7]) or ("Overlay" if printing == "Overlays" else "Unknown")
            front, back = parse_faces(image_file)
            if not front:
                errors.append(f"{fname}:{line_no} missing ImageFile")
                continue
            release = sanitize(cols[3])
            stem = Path(front).stem
            database_id = f"{release or printing}_{stem}"
            if database_id in seen:
                database_id = f"{database_id}_{slug(name)}"
            if database_id in seen:
                errors.append(f"Duplicate {database_id} at {fname}:{line_no}")
                continue
            seen.add(database_id)
            raw.append(
                {
                    "databaseId": database_id,
                    "name": name,
                    "imageUrl": card_image_url(front),
                    "cardBack": "default",
                    "type": card_type,
                    "missionType": sanitize(cols[8]),
                    "affiliation": normalize_affiliation(cols[9]),
                    "classification": sanitize(cols[10]),
                    "integrity": sanitize(cols[11]),
                    "cunning": sanitize(cols[12]),
                    "strength": sanitize(cols[13]),
                    "points": sanitize(cols[14]),
                    "span": sanitize(cols[17]),
                    "quadrant": sanitize(cols[16]),
                    "region": sanitize(cols[15]),
                    "icons": sanitize(cols[18]),
                    "uniqueness": sanitize(cols[6]),
                    "keywords": sanitize(cols[20]),
                    "text": sanitize(cols[27]),
                    "lore": sanitize(cols[24]),
                    "rarity": sanitize(cols[4]),
                    "property": sanitize(cols[5]),
                    "packName": pack_label(release),
                    "set": release or printing,
                    "printing": printing,
                    "loadGroupId": load_group(card_type),
                    "_back_stem": back,
                    "_front_stem": front,
                }
            )

    by_name = {card["name"]: card for card in raw}
    cards: list[dict[str, str]] = []
    skipped_backs = 0
    for card in raw:
        if card["name"].endswith(" (back)"):
            skipped_backs += 1
            continue
        back_name = f"{card['name']} (back)"
        back_card = by_name.get(back_name)
        back_stem = card.get("_back_stem") or ""
        if back_card:
            back_stem = back_card.get("_front_stem") or back_stem
        if back_stem:
            face_a = {key: card[key] for key in TSV_COLUMNS}
            face_a["cardBack"] = "multi_sided"
            face_b = {key: (back_card or card)[key] for key in TSV_COLUMNS}
            face_b["databaseId"] = card["databaseId"]
            face_b["name"] = back_card["name"] if back_card else f"{card['name']} (back)"
            face_b["imageUrl"] = card_image_url(back_stem)
            face_b["cardBack"] = "default"
            face_b["type"] = card["type"]
            face_b["loadGroupId"] = card["loadGroupId"]
            cards.append(face_a)
            cards.append(face_b)
        else:
            cards.append({key: card[key] for key in TSV_COLUMNS})
    if skipped_backs:
        print(f"  paired {skipped_backs} dual-faced backs")
    return cards, errors


def write_tsv(cards: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["\t".join(TSV_COLUMNS)]
    rows.extend("\t".join(sanitize(card.get(col, "")) for col in TSV_COLUMNS) for card in cards)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def parse_deck_txt(path: Path) -> dict[str, Counter]:
    zones: dict[str, Counter] = defaultdict(Counter)
    current = "Deck"
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.endswith(":") and "\t" not in line:
            label = line[:-1]
            current = label if label in DECK_ZONES else "Deck"
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        try:
            quantity = int(parts[0].strip())
        except ValueError:
            continue
        name = sanitize(parts[1])
        if name and quantity:
            zones[current][name] += quantity
    return zones


def build_card_index(cards: list[dict[str, str]]) -> dict:
    faces = [card for card in cards if not card["name"].endswith(" (back)")]
    exact: dict[str, list[dict]] = defaultdict(list)
    fold: dict[str, list[dict]] = defaultdict(list)
    stripped: dict[str, list[dict]] = defaultdict(list)
    for card in faces:
        if card["name"].endswith(" (back)"):
            continue
        exact[card["name"]].append(card)
        fold[card["name"].casefold()].append(card)
        stripped[card["name"].rstrip("*").casefold()].append(card)
    return {"exact": exact, "fold": fold, "stripped": stripped, "playable": faces}


def name_matches(card_name: str, query: str) -> bool:
    card_name = card_name.rstrip("*").strip()
    query = query.rstrip("*").strip()
    if card_name.casefold() == query.casefold():
        return True
    return card_name.casefold().startswith(query.casefold() + " (")


def pick_best(hits: list[dict]) -> dict:
    def score(card: dict) -> tuple:
        name = card["name"]
        return (
            0 if "2E" in name else 1,
            1 if "Remastered" in name else 0,
            0 if "Traditional" in name else 1,
            ["Overlays", "Rework", "Virtual", "Physical"].index(card.get("printing", "Rework")),
        )

    return max(hits, key=score)


def resolve_card(index: dict, name: str) -> dict | None:
    hits = index["exact"].get(name) or index["fold"].get(name.casefold())
    if not hits:
        hits = index["stripped"].get(name.rstrip("*").casefold())
    if not hits:
        hits = [card for card in index["playable"] if name_matches(card["name"], name)]
    if not hits:
        return None
    return pick_best(hits)


def deck_label(filename: str) -> str:
    stem = Path(filename).stem
    return stem.replace("_", " ").replace("-", " ").strip().title()


def deck_bucket(filename: str) -> str:
    stem = Path(filename).stem.lower()
    if stem.startswith("simple-"):
        return "Simple Decks"
    if "showdown" in stem or "four_lights" in stem:
        return "Showdown"
    if "coa" in stem:
        return "TNG Continuity of Action"
    if stem.startswith("tng_"):
        return "TNG Starters"
    return "Other"


def convert_decks(cards: list[dict[str, str]]) -> tuple[dict, dict, list[str]]:
    index = build_card_index(cards)
    errors: list[str] = []
    prebuilt: OrderedDict[str, dict] = OrderedDict()
    buckets: dict[str, list[dict]] = OrderedDict()
    used_ids: dict[str, int] = {}
    for dek in sorted((LACKEY / "decks").glob("*.txt")):
        label = deck_label(dek.name)
        deck_id = slug(label)
        used_ids[deck_id] = used_ids.get(deck_id, 0) + 1
        if used_ids[deck_id] > 1:
            deck_id = f"{deck_id}-{used_ids[deck_id]}"
        entries = []
        for zone_name, counts in parse_deck_txt(dek).items():
            load_group = DECK_ZONES.get(zone_name, "playerNDeck")
            for name, quantity in counts.items():
                card = resolve_card(index, name)
                if card is None:
                    errors.append(f"{dek.name}: unknown card {name!r}")
                    continue
                entries.append(
                    {"databaseId": card["databaseId"], "quantity": quantity, "loadGroupId": load_group}
                )
        prebuilt[deck_id] = {"label": label, "cards": entries}
        buckets.setdefault(deck_bucket(dek.name), []).append({"deckListId": deck_id, "label": label})
    order = ["Simple Decks", "TNG Starters", "TNG Continuity of Action", "Showdown", "Other"]
    sub = [{"label": name, "deckLists": buckets[name]} for name in order if name in buckets]
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
        "sharedSpaceline": {
            "groupType": "spaceline",
            "label": "Spaceline",
            "tableLabel": "Spaceline",
            "canHaveAttachments": True,
            "onCardEnter": {"controller": "shared", "inPlay": True, "currentSide": "A"},
        },
    }
    player_kinds = (
        ("Deck", "deck", "Deck", {}),
        ("Discard", "discard", "Discard", {}),
        ("Hand", "hand", "Hand", {}),
        ("Play", "inPlay", "Play", {"canHaveAttachments": True}),
        ("Seed", "aside", "Seed", {}),
        ("Missions", "aside", "Missions", {}),
        ("Sites", "aside", "Sites", {}),
        ("Tent", "aside", "Q's Tent", {}),
        ("Flash", "deck", "Q-Flash", {}),
        ("Tactics", "deck", "Battle Bridge", {}),
        ("Tribbles", "deck", "Tribbles", {}),
        ("Dyson", "aside", "Dyson Sphere", {}),
        ("Ref", "aside", "Ref", {}),
        ("Removed", "discard", "Removed", {}),
        ("Aside", "aside", "Aside", {}),
    )
    for n in range(1, MAX_PLAYERS + 1):
        player = f"player{n}"
        for kind, group_type, label, extra in player_kinds:
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
                "cardSize": 8,
                "rowSpacing": 2,
                "chat": {"left": "73%", "top": "80%", "width": "26%", "height": "19%"},
                "regions": {
                    "playerN+1Hand": region(
                        "playerN+1Hand", "fan", "0%", "0%", "72%", "9%", disableDroppableAttachments=True
                    ),
                    "playerN+1Play": region("playerN+1Play", "free", "0%", "9%", "72%", "17%"),
                    "sharedSpaceline": region("sharedSpaceline", "row", "0%", "26%", "72%", "18%"),
                    "playerNPlay": region("playerNPlay", "free", "0%", "44%", "72%", "21%"),
                    "playerNHand": region(
                        "playerNHand", "fan", "0%", "82%", "50%", "17%", disableDroppableAttachments=True
                    ),
                    "playerN+1Deck": region("playerN+1Deck", "pile", "73%", "9%", "8%", "12%"),
                    "playerN+1Discard": region("playerN+1Discard", "pile", "82%", "9%", "8%", "12%"),
                    "playerN+1Seed": region("playerN+1Seed", "pile", "91%", "9%", "8%", "12%"),
                    "playerN+1Missions": region("playerN+1Missions", "pile", "73%", "22%", "8%", "10%"),
                    "playerN+1Tactics": region("playerN+1Tactics", "pile", "82%", "22%", "8%", "10%"),
                    "playerN+1Tent": region("playerN+1Tent", "pile", "91%", "22%", "8%", "10%"),
                    "sharedSetAside": region("sharedSetAside", "pile", "73%", "33%", "8%", "9%"),
                    "playerNSites": region("playerNSites", "pile", "82%", "33%", "8%", "9%"),
                    "playerNFlash": region("playerNFlash", "pile", "91%", "33%", "8%", "9%"),
                    "playerNDeck": region("playerNDeck", "pile", "73%", "55%", "8%", "12%"),
                    "playerNDiscard": region("playerNDiscard", "pile", "82%", "55%", "8%", "12%"),
                    "playerNSeed": region("playerNSeed", "pile", "91%", "55%", "8%", "12%"),
                    "playerNMissions": region("playerNMissions", "pile", "73%", "68%", "8%", "10%"),
                    "playerNTactics": region("playerNTactics", "pile", "82%", "68%", "8%", "10%"),
                    "playerNTent": region("playerNTent", "pile", "91%", "68%", "8%", "10%"),
                },
                "tableButtons": {
                    "drawDeck": {
                        "actionList": "drawDeck",
                        "label": "Draw",
                        "left": "73%",
                        "top": "43%",
                        "width": "8%",
                        "height": "3.2%",
                    },
                    "probeDeck": {
                        "actionList": "probeDeck",
                        "label": "Probe",
                        "left": "82%",
                        "top": "43%",
                        "width": "8%",
                        "height": "3.2%",
                    },
                    "seedSpaceline": {
                        "actionList": "seedSpaceline",
                        "label": "Seed Line",
                        "left": "91%",
                        "top": "43%",
                        "width": "8%",
                        "height": "3.2%",
                    },
                    "discardDeck": {
                        "actionList": "discardFromDeck",
                        "label": "Mill",
                        "left": "73%",
                        "top": "47%",
                        "width": "8%",
                        "height": "3.2%",
                    },
                    "increasePoints": {
                        "actionList": "increasePoints",
                        "label": "Pts +5",
                        "left": "82%",
                        "top": "47%",
                        "width": "8%",
                        "height": "3.2%",
                    },
                    "decreasePoints": {
                        "actionList": "decreasePoints",
                        "label": "Pts -5",
                        "left": "91%",
                        "top": "47%",
                        "width": "8%",
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
        dest_dir / "banner.jpg": ART_ROOT + "Lackey/images/backgrounds/startrek_table.jpg",
        dest_dir / "logo.jpg": ART_ROOT + "Lackey/images/avatars/bot.jpg",
    }
    for dest, url in mapping.items():
        if dest.exists() and dest.stat().st_size > 0:
            continue
        dest.write_bytes(fetch_bytes(url))
    write_color_png(IMAGES / plugin_art_rel(GAME_FOLDER, "StarTrekCcg1e", "token-countdown", ".png"), (46, 184, 72))


def write_plugin_jsons(cards: list[dict[str, str]], decks: dict, menu: dict) -> None:
    jsons = OUT / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    types = sorted({card["type"] for card in cards if card["type"]})
    dump_json(
        jsons / "main.json",
        {
            "pluginName": "Star Trek CCG 1E",
            "author": "Lackey / eberlems",
            "tutorialUrl": "https://github.com/eberlems/startrek1e",
            "announcements": [
                "Tabletop plugin from the Lackey Star Trek CCG 1E set. No rules engine — Draw, Probe, Seed Line, and tokens are shortcuts.",
                "Missions snap onto the shared spaceline (center row). Attach ships and personnel underneath a mission. D = draw. Y = probe. L = seed missions onto the line. 1/2/3 = yellow / countdown / black.",
            ],
            "loadPreBuiltOnNewGame": False,
            "backgroundUrl": ART_ROOT + "Lackey/images/backgrounds/startrek_table.jpg",
        },
    )
    stamp_lobby_art(jsons, GAME_FOLDER)
    dump_json(
        jsons / "announcements.json",
        {
            "announcements": [
                "Star Trek CCG 1E tabletop: load a deck, seed missions onto the spaceline, then play. Rules are reminders, not enforced.",
            ]
        },
    )
    dump_json(jsons / "imageUrlPrefix.json", {"imageUrlPrefix": {"Default": TOYBOX_PREFIX}})
    dump_json(
        jsons / "cardBacks.json",
        {
            "cardBacks": {
                "default": {
                    "width": 0.72,
                    "height": 1.0,
                    "imageUrl": ART_ROOT + "sets/setimages/general/cardback.jpg",
                },
                "spawned": {
                    "width": 0.72,
                    "height": 1.0,
                    "imageUrl": ART_ROOT + "sets/setimages/general/spawned.jpg",
                },
            }
        },
    )
    dump_json(
        jsons / "cardTypes.json",
        {
            "cardTypes": {
                name: {"width": 0.72, "height": 1.0, "tokens": ["yellow", "countdown", "black"]}
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
                "spaceline": {
                    "canHaveAttachments": True,
                    "canHaveTokens": True,
                    "shuffleOnLoad": False,
                    "onCardEnter": {"currentSide": "A", "inPlay": True, "rotation": 0},
                },
                "aside": {
                    "canHaveAttachments": False,
                    "canHaveTokens": False,
                    "shuffleOnLoad": False,
                    "onCardEnter": {"currentSide": "B", "inPlay": False, "rotation": 0},
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
            "phases": {
                "play": {"label": "Play", "height": "34%"},
                "order": {"label": "Execute Orders", "height": "33%"},
                "draw": {"label": "Draw", "height": "33%"},
            },
            "phaseOrder": ["play", "order", "draw"],
        },
    )
    dump_json(
        jsons / "steps.json",
        {
            "steps": {
                "playStep": {"phaseId": "play", "label": "Play"},
                "orderStep": {"phaseId": "order", "label": "Execute Orders"},
                "drawStep": {"phaseId": "draw", "label": "Draw"},
            },
            "stepOrder": ["playStep", "orderStep", "drawStep"],
        },
    )
    dump_json(
        jsons / "playerProperties.json",
        {"playerProperties": {"points": {"label": "Points", "type": "integer", "default": 0, "min": 0}}},
    )
    dump_json(jsons / "gameProperties.json", {"gameProperties": {}})
    dump_json(
        jsons / "topBarCounters.json",
        {
            "topBarCounters": {
                "shared": [{"label": "Round", "imageUrl": "", "gameProperty": "roundNumber"}],
                "player": [{"label": "Pts", "imageUrl": "", "playerProperty": "points"}],
            }
        },
    )
    dump_json(
        jsons / "tokens.json",
        {
            "tokens": {
                "yellow": {
                    "label": "Yellow",
                    "left": "48%",
                    "top": "6%",
                    "width": "4vh",
                    "height": "4vh",
                    "imageUrl": ART_ROOT + "images/counteryellow.png",
                    "canBeNegative": True,
                },
                "countdown": {
                    "label": "Countdown",
                    "left": "10%",
                    "top": "46%",
                    "width": "4vh",
                    "height": "4vh",
                    "imageUrl": toybox_url(plugin_art_rel(GAME_FOLDER, "StarTrekCcg1e", "token-countdown", ".png")),
                    "canBeNegative": True,
                },
                "black": {
                    "label": "Black",
                    "left": "86%",
                    "top": "86%",
                    "width": "4vh",
                    "height": "4vh",
                    "imageUrl": ART_ROOT + "images/counterblack.png",
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
                                ["LOG", "{{$ALIAS_N}} flipped {{$CARD.currentFace.name}}."],
                                ["SET", "/cardById/$CARD.id/currentSide", "B"],
                            ],
                            ["TRUE"],
                            [
                                ["SET", "/cardById/$CARD.id/currentSide", "A"],
                                ["LOG", "{{$ALIAS_N}} flipped {{$CARD.currentFace.name}}."],
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
                "probeDeck": [
                    [
                        "COND",
                        ["GROUP_EMPTY", "{{$PLAYER_N}}Deck"],
                        ["LOG", "{{$ALIAS_N}} tried to probe an empty deck."],
                        ["TRUE"],
                        [
                            ["MOVE_STACKS", "{{$PLAYER_N}}Deck", "{{$PLAYER_N}}Play", 1, "bottom"],
                            ["LOG", "{{$ALIAS_N}} probed."],
                        ],
                    ]
                ],
                "discardFromDeck": [
                    [
                        "COND",
                        ["GROUP_EMPTY", "{{$PLAYER_N}}Deck"],
                        ["LOG", "{{$ALIAS_N}} tried to discard from an empty deck."],
                        ["TRUE"],
                        [
                            ["MOVE_STACKS", "{{$PLAYER_N}}Deck", "{{$PLAYER_N}}Discard", 1, "bottom"],
                            ["LOG", "{{$ALIAS_N}} discarded from deck."],
                        ],
                    ]
                ],
                "seedSpaceline": [
                    [
                        "COND",
                        ["GROUP_EMPTY", "{{$PLAYER_N}}Missions"],
                        ["LOG", "{{$ALIAS_N}} has no missions to seed."],
                        ["TRUE"],
                        [
                            ["MOVE_STACKS", "{{$PLAYER_N}}Missions", "sharedSpaceline", 99, "bottom"],
                            ["LOG", "{{$ALIAS_N}} seeded missions onto the spaceline."],
                        ],
                    ]
                ],
                "increasePoints": [
                    ["INCREASE_VAL", "/playerData/$PLAYER_N/points", 5],
                    ["LOG", "{{$ALIAS_N}} scored 5 points."],
                ],
                "decreasePoints": [
                    [
                        "COND",
                        ["GREATER_THAN", "$GAME.playerData.$PLAYER_N.points", 0],
                        [
                            ["DECREASE_VAL", "/playerData/$PLAYER_N/points", 5],
                            ["LOG", "{{$ALIAS_N}} lost 5 points."],
                        ],
                        ["TRUE"],
                        ["LOG", "{{$ALIAS_N}} has no points to lose."],
                    ]
                ],
                "rotate90": [
                    ["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 90],
                    ["LOG", "{{$ALIAS_N}} rotated {{$ACTIVE_FACE.name}}."],
                ],
                "rotate180": [
                    ["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 180],
                    ["LOG", "{{$ALIAS_N}} rotated {{$ACTIVE_FACE.name}} 180."],
                ],
                "readyCard": [
                    ["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 0],
                    ["LOG", "{{$ALIAS_N}} straightened {{$ACTIVE_FACE.name}}."],
                ],
                "moveToSpaceline": [
                    ["MOVE_CARD", "$ACTIVE_CARD_ID", "sharedSpaceline", -1],
                    ["LOG", "{{$ALIAS_N}} put {{$ACTIVE_FACE.name}} on the spaceline."],
                ],
                "flipCard": [["FLIP", "$ACTIVE_CARD_ID"]],
                "discardCard": [["DISCARD", "$ACTIVE_CARD_ID"]],
                "detachCard": [["DETACH", "$ACTIVE_CARD_ID"]],
                "shuffleIntoDeck": [["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"]],
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
                    {"key": "Y", "actionList": "probeDeck", "label": "Probe"},
                    {"key": "L", "actionList": "seedSpaceline", "label": "Seed spaceline"},
                    {"key": "B", "actionList": "increasePoints", "label": "Points +5"},
                    {"key": "N", "actionList": "decreasePoints", "label": "Points -5"},
                ],
                "card": [
                    {"key": "T", "actionList": "rotate90", "label": "Rotate 90"},
                    {"key": "I", "actionList": "rotate180", "label": "Rotate 180"},
                    {"key": "K", "actionList": "readyCard", "label": "Straighten"},
                    {"key": "F", "actionList": ["FLIP", "$ACTIVE_CARD_ID"], "label": "Flip"},
                    {"key": "P", "actionList": "moveToSpaceline", "label": "To spaceline"},
                    {"key": "X", "actionList": ["DISCARD", "$ACTIVE_CARD_ID"], "label": "Discard"},
                    {"key": "A", "actionList": ["DETACH", "$ACTIVE_CARD_ID"], "label": "Detach"},
                    {"key": "H", "actionList": ["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"], "label": "Shuffle into deck"},
                ],
                "token": [
                    {"key": "1", "tokenType": "yellow", "label": "Yellow token"},
                    {"key": "2", "tokenType": "countdown", "label": "Countdown"},
                    {"key": "3", "tokenType": "black", "label": "Black token"},
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
                    {"label": "Probe", "actionList": "probeDeck"},
                    {"label": "Seed spaceline", "actionList": "seedSpaceline"},
                    {"label": "Points +5", "actionList": "increasePoints"},
                    {"label": "Points -5", "actionList": "decreasePoints"},
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
                    {"label": "To spaceline", "actionList": "moveToSpaceline"},
                    {"label": "Rotate 90", "actionList": "rotate90"},
                    {"label": "Rotate 180", "actionList": "rotate180"},
                    {"label": "Straighten", "actionList": "readyCard"},
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
                "textPropertiesSideA": ["name", "affiliation", "classification", "text", "packName"],
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
                    {"propName": "affiliation", "label": "Affiliation"},
                    {"propName": "classification", "label": "Class"},
                    {"propName": "integrity", "label": "Int/Rng"},
                    {"propName": "cunning", "label": "Cun/Wpn"},
                    {"propName": "strength", "label": "Str/Shd"},
                    {"propName": "points", "label": "Pts"},
                    {"propName": "packName", "label": "Set"},
                ],
                "spawnGroups": [
                    {"loadGroupId": "playerNDeck", "label": "Draw Deck"},
                    {"loadGroupId": "playerNSeed", "label": "Seed"},
                    {"loadGroupId": "playerNMissions", "label": "Missions"},
                    {"loadGroupId": "playerNSites", "label": "Sites"},
                    {"loadGroupId": "sharedSpaceline", "label": "Spaceline"},
                    {"loadGroupId": "playerNTent", "label": "Q's Tent"},
                    {"loadGroupId": "playerNTactics", "label": "Battle Bridge"},
                ],
            }
        },
    )
    dump_json(
        jsons / "spawnExistingCardModal.json",
        {
            "spawnExistingCardModal": {
                "columnProperties": ["name", "type", "affiliation", "packName"],
                "loadGroupIds": [
                    "player1Deck",
                    "player1Play",
                    "player1Hand",
                    "player1Seed",
                    "player1Missions",
                    "sharedSpaceline",
                    "sharedSetAside",
                    "player2Deck",
                    "player2Play",
                ],
            }
        },
    )
    dump_json(
        jsons / "faceProperties.json",
        {
            "faceProperties": {
                "missionType": {"label": "Mission/Dilemma Type", "type": "string", "default": ""},
                "affiliation": {"label": "Affiliation", "type": "string", "default": ""},
                "classification": {"label": "Classification", "type": "string", "default": ""},
                "integrity": {"label": "Int/Range", "type": "string", "default": ""},
                "cunning": {"label": "Cun/Weapons", "type": "string", "default": ""},
                "strength": {"label": "Str/Shields", "type": "string", "default": ""},
                "points": {"label": "Points", "type": "string", "default": ""},
                "span": {"label": "Span", "type": "string", "default": ""},
                "quadrant": {"label": "Quadrant", "type": "string", "default": ""},
                "region": {"label": "Region", "type": "string", "default": ""},
                "icons": {"label": "Icons", "type": "string", "default": ""},
                "uniqueness": {"label": "Uniqueness", "type": "string", "default": ""},
                "keywords": {"label": "Keywords", "type": "string", "default": ""},
                "text": {"label": "Text", "type": "string", "default": ""},
                "lore": {"label": "Lore", "type": "string", "default": ""},
                "rarity": {"label": "Rarity", "type": "string", "default": ""},
                "property": {"label": "Property", "type": "string", "default": ""},
                "packName": {"label": "Set", "type": "string", "default": ""},
                "set": {"label": "Lackey Set", "type": "string", "default": ""},
                "printing": {"label": "Printing", "type": "string", "default": ""},
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
                        "Star Trek CCG 1E table created. Load a deck, then Seed Line to snap missions onto the spaceline. No rules are enforced.",
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
    if not (LACKEY / "sets" / "Physical.txt").exists():
        raise SystemExit(f"Lackey plugin not found: {LACKEY}")
    cards, errors = load_cards()
    (OUT / "tsvs").mkdir(parents=True, exist_ok=True)
    write_tsv(cards, OUT / "tsvs" / "cards.tsv")
    decks, menu, deck_errors = convert_decks(cards)
    unique_cards = len({card["databaseId"] for card in cards})
    errors.extend(deck_errors)
    download_lobby_art()
    write_plugin_jsons(cards, decks, menu)
    missing_urls = sum(1 for card in cards if not card["imageUrl"])
    (OUT / "SOURCE.txt").write_text(
        "\n".join(
            [
                f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from LackeyCCG startrek1e.",
                f"Source: {LACKEY}",
                "Art: GitHub eberlems/startrek1e playable setimages/general (localized to toybox).",
                "Author credit: Lackey / eberlems",
                "",
                "Tabletop plugin only — Lackey has no rules engine to port.",
                f"TSV rows: {len(cards)}  unique cards: {unique_cards}  missing image URLs: {missing_urls}",
                f"Prebuilts: {len(decks['preBuiltDecks'])} Lackey starter / simple decks.",
                "Spaceline is a shared row (hand-style snap). Attachments drop under missions.",
                "Dual-faced missions/stations are multi_sided (flip).",
                "Renamed_cards.txt skipped (aliases only).",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUT.name}")
    print("  pluginName: Star Trek CCG 1E")
    print(f"  tsv rows: {len(cards)}  unique: {unique_cards}  missing urls: {missing_urls}")
    print(f"  prebuilt decks: {len(decks['preBuiltDecks'])}")
    print(f"  types: {', '.join(sorted({card['type'] for card in cards}))}")
    if errors:
        print(f"\n{len(errors)} issue(s):")
        for err in errors[:40]:
            print(f"  - {err}")
        if len(errors) > 40:
            print(f"  … {len(errors) - 40} more")
        # Deck name misses are non-fatal if most resolved.
        deck_unknown = sum(1 for err in errors if "unknown card" in err)
        if deck_unknown and deck_unknown == len(errors):
            return 0
        if any("unexpected header" in err or "Duplicate" in err for err in errors):
            return 1
    print()
    print("Next:")
    print("  python3 plugins/scripts/collect_hosted_images.py star-trek-ccg-1e")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
