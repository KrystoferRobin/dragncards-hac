"""Parse LoN client storage + official .eqd lists. RoF2 layout preferred."""

from __future__ import annotations

import html
import re
import zlib
from collections import Counter
from pathlib import Path

TYPE_REF = {
    "b\x1c__": "Avatar",
    "c\x1c__": "Item",
    "d\x1c__": "Ability",
    "e\x1c__": "Quest",
    "f\x1c__": "Unit",
    "g\x1c__": "Tactic",
}
STAT_PREFIX = {
    "k": "attack",
    "l": "defense",
    "m": "health",
    "q": "damage",
    "r": "damage",
    "s": "level",
    "n": "cost",
    "o": "itemAttack",
    "p": "itemDefense",
}
SET_NAMES = {
    1: "Oathbound",
    2: "Forsworn",
    3: "Inquisitor",
    4: "Oathbreaker",
    5: "Ethernauts",
    6: "Against the Void",
    7: "Storm Break",
    8: "Travelers",
    9: "Vengeful Gods",
    10: "Doom of the Ancient Ones",
    11: "Dragonbrood",
    12: "Legacies",
    13: "Priestess of the Anarchs",
    14: "Fall of the Estarim",
    15: "Debt of the Ratonga",
}
ARCHETYPE_FROM_PRODUCT = {2: "Fighter", 3: "Mage", 4: "Priest", 5: "Scout"}
SKIP_NAME = re.compile(
    r"(Booster Pack|Starter Deck|Tournament Deck|Starter Pack|Gift Box|"
    r"Event Pass|Loot Card|^Painting:|Ornamentation|Deed of Ownership|"
    r"Legendary Starter|Cloudskipper Deck|Jarsath Destroyer|Reward Pack|"
    r"Tournament Pack|Choose a Pack|The Bat Pack|Scenario Pack|Celebration Pack|"
    r"Potion Pack|Potion Package|Launch Pack|Raid Pack|Living Legacy)",
    re.I,
)
TEMPLATE_NAMES = {"Avatar", "Item", "Ability", "Quest", "Unit", "Tactic", "Player", "World", "Object"}
ART_LO, ART_HI = 100004000, 100026000


def resolve_paths(root: Path) -> dict[str, Path]:
    rof2 = root / "LegendsOfNorrath-RoF2"
    if (rof2 / "data/archetypes/storage.dat").exists():
        return {
            "storage": rof2 / "data/archetypes/storage.dat",
            "cards_rcc": rof2 / "cards.rcc",
            "resources_rcc": rof2 / "resources.rcc",
            "decks": rof2 / "data/decks",
            "locale_dat": rof2 / "locale/en_us_data.dat",
            "locale_dir": rof2 / "locale/en_us_data.dir",
            "label": "RoF2 install",
        }
    return {
        "storage": root / "storage.dat",
        "cards_rcc": root / "cards.rcc",
        "resources_rcc": root / "resources.rcc",
        "decks": root,
        "locale_dat": root / "en_us_data.dat",
        "locale_dir": root / "en_us_data.dir",
        "label": "flat LoN dump",
    }


def inflate_storage(path: Path) -> list[bytes]:
    data = path.read_bytes()
    outs: list[bytes] = []
    pos = 6
    fails = 0
    while pos < len(data) - 2:
        if data[pos : pos + 2] != b"\x78\x9c":
            nxt = data.find(b"\x78\x9c", pos)
            if nxt < 0:
                break
            pos = nxt
        dobj = zlib.decompressobj()
        try:
            out = dobj.decompress(data[pos:])
            used = len(data[pos:]) - len(dobj.unused_data)
            if not out or used <= 0:
                pos += 2
                fails += 1
                if fails > 20:
                    break
                continue
            outs.append(out)
            pos += used
            fails = 0
        except Exception:
            pos += 2
            fails += 1
            if fails > 20:
                break
    return outs


