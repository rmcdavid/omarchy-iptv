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
import resource
import shutil
import signal
import socket
import stat
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

    def lookup(host, port, timeout, **limit):
        text = host.decode("utf-8", "replace") if isinstance(host, bytes) else str(host)
        try:
            ipaddress.ip_address(text.split("%", 1)[0])
        except ValueError:
            raise AssertionError("a name reached resolve_within: %r" % (host,)) from None
        return real(host, port, timeout, **limit)
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

    def relay_port(self):
        """The relay pin's port on the spawned player's argv, as the stub mpv
        recorded it."""
        argv = self.spawned_argv()[0]
        ports = [helper.relay_pin_port(a.encode()) for a in argv if a.startswith("--http-proxy=")]
        self.assertEqual(len(ports), 1, "no relay pin on the spawned player's argv")
        return ports[0]

    def start_player(self):
        """`player start`, and the player's pid and its relay's. The relay's
        pid is the relay's own answer on its control socket -- relay_status's
        `_pid`, the kernel's SO_PEERCRED for the process that listens there,
        asked as the ancestor of THIS player -- never a pid read off the
        player's parent (the conformance review): on a tree with no
        relay that parent is the user's own `systemd --user` manager
        (relay_pidfd says what that cost). relay_pidfd then checks its
        command line on a pidfd before any test holds it."""
        code, payload, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        found = helper.find_player(self.sock)
        self.assertEqual(len(found), 1)
        player = found[0]["pid"]
        status = helper.relay_status(self.sock, player, self.relay_port())
        self.assertIsNotNone(status, "the spawned player's relay does not answer as its relay")
        relay = status["_pid"]
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
        status = helper.relay_status(self.sock, player, self.relay_port())
        self.assertIsNotNone(status)
        self.assertEqual(status["child"], player)
        # Read only: the process that answers as the relay is the player's
        # parent, as the spawn makes it. Nothing signals a pid read this way.
        self.assertEqual(helper.proc_parent(player), relay)

    @staticmethod
    def fd_table(pid):
        """/proc/<pid>/fd: descriptor number -> what it names. Readable for
        the player (dumpable after its exec), not for the relay, which runs
        non-dumpable from its stub's shield: the relay's table is what
        probed_start's probe records at its exec."""
        table = {}
        for name in os.listdir("/proc/%d/fd" % pid):
            try:
                table[int(name)] = os.readlink("/proc/%d/fd/%s" % (pid, name))
            except OSError:
                pass
        return table

    # What the probe in relay_argv's place records, at the exec and before it
    # opens anything that lasts: its core limit, and each descriptor it holds
    # with what it names and whether it survives an exec (no O_CLOEXEC in
    # fdinfo's octal flags). Then it execs the real relay in place, keeping
    # its pid, its descriptors and its argv, and the start goes on as ever.
    RELAY_PROBE = (
        "import json, os, sys\n"
        "fds = {}\n"
        "for name in os.listdir('/proc/self/fd'):\n"
        "    try:\n"
        "        link = os.readlink('/proc/self/fd/' + name)\n"
        "        flags = [l for l in open('/proc/self/fdinfo/' + name) if l.startswith('flags:')][0]\n"
        "    except OSError:\n"
        "        continue\n"
        "    fds[name] = [link, not int(flags.split()[1], 8) & 0o2000000]\n"
        "core = [l for l in open('/proc/self/limits') if l.startswith('Max core file size')][0].split()[4:6]\n"
        "fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)\n"
        "os.write(fd, json.dumps({'core': core, 'fds': fds}).encode()); os.close(fd)\n"
        "os.execv(sys.argv[2], sys.argv[2:])\n")

    def probed_start(self):
        """start_player with RELAY_PROBE in relay_argv's place -> (what the
        probe recorded, the player's pid, the relay's pid)."""
        record = os.path.join(self.dir, "relay-probe.json")
        real = test_player.helper.relay_argv()
        with mock.patch.object(test_player.helper, "relay_argv",
                               lambda: [real[0], "-I", "-c", self.RELAY_PROBE, record] + real):
            _, player, relay = self.start_player()
        probed = json.loads(pathlib.Path(record).read_text(encoding="utf-8"))
        return probed, player, relay

    def test_the_relay_holds_its_two_listeners_and_the_player_neither(self):
        """The spawn's descriptor hygiene (the conformance review):
        G hands the two listeners to fds 3 and 4 and closes 5 up to 4095
        (`min(SC_OPEN_MAX, 4096)`, ARCHITECTURE-PLAYER 20.2), and the player
        closes 3 and 4 before its exec, so mpv -- and everything mpv or a
        wrapper starts -- holds neither the proxy listener nor the control
        socket. The relay inherits exactly 0-4, 3 and 4 the two sockets (its
        own later descriptors, its child's pidfd and its wake pipe, are
        close-on-exec), and a descriptor this process leaves inheritable (a
        pipe) reaches neither process. The kernel is asked: /proc at the
        relay's exec (probed_start) and the player's /proc/<pid>/fd."""
        leak_r, leak_w = os.pipe()
        self.addCleanup(os.close, leak_r)
        self.addCleanup(os.close, leak_w)
        os.set_inheritable(leak_w, True)
        leaked = os.readlink("/proc/self/fd/%d" % leak_w)
        probed, player, relay = self.probed_start()
        table = {int(fd): link for fd, (link, _) in probed["fds"].items()}
        kept = sorted(int(fd) for fd, (_, survives) in probed["fds"].items() if survives)
        self.assertEqual(kept, [0, 1, 2, 3, 4], table)
        listeners = {table[3], table[4]}
        self.assertTrue(all(link.startswith("socket:[") for link in listeners), table)
        self.assertEqual(len(listeners), 2)
        self.assertNotIn(leaked, set(table.values()), "the relay inherited this test's pipe")
        held = set(self.fd_table(player).values())
        self.assertEqual(listeners & held, set(), "the player holds a relay listener")
        self.assertNotIn(leaked, held, "the player inherited this test's pipe")

    def test_the_relay_starts_with_a_zero_core_limit_from_the_spawn(self):
        """The spawn sets RLIMIT_CORE (0, 0) in G before it execs the relay
        (the conformance review), the only layer between that exec
        and the stub's shield, for the relay holds the session's environment
        less the private names. The relay sets it again at its own start, so
        /proc/<relay>/limits after a start cannot tell the spawn's call from
        the relay's: the probe (probed_start) reads it at the exec. The
        relay's pid is its own answer (start_player)."""
        inherited = resource.getrlimit(resource.RLIMIT_CORE)
        if inherited[1] == 0:
            self.skipTest("RLIMIT_CORE is already hard-zero in this process; the spawn cannot be told apart from it")
        # A soft limit of 0 raised to one byte (the hard one is not 0, above),
        # so an inherited limit reads as something other than 0: a core of
        # one byte is no core, and nothing here crashes.
        if inherited[0] == 0:
            resource.setrlimit(resource.RLIMIT_CORE, (1, inherited[1]))
            self.addCleanup(resource.setrlimit, resource.RLIMIT_CORE, inherited)
        probed, player, relay = self.probed_start()
        self.assertEqual(probed["core"], ["0", "0"], "the relay was exec'd with the core limit it inherited")
        self.assertEqual(test_player.core_limit_of(relay), ("0", "0"))
        self.assertEqual(test_player.core_limit_of(player), ("0", "0"))

    def test_the_relays_control_socket_is_owner_only_whatever_the_umask(self):
        """bind_relay_listeners binds the control socket under umask 077, so
        the socket file reads srwx------ even under a shell's 022, beside
        the 0700 runtime folder and the uid check on each connection."""
        saved = os.umask(0o022)
        try:
            self.start_player()
        finally:
            os.umask(saved)
        path = helper.relay_socket_path(self.sock)
        mode = os.lstat(path).st_mode
        self.assertTrue(stat.S_ISSOCK(mode))
        self.assertEqual(stat.S_IMODE(mode), 0o700)

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
        (measured by the review of 7c281d8). That start fails before this
        test's parent check is reached, and so does WrapperSpawnTest's
        background case: what holds a backgrounded player under its relay at
        any start that answers ok is relay_register's check that the relay is
        an ancestor of the PEER, the player itself (measured by the recheck,
        with wait_for_relay forced to pass). This test states the property
        directly; it adds no coverage of a race. The parent is read off the
        kernel, and only read."""
        self.background_wrapper()
        code, payload, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        found = helper.find_player(self.sock)
        self.assertEqual(len(found), 1, found)          # the wrapper has exited
        # The property itself, read off the kernel (relay_register's peer
        # check is what makes a start that answered ok imply it).
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

    def test_a_start_whose_load_the_relay_did_not_register_stops_the_player_it_spawned(self):
        """The relay answered the spawn's status, and then its registration of
        the load came back out of shape (relay_register's refusal, reached
        here through the shipping start): a local start failure,
        `not_running` with `outdated` in RELAY_REGISTER_REFUSAL's words, and
        the player this start spawned is stopped as D-PLY-57's is, where it
        was left idle on the socket until the next start read it older (the
        conformance review). The relay's own answer is changed in
        the helper's reading of it; the relay itself is the real one."""
        real = test_player.helper.relay_request

        def out_of_shape(sock_path, request, peer, *args, **kwargs):
            reply = real(sock_path, request, peer, *args, **kwargs)
            if isinstance(request, dict) and request.get("op") == "load" and isinstance(reply, dict):
                return dict(reply, token="not-a-token")
            return reply

        with mock.patch.object(test_player.helper, "relay_request", out_of_shape):
            code, payload, _, stderr = self.player_start()
        self.assertEqual((code, payload["error"]["code"], payload.get("outdated"), payload["error"]["message"]),
                         (1, "not_running", True, helper.RELAY_REGISTER_REFUSAL), stderr)
        self.assertEqual(len(self.spawned_launches()), 1, "the player never started")
        self.assertEqual(helper.find_player(self.sock), [], "the player this start spawned was left on the socket")


