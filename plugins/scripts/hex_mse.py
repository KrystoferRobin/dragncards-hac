#!/usr/bin/env python3
"""Extract HEX card chrome + fonts for a future Magic Set Editor template.

  plugins/hex-shards-of-fate/.venv/bin/python plugins/scripts/hex_mse.py

Reads the 1.1.0.086 client in place. Writes plugins/hex-shards-of-fate/mse/.
Does not rebuild the kitchen-table plugin or copy portraits (those stay in _art/).
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from hex_catalog import resolve_hex  # noqa: E402

OUT = ROOT / "hex-shards-of-fate" / "mse"

ATLAS_GOS = {
    "Frames": "A_CardTemplate_Frames",
    "Elements": "A_CardTemplate_Elements",
    "Icons": "A_CardTemplate_Icons",
}
ATLAS_TEXTURES = {
    "Frames": "CardTemplate_Frames",
    "Elements": "CardTemplate_Elements",
    "Icons": "CardTemplate_Icons",
}
EXTRA_TEXTURES = (
    "CardSleeve_Default",
    "hex_logo_white",
    "Gem_N",
    "Gem_Effects",
    "Gem_Runes",
    "Gem_InnerFX",
    "u_threshold_qty_blood_da",
    "u_threshold_qty_diamond_da",
    "u_threshold_qty_ruby_da",
    "u_threshold_qty_sapphire_da",
    "u_threshold_qty_wild_da",
)
ENGLISH_FONTS = (
    "Hex_Arial",
    "Hex_Arial_Bold",
    "Arial_Bold_Hex",
    "FMBolyar_Regular",
)


def load_env(hex_root: Path):
    import UnityPy

    return UnityPy.load(str(hex_root / "Hex_Data" / "resources.assets"))


def object_name(obj) -> str:
    peek = getattr(obj, "peek_name", None)
    if callable(peek):
        try:
            return peek() or ""
        except Exception:
            pass
    try:
        return obj.read().m_Name or ""
    except Exception:
        return ""


def find_named(env, type_name: str, names: set[str]) -> dict:
    found = {}
    wanted = set(names)
    for obj in env.objects:
        if obj.type.name != type_name or not wanted:
            continue
        name = object_name(obj)
        if name in wanted:
            found[name] = obj
            wanted.discard(name)
    return found


def atlas_mb_path_id(env, go_name: str) -> int:
    for obj in env.objects:
        if obj.type.name != "GameObject":
            continue
        if object_name(obj) != go_name:
            continue
        go = obj.read()
        for pair in go.m_Component:
            pid = pair.component.path_id
            comp = next(x for x in env.objects if x.path_id == pid)
            if comp.type.name == "MonoBehaviour":
                return pid
    raise KeyError(go_name)


def parse_ngui_sprites(raw: bytes) -> list[dict]:
    sprites: list[dict] = []
    index = 0
    while index < len(raw) - 8:
        length = struct.unpack_from("<i", raw, index)[0]
        if 3 <= length <= 80:
            chunk = raw[index + 4 : index + 4 + length]
            if chunk and all(32 <= byte < 127 for byte in chunk) and chunk[:1].isalpha():
                name = chunk.decode("ascii")
                cursor = (index + 4 + length + 3) & ~3
                if cursor + 48 <= len(raw):
                    nums = struct.unpack_from("<12i", raw, cursor)
                    sprites.append(
                        {
                            "name": name,
                            "x": nums[0],
                            "y": nums[1],
                            "w": nums[2],
                            "h": nums[3],
                            "border": list(nums[4:8]),
                            "outer": list(nums[8:12]),
                        }
                    )
                    index = cursor + 48
                    continue
        index += 1
    return sprites


def _ngui_record(name: str, nums: tuple[int, ...]) -> dict | None:
    x, y, w, h = nums[:4]
    if not (1 <= w <= 2048 and 1 <= h <= 2048):
        return None
    outer = list(nums[8:12])
    if any(abs(v) > 2048 for v in outer):
        return None
    rotated = len(nums) > 12 and nums[12] == 1
    return {
        "name": name,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "border": list(nums[4:8]),
        "outer": outer,
        "rotated": rotated,
    }


def scan_ngui_from_assets(assets_path: Path, expected: dict[str, tuple[int, int]] | None = None) -> dict[str, dict]:
    """Read NGUI sprite padding out of resources.assets without UnityPy.

    Each UIAtlas sprite is a length-prefixed name plus twelve ints (xywh,
    border, leftover canvas padding). The leftover padding *is* the layout.
    When ``expected`` maps name → (w, h) from slices.json, that size wins.
    """
    data = assets_path.read_bytes()
    names = list(expected or [])
    if not names:
        raise ValueError("scan_ngui_from_assets needs expected sprite sizes")
    found: dict[str, dict] = {}
    for name in names:
        encoded = name.encode("ascii")
        prefix = struct.pack("<i", len(encoded)) + encoded
        start = 0
        matches: list[dict] = []
        while True:
            index = data.find(prefix, start)
            if index < 0:
                break
            cursor = (index + 4 + len(encoded) + 3) & ~3
            if cursor + 52 <= len(data):
                record = _ngui_record(name, struct.unpack_from("<13i", data, cursor))
                if record:
                    matches.append(record)
            elif cursor + 48 <= len(data):
                record = _ngui_record(name, struct.unpack_from("<12i", data, cursor))
                if record:
                    matches.append(record)
            start = index + 1
        if not matches:
            continue
        want = expected[name]
        sized = [m for m in matches if (m["w"], m["h"]) == want]
        pick = sized[0] if sized else matches[0]
        found[name] = pick
    return found


def atlas_crop(image, sprite: dict):
    """Cut one NGUI sprite out of an atlas PNG.

    Side rails are packed rotated (logical 27x432 stored as 432x27). Crop the
    packed rect and turn it upright so MSE can use a normal image layer.
    """
    from PIL import Image

    x, y, w, h = sprite["x"], sprite["y"], sprite["w"], sprite["h"]
    rotated = sprite.get("rotated") and h > w
    if rotated:
        crop = image.crop((x, y, x + h, y + w))
        return crop.transpose(Image.Transpose.ROTATE_90)
    return image.crop((x, y, x + w, y + h))


def reslice_from_atlases(kit: Path, sprites_by_atlas: dict[str, dict[str, dict]]) -> int:
    """Rewrite slices/*.png from the kit atlases using NGUI rects (and rotation)."""
    from PIL import Image

    count = 0
    names = {"Frames": "CardTemplate_Frames", "Elements": "CardTemplate_Elements", "Icons": "CardTemplate_Icons"}
    for key, sprites in sprites_by_atlas.items():
        atlas_path = kit / "atlases" / f"{names[key]}.png"
        if not atlas_path.exists():
            continue
        image = Image.open(atlas_path)
        folder = kit / "slices" / key.lower()
        folder.mkdir(parents=True, exist_ok=True)
        for sprite in sprites.values():
            crop = atlas_crop(image, sprite)
            dest = folder / f"{sprite['name']}.png"
            crop.convert("RGBA").save(dest)
            count += 1
    return count


def save_png(image, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGBA").save(dest)


def font_bytes(data) -> bytes:
    raw = getattr(data, "m_FontData", None) or getattr(data, "m_Data", None)
    if raw is None:
        return b""
    return bytes(raw)


def extract(hex_root: Path, dest: Path = OUT) -> dict:
    print("  loading resources.assets…", flush=True)
    env = load_env(hex_root)
    tex_names = set(ATLAS_TEXTURES.values()) | set(EXTRA_TEXTURES)
    textures = find_named(env, "Texture2D", tex_names)
    fonts = find_named(env, "Font", set(ENGLISH_FONTS))
    atlas_dir = dest / "atlases"
    slice_root = dest / "slices"
    manifest: dict = {"client": str(hex_root), "atlases": {}, "extras": [], "fonts": []}

    for key, tex_name in ATLAS_TEXTURES.items():
        obj = textures[tex_name]
        data = obj.read()
        image = data.image
        atlas_path = atlas_dir / f"{tex_name}.png"
        save_png(image, atlas_path)
        raw = next(o for o in env.objects if o.path_id == atlas_mb_path_id(env, ATLAS_GOS[key])).get_raw_data()
        sprites = parse_ngui_sprites(raw)
        folder = slice_root / key.lower()
        for sprite in sprites:
            box = (
                sprite["x"],
                sprite["y"],
                sprite["x"] + sprite["w"],
                sprite["y"] + sprite["h"],
            )
            crop = image.crop(box)
            save_png(crop, folder / f"{sprite['name']}.png")
            sprite["file"] = f"slices/{key.lower()}/{sprite['name']}.png"
        manifest["atlases"][key] = {
            "texture": f"atlases/{tex_name}.png",
            "width": data.m_Width,
            "height": data.m_Height,
            "sprites": sprites,
        }
        print(f"  {tex_name}: {len(sprites)} slices", flush=True)

    for name in EXTRA_TEXTURES:
        obj = textures.get(name)
        if not obj:
            print(f"  missing extra {name}")
            continue
        data = obj.read()
        rel = f"extras/{name}.png"
        save_png(data.image, dest / rel)
        manifest["extras"].append({"name": name, "file": rel, "width": data.m_Width, "height": data.m_Height})

    for name in ENGLISH_FONTS:
        obj = fonts.get(name)
        if not obj:
            print(f"  missing font {name}")
            continue
        payload = font_bytes(obj.read())
        if payload[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"wOFF"):
            print(f"  skip font {name}: not a TTF ({payload[:8]!r})")
            continue
        rel = f"fonts/{name}.ttf"
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        (dest / rel).write_bytes(payload)
        manifest["fonts"].append({"name": name, "file": rel, "bytes": len(payload)})

    (dest / "slices.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


README = """# HEX MSE chrome kit

Sliced from the final **1.1.0.086** client (`Hex_Data/resources.assets`). Kitchen-table
plugin still uses the homemade `hex_compose.py` faces until we wire an MSE export.

## What this is

HEX does not ship one blank “card frame” PNG. The in-game face is a 3D shell plus
three NGUI atlases:

| Atlas | Use |
|---|---|
| `atlases/CardTemplate_Frames.png` | Color plates. Each shard (`Blood`, `Ruby`, `Sapphire`, `Wild`, `Diamond`, `Multi`, `Artifact`, `Class`, `Shardless`) has `_1` top, `_2` bottom, `_3` left, `_4` right, `_Text` rules box. |
| `atlases/CardTemplate_Elements.png` | Gold chrome: `TitleBar`, `TypeBar`, `ThresholdBar`, `ManaCost`, `AtkDefFrame`, sockets, PvE / Immortal badges. |
| `atlases/CardTemplate_Icons.png` | Threshold pips, rarity gems, faction marks, set icons. |

`slices/<atlas>/<Sprite>.png` is each of those pieces already cut. Rects and the
client’s outer numbers live in `slices.json` (NGUI origin is **top-left**, same as PIL).

## Also here

- `extras/CardSleeve_Default.png` — official sleeve / card back (512²).
- `extras/hex_logo_white.png`
- `extras/Gem_*` — socket gem FX
- `extras/u_threshold_qty_*` — tiny threshold counters
- `fonts/Hex_Arial.ttf`, `Hex_Arial_Bold.ttf`, `Arial_Bold_Hex.ttf`, `FMBolyar_Regular.ttf`

Portraits stay in `plugins/images/hex-shards-of-fate/_art/a#######.png` (512²).
Card text / stats stay in the plugin TSV / gamedata parse.

## Rebuild

```
plugins/hex-shards-of-fate/.venv/bin/python plugins/scripts/hex_mse.py
```

CJK fonts and the 2048 UI `T_Frames_Atlas` are not included (menus, not cards).
"""


def main() -> None:
    hex_root = resolve_hex()
    print(f"HEX client: {hex_root}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "README.md").write_text(README, encoding="utf-8")
    manifest = extract(hex_root, OUT)
    print(
        f"Wrote {OUT}  atlases={len(manifest['atlases'])}  "
        f"extras={len(manifest['extras'])}  fonts={len(manifest['fonts'])}"
    )


if __name__ == "__main__":
    main()
