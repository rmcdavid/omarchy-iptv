"""D-SINK-102 (the marketplace maintainer on omacom/omarchy-plugin-marketplace
#14290, against 0.19.1): the player is pinned to a relay the helper runs as
its HTTP proxy, and the launch path, the load and the adoption are bound to
it. tests/test_relay.py holds the relay itself; this module holds what the
player side does with it, through the shipping functions and verbs:

  * the build gate reads a player as this build's only when its relay
    answers as the player's (player_verdict);
  * the spawn makes the player the relay's child, with an environment that
    names no proxy FFmpeg reads, and a dead relay takes its player with it;
  * every load registers a token before anything about a channel, carries it
    per file, and refuses a player whose proxy reads anything else;
  * a channel of a scheme that never asks a proxy is handed the address it
    was judged by, and one whose connections nothing here can judge is
    refused from a playlist that is not local;
  * a start whose first load the relay refused is the channel's own refusal;
  * the probe says whether the relay answered, the orphan check stops a
    player of this build whose relay is gone, and a stop removes a socket a
    killed relay left.

Nothing here asks a real resolver: the play-time lookup is the suite's
stand-in or a Resolver whose answers the test states, and every target the
relay is asked to reach is an IP literal. Players are the stub mpv or a
FakeMpv on scratch sockets under /tmp, never the default socket.

Run: python3 -m unittest discover -s tests
"""
import base64
import json
import os
import pathlib
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import FakeRelay, loopback_reads_public  # noqa: E402
import test_mpv  # noqa: E402
import test_player  # noqa: E402
import test_stream_lookup  # noqa: E402
from test_mpv import (FakeMpv, IdentitySeam, MpvTestCase, PINNED_CMDLINE, current_props, hold_launch,  # noqa: E402
                      run)

helper = test_mpv.helper
LEAK = "qqqqqq"


def literal_lookups_only(real):
    """resolve_within for this module, in both helper instances it uses: the
    real one for an IP literal, which getaddrinfo answers without a query,
    and a failure for any name. Nothing here should ever ask it a name --
    the play-time lookup is a stand-in, the relay's is stream_resolve -- so a
    name reaching it is a test, or a tree (a red-first run against code with
    no seam), that would have asked a real resolver."""
    import ipaddress

    def lookup(host, port, timeout):
        text = host.decode("utf-8", "replace") if isinstance(host, bytes) else str(host)
        try:
            ipaddress.ip_address(text.split("%", 1)[0])
        except ValueError:
            raise AssertionError("a name reached resolve_within: %r" % (host,)) from None
        return real(host, port, timeout)
    return lookup


_GUARDS = [mock.patch.object(module, "resolve_within", literal_lookups_only(module.resolve_within))
           for module in (helper, test_stream_lookup.helper)]


def setUpModule():
    for guard in _GUARDS:
        guard.start()


def tearDownModule():
    for guard in _GUARDS:
        guard.stop()


def proc_environ(pid):
    with open("/proc/%d/environ" % pid, "rb") as handle:
        return dict(item.split(b"=", 1) for item in handle.read().split(b"\0") if b"=" in item)


def gone(pid, wait):
    """Whether `pid` has exited (or is a zombie) within `wait` seconds."""
    until = time.monotonic() + wait
    while time.monotonic() < until:
        try:
            with open("/proc/%d/stat" % pid, "rb") as handle:
                if handle.read().rsplit(b")", 1)[1].split()[0] == b"Z":
                    return True
        except OSError:
            return True
        time.sleep(0.02)
    return False


def relay_pidfd(relay, player):
    """A pidfd for `relay`, opened only once its command line reads as the
    relay this player was launched under (`... player relay --child=<player>`),
    so a signal sent through it can reach nothing else.

    Never signal a pid read off another process's parent. A player the old
    launch path double-forked away is reparented to the nearest subreaper,
    which is the user's own `systemd --user` manager. Run against 7c1784c (the
    red-first run), this test took the player's parent for the relay and
    SIGKILLed the user manager: the whole desktop session ended, three times on
    2026-11-14/15. The pidfd pins the process, so the pid cannot be reused
    between the check and the signal."""
    if relay <= 1:
        raise AssertionError("no relay pid to signal: %r" % relay)
    fd = os.pidfd_open(relay)
    try:
        raw = pathlib.Path("/proc/%d/cmdline" % relay).read_bytes().split(b"\0")
        argv = [os.fsdecode(a) for a in raw if a]
        if argv[-3:] != ["player", "relay", "--child=%d" % player]:
            raise AssertionError("pid %d is not this player's relay (argv[0] %r); not signalling it"
                                 % (relay, argv[:1]))
        # Still the process the pidfd holds: had it exited between the open
        # and the read, the command line read could be a reused pid's.
        signal.pidfd_send_signal(fd, 0)
    except BaseException:
        os.close(fd)
        raise
    return fd


