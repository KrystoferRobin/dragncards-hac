#!/usr/bin/env python3
"""Build a DragnCards Fight Klub plugin from the LackeyCCG plugin.

  python3 plugins/scripts/import_lackey_fightklub.py
  python3 plugins/scripts/collect_hosted_images.py --retarget fight-klub
"""

from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from image_names import TOYBOX_PREFIX, lobby_art_rel, stamp_lobby_art, toybox_url  # noqa: E402
from lackey_tabletop import (  # noqa: E402
    copy_card_art,
    copy_plugin_art,
    dump_json,
    find_local_image,
    group_types,
    index_setimages,
    region,
    sanitize,
    standard_actions,
    standard_functions,
    write_tsv,
)

LACKEY = Path("/Users/krystoferrobin/Downloads/lackeyplugins/fightklub")
OUT = ROOT / "fight-klub"
GAME_FOLDER = "fight-klub"
GAME_PASCAL = "FightKlub"
IMAGES = ROOT / "images"

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "rarity",
    "number",
    "packName",
    "set",
    "loadGroupId",
]

MOVE_GROUPS = [
    "playerNHand",
    "playerNDeck",
    "playerNDiscard",
    "playerNCharacter",
    "playerNFight",
    "playerNDamage",
    "playerN+1Character",
    "sharedDrop",
    "sharedSetAside",
]


def display_name(raw: str) -> str:
    parts = raw.split("_")
    if len(parts) >= 4:
        rest = "_".join(parts[3:])
    else:
        rest = raw
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", rest)
    spaced = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", spaced)
    return spaced.replace("_", " ").strip() or raw


def parse_meta(raw: str) -> tuple[str, str]:
    parts = raw.split("_")
    number = parts[1] if len(parts) > 1 else ""
    rarity = {"C": "Common", "U": "Uncommon", "R": "Rare"}.get(parts[2], parts[2] if len(parts) > 2 else "")
    return number, rarity


def load_cards(carddata: Path, index: dict[str, Path]) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    seen: set[str] = set()
    used: dict[str, int] = {}
    lines = carddata.read_text(encoding="utf-8", errors="replace").splitlines()
    for line_no, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        cols = line.split("\t")
        while len(cols) < 3:
            cols.append("")
        raw_name, set_name, image_file = [sanitize(c) for c in cols[:3]]
        if not raw_name or not image_file:
            continue
        database_id = f"{set_name}_{image_file}"
        if database_id in seen:
            errors.append(f"Duplicate {database_id} at line {line_no}")
            continue
        seen.add(database_id)
        number, rarity = parse_meta(raw_name)
        name = display_name(raw_name)
        src = find_local_image(index, set_name, image_file)
        if not src:
            errors.append(f"Missing image for {database_id}")
            image_url = ""
        else:
            image_url = copy_card_art(src, IMAGES, GAME_FOLDER, GAME_PASCAL, set_name, name, used)
        cards.append(
            {
                "databaseId": database_id,
                "name": name,
                "imageUrl": image_url,
                "cardBack": "default",
                "type": "Card",
                "rarity": rarity,
                "number": number,
                "packName": set_name,
                "set": set_name,
                "loadGroupId": "playerNDeck",
            }
        )
    return cards, errors


def player_piles(player: str) -> dict[str, dict]:
    return {
        f"{player}Deck": {
            "groupType": "deck",
            "label": f"Player {player[-1]} Draw Stack",
            "tableLabel": "Draw",
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
        f"{player}Character": {
            "groupType": "inPlay",
            "label": f"Player {player[-1]} Character",
            "tableLabel": "Character",
            "canHaveAttachments": True,
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}Discard", "inPlay": True},
        },
        f"{player}Fight": {
            "groupType": "inPlay",
            "label": f"Player {player[-1]} Fight Stack",
            "tableLabel": "Fight",
            "canHaveAttachments": True,
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}Discard", "inPlay": True},
        },
        f"{player}Damage": {
            "groupType": "discard",
            "label": f"Player {player[-1]} Damage Stack",
            "tableLabel": "Damage",
            "onCardEnter": {"controller": player, "deckGroupId": f"{player}Deck", "discardGroupId": f"{player}Discard"},
        },
    }


