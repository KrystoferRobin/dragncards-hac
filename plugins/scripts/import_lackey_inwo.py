#!/usr/bin/env python3
"""Build a DragnCards INWO plugin from the LackeyCCG plugin.

  python3 plugins/scripts/import_lackey_inwo.py
  python3 plugins/scripts/collect_hosted_images.py inwo
"""

from __future__ import annotations

import json
import re
import shutil
import struct
import zlib
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))
from image_names import (  # noqa: E402
    TOYBOX_PREFIX,
    plugin_art_rel,
    stamp_lobby_art,
    toybox_url,
)

LACKEY = Path("/Volumes/Expand/MegaNZ/LackeyCCG/plugins/INWO")
OUT = ROOT / "inwo"
GAME_FOLDER = "inwo"
GAME_PASCAL = "Inwo"
IMAGES = ROOT / "images"
IMAGE_BASE = "https://raw.githubusercontent.com/MightyBullMoose/LackeyCCG-INWO/main/high/sets/setimages/"
MAX_PLAYERS = 4

SET_LABELS = {
    "Limited": "Limited Edition",
    "Assassins": "Assassins",
    "Subgenius": "SubGenius",
    "German": "German Edition",
    "German 2": "German 2",
    "Virtual": "Virtual",
    "Fan": "Fan Created",
}

NWO_TYPES = {
    "NWOB": "NWO (Blue)",
    "NWOR": "NWO (Red)",
    "NWOY": "NWO (Yellow)",
}

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "deck",
    "alignment",
    "attribute",
    "power",
    "resistance",
    "control",
    "rarity",
    "errata",
    "text",
    "packName",
    "set",
    "loadGroupId",
]

MOVE_GROUPS = [
    "playerNHand",
    "playerNGroupDeck",
    "playerNPlotDeck",
    "playerNLead",
    "playerNPlay",
    "playerNDiscard",
    "playerNRemoved",
    "playerN+1Play",
    "sharedGroups",
    "sharedPlots",
    "sharedSetAside",
]

SUPERZONE_TO_GROUP = {
    "Lead Cards": "playerNLead",
    "Group Deck": "playerNGroupDeck",
    "Plot Deck": "playerNPlotDeck",
    "Shared Groups": "sharedGroups",
    "Shared Plots": "sharedPlots",
}


