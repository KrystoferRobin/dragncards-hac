"""Compose readable HEX card faces from 512 portraits + CardTemplate stats."""

from __future__ import annotations

from pathlib import Path

CARD_W, CARD_H = 375, 560
NAME_H = 70
TEXT_H = 168
ART_TOP = NAME_H
ART_H = CARD_H - NAME_H - TEXT_H

SHARD_COLOR = {
    "Blood": (92, 28, 110),
    "Ruby": (168, 36, 36),
    "Diamond": (196, 188, 168),
    "Sapphire": (32, 72, 140),
    "Wild": (36, 110, 48),
    "Colorless": (72, 72, 80),
}
TYPE_COLOR = {
    "Troop": (140, 48, 40),
    "Troop Artifact": (120, 56, 40),
    "Basic Action": (48, 72, 150),
    "Quick Action": (96, 48, 140),
    "Constant": (48, 100, 88),
    "Artifact": (80, 80, 88),
    "Resource": (40, 40, 48),
    "Champion": (168, 132, 40),
    "Choice": (88, 72, 40),
    "Bane": (48, 28, 28),
    "Rules": (28, 56, 72),
}

FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/Library/Fonts/Arial.ttf"),
    Path("/System/Library/Fonts/Helvetica.ttc"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    if bold:
        for path in (
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
            Path("/Library/Fonts/Arial Bold.ttf"),
        ):
            if path.exists():
                return ImageFont.truetype(str(path), size)
    for path in FONT_CANDIDATES:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _edge(card: dict[str, str]) -> tuple[int, int, int]:
    thresh = card.get("threshold") or ""
    for name, rgb in SHARD_COLOR.items():
        if name in thresh:
            return rgb
    return TYPE_COLOR.get(card.get("type") or "", (60, 52, 48))


def _round_mask(size: tuple[int, int], radius: int = 22):
    from PIL import Image, ImageDraw

    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def _fit(draw, font_fn, text: str, max_w: int, sizes: tuple[int, ...]):
    for size in sizes:
        font = font_fn(size)
        if draw.textlength(text, font=font) <= max_w:
            return font
    return font_fn(sizes[-1])


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    lines: list[str] = []
    for para in (text or "").split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if draw.textlength(trial, font=font) <= max_w:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def compose_card(card: dict[str, str], dest: Path, portraits: dict[str, Path]) -> bool:
    from PIL import Image, ImageDraw

    dest.parent.mkdir(parents=True, exist_ok=True)
    edge = _edge(card)
    paper = (248, 244, 232, 255)
    canvas = Image.new("RGBA", (CARD_W, CARD_H), (18, 14, 16, 255))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, CARD_W, 8), fill=edge + (255,))
    draw.rectangle((0, 8, CARD_W, NAME_H), fill=(28, 22, 24, 255))

    art_box = (12, ART_TOP + 6, CARD_W - 12, ART_TOP + ART_H - 8)
    art_w = art_box[2] - art_box[0]
    art_h = art_box[3] - art_box[1]
    art_id = (card.get("artId") or "").lower()
    portrait = portraits.get(art_id)
    if portrait and portrait.exists():
        art = Image.open(portrait).convert("RGBA")
        art.thumbnail((art_w, art_h), Image.Resampling.LANCZOS)
        placed = Image.new("RGBA", (art_w, art_h), (8, 6, 8, 255))
        px = (art_w - art.size[0]) // 2
        py = (art_h - art.size[1]) // 2
        placed.alpha_composite(art, (px, py))
        placed.putalpha(_round_mask((art_w, art_h)))
        canvas.alpha_composite(placed, (art_box[0], art_box[1]))
    else:
        draw.rounded_rectangle(art_box, radius=18, fill=(36, 30, 28, 255))

    draw.rectangle((10, CARD_H - TEXT_H, CARD_W - 10, CARD_H - 10), fill=paper)

    title_font = _fit(draw, lambda s: _font(s, True), card.get("name") or "", CARD_W - 88, (22, 18, 16, 14))
    draw.text((16, 16), card.get("name") or "", font=title_font, fill=(245, 238, 220, 255))
    traits = " · ".join(
        bit
        for bit in (
            card.get("type"),
            card.get("subtitle"),
            card.get("faction"),
            card.get("rarity"),
        )
        if bit
    )
    trait_font = _fit(draw, _font, traits, CARD_W - 88, (13, 11, 10))
    draw.text((16, 44), traits, font=trait_font, fill=(196, 180, 150, 255))

    cost = card.get("cost") or ""
    if cost != "" and card.get("type") != "Champion":
        draw.ellipse((CARD_W - 58, 12, CARD_W - 12, 58), fill=edge + (255,))
        cf = _font(22, True)
        tw = draw.textlength(cost, font=cf)
        draw.text((CARD_W - 35 - tw / 2, 20), cost, font=cf, fill=(255, 255, 255, 255))

    thresh = card.get("threshold") or ""
    if thresh:
        draw.text((16, ART_TOP + ART_H - 26), thresh, font=_font(12, True), fill=(230, 220, 190, 255))

    body = card.get("text") or ""
    flavor = card.get("flavour") or ""
    body_font = _font(13)
    lines = _wrap(draw, body, body_font, CARD_W - 36)
    y = CARD_H - TEXT_H + 8
    max_y = CARD_H - 36
    for line in lines:
        if y > max_y:
            break
        draw.text((18, y), line, font=body_font, fill=(28, 24, 20, 255))
        y += 16
    if flavor and y + 16 < max_y:
        y += 4
        for line in _wrap(draw, flavor, _font(11), CARD_W - 36):
            if y > max_y:
                break
            draw.text((18, y), line, font=_font(11), fill=(90, 72, 52, 255))
            y += 14

    stats = []
    if card.get("attack") != "" and card.get("type", "").startswith("Troop"):
        stats.append(f"{card.get('attack') or '0'} / {card.get('defense') or '0'}")
    if card.get("health"):
        stats.append(f"HP {card['health']}")
    if stats:
        label = "   ".join(stats)
        sf = _font(16, True)
        tw = draw.textlength(label, font=sf)
        draw.rounded_rectangle(
            (CARD_W - tw - 28, CARD_H - 38, CARD_W - 12, CARD_H - 12),
            radius=6,
            fill=edge + (255,),
        )
        draw.text((CARD_W - tw - 20, CARD_H - 36), label, font=sf, fill=(255, 255, 255, 255))

    rgb = canvas.convert("RGB")
    rgb.save(dest, "JPEG", quality=86, optimize=True)
    return True