def clean_text(value: str) -> str:
    text = html.unescape(value or "")
    text = text.replace("\r", "\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<img[^>]*>", " >> ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("[*title*]", "this card")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def good_name(value: str) -> bool:
    name = (value or "").strip()
    if len(name) < 3 or len(name) > 70:
        return False
    if any(ch in name for ch in "_`"):
        return False
    if name in TEMPLATE_NAMES or SKIP_NAME.search(name):
        return False
    if re.match(r"(?i)(prototype|level \d+ \w+ quest)\b", name):
        return False
    if re.fullmatch(r"..__", name):
        return False
    return bool(re.search(r"[A-Za-z]{3,}", name))


def record_strings(raw: bytes) -> list[str]:
    return [chunk.decode("latin1") for chunk in re.findall(rb"[\x20-\x7e]{3,200}", raw)]


def record_art_ids(raw: bytes) -> list[str]:
    found = [m.decode() for m in re.findall(rb"1000\d{5,7}", raw)]
    for index in range(0, max(0, len(raw) - 3)):
        value = int.from_bytes(raw[index : index + 4], "little")
        if ART_LO <= value <= ART_HI:
            found.append(str(value))
    return list(dict.fromkeys(found))


TYPE_TEMPLATES = {f"{letter}\x1c__" for letter in "bcdefg"}


def looks_like_obj_id(value: str) -> bool:
    return len(value) == 4 and value.endswith("_")


def record_own_id(raw: bytes) -> str:
    if len(raw) < 12:
        return ""
    return raw[8:12].decode("latin1")


def record_obj_ids(raw: bytes) -> list[str]:
    found: list[str] = []
    own = record_own_id(raw)
    if own and own not in TYPE_TEMPLATES:
        found.append(own)
    for match in re.findall(rb"..\x5f\x5f", raw):
        token = match.decode("latin1")
        if token not in TYPE_TEMPLATES and token not in found:
            found.append(token)
    return found


def record_type(raw: bytes) -> str:
    for ref, name in TYPE_REF.items():
        if ref.encode("latin1") in raw:
            return name
    return "Card"


def record_stats(raw: bytes) -> dict[str, str]:
    stats: dict[str, str] = {}
    for prefix, key in STAT_PREFIX.items():
        match = re.search(re.escape(prefix.encode()) + rb"\*([\x60-\x7a])", raw)
        if match and key not in stats:
            stats[key] = str(ord(match.group(1)) - ord("`"))
    return stats


def record_frame(raw: bytes) -> str:
    match = re.search(rb"playmat[\w./\-]+", raw)
    return match.group().decode() if match else ""


def record_set_key(raw: bytes) -> str:
    match = re.search(rb"set(\d{2})_\w+", raw)
    return match.group().decode() if match else ""


def pick_text(strings: list[str]) -> str:
    for item in strings:
        low = item.lower()
        if any(
            token in low
            for token in (
                "[main]",
                "[att]",
                "[def]",
                "exert this",
                "whenever ",
                "when you play this",
                "play this tactic",
                "this avatar",
                "this unit",
                "this item",
                "this ability",
                "this quest",
            )
        ):
            return clean_text(item)
    return ""


def pick_flavor(strings: list[str], name: str, subtitle: str, text: str) -> str:
    skip = {name, subtitle, text}
    for item in strings:
        cleaned = clean_text(item)
        if cleaned in skip or not cleaned:
            continue
        if cleaned.startswith("[") or ">>" in cleaned or cleaned.startswith("playmat"):
            continue
        if re.fullmatch(r"1000\d+", cleaned) or re.fullmatch(r"set\d+_.*", cleaned):
            continue
        if 20 <= len(cleaned) <= 280 and (cleaned[0] in "'\"" or cleaned.endswith(".")):
            return cleaned
    return ""


def parse_cards(records: list[bytes]) -> list[dict[str, str]]:
    merged: dict[tuple[str, str, str], dict[str, str]] = {}
    for raw in records:
        strings = record_strings(raw)
        if not strings:
            continue
        own = record_own_id(raw)
        name = strings[0].strip()
        if name == own or looks_like_obj_id(name):
            name = next((item.strip() for item in strings[1:] if good_name(item.strip())), "")
        if not good_name(name):
            continue
        if any("Loot Card" in item for item in strings[:8]):
            continue
        typ = record_type(raw)
        subtitle = ""
        for item in strings[1:]:
            cand = item.strip()
            if cand == name or looks_like_obj_id(cand):
                continue
            if any(ch in cand for ch in "*@`") or cand.startswith("playmat") or cand.startswith("set"):
                continue
            if cand.startswith("[") or ">>" in cand or re.fullmatch(r"1000\d+", cand):
                continue
            if re.match(r"(?i)(whenever |when you |exert this |play this |at the start)", cand):
                continue
            if " " not in cand and not cand.endswith("."):
                continue
            if re.fullmatch(r"[A-Za-z]{1,4}\.", cand):
                continue
            if good_name(cand):
                subtitle = cand
                break
        text = pick_text(strings)
        art = record_art_ids(raw)
        objs = record_obj_ids(raw)
        stats = record_stats(raw)
        flavor = pick_flavor(strings, name, subtitle, text)
        frame = record_frame(raw)
        set_key = record_set_key(raw)
        archetype = ""
        if "fighter" in frame:
            archetype = "Fighter"
        elif "mage" in frame:
            archetype = "Mage"
        elif "priest" in frame:
            archetype = "Priest"
        elif "rogue" in frame:
            archetype = "Scout"
        key = (name.casefold(), typ, subtitle.casefold())
        row = merged.get(key)
        if row is None:
            merged[key] = {
                "name": name,
                "subtitle": subtitle,
                "type": typ,
                "text": text,
                "flavour": flavor,
                "artIds": art,
                "artId": art[0] if art else "",
                "objIds": objs,
                "objId": objs[0] if objs else "",
                "ownId": own,
                "frame": frame,
                "setKey": set_key,
                "archetype": archetype,
                "faction": "",
                "setNumber": "",
                "packName": "",
                **stats,
            }
            continue
        if typ != "Card" and row["type"] == "Card":
            row["type"] = typ
        if text and len(text) > len(row["text"]):
            row["text"] = text
        if subtitle and not row["subtitle"]:
            row["subtitle"] = subtitle
        if flavor and not row["flavour"]:
            row["flavour"] = flavor
        if frame and not row["frame"]:
            row["frame"] = frame
        if set_key and not row["setKey"]:
            row["setKey"] = set_key
        if archetype and not row["archetype"]:
            row["archetype"] = archetype
        for art_id in art:
            if art_id not in row["artIds"]:
                row["artIds"].append(art_id)
        if not row["artId"] and row["artIds"]:
            row["artId"] = row["artIds"][0]
        if own and own not in row["objIds"] and own not in TYPE_TEMPLATES:
            row["objIds"].insert(0, own)
            row["ownId"] = row.get("ownId") or own
        for obj in objs:
            if obj not in row["objIds"]:
                row["objIds"].append(obj)
        for key_name, value in stats.items():
            row.setdefault(key_name, value)
    return sorted(merged.values(), key=lambda item: (item["type"], item["name"].lower(), item["subtitle"].lower()))


def set_from_product_id(product_id: int) -> int:
    return product_id // 1_000_000


def _eqd_id_tokens(blob: bytes) -> list[str]:
    tokens: list[str] = []
    for match in re.finditer(rb"(.{3}_)\x00", blob):
        token = match.group(1).decode("latin1")
        if token not in TYPE_TEMPLATES:
            tokens.append(token)
        rest = blob[match.end() :]
        if rest.startswith(b"E\x19") or rest.startswith(b"B\x17"):
            break
    return tokens


def parse_eqd_tokens(path: Path) -> tuple[Counter[str], str, list[str]]:
    raw = path.read_bytes()
    marker = raw.find(b'"\x03')
    if marker < 0:
        marker = raw.find(b"'\x03")
    body = raw[marker + 2 :] if marker >= 0 else raw
    sep = body.find(b"\x00\x00\x00\x01")
    if sep >= 0 and sep > len(body) - 8:
        sep = -1
    deck_blob = body[:sep] if sep >= 0 else body
    tail_blob = body[sep + 4 :] if sep >= 0 else b""
    deck_tokens = _eqd_id_tokens(deck_blob)
    tail = _eqd_id_tokens(tail_blob)
    if (sep < 0 or not tail) and len(deck_tokens) >= 54:
        tail = tail or deck_tokens[-5:]
        deck_tokens = deck_tokens[:-5]
    elif (sep < 0 or not tail) and len(deck_tokens) > 50:
        extra = len(deck_tokens) - 50
        tail = tail or deck_tokens[-extra:]
        deck_tokens = deck_tokens[:-extra]
    if not tail:
        embedded = body.find(b"E\x19\x11")
        if embedded >= 0 and embedded + 12 <= len(body):
            own = body[embedded + 8 : embedded + 12].decode("latin1")
            if own not in TYPE_TEMPLATES:
                tail = [own]
    avatar = tail[0] if tail else ""
    quests = tail[1:5]
    return Counter(deck_tokens), avatar, quests


def product_id_from_eqd(path: Path) -> int | None:
    match = re.fullmatch(r"(\d+)\.eqd", path.name)
    return int(match.group(1)) if match else None


def apply_sets_from_decks(cards: list[dict[str, str]], decks_dir: Path) -> None:
    by_obj: dict[str, list[dict[str, str]]] = {}
    for card in cards:
        for obj in card.get("objIds") or []:
            by_obj.setdefault(obj, []).append(card)
    for path in sorted(decks_dir.glob("*.eqd")):
        pid = product_id_from_eqd(path)
        if pid is None:
            if path.stem.endswith("Starter") and path.stem[0].isalpha():
                pid = 1_900_000 + {"Fighter": 2, "Mage": 3, "Priest": 4, "Scout": 5}.get(path.stem.replace("Starter", ""), 2)
            else:
                continue
        set_no = set_from_product_id(pid)
        set_name = SET_NAMES.get(set_no, f"Set {set_no}")
        arch = ARCHETYPE_FROM_PRODUCT.get(pid % 10, "")
        deck, avatar, quests = parse_eqd_tokens(path)
        for obj_id in list(deck) + [avatar, *quests]:
            for card in by_obj.get(obj_id, []):
                if not card["setNumber"] or int(card["setNumber"] or 99) > set_no:
                    card["setNumber"] = str(set_no)
                    card["packName"] = set_name
                if arch and not card["archetype"]:
                    card["archetype"] = arch
    for card in cards:
        if card["setKey"] and not card["setNumber"]:
            match = re.match(r"set(\d+)_", card["setKey"])
            if match:
                set_no = int(match.group(1))
                card["setNumber"] = str(set_no)
                card["packName"] = SET_NAMES.get(set_no, f"Set {set_no}")
        if not card["packName"]:
            card["packName"] = "Norrath"
            card["setNumber"] = card["setNumber"] or "0"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "card"


def assign_ids(cards: list[dict[str, str]]) -> None:
    used: dict[str, int] = {}
    for card in cards:
        base = slug(card["name"])
        if card["subtitle"]:
            base = f"{base}-{slug(card['subtitle'])}"
        ident = f"lon-{base}"
        used[ident] = used.get(ident, 0) + 1
        if used[ident] > 1:
            ident = f"{ident}-{used[ident]}"
        card["databaseId"] = ident
