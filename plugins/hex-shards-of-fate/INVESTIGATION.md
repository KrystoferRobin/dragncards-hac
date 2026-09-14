# HEX client investigations (13 Sep 2026)

Notes from poking the final **1.1.0.086** install at `/Volumes/Expand/HEX SHARDS OF FATE`. Kitchen-table plugin is separate (`NOTES.md`, `RULES.md`). This file is “what else is in the box” so we do not re-learn it.

Do not copy the HEX install into `plugins/`. Do not ship a login bypass or a fake game server.

---

## Client shape

Unity 5.6.5p2 / Mono. `Hex.exe` + `Hex_Data` + `AssetBundles` + `Data/`.

| Path | What it is |
|---|---|
| `Data/gamedata` | gzip, **104 MB** uncompressed. Reckoning JSON: cards, abilities, decks, quests, conversations, scenes, champs, talents, mercs |
| `Data/Localization/hex_carddata_en.xlf` | Card names / rules text |
| `Data/Localization/hex_uidata_en.xml` | UI + **keyword glossary** (we used this) |
| `Data/localization.db` | Not SQLite. `$$---$$` GUID catalog |
| `AssetBundles/cardsets/*.harc` | Custom `HARC` dirs of UnityFS 5.6 bundles (`a0000123.ab` = 512×512 painting) |
| `AssetBundles/pve/` | AZ1 map/nodescapes (~313 MB), AZ2 (25 MB), frost arena, race strongholds |
| `AssetBundles/gameboards/*.ab` | 19 combat boards |
| `Hex_Data/Managed/Assembly-CSharp.dll` | UI, Steam, chat, “Play AI” buttons |
| `Hex_Data/Managed/Assembly-CSharp-firstpass.dll` | **Network + session.** `Game.Shared.Network.HConnect`, `AuthoritativeSession` |
| `config.ini` | `CZEAuthUrl=https://live-auth.hextcg.com/auth/hexlogin`, `GameServerIP=205.220.229.20\|…` |

HARC format: `HARC\r\n` then `offset,size,./name.ab` lines, blank line, then concatenated UnityFS blobs. Offsets are relative to the end of that directory. Skip `*_dr.ab` and `atlas.ab` unless you need extras.

Art path on a card: `_ArtSource\…\a0008249.PNG` → bundle stem `a0008249`. XOR is not involved (that was LoN). UnityPy extracts Texture2D.

---

## Why the dead client will not “just go offline”

Combat is **server-authoritative**. Firstpass strings: `AuthoritativeSession` / `AuthoritativeSessionBase`, `IsAuthoritative`, `IsServer`, `abilityDataFromServer`, `needsTargetingInfoFromServer`, `RelyOnServerForData`, `m_WaitingForServerData`. Random targets: server picks. PvE still has `needToValidatePVE`. Login gate: `ShowNeedValidNetLogin`.

Services the client expects (not in this folder):

- Auth (`CZEAuth`, `AUTH_HEX`)
- Profile / collection / gold / escrow / billing
- Campaign progress
- **Match / game session host** (the thing that sets `IsServer`)
- **AI server** (`PingAIServer`, `AIServerId`)
- Matchmaking, mail, tournaments, chat
- Reconnect novel (`TryReconnectionToDisconnectedGame`)

RabbitMQ DLL is **logging** (`m_bEnableRabbitMQLogging`), not matches. `m_IsOffline` / `AuthBypass` look like Steam-persona / internal hooks, not a shipped single-player flag.

**Odds (do not start this):** fake-login into some PvE UI ~25%. Offline encounters that actually resolve ~10–15% as a hack, ~40% as a 1–2 year “reimplement AuthoritativeSession from the JSON.” A public PvP private server is the same combat host plus accounts — small-MMO energy, years, team. Little Orbit / CZE server code is not here.

The rules **data** is local. The rules **host** is not.

---

## Campaign data (not cards)

All in `gamedata` unless noted.

