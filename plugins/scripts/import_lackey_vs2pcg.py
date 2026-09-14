#!/usr/bin/env python3
"""Build a DragnCards VS System 2PCG plugin from the LackeyCCG plugin.

  python3 plugins/scripts/import_lackey_vs2pcg.py
  python3 plugins/scripts/collect_hosted_images.py --retarget vs-system-2pcg
"""

from __future__ import annotations

import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from image_names import TOYBOX_PREFIX, clear_image_url_prefix, lobby_art_rel, stamp_lobby_art, toybox_url  # noqa: E402
from lackey_tabletop import (  # noqa: E402
    copy_card_art,
    copy_plugin_art,
    dump_json,
    find_local_image,
    group_types,
    index_setimages,
    region,
    sanitize,
    slug,
    standard_actions,
    standard_functions,
    write_color_png,
    write_tsv,
)

LACKEY = Path("/Users/krystoferrobin/Downloads/lackeyplugins/VS2PCG")
OUT = ROOT / "vs-system-2pcg"
GAME_FOLDER = "vs-system-2pcg"
GAME_PASCAL = "VsSystem2pcg"
IMAGES = ROOT / "images"

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "cost",
    "health",
    "team",
    "powerSymbol",
    "rangedFlight",
    "keyword",
    "text",
    "packName",
    "set",
    "loadGroupId",
]

MOVE_GROUPS = [
    "playerNHand",
    "playerNDeck",
    "playerNKO",
    "playerNPlay",
    "playerNMain",
    "playerNLocations",
    "playerNRemoved",
    "playerNMisc",
    "playerN+1Play",
    "sharedSetAside",
]


def pack_name(set_name: str) -> str:
    aliases = {
        "the marvel battles": "The Marvel Battles",
        "legacy": "Legacy",
        "the defenders": "The Defenders",
        "aliens": "Aliens",
        "a-force": "A-Force",
    }
    return aliases.get(set_name.lower(), set_name.title() if set_name else "Unknown")


def load_group(card_type: str) -> str:
    if card_type == "Main Character":
        return "playerNMain"
    if card_type == "Location":
        return "playerNDeck"
    if "Token" in card_type or card_type == "Facehugger Pile":
        return "playerNMisc"
    return "playerNDeck"


def load_cards(carddata: Path, index: dict[str, Path]) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    seen: set[str] = set()
    used: dict[str, int] = {}
    lines = carddata.read_text(encoding="utf-8", errors="replace").splitlines()
    header = [h.strip() for h in lines[0].split("\t")]
    col = {name: i for i, name in enumerate(header)}
    for line_no, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        cols = line.split("\t")
        while len(cols) < len(header):
            cols.append("")
        name = sanitize(cols[col.get("Name", 0)])
        set_name = sanitize(cols[col.get("Set", 1)])
        image_file = sanitize(cols[col.get("ImageFile", 2)])
        if not name or name == '"' or not image_file:
            continue
        card_type = sanitize(cols[col.get("Card Type", 3)]) or "Card"
        database_id = f"{set_name}_{image_file}"
        if database_id in seen:
            errors.append(f"Duplicate {database_id} at line {line_no}")
            continue
        seen.add(database_id)
        src = find_local_image(index, set_name, image_file)
        if not src:
            errors.append(f"Missing image for {database_id}")
            image_url = ""
        else:
            image_url = copy_card_art(src, IMAGES, GAME_FOLDER, GAME_PASCAL, pack_name(set_name), name, used)
        cards.append(
            {
                "databaseId": database_id,
                "name": name,
                "imageUrl": image_url,
                "cardBack": "default",
                "type": card_type,
                "cost": sanitize(cols[col.get("Cost", 4)]),
                "health": sanitize(cols[col.get("Health", 5)]),
                "team": sanitize(cols[col.get("Team", 6)]),
                "powerSymbol": sanitize(cols[col.get("Power Symbol", 7)]),
                "rangedFlight": sanitize(cols[col.get("Ranged/Flight", 8)]),
                "keyword": sanitize(cols[col.get("Key Word", 9)]),
                "text": sanitize(cols[col.get("Text", 10)]),
                "packName": pack_name(set_name),
                "set": set_name,
                "loadGroupId": load_group(card_type),
            }
        )
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


