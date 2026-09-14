#!/bin/bash
# Regenerate the local media this fixture serves. Needs ffmpeg.
#   test.ts   900 s  - long enough that nothing ends during a test
#   short.ts    3 s  - ends on its own, for PO-4's clean `eof`
set -euo pipefail
cd "$(dirname "$0")"
gen() {
  local out=$1 secs=$2
  [[ -s $out ]] && { echo "$out exists"; return; }
  ffmpeg -loglevel error -y -f lavfi -i "testsrc=size=320x240:rate=15" \
    -f lavfi -i "sine=frequency=440:sample_rate=22050" \
    -t "$secs" -c:v libx264 -preset ultrafast -pix_fmt yuv420p \
    -c:a aac -b:a 32k -f mpegts "$out"
  echo "$out written"
}
gen test.ts 900
gen short.ts 3

# The sentinel channel's URL carries a token in its path; serve the same media there.
mkdir -p live/qa-token-XYZ && cp -f test.ts live/qa-token-XYZ/stream.ts
echo "live/qa-token-XYZ/stream.ts written"