class RelayPathTooLongTest(test_player.GateTestCase):
    """A socket path that mpv can bind (104 bytes, sun_path holds 107) but
    whose relay socket (`.relay`, 6 more) it cannot: `player start` and
    `player restart` answer spawn_failed RELAY_PATH_TOO_LONG BEFORE they stop
    anything (the conformance review). It was refused at the
    spawn, after the restart's ladder or the adoption's replacement had
    stopped the older player, so the start ended with no player at all. The
    older player here is the stub mpv with another build's argv, which logs
    every command it is told."""

    def setUp(self):
        super().setUp()
        base = os.path.join(self.dir, "r")
        self.runtime = base + "x" * (104 - len(os.fsencode(os.path.join(base, "mpv.sock"))))
        self.sock = os.path.join(self.runtime, "mpv.sock")
        self.assertEqual(len(os.fsencode(self.sock)), 104)
        self.assertGreater(len(os.fsencode(self.sock + helper.RELAY_SOCKET_SUFFIX)), helper.RELAY_SUN_PATH_MAX)

    def test_a_relay_socket_path_past_sun_path_is_refused_before_the_older_player_is_touched(self):
        old = self.old_player("older")
        before = self.told(old.pid)
        for verb in ("start", "restart"):
            with self.subTest(verb=verb):
                code, payload, _, stderr = test_player.run(
                    "player", verb, "--socket", self.sock, "--cache-dir", self.cache, "--id", "t:bbc1.uk",
                    "--seq", "1", "--ipc-timeout", "1", "--lock-timeout", "1", "--spawn-timeout", "4",
                    "--first-load-timeout", "1")
                self.assertEqual((code, payload["error"]["code"], payload["error"]["message"]),
                                 (1, "spawn_failed", helper.RELAY_PATH_TOO_LONG), stderr)
                self.assertIsNone(old.poll(), "the older player was stopped")
                self.assertEqual(self.told(old.pid), before, "the older player was told something")
                self.assertEqual([record["pid"] for record in helper.find_player(self.sock)], [old.pid])
                self.assertEqual(self.spawned_launches(), [])


