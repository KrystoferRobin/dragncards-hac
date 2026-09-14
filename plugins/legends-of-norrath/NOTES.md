# Legends of Norrath — what we have, what we need

Kitchen-table plugin only. No rules engine. Proof of concept as of 13 Sep 2026.

When a newer client dump shows up, drop it in `plugins/LoN/<name>/` and leave existing folders alone. Rebuild with:

```
plugins/legends-of-norrath/.venv/bin/python plugins/scripts/import_legends_of_norrath.py
```

Importer prefers `plugins/LoN/LegendsOfNorrath-RoF2/` (real install layout) over the flat files next to it.

---

## What we have

**Client (best source).** May 2013 / LoN 1.745 / T4-2.1.0040, through **Debt of the Ratonga** (set 15).

- Flat dump + full RoF2 install (same `cards.rcc` / `storage.dat` / locale sizes). RoF2 is the useful layout: `data/archetypes/storage.dat`, `data/decks/*.eqd`, `locale/`.
- **4,467** unique cards after merge: Unit 1127, Ability 979, Card 659, Item 651, Tactic 473, Quest 349, Avatar 229.
- **48** official starters from `.eqd` (Fighter / Mage / Priest / Scout by set, plus a few Void extras).
- Faces are **composited**: parchment, cost/class icons, left-rail stats, white text box. RCC portraits when we have an art id (~1,193). Otherwise framed text, unless Fandom had a crop.
- TSV fields: name, subtitle, type, set/packName, archetype, faction, cost, attack, defense, health, damage, level, artId, frame, flavour, text.

**Printed numbers vs client encode.** The 2013 `k* / l* / m*` bytes are **not** the numbers on the real cards (Aery Outrider dumps as 12/12/11; printed is cost 2, 1/1/2). Where Fandom has the same name **and** type, we overwrite cost / ATK / DEF / damage / health / trait / set with the printed values. Terin avatar is 2 / 2 / +1 / 11, matching the labeled diagram.

---

## What we do not have

- **Drakkinshard (set 16)** and anything after May 2013. Torridus Smashkull is not in this client or on Fandom.
- **Most later-set printed stats.** Only ~480 Fandom pages had usable CardInformation; later cards still show the raw client encode or blanks.
- **Most portraits.** RCC has ~4,488 numeric JPEGs but only ~1,193 catalog rows have an art id. Fandom added ~300 more crops. The rest are text-only faces.
- **Honest set tags.** Anything not in an official `.eqd` or a `setNN_*` key / Fandom expansion stays **Norrath** (~3,300). Do not guess from art-id ranges.
- **Race / cost / collector / illustrator** on most post-Oathbound cards.
- **Playmat 9-slice frames as a finished card.** Those PNGs are overlays with transparent centers; the client drew the real card in Qt. `cardtext.css` in `resources.rcc` is empty.
- Map / questing mode. Out of scope.

---

## Scripts

| File | Job |
|---|---|
| `plugins/scripts/import_legends_of_norrath.py` | Build plugin + TSV + faces |
| `plugins/scripts/lon_catalog.py` | `storage.dat` + `.eqd` |
| `plugins/scripts/lon_compose.py` | Card images |
| `plugins/scripts/lon_fandom.py` | Fandom pages + portrait cache (`plugins/images/legends-of-norrath/_wiki/`) |

Output: `plugins/legends-of-norrath/` and `plugins/images/legends-of-norrath/`. Do not zip or rsync `plugins/LoN`.

---

## Other sources (checked 13 Sep 2026)

### Already used — [lon.fandom.com Category:Cards](https://lon.fandom.com/wiki/Category:Cards)

