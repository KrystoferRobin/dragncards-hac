#!/usr/bin/env python3
"""Build the remaining GitHub-backed Lackey plugins (tabletop only).

  python3 plugins/scripts/import_lackey_github_batch.py
  python3 plugins/scripts/import_lackey_github_batch.py rifts-ccg
  python3 plugins/scripts/collect_hosted_images.py rifts-ccg
"""

from __future__ import annotations

import shutil
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from image_names import TOYBOX_PREFIX, clear_image_url_prefix, lobby_art_rel, stamp_lobby_art, toybox_url  # noqa: E402
from lackey_tabletop import (  # noqa: E402
    copy_plugin_art,
    dump_json,
    group_types,
    load_image_urls,
    lookup_image,
    region,
    sanitize,
    slug,
    standard_actions,
    standard_functions,
    write_color_png,
    write_tsv,
)

LACKEY_ROOT = Path("/Users/krystoferrobin/Downloads/lackeyplugins")
IMAGES = ROOT / "images"

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


def pretty_set(name: str, mapping: dict[str, str]) -> str:
    if name in mapping:
        return mapping[name]
    return name.replace("_", " ")


def _has_image_ext(name: str) -> bool:
    return Path(name).suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def front_image(image_file: str) -> str:
    """Lackey sometimes stores 'front,back'. Commas can also be part of a filename."""
    if "," not in image_file:
        return image_file
    left, right = (part.strip() for part in image_file.split(",", 1))
    right_l = right.lower()
    if _has_image_ext(left) and _has_image_ext(right):
        return left
    if right_l in {"chback", "cardback", "silverback", "spawned"} or right_l.startswith("cardback") or right_l.startswith("rubble"):
        return left
    return image_file


def match_database_id(known: set[str], set_name: str, image_id: str) -> str:
    front = front_image(image_id)
    exact = f"{set_name}_{front}"
    if exact in known:
        return exact
    stem = Path(front).stem.lower()
    prefix = f"{set_name}_"
    for database_id in known:
        if not database_id.startswith(prefix):
            continue
        other = Path(database_id[len(prefix):]).stem.lower()
        if other == stem or other == f"{stem}-horizontal" or stem == f"{other}-horizontal":
            return database_id
    return ""


def load_group_by_type(type_map: dict[str, str], default: str):
    def choose(card: dict[str, str]) -> str:
        return type_map.get(card.get("type", ""), default)

    return choose