class SpawnPathBlockedTest(test_player.GateTestCase):
    """RelayPathTooLongTest's siblings (the branch's recheck, 2026-11-16):
    the two other refusals a spawn meets at a path that is the user's --
    something other than a socket at `<socket>.relay` (D-SINK-102,
    bind_relay_listeners' socket_path_blocked), and a folder at the options
    file's path when the start has tokens to write there (D-PLY-68,
    write_mpv_args' runtime_unwritable) -- are asked by `player start` and
    `player restart` before the lock, in the spawn's own words, so the older
    player is neither stopped nor told anything, nothing is launched, and
    what sits at the path is left as it was. Each was refused only at the
    spawn, after the restart's ladder or the adoption's replacement had
    stopped the older player, so the start ended with no player at all."""

    def assert_refused_before_anything_is_stopped(self, extra, code_and_message):
        old = self.old_player("older")
        before = self.told(old.pid)
        for verb in ("start", "restart"):
            with self.subTest(verb=verb):
                code, payload, _, stderr = test_player.run(
                    "player", verb, "--socket", self.sock, "--cache-dir", self.cache, "--id", "t:bbc1.uk",
                    "--seq", "1", "--ipc-timeout", "1", "--lock-timeout", "1", "--spawn-timeout", "4",
                    "--first-load-timeout", "1", *extra)
                self.assertEqual((code, payload["error"]["code"], payload["error"]["message"]),
                                 (1,) + code_and_message, stderr)
                self.assertIsNone(old.poll(), "the older player was stopped")
                self.assertEqual(self.told(old.pid), before, "the older player was told something")
                self.assertEqual([record["pid"] for record in helper.find_player(self.sock)], [old.pid])
                self.assertEqual(self.spawned_launches(), [])

    def test_a_relay_socket_path_holding_a_file_is_refused_before_the_older_player_is_touched(self):
        os.makedirs(self.runtime, 0o700, exist_ok=True)
        path = pathlib.Path(helper.relay_socket_path(self.sock))
        path.write_text("the user's own file\n", encoding="utf-8")
        self.assert_refused_before_anything_is_stopped((), ("socket_path_blocked", helper.RELAY_PATH_BLOCKED))
        self.assertEqual(path.read_text(encoding="utf-8"), "the user's own file\n")

    def test_an_options_file_path_holding_a_folder_is_refused_before_the_older_player_is_touched(self):
        os.makedirs(self.runtime, 0o700, exist_ok=True)
        folder = helper.mpv_args_path(self.sock, helper.player_dirs(self.sock))
        os.mkdir(folder, 0o700)
        self.assert_refused_before_anything_is_stopped(
            ("--mpv-arg=--osd-level=1",), ("runtime_unwritable", "could not write the player's options (Is a directory)"))
        self.assertTrue(os.path.isdir(folder))


