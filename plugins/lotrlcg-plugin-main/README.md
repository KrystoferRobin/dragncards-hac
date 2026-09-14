# Lord of the Rings LCG for DragnCards

Official-style LotR LCG plugin (automation included). Card art is hosted on Toybox after `collect_hosted_images.py`. Relative TSV / card-back paths plus `imageUrlPrefix` resolve to:

`/cards/lord-of-the-rings-lcg/{set}/{Game}-{Set}-{Cardname}.ext`

See [../README.md](../README.md) for the `/cards/` convention.

Lobby listing art (add the files when you have them):

- `/cards/lord-of-the-rings-lcg/_plugin/banner.jpg`
- `/cards/lord-of-the-rings-lcg/_plugin/logo.jpg`

## Contents

- `jsons/` — game definition (one JSON object per file; DragnCards merges them)
- `tsvs/cardDb.tsv` — player, encounter, quest, and campaign cards

## Upload

1. Copy `images/lord-of-the-rings-lcg/` onto the Toybox image docroot (public URL prefix is `/cards/`)
2. My Plugins → Load Game Definition → every file in `jsons/`
3. Upload card database → `tsvs/cardDb.tsv`
4. Keep the plugin private while testing
5. Open a room and confirm a hero, an encounter card, a card back, and a token all load from `/cards/`

Translated card images were not mirrored. Every language prefix points at the English Toybox tree.

Three Harad cycle **rulesheet** scans were not on the English S3 bucket (Race Across Harad, Beneath the Sands, The Dungeons of Cirith Gurat). Those TSV rows already use the renamed path; drop the jpgs in later if you find them.

## Upstream TSV

For a fresh card database from upstream, download the [google sheet](https://docs.google.com/spreadsheets/d/1Uxfs4HYK9gB2vi0cXM_Rjkj8sW-f2viP9EMfGQirNp0/edit?gid=1666395093#gid=1666395093) as `.tsv`, then re-run `python scripts/collect_hosted_images.py lotrlcg-plugin-main`.
