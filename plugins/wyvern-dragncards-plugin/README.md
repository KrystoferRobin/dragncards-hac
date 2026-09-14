# Wyvern for DragnCards

Dumb (no rules enforcement) table plugin converted from the LackeyCCG Wyvern plugin.

After `collect_hosted_images.py`, card images resolve from:

`/cards/wyvern/{set}/{Game}-{Set}-{Cardname}.ext`

See [../README.md](../README.md) for the `/cards/` convention.

## Contents

- `jsons/` — game definition (one JSON object per file; DragnCards merges them)
- `tsvs/cards.tsv` — 457 cards from Kingdom, Phoenix, and Chameleon
- `scripts/convert_lackey.py` — regenerates the TSV and sample decks from Lackey
- `scripts/validate_plugin.py` — sanity-checks the merged definition against the TSV

## Upload to dragncards.com

1. Create an account and open **My Plugins**
2. Click **New Plugin**
3. **Load Game Definition** and select every file in `jsons/`
4. **Upload card database** and select `tsvs/cards.tsv`
5. Create the plugin (keep it private while testing)
6. Open a **2-player** room

## Play notes

- Each player has a Treasure Horde and a Dragon Lair (plus matching hands/discards) and a free battlefield
- Cards enter the battlefield facedown; press **F** to flip
- **D** draws from the Treasure Horde, **L** draws from the Dragon Lair
- Gold starts at 25 (**G** / **T** to gain/spend, or use the top-bar counter)
- **1** / **2** add green/red strength counters
- Terrain, treasure, and hidden actions can be attached onto battlefield cards
- Three Lackey sample decks are in the pre-built deck menu (tagged `sealed` for limited play)
- `jsons/limited.json` defines Kingdom / Phoenix / Chameleon boosters and a sample starter for sealed, draft, and sealed draft

Nothing enforces payment, legal attacks, or battle math. Drag cards, flip them, and count gold yourself.

## Regenerating from Lackey

```
python scripts/convert_lackey.py
python ../scripts/collect_hosted_images.py wyvern-dragncards-plugin
python scripts/validate_plugin.py
node scripts/validate_schema.mjs
```

The converter reads `C:\Users\chris\Documents\e-Sword\tests\LackeyCCG\plugins\Wyvern`. Run `python ../scripts/collect_hosted_images.py wyvern-dragncards-plugin` afterward so TSV paths stay relative and `imageUrlPrefix` supplies `/cards/`.
