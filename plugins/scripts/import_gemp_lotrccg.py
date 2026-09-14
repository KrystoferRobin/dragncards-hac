#!/usr/bin/env python3
"""Build a DragnCards Lord of the Rings TCG plugin from GEMP-LOTR HJSON + art maps.

GEMP's Java rules engine is not ported. Layout follows the GEMP table: adventure path,
fellowship, support, shadow/minions, deck/discard/dead/adventure-deck piles, twilight.

  python plugins/scripts/import_gemp_lotrccg.py
  python plugins/scripts/collect_hosted_images.py lotr-ccg-gemp
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from import_gemp_prebuilts import write_lotr_prebuilts
from image_names import clear_image_url_prefix, toybox_url

ROOT = Path(__file__).resolve().parents[1]
GEMP = ROOT / "lotrccg-gemp-conversion" / "gemp-lotr-master" / "gemp-lotr"
CARDS = GEMP / "gemp-lotr-cards" / "src" / "main" / "resources" / "cards"
SET_CONFIG = GEMP / "gemp-lotr-cards" / "src" / "main" / "resources" / "setConfig.hjson"
JS = GEMP / "gemp-lotr-async" / "src" / "main" / "web" / "js" / "gemp-022"
SWCCG = ROOT / "star-wars-ccg-decipher"
OUT = ROOT / "lotr-ccg-gemp"

CARD_BACK = "https://i.lotrtcgpc.net/decipher/LOTR00000.jpg"
CDN = "https://i.lotrtcgpc.net/"

CATEGORIES = [
    "COMPANION",
    "ALLY",
    "MINION",
    "SITE",
    "METASITE",
    "EVENT",
    "CONDITION",
    "POSSESSION",
    "ARTIFACT",
    "THE_ONE_RING",
    "FOLLOWER",
    "MAP",
]

CULTURE_COLORS = {
    "Gondor": "#4B81D7",
    "Rohan": "#C4A35A",
    "Elven": "#57B01A",
    "Dwarven": "#8B6914",
    "Gandalf": "#C9A227",
    "Shire": "#6B8F3C",
    "Gollum": "#7A6F5D",
    "Sauron": "#4A0E0E",
    "Ringwraith": "#2B2B2B",
    "Moria": "#5C4A3A",
    "Isengard": "#3D5C3A",
    "Raider": "#8B3A2A",
    "Dunland": "#6E4B2A",
    "Men": "#8A6A4A",
    "Orc": "#3F4A2A",
    "Uruk-hai": "#4A3020",
    "Wraith": "#333333",
    "Free Peoples": "#4B81D7",
    "Shadow": "#AC1714",
}

COPY_AS_IS = [
    "groupTypes.json",
    "saveGame.json",
    "preferences.json",
    "pluginMenu.json",
    "tokens.json",
    "cardProperties.json",
    "faceProperties.json",
]


def dump_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")
    return text.strip()


def parse_js_images(*paths: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    pattern = re.compile(r"""['"](\-?\d+_\d+|gl_[^'"]+)['"]\s*:\s*['"](https?://[^'"]+)['"]""")
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        cleaned = "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))
        mapping.update(pattern.findall(cleaned))
    return mapping


def parse_set_names(path: Path) -> dict[int, str]:
    names: dict[int, str] = {}
    text = path.read_text(encoding="utf-8")
    for block in re.split(r"\{", text):
        sid = re.search(r"setId:\s*(\d+)", block)
        name = re.search(r"setName:\s*(.+)", block)
        if sid and name:
            names[int(sid.group(1))] = name.group(1).strip().strip('"').strip("'")
    return names


def extract_objects(text: str) -> list[tuple[str, str]]:
    cards: list[tuple[str, str]] = []
    for match in re.finditer(r"(?m)^[\t ]+(\d+_\d+)\s*:\s*\{", text):
        start = match.end() - 1
        depth = 0
        for index, char in enumerate(text[start:], start):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    cards.append((match.group(1), text[start : index + 1]))
                    break
    return cards


def field(block: str, name: str) -> str:
    quoted = re.search(rf'(?m)^\s*{re.escape(name)}:\s*"((?:\\.|[^"\\])*)"', block)
    if quoted:
        return quoted.group(1).replace("\\n", " ").replace("<br>", " ")
    plain = re.search(rf"(?m)^\s*{re.escape(name)}:\s*(.+?)\s*$", block)
    if not plain:
        return ""
    value = plain.group(1).strip()
    if value in "{[":
        return ""
    return value.strip('"').replace("<br>", " ")


def norm_type(raw: str) -> str:
    key = (raw or "").strip().lower().replace("-", " ")
    aliases = {
        "the one ring": "THE_ONE_RING",
        "metasite": "METASITE",
        "meta site": "METASITE",
    }
    if key in aliases:
        return aliases[key]
    return re.sub(r"[^A-Za-z0-9]+", "_", (raw or "UNKNOWN").strip()).upper().strip("_") or "UNKNOWN"


def format_card_no(set_no: int, card_no: int) -> str:
    set_s = f"{set_no:02d}" if set_no < 10 else str(set_no)
    if card_no < 10:
        return f"{set_s}00{card_no}"
    if card_no < 100:
        return f"{set_s}0{card_no}"
    return f"{set_s}{card_no}"


def image_url(card_id: str, rel: str, maps: dict[str, str]) -> str:
    if card_id in maps:
        return maps[card_id]
    rel = (rel or "").strip()
    if rel.startswith("http"):
        return rel
    if rel.startswith("/gemp-lotr/"):
        rel = ""
    if rel.startswith("decipher/") or rel.startswith("sets/") or rel.startswith("hobbit/"):
        return CDN + rel
    if rel:
        return CDN + rel.lstrip("/")
    set_no_s, card_no_s = card_id.split("_", 1)
    return f"{CDN}decipher/LOTR{format_card_no(int(set_no_s), int(card_no_s))}.jpg"


def pile_region(group_id: str, left: str, top: str) -> dict:
    return {
        "direction": "horizontal",
        "groupId": group_id,
        "height": "12%",
        "left": left,
        "top": top,
        "type": "pile",
        "width": "7%",
    }


def row_region(group_id: str, top: str, height: str, left: str = "0%", width: str = "72%") -> dict:
    return {
        "cardSizeFactor": 0.75,
        "direction": "horizontal",
        "groupId": group_id,
        "height": height,
        "left": left,
        "top": top,
        "type": "free" if "Hand" not in group_id else "row",
        "width": width,
    }


def player_group(pid: str, kind: str, group_type: str, label: str) -> dict:
    other = "player2" if pid == "player1" else "player1"
    group: dict = {
        "groupType": group_type,
        "label": label,
        "tableLabel": label,
        "onCardEnter": {"controller": pid},
    }
    if kind == "Hand":
        group["onCardEnter"].update(
            {
                "currentSide": "B",
                "peeking": {pid: True},
                "rotation": 0,
                "rotationByPlayer": {},
            }
        )
    elif kind == "Deck":
        group["shuffleOnLoad"] = True
        group["onCardEnter"].update(
            {
                "deckGroupId": f"{pid}Deck",
                "discardGroupId": f"{pid}Discard",
                "peeking": {other: False},
            }
        )
    elif kind == "AdventureDeck":
        group["shuffleOnLoad"] = False
        group["onCardEnter"].update(
            {
                "deckGroupId": f"{pid}AdventureDeck",
                "discardGroupId": f"{pid}Discard",
                "peeking": {other: False},
            }
        )
    elif kind in {"Discard", "Dead"}:
        group["onCardEnter"].update(
            {
                "deckGroupId": f"{pid}Deck",
                "peeking": {pid: True, other: kind == "Dead"},
            }
        )
    elif group_type == "inPlay":
        group["onCardEnter"]["discardGroupId"] = f"{pid}Discard"
    return group


def cond_move(src: str, dest: str, n: int, empty_msg: str, ok_msg: str, dest_is_group: bool = True) -> list:
    move = ["MOVE_STACKS", src, dest, n, "top" if n == 1 else "bottom"]
    if n == 8:
        move[4] = "bottom"
    return [
        "COND",
        ["GROUP_NOT_EMPTY", src],
        [move, ["LOG", ok_msg]],
        ["true"],
        ["LOG", empty_msg],
    ]


def end_turn(next_player: str) -> dict:
    return {
        "args": [],
        "code": [
            ["VAR", "$HALT", False],
            ["VAR", "$STOP_STEP_ID", "1.0"],
            [
                "WHILE",
                ["NOT", "$HALT"],
                [
                    ["NEXT_STEP"],
                    ["VAR", "$STEP", "$GAME.stepId"],
                    ["COND", ["EQUAL", "$STEP", "$STOP_STEP_ID"], ["UPDATE_VAR", "$HALT", True]],
                ],
            ],
            ["LOG", "{{$ALIAS_N}} ended their turn. Fellowship phase — " + next_player + "."],
        ],
    }


def build_functions() -> dict:
    empty_deck = "{{$ALIAS_N}} draw deck is empty. Load a deck with Menu → Load or Builder."
    return {
        "functions": {
            "DRAW_ONE_CARD": {
                "args": [],
                "code": [cond_move("{{$PLAYER_N}}Deck", "{{$PLAYER_N}}Hand", 1, empty_deck, "{{$ALIAS_N}} drew 1 card.")],
            },
            "DRAW_STARTING_HAND": {
                "args": [],
                "code": [
                    cond_move(
                        "{{$PLAYER_N}}Deck",
                        "{{$PLAYER_N}}Hand",
                        8,
                        empty_deck,
                        "{{$ALIAS_N}} drew a starting hand of 8.",
                    )
                ],
            },
            "ADD_TWILIGHT": {
                "args": [],
                "code": [
                    [
                        "SET",
                        "/playerData/{{$PLAYER_N}}/twilight",
                        ["ADD", "$GAME.playerData.{{$PLAYER_N}}.twilight", 1],
                    ],
                    ["LOG", "{{$ALIAS_N}} added 1 twilight."],
                ],
            },
            "REMOVE_TWILIGHT": {
                "args": [],
                "code": [
                    [
                        "SET",
                        "/playerData/{{$PLAYER_N}}/twilight",
                        [
                            "COND",
                            ["GREATER_THAN", "$GAME.playerData.{{$PLAYER_N}}.twilight", 0],
                            ["ADD", "$GAME.playerData.{{$PLAYER_N}}.twilight", -1],
                            True,
                            0,
                        ],
                    ],
                    ["LOG", "{{$ALIAS_N}} removed 1 twilight."],
                ],
            },
            "DETACH": {
                "args": ["$CARD_ID"],
                "code": [
                    ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
                    [
                        "COND",
                        ["GREATER_THAN", "$CARD.cardIndex", 0],
                        [
                            ["MOVE_CARD", "$CARD.id", "$CARD.groupId", ["ADD", "$CARD.stackIndex", 1]],
                            ["LOG", "{{$ALIAS_N}} detached {{$CARD.currentFace.name}}."],
                        ],
                    ],
                ],
            },
            "FLIP": {
                "args": ["$CARD_ID"],
                "code": [
                    ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
                    [
                        "COND",
                        ["EQUAL", "$CARD.currentSide", "A"],
                        [
                            ["LOG", "{{$ALIAS_N}} flipped {{$CARD.currentFace.name}} facedown."],
                            ["SET", "/cardById/$CARD.id/currentSide", "B"],
                        ],
                        ["TRUE"],
                        [
                            ["SET", "/cardById/$CARD.id/currentSide", "A"],
                            ["LOG", "{{$ALIAS_N}} flipped {{$CARD.currentFace.name}} faceup."],
                        ],
                    ],
                ],
            },
            "SEND_TO_DISCARD": {
                "args": ["$CARD_ID"],
                "code": [
                    ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
                    ["MOVE_CARD", "$CARD.id", "{{$PLAYER_N}}Discard", 0, "top"],
                    ["LOG", "{{$ALIAS_N}} discarded {{$CARD.currentFace.name}}."],
                ],
            },
            "SEND_TO_DISCARD_CARD": {
                "args": [],
                "code": [
                    ["MOVE_CARD", "$ACTIVE_CARD_ID", "{{$PLAYER_N}}Discard", 0, "top"],
                    ["LOG", "{{$ALIAS_N}} discarded ", "$ACTIVE_FACE.name", "."],
                ],
            },
            "SEND_TO_DEAD": {
                "args": [],
                "code": [
                    ["MOVE_CARD", "$ACTIVE_CARD_ID", "{{$PLAYER_N}}Dead", 0, "top"],
                    ["LOG", "{{$ALIAS_N}} put ", "$ACTIVE_FACE.name", " in the dead pile."],
                ],
            },
            "SHUFFLE_INTO_DECK": {
                "args": ["$CARD_ID"],
                "code": [
                    ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
                    ["MOVE_CARD", "$CARD.id", "{{$PLAYER_N}}Deck", 0],
                    ["SHUFFLE_GROUP", "{{$PLAYER_N}}Deck"],
                    ["LOG", "{{$ALIAS_N}} shuffled {{$CARD.currentFace.name}} into their deck."],
                ],
            },
            "DECLARE_SKIRMISH": {
                "args": [],
                "code": [["LOG", "{{$ALIAS_N}} assigned a skirmish involving ", "$ACTIVE_FACE.name"]],
            },
            "LOG_ACTIVATION": {
                "args": [],
                "code": [["LOG", "{{$ALIAS_N}} used an ability of ", "$ACTIVE_FACE.name"]],
            },
            "P1END_TURN": end_turn("Player 2"),
            "P2END_TURN": end_turn("Player 1"),
            "P1START_TURN": {"args": [], "code": [["LOG", "{{$ALIAS_N}} started their turn (Fellowship)."]]},
            "P2START_TURN": {"args": [], "code": [["LOG", "{{$ALIAS_N}} started their turn (Fellowship)."]]},
        }
    }


def phase_text() -> list:
    steps = [
        ("1.0", "Fellowship", "Play companions/allies/possessions (pay twilight into the pool). T adds twilight. D draws. Arrow-Down for Shadow."),
        ("2.0", "Shadow", "Opponent plays minions to the shadow row, paying twilight from the pool. Arrow-Down for Maneuver."),
        ("3.0", "Maneuver", "Maneuver actions (both sides). Arrow-Down for Archery."),
        ("4.0", "Archery", "Count archery totals; wound that many characters. Arrow-Down for Assignment."),
        ("5.0", "Assignment", "Assign minions to companions (drag onto fellowship or log skirmish). Arrow-Down for Skirmish."),
        ("6.0", "Skirmish", "Resolve each skirmish: strength + wound loser. W wounds. Arrow-Down for Regroup."),
        ("7.0", "Regroup", "Reconcile, optional another Shadow round or End Turn (Used/discard cleanup). Arrow-Down for next Fellowship."),
    ]
    then: list = ["COND"]
    for step, fade, reminder in steps:
        then.extend(
            [
                ["EQUAL", "$GAME.stepId", step],
                [
                    ["FADE_TEXT_GAME", fade],
                    ["UPDATE_LAYOUT", "/layout/textBoxes/roundAdvancement/label", reminder],
                ],
            ]
        )
    return then


def build_groups() -> dict:
    groups: dict[str, dict] = {}
    for n in ("player1", "player2"):
        num = "1" if n == "player1" else "2"
        groups[f"{n}Hand"] = player_group(n, "Hand", "hand", f"Player {num} Hand")
        groups[f"{n}Fellowship"] = player_group(n, "Fellowship", "inPlay", f"Player {num} Fellowship")
        groups[f"{n}Support"] = player_group(n, "Support", "inPlay", f"Player {num} Support")
        groups[f"{n}Deck"] = player_group(n, "Deck", "deck", f"Player {num} Deck")
        groups[f"{n}Discard"] = player_group(n, "Discard", "discard", f"Player {num} Discard")
        groups[f"{n}Dead"] = player_group(n, "Dead", "discard", f"Player {num} Dead Pile")
        groups[f"{n}AdventureDeck"] = player_group(n, "AdventureDeck", "deck", f"Player {num} Adventure Deck")
    groups["sharedAdventurePath"] = {
        "groupType": "inPlay",
        "label": "Adventure Path",
        "tableLabel": "Adventure Path",
        "onCardEnter": {"controller": "shared"},
    }
    groups["sharedShadow"] = {
        "groupType": "inPlay",
        "label": "Shadow / Minions",
        "tableLabel": "Shadow / Minions",
        "onCardEnter": {"controller": "shared"},
    }
    groups["sharedSkirmish"] = {
        "groupType": "inPlay",
        "label": "Skirmish",
        "tableLabel": "Skirmish",
        "onCardEnter": {"controller": "shared"},
    }
    return {"groups": groups}


def build_layouts() -> dict:
    regions = {
        "player2Hand": {**row_region("player2Hand", "0%", "11%", width="58%"), "type": "row", "cardSizeFactor": 1},
        "player2Support": {**row_region("player2Support", "11%", "10%"), "style": {"background": "rgba(0,0,0,0.15)"}},
        "player2Fellowship": row_region("player2Fellowship", "21%", "13%"),
        "sharedAdventurePath": {
            **row_region("sharedAdventurePath", "34%", "10%"),
            "style": {"background": "rgba(0,0,0,0.3)"},
        },
        "sharedShadow": {
            **row_region("sharedShadow", "44%", "13%"),
            "style": {"background": "rgba(80,0,0,0.2)"},
        },
        "player1Fellowship": row_region("player1Fellowship", "57%", "13%"),
        "player1Support": {**row_region("player1Support", "70%", "10%"), "style": {"background": "rgba(0,0,0,0.15)"}},
        "player1Hand": {**row_region("player1Hand", "80%", "12%", width="58%"), "type": "row", "cardSizeFactor": 1},
        "sharedSkirmish": {
            "direction": "vertical",
            "groupId": "sharedSkirmish",
            "height": "50%",
            "left": "72.5%",
            "style": {"background": "rgba(0,0,0,0.3)"},
            "top": "25%",
            "type": "free",
            "width": "6%",
        },
        "player2Deck": pile_region("player2Deck", "58%", "0%"),
        "player2Discard": pile_region("player2Discard", "65%", "0%"),
        "player2Dead": pile_region("player2Dead", "72%", "0%"),
        "player2AdventureDeck": pile_region("player2AdventureDeck", "79%", "0%"),
        "player1Deck": pile_region("player1Deck", "58%", "88%"),
        "player1Discard": pile_region("player1Discard", "65%", "88%"),
        "player1Dead": pile_region("player1Dead", "72%", "88%"),
        "player1AdventureDeck": pile_region("player1AdventureDeck", "79%", "88%"),
    }
    return {
        "layouts": {
            "default": {
                "cardSize": 10,
                "chat": {"height": "40%", "left": "86%", "top": "30%", "width": "14%"},
                "regions": regions,
                "rowSpacing": 3,
                "tableButtons": {
                    "p1endTurnSuggestion": {
                        "actionList": ["P1END_TURN"],
                        "height": "4%",
                        "label": "P1 End Turn",
                        "left": "86%",
                        "top": "78%",
                        "visible": True,
                        "width": "13%",
                    },
                    "p1startTurn": {
                        "actionList": ["P1START_TURN"],
                        "height": "4%",
                        "label": "P1 Fellowship",
                        "left": "86%",
                        "top": "73%",
                        "visible": True,
                        "width": "13%",
                    },
                    "p2endTurnSuggestion": {
                        "actionList": ["P2END_TURN"],
                        "height": "4%",
                        "label": "P2 End Turn",
                        "left": "86%",
                        "top": "22%",
                        "visible": True,
                        "width": "13%",
                    },
                    "p2startTurn": {
                        "actionList": ["P2START_TURN"],
                        "height": "4%",
                        "label": "P2 Fellowship",
                        "left": "86%",
                        "top": "17%",
                        "visible": True,
                        "width": "13%",
                    },
                },
                "testBorders": False,
                "textBoxes": {
                    "roundAdvancement": {
                        "height": "3%",
                        "label": "Menu → Load a draw deck. Sites go on the adventure path. TAB for hotkeys.",
                        "left": "0%",
                        "top": "0%",
                        "visible": True,
                        "width": "86%",
                    }
                },
            }
        }
    }


def write_plugin_jsons() -> None:
    jsons = OUT / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    for name in COPY_AS_IS:
        shutil.copy2(SWCCG / "jsons" / name, jsons / name)

    dump_json(jsons / "groups.json", build_groups())
    dump_json(jsons / "layouts.json", build_layouts())
    dump_json(jsons / "functions.json", build_functions())

    phases = {
        name: {"height": "14.0%" if name == "Skirmish" else "10.0%", "label": f"id:{name}"}
        for name in ("Fellowship", "Shadow", "Maneuver", "Archery", "Assignment", "Skirmish", "Regroup")
    }
    dump_json(jsons / "phases.json", {"phases": phases})
    steps = {
        "1.0": {"label": "id:step-1.0", "phaseId": "Fellowship"},
        "2.0": {"label": "id:step-2.0", "phaseId": "Shadow"},
        "3.0": {"label": "id:step-3.0", "phaseId": "Maneuver"},
        "4.0": {"label": "id:step-4.0", "phaseId": "Archery"},
        "5.0": {"label": "id:step-5.0", "phaseId": "Assignment"},
        "6.0": {"label": "id:step-6.0", "phaseId": "Skirmish"},
        "7.0": {"label": "id:step-7.0", "phaseId": "Regroup"},
    }
    dump_json(jsons / "steps.json", {"steps": steps})

    types = {}
    for name in CATEGORIES:
        if name in {"SITE", "METASITE"}:
            types[name] = {"height": 0.72, "tokens": [], "width": 1}
        else:
            types[name] = {"height": 1, "tokens": [], "width": 0.72}
    dump_json(jsons / "cardTypes.json", {"cardTypes": types})
    dump_json(
        jsons / "cardBacks.json",
        {"cardBacks": {"normal": {"height": 1, "imageUrl": CARD_BACK, "width": 0.72}}},
    )
    dump_json(
        jsons / "playerProperties.json",
        {
            "playerProperties": {
                "twilight": {"default": 0, "label": "id:twilight", "min": 0, "type": "integer"}
            }
        },
    )
    dump_json(jsons / "gameProperties.json", load_json(SWCCG / "jsons" / "gameProperties.json"))
    dump_json(
        jsons / "topBarCounters.json",
        {
            "topBarCounters": {
                "player": [
                    {"imageUrl": CARD_BACK, "label": "id:twilight", "playerProperty": "twilight"}
                ],
                "shared": [{"gameProperty": "roundNumber", "imageUrl": "", "label": "Round"}],
            }
        },
    )
    clear_image_url_prefix(jsons)
    dump_json(
        jsons / "main.json",
        {
            "pluginName": "Lord of the Rings TCG",
            "author": "GEMP / lotrtcgpc.net",
            "defaultActions": [
                {
                    "actionList": "damageCard",
                    "condition": ["AND", ["EQUAL", "$ACTIVE_CARD.rotation", 0], "$ACTIVE_CARD.inPlay"],
                    "label": "id:damage",
                },
                {
                    "actionList": "damageCard",
                    "condition": ["AND", ["EQUAL", "$ACTIVE_CARD.rotation", 90], "$ACTIVE_CARD.inPlay"],
                    "label": "id:damage",
                },
            ],
            "announcements": [
                "Decipher LOTR TCG tabletop from GEMP card data. Not a rules engine.",
                "D draw · S starting hand · T/R twilight · W wound · L discard · K dead pile.",
                "Load draw deck to Deck. Sites go on the Adventure Path (or Adventure Deck first).",
            ],
            "playerCountMenu": [{"label": "2", "layoutId": "default", "numPlayers": 2}],
            "stepReminderRegex": [],
            "stepOrder": ["1.0", "2.0", "3.0", "4.0", "5.0", "6.0", "7.0"],
            "loadPreBuiltOnNewGame": False,
            "tutorialUrl": "https://wiki.lotrtcgpc.net/",
            "phaseOrder": ["Fellowship", "Shadow", "Maneuver", "Archery", "Assignment", "Skirmish", "Regroup"],
            "touchBar": [],
            "bannerUrl": toybox_url("lord-of-the-rings-ccg/_plugin/banner.jpg"),
            "logoUrl": toybox_url("lord-of-the-rings-ccg/_plugin/logo.jpg"),
            "clearTableOptions": load_json(SWCCG / "jsons" / "main.json")["clearTableOptions"],
            "closeRoomOptions": [
                {
                    "actionList": ["SET", "/victoryState", label],
                    "label": key,
                }
                for key, label in (
                    ("id:player1Victory", "Player1 LOTR TCG Win"),
                    ("id:player2Victory", "Player2 LOTR TCG Win"),
                    ("id:markasIncomplete", "Incomplete"),
                )
            ],
        },
    )
    dump_json(
        jsons / "hotkeys.json",
        {
            "hotkeys": {
                "card": [
                    {"actionList": ["FLIP", "$ACTIVE_CARD_ID"], "key": "F", "label": "Flip Card"},
                    {"actionList": ["DETACH", "$ACTIVE_CARD_ID"], "key": "C", "label": "Detach"},
                    {"actionList": ["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"], "key": "H", "label": "Shuffle Into Deck"},
                    {"actionList": ["SEND_TO_DISCARD", "$ACTIVE_CARD_ID"], "key": "L", "label": "Discard"},
                    {"actionList": ["SEND_TO_DEAD"], "key": "K", "label": "Dead Pile"},
                    {"actionList": "damageCard", "key": "W", "label": "Wound / Heal"},
                ],
                "game": [
                    {"actionList": ["DRAW_ONE_CARD"], "key": "D", "label": "Draw from Deck"},
                    {"actionList": ["DRAW_STARTING_HAND"], "key": "S", "label": "Draw starting hand (8)"},
                    {"actionList": ["ADD_TWILIGHT"], "key": "T", "label": "Add 1 twilight"},
                    {"actionList": ["REMOVE_TWILIGHT"], "key": "R", "label": "Remove 1 twilight"},
                ],
                "token": [],
            }
        },
    )
    dump_json(
        jsons / "groupMenu.json",
        {
            "groupMenu": {
                "moveToGroupIds": [
                    "playerNDeck",
                    "playerNDiscard",
                    "playerNDead",
                    "playerNHand",
                    "playerNAdventureDeck",
                    "playerNFellowship",
                    "playerNSupport",
                ],
                "options": [
                    {"actionList": "drawoneCard", "label": "id:drawonecard"},
                    {"actionList": "drawstartingHand", "label": "id:drawstartinghand"},
                    {"actionList": "menuAddTwilight", "label": "id:menuAddTwilight"},
                    {"actionList": "menuRemoveTwilight", "label": "id:menuRemoveTwilight"},
                ],
            }
        },
    )
    dump_json(
        jsons / "cardMenu.json",
        {
            "cardMenu": {
                "moveToGroupIds": [
                    "playerNDeck",
                    "playerNDiscard",
                    "playerNDead",
                    "playerNHand",
                    "playerNFellowship",
                    "playerNSupport",
                    "playerNAdventureDeck",
                ],
                "options": [
                    {"actionList": "menulog_activation", "label": "id:menulog_activation"},
                    {"actionList": "menu_declareskirmish", "label": "id:menu_declareskirmish"},
                    {"actionList": "damageCard", "label": "id:damage"},
                    {"actionList": "menusendcardtodiscard", "label": "id:sendcardtodiscard"},
                    {"actionList": "menusendcardtodead", "label": "id:sendcardtodead"},
                ],
                "suppress": ["Delete", "Toggle Trigger", "Set Rotation"],
            }
        },
    )
    dump_json(
        jsons / "actionLists.json",
        {
            "actionLists": {
                "damageCard": load_json(SWCCG / "jsons" / "actionLists.json")["actionLists"]["damageCard"],
                "drawoneCard": [["DRAW_ONE_CARD"]],
                "drawstartingHand": [["DRAW_STARTING_HAND"]],
                "menuAddTwilight": [["ADD_TWILIGHT"]],
                "menuRemoveTwilight": [["REMOVE_TWILIGHT"]],
                "menulog_activation": [["LOG_ACTIVATION"]],
                "menu_declareskirmish": [["DECLARE_SKIRMISH"]],
                "menusendcardtodiscard": [["SEND_TO_DISCARD_CARD"]],
                "menusendcardtodead": [["SEND_TO_DEAD"]],
                "flipCard": [["FLIP"]],
            }
        },
    )
    labels = {
        "twilight": {"English": "Twilight"},
        "damage": {"English": "•Wound / Heal"},
        "drawonecard": {"English": "•Draw 1"},
        "drawstartinghand": {"English": "•Draw starting hand (8)"},
        "menuAddTwilight": {"English": "•Add 1 twilight"},
        "menuRemoveTwilight": {"English": "•Remove 1 twilight"},
        "menulog_activation": {"English": "•Use ability"},
        "menu_declareskirmish": {"English": "•Log skirmish here"},
        "sendcardtodiscard": {"English": "•Discard"},
        "sendcardtodead": {"English": "•Dead pile"},
        "myDeck": {"English": "My Draw Deck"},
        "player1Victory": {"English": "Player 1 Win"},
        "player2Victory": {"English": "Player 2 Win"},
        "player1modifiedVictory": {"English": "Player 1 Modified Win"},
        "player2modifiedVictory": {"English": "Player 2 Modified Win"},
        "markasIncomplete": {"English": "Incomplete"},
        "Fellowship": {"English": "Fellowship"},
        "Shadow": {"English": "Shadow"},
        "Maneuver": {"English": "Maneuver"},
        "Archery": {"English": "Archery"},
        "Assignment": {"English": "Assignment"},
        "Skirmish": {"English": "Skirmish"},
        "Regroup": {"English": "Regroup"},
        "step-1.0": {"English": "1. FELLOWSHIP"},
        "step-2.0": {"English": "2. SHADOW"},
        "step-3.0": {"English": "3. MANEUVER"},
        "step-4.0": {"English": "4. ARCHERY"},
        "step-5.0": {"English": "5. ASSIGNMENT"},
        "step-6.0": {"English": "6. SKIRMISH"},
        "step-7.0": {"English": "7. REGROUP"},
    }
    dump_json(jsons / "labels.json", {"labels": labels})
    dump_json(
        jsons / "deckbuilder.json",
        {
            "deckbuilder": {
                "addButtons": [1],
                "colorKey": "culture",
                "colorValues": CULTURE_COLORS,
                "columns": [
                    {"label": "Name", "propName": "name"},
                    {"label": "Type", "propName": "type"},
                    {"label": "Culture", "propName": "culture"},
                    {"label": "Set", "propName": "packName"},
                    {"label": "Twilight", "propName": "twilight"},
                ],
                "spawnGroups": [{"label": "id:myDeck", "loadGroupId": "playerNDeck"}],
            }
        },
    )
    dump_json(
        jsons / "browse.json",
        {
            "browse": {
                "filterPropertySideA": "type",
                "filterValuesSideA": CATEGORIES,
                "textPropertiesSideA": ["name", "text", "lore", "subtitle"],
            }
        },
    )
    dump_json(
        jsons / "spawnExistingCardModal.json",
        {
            "spawnExistingCardModal": {
                "columnProperties": ["name", "type"],
                "loadGroupIds": [
                    "player1Deck",
                    "player1Fellowship",
                    "player1Support",
                    "player1AdventureDeck",
                    "sharedAdventurePath",
                    "sharedShadow",
                    "player2Deck",
                    "player2Fellowship",
                    "player2Support",
                    "player2AdventureDeck",
                    "sharedSkirmish",
                ],
            }
        },
    )
    dump_json(
        jsons / "prompts.json",
        {
            "prompts": {
                "welcome1": {
                    "args": [],
                    "message": (
                        "Lord of the Rings TCG (Decipher) on DragnCards, from GEMP card data. "
                        "This table is not rules-enforced. Load a draw deck onto Deck; put sites on the Adventure Path. "
                        "D draw, S starting hand (8), T/R twilight, W wound, L discard, K dead pile. TAB shows hotkeys. "
                        "Card data/art: GEMP / lotrtcgpc.net."
                    ),
                    "options": [{"hotkey": "K", "label": "OK"}],
                }
            }
        },
    )
    dump_json(
        jsons / "automation.json",
        {
            "automation": {
                "cards": {},
                "gameRules": {
                    "phaseText": {
                        "_comment": "Phase reminders",
                        "condition": True,
                        "inheritFrom": "stepTrigger",
                        "priority": 10,
                        "then": phase_text(),
                    },
                    "stepTrigger": {
                        "_comment": "Watch step changes",
                        "abstract": True,
                        "listenTo": ["/stepId"],
                        "type": "trigger",
                    },
                },
                "postLoadActionList": [["LOG", "{{$PLAYER_N}} loaded some cards."]],
                "postNewGameActionList": [
                    ["LOG", "A new game was created."],
                    ["PROMPT", "player1", "welcome1"],
                    ["PROMPT", "player2", "welcome1"],
                ],
            }
        },
    )


def build_tsv(maps: dict[str, str], set_names: dict[int, str]) -> tuple[list[str], list[list[str]], int]:
    header = [
        "databaseId",
        "name",
        "imageUrl",
        "cardBack",
        "type",
        "subtitle",
        "side",
        "culture",
        "race",
        "twilight",
        "strength",
        "vitality",
        "site",
        "packName",
        "rarity",
        "collInfo",
        "lore",
        "text",
    ]
    rows: list[list[str]] = []
    missing = 0
    seen: set[str] = set()
    for path in sorted(CARDS.rglob("*.hjson")):
        if "archive" in path.parts:
            continue
        for card_id, block in extract_objects(path.read_text(encoding="utf-8", errors="replace")):
            if card_id in seen:
                continue
            seen.add(card_id)
            set_no = int(card_id.split("_", 1)[0])
            rel = field(block, "image")
            url = image_url(card_id, rel, maps)
            if not url:
                missing += 1
            name = field(block, "title")
            subtitle = field(block, "subtitle")
            display = name if not subtitle else f"{name}, {subtitle}"
            rows.append(
                [
                    card_id,
                    cell(display),
                    url,
                    "normal",
                    norm_type(field(block, "type")),
                    cell(subtitle),
                    cell(field(block, "side")),
                    cell(field(block, "culture")),
                    cell(field(block, "race")),
                    cell(field(block, "twilight")),
                    cell(field(block, "strength")),
                    cell(field(block, "vitality")),
                    cell(field(block, "site")),
                    set_names.get(set_no, f"Set {set_no}"),
                    cell(field(block, "rarity")),
                    cell(field(block, "collInfo")),
                    cell(field(block, "lore")),
                    cell(field(block, "gametext")),
                ]
            )
    rows.sort(key=lambda r: (r[13], r[0]))
    return header, rows, missing


def main() -> int:
    if not CARDS.exists():
        raise SystemExit("GEMP LOTR cards folder not found")
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "tsvs").mkdir(parents=True)
    write_plugin_jsons()
    maps = parse_js_images(JS / "cards" / "CardImages.js", JS / "hobbit.js", JS / "PC_Cards.js")
    set_names = parse_set_names(SET_CONFIG)
    header, rows, missing = build_tsv(maps, set_names)
    tsv = OUT / "tsvs" / "cards.tsv"
    tsv.write_text("\n".join(["\t".join(header)] + ["\t".join(row) for row in rows]) + "\n", encoding="utf-8")
    decks = write_lotr_prebuilts(OUT)
    (OUT / "SOURCE.txt").write_text(
        "\n".join(
            [
                f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from GEMP-LOTR HJSON.",
                "Table follows GEMP: adventure path, fellowship, support, shadow, deck/discard/dead.",
                "Card data: gemp-lotr-cards/.../cards/**/*.hjson",
                "Art: CardImages.js / hobbit.js / PC_Cards.js + i.lotrtcgpc.net",
                "Author credit: GEMP / lotrtcgpc.net",
                "",
                "Tabletop plugin only — GEMP's Java rules engine is not ported.",
                f"TSV rows: {len(rows)}  cards missing a constructed image URL: {missing}",
                "Drop banner.jpg and logo.jpg into images/lord-of-the-rings-ccg/_plugin/.",
                "Prebuilts come from GEMP product/*Starters.hjson (sites → adventure deck).",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUT.name}")
    print("  pluginName: Lord of the Rings TCG")
    print(f"  tsv rows: {len(rows)}  js image overrides: {len(maps)}  missing urls: {missing}")
    print(f"  prebuilt decks: {decks['decks']}  missing card ids: {decks['missing']}")
    print()
    print("Next:")
    print("  python plugins/scripts/collect_hosted_images.py lotr-ccg-gemp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
