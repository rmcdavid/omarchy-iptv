# tests/fixtures/qa-id-rotate/

The end-to-end password-rotation fixture for **D-ID-1** (`docs/STATUS.md`,
"## Defects"; the phase-3 spec is `docs/QA-PHASE3.md`). It is run by
`tests/test_fixture_id_rotate.py` through the real `playlist --state-dir`
verb of `bin/omarchy-iptv`, in a subprocess, with `--cache-dir` and
`--state-dir` under a scratch directory and HOME redirected by
`tests/helper_loader.py`. Nothing here reaches the network: every host is
under the reserved `.test` TLD and no URL carries userinfo or a credential.

## Why this fixture exists

D-ID-1: a channel with no unique tvg-id got the id `u:<fnv1a32(url)>`, and an
Xtream stream URL carries the account password, so a routine password change
re-keyed every such row and silently orphaned every favourite, recent,
`lastPlayed` and `session` record. Scheme 2 keys such rows by name
(`n:<fnv1a32(folded name)>`) and a one-time migration remaps saved state.

The list the plugin is configured with cannot show any of this: iptv-org
carries a unique tvg-id on every row, so every id is `t:` under both schemes
and the migration is a total no-op there. A pass on that list cannot tell a
wired migration from a dead one, which is byte-for-byte the state two
reviewers refused. `tests/test_channel_ids.py` already proves the mechanics on
`channel-ids.json` and drives the verb once on `basic.m3u` (one row moves).
This fixture is the rotation those tests never run: seed, migrate, rotate,
resolve.

## Files

- `list-v1.m3u` -- the provider list BEFORE the rotation. Sixteen rows in
  five categories, described in the file's own header comment:
  - A. six rows with no tvg-id and a unique name (legacy `u:`, scheme 2 `n:`;
    MUST move)
  - B. one tvg-id shared by an HD/SD pair with distinct names (legacy `u:`
    because the tvg-id is not unique, scheme 2 `n:`; MUST move, through the
    non-unique-id path)
  - C. four rows with a unique tvg-id (`t:` under both schemes; must NOT move)
  - D. exactly one colliding-name pair, no tvg-id, byte-identical names,
    different URLs (both stay `u:`; the accepted limit **D-ID-2**, observable)
  - E. two DIFFERENT names whose folded fnv1a32 collide, `Hash Twin 132789`
    and `Hash Twin 729192`, both `n:e63189cb` (found by brute force through
    the shipping `name_id_key`). The uniqueness test runs on the hashed key,
    so both are refused and stay `u:` exactly like D.
- `list-v2.m3u` -- byte-identical to v1 except that the path segment after
  `/live/` differs on every stream URL (`k1` -> `k2`). That segment stands in
  for the credential slot of an Xtream URL; it is not a credential. Every
  `u:` id changes between v1 and v2, every `n:` and `t:` id survives.
- `state-seed.json` -- a scheme-1 `state.json` with legacy `u:` ids in all
  four slots `remap_state_ids` touches, plus one favourite that is already the
  TARGET of another row's remap (the merge-not-duplicate path; favourites are
  global across sources, so another source may already have contributed it),
  plus one unknown top-level key the helper must preserve. The map is below.
- `verify.js` -- the JavaScript half. The python test runs it through node
  with an argv list; it calls the shipping `Model.js` (`channelIds`,
  `channelIdRemap`, `remapStateIds`) on the helper's own `channels.json`
  output and the seed, and prints JSON. This is the first python-drives-node
  pattern in the repository; it holds both id implementations to one fixture
  by a call, not by a name.

## The seed, row by row

Ids are what the shipping helper assigns on `list-v1.m3u` (scheme 1 on the
left). "moves" counts toward the `moved 8` the helper must report.

| Slot | Seeded id | Row | Category | Expected |
|---|---|---|---|---|
| favorites[0] | `u:9712e180` | Alpha News | A | moves to `n:de152e0a` |
| favorites[1] | `t:hotel.test` | Hotel TV | C | stays |
| favorites[2] | `n:d8cf1772` | Charlie Kids (already the scheme-2 target) | A | stays |
| favorites[3] | `u:36f90b72` | Charlie Kids (legacy) | A | moves onto favorites[2]: merged, appears once |
| favorites[4] | `u:4a0e659f` | Lima Twins (first) | D | stays `u:`; orphaned by v2 (D-ID-2) |
| favorites[5] | `u:402cf731` | Golf HD | B | moves to `n:2a0db957` |
| favorites[6] | `u:58b2a668` | Bravo Sports | A | moves to `n:99ad941e` |
| favorites[7] | `u:e2ffd78c` | Hash Twin 132789 | E | stays `u:`; orphaned by v2 |
| recents[0] | `u:33db2e82` | Delta Movies | A | moves to `n:92937b2e` |
| recents[1] | `t:india.test` | India TV | C | stays |
| recents[2] | `u:b170b7bd` | Echo Music | A | moves to `n:320e63f7` |
| lastPlayed | `u:f91b61c4` | Foxtrot Docs | A | moves to `n:9ca3981a` |
| session | `u:1db3ed20` | Golf SD | B | moves to `n:47f21214` |
| `qaUnknownTopLevelKey` | -- | -- | -- | survives the rewrite byte for byte |

Eight references move, so the first run reports `moved 8 saved channel
reference(s) onto id scheme 2`, favourites go from eight entries to seven,
and the file is rewritten once at mode 0600 (the test seeds it at 0644 on
purpose, so the mode after the write is an observation of the write). A
second run on v1 reports nothing and leaves mtime and sha alone. A run on v2
also reports nothing, and every reference that moved, plus every `t:`
reference, resolves to the same channel NAME as before. The two accepted-limit
rows (D and E) do not: they are orphaned, which is D-ID-2 made executable.

## What the terminal settles, and what still needs a screen

Settled here: that the shipping verb, given a state directory, moves exactly
the seeded references and no others, merges rather than duplicates, preserves
what it does not know, writes 0600, is idempotent, and that after the
rotation every moved reference still names its channel while the legacy ids
of those rows all differ between v1 and v2; that `Model.js` computes the same
ids, the same remap and the same post-remap state on this fixture as the
helper does; and that the user's real `state.json` is byte-identical before
and after (`helper_loader.live_state_fingerprint`).

Not settled here, and not attempted by this lane: observing `--state-dir` on
the RUNNING helper's argv with `ps` while the shell fetches the active source
(the argv builders are asserted in `tests/Model.test.js`, but only a live
process shows what the shell actually spawned), and the guide rendering the
merged favourite once.

## Rule 11: the fixture goes red against a dead migration

With `channel_id_remap` returning `{}` in `bin/omarchy-iptv` (a wired call
site around a migration that moves nothing, which is the refused state), 4 of
the 7 tests in `tests/test_fixture_id_rotate.py` fail: the first run reports
no `moved` line and every moved favourite is orphaned against v1's own
channels.json, the idempotence test finds no first move to be idempotent
about, the rotation test finds every seeded reference orphaned after v2, and
the node cross-check disagrees with the helper on `moved` and on the remap.
Against the shipping code all 7 pass. The exact counts are in the test
module's docstring.
