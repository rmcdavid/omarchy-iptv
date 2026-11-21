# A part of bin/omarchy-iptv (D-REL-7), not a module: the helper compiles
# this file into its own namespace in the order its HELPER_PARTS lists, so
# a part sees every name the parts before it define. Run the helper.
from __future__ import annotations
# --------------------------------------------------------------- player
# The detached player (ARCHITECTURE-PLAYER.md (dev branch)). mpv runs as a setsid'd
# grandchild of this helper, reparented to the session subreaper, so it
# outlives every shell restart and is still reaped at logout by the
# compositor's own cgroup. The shell observes it over mpv's JSON IPC socket.
#
# Nothing channel-specific is ever on mpv's command line: the URL, the headers
# and the title travel over the 0600 socket instead (S-03, requirement 9).
# Every verb is idempotent, serialised by one flock with an inode re-check,
# and ordered by the caller's --seq intent number rather than by the order the
# kernel happens to grant the lock in.

PLAYER_LOCK_FILE = "player.lock"
PLAYER_STASH_SCHEMA = 1
# Two sibling top-level user-data nodes (4.6), probe-verified on mpv 0.41: a
# second client reads back the identical object, the top level is not
# writable, and `del_property` is not a command ("invalid parameter"). [The
# `del` input command DOES remove a sub-path on mpv 0.41.0 -- `success`, then
# `property not found`; `error running command` on an absent one -- measured
# 2026-11-02 by lane-sk72; nothing here uses it.] The record dies with the
# process it describes, which is exactly why it is not a file on disk.
USER_DATA_STASH = "user-data/omarchy-iptv"
USER_DATA_OWNER = "user-data/omarchy-iptv-owner"
# M5-01 live rewind (M5-01-LIVE-REWIND.md 2.2, dev branch): the third sibling node,
# the zero point "behind live" is measured from. Keyed by the stash's
# `entryId`, so a zap -- which changes the entry id -- invalidates it by
# construction, and a shell restart recovers it from the player the way
# pause state is recovered today. Written lazily by `status`, `pause` and
# `seek`, whichever first sees a numeric `time-pos` for the current entry;
# `probe` reads it and never writes (the probe is side-effect-free).
USER_DATA_REWIND = "user-data/omarchy-iptv-rewind"
REWIND_SCHEMA = 1
# D-SINK-72 (lane-sk72, 2026-11-02): one more sibling -- beside the stash,
# the owner claim, the rewind zero point and the shell's picture-in-picture
# snapshot (user-data/omarchy-iptv-pip, Model.PIP_SNAPSHOT_KEY) -- the fact
# that a probe changed this player's TLS settings in place, kept ON THE
# PLAYER so that it outlives the shell that learned it. Set by migrate_tls
# when it has to act, read by every later probe (whose `migrated` it keeps
# true), and cleared -- set to anything but the word -- only by
# apply_channel's own load, the one act that re-establishes the connection
# the migration could not reach. A fixed word: nothing private. Measured on
# mpv 0.41.0, windowless (QA-RESULTS "D-SINK-72"): a get of the absent node
# answers `property not found`; set_property answers success, a SECOND
# client reads the word back, it survives two `loadfile ... replace`, and
# the set changes no other property, idle or playing.
USER_DATA_TLS = "user-data/omarchy-iptv-tls"
TLS_MIGRATED_MARK = "migrated"
PLAYER_GENERIC_FAILURE = "Playback stopped unexpectedly"   # mirrors Model.PLAYER_GENERIC_FAILURE
# The D-LIVE-17 ladder, unchanged: quit at 0, SIGTERM at 2 s, SIGKILL at 4 s.
STOP_QUIT_GRACE_MS = 2000
STOP_KILL_GRACE_MS = 2000
STOP_SETTLE_MS = 500
DEFAULT_LOCK_TIMEOUT = 6.0
DEFAULT_SPAWN_TIMEOUT = 5.0
DEFAULT_FIRST_LOAD_TIMEOUT = 3.0
DEFAULT_ORPHAN_GRACE = 6.0
LOCK_POLL_S = 0.05
LOCK_RETRIES = 5
# X1/X2: the two settle call sites that hold no lock of their own take one
# briefly. Short on purpose - a probe that cannot have it simply does not
# unlink, which is the safe half of the decision.
SETTLE_LOCK_TIMEOUT = 0.5
SPAWN_POLL_S = 0.02
STOP_POLL_S = 0.05
# D-PLY-35 (2026-10-28): the two bounds of the spawn and the settle that were
# literals, named so the shared player-bounds fixture can pin them. The shell's
# player watchdog (Model.playerWatchdogMs) is derived from every bound a
# `player start|restart|probe` can wait out, these two included; a literal
# could change without anything noticing. Values unchanged: how long the
# spawn waits for the grandchild to report its pid, and the connect timeout
# of socket_is_dead's one look at a socket that may be stale.
SPAWN_PID_TIMEOUT = 2.0
SETTLE_CONNECT_TIMEOUT = 0.2
# D-PLY-39 (2026-11-18): mpv's round trips in one control-slot verb (`play`,
# `status`, `pause`, `tracks`, `seek`), together: what the control slot's 8 s
# watchdog left them after the play-time lookup (Model.CONTROL_WATCHDOG_MS
# less STREAM_LOOKUP_TIMEOUT_S), now the share player_verb_bound_ms gives
# them and the verb's deadline holds them to. Mirrored by
# Model.PLAYER_BOUNDS.controlIpcMs, pinned by the player-bounds fixture.
CONTROL_IPC_S = 5.0
LAUNCH_STDERR_MAX = 4096          # PO-6: the launch window's stderr, memory only
PLAYER_UMASK = 0o077              # PO-11: 0600 files / 0700 dirs, requirement 10
# Mirror of Model.splitMpvArgs (4.12). The helper re-validates every
# --mpv-arg because bin/omarchy-iptv is a public CLI, and a parity test pins
# the two reserved sets equal.
MPV_ARG_RE = re.compile(r"^--[a-z0-9][a-z0-9-]*(=.*)?$")
# The list-option suffixes mpv spells one option with (mpv_option_base).
MPV_LIST_SUFFIX_RE = re.compile(r"-(add|append|set|pre|clr|del|remove|toggle)$")
MPV_RESERVED = frozenset((
    "--input-ipc-server", "--wayland-app-id", "--title", "--force-media-title",
    "--idle", "--input-ipc-client", "--script", "--scripts", "--config-dir",
    # D-SINK-4: reserved rather than merely defaulted off. `--load-scripts=no`
    # is in the base argv, but user mpv_args are concatenated AFTER it, so a
    # pasted `--load-scripts=yes` would win and put the credentialed stream
    # URL back on the session bus via mpv-mpris. Unlike --ytdl (PO-5) this one
    # guards a credential and has no legitimate counter-position.
    "--load-scripts",
    # D-SINK-2: --script is mpv's ALIAS for --scripts-append, so naming only
    # the alias reserved nothing. Matching is by base name now (see
    # filter_mpv_args), and --include loads a config that can set any of these.
    "--include",
    # D-SINK-13, and the reason layer 2 is not the whole fix.
    # `--stream-lavf-o` hands key=value straight to libavformat for the
    # STREAM, and FFmpeg's own AVOption is `tls_verify` -- a different knob
    # from mpv's `--tls-verify`, reaching the same place -- so the trailing
    # re-assertion cannot outvote it. Measured 2026-10-07 with BOTH
    # tls-verify tokens in place: `--stream-lavf-o=tls_verify=0` PLAYED the
    # attacker's stream, as did the -add, -append and -set forms.
    # mpv_option_base strips the list suffixes, so this covers all six.
    # `--demuxer-lavf-o` is NOT reserved, but that is no longer because it
    # "does not bypass": it DOES, for HLS and DASH (D-SINK-43, 2026-10-29),
    # because libavformat reopens those with the demuxer's options and hands
    # them to every segment open. It stays the user's because its other keys
    # are real workarounds (live_start_index, http_persistent); its TLS keys
    # are refused by filter_mpv_args (MPV_DEMUXER_TLS_WORDS), pinned by the
    # trailing block, and read back over IPC before every load.
    "--stream-lavf-o",
    "--log-file", "--dump-stats", "--stream-record", "--save-position-on-quit",
    "--watch-later-dir", "--osd-msg1", "--osd-msg2", "--osd-msg3",
    "--term-status-msg", "--screenshot-template",
    # M5-01 (design 2.6, D3). The privacy-relevant switch is not whether mpv
    # caches on disk but whether the file OUTLIVES the process: mpv unlinks
    # its cache file the moment it is created (F-RWD-5), and `whendone` or
    # `no` here keeps a copy of the stream at a path the plugin never listed,
    # which is `--stream-record`'s class. `--cache-on-disk` itself stays a
    # user choosing their own disk (PO-5's shape) and is warned about below.
    "--demuxer-cache-unlink-files",
    # D-SINK-13, layer 3 of four. mpv's `--tls-verify` defaults to NO, so the
    # plugin was handing provider headers and an HTTPS stream URL to a peer it
    # never authenticated; measured by the lead on 2026-10-07, the shipped argv
    # played a self-signed server, exit 0. The TLS peer is a rule 5 sink and
    # the one that gets the credential unredacted.
    #
    # Reserved here AND re-asserted as the final token in mpv_launch_argv. Not
    # alternatives: the trailing token is what makes verification safe (a later
    # command-line token beats an earlier one, and `--profile` carries
    # arbitrary options), this entry is what makes the refusal honest, so a
    # pasted `--tls-verify=no` is reported dropped instead of silently undone.
    # Both spellings fall out of the existing `no_form` arm in
    # filter_mpv_args: it rebuilds `--tls-verify` from `--no-tls-verify` and
    # finds it here, so no new branch is needed.
    #
    # Deliberately NOT reserved: `--tls-ca-file`, the targeted escape for a
    # provider with a self-signed or private-CA certificate (measured working
    # behind the trailing token - the `--screenshot-dir` shape, a user choice
    # that lands after ours and wins); and `--profile`, a legitimate mpv
    # feature that the trailing token makes harmless. `--tls-cert-file` and
    # `--tls-key-file` are CLIENT certificates, a different thing, untouched.
    "--tls-verify",
    # D-SINK-43..46 (owner, 2026-10-29: pin + classify). From here on the list
    # is the `reserved` and `pinned` classes of the mpv-options.json fixture
    # (dev branch), which classifies EVERY option of the installed mpv and is
    # what both mirrors are pinned to; a new mpv option nobody classified turns
    # the gate red (the mpv option guard, dev branch). Each entry's reason is in
    # the fixture; the groups are:
    #
    # PINNED as well as reserved: MPV_PIN_BLOCK re-asserts each after the
    # user's tokens, so a named profile, a plain mpv.conf line or a per-file
    # profile cannot change it either; refusing the token is the honest half,
    # exactly as for `--tls-verify` above.
    "--load-auto-profiles", "--load-select", "--load-unsafe-playlists",
    "--save-watch-history", "--input-commands", "--reset-on-next-file",
    "--osd-playlist-entry", "--demuxer-lavf-propagate-opts",
    # `pseudo-gui` makes mpv apply the user's [pseudo-gui] profile AFTER the
    # command line, with nothing preserved, so it undid every pin in
    # MPV_PIN_BLOCK (recheck, 2026-10-29: a plain mpv.conf line was enough;
    # D-SINK-44).
    "--player-operation-mode",
    # An ALIAS of a reserved name is the same option (D-SINK-2's lesson in the
    # other direction): mpv lists `--watch-later-directory` as an alias for
    # watch-later-dir, and base-name matching cannot see that.
    "--watch-later-directory",
    # Durable writes of the stream or of the URL (the --stream-record class).
    "--stream-dump", "--o", "--watch-history-path", "--ao-pcm-file", "--vo-image-outdir",
    # Property-expanding text (siblings of --osd-msg1..3 and --term-status-msg).
    "--osd-playing-msg", "--osd-status-msg", "--term-playing-msg", "--term-title",
    # A file of commands: every binding can `run` a program or draw ${path},
    # and mpv fetches it from a URL at startup (measured).
    "--input-conf",
    # Entries loaded before the shell: user-origin, so mpv's origin rule lets
    # them open any protocol, and the newborn-player check
    # (applied_by_another_client) would read them as another client's.
    "--playlist",
    # D-SINK-51: each opens a second address the token names and sends it the
    # channel's PROVIDER HEADERS (measured: the collector logged the header).
    # The aliases are the CLI spellings of the same options.
    "--sub-files", "--audio-files", "--external-files", "--cover-art-files", "--chapters-file",
    "--sub-file", "--audio-file", "--external-file", "--cover-art-file",
    # D-PLY-46 (lead, 2026-10-29): PINNED off. mpv's default `auto` loads a
    # URL dropped on the player window as a new entry, which no gate saw.
    "--drag-and-drop",
    # D-SINK-63 (lane-p1c, 2026-10-29): PINNED off. With it on, mpv opens the
    # next playlist entry while the playing file's per-file options are still
    # in force, so an entry the helper did not load was sent the channel's
    # provider headers (measured).
    "--prefetch-playlist",
    # D-SINK-61 (owner, 2026-10-29: turn the console off): PINNED off. mpv's
    # console draws the log commands.lua queues for it, and mpv logs a failed
    # open, or an HLS key that would not open, with its whole URL (measured).
    # `--load-osd-console` is mpv's alias of it, the same option.
    "--load-console", "--load-osd-console",
    # D-SINK-67 (owner, 2026-10-29: turn stats off): PINNED off. The stats
    # overlay's first and file pages draw `${filename}`, which is the whole
    # URL, userinfo and path credentials included, for a URL whose last path
    # segment is empty, and the userinfo for one with no path (measured).
    "--load-stats-overlay",
    # D-SINK-102 (the lead's call under the owner's standing authority of
    # 2026-11-09, reversing D-SINK-51's warning): PINNED to the player's
    # relay (mpv_relay_pin). Every connection the player makes over http and
    # https goes through it, judged against the address it reaches; a token
    # naming another proxy would carry the channel past every judgment, and
    # mpv takes the last one. The session's own http_proxy still applies, as
    # the relay's upstream.
    "--http-proxy",
))
# D-SINK-43 (and its verifyhost sibling): the words a `--demuxer-lavf-o*`
# token may not contain. For an HLS or DASH stream libavformat reopens the URL
# with the demuxer's options and copies them into every segment and key open,
# so a key there configures the TLS PROTOCOL: `tls_verify=0` played the
# attacker's segment with both --tls-verify=yes tokens in place, and
# `verifyhost=<attacker's own name>` played it with a certificate that was
# valid for that name -- the trailing tls_verify=1 pin cannot reach the
# second, which is why the token is refused and not merely outvoted. A
# substring test over the raw token, not a parse of mpv's key/value syntax:
# FFmpeg matches option names exactly, so every spelling of a TLS key
# (quoted, %n%-escaped, -append'ed) still carries the word, and the price is
# refusing a token whose VALUE happens to say "verify". The binding layer is
# the IPC read-back of the parsed map (demuxer_tls_unsafe), which no quoting
# reaches. Every key FFmpeg's TLS protocol names that is not harmless contains
# one of these words; the gate holds that against `ffmpeg -h protocol=tls`.
# Mirror of Model.MPV_DEMUXER_TLS_WORDS.
#
# D-SINK-55 (2026-10-29): and `protocol_whitelist` / `protocol_blacklist`,
# because the pin block now gives the demuxer a protocol whitelist (see
# MPV_PROTOCOL_WHITELIST) and a user key of the same name would replace it.
#
# D-SINK-62 (lane-p1c, 2026-10-29): and `format_whitelist` (the pin block's
# MPV_FORMAT_WHITELIST) and `format_blacklist` (no such FFmpeg key today;
# refused rather than reasoned about), and D-SINK-64: `seg_format_options`,
# the hls demuxer's options for its SEGMENT demuxer. That value is itself a
# dictionary FFmpeg parses with its own escapes, so the substring premise
# above is false inside it: `seg_format_options="format\_whitelist=sdp:
# protocol\_whitelist=rtp,udp"` carries neither word, passed this filter, and
# replaced both pinned lists in the segment's context -- with the user's
# `extension_picky=0` beside it, a stream server answering an HLS segment
# with an SDP body made the player listen on 0.0.0.0 (measured inside
# `unshare -rn`). The key is refused whole, and the read-back removes it.
#
# D-SINK-102 (the lead's call under the owner's standing authority of
# 2026-11-09, reversing D-SINK-59's warning): and `http_proxy`. mpv applies
# demuxer-lavf-o AFTER the network options (read in demux_lavf.c), so the
# key would replace the per-file proxy of every HLS and DASH reopen and
# segment, past the relay: measured with a plain mpv.conf line, the HLS
# demuxer's reopen of the master went to the decoy the line named while the
# stream layer's open went to the relay. Refused as a token, removed and
# counted at the read-back (DEMUXER_TLS_FORBIDDEN).
MPV_DEMUXER_TLS_WORDS = ("verify", "ca_file", "cafile", "listen", "external_sock",
                         "protocol_whitelist", "protocol_blacklist",
                         "format_whitelist", "format_blacklist", "seg_format_options", "http_proxy")
