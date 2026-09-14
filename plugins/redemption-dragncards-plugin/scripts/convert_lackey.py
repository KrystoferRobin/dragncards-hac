#!/usr/bin/env python3
"""Convert the LackeyCCG Redemption plugin into DragnCards TSV + table JSON."""

from __future__ import annotations

import csv
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from image_names import stamp_lobby_art  # noqa: E402

LACKEY_DIR = Path(r"C:\Users\chris\Documents\e-Sword\tests\LackeyCCG\plugins\Redemption")
PLUGIN_DIR = Path(r"C:\Users\chris\Documents\e-Sword\dragncards\redemption-dragncards-plugin")
CARDDATA = LACKEY_DIR / "sets" / "carddata.txt"
DECKS_DIR = LACKEY_DIR / "decks"
TSV_OUT = PLUGIN_DIR / "tsvs" / "cards.tsv"
JSONS_DIR = PLUGIN_DIR / "jsons"
GAME_FOLDER = "redemption"

IMAGE_BASE = "https://jalstad.github.io/RedemptionLackeyCCG/RedemptionQuick/sets/setimages/general"

TYPE_MAP = {
    "GE": "Good Enhancement",
    "EE": "Evil Enhancement",
    "GE/EE": "Good/Evil Enhancement",
    "GE/Hero": "Good Enhancement/Hero",
    "Hero/GE": "Hero/Good Enhancement",
    "GE/Evil Character": "Good Enhancement/Evil Character",
    "EE/Evil Character": "Evil Enhancement/Evil Character",
    "Evil Character/EE": "Evil Character/Evil Enhancement",
    "Hero/Evil Character": "Hero/Evil Character",
    "Evil Character/Fortress": "Evil Character/Fortress",
    "Fortress / Evil Character": "Fortress/Evil Character",
    "Hero/Fortress": "Hero/Fortress",
}

BROWSE_FILTERS = [
    "Hero",
    "Evil Character",
    "Lost Soul",
    "Good Enhancement",
    "Evil Enhancement",
    "Good/Evil Enhancement",
    "Artifact",
    "Dominant",
    "Fortress",
    "Site",
    "Curse",
    "Covenant",
    "City",
    "Token",
]

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "category",
    "set",
    "officialSet",
    "brigade",
    "strength",
    "toughness",
    "class",
    "identifier",
    "rarity",
    "reference",
    "alignment",
    "legality",
    "text",
    "loadGroupId",
]

DECK_FILES = [
    ("starterE", "Starter E", "Starter_E.dek", "Starters"),
    ("starterF", "Starter F", "Starter_F.dek", "Starters"),
    ("starterG", "Starter G", "Starter_G.dek", "Starters"),
    ("starterH", "Starter H", "Starter_H.dek", "Starters"),
    ("starterI", "Starter I", "Starter_I.dek", "Starters"),
    ("starterJ", "Starter J", "Starter_J.dek", "Starters"),
    ("starterK", "Starter K", "Starter_K.dek", "Starters"),
    ("starterL", "Starter L", "Starter_L.dek", "Starters"),
    ("limitedA", "Limited A", "Limited_A.dek", "Limited / Unlimited"),
    ("limitedB", "Limited B", "Limited_B.dek", "Limited / Unlimited"),
    ("unlimitedA", "Unlimited A", "Unlimited_A.dek", "Limited / Unlimited"),
    ("unlimitedB", "Unlimited B", "Unlimited_B.dek", "Limited / Unlimited"),
    ("cDeck1st", "C Deck 1st print", "C_Deck_1st_print.dek", "C / D Decks"),
    ("cDeck2nd", "C Deck 2nd print", "C_Deck_2nd_print.dek", "C / D Decks"),
    ("dDeck1st", "D Deck 1st print", "D_Deck_1st_print.dek", "C / D Decks"),
    ("dDeck2nd", "D Deck 2nd print", "D_Deck_2nd_print.dek", "C / D Decks"),
]

SUPERZONE_TO_GROUP = {
    "Deck": "playerNDeck",
    "Reserve": "playerNReserve",
    "Tokens": "playerNTokens",
}

