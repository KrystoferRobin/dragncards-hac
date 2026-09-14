#!/usr/bin/env python3
"""Build an AEG Legend of the Five Rings tabletop plugin from Sun and Moon + Oracle.

  python3 plugins/scripts/import_l5r.py
  python3 plugins/scripts/import_l5r.py --skip-oracle
  python3 plugins/scripts/import_l5r.py --upgrade-art
  python3 plugins/scripts/collect_hosted_images.py legend-of-the-five-rings
"""

from __future__ import annotations

import html
import json
import re
import shutil
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from image_names import TOYBOX_PREFIX, clear_image_url_prefix, card_rel_path, folder_slug, lobby_art_rel, pascal, stamp_lobby_art, toybox_url  # noqa: E402
from l5r_keywords import reminder_glossary  # noqa: E402
from l5r_l5rdb import fetch_l5rdb  # noqa: E402
from lackey_tabletop import (  # noqa: E402
    dump_json,
    group_types,
    region,
    sanitize,
    slug,
    standard_functions,
    unique_rel,
    write_color_png,
    write_tsv,
)

SOURCE = ROOT / "LegendOfTheFiveRings"
OUT = ROOT / "legend-of-the-five-rings"
IMAGES = ROOT / "images"
FOLDER = "legend-of-the-five-rings"
PASCAL = "LegendOfTheFiveRings"
PLACEHOLDER_REL = f"{FOLDER}/missing/{PASCAL}-Missing-NoArt.png"
ORACLE_FETCH = "https://api.oracleofthevoid.com/oracle-fetch?table=l5r&cardid={id}"
ORACLE_IMAGE = "https://images.oracleofthevoid.com/l5r/{hash}/printing_{cardid}_{printingid}_{size}.jpg"
LACKEY_BACK = "https://lackeyccg.com/l5r/high/cardback.jpg"
USER_AGENT = "Toybox/1.0 (private tabletop image collect)"
ORACLE_MAX_ID = 16000
ORACLE_WORKERS = 10
# Pack scans / Oracle "details" below this lose to a same-card Master or Oracle master.
WEAK_ART_BYTES = 150_000

DYNASTY_TYPES = {
    "personality",
    "holding",
    "event",
    "region",
    "ancestor",
    "celestial",
}
FATE_TYPES = {"strategy", "follower", "item", "spell", "ring"}
TYPE_TITLE = {
    "personality": "Personality",
    "strategy": "Strategy",
    "item": "Item",
    "holding": "Holding",
    "follower": "Follower",
    "spell": "Spell",
    "event": "Event",
    "stronghold": "Stronghold",
    "region": "Region",
    "sensei": "Sensei",
    "ancestor": "Ancestor",
    "celestial": "Celestial",
    "ring": "Ring",
    "wind": "Wind",
    "token": "Token",
    "playmat": "Playmat",
}
CLANS = ("crab", "crane", "dragon", "lion", "mantis", "phoenix", "scorpion", "spider", "unicorn")
MAT_FILES = {
    "crab": "crab.jpg",
    "crane": "crane.jpg",
    "dragon": "dragon.jpg",
    "lion": "lion.jpg",
    "mantis": "mantis_green.jpg",
    "phoenix": "phoenix.jpg",
    "scorpion": "scorpion.jpg",
    "spider": "spider.jpg",
    "unicorn": "unicorn.jpg",
    "default": "default.jpg",
}
SET_NAMES = {
    "Ivory": "Ivory Edition",
    "Celestial": "Celestial Edition",
    "Emperor": "Emperor Edition",
    "TwentyFestivals": "Twenty Festivals",
    "Samurai": "Samurai Edition",
    "Lotus": "Lotus Edition",
    "Diamond": "Diamond Edition",
    "Gold": "Gold Edition",
    "Jade": "Jade Edition",
    "Pearl": "Pearl Edition",
    "Imperial": "Imperial Edition",
    "Emerald": "Emerald Edition",
    "Obsidian": "Obsidian Edition",
    "Promo": "Promotional",
    "EP": "Evil Portents",
    "AD": "Anvil of Despair",
    "WoH": "War of Honor",
    "HaT": "Honor and Treachery",
    "FL": "The Floating World",
    "AMoH": "A Matter of Honor",
    "TCS": "The Coming Storm",
    "CoM": "Coils of Madness",
    "FaS": "Forgotten Souls",
    "TotV": "Thunderous Acclaim",
    "TBS": "The Blackest Storm",
    "HFW": "Hidden Forest War",
    "Onyx": "Onyx Edition",
    "RoJ": "Rise of Jigoku",
    "RtR": "Road to Ruin",
    "ROU": "Rise of Otosan Uchi",
    "RoU": "Rise of Otosan Uchi",
    "GS": "Gathering Storms",
    "ShE": "Shattered Empire",
    "CRI": "Chaos Reigns I",
    "CRII": "Chaos Reigns II",
    "CRIII": "Chaos Reigns III",
    "GoT": "Gates of Tengoku",
}
CLAN_MENU_ORDER = (
    "Crab",
    "Crane",
    "Dragon",
    "Lion",
    "Mantis",
    "Phoenix",
    "Scorpion",
    "Unicorn",
    "Spider",
    "Shadowlands",
    "Imperial",
    "Naga",
    "Unaligned",
    "Neutral",
)
FORMAT_MENU_ORDER = (
    "Imperial",
    "Jade",
    "Jade Extended",
    "Jade Open",
    "Gold",
    "Diamond",
    "Lotus",
    "Samurai",
    "Celestial",
    "Emperor",
    "Emperor Extended",
    "Ivory",
    "Twenty Festivals",
    "Ivory/20F Extended",
    "Onyx",
    "Onyx/20F Extended",
    "Shattered Empire",
    "ShE/Onyx Extended",
    "OBH (The Obsidian Hand) Legacy",
    "Modern",
    "Open",
    "Eternal",
    "Three Dynasties",
    "Big Deck",
    "Siege",
    "Clan Wars",
)
FORMAT_LEGAL = {
    "imperial": "imperial",
    "jade": "jade",
    "jade extended": "jade",
    "jade open": "jade",
    "gold": "gold",
    "diamond": "diamond",
    "lotus": "lotus",
    "samurai": "samurai",
    "celestial": "celestial",
    "emperor": "emperor",
    "emperor extended": "emperor",
    "ivory": "ivory",
    "twenty festivals": "ivory",
    "ivory/20f extended": "ivory",
    "onyx": "onyx",
    "onyx/20f extended": "onyx",
    "shattered empire": "shattered_empire",
    "she/onyx extended": "shattered_empire",
    "obh (the obsidian hand) legacy": "obsidian",
    "modern": "open",
    "open": "open",
    "siege": "open",
    "clan wars": "open",
}
SECTION_GROUP = {
    "stronghold": "playerNStronghold",
    "sensei": "playerNSensei",
    "wind": "playerNWind",
    "dynasty": "playerNDynasty",
    "fate": "playerNFate",
}
# Pile-viewer filter chips. Stronghold / Wind / Token / Playmat stay in the
# catalog but are not useful as browse buttons during play.
BROWSE_FILTER_TYPES = [
    "Ancestor",
    "Celestial",
    "Event",
    "Follower",
    "Holding",
    "Item",
    "Personality",
    "Region",
    "Ring",
    "Sensei",
    "Spell",
    "Strategy",
]
COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "zoomImageUrl",
    "cardBack",
    "type",
    "packName",
    "set",
    "loadGroupId",
    "clan",
    "legal",
    "cost",
    "focus",
    "force",
    "chi",
    "personalHonor",
    "honorReq",
    "goldProduction",
    "provinceStrength",
    "startingHonor",
    "rarity",
    "artist",
    "flavour",
    "text",
]


def fetch(url: str, dest: Path | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    data = urllib.request.urlopen(req, timeout=45).read()
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return data


def norm_name(value: str) -> str:
    text = html.unescape(value or "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("\u2019", "'").replace("`", "'")
    text = re.sub(r"&#149;", " ", text)
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text, flags=re.I)
    text = text.replace("\u2022", " ").replace("•", " ").replace("·", " ")
    text = re.sub(r"\bexperienced(?=[A-Za-z])", "experienced ", text, flags=re.I)
    text = re.sub(r"\binexperienced\b", "inexp", text, flags=re.I)
    text = re.sub(r"\bexperienced\s*(\d+)?\b", lambda match: f"exp{match.group(1) or ''}", text, flags=re.I)
    text = re.sub(r"\s*-\s*exp(\d*)\s*$", r" exp\1", text, flags=re.I)
    text = re.sub(r"\s*-\s*inexp\s*$", " inexp", text, flags=re.I)
    text = re.sub(r"\s*\(\d+\)\s*$", "", text)
    text = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()
    text = re.sub(r"\bexp\s+(\d+)\b", r"exp\1", text)
    return text


def norm_set(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (value or "").lower())).strip()


def text_of(card: ET.Element, tag: str) -> str:
    return sanitize(card.findtext(tag) or "")


def load_group(type_key: str) -> str:
    if type_key == "stronghold":
        return "playerNStronghold"
    if type_key == "sensei":
        return "playerNSensei"
    if type_key == "wind":
        return "playerNWind"
    if type_key in DYNASTY_TYPES:
        return "playerNDynasty"
    if type_key in FATE_TYPES:
        return "playerNFate"
    return "playerNFate"


def card_back_for(type_key: str) -> str:
    """Fate deck (green). Dynasty and table extras stay on the black default back."""
    return "fate" if type_key in FATE_TYPES else "default"


def pack_name(edition: str) -> str:
    return SET_NAMES.get(edition, edition or "Unknown")


def parse_xml(path: Path) -> list[dict[str, str]]:
    root = ET.parse(path).getroot()
    rows: list[dict[str, str]] = []
    for card in root.findall("card"):
        card_id = sanitize(card.get("id") or "")
        type_key = (card.get("type") or "strategy").strip().lower()
        if not card_id:
            continue
        editions = [sanitize(node.text or "") for node in card.findall("edition") if sanitize(node.text or "")]
        images = card.findall("image")
        image_files = [sanitize(node.text or "") for node in images if sanitize(node.text or "")]
        primary = sanitize(images[0].get("edition") or "") if images else (editions[0] if editions else "")
        if not primary and editions:
            primary = editions[0]
        legal = [sanitize(node.text or "") for node in card.findall("legal") if sanitize(node.text or "")]
        rows.append({
            "databaseId": card_id,
            "name": text_of(card, "name"),
            "typeKey": type_key,
            "type": TYPE_TITLE.get(type_key, type_key.title()),
            "packName": pack_name(primary),
            "set": primary or "Unknown",
            "editions": editions,
            "imageFiles": image_files,
            "loadGroupId": load_group(type_key),
            "clan": text_of(card, "clan").lower(),
            "legal": " ".join(legal),
            "cost": text_of(card, "cost"),
            "focus": text_of(card, "focus"),
            "force": text_of(card, "force"),
            "chi": text_of(card, "chi"),
            "personalHonor": text_of(card, "personal_honor"),
            "honorReq": text_of(card, "honor_req"),
            "goldProduction": text_of(card, "gold_production"),
            "provinceStrength": text_of(card, "province_strength"),
            "startingHonor": text_of(card, "starting_honor"),
            "rarity": text_of(card, "rarity"),
            "artist": text_of(card, "artist"),
            "flavour": text_of(card, "flavor"),
            "text": text_of(card, "text"),
            "cardBack": card_back_for(type_key),
            "imageUrl": "",
            "zoomImageUrl": "",
        })
    return rows


