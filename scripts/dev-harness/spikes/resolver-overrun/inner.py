#!/usr/bin/env python3
"""The inside of run.sh's namespace (D-SRC-62). Runs as the namespace's uid 0.

Cases, each under two resolver settings -- `timeout:1 attempts:1` (the
smallest glibc takes) and glibc's defaults (timeout:5 attempts:2) --
against `nonexistent.example`, which the sink on 127.0.0.1:53 never
answers:
  lookup    a bare socket.getaddrinfo in a fresh python: the resolver's own
            timeout, which is what the fetch waits for today
  playlist  the shipping `playlist` verb with OMARCHY_IPTV_HTTP_DEADLINE=0.5:
            the deadline promised 0.5 s; the overrun is what it took minus that
The sink's pid is the only pid killed, and it is the one this script started.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time

HELPER = sys.argv[1]
LABEL = sys.argv[2]
NAME = "nonexistent.example"
DEADLINE = "0.5"
RUNS = 3


def sh(*argv):
    subprocess.run(argv, check=True)


def main():
    work = tempfile.mkdtemp(prefix="resolver-overrun-")
    sh("ip", "link", "set", "lo", "up")
    nss = os.path.join(work, "nsswitch.conf")
    with open(nss, "w") as handle:
        handle.write("hosts: files dns\n")
    sh("mount", "--bind", nss, "/etc/nsswitch.conf")
    rc = os.path.join(work, "resolv.conf")
    with open(rc, "w") as handle:
        handle.write("nameserver 127.0.0.1\n")
    sh("mount", "--bind", rc, "/etc/resolv.conf")
    sink = subprocess.Popen([sys.executable, "-I", "-c",
                             "import socket\ns=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)\n"
                             "s.bind(('127.0.0.1',53))\n"
                             "while True: s.recvfrom(4096)\n"])
    try:
        time.sleep(0.2)
        cache = os.path.join(work, "cache")
        env = dict(PATH="/usr/bin:/bin", HOME=work, LANG="C.UTF-8", OMARCHY_IPTV_HTTP_DEADLINE=DEADLINE,
                   XDG_CACHE_HOME=cache, XDG_STATE_HOME=os.path.join(work, "state"),
                   XDG_RUNTIME_DIR=os.path.join(work, "run"))
        print("D-SRC-62 resolver overrun, helper %s, %s, deadline %s s, name %s, %d runs a case"
              % (LABEL, time.strftime("%Y-%m-%d %H:%M:%S"), DEADLINE, NAME, RUNS))
        print("nsswitch hosts: files dns; resolv.conf nameserver 127.0.0.1 (a sink that never answers)")
        for options in ("options timeout:1 attempts:1", ""):
            with open(rc, "w") as handle:
                handle.write("nameserver 127.0.0.1\n%s\n" % options)
            print("== resolver %s" % (options or "glibc defaults (timeout:5 attempts:2)"))
            for _ in range(RUNS):
                t0 = time.monotonic()
                proc = subprocess.run([sys.executable, "-I", "-c",
                                       "import socket\ntry: socket.getaddrinfo(%r, 443)\n"
                                       "except OSError as e: print(type(e).__name__)" % NAME],
                                      capture_output=True, text=True, timeout=120)
                print("  lookup    %6.2f s  %s" % (time.monotonic() - t0, proc.stdout.strip()))
            for _ in range(RUNS):
                t0 = time.monotonic()
                proc = subprocess.run([sys.executable, "-B", "-I", HELPER, "playlist", "--url",
                                       "https://%s/list.m3u" % NAME, "--timeout", "10"],
                                      capture_output=True, text=True, timeout=120, env=env)
                took = time.monotonic() - t0
                try:
                    reply = json.loads(proc.stdout.strip().splitlines()[-1])
                    code = (reply.get("error") or {}).get("code")
                except (ValueError, IndexError):
                    code = "no reply"
                print("  playlist  %6.2f s  overrun %+5.2f s  rc=%d code=%s" % (took, took - float(DEADLINE), proc.returncode, code))
    finally:
        sink.kill()
        sink.wait()


if __name__ == "__main__":
    main()
