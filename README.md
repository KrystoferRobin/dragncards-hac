# DragnCards — Toybox

A club fork of [seastan/dragncards](https://github.com/seastan/dragncards): multiplayer online card tables in Elixir, Phoenix, React, and TypeScript.

This tree is the **Toybox** instance. It is not a drop-in replacement for the public DragnCards site. The engine, plugin format, and image pipeline have all been extended here, and this repo ships a large set of first-pass game plugins for club tables.

---

## Compatibility warning

**These plugins will not work on the original DragnCards development branch** ([seastan/dragncards](https://github.com/seastan/dragncards), or any unmodified public site).

This fork adds game-definition keys, table features, and engine functions that stock DragnCards does not have. Loading a plugin from this repo over there will throw errors — missing functions, unknown definition fields, and an image-URL scheme the original client does not apply.

Do not copy `plugins/` into an upstream checkout and expect a table to open. Work on these games here, or port a plugin deliberately after stripping Toybox-only features.

---

## Plugin maturity

**Most plugins in this repo are raw initial databases.** They are first-pass conversions (Lackey, OCTGN, GEMP, catalog dumps, or a snapshot of a public table): card lists, art paths, and a skeleton layout. They are **not** finished products and are **not ready for public consumption**.

Expect missing automation, incomplete menus, placeholder layouts, unpolished card backs, and rules that still live in the players' heads. A handful (for example HEX keyword hover, or the official-style LotR LCG definition) are further along; treat everything else as a workbench.

---

## What this fork adds

On top of upstream DragnCards (including the 3D table):

- **Club auth.** Sign-up is invite-code only (`DRAGN_INVITE_CODE`). Accounts are alias + password; the backend synthesizes a local email. Log in with the alias, not an inbox.
- **Haven LFG.** New looking-for-game posts can hit a Haven/Discord-style webhook (`HAVEN_LFG_WEBHOOK_URL`) with a link back to the table (`DRAGNCARDS_PUBLIC_URL`).
- **Same-origin card art.** Plugins store *relative* image paths. The frontend prefixes `/cards/`. Host nginx maps that onto the fileshare (example `/dragncards/images/` on host). Plugin JSON/TSV does **not** publish the public image host, so GitHub is not a map of the fileshare. Details: [`plugins/README.md`](plugins/README.md).
- **Keyword reminders.** `keywordReminders` in the game definition: hovering a card shows glossary text under the giant preview for terms found in the printed text.
- **Lobby deck editor.** `/deck-editor/:pluginId` — catalog, plaintext import, and start-a-table from a built deck, outside the in-room deckbuilder.
- **Table UI.** Shared browse HUD (2D and 3D), lobby banner/logo slots, author credit on the plugin list, and table-region polish used by the club plugins.
- **Author-only plugin edits.** Create / update / delete is the plugin author (or an admin), not any logged-in user.
- **Conversion toolchain.** Python (and a few JS) importers under `plugins/scripts/` for Lackey, OCTGN, GEMP, live-table dumps, and game-specific catalogs (HEX, L5R, Legends of Norrath, Force of Will, and others), plus `collect_hosted_images.py` to download art, rename it, and rewrite paths.

Card art, reference dumps, and third-party conversion sources stay off GitHub (`/images/`, `/references/`, live-dump JSON). This repo is the engine plus plugin *definitions*.

---

## Plugins

Forty-odd games live under `plugins/`. Each folder is a DragnCards plugin: `jsons/` (game definition) and `tsvs/cards.tsv` (card database). Image files are collected next to the tree and copied onto the Toybox docroot; they are not in git.

### Club conversions

| Folder | Lobby name |
| --- | --- |
| `7th-sea-dragncards-plugin` | 7th Sea |
| `anachronism-dragncards-plugin` | Anachronism |
| `bttactics2-dragncards-plugin` | Battletech Tactics 2 |
| `call-of-cthulhu-lcg` | Call of Cthulhu LCG |
| `doomtown` | Doomtown |
| `doomtown-reloaded` | Doomtown Reloaded |
| `fe-cipher` | Fire Emblem Cipher |
| `fight-klub` | Fight Klub |
| `force-of-will` | Force of Will |
| `fpg-guardians` | Guardians (FPG) |
| `gundam-ms-war-ccg` | Gundam: The Movie MS War CCG |
| `hex-shards-of-fate` | HEX: Shards of Fate |
| `inwo` | INWO |
| `legend-of-mana-ccg` | Legend of Mana CCG |
| `legend-of-the-five-rings` | Legend of the Five Rings |
| `legends-of-norrath` | Legends of Norrath |
| `lotr-ccg-gemp` | Lord of the Rings TCG |
| `magic` | Magic The Gathering |
| `maple-story` | MapleStory TCG |
| `middle-earth-ccg-dragncards-plugin` | Middle Earth CCG |
| `mlp-ccg` | My Little Pony CCG |
| `mmtcg` | Mega Man TCG |
| `monty-python-ccg` | Monty Python and the Holy Grail CCG |
| `my-little-pony-dragncards-plugin` | My Little Pony (Kayou) |
| `mythos` | Mythos |
| `netrunner-1996` | Netrunner (1996) |
| `nightmare-before-christmas` | The Nightmare Before Christmas CCG |
| `redemption-dragncards-plugin` | Redemption |
| `rifts-ccg` | Rifts CCG |
| `robotech-ccg` | Robotech CCG |
| `sailor-moon-tcg` | Sailor Moon TCG |
| `shadowfist` | Shadowfist |
| `star-trek-ccg-1e` | Star Trek CCG 1E |
| `star-trek-tcg` | Star Trek TCG |
| `star-wars-ccg-decipher` | Star Wars CCG |
| `vs-system-2pcg` | VS System 2PCG |
| `vtes-dragncards-plugin` | Vampire: The Eternal Struggle |
| `wyvern-dragncards-plugin` | Wyvern |
| `x-files-ccg` | The X-Files CCG |

### Snapshots from a public DragnCards table

These `*-live-import` folders are dumps of a compiled `game_def` / `card_db` from an already-running public table, retargeted so Toybox hosts the art. They are snapshots, not original GitHub plugin source.

| Folder | Lobby name |
| --- | --- |
| `arkham-horror-living-card-game-live-import` | Arkham Horror Living Card Game |
| `earthborne-rangers-live-import` | Earthborne Rangers |
| `marvel-champions-the-card-game-live-import` | Marvel Champions: The Card Game |
| `star-wars-deckbuilding-game-live-import` | Star Wars Deckbuilding Game |
| `war-of-the-ring-card-game-live-import` | WotR Card Game |
| `wars-trading-card-game-live-import` | WARS Trading Card Game |

### Official-style definition in-tree

| Folder | Lobby name |
| --- | --- |
| `lotrlcg-plugin-main` | Lord of the Rings LCG (seastan's plugin, art retargeted to Toybox) |

How to convert, collect art, and upload a plugin to Toybox: [`plugins/README.md`](plugins/README.md). Per-game notes (when they exist) live in that plugin's own README or `SOURCE.txt`.

---

## Local development

**Requirements:** Docker and Docker Compose.

Tested on Ubuntu 22.04 / 24.04 Server. Copy `.env.example` to `.env` next to `compose.yml` if you need to override the invite code, public URL, or image root.

```
docker compose up -d backend
# First time: create a user in the DB. Alias "dev_user", password "password"
docker compose exec backend mix run /app/priv/create_user.exs

docker compose run --rm --service-ports frontend
```

Browse to `localhost:3000`. Sign-up needs `DRAGN_INVITE_CODE` (default in compose is `changeme`). Plugin docs for the *engine* still apply: [Plugin Documentation](https://github.com/seastan/dragncards/wiki/Plugin-Documentation) — then account for the Toybox-only fields and `/cards/` prefix described above.

Local webpack has no nginx `/cards/` map. Set `REACT_APP_CARDS_ORIGIN` to a host that already serves `/cards/` if you want art to load without local nginx (`frontend/src/setupProxy.js` proxies `/cards` there).

### Optional users

If you need extra users via SQL:

| username | password |
| --- | --- |
| player1@dragncards.com | password1 |
| player2@dragncards.com | password2 |
| player3@dragncards.com | password3 |
| player4@dragncards.com | password4 |

```
cat > users.sql << EOF
      INSERT INTO users (email , alias, inserted_at, updated_at, password_hash, email_confirmed_at, email_confirmation_token )
      VALUES ('player1@dragncards.com', 'player1', 'now', 'now', '$pbkdf2-sha512$100000$lBo3zNe49wIoWrAvht6Mbg==$SDfV/L5fNapiox7OgAJNB5rwrUm9RRNPCUBLHKXnNoVHcu574up2Tquxaa6shenktv7sCOtUu6rh4q0CmtOR+w==', 'now', 'c236e80a-2c34-44b9-92ab-312df26365f9' );
      INSERT INTO users (id , email , alias, inserted_at, updated_at, password_hash, email_confirmed_at, email_confirmation_token )
      VALUES ('7', 'player2@dragncards.com', 'player2', 'now', 'now', '$pbkdf2-sha512$100000$Hiwfmqbz6R0/R/q3whjVnA==$BvGkKDB/YfRnU4aQcV6INNJ8gv25Quw7SgzG64H7By5EgRdlTXIsOVHcLk7+Lf+bPqLkejAbl4F8Aanl1tASPQ==', 'now', '6a35ba55-fd0d-47e5-aff1-d53edd5af1ec' );
      INSERT INTO users (id , email , alias, inserted_at, updated_at, password_hash, email_confirmed_at, email_confirmation_token )
      VALUES ('8', 'player3@dragncards.com', 'player3', 'now', 'now', '$pbkdf2-sha512$100000$Z0jyoOb1KfzCuTGh/xVrZA==$YAlsffctWUbxujs3woZGZO6KGW++LquQAmc9MRalCXqBhaJYiOxJFjkkRjMAtbwLziVxCFD/LiRGlHutGvSpzw==', 'now', '45eacb70-01c4-4194-a3b3-fe927bef0d0b' );
      INSERT INTO users (id , email , alias, inserted_at, updated_at, password_hash, email_confirmed_at, email_confirmation_token )
      VALUES ('9', 'player4@dragncards.com', 'player4', 'now', 'now', '$pbkdf2-sha512$100000$1pFAgFabRwWro2FoLewoXw==$z0RCI+KwM68hdCxX+z+pN0mKELAd8aqvuPy+XUxNNx/ebpxrxlrxZ1fvLZ7NJQKyZnoF89NoR3fIggAYOJmEGQ==', 'now', '9c05358a-5b4f-477a-a201-8565a842ec2f' );
EOF
sql -d dragncards_dev -f ./users.sql -U postgres -h 127.0.0.1
```

This installs four players into the postgres container exposed locally. Adjust host/port if yours differs.

### Docker versions

Snap-packaged Docker/Compose has been a source of pain. These versions were known-good at the time of the original compose write-up:

```
Docker Engine 27.3.1
Docker Compose v2.29.7
```

---

## Credits

DragnCards itself is [seastan/dragncards](https://github.com/seastan/dragncards) (and earlier work on the same engine). The 3D table, plugin authorship checks, and much of the core engine in this tree come from that project.

This Toybox fork:

- **Architecture and direction** — Krystofer Robin
- **Implementation** — [Cursor](https://cursor.com) AI coding agents, working from that direction

Plugin card databases, layouts, and automation (such as they are) were converted or snapshotted from LackeyCCG, OCTGN, GEMP, public DragnCards tables, and community catalogs. Original plugin authors are credited in each plugin's `jsons/main.json` `author` field where known. Card art is not redistributed in this repository.
