#!/usr/bin/env python3
"""scripts/dev-harness/stub-hyprctl.py -- a stand-in for hyprctl.

WHY THIS EXISTS. Picture in picture (M2-05) is the first feature in this
plugin whose correctness depends on how a program OUTSIDE the plugin answers.
The M2-05-00 gate ran that program against a live compositor and wrote down
what it does; this file is those observations made executable, so the service
half can be driven headless, on any machine, with no display and no window.

CLAUDE.md rule 10 is the whole point: a test double must never be more
forgiving than the real thing. Every behaviour below is one the gate
MEASURED, and tests/test_pip.py drives each of them against the transcript
in docs/QA-RESULTS.md. The four that matter, because building against the
opposite of any of them produces a plugin that passes its own tests and
fails on the desktop:

  1. A dispatch aimed at an address that does not exist answers `ok` with
     exit status 0 and does nothing at all (D-PIP-2). Exit status therefore
     cannot detect failure, anywhere, ever.
  2. A refusal that IS reported arrives as `warning:` text on stdout, also
     with exit status 0 -- `Window does not qualify to be pinned`.
  3. `action = "set"` / `"unset"` is IGNORED. float and pin toggle, and a
     second "set" toggles back off (G-3). Unfloating a pinned window clears
     the pin by itself.
  4. Under a Lua config provider there is NO spelling of the legacy
     dispatcher that parses: `hyprctl dispatch` wraps its argument as
     `return hl.dispatch(<arg>)`, so `tagwindow +x address:0x1` is a Lua
     SYNTAX error, not an unknown-dispatcher error (G-1). And focus lives at
     `hl.dsp.focus`, one level up from `hl.dsp.window.*`, which has no
     `focus` member at all.

Environment:
  STUB_HYPRCTL_STATE     JSON file holding { "clients": [...], "monitors": [...] }.
                         Required. Rewritten in place by every dispatch that
                         has an effect, so a scenario reads state back the
                         way the service does.
  STUB_HYPRCTL_LOG       append one JSON line per invocation: the argv, the
                         exit status and the output. Optional.
  STUB_HYPRCTL_PROVIDER  "lua" (default) or "hyprlang". Selects which
                         spelling parses, so the legacy builder that ships
                         for other people's Hyprlands has somewhere to run.

Not a test double for anything the product ships: it is QA tooling, it never
runs inside the plugin, and it touches no path it was not given.
"""

import json
import os
import re
import sys

WINDOW_VERBS = ("float", "pin", "resize", "move", "tag", "alter_zorder",
                "close", "center", "fullscreen")
# What a window dispatcher can actually change here. Everything else in
# WINDOW_VERBS parses and does nothing, which is also what it does live.
EFFECTIVE = ("float", "pin", "resize", "move", "tag", "alter_zorder")
ADDRESS_RE = re.compile(r"^0x[0-9a-f]{1,16}$")
CALL_RE = re.compile(r"^hl\.dsp\.(window\.)?([a-z_]+)\(\s*\{(?P<body>.*)\}\s*\)$", re.S)
VERSION = ("Hyprland 0.56.2 built from branch v0.56.2 at commit "
           "efb50993780079460b0cbed1363e2166a2de1d9f clean ([gha] Nix: update inputs).")


def state_path() -> str:
    path = os.environ.get("STUB_HYPRCTL_STATE", "")
    if not path:
        sys.stderr.write("stub-hyprctl: STUB_HYPRCTL_STATE is not set\n")
        raise SystemExit(2)
    return path


def load_state() -> dict:
    with open(state_path(), "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_state(state: dict) -> None:
    path = state_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    os.replace(tmp, path)


def record(argv: list, out: str, code: int) -> None:
    path = os.environ.get("STUB_HYPRCTL_LOG", "")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"argv": argv, "rc": code, "out": out}) + "\n")


def finish(argv: list, out: str, code: int) -> "int":
    record(argv, out, code)
    if out:
        sys.stdout.write(out if out.endswith("\n") else out + "\n")
    return code


def lua_fields(body: str) -> dict:
    """The handful of `key = value` pairs a dispatch table can carry. Not a
    Lua parser: it accepts exactly the shapes this plugin builds, which is
    the point -- anything else must not be silently understood."""
    fields = {}
    for key, value in re.findall(r'([a-z_]+)\s*=\s*("(?:[^"\\]*)"|-?\d+)', body):
        fields[key] = value[1:-1] if value.startswith('"') else int(value)
    return fields


