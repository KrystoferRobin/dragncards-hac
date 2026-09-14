# My Little Pony for DragnCards

Dumb (no rules enforcement) 1v1 table plugin converted from the LackeyCCG **MyLittlePonyKayou** plugin (Kayou MLP TCG, BP01/BP02/SD01/PR).

`pluginName` is **My Little Pony**. Card images are hosted on toybox after `collect_hosted_images.py` rewrites the Dropbox URLs. Relative TSV / card-back paths plus `imageUrlPrefix` resolve to:

`https://toybox.hundredacre.club/cards/my-little-pony/{set}/{Game}-{Set}-{Cardname}.ext`

See [../README.md](../README.md) for the `/cards/` convention.

## Contents

- `jsons/` — game definition (one JSON object per file; DragnCards merges them)
- `tsvs/cards.tsv` — Character, Scene, Event, Item, Story, and Main Character cards
- `scripts/convert_lackey.py` — regenerates the TSV, groups, layouts, types, backs, browse, and starter decks
- `scripts/validate_plugin.py` / `validate_schema.mjs` — sanity-checks against the TSV and DragnCards schema

## Upload

1. Copy `images/my-little-pony/` onto the toybox image docroot (public URL prefix is `/cards/`)
2. My Plugins → Load Game Definition → every file in `jsons/`
3. Upload card database → `tsvs/cards.tsv`
4. Create/update the plugin, keep it private while testing
5. Open a **2-player** room

## Play notes

The table follows the Kayou playmat (cream = opponent, lavender = you):

- **Scene Zone** — large side square (your scenes on the left, theirs on the right)
- **Story Zone** — wide bar (theirs at the top, yours at the bottom)
- **Three adventure lanes** — open play boxes that face each other across the middle. Drop a character in a lane; attach items onto that character
- **Home square** — the unlabeled large box (MC, decks, plans, retire). Yours is on the right; theirs is on the left

Hands sit in the Scene Zone. Starters load MC onto the table, stories into the story deck (no shuffle), scenes into the scene deck.

- **D** draws, **S** shuffles deck, **N** adds a scene, **U** untaps, **P** adds a plan, **G** takes a plan, **R** rolls 1d6
- **T** taps, **K** untaps, **F** flips, **X** retires
- **1** green counter

Nothing enforces inspiration, contact, or story promotion. Drag cards, tap them, and count yourself.

## Regenerating from Lackey

```
python scripts/convert_lackey.py
python ../scripts/collect_hosted_images.py my-little-pony-dragncards-plugin
python scripts/validate_plugin.py
node scripts/validate_schema.mjs
```

The converter reads `C:\Users\chris\Documents\e-Sword\tests\LackeyCCG\plugins\MyLittlePonyKayou`.
