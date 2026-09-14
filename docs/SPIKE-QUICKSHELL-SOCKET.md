# Omarchy IPTV -- Spike: `Quickshell.Io/Socket` as the mpv IPC observer (gate PB-0)

Owner: Software Architect. Date: 2026-09-13. Gate: PB-0 in
docs/ARCHITECTURE-PLAYER.md section 9 ("Lane PB"). Repo at `88c1ea5`
(`v0.2.1-4-g88c1ea5`). Companion: docs/ARCHITECTURE-PLAYER.md sections 4.5,
4.7, 4.8 and 9.

Machine of record: Omarchy 4.0.0.alpha, Quickshell 0.3.1-1, Qt 6.11.2-3,
mpv 1:0.41.0-6, Python 3.14.7-1.

**Verdict: VIABLE WITH CAVEATS.** The socket observer works, and works well
-- but only if lane PB **never reuses a `Socket` object across a failed
connect**. The single declarative `Socket { id: playerSocket }` that section 9
currently prescribes is the one shape that provably cannot work: it connects
once and then bricks itself permanently on the first refused reattach, and it
does so silently. The degraded-mode fallback in section 2.1 is **not**
required. Two design-document corrections are needed (section 8 below); no
product-owner ruling, PO-1 included, needs revisiting.

## 1. Scope and method

PB-0 asks six questions. The type surface was already confirmed present in
`/usr/lib/qt6/qml/Quickshell/Io/quickshell-io.qmltypes` (`Socket` at lines
194-240, `name:` at 197: writable `path`, writable `connected` notifying
`connectionStateChanged`, `error(QLocalSocket::LocalSocketError)`, `write`,
`flush`, `DataStream` prototype carrying `parser`; `SplitParser` at 282-301
with `splitMarker`). What was missing was any evidence it behaves: a fresh
`grep -rn "Socket"` over `/usr/share/omarchy/shell` still returns **zero**
hits for both `Socket` and `SocketServer`. `SplitParser` is exercised -- 17
hits across 11 files -- but only ever as a `Process` `stdout`/`stderr` reader
(`plugins/bar/Bar.qml:1087`, `plugins/menu/Menu.qml:887`,
`plugins/clipboard/Clipboard.qml:287`, and fourteen more) -- never behind a
`Socket`.

Method: ten standalone Quickshell configs driven against a purpose-built
python `FakeMpv` speaking mpv's newline-delimited JSON IPC, plus one run
against a real headless mpv 0.41.0. Every run was
`QT_QPA_PLATFORM=offscreen qs -p <file>`; Quickshell accepts offscreen
without complaint (it warns that `WAYLAND_DISPLAY` is set but runs), so **no
window was created at any point** -- confirmed independently by
`hyprctl clients -j | grep -c '"class": *"mpv"'` returning 0 during the real-mpv
run. Scratch tree `/tmp/claude-1000/omarchy-iptv-spike/` (ephemeral; the
reproduction material below is self-contained). Nothing under `~/.config`,
`~/.cache`, `~/.local/state`, `/usr/share/omarchy` or
`~/.config/omarchy/plugins/io.github.rmcdavid.iptv` was written; the spike used
its own runtime directory `/run/user/1000/omarchy-iptv-spike/`, since removed,
and never touched `/run/user/1000/omarchy-iptv/`. No repo file other than this
one was modified. All processes and sockets created were reaped.

Observed `QLocalSocket::LocalSocketError` values, used throughout below:
`0 = ConnectionRefusedError`, `1 = PeerClosedError`, `2 = ServerNotFoundError`.

## 2. The headline finding: a failed connect brick

This is the finding that decides the gate, so it comes first.

**A `Socket` object whose `connected = true` fails is dead forever.** No
sequence of property writes revives it: not `connected = true` again, not
`connected = false` then `true` (same turn or separate event-loop turns), not
re-assigning `path`, not clearing `path` to `""` and setting it back. It emits
its error exactly once and then silently ignores every subsequent instruction,
including after the peer it was waiting for has appeared.

Evidence, run T5 -- the 250 ms retry loop the design prescribes, against a
peer that is SIGKILLed and then comes back 4.5 s later. `LOOP-A` re-arms one
long-lived `Socket`; `LOOP-B` creates a fresh `Socket` per attempt:

