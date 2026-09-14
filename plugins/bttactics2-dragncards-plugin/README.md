# BT Tactics 2 for DragnCards

Dumb (no rules enforcement) 1v1 table plugin converted from the LackeyCCG **bttactics2** plugin (v1.2.7).

After `collect_hosted_images.py`, card images resolve from:

`/cards/battletech-tactics-2/{set}/{Game}-{Set}-{Cardname}.ext`

See [../README.md](../README.md) for the `/cards/` convention.

## Contents

- `jsons/` — game definition (one JSON object per file; DragnCards merges them)
- `tsvs/cards.tsv` — original BattleTech CCG plus BT Tactics 2 (Units, Commands, Missions, Box Powers)
- `scripts/convert_lackey.py` — regenerates the TSV, groups, layouts, types, backs, browse, and precon decks
- `scripts/validate_plugin.py` / `validate_schema.mjs` — sanity-checks against the TSV and DragnCards schema

## Upload to dragncards.com

1. Create an account and open **My Plugins**
2. Click **New Plugin**
3. **Load Game Definition** and select every file in `jsons/`
4. **Upload card database** and select `tsvs/cards.tsv`
5. Create the plugin (keep it private while testing)
6. Open a **2-player** room

## Play notes

- Each player: Stockpile, Hand, Resources, Units, Commands, Scrapheap, Removed, Sideboard, Tokens
- Shared: Set Aside (LAMs, box powers, whatever you park off to the side)
- **D** draws, **S** shuffles, **U** untaps all, **C** scraps the top of the stockpile, **R** rolls 1d6
- **T** taps (90°), **K** untaps, **F** flips, **X** scraps
- **1** damage, **2** construction, **3** generic
- Attach pilots/enhancements onto Units
- Beginner and F20 60-card decks are in the pre-built menu (DSR two-stockpile decks are not; this table is standard 1v1)

Nothing enforces construction costs, initiative, blocking, or structure. Drag cards, tap them, and count counters yourself.

## Regenerating from Lackey

```
python scripts/convert_lackey.py
python ../scripts/collect_hosted_images.py bttactics2-dragncards-plugin
python scripts/validate_plugin.py
node scripts/validate_schema.mjs
```

The converter reads `C:\Users\chris\Documents\e-Sword\tests\LackeyCCG\plugins\bttactics2`.
