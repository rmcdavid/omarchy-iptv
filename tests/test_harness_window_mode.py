"""The harness-only window mode (docs/SPIKE-CAGE-HEADLESS.md), the half that
runs with no display.

Under a compositor with no zwlr_layer_shell_v1 -- the headless cage the dev
harness can run inside -- the guide's production window, a PanelWindow with
WlrLayershell attached, never maps. `run.sh --window floating` hosts the same
content in a FloatingWindow instead, and Guide.qml chooses the window with a
Loader so the layer-shell Component is not even instantiated in that mode.
Three things are pinned here, and where a call is possible the check is a
call rather than a search for the string the code was written to contain
(CLAUDE.md 14):

  1. run.sh exposes the mode and REFUSES anything but its two values, run for
     real. A typo must die, not start the production window under a
     compositor that cannot map it and make every pixel check after it
     vacuous. Both accepted values are shown to be consumed, again by running
     the parser, without ever starting a shell.
  2. Guide.qml's floating branch holds no `WlrLayershell` token, found by
     brace-matching the Component rather than by a line grep; and the layer
     branch DOES hold the layer and the focus mode, so the parser cannot pass
     by finding nothing.
  3. The names that join run.sh to shell.qml to Guide.qml -- the environment
     variable and the initial property -- resolve on both sides (CLAUDE.md
     13), and neither is a user setting anywhere in manifest.json.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN_SH = ROOT / "scripts" / "dev-harness" / "run.sh"
SHELL_QML = (ROOT / "scripts" / "dev-harness" / "shell.qml").read_text(encoding="utf-8")
GUIDE = (ROOT / "Guide.qml").read_text(encoding="utf-8")
RUN_SH_TEXT = RUN_SH.read_text(encoding="utf-8")
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


def run_sh(*args):
    """run.sh with everything it could touch pointed at a throwaway directory.

    Every invocation here dies in the option parser or prints usage, so no
    shell is started; the scratch dir is belt and braces, and the display
    variables are cleared so even a bug could not reach the live session."""
    env = dict(os.environ)
    env.pop("WAYLAND_DISPLAY", None)
    env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
    with tempfile.TemporaryDirectory() as tmp:
        env["OMARCHY_IPTV_HARNESS_DIR"] = tmp
        return subprocess.run(["bash", str(RUN_SH)] + list(args), capture_output=True,
                              text=True, timeout=30, env=env, cwd=str(ROOT))


def component_block(source, component_id):
    """The text of `Component { id: <component_id> ... }`, by brace matching."""
    match = re.search(r"Component \{\s*\n\s*id: %s\b" % re.escape(component_id), source)
    if match is None:
        return None
    start = match.start()
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    return None


class RunShExposesTheModeTest(unittest.TestCase):

    def test_an_unknown_mode_dies_naming_the_two_it_takes(self):
        completed = run_sh("--window", "bogus")
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("--window takes layer or floating", completed.stderr)
        self.assertNotIn("unknown option", completed.stderr)

    def test_both_modes_are_consumed_by_the_parser(self):
        # The option after --window MODE is a deliberate unknown: the parser
        # must reach IT, which it only does after consuming the mode and its
        # value. A tree without --window dies on --window itself.
        for mode in ("layer", "floating"):
            completed = run_sh("--window", mode, "--no-such-option")
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("unknown option: --no-such-option", completed.stderr, mode)
            self.assertNotIn("unknown option: --window", completed.stderr, mode)

    def test_usage_lists_the_mode(self):
        completed = run_sh("usage")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--window MODE", completed.stdout)
        self.assertIn("floating", completed.stdout)


class GuideWindowBranchesTest(unittest.TestCase):

    def test_the_floating_branch_carries_no_layer_shell_token(self):
        floating = component_block(GUIDE, "floatingHost")
        self.assertIsNotNone(floating, "Guide.qml has no `Component { id: floatingHost }`")
        self.assertIn("FloatingWindow {", floating)
        self.assertNotIn("WlrLayershell", floating)
        self.assertNotIn("PanelWindow", floating)

    def test_the_layer_branch_is_the_production_window(self):
        # The parser above would also pass on an empty Component; this is
        # the same slicer finding what production needs, so a false negative
        # in it cannot hide behind the negative assertion.
        layer = component_block(GUIDE, "layerHost")
        self.assertIsNotNone(layer, "Guide.qml has no `Component { id: layerHost }`")
        self.assertIn("PanelWindow {", layer)
        self.assertIn("WlrLayershell.layer: WlrLayer.Overlay", layer)
        self.assertIn("WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive", layer)
        self.assertNotIn("FloatingWindow", layer)

    def test_the_layer_shell_tokens_live_only_inside_that_component(self):
        layer = component_block(GUIDE, "layerHost") or ""
        outside = GUIDE.replace(layer, "")
        self.assertNotIn("WlrLayershell.", outside,
                         "a WlrLayershell attached property escaped the layer Component")


class NamesJoinTest(unittest.TestCase):

    def test_the_environment_variable_run_sh_exports_is_the_one_shell_qml_reads(self):
        exported = re.findall(r'export (OMARCHY_IPTV_HARNESS_WINDOW)="\$WINDOW"', RUN_SH_TEXT)
        read = re.findall(r'Quickshell\.env\("(OMARCHY_IPTV_HARNESS_WINDOW)"\) === "floating"', SHELL_QML)
        self.assertEqual(exported, ["OMARCHY_IPTV_HARNESS_WINDOW"])
        self.assertEqual(read, ["OMARCHY_IPTV_HARNESS_WINDOW"])
        # and it is recorded for restart-shell, or a restarted shell would
        # come back with the production window under the same cage
        self.assertIn('qa_env_line OMARCHY_IPTV_HARNESS_WINDOW "$OMARCHY_IPTV_HARNESS_WINDOW"', RUN_SH_TEXT)

    def test_the_initial_property_shell_qml_passes_is_the_one_guide_qml_declares(self):
        passed = re.search(r"setSource\(\s*\"file://\" \+ harness\.repoRoot \+ \"/Guide\.qml\",\s*"
                           r"harness\.floatingGuide \? \{ (\w+): true \} : \{\}\)", SHELL_QML)
        self.assertIsNotNone(passed, "shell.qml does not hand Guide.qml an initial property through setSource")
        name = passed.group(1)
        self.assertRegex(GUIDE, r"\n  property bool %s: false\n" % re.escape(name))
        # decided once, at completion, from that property
        self.assertIn("Component.onCompleted: sourceComponent = root.%s ? floatingHost : layerHost" % name, GUIDE)

    def test_the_switch_is_not_a_user_setting(self):
        def keys(node, out):
            if isinstance(node, dict):
                for k, v in node.items():
                    out.add(k)
                    keys(v, out)
            elif isinstance(node, list):
                for v in node:
                    keys(v, out)
            return out
        names = keys(MANIFEST, set())
        self.assertNotIn("harnessFloatingWindow", names)
        self.assertNotIn("floatingWindow", names)
        self.assertNotIn("windowMode", names)


if __name__ == "__main__":
    unittest.main()