def convert_decks(cards: list[dict[str, str]]) -> tuple[dict, dict, list[str]]:
    known = {card["databaseId"] for card in cards}
    errors: list[str] = []
    prebuilt: OrderedDict[str, dict] = OrderedDict()
    menu: list[dict] = []
    zone_to_group = {
        "Player Deck": "playerNDeck",
        "Main Deck": "playerNMain",
        "Misc": "playerNMisc",
    }
    for dek in sorted((LACKEY / "decks").glob("*.dek")):
        label = dek.stem.replace("_", " ").replace("ƒ", "").replace("#", "")
        deck_id = slug(label)
        entries = []
        for zone, counts in parse_dek(dek).items():
            group = zone_to_group.get(zone, "playerNDeck")
            for database_id, quantity in counts.items():
                if database_id not in known:
                    errors.append(f"{dek.name}: unknown card {database_id}")
                    continue
                entries.append({"databaseId": database_id, "quantity": quantity, "loadGroupId": group})
        prebuilt[deck_id] = {"label": label, "cards": entries}
        menu.append({"deckListId": deck_id, "label": label})
    return {"preBuiltDecks": dict(prebuilt)}, {"deckMenu": {"subMenus": [{"label": "Tournament Decks", "deckLists": menu}]}}, errors


def player_piles(player: str) -> dict[str, dict]:
    return {
        f"{player}Deck": {
            "groupType": "deck",
            "label": f"Player {player[-1]} Main Deck",
            "tableLabel": "Main Deck",
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}KO"},
        },
        f"{player}KO": {
            "groupType": "discard",
            "label": f"Player {player[-1]} KO",
            "tableLabel": "KO",
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}KO"},
        },
        f"{player}Hand": {
            "groupType": "hand",
            "label": f"Player {player[-1]} Hand",
            "tableLabel": "Hand",
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}KO"},
        },
        f"{player}Play": {
            "groupType": "inPlay",
            "label": f"Player {player[-1]} Characters",
            "tableLabel": "Characters",
            "canHaveAttachments": True,
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}KO", "inPlay": True},
        },
        f"{player}Main": {
            "groupType": "inPlay",
            "label": f"Player {player[-1]} Main",
            "tableLabel": "Main",
            "canHaveAttachments": True,
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}KO", "inPlay": True},
        },
        f"{player}Locations": {
            "groupType": "inPlay",
            "label": f"Player {player[-1]} Locations",
            "tableLabel": "Locations",
            "canHaveAttachments": True,
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}KO", "inPlay": True},
        },
        f"{player}Removed": {
            "groupType": "aside",
            "label": f"Player {player[-1]} Removed",
            "tableLabel": "Removed",
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}KO"},
        },
        f"{player}Misc": {
            "groupType": "aside",
            "label": f"Player {player[-1]} Misc",
            "tableLabel": "Misc",
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}KO"},
        },
    }


