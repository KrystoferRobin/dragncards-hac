#!/usr/bin/env python3
"""Convert the LackeyCCG MyLittlePonyKayou plugin into a DragnCards dumb table."""

from __future__ import annotations

import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:\Users\chris\Documents\e-Sword\dragncards")
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from image_names import TOYBOX_PREFIX, clear_image_url_prefix, lobby_art_urls, plugin_art_rel, toybox_url  # noqa: E402

LACKEY_DIR = Path(r"C:\Users\chris\Documents\e-Sword\tests\LackeyCCG\plugins\MyLittlePonyKayou")
PLUGIN_DIR = ROOT / "my-little-pony-dragncards-plugin"
SETS_DIR = LACKEY_DIR / "sets"
DECKS_DIR = LACKEY_DIR / "decks"
JSONS_DIR = PLUGIN_DIR / "jsons"
TSV_OUT = PLUGIN_DIR / "tsvs" / "cards.tsv"

PLUGIN_NAME = "My Little Pony"
GAME_FOLDER = "my-little-pony"
GAME_PASCAL = "MyLittlePony"

CARD_BACK_URL = (
    "https://dl.dropboxusercontent.com/scl/fi/g3td1ciqkm0j8fyppzl1m/cardback.jpg"
    "?rlkey=9n5cke9xhygp6pnsgyva56bka&st=n4g1mu0r"
)
BACKGROUND_URL = toybox_url(plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "background", ".jpg"))

ZONE_BORDER = "1px solid rgba(40, 40, 40, 0.30)"
PLAYMAT_FILL = "rgba(255, 255, 255, 0.04)"
PILE_FILL = "rgba(0, 0, 0, 0.12)"

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "set",
    "rarity",
    "cost",
    "keywords",
    "inspiration",
    "stage",
    "subtitle",
    "text",
    "loadGroupId",
]

LOAD_BY_TYPE = {
    "Main Character": "playerNMC",
    "Scene": "playerNSceneDeck",
    "Story": "playerNStoryDeck",
}

SUPERZONE_TO_GROUP = {
    "Deck": "playerNDeck",
    "Scene Deck": "playerNSceneDeck",
    "Story Deck": "playerNStoryDeck",
    "MC": "playerNMC",
}