GAMES = [
    {
        "id": "rifts-ccg",
        "lackey": "RiftsCCG",
        "plugin_name": "Rifts CCG",
        "github": "https://github.com/wishmstr/RiftsCCG",
        "folder": "rifts-ccg",
        "pascal": "RiftsCcg",
        "draw_group": "Deck",
        "type_keys": ("card_type", "CardType", "Type"),
        "image_keys": ("Imagefile", "ImageFile"),
        "extras": [],
        "pack_names": {"Premiere": "Premiere"},
        "load_group": load_group_by_type({"Nation Card": "playerNNation"}, "playerNDeck"),
        "zone_groups": {"Deck": "playerNDeck", "Nation": "playerNNation"},
        "piles": [
            pile("Deck", "Deck", "deck"),
            pile("Discard", "Discard", "discard"),
            pile("Hand", "Hand", "hand"),
            pile("Nation", "Nation", "inPlay", inPlay=True),
            pile("Play", "Play", "inPlay", inPlay=True),
        ],
        "player_props": {},
        "game_props": {},
        "phases": [
            ("ready", "Ready"),
            ("draw", "Draw"),
            ("play", "Play Cards"),
            ("attack", "Attack"),
            ("end", "End Turn"),
        ],
        "announcements": [
            "Tabletop plugin from the Lackey Rifts CCG set. No rules engine — Draw, Ready, and Nation are shortcuts.",
            "D = draw. R = ready all. X = discard. Nation cards load to the Nation row.",
        ],
        "regions": [
            ("playerN+1Hand", "fan", "0%", "0%", "58%", "9%"),
            ("playerN+1Nation", "row", "58%", "0%", "17%", "12%"),
            ("playerN+1Play", "free", "0%", "12%", "75%", "22%"),
            ("playerNPlay", "free", "0%", "40%", "58%", "22%"),
            ("playerNNation", "row", "58%", "40%", "17%", "16%"),
            ("playerNHand", "fan", "0%", "82%", "58%", "17%"),
            ("playerN+1Deck", "pile", "76%", "10%", "11%", "14%"),
            ("playerN+1Discard", "pile", "88%", "10%", "11%", "14%"),
            ("sharedSetAside", "pile", "76%", "25%", "23%", "12%"),
            ("playerNDeck", "pile", "76%", "58%", "11%", "16%"),
            ("playerNDiscard", "pile", "88%", "58%", "11%", "16%"),
        ],
        "spawn_groups": ["playerNDeck", "playerNNation"],
        "deck_columns": [("name", "Name"), ("type", "Type"), ("packName", "Set")],
    },
    {
        "id": "gundam-ms-war-ccg",
        "lackey": "GundamMSWarCCG",
        "plugin_name": "Gundam: The Movie MS War CCG",
        "github": "https://github.com/wishmstr/GundamMSWarCCG",
        "folder": "gundam-ms-war-ccg",
        "pascal": "GundamMsWarCcg",
        "draw_group": "SupplyBase",
        "type_keys": ("CardType", "Type"),
        "image_keys": ("ImageFile", "Imagefile"),
        "extras": [
            ("corps", "CorpsSymbol"),
            ("price", "Price"),
            ("clash", "ClashPoints"),
            ("msType", "MSType"),
            ("dockPilot", "Dock Pilot"),
            ("limited", "Limited"),
            ("unique", "Unique"),
            ("preemptive", "Preemptive Strike"),
        ],
        "pack_names": {"set1": "Set 1", "set2": "Set 2", "set3": "Set 3"},
        "load_group": lambda card: "playerNSupplyBase",
        "zone_groups": {"Supply Base": "playerNSupplyBase"},
        "piles": [
            pile("SupplyBase", "Supply Base", "deck"),
            pile("Defunct", "Defunct Pile", "discard"),
            pile("Hand", "Hand", "hand"),
            pile("DryDock", "Dry Dock", "inPlay", inPlay=True),
            pile("Play", "Play", "inPlay", inPlay=True),
        ],
        "player_props": {
            "warXp": {"label": "War Experience", "type": "integer", "default": 0, "min": 0},
        },
        "game_props": {},
        "phases": [
            ("preliminary", "Preliminary"),
            ("attack", "Attack"),
            ("strategic", "Strategic"),
            ("recuperation", "Recuperation"),
        ],
        "announcements": [
            "Tabletop plugin from the Lackey Gundam MS War CCG set. No rules engine — Draw is from Supply Base; Dry Dock and Defunct are shortcuts.",
            "D = draw. R = ready all. V = War Experience +1.",
        ],
        "regions": [
            ("playerN+1Hand", "fan", "0%", "0%", "58%", "9%"),
            ("playerN+1DryDock", "row", "58%", "0%", "17%", "12%"),
            ("playerN+1Play", "free", "0%", "12%", "75%", "22%"),
            ("playerNPlay", "free", "0%", "40%", "58%", "22%"),
            ("playerNDryDock", "row", "58%", "40%", "17%", "16%"),
            ("playerNHand", "fan", "0%", "82%", "58%", "17%"),
            ("playerN+1SupplyBase", "pile", "76%", "10%", "11%", "14%"),
            ("playerN+1Defunct", "pile", "88%", "10%", "11%", "14%"),
            ("sharedSetAside", "pile", "76%", "25%", "23%", "12%"),
            ("playerNSupplyBase", "pile", "76%", "58%", "11%", "16%"),
            ("playerNDefunct", "pile", "88%", "58%", "11%", "16%"),
        ],
        "spawn_groups": ["playerNSupplyBase", "playerNDryDock"],
        "deck_columns": [("name", "Name"), ("type", "Type"), ("corps", "Corps"), ("price", "Price"), ("packName", "Set")],
        "stat_buttons": [("increase_warXp", "XP +1", "decrease_warXp", "XP -1")],
        "extra_hotkeys": [{"key": "V", "actionList": "increase_warXp", "label": "War Experience +1"}],
    },
    {
        "id": "legend-of-mana-ccg",
        "lackey": "LegendOfManaCCG",
        "plugin_name": "Legend of Mana CCG",
        "github": "https://github.com/wishmstr/LegendOfManaCCG",
        "folder": "legend-of-mana-ccg",
        "pascal": "LegendOfManaCcg",
        "draw_group": "MainDeck",
        "type_keys": ("CardType", "Type"),
        "image_keys": ("ImageFile", "Imagefile"),
        "extras": [
            ("cost", "Cost"),
            ("attribute", "Attribute"),
            ("attributeCondition", "AttributeCondition"),
            ("basicMana", "BasicMana"),
            ("landName", "LandName"),
            ("strength", "Strength"),
            ("defense", "Defense"),
            ("usageTiming", "UsageTiming"),
            ("specialSkill", "SpecialSkill"),
        ],
        "pack_names": {"core": "Core"},
        "load_group": load_group_by_type({"Character": "playerNCharacterDeck"}, "playerNMainDeck"),
        "zone_groups": {"Main Deck": "playerNMainDeck", "Character Deck": "playerNCharacterDeck"},
        "piles": [
            pile("MainDeck", "Main Deck", "deck"),
            pile("CharacterDeck", "Character Deck", "deck"),
            pile("Discard", "Discard", "discard"),
            pile("Hand", "Hand", "hand"),
            pile("Play", "Play", "inPlay", inPlay=True),
        ],
        "player_props": {
            "mana": {"label": "Mana", "type": "integer", "default": 0, "min": 0},
        },
        "game_props": {},
        "phases": [
            ("start", "Start"),
            ("main", "Main"),
            ("monsters", "Monster Placement"),
            ("end", "End"),
        ],
        "announcements": [
            "Tabletop plugin from the Lackey Legend of Mana CCG set. No rules engine — Main Deck, Character Deck, and Mana are shortcuts.",
            "D = draw main. T = draw a character into play. M = Mana +1. Character cards use the character back.",
        ],
        "card_backs": {"default": "cardback.jpg", "character": "chback.jpg"},
        "card_back_for_type": {"Character": "character"},
        "regions": [
            ("playerN+1Hand", "fan", "0%", "0%", "75%", "9%"),
            ("playerN+1Play", "free", "0%", "12%", "75%", "24%"),
            ("playerNPlay", "free", "0%", "42%", "75%", "24%"),
            ("playerNHand", "fan", "0%", "82%", "58%", "17%"),
            ("playerN+1MainDeck", "pile", "76%", "10%", "11%", "14%"),
            ("playerN+1CharacterDeck", "pile", "88%", "10%", "11%", "14%"),
            ("playerN+1Discard", "pile", "76%", "25%", "11%", "12%"),
            ("sharedSetAside", "pile", "88%", "25%", "11%", "12%"),
            ("playerNMainDeck", "pile", "76%", "58%", "11%", "16%"),
            ("playerNCharacterDeck", "pile", "88%", "58%", "11%", "16%"),
            ("playerNDiscard", "pile", "76%", "42%", "11%", "14%"),
        ],
        "spawn_groups": ["playerNMainDeck", "playerNCharacterDeck"],
        "deck_columns": [("name", "Name"), ("type", "Type"), ("cost", "Cost"), ("attribute", "Attribute"), ("packName", "Set")],
        "stat_buttons": [("increase_mana", "Mana +1", "decrease_mana", "Mana -1")],
        "extra_actions": {
            "drawCharacter": [[
                "COND",
                ["GROUP_EMPTY", "{{$PLAYER_N}}CharacterDeck"],
                ["LOG", "{{$ALIAS_N}} tried to draw a character from an empty Character Deck."],
                ["TRUE"],
                [
                    ["MOVE_STACKS", "{{$PLAYER_N}}CharacterDeck", "{{$PLAYER_N}}Play", 1, "bottom"],
                    ["LOG", "{{$ALIAS_N}} drew a character."],
                ],
            ]],
        },
        "extra_hotkeys": [{"key": "T", "actionList": "drawCharacter", "label": "Draw character"}],
        "extra_menu": [{"label": "Draw character", "actionList": "drawCharacter"}],
        "extra_buttons": [("drawCharacter", "Draw Char", "76%", "50%", "23%", "3.2%")],
    },
    {
        "id": "maple-story",
        "lackey": "MapleStory",
        "plugin_name": "MapleStory TCG",
        "github": "https://github.com/wishmstr/MapleStory",
        "folder": "maple-story",
        "pascal": "MapleStory",
        "draw_group": "Deck",
        "type_keys": ("Type",),
        "image_keys": ("ImageFile", "Imagefile"),
        "extras": [
            ("klass", "Class"),
            ("level", "Level"),
            ("attack", "Attack"),
            ("hp", "HP"),
            ("type2", "Type2"),
            ("text", "Text"),
            ("text2", "Text2"),
            ("text3", "Text3"),
            ("rarity", "Rarity"),
            ("number", "Number"),
        ],
        "pack_names": {
            "Set1": "Set 1",
            "Set2": "Set 2",
            "Set3": "Set 3",
            "Set4": "Set 4",
            "Set5": "Set 5",
            "Set6": "Set 6",
            "Promo": "Promo",
        },
        "load_group": load_group_by_type({"Character": "playerNStarting"}, "playerNDeck"),
        "zone_groups": {"Deck": "playerNDeck", "Starting": "playerNStarting"},
        "piles": [
            pile("Deck", "Deck", "deck"),
            pile("Discard", "Discard", "discard"),
            pile("Hand", "Hand", "hand"),
            pile("Starting", "Starting", "inPlay", inPlay=True),
            pile("Play", "Play", "inPlay", inPlay=True),
            pile("Pet", "Pet", "aside"),
        ],
        "player_props": {
            "level": {"label": "Level", "type": "integer", "default": 0, "min": 0},
            "hitPoints": {"label": "HP", "type": "integer", "default": 0, "min": 0},
        },
        "game_props": {},
        "phases": [
            ("levelUp", "Level Up"),
            ("actions", "Character Actions"),
            ("attack", "Attack With Monsters"),
        ],
        "announcements": [
            "Tabletop plugin from the Lackey MapleStory set. No rules engine — Level, HP, Starting, and Feed Pet are shortcuts.",
            "D = draw. R = ready all. L / H = Level / HP +1. P = feed pet (top of deck facedown).",
        ],
        "regions": [
            ("playerN+1Hand", "fan", "0%", "0%", "58%", "9%"),
            ("playerN+1Starting", "row", "58%", "0%", "17%", "12%"),
            ("playerN+1Play", "free", "0%", "12%", "75%", "22%"),
            ("playerNPlay", "free", "0%", "40%", "58%", "22%"),
            ("playerNStarting", "row", "58%", "40%", "17%", "16%"),
            ("playerNHand", "fan", "0%", "82%", "58%", "17%"),
            ("playerN+1Deck", "pile", "76%", "10%", "11%", "14%"),
            ("playerN+1Discard", "pile", "88%", "10%", "11%", "14%"),
            ("sharedSetAside", "pile", "76%", "25%", "11%", "12%"),
            ("playerNPet", "pile", "88%", "25%", "11%", "12%"),
            ("playerNDeck", "pile", "76%", "58%", "11%", "16%"),
            ("playerNDiscard", "pile", "88%", "58%", "11%", "16%"),
        ],
        "spawn_groups": ["playerNDeck", "playerNStarting"],
        "deck_columns": [("name", "Name"), ("type", "Type"), ("klass", "Class"), ("level", "Level"), ("packName", "Set")],
        "stat_buttons": [
            ("increase_level", "Lv +1", "decrease_level", "Lv -1"),
            ("increase_hitPoints", "HP +1", "decrease_hitPoints", "HP -1"),
        ],
        "extra_actions": {
            "feedPet": [[
                "COND",
                ["GROUP_EMPTY", "{{$PLAYER_N}}Deck"],
                ["LOG", "{{$ALIAS_N}} tried to feed a pet from an empty deck."],
                ["TRUE"],
                [
                    ["MOVE_STACKS", "{{$PLAYER_N}}Deck", "{{$PLAYER_N}}Pet", 1, "bottom"],
                    ["LOG", "{{$ALIAS_N}} fed a pet (top of deck, facedown)."],
                ],
            ]],
        },
        "extra_hotkeys": [{"key": "P", "actionList": "feedPet", "label": "Feed pet"}],
        "extra_menu": [{"label": "Feed pet", "actionList": "feedPet"}],
        "extra_buttons": [("feedPet", "Feed Pet", "76%", "54%", "23%", "3.2%")],
    },
    {
        "id": "nightmare-before-christmas",
        "lackey": "NightmareBeforeChristmas",
        "plugin_name": "The Nightmare Before Christmas CCG",
        "github": "https://github.com/wishmstr/Nightmare-Before-Christmas-CCG",
        "folder": "nightmare-before-christmas",
        "pascal": "NightmareBeforeChristmas",
        "draw_group": "Deck",
        "type_keys": ("Type",),
        "image_keys": ("ImageFile", "Imagefile"),
        "extras": [
            ("scare", "Scare_Threshold"),
            ("rarity", "Rarity"),
            ("text", "CardText"),
        ],
        "pack_names": {
            "Premiere": "Premiere",
            "ChristmasTown": "Christmas Town",
            "Tournament": "Tournament",
            "PlayerAids": "Player Aids",
        },
        "load_group": lambda card: (
            "playerNAids" if card.get("set") == "PlayerAids"
            else "playerNLocale" if card.get("type") == "Locale"
            else "playerNDeck"
        ),
        "zone_groups": {
            "Deck": "playerNDeck",
            "Locale": "playerNLocale",
            "Starting Locale": "playerNStartingLocale",
            "Player Aids": "playerNAids",
        },
        "piles": [
            pile("Deck", "Deck", "deck"),
            pile("Discard", "Discard", "discard"),
            pile("Hand", "Hand", "hand"),
            pile("Locale", "Locale", "inPlay", inPlay=True),
            pile("StartingLocale", "Starting Locale", "inPlay", inPlay=True),
            pile("Aids", "Player Aids", "aside"),
            pile("Play", "Play", "inPlay", inPlay=True),
        ],
        "player_props": {},
        "game_props": {
            "daysUntilChristmas": {"label": "Days Until Christmas", "type": "integer", "default": 12, "min": 0},
        },
        "phases": [
            ("start", "Start"),
            ("turn", "Player Turn"),
            ("end", "End"),
        ],
        "announcements": [
            "Tabletop plugin from the Lackey Nightmare Before Christmas CCG set. No rules engine — locales, player aids, and the day counter are shortcuts.",
            "D = draw. Y = one day closer to Christmas. Locales and starting locales load to their rows.",
        ],
        "regions": [
            ("playerN+1Hand", "fan", "0%", "0%", "50%", "9%"),
            ("playerN+1StartingLocale", "row", "50%", "0%", "12%", "12%"),
            ("playerN+1Locale", "row", "0%", "12%", "75%", "10%"),
            ("playerN+1Play", "free", "0%", "22%", "75%", "16%"),
            ("playerNPlay", "free", "0%", "40%", "50%", "18%"),
            ("playerNLocale", "row", "0%", "58%", "62%", "10%"),
            ("playerNStartingLocale", "row", "50%", "40%", "12%", "16%"),
            ("playerNAids", "row", "62%", "58%", "13%", "10%"),
            ("playerNHand", "fan", "0%", "82%", "58%", "17%"),
            ("playerN+1Deck", "pile", "76%", "10%", "11%", "14%"),
            ("playerN+1Discard", "pile", "88%", "10%", "11%", "14%"),
            ("sharedSetAside", "pile", "76%", "25%", "23%", "12%"),
            ("playerNDeck", "pile", "76%", "58%", "11%", "16%"),
            ("playerNDiscard", "pile", "88%", "58%", "11%", "16%"),
        ],
        "spawn_groups": ["playerNDeck", "playerNLocale", "playerNStartingLocale", "playerNAids"],
        "deck_columns": [("name", "Name"), ("type", "Type"), ("scare", "Scare"), ("packName", "Set")],
        "extra_actions": {
            "decreaseDays": [
                ["DECREASE_VAL", "/daysUntilChristmas", 1],
                ["LOG", "{{$ALIAS_N}} removed a day until Christmas."],
            ],
            "increaseDays": [
                ["INCREASE_VAL", "/daysUntilChristmas", 1],
                ["LOG", "{{$ALIAS_N}} added a day until Christmas."],
            ],
        },
        "extra_hotkeys": [{"key": "Y", "actionList": "decreaseDays", "label": "Day -1"}],
        "extra_menu": [
            {"label": "Day -1", "actionList": "decreaseDays"},
            {"label": "Day +1", "actionList": "increaseDays"},
        ],
        "extra_buttons": [
            ("decreaseDays", "Day -1", "76%", "50%", "11%", "3.2%"),
            ("increaseDays", "Day +1", "88%", "50%", "11%", "3.2%"),
        ],
        "topbar_shared": [{"label": "Days", "imageUrl": "", "gameProperty": "daysUntilChristmas"}],
    },
    {
        "id": "mmtcg",
        "lackey": "MMTCG",
        "plugin_name": "Mega Man TCG",
        "github": "https://github.com/wishmstr/MMTCG",
        "folder": "mmtcg",
        "pascal": "Mmtcg",
        "draw_group": "Deck",
        "type_keys": ("Type",),
        "image_keys": ("ImageFile", "Imagefile"),
        "extras": [
            ("title", "Title"),
            ("tags", "Tags"),
            ("emblem", "Emblem"),
            ("color", "Color"),
            ("strength", "Strength"),
            ("defense", "Defense"),
            ("blast", "Blast"),
            ("destiny", "Destiny"),
            ("requiredPower", "Required_Power"),
            ("requiredColor", "Required_Color"),
            ("requiredEmblem", "Required_Emblem"),
            ("text", "Text"),
            ("help", "Help"),
            ("number", "Number"),
        ],
        "pack_names": {
            "PowerUp": "Power Up",
            "Grave": "Grave",
            "GrandPrix": "Grand Prix",
            "Promo": "Promo",
            "LevelUp": "Level Up",
        },
        "load_group": load_group_by_type({"NetNavi": "playerNNetNavi"}, "playerNDeck"),
        "zone_groups": {"Deck": "playerNDeck", "NetNavi": "playerNNetNavi"},
        "piles": [
            pile("Deck", "Deck", "deck"),
            pile("Discard", "Discard", "discard"),
            pile("Hand", "Hand", "hand"),
            pile("NetNavi", "NetNavi", "inPlay", inPlay=True),
            pile("Play", "Play", "inPlay", inPlay=True),
            pile("PowerUp", "Power Up", "aside"),
        ],
        "player_props": {},
        "game_props": {},
        "phases": [
            ("draw", "Draw"),
            ("resource", "Resource"),
            ("main", "Main"),
            ("battle", "Battle"),
        ],
        "announcements": [
            "Tabletop plugin from the Lackey Mega Man TCG set. No rules engine — NetNavi, Power Up, and mill-for-damage are shortcuts.",
            "D = draw. U = power up (top of deck facedown). M = 1 damage (mill to discard).",
        ],
        "regions": [
            ("playerN+1Hand", "fan", "0%", "0%", "58%", "9%"),
            ("playerN+1NetNavi", "row", "58%", "0%", "17%", "12%"),
            ("playerN+1Play", "free", "0%", "12%", "75%", "22%"),
            ("playerNPlay", "free", "0%", "40%", "58%", "22%"),
            ("playerNNetNavi", "row", "58%", "40%", "17%", "16%"),
            ("playerNHand", "fan", "0%", "82%", "58%", "17%"),
            ("playerN+1Deck", "pile", "76%", "10%", "11%", "14%"),
            ("playerN+1Discard", "pile", "88%", "10%", "11%", "14%"),
            ("playerNPowerUp", "pile", "76%", "25%", "11%", "12%"),
            ("sharedSetAside", "pile", "88%", "25%", "11%", "12%"),
            ("playerNDeck", "pile", "76%", "58%", "11%", "16%"),
            ("playerNDiscard", "pile", "88%", "58%", "11%", "16%"),
        ],
        "spawn_groups": ["playerNDeck", "playerNNetNavi"],
        "deck_columns": [("name", "Name"), ("type", "Type"), ("color", "Color"), ("strength", "Str"), ("packName", "Set")],
        "extra_actions": {
            "powerUp": [[
                "COND",
                ["GROUP_EMPTY", "{{$PLAYER_N}}Deck"],
                ["LOG", "{{$ALIAS_N}} tried to power up from an empty deck."],
                ["TRUE"],
                [
                    ["MOVE_STACKS", "{{$PLAYER_N}}Deck", "{{$PLAYER_N}}PowerUp", 1, "bottom"],
                    ["LOG", "{{$ALIAS_N}} powered up (top of deck)."],
                ],
            ]],
            "millDamage": [[
                "COND",
                ["GROUP_EMPTY", "{{$PLAYER_N}}Deck"],
                ["LOG", "{{$ALIAS_N}} tried to take damage from an empty deck."],
                ["TRUE"],
                [
                    ["MOVE_STACKS", "{{$PLAYER_N}}Deck", "{{$PLAYER_N}}Discard", 1, "bottom"],
                    ["LOG", "{{$ALIAS_N}} took 1 damage (milled)."],
                ],
            ]],
        },
        "extra_hotkeys": [
            {"key": "U", "actionList": "powerUp", "label": "Power up"},
            {"key": "M", "actionList": "millDamage", "label": "1 damage (mill)"},
        ],
        "extra_menu": [
            {"label": "Power up", "actionList": "powerUp"},
            {"label": "1 damage (mill)", "actionList": "millDamage"},
        ],
        "extra_buttons": [
            ("powerUp", "Power Up", "76%", "50%", "11%", "3.2%"),
            ("millDamage", "1 Dmg", "88%", "50%", "11%", "3.2%"),
        ],
    },
    {
        "id": "fpg-guardians",
        "lackey": "FPGGuardians",
        "plugin_name": "Guardians (FPG)",
        "github": "https://github.com/wishmstr/FPGGuardians",
        "folder": "fpg-guardians",
        "pascal": "FpgGuardians",
        "draw_group": "Deck",
        "type_keys": ("Type",),
        "image_keys": ("ImageFile", "Imagefile"),
        "extras": [
            ("klass", "Class"),
            ("vp", "VP"),
            ("flying", "Flying"),
            ("size", "Size"),
            ("vitality", "Vitality"),
            ("vitRed", "Vit. Red"),
            ("ocb", "OCB"),
            ("babes", "Babes"),
            ("gold", "Gold"),
            ("beer", "Beer"),
            ("channeling", "Channeling"),
            ("channeler", "Channeler"),
            ("ranged", "Ranged attack"),
            ("command", "Command"),
            ("powerStones", "Power stones"),
            ("basicDraw", "basic draw"),
            ("ldl", "LDL"),
            ("mdl", "MDL"),
            ("luc", "LUC"),
            ("effect", "Effect"),
            ("bonus", "Bonus"),
            ("script", "Script"),
        ],
        "pack_names": {
            "RE": "Revised Edition",
            "DI": "Dagger Isle",
            "DN": "Drifter's Nexus",
            "NP": "Necropolis Park",
            "Events": "Events",
            "Adventure": "Adventure",
            "PR": "Promo",
        },
        "load_group": lambda card: (
            "playerNAdventure" if card.get("type", "").lower() == "adventure"
            else "playerNStarting" if card.get("type", "").lower() == "guardian"
            else "playerNDeck"
        ),
        "zone_groups": {
            "Deck": "playerNDeck",
            "Starting": "playerNStarting",
            "Adventure": "playerNAdventure",
        },
        "piles": [
            pile("Deck", "Deck", "deck"),
            pile("Adventure", "Adventure", "deck"),
            pile("Discard", "Discard", "discard"),
            pile("Hand", "Hand", "hand"),
            pile("Starting", "Starting", "inPlay", inPlay=True),
            pile("Play", "Play", "inPlay", inPlay=True),
            pile("CreaturePen", "Creature Pen", "inPlay", inPlay=True),
            pile("Storage", "Storage Depot", "aside"),
            pile("Reinforce", "Reinforce", "aside"),
        ],
        "player_props": {},
        "game_props": {},
        "phases": [
            ("organize", "Draw and Organize"),
            ("combat", "Movement and Combat"),
            ("terrain", "Terrain Settlement"),
        ],
        "announcements": [
            "Tabletop plugin from the Lackey FPG Guardians set. No rules engine — Starting, Adventure, Storage Depot, Creature Pen, and Reinforce are shortcuts.",
            "D = draw. A = draw adventure. G = roll a d6. Guardians load to Starting; Adventure cards load to the Adventure deck.",
        ],
        "regions": [
            ("playerN+1Hand", "fan", "0%", "0%", "50%", "9%"),
            ("playerN+1Starting", "row", "50%", "0%", "25%", "11%"),
            ("playerN+1Play", "free", "0%", "12%", "75%", "14%"),
            ("playerN+1CreaturePen", "row", "0%", "26%", "75%", "8%"),
            ("playerNPlay", "free", "0%", "36%", "50%", "16%"),
            ("playerNStarting", "row", "50%", "36%", "25%", "12%"),
            ("playerNCreaturePen", "row", "0%", "52%", "50%", "10%"),
            ("playerNStorage", "row", "50%", "52%", "25%", "10%"),
            ("playerNReinforce", "pile", "0%", "62%", "12%", "12%"),
            ("playerNHand", "fan", "12%", "82%", "46%", "17%"),
            ("playerN+1Deck", "pile", "76%", "10%", "11%", "12%"),
            ("playerN+1Adventure", "pile", "88%", "10%", "11%", "12%"),
            ("playerN+1Discard", "pile", "76%", "23%", "11%", "10%"),
            ("sharedSetAside", "pile", "88%", "23%", "11%", "10%"),
            ("playerNDeck", "pile", "76%", "58%", "11%", "14%"),
            ("playerNAdventure", "pile", "88%", "58%", "11%", "14%"),
            ("playerNDiscard", "pile", "76%", "44%", "11%", "12%"),
        ],
        "spawn_groups": ["playerNDeck", "playerNStarting", "playerNAdventure", "playerNStorage"],
        "deck_columns": [("name", "Name"), ("type", "Type"), ("klass", "Class"), ("vp", "VP"), ("packName", "Set")],
        "extra_actions": {
            "drawAdventure": [[
                "COND",
                ["GROUP_EMPTY", "{{$PLAYER_N}}Adventure"],
                ["LOG", "{{$ALIAS_N}} tried to draw from an empty Adventure deck."],
                ["TRUE"],
                [
                    ["MOVE_STACKS", "{{$PLAYER_N}}Adventure", "{{$PLAYER_N}}Play", 1, "bottom"],
                    ["LOG", "{{$ALIAS_N}} drew an Adventure card."],
                ],
            ]],
            "rollD6": [
                ["VAR", "$ROLL", ["RANDOM_INT", 1, 6]],
                ["LOG", "{{$ALIAS_N}} rolled a {{$ROLL}}."],
            ],
        },
        "extra_hotkeys": [
            {"key": "A", "actionList": "drawAdventure", "label": "Draw adventure"},
            {"key": "G", "actionList": "rollD6", "label": "Roll d6"},
        ],
        "extra_menu": [
            {"label": "Draw adventure", "actionList": "drawAdventure"},
            {"label": "Roll d6", "actionList": "rollD6"},
        ],
        "extra_buttons": [
            ("drawAdventure", "Adv.", "88%", "44%", "11%", "3.2%"),
            ("rollD6", "d6", "88%", "48%", "11%", "3.2%"),
        ],
    },
    {
        "id": "shadowfist",
        "lackey": "shadowfist",
        "plugin_name": "Shadowfist",
        "author": "Lackey / NoSoup4you",
        "github": "https://github.com/NoSoup4you/Shadowfist-LackeyCCG",
        "github_branch": "master",
        "folder": "shadowfist",
        "pascal": "Shadowfist",
        "draw_group": "Deck",
        "type_keys": ("Type",),
        "image_keys": ("ImageFile", "Imagefile"),
        "extras": [
            ("faction", "Faction"),
            ("subtitle", "Subtitle"),
            ("cost", "Cost"),
            ("requires", "Requires"),
            ("provides", "Provides"),
            ("fighting", "Fighting"),
            ("power", "Power"),
            ("body", "Body"),
            ("rarity", "Rarity"),
            ("designators", "Designators"),
            ("text", "Text"),
        ],
        "pack_names": {
            "standard": "Limited / Standard",
            "10kbullets": "10,000 Bullets",
            "7masters": "Seven Masters",
            "backforseconds": "Back for Seconds",
            "boomchakalaka": "Boom Chaka Laka",
            "canofwhupass": "Can of Whupass",
            "combatinkowloon": "Combat in Kowloon",
            "criticalshift": "Critical Shift",
            "darkfuture": "Dark Future",
            "empireofevil": "Empire of Evil",
            "endgame": "Endgame",
            "flashpoint": "Flashpoint",
            "knightspassage": "Knight's Passage",
            "modern": "Modern Promos",
            "netherworld": "Netherworld",
            "netherworld2": "Netherworld 2",
            "promos": "Promos",
            "queensgambit": "Queen's Gambit",
            "redwedding": "Red Wedding",
            "reinforcements": "Reinforcements",
            "reloaded": "Reloaded",
            "revelations": "Revelations",
            "shaolinshowdown": "Shaolin Showdown",
            "shurikensandsixguns": "Shurikens and Six-Guns",
            "thronewar": "Throne War",
            "twofistedtales": "Two-Fisted Tales",
            "yearofthedragon": "Year of the Dragon",
            "yearofthegoat": "Year of the Goat",
        },
        "load_group": load_group_by_type({"Token": "playerNMisc"}, "playerNDeck"),
        "zone_groups": {"Deck": "playerNDeck", "Misc": "playerNMisc"},
        "deck_label": lambda stem: shadowfist_deck_label(stem),
        "piles": [
            pile("Deck", "Deck", "deck"),
            pile("Smoked", "Smoked", "discard"),
            pile("Hand", "Hand", "hand"),
            pile("Play", "Play", "inPlay", inPlay=True),
            pile("Sites", "Sites", "inPlay", inPlay=True),
            pile("Edges", "Edges", "inPlay", inPlay=True),
            pile("Burned", "Burned for Victory", "aside"),
            pile("Toasted", "Toasted", "aside"),
            pile("Misc", "Misc", "aside"),
        ],
        "player_props": {
            "power": {"label": "Power", "type": "integer", "default": 1, "min": 0},
        },
        "game_props": {},
        "phases": [
            ("establishing", "Establishing Shot"),
            ("generate", "Generate Power"),
            ("unturn", "Unturn"),
            ("discard", "Discard"),
            ("draw", "Draw"),
            ("main", "Main Shot"),
            ("end", "End of Turn"),
        ],
        "announcements": [
            "Tabletop plugin from the Lackey Shadowfist set. No rules engine — Sites, Edges, Smoked, Toasted, and Burned for Victory are shortcuts.",
            "D = draw. E = turn. K / R = unturn. P = Power +1. X = smoke. G = d20.",
        ],
        "regions": [
            ("playerN+1Hand", "fan", "0%", "0%", "58%", "9%"),
            ("playerN+1Sites", "row", "58%", "0%", "17%", "12%"),
            ("playerN+1Play", "free", "0%", "12%", "75%", "22%"),
            ("playerNPlay", "free", "0%", "40%", "50%", "22%"),
            ("playerNSites", "row", "50%", "40%", "25%", "16%"),
            ("playerNHand", "fan", "0%", "82%", "58%", "17%"),
            ("playerN+1Deck", "pile", "76%", "10%", "11%", "14%"),
            ("playerN+1Smoked", "pile", "88%", "10%", "11%", "14%"),
            ("playerNEdges", "pile", "76%", "25%", "11%", "12%"),
            ("playerNBurned", "pile", "88%", "25%", "11%", "12%"),
            ("playerNToasted", "pile", "76%", "42%", "11%", "12%"),
            ("playerNMisc", "pile", "88%", "42%", "11%", "12%"),
            ("playerNDeck", "pile", "76%", "58%", "11%", "16%"),
            ("playerNSmoked", "pile", "88%", "58%", "11%", "16%"),
        ],
        "spawn_groups": ["playerNDeck", "playerNSites", "playerNEdges", "playerNMisc"],
        "deck_columns": [("name", "Name"), ("type", "Type"), ("faction", "Faction"), ("cost", "Cost"), ("fighting", "Fight"), ("packName", "Set")],
        "extra_actions": {
            "rollD20": [
                ["VAR", "$ROLL", ["RANDOM_INT", 1, 20]],
                ["LOG", "{{$ALIAS_N}} rolled a {{$ROLL}}."],
            ],
        },
        "extra_hotkeys": [
            {"key": "G", "actionList": "rollD20", "label": "Roll d20"},
        ],
        "extra_menu": [
            {"label": "Roll d20", "actionList": "rollD20"},
        ],
        "stat_buttons": [
            ("increase_power", "Power +1", "decrease_power", "Power -1"),
        ],
    },
    {
        "id": "fe-cipher",
        "lackey": "FECipher0",
        "plugin_name": "Fire Emblem Cipher",
        "author": "Lackey / retrop",
        "github": "https://fecipher.jp",
        "cardback_url": "https://dl.dropboxusercontent.com/s/0x3rzwap53ohys5/cardback.jpg",
        "folder": "fe-cipher",
        "pascal": "FeCipher",
        "draw_group": "Deck",
        "type_keys": ("Color",),
        "image_keys": ("Imagefile", "ImageFile"),
        "fuzzy_image": True,
        "extras": [
            ("rarity", "Rarity"),
            ("cost", "Cost"),
            ("klass", "Class"),
            ("traits", "Type"),
            ("range", "Range"),
            ("attack", "Attack"),
            ("support", "Support"),
            ("text", "Skill#1"),
            ("text2", "Skill#2"),
            ("text3", "Skill#3"),
            ("text4", "Skill#4"),
        ],
        "pack_names": {
            "S01": "S01 War of Shadows",
            "S02": "S02 Awakening",
            "S03": "S03 Hoshido",
            "S04": "S04 Nohr",
            "S05": "S05 Path of Radiance",
            "S06": "S06 Tokyo Mirage",
            "S07": "S07 Binding Disturbance",
            "S08": "S08 Genealogy",
            "S09": "S09 Land of the Gods",
            "S10": "S10 Blazing Blade",
            "S11": "S11 Warriors of Bonds",
            "S12": "S12 Three Houses",
            "Token": "Tokens",
            "Dynamite": "Dynamite Orbs",
            "USO": "April Fools",
            "PBK": "Pack Battles Bonds",
            "PBM": "Pack Battles MC",
        },
        "load_group": lambda card: (
            "playerNMisc" if card.get("set") in {"Token", "Dynamite"} or card.get("type") in {"Token", "Special"}
            else "playerNDeck"
        ),
        "zone_groups": {"Deck": "playerNDeck", "MC": "playerNStarting"},
        "deck_label": lambda stem: cipher_deck_label(stem),
        "piles": [
            pile("Deck", "Deck", "deck"),
            pile("Retreat", "Retreat", "discard"),
            pile("Hand", "Hand", "hand"),
            pile("Starting", "Main Character", "inPlay", inPlay=True),
            pile("Play", "Field", "inPlay", inPlay=True),
            pile("Bonds", "Bonds", "inPlay", inPlay=True),
            pile("Support", "Support", "aside"),
            pile("Orbs", "Orbs", "aside"),
            pile("FaceUpOrbs", "Face-Up Orbs", "aside"),
            pile("Boundless", "Boundless", "aside"),
            pile("Misc", "Misc", "aside"),
        ],
        "player_props": {},
        "game_props": {},
        "phases": [
            ("start", "Start"),
            ("bond", "Bond"),
            ("deploy", "Deploy"),
            ("action", "Action"),
            ("end", "End"),
        ],
        "announcements": [
            "Tabletop plugin from the Lackey Fire Emblem Cipher set. No rules engine — MC, Bonds, Orbs, Support, Retreat, and Boundless are shortcuts.",
            "D = draw. U = support. O = add orb. T = take orb. E = tap. K / R = untap. X = retreat. G = d6.",
        ],
        "regions": [
            ("playerN+1Hand", "fan", "0%", "0%", "50%", "9%"),
            ("playerN+1Starting", "row", "50%", "0%", "12%", "12%"),
            ("playerN+1Bonds", "row", "62%", "0%", "13%", "12%"),
            ("playerN+1Play", "free", "0%", "12%", "75%", "22%"),
            ("playerNPlay", "free", "0%", "40%", "50%", "22%"),
            ("playerNStarting", "row", "50%", "40%", "12%", "16%"),
            ("playerNBonds", "row", "62%", "40%", "13%", "16%"),
            ("playerNHand", "fan", "0%", "82%", "58%", "17%"),
            ("playerN+1Deck", "pile", "76%", "10%", "11%", "14%"),
            ("playerN+1Retreat", "pile", "88%", "10%", "11%", "14%"),
            ("playerNOrbs", "pile", "76%", "25%", "11%", "12%"),
            ("playerNFaceUpOrbs", "pile", "88%", "25%", "11%", "12%"),
            ("playerNSupport", "pile", "76%", "42%", "11%", "12%"),
            ("playerNBoundless", "pile", "88%", "42%", "11%", "12%"),
            ("playerNDeck", "pile", "76%", "58%", "11%", "16%"),
            ("playerNRetreat", "pile", "88%", "58%", "11%", "16%"),
        ],
        "spawn_groups": ["playerNDeck", "playerNStarting", "playerNBonds", "playerNMisc"],
        "deck_columns": [("name", "Name"), ("type", "Color"), ("klass", "Class"), ("cost", "Cost"), ("attack", "ATK"), ("packName", "Set")],
        "extra_actions": {
            "drawSupport": [[
                "COND",
                ["GROUP_EMPTY", "{{$PLAYER_N}}Deck"],
                ["LOG", "{{$ALIAS_N}} tried to support from an empty deck."],
                ["TRUE"],
                [
                    ["MOVE_STACKS", "{{$PLAYER_N}}Deck", "{{$PLAYER_N}}Support", 1, "bottom"],
                    ["LOG", "{{$ALIAS_N}} revealed a support."],
                ],
            ]],
            "addOrb": [[
                "COND",
                ["GROUP_EMPTY", "{{$PLAYER_N}}Deck"],
                ["LOG", "{{$ALIAS_N}} tried to add an orb from an empty deck."],
                ["TRUE"],
                [
                    ["MOVE_STACKS", "{{$PLAYER_N}}Deck", "{{$PLAYER_N}}Orbs", 1, "bottom"],
                    ["LOG", "{{$ALIAS_N}} added an orb."],
                ],
            ]],
            "takeOrb": [[
                "COND",
                ["GROUP_EMPTY", "{{$PLAYER_N}}Orbs"],
                ["LOG", "{{$ALIAS_N}} has no orbs to take."],
                ["TRUE"],
                [
                    ["MOVE_STACKS", "{{$PLAYER_N}}Orbs", "{{$PLAYER_N}}Hand", 1, "bottom"],
                    ["LOG", "{{$ALIAS_N}} took an orb into hand."],
                ],
            ]],
            "rollD6": [
                ["VAR", "$ROLL", ["RANDOM_INT", 1, 6]],
                ["LOG", "{{$ALIAS_N}} rolled a {{$ROLL}}."],
            ],
        },
        "extra_hotkeys": [
            {"key": "U", "actionList": "drawSupport", "label": "Support"},
            {"key": "O", "actionList": "addOrb", "label": "Add orb"},
            {"key": "T", "actionList": "takeOrb", "label": "Take orb"},
            {"key": "G", "actionList": "rollD6", "label": "Roll d6"},
        ],
        "extra_menu": [
            {"label": "Support", "actionList": "drawSupport"},
            {"label": "Add orb", "actionList": "addOrb"},
            {"label": "Take orb", "actionList": "takeOrb"},
            {"label": "Roll d6", "actionList": "rollD6"},
        ],
        "extra_buttons": [
            ("drawSupport", "Support", "76%", "50%", "11%", "3.2%"),
            ("addOrb", "Orb +", "88%", "50%", "11%", "3.2%"),
            ("takeOrb", "Take Orb", "76%", "54%", "11%", "3.2%"),
            ("rollD6", "d6", "88%", "54%", "11%", "3.2%"),
        ],
    },
    {
        "id": "star-trek-tcg",
        "lackey": "StarTrekTCG",
        "plugin_name": "Star Trek TCG",
        "author": "Lackey / ericbsmith42",
        "github": "https://github.com/ericbsmith42/LackeyCCG-StarTrekTCG",
        "cardback_url": "https://raw.githubusercontent.com/ericbsmith42/LackeyCCG-StarTrekTCG/main/sets/setimages/cardback.jpg",
        "remote_backs": {
            "silverback": "https://raw.githubusercontent.com/ericbsmith42/LackeyCCG-StarTrekTCG/main/sets/setimages/silverback.jpg",
        },
        "image_prefix": "https://raw.githubusercontent.com/ericbsmith42/LackeyCCG-StarTrekTCG/main/sets/setimages/",
        "folder": "star-trek-tcg",
        "pascal": "StarTrekTcg",
        "draw_group": "Deck",
        "type_keys": ("Type",),
        "image_keys": ("ImageFile", "Imagefile"),
        "extras": [
            ("subtype", "Sub-Type"),
            ("rarity", "Rarity"),
        ],
        "pack_names": {
            "Base": "Base Set",
            "Starfleet Maneuvers": "Starfleet Maneuvers",
            "Promo": "Promo",
        },
        "card_back_for_type": {
            "Core Crew": "silverback",
            "Core Info Card": "silverback",
            "Core Episode Discovery": "silverback",
            "Core Episode Mission": "silverback",
            "Core Episode Plot": "silverback",
        },
        "load_group": lambda card: (
            "playerNStarting" if card.get("type", "").startswith("Core")
            else "playerNEpisode" if card.get("type", "").startswith("Episode")
            else "playerNChallenges" if card.get("type") == "Challenge"
            else "playerNDeck"
        ),
        "zone_groups": {"Deck": "playerNDeck", "Starting Cards": "playerNStarting"},
        "piles": [
            pile("Deck", "Deck", "deck"),
            pile("Discard", "Discard", "discard"),
            pile("Hand", "Hand", "hand"),
            pile("Starting", "Starting / Core", "inPlay", inPlay=True),
            pile("Play", "Play", "inPlay", inPlay=True),
            pile("Episode", "Episode", "inPlay", inPlay=True),
            pile("Challenges", "Challenges", "inPlay", inPlay=True),
            pile("Removed", "Removed", "aside"),
        ],
        "player_props": {
            "xc": {"label": "XC", "type": "integer", "default": 0, "min": 0, "hotkey": "P"},
        },
        "game_props": {},
        "phases": [
            ("discard", "Discard"),
            ("draw", "Draw"),
            ("crew", "Crew"),
            ("episode", "Episode"),
            ("resolution", "Resolution"),
            ("change", "Change Player"),
        ],
        "announcements": [
            "Tabletop plugin from the Lackey Star Trek TCG set (Decipher 2000 — not CCG 1E). No rules engine — Core, Episode, Challenges, and XC are shortcuts.",
            "D = draw. E = exhaust. K / R = ready. P = XC +1. X = discard.",
        ],
        "regions": [
            ("playerN+1Hand", "fan", "0%", "0%", "50%", "9%"),
            ("playerN+1Starting", "row", "50%", "0%", "12%", "12%"),
            ("playerN+1Episode", "row", "62%", "0%", "13%", "12%"),
            ("playerN+1Play", "free", "0%", "12%", "75%", "14%"),
            ("playerN+1Challenges", "row", "0%", "26%", "75%", "8%"),
            ("playerNPlay", "free", "0%", "36%", "50%", "16%"),
            ("playerNStarting", "row", "50%", "36%", "12%", "16%"),
            ("playerNEpisode", "row", "62%", "36%", "13%", "16%"),
            ("playerNChallenges", "row", "0%", "54%", "62%", "10%"),
            ("playerNRemoved", "pile", "62%", "54%", "13%", "10%"),
            ("playerNHand", "fan", "0%", "82%", "58%", "17%"),
            ("playerN+1Deck", "pile", "76%", "10%", "11%", "14%"),
            ("playerN+1Discard", "pile", "88%", "10%", "11%", "14%"),
            ("sharedSetAside", "pile", "88%", "25%", "11%", "12%"),
            ("playerNDeck", "pile", "76%", "58%", "11%", "16%"),
            ("playerNDiscard", "pile", "88%", "58%", "11%", "16%"),
        ],
        "spawn_groups": ["playerNDeck", "playerNStarting", "playerNEpisode", "playerNChallenges"],
        "deck_columns": [("name", "Name"), ("type", "Type"), ("subtype", "Subtype"), ("rarity", "Rarity"), ("packName", "Set")],
        "stat_buttons": [
            ("increase_xc", "XC +1", "decrease_xc", "XC -1"),
        ],
    },
]