```
FINAL A=false aAttempts=31 aErrors=2  aReconnectedAt=0
FINAL B=true  bAttempts=15 bErrors=15 objectsCreated=16 bReconnectedAt=1789359942298
   (server restarted at 1789359942126 -- B recovered 172 ms later)
```

`LOOP-A` made 31 re-arm attempts and produced **two** errors total: one
`PeerClosedError` when the peer died, one `ConnectionRefusedError` on the
first retry. Attempts 2 through 31 issued no syscall and emitted nothing --
corroborated by the quickshell log, which carries exactly one WARN line per
real attempt (15 `ConnectionRefusedError` + 2 `PeerClosedError` for the run,
all but one of the refusals belonging to `LOOP-B`). `LOOP-A` never reconnected
although the server was live for the final 4.5 seconds.

Run T1b ruled out the three obvious workarounds; run T1c showed a virgin
`Socket` and a dynamically created replacement both connect to the same live
path in the same process at the same instant (`FINAL D=true E=false F=true`,
where `E` was the burned object and `F` a fresh one).

**Mechanism** (Quickshell 0.3.1 `src/io/socket.cpp`, quoted to explain the
behaviour, not as the primary evidence):

```cpp
void Socket::setConnected(bool connected) {
	this->targetConnected = connected;
	if (!connected) {
		if (this->socket != nullptr && !this->disconnecting) {
			this->disconnecting = true;
			this->socket->disconnectFromServer();
		}
	} else if (this->socket == nullptr) this->connectPathSocket();
}

void Socket::onSocketError(QLocalSocket::LocalSocketError error) {
	qCWarning(logSocket) << "Socket error for" << this << error;
	emit this->error(error);
}
```

The retry guard is `this->socket == nullptr`. `onSocketError` does **not**
null the pointer, and `onSocketDisconnected` (which does:
`this->socket->deleteLater(); this->socket = nullptr;`) never runs for a
connection that never connected. So after a failed connect the object holds a
non-null `QLocalSocket` in an unconnected state forever, and the `else if`
never fires again. `setConnected(false)` cannot clear it either: it sets
`disconnecting = true` and calls `disconnectFromServer()` on an already
unconnected socket, which emits nothing, so `disconnecting` also latches.
`setPath` is guarded by the same `this->socket == nullptr` test.

The corollary is the good news in question 4: a socket that **did** connect
and then lost its peer goes through `onSocketDisconnected`, which nulls the
pointer, so that object *can* be re-armed. That asymmetry is why the bug is
easy to miss -- the happy path and the first failure both look fine.

### 2.1 The second trap: arming `connected = true` while already connected

`onSocketDisconnected` ends with `if (this->targetConnected)
this->connectPathSocket();`, and `onSocketConnected` sets
`targetConnected = false`. So a socket that simply connects has no
auto-reconnect. But if PB writes `playerSocket.connected = true` defensively
while the socket is *already connected* -- a natural "make sure we are
attached" reflex, and a no-op to all appearances -- `targetConnected` latches
`true`, and the moment the peer dies the Socket fires an immediate,
zero-delay reconnect at the peer that just died. That attempt fails, and by
section 2 the object is now bricked, without PB having asked for anything.

Evidence, run T9. `TRAP` re-armed while connected; `CLEAN` did not. Peer
SIGKILLed at epoch ms 1789360250265:

```
1789360250267 | TRAP error#1=1   (PeerClosedError,      2 ms after the kill)
1789360250267 | TRAP connected=false
1789360250267 | TRAP error#2=0   (ConnectionRefusedError -- unrequested auto-retry)
1789360250267 | CLEAN error#1=1
1789360250267 | CLEAN connected=false
... server restarted, both told to reconnect ...
1789360255423 | TRAP after retry=false
1789360255423 | CLEAN connected=true
FINAL trap=false trapErrs=2 | clean=true cleanErrs=1
```

One redundant line of defensive code costs the reattach permanently.

## 3. The six questions, answered

### Q1 -- `connected = true` on a path that does not exist

**Fails cleanly and synchronously. No wedge, no retry storm, no crash.**

Run T1. The assignment emits `error(2 /* ServerNotFoundError */)` *inside*
the assignment and returns; `connected` reads `false` on the next statement.
A 250 ms liveness tick kept firing for 3 s afterwards, fds stayed flat and
CPU stayed at zero ticks. A path whose **parent directory** is missing behaves
identically. Reattach-on-start is therefore safe to attempt blindly -- with
two riders:

