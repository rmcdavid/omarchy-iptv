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
7. **A logo's declared dimensions are bounded, for all four allowed types.**
   Added 2026-10-11 for D-LOGO-11, in the shape of the rules above. No side
   over 4096 px and no more than 4,194,304 px in all, read from the header
   before a byte reaches the disk, and a header that cannot be read is a
   refusal rather than a pass. Rule 5's per-file byte cap bounds the
   download and nothing the decoder does: the decoder's cost is quadratic in
   a number the header states and the bytes need not honour, and a 304-byte
   progressive JPEG whose header says 20000x20000 took a Qt process standing
   in for the shell to 840 MB of resident memory -- the lead's probe, which
   is the qml runtime drawing one `Image` declared exactly as the guide's row
   slot declares it and nothing else (measured by the lead on 2026-10-09,
   Qt 6.11.2 offscreen, `docs/QA-RESULTS.md` under the fifth maintainer
   finding; reproduced by the harness lane on 2026-10-11 at 839 MB under an
   address-space rlimit, `scripts/dev-harness/spikes/logo-decode-bomb/`).
   The shell itself was never fed one, deliberately; that it would allocate
   the same is inference from the probe being the slot's own declaration,
   and it is stated as inference. Qt's own allocation limit does not refuse
   a JPEG on that path, measured by bracketing it: it is compared against
   the image already divided by libjpeg's largest scale denominator, and the
   format's largest dimension lands exactly on the default limit. The numbers are the
   cost at the bound: a 4:4:4 progressive JPEG of 4,194,304 px holds
   25,165,824 bytes of coefficients, 24 MiB, the same order as the 23.8 MiB
   Qt was already willing to allocate for a logo, and a 1920x1080 provider
   banner passes (called on the shipping `logo_within_bounds`, 2026-10-11).
   The side cap is the second half because area alone admits 65535x64. It
   covers PNG, GIF and WEBP although only JPEG is exposed today, because that
   asymmetry is Qt's and a dependency bump could end it in silence. The cache
   written before this rule is checked by the same parser on the next fetch
   and a file that fails -- over the bound, header unreadable, bytes that
   are none of the four types, or over the byte cap with its header past the
   first read -- is removed rather than announced, since the
   guide draws only a name the helper announced, AND ONLY FOR THE DIRECTORY
   IT ANNOUNCED IT FOR. That second clause is the review's blocker and it is
   part of the rule: a name is a hash of a logo URL, two sources that share a
   provider share every URL, so a set of names announced for source A would
   resolve to files in source B's directory that no fetch has looked at. The
   announced set therefore carries the cache directory it was announced for,
   the guide draws nothing from a set tagged for any other directory or from
   the old untagged shape, an empty summary replaces the set rather than
   being ignored, a source switch clears it, and a fetch still running for
   another directory is stopped and started again for the current one
   (`Model.logoHaveSet`, `logoSlot`, `logoHaveMerge`, `logoSummaryNames`,
   `logoFetchPlan`; `Service.qml` `clearSourceData` and `fetchLogos`; called
   by the seven "D-LOGO-11 blocker" checks in `tests/Model.test.js` plus two re-shaped older ones (the D-LOGO-8 call-site inventory and the M2-04 defensive-report check), which together
   read 9 failures against the Model.js and Service.qml of 995c6be and 0
   against the fix, lane commit 1a05214).

   Annotation, not a rewrite: rule 5's "a total cap" is `MAX_LOGO_FILES *
   MAX_LOGO_BYTES`, and measured on 2026-10-11 it is not a cap on the cache,
   because the file count bounds fetches per run and not files on disk
   (D-LOGO-12, open on the board). Rule 5 stands as the owner wrote it until
   the owner rules on that.

Rule 6 is the part this ruling adds to the plan rather than merely approving.
It is implemented as `omarchy-iptv logos --survey`, which reads the cache and
contacts nothing.

## Built so far (2026-09-23)

`omarchy-iptv logos` surveys, and `--fetch` downloads under every guard above.
The fetch is deliberately **not** `read_http_source`: that path turns userinfo
into an `Authorization` header, which is correct for a playlist and is the one
thing a logo request must never do. `fetch_logo` refuses a URL carrying
userinfo rather than stripping it, refuses anything that is not `https`,
refuses a content type outside the allowlist, and caps each file at 256 KB.

Files are named by `fnv1a32` of the URL, never from its path: a provider path
can carry a channel name, a subscriber id or a token, and a path built from an
untrusted string is also how a traversal escapes the cache. Written 0600 into a
0700 `logos/` directory beside the rest of that source's cache.

Fourteen tests. The one worth naming asserts, over the parsed AST rather than
the source text, that `fetch_logo` never reaches `Authorization`, `base64`,
`split_userinfo` or `read_http_source` -- a plain substring search matched this
file's own explanation of why it must not.

## The guide half, built 2026-09-23

Setting and rendering shipped together, as this document required.

**The setting** is `showLogos`, declared in the manifest, defaulting to
`false`, and read by `Model.optInSetting` rather than `Model.boolSetting`.
That distinction is the ruling's first line in code. `boolSetting` is
"anything but `false` and the string `"false"` means on", which is right for
`showChannelName` -- a junk value in a hand-edited `shell.json` leaves a label
visible. Applied here the same rule would let `showLogos: 0`,
`showLogos: "no"` and `showLogos: null` each contact sixty-three hosts. A
privacy switch whose unknown values mean ON is not off by default; it is off
by default only for people whose config file happens to be well formed.
`optInSetting` accepts `true` and `"true"` and nothing else.

**The consent** is `g` on the Sources screen. The footer hint reads `g logos
on` or `g logos off`, naming the direction, so nobody has to press it to find
out -- and finding out means contacting third parties. Turning it ON opens a
confirm screen carrying the count (rule 6); turning it OFF is immediate,
because it discloses nothing and a dialog in front of the safe direction
teaches people to dismiss dialogs. The confirm button says **Turn on**, not
OK: the dialog is a disclosure notice, and OK on a disclosure notice is how
people agree to things they have not read.

Measured live on a 100-channel fixture at the provider's 27 per cent:

```
Turning logos on will contact 1 host, the busiest being logos.example.test (27 channels).
27 of 100 channels carry a logo. Each one is fetched once and cached.
No credentials are ever sent with a logo request.
```

**The row** puts the logo after the star and before the name: a picture is a
stronger signal than a word, so it must not sit where the eye is looking for
the name, and the star stays at the left edge where a favourite is findable by
running down the column. A channel with no logo gets **blank space, never a
drawn placeholder** -- the codebase already settled this for the channel
number ("a placeholder in a column reads as a value; the absence is the
information"), and at 27 per cent coverage the other choice is a list of empty
boxes. The column itself is absent when no row on screen offers a logo, the
same rule the number column follows.

Verified live at both extremes the ruling demands: 27 per cent front-loaded
and 98 per cent even, both `logoColumn: true`, `logoWidth: 22`.

## Three things the build changed about the fetch

**The extension is gone.** Files are named `fnv1a32(url)` and nothing else.
The guide has to turn a channel's logo URL into a file name, and with an
extension implied by the content type it would have had to read an index --
a second source of truth and a JSON parse inside the 150 ms open budget.
Measured on Qt 6.11.2 first: QML's `Image` loads a local file by CONTENT, not
by name. An extension-less PNG, GIF and JPEG all reach `Image.Ready` at their
true size, and so does a PNG named `.txt`. The extension was never a gate.

**The magic bytes are checked.** Since the extension gated nothing, the
server's `Content-Type` was the only thing standing between a payload and
Qt's decoders -- and a file whose bytes are SVG renders as SVG whatever it is
called, through a much larger surface than a bitmap decoder. `write_logo` now
refuses bytes that do not begin the way the claimed type says, before anything
touches the disk.

**A cached logo is not fetched again.** The service runs a fetch whenever the
channel cache loads, so without this the shell re-downloaded every logo on
every start: 1,445 requests to sixty-three third parties per launch, which is
precisely the disclosure this ruling exists to bound. Measured after the fix,
10,000 channels with every logo cached: `fetched=0 cached=9820 failed=0`, zero
hosts contacted, 0.49 s.

## Two defects the build found, both live

**The consent text was a credential sink.** The survey reported the host of
`https://user:pass@provider.test/logo.png` as `user:pass@provider.test` -- so
the dialog the user reads before consenting would have printed their password,
and it promised a fetch that `fetch_logo` refuses anyway. Caught by the shared
fixture on its first run, before the screen was ever drawn. Userinfo now makes
the answer "" and counts as refused, in both implementations. The port is
stripped too: the sentence counts PARTIES, and `cdn.test` and `cdn.test:8443`
are one party.

