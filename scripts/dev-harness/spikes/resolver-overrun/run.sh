#!/usr/bin/env bash
# D-SRC-62: how long a host-name lookup holds a fetch past its deadline.
#
# FetchDeadline (bin/helper/03-io-playlist.py) raises from a SIGALRM
# handler, which ends every wait the interpreter is in -- but glibc's
# getaddrinfo retries its own poll after a signal and returns to the
# interpreter only on the resolver's own timeout, so the handler runs
# THEN. This rig measures that overrun on this machine, with no network and
# no root, and nothing exhausted: a resolver that never answers is one UDP
# socket that reads and drops.
#
# The rig: `unshare -rnm` (a user namespace with its own network and mount
# namespaces, unprivileged), `lo` up, a UDP sink on 127.0.0.1:53 that never
# answers, a resolv.conf naming it bind-mounted over /etc/resolv.conf, and
# -- the part a resolv.conf alone cannot do on this machine -- an
# nsswitch.conf with `hosts: files dns` bind-mounted over /etc/nsswitch.conf,
# because the host's has `resolve` before `dns` and nss-resolve would reach
# systemd-resolved over its unix socket and answer from the host's network
# inside the namespace (the round's refuter, 2026-10-24). Nothing outside
# the namespace is touched; the mounts die with it.
#
# Usage: run.sh <helper> [label]      (writes nothing but stdout)
# Each case runs the shipping helper as a subprocess with
# OMARCHY_IPTV_HTTP_DEADLINE=0.5 (a lever that can only LOWER the budget)
# against a name no resolver answers, and reports the wall time against the
# 0.5 s the deadline promised, beside a bare getaddrinfo under the same
# resolver settings as the control.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
HELPER=$(realpath "${1:?helper path}")
LABEL=${2:-$(git -C "$HERE" rev-parse --short HEAD 2>/dev/null || echo unknown)}
exec unshare -rnm --propagation private python3 -I "$HERE/inner.py" "$HELPER" "$LABEL"