- `connectionStateChanged` does **not** fire on a failed connect (it is the
  property notify, and `connected` never changed). `error` is the only
  failure signal.
- An **empty** `path` is worse than a bad one: `connectPathSocket()` is
  wrapped in `if (!this->mPath.isEmpty())`, so `connected = true` does nothing
  at all -- no connect, no `error`, no state change. Run T1's third socket
  produced total silence. PB must never arm before `socketPath` is set.

And by section 2, "safe to attempt" means safe *for the process*, not for the
object: the object that made the attempt is spent.

### Q2 -- `SplitParser` and mpv's newline-delimited JSON

**Reliable, in every boundary case tested.** Run T2, all against one
connection:

| Case | Result |
|---|---|
| 3 complete messages in one `write()` | 3 separate `onRead` calls, in order |
| 1 message split across 2 writes, 300 ms apart | buffered, delivered once, whole |
| complete line + dangling partial, completed 300 ms later | both delivered correctly |
| 200 KB single line | delivered intact (200002 chars) in ~7 ms |
| 2000 messages in one `write()` | all 2000 delivered, ~12 ms, none lost |
| non-ASCII incl. astral plane | `"Canal É 7 — ümlaut 日本"`, `"📺"` round-trip exact |

Totals for the run: `reads=2021 replies=10 events=2011 floodSeen=2000
badJson=0`. The `splitMarker` is **stripped** -- `onRead` receives a JS
`string` with no trailing newline (`RAW#1 len=26 endsWithNL=false
typeof=string`), so `JSON.parse(String(line))` is correct with no trimming.

One caveat, run T4: **a trailing partial line is discarded at EOF.** A peer
that sent `{"event":"before-eof"}\n{"event":"never-terminated"` and then
closed delivered the first and dropped the second. That is the right
behaviour (no garbage reaches the router), but it means PB must not depend on
a last-gasp `end-file` surviving a hard death -- which section 4.8 already
gets right by treating socket EOF as its own terminal signal.

### Q3 -- duplex: requests and unsolicited events on one connection

**Yes, with clean `request_id` correlation.** Run T2 fired four commands
back-to-back and got four replies, with a `property-change` event interleaved
between the replies to `request_id` 201 and 202, followed by the `start-file`
/ `log-message` / `end-file` sequence for the `loadfile`. Nothing was
mis-attributed; the pending map drained to `{}`.

Confirmed against **real headless mpv 0.41.0** (run T7,
`mpv --no-config --no-terminal --idle=once --force-window=no --vo=null
--ao=null --input-ipc-server=... --msg-level=all=no`, zero windows):

```
SEND[logmsgs] rid=1 ... SEND[stash-read] rid=6      (six commands, no waiting)
REPLY rid=1 matched=logmsgs   error=success
REPLY rid=2 matched=observe-idle error=success
REPLY rid=3 matched=q-version error=success data="mpv v0.41.0"
EVENT {"event":"property-change","id":7,"name":"idle-active","data":true}
REPLY rid=4 matched=q-idle    error=success data=true
REPLY rid=5 matched=stash-write error=success
REPLY rid=6 matched=stash-read error=success data={"schema":1,"playing":true,"name":"Canal É 7"}
...
REPLY rid=10 matched=loadfile-bad error=success data={"playlist_entry_id":1}
EVENT {"event":"start-file","playlist_entry_id":1}
EVENT {"event":"property-change","id":7,"name":"idle-active","data":false}
EVENT {"event":"log-message","prefix":"stream","level":"error","text":"Failed to open http://127.0.0.1:9/nope.ts.\n"}
EVENT {"event":"end-file","reason":"error","playlist_entry_id":1,"file_error":"loading failed"}
SUMMARY replies=7 unmatched=0 events=8 stillPending={}
```

Three section-4 assumptions fall out of that transcript for free:

1. `loadfile`'s reply carries `data.playlist_entry_id` and the following
   `start-file` confirms it -- section 4.8 / F4 as written.
2. `end-file{reason:"error", file_error:"loading failed"}` is verbatim what
   section 4.8's table expects.
3. The `user-data/omarchy-iptv-spike` sibling node round-tripped through the
   **QML** socket with non-ASCII intact, so section 4.6's stash works from
   Service.qml and not only from the python helper.

Incidental, outside PB-0's scope and already settled by PO-5: mpv's
`ytdl_hook` fired on the failed HTTP open and logged the URL, i.e. the
`yt-dlp`-on-argv exposure PO-5 accepted is real and observable by default.
No action requested.

