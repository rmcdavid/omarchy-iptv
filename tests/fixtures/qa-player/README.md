# tests/fixtures/qa-player/

Fixtures for the M2-02 detached-player pass (`docs/QA-PLAYER.md` section 8.0).

- `qa-player.m3u` - the playlist. Nine channels, described in the file's own
  header comment. Every URL points at `127.0.0.1`; nothing here reaches the
  network.
- `make-media.sh` - regenerates `test.ts` (900 s) and `short.ts` (3 s) with
  ffmpeg. The media files are **not** committed (see `.gitignore`); run the
  script once before a pass, or let `scripts/qa-player-scenarios.sh` do it.

The privacy needles carried by `qa.sentinel` and `qa.sentinel-dead`, used
verbatim by every grep in `docs/QA-PLAYER.md` section 5:

    qa-user  qa-secret  qa-token-XYZ  qa-ua-SENTINEL  qa-ref-SENTINEL

`qa.dead` and `qa.sentinel-dead` point at port 9 (discard), which refuses
immediately, so a first-load failure lands well inside the 3 s window.
