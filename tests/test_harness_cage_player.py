"""F-HARNESS-45 (2026-10-25): a player under a nested headless cage.

The m3 and pip cells of the F-HARNESS-18 live proof left mpv aborting
inside the cage lanes' rigs: 30 cores and 7 "Process crashed: mpv" cards
on the user's REAL desktop, none of them at a teardown. The cause, measured
with a renamed copy of mpv under a WLR_RENDERER=pixman cage on the private
bus (QA-RESULTS "F-HARNESS-45"): mpv 0.41.0's automatic VO probe trips its
own assertion, `vo_x11_init: Assertion '!vo->x11' failed`
(video/out/x11_common.c:679), on a compositor that can serve no hardware GL
or Vulkan context -- `waylandvk` loses its surface, `x11vk` fails (with the
cage's lazy Xwayland or with no DISPLAY at all), the wayland EGL context
comes up on llvmpipe and is refused as a software renderer without
releasing its Wayland state (a pointer that shares a union with
`vo->x11`), and `x11egl` asserts -- mpv-player/mpv#17190, fixed on master
by a58dd8ac4, in no release as of 2026-10-26. `--gpu-sw=yes` makes the probe accept the
llvmpipe context and the player comes up; `--vo=wlshm` does not (a
zero-size wl_viewport destination, and the compositor disconnects it).

Three things are pinned here, each DRIVEN rather than grepped (rule 14):

1. run.sh's `harness_env` appends `--gpu-sw=yes --ao=null` to the mpvArgs
   lever (OMARCHY_IPTV_MPV_ARGS) when the environment says pixman
   (WLR_RENDERER, inherited inside a cage's child) or the caller says so
   (OMARCHY_IPTV_HARNESS_SOFTWARE_GPU=1), BEHIND the caller's own tokens,
   never over a caller that already named `--gpu-sw` or `--ao`, never when
   the caller said no, and never for a live session; and the shipped
   helper's filter passes the result with `--tls-verify=yes` still the last
   token (D-SINK-13's trailing re-assertion).
2. private-bus.sh hands its command a soft RLIMIT_CORE of 0: the second
   layer, so a crash that still happens stores no file.
3. Every scenario `h()` that points run.sh at a cage's display sets the
   lever -- bookkeeping by shape, the F-HARNESS-18 pin's kind; the proof
   for the behaviour is 1.

Rule 11: `FH45_ROOT=<tree>` runs these against another checkout. Red on dev
96a1487: 1 fails everywhere the lever is expected, 2 fails (soft limit
unlimited), 3 fails on all five files.
"""

import json
import os
import pathlib
import re
import resource
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(os.environ.get("FH45_ROOT") or pathlib.Path(__file__).resolve().parent.parent)
RUN_SH = ROOT / "scripts" / "dev-harness" / "run.sh"
QA_LIB = ROOT / "scripts" / "qa-lib.sh"
PRIVATE_BUS = ROOT / "scripts" / "dev-harness" / "private-bus.sh"
HELPER = ROOT / "bin" / "omarchy-iptv"
SCENARIOS = ROOT / "scripts" / "dev-harness"

# The harness side, in bash: qa-lib.sh sourced, `harness_env` pulled out of
# run.sh as text and evaluated (so a revert of run.sh is a revert of what
# runs here, as tests/test_harness_home.py does), called once, and the two
# variables it may have set printed.
DRIVER = r'''
set -u
QA_LIB=$1 RUN_SH=$2 SCRATCH=$3 REAL_RUNTIME=$4
. "$QA_LIB"
die() { printf 'die: %s\n' "$*" >&2; exit 97; }
eval "$(sed -n '/^harness_env() {/,/^}/p' "$RUN_SH")"
declare -F harness_env >/dev/null || { echo "run.sh defines no harness_env" >&2; exit 96; }
harness_env
printf 'ARGS=%s\nFLAG=%s\n' "${OMARCHY_IPTV_MPV_ARGS-<unset>}" "${OMARCHY_IPTV_HARNESS_SOFTWARE_GPU-<unset>}"
'''