### Q4 -- the peer disappears

**Clean, and fast: 2-3 ms.** Three deaths tested (run T4, T9, T10):

| Death | Signals | Latency |
|---|---|---|
| peer `kill -9` | `error(1 /*PeerClosedError*/)` then `connectionStateChanged` with `connected === false` | 3 ms, 2 ms, 2 ms across three runs |
| peer closes the connection gracefully | same pair | immediate |
| `unlink()` of the socket **file** while connected | **nothing** -- the connection survives and stays fully usable | n/a |

The unlink result matters for section 4.5: `player probe`'s one stale-socket
unlink cannot disturb a QML observer that is already attached. It only changes
the error a *future* connect gets from `ConnectionRefusedError` to
`ServerNotFoundError`, and both are handled identically by section 7's
pattern.

**Reconnect after a peer death: yes, but only for an object with no failed
attempt in its history.** Run T4 reconnected the same object with a plain
`connected = true` the instant the server returned. Run T5 shows that the same
object loses that ability the moment one retry lands on an absent server --
which, in production, is the overwhelmingly likely first retry, because the
thing that just died is exactly what you are retrying against. Treat
same-object reconnect as unusable and always build a new object.

### Q5 -- built-in reconnect or backoff

**Neither. The plugin must drive it with a timer.** There is exactly one
built-in retry: the `if (this->targetConnected) this->connectPathSocket();`
tail of `onSocketDisconnected`, which is disarmed by `onSocketConnected` and
is a liability rather than a feature (section 2.1). There is no delay, no
backoff, and no repeat. Run T5 observed a disconnected socket sit idle for
4.5 s with a live server in front of it until the QML timer acted.

### Q6 -- fd leaks, CPU spin, repeated cycles

**Clean.** Two stress runs, sampled on the real `qs` pid via `/proc`:

Run T6 -- 50 connect/disconnect cycles on one reused object (server always
present, so no attempt ever failed), then 50 cycles each creating and
destroying a fresh object:

```
PHASE 1 done: 50 same-object cycles, ok=50 fail=0
PHASE 2 done: 50 fresh-object cycles, ok=50 fail=0, repliesReadInPhase2=50
FakeMpv saw: 100 accepts, 101 commands, 100 clean EOFs
fds 26 -> 27 (sockfds 5 -> 6, the in-flight connection), threads 10, constant
cpu +4 ticks (40 ms) total, rss 112916 -> 113052 kB
```

Run T8 -- the degraded case: 120 **failed** attempts (60 with explicit
`destroy()`, 60 deliberately leaked and never destroyed):

```
errs=120  connectedEver=0
fds 26, sockfds 5 -- constant, no growth at all
cpu +4 ticks (40 ms) total, rss +136 kB
```

Even the 60 deliberately leaked failed sockets cost nothing: a failed connect
never holds a descriptor. Note also that 50 same-object cycles all succeeded,
which pins the rule precisely -- connect/disconnect churn is fine, it is a
*failed* attempt that is fatal to the object.

**One real cost: log noise.** Every failed attempt writes one line,
`WARN quickshell.io.socket: Socket error for Socket(0x...) QLocalSocket::...`,
to `/run/user/1000/quickshell/by-id/*/log.qslog` and the journal -- 120 for
120 attempts in T8, exactly one per attempt, with no deduplication. A
free-running 250 ms retry is 4 lines/second, ~14k/hour. See caveat C6.

## 4. Decision

**Viable with caveats.** All six questions come back positive on the
mechanism. `SplitParser` framing is sound at every boundary that matters,
duplex correlation works against real mpv, death detection is 2-3 ms (three
orders of magnitude better than the 10 s poll it replaces), and there is no
leak or spin. The design's central claim -- that section 4.8's four failure
signals can be built on this type -- holds.

What does not hold is the *shape* section 9 prescribes. A single long-lived
declarative `Socket` is the one implementation that is guaranteed to fail, and
to fail silently and permanently after the first reattach miss. The caveats in
section 5 are not optional polish; C1 and C2 are the difference between a
working reattach and a plugin that shows "idle" forever after the first time
mpv dies while the shell is running.

