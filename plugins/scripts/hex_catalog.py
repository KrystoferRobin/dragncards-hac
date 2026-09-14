"""Parse HEX: Shards of Fate gamedata + locale into card rows."""

from __future__ import annotations

import gzip
import html
import re
from collections import Counter
from pathlib import Path

HEX_ROOTS = (
    Path("/Volumes/Expand/HEX SHARDS OF FATE"),
    Path(__file__).resolve().parents[1] / "HEX",
    Path(__file__).resolve().parents[1] / "HEX SHARDS OF FATE",
)

CONSTRUCTED_ORDER = [
    "Shards of Fate",
    "Shattered Destiny",
    "Armies of Myth",
    "Primal Dawn",
    "Herofall",
    "Scars of War",
    "Frostheart",
    "Dead of Winter",
    "Doombringer",
]

SET_PRETTY = {
    "AI Only Cards": "AI Only",
    "Basic_Shards": "Basic Shards",
    "Campaign Created Champions": "Created Champions",
    "Engineering_Oddities": "Engineering Oddities",
    "PvE01_AZ_1_NPCs": "PvE AZ1 NPCs",
    "AZ1": "PvE AZ1",
    "AZ1 Equipment": "PvE AZ1 Equipment",
    "AZ2 NPCs": "PvE AZ2 NPCs",
    "AZ2": "PvE AZ2",
    "AZ2 Equipment": "PvE AZ2 Equipment",
    "PvE_AZ1_Created_Effects": "PvE AZ1 Effects",
    "PvE_AZ2_Created_Effects": "PvE AZ2 Effects",
    "Set001_alternates": "Shards of Fate (Alt)",
    "Set01_Kickstarter": "Shards of Fate (Kickstarter)",
    "Set01_Kickstarter_alternates": "Shards of Fate (Kickstarter Alt)",
    "Set01_PvE_Arena": "PvE Arena",
    "Set01_PvE_Arena_alternates": "PvE Arena (Alt)",
    "Set01_PvE_Holiday": "Holiday",
    "Set01_PvE_Holiday_alternates": "Holiday (Alt)",
    "Set01_PvE_Talents": "PvE Talents",
    "Set01_PvE_Talents_alternates": "PvE Talents (Alt)",
    "Set02_PvE_Talents": "PvE Talents 2",
    "Set02_PvE_Talents_alternates": "PvE Talents 2 (Alt)",
    "Set02_PvP_alternates": "Shattered Destiny (Alt)",
    "Set03_PvE_Promo": "Armies of Myth (Promo)",
    "Set03_PvE_Promo_alternates": "Armies of Myth (Promo Alt)",
    "Set03_PvP_alternates": "Armies of Myth (Alt)",
    "Set04_PvE_Promo": "Primal Dawn (Promo)",
    "Set04_PvE_Promo_alternates": "Primal Dawn (Promo Alt)",
    "Set04_PvP_alternates": "Primal Dawn (Alt)",
    "Set05_PvE_Promo": "Herofall (Promo)",
    "Set05_PvE_Promo_alternates": "Herofall (Promo Alt)",
    "Set05_PvP_alternates": "Herofall (Alt)",
    "Set06_PvE_Promo": "Scars of War (Promo)",
    "Set06_PvE_Promo_alternates": "Scars of War (Promo Alt)",
    "Set06_PvP_alternates": "Scars of War (Alt)",
    "Set07_PvE_Promo": "Frostheart (Promo)",
    "Set07_PvE_Promo_alternates": "Frostheart (Promo Alt)",
    "Frostheart Core Commons": "Frostheart (Core)",
    "Set07_PvP_Core_Commons_alternates": "Frostheart (Core Alt)",
    "Set07_PvP_alternates": "Frostheart (Alt)",
    "Set08_PvE_Promo": "Dead of Winter (Promo)",
    "Set08_PvE_Promo_alternates": "Dead of Winter (Promo Alt)",
    "Set08_PvP_alternates": "Dead of Winter (Alt)",
    "Set09_PvE_Promo": "Doombringer (Promo)",
    "Set09_PvE_Promo_alternates": "Doombringer (Promo Alt)",
    "DoombringerCoreCommons": "Doombringer (Core)",
    "Set09_PvP_Core_Commons_alternates": "Doombringer (Core Alt)",
    "Set09_PvP_alternates": "Doombringer (Alt)",
}

TYPE_LABEL = {
    "Troop": "Troop",
    "BasicAction": "Basic Action",
    "QuickAction": "Quick Action",
    "Constant": "Constant",
    "Artifact": "Artifact",
    "Troop|Artifact": "Troop Artifact",
    "Choice": "Choice",
    "Troop|Quick": "Troop",
    "Resource": "Resource",
    "Bane": "Bane",
    "Constant|Quick": "Constant",
    "Mod": "Mod",
    "Champion": "Champion",
}