# The shipped helper, loaded the way tests/test_harness_home.py's probe
# loads it, asked to filter what harness_env produced and to build the
# launch argv over it.
FILTER_PROBE = r'''
import importlib.machinery, importlib.util, json, os, sys
sys.dont_write_bytecode = True
loader = importlib.machinery.SourceFileLoader("omarchy_iptv_fh45", sys.argv[1])
spec = importlib.util.spec_from_loader("omarchy_iptv_fh45", loader)
h = importlib.util.module_from_spec(spec)
loader.exec_module(h)
tokens = sys.argv[2].split()
kept, rejected = h.filter_mpv_args(tokens)
dirs = {"screenshots": "/s", "watchLater": "/w", "shaderCache": "/c"}
argv = h.mpv_launch_argv("/r/mpv.sock", kept, dirs)
pins = len(h.mpv_pin_block(dirs)) if hasattr(h, "mpv_pin_block") else 1
print(json.dumps({"kept": kept, "rejected": rejected, "argv": argv, "pins": pins}))
'''


class HarnessEnvSoftwareGpu(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fh45-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.runtime = os.path.join(self.tmp, "run")
        os.makedirs(self.runtime, mode=0o700)
        self.scratch = os.path.join(self.tmp, "harness")
        os.makedirs(self.scratch, mode=0o700)

    def harness_env(self, **extra):
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": "C.UTF-8",
            "HOME": self.tmp,
            "XDG_RUNTIME_DIR": self.runtime,
            "WAYLAND_DISPLAY": "wayland-fh45",
        }
        env.update({k: v for k, v in extra.items() if v is not None})
        r = subprocess.run(["bash", "-c", DRIVER, "fh45", str(QA_LIB), str(RUN_SH), self.scratch, self.runtime],
                           env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = dict(line.split("=", 1) for line in r.stdout.strip().splitlines() if "=" in line)
        return out.get("ARGS"), out.get("FLAG")

    def test_pixman_in_the_environment_appends_both_tokens_and_sets_the_flag(self):
        args, flag = self.harness_env(WLR_RENDERER="pixman", WLR_BACKENDS="headless")
        self.assertEqual(args, "--gpu-sw=yes --ao=null")
        self.assertEqual(flag, "1")

    def test_the_tokens_go_behind_the_callers_own(self):
        args, _ = self.harness_env(WLR_RENDERER="pixman", OMARCHY_IPTV_MPV_ARGS="--tls-ca-file=/x --demuxer-max-bytes=4MiB")
        self.assertEqual(args, "--tls-ca-file=/x --demuxer-max-bytes=4MiB --gpu-sw=yes --ao=null")

    def test_a_caller_that_named_either_option_keeps_its_word(self):
        args, _ = self.harness_env(WLR_RENDERER="pixman", OMARCHY_IPTV_MPV_ARGS="--gpu-sw=no --ao=pipewire")
        self.assertEqual(args, "--gpu-sw=no --ao=pipewire")
        args, _ = self.harness_env(WLR_RENDERER="pixman", OMARCHY_IPTV_MPV_ARGS="--no-gpu-sw")
        self.assertEqual(args, "--no-gpu-sw --ao=null")
        args, _ = self.harness_env(WLR_RENDERER="pixman", OMARCHY_IPTV_MPV_ARGS="--ao=alsa")
        self.assertEqual(args, "--ao=alsa --gpu-sw=yes")

    def test_the_callers_explicit_word_decides_either_way(self):
        args, flag = self.harness_env(OMARCHY_IPTV_HARNESS_SOFTWARE_GPU="1")
        self.assertEqual((args, flag), ("--gpu-sw=yes --ao=null", "1"))
        args, flag = self.harness_env(WLR_RENDERER="pixman", OMARCHY_IPTV_HARNESS_SOFTWARE_GPU="0")
        self.assertEqual((args, flag), ("<unset>", "0"))

    def test_a_live_session_and_a_gles2_cage_get_nothing(self):
        args, flag = self.harness_env()
        self.assertEqual((args, flag), ("<unset>", "<unset>"))
        args, flag = self.harness_env(OMARCHY_IPTV_MPV_ARGS="--tls-ca-file=/x")
        self.assertEqual((args, flag), ("--tls-ca-file=/x", "<unset>"))
        # A gles2 headless cage serves hardware contexts (the chno-mutations
        # spike plays served streams under one); only pixman is the signal.
        args, flag = self.harness_env(WLR_RENDERER="gles2", WLR_BACKENDS="headless")
        self.assertEqual((args, flag), ("<unset>", "<unset>"))

    def test_the_shipped_helper_passes_the_tokens_and_keeps_tls_verify_last(self):
        args, _ = self.harness_env(WLR_RENDERER="pixman", OMARCHY_IPTV_MPV_ARGS="--tls-ca-file=/x")
        r = subprocess.run(["python3", "-I", "-c", FILTER_PROBE, str(HELPER), args],
                           env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": self.tmp, "LANG": "C.UTF-8",
                                "PYTHONDONTWRITEBYTECODE": "1", "XDG_RUNTIME_DIR": self.runtime},
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["rejected"], [])
        self.assertEqual(out["kept"], ["--tls-ca-file=/x", "--gpu-sw=yes", "--ao=null"])
        # Since 2026-10-29 the user's tokens are followed by the whole pin
        # block (D-SINK-43..46), which still ends with --tls-verify=yes.
        pins = out["pins"]
        self.assertEqual(out["argv"][-pins - 3:-pins], ["--tls-ca-file=/x", "--gpu-sw=yes", "--ao=null"])
        self.assertEqual(out["argv"][-1], "--tls-verify=yes")
        self.assertEqual(out["argv"][0], "mpv")


