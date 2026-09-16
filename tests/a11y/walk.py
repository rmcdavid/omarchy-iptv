"""Start a hermetic AT-SPI bus, run a QML file under it, walk the real tree.

No global setting is touched: the bridge is forced for this one child with
AT_SPI_BUS_ADDRESS, and the bus it points at is a private dbus-daemon this
script starts and kills. Everything is killed by pid, never by pattern.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbusmin
import atspi
import settle

HERE = os.path.dirname(os.path.abspath(__file__))
BUS_CONF = os.path.join(HERE, "bus.conf")
BUDGET_S = 30.0

# Lane 2: the last run's settle report and child-log path, so a caller using
# the original run(qml, import_path, out_json) signature can still read them.
LAST = {}


def start_private_bus():
    open(BUS_CONF, "w").write(
        '<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"\n'
        ' "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">\n'
        "<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>\n"
        '<policy context="default"><allow send_destination="*" eavesdrop="true"/>'
        '<allow eavesdrop="true"/><allow own="*"/></policy></busconfig>\n')
    p = subprocess.Popen(["/usr/bin/dbus-daemon", "--config-file", BUS_CONF,
                          "--print-address", "--nofork"], stdout=subprocess.PIPE)
    return p, p.stdout.readline().decode().strip()


def wait_for_marker(log_path, marker, budget_s=10.0, gap_s=0.15):
    """Bounded wait for a line the probe prints about itself.

    Returns (found, polls, elapsed_s). Never loops without a deadline, and
    the caller is expected to say so when it comes back False.
    """
    t0 = time.time()
    deadline = t0 + budget_s
    polls = 0
    while time.time() < deadline:
        polls += 1
        try:
            with open(log_path, "rb") as fh:
                data = fh.read().decode("utf-8", "replace")
        except OSError:
            data = ""
        if marker in data:
            return True, polls, time.time() - t0
        time.sleep(gap_s)
    return False, polls, time.time() - t0


def run(qmlfile, import_path, out_json=None, log_path=None, wait_for=None):
    bus_proc, addr = start_private_bus()
    app = None
    nodes = []
    # Lane 2: the child's output goes to a FILE, not to a pipe nobody reads.
    # An unread PIPE is a 64K bomb -- the 10,000-channel scenario plus Qt's
    # own warnings can fill it, and the probe then blocks forever on write
    # while the harness waits for a tree that will never finish building.
    # A file also lets an assertion read what the widget printed about
    # itself, which is how a bus claim gets paired with a state claim.
    if log_path is None:
        log_path = os.path.join(HERE, "probe_child.log")
    log = open(log_path, "wb")
    LAST.clear()
    LAST["log_path"] = log_path
    try:
        env = dict(os.environ)
        env["QT_FORCE_STDERR_LOGGING"] = "1"
        env["QML_XHR_ALLOW_FILE_READ"] = "1"
        env["QT_QPA_PLATFORM"] = "wayland"
        env["AT_SPI_BUS_ADDRESS"] = addr
        env.pop("QT_LINUX_ACCESSIBILITY_ALWAYS_ON", None)
        cmd = ["/usr/lib/qt6/bin/qml"]
        if import_path:
            cmd += ["-I", import_path]
        cmd.append(qmlfile)
        app = subprocess.Popen(cmd, env=env, stdout=log,
                               stderr=subprocess.STDOUT)
        bus = dbusmin.Bus(addr)
        conn = None
        deadline = time.time() + BUDGET_S
        polls = 0
        while time.time() < deadline:
            polls += 1
            if app.poll() is not None:
                print("QML EXITED EARLY rc=%s" % app.returncode)
                break
            conn = atspi.find_qt_connection(bus, app.pid)
            if conn:
                break
            time.sleep(0.5)
        if not conn:
            print("GAVE UP after %d polls / %.0fs: no Qt connection for pid %d"
                  % (polls, BUDGET_S, app.pid))
            return None
        # If the probe promises to print a marker when its own state has
        # stopped moving, wait for it BEFORE reading the tree -- bounded,
        # and loud when it does not arrive.
        if wait_for:
            found, polls, secs = wait_for_marker(log_path, wait_for)
            LAST["marker"] = {"marker": wait_for, "found": found,
                              "polls": polls, "elapsed_s": secs}
            if not found:
                print("GAVE UP waiting for marker %r after %d polls / %.1fs"
                      % (wait_for, polls, secs))

        # The guide builds its delegates asynchronously. Lane 2: this was a
        # fixed 1.5s sleep. It is now a bounded stability poll -- walk until
        # two consecutive walks agree, with a deadline and a poll cap, and
        # say so out loud when it gives up.
        nodes, report = settle.settled_walk(bus, conn["name"])
        LAST["settle"] = report
        if report["settled"]:
            print("Qt connection %s, %d nodes, settled after %d walks in %.2fs"
                  % (conn["name"], len(nodes), report["polls"], report["elapsed_s"]))
        else:
            print("GAVE UP waiting for the tree to settle: %s "
                  "(%d walks, %.2fs, %d nodes at the end). Grading it anyway, "
                  "but the scenario is NOT trustworthy."
                  % (report["gave_up_reason"], report["polls"],
                     report["elapsed_s"], len(nodes)))
        bus.close()
        if out_json:
            open(out_json, "w").write(json.dumps(nodes, indent=1))
        return nodes
    finally:
        for p in (app, bus_proc):
            if p is not None and p.poll() is None:
                p.kill()          # by pid, never by pattern
                p.wait(timeout=10)
        log.close()


if __name__ == "__main__":
    qmlfile = sys.argv[1]
    imp = sys.argv[2] if len(sys.argv) > 2 else None
    out = sys.argv[3] if len(sys.argv) > 3 else None
    ns = run(qmlfile, imp, out)
    if ns:
        print(atspi.render(ns))
