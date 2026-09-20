# Marketplace submission, drafted for review

**FILED 2026-09-17:** https://github.com/omacom/omarchy-plugin-marketplace/issues/7374

This is the text that went in, kept so the submission can be compared against
what was intended. It follows the `submit-plugin.yml` template, whose real
fields were read from the repository rather than from the rendered page.

**A correction to what this file said on the day.** It recorded that the
`submission` label had not taken, because our own `gh` call could not set a
label on another organisation's repository. That was true of our call and
false about the outcome: the marketplace's own automation applied `submission`
four seconds after the issue opened, and validation ran off it. Nothing needed
watching. The lesson is the ordinary one -- our command failing to do a thing
is not evidence the thing did not happen -- and the timeline was one API call
away the whole time.

The template's fields were read from the repository rather than from the
rendered page, so the field names and validation below are the real ones.

---

## Field: Repository URL (required)

    https://github.com/rmcdavid/omarchy-iptv

## Field: Category (required, one of nine)

**Desktop**

The other candidates were Widgets and Productivity. Desktop fits best: the
plugin's main surface is a full-screen overlay, and it ships a bar widget and a
background service rather than being only a widget.

## Field: Tags (required, one to three; MORE THAN THREE IS REJECTED)

**Media**, **Quickshell**, **Bar**

Media is what it is. Quickshell is what it is built on and what a person
filtering by stack would search. Bar is the third because the plugin genuinely
ships a bar widget with its own states, not because a third tag was available.
Hyprland was the runner-up and was dropped: the guide and the player work
without any Hyprland-specific feature, and only picture in picture needs it.

## Field: Suggest a missing tag (optional)

Left blank. The nine categories and thirteen tags cover this.

## Field: Maintainer notes (optional, free text)