def cipher_deck_label(stem: str) -> str:
    parts = stem.replace("_", " ").split()
    if parts and parts[0].isdigit():
        parts = parts[1:]
    return " ".join(parts) or stem


SHADOWFIST_DECK_SETS = {
    "10KB": "10,000 Bullets",
    "BFS": "Back for Seconds",
    "CIK": "Combat in Kowloon",
    "YotD": "Year of the Dragon",
    "YotG": "Year of the Goat",
}

SHADOWFIST_FACTIONS = {
    "ARC": "Architects",
    "ASC": "Ascended",
    "DRA": "Dragons",
    "HAN": "Guiding Hand",
    "JAM": "Jammers",
    "LOT": "Lotus",
    "MON": "Monarchs",
    "PUR": "Purists",
}


def shadowfist_deck_label(stem: str) -> str:
    name = stem.lstrip("_")
    if name.startswith("precon-"):
        parts = name.split("-")
        if len(parts) >= 3:
            set_name = SHADOWFIST_DECK_SETS.get(parts[1], parts[1])
            faction = SHADOWFIST_FACTIONS.get(parts[2], parts[2])
            return f"{set_name} — {faction}"
    return name.replace("_", " ").strip() or stem


def load_all_urls(lackey: Path) -> dict[str, str]:
    urls: dict[str, str] = {}
    for path in sorted(lackey.glob("CardImageURLs*.txt")):
        urls.update(load_image_urls(path))
    return urls