class FreshSpawnRefusedBeforeItsLoadTest(test_player.GateTestCase):
    """D-PLY-57's rule, widened on 2026-11-16 (the branch's recheck): a
    fresh spawn this start fed nothing is stopped on every refusal that
    comes before its load. Here the TLS read-back's: a user's `mpv` wrapper
    on PATH appends its own `--http-proxy` after this build's whole launch
    argv, so the player's `http-proxy` names something other than its
    relay's pin, every load is refused `tls_unverified` (read_tls_state),
    and the spawn was left idle and unfed on the socket, a black window the
    next start found. Through the shipping start over the stub mpv, which
    applies its argv's last word as mpv does."""

    def test_a_fresh_spawn_the_tls_read_back_refuses_is_stopped_and_fed_nothing(self):
        test_player.WrapperSpawnTest.wrap(self, 'exec REAL "$@" --http-proxy=http://127.0.0.1:9')
        os.makedirs(self.runtime, 0o700, exist_ok=True)
        code, payload, _, stderr = self.player_start()
        self.assertEqual((code, payload["error"]["code"]), (1, "tls_unverified"), stderr)
        launches = self.spawned_launches()
        self.assertEqual(len(launches), 1, "the player never started")
        self.assertEqual(launches[0]["applied"][-1], "--http-proxy=http://127.0.0.1:9")
        told = [c for c in self.told(launches[0]["pid"]) if isinstance(c, list)]
        self.assertEqual([c for c in told if c[:1] == ["loadfile"]], [])
        self.assertEqual(helper.find_player(self.sock), [], "the spawn the read-back refused was left on the socket")

    def test_a_spawn_a_newer_channel_plays_on_is_kept_when_the_start_then_fails(self):
        """The other side of the rule: a start that stands down (another
        client's channel already on its spawn, applied_by_another_client)
        and then fails writing its owner claim keeps the spawn, which is
        playing that client's channel. The newer channel is stated through
        the seam; the claim's write fails as a dead connection does."""
        os.makedirs(self.runtime, 0o700, exist_ok=True)
        newer = {"id": "t:espn.us", "name": "ESPN", "entryId": 1, "verb": "play", "loaded": True}
        shipping = test_player.helper
        real = shipping.MpvIpc.try_command

        def claim_fails(client, *args):
            if args[:2] == ("set_property", shipping.USER_DATA_OWNER):
                raise shipping.HelperError("ipc_error", "mpv closed the connection")
            return real(client, *args)

        with mock.patch.object(shipping, "applied_by_another_client", lambda client: dict(newer)), \
                mock.patch.object(shipping.MpvIpc, "try_command", claim_fails):
            code, payload, _, stderr = self.player_start("--owner-pid", str(os.getpid()))
        self.assertEqual((code, payload["error"]["code"]), (1, "ipc_error"), stderr)
        launches = self.spawned_launches()
        self.assertEqual(len(launches), 1, "the player never started")
        self.assertEqual([record["pid"] for record in helper.find_player(self.sock)], [launches[0]["pid"]])


