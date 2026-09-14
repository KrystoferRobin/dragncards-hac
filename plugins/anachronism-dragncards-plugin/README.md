# Anachronism for DragnCards

Dumb (no rules enforcement) table plugin converted from the LackeyCCG Anachronism plugin.

After `collect_hosted_images.py`, card images resolve from:

`https://toybox.hundredacre.club/cards/anachronism/{set}/{Game}-{Set}-{Cardname}.ext`

See [../README.md](../README.md) for the `/cards/` convention.

## What's different about this game

- Each army is **5 cards**: 1 warrior + 4 support cards
- Shared **4x4 arena** (not a free play area). Drag the warrior onto a cell
- Support cards load **facedown** in your pool; flip them as you reveal each round
- Facing is rotation: **N / E / S / W** (North = toward the top of the table)
- Dice are plugin buttons, not a built-in roller: **2d6 Atk**, **2d6 Def**, **1d6**, **3d6**
- Life is a top-bar counter (set it from your warrior's printed Life)

P1 starts on the **bottom** row facing North. P2 starts on the **top** row facing South. The board does not flip for player 2.

## Upload to dragncards.com

1. My Plugins → New Plugin
2. Load every file in `jsons/`
3. Upload `tsvs/cards.tsv`
4. Create the plugin (keep it private while testing)
5. Open a 2-player room

## Play notes

- Load a sample army (Achilles, Musashi, or Caesar) or build one in the deckbuilder
- Drag your warrior from the Warrior pile onto your start row
- **A** attack 2d6, **D** defense 2d6 (doubles are logged as crits)
- **F** flip, **N/E/S/W** face, **G/T** life +/-
- Green token (**1**) for extra counters

Nothing enforces attack grids, legal facing, initiative, or damage math.

## Regenerating from Lackey

```
python scripts/convert_lackey.py
python ../scripts/collect_hosted_images.py anachronism-dragncards-plugin
python scripts/validate_plugin.py
node scripts/validate_schema.mjs
```

The converter reads `C:\Users\chris\Documents\e-Sword\tests\LackeyCCG\plugins\anachronism`.