| Section | Count | Use |
|---|---|---|
| `QuestTemplate` | 32 | AZ1 / AZ2 quests, objectives, dungeon + conversation links |
| `ConversationTemplate` | 2,325 | 5,870 questions, 7,252 answers, **~1.06M characters** of English dialogue |
| Dialogue gates | 934 race, plus class/faction/gender/gold/quest-state | Branching is real |
| `ServerScriptEvent` on chats | 219 | “Start fight / set quest / grant buff” — hooks, not implementations |
| `DungeonTemplate` | 23 | Node graphs + flavor |
| Dungeon nodes | Howling Plains ~85, Alachian Sea ~82, plus keeps/kraken/graveyard/etc. | Title, click text, on-move text, terrain, encounter totem |
| `EncounterScene` | 336 | Named fights/dialog nodes (`SEA WITCH UNFETTERED`, blockades, …) |
| `EncounterDeck` | 301 | Points at `DeckTemplate` + opening hand + card order |
| Encounter mods | +cards, +champ health, +resources | Pre-fight buffs from story |
| `ChampionTalentData` | 241 | PvE talent grids |
| `MercenaryTemplate` | 83 unique | Hireables |
| `XpTable` | 1 | Level curve |
| `RewardTemplate` | handful | e.g. Kraken boss 600 gold / 5 plat / 500 XP |

Quest names worth remembering: Crayburn Castle, Ambling Mesa, Usurper, Army of Myth, Blood Beneath, Devonshire Keep, Tranquil Dream, Fort Romor, Smoldering Dead, Brutecrown Bluff, Ruins of Kukatan, Great Machine Graveyard, The Kraken. Ardent vs Underworld forks (`AZ01 - AR -`, `AZ01 - UW -`).

**Node art:** `m_NodeScapeArtNumber` (`a0006155`) + `m_NodeScapeSubBundlePath` (`AdventureZone01`). Same extract path as card portraits.

**Node positions are not in JSON.** `m_MapNodeId` (`NodeA`, `Node001`) keys into Unity `pve/adventurezone01/map.ab`. No `m_X` / `m_Position`. A new client either reads transforms from that scene or redraws a schematic graph.

Race-home “dungeons” (Jinguru, Hatchery, Necropolis…) are almost stubs in JSON; the 3D scene is `p_elf_aryndelpalace.ab` etc. Story for those is in conversations + `AZ0_*` encounter scenes.

**Enough to populate a bespoke PvE client:** yes — quest graph, full dialogue, encounter lists, AI decks, location paintings, boards, talents/mercs. **Not enough to press Play in empty Unity:** presentation, saves, and those 219 script events are new work.

---

## HEX AI — what we have vs what we do not

### Have

- Hundreds of **AI / encounter / arena / PvE decks** (`DeckTemplate` + `EncounterDeck`). We already import the constructed/starter slice; the rest are still in gamedata (`AI_Blood`, `Arena_*`, `AZ1 - …`, `zPvE*`).
- Encounter **when** to fight and **what list** to load, plus pre-fight mods.
- Client types/hooks: `AICardEvaluator`, `AICustomAbilityEvaluator`, `EAIEvaluationRole`, `TakeAIActions`, `m_AIHints` on every card and ability.
- A debug cheat string: make the AI use one of *your* decks.

### Do not have

- A filled-in brain. On this dump `m_AIHints` is `""` on cards. `m_AICustomAbilityEvaluator` is `[]` on abilities. No weights, no combo scripts, no priority tables in gamedata.
- The **AI server**. Firstpass talks to `PingAIServer` / `AIServerId` the same way it talks to matchmaking. Decisions were made next to `AuthoritativeSession`, not in a local Lua file.
- `TakeAIActions` sits beside session methods (`IsNextActionValidThisPhase`, `PlayerActionWasPerformed`). That is “session please act for the AI seat,” not a portable heuristic.

**HEX’s AI understanding of cards/combos is not in this install.** We have its *decklists* and *encounter scripts*. The play policy lived on a machine we do not have. Anything we put in DragnCards would be a **new** opponent (scripted, heuristic, or LLM), taught from card text + those lists — not a port of Cryptozoic’s bot.

---

## DragnCards: automate HEX PvE?

Possible in layers. Stark departure from “shortcuts only,” but the campaign *data* is the easy layer.

### 1. Adventure shell (plugin data, little core)

Node picker → flavor / conversation → “fight this encounter.” Spawn the encounter deck + champ into the opponent seat. Player plays kitchen-table HEX as we do now.

**Have everything for this** except a UI and a save file. Could stay mostly in the plugin (JSON of quests/nodes/chats we dump from gamedata). Combat stays human-vs-human or human-vs-“pass and play the listed cards by hand.”

### 2. Opponent that plays the encounter (needs core + plugin AI)

Need, in order:

