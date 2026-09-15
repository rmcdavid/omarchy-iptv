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

SECOND, the shape those two rulings force on the code. `Model.pipVerify`
against a fresh read is the only definition of success, and no float or pin
step may be issued without a live read behind it. Both are structural
properties, and a structural property with nothing asserting it is one
refactor away from gone.

Where a rule lives decides which file is read here. Integration moved the
pure half out of Service.qml and into Model.js, where node and the QML spec
call it for real (CLAUDE.md 12), so the decisions are asserted against
Model.js and what is asserted against Service.qml is that it DELEGATES: it
holds no compositor expression, no address pattern and no plan of its own.

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
MODEL = (ROOT / "Model.js").read_text(encoding="utf-8")
GUIDE = (ROOT / "Guide.qml").read_text(encoding="utf-8")

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

    def test_a_class_selector_cannot_say_which_of_two_windows_it_means(self):
        # D-PIP-5, with the state that produces it: PLY-RST-11's reproduced
        # case, a user's own `mpv --wayland-app-id=omarchy-iptv`, listed
        # first. Both commands below answer `ok` with exit status 0, so the
        # reply cannot tell them apart -- which is why the stub now records
        # WHICH window focus reached, and why a double that did not would be
        # more forgiving than the compositor (CLAUDE.md rule 10).
        state = base_state()
        state["clients"].insert(0, {
            "class": "omarchy-iptv", "pid": 2053730, "address": "0x559c687e0bb0",
            "at": [0, 0], "size": [800, 600], "floating": False, "pinned": False,
            "monitor": 0, "workspace": {"id": 1}, "tags": [],
        })
        hypr = StubDriver(state=state)
        self.addCleanup(hypr.close)
        code, out = hypr.dispatch('hl.dsp.focus({ window = "class:omarchy-iptv" })')
        self.assertEqual((code, out), (0, "ok"))
        self.assertEqual(self.focused(hypr), "0x559c687e0bb0",
                         "a class names an app id, not a window: the stranger got the focus")
        # The address the pid resolved reaches ours, and nothing else does.
        code, out = hypr.dispatch('hl.dsp.focus({ window = "address:%s" })' % ADDRESS)
        self.assertEqual((code, out), (0, "ok"))
        self.assertEqual(self.focused(hypr), ADDRESS)

    def focused(self, hypr):
        with open(hypr.state_path, "r", encoding="utf-8") as handle:
            return json.load(handle).get("focused", "")

    def test_the_lua_spelling_is_the_only_one_that_exists_here(self):
        # PIP15. The legacy spelling works on a hyprlang provider and is a
        # Lua syntax error on this one, so there is exactly one spelling to
        # build and the provider decides whether we can speak at all. The
        # stub still models the hyprlang side, because that is what makes
        # "the other form is not a fallback, it is another compositor" a
        # fact this suite can point at rather than a claim.
        hypr = StubDriver(provider="hyprlang")
        self.addCleanup(hypr.close)
        self.assertIn("configProvider: hyprlang", hypr.run("systeminfo")[1])
        hypr.run("dispatch", "togglefloating", "address:" + ADDRESS)
        hypr.run("dispatch", "resizewindowpixel", "exact 410 230,address:" + ADDRESS)
        hypr.run("dispatch", "movewindowpixel", "exact 940 42,address:" + ADDRESS)
        hypr.run("dispatch", "pin", "address:" + ADDRESS)
        hypr.run("dispatch", "tagwindow", "+iptv-pip,address:" + ADDRESS)
        window = hypr.window()
        self.assertEqual((window["at"], window["size"]), ([940, 42], [410, 230]))
        self.assertEqual((window["floating"], window["pinned"]), (True, True))
        self.assertIn("iptv-pip", window["tags"])
        # And the same argv on the Lua provider does nothing at all, which is
        # why shipping it as a fallback would have been a second failure
        # dressed as safety.
        lua = StubDriver(provider="lua")
        self.addCleanup(lua.close)
        code, out = lua.run("dispatch", "togglefloating", "address:" + ADDRESS)
        self.assertEqual(code, 7, out)
        self.assertIs(lua.window()["floating"], False)

    def test_the_stub_understands_exactly_what_model_js_builds(self):
        # CLAUDE.md: a rule written twice gets one fixture that both
        # implementations run. Model.js builds these expressions and this
        # stub parses them - one grammar, two languages, two lanes - and
        # before tests/fixtures/pip-dispatch.json nothing compared the two:
        # this suite drove the fake with strings written by hand HERE, and
        # tests/Model.test.js asserted the builder against strings written by
        # hand THERE. Both could be green with the halves unable to speak.
        #
        # So the vectors below are not written here at all. They are the ones
        # tests/Model.test.js asserts pipPlan emits, replayed verbatim, with
        # the leading "hyprctl" dropped because this file IS hyprctl.
        fixture = json.loads((ROOT / "tests" / "fixtures" / "pip-dispatch.json")
                             .read_text(encoding="utf-8"))
        hypr = StubDriver(state={"clients": [fixture["window"]],
                                 "monitors": [fixture["monitor"]]})
        self.addCleanup(hypr.close)
        address = fixture["address"]
        for leg in ("enter", "exit"):
            for argv in fixture[leg]["argv"]:
                self.assertEqual(argv[0], "hyprctl", argv)
                code, out = hypr.run(*argv[1:])
                # `ok` and nothing else: a grammar the fake did not recognise
                # answers with a Lua error here, exactly as the compositor
                # does, rather than being silently ignored.
                self.assertEqual((code, out), (0, "ok"), argv[2])
            window = hypr.window(address)
            after = fixture[leg]["after"]
            self.assertEqual(window["at"], after["at"], leg)
            self.assertEqual(window["size"], after["size"], leg)
            self.assertIs(window["floating"], after["floating"], leg)
            self.assertIs(window["pinned"], after["pinned"], leg)
            self.assertEqual(window["tags"], after["tags"], leg)

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
    """The rulings, as properties of the tree that a refactor must keep.

    Integration moved every decision into Model.js, so a rule is asserted
    against the file that now owns it. What is asserted against Service.qml
    is delegation: the decisions it must not make for itself.
    """

    def has(self, haystack, needle, label):
        # assertIn on a 180 KB file prints the file. Say where and what.
        self.assertTrue(needle in haystack, "%s: %s" % (label, needle))

    def lacks(self, haystack, needle, label):
        self.assertFalse(needle in haystack, "%s: %s" % (label, needle))

    def test_the_window_is_resolved_by_class_and_by_the_player_pid(self):
        # Never by class alone: a user's own mpv --wayland-app-id=omarchy-iptv
        # reproduces as a second client, and floating, shrinking and pinning a
        # stranger's window is damage rather than a nuisance.
        self.has(SERVICE, "Model.pipFindWindow(text, root.playerPid, root.pipClass)", "Service.qml")
        self.has(SERVICE, "playing: root.playing && root.playerPid > 0", "Service.qml")
        # The narrowing itself, where a node test can call it.
        self.has(MODEL, "if (pipInteger(c.pid, -1) !== want) continue", "Model.js")
        self.has(MODEL, 'if (hits.length > 1) return pipWindowFail("ambiguous")', "Model.js")

    def test_focus_is_narrowed_by_the_pid_like_every_other_window_command(self):
        # D-PIP-5. The D-PIP-1 repair fixed the spelling and kept the
        # selector, and `class:` names an app id rather than a window: with a
        # user's own `mpv --wayland-app-id=omarchy-iptv` open, focus landed
        # on the stranger three times out of three. 4.2 had already ruled
        # narrowing by pid non-optional for every other verb.
        self.has(SERVICE, "root.dispatchFocus(derived.address)", "Service.qml")
        self.has(SERVICE, "var argv = Model.focusPlayerArgv(address)", "Service.qml")
        self.has(SERVICE, "if (argv.length === 0) return false", "Service.qml")
        self.has(MODEL, "function focusPlayerArgv(address) {", "Model.js")
        self.has(MODEL, '  return pipDispatchArgv("focus", { window: pipAddressSelector(address) })', "Model.js")
        # And the class selector is GONE, not merely unused: the builder
        # cannot produce one for any verb, so no future caller can route back
        # to it. A constant left behind for "compatibility" is how this kind
        # of defect returns.
        self.lacks(MODEL, "PIP_CLASS_SELECTOR", "Model.js must not keep a class selector")
        self.lacks(MODEL, 'if (value === PIP_CLASS_SELECTOR) return value', "Model.js")
        self.lacks(SERVICE, "Model.focusPlayerArgv()", "Service.qml must not focus without an address")

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
        self.assertIn("Model.pipVerify(live, root.pipIntent, expected)", victory.group(1))
        self.assertIn("root.pipFinish(true", victory.group(1))
        # What "asked for" means on each leg: the geometry in, the snapshot
        # out. Passing one where the other belongs would verify the window
        # against the wrong rectangle and call a failure a success.
        self.assertIn('root.pipIntent === "off" ? root.pipSnapshot : root.pipGeom', victory.group(1))

    def test_the_only_pipFinish_true_outside_pipCheck_is_the_nothing_to_undo_case(self):
        # A second "it worked" that did not go through a readback is exactly
        # the regression PIP11 forbids, so the count is pinned.
        self.assertEqual(SERVICE.count("root.pipFinish(true"), 2)

    def test_no_float_or_pin_step_is_issued_blind(self):
        # PIP10. Both conditionals must read the live window, and the two
        # words that would signal a blind instruction appear in no source
        # file in the tree.
        self.has(MODEL, 'if (l.floating !== true) steps.push(pipDispatchArgv("float"', "Model.js")
        self.has(MODEL, 'if (l.pinned !== true) steps.push(pipDispatchArgv("pin"', "Model.js")
        for source in (MODEL, SERVICE, GUIDE):
            self.assertNotIn('action = "set"', source)
            self.assertNotIn('action = "unset"', source)

    def test_unpin_comes_before_unfloat_on_the_way_out(self):
        exit_plan = MODEL[MODEL.index("var snap = pipParseSnapshot(snapshot)"):]
        pin_at = exit_plan.index('pipDispatchArgv("pin"')
        float_at = exit_plan.index('pipDispatchArgv("float"')
        self.assertLess(pin_at, float_at,
                        "pin applies to floating windows; unfloating first loses the unpin")

    def test_only_an_address_and_integers_can_reach_a_dispatch_string(self):
        # 4.11 and ruling PIP7. The pattern is applied when the window is
        # found and applied AGAIN when the string is built, so a later caller
        # cannot route around it; the tag is a whitelist of two literals
        # rather than a pattern that would accept a channel name; and the
        # expression is re-checked as a whole before it leaves the builder.
        self.has(MODEL, 'if (pipAddressSelector(address) === "") return pipWindowFail("bad_address")', "Model.js")
        self.has(MODEL, '  tag: ["+" + PIP_TAG, "-" + PIP_TAG]', "Model.js")
        self.has(MODEL, "  if (value < -PIP_COORD_LIMIT || value > PIP_COORD_LIMIT) return null", "Model.js")
        self.has(MODEL, '  return PIP_EXPR_RE.test(expr) ? expr : ""', "Model.js")

    def test_the_service_builds_no_compositor_expression_of_its_own(self):
        # The strongest form of "one implementation": after integration the
        # service holds no expression, no address pattern, no tag literal and
        # no window-state parsing at all. Every one of those was a local copy
        # of a Model.js rule while the two lanes were separate, and a copy
        # that agrees today is a copy that can disagree tomorrow.
        # Needles that cannot appear in prose: a quoted literal or a call.
        # (Both files still NAME these things in comments, which is the
        # documentation this test exists to keep honest.)
        for forbidden in ("hl.dsp.", "/^0x", '"user-data/', '"iptv-pip"', "JSON.parse("):
            self.lacks(SERVICE, forbidden, "Service.qml must not carry this rule")
        self.has(SERVICE, "readonly property string pipClass: Model.PIP_CLASS", "Service.qml")
        self.has(SERVICE, "readonly property string pipTag: Model.PIP_TAG", "Service.qml")
        self.has(SERVICE, "Model.PIP_SNAPSHOT_KEY", "Service.qml")

    def test_there_is_no_fallback_spelling(self):
        # PIP15. One question to the compositor, one answer, one builder. A
        # second arm could not be reached (rc cannot report a refusal) and
        # would not work if it were (the other form is a syntax error here),
        # so it must not exist to read like safety.
        self.has(SERVICE,
                 'root.pipProvider = /configProvider:\\s*lua/i.test(String(hyprInfoStdout.text)) ? "lua" : "other"',
                 "Service.qml")
        self.has(SERVICE, 'root.pipAvailable = exitCode === 0 && root.pipProvider === "lua"', "Service.qml")
        # As argv items, which is the only way a legacy spelling could ship.
        # Model.js's comment still explains why the form is a syntax error
        # here; what must not exist is a builder that emits one.
        for forbidden in ('"tagwindow"', '"togglefloating"', '"resizewindowpixel"',
                          '"movewindowpixel"', '"alterzorder"', '"pin"]', "pipLegacyDispatch"):
            self.lacks(SERVICE, forbidden, "no legacy spelling ships")
            self.lacks(MODEL, forbidden, "no legacy spelling ships")

    def test_the_snapshot_lives_in_the_player_and_writes_no_file(self):
        # No new file, no state.json schema change, no write outside the
        # plugin's own directories -- in fact no write to disk at all. The
        # snapshot's lifetime is the window's because it lives in the process
        # that owns the window (4.5).
        self.has(MODEL, 'var PIP_SNAPSHOT_KEY = "user-data/omarchy-iptv-pip"', "Model.js")
        start = SERVICE.index("// ------------ picture in picture (M2-05)".replace(
            "------------", "------------------------------------------------------------"))
        api = SERVICE[start:SERVICE.index("// Debounced: settings changes", start)]
        self.assertIn("pipWriteMpv", api)
        for forbidden in ("setText(", "stateDir", "cacheDir", "FileView", "runtimeDir"):
            self.assertNotIn(forbidden, api, "PiP writes no file at all")

    def test_the_reported_state_is_re_derived_when_a_player_becomes_ours(self):
        # D-PIP-4 and design 4.7 step 3. The window half already worked: a
        # request re-reads the compositor before it plans, so `p` exited
        # correctly after `omarchy restart shell`. What was missing is the
        # same read taken ONCE when a player becomes ours, which is why
        # `status.pip.on` answered false on thirty consecutive samples with
        # the box demonstrably in the corner.
        #
        # Two hooks, because the pid can arrive either way round: the
        # reattach probe learns it before the socket is armed, and a cold
        # start learns it from the player's own reply afterwards.
        self.has(SERVICE, "    root.pipPeek()\n  }\n\n  // ---- what picture in picture IS", "Service.qml")
        attach = SERVICE[SERVICE.index("function onPlayerAttached(sock)"):]
        attach = attach[:attach.index("\n  }")]
        self.assertIn("root.pipPeek()", attach,
                      "onPlayerAttached must re-derive the state (4.7 step 3)")
        self.assertIn("root.pipRequestSnapshot(sock)", attach,
                      "and still read back what the window WAS (4.5)")
        # The read itself, and the two decisions behind it, are the model's.
        self.has(SERVICE, "Model.pipDeriveGate({ pid: root.playerPid, busy: root.pipBusy, reading: root.pipPeeking })",
                 "Service.qml")
        self.has(SERVICE, "var derived = Model.pipDeriveState(text, root.playerPid, root.pipClass)", "Service.qml")
        self.has(SERVICE, "if (derived.decided && !root.pipBusy) root.pipOn = derived.on", "Service.qml")
        self.has(MODEL, "function pipDeriveState(clients, pid, className) {", "Model.js")

    def test_nothing_reports_picture_in_picture_from_memory(self):
        # The defect in one property of the tree: every value `pipOn` can
        # take comes from a live read of the compositor or from clearing it
        # outright. There is no cached boolean, no last-known-good and no
        # "what we asked for" anywhere on the right-hand side -- which is
        # what makes the state survive a restart this process was not alive
        # for. `root.pipIntent === "on"` is the one apparent exception and is
        # not one: pipCheck reaches it only after Model.pipVerify has
        # compared a FRESH read field by field (PIP11).
        allowed = {
            "Model.pipActive(live)",
            "Model.pipActive(root.pipLive)",
            'root.pipIntent === "on"',
            "derived.on",
            "false",
        }
        found = set(re.findall(r"root\.pipOn = (.+)$", SERVICE, re.M))
        self.assertTrue(found, "no pipOn assignment found at all: this test has stopped testing")
        self.assertEqual(found - allowed, set(),
                         "pipOn was assigned from something that is not a live read")
        # And the derivation cannot be handed one either: three parameters,
        # all of them facts about the compositor and the player.
        self.assertIn("function pipDeriveState(clients, pid, className) {", MODEL)
        self.assertNotIn("function pipDeriveState(clients, pid, className, ", MODEL)

    def test_every_wait_is_bounded(self):
        # CLAUDE.md "Working in parallel" rule 3. Three independent bounds:
        # rounds, steps per round, and wall clock on a step and on the whole
        # sequence, so pipBusy cannot latch the key out of existence.
        for bound in ("readonly property int pipMaxRounds: 3",
                      "readonly property int pipMaxSteps: 8",
                      "readonly property int pipStepMs: 2 * 1000",
                      "readonly property int pipSequenceMs: 15 * 1000"):
            self.has(SERVICE, bound, "Service.qml")
        self.has(SERVICE, "id: pipStepWatchdog", "Service.qml")
        self.has(SERVICE, "id: pipSequenceWatchdog", "Service.qml")
        # And the read that is not part of a sequence has its own, or an
        # hyprctl that never exits would latch `pipPeeking` and the state
        # would quietly stop being re-derived for the rest of the session.
        self.has(SERVICE, "id: pipPeekWatchdog", "Service.qml")
        self.has(SERVICE, "      if (hyprPeekProc.running) hyprPeekProc.signal(15)", "Service.qml")

    def test_the_verb_and_its_refusals(self):
        self.has(SERVICE, "function pip(mode: string): string", "Service.qml")
        for refusal in ('root.pipRefuse(want, "bad_mode")', 'root.pipRefuse(want, "busy")',
                        "root.pipRefuse(want, gate.code)"):
            self.has(SERVICE, refusal, "Service.qml")
        # And the two the gate answers are the model's, not a second list.
        self.has(MODEL, 'return { ok: false, code: "no_compositor", text: pipStatusText("no_compositor") }',
                 "Model.js")
        self.has(MODEL, 'return { ok: false, code: "nothing_playing", text: pipStatusText("nothing_playing") }',
                 "Model.js")

    def test_no_stand_in_survives_anywhere(self):
        # CLAUDE.md "Working in parallel" rule 4: stubbing a dependency to
        # build is fine, leaving one is not, and integration proves it with a
        # grep. This is that grep, run over every file a stand-in could hide
        # in rather than over the one it was known to be in.
        for name in ("Service.qml", "Guide.qml", "BarWidget.qml", "Model.js"):
            text = (ROOT / name).read_text(encoding="utf-8")
            for marker in ("STANDIN_", "STAND-IN-M2-05-V1"):
                self.lacks(text, marker, "%s still carries a stand-in" % name)

    def test_the_service_calls_the_model_for_every_pip_decision(self):
        # The other half of the stand-in grep: the names are not merely gone,
        # they are gone BECAUSE the real functions are called. A wrapper
        # deleted along with its call site would pass the grep above.
        for call in ("Model.pipFindWindow(", "Model.pipFindMonitor(", "Model.pipGeometry(",
                     "Model.pipOptions(", "Model.pipPlan(", "Model.pipVerify(",
                     "Model.pipActive(", "Model.pipResolveIntent(", "Model.pipSnapshotFor(",
                     "Model.pipParseSnapshot(", "Model.pipMpvCommands(", "Model.pipHasTag(",
                     "Model.pipResultCode(", "Model.pipKeyRequest(", "Model.pipDispatchAccepted(",
                     "Model.pipDeriveState(", "Model.pipDeriveGate(",
                     "Model.parsePlayerReply("):
            self.has(SERVICE, call, "Service.qml must call the shipped function")