def write_plugin_jsons(cards: list[dict[str, str]], back_rel: str) -> None:
    jsons = OUT / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    types = sorted({card["type"] for card in cards})
    dump_json(jsons / "main.json", {
        "pluginName": "Fight Klub",
        "author": "Lackey / Fight Klub",
        "announcements": [
            "Tabletop plugin from the Lackey Fight Klub set. No rules engine — Draw, Fight, Refresh/Activate, and energy counters are shortcuts.",
            "D = draw. R = refresh all. T = activate. I = invert. X = discard.",
        ],
        "loadPreBuiltOnNewGame": False,
    })
    stamp_lobby_art(jsons, GAME_FOLDER)
    dump_json(jsons / "imageUrlPrefix.json", {"imageUrlPrefix": {"Default": TOYBOX_PREFIX}})
    dump_json(jsons / "cardBacks.json", {"cardBacks": {"default": {"width": 0.72, "height": 1.0, "imageUrl": back_rel}}})
    dump_json(jsons / "cardTypes.json", {"cardTypes": {name: {"width": 0.72, "height": 1.0, "tokens": []} for name in types}})
    groups = {
        "sharedSetAside": {"groupType": "aside", "label": "Set Aside", "tableLabel": "Set Aside", "onCardEnter": {"controller": "shared"}},
        "sharedDrop": {"groupType": "inPlay", "label": "The Drop", "tableLabel": "The Drop", "canHaveAttachments": True, "onCardEnter": {"controller": "shared", "inPlay": True}},
    }
    groups.update(player_piles("player1"))
    groups.update(player_piles("player2"))
    dump_json(jsons / "groups.json", {"groups": groups})
    dump_json(jsons / "layouts.json", {"layouts": {"default": {
        "cardSize": 10,
        "rowSpacing": 2,
        "chat": {"left": "76%", "top": "78%", "width": "23%", "height": "21%"},
        "regions": {
            "playerN+1Hand": region("playerN+1Hand", "fan", "0%", "0%", "58%", "10%", disableDroppableAttachments=True),
            "playerN+1Character": region("playerN+1Character", "row", "58%", "0%", "17%", "12%"),
            "playerN+1Fight": region("playerN+1Fight", "row", "0%", "12%", "75%", "14%"),
            "sharedDrop": region("sharedDrop", "row", "0%", "26%", "75%", "12%"),
            "playerNFight": region("playerNFight", "row", "0%", "38%", "75%", "16%"),
            "playerNCharacter": region("playerNCharacter", "row", "58%", "54%", "17%", "14%"),
            "playerNHand": region("playerNHand", "fan", "0%", "82%", "58%", "17%", disableDroppableAttachments=True),
            "playerN+1Deck": region("playerN+1Deck", "pile", "76%", "10%", "11%", "14%"),
            "playerN+1Discard": region("playerN+1Discard", "pile", "88%", "10%", "11%", "14%"),
            "playerN+1Damage": region("playerN+1Damage", "pile", "76%", "25%", "11%", "12%"),
            "sharedSetAside": region("sharedSetAside", "pile", "88%", "25%", "11%", "12%"),
            "playerNDeck": region("playerNDeck", "pile", "76%", "58%", "11%", "16%"),
            "playerNDiscard": region("playerNDiscard", "pile", "88%", "58%", "11%", "16%"),
            "playerNDamage": region("playerNDamage", "pile", "76%", "46%", "11%", "11%"),
        },
        "tableButtons": {
            "drawDeck": {"actionList": "drawDeck", "label": "Draw", "left": "76%", "top": "40%", "width": "11%", "height": "3.2%"},
            "readyAll": {"actionList": "readyAll", "label": "Refresh All", "left": "88%", "top": "40%", "width": "11%", "height": "3.2%"},
        },
    }}})
    dump_json(jsons / "groupTypes.json", {"groupTypes": group_types()})
    dump_json(jsons / "playerCountMenu.json", {"playerCountMenu": [{"label": "2", "numPlayers": 2, "layoutId": "default"}]})
    dump_json(jsons / "phases.json", {"phases": {
        "draw": {"label": "Draw", "height": "33%"},
        "fight": {"label": "Fight", "height": "34%"},
        "cleanup": {"label": "Cleanup", "height": "33%"},
    }, "phaseOrder": ["draw", "fight", "cleanup"]})
    dump_json(jsons / "steps.json", {"steps": {
        "drawStep": {"phaseId": "draw", "label": "Draw"},
        "fightStep": {"phaseId": "fight", "label": "Fight"},
        "cleanupStep": {"phaseId": "cleanup", "label": "Cleanup"},
    }, "stepOrder": ["drawStep", "fightStep", "cleanupStep"]})
    dump_json(jsons / "playerProperties.json", {"playerProperties": {
        "life": {"label": "Life", "type": "integer", "default": 0},
        "hold": {"label": "Hold", "type": "integer", "default": 0, "min": 0},
        "energyBlue": {"label": "Energy Blue", "type": "integer", "default": 0, "min": 0},
        "energyGreen": {"label": "Energy Green", "type": "integer", "default": 0, "min": 0},
        "energyYellow": {"label": "Energy Yellow", "type": "integer", "default": 0, "min": 0},
    }})
    dump_json(jsons / "gameProperties.json", {"gameProperties": {}})
    dump_json(jsons / "topBarCounters.json", {"topBarCounters": {
        "shared": [{"label": "Round", "imageUrl": "", "gameProperty": "roundNumber"}],
        "player": [
            {"label": "Life", "imageUrl": "", "playerProperty": "life"},
            {"label": "Hold", "imageUrl": "", "playerProperty": "hold"},
            {"label": "Blue", "imageUrl": "", "playerProperty": "energyBlue"},
            {"label": "Green", "imageUrl": "", "playerProperty": "energyGreen"},
            {"label": "Yellow", "imageUrl": "", "playerProperty": "energyYellow"},
        ],
    }})
    dump_json(jsons / "tokens.json", {"tokens": {}})
    dump_json(jsons / "functions.json", {"functions": standard_functions()})
    dump_json(jsons / "actionLists.json", {"actionLists": standard_actions()})
    dump_json(jsons / "hotkeys.json", {"hotkeys": {
        "game": [
            {"key": "D", "actionList": "drawDeck", "label": "Draw"},
            {"key": "S", "actionList": "shuffleDeck", "label": "Shuffle draw stack"},
            {"key": "R", "actionList": "readyAll", "label": "Refresh all"},
        ],
        "card": [
            {"key": "T", "actionList": "spendCard", "label": "Activate"},
            {"key": "K", "actionList": "readyCard", "label": "Refresh"},
            {"key": "I", "actionList": "invertCard", "label": "Invert"},
            {"key": "F", "actionList": ["FLIP", "$ACTIVE_CARD_ID"], "label": "Flip"},
            {"key": "X", "actionList": ["DISCARD", "$ACTIVE_CARD_ID"], "label": "Discard"},
            {"key": "A", "actionList": ["DETACH", "$ACTIVE_CARD_ID"], "label": "Detach"},
            {"key": "H", "actionList": ["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"], "label": "Shuffle into draw stack"},
        ],
        "token": [],
    }})
    dump_json(jsons / "pluginMenu.json", {"pluginMenu": {"options": [
        {"label": "Draw", "actionList": "drawDeck"},
        {"label": "Shuffle draw stack", "actionList": "shuffleDeck"},
        {"label": "Refresh all", "actionList": "readyAll"},
    ]}})
    dump_json(jsons / "cardMenu.json", {"cardMenu": {"moveToGroupIds": MOVE_GROUPS, "options": [
        {"label": "Activate", "actionList": "spendCard"},
        {"label": "Refresh", "actionList": "readyCard"},
        {"label": "Invert", "actionList": "invertCard"},
        {"label": "Flip", "actionList": "flipCard"},
        {"label": "Discard", "actionList": "discardCard"},
        {"label": "Detach", "actionList": "detachCard"},
        {"label": "Shuffle into draw stack", "actionList": "shuffleIntoDeck"},
    ]}})
    dump_json(jsons / "groupMenu.json", {"groupMenu": {"moveToGroupIds": MOVE_GROUPS, "options": []}})
    dump_json(jsons / "browse.json", {"browse": {
        "filterPropertySideA": "packName",
        "filterValuesSideA": sorted({card["packName"] for card in cards}),
        "textPropertiesSideA": ["name", "rarity", "packName"],
    }})
    dump_json(jsons / "deckbuilder.json", {"deckbuilder": {
        "addButtons": [1, 2, 3, 4],
        "columns": [
            {"propName": "name", "label": "Name"},
            {"propName": "rarity", "label": "Rarity"},
            {"propName": "packName", "label": "Set"},
            {"propName": "number", "label": "No."},
        ],
        "spawnGroups": [{"loadGroupId": "playerNDeck", "label": "My Draw Stack"}],
    }})
    dump_json(jsons / "spawnExistingCardModal.json", {"spawnExistingCardModal": {
        "columnProperties": ["name", "rarity", "packName"],
        "loadGroupIds": ["player1Deck", "player1Character", "player1Fight", "player1Hand", "sharedDrop", "player2Deck", "player2Character"],
    }})
    dump_json(jsons / "faceProperties.json", {"faceProperties": {
        "rarity": {"label": "Rarity", "type": "string", "default": ""},
        "number": {"label": "Number", "type": "string", "default": ""},
        "packName": {"label": "Set", "type": "string", "default": ""},
        "set": {"label": "Lackey Set", "type": "string", "default": ""},
        "loadGroupId": {"label": "Load Group", "type": "string", "default": ""},
    }})
    dump_json(jsons / "cardProperties.json", {"cardProperties": {}})
    dump_json(jsons / "defaultActions.json", {"defaultActions": []})
    dump_json(jsons / "automation.json", {"automation": {
        "postNewGameActionList": [["LOG", "Fight Klub table created. Build a draw stack from the deck editor. No rules are enforced."]],
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
    dump_json(jsons / "preBuiltDecks.json", {"preBuiltDecks": {}})
    dump_json(jsons / "deckMenu.json", {"deckMenu": {"subMenus": []}})


def write_plugin_art() -> str:
    back = LACKEY / "sets" / "setimages" / "general" / "cardback.jpg"
    back_rel = copy_plugin_art(back, IMAGES, GAME_FOLDER, GAME_PASCAL, "cardback-default")
    shutil.copy2(back, IMAGES / lobby_art_rel(GAME_FOLDER, "logo"))
    spawned = LACKEY / "sets" / "setimages" / "general" / "spawned.jpg"
    if spawned.exists():
        shutil.copy2(spawned, IMAGES / lobby_art_rel(GAME_FOLDER, "banner"))
    else:
        shutil.copy2(back, IMAGES / lobby_art_rel(GAME_FOLDER, "banner"))
    return back_rel


def main() -> int:
    carddata = LACKEY / "sets" / "carddata.txt"
    if not carddata.exists():
        raise SystemExit(f"Lackey plugin not found: {LACKEY}")
    index = index_setimages(LACKEY / "sets" / "setimages")
    cards, errors = load_cards(carddata, index)
    write_tsv(cards, TSV_COLUMNS, OUT / "tsvs" / "cards.tsv")
    back_rel = write_plugin_art()
    write_plugin_jsons(cards, back_rel)
    missing = [err for err in errors if err.startswith("Missing")]
    (OUT / "SOURCE.txt").write_text(
        "\n".join([
            f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from LackeyCCG fightklub.",
            f"Source: {LACKEY}",
            "Art copied from local sets/setimages (no remote host).",
            "Author credit: Lackey / Fight Klub",
            "",
            "Tabletop plugin only — Lackey has no rules engine to port.",
            f"TSV rows: {len(cards)}  missing images: {sum(1 for c in cards if not c['imageUrl'])}",
            "No Lackey starter decks shipped with this plugin.",
            "Missing from the Lackey image dump: Three / 3_009_R_Targeting." if missing else "",
            "",
        ]),
        encoding="utf-8",
    )
    print(f"Wrote {OUT.name}")
    print(f"  pluginName: Fight Klub")
    print(f"  tsv rows: {len(cards)}  missing images: {sum(1 for c in cards if not c['imageUrl'])}")
    if errors:
        print(f"\n{len(errors)} issue(s):")
        for err in errors[:40]:
            print(f"  - {err}")
    print("\nNext:\n  python3 plugins/scripts/collect_hosted_images.py --retarget fight-klub")
    return 1 if any(not err.startswith("Missing") for err in errors) else 0


if __name__ == "__main__":
    raise SystemExit(main())
