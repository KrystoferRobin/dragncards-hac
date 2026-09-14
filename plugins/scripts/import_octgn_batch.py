#!/usr/bin/env python3
"""Build DragnCards tabletop plugins from the OCTGN games in plugins/octgn.

  python3 plugins/scripts/import_octgn_batch.py
  python3 plugins/scripts/import_octgn_batch.py doomtown
"""

from __future__ import annotations

import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from image_names import (  # noqa: E402
    TOYBOX_PREFIX,
    card_rel_path,
    ext_from_url,
    lobby_art_rel,
    stamp_lobby_art,
    toybox_url,
)
from lackey_tabletop import (  # noqa: E402
    copy_plugin_art,
    dump_json,
    group_types,
    region,
    sanitize,
    slug,
    standard_actions,
    standard_functions,
    unique_rel,
    write_color_png,
    write_tsv,
)

OCTGN = ROOT / "octgn"
IMAGES = ROOT / "images"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

CORE_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "packName",
    "set",
    "loadGroupId",
]


def pile(suffix: str, label: str, group_type: str, **extra) -> dict:
    return {"suffix": suffix, "label": label, "groupType": group_type, **extra}


def pretty_set(name: str) -> str:
    cleaned = (name or "").replace("_", " ").strip()
    cleaned = cleaned.split(" - ", 1)[-1] if cleaned[:3].isdigit() and " - " in cleaned else cleaned
    return cleaned


def prop(card: ET.Element, *names: str) -> str:
    wanted = {name.casefold() for name in names}
    for child in card.findall("property"):
        if (child.attrib.get("name") or "").casefold() in wanted:
            return sanitize(child.attrib.get("value", "") or (child.text or ""))
    return ""