def sanitize(value: str) -> str:
    return (value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()


def fold_name(value: str) -> str:
    text = sanitize(value)
    text = text.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return text.casefold()


def abs_url(url: str) -> str:
    url = sanitize(url)
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def slug(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", text).strip()
    parts = cleaned.split()
    if not parts:
        return "deck"
    return parts[0].lower() + "".join(part.title() for part in parts[1:])


def col(row: dict[str, str], *names: str) -> str:
    for name in names:
        if name in row:
            return sanitize(row[name])
    return ""


def ability_text(*parts: str) -> str:
    bits = []
    for part in parts:
        text = sanitize(part)
        if text and text != "-":
            bits.append(text)
    return " ".join(bits)


def load_image_map() -> dict[str, str]:
    urls: dict[str, str] = {}
    for path in sorted(LACKEY_DIR.glob("CardImageURLs*.txt")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "\t" not in line or line.lower().startswith("cardimage"):
                continue
            key, url = line.split("\t", 1)
            key = key.strip().replace("\\", "/")
            resolved = abs_url(url)
            if not key or not resolved:
                continue
            urls[key] = resolved
            name = Path(key).name
            urls[name] = resolved
            urls[Path(name).stem] = resolved
    return urls


def image_url_for(image_file: str, set_name: str, urls: dict[str, str]) -> str:
    image_file = sanitize(image_file)
    set_name = sanitize(set_name)
    for key in (
        f"{set_name}/{image_file}.jpg",
        f"{set_name}/{image_file}",
        f"{image_file}.jpg",
        image_file,
    ):
        if key in urls:
            return urls[key]
    return ""


def load_group_for(card_type: str) -> str:
    return LOAD_BY_TYPE.get(card_type, "playerNDeck")


def load_cards(urls: dict[str, str]) -> tuple[list[dict[str, str]], list[str]]:
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
            name = col(row, "Name", "Main Title")
            set_name = col(row, "Set")
            image_file = col(row, "Imagefile", "ImageFile")
            card_type = col(row, "Type") or "Character"
            if not name or not image_file:
                errors.append(f"{path.name}:{line_no} missing name or Imagefile")
                continue
            database_id = image_file
            if database_id in seen_ids:
                errors.append(f"Duplicate databaseId {database_id} at {path.name}:{line_no}")
                continue
            seen_ids.add(database_id)
            image_url = image_url_for(image_file, set_name, urls)
            if not image_url:
                errors.append(f"{path.name}:{line_no} no image URL for {set_name}/{image_file}")
            cards.append(
                {
                    "databaseId": database_id,
                    "name": name,
                    "imageUrl": image_url,
                    "cardBack": "default",
                    "type": card_type,
                    "set": set_name,
                    "rarity": col(row, "Rareness", "Rarity"),
                    "cost": col(row, "Cost"),
                    "keywords": col(row, "Keywords"),
                    "inspiration": col(row, "Inspiration", "Insp"),
                    "stage": col(row, "Stage Mark"),
                    "subtitle": col(row, "Subtitle"),
                    "text": ability_text(
                        col(row, "Ability 1", "Ability"),
                        col(row, "Ability 2"),
                    ),
                    "loadGroupId": load_group_for(card_type),
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
    def enter(deck: str, extra: dict | None = None) -> dict:
        data = {
            "controller": pid,
            "deckGroupId": f"{pid}{deck}",
            "discardGroupId": f"{pid}Retire",
        }
        if extra:
            data.update(extra)
        return data

    return {
        f"{pid}Deck": {
            "groupType": "deck",
            "label": f"Player {n} Deck",
            "tableLabel": "Deck",
            "onCardEnter": enter("Deck"),
        },
        f"{pid}SceneDeck": {
            "groupType": "sceneDeck",
            "label": f"Player {n} Scene Deck",
            "tableLabel": "Scenes",
            "onCardEnter": enter("SceneDeck"),
        },
        f"{pid}StoryDeck": {
            "groupType": "storyDeck",
            "label": f"Player {n} Story Deck",
            "tableLabel": "Stories",
            "onCardEnter": enter("StoryDeck"),
        },
        f"{pid}MC": {
            "groupType": "mc",
            "label": f"Player {n} Main Character",
            "tableLabel": "MC",
            "canHaveAttachments": True,
            "onCardEnter": enter("MC", {"inPlay": True}),
        },
        f"{pid}Hand": {
            "groupType": "hand",
            "label": f"Player {n} Hand",
            "tableLabel": "Hand",
            "onCardEnter": enter("Deck"),
        },
        f"{pid}Lane1": {
            "groupType": "inPlay",
            "label": f"Player {n} Lane 1",
            "tableLabel": "Lane 1",
            "canHaveAttachments": True,
            "onCardEnter": enter("Deck", {"inPlay": True}),
        },
        f"{pid}Lane2": {
            "groupType": "inPlay",
            "label": f"Player {n} Lane 2",
            "tableLabel": "Lane 2",
            "canHaveAttachments": True,
            "onCardEnter": enter("Deck", {"inPlay": True}),
        },
        f"{pid}Lane3": {
            "groupType": "inPlay",
            "label": f"Player {n} Lane 3",
            "tableLabel": "Lane 3",
            "canHaveAttachments": True,
            "onCardEnter": enter("Deck", {"inPlay": True}),
        },
        f"{pid}Scenes": {
            "groupType": "scenes",
            "label": f"Player {n} Scene Area",
            "tableLabel": "Scene Area",
            "canHaveAttachments": False,
            "onCardEnter": enter("SceneDeck", {"inPlay": True}),
        },
        f"{pid}Story": {
            "groupType": "story",
            "label": f"Player {n} Story",
            "tableLabel": "Story",
            "canHaveAttachments": False,
            "onCardEnter": enter("StoryDeck", {"inPlay": True}),
        },
        f"{pid}Plans": {
            "groupType": "plans",
            "label": f"Player {n} Plans",
            "tableLabel": "Plans",
            "onCardEnter": enter("Deck"),
        },
        f"{pid}Retire": {
            "groupType": "retire",
            "label": f"Player {n} Retire",
            "tableLabel": "Retire",
            "onCardEnter": enter("Deck"),
        },
    }


def make_groups() -> dict:
    groups = {}
    groups.update(player_groups("player1", "1"))
    groups.update(player_groups("player2", "2"))
    return {"groups": groups}


def playmat_style(fill: str = PLAYMAT_FILL) -> dict:
    return {"background": fill, "border": ZONE_BORDER, "boxSizing": "border-box"}


def slot(
    group_id: str,
    left: float,
    top: float,
    width: float,
    height: float,
    region_type: str = "pile",
    hide_title: bool = False,
    disable_attachments: bool = False,
    fill: str = PLAYMAT_FILL,
) -> dict:
    region = {
        "groupId": group_id,
        "type": region_type,
        "direction": "horizontal",
        "left": pct(left),
        "top": pct(top),
        "width": pct(width),
        "height": pct(height),
        "style": playmat_style(fill),
    }
    if hide_title:
        region["hideTitle"] = True
    if disable_attachments:
        region["disableDroppableAttachments"] = True
    return region


def make_layouts() -> dict:
    # Boxes measured from MyLittlePony-Background.jpg (2000x1000 playmat).
    # Opponent is the cream half (top), you are the lavender half (bottom).
    regions = {
        "playerN+1Story": slot("playerN+1Story", 29.0, 3.8, 42.0, 22.2, "row", True, True),
        "playerN+1Lane1": slot("playerN+1Lane1", 32.0, 27.8, 7.1, 20.2, "row"),
        "playerN+1Lane2": slot("playerN+1Lane2", 45.5, 27.8, 7.0, 20.2, "row"),
        "playerN+1Lane3": slot("playerN+1Lane3", 59.0, 27.8, 7.1, 20.2, "row"),
        "playerN+1Hand": slot("playerN+1Hand", 74.0, 3.8, 24.2, 11.5, "fan", False, True, PILE_FILL),
        "playerN+1Scenes": slot("playerN+1Scenes", 74.0, 15.6, 24.2, 32.4, "row", True, True),
        "playerN+1Deck": slot("playerN+1Deck", 2.6, 4.4, 11.2, 10.2, fill=PILE_FILL),
        "playerN+1MC": slot("playerN+1MC", 14.4, 4.4, 11.2, 10.2),
        "playerN+1SceneDeck": slot("playerN+1SceneDeck", 2.6, 15.0, 11.2, 10.2, fill=PILE_FILL),
        "playerN+1Plans": slot("playerN+1Plans", 14.4, 15.0, 11.2, 10.2, fill=PILE_FILL),
        "playerN+1StoryDeck": slot("playerN+1StoryDeck", 2.6, 25.6, 11.2, 10.2, fill=PILE_FILL),
        "playerN+1Retire": slot("playerN+1Retire", 14.4, 25.6, 11.2, 10.2, fill=PILE_FILL),
        "playerNLane1": slot("playerNLane1", 32.0, 51.5, 7.1, 20.5, "row"),
        "playerNLane2": slot("playerNLane2", 45.5, 51.5, 7.0, 20.5, "row"),
        "playerNLane3": slot("playerNLane3", 59.0, 51.5, 7.1, 20.5, "row"),
        "playerNStory": slot("playerNStory", 28.9, 73.8, 42.2, 22.2, "row", True, True),
        "playerNScenes": slot("playerNScenes", 2.0, 51.8, 24.0, 32.0, "row", True, True),
        "playerNHand": slot("playerNHand", 2.0, 84.2, 24.0, 11.8, "fan", False, True, PILE_FILL),
        "playerNMC": slot("playerNMC", 74.6, 52.4, 11.2, 10.5),
        "playerNDeck": slot("playerNDeck", 86.4, 52.4, 11.2, 10.5, fill=PILE_FILL),
        "playerNPlans": slot("playerNPlans", 74.6, 63.4, 11.2, 10.5, fill=PILE_FILL),
        "playerNSceneDeck": slot("playerNSceneDeck", 86.4, 63.4, 11.2, 10.5, fill=PILE_FILL),
        "playerNRetire": slot("playerNRetire", 74.6, 74.4, 11.2, 10.5, fill=PILE_FILL),
        "playerNStoryDeck": slot("playerNStoryDeck", 86.4, 74.4, 11.2, 10.5, fill=PILE_FILL),
    }
    btn_left, btn_w, btn_h = 67.0, 6.6, 3.2
    table_buttons = {}
    for index, (key, action, label) in enumerate(
        (
            ("drawDeck", "drawDeck", "Draw"),
            ("addScene", "addScene", "Scene"),
            ("untapAll", "untapAll", "Untap"),
            ("roll1d6", "roll1d6", "d6"),
            ("addPlan", "addPlan", "Plan"),
            ("takePlan", "takePlan", "Take"),
        )
    ):
        table_buttons[key] = {
            "actionList": action,
            "label": label,
            "left": pct(btn_left),
            "top": pct(52.0 + index * 3.4),
            "width": pct(btn_w),
            "height": pct(btn_h),
        }
    return {
        "layouts": {
            "default": {
                "cardSize": 8,
                "rowSpacing": 1,
                "chat": {"left": "75%", "top": "86%", "width": "24%", "height": "13%"},
                "regions": regions,
                "tableButtons": table_buttons,
            }
        }
    }


def make_card_types(cards: list[dict[str, str]]) -> dict:
    types = {
        kind: {"width": 0.72, "height": 1.0, "tokens": ["green"]}
        for kind in sorted({card["type"] for card in cards})
    }
    return {"cardTypes": types}


def make_card_backs() -> dict:
    return {"cardBacks": {"default": {"width": 0.72, "height": 1.0, "imageUrl": CARD_BACK_URL}}}


def make_browse(cards: list[dict[str, str]]) -> dict:
    types = sorted({card["type"] for card in cards})
    return {
        "browse": {
            "filterPropertySideA": "type",
            "filterValuesSideA": types,
            "textPropertiesSideA": ["name", "text", "keywords", "set", "cost", "inspiration", "subtitle"],
        }
    }


def make_main() -> dict:
    main = {
        "pluginName": PLUGIN_NAME,
        "tutorialUrl": "",
        "backgroundUrl": BACKGROUND_URL,
        "loadPreBuiltOnNewGame": False,
    }
    main.update(lobby_art_urls(GAME_FOLDER))
    return main


def stage_green_token() -> None:
    src_candidates = [
        PLUGIN_DIR / "scripts" / "_token-green-src.png",
        ROOT / "images" / "wyvern" / "_plugin" / "Wyvern-TokenGreen.png",
        ROOT / "DragnCards" / "frontend" / "public" / "images" / "tokens" / "resource.png",
    ]
    rel = plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "token-green", ".png")
    dest = ROOT / "images" / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    for src in src_candidates:
        if src.exists():
            shutil.copy2(src, dest)
            return
    raise SystemExit("No source PNG found for the green counter token")


def parse_dek(path: Path) -> dict[str, Counter]:
    text = path.read_text(encoding="utf-8", errors="replace")
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
    by_id: dict[str, str],
    by_id_unique: dict[str, str],
    by_name: dict[str, list[str]],
) -> str | None:
    key = (fold_name(set_name), image_id)
    if image_id and key in by_id:
        return by_id[key]
    if image_id and image_id in by_id_unique:
        return by_id_unique[image_id]
    matches = by_name.get(fold_name(card_name), [])
    if len(matches) == 1:
        return matches[0]
    return None


def make_prebuilts(cards: list[dict[str, str]]) -> tuple[dict, dict, list[str]]:
    by_id = {(fold_name(card["set"]), card["databaseId"]): card["databaseId"] for card in cards}
    by_id_unique: dict[str, str] = {}
    id_counts: Counter = Counter(card["databaseId"] for card in cards)
    for card in cards:
        if id_counts[card["databaseId"]] == 1:
            by_id_unique[card["databaseId"]] = card["databaseId"]
    by_name: dict[str, list[str]] = {}
    for card in cards:
        by_name.setdefault(fold_name(card["name"]), []).append(card["databaseId"])
    errors: list[str] = []
    prebuilts: dict[str, dict] = {}
    section_lists: list[dict] = []
    for path in sorted(DECKS_DIR.glob("*.dek")):
        label = path.stem.replace("_", " ")
        deck_id = slug(path.stem)
        zones = parse_dek(path)
        load_list: list[dict] = []
        for zone_name, counts in zones.items():
            load_group = SUPERZONE_TO_GROUP.get(zone_name)
            if not load_group:
                errors.append(f"{path.name}: unknown superzone '{zone_name}'")
                continue
            for (image_id, card_name, set_name), quantity in counts.items():
                database_id = resolve_card(image_id, card_name, set_name, by_id, by_id_unique, by_name)
                if not database_id:
                    errors.append(f"{path.name}: unknown card {card_name!r} ({set_name}/{image_id})")
                    continue
                load_list.append({"databaseId": database_id, "quantity": quantity, "loadGroupId": load_group})
        if not load_list:
            errors.append(f"{path.name}: no cards loaded")
            continue
        prebuilts[deck_id] = {"label": label, "cards": load_list}
        section_lists.append({"label": label, "deckListId": deck_id})
    menu = [{"label": "Starter Decks", "deckLists": section_lists}] if section_lists else []
    return {"preBuiltDecks": prebuilts}, {"deckMenu": {"subMenus": menu}}, errors


def main() -> int:
    urls = load_image_map()
    cards, errors = load_cards(urls)
    write_tsv(cards)
    write_json("groups.json", make_groups())
    write_json("layouts.json", make_layouts())
    write_json("cardTypes.json", make_card_types(cards))
    write_json("cardBacks.json", make_card_backs())
    write_json("browse.json", make_browse(cards))
    write_json("main.json", make_main())
    clear_image_url_prefix(JSONS_DIR)
    prebuilts, menu, deck_errors = make_prebuilts(cards)
    errors.extend(deck_errors)
    write_json("preBuiltDecks.json", prebuilts)
    write_json("deckMenu.json", menu)
    stage_green_token()

    types = sorted({card["type"] for card in cards})
    sets = sorted({card["set"] for card in cards})
    print(f"Wrote {len(cards)} cards to {TSV_OUT}")
    print(f"Image map entries: {len(urls)}")
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