def pidfd_naming(pid, token):
    """A pidfd for `pid`, a process this test started, once its command line
    holds `token` (bytes); the cleanup signals through it and nothing else, so
    a pid reused after the process has gone is never reached."""
    fd = os.pidfd_open(pid)
    try:
        if token not in pathlib.Path("/proc/%d/cmdline" % pid).read_bytes().split(b"\0"):
            raise AssertionError("pid %d does not name %r; not signalling it" % (pid, token))
        signal.pidfd_send_signal(fd, 0)
    except BaseException:
        os.close(fd)
        raise
    return fd


def kill_through(fd):
    """SIGKILL through a pidfd, and close it; a process already gone is fine."""
    try:
        signal.pidfd_send_signal(fd, signal.SIGKILL)
    except OSError:
        pass
    finally:
        os.close(fd)


def proxied_request(port, token, target):
    """One absolute-form GET to the relay at `port` for `target` (an
    http://<literal>:<port>/ URL), as FFmpeg sends it after the 407, and the
    relay's whole answer."""
    auth = base64.b64encode(("iptv:%s" % token).encode("ascii")).decode("ascii")
    head = "GET %s HTTP/1.1\r\nHost: x\r\nProxy-Authorization: Basic %s\r\n\r\n" % (target, auth)
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(head.encode("ascii"))
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                return data
            data += chunk


# ---- the gate reads the relay ------------------------------------------------

