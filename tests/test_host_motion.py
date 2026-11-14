"""D-A11Y-11 (2026-11-14): the plugin's animations run for the host's own
duration, which is 0 while Omarchy's reduce motion is on.

Two joins by name that nothing else calls (rule 13):

1. The host function. BarWidget.qml and Guide.qml hand the theme kit's
   `Style` to Model.motionMs, which asks `Style.duration(ms)`; Omarchy 4.5.0
   defines it in Commons/Style.qml as `reduceMotion ? 0 : ms`. HostMotion
   reads that file on this machine and goes red when a host update renames
   the function, changes what it returns, or drops the property it reads. A
   red here is a re-read request, not a plugin defect: Model.motionMs keeps
   the plugin's own number when the function is missing, so the cost of a
   silent rename is that reduce motion stops reaching the plugin, with no
   error anywhere. The host directory comes from OMARCHY_SHELL_DIR so the
   test can be run against a copy with one thing changed.

2. The shipped animations. ShippedAnimations reads every root-level QML
   file and holds each animation to a duration that is a property of the
   file's root declared as `Model.motionMs(Style, <milliseconds>)`, so an
   animation written later with a literal, or with none (Qt's default is
   250 ms), is refused. What it cannot see: whether the binding re-reads
   when the host's setting changes (tests/Model.spec.qml observes that in
   the engine) and what a real bar draws.
"""
import glob
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOST = os.environ.get("OMARCHY_SHELL_DIR", "/usr/share/omarchy/shell")

ANIMATION_RE = re.compile(r"\b([A-Z][A-Za-z]*(?:Animation|Animator))\s*\{")
DURATION_RE = re.compile(r"\bduration\s*:\s*([^;}\n]+)")
MOTION_PROPERTY_RE = re.compile(
    r"^\s*readonly property int ([A-Za-z][A-Za-z0-9]*): Model\.motionMs\(Style, ([0-9]+)\)\s*$", re.M)


def strip_comments(text):
    """QML with // comments blanked, line for line; strings here hold no //."""
    return "\n".join(line.split("//", 1)[0] for line in text.split("\n"))


def block_after(text, start):
    """The text of the brace block that opens at or after `start`."""
    depth = 0
    opened = text.index("{", start)
    for i in range(opened, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[opened:i + 1]
    raise AssertionError("unclosed block")


def animation_problems(text):
    """Every animation in one QML file that does not run for a motion time."""
    code = strip_comments(text)
    motion = dict(MOTION_PROPERTY_RE.findall(code))
    problems = []
    seen = 0
    for match in ANIMATION_RE.finditer(code):
        seen += 1
        line = code.count("\n", 0, match.start()) + 1
        body = block_after(code, match.start())
        durations = DURATION_RE.findall(body)
        if len(durations) != 1:
            problems.append("line %d: %s declares %d durations" % (line, match.group(1), len(durations)))
            continue
        value = durations[0].strip()
        if not value.startswith("root.") or value[5:] not in motion:
            problems.append("line %d: %s runs for `%s`, not a root property declared as Model.motionMs(Style, N)"
                            % (line, match.group(1), value))
    return seen, motion, problems


class ShippedAnimations(unittest.TestCase):
    def files(self):
        found = sorted(glob.glob(os.path.join(ROOT, "*.qml")))
        self.assertEqual([os.path.basename(p) for p in found], ["BarWidget.qml", "Guide.qml", "Service.qml"])
        return found

    def test_every_animation_runs_for_a_motion_time(self):
        total = 0
        for path in self.files():
            with open(path, encoding="utf-8") as handle:
                seen, _motion, problems = animation_problems(handle.read())
            self.assertEqual(problems, [], os.path.basename(path))
            total += seen
        # The seven the board row counted (the bar label at three sites, the
        # glyph colour, the banner's two fades, the Sources row's tint): a
        # reader that finds none would pass everything.
        self.assertEqual(total, 7)

    def test_the_motion_times_are_the_documented_ones(self):
        times = {}
        for path in self.files():
            with open(path, encoding="utf-8") as handle:
                times.update(animation_problems(handle.read())[1])
        self.assertEqual(times, {"labelAnimMs": "180", "glyphAnimMs": "160", "bannerFadeMs": "140", "rowTintMs": "60"})

    def test_the_reader_refuses_a_literal_a_missing_and_a_foreign_duration(self):
        good = ("Item {\n  id: root\n  readonly property int fadeMs: Model.motionMs(Style, 140)\n"
                "  Behavior on opacity { NumberAnimation { duration: root.fadeMs; easing.type: Easing.OutCubic } }\n}\n")
        self.assertEqual(animation_problems(good)[2], [])
        self.assertEqual(len(animation_problems(good.replace("root.fadeMs", "140"))[2]), 1)
        self.assertEqual(len(animation_problems(good.replace("duration: root.fadeMs; ", ""))[2]), 1)
        self.assertEqual(len(animation_problems(good.replace("root.fadeMs", "root.otherMs"))[2]), 1)
        self.assertEqual(len(animation_problems(good.replace("Model.motionMs(Style, 140)", "140"))[2]), 1)
        self.assertEqual(len(animation_problems(good.replace("NumberAnimation", "OpacityAnimator"))[2]), 0)
        self.assertEqual(animation_problems(good.replace("NumberAnimation", "OpacityAnimator"))[0], 1)
        commented = good.replace("  Behavior", "  // ColorAnimation { duration: 60 }\n  Behavior")
        self.assertEqual(animation_problems(commented)[0], 1)


class HostMotion(unittest.TestCase):
    def setUp(self):
        if not os.path.isdir(HOST):
            self.skipTest("no Omarchy shell under %s; the host contract cannot be checked here" % HOST)
        with open(os.path.join(HOST, "Commons", "Style.qml"), encoding="utf-8") as handle:
            self.style = strip_comments(handle.read())

    def test_the_host_declares_reduce_motion(self):
        self.assertRegex(self.style, r"(?m)^\s*property bool reduceMotion: false\s*$")

    def test_the_host_duration_is_zero_under_reduce_motion_and_the_number_otherwise(self):
        found = re.findall(r"(?m)^\s*function duration\(ms\)\s*\{", self.style)
        self.assertEqual(len(found), 1, "Style.duration(ms): %d definitions" % len(found))
        body = block_after(self.style, self.style.index("function duration(ms)"))
        self.assertEqual(" ".join(body.split()), "{ return reduceMotion ? 0 : ms }")


if __name__ == "__main__":
    unittest.main()