def selector(fields: dict) -> str:
    return str(fields.get("window", ""))


def match_window(state: dict, want: str):
    if want.startswith("address:"):
        address = want[len("address:"):]
        if not ADDRESS_RE.match(address):
            return None
        for client in state["clients"]:
            if client.get("address") == address:
                return client
        return None
    if want.startswith("class:"):
        name = want[len("class:"):]
        for client in state["clients"]:
            if client.get("class") == name:
                return client
    return None


def float_window(state: dict, target: dict) -> None:
    """What a TILING compositor does around the float toggle, which is most of
    what makes this fake unforgiving.

    Floating a tiled window hands it a default rectangle of the compositor's
    choosing, not the one the layout had given it: the gate watched
    [690, 38] 650x718 become [404, 127] 960x540. A plan that floated the
    window and forgot to resize and move it would look correct against a fake
    that kept the old rectangle, and would put a full-size window in the
    user's face on a real desktop.

    Unfloating puts the layout's rectangle back, which is why the design's
    exit path does not resize a window that was tiled before PiP -- and why
    the gate's exit comparison came back byte-identical.
    """
    remembered = state.setdefault("_tiled", {})
    address = target["address"]
    if not target["floating"]:
        remembered[address] = {"at": list(target["at"]), "size": list(target["size"])}
        monitor = next((m for m in state["monitors"] if m["id"] == target.get("monitor", 0)),
                       state["monitors"][0])
        width, height = 960, 540
        target["size"] = [width, height]
        target["at"] = [monitor["x"] + (round(monitor["width"] / monitor["scale"]) - width) // 2,
                        monitor["y"] + (round(monitor["height"] / monitor["scale"]) - height) // 2]
        target["floating"] = True
        return
    was = remembered.pop(address, None)
    if was is not None:
        target["at"], target["size"] = was["at"], was["size"]
    target["floating"] = False
    target["pinned"] = False                # unfloating clears the pin by itself


def apply_window(state: dict, verb: str, target, fields: dict) -> str:
    # D-PIP-2: a dispatch at a window that is not there succeeds and does
    # nothing. This `return "ok"` is the single most important line here.
    if target is None:
        return "ok"
    if verb == "float":
        # G-3: the action argument is ignored. It toggles, whatever you ask.
        float_window(state, target)
        return "ok"
    if verb == "pin":
        if not target["floating"]:
            return "warning: =[C]:-1: Window does not qualify to be pinned"
        target["pinned"] = not target["pinned"]
        return "ok"
    if verb == "resize":
        # A tiled window's size belongs to the layout: the dispatcher changes
        # the split ratio instead, which this fake does not model. Leaving the
        # size alone is the unforgiving answer, so a plan that resizes a tiled
        # window fails verification here rather than on someone's desktop.
        if target["floating"]:
            target["size"] = [int(fields.get("x", 0)), int(fields.get("y", 0))]
        return "ok"
    if verb == "move":
        if target["floating"]:
            target["at"] = [int(fields.get("x", 0)), int(fields.get("y", 0))]
        return "ok"
    if verb == "alter_zorder":
        return "ok"
    tag = str(fields.get("tag", ""))
    if not tag or tag[0] not in "+-":
        return "ok"
    tags = target.setdefault("tags", [])
    if tag[0] == "+" and tag[1:] not in tags:
        tags.append(tag[1:])
    if tag[0] == "-" and tag[1:] in tags:
        tags.remove(tag[1:])
    return "ok"


def dispatch_lua(argv: list, raw: str) -> int:
    trimmed = raw.strip()
    if trimmed.startswith('"'):
        # A legacy command passed as a quoted STRING parses as Lua and is
        # then refused by hl.dispatch itself. Still exit status 7.
        return finish(argv, "error: return hl.dispatch(%s):1: hl.dispatch: expected a "
                            "dispatcher (e.g. hl.dsp.window.close())" % trimmed, 7)
    call = CALL_RE.match(trimmed)
    if not call:
        # The legacy spelling, either way round. `hyprctl dispatch` wraps its
        # argument as `return hl.dispatch(<arg>)`, so a bare dispatcher name
        # is a Lua syntax error (G-1).
        tokens = trimmed.split()
        near = tokens[1] if len(tokens) > 1 else trimmed
        return finish(argv, 'error: [string "return hl.dispatch(%s..."]:1: '
                            "')' expected near '%s'" % (trimmed[:40], near.split(",")[-1]), 7)
    scoped, verb, body = call.group(1), call.group(2), call.group("body")
    state = load_state()
    fields = lua_fields(body)
    if scoped:
        if verb not in WINDOW_VERBS:
            # There is no hl.dsp.window.focus. The PIP8 fix must use
            # hl.dsp.focus, one level up, and this is what proves it.
            return finish(argv, "error: [string \"return hl.dispatch(...)\"]:1: attempt to "
                                "call a nil value (field '%s')" % verb, 7)
        out = apply_window(state, verb, match_window(state, selector(fields)), fields)
        if verb in EFFECTIVE:
            save_state(state)
        return finish(argv, out, 0)
    if verb != "focus":
        return finish(argv, "error: [string \"return hl.dispatch(...)\"]:1: attempt to "
                            "call a nil value (field '%s')" % verb, 7)
    target = match_window(state, selector(fields))
    if target is None:
        return finish(argv, "warning: =[C]:-1: hl.focus: window not found", 0)
    # WHICH window focus reached. A fake that only answered `ok` could not
    # tell the D-PIP-5 defect from its fix, because both answer ok -- that is
    # ruling PIP11 applied to focus, and it is exactly the forgiveness
    # CLAUDE.md rule 10 forbids. `match_window` resolves a class to the FIRST
    # client carrying it and cannot do better: a class names an app id, not a
    # window. That is how the live pass met it, with a user's own
    # `mpv --wayland-app-id=omarchy-iptv` open and focus landing on the
    # stranger three times out of three.
    state["focused"] = str(target.get("address", ""))
    save_state(state)
    return finish(argv, "ok", 0)


LEGACY = {
    "togglefloating": "float",
    "pin": "pin",
    "resizewindowpixel": "resize",
    "movewindowpixel": "move",
    "alterzorder": "alter_zorder",
    "tagwindow": "tag",
}


def dispatch_legacy(argv: list, args: list) -> int:
    if not args:
        return finish(argv, "Invalid dispatcher", 1)
    verb = LEGACY.get(args[0])
    if verb is None:
        return finish(argv, "Invalid dispatcher", 1)
    rest = " ".join(args[1:])
    fields = {}
    if verb in ("resize", "move"):
        shape = re.match(r"^exact (-?\d+) (-?\d+),(.*)$", rest)
        if not shape:
            return finish(argv, "Invalid dispatcher arg", 1)
        fields = {"x": int(shape.group(1)), "y": int(shape.group(2)), "window": shape.group(3)}
    elif verb == "alter_zorder":
        shape = re.match(r"^top,(.*)$", rest)
        if not shape:
            return finish(argv, "Invalid dispatcher arg", 1)
        fields = {"window": shape.group(1)}
    elif verb == "tag":
        shape = re.match(r"^([+-][A-Za-z0-9_-]+),(.*)$", rest)
        if not shape:
            return finish(argv, "Invalid dispatcher arg", 1)
        fields = {"tag": shape.group(1), "window": shape.group(2)}
    else:
        fields = {"window": rest}
    state = load_state()
    out = apply_window(state, verb, match_window(state, selector(fields)), fields)
    save_state(state)
    return finish(argv, out, 0)


def main(argv: list) -> int:
    args = list(argv)
    if args and args[0] in ("-j", "--json"):
        args = args[1:]
    if not args:
        return finish(argv, "usage: hyprctl [-j] <command>", 1)
    command, rest = args[0], args[1:]
    provider = os.environ.get("STUB_HYPRCTL_PROVIDER", "lua")
    if command == "systeminfo":
        # `configProvider` is reported HERE and nowhere else: it is absent
        # from `hyprctl -j version`, which is where a lane would look first.
        return finish(argv, VERSION + "\nconfigProvider: " + provider, 0)
    if command in ("clients", "monitors"):
        # `_tiled` is this fake's bookkeeping, not a field hyprctl reports:
        # it never reaches the JSON the service parses.
        return finish(argv, json.dumps(load_state()[command], indent=2), 0)
    if command != "dispatch":
        return finish(argv, "Invalid command", 1)
    if provider == "lua":
        return dispatch_lua(argv, " ".join(rest))
    return dispatch_legacy(argv, rest)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
