# Omarchy IPTV

A native Omarchy shell plugin: a keyboard-first live TV guide with EPG,
favorites, source management, and mpv playback. One plugin id,
`io.github.rmcdavid.iptv`, with three kinds: `bar-widget`, `overlay`,
`service`. It runs inside the single long-running `omarchy-shell`
Quickshell process. Released through v0.7.1.

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
- A release is: bump `manifest.json` and `CHANGELOG.md` on `dev`, green
  gate, `scripts/release.py build --gate-already-green`, then push `dev`,
  `main` and the tag. While a marketplace review is open, `main` moves only
  when the reviewer asks for a new commit.

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
   registers as failed unlock attempts.

## Commits

Small and logical, present tense, explaining why rather than restating the
diff. Never commit a red `check.sh`.