# ---- the load ----------------------------------------------------------------

class LoadRegistrationTest(MpvTestCase):
    """apply_channel through `play`, against FakeMpv and the FakeRelay."""

    def test_the_load_is_registered_after_the_gate_and_before_anything_about_a_channel(self):
        server = self.start()
        relay = self.relay_for(self.sock)
        seen = []
        real = relay.state.enter

        def enter(record):
            seen.append((len(server.commands), dict(record)))
            return real(record)
        relay.state.enter = enter
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

    def test_a_registration_the_relay_answers_out_of_shape_refuses_the_play_before_any_line(self):
        """relay_register's own refusal (the conformance review): the
        relay answers the gate's status, so the play reaches the
        registration, and the registration's reply is refused unless it is
        `ok` with a token of 32 lowercase hex digits and a port in
        1-65535 -- `not_running` with `outdated` in RELAY_REGISTER_REFUSAL's
        words, with no command sent to the player and no load. The relay is
        the FakeRelay; only the helper's reading of its `load` reply is
        changed, one way per subtest."""
        changes = [("not ok", lambda r: dict(r, ok=False)),
                   ("token upper case", lambda r: dict(r, token=r["token"].upper())),
                   ("token 31 digits", lambda r: dict(r, token=r["token"][:31])),
                   ("token 33 digits", lambda r: dict(r, token=r["token"] + "0")),
                   ("token not hex", lambda r: dict(r, token="g" * 32)),
                   ("token a number", lambda r: dict(r, token=12345)),
                   ("port 0", lambda r: dict(r, port=0)),
                   ("port 65536", lambda r: dict(r, port=65536)),
                   ("port a boolean", lambda r: dict(r, port=True)),
                   ("port a string", lambda r: dict(r, port=str(r["port"])))]
        real = helper.relay_request
        for label, change in changes:
            with self.subTest(label):
                server = self.start()

                def answer(sock_path, request, peer, *args, change=change, **kwargs):
                    reply = real(sock_path, request, peer, *args, **kwargs)
                    if isinstance(request, dict) and request.get("op") == "load" and isinstance(reply, dict):
                        return change(reply)
                    return reply

                try:
                    with mock.patch.object(helper, "relay_request", answer):
                        code, payload, _, stderr = self.play("--id", "t:espn.us")
                    self.assertEqual((code, (payload.get("error") or {}).get("code"), payload.get("outdated"),
                                      (payload.get("error") or {}).get("message")),
                                     (1, "not_running", True, helper.RELAY_REGISTER_REFUSAL), stderr)
                    time.sleep(0.05)
                    self.assertEqual(server.commands, [])
                finally:
                    server.close()
                    self.server = None

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
        every vector meets the three shipping functions its comment names
        (the conformance review): stream_entry_refusal answers
        its reason; parse_m3u, over a playlist_source built from the
        vector's source, keeps it, skips and counts it in parseOne's words
        (`remote`) or as an unsupported scheme (`scheme`); and player_target,
        over a cache the parse would write from that source, plays it or
        refuses it `unsupported_scheme` (in the fixture's `play` sentence for
        `remote`). Only cdn.example.test is ever looked up, by the suite's
        stated answers."""
        lk = test_stream_lookup
        table = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures" / "destinations.json")
                           .read_text(encoding="utf-8"))["remoteSchemes"]
        self.assertEqual(sorted(helper.STREAM_REMOTE_REFUSED_SCHEMES), table["refused"])
        self.assertEqual((helper.PARSE_REMOTE_SCHEME_ONE, helper.PARSE_REMOTE_SCHEME_MANY, helper.STREAM_REMOTE_REFUSAL),
                         (table["parseOne"], table["parseMany"], table["play"]))
        got = [(v["url"], v["source"]["local"], helper.stream_entry_refusal(v["url"], v["source"])[0])
               for v in table["vectors"]]
        self.assertEqual(got, [(v["url"], v["source"]["local"], v["reason"]) for v in table["vectors"]])
        root = tempfile.mkdtemp(prefix="omarchy-iptv-schemes-")
        self.addCleanup(shutil.rmtree, root, True)
        for at, vector in enumerate(table["vectors"]):
            url, source, reason = vector["url"], vector["source"], vector["reason"]
            with self.subTest(url=url, local=source["local"]):
                if source["host"] == "":
                    built, cached = helper.playlist_source("file", ""), dict(lk.FILE)
                else:
                    built = helper.playlist_source("http", "http://%s:%d/list" % (source["host"], source["port"]),
                                                   source["class"], source["class"])
                    cached = {"sourceHost": source["host"], "sourceClass": source["class"],
                              "sourceLocal": source["local"], "sourcePort": source["port"]}
                self.assertEqual(built, {key: source[key] for key in built})
                parsed = lk.helper.parse_m3u("#EXTM3U\n#EXTINF:-1,C\n%s\n" % url, built)
                self.assertEqual([c["url"] for c in parsed["channels"]], [url] if reason == "" else [])
                skipped = {"": [], "remote": [helper.PARSE_REMOTE_SCHEME_ONE % 1],
                           "scheme": ["1 entry skipped: unsupported URL scheme"]}[reason]
                self.assertEqual(parsed["warnings"], skipped)
                directory = os.path.join(root, str(at))
                ids = lk.write_cache(directory, [url], cached)
                resolver, patch = lk.resolving({"cdn.example.test": [lk.GLOBAL]})
                with patch:
                    try:
                        target = lk.helper.player_target(ids[0], "", directory)
                        played = ("played", target["url"].split(":", 1)[0].lower())
                    except lk.helper.HelperError as error:
                        played = (error.code, error.message == helper.STREAM_REMOTE_REFUSAL)
                expected = {"": ("played", url.split(":", 1)[0].lower()), "remote": ("unsupported_scheme", True),
                            "scheme": ("unsupported_scheme", False)}[reason]
                self.assertEqual(played, expected)
                if reason != "":
                    self.assertEqual(resolver.asked, [])
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


# ---- the spawn's wait for its relay -----------------------------------------

class WaitForRelayTest(unittest.TestCase):
    """wait_for_relay asks one anchor at a time, and each question has
    min(RELAY_IPC_S, the time left in its bound) for its whole exchange (the
    conformance review): each had 10 ms, so a relay that
    answered slower than that on a loaded machine read as never answering
    and the start failed spawn_failed. relay_request is a double that
    records each bound it is handed and answers only a bound of 50 ms or
    more, a relay that takes 50 ms to answer; nothing is connected."""

    PORT = 4321

    def wait(self, timeout, answer_for=(11, 12)):
        handed = []

        def slow_relay(sock_path, request, peer, timeout=None, relay_pid=0):
            handed.append((peer, timeout))
            if timeout is None or timeout < 0.05 or peer not in answer_for:
                return None
            return {"ok": True, "port": self.PORT, "build": helper.player_build(), "_pid": 99}

        with mock.patch.object(helper, "relay_request", slow_relay):
            started = time.monotonic()
            ok = helper.wait_for_relay("/nonexistent-relay-wait/mpv.sock", (11, 12), self.PORT, timeout)
        return ok, handed, time.monotonic() - started

    def test_a_relay_that_takes_50_ms_to_answer_is_waited_for(self):
        ok, handed, _ = self.wait(helper.RELAY_START_S)
        self.assertTrue(ok, handed)
        self.assertEqual(handed[0][0], 11)
        self.assertAlmostEqual(handed[0][1], helper.RELAY_IPC_S, delta=0.05)

    def test_each_question_is_capped_by_the_time_left_and_one_anchor_is_asked_at_a_time(self):
        ok, handed, spent = self.wait(0.3)
        self.assertTrue(ok, handed)
        self.assertTrue(0.25 < handed[0][1] <= 0.3, handed)
        ok, handed, spent = self.wait(0.3, answer_for=(12,))
        self.assertTrue(ok, handed)
        self.assertEqual([peer for peer, _ in handed[:2]], [11, 12])
        ok, handed, spent = self.wait(0.3, answer_for=())
        self.assertFalse(ok)
        self.assertTrue(all(t is not None and t <= helper.RELAY_IPC_S for _, t in handed), handed)
        self.assertLess(spent, 0.3 + 2 * helper.SPAWN_POLL_S + 0.1)


# ---- whose answer relay_request trusts ---------------------------------------

class RelayRequestIdentityTest(unittest.TestCase):
    """relay_request asked for a relay by pid (relay_refused_count, after the
    player has gone) answers only when the process listening on the control
    socket IS that pid (SO_PEERCRED): the FakeRelay runs in this process, so
    this process's pid is the one that answers, and any other pid -- only
    compared here, never signalled -- gets nothing."""

    def setUp(self):
        root = tempfile.mkdtemp(prefix="omarchy-iptv-rr-", dir="/tmp")
        self.addCleanup(shutil.rmtree, root, True)
        self.sock = os.path.join(root, "run", "mpv.sock")
        relay = FakeRelay(helper, self.sock)
        self.addCleanup(relay.close)

    def test_a_relay_pid_that_is_not_the_answering_process_gets_no_answer(self):
        ok = helper.relay_request(self.sock, {"op": "status"}, 0, relay_pid=os.getpid())
        self.assertEqual((ok["ok"], ok["_pid"]), (True, os.getpid()))
        for other in (os.getpid() + 1, 4242):
            with self.subTest(other=other):
                self.assertIsNone(helper.relay_request(self.sock, {"op": "status"}, 0, relay_pid=other))


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
                    "replaced": 0, "carry": {}}

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


# ---- the question after a later failed open (D-PLY-66) ------------------------

class RefusedVerbTest(FirstLoadRefusalTest):
    """D-PLY-66: a load's reply carries its relay's handle -- the relay's pid
    and its number for the load, no token -- and `player refused` answers
    that load's count from the relay itself, for the shell to ask when the
    load's open fails after the reply. The relay is the FakeRelay, the real
    relay's code in this process, so its pid is this process's."""

    def refused(self, pid, load, sock=None):
        code, payload, stdout, stderr = run("player", "refused", "--socket", sock or self.sock,
                                            "--relay-pid", str(pid), "--load", str(load))
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(sorted(payload), ["kind", "ok", "refused"])
        self.assertEqual((payload["ok"], payload["kind"]), (True, "player.refused"))
        return payload["refused"]

    def refuse_one(self, relay, token):
        def literal_only(name, port):
            if name != "127.0.0.2":
                raise AssertionError("unexpected lookup of %r" % (name,))
            return [test_stream_lookup.answer(name, port)]
        with mock.patch.object(helper, "stream_resolve", literal_only):
            reply = proxied_request(relay.port, token, "http://127.0.0.2:9/x.ts")
        self.assertTrue(reply.startswith(b"HTTP/1.1 403 "), reply)

    def test_a_start_reply_carries_the_handle_and_the_verb_counts_that_loads_refusals(self):
        code, payload, stdout, stderr = self.start_verb(False)
        self.assertEqual(code, 0, stderr)
        relay = self.relay_for(self.sock)
        self.assertEqual(payload["relay"], {"pid": os.getpid(), "load": 1})
        self.assertNotIn(relay.tokens()[-1], stdout + stderr)
        self.assertEqual(self.refused(os.getpid(), 1), 0)
        # what the player does after the reply: a connection the relay refuses
        self.refuse_one(relay, relay.tokens()[-1])
        self.assertEqual(self.refused(os.getpid(), 1), 1)
        self.refuse_one(relay, relay.tokens()[-1])
        self.assertEqual(self.refused(os.getpid(), 1), 2)

    def test_each_load_is_counted_on_its_own_number(self):
        self.start_verb(False)
        relay = self.relay_for(self.sock)
        second = relay.state.enter(dict(relay.policies()[-1]))
        self.assertEqual(second.load, 2)
        self.refuse_one(relay, second.token)
        self.assertEqual((self.refused(os.getpid(), 1), self.refused(os.getpid(), 2)), (0, 1))

    def test_nothing_that_cannot_say_is_an_error_or_a_count(self):
        self.start_verb(False)
        relay = self.relay_for(self.sock)
        self.refuse_one(relay, relay.tokens()[-1])
        # another process's pid (compared, never signalled), a load the relay
        # does not keep, numbers out of range, and no relay at all
        for pid, load in ((os.getpid() + 1, 1), (os.getppid(), 1), (os.getpid(), 2), (os.getpid(), 0),
                          (os.getpid(), -1), (1, 1), (0, 1), (-7, 1)):
            with self.subTest(pid=pid, load=load):
                self.assertIsNone(self.refused(pid, load))
        empty = tempfile.mkdtemp(prefix="omarchy-iptv-refused-", dir="/tmp")
        self.addCleanup(shutil.rmtree, empty, True)
        self.assertIsNone(self.refused(os.getpid(), 1, sock=os.path.join(empty, "run", "mpv.sock")))
        self.assertEqual(self.refused(os.getpid(), 1), 1)

    def test_a_zap_reply_carries_its_own_loads_handle_only_with_the_session_flags(self):
        server = self.start(props=current_props(self.sock, relay_port=self.relay_for(self.sock).port),
                            cmdline=PINNED_CMDLINE)
        self.identity(self.sock)
        root = tempfile.mkdtemp(prefix="omarchy-iptv-zap-")
        self.addCleanup(shutil.rmtree, root, True)
        ids = test_stream_lookup.write_cache(root, ["http://93.184.216.34/live/1.ts"], test_stream_lookup.REMOTE)
        zap = lambda *more: run("play", "--id", ids[0], "--cache-dir", root, "--socket", self.sock, "--ipc-timeout", "1", *more)
        code, bare, _, stderr = zap()
        self.assertEqual(code, 0, stderr)
        self.assertNotIn("relay", bare)
        code, first, _, stderr = zap("--scope", "all", "--since", "5")
        self.assertEqual(code, 0, stderr)
        code, second, stdout, stderr = zap("--scope", "all", "--since", "6")
        self.assertEqual(code, 0, stderr)
        self.assertEqual((first["relay"], second["relay"]), ({"pid": os.getpid(), "load": 2}, {"pid": os.getpid(), "load": 3}))
        self.assertNotIn(self.relay_for(self.sock).tokens()[-1], stdout + stderr)


# ---- the probe and the orphan check -----------------------------------------

class StatusRelayTest(test_player.PlayerTestCase):
    """D-PLY-67: the health tick's `status` says whether this build's player
    still has its relay -- true, false once the relay is gone, and null for
    a player another build launched, which is the reattach's to replace. It
    stays a read: the reply is a healthy status either way."""

    def player(self, launch="current"):
        os.makedirs(self.runtime, 0o700, exist_ok=True)
        idle = self.sleeper(launch=launch)
        if launch == "current":
            self.start_current(props={"idle-active": False}, user_data={"omarchy-iptv": {"id": "t:x", "playing": True}})
        else:
            self.start(props={"idle-active": False, "mpv-version": "mpv 0.41.0"},
                       user_data={"omarchy-iptv": {"id": "t:x", "playing": True}})
        return idle

    def status(self):
        code, payload, _, stderr = test_player.run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual((payload["ok"], payload["running"], payload["idle"]), (True, True, False))
        return payload

    def test_a_current_player_whose_relay_answers_reports_true(self):
        idle = self.player()
        self.assertIs(self.status()["relay"], True)
        self.assertIsNone(idle.poll())

    def test_a_current_player_whose_relay_is_gone_reports_false_and_is_left_running(self):
        idle = self.player()
        self.relay_for(self.sock).close()
        started = time.monotonic()
        self.assertIs(self.status()["relay"], False)
        # One relay question, asked again inside RELAY_IPC_S and no longer.
        self.assertLess(time.monotonic() - started, helper.RELAY_IPC_S + 2.0)
        self.assertIsNone(idle.poll(), "status stopped the player; it is a read")

    def test_a_player_another_build_launched_reports_null(self):
        self.player(launch="older")
        self.assertIsNone(self.status()["relay"])

    def test_a_listener_with_no_launch_argv_reports_null(self):
        # No sleeper registered: the kernel names this test process, which
        # carries no socket token ("unknown").
        os.makedirs(self.runtime, 0o700, exist_ok=True)
        self.start(props={"idle-active": False})
        self.assertIsNone(self.status()["relay"])


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
        """And it removes the socket file the killed relay left (a relay
        killed outright never removes its own), under the player lock once
        no player is left, as `player stop` does (the conformance review):
        the FakeRelay's close removes its socket, so the file a killed relay
        leaves is put back here, with nothing listening."""
        idle = self.player()
        self.relay_for(self.sock).close()
        path = helper.relay_socket_path(self.sock)
        stale = socket.socket(socket.AF_UNIX)
        stale.bind(path)
        stale.close()
        code, payload, _, stderr = test_player.run("player", "orphan-check", "--socket", self.sock,
                                                   "--owner-pid", "1", "--grace", "0", "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual((payload["reason"], payload["stopped"]), ("relay_gone", True))
        self.assertTrue(gone(idle.pid, 3.0))
        self.assertFalse(os.path.lexists(path), "the dead relay's socket was left behind")

    def test_the_orphan_check_leaves_a_player_whose_relay_answers_to_its_claim(self):
        idle = self.player()
        code, payload, _, stderr = test_player.run("player", "orphan-check", "--socket", self.sock,
                                                   "--owner-pid", "1", "--grace", "0", "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual((payload["reason"], payload["stopped"]), ("reassigned", False))
        self.assertIsNone(idle.poll())


if __name__ == "__main__":
    unittest.main()
