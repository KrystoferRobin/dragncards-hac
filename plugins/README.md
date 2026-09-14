# DragnCards plugins — image hosting

Toybox serves card art at **`/cards/`**. Host nginx aliases that path onto the `images/` tree (`compose.yml`, `nginx/toybox.hundredacre.club`). Do not put a `cards/` folder inside `images/`, and do not put `cards/` in TSV or card-back relative paths.

## Resolved URL

```
https://toybox.hundredacre.club/cards/{game}/{set}/{Game}-{Set}-{Cardname}.ext
```

Example: `https://toybox.hundredacre.club/cards/my-little-pony/_plugin/MyLittlePony-CardbackDefault.jpg`

| Piece | What it stores | Example |
| --- | --- | --- |
| `jsons/imageUrlPrefix.json` | Host + `/cards/` | `https://toybox.hundredacre.club/cards/` |
| `tsvs/cards.tsv` `imageUrl` | Relative path only | `my-little-pony/bp01/MyLittlePony-BP01-TwilightSparkleBP011.jpg` |
| `jsons/cardBacks.json` `imageUrl` | Relative path only | `my-little-pony/_plugin/MyLittlePony-CardbackDefault.jpg` |
| Token / background / lobby banner & logo | **Full** URL (DragnCards does not prefix these) | `https://toybox.hundredacre.club/cards/my-little-pony/_plugin/MyLittlePony-TokenGreen.png` |

Lobby listing art in `jsons/main.json` is always these two files in the game’s `_plugin` folder (drop them in when you have art):

- `bannerUrl` → `https://toybox.hundredacre.club/cards/{game}/_plugin/banner2.jpg` — card background, cover-scaled at ~50% opacity
- `logoUrl` → `https://toybox.hundredacre.club/cards/{game}/_plugin/logo2.jpg` — full-opacity icon in a square slot on the right

Converters stamp those URLs via `stamp_lobby_art()`. Do not PascalCase-rename `banner2.jpg` / `logo2.jpg`.

DragnCards prepends `imageUrlPrefix` to any card or card-back `imageUrl` that does not start with `http`. That is why the TSV stays game-relative: prefix + path is the public URL.

## Why not `cards/` in the TSV?

The files on disk are `images/{game}/{set}/...`. Nginx maps `/cards/` → that `images/` root. A TSV path of `cards/my-little-pony/...` plus this prefix would 404 as `/cards/cards/my-little-pony/...`.

## Pipeline

### Live table dump (official site)

If you are already sitting at a public table and want a club copy (so toybox hosts the art instead of hotlinking):

1. Wait until the table finishes loading (cards on screen).
2. Brave → DevTools (`Cmd+Option+I`) → Console. Paste `plugins/scripts/dump_live_plugin.js`. It downloads `{pluginName}-live-dump.json`.
3. Import and collect (S3 art is skipped unless `--allow-s3`):

   ```
   python plugins/scripts/import_live_plugin.py ~/Downloads/*-live-dump.json
   python plugins/scripts/collect_hosted_images.py --allow-s3 some-game-live-import
   ```

That writes split `jsons/` + `tsvs/cards.tsv` from the compiled `game_def`/`card_db` the table already had. It is a snapshot, not original GitHub source.

### Lackey / OCTGN convert

1. Convert Lackey/OCTGN (`scripts/convert_lackey.py` or `convert_octgn.py`) — writes source image URLs into the TSV and generated JSON.
2. Collect and rename art:

   ```
   python scripts/collect_hosted_images.py
   python scripts/collect_hosted_images.py --retarget
   python scripts/collect_hosted_images.py lotrlcg-plugin-main
   ```

   Downloads remote art into `images/{game}/{set}/Game-Set-Cardname`, rewrites TSV/card backs to relative paths, writes `imageUrlPrefix` to `https://toybox.hundredacre.club/cards/`, and gives tokens/backgrounds full `/cards/` URLs. `--retarget` only rewrites already-collected plugins (no download).
3. Copy `images/{game}/` onto the toybox image docroot (`/fileshare/services/dragncards/images/` on the host).
4. Validate, then Load Game Definition + Upload card database.

Shared helpers live in `scripts/image_names.py` (`TOYBOX_PREFIX`, `card_rel_path`, `plugin_art_rel`, `rewrite_toybox_url`). Converters and the collector must import that prefix — do not hardcode the host without `/cards/`.

## Upload to toybox

1. Copy `images/{game}/` onto the toybox image docroot
2. My Plugins → Load Game Definition → every file in `jsons/`
3. Upload card database → `tsvs/cards.tsv`
4. Optional: `author` in `jsons/main.json` is the lobby credit. If it is missing, the uploader's name is shown. Reload the game definition after changing it.
5. Keep the plugin private while testing
6. Open a room and confirm a card, the card back, and a token all load from `/cards/`