The degraded-mode fallback in section 2.1 (no subscriber; detection via the
10 s `status` poll plus `player start`'s first-load window) is **not**
invoked. It remains correct as a contingency and is unaffected.

## 5. Caveats lane PB must code around

- **C1 (blocking).** Never reuse a `Socket` object after a failed
  `connected = true`. Every reattach attempt must construct a **new** object
  from a `Component` and destroy the old one. The declarative
  `Socket { id: playerSocket }` in section 9's PB bullet must become
  `Component { id: playerSocketComponent; Socket { ... } }` plus
  `property var playerSocket`.
- **C2 (blocking).** Never write `connected = true` on a socket that is
  already connected. It arms the hidden zero-delay auto-reconnect of section
  2.1 and bricks the object at the exact moment mpv dies. Guard every arm with
  `if (playerSocket === null)`.
- **C3.** `playerUp` must null-guard. Section 4.7's
  `playerSocket.connected || playerPending` throws once `playerSocket` is a
  `var` that is null between attempts. Use
  `(playerSocket !== null && playerSocket.connected) || playerPending`.
- **C4.** `onConnectionStateChanged` fires **synchronously inside** the
  `connected = true` assignment, before the caller can store the object
  reference, and before the `playerUp` binding re-evaluates. Runs T10 showed
  the handler logging `playerUp=false` on the very tick it attached, with
  `playerUp -> true` arriving immediately after. Inside that handler read
  `this.connected`, never `root.playerUp` or `root.playerSocket`. Publishing
  the reference before arming does not fix it -- the handler is connected
  before the binding subscribes.
- **C5.** A failed connect emits `error` only; there is no
  `connectionStateChanged`. Do not wait for a state change to learn that an
  attach failed -- test `connected` immediately after the assignment, which
  is authoritative because the assignment is synchronous.
- **C6.** Bound the retry loop. One WARN line per failed attempt goes to the
  journal, so an unbounded 250 ms retry is ~14k lines/hour. Gate it on
  `playerWanted` as section 4.7 already specifies, and additionally cap the
  burst (12 tries ≈ 3 s fits inside the existing 12 s `playerWatchdog`
  budget) before falling back to `player probe` / the 10 s poll rather than
  spinning forever.
- **C7.** Never `write()` unless `connected` is true. A write to an
  unconnected socket returns normally, throws nothing, and is silently
  discarded (run T1).
- **C8.** Never arm with an empty `path` -- it is a total no-op with no error
  (Q1).
- **C9.** A trailing partial line is dropped at EOF (Q2), so the `end-file`
  that explains a death may legitimately be absent. Section 4.8's "no
  `end-file` at all -> stream failure, generic reason" row already covers
  this; keep it, and keep the entry gate fail-open.
- **C10.** `destroy()` called on a `Socket` from inside its own
  `onConnectionStateChanged` is safe -- QML defers it. Run T10 exercised that
  path on the peer death and did ~25 `destroy()` calls in total across the
  run, with no crash and no fd growth.

## 6. Reference snippet for lane PB

This is run T10, verbatim minus the test scaffolding. It was exercised end to
end: absent server -> 12 failed retries -> server appears -> attach 132 ms
later -> real `loadfile` reply plus `start-file` / `log-message` / `end-file`
-> peer `kill -9` -> detach in 2 ms -> 12 failed retries -> server returns ->
reattach 246 ms later. fds 26 -> 27, cpu +1 tick, rss flat.

```qml
property var playerSocket: null
property bool playerWanted: false
property bool playerPending: false
readonly property bool playerUp: (root.playerSocket !== null && root.playerSocket.connected)
                                 || root.playerPending

Component {
  id: playerSocketComponent
  Socket {
    path: root.socketPath
    onConnectionStateChanged: {
      // NB: fires synchronously inside `connected = true` below.
      // Read `this.connected` here, never root.playerUp / root.playerSocket.
      if (this.connected) {
        root.playerPending = false;
        playerSocketTimer.stop();
        root.onPlayerAttached();
      } else {
        root.releasePlayerSocket();   // peer gone; never re-arm this one
        root.onPlayerGone();
      }
    }
    onError: function (err) { root.onSocketError(err); }
    parser: SplitParser {
      splitMarker: "\n"
      onRead: function (line) { root.handlePlayerLine(String(line)); }
    }
  }
}

function releasePlayerSocket() {
  if (root.playerSocket === null) return;
  var s = root.playerSocket;
  root.playerSocket = null;       // drop the binding first
  s.destroy();                    // deferred by QML, safe from inside a handler
}

// Returns true iff attached. Synchronous: `connected` is authoritative
// on the next line.
function attachPlayerSocket() {
  root.releasePlayerSocket();
  var s = playerSocketComponent.createObject(root);
  root.playerSocket = s;
  s.connected = true;
  if (s.connected) return true;
  root.playerSocket = null;
  s.destroy();                    // a failed connect bricks it -- discard
  return false;
}

Timer {
  id: playerSocketTimer
  interval: 250; repeat: true; running: false
  property int tries: 0
  onTriggered: {
    if (!root.playerWanted) { playerSocketTimer.stop(); return; }
    playerSocketTimer.tries++;
    if (root.attachPlayerSocket()) {
      playerSocketTimer.tries = 0;
      playerSocketTimer.stop();
    } else if (playerSocketTimer.tries >= 12) {   // C6: cap the burst
      playerSocketTimer.tries = 0;
      playerSocketTimer.stop();
      root.runPlayerProbe();
    }
  }
}
```

Writes take the same shape the helper's `MpvIpc.request()` uses -- one JSON
object per line, `request_id` echoed back:

```qml
root.playerSocket.write(JSON.stringify({ command: cmd, request_id: rid }) + "\n");
root.playerSocket.flush();
```

## 7. Reproducing this

`FakeMpv` in full is ~200 lines; the part that proves C1 and C2 is this much,
and needs no fixtures:

```python
import json, os, socket, threading
path = "/run/user/1000/omarchy-iptv-spike/live.sock"
os.makedirs(os.path.dirname(path), exist_ok=True)
if os.path.exists(path): os.unlink(path)
srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
srv.bind(path); os.chmod(path, 0o600); srv.listen(8)
def handle(c):
    buf = b""
    while True:
        chunk = c.recv(65536)
        if not chunk: return
        buf += chunk
        while b"\n" in buf:
            line, _, buf = buf.partition(b"\n")
            m = json.loads(line)
            c.sendall((json.dumps({"error": "success", "data": "mpv 0.41.0",
                                   "request_id": m.get("request_id", 0)}) + "\n").encode())
while True:
    conn, _ = srv.accept()
    threading.Thread(target=handle, args=(conn,), daemon=True).start()
```

Then, in one process each: `QT_QPA_PLATFORM=offscreen qs -p spike.qml`, with
the server started, `kill -9`ed and restarted around it. The decisive
assertion is that a `Socket` re-armed after one refused attempt never
reconnects, while a freshly constructed one attaches on the next 250 ms tick.
Every run in this document was window-less; Quickshell needs no display to
exercise `Quickshell.Io`.

For lane PC: none of this replaces a live-shell gate. The PO's D-LIVE-20 note
in section 12 stands -- a scratch Quickshell is not a shell restart, and the
reattach path still has to be proven in the live session.

## 8. Consequences for the design document

Two corrections are required in docs/ARCHITECTURE-PLAYER.md. Both are lane-PB
implementation shape, not architecture, and neither disturbs a PO ruling. They
are recorded here rather than edited in, because this lane does not own that
file.

1. **Section 9, Lane PB, second bullet.** "Add `Socket { id: playerSocket }` +
   `SplitParser` + `Connections`" must become a `Component`-plus-dynamic-object
   construction per caveat C1, with the `playerSocketTimer` recreating the
   object on every attempt. As written the bullet specifies the one shape that
   cannot reattach.
2. **Section 4.7, the `playerUp` definition.** `playerSocket.connected ||
   root.playerPending` must gain the null guard of caveat C3, since
   `playerSocket` becomes a `var` that is null between attempts.

Everything else in sections 4.5 through 4.8 survives unchanged, and three of
its assumptions were positively confirmed in passing (Q3): `loadfile`'s reply
carries `playlist_entry_id`, `end-file` carries the documented
`reason`/`file_error` shape, and the `user-data` stash round-trips from QML.

**No product-owner ruling needs revisiting.** PO-1 (`--idle=once`) is
untouched and is in fact slightly strengthened: run T7 observed real mpv under
`--idle=once` exit 1 ms after `end-file{reason:"error"}`, which is PA-0(b)
satisfied incidentally -- though PA-0(a), the `loadfile ... replace` case, is
lane PA's gate and was not tested here. PO-1's stated safety net ("it leaves a
working degraded mode if the socket observer proves unusable") is not needed,
because the observer is usable. PO-2 through PO-7 are unaffected.