ZONE_BORDER = "1px solid rgba(210, 210, 210, 0.55)"
TERRITORY_BORDER = "1px solid rgba(180, 200, 230, 0.85)"
BATTLE_BORDER = "1px solid rgba(230, 180, 120, 0.9)"
BONDAGE_BORDER = "1px solid rgba(160, 90, 160, 0.9)"


def sanitize(value: str) -> str:
    return (value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()


def map_type(raw: str) -> str:
    text = sanitize(raw)
    return TYPE_MAP.get(text, text)


def browse_category(kind: str) -> str:
    if "Token" in kind:
        return "Token"
    if kind in BROWSE_FILTERS:
        return kind
    for cat in BROWSE_FILTERS:
        if kind.startswith(cat + "/") or kind.endswith("/" + cat) or f"/{cat}/" in f"/{kind}/":
            return cat
    return "Other"


def image_url(image_file: str) -> str:
    return f"{IMAGE_BASE}/{quote(image_file, safe='-_.()')}.jpg"


def region_style(background: str, border: str) -> dict:
    return {
        "background": background,
        "border": border,
        "boxSizing": "border-box",
    }


def load_cards() -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    seen: set[str] = set()
    with CARDDATA.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            name = sanitize(row.get("Name", ""))
            set_name = sanitize(row.get("Set", ""))
            image_file = sanitize(row.get("ImageFile", ""))
            if not name or not set_name or not image_file:
                errors.append(f"Skipping incomplete row: {name!r} {set_name!r} {image_file!r}")
                continue
            kind = map_type(row.get("Type", ""))
            if not kind:
                errors.append(f"Missing type for {name} ({set_name})")
                continue
            database_id = f"{set_name}__{image_file}"
            if database_id in seen:
                database_id = f"{database_id}__{name}"
            if database_id in seen:
                errors.append(f"Duplicate databaseId {database_id}")
                continue
            seen.add(database_id)
            token = "Token" in kind
            cards.append(
                {
                    "databaseId": database_id,
                    "name": name,
                    "imageUrl": image_url(image_file),
                    "cardBack": "default",
                    "type": kind,
                    "category": browse_category(kind),
                    "set": set_name,
                    "officialSet": sanitize(row.get("OfficialSet", "")),
                    "brigade": sanitize(row.get("Brigade", "")),
                    "strength": sanitize(row.get("Strength", "")),
                    "toughness": sanitize(row.get("Toughness", "")),
                    "class": sanitize(row.get("Class", "")),
                    "identifier": sanitize(row.get("Identifier", "")),
                    "rarity": sanitize(row.get("Rarity", "")),
                    "reference": sanitize(row.get("Reference", "")),
                    "alignment": sanitize(row.get("Alignment", "")),
                    "legality": sanitize(row.get("Legality", "")),
                    "text": sanitize(row.get("SpecialAbility", "")),
                    "loadGroupId": "playerNTokens" if token else "playerNDeck",
                    "_imageFile": image_file,
                }
            )
    return cards, errors


def write_tsv(cards: list[dict[str, str]]) -> None:
    TSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = ["\t".join(TSV_COLUMNS)]
    for card in cards:
        lines.append("\t".join(sanitize(card.get(col, "")) for col in TSV_COLUMNS))
    TSV_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(name: str, payload: dict) -> None:
    JSONS_DIR.mkdir(parents=True, exist_ok=True)
    (JSONS_DIR / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def make_indexes(cards: list[dict[str, str]]) -> tuple[dict, dict, dict]:
    by_image_set: dict[tuple[str, str], dict] = {}
    by_name_set: dict[tuple[str, str], dict] = {}
    by_image: dict[str, list[dict]] = {}
    for card in cards:
        by_image_set[(card["_imageFile"], card["set"])] = card
        by_name_set[(card["name"], card["set"])] = card
        by_image.setdefault(card["_imageFile"], []).append(card)
    return by_image_set, by_name_set, by_image


def match_dek_card(
    name: str,
    set_name: str,
    image_id: str,
    by_image_set: dict,
    by_name_set: dict,
    by_image: dict,
) -> dict | None:
    if image_id and set_name and (image_id, set_name) in by_image_set:
        return by_image_set[(image_id, set_name)]
    if name and set_name and (name, set_name) in by_name_set:
        return by_name_set[(name, set_name)]
    if image_id:
        matches = by_image.get(image_id, [])
        if len(matches) == 1:
            return matches[0]
        if set_name:
            set_matches = [card for card in matches if card["set"] == set_name]
            if len(set_matches) == 1:
                return set_matches[0]
    return None


def parse_dek(path: Path) -> list[tuple[str, str, str, str]]:
    tree = ET.parse(path)
    rows: list[tuple[str, str, str]] = []
    for superzone in tree.getroot().findall("superzone"):
        zone_name = superzone.get("name") or "Deck"
        load_group = SUPERZONE_TO_GROUP.get(zone_name)
        if not load_group:
            continue
        for card_el in superzone.findall("card"):
            name_el = card_el.find("name")
            set_el = card_el.find("set")
            name = sanitize(name_el.text if name_el is not None else "")
            image_id = sanitize(name_el.get("id") if name_el is not None else "")
            set_name = sanitize(set_el.text if set_el is not None else "")
            rows.append((name, set_name, image_id, load_group))
    return rows


def make_prebuilts(cards: list[dict[str, str]]) -> tuple[dict, dict, list[str]]:
    by_image_set, by_name_set, by_image = make_indexes(cards)
    errors: list[str] = []
    decks: dict[str, dict] = {}
    menu_groups: dict[str, list[dict]] = {}
    for deck_id, label, filename, menu_label in DECK_FILES:
        path = DECKS_DIR / filename
        if not path.exists():
            errors.append(f"Missing dek {filename}")
            continue
        counts: Counter[tuple[str, str]] = Counter()
        unmatched = 0
        for name, set_name, image_id, load_group in parse_dek(path):
            card = match_dek_card(name, set_name, image_id, by_image_set, by_name_set, by_image)
            if not card:
                unmatched += 1
                if unmatched <= 8:
                    errors.append(f"{deck_id}: unmatched {name!r} set={set_name!r} id={image_id!r}")
                continue
            counts[(card["databaseId"], load_group)] += 1
        if unmatched > 8:
            errors.append(f"{deck_id}: {unmatched - 8} more unmatched cards")
        decks[deck_id] = {
            "label": label,
            "cards": [
                {"databaseId": database_id, "quantity": qty, "loadGroupId": load_group}
                for (database_id, load_group), qty in counts.items()
            ],
        }
        menu_groups.setdefault(menu_label, []).append({"label": label, "deckListId": deck_id})
    menu = {"deckMenu": {"subMenus": [{"label": key, "deckLists": val} for key, val in menu_groups.items()]}}
    return {"preBuiltDecks": decks}, menu, errors


def in_play_group(pid: str, label: str, table_label: str) -> dict:
    return {
        "groupType": "inPlay",
        "label": f"Player {pid[-1]} {label}" if pid.startswith("player") else label,
        "tableLabel": table_label,
        "canHaveAttachments": True,
        "onCardEnter": {
            "controller": pid,
            "deckGroupId": f"{pid}Deck",
            "discardGroupId": f"{pid}Discard",
        },
    }


def make_groups() -> dict:
    groups: dict[str, dict] = {
        "sharedSetAside": {
            "groupType": "aside",
            "label": "Set Aside",
            "tableLabel": "Set Aside",
            "onCardEnter": {"controller": "shared"},
        }
    }
    for player in (1, 2):
        pid = f"player{player}"
        n = str(player)
        groups[f"{pid}Deck"] = {
            "groupType": "deck",
            "label": f"Player {n} Deck",
            "tableLabel": "Deck",
            "onCardEnter": {
                "controller": pid,
                "deckGroupId": f"{pid}Deck",
                "discardGroupId": f"{pid}Discard",
            },
        }
        groups[f"{pid}Hand"] = {
            "groupType": "hand",
            "label": f"Player {n} Hand",
            "tableLabel": "Hand",
            "onCardEnter": {
                "controller": pid,
                "deckGroupId": f"{pid}Deck",
                "discardGroupId": f"{pid}Discard",
            },
        }
        groups[f"{pid}Discard"] = {
            "groupType": "discard",
            "label": f"Player {n} Discard",
            "tableLabel": "Discard",
            "onCardEnter": {
                "controller": pid,
                "deckGroupId": f"{pid}Deck",
                "discardGroupId": f"{pid}Discard",
            },
        }
        groups[f"{pid}Reserve"] = {
            "groupType": "reserve",
            "label": f"Player {n} Reserve",
            "tableLabel": "Reserve",
            "onCardEnter": {
                "controller": pid,
                "deckGroupId": f"{pid}Deck",
                "discardGroupId": f"{pid}Discard",
            },
        }
        groups[f"{pid}GoodTerritory"] = in_play_group(pid, "Good Territory", "Good")
        groups[f"{pid}EvilTerritory"] = in_play_group(pid, "Evil Territory", "Evil")
        groups[f"{pid}LandOfBondage"] = in_play_group(pid, "Land of Bondage", "LoB")
        groups[f"{pid}BattleEnhancements"] = in_play_group(pid, "Battle Enhancements", "Enh")
        groups[f"{pid}Battle"] = in_play_group(pid, "Battle", "Battle")
        groups[f"{pid}Artifacts"] = in_play_group(pid, "Artifacts", "Art")
        groups[f"{pid}LandOfRedemption"] = {
            "groupType": "lor",
            "label": f"Player {n} Land of Redemption",
            "tableLabel": "LoR",
            "onCardEnter": {
                "controller": pid,
                "deckGroupId": f"{pid}Deck",
                "discardGroupId": f"{pid}Discard",
            },
        }
        groups[f"{pid}Banished"] = {
            "groupType": "banished",
            "label": f"Player {n} Banished",
            "tableLabel": "Banished",
            "onCardEnter": {
                "controller": pid,
                "deckGroupId": f"{pid}Deck",
                "discardGroupId": f"{pid}Discard",
            },
        }
        groups[f"{pid}Tokens"] = {
            "groupType": "tokens",
            "label": f"Player {n} Tokens",
            "tableLabel": "Tokens",
            "onCardEnter": {
                "controller": pid,
                "deckGroupId": f"{pid}Deck",
                "discardGroupId": f"{pid}Discard",
            },
        }
    return {"groups": groups}


def pct(value: float) -> str:
    return f"{value:g}%"


def pile(group_id: str, left: float, top: float, width: float = 6.0, height: float = 11.0) -> dict:
    return {
        "groupId": group_id,
        "type": "pile",
        "direction": "horizontal",
        "left": pct(left),
        "top": pct(top),
        "width": pct(width),
        "height": pct(height),
        "style": region_style("rgba(0, 0, 0, 0.35)", ZONE_BORDER),
    }


def row_region(
    group_id: str,
    left: float,
    top: float,
    width: float,
    height: float,
    background: str,
    border: str,
    region_type: str = "row",
    disable_attachments: bool = False,
) -> dict:
    region = {
        "groupId": group_id,
        "type": region_type,
        "direction": "horizontal",
        "left": pct(left),
        "top": pct(top),
        "width": pct(width),
        "height": pct(height),
        "style": region_style(background, border),
    }
    if disable_attachments:
        region["disableDroppableAttachments"] = True
    return region


def make_layouts() -> dict:
    play_w = 87.0
    good_w = play_w * 0.40
    evil_w = play_w * 0.40
    lob_w = play_w - good_w - evil_w
    lob_left = good_w + evil_w
    enh_w = play_w * 0.10
    art_w = play_w * 0.20
    battle_w = play_w - enh_w - art_w
    art_left = enh_w + battle_w
    pile_w = 6.0
    col1 = 88.0
    col2 = 94.0

    p2_hand_top, p2_hand_h = 0.0, 12.0
    p2_terr_top, p2_terr_h = 12.0, 16.0
    p2_battle_top, p2_battle_h = 28.0, 14.0
    p1_battle_top, p1_battle_h = 42.0, 14.0
    p1_terr_top, p1_terr_h = 56.0, 18.0
    p1_hand_top, p1_hand_h = 74.0, 26.0

    good_bg, good_bd = "rgba(24, 90, 42, 0.36)", "1px solid rgba(90, 200, 120, 0.9)"
    evil_bg, evil_bd = "rgba(110, 28, 28, 0.40)", "1px solid rgba(220, 90, 90, 0.9)"
    battle_bg, battle_bd = "rgba(200, 200, 200, 0.38)", "1px solid rgba(170, 170, 170, 0.85)"
    enh_bg, enh_bd = "transparent", "1px solid rgba(210, 210, 210, 0.35)"
    art_bg, art_bd = "rgba(25, 55, 130, 0.40)", "1px solid rgba(100, 150, 230, 0.9)"
    hand_bg = "rgba(0, 0, 0, 0.32)"
    lob_bg = "rgba(70, 20, 70, 0.32)"

    regions = {
        "playerN+1Hand": row_region("playerN+1Hand", 0, p2_hand_top, play_w, p2_hand_h, hand_bg, ZONE_BORDER, "fan", True),
        "playerN+1EvilTerritory": row_region("playerN+1EvilTerritory", 0, p2_terr_top, evil_w, p2_terr_h, evil_bg, evil_bd),
        "playerN+1GoodTerritory": row_region("playerN+1GoodTerritory", evil_w, p2_terr_top, good_w, p2_terr_h, good_bg, good_bd),
        "playerN+1LandOfBondage": row_region("playerN+1LandOfBondage", lob_left, p2_terr_top, lob_w, p2_terr_h, lob_bg, BONDAGE_BORDER),
        "playerN+1BattleEnhancements": row_region("playerN+1BattleEnhancements", 0, p2_battle_top, enh_w, p2_battle_h, enh_bg, enh_bd),
        "playerN+1Battle": row_region("playerN+1Battle", enh_w, p2_battle_top, battle_w, p2_battle_h, battle_bg, battle_bd),
        "playerN+1Artifacts": row_region("playerN+1Artifacts", art_left, p2_battle_top, art_w, p2_battle_h, art_bg, art_bd),
        "playerNBattleEnhancements": row_region("playerNBattleEnhancements", 0, p1_battle_top, enh_w, p1_battle_h, enh_bg, enh_bd),
        "playerNBattle": row_region("playerNBattle", enh_w, p1_battle_top, battle_w, p1_battle_h, battle_bg, battle_bd),
        "playerNArtifacts": row_region("playerNArtifacts", art_left, p1_battle_top, art_w, p1_battle_h, art_bg, art_bd),
        "playerNGoodTerritory": row_region("playerNGoodTerritory", 0, p1_terr_top, good_w, p1_terr_h, good_bg, good_bd),
        "playerNEvilTerritory": row_region("playerNEvilTerritory", good_w, p1_terr_top, evil_w, p1_terr_h, evil_bg, evil_bd),
        "playerNLandOfBondage": row_region("playerNLandOfBondage", lob_left, p1_terr_top, lob_w, p1_terr_h, lob_bg, BONDAGE_BORDER),
        "playerNHand": row_region("playerNHand", 0, p1_hand_top, lob_left, p1_hand_h, hand_bg, ZONE_BORDER, "fan", True),
        "playerN+1Deck": pile("playerN+1Deck", col1, 12.0, pile_w),
        "playerN+1Discard": pile("playerN+1Discard", col2, 12.0, pile_w),
        "playerN+1Reserve": pile("playerN+1Reserve", col1, 23.5, pile_w),
        "playerN+1LandOfRedemption": pile("playerN+1LandOfRedemption", col2, 23.5, pile_w),
        "playerN+1Banished": pile("playerN+1Banished", col1, 35.0, pile_w),
        "playerN+1Tokens": pile("playerN+1Tokens", col2, 35.0, pile_w),
        "playerNDeck": pile("playerNDeck", col1, 56.0, pile_w),
        "playerNDiscard": pile("playerNDiscard", col2, 56.0, pile_w),
        "playerNReserve": pile("playerNReserve", col1, 67.5, pile_w),
        "playerNLandOfRedemption": pile("playerNLandOfRedemption", col2, 67.5, pile_w),
        "playerNBanished": pile("playerNBanished", col1, 79.0, pile_w),
        "playerNTokens": pile("playerNTokens", col2, 79.0, pile_w),
        "sharedSetAside": row_region(
            "sharedSetAside",
            col1,
            90.0,
            pile_w * 2,
            10.0,
            "rgba(0, 0, 0, 0.45)",
            ZONE_BORDER,
            "fan",
            True,
        ),
    }
    table_buttons = {
        "draw": {
            "actionList": "drawCard",
            "label": "Draw",
            "left": pct(col1),
            "top": "47%",
            "width": pct(pile_w),
            "height": "4%",
        },
        "draw8": {
            "actionList": "drawEight",
            "label": "Draw 8",
            "left": pct(col2),
            "top": "47%",
            "width": pct(pile_w),
            "height": "4%",
        },
        "shuffle": {
            "actionList": "shuffleDeck",
            "label": "Shuffle",
            "left": pct(col1),
            "top": "51.5%",
            "width": "4%",
            "height": "4%",
        },
        "roll1d6": {
            "actionList": "roll1d6",
            "label": "d6",
            "left": "92%",
            "top": "51.5%",
            "width": "4%",
            "height": "4%",
        },
        "flipCoin": {
            "actionList": "flipCoin",
            "label": "Coin",
            "left": "96%",
            "top": "51.5%",
            "width": "4%",
            "height": "4%",
        },
    }
    return {
        "layouts": {
            "default": {
                "cardSize": 10,
                "rowSpacing": 1,
                "chat": {
                    "left": pct(lob_left),
                    "top": pct(p1_hand_top),
                    "width": pct(lob_w),
                    "height": pct(p1_hand_h),
                },
                "regions": regions,
                "tableButtons": table_buttons,
            }
        }
    }

def make_card_types(cards: list[dict[str, str]]) -> dict:
    types = {
        kind: {"width": 0.72, "height": 1.0, "tokens": ["green", "red"]}
        for kind in sorted({card["type"] for card in cards})
    }
    return {"cardTypes": types}


def make_browse(cards: list[dict[str, str]]) -> dict:
    return {
        "browse": {
            "filterPropertySideA": "category",
            "filterValuesSideA": BROWSE_FILTERS,
            "textPropertiesSideA": ["name", "text", "brigade", "set", "reference"],
        }
    }


def main() -> int:
    cards, errors = load_cards()
    write_tsv(cards)
    write_json("groups.json", make_groups())
    write_json("layouts.json", make_layouts())
    write_json("cardTypes.json", make_card_types(cards))
    write_json("browse.json", make_browse(cards))
    prebuilts, menu, deck_errors = make_prebuilts(cards)
    errors.extend(deck_errors)
    write_json("preBuiltDecks.json", prebuilts)
    write_json("deckMenu.json", menu)
    stamp_lobby_art(JSONS_DIR, GAME_FOLDER)

    types = sorted({card["type"] for card in cards})
    sets = sorted({card["set"] for card in cards})
    categories = Counter(card["category"] for card in cards)
    print(f"Wrote {len(cards)} cards to {TSV_OUT}")
    print(f"Sets ({len(sets)}): {', '.join(sets)}")
    print(f"Types: {', '.join(types)}")
    print("Browse categories:")
    for name, count in categories.most_common():
        print(f"  {name}: {count}")
    if errors:
        print(f"\n{len(errors)} issue(s):")
        for err in errors[:60]:
            print(f"  - {err}")
        if len(errors) > 60:
            print(f"  ... {len(errors) - 60} more")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