MPV_DEMUXER_OPTS = "--demuxer-lavf-o"
# D-SINK-55 (2026-10-29). The protocols libavformat may open BELOW a demuxer
# -- an HLS or DASH segment and key, and whatever a sniffed format opens on its
# own. A stream server that answers an http(s) URL with an SDP body makes
# FFmpeg's sdp demuxer open rtp with the whitelist it inherited from http, and
# the player then LISTENS (measured inside `unshare -rn`: c=0.0.0.0 bound
# 0.0.0.0:P and P+1, also under a .ts path). With this list as the demuxer's
# `protocol_whitelist` the same server bound nothing, and every scheme the
# gate admits still played or reached its server: http and https TS, an HLS
# master over http and a variant over https (segments too), rtmp, rtmps,
# rtsp over its default TCP transport, multicast udp and rtp, srt as caller,
# mms and mmsh (lane-p1b, 2026-10-29). The stream itself is opened by mpv's
# stream layer, which this list does not govern, so a udp, rtp or srt channel
# needs nothing from it. ONE exception, per file: an rtsp channel's demuxer
# opens its RTP transport itself, so the user's own --rtsp-transport=udp (or
# udp_multicast, or lavf) needs rtp and udp there -- MPV_RTSP_PROTOCOLS is
# added on the helper's own loadfile of an rtsp channel and nowhere else
# (channel_load_options). Mirror of Model.MPV_PROTOCOL_WHITELIST.
#
# [lane-p1c, 2026-10-29: "whatever a sniffed format opens on its own" above
# was too wide a claim. A demuxer that opens the URLs its CONTENT names opens
# them with this same list, which must hold tcp and tls because http and
# https run over them -- so FFmpeg's IMF demuxer, sniffed from a stream
# server's answer at score 100, bound `tcp://0.0.0.0:P?listen=1` and its tls
# and listen=2 forms, and an ffconcat file naming the CPL reached it too
# (rc-p1b, D-SINK-62). No protocol list can close that; MPV_FORMAT_WHITELIST
# below does.]
MPV_PROTOCOL_WHITELIST = "http,https,tls,tcp,crypto,data,httpproxy"
MPV_RTSP_PROTOCOLS = "rtp,udp"
MPV_DEMUXER_WHITELIST_KEY = "protocol_whitelist"
# D-SINK-62 (lane-p1c, 2026-10-29). The demuxers libavformat may use, as the
# demuxer's `format_whitelist`: FFmpeg checks it against the format a probe
# chose (or a user forced) before the demuxer reads a byte, and copies it into
# every nested context -- an HLS or DASH segment, a WebVTT rendition, a
# concat or IMF child -- so it binds at every depth (measured: each nested
# format taken off the list failed the stream that needed it). The list is
# what IPTV carries, and nothing on it opens a URL its content names except
# hls and dash, which open http(s) and data alone and give each segment's
# demuxer no opener of its own, and mov, whose external references are off by
# default and are local paths when on (measured: the colon becomes a slash,
# and `file` is not on MPV_PROTOCOL_WHITELIST). Every other demuxer that opens
# what it reads -- imf, concat, sdp, rtp, sap, vobsub, mlv, image2, dvdvideo,
# avisynth, vapoursynth, the lavfi device -- is off it (ARCHITECTURE-PLAYER
# 4.12.1 has the whole search). Measured inside `unshare -rn` through
# apply_channel: every channel kind the gate admits still plays or reaches
# its server, and every IMF, ffconcat, SDP and DASH-listen route binds
# nothing. Mirror of Model.MPV_FORMAT_WHITELIST.
MPV_FORMAT_WHITELIST = "hls,dash,mpegts,mov,matroska,flv,live_flv,mp3,aac,ac3,eac3,ogg,flac,asf,rtsp,webvtt"
MPV_DEMUXER_FORMATS_KEY = "format_whitelist"
# D-SINK-64: the keys of a demuxer-lavf-o map that are never left in it (see
# MPV_DEMUXER_TLS_WORDS): the hls segment demuxer's own options dictionary.
# rc-p1c (2026-10-29): and the rtsp demuxer's `listen_timeout`, which IMPLIES
# its listen flag (a value above 0 sets RTSP_FLAG_LISTEN in rtsp_read_header)
# and is the one key without which that flag cannot bind (the listener's tcp
# timeout is the value times 1000, and the default -1 is out of tcp's range).
# DEMUXER_TLS_FORBIDDEN removes an exact `listen` and nothing else, so a plain
# mpv.conf `demuxer-lavf-o=listen_timeout=5` -- a token is refused by the word
# `listen` -- made an rtsp channel LISTEN on its URL's host and port (measured
# inside `unshare -rn`: 127.0.0.1:P bound, on sec-int 124589e and lane-p1c
# alike; the same with the key removed bound nothing). A client that receives
# a channel by listening is not a player of a channel, so the key goes.
DEMUXER_FORMAT_FORBIDDEN = frozenset(("seg_format_options", "listen_timeout"))
# D-SINK-52 (owner, 2026-10-29: pin and refuse). The OSC embedded in mpv 0.41.0
# binds the title's middle click to `show-text ${path}`, which draws the whole
# credentialed URL on the picture and into any screenshot (read from osc.lua
# in /usr/bin/mpv, not clicked: no window here). Pinned to `ignore` as one key
# of script-opts, `-append` replacing that key and keeping the user's others
# (measured: a user token setting the same key lost to the pin and its other
# key stayed). Of the OSC's other command defaults, the playlist buttons'
# middle click draws ${playlist}, which reads the channel's title under the
# pinned osd-playlist-entry=title (measured); the rest draw no path.
MPV_OSC_TITLE_KEY = "osc-title_mbtn_mid_command"
MPV_OSC_TITLE_VALUE = "ignore"
# D-SINK-13, layers 1 and 2: one string, written into the argv twice on
# purpose. Mirror of Model.MPV_TLS_VERIFY; the two literals are pinned to each
# other by the shared player-argv.json vectors. See mpv_launch_argv.
MPV_TLS_VERIFY = "--tls-verify=yes"
# The trailing pin block (owner, 2026-10-29, decision 1): what a security layer
# depends on, re-asserted AFTER the user's tokens -- the D-SINK-13 layer-2
# shape. mpv takes the last token for an option, and a token here is also SET
# FROM THE COMMAND LINE, which is what keeps a [protocol.*] or [extension.*]
# profile from replacing it at file load (measured, per pin, in the five-way
# table of ARCHITECTURE-PLAYER 4.12). The block is the `pinned` class of
# the mpv-options.json fixture (dev branch), in this order, preceded by the one pin that
# carries a path (`--watch-later-dir`, composed in mpv_pin_block); its last
# element is layer 2 of D-SINK-13 and stays last. Mirror of Model.MPV_PIN_BLOCK.
MPV_PIN_BLOCK = (
    "--load-scripts=no",                 # D-SINK-4 against a named profile
    "--scripts-clr",                     # an explicit script= line loads anyway
    "--input-commands-clr",              # D-SINK-45: commands run at startup
    "--input-commands-append=keybind ctrl+v ignore",  # D-PLY-46: the paste-to-playlist key
    "--load-auto-profiles=no",           # D-SINK-44: profile-cond beats the command line
    "--player-operation-mode=cplayer",   # D-SINK-44: [pseudo-gui] applies after the command line
    "--load-select=no",                  # D-SINK-46: g l forks ffmpeg with the URL
    "--load-console=no",                 # D-SINK-61: the console draws a failed open's URL
    "--load-stats-overlay=no",           # D-SINK-67: stats draws ${filename}, credentials and all
    "--prefetch-playlist=no",            # D-SINK-63: a prefetched entry got the channel's headers
    "--load-unsafe-playlists=no",        # D-SINK-44: mpv's origin rule for nested entries
    "--save-watch-history=no",           # D-SINK-44: every path, durably
    "--log-file=",                       # every URL, durably
    "--reset-on-next-file-clr",          # D-SINK-51: the previous channel's headers
    "--osd-playlist-entry=title",        # ${playlist} draws the URL otherwise
    "--drag-and-drop=no",                # D-PLY-46: a dropped URL is an entry no gate saw
    "--script-opts-append=%s=%s" % (MPV_OSC_TITLE_KEY, MPV_OSC_TITLE_VALUE),  # D-SINK-52: show-text ${path}
    "--stream-lavf-o-clr",               # D-SINK-44: command-line-set, so no profile replaces it
    "--demuxer-lavf-propagate-opts=yes", # the next pins reach segments only this way
    "--demuxer-lavf-o-append=protocol_whitelist=" + MPV_PROTOCOL_WHITELIST,  # D-SINK-55
    "--demuxer-lavf-o-append=format_whitelist=" + MPV_FORMAT_WHITELIST,      # D-SINK-62
    "--demuxer-lavf-o-append=tls_verify=1",  # D-SINK-43
    MPV_TLS_VERIFY,                      # D-SINK-13 layer 2: LAST
)
# D-PLY-27 (the owner's decision, 2026-10-26): the launch argv ACCEPTS a
# software renderer. mpv 0.41.0's automatic VO probe, on a compositor that
# can serve no hardware GL or Vulkan context (a VM on llvmpipe, a pixman
# compositor), loses the waylandvk surface, fails x11vk -- through a lazy
# Xwayland or with no DISPLAY at all -- refuses the llvmpipe EGL context as a
# software renderer without releasing its Wayland state, whose pointer
# shares a union with `vo->x11`, and then trips its own assertion at x11egl,
# `vo_x11_init: Assertion '!vo->x11' failed` (video/out/x11_common.c:679;
# mpv-player/mpv#17190, fixed on master by a58dd8ac4, in no release as of
# 2026-10-26): SIGABRT about 5 s after every launch, a
# crash card and a coredump journal entry per zap (no core file: D-SINK-39
# holds the player's core limit at 0), relaunched by the service every
# ~5.5 s for as long as the play intent stands. `--gpu-sw=yes` makes the
# probe ACCEPT
# the software context (current-vo gpu-next, vo-configured true, exit 0);
# DISPLAY is not the lever and `--vo=wlshm` is not an alternative. Measured
# 2026-10-25 in a pixman cage with this argv shape (QA-RESULTS
# "F-HARNESS-45"). A rendering preference, not a security layer: it sits in
# the BASE argv so a user's own `--gpu-sw=no` or `--no-gpu-sw` lands after
# it and wins, it is NOT re-asserted at the tail the way MPV_TLS_VERIFY is,
# and it is NOT reserved. Mirror of the model's MPV_GPU_SW; the two literals
# are pinned to each other by the shared player-argv.json vectors
# (`gpuSoftware`).
MPV_GPU_SW = "--gpu-sw=yes"
# Restart on adoption (owner, 2026-10-31 and 2026-11-01): the build that
# launched a player, written onto its OWN command line, so a later helper can
# tell a player this build started from one another release or another
# helper build started. ONE token in the base section, version and checksum
# only -- nothing private (rule 5). The carrier is a script-opts key no
# script reads: `--script-opts` is the pinned class in the options fixture
# (dev branch), so the base-section test admits it, and the pin block's own
# script-opts token (one key, -append) leaves it where it is. Measured on mpv
# 0.41.0, windowless (lane RA's M2, 2026-11-01): exit 0, nothing at
# --msg-level=all=error, the key reading back exactly and script-opts, osc,
# load-scripts and idle otherwise equal with and without it. Mirror of the
# model's PLAYER_BUILD_KEY; the shared player-argv.json vectors carry a
# fixed build so both mirrors render the same token.
PLAYER_BUILD_KEY = "omarchy_iptv-build"
# What a build may be spelled with, at most PLAYER_BUILD_MAX of them (the
# model's PLAYER_BUILD_PATTERN is the same set and bound); a set, not a
# regex, so it adds nothing for the helper's regex-cost guard to review.
PLAYER_BUILD_CHARS = frozenset("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.+_-")
PLAYER_BUILD_MAX = 64
PLAYER_BUILD_UNKNOWN = "unknown"
LAUNCH_VERDICTS = ("current", "older", "unknown")
# D-SINK-16. The same two knobs, named as mpv PROPERTIES rather than as
# command-line options, because an ADOPTED player has no launch argv left to
# change: all four of D-SINK-13's layers live on the argv, so a process started
# by 0.12.1 -- mpv's own default is `tls-verify=no` -- goes on not verifying
# after the upgrade while this helper goes on sending it new provider headers
# and a new credentialed URL on every zap. Mirrors Model.MPV_TLS_VERIFY_PROP /
# Model.MPV_STREAM_OPTS_PROP.
MPV_TLS_VERIFY_PROP = "tls-verify"
MPV_STREAM_OPTS_PROP = "stream-lavf-o"
# D-SINK-16's other half (2026-10-29): the properties an ADOPTED player must
# also hold before it is handed a URL, because the launch argv of the process
# that is running may predate the pin block. `demuxer-lavf-o` is D-SINK-43 at
# runtime; `load-auto-profiles` is the switch for auto_profiles.lua, which
# applies a profile-cond profile at every load over the command line and over
# our own set_property (measured: tls-verify read false during play) -- and
# which mpv UNLOADS when the option is set to no at runtime (measured 3 of 3
# on a pre-pin player: the self-signed server got nothing). The two keys of
# demuxer-lavf-o that must read "1" when present, and the ones that must be
# absent, are FFmpeg's TLS protocol options as `ffmpeg -h protocol=tls` lists
# them for n9.0.1; the gate holds this list against the installed FFmpeg.
MPV_DEMUXER_OPTS_PROP = "demuxer-lavf-o"
MPV_AUTO_PROFILES_PROP = "load-auto-profiles"
# D-SINK-60: read back with the TLS pins (read_tls_state says why).
MPV_RESET_PROP = "reset-on-next-file"
DEMUXER_TLS_ON = frozenset(("tls_verify", "verify"))
DEMUXER_TLS_FORBIDDEN = frozenset(("ca_file", "cafile", "verifyhost", "listen", "external_sock", "http_proxy"))
# The options a [protocol.*] or [extension.*] profile could set at file load,
# AFTER the read-back, to undo the TLS layer -- harmless on a player that has
# them set from the command line (the pin block does), and the residual on a
# player that does not (measured: a pre-pin player with [protocol.https]
# stream-lavf-o=tls_verify=0 in its mpv.conf read safe and then fetched from
# the attacker). `profile` is followed, since a profile can name another.
#
# Since 2026-10-29 (the lead's decision on rc-mpvpin's recheck) it is EVERY
# option the pin block holds, not only the TLS ones: on a pre-pin player a
# [protocol.http] profile with save-watch-history, load-unsafe-playlists or
# load-select undid pin_adopted_player's runtime writes at every load
# (measured by the recheck: the watch history got the credentialed path, a
# nested playlist truncated a scratch file, select forked ffmpeg with the
# URL). So a pre-pin player whose mpv.conf holds a per-file profile that
# touches ANY pinned option is stopped rather than migrated.
#
# load-stats-overlay (D-SINK-67) included: measured, a pre-pin player's own
# [protocol.*] profile turning stats back on drew the credentialed filename
# after the adoption had turned it off.
#
# D-SINK-102: and `http-proxy`, the relay pin, which mpv_pin_block composes
# beside the resume folder because it carries the relay's port.
PER_FILE_TLS_OPTIONS = tuple(sorted({MPV_LIST_SUFFIX_RE.sub("", token.split("=", 1)[0])[2:]
                                     for token in ("--watch-later-dir=", "--http-proxy=") + MPV_PIN_BLOCK}))
