import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbusmin, atspi

cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bus.conf")
open(cfg, "w").write("""<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <listen>unix:tmpdir=/tmp</listen>
  <policy context="default">
    <allow send_destination="*" eavesdrop="true"/>
    <allow eavesdrop="true"/>
    <allow own="*"/>
  </policy>
</busconfig>
""")
bus_proc = subprocess.Popen(["/usr/bin/dbus-daemon", "--config-file", cfg,
                             "--print-address", "--nofork"],
                            stdout=subprocess.PIPE)
addr = bus_proc.stdout.readline().decode().strip()
print("private bus: %s (pid %d)" % (addr, bus_proc.pid))

qml_proc = None
try:
    env = dict(os.environ)
    env["QT_FORCE_STDERR_LOGGING"] = "1"
    env["QT_QPA_PLATFORM"] = "wayland"
    env["AT_SPI_BUS_ADDRESS"] = addr
    env.pop("QT_LINUX_ACCESSIBILITY_ALWAYS_ON", None)
    qml_proc = subprocess.Popen(["/usr/lib/qt6/bin/qml", sys.argv[1]], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print("probe pid %d" % qml_proc.pid)
    bus = dbusmin.Bus(addr)
    conn = None
    deadline = time.time() + 20.0
    tries = 0
    while time.time() < deadline:
        tries += 1
        if qml_proc.poll() is not None:
            print("PROBE EXITED rc=%s" % qml_proc.returncode)
            break
        conn = atspi.find_qt_connection(bus, qml_proc.pid)
        if conn:
            break
        time.sleep(0.5)
    if not conn:
        print("GAVE UP after %d polls: no Qt connection on the private bus" % tries)
    else:
        print("Qt connection %s after %d polls" % (conn["name"], tries))
        nodes = atspi.walk(bus, conn["name"])
        print(atspi.render(nodes))
        print("NODE COUNT %d" % len(nodes))
    bus.close()
finally:
    for p in (qml_proc, bus_proc):
        if p is not None and p.poll() is None:
            p.kill()            # by pid
            p.wait(timeout=10)