**A missing logo file filled the journal.** Pointing a QML `Image` at a file
that is not there is not a blank slot: Qt logs `Cannot open` for every
attempt, so one dead logo host produces a warning per row per scroll. Seen
live with 27 URLs and 26 files. The helper's fetch now reports the names ON
DISK (hashes only, no URLs -- that stdout is a sink too) and a row draws an
`Image` only for a name in that set. Re-measured with one file deliberately
missing and the whole list scrolled: **0 warnings**.

## Open budget

150 ms with a 10,000 channel cache. Measured in the harness, seven opens each,
the list forced to lay out before the clock stops:

| | ms |
|---|---|
| logos off (the default) | 68, 16, 20, 20, 14, 14, 14 |
| logos on, 10,000 logos cached | 26, 37, 22, 21, 20, 12, 12 |

The list instantiates only its visible delegates plus `cacheBuffer`, so the
column costs about twenty image loads and not ten thousand; each is
`asynchronous`, with `sourceSize` capped at twice the slot so a 256 KB image is
not decoded at full size to be drawn at 22 px.

That last sentence is true of a well-formed image and was the whole exposure
for a malformed one (D-LOGO-11, 2026-10-09): `sourceSize` lets libjpeg scale
during decode, which is what makes a JPEG cheap to draw small, and it is also
what Qt's allocation limit is then measured against, so the limit never sees
the full-resolution coefficient buffers a progressive JPEG allocates from the
header's numbers. The bound is rule 7 above, in the helper, not a change to
this slot.

