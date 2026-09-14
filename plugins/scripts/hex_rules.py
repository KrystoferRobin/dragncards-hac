"""Pull HEX keyword glossary + a kitchen-table primer from the client UI XML."""

from __future__ import annotations

import re
from pathlib import Path

from hex_catalog import clean_text

SKIP_KEYS = {
    "ComingSoon",
    "AIMustPlay",
    "MinBothDeckSizes",
    "MinConstructedDeckSize",
    "MinLimitedDeckSize",
    "AllowYardInspire",
    "Juggernaught",
    "SpiritDrain",
    "FirstStrike",
    "SkyGuard",
    "Invincible",
}

DISPLAY = {
    "CantBlock": "Can't Block",
    "EntersPlayExhausted": "Enters Play Exhausted",
    "MustBeBlocked": "Must Be Blocked",
    "CantBeBlocked": "Can't Be Blocked",
    "DeathSentence": "Death Sentence",
    "SporeaticGrowth": "Sporeatic Growth",
    "DamageShield": "Damage Shield",
    "QuickAction": "Quick Action",
}

# Printed aliases → client glossary name.
KEYWORD_ALIASES = (
    ("Spellshield", "Spell Shield"),
    ("Juggernaut", "Crush"),
    ("Juggernaught", "Crush"),
    ("First Strike", "Swiftstrike"),
    ("Sky Guard", "Skyguard"),
)


def _units(xml: str, prefix: str) -> list[tuple[str, str]]:
    pattern = re.compile(
        rf'<trans-unit id="{prefix}([^"]+)"[^>]*>\s*'
        r"<source>.*?</source>\s*"
        r"<target><!\[CDATA\[(.*?)\]\]></target>",
        re.S,
    )
    rows = []
    for key, text in pattern.findall(xml):
        text = re.sub(r"\s+", " ", text).strip()
        if not text or text.startswith(prefix):
            continue
        rows.append((key, text))
    return rows


def load_keywords(ui_xml: Path) -> list[tuple[str, str]]:
    xml = ui_xml.read_text(encoding="utf-8", errors="replace")
    seen: dict[str, str] = {}
    for key, text in _units(xml, "Keyword_"):
        if key in SKIP_KEYS or key.startswith("#"):
            continue
        label = DISPLAY.get(key, re.sub(r"([a-z])([A-Z])", r"\1 \2", key))
        seen[label] = clean_text(text)
    return sorted(seen.items())


def reminder_glossary(keywords: list[tuple[str, str]]) -> dict[str, str]:
    """Name → reminder, including printed aliases, for GiantCard hover."""
    by_name = {name: text for name, text in keywords if text and text.strip() not in {"[null]", "null"}}
    out = dict(by_name)
    for alias, canonical in KEYWORD_ALIASES:
        if alias not in out and canonical in by_name:
            out[alias] = by_name[canonical]
    return out


def primer() -> str:
    return """# HEX: Shards of Fate — kitchen table

Cryptozoic's digital CCG, from the final 1.1.0.086 client. Shortcuts only — nobody is enforcing the chain.

## How a game works

Each player has a **champion** (usually 20 health; some PvE champs differ) and a **60-card deck**. You win by reducing the other champion to 0 health, or when they cannot draw.

**Resources** (shards) are your lands. Play **one resource a turn**. A card's number is how many resources you must exhaust to play it. **Threshold** is extra: you also need that many resources of the named shard color(s) in play (Blood, Ruby, Diamond, Sapphire, Wild). You do not exhaust the colored ones separately — you just have to have them.

**Troops** enter play exhausted unless they have Speed. They attack the opposing champion; the defender may block with troops. Combat damage to a troop equal to its DEF kills it. Overflow does not hit the champion unless the attacker has Crush.

**Basic Actions** can only be played on your turn, as a main-phase play. **Quick Actions** can be played whenever you have priority (your turn or in response). **Constants** and **Artifacts** stay in play. **Equipment** (often Artifact / Troop Artifact) can sit on a troop in the real game; here, stack it on the troop or leave it in Support.

Zones on this table: Champion, Resources, Troops, Support (constants / artifacts), Deck, Hand, Crypt (discard), Void (removed from game). Tunneling cards can sit in Void or Set Aside until they "surface."

## Turn outline

1. **Ready** — ready your exhausted cards. Diligence happens here.
2. **Resource** — play one resource from hand.
3. **Draw** — draw a card.
4. **Main** — play cards, use powers, attack.
5. **End** — cleanup. "At the start of your turn" effects wait until next Ready.

Hotkeys: **D** draw, **R** ready all, **S** shuffle, **E** exhaust, **U** ready, **X** crypt, **V** void.

## Keywords

The client shipped these as the in-game glossary. Aliases (Juggernaut = Crush, First Strike = Swiftstrike, Sky Guard = Skyguard) are folded into the main name.
"""


def write_rules_md(path: Path, keywords: list[tuple[str, str]]) -> None:
    lines = [primer(), ""]
    for name, text in keywords:
        lines.append(f"**{name}.** {text}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def rules_cards(keywords: list[tuple[str, str]]) -> list[dict[str, str]]:
    chunks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    size = 0
    for name, text in keywords:
        entry = f"{name}: {text}"
        if size + len(entry) > 520 and current:
            chunks.append(current)
            current = []
            size = 0
        current.append((name, text))
        size += len(entry)
    if current:
        chunks.append(current)
    cards = [
        {
            "guid": "hex-rules-how-to",
            "name": "How to Play HEX",
            "subtitle": "Kitchen table",
            "type": "Rules",
            "packName": "Rules",
            "faction": "",
            "rarity": "",
            "cost": "",
            "threshold": "",
            "attack": "",
            "defense": "",
            "health": "",
            "text": (
                "60-card deck + a champion (usually 20 HP). Play one resource a turn. "
                "Cost = resources you exhaust. Threshold = shard colors you must have in play. "
                "Troops attack the champion; blockers step in front. Crush leftover hits the champ. "
                "Basic Actions on your turn; Quick Actions anytime. Crypt = discard, Void = gone. "
                "D draw · R ready all · E exhaust · X crypt · V void."
            ),
            "flavour": "From the 1.1.0.086 client glossary and turn structure — not a living rules engine.",
            "artist": "",
            "artPath": "",
            "artId": "",
            "cardNumber": "",
            "unique": "1",
            "pve": "0",
        }
    ]
    for index, chunk in enumerate(chunks, start=1):
        body = "\n".join(f"{name}. {text}" for name, text in chunk)
        cards.append(
            {
                "guid": f"hex-rules-kw-{index}",
                "name": f"Keywords {index}",
                "subtitle": "Glossary",
                "type": "Rules",
                "packName": "Rules",
                "faction": "",
                "rarity": "",
                "cost": "",
                "threshold": "",
                "attack": "",
                "defense": "",
                "health": "",
                "text": body,
                "flavour": "",
                "artist": "",
                "artPath": "",
                "artId": "",
                "cardNumber": "",
                "unique": "1",
                "pve": "0",
            }
        )
    return cards
