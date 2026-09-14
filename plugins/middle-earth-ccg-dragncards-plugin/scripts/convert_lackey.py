#!/usr/bin/env python3
"""Convert the LackeyCCG meccg plugin into a DragnCards Middle Earth CCG table."""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from image_names import stamp_lobby_art  # noqa: E402

LACKEY_DIR = Path(r"C:\Users\chris\Documents\e-Sword\tests\LackeyCCG\plugins\meccg")
PLUGIN_DIR = Path(r"C:\Users\chris\Documents\e-Sword\dragncards\middle-earth-ccg-dragncards-plugin")
SETS_DIR = LACKEY_DIR / "sets"
DECKS_DIR = LACKEY_DIR / "decks"
JSONS_DIR = PLUGIN_DIR / "jsons"
TSV_OUT = PLUGIN_DIR / "tsvs" / "cards.tsv"
GAME_FOLDER = "middle-earth-ccg"
UPDATELIST = LACKEY_DIR / "updatelist.txt"

IMAGE_BASE = "https://www.chrisvos.com/meuk/lackey/meccg/sets/setimages/"
CARD_BACK_URL = IMAGE_BASE + "general/cardback.jpg"

ZONE_BORDER = "1px solid rgba(210, 210, 210, 0.55)"

LOCATION_TYPES = {
    "Hero Site",
    "Minion Site",
    "Balrog Site",
    "Fallen-wizard Site",
    "Region",
}

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "set",
    "class",
    "race",
    "skills",
    "homeSite",
    "mind",
    "influence",
    "gi",
    "prowess",
    "body",
    "strikes",
    "playable",
    "mp",
    "sp",
    "magic",
    "specific",
    "corruption",
    "region",
    "sitePath",
    "draw",
    "opponentDraw",
    "rarity",
    "text",
    "loadGroupId",
]

SUPERZONE_TO_GROUP = {
    "Deck": "playerNDeck",
    "Starting Company": "playerNCompany",
    "Location Deck": "playerNLocationDeck",
    "Sideboard": "playerNSideboard",
}

BROWSE_TYPE_ORDER = [
    "Hero Character",
    "Hero Resource",
    "Hero Site",
    "Minion Character",
    "Minion Resource",
    "Minion Site",
    "Hazard",
    "Region",
    "Stage Resource",
    "Fallen-wizard Character",
    "Fallen-wizard Site",
    "Balrog Character",
    "Balrog Site",
]


