"""Composite LoN card faces from RCC portraits, 9-slice frames, icons, and Vera."""

from __future__ import annotations

import re
import struct
from pathlib import Path

XOR_KEY = 0x73
CARD_W, CARD_H = 360, 560
NAME_H = 72
TEXT_H = 210
ART_TOP = NAME_H
ART_H = CARD_H - NAME_H - TEXT_H
PARCHMENT = (255, 250, 238, 255)
TEXT_BOX = (255, 255, 252, 255)

ARCH_COLOR = {
    "Fighter": (180, 32, 40),
    "Mage": (72, 56, 150),
    "Priest": (36, 118, 78),
    "Scout": (196, 156, 40),
}
TYPE_COLOR = {
    "Avatar": (196, 156, 48),
    "Quest": (92, 64, 36),
    "Unit": (120, 48, 40),
    "Ability": (48, 72, 140),
    "Item": (72, 72, 80),
    "Tactic": (96, 48, 110),
}


def xor_blob(blob: bytes) -> bytes:
    return bytes(byte ^ XOR_KEY for byte in blob)


def rcc_header(raw: bytes) -> tuple[int, int, int]:
    _ver, tree, data_off, names = struct.unpack_from(">4I", raw, 4)
    return tree, data_off, names


def rcc_names(raw: bytes, names: int, tree: int) -> dict[int, str]:
    table: dict[int, str] = {}
    off = names
    while off + 6 <= tree:
        nlen = struct.unpack_from(">H", raw, off)[0]
        if nlen == 0 or nlen > 400 or off + 6 + nlen * 2 > tree:
            break
        name = "".join(chr(struct.unpack_from(">H", raw, off + 6 + i * 2)[0]) for i in range(nlen))
        table[off - names] = name
        off += 6 + nlen * 2
    return table


def iter_rcc_files(path: Path):
    raw = path.read_bytes()
    tree, data_off, names = rcc_header(raw)
    name_at = rcc_names(raw, names, tree)
    node_size = 14
    count = (len(raw) - tree) // node_size
    nodes = []
    for index in range(count):
        off = tree + index * node_size
        name_off, flags = struct.unpack_from(">IH", raw, off)
        if flags & 2:
            child_count, first = struct.unpack_from(">II", raw, off + 6)
            nodes.append((True, name_off, child_count, first, 0))
        else:
            _country, _lang, data_rel = struct.unpack_from(">HHI", raw, off + 6)
            nodes.append((False, name_off, 0, 0, data_rel))

    def walk(idx: int, prefix: str):
        is_dir, name_off, child_count, first, data_rel = nodes[idx]
        name = name_at.get(name_off, "")
        path_name = f"{prefix}/{name}" if prefix and name else (name or prefix)
        if is_dir:
            for child in range(child_count):
                yield from walk(first + child, path_name)
            return
        yield path_name, data_off, data_rel

    yield raw, walk(0, "")


def read_rcc_blob(raw: bytes, data_off: int, data_rel: int) -> bytes:
    abs_off = data_off + data_rel
    size = struct.unpack_from(">I", raw, abs_off)[0]
    return xor_blob(raw[abs_off + 4 : abs_off + 4 + size])


def extract_parts(cards_rcc: Path, dest: Path, resources_rcc: Path | None = None) -> dict[str, Path]:
    dest.mkdir(parents=True, exist_ok=True)
    wanted = {
        "vera.ttf",
        "verabd.ttf",
        "verait.ttf",
        "icon_attack.png",
        "icon_defense.png",
        "icon_damage.png",
        "icon_health.png",
        "icon_level.png",
        "faction_icon_fighter.png",
        "faction_icon_mage.png",
        "faction_icon_priest.png",
        "faction_icon_scout.png",
        "faction_icon_generic.png",
    }
    found: dict[str, Path] = {}
    portraits: dict[str, tuple[int, int]] = {}

    def take(rcc: Path, skip_tutorial: bool = False) -> None:
        raw, files = next(iter_rcc_files(rcc))
        for rel, data_off, data_rel in files:
            if skip_tutorial and "tutorial" in rel.lower():
                continue
            name = Path(rel).name
            if name in wanted and name not in found:
                path = dest / name
                if not path.exists():
                    path.write_bytes(read_rcc_blob(raw, data_off, data_rel))
                found[name] = path
            match = re.match(r"(1000\d+)\.jpg$", name, re.I)
            if match and "uncompressed" not in rel.lower():
                portraits[match.group(1)] = (data_off, data_rel)

    take(cards_rcc)
    if resources_rcc and resources_rcc.exists():
        take(resources_rcc, skip_tutorial=True)
    found["_rcc"] = cards_rcc
    index_path = dest / "portraits.idx"
    if not index_path.exists() and portraits:
        lines = [f"{art}\t{off}\t{rel}" for art, (off, rel) in portraits.items()]
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return found


