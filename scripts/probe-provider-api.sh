#!/bin/bash
# scripts/probe-provider-api.sh -- ask your provider whether it has a metadata
# API, and report ONLY what it offers.
#
# WHY THIS EXISTS. Every stream address in an Xtream-style subscription has the
# shape https://<host>/<username>/<password>/<stream id>. Providers using that
# layout usually also answer at /player_api.php, and that endpoint reports, per
# channel: a channel number, a logo, a real category, an archive (catch-up)
# flag, and a STREAM ID that does not change when you rotate your password.
#
# That one answer would resolve or reframe five separate items on this
# project's backlog. It is worth one request to find out.
#
# WHY YOU RUN IT AND NOT US. The request carries your subscription credentials.
# They go to your own provider and nowhere else -- this script contacts exactly
# the host already in your playlist file and no other -- but no agent on this
# team will send your credentials anywhere, so this is yours to run or refuse.
#
# WHAT IT PRINTS. Whether the endpoint answered, and which useful fields came
# back, as counts. It NEVER prints your username, your password, any URL, or
# the response body. You can paste its entire output anywhere safely.
#
# Usage:  ./scripts/probe-provider-api.sh <path-to-one-of-your-m3u-files>
set -uo pipefail

FILE=${1:-}
if [[ -z $FILE || ! -f $FILE ]]; then
  echo "usage: $0 <path-to-an-m3u-file-from-your-provider>" >&2
  exit 2
fi

read -r HOST USER_SEG PASS_SEG < <(python3 - "$FILE" <<'PY'
import io, sys
from urllib.parse import urlparse
for line in io.open(sys.argv[1], encoding='utf-8', errors='replace'):
    line = line.strip()
    if not line.startswith('http'):
        continue
    u = urlparse(line)
    parts = [p for p in u.path.split('/') if p]
    if len(parts) >= 3:
        print(u.scheme + '://' + u.netloc, parts[0], parts[1])
    break
PY
)

if [[ -z ${HOST:-} || -z ${USER_SEG:-} || -z ${PASS_SEG:-} ]]; then
  echo "This file's stream addresses are not in the /user/pass/id shape, so"
  echo "there is no Xtream-style API to ask. Nothing to do."
  exit 1
fi

echo "Asking your provider (host taken from the playlist file, nothing typed)."
echo "Nothing below will contain your credentials."
echo

python3 - "$HOST" "$USER_SEG" "$PASS_SEG" <<'PY'
import json, ssl, sys, urllib.parse, urllib.request

host, user, pw = sys.argv[1], sys.argv[2], sys.argv[3]
ctx = ssl.create_default_context()


def ask(params, label):
    """Return (status, content-type, body) or None. Prints nothing sensitive.

    A bare player_api.php call returns user_info, which on most panels ECHOES
    THE USERNAME AND PASSWORD BACK in its values. So nothing here ever prints a
    VALUE from the response -- only status, type, length, and KEY NAMES.
    """
    q = urllib.parse.urlencode(dict(params, username=user, password=pw))
    try:
        with urllib.request.urlopen(host + "/player_api.php?" + q,
                                    timeout=20, context=ctx) as r:
            return r.status, (r.headers.get("Content-Type") or "?"), r.read(8 * 1024 * 1024)
    except Exception as exc:
        print("%-22s no answer (%s)" % (label, type(exc).__name__))
        return None


def classify(body):
    head = body[:400].lstrip()
    if not body:
        return "EMPTY (zero bytes)"
    low = head.lower()
    if low.startswith(b"<!doctype") or low.startswith(b"<html"):
        return "an HTML page, so this path is a web server and not an API"
    if head[:1] in (b"{", b"["):
        return "JSON"
    return "neither JSON nor HTML"


print("%-22s %s" % ("request", "result"))
print("")
results = {}
for label, params in (("bare (user_info)", {}),
                      ("get_live_streams", {"action": "get_live_streams"}),
                      ("get_live_categories", {"action": "get_live_categories"})):
    got = ask(params, label)
    if not got:
        continue
    status, ctype, raw = got
    results[label] = raw
    print("%-22s HTTP %s, %s, %d bytes -- %s"
          % (label, status, ctype.split(";")[0], len(raw), classify(raw)))

print("")
usable = None
for label, raw in results.items():
    try:
        data = json.loads(raw)
    except ValueError:
        continue
    usable = (label, data)
    break

if usable is None:
    print("VERDICT: no usable API. Every response was empty, HTML, or")
    print("unparseable, so there is nothing here to build on. That is a clean")
    print("negative and three backlog items stay correctly closed.")
    raise SystemExit(0)

label, data = usable
print("VERDICT: %s returned JSON." % label)
if isinstance(data, dict):
    print("top-level keys: %s" % ", ".join(sorted(data.keys())))
    for k in ("user_info", "server_info"):
        if isinstance(data.get(k), dict):
            print("  %s keys: %s" % (k, ", ".join(sorted(data[k].keys()))))
    raise SystemExit(0)

if not isinstance(data, list) or not data:
    print("...but it is not a stream list. Treat as a negative.")
    raise SystemExit(0)

n = len(data)
print("streams reported: %d" % n)
print("")


def count(field):
    return sum(1 for s in data if isinstance(s, dict) and s.get(field) not in (None, "", 0, "0"))


FIELDS = [
    ("stream_id", "a stable id that survives a password change"),
    ("num", "a channel number"),
    ("stream_icon", "a logo"),
    ("category_id", "a real category"),
    ("tv_archive", "catch-up available"),
    ("epg_channel_id", "guide data identifier"),
]
print("%-22s %-9s %s" % ("field", "present", "what it would give us"))
for f, meaning in FIELDS:
    print("%-22s %-9s %s" % (f, "%d/%d" % (count(f), n), meaning))
print("")
print("distinct categories offered: %d"
      % len({s.get("category_id") for s in data if isinstance(s, dict)}))
print("")
print("Paste this whole output back; it contains no credentials and no URLs.")
PY
