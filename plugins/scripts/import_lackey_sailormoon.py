#!/usr/bin/env python3
"""Build a DragnCards Sailor Moon TCG plugin from the LackeyCCG plugin.

  python3 plugins/scripts/import_lackey_sailormoon.py
  python3 plugins/scripts/collect_hosted_images.py sailor-moon-tcg
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
from image_names import TOYBOX_PREFIX, lobby_art_rel, stamp_lobby_art, toybox_url  # noqa: E402
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

LACKEY = Path("/Users/krystoferrobin/Downloads/lackeyplugins/SailorMoonTCG")
OUT = ROOT / "sailor-moon-tcg"
GAME_FOLDER = "sailor-moon-tcg"
GAME_PASCAL = "SailorMoonTcg"
IMAGES = ROOT / "images"
CARD_BACK_REMOTE = "https://raw.githubusercontent.com/wishmstr/SailorMoonTCG/main/sets/setimages/general/cardback.jpg"

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "rarity",
    "number",
    "faction",
    "health",
    "vp",
    "weak",
    "strong",
    "text",
    "packName",
    "set",
    "loadGroupId",
]

MOVE_GROUPS = [
    "playerNHand",
    "playerNDeck",
    "playerNDiscard",
    "playerNPlay",
    "playerNStarting",
    "playerNLocations",
    "playerNJkp",
    "playerN+1Play",
    "sharedSetAside",
]


def pack_name(set_name: str) -> str:
    return {"past_and_future": "Past and Future", "jkp": "JKP", "premiere": "Premiere"}.get(
        set_name.lower(), set_name.replace("_", " ")
    )


def load_group(card_type: str, set_name: str) -> str:
    if set_name.lower() == "jkp" or card_type == "Token":
        return "playerNJkp"
    if card_type == "Location":
        return "playerNDeck"
    return "playerNDeck"


def load_cards(carddata: Path, urls: dict[str, str]) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    seen: set[str] = set()
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
        if not name or not image_file:
            continue
        card_type = sanitize(cols[col.get("Type", 3)]) or "Card"
        database_id = f"{set_name}_{image_file}"
        if database_id in seen:
            errors.append(f"Duplicate {database_id} at line {line_no}")
            continue
        seen.add(database_id)
        image_url = lookup_image(urls, set_name, image_file)
        if not image_url:
            errors.append(f"Missing image URL for {database_id}")
        texts = [sanitize(cols[col[key]]) for key in ("Card_Text1", "Card_Text2", "Card_Text3", "Card_Text4") if key in col]
        cards.append(
            {
                "databaseId": database_id,
                "name": name,
                "imageUrl": image_url,
                "cardBack": "default",
                "type": card_type,
                "rarity": sanitize(cols[col.get("Rarity", 4)]),
                "number": sanitize(cols[col.get("Number", 5)]),
                "faction": sanitize(cols[col.get("Monster", 6)]),
                "health": sanitize(cols[col.get("Health", 7)]),
                "vp": sanitize(cols[col.get("VP", 8)]),
                "weak": sanitize(cols[col.get("Weak", 9)]),
                "strong": sanitize(cols[col.get("Strong", 10)]),
                "text": " / ".join(part for part in texts if part),
                "packName": pack_name(set_name),
                "set": set_name,
                "loadGroupId": load_group(card_type, set_name),
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
    character: list[dict] = []
    starters: list[dict] = []
    extras: list[dict] = []
    zone_to_group = {
        "Deck": "playerNDeck",
        "Starting": "playerNStarting",
        "JKP": "playerNJkp",
    }
    for dek in sorted((LACKEY / "decks").glob("*.dek")):
        label = dek.stem.replace("_", " ")
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
        item = {"deckListId": deck_id, "label": label}
        lower = label.lower()
        if "character" in lower:
            character.append(item)
        elif "starter" in lower:
            starters.append(item)
        else:
            extras.append(item)
    menus = []
    if character:
        menus.append({"label": "Character Decks", "deckLists": character})
    if starters:
        menus.append({"label": "2-Player Starters", "deckLists": starters})
    if extras:
        menus.append({"label": "Theme Decks", "deckLists": extras})
    return {"preBuiltDecks": dict(prebuilt)}, {"deckMenu": {"subMenus": menus}}, errors


def player_piles(player: str) -> dict[str, dict]:
    return {
        f"{player}Deck": {
            "groupType": "deck",
            "label": f"Player {player[-1]} Deck",
            "tableLabel": "Deck",
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}Discard"},
        },
        f"{player}Discard": {
            "groupType": "discard",
            "label": f"Player {player[-1]} Discard",
            "tableLabel": "Discard",
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}Discard"},
        },
        f"{player}Hand": {
            "groupType": "hand",
            "label": f"Player {player[-1]} Hand",
            "tableLabel": "Hand",
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}Discard"},
        },
        f"{player}Starting": {
            "groupType": "inPlay",
            "label": f"Player {player[-1]} Starting",
            "tableLabel": "Starting",
            "canHaveAttachments": True,
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}Discard", "inPlay": True},
        },
        f"{player}Play": {
            "groupType": "inPlay",
            "label": f"Player {player[-1]} Play",
            "tableLabel": "Play",
            "canHaveAttachments": True,
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}Discard", "inPlay": True},
        },
        f"{player}Locations": {
            "groupType": "inPlay",
            "label": f"Player {player[-1]} Locations",
            "tableLabel": "Locations",
            "canHaveAttachments": True,
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}Discard", "inPlay": True},
        },
        f"{player}Jkp": {
            "groupType": "aside",
            "label": f"Player {player[-1]} JKP",
            "tableLabel": "JKP",
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}Discard", "currentSide": "A"},
        },
    }


def write_plugin_jsons(cards: list[dict[str, str]], decks: dict, menu: dict, back_rel: str) -> None:
    jsons = OUT / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    types = sorted({card["type"] for card in cards})
    dump_json(jsons / "main.json", {
        "pluginName": "Sailor Moon TCG",
        "author": "Lackey / wishmstr",
        "tutorialUrl": "https://github.com/wishmstr/SailorMoonTCG",
        "announcements": [
            "Tabletop plugin from the Lackey Sailor Moon TCG set. No rules engine — Draw, JKP, damage counters, and VP are shortcuts.",
            "D = draw. R = ready all. I = rotate 180. X = discard. 1/2/3 = +10 / +30 / +100 damage. C = flip a coin.",
        ],
        "loadPreBuiltOnNewGame": False,
    })
    stamp_lobby_art(jsons, GAME_FOLDER)
    dump_json(jsons / "imageUrlPrefix.json", {"imageUrlPrefix": {"Default": TOYBOX_PREFIX}})
    dump_json(jsons / "cardBacks.json", {"cardBacks": {"default": {"width": 0.72, "height": 1.0, "imageUrl": back_rel or CARD_BACK_REMOTE}}})
    dump_json(jsons / "cardTypes.json", {"cardTypes": {
        name: {"width": 0.72, "height": 1.0, "tokens": ["dmg10", "dmg30", "dmg100"]} for name in types
    }})
    groups = {"sharedSetAside": {"groupType": "aside", "label": "Set Aside", "tableLabel": "Set Aside", "onCardEnter": {"controller": "shared"}}}
    groups.update(player_piles("player1"))
    groups.update(player_piles("player2"))
    dump_json(jsons / "groups.json", {"groups": groups})
    dump_json(jsons / "layouts.json", {"layouts": {"default": {
        "cardSize": 10,
        "rowSpacing": 2,
        "chat": {"left": "76%", "top": "78%", "width": "23%", "height": "21%"},
        "regions": {
            "playerN+1Hand": region("playerN+1Hand", "fan", "0%", "0%", "58%", "9%", disableDroppableAttachments=True),
            "playerN+1Starting": region("playerN+1Starting", "row", "58%", "0%", "17%", "12%"),
            "playerN+1Play": region("playerN+1Play", "free", "0%", "12%", "75%", "18%"),
            "playerN+1Locations": region("playerN+1Locations", "row", "0%", "30%", "75%", "8%"),
            "playerNLocations": region("playerNLocations", "row", "0%", "38%", "75%", "8%"),
            "playerNPlay": region("playerNPlay", "free", "0%", "46%", "58%", "20%"),
            "playerNStarting": region("playerNStarting", "row", "58%", "46%", "17%", "14%"),
            "playerNJkp": region("playerNJkp", "row", "0%", "66%", "36%", "10%"),
            "playerNHand": region("playerNHand", "fan", "0%", "82%", "58%", "17%", disableDroppableAttachments=True),
            "playerN+1Deck": region("playerN+1Deck", "pile", "76%", "10%", "11%", "14%"),
            "playerN+1Discard": region("playerN+1Discard", "pile", "88%", "10%", "11%", "14%"),
            "sharedSetAside": region("sharedSetAside", "pile", "76%", "25%", "23%", "12%"),
            "playerNDeck": region("playerNDeck", "pile", "76%", "58%", "11%", "16%"),
            "playerNDiscard": region("playerNDiscard", "pile", "88%", "58%", "11%", "16%"),
        },
        "tableButtons": {
            "drawDeck": {"actionList": "drawDeck", "label": "Draw", "left": "76%", "top": "46%", "width": "11%", "height": "3.2%"},
            "flipCoin": {"actionList": "flipCoin", "label": "JKP / Coin", "left": "88%", "top": "46%", "width": "11%", "height": "3.2%"},
            "increaseVp": {"actionList": "increaseVp", "label": "VP +1", "left": "76%", "top": "50%", "width": "11%", "height": "3.2%"},
            "readyAll": {"actionList": "readyAll", "label": "Ready All", "left": "88%", "top": "50%", "width": "11%", "height": "3.2%"},
        },
    }}})
    dump_json(jsons / "groupTypes.json", {"groupTypes": group_types()})
    dump_json(jsons / "playerCountMenu.json", {"playerCountMenu": [{"label": "2", "numPlayers": 2, "layoutId": "default"}]})
    dump_json(jsons / "phases.json", {"phases": {
        "draw": {"label": "Draw", "height": "20%"},
        "play": {"label": "Play", "height": "20%"},
        "use": {"label": "Use", "height": "20%"},
        "attack": {"label": "Attack", "height": "20%"},
        "discard": {"label": "Discard / Balance", "height": "20%"},
    }, "phaseOrder": ["draw", "play", "use", "attack", "discard"]})
    dump_json(jsons / "steps.json", {"steps": {
        "drawStep": {"phaseId": "draw", "label": "Draw 1 Card"},
        "playStep": {"phaseId": "play", "label": "Play Cards"},
        "useStep": {"phaseId": "use", "label": "Use Cards"},
        "attackStep": {"phaseId": "attack", "label": "Scout / Knight Action"},
        "discardStep": {"phaseId": "discard", "label": "Discard / Balance to 5"},
    }, "stepOrder": ["drawStep", "playStep", "useStep", "attackStep", "discardStep"]})
    dump_json(jsons / "playerProperties.json", {"playerProperties": {
        "victoryPoints": {"label": "Victory Points", "type": "integer", "default": 0, "min": 0},
    }})
    dump_json(jsons / "gameProperties.json", {"gameProperties": {}})
    dump_json(jsons / "topBarCounters.json", {"topBarCounters": {
        "shared": [{"label": "Round", "imageUrl": "", "gameProperty": "roundNumber"}],
        "player": [{"label": "VP", "imageUrl": "", "playerProperty": "victoryPoints"}],
    }})
    dump_json(jsons / "tokens.json", {"tokens": {
        "dmg10": {"label": "+10", "left": "72%", "top": "4%", "width": "4vh", "height": "4vh", "imageUrl": toybox_url(f"{GAME_FOLDER}/_plugin/{GAME_PASCAL}-TokenDmg10.png"), "canBeNegative": True},
        "dmg30": {"label": "+30", "left": "50%", "top": "4%", "width": "4vh", "height": "4vh", "imageUrl": toybox_url(f"{GAME_FOLDER}/_plugin/{GAME_PASCAL}-TokenDmg30.png"), "canBeNegative": True},
        "dmg100": {"label": "+100", "left": "28%", "top": "4%", "width": "4vh", "height": "4vh", "imageUrl": toybox_url(f"{GAME_FOLDER}/_plugin/{GAME_PASCAL}-TokenDmg100.png"), "canBeNegative": True},
    }})
    dump_json(jsons / "functions.json", {"functions": standard_functions()})
    actions = standard_actions()
    actions.update({
        "flipCoin": [["VAR", "$FLIP", ["RANDOM_INT", 1, 3]], [
            "COND",
            ["EQUAL", "$FLIP", 1], ["LOG", "{{$ALIAS_N}} flipped JKP: Jan."],
            ["EQUAL", "$FLIP", 2], ["LOG", "{{$ALIAS_N}} flipped JKP: Ken."],
            ["TRUE"], ["LOG", "{{$ALIAS_N}} flipped JKP: Pon."],
        ]],
        "increaseVp": [["INCREASE_VAL", "/playerData/$PLAYER_N/victoryPoints", 1], ["LOG", "{{$ALIAS_N}} scored 1 Victory Point."]],
        "decreaseVp": [["DECREASE_VAL", "/playerData/$PLAYER_N/victoryPoints", 1], ["LOG", "{{$ALIAS_N}} lost 1 Victory Point."]],
        "rotateCard": [["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 180], ["LOG", "{{$ALIAS_N}} rotated {{$ACTIVE_FACE.name}}."]],
    })
    dump_json(jsons / "actionLists.json", {"actionLists": actions})
    dump_json(jsons / "hotkeys.json", {"hotkeys": {
        "game": [
            {"key": "D", "actionList": "drawDeck", "label": "Draw"},
            {"key": "S", "actionList": "shuffleDeck", "label": "Shuffle deck"},
            {"key": "R", "actionList": "readyAll", "label": "Ready all"},
            {"key": "C", "actionList": "flipCoin", "label": "JKP / coin"},
            {"key": "V", "actionList": "increaseVp", "label": "VP +1"},
        ],
        "card": [
            {"key": "I", "actionList": "rotateCard", "label": "Rotate 180"},
            {"key": "K", "actionList": "readyCard", "label": "Ready"},
            {"key": "F", "actionList": ["FLIP", "$ACTIVE_CARD_ID"], "label": "Flip"},
            {"key": "X", "actionList": ["DISCARD", "$ACTIVE_CARD_ID"], "label": "Discard"},
            {"key": "A", "actionList": ["DETACH", "$ACTIVE_CARD_ID"], "label": "Detach"},
            {"key": "H", "actionList": ["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"], "label": "Shuffle into deck"},
        ],
        "token": [
            {"key": "1", "tokenType": "dmg10", "label": "+10 damage"},
            {"key": "2", "tokenType": "dmg30", "label": "+30 damage"},
            {"key": "3", "tokenType": "dmg100", "label": "+100 damage"},
        ],
    }})
    dump_json(jsons / "pluginMenu.json", {"pluginMenu": {"options": [
        {"label": "Draw", "actionList": "drawDeck"},
        {"label": "Shuffle deck", "actionList": "shuffleDeck"},
        {"label": "Ready all", "actionList": "readyAll"},
        {"label": "JKP / coin", "actionList": "flipCoin"},
        {"label": "VP +1", "actionList": "increaseVp"},
        {"label": "VP -1", "actionList": "decreaseVp"},
    ]}})
    dump_json(jsons / "cardMenu.json", {"cardMenu": {"moveToGroupIds": MOVE_GROUPS, "options": [
        {"label": "Rotate 180", "actionList": "rotateCard"},
        {"label": "Ready", "actionList": "readyCard"},
        {"label": "Flip", "actionList": "flipCard"},
        {"label": "Discard", "actionList": "discardCard"},
        {"label": "Detach", "actionList": "detachCard"},
        {"label": "Shuffle into deck", "actionList": "shuffleIntoDeck"},
    ]}})
    dump_json(jsons / "groupMenu.json", {"groupMenu": {"moveToGroupIds": MOVE_GROUPS, "options": []}})
    dump_json(jsons / "browse.json", {"browse": {
        "filterPropertySideA": "type",
        "filterValuesSideA": types,
        "textPropertiesSideA": ["name", "faction", "text", "packName"],
    }})
    dump_json(jsons / "deckbuilder.json", {"deckbuilder": {
        "addButtons": [1, 2, 3, 4],
        "columns": [
            {"propName": "name", "label": "Name"},
            {"propName": "type", "label": "Type"},
            {"propName": "health", "label": "Health"},
            {"propName": "vp", "label": "VP"},
            {"propName": "packName", "label": "Set"},
        ],
        "spawnGroups": [
            {"loadGroupId": "playerNDeck", "label": "My Deck"},
            {"loadGroupId": "playerNStarting", "label": "My Starting"},
            {"loadGroupId": "playerNJkp", "label": "My JKP"},
        ],
    }})
    dump_json(jsons / "spawnExistingCardModal.json", {"spawnExistingCardModal": {
        "columnProperties": ["name", "type", "packName", "health", "vp"],
        "loadGroupIds": ["player1Deck", "player1Play", "player1Starting", "player1Locations", "player1Jkp", "player1Hand", "player2Deck", "player2Play"],
    }})
    dump_json(jsons / "faceProperties.json", {"faceProperties": {
        "rarity": {"label": "Rarity", "type": "string", "default": ""},
        "number": {"label": "Number", "type": "string", "default": ""},
        "faction": {"label": "Faction", "type": "string", "default": ""},
        "health": {"label": "Health", "type": "string", "default": ""},
        "vp": {"label": "Victory Points", "type": "string", "default": ""},
        "weak": {"label": "Weak Against", "type": "string", "default": ""},
        "strong": {"label": "Strong Against", "type": "string", "default": ""},
        "text": {"label": "Text", "type": "string", "default": ""},
        "packName": {"label": "Set", "type": "string", "default": ""},
        "set": {"label": "Lackey Set", "type": "string", "default": ""},
        "loadGroupId": {"label": "Load Group", "type": "string", "default": ""},
    }})
    dump_json(jsons / "cardProperties.json", {"cardProperties": {}})
    dump_json(jsons / "defaultActions.json", {"defaultActions": []})
    dump_json(jsons / "automation.json", {"automation": {
        "postNewGameActionList": [["LOG", "Sailor Moon TCG table created. Load a character deck from Menu → Load. No rules are enforced."]],
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
    back = LACKEY / "sets" / "setimages" / "general" / "cardback.jpg"
    back_rel = ""
    if back.exists():
        back_rel = copy_plugin_art(back, IMAGES, GAME_FOLDER, GAME_PASCAL, "cardback-default")
        shutil.copy2(back, IMAGES / lobby_art_rel(GAME_FOLDER, "logo"))
        shutil.copy2(back, IMAGES / lobby_art_rel(GAME_FOLDER, "banner"))
    write_color_png(plugin / f"{GAME_PASCAL}-TokenDmg10.png", (196, 48, 48))
    write_color_png(plugin / f"{GAME_PASCAL}-TokenDmg30.png", (48, 110, 196))
    write_color_png(plugin / f"{GAME_PASCAL}-TokenDmg100.png", (214, 176, 36))
    return back_rel


def main() -> int:
    carddata = LACKEY / "sets" / "carddata.txt"
    if not carddata.exists():
        raise SystemExit(f"Lackey plugin not found: {LACKEY}")
    urls = load_image_urls(LACKEY / "CardImageURLs1.txt")
    cards, errors = load_cards(carddata, urls)
    write_tsv(cards, TSV_COLUMNS, OUT / "tsvs" / "cards.tsv")
    decks, menu, deck_errors = convert_decks(cards)
    errors.extend(deck_errors)
    back_rel = write_plugin_art()
    write_plugin_jsons(cards, decks, menu, back_rel)
    (OUT / "SOURCE.txt").write_text(
        "\n".join([
            f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from LackeyCCG SailorMoonTCG.",
            f"Source: {LACKEY}",
            "Art: GitHub wishmstr/SailorMoonTCG raw setimages.",
            "Author credit: Lackey / wishmstr",
            "",
            "Tabletop plugin only — Lackey has no rules engine to port.",
            f"TSV rows: {len(cards)}  missing image URLs: {sum(1 for c in cards if not c['imageUrl'])}",
            f"Prebuilts: {len(decks['preBuiltDecks'])} Lackey character / starter / theme decks.",
            "Starting zone holds the opening Scout + Person + Monster. JKP tokens load to the JKP row.",
            "",
        ]),
        encoding="utf-8",
    )
    print(f"Wrote {OUT.name}")
    print(f"  pluginName: Sailor Moon TCG")
    print(f"  tsv rows: {len(cards)}  missing urls: {sum(1 for c in cards if not c['imageUrl'])}")
    print(f"  prebuilt decks: {len(decks['preBuiltDecks'])}")
    print(f"  types: {', '.join(sorted({c['type'] for c in cards}))}")
    if errors:
        print(f"\n{len(errors)} issue(s):")
        for err in errors[:40]:
            print(f"  - {err}")
        if len(errors) > 40:
            print(f"  … {len(errors) - 40} more")
        return 1
    print("\nNext:\n  python3 plugins/scripts/collect_hosted_images.py sailor-moon-tcg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
