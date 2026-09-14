# VTES for DragnCards

Dumb (no rules enforcement) table plugin converted from the KRCG LackeyCCG VTES plugin (2026-02-28).

After `collect_hosted_images.py`, card images resolve from:

`https://toybox.hundredacre.club/cards/vampire-the-eternal-struggle/{set}/{Game}-{Set}-{Cardname}.ext`

See [../README.md](../README.md) for the `/cards/` convention.

The table is **relative to you**. Prey sits to your left (`playerN+1`); predator sits to your right (`playerN+(n-1)`). In a 2-player game those are the same opponent, shown once.

DragnCards allows **2–8 seats**. 4–5 is the usual VTES table; 3 and 6–8 use the same you / prey / predator layout, with everyone else behind overlay buttons.

| Seats | Layout | Always on the table | Overlay buttons (your client only) |
| --- | --- | --- | --- |
| 2 | `default` | You and the other player | none |
| 3 | `table3` | You, prey, predator | none |
| 4 | `table4` | You, prey, predator | **Other** = across (`+2`) |
| 5 | `table5` | You, prey, predator | **GP** (`+2`), **GPr** (`+3`) |
| 6–8 | `table6`–`table8` | You, prey, predator | **GP**, middle seats as **+3** / **+4** / **+5**, **GPr** |

Example in a 5-player room: client 1 sees seats 2 (prey) and 5 (predator), with buttons for 3 and 4. Client 3 sees 4 and 2, with buttons for 5 and 1.

Host picks 2–8 from the player-count menu; that switches everyone’s layout. Overlay visibility is stored on *your* layout copy, so peeking at another seat does not pop an overlay on anyone else’s screen.

**Ousting:** seats wrap by player count, not by who is still in the game. If player 3 is ousted in a 5-player room, player 2’s prey is still seat 3 until you change the player count or reseat. Use **Close** / the same toggle to hide an overlay.

## Contents

- `jsons/` — game definition (one JSON object per file; DragnCards merges them)
- `tsvs/cards.tsv` — 4,370 cards (crypt, library, tokens, storyline extras)
- `scripts/convert_lackey.py` — regenerates the TSV, groups, layouts, player-count menu, types, backs, browse, and precon decks
- `scripts/validate_plugin.py` / `validate_schema.mjs` — sanity-checks against the TSV and DragnCards schema

## Upload to dragncards.com

1. Create an account and open **My Plugins**
2. Click **New Plugin**
3. **Load Game Definition** and select every file in `jsons/`
4. **Upload card database** and select `tsvs/cards.tsv`
5. Create the plugin (keep it private while testing)
6. Open a room and set player count to 2–8 (defaults to 2)

## Play notes

- Each player: Library, Crypt, Hand, Uncontrolled, Ready, Torpor, Masters, Ash Heap, Removed, Tokens
- Shared: The Edge (spawned at table start) and Set Aside
- Pool starts at **30**, VP at 0 (top-bar counters, or **G** / **P** / **V**)
- **D** draws library, **C** draws crypt into Uncontrolled, **S** shuffles library, **U** unlocks your cards
- **L** locks (90°), **K** unlocks, **F** flips, **X** burns to ash heap
- **1** blood, **2** life, **3** green, **4** orange
- Predator is the reddish strip on the left; prey is the green strip on the right. Overlay buttons peek at seats that are not adjacent to you
- Attach retainers/equipment onto Ready minions
- 53 Lackey precons (V5, Legacy, Storyline) are in the pre-built deck menu

Nothing enforces stealth/intercept, transfers, contest, or ousting. Drag cards, lock them, and count pool yourself.

## Regenerating from Lackey

```
python scripts/convert_lackey.py
python ../scripts/collect_hosted_images.py vtes-dragncards-plugin
python scripts/validate_plugin.py
node scripts/validate_schema.mjs
```

The converter reads `C:\Users\chris\Documents\e-Sword\tests\LackeyCCG\plugins\vtes`.
