#!/usr/bin/env python3
"""scripts/check-mpv-options.py -- every mpv option is a decision (D-SINK-43..46).

The owner's decision of 2026-10-29: the player keeps a user's mpvArgs and
their mpv.conf, PINS on the launch argv every option a security layer depends
on, RESERVES the names that undo a layer, and CLASSIFIES every option the
installed mpv offers, so that an option nobody has thought about is a red
gate rather than a default. tests/fixtures/mpv-options.json is that
classification; both mirrors' MPV_RESERVED and the trailing pin block are
pinned to it by the unit tests. This script holds it against the mpv that is
actually installed:

  RED   an option base `mpv --list-options` prints that the fixture does not
        classify -- a new mpv option, which is a decision for a person
  RED   an option whose type or alias target is not what the fixture says,
        because the classification was made for the old shape
  RED   a fixture entry that breaks the fixture's own rules: a class that is
        not one of the five, a string-shaped or [file] option with no `why`,
        an alias whose class is not its target's
  NOTE  an option the fixture names that this mpv lacks (an older build, a
        different configure) -- reported, never red

and, when the ffmpeg CLI is installed, FFmpeg's own TLS protocol options
(`ffmpeg -h protocol=tls`), because a key in `--demuxer-lavf-o` configures
the TLS protocol of every HLS segment open (D-SINK-43) and the helper's
read-back judges those keys by name: an option FFmpeg adds there is RED until
it is classified, and every key the fixture forbids or pins must contain one
of the words the token filter refuses (MPV_DEMUXER_TLS_WORDS), so the two
layers cover the same keys.

mpv runs WINDOWLESS and touches nothing of the user's: `--no-config`, no
DISPLAY / WAYLAND_DISPLAY / DBUS_SESSION_BUS_ADDRESS, HOME and every XDG
directory in a temporary directory removed afterwards, RLIMIT_CORE 0, a 30 s
timeout. `--list-options` opens no file and no window.

Exit 0 green, 1 red, 77 when mpv is not installed (scripts/check.sh turns 77
red unless MPV_OPTIONS_SKIP_OK=1, the LOGO_PREFLIGHT_SKIP_OK shape).
`--listing FILE` and `--ffmpeg-listing FILE` read saved output instead of
running the programs (the unit tests use them). Stdlib only, ASCII only.
"""
from __future__ import annotations

import json
import os
import re
import resource
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "mpv-options.json")
CLASSES = ("allowed", "reserved", "pinned", "warned", "base")
STRINGY = ("String", "String list", "Key/value list", "Object settings list", "alias", "removed", "Print")
FFMPEG_CLASSES = ("allowed", "forbidden", "pinned")
LIST_SUFFIX = re.compile(r"-(add|append|set|pre|clr|del|remove|toggle)$")


def parse_listing(text: str) -> dict[str, dict[str, str]]:
    """`mpv --list-options` -> {"--name": {"type": ..., "alias": ...}}. The
    shape the fixture records: the type word(s) before the first parenthesis
    or bracket, `Choices` for a choice, `alias` with its target."""
    out: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        m = re.match(r"^ --(\S+)\s+(.*?)\s*$", line)
        if not m:
            continue
        name, desc = "--" + m.group(1), m.group(2)
        a = re.match(r"^alias(?: \[deprecated\])? for (\S+)", desc)
        if a:
            target = a.group(1)
            out[name] = {"type": "alias", "alias": target if target.startswith("--") else "--" + target}
        elif desc.startswith("removed"):
            out[name] = {"type": "removed"}
        elif desc.startswith("Choices:"):
            out[name] = {"type": "Choices"}
        else:
            out[name] = {"type": re.split(r" \(| \[", desc)[0].strip()}
        if "[file]" in desc:
            out[name]["file"] = "1"
    return out


def parse_ffmpeg_tls(text: str) -> list[str]:
    names = []
    inside = False
    for line in text.splitlines():
        if line.startswith("tls AVOptions"):
            inside = True
            continue
        if inside:
            m = re.match(r"^\s+-(\w+)\s", line)
            if m:
                names.append(m.group(1))
            elif line.strip() and not line.startswith(" "):
                inside = False
    return names


def clean_env(home: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if k not in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "HYPRLAND_INSTANCE_SIGNATURE",
                        "MPV_HOME", "XDG_CONFIG_DIRS")}
    for key, sub in (("HOME", "home"), ("XDG_CONFIG_HOME", "config"), ("XDG_CACHE_HOME", "cache"),
                     ("XDG_STATE_HOME", "state"), ("XDG_DATA_HOME", "data"), ("XDG_RUNTIME_DIR", "run")):
        path = os.path.join(home, sub)
        os.makedirs(path, mode=0o700, exist_ok=True)
        env[key] = path
    return env


def no_core() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run_listing(argv: list[str]) -> str:
    home = tempfile.mkdtemp(prefix="mpv-options-")
    try:
        done = subprocess.run(argv, env=clean_env(home), cwd=home, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=30, preexec_fn=no_core)
        return done.stdout
    finally:
        shutil.rmtree(home, ignore_errors=True)