LOAD_GROUP = {
    "Champion": "playerNChampion",
    "Resource": "playerNResources",
    "Troop": "playerNDeck",
    "Troop Artifact": "playerNDeck",
    "Artifact": "playerNDeck",
    "Constant": "playerNDeck",
    "Basic Action": "playerNDeck",
    "Quick Action": "playerNDeck",
    "Choice": "playerNDeck",
    "Bane": "playerNDeck",
    "Mod": "playerNDeck",
    "Rules": "playerNHand",
}

SKIP_DECK = re.compile(
    r"(?i)^(ai[_ ]|tutorial|demo_|z?pve|arena_|roid$)|"
    r"( - ai$)|(^az\d)|(^az )|(crayburn castle)|(^starting_)",
)


def resolve_hex() -> Path:
    for path in HEX_ROOTS:
        if (path / "Data" / "gamedata").exists():
            return path
    raise FileNotFoundError("HEX install not found (looked in /Volumes/Expand/HEX SHARDS OF FATE)")


def section(raw: str, name: str) -> str:
    start = raw.find(f"$$$---$$$\n{name}\n$$--$$\n")
    if start < 0:
        return ""
    start = raw.find("$$--$$\n", start) + len("$$--$$\n")
    end = raw.find("$$$---$$$", start)
    return raw[start:end] if end > 0 else raw[start:]


def split_objects(blob: str, type_name: str) -> list[str]:
    marker = f'"_t":"Reckoning.Game.{type_name}"'
    return blob.split(marker)[1:]


def field_str(blob: str, name: str, default: str = "") -> str:
    match = re.search(rf'"{name}"\s*:\s*"((?:\\.|[^"\\])*)"', blob[:12000])
    if match:
        return match.group(1).replace('\\"', '"').replace("\\n", "\n")
    return default


def field_int(blob: str, name: str, default: str = "") -> str:
    match = re.search(rf'"{name}"\s*:\s*(-?\d+)', blob[:8000])
    return match.group(1) if match else default


def field_guid(blob: str, name: str) -> str:
    match = re.search(rf'"{name}"\s*:\s*\{{\s*"m_Guid"\s*:\s*"([^"]+)"', blob[:4000])
    return match.group(1) if match else ""


def art_id_from_path(path: str) -> str:
    if not path:
        return ""
    stem = Path(path.replace("\\", "/")).stem
    match = re.search(r"(a\d{7})", stem, re.I)
    return match.group(1).lower() if match else stem.lower()


def pretty_set(name: str) -> str:
    return SET_PRETTY.get(name, name or "Unknown")