def recover_xml_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin1")
        for old, new in (("\x91", "'"), ("\x92", "'"), ("\x93", '"'), ("\x94", '"'), ("\x96", "-"), ("\x97", "-")):
            text = text.replace(old, new)
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)


def parse_xml_recovered(path: Path) -> list[dict[str, str]]:
    try:
        return parse_xml(path)
    except ET.ParseError:
        tmp = path.with_suffix(".recovered.xml")
        tmp.write_text(recover_xml_text(path), encoding="utf-8")
        try:
            return parse_xml(tmp)
        finally:
            if tmp.exists():
                tmp.unlink()


def merge_catalogs() -> tuple[list[dict[str, str]], dict[str, int]]:
    official_path = SOURCE / "Twenty Festivals Arc (Full)" / "database.xml"
    if not official_path.exists():
        official_path = SOURCE / "database.xml"
    official = parse_xml(official_path)
    by_id = {card["databaseId"]: card for card in official}
    extra = 0
    emerald_path = SOURCE / "Emerald" / "database.xml"
    if emerald_path.exists():
        for card in parse_xml_recovered(emerald_path):
            if card["databaseId"] not in by_id:
                by_id[card["databaseId"]] = card
                extra += 1
    cards = list(by_id.values())
    return cards, {"official": len(official), "community": extra, "xml": str(official_path)}


def local_pack_index() -> dict[str, Path]:
    index: dict[str, Path] = {}

    def consider(key: str, path: Path) -> None:
        prev = index.get(key)
        if prev is None or path.stat().st_size > prev.stat().st_size:
            index[key] = path

    roots = [SOURCE / "_packs", SOURCE / "Emerald" / "Set PDFS and Image Packs"]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            stem = path.stem.lower()
            consider(stem, path)
            consider(stem.replace("_", ""), path)
            consider(re.sub(r"[^a-z0-9]+", "", stem), path)
    return index


def card_art_keys(card: dict[str, str]) -> list[str]:
    keys = [card["databaseId"].lower(), re.sub(r"[^a-z0-9]+", "", card["databaseId"].lower())]
    match = re.match(r"([A-Za-z]+)(\d+[a-z]?)$", card["databaseId"])
    if match:
        keys.append(f"{match.group(1).lower()}_{match.group(2).lower()}")
        keys.append(f"{match.group(1).lower()}{match.group(2).lower()}")
    for image in card.get("imageFiles") or []:
        stem = Path(image).stem.lower()
        keys.extend([stem, stem.replace("_", ""), re.sub(r"[^a-z0-9]+", "", stem)])
    seen: set[str] = set()
    out: list[str] = []
    for key in keys:
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _art_core_stem(stem: str) -> str:
    core = re.sub(r"-\d+$", "", stem)
    if core.endswith("Master"):
        core = core[:-6]
    return core


def card_art_stems(card: dict[str, str]) -> list[str]:
    stems: list[str] = []
    for set_name in (card.get("packName") or "", card.get("set") or ""):
        if set_name:
            stems.append(f"{PASCAL}-{pascal(set_name)}-{pascal(card['name'])}")
    seen: set[str] = set()
    out: list[str] = []
    for stem in stems:
        if stem not in seen:
            seen.add(stem)
            out.append(stem)
    return out


def local_file_size(rel: str) -> int:
    if not rel or rel.startswith("http") or "missing/" in rel:
        return 0
    path = IMAGES / rel
    return path.stat().st_size if path.is_file() else 0


def art_is_weak(rel: str) -> bool:
    size = local_file_size(rel)
    return size < WEAK_ART_BYTES


def same_card_local_art(card: dict[str, str]) -> list[tuple[int, str]]:
    """Local files for this printing only — never a namesake from another set."""
    stems = set(card_art_stems(card))
    folders: list[Path] = []
    for set_name in (card.get("packName") or "", card.get("set") or ""):
        if set_name:
            folders.append(IMAGES / FOLDER / folder_slug(set_name))
    found: dict[str, int] = {}
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            if _art_core_stem(path.stem) not in stems:
                continue
            rel = str(path.relative_to(IMAGES)).replace("\\", "/")
            found[rel] = path.stat().st_size
    for rel in (card.get("imageUrl") or "", card.get("zoomImageUrl") or ""):
        size = local_file_size(rel)
        if size and _art_core_stem(Path(rel).stem) in stems:
            found[rel] = max(size, found.get(rel, 0))
    return sorted(((size, rel) for rel, size in found.items()), reverse=True)


def prefer_highest_quality_art(cards: list[dict[str, str]]) -> int:
    upgraded = 0
    for card in cards:
        if card.get("typeKey") in {"token", "playmat"}:
            continue
        candidates = same_card_local_art(card)
        if candidates:
            _size, rel = candidates[0]
            if card.get("imageUrl") != rel or card.get("zoomImageUrl") != rel:
                upgraded += 1
            card["imageUrl"] = rel
            card["zoomImageUrl"] = rel
            continue
        rel = card.get("imageUrl") or ""
        if rel and not rel.startswith("http") and "missing/" not in rel:
            if _art_core_stem(Path(rel).stem) not in set(card_art_stems(card)):
                card["imageUrl"] = ""
                card["zoomImageUrl"] = ""
                upgraded += 1
    return upgraded


def apply_local_art(cards: list[dict[str, str]]) -> int:
    index = local_pack_index()
    used: dict[str, int] = {}
    applied = 0
    for card in cards:
        if card["typeKey"] in {"token", "playmat"}:
            continue
        matches = [index[key] for key in card_art_keys(card) if key in index]
        if not matches:
            continue
        src = max(matches, key=lambda path: path.stat().st_size)
        rel = unique_rel(
            card_rel_path(FOLDER, PASCAL, card["packName"], card["name"], src.suffix),
            used,
        )
        dest = IMAGES / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or dest.stat().st_size < src.stat().st_size:
            shutil.copy2(src, dest)
        card["imageUrl"] = rel
        card["zoomImageUrl"] = rel
        applied += 1
    return applied


def reuse_collected_art(cards: list[dict[str, str]]) -> int:
    reused = 0
    for card in cards:
        if card["typeKey"] in {"token", "playmat"}:
            continue
        if card.get("imageUrl") and not art_is_weak(card["imageUrl"]):
            continue
        for ext in (".jpg", ".png", ".webp"):
            rel = card_rel_path(FOLDER, PASCAL, card["packName"], card["name"], ext)
            master = card_rel_path(FOLDER, PASCAL, card["packName"], f"{card['name']} Master", ext)
            table = IMAGES / rel
            hq = IMAGES / master
            pick = ""
            if hq.exists() and hq.stat().st_size > 0:
                pick = master
            elif table.exists() and table.stat().st_size > 0:
                pick = rel
            if pick and (art_is_weak(card.get("imageUrl") or "") or not card.get("imageUrl")):
                if local_file_size(pick) > local_file_size(card.get("imageUrl") or ""):
                    card["imageUrl"] = pick
                    card["zoomImageUrl"] = pick
                    reused += 1
                    break
    return reused


def oracle_image_entry(printing: dict | None) -> dict:
    if not printing:
        return {}
    images = printing.get("image") or []
    if isinstance(images, dict):
        return images
    if isinstance(images, list):
        for item in images:
            if isinstance(item, dict) and (item.get("master") or item.get("details")):
                return item
    return {}


def oracle_urls(card: dict, printing: dict | None) -> tuple[str, str]:
    card_id = str(card.get("cardid") or "")
    if printing:
        hashes = printing.get("printimagehash") or []
        image_hash = hashes[0] if hashes else ""
        printing_id = str(printing.get("printingid") or card.get("printingprimary") or "1")
        set_code = printing.get("imagehash") or ""
    else:
        image_hash = ""
        printing_id = str(card.get("printingprimary") or "1")
        set_code = ""
    if isinstance(set_code, list):
        set_code = set_code[0] if set_code else ""
    set_code = str(set_code).strip()
    if not image_hash:
        image_hash = (card.get("imagehash") or "")
        if isinstance(image_hash, list):
            image_hash = image_hash[0] if image_hash else ""
    image_hash = str(image_hash).strip()
    entry = oracle_image_entry(printing)
    # Community / Onyx Lives scans: /l5r/{TBS}/TBS_001_master.png
    if set_code and entry.get("master"):
        master = f"https://images.oracleofthevoid.com/l5r/{set_code}/{entry['master']}"
        details_name = entry.get("details") or entry["master"]
        details = f"https://images.oracleofthevoid.com/l5r/{set_code}/{details_name}"
        return details, master
    if not card_id or not image_hash:
        return "", ""
    details = ORACLE_IMAGE.format(hash=image_hash, cardid=card_id, printingid=printing_id, size="details")
    master = ORACLE_IMAGE.format(hash=image_hash, cardid=card_id, printingid=printing_id, size="master")
    return details, master


COMMUNITY_IMAGE_CODES = {
    "CRI", "CRII", "CRIII", "GS", "GoT", "HFW", "Onyx", "RoJ", "RoU", "RtR", "ShE", "TBS",
}

def community_master_url(database_id: str) -> str:
    """Onyx Lives / Emerald scans: /l5r/TBS/TBS_090_master.png from XML ids like TBS090."""
    match = re.match(r"([A-Za-z]+)(\d+[a-z]?)$", database_id or "", re.I)
    if not match:
        return ""
    code, number = match.group(1), re.sub(r"[a-z]$", "", match.group(2), flags=re.I)
    if code not in COMMUNITY_IMAGE_CODES or not number.isdigit():
        return ""
    return f"https://images.oracleofthevoid.com/l5r/{code}/{code}_{int(number):03d}_master.png"


def pick_printing(row: dict[str, str], card: dict) -> dict | None:
    printings = card.get("printing") or []
    if not printings:
        return None
    wanted = {norm_set(row["set"]), norm_set(row["packName"])}
    wanted.update(norm_set(name) for name in row.get("editions") or [])
    wanted.discard("")
    for printing in printings:
        set_name = norm_set(" ".join(printing.get("set") or []) if isinstance(printing.get("set"), list) else str(printing.get("set") or ""))
        if set_name in wanted or any(key and key in set_name for key in wanted):
            return printing
    primary = str(card.get("printingprimary") or "1")
    for printing in printings:
        if str(printing.get("printingid") or "") == primary:
            return printing
    return printings[0]


def fetch_oracle_card(card_id: int) -> dict | None:
    try:
        raw = fetch(ORACLE_FETCH.format(id=card_id))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("error") or not data.get("cardid"):
        return None
    return data