def index_folder_images(sets_dir: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    if not sets_dir.exists():
        return index
    for path in sets_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
            continue
        guid = path.stem.lower().split(".")[0]
        index[guid] = path
        try:
            cards_at = path.parts.index("Cards")
            set_id = path.parts[cards_at - 1].lower()
            index[f"{set_id}/{guid}"] = path
        except ValueError:
            pass
    return index


def index_o8c(path: Path) -> tuple[dict[str, tuple[zipfile.ZipFile, str]], zipfile.ZipFile | None]:
    index: dict[str, tuple[zipfile.ZipFile, str]] = {}
    if not path or not path.exists():
        return index, None
    archive = zipfile.ZipFile(path)
    for name in archive.namelist():
        suffix = Path(name).suffix.lower()
        if suffix not in IMAGE_EXTS:
            continue
        guid = Path(name).stem.lower().split(".")[0]
        index[guid] = (archive, name)
        parts = Path(name).parts
        if "Sets" in parts:
            set_at = parts.index("Sets")
            if set_at + 1 < len(parts):
                index[f"{parts[set_at + 1].lower()}/{guid}"] = (archive, name)
    return index, archive


def lookup_image(folder_index: dict, zip_index: dict, set_id: str, card_id: str):
    card_id = (card_id or "").lower()
    set_id = (set_id or "").lower()
    for key in (f"{set_id}/{card_id}", card_id):
        if key in folder_index:
            return folder_index[key]
        if key in zip_index:
            return zip_index[key]
    return None


def copy_image(source, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(source, Path):
        shutil.copy2(source, dest)
        return
    archive, name = source
    dest.write_bytes(archive.read(name))


def source_ext(source) -> str:
    name = source.name if isinstance(source, Path) else source[1]
    return ext_from_url(name, Path(name).suffix or ".jpg")


GAMES = [
    {
        "id": "doomtown",
        "octgn": "doomtown",
        "plugin_name": "Doomtown",
        "author": "OCTGN / Db0, jbeast",
        "url": "http://classic-dtdb.co",
        "folder": "doomtown",
        "pascal": "Doomtown",
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
            ("rarity", "Rarity"),
            ("ghostRock", "Ghost Rock"),
            ("text", "Text"),
        ],
        "load_group": lambda card: (
            "playerNOutfit" if card.get("type") == "Outfit"
            else "sharedSetAside" if card.get("type") in {"Token", "Joker"}
            else "playerNDeck"
        ),
        "section_groups": {"Outfit": "playerNOutfit", "Starting Cards": "playerNStarting", "Deck": "playerNDeck"},
        "piles": [
            pile("Deck", "Deck", "deck"),
            pile("Discard", "Discard", "discard"),
            pile("BootHill", "Boot Hill", "aside"),
            pile("Hand", "Play Hand", "hand"),
            pile("DrawHand", "Draw Hand", "hand"),
            pile("Outfit", "Outfit", "inPlay", inPlay=True),
            pile("Starting", "Starting", "inPlay", inPlay=True),
            pile("Play", "Town", "inPlay", inPlay=True),
        ],
        "player_props": {
            "ghostRock": {"label": "Ghost Rock", "type": "integer", "default": 0, "min": 0},
            "influence": {"label": "Influence", "type": "integer", "default": 0, "min": 0},
            "control": {"label": "Control", "type": "integer", "default": 0, "min": 0},
            "victoryPoints": {"label": "Victory Points", "type": "integer", "default": 0, "min": 0},
        },
        "game_props": {},
        "phases": [("lowball", "Lowball"), ("upkeep", "Upkeep"), ("highNoon", "High Noon"), ("sundown", "Sundown"), ("nightfall", "Nightfall")],
        "announcements": [
            "Tabletop plugin from the OCTGN Doomtown (classic) set. No rules engine — Ghost Rock, town, Draw Hand, and Boot Hill are shortcuts.",
            "D = draw to Play Hand. P = pull to Draw Hand. Outfits load to the Outfit row.",
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
    },
    {
        "id": "mlp-ccg",
        "octgn": "mlp-ccg",
        "o8c": "MLP CCG - All Sets (2019).o8c",
        "plugin_name": "My Little Pony CCG",
        "author": "OCTGN / Gabby Gums, GameMasterLuna",
        "url": "https://discord.gg/QkGx4FT",
        "folder": "mlp-ccg",
        "pascal": "MlpCcg",
        "draw_group": "Deck",
        "type_keys": ("Type",),
        "extras": [
            ("number", "Number"),
            ("rarity", "Rarity"),
            ("element", "Element"),
            ("power", "Power"),
            ("cost", "Cost"),
            ("playRequired", "PlayRequiredPower"),
            ("keywords", "Keywords"),
            ("traits", "Traits"),
            ("text", "Text"),
        ],
        "load_group": lambda card: (
            "playerNStarting" if card.get("type") == "Mane Character"
            else "playerNProblemDeck" if card.get("type") == "Problem"
            else "playerNDeck"
        ),
        "section_groups": {
            "Mane Character": "playerNStarting",
            "Problems": "playerNProblemDeck",
            "Friends": "playerNDeck",
            "Resources": "playerNDeck",
            "Events": "playerNDeck",
            "Troublemakers": "playerNDeck",
        },
        "piles": [
            pile("Deck", "Deck", "deck"),
            pile("ProblemDeck", "Problem Deck", "deck"),
            pile("Discard", "Discard", "discard"),
            pile("Banished", "Banished", "aside"),
            pile("Hand", "Hand", "hand"),
            pile("Starting", "Mane", "inPlay", inPlay=True),
            pile("Play", "Play", "inPlay", inPlay=True),
            pile("Problems", "Problems", "inPlay", inPlay=True),
        ],
        "player_props": {
            "points": {"label": "Points", "type": "integer", "default": 0, "min": 0},
            "actions": {"label": "Action Tokens", "type": "integer", "default": 0, "min": 0},
        },
        "game_props": {},
        "phases": [("ready", "Ready"), ("troublemaker", "Troublemaker"), ("main", "Main"), ("score", "Score"), ("end", "End")],
        "announcements": [
            "Tabletop plugin from the OCTGN My Little Pony CCG set. No rules engine — Mane, Problem Deck, Points, and Action Tokens are shortcuts.",
            "D = draw. A = Action Token +1. Manes load to the Mane row; Problems load to the Problem Deck.",
        ],
        "card_back": "cards/back.png",
        "regions": [
            ("playerN+1Hand", "fan", "0%", "0%", "50%", "9%"),
            ("playerN+1Starting", "row", "50%", "0%", "12%", "12%"),
            ("playerN+1Problems", "row", "62%", "0%", "13%", "12%"),
            ("playerN+1Play", "free", "0%", "12%", "75%", "20%"),
            ("playerNPlay", "free", "0%", "36%", "50%", "20%"),
            ("playerNStarting", "row", "50%", "36%", "12%", "16%"),
            ("playerNProblems", "row", "62%", "36%", "13%", "16%"),
            ("playerNHand", "fan", "0%", "82%", "58%", "17%"),
            ("playerN+1Deck", "pile", "76%", "10%", "11%", "12%"),
            ("playerN+1ProblemDeck", "pile", "88%", "10%", "11%", "12%"),
            ("playerN+1Discard", "pile", "76%", "23%", "11%", "10%"),
            ("sharedSetAside", "pile", "88%", "23%", "11%", "10%"),
            ("playerNDeck", "pile", "76%", "58%", "11%", "14%"),
            ("playerNProblemDeck", "pile", "88%", "58%", "11%", "14%"),
            ("playerNDiscard", "pile", "76%", "44%", "11%", "12%"),
            ("playerNBanished", "pile", "88%", "44%", "11%", "12%"),
        ],
        "spawn_groups": ["playerNDeck", "playerNStarting", "playerNProblemDeck"],
        "deck_columns": [("name", "Name"), ("type", "Type"), ("element", "Element"), ("power", "Power"), ("packName", "Set")],
        "stat_buttons": [
            ("increase_points", "Pts +1", "decrease_points", "Pts -1"),
            ("increase_actions", "AT +1", "decrease_actions", "AT -1"),
        ],
    },
    {
        "id": "monty-python-ccg",
        "octgn": "montypython",
        "o8c": "monty-python_image_pack.o8c",
        "plugin_name": "Monty Python and the Holy Grail CCG",
        "author": "OCTGN / StormyWaters2021",
        "url": "http://www.TCGBuilder.net",
        "folder": "monty-python-ccg",
        "pascal": "MontyPythonCcg",
        "draw_group": "Deck",
        "type_keys": ("Card Type", "Type"),
        "extras": [
            ("subtype", "Subtype"),
            ("combat", "Combat"),
            ("wits", "Wits"),
            ("grail", "Grail"),
            ("rarity", "Rarity"),
            ("text", "Card Text"),
            ("altText", "Alternative Text"),
            ("number", "Card Number"),
        ],
        "load_group": lambda card: "sharedSetAside" if card.get("type") == "Pawn" else "playerNDeck",
        "section_groups": {"Deck": "playerNDeck", "Extra": "playerNExtra"},
        "piles": [
            pile("Deck", "Deck", "deck"),
            pile("Discard", "Dead Cart", "discard"),
            pile("Eliminated", "Eliminated", "aside"),
            pile("Extra", "Extra", "aside"),
            pile("Hand", "Hand", "hand"),
            pile("Play", "Play", "inPlay", inPlay=True),
        ],
        "player_props": {},
        "game_props": {},
        "phases": [("play", "Play"), ("combat", "Combat"), ("quest", "Quest")],
        "announcements": [
            "Tabletop plugin from the OCTGN Monty Python and the Holy Grail CCG set. No rules engine — draw, Dead Cart, and Extra are shortcuts.",
            "D = draw. Discard goes to the Dead Cart.",
        ],
        "card_back": "Images/cardback.jpg",
        "regions": [
            ("playerN+1Hand", "fan", "0%", "0%", "75%", "9%"),
            ("playerN+1Play", "free", "0%", "12%", "75%", "24%"),
            ("playerNPlay", "free", "0%", "42%", "75%", "24%"),
            ("playerNHand", "fan", "0%", "82%", "58%", "17%"),
            ("playerN+1Deck", "pile", "76%", "10%", "11%", "14%"),
            ("playerN+1Discard", "pile", "88%", "10%", "11%", "14%"),
            ("sharedSetAside", "pile", "76%", "25%", "11%", "12%"),
            ("playerNExtra", "pile", "88%", "25%", "11%", "12%"),
            ("playerNDeck", "pile", "76%", "58%", "11%", "16%"),
            ("playerNDiscard", "pile", "88%", "58%", "11%", "16%"),
            ("playerNEliminated", "pile", "88%", "42%", "11%", "14%"),
        ],
        "spawn_groups": ["playerNDeck", "playerNExtra"],
        "deck_columns": [("name", "Name"), ("type", "Type"), ("combat", "Combat"), ("wits", "Wits"), ("packName", "Set")],
    },
    {
        "id": "netrunner-1996",
        "octgn": "netrunner",
        "o8c": "netrunner-1996_image_pack.o8c",
        "plugin_name": "Netrunner (1996)",
        "author": "OCTGN / Db0, toon",
        "url": "https://github.com/db0/Netrunner-OCTGN",
        "folder": "netrunner-1996",
        "pascal": "Netrunner1996",
        "draw_group": "Deck",
        "type_keys": ("Type",),
        "extras": [
            ("player", "Player"),
            ("cost", "Cost"),
            ("mu", "MU Required"),
            ("keywords", "Keywords"),
            ("stat", "Stat"),
            ("text", "Rules"),
            ("flavor", "Flavor"),
            ("rarity", "Rarity"),
            ("number", "Number"),
        ],
        "load_group": lambda card: "sharedSetAside" if card.get("type") in {"Counter Hold", "Tracing", "Token"} else "playerNDeck",
        "section_groups": {"R&D / Stack": "playerNDeck", "R&D/Stack": "playerNDeck"},
        "piles": [
            pile("Deck", "R&D / Stack", "deck"),
            pile("Discard", "Archives", "discard"),
            pile("HiddenArchives", "Hidden Archives", "aside"),
            pile("Hand", "HQ / Hand", "hand"),
            pile("Play", "Play", "inPlay", inPlay=True),
        ],
        "player_props": {
            "actions": {"label": "Actions", "type": "integer", "default": 0, "min": 0},
            "bits": {"label": "Bits", "type": "integer", "default": 0, "min": 0},
            "agendaPoints": {"label": "Agenda Points", "type": "integer", "default": 0, "min": 0},
            "tags": {"label": "Tags", "type": "integer", "default": 0, "min": 0},
            "memory": {"label": "Memory", "type": "integer", "default": 0, "min": 0},
        },
        "game_props": {},
        "phases": [("start", "Start of Turn"), ("actions", "Actions"), ("end", "End of Turn")],
        "announcements": [
            "Tabletop plugin from the OCTGN 1996 Netrunner set (Wizards, not Android). No rules engine — Bits, Actions, Archives, and Tags are shortcuts.",
            "D = draw from R&D / Stack. B = Bits +1. One player Corp, one Runner — you keep the sides.",
        ],
        "card_back": "Card/back.jpg",
        "regions": [
            ("playerN+1Hand", "fan", "0%", "0%", "75%", "9%"),
            ("playerN+1Play", "free", "0%", "12%", "75%", "24%"),
            ("playerNPlay", "free", "0%", "42%", "75%", "24%"),
            ("playerNHand", "fan", "0%", "82%", "58%", "17%"),
            ("playerN+1Deck", "pile", "76%", "10%", "11%", "14%"),
            ("playerN+1Discard", "pile", "88%", "10%", "11%", "14%"),
            ("playerN+1HiddenArchives", "pile", "76%", "25%", "11%", "12%"),
            ("sharedSetAside", "pile", "88%", "25%", "11%", "12%"),
            ("playerNDeck", "pile", "76%", "58%", "11%", "16%"),
            ("playerNDiscard", "pile", "88%", "58%", "11%", "16%"),
            ("playerNHiddenArchives", "pile", "88%", "42%", "11%", "14%"),
        ],
        "spawn_groups": ["playerNDeck", "playerNHiddenArchives"],
        "deck_columns": [("name", "Name"), ("type", "Type"), ("player", "Side"), ("cost", "Cost"), ("packName", "Set")],
        "stat_buttons": [
            ("increase_bits", "Bit +1", "decrease_bits", "Bit -1"),
            ("increase_actions", "Act +1", "decrease_actions", "Act -1"),
            ("increase_agendaPoints", "AP +1", "decrease_agendaPoints", "AP -1"),
        ],
        "extra_actions": {
            "rollD6": [["VAR", "$ROLL", ["RANDOM_INT", 1, 6]], ["LOG", "{{$ALIAS_N}} rolled a {{$ROLL}}."]],
        },
        "extra_hotkeys": [{"key": "G", "actionList": "rollD6", "label": "Roll d6"}],
        "extra_menu": [{"label": "Roll d6", "actionList": "rollD6"}],
    },
    {
        "id": "x-files-ccg",
        "octgn": "x-files",
        "o8c": "x-files-ccg_image_pack.o8c",
        "plugin_name": "The X-Files CCG",
        "author": "OCTGN / StormyWaters2021",
        "url": "https://mandalornl.github.io/x-files-ccg/",
        "folder": "x-files-ccg",
        "pascal": "XFilesCcg",
        "draw_group": "Deck",
        "type_keys": ("Type",),
        "extras": [
            ("cost", "Cost"),
            ("keywords", "Keywords"),
            ("text", "Text"),
            ("health", "Health"),
            ("affiliation", "Affiliation"),
            ("rarity", "Rarity"),
            ("episode", "Episode"),
            ("number", "Card Number"),
        ],
        "load_group": lambda card: (
            "playerNXFile" if card.get("type") == "X-File"
            else "playerNStarting" if card.get("type") == "Agent"
            else "playerNDeck"
        ),
        "section_groups": {"Deck": "playerNDeck", "Side Deck": "playerNSide"},
        "piles": [
            pile("Deck", "Deck", "deck"),
            pile("Discard", "Discard", "discard"),
            pile("Removed", "Removed from Game", "aside"),
            pile("Side", "Side Deck", "aside"),
            pile("XFile", "X-File", "aside"),
            pile("Hand", "Hand", "hand"),
            pile("Starting", "Agents", "inPlay", inPlay=True),
            pile("Play", "Play", "inPlay", inPlay=True),
        ],
        "player_props": {
            "resources": {"label": "Resources", "type": "integer", "default": 0, "min": 0},
            "conspiracy": {"label": "Conspiracy", "type": "integer", "default": 0, "min": 0},
        },
        "game_props": {},
        "phases": [("assign", "Assign"), ("investigate", "Investigate"), ("combat", "Combat")],
        "announcements": [
            "Tabletop plugin from the OCTGN X-Files CCG set. No rules engine — Agents, X-File, Resources, and Conspiracy are shortcuts.",
            "D = draw. X-Files load facedown to the X-File pile. Agents load to the Agents row.",
        ],
        "card_back": "Images/cardback.jpg",
        "regions": [
            ("playerN+1Hand", "fan", "0%", "0%", "50%", "9%"),
            ("playerN+1Starting", "row", "50%", "0%", "25%", "12%"),
            ("playerN+1Play", "free", "0%", "12%", "75%", "22%"),
            ("playerNPlay", "free", "0%", "38%", "50%", "22%"),
            ("playerNStarting", "row", "50%", "38%", "25%", "16%"),
            ("playerNHand", "fan", "0%", "82%", "58%", "17%"),
            ("playerN+1Deck", "pile", "76%", "10%", "11%", "14%"),
            ("playerN+1Discard", "pile", "88%", "10%", "11%", "14%"),
            ("playerNXFile", "pile", "76%", "25%", "11%", "12%"),
            ("sharedSetAside", "pile", "88%", "25%", "11%", "12%"),
            ("playerNDeck", "pile", "76%", "58%", "11%", "16%"),
            ("playerNDiscard", "pile", "88%", "58%", "11%", "16%"),
            ("playerNSide", "pile", "76%", "44%", "11%", "12%"),
            ("playerNRemoved", "pile", "88%", "44%", "11%", "12%"),
        ],
        "spawn_groups": ["playerNDeck", "playerNStarting", "playerNXFile", "playerNSide"],
        "deck_columns": [("name", "Name"), ("type", "Type"), ("cost", "Cost"), ("affiliation", "Affiliation"), ("packName", "Set")],
        "stat_buttons": [
            ("increase_resources", "Res +1", "decrease_resources", "Res -1"),
            ("increase_conspiracy", "Con +1", "decrease_conspiracy", "Con -1"),
        ],
    },
]


def load_cards(game: dict, folder_index: dict, zip_index: dict) -> tuple[list[dict[str, str]], list[str], int]:
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    used: dict[str, int] = {}
    copied = 0
    octgn_dir = OCTGN / game["octgn"]
    images_root = IMAGES
    for set_path in sorted((octgn_dir / "Sets").glob("*/set.xml")):
        root = ET.parse(set_path).getroot()
        set_name = root.attrib.get("name", set_path.parent.name)
        set_id = root.attrib.get("id", "")
        if (root.attrib.get("hidden") or "").lower() == "true" and "marker" in set_name.lower():
            continue
        for card_el in root.findall("cards/card") or root.findall(".//card"):
            card_id = (card_el.attrib.get("id") or "").strip()
            name = sanitize(card_el.attrib.get("name", ""))
            if not card_id or not name:
                continue
            card_type = prop(card_el, *game["type_keys"]) or "Card"
            source = lookup_image(folder_index, zip_index, set_id, card_id)
            if not source:
                errors.append(f"{game['id']}: no image for {set_name} / {name}")
                continue
            ext = source_ext(source)
            rel = unique_rel(card_rel_path(game["folder"], game["pascal"], pretty_set(set_name), name, ext), used)
            dest = images_root / rel
            if not dest.exists() or dest.stat().st_size == 0:
                copy_image(source, dest)
            copied += 1
            card = {
                "databaseId": card_id,
                "name": name,
                "imageUrl": rel.replace("\\", "/"),
                "cardBack": "default",
                "type": card_type,
                "packName": pretty_set(set_name),
                "set": set_name,
            }
            for tsv_name, source_name in game.get("extras") or []:
                card[tsv_name] = prop(card_el, source_name)
            card["loadGroupId"] = game["load_group"](card)
            cards.append(card)
    return cards, errors, copied


def convert_decks(game: dict, cards: list[dict[str, str]]) -> tuple[dict, dict, list[str]]:
    known = {card["databaseId"].lower(): card for card in cards}
    errors: list[str] = []
    prebuilt: OrderedDict[str, dict] = OrderedDict()
    items: list[dict] = []
    section_groups = game.get("section_groups") or {}
    decks_dir = OCTGN / game["octgn"] / "Decks"
    if not decks_dir.exists():
        return {"preBuiltDecks": {}}, {"deckMenu": {"subMenus": []}}, errors
    for dek in sorted(decks_dir.rglob("*.o8d")):
        label = dek.stem.replace("_", " ").strip()
        deck_id = slug(label)
        try:
            root = ET.parse(dek).getroot()
        except ET.ParseError as exc:
            errors.append(f"{game['id']} {dek.name}: {exc}")
            continue
        entries = []
        for section in root.findall("section"):
            section_name = section.attrib.get("name") or "Deck"
            group = section_groups.get(section_name)
            for card_el in section.findall("card"):
                card_id = (card_el.attrib.get("id") or "").strip()
                qty = int(card_el.attrib.get("qty") or "1")
                card = known.get(card_id.lower())
                if not card:
                    errors.append(f"{game['id']} {dek.name}: unknown {card_el.text or card_id}")
                    continue
                entries.append({
                    "databaseId": card["databaseId"],
                    "quantity": qty,
                    "loadGroupId": group or card["loadGroupId"],
                })
        if not entries:
            continue
        prebuilt[deck_id] = {"label": label, "cards": entries}
        items.append({"deckListId": deck_id, "label": label})
    menus = [{"label": "OCTGN Decks", "deckLists": items}] if items else []
    return {"preBuiltDecks": dict(prebuilt)}, {"deckMenu": {"subMenus": menus}}, errors


def player_groups(player: str, piles: list[dict], draw_group: str) -> dict[str, dict]:
    groups = {}
    discard_suffix = next((spec["suffix"] for spec in piles if spec["groupType"] == "discard"), "Discard")
    for spec in piles:
        suffix = spec["suffix"]
        enter = {
            "controller": player,
            "deckGroupId": f"{player}{draw_group}",
            "discardGroupId": f"{player}{discard_suffix}",
        }
        if spec.get("inPlay"):
            enter["inPlay"] = True
        groups[f"{player}{suffix}"] = {
            "groupType": spec["groupType"],
            "label": f"Player {player[-1]} {spec['label']}",
            "tableLabel": spec["label"],
            "onCardEnter": enter,
        }
        if spec.get("inPlay"):
            groups[f"{player}{suffix}"]["canHaveAttachments"] = True
    return groups


def increment_actions(player_props: dict) -> dict:
    actions = {}
    for key, spec in player_props.items():
        label = spec["label"]
        actions[f"increase_{key}"] = [
            ["INCREASE_VAL", f"/playerData/$PLAYER_N/{key}", 1],
            ["LOG", f"{{{{$ALIAS_N}}}} gained 1 {label}."],
        ]
        actions[f"decrease_{key}"] = [
            ["DECREASE_VAL", f"/playerData/$PLAYER_N/{key}", 1],
            ["LOG", f"{{{{$ALIAS_N}}}} lost 1 {label}."],
        ]
    return actions


def tsv_columns(game: dict, cards: list[dict[str, str]]) -> list[str]:
    extras = [name for name, _ in game.get("extras") or []]
    columns = list(CORE_COLUMNS)
    for name in extras:
        if name not in columns:
            columns.append(name)
    return columns


def write_plugin_jsons(game: dict, cards: list[dict[str, str]], decks: dict, menu: dict, backs: dict[str, str]) -> None:
    jsons = ROOT / game["id"] / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    types = sorted({card["type"] for card in cards})
    folder = game["folder"]
    pascal_name = game["pascal"]
    draw_group = game["draw_group"]
    piles = game["piles"]
    dump_json(jsons / "main.json", {
        "pluginName": game["plugin_name"],
        "author": game["author"],
        "tutorialUrl": game["url"],
        "announcements": game["announcements"],
        "loadPreBuiltOnNewGame": False,
    })
    stamp_lobby_art(jsons, folder)
    dump_json(jsons / "imageUrlPrefix.json", {"imageUrlPrefix": {"Default": TOYBOX_PREFIX}})
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
    groups.update(player_groups("player1", piles, draw_group))
    groups.update(player_groups("player2", piles, draw_group))
    dump_json(jsons / "groups.json", {"groups": groups})
    regions = {}
    for group_id, rtype, left, top, width, height in game["regions"]:
        extra = {"disableDroppableAttachments": True} if rtype == "fan" else {}
        regions[group_id] = region(group_id, rtype, left, top, width, height, **extra)
    buttons = {
        "drawDeck": {"actionList": "drawDeck", "label": "Draw", "left": "76%", "top": "46%", "width": "11%", "height": "3.2%"},
        "readyAll": {"actionList": "readyAll", "label": "Ready All", "left": "88%", "top": "46%", "width": "11%", "height": "3.2%"},
    }
    top = 50.0
    for increase, inc_label, decrease, dec_label in game.get("stat_buttons") or []:
        buttons[increase] = {"actionList": increase, "label": inc_label, "left": "76%", "top": f"{top}%", "width": "11%", "height": "3.2%"}
        buttons[decrease] = {"actionList": decrease, "label": dec_label, "left": "88%", "top": f"{top}%", "width": "11%", "height": "3.2%"}
        top += 4.0
    for action, label, left, btop, width, height in game.get("extra_buttons") or []:
        buttons[action] = {"actionList": action, "label": label, "left": left, "top": btop, "width": width, "height": height}
    dump_json(jsons / "layouts.json", {"layouts": {"default": {
        "cardSize": 10,
        "rowSpacing": 2,
        "chat": {"left": "76%", "top": "78%", "width": "23%", "height": "21%"},
        "regions": regions,
        "tableButtons": buttons,
    }}})
    dump_json(jsons / "groupTypes.json", {"groupTypes": group_types()})
    dump_json(jsons / "playerCountMenu.json", {"playerCountMenu": [{"label": "2", "numPlayers": 2, "layoutId": "default"}]})
    dump_json(jsons / "phases.json", {"phases": {
        key: {"label": label, "height": f"{int(100 / max(len(game['phases']), 1))}%"} for key, label in game["phases"]
    }, "phaseOrder": [key for key, _ in game["phases"]]})
    dump_json(jsons / "steps.json", {"steps": {
        f"{key}Step": {"phaseId": key, "label": label} for key, label in game["phases"]
    }, "stepOrder": [f"{key}Step" for key, _ in game["phases"]]})
    dump_json(jsons / "playerProperties.json", {"playerProperties": game.get("player_props") or {}})
    dump_json(jsons / "gameProperties.json", {"gameProperties": game.get("game_props") or {}})
    dump_json(jsons / "topBarCounters.json", {"topBarCounters": {
        "shared": [{"label": "Round", "imageUrl": "", "gameProperty": "roundNumber"}],
        "player": [{"label": spec["label"], "imageUrl": "", "playerProperty": key} for key, spec in (game.get("player_props") or {}).items()],
    }})
    dump_json(jsons / "tokens.json", {"tokens": {
        "green": {
            "label": "+1", "left": "72%", "top": "4%", "width": "4vh", "height": "4vh",
            "imageUrl": toybox_url(f"{folder}/_plugin/{pascal_name}-TokenGreen.png"), "canBeNegative": True,
        },
        "red": {
            "label": "-1", "left": "50%", "top": "4%", "width": "4vh", "height": "4vh",
            "imageUrl": toybox_url(f"{folder}/_plugin/{pascal_name}-TokenRed.png"), "canBeNegative": True,
        },
    }})
    dump_json(jsons / "functions.json", {"functions": standard_functions()})
    actions = standard_actions(draw_group=draw_group)
    actions["flipCoin"] = [
        ["VAR", "$FLIP", ["RANDOM_INT", 1, 2]],
        ["COND", ["EQUAL", "$FLIP", 1], ["LOG", "{{$ALIAS_N}} flipped heads."], ["TRUE"], ["LOG", "{{$ALIAS_N}} flipped tails."]],
    ]
    actions.update(increment_actions(game.get("player_props") or {}))
    actions.update(game.get("extra_actions") or {})
    dump_json(jsons / "actionLists.json", {"actionLists": actions})
    game_hotkeys = [
        {"key": "D", "actionList": "drawDeck", "label": "Draw"},
        {"key": "S", "actionList": "shuffleDeck", "label": "Shuffle deck"},
        {"key": "R", "actionList": "readyAll", "label": "Ready all"},
        {"key": "C", "actionList": "flipCoin", "label": "Flip coin"},
    ]
    game_hotkeys.extend(game.get("extra_hotkeys") or [])
    dump_json(jsons / "hotkeys.json", {"hotkeys": {
        "game": game_hotkeys,
        "card": [
            {"key": "K", "actionList": "readyCard", "label": "Ready"},
            {"key": "E", "actionList": "spendCard", "label": "Exert / boot"},
            {"key": "F", "actionList": ["FLIP", "$ACTIVE_CARD_ID"], "label": "Flip"},
            {"key": "X", "actionList": ["DISCARD", "$ACTIVE_CARD_ID"], "label": "Discard"},
            {"key": "A", "actionList": ["DETACH", "$ACTIVE_CARD_ID"], "label": "Detach"},
            {"key": "H", "actionList": ["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"], "label": "Shuffle into deck"},
        ],
        "token": [
            {"key": "1", "tokenType": "green", "label": "Green +1"},
            {"key": "2", "tokenType": "red", "label": "Red +1"},
        ],
    }})
    plugin_menu = [
        {"label": "Draw", "actionList": "drawDeck"},
        {"label": "Shuffle deck", "actionList": "shuffleDeck"},
        {"label": "Ready all", "actionList": "readyAll"},
        {"label": "Flip coin", "actionList": "flipCoin"},
    ]
    for key, spec in (game.get("player_props") or {}).items():
        plugin_menu.append({"label": f"{spec['label']} +1", "actionList": f"increase_{key}"})
        plugin_menu.append({"label": f"{spec['label']} -1", "actionList": f"decrease_{key}"})
    plugin_menu.extend(game.get("extra_menu") or [])
    dump_json(jsons / "pluginMenu.json", {"pluginMenu": {"options": plugin_menu}})
    moves = [f"playerN{spec['suffix']}" for spec in piles] + ["playerN+1Play", "sharedSetAside"]
    dump_json(jsons / "cardMenu.json", {"cardMenu": {"moveToGroupIds": moves, "options": [
        {"label": "Ready", "actionList": "readyCard"},
        {"label": "Exert / boot", "actionList": "spendCard"},
        {"label": "Flip", "actionList": "flipCard"},
        {"label": "Discard", "actionList": "discardCard"},
        {"label": "Detach", "actionList": "detachCard"},
        {"label": "Shuffle into deck", "actionList": "shuffleIntoDeck"},
    ]}})
    dump_json(jsons / "groupMenu.json", {"groupMenu": {"moveToGroupIds": moves, "options": []}})
    dump_json(jsons / "browse.json", {"browse": {
        "filterPropertySideA": "type",
        "filterValuesSideA": types,
        "textPropertiesSideA": ["name", "packName", "text"],
    }})
    dump_json(jsons / "deckbuilder.json", {"deckbuilder": {
        "addButtons": [1, 2, 3, 4],
        "columns": [{"propName": name, "label": label} for name, label in game["deck_columns"]],
        "spawnGroups": [{"loadGroupId": gid, "label": gid.replace("playerN", "My ")} for gid in game["spawn_groups"]],
    }})
    dump_json(jsons / "spawnExistingCardModal.json", {"spawnExistingCardModal": {
        "columnProperties": [name for name, _ in game["deck_columns"]],
        "loadGroupIds": [gid.replace("playerN", "player1") for gid in game["spawn_groups"]] + ["player1Hand", "player2Hand"],
    }})
    face = {
        name: {"label": source.replace("_", " "), "type": "string", "default": ""}
        for name, source in game.get("extras") or []
    }
    face.update({
        "packName": {"label": "Set", "type": "string", "default": ""},
        "set": {"label": "OCTGN Set", "type": "string", "default": ""},
        "loadGroupId": {"label": "Load Group", "type": "string", "default": ""},
    })
    dump_json(jsons / "faceProperties.json", {"faceProperties": face})
    dump_json(jsons / "cardProperties.json", {"cardProperties": {}})
    dump_json(jsons / "defaultActions.json", {"defaultActions": []})
    dump_json(jsons / "automation.json", {"automation": {
        "postNewGameActionList": [[
            "LOG",
            f"{game['plugin_name']} table created. Load a deck from Menu → Load if one is listed. No rules are enforced.",
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


def write_plugin_art(game: dict) -> dict[str, str]:
    octgn_dir = OCTGN / game["octgn"]
    plugin = IMAGES / game["folder"] / "_plugin"
    plugin.mkdir(parents=True, exist_ok=True)
    backs: dict[str, str] = {}
    back = octgn_dir / game["card_back"]
    if back.exists():
        rel = copy_plugin_art(back, IMAGES, game["folder"], game["pascal"], "cardback-default")
        backs["default"] = rel
        shutil.copy2(back, IMAGES / lobby_art_rel(game["folder"], "logo"))
        shutil.copy2(back, IMAGES / lobby_art_rel(game["folder"], "banner"))
    else:
        backs["default"] = f"{game['folder']}/_plugin/{game['pascal']}-CardbackDefault.jpg"
    write_color_png(plugin / f"{game['pascal']}-TokenGreen.png", (48, 160, 72))
    write_color_png(plugin / f"{game['pascal']}-TokenRed.png", (196, 48, 48))
    return backs


def convert_game(game: dict) -> tuple[int, list[str]]:
    octgn_dir = OCTGN / game["octgn"]
    if not (octgn_dir / "definition.xml").exists():
        return 1, [f"{game['id']}: missing {octgn_dir}"]
    folder_index = index_folder_images(octgn_dir / "Sets")
    zip_index, archive = index_o8c(octgn_dir / game["o8c"]) if game.get("o8c") else ({}, None)
    try:
        cards, errors, copied = load_cards(game, folder_index, zip_index)
        if not cards:
            return 1, errors or [f"{game['id']}: no cards with art"]
        out = ROOT / game["id"]
        write_tsv(cards, tsv_columns(game, cards), out / "tsvs" / "cards.tsv")
        decks, menu, deck_errors = convert_decks(game, cards)
        errors.extend(deck_errors)
        backs = write_plugin_art(game)
        write_plugin_jsons(game, cards, decks, menu, backs)
        (out / "SOURCE.txt").write_text(
            "\n".join([
                f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from OCTGN {game['octgn']}.",
                f"Source: {octgn_dir}",
                f"Art: {'extracted Sets/ plus ' if folder_index else ''}{game.get('o8c') or 'Sets/*/Cards'}",
                f"Author credit: {game['author']}",
                "",
                "Tabletop plugin only — OCTGN scripts were not ported.",
                f"TSV rows: {len(cards)}  images copied: {copied}  missing art: {sum(1 for e in errors if 'no image' in e)}",
                f"Prebuilts: {len(decks['preBuiltDecks'])}",
                "",
            ]),
            encoding="utf-8",
        )
        print(f"Wrote {out.name}")
        print(f"  pluginName: {game['plugin_name']}")
        print(f"  tsv rows: {len(cards)}  copied: {copied}")
        print(f"  prebuilt decks: {len(decks['preBuiltDecks'])}")
        print(f"  types: {', '.join(sorted({c['type'] for c in cards}))}")
        missing = sum(1 for err in errors if "no image" in err)
        return (1 if missing > 40 else 0), errors
    finally:
        if archive is not None:
            archive.close()


def main() -> int:
    wanted = {arg for arg in sys.argv[1:] if not arg.startswith("-")}
    games = [game for game in GAMES if not wanted or game["id"] in wanted or game["octgn"] in wanted]
    if wanted and not games:
        print(f"No game matched {sorted(wanted)}")
        return 1
    status = 0
    all_errors: list[str] = []
    for game in games:
        code, errors = convert_game(game)
        status = status or code
        all_errors.extend(errors)
        print()
    missing = [err for err in all_errors if "no image" in err or "unknown" in err]
    if missing:
        print(f"{len(missing)} issue(s):")
        for err in missing[:50]:
            print(f"  - {err}")
        if len(missing) > 50:
            print(f"  … {len(missing) - 50} more")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