# mpv's own aliases of pinned options, as a profile's key may spell them.
PER_FILE_OPTION_ALIASES = {"script": "scripts", "watch-later-directory": "watch-later-dir",
                           "script-opt": "script-opts", "load-osd-console": "load-console"}
PER_FILE_PROFILE_PREFIXES = ("protocol.", "extension.")
PLAYER_VERBS = ("start", "stop", "restart", "probe", "orphan-check", "pause", "tracks", "seek", "relay", "refused")
# Mirror of MPV_HANDOFF (model/mpv.mjs, internal to the model) and friends (PO-10, D-PLY-5). These options are
# allowed - PO-5 keeps `--ytdl` as the documented escape hatch for links that
# are not direct streams - but each one puts the credentialed stream address
# on a SECOND program's command line, so the user is told at the moment the
# option is in force. Pinned to the JavaScript by the `mpvHandoff` vectors in
# the player-argv.json. fixture (dev branch)
# D-SINK-51 (2026-10-29) made `--http-proxy` one of them; D-SINK-102 pins it
# to the relay instead (MPV_RESERVED), so it is refused, not warned.
MPV_HANDOFF = frozenset(("--ytdl-format", "--ytdl-raw-options"))
MPV_HANDOFF_SCRIPT_OPTS = frozenset(("--script-opts", "--script-opt"))
MPV_YTDL_OFF = frozenset(("no", "0", "false"))
MPV_HANDOFF_TEXT = " hands the stream address to another program"
# M5-01 (design 2.6): the same PO-10 mechanism, a different cost. `--cache-on-disk`
# writes the stream to the user's own disk continuously (1.8 to 4.5 GiB per
# hour at the measured bitrates, into a file mpv unlinks at creation, so `ls`
# and `du` show nothing). Allowed, because it is the user's disk; said out
# loud, because nothing else would say it. Mirror of Model.MPV_DISK_WARN.
MPV_DISK_WARN = frozenset(("--cache-on-disk",))
MPV_DISK_TEXT = " writes the stream to disk while it plays"
# D-SINK-59 (lead, 2026-10-29) warned of a `--demuxer-lavf-o` token carrying
# FFmpeg's `http_proxy` key; D-SINK-102 refuses it (MPV_DEMUXER_TLS_WORDS).
# D-SINK-53 (lead, 2026-10-29): `--rtsp-transport` other than tcp or http makes
# every rtsp channel bind RTP and RTCP ports on all interfaces for anyone to
# send to (measured by lane-dest: SETUP asked for client_port with udp, TCP
# interleaved without it). The user's own choice (PO-5's shape), so warned.
# mpv 0.41.0's values: lavf udp tcp http udp_multicast; `lavf` lets FFmpeg
# pick, and it tries UDP first.
MPV_LISTEN_WARN = frozenset(("--rtsp-transport",))
MPV_LISTEN_QUIET = frozenset(("tcp", "http", "https"))
MPV_LISTEN_TEXT = " opens ports on this computer that anyone can send to"
# D-SINK-65 (lane-p2a, 2026-10-29): the same cost through FFmpeg's own key.
# `--demuxer-lavf-o=rtsp_transport=udp` binds an rtsp channel's RTP/RTCP pair
# on 0.0.0.0 exactly as `--rtsp-transport=udp` does, and FFmpeg takes the
# value as FLAGS: a name, a number, an expression, `+udp` and `-tcp` against
# mpv's tcp, `0`, quoted, bracketed or %n%-escaped -- each measured binding
# inside `unshare -rn`, none of them warned. So every occurrence of the key is
# read and the token warns unless EACH value is a plain `+`-join of tcp, http
# and https; anything else warns. No spelling of `rtsp_flags` binds
# (measured), and a removal (-clr, -del, -remove) sets nothing. Mirror of
# Model's MPV_RTSP_TRANSPORT_KEY.
MPV_RTSP_TRANSPORT_KEY = "rtsp_transport"
MPV_LIST_REMOVALS = ("-clr", "-del", "-remove")
# D-SINK-52 (owner, 2026-10-29: pin and refuse). A `--script-opts` token is
# REFUSED when its text sets an on-screen-controller command -- the OSC runs
# its `*_mbtn_*_command` / `*_wheel_*_command` options as input commands on a
# click, so `show-text ${path}` draws the credentialed URL and `run` starts a
# program -- or carries `${`, which the OSC's text options property-expand. A
# substring of the raw token, the MPV_DEMUXER_TLS_WORDS shape: every spelling
# of such a key still carries the word, and the price is refusing a value
# that happens to contain one. Every other key, `ytdl_hook-*` included (PO-10,
# warned), passes. Mirror of Model.MPV_SCRIPT_OPTS_WORDS.
MPV_SCRIPT_OPTS_WORDS = ("${", "_command", "_mbtn_", "_wheel_")


def _monotonic() -> float:
    """Indirection so tests can drive the stop ladder with a fake clock."""
    return time.monotonic()


