"""The harness's stand-in mpv (scripts/qa-stub-mpv.py) against the SHIPPING
helper's pin read-back, over a real socket (D-SINK-43, D-SINK-44).

The stub's own --self-test replays what mpv 0.41.0 answered (the fixture
tests/fixtures/stub-mpv-ipc.json). This is the other half of the join: the
helper's read_tls_state, migrate_tls and assert_tls_verification, called for
real against a stub process launched with the helper's own launch argv, read
the three outcomes a real player gives -- a player this plugin starts is
safe as it comes, a player started before the pins is made safe by the
migration, and one whose mpv.conf carries a per-file profile that could undo
a loose option is NOT, and stays refused. Before the stub learned the pin
properties every one of these read `unpinned` None and refused, which is why
every scenario play into it failed `tls_unverified`.

The stub runs as a child of this process with a bounded life (STUB_LIFE), in
a private temporary directory, and is ended by `quit` and then by its Popen
handle -- never by a pattern."""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import FakeRelay, load_helper  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
STUB = ROOT / "scripts" / "qa-stub-mpv.py"
helper = load_helper()


class StubPlayer:
    def __init__(self, argv, profiles=None, relay=False):
        self.dir = tempfile.mkdtemp(prefix="stub-pins-")
        os.chmod(self.dir, 0o700)
        self.sock = os.path.join(self.dir, "s")
        # D-SINK-102: with `relay`, the helper's own relay code in this
        # process (FakeRelay) and the argv's pin naming its port.
        self.relay = FakeRelay(helper, self.sock) if relay else None
        if self.relay is not None:
            argv = [helper.mpv_relay_pin(self.relay.port) if a.startswith("--http-proxy=") else a for a in argv]
        env = {k: v for k, v in os.environ.items() if not k.startswith("STUB_")}
        env["STUB_LIFE"] = "20"
        if profiles is not None:
            env["STUB_PROFILES"] = json.dumps(profiles)
        launch = [a.replace("@SOCK@", self.sock) for a in argv]
        self.proc = subprocess.Popen([sys.executable, str(STUB)] + launch[1:], env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 10
        while not os.path.exists(self.sock):
            if time.monotonic() > deadline or self.proc.poll() is not None:
                self.close()
                raise RuntimeError("the stub did not bind %s" % self.sock)
            time.sleep(0.02)
        self.client = helper.MpvIpc(self.sock, 5.0)
        self.client.connect()

    def close(self):
        try:
            if getattr(self, "client", None) is not None:
                self.client.try_command("quit")
        except Exception:
            pass
        finally:
            if getattr(self, "client", None) is not None:
                self.client.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
        if self.relay is not None:
            self.relay.close()
        shutil.rmtree(self.dir, ignore_errors=True)


# D-SINK-102: the relay port a pinned launch argv names here.
RELAY_PORT = 48510


def launch_argv(pins=True, relay_port=RELAY_PORT):
    dirs = {"cwd": "/nonexistent", "screenshots": "/nonexistent/shots",
            "watchLater": "/nonexistent/wl", "shaderCache": "/nonexistent/sc"}
    argv = helper.mpv_launch_argv("@SOCK@", [], dirs, relay_port=relay_port)
    if not pins:
        # A player started before the pin block: the same launch argv with
        # the tail cut off, which is what 0.15.0's mpv_launch_argv returned
        # (its base argv already carried --tls-verify=yes, and so does this).
        argv = argv[:len(argv) - len(helper.mpv_pin_block(dirs))]
    return argv


HTTPS_PROFILE = [{"name": "protocol.https", "options": [{"key": "stream-lavf-o", "value": "tls_verify=0"}]}]
# F-HARNESS-76: a profile of the user's own, as their mpv.conf would hold it,
# for a `--profile=loose` token on a launch argv.
LOOSE_PROFILE = [{"name": "loose", "options": [{"key": "tls-verify", "value": "no"},
                                               {"key": "stream-lavf-o", "value": "tls_verify=0"}]}]


def record_requests(client):
    """Every request `client` sends from here on, with the error it drew."""
    seen = []
    send = client.request

    def request(command, allow_close=False):
        reply = send(command, allow_close)
        seen.append((list(command), reply.get("error")))
        return reply

    client.request = request
    return seen


class StubAgainstTheShippingReadBack(unittest.TestCase):
    def player(self, **kw):
        stub = StubPlayer(**kw)
        self.addCleanup(stub.close)
        return stub

    def test_a_player_this_plugin_starts_is_safe_as_it_comes(self):
        stub = self.player(argv=launch_argv())
        self.assertEqual(helper.read_tls_state(stub.client, RELAY_PORT), (True, 0, 0))
        self.assertFalse(helper.migrate_tls(stub.client, RELAY_PORT)["migrated"])
        helper.assert_tls_verification(stub.client, "test", RELAY_PORT)      # raises when it refuses
        # D-SINK-102: held to its OWN relay's port, which no other port is.
        self.assertEqual(helper.read_tls_state(stub.client, RELAY_PORT + 1), (True, 0, 1))

    def test_a_player_from_before_the_pins_is_migrated_to_safe(self):
        stub = self.player(argv=launch_argv(pins=False))
        # Three pins not held: load-auto-profiles reads "auto", and the
        # demuxer map holds neither the protocol list (D-SINK-55) nor, since
        # lane-p1c (2026-10-29), the format list (D-SINK-62); and since
        # D-SINK-102 the relay pin, which no migration sets: such a player is
        # replaced, never fed.
        self.assertEqual(helper.read_tls_state(stub.client), (True, 0, 4))
        result = helper.migrate_tls(stub.client)
        self.assertEqual((result["migrated"], result["verify"], result["optionCount"], result["unpinned"]),
                         (True, True, 0, 1))

    def test_a_per_file_profile_on_a_loose_player_is_counted_and_refused(self):
        stub = self.player(argv=launch_argv(pins=False), profiles=HTTPS_PROFILE)
        result = helper.migrate_tls(stub.client)
        # The profile, and (D-SINK-102) the relay pin it has none of.
        self.assertEqual((result["migrated"], result["unpinned"]), (True, 2))
        with self.assertRaises(helper.HelperError) as caught:
            helper.assert_tls_verification(stub.client, "test")
        self.assertEqual(caught.exception.code, "tls_unverified")

    def test_the_same_profile_is_harmless_to_a_pinned_player(self):
        stub = self.player(argv=launch_argv(), profiles=HTTPS_PROFILE)
        self.assertEqual(helper.read_tls_state(stub.client, RELAY_PORT), (True, 0, 0))

    def test_a_profile_named_on_a_loose_player_s_argv_is_read_and_migrated(self):
        """F-HARNESS-76: the stub applied no `--profile=<name>` token, so a
        player from before the pins that was launched with one read as a
        player launched without it. With the token applied (as mpv 0.41.0
        was measured to apply it), the shipping read-back sees what such a
        player holds -- verification off and a stream option -- and the
        migration makes it safe, as it does any loose player."""
        stub = self.player(argv=launch_argv(pins=False) + ["--profile=loose"], profiles=LOOSE_PROFILE)
        self.assertEqual(helper.read_tls_state(stub.client), (False, 1, 4))
        result = helper.migrate_tls(stub.client)
        self.assertEqual((result["migrated"], result["verify"], result["optionCount"], result["unpinned"]),
                         (True, True, 0, 1))

    def test_the_same_token_is_harmless_before_the_pin_block(self):
        dirs = {"cwd": "/nonexistent", "screenshots": "/nonexistent/shots",
                "watchLater": "/nonexistent/wl", "shaderCache": "/nonexistent/sc"}
        cut = len(helper.mpv_pin_block(dirs))
        argv = launch_argv()
        stub = self.player(argv=argv[:len(argv) - cut] + ["--profile=loose"] + argv[len(argv) - cut:], profiles=LOOSE_PROFILE)
        self.assertEqual(helper.read_tls_state(stub.client, RELAY_PORT), (True, 0, 0))


if __name__ == "__main__":
    unittest.main()



class StubAgainstTheShippingWrites(unittest.TestCase):
    """F-HARNESS-74: the stub answers `property not found` to a write of a
    name it does not list, as mpv does to one it does not have. The join the
    list needs: every property the SHIPPING helper writes -- a zap, the
    migration of an older player, the carry across a replacement -- is one
    the stub takes, so a helper write the list has not heard of goes red
    here, in the gate, rather than in a scenario that holds the display."""

    def player(self, **kw):
        stub = StubPlayer(**kw)
        self.addCleanup(stub.close)
        return stub

    def test_the_stub_takes_every_property_the_shipping_helper_writes(self):
        # The migration of an older player and the carry, on a player launched
        # before the pins; the zap, on one this build launched, whose relay
        # (D-SINK-102) is the helper's own RelayServer in this process -- the
        # stub's parent, as the spawn makes the real relay (FakeRelay).
        older = self.player(argv=launch_argv(pins=False))
        seen = record_requests(older.client)
        helper.migrate_tls(older.client)
        helper.apply_carry(older.client, {"volume": 37.0, "mute": True, "fullscreen": False}, 2.0)
        stub = self.player(argv=launch_argv(), relay=True)
        relay = stub.relay
        zap = record_requests(stub.client)
        target = {"url": "http://127.0.0.1:9/a.ts", "name": "A", "id": "t:a", "group": "", "headers": {},
                  "relay": {"origin": "user", "host": "127.0.0.1", "port": 9}}
        helper.apply_channel(stub.client, target, stash=None, owner=None, label="test",
                             vouched_pid=stub.proc.pid)
        self.assertEqual(relay.tokens(), [target["relayToken"]])
        seen = seen + zap
        writes = [(c[1], err) for c, err in seen if c[0] in ("set_property", "set_property_string")]
        names = sorted(set(name for name, _ in writes))
        # The run reached the writes it is about: the title pair, the track
        # pair, the three header properties, the carry and a user-data key.
        for name in ("title", "force-media-title", "aid", "sid", "user-agent", "http-header-fields", "referrer",
                     "volume", "mute", "fullscreen", "pause"):
            self.assertIn(name, names)
        self.assertTrue(any(name.startswith("user-data/") for name in names), names)
        self.assertEqual([w for w in writes if w[1] != "success"], [])
        # And the stub is not answering success to everything: the same
        # connection, a name mpv does not have.
        self.assertEqual(stub.client.try_command("set_property", "no-such-property", 1), (False, None))
        self.assertEqual(zap[-1][1], "property not found")


class StubAgainstTheShippingOptionsFile(unittest.TestCase):
    """F-HARNESS-81: the join between the helper's writer and the stub's
    reader. The helper hands a user's mpvArgs to mpv as the file
    `write_mpv_args` makes, named by an `--include` token on the launch argv;
    a stub process started with that token must read what one started with
    the same tokens on its argv reads, where the token stands."""

    # The two modelled options a user's mpvArgs may name (the rest are the
    # plugin's own, which filter_mpv_args refuses), beside two the stub does
    # not model, which travel in the file all the same.
    TOKENS = ["--hwdec=no", "--demuxer-lavf-o-append=k=v,w", "--script-opts-append=a-b=c d#e%f",
              "--demuxer-lavf-o-append=x=y", "--no-border"]
    NAMES = ("demuxer-lavf-o", "script-opts")

    def read(self, argv):
        stub = StubPlayer(["mpv", "--idle=yes", "--input-ipc-server=@SOCK@"] + argv)
        self.addCleanup(stub.close)
        out = []
        for name in self.NAMES:
            out.append((stub.client.try_command("get_property", name),
                        stub.client.try_command("get_property", "option-info/%s/set-from-commandline" % name)))
        return out

    def test_the_file_the_helper_writes_reads_as_the_same_tokens_on_the_argv(self):
        work = tempfile.mkdtemp(prefix="stub-opts-")
        self.addCleanup(shutil.rmtree, work, True)
        os.chmod(work, 0o700)
        path = os.path.join(work, "mpv-args.conf")
        kept, rejected = helper.filter_mpv_args(list(self.TOKENS))
        self.assertEqual((kept, rejected), (self.TOKENS, []))
        helper.write_mpv_args(path, kept)
        on_argv = self.read(list(self.TOKENS))
        self.assertEqual(self.read(["--include=" + path]), on_argv)
        self.assertEqual(on_argv, [((True, {"k": "v,w", "x": "y"}), (True, True)),
                                   ((True, {"a-b": "c d#e%f"}), (True, True))])
        # Where the token stands: what follows it on the argv wins, as the
        # helper's own pins do, and what precedes it loses.
        late = self.read(["--include=" + path, "--demuxer-lavf-o-append=k=late"])
        self.assertEqual(late[0][0], (True, {"k": "late", "x": "y"}))
        early = self.read(["--demuxer-lavf-o-append=k=early", "--include=" + path])
        self.assertEqual(early[0][0], (True, {"k": "v,w", "x": "y"}))
        # And a file that is not there applies nothing.
        self.assertEqual(self.read(["--include=" + path + ".missing"]),
                         [((True, {}), (True, False)), ((True, {}), (True, False))])
