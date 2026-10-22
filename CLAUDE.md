# Omarchy IPTV

A native Omarchy shell plugin: a keyboard-first live TV guide with EPG,
favorites, source management, and mpv playback. One plugin id,
`io.github.rmcdavid.iptv`, with three kinds: `bar-widget`, `overlay`,
`service`. It runs inside the single long-running `omarchy-shell`
Quickshell process. Released through v0.15.0 (2026-10-22: the P3 sweep, the bounds sweep's eight
rounds, D-EPG-11 and the #14748 work; `main` e710341). Four of the last releases were cut for a finding
the marketplace maintainer raised -- D-SINK-8, D-TEXT-1, D-SINK-13, and then
D-SINK-16 against the release that fixed D-SINK-13, on the verification
request for that very commit; until
2026-10-22 the verified snapshot was STILL v0.12.0 (f89f748, approved
2026-10-04), five releases behind, and that is worth knowing rather than assuming: the catalog
read on 2026-10-09 gives `verificationCommit f89f748`,
`verificationCheckedAt 2026-10-04T17:51:07Z`, beside `version 0.13.1`, so the
two fields do not mean the same thing. The requests for 0.12.1, 0.13.0,
0.13.1 and 0.13.2 were all CLOSED by the maintainer carrying `validated` and
`plugin-update` but NOT `approved-and-verified`, i.e. superseded rather than
approved, while he raised a finding on each, and so were 0.13.3's and
0.13.4's after his findings D-LOGO-11 and D-CLIP-1. 0.13.5's (#11114) was
stopped by the marketplace's automated security baseline, not by him: its
scanner refuses any non-executable file over 512 KiB and `Model.js` had
crossed it (D-REL-5, found 2026-10-12, the catalog read that day still
giving `verificationCommit f89f748`). 0.13.6 is the split that fixes it.
What the verified snapshot does and does not decide, because this file said
the wrong thing for a week: it decides the marketplace's "Verified" label
and nothing else. `omarchy plugin add` is a plain `git clone` of the
repository's current HEAD (`/usr/share/omarchy/bin/omarchy-plugin-add`; the
catalog's own `installNote` says "Omarchy clones the current upstream
repository"; nothing under `/usr/share/omarchy` reads `verificationCommit`),
and `omarchy-plugin-update` is `git merge --ff-only` of the same HEAD. So a
fresh install gets current `main`, verified or not. This file and the
lead's memory said a fresh install got the verified 0.12.0 until the 0.13.6
pre-cut review measured otherwise on 2026-10-12, and 0.13.6's first draft
of release notes repeated it. Re-read the catalog before repeating any of this;
the twelve days it sat on v0.7.1 are explained in the decisions log.

**Since 2026-10-22T03:45:56Z the verified snapshot is 0.14.3 (205ee12):**
#12474 closed `approved-and-verified` by the marketplace's automated
publication ("Updated and verified IPTV ... Verification method:
`automated`"), the first approval since 0.12.0. The catalog read at 06:50 CDT
that day carries `listingValidatedCommit 205ee12…`, `listingValidatedAt
2026-10-22T03:42:09Z`, `listingValidatedBranch main` and an
`automatedSecurityBaseline` block at the same commit with `outcome passed`;
the `verificationCommit` / `verificationCheckedAt` fields the paragraph above
cites are no longer in the catalog's shape, so re-read it before quoting
either name. The live install was already on 0.14.3. 0.15.0 (`main`
e710341) followed the same day, filed as its own request; 0.14.3 stays the
verified snapshot until a maintainer actions it.

## Branches: `dev` is the tree, `main` is the artifact

You are on `dev`. Everything is here. `main` holds ONLY the install artifact:
the files in `ALLOWLIST` in `scripts/release.py` (42 since D-REL-5 split the
model into `Model.mjs` and `model/` and D-REL-7 split the helper into
`bin/omarchy-iptv` and `bin/helper/`), exported from a
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
  A new helper part goes into the stub's `HELPER_PARTS` as
  `("12-x.py", 1, 0x00000000),` and into `ALLOWLIST` together, then
  `scripts/split-helper.py --seal` fills in its length and CRC-32:
  `release.py check` refuses a part the stub loads that does not ship, and
  one that ships that the stub does not load (D-REL-7).
- `main` must stay linear: `omarchy-plugin-update` is `git merge --ff-only`,
  so a force-push to `main` strands every install. Never rewrite it. A GitHub
  ruleset (`main-is-the-artifact`, #23743896) enforces this on the remote --
  no force-push, no merge commits, no deletion, no bypass for anyone -- so a
  by-hand `git push origin X:main` that is not a fast-forward is refused
  there, not only by convention here.
- A release is: bump `manifest.json` (and `Model.PLUGIN_VERSION` with it,
  D-HOST-1), date the top `CHANGELOG.md` heading for the day of the cut,
  re-level the test floors in `scripts/check.sh` to the counts on the tree,
  green gate, run `scripts/dev-harness/key-scenario.sh live` (on the tree
  since D-SINK-19 landed, `efde249`, 2026-10-14) under the
  nested headless cage on a private D-Bus (`scripts/dev-harness/private-bus.sh`,
  rule 6b) and record its count in `docs/QA-RESULTS.md` (the
  live arm is the only observer of the start-up window that D-SRC-15 lives
  in; `check.sh` runs just its 11-check preflight, and a README that
  promises the live run is only true while this step is run), then
  `scripts/release.py build --gate-already-green`, then push
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
- **Exception, decided by the product owner on 2026-10-13: `main` is HELD at
  0.13.6 until a maintainer actions #11315** (approves it or raises a
  finding on it). Why this request and not the rule: the marketplace's update
  validation checks the requested commit against the repository's CURRENT
  default-branch HEAD (`plugin-update.mjs`: "The repository HEAD no longer
  matches the requested update commit"), so a moved `main` makes a pending
  request stale; every request since 0.12.1 was superseded or answered with a
  finding before it could be approved, and #11315 is the first since 0.13.3
  whose automated baseline passed. `dev` moves freely; nothing runs
  `release.py build` or pushes `main` until #11315 is actioned. F-M3-4's
  half that says never close our own request stands unchanged.
  **The hold ended on 2026-10-13**, when the maintainer raised a finding on
  #11315 (D-LOGO-13); the rule above applies again, and a release still
  waits for the owner's word.
- **The same exception again, decided by the owner on 2026-10-20: `main` is
  HELD at 0.14.2 until a maintainer actions #11935** (approves it or raises
  a finding on it), for the same reason: a moved `main` makes the pending
  request stale. `dev` moves freely -- the helper split (D-REL-7) waits on
  it, unreleased. If the maintainer raises a finding, its fix ships at once
  in a new release, which then carries what `dev` holds. **This hold ended
  at 2026-10-20T18:47Z**, when the maintainer raised D-M3U-1 on #11935.
- **And a third time, decided by the owner on 2026-10-21: `main` is HELD at
  0.14.3 until a maintainer actions #12474** (approves it or raises a
  finding on it), for the same reason. `dev` moves freely -- the P3 sweep
  (`f55a32f`) and the bounds sweep wait on it, unreleased. A finding on
  #12474 is fixed and released at once, carrying what `dev` holds.
  **This hold ended at 2026-10-22T03:45:56Z**, when #12474 closed
  `approved-and-verified`; the standing rule applies again, and a release
  still waits for the owner's word.

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
     interpreter starting and compiling the stub, which is compiled whole
     before its first statement runs, so its size is in the window. It is
     CPU-bound, so it scales with load. With the whole helper in one file it
     was 98-113 ms idle at sub-millisecond resolution, median 105 over twelve
     runs (about 125 ms when the shield sat below the stdlib imports, which
     is where the first version put it while calling it the first
     statement), 264-634 ms with the cores oversubscribed twice over. Since
     D-REL-7 the helper is a 9 KB stub that shields and only then reads,
     checks and compiles the parts, and the window is 22.9-40.1 ms (medians
     27.0 and 27.1, measured on the 6,502-byte stub; the checking loader
     adds about 0.6 ms of compile at load 3.9)
     against 136.8-164.0 ms (medians 148.4 and 148.2) for 0.14.2's one-file
     helper, 12 interleaved runs each, twice, under a load average of 3.1-3.7
     (2026-10-17, QA-RESULTS "D-REL-7: the helper split, rebuilt on today's
     dev"). An earlier version of this rule said
     nothing a child does can shorten it; that was false by about five times.
     Readable in that window by same-uid processes only. State it as a
     bounded, measured window under a stated load, never as zero. The fetch verbs start no child process,
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
     **The fix is five layers on the launch argv and two more over IPC, and NONE
     of them is redundant.** Layers one to four are below; the fifth is
     `--stream-lavf-o`, two paragraphs down, which the trailing token cannot
     reach. The two over IPC are D-SINK-16: the launch argv is the wrong
     place entirely for a player this shell ADOPTS rather than starts, and
     the maintainer raised that against the release that fixed the launch
     path. See the D-SINK-16 entry after this one. mpv applies
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
   - **The player we did not start** (D-SINK-16), which is the TLS peer entry's
     other half and was raised by the maintainer against the release that fixed
     the first half, on the verification request for that very commit. Every
     layer above lives on the LAUNCH argv, and an adopted player has no launch
     argv left to change: the detached player survives a shell restart by
     design, so after an upgrade the shell reattaches to a process started by
     the old code, and `apply_channel` then sends it new provider headers and
     new credentialed URLs. A live feed into an unauthenticated process, not
     stale state a user can restart away. We had recorded it ourselves as
     D-PLY-25 and described it too kindly, which is the lesson worth carrying:
     a residual in our own words can be the same defect, softened.
     Measured 2026-10-07 over a real IPC socket: a player launched the old way
     reads `tls-verify` False and fetches from a server nobody authenticated;
     `set_property tls-verify True` succeeds, reads back True, and the next
     load of the same URL fetches NOTHING -- attacker GETs 1 before and 0
     after, on the same process, with a plain-http control proving the migrated
     player still plays. A stale `stream-lavf-o` clears the same way.
     So: `apply_channel` asserts both properties before EVERY load, reads them
     BACK, and REFUSES to load when they are not safe -- and that last part is
     what separates it from the `pause`, `aid` and `sid` assertions beside it,
     which are best effort. Loading IS the act of handing over the credential,
     so a player that cannot be secured gets neither the URL nor the headers.
     Adoption migrates, reads back, and then RE-ESTABLISHES the current
     channel, because whether a stream already open picks the change up for its
     ongoing fetches is UNMEASURED and this must not depend on the answer; a
     player that cannot be made safe is stopped rather than fed. Cost: one
     visible rebuffer, once, on the first reattach after an upgrade.
     `player probe` is therefore no longer purely a read, and that is
     deliberate: a probe that found the exposure and walked past it would be
     worse than the side effect.
   - **The image decoder** (D-LOGO-11), which is the sink that is not a
     place a string goes but a place a NUMBER goes: a provider's logo is
     decoded inside the long-running shell, and the decoder's cost is
     quadratic in the dimensions the file's HEADER declares, which the bytes
     do not have to honour. A 304-byte progressive JPEG whose header says
     20000x20000 took a Qt `Image` declared exactly as the row slot is to
     840 MB; 555 bytes with three components, 1,239 MB; the 65500x65500 pair
     were refused by the allocator at a 2.5 GB address-space limit (and
     killed outright under a 1.5 GB memory scope). Measured on Qt 6.11.2,
     offscreen, with the cap around the Qt process only: the scope figures
     on 2026-10-09, the rlimit figures on 2026-10-11. Raised
     by the marketplace maintainer against the shipped 0.13.3.
     Qt's own allocation limit is NOT a bound here, and that is arithmetic:
     it is compared against `ceil(dim/8)^2 * 4`, the image already divided
     by libjpeg's largest scale denominator, and at the format's own maximum
     that is 8192 * 8192 * 4 = exactly the 256 MiB default. No JPEG the
     format can express can exceed it on this path, and it is unreachable
     BECAUSE `sourceSize` is set -- the option added to keep the decode cheap
     is the option that disarms the only bound Qt has. PNG, GIF and WEBP are
     refused by that same limit because their handlers decode full size and
     hand it the real number; JPEG is the one of the four the decoder can
     scale, which is the whole reason it is the one exposed -- and the bound
     covers all four anyway, because that asymmetry is upstream behaviour a
     dependency bump could end in silence.
     The bound lives in the HELPER (`write_logo`, `MAX_LOGO_SIDE = 4096`,
     `MAX_LOGO_PIXELS = 4194304`, `logo_dimensions` for all four types),
     refuses unless it can PROVE the file is within it, and the cached-file
     branch of `logos --fetch` proves a header before announcing a name,
     because the guide points an `Image` only at a name the helper announced
     -- FOR THE DIRECTORY IT ANNOUNCED IT FOR. That qualifier is the review's
     finding: `logoHave` used to be a bare set of names that survived a
     source switch while the directory under it changed, so the set is
     tagged with its directory (`Model.logoHaveSet(names, dir)`), derived
     through `Model.logoDirFor` at BOTH the binding and the tag (the first
     repair tagged with the cache directory and compared with the logos
     directory, and every slot was blank with 1,910 node checks green), and
     `Model.logoSlot` refuses a set for another directory. A byte cap
     (`MAX_LOGO_BYTES`) bounds the download and nothing the decoder does;
     the README used to present it as the protection.
     The gate observes the sink: `scripts/dev-harness/logo-scenario.sh
     check-tree` runs the shipping helper over a generated corpus and a QML
     `Image` probe under an address-space rlimit on the qml process alone
     (never a service-manager scope: the marketplace capability scanner
     reads that command's name as a capability, and a harness commit once
     turned the gate red with it while its own gate run, taken before `git
     add`, read clean). A skipped scenario is RED unless
     `LOGO_PREFLIGHT_SKIP_OK=1` says the machine cannot run it.
     The lesson (rule 15's shape, found by the parser lane): `MAX_LOGO_FILES`
     has the same property the byte cap had -- it bounds fetches per run, not
     the cache -- and is filed open as D-LOGO-12. A number that cannot fail
     for the thing it looks like it guards is the defect, whatever the number.
     **The same sink's other axis is what a PNG carries BESIDE its pixels**
     (D-LOGO-13, the maintainer's seventh finding, against 0.13.6 on #11315;
     fixed on `dev` 2026-10-15). zTXt, iTXt and iCCP are compressed, libpng
     inflates them while it reads the header whatever `sourceSize` says, and
     Qt keeps the text (`png_get_text` after `png_read_info` AND after
     `png_read_end`) and the profile. libpng 1.6.58's only ceiling is its
     compiled default, 8,000,000 bytes per chunk and 1,000 stored chunks per
     info struct, and Qt sets neither (read in the 6.11.2 and 1.6.58 sources
     and import tables, NOT measured, on purpose: the fix is judged by what it
     keeps and drops). So the helper caches a PNG only in a CANONICAL form,
     `canonical_png`: IHDR, PLTE, IDAT, IEND, and tRNS, gAMA, cHRM, sRGB at
     their spec lengths; everything else dropped; walked without inflating
     anything, every CRC checked, the IDAT bytes copied untouched, so the
     pixels are the provider's (observed: Qt draws both files identically).
     A file it cannot walk is refused (`logo_chunks`), and the cached-file
     branch announces a PNG only once it is canonical: rewritten in place
     (0600, atomically) or swept. JPEG, GIF and WEBP are left as they come:
     Qt reads no compressed metadata from any of them, so what it keeps is
     bounded by the file's own bytes. A picture already decoded by a running
     shell has paid; the restart is what clears it.
     **And a declared size is not the only number the decoder sizes from**
     (D-LOGO-14, the eighth finding, against 0.14.1 on #11892; fixed on
     `dev` 2026-10-16). Qt's GIF handler builds a ZERO logical screen from
     the first frame's left+width and top+height before it allocates, and
     the reader took each frame's size and ignored its offsets, so a 1x1
     frame at 8190,8190 under a 0x0 screen read as 1x1 and is an 8191x8191
     canvas, inside Qt's own limits. `_gif_dimensions` now returns the
     largest of the screen and every frame's right and bottom edge, and a
     zero screen or zero frame is unreadable, so refused. Rule 15 over the
     other three types, read in their sources and not run: none sizes from a
     field the reader does not read.
   - **The clipboard, as an INPUT that blocks** (D-CLIP-1). Every editable
     QtQuick `TextInput` subscribes to `QClipboard::dataChanged` at
     construction, and on the RELEASED Qt 6.11.2 that slot calls
     `QMimeData::text()`: on Wayland that is a synchronous read of the
     whole offer on the shell's main thread through a pipe with a 1 s
     per-read timeout, NO total byte limit and NO overall deadline, cached
     until the next offer. Any application's clipboard change is the
     trigger; no user action is needed. Measured 2026-10-11 on this machine
     with a throwaway client under the user's own compositor: one editable
     `TextField` grew by 238 MB within 600 ms of a foreign 100 MB
     `text/plain` offer; the same field `readOnly: true` grew by nothing; a
     window with no field created no pipe after the offer. Attributed by a gdb
     catchpoint on `pipe2`: `q_canPasteChanged -> QMimeData::text() ->
     QInternalMimeData::retrieveData`. Upstream added that read on
     2026-02-18 (`c82ef988`, in 6.11.2) and removed it on 2026-09-15
     (`7d0a433a`, after the cut), so the marketplace maintainer's "6.12
     path" had the versions inverted and the mechanism right. Raised on
     the verification request for 0.13.4, the sixth finding in five
     calendar days.
     `readOnly` is the one switch on the slot in every version, so the
     rule is: **while the plugin's form is open, no editable `TextInput`
     exists in the shell.** The form's fields are `readOnly: true`
     unconditionally; the plugin does the editing itself in
     `handleFormKey` over the model value (`Model.editInsert` and
     `Model.editDelete`, node-tested), and paste is the out-of-process path
     only: the helper's `clipboard` verb runs `wl-paste` as argv, reads at
     most 32 KiB (`MAX_CLIPBOARD_BYTES`, 8,192 characters at four bytes
     each) under a 5 s deadline, reaps the child even when the shell's
     watchdog SIGTERMs it, and prints one bounded reply, so the shell never
     holds more than that (the first version collected `wl-paste` whole in
     the shell and a user Ctrl+V over a 100 MB offer cost +298 MB, kept;
     measured, then closed). `readOnly` also closes the middle-click
     Selection paste, a second unbounded read on the same object. What it
     does NOT close, recorded rather than fixed: a left-button selection in
     a REVEALED URL field writes the raw URL to the PRIMARY selection
     (`mouseReleaseEvent` copies on every left release, no `readOnly`
     gate) -- user-initiated, pre-existing, and the password field is
     exempt because `copy()` is a no-op for `echoMode` Password. The
     stated loss: input-method composition (dead keys, CJK) does not reach
     a read-only field, so accents cannot be TYPED into the name field;
     ASCII typing and any paste are unaffected.
     The lesson, which is D-LOGO-11's again one layer up: the host kit's
     `qs.Ui.TextField` is exposed in every host form too, and a Qt
     subscription made at construction is a sink opened by an object's
     mere existence, not by anything it is asked to do. Reported upstream
     to Omarchy and Qt with the measurements.
   - **The helper's XML parser** (D-EPG-6, the ninth finding, against 0.14.1
     on #11892; fixed on `dev` 2026-10-16), which is D-LOGO-11's shape in
     the helper: a parser that EXPANDS is a decoder, and its cost is not its
     input. ElementTree expands the entities a document declares in its
     internal subset, `MAX_SOURCE_BYTES` bounds the bytes in and not the
     text out, and an element is released only once it is complete. XMLTV
     declares no entity (the common `<!DOCTYPE tv SYSTEM "xmltv.dtd">` has no
     subset and passes), so `EntityRefusingReader` reads the prolog with its
     own expat parser, refuses any entity declaration, general or parameter,
     as `bad_xml` (one sentence, no URL), and hands ElementTree nothing until
     that parser has reached the root's start tag; no external DTD is read.
     It is the helper's only markup parser; the search is in QA-RESULTS.
   When you add a sink, add it here.
6. Files the plugin writes: cache under `~/.cache/omarchy-iptv/sources/<key>/`,
   state at `~/.local/state/omarchy-iptv/state.json`, socket under
   `$XDG_RUNTIME_DIR/omarchy-iptv/`. Modes 0700 for directories, 0600 for files.
7. Performance budgets: the guide opens in under 150 ms with a 10,000 channel
   cache, typing stays responsive, and the helper parses 10,000 channels in
   under a second.
8. ASCII only in `.js`, `.mjs` and `.py` sources. Nerd Font glyphs belong in QML, by
   codepoint, verified present in the installed font.
9. Never wait for the host to echo your own write back before updating your
   own UI. The Omarchy shell publishes a plugin's `barConfig` one write
   behind, so a plugin never receives the echo of its own settings write, and
   `updateEntryInline` returning `false` means "already stored", not
   "failed". Apply your own write locally in the same turn, drop that
   override as soon as the host reports any other value so external changes
   win, and keep the echo path idempotent. See the last section of
   `docs/OMARCHY-PLUGIN-CONTRACT.md`.
   Upstream confirmed and fixed this on 2026-10-11 (omacom/omarchy#11852 ->
   #15082, awaiting review): a host carrying it ECHOES the write at once.
   The rule does not change -- the override is dropped on any value but the
   pre-write one, our own echo included, so both hosts read the same -- but
   the harness fake models only the old host until D-HOST-4 is done.
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
   reach, such as inside a QML component, lift it into the model and call it
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
15. When you fix a defect, FIND ITS SIBLINGS before you close it. Not the
   file you were in: every other place that does the same job, by the shape of
   the code and not by the name of the function. This project has now paid for
   the same omission three times, and the third was found by someone outside
   it.
   - F-RWD-22 softened an assertion in R10 that was asserting chance. Its
     twin in R11, one screen below, carried a comment saying the two were the
     same pair and kept the old assertion. Found when it flaked (F-RWD-26).
   - F-HARNESS-8 gave the scenario's own sweep a barrier because a transcript
     grepped straight back after a run can be short. The predicates in the
     same repository did the same read with no barrier. Found when it
     reddened the gate (F-HARNESS-15).
   - D-SINK-1 taught that the userinfo of a URL ends at the LAST `@`, and
     `redactUrls` and `validateSourceUrl` have cut it correctly ever since,
     with the lesson in a comment beside them. `hostPortOf` sat three
     thousand lines below with `[^@/?#]*@`, which cannot cross an at-sign,
     and put the password into the Sources row's host and default label. The
     marketplace maintainer found it in a shipped release (D-SINK-17), and
     1,890 node checks and 941 python tests were green: the defect was not
     missed by a weak check, it was never reached by one.
   The search is cheap and it is a GREP OVER SHAPE, which is the one job a
   grep is good at -- not "does this string appear", which rule 14 forbids as
   a criterion, but "where else does this pattern live". For a parser, the
   pattern; for a timing assumption, the other readers of that value; for a
   wrong default, the other places the default is taken. Write what you
   searched for in the write-up, including the places you cleared, so the
   next person inherits the search instead of repeating the defect.

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
Since D-REL-5 it also carries `missing-property` for every member of
`Model`: qmllint reads no ES module exports, so each `Model.X` in QML warns.
That lost the warning a MISTYPED member used to draw, so the gate runs
`scripts/check-model-members.py` over those lines and goes red on any member
`Model.mjs` does not export. Anything outside that baseline is a real finding.

Pure logic belongs in the model so it is unit-testable from node, not only
visible on screen. Since D-REL-5 (2026-10-12) the model is ES modules:
`Model.mjs` is a GENERATED aggregator that re-exports exactly the public
names, and the code lives in parts under `model/`, split by domain. The
marketplace's security scan refuses any non-executable file over 512 KiB
(`securityFileByteLimit` in its own scripts), and the single `Model.js`
crossed it in 0.13.5, which is why. `release.py check` holds every shipped
file under 448 KiB, executables included. Edit the part a declaration
belongs in, then `node scripts/split-model.mjs --relink` rewrites the
generated import and export lines and `--check`, which the gate runs, judges
the tree; `docs/ARCHITECTURE.md` section 9 holds the model's coding rules and
how a new public name or a new part is added.
Two of those rules are
measured hazards under Quickshell that the script refuses: a part may not
read another part's declaration in a top-level initializer (it reads
`undefined`, silently, across an import cycle), and a `var` is declared
above the first function in its part that names it.
The helper went the same way for the same reason (D-REL-7, decided
2026-10-15 and cut from 0.14.2's one-file helper on 2026-10-17,
`docs/HELPER-SPLIT.md`): `bin/omarchy-iptv` is a stub that makes the process
non-dumpable and then compiles `bin/helper/NN-*.py`, in the order of its
`HELPER_PARTS`, into its OWN namespace, so the parts behave as the one file
they were cut from -- one set of globals, one module a test patches. Edit the
part a function belongs in. `scripts/split-helper.py --check`, which the gate
runs, proves that the loader is exactly what the list generates and sits
directly after the shield; that every part carries its header, compiles, and
matches its entry (the length and CRC-32 of its text with CRLF read as LF);
and that `bin/helper/` holds nothing else except names starting with `.`.
Each entry is a part's (name, length, crc32), so EVERY edit to a part changes
the stub: run `scripts/split-helper.py --seal` after any part edit. Until you
do, the stub refuses that part with `helper_damaged` and every helper test
goes red, not only `--check`. Two lanes that edit the same part or adjacent
parts conflict on the stub's entries; resolve that by taking either side and
running `--seal`, never by editing an entry by hand. `release.py` proves the
list and the allowlist agree. Anything that
needs the helper's FILES reads the list from the stub
(`scripts/helper_files.py`, `qa_helper_parts`); a copy of the stub alone is
a helper that cannot start.
A rule implemented in both JavaScript and Python gets one
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
6b. A nested cage gets a PRIVATE D-Bus: a `dbus-daemon` started from a config
   with NO service directories (the shape `tests/a11y/run_private_bus.py`
   uses), never plain `dbus-run-session`. Its standard service directories let
   D-Bus activation start desktop portals inside the nested session, and on
   2026-10-13 a lane's throwaway rig did exactly that: two portal instances
   crashed, the host posted a crash notification on the user's desktop, and the
   user's REAL `xdg-document-portal.service` exited with status 21 the second
   the rig started and stayed failed (F-M3-21). A rig a lane writes for itself
   is held to this rule as much as the harness is; the harness's own scripts
   already never use `dbus-run-session`.
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
