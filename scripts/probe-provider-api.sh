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
q = urllib.parse.urlencode({"username": user, "password": pw,
                            "action": "get_live_streams"})
url = host + "/player_api.php?" + q

try:
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(url, timeout=20, context=ctx) as r:
        body = r.read(8 * 1024 * 1024)
        code = r.status
except Exception as exc:
    print("NO ANSWER: %s" % type(exc).__name__)
    print("")
    print("That is a clean negative. The three backlog items that depend on it")
    print("stay correctly closed and nothing is lost.")
    raise SystemExit(0)

print("answered: HTTP %d, %d KB" % (code, len(body) // 1024))
try:
    data = json.loads(body)
except ValueError:
    print("...but the body is not JSON, so there is no usable API here.")
    raise SystemExit(0)

if not isinstance(data, list) or not data:
    print("...but it returned no stream list. Treat as a negative.")
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
    c = count(f)
    print("%-22s %-9s %s" % (f, "%d/%d" % (c, n), meaning))
print("")
cats = {s.get("category_id") for s in data if isinstance(s, dict)}
print("distinct categories offered: %d" % len(cats))
print("")
print("Paste this whole output back; it contains no credentials and no URLs.")
PY
