# HEX: Shards of Fate — kitchen-table plugin

Final client **1.1.0.086**. Shortcuts only. No rules engine.

Rebuild:

```
plugins/hex-shards-of-fate/.venv/bin/python plugins/scripts/import_hex_shards_of_fate.py
```

The importer reads `/Volumes/Expand/HEX SHARDS OF FATE` in place. Do not copy that tree into `plugins/`.

`Hex TCG Browser data dump - Cards.csv` is a last community catalog (4,525 GUIDs). It was never the build source. Compare only:

```
plugins/hex-shards-of-fate/.venv/bin/python plugins/scripts/hex_browser.py
```

MSE chrome (frames, gold bits, pips, fonts, official sleeve) lives in `mse/`. Rebuild the editor kit:

```
plugins/hex-shards-of-fate/.venv/bin/python plugins/scripts/hex_mse_style.py
```

Stamp every tabletop face from that chrome (same paths DragnCards already uses):

```
plugins/hex-shards-of-fate/.venv/bin/python plugins/scripts/import_hex_shards_of_fate.py --faces-only
```

Smoke a handful first with `--faces-only --limit 20`. Live table still needs the
JPEGs rsynced to Toybox; this repo does not rsync on its own.

Hovering a card on the table shows the big preview plus a small glossary pane
under it for keywords found in that card's text (`jsons/keywordReminders.json`).
Needs the Toybox frontend that ships GiantCard reminders, and a HEX game-definition reload.

See `mse/README.md`. Portraits stay in `_art/`. Lobby / card back still use homemade compose.

See `RULES.md` for the turn outline and the client keyword glossary.

See `INVESTIGATION.md` for campaign data, why the Unity client will not go offline, and whether HEX’s AI (it doesn’t ship) could drive DragnCards PvE.