## Seven defects the 0.7.9 preflight found, all in this feature

The guide half was committed with eleven mutation proofs and a live pass at
both coverage extremes. An adversarial review of the release candidate found
**seven defects in it anyway**, two of them blockers, and the release was held.

Two broke this ruling directly:

- **Rule 3 held for one hop only.** `fetch_logo` validated the scheme it was
  handed and then used urllib's default opener, which follows a 302 to
  `http://` or `ftp://`. The consent sentence rule 6 composes is a promise
  about which hosts are contacted, and a redirect broke it silently.
  `logo_opener` now enforces https and refuses userinfo on every hop.
- **Rule 1's switch did not stay thrown.** Turning logos off, then editing a
  source URL, wrote `showLogos: true` back to disk, because the bar entry is
  composed from a `barConfig` the host publishes one write behind. Off by
  default means nothing if off does not persist.

One was a privacy defect this ruling did not anticipate at all: **a removed
source kept its logo cache forever**, with filenames that re-identify the
channels that source carried. The ruling reasoned carefully about what
fetching logos discloses and not at all about what the cache leaves behind
when the user withdraws consent. Add that to the list of things a feature
like this has to answer: not only *who is contacted* but *what survives the
user changing their mind*.

The rest are in `docs/QA-RESULTS.md`.

The honest reading of this is not that the mutation proofs were wrong. They
were answering a narrower question than they were being read as answering: a
mutation proof says a check can see the decision it was written for, and says
nothing about decisions nobody wrote a check for. Enumerating those is what an
adversarial reader does and the author cannot.

## Still not built

The fetch is best-effort and reports nothing to the user: the pictures
appearing is the report. Whether a persistent failure deserves a notice is
open, and it is a product question, not an implementation one.

## What is NOT ruled here

The fetch itself, the row design at both coverage extremes, and the open-budget
guard. Those are M2-04-02 through M2-04-07 and they are unchanged by this
ruling, except that the row design now has two coverage cases to satisfy rather
than one.