def _sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def filter_mpv_args(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Mirror of Model.splitMpvArgs on already-split tokens."""
    args: list[str] = []
    rejected: list[str] = []
    for token in tokens or []:
        text = str(token)
        name = text.split("=", 1)[0]
        # D-SINK-2: the BASE name decides. `mpv_option_base` was defined
        # fifteen lines below this filter and never used by it, so
        # `--scripts-append` -- which mpv's own --list-options calls the
        # option that `--script` is an ALIAS for -- was accepted here and by
        # the JavaScript mirror.
        base = mpv_option_base(name)
        bare = "--" + name[5:] if name.startswith("--no-") else ""
        no_form = bool(bare) and (bare in MPV_RESERVED or mpv_option_base(bare) in MPV_RESERVED)
        # D-SINK-47: a token becomes one line of the player's options file
        # (mpv_args_config), and a line break or a NUL cannot be carried on
        # one -- refused here, so the writer never meets one. Nor can a lone
        # surrogate, which no UTF-8 file can hold: a byte argv could not
        # decode arrives as one (U+DC80-U+DCFF), and so does a JSON \ud800
        # escape; the writer met it and the start ended `internal`.
        if (not MPV_ARG_RE.match(text) or name in MPV_RESERVED or base in MPV_RESERVED or no_form
                or demuxer_names_tls(base, text) or script_opts_refused(base, text)
                or not mpv_token_writable(text)):
            rejected.append(text)
        else:
            args.append(text)
    return args, rejected


def demuxer_names_tls(base: str, token: str) -> bool:
    """Mirror of Model.demuxerNamesTls: a `--demuxer-lavf-o*` token that names
    a TLS setting (D-SINK-43). See MPV_DEMUXER_TLS_WORDS for why a substring."""
    return base == MPV_DEMUXER_OPTS and any(word in token for word in MPV_DEMUXER_TLS_WORDS)


def script_opts_refused(base: str, token: str) -> bool:
    """Mirror of Model.scriptOptsRefused: a `--script-opts*` token that sets
    an OSC command or carries `${` (D-SINK-52). See MPV_SCRIPT_OPTS_WORDS."""
    return base in MPV_HANDOFF_SCRIPT_OPTS and any(word in token for word in MPV_SCRIPT_OPTS_WORDS)


def mpv_option_base(name: str) -> str:
    """Mirror of Model.mpvOptionBase: `--opt-append` and `--opt-set` set the
    same option `--opt` does, so the base name is what decides."""
    return MPV_LIST_SUFFIX_RE.sub("", str(name))


def mpv_arg_hands_off_url(token: str) -> str:
    """Mirror of Model.mpvHandoffName. "" when the token is harmless, else the
    option NAME. The VALUE is never returned: it can carry a credentialed URL
    of its own (a proxy in --ytdl-raw-options) and a warning is a sink (R12).
    """
    text = str(token)
    name, _, value = text.partition("=")
    if name.startswith("--no-"):          # --no-ytdl turns the handoff OFF
        return ""
    base = mpv_option_base(name)
    if base == "--ytdl":
        return "" if value.lower() in MPV_YTDL_OFF else name
    if base in MPV_HANDOFF:
        return name
    if base in MPV_HANDOFF_SCRIPT_OPTS:
        return name if "ytdl" in value else ""
    return ""


def mpv_arg_writes_disk(token: str) -> str:
    """Mirror of Model.mpvDiskName: the option NAME when the token turns the
    disk cache on, "" otherwise. A flag like `--ytdl`: `--no-cache-on-disk`
    and `=no` turn it off and are silent."""
    text = str(token)
    name, _, value = text.partition("=")
    if name.startswith("--no-"):
        return ""
    if mpv_option_base(name) in MPV_DISK_WARN:
        return "" if value.lower() in MPV_YTDL_OFF else name
    return ""


def mpv_arg_opens_ports(token: str) -> str:
    """Mirror of Model.mpvListenName: the option NAME when the token makes
    rtsp channels bind ports (D-SINK-53, and D-SINK-65 through FFmpeg's own
    rtsp_transport), "" otherwise. The line carries the name alone (R12)."""
    text = str(token)
    name, _, value = text.partition("=")
    if name.startswith("--no-"):
        return ""
    base = mpv_option_base(name)
    if base == MPV_DEMUXER_OPTS:
        return name if demuxer_opens_ports(name, value) else ""
    if base not in MPV_LISTEN_WARN:
        return ""
    # D-STATE-2: the reader's class, Model.stripSpace's, so the warning is mpvListenName's.
    return "" if value.strip(URL_SPACE_CHARS).lower() in MPV_LISTEN_QUIET else name


def demuxer_opens_ports(name: str, value: str) -> bool:
    """Mirror of Model.demuxerOpensPorts (D-SINK-65): a `--demuxer-lavf-o*`
    value that sets rtsp_transport to anything but a plain `+`-join of tcp,
    http and https. Index walks, no pattern."""
    if str(name).endswith(MPV_LIST_REMOVALS):
        return False
    text = str(value)
    at = text.find(MPV_RTSP_TRANSPORT_KEY)
    while at != -1:
        rest = text[at + len(MPV_RTSP_TRANSPORT_KEY):]
        if not rest.startswith("="):
            return True
        v = rest[1:]
        close = '"' if v.startswith('"') else ("]" if v.startswith("[") else "")
        end = v.find(close, 1) if close else v.find(",")
        if close:
            v = v if end == -1 else v[1:end]
        elif end != -1:
            v = v[:end]
        if not all(part in MPV_LISTEN_QUIET for part in v.split("+")):
            return True
        at = text.find(MPV_RTSP_TRANSPORT_KEY, at + 1)
    return False


def mpv_arg_warning(token: str) -> str:
    """Mirror of Model.mpvArgWarning: the whole warning line for one token,
    or "" -- the first of mpv_arg_warning_lines. The three costs carry their
    own sentence, so the user is told WHAT the option does rather than that
    it is "dangerous"."""
    lines = mpv_arg_warning_lines(token)
    return lines[0] if lines else ""


def mpv_arg_warning_lines(token: str) -> list[str]:
    """Mirror of Model.mpvArgWarningLines: every cost one token carries, in a
    fixed order (D-SINK-65 made one token able to carry two)."""
    out = []
    name = mpv_arg_hands_off_url(token)
    if name:
        out.append("mpvArg " + name + MPV_HANDOFF_TEXT)
    name = mpv_arg_writes_disk(token)
    if name:
        out.append("mpvArg " + name + MPV_DISK_TEXT)
    name = mpv_arg_opens_ports(token)
    if name:
        out.append("mpvArg " + name + MPV_LISTEN_TEXT)
    return out


def mpv_arg_warnings(tokens: list[str]) -> list[str]:
    """Mirror of Model.mpvArgWarnings: one line per distinct option and cost,
    in the order the user wrote them."""
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens or []:
        for line in mpv_arg_warning_lines(token):
            if line in seen:
                continue
            seen.add(line)
            out.append(line)
    return out


def player_dirs(sock_path: str, state_override: str | None = None) -> dict[str, str]:
    """Where the player is allowed to write (PO-11, D-PLY-7).

    mpv's own key bindings are live on its window and two of them write a
    durable file: `s` takes a screenshot and `Q` (quit-watch-later) writes a
    resume record. Both used to land wherever the shell happened to be - the
    user's home for the screenshot, mpv's own ~/.local/state/mpv tree for the
    resume record - at mode 0644, outside every list of files this plugin
    says it writes.

    - `cwd` is the runtime directory (0700, already ensured for the socket).
      It is where anything relative still lands, so a cwd-relative write we
      have not anticipated goes somewhere private and disappears at logout
      instead of accumulating in $HOME.
    - `screenshots` is durable on purpose: a screenshot is something the user
      asked for, so the runtime directory would be data loss at logout. It
      lives under the state directory this plugin already owns and documents.
    - `watchLater` is a resume position for a live stream, which is never
      worth keeping: ephemeral, private, gone at logout.
    - `shaderCache` is D-PLY-10, ruling CL2: mpv compiles its shaders into
      $XDG_CACHE_HOME/mpv/ otherwise, which is outside every list of files
      this plugin says it writes. A shader cache is content-free and
      regenerable - it is not keyed to anything that was watched - so the
      runtime directory is the right home: already 0700, already documented,
      gone at logout, and it adds NO durable path and nothing to clean up at
      uninstall. Containment here is a sensible default, not a guarantee:
      neither option is reserved, because MPV_RESERVED is a privacy
      instrument and a content-free cache does not belong on it (CL2).

    D-SINK-47 (lane-p2a, 2026-10-29): `mpvArgs` is the private file the
    user's tokens live in for the length of a launch (write_mpv_args), in the
    runtime directory beside the socket.
    """
    runtime = os.path.dirname(sock_path)
    return {
        "cwd": runtime,
        "screenshots": os.path.join(state_dir(state_override), "screenshots"),
        "watchLater": os.path.join(runtime, "watch-later"),
        "shaderCache": os.path.join(runtime, "shader-cache"),
        "mpvArgs": os.path.join(runtime, MPV_ARGS_FILE),
    }


def player_build() -> str:
    """This helper's build, the one thing the launch marker says (restart on
    adoption): the plugin's version and the CRC-32, as eight hex digits, of
    one `name:length:crc` line per entry of the stub's HELPER_PARTS. The parts
    run in the stub's own globals, so the table is read with no file read;
    every part edit changes it (`--seal` rewrites the entry) and every release
    changes the version, so nothing is bumped by hand. The ONLY producer: the
    launch argv and launch_verdict both call it. A value outside
    player_build_ok (a manifest version with a space in it) is the word
    `unknown`, which every build then shares -- a marker that cannot tell
    builds apart is honest about it, and the version read is nothing private."""
    parts = globals().get("HELPER_PARTS") or ()
    try:
        text = "".join("%s:%d:%08x\n" % (name, int(size), int(crc)) for name, size, crc in parts)
    except (TypeError, ValueError):
        return PLAYER_BUILD_UNKNOWN
    if not text:
        return PLAYER_BUILD_UNKNOWN
    build = "%s+%08x" % (VERSION, zlib.crc32(text.encode("ascii", "replace")) & 0xFFFFFFFF)
    return build if player_build_ok(build) else PLAYER_BUILD_UNKNOWN


def player_build_ok(value: Any) -> bool:
    """A build is 1 to PLAYER_BUILD_MAX of PLAYER_BUILD_CHARS."""
    return (isinstance(value, str) and 0 < len(value) <= PLAYER_BUILD_MAX
            and all(char in PLAYER_BUILD_CHARS for char in value))


def mpv_build_marker(build: Any) -> str:
    """The launch marker for `build`, `unknown` when it is not one. Mirror of
    the model's mpvBuildMarker."""
    value = build if player_build_ok(build) else PLAYER_BUILD_UNKNOWN
    return "--script-opts-append=%s=%s" % (PLAYER_BUILD_KEY, value)


def mpv_launch_argv(sock_path: str, mpv_args: list[str],
                    dirs: dict[str, str] | None = None, build: str | None = None,
                    relay_port: int = 0) -> list[str]:
    """The player's launch argv: `mpv_args` decides only whether the private
    options file is named (D-SINK-47; its tokens are never on the argv), and
    `build` is player_build()'s unless a caller names one (the shared
    vectors do). launch_verdict composes the same argv through the same
    builder, both forms, which is what makes a player this build launched
    read as this build's (restart on adoption). `relay_port` is the port of
    the relay listener the spawn bound (D-SINK-102, mpv_relay_pin); a caller
    that names none composes port 0, which no relay can hold, so a player
    launched from such an argv reaches nothing over http and reads as no
    build's own."""
    where = dirs or player_dirs(sock_path)
    return compose_launch_argv(sock_path, bool(mpv_args), where, player_build() if build is None else build,
                               relay_port)


def mpv_relay_pin(relay_port: Any) -> str:
    """D-SINK-102: the pin that makes the relay the player's HTTP proxy,
    `--http-proxy=http://127.0.0.1:<port>`, with no credential, so that on
    its own it denies everything (the relay answers 407 and FFmpeg, having
    no credential, gives up: measured); each load the helper registers
    carries its own token as a per-file value (channel_load_options). A
    port that is not one is 0. Mirror of the model's mpvRelayPin."""
    port = relay_port if isinstance(relay_port, int) and not isinstance(relay_port, bool) and 0 < relay_port < 65536 else 0
    return "--http-proxy=http://%s:%d" % (RELAY_HOST, port)


def compose_launch_argv(sock_path: str, include: bool, where: dict[str, str], build: str,
                        relay_port: int = 0) -> list[str]:
    """Mirror of Model.buildMpvArgv, pinned by the player-argv.json. fixture (dev branch)

    No URL, no "--", no header options, no per-channel title: the first
    channel arrives over IPC like every later one (S-03). `--idle=once` (PO-1)
    idles at startup and still exits when the playlist finishes, which keeps
    today's UX and the degraded status-poll fallback.

    The two output directories (PO-11) are fixed options, so a user who wants
    their screenshots elsewhere can still say so: `--screenshot-dir` is not
    reserved and user tokens land after these. `--watch-later-dir` IS
    reserved, because a resume record naming a stream path has no business
    being redirected back into $HOME -- and since 2026-10-29 it is pinned too,
    because a named profile in the user's own mpv.conf moved it (measured).

    The two cache directories are D-PLY-10 / CL2, in the same shape and for
    the same reason: mpv's shader and ICC caches default into
    $XDG_CACHE_HOME/mpv/, outside this plugin's tree. Neither is reserved -
    both are content-free - so a user token can still point them elsewhere.

    D-SINK-13 broke the "user tokens land last" shape on purpose for one
    option, `--tls-verify=yes`, in the base argv AND again after the user's;
    D-SINK-43..46 widened that tail to the whole pin block (MPV_PIN_BLOCK),
    which still ends with that token. See the comment on the return.

    Restart on adoption (2026-11-01): the base section ends with the build
    marker (mpv_build_marker), after layer 1 of TLS and before the options
    file, so a user token can never stand in front of it on the argv -- the
    tokens are in the file -- and the pin block after it is unchanged.
    """
    return [
        "mpv",
        "--input-ipc-server=%s" % sock_path,
        "--wayland-app-id=omarchy-iptv",
        "--force-window=immediate",
        "--idle=once",
        "--keep-open=no",
        "--title=%sIPTV" % MPV_RAW_PREFIX,
        "--force-media-title=IPTV",
        "--msg-level=all=error",
        "--ytdl=no",
        # D-SINK-4. mpv autoloads every script in its system directory, which
        # here includes mpv-mpris; it publishes `xesam:url` -- the stream URL,
        # credentials and all -- on the session bus for as long as a channel
        # plays. Measured on the real bus. mpv-mpris has no configuration
        # surface, so keeping it and not leaking is not available, and this
        # plugin loads no script of its own. Cost: Omarchy's media widget
        # stops showing the channel, which the bar widget already shows.
        "--load-scripts=no",
        "--screenshot-dir=%s" % where["screenshots"],
        "--watch-later-dir=%s" % where["watchLater"],
        "--gpu-shader-cache-dir=%s" % where["shaderCache"],
        "--icc-cache-dir=%s" % where["shaderCache"],
        # D-PLY-27: accept a software renderer (see MPV_GPU_SW). In the base
        # section, BEFORE the user's tokens, so a `--gpu-sw=no` in mpv_args
        # lands after it and wins; once, never re-asserted, never reserved.
        MPV_GPU_SW,
        # D-SINK-13, LAYER 1: stated here, where a reader looks to find out what
        # the player is launched with. mpv's own default is `--tls-verify=no`
        # (`mpv --list-options`, 0.41.0). Layer 1 alone is NOT the fix.
        MPV_TLS_VERIFY,
        # Restart on adoption: which build launched this player, read back
        # off /proc by launch_verdict. Version and checksum only.
        mpv_build_marker(build),
    # D-SINK-13, LAYER 2, and the line that actually guarantees verification.
    #
    # THE TWO OCCURRENCES OF MPV_TLS_VERIFY ARE NOT REDUNDANT. Removing either
    # is a security change, not a tidy-up, and this one is the one that holds.
    # mpv takes the LAST token for a repeated option, so user mpv_args land
    # between the base argv and this one and are overridden rather than
    # overriding. That matters because `--tls-verify` is not the only way off:
    # `--profile=NAME` applies every option in that profile where the token
    # appears, and a profile in the user's own mpv.conf can set
    # `tls-verify=no`. Measured by the lead on 2026-10-07: with layer 1 only,
    # `--profile=evil` PLAYED a self-signed stream (exit 0); with this trailing
    # token the same command refused it (exit 2), as did `--tls-verify=no` and
    # `--no-tls-verify` behind it. So this layer covers the indirections nobody
    # has enumerated, which is why `--profile` is not reserved. A bare `--`
    # cannot escape it: MPV_ARG_RE requires `--` followed by a lowercase letter
    # or digit, so filter_mpv_args puts `--` in the rejected bucket (measured by
    # calling it). And it leaves the escape hatch intact: `--tls-ca-file` is
    # unreserved and names a CA for THIS token to verify against.
    #
    # Mirror of Model.buildMpvArgv's return; pinned to it by the
    # `--profile=evil` vector in the player-argv.json fixture (dev branch),
    # whose user arguments are what make this line visible at all.
    #
    # D-SINK-43..46 (owner, 2026-10-29) widened the tail from one token to the
    # pin block, on the same reasoning: every option a security layer depends
    # on is re-asserted here, after the user's tokens, so the last word is ours
    # over a token, a named profile and a plain mpv.conf line, and each is set
    # from the command line, so no per-file profile replaces it. The block ends
    # with MPV_TLS_VERIFY, so the line above still describes the last element.
    #
    # D-SINK-47 (lane-p2a, 2026-10-29): the user's tokens are no longer ON this
    # argv, which is /proc/<pid>/cmdline -- world-readable for the hours a
    # player runs, and COREDUMP_CMDLINE in the journal if it crashes -- and a
    # token is where a proxy password or an API-key header goes. They are in
    # the private file `where["mpvArgs"]` (write_mpv_args), named here at the
    # place they stood: mpv parses an --include file AT ITS POSITION and marks
    # what it sets as set from the command line (measured), so the pin block
    # after it keeps the last word exactly as it did over the tokens.
    #
    # D-SINK-102: the pin block now opens with the relay pin beside the
    # resume folder (mpv_pin_block), so it too is set from the command line
    # after the user's tokens and no profile replaces it at file load
    # (measured: a [protocol.http] profile naming another proxy set nothing
    # over it), and MPV_TLS_VERIFY is still the last element.
    ] + (["--include=%s" % mpv_args_path(sock_path, where)] if include else []) + mpv_pin_block(where, relay_port)


# D-SINK-47: the private file's name, in the runtime directory.
MPV_ARGS_FILE = "mpv-args.conf"


def mpv_args_path(sock_path: str, where: dict[str, str]) -> str:
    """The options file a set of player folders names, or the runtime
    folder's own when a caller's set predates it. Mirror of the model's
    fallback in buildMpvArgv."""
    return where.get("mpvArgs") or os.path.join(os.path.dirname(sock_path), MPV_ARGS_FILE)


