#!/usr/bin/env python3
"""Build a Force of Will tabletop plugin from the local FoWind / TCG Arena tables.

Text catalog: plugins/ForceOfWill/cards.json
Art index:    plugins/ForceOfWill/cards_fow.json
Faces:        FoWind S3 (fowsim) + TCG Arena token images
Starters:     Fandom wiki card lists (quantities) nested by cluster

  python3 plugins/scripts/import_force_of_will.py
  python3 plugins/scripts/collect_hosted_images.py force-of-will
  python3 plugins/scripts/import_force_of_will.py --remap-missing
  python3 plugins/scripts/import_force_of_will.py --decks-only
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from image_names import TOYBOX_PREFIX, clear_image_url_prefix, lobby_art_rel, stamp_lobby_art, toybox_url  # noqa: E402
from lackey_tabletop import (  # noqa: E402
    dump_json,
    group_types,
    region,
    sanitize,
    slug,
    standard_actions,
    standard_functions,
    write_color_png,
    write_tsv,
)

SOURCE = ROOT / "ForceOfWill"
OUT = ROOT / "force-of-will"
IMAGES = ROOT / "images"
FOLDER = "force-of-will"
PASCAL = "ForceOfWill"
PLACEHOLDER_REL = f"{FOLDER}/missing/ForceOfWill-Missing-NoArt.png"
S3_CARD = "https://fowsim.s3.amazonaws.com/media/cards/{id}.jpg"
S3_PLACEHOLDER = "https://fowsim.s3.amazonaws.com/static/img/none.000fb66afe5c.png"
S3_CARDBACK = "https://fowsim.s3.amazonaws.com/static/img/pack/card_back.fd17635728de.png"
OFFICIAL_LOGO = "https://www.fowtcg.com/images/common/logo.png"
ARENA_BANNER = "https://niebvelungen.github.io/TCG-Arena-FoW/Images/menu_background.png"
ARENA_PLAYMAT = "https://niebvelungen.github.io/TCG-Arena-FoW/Images/Masterpiece_03_playmat.png"
ARENA_DECKS = "https://raw.githubusercontent.com/Niebvelungen/TCG-Arena-FoW/main/decks.json"
ARENA_MISSING = "https://raw.githubusercontent.com/Niebvelungen/TCG-Arena-FoW/main/missing_images.txt"
FANDOM_API = "https://force-of-will-tcg.fandom.com/api.php"
SKIP_STARTER_PAGES = {"Starter Decks", "Force of Will Half Deck", "Category:Starter Deck"}
CARD_ID_RE = re.compile(
    r"\b("
    r"[A-Z]{2,}[A-Z0-9]*-(?:[A-Z0-9]+-)+\d+[A-Z0-9]*"
    r"|[A-Z]{2,}[A-Z0-9]*-\d+[A-Z0-9]*"
    r"|[A-Z]-\d+"
    r"|[1-9]-\d{3}"
    r")\b",
    re.I,
)
CLUSTER_ORDER = [
    "Valhalla",
    "Grimm",
    "Alice",
    "Lapis",
    "Reiya",
    "New Valhalla",
    "Alice Origin",
    "Saga",
    "Duel",
    "Hero",
    "Trinity",
    "Arcana Battle Colosseum",
    "Masterpiece",
    "Evil",
]
PREFIX_CLUSTER = (
    ("SDAO", "Alice Origin"),
    ("GITS", "Alice Origin"),
    ("VS01", "Alice"),
    ("SDL", "Lapis"),
    ("SDR", "Reiya"),
    ("SDV", "New Valhalla"),
    ("DSD", "Duel"),
    ("HSD", "Hero"),
    ("TSD", "Trinity"),
    ("ESD", "Evil"),
    ("ABC", "Arcana Battle Colosseum"),
    ("CMF", "Grimm"),
    ("TAT", "Alice"),
)
SKIP_PREFIXES = ("ABC-BG", "ABC-RD", "ABC-RG", "ABC-WD", "ABC-WB")
USER_AGENT = "HundredAcreClub/1.0 (private tabletop image collect; +https://hundredacre.club)"

COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "packName",
    "set",
    "loadGroupId",
    "cluster",
    "colour",
    "race",
    "cost",
    "atk",
    "defense",
    "rarity",
    "artist",
    "divinity",
    "willpower",
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


def to_jpeg(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["sips", "-s", "format", "jpeg", str(src), "--out", str(dest)], check=True, capture_output=True)


def join_list(value) -> str:
    if isinstance(value, list):
        return " / ".join(sanitize(str(part)) for part in value if str(part).strip())
    return sanitize(str(value or ""))


def norm_type(value) -> str:
    text = join_list(value).replace("_", " ")
    return text or "Card"


def is_stone(type_name: str) -> bool:
    return "magic stone" in type_name.lower()


def is_ruler_row(type_name: str) -> bool:
    lower = type_name.lower()
    return any(key in lower for key in ("ruler", "warden", "order"))


def load_group(type_name: str, token: bool) -> str:
    if token:
        return "playerNPlay"
    if is_stone(type_name):
        return "playerNStoneDeck"
    if is_ruler_row(type_name):
        return "playerNRuler"
    return "playerNDeck"


def image_from_fow(record: dict | None, side: str) -> str:
    if not record:
        return ""
    face = record.get("face") or {}
    slot = face.get(side) or {}
    return sanitize(slot.get("image") or "")


def known_missing(card_id: str, missing: set[str]) -> bool:
    if card_id in missing:
        return True
    return card_id.startswith(SKIP_PREFIXES)


def flatten_catalog(data: dict) -> list[dict]:
    rows: list[dict] = []
    seen: dict[str, int] = {}
    for cluster in data.get("fow", {}).get("clusters") or []:
        cluster_name = sanitize(cluster.get("name") or "Unknown")
        for card_set in cluster.get("sets") or []:
            set_code = sanitize(card_set.get("code") or card_set.get("name") or "UNK")
            set_name = sanitize(card_set.get("name") or set_code)
            for raw in card_set.get("cards") or []:
                card_id = sanitize(raw.get("id") or "")
                if not card_id:
                    continue
                seen[card_id] = seen.get(card_id, 0) + 1
                database_id = card_id if seen[card_id] == 1 else f"{card_id}-{seen[card_id]}"
                rows.append({
                    "id": card_id,
                    "databaseId": database_id,
                    "name": sanitize(str(raw.get("name") or card_id)),
                    "type": norm_type(raw.get("type")),
                    "race": join_list(raw.get("race")),
                    "cost": sanitize(str(raw.get("cost") or "")),
                    "colour": join_list(raw.get("colour")),
                    "atk": sanitize(str(raw.get("ATK") or raw.get("atk") or "")),
                    "defense": sanitize(str(raw.get("DEF") or raw.get("def") or "")),
                    "text": " / ".join(sanitize(str(part)) for part in (raw.get("abilities") or []) if str(part).strip()),
                    "divinity": sanitize(str(raw.get("divinity") or "")),
                    "willpower": sanitize(str(raw.get("willpower") or "")),
                    "flavour": sanitize(str(raw.get("flavour") or "")),
                    "artist": sanitize(str(raw.get("artist") or "")),
                    "rarity": sanitize(str(raw.get("rarity") or "")),
                    "cluster": cluster_name,
                    "set": set_code,
                    "packName": set_name,
                    "token": False,
                })
    return rows


def face_row(src: dict, image_url: str, card_back: str, database_id: str | None = None) -> dict[str, str]:
    return {
        "databaseId": database_id or src["databaseId"],
        "name": src["name"],
        "imageUrl": image_url,
        "cardBack": card_back,
        "type": src["type"],
        "packName": src["packName"],
        "set": src["set"],
        "loadGroupId": load_group(src["type"], src["token"]),
        "cluster": src.get("cluster") or ("Tokens" if src["token"] else ""),
        "colour": src.get("colour") or "",
        "race": src.get("race") or "",
        "cost": src.get("cost") or "",
        "atk": src.get("atk") or "",
        "defense": src.get("defense") or "",
        "rarity": src.get("rarity") or "",
        "artist": src.get("artist") or "",
        "divinity": src.get("divinity") or "",
        "willpower": src.get("willpower") or "",
        "flavour": src.get("flavour") or "",
        "text": src.get("text") or "",
    }


def quote_http_url(url: str) -> str:
    # FoWind S3 403s on the "*" alternate-art suffix; the base id is the same face.
    url = url.replace("*", "")
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/%+!*'(),-_.:@")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def resolve_image(card_id: str, fow: dict, missing: set[str], side: str = "front") -> str:
    if known_missing(card_id, missing):
        return PLACEHOLDER_REL
    url = image_from_fow(fow.get(card_id), side)
    if url:
        return quote_http_url(url)
    if side == "back":
        url = image_from_fow(fow.get(card_id), "back")
        if url:
            return quote_http_url(url)
    return S3_CARD.format(id=urllib.parse.quote(card_id, safe="-_*"))


def build_cards(catalog: list[dict], fow: dict, missing: set[str]) -> tuple[list[dict[str, str]], dict[str, int]]:
    by_id: dict[str, dict] = {}
    for row in catalog:
        by_id.setdefault(row["id"], row)

    paired_j: set[str] = set()
    cards: list[dict[str, str]] = []
    stats = {"catalog": len(catalog), "paired": 0, "tokens": 0, "placeholder": 0}

    for row in catalog:
        card_id = row["id"]
        if card_id in paired_j:
            continue
        j_id = f"{card_id}J"
        partner = by_id.get(j_id) if row["databaseId"] == card_id and not card_id.endswith("J") else None
        # Pair XXX + XXXJ when both exist. Unpaired J-rulers stay single-faced.
        if partner is not None:
            paired_j.add(j_id)
            front = resolve_image(card_id, fow, missing, "front")
            back = resolve_image(j_id, fow, missing, "front")
            if not back or back == PLACEHOLDER_REL:
                back = image_from_fow(fow.get(card_id), "back") or resolve_image(j_id, fow, missing, "front")
            cards.append(face_row(row, front, "multi_sided"))
            cards.append(face_row(partner, back, "multi_sided", database_id=row["databaseId"]))
            stats["paired"] += 1
            if PLACEHOLDER_REL in {front, back}:
                stats["placeholder"] += 1
            continue
        image = resolve_image(card_id, fow, missing, "front")
        cards.append(face_row(row, image, "default"))
        if image == PLACEHOLDER_REL:
            stats["placeholder"] += 1

    seen_ids = {card["databaseId"] for card in cards}
    for key, record in fow.items():
        if not isinstance(record, dict):
            continue
        if not (record.get("isToken") or record.get("type") == "Token"):
            continue
        token_id = sanitize(record.get("id") or key)
        if token_id in seen_ids:
            continue
        image = image_from_fow(record, "front")
        image = quote_http_url(image) if image.startswith("http") else (image or PLACEHOLDER_REL)
        token = {
            "id": token_id,
            "databaseId": token_id,
            "name": sanitize(record.get("name") or token_id),
            "type": "Token",
            "race": "",
            "cost": str(record.get("cost") or ""),
            "colour": join_list(record.get("Colors") or record.get("Color identity") or []),
            "atk": "",
            "defense": "",
            "text": "",
            "divinity": "",
            "willpower": "",
            "flavour": "",
            "artist": "",
            "rarity": "",
            "cluster": "Tokens",
            "set": "TOKEN",
            "packName": "Tokens",
            "token": True,
        }
        cards.append(face_row(token, image, "default"))
        seen_ids.add(token_id)
        stats["tokens"] += 1
    stats["rows"] = len(cards)
    stats["unique"] = len({card["databaseId"] for card in cards})
    return cards, stats


def load_group_for_deck(category: str, card: dict[str, str]) -> str:
    cat = (category or "").lower().replace("_", " ")
    if cat in {"ruler", "warden", "sub ruler"}:
        return "playerNRuler"
    if "magic stone" in cat or cat == "magic stones":
        return "playerNStoneDeck"
    if cat in {"extra deck", "sideboard"}:
        return "playerNRemoved"
    return card.get("loadGroupId") or "playerNDeck"


def fandom_api(**kwargs) -> dict:
    query = urllib.parse.urlencode({**kwargs, "format": "json"})
    req = urllib.request.Request(f"{FANDOM_API}?{query}", headers={"User-Agent": USER_AGENT})
    return json.loads(urllib.request.urlopen(req, timeout=45).read().decode("utf-8"))


def fandom_category_titles(category: str) -> list[str]:
    titles: list[str] = []
    cont = None
    while True:
        kwargs: dict = {"action": "query", "list": "categorymembers", "cmtitle": category, "cmlimit": "100"}
        if cont:
            kwargs["cmcontinue"] = cont
        data = fandom_api(**kwargs)
        titles.extend(item["title"] for item in data.get("query", {}).get("categorymembers", []))
        cont = (data.get("continue") or {}).get("cmcontinue")
        if not cont:
            return titles


def fandom_wikitext(title: str) -> str:
    data = fandom_api(action="parse", page=title, prop="wikitext")
    return ((data.get("parse") or {}).get("wikitext") or {}).get("*") or ""


def clean_wiki_title(title: str) -> str:
    text = title
    for prefix in ("Starter Deck : ", "Starter Deck:", "Starter Deck "):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    return sanitize(text)


def first_card_id(cell: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", cell or "", flags=re.I)
    text = re.sub(r"\[\[|\]\]", "", text)
    match = CARD_ID_RE.search(text.replace("&nbsp;", " "))
    return match.group(1).upper() if match else ""


def parse_quantity(cell: str) -> int:
    match = re.search(r"\d+", cell or "")
    return int(match.group(0)) if match else 0


IGNORE_HEADINGS = {
    "information", "gallery", "description", "trivia", "see also", "notes",
    "contents", "card list", "cardlist", "references", "external links",
    "playstyle", "play style",
}
ABC_SIDES = {
    "ABC-SD01": "Elektra",
    "ABC-SD02": "Replicant: Aristella",
    "ABC-SD03": "Gnome",
    "ABC-SD04": "Hyde",
    "ABC-SD05": "Undine",
    "ABC-SD06": "Ki Lua",
    "ABC-SD07": "Efreet",
    "ABC-SD08": "Falchion",
    "ABC-SD09": "Reinhardt",
    "ABC-SD10": "The Lich King",
    "ABC-SD11": "Void",
}


def parse_wiki_tables(page_title: str, wikitext: str) -> list[dict]:
    headings = [(m.end(), sanitize(re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", m.group(1)))) for m in re.finditer(r"^==+\s*(.+?)\s*==+\s*$", wikitext, re.M)]
    decks: list[dict] = []
    for table_match in re.finditer(r"\{\|(.*?)\|\}", wikitext, re.S):
        heading = clean_wiki_title(page_title)
        for pos, label in headings:
            if pos <= table_match.start():
                cleaned = re.sub(r"\s+card lists?$", "", label, flags=re.I).strip()
                if cleaned and cleaned.casefold() not in IGNORE_HEADINGS:
                    heading = cleaned
        rows = []
        for raw_row in re.split(r"\|-", table_match.group(1)):
            cells = [line[1:].strip() for line in raw_row.splitlines() if line.startswith("|") and not line.startswith("|+")]
            if len(cells) < 2 or cells[0].startswith("!"):
                continue
            card_id = first_card_id(cells[0])
            quantity = parse_quantity(cells[1])
            if card_id and quantity:
                rows.append((card_id, quantity))
        if rows:
            side_counts: dict[str, int] = defaultdict(int)
            for card_id, _qty in rows:
                side_key = re.match(r"(ABC-SD\d+)", card_id.upper())
                if side_key and side_key.group(1) in ABC_SIDES:
                    side_counts[side_key.group(1)] += 1
            if side_counts:
                heading = ABC_SIDES[max(side_counts, key=side_counts.get)]
            decks.append({"page": page_title, "label": heading, "rows": rows})
    return decks


def padded_id(card_id: str) -> str:
    match = re.fullmatch(r"([A-Z]+)(\d*)-(\d+)([A-Z]*)", card_id, re.I)
    if not match:
        return ""
    prefix, set_num, number, suffix = match.groups()
    return f"{prefix.upper()}{set_num}-{int(number):03d}{suffix.upper()}"


def resolve_deck_id(card_id: str, known: dict[str, dict[str, str]]) -> str:
    candidates = [card_id]
    if card_id.endswith("J"):
        candidates.append(card_id[:-1])
    padded = padded_id(card_id)
    if padded:
        candidates.append(padded)
        if padded.endswith("J"):
            candidates.append(padded[:-1])
    for candidate in candidates:
        if candidate and candidate in known:
            return candidate
    return ""


def cluster_for_deck(entries: list[dict], known: dict[str, dict[str, str]], first_id: str) -> str:
    counts: dict[str, int] = defaultdict(int)
    for entry in entries:
        cluster = known.get(entry["databaseId"], {}).get("cluster") or ""
        if cluster:
            counts[cluster] += entry["quantity"]
    if counts:
        return max(counts, key=counts.get)
    upper = first_id.upper()
    for prefix, cluster in PREFIX_CLUSTER:
        if upper.startswith(prefix):
            return cluster
    return "Other"


def fetch_fandom_starters() -> list[dict]:
    cache_path = SOURCE / "fandom_starter_wikitext.json"
    refresh = "--refresh-starters" in sys.argv
    cached: dict[str, str] = {}
    if cache_path.exists() and not refresh:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
    titles = [title for title in fandom_category_titles("Category:Starter_Deck") if title not in SKIP_STARTER_PAGES]
    parsed: list[dict] = []
    for index, title in enumerate(titles, start=1):
        try:
            text = cached.get(title) if not refresh else ""
            if not text:
                text = fandom_wikitext(title)
                cached[title] = text
                if index < len(titles):
                    time.sleep(0.2)
            parsed.extend(parse_wiki_tables(title, text))
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, json.JSONDecodeError) as exc:
            parsed.append({"page": title, "label": clean_wiki_title(title), "rows": [], "error": str(exc)})
    cache_path.write_text(json.dumps(cached, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return parsed


def convert_decks(cards: list[dict[str, str]], raw_decks: list | None = None) -> tuple[dict, dict, list[str]]:
    known: dict[str, dict[str, str]] = {}
    for card in cards:
        known.setdefault(card["databaseId"], card)
    errors: list[str] = []
    prebuilt: OrderedDict[str, dict] = OrderedDict()
    grouped: dict[str, dict[str, list[dict]]] = OrderedDict()
    used_ids: dict[str, int] = {}

    for parsed in fetch_fandom_starters():
        page = parsed.get("page") or "Starter"
        label = parsed.get("label") or clean_wiki_title(page)
        rows = parsed.get("rows") or []
        if parsed.get("error"):
            errors.append(f"{page}: {parsed['error']}")
        if not rows:
            if not parsed.get("error"):
                errors.append(f"{page}: no card table")
            continue
        entries = []
        missing = []
        for card_id, quantity in rows:
            database_id = resolve_deck_id(card_id, known)
            if not database_id:
                missing.append(card_id)
                continue
            card = known[database_id]
            entries.append({
                "databaseId": database_id,
                "quantity": quantity,
                "loadGroupId": card.get("loadGroupId") or "playerNDeck",
            })
        if missing:
            errors.append(f"{label}: missing {len(missing)}/{len(rows)} ({', '.join(missing[:8])}{'…' if len(missing) > 8 else ''})")
        if len(entries) < 8 or len(entries) < len(rows) * 0.7:
            errors.append(f"{label}: skipped ({len(entries)} resolved of {len(rows)})")
            continue
        deck_id = slug(f"{clean_wiki_title(page)}-{label}" if label.lower() != clean_wiki_title(page).lower() else label)
        used_ids[deck_id] = used_ids.get(deck_id, 0) + 1
        if used_ids[deck_id] > 1:
            deck_id = f"{deck_id}-{used_ids[deck_id]}"
        display = label if label.lower() != clean_wiki_title(page).lower() else clean_wiki_title(page)
        prebuilt[deck_id] = {"label": display, "cards": entries}
        cluster = cluster_for_deck(entries, known, rows[0][0])
        product = clean_wiki_title(page)
        grouped.setdefault(cluster, OrderedDict())
        grouped[cluster].setdefault(product, []).append({"deckListId": deck_id, "label": display})

    menus = []
    for cluster in CLUSTER_ORDER + [name for name in grouped if name not in CLUSTER_ORDER]:
        products = grouped.get(cluster) or {}
        if not products:
            continue
        node: dict = {"label": cluster}
        singles = []
        nested = []
        for product, decks in products.items():
            if len(decks) == 1:
                item = dict(decks[0])
                item["label"] = product
                singles.append(item)
            else:
                nested.append({"label": product, "deckLists": decks})
        if singles:
            node["deckLists"] = singles
        if nested:
            node["subMenus"] = nested
        menus.append(node)
    return {"preBuiltDecks": dict(prebuilt)}, {"deckMenu": {"subMenus": menus}}, errors


def load_cards_from_tsv() -> list[dict[str, str]]:
    path = OUT / "tsvs" / "cards.tsv"
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    cards = []
    for line in lines[1:]:
        if not line.strip():
            continue
        cols = line.split("\t")
        while len(cols) < len(header):
            cols.append("")
        cards.append({name: cols[index] for index, name in enumerate(header)})
    return cards


def player_groups(player: str) -> dict:
    piles = [
        ("Deck", "Deck", "deck", "Deck", False),
        ("StoneDeck", "Magic Stone Deck", "deck", "StoneDeck", False),
        ("Graveyard", "Graveyard", "discard", "Deck", False),
        ("Hand", "Hand", "hand", "Deck", False),
        ("Ruler", "Ruler", "inPlay", "Deck", True),
        ("Stones", "Magic Stones", "inPlay", "StoneDeck", True),
        ("Play", "Field", "inPlay", "Deck", True),
        ("Standby", "Chant-Standby", "inPlay", "Deck", True),
        ("Removed", "Removed / Extra", "aside", "Deck", False),
    ]
    groups = {}
    for suffix, label, group_type, deck_suffix, in_play in piles:
        enter = {
            "controller": player,
            "deckGroupId": f"{player}{deck_suffix}",
            "discardGroupId": f"{player}Graveyard",
        }
        if in_play:
            enter["inPlay"] = True
        groups[f"{player}{suffix}"] = {
            "groupType": group_type,
            "label": f"Player {player[-1]} {label}",
            "tableLabel": label,
            "onCardEnter": enter,
        }
        if in_play:
            groups[f"{player}{suffix}"]["canHaveAttachments"] = True
    return groups


def write_plugin_art() -> dict[str, str]:
    plugin = IMAGES / FOLDER / "_plugin"
    plugin.mkdir(parents=True, exist_ok=True)
    missing_dir = IMAGES / FOLDER / "missing"
    missing_dir.mkdir(parents=True, exist_ok=True)

    back_png = plugin / f"{PASCAL}-CardbackDefault.png"
    if not back_png.exists() or back_png.stat().st_size == 0:
        fetch(S3_CARDBACK, back_png)
    logo_src = plugin / "_official-logo.png"
    banner_src = plugin / "_arena-banner.png"
    if not logo_src.exists() or logo_src.stat().st_size == 0:
        fetch(OFFICIAL_LOGO, logo_src)
    if not banner_src.exists() or banner_src.stat().st_size == 0:
        fetch(ARENA_BANNER, banner_src)
    to_jpeg(logo_src, IMAGES / lobby_art_rel(FOLDER, "logo"))
    to_jpeg(banner_src, IMAGES / lobby_art_rel(FOLDER, "banner"))

    placeholder = IMAGES / PLACEHOLDER_REL
    write_color_png(placeholder, (28, 24, 40), size=96)

    write_color_png(plugin / f"{PASCAL}-TokenGreen.png", (48, 160, 72))
    write_color_png(plugin / f"{PASCAL}-TokenRed.png", (196, 48, 48))
    return {"default": f"{FOLDER}/_plugin/{PASCAL}-CardbackDefault.png"}


def write_plugin_jsons(cards: list[dict[str, str]], decks: dict, menu: dict, backs: dict[str, str]) -> None:
    jsons = OUT / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    types = sorted({card["type"] for card in cards})
    dump_json(jsons / "main.json", {
        "pluginName": "Force of Will",
        "author": "FoWind / TCG Arena FoW / official catalog",
        "tutorialUrl": "https://www.forceofwind.online/",
        "announcements": [
            "Tabletop plugin from the FoWind / official Force of Will catalog. No rules engine — life, judgment, stones, and recover are shortcuts.",
            "D = draw. T = draw a magic stone. R = recover all. F = flip / judgment. L = life +100. X = graveyard.",
        ],
        "loadPreBuiltOnNewGame": False,
        "backgroundUrl": ARENA_PLAYMAT,
    })
    stamp_lobby_art(jsons, FOLDER)
    clear_image_url_prefix(jsons)
    dump_json(jsons / "cardBacks.json", {"cardBacks": {
        key: {"width": 0.72, "height": 1.0, "imageUrl": rel} for key, rel in backs.items()
    }})
    dump_json(jsons / "cardTypes.json", {"cardTypes": {
        name: {"width": 0.72, "height": 1.0, "tokens": ["green", "red"]} for name in types
    }})
    groups = {
        "sharedSetAside": {
            "groupType": "aside",
            "label": "Set Aside",
            "tableLabel": "Set Aside",
            "onCardEnter": {"controller": "shared"},
        }
    }
    groups.update(player_groups("player1"))
    groups.update(player_groups("player2"))
    dump_json(jsons / "groups.json", {"groups": groups})

    layout_regions = [
        ("playerN+1Hand", "fan", "0%", "0%", "50%", "9%"),
        ("playerN+1Ruler", "row", "50%", "0%", "12%", "12%"),
        ("playerN+1Stones", "row", "62%", "0%", "13%", "12%"),
        ("playerN+1Play", "free", "0%", "12%", "75%", "16%"),
        ("playerNPlay", "free", "0%", "32%", "50%", "18%"),
        ("playerNRuler", "row", "50%", "32%", "12%", "18%"),
        ("playerNStones", "row", "62%", "32%", "13%", "18%"),
        ("playerNStandby", "row", "0%", "51%", "48%", "10%"),
        ("playerNRemoved", "pile", "48%", "51%", "27%", "10%"),
        ("playerNHand", "fan", "0%", "82%", "58%", "17%"),
        ("playerN+1Deck", "pile", "76%", "8%", "11%", "12%"),
        ("playerN+1Graveyard", "pile", "88%", "8%", "11%", "12%"),
        ("playerN+1StoneDeck", "pile", "76%", "21%", "11%", "10%"),
        ("sharedSetAside", "pile", "88%", "21%", "11%", "10%"),
        ("playerNStoneDeck", "pile", "76%", "52%", "11%", "10%"),
        ("playerNDeck", "pile", "76%", "63%", "11%", "14%"),
        ("playerNGraveyard", "pile", "88%", "63%", "11%", "14%"),
    ]
    regions = {}
    for group_id, rtype, left, top, width, height in layout_regions:
        extra = {"disableDroppableAttachments": True} if rtype == "fan" else {}
        regions[group_id] = region(group_id, rtype, left, top, width, height, **extra)
    dump_json(jsons / "layouts.json", {"layouts": {"default": {
        "cardSize": 10,
        "rowSpacing": 2,
        "chat": {"left": "76%", "top": "78%", "width": "23%", "height": "21%"},
        "regions": regions,
        "tableButtons": {
            "drawDeck": {"actionList": "drawDeck", "label": "Draw", "left": "76%", "top": "32%", "width": "11%", "height": "3.2%"},
            "drawStone": {"actionList": "drawStone", "label": "Stone", "left": "88%", "top": "32%", "width": "11%", "height": "3.2%"},
            "readyAll": {"actionList": "readyAll", "label": "Recover", "left": "76%", "top": "36%", "width": "11%", "height": "3.2%"},
            "shuffleDeck": {"actionList": "shuffleDeck", "label": "Shuffle", "left": "88%", "top": "36%", "width": "11%", "height": "3.2%"},
            "increase_life_100": {"actionList": "increase_life_100", "label": "Life +100", "left": "76%", "top": "40.4%", "width": "11%", "height": "3.2%"},
            "decrease_life_100": {"actionList": "decrease_life_100", "label": "Life -100", "left": "88%", "top": "40.4%", "width": "11%", "height": "3.2%"},
            "increase_life_500": {"actionList": "increase_life_500", "label": "Life +500", "left": "76%", "top": "44.8%", "width": "11%", "height": "3.2%"},
            "decrease_life_500": {"actionList": "decrease_life_500", "label": "Life -500", "left": "88%", "top": "44.8%", "width": "11%", "height": "3.2%"},
        },
    }}})
    dump_json(jsons / "groupTypes.json", {"groupTypes": group_types()})
    dump_json(jsons / "playerCountMenu.json", {"playerCountMenu": [{"label": "2", "numPlayers": 2, "layoutId": "default"}]})
    phases = [
        ("draw", "Draw"),
        ("recovery", "Recovery"),
        ("main", "Main"),
        ("end", "End"),
    ]
    dump_json(jsons / "phases.json", {"phases": {
        key: {"label": label, "height": "25%"} for key, label in phases
    }, "phaseOrder": [key for key, _ in phases]})
    dump_json(jsons / "steps.json", {"steps": {
        f"{key}Step": {"phaseId": key, "label": label} for key, label in phases
    }, "stepOrder": [f"{key}Step" for key, _ in phases]})
    dump_json(jsons / "playerProperties.json", {"playerProperties": {
        "life": {"label": "Life", "type": "integer", "default": 4000, "min": 0},
    }})
    dump_json(jsons / "gameProperties.json", {"gameProperties": {}})
    dump_json(jsons / "topBarCounters.json", {"topBarCounters": {
        "shared": [{"label": "Round", "imageUrl": "", "gameProperty": "roundNumber"}],
        "player": [{"label": "Life", "imageUrl": "", "playerProperty": "life"}],
    }})
    dump_json(jsons / "tokens.json", {"tokens": {
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
    dump_json(jsons / "functions.json", {"functions": standard_functions()})
    actions = standard_actions(draw_group="Deck")
    actions["drawStone"] = [[
        "COND",
        ["GROUP_EMPTY", "{{$PLAYER_N}}StoneDeck"],
        ["LOG", "{{$ALIAS_N}} tried to draw from an empty magic stone deck."],
        ["TRUE"],
        [
            ["MOVE_STACKS", "{{$PLAYER_N}}StoneDeck", "{{$PLAYER_N}}Stones", 1, "bottom"],
            ["LOG", "{{$ALIAS_N}} drew a magic stone."],
        ],
    ]]
    actions["shuffleStone"] = [
        ["SHUFFLE_GROUP", "{{$PLAYER_N}}StoneDeck"],
        ["LOG", "{{$ALIAS_N}} shuffled their magic stone deck."],
    ]
    actions["flipCoin"] = [
        ["VAR", "$FLIP", ["RANDOM_INT", 1, 2]],
        ["COND", ["EQUAL", "$FLIP", 1], ["LOG", "{{$ALIAS_N}} flipped heads."], ["TRUE"], ["LOG", "{{$ALIAS_N}} flipped tails."]],
    ]
    for amount in (1, 100, 500):
        actions[f"increase_life_{amount}"] = [
            ["INCREASE_VAL", "/playerData/$PLAYER_N/life", amount],
            ["LOG", f"{{{{$ALIAS_N}}}} gained {amount} life."],
        ]
        actions[f"decrease_life_{amount}"] = [
            ["DECREASE_VAL", "/playerData/$PLAYER_N/life", amount],
            ["LOG", f"{{{{$ALIAS_N}}}} lost {amount} life."],
        ]
    dump_json(jsons / "actionLists.json", {"actionLists": actions})
    dump_json(jsons / "hotkeys.json", {"hotkeys": {
        "game": [
            {"key": "D", "actionList": "drawDeck", "label": "Draw"},
            {"key": "T", "actionList": "drawStone", "label": "Draw magic stone"},
            {"key": "S", "actionList": "shuffleDeck", "label": "Shuffle deck"},
            {"key": "R", "actionList": "readyAll", "label": "Recover all"},
            {"key": "L", "actionList": "increase_life_100", "label": "Life +100"},
            {"key": "C", "actionList": "flipCoin", "label": "Flip coin"},
        ],
        "card": [
            {"key": "K", "actionList": "readyCard", "label": "Recover"},
            {"key": "E", "actionList": "spendCard", "label": "Rest"},
            {"key": "I", "actionList": "invertCard", "label": "Rotate 180"},
            {"key": "F", "actionList": ["FLIP", "$ACTIVE_CARD_ID"], "label": "Flip / Judgment"},
            {"key": "X", "actionList": ["DISCARD", "$ACTIVE_CARD_ID"], "label": "Graveyard"},
            {"key": "A", "actionList": ["DETACH", "$ACTIVE_CARD_ID"], "label": "Detach"},
            {"key": "H", "actionList": ["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"], "label": "Shuffle into deck"},
        ],
        "token": [
            {"key": "1", "tokenType": "green", "label": "Green +1"},
            {"key": "2", "tokenType": "red", "label": "Red +1"},
        ],
    }})
    dump_json(jsons / "pluginMenu.json", {"pluginMenu": {"options": [
        {"label": "Draw", "actionList": "drawDeck"},
        {"label": "Draw magic stone", "actionList": "drawStone"},
        {"label": "Shuffle deck", "actionList": "shuffleDeck"},
        {"label": "Shuffle stone deck", "actionList": "shuffleStone"},
        {"label": "Recover all", "actionList": "readyAll"},
        {"label": "Life +100", "actionList": "increase_life_100"},
        {"label": "Life -100", "actionList": "decrease_life_100"},
        {"label": "Life +500", "actionList": "increase_life_500"},
        {"label": "Life -500", "actionList": "decrease_life_500"},
        {"label": "Flip coin", "actionList": "flipCoin"},
    ]}})
    moves = [
        "playerNDeck",
        "playerNStoneDeck",
        "playerNHand",
        "playerNRuler",
        "playerNStones",
        "playerNPlay",
        "playerNStandby",
        "playerNGraveyard",
        "playerNRemoved",
        "playerN+1Play",
        "sharedSetAside",
    ]
    dump_json(jsons / "cardMenu.json", {"cardMenu": {"moveToGroupIds": moves, "options": [
        {"label": "Recover", "actionList": "readyCard"},
        {"label": "Rest", "actionList": "spendCard"},
        {"label": "Rotate 180", "actionList": "invertCard"},
        {"label": "Flip / Judgment", "actionList": "flipCard"},
        {"label": "Graveyard", "actionList": "discardCard"},
        {"label": "Detach", "actionList": "detachCard"},
        {"label": "Shuffle into deck", "actionList": "shuffleIntoDeck"},
    ]}})
    dump_json(jsons / "groupMenu.json", {"groupMenu": {"moveToGroupIds": moves, "options": []}})
    dump_json(jsons / "browse.json", {"browse": {
        "filterPropertySideA": "type",
        "filterValuesSideA": types,
        "textPropertiesSideA": ["name", "packName", "text", "colour"],
    }})
    deck_columns = [
        ("name", "Name"),
        ("type", "Type"),
        ("colour", "Colour"),
        ("cost", "Cost"),
        ("atk", "ATK"),
        ("defense", "DEF"),
        ("packName", "Set"),
    ]
    spawn = ["playerNDeck", "playerNStoneDeck", "playerNRuler"]
    dump_json(jsons / "deckbuilder.json", {"deckbuilder": {
        "addButtons": [1, 2, 3, 4],
        "columns": [{"propName": name, "label": label} for name, label in deck_columns],
        "spawnGroups": [{"loadGroupId": gid, "label": gid.replace("playerN", "My ")} for gid in spawn],
    }})
    dump_json(jsons / "spawnExistingCardModal.json", {"spawnExistingCardModal": {
        "columnProperties": [name for name, _ in deck_columns],
        "loadGroupIds": [gid.replace("playerN", "player1") for gid in spawn] + ["player1Hand", "player2Hand", "player1Play"],
    }})
    dump_json(jsons / "faceProperties.json", {"faceProperties": {
        "cluster": {"label": "Cluster", "type": "string", "default": ""},
        "colour": {"label": "Colour", "type": "string", "default": ""},
        "race": {"label": "Race", "type": "string", "default": ""},
        "cost": {"label": "Cost", "type": "string", "default": ""},
        "atk": {"label": "ATK", "type": "string", "default": ""},
        "defense": {"label": "DEF", "type": "string", "default": ""},
        "rarity": {"label": "Rarity", "type": "string", "default": ""},
        "artist": {"label": "Artist", "type": "string", "default": ""},
        "divinity": {"label": "Divinity", "type": "string", "default": ""},
        "willpower": {"label": "Will", "type": "string", "default": ""},
        "flavour": {"label": "Flavour", "type": "string", "default": ""},
        "text": {"label": "Text", "type": "string", "default": ""},
        "packName": {"label": "Set", "type": "string", "default": ""},
        "set": {"label": "Set Code", "type": "string", "default": ""},
        "loadGroupId": {"label": "Load Group", "type": "string", "default": ""},
    }})
    dump_json(jsons / "cardProperties.json", {"cardProperties": {}})
    dump_json(jsons / "defaultActions.json", {"defaultActions": []})
    dump_json(jsons / "automation.json", {"automation": {
        "postNewGameActionList": [[
            "LOG",
            "Force of Will table created. Load a starter from Menu → Load, or build a deck. No rules are enforced.",
        ]],
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


def remap_missing() -> int:
    tsv = OUT / "tsvs" / "cards.tsv"
    header = tsv.read_text(encoding="utf-8").splitlines()[0].split("\t")
    lines = tsv.read_text(encoding="utf-8").splitlines()
    url_i = header.index("imageUrl")
    changed = 0
    rows = ["\t".join(header)]
    for line in lines[1:]:
        if not line.strip():
            continue
        cols = line.split("\t")
        while len(cols) < len(header):
            cols.append("")
        url = cols[url_i].strip()
        if url.startswith(("http://", "https://")):
            cols[url_i] = PLACEHOLDER_REL
            changed += 1
        rows.append("\t".join(cols[: len(header)]))
    tsv.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"Remapped {changed} leftover remote imageUrl(s) to the placeholder.")
    return 0


def write_decks_only() -> int:
    cards = load_cards_from_tsv()
    decks, menu, errors = convert_decks(cards)
    dump_json(OUT / "jsons" / "preBuiltDecks.json", decks)
    dump_json(OUT / "jsons" / "deckMenu.json", menu)
    source = OUT / "SOURCE.txt"
    extra = [
        "",
        f"Starters refreshed {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from the Force of Will TCG Fandom wiki.",
        f"Prebuilts: {len(decks['preBuiltDecks'])} nested by cluster in deckMenu.json.",
    ]
    if errors:
        extra.append(f"Deck notes: {len(errors)}")
        extra.extend(f"  {line}" for line in errors)
    if source.exists():
        text = source.read_text(encoding="utf-8").rstrip() + "\n"
        text = re.sub(r"\nStarters refreshed .*", "", text, flags=re.S)
        source.write_text(text.rstrip() + "\n" + "\n".join(extra) + "\n", encoding="utf-8")
    print(f"Force of Will starters: {len(decks['preBuiltDecks'])} decks in {len(menu['deckMenu']['subMenus'])} clusters.")
    for line in errors:
        print(f"  {line}")
    return 0


def main() -> int:
    if "--remap-missing" in sys.argv:
        return remap_missing()
    if "--decks-only" in sys.argv:
        return write_decks_only()

    catalog_path = SOURCE / "cards.json"
    art_path = SOURCE / "cards_fow.json"
    if not catalog_path.exists() or not art_path.exists():
        print(f"Missing source tables in {SOURCE}", file=sys.stderr)
        return 1

    catalog = flatten_catalog(json.loads(catalog_path.read_text(encoding="utf-8")))
    fow = json.loads(art_path.read_text(encoding="utf-8"))
    missing_text = fetch(ARENA_MISSING).decode("utf-8", errors="replace")
    missing = {line.strip() for line in missing_text.splitlines() if line.strip()}
    cards, stats = build_cards(catalog, fow, missing)
    decks, menu, deck_errors = convert_decks(cards)

    write_tsv(cards, COLUMNS, OUT / "tsvs" / "cards.tsv")
    backs = write_plugin_art()
    write_plugin_jsons(cards, decks, menu, backs)

    (OUT / "SOURCE.txt").write_text(
        "\n".join([
            f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from FoWind / official Force of Will tables.",
            f"Text: {catalog_path}",
            f"Art index: {art_path}",
            "Faces: https://fowsim.s3.amazonaws.com/media/cards/{id}.jpg (FoWind) and TCG Arena token images.",
            "Card back / placeholder: FoWind S3 static pack art.",
            "Lobby logo: official fowtcg.com. Banner: TCG Arena FoW menu art. Playmat: Masterpiece 03.",
            "Starters: Force of Will TCG Fandom wiki card lists, nested by cluster.",
            "",
            "Tabletop plugin only — no rules engine.",
            f"Catalog cards: {stats['catalog']}  TSV rows: {stats['rows']}  Unique cards: {stats['unique']}",
            f"Ruler/J-ruler pairs: {stats['paired']}  Tokens: {stats['tokens']}  Known-missing placeholder: {stats['placeholder']}",
            f"Prebuilts: {len(decks['preBuiltDecks'])}",
            *([f"Deck warnings: {len(deck_errors)}"] + deck_errors if deck_errors else []),
        ]) + "\n",
        encoding="utf-8",
    )
    print(
        f"Force of Will: {stats['unique']} cards, {stats['rows']} TSV rows, "
        f"{stats['paired']} dual-face, {stats['tokens']} tokens, "
        f"{len(decks['preBuiltDecks'])} starters, {stats['placeholder']} placeholder faces."
    )
    for err in deck_errors:
        print(f"  deck: {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