def fixture_problems(fixture: dict) -> list[str]:
    out = []
    options = fixture.get("options") or {}
    for name, entry in options.items():
        klass = entry.get("class")
        if klass not in CLASSES:
            out.append("%s: class %r is not one of %s" % (name, klass, ", ".join(CLASSES)))
        if (entry.get("type") in STRINGY or entry.get("file")) and not entry.get("why"):
            out.append("%s: a %s option needs a one-line `why`" % (name, entry.get("type")))
        if entry.get("type") == "alias":
            target = options.get(LIST_SUFFIX.sub("", entry.get("alias", "")))
            if target is None:
                out.append("%s: alias of %s, which the fixture does not name" % (name, entry.get("alias")))
            elif target.get("class") != klass:
                out.append("%s: alias of %s but classified %s, not %s" % (name, entry.get("alias"), klass, target.get("class")))
        if klass == "pinned" and entry.get("type") != "alias" and not entry.get("pin"):
            out.append("%s: pinned with no `pin` token" % name)
    tls = fixture.get("ffmpegTls") or {}
    words = tls.get("words") or []
    for key, klass in (tls.get("options") or {}).items():
        if klass not in FFMPEG_CLASSES:
            out.append("ffmpeg tls %s: class %r is not one of %s" % (key, klass, ", ".join(FFMPEG_CLASSES)))
        elif klass != "allowed" and not any(word in key for word in words):
            out.append("ffmpeg tls %s: %s, but the token filter's words (%s) do not catch it" % (key, klass, ", ".join(words)))
    return out


def main(argv: list[str]) -> int:
    args = {"--listing": None, "--ffmpeg-listing": None, "--mpv": "mpv", "--ffmpeg": "ffmpeg", "--fixture": FIXTURE}
    i = 0
    while i < len(argv):
        if argv[i] not in args or i + 1 >= len(argv):
            print("usage: check-mpv-options.py [--mpv PATH | --listing FILE] [--ffmpeg PATH | --ffmpeg-listing FILE] [--fixture FILE]")
            return 2
        args[argv[i]] = argv[i + 1]
        i += 2
    with open(args["--fixture"], encoding="utf-8") as fh:
        fixture = json.load(fh)
    red = fixture_problems(fixture)
    if args["--listing"]:
        with open(args["--listing"], encoding="utf-8") as fh:
            listing = fh.read()
        source = args["--listing"]
    else:
        mpv = shutil.which(args["--mpv"])
        if not mpv:
            print("SKIP mpv option guard: no mpv on PATH, so nothing was classified")
            return 77
        listing = run_listing([mpv, "--no-config", "--list-options"])
        source = mpv
    live = parse_listing(listing)
    if not live:
        red.append("%s printed no option at all" % source)
    options = fixture.get("options") or {}
    for name in sorted(set(live) - set(options)):
        red.append("%s: not classified (%s) -- add it to tests/fixtures/mpv-options.json with a class and a why" % (name, live[name]["type"]))
    for name in sorted(set(live) & set(options)):
        want, got = options[name], live[name]
        if want.get("type") != got["type"]:
            red.append("%s: the fixture says %s, this mpv says %s -- re-classify it" % (name, want.get("type"), got["type"]))
        if got["type"] == "alias" and want.get("alias") != got.get("alias"):
            red.append("%s: an alias of %s here, the fixture says %s" % (name, got.get("alias"), want.get("alias")))
    missing = sorted(set(options) - set(live))
    if args["--ffmpeg-listing"]:
        with open(args["--ffmpeg-listing"], encoding="utf-8") as fh:
            ff_text = fh.read()
    else:
        ffmpeg = shutil.which(args["--ffmpeg"])
        ff_text = run_listing([ffmpeg, "-hide_banner", "-h", "protocol=tls"]) if ffmpeg else None
    ff_note = ""
    if ff_text is None:
        ff_note = "; ffmpeg not installed, FFmpeg's TLS keys not checked"
    else:
        keys = parse_ffmpeg_tls(ff_text)
        known = (fixture.get("ffmpegTls") or {}).get("options") or {}
        if not keys:
            red.append("ffmpeg -h protocol=tls listed no option")
        for key in keys:
            if key not in known:
                red.append("ffmpeg tls %s: not classified -- a --demuxer-lavf-o key reaches it for every HLS segment" % key)
        ff_note = "; %d FFmpeg TLS keys classified" % len([k for k in keys if k in known])
    counts = {klass: 0 for klass in CLASSES}
    for name in live:
        klass = (options.get(name) or {}).get("class")
        if klass in counts:
            counts[klass] += 1
    for line in red:
        print("RED  " + line)
    if missing:
        print("NOTE the fixture names %d option(s) this mpv lacks: %s" % (len(missing), " ".join(missing)))
    print("mpv option guard: %d options classified (%s) against %s%s"
          % (sum(counts.values()), ", ".join("%s %d" % (k, counts[k]) for k in CLASSES),
             (fixture.get("mpv") or {}).get("version", "?"), ff_note))
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
