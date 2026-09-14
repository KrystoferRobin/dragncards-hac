# Redemption for DragnCards

Dumb (no rules enforcement) table plugin converted from the LackeyCCG Redemption plugin.

After `collect_hosted_images.py`, card images resolve from:

`/cards/redemption/{set}/{Game}-{Set}-{Cardname}.ext`

See [../README.md](../README.md) for the `/cards/` convention.

## Table

- Per player: Deck, Hand, Discard, Reserve, Good/Evil Territory, Land of Bondage (beside the hand), Battle (enhancements / battle / artifacts), Land of Redemption, Banished, Tokens
- **Lost Souls drawn from deck** automatically go to Land of Bondage and you draw a replacement (including replacement Lost Souls). Dragging a Lost Soul from somewhere other than the deck does not trigger this.
- Reserve loads facedown (browse the pile to look)
- Green token = Exp, red token = Set Aside
- Meekify is 180° rotation (**M** / **U**)
- Buttons: Draw, Draw 8, Shuffle, d6, Coin
- Top-bar **Souls** counter (set it when you rescue)

Nothing enforces banding, ignore, initiative, or rescue math.

## Upload to dragncards.com

1. My Plugins → New Plugin
2. Load every file in `jsons/`
3. Upload `tsvs/cards.tsv` (about 5700 cards; the upload may take a moment)
4. Create a 2-player room

## Regenerating from Lackey

```
python scripts/convert_lackey.py
python ../scripts/collect_hosted_images.py redemption-dragncards-plugin
python scripts/validate_plugin.py
node scripts/validate_schema.mjs
```

The converter reads `C:\Users\chris\Documents\e-Sword\tests\LackeyCCG\plugins\Redemption`.
