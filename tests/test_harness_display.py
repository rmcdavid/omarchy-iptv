"""F-HARNESS-47 and F-HARNESS-48 (2026-10-26): what the processes the dev
harness starts may inherit about displays and compositors.

F-HARNESS-47 (P2). A caged harness run inherited the caller's DISPLAY --
the owner's Xwayland, `:0` -- and mpv's VO probe tries `x11vk` after
`waylandvk` loses its surface (QA-RESULTS "F-HARNESS-45"), so a player
started toward a cage could map its window on the owner's real desktop.
run.sh's harness_env now drops DISPLAY always (nothing in the harness or the
plugin needs X), keeps it only on an explicit opt-in and only on the desk,
and drops HYPRLAND_INSTANCE_SIGNATURE whenever the target is nested.

F-HARNESS-48. prepare_root linked the scratch runtime's `hypr` to the real
one "so hyprctl works". Through it the socket path was 123 bytes at the
default harness directory, past sun_path's 108, so hyprctl could not connect
-- an accident of a path's length: through a 106-byte path it answered the
owner's live Hyprland. The link is gone, and one an older run.sh left is
removed.

Everything here is DRIVEN (rule 14): run.sh's own functions, extracted from
the file as text and run (tests/test_harness_home.py's method), under a
runtime directory built here -- a Hyprland lock in the shape 0.56.2 writes
(pid, then the session's Wayland socket name) and a listening UNIX socket
where Hyprland's would be. Nothing reads or reaches the owner's compositor,
and DISPLAY is a bogus `:99`.

Rule 11: `FH47_ROOT=<tree>` runs these against another checkout. On dev
e243c29 (an export of it) every case below fails except the opt-in on the
desk, which held there by not dropping anything.
"""

import os
import pathlib
import shutil
import socket
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(os.environ.get("FH47_ROOT") or pathlib.Path(__file__).resolve().parent.parent)
RUN_SH = ROOT / "scripts" / "dev-harness" / "run.sh"
QA_LIB = ROOT / "scripts" / "qa-lib.sh"
HERE = ROOT / "scripts" / "dev-harness"

SIG = "fh47sig"
DESK = "wayland-desk"
CAGE = "wayland-cage"

# run.sh's harness_env (and, in mode `root`, prepare_root with what it
# calls) pulled out of the file and run once, as run.sh's `start` runs them.
# Then what the harness's processes would inherit is printed, and in mode
# `root` a UNIX connect is made exactly where hyprctl looks:
# $XDG_RUNTIME_DIR/hypr/<signature>/.socket.sock, with the signature named by
# the test (as if it had been put back), so the runtime directory alone is
# what is judged.
DRIVER = r'''
set -u
QA_LIB=$1 RUN_SH=$2 SCRATCH=$3 REAL_RUNTIME=$4 HERE=$5 PLUGIN_ROOT=$6 SHELL_DIR=$7 MODE=$8 PROBE_SIG=$9
INSTANCE=""
. "$QA_LIB"
die() { printf 'die: %s\n' "$*" >&2; exit 97; }
eval "$(sed -n '/^harness_env() {/,/^}/p' "$RUN_SH")"
eval "$(sed -n '/^qs_root() *{.*}$/p' "$RUN_SH")"
eval "$(sed -n '/^seed_scratch_[a-z_]*() {/,/^}/p' "$RUN_SH")"
eval "$(sed -n '/^prepare_root() {/,/^}/p' "$RUN_SH")"
for f in harness_env qs_root prepare_root; do
  declare -F "$f" >/dev/null || { echo "run.sh defines no $f" >&2; exit 96; }
done
harness_env
printf 'DISPLAY=%s\nSIG=%s\nWL=%s\n' "${DISPLAY-<unset>}" "${HYPRLAND_INSTANCE_SIGNATURE-<unset>}" "${WAYLAND_DISPLAY-<unset>}"
[[ $MODE == root ]] || exit 0
prepare_root >"$SCRATCH/prepare.log" 2>&1 || { cat "$SCRATCH/prepare.log" >&2; exit 95; }
printf 'HYPR=%s\n' "$([[ -e $SCRATCH/runtime/hypr || -L $SCRATCH/runtime/hypr ]] && echo present || echo absent)"
exec python3 -I -c '
import errno, socket, sys
path = sys.argv[1]
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
try:
    s.connect(path)
    print("CONNECT=connected")
except OSError as e:
    print("CONNECT=refused:%s" % errno.errorcode.get(e.errno, e.errno))
' "$XDG_RUNTIME_DIR/hypr/$PROBE_SIG/.socket.sock"
'''


def short_tmpdir(prefix):
    """A temporary directory short enough that a socket under the old link
    would be inside sun_path: otherwise the old tree would read "refused"
    for the length, which is the accident this test must not lean on."""
    tmp = tempfile.mkdtemp(prefix=prefix)
    probe = os.path.join(tmp, "h", "runtime", "hypr", SIG, ".socket.sock")
    if len(probe.encode()) >= 100 and os.path.isdir("/tmp"):
        shutil.rmtree(tmp, ignore_errors=True)
        tmp = tempfile.mkdtemp(prefix=prefix, dir="/tmp")
    return tmp