~489 pages, ~516 files, ~320 portrait-sized images. Almost all **Oathbound**. API works (`/api.php`). Skip their generated 350×489 “cards”; take the 230–280px art. No Smashkull, no Arasai Ravager, almost no later sets. [Main page](https://lon.fandom.com/wiki/Main_Page) is hub only.

### The site you remember — `lon.allakhazam.com/db/` (not the live EQ wiki)

The [live EQ wiki hub](https://everquest.allakhazam.com/wiki/Legends_of_Norrath) is a husk. `?action=history` / `?action=raw` are WAF-blocked (403). Card articles like `Allure_(LoN_Card)` exist as empty shells.

What you used for decks was a **separate card database**: `lon.allakhazam.com/db/card.html?loncard=1c107`. Wayback has **772 unique card pages** (2011-ish), through **Inquisitor** only:

- set 1 Oathbound ~335
- set 2 Forsworn ~220
- set 3 Inquisitor ~216

Each page has printed cost / ATK / DEF / HP, text, lore, illustrator, collector id, type, archetype, faction, rarity. Example (Aery Outrider 1C107): cost 2, 1/1/2, Mage, Oathbound — matches the Fandom printed numbers.

Full-card JPEGs were at `/images/cards/lg/1C107.jpg`. Those image URLs themselves do **not** appear to be in the archive (HTML says 252×367; fetch 404). Stats we can scrape; pretty pictures probably not from here.

Browse like kitsdb (path + query, not the homepage):

- [Aery Outrider](https://web.archive.org/web/20110319225208/http://lon.allakhazam.com/db/card.html?loncard=1c107)
- [Card list by set](https://web.archive.org/web/20080512232245/http://lon.allakhazam.com/db/cardlist.html?listby=card_set)
- CDX: `lon.allakhazam.com/db/card.html*`

Live wiki set-category *counts* (Oathbound 462, etc.) are leftover index, not filled pages.

### Worth a Wayback scrape later — [kitsdb LoN](https://web.archive.org/web/20120218164759/http://kitsdb.com/LoN/cardlist.php)

Community DB, 2007–2012 captures, lists through **Ethernauts** (set 5). Filter by set + rarity. Individual `card.php` URLs 404 on some timestamps; use the [cardlist snapshot](https://web.archive.org/web/20120218164759/http://kitsdb.com/LoN/cardlist.php) and CDX `kitsdb.com/LoN/*`. Printed stats / combos / comments — not a later-set art dump.

### Official site — [legendsofnorrath.com (2016-02-05)](https://web.archive.org/web/20160205173247/https://www.legendsofnorrath.com/)

Flash lobby, “upgrade your browser.” Nav confirms set names including **Drakkinshard** and **The Jarsath Destroyer** (loot/scenario, not a full set in our TSV). Loot-card marketing, not a card database. Keep for set list + “Play Free / Buy Cards” era screenshots only.

### Not useful yet

- Fandom generated card renders (poor composites).
- Official site loot pages as an art source (need a later client or a real gallery).

---

## Next dump — what to look for

A client **newer than May 2013** (post–Debt of the Ratonga). Ideal signs:

- `cards.rcc` bigger than **407,884,677** bytes, or new `1000xxxxx.jpg` above our current range.
- `storage.dat` / `data/archetypes/` with **Drakkinshard** / set 16 / `set16_`.
- Locale date after **Wed May 15 2013**.
- More than 52 `.eqd` files, or product ids `1690000x`.

Drop it as `plugins/LoN/<short-name>/`. If it has `data/archetypes/storage.dat`, the importer will prefer that tree automatically once we point `resolve_paths` at it (or we add a “newest wins” scan). Then merge: new objects, new art ids, new decks — keep Fandom printed-stat overlay for the early sets.

---

## Set list (official names)

1 Oathbound · 2 Forsworn · 3 Inquisitor · 4 Oathbreaker · 5 Ethernauts · 6 Against the Void · 7 Storm Break · 8 Travelers · 9 Vengeful Gods · 10 Doom of the Ancient Ones · 11 Dragonbrood · 12 Legacies · 13 Priestess of the Anarchs · 14 Fall of the Estarim · 15 Debt of the Ratonga · **16 Drakkinshard (missing)**
