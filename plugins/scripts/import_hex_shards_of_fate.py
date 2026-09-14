#!/usr/bin/env python3
"""Build a kitchen-table HEX: Shards of Fate plugin from the final client.

  plugins/hex-shards-of-fate/.venv/bin/python plugins/scripts/import_hex_shards_of_fate.py
  plugins/hex-shards-of-fate/.venv/bin/python plugins/scripts/import_hex_shards_of_fate.py --compare-browser
  plugins/hex-shards-of-fate/.venv/bin/python plugins/scripts/import_hex_shards_of_fate.py --faces-only
  plugins/hex-shards-of-fate/.venv/bin/python plugins/scripts/import_hex_shards_of_fate.py --faces-only --limit 20
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))
from hex_art import extract_portraits  # noqa: E402
from hex_browser import compare_browser  # noqa: E402
from hex_catalog import (  # noqa: E402
    CONSTRUCTED_ORDER,
    assign_ids,
    load_gamedata,
    parse_cards,
    parse_champions,
    parse_decks,
    parse_sets,
    resolve_hex,
    set_sort_key,
    slug,
    summarize,
)
from hex_compose import compose_back, compose_lobby  # noqa: E402
from hex_mse_style import stamp_jobs  # noqa: E402
from hex_rules import load_keywords, reminder_glossary, rules_cards, write_rules_md  # noqa: E402
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

OUT = ROOT / "hex-shards-of-fate"
IMAGES = ROOT / "images"
FOLDER = "hex-shards-of-fate"
PASCAL = "HexShardsOfFate"
PLACEHOLDER_REL = f"{FOLDER}/missing/{PASCAL}-Missing-NoArt.jpg"

def pretty_deck_name(name: str) -> str:
    label = name.replace("_", " ").replace("StarterDeck", "Starter: ").replace("Starter ", "Starter: ")
    label = label.replace("AI Tourney ", "Tourney ")
    return " ".join(label.split())


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
    "faction",
    "rarity",
    "cost",
    "threshold",
    "attack",
    "defense",
    "health",
    "artist",
    "flavour",
    "text",
]


def player_groups(player: str) -> dict:
    number = player.replace("player", "")
    piles = [
        ("Deck", "Deck", "deck", "Deck", "Crypt", False, "B"),
        ("Crypt", "Crypt", "discard", "Deck", "Crypt", False, "A"),
        ("Hand", "Hand", "hand", "Deck", "Crypt", False, "B"),
        ("Champion", "Champion", "inPlay", "Deck", "Crypt", True, "A"),
        ("Resources", "Resources", "inPlay", "Deck", "Crypt", True, "A"),
        ("Play", "Troops", "inPlay", "Deck", "Crypt", True, "A"),
        ("Support", "Support", "inPlay", "Deck", "Crypt", True, "A"),
        ("Void", "Void", "aside", "Deck", "Crypt", False, "A"),
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
    return groups


def write_plugin_jsons(
    cards: list[dict[str, str]],
    decks: dict,
    menu: dict,
    backs: dict[str, str],
    keywords: list[tuple[str, str]] | None = None,
) -> None:
    jsons = OUT / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    types = sorted({card["type"] for card in cards})
    dump_json(
        jsons / "main.json",
        {
            "pluginName": "HEX: Shards of Fate",
            "author": "Hundred Acre Club / Cryptozoic",
            "tutorialUrl": "",
            "announcements": [
                "HEX: Shards of Fate, final client 1.1.0.086. Faces stamped from client chrome + portraits. Shortcuts only.",
                "D draw. R ready all. S shuffle. E exhaust. U ready. X crypt. V void. Champion / Resources / Troops / Support.",
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
        {"cardTypes": {name: {"width": 0.72, "height": 1.0, "tokens": ["plus", "damage"]} for name in types}},
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
        ("playerLChampion", "row", "0%", "8%", "8%", "12%"),
        ("playerLResources", "fan", "8%", "8%", "28%", "12%"),
        ("playerLSupport", "fan", "36%", "8%", "20%", "12%"),
        ("playerLPlay", "free", "56%", "8%", "16%", "12%"),
        ("playerSChampion", "row", "0%", "58%", "8%", "14%"),
        ("playerSResources", "fan", "8%", "58%", "28%", "14%"),
        ("playerSSupport", "fan", "36%", "58%", "20%", "14%"),
        ("playerSPlay", "free", "56%", "58%", "16%", "14%"),
        ("playerSHand", "fan", "0%", "82%", "72%", "17%"),
        ("playerLDeck", "pile", "75%", "8%", "8%", "12%"),
        ("playerLCrypt", "pile", "84%", "8%", "8%", "12%"),
        ("playerLVoid", "pile", "93%", "8%", "6%", "12%"),
        ("playerSDeck", "pile", "75%", "58%", "8%", "14%"),
        ("playerSCrypt", "pile", "84%", "58%", "8%", "14%"),
        ("playerSVoid", "pile", "93%", "58%", "6%", "14%"),
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
    phases = [("ready", "Ready"), ("resource", "Resource"), ("draw", "Draw"), ("main", "Main"), ("end", "End")]
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
        {"playerProperties": {"health": {"label": "Health", "type": "integer", "default": 20, "min": 0}}},
    )
    dump_json(jsons / "gameProperties.json", {"gameProperties": {}})
    dump_json(
        jsons / "topBarCounters.json",
        {
            "topBarCounters": {
                "shared": [{"label": "Round", "imageUrl": "", "gameProperty": "roundNumber"}],
                "player": [{"label": "Health", "imageUrl": "", "playerProperty": "health"}],
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
    actions["voidCard"] = [
        ["MOVE_CARD", "$ACTIVE_CARD_ID", "{{$PLAYER_N}}Void", 0],
        ["LOG", "{{$ALIAS_N}} voided {{$ACTIVE_FACE.name}}."],
    ]
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
                    {"key": "E", "actionList": "spendCard", "label": "Exhaust"},
                    {"key": "U", "actionList": "readyCard", "label": "Ready"},
                    {"key": "F", "actionList": "flipCard", "label": "Flip"},
                    {"key": "X", "actionList": "discardCard", "label": "Crypt"},
                    {"key": "V", "actionList": "voidCard", "label": "Void"},
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
        "playerNChampion",
        "playerNResources",
        "playerNSupport",
        "playerNHand",
        "playerNDeck",
        "playerNCrypt",
        "playerNVoid",
        "sharedSetAside",
    ]
    dump_json(
        jsons / "cardMenu.json",
        {
            "cardMenu": {
                "moveToGroupIds": moves,
                "options": [
                    {"label": "Exhaust", "actionList": "spendCard"},
                    {"label": "Ready", "actionList": "readyCard"},
                    {"label": "Flip", "actionList": "flipCard"},
                    {"label": "Crypt", "actionList": "discardCard"},
                    {"label": "Void", "actionList": "voidCard"},
                    {"label": "Detach", "actionList": "detachCard"},
                ],
            }
        },
    )
    dump_json(jsons / "groupMenu.json", {"groupMenu": {"moveToGroupIds": moves, "options": []}})
    sets = sorted({card["packName"] for card in cards}, key=set_sort_key)
    dump_json(
        jsons / "browse.json",
        {
            "browse": {
                "filterPropertySideA": "packName",
                "filterValuesSideA": sets,
                "textPropertiesSideA": ["name", "subtitle", "type", "threshold", "text"],
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
                    {"propName": "type", "label": "Type"},
                    {"propName": "cost", "label": "Cost"},
                    {"propName": "threshold", "label": "Threshold"},
                    {"propName": "attack", "label": "ATK"},
                    {"propName": "defense", "label": "DEF"},
                    {"propName": "packName", "label": "Set"},
                ],
                "spawnGroups": [
                    {"loadGroupId": "playerNDeck", "label": "My Deck"},
                    {"loadGroupId": "playerNHand", "label": "My Hand"},
                    {"loadGroupId": "playerNChampion", "label": "My Champion"},
                    {"loadGroupId": "playerNResources", "label": "My Resources"},
                    {"loadGroupId": "playerNPlay", "label": "My Troops"},
                    {"loadGroupId": "playerNSupport", "label": "My Support"},
                ],
            }
        },
    )
    dump_json(
        jsons / "spawnExistingCardModal.json",
        {
            "spawnExistingCardModal": {
                "columnProperties": ["name", "type", "cost", "threshold", "attack", "defense", "packName"],
                "loadGroupIds": [
                    "player1Deck",
                    "player1Hand",
                    "player1Champion",
                    "player1Resources",
                    "player1Play",
                    "player1Support",
                ],
            }
        },
    )
    face = {
        "zoomImageUrl": {"label": "Preview art", "type": "string", "default": ""},
        "subtitle": {"label": "Subtitle", "type": "string", "default": ""},
        "faction": {"label": "Faction", "type": "string", "default": ""},
        "rarity": {"label": "Rarity", "type": "string", "default": ""},
        "cost": {"label": "Cost", "type": "string", "default": ""},
        "threshold": {"label": "Threshold", "type": "string", "default": ""},
        "attack": {"label": "Attack", "type": "string", "default": ""},
        "defense": {"label": "Defense", "type": "string", "default": ""},
        "health": {"label": "Health", "type": "string", "default": ""},
        "artist": {"label": "Artist", "type": "string", "default": ""},
        "flavour": {"label": "Flavor", "type": "string", "default": ""},
        "text": {"label": "Text", "type": "string", "default": ""},
        "packName": {"label": "Set", "type": "string", "default": ""},
        "set": {"label": "Set code", "type": "string", "default": ""},
        "loadGroupId": {"label": "Load group", "type": "string", "default": ""},
    }
    dump_json(jsons / "faceProperties.json", {"faceProperties": face})
    dump_json(jsons / "cardProperties.json", {"cardProperties": {}})
    if keywords:
        dump_json(jsons / "keywordReminders.json", {"keywordReminders": reminder_glossary(keywords)})
    dump_json(jsons / "defaultActions.json", {"defaultActions": []})
    dump_json(
        jsons / "automation.json",
        {
            "automation": {
                "postNewGameActionList": [
                    [
                        "LOG",
                        "HEX table created. Load a starter or a 60-card deck plus a champion. Health starts at 20. No rules are enforced.",
                    ]
                ],
                "postLoadActionList": [
                    ["SHUFFLE_GROUP", "{{$PLAYER_N}}Deck"],
                    [
                        "COND",
                        ["GROUP_EMPTY", "{{$PLAYER_N}}Deck"],
                        ["LOG", "{{$ALIAS_N}} has an empty deck."],
                        ["TRUE"],
                        [["MOVE_STACKS", "{{$PLAYER_N}}Deck", "{{$PLAYER_N}}Hand", 7, "bottom"]],
                    ],
                    ["LOG", "{{$ALIAS_N}} shuffled and drew seven."],
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


def official_decks(cards: list[dict[str, str]], deck_rows: list[dict]) -> tuple[dict, dict]:
    by_guid = {card["guid"]: card for card in cards if card.get("guid")}
    prebuilts: dict[str, dict] = {}
    menus: dict[str, list] = defaultdict(list)
    for deck in deck_rows:
        rows = []
        champ = by_guid.get(deck["champion"])
        if champ:
            rows.append({"databaseId": champ["databaseId"], "quantity": 1, "loadGroupId": "playerNChampion"})
        total = 0
        unmatched = 0
        for guid, qty in deck["cards"]:
            card = by_guid.get(guid)
            if not card:
                unmatched += 1
                continue
            group = "playerNResources" if card["type"] == "Resource" else "playerNDeck"
            if card["type"] == "Champion":
                group = "playerNChampion"
            rows.append({"databaseId": card["databaseId"], "quantity": qty, "loadGroupId": group})
            total += qty
        if total < 8:
            continue
        label = pretty_deck_name(deck["name"])
        deck_id = slug(label)
        if deck_id in prebuilts:
            deck_id = f"{deck_id}-{len(prebuilts)}"
        prebuilts[deck_id] = {"label": label, "cards": rows}
        if label.lower().startswith("starter"):
            bucket = "Starters"
        elif label.startswith("Signature"):
            bucket = "Signature"
        elif any(label.startswith(name) or name in label for name in CONSTRUCTED_ORDER):
            bucket = "Constructed"
        else:
            bucket = "Constructed"
        menus[bucket].append({"deckListId": deck_id, "label": label})
        print(f"  deck {label}: {total} unmatched={unmatched}")
    order = ["Starters", "Constructed", "Signature"]
    menu = {
        "deckMenu": {
            "subMenus": [
                {"label": name, "deckLists": menus[name]} for name in order if menus.get(name)
            ]
        }
    }
    return {"preBuiltDecks": prebuilts}, menu


def planned_image_url(card: dict[str, str], used: dict[str, int]) -> str:
    set_name = card.get("packName") or "Unknown"
    planned = card_rel_path(FOLDER, PASCAL, set_name, card["name"], ".jpg")
    key = planned.casefold()
    used[key] = used.get(key, 0) + 1
    if used[key] > 1:
        path = Path(planned)
        planned = path.with_name(f"{path.stem}-{used[key]}{path.suffix}").as_posix()
    return planned


def stamp_plugin_cards(
    hex_root: Path,
    cards: list[dict[str, str]],
    portraits: dict[str, Path],
    *,
    workers: int,
) -> int:
    """Write MSE-chrome JPEGs onto the existing toybox-relative paths."""
    used: dict[str, int] = {}
    jobs: list[tuple[dict[str, str], str, str | None]] = []
    urls: list[str] = []
    for card in cards:
        planned = planned_image_url(card, used)
        urls.append(planned)
        portrait = portraits.get((card.get("artId") or "").lower())
        jobs.append((card, str(IMAGES / planned), str(portrait) if portrait else None))
    print(f"Stamping {len(jobs)} faces with MSE chrome ({workers} worker{'s' if workers != 1 else ''})…")
    composed, failed = stamp_jobs(hex_root, jobs, workers=workers)
    for card, planned, (_card, dest, _portrait) in zip(cards, urls, jobs):
        rel = PLACEHOLDER_REL if dest in failed else planned
        card["imageUrl"] = rel
        card["zoomImageUrl"] = rel
        card["cardBack"] = "default"
    return composed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the HEX: Shards of Fate DragnCards plugin")
    parser.add_argument("--compare-browser", action="store_true", help="Diff gamedata against the Hex TCG Browser CSV")
    parser.add_argument(
        "--faces-only",
        action="store_true",
        help="Restamp tabletop JPEGs in place; leave TSV / plugin JSONs alone",
    )
    parser.add_argument("--limit", type=int, default=0, help="Stamp only the first N cards (requires --faces-only)")
    parser.add_argument("--workers", type=int, default=6, help="Parallel stamp workers (1 = sequential)")
    args = parser.parse_args()
    if args.limit and not args.faces_only:
        parser.error("--limit requires --faces-only")
    return args


def write_source(
    hex_root: Path,
    cards: list[dict[str, str]],
    composed: int,
    decks: int,
    keywords: int,
    *,
    faces_only: bool,
) -> None:
    (OUT / "SOURCE.txt").write_text(
        "\n".join(
            [
                f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from {hex_root} (HEX 1.1.0.086).",
                "CardTemplate + ChampionTemplate from Data/gamedata (gzip JSON).",
                "Portraits from AssetBundles/cardsets/*.harc (Unity 5.6 Texture2D).",
                "Keywords from Data/Localization/hex_uidata_en.xml.",
                "Faces stamped with client NGUI chrome (hex_mse_style.render_face). Kitchen-table hex_compose is lobby/back only.",
                "Hex TCG Browser CSV is a check only (hex_browser.py --compare-browser). Do not rebuild from it.",
                "Leave the HEX install where it is. Do not copy it into plugins/.",
                f"Cards: {len(cards)}  Composed: {composed}  Decks: {decks}  Keywords: {keywords}"
                + ("  (faces-only restamp)" if faces_only else ""),
                f"Types: {dict(Counter(card['type'] for card in cards))}",
                f"Sets: {dict(Counter(card['packName'] for card in cards))}",
                "Tabletop plugin only — no rules engine.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    hex_root = resolve_hex()
    print(f"HEX client: {hex_root}")
    raw = load_gamedata(hex_root)
    sets = parse_sets(raw)
    cards = parse_cards(raw, sets)
    champs = parse_champions(raw, sets)
    print(f"  {summarize(cards)}")
    print(f"  champions {len(champs)}")
    if args.compare_browser:
        print(compare_browser(cards + champs))
        if not args.faces_only:
            return
    keywords = load_keywords(hex_root / "Data/Localization/hex_uidata_en.xml")
    if not args.faces_only:
        write_rules_md(OUT / "RULES.md", keywords)
    cards.extend(rules_cards(keywords))
    cards.extend(champs)
    assign_ids(cards)
    print(f"  after champs+rules {len(cards)}")

    deck_rows = parse_decks(raw)
    decks, menu = official_decks(cards, deck_rows)

    art_ids = {card["artId"] for card in cards if card.get("artId")}
    print(f"Extracting {len(art_ids)} portraits from HARC…")
    portraits = extract_portraits(
        hex_root / "AssetBundles/cardsets",
        IMAGES / FOLDER / "_art",
        art_ids,
    )
    print(f"  portraits on disk {len(portraits)}")

    if not args.faces_only:
        plugin = IMAGES / FOLDER / "_plugin"
        plugin.mkdir(parents=True, exist_ok=True)
        compose_back(plugin / f"{PASCAL}-CardbackDefault.jpg")
        sample = next(iter(portraits.values()), None)
        compose_lobby(plugin / "banner2.jpg", sample, "HEX: Shards of Fate")
        compose_lobby(plugin / "logo2.jpg", sample, "HEX")
        compose_lobby(plugin / f"{PASCAL}-Background.jpg", sample, "HEX: Shards of Fate")
        write_color_png(plugin / f"{PASCAL}-TokenPlus.png", (48, 160, 72))
        write_color_png(plugin / f"{PASCAL}-TokenDamage.png", (196, 48, 48))

    (IMAGES / PLACEHOLDER_REL).parent.mkdir(parents=True, exist_ok=True)
    stamp_jobs(
        hex_root,
        [(
            {"name": "Missing", "type": "Rules", "text": "No art in this client.", "threshold": ""},
            str(IMAGES / PLACEHOLDER_REL),
            None,
        )],
        workers=1,
    )

    to_stamp = cards[: args.limit] if args.limit else cards
    composed = stamp_plugin_cards(hex_root, to_stamp, portraits, workers=args.workers)
    if args.limit:
        print(f"  limit {args.limit}: left {len(cards) - len(to_stamp)} faces unchanged")

    if not args.faces_only:
        tsv_cards = [{col: sanitize(str(card.get(col, ""))) for col in COLUMNS} for card in cards]
        write_tsv(tsv_cards, COLUMNS, OUT / "tsvs" / "cards.tsv")
        write_plugin_jsons(
            cards,
            decks,
            menu,
            {"default": f"{FOLDER}/_plugin/{PASCAL}-CardbackDefault.jpg"},
            keywords,
        )
        write_source(
            hex_root,
            cards,
            composed,
            len(decks["preBuiltDecks"]),
            len(keywords),
            faces_only=False,
        )
    elif not args.limit:
        write_source(
            hex_root,
            cards,
            composed,
            len(decks["preBuiltDecks"]),
            len(keywords),
            faces_only=True,
        )
    print(f"Wrote {OUT}  composed={composed} decks={len(decks['preBuiltDecks'])} keywords={len(keywords)}")


if __name__ == "__main__":
    main()
