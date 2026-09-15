"""Picture in picture (M2-05), the half that runs with no display.

Two things are pinned here.

FIRST, the fake compositor. `scripts/dev-harness/stub-hyprctl.py` is what the
harness scenario drives the service against, and CLAUDE.md rule 10 says a
test double must never be more forgiving than the real thing. So every
behaviour it models is asserted against the transcript the M2-05-00 gate
recorded in docs/QA-RESULTS.md -- including the two that make the design's
original failure detection unimplementable, because a fake that got either of
them backwards would make the plugin pass its own tests and fail on a desktop:

  * a dispatch aimed at a window that does not exist answers `ok` with exit
    status 0 and changes nothing (D-PIP-2, ruling PIP11);
  * `action` is ignored -- float and pin toggle, and an "unset" aimed at a
    tiled window floats it (G-3, ruling PIP10).

SECOND, the shape those two rulings force on Service.qml. `pipVerify` against
a fresh read is the only definition of success, and no float or pin step may
be issued without a live read behind it. Both are structural properties of
the file, and a structural property with nothing asserting it is one
refactor away from gone.

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
STUB = ROOT / "scripts" / "dev-harness" / "stub-hyprctl.py"
SERVICE = (ROOT / "Service.qml").read_text(encoding="utf-8")

ADDRESS = "0x559c6893d940"
FOREIGN = "0x559c687e09a0"

# The opening capture of the gate's own run: our player tiled at [690, 38]
# 650x718 with only Omarchy's rule-applied tag, and the user's other window
# beside it. The foreign entry is PLY-RST-11's case, a second client of the
# same class that is not ours.
def base_state():
    return {
        "clients": [
            {"class": "com.anthropic.Claude", "pid": 1242840, "address": FOREIGN,
             "at": [12, 38], "size": [650, 718], "floating": False, "pinned": False,
             "monitor": 0, "workspace": {"id": 1}, "tags": ["default-opacity*"]},
            {"class": "omarchy-iptv", "pid": 1937373, "address": ADDRESS,
             "at": [690, 38], "size": [650, 718], "floating": False, "pinned": False,
             "monitor": 0, "workspace": {"id": 1}, "tags": ["default-opacity*"]},
        ],
        "monitors": [
            {"id": 0, "name": "eDP-1", "width": 1366, "height": 768, "scale": 1,
             "transform": 0, "reserved": [0, 26, 0, 0], "x": 0, "y": 0},
        ],
    }


class StubDriver:
    """One scratch state file per test, so nothing leaks between them."""

    def __init__(self, provider="lua", state=None):
        self.dir = tempfile.TemporaryDirectory(prefix="omarchy-iptv-pip-")
        self.state_path = os.path.join(self.dir.name, "state.json")
        self.log_path = os.path.join(self.dir.name, "calls.log")
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(state if state is not None else base_state(), handle)
        self.env = dict(os.environ)
        self.env["STUB_HYPRCTL_STATE"] = self.state_path
        self.env["STUB_HYPRCTL_LOG"] = self.log_path
        self.env["STUB_HYPRCTL_PROVIDER"] = provider

    def run(self, *args):
        done = subprocess.run(["python3", str(STUB)] + list(args), env=self.env,
                              capture_output=True, text=True, timeout=30)
        return done.returncode, done.stdout.strip()

    def dispatch(self, expression):
        return self.run("dispatch", expression)

    def window(self, address=ADDRESS):
        with open(self.state_path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
        for client in state["clients"]:
            if client["address"] == address:
                return client
        return None

    def calls(self):
        if not os.path.exists(self.log_path):
            return []
        with open(self.log_path, "r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def close(self):
        self.dir.cleanup()


def lua(verb, address=ADDRESS, **fields):
    parts = ['window = "address:%s"' % address]
    for key in ("action", "mode", "tag"):
        if key in fields:
            parts.append('%s = "%s"' % (key, fields[key]))
    for key in ("x", "y"):
        if key in fields:
            parts.append("%s = %d" % (key, fields[key]))
    return "hl.dsp.window.%s({ %s })" % (verb, ", ".join(parts))


class StubFidelityTest(unittest.TestCase):
    """docs/QA-RESULTS.md, the M2-05 gate section, made executable."""

    def setUp(self):
        self.hypr = StubDriver()
        self.addCleanup(self.hypr.close)

    def test_the_stub_exists_and_is_executable(self):
        self.assertTrue(STUB.exists(), STUB)
        self.assertTrue(os.access(STUB, os.X_OK), "stub-hyprctl.py must be executable")

    def test_systeminfo_is_where_the_config_provider_is_reported(self):
        # It is absent from `hyprctl -j version`, which is where a lane would
        # look first; the service reads it here and chooses its spelling once.
        code, out = self.hypr.run("systeminfo")
        self.assertEqual(code, 0)
        self.assertIn("configProvider: lua", out)
        self.assertIn("0.56.2", out)

    def test_a_dispatch_at_an_address_that_does_not_exist_reports_success(self):
        # D-PIP-2, the finding that makes ruling PIP11 necessary. All four of
        # these did nothing and all four answered rc 0 `ok` on the live
        # compositor. If this ever asserts the opposite, failure detection
        # built on exit status would start passing its own tests.
        before = json.dumps(self.hypr.window())
        for expression in (lua("tag", address="0xdeadbeef", tag="+zz"),
                           lua("move", address="0xdeadbeef", x=10, y=10),
                           lua("float", address="0xdeadbeef", action="toggle"),
                           lua("pin", address="0xdeadbeef")):
            code, out = self.hypr.dispatch(expression)
            self.assertEqual((code, out), (0, "ok"), expression)
        self.assertEqual(json.dumps(self.hypr.window()), before)

    def test_a_refusal_arrives_as_warning_text_with_exit_status_zero(self):
        # `pin` on a tiled window. The only channel a refusal has is stdout.
        code, out = self.hypr.dispatch(lua("pin"))
        self.assertEqual(code, 0)
        self.assertIn("Window does not qualify to be pinned", out)
        self.assertIs(self.hypr.window()["pinned"], False)

    def test_action_is_ignored_and_float_toggles_unconditionally(self):
        # G-3, exactly as the gate ran it. The gate's own probe gave a FALSE
        # PASS here by only applying "set" once, from tiled, where a set and a
        # toggle are indistinguishable.
        self.assertIs(self.hypr.window()["floating"], False)
        self.hypr.dispatch(lua("float", action="set"))
        self.assertIs(self.hypr.window()["floating"], True)
        self.hypr.dispatch(lua("float", action="set"))
        self.assertIs(self.hypr.window()["floating"], False, "a set is not idempotent: it toggled")
        self.hypr.dispatch(lua("float", action="unset"))
        self.assertIs(self.hypr.window()["floating"], True,
                      "an unset aimed at a tiled window FLOATS it")
        self.hypr.dispatch(lua("float", action="toggle"))
        self.assertIs(self.hypr.window()["floating"], False)

    def test_unfloating_a_pinned_window_clears_the_pin_by_itself(self):
        self.hypr.dispatch(lua("float", action="toggle"))
        self.hypr.dispatch(lua("pin"))
        self.assertEqual((self.hypr.window()["floating"], self.hypr.window()["pinned"]),
                         (True, True))
        self.hypr.dispatch(lua("float", action="toggle"))
        self.assertEqual((self.hypr.window()["floating"], self.hypr.window()["pinned"]),
                         (False, False))

    def test_the_enter_sequence_lands_on_the_integers_it_asked_for(self):
        # The gate's six steps against the live window, and its recorded
        # result: at [940, 42] size [410, 230] float True pin True, tagged.
        for expression in (lua("float", action="toggle"),
                           lua("resize", x=410, y=230),
                           lua("move", x=940, y=42),
                           lua("pin"),
                           lua("alter_zorder", mode="top"),
                           lua("tag", tag="+iptv-pip")):
            code, out = self.hypr.dispatch(expression)
            self.assertEqual((code, out), (0, "ok"), expression)
        window = self.hypr.window()
        self.assertEqual(window["at"], [940, 42])
        self.assertEqual(window["size"], [410, 230])
        self.assertEqual((window["floating"], window["pinned"]), (True, True))
        self.assertEqual(window["tags"], ["default-opacity*", "iptv-pip"])
        # And the foreign client of the same class is untouched (PLY-RST-11).
        self.assertEqual(self.hypr.window(FOREIGN), base_state()["clients"][0])

    def test_the_exit_sequence_puts_the_window_back_field_for_field(self):
        opening = json.loads(json.dumps(self.hypr.window()))
        for expression in (lua("float", action="toggle"), lua("resize", x=410, y=230),
                           lua("move", x=940, y=42), lua("pin"),
                           lua("tag", tag="+iptv-pip")):
            self.assertEqual(self.hypr.dispatch(expression), (0, "ok"), expression)
        # Mid-way, so a stub that answered nothing at all cannot pass this
        # test by leaving the window exactly as it found it.
        self.assertEqual(self.hypr.window()["at"], [940, 42])
        # The exit the design specifies for a window that was TILED before:
        # untag, unpin, unfloat, and let the layout put the rectangle back.
        # No resize and no move, which is why unpin must come first.
        for expression in (lua("tag", tag="-iptv-pip"), lua("pin"),
                           lua("float", action="toggle")):
            self.assertEqual(self.hypr.dispatch(expression), (0, "ok"), expression)
        self.assertEqual(self.hypr.window(), opening)

    def test_a_dispatched_tag_carries_no_asterisk_and_a_rule_tag_keeps_one(self):
        # Model.pipFindWindow strips a trailing `*` for exactly this reason:
        # a rule-applied tag reads back as `default-opacity*`, a dispatched
        # one does not (G-11).
        self.hypr.dispatch(lua("tag", tag="+iptv-pip"))
        tags = self.hypr.window()["tags"]
        self.assertIn("default-opacity*", tags)
        self.assertIn("iptv-pip", tags)
        self.assertNotIn("iptv-pip*", tags)

    def test_no_spelling_of_the_legacy_dispatcher_parses_under_a_lua_provider(self):
        # G-1, the headline gate result: `hyprctl dispatch` wraps its argument
        # as `return hl.dispatch(<arg>)`, so the legacy name is a Lua SYNTAX
        # error. Both spellings, including the comma one the design told lanes
        # to copy.
        for raw in ("tagwindow +iptv-probe2 address:" + ADDRESS,
                    'tagwindow "+iptv-probe3,address:%s"' % ADDRESS):
            code, out = self.hypr.dispatch(raw)
            self.assertEqual(code, 7, raw)
            self.assertIn("expected", out)
        self.assertEqual(self.hypr.window()["tags"], ["default-opacity*"])

    def test_a_legacy_command_quoted_as_a_string_is_refused_too(self):
        code, out = self.hypr.dispatch('"focuswindow class:zz-nonexistent"')
        self.assertEqual(code, 7)
        self.assertIn("expected a dispatcher", out)

    def test_there_is_no_hl_dsp_window_focus(self):
        # The namespace correction the PIP8 fix depends on.
        code, out = self.hypr.dispatch('hl.dsp.window.focus({ window = "class:omarchy-iptv" })')
        self.assertEqual(code, 7)
        self.assertIn("nil value", out)
        code, out = self.hypr.dispatch('hl.dsp.focus({ window = "class:omarchy-iptv" })')
        self.assertEqual((code, out), (0, "ok"))
        code, out = self.hypr.dispatch('hl.dsp.focus({ window = "class:zz-nonexistent" })')
        self.assertEqual(code, 0, "even a miss is exit status 0")
        self.assertIn("window not found", out)

    def test_the_legacy_builder_has_somewhere_to_run(self):
        # The comma spelling, on the hyprlang provider it ships for. This is
        # what keeps Model.pipLegacyDispatch from being untested code.
        hypr = StubDriver(provider="hyprlang")
        self.addCleanup(hypr.close)
        self.assertIn("configProvider: hyprlang", hypr.run("systeminfo")[1])
        # Argv items, exactly as Model.pipLegacyDispatch emits them: the
        # dispatcher name and its argument are two separate items, and the
        # selector is joined to the geometry by a COMMA.
        hypr.run("dispatch", "togglefloating", "address:" + ADDRESS)
        hypr.run("dispatch", "resizewindowpixel", "exact 410 230,address:" + ADDRESS)
        hypr.run("dispatch", "movewindowpixel", "exact 940 42,address:" + ADDRESS)
        hypr.run("dispatch", "pin", "address:" + ADDRESS)
        hypr.run("dispatch", "tagwindow", "+iptv-pip,address:" + ADDRESS)
        window = hypr.window()
        self.assertEqual((window["at"], window["size"]), ([940, 42], [410, 230]))
        self.assertEqual((window["floating"], window["pinned"]), (True, True))
        self.assertIn("iptv-pip", window["tags"])

    def test_every_invocation_is_recorded_with_its_argv(self):
        # The scenario asserts on these: the address in every vector, and that
        # nothing playlist-derived appears in any of them.
        self.hypr.run("-j", "clients")
        self.hypr.dispatch(lua("tag", tag="+iptv-pip"))
        calls = self.hypr.calls()
        self.assertEqual(calls[0]["argv"], ["-j", "clients"])
        self.assertEqual(calls[1]["rc"], 0)
        self.assertIn(ADDRESS, calls[1]["argv"][1])
        for call in calls:
            self.assertNotIn("://", json.dumps(call["argv"]))


class ServiceShapeTest(unittest.TestCase):
    """The rulings, as properties of Service.qml that a refactor must keep."""

    def test_the_window_is_resolved_by_class_and_by_the_player_pid(self):
        # Never by class alone: a user's own mpv --wayland-app-id=omarchy-iptv
        # reproduces as a second client, and floating, shrinking and pinning a
        # stranger's window is damage rather than a nuisance.
        self.assertIn("root.pipFindWindow(text, root.playerPid, root.pipClass)", SERVICE)
        self.assertIn('reason: "ambiguous"', SERVICE)
        self.assertIn("if (!root.playing || root.playerPid <= 0)", SERVICE)
        self.assertIn('if (Math.floor(Number(c.pid) || 0) !== want) continue', SERVICE)

    def test_success_is_decided_by_a_readback_and_by_nothing_else(self):
        # PIP11. The dispatch handler must hand its exit status to a function
        # that only logs it; the verdict comes from pipVerify against a fresh
        # `hyprctl -j clients`.
        handler = re.search(r"Connections \{\s*target: hyprDispatchProc(.*?)\n  \}",
                            SERVICE, re.S)
        self.assertIsNotNone(handler, "the dispatch Connections block moved or vanished")
        body = handler.group(1)
        self.assertIn("root.pipNoteStep(", body)
        self.assertNotIn("exitCode ===", body)
        self.assertNotIn("exitCode !==", body)
        # And the one place that declares victory reads the verdict.
        victory = re.search(r"function pipCheck\(live\) \{(.*?)\n  \}", SERVICE, re.S)
        self.assertIsNotNone(victory)
        self.assertIn("root.pipVerify(live,", victory.group(1))
        self.assertIn("root.pipFinish(true", victory.group(1))

    def test_the_only_pipFinish_true_outside_pipCheck_is_the_nothing_to_undo_case(self):
        # A second "it worked" that did not go through a readback is exactly
        # the regression PIP11 forbids, so the count is pinned.
        self.assertEqual(SERVICE.count("root.pipFinish(true"), 2)

    def test_no_float_or_pin_step_is_issued_blind(self):
        # PIP10. Both conditionals must read `live`, and the two words that
        # would signal a blind instruction must appear nowhere in the tree.
        self.assertIn('if (live.floating !== true) steps.push(root.pipDispatch("float"', SERVICE)
        self.assertIn('if (live.pinned !== true) steps.push(root.pipDispatch("pin"', SERVICE)
        self.assertNotIn('action = "set"', SERVICE)
        self.assertNotIn('action = "unset"', SERVICE)

    def test_unpin_comes_before_unfloat_on_the_way_out(self):
        exit_plan = SERVICE[SERVICE.index('if (intent !== "off") return steps'):]
        pin_at = exit_plan.index('root.pipDispatch("pin"')
        float_at = exit_plan.index('root.pipDispatch("float"')
        self.assertLess(pin_at, float_at,
                        "pin applies to floating windows; unfloating first loses the unpin")

    def test_only_an_address_and_integers_can_reach_a_dispatch_string(self):
        # 4.11 and ruling PIP7. The regex is applied when the window is found
        # and applied AGAIN when the string is built, so a later caller cannot
        # route around it, and the tag is a two-value whitelist rather than a
        # pattern that would accept a channel name.
        self.assertEqual(SERVICE.count("/^0x[0-9a-f]{1,16}$/.test("), 2)
        self.assertIn('if (out.tag !== "+iptv-pip" && out.tag !== "-iptv-pip") return null', SERVICE)
        self.assertIn("if (n < -100000 || n > 100000) return null", SERVICE)

    def test_the_snapshot_lives_in_the_player_and_writes_no_file(self):
        # No new file, no state.json schema change, no write outside the
        # plugin's own directories -- in fact no write to disk at all. The
        # snapshot's lifetime is the window's because it lives in the process
        # that owns the window (4.5).
        self.assertIn('"user-data/omarchy-iptv-pip"', SERVICE)
        start = SERVICE.index("// ------------ picture in picture (M2-05)".replace(
            "------------", "------------------------------------------------------------"))
        api = SERVICE[start:SERVICE.index("// Debounced: settings changes", start)]
        self.assertIn("pipWriteMpv", api)
        for forbidden in ("setText(", "stateDir", "cacheDir", "FileView", "runtimeDir"):
            self.assertNotIn(forbidden, api, "PiP writes no file at all")

    def test_every_wait_is_bounded(self):
        # CLAUDE.md "Working in parallel" rule 3. Three independent bounds:
        # rounds, steps per round, and wall clock on a step and on the whole
        # sequence, so pipBusy cannot latch the key out of existence.
        for bound in ("readonly property int pipMaxRounds: 3",
                      "readonly property int pipMaxSteps: 8",
                      "readonly property int pipStepMs: 2 * 1000",
                      "readonly property int pipSequenceMs: 15 * 1000"):
            self.assertIn(bound, SERVICE)
        self.assertIn("id: pipStepWatchdog", SERVICE)
        self.assertIn("id: pipSequenceWatchdog", SERVICE)

    def test_the_verb_and_its_refusals(self):
        self.assertIn("function pip(mode: string): string", SERVICE)
        for code in ("bad_mode", "no_compositor", "nothing_playing", "busy"):
            self.assertIn('code: "%s"' % code, SERVICE)

    def test_no_stand_in_is_called_from_outside_its_marked_block(self):
        # CLAUDE.md "Working in parallel" rule 4: stubbing a dependency to
        # build is fine, leaving one is not, and integration proves it with a
        # grep. This passes BOTH before lane V1 merges (every STANDIN_ name
        # sits inside the marked block) and after (there are none at all), so
        # it never has to be edited to stay true.
        start = "============ STAND-IN-M2-05-V1\n"
        end = "======== end STAND-IN-M2-05-V1"
        if start not in SERVICE:
            self.assertNotIn("STANDIN_", SERVICE)
            return
        outside = SERVICE[:SERVICE.index(start)] + SERVICE[SERVICE.index(end):]
        self.assertNotIn("STANDIN_", outside)
        # And the block really is one contiguous region with both ends on it,
        # so the swap is a deletion rather than a hunt.
        self.assertLess(SERVICE.index(start), SERVICE.index(end))

    def test_the_swap_recipe_is_complete(self):
        # Each stand-in is one line and says which line replaces it, so the
        # merge is mechanical rather than archaeological.
        wrappers = re.findall(r"^  function (\w+)\([^)]*\) \{ return STANDIN_\w+\([^)]*\) \}"
                              r"\s*// -> return Model\.(\w+)\(", SERVICE, re.M)
        if not wrappers:
            self.assertNotIn("STANDIN_", SERVICE)
            return
        for local, modelled in wrappers:
            self.assertEqual(local, modelled)
        self.assertEqual(len(wrappers),
                         len(re.findall(r"^  function \w+\([^)]*\) \{ return STANDIN_", SERVICE, re.M)))


if __name__ == "__main__":
    unittest.main()
