# QA assets — public, legal test sources (verified 2026-09-12 from this machine)

Use these for unit fixtures, live-shell QA, and the performance gate. None are
bundled with the plugin; they are test inputs only.

| Purpose | URL | Notes |
|---|---|---|
| 10k-channel performance fixture | https://iptv-org.github.io/iptv/index.m3u | 11,041 `#EXTINF` entries, `audio/x-mpegurl`. Many streams are dead by design; good for timeout/failure paths. |
| Realistic mid-size playlist | https://iptv-org.github.io/iptv/countries/us.m3u | 1,475 entries; attributes `tvg-id`, `tvg-logo`, `group-title` (semicolon-joined multi-groups like `Animation;Kids;Religious`). |
| Small playlist | https://iptv-org.github.io/iptv/categories/news.m3u | Quick smoke tests. |
| XMLTV EPG, gzip | https://i.mjh.nz/PlutoTV/us.xml.gz | Pluto TV US guide, ~950 KB gz (plain .xml also served at the same path without .gz). Channel ids are 24-hex Pluto ids (e.g. `673247127d5da5000817b4d6`), display-name and icon present. Channel ids follow mjh's scheme, so EPG matching against iptv-org `tvg-id` values will be partial; use it to test parsing, gzip, timezones, and the "no EPG for this channel" path. |
| XMLTV EPG, gzip | https://i.mjh.nz/SamsungTVPlus/us.xml.gz | ~500 KB gz. Same notes as above. |

Playlist format sample (iptv-org):

```
#EXTM3U
#EXTINF:-1 tvg-id="00sReplay.us@SD" tvg-logo="https://images.pluto.tv/channels/.../colorLogoPNG.png" group-title="Movies",00s Replay
https://jmp2.uk/plu-62ba60f059624e000781c436.m3u8
```

Guidance:
- Unit tests must use local fixture files under `tests/fixtures/`, never the network.
- Live QA: configure `playlistUrl` to the US list first (fast), then the index for the 10k gate.
- Observed quirk to cover: `group-title` may contain several groups separated by `;`. Product call: index the channel under its FIRST group for display, keep the full string searchable.
- The `#EXTVLCOPT:http-user-agent=` / `#KODIPROP:inputstream...` lines do not appear in iptv-org lists; add synthetic fixtures for them.