class TwoLanesAgreeTest(unittest.TestCase):
    """Where the same rule was implemented on both sides of a lane boundary.

    This project has twice shipped two implementations of one rule that
    quietly disagreed, once where a user could see it. These are the places
    M2-05 could do it again, each reduced to one function or one constant
    and then pinned here.
    """

    def guide_service_handlers(self):
        """Every on<Signal> the guide listens for on the service object."""
        block = re.search(r"Connections \{\s*\n\s*target: root\.service\b(.*?)\n  \}",
                          GUIDE, re.S)
        self.assertIsNotNone(block, "the guide's service Connections block moved")
        return re.findall(r"function on([A-Z]\w*)\(", block.group(1))

    def test_the_guide_listens_for_signals_the_service_actually_emits(self):
        # THE defect this integration found. The guide had `onPipResult` and
        # the service emitted `pipOutcome`; `ignoreUnknownSignals: true` is
        # required there (an older service has neither Sources nor PiP), so
        # the mismatch was not an error, not a warning, and not a failure --
        # the footer was simply wired to a signal nobody emits, and every
        # gate stayed green. A name is a contract between two files; compare
        # them.
        signals = set(re.findall(r"^  signal (\w+)\(", SERVICE, re.M))
        properties = set(re.findall(r"^  (?:readonly )?property \w+ (\w+)", SERVICE, re.M))
        functions = set(re.findall(r"^  function (\w+)\(", SERVICE, re.M))
        handlers = self.guide_service_handlers()
        self.assertIn("PipOutcome", handlers, "the guide stopped listening for the PiP outcome")
        for handler in handlers:
            lower = handler[0].lower() + handler[1:]
            known = (lower in signals
                     or lower in functions
                     or (lower.endswith("Changed") and lower[:-len("Changed")] in properties))
            self.assertTrue(known,
                            "Guide.qml listens for on%s; Service.qml emits no such signal" % handler)

    def test_one_gate_decides_whether_pip_may_start(self):
        # The guide answers the two refusals it can see; the service re-asks
        # with the fact the guide does not have (the player's pid). Both go
        # through Model.pipKeyRequest, so they cannot drift into refusing for
        # different reasons or saying it in different words.
        self.assertIn("Model.pipKeyRequest({", GUIDE)
        self.assertIn("Model.pipKeyRequest({", SERVICE)

    def test_one_definition_of_being_in_picture_in_picture(self):
        # The service's own copy of this predicate required `pinned` as well
        # as the tag; Model.pipActive deliberately does not, because a user
        # who unpins the corner box still owns it and `p` must still put it
        # back. Two answers to "am I in PiP?" is an inverted toggle: the key
        # enters when it should exit.
        self.assertIn("function pipActive(live)", MODEL)
        self.assertEqual(SERVICE.count("Model.pipActive("), 3)
        self.assertNotIn("function pipIsOn", SERVICE)

    def test_one_copy_of_every_line_the_user_reads(self):
        # PIP9 and section 5: the footer lines and the tooltip line live in
        # Model.js and nowhere else. A sentence in Service.qml or Guide.qml
        # is a line no test can compare against the table.
        #
        # Over CODE, not over comments: a comment that quotes a line to
        # explain a failure mode is documentation, and a test that forbids
        # quoting the thing it protects teaches people to write vaguer
        # comments.
        def code_only(text):
            return "\n".join(row for row in text.splitlines()
                             if not row.lstrip().startswith("//"))
        model, service, guide = code_only(MODEL), code_only(SERVICE), code_only(GUIDE)
        for line in ("Picture in picture on", "Picture in picture off", "Nothing playing",
                     "Picture in picture needs Hyprland", "Cannot find the player window",
                     "Hyprland refused the window change", "Picture in picture: on"):
            self.assertEqual(model.count('"%s"' % line), 1, line)
            self.assertNotIn(line, service, "the service never composes a sentence")
            self.assertNotIn(line, guide, "the guide renders Model.pipStatusText, never a literal")

    def test_the_settings_have_one_clamp_behind_them(self):
        # The manifest declares the range the host offers; Model.SETTING_RANGES
        # is what the plugin accepts; tests/Model.test.js asserts the two are
        # equal in both directions. What is asserted here is that there is no
        # THIRD clamp: the service reads the one bar entry through
        # Model.pipOptions rather than clamping for itself.
        self.assertIn("Model.pipOptions(root.pipConfig())", SERVICE)
        self.assertNotIn("pipSizePercent, 15, 60", SERVICE)
        self.assertNotIn("pipMargin, 0, 200", SERVICE)
        self.assertEqual(MODEL.count("pipSizePercent: { def: 30, min: 15, max: 60 }"), 1)
        self.assertEqual(MODEL.count("pipMargin: { def: 16, min: 0, max: 200 }"), 1)


if __name__ == "__main__":
    unittest.main()
