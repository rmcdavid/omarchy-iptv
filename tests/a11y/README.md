# tests/a11y -- verifying accessibility by observation

Accessibility on this project was graded for months by searching our own source
for the properties we had just written. Four acceptance criteria said, in as
many words, `grep`. Such a test cannot go red, and nobody noticed, because
nothing had ever looked at what the code actually publishes.

This directory is the replacement, and it has two halves with very different
costs and guarantees.

## The two halves

**The fidelity guard** (`fidelity.py`, `qmlscan.py`, `test_fidelity.py`,
`mutate_guard.py`) is pure text. It needs no display, no D-Bus and no Qt, runs
in about seven seconds, and is green on shipping code. **It is in
`scripts/check.sh`** and runs on every commit.

It exists because the other half grades a *generated copy* of `Guide.qml`, and
a copy can drift from what ships. Every accessibility-bearing declaration must
survive the transform intact, the host UI kit must be the kit that ships except
for a declared patch set, and any surface that declares accessibility and is
graded by nobody is named on every run.

**The bus half** (`check_bus.py` and everything it loads) starts a hidden Qt
window, lets Qt's AT-SPI bridge publish a real accessibility tree, and walks it
from a stdlib-only D-Bus client. It needs a graphical session, and **it is not
in the gate** (PLAN-NEXT decision 9): its baseline on shipping code is
deliberately RED, and those failures are real defects.

## Running it

```bash
./scripts/a11y-probe.sh
```

That builds the tree, refuses to measure if the copy has drifted, and walks the
bus. **A red run is the expected result.** Compare against the baseline in
`docs/QA-A11Y.md`, not against zero.

## What a PASS here does and does not mean

It means the markup composes and publishes correctly **in a window the user
never sees**. It does *not* mean any of it reaches a screen reader. On this
desktop none of it does: no window Quickshell creates publishes an
accessibility tree at all (D-GS-3, quickshell issue 1144), so the shipping
guide announces nothing to anything today. This harness proves our side would
be correct if the host were. Those are different claims and nothing here may
blur them.

## The pieces

| File | Does |
|---|---|
| `make_tree.py` | stage 1: copies the host kit, transforms `Guide.qml` into `GuideProbe.qml` |
| `make_hosts.py` | stage 2: the QML that drives each scenario, plus `BarWidget.qml` copied unedited |
| `fidelity.py` | the guard. `guard_tree()` is the one call the harness gates itself on |
| `check_bus.py` | the scenarios and their assertions |
| `walk.py`, `atspi.py`, `dbusmin.py`, `settle.py` | the bus client and the bounded settle poll |
| `mutate_bus.py`, `mutate_guard.py` | break one thing on purpose and prove a check goes red (rule 11) |
| `selftest_settle.py` | proves the settle poll settles rather than sleeping |

## Two rules for anyone working here

**The generated tree is a build artifact and never lives in the repo.** It
defaults to a temporary directory; set `A11Y_TREE` to keep one for inspection.
It must not be shared between concurrent runs: a shared directory written by
two lanes at once already produced one reading that was green only because a
mutation had been overwritten (CLAUDE.md rule 4b).

**Absence of a secret is not a pass.** A proposed fix for the credential
exposure once turned this harness green by silently overwriting the user's
stored credentials with the masked rendering. Any check that hunts for a leak
must also assert the data is undamaged: digest, length and content equal before
and after.