class HarnessDisplay(unittest.TestCase):
    def setUp(self):
        self.tmp = short_tmpdir("fh47-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        base = pathlib.Path(self.tmp)
        self.runtime = base / "rt"
        self.scratch = base / "h"
        self.home = base / "home"
        for d in (self.runtime, self.scratch, self.home):
            d.mkdir(mode=0o700)
        lock = self.runtime / "hypr" / SIG / "hyprland.lock"
        lock.parent.mkdir(parents=True, mode=0o700)
        lock.write_text("4242\n%s\n" % DESK, encoding="utf-8")
        self.hypr_socket = lock.parent / ".socket.sock"
        # The host's shell directory, as prepare_root links it: two
        # directories, nothing read from them here.
        self.shell_dir = base / "omarchy" / "shell"
        for d in ("Commons", "Ui"):
            (self.shell_dir / d).mkdir(parents=True)

    def drive(self, mode="env", target=DESK, **extra):
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": str(self.home),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "WAYLAND_DISPLAY": target,
            "DISPLAY": ":99",
            "HYPRLAND_INSTANCE_SIGNATURE": SIG,
        }
        for k, v in extra.items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = v
        r = subprocess.run(["bash", "-c", DRIVER, "fh47", str(QA_LIB), str(RUN_SH), str(self.scratch),
                            str(self.runtime), str(HERE), str(ROOT), str(self.shell_dir), mode, SIG],
                           env=env, capture_output=True, text=True, timeout=120)
        if r.returncode == 96:
            raise AssertionError(r.stderr.strip())
        out = dict(line.split("=", 1) for line in r.stdout.strip().splitlines() if "=" in line)
        return r, out

    # -- DISPLAY and the signature (F-HARNESS-47)

    def test_a_nested_target_inherits_neither_display_nor_the_signature(self):
        r, out = self.drive(target=CAGE)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((out["DISPLAY"], out["SIG"]), ("<unset>", "<unset>"))
        self.assertEqual(out["WL"], str(self.runtime / CAGE))

    def test_the_desk_keeps_its_signature_and_still_loses_display(self):
        r, out = self.drive(target=DESK)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((out["DISPLAY"], out["SIG"]), ("<unset>", SIG))

    def test_an_absolute_desk_socket_is_the_desk(self):
        r, out = self.drive(target=str(self.runtime / DESK))
        self.assertEqual((out["DISPLAY"], out["SIG"]), ("<unset>", SIG))

    def test_the_opt_in_keeps_display_on_the_desk(self):
        r, out = self.drive(target=DESK, OMARCHY_IPTV_HARNESS_KEEP_DISPLAY="1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((out["DISPLAY"], out["SIG"]), (":99", SIG))

    def test_the_opt_in_against_a_nested_target_is_refused_not_ignored(self):
        r, out = self.drive(target=CAGE, OMARCHY_IPTV_HARNESS_KEEP_DISPLAY="1")
        self.assertEqual(r.returncode, 97, "harness_env did not refuse: %r" % (out,))
        self.assertIn("F-HARNESS-47", r.stderr)
        self.assertNotIn("DISPLAY", out)

    def test_a_cage_child_is_nested_whatever_socket_it_names(self):
        # Inside a cage's child the wlroots variables are inherited from the
        # cage; no Hyprland session carries them.
        r, out = self.drive(target=DESK, WLR_BACKENDS="headless", WLR_RENDERER="pixman")
        self.assertEqual((out["DISPLAY"], out["SIG"]), ("<unset>", "<unset>"))

    def test_without_a_signature_display_is_still_dropped(self):
        r, out = self.drive(target=DESK, HYPRLAND_INSTANCE_SIGNATURE=None)
        self.assertEqual((out["DISPLAY"], out["SIG"]), ("<unset>", "<unset>"))

    def test_a_signature_naming_no_instance_is_dropped_against_any_target(self):
        r, out = self.drive(target=DESK, HYPRLAND_INSTANCE_SIGNATURE="nosuchinstance")
        self.assertEqual((out["DISPLAY"], out["SIG"]), ("<unset>", "<unset>"))

    # -- the runtime directory (F-HARNESS-48)

    def listening(self):
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(srv.close)
        srv.bind(str(self.hypr_socket))
        srv.listen(4)
        return srv

    def test_no_signature_finds_a_compositor_under_the_scratch_runtime(self):
        self.listening()
        # Positive controls. The stand-in answers where Hyprland's socket
        # sits, and the path the old link made is inside sun_path, so on a
        # tree that still links it the connect below SUCCEEDS.
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.connect(str(self.hypr_socket))
        probe.close()
        through_link = self.scratch / "runtime" / "hypr" / SIG / ".socket.sock"
        self.assertLess(len(str(through_link).encode()), 108)
        r, out = self.drive(mode="root", target=CAGE)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(out["CONNECT"], "refused:ENOENT")
        self.assertEqual(out["HYPR"], "absent")

    def test_a_link_an_older_run_sh_left_is_removed(self):
        self.listening()
        (self.scratch / "runtime").mkdir(mode=0o700)
        os.symlink(str(self.runtime / "hypr"), str(self.scratch / "runtime" / "hypr"))
        r, out = self.drive(mode="root", target=DESK)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(out["CONNECT"], "refused:ENOENT")
        self.assertEqual(out["HYPR"], "absent")

    def test_something_else_at_runtime_hypr_stops_the_start(self):
        (self.scratch / "runtime" / "hypr").mkdir(parents=True, mode=0o700)
        r, out = self.drive(mode="root", target=DESK)
        # run.sh's die, which the driver stands in for, exits the shell.
        self.assertEqual(r.returncode, 97, "prepare_root started over a runtime/hypr it did not make: %r" % (out,))
        self.assertIn("runtime/hypr exists", (self.scratch / "prepare.log").read_text())
        self.assertNotIn("HYPR", out)


if __name__ == "__main__":
    unittest.main()