def mpv_token_writable(text: str) -> bool:
    """D-SINK-47: whether one token can be one line of the player's options
    file: no NUL, no line break, and UTF-8 encodable -- a lone surrogate,
    which is what a byte argv could not decode becomes, is not. Mirror of
    Model.mpvTokenWritable."""
    if any(char in text for char in "\0\n\r"):
        return False
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def mpv_args_config(tokens: list[str]) -> str:
    """The text of the player's options file: one line per token, in order.

    `--name` becomes `name` (mpv's config syntax for a flag, and for
    `no-name`, measured), and `--name=value` becomes `name=%N%value`, N being
    the value's length in UTF-8 bytes: mpv's length-quoted form, the one form
    whose value is taken exactly, so a value holding `=`, `,`, either quote,
    spaces, `#` (a comment in the plain form, measured cutting `a#b` to `a`),
    `%`, a trailing backslash or any other byte means what it meant on the
    argv -- measured token by token, 16 of 16 reading back identical both
    ways. A line break, a NUL or a lone surrogate cannot be carried on a
    line (mpv_token_writable), and the filter refuses each before this is
    reached; one here is a bug, and refused."""
    lines = []
    for token in tokens or []:
        text = str(token)
        if not text.startswith("--") or not mpv_token_writable(text):
            raise HelperError("bad_arguments", "an mpv option cannot be written to the player's options")
        name, eq, value = text[2:].partition("=")
        lines.append("%s=%%%d%%%s" % (name, len(value.encode("utf-8")), value) if eq else name)
    return "".join(line + "\n" for line in lines)


def write_mpv_args(path: str, tokens: list[str]) -> None:
    """D-SINK-47: put the user's tokens where only this uid can read them, for
    the length of a launch. The folder is the 0700 runtime folder
    (player_runtime made it); the file is created 0600 under a name of its
    own with O_EXCL and O_NOFOLLOW -- a link or anything else at that name is
    never written through -- and renamed over `path`, so mpv reads either the
    whole file or none, and a stale one from a helper that was killed is
    replaced, never appended to."""
    data = mpv_args_config(tokens).encode("utf-8")
    temp = os.path.join(os.path.dirname(path), ".%s.%d" % (os.path.basename(path), os.getpid()))
    try:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
        finally:
            os.close(fd)
        os.rename(temp, path)
    except OSError as io_error:
        remove_mpv_args(temp)
        raise runtime_unwritable("write the player's options", io_error) from None


def remove_mpv_args(path: str) -> None:
    """D-SINK-47: the file goes as soon as mpv has read it -- once its socket
    answers, which mpv binds only after its whole command line is parsed --
    and on every path out of a launch that failed. Quiet: a file already gone
    is the goal, and any other failure leaves a 0600 file in a 0700 folder
    that the next launch's rename replaces and a logout removes."""
    try:
        os.unlink(path)
    except OSError:
        pass


def check_mpv_args_path(path: str) -> None:
    """D-PLY-68: the refusal write_mpv_args meets at a folder in the options
    file's place (its rename cannot replace one: EISDIR), asked by `player
    start` and `player restart` before the lock, in the same words, so
    before a restart's ladder or an adoption's replacement has stopped
    anything. Anything else there is replaced by that rename, as before."""
    try:
        mode = os.lstat(path).st_mode
    except OSError:
        return
    if stat.S_ISDIR(mode):
        raise runtime_unwritable("write the player's options", IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR)))


def mpv_pin_block(where: dict[str, str], relay_port: int = 0) -> list[str]:
    """Mirror of Model.mpvPinBlock: the trailing pins, the contained resume
    folder first (a named profile moved it: measured), then the relay pin
    (D-SINK-102, mpv_relay_pin), then MPV_PIN_BLOCK, whose last element is
    D-SINK-13's layer 2."""
    return ["--watch-later-dir=%s" % where["watchLater"], mpv_relay_pin(relay_port)] + list(MPV_PIN_BLOCK)


def stop_escalation(stage: str) -> dict[str, Any]:
    """Mirror of Model.stopEscalation (the reducer of record)."""
    text = stage or ""
    if text == "":
        return {"action": "quit", "signal": 0, "waitMs": STOP_QUIT_GRACE_MS}
    if text == "quit":
        return {"action": "term", "signal": 15, "waitMs": STOP_KILL_GRACE_MS}
    if text == "term":
        return {"action": "kill", "signal": 9, "waitMs": 0}
    return {"action": "kill", "signal": 0, "waitMs": 0}


def ended_verdict(end_file: dict[str, Any] | None, user_stopped: bool = False,
                  stopping: bool = False) -> dict[str, Any]:
    """Mirror of Model.endedVerdict (4.8): why the player ended.

    The entry id is deliberately not consulted - it decides which channel the
    message names, never whether there is one (F4, the gate fails open).
    """
    if user_stopped or stopping:
        return {"notify": False, "reason": "", "kind": "silent"}
    if not isinstance(end_file, dict):
        return {"notify": True, "reason": PLAYER_GENERIC_FAILURE, "kind": "failed"}
    reason = str(end_file.get("reason") or "")
    if reason == "redirect":
        # The .m3u8 master resolution IPTV uses most: never terminal.
        return {"notify": False, "reason": "", "kind": "ignored"}
    if reason in ("quit", "eof"):
        return {"notify": False, "reason": "", "kind": "silent"}
    detail = redact_urls(end_file.get("fileError") or end_file.get("file_error") or "").strip()
    return {"notify": True, "reason": detail or PLAYER_GENERIC_FAILURE, "kind": "failed"}


def player_stash(channel_id: str, name: str, group: str, scope: str, source_key: str,
                 since: int, seq: int, entry_id: int | None = None,
                 playing: bool = True, verb: str = "play") -> dict[str, Any]:
    """Mirror of Model.playerStash: the now-playing record mpv carries for us.

    `launchedFrom` is the zap-ring scope - pure UI intent no mpv property
    could ever report, which is why the shell's own value is stashed here and
    echoed back on reattach.

    `verb` says which slot wrote the record last, and it exists because `seq`
    stopped being able to say so. The zap used to hardcode `seq` to 0, which
    made "not zero" a usable stand-in for "a player verb wrote this" - the
    reading wave two's evidence leaned on. Now that both sides carry a real
    intent number the two can be COMPARED, which is the point, but the
    writer has to be named outright rather than inferred from a zero.

    D-SINK-104 (2026-11-16): the name and the group are stored as shown_text
    prints them, and the scope only when it reads plainly (scope_reading),
    so the record at rest in the player is the one every reply prints: the
    status and probe replies printed it raw beside a redacted title. The
    shell restores the name and the group only to draw them, through its own
    reading, and replaces both from the cache when the channel is found
    (Service.reconcileNowPlaying), which also scopes an empty `launchedFrom`
    to the channel's first group. Cost: a channel no longer in the playlist
    at a reattach, whose group's name reads as an address or holds a
    credential or a control, zaps nowhere until another channel is chosen.
    The id stays as it is: `play` takes it back.
    """
    return {
        "schema": PLAYER_STASH_SCHEMA,
        "playing": bool(playing),
        "id": str(channel_id or ""),
        "name": shown_text(str(name or "")),
        "group": shown_text(str(group or "")),
        "launchedFrom": scope_reading(str(scope or "")),
        "sourceKey": str(source_key or ""),
        "since": int(since or 0),
        "entryId": entry_id if isinstance(entry_id, int) and entry_id > 0 else None,
        "seq": int(seq or 0),
        "verb": str(verb or ""),
    }


def source_key_of(directory: str) -> str:
    """The source key a per-source cache directory belongs to, so the stash
    can say which playlist the channel id resolves against without the URL
    or the key crossing a command line of its own."""
    parent, base = os.path.split(os.path.normpath(directory or ""))
    if os.path.basename(parent) == SOURCES_DIR and SOURCE_KEY_RE.match(base or ""):
        return base
    return ""


# ------------------------------------------------------- process discovery
# `connect()` only ever answers "responsive": it succeeds through the listen
# backlog against a wedged mpv. The authoritative existence check is a /proc
# scan for our exact --input-ipc-server token plus our uid, which is also the
# only way to obtain a pid for an mpv whose IPC is dead - the very case the
# stop ladder exists for.

def proc_cmdline(pid: int) -> list[str]:
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as handle:
            raw = handle.read()
    except OSError:
        return []
    return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]


def proc_start_time(pid: int) -> str:
    """Field 22 of /proc/<pid>/stat, read after the last ')' so a comm
    containing spaces or parentheses cannot shift the fields."""
    try:
        with open("/proc/%d/stat" % pid, "rb") as handle:
            data = handle.read().decode("utf-8", "replace")
    except OSError:
        return ""
    close = data.rfind(")")
    if close == -1:
        return ""
    fields = data[close + 1:].split()
    return fields[19] if len(fields) > 19 else ""


# How far up the parent chain descends_from looks: a wrapper script, a
# sandbox launcher and the player are a handful of levels, never this many.
DESCENT_MAX_DEPTH = 16


def proc_parent(pid: int) -> int:
    """Field 4 of /proc/<pid>/stat (the parent's pid), 0 when unreadable;
    read after the last ')' for the same reason as proc_start_time."""
    try:
        with open("/proc/%d/stat" % pid, "rb") as handle:
            data = handle.read()
    except OSError:
        return 0
    fields = data[data.rfind(b")") + 1:].split()
    try:
        return int(fields[1]) if len(fields) > 1 else 0
    except ValueError:
        return 0


def descends_from(pid: int, ancestor: int) -> bool:
    """Whether `ancestor` is a parent, grandparent ... of `pid`, at most
    DESCENT_MAX_DEPTH levels up. Restart on adoption: the process exec'd as
    `mpv` may be a user's wrapper that runs the real player as its CHILD, and
    that child is the listener the connection reaches (feed_gate)."""
    if ancestor <= 1:
        return False
    current = pid
    for _ in range(DESCENT_MAX_DEPTH):
        current = proc_parent(current)
        if current <= 1:
            return False
        if current == ancestor:
            return True
    return False


def proc_is_ours(pid: int) -> bool:
    try:
        return os.stat("/proc/%d" % pid).st_uid == os.getuid()
    except OSError:
        return False


def find_player(sock_path: str) -> list[dict[str, Any]]:
    """Every live process of ours whose argv carries our exact socket token."""
    token = "--input-ipc-server=%s" % sock_path
    found: list[dict[str, Any]] = []
    try:
        entries = os.listdir("/proc")
    except OSError as error:
        # D-PLY-38: with no descriptor left the scan cannot run, and "no
        # player" would be a false answer a stop reports as done.
        if out_of_descriptors(error):
            raise no_descriptors(error) from None
        return found
    mine = os.getpid()
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid == mine:
            continue
        if token not in proc_cmdline(pid) or not proc_is_ours(pid):
            continue
        found.append({"pid": pid, "startTime": proc_start_time(pid)})
    found.sort(key=lambda record: record["pid"])
    return found


def launch_verdict(pid: Any, sock_path: str) -> str:
    """Whether the process `pid` was launched by THIS build of the helper on
    `sock_path`: "current", "older" or "unknown" (restart on adoption, owner,
    2026-10-31; "older" is ANY player another release or helper build
    launched, owner, 2026-11-01).

    Read off /proc/<pid>/cmdline as BYTES -- proc_cmdline decodes with
    "replace", which would make a state folder whose name is not UTF-8 read
    as another build -- and judged against what this build composes:
      - an empty or unreadable command line is "unknown" (F-HARNESS-41: it is
        briefly empty after exec), and so is one without our exact socket
        token (an impostor, or a test's in-process double);
      - everything BEFORE the token is ignored: real mpv, the harness stub
        (`python3 /x/bin/mpv`), a wrapper that prepends its own options or a
        sandbox launcher all keep our elements whole after it;
      - the tail from the token must BEGIN with this build's composed argv
        less its program name, in either form (no options file, or one
        named), byte for byte. Measured on mpv 0.41.0, windowless (lane RA's
        M1, 2026-11-01): /proc/<pid>/cmdline is the exec argv byte for byte
        in both forms, a 0xff byte in a path element kept, at bind and after
        a load. The one tolerance is the `--screenshot-dir=` element, taken
        from the candidate at the same index when it is one: the only element
        derived from the CALLER's environment (state_dir) rather than from
        the socket path, so two shells on one runtime folder agree.
      - elements AFTER that composition are the user's `mpv` wrapper
        appending its own options (`exec /usr/bin/mpv "$@" --hwdec=auto`),
        and read "current" (D-PLY-61, the lead's decision of 2026-11-02),
        with one exception below. Anything that differs INSIDE the composed
        tail -- an element changed, dropped or moved, another build's marker
        -- is "older".

    What this does and does not protect. Its job is build IDENTITY: no verb
    of this helper feeds a player another build launched (the build gate,
    feed_gate). An older build cannot produce this prefix, because the marker
    element in it carries the version and the CRC of the helper's part
    table, so reading an appended tail as "current" admits no other build's
    player. It does NOT police the user's own wrapper's appended options
    here: a wrapper that appends has taken the pin block's last word
    (D-SINK-13 layer 2) for whatever no read-back holds, because the
    replacement a stricter answer would ask for runs through the same
    wrapper and appends the same tokens again -- that is the user's own
    configuration, PO-5's shape, like a token in mpvArgs. The stricter
    reading this replaced cost such a user a new player window at every
    channel change and every shell restart, and protected nothing. What a
    read-back holds is enforced there whatever this answers: an appended
    `--http-proxy` (mpv takes the last) leaves the player's `http-proxy`
    reading something other than the relay pin, so read_tls_state counts it
    unpinned and every load into that player is refused before any channel
    line (D-SINK-102, 20.3); and an appended `--tls-verify=no` is the
    TLS read-back's (D-SINK-16).

    The exception: a socket option among the appended elements
    (`--input-ipc-server` in any of mpv's spellings) reads "older". mpv obeys
    the LAST one, so a second one after ours re-points the very element this
    reading is anchored on, and the command line no longer shows this build
    launching a player on `sock_path`. The verdict is asked of the process
    that listens on our socket (player_peer), so the only shape that reaches
    it names our own socket again, which no wrapper needs to do; a wrapper
    that names another socket cannot work with the plugin at all (the
    player never binds ours, `no_socket`).

    Rule 5: the word is the whole answer. No element of the candidate's argv
    is returned, logged, put in an exception or compared out loud -- an older
    player's argv holds the user's mpvArgs tokens (before D-SINK-47), and the
    appended elements are the user's own.
    """
    return launch_reading(pid, sock_path)[0]