def clean_text(value: str) -> str:
    text = html.unescape(value or "")
    text = text.replace("\\r", "").replace("\\n", "\n")
    repl = (
        ("[ARROWR]", " → "),
        ("[ACT]", "Exhaust"),
        ("[BASIC]", "Basic"),
        ("[ONE-SHOT]", "One-Shot"),
        ("<p>", "\n"),
        ("</p>", ""),
        ("<b>", ""),
        ("</b>", ""),
        ("[*title*]", "this"),
    )
    for old, new in repl:
        text = text.replace(old, new)
    text = re.sub(r"\[\((\d+)\)\]", r"(\1)", text)
    text = re.sub(r"\[L(\d+)\]", r"[Wild \1]", text)
    text = re.sub(r"\[R(\d+)\]", r"[Ruby \1]", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def parse_threshold(blob: str) -> str:
    block = re.search(r'"m_Threshold"\s*:\s*(\[[\s\S]*?\]|null)', blob[:6000])
    if not block or block.group(1) == "null":
        return ""
    bits = []
    for color, need in re.findall(
        r'"m_ColorFlags"\s*:\s*"([^"]+)"[\s\S]*?"m_ThresholdColorRequirement"\s*:\s*(\d+)',
        block.group(1),
    ):
        bits.append(f"{color} {need}" if need != "1" else color)
    return ", ".join(bits)


def load_gamedata(root: Path) -> str:
    return gzip.decompress((root / "Data" / "gamedata").read_bytes()).decode("utf-8", "replace")


def parse_sets(raw: str) -> dict[str, str]:
    blob = section(raw, "CardSetTemplate")
    sets: dict[str, str] = {}
    for item in split_objects(blob, "CardSetTemplate"):
        guid = field_guid(item, "m_Id") or field_guid(item, "m_SetId")
        name = field_str(item, "m_Name")
        if guid and name:
            sets[guid] = pretty_set(name)
    return sets


def parse_cards(raw: str, sets: dict[str, str]) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    for item in split_objects(section(raw, "CardTemplate"), "CardTemplate"):
        name = field_str(item, "m_Name")
        if not name or name.startswith("#"):
            continue
        raw_type = field_str(item, "m_CardType") or "Card"
        typ = TYPE_LABEL.get(raw_type, raw_type.replace("|", " "))
        set_name = sets.get(field_guid(item, "m_SetId"), "Unknown")
        art_path = field_str(item, "m_CardImagePath")
        cards.append(
            {
                "guid": field_guid(item, "m_Id"),
                "name": name,
                "subtitle": field_str(item, "m_CardSubtype"),
                "type": typ,
                "packName": set_name,
                "faction": field_str(item, "m_Faction").replace("None", ""),
                "rarity": field_str(item, "m_CardRarity"),
                "cost": field_int(item, "m_ResourceCost"),
                "threshold": parse_threshold(item),
                "attack": field_int(item, "m_BaseAttackValue"),
                "defense": field_int(item, "m_BaseDefenseValue"),
                "health": "",
                "text": clean_text(field_str(item, "m_GameText")),
                "flavour": clean_text(field_str(item, "m_FlavorText")),
                "artist": field_str(item, "m_ArtistName"),
                "artPath": art_path,
                "artId": art_id_from_path(art_path),
                "cardNumber": field_int(item, "m_CardNumber"),
                "unique": field_int(item, "m_Unique"),
                "pve": field_int(item, "m_IsPvE"),
            }
        )
    return cards


def parse_champions(raw: str, sets: dict[str, str]) -> list[dict[str, str]]:
    champs: list[dict[str, str]] = []
    for item in split_objects(section(raw, "ChampionTemplate"), "ChampionTemplate"):
        name = field_str(item, "m_Name")
        if not name:
            continue
        selectable = field_int(item, "m_IsPlayerSelectable", "0")
        race = field_str(item, "m_Race").replace("None", "")
        klass = field_str(item, "m_Class").replace("None", "")
        if selectable != "1" and not field_str(item, "m_GameText"):
            continue
        art_path = field_str(item, "m_HudPortrait") or field_str(item, "m_CardImagePath")
        subtitle = " / ".join(bit for bit in (race, klass, field_str(item, "m_SubType")) if bit and bit != name)
        champs.append(
            {
                "guid": field_guid(item, "m_Id"),
                "name": name,
                "subtitle": subtitle,
                "type": "Champion",
                "packName": sets.get(field_guid(item, "m_SetId"), "Champions"),
                "faction": field_str(item, "m_Faction").replace("None", ""),
                "rarity": "Champion",
                "cost": "",
                "threshold": "",
                "attack": "",
                "defense": "",
                "health": field_int(item, "m_StartingHealth"),
                "text": clean_text(field_str(item, "m_GameText")),
                "flavour": "",
                "artist": field_str(item, "m_ArtistName"),
                "artPath": art_path,
                "artId": art_id_from_path(art_path),
                "cardNumber": "",
                "unique": "1",
                "pve": "0" if selectable == "1" else "1",
            }
        )
    return champs


def parse_decks(raw: str) -> list[dict]:
    decks = []
    for item in split_objects(section(raw, "DeckTemplate"), "DeckTemplate"):
        name = field_str(item, "m_DeckName")
        if not name or SKIP_DECK.search(name):
            continue
        champ = field_guid(item, "m_ChampionId") or field_guid(item, "m_Champion")
        stacks = []
        for guid, count in re.findall(
            r'"m_idTemplate"\s*:\s*\{\s*"m_Guid"\s*:\s*"([^"]+)"[\s\S]*?"m_Count"\s*:\s*(\d+)',
            item,
        ):
            stacks.append((guid, int(count)))
        if not stacks:
            continue
        decks.append({"name": name, "champion": champ, "cards": stacks})
    return decks


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "card"


def assign_ids(cards: list[dict[str, str]]) -> None:
    used: dict[str, int] = {}
    for card in cards:
        base = slug(card["name"])
        if card.get("subtitle"):
            base = f"{base}-{slug(card['subtitle'])}"
        ident = f"hex-{base}"
        used[ident] = used.get(ident, 0) + 1
        if used[ident] > 1:
            ident = f"{ident}-{used[ident]}"
        card["databaseId"] = ident
        card["loadGroupId"] = LOAD_GROUP.get(card["type"], "playerNDeck")
        card["set"] = card.get("packName") or ""


def set_sort_key(name: str) -> tuple[int, str]:
    if name in CONSTRUCTED_ORDER:
        return (CONSTRUCTED_ORDER.index(name), name)
    if name.startswith(tuple(CONSTRUCTED_ORDER)):
        return (20, name)
    if name == "Rules":
        return (0, name)
    if name == "Champions" or "Champion" in name:
        return (30, name)
    if name.startswith("PvE") or name.startswith("AZ"):
        return (80, name)
    return (50, name)


def summarize(cards: list[dict[str, str]]) -> str:
    return f"{len(cards)} cards  types={dict(Counter(c['type'] for c in cards))}  sets={len(set(c['packName'] for c in cards))}"