def load_oracle_cache(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return {str(key): value for key, value in payload.items() if isinstance(value, dict)}
    return {}


def fetch_oracle_index(cache_path: Path, skip: bool) -> dict[str, list[dict]]:
    cache = load_oracle_cache(cache_path)
    if skip:
        print(f"Oracle cache: {len(cache)} cards (fetch skipped).")
    else:
        have = {int(key) for key in cache if key.isdigit()}
        missing = [card_id for card_id in range(1, ORACLE_MAX_ID + 1) if card_id not in have]
        print(f"Oracle cache: {len(cache)} cards. Fetching {len(missing)} ids…")
        done = 0
        with ThreadPoolExecutor(max_workers=ORACLE_WORKERS) as pool:
            futures = {pool.submit(fetch_oracle_card, card_id): card_id for card_id in missing}
            for future in as_completed(futures):
                card_id = futures[future]
                card = future.result()
                if card:
                    cache[str(card.get("cardid") or card_id)] = card
                done += 1
                if done % 400 == 0:
                    cache_path.write_text(json.dumps(cache), encoding="utf-8")
                    print(f"  oracle {done}/{len(missing)} ({len(cache)} cards)", flush=True)
                time.sleep(0.01)
        cache_path.write_text(json.dumps(cache), encoding="utf-8")
        print(f"Oracle cache saved: {len(cache)} cards.")
    index: dict[str, list[dict]] = defaultdict(list)
    for card in cache.values():
        titles = card.get("formattedtitle") or card.get("title") or []
        if isinstance(titles, str):
            titles = [titles]
        for title in titles:
            key = norm_name(str(title))
            if key:
                index[key].append(card)
                stripped = re.sub(r"\s+(exp(?:\s*\d+)?|inexp)$", "", key).strip()
                if stripped and stripped != key:
                    index[stripped].append(card)
    return index


def match_oracle_card(row: dict[str, str], index: dict[str, list[dict]]) -> dict | None:
    key = norm_name(row["name"])
    candidates = index.get(key) or []
    if not candidates:
        return None
    card = candidates[0]
    if len(candidates) > 1:
        legal = set((row.get("legal") or "").split())
        scored: list[tuple[int, dict]] = []
        for option in candidates:
            option_legal = {norm_set(item) for item in (option.get("legality") or [])}
            score = len(legal & {item.split()[0] for item in option_legal})
            scored.append((score, option))
        scored.sort(key=lambda item: item[0], reverse=True)
        card = scored[0][1]
    return card


def apply_oracle_art(rows: list[dict[str, str]], index: dict[str, list[dict]], download: bool = True) -> dict[str, int]:
    pending: list[tuple[dict[str, str], str]] = []
    matched = 0
    for row in rows:
        if row["typeKey"] in {"token", "playmat"}:
            continue
        if row.get("imageUrl") and not row["imageUrl"].startswith("http") and not art_is_weak(row["imageUrl"]):
            continue
        card = match_oracle_card(row, index)
        remote = ""
        if card:
            printing = pick_printing(row, card)
            details, master = oracle_urls(card, printing)
            remote = master or details
        if not remote:
            remote = community_master_url(row.get("databaseId") or "")
        if not remote:
            continue
        if download:
            pending.append((row, remote))
        elif not row.get("imageUrl") or row["imageUrl"].startswith("http") or "missing/" in row["imageUrl"]:
            row["imageUrl"] = remote
            row["zoomImageUrl"] = remote
            matched += 1
    if pending:
        with ThreadPoolExecutor(max_workers=ORACLE_WORKERS) as pool:
            futures = {pool.submit(host_oracle_image, row, url): (row, url) for row, url in pending}
            for future in as_completed(futures):
                row, remote = futures[future]
                hosted = future.result()
                if hosted and local_file_size(hosted) > local_file_size(row.get("imageUrl") or ""):
                    row["imageUrl"] = hosted
                    row["zoomImageUrl"] = hosted
                    matched += 1
    return {"oracle": len(index), "matched": matched}


def host_oracle_image(row: dict[str, str], url: str) -> str:
    rel = card_rel_path(FOLDER, PASCAL, row["packName"], f"{row['name']} Master", Path(url).suffix or ".jpg")
    dest = IMAGES / rel
    if dest.exists() and dest.stat().st_size >= WEAK_ART_BYTES:
        return rel
    try:
        fetch(url, dest)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return rel if dest.exists() and dest.stat().st_size > 0 else ""
    return rel if dest.exists() and dest.stat().st_size > 0 else ""


def extra_cards() -> list[dict[str, str]]:
    extras = []
    extras.append({
        "databaseId": "l5r-imperial-favor",
        "name": "Imperial Favor",
        "typeKey": "token",
        "type": "Token",
        "packName": "Tokens",
        "set": "Tokens",
        "editions": [],
        "loadGroupId": "sharedFavor",
        "clan": "",
        "legal": "open",
        "cost": "",
        "focus": "",
        "force": "",
        "chi": "",
        "personalHonor": "",
        "honorReq": "",
        "goldProduction": "",
        "provinceStrength": "",
        "startingHonor": "",
        "rarity": "",
        "artist": "",
        "flavour": "The favor of the Emperor.",
        "text": "Claim the Imperial Favor. Drag it to your favor slot.",
        "cardBack": "default",
        "imageUrl": f"{FOLDER}/_plugin/{PASCAL}-ImperialFavorGeneric.jpg",
        "zoomImageUrl": f"{FOLDER}/_plugin/{PASCAL}-ImperialFavorGeneric.jpg",
    })
    extras.append({
        "databaseId": "l5r-playmat",
        "name": "Clan Playmat",
        "typeKey": "playmat",
        "type": "Playmat",
        "packName": "Playmats",
        "set": "Playmats",
        "editions": [],
        "loadGroupId": "playerNMat",
        "clan": "",
        "legal": "open",
        "cost": "",
        "focus": "",
        "force": "",
        "chi": "",
        "personalHonor": "",
        "honorReq": "",
        "goldProduction": "",
        "provinceStrength": "",
        "startingHonor": "",
        "rarity": "",
        "artist": "",
        "flavour": "",
        "text": "This player's clan mat. Loads the generic table until a deck is seated.",
        "cardBack": "default",
        "imageUrl": f"{FOLDER}/_plugin/{PASCAL}-MatDefault.jpg",
        "zoomImageUrl": f"{FOLDER}/_plugin/{PASCAL}-MatDefault.jpg",
    })
    return extras


def index_cards(cards: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = defaultdict(list)
    for card in cards:
        index[norm_name(card["name"])].append(card)
    return index


def pick_named(name: str, index: dict[str, list[dict[str, str]]], prefer_legal: str = "ivory") -> dict[str, str] | None:
    key = norm_name(name)
    matches = index.get(key) or []
    if not matches:
        stripped = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
        if stripped != name:
            matches = index.get(norm_name(stripped)) or []
    if not matches and "," in name:
        suffix = ""
        key_exp = re.search(r"(inexp|exp\d*)$", key)
        if key_exp:
            suffix = key_exp.group(1)
        matches = index.get(norm_name(f"{name.split(',', 1)[0]} {suffix}")) or []
    if not matches:
        return None
    preferred = [card for card in matches if prefer_legal and prefer_legal in card["legal"].split()]
    pool = preferred or matches
    if prefer_legal:
        edition_hit = [card for card in pool if prefer_legal in norm_set(card["set"]) or prefer_legal in norm_set(card["packName"])]
        if edition_hit:
            return edition_hit[0]
    return pool[0]


def parse_qty_line(line: str) -> tuple[int, str] | None:
    text = line.strip()
    if not text or text.lower().startswith("legality:"):
        return None
    match = re.match(r"^(\d+)\s*[xX]\s+(.+)$", text)
    if match:
        return int(match.group(1)), match.group(2).strip()
    match = re.match(r"^(\d+)\s+(.+)$", text)
    if match:
        return int(match.group(1)), match.group(2).strip()
    return 1, text


def deck_load_group(card: dict[str, str], section: str = "") -> str:
    """Stronghold / sensei / wind seat themselves. Personalities never start in play."""
    key = card["typeKey"]
    if key == "stronghold":
        return "playerNStronghold"
    if key == "sensei":
        return "playerNSensei"
    if key == "wind":
        return "playerNWind"
    if section in {"starting", "under_stronghold"} and key == "holding":
        return "playerNHoldings"
    if section in SECTION_GROUP:
        return SECTION_GROUP[section]
    return card["loadGroupId"]


def convert_txt_deck(
    path: Path,
    index: dict[str, list[dict[str, str]]],
    *,
    legality: str,
    ivory_style: bool,
    label: str,
    deck_id: str,
) -> tuple[dict, list[str]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    names: list[tuple[int, str]] = []
    for raw in lines:
        if raw.lower().startswith("legality:"):
            legality = raw.split(":", 1)[1].strip().lower() or legality
            continue
        parsed = parse_qty_line(raw)
        if parsed:
            names.append(parsed)
    cards_out = []
    missing = []
    for _position, (quantity, name) in enumerate(names):
        card = pick_named(name, index, prefer_legal=legality)
        if not card:
            missing.append(name)
            continue
        group = deck_load_group(card)
        entry = {
            "databaseId": card["databaseId"],
            "quantity": quantity,
            "loadGroupId": group,
        }
        if group == "playerNHoldings":
            entry["left"] = "18%"
            entry["top"] = "22%"
        cards_out.append(entry)
    return {"label": label, "cards": cards_out}, missing


def attribution_label(name: str, created_by: str, fallback: str = "") -> str:
    title = sanitize(name) or "Untitled"
    credit = sanitize(created_by) or sanitize(fallback)
    if credit and credit.lower() not in title.lower():
        return f"{title} — {credit}"
    return title


def clan_label(value: str) -> str:
    text = sanitize(value)
    if not text:
        return "Unaligned"
    return text[:1].upper() + text[1:]


def format_label(value: str) -> str:
    return sanitize(value) or "Unspecified"


def legal_for_format(value: str) -> str:
    return FORMAT_LEGAL.get(format_label(value).lower(), "open")


def sort_clan(name: str) -> tuple[int, str]:
    try:
        return CLAN_MENU_ORDER.index(name), name
    except ValueError:
        return len(CLAN_MENU_ORDER), name


def sort_format(name: str) -> tuple[int, str]:
    try:
        return FORMAT_MENU_ORDER.index(name), name
    except ValueError:
        return len(FORMAT_MENU_ORDER), name


def convert_l5rdb_decks(
    payload: dict,
    index: dict[str, list[dict[str, str]]],
) -> tuple[dict[str, dict], dict[str, dict[str, list[dict]]], list[str]]:
    cards_by_id = {int(card["id"]): card for card in payload.get("cards") or [] if card.get("id") is not None}
    rows_by_deck: dict[str, list[dict]] = defaultdict(list)
    for row in payload.get("deck_cards") or []:
        rows_by_deck[str(row.get("deck_id") or "")].append(row)
    decks: dict[str, dict] = {}
    menu: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    errors: list[str] = []
    for deck in payload.get("decks") or []:
        if not deck.get("is_public", True):
            continue
        deck_uuid = str(deck.get("id") or "")
        short = deck_uuid.split("-", 1)[0] or slug(str(deck.get("name") or "deck"))
        deck_id = f"l5rdb-{short}"
        clan = clan_label(str(deck.get("clan") or ""))
        fmt = format_label(str(deck.get("format") or ""))
        legality = legal_for_format(fmt)
        cards_out = []
        missing = []
        for row in rows_by_deck.get(deck_uuid, []):
            info = cards_by_id.get(int(row.get("card_id") or 0))
            title = ""
            if info:
                title = str(info.get("formatted_title") or info.get("title") or "")
            card = pick_named(title, index, prefer_legal=legality) if title else None
            if not card:
                if title:
                    missing.append(title)
                continue
            section = str(row.get("deck_section") or "").lower()
            group = deck_load_group(card, section)
            entry = {
                "databaseId": card["databaseId"],
                "quantity": int(row.get("quantity") or 1),
                "loadGroupId": group,
            }
            if group == "playerNHoldings":
                entry["left"] = "18%"
                entry["top"] = "22%"
            cards_out.append(entry)
        if not cards_out:
            errors.append(f"{deck.get('name')}: no cards resolved")
            continue
        label = attribution_label(str(deck.get("name") or ""), str(deck.get("created_by") or ""))
        decks[deck_id] = {"label": f"{label} ({fmt})", "cards": cards_out}
        menu[clan][fmt].append({"deckListId": deck_id, "label": label})
        if missing:
            errors.append(f"{label}: missing {len(missing)} ({', '.join(missing[:8])})")
    return decks, menu, errors


def convert_decks(cards: list[dict[str, str]], l5rdb: dict | None) -> tuple[dict, dict, list[str]]:
    index = index_cards(cards)
    decks: dict[str, dict] = {}
    errors: list[str] = []
    ivory_items = []
    for path in sorted((SOURCE / "decks").glob("*.txt")):
        deck_id = slug(path.stem)
        payload, missing = convert_txt_deck(
            path,
            index,
            legality="ivory",
            ivory_style=True,
            label=f"{path.stem} — Ivory starter",
            deck_id=deck_id,
        )
        if len(payload["cards"]) < 2:
            errors.append(f"{path.name}: not enough lines")
            continue
        decks[deck_id] = payload
        ivory_items.append({"deckListId": deck_id, "label": path.stem})
        if missing:
            errors.append(f"{path.stem}: missing {', '.join(missing)}")

    she_items = []
    she_dir = SOURCE / "Emerald" / "ShE Starter Decklists (SnM Compatible)"
    if she_dir.exists():
        for path in sorted(she_dir.glob("*.txt")):
            stem = path.stem.replace("Starter Deck- ", "").strip()
            deck_id = slug(f"she-starter-{stem}")
            payload, missing = convert_txt_deck(
                path,
                index,
                legality="shattered_empire",
                ivory_style=False,
                label=f"{stem} — Shattered Empire starter",
                deck_id=deck_id,
            )
            if len(payload["cards"]) < 2:
                errors.append(f"{path.name}: not enough lines")
                continue
            decks[deck_id] = payload
            she_items.append({"deckListId": deck_id, "label": stem})
            if missing:
                errors.append(f"ShE {stem}: missing {', '.join(missing)}")

    sub_menus: list[dict] = []
    if ivory_items:
        sub_menus.append({"label": "Ivory starters", "deckLists": ivory_items})
    if she_items:
        sub_menus.append({"label": "Shattered Empire starters", "deckLists": she_items})

    if l5rdb:
        community, clan_menu, community_errors = convert_l5rdb_decks(l5rdb, index)
        decks.update(community)
        errors.extend(community_errors)
        clan_subs = []
        for clan in sorted(clan_menu, key=sort_clan):
            formats = clan_menu[clan]
            format_subs = []
            for fmt in sorted(formats, key=sort_format):
                items = sorted(formats[fmt], key=lambda item: item["label"].lower())
                format_subs.append({"label": fmt, "deckLists": items})
            clan_subs.append({"label": clan, "subMenus": format_subs})
        # DragnCards only allows two menu levels. Clan is the top folder;
        # format is the nested list. A "Community decks" wrapper is one nest too many.
        sub_menus.extend(clan_subs)

    return {"preBuiltDecks": decks}, {"deckMenu": {"subMenus": sub_menus}}, errors


def player_groups(player: str) -> dict:
    number = player.replace("player", "")
    piles = [
        ("Dynasty", "Dynasty", "deck", "Dynasty", "DynastyDiscard", False, "B"),
        ("DynastyDiscard", "Dynasty Discard", "discard", "Dynasty", "DynastyDiscard", False, "A"),
        ("Fate", "Fate", "deck", "Fate", "FateDiscard", False, "B"),
        ("FateDiscard", "Fate Discard", "discard", "Fate", "FateDiscard", False, "A"),
        ("Hand", "Hand", "hand", "Fate", "FateDiscard", False, "B"),
        ("Play", "Play", "inPlay", "Fate", "FateDiscard", True, "A"),
        ("Holdings", "Holdings", "inPlay", "Dynasty", "DynastyDiscard", True, "A"),
        ("Stronghold", "Stronghold", "inPlay", "Dynasty", "DynastyDiscard", True, "A"),
        ("Sensei", "Sensei", "inPlay", "Dynasty", "DynastyDiscard", True, "A"),
        ("Wind", "Wind", "inPlay", "Dynasty", "DynastyDiscard", True, "A"),
        ("Favor", "Favor", "inPlay", "Fate", "FateDiscard", True, "A"),
        ("Mat", "Playmat", "aside", "Dynasty", "DynastyDiscard", False, "A"),
        ("Removed", "Removed", "aside", "Fate", "FateDiscard", False, "A"),
    ]
    groups = {}
    for suffix, label, group_type, deck_suffix, discard_suffix, in_play, side in piles:
        enter = {
            "controller": player,
            "deckGroupId": f"{player}{deck_suffix}",
            "discardGroupId": f"{player}{discard_suffix}",
            "currentSide": side,
        }
        if in_play:
            enter["inPlay"] = True
        if suffix == "Hand":
            enter["peeking"] = {player: True}
        groups[f"{player}{suffix}"] = {
            "groupType": group_type,
            "label": f"Player {number} {label}",
            "tableLabel": label,
            "onCardEnter": enter,
        }
        if in_play:
            groups[f"{player}{suffix}"]["canHaveAttachments"] = True
    for index in range(1, 5):
        groups[f"{player}Province{index}"] = {
            "groupType": "inPlay",
            "label": f"Player {number} Province {index}",
            "tableLabel": f"P{index}",
            "canHaveAttachments": True,
            "destroyed": False,
            "onCardEnter": {
                "controller": player,
                "deckGroupId": f"{player}Dynasty",
                "discardGroupId": f"{player}DynastyDiscard",
                "currentSide": "B",
                "inPlay": True,
            },
        }
    return groups


def mat_rel(clan: str) -> str:
    return f"{FOLDER}/_plugin/{PASCAL}-Mat{clan.title()}.jpg"


def paint_fate_back(src: Path, dest: Path) -> None:
    """Same five-rings plate as the dynasty back, on a jade field.

    Lackey only ships the black scan. Sun and Moon / AEG fate cards use the
    same gold mons on green; we keep the gold and title and retint the field.
    """
    try:
        from PIL import Image
    except ImportError:
        return
    if not src.exists() or src.stat().st_size == 0:
        return
    image = Image.open(src).convert("RGB")
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            red, green, blue = pixels[x, y]
            lum = 0.2126 * red + 0.7152 * green + 0.0722 * blue
            gold = red > 70 and green > 45 and (red + green) > blue * 2.1 and (red + green) > 140
            title = (not gold) and red > green + 18 and red > blue + 18 and red > 38
            if gold or title:
                continue
            pixels[x, y] = (
                int(min(255, lum * 0.20 + 8)),
                int(min(255, lum * 0.62 + 26)),
                int(min(255, lum * 0.22 + 10)),
            )
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, quality=92)


def write_plugin_art() -> dict[str, str]:
    plugin = IMAGES / FOLDER / "_plugin"
    plugin.mkdir(parents=True, exist_ok=True)
    (IMAGES / FOLDER / "missing").mkdir(parents=True, exist_ok=True)
    backgrounds = SOURCE / "backgrounds"

    back = plugin / f"{PASCAL}-CardbackDefault.jpg"
    if not back.exists() or back.stat().st_size == 0:
        try:
            fetch(LACKEY_BACK, back)
        except (urllib.error.URLError, TimeoutError, OSError):
            write_color_png(back.with_suffix(".png"), (40, 18, 18), size=96)
            back = back.with_suffix(".png")
    fate = plugin / f"{PASCAL}-CardbackFate.jpg"
    if not fate.exists() or fate.stat().st_size == 0:
        paint_fate_back(back, fate)

    default_bg = backgrounds / "default.jpg"
    if default_bg.exists():
        shutil.copy2(default_bg, IMAGES / lobby_art_rel(FOLDER, "banner"))
        shutil.copy2(default_bg, IMAGES / lobby_art_rel(FOLDER, "logo"))
        shutil.copy2(default_bg, plugin / f"{PASCAL}-Background.jpg")
        shutil.copy2(default_bg, plugin / f"{PASCAL}-MatDefault.jpg")
    for clan, filename in MAT_FILES.items():
        src = backgrounds / filename
        if src.exists() and clan != "default":
            shutil.copy2(src, plugin / f"{PASCAL}-Mat{clan.title()}.jpg")

    favor_sources = {
        "": "if-generic.jpg",
        "Generic": "if-generic.jpg",
        "Crab": "if-crab.jpg",
        "Crane": "if-crane.jpg",
        "Dragon": "if-dragon.jpg",
        "Lion": "if-lion.jpg",
        "Mantis": "if-mantis.jpg",
        "Phoenix": "if-pheonix.jpg",
        "Scorpion": "if-scorpion.jpg",
        "Spider": "if-spider.jpg",
        "Unicorn": "if-unicorn.jpg",
    }
    for suffix, src_name in favor_sources.items():
        src = plugin / src_name
        dest = plugin / f"{PASCAL}-ImperialFavor{suffix}.jpg"
        if src.exists():
            shutil.copy2(src, dest)
        elif suffix == "" and (not dest.exists() or dest.stat().st_size < 1024):
            write_color_png(dest.with_suffix(".png"), (196, 164, 48), size=128)
            shutil.copy2(dest.with_suffix(".png"), dest)

    write_color_png(IMAGES / PLACEHOLDER_REL, (42, 28, 22), size=96)
    write_color_png(plugin / f"{PASCAL}-TokenGreen.png", (48, 160, 72))
    write_color_png(plugin / f"{PASCAL}-TokenRed.png", (196, 48, 48))
    write_color_png(plugin / f"{PASCAL}-TokenStayBowed.png", (120, 72, 24))
    write_color_png(plugin / f"{PASCAL}-TokenStayFlip.png", (72, 72, 140))
    rel = f"{FOLDER}/_plugin/{PASCAL}-CardbackDefault{back.suffix.lower()}"
    if back.suffix.lower() == ".png":
        rel = rel.replace(".png", ".png")
    backs = {"default": rel}
    if fate.exists() and fate.stat().st_size > 0:
        backs["fate"] = f"{FOLDER}/_plugin/{PASCAL}-CardbackFate.jpg"
    return backs


def refill_province_code() -> list:
    """Fill one empty, undestroyed province from that player's dynasty, face-down."""
    return [
        ["COND",
         ["AND",
          ["IN_STRING", "$PROVINCE_ID", "Province"],
          ["GROUP_EMPTY", "$PROVINCE_ID"],
          ["NOT", ["EQUAL", "$GAME.groupById.$PROVINCE_ID.destroyed", True]]],
         [
             ["VAR", "$OWNER", ["REGEX_REPLACE", "$PROVINCE_ID", "(player[0-9]+).*", "\\1"]],
             ["COND",
              ["NOT", ["GROUP_EMPTY", "{{$OWNER}}Dynasty"]],
              [
                  ["MOVE_STACKS", "{{$OWNER}}Dynasty", "$PROVINCE_ID", 1, "bottom"],
                  ["LOG", "A dynasty card filled the empty province face-down."],
              ]],
         ]],
    ]


def start_turn_code() -> list:
    """Unbow a player's cards and flip their provinces. Dishonor / hold locks stay."""
    return [
        ["FOR_EACH_KEY_VAL", "$CARD_ID", "$CARD", "$GAME.cardById",
         ["COND",
          ["AND",
           ["EQUAL", "$CARD.controller", "$WHO"],
           ["NOT_EQUAL", "$CARD.tokens.stayBowed", 1],
           ["NOT_EQUAL", "$CARD.rotation", 180]],
          ["SET", "/cardById/{{$CARD_ID}}/rotation", 0]]],
        ["FOR_EACH_KEY_VAL", "$CARD_ID", "$CARD", "$GAME.cardById",
         ["COND",
          ["AND",
           ["EQUAL", "$CARD.controller", "$WHO"],
           ["IN_STRING", "$CARD.groupId", "Province"],
           ["NOT_EQUAL", "$CARD.tokens.stayFlip", 1]],
          ["SET", "/cardById/{{$CARD_ID}}/currentSide", "A"]]],
        ["LOG", ["GET_ALIAS", "$WHO"], " straightened and revealed provinces (held and dishonored cards stayed)."],
    ]


def favor_art_path(clan_title: str) -> str:
    return f"{FOLDER}/_plugin/{PASCAL}-ImperialFavor{clan_title}.jpg"


def apply_favor_art_code() -> list:
    """Paint the Imperial Favor with $WHO's clan art (generic if unknown)."""
    conds: list = []
    for clan in CLANS:
        art = favor_art_path(clan.title())
        conds.extend([
            ["EQUAL", "$GAME.playerData.$WHO.clan", clan],
            [
                ["SET", "/cardById/{{$CARD_ID}}/sides/A/imageUrl", art],
                ["SET", "/cardById/{{$CARD_ID}}/sides/A/zoomImageUrl", art],
            ],
        ])
    generic = favor_art_path("Generic")
    conds.extend([
        ["TRUE"],
        [
            ["SET", "/cardById/{{$CARD_ID}}/sides/A/imageUrl", generic],
            ["SET", "/cardById/{{$CARD_ID}}/sides/A/zoomImageUrl", generic],
        ],
    ])
    return [["COND", *conds]]


def reset_favor_art_code() -> list:
    generic = favor_art_path("Generic")
    return [
        ["SET", "/cardById/{{$CARD_ID}}/sides/A/imageUrl", generic],
        ["SET", "/cardById/{{$CARD_ID}}/sides/A/zoomImageUrl", generic],
    ]


def add_facedown_dynasty_code() -> list:
    """Deal one facedown dynasty card into a province even if it already has a card."""
    return [
        ["COND",
         ["AND",
          ["IN_STRING", "$PROVINCE_ID", "Province"],
          ["NOT", ["EQUAL", "$GAME.groupById.$PROVINCE_ID.destroyed", True]]],
         [
             ["VAR", "$OWNER", ["REGEX_REPLACE", "$PROVINCE_ID", "(player[0-9]+).*", "\\1"]],
             ["COND",
              ["NOT", ["GROUP_EMPTY", "{{$OWNER}}Dynasty"]],
              [
                  ["MOVE_STACKS", "{{$OWNER}}Dynasty", "$PROVINCE_ID", 1, "bottom"],
                  ["LOG", "A dynasty card filled the province face-down."],
              ]],
         ]],
    ]


def claim_favor_code() -> list:
    return [
        ["VAR", "$FAVOR", ["ONE_CARD", "$C", ["EQUAL", "$C.databaseId", "l5r-imperial-favor"]]],
        ["COND",
         ["EQUAL", "$FAVOR", None],
         ["LOG", "The Imperial Favor is not on the table."],
         ["TRUE"],
         [
             ["MOVE_CARD", "$FAVOR.id", "{{$WHO}}Favor", 0],
             ["VAR", "$CARD_ID", "$FAVOR.id"],
             ["APPLY_FAVOR_ART", "$WHO", "$CARD_ID"],
             ["LOG", ["GET_ALIAS", "$WHO"], " claimed the Imperial Favor."],
         ]],
    ]


def l5r_functions() -> dict:
    functions = standard_functions()
    functions["START_TURN"] = {"args": ["$WHO"], "code": start_turn_code()}
    functions["REFILL_PROVINCE"] = {"args": ["$PROVINCE_ID"], "code": refill_province_code()}
    functions["ADD_FACEDOWN_DYNASTY"] = {"args": ["$PROVINCE_ID"], "code": add_facedown_dynasty_code()}
    functions["APPLY_FAVOR_ART"] = {"args": ["$WHO", "$CARD_ID"], "code": apply_favor_art_code()}
    functions["RESET_FAVOR_ART"] = {"args": ["$CARD_ID"], "code": reset_favor_art_code()}
    functions["CLAIM_FAVOR"] = {"args": ["$WHO"], "code": claim_favor_code()}
    functions["TOGGLE_PROVINCE_DESTROYED"] = {"args": ["$PROVINCE_ID"], "code": [
        ["COND",
         ["EQUAL", "$GAME.groupById.$PROVINCE_ID.destroyed", True],
         [
             ["SET", "/groupById/{{$PROVINCE_ID}}/destroyed", False],
             ["LOG", "{{$ALIAS_N}} restored {{$GAME.groupById.$PROVINCE_ID.label}}."],
             ["REFILL_PROVINCE", "$PROVINCE_ID"],
         ],
         ["TRUE"],
         [
             ["SET", "/groupById/{{$PROVINCE_ID}}/destroyed", True],
             ["LOG", "{{$ALIAS_N}} destroyed {{$GAME.groupById.$PROVINCE_ID.label}}."],
         ]],
    ]}
    dynasty_check = ["OR"]
    for name in ("Personality", "Holding", "Event", "Region", "Ancestor", "Celestial", "Stronghold", "Sensei", "Wind"):
        dynasty_check.append(["EQUAL", "$CARD.currentFace.type", name])
    functions["DISCARD"] = {"args": ["$CARD_ID"], "code": [
        ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
        ["COND",
         ["EQUAL", "$CARD.databaseId", "l5r-imperial-favor"],
         [["MOVE_CARD", "$CARD.id", "sharedFavor", 0],
          ["RESET_FAVOR_ART", "$CARD.id"],
          ["LOG", "{{$ALIAS_N}} returned the Imperial Favor."]],
         dynasty_check,
         [["MOVE_CARD", "$CARD.id", "{{$CARD.controller}}DynastyDiscard", 0],
          ["LOG", "{{$ALIAS_N}} discarded {{$CARD.sides.A.name}} to the dynasty discard."]],
         ["TRUE"],
         [["MOVE_CARD", "$CARD.id", "{{$CARD.controller}}FateDiscard", 0],
          ["LOG", "{{$ALIAS_N}} discarded {{$CARD.sides.A.name}} to the fate discard."]]],
    ]}
    return functions


def post_load_actions() -> list:
    mat_conds: list = []
    for clan in CLANS:
        mat_conds.extend([
            ["EQUAL", f"$GAME.playerData.$PLAYER_N.clan", clan],
            ["SET", "/cardById/{{$CARD_ID}}/sides/A/imageUrl", mat_rel(clan)],
        ])
    mat_conds.extend([
        ["TRUE"],
        ["SET", "/cardById/{{$CARD_ID}}/sides/A/imageUrl", mat_rel("Default")],
    ])
    refill = [["REFILL_PROVINCE", f"{{{{$PLAYER_N}}}}Province{index}"] for index in range(1, 5)]
    seating = [
        ["FOR_EACH_KEY_VAL", "$CARD_ID", "$CARD", "$GAME.cardById",
         ["COND",
          ["AND",
           ["EQUAL", "$CARD.controller", "$PLAYER_N"],
           ["EQUAL", "$CARD.currentFace.type", "Stronghold"]],
          [
              ["SET", "/playerData/$PLAYER_N/clan", "$CARD.currentFace.clan"],
              ["SET", "/playerData/$PLAYER_N/honor", ["TO_INT", "$CARD.currentFace.startingHonor"]],
          ]]],
        ["FOR_EACH_KEY_VAL", "$CARD_ID", "$CARD", "$GAME.cardById",
         ["COND",
          ["EQUAL", "$CARD.groupId", "{{$PLAYER_N}}Mat"],
          [["COND", *mat_conds]]]],
        ["FOR_EACH_KEY_VAL", "$CARD_ID", "$CARD", "$GAME.cardById",
         ["COND",
          ["AND",
           ["EQUAL", "$CARD.controller", "$PLAYER_N"],
           ["EQUAL", "$CARD.currentFace.type", "Stronghold"],
           ["IN_STRING", "$CARD.currentFace.legal", "emperor"],
           ["NOT_EQUAL", ["IN_STRING", "$CARD.currentFace.legal", "ivory"], True]],
          [
              ["LOAD_CARDS", ["LIST",
                  {"databaseId": "HaT001", "loadGroupId": "playerNHoldings", "quantity": 1, "left": "38%", "top": "22%"},
                  {"databaseId": "Emperor028", "loadGroupId": "playerNHoldings", "quantity": 1, "left": "58%", "top": "22%"},
              ]],
              ["LOG", "{{$ALIAS_N}} received Bamboo Harvesters and Border Keep."],
          ]]],
        ["SHUFFLE_GROUP", "{{$PLAYER_N}}Dynasty"],
        ["SHUFFLE_GROUP", "{{$PLAYER_N}}Fate"],
        *refill,
        ["MOVE_STACKS", "{{$PLAYER_N}}Fate", "{{$PLAYER_N}}Hand", 5, "bottom"],
        ["LOG", "{{$ALIAS_N}} seated a clan: stronghold and sensei in place, provinces filled, five fate drawn."],
        ["COND",
         ["EQUAL", "$PLAYER_N", "$GAME.firstPlayer"],
         ["START_TURN", "$PLAYER_N"]],
    ]
    return [
        ["COND",
         ["GROUP_NOT_EMPTY", "{{$PLAYER_N}}Stronghold"],
         seating],
    ]


def write_plugin_jsons(cards: list[dict[str, str]], decks: dict, menu: dict, backs: dict[str, str], keep_layouts: bool = False) -> None:
    jsons = OUT / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    types = sorted({card["type"] for card in cards})
    main_path = jsons / "main.json"
    existing_main = json.loads(main_path.read_text(encoding="utf-8")) if main_path.exists() else {}
    main_payload = {
        "pluginName": "Legend of the Five Rings",
        "author": "Kamisasori Toshokan / Oracle of the Void / Sun and Moon / L5R DB",
        "tutorialUrl": "https://www.hwstn.com/sunandmoon/",
        "announcements": [
            "AEG Legend of the Five Rings CCG (not the FFG LCG). Ivory-shaped table for 2–8, shortcuts only — no rules engine.",
            "Your seat stays at the bottom. Look at another player to put them across the table. Holdings sit below the provinces.",
            "Empty provinces refill face-down from dynasty. The × on a province marks it destroyed so it stays empty. Flipping a dynasty Event shouts EVENT and deals another facedown card into that province — negotiate what the Event does. F on a Favor box claims the Imperial Favor in your clan's art (V does the same). Dynasty starts the turn: unbow and flip your provinces. D fate, R unbow + flip, Y refill, B bow, U straighten, F flip, I dishonor/honor.",
        ],
        "loadPreBuiltOnNewGame": False,
        "backgroundUrl": toybox_url(f"{FOLDER}/_plugin/{PASCAL}-Background.jpg"),
    }
    # Keep a hand-picked lobby banner/logo (logo.jpg / banner.jpg) if already set.
    if existing_main.get("bannerUrl"):
        main_payload["bannerUrl"] = existing_main["bannerUrl"]
    if existing_main.get("logoUrl"):
        main_payload["logoUrl"] = existing_main["logoUrl"]
    dump_json(main_path, main_payload)
    if "bannerUrl" not in main_payload or "logoUrl" not in main_payload:
        stamp_lobby_art(jsons, FOLDER)
    clear_image_url_prefix(jsons)
    dump_json(jsons / "cardBacks.json", {"cardBacks": {
        key: {"width": 0.72, "height": 1.0, "imageUrl": rel} for key, rel in backs.items()
    }})
    card_types = {}
    for name in types:
        if name == "Playmat":
            card_types[name] = {"width": 3.4, "height": 0.55, "tokens": [], "zoomFactor": 0.35}
        else:
            card_types[name] = {"width": 0.72, "height": 1.0, "tokens": ["stayBowed", "stayFlip", "green", "red"]}
    dump_json(jsons / "cardTypes.json", {"cardTypes": card_types})

    groups = {
        "sharedSetAside": {
            "groupType": "aside",
            "label": "Set Aside",
            "tableLabel": "Set Aside",
            "onCardEnter": {"controller": "shared"},
        },
        "sharedFavor": {
            "groupType": "inPlay",
            "label": "Imperial Favor",
            "tableLabel": "Favor",
            "onCardEnter": {"controller": "shared", "inPlay": True},
        },
    }
    for number in range(1, 9):
        groups.update(player_groups(f"player{number}"))
    dump_json(jsons / "groups.json", {"groups": groups})

    # Sit (S) is always your seat at the bottom. Look (L) is the opponent
    # you're viewing — previous seat if you're looking at yourself. That is
    # what lets one layout serve 2–8 players.
    layout_regions = [
        ("playerLHand", "fan", "0.0%", "0.0%", "72.0%", "8.0%"),
        ("playerLFate", "pile", "0.0%", "8.8%", "8.0%", "10.0%"),
        ("playerLProvince4", "fan", "8.0%", "8.8%", "11.0%", "10.0%"),
        ("playerLProvince3", "fan", "20.0%", "8.8%", "11.0%", "10.0%"),
        ("playerLProvince2", "fan", "32.0%", "8.8%", "11.0%", "10.0%"),
        ("playerLProvince1", "fan", "44.0%", "8.8%", "11.0%", "10.0%"),
        ("playerLDynasty", "pile", "56.0%", "8.8%", "8.0%", "10.0%"),
        ("playerLStronghold", "row", "65.0%", "8.8%", "8.0%", "10.0%"),
        ("playerLDynastyDiscard", "pile", "73.0%", "15.0%", "8.0%", "10.0%"),
        ("playerLFateDiscard", "pile", "82.0%", "15.0%", "8.0%", "10.0%"),
        ("playerLRemoved", "pile", "91.0%", "15.0%", "8.0%", "10.0%"),
        ("playerLSensei", "row", "65.0%", "18.8%", "8.0%", "8.8%"),
        ("playerLHoldings", "row", "8.0%", "19.0%", "53.0%", "8.0%"),
        ("playerLPlay", "free", "8.0%", "27.6%", "53.0%", "16.0%"),
        ("playerLFavor", "pile", "0.0%", "32.5%", "8.0%", "11.3%"),
        ("sharedFavor", "pile", "61.0%", "40.0%", "12.0%", "9.0%"),
        ("playerSFavor", "pile", "0.0%", "45.0%", "8.0%", "12.0%"),
        ("playerSPlay", "free", "8.0%", "45.0%", "53.0%", "15.5%"),
        ("playerSSensei", "row", "0.0%", "72.5%", "8.0%", "10.5%"),
        ("playerSStronghold", "row", "0.0%", "61.5%", "8.0%", "10.5%"),
        ("playerSDynasty", "pile", "8.0%", "61.5%", "8.0%", "10.5%"),
        ("playerSProvince1", "fan", "17.0%", "61.5%", "11.0%", "10.5%"),
        ("playerSProvince2", "fan", "29.0%", "61.5%", "11.0%", "10.5%"),
        ("playerSProvince3", "fan", "41.0%", "61.5%", "11.0%", "10.5%"),
        ("playerSProvince4", "fan", "53.0%", "61.5%", "11.0%", "10.5%"),
        ("playerSFate", "pile", "65.0%", "61.5%", "8.0%", "10.5%"),
        ("playerSHoldings", "row", "8.0%", "72.5%", "53.0%", "10.5%"),
        ("playerSDynastyDiscard", "pile", "73.0%", "75.0%", "8.0%", "11.0%"),
        ("playerSFateDiscard", "pile", "82.0%", "75.0%", "8.0%", "11.3%"),
        ("playerSRemoved", "pile", "91.0%", "75.0%", "8.0%", "11.0%"),
        ("playerSHand", "fan", "0.0%", "83.8%", "73.0%", "16.3%"),
    ]
    regions = {}
    for group_id, rtype, left, top, width, height in layout_regions:
        extra = {"disableDroppableAttachments": True} if rtype == "fan" else {}
        regions[group_id] = region(group_id, rtype, left, top, width, height, **extra)
    layouts_path = jsons / "layouts.json"
    if keep_layouts and layouts_path.exists():
        print(f"Keeping existing {layouts_path.name}")
    else:
        dump_json(layouts_path, {"layouts": {"default": {
            "cardSize": 9,
            "rowSpacing": 1,
            "chat": {"left": "73%", "top": "81%", "width": "26%", "height": "18%"},
            "regions": regions,
            "tableButtons": {
                "drawFate": {"actionList": "drawFate", "label": "Draw Fate", "left": "73%", "top": "36%", "width": "12%", "height": "3.4%"},
                "refresh": {"actionList": "refresh", "label": "Refresh", "left": "86%", "top": "36%", "width": "13%", "height": "3.4%"},
                "refillDynasty": {"actionList": "refillDynasty", "label": "Refill", "left": "73%", "top": "40%", "width": "12%", "height": "3.4%"},
                "shuffleBoth": {"actionList": "shuffleBoth", "label": "Shuffle", "left": "86%", "top": "40%", "width": "13%", "height": "3.4%"},
            },
        }}})

    typed_groups = group_types()
    typed_groups["inPlay"]["onCardEnter"]["currentSide"] = "A"
    typed_groups["hand"]["onCardEnter"]["currentSide"] = "B"
    dump_json(jsons / "groupTypes.json", {"groupTypes": typed_groups})
    dump_json(jsons / "playerCountMenu.json", {"playerCountMenu": [
        {"label": str(n), "numPlayers": n, "layoutId": "default"} for n in range(2, 9)
    ]})
    phases = [
        ("dynasty", "Dynasty"),
        ("draw", "Draw"),
        ("combat", "Combat"),
        ("action", "Action"),
        ("end", "End"),
    ]
    dump_json(jsons / "phases.json", {"phases": {
        key: {"label": label, "height": "20%"} for key, label in phases
    }, "phaseOrder": [key for key, _ in phases]})
    dump_json(jsons / "steps.json", {"steps": {
        f"{key}Step": {"phaseId": key, "label": label} for key, label in phases
    }, "stepOrder": [f"{key}Step" for key, _ in phases]})
    dump_json(jsons / "playerProperties.json", {"playerProperties": {
        "honor": {"label": "Honor", "type": "integer", "default": 0, "min": 0},
        "gold": {"label": "Gold", "type": "integer", "default": 0, "min": 0},
        "clan": {"label": "Clan", "type": "string", "default": ""},
    }})
    dump_json(jsons / "gameProperties.json", {"gameProperties": {}})
    dump_json(jsons / "topBarCounters.json", {"topBarCounters": {
        "shared": [{"label": "Round", "imageUrl": "", "gameProperty": "roundNumber"}],
        "player": [
            {"label": "Honor", "imageUrl": "", "playerProperty": "honor"},
            {"label": "Gold", "imageUrl": "", "playerProperty": "gold"},
        ],
    }})
    dump_json(jsons / "tokens.json", {"tokens": {
        "stayBowed": {
            "label": "Hold bow",
            "left": "8%",
            "top": "78%",
            "width": "3.4vh",
            "height": "3.4vh",
            "imageUrl": toybox_url(f"{FOLDER}/_plugin/{PASCAL}-TokenStayBowed.png"),
            "canBeNegative": False,
        },
        "stayFlip": {
            "label": "Hold flip",
            "left": "22%",
            "top": "78%",
            "width": "3.4vh",
            "height": "3.4vh",
            "imageUrl": toybox_url(f"{FOLDER}/_plugin/{PASCAL}-TokenStayFlip.png"),
            "canBeNegative": False,
        },
        "green": {
            "label": "+1",
            "left": "72%",
            "top": "4%",
            "width": "4vh",
            "height": "4vh",
            "imageUrl": toybox_url(f"{FOLDER}/_plugin/{PASCAL}-TokenGreen.png"),
            "canBeNegative": True,
        },
        "red": {
            "label": "-1",
            "left": "50%",
            "top": "4%",
            "width": "4vh",
            "height": "4vh",
            "imageUrl": toybox_url(f"{FOLDER}/_plugin/{PASCAL}-TokenRed.png"),
            "canBeNegative": True,
        },
    }})
    dump_json(jsons / "functions.json", {"functions": l5r_functions()})

    refill = [["REFILL_PROVINCE", f"{{{{$PLAYER_N}}}}Province{index}"] for index in range(1, 5)]
    actions = {
        "drawFate": [[
            "COND",
            ["GROUP_EMPTY", "{{$PLAYER_N}}Fate"],
            ["LOG", "{{$ALIAS_N}} tried to draw from an empty fate deck."],
            ["TRUE"],
            [
                ["MOVE_STACKS", "{{$PLAYER_N}}Fate", "{{$PLAYER_N}}Hand", 1, "bottom"],
                ["LOG", "{{$ALIAS_N}} drew a fate card."],
            ],
        ]],
        "shuffleBoth": [
            ["SHUFFLE_GROUP", "{{$PLAYER_N}}Dynasty"],
            ["SHUFFLE_GROUP", "{{$PLAYER_N}}Fate"],
            ["LOG", "{{$ALIAS_N}} shuffled dynasty and fate."],
        ],
        "refillDynasty": refill + [["LOG", "{{$ALIAS_N}} refilled empty provinces."]],
        "refresh": [["START_TURN", "$PLAYER_N"]],
        "spendCard": [["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 90], ["LOG", "{{$ALIAS_N}} bowed {{$ACTIVE_FACE.name}}."]],
        "readyCard": [
            ["COND",
             ["EQUAL", "$ACTIVE_CARD.rotation", 180],
             [
                 ["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 0],
                 ["SET", "/cardById/$ACTIVE_CARD_ID/tokens/stayBowed", 0],
                 ["LOG", "{{$ALIAS_N}} restored {{$ACTIVE_FACE.name}} to honor."],
             ],
             ["TRUE"],
             [
                 ["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 0],
                 ["LOG", "{{$ALIAS_N}} straightened {{$ACTIVE_FACE.name}}."],
             ]],
        ],
        "invertCard": [
            ["COND",
             ["EQUAL", "$ACTIVE_CARD.rotation", 180],
             [
                 ["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 0],
                 ["SET", "/cardById/$ACTIVE_CARD_ID/tokens/stayBowed", 0],
                 ["LOG", "{{$ALIAS_N}} restored {{$ACTIVE_FACE.name}} to honor."],
             ],
             ["TRUE"],
             [
                 ["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 180],
                 ["SET", "/cardById/$ACTIVE_CARD_ID/tokens/stayBowed", 1],
                 ["LOG", "{{$ALIAS_N}} dishonored {{$ACTIVE_FACE.name}} (will stay bowed)."],
             ]],
        ],
        "flipCard": [["FLIP", "$ACTIVE_CARD_ID"]],
        "discardCard": [["DISCARD", "$ACTIVE_CARD_ID"]],
        "detachCard": [["DETACH", "$ACTIVE_CARD_ID"]],
        "toggleStayBowed": [
            ["COND",
             ["AND",
              ["EQUAL", "$ACTIVE_CARD.tokens.stayBowed", 1],
              ["EQUAL", "$ACTIVE_CARD.rotation", 180]],
             ["LOG", "{{$ACTIVE_FACE.name}} is dishonored — honor them (I) before releasing the bow lock."],
             ["EQUAL", "$ACTIVE_CARD.tokens.stayBowed", 1],
             [["SET", "/cardById/$ACTIVE_CARD_ID/tokens/stayBowed", 0], ["LOG", "{{$ALIAS_N}} will unbow {{$ACTIVE_FACE.name}}."]],
             ["TRUE"],
             [["SET", "/cardById/$ACTIVE_CARD_ID/tokens/stayBowed", 1], ["LOG", "{{$ALIAS_N}} held {{$ACTIVE_FACE.name}} bowed."]]],
        ],
        "toggleStayFlip": [
            ["COND",
             ["EQUAL", "$ACTIVE_CARD.tokens.stayFlip", 1],
             [["SET", "/cardById/$ACTIVE_CARD_ID/tokens/stayFlip", 0], ["LOG", "{{$ALIAS_N}} will flip {{$ACTIVE_FACE.name}}."]],
             ["TRUE"],
             [["SET", "/cardById/$ACTIVE_CARD_ID/tokens/stayFlip", 1], ["LOG", "{{$ALIAS_N}} held {{$ACTIVE_FACE.name}} from flipping."]]],
        ],
        "claimFavor": [["CLAIM_FAVOR", "$PLAYER_N"]],
        "returnFavor": [
            ["VAR", "$FAVOR", ["ONE_CARD", "$C", ["EQUAL", "$C.databaseId", "l5r-imperial-favor"]]],
            ["COND",
             ["NOT_EQUAL", "$FAVOR", None],
             [
                 ["MOVE_CARD", "$FAVOR.id", "sharedFavor", 0],
                 ["RESET_FAVOR_ART", "$FAVOR.id"],
                 ["LOG", "{{$ALIAS_N}} returned the Imperial Favor."],
             ]],
        ],
    }
    dump_json(jsons / "actionLists.json", {"actionLists": actions})
    dump_json(jsons / "hotkeys.json", {"hotkeys": {
        "game": [
            {"key": "D", "actionList": "drawFate", "label": "Draw fate"},
            {"key": "Y", "actionList": "refillDynasty", "label": "Refill provinces"},
            {"key": "R", "actionList": "refresh", "label": "Unbow + flip provinces"},
            {"key": "S", "actionList": "shuffleBoth", "label": "Shuffle both decks"},
            {"key": "V", "actionList": "claimFavor", "label": "Claim Imperial Favor"},
        ],
        "card": [
            {"key": "B", "actionList": "spendCard", "label": "Bow"},
            {"key": "U", "actionList": "readyCard", "label": "Straighten"},
            {"key": "I", "actionList": "invertCard", "label": "Dishonor / honor"},
            {"key": "F", "actionList": ["FLIP", "$ACTIVE_CARD_ID"], "label": "Flip"},
            {"key": "X", "actionList": ["DISCARD", "$ACTIVE_CARD_ID"], "label": "Discard"},
            {"key": "A", "actionList": ["DETACH", "$ACTIVE_CARD_ID"], "label": "Detach"},
            {"key": "H", "actionList": "toggleStayBowed", "label": "Hold bow"},
            {"key": "J", "actionList": "toggleStayFlip", "label": "Hold flip"},
        ],
        "token": [
            {"key": "1", "tokenType": "green", "label": "Green +1"},
            {"key": "2", "tokenType": "red", "label": "Red +1"},
        ],
    }})
    dump_json(jsons / "pluginMenu.json", {"pluginMenu": {"options": [
        {"label": "Draw fate", "actionList": "drawFate"},
        {"label": "Refill provinces", "actionList": "refillDynasty"},
        {"label": "Unbow + flip provinces", "actionList": "refresh"},
        {"label": "Shuffle both decks", "actionList": "shuffleBoth"},
        {"label": "Claim Imperial Favor", "actionList": "claimFavor"},
        {"label": "Return Imperial Favor", "actionList": "returnFavor"},
    ]}})
    moves = [
        "playerSPlay",
        "playerSHoldings",
        "playerSStronghold",
        "playerSSensei",
        "playerSProvince1",
        "playerSProvince2",
        "playerSProvince3",
        "playerSProvince4",
        "playerSHand",
        "playerSDynasty",
        "playerSFate",
        "playerSDynastyDiscard",
        "playerSFateDiscard",
        "playerSFavor",
        "playerSRemoved",
        "playerLPlay",
        "playerLHoldings",
        "sharedFavor",
        "sharedSetAside",
    ]
    dump_json(jsons / "cardMenu.json", {"cardMenu": {"moveToGroupIds": moves, "options": [
        {"label": "Bow", "actionList": "spendCard"},
        {"label": "Straighten", "actionList": "readyCard"},
        {"label": "Dishonor / honor", "actionList": "invertCard"},
        {"label": "Flip", "actionList": "flipCard"},
        {"label": "Hold bow / allow unbow", "actionList": "toggleStayBowed"},
        {"label": "Hold flip / allow flip", "actionList": "toggleStayFlip"},
        {"label": "Discard", "actionList": "discardCard"},
        {"label": "Detach", "actionList": "detachCard"},
    ]}})
    dump_json(jsons / "groupMenu.json", {"groupMenu": {"moveToGroupIds": moves, "options": []}})
    dump_json(jsons / "browse.json", {"browse": {
        "filterPropertySideA": "type",
        "filterValuesSideA": BROWSE_FILTER_TYPES,
        "textPropertiesSideA": ["name", "packName", "clan", "legal", "text"],
    }})
    deck_columns = [
        ("name", "Name"),
        ("type", "Type"),
        ("clan", "Clan"),
        ("legal", "Legality"),
        ("cost", "Gold"),
        ("force", "Force"),
        ("chi", "Chi"),
        ("packName", "Set"),
    ]
    spawn = [
        "playerNDynasty",
        "playerNFate",
        "playerNStronghold",
        "playerNSensei",
        "playerNPlay",
        "playerNHoldings",
        "playerNWind",
    ]
    dump_json(jsons / "deckbuilder.json", {"deckbuilder": {
        "addButtons": [1, 2, 3],
        "columns": [{"propName": name, "label": label} for name, label in deck_columns],
        "spawnGroups": [{"loadGroupId": gid, "label": gid.replace("playerN", "My ")} for gid in spawn],
    }})
    dump_json(jsons / "spawnExistingCardModal.json", {"spawnExistingCardModal": {
        "columnProperties": [name for name, _ in deck_columns],
        "loadGroupIds": [gid.replace("playerN", "player1") for gid in spawn] + ["player1Hand", "player1Province1", "sharedFavor"],
    }})
    face = {}
    for key, label in (
        ("zoomImageUrl", "Preview art"),
        ("clan", "Clan"),
        ("legal", "Legality"),
        ("cost", "Gold cost"),
        ("focus", "Focus"),
        ("force", "Force"),
        ("chi", "Chi"),
        ("personalHonor", "Personal honor"),
        ("honorReq", "Honor req"),
        ("goldProduction", "Gold production"),
        ("provinceStrength", "Province strength"),
        ("startingHonor", "Starting honor"),
        ("rarity", "Rarity"),
        ("artist", "Artist"),
        ("flavour", "Flavor"),
        ("text", "Text"),
        ("packName", "Set"),
        ("set", "Set code"),
        ("loadGroupId", "Load group"),
    ):
        face[key] = {"label": label, "type": "string", "default": ""}
    dump_json(jsons / "faceProperties.json", {"faceProperties": face})
    dump_json(jsons / "cardProperties.json", {"cardProperties": {}})
    dump_json(jsons / "keywordReminders.json", {"keywordReminders": reminder_glossary()})
    dump_json(jsons / "defaultActions.json", {"defaultActions": []})
    dump_json(jsons / "automation.json", {"automation": {
        "postNewGameActionList": [
            ["LOG", "Legend of the Five Rings table created. Load a starter or a community deck (clan, then format). Honor and gold live in the top bar. No rules are enforced."],
            ["LOAD_CARDS", ["LIST",
                {"databaseId": "l5r-imperial-favor", "loadGroupId": "sharedFavor", "quantity": 1},
            ]],
            ["FOR_EACH_KEY_VAL", "$CARD_ID", "$CARD", "$GAME.cardById",
             ["COND",
              ["EQUAL", "$CARD.databaseId", "l5r-imperial-favor"],
              [
                  ["SET", "/cardById/{{$CARD_ID}}/sides/A/imageUrl", f"{FOLDER}/_plugin/{PASCAL}-ImperialFavorGeneric.jpg"],
                  ["SET", "/cardById/{{$CARD_ID}}/sides/A/zoomImageUrl", f"{FOLDER}/_plugin/{PASCAL}-ImperialFavorGeneric.jpg"],
              ]]],
        ],
        "postLoadActionList": post_load_actions(),
        "postMoveStackActionList": [
            ["COND",
             ["AND",
              ["IN_STRING", "$ORIG_GROUP_ID", "Province"],
              ["NOT_EQUAL", "$ORIG_GROUP_ID", "$DEST_GROUP_ID"]],
             [["REFILL_PROVINCE", "$ORIG_GROUP_ID"]]],
            ["COND",
             ["AND",
              ["EQUAL", "$ORIG_PARENT_CARD.databaseId", "l5r-imperial-favor"],
              ["IN_STRING", "$DEST_GROUP_ID", "Play"]],
             [
                 ["MOVE_CARD", "$ORIG_PARENT_CARD.id", "{{$DEST_PARENT_CARD.controller}}Favor", 0],
                 ["APPLY_FAVOR_ART", "$DEST_PARENT_CARD.controller", "$ORIG_PARENT_CARD.id"],
                 ["LOG", "The Imperial Favor snapped to that clan's favor slot."],
             ]],
            ["COND",
             ["AND",
              ["EQUAL", "$ORIG_PARENT_CARD.databaseId", "l5r-imperial-favor"],
              ["IN_STRING", "$DEST_GROUP_ID", "Favor"],
              ["NOT_EQUAL", "$DEST_GROUP_ID", "sharedFavor"]],
             [
                 ["VAR", "$OWNER", ["REGEX_REPLACE", "$DEST_GROUP_ID", "(player[0-9]+).*", "\\1"]],
                 ["APPLY_FAVOR_ART", "$OWNER", "$ORIG_PARENT_CARD.id"],
             ]],
            ["COND",
             ["AND",
              ["EQUAL", "$ORIG_PARENT_CARD.databaseId", "l5r-imperial-favor"],
              ["EQUAL", "$DEST_GROUP_ID", "sharedFavor"]],
             [["RESET_FAVOR_ART", "$ORIG_PARENT_CARD.id"]]],
            ["COND",
             ["AND",
              ["EQUAL", "$ORIG_PARENT_CARD.databaseId", "l5r-imperial-favor"],
              ["OR",
               ["IN_STRING", "$DEST_GROUP_ID", "Discard"],
               ["IN_STRING", "$DEST_GROUP_ID", "Removed"]]],
             [
                 ["MOVE_CARD", "$ORIG_PARENT_CARD.id", "sharedFavor", 0],
                 ["RESET_FAVOR_ART", "$ORIG_PARENT_CARD.id"],
                 ["LOG", "The Imperial Favor returned to the middle."],
             ]],
        ],
        "gameRules": {
            "refillEmptyProvince": {
                "type": "trigger",
                "listenTo": ["/groupById/*/stackIds"],
                "condition": [
                    "AND",
                    ["IN_STRING", "$TARGET_ID", "Province"],
                    ["EQUAL", ["LENGTH", "$TARGET.stackIds"], 0],
                    ["NOT", ["EQUAL", "$TARGET.destroyed", True]],
                ],
                "then": [["REFILL_PROVINCE", "$TARGET_ID"]],
            },
            "revealEvent": {
                "type": "trigger",
                "listenTo": ["/cardById/*/currentSide"],
                "condition": [
                    "AND",
                    ["IN_STRING", "$TARGET.groupId", "Province"],
                    ["EQUAL", "$TARGET.currentSide", "A"],
                    ["NOT_EQUAL", ["PREV", "$TARGET.currentSide"], "A"],
                    ["EQUAL", "$TARGET.currentFace.type", "Event"],
                ],
                "then": [
                    ["FADE_TEXT_GAME", "EVENT"],
                    ["LOG", "{{$TARGET.currentFace.name}} is an Event."],
                    ["ADD_FACEDOWN_DYNASTY", "$TARGET.groupId"],
                ],
            },
            "startOfTurn": {
                "type": "trigger",
                "listenTo": ["/stepId"],
                "condition": [
                    "AND",
                    ["EQUAL", "$GAME.stepId", "dynastyStep"],
                    ["NOT_EQUAL", ["PREV", "$GAME.stepId"], "dynastyStep"],
                ],
                "then": [
                    ["COND",
                     ["EQUAL", ["PREV", "$GAME.stepId"], "endStep"],
                     [
                         ["VAR", "$NEXT", ["NEXT_PLAYER", "$GAME.firstPlayer"]],
                         ["COND",
                          ["DEFINED", "$GAME.playerInfo.{{$NEXT}}.id"],
                          [["SET", "/firstPlayer", "$NEXT"]]],
                     ]],
                    ["COND",
                     ["DEFINED", "$GAME.playerInfo.{{$GAME.firstPlayer}}.id"],
                     ["START_TURN", "$GAME.firstPlayer"]],
                ],
            },
        },
    }})
    dump_json(jsons / "labels.json", {"labels": {}})
    dump_json(jsons / "preferences.json", {"preferences": {"game": [], "player": []}})
    dump_json(jsons / "prompts.json", {"prompts": {}})
    dump_json(jsons / "touchBar.json", {"touchBar": []})
    dump_json(jsons / "closeRoomOptions.json", {"closeRoomOptions": [{"label": "Just close", "actionList": []}]})
    dump_json(jsons / "clearTableOptions.json", {"clearTableOptions": [
        *[{"label": f"Player {n} wins", "actionList": ["SET", "/victoryState", f"player{n}Win"]} for n in range(1, 9)],
        {"label": "Tie", "actionList": ["SET", "/victoryState", "tie"]},
        {"label": "Incomplete", "actionList": ["SET", "/victoryState", "incomplete"]},
    ]})
    dump_json(jsons / "preBuiltDecks.json", decks)
    dump_json(jsons / "deckMenu.json", menu)


def tsv_row(card: dict[str, str]) -> dict[str, str]:
    return {key: card.get(key, "") if isinstance(card.get(key, ""), str) else "" for key in COLUMNS}


def type_key_from_title(title: str) -> str:
    lowered = (title or "").strip().lower()
    for key, label in TYPE_TITLE.items():
        if label.lower() == lowered:
            return key
    return lowered


def upgrade_tsv_art() -> int:
    """Point the existing catalog at the largest same-card file; fetch Oracle masters for weak scans."""
    tsv_path = OUT / "tsvs" / "cards.tsv"
    lines = tsv_path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    cards: list[dict[str, str]] = []
    for line in lines[1:]:
        if not line.strip():
            continue
        cols = line.split("\t")
        row = {header[i]: cols[i] if i < len(cols) else "" for i in range(len(header))}
        row["typeKey"] = type_key_from_title(row.get("type") or "")
        cards.append(row)
    local_up = prefer_highest_quality_art(cards)
    reused = reuse_collected_art(cards)
    oracle_index = fetch_oracle_index(SOURCE / "oracle_cards.json", skip=True)
    stats = apply_oracle_art(cards, oracle_index, download=True)
    local_up += prefer_highest_quality_art(cards)
    for card in cards:
        if not card.get("imageUrl") and card["typeKey"] not in {"token", "playmat"}:
            card["imageUrl"] = PLACEHOLDER_REL
            card["zoomImageUrl"] = PLACEHOLDER_REL
    out = ["\t".join(header)]
    for card in cards:
        out.append("\t".join(card.get(col, "") for col in header))
    tsv_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    placeholders = sum(1 for card in cards if card.get("imageUrl") == PLACEHOLDER_REL)
    source = OUT / "SOURCE.txt"
    if source.exists():
        lines = source.read_text(encoding="utf-8").splitlines()
        rewritten = []
        for line in lines:
            if line.startswith("Art:"):
                rewritten.append(
                    "Art: largest same-card local file (Master when present), then Oracle master for weak/missing scans."
                )
            else:
                rewritten.append(line)
        source.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    print(
        f"L5R art upgrade: {local_up} local promotions, {reused} reused, "
        f"{stats['matched']} Oracle masters, {placeholders} placeholders."
    )
    return 0


def main() -> int:
    if "--upgrade-art" in sys.argv:
        return upgrade_tsv_art()

    skip_oracle = "--skip-oracle" in sys.argv
    skip_l5rdb = "--skip-l5rdb" in sys.argv
    keep_layouts = "--keep-layouts" in sys.argv or "--rewrite-layouts" not in sys.argv

    cards, catalog = merge_catalogs()
    cards.extend(extra_cards())
    local_art = apply_local_art(cards)
    reused = reuse_collected_art(cards)
    oracle_index = fetch_oracle_index(SOURCE / "oracle_cards.json", skip_oracle)
    stats = apply_oracle_art(cards, oracle_index)
    prefer_highest_quality_art(cards)
    for card in cards:
        if not card["imageUrl"] and card["typeKey"] not in {"token", "playmat"}:
            card["imageUrl"] = PLACEHOLDER_REL
            card["zoomImageUrl"] = PLACEHOLDER_REL
    l5rdb = fetch_l5rdb(SOURCE / "l5rdb", skip=skip_l5rdb)
    decks, menu, deck_errors = convert_decks(cards, l5rdb)

    write_tsv([tsv_row(card) for card in cards], COLUMNS, OUT / "tsvs" / "cards.tsv")
    backs = write_plugin_art()
    write_plugin_jsons(cards, decks, menu, backs, keep_layouts=keep_layouts)

    playable = sum(1 for card in cards if card["typeKey"] not in {"token", "playmat"})
    placeholders = sum(1 for card in cards if card.get("imageUrl") == PLACEHOLDER_REL)
    community_decks = sum(1 for key in decks["preBuiltDecks"] if key.startswith("l5rdb-"))
    missing_notes = [line for line in deck_errors if "missing" in line or "no cards" in line]
    (OUT / "SOURCE.txt").write_text(
        "\n".join([
            f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from Twenty Festivals / Emerald SnM XML, Oracle of the Void, and L5R DB.",
            f"Official XML: {catalog['xml']}",
            "Art: largest same-card local file (Master when present), then Oracle master for weak/missing scans.",
            "Playmats / lobby: Sun and Moon clan backgrounds. Card back: Lackey L5R HQ.",
            "Community Onyx / Shattered Empire / Chaos Reigns sets included. Tabletop only — no rules engine.",
            "",
            f"Cards: {playable}  official XML {catalog['official']}  community XML {catalog['community']}",
            f"Art: local {local_art}  reused {reused}  Oracle {stats['matched']}  placeholders {placeholders}  cache titles {stats['oracle']}",
            f"Decks: {len(decks['preBuiltDecks'])} total, {community_decks} from L5R DB",
            *([f"Deck notes: {len(missing_notes)} (see importer printout)"] if missing_notes else []),
        ]) + "\n",
        encoding="utf-8",
    )
    print(
        f"L5R: {playable} cards ({catalog['official']} official + {catalog['community']} community), "
        f"{local_art} pack faces, {reused} reused, {stats['matched']} Oracle, "
        f"{len(decks['preBuiltDecks'])} decks ({community_decks} community)."
    )
    print(f"Deck notes: {len(deck_errors)}")
    for line in deck_errors[:40]:
        print(f"  deck: {line}")
    if len(deck_errors) > 40:
        print(f"  … {len(deck_errors) - 40} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
