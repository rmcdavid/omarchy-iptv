# M3 plan: two things that make a long list less hostile

Product owner go: 2026-09-26 ("Let's do 1 and 2"). Built after 0.8.0, ships
as 0.9.0. Both features work on the owner's own data today: 1,464 channels
in 28 groups, two of which (Religious 117, Undefined 107) are fifteen percent
of the list and are scrolled past on every open.

| Item | What | Where the logic lives |
|---|---|---|
| M3-01 | Hide groups | `Model.js` (state key, scope filter, column section), `bin/omarchy-iptv` (state mirror), `Guide.qml` (key, column rendering) |
| M3-02 | Audio and subtitle picker | `bin/omarchy-iptv` (`player tracks`), `Service.qml` (one control kind), `Model.js` (rows, cursor, labels), `Guide.qml` (a panel over the list) |

The two share no code. They share a character: neither touches a refusal, a
privacy decision, or a host contract, and both are one keystroke from the
list.

## 1. Decisions (product owner delegated: "I trust you on this decision")

Numbered so a document can cite one. Each is a sentence a user could be
told, then the reason.

1. **Hiding removes a group from browsing. It never removes something the
   user chose by hand.** Hidden groups leave All, the GROUPS section, search
   from All, saved searches and the wall. A starred
   channel, a recent, and a channel reached by its number still work and
   still show, because each of those is a thing the user did on purpose.
   Channel numbers do not shift: they come from the playlist's `tvg-chno`
   (M2-03), not from position.
   Two corrections from the 0.9.0 preflight. First, this said "the zap
   ring's All", which names a path that does not exist: `launchScope`
   resolves every non-Favourites launch to the channel's own group, so a
   GROUP ring is untouched by hiding. A FAVOURITES ring is not: its
   saved-search rows are filtered like Favourites itself, so hiding can
   shrink or empty it -- which is what this decision asks for, and the
   replacement sentence that said hiding never touches the ring was wrong
   in the other direction. Second, the
   sentence about numbers was a statement of intent, not of fact -- All
   stopped holding those channels and the jump landed nowhere, naming and
   then playing a channel the user had not asked for. `Model.numberJumpScope`
   sends the jump to the group's own scope, which is what decision 2
   already licenses, and a node check calls it.
2. **A hidden group is moved, not lost.** The column gains a HIDDEN section
   under GROUPS listing every hidden group that exists in the current
   source, dimmed. Selecting one shows its channels (the user asked for it by
   name), and the same key unhides it there. A user can always see what they
   hid and get it back with the keys they already know.
   **On the channel wall there is no column**, which the 0.9.0 preflight
   found: hiding works there, and the notice saying where the group went
   would have named a surface the wall does not draw and a key (`h`/`l`)
   that moves the cursor there rather than the scope. So on the wall the
   notice names `Ctrl+G`, the key back to the view that has the column.
   Refusing `x` on the wall was the alternative and is worse: the wall is a
   full browsing view, and a key that works in one view and not its twin is
   the kind of thing this project files defects about.
3. **The key is `x`, extended.** UX 3.1 already has `x` meaning "remove the
   cursor row from THIS list": a recent in Recent, a star in Favorites, no-op
   elsewhere. The no-op becomes "hide the cursor row's group" in All and in a
   group, and "unhide" in a hidden group. One key, one meaning -- take this
   away from here -- and the footer names the target (`x hide group` /
   `x unhide`) so the blast radius is stated before the press. Recent and
   Favorites are unchanged.
4. **Hidden is by group NAME, global, not per source.** "Religious" hidden
   once is hidden in every source that has a group by that name. Names
   collide across providers on purpose here; the collision is the feature.
   Cap 200 names, de-duplicated, whitespace-trimmed; both readers agree via
   one fixture.
5. **The picker asks the player, and the player is authoritative.** `t`
   (list mode, only while something plays) opens a panel: an Audio section
   and a Subtitles section, the selected track marked, an `Off` row for
   subtitles. `j`/`k` move, `Enter` selects, `Esc` closes. Every reply
   carries the whole track list AFTER the change, so the panel shows what
   mpv did, not what was asked. Nothing is remembered across channels or
   restarts in this milestone: a language preference is a second feature
   with its own questions (which language? per provider?).
6. **The track list is a sink (engineering rule 5, dev branch).** mpv's
   `track-list` carries `external-filename` for external tracks, which is a
   path or a URL, and a `title` the stream author wrote. The helper emits a
   whitelist of fields (`id`, `type`, `selected`, `lang`, `title`, `codec`,
   `default`, `forced`, `external`) with `title` through `redact_urls`;
   `Model.parseTracks` scrubs again before anything reaches the guide, the
   footer or an accessible name. `external-filename` is never emitted.
7. **No PIN, no lock.** Smarters hides categories behind a PIN. The useful
   half is hiding; a PIN in a keyboard-first guide on a single-user desktop
   is theatre.

## 2. Keys, in the table the footer is built from

| Key | Mode | Action | Hint |
|---|---|---|---|
| `x` | list, All or a group | hide the cursor row's group | `x hide group` |
| `x` | list, a hidden group | unhide it | `x unhide` |
| `x` | list, Recent / Favorites | unchanged (UX 3.1) | unchanged |
| `t` | list, something playing | open the picker | `t tracks` |
| `j`/`k`, `Enter`, `Esc`, `t` | picker | move, select, close, close | from `footerHints` |

`t` is a bare letter because the picker is list-mode only: search mode
types it. `x` in search mode types it too, so hiding is list-mode only.

## 3. Acceptance, each with the check that observes it

- `channelsForScope(all)` with a hidden group is the list minus that group,
  and with no hidden groups is the SAME array (identity), so nothing that
  compared by reference changes. Node, against the function.
- `scopeSurface` lists the hidden group under a HIDDEN header, dimmed, with
  its count, and only when it exists in the source. Node.
- Search from All does not find a hidden channel; search inside the hidden
  group does. Node, through `filterChannels(channelsForScope(...))` -- the
  real path, not a mirror.
- Both readers accept the same `hiddenGroups` bytes to the same list, and a
  write by the helper's own `state` verb keeps it (the erase that
  savedSearches suffered before it was taught). One fixture, two suites.
- `player tracks` against FakeMpv: lists, selects then lists, refuses a bad
  id, emits no `external-filename`, redacts a URL in a title. Python, over
  the socket.
- Every new test is run against the code before the change, or a
  deliberate mutation, and both counts are reported (rule 11).
- Open budget: hiding costs one `primaryGroup` per channel per scope
  rebuild only when the hidden list is non-empty; measured in node at 10,000
  channels and recorded in QA-RESULTS. D-PERF-1 (the open budget itself) is
  not touched by this milestone.

## 4. Not in this milestone

Remembering a preferred audio language; hiding single channels; a PIN;
per-source hidden lists; exposing hidden groups to the bar widget's ring
in any way other than "not there".
