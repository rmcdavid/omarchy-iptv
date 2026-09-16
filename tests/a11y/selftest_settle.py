"""Two-sided proof that the stability poll is not decoration.

The poll replaced a fixed sleep. A poll that always answers "settled" is
worse than the sleep it replaced, because it looks like evidence. So:

  restless.qml  a tree whose accessible name changes every 40 ms. The poll
                MUST exhaust its bound and report that it gave up.
  barhost.qml   a tree that stops. The poll MUST settle, and fast.

`check_lane2._scenario` asserts on the same `settled` field this reads, as
L2-RUN-<scenario>, so a scenario graded mid-build fails instead of passing
quietly.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import walk as walker

HERE = os.path.dirname(os.path.abspath(__file__))
# The generated tree is a BUILD ARTIFACT, not source: it holds a copy of the
# host UI kit and a transformed copy of Guide.qml, both regenerated on every
# run. It must not land inside the repo, and it must not be shared between
# concurrent runs -- a shared directory written by two lanes at once already
# produced one reading that was green only because a mutation had been
# overwritten. Override with A11Y_TREE when you want to keep one to inspect.
TREE = os.environ.get("A11Y_TREE") or os.path.join(
    os.environ.get("TMPDIR", "/tmp"), "omarchy-iptv-a11y-tree")

failures = []


def expect(ok, label, detail):
    print("  %s  %s" % ("pass" if ok else "FAIL", label))
    print("        %s" % detail)
    if not ok:
        failures.append(label)


def main():
    print("settle poll self-test")

    walker.run(os.path.join(HERE, "restless.qml"), None, None,
               log_path=os.path.join(HERE, "restless.log"))
    r = walker.LAST.get("settle") or {}
    expect(r.get("settled") is False,
           "a tree that never stops changing is reported as NOT settled",
           "polls=%s elapsed=%.2fs reason=%r"
           % (r.get("polls"), r.get("elapsed_s", 0), r.get("gave_up_reason")))
    expect(bool(r.get("gave_up_reason")),
           "and it says why it gave up rather than looping on",
           "reason=%r" % r.get("gave_up_reason"))

    open(os.path.join(TREE, "barscenario.txt"), "w").write("idle\n")
    walker.run(os.path.join(TREE, "barhost.qml"), TREE, None,
               log_path=os.path.join(HERE, "selftest_bar.log"),
               wait_for="BAR_HOST_READY")
    r = walker.LAST.get("settle") or {}
    expect(r.get("settled") is True,
           "a tree that stops is reported as settled",
           "polls=%s elapsed=%.2fs nodes=%s"
           % (r.get("polls"), r.get("elapsed_s", 0), r.get("node_count")))
    expect(r.get("elapsed_s", 99) < 1.5,
           "and it costs less than the fixed 1.5s sleep it replaced",
           "elapsed=%.2fs" % r.get("elapsed_s", 0))

    # The marker wait has the same obligation: bounded, and honest when the
    # thing it waits for never arrives. check_lane2 asserts on this field as
    # L2-MARK-<scenario>.
    walker.run(os.path.join(TREE, "barhost.qml"), TREE, None,
               log_path=os.path.join(HERE, "selftest_marker.log"),
               wait_for="A_MARKER_NOTHING_EVER_PRINTS")
    m = walker.LAST.get("marker") or {}
    expect(m.get("found") is False,
           "a marker that never arrives is reported as not found",
           "polls=%s elapsed=%.2fs" % (m.get("polls"), m.get("elapsed_s", 0)))
    expect(m.get("elapsed_s", 0) < 20,
           "and the wait is bounded rather than open-ended",
           "gave up after %.2fs" % m.get("elapsed_s", 0))

    print("%d failures" % len(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
