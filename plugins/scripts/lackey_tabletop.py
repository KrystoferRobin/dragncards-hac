"""Shared helpers for Lackey → DragnCards tabletop plugins."""

from __future__ import annotations

import json
import re
import shutil
import struct
import zlib
from pathlib import Path

from image_names import card_rel_path, ext_from_url, plugin_art_rel


def dump_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sanitize(value: str) -> str:
    return (value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()


def write_tsv(cards: list[dict[str, str]], columns: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["\t".join(columns)]
    rows.extend("\t".join(sanitize(card.get(col, "")) for col in columns) for card in cards)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_color_png(path: Path, rgb: tuple[int, int, int], size: int = 48) -> None:
    red, green, blue = rgb
    raw = b"".join(b"\x00" + bytes([red, green, blue]) * size for _ in range(size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "deck"


def unique_rel(rel: str, used: dict[str, int]) -> str:
    key = rel.casefold()
    used[key] = used.get(key, 0) + 1
    if used[key] == 1:
        return rel
    path = Path(rel)
    return str(path.with_name(f"{path.stem}-{used[key]}{path.suffix}")).replace("\\", "/")


def index_setimages(setimages: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    if not setimages.exists():
        return index
    for path in setimages.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
            continue
        rel = path.relative_to(setimages).as_posix().lower()
        index[rel] = path
        index[path.name.lower()] = path
        index[path.stem.lower()] = path
    return index


def load_image_urls(path: Path) -> dict[str, str]:
    urls: dict[str, str] = {}
    if not path.exists():
        return urls
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("cardimageurls"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        rel = parts[0].strip().replace("\\", "/")
        url = parts[1].strip()
        if not rel or not url:
            continue
        lower = rel.lower()
        urls[lower] = url
        filename = lower.split("/")[-1]
        urls[filename] = url
        urls[filename.rsplit(".", 1)[0]] = url
        urls[f"{Path(lower).parent.as_posix()}/{Path(filename).stem}"] = url
    return urls


def lookup_image(urls: dict[str, str], set_name: str, image_file: str) -> str:
    stem = Path(image_file).stem
    for key in (
        f"{set_name}/{image_file}".lower(),
        f"{set_name}/{stem}.jpg".lower(),
        f"{set_name}/{stem}".lower(),
        image_file.lower(),
        f"{stem}.jpg".lower(),
        stem.lower(),
    ):
        if key in urls:
            return urls[key]
    return ""


def find_local_image(index: dict[str, Path], set_name: str, image_file: str) -> Path | None:
    stem = Path(image_file).stem
    for key in (
        f"{set_name}/{image_file}".lower(),
        f"{set_name}/{stem}.jpg".lower(),
        f"{set_name}/{stem}.png".lower(),
        image_file.lower(),
        f"{stem}.jpg".lower(),
        f"{stem}.png".lower(),
        stem.lower(),
    ):
        if key in index:
            return index[key]
    return None


def copy_card_art(
    src: Path,
    images_root: Path,
    game_folder: str,
    game_pascal: str,
    set_name: str,
    card_name: str,
    used: dict[str, int],
) -> str:
    ext = ext_from_url(src.name, src.suffix or ".jpg")
    rel = unique_rel(card_rel_path(game_folder, game_pascal, set_name, card_name, ext), used)
    dest = images_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or dest.stat().st_size == 0:
        shutil.copy2(src, dest)
    return rel.replace("\\", "/")


def copy_plugin_art(src: Path, images_root: Path, game_folder: str, game_pascal: str, label: str) -> str:
    ext = ext_from_url(src.name, src.suffix or ".jpg")
    rel = plugin_art_rel(game_folder, game_pascal, label, ext)
    dest = images_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return rel.replace("\\", "/")


def group_types() -> dict:
    return {
        "deck": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": True, "onCardEnter": {"currentSide": "B", "inPlay": False, "rotation": 0}},
        "discard": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
        "hand": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
        "inPlay": {"canHaveAttachments": True, "canHaveTokens": True, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": True, "rotation": 0}},
        "aside": {"canHaveAttachments": False, "canHaveTokens": False, "shuffleOnLoad": False, "onCardEnter": {"currentSide": "A", "inPlay": False, "rotation": 0}},
    }


def layout_group_id(group_id: str) -> str:
    """Brace playerN so current Haven validation does not eat a following N (NetNavi, Nation)."""
    if group_id.startswith("playerN+") or group_id.startswith("{") or not group_id.startswith("playerN"):
        return group_id
    return "{playerN}" + group_id[len("playerN"):]


def region(group_id: str, rtype: str, left: str, top: str, width: str, height: str, **extra) -> dict:
    payload = {
        "groupId": layout_group_id(group_id),
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


def standard_functions() -> dict:
    return {
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
    }


def standard_actions(draw_group: str = "Deck", discard_label: str = "discarded") -> dict:
    return {
        "drawDeck": [[
            "COND",
            ["GROUP_EMPTY", f"{{{{$PLAYER_N}}}}{draw_group}"],
            ["LOG", "{{$ALIAS_N}} tried to draw from an empty deck."],
            ["TRUE"],
            [
                ["MOVE_STACKS", f"{{{{$PLAYER_N}}}}{draw_group}", "{{$PLAYER_N}}Hand", 1, "bottom"],
                ["LOG", "{{$ALIAS_N}} drew a card."],
            ],
        ]],
        "shuffleDeck": [["SHUFFLE_GROUP", f"{{{{$PLAYER_N}}}}{draw_group}"], ["LOG", "{{$ALIAS_N}} shuffled their deck."]],
        "readyAll": [[
            "FOR_EACH_KEY_VAL", "$CARD_ID", "$CARD", "$GAME.cardById",
            ["COND", ["EQUAL", "$CARD.controller", "$PLAYER_N"], ["SET", "/cardById/{{$CARD_ID}}/rotation", 0]],
        ], ["LOG", "{{$ALIAS_N}} readied all their cards."]],
        "spendCard": [["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 90], ["LOG", "{{$ALIAS_N}} exerted {{$ACTIVE_FACE.name}}."]],
        "readyCard": [["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 0], ["LOG", "{{$ALIAS_N}} readied {{$ACTIVE_FACE.name}}."]],
        "invertCard": [["SET", "/cardById/$ACTIVE_CARD_ID/rotation", 180], ["LOG", "{{$ALIAS_N}} inverted {{$ACTIVE_FACE.name}}."]],
        "flipCard": [["FLIP", "$ACTIVE_CARD_ID"]],
        "discardCard": [["DISCARD", "$ACTIVE_CARD_ID"]],
        "detachCard": [["DETACH", "$ACTIVE_CARD_ID"]],
        "shuffleIntoDeck": [["SHUFFLE_INTO_DECK", "$ACTIVE_CARD_ID"]],
    }
