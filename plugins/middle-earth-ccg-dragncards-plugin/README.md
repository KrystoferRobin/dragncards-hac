# Middle Earth CCG for DragnCards

Dumb (no rules enforcement) 1v1 table plugin converted from the LackeyCCG **meccg** plugin.

The lobby name is **Middle Earth CCG**, not `meccg`. After `collect_hosted_images.py`, card images resolve from:

`/cards/middle-earth-ccg/{set}/{Game}-{Set}-{Cardname}.ext`

See [../README.md](../README.md) for the `/cards/` convention.

## Contents

- `jsons/` — game definition (one JSON object per file; DragnCards merges them)
- `tsvs/cards.tsv` — The Wizards through The Balrog, plus Promo / PromoGerman
- `scripts/convert_lackey.py` — regenerates the TSV, groups, layouts, types, backs, browse, and Challenge Decks
- `scripts/validate_plugin.py` / `validate_schema.mjs` — sanity-checks against the TSV and DragnCards schema

## Upload to dragncards.com

1. Create an account and open **My Plugins**
2. Click **New Plugin**
3. **Load Game Definition** and select every file in `jsons/`
4. **Upload card database** and select `tsvs/cards.tsv`
5. Create the plugin (keep it private while testing)
6. Open a **2-player** room

## Play notes

- Each player: Deck, Hand, Discard, Out of Play, Sideboard, Location Deck, Company (characters + attachments), Site, Events, Tokens
- Shared: Set Aside
- Marshalling Points sit on the top bar (count them yourself)
- **D** draws, **S** shuffles the deck, **L** shuffles the location deck, **U** untaps all, **C** discards the top of the deck, **R** rolls 1d6
- **T** taps (90°), **K** untaps, **O** rotates 180°, **F** flips, **X** discards
- **1** green counter, **2** red counter
- Attach items/followers onto Company characters
- ICE Challenge Decks A–J are in the pre-built menu (Hero A–E, Minion F–J)

Nothing enforces hazard limits, influence, corruption, or marshalling points. Drag cards, tap them, and count tokens yourself.

## Regenerating from Lackey

```
python scripts/convert_lackey.py
python ../scripts/collect_hosted_images.py middle-earth-ccg-dragncards-plugin
python scripts/validate_plugin.py
node scripts/validate_schema.mjs
```

The converter reads `C:\Users\chris\Documents\e-Sword\tests\LackeyCCG\plugins\meccg`.
