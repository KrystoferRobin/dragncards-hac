# 7th Sea for DragnCards

Dumb (no rules enforcement) 1v1 table plugin converted from the OCTGN **7th Sea** game definition.

The lobby name is **7th Sea**. Card images are served from the Toybox `/cards/` prefix:

`/cards/7th-sea/{set}/{Game}-{Set}-{Cardname}.ext`

See [../README.md](../README.md) for the `/cards/` convention.

## Contents

- `jsons/` — game definition
- `tsvs/cards.tsv` — 1,677 cards (OCTGN GUIDs kept as `databaseId`)
- `../images/7th-sea/` — renamed/reorganized art ready to copy onto Toybox
- `scripts/convert_octgn.py` — regenerates TSV, groups, layouts, and the image tree

## Upload images to Toybox

Copy the whole `images/` tree onto the Apache/httpd docroot used by DragnCards (compose default is `./images` → `/usr/local/apache2/htdocs`):

```
images/7th-sea/iron-shadow/7thSea-IronShadow-AndareDeCastillo.jpg
images/7th-sea/_plugin/7thSea-cardback.jpg
```

becomes

```
/cards/7th-sea/iron-shadow/7thSea-IronShadow-AndareDeCastillo.jpg
```

OCTGN originals are left in place. A GUID→new-path map is at `images/7th-sea/_manifest.tsv`.

Two OCTGN cards had no art (`The General's Tactics`, `The Prized Emblem of the Explorer Society`) and fall back to the card back.

## Upload the plugin

1. **Load Game Definition** — every file in `jsons/`
2. **Upload card database** — `tsvs/cards.tsv`
3. Open a **2-player** room

## Play notes

- Shared seas across the middle (auto-placed on new game): Trade Sea, Frothing Sea, La Boca, Forbidden Sea, The Mirror
- Each player: Deck, Hand, Discard, Sunk, Crew (attachments), Ship, Captain, Adventures
- **D** draws, **S** shuffles, **U** untacks all, **C** discards the top of the deck, **R** rolls 1d6
- **T** tacks (90°), **K** untacks, **F** flips, **X** discards, **G** sinks
- **1** hits, **2** generic
- Attach crew gear onto Crew; drag a ship onto a sea to show where you are

Nothing enforces crew max, influence costs, boardings, or hits.

## Regenerating

```
python scripts/convert_octgn.py
python ../scripts/collect_hosted_images.py --retarget 7th-sea-dragncards-plugin
python scripts/validate_plugin.py
node scripts/validate_schema.mjs
```