1. A **HEX rules engine** (threshold, chain, targeting, crush overflow, deploy/deathcry, etc.). Not in DragnCards today. Plugin would have to be allowed to own game logic, or we grow a generic “plugin rules + plugin AI” hook.
2. An **AI** that can choose legal actions. We do **not** have HEX’s. Options: (a) dumb heuristic — play cheapest legal troop, block if lethal, smash face; (b) scripted per encounter (“always play X if in hand”); (c) search/eval using the AbilityTemplate dump as a fact base. (a) is a weekend after a rules engine exists. (c) is a project. None of them *are* the old bot.
3. Modular hook: plugin provides `chooseAction(state) -> action` and maybe `legalActions(state)`. That is new DragnCards surface. Worth doing generically (other CCGs would use it) if we ever grow engines.

Without (1), an AI is just clicking random piles. The engine is the real cost; the missing HEX brain is a disappointment, not a blocker, if we accept “good enough PvE AI.”

### 3. Full auto campaign (1 + 2 + script events)

Reimplement ~219 conversation server events as plugin callbacks, persist quest state, apply encounter mods. Data is local. Work is product work.

### Honest stack

| Piece | In the dump? | In DragnCards today? |
|---|---|---|
| Cards, art, keywords | Yes | Plugin done |
| Quest / dialogue / nodes | Yes | Not used |
| Encounter decks | Yes | Not imported (we skipped AI/AZ/Arena) |
| Location / board art | Yes | Not extracted |
| HEX AI policy | **No** | — |
| HEX rules host | **No** (data yes) | No |
| Plugin-scripted opponent | — | No hook |

**Verdict:** a **guided PvE book** that dumps you onto the HEX table vs a listed deck is realistic and modular. A **self-playing campaign that feels like HEX’s AI** needs a new rules engine and a new bot. The dump helps the engine (AbilityTemplate is a complete effect catalog) and does not donate the bot.

If we ever cut that loose: dump quests/conversations/encounters to `plugins/hex-shards-of-fate/pve/`, keep AI as a plugin module, keep DragnCards core to “run plugin engine + plugin actor.” Do not special-case HEX in the C# server beyond generic hooks.

---

## Hex TCG Browser CSV (not the client)

`plugins/hex-shards-of-fate/Hex TCG Browser data dump - Cards.csv` — 4,525 unique GUIDs, last community browser catalog. It was sitting in the plugin folder unused (13 Sep 2026). **Do not rebuild the plugin from it.** The client still wins: 7,699 Card+Champion templates, plus alts / equipment / PvE effects the browser never listed.

Useful as a check:

- GUID overlap is clean (names match on 4,379 shared cards).
- Browser writes **X costs** as `1X` / `X`; the client stores the numeric prefix only (`1` / `0`) — 27 constructed cards.
- Ban notes: PVE / Standard / Immortal / Rock on a handful of names.
- 83 **mercenaries** (PvE hireables). Client has `MercenaryTemplate` (166) but we do not import them as table cards.
- 8 talent pets exist in gamedata as `#PET_RAT#` etc.; we skip `#` names; the dump has the real labels.
- Promo / ladder / quest `source` strings, AA/reprint links, collectable flags.
- Text is player-facing HTML (`<b>Flight</b>`, card names). Client text uses `#SELF#`, `ESC:2`, and is often the fuller template. A few lines disagree in substance (Rose Lion, Ninja Training, Oath of Valor) — if a kitchen-table argument comes up, read both.

Compare: `plugins/scripts/hex_browser.py` or `import_hex_shards_of_fate.py --compare-browser`.

---

## Plugin / importer map

| File | Job |
|---|---|
| `plugins/scripts/hex_catalog.py` | gamedata parse |
| `plugins/scripts/hex_browser.py` | Hex TCG Browser CSV check |
| `plugins/scripts/hex_mse.py` | CardTemplate atlases, fonts, sleeve → `mse/` |
| `plugins/scripts/hex_art.py` | HARC index + UnityPy |
| `plugins/scripts/hex_compose.py` | 2D faces |
| `plugins/scripts/hex_rules.py` | keyword glossary + primer |
| `plugins/scripts/import_hex_shards_of_fate.py` | build plugin |
| `plugins/images/hex-shards-of-fate/_art/` | cached 512 portraits |
| `plugins/images/hex-shards-of-fate/<set>/` | composed JPEGs |

Rebuild: `plugins/hex-shards-of-fate/.venv/bin/python plugins/scripts/import_hex_shards_of_fate.py`

---

## Constructed sets in this client

Shards of Fate → Shattered Destiny → Armies of Myth → Primal Dawn → Herofall → Scars of War → Frostheart → Dead of Winter → Doombringer. Alts/promos/PvE folders beside them.