def compose_back(dest: Path) -> None:
    from PIL import Image, ImageDraw

    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (CARD_W, CARD_H), (22, 12, 28))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((14, 14, CARD_W - 14, CARD_H - 14), outline=(168, 132, 48), width=4)
    draw.rectangle((22, 22, CARD_W - 22, CARD_H - 22), outline=(92, 28, 110), width=2)
    font = _font(36, True)
    label = "HEX"
    tw = draw.textlength(label, font=font)
    draw.text(((CARD_W - tw) / 2, CARD_H / 2 - 40), label, font=font, fill=(230, 210, 150))
    sub = _font(16)
    line = "Shards of Fate"
    tw = draw.textlength(line, font=sub)
    draw.text(((CARD_W - tw) / 2, CARD_H / 2 + 8), line, font=sub, fill=(180, 150, 110))
    canvas.save(dest, "JPEG", quality=88)


def compose_lobby(dest: Path, sample: Path | None, label: str) -> None:
    from PIL import Image, ImageDraw

    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (960, 320), (16, 10, 18))
    if sample and sample.exists():
        art = Image.open(sample).convert("RGB")
        art.thumbnail((960, 320), Image.Resampling.LANCZOS)
        canvas.paste(art, ((960 - art.size[0]) // 2, (320 - art.size[1]) // 2))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 230, 960, 320), fill=(12, 8, 14))
    draw.text((28, 242), label, font=_font(28, True), fill=(236, 220, 170))
    canvas.save(dest, "JPEG", quality=88)
