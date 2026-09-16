"""Lane 2: a bounded stability poll, replacing the prototype's fixed sleep.

walk.py used `time.sleep(1.5)` before reading the tree. A fixed sleep is
wrong in both directions: too short and the harness grades a half-built
tree, too long and every scenario pays for the slowest one. Worse, it is
silent -- a scenario that needed 1.6s would fail with no hint that timing
was the reason.

This walks the tree repeatedly and stops when two consecutive walks agree.
It is bounded by a deadline AND a poll count, and when it runs out it says
so and hands back what it had, with `settled` false, so the caller can fail
the scenario instead of quietly grading an unfinished tree.
"""
import time

import atspi


def signature(nodes):
    """Everything an assertion can read. If none of it changed between two
    walks, nothing an assertion can see is still moving."""
    return tuple(
        (n["depth"], n["role"], n["name"], n.get("description"),
         n.get("text"), tuple(n.get("state_names", [])))
        for n in nodes
    )


def settled_walk(bus, dest, budget_s=12.0, max_polls=40, gap_s=0.20,
                 agreements=2):
    """Walk until the tree stops changing. Returns (nodes, report).

    `agreements` is how many CONSECUTIVE identical walks are required. Two
    (three identical walks) rather than one, because a single agreement can
    be two reads of a tree that has not started building yet -- which would
    hand the checker an empty tree and call it settled. Each extra agreement
    costs one gap.

    report: dict(settled, polls, elapsed_s, gave_up_reason, node_count)
    """
    t0 = time.time()
    deadline = t0 + budget_s
    previous = None
    nodes = []
    polls = 0
    stable = 0
    reason = ""
    while True:
        if polls >= max_polls:
            reason = "poll cap %d reached" % max_polls
            break
        if time.time() > deadline:
            reason = "budget %.1fs exhausted" % budget_s
            break
        polls += 1
        nodes = atspi.walk(bus, dest)
        sig = signature(nodes)
        stable = stable + 1 if (previous is not None and sig == previous) else 0
        if stable >= agreements:
            return nodes, {"settled": True, "polls": polls,
                           "elapsed_s": time.time() - t0, "gave_up_reason": "",
                           "node_count": len(nodes)}
        previous = sig
        time.sleep(gap_s)
    # Honest give-up: say it, and hand back the last tree anyway so the
    # caller can report WHAT it saw as well as that it never stopped moving.
    return nodes, {"settled": False, "polls": polls,
                   "elapsed_s": time.time() - t0,
                   "gave_up_reason": reason, "node_count": len(nodes)}