def dump_json(path: Path, payload: dict | list) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sanitize(value: str) -> str:
    return (value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()


def unescape(value: str) -> str:
    return (
        sanitize(value)
        .replace("&amp;", "&")
        .replace("&apos;", "'")
        .replace("&quot;", '"')
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )


def norm_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", unescape(value).replace("'", "").lower())


def write_color_png(path: Path, rgb: tuple[int, int, int], size: int = 48) -> None:
    red, green, blue = rgb
    raw = b"".join(b"\x00" + bytes([red, green, blue]) * size for _ in range(size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    )


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "deck"


def image_url(stem: str) -> str:
    return IMAGE_BASE + quote(f"{stem}.jpg", safe="-_.")


def normalize_type(card_type: str) -> str:
    card_type = sanitize(card_type).rstrip("!")
    return NWO_TYPES.get(card_type, card_type)


def default_load_group(card_type: str, deck: str) -> str:
    if card_type == "Illuminati":
        return "playerNLead"
    if deck == "Puppet":
        return "playerNGroupDeck"
    return "playerNPlotDeck"


def load_cards() -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    seen: set[str] = set()
    path = LACKEY / "sets" / "carddata.txt"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    header = [h.strip() for h in lines[0].split("\t")]
    if header[:6] != ["Name", "Set", "ImageFile", "Rarity", "Deck", "Type"]:
        errors.append(f"Unexpected carddata header: {header}")
    for line_no, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        cols = line.split("\t")
        while len(cols) < 13:
            cols.append("")
        name = sanitize(cols[0])
        set_name = sanitize(cols[1])
        image_file = sanitize(cols[2])
        rarity = sanitize(cols[3])
        deck = sanitize(cols[4])
        card_type = normalize_type(cols[5])
        if not name or not image_file:
            errors.append(f"Line {line_no}: missing name or ImageFile")
            continue
        front, *back_bits = image_file.split(",")
        stem = sanitize(front)
        back = sanitize(back_bits[0] if back_bits else deck).lower() or "default"
        if back not in {"master", "puppet"}:
            back = "default"
        database_id = f"{set_name}_{stem}"
        if database_id in seen:
            errors.append(f"Duplicate {database_id} at line {line_no}")
            continue
        seen.add(database_id)
        cards.append(
            {
                "databaseId": database_id,
                "name": name,
                "imageUrl": image_url(stem),
                "cardBack": back,
                "type": card_type or "Unknown",
                "deck": deck or back.title(),
                "alignment": sanitize(cols[6]),
                "attribute": sanitize(cols[7]),
                "power": sanitize(cols[8]),
                "resistance": sanitize(cols[9]),
                "control": sanitize(cols[10]),
                "rarity": rarity,
                "errata": sanitize(cols[11]),
                "text": sanitize(cols[12]),
                "packName": SET_LABELS.get(set_name, set_name),
                "set": set_name,
                "loadGroupId": default_load_group(card_type, deck),
                "_stem": stem,
            }
        )
    return cards, errors


def write_tsv(cards: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["\t".join(TSV_COLUMNS)]
    rows.extend("\t".join(sanitize(card.get(col, "")) for col in TSV_COLUMNS) for card in cards)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def parse_dek(path: Path) -> dict[str, Counter]:
    text = path.read_text(encoding="utf-8", errors="replace")
    zones: dict[str, Counter] = {}
    for zone_name, body in re.findall(r'<superzone name="([^"]+)">(.*?)</superzone>', text, flags=re.S | re.I):
        counts: Counter = Counter()
        for match in re.finditer(r"<card>(.*?)</card>", body, flags=re.S | re.I):
            chunk = match.group(1)
            name_el = re.search(r"<name(?:\s[^>]*)?>(.*?)</name>", chunk, flags=re.S | re.I)
            set_el = re.search(r"<set>(.*?)</set>", chunk, flags=re.I)
            if name_el is None or set_el is None:
                continue
            name = unescape(re.sub(r"<[^>]+>", "", name_el.group(1)))
            set_name = unescape(set_el.group(1))
            if name:
                counts[(name, set_name)] += 1
        zones[zone_name] = counts
    return zones


def build_card_index(cards: list[dict[str, str]]) -> dict:
    exact = { (card["name"], card["set"]): card for card in cards }
    fold: dict[tuple[str, str], list[dict]] = defaultdict(list)
    norm_set: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_norm: dict[str, list[dict]] = defaultdict(list)
    for card in cards:
        fold[(card["name"].casefold(), card["set"].casefold())].append(card)
        norm_set[(norm_name(card["name"]), card["set"].casefold())].append(card)
        by_norm[norm_name(card["name"])].append(card)
    return {"exact": exact, "fold": fold, "norm_set": norm_set, "by_norm": by_norm}


def resolve_card(index: dict, name: str, set_name: str) -> dict | None:
    hit = index["exact"].get((name, set_name))
    if hit:
        return hit
    fold_hits = index["fold"].get((name.casefold(), set_name.casefold()), [])
    if len(fold_hits) == 1:
        return fold_hits[0]
    norm_hits = index["norm_set"].get((norm_name(name), set_name.casefold()), [])
    if len(norm_hits) == 1:
        return norm_hits[0]
    name_hits = index["by_norm"].get(norm_name(name), [])
    if set_name in {"", "0", "?"}:
        exact_name = [card for card in name_hits if card["name"] == name]
        if len(exact_name) == 1:
            return exact_name[0]
        if len(name_hits) == 1:
            return name_hits[0]
    if len(name_hits) == 1:
        return name_hits[0]
    return None


def deck_label(filename: str) -> str:
    stem = Path(filename).stem
    if stem.startswith("0BD_"):
        return "One Big Deck: " + stem[4:].replace("_", " ").replace("-", " ").strip()
    return stem.replace("_", " ").strip()


def deck_bucket(filename: str, label: str) -> str:
    stem = Path(filename).stem
    if stem.startswith("0BD_"):
        return "One Big Deck"
    if stem.startswith("Perpetual_Motion") or stem == "Gay_Space_Vampires":
        return "OWE: Perpetual Motion"
    if stem.startswith("Ascension_"):
        return "OWE: Ascension"
    if stem.startswith("Personality_Clash_II"):
        return "OWE: Personality Clash II"
    if stem.startswith("Personality_Clash"):
        return "OWE: Personality Clash"
    return "Standalone"


def convert_decks(cards: list[dict[str, str]]) -> tuple[dict, dict, list[str]]:
    index = build_card_index(cards)
    errors: list[str] = []
    prebuilt: OrderedDict[str, dict] = OrderedDict()
    buckets: dict[str, list[dict]] = OrderedDict()
    used_ids: dict[str, int] = {}
    for dek in sorted((LACKEY / "decks").glob("*.dek")):
        label = deck_label(dek.name)
        deck_id = slug(label)
        used_ids[deck_id] = used_ids.get(deck_id, 0) + 1
        if used_ids[deck_id] > 1:
            deck_id = f"{deck_id}-{used_ids[deck_id]}"
        entries = []
        for zone_name, counts in parse_dek(dek).items():
            load_group = SUPERZONE_TO_GROUP.get(zone_name)
            if not load_group:
                errors.append(f"{dek.name}: unknown superzone {zone_name!r}")
                continue
            for (name, set_name), quantity in counts.items():
                card = resolve_card(index, name, set_name)
                if card is None:
                    errors.append(f"{dek.name}: unknown card {name!r} [{set_name}]")
                    continue
                entries.append(
                    {"databaseId": card["databaseId"], "quantity": quantity, "loadGroupId": load_group}
                )
        prebuilt[deck_id] = {"label": label, "cards": entries}
        buckets.setdefault(deck_bucket(dek.name, label), []).append({"deckListId": deck_id, "label": label})
    order = [
        "One Big Deck",
        "OWE: Perpetual Motion",
        "OWE: Ascension",
        "OWE: Personality Clash",
        "OWE: Personality Clash II",
        "Standalone",
    ]
    sub = [{"label": name, "deckLists": buckets[name]} for name in order if name in buckets]
    return {"preBuiltDecks": dict(prebuilt)}, {"deckMenu": {"subMenus": sub}}, errors


def player_group(player: str, kind: str, group_type: str, table_label: str, enter: dict, **extra) -> tuple[str, dict]:
    payload = {
        "groupType": group_type,
        "label": f"Player {player[-1]} {table_label}",
        "tableLabel": table_label,
        "onCardEnter": enter,
    }
    payload.update(extra)
    return f"{player}{kind}", payload


def build_groups() -> dict:
    groups: dict[str, dict] = {
        "sharedSetAside": {
            "groupType": "aside",
            "label": "Set Aside",
            "tableLabel": "Set Aside",
            "onCardEnter": {"controller": "shared"},
        },
        "sharedGroups": {
            "groupType": "deck",
            "label": "Shared Groups",
            "tableLabel": "Shared Groups",
            "onCardEnter": {"controller": "shared", "deckGroupId": "sharedGroups"},
        },
        "sharedPlots": {
            "groupType": "deck",
            "label": "Shared Plots",
            "tableLabel": "Shared Plots",
            "onCardEnter": {"controller": "shared", "deckGroupId": "sharedPlots"},
        },
    }
    for n in range(1, MAX_PLAYERS + 1):
        player = f"player{n}"
        discard = f"{player}Discard"
        specs = (
            ("GroupDeck", "deck", "Group Deck", {"controller": player, "deckGroupId": f"{player}GroupDeck", "discardGroupId": discard}, {}),
            ("PlotDeck", "deck", "Plot Deck", {"controller": player, "deckGroupId": f"{player}PlotDeck", "discardGroupId": discard}, {}),
            ("Lead", "lead", "Lead", {"controller": player, "deckGroupId": f"{player}GroupDeck", "discardGroupId": discard}, {"canHaveAttachments": True}),
            ("Discard", "discard", "Discard", {"controller": player, "discardGroupId": discard}, {}),
            ("Removed", "removed", "Removed", {"controller": player, "discardGroupId": discard}, {}),
            ("Hand", "hand", "Hand", {"controller": player, "discardGroupId": discard}, {}),
            ("Play", "inPlay", "Power Structure", {"controller": player, "discardGroupId": discard}, {"canHaveAttachments": True}),
        )
        for kind, group_type, label, enter, extra in specs:
            key, payload = player_group(player, kind, group_type, label, enter, **extra)
            groups[key] = payload
    return {"groups": groups}


def region(group_id: str, rtype: str, left: str, top: str, width: str, height: str, **extra) -> dict:
    payload = {
        "groupId": group_id,
        "type": rtype,
        "direction": "free" if rtype == "free" else "horizontal",
        "left": left,
        "top": top,
        "width": width,
        "height": height,
        "style": {
            "background": "rgba(0, 0, 0, 0.22)",
            "border": "1px solid rgba(50, 50, 50, 0.4)",
            "boxSizing": "border-box",
        },
    }
    payload.update(extra)
    return payload


def build_layouts() -> dict:
    return {
        "layouts": {
            "default": {
                "cardSize": 9,
                "rowSpacing": 2,
                "chat": {"left": "75%", "top": "82%", "width": "24%", "height": "17%"},
                "regions": {
                    "playerN+1Hand": region("playerN+1Hand", "fan", "0%", "0%", "74%", "8%", disableDroppableAttachments=True),
                    "playerN+1Play": region("playerN+1Play", "free", "0%", "8%", "74%", "25%"),
                    "playerNPlay": region("playerNPlay", "free", "0%", "33%", "74%", "31%"),
                    "playerNHand": region("playerNHand", "fan", "0%", "82%", "50%", "17%", disableDroppableAttachments=True),
                    "playerNLead": region("playerNLead", "pile", "50%", "82%", "12%", "17%"),
                    "playerNRemoved": region("playerNRemoved", "pile", "62%", "82%", "12%", "17%"),
                    "playerN+1GroupDeck": region("playerN+1GroupDeck", "pile", "75%", "8%", "12%", "13%"),
                    "playerN+1PlotDeck": region("playerN+1PlotDeck", "pile", "87%", "8%", "12%", "13%"),
                    "playerN+1Lead": region("playerN+1Lead", "pile", "75%", "21%", "12%", "12%"),
                    "playerN+1Discard": region("playerN+1Discard", "pile", "87%", "21%", "12%", "12%"),
                    "sharedGroups": region("sharedGroups", "pile", "75%", "34%", "12%", "12%"),
                    "sharedPlots": region("sharedPlots", "pile", "87%", "34%", "12%", "12%"),
                    "playerNGroupDeck": region("playerNGroupDeck", "pile", "75%", "58%", "12%", "13%"),
                    "playerNPlotDeck": region("playerNPlotDeck", "pile", "87%", "58%", "12%", "13%"),
                    "playerNDiscard": region("playerNDiscard", "pile", "75%", "71%", "12%", "10%"),
                    "sharedSetAside": region("sharedSetAside", "pile", "87%", "71%", "12%", "10%"),
                },
                "tableButtons": {
                    "drawPlot": {"actionList": "drawPlot", "label": "Draw Plot", "left": "75%", "top": "47%", "width": "12%", "height": "3.2%"},
                    "drawGroup": {"actionList": "drawGroup", "label": "Draw Group", "left": "87%", "top": "47%", "width": "12%", "height": "3.2%"},
                    "drawSharedPlot": {"actionList": "drawSharedPlot", "label": "Shared Plot", "left": "75%", "top": "51%", "width": "12%", "height": "3.2%"},
                    "drawSharedGroup": {"actionList": "drawSharedGroup", "label": "Shared Group", "left": "87%", "top": "51%", "width": "12%", "height": "3.2%"},
                    "readyAll": {"actionList": "readyAll", "label": "Ready All", "left": "75%", "top": "55%", "width": "12%", "height": "2.8%"},
                    "increaseAttack": {"actionList": "increaseAttack", "label": "Atk +1", "left": "87%", "top": "55%", "width": "12%", "height": "2.8%"},
                },
            }
        }
    }


def copy_plugin_art() -> dict[str, str]:
    dest_dir = IMAGES / GAME_FOLDER / "_plugin"
    dest_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        "default": (LACKEY / "sets" / "setimages" / "general" / "cardback.jpg", plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "cardback-default", ".jpg")),
        "master": (LACKEY / "sets" / "setimages" / "general" / "Master.jpg", plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "cardback-master", ".jpg")),
        "puppet": (LACKEY / "sets" / "setimages" / "general" / "Puppet.jpg", plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "cardback-puppet", ".jpg")),
    }
    urls = {}
    for key, (src, rel) in mapping.items():
        dest = IMAGES / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, dest)
            urls[key] = rel
        else:
            urls[key] = IMAGE_BASE + f"{key}.jpg" if key != "default" else IMAGE_BASE.replace("setimages/", "setimages/general/cardback.jpg")
    banner_src = LACKEY / "packs" / "Limited_Double_Starter.jpg"
    logo_src = LACKEY / "bot.jpg"
    if banner_src.exists() and not (dest_dir / "banner.jpg").exists():
        shutil.copy2(banner_src, dest_dir / "banner.jpg")
    if logo_src.exists() and not (dest_dir / "logo.jpg").exists():
        shutil.copy2(logo_src, dest_dir / "logo.jpg")
    return urls


