# HEX MSE chrome kit

Sliced from the final **1.1.0.086** client (`Hex_Data/resources.assets`). Kitchen-table
lobby/back art is still homemade compose. **Card faces** are the MSE-chrome stamps
from `hex_mse_style.render_face` (Magic Set Editor is the layout editor, not the
production renderer — `mse --export-images` hangs).

## What this is

HEX does not ship one blank “card frame” PNG. The in-game face is a 3D shell plus
three NGUI atlases:

| Atlas | Use |
|---|---|
| `atlases/CardTemplate_Frames.png` | Color plates. Each shard (`Blood`, `Ruby`, `Sapphire`, `Wild`, `Diamond`, `Multi`, `Artifact`, `Class`, `Shardless`) has `_1` top, `_2` bottom, `_3` left, `_4` right, `_Text` rules box. |
| `atlases/CardTemplate_Elements.png` | Gold chrome: `TitleBar`, `TypeBar`, `ThresholdBar`, `ManaCost`, `AtkDefFrame`, sockets, PvE / Immortal badges. |
| `atlases/CardTemplate_Icons.png` | Threshold pips, rarity gems, faction marks, set icons. |

`slices/<atlas>/<Sprite>.png` is each of those pieces already cut. Rects and the
client’s leftover padding (`outer`) live in `slices.json` (NGUI origin is **top-left**,
same as PIL). That padding *is* the layout: each sprite was a full-card image, then
trimmed. Side rails (`*_3` / `*_4`) are packed **rotated** in the atlas; the kit
stores them upright so MSE can use a normal image layer.

MSE packages are generated from those positions plus `GoCardBuilder` / `CardTemplate`
conditions (not hand-placed boxes):

```
plugins/hex-shards-of-fate/.venv/bin/python plugins/scripts/hex_mse_style.py
```

Installs `hex.mse-game` + `hex-standard.mse-style` next to the kit and, if present,
into `~/Library/Application Support/magicseteditor/data/`. Open
`packages/hex-layout-check.mse-set` in Magic Set Editor 2.1.2 to check a resource
and a troop.

## Also here

- `extras/CardSleeve_Default.png` — official sleeve / card back (512²).
- `extras/hex_logo_white.png`
- `extras/Gem_*` — socket gem FX
- `extras/u_threshold_qty_*` — tiny threshold counters
- `fonts/Hex_Arial.ttf`, `Hex_Arial_Bold.ttf`, `Arial_Bold_Hex.ttf`, `FMBolyar_Regular.ttf`

Portraits stay in `plugins/images/hex-shards-of-fate/_art/a#######.png` (512²).
Card text / stats stay in the plugin TSV / gamedata parse. Tabletop JPEGs:

```
plugins/hex-shards-of-fate/.venv/bin/python plugins/scripts/import_hex_shards_of_fate.py --faces-only
```

That overwrites `plugins/images/hex-shards-of-fate/{set}/*.jpg` in place. DragnCards
keeps the same TSV `imageUrl`s; live table needs those files rsynced to toybox.

## Rebuild

```
plugins/hex-shards-of-fate/.venv/bin/python plugins/scripts/hex_mse.py
```

CJK fonts and the 2048 UI `T_Frames_Atlas` are not included (menus, not cards).