def launch_reading(pid: Any, sock_path: str) -> tuple[str, int | None]:
    """launch_verdict's word, and beside it the port of the relay pin the
    player was launched with (D-SINK-102) when the word is "current", None
    otherwise. The pin's element is the second tolerance: taken from the
    candidate at its index when it reads exactly
    `--http-proxy=http://127.0.0.1:<port>` (relay_pin_port), because the port
    is the kernel's choice at each spawn, as the screenshot folder is the
    caller's. Any other value there -- another host, a credential, a port
    with a leading zero, no pin at all, which is every player of 0.19.x and
    before -- reads "older". The port is read, never returned out of the
    helper: it names a listener of this uid and nothing private."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return "unknown", None
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as handle:
            raw = handle.read()
    except OSError:
        return "unknown", None
    argv = [part for part in raw.split(b"\0") if part]
    token = os.fsencode("--input-ipc-server=%s" % sock_path)
    if not argv or token not in argv:
        return "unknown", None
    tail = argv[argv.index(token):]
    where = player_dirs(sock_path)
    build = player_build()
    for include in (False, True):
        expected = [os.fsencode(element) for element in compose_launch_argv(sock_path, include, where, build)[1:]]
        if len(tail) < len(expected):
            continue
        head, appended = tail[:len(expected)], tail[len(expected):]
        port = None
        for at, element in enumerate(expected):
            if element.startswith(b"--screenshot-dir=") and head[at].startswith(b"--screenshot-dir="):
                expected[at] = head[at]
            elif element.startswith(RELAY_PIN_PREFIX) and relay_pin_port(head[at]) is not None:
                port = relay_pin_port(head[at])
                expected[at] = head[at]
        if head == expected and port is not None:
            if any(_names_ipc_server(element) for element in appended):
                return "older", None
            return "current", port
    return "older", None


# D-SINK-102: what a relay pin element is, as bytes off /proc.
RELAY_PIN_PREFIX = b"--http-proxy="
_RELAY_PIN_HEAD = b"--http-proxy=http://127.0.0.1:"


def relay_pin_port(element: Any) -> int | None:
    """The port of one argv element when it is exactly the relay pin,
    `--http-proxy=http://127.0.0.1:<1-65535>` in ASCII digits with no leading
    zero, as mpv_relay_pin composes it; None for anything else."""
    if not isinstance(element, bytes) or not element.startswith(_RELAY_PIN_HEAD):
        return None
    digits = element[len(_RELAY_PIN_HEAD):]
    if not 0 < len(digits) <= 5 or not digits.isdigit() or digits.startswith(b"0"):
        return None
    port = int(digits)
    return port if port < 65536 else None


def _names_ipc_server(element: bytes) -> bool:
    """Whether one argv element is mpv's socket option, in any spelling mpv
    takes: `--input-ipc-server=X`, `--input-ipc-server X` and the legacy
    single-dash forms (man mpv, "Legacy option syntax")."""
    return element.lstrip(b"-").split(b"=", 1)[0] == b"input-ipc-server" and element.startswith(b"-")


def still_the_player(record: dict[str, Any], sock_path: str) -> bool:
    """Re-verified immediately before every signal: pid alive, same start
    time, same socket token, same uid - so a recycled pid is never signalled."""
    pid = int(record.get("pid") or 0)
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    if not proc_is_ours(pid):
        return False
    recorded = str(record.get("startTime") or "")
    if recorded and proc_start_time(pid) != recorded:
        return False
    return ("--input-ipc-server=%s" % sock_path) in proc_cmdline(pid)


# ----------------------------------------------------------------- relay

def relay_socket_path(sock_path: str) -> str:
    """D-SINK-102: the player's relay's control socket, beside the player's
    own in the 0700 runtime folder. Refused (`spawn_failed`) when it does not
    fit sun_path, which would otherwise end the spawn with an OSError."""
    path = sock_path + RELAY_SOCKET_SUFFIX
    if len(os.fsencode(path)) > RELAY_SUN_PATH_MAX:
        raise HelperError("spawn_failed", RELAY_PATH_TOO_LONG)
    return path


def relay_request(sock_path: str, request: dict[str, Any], peer: int, timeout: float = RELAY_IPC_S,
                  relay_pid: int = 0) -> dict[str, Any] | None:
    """One request on the relay's control socket, one JSON line each way,
    the whole exchange inside `timeout`. -> the relay's answer, or None when
    there is no answer to trust: no socket, a peer of another uid, a peer
    that is not an ANCESTOR of `peer` (the process the player's own socket
    reaches: the spawn makes the relay the player's parent, and a wrapper's
    child and a backgrounded one stay below it), a line that is not one JSON
    object, or the time ran out. The pid is the kernel's (SO_PEERCRED), which
    names the process that last called listen(2) on that socket: the relay
    listens again at its start, so the spawn that bound it is never named
    (measured: the re-listen moved the answer from the binder to the child).
    Nothing is logged: a request can carry a channel's playlist host.
    With `relay_pid` the relay must be that process instead, for a question
    asked after the player has gone (relay_refused_count). The answer
    carries the relay's pid as `_pid`, for that later question."""
    import socket as sockets
    import struct
    if (not isinstance(peer, int) or peer <= 1) and not (isinstance(relay_pid, int) and relay_pid > 1):
        return None
    try:
        path = relay_socket_path(sock_path)
    except HelperError:
        return None
    deadline = time.monotonic() + max(0.0, timeout)
    conn = sockets.socket(sockets.AF_UNIX, sockets.SOCK_STREAM | sockets.SOCK_CLOEXEC)
    try:
        conn.settimeout(max(0.001, deadline - time.monotonic()))
        conn.connect(path)
        raw = conn.getsockopt(sockets.SOL_SOCKET, sockets.SO_PEERCRED, struct.calcsize("3i"))
        answering, uid, _ = struct.unpack("3i", raw)
        if uid != os.getuid():
            return None
        if relay_pid > 1 and answering != relay_pid:
            return None
        if relay_pid <= 1 and not descends_from(peer, answering):
            return None
        conn.sendall(json.dumps(request, separators=(",", ":")).encode("ascii") + b"\n")
        line = bytearray()
        while b"\n" not in line:
            left = deadline - time.monotonic()
            if left <= 0 or len(line) > RELAY_CONTROL_BYTES:
                return None
            conn.settimeout(left)
            chunk = conn.recv(RELAY_CONTROL_BYTES + 1)
            if not chunk:
                return None
            line += chunk
        reply = json_decode(bytes(line).split(b"\n", 1)[0].decode("utf-8"))
    except (OSError, ValueError, UnicodeError, struct.error):
        return None
    finally:
        conn.close()
    if not isinstance(reply, dict):
        return None
    reply["_pid"] = answering
    return reply


def relay_status(sock_path: str, peer: int, port: int | None, timeout: float = RELAY_IPC_S) -> dict[str, Any] | None:
    """The relay's status when it is THIS player's relay: it answers (an
    ancestor of `peer`, relay_request), and says it serves `port` -- the
    port on the player's own command line -- for this build. None otherwise.

    Asked again until `timeout` runs out, because a relay that has just been
    spawned answers only once its interpreter has started (about 0.3 s idle,
    measured) and listened again: until then a connection is queued under
    the spawn's credentials and refused by the ancestor check, at once. So a
    zap that reaches a player inside its first moments is not read as one
    whose relay is gone, which would replace it."""
    if port is None:
        return None
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        reply = relay_status_once(sock_path, peer, port, deadline - time.monotonic())
        if reply is not None:
            return reply
        if time.monotonic() + SPAWN_POLL_S >= deadline:
            return None
        time.sleep(SPAWN_POLL_S)


def relay_status_once(sock_path: str, peer: int, port: int | None, timeout: float) -> dict[str, Any] | None:
    """relay_status's one question, asked once, its whole exchange inside
    `timeout` (10 ms at the least): the relay's status when it answers as
    the ancestor of `peer` for `port` and this build, None otherwise. A relay
    not yet listening again refuses at once (the ancestor check), so None
    can come long before the bound."""
    if port is None:
        return None
    reply = relay_request(sock_path, {"op": "status"}, peer, max(0.01, timeout))
    if (isinstance(reply, dict) and reply.get("ok") is True and reply.get("port") == port
            and reply.get("build") == player_build()):
        return reply
    return None


def player_verdict(peer: Any, sock_path: str, timeout: float = RELAY_IPC_S) -> str:
    """launch_verdict, and for "current" a relay that answers as this
    player's (relay_status): otherwise "older" (D-SINK-102, decision 16, the
    lead's call under the owner's standing authority of 2026-11-09). So a
    player this build launched whose relay is gone -- killed, or a wrapper's
    child that outlived it -- is replaced, never fed: its pin names a port
    nothing of ours holds, and a plain-http request it sends there carries
    the channel's whole address and headers to whatever binds it next."""
    verdict, port = launch_reading(peer, sock_path)
    if verdict != "current":
        return verdict
    return "current" if relay_status(sock_path, peer, port, timeout) is not None else "older"


# ------------------------------------------------------------------ lock

def player_lock_path(sock_path: str) -> str:
    return os.path.join(os.path.dirname(sock_path), PLAYER_LOCK_FILE)


def runtime_unwritable(what: str, io_error: OSError) -> HelperError:
    """D-PLY-30 (2026-10-27): the player's runtime folder could not be made,
    or its lock file could not be opened, as a refusal with a code rather
    than an OSError left to main()'s catch-all, which answered `internal`
    with the exception's text and the path (`PermissionError: [Errno 13]
    Permission denied: '<runtime>/omarchy-iptv'` under a parent the user
    cannot write). `what` says which of the two and the error's own words
    say why; nothing names the path, which is fixed by the socket path
    ($XDG_RUNTIME_DIR/omarchy-iptv, rule 6) and carries the user's home
    directory when that variable is unset. The shape of D-SRC-69's
    cache_unwritable. A folder that is a link to nothing, or not a folder,
    stays R25c's `folder_unusable` (player_runtime)."""
    reason = io_error.strerror or type(io_error).__name__
    return HelperError("runtime_unwritable", "could not %s (%s)" % (what, reason))


def acquire_lock(path: str, timeout: float) -> int:
    """flock with an inode re-check.

    A plain flock is defeated by unlinking the lock file and recreating it:
    the winner then holds a lock on an orphaned inode while a second launcher
    locks the new one. After every grant we compare fstat(fd) with stat(path)
    and start over when they differ. The kernel releases the lock on any
    death including SIGKILL, so it can never go stale.
    """
    deadline = _monotonic() + max(0.0, float(timeout))
    for _ in range(LOCK_RETRIES):
        # D-PLY-30: a lock file that cannot be opened -- a folder at its
        # name, a file this user may not write, a runtime folder gone from
        # under it -- is a named refusal, not main()'s `internal` with the
        # path. settle_under_lock still reads any failure here as "cannot
        # take the lock" and leaves the socket alone.
        try:
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as io_error:
            raise runtime_unwritable("open the player's lock file", io_error) from None
        try:
            # R23d (rule 15): only a regular file is made 0600, decided on
            # the descriptor. O_RDWR never blocks on a FIFO (Linux), so the
            # open above needs no O_NONBLOCK; the chmod is what is gated.
            if stat.S_ISREG(os.fstat(fd).st_mode):
                os.fchmod(fd, 0o600)
        except OSError:
            pass
        granted = False
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                granted = True
                break
            except OSError as error:
                if error.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                    os.close(fd)
                    raise HelperError("busy", "could not lock the player: %s" % (error.strerror or type(error).__name__))
                if _monotonic() >= deadline:
                    break
                _sleep(LOCK_POLL_S)
        if not granted:
            os.close(fd)
            raise HelperError("busy", "another player command holds the lock")
        try:
            same_inode = os.fstat(fd).st_ino == os.stat(path).st_ino
        except OSError:
            same_inode = False
        if same_inode:
            return fd
        os.close(fd)
        if _monotonic() >= deadline:
            break
    raise HelperError("busy", "the player lock file kept being replaced")


