# M2-04 logos: the privacy ruling

Product owner delegated this ruling on 2026-09-23. It is made against measured
data rather than convention, and the measurement changed the answer.

## What the data says, and it is not what the roadmap assumed

`docs/ROADMAP-PROPOSED.md` reframed the logo design around coverage: on the
3,335-channel **provider** list, 27 per cent of channels carry a `tvg-logo` and
coverage by decile in playlist order is 99, 67, 38, 14, 3, 0, 0, 0, 0, 0 — "the
design problem is a cliff, not a placeholder majority".

Measured on the list actually configured here (1,471 channels, the free
iptv-org playlist), the cliff is absent:

| | provider list | this list |
|---|---|---|
| channels with a logo | 27% | **98%** (1,445 of 1,471) |
| coverage by decile | 99, 67, 38, 14, 3, 0, 0, 0, 0, 0 | **98, 99, 99, 99, 97, 99, 100, 98, 97, 95** |
| first 200 rows | 199 of 200 | 196 of 200 |

So the placeholder design problem is a property of one provider's data, not of
the feature. **Neither list should be treated as the general case** — the
feature has to look right at 27 per cent and at 98 per cent.

## The measurement that actually decides the ruling

Nobody had counted the hosts. On this list:

| | |
|---|---|
| distinct logo hosts | **63** |
| `i.imgur.com` | 999 channels |
| `upload.wikimedia.org` | 170 |
| `images.pluto.tv` | 116 |
| schemes | `https` on 1,445 of 1,445 |

Turning logos on tells **sixty-three third parties** which channels this user
has, and hands `i.imgur.com` alone a request pattern covering two thirds of the
list. That is a bigger disclosure than the plugin makes anywhere else, and it is
made to hosts neither we nor the user chose — the playlist author did.

## The ruling

1. **Off by default.** The setting exists; it starts `false`. No third-party
   host is contacted until the user turns it on. This is the whole ruling in one
   line and the rest is detail.
2. **Only hosts the playlist itself names.** The plugin never substitutes a
   logo aggregator, CDN or fallback of its own choosing. If a channel has no
   `tvg-logo`, it has no logo.
3. **`https` only.** Costs nothing on this data (1,445 of 1,445 already) and an
   `http` logo fetch would put the request in cleartext for anyone on the path.
4. **No credentials, ever.** Logo requests carry none of the playlist's headers,
   query string or auth. A provider whose logos sit on the same host as its
   playlist must not receive the subscription credentials as a side effect of a
   picture. This is the one rule whose absence would be a security defect rather
   than a privacy choice.
5. **Content-type allowlist** (`image/png`, `image/jpeg`, `image/webp`,
   `image/gif`), a per-file byte cap and a total cap, per-source directory under
   the cache at 0700 with files at 0600 — the existing cache rules, unchanged.
6. **The user is told the number before they choose.** A generic "logos may
   contact third parties" is not informed consent when the real answer is
   countable. The plugin can survey the configured playlist without making a
   single request, and the setting must say what it found: *"turning this on
   will contact 63 hosts, including i.imgur.com (999 channels)"*.

Rule 6 is the part this ruling adds to the plan rather than merely approving.
It is implemented as `omarchy-iptv logos --survey`, which reads the cache and
contacts nothing.

## What is NOT ruled here

The fetch itself, the row design at both coverage extremes, and the open-budget
guard. Those are M2-04-02 through M2-04-07 and they are unchanged by this
ruling, except that the row design now has two coverage cases to satisfy rather
than one.
