# Omarchy IPTV

A native Omarchy shell plugin: a keyboard-first live TV guide with EPG,
favorites, source management, and mpv playback. One plugin id,
`io.github.rmcdavid.iptv`, with three kinds: `bar-widget`, `overlay`,
`service`. It runs inside the single long-running `omarchy-shell`
Quickshell process. Released through v0.13.0, the third release cut for a finding the
marketplace maintainer raised (D-SINK-8, D-TEXT-1, now D-SINK-13); the
verified snapshot is v0.12.0 (f89f748, #10012, approved 2026-10-04 in about
an hour) until the 0.12.1 and 0.13.0 requests are actioned;
the twelve days it sat on v0.7.1 are explained in the decisions log.

## Branches: `dev` is the tree, `main` is the artifact

You are on `dev`. Everything is here. `main` holds ONLY the install artifact:
the thirteen files in `ALLOWLIST` in `scripts/release.py`, exported from a
clean, green `dev` by `scripts/release.py build`, committed onto `main` with
its previous tip as parent, and tagged. Nobody commits to `main` by hand, and
nothing is ever pushed to `main` except the output of that script.

Why. `omarchy plugin add` is a whole-repository `git clone`, and the
marketplace validates default-branch HEAD. So for the life of this project
every file on `main` landed in every user's plugin directory -- including this
one, a root-level agent instruction file that any coding agent opened inside
`~/.config/omarchy/plugins/io.github.rmcdavid.iptv/` would obey as its own.
A marketplace reviewer found that on 2026-09-20 (issue #7374) and was right.
The fix is structural, not a rename: what ships is an explicit allowlist, and
`release.py check` runs in the gate to prove the list is whole -- every
runtime import resolves inside it, every manifest entry point is on it, the
README names nothing outside it, and no agent-instruction filename is on it.

Consequences you must respect:
- This file never ships. Neither does `docs/`, `tests/`, `scripts/`, or
  `.claude/`. Do not reference them from README.md by path; link the `dev`
  branch by URL. The gate rejects a bare `docs/...` in the README.
- Adding a file the plugin needs at runtime means adding it to `ALLOWLIST`,
  or the release ships broken. The gate catches an import it cannot find.
- `main` must stay linear: `omarchy-plugin-update` is `git merge --ff-only`,
  so a force-push to `main` strands every install. Never rewrite it. A GitHub
  ruleset (`main-is-the-artifact`, #23743896) enforces this on the remote --
  no force-push, no merge commits, no deletion, no bypass for anyone -- so a
  by-hand `git push origin X:main` that is not a fast-forward is refused
  there, not only by convention here.
- A release is: bump `manifest.json` (and `Model.PLUGIN_VERSION` with it,
  D-HOST-1), date the top `CHANGELOG.md` heading for the day of the cut,
  re-level the test floors in `scripts/check.sh` to the counts on the tree,
  green gate, `scripts/release.py build --gate-already-green`, then push
  `dev`, `main` and the tag. `build` refuses a heading that names another
  version or carries another day's date, which is how 0.8.0 came to ship
  release notes dated the day before it existed (D-REL-4).
- **A pending marketplace verification request does not hold `main`.** This
  said the opposite until 2026-09-26: "while a marketplace review is open,
  `main` moves only when the reviewer asks for a new commit", written on
  2026-09-20 during the #7374 listing freeze and never revisited, while two
  product-owner decisions had already overtaken it -- 2026-09-21, "the review
  freeze on `main` is over; the branch model stands", and 2026-09-25, a
  pending request blocks nothing because `VERIFICATION.md` says the verified
  snapshot is unchanged while an update is pending. A moved `main` simply
  reads as `Update unverified` until a maintainer actions the request.
  What DOES matter is the opposite discipline, and it is the reason the
  marketplace never served anything past v0.7.1: four update requests were
  closed BY US as superseded, each at about a third of the maintainers' only
  demonstrated turnaround of 3.5 days. So a release files a NEW verification
  request and never closes an older one. Settled by the product owner on
  2026-09-26 (F-M3-4).

## Where the truth lives

Read these before changing anything; they outrank your instincts.

| Document | Authority |
|---|---|
| `docs/PRODUCT.md` | Vision, locked decisions, user stories, quality bar, M2 scope |
| `docs/ARCHITECTURE.md` | Data, processes, security. Section 12 and 12.1 are product-owner rulings and override the text above them |
| `docs/UX.md` | Interaction and visuals for the guide and bar |
| `docs/UX-SOURCES.md`, `docs/ARCHITECTURE-SOURCES.md` | The Sources feature. The rulings SR1-SR32 at the end of the architecture file override everything earlier |
| `docs/PLAN-M2.md` | Current milestone plan, lane splits, risks, process rules |
| `docs/ARCHITECTURE-PLAYER.md` | The detached player (M2-02). Section 12 is my rulings, section 13 is a binding amendment that withdraws part of section 9 |
| `docs/SPIKE-QUICKSHELL-SOCKET.md` | Proof of how Quickshell's socket type really behaves. Read before writing socket code; a failed connect is permanent |
| `docs/M2-03-CHANNEL-NUMBERS.md` | Channel numbers and numeric zap. Section 13 is my rulings CN1-CN14 |
| `docs/ACCESSIBILITY-INVESTIGATION.md` | Why nothing the guide declares reaches a screen reader. Section 6 settles the cause with measurements; section 8 is what we change regardless; section 9 holds the upstream drafts |
| `docs/STATUS.md` | Living board, defects, decisions log |
| `docs/QA.md`, `docs/QA-SOURCES.md`, `docs/QA-RESULTS.md` | Test plans and evidence |
| `docs/OMARCHY-PLUGIN-CONTRACT.md` | Verified facts about the Omarchy plugin API on this machine |

When two documents disagree: product-owner rulings win, then UX for
interaction and visuals, then architecture for data and process. Do not
resolve a conflict silently. Collect conflicts as numbered decision
requests and raise the batch.

## Engineering constraints, non-negotiable

1. Theme tokens only. Every color and metric comes from `Color.*` and
   `Style.*`. A literal needs a `CONVENTION-EXCEPTION` comment saying why.
2. argv-only process launching. Never `bash -c`, never string interpolation
   into a command, never `shell=True`. Playlist-derived data reaches mpv or
   curl as argv items, never as shell text.
3. The helper `bin/omarchy-iptv` is Python 3 stdlib only. No third-party
   imports, no new runtime dependency.
4. No sudo, ever. No writes inside the plugin directory at runtime.
5. URLs are redacted to scheme and host at every sink: notifications,
   tooltips, guide text, console, IPC output, helper stdout and stderr, **and
   the accessibility bus**. Playlist URLs carry provider credentials.
   `Model.redactUrls` exists; use it. The accessibility bus was missing from
   this list for the life of the project and D-A11Y-1 is the result. Two things
   publish there and both were missed:
   - The accessible **Value**, and the rule is narrower than it first looks.
     Measured on Qt 6.11.2 with a purpose-built probe on the real bus:
     `Accessible.EditableText` publishes the element's own `text` (a text-input
     control publishes its `displayText`); `Accessible.StaticText` publishes
     its `Accessible.name`, and its `text` property never reaches the bus at
     all; `Accessible.Button` exposes no text interface. So **the exposure is
     confined to elements declared editable** -- both the form fields and the
     search line at `Guide.qml:2088`, a plain `Text` carrying
     `Accessible.role: Accessible.EditableText`. Masking
     `Accessible.description` protects none of them. An earlier version of this
     rule said any annotated item publishes its `text`; that was wrong, and an
     over-broad security rule gets ignored rather than followed.
   - The **text-change event payload**. Assigning a whole new string to `text`
     raises `TextUpdated` carrying the full plaintext in both its inserted and
     its removed halves. It fires on every mask and every reveal, on a field
     whose Value reads as bullets, and on an `Accessible.ignored` field, so the
     states that look safe leak on the way into themselves.
   - **Process argv**, which was missing from this list while the list itself
     said to add sinks to it (D-SINK-3). The helper used to be handed the
     composed playlist URL as an argument, so it sat in `/proc/<pid>/cmdline`
     -- which is world-readable, unlike `/proc/<pid>/environ` -- for as long
     as the fetch ran. That was recorded as a KNOWINGLY ACCEPTED residual in
     `docs/ARCHITECTURE.md` section 6, transient and reasoned about, with the
     fix named in the same paragraph and deferred "if this is ever
     revisited". It was revisited from outside: a marketplace reviewer raised
     it against the shipped 0.9.1 and the transient exposure was CLOSED on
     2026-10-01 (D-SINK-8). The URL travels in the environment variable
     `OMARCHY_IPTV_URL`, set by the service on the helper process at the
     three spawns that carry one (the playlist fetch, the EPG fetch, the
     source probe) and read by the helper's `playlist` and `epg` verbs when
     `--url` is absent; `--url` stays for a human in their own shell.
     `environ` is mode 0400, but the kernel's open check is a ptrace-read
     check that EVERY process running as the same uid passes while the
     target is dumpable -- "your own account" meant every program the user
     runs -- so the fetch verbs make themselves non-dumpable first
     (`shield_environment`, D-SINK-9): the same-uid reader then gets EACCES,
     only root reads it, and a crash writes no core (a dumpable crash hands
     its whole environment to systemd-coredump, durably, in the journal).
     Measured both ways on 2026-10-01. What remains is the window between
     exec and the shield, which sits before every import but `sys`: the
     interpreter starting and compiling a 5,000-line file. It is CPU-bound,
     so it scales with load -- 98-113 ms idle at sub-millisecond resolution,
     median 105 over twelve runs (about 125 ms when the shield sat below
     the stdlib imports, which is where the first version put it while
     calling it the first statement), 264-634 ms with the cores oversubscribed twice over -- and
     it is NOT the floor: a split stub that shields before compiling the
     body reaches about 25 ms. An earlier version of this rule said nothing
     a child does can shorten it; that was false by about five times.
     Readable in that window by same-uid processes only. State it as a
     bounded, measured window under a stated load, never as zero and never
     as unshortenable. The fetch verbs start no child process,
     so nothing inherits the variable -- the helper forks mpv only in
     `player start`, on a Process the service never hands this environment;
     keep BOTH halves that way. In QML, assign
     `<proc>.environment = Model.fetchEnvironment(<url>)` immediately before
     every `running = true`, `{}` included on a run that carries no URL:
     re-assignment REPLACES the previous value, and that is what keeps a
     stale URL out of a later run on the same Process object.
     What is NOT accepted, and what the rule missed, is the DURABLE form: the
     README used to instruct the user to set a credentialed URL with
     `omarchy bar set`, which writes it into their shell history permanently.
     A transient exposure reasoned about is not a licence for a durable one
     nobody costed. Prefer the in-app form, which reaches neither.
     The lesson this episode adds: an accepted residual is invisible to a
     review process that only checks consistency with the documented
     decision, and it took someone outside the project to ask why it was
     accepted.
   - The **MPRIS session bus**, via a script this project does not ship and
     did not know was loaded (D-SINK-4). mpv autoloads every script in its
     system directory; on this distribution that includes `mpv-mpris`, which
     publishes `xesam:url` -- the stream URL, credentials and all -- to every
     process on the session bus for as long as a channel plays. Measured on
     the real bus with a synthetic credential, not reasoned about.
     `--force-media-title` guards the TITLE, and the title is a name, never
     a URL: the launch argv's `IPTV` holds only while the player is idle,
     and the helper's `apply_channel` sets `title` (`$>`-prefixed, so mpv
     expands nothing in it, S-01) and `force-media-title` to the channel name
     on every zap, by design (ARCHITECTURE-PLAYER 4.11 and hard requirements
     2 and 3). An earlier version of this item said the title "reads
     `IPTV`", which is true until the first play (D-DOC-4). The URL has no
     equivalent option and mpv-mpris has no configuration surface, so the
     only lever is `--load-scripts=no`. It is RESERVED as well as defaulted,
     because user `mpvArgs` are concatenated after the base argv and a
     pasted `--load-scripts=yes` would silently reopen it.
     The lesson generalises past this one option: **a sink can be opened by
     software you did not write and did not choose to run.** The sink list had
     only ever been audited over code in this repository.
   - **Qt text layout** (D-TEXT-1). A `Text` whose `textFormat` is left at
     the default, `Text.AutoText`, is a NETWORK sink for whatever string it
     renders: Qt reads the string for markup, and an `<img src="http://...">`
     in it is fetched. Measured on Qt 6.11.2 offscreen against a logging
     server, one `Text` per case (QA-RESULTS "Marketplace finding at
     2d3cee3, 2026-10-02"): AutoText resolves to StyledText and GETs the
     `src` with `User-Agent: Mozilla/5.0`, silently, whether the tag is
     first, last or 300 characters in, elided or not, and whether or not the
     element is visible, sized, on screen or parented into a scene at all --
     the fetch happens at text layout on creation. An https `src` draws a
     TCP SYN to port 443 from the QML process (the handshake beyond it was
     not checked). `Text.StyledText` and `Text.RichText` fetch too. The first
     measurement saw Qt log a failed transfer's FULL URL to stderr and
     filed it against RichText; re-measured case by case, the line appears
     only while the scene also holds an https `<img>` toward a
     non-routable host, never for a RichText 404 alone -- a console sink
     that exists under that condition, which the kept spike does not
     reproduce on purpose. `Text.PlainText` is the only stop: no request
     in four runs, the tag drawn as glyphs. Two things that look like
     closures are not: entity escaping (AutoText decodes `&lt;img ...&gt;`
     back into a tag, so escaping is a rendering change, not a sink closure)
     and URL redaction (the helper's `redact_urls` turns
     `<img src="http://h/x.png">` into `<img src="http://h">`, still a
     well-formed, fetchable tag). The element that carried this was the
     channel-wall caption, the `Text` with `text: tile.name` inside
     `channelWall`, which declared no format while 42 other `Text`s declared
     PlainText; and the exposure was every guide open, not the wall:
     `channelWall` has `visible: root.wallView` over a live
     `model: root.rowCount`, and a GridView realises delegates by geometry,
     so the first page of captions is laid out whether or not the user has
     ever pressed the wall key. Found by the marketplace maintainer on
     omacom/omarchy-plugin-marketplace#9628 against the shipped 0.9.2.
     The rule, as the gate enforces it: EVERY shipped `Text` (and `Label`,
     a Text subclass with the same default) declares `textFormat`, and
     declares `Text.PlainText` -- the plugin's own glyph Texts included,
     because a rule with "unless it looks harmless" in it is the rule the
     next caption gets written under. `Text.StyledText` is allowed only for
     the plugin's own strings, with a `// MARKUP-EXCEPTION: <reason>`
     comment on the line directly above the `textFormat` line and a test
     that what it renders composes from literals (`footerHints` renders
     `Model.footerHints` through `Model.footerHintMarkup`, tested in
     `tests/Model.test.js` under "F-TEXT-2"). The fix is at the SINK and
     not in the parsers the reviewer named (`clean_name`, `displayName`):
     a name must display its literal characters, a tag stripper can
     manufacture a tag out of two halves (the host's own notification code
     documents that case), and EPG titles never pass through the name
     cleaner at all. Two surfaces stay outside the guard and are recorded
     rather than fixed: the QtQuick Controls `TextField` placeholder in the
     Sources form is AutoText with no plugin lever and renders only strings
     the user typed; and the strings the plugin hands to the HOST --
     section headers, the confirm dialog, the bar tooltip, the active-window
     title, and a failure toast's body -- are rendered by host files under
     `/usr/share/omarchy/shell`, PlainText except the toast body, which is
     StyledText behind the host's own image-tag stripper. Those five files
     are recorded in `docs/OMARCHY-PLUGIN-CONTRACT.md` and pinned by
     `tests/test_host_text_format.py`, which goes red on this machine when
     a host update changes or removes the declaration on one of those
     elements; a moved line stays green, so the line numbers in the
     contract's table are for the reader, not the test.
     `scripts/check-text-format.py`, run by `scripts/check.sh` under the
     banner "text format guard", enforces the declaration;
     `scripts/dev-harness/text-scenario.sh` observes the sink itself, checks
     T1..T6 over a playlist whose names carry `<img src>` probes and a
     logging server, with `--baseline <ref>` to show the red run against
     the code before the fix; the measurement is re-runnable from
     `scripts/dev-harness/spikes/text-autotext-img/`.
     The lesson (F-TEXT-2): the rule "`Text.PlainText` for any user-supplied
     string" has been in `docs/ARCHITECTURE.md` since the scaffold
     (42015dc, 2026-09-12), the caption landed without it (ddbc6d6,
     2026-09-25), and the rule's acceptance row SRC-SEC-13 was graded by
     `grep -n 'StyledText\|RichText' Guide.qml`, which cannot see a MISSING
     line on an element whose default is the unsafe one. That is rule 14's
     shape exactly -- written down in this file, and still committed,
     because the grep was never re-graded after rule 14 existed. A check
     that cannot go red for the failure it guards is not a check.
   - **The player's on-screen display**, through the `show-text` command
     (M5-01, owner decision D9, joining this list the day the feature
     ships). `show-text` PROPERTY-EXPANDS its argument -- a `${path}` in it
     is drawn on the picture and into any screenshot -- which is the whole
     reason `--osd-msg1..3` are reserved. So the rule is "nothing
     provider-controlled goes through it", not "no OSD": the one line the
     plugin draws after a seek is numbers only, composed by
     `Model.rewindOsdText` (one argument, the seek reply) and mirrored by
     `rewind_osd_text` in the helper, with ONE shared fixture,
     `tests/fixtures/rewind-osd.json`, that both run, asserting equal output
     and that no output contains `$` anywhere. The helper's seek reply is
     numbers and booleans alone and never echoes `path`; the existing
     status reply emits `pathHost` and this one emits nothing of the kind.
     The user's own `--osd-level=0` turns the line off. On the same day
     `--demuxer-cache-unlink-files` joins `MPV_RESERVED` in both mirrors
     (D3; design 2.6): the privacy-relevant switch is not whether mpv
     caches on disk but whether the file OUTLIVES the process. mpv unlinks
     its cache file at creation, so by default the bytes die with the
     player; with that option set to `whendone` or `no` a copy of the stream
     survives at a path the plugin never listed, which is `--stream-record`'s
     class, and that option is already reserved. `--cache-on-disk` itself is
     a user choosing their own disk, the PO-5 shape, and gets the PO-10
     footer warning rather than a refusal. Nothing else moves: the four
     standing facts about mpv's directories and handoffs -- the shader and
     ICC caches contained in the runtime directory but NOT reserved (CL2),
     `--screenshot-dir` deliberately unreserved, `--watch-later-dir`
     reserved, and the `--ytdl*` handoffs warned rather than refused
     (PO-10) -- stay exactly as they are. Rewind inside the default window
     adds no other sink: the seek crosses the private 0600 socket with no
     address in it, nothing forks, nothing is written, nothing reaches a
     bus. Enlarging the window, in RAM or on disk, is refused this round
     (D2), and the README names the `mpvArgs` lever with its RAM cost
     rather than pretending the lever does not exist.
   - **The TLS peer** (D-SINK-13), which is the sink that is not a place the
     plugin writes but a party it talks to. mpv's `--tls-verify` defaults to
     `no`, so mpv hands `tls_verify=0` to FFmpeg and the base argv never said
     otherwise: measured on mpv 0.41.0 against a local server with a
     self-signed certificate, today's shipped argv exits 0 and PLAYS the
     stream, where `--tls-verify=yes` exits 2 on `tls: Peer certificate failed
     verification`. So an on-path attacker could present any certificate,
     receive the credentials in the stream URL and in the headers
     `apply_channel` sets before the loadfile, and serve back whatever media
     it liked. Raised by the marketplace maintainer against the shipped
     0.12.1, the third such finding in three weeks.
     The scope was one sink, measured rather than assumed: the helper's own
     playlist fetch already refuses a self-signed certificate, because urllib
     verifies by default and nothing disables it. The plugin verified TLS
     everywhere except the one place it handed the stream to mpv.
     **The fix is four layers and NONE of them is redundant.** mpv applies
     command-line options in order and a LATER token beats an earlier one, so
     `--tls-verify=yes` followed by a user `--tls-verify=no`, by
     `--no-tls-verify`, or by a `--profile` naming a profile that sets it off,
     all PLAYED the self-signed stream -- the last being the one no reserved
     list can catch, because a profile carries arbitrary options. So: the
     option is in the base argv where a reader looks; it is RE-ASSERTED as the
     final element after the user's `mpvArgs`, which is the layer that
     actually binds and closes all three; `--tls-verify` is RESERVED in both
     its `=no` and `--no-` forms so a direct attempt is refused loudly rather
     than silently overridden; and `--tls-ca-file` is deliberately NOT
     reserved, because it is the targeted escape for a provider with a
     self-signed or private certificate and it is measured working behind the
     trailing re-assertion. `--profile` is not reserved either: the last token
     makes it harmless.
     **The trailing token does NOT cover everything, and the first version of
     this entry said it did.** `--stream-lavf-o` hands `key=value` straight to
     libavformat for the stream, and FFmpeg's own AVOption is `tls_verify` --
     a different knob from mpv's `--tls-verify`, reaching the same place -- so
     our last word is not the last word. Measured with BOTH tls-verify tokens
     in place: `--stream-lavf-o=tls_verify=0` played the attacker's stream,
     and so did its `-add`, `-append` and `-set` forms, with the GET in the
     attacker's log each time. It is reserved, which is the only thing that
     closes it, and `mpvOptionBase` strips the list suffixes so one entry
     covers all six spellings. `--demuxer-lavf-o` is measured NOT to bypass
     (it configures the demuxer, not the protocol) and stays unreserved rather
     than reserved on suspicion.
     The lesson, and it is the one worth carrying: an option that forwards
     arbitrary options to a LIBRARY is not covered by winning an argument with
     the program. Ask what the library is configured with, not only what the
     program was told. Three independent reviewers found this against a fix
     that had already been measured working. Do not "tidy away" the duplicate token -- removing
     either occurrence is a security change, and the one that matters is the
     last.
     A user's own `mpv.conf` does NOT beat the command line (measured), so a
     pre-existing configuration cannot undo this. A bare `--` would make
     everything after it a filename, which would defeat a trailing token, but
     `MPV_ARG_RE` is `^--[a-z0-9][a-z0-9-]*(=.*)?$` and the shipping
     `filter_mpv_args` rejects a bare `--`; that is measured by calling it,
     and it is load-bearing for layer two.
     The lesson this one adds: a defaulted option and a reserved option were
     enough for every earlier sink, and they are not enough when the program
     being configured lets a later argument rewrite an earlier one. Ask what
     the LAST word is, not what the setting is.
   When you add a sink, add it here.
6. Files the plugin writes: cache under `~/.cache/omarchy-iptv/sources/<key>/`,
   state at `~/.local/state/omarchy-iptv/state.json`, socket under
   `$XDG_RUNTIME_DIR/omarchy-iptv/`. Modes 0700 for directories, 0600 for files.
7. Performance budgets: the guide opens in under 150 ms with a 10,000 channel
   cache, typing stays responsive, and the helper parses 10,000 channels in
   under a second.
8. ASCII only in `.js` and `.py` sources. Nerd Font glyphs belong in QML, by
   codepoint, verified present in the installed font.
9. Never wait for the host to echo your own write back before updating your
   own UI. The Omarchy shell publishes a plugin's `barConfig` one write
   behind, so a plugin never receives the echo of its own settings write, and
   `updateEntryInline` returning `false` means "already stored", not
   "failed". Apply your own write locally in the same turn, drop that
   override as soon as the host reports any other value so external changes
   win, and keep the echo path idempotent. See the last section of
   `docs/OMARCHY-PLUGIN-CONTRACT.md`.
10. A test double must never be more forgiving than the real thing. When you
   change a fake to match reality, prove it with counts: the suite must fail
   against the code that shipped the bug and pass against the fix.
11. Prove every new test catches something. Run it against the code as it was
   before your change and report both counts. When the code is new and there
   is no "before", mutate the shipping function instead: break one decision
   deliberately and show the test goes red. A test written after the code,
   never seen failing, is decoration. This found a real gap here: a router
   case that survived every mutation until a missing transcript was added.
12. A test that mirrors logic instead of calling it can pass while the
   shipping path is broken. If pure logic is stranded somewhere a test cannot
   reach, such as inside a QML component, lift it into `Model.js` and call it
   for real rather than reimplementing it in the test.
13. The rule about names applies to documents too, not only to code.
   Wherever two things are joined by a NAME rather than by a call, nothing
   verifies the join and the failure is invisible. A defect filed in prose in
   `docs/QA-RESULTS.md` and a row on the board in `docs/STATUS.md` are joined
   by an id, and for a long time nothing checked it: a lane already filed
   F-CHNO-4 saying the board was stale, the board was patched by hand, and 32
   more ids drifted off it afterwards, one of them a P2 that had been a
   release gate. `scripts/check-defect-ledger.py` now makes that join a call.
   When you invent a new cross-document id -- a ruling, a scenario, a defect
   -- either point an existing check at it or write one. An id that only a
   human is expected to copy is an id that will eventually stop being copied.
   The join has a second failure mode, and it cost more: a finding with NO id
   at all. A QA plan listed ten numbered, bold-titled, severity-graded
   findings under "Contradictions and gaps found while planning" on
   2026-09-14, and because a test-plan section number is not a defect id the
   checker never saw them. Three were fixed within the hour and read as open
   for eleven days; one was half done and read as done; one recurred in two
   shipped files before anyone noticed (D-REL-3). So: **a finding gets its
   `D-` or `F-` id on the day it is written**, `F-` when it is a finding
   rather than a defect (the checker treats them alike). The checker enforces
   the part it can see: under any heading that names findings, defects,
   problems, gaps, contradictions, issues or weaknesses, every numbered item
   that opens with a bold title must carry an id. A list that is genuinely
   not findings says so ON THE HEADING -- "(not defects)" or "no defect ids"
   -- so the exemption is visible on the line a reader sees first, not
   buried in a script. Do not route around the check by dropping the bold
   title; an untitled item is a remark, and a finding written as a remark is
   the same defect with worse odds.
14. An acceptance criterion may not be a grep for the string the
   implementation was written to contain. Verify by calling the shipping logic
   or by observing the real sink. A rule that can be verified by neither is
   marked UNVERIFIED in the document that states it, and stays marked until
   something observes it. This project wrote accessibility rules from M0 and
   graded them with `grep -n 'Accessible\.' Guide.qml`, a test that cannot go
   red, so nobody noticed for months that NOTHING the guide declares reaches a
   screen reader (D-GS-3). The 17 executable assertions that existed all tested
   the string builders, proving a name composes correctly and never that it
   becomes a node. Applied retroactively this rule would have caught that, the
   credential leak on the same sink, and the row announcement, on day one.

## Never touch

- `/usr/share/omarchy/` is package-owned. Read it freely, never write it.
- `~/.config/`, `~/.cache/`, `~/.local/state/` belong to the user. Read only,
  unless the task brief explicitly authorizes a change, and then snapshot
  first and restore after.
- The installed plugin at `~/.config/omarchy/plugins/io.github.rmcdavid.iptv`
  is the user's live install. Do not modify it as a side effect of repo work.
  **Including by reading it.** Verifying that an install carries a change by
  importing its helper -- `SourceFileLoader(...).exec_module()` -- writes
  `bin/__pycache__/` into the plugin directory, which then shows as untracked
  in the very `git status` the next update depends on. Run the installed
  helper as a SUBPROCESS, the way the plugin itself does
  (`python3 <install>/bin/omarchy-iptv <verb>`), which compiles nothing.
  Done on 2026-09-27 and noticed only because the next update's
  pre-flight check found the install dirty.

## Verify before you claim

```bash
./scripts/check.sh          # validate + qmllint + node + python + qml spec
node tests/Model.test.js
python3 -m unittest discover -s tests
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml
omarchy plugin validate .
```

`scripts/check.sh` must be green before any commit. qmllint has a known
warning baseline: `missing-property` and unqualified access on host-injected
objects and on `Style` and `Color` children, `uncreatable-type` for
`PanelWindow`, and `signal-handler-parameters` on `Process.onExited`.
Anything outside that baseline is a real finding.

Pure logic belongs in `Model.js` so it is unit-testable from node, not only
visible on screen. A rule implemented in both JavaScript and Python gets one
shared JSON fixture that both implementations run.

## Working in parallel

This project is built by role lanes running in separate git worktrees.

1. Declare file ownership up front: files you may write, files you may read,
   files you must not open. A diff touching an unowned file is rejected.
2. One lane holds the display. If your brief does not say you hold it, you
   may not run `wtype`, `grim`, `hyprctl dispatch`, `omarchy theme set`,
   `omarchy plugin add|enable|disable|remove`, `omarchy bar set`, the dev
   harness, quickshell, or mpv with a window.
3. Finish in the foreground. Never end a turn waiting on a background run.
   Bound it with `timeout`, or poll it to completion in the same turn. A wait
   loop MUST have a bound: a maximum number of iterations or a deadline, and
   it must report that it gave up rather than looping on. An unbounded wait
   is a bug, not patience.
   Never write a wait or a kill that can match ITSELF. `pgrep -f foo.py` and
   `pkill -f foo` match the command line of the shell running them, so a loop
   that waits for `foo.py` to disappear finds itself and waits forever, and a
   kill by pattern can kill the terminal it was typed in. Both have happened
   here, and it happened a third time in a task brief I wrote MYSELF while
   quoting this very rule: `pgrep -f 'quickshell -n -p ...'` returns two pids,
   the second being the shell running the pgrep, and it changes between
   invocations. For the shell specifically the stable form is
   **`pgrep -x quickshell`**. Prefer `-x` over `-f` whenever the process name
   alone identifies it.
   A detached server's pid is read from the LISTENER, never from `$!`: behind
   `setsid`, `$!` is the wrapper, and a live pass once "killed" its fixture
   server that way and found it still serving at the next segment. `ss -ltnp`
   names the pid that holds the port; kill that. Wait on a pid, a file, or a marker the watched process writes; kill
   by pid. If a pattern is unavoidable, anchor it and exclude your own pid,
   and say in a comment why the anchor is load-bearing.
4. No shims at merge. Stubbing a dependency to build is fine; leaving one is
   not. Integration proves zero stubs with a grep and a green `check.sh`.
4b. **Lanes get their own worktree, or they get no `git add -A`.** Three lanes
   were once run concurrently in the SHARED working tree; they committed to
   `main` directly while the lead was also committing, and one lead commit
   swept two documents into itself that the lead had neither written nor read,
   under a message describing something else entirely. That commit was pushed.
   Nothing detected it, because `git add -A` cannot tell whose work it is
   staging. Either isolate the lanes, or stage by explicit path and read the
   diff before every commit. A concurrent tree also produced one measurement
   that was green only because a second lane had overwritten a mutation.
5. Snapshot before, restore after. A live pass backs up `shell.json`, the
   state directory and the cache first, and restores the exact end state.
   Restore ORDER matters while the shell is running: `shell.json` first, a
   few seconds to settle, then `state.json`, then re-check the hash. The
   other order is undone -- the settings change makes the service touch the
   source record and save its in-memory state over the copy you just wrote.
   Seen on 2026-09-21; the restore script was corrected mid-pass.
6. Check `pgrep -x hyprlock` before any keystroke. Typing into a lock prompt
   registers as failed unlock attempts. The harness checks this for you now:
   `run.sh key` and `run.sh type` refuse with exit 3 if hyprlock is running,
   and that refusal has no escape hatch. They also refuse unless the GUIDE
   holds the keyboard, which it answers itself over `ipc focusState` -- the
   compositor cannot be asked, because `hyprctl layers` carries no
   keyboard-focus field and `hyprctl activewindow` names the foreground
   toplevel while the overlay is receiving keys (measured 2026-10-06).
7. A scenario's output is its evidence, and evidence is never summarised from
   a tail. Every scenario opens a transcript through `qa_transcript_start`
   (`scripts/qa-lib.sh`) and prints the path as its own first line; report
   from that file. F-M3-1 is one live run of `m3-scenario.sh` that answered
   17 passed / 14 failed with WHICH FOURTEEN UNKNOWN, because the run was
   backgrounded and its output piped through `tail -n 3` by the person
   running it: every check was there and the scenario was not at fault -- the
   evidence was thrown away downstream of it. `tail`, `| head` and
   `grep -c PASS` keep the arithmetic and discard the finding. The transcript
   is a SINK (rule 5), so it is 0600 inside a 0700 directory and the function
   refuses a directory others can enter rather than writing into it; a
   scenario that sweeps its own transcript calls `qa_transcript_sync` first,
   because a line printed and grepped straight back was absent 6 times in 30
   under load.

## Commits

Small and logical, present tense, explaining why rather than restating the
diff. Never commit a red `check.sh`.