def write_plugin_jsons(cards: list[dict[str, str]], decks: dict, menu: dict, backs: dict[str, str]) -> None:
    jsons = OUT / "jsons"
    jsons.mkdir(parents=True, exist_ok=True)
    types = sorted({card["type"] for card in cards})
    token_names = ["red", "white", "blue", "green", "yellow"]
    dump_json(jsons / "main.json", {
        "pluginName": "INWO",
        "author": "Lackey / MightyBullMoose",
        "tutorialUrl": "https://github.com/MightyBullMoose/LackeyCCG-INWO",
        "announcements": [
            "Tabletop plugin from the Lackey INWO set. No rules engine — Group/Plot decks, Lead, links, and action tokens are shortcuts.",
            "D = draw plot. G = draw group. R = ready all. T = rotate. X = discard. 1 = action. 2–5 = white/blue/green/yellow links.",
        ],
        "loadPreBuiltOnNewGame": False,
    })
    stamp_lobby_art(jsons, GAME_FOLDER)
    dump_json(jsons / "announcements.json", {"announcements": [
        "INWO tabletop: load a standalone or One Big Deck. Plots to Plot Deck, groups to Group Deck, Illuminati to Lead. Rules are reminders, not enforced.",
    ]})
    dump_json(jsons / "imageUrlPrefix.json", {"imageUrlPrefix": {"Default": TOYBOX_PREFIX}})
    dump_json(jsons / "cardBacks.json", {"cardBacks": {
        key: {"width": 0.72, "height": 1.0, "imageUrl": url} for key, url in backs.items()
    }})
    dump_json(jsons / "cardTypes.json", {"cardTypes": {
        name: {"width": 0.72, "height": 1.0, "tokens": token_names} for name in types
    }})
    dump_json(jsons / "groups.json", build_groups())
    dump_json(jsons / "layouts.json", build_layouts())
    dump_json(jsons / "groupTypes.json", {"groupTypes": {
        "deck": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": True, "onCardEnter": {"currentSide": "B", "inPlay": False, "rotation": 0}},
        "discard": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
        "removed": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
        "hand": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
        "inPlay": {"canHaveAttachments": True, "canHaveTokens": True, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": True, "rotation": 0}},
        "lead": {"canHaveAttachments": True, "canHaveTokens": True, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": True, "rotation": 0}},
        "aside": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
    }})
    dump_json(jsons / "playerCountMenu.json", {"playerCountMenu": [
        {"label": str(n), "numPlayers": n, "layoutId": "default"} for n in (2, 3, 4)
    ]})
    dump_json(jsons / "phases.json", {
        "phases": {
            "draw": {"label": "(1–2) Draw Plot or Group", "height": "14%"},
            "takeover": {"label": "(3) Automatic Takeover", "height": "14%"},
            "tokens": {"label": "(4) Place Action Tokens", "height": "14%"},
            "attack": {"label": "(5) Attack / Main", "height": "20%"},
            "plots": {"label": "(6) Use Plot / Other", "height": "19%"},
            "endTurn": {"label": "(7) Knock / End Turn", "height": "19%"},
        },
        "phaseOrder": ["draw", "takeover", "tokens", "attack", "plots", "endTurn"],
    })
    dump_json(jsons / "steps.json", {
        "steps": {
            "drawStep": {"phaseId": "draw", "label": "Draw"},
            "takeoverStep": {"phaseId": "takeover", "label": "Automatic Takeover"},
            "tokensStep": {"phaseId": "tokens", "label": "Place Action Tokens"},
            "attackStep": {"phaseId": "attack", "label": "Attack / Main"},
            "plotsStep": {"phaseId": "plots", "label": "Use Plot / Other"},
            "endTurnStep": {"phaseId": "endTurn", "label": "Knock / End Turn"},
        },
        "stepOrder": ["drawStep", "takeoverStep", "tokensStep", "attackStep", "plotsStep", "endTurnStep"],
    })
    dump_json(jsons / "playerProperties.json", {"playerProperties": {}})
    dump_json(jsons / "gameProperties.json", {"gameProperties": {
        "attackBonus": {"label": "Attack Bonus/Penalty", "type": "integer", "default": 0},
    }})
    dump_json(jsons / "topBarCounters.json", {"topBarCounters": {
        "shared": [
            {"label": "Round", "imageUrl": "", "gameProperty": "roundNumber"},
            {"label": "Attack", "imageUrl": "", "gameProperty": "attackBonus"},
        ],
        "player": [],
    }})
    token_rel = {
        "red": plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "token-red", ".png"),
        "white": plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "token-white", ".png"),
        "blue": plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "token-blue", ".png"),
        "green": plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "token-green", ".png"),
        "yellow": plugin_art_rel(GAME_FOLDER, GAME_PASCAL, "token-yellow", ".png"),
    }
    dump_json(jsons / "tokens.json", {"tokens": {
        "red": {"label": "Action", "left": "50%", "top": "46%", "width": "4vh", "height": "4vh", "imageUrl": toybox_url(token_rel["red"]), "canBeNegative": True},
        "white": {"label": "White Link", "left": "82%", "top": "86%", "width": "3.4vh", "height": "3.4vh", "imageUrl": toybox_url(token_rel["white"]), "canBeNegative": True},
        "blue": {"label": "Blue Link", "left": "82%", "top": "6%", "width": "3.4vh", "height": "3.4vh", "imageUrl": toybox_url(token_rel["blue"]), "canBeNegative": True},
        "green": {"label": "Green Link", "left": "14%", "top": "6%", "width": "3.4vh", "height": "3.4vh", "imageUrl": toybox_url(token_rel["green"]), "canBeNegative": True},
        "yellow": {"label": "Yellow Link", "left": "14%", "top": "86%", "width": "3.4vh", "height": "3.4vh", "imageUrl": toybox_url(token_rel["yellow"]), "canBeNegative": True},
    }})
    dump_json(jsons / "functions.json", {"functions": {
        "DISCARD": {"args": ["$CARD_ID"], "code": [
            ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
            ["COND", ["EQUAL", "$CARD.discardGroupId", None],
             ["LOG", "{{$ALIAS_N}} failed to discard {{$CARD.currentFace.name}} because it has no discard pile."],
             ["TRUE"], [["LOG", "{{$ALIAS_N}} discarded {{$CARD.sides.A.name}}."], ["MOVE_CARD", "$CARD.id", "$CARD.discardGroupId", 0]]],
        ]},
        "FLIP": {"args": ["$CARD_ID"], "code": [
            ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
            ["COND", ["EQUAL", "$CARD.currentSide", "A"],
             [["LOG", "{{$ALIAS_N}} flipped {{$CARD.currentFace.name}} facedown."], ["SET", "/cardById/$CARD.id/currentSide", "B"]],
             ["TRUE"], [["SET", "/cardById/$CARD.id/currentSide", "A"], ["LOG", "{{$ALIAS_N}} flipped {{$CARD.currentFace.name}} faceup."]]],
        ]},
        "DETACH": {"args": ["$CARD_ID"], "code": [
            ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
            ["COND", ["GREATER_THAN", "$CARD.cardIndex", 0],
             [["MOVE_CARD", "$CARD.id", "$CARD.groupId", ["ADD", "$CARD.stackIndex", 1]], ["LOG", "{{$ALIAS_N}} detached {{$CARD.currentFace.name}}."]]],
        ]},
        "SHUFFLE_INTO_DECK": {"args": ["$CARD_ID"], "code": [
            ["VAR", "$CARD", "$GAME.cardById.$CARD_ID"],
            ["VAR", "$GROUP_ID", "$CARD.deckGroupId"],
            ["COND", ["EQUAL", "$GROUP_ID", None],
             ["LOG", "{{$ALIAS_N}} failed to shuffle {{$CARD.currentFace.name}} into a deck."],
             ["TRUE"], [["MOVE_CARD", "$CARD.id", "$CARD.deckGroupId", 0], ["SHUFFLE_GROUP", "$GROUP_ID"],
                        ["LOG", "{{$ALIAS_N}} shuffled {{$CARD.currentFace.name}} into {{$GAME.groupById.$GROUP_ID.label}}."]]],
        ]},
    }})
    dump_json(jsons / "actionLists.json", {"actionLists": {
        "drawPlot": [[
            "COND", ["GROUP_EMPTY", "{{$PLAYER_N}}PlotDeck"],
            ["LOG", "{{$ALIAS_N}} tried to draw from an empty Plot Deck."],
            ["TRUE"], [["MOVE_STACKS", "{{$PLAYER_N}}PlotDeck", "{{$PLAYER_N}}Hand", 1, "bottom"], ["LOG", "{{$ALIAS_N}} drew a Plot."]],
        ]],
        "drawGroup": [[
            "COND", ["GROUP_EMPTY", "{{$PLAYER_N}}GroupDeck"],
            ["LOG", "{{$ALIAS_N}} tried to draw from an empty Group Deck."],
            ["TRUE"], [["MOVE_STACKS", "{{$PLAYER_N}}GroupDeck", "{{$PLAYER_N}}Hand", 1, "bottom"], ["LOG", "{{$ALIAS_N}} drew a Group."]],
        ]],
        "drawSharedPlot": [[
            "COND", ["GROUP_EMPTY", "sharedPlots"],
            ["LOG", "{{$ALIAS_N}} tried to draw from an empty Shared Plots deck."],
            ["TRUE"], [["MOVE_STACKS", "sharedPlots", "{{$PLAYER_N}}Hand", 1, "bottom"], ["LOG", "{{$ALIAS_N}} drew a shared Plot."]],
        ]],
        "drawSharedGroup": [[
            "COND", ["GROUP_EMPTY", "sharedGroups"],
            ["LOG", "{{$ALIAS_N}} tried to draw from an empty Shared Groups deck."],
            ["TRUE"], [["MOVE_STACKS", "sharedGroups", "{{$PLAYER_N}}Hand", 1, "bottom"], ["LOG", "{{$ALIAS_N}} drew a shared Group."]],
        ]],
        "shuffleGroupDeck": [["SHUFFLE_GROUP", "{{$PLAYER_N}}GroupDeck"], ["LOG", "{{$ALIAS_N}} shuffled their Group Deck."]],
        "shufflePlotDeck": [["SHUFFLE_GROUP", "{{$PLAYER_N}}PlotDeck"], ["LOG", "{{$ALIAS_N}} shuffled their Plot Deck."]],
        "readyAll": [[
            "FOR_EACH_KEY_VAL", "$CARD_ID", "$CARD", "$GAME.cardById",
            ["COND", ["EQUAL", "$CARD.controller", "$PLAYER_N"], ["SET", "/cardById/{{$CARD_ID}}/rotation", 0]],
        ], ["LOG", "{{$ALIAS_N}} readied all their cards."]],
        "rotateCard": [
            ["VAR", "$CARD", "$GAME.cardById.$ACTIVE_CARD_ID"],
            ["SET", "/cardById/$ACTIVE_CARD_ID/rotation", ["MODULO", ["ADD", "$CARD.rotation", 90], 360]],
            ["LOG", "{{$ALIAS_N}} rotated {{$ACTIVE_FACE.name}}."],
        ],
        "unrotateCard": [["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 0], ["LOG", "{{$ALIAS_N}} unrotated {{$ACTIVE_FACE.name}}."]],
        "increaseAttack": [["INCREASE_VAL", "/attackBonus", 1], ["LOG", "{{$ALIAS_N}} raised the attack bonus by 1."]],
        "decreaseAttack": [["DECREASE_VAL", "/attackBonus", 1], ["LOG", "{{$ALIAS_N}} lowered the attack bonus by 1."]],
        "flipCard": [["FLIP", "$ACTIVE_CARD_ID"]],
        "discardCard": [["DISCARD", "$ACTIVE_CARD_ID"]],
        "detachCard": [["DETACH", "$ACTIVE_CARD_ID"]],
        "shuffleIntoDeck": [["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"]],
        "toRemoved": [["MOVE_CARD", "$ACTIVE_CARD_ID", "{{$PLAYER_N}}Removed", 0], ["LOG", "{{$ALIAS_N}} removed a card from the game."]],
        "toLead": [["MOVE_CARD", "$ACTIVE_CARD_ID", "{{$PLAYER_N}}Lead", 0], ["LOG", "{{$ALIAS_N}} moved a card to Lead."]],
    }})
    dump_json(jsons / "hotkeys.json", {"hotkeys": {
        "game": [
            {"key": "D", "actionList": "drawPlot", "label": "Draw plot"},
            {"key": "G", "actionList": "drawGroup", "label": "Draw group"},
            {"key": "S", "actionList": "shufflePlotDeck", "label": "Shuffle plot deck"},
            {"key": "W", "actionList": "shuffleGroupDeck", "label": "Shuffle group deck"},
            {"key": "R", "actionList": "readyAll", "label": "Ready all"},
            {"key": "Y", "actionList": "increaseAttack", "label": "Attack +1"},
            {"key": "U", "actionList": "decreaseAttack", "label": "Attack -1"},
        ],
        "card": [
            {"key": "T", "actionList": "rotateCard", "label": "Rotate"},
            {"key": "K", "actionList": "unrotateCard", "label": "Unrotate"},
            {"key": "F", "actionList": ["FLIP", "$ACTIVE_CARD_ID"], "label": "Flip"},
            {"key": "X", "actionList": ["DISCARD", "$ACTIVE_CARD_ID"], "label": "Discard"},
            {"key": "A", "actionList": ["DETACH", "$ACTIVE_CARD_ID"], "label": "Detach"},
            {"key": "H", "actionList": ["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"], "label": "Shuffle into deck"},
            {"key": "Q", "actionList": "toRemoved", "label": "Remove from game"},
            {"key": "L", "actionList": "toLead", "label": "Move to Lead"},
        ],
        "token": [
            {"key": "1", "tokenType": "red", "label": "Action token"},
            {"key": "2", "tokenType": "white", "label": "White link"},
            {"key": "3", "tokenType": "blue", "label": "Blue link"},
            {"key": "4", "tokenType": "green", "label": "Green link"},
            {"key": "5", "tokenType": "yellow", "label": "Yellow link"},
        ],
    }})
    dump_json(jsons / "pluginMenu.json", {"pluginMenu": {"options": [
        {"label": "Draw plot", "actionList": "drawPlot"},
        {"label": "Draw group", "actionList": "drawGroup"},
        {"label": "Draw shared plot", "actionList": "drawSharedPlot"},
        {"label": "Draw shared group", "actionList": "drawSharedGroup"},
        {"label": "Shuffle plot deck", "actionList": "shufflePlotDeck"},
        {"label": "Shuffle group deck", "actionList": "shuffleGroupDeck"},
        {"label": "Ready all", "actionList": "readyAll"},
        {"label": "Attack +1", "actionList": "increaseAttack"},
        {"label": "Attack -1", "actionList": "decreaseAttack"},
    ]}})
    dump_json(jsons / "cardMenu.json", {"cardMenu": {"moveToGroupIds": MOVE_GROUPS, "options": [
        {"label": "Rotate", "actionList": "rotateCard"},
        {"label": "Unrotate", "actionList": "unrotateCard"},
        {"label": "Flip", "actionList": "flipCard"},
        {"label": "Discard", "actionList": "discardCard"},
        {"label": "Remove from game", "actionList": "toRemoved"},
        {"label": "Move to Lead", "actionList": "toLead"},
        {"label": "Detach", "actionList": "detachCard"},
        {"label": "Shuffle into deck", "actionList": "shuffleIntoDeck"},
    ]}})
    dump_json(jsons / "groupMenu.json", {"groupMenu": {"moveToGroupIds": MOVE_GROUPS, "options": []}})
    dump_json(jsons / "browse.json", {"browse": {
        "filterPropertySideA": "type",
        "filterValuesSideA": types,
        "textPropertiesSideA": ["name", "alignment", "attribute", "text", "packName"],
    }})
    dump_json(jsons / "deckbuilder.json", {"deckbuilder": {
        "addButtons": [1, 2, 3],
        "columns": [
            {"propName": "name", "label": "Name"},
            {"propName": "type", "label": "Type"},
            {"propName": "power", "label": "Power"},
            {"propName": "packName", "label": "Set"},
            {"propName": "deck", "label": "Deck"},
        ],
        "spawnGroups": [
            {"loadGroupId": "playerNPlotDeck", "label": "My Plot Deck"},
            {"loadGroupId": "playerNGroupDeck", "label": "My Group Deck"},
            {"loadGroupId": "playerNLead", "label": "My Lead"},
            {"loadGroupId": "sharedPlots", "label": "Shared Plots"},
            {"loadGroupId": "sharedGroups", "label": "Shared Groups"},
        ],
    }})
    dump_json(jsons / "spawnExistingCardModal.json", {"spawnExistingCardModal": {
        "columnProperties": ["name", "type", "packName", "power"],
        "loadGroupIds": [
            "player1PlotDeck", "player1GroupDeck", "player1Lead", "player1Play", "player1Hand",
            "sharedPlots", "sharedGroups", "sharedSetAside",
            "player2PlotDeck", "player2GroupDeck", "player2Lead", "player2Play",
        ],
    }})
    dump_json(jsons / "faceProperties.json", {"faceProperties": {
        "deck": {"label": "Deck", "type": "string", "default": ""},
        "alignment": {"label": "Alignment", "type": "string", "default": ""},
        "attribute": {"label": "Attribute", "type": "string", "default": ""},
        "power": {"label": "Power", "type": "string", "default": ""},
        "resistance": {"label": "Resistance", "type": "string", "default": ""},
        "control": {"label": "Control", "type": "string", "default": ""},
        "rarity": {"label": "Rarity", "type": "string", "default": ""},
        "errata": {"label": "Errata", "type": "string", "default": ""},
        "text": {"label": "Text", "type": "string", "default": ""},
        "packName": {"label": "Set", "type": "string", "default": ""},
        "set": {"label": "Lackey Set", "type": "string", "default": ""},
        "loadGroupId": {"label": "Load Group", "type": "string", "default": ""},
    }})
    dump_json(jsons / "cardProperties.json", {"cardProperties": {}})
    dump_json(jsons / "defaultActions.json", {"defaultActions": []})
    dump_json(jsons / "automation.json", {"automation": {
        "postNewGameActionList": [["LOG", "INWO table created. Load a deck from Menu. No rules are enforced. Fnord."]],
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


def write_tokens() -> None:
    images = IMAGES / GAME_FOLDER / "_plugin"
    write_color_png(images / f"{GAME_PASCAL}-TokenRed.png", (196, 48, 48))
    write_color_png(images / f"{GAME_PASCAL}-TokenWhite.png", (236, 236, 236))
    write_color_png(images / f"{GAME_PASCAL}-TokenBlue.png", (48, 96, 196))
    write_color_png(images / f"{GAME_PASCAL}-TokenGreen.png", (46, 184, 72))
    write_color_png(images / f"{GAME_PASCAL}-TokenYellow.png", (212, 176, 40))


def main() -> int:
    if not (LACKEY / "sets" / "carddata.txt").exists():
        raise SystemExit(f"Lackey plugin not found: {LACKEY}")
    cards, errors = load_cards()
    write_tsv(cards, OUT / "tsvs" / "cards.tsv")
    decks, menu, deck_errors = convert_decks(cards)
    errors.extend(deck_errors)
    backs = copy_plugin_art()
    write_plugin_jsons(cards, decks, menu, backs)
    write_tokens()
    missing = sum(1 for card in cards if not card["imageUrl"])
    (OUT / "SOURCE.txt").write_text(
        "\n".join(
            [
                f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from LackeyCCG INWO.",
                f"Source: {LACKEY}",
                "Art: GitHub MightyBullMoose/LackeyCCG-INWO raw setimages.",
                "Author credit: Lackey / MightyBullMoose",
                "",
                "Tabletop plugin only — Lackey has no rules engine to port.",
                f"TSV rows: {len(cards)}  missing image URLs: {missing}",
                f"Prebuilts: {len(decks['preBuiltDecks'])} Lackey decks (DOTW, OWE sets, One Big Deck).",
                "Lobby banner is the Limited double starter; logo is the Lackey bot pyramid eye.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUT.name}")
    print("  pluginName: INWO")
    print(f"  tsv rows: {len(cards)}  missing urls: {missing}")
    print(f"  prebuilt decks: {len(decks['preBuiltDecks'])}")
    print(f"  types: {', '.join(sorted({c['type'] for c in cards}))}")
    print(f"  sets: {', '.join(sorted({c['set'] for c in cards}))}")
    if errors:
        print(f"\n{len(errors)} issue(s):")
        for err in errors[:40]:
            print(f"  - {err}")
        if len(errors) > 40:
            print(f"  … {len(errors) - 40} more")
        return 1
    print()
    print("Next:")
    print("  python3 plugins/scripts/collect_hosted_images.py inwo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
