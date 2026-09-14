# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

Entries below **[Unreleased]** are the Toybox fork of [seastan/dragncards](https://github.com/seastan/dragncards). Older `0.3.x` notes are leftover from the original Spades tree this engine grew out of.

## [Unreleased]

### Added

- Toybox club instance: invite-only sign-up (`DRAGN_INVITE_CODE`), alias + password accounts (no inbox), and log-in by alias.
- Haven LFG webhook (`HAVEN_LFG_WEBHOOK_URL`) so looking-for-game posts can land in club chat with a link back (`DRAGNCARDS_PUBLIC_URL`).
- Same-origin card art: plugins store relative image paths, the frontend prefixes `/cards/`, and host nginx maps that onto the fileshare. Plugin files do not publish a public image host.
- `keywordReminders` glossary under the giant card preview for terms found in printed text.
- Lobby deck editor at `/deck-editor/:pluginId` (catalog, plaintext import, start-a-table).
- Shared browse HUD (2D and 3D), lobby banner/logo slots, and author credit on the plugin list.
- Conversion toolchain under `plugins/scripts/` (Lackey, OCTGN, GEMP, live-table dumps, HEX / L5R / LoN / FoW and others) plus `collect_hosted_images.py`.
- First-pass club plugins (Lackey / OCTGN / GEMP / catalog conversions), live-table snapshots, and an in-tree LotR LCG definition. Most are raw card databases, not finished public plugins. They will not load on stock DragnCards.
- Table chat as a right-edge slide-out overlay (2D and 3D). Hidden except for a tab; hover peeks, click pins, click again hides. New chat pulses the tab while it is closed.
- Plugin lobby reference buttons: `tutorialUrl` plus up to eight extra links from `referenceLinks` (or `referenceLinkNUrl` / `referenceLinkNLabel`) in `main.json`.
- Tournaments (club admin): one open event per plugin, Haven announce, lobby registration, pairings with private match tables, winner report, kick/ban (counts as losses), early end. Plugin list pins open events with a trophy. Match size follows `playerCountMenu`. Two-loss-out auto-advances; Swiss/elim structures are stored for later pairing math.
- Limited play (sealed, draft, sealed draft): plugin `limited` recipes, server-side booster/starter generation, pick-and-pass overlay, then a lite deck editor with leftover Card Pool. Wyvern ships the first example. The host can start with whoever is seated; empty seats are left out of the pod.

### Changed

- README describes the Toybox fork, plugin maturity, compatibility with upstream, and credits.
- Public site URL for LFG / websocket origin is configured with `DRAGNCARDS_PUBLIC_URL` instead of a hardcoded host. Local `/cards/` proxy is opt-in via `REACT_APP_CARDS_ORIGIN`.
- Create / update / delete of a plugin is author-only (or admin).
- Plugin lobby layout: notes and rooms in the center, Create Room + Looking for Game stacked on the right (same width), tutorial and extra links stacked on the left. Removed the unused "Email me new LFG posts" toggle.

### Fixed

- Image-path helpers rewrite leftover absolute Toybox `/cards/` URLs to same-origin paths without storing a hostname in the repo.
- My Plugins list sends the session token. After plugin create/update/delete became author-only, the unauthenticated list request 401'd and the page looked empty.
- Limited draft overlay shows a full-size card preview on hover so pack cards can be read.

## [0.3.4] - 2020-03-16

### Changed

- Dependency updates

## [0.3.3] - 2020-01-26

### Changed

- Moved from `yarn` to `npm`.

## [0.3.2] - 2020-01-20

### Changed

- Dependency upgrades

## [0.3.1] - 2020-01-09

### Changed

- Moved chat layouts to be side-by-side with the game and lobby.

## [0.3.0] - 2019-11-22

### Added

- Bots learned how to bid by looking at their hands.
- Bots learned how to pick cards with some logic instead of randomly. They
  don't play perfectly, but they play "good enough" and are aware of nils.
  Note that they don't try to avoid bags.

## [0.2.1] - 2019-11-19

### Added

- Chat windows in the lobby and game rooms. Overall page layout needs to be
  improved, though.

## [0.2.0] - 2019-11-18

### Added

- Dumb bots to play against. They will always bid 3 and play random cards.

## [0.1.1] - 2019-11-17

### Fixed

- Fixed idle rooms not automatically deleting.

## [0.1.0] - 2019-11-16

Initial release. Rough, but playable with 4 people.

[unreleased]: https://github.com/KrystoferRobin/dragncards-hac/compare/v0.3.4...HEAD
[0.3.4]: https://github.com/mreishus/spades/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/mreishus/spades/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/mreishus/spades/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/mreishus/spades/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/mreishus/spades/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/mreishus/spades/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/mreishus/spades/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/mreishus/spades/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mreishus/spades/releases/tag/v0.1.0
