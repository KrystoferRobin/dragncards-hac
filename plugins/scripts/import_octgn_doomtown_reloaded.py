#!/usr/bin/env python3
"""Build Doomtown Reloaded from the OCTGN definition + dtdb.co card images.

Downloads once via collect_hosted_images (no hotlinking):

  python3 plugins/scripts/import_octgn_doomtown_reloaded.py
  python3 plugins/scripts/collect_hosted_images.py doomtown-reloaded
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lackey_tabletop import write_tsv  # noqa: E402
from import_octgn_batch import (  # noqa: E402
    convert_decks,
    pile,
    tsv_columns,
    write_plugin_art,
    write_plugin_jsons,
)

OCTGN = ROOT / "octgn" / "doomtown-reloaded-NO-IMAGES"
DTDB_CARDS = "https://dtdb.co/api/cards"
DTDB_HOST = "https://dtdb.co"
USER_AGENT = "Toybox/1.0 (private tabletop image collect)"

GAME = {
    "id": "doomtown-reloaded",
    "octgn": "doomtown-reloaded-NO-IMAGES",
    "plugin_name": "Doomtown Reloaded",
    "author": "OCTGN / Db0, trimm · images from dtdb.co",
    "url": "https://dtdb.co",
    "folder": "doomtown-reloaded",
    "pascal": "DoomtownReloaded",
    "draw_group": "Deck",
    "type_keys": ("Type",),
    "extras": [
        ("rank", "Rank"),
        ("suit", "Suit"),
        ("cost", "Cost"),
        ("upkeep", "Upkeep"),
        ("production", "Production"),
        ("bullets", "Bullets"),
        ("drawType", "Draw Type"),
        ("influence", "Influence"),
        ("control", "Control"),
        ("outfit", "Outfit"),
        ("keywords", "Keywords"),
        ("text", "Text"),
        ("dtdbCode", "Code"),
    ],
    "load_group": lambda card: (
        "playerNOutfit" if card.get("type") == "Outfit"
        else "playerNStarting" if card.get("type") == "Legend"
        else "sharedSetAside" if card.get("type") in {"Token", "Joker"}
        else "playerNDeck"
    ),
    "section_groups": {
        "Outfit": "playerNOutfit",
        "Legend": "playerNStarting",
        "Starting Cards": "playerNStarting",
        "Deck": "playerNDeck",
    },
    "piles": [
        pile("Deck", "Deck", "deck"),
        pile("Discard", "Discard", "discard"),
        pile("BootHill", "Boot Hill", "aside"),
        pile("Hand", "Play Hand", "hand"),
        pile("DrawHand", "Draw Hand", "hand"),
        pile("Outfit", "Outfit", "inPlay", inPlay=True),
        pile("Starting", "Starting / Legend", "inPlay", inPlay=True),
        pile("Play", "Town", "inPlay", inPlay=True),
    ],
    "player_props": {
        "ghostRock": {"label": "Ghost Rock", "type": "integer", "default": 0, "min": 0},
        "influence": {"label": "Influence", "type": "integer", "default": 0, "min": 0},
        "control": {"label": "Control", "type": "integer", "default": 0, "min": 0},
    },
    "game_props": {},
    "phases": [
        ("lowball", "Lowball"),
        ("upkeep", "Upkeep"),
        ("highNoon", "High Noon"),
        ("sundown", "Sundown"),
        ("nightfall", "Nightfall"),
    ],
    "announcements": [
        "Tabletop plugin from OCTGN Doomtown Reloaded. Faces collected once from dtdb.co onto Toybox — the site is not hotlinked.",
        "D = draw to Play Hand. P = pull to Draw Hand. Outfits and Legends load to their rows. No rules engine.",
    ],
    "card_back": "Card/back.jpg",
    "regions": [
        ("playerN+1Hand", "fan", "0%", "0%", "58%", "9%"),
        ("playerN+1Outfit", "row", "58%", "0%", "17%", "12%"),
        ("playerN+1Play", "free", "0%", "12%", "75%", "20%"),
        ("playerNPlay", "free", "0%", "36%", "58%", "20%"),
        ("playerNOutfit", "row", "58%", "36%", "17%", "14%"),
        ("playerNDrawHand", "row", "0%", "66%", "36%", "10%"),
        ("playerNStarting", "row", "36%", "66%", "22%", "10%"),
        ("playerNHand", "fan", "0%", "82%", "58%", "17%"),
        ("playerN+1Deck", "pile", "76%", "10%", "11%", "14%"),
        ("playerN+1Discard", "pile", "88%", "10%", "11%", "14%"),
        ("playerN+1BootHill", "pile", "76%", "25%", "11%", "12%"),
        ("sharedSetAside", "pile", "88%", "25%", "11%", "12%"),
        ("playerNDeck", "pile", "76%", "58%", "11%", "16%"),
        ("playerNDiscard", "pile", "88%", "58%", "11%", "16%"),
        ("playerNBootHill", "pile", "88%", "42%", "11%", "12%"),
    ],
    "spawn_groups": ["playerNDeck", "playerNOutfit", "playerNStarting", "playerNDrawHand"],
    "deck_columns": [("name", "Name"), ("type", "Type"), ("outfit", "Outfit"), ("cost", "Cost"), ("packName", "Set")],
    "extra_actions": {
        "pullDrawHand": [[
            "COND",
            ["GROUP_EMPTY", "{{$PLAYER_N}}Deck"],
            ["LOG", "{{$ALIAS_N}} tried to pull from an empty deck."],
            ["TRUE"],
            [
                ["MOVE_STACKS", "{{$PLAYER_N}}Deck", "{{$PLAYER_N}}DrawHand", 1, "bottom"],
                ["LOG", "{{$ALIAS_N}} pulled to their Draw Hand."],
            ],
        ]],
    },
    "extra_hotkeys": [{"key": "P", "actionList": "pullDrawHand", "label": "Pull to Draw Hand"}],
    "extra_menu": [{"label": "Pull to Draw Hand", "actionList": "pullDrawHand"}],
    "extra_buttons": [("pullDrawHand", "Pull", "76%", "50%", "23%", "3.2%")],
}


def norm(value: str) -> str:
    text = html.unescape(value or "").replace("\u2019", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text.casefold())
    text = re.sub(r"\s+exp\s*\d+", "", text)
    return " ".join(text.split())


def prop(card: ET.Element, *names: str) -> str:
    wanted = {name.casefold() for name in names}
    for child in card.findall("property"):
        if (child.attrib.get("name") or "").casefold() in wanted:
            return html.unescape((child.attrib.get("value") or child.text or "").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip())
    return ""


def fetch_dtdb() -> list[dict]:
    request = urllib.request.Request(DTDB_CARDS, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode())
    if not isinstance(payload, list):
        raise SystemExit(f"Unexpected dtdb payload: {type(payload)}")
    return payload


def image_url(card: dict) -> str:
    src = (card.get("imagesrc") or "").strip()
    if not src:
        return ""
    if src.startswith("http"):
        return src
    return DTDB_HOST + src


def load_group(card_type: str) -> str:
    return GAME["load_group"]({"type": card_type})


def match_dtdb(octgn_id: str, name: str, set_name: str, by_id: dict, by_pack_name: dict, by_name: dict) -> dict | None:
    if octgn_id and octgn_id.lower() in by_id:
        return by_id[octgn_id.lower()]
    hits = by_pack_name.get((norm(set_name), norm(name))) or []
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        return hits[0]
    unique = by_name.get(norm(name)) or []
    if len(unique) == 1:
        return unique[0]
    return None


def dtdb_row(dtdb: dict, database_id: str) -> dict[str, str]:
    card_type = (dtdb.get("type") or "Card").strip() or "Card"
    row = {
        "databaseId": database_id,
        "name": html.unescape(dtdb.get("title") or ""),
        "imageUrl": image_url(dtdb),
        "cardBack": "default",
        "type": card_type,
        "packName": dtdb.get("pack") or "Unknown",
        "set": dtdb.get("pack") or "Unknown",
        "rank": "" if dtdb.get("rank") is None else str(dtdb.get("rank")),
        "suit": dtdb.get("suit") or "",
        "cost": "" if dtdb.get("cost") is None else str(dtdb.get("cost")),
        "upkeep": "" if dtdb.get("upkeep") is None else str(dtdb.get("upkeep")),
        "production": "" if dtdb.get("production") is None else str(dtdb.get("production")),
        "bullets": "" if dtdb.get("bullets") is None else str(dtdb.get("bullets")),
        "drawType": dtdb.get("shooter") or "",
        "influence": "" if dtdb.get("influence") is None else str(dtdb.get("influence")),
        "control": "" if dtdb.get("control") is None else str(dtdb.get("control")),
        "outfit": dtdb.get("gang") or "",
        "keywords": dtdb.get("keywords") or "",
        "text": html.unescape((dtdb.get("text") or "").replace("\r", " ").replace("\n", " ")),
        "dtdbCode": dtdb.get("code") or "",
    }
    row["loadGroupId"] = load_group(card_type)
    return row


def load_cards() -> tuple[list[dict[str, str]], list[str], dict[str, int]]:
    dtdb = fetch_dtdb()
    by_id = {card["octgnid"].lower(): card for card in dtdb if card.get("octgnid")}
    by_pack_name: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_name: dict[str, list[dict]] = defaultdict(list)
    for card in dtdb:
        by_pack_name[(norm(card.get("pack") or ""), norm(card.get("title") or ""))].append(card)
        by_name[norm(card.get("title") or "")].append(card)

    cards: list[dict[str, str]] = []
    errors: list[str] = []
    used_codes: set[str] = set()
    seen_ids: set[str] = set()
    stats = {"octgn": 0, "octgn_id": 0, "octgn_name": 0, "dtdb_extra": 0, "skipped": 0}

    for set_path in sorted((OCTGN / "Sets").glob("*/set.xml")):
        root = ET.parse(set_path).getroot()
        set_name = html.unescape(root.attrib.get("name") or set_path.parent.name)
        for card_el in root.findall("cards/card") or root.findall(".//card"):
            card_id = (card_el.attrib.get("id") or "").strip()
            name = html.unescape((card_el.attrib.get("name") or "").strip())
            card_type = prop(card_el, "Type") or "Card"
            if not card_id or not name:
                continue
            if card_type == "Token" or "marker" in set_name.casefold():
                stats["skipped"] += 1
                continue
            hit = match_dtdb(card_id, name, set_name, by_id, by_pack_name, by_name)
            if not hit or not image_url(hit):
                errors.append(f"no dtdb image for {set_name} / {name}")
                continue
            if card_id.lower() in seen_ids:
                continue
            seen_ids.add(card_id.lower())
            row = dtdb_row(hit, card_id)
            row["name"] = name
            row["set"] = set_name
            row["packName"] = set_name
            row["type"] = card_type
            for tsv_name, source_name in GAME["extras"]:
                if tsv_name == "dtdbCode":
                    continue
                value = prop(card_el, source_name)
                if value:
                    row[tsv_name] = value
            row["loadGroupId"] = load_group(card_type)
            cards.append(row)
            stats["octgn"] += 1
            if hit.get("octgnid") and hit["octgnid"].lower() == card_id.lower():
                stats["octgn_id"] += 1
            else:
                stats["octgn_name"] += 1
            if hit.get("code"):
                used_codes.add(hit["code"])

    for hit in dtdb:
        code = hit.get("code") or ""
        if not code or code in used_codes or not image_url(hit):
            continue
        if (hit.get("type") or "").lower() == "token":
            continue
        extra_id = hit.get("octgnid") or f"dtdb-{code}"
        if extra_id.lower() in seen_ids:
            continue
        seen_ids.add(extra_id.lower())
        used_codes.add(code)
        cards.append(dtdb_row(hit, extra_id))
        stats["dtdb_extra"] += 1

    return cards, errors, stats


def main() -> int:
    if not (OCTGN / "definition.xml").exists():
        raise SystemExit(f"Missing OCTGN plugin: {OCTGN}")
    print("Fetching dtdb.co/api/cards …")
    cards, errors, stats = load_cards()
    if not cards:
        print("No cards matched.")
        return 1
    out = ROOT / GAME["id"]
    write_tsv(cards, tsv_columns(GAME, cards), out / "tsvs" / "cards.tsv")
    decks, menu, deck_errors = convert_decks(GAME, cards)
    errors.extend(deck_errors)
    backs = write_plugin_art(GAME)
    write_plugin_jsons(GAME, cards, decks, menu, backs)
    (out / "SOURCE.txt").write_text(
        "\n".join([
            f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from OCTGN Doomtown Reloaded + dtdb.co.",
            f"Source: {OCTGN}",
            "Art: https://dtdb.co/api/cards → /images/cards/en/{code}.jpg (collected onto Toybox, not hotlinked).",
            "Author credit: OCTGN / Db0, trimm. Image host: DoomtownDB (dtdb.co).",
            "",
            "Tabletop plugin only — OCTGN scripts were not ported.",
            f"TSV rows: {len(cards)}  OCTGN matched: {stats['octgn']} (id {stats['octgn_id']}, name {stats['octgn_name']})  extra dtdb printings: {stats['dtdb_extra']}",
            f"Skipped tokens/markers: {stats['skipped']}  missing: {sum(1 for e in errors if 'no dtdb' in e)}",
            f"Prebuilts: {len(decks['preBuiltDecks'])}",
            "",
        ]),
        encoding="utf-8",
    )
    print(f"Wrote {out.name}")
    print(f"  pluginName: {GAME['plugin_name']}")
    print(f"  tsv rows: {len(cards)}")
    print(f"  OCTGN matched: {stats['octgn']} (id {stats['octgn_id']}, name {stats['octgn_name']})")
    print(f"  extra dtdb printings: {stats['dtdb_extra']}")
    print(f"  prebuilt decks: {len(decks['preBuiltDecks'])}")
    print(f"  types: {', '.join(sorted({c['type'] for c in cards}))}")
    if errors:
        print(f"\n{len(errors)} issue(s):")
        for err in errors[:30]:
            print(f"  - {err}")
        if len(errors) > 30:
            print(f"  … {len(errors) - 30} more")
    print("\nNext:\n  python3 plugins/scripts/collect_hosted_images.py doomtown-reloaded")
    return 0 if stats["octgn"] >= 800 else 1


if __name__ == "__main__":
    raise SystemExit(main())