> Requires `mpv` 0.41 or newer on PATH, which Omarchy installs by default, and
> `python3`, which Omarchy already depends on through `uwsm`. No third-party
> Python packages: the helper is standard library only.
>
> The plugin ships no content. You bring your own M3U playlist or Xtream login.
> Playlist addresses usually carry provider credentials, so the plugin redacts
> URLs to scheme and host at every place text is emitted, never puts a stream
> address on a command line, and passes it to mpv over a private socket in
> `$XDG_RUNTIME_DIR`.
>
> Files it writes, all under the user's own directories and none of them
> configuration: a cache under `~/.cache/omarchy-iptv/`, state at
> `~/.local/state/omarchy-iptv/state.json`, and a socket under
> `$XDG_RUNTIME_DIR/omarchy-iptv/`. Directories 0700, files 0600. Settings live
> on the bar entry in `shell.json` through the documented plugin API.
>
> Two known limitations, both reported upstream and neither fixable from a
> plugin. Nothing the plugin declares reaches assistive technology, because no
> Quickshell window publishes an accessibility tree
> (quickshell-mirror/quickshell#1144). And picture in picture needs Hyprland's
> Lua config provider, which is the Omarchy default; elsewhere it reports
> itself unavailable rather than half working.

## Field: Submission checklist (all five required)

| Item | Status |
|---|---|
| The repository is public and contains installation and removal instructions | **Yes.** `README.md` has an Install section and an Uninstall section, and the Uninstall section names all three directories the plugin writes |
| I have documented the plugin license and any external dependencies | **Yes.** MIT, as a `LICENSE` file and in `manifest.json`. Dependencies under Requirements: mpv 0.41+ and python3, with a note that the helper uses the standard library only |
| I confirm that I own or have permission to submit this plugin and its preview assets | **Yes.** The preview is a capture of the plugin itself showing a public channel list |
| The plugin does not overwrite user configuration without explicit consent | **Yes**, and worth stating precisely rather than ticking. The only file it writes that a user would call configuration is its own settings block on its own bar entry in `shell.json`, through the host's documented `updateEntryInline` API, and only when the user changes a setting. Everything else it writes is cache, state or a socket |
| I understand that approval is for listing and is not a security review | **Yes** |

## Preview asset

`preview.png` in the repository root, 960x620, the guide mid-search.

It was cropped to the card's own border, verified by checking that all four
edges of the crop are the border colour, so no desktop, no terminal, no window
titles and no other application appear. The channel names are from the public
iptv-org list. No source address and no credential is visible anywhere in it.

## Title

    [Plugin]: IPTV -- a keyboard-first live TV guide with mpv playback

---

## 2026-09-18: approval cannot cover a moving branch

Both bots passed at `e5f68c0`, the HEAD when we filed. Validation was green
and the security baseline returned **zero findings**. Nine hours later a
marketplace collaborator applied `needs-fixes` and wrote:

> The validated marketplace/security commit is `e5f68c0...`, but the current
> default-branch HEAD is `13ede1f...`. Approval cannot cover code outside the
> immutable validated revision.

Nothing was wrong with the plugin. We had moved HEAD after the measurement, by
pushing the docs commit that recorded the filing. Approval binds to an exact
commit, so a moved branch invalidates the scan that approval would rest on.

**The standing rule this forces: `main` is frozen while a submission is
pending.** Validation resolves the commit by inspecting the repository live and
taking default-branch HEAD at scan time -- confirmed by reading their
`validate-submission.mjs`, which passes the issue's creation timestamp only to
the format parser and never to commit resolution. So every push re-staleness
the scan, and the loop can repeat forever. Work continues on branches; nothing
lands on `main` until the listing is approved.

**Re-triggering is an issue edit, not a comment.** Their automation runs on
`issues: [opened, edited, reopened, labeled, unlabeled]`. A comment fires a
different event and wakes nothing, so replying to the maintainer would have
looked like an answer and done nothing at all. Their guide says it plainly:
"Editing the issue runs submission detection again."

### The two capability hits, and why we reworded rather than argued

The baseline came back `review-required` rather than `passed`. Their rule is
`findings.length ? "needs-fixes" : capabilities.length ? "review-required" :
"passed"`, and our findings were empty, so the two capabilities were the whole
difference. Both were message strings in developer tooling:

| Evidence | What it actually is |
|---|---|
| `scripts/check.sh:122` | the argument to `bad()`, which is `printf 'FAIL %s\n' "$*"` -- an error telling a developer which package provides qmllint |
| `scripts/qa-player-scenarios.sh:396` | the argument to `note()`, which is `printf 'NOTE: %s\n' "$*"` -- prose explaining why that case uses a PATH-shadowed stub *instead of* removing mpv |

Neither is executed; neither ships in the plugin; neither script is reachable
from `manifest.json`. The scanner reads a shell file as a command sequence and
cannot tell a quoted message from a real invocation.

We reworded both rather than asking a maintainer to accept a capability the
plugin does not have. The wording keeps every piece of real information -- a
developer still learns that qmllint ships in `qt6-declarative`, a QA reader
still learns why the missing-mpv case needs a stub -- and each site carries a
comment saying why the phrasing is load-bearing, so it does not drift back.
The change is disclosed in the issue rather than made quietly.

That the rewording is legitimate rather than evasion rests on something in
their own detector: its privilege matcher already strips negated forms of the
elevation verb -- the "no X", "does not use X" and "X is not required" shapes
are all removed before the test runs. Its authors clearly intend prose not to
read as capability. Our phrasing simply was not a shape it recognised. The capability label the marketplace prints for us -- "The plugin
can install, upgrade, or remove software outside its own checkout" -- is
untrue of this plugin, and the honest fix is to stop asserting it.

**Still unguarded.** Nothing checks that these two strings stay reworded. A
package-install command written into a future message string would silently
drop a listed plugin back to `review-required` on the next update scan, and the
comments at each site are a name, not a call -- exactly the join CLAUDE.md rule
13 is about. A check belongs in `check.sh`; it is not written yet.

Note that this file keeps its own prose clear of the literal tokens it
describes. Markdown prose appears not to be read as commands -- 24 such lines
sat in `docs/` at `e5f68c0` and the scan reported only the one in a shell
script -- but that is an inference from one observation, and there is no reason
to rest a re-scan on it when a rephrasing costs nothing.