def header_index(header: list[str]) -> dict[str, int]:
    return {name.strip(): i for i, name in enumerate(header)}


def col(header_map: dict[str, int], cols: list[str], *names: str) -> str:
    for name in names:
        if name in header_map:
            return sanitize(cols[header_map[name]])
        folded = {key.casefold(): key for key in header_map}
        if name.casefold() in folded:
            return sanitize(cols[header_map[folded[name.casefold()]]])
    return ""


def discover_carddata(lackey: Path) -> list[Path]:
    single = lackey / "sets" / "carddata.txt"
    if single.exists():
        return [single]
    return sorted(path for path in (lackey / "sets").glob("*.txt") if path.is_file())


def fuzzy_lookup_image(urls: dict[str, str], set_name: str, image_file: str) -> str:
    stem = Path(image_file).stem
    for alt in (f"{stem}v2", f"{stem}v3", f"{stem.replace('v2', 'v3')}", f"{stem}.jpg"):
        found = lookup_image(urls, set_name, alt)
        if found:
            return found
    return ""


def load_cards(game: dict, carddata_files: list[Path], urls: dict[str, str]) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    seen: set[str] = set()
    back_for_type = game.get("card_back_for_type") or {}
    for carddata in carddata_files:
        lines = carddata.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        if not lines:
            continue
        header = [h.strip() for h in lines[0].split("\t")]
        header_map = header_index(header)
        for line in lines[1:]:
            if not line.strip():
                continue
            cols = line.split("\t")
            while len(cols) < len(header):
                cols.append("")
            name = col(header_map, cols, "Name")
            set_name = col(header_map, cols, "Set")
            image_file = col(header_map, cols, *game["image_keys"])
            if not name:
                continue
            image_file = front_image(image_file)
            card_type = col(header_map, cols, *game["type_keys"]) or "Card"
            if card_type.lower() == "characters":
                card_type = "Character"
            if card_type in {"-", ""}:
                card_type = "Special"
            if card_type == "Core Eipisode Mission":
                card_type = "Core Episode Mission"
            database_id = f"{set_name}_{image_file or slug(name)}"
            if database_id in seen:
                continue
            seen.add(database_id)
            image_url = lookup_image(urls, set_name, image_file) if image_file else ""
            if not image_url and image_file and "," in image_file:
                image_url = lookup_image(urls, set_name, image_file.split(",", 1)[0].strip())
            if not image_url and image_file and game.get("fuzzy_image"):
                image_url = fuzzy_lookup_image(urls, set_name, image_file)
            if not image_url and image_file and game.get("image_prefix"):
                stem = Path(image_file).stem if Path(image_file).suffix else image_file
                image_url = game["image_prefix"].rstrip("/") + "/" + stem + ".jpg"
            if not image_url:
                errors.append(f"{game['id']}: missing image URL for {database_id} ({name})")
                continue
            card = {
                "databaseId": database_id,
                "name": name,
                "imageUrl": image_url,
                "cardBack": back_for_type.get(card_type, "default"),
                "type": card_type,
                "packName": pretty_set(set_name, game.get("pack_names") or {}),
                "set": set_name,
            }
            for tsv_name, source in game.get("extras") or []:
                card[tsv_name] = col(header_map, cols, source)
            if "text" in card and any(card.get(key) for key in ("text2", "text3", "text4")):
                parts = [card.get(key) for key in ("text", "text2", "text3", "text4")]
                card["text"] = " / ".join(part for part in parts if part and part != "-")
                card.pop("text2", None)
                card.pop("text3", None)
                card.pop("text4", None)
            card["loadGroupId"] = game["load_group"](card)
            cards.append(card)
    return cards, errors


