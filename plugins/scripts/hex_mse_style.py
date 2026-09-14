#!/usr/bin/env python3
"""Translate HEX NGUI atlas padding into Magic Set Editor packages.

Each CardTemplate sprite was painted on a full-card canvas, then trimmed into
the atlas. The leftover padding *is* the layout: left/top of the slice on that
canvas. Frames, Elements, and Icons used three scales of the same face; we map
them onto the Elements canvas (448 x 625), which matches Magic's aspect.

  plugins/hex-shards-of-fate/.venv/bin/python plugins/scripts/hex_mse_style.py

Writes:
  plugins/hex-shards-of-fate/mse/packages/
  ~/Library/Application Support/magicseteditor/data/   (if that folder exists)
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import textwrap
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from hex_mse import reslice_from_atlases, scan_ngui_from_assets  # noqa: E402
from hex_catalog import load_gamedata, parse_cards, parse_sets, resolve_hex  # noqa: E402
from hex_art import extract_portraits  # noqa: E402
from hex_rules import KEYWORD_ALIASES, load_keywords  # noqa: E402

KIT = ROOT / "hex-shards-of-fate" / "mse"
PKG = KIT / "packages"
ART_DIR = ROOT / "images" / "hex-shards-of-fate" / "_art"
MSE_DATA = Path.home() / "Library/Application Support/magicseteditor/data"
GAME = "hex"
STYLE = "standard"
MSE_VER = "2.1.2"

# Elements native canvas. GoCardBuilder.s_CardSizeInPx is 437x608 (same aspect).
CARD_W, CARD_H, CARD_DPI = 448, 625, 150

# Typical CardTemplate.m_DefaultLayout UV (left, top, right, bottom).
PORTRAIT_UV = (0.166015625, 0.0322265625, 0.8352585, 0.9658203)

# Official HEX keywords: blue + underline. Numbered ones take a trailing digit (Rage 1).
KEYWORD_COLOR = "rgb(64,176,255)"
NUMBERED_KEYWORDS = frozenset({
    "Rage", "Armor", "Gladiator", "Momentum", "Scrounge", "Tunneling",
})

# GoCardBuilder.BuildThreshold order. "Ruby 2" → two Ruby pips.
PIP_COLORS = ("Blood", "Diamond", "Ruby", "Sapphire", "Wild")
MAX_PIPS = 8
SAMPLE_CARDS = (
    ("Starshield", ""),
    ("Lord Benjamin, the Wise", "Human Mage"),
    ("Emberspire Witch", "Witch"),
    ("Ash Harpy", "Harpy"),
    ("Absolute Power", ""),
    ("Blood Shard", "Standard"),
    ("Talysen's Memorial", ""),
    ("Goreseeker", "Orc Warrior"),
    ("The Triumvirate", "Human Trinity"),
    ("Zoltog", "Orc Ranger"),
)

KEYWORD_LABELS: list[str] = []
_KW_RE: re.Pattern[str] | None = None
_LAYER_CACHE: dict[tuple, object] = {}
_FONT_CACHE: dict[int, object] = {}
_SYMBOL_CACHE: dict[tuple[str, int], object] = {}
_STAMP_LAYOUT = None
_BAND_CACHE = None

SYM_CODES = {
    "BLOOD": "blood",
    "DIAMOND": "diamond",
    "RUBY": "ruby",
    "SAPPHIRE": "sapphire",
    "WILD": "wild",
    "ATK": "atk",
    "DEF": "def",
}


def map_layout(grouped: dict[str, list[dict]], *, verbose: bool = False) -> dict:
    """Scale NGUI leftover padding onto the Elements canvas (448 x 625)."""
    layout = {}
    for key, sprites in grouped.items():
        if not sprites:
            continue
        widths = [s["outer"][0] + s["w"] + s["outer"][1] for s in sprites]
        heights = [s["outer"][2] + s["h"] + s["outer"][3] for s in sprites]
        canvas_w = max(widths)
        canvas_h = max(heights)
        sx, sy = CARD_W / canvas_w, CARD_H / canvas_h
        mapped = {}
        for sprite in sprites:
            mapped[sprite["name"]] = {
                **sprite,
                "canvas": [canvas_w, canvas_h],
                "left": round(sprite["outer"][0] * sx, 2),
                "top": round(sprite["outer"][2] * sy, 2),
                "width": round(sprite["w"] * sx, 2),
                "height": round(sprite["h"] * sy, 2),
            }
        layout[key] = {
            "canvas": [canvas_w, canvas_h],
            "scale": [round(sx, 5), round(sy, 5)],
            "sprites": mapped,
        }
        if verbose:
            print(f"  {key} canvas {canvas_w}x{canvas_h} → {CARD_W}x{CARD_H}  ({len(mapped)} sprites)", flush=True)
    return layout


def layout_from_kit() -> dict:
    """Reuse the last NGUI padding in slices.json. Does not touch the HEX install."""
    slices = json.loads((KIT / "slices.json").read_text())
    grouped = {key: data["sprites"] for key, data in slices["atlases"].items()}
    missing = [s["name"] for sprites in grouped.values() for s in sprites if "outer" not in s]
    if missing:
        raise RuntimeError(f"slices.json has no NGUI padding for {missing[:8]}; run hex_mse_style.py first")
    return map_layout(grouped)


def load_layout(hex_root: Path) -> dict:
    """Map NGUI leftover padding onto the Elements canvas. No UnityPy."""
    slices = json.loads((KIT / "slices.json").read_text())
    expected: dict[str, tuple[int, int]] = {}
    atlas_of: dict[str, str] = {}
    for key, data in slices["atlases"].items():
        for sprite in data["sprites"]:
            expected[sprite["name"]] = (sprite["w"], sprite["h"])
            atlas_of[sprite["name"]] = key
    assets = hex_root / "Hex_Data" / "resources.assets"
    print(f"  scanning {assets.name} for {len(expected)} sprites…", flush=True)
    padded = scan_ngui_from_assets(assets, expected)
    missing = [name for name in expected if name not in padded]
    if missing:
        print(f"  missing padding for {len(missing)}: {missing[:8]}", flush=True)

    grouped: dict[str, list[dict]] = {"Frames": [], "Elements": [], "Icons": []}
    for name, sprite in padded.items():
        key = atlas_of[name]
        grouped[key].append(sprite)
        for raw in slices["atlases"][key]["sprites"]:
            if raw["name"] == name:
                raw["outer"] = sprite["outer"]
                raw["border"] = sprite["border"]
                raw["rotated"] = sprite.get("rotated", False)
                raw["x"] = sprite["x"]
                raw["y"] = sprite["y"]
                raw["w"] = sprite["w"]
                raw["h"] = sprite["h"]
                break
    n = reslice_from_atlases(KIT, {key: {s["name"]: s for s in grouped[key]} for key in grouped})
    print(f"  recut {n} slices (rotated rails turned upright)", flush=True)
    (KIT / "slices.json").write_text(json.dumps(slices, indent=2) + "\n", encoding="utf-8")
    return map_layout(grouped, verbose=True)


def by_name(layout: dict, atlas: str, name: str) -> dict:
    return layout[atlas]["sprites"][name]


def mse_block(lines: list[str], indent: int = 0) -> str:
    pad = "\t" * indent
    return "\n".join(pad + line if line else "" for line in lines) + "\n"


def field(kind: str, name: str, **opts) -> str:
    lines = ["card field:", f"\ttype: {kind}", f"\tname: {name}"]
    for key, value in opts.items():
        attr = key.replace("_", " ")
        if value is True:
            lines.append(f"\t{attr}: true")
        elif value is False:
            lines.append(f"\t{attr}: false")
        elif isinstance(value, list):
            for item in value:
                lines.append(f"\t{attr}: {item}")
        else:
            lines.append(f"\t{attr}: {value}")
    return "\n".join(lines) + "\n\n"


def extra_field(name: str, kind: str = "image", **opts) -> str:
    return field(kind, name, editable=False, save_value=False, **opts).replace("card field:", "extra card field:", 1)


def outlined_font(
    name: str,
    size: int,
    *,
    color: str = "rgb(255,255,255)",
    weight: str = "bold",
    style: str | None = None,
) -> list[str]:
    """Official HEX text is white, bold, with a hairline black outline."""
    lines = [
        "font:",
        f"\tname: {name}",
        f"\tsize: {size}",
        f"\tcolor: {color}",
        f"\tweight: {weight}",
    ]
    if style:
        lines.append(f"\tstyle: {style}")
    lines.extend(
        [
            "\tshadow color: rgb(0,0,0)",
            "\tshadow displacement x: 0.6",
            "\tshadow displacement y: 0.6",
            "\tshadow blur: 0.25",
        ]
    )
    return lines


def mse_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def keyword_entries(keywords: list[tuple[str, str]]) -> list[tuple[str, str]]:
    by_name = {name: reminder for name, reminder in keywords}
    rows = list(keywords)
    for alias, canonical in KEYWORD_ALIASES:
        if alias not in by_name and canonical in by_name:
            rows.append((alias, by_name[canonical]))
    return rows


def keyword_block(name: str, reminder: str) -> str:
    match = f"{name} <atom-param>number</atom-param>" if name in NUMBERED_KEYWORDS else name
    quoted = mse_quote((reminder or name).replace("{", "(").replace("}", ")"))
    return "\n".join(
        [
            "keyword:",
            f"\tkeyword: {name}",
            f"\tmatch: {match}",
            "\tmode: hex",
            f"\treminder: {{ {quoted} }}",
            f"\trules: {quoted}",
            "",
        ]
    )


def switch_box(troop: dict, resource: dict) -> dict:
    return {
        key: f"{{ if is_resource() then {resource[key]} else {troop[key]} }}"
        for key in ("left", "top", "width", "height")
    }


def _dark_edge(px, x: int, y: int, threshold: int = 18) -> bool:
    p = px[x, y]
    if len(p) == 4 and p[3] < 12:
        return True
    return p[0] <= threshold and p[1] <= threshold and p[2] <= threshold


def trim_letterbox(src):
    """Drop fully empty or near-black strips so square portraits aren't padded."""
    bbox = src.getbbox()
    if bbox:
        src = src.crop(bbox)
    w, h = src.size
    if w < 8 or h < 8:
        return src
    px = src.load()
    step_x = max(1, w // 96)
    step_y = max(1, h // 96)

    def col_dark(x: int) -> bool:
        return all(_dark_edge(px, x, y) for y in range(0, h, step_y))

    def row_dark(y: int) -> bool:
        return all(_dark_edge(px, x, y) for x in range(0, w, step_x))

    left, right, top, bottom = 0, w, 0, h
    while left < right - 4 and col_dark(left):
        left += 1
    while right - 1 > left + 4 and col_dark(right - 1):
        right -= 1
    while top < bottom - 4 and row_dark(top):
        top += 1
    while bottom - 1 > top + 4 and row_dark(bottom - 1):
        bottom -= 1
    if left == 0 and top == 0 and right == w and bottom == h:
        return src
    return src.crop((left, top, right, bottom))


def cover_crop(im, width: int, height: int):
    """Fill the box, keep aspect, crop overflow. Trims empty / black edges first."""
    from PIL import Image

    src = trim_letterbox(im.convert("RGBA"))
    if src.width <= 0 or src.height <= 0:
        return Image.new("RGBA", (width, height), (0, 0, 0, 255))
    scale = max(width / src.width, height / src.height)
    nw = max(1, int(src.width * scale + 0.5))
    nh = max(1, int(src.height * scale + 0.5))
    src = src.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max(0, (nw - width) // 2)
    top = max(0, (nh - height) // 2)
    return src.crop((left, top, left + width, top + height))


def pin_icon(rail: dict, bar: dict, icon: dict) -> dict:
    """Sit an icon on the type bar, centered under a vertical rail bezel."""
    return {
        "left": round(rail["left"] + (rail["width"] - icon["width"]) / 2, 2),
        "top": round(bar["top"] + (bar["height"] - icon["height"]) / 2, 2),
        "width": icon["width"],
        "height": icon["height"],
    }


def troop_art_box(layout: dict) -> dict:
    """Portrait well: type-bar width, from under the title to the type bar."""
    title = by_name(layout, "Elements", "TitleBar")
    type_bar = by_name(layout, "Elements", "TypeBar")
    top = title["top"] + title["height"] - 4
    return {
        "left": type_bar["left"],
        "top": round(top, 2),
        "width": type_bar["width"],
        "height": round(type_bar["top"] - top, 2),
    }


def portrait_target_size(card: dict[str, str], layout: dict | None = None) -> tuple[int, int]:
    """Match the MSE art window so ImageValueViewer cannot squash."""
    if (card.get("type") or "").lower() == "resource":
        return CARD_H, CARD_H
    if layout:
        box = troop_art_box(layout)
        return max(1, int(round(box["width"]))), max(1, int(round(box["height"])))
    w = max(1, int(round((PORTRAIT_UV[2] - PORTRAIT_UV[0]) * CARD_W)))
    h = max(1, int(round((PORTRAIT_UV[3] - PORTRAIT_UV[1]) * CARD_H)))
    return w, h


def insert_hex_symbols(text: str) -> str:
    """Turn client tokens and glued ATK/DEF into MSE <sym> tags."""
    if not text:
        return text

    def bracket(match: re.Match[str]) -> str:
        token = match.group(1) or match.group(2)
        return f"<sym>{SYM_CODES.get(token.upper(), token.lower())}</sym>"

    text = re.sub(
        r"\[(BLOOD|DIAMOND|RUBY|SAPPHIRE|WILD|ATK|DEF)\]"
        r"|\[(Blood|Diamond|Ruby|Sapphire|Wild)\s+\d+\]",
        bracket,
        text,
        flags=re.I,
    )
    text = re.sub(r"(\+?-?\d+)ATK", r"\1<sym>atk</sym>", text)
    text = re.sub(r"(\+?-?\d+)DEF", r"\1<sym>def</sym>", text)
    text = re.sub(r"(?<![A-Za-z</])ATK(?![A-Za-z>])", "<sym>atk</sym>", text)
    text = re.sub(r"(?<![A-Za-z</])DEF(?![A-Za-z>])", "<sym>def</sym>", text)
    return text


def keyword_regex() -> re.Pattern[str]:
    global _KW_RE
    if _KW_RE is not None:
        return _KW_RE
    labels = sorted(KEYWORD_LABELS, key=len, reverse=True)
    parts = []
    for label in labels:
        escaped = re.escape(label)
        if label in NUMBERED_KEYWORDS:
            parts.append(rf"{escaped}(?:\s+\d+)?")
        else:
            parts.append(escaped)
    if not parts:
        _KW_RE = re.compile(r"(?!x)x")
    else:
        _KW_RE = re.compile(r"\b(" + "|".join(parts) + r")\b", re.I)
    return _KW_RE


def write_symbol_font(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    copies = {
        "blood.png": KIT / "slices" / "icons" / "Threshold_Blood.png",
        "diamond.png": KIT / "slices" / "icons" / "Threshold_Diamond.png",
        "ruby.png": KIT / "slices" / "icons" / "Threshold_Ruby.png",
        "sapphire.png": KIT / "slices" / "icons" / "Threshold_Sapphire.png",
        "wild.png": KIT / "slices" / "icons" / "Threshold_Wild.png",
        "atk.png": KIT / "slices" / "elements" / "AttackIcon.png",
        "def.png": KIT / "slices" / "elements" / "DefenseIcon.png",
    }
    for name, src in copies.items():
        if not src.exists():
            continue
        from PIL import Image

        im = Image.open(src).convert("RGBA")
        bbox = im.getbbox()
        if bbox:
            im = im.crop(bbox)
        im.save(dest / name)
    lines = [
        f"mse version: {MSE_VER}",
        "short name: HEX symbols",
        "full name: HEX inline symbols",
        "version: 0.1.1",
        "image font size: 40",
        "horizontal space: 0.15",
        "",
    ]
    for code in ("blood", "diamond", "ruby", "sapphire", "wild", "atk", "def"):
        lines.extend(
            [
                "symbol:",
                f"\tcode: {code}",
                f"\timage: {code}.png",
                "",
            ]
        )
    (dest / "symbol-font").write_text("\n".join(lines), encoding="utf-8")


def face_font(size: int):
    from PIL import ImageFont

    if size not in _FONT_CACHE:
        path = KIT / "fonts" / "Hex_Arial_Bold.ttf"
        try:
            _FONT_CACHE[size] = ImageFont.truetype(str(path), size)
        except OSError:
            _FONT_CACHE[size] = ImageFont.load_default()
    return _FONT_CACHE[size]


def chrome_layer(atlas: str, name: str, box: dict):
    from PIL import Image

    width = max(1, int(box["width"]))
    height = max(1, int(box["height"]))
    key = (atlas, name, width, height)
    if key not in _LAYER_CACHE:
        folder = {"Frames": "frames", "Elements": "elements", "Icons": "icons"}[atlas]
        path = KIT / "slices" / folder / f"{name}.png"
        if not path.exists():
            _LAYER_CACHE[key] = None
        else:
            _LAYER_CACHE[key] = Image.open(path).convert("RGBA").resize((width, height), Image.Resampling.LANCZOS)
    return _LAYER_CACHE[key]


def resource_title_band():
    global _BAND_CACHE
    if _BAND_CACHE is not None:
        return _BAND_CACHE
    path = KIT / "slices" / "elements" / "ResourceTitleBand.png"
    if not path.exists():
        write_resource_title_band(path)
    from PIL import Image

    band = Image.open(path).convert("RGBA")
    if band.size[0] != CARD_W:
        band = band.resize((CARD_W, band.height), Image.Resampling.LANCZOS)
    _BAND_CACHE = band
    return band


def prepare_faces(hex_root: Path) -> dict:
    """Load kit layout + keyword list so tabletop faces can be stamped."""
    global KEYWORD_LABELS, _KW_RE
    layout = layout_from_kit()
    band = KIT / "slices" / "elements" / "ResourceTitleBand.png"
    if not band.exists():
        write_resource_title_band(band)
    ui_xml = hex_root / "Data" / "Localization" / "hex_uidata_en.xml"
    KEYWORD_LABELS = [name for name, _ in keyword_entries(load_keywords(ui_xml))]
    _KW_RE = None
    return layout


def save_plugin_face(layout: dict, card: dict[str, str], portrait: Path | None, dest: Path) -> None:
    face = render_face(layout, card, Path(portrait) if portrait else None)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    face.convert("RGB").save(dest, "JPEG", quality=88)
    dest.with_suffix(".png").unlink(missing_ok=True)


def _init_stamp_worker(hex_root: str) -> None:
    global _STAMP_LAYOUT
    _STAMP_LAYOUT = prepare_faces(Path(hex_root))


def _stamp_one(payload: tuple) -> tuple[str, str, bool, str]:
    card, dest, portrait = payload
    try:
        save_plugin_face(_STAMP_LAYOUT, card, Path(portrait) if portrait else None, Path(dest))
        return card.get("name") or dest, dest, True, ""
    except Exception as exc:
        return card.get("name") or dest, dest, False, str(exc)


def stamp_jobs(
    hex_root: Path,
    jobs: list[tuple[dict[str, str], str, str | None]],
    workers: int = 6,
) -> tuple[int, set[str]]:
    """Stamp tabletop JPEGs. Returns (ok_count, failed dest paths)."""
    failed: set[str] = set()
    ok = 0
    total = len(jobs)
    if total == 0:
        return 0, failed
    if workers <= 1:
        layout = prepare_faces(hex_root)
        for i, (card, dest, portrait) in enumerate(jobs, 1):
            try:
                save_plugin_face(layout, card, Path(portrait) if portrait else None, Path(dest))
                ok += 1
            except Exception as exc:
                failed.add(dest)
                print(f"  stamp failed {card.get('name')}: {exc}", flush=True)
            if i % 100 == 0 or i == total:
                print(f"  stamped {i}/{total}", flush=True)
        return ok, failed
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_stamp_worker, initargs=(str(hex_root),)) as pool:
        futures = [pool.submit(_stamp_one, job) for job in jobs]
        done = 0
        for fut in as_completed(futures):
            name, dest, success, err = fut.result()
            done += 1
            if success:
                ok += 1
            else:
                failed.add(dest)
                print(f"  stamp failed {name}: {err}", flush=True)
            if done % 100 == 0 or done == total:
                print(f"  stamped {done}/{total}", flush=True)
    return ok, failed


def load_symbol_image(code: str, height: int):
    from PIL import Image

    key = (code, height)
    if key in _SYMBOL_CACHE:
        return _SYMBOL_CACHE[key]
    folder = "icons" if code in {"blood", "diamond", "ruby", "sapphire", "wild"} else "elements"
    name = {
        "blood": "Threshold_Blood.png",
        "diamond": "Threshold_Diamond.png",
        "ruby": "Threshold_Ruby.png",
        "sapphire": "Threshold_Sapphire.png",
        "wild": "Threshold_Wild.png",
        "atk": "AttackIcon.png",
        "def": "DefenseIcon.png",
    }[code]
    path = KIT / "slices" / folder / name
    if not path.exists():
        _SYMBOL_CACHE[key] = None
        return None
    im = Image.open(path).convert("RGBA")
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    scale = height / max(1, im.height)
    icon = im.resize((max(1, int(im.width * scale)), height), Image.Resampling.LANCZOS)
    _SYMBOL_CACHE[key] = icon
    return icon


def write_resource_title_band(path: Path, width: int = CARD_W, height: int = 108) -> None:
    from PIL import Image

    band = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    px = band.load()
    fade_start = int(height * 0.55)
    for y in range(height):
        if y < fade_start:
            alpha = 232
        else:
            t = (y - fade_start) / max(1, height - fade_start - 1)
            alpha = int(232 * (1 - t) ** 1.25)
        for x in range(width):
            px[x, y] = (0, 0, 0, max(0, min(255, alpha)))
    path.parent.mkdir(parents=True, exist_ok=True)
    band.save(path)


def stat_box(frame: dict) -> dict:
    """Sit ATK/DEF in the visual well of AtkDefFrame, a bit below geometric center."""
    return {
        "left": round(frame["left"] + 14, 2),
        "top": round(frame["top"] + 20, 2),
        "width": round(frame["width"] - 28, 2),
        "height": round(frame["height"] - 32, 2),
    }


def style_box(name: str, box: dict, z: int, extra: list[str] | None = None) -> str:
    lines = [
        f"{name}:",
        f"\tleft: {box['left']}",
        f"\ttop: {box['top']}",
        f"\twidth: {box['width']}",
        f"\theight: {box['height']}",
        f"\tz index: {z}",
    ]
    if extra:
        lines.extend("\t" + line for line in extra)
    return mse_block(lines, 1)


def write_game(dest: Path, keywords: list[tuple[str, str]]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    text_script = (
        '{ expand_keywords(default_expand: { true }, '
        f'combine: {{ "<color:{KEYWORD_COLOR}><u>" + keyword + "</u></color>" }}) }}'
    )
    parts = [
        f"mse version: {MSE_VER}",
        "short name: HEX",
        "full name: HEX: Shards of Fate",
        "version: 0.1.2",
        "",
        "has keywords: true",
        "",
        "keyword mode:",
        "\tname: hex",
        "\tdescription: HEX glossary",
        "\tis default: true",
        "",
        "keyword parameter type:",
        "\tname: number",
        "\tdescription: A number after a keyword, such as Rage 1",
        "\tmatch: [0-9]+",
        '\tseparator before is: " "',
        "\toptional: true",
        "",
        "set field:",
        "\ttype: text",
        "\tname: title",
        "\tidentifying: true",
        "",
        "set field:",
        "\ttype: text",
        "\tname: description",
        "\tmulti line: true",
        "",
        field("text", "name", identifying=True),
        field("text", "card_type", description="Troop, Basic Action, Quick Action, Constant, Artifact, Resource, Champion, …"),
        field("text", "subtype"),
        field(
            "text",
            "type_line",
            editable=False,
            save_value=False,
            script='{ to_upper(card.card_type) + (if to_lower(card.card_type) == "resource" then "" else (if card.subtype != "" then " -- " + card.subtype else "")) + (if card.unique == "yes" then " Unique" else "") }',
        ),
        field("text", "cost"),
        field("text", "threshold", description="Blood / Ruby / Diamond / Sapphire / Wild, comma-separated"),
        field("text", "text", multi_line=True, script=text_script),
        field("text", "flavor", multi_line=True),
        field("text", "attack"),
        field("text", "defense"),
        field("text", "health"),
        field(
            "choice",
            "rarity",
            choice=["Common", "Uncommon", "Rare", "Legendary", "Epic", "Promo", "Land", "Champion"],
        ),
        field("choice", "faction", choice=["", "Ardent", "Underworld", "Neutral"]),
        field("choice", "pve", choice=["no", "yes"], default="no"),
        field("choice", "unique", choice=["no", "yes"], default="no"),
        field("choice", "immortal", choice=["no", "yes"], default="no", description="CardTemplate.IsImmortal() — Immortal-format chrome, not the keyword"),
        field("image", "art"),
    ]
    entries = keyword_entries(keywords)
    for name, reminder in entries:
        parts.append(keyword_block(name, reminder))
    (dest / "game").write_text("\n".join(parts), encoding="utf-8")
    print(f"  {len(entries)} keywords", flush=True)


def frame_family_script() -> str:
    # GoCardBuilder.BuildFrame + CardTemplate.get_CardShards / Is*
    return """
shard_colors := {
	th := to_lower(card.threshold)
	(if contains(input: th, match: "blood") then 1 else 0) + (if contains(input: th, match: "ruby") then 1 else 0) + (if contains(input: th, match: "diamond") then 1 else 0) + (if contains(input: th, match: "sapphire") then 1 else 0) + (if contains(input: th, match: "wild") then 1 else 0)
}
is_champion := { to_lower(card.card_type) == "champion" }
is_artifact := { contains(input: to_lower(card.card_type), match: "artifact") }
is_troop := { contains(input: to_lower(card.card_type), match: "troop") }
is_resource := { to_lower(card.card_type) == "resource" }
is_choice := { to_lower(card.card_type) == "choice" }
is_bane := { contains(input: to_lower(card.card_type), match: "bane") }
is_resource_or_choice := { is_resource() or is_choice() }
is_pve := { card.pve == "yes" }
is_basic_resource := { is_resource() and contains(input: to_lower(card.subtype), match: "standard") }
is_immortal := { card.immortal == "yes" }
frame_family := {
	n := shard_colors()
	if n == 0 and is_champion() then "Multi"
	else if n == 0 then "Shardless"
	else if n > 1 then "Multi"
	else if is_artifact() then "Artifact"
	else if contains(input: to_lower(card.threshold), match: "blood") then "Blood"
	else if contains(input: to_lower(card.threshold), match: "ruby") then "Ruby"
	else if contains(input: to_lower(card.threshold), match: "diamond") then "Diamond"
	else if contains(input: to_lower(card.threshold), match: "sapphire") then "Sapphire"
	else if contains(input: to_lower(card.threshold), match: "wild") then "Wild"
	else "Shardless"
}
shard_count := {
	name := input
	th := to_lower(card.threshold)
	if contains(input: th, match: name + " 6") then 6
	else if contains(input: th, match: name + " 5") then 5
	else if contains(input: th, match: name + " 4") then 4
	else if contains(input: th, match: name + " 3") then 3
	else if contains(input: th, match: name + " 2") then 2
	else if contains(input: th, match: name) then 1
	else 0
}
pip_color := {
	i := input
	b := shard_count("blood")
	d := shard_count("diamond")
	r := shard_count("ruby")
	s := shard_count("sapphire")
	w := shard_count("wild")
	if i <= 0 then ""
	else if i <= b then "Blood"
	else if i <= b + d then "Diamond"
	else if i <= b + d + r then "Ruby"
	else if i <= b + d + r + s then "Sapphire"
	else if i <= b + d + r + s + w then "Wild"
	else ""
}
""".strip()


def write_style(dest: Path, layout: dict) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for folder in ("frames", "elements", "icons"):
        src = KIT / "slices" / folder
        target = dest / folder
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target)
    write_resource_title_band(dest / "elements" / "ResourceTitleBand.png")
    write_resource_title_band(KIT / "slices" / "elements" / "ResourceTitleBand.png")
    if (KIT / "extras" / "CardSleeve_Default.png").exists():
        shutil.copy2(KIT / "extras" / "CardSleeve_Default.png", dest / "sleeve.png")

    fr = lambda n: by_name(layout, "Frames", n)
    el = lambda n: by_name(layout, "Elements", n)
    ic = lambda n: by_name(layout, "Icons", n)

    title = el("TitleBar")
    type_bar = el("TypeBar")
    text_box = fr("Blood_Text")
    mana = el("ManaCost")
    atkdef = el("AtkDefFrame")
    defframe = {
        "left": round(CARD_W - atkdef["left"] - atkdef["width"], 2),
        "top": atkdef["top"],
        "width": atkdef["width"],
        "height": atkdef["height"],
    }
    uv_l, uv_t, uv_r, uv_b = PORTRAIT_UV
    art = {
        "left": round(uv_l * CARD_W, 2),
        "top": round(uv_t * CARD_H, 2),
        "width": round((uv_r - uv_l) * CARD_W, 2),
        "height": round((uv_b - uv_t) * CARD_H, 2),
    }
    name_box = {
        "left": mana["left"] + mana["width"] + 4,
        "top": title["top"] + 6,
        "width": title["left"] + title["width"] - (mana["left"] + mana["width"] + 12),
        "height": title["height"] - 10,
    }
    type_text = {
        "left": type_bar["left"] + 46,
        "top": type_bar["top"] + 4,
        "width": type_bar["width"] - 92,
        "height": type_bar["height"] - 6,
    }
    body = {
        "left": text_box["left"] + 8,
        "top": text_box["top"] + 8,
        "width": text_box["width"] - 16,
        "height": max(40.0, atkdef["top"] - text_box["top"] - 6),
    }
    flavor = {
        "left": atkdef["left"] + atkdef["width"] + 4,
        "top": atkdef["top"] + 28,
        "width": max(40.0, defframe["left"] - (atkdef["left"] + atkdef["width"]) - 8),
        "height": 32,
    }
    atk = stat_box(atkdef)
    defense = stat_box(defframe)
    cost_box = {
        "left": mana["left"] + 10,
        "top": mana["top"] + 16,
        "width": mana["width"] - 20,
        "height": mana["height"] - 20,
    }
    pip0 = ic("Threshold_Ruby")
    pip_stride = pip0["height"] + 2
    res_mana = el("ResourceManaCost")
    res_name = {"left": 20, "top": 10, "width": CARD_W - 40, "height": 52}
    res_type = {
        "left": round(res_mana["left"] + res_mana["width"] + 8, 2),
        "top": round(res_mana["top"] + 6, 2),
        "width": 240,
        "height": round(res_mana["height"] - 10, 2),
    }
    res_body = {
        "left": round(res_mana["left"] + res_mana["width"] + 8, 2),
        "top": round(res_mana["top"] + 40, 2),
        "width": round(CARD_W - (res_mana["left"] + res_mana["width"] + 24), 2),
        "height": max(40.0, CARD_H - (res_mana["top"] + 42)),
    }
    troop_art = troop_art_box(layout)
    res_art = {
        "left": round((CARD_W - CARD_H) / 2, 2),
        "top": 0,
        "width": CARD_H,
        "height": CARD_H,
    }
    res_stats = {
        "left": round(res_mana["left"] + 18, 2),
        "top": round(res_mana["top"] + 8, 2),
        "width": round(res_mana["width"] - 36, 2),
        "height": round(res_mana["height"] - 14, 2),
    }
    res_rarity = {
        "left": round(CARD_W - ic("Rarity_Rare")["width"] - 16, 2),
        "top": round(res_mana["top"] + (res_mana["height"] - ic("Rarity_Rare")["height"]) / 2, 2),
        "width": ic("Rarity_Rare")["width"],
        "height": ic("Rarity_Rare")["height"],
    }
    res_faction = {
        "left": round(res_rarity["left"] - ic("Faction_Neutral")["width"] - 6, 2),
        "top": round(res_mana["top"] + (res_mana["height"] - ic("Faction_Neutral")["height"]) / 2, 2),
        "width": ic("Faction_Neutral")["width"],
        "height": ic("Faction_Neutral")["height"],
    }

    head = [
        f"mse version: {MSE_VER}",
        f"game: {GAME}",
        "short name: Standard",
        "full name: HEX card (client layout)",
        "version: 0.1.6",
        f"depends on: {GAME}.mse-game 0.1.2",
        "depends on: hex-inline.mse-symbol-font 0.1.1",
        "",
        f"card width: {CARD_W}",
        f"card height: {CARD_H}",
        f"card dpi: {CARD_DPI}",
        "card background: rgb(8,6,8)",
        "",
        "init script:",
        *[f"\t{line}" if line else "\t" for line in frame_family_script().splitlines()],
        "",
        "card style:",
    ]
    text_style = [
        'alignment: { if is_resource() then "center middle shrink-overflow" else "left middle shrink-overflow" }',
        "font:",
        "\tname: Hex_Arial_Bold",
        '\tsize: { if is_resource() then 23 else 15 }',
        "\tcolor: rgb(255,255,255)",
        "\tweight: bold",
        "\tshadow color: rgb(0,0,0)",
        "\tshadow displacement x: 0.6",
        "\tshadow displacement y: 0.6",
        "\tshadow blur: 0.25",
    ]
    body_style = [
        "alignment: top left",
        "padding top: 2",
        *outlined_font("Hex_Arial_Bold", 12),
        "symbol font:",
        "\tname: hex-inline",
        "\tsize: 13",
        "\talignment: middle center",
    ]
    cost_style = [
        "alignment: center middle shrink-overflow",
        "visible: { not is_choice() and not is_resource() }",
        *outlined_font("Hex_Arial_Bold", 30),
    ]
    stat_style = [
        "alignment: center middle shrink-overflow",
        "padding top: 2",
        "visible: { is_troop() }",
        *outlined_font("Hex_Arial_Bold", 28),
    ]

    chunks = ["\n".join(head) + "\n"]
    chunks.append(style_box("name", switch_box(name_box, res_name), 30, text_style))
    chunks.append(style_box("card_type", {"left": 0, "top": 0, "width": 1, "height": 1}, 0, ["visible: false"]))
    chunks.append(style_box("subtype", {"left": 0, "top": 0, "width": 1, "height": 1}, 0, ["visible: false"]))
    chunks.append(
        style_box(
            "type_line",
            switch_box(type_text, res_type),
            30,
            [
                "alignment: left middle shrink-overflow",
                *outlined_font("Hex_Arial_Bold", 12),
            ],
        )
    )
    chunks.append(style_box("cost", cost_box, 31, cost_style))
    chunks.append(style_box("threshold", {"left": 0, "top": 0, "width": 1, "height": 1}, 0, ["visible: false"]))
    chunks.append(style_box("text", switch_box(body, res_body), 30, body_style))
    chunks.append(style_box("flavor", flavor, 30, [
        "alignment: middle center",
        "visible: { not is_resource() }",
        *outlined_font("Hex_Arial_Bold", 9, style="italic"),
    ]))
    chunks.append(style_box("attack", atk, 32, stat_style))
    chunks.append(style_box("defense", defense, 32, stat_style))
    chunks.append(style_box("health", {"left": atkdef["left"] + 20, "top": atkdef["top"] + 8, "width": 48, "height": 20}, 32, [
        "alignment: center middle",
        "visible: { card.health != \"\" }",
        *outlined_font("Hex_Arial_Bold", 12),
    ]))
    rarity = ic("Rarity_Rare")
    fac = ic("Faction_Ardent")
    troop_rarity = pin_icon(el("GemBar"), type_bar, rarity)
    troop_faction = pin_icon(el("ThresholdBar"), type_bar, fac)
    chunks.append(style_box("rarity", switch_box(troop_rarity, res_rarity), 29, [
        "render style: image",
        "visible: { card.rarity != \"\" }",
        "choice images:",
        "\tCommon: icons/Rarity_Common.png",
        "\tUncommon: icons/Rarity_Uncommon.png",
        "\tRare: icons/Rarity_Rare.png",
        "\tLegendary: icons/Rarity_Legendary.png",
        "\tEpic: icons/Rarity_Epic.png",
        "\tPromo: icons/Rarity_Rare.png",
        "\tLand: icons/Rarity_Common.png",
        "\tChampion: icons/Rarity_Legendary.png",
    ]))
    chunks.append(style_box("faction", switch_box(troop_faction, res_faction), 29, [
        "render style: image",
        'visible: { card.faction != "" }',
        "choice images:",
        "\tArdent: icons/Faction_Ardent.png",
        "\tUnderworld: icons/Faction_Underworld.png",
        "\tNeutral: icons/Faction_Neutral.png",
    ]))
    for hidden in ("pve", "unique", "immortal"):
        chunks.append(style_box(hidden, {"left": 0, "top": 0, "width": 1, "height": 1}, 0, ["visible: false"]))
    chunks.append(style_box("art", switch_box(troop_art, res_art), 2))

    extras = []
    extras.append(extra_field("frame_top"))
    extras.append(extra_field("frame_bottom"))
    extras.append(extra_field("frame_left"))
    extras.append(extra_field("frame_right"))
    extras.append(extra_field("frame_text"))
    extras.append(extra_field("chrome_title"))
    extras.append(extra_field("chrome_type"))
    extras.append(extra_field("chrome_threshold"))
    for i in range(1, MAX_PIPS + 1):
        extras.append(extra_field(f"pip_{i}"))
    extras.append(extra_field("chrome_gembar"))
    extras.append(extra_field("chrome_bottom"))
    extras.append(extra_field("chrome_mana"))
    extras.append(extra_field("chrome_resource_mana"))
    extras.append(extra_field("chrome_resource_title"))
    extras.append(extra_field("resource_stats", kind="text", script='{ if to_lower(card.card_type) == "resource" then (if card.attack != "" and card.attack != "0" then card.attack else "1") + "/" + (if card.defense != "" and card.defense != "0" then card.defense else "1") else "" }'))
    extras.append(extra_field("chrome_atkdef"))
    extras.append(extra_field("chrome_defframe"))
    extras.append(extra_field("chrome_format"))
    extras.append(extra_field("sleeve"))

    extra_style = ["extra card style:\n"]
    hide_if_resource = "visible: { not is_resource_or_choice() }"
    extra_style.append(style_box("frame_top", fr("Blood_1"), 8, [
        "render style: image",
        hide_if_resource,
        "image: { \"frames/\" + frame_family() + \"_1.png\" }",
    ]))
    extra_style.append(style_box("frame_bottom", fr("Blood_2"), 8, [
        "render style: image",
        hide_if_resource,
        "image: { \"frames/\" + frame_family() + \"_2.png\" }",
    ]))
    extra_style.append(style_box("frame_left", fr("Blood_3"), 8, [
        "render style: image",
        hide_if_resource,
        "image: { \"frames/\" + frame_family() + \"_3.png\" }",
    ]))
    extra_style.append(style_box("frame_right", fr("Blood_4"), 8, [
        "render style: image",
        hide_if_resource,
        "image: { \"frames/\" + frame_family() + \"_4.png\" }",
    ]))
    extra_style.append(style_box("frame_text", fr("Blood_Text"), 7, [
        "render style: image",
        hide_if_resource,
        "image: { \"frames/\" + frame_family() + \"_Text.png\" }",
    ]))
    extra_style.append(style_box("chrome_title", el("TitleBar"), 12, [
        "render style: image",
        hide_if_resource,
        "image: { if is_pve() then \"elements/TitleBarPVE_1.png\" else \"elements/TitleBar.png\" }",
    ]))
    extra_style.append(style_box("chrome_type", el("TypeBar"), 12, [
        "render style: image",
        hide_if_resource,
        "image: elements/TypeBar.png",
    ]))
    extra_style.append(style_box("chrome_threshold", el("ThresholdBar"), 11, [
        "render style: image",
        hide_if_resource,
        "image: elements/ThresholdBar.png",
    ]))
    for i in range(1, MAX_PIPS + 1):
        extra_style.append(style_box(
            f"pip_{i}",
            {
                "left": pip0["left"],
                "top": round(pip0["top"] + (i - 1) * pip_stride, 2),
                "width": pip0["width"],
                "height": pip0["height"],
            },
            15,
            [
                "render style: image",
                f'visible: {{ pip_color({i}) != "" and not is_resource_or_choice() }}',
                f'image: {{ "icons/Threshold_" + pip_color({i}) + ".png" }}',
            ],
        ))
    extra_style.append(style_box("chrome_gembar", el("GemBar"), 11, [
        "render style: image",
        hide_if_resource,
        "image: elements/GemBar.png",
    ]))
    extra_style.append(style_box("chrome_bottom", el("BottomBar"), 12, [
        "render style: image",
        hide_if_resource,
        "image: elements/BottomBar.png",
    ]))
    extra_style.append(style_box("chrome_mana", el("ManaCost"), 13, [
        "render style: image",
        "visible: { not is_resource_or_choice() }",
        'image: { if is_bane() then "elements/BaneSkull.png" else if is_immortal() then "elements/ManaCostImmortal.png" else "elements/ManaCost.png" }',
    ]))
    extra_style.append(style_box("chrome_resource_mana", el("ResourceManaCost"), 13, [
        "render style: image",
        "visible: { is_resource() and not is_choice() }",
        'image: { if is_immortal() and not is_basic_resource() then "elements/ResourceManaCostImmortal.png" else "elements/ResourceManaCost.png" }',
    ]))
    extra_style.append(style_box("chrome_resource_title", {"left": 0, "top": 0, "width": CARD_W, "height": 108}, 12, [
        "render style: image",
        "visible: { is_resource() and not is_choice() }",
        "image: elements/ResourceTitleBand.png",
    ]))
    extra_style.append(style_box("resource_stats", res_stats, 31, [
        "alignment: center middle shrink-overflow",
        "visible: { is_resource() and not is_choice() }",
        *outlined_font("Hex_Arial_Bold", 20),
    ]))
    extra_style.append(style_box("chrome_atkdef", atkdef, 13, [
        "render style: image",
        "visible: { is_troop() and not is_resource_or_choice() }",
        "image: elements/AtkDefFrame.png",
    ]))
    extra_style.append(style_box("chrome_defframe", defframe, 13, [
        "render style: image",
        "visible: { is_troop() and not is_resource_or_choice() }",
        "image: elements/AtkDefFrame.png",
    ]))
    extra_style.append(style_box("chrome_format", el("PVE"), 14, [
        "render style: image",
        "visible: { is_pve() or is_immortal() }",
        'image: { if is_pve() then "elements/PVE.png" else "elements/Immortal.png" }',
    ]))
    extra_style.append(style_box("sleeve", {"left": 0, "top": 0, "width": CARD_W, "height": CARD_H}, 0, [
        "visible: false",
        "render style: image",
        "image: sleeve.png",
    ]))

    (dest / "style").write_text("".join(chunks) + "".join(extras) + "".join(extra_style), encoding="utf-8")

    (KIT / "layout.json").write_text(
        json.dumps(
            {
                "card": [CARD_W, CARD_H],
                "dpi": CARD_DPI,
                "note": "NGUI leftover padding mapped onto the Elements canvas. Conditions are GoCardBuilder.BuildFrame / BuildResourceOrChoiceCard / CardTemplate.Is*.",
                "client_card_px": [437, 608],
                "portrait_uv": list(PORTRAIT_UV),
                "art": art,
                "atlases": {key: {"canvas": val["canvas"], "scale": val["scale"]} for key, val in layout.items()},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def install_fonts() -> None:
    fonts = Path.home() / "Library" / "Fonts"
    if not fonts.exists():
        return
    for ttf in (KIT / "fonts").glob("*.ttf"):
        dest = fonts / ttf.name
        if not dest.exists():
            shutil.copy2(ttf, dest)
            print(f"  installed font {ttf.name}", flush=True)


def install_packages(*packages: Path) -> None:
    if not MSE_DATA.exists():
        return
    MSE_DATA.mkdir(parents=True, exist_ok=True)
    for src in packages:
        dest = MSE_DATA / src.name
        if dest.resolve() == src.resolve():
            continue
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        print(f"  installed {dest}", flush=True)


def write_preview(layout: dict, dest: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    dest.parent.mkdir(parents=True, exist_ok=True)
    card = Image.new("RGBA", (CARD_W, CARD_H), (12, 8, 10, 255))
    draw = ImageDraw.Draw(card)

    def paste(atlas: str, name: str) -> None:
        box = by_name(layout, atlas, name)
        folder = {"Frames": "frames", "Elements": "elements", "Icons": "icons"}[atlas]
        path = KIT / "slices" / folder / f"{name}.png"
        if not path.exists():
            return
        layer = Image.open(path).convert("RGBA").resize(
            (max(1, int(box["width"])), max(1, int(box["height"]))), Image.Resampling.LANCZOS
        )
        card.paste(layer, (int(box["left"]), int(box["top"])), layer)

    paste("Frames", "Ruby_1")
    paste("Frames", "Ruby_2")
    paste("Frames", "Ruby_3")
    paste("Frames", "Ruby_4")
    paste("Frames", "Ruby_Text")
    paste("Elements", "TitleBar")
    paste("Elements", "TypeBar")
    paste("Elements", "ThresholdBar")
    paste("Elements", "GemBar")
    paste("Elements", "BottomBar")
    paste("Elements", "ManaCost")
    paste("Elements", "AtkDefFrame")
    atkdef = by_name(layout, "Elements", "AtkDefFrame")
    def_left = int(CARD_W - atkdef["left"] - atkdef["width"])
    def_path = KIT / "slices" / "elements" / "AtkDefFrame.png"
    if def_path.exists():
        layer = Image.open(def_path).convert("RGBA").resize(
            (max(1, int(atkdef["width"])), max(1, int(atkdef["height"]))), Image.Resampling.LANCZOS
        )
        card.paste(layer, (def_left, int(atkdef["top"])), layer)
    paste("Icons", "Rarity_Rare")
    paste("Icons", "Faction_Ardent")
    pip0 = by_name(layout, "Icons", "Threshold_Ruby")
    pip_path = KIT / "slices" / "icons" / "Threshold_Ruby.png"
    if pip_path.exists():
        pip_img = Image.open(pip_path).convert("RGBA").resize(
            (max(1, int(pip0["width"])), max(1, int(pip0["height"]))), Image.Resampling.LANCZOS
        )
        for i in range(2):
            card.paste(
                pip_img,
                (int(pip0["left"]), int(pip0["top"] + i * (pip0["height"] + 2))),
                pip_img,
            )
    try:
        name_font = ImageFont.truetype(str(KIT / "fonts" / "Hex_Arial_Bold.ttf"), 16)
        type_font = ImageFont.truetype(str(KIT / "fonts" / "Hex_Arial_Bold.ttf"), 13)
        body_font = ImageFont.truetype(str(KIT / "fonts" / "Hex_Arial_Bold.ttf"), 13)
        cost_font = ImageFont.truetype(str(KIT / "fonts" / "Hex_Arial_Bold.ttf"), 30)
        stat_font = ImageFont.truetype(str(KIT / "fonts" / "Hex_Arial_Bold.ttf"), 30)
        flavor_font = ImageFont.truetype(str(KIT / "fonts" / "Hex_Arial_Bold.ttf"), 10)
    except OSError:
        name_font = type_font = body_font = cost_font = stat_font = flavor_font = ImageFont.load_default()

    def outlined(xy, text, font, fill=(255, 255, 255), **kwargs):
        x, y = xy
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font, **kwargs)
        draw.text(xy, text, fill=fill, font=font, **kwargs)

    def keyword(xy, word, font):
        outlined(xy, word, font, fill=(64, 176, 255))
        box = draw.textbbox(xy, word, font=font)
        draw.line((box[0], box[3], box[2], box[3]), fill=(64, 176, 255), width=2)

    outlined((90, 18), "Example Troop", name_font)
    outlined((36.5, 40), "3", cost_font, anchor="mm")
    outlined((90, by_name(layout, "Elements", "TypeBar")["top"] + 6), "TROOP -- Human Warrior", type_font)
    text_box = by_name(layout, "Frames", "Ruby_Text")
    tx, ty = text_box["left"] + 10, text_box["top"] + 12
    keyword((tx, ty), "Speed", body_font)
    keyword((tx, ty + 18), "Deploy", body_font)
    deploy_box = draw.textbbox((tx, ty + 18), "Deploy", font=body_font)
    outlined((deploy_box[2] + 4, ty + 18), "— Draw a card.", body_font)
    atk_s = stat_box(atkdef)
    def_s = stat_box({"left": def_left, "top": atkdef["top"], "width": atkdef["width"], "height": atkdef["height"]})
    outlined((atk_s["left"] + atk_s["width"] / 2, atk_s["top"] + atk_s["height"] / 2), "2", stat_font, anchor="mm")
    outlined((def_s["left"] + def_s["width"] / 2, def_s["top"] + def_s["height"] / 2), "2", stat_font, anchor="mm")
    flavor_x = atkdef["left"] + atkdef["width"] + 8
    outlined((flavor_x, atkdef["top"] + atkdef["height"] / 2), '"Steel remembers."', flavor_font, fill=(220, 220, 220), anchor="lm")
    card.convert("RGB").save(dest)
    print(f"  preview {dest}", flush=True)


def expand_pips(threshold: str) -> list[str]:
    th = (threshold or "").lower()
    out: list[str] = []
    for color in PIP_COLORS:
        name = color.lower()
        count = 0
        for n in range(6, 1, -1):
            if f"{name} {n}" in th:
                count = n
                break
        if count == 0 and name in th:
            count = 1
        out.extend([color] * count)
    return out


def set_field(name: str, value: str) -> str:
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    if "\n" in text:
        lines = [f"\t{name}:"]
        lines.extend(f"\t\t{line}" for line in text.split("\n"))
        return "\n".join(lines)
    return f"\t{name}: {text}"


def pick_sample_cards(hex_root: Path) -> list[dict[str, str]]:
    print("  reading gamedata for sample cards…", flush=True)
    raw = load_gamedata(hex_root)
    cards = parse_cards(raw, parse_sets(raw))
    by_key = {(c["name"], c.get("subtitle") or ""): c for c in cards}
    by_name: dict[str, dict[str, str]] = {}
    for card in cards:
        by_name.setdefault(card["name"], card)
    picked: list[dict[str, str]] = []
    for name, subtitle in SAMPLE_CARDS:
        card = by_key.get((name, subtitle)) or (by_name.get(name) if not subtitle else None)
        if card:
            picked.append(card)
        else:
            print(f"  missing sample {name}", flush=True)
    return picked


def resolve_portraits(hex_root: Path, cards: list[dict[str, str]]) -> dict[str, Path]:
    art_ids = {card["artId"] for card in cards if card.get("artId")}
    found = {key: ART_DIR / f"{key}.png" for key in art_ids if (ART_DIR / f"{key}.png").exists()}
    missing = art_ids - set(found)
    if missing:
        print(f"  extracting {len(missing)} portraits…", flush=True)
        found.update(
            extract_portraits(hex_root / "AssetBundles" / "cardsets", ART_DIR, missing)
        )
    return found


def mse_card_block(card: dict[str, str], art_name: str) -> list[str]:
    rarity = card.get("rarity") or ""
    if rarity not in {"Common", "Uncommon", "Rare", "Legendary", "Epic", "Promo", "Land", "Champion"}:
        rarity = "Rare" if rarity else ""
    faction = card.get("faction") or ""
    if faction not in {"Ardent", "Underworld", "Neutral"}:
        faction = "" if (card.get("type") or "").lower() == "resource" else "Neutral"
    lines = [
        "card:",
        set_field("name", card.get("name") or ""),
        set_field("card_type", card.get("type") or ""),
        set_field("subtype", card.get("subtitle") or ""),
        set_field("cost", card.get("cost") or ""),
        set_field("threshold", card.get("threshold") or ""),
        set_field("text", insert_hex_symbols(card.get("text") or "")),
        set_field("flavor", card.get("flavour") or ""),
        set_field("attack", card.get("attack") or ""),
        set_field("defense", card.get("defense") or ""),
        set_field("rarity", rarity),
        set_field("faction", faction),
        set_field("pve", "yes" if card.get("pve") == "1" else "no"),
        set_field("unique", "yes" if card.get("unique") == "1" else "no"),
        set_field("immortal", "no"),
    ]
    if art_name:
        lines.append(f"\tart: {art_name}")
    return lines


def write_sample_set(dest: Path, hex_root: Path, layout: dict) -> list[dict[str, str]]:
    dest.mkdir(parents=True, exist_ok=True)
    for leftover in dest.glob("art-*.png"):
        leftover.unlink()
    cards = pick_sample_cards(hex_root)
    portraits = resolve_portraits(hex_root, cards)
    lines = [
        f"mse version: {MSE_VER}",
        f"game: {GAME}",
        f"stylesheet: {STYLE}",
        "set info:",
        "\ttitle: HEX layout check",
    ]
    for index, card in enumerate(cards, start=1):
        art_name = ""
        portrait = portraits.get((card.get("artId") or "").lower())
        if portrait and portrait.exists():
            art_name = f"art-{index:02d}.png"
            from PIL import Image

            width, height = portrait_target_size(card, layout)
            cover_crop(Image.open(portrait), width, height).save(dest / art_name)
        lines.extend(mse_card_block(card, art_name))
        print(f"  sample {card['name']}  {card.get('cost') or '—'}  {card.get('threshold') or '—'}", flush=True)
    (dest / "set").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_gallery(layout, cards, portraits, KIT / "preview-sample-ten.png")
    return cards


def write_gallery(
    layout: dict,
    cards: list[dict[str, str]],
    portraits: dict[str, Path],
    dest: Path,
) -> None:
    from PIL import Image

    faces = []
    for card in cards:
        portrait = portraits.get((card.get("artId") or "").lower())
        faces.append(render_face(layout, card, portrait))
    if not faces:
        return
    cols = 5
    rows = (len(faces) + cols - 1) // cols
    pad = 16
    sheet = Image.new("RGB", (cols * CARD_W + (cols + 1) * pad, rows * CARD_H + (rows + 1) * pad), (18, 14, 16))
    for i, face in enumerate(faces):
        x = pad + (i % cols) * (CARD_W + pad)
        y = pad + (i // cols) * (CARD_H + pad)
        sheet.paste(face.convert("RGB"), (x, y))
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest)
    print(f"  gallery {dest}", flush=True)


def render_face(layout: dict, card: dict[str, str], portrait: Path | None) -> "Image.Image":
    from PIL import Image, ImageDraw

    card_img = Image.new("RGBA", (CARD_W, CARD_H), (12, 8, 10, 255))
    draw = ImageDraw.Draw(card_img)
    family = "Ruby"
    th = (card.get("threshold") or "").lower()
    if "," in th or sum(name in th for name in ("blood", "ruby", "diamond", "sapphire", "wild")) > 1:
        family = "Multi"
    elif "blood" in th:
        family = "Blood"
    elif "diamond" in th:
        family = "Diamond"
    elif "sapphire" in th:
        family = "Sapphire"
    elif "wild" in th:
        family = "Wild"
    elif not th:
        family = "Shardless"
    is_resource = (card.get("type") or "").lower() == "resource"

    def paste(atlas: str, name: str, dest=None) -> None:
        box = dest or by_name(layout, atlas, name)
        layer = chrome_layer(atlas, name, box)
        if layer is None:
            return
        card_img.paste(layer, (int(box["left"]), int(box["top"])), layer)

    if portrait and portrait.exists():
        art = Image.open(portrait)
        if is_resource:
            fitted = cover_crop(art, CARD_W, CARD_H)
            card_img.paste(fitted, (0, 0), fitted)
        else:
            box = troop_art_box(layout)
            fitted = cover_crop(art, max(1, int(box["width"])), max(1, int(box["height"])))
            card_img.paste(fitted, (int(box["left"]), int(box["top"])), fitted)

    def rarity_icon_name(raw: str) -> str:
        key = raw or "Rare"
        return {"Land": "Common", "Promo": "Rare", "Champion": "Legendary"}.get(key, key)

    if not is_resource:
        for part in ("1", "2", "3", "4", "Text"):
            paste("Frames", f"{family}_{part}")
        paste("Elements", "TitleBar")
        paste("Elements", "TypeBar")
        paste("Elements", "ThresholdBar")
        paste("Elements", "GemBar")
        paste("Elements", "BottomBar")
        paste("Elements", "ManaCost")
        type_bar = by_name(layout, "Elements", "TypeBar")
        rar = by_name(layout, "Icons", "Rarity_Rare")
        paste("Icons", f"Rarity_{rarity_icon_name(card.get('rarity') or '')}", pin_icon(
            by_name(layout, "Elements", "GemBar"), type_bar, rar
        ))
        faction = card.get("faction") or "Neutral"
        if faction not in {"Ardent", "Underworld", "Neutral"}:
            faction = "Neutral"
        fac = by_name(layout, "Icons", f"Faction_{faction}")
        paste("Icons", f"Faction_{faction}", pin_icon(
            by_name(layout, "Elements", "ThresholdBar"), type_bar, fac
        ))
        if (card.get("type") or "").lower().startswith("troop"):
            atkdef = by_name(layout, "Elements", "AtkDefFrame")
            paste("Elements", "AtkDefFrame")
            def_box = {
                "left": CARD_W - atkdef["left"] - atkdef["width"],
                "top": atkdef["top"],
                "width": atkdef["width"],
                "height": atkdef["height"],
            }
            paste("Elements", "AtkDefFrame", def_box)
        pip0 = by_name(layout, "Icons", "Threshold_Ruby")
        for i, color in enumerate(expand_pips(card.get("threshold") or "")):
            paste("Icons", f"Threshold_{color}", {
                "left": pip0["left"],
                "top": pip0["top"] + i * (pip0["height"] + 2),
                "width": pip0["width"],
                "height": pip0["height"],
            })
    else:
        band = resource_title_band()
        if band is not None:
            card_img.paste(band, (0, 0), band)
        paste("Elements", "ResourceManaCost")
        rarity_key = rarity_icon_name(card.get("rarity") or "Rare")
        rar = by_name(layout, "Icons", "Rarity_Rare")
        mana = by_name(layout, "Elements", "ResourceManaCost")
        paste("Icons", f"Rarity_{rarity_key}", {
            "left": CARD_W - rar["width"] - 16,
            "top": mana["top"] + (mana["height"] - rar["height"]) / 2,
            "width": rar["width"],
            "height": rar["height"],
        })
        faction = card.get("faction") or ""
        if faction in {"Ardent", "Underworld", "Neutral"}:
            fac = by_name(layout, "Icons", f"Faction_{faction}")
            paste("Icons", f"Faction_{faction}", {
                "left": CARD_W - rar["width"] - fac["width"] - 22,
                "top": mana["top"] + (mana["height"] - fac["height"]) / 2,
                "width": fac["width"],
                "height": fac["height"],
            })

    name_font = face_font(23 if is_resource else 16)
    type_font = face_font(13)
    body_font = face_font(13)
    cost_font = face_font(30)
    stat_font = face_font(30)
    res_stat_font = face_font(20)
    flavor_font = face_font(10)

    def outlined(xy, text, font, fill=(255, 255, 255), **kwargs):
        x, y = xy
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font, **kwargs)
        draw.text(xy, text, fill=fill, font=font, **kwargs)

    def draw_rich(origin, text, font, max_width, line_h=16):
        left, y = origin
        x = left
        blue = (64, 176, 255)
        kw = keyword_regex()

        def newline():
            nonlocal x, y
            x = left
            y += line_h

        def draw_run(chunk: str, fill, underline=False):
            nonlocal x, y
            if not chunk:
                return
            for word in re.split(r"( )", chunk):
                if word == "":
                    continue
                width = draw.textlength(word, font=font)
                if x > left and x + width > left + max_width:
                    newline()
                    if word == " ":
                        continue
                    width = draw.textlength(word, font=font)
                outlined((x, y), word, font, fill=fill)
                if underline and word.strip():
                    box = draw.textbbox((x, y), word, font=font)
                    draw.line((box[0], box[3] - 1, box[2], box[3] - 1), fill=fill, width=2)
                x += width

        tagged = insert_hex_symbols(text or "")
        for part in re.split(r"(<sym>.*?</sym>|\n)", tagged):
            if not part:
                continue
            if part == "\n":
                newline()
                continue
            if part.startswith("<sym>"):
                code = re.sub(r"</?sym>", "", part).lower()
                cap = max(11, int(getattr(font, "size", 13) or 13))
                icon_h = cap + (2 if code in {"atk", "def"} else 1)
                icon = load_symbol_image(code, icon_h)
                if icon is None:
                    draw_run(code.upper(), (255, 255, 255))
                    continue
                if x > left and x + icon.width > left + max_width:
                    newline()
                line = draw.textbbox((left, y), "0", font=font)
                mid = (line[1] + line[3]) / 2
                card_img.paste(icon, (int(x), int(mid - icon.height / 2 - 2)), icon)
                x += icon.width + 2
                continue
            pos = 0
            for match in kw.finditer(part):
                draw_run(part[pos:match.start()], (255, 255, 255))
                draw_run(match.group(0), blue, underline=True)
                pos = match.end()
            draw_run(part[pos:], (255, 255, 255))

    type_line = (card.get("type") or "").upper()
    if card.get("subtitle") and not is_resource:
        type_line += " -- " + card["subtitle"]
    if card.get("unique") == "1":
        type_line += " Unique"
    if is_resource:
        outlined((CARD_W / 2, 36), card.get("name") or "", name_font, anchor="mm")
        mana = by_name(layout, "Elements", "ResourceManaCost")
        atk = card.get("attack") or ""
        df = card.get("defense") or ""
        stats = f"{atk if atk not in ('', '0') else '1'}/{df if df not in ('', '0') else '1'}"
        outlined((mana["left"] + mana["width"] / 2, mana["top"] + mana["height"] / 2 + 1), stats, res_stat_font, anchor="mm")
        type_x = mana["left"] + mana["width"] + 8
        outlined((type_x, mana["top"] + mana["height"] / 2), type_line, type_font, anchor="lm")
        draw_rich((type_x, mana["top"] + 40), card.get("text") or "", body_font, CARD_W - type_x - 16)
    else:
        outlined((90, 18), card.get("name") or "", name_font)
        if card.get("cost") not in ("", None):
            outlined((36.5, 40), str(card["cost"]), cost_font, anchor="mm")
        type_bar = by_name(layout, "Elements", "TypeBar")
        outlined((type_bar["left"] + 46, type_bar["top"] + 6), type_line, type_font)
        text_box = by_name(layout, "Frames", f"{family}_Text")
        draw_rich((text_box["left"] + 10, text_box["top"] + 12), card.get("text") or "", body_font, text_box["width"] - 20)
    if (card.get("type") or "").lower().startswith("troop"):
        atkdef = by_name(layout, "Elements", "AtkDefFrame")
        atk_s = stat_box(atkdef)
        def_s = stat_box({
            "left": CARD_W - atkdef["left"] - atkdef["width"],
            "top": atkdef["top"],
            "width": atkdef["width"],
            "height": atkdef["height"],
        })
        outlined((atk_s["left"] + atk_s["width"] / 2, atk_s["top"] + atk_s["height"] / 2), card.get("attack") or "0", stat_font, anchor="mm")
        outlined((def_s["left"] + def_s["width"] / 2, def_s["top"] + def_s["height"] / 2), card.get("defense") or "0", stat_font, anchor="mm")
        if card.get("flavour"):
            outlined((atkdef["left"] + atkdef["width"] + 8, atkdef["top"] + atkdef["height"] / 2), f'"{card["flavour"][:28]}"', flavor_font, fill=(220, 220, 220), anchor="lm")
    return card_img


def main() -> None:
    hex_root = resolve_hex()
    print(f"HEX client: {hex_root}", flush=True)
    print("  reading NGUI atlas padding…", flush=True)
    layout = load_layout(hex_root)
    ui_xml = hex_root / "Data" / "Localization" / "hex_uidata_en.xml"
    keywords = load_keywords(ui_xml)
    global KEYWORD_LABELS
    KEYWORD_LABELS = [name for name, _ in keyword_entries(keywords)]
    game_dir = PKG / f"{GAME}.mse-game"
    style_dir = PKG / f"{GAME}-{STYLE}.mse-style"
    font_dir = PKG / "hex-inline.mse-symbol-font"
    write_game(game_dir, keywords)
    write_style(style_dir, layout)
    write_symbol_font(font_dir)
    write_sample_set(PKG / "hex-layout-check.mse-set", hex_root, layout)
    write_preview(layout, KIT / "preview-example-troop.png")
    install_fonts()
    install_packages(game_dir, style_dir, font_dir)
    print(f"Wrote {PKG}", flush=True)


if __name__ == "__main__":
    main()