def release_lock(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


def read_lock_record(fd: int) -> dict[str, Any]:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, 4096)
    except OSError:
        return {}
    try:
        document = json_decode(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def read_lock_file(sock_path: str) -> dict[str, Any]:
    """The record without taking the lock (probe is lock-free)."""
    try:
        with os.fdopen(open_regular(player_lock_path(sock_path)), "rb") as handle:
            document = json_decode(handle.read().decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


# The highest intent number the lock record honours (D-PLY-77's review,
# 2026-11-21): 2**31 - 3. The shell holds its counter in a QML `int`
# (Service.qml playSeq), which wraps past 2**31 - 1, and it resyncs to the
# record + 1 (Model.probeVerdict) and issues the record + 2, so this is the
# highest record it can count above (measured through the shipping Model on
# an int property: a record of 2147483645 resyncs to 2147483646 and issues
# 2147483647; one of 2147483646 resyncs to 2147483647 and its next intent
# wraps to `--seq 0`, seqArg's word (model/privacy.mjs) for 0 or less). The
# CLI's `--seq` is an unbounded int and the shell's own last two intents lie
# above this, so neither is refused at the parse; a record above it is read
# as none, as a negative one is.
SEQ_MAX = 2147483645


def record_seq(record: dict[str, Any]) -> int:
    """The record's seq, or 0 (none) for anything that is not one a shell
    can count above: not an integer, below 0, or above SEQ_MAX. So a seq
    typed past what the shell's counter holds (`--seq 100000000000` read as
    1215752192 there, `--seq 2147483647` wrapping it negative) is honoured by
    its own verb's check_seq and outlives it in no record; and a shell that
    counts past SEQ_MAX records its last two intents as none, its wrapped
    intents (`--seq 0`) then leave 0 (write_lock_record) and its next probe
    resyncs it to 1."""
    value = record.get("seq")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > SEQ_MAX:
        return 0
    return value


def write_lock_record(fd: int, seq: int, verb: str) -> None:
    """The record a verb leaves under the lock: the HIGHER of its own seq
    and the one recorded (D-PLY-77, 2026-11-21). A verb on the CLI's default
    `--seq 0` -- `omarchy-iptv player stop` typed in a terminal -- is never
    superseded (check_seq), and it used to write its 0 here, so a stop of the
    shell's issued before a start that had recorded a higher seq, still
    waiting for the lock, passed check_seq after it and laddered that start's
    player. Every seq above 0 that passes check_seq is already at least the
    record's, so only a seq-0 verb is changed: it leaves the record's seq
    where it was. Its readers ask the highest intent the lock has seen: the
    probe's `seq`, which the shell resyncs its playSeq above, and the stop
    look's comparison with the stop's seq; nothing reads `verb` or `at`.
    The recorded one is read through record_seq, so one above SEQ_MAX counts
    as none and the verb's own seq replaces it, a seq-0 verb's included."""
    seq = max(int(seq), record_seq(read_lock_record(fd)))
    payload = json.dumps({"schema": 1, "seq": seq, "verb": verb, "at": int(time.time())})
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        os.truncate(fd, 0)
        os.write(fd, payload.encode("utf-8"))
    except OSError:
        pass


def check_seq(record: dict[str, Any], seq: int, verb: str) -> None:
    """Ordering by issue time, not by lock-grant order (4.10): a verb whose
    intent number is older than the recorded one does nothing at all."""
    if seq > 0 and record_seq(record) > seq:
        raise HelperError("superseded", "intent %d is older than the recorded %d" % (seq, record_seq(record)))


# ----------------------------------------------------------------- spawn

def _read_pipe(fd: int, timeout: float) -> bytes:
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            ready, _, _ = select.select([fd], [], [], remaining)
        except OSError:
            break
        if not ready:
            break
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def player_environment(environ: Any = None) -> dict[str, str]:
    """D-SINK-102: the player's environment, explicit, where it used to be
    inherited whole: the helper's own less the private URL and arguments
    (URL_ENV, ARGS_ENV) and less the two names FFmpeg reads
    (PLAYER_PROXY_ENV), each copied to its uppercase spelling where that is
    absent, so a program the user enabled under the player keeps the user's
    proxy. Nothing is set for FFmpeg: the pin is its only proxy."""
    env = dict(os.environ if environ is None else environ)
    for name in (URL_ENV, ARGS_ENV):
        env.pop(name, None)
    for lower, upper in PLAYER_PROXY_ENV:
        value = env.pop(lower, None)
        if value is not None and upper not in env:
            env[upper] = value
    return env


def relay_argv() -> list[str]:
    """The relay's program and arguments, less `--child=`: this
    interpreter, isolated (`-I`, as Model.helperArgv starts the helper,
    D-SINK-50), on this helper's own stub, resolved through any link. Never
    from argv or the environment, so `player start` is no arbitrary-exec
    verb; no token and no URL, and no `--input-ipc-server=` element, which
    find_player would read as a player."""
    stub = globals().get("__file__") or ""
    return [sys.executable or "python3", "-I", os.path.realpath(stub), "player", "relay"]


PR_SET_PDEATHSIG = 1


def _prctl() -> Any:
    """libc's prctl, resolved before a fork so the child calls it without
    loading anything; None where it cannot be had."""
    try:
        import ctypes
        return ctypes.CDLL(None, use_errno=True).prctl
    except (ImportError, OSError, AttributeError):
        return None


def spawn_player(argv: list[str], cwd: str, proxy_fd: int, control_fd: int,
                 env: dict[str, str] | None = None) -> dict[str, Any]:
    """setsid + double fork, and the fd hygiene that makes it survivable.

    The grandchild reports its own pid over a pipe (so a spawn that never
    binds a socket is still reapable by the helper that created it), reports
    an exec failure over a CLOEXEC pipe (restoring the error
    Quickshell.execDetached throws away - it returns void), keeps its stderr
    on a pipe for the launch window only (PO-6), puts /dev/null on stdin and
    stdout and closes every other inherited descriptor before execvp - which
    is what guarantees mpv never holds a Quickshell StdioCollector pipe for
    hours and dies of BrokenPipeError at the restart it exists to survive.

    argv[0] is the literal "mpv", never caller-supplied, so `player start` is
    not an arbitrary-exec verb.

    D-SINK-39: the grandchild sets RLIMIT_CORE to (0, 0) as its last act
    before the exec (disable_core_dumps says why both halves), because the
    non-dumpable flag this helper runs under does not survive an exec and a
    crashed player's core would carry the credentialed URL and the provider
    headers to /var/lib/systemd/coredump, readable by the whole uid.

    PO-11: the working directory is explicit, never inherited. A process that
    inherits the shell's cwd is running in the user's home, and mpv's own key
    bindings write files relative to it. The umask is explicit for the same
    reason: mpv creates whatever it writes with the process umask, which is
    0022 under the shell and gave D-PLY-7 its world-readable 0644 screenshot.
    0o077 puts every file the player creates at 0600 and every directory it
    creates at 0700, matching requirement 10. `chdir` failing must never
    leave us in the inherited directory, so "/" is the fallback.

    D-PLY-31 (2026-10-28): the three pipes and the first fork are this
    process's own, and their failure -- no descriptor left for a pipe
    (EMFILE, ENFILE), no process to fork (EAGAIN under RLIMIT_NPROC, ENOMEM)
    -- used to leave an OSError to main()'s catch-all, `internal`, which the
    shell reads as "Helper failed unexpectedly". It is `spawn_failed` with
    the error's words, the code and the message shape the grandchild's
    failures already have (its own fork, its setsid, the exec all come back
    over err_w as `could not start mpv: <words>`), because to the user it is
    the same fact: the player program could not be started. Whatever was
    opened before the failure is closed first.

    D-SINK-102 (2026-11-14): the grandchild is now the player's RELAY and
    the player its child (spawn_detached is gone; this generalises it). The
    grandchild G hands the two listeners the helper bound, `proxy_fd` and
    `control_fd`, to fds 3 and 4, and forks the player M, which:
      * asks for SIGKILL when its parent thread ends (PR_SET_PDEATHSIG) and
        then checks that its parent is still G, so a dead relay takes its
        player with it and a pinned port is never left for another account
        to bind (measured: gone in about 5 ms after a SIGKILL of its parent,
        across mpv's exec; the setting is not inherited by a child M forks,
        which is the wrapper residual stated in ARCHITECTURE-PLAYER);
      * closes 3 and 4, puts the launch-window pipe on stderr, reports its
        pid, sets RLIMIT_CORE (0, 0) and execs mpv with `env`, the explicit
        environment (player_environment), where execvp inherited everything.
    G is a child subreaper from before that fork (a wrapper that backgrounds
    the player and exits leaves it G's), and then sets its own core limit,
    points stderr at /dev/null and execs the relay (relay_argv) with `--child=<M>`. An exec
    failure comes back as `m<errno>` for the player and `r<errno>` for the
    relay; after the second G kills M first. The player and the relay start
    in parallel, so the relay's interpreter is off the launch path; a
    connection the player makes before the relay accepts waits in the
    listener's backlog. -> pid (M's) and stderrFd. The relay's pid is not
    returned: the helper learns it only from the relay's own answer on its
    control socket (SO_PEERCRED, relay_register), never off M's ancestry."""
    opened: list[int] = []
    prctl = _prctl()
    player_env = player_environment() if env is None else env
    relay_env = dict(os.environ)
    for name in (URL_ENV, ARGS_ENV):
        relay_env.pop(name, None)
    relay = relay_argv()
    try:
        pid_r, pid_w = os.pipe()
        opened += [pid_r, pid_w]
        err_r, err_w = os.pipe2(os.O_CLOEXEC)
        opened += [err_r, err_w]
        log_r, log_w = os.pipe()
        opened += [log_r, log_w]
        child = os.fork()
    except OSError as error:
        for fd in opened:
            try:
                os.close(fd)
            except OSError:
                pass
        raise HelperError("spawn_failed", "could not start mpv: %s" % (error.strerror or type(error).__name__)) from None
    if child == 0:                                        # pragma: no cover
        stage = "m"
        try:
            os.setsid()
            if os.fork() > 0:
                os._exit(0)
            relay_pid = os.getpid()
            # The leader of its own process group, which the player and
            # whatever it starts join: the relay passes a SIGTERM to that
            # group (player_relay), so a wrapper's child hears it too. The
            # group holds nothing the spawn did not start.
            os.setpgid(0, 0)
            os.umask(PLAYER_UMASK)
            try:
                os.chdir(cwd or "/")
            except OSError:
                os.chdir("/")
            # Every descriptor this needs, moved above the two fixed numbers
            # first, so handing the listeners to 3 and 4 cannot land on one.
            held = [fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 10)
                    for fd in (pid_w, err_w, log_w, proxy_fd, control_fd)]
            pid_w, err_w, log_w, proxy_high, control_high = held
            devnull = fcntl.fcntl(os.open(os.devnull, os.O_RDWR | os.O_CLOEXEC), fcntl.F_DUPFD_CLOEXEC, 10)
            held.append(devnull)
            os.dup2(devnull, 0)
            os.dup2(devnull, 1)
            os.dup2(log_w, 2)
            os.dup2(proxy_high, 3)
            os.dup2(control_high, 4)
            # Once this helper exits nobody reads that pipe; an ignored
            # SIGPIPE (inherited through execve) keeps a failed diagnostic
            # write from ever killing the player.
            signal.signal(signal.SIGPIPE, signal.SIG_IGN)
            try:
                limit = int(os.sysconf("SC_OPEN_MAX"))
            except (ValueError, OSError):
                limit = 4096
            for fd in range(5, min(limit, 4096)):
                if fd in held:
                    continue
                try:
                    os.close(fd)
                except OSError:
                    pass
            # A child subreaper BEFORE the player is forked, so a wrapper that
            # backgrounds the real player and exits at once leaves it this
            # relay's child, whichever exits first.
            if prctl is not None:
                prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0)
            player = os.fork()
            if player == 0:
                # The player. Its death signal first, then the check that
                # its parent is still the relay: a parent gone before the
                # prctl would leave it with no death signal at all.
                if prctl is None or prctl(PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0) != 0:
                    raise OSError(errno.EPERM, "no death signal")
                if os.getppid() != relay_pid:
                    os._exit(127)
                os.close(3)
                os.close(4)
                os.write(pid_w, str(os.getpid()).encode("ascii"))
                os.close(pid_w)
                # D-SINK-39: the player is the one child that holds the
                # stream URL and the provider headers, and a crash of it
                # would hand them to systemd-coredump, durably and readable
                # by every process of this uid. Set HERE, after the fork
                # and before the exec, so the helper's own limits are
                # untouched; a failure is reported over err_w like an exec
                # failure and the player does not start.
                disable_core_dumps()
                os.execvpe("mpv", argv, player_env)
            # The relay.
            stage = "r"
            os.close(pid_w)
            disable_core_dumps()
            os.dup2(devnull, 2)
            try:
                os.execve(relay[0], relay + ["--child=%d" % player], relay_env)
            except BaseException:
                try:
                    os.kill(player, signal.SIGKILL)
                except OSError:
                    pass
                raise
        except BaseException as error:                    # noqa: BLE001 - reported over the pipe
            number = getattr(error, "errno", 0) or 0
            try:
                os.write(err_w, ("%s%d" % (stage, int(number))).encode("ascii"))
            except OSError:
                pass
        os._exit(127)
    os.close(pid_w)
    os.close(err_w)
    os.close(log_w)
    try:
        os.waitpid(child, 0)                              # the intermediate child, never a zombie
    except OSError:
        pass
    pid_text = _read_pipe(pid_r, SPAWN_PID_TIMEOUT).decode("ascii", "replace").strip()
    os.close(pid_r)
    failure = _read_pipe(err_r, DEFAULT_SPAWN_TIMEOUT).decode("ascii", "replace").strip()
    os.close(err_r)
    pid = int(pid_text) if pid_text.isdigit() else 0
    if failure:
        os.close(log_r)
        stage, digits = failure[:1], failure[1:]
        number = int(digits) if digits.isdigit() else 0
        if stage == "r":
            raise HelperError("spawn_failed", "%s: %s" % (RELAY_SPAWN_FAILED, os.strerror(number) if number else "exec failed"))
        if number == errno.ENOENT:
            raise HelperError("mpv_missing", "mpv is not installed")
        raise HelperError("spawn_failed", "could not start mpv: %s" % (os.strerror(number) if number else "exec failed"))
    if pid <= 0:
        os.close(log_r)
        raise HelperError("spawn_failed", "the player did not report a pid")
    os.set_blocking(log_r, False)
    return {"pid": pid, "stderrFd": log_r}


# The un-redacted tail of a partial line, per fd, between calls to
# drain_launch_stderr. It exists because redaction is not distributive over a
# split: redact(a) + redact(b) is not redact(a + b) when a URL straddles the
# boundary. The old code redacted each 4096-byte os.read separately and a
# stream whose URL crossed a read left `http://host.example/li` in the buffer
# -- the path, which rule 5 says never leaves the helper -- and, at another
# offset, the username. Same defect class as the clean_detail cut-before-
# redact blocker, at a sink that reaches a desktop notification through
# launch_reason (D-SINK-12).
#
# Bounded: a tail is at most one line, and a line longer than
# LAUNCH_STDERR_MAX is redacted and flushed rather than grown, so a single
# newline-free stream cannot hold memory open.
_LAUNCH_TAIL: dict[int, str] = {}


def drain_launch_stderr(fd: int, buffer: list[str]) -> None:
    """PO-6: whatever mpv said while starting, redacted, memory only, capped.

    Kept drained so a chatty mpv can never block on a full pipe. Redacts
    whole LINES, carrying an unterminated one to the next call, because mpv's
    stderr is line-oriented and a URL never spans a newline.
    """
    def keep(text: str) -> None:
        room = LAUNCH_STDERR_MAX - sum(len(part) for part in buffer)
        if room > 0:
            buffer.append(text[:room])

    pending = _LAUNCH_TAIL.pop(fd, "")
    while True:
        try:
            chunk = os.read(fd, 4096)
        except (BlockingIOError, OSError):
            break
        if not chunk:
            # EOF: whatever is left is a whole line as far as this fd goes.
            if pending:
                keep(redact_urls(pending))
            return
        pending += chunk.decode("utf-8", "replace")
        head, sep, tail = pending.rpartition("\n")
        if sep:
            keep(redact_urls(head + sep))
            pending = tail
        if len(pending) > LAUNCH_STDERR_MAX:
            # A single line longer than the whole budget. It is DROPPED, not
            # flushed: emitting it would mean redacting a fragment that may be
            # cut mid-URL, which is the defect this function was repaired for.
            # Measured while repairing it -- flushing the over-long partial
            # leaked at 33 of 48 boundary offsets, because the flush itself is
            # a cut. Nothing a person would read is lost: launch_reason wants
            # mpv's last LINE, and a newline-free blob of this size is not one.
            pending = ""
    if pending:
        _LAUNCH_TAIL[fd] = pending