def parse_dek(path: Path) -> dict[str, Counter]:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        root = ET.fromstring(f"<root>{text}</root>")
    zones: dict[str, Counter] = {}
    for superzone in root.findall(".//superzone"):
        zone = (superzone.attrib.get("name") or "").strip()
        counts = zones.setdefault(zone, Counter())
        for card in superzone.findall("card"):
            name_el = card.find("name")
            set_el = card.find("set")
            if name_el is None or set_el is None:
                continue
            image_id = (name_el.attrib.get("id") or "").strip()
            set_name = (set_el.text or "").strip()
            if image_id and set_name:
                counts[f"{set_name}_{image_id}"] += 1
    return zones


def convert_decks(game: dict, cards: list[dict[str, str]], lackey: Path) -> tuple[dict, dict, list[str]]:
    known = {card["databaseId"] for card in cards}
    errors: list[str] = []
    prebuilt: OrderedDict[str, dict] = OrderedDict()
    items: list[dict] = []
    zone_to_group = game.get("zone_groups") or {}
    decks_dir = lackey / "decks"
    if not decks_dir.exists():
        return {"preBuiltDecks": {}}, {"deckMenu": {"subMenus": []}}, errors
    label_fn = game.get("deck_label")
    for dek in sorted(decks_dir.glob("*.dek")):
        label = label_fn(dek.stem) if callable(label_fn) else dek.stem.replace("_", " ").replace("  ", " ").strip()
        deck_id = slug(label)
        entries = []
        for zone, counts in parse_dek(dek).items():
            group = zone_to_group.get(zone, f"playerN{game['draw_group']}")
            for raw_id, quantity in counts.items():
                set_name, _, image_id = raw_id.partition("_")
                database_id = match_database_id(known, set_name, image_id) if image_id else ""
                if not database_id:
                    errors.append(f"{game['id']} {dek.name}: unknown card {raw_id}")
                    continue
                entries.append({"databaseId": database_id, "quantity": quantity, "loadGroupId": group})
        if not entries:
            continue
        prebuilt[deck_id] = {"label": label, "cards": entries}
        items.append({"deckListId": deck_id, "label": label})
    menus = [{"label": "Lackey Decks", "deckLists": items}] if items else []
    return {"preBuiltDecks": dict(prebuilt)}, {"deckMenu": {"subMenus": menus}}, errors


