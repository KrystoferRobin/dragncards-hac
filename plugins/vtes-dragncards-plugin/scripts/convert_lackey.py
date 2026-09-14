#!/usr/bin/env python3
"""Convert the LackeyCCG VTES plugin into DragnCards TSV + table JSON."""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from image_names import stamp_lobby_art  # noqa: E402

LACKEY_DIR = Path(r"C:\Users\chris\Documents\e-Sword\tests\LackeyCCG\plugins\vtes")
PLUGIN_DIR = Path(r"C:\Users\chris\Documents\e-Sword\dragncards\vtes-dragncards-plugin")
GAME_FOLDER = "vampire-the-eternal-struggle"
SETS_DIR = LACKEY_DIR / "sets"
DECKS_DIR = LACKEY_DIR / "decks"
GENERAL_DIR = SETS_DIR / "setimages" / "general"
TSV_OUT = PLUGIN_DIR / "tsvs" / "cards.tsv"
JSONS_DIR = PLUGIN_DIR / "jsons"

STATIC_CARD = "https://static.krcg.org/card"
LACKEY_GENERAL = "https://lackey.krcg.org/sets/setimages/general"

BROWSE_FILTERS = [
    "Vampire",
    "Master",
    "Action",
    "Action Modifier",
    "Combat",
    "Reaction",
    "Political Action",
    "Equipment",
    "Ally",
    "Retainer",
    "Event",
    "Imbued",
    "Power",
    "Conviction",
    "Token",
]

BACK_MAP = {
    "cardbackcrypt": "crypt",
    "cardbacklibrary": "library",
    "cardbacktoken": "token",
    "cardbackcultist": "cultist",
    "cardbackcultistcrypt": "cultistCrypt",
    "cardbacknergal": "nergal",
    "cardbacknergalcrypt": "nergalCrypt",
    "edge": "token",
    "edge2": "token",
}

BACK_URLS = {
    "library": f"{STATIC_CARD}/cardbacklibrary.jpg",
    "crypt": f"{STATIC_CARD}/cardbackcrypt.jpg",
    "token": f"{LACKEY_GENERAL}/cardbacktoken.jpg",
    "cultist": f"{LACKEY_GENERAL}/cardbackcultist.jpg",
    "cultistCrypt": f"{LACKEY_GENERAL}/cardbackcultistcrypt.jpg",
    "nergal": f"{LACKEY_GENERAL}/cardbacknergal.jpg",
    "nergalCrypt": f"{LACKEY_GENERAL}/cardbacknergalcrypt.jpg",
}

TSV_COLUMNS = [
    "databaseId",
    "name",
    "imageUrl",
    "cardBack",
    "type",
    "category",
    "clan",
    "group",
    "capacity",
    "discipline",
    "poolCost",
    "bloodCost",
    "set",
    "rarity",
    "text",
    "loadGroupId",
]

ZONE_BORDER = "1px solid rgba(210, 210, 210, 0.55)"
MAX_PLAYERS = 8
OVERLAY_ZONES = [
    "Hand",
    "Ready",
    "Uncontrolled",
    "Torpor",
    "Masters",
    "Crypt",
    "Library",
    "AshHeap",
    "Removed",
]


def extra_offsets(num_players: int) -> list[int]:
    return list(range(2, num_players - 1))


def all_extra_offsets() -> list[int]:
    return extra_offsets(MAX_PLAYERS)


def extra_button_label(offset: int, num_players: int) -> str:
    if num_players == 4:
        return "Other"
    if offset == 2:
        return "GP"
    if offset == num_players - 2:
        return "GPr"
    return f"+{offset}"


def extra_title(offset: int, num_players: int) -> str:
    if num_players == 4 and offset == 2:
        return "Across"
    if offset == 2:
        return "Grandprey"
    if offset == num_players - 2:
        return "Grandpredator"
    return f"+{offset}"


