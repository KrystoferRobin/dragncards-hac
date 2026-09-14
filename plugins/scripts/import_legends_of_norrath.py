#!/usr/bin/env python3
"""Build a kitchen-table Legends of Norrath plugin from the client dump.

Prefers plugins/LoN/LegendsOfNorrath-RoF2 (full install). Leaves that folder as-is.

  plugins/legends-of-norrath/.venv/bin/python plugins/scripts/import_legends_of_norrath.py
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))
from image_names import TOYBOX_PREFIX, card_rel_path, stamp_lobby_art, toybox_url  # noqa: E402
from lackey_tabletop import (  # noqa: E402
    dump_json,
    group_types,
    region,
    sanitize,
    standard_actions,
    standard_functions,
    write_color_png,
    write_tsv,
)
from lon_catalog import (  # noqa: E402
    ARCHETYPE_FROM_PRODUCT,
    SET_NAMES,
    TYPE_TEMPLATES,
    apply_sets_from_decks,
    assign_ids,
    inflate_storage,
    parse_cards,
    parse_eqd_tokens,
    product_id_from_eqd,
    resolve_paths,
    set_from_product_id,
    slug,
)
from lon_compose import compose_card, extract_parts, load_portrait_index  # noqa: E402
from lon_fandom import apply_wiki, download_portraits, load_or_fetch  # noqa: E402

SOURCE = ROOT / "LoN"
OUT = ROOT / "legends-of-norrath"
IMAGES = ROOT / "images"
FOLDER = "legends-of-norrath"
PASCAL = "LegendsOfNorrath"
PLACEHOLDER_REL = f"{FOLDER}/missing/{PASCAL}-Missing-NoArt.png"

COLUMNS = [
    "databaseId",
    "name",
    "subtitle",
    "imageUrl",
    "zoomImageUrl",
    "cardBack",
    "type",
    "packName",
    "set",
    "loadGroupId",
    "archetype",
    "faction",
    "cost",
    "attack",
    "defense",
    "health",
    "damage",
    "level",
    "artId",
    "frame",
    "flavour",
    "text",
]

LOAD_GROUP = {
    "Avatar": "playerNAvatar",
    "Quest": "playerNQuests",
    "Ability": "playerNDeck",
    "Item": "playerNDeck",
    "Unit": "playerNDeck",
    "Tactic": "playerNDeck",
    "Card": "playerNDeck",
}

def player_groups(player: str) -> dict:
    number = player.replace("player", "")
    piles = [
        ("Deck", "Deck", "deck", "Deck", "Discard", False, "B"),
        ("Discard", "Discard", "discard", "Deck", "Discard", False, "A"),
        ("Hand", "Hand", "hand", "Deck", "Discard", False, "B"),
        ("Play", "Combat", "inPlay", "Deck", "Discard", True, "A"),
        ("Avatar", "Avatar", "inPlay", "Deck", "Discard", True, "A"),
        ("Abilities", "Abilities", "inPlay", "Deck", "Discard", True, "A"),
        ("Items", "Items", "inPlay", "Deck", "Discard", True, "A"),
        ("Quests", "Quests", "inPlay", "Deck", "Discard", True, "A"),
        ("Removed", "Removed", "aside", "Deck", "Discard", False, "A"),
    ]
    groups = {}
    for suffix, label, group_type, deck_suffix, discard_suffix, in_play, side in piles:
        enter = {
            "controller": player,
            "deckGroupId": f"{player}{deck_suffix}",
            "discardGroupId": f"{player}{discard_suffix}",
            "currentSide": side,
        }
        if in_play:
            enter["inPlay"] = True
        if suffix == "Hand":
            enter["peeking"] = {player: True}
        groups[f"{player}{suffix}"] = {
            "groupType": group_type,
            "label": f"Player {number} {label}",
            "tableLabel": label,
            "onCardEnter": enter,
        }
        if in_play:
            groups[f"{player}{suffix}"]["canHaveAttachments"] = True
    for index in range(1, 5):
        groups[f"{player}Quest{index}"] = {
            "groupType": "inPlay",
            "label": f"Player {number} Quest {index}",
            "tableLabel": f"Q{index}",
            "canHaveAttachments": True,
            "onCardEnter": {
                "controller": player,
                "deckGroupId": f"{player}Deck",
                "discardGroupId": f"{player}Discard",
                "currentSide": "A",
                "inPlay": True,
            },
        }
    return groups


def write_plugin_jsons(cards: list[dict[str, str]], decks: dict, menu: dict, backs: dict[str, str]) -> None:
    jsons = OUT / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    types = sorted({card["type"] for card in cards})
    dump_json(
        jsons / "main.json",
        {
            "pluginName": "Legends of Norrath",
            "author": "Hundred Acre Club / Sony Online Entertainment",
            "tutorialUrl": "",
            "announcements": [
                "SOE Legends of Norrath (the EQ CCG), May 2013 client through Debt of the Ratonga. Faces are composited from the client's frames + portraits + text. Shortcuts only. Drakkinshard is not in this dump.",
                "D draw. R ready all. S shuffle. E exert. U ready. X discard. Drop units onto quests. Power / Light / Shadow live in the top bar.",
            ],
            "loadPreBuiltOnNewGame": False,
            "backgroundUrl": toybox_url(f"{FOLDER}/_plugin/{PASCAL}-Background.jpg"),
        },
    )
    stamp_lobby_art(jsons, FOLDER)
    dump_json(jsons / "imageUrlPrefix.json", {"imageUrlPrefix": {"Default": TOYBOX_PREFIX}})
    dump_json(
        jsons / "cardBacks.json",
        {"cardBacks": {key: {"width": 0.72, "height": 1.0, "imageUrl": rel} for key, rel in backs.items()}},
    )
    dump_json(
        jsons / "cardTypes.json",
        {"cardTypes": {name: {"width": 0.72, "height": 1.0, "tokens": ["damage", "plus"]} for name in types}},
    )
    groups = {
        "sharedSetAside": {
            "groupType": "aside",
            "label": "Set Aside",
            "tableLabel": "Set Aside",
            "onCardEnter": {"controller": "shared"},
        }
    }
    for number in range(1, 5):
        groups.update(player_groups(f"player{number}"))
    dump_json(jsons / "groups.json", {"groups": groups})

    layout_regions = [
        ("playerLHand", "fan", "0%", "0%", "72%", "8%"),
        ("playerLAvatar", "row", "0%", "8%", "8%", "12%"),
        ("playerLAbilities", "fan", "8%", "8%", "18%", "12%"),
        ("playerLItems", "fan", "26%", "8%", "22%", "12%"),
        ("playerLPlay", "free", "48%", "8%", "24%", "12%"),
        ("playerLQuest1", "row", "0%", "20%", "12%", "14%"),
        ("playerLQuest2", "row", "12%", "20%", "12%", "14%"),
        ("playerLQuest3", "row", "24%", "20%", "12%", "14%"),
        ("playerLQuest4", "row", "36%", "20%", "12%", "14%"),
        ("playerLQuests", "pile", "48%", "20%", "8%", "14%"),
        ("playerSQuest1", "row", "0%", "42%", "12%", "16%"),
        ("playerSQuest2", "row", "12%", "42%", "12%", "16%"),
        ("playerSQuest3", "row", "24%", "42%", "12%", "16%"),
        ("playerSQuest4", "row", "36%", "42%", "12%", "16%"),
        ("playerSQuests", "pile", "48%", "42%", "8%", "16%"),
        ("playerSAvatar", "row", "0%", "58%", "8%", "14%"),
        ("playerSAbilities", "fan", "8%", "58%", "18%", "14%"),
        ("playerSItems", "fan", "26%", "58%", "22%", "14%"),
        ("playerSPlay", "free", "48%", "58%", "24%", "14%"),
        ("playerSHand", "fan", "0%", "82%", "72%", "17%"),
        ("playerLDeck", "pile", "75%", "8%", "8%", "12%"),
        ("playerLDiscard", "pile", "84%", "8%", "8%", "12%"),
        ("playerLRemoved", "pile", "93%", "8%", "6%", "12%"),
        ("playerSDeck", "pile", "75%", "58%", "8%", "14%"),
        ("playerSDiscard", "pile", "84%", "58%", "8%", "14%"),
        ("playerSRemoved", "pile", "93%", "58%", "6%", "14%"),
        ("sharedSetAside", "pile", "75%", "42%", "8%", "12%"),
    ]
    regions = {}
    for group_id, rtype, left, top, width, height in layout_regions:
        extra = {"disableDroppableAttachments": True} if rtype == "fan" else {}
        regions[group_id] = region(group_id, rtype, left, top, width, height, **extra)
    dump_json(
        jsons / "layouts.json",
        {
            "layouts": {
                "default": {
                    "cardSize": 9,
                    "rowSpacing": 1,
                    "chat": {"left": "75%", "top": "82%", "width": "24%", "height": "17%"},
                    "regions": regions,
                    "tableButtons": {
                        "drawDeck": {"actionList": "drawDeck", "label": "Draw", "left": "75%", "top": "28%", "width": "12%", "height": "3.4%"},
                        "readyAll": {"actionList": "readyAll", "label": "Ready", "left": "88%", "top": "28%", "width": "11%", "height": "3.4%"},
                        "shuffleDeck": {"actionList": "shuffleDeck", "label": "Shuffle", "left": "75%", "top": "32%", "width": "12%", "height": "3.4%"},
                    },
                }
            }
        },
    )
    typed = group_types()
    typed["inPlay"]["onCardEnter"]["currentSide"] = "A"
    typed["hand"]["onCardEnter"]["currentSide"] = "B"
    dump_json(jsons / "groupTypes.json", {"groupTypes": typed})
    dump_json(jsons / "playerCountMenu.json", {"playerCountMenu": [{"label": "2", "numPlayers": 2, "layoutId": "default"}]})
    phases = [("ready", "Ready"), ("quest", "Quest"), ("main", "Main"), ("combat", "Combat"), ("end", "End")]
    dump_json(
        jsons / "phases.json",
        {"phases": {key: {"label": label, "height": "20%"} for key, label in phases}, "phaseOrder": [key for key, _ in phases]},
    )
    dump_json(
        jsons / "steps.json",
        {
            "steps": {f"{key}Step": {"phaseId": key, "label": label} for key, label in phases},
            "stepOrder": [f"{key}Step" for key, _ in phases],
        },
    )
    dump_json(
        jsons / "playerProperties.json",
        {
            "playerProperties": {
                "power": {"label": "Power", "type": "integer", "default": 0, "min": 0},
                "light": {"label": "Light", "type": "integer", "default": 0, "min": 0},
                "shadow": {"label": "Shadow", "type": "integer", "default": 0, "min": 0},
            }
        },
    )
    dump_json(jsons / "gameProperties.json", {"gameProperties": {}})
    dump_json(
        jsons / "topBarCounters.json",
        {
            "topBarCounters": {
                "shared": [{"label": "Round", "imageUrl": "", "gameProperty": "roundNumber"}],
                "player": [
                    {"label": "Power", "imageUrl": "", "playerProperty": "power"},
                    {"label": "Light", "imageUrl": "", "playerProperty": "light"},
                    {"label": "Shadow", "imageUrl": "", "playerProperty": "shadow"},
                ],
            }
        },
    )
    dump_json(
        jsons / "tokens.json",
        {
            "tokens": {
                "plus": {
                    "label": "+1",
                    "left": "72%",
                    "top": "4%",
                    "width": "4vh",
                    "height": "4vh",
                    "imageUrl": toybox_url(f"{FOLDER}/_plugin/{PASCAL}-TokenPlus.png"),
                    "canBeNegative": True,
                },
                "damage": {
                    "label": "Damage",
                    "left": "50%",
                    "top": "4%",
                    "width": "4vh",
                    "height": "4vh",
                    "imageUrl": toybox_url(f"{FOLDER}/_plugin/{PASCAL}-TokenDamage.png"),
                    "canBeNegative": False,
                },
            }
        },
    )
    dump_json(jsons / "functions.json", {"functions": standard_functions()})
    actions = standard_actions(draw_group="Deck")
    dump_json(jsons / "actionLists.json", {"actionLists": actions})
    dump_json(
        jsons / "hotkeys.json",
        {
            "hotkeys": {
                "game": [
                    {"key": "D", "actionList": "drawDeck", "label": "Draw"},
                    {"key": "R", "actionList": "readyAll", "label": "Ready all"},
                    {"key": "S", "actionList": "shuffleDeck", "label": "Shuffle"},
                ],
                "card": [
                    {"key": "E", "actionList": "spendCard", "label": "Exert"},
                    {"key": "U", "actionList": "readyCard", "label": "Ready"},
                    {"key": "F", "actionList": "flipCard", "label": "Flip"},
                    {"key": "X", "actionList": "discardCard", "label": "Discard"},
                    {"key": "A", "actionList": "detachCard", "label": "Detach"},
                ],
                "token": [
                    {"key": "1", "tokenType": "plus", "label": "+1"},
                    {"key": "2", "tokenType": "damage", "label": "Damage"},
                ],
            }
        },
    )
    dump_json(
        jsons / "pluginMenu.json",
        {
            "pluginMenu": {
                "options": [
                    {"label": "Draw", "actionList": "drawDeck"},
                    {"label": "Ready all", "actionList": "readyAll"},
                    {"label": "Shuffle deck", "actionList": "shuffleDeck"},
                ]
            }
        },
    )
    moves = [
        "playerNPlay",
        "playerNAvatar",
        "playerNAbilities",
        "playerNItems",
        "playerNQuest1",
        "playerNQuest2",
        "playerNQuest3",
        "playerNQuest4",
        "playerNQuests",
        "playerNHand",
        "playerNDeck",
        "playerNDiscard",
        "playerNRemoved",
        "sharedSetAside",
    ]
    dump_json(
        jsons / "cardMenu.json",
        {
            "cardMenu": {
                "moveToGroupIds": moves,
                "options": [
                    {"label": "Exert", "actionList": "spendCard"},
                    {"label": "Ready", "actionList": "readyCard"},
                    {"label": "Flip", "actionList": "flipCard"},
                    {"label": "Discard", "actionList": "discardCard"},
                    {"label": "Detach", "actionList": "detachCard"},
                ],
            }
        },
    )
    dump_json(jsons / "groupMenu.json", {"groupMenu": {"moveToGroupIds": moves, "options": []}})
    dump_json(
        jsons / "browse.json",
        {
            "browse": {
                "filterPropertySideA": "type",
                "filterValuesSideA": types,
                "textPropertiesSideA": ["name", "subtitle", "type", "packName", "archetype", "text"],
            }
        },
    )
    dump_json(
        jsons / "deckbuilder.json",
        {
            "deckbuilder": {
                "addButtons": [1, 2, 3, 4],
                "columns": [
                    {"propName": "name", "label": "Name"},
                    {"propName": "subtitle", "label": "Subtitle"},
                    {"propName": "type", "label": "Type"},
                    {"propName": "archetype", "label": "Archetype"},
                    {"propName": "attack", "label": "ATK"},
                    {"propName": "defense", "label": "DEF"},
                    {"propName": "health", "label": "HP"},
                    {"propName": "cost", "label": "Cost"},
                    {"propName": "packName", "label": "Set"},
                ],
                "spawnGroups": [
                    {"loadGroupId": "playerNDeck", "label": "My Deck"},
                    {"loadGroupId": "playerNHand", "label": "My Hand"},
                    {"loadGroupId": "playerNAvatar", "label": "My Avatar"},
                    {"loadGroupId": "playerNQuest1", "label": "My Quest 1"},
                    {"loadGroupId": "playerNQuest2", "label": "My Quest 2"},
                    {"loadGroupId": "playerNQuest3", "label": "My Quest 3"},
                    {"loadGroupId": "playerNQuest4", "label": "My Quest 4"},
                    {"loadGroupId": "playerNAbilities", "label": "My Abilities"},
                    {"loadGroupId": "playerNItems", "label": "My Items"},
                    {"loadGroupId": "playerNPlay", "label": "My Combat"},
                ],
            }
        },
    )
    dump_json(
        jsons / "spawnExistingCardModal.json",
        {
            "spawnExistingCardModal": {
                "columnProperties": ["name", "type", "archetype", "faction", "attack", "health", "packName"],
                "loadGroupIds": [
                    "player1Deck",
                    "player1Hand",
                    "player1Avatar",
                    "player1Quest1",
                    "player1Quest2",
                    "player1Quest3",
                    "player1Quest4",
                    "player1Abilities",
                    "player1Items",
                    "player1Play",
                ],
            }
        },
    )
    face = {
        "zoomImageUrl": {"label": "Preview art", "type": "string", "default": ""},
        "subtitle": {"label": "Subtitle", "type": "string", "default": ""},
        "archetype": {"label": "Archetype", "type": "string", "default": ""},
        "faction": {"label": "Faction", "type": "string", "default": ""},
        "cost": {"label": "Cost", "type": "string", "default": ""},
        "attack": {"label": "Attack", "type": "string", "default": ""},
        "defense": {"label": "Defense", "type": "string", "default": ""},
        "health": {"label": "Health", "type": "string", "default": ""},
        "damage": {"label": "Damage", "type": "string", "default": ""},
        "level": {"label": "Level", "type": "string", "default": ""},
        "artId": {"label": "Art id", "type": "string", "default": ""},
        "frame": {"label": "Frame", "type": "string", "default": ""},
        "flavour": {"label": "Flavor", "type": "string", "default": ""},
        "text": {"label": "Text", "type": "string", "default": ""},
        "packName": {"label": "Set", "type": "string", "default": ""},
        "set": {"label": "Set code", "type": "string", "default": ""},
        "loadGroupId": {"label": "Load group", "type": "string", "default": ""},
    }
    dump_json(jsons / "faceProperties.json", {"faceProperties": face})
    dump_json(jsons / "cardProperties.json", {"cardProperties": {}})
    dump_json(jsons / "defaultActions.json", {"defaultActions": []})
    dump_json(
        jsons / "automation.json",
        {
            "automation": {
                "postNewGameActionList": [
                    ["LOG", "Legends of Norrath table created. Load an Oathbound starter or build a 50-card deck plus avatar and four quests. No rules are enforced."]
                ],
                "postLoadActionList": [
                    ["SHUFFLE_GROUP", "{{$PLAYER_N}}Deck"],
                    [
                        "COND",
                        ["GROUP_EMPTY", "{{$PLAYER_N}}Deck"],
                        ["LOG", "{{$ALIAS_N}} has an empty deck."],
                        ["TRUE"],
                        [["MOVE_STACKS", "{{$PLAYER_N}}Deck", "{{$PLAYER_N}}Hand", 5, "bottom"]],
                    ],
                    ["LOG", "{{$ALIAS_N}} shuffled and drew five."],
                ],
                "gameRules": {},
            }
        },
    )
    dump_json(jsons / "labels.json", {"labels": {}})
    dump_json(jsons / "preferences.json", {"preferences": {"game": [], "player": []}})
    dump_json(jsons / "prompts.json", {"prompts": {}})
    dump_json(jsons / "touchBar.json", {"touchBar": []})
    dump_json(jsons / "closeRoomOptions.json", {"closeRoomOptions": [{"label": "Just close", "actionList": []}]})
    dump_json(
        jsons / "clearTableOptions.json",
        {
            "clearTableOptions": [
                {"label": "Player 1 wins", "actionList": ["SET", "/victoryState", "player1Win"]},
                {"label": "Player 2 wins", "actionList": ["SET", "/victoryState", "player2Win"]},
                {"label": "Tie", "actionList": ["SET", "/victoryState", "tie"]},
                {"label": "Incomplete", "actionList": ["SET", "/victoryState", "incomplete"]},
            ]
        },
    )
    dump_json(jsons / "preBuiltDecks.json", decks)
    dump_json(jsons / "deckMenu.json", menu)


def write_plugin_art(paths: dict[str, Path]) -> dict[str, str]:
    from lon_compose import iter_rcc_files, read_rcc_blob

    plugin = IMAGES / FOLDER / "_plugin"
    plugin.mkdir(parents=True, exist_ok=True)
    raw, files = next(iter_rcc_files(paths["resources_rcc"]))
    for rel, data_off, data_rel in files:
        name = Path(rel).name.lower()
        if name in {"lobby_background.jpg", "background.jpg"}:
            blob = read_rcc_blob(raw, data_off, data_rel)
            (plugin / "banner2.jpg").write_bytes(blob)
            (plugin / f"{PASCAL}-Background.jpg").write_bytes(blob)
            (plugin / "logo2.jpg").write_bytes(blob)
            break
    write_color_png(plugin / f"{PASCAL}-CardbackDefault.png", (28, 42, 32), size=96)
    write_color_png(IMAGES / PLACEHOLDER_REL, (36, 28, 22), size=96)
    write_color_png(plugin / f"{PASCAL}-TokenPlus.png", (48, 160, 72))
    write_color_png(plugin / f"{PASCAL}-TokenDamage.png", (196, 48, 48))
    return {"default": f"{FOLDER}/_plugin/{PASCAL}-CardbackDefault.png"}


def official_decks(cards: list[dict[str, str]], decks_dir: Path) -> tuple[dict, dict]:
    by_obj: dict[str, dict[str, str]] = {}
    for card in cards:
        own = card.get("ownId") or ""
        if own and own not in TYPE_TEMPLATES:
            by_obj[own] = card
        for obj_id in card.get("objIds") or []:
            if obj_id and obj_id not in TYPE_TEMPLATES:
                by_obj.setdefault(obj_id, card)
    prebuilts: dict[str, dict] = {}
    menus: dict[str, list] = defaultdict(list)
    seen_named = False
    for path in sorted(decks_dir.glob("*.eqd")):
        if path.stem[0].isalpha():
            if seen_named:
                continue
            pid = 1_900_000 + {"FighterStarter": 2, "MageStarter": 3, "PriestStarter": 4, "ScoutStarter": 5}.get(path.stem, 2)
        else:
            seen_named = True
            pid = product_id_from_eqd(path) or 0
        set_no = set_from_product_id(pid) if pid else 1
        set_name = SET_NAMES.get(set_no, f"Set {set_no}")
        arch = ARCHETYPE_FROM_PRODUCT.get(pid % 10, "")
        deck_counts, avatar_id, quest_ids = parse_eqd_tokens(path)
        rows = []
        avatar = by_obj.get(avatar_id)
        avatar_name = avatar["name"] if avatar else path.stem
        if avatar:
            rows.append({"databaseId": avatar["databaseId"], "quantity": 1, "loadGroupId": "playerNAvatar"})
        deck_n = 0
        unmatched = 0
        for obj_id, qty in deck_counts.items():
            card = by_obj.get(obj_id)
            if not card:
                unmatched += 1
                continue
            rows.append({"databaseId": card["databaseId"], "quantity": qty, "loadGroupId": "playerNDeck"})
            deck_n += qty
        quests = 0
        for index, obj_id in enumerate(quest_ids, start=1):
            card = by_obj.get(obj_id)
            if not card:
                unmatched += 1
                continue
            card["type"] = "Quest"
            card["loadGroupId"] = "playerNQuests"
            rows.append({"databaseId": card["databaseId"], "quantity": 1, "loadGroupId": f"playerNQuest{index}"})
            quests += 1
        label = f"{set_name} {arch or path.stem} — {avatar_name}".strip()
        deck_id = slug(f"{set_name}-{arch or path.stem}-{avatar_name}")
        if deck_id in prebuilts:
            deck_id = f"{deck_id}-{pid}"
        prebuilts[deck_id] = {"label": label, "cards": rows}
        menus[set_name].append({"deckListId": deck_id, "label": f"{arch or path.stem} — {avatar_name}"})
        print(f"  {path.name}: {label} deck={deck_n} quests={quests} unmatched={unmatched}")
    menu = {
        "deckMenu": {
            "subMenus": [
                {"label": set_name, "deckLists": menus[set_name]}
                for set_name in sorted(menus, key=lambda name: next((num for num, label in SET_NAMES.items() if label == name), 99))
            ]
        }
    }
    return {"preBuiltDecks": prebuilts}, menu


def main() -> None:
    paths = resolve_paths(SOURCE)
    if not paths["storage"].exists():
        raise SystemExit(f"Missing {paths['storage']}")
    print(f"Catalog from {paths['label']}: {paths['storage']}")
    records = inflate_storage(paths["storage"])
    print(f"  {len(records)} objects")
    cards = parse_cards(records)
    apply_sets_from_decks(cards, paths["decks"])
    assign_ids(cards)
    for card in cards:
        card["set"] = card.get("setNumber") or ""
        card["loadGroupId"] = LOAD_GROUP.get(card["type"], "playerNDeck")
    print(f"  {len(cards)} unique cards  {Counter(card['type'] for card in cards)}")
    print(f"  sets {Counter(card['packName'] for card in cards)}")

    wiki_dir = IMAGES / FOLDER / "_wiki"
    wiki = load_or_fetch(wiki_dir)
    wiki_art = download_portraits(wiki, wiki_dir / "portraits")
    wiki_stats = apply_wiki(cards, wiki, wiki_art)
    print(f"  fandom matched={wiki_stats['matched']} art={wiki_stats['art']} cost+={wiki_stats['filled_cost']} set+={wiki_stats['filled_set']} atk≠{wiki_stats['atk_mismatches']}")
    for line in wiki_stats.get("mismatch_samples") or []:
        print(f"    {line}")

    decks, menu = official_decks(cards, paths["decks"])
    backs = write_plugin_art(paths)

    print("Extracting frames / fonts / portrait index…")
    parts_dir = IMAGES / FOLDER / "_parts"
    parts = extract_parts(paths["cards_rcc"], parts_dir, paths.get("resources_rcc"))
    portraits = load_portrait_index(parts_dir)
    rcc_raw = paths["cards_rcc"].read_bytes()
    print(f"  parts {len(parts)}  portraits {len(portraits)}")

    used: dict[str, int] = {}
    composed = 0
    for card in cards:
        set_name = card.get("packName") or "Norrath"
        planned = card_rel_path(FOLDER, PASCAL, set_name, card["name"], ".jpg")
        key = planned.casefold()
        used[key] = used.get(key, 0) + 1
        if used[key] > 1:
            path = Path(planned)
            planned = path.with_name(f"{path.stem}-{used[key]}{path.suffix}").as_posix()
        dest = IMAGES / planned
        try:
            compose_card(card, dest, parts, rcc_raw, portraits)
            rel = planned
            composed += 1
        except Exception as exc:
            print(f"  compose failed {card['name']}: {exc}")
            rel = PLACEHOLDER_REL
        card["imageUrl"] = rel
        card["zoomImageUrl"] = rel
        card["cardBack"] = "default"

    tsv_cards = [{col: sanitize(str(card.get(col, ""))) for col in COLUMNS} for card in cards]
    write_tsv(tsv_cards, COLUMNS, OUT / "tsvs" / "cards.tsv")
    write_plugin_jsons(cards, decks, menu, backs)
    (OUT / "SOURCE.txt").write_text(
        "\n".join(
            [
                f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from {paths['label']}.",
                "RoF2 is the same May 2013 catalog, laid out as a real install (data/archetypes, data/decks, locale).",
                "Cards are composited: cream text box, cost/class icons, RCC or lon.fandom.com portraits, Vera, official stat icons.",
                "Leave plugins/LoN as-is. Drop newer extracts in plugins/LoN/<name>/.",
                f"Cards: {len(cards)}  Composed: {composed}  Official decks: {len(decks['preBuiltDecks'])}",
                f"Fandom: {wiki_stats}",
                f"Types: {dict(Counter(card['type'] for card in cards))}",
                f"Sets: {dict(Counter(card['packName'] for card in cards))}",
                "Tabletop plugin only — no rules engine. Wiki has a few Drakkinshard stubs; this client dump does not.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUT}  composed={composed} decks={len(decks['preBuiltDecks'])}")


if __name__ == "__main__":
    main()