def player_groups(player: str, piles: list[dict], draw_group: str) -> dict[str, dict]:
    groups = {}
    discard_suffix = next((p["suffix"] for p in piles if p["groupType"] == "discard"), "Discard")
    for spec in piles:
        suffix = spec["suffix"]
        group_id = f"{player}{suffix}"
        enter = {
            "controller": player,
            "deckGroupId": f"{player}{draw_group}",
            "discardGroupId": f"{player}{discard_suffix}",
        }
        if spec.get("inPlay"):
            enter["inPlay"] = True
        groups[group_id] = {
            "groupType": spec["groupType"],
            "label": f"Player {player[-1]} {spec['label']}",
            "tableLabel": spec["label"],
            "onCardEnter": enter,
        }
        if spec.get("inPlay"):
            groups[group_id]["canHaveAttachments"] = True
    return groups


def move_groups(piles: list[dict]) -> list[str]:
    ids = [f"playerN{spec['suffix']}" for spec in piles]
    ids.append("playerN+1Play")
    ids.append("sharedSetAside")
    return ids


def tsv_columns(game: dict, cards: list[dict[str, str]]) -> list[str]:
    extras = [name for name, _ in game.get("extras") or [] if name not in {"text2", "text3", "text4"}]
    if any(card.get("text") for card in cards) and "text" not in extras:
        extras.append("text")
    columns = list(CORE_COLUMNS)
    for name in extras:
        if name not in columns:
            columns.append(name)
    return columns


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