def sanitize(value: str) -> str:
    return (value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()


def fold_name(value: str) -> str:
    text = sanitize(value)
    text = text.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("`", "'")
    return text.casefold()


def lookup_keys(name: str) -> list[str]:
    folded = fold_name(name)
    keys = [folded]
    no_paren = re.sub(r"\s*\([^)]*\)\s*", " ", folded).strip()
    if no_paren and no_paren not in keys:
        keys.append(no_paren)
    if folded.endswith(", the"):
        keys.append(folded[:-5].strip())
        keys.append("the " + folded[:-5].strip())
    if folded.startswith("the "):
        keys.append(folded[4:].strip())
        keys.append(folded[4:].strip() + ", the")
    return keys


DECK_NAME_ALIASES = {
    "rego motus": "rego motum",
}


def normalize_type(raw: str) -> str:
    text = sanitize(raw).replace(" / ", "/")
    return text


def browse_category(kind: str) -> str:
    if kind in BROWSE_FILTERS:
        return kind
    for cat in BROWSE_FILTERS:
        if kind.startswith(cat + "/") or kind.endswith("/" + cat):
            return cat
    return "Other"


def local_general_names() -> dict[str, str]:
    names: dict[str, str] = {}
    if GENERAL_DIR.is_dir():
        for path in GENERAL_DIR.iterdir():
            if path.is_file():
                names[path.name.lower()] = path.name
    return names


def front_filename(image_file: str) -> str:
    front = sanitize(image_file.split(",")[0])
    if not front:
        return ""
    if "." not in front:
        front = f"{front}.jpg"
    return front


def image_url(image_file: str, local_names: dict[str, str]) -> str:
    fname = front_filename(image_file)
    if not fname:
        return ""
    actual = local_names.get(fname.lower(), fname)
    if fname.lower() in local_names:
        return f"{LACKEY_GENERAL}/{quote(actual, safe='-_.()')}"
    return f"{STATIC_CARD}/{quote(fname, safe='-_.()')}"


def card_back_id(image_file: str, kind: str) -> str:
    parts = [sanitize(part) for part in image_file.split(",")]
    if len(parts) > 1 and parts[1]:
        back = parts[1]
        stem = back.rsplit(".", 1)[0]
        return BACK_MAP.get(stem, BACK_MAP.get(back, "library"))
    if kind in ("Vampire", "Imbued"):
        return "crypt"
    if kind == "Token":
        return "token"
    return "library"


def default_load_group(kind: str, name: str) -> str:
    if name.lower().startswith("edge"):
        return "sharedEdge"
    if kind == "Token":
        return "playerNTokens"
    if kind in ("Vampire", "Imbued"):
        return "playerNCrypt"
    return "playerNLibrary"


def load_cards() -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    cards: list[dict[str, str]] = []
    seen: set[str] = set()
    local_names = local_general_names()
    set_files = [SETS_DIR / "allsets.txt", SETS_DIR / "tokens.txt"]
    set_files.extend(sorted(path for path in SETS_DIR.glob("*.txt") if path.name not in {"allsets.txt", "tokens.txt"}))
    for path in set_files:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t", quoting=csv.QUOTE_NONE)
            for row in reader:
                name = sanitize(row.get("Name", ""))
                set_name = sanitize(row.get("Set", ""))
                image_file = sanitize(row.get("ImageFile", ""))
                kind = normalize_type(row.get("Type", ""))
                if not name or not image_file or not kind:
                    errors.append(f"Skipping incomplete row in {path.name}: {name!r}")
                    continue
                front = front_filename(image_file)
                database_id = Path(front).stem
                if database_id in seen:
                    database_id = f"{set_name}__{database_id}"
                if database_id in seen:
                    database_id = f"{database_id}__{name}"
                if database_id in seen:
                    errors.append(f"Duplicate databaseId {database_id}")
                    continue
                seen.add(database_id)
                cards.append(
                    {
                        "databaseId": database_id,
                        "name": name,
                        "imageUrl": image_url(image_file, local_names),
                        "cardBack": card_back_id(image_file, kind),
                        "type": kind,
                        "category": browse_category(kind),
                        "clan": sanitize(row.get("Clan", "")),
                        "group": sanitize(row.get("Group", "")),
                        "capacity": sanitize(row.get("Capacity", "")),
                        "discipline": sanitize(row.get("Discipline", "")),
                        "poolCost": sanitize(row.get("PoolCost", "")),
                        "bloodCost": sanitize(row.get("BloodCost", "")),
                        "set": set_name,
                        "rarity": sanitize(row.get("Rarity", "")),
                        "text": sanitize(row.get("Text", "")),
                        "loadGroupId": default_load_group(kind, name),
                    }
                )
    return cards, errors


def write_tsv(cards: list[dict[str, str]]) -> None:
    TSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with TSV_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\t".join(TSV_COLUMNS) + "\n")
        for card in cards:
            handle.write("\t".join(card.get(col, "") for col in TSV_COLUMNS) + "\n")


def write_json(name: str, payload: dict) -> None:
    JSONS_DIR.mkdir(parents=True, exist_ok=True)
    path = JSONS_DIR / name
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def in_play_group(pid: str, label: str, table_label: str, group_type: str, attachments: bool = True) -> dict:
    data = {
        "groupType": group_type,
        "label": f"{pid.replace('player', 'Player ')} {label}" if pid.startswith("player") else label,
        "tableLabel": table_label,
        "onCardEnter": {
            "controller": pid,
            "deckGroupId": f"{pid}Library",
            "discardGroupId": f"{pid}AshHeap",
        },
    }
    if attachments:
        data["canHaveAttachments"] = True
    return data


def make_groups() -> dict:
    groups: dict[str, dict] = {
        "sharedSetAside": {
            "groupType": "aside",
            "label": "Set Aside",
            "tableLabel": "Set Aside",
            "onCardEnter": {"controller": "shared"},
        },
        "sharedEdge": {
            "groupType": "edge",
            "label": "The Edge",
            "tableLabel": "Edge",
            "onCardEnter": {"controller": "shared"},
        },
        "sharedOverlay": {
            "groupType": "aside",
            "label": "Overlay",
            "tableLabel": "",
            "onCardEnter": {"controller": "shared"},
        },
    }
    for player in range(1, MAX_PLAYERS + 1):
        pid = f"player{player}"
        n = str(player)
        groups[f"{pid}Library"] = {
            "groupType": "library",
            "label": f"Player {n} Library",
            "tableLabel": "Library",
            "onCardEnter": {
                "controller": pid,
                "deckGroupId": f"{pid}Library",
                "discardGroupId": f"{pid}AshHeap",
            },
        }
        groups[f"{pid}Crypt"] = {
            "groupType": "crypt",
            "label": f"Player {n} Crypt",
            "tableLabel": "Crypt",
            "onCardEnter": {
                "controller": pid,
                "deckGroupId": f"{pid}Crypt",
                "discardGroupId": f"{pid}AshHeap",
            },
        }
        groups[f"{pid}Hand"] = {
            "groupType": "hand",
            "label": f"Player {n} Hand",
            "tableLabel": "Hand",
            "onCardEnter": {
                "controller": pid,
                "deckGroupId": f"{pid}Library",
                "discardGroupId": f"{pid}AshHeap",
            },
        }
        groups[f"{pid}AshHeap"] = {
            "groupType": "ashHeap",
            "label": f"Player {n} Ash Heap",
            "tableLabel": "Ash",
            "onCardEnter": {
                "controller": pid,
                "deckGroupId": f"{pid}Library",
                "discardGroupId": f"{pid}AshHeap",
            },
        }
        groups[f"{pid}Removed"] = {
            "groupType": "removed",
            "label": f"Player {n} Removed",
            "tableLabel": "RFG",
            "onCardEnter": {
                "controller": pid,
                "deckGroupId": f"{pid}Library",
                "discardGroupId": f"{pid}AshHeap",
            },
        }
        groups[f"{pid}Uncontrolled"] = in_play_group(pid, "Uncontrolled", "Unctrl", "uncontrolled", False)
        groups[f"{pid}Ready"] = in_play_group(pid, "Ready", "Ready", "ready", True)
        groups[f"{pid}Torpor"] = in_play_group(pid, "Torpor", "Torpor", "torpor", True)
        groups[f"{pid}Masters"] = in_play_group(pid, "Masters", "Master", "masters", False)
        groups[f"{pid}Tokens"] = {
            "groupType": "tokens",
            "label": f"Player {n} Tokens",
            "tableLabel": "Tokens",
            "onCardEnter": {
                "controller": pid,
                "deckGroupId": f"{pid}Library",
                "discardGroupId": f"{pid}AshHeap",
            },
        }
    return {"groups": groups}


def pct(value: float) -> str:
    return f"{value:g}%"


def region_style(background: str, border: str) -> dict:
    return {"background": background, "border": border, "boxSizing": "border-box"}


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


def hidden_overlay(region: dict, layer: int = 8) -> dict:
    region = dict(region)
    region["visible"] = False
    region["layerIndex"] = layer
    region["cardSizeFactor"] = 0.75
    return region


def overlay_geom() -> dict:
    scale = 0.75
    field_w = 70.0 * scale
    hand_h = 10.0 * scale
    ready_h = 16.0 * scale
    rest_h = 12.0 * scale
    field_h = hand_h + ready_h + rest_h
    pile_w = 5.0 * scale
    pile_h = 10.0 * scale
    pile_col = 5.5 * scale
    pile_row = 10.5 * scale
    gap = 1.0 * scale
    pile_block = pile_col + pile_w
    cluster_w = field_w + gap + pile_block
    left = (100.0 - cluster_w) / 2
    top = (100.0 - field_h) / 2
    pad_x, pad_top, pad_bot = 1.6, 5.5, 2.2
    return {
        "left": left,
        "top": top,
        "width": field_w,
        "hand_h": hand_h,
        "ready_h": ready_h,
        "rest_h": rest_h,
        "field_h": field_h,
        "pile_left": left + field_w + gap,
        "pile_w": pile_w,
        "pile_h": pile_h,
        "pile_col": pile_col,
        "pile_row": pile_row,
        "cluster_w": cluster_w,
        "back_left": left - pad_x,
        "back_top": top - pad_top,
        "back_w": cluster_w + pad_x * 2,
        "back_h": field_h + pad_top + pad_bot,
        "label_left": left,
        "label_top": top - 3.6,
    }


def compact_seat(
    pid: str,
    left: float,
    top: float,
    width: float,
    height: float,
    ready_bg: str,
    ready_bd: str,
    piles_on: str = "right",
) -> dict:
    pile_w = 5.5
    field_w = width - pile_w
    field_left = left + pile_w if piles_on == "left" else left
    pile_left = left if piles_on == "left" else left + field_w
    hand_h = height * 0.26
    ready_h = height * 0.46
    rest_h = height - hand_h - ready_h
    unc_w = field_w * 0.58
    side_w = (field_w - unc_w) / 2
    ready_top = top + hand_h
    rest_top = ready_top + ready_h
    pile_h = height / 4
    regions = {
        f"{pid}Hand": row_region(f"{pid}Hand", field_left, top, field_w, hand_h, "rgba(0, 0, 0, 0.32)", ZONE_BORDER, "fan", True),
        f"{pid}Ready": row_region(f"{pid}Ready", field_left, ready_top, field_w, ready_h, ready_bg, ready_bd),
        f"{pid}Uncontrolled": row_region(
            f"{pid}Uncontrolled", field_left, rest_top, unc_w, rest_h, "rgba(40, 20, 70, 0.36)", "1px solid rgba(140, 100, 200, 0.85)"
        ),
        f"{pid}Torpor": row_region(
            f"{pid}Torpor", field_left + unc_w, rest_top, side_w, rest_h, "rgba(90, 20, 20, 0.40)", "1px solid rgba(210, 80, 80, 0.9)"
        ),
        f"{pid}Masters": row_region(
            f"{pid}Masters", field_left + unc_w + side_w, rest_top, side_w, rest_h, "rgba(90, 70, 20, 0.36)", "1px solid rgba(210, 180, 80, 0.85)"
        ),
        f"{pid}Crypt": pile(f"{pid}Crypt", pile_left, top, pile_w, pile_h),
        f"{pid}Library": pile(f"{pid}Library", pile_left, top + pile_h, pile_w, pile_h),
        f"{pid}AshHeap": pile(f"{pid}AshHeap", pile_left, top + pile_h * 2, pile_w, pile_h),
        f"{pid}Removed": pile(f"{pid}Removed", pile_left, top + pile_h * 3, pile_w, pile_h),
    }
    for region in regions.values():
        region["cardSizeFactor"] = 0.72
    return regions


def overlay_seat(pid: str, prefix: str) -> dict:
    g = overlay_geom()
    left, top, width = g["left"], g["top"], g["width"]
    hand_h, ready_h, rest_h = g["hand_h"], g["ready_h"], g["rest_h"]
    unc_w = width * 0.58
    side_w = (width - unc_w) / 2
    pile_left = g["pile_left"]
    opaque = {
        "hand": "rgb(16, 16, 26)",
        "ready": "rgb(18, 42, 28)",
        "unc": "rgb(32, 16, 52)",
        "torpor": "rgb(68, 14, 14)",
        "master": "rgb(68, 52, 14)",
        "pile": "rgb(14, 14, 20)",
    }

    def overlay_pile(group_id: str, pile_left_val: float, pile_top: float) -> dict:
        region = hidden_overlay(pile(group_id, pile_left_val, pile_top, g["pile_w"], g["pile_h"]))
        region["style"] = region_style(opaque["pile"], ZONE_BORDER)
        return region

    return {
        f"{prefix}Hand": hidden_overlay(row_region(f"{pid}Hand", left, top, width, hand_h, opaque["hand"], ZONE_BORDER, "fan", True)),
        f"{prefix}Ready": hidden_overlay(
            row_region(f"{pid}Ready", left, top + hand_h, width, ready_h, opaque["ready"], "1px solid rgb(90, 180, 110)")
        ),
        f"{prefix}Uncontrolled": hidden_overlay(
            row_region(
                f"{pid}Uncontrolled",
                left,
                top + hand_h + ready_h,
                unc_w,
                rest_h,
                opaque["unc"],
                "1px solid rgb(140, 100, 200)",
            )
        ),
        f"{prefix}Torpor": hidden_overlay(
            row_region(
                f"{pid}Torpor",
                left + unc_w,
                top + hand_h + ready_h,
                side_w,
                rest_h,
                opaque["torpor"],
                "1px solid rgb(210, 80, 80)",
            )
        ),
        f"{prefix}Masters": hidden_overlay(
            row_region(
                f"{pid}Masters",
                left + unc_w + side_w,
                top + hand_h + ready_h,
                side_w,
                rest_h,
                opaque["master"],
                "1px solid rgb(210, 180, 80)",
            )
        ),
        f"{prefix}Crypt": overlay_pile(f"{pid}Crypt", pile_left, top),
        f"{prefix}Library": overlay_pile(f"{pid}Library", pile_left + g["pile_col"], top),
        f"{prefix}AshHeap": overlay_pile(f"{pid}AshHeap", pile_left, top + g["pile_row"]),
        f"{prefix}Removed": overlay_pile(f"{pid}Removed", pile_left + g["pile_col"], top + g["pile_row"]),
    }


def overlay_backdrop() -> dict:
    g = overlay_geom()
    region = hidden_overlay(
        {
            "groupId": "sharedOverlay",
            "type": "row",
            "direction": "horizontal",
            "left": pct(g["back_left"]),
            "top": pct(g["back_top"]),
            "width": pct(g["back_w"]),
            "height": pct(g["back_h"]),
            "hideTitle": True,
            "style": {
                "background": "rgb(8, 8, 14)",
                "border": "1px solid rgb(160, 140, 200)",
                "boxSizing": "border-box",
                "boxShadow": "0 0 28px 12px rgb(0, 0, 0)",
            },
        },
        layer=7,
    )
    return region


def you_and_sidebar(play_w: float, you_top: float) -> tuple[dict, dict, dict]:
    unc_w = play_w * 0.60
    side_w = play_w * 0.20
    chat_left = unc_w + side_w
    chat_w = play_w - chat_left
    pile_w = 6.0
    col1, col2 = 88.0, 94.0
    hand_bg = "rgba(0, 0, 0, 0.32)"
    ready_bg, ready_bd = "rgba(30, 70, 40, 0.36)", "1px solid rgba(90, 180, 110, 0.85)"
    unc_bg, unc_bd = "rgba(40, 20, 70, 0.36)", "1px solid rgba(140, 100, 200, 0.85)"
    torpor_bg, torpor_bd = "rgba(90, 20, 20, 0.40)", "1px solid rgba(210, 80, 80, 0.9)"
    master_bg, master_bd = "rgba(90, 70, 20, 0.36)", "1px solid rgba(210, 180, 80, 0.85)"
    edge_bg = "rgba(90, 70, 10, 0.45)"
    ready_h = 16.0
    rest_h = 12.0
    hand_top = you_top + ready_h + rest_h
    hand_h = 100.0 - hand_top
    regions = {
        "playerNReady": row_region("playerNReady", 0, you_top, play_w, ready_h, ready_bg, ready_bd),
        "playerNUncontrolled": row_region("playerNUncontrolled", 0, you_top + ready_h, unc_w, rest_h, unc_bg, unc_bd),
        "playerNTorpor": row_region("playerNTorpor", unc_w, you_top + ready_h, side_w, rest_h, torpor_bg, torpor_bd),
        "playerNMasters": row_region("playerNMasters", chat_left, you_top + ready_h, chat_w, rest_h, master_bg, master_bd),
        "playerNHand": row_region("playerNHand", 0, hand_top, chat_left, hand_h, hand_bg, ZONE_BORDER, "fan", True),
        "playerNCrypt": pile("playerNCrypt", col1, 56.0, pile_w),
        "playerNLibrary": pile("playerNLibrary", col2, 56.0, pile_w),
        "playerNAshHeap": pile("playerNAshHeap", col1, 67.5, pile_w),
        "playerNRemoved": pile("playerNRemoved", col2, 67.5, pile_w),
        "playerNTokens": pile("playerNTokens", col1, 79.0, pile_w),
        "sharedEdge": {
            "groupId": "sharedEdge",
            "type": "pile",
            "direction": "horizontal",
            "left": pct(col2),
            "top": "79%",
            "width": pct(pile_w),
            "height": "11%",
            "style": region_style(edge_bg, "1px solid rgba(230, 190, 70, 0.95)"),
        },
        "sharedSetAside": row_region("sharedSetAside", col1, 90.0, pile_w * 2, 10.0, "rgba(0, 0, 0, 0.45)", ZONE_BORDER, "fan", True),
    }
    buttons = {
        "drawLibrary": {"actionList": "drawLibrary", "label": "Draw", "left": pct(col1), "top": "47%", "width": pct(pile_w), "height": "4%"},
        "drawCrypt": {"actionList": "drawCrypt", "label": "Crypt", "left": pct(col2), "top": "47%", "width": pct(pile_w), "height": "4%"},
        "shuffleLibrary": {"actionList": "shuffleLibrary", "label": "Shuf L", "left": pct(col1), "top": "51.5%", "width": "4%", "height": "4%"},
        "shuffleCrypt": {"actionList": "shuffleCrypt", "label": "Shuf C", "left": "92%", "top": "51.5%", "width": "4%", "height": "4%"},
        "unlockAll": {"actionList": "unlockAll", "label": "Unlock", "left": "96%", "top": "51.5%", "width": "4%", "height": "4%"},
    }
    chat = {"left": pct(chat_left), "top": pct(hand_top), "width": pct(chat_w), "height": pct(hand_h)}
    return regions, buttons, chat


def overlay_label(text: str) -> dict:
    g = overlay_geom()
    return {
        "label": text,
        "left": pct(g["label_left"]),
        "top": pct(g["label_top"]),
        "width": "22%",
        "height": "3.2%",
        "visible": False,
        "style": {
            "background": "rgb(8, 8, 14)",
            "border": "none",
            "color": "rgb(230, 220, 255)",
            "fontSize": "0.95em",
            "fontWeight": "700",
            "pointerEvents": "none",
            "zIndex": "850",
        },
    }


def circle_layout(num_players: int) -> dict:
    play_w = 87.0
    neighbor_h = 28.0
    half = play_w / 2
    predator_id = f"playerN+{num_players - 1}"
    regions: dict = {}
    regions.update(
        compact_seat(
            predator_id,
            0,
            0,
            half,
            neighbor_h,
            "rgba(80, 30, 30, 0.40)",
            "1px solid rgba(210, 90, 90, 0.9)",
            piles_on="right",
        )
    )
    regions.update(
        compact_seat(
            "playerN+1",
            half,
            0,
            half,
            neighbor_h,
            "rgba(30, 70, 40, 0.36)",
            "1px solid rgba(90, 180, 110, 0.85)",
            piles_on="left",
        )
    )
    you_regions, buttons, chat = you_and_sidebar(play_w, neighbor_h + 1.0)
    regions.update(you_regions)
    peek_style = {
        "backgroundColor": "rgba(70, 45, 110, 0.92)",
        "color": "white",
        "fontSize": "0.75em",
    }
    text_boxes = {
        "predatorLabel": {
            "label": "Predator",
            "left": "1%",
            "top": "0.2%",
            "width": "12%",
            "height": "3%",
            "style": {"color": "rgba(230, 160, 160, 0.95)", "fontSize": "0.8em", "pointerEvents": "none"},
        },
        "preyLabel": {
            "label": "Prey",
            "left": pct(half + 1),
            "top": "0.2%",
            "width": "10%",
            "height": "3%",
            "style": {"color": "rgba(160, 220, 170, 0.95)", "fontSize": "0.8em", "pointerEvents": "none"},
        },
    }
    if num_players >= 4:
        for offset in all_extra_offsets():
            regions.update(overlay_seat(f"playerN+{offset}", f"extra{offset}"))
            text_boxes[f"extra{offset}Label"] = overlay_label(extra_title(offset, num_players))
        regions["overlayBack"] = overlay_backdrop()
        extras = extra_offsets(num_players)
        for index, offset in enumerate(extras):
            buttons[f"toggleExtra{offset}"] = {
                "actionList": f"toggleExtra{offset}",
                "label": extra_button_label(offset, num_players),
                "left": pct(88.0 if index % 2 == 0 else 94.0),
                "top": pct(2.0 + (index // 2) * 5.2),
                "width": "6%",
                "height": "4.8%",
                "style": peek_style,
            }
        buttons["hideOverlays"] = {
            "actionList": "hideOverlays",
            "label": "Close",
            "left": "88%",
            "top": pct(2.0 + ((len(extras) + 1) // 2) * 5.2),
            "width": "12%",
            "height": "4%",
            "visible": False,
            "style": peek_style,
        }
    return {
        "cardSize": 8,
        "rowSpacing": 1,
        "chat": chat,
        "regions": regions,
        "tableButtons": buttons,
        "textBoxes": text_boxes,
    }


def make_player_count_menu() -> dict:
    menu = [{"label": "2", "numPlayers": 2, "layoutId": "default"}]
    for count in range(3, MAX_PLAYERS + 1):
        menu.append({"label": str(count), "numPlayers": count, "layoutId": f"table{count}"})
    return {"playerCountMenu": menu}


def make_overlay_action_lists() -> dict:
    hide: list = []
    for offset in all_extra_offsets():
        for zone in OVERLAY_ZONES:
            hide.append(["SET", f"/playerData/$PLAYER_N/layout/regions/extra{offset}{zone}/visible", False])
        hide.append(["SET", f"/playerData/$PLAYER_N/layout/textBoxes/extra{offset}Label/visible", False])
    hide.append(["SET", "/playerData/$PLAYER_N/layout/regions/overlayBack/visible", False])
    hide.append(["SET", "/playerData/$PLAYER_N/layout/tableButtons/hideOverlays/visible", False])
    action_lists = {"hideOverlays": hide}
    for offset in all_extra_offsets():
        show: list = [
            ["ACTION_LIST", "hideOverlays"],
            ["SET", "/playerData/$PLAYER_N/layout/regions/overlayBack/visible", True],
        ]
        for zone in OVERLAY_ZONES:
            show.append(["SET", f"/playerData/$PLAYER_N/layout/regions/extra{offset}{zone}/visible", True])
        show.append(["SET", f"/playerData/$PLAYER_N/layout/textBoxes/extra{offset}Label/visible", True])
        show.append(["SET", "/playerData/$PLAYER_N/layout/tableButtons/hideOverlays/visible", True])
        show.append(["FADE_TEXT_PLAYER", "$PLAYER_N", f"Looking at +{offset}"])
        action_lists[f"toggleExtra{offset}"] = [
            [
                "COND",
                f"$GAME.playerData.$PLAYER_N.layout.regions.extra{offset}Ready.visible",
                ["ACTION_LIST", "hideOverlays"],
                ["TRUE"],
                show,
            ]
        ]
    return {"actionLists": action_lists}


def make_layouts() -> dict:
    play_w = 87.0
    unc_w = play_w * 0.60
    side_w = play_w * 0.20
    pile_w = 6.0
    col1 = 88.0
    col2 = 94.0
    chat_left = unc_w + side_w
    chat_w = play_w - chat_left

    hand_bg = "rgba(0, 0, 0, 0.32)"
    ready_bg, ready_bd = "rgba(30, 70, 40, 0.36)", "1px solid rgba(90, 180, 110, 0.85)"
    unc_bg, unc_bd = "rgba(40, 20, 70, 0.36)", "1px solid rgba(140, 100, 200, 0.85)"
    torpor_bg, torpor_bd = "rgba(90, 20, 20, 0.40)", "1px solid rgba(210, 80, 80, 0.9)"
    master_bg, master_bd = "rgba(90, 70, 20, 0.36)", "1px solid rgba(210, 180, 80, 0.85)"
    edge_bg = "rgba(90, 70, 10, 0.45)"

    regions = {
        "playerN+1Hand": row_region("playerN+1Hand", 0, 0, play_w, 11, hand_bg, ZONE_BORDER, "fan", True),
        "playerN+1Uncontrolled": row_region("playerN+1Uncontrolled", 0, 11, unc_w, 12, unc_bg, unc_bd),
        "playerN+1Torpor": row_region("playerN+1Torpor", unc_w, 11, side_w, 12, torpor_bg, torpor_bd),
        "playerN+1Masters": row_region("playerN+1Masters", chat_left, 11, chat_w, 12, master_bg, master_bd),
        "playerN+1Ready": row_region("playerN+1Ready", 0, 23, play_w, 17, ready_bg, ready_bd),
        "playerNReady": row_region("playerNReady", 0, 40, play_w, 17, ready_bg, ready_bd),
        "playerNUncontrolled": row_region("playerNUncontrolled", 0, 57, unc_w, 13, unc_bg, unc_bd),
        "playerNTorpor": row_region("playerNTorpor", unc_w, 57, side_w, 13, torpor_bg, torpor_bd),
        "playerNMasters": row_region("playerNMasters", chat_left, 57, chat_w, 13, master_bg, master_bd),
        "playerNHand": row_region("playerNHand", 0, 70, chat_left, 30, hand_bg, ZONE_BORDER, "fan", True),
        "playerN+1Crypt": pile("playerN+1Crypt", col1, 12.0, pile_w),
        "playerN+1Library": pile("playerN+1Library", col2, 12.0, pile_w),
        "playerN+1AshHeap": pile("playerN+1AshHeap", col1, 23.5, pile_w),
        "playerN+1Removed": pile("playerN+1Removed", col2, 23.5, pile_w),
        "playerN+1Tokens": pile("playerN+1Tokens", col1, 35.0, pile_w),
        "playerNCrypt": pile("playerNCrypt", col1, 56.0, pile_w),
        "playerNLibrary": pile("playerNLibrary", col2, 56.0, pile_w),
        "playerNAshHeap": pile("playerNAshHeap", col1, 67.5, pile_w),
        "playerNRemoved": pile("playerNRemoved", col2, 67.5, pile_w),
        "playerNTokens": pile("playerNTokens", col1, 79.0, pile_w),
        "sharedEdge": {
            "groupId": "sharedEdge",
            "type": "pile",
            "direction": "horizontal",
            "left": pct(col2),
            "top": "79%",
            "width": pct(pile_w),
            "height": "11%",
            "style": region_style(edge_bg, "1px solid rgba(230, 190, 70, 0.95)"),
        },
        "sharedSetAside": row_region("sharedSetAside", col1, 90.0, pile_w * 2, 10.0, "rgba(0, 0, 0, 0.45)", ZONE_BORDER, "fan", True),
    }
    table_buttons = {
        "drawLibrary": {
            "actionList": "drawLibrary",
            "label": "Draw",
            "left": pct(col1),
            "top": "47%",
            "width": pct(pile_w),
            "height": "4%",
        },
        "drawCrypt": {
            "actionList": "drawCrypt",
            "label": "Crypt",
            "left": pct(col2),
            "top": "47%",
            "width": pct(pile_w),
            "height": "4%",
        },
        "shuffleLibrary": {
            "actionList": "shuffleLibrary",
            "label": "Shuf L",
            "left": pct(col1),
            "top": "51.5%",
            "width": "4%",
            "height": "4%",
        },
        "shuffleCrypt": {
            "actionList": "shuffleCrypt",
            "label": "Shuf C",
            "left": "92%",
            "top": "51.5%",
            "width": "4%",
            "height": "4%",
        },
        "unlockAll": {
            "actionList": "unlockAll",
            "label": "Unlock",
            "left": "96%",
            "top": "51.5%",
            "width": "4%",
            "height": "4%",
        },
    }
    return {
        "layouts": {
            "default": {
                "cardSize": 9,
                "rowSpacing": 1,
                "chat": {"left": pct(chat_left), "top": "70%", "width": pct(chat_w), "height": "30%"},
                "regions": regions,
                "tableButtons": table_buttons,
            },
            **{f"table{count}": circle_layout(count) for count in range(3, MAX_PLAYERS + 1)},
        }
    }


def make_card_types(cards: list[dict[str, str]]) -> dict:
    types = {
        kind: {
            "width": 0.72,
            "height": 1.0,
            "tokens": ["blood", "life", "green", "orange"],
        }
        for kind in sorted({card["type"] for card in cards})
    }
    return {"cardTypes": types}


def make_card_backs() -> dict:
    return {
        "cardBacks": {
            key: {"width": 0.72, "height": 1.0, "imageUrl": url}
            for key, url in BACK_URLS.items()
        }
    }


def make_browse(_cards: list[dict[str, str]]) -> dict:
    return {
        "browse": {
            "filterPropertySideA": "category",
            "filterValuesSideA": BROWSE_FILTERS,
            "textPropertiesSideA": ["name", "text", "clan", "discipline", "set"],
        }
    }


def slug(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", text).strip()
    parts = cleaned.split()
    if not parts:
        return "deck"
    return parts[0].lower() + "".join(part.title() for part in parts[1:])


def make_prebuilts(cards: list[dict[str, str]]) -> tuple[dict, dict, list[str]]:
    by_name: dict[str, str] = {}
    type_by_id = {card["databaseId"]: card["type"] for card in cards}
    name_by_id = {card["databaseId"]: card["name"] for card in cards}
    for card in cards:
        for key in lookup_keys(card["name"]):
            by_name.setdefault(key, card["databaseId"])
    prebuilts: dict[str, dict] = {}
    menu: list[dict] = []
    errors: list[str] = []
    folders = [
        ("5E", "V5 Precons"),
        ("Legacy", "Legacy Precons"),
        ("Storyline", "Storyline"),
    ]
    for folder, section in folders:
        section_lists: list[dict] = []
        for path in sorted((DECKS_DIR / folder).glob("*.txt")):
            deck_id = slug(path.stem)
            label = path.stem.replace("Precon_", "").replace("_", " ")
            load_list: list[dict] = []
            zone = "library"
            with path.open(encoding="utf-8", errors="replace") as handle:
                for raw in handle:
                    line = raw.strip()
                    if not line:
                        continue
                    if line.casefold().startswith("crypt"):
                        zone = "crypt"
                        continue
                    match = re.match(r"^(\d+)\s+(.+)$", line)
                    if not match:
                        errors.append(f"{path.name}: bad line {line!r}")
                        continue
                    qty = int(match.group(1))
                    card_name = match.group(2).strip()
                    alias = DECK_NAME_ALIASES.get(fold_name(card_name), fold_name(card_name))
                    database_id = None
                    for key in lookup_keys(alias):
                        database_id = by_name.get(key)
                        if database_id:
                            break
                    if not database_id:
                        errors.append(f"{path.name}: missing card {card_name!r}")
                        continue
                    kind = type_by_id[database_id]
                    if zone == "crypt" or kind in ("Vampire", "Imbued"):
                        load_group = "playerNCrypt"
                    elif kind == "Token" or name_by_id[database_id].lower().startswith("edge"):
                        load_group = "sharedEdge" if name_by_id[database_id].lower().startswith("edge") else "playerNTokens"
                    else:
                        load_group = "playerNLibrary"
                    load_list.append({"databaseId": database_id, "quantity": qty, "loadGroupId": load_group})
            if not load_list:
                errors.append(f"{path.name}: empty after parsing")
                continue
            prebuilts[deck_id] = {"label": label, "cards": load_list}
            section_lists.append({"label": label, "deckListId": deck_id})
        if section_lists:
            menu.append({"label": section, "deckLists": section_lists})
    return {"preBuiltDecks": prebuilts}, {"deckMenu": {"subMenus": menu}}, errors


def main() -> int:
    cards, errors = load_cards()
    write_tsv(cards)
    write_json("groups.json", make_groups())
    write_json("layouts.json", make_layouts())
    write_json("playerCountMenu.json", make_player_count_menu())
    write_json("overlayActions.json", make_overlay_action_lists())
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
    categories = Counter(card["category"] for card in cards)
    backs = Counter(card["cardBack"] for card in cards)
    print(f"Wrote {len(cards)} cards to {TSV_OUT}")
    print(f"Sets ({len(sets)}): {', '.join(sets)}")
    print(f"Types: {', '.join(types)}")
    print("Browse categories:")
    for name, count in categories.most_common():
        print(f"  {name}: {count}")
    print("Card backs:", dict(backs))
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
