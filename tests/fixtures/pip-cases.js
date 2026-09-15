// Shared vectors for picture in picture (M2-05 section 10.1).
//
// ONE file, run by both JavaScript engines: node requires it
// (tests/Model.test.js) and the Qt engine imports it as a QML script library
// (tests/Model.spec.qml), the same arrangement chno-cases.js uses and for the
// same reason - a QML TestCase cannot read a local file, and a second copy of
// the vectors in the spec would be the mirrored logic CLAUDE.md 12 forbids.
// No `.pragma library`: node's parser rejects it.
//
// ASCII only.
//
// Why the numbers here are written out rather than computed: this is the only
// place multi-monitor correctness can come from on a single-monitor machine
// (10.5). Every expected box below is derived BY HAND from design 4.4's five
// steps, with the arithmetic in the comment, so the fixture is an independent
// statement of the rule and not a transcript of what pipGeometry happens to
// do. The first one is not even ours: MONITOR_LIVE / GEOMETRY_LIVE is the box
// the gate applied to a real window on this machine and read back
// (docs/QA-RESULTS.md, M2-05-00, "Does the state apply to a window the plugin
// did not spawn?"). Design 4.4 and open question 4 say "(932, 42)"; they are
// wrong by 8 px and the gate says so - 1350 - 410 = 940.

// One entry of `hyprctl -j monitors`. Sizes are PHYSICAL pixels.
var MONITORS = {
  // eDP-1 as this machine actually reports it.
  live: { id: 0, name: "eDP-1", width: 1366, height: 768, scale: 1, transform: 0, x: 0, y: 0, reserved: [0, 26, 0, 0] },
  // A 4K panel at 2x. None of the four below exists here.
  hidpi: { id: 1, name: "DP-1", width: 3840, height: 2160, scale: 2, transform: 0, x: 0, y: 0, reserved: [0, 26, 0, 0] },
  // A fractional scale, where the logical size is not an integer division.
  fractional: { id: 2, name: "DP-2", width: 2560, height: 1440, scale: 1.5, transform: 0, x: 0, y: 0, reserved: [0, 0, 0, 0] },
  // Rotated 90 degrees: an odd transform swaps the axes.
  rotated: { id: 3, name: "DP-3", width: 1920, height: 1080, scale: 1, transform: 1, x: 0, y: 0, reserved: [0, 0, 0, 0] },
  // A second head to the right of and above the first. `move` takes GLOBAL
  // layout coordinates, so x and y must reach the answer.
  offset: { id: 4, name: "HDMI-A-1", width: 1920, height: 1080, scale: 1, transform: 0, x: 1920, y: -360, reserved: [0, 26, 0, 0] },
  // Short enough that a 16:9 box off the width does not fit the height.
  letterbox: { id: 5, name: "DP-4", width: 640, height: 200, scale: 1, transform: 0, x: 0, y: 0, reserved: [0, 0, 0, 0] },
  // Small enough that the percentage lands under the 240 px floor.
  small: { id: 6, name: "DP-5", width: 640, height: 480, scale: 1, transform: 0, x: 0, y: 0, reserved: [0, 0, 0, 0] },
  // A margin bigger than the usable rectangle: no box exists.
  impossible: { id: 7, name: "DP-6", width: 320, height: 240, scale: 1, transform: 0, x: 0, y: 0, reserved: [0, 0, 0, 0] }
}

var GEOMETRY = [
  // lw 1366 lh 768; x0 16 y0 42 x1 1350 y1 752
  // w round(1366*30/100) = 410; h round(410*9/16) = 231 -> even 230
  { why: "the live monitor, defaults, top-right: the box the gate applied and read back",
    monitor: "live", opts: { corner: "top-right", sizePercent: 30, margin: 16 }, box: { x: 940, y: 42, w: 410, h: 230 } },
  { why: "the same box in the other three corners",
    monitor: "live", opts: { corner: "top-left", sizePercent: 30, margin: 16 }, box: { x: 16, y: 42, w: 410, h: 230 } },
  { why: "bottom-right sits h above the usable bottom",
    monitor: "live", opts: { corner: "bottom-right", sizePercent: 30, margin: 16 }, box: { x: 940, y: 522, w: 410, h: 230 } },
  { why: "bottom-left likewise",
    monitor: "live", opts: { corner: "bottom-left", sizePercent: 30, margin: 16 }, box: { x: 16, y: 522, w: 410, h: 230 } },
  // scale 2: lw 1920 lh 1080; x0 16 y0 42 x1 1904 y1 1064
  // w round(1920*30/100) = 576; h round(576*9/16) = 324
  { why: "a 2x monitor: the box is computed in LOGICAL pixels, so it is half what the physical size would give",
    monitor: "hidpi", opts: { corner: "top-right", sizePercent: 30, margin: 16 }, box: { x: 1328, y: 42, w: 576, h: 324 } },
  // scale 1.5: lw round(2560/1.5) = 1707, lh 960; x0 20 y0 20 x1 1687 y1 940
  // w round(1707*40/100) = 683; h round(683*9/16) = 384; even -> 682 x 384
  { why: "a 1.5x monitor, where the logical size is not an integer division",
    monitor: "fractional", opts: { corner: "bottom-right", sizePercent: 40, margin: 20 }, box: { x: 1005, y: 556, w: 682, h: 384 } },
  // transform 1: lw 1080 lh 1920; x0 0 y0 0
  // w round(1080*30/100) = 324; h round(324*9/16) = 182
  { why: "transform 1 swaps the axes, so the width comes off the SHORT side",
    monitor: "rotated", opts: { corner: "top-left", sizePercent: 30, margin: 0 }, box: { x: 0, y: 0, w: 324, h: 182 } },
  // x 1920 y -360: x0 1930 y0 -324 x1 3830 y1 710
  // w round(1920*25/100) = 480; h 270; bottom-left -> (1930, 710-270)
  { why: "a monitor at a non-zero, negative-y origin: the answer is in global layout coordinates",
    monitor: "offset", opts: { corner: "bottom-left", sizePercent: 25, margin: 10 }, box: { x: 1930, y: 440, w: 480, h: 270 } },
  // lw 640 lh 200; w round(640*60/100) = 384; h 216 > 200, so h = 200 and
  // w = round(200*16/9) = 356
  { why: "a monitor so short the 16:9 box must shrink to fit the height",
    monitor: "letterbox", opts: { corner: "top-right", sizePercent: 60, margin: 0 }, box: { x: 284, y: 0, w: 356, h: 200 } },
  // w round(640*15/100) = 96, under the 240 floor; h round(240*9/16) = 135 -> 134
  { why: "a percentage under the 240 px floor is raised to it",
    monitor: "small", opts: { corner: "top-left", sizePercent: 15, margin: 0 }, box: { x: 0, y: 0, w: 240, h: 134 } },
  // x0 200 x1 120: the usable rectangle is inside out
  { why: "a margin larger than the monitor has no box at all, and must not invent one",
    monitor: "impossible", opts: { corner: "top-left", sizePercent: 30, margin: 200 }, box: null }
]

