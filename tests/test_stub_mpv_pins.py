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
from helper_loader import load_helper  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
STUB = ROOT / "scripts" / "qa-stub-mpv.py"
helper = load_helper()


class StubPlayer:
    def __init__(self, argv, profiles=None):
        self.dir = tempfile.mkdtemp(prefix="stub-pins-")
        os.chmod(self.dir, 0o700)
        self.sock = os.path.join(self.dir, "s")
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
        shutil.rmtree(self.dir, ignore_errors=True)


def launch_argv(pins=True):
    dirs = {"cwd": "/nonexistent", "screenshots": "/nonexistent/shots",
            "watchLater": "/nonexistent/wl", "shaderCache": "/nonexistent/sc"}
    argv = helper.mpv_launch_argv("@SOCK@", [], dirs)
    if not pins:
        # A player started before the pin block: the same launch argv with
        # the tail cut off, which is what 0.15.0's mpv_launch_argv returned
        # (its base argv already carried --tls-verify=yes, and so does this).
        argv = argv[:len(argv) - len(helper.mpv_pin_block(dirs))]
    return argv


HTTPS_PROFILE = [{"name": "protocol.https", "options": [{"key": "stream-lavf-o", "value": "tls_verify=0"}]}]


class StubAgainstTheShippingReadBack(unittest.TestCase):
    def player(self, **kw):
        stub = StubPlayer(**kw)
        self.addCleanup(stub.close)
        return stub

    def test_a_player_this_plugin_starts_is_safe_as_it_comes(self):
        stub = self.player(argv=launch_argv())
        self.assertEqual(helper.read_tls_state(stub.client), (True, 0, 0))
        self.assertFalse(helper.migrate_tls(stub.client)["migrated"])
        helper.assert_tls_verification(stub.client, "test")      # raises when it refuses

    def test_a_player_from_before_the_pins_is_migrated_to_safe(self):
        stub = self.player(argv=launch_argv(pins=False))
        # Three pins not held: load-auto-profiles reads "auto", and the
        # demuxer map holds neither the protocol list (D-SINK-55) nor, since
        # lane-p1c (2026-10-29), the format list (D-SINK-62).
        self.assertEqual(helper.read_tls_state(stub.client), (True, 0, 3))
        result = helper.migrate_tls(stub.client)
        self.assertEqual((result["migrated"], result["verify"], result["optionCount"], result["unpinned"]),
                         (True, True, 0, 0))

    def test_a_per_file_profile_on_a_loose_player_is_counted_and_refused(self):
        stub = self.player(argv=launch_argv(pins=False), profiles=HTTPS_PROFILE)
        result = helper.migrate_tls(stub.client)
        self.assertEqual((result["migrated"], result["unpinned"]), (True, 1))
        with self.assertRaises(helper.HelperError) as caught:
            helper.assert_tls_verification(stub.client, "test")
        self.assertEqual(caught.exception.code, "tls_unverified")

    def test_the_same_profile_is_harmless_to_a_pinned_player(self):
        stub = self.player(argv=launch_argv(), profiles=HTTPS_PROFILE)
        self.assertEqual(helper.read_tls_state(stub.client), (True, 0, 0))


if __name__ == "__main__":
    unittest.main()