# D-PLY-29: a line that only warns is not the reason. Model.playerLogWarning
# is the same pattern (exact cases on purpose: the two languages fold case
# differently outside ASCII); the shared fixture player-endings.json (dev
# branch tests), its `tailWarnings` section, holds both to it.
PLAYER_WARNING_RE = re.compile(r"(?:\[[^\]]*\] )?(?:[A-Za-z0-9_.-]+: )*(?:warning|Warning|WARNING):")


def player_log_warning(line: str) -> bool:
    return PLAYER_WARNING_RE.match(str(line)) is not None


def launch_reason(buffer: list[str]) -> str:
    """mpv's last stderr line that is not a warning (a driver's warning is
    what software GL writes there), or its last line when all of them warn."""
    lines = [line.strip() for line in "".join(buffer).splitlines() if line.strip()]
    for line in reversed(lines):
        if not player_log_warning(line):
            return line
    return lines[-1] if lines else ""


# ------------------------------------------------------------ connection

def probe_client(sock_path: str, ipc_timeout: float) -> MpvIpc | None:
    """A connected client that actually answered, or None."""
    client = MpvIpc(sock_path, ipc_timeout)
    try:
        client.connect()
        ok, _ = client.try_command("get_property", "mpv-version")
        if ok:
            return client
    except HelperError as error:
        if error.code == "no_descriptors":
            # D-PLY-38: the helper could not look, which is not "the player
            # does not answer" -- adopt_or_spawn stops such a player.
            client.close()
            raise
    client.close()
    return None


def wait_for_socket(sock_path: str, timeout: float, ipc_timeout: float,
                    stderr_fd: int = -1, stderr_buffer: list[str] | None = None) -> MpvIpc | None:
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        if stderr_fd >= 0 and stderr_buffer is not None:
            drain_launch_stderr(stderr_fd, stderr_buffer)
        try:
            client = probe_client(sock_path, ipc_timeout)
        except HelperError:
            # no_descriptors (D-PLY-38), after a spawn: read as "not yet",
            # so the wait stays bounded and the caller reaps what it
            # launched instead of leaving it behind an error.
            client = None
        if client is not None:
            return client
        if time.monotonic() >= deadline:
            return None
        time.sleep(SPAWN_POLL_S)


def quit_over_ipc(sock_path: str, ipc_timeout: float) -> bool:
    client = MpvIpc(sock_path, ipc_timeout)
    try:
        client.connect()
        client.request(["quit"], allow_close=True)
        return True
    except HelperError:
        return False
    finally:
        client.close()


def socket_is_dead(sock_path: str) -> bool:
    client = MpvIpc(sock_path, SETTLE_CONNECT_TIMEOUT)
    try:
        client.connect()
    except HelperError:
        return client.refused or not os.path.exists(sock_path)
    finally:
        client.close()
    return False


def settle_socket(sock_path: str, deadline: float | None = None) -> bool:
    """Unlink the socket only once nothing is listening and nothing of ours
    is running (S_ISSOCK-guarded), so a racing start's fresh socket is never
    deleted. mpv never unlinks its own socket on any exit path.

    D-PLY-8: after a SIGKILL those two facts do not become true at the same
    instant. A killed process runs exit_mm first, so its command line is
    already empty at the first sample - 0.13-0.31 ms, 8/8 on real headless
    mpv 0.41 here - while its listening socket stays bound for another
    2.7-4.9 ms (and far longer for a windowed player, which tears down a GPU
    context, a Wayland connection and decoder buffers as well). The stop path
    asks both questions 4.5-7.5 ms after the kill: one /proc scan (3.7-4.9 ms
    for 225 pids on this box) after wait_for_exit wins on its first check.
    Ask once and the answer can be "not yet", after which nothing asks again
    and the socket file is left on disk until the next helper call.

    So with a `deadline` both guards are re-checked until they agree or the
    time is up. This NEVER widens the conditions - a racing spawn seen by
    find_player, a successful connect (a wedged player answering through its
    backlog) and a timed-out connect all still block the unlink, every
    iteration - it only stops giving up after one look.

    With `deadline=None` the behaviour is byte-identical to before: one check
    of each guard, no sleep. That is what every call site outside the stop
    ladder gets.

    The deadline is absolute and comes from the rung that is already waiting
    (4.9), so the settle spends time the ladder had reserved and never adds
    any. Worst case it overruns by one refused-connect timeout, the 0.2 s
    inside socket_is_dead, which is bounded and cannot repeat.
    """
    while True:
        if find_player(sock_path):
            return False
        if socket_is_dead(sock_path):
            return unlink_stale_socket(sock_path)
        if deadline is None or _monotonic() >= deadline:
            return False
        _sleep(min(STOP_POLL_S, max(0.0, deadline - _monotonic())))


def settle_under_lock(sock_path: str, deadline: float | None = None,
                      lock_timeout: float = SETTLE_LOCK_TIMEOUT, relay: bool = False) -> bool:
    """The settle for the two call sites that hold no lock of their own
    (X1/X2, ruling CL8).

    The unlink is only safe with the player lock held across the check AND
    the unlink: a `player start` that binds a fresh socket between this
    settle's refused connect and its os.unlink would have the NEW socket
    deleted. player_stop has always been safe that way (it settles inside its
    own lock); player_probe and player_orphan_check were not.

    A call site that cannot take the lock does not unlink. Another verb owns
    the socket at this instant and will settle it itself, and neither of
    these two verbs is worth failing over a leftover file.

    `relay` (D-SINK-102): the relay socket too, under the same lock and only
    while no player is left on the socket to have a relay (a start that
    took the lock before this one has spawned its own, and bound its own
    relay socket), as player_stop removes it. The orphan check passes it
    after stopping a player whose relay was killed, which never removes its
    own.
    """
    try:
        lock_fd = acquire_lock(player_lock_path(sock_path), lock_timeout)
    except (HelperError, OSError):
        return False
    try:
        settled = settle_socket(sock_path, deadline)
        if relay and not find_player(sock_path):
            unlink_relay_socket(sock_path)
        return settled
    finally:
        release_lock(lock_fd)


def wait_for_exit(targets: list[dict[str, Any]], sock_path: str, wait_ms: int) -> bool:
    deadline = _monotonic() + max(0, int(wait_ms)) / 1000.0
    while True:
        if not any(still_the_player(record, sock_path) for record in targets):
            return True
        if _monotonic() >= deadline:
            return False
        _sleep(STOP_POLL_S)


def signal_targets(targets: list[dict[str, Any]], sock_path: str, number: int) -> bool:
    sent = False
    for record in targets:
        if not still_the_player(record, sock_path):
            continue
        try:
            os.kill(int(record["pid"]), number)
            sent = True
        except OSError:
            continue
    return sent


STOP_STAGE_BEFORE = {"": "", "quit": "", "term": "quit", "kill": "term"}


def stop_ladder(sock_path: str, targets: list[dict[str, Any]], from_rung: str = "",
                ipc_timeout: float = DEFAULT_IPC_TIMEOUT) -> dict[str, Any]:
    """The whole D-LIVE-17 ladder inside one process (4.9).

    quit at 0, SIGTERM at 2 s, SIGKILL at 4 s - the same timeline as today,
    but no rung can be starved by a busy control channel, the ladder finishes
    even if the shell dies one millisecond after issuing it, and the pid comes
    from /proc rather than from `get_property pid`, so a wedged mpv (the case
    the ladder exists for, where IPC is by definition dead) is reachable.
    `stop_escalation()` drives the rungs so the shared vectors really govern.

    `deadline` in the reply is the absolute monotonic instant the rung that
    actually ran would have kept waiting until. The kill rung reserves 500 ms
    (`stop_escalation("term")` gives waitMs 0, so `grace` falls back to
    STOP_SETTLE_MS) and spends about 0.3 ms of it, because wait_for_exit
    checks before it sleeps and a killed process is gone at once. Handing
    that instant to the settle (D-PLY-8) spends time the ladder had already
    reserved rather than adding any, so the stop cannot run longer than the
    published timeline whatever the teardown does.
    """
    result: dict[str, Any] = {"rung": "", "running": True, "deadline": None}
    stage = STOP_STAGE_BEFORE.get(from_rung or "", "")
    for _ in range(3):
        step = stop_escalation(stage)
        action = str(step["action"])
        # Each rung's grace is measured from the rung's OWN start, so the
        # next one lands where the timeline says it does. The quit rung is
        # the reason: against an unresponsive player `request(["quit"])`
        # spends the whole --ipc-timeout before anything is waited for, and
        # that cost sat OUTSIDE the 2 s grace - so SIGTERM arrived at 4 s,
        # SIGKILL at 6 s, and a wedged player took ~6.27 s to reap against a
        # 4.5 s budget. Counting it inside costs a responsive player nothing
        # (it answers `quit` at once and exits in about a third of a second,
        # with the full grace still ahead of it) and keeps the guarantee
        # that it is asked politely first.
        rung_started = _monotonic()
        grace = int(step["waitMs"]) or STOP_SETTLE_MS
        # Recorded before the rung acts, so every exit below reports the
        # window this rung owned - including the one where there was nothing
        # left to signal, which is precisely when a socket can still be bound
        # by a process the finder can no longer see.
        result["deadline"] = rung_started + grace / 1000.0
        if action == "quit":
            quit_over_ipc(sock_path, ipc_timeout)
            result["rung"] = "quit"
        elif step["signal"]:
            if not signal_targets(targets, sock_path, int(step["signal"])):
                result["running"] = False
                return result
            result["rung"] = action
        else:
            break
        spent = int((_monotonic() - rung_started) * 1000.0)
        if wait_for_exit(targets, sock_path, max(0, grace - spent)):
            result["running"] = False
            return result
        stage = action
    result["deadline"] = _monotonic() + STOP_SETTLE_MS / 1000.0
    result["running"] = not wait_for_exit(targets, sock_path, STOP_SETTLE_MS)
    return result


# ---- D-PLY-39 (2026-11-18): each watched verb's bound, from this helper ----
#
# Model.playerWatchdogMs(verb) is the shell's watchdog over a verb: the
# verb's longest path through this code with every wait it survives at its
# bound, and a margin for what no bound cuts. These are the same sums, from
# this helper's own constants and without the margin, so the deadline a verb
# runs under (verb_deadline) is the watchdog less the margin by construction;
# the shared player-bounds fixture (dev branch) holds both sides to the same
# numbers (watchdogMs less marginMs) and its walk holds the verbs inside them.
# model/player.mjs says why each term is there.
CONTROL_SLOT_VERBS = ("play", "status", "pause", "tracks", "seek")


def _bound_ms(seconds: float) -> int:
    return int(round(seconds * 1000))


def player_ladder_ms(from_rung: str) -> int:
    """Model.playerLadderMs: the stop ladder's longest run from its first
    rung, "" (quit) or "term"."""
    tail = STOP_KILL_GRACE_MS + 2 * STOP_SETTLE_MS
    if from_rung == "term":
        return tail
    return max(STOP_QUIT_GRACE_MS, 2 * _bound_ms(DEFAULT_IPC_TIMEOUT)) + tail


def player_verb_bound_ms(verb: str) -> int:
    """A watched verb's bound in ms (Model.playerVerbBoundMs): `start`,
    `restart`, `probe`, `stop`, or one of the control slot's verbs, which
    share its one watchdog and so its bound. Anything else is a ValueError:
    a verb with no bound has no deadline to run under."""
    ipc = _bound_ms(DEFAULT_IPC_TIMEOUT)
    lock = _bound_ms(DEFAULT_LOCK_TIMEOUT) + _bound_ms(LOCK_POLL_S)
    settle_connect = _bound_ms(SETTLE_CONNECT_TIMEOUT)
    relay_ipc = _bound_ms(RELAY_IPC_S)
    lookup = _bound_ms(STREAM_LOOKUP_TIMEOUT_S)
    spawn = settle_connect + _bound_ms(SPAWN_PID_TIMEOUT) + 2 * _bound_ms(DEFAULT_SPAWN_TIMEOUT) + 2 * ipc
    tail = max(player_ladder_ms("term") + settle_connect, ipc + _bound_ms(DEFAULT_FIRST_LOAD_TIMEOUT))
    carry = 2 * ipc
    relay = _bound_ms(RELAY_START_S) + 3 * relay_ipc
    if verb == "start":
        return lookup + lock + 2 * ipc + carry + player_ladder_ms("") + spawn + tail + relay
    if verb == "restart":
        return (lookup + lock + player_ladder_ms("term") + settle_connect + 2 * ipc + player_ladder_ms("")
                + spawn + tail + relay)
    if verb == "probe":
        return max(3 * ipc, _bound_ms(SETTLE_LOCK_TIMEOUT) + _bound_ms(LOCK_POLL_S) + settle_connect) + relay_ipc
    if verb == "stop":
        return lock + player_ladder_ms("") + settle_connect
    if verb in CONTROL_SLOT_VERBS:
        return lookup + 2 * relay_ipc + _bound_ms(CONTROL_IPC_S)
    raise ValueError("no bound for player verb %r" % (verb,))


def player_verb_reserve_ms(verb: str) -> int:
    """What a watched verb may still spend, uncut by its mpv deadline, after
    its last wait on mpv ends or is refused, in ms. A start or a restart:
    the first-load window and the first-load count it asks the relay
    (DEFAULT_FIRST_LOAD_TIMEOUT + RELAY_IPC_S) after a load, or the ladder
    from term that stops a spawn it fed nothing (stop_fresh_spawn, with a
    settle's connect), whichever is longer. `status`: the relay question it
    asks after its reads (status_relay). Every other: nothing -- the probe's
    and `play`'s questions to the relay, and the lookup, come before their
    mpv waits end, and their refusals only print."""
    if verb in ("start", "restart"):
        return max(_bound_ms(DEFAULT_FIRST_LOAD_TIMEOUT) + _bound_ms(RELAY_IPC_S),
                   player_ladder_ms("term") + _bound_ms(SETTLE_CONNECT_TIMEOUT))
    if verb == "status":
        return _bound_ms(RELAY_IPC_S)
    return 0


def player_verb_ipc_span_ms(verb: str) -> int:
    """How long after a watched verb begins its waits on mpv must be over:
    its bound less its reserve (verb_deadline)."""
    return player_verb_bound_ms(verb) - player_verb_reserve_ms(verb)


