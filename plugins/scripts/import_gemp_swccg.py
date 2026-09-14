#!/usr/bin/env python3
"""Build a DragnCards Star Wars CCG plugin from GEMP card data + the WARS table shell.

GEMP's Java rules engine is not ported. This clones the WARS layout/piles/turn flow
(Activate → Control → Deploy → Battle → Move → Draw → End; Reserve / Force / Used / Lost)
and fills the card database from GEMP's blueprint JSON + CardImages.js.

  python plugins/scripts/import_gemp_swccg.py
  python plugins/scripts/collect_hosted_images.py star-wars-ccg-decipher
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from import_gemp_prebuilts import write_swccg_prebuilts
from image_names import clear_image_url_prefix, toybox_url

ROOT = Path(__file__).resolve().parents[1]
GEMP = ROOT / "star-wars-decipher" / "gemp-swccg"
WARS = ROOT / "wars-trading-card-game-live-import"
OUT = ROOT / "star-wars-ccg-decipher"

BLUEPRINTS = GEMP / "src/gemp-swccg-cards/src/main/resources/card_blueprint_database.json"
CARD_IMAGES_JS = GEMP / "src/gemp-swccg-async/src/main/web/js/gemp-016/cards/CardImages.js"

LIGHT_BACK = "https://res.starwarsccg.org/gemp/lightcardback.png"
DARK_BACK = "https://res.starwarsccg.org/gemp/darkcardback.png"

SET_NAMES = {
    "PREMIERE": "Premiere",
    "A_NEW_HOPE": "A New Hope",
    "HOTH": "Hoth",
    "DAGOBAH": "Dagobah",
    "CLOUD_CITY": "Cloud City",
    "JABBAS_PALACE": "Jabba's Palace",
    "SPECIAL_EDITION": "Special Edition",
    "ENDOR": "Endor",
    "DEATH_STAR_II": "Death Star II",
    "REFLECTIONS_II": "Reflections II",
    "TATOOINE": "Tatooine",
    "CORUSCANT": "Coruscant",
    "REFLECTIONS_III": "Reflections III",
    "THEED_PALACE": "Theed Palace",
    "PREMIERE_INTRO_TWO_PLAYER": "Premiere Introductory Two Player Game",
    "JEDI_PACK": "Jedi Pack",
    "REBEL_LEADER_PACK": "Rebel Leader Pack",
    "ESB_INTRO_TWO_PLAYER": "Empire Strikes Back Introductory Two Player Game",
    "FIRST_ANTHOLOGY": "First Anthology",
    "OTSD": "Official Tournament Sealed Deck",
    "SECOND_ANTHOLOGY": "Second Anthology",
    "ENHANCED_PREMIERE": "Enhanced Premiere",
    "ENHANCED_CLOUD_CITY": "Enhanced Cloud City",
    "ENHANCED_JABBAS_PALACE": "Enhanced Jabba's Palace",
    "THIRD_ANTHOLOGY": "Third Anthology",
    "JPSD": "Jabba's Palace Sealed Deck",
    "SET_0": "Virtual Set 0",
    "SET_1": "Virtual Set 1",
    "SET_2": "Virtual Set 2",
    "SET_3": "Virtual Set 3",
    "SET_4": "Virtual Set 4",
    "SET_5": "Virtual Set 5",
    "SET_6": "Virtual Set 6",
    "SET_7": "Virtual Set 7",
    "SET_8": "Virtual Set 8",
    "SET_9": "Virtual Set 9",
    "SET_10": "Virtual Set 10",
    "SET_11": "Virtual Set 11",
    "SET_12": "Virtual Set 12",
    "SET_13": "Virtual Set 13",
    "SET_14": "Virtual Set 14",
    "SET_15": "Virtual Set 15",
    "SET_16": "Virtual Set 16",
    "SET_17": "Virtual Set 17",
    "SET_18": "Virtual Set 18",
    "SET_19": "Virtual Set 19",
    "SET_20": "Virtual Set 20",
    "SET_21": "Virtual Set 21",
    "SET_22": "Virtual Set 22",
    "SET_23": "Virtual Set 23",
    "SET_24": "Virtual Set 24",
    "SET_25": "Virtual Set 25",
    "SET_26": "Virtual Set 26",
    "SET_27": "Virtual Set 27",
    "DEMO_DECK": "Virtual Premium Set",
    "DREAM_CARDS": "Dream Cards",
    "PLAYTESTING": "Playtesting",
    "LEGACY": "Legacy",
}

CATEGORIES = [
    "CHARACTER",
    "LOCATION",
    "STARSHIP",
    "VEHICLE",
    "WEAPON",
    "DEVICE",
    "INTERRUPT",
    "EFFECT",
    "OBJECTIVE",
    "ADMIRALS_ORDER",
    "EPIC_EVENT",
    "JEDI_TEST",
    "DEFENSIVE_SHIELD",
    "CREATURE",
    "PODRACER",
    "GAME_AID",
]

COPY_JSONS = [
    "actionLists.json",
    "automation.json",
    "cardMenu.json",
    "cardProperties.json",
    "faceProperties.json",
    "functions.json",
    "gameProperties.json",
    "groupMenu.json",
    "groupTypes.json",
    "groups.json",
    "hotkeys.json",
    "labels.json",
    "layouts.json",
    "main.json",
    "phases.json",
    "playerProperties.json",
    "pluginMenu.json",
    "preferences.json",
    "prompts.json",
    "saveGame.json",
    "spawnExistingCardModal.json",
    "steps.json",
    "tokens.json",
    "topBarCounters.json",
]


def dump_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def rewrite_text(text: str) -> str:
    replacements = [
        ("player1Active", "player1Force"),
        ("player2Active", "player2Force"),
        ("playerNActive", "playerNForce"),
        ("Player1Active", "Player1Force"),
        ("Player2Active", "Player2Force"),
        ("{{$PLAYER_N}}Active", "{{$PLAYER_N}}Force"),
        ("your Active, Reserve", "your Force, Reserve"),
        ("https://warstcg.org/dragncards-tutorial/", "https://www.starwarsccg.org/"),
        ("https://warstcg.org", "https://www.starwarsccg.org"),
        ("WARS Trading Card Game", "Star Wars CCG"),
        ("WARS TCG", "Star Wars CCG"),
        ("wars-trading-card-game", "star-wars-ccg"),
        ("WARSTradingCardGame", "StarWarsCcg"),
        ("Player1 WARS", "Player1 Star Wars CCG"),
        ("Player2 WARS", "Player2 Star Wars CCG"),
        ("Active Pile", "Force Pile"),
        ("from their Active", "from their Force"),
        ("from Active", "from Force"),
        ("to Active", "to Force"),
        ("from Active or", "from Force or"),
        ("Activate Energy", "Activate Force"),
        ("Activated 1 Energy", "Activated 1 Force"),
        ("Pay 1 Energy", "Use 1 Force"),
        ("paid 1 Energy", "used 1 Force"),
        ("Lost 1 Energy", "Lost 1 Force"),
        ("lose Energy", "lose Force"),
        ("Energy from", "Force from"),
        ("Energy Icon", "Force Icon"),
        ("energy icons", "Force icons"),
        ("Energy equal", "Force equal"),
        ("Pay 1 Energy", "Use 1 Force"),
        ("1 Energy for each", "1 Force for each"),
        ("Additional", "additional"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def parse_card_images(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    return dict(re.findall(r'"([^"]+)":\s*"((?:https:)?//[^"]+)"', text))


def cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")
    return text.strip()


def icons_text(card: dict) -> str:
    parts = []
    for item in card.get("icons") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("icon") or ""
        count = item.get("count") or 1
        if not name:
            continue
        parts.append(name if count == 1 else f"{name} x{count}")
    return ", ".join(parts)


def card_text(card: dict) -> str:
    if card.get("cardCategory") == "LOCATION":
        light = (card.get("locationLightSideGameText") or "").strip()
        dark = (card.get("locationDarkSideGameText") or "").strip()
        chunks = []
        if light:
            chunks.append(f"Light: {light}")
        if dark:
            chunks.append(f"Dark: {dark}")
        return " / ".join(chunks)
    return (card.get("gameText") or "").strip()


def num(card: dict, *keys: str) -> str:
    for key in keys:
        if key in card and card[key] not in (None, ""):
            return cell(card[key])
    return ""


def build_tsv(images: dict[str, str]) -> tuple[list[str], list[list[str]], int, int]:
    cards = json.loads(BLUEPRINTS.read_text(encoding="utf-8"))
    header = [
        "databaseId",
        "name",
        "imageUrl",
        "cardBack",
        "type",
        "subtype",
        "side",
        "uniqueness",
        "packName",
        "rarity",
        "destiny",
        "deploy",
        "power",
        "ability",
        "armor",
        "maneuver",
        "hyperspeed",
        "landspeed",
        "forfeit",
        "politics",
        "icons",
        "cardTypes",
        "lore",
        "text",
    ]
    rows: list[list[str]] = []
    missing = 0
    extra_faces = 0
    for card in cards:
        card_id = str(card.get("cardId") or "").strip()
        if not card_id:
            continue
        image = images.get(card_id) or ""
        if image.startswith("//"):
            image = "https:" + image
        if not image:
            missing += 1
        side = (card.get("side") or "").upper()
        back = "Dark" if side == "DARK" else "Light"
        double = bool(card.get("isFrontOfDoubleSidedCard"))
        if double:
            back = "multi_sided"
        row = [
            card_id,
            cell(card.get("title")),
            image,
            back,
            cell(card.get("cardCategory")),
            cell(card.get("cardSubtype")),
            side,
            cell(card.get("uniqueness")),
            SET_NAMES.get(card.get("expansionSet") or "", cell(card.get("expansionSet"))),
            cell(card.get("rarity")),
            num(card, "destiny"),
            num(card, "deployCost"),
            num(card, "power"),
            num(card, "ability"),
            num(card, "armor"),
            num(card, "maneuver"),
            num(card, "hyperspeed"),
            num(card, "landspeed"),
            num(card, "forfeit"),
            num(card, "politics"),
            icons_text(card),
            ", ".join(card.get("cardTypes") or []),
            cell(card.get("lore")),
            cell(card_text(card)),
        ]
        rows.append(row)
        if double:
            back_url = images.get(f"{card_id}_BACK") or images.get(f"{card_id}_back") or ""
            if back_url.startswith("//"):
                back_url = "https:" + back_url
            if back_url:
                extra = list(row)
                extra[2] = back_url
                extra[1] = cell(card.get("title")) + " (Back)"
                rows.append(extra)
                extra_faces += 1
    return header, rows, missing, extra_faces


def write_source(missing: int, extra_faces: int, rows: int) -> None:
    lines = [
        f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from GEMP-SWCCG card data.",
        "Table shell cloned from wars-trading-card-game-live-import (same Decipher pile/turn flow).",
        "Card stats: gemp-swccg/.../card_blueprint_database.json",
        "Art map: gemp-swccg/.../CardImages.js → res.starwarsccg.org",
        "Author credit: GEMP / starwarsccg.org",
        "",
        "This is a tabletop plugin (layout, piles, reminders). GEMP's Java rules engine is not ported.",
        f"TSV rows: {rows}  extra objective/back faces: {extra_faces}  cards missing art in CardImages.js: {missing}",
        "Drop banner.jpg and logo.jpg into images/star-wars-ccg/_plugin/ before Load Game Definition.",
        "Prebuilts come from GEMP Librarian sample_decks.sql + utinni_sample_decks.sql.",
        "",
    ]
    (OUT / "SOURCE.txt").write_text("\n".join(lines), encoding="utf-8")


def customize_copied_jsons() -> None:
    jsons = OUT / "jsons"

    main = load_json(jsons / "main.json")
    main["pluginName"] = "Star Wars CCG"
    main["author"] = "GEMP / starwarsccg.org"
    main["tutorialUrl"] = "https://www.starwarsccg.org/"
    main["announcements"] = [
        "Tabletop plugin from GEMP card data. Rules are reminders + pile shortcuts, not a rules engine.",
        "A = activate Force (Reserve → Force). P = use Force (Force → Used). D = draw from Force. Y = destiny to Stack.",
        "Load a Reserve deck, put starting locations on the location row, deploy your Objective, then Activate.",
    ]
    main.pop("backgroundUrl", None)
    main["bannerUrl"] = toybox_url("star-wars-ccg/_plugin/banner.jpg")
    main["logoUrl"] = toybox_url("star-wars-ccg/_plugin/logo.jpg")
    main["defaultActions"] = [
        action
        for action in main.get("defaultActions") or []
        if action.get("actionList") != "invertCard"
    ]
    dump_json(jsons / "main.json", main)

    types = {
        name: {"height": 1, "tokens": [], "width": 0.72}
        for name in CATEGORIES
    }
    dump_json(jsons / "cardTypes.json", {"cardTypes": types})

    dump_json(
        jsons / "cardBacks.json",
        {
            "cardBacks": {
                "Light": {"height": 1, "imageUrl": LIGHT_BACK, "width": 0.72},
                "Dark": {"height": 1, "imageUrl": DARK_BACK, "width": 0.72},
            }
        },
    )

    dump_json(
        jsons / "playerProperties.json",
        {
            "playerProperties": {
                "force": {
                    "default": 0,
                    "label": "id:force",
                    "min": 0,
                    "type": "integer",
                }
            }
        },
    )

    dump_json(
        jsons / "topBarCounters.json",
        {
            "topBarCounters": {
                "player": [
                    {
                        "imageUrl": LIGHT_BACK,
                        "label": "id:force",
                        "playerProperty": "force",
                    }
                ],
                "shared": [
                    {
                        "gameProperty": "roundNumber",
                        "imageUrl": "",
                        "label": "Round",
                    }
                ],
            }
        },
    )

    dump_json(
        jsons / "deckbuilder.json",
        {
            "deckbuilder": {
                "addButtons": [1],
                "colorKey": "side",
                "colorValues": {"LIGHT": "#4B81D7", "DARK": "#AC1714"},
                "columns": [
                    {"label": "Name", "propName": "name"},
                    {"label": "Type", "propName": "type"},
                    {"label": "Side", "propName": "side"},
                    {"label": "Set", "propName": "packName"},
                    {"label": "Destiny", "propName": "destiny"},
                ],
                "spawnGroups": [{"label": "id:myDeck", "loadGroupId": "playerNReserve"}],
            }
        },
    )

    dump_json(
        jsons / "browse.json",
        {
            "browse": {
                "filterPropertySideA": "type",
                "filterValuesSideA": CATEGORIES,
                "textPropertiesSideA": ["name", "text", "lore"],
            }
        },
    )

    clear_image_url_prefix(jsons)

    menu = load_json(jsons / "cardMenu.json")
    menu["cardMenu"]["options"] = [
        opt for opt in menu["cardMenu"]["options"] if opt.get("actionList") != "invertCard"
    ]
    if "playerNForce" not in menu["cardMenu"]["moveToGroupIds"]:
        menu["cardMenu"]["moveToGroupIds"].insert(1, "playerNForce")
    dump_json(jsons / "cardMenu.json", menu)

    hotkeys = load_json(jsons / "hotkeys.json")
    for item in hotkeys["hotkeys"]["game"]:
        if item.get("actionList") == ["DRAW_STARTING_HAND"]:
            item["key"] = "Y"
            item["label"] = "Draw destiny from Reserve onto the Stack"
        elif item.get("actionList") == ["DRAW_ONE_CARD"]:
            item["label"] = "Draw a card from Force Pile"
        elif item.get("actionList") == ["ACTIVATE_ENERGY"]:
            item["label"] = "Activate 1 Force from Reserve to Force Pile"
        elif item.get("actionList") == ["PAY_ENERGY"]:
            item["label"] = "Use 1 Force from Force Pile to Used"
        elif item.get("actionList") == ["USED_TO_RESERVE"]:
            item["label"] = "End Turn — Used Pile under Reserve"
    dump_json(jsons / "hotkeys.json", hotkeys)

    labels = load_json(jsons / "labels.json")
    labels["labels"]["force"] = {"English": "Force"}
    labels["labels"]["energy"] = {"English": "Force"}
    labels["labels"]["menuactivateEnergy"] = {"English": "•Activate 1 Force."}
    labels["labels"]["menuPayEnergy"] = {"English": "•Use 1 Force."}
    labels["labels"]["drawonecard"] = {"English": "•Draw 1 from Force Pile"}
    labels["labels"]["drawstartinghand"] = {"English": "•Draw Destiny (Reserve → Stack)"}
    labels["labels"]["menuactivetoLost"] = {"English": "•Lose 1 from Force."}
    labels["labels"]["rotate180"] = {"English": "•Rotate 180"}
    dump_json(jsons / "labels.json", labels)

    prompts = load_json(jsons / "prompts.json")
    prompts["prompts"]["welcome1"]["message"] = (
        "Welcome to Star Wars CCG on DragnCards. This table copies the WARS/Decipher layout "
        "(Reserve, Force, Used, Lost, location row) with GEMP's card list. It does not enforce card text. "
        "Builder or Menu → Load puts a deck in Reserve. Deploy starting locations onto the location row and "
        "your Objective into play. A = activate Force, P = use Force, D = draw from Force, Y = destiny onto the Stack, "
        "E = Used under Reserve. TAB shows hotkeys. Card data/art: GEMP / starwarsccg.org."
    )
    dump_json(jsons / "prompts.json", prompts)

    functions = load_json(jsons / "functions.json")
    start = functions["functions"]["DRAW_STARTING_HAND"]["code"][0]
    # MOVE_STACKS Reserve → Hand, 8, bottom  → Stack, 1, top
    start[2][0][2] = "sharedStack"
    start[2][0][3] = 1
    start[2][0][4] = "top"
    start[2][1][1] = "{{$ALIAS_N}} drew destiny from Reserve onto the Stack. Send it to Used when resolved."
    start[4][1] = (
        "{{$ALIAS_N}} Reserve Deck is empty. Load a deck with Menu → Load or Builder. "
        "You lose if Reserve, Force, and Used are all empty."
    )
    dump_json(jsons / "functions.json", functions)

    automation = load_json(jsons / "automation.json")
    rules = automation["automation"]["gameRules"]
    # Fix End step id 7.1 → 7.0 and rewrite SWCCG reminders.
    phase_labels = {
        "1.0": (
            "Activate Phase",
            "Activate Force: one for each Force icon on your side of locations, plus 1. Hotkey A. Arrow-Down for Next.",
        ),
        "2.1": (
            "Control Phase",
            "Drain at each location you control that opponent occupies. Opponent loses that much Force. Arrow-Down for Next.",
        ),
        "3.1": (
            "Deploy Phase",
            "Deploy cards from hand (pay deploy cost from Force Pile). Arrow-Down for Next.",
        ),
        "4.1": (
            "Battle Phase",
            "Use 1 Force to initiate a battle at a location where you both have presence. Arrow-Down for Next.",
        ),
        "4.2": (None, "Weapons segment: fire weapons, draw weapon destiny. Interrupts as needed. Arrow-Down for Next."),
        "4.3": (None, "Power segment: total power + battle destiny. Hotkey Y draws destiny onto the Stack. Arrow-Down for Next."),
        "4.4": (None, "Interrupts / just actions. Arrow-Down for Next."),
        "4.5": (None, "Attrition: losing side must lose cards totaling forfeit ≥ attrition. Arrow-Down for Next."),
        "4.6": (None, "Interrupts / just actions. Arrow-Down for Next."),
        "4.7": (None, "Battle damage: power difference as Force loss (may satisfy with forfeited cards). Arrow-Down for Next."),
        "4.8": (None, "Interrupts / just actions. Arrow-Down for Next."),
        "4.9": (None, "Satisfy remaining Force loss from Reserve / Force / Used. Arrow-Down for Next."),
        "4.10": (None, "Interrupts / just actions. Arrow-Down for Next."),
        "4.11": (
            "Battle Phase: End of Battle",
            "Hit cards to Lost Pile. Arrow-Up to 4.1 for another battle or Arrow-Down for Move.",
        ),
        "5.1": (
            "Move Phase",
            "Move characters, vehicles, and starships (usually 1 Force each). Arrow-Down for Next.",
        ),
        "6.1": (
            "Draw Phase",
            "Draw any number of cards from Force Pile to hand (Hotkey D). Unused Force stays. Arrow-Down for Next.",
        ),
        "7.0": (
            "End of Turn",
            "Used Pile under Reserve (Hotkey E or End Turn). Arrow-Down for opponent Activate.",
        ),
    }
    then = rules["phaseText"]["then"]
    # Walk COND branches: [COND, cond1, then1, cond2, then2, ...]
    i = 1
    while i < len(then) - 1:
        cond = then[i]
        body = then[i + 1]
        step = None
        if isinstance(cond, list) and len(cond) >= 3 and cond[0] == "EQUAL":
            step = cond[2]
        if step == "7.1":
            cond[2] = "7.0"
            step = "7.0"
        if step in phase_labels:
            fade, reminder = phase_labels[step]
            if isinstance(body, list) and body and isinstance(body[0], list) and body[0][0] == "FADE_TEXT_GAME":
                body[0][1] = fade
                for item in body:
                    if isinstance(item, list) and item and item[0] == "UPDATE_LAYOUT":
                        item[2] = reminder
            elif isinstance(body, list) and body and body[0] == "UPDATE_LAYOUT":
                body[2] = reminder
        i += 2

    # Force counters for both players
    for player in ("player1", "player2"):
        force_id = "player1Force" if player == "player1" else "player2Force"
        rules[f"{player}ForceUpdater"] = {
            "_comment": f"Life Force = Reserve + Force + Used for {player}",
            "condition": True,
            "inheritFrom": f"{player}deckTrigger",
            "priority": 10,
            "then": [
                [
                    "SET",
                    f"/playerData/{player}/force",
                    [
                        "ADD",
                        ["LENGTH", f"$GAME.groupById.{player}Reserve.stackIds"],
                        ["LENGTH", f"$GAME.groupById.{force_id}.stackIds"],
                        ["LENGTH", f"$GAME.groupById.{player}Used.stackIds"],
                    ],
                ]
            ],
        }
        rules[f"{player}deckTrigger"] = {
            "_comment": "Watch life-force piles",
            "abstract": True,
            "listenTo": [
                f"$GAME.groupById.{player}Reserve.stackIds",
                f"$GAME.groupById.{force_id}.stackIds",
                f"$GAME.groupById.{player}Used.stackIds",
            ],
            "type": "trigger",
        }
    rules.pop("player1EnergyUpdater", None)
    dump_json(jsons / "automation.json", automation)

    lists = load_json(jsons / "actionLists.json")
    lists["actionLists"]["drawstartingHand"][0][2] = " drew destiny onto the Stack."
    dump_json(jsons / "actionLists.json", lists)

    groups = load_json(jsons / "groups.json")
    for key in ("player1Force", "player2Force"):
        if key in groups["groups"]:
            n = "1" if "1" in key else "2"
            groups["groups"][key]["label"] = f"Player {n} Force"
            groups["groups"][key]["tableLabel"] = f"Player {n} Force"
    dump_json(jsons / "groups.json", groups)


def main() -> int:
    if not BLUEPRINTS.exists() or not CARD_IMAGES_JS.exists():
        raise SystemExit("GEMP card JSON or CardImages.js not found")
    if not WARS.exists():
        raise SystemExit("WARS plugin folder not found")

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "jsons").mkdir(parents=True)
    (OUT / "tsvs").mkdir(parents=True)

    for name in COPY_JSONS:
        src = WARS / "jsons" / name
        dest = OUT / "jsons" / name
        text = rewrite_text(src.read_text(encoding="utf-8"))
        dest.write_text(text, encoding="utf-8")

    customize_copied_jsons()

    images = parse_card_images(CARD_IMAGES_JS)
    header, rows, missing, extra_faces = build_tsv(images)
    tsv = OUT / "tsvs" / "cards.tsv"
    lines = ["\t".join(header)]
    lines.extend("\t".join(row) for row in rows)
    tsv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    decks = write_swccg_prebuilts(OUT)
    write_source(missing, extra_faces, len(rows))

    print(f"Wrote {OUT.name}")
    print(f"  pluginName: Star Wars CCG")
    print(f"  tsv rows: {len(rows)}  missing art: {missing}  extra faces: {extra_faces}")
    print(f"  prebuilt decks: {decks['decks']}  missing card ids: {decks['missing']}")
    print(f"  json files: {len(list((OUT / 'jsons').glob('*.json')))}")
    print()
    print("Next:")
    print("  python plugins/scripts/collect_hosted_images.py star-wars-ccg-decipher")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