class PrivateBusCoreLimit(unittest.TestCase):
    """OBSERVED: private-bus.sh is run for real with a probe that reports its
    own RLIMIT_CORE. The probe's parent (this process) is given a non-zero
    soft limit first, so the 0 the probe sees can only have come from the
    script; a machine whose hard limit is already 0 cannot run this and says
    so."""

    def test_private_bus_hands_its_command_a_soft_core_limit_of_zero(self):
        soft, hard = resource.getrlimit(resource.RLIMIT_CORE)
        if hard == 0:
            self.skipTest("RLIMIT_CORE hard limit is 0 here; the script's soft 0 cannot be told from it")
        want_soft = hard if hard != resource.RLIM_INFINITY else resource.RLIM_INFINITY

        def raise_core_limit():
            resource.setrlimit(resource.RLIMIT_CORE, (want_soft, hard))

        tmp = tempfile.mkdtemp(prefix="fh45-bus-")
        self.addCleanup(shutil.rmtree, tmp, True)
        bus = os.path.join(tmp, "b")
        probe = "import json, resource; print(json.dumps(resource.getrlimit(resource.RLIMIT_CORE)))"
        env = dict(os.environ, HOME=tmp, XDG_RUNTIME_DIR=tmp)
        control = subprocess.run(["python3", "-I", "-c", probe], env=env, preexec_fn=raise_core_limit,
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(control.returncode, 0, control.stderr)
        self.assertNotEqual(json.loads(control.stdout)[0], 0, "the control probe already saw a soft limit of 0; nothing here can be told")
        proc = subprocess.run(["bash", str(PRIVATE_BUS), bus, "20", "python3", "-I", "-c", probe],
                              env=env, preexec_fn=raise_core_limit, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        seen_soft, seen_hard = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(seen_soft, 0, "private-bus.sh did not lower the soft core limit to 0")
        self.assertEqual(seen_hard, hard, "the hard limit is not the script's to change")
        self.assertFalse(os.path.exists(bus), "private-bus.sh left its directory behind")


class CageScenariosSetTheLever(unittest.TestCase):
    """Every `h()` that runs run.sh with WAYLAND_DISPLAY=$NESTED -- the one
    line in each cage scenario that points the harness at the cage -- also
    sets OMARCHY_IPTV_HARNESS_SOFTWARE_GPU=1. By shape, not by name: the set
    is whatever the tree holds, and it must hold the five known ones so the
    pin cannot pass over nothing."""

    POINTS_AT_NESTED = re.compile(r'^h\(\) *\{ env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY="\$NESTED" (.*)"\$RUN" "\$@"; \}$')

    def test_every_h_that_points_run_sh_at_the_cage_sets_the_lever(self):
        found, missing = [], []
        for path in sorted(SCENARIOS.rglob("*.sh")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                m = self.POINTS_AT_NESTED.match(line)
                if not m:
                    continue
                rel = str(path.relative_to(ROOT))
                found.append(rel)
                if "OMARCHY_IPTV_HARNESS_SOFTWARE_GPU=1 " not in m.group(1):
                    missing.append("%s:%d" % (rel, number))
        self.assertEqual(missing, [], "h() points run.sh at a cage's display without the software-GPU lever")
        for name in ("key-scenario.sh", "logo-scenario.sh", "open-scenario.sh", "clip-scenario.sh", "spikes/first-open/run.sh"):
            self.assertIn("scripts/dev-harness/" + name, found)


if __name__ == "__main__":
    unittest.main()