// `hyprctl -j clients` entries. The live one is the player window the gate
// drove, address and pid included.
var PLAYER_PID = 1937373
var PLAYER_ADDRESS = "0x559c6893d940"
var CLIENTS = {
  tiled: { "class": "omarchy-iptv", pid: PLAYER_PID, address: PLAYER_ADDRESS, at: [690, 38], size: [650, 718], floating: false, pinned: false, monitor: 0, workspace: { id: 1 }, tags: ["default-opacity*"] },
  inPip: { "class": "omarchy-iptv", pid: PLAYER_PID, address: PLAYER_ADDRESS, at: [940, 42], size: [410, 230], floating: true, pinned: true, monitor: 0, workspace: { id: 1 }, tags: ["default-opacity*", "iptv-pip"] },
  // The user's own SUPER+O: floating and pinned, and NOT ours - no tag.
  userPopped: { "class": "omarchy-iptv", pid: PLAYER_PID, address: PLAYER_ADDRESS, at: [300, 300], size: [900, 500], floating: true, pinned: true, monitor: 0, workspace: { id: 1 }, tags: ["default-opacity*"] },
  // PLY-RST-11 reproduced: a user's own mpv --wayland-app-id=omarchy-iptv.
  foreign: { "class": "omarchy-iptv", pid: 424242, address: "0x559c687e09a0", at: [0, 0], size: [800, 600], floating: false, pinned: false, monitor: 0, workspace: { id: 1 }, tags: [] },
  otherApp: { "class": "com.anthropic.Claude", pid: 999, address: "0x559c687e0aa0", at: [12, 38], size: [1342, 718], floating: false, pinned: false, monitor: 0, workspace: { id: 1 }, tags: ["default-opacity*"] },
  // Same class, same pid, two windows: PiP refuses rather than guessing.
  twin: { "class": "omarchy-iptv", pid: PLAYER_PID, address: "0x559c6893d941", at: [0, 0], size: [10, 10], floating: false, pinned: false, monitor: 0, workspace: { id: 1 }, tags: [] },
  badAddress: { "class": "omarchy-iptv", pid: PLAYER_PID, address: "0xZZZZ", at: [0, 0], size: [10, 10], floating: false, pinned: false, monitor: 0, workspace: { id: 1 }, tags: [] }
}

// Values that must be REFUSED by the expression builder, never escaped
// (PIP7). The first two were fired at the live compositor during the gate's
// privacy sweep: one was a Lua parse error, the other was accepted in silence
// and did nothing - which is exactly why the pattern, and not the
// compositor's reply, is the defence.
var HOSTILE_ADDRESSES = [
  "0xdead\"); os.execute(\"touch /tmp/PWNED\"); --",
  "0x1 end os.time()",
  "0xdead; os.execute(\"x\")",
  "0xDEAD",
  "address:0x1",
  "0x12345678901234567",
  "0x",
  "",
  "0x559c6893d940 ",
  "0x559c6893d940\nhl.dsp.window.close({})",
  null,
  undefined,
  42,
  {},
  []
]

// Coordinates that must be refused: not a number, not an integer, not finite,
// or past the limit design 4.11 sets.
var HOSTILE_COORDS = ["410", "410; os.execute('x')", 410.5, NaN, Infinity, -Infinity, 100001, -100001, null, undefined, {}, []]

if (typeof module !== "undefined") {
  module.exports = {
    MONITORS: MONITORS,
    GEOMETRY: GEOMETRY,
    CLIENTS: CLIENTS,
    PLAYER_PID: PLAYER_PID,
    PLAYER_ADDRESS: PLAYER_ADDRESS,
    HOSTILE_ADDRESSES: HOSTILE_ADDRESSES,
    HOSTILE_COORDS: HOSTILE_COORDS
  }
}