class PlayerVerdictTest(IdentitySeam, unittest.TestCase):
    """player_verdict over real processes holding a launch argv, and the
    helper's own relay code in this process (FakeRelay), which is their
    parent as the spawn makes the real relay the player's."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="omarchy-iptv-verdict-", dir="/tmp")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, True))
        self.sock = os.path.join(self.dir, "run", "mpv.sock")
        os.makedirs(os.path.dirname(self.sock), 0o700)
        self.install_identity_seam(helper)

    def holder(self, port):
        process = hold_launch(self.sock, "current", relay_port=port)
        self.addCleanup(self.reap_holder, process)
        return process

    def test_a_current_player_whose_relay_answers_reads_current(self):
        relay = self.relay_for(self.sock)
        process = self.holder(relay.port)
        self.assertEqual(helper.launch_reading(process.pid, self.sock), ("current", relay.port))
        self.assertEqual(helper.player_verdict(process.pid, self.sock), "current")

    def test_a_player_whose_relay_is_gone_reads_older(self):
        relay = self.relay_for(self.sock)
        process = self.holder(relay.port)
        relay.close()
        started = time.monotonic()
        self.assertEqual(helper.player_verdict(process.pid, self.sock, timeout=0.3), "older")
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(helper.launch_verdict(process.pid, self.sock), "current")

    def test_a_relay_that_is_not_the_players_ancestor_reads_older(self):
        """The holder is started by an intermediate that exits at once, so
        it is reparented away from this process, and the relay this process
        runs is no ancestor of it: a relay socket someone else answers."""
        relay = self.relay_for(self.sock)
        argv = test_mpv.launch_argv(self.sock, "current", relay.port)
        code = ("import subprocess, sys\np = subprocess.Popen([sys.executable, '-c', %r] + sys.argv[1:],"
                " stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\nprint(p.pid)\n"
                % test_mpv.HOLDER_CODE)
        out = subprocess.run([sys.executable, "-c", code, "-"] + argv[1:], capture_output=True, text=True, timeout=10)
        pid = int(out.stdout.strip())
        token = os.fsencode("--input-ipc-server=%s" % self.sock)
        until = time.monotonic() + 5
        while time.monotonic() < until and token not in pathlib.Path("/proc/%d/cmdline" % pid).read_bytes().split(b"\0"):
            time.sleep(0.01)
        # The holder this test started, by the pid its intermediate printed,
        # pinned once its command line names this test's socket.
        self.addCleanup(kill_through, pidfd_naming(pid, token))
        self.assertFalse(helper.descends_from(pid, os.getpid()))
        self.assertEqual(helper.launch_reading(pid, self.sock), ("current", relay.port))
        self.assertEqual(helper.player_verdict(pid, self.sock, timeout=0.3), "older")

    def test_a_relay_serving_another_port_reads_older(self):
        relay = self.relay_for(self.sock)
        process = self.holder(relay.port + 1 if relay.port < 65535 else relay.port - 1)
        self.assertEqual(helper.player_verdict(process.pid, self.sock, timeout=0.3), "older")

    def test_a_relay_another_build_loaded_reads_older(self):
        relay = self.relay_for(self.sock)
        process = self.holder(relay.port)
        relay.state.build = "0.19.1+ffffffff"
        self.assertEqual(helper.player_verdict(process.pid, self.sock, timeout=0.3), "older")


# ---- the spawn ---------------------------------------------------------------

class SpawnPlayerTest(test_player.PlayerTestCase):
    """The shipping `player start` against the stub mpv on PATH: the spawn
    starts the REAL relay (`player relay`, this helper) as the player's
    parent. The kernel is asked, not the code."""

    def start_player(self):
        code, payload, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        found = helper.find_player(self.sock)
        self.assertEqual(len(found), 1)
        player = found[0]["pid"]
        relay = helper.proc_parent(player)
        # Fail here, before any test holds the pid, when the parent is not this
        # player's relay: on a tree with no relay it is the user's systemd
        # --user manager (relay_pidfd says why that matters).
        os.close(relay_pidfd(relay, player))
        return payload, player, relay

    def test_the_player_is_its_relays_child_and_its_environment_names_no_proxy_ffmpeg_reads(self):
        self.env(http_proxy="http://proxy.example.test:3128", no_proxy="*", NO_PROXY="mine.example.test")
        os.environ.pop("HTTP_PROXY", None)
        _, player, relay = self.start_player()
        env = proc_environ(player)
        self.assertNotIn(b"http_proxy", env)
        self.assertNotIn(b"no_proxy", env)
        # copied where the uppercase spelling was absent, kept where present
        self.assertEqual(env.get(b"HTTP_PROXY"), b"http://proxy.example.test:3128")
        self.assertEqual(env.get(b"NO_PROXY"), b"mine.example.test")
        relay_argv = [os.fsdecode(a) for a in pathlib.Path("/proc/%d/cmdline" % relay).read_bytes().split(b"\0") if a]
        self.assertEqual(relay_argv[-3:], ["player", "relay", "--child=%d" % player])
        # The relay leads its own process group and the player is in it, so
        # a SIGTERM the relay passes on reaches the player's whole tree.
        self.assertEqual((os.getpgid(relay), os.getpgid(player)), (relay, relay))
        self.assertEqual(relay_argv[1], "-I")
        self.assertFalse(any(a.startswith("--input-ipc-server") for a in relay_argv))
        # the relay runs non-dumpable (the stub's shield): not even this uid
        # reads its environment, which keeps the session's proxy as its upstream
        with self.assertRaises(PermissionError):
            proc_environ(relay)
        argv = self.spawned_argv()[0]
        port = [helper.relay_pin_port(a.encode()) for a in argv if a.startswith("--http-proxy=")]
        status = helper.relay_status(self.sock, player, port[0])
        self.assertIsNotNone(status)
        self.assertEqual(status["child"], player)
        self.assertEqual(status["_pid"], relay)

    def test_a_relay_killed_takes_its_player_with_it(self):
        _, player, relay = self.start_player()
        fd = relay_pidfd(relay, player)
        try:
            signal.pidfd_send_signal(fd, signal.SIGKILL)
        finally:
            os.close(fd)
        self.assertTrue(gone(player, 2.0), "the player outlived its relay")

    def test_a_stop_ends_the_relay_and_its_socket_goes_with_it(self):
        _, player, relay = self.start_player()
        path = helper.relay_socket_path(self.sock)
        self.assertTrue(os.path.exists(path))
        code, payload, _, stderr = test_player.run("player", "stop", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertTrue(gone(relay, helper.RELAY_LINGER_S + 3.0))
        self.assertFalse(os.path.exists(path))

    def test_a_relay_that_cannot_be_started_is_a_failed_spawn_that_leaves_no_player(self):
        """The relay's exec fails (`r<errno>` on the error pipe): the spawn
        answers spawn_failed in the relay's own words, and the player it had
        already forked is killed by the process that forked it."""
        missing = os.path.join(self.dir, "no-such-interpreter")
        with mock.patch.object(test_player.helper, "relay_argv", lambda: [missing, "-I", "x", "player", "relay"]):
            code, payload, _, stderr = self.player_start()
        self.assertEqual((code, (payload.get("error") or {}).get("code")), (1, "spawn_failed"), (payload, stderr))
        self.assertTrue(payload["error"]["message"].startswith(helper.RELAY_SPAWN_FAILED), payload)
        until = time.monotonic() + 3
        while helper.find_player(self.sock) and time.monotonic() < until:
            time.sleep(0.05)
        self.assertEqual(helper.find_player(self.sock), [])

    def test_a_relay_that_never_answers_is_a_failed_spawn_and_its_player_is_stopped(self):
        """The relay starts but never answers its status as the player's
        (here a process that only sleeps where the relay would run): after
        RELAY_START_S the spawn stops the player it launched and answers
        spawn_failed, so no player runs with nothing to judge its
        connections. The sleeper exits by itself; nothing signals it."""
        with mock.patch.object(test_player.helper, "relay_argv",
                               lambda: [sys.executable, "-I", "-c", "import time; time.sleep(%d)" % (
                                   int(helper.RELAY_START_S) + 2)]):
            started = time.monotonic()
            code, payload, _, stderr = self.player_start()
        self.assertEqual((code, payload["error"]["code"], payload["error"]["message"]),
                         (1, "spawn_failed", helper.RELAY_SPAWN_FAILED), stderr)
        self.assertGreaterEqual(time.monotonic() - started, helper.RELAY_START_S)
        self.assertEqual(helper.find_player(self.sock), [])

    def background_wrapper(self):
        """The stub mpv renamed `mpv-real`, behind a /bin/sh `mpv` on PATH that
        starts it in the background and exits at once: D-PLY-55's second
        wrapper shape, in which the pid the spawn launched is gone within
        milliseconds and the player is the process the socket reaches."""
        stub = os.path.join(self.bin, "mpv")
        real = os.path.join(self.bin, "mpv-real")
        os.rename(stub, real)
        pathlib.Path(stub).write_text('#!/bin/sh\n%s %s "$@" </dev/null >/dev/null 2>&1 &\nexit 0\n'
                                      % (sys.executable, real), encoding="utf-8")
        os.chmod(stub, 0o755)

    def test_a_wrapper_that_backgrounds_the_player_leaves_it_its_relays_child(self):
        """The spawn makes the relay a child subreaper BEFORE it forks the
        player, so a wrapper that backgrounds the real player and exits at
        once -- before the relay's interpreter has started, which is when the
        relay sets the flag again itself -- leaves the player the relay's
        child, and the start answers ok. Without the spawn's own call the
        player is reparented above the relay, which is then no ancestor of it,
        and the start answers spawn_failed with the player left running
        (measured by the review of 7c281d8). The parent is read off the
        kernel, and only read."""
        self.background_wrapper()
        code, payload, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        found = helper.find_player(self.sock)
        self.assertEqual(len(found), 1, found)          # the wrapper has exited
        # Asked even of a start that answered ok: a relay that happened to
        # answer as the launched pid's ancestor before it reaped that pid
        # would pass the spawn's own check with the player elsewhere.
        parent = helper.proc_parent(found[0]["pid"])
        argv = ([os.fsdecode(a) for a in pathlib.Path("/proc/%d/cmdline" % parent).read_bytes().split(b"\0") if a]
                if parent > 1 else [])
        self.assertEqual(argv[-3:], ["player", "relay", "--child=%d" % payload["pid"]],
                         "the socket's player is not its relay's child")

    def test_a_relay_that_never_answers_stops_a_backgrounded_player_too(self):
        """The relay never answers (a process that only sleeps where it would
        run) and a wrapper backgrounded the player: the launched pid is the
        wrapper, gone when the spawn gives up, and the player is the process
        the socket reaches. The spawn ladders both, so a start that answered
        spawn_failed leaves no player on the socket; laddering the launched
        pid alone left this one idle there (the review of 7c281d8). The
        sleeper exits by itself; nothing signals it."""
        self.background_wrapper()
        with mock.patch.object(test_player.helper, "relay_argv",
                               lambda: [sys.executable, "-I", "-c", "import time; time.sleep(%d)" % (
                                   int(helper.RELAY_START_S) + 2)]):
            code, payload, _, stderr = self.player_start()
        self.assertEqual((code, payload["error"]["code"], payload["error"]["message"]),
                         (1, "spawn_failed", helper.RELAY_SPAWN_FAILED), stderr)
        self.assertEqual(len(self.spawned_launches()), 1, "the player never started")
        self.assertEqual(helper.find_player(self.sock), [])

    def test_a_relay_socket_a_killed_relay_left_is_removed_by_a_stop(self):
        os.makedirs(self.runtime, 0o700, exist_ok=True)
        path = helper.relay_socket_path(self.sock)
        stale = socket.socket(socket.AF_UNIX)
        stale.bind(path)
        stale.close()
        code, payload, _, stderr = test_player.run("player", "stop", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual((code, payload["running"]), (0, False), stderr)
        self.assertFalse(os.path.lexists(path))


# ---- the load ----------------------------------------------------------------

class LoadRegistrationTest(MpvTestCase):
    """apply_channel through `play`, against FakeMpv and the FakeRelay."""

    def test_the_load_is_registered_after_the_gate_and_before_anything_about_a_channel(self):
        server = self.start()
        relay = self.relay_for(self.sock)
        seen = []
        real = relay.state.register

        def register(record):
            seen.append((len(server.commands), dict(record)))
            return real(record)
        relay.state.register = register
        code, _, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        # nothing had been said to the player when the load was registered
        self.assertEqual([n for n, _ in seen], [0])
        # the playlist is a local file: its rule rides on the token
        self.assertEqual(seen[0][1], {"origin": "playlist", "host": "", "port": None, "loopback": False,
                                      "local": True, "class": ""})
        load = test_mpv.last_load(server)
        self.assertEqual(dict(load[4])["http-proxy"],
                         "http://iptv:%s@127.0.0.1:%d" % (relay.tokens()[-1], relay.port))

    def test_a_typed_url_is_registered_under_the_users_rule(self):
        self.start()
        relay = self.relay_for(self.sock)
        code, _, _, stderr = self.play("--url", "http://live.example.test:8080/x.ts")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(relay.policies()[-1], {"origin": "user", "host": "live.example.test", "port": 8080})

    def test_a_player_whose_relay_is_gone_is_not_running_and_fed_nothing(self):
        server = self.start()
        self.identity(self.sock)
        self.relay_for(self.sock).close()
        code, payload, stdout, stderr = self.play("--id", "t:espn.us")
        self.assertEqual((code, payload["error"]["code"], payload.get("outdated")), (1, "not_running", True))
        time.sleep(0.05)
        self.assertEqual(server.commands, [])

    def test_a_proxy_another_client_set_refuses_the_load_before_any_channel_line(self):
        for value in ("http://proxy.example.test:3128", "", "http://127.0.0.1:9"):
            with self.subTest(value=value):
                server = self.start(props={"http-proxy": value})
                code, payload, _, stderr = self.play("--id", "t:espn.us")
                self.assertEqual((code, payload["error"]["code"]), (1, "tls_unverified"), stderr)
                self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])
                self.assertNotIn(["set_property", "title", "$>ESPN"], server.commands)
                self.assertNotIn("proxy.example", stderr)
                server.close()
                self.server = None

    def test_a_demuxer_http_proxy_is_removed_before_the_load_or_the_load_refused(self):
        lists = dict(test_mpv.LISTS, tls_verify="1")
        server = self.start(props={"demuxer-lavf-o": dict(lists, http_proxy="http://u:pw@proxy.example.test:3128",
                                                          live_start_index="-1")})
        code, _, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        remove = ["change-list", "demuxer-lavf-o", "remove", "http_proxy"]
        self.assertIn(remove, server.commands)
        self.assertLess(server.commands.index(remove), [c[0] for c in server.commands].index("loadfile"))
        self.assertEqual(server.props["demuxer-lavf-o"].get("live_start_index"), "-1")
        server.close()
        self.server = None
        server = self.start(props={"demuxer-lavf-o": dict(lists, http_proxy="http://p:1")}, refuse={"demuxer-lavf-o"})
        code, payload, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual((code, payload["error"]["code"]), (1, "tls_unverified"))
        self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])


class RelayHeaderTest(unittest.TestCase):
    """A channel header that would address the relay never reaches the
    player (player_target), over a cache as the parse writes it."""

    def test_proxy_headers_are_dropped_and_the_rest_kept(self):
        root = tempfile.mkdtemp(prefix="omarchy-iptv-hdr-")
        self.addCleanup(lambda: __import__("shutil").rmtree(root, True))
        document = {"version": 1, "sourceHost": "prov.example.test", "sourceClass": "global", "sourceLocal": False,
                    "sourcePort": 80, "channels": [{"id": "e1", "name": "E", "group": "G",
                                                    "url": "http://prov.example.test/live/1.ts",
                                                    "headers": {"Proxy-Authorization": "Basic " + LEAK,
                                                                "proxy-connection": "keep-alive",
                                                                "X-Keep": "1", "Authorization": "Bearer own"}}]}
        pathlib.Path(root, "channels.json").write_text(json.dumps(document), encoding="utf-8")
        target = helper.player_target("e1", "", root)
        self.assertEqual(target["headers"], {"X-Keep": "1", "Authorization": "Bearer own"})


# ---- pinned schemes, refused schemes ----------------------------------------

class PinnedSchemeTest(unittest.TestCase):
    """player_target over caches, with stated answers (test_stream_lookup's
    Resolver): rtmp, rtsp and srt from a playlist that is not local are
    handed the address they were judged by."""

    lk = test_stream_lookup

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.count = 0

    def targets(self, source, urls, answers):
        self.count += 1
        directory = os.path.join(self.root, str(self.count))
        ids = self.lk.write_cache(directory, urls, source)
        resolver, patch = self.lk.resolving(answers)
        got = []
        with patch:
            for cid in ids:
                try:
                    got.append(self.lk.helper.player_target(cid, "", directory))
                except self.lk.helper.HelperError as error:
                    got.append((error.code, error.message))
        return got, resolver

    def test_a_remote_playlists_rtmp_rtsp_and_srt_are_handed_the_judged_address(self):
        name = self.lk.NAME
        urls = ["rtmp://%s/app/x" % name, "srt://me:pw@%s:9000?streamid=a&mode=caller" % name,
                "rtsp://%s:8554/live/1?x=1" % name, "rtsp://cam%s/s" % name.replace("svc", ""),
                "RTMP://%s/a" % name]
        answers = {name: [self.lk.GLOBAL], "cam." + name.split(".", 1)[1]: ["2606:4700::1111", self.lk.GLOBAL]}
        got, resolver = self.targets(self.lk.REMOTE, urls, answers)
        self.assertEqual([t["url"] for t in got],
                         ["rtmp://93.184.216.34/app/x", "srt://me:pw@93.184.216.34:9000?streamid=a&mode=caller",
                          "rtsp://93.184.216.34:8554/live/1?x=1", "rtsp://[2606:4700::1111]/s",
                          "RTMP://93.184.216.34/a"])
        self.assertEqual([t.get("transport", "") for t in got], ["", "", "tcp", "tcp", ""])
        options = [dict(self.lk.helper.channel_load_options(t, "ua", "http://iptv:%s@127.0.0.1:9" % ("a" * 32)))
                   for t in got]
        self.assertEqual([(o.get("rtsp-transport"), o.get("demuxer-lavf-o-append")) for o in options],
                         [(None, None), (None, None), ("tcp", "rtsp_transport=tcp"), ("tcp", "rtsp_transport=tcp"),
                          (None, None)])

    def test_http_a_local_playlist_and_a_literal_are_not_pinned(self):
        name = self.lk.NAME
        got, _ = self.targets(self.lk.REMOTE, ["http://%s/x.ts" % name, "rtsp://93.184.216.34/s"],
                              {name: [self.lk.GLOBAL]})
        self.assertEqual([t["url"] for t in got], ["http://%s/x.ts" % name, "rtsp://93.184.216.34/s"])
        self.assertEqual(got[1].get("transport"), "tcp")
        got, resolver = self.targets(self.lk.LAN, ["rtsp://%s/s" % name, "srt://%s:9000" % name], {})
        self.assertEqual([(t["url"], t.get("transport", "")) for t in got],
                         [("rtsp://%s/s" % name, ""), ("srt://%s:9000" % name, "")])
        self.assertEqual(resolver.asked, [])

    def test_a_typed_url_is_never_pinned(self):
        resolver, patch = self.lk.resolving({})
        with patch:
            target = self.lk.helper.player_target("", "rtsp://%s/s" % self.lk.NAME, self.root)
        self.assertEqual((target["url"], target.get("transport", ""), resolver.asked),
                         ("rtsp://%s/s" % self.lk.NAME, "", []))

    def test_a_pinned_scheme_with_no_answer_to_hand_over_is_unchecked(self):
        """The own host of a source fetched through a proxy (`unresolved`)
        passes the lookup with no answer; there is nothing to pin to."""
        source = dict(self.lk.REMOTE, sourceHost=self.lk.NAME, sourceClass="unresolved")
        name = self.lk.NAME
        failing = OSError("no answer")
        got, _ = self.targets(source, ["rtsp://%s/s" % name, "http://%s/x.ts" % name], {name: failing})
        self.assertEqual(got[0], ("unchecked_address", self.lk.helper.STREAM_PIN_REFUSAL))
        self.assertEqual(got[1]["url"], "http://%s/x.ts" % name)


class RefusedSchemeTest(unittest.TestCase):
    """Decision 10: mms and mmsh from a playlist that is not local are
    skipped at the parse and refused at play; rtmps is relayed and kept; a
    local playlist keeps them. rtsps was never a scheme the plugin plays
    (STREAM_SCHEMES), from any playlist, and stays so."""

    URLS = ["mms://media.example.test/live", "mmsh://media.example.test/live", "rtsps://cam.example.test/s",
            "MMSH://media.example.test/x", "rtmps://cdn.example.test/app/x", "http://cdn.example.test/x.ts"]

    def playlist(self):
        return "#EXTM3U\n" + "".join('#EXTINF:-1 tvg-id="c%d",C%d\n%s\n' % (i, i, u) for i, u in enumerate(self.URLS))

    def test_the_parse_skips_and_counts_them_from_a_remote_playlist_and_keeps_them_from_a_local_one(self):
        remote = helper.parse_m3u(self.playlist(), helper.playlist_source("http", "https://prov.example.test/list"))
        self.assertEqual([c["url"] for c in remote["channels"]], self.URLS[4:])
        self.assertEqual(sorted(remote["warnings"]), sorted([helper.PARSE_REMOTE_SCHEME_MANY % 3,
                                                             "1 entry skipped: unsupported URL scheme"]))
        one = helper.parse_m3u("#EXTM3U\n#EXTINF:-1,A\nmms://m.example.test/x\n",
                               helper.playlist_source("http", "https://prov.example.test/list"))
        self.assertIn(helper.PARSE_REMOTE_SCHEME_ONE % 1, one["warnings"])
        self.assertFalse(any("example" in w for w in remote["warnings"] + one["warnings"]))
        local = helper.parse_m3u(self.playlist(), helper.playlist_source("file", ""))
        kept = [u for u in self.URLS if not u.startswith("rtsps:")]
        self.assertEqual([c["url"] for c in local["channels"]], kept)
        lan = helper.parse_m3u(self.playlist(), helper.playlist_source("http", "http://192.168.1.5/l", "private"))
        self.assertEqual([c["url"] for c in lan["channels"]], kept)

    def test_the_shared_vectors_and_sentences_are_the_helpers(self):
        """tests/fixtures/destinations.json `remoteSchemes`: the refused set
        and the three fixed sentences are the helper's own (rule 13), and
        every vector meets stream_entry_refusal as the fixture says."""
        table = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures" / "destinations.json")
                           .read_text(encoding="utf-8"))["remoteSchemes"]
        self.assertEqual(sorted(helper.STREAM_REMOTE_REFUSED_SCHEMES), table["refused"])
        self.assertEqual((helper.PARSE_REMOTE_SCHEME_ONE, helper.PARSE_REMOTE_SCHEME_MANY, helper.STREAM_REMOTE_REFUSAL),
                         (table["parseOne"], table["parseMany"], table["play"]))
        got = [(v["url"], v["source"]["local"], helper.stream_entry_refusal(v["url"], v["source"])[0])
               for v in table["vectors"]]
        self.assertEqual(got, [(v["url"], v["source"]["local"], v["reason"]) for v in table["vectors"]])
        # Both answers and both kinds of source are held, and every refused
        # scheme is refused from a remote list and kept from a local one.
        reasons = {(v["source"]["local"], v["reason"]) for v in table["vectors"]}
        self.assertTrue({(False, "remote"), (False, ""), (True, "")} <= reasons, reasons)
        for scheme in table["refused"]:
            self.assertIn((False, "remote"), {(v["source"]["local"], v["reason"]) for v in table["vectors"]
                                              if v["url"].lower().startswith(scheme + "://")})

    def test_play_refuses_a_cached_one_from_a_remote_playlist_before_any_lookup(self):
        lk = test_stream_lookup
        root = tempfile.mkdtemp(prefix="omarchy-iptv-refused-")
        self.addCleanup(lambda: __import__("shutil").rmtree(root, True))
        ids = lk.write_cache(root, self.URLS, lk.REMOTE)
        resolver, patch = lk.resolving({"cdn.example.test": [lk.GLOBAL]})
        got = []
        with patch:
            for cid in ids:
                try:
                    got.append(lk.helper.player_target(cid, "", root)["url"])
                except lk.helper.HelperError as error:
                    got.append((error.code, error.message))
        refusal = ("unsupported_scheme", lk.helper.STREAM_REMOTE_REFUSAL)
        self.assertEqual(got[:2] + got[3:], [refusal] * 3 + self.URLS[4:])
        self.assertEqual(got[2][0], "unsupported_scheme")          # rtsps: no scheme the plugin plays
        self.assertEqual(resolver.asked, [("cdn.example.test", 443), ("cdn.example.test", 80)])


# ---- the first load the relay refused ---------------------------------------

class FirstLoadRefusalTest(MpvTestCase):
    """`player start` whose first load failed after the relay refused one of
    its connections answers the channel's own refusal, `local_address`; one
    that failed with nothing refused answers as before. The connection is the
    one the player would make, sent here to the FakeRelay with the load's own
    token, for a loopback literal a remote playlist may not reach."""

    def start_verb(self, refuse_one):
        server = self.start(props=current_props(self.sock, relay_port=self.relay_for(self.sock).port),
                            cmdline=PINNED_CMDLINE)
        holder = self.identity(self.sock)
        relay = self.relay_for(self.sock)
        root = tempfile.mkdtemp(prefix="omarchy-iptv-first-")
        self.addCleanup(lambda: __import__("shutil").rmtree(root, True))
        ids = test_stream_lookup.write_cache(root, ["http://93.184.216.34/live/1.ts"], test_stream_lookup.REMOTE)

        def outcome(*a, **k):
            client = helper.MpvIpc(self.sock, 1.0)
            client.connect()
            return {"spawned": False, "client": client, "pid": holder.pid, "vouched": holder.pid,
                    "replaced": 0, "carry": {}, "relayPid": 0}

        def literal_only(name, port):
            # The relay's lookup of its target: a literal answers itself, and
            # nothing else is asked (never the suite's stand-in, which would
            # answer a public address for anything).
            if name != "127.0.0.2":
                raise AssertionError("unexpected lookup of %r" % (name,))
            return [test_stream_lookup.answer(name, port)]

        def first_load(client, entry_id, timeout, launch_errors=None):
            if refuse_one:
                with mock.patch.object(helper, "stream_resolve", literal_only):
                    reply = proxied_request(relay.port, relay.tokens()[-1], "http://127.0.0.2:9/x.ts")
                self.assertTrue(reply.startswith(b"HTTP/1.1 403 "), reply)
            return {"state": "failed", "reason": "Failed to open", "ended": "end-file", "fileError": "loading failed"}

        with mock.patch.object(helper, "adopt_or_spawn", outcome), \
                mock.patch.object(helper, "observe_first_load", first_load):
            return run("player", "start", "--socket", self.sock, "--cache-dir", root, "--id", ids[0], "--seq", "1",
                       "--ipc-timeout", "1", "--lock-timeout", "1", "--first-load-timeout", "0.2")

    def test_a_first_load_the_relay_refused_is_local_address(self):
        code, payload, stdout, stderr = self.start_verb(True)
        self.assertEqual((code, payload["kind"], payload["error"]["code"]), (1, "player.start", "local_address"))
        self.assertEqual(payload["error"]["message"], helper.RELAY_LOAD_REFUSAL)
        self.assertNotIn("127.0.0.2", stdout + stderr)

    def test_a_first_load_that_failed_with_nothing_refused_answers_as_before(self):
        code, payload, _, stderr = self.start_verb(False)
        self.assertEqual((code, payload["ok"], payload["firstLoad"]["state"]), (0, True, "failed"), stderr)


# ---- the probe and the orphan check -----------------------------------------

class ProbeAndOrphanRelayTest(test_player.PlayerTestCase):
    """The probe says whether the relay answered; a player of this build
    whose relay is gone reads `older` there (the shell then replaces it, or
    stops it at the hold's end: Model.olderPlayerUnsafe), and the orphan
    check stops it whoever claims it."""

    def player(self):
        os.makedirs(self.runtime, 0o700, exist_ok=True)
        idle = self.sleeper()
        self.start_current(props={"idle-active": False}, user_data={"omarchy-iptv": {"id": "t:x", "playing": True}})
        return idle

    def test_the_probe_reports_the_relay_and_reads_a_relayless_player_older(self):
        self.player()
        code, payload, _, stderr = test_player.run("player", "probe", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual((payload["relay"], payload["launch"], payload["tls"]["unpinned"]), (True, "current", 0))
        self.relay_for(self.sock).close()
        code, payload, _, stderr = test_player.run("player", "probe", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual((payload["relay"], payload["launch"], payload["tls"]["unpinned"]), (False, "older", 0))

    def test_the_orphan_check_stops_a_player_whose_relay_is_gone_whoever_claims_it(self):
        idle = self.player()
        self.relay_for(self.sock).close()
        code, payload, _, stderr = test_player.run("player", "orphan-check", "--socket", self.sock,
                                                   "--owner-pid", "1", "--grace", "0", "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual((payload["reason"], payload["stopped"]), ("relay_gone", True))
        self.assertTrue(gone(idle.pid, 3.0))

    def test_the_orphan_check_leaves_a_player_whose_relay_answers_to_its_claim(self):
        idle = self.player()
        code, payload, _, stderr = test_player.run("player", "orphan-check", "--socket", self.sock,
                                                   "--owner-pid", "1", "--grace", "0", "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual((payload["reason"], payload["stopped"]), ("reassigned", False))
        self.assertIsNone(idle.poll())


if __name__ == "__main__":
    unittest.main()
