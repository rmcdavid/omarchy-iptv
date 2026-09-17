# Marketplace submission, drafted for review

**Nothing has been filed.** This is the text that would go into the GitHub
issue at `omacom/omarchy-plugin-marketplace` using the `submit-plugin.yml`
template. Read it, change anything, then say go.

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