def write_plugin_jsons(game: dict, cards: list[dict[str, str]], decks: dict, menu: dict, backs: dict[str, str]) -> None:
    out = ROOT / game["id"]
    jsons = out / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    types = sorted({card["type"] for card in cards})
    folder = game["folder"]
    pascal_name = game["pascal"]
    draw_group = game["draw_group"]
    piles = game["piles"]
    dump_json(jsons / "main.json", {
        "pluginName": game["plugin_name"],
        "author": game.get("author") or "Lackey / wishmstr",
        "tutorialUrl": game["github"],
        "announcements": game["announcements"],
        "loadPreBuiltOnNewGame": False,
    })
    stamp_lobby_art(jsons, folder)
    clear_image_url_prefix(jsons)
    dump_json(jsons / "cardBacks.json", {"cardBacks": {
        key: {"width": 0.72, "height": 1.0, "imageUrl": rel}
        for key, rel in backs.items()
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
        extra = {}
        if rtype == "fan":
            extra["disableDroppableAttachments"] = True
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
    phases = {key: {"label": label, "height": f"{int(100 / max(len(game['phases']), 1))}%"} for key, label in game["phases"]}
    dump_json(jsons / "phases.json", {"phases": phases, "phaseOrder": [key for key, _ in game["phases"]]})
    dump_json(jsons / "steps.json", {"steps": {
        f"{key}Step": {"phaseId": key, "label": label} for key, label in game["phases"]
    }, "stepOrder": [f"{key}Step" for key, _ in game["phases"]]})
    player_props = {}
    for key, spec in (game.get("player_props") or {}).items():
        player_props[key] = {name: value for name, value in spec.items() if name != "hotkey"}
    dump_json(jsons / "playerProperties.json", {"playerProperties": player_props})
    dump_json(jsons / "gameProperties.json", {"gameProperties": game.get("game_props") or {}})
    topbar_player = [{"label": spec["label"], "imageUrl": "", "playerProperty": key} for key, spec in (game.get("player_props") or {}).items()]
    topbar_shared = list(game.get("topbar_shared") or [{"label": "Round", "imageUrl": "", "gameProperty": "roundNumber"}])
    dump_json(jsons / "topBarCounters.json", {"topBarCounters": {"shared": topbar_shared, "player": topbar_player}})
    dump_json(jsons / "tokens.json", {"tokens": {
        "green": {
            "label": "+1",
            "left": "72%",
            "top": "4%",
            "width": "4vh",
            "height": "4vh",
            "imageUrl": toybox_url(f"{folder}/_plugin/{pascal_name}-TokenGreen.png"),
            "canBeNegative": True,
        },
        "red": {
            "label": "-1",
            "left": "50%",
            "top": "4%",
            "width": "4vh",
            "height": "4vh",
            "imageUrl": toybox_url(f"{folder}/_plugin/{pascal_name}-TokenRed.png"),
            "canBeNegative": True,
        },
    }})
    dump_json(jsons / "functions.json", {"functions": standard_functions()})
    actions = standard_actions(draw_group=draw_group)
    actions["flipCoin"] = [
        ["VAR", "$FLIP", ["RANDOM_INT", 1, 2]],
        [
            "COND",
            ["EQUAL", "$FLIP", 1],
            ["LOG", "{{$ALIAS_N}} flipped heads."],
            ["TRUE"],
            ["LOG", "{{$ALIAS_N}} flipped tails."],
        ],
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
    for key, spec in (game.get("player_props") or {}).items():
        game_hotkeys.append({
            "key": spec.get("hotkey") or spec["label"][:1].upper(),
            "actionList": f"increase_{key}",
            "label": f"{spec['label']} +1",
        })
    game_hotkeys.extend(game.get("extra_hotkeys") or [])
    dump_json(jsons / "hotkeys.json", {"hotkeys": {
        "game": game_hotkeys,
        "card": [
            {"key": "K", "actionList": "readyCard", "label": "Ready"},
            {"key": "E", "actionList": "spendCard", "label": "Exert"},
            {"key": "I", "actionList": "invertCard", "label": "Rotate 180"},
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
    moves = move_groups(piles)
    dump_json(jsons / "cardMenu.json", {"cardMenu": {"moveToGroupIds": moves, "options": [
        {"label": "Ready", "actionList": "readyCard"},
        {"label": "Exert", "actionList": "spendCard"},
        {"label": "Rotate 180", "actionList": "invertCard"},
        {"label": "Flip", "actionList": "flipCard"},
        {"label": "Discard", "actionList": "discardCard"},
        {"label": "Detach", "actionList": "detachCard"},
        {"label": "Shuffle into deck", "actionList": "shuffleIntoDeck"},
    ]}})
    dump_json(jsons / "groupMenu.json", {"groupMenu": {"moveToGroupIds": moves, "options": []}})
    extra_text = [name for name, _ in game.get("extras") or [] if name in {"text", "effect", "specialSkill"}]
    dump_json(jsons / "browse.json", {"browse": {
        "filterPropertySideA": "type",
        "filterValuesSideA": types,
        "textPropertiesSideA": ["name", "packName", *extra_text],
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
    face = {}
    for name, source in game.get("extras") or []:
        if name in {"text2", "text3", "text4"}:
            continue
        face[name] = {"label": source.replace("_", " "), "type": "string", "default": ""}
    if any(card.get("text") for card in cards) and "text" not in face:
        face["text"] = {"label": "Text", "type": "string", "default": ""}
    face.update({
        "packName": {"label": "Set", "type": "string", "default": ""},
        "set": {"label": "Lackey Set", "type": "string", "default": ""},
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


def write_plugin_art(game: dict, lackey: Path) -> dict[str, str]:
    plugin = IMAGES / game["folder"] / "_plugin"
    plugin.mkdir(parents=True, exist_ok=True)
    general = lackey / "sets" / "setimages" / "general"
    requested = game.get("card_backs") or {"default": "cardback.jpg"}
    backs: dict[str, str] = {}
    fallback = ""
    for key, filename in requested.items():
        src = general / filename
        if not src.exists():
            matches = list(general.glob("cardback.*")) + list(general.glob("cardback.*"))
            src = matches[0] if matches else None
        if src and src.exists():
            rel = copy_plugin_art(src, IMAGES, game["folder"], game["pascal"], f"cardback-{key}")
            backs[key] = rel
            if not fallback:
                fallback = str(src)
    if "default" not in backs:
        branch = game.get("github_branch") or "main"
        remote = game.get("cardback_url") or (
            f"{game['github'].replace('https://github.com/', 'https://raw.githubusercontent.com/')}"
            f"/{branch}/sets/setimages/general/cardback.jpg"
        )
        dest = plugin / f"{game['pascal']}-CardbackDefault.jpg"
        try:
            req = urllib.request.Request(
                remote,
                headers={"User-Agent": "HundredAcreClub/1.0 (private tabletop image collect; +https://hundredacre.club)"},
            )
            dest.write_bytes(urllib.request.urlopen(req, timeout=45).read())
            fallback = str(dest)
            backs["default"] = copy_plugin_art(dest, IMAGES, game["folder"], game["pascal"], "cardback-default")
        except OSError:
            backs["default"] = remote
    for key, remote in (game.get("remote_backs") or {}).items():
        if key in backs:
            continue
        dest = plugin / f"{game['pascal']}-Cardback{key.title()}.jpg"
        try:
            req = urllib.request.Request(
                remote,
                headers={"User-Agent": "HundredAcreClub/1.0 (private tabletop image collect; +https://hundredacre.club)"},
            )
            dest.write_bytes(urllib.request.urlopen(req, timeout=45).read())
            backs[key] = copy_plugin_art(dest, IMAGES, game["folder"], game["pascal"], f"cardback-{key}")
        except OSError:
            backs[key] = remote
    if fallback:
        shutil.copy2(fallback, IMAGES / lobby_art_rel(game["folder"], "logo"))
        shutil.copy2(fallback, IMAGES / lobby_art_rel(game["folder"], "banner"))
    write_color_png(plugin / f"{game['pascal']}-TokenGreen.png", (48, 160, 72))
    write_color_png(plugin / f"{game['pascal']}-TokenRed.png", (196, 48, 48))
    return backs


def convert_game(game: dict) -> tuple[int, list[str]]:
    lackey = LACKEY_ROOT / game["lackey"]
    carddata_files = discover_carddata(lackey)
    if not carddata_files:
        return 1, [f"{game['id']}: Lackey plugin not found at {lackey}"]
    urls = load_all_urls(lackey)
    cards, errors = load_cards(game, carddata_files, urls)
    if not cards:
        return 1, errors or [f"{game['id']}: no cards loaded"]
    out = ROOT / game["id"]
    write_tsv(cards, tsv_columns(game, cards), out / "tsvs" / "cards.tsv")
    decks, menu, deck_errors = convert_decks(game, cards, lackey)
    errors.extend(deck_errors)
    backs = write_plugin_art(game, lackey)
    write_plugin_jsons(game, cards, decks, menu, backs)
    (out / "SOURCE.txt").write_text(
        "\n".join([
            f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from LackeyCCG {game['lackey']}.",
            f"Source: {lackey}",
            f"Art: {game['github']} raw setimages.",
            f"Author credit: {game.get('author') or 'Lackey / wishmstr'}",
            "",
            "Tabletop plugin only — Lackey has no rules engine to port.",
            f"TSV rows: {len(cards)}  skipped (no image URL or duplicate): {sum(1 for e in errors if 'missing image' in e or 'duplicate' in e)}",
            f"Prebuilts: {len(decks['preBuiltDecks'])} Lackey decks.",
            "",
        ]),
        encoding="utf-8",
    )
    print(f"Wrote {out.name}")
    print(f"  pluginName: {game['plugin_name']}")
    print(f"  tsv rows: {len(cards)}")
    print(f"  prebuilt decks: {len(decks['preBuiltDecks'])}")
    print(f"  types: {', '.join(sorted({c['type'] for c in cards}))}")
    return 0 if not any("missing image" in e or "duplicate" in e or "unknown card" in e for e in errors) else 1, errors


def main() -> int:
    wanted = {arg for arg in sys.argv[1:] if not arg.startswith("-")}
    games = [game for game in GAMES if not wanted or game["id"] in wanted or game["lackey"] in wanted]
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
    if all_errors:
        print(f"{len(all_errors)} issue(s):")
        for err in all_errors[:60]:
            print(f"  - {err}")
        if len(all_errors) > 60:
            print(f"  … {len(all_errors) - 60} more")
    print("Next: collect each game, e.g.")
    print("  python3 plugins/scripts/collect_hosted_images.py rifts-ccg")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