def sanitize(value: str) -> str:
    return (value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()


def fold_name(value: str) -> str:
    text = sanitize(value)
    text = text.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return text.casefold()


def slug(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", text).strip()
    parts = cleaned.split()
    if not parts:
        return "deck"
    return parts[0].lower() + "".join(part.title() for part in parts[1:])


def col(row: dict[str, str], *names: str) -> str:
    lowered = {key.lower(): key for key in row}
    for name in names:
        actual = row.get(name)
        if actual is None:
            key = lowered.get(name.lower())
            actual = row.get(key, "") if key else ""
        cleaned = sanitize(actual)
        if cleaned:
            return cleaned
    return ""


def load_image_urls() -> dict[str, str]:
    urls: dict[str, str] = {}
    if not UPDATELIST.exists():
        return urls
    in_section = False
    for line in UPDATELIST.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("CardImageURLs"):
            in_section = True
            continue
        if line.startswith("CardGeneralURLs"):
            break
        if not in_section or "\t" not in line:
            continue
        rel, url = line.split("\t", 1)
        urls[rel.strip().replace("\\", "/")] = sanitize(url).replace("http://", "https://")
    return urls


def image_url(set_name: str, image_file: str, hosted: dict[str, str]) -> str:
    filename = sanitize(image_file)
    if "." not in Path(filename).name:
        filename = f"{filename}.jpg"
    rel = f"{sanitize(set_name)}/{filename}"
    if rel in hosted:
        return hosted[rel]
    return IMAGE_BASE + rel.replace("\\", "/")


def load_group_id(card_type: str) -> str:
    if card_type in LOCATION_TYPES:
        return "playerNLocationDeck"
    return "playerNDeck"


def load_cards() -> tuple[list[dict[str, str]], list[str]]:
    hosted = load_image_urls()
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for path in sorted(SETS_DIR.glob("*.txt")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines:
            continue
        header = [h.strip() for h in lines[0].split("\t")]
        for line_no, line in enumerate(lines[1:], start=2):
            if not line.strip():
                continue
            values = line.split("\t")
            while len(values) < len(header):
                values.append("")
            row = {header[i]: values[i] for i in range(len(header))}
            name = col(row, "Name")
            set_name = col(row, "Set")
            image_file = col(row, "Imagefile", "ImageFile")
            card_type = col(row, "Type") or "Resource"
            if not name or not image_file:
                errors.append(f"{path.name}:{line_no} missing name or Imagefile")
                continue
            database_id = f"{set_name}_{image_file}"
            if database_id in seen_ids:
                errors.append(f"Duplicate databaseId {database_id} at {path.name}:{line_no}")
                continue
            seen_ids.add(database_id)
            cards.append(
                {
                    "databaseId": database_id,
                    "name": name,
                    "imageUrl": image_url(set_name, image_file, hosted),
                    "cardBack": "default",
                    "type": card_type,
                    "set": set_name,
                    "class": col(row, "Class"),
                    "race": col(row, "Race"),
                    "skills": col(row, "Skills"),
                    "homeSite": col(row, "HomeSite"),
                    "mind": col(row, "Mind"),
                    "influence": col(row, "Influence"),
                    "gi": col(row, "GI"),
                    "prowess": col(row, "Prowess"),
                    "body": col(row, "Body"),
                    "strikes": col(row, "Strikes"),
                    "playable": col(row, "Playable"),
                    "mp": col(row, "MP"),
                    "sp": col(row, "SP"),
                    "magic": col(row, "Magic"),
                    "specific": col(row, "Specific"),
                    "corruption": col(row, "Corruption"),
                    "region": col(row, "Region"),
                    "sitePath": col(row, "SitePath"),
                    "draw": col(row, "Draw"),
                    "opponentDraw": col(row, "OpponentDraw"),
                    "rarity": col(row, "Rarity"),
                    "text": col(row, "Text"),
                    "loadGroupId": load_group_id(card_type),
                    "_imageFile": image_file,
                }
            )
    return cards, errors


def write_tsv(cards: list[dict[str, str]]) -> None:
    TSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = ["\t".join(TSV_COLUMNS)]
    for card in cards:
        rows.append("\t".join(sanitize(card.get(column, "")) for column in TSV_COLUMNS))
    TSV_OUT.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_json(name: str, payload: dict) -> None:
    JSONS_DIR.mkdir(parents=True, exist_ok=True)
    path = JSONS_DIR / name
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def pct(value: float) -> str:
    return f"{value:g}%"


def region_style(background: str, border: str = ZONE_BORDER) -> dict:
    return {"background": background, "border": border, "boxSizing": "border-box"}


def pile(group_id: str, left: float, top: float, width: float = 8.0, height: float = 11.0) -> dict:
    return {
        "groupId": group_id,
        "type": "pile",
        "direction": "horizontal",
        "left": pct(left),
        "top": pct(top),
        "width": pct(width),
        "height": pct(height),
        "style": region_style("rgba(0, 0, 0, 0.35)"),
    }


def row_region(
    group_id: str,
    left: float,
    top: float,
    width: float,
    height: float,
    background: str,
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
        "style": region_style(background),
    }
    if disable_attachments:
        region["disableDroppableAttachments"] = True
    return region


def player_groups(pid: str, n: str) -> dict:
    def enter(extra: dict | None = None) -> dict:
        data = {
            "controller": pid,
            "deckGroupId": f"{pid}Deck",
            "discardGroupId": f"{pid}Discard",
        }
        if extra:
            data.update(extra)
        return data

    return {
        f"{pid}Deck": {
            "groupType": "deck",
            "label": f"Player {n} Deck",
            "tableLabel": "Deck",
            "onCardEnter": enter(),
        },
        f"{pid}Discard": {
            "groupType": "discard",
            "label": f"Player {n} Discard",
            "tableLabel": "Discard",
            "onCardEnter": enter(),
        },
        f"{pid}OutOfPlay": {
            "groupType": "outOfPlay",
            "label": f"Player {n} Out of Play",
            "tableLabel": "OOP",
            "onCardEnter": enter(),
        },
        f"{pid}Sideboard": {
            "groupType": "sideboard",
            "label": f"Player {n} Sideboard",
            "tableLabel": "Side",
            "onCardEnter": enter(),
        },
        f"{pid}LocationDeck": {
            "groupType": "locationDeck",
            "label": f"Player {n} Location Deck",
            "tableLabel": "Loc",
            "onCardEnter": enter(),
        },
        f"{pid}Hand": {
            "groupType": "hand",
            "label": f"Player {n} Hand",
            "tableLabel": "Hand",
            "onCardEnter": enter(),
        },
        f"{pid}Company": {
            "groupType": "inPlay",
            "label": f"Player {n} Company",
            "tableLabel": "Company",
            "canHaveAttachments": True,
            "onCardEnter": enter({"inPlay": True}),
        },
        f"{pid}Site": {
            "groupType": "inPlay",
            "label": f"Player {n} Site",
            "tableLabel": "Site",
            "canHaveAttachments": False,
            "onCardEnter": enter({"inPlay": True}),
        },
        f"{pid}Events": {
            "groupType": "inPlay",
            "label": f"Player {n} Events",
            "tableLabel": "Events",
            "canHaveAttachments": False,
            "onCardEnter": enter({"inPlay": True}),
        },
        f"{pid}Tokens": {
            "groupType": "tokens",
            "label": f"Player {n} Tokens",
            "tableLabel": "Tokens",
            "onCardEnter": enter(),
        },
    }


def make_groups() -> dict:
    groups = {
        "sharedSetAside": {
            "groupType": "aside",
            "label": "Set Aside",
            "tableLabel": "Set Aside",
            "onCardEnter": {"controller": "shared"},
        }
    }
    groups.update(player_groups("player1", "1"))
    groups.update(player_groups("player2", "2"))
    return {"groups": groups}


def make_layouts() -> dict:
    play_w = 81.0
    pile_w = 8.0
    col1, col2 = 82.0, 91.0
    company_w = 68.0
    site_w = play_w - company_w
    hand_w = 64.0
    chat_left = hand_w
    chat_w = play_w - chat_left
    hand_bg = "rgba(0, 0, 0, 0.32)"
    event_bg = "rgba(70, 30, 30, 0.36)"
    company_bg = "rgba(40, 60, 35, 0.36)"
    site_bg = "rgba(70, 55, 30, 0.40)"
    regions = {
        "playerN+1Hand": row_region("playerN+1Hand", 0, 0, play_w, 8, hand_bg, "fan", True),
        "playerN+1Events": row_region("playerN+1Events", 0, 8, play_w, 8, event_bg, "row", True),
        "playerN+1Company": row_region("playerN+1Company", 0, 16, company_w, 16, company_bg),
        "playerN+1Site": row_region("playerN+1Site", company_w, 16, site_w, 16, site_bg, "row", True),
        "playerNSite": row_region("playerNSite", company_w, 32, site_w, 16, site_bg, "row", True),
        "playerNCompany": row_region("playerNCompany", 0, 32, company_w, 16, company_bg),
        "playerNEvents": row_region("playerNEvents", 0, 48, play_w, 8, event_bg, "row", True),
        "playerNHand": row_region("playerNHand", 0, 56, chat_left, 44, hand_bg, "fan", True),
        "playerN+1LocationDeck": pile("playerN+1LocationDeck", col1, 8.0, pile_w),
        "playerN+1Deck": pile("playerN+1Deck", col2, 8.0, pile_w),
        "playerN+1Discard": pile("playerN+1Discard", col1, 19.5, pile_w),
        "playerN+1OutOfPlay": pile("playerN+1OutOfPlay", col2, 19.5, pile_w),
        "playerN+1Sideboard": pile("playerN+1Sideboard", col1, 31.0, pile_w),
        "playerNLocationDeck": pile("playerNLocationDeck", col1, 56.0, pile_w),
        "playerNDeck": pile("playerNDeck", col2, 56.0, pile_w),
        "playerNDiscard": pile("playerNDiscard", col1, 67.5, pile_w),
        "playerNOutOfPlay": pile("playerNOutOfPlay", col2, 67.5, pile_w),
        "playerNSideboard": pile("playerNSideboard", col1, 79.0, pile_w),
        "playerNTokens": pile("playerNTokens", col2, 79.0, pile_w),
        "sharedSetAside": row_region("sharedSetAside", col1, 90.0, pile_w * 2 + 1, 10.0, "rgba(0, 0, 0, 0.45)", "fan", True),
    }
    table_buttons = {
        "drawDeck": {
            "actionList": "drawDeck",
            "label": "Draw",
            "left": pct(col1),
            "top": "47%",
            "width": pct(pile_w),
            "height": "4%",
        },
        "shuffleDeck": {
            "actionList": "shuffleDeck",
            "label": "Shuf",
            "left": pct(col2),
            "top": "47%",
            "width": pct(pile_w),
            "height": "4%",
        },
        "untapAll": {
            "actionList": "untapAll",
            "label": "Untap",
            "left": pct(col1),
            "top": "51.5%",
            "width": pct(pile_w),
            "height": "4%",
        },
        "roll1d6": {
            "actionList": "roll1d6",
            "label": "d6",
            "left": pct(col2),
            "top": "51.5%",
            "width": pct(pile_w),
            "height": "4%",
        },
    }
    return {
        "layouts": {
            "default": {
                "cardSize": 9,
                "rowSpacing": 1,
                "chat": {"left": pct(chat_left), "top": "56%", "width": pct(chat_w), "height": "44%"},
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


def make_card_backs() -> dict:
    return {"cardBacks": {"default": {"width": 0.72, "height": 1.0, "imageUrl": CARD_BACK_URL}}}


def make_browse(cards: list[dict[str, str]]) -> dict:
    present = {card["type"] for card in cards}
    filter_values = [kind for kind in BROWSE_TYPE_ORDER if kind in present]
    extra = sorted(present - set(filter_values))
    return {
        "browse": {
            "filterPropertySideA": "type",
            "filterValuesSideA": filter_values + extra,
            "textPropertiesSideA": ["name", "text", "class", "race", "skills", "set", "playable"],
        }
    }


def parse_dek(path: Path) -> dict[str, Counter]:
    text = path.read_bytes().decode("iso-8859-1")
    text = re.sub(r"<!DOCTYPE[^>]*>", "", text, count=1)
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        root = ET.fromstring(f"<root>{text}</root>")
    zones: dict[str, Counter] = {}
    for superzone in root.findall(".//superzone"):
        zone_name = superzone.attrib.get("name", "").strip()
        counts: Counter = Counter()
        for card in superzone.findall("card"):
            name_el = card.find("name")
            set_el = card.find("set")
            if name_el is None:
                continue
            image_id = (name_el.attrib.get("id") or "").strip()
            card_name = sanitize(name_el.text or "")
            set_name = sanitize(set_el.text if set_el is not None else "")
            counts[(image_id, card_name, set_name)] += 1
        zones[zone_name] = counts
    return zones


def resolve_card(
    image_id: str,
    card_name: str,
    set_name: str,
    by_set_img: dict[tuple[str, str], str],
    by_img: dict[str, list[str]],
    by_name_set: dict[tuple[str, str], list[str]],
    by_name: dict[str, list[str]],
) -> str | None:
    set_img = (fold_name(set_name), fold_name(image_id))
    if image_id and set_name and set_img in by_set_img:
        return by_set_img[set_img]
    img_matches = by_img.get(fold_name(image_id), [])
    if len(img_matches) == 1:
        return img_matches[0]
    name_set = by_name_set.get((fold_name(card_name), fold_name(set_name)), [])
    if len(name_set) == 1:
        return name_set[0]
    matches = by_name.get(fold_name(card_name), [])
    if len(matches) == 1:
        return matches[0]
    return None


def deck_label(stem: str) -> tuple[str, str]:
    match = re.match(r"ChallengeDeck_([A-J])_(Hero|Minion)_(.+?)(?:_\(.*\))?$", stem)
    if match:
        letter, side, rest = match.groups()
        name = rest.replace("-", " ").replace("_", " ")
        return side, f"{letter} {side}: {name}"
    return "Other", stem.replace("_", " ")


def make_prebuilts(cards: list[dict[str, str]]) -> tuple[dict, dict, list[str]]:
    by_set_img = {
        (fold_name(card["set"]), fold_name(card["_imageFile"])): card["databaseId"] for card in cards
    }
    by_img: dict[str, list[str]] = defaultdict(list)
    by_name_set: dict[tuple[str, str], list[str]] = defaultdict(list)
    by_name: dict[str, list[str]] = defaultdict(list)
    for card in cards:
        by_img[fold_name(card["_imageFile"])].append(card["databaseId"])
        by_name_set[(fold_name(card["name"]), fold_name(card["set"]))].append(card["databaseId"])
        by_name[fold_name(card["name"])].append(card["databaseId"])

    errors: list[str] = []
    prebuilts: dict[str, dict] = {}
    sections: dict[str, list[dict]] = {"Hero": [], "Minion": [], "Other": []}
    for path in sorted(DECKS_DIR.glob("*.dek")):
        side, label = deck_label(path.stem)
        deck_id = slug(path.stem)
        zones = parse_dek(path)
        load_list: list[dict] = []
        for zone_name, counts in zones.items():
            load_group = SUPERZONE_TO_GROUP.get(zone_name)
            if not load_group:
                errors.append(f"{path.name}: unknown superzone '{zone_name}'")
                continue
            for (image_id, card_name, set_name), quantity in counts.items():
                database_id = resolve_card(
                    image_id, card_name, set_name, by_set_img, by_img, by_name_set, by_name
                )
                if not database_id:
                    errors.append(f"{path.name}: unknown card {card_name!r} ({set_name}/{image_id})")
                    continue
                load_list.append({"databaseId": database_id, "quantity": quantity, "loadGroupId": load_group})
        if not load_list:
            errors.append(f"{path.name}: no cards loaded")
            continue
        prebuilts[deck_id] = {"label": label, "cards": load_list}
        sections.setdefault(side, []).append({"label": label, "deckListId": deck_id})

    menu: list[dict] = []
    for section in ("Hero", "Minion", "Other"):
        if sections[section]:
            menu.append({"label": f"{section} Challenge Decks", "deckLists": sections[section]})
    return {"preBuiltDecks": prebuilts}, {"deckMenu": {"subMenus": menu}}, errors


def main() -> int:
    cards, errors = load_cards()
    write_tsv(cards)
    write_json("groups.json", make_groups())
    write_json("layouts.json", make_layouts())
    write_json("cardTypes.json", make_card_types(cards))
    write_json("cardBacks.json", make_card_backs())
    write_json("browse.json", make_browse(cards))
    prebuilts, menu, deck_errors = make_prebuilts(cards)
    errors.extend(deck_errors)
    write_json("preBuiltDecks.json", prebuilts)
    write_json("deckMenu.json", menu)
    stamp_lobby_art(JSONS_DIR, GAME_FOLDER)

    types = sorted({card["type"] for card in cards})
    sets = sorted({card["set"] for card in cards})
    print(f"Wrote {len(cards)} cards to {TSV_OUT}")
    print(f"Sets ({len(sets)}): {', '.join(sets)}")
    print(f"Types: {', '.join(types)}")
    print(f"Pre-built decks: {len(prebuilts['preBuiltDecks'])}")
    if errors:
        print(f"\n{len(errors)} issue(s):")
        for err in errors[:80]:
            print(f"  - {err}")
        if len(errors) > 80:
            print(f"  ... {len(errors) - 80} more")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