def load_portrait_index(parts: Path) -> dict[str, tuple[int, int]]:
    index: dict[str, tuple[int, int]] = {}
    path = parts / "portraits.idx"
    if not path.exists():
        return index
    for line in path.read_text(encoding="utf-8").splitlines():
        art, off, rel = line.split("\t")
        index[art] = (int(off), int(rel))
    return index


def _nine_slice(im, width: int, height: int, border: int = 22):
    from PIL import Image

    src_w, src_h = im.size
    border = min(border, src_w // 3, src_h // 3)
    out = Image.new("RGBA", (width, height))
    tiles = [
        ((0, 0, border, border), (0, 0, border, border)),
        ((border, 0, src_w - border, border), (border, 0, width - border, border)),
        ((src_w - border, 0, src_w, border), (width - border, 0, width, border)),
        ((0, border, border, src_h - border), (0, border, border, height - border)),
        ((border, border, src_w - border, src_h - border), (border, border, width - border, height - border)),
        ((src_w - border, border, src_w, src_h - border), (width - border, border, width, height - border)),
        ((0, src_h - border, border, src_h), (0, height - border, border, height)),
        ((border, src_h - border, src_w - border, src_h), (border, height - border, width - border, height)),
        ((src_w - border, src_h - border, src_w, src_h), (width - border, height - border, width, height)),
    ]
    for src, dst in tiles:
        piece = im.crop(src)
        target = (dst[2] - dst[0], dst[3] - dst[1])
        if target[0] > 0 and target[1] > 0:
            out.paste(piece.resize(target, Image.Resampling.LANCZOS), (dst[0], dst[1]))
    return out


def _font(parts: dict[str, Path], name: str, size: int):
    from PIL import ImageFont

    path = parts.get(name) or parts.get("vera.ttf")
    if path and path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _wrap(draw, text: str, font, width: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if draw.textlength(trial, font=font) <= width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _stamp(canvas, path: Path | None, xy: tuple[int, int], size: int) -> None:
    from PIL import Image

    if not path or not path.exists():
        return
    icon = Image.open(path).convert("RGBA")
    bbox = icon.getbbox()
    if bbox:
        icon = icon.crop(bbox)
    icon.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas.alpha_composite(icon, xy)


def _fit_font(parts: dict[str, Path], name: str, text: str, max_w: int, sizes: tuple[int, ...]):
    from PIL import Image, ImageDraw

    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for size in sizes:
        font = _font(parts, name, size)
        if draw.textlength(text, font) <= max_w:
            return font
    return _font(parts, name, sizes[-1])


def frame_key(card: dict[str, str]) -> str:
    arch = (card.get("archetype") or "").lower()
    if arch == "scout":
        arch = "rogue"
    if arch not in {"fighter", "mage", "priest", "rogue"}:
        arch = "generic"
    return arch


def border_color(card: dict[str, str]) -> tuple[int, int, int]:
    if card.get("archetype") in ARCH_COLOR:
        return ARCH_COLOR[card["archetype"]]
    return TYPE_COLOR.get(card.get("type") or "Card", (80, 70, 60))


def _traits(card: dict[str, str]) -> str:
    subtitle = (card.get("subtitle") or "").strip()
    title_like = (
        subtitle
        and len(subtitle) <= 42
        and not subtitle.endswith(".")
        and (subtitle[:1].isupper() or subtitle.startswith("of "))
        and not subtitle.startswith("[")
    )
    if title_like:
        return subtitle
    bits = [card.get("type") or ""]
    if card.get("faction"):
        bits.append(card["faction"])
    elif card.get("archetype"):
        bits.append(card["archetype"])
    return ", ".join(bit for bit in bits if bit)


def compose_card(
    card: dict[str, str],
    dest: Path,
    parts: dict[str, Path],
    rcc_raw: bytes,
    portraits: dict[str, tuple[int, int]],
) -> bool:
    from PIL import Image, ImageDraw

    dest.parent.mkdir(parents=True, exist_ok=True)
    edge = border_color(card)
    canvas = Image.new("RGBA", (CARD_W, CARD_H), PARCHMENT)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, CARD_W, 7), fill=edge + (255,))

    has_art = False
    art_id = card.get("artId") or ""
    if art_id in portraits:
        data_off, data_rel = portraits[art_id]
        blob = read_rcc_blob(rcc_raw, data_off, data_rel)
        from io import BytesIO

        try:
            portrait = Image.open(BytesIO(blob)).convert("RGBA")
            scale = max(CARD_W / portrait.width, ART_H / portrait.height)
            resized = portrait.resize((int(portrait.width * scale), int(portrait.height * scale)), Image.Resampling.LANCZOS)
            x = (CARD_W - resized.width) // 2
            y = ART_TOP + (ART_H - resized.height) // 2
            canvas.alpha_composite(resized, (x, y))
            has_art = True
        except Exception:
            pass
    if not has_art:
        wiki = card.get("wikiArt") or ""
        if wiki and Path(wiki).exists():
            try:
                portrait = Image.open(wiki).convert("RGBA")
                scale = max(CARD_W / portrait.width, ART_H / portrait.height)
                resized = portrait.resize((int(portrait.width * scale), int(portrait.height * scale)), Image.Resampling.LANCZOS)
                x = (CARD_W - resized.width) // 2
                y = ART_TOP + (ART_H - resized.height) // 2
                canvas.alpha_composite(resized, (x, y))
                has_art = True
            except Exception:
                pass

    text_top = ART_TOP + ART_H
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, text_top, CARD_W, CARD_H), fill=TEXT_BOX)
    draw.line((0, text_top, CARD_W, text_top), fill=edge + (255,), width=3)
    draw.rectangle((0, CARD_H - 7, CARD_W, CARD_H), fill=edge + (255,))

    cost = card.get("cost") or ""
    has_cost = cost not in ("", None)
    arch = (card.get("archetype") or "").lower()
    if arch == "rogue":
        arch = "scout"
    arch_icon = parts.get(f"faction_icon_{arch}.png") if arch in {"fighter", "mage", "priest", "scout"} else None
    left_pad = 54 if has_cost else 12
    right_pad = 54 if arch_icon else 12
    name = (card.get("name") or "").upper()
    title_font = _fit_font(parts, "verabd.ttf", name, CARD_W - left_pad - right_pad, (20, 17, 15, 13, 11))
    sub_font = _font(parts, "verait.ttf", 12)
    draw.text((left_pad, 10), name, fill=(22, 18, 14, 255), font=title_font)
    traits = _traits(card)
    if traits:
        draw.text((left_pad, 40), traits[:48], fill=(70, 50, 40, 255), font=sub_font)

    if has_cost:
        _stamp(canvas, parts.get("icon_level.png"), (4, 6), 50)
        cost_font = _font(parts, "verabd.ttf", 18)
        draw = ImageDraw.Draw(canvas)
        bbox = draw.textbbox((0, 0), str(cost), font=cost_font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((29 - tw // 2, 20 - th // 2), str(cost), fill=(255, 244, 210, 255), font=cost_font)
    if arch_icon:
        _stamp(canvas, arch_icon, (CARD_W - 50, 8), 42)

    draw = ImageDraw.Draw(canvas)
    stat_font = _font(parts, "verabd.ttf", 16)
    rail = [
        ("attack", "icon_attack.png", False),
        ("defense", "icon_defense.png", False),
        ("damage", "icon_damage.png", True),
        ("health", "icon_health.png", False),
    ]
    y = ART_TOP + 8
    for key, icon_name, plus in rail:
        value = card.get(key)
        if value in (None, ""):
            continue
        if key == "damage" and str(value) == "0":
            continue
        label = f"+{value}" if plus else str(value)
        _stamp(canvas, parts.get(icon_name), (8, y), 28)
        fill = (255, 255, 255, 255) if has_art else (22, 18, 14, 255)
        stroke = (0, 0, 0, 220) if has_art else (255, 255, 255, 180)
        draw.text((40, y + 4), label, fill=fill, font=stat_font, stroke_width=2, stroke_fill=stroke)
        y += 34

    rules = card.get("text") or ""
    flavor = card.get("flavour") or ""
    inner_w = CARD_W - 28
    max_bottom = CARD_H - 16
    body_size = 13
    for body_size in (13, 12, 11, 10):
        body_font = _font(parts, "vera.ttf", body_size)
        flavor_font = _font(parts, "verait.ttf", max(body_size - 1, 10))
        lh = body_size + 3
        flh = body_size + 2
        rule_lines = _wrap(draw, rules, body_font, inner_w)
        flavor_lines = _wrap(draw, flavor, flavor_font, inner_w)
        need = len(rule_lines) * lh + (8 + len(flavor_lines) * flh if flavor_lines else 0)
        if text_top + 14 + need <= max_bottom:
            break
    y = text_top + 14
    for line in rule_lines:
        if y + lh > max_bottom:
            break
        draw.text((14, y), line, fill=(24, 20, 18, 255), font=body_font)
        y += lh
    if flavor_lines and y + 8 < max_bottom:
        y += 6
        for line in flavor_lines:
            if y + flh > max_bottom:
                break
            draw.text((14, y), line, fill=(90, 60, 45, 255), font=flavor_font)
            y += flh

    rgb = canvas.convert("RGB")
    dest.parent.mkdir(parents=True, exist_ok=True)
    rgb.save(dest, "JPEG", quality=90)
    return True