def write_plugin_jsons(cards: list[dict[str, str]], decks: dict, menu: dict, back_rel: str) -> None:
    jsons = OUT / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    types = sorted({card["type"] for card in cards})
    dump_json(jsons / "main.json", {
        "pluginName": "VS System 2PCG",
        "author": "Lackey / VS 2PCG",
        "announcements": [
            "Tabletop plugin from the Lackey VS System 2PCG set. No rules engine — Draw, Exert/Ready, KO, and counters are shortcuts.",
            "D = draw. R = ready all. T = exert. K = ready one. X = KO. 1–4 = wound / XP / +1 / −1 counters.",
        ],
        "backgroundUrl": toybox_url(f"{GAME_FOLDER}/_plugin/{GAME_PASCAL}-Background.jpg"),
        "loadPreBuiltOnNewGame": False,
    })
    stamp_lobby_art(jsons, GAME_FOLDER)
    clear_image_url_prefix(jsons)
    dump_json(jsons / "cardBacks.json", {"cardBacks": {"default": {"width": 0.72, "height": 1.0, "imageUrl": back_rel}}})
    dump_json(jsons / "cardTypes.json", {"cardTypes": {name: {"width": 0.72, "height": 1.0, "tokens": ["wound", "xp", "plus", "minus"]} for name in types}})
    groups = {"sharedSetAside": {"groupType": "aside", "label": "Set Aside", "tableLabel": "Set Aside", "onCardEnter": {"controller": "shared"}}}
    groups.update(player_piles("player1"))
    groups.update(player_piles("player2"))
    dump_json(jsons / "groups.json", {"groups": groups})
    dump_json(jsons / "layouts.json", {"layouts": {"default": {
        "cardSize": 10,
        "rowSpacing": 2,
        "chat": {"left": "76%", "top": "78%", "width": "23%", "height": "21%"},
        "regions": {
            "playerN+1Hand": region("playerN+1Hand", "fan", "0%", "0%", "62%", "9%", disableDroppableAttachments=True),
            "playerN+1Main": region("playerN+1Main", "row", "62%", "0%", "13%", "9%"),
            "playerN+1Play": region("playerN+1Play", "free", "0%", "9%", "75%", "22%"),
            "playerN+1Locations": region("playerN+1Locations", "row", "0%", "31%", "75%", "8%"),
            "playerNLocations": region("playerNLocations", "row", "0%", "39%", "75%", "8%"),
            "playerNPlay": region("playerNPlay", "free", "0%", "47%", "62%", "24%"),
            "playerNMain": region("playerNMain", "row", "62%", "47%", "13%", "12%"),
            "playerNHand": region("playerNHand", "fan", "0%", "82%", "58%", "17%", disableDroppableAttachments=True),
            "playerN+1Deck": region("playerN+1Deck", "pile", "76%", "9%", "11%", "14%"),
            "playerN+1KO": region("playerN+1KO", "pile", "88%", "9%", "11%", "14%"),
            "sharedSetAside": region("sharedSetAside", "pile", "76%", "24%", "11%", "12%"),
            "playerNRemoved": region("playerNRemoved", "pile", "88%", "24%", "11%", "12%"),
            "playerNDeck": region("playerNDeck", "pile", "76%", "58%", "11%", "16%"),
            "playerNKO": region("playerNKO", "pile", "88%", "58%", "11%", "16%"),
        },
        "tableButtons": {
            "drawDeck": {"actionList": "drawDeck", "label": "Draw", "left": "76%", "top": "46%", "width": "11%", "height": "3.2%"},
            "readyAll": {"actionList": "readyAll", "label": "Ready All", "left": "88%", "top": "46%", "width": "11%", "height": "3.2%"},
            "increaseRecruit": {"actionList": "increaseRecruit", "label": "Recruit +1", "left": "76%", "top": "50%", "width": "11%", "height": "3.2%"},
            "increaseResource": {"actionList": "increaseResource", "label": "Resource +1", "left": "88%", "top": "50%", "width": "11%", "height": "3.2%"},
        },
    }}})
    dump_json(jsons / "groupTypes.json", {"groupTypes": group_types()})
    dump_json(jsons / "playerCountMenu.json", {"playerCountMenu": [{"label": "2", "numPlayers": 2, "layoutId": "default"}]})
    dump_json(jsons / "phases.json", {"phases": {
        "build": {"label": "Build", "height": "33%"},
        "main": {"label": "Main", "height": "34%"},
        "combat": {"label": "Combat", "height": "33%"},
    }, "phaseOrder": ["build", "main", "combat"]})
    dump_json(jsons / "steps.json", {"steps": {
        "buildStep": {"phaseId": "build", "label": "Build"},
        "mainStep": {"phaseId": "main", "label": "Main"},
        "combatStep": {"phaseId": "combat", "label": "Combat"},
    }, "stepOrder": ["buildStep", "mainStep", "combatStep"]})
    dump_json(jsons / "playerProperties.json", {"playerProperties": {
        "resourceLocations": {"label": "Resource Locations", "type": "integer", "default": 0, "min": 0},
        "recruit": {"label": "Recruit", "type": "integer", "default": 0, "min": 0},
    }})
    dump_json(jsons / "gameProperties.json", {"gameProperties": {}})
    dump_json(jsons / "topBarCounters.json", {"topBarCounters": {
        "shared": [{"label": "Round", "imageUrl": "", "gameProperty": "roundNumber"}],
        "player": [
            {"label": "Resources", "imageUrl": "", "playerProperty": "resourceLocations"},
            {"label": "Recruit", "imageUrl": "", "playerProperty": "recruit"},
        ],
    }})
    dump_json(jsons / "tokens.json", {"tokens": {
        "wound": {"label": "Wound", "left": "72%", "top": "4%", "width": "4vh", "height": "4vh", "imageUrl": toybox_url(f"{GAME_FOLDER}/_plugin/{GAME_PASCAL}-TokenWound.png"), "canBeNegative": True},
        "xp": {"label": "XP", "left": "50%", "top": "4%", "width": "4vh", "height": "4vh", "imageUrl": toybox_url(f"{GAME_FOLDER}/_plugin/{GAME_PASCAL}-TokenXp.png"), "canBeNegative": True},
        "plus": {"label": "+1/+1", "left": "28%", "top": "4%", "width": "4vh", "height": "4vh", "imageUrl": toybox_url(f"{GAME_FOLDER}/_plugin/{GAME_PASCAL}-TokenPlus.png"), "canBeNegative": True},
        "minus": {"label": "-1/-1", "left": "6%", "top": "4%", "width": "4vh", "height": "4vh", "imageUrl": toybox_url(f"{GAME_FOLDER}/_plugin/{GAME_PASCAL}-TokenMinus.png"), "canBeNegative": True},
    }})
    dump_json(jsons / "functions.json", {"functions": standard_functions()})
    actions = standard_actions()
    actions.update({
        "increaseRecruit": [["INCREASE_VAL", "/playerData/$PLAYER_N/recruit", 1], ["LOG", "{{$ALIAS_N}} gained 1 Recruit."]],
        "decreaseRecruit": [["DECREASE_VAL", "/playerData/$PLAYER_N/recruit", 1], ["LOG", "{{$ALIAS_N}} spent 1 Recruit."]],
        "increaseResource": [["INCREASE_VAL", "/playerData/$PLAYER_N/resourceLocations", 1], ["LOG", "{{$ALIAS_N}} gained a Resource Location."]],
        "decreaseResource": [["DECREASE_VAL", "/playerData/$PLAYER_N/resourceLocations", 1], ["LOG", "{{$ALIAS_N}} lost a Resource Location."]],
        "koCard": [["DISCARD", "$ACTIVE_CARD_ID"]],
    })
    dump_json(jsons / "actionLists.json", {"actionLists": actions})
    dump_json(jsons / "hotkeys.json", {"hotkeys": {
        "game": [
            {"key": "D", "actionList": "drawDeck", "label": "Draw"},
            {"key": "S", "actionList": "shuffleDeck", "label": "Shuffle deck"},
            {"key": "R", "actionList": "readyAll", "label": "Ready all"},
            {"key": "B", "actionList": "increaseRecruit", "label": "Recruit +1"},
            {"key": "N", "actionList": "decreaseRecruit", "label": "Recruit -1"},
            {"key": "L", "actionList": "increaseResource", "label": "Resource +1"},
        ],
        "card": [
            {"key": "T", "actionList": "spendCard", "label": "Exert"},
            {"key": "K", "actionList": "readyCard", "label": "Ready"},
            {"key": "F", "actionList": ["FLIP", "$ACTIVE_CARD_ID"], "label": "Flip"},
            {"key": "X", "actionList": ["DISCARD", "$ACTIVE_CARD_ID"], "label": "KO"},
            {"key": "A", "actionList": ["DETACH", "$ACTIVE_CARD_ID"], "label": "Detach"},
            {"key": "H", "actionList": ["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"], "label": "Shuffle into deck"},
        ],
        "token": [
            {"key": "1", "tokenType": "wound", "label": "Wound"},
            {"key": "2", "tokenType": "xp", "label": "XP"},
            {"key": "3", "tokenType": "plus", "label": "+1/+1"},
            {"key": "4", "tokenType": "minus", "label": "-1/-1"},
        ],
    }})
    dump_json(jsons / "pluginMenu.json", {"pluginMenu": {"options": [
        {"label": "Draw", "actionList": "drawDeck"},
        {"label": "Shuffle deck", "actionList": "shuffleDeck"},
        {"label": "Ready all", "actionList": "readyAll"},
        {"label": "Recruit +1", "actionList": "increaseRecruit"},
        {"label": "Recruit -1", "actionList": "decreaseRecruit"},
        {"label": "Resource +1", "actionList": "increaseResource"},
        {"label": "Resource -1", "actionList": "decreaseResource"},
    ]}})
    dump_json(jsons / "cardMenu.json", {"cardMenu": {"moveToGroupIds": MOVE_GROUPS, "options": [
        {"label": "Exert", "actionList": "spendCard"},
        {"label": "Ready", "actionList": "readyCard"},
        {"label": "Flip", "actionList": "flipCard"},
        {"label": "KO", "actionList": "koCard"},
        {"label": "Detach", "actionList": "detachCard"},
        {"label": "Shuffle into deck", "actionList": "shuffleIntoDeck"},
    ]}})
    dump_json(jsons / "groupMenu.json", {"groupMenu": {"moveToGroupIds": MOVE_GROUPS, "options": []}})
    dump_json(jsons / "browse.json", {"browse": {
        "filterPropertySideA": "type",
        "filterValuesSideA": types,
        "textPropertiesSideA": ["name", "team", "keyword", "packName", "text"],
    }})
    dump_json(jsons / "deckbuilder.json", {"deckbuilder": {
        "addButtons": [1, 2, 3, 4],
        "columns": [
            {"propName": "name", "label": "Name"},
            {"propName": "type", "label": "Type"},
            {"propName": "cost", "label": "Cost"},
            {"propName": "team", "label": "Team"},
            {"propName": "packName", "label": "Set"},
        ],
        "spawnGroups": [
            {"loadGroupId": "playerNDeck", "label": "My Main Deck"},
            {"loadGroupId": "playerNMain", "label": "My Main Character"},
        ],
    }})
    dump_json(jsons / "spawnExistingCardModal.json", {"spawnExistingCardModal": {
        "columnProperties": ["name", "type", "team", "packName", "cost"],
        "loadGroupIds": ["player1Deck", "player1Play", "player1Main", "player1Locations", "player1Hand", "player1KO", "player2Deck", "player2Play"],
    }})
    dump_json(jsons / "faceProperties.json", {"faceProperties": {
        "cost": {"label": "Cost", "type": "string", "default": ""},
        "health": {"label": "Health", "type": "string", "default": ""},
        "team": {"label": "Team", "type": "string", "default": ""},
        "powerSymbol": {"label": "Power Symbol", "type": "string", "default": ""},
        "rangedFlight": {"label": "Ranged / Flight", "type": "string", "default": ""},
        "keyword": {"label": "Keyword", "type": "string", "default": ""},
        "text": {"label": "Text", "type": "string", "default": ""},
        "packName": {"label": "Set", "type": "string", "default": ""},
        "set": {"label": "Lackey Set", "type": "string", "default": ""},
        "loadGroupId": {"label": "Load Group", "type": "string", "default": ""},
    }})
    dump_json(jsons / "cardProperties.json", {"cardProperties": {}})
    dump_json(jsons / "defaultActions.json", {"defaultActions": []})
    dump_json(jsons / "automation.json", {"automation": {
        "postNewGameActionList": [["LOG", "VS System 2PCG table created. Load a tournament list from Menu → Load. No rules are enforced."]],
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


def write_plugin_art() -> str:
    plugin = IMAGES / GAME_FOLDER / "_plugin"
    plugin.mkdir(parents=True, exist_ok=True)
    back = LACKEY / "sets" / "setimages" / "general" / "Cardback.jpg"
    back_rel = copy_plugin_art(back, IMAGES, GAME_FOLDER, GAME_PASCAL, "cardback-default")
    bg = LACKEY / "Put this image in your backgrounds and select it for VS2PCG" / "VSSYSTEM_Wood.jpg"
    if bg.exists():
        dest = IMAGES / GAME_FOLDER / "_plugin" / f"{GAME_PASCAL}-Background.jpg"
        shutil.copy2(bg, dest)
        shutil.copy2(bg, IMAGES / lobby_art_rel(GAME_FOLDER, "banner"))
    logo = LACKEY / "bot.jpg"
    if logo.exists():
        shutil.copy2(logo, IMAGES / lobby_art_rel(GAME_FOLDER, "logo"))
    elif back.exists():
        shutil.copy2(back, IMAGES / lobby_art_rel(GAME_FOLDER, "logo"))
    write_color_png(plugin / f"{GAME_PASCAL}-TokenWound.png", (214, 122, 36))
    write_color_png(plugin / f"{GAME_PASCAL}-TokenXp.png", (48, 110, 196))
    write_color_png(plugin / f"{GAME_PASCAL}-TokenPlus.png", (46, 184, 72))
    write_color_png(plugin / f"{GAME_PASCAL}-TokenMinus.png", (196, 48, 48))
    return back_rel


def main() -> int:
    carddata = LACKEY / "sets" / "carddata.txt"
    if not carddata.exists():
        raise SystemExit(f"Lackey plugin not found: {LACKEY}")
    index = index_setimages(LACKEY / "sets" / "setimages")
    cards, errors = load_cards(carddata, index)
    write_tsv(cards, TSV_COLUMNS, OUT / "tsvs" / "cards.tsv")
    decks, menu, deck_errors = convert_decks(cards)
    errors.extend(deck_errors)
    back_rel = write_plugin_art()
    write_plugin_jsons(cards, decks, menu, back_rel)
    (OUT / "SOURCE.txt").write_text(
        "\n".join([
            f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from LackeyCCG VS2PCG.",
            f"Source: {LACKEY}",
            "Art copied from local sets/setimages (no remote host).",
            "Author credit: Lackey / VS 2PCG",
            "",
            "Tabletop plugin only — Lackey has no rules engine to port.",
            f"TSV rows: {len(cards)}  missing images: {sum(1 for c in cards if not c['imageUrl'])}",
            f"Prebuilts: {len(decks['preBuiltDecks'])} Lackey tournament decks.",
            "In Lackey, Player Deck is the 60-card deck; Main Deck holds the main character levels.",
            "",
        ]),
        encoding="utf-8",
    )
    print(f"Wrote {OUT.name}")
    print(f"  pluginName: VS System 2PCG")
    print(f"  tsv rows: {len(cards)}  missing images: {sum(1 for c in cards if not c['imageUrl'])}")
    print(f"  prebuilt decks: {len(decks['preBuiltDecks'])}")
    print(f"  types: {', '.join(sorted({c['type'] for c in cards}))}")
    if errors:
        print(f"\n{len(errors)} issue(s):")
        for err in errors[:40]:
            print(f"  - {err}")
        if len(errors) > 40:
            print(f"  … {len(errors) - 40} more")
        return 1
    print("\nNext:\n  python3 plugins/scripts/collect_hosted_images.py --retarget vs-system-2pcg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
