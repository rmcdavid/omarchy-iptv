# Accessibility investigation: why nothing in the guide reaches AT-SPI

Defect D-GS-3 (docs/STATUS.md:167). Written by the architect, 2026-09-15,
against `main` at `64cd46b`. Three investigations were run in parallel and each
was attacked by a separate skeptic. This document keeps only what survived that
attack, labels assumptions as assumptions, and says plainly where the answer is
still open.

Read-only pass. Nothing in the repo, the installed plugin, `~/.config`,
`~/.cache`, `~/.local/state` or `/usr/share/omarchy` was modified, and the
running shell (pid 2488126) was never restarted.

---

## 1. The finding, restated

During the M2-09 live pass, with the guide open on 3,335 rows on the user's real
desktop, the shell's accessible root on the AT-SPI bus reported `ChildCount 0`
and `GetChildren` returned an empty array. A GTK client on the same bus in the
same moment reported a child, so the probe itself worked. The observation is
recorded at docs/QA-RESULTS.md:4766-4790 and on the board at docs/STATUS.md:167,
and the product owner sent it to its own investigation as ruling GS10
(docs/UX-GUIDE-AT-SCALE.md:1115).

Two details of that record matter more than they first appear, and both were
missed by one of the three investigations:

- The gate was open when it was measured. QA-RESULTS.md:4772-4779 says the
  accessibility gate was enabled, that "the shell connected to the accessibility
  bus within a second without a restart, and again after a restart with it
  enabled from startup", and that **both times** the root reported zero
  children. The setting was restored to false afterwards
  (docs/QA-RESULTS.md:4862). So the current `IsEnabled false` reading on this
  machine is a restored state, not a history, and any conclusion of the form
  "the gate has never been opened, that is the whole story" is contradicted by
  this project's own evidence.
- Which connection was read is not recorded. This turns out to decide the case.
  See section 4.2.

No screen reader is installed on this machine (`orca` absent), so everything
here was observed through the bus directly.

## 2. Why it matters beyond this plugin

This project has written accessibility rules since M0: roles and names on every
surface (docs/UX.md section 7.1, docs/UX-SOURCES.md section 7.1), nothing
conveyed by colour or position alone (7.2), a row announcement that names the
channel and its state, and a privacy rule that a screen reader never receives a
credential (docs/UX-SOURCES.md 6.7). The code sets those properties: 56 lines
carrying `Accessible.` in Guide.qml and 2 in BarWidget.qml, 24 `Accessible.role`
declarations in the guide and 1 in the bar.

Every one of those rules is currently unobservable on this machine, and has been
for the whole life of the project. The reason it went unnoticed is not
carelessness about accessibility; it is that the acceptance criteria were
written as greps of our own source:

| Test | Method as written | Where |
|---|---|---|
| TC-A11Y-01 roles and names | ``A `grep -n 'Accessible\.' Guide.qml BarWidget.qml` `` | docs/QA.md:220 |
| TC-BAR-11 accessible names | ``A `grep -n 'Accessible' BarWidget.qml` `` | docs/QA.md:146 |
| SRC-A11Y-01 roles and names | ``A `grep -n 'Accessible\.' Guide.qml` `` | docs/QA-SOURCES.md:239 |
| SRC-A11Y-05 no secret to a screen reader | `A grep` | docs/QA-SOURCES.md:243 |

`grep -rn Accessible scripts/` returns nothing. The only executable assertions
anywhere are 12 in tests/Model.test.js and 5 in tests/Model.spec.qml, and all 17
are on the pure string builders (`rowAccessibleName`, `barAccessibleName`,
`sourceAccessibleName`) - they prove the strings compose correctly, never that a
string becomes a node.

That is exactly the failure shape CLAUDE.md constraints 11 and 12 describe: a
rule joined to its verification by a name rather than by a call, and a test that
was never seen to fail. The general lesson is larger than D-GS-3 and is the part
of this report that should outlive it: **a documented rule with no observation of
its real sink is a claim, not a feature.** Section 8 proposes the process change.

## 3. Evidence standard used here

Claims are graded:

- **Observed here** - a command run during this pass, output quoted.
- **Observed and independently reproduced** - measured by one investigation and
  re-measured by a different agent on different code.
- **Observed once, disputed** - two probes disagree; treated as unsettled.
- **Read, not observed** - from headers, symbol tables, type metadata or
  disassembly.
- **Assumption** - explicitly labelled, never used to support a conclusion.

## 4. What is established

### 4.1 The machine, the bus and the toolkit

Observed here:

```
pacman -Q quickshell qt6-base at-spi2-core gtk3
  quickshell 0.3.1-1   qt6-base 6.11.2-3   at-spi2-core 2.60.6-1   gtk3 1:3.24.52-1

busctl --user get-property org.a11y.Bus /org/a11y/bus org.a11y.Status \
  IsEnabled ScreenReaderEnabled
  b false
  b false

busctl --address=unix:path=/run/user/1000/at-spi/bus_0 list
  :1.0     1347  xdg-desktop-por
  :1.2     1393  at-spi2-registr    (org.a11y.atspi.Registry)
  :1.213   2488126 quickshell
  :1.3     1078  udiskie
  :1.4     1392  voxtype-osd-gtk
```

The accessibility bus is up and has been since boot; the gate is currently
closed because nothing has asked for accessibility, which is the designed
default on a machine with no assistive technology installed. Nothing here is
misconfigured.

Qt on this machine ships accessibility in full. The hypothesis "Qt was built
without a11y" is dead, and so is the inference some readers draw from the
missing plugin directory:

- `/usr/include/qt6/QtGui/6.11.2/QtGui/private/qspiaccessiblebridge_p.h:37`
  declares `class Q_GUI_EXPORT QSpiAccessibleBridge : public QObject, public
  QPlatformAccessibility`. In Qt 6.11 the AT-SPI bridge **is** the platform
  accessibility object, compiled into QtGui, not a loadable plugin. The absence
  of `/usr/lib/qt6/plugins/accessiblebridge` is therefore normal.
- `nm -D --defined-only /usr/lib/libQt6Gui.so.6 | grep -cE
  'SpiAccessibleBridge|AtSpiAdaptor'` -> 22.
- `/usr/include/qt6/QtGui/qtgui-config.h:4` `QT_FEATURE_accessibility_atspi_bridge 1`,
  `:108` `QT_FEATURE_accessibility 1`.
- libQt6Quick exports 193 accessibility symbols including `QAccessibleQuickItem`
  and `QAccessibleQuickWindow`.

The bridge is gated on `org.a11y.Status`, and it follows the gate at runtime -
`qspiaccessiblebridge_p.h:56` declares the slot `void enabledChanged(bool)` and
`:60` `void updateStatus()`. Observed and independently reproduced, by two
agents on separate buses: with the gate closed, a `qml` process on the wayland
platform never joins the accessibility bus at all; with the gate forced open
(`QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1`, or `AT_SPI_BUS_ADDRESS`, or by flipping
the status property while it runs) the same process joins within about a second
and publishes `ToolkitName "Qt"`, `Version "6.11.2"`, `ChildCount 1`, and the
tree walks: `application -> frame -> list "PROBE LIST" -> list item "PROBE ROW
ONE"`. **QML `Accessible.role` and `Accessible.name` do reach AT-SPI on this
machine once a bridge is live.** No restart and no permanent configuration
change is needed to open the gate; starting a screen reader is what normally
opens it.

One consequence that constrains every future QA design: the `offscreen` and
`minimal` platform plugins define no `accessibility()` override and never
reference the bridge, so a headless offscreen process has no AT-SPI bridge even
with the env var set. **Any real bus assertion must run on the wayland
platform**, which means it needs the display lane.

### 4.2 The GTK decoy - identified, and its mechanism is NOT explained

Observed and independently reproduced by all four agents that looked: the
shell's single connection on the accessibility bus, `:1.213` for pid 2488126,
reports `Name "quickshell"`, role `application`, `ChildCount 0`, and -
decisively - `ToolkitName "gtk"`, `ToolkitVersion "3.24.52"`, with the
`Collection` interface present. Qt registrations report `ToolkitName "Qt"`,
`Version "6.11.2"` and no `Collection`. The other GTK3 processes on this bus
(`xdg-desktop-portal-gtk`, `udiskie`) carry the identical fingerprint.

So the empty object that anyone probing the shell by pid will find **is not
Qt's tree**. It is a GTK 3 ATK application object living inside the Qt process,
and it would look exactly the same whether the plugin set every property
correctly or none at all.

GTK is in the process because of the platform theme:
`/usr/share/omarchy/default/hypr/envs.lua:14` sets
`hl.env("QT_QPA_PLATFORMTHEME", "gtk3")`, confirmed live in
`/proc/2488126/environ`; `libqgtk3.so` links libgtk-3, libatk-1.0 and
libatk-bridge-2.0, and all four are mapped in `/proc/2488126/maps`.

What is **not** established is why that ATK bridge registered on the bus. The
obvious explanation - "loading libqgtk3 does it" - was tested and failed: five
bounded headless probes with libqgtk3, libgtk-3 and libatk-bridge all mapped
registered nothing on the bus, one of them waited 30 seconds. The evidence
originally offered for the mechanism ("atk-bridge mapped in process: 5") was
five ELF segments of a single library, and libgtk-3 lists libatk-bridge as a
direct `NEEDED`, so the mapping proves linkage, not activation. Something else
about the long-lived shell triggered the registration. **Do not report this
upstream until the trigger is reproduced.**

Practical rule for every future investigator, and the single most useful thing
to come out of this work: **key on `ToolkitName`, never on `Name`.** With the
gate open the shell has two connections, and Qt names its root after the process
too, so both are likely called "quickshell"; `busctl list` shows the older gtk
one first.

This is what makes the original finding ambiguous. QA-RESULTS.md section 6 does
not record which connection was read, and it cannot be recovered read-only.

### 4.3 The host shell

Observed here and by two agents with `/usr/bin/grep` rather than this
environment's grep wrapper: `/usr/bin/grep -rn 'Accessible\.'
/usr/share/omarchy/shell` exits 1 with no output, across 102 `.qml` files and
34,914 lines. Not one role, name or `ignored`, anywhere in Omarchy's shell -
which matches what docs/UX.md:809 already asserted, now measured.

There are no implicit roles to fall back on either: the UI kit is hand-built
from Rectangles and MouseAreas. Of 33 components in `Ui/`, only `TextField.qml`
(a QtQuick Controls `TextField`) and `PanelToolTip.qml` inherit a Controls
default role. `Ui/ConfirmDialog.qml` builds both of its buttons in a Repeater as
bare `BorderSurface` with a `Text` inside (:88, :91, :108) and sets no
accessibility properties, which is why the two Buttons that
docs/UX-SOURCES.md 7.1 requires on the remove-source confirmation cannot be
delivered by annotating the host's component.

Consequence, independent of D-GS-3: even with a live bridge, the bar, menu,
clipboard picker, emoji picker, notifications, OSD, lock screen and every panel
publish an unnamed, roleless tree. A plugin cannot fix that from inside.

### 4.4 Quickshell

Quickshell contains no accessibility code and suppresses nothing:
`grep -rn -i -E 'accessib|a11y' /usr/lib/qt6/qml/Quickshell/` -> 0 hits;
`nm -C -D --defined-only /usr/bin/quickshell | grep -ci accessib` -> 0; the only
accessibility symbol it imports is `U QQuickWindow::accessibleRoot() const`.

But it is not a bystander structurally, and this is where the case is still
open. Read, not observed, from
`/usr/lib/qt6/qml/Quickshell/_Window/quickshell-window.qmltypes`:

- `PanelWindowInterface` (:134) has prototype `WindowInterface`, whose prototype
  is `Reloadable` - a QObject. QML `PanelWindow` is **not** a QQuickWindow.
- `ProxyWindowBase` (from `proxywindow.hpp`) holds the real window as a separate
  read-only property `_backingWindow` of type `QQuickWindow` (:275).
- `PanelWindowInterface` has no `title` property. `title` exists on
  `FloatingWindowInterface` (:38-47) and not on the panel type. **The plugin
  therefore cannot give its window a name**; that is an upstream gap, not an
  omission in Guide.qml.
- Observed here: `nm -DC -u /usr/bin/quickshell` imports
  `QWindow::setFlag(Qt::WindowType, bool)` and
  `QtWaylandClient::QWaylandShellSurface::setWindowFlags(QFlags<Qt::WindowType>)`.
  Quickshell does manipulate window flags on its backing window. **Which flags it
  sets for a wlr-layer-shell surface is not established** - no debug sources are
  installed (`/usr/src/debug` has no quickshell entry) and a full disassembly did
  not complete inside this pass's time bound.

That matters because of the next fact.

### 4.5 Qt's top-level enumeration drops exactly one window type

Observed here (disassembly) and independently measured by experiment:

```
nm -DC --defined-only /usr/lib/libQt6Gui.so.6
  0000000000616220 T QAccessibleApplication::childCount() const

objdump -d --start-address=0x616220 ... /usr/lib/libQt6Gui.so.6
  616257: call 615c80 <topLevelObjects() [clone .lto_priv.0]>

objdump -d --start-address=0x615c80 ...
  615ccd: call 1a6010 <QGuiApplication::topLevelWindows()>
  615d10: cmp  $0x9,%cl
```

`Qt::Popup == 0x9`. The measurement that matches it: the same hidden probe
window on the real bus with a forced bridge gives a Qt root with `ChildCount 1`
under default flags and `ChildCount 0` with `flags: Qt.Popup`, while `Qt.Tool`,
`Qt.ToolTip`, `Qt.SplashScreen` and `Qt.BypassWindowManagerHint` all give 1.

So **"a live Qt bridge whose application root reports zero children" is a
reachable state that has nothing to do with the plugin's properties.** This is
the concrete mechanism behind candidate cause B below, and it is testable.

Also established, and it narrows the suspects in the plugin's favour: a non-Item
QObject that creates a Window imperatively and reparents declared content into
`window.contentItem` after creation - the ProxyWindowBase pattern - produces a
correct tree (`Window > Dialog "IPTV guide" > ListItem "a row"`). Reparenting
through a proxy is not the break.

### 4.6 The plugin's own markup, on its own terms

Placement is correct everywhere. All 24 `Accessible.role` sites in Guide.qml and
the 1 in BarWidget.qml attach to QQuickItem subclasses - verified against the
host bases: `Ui/BorderSurface.qml:7` is a `Rectangle`, `Ui/ConfirmDialog.qml:4`
an `Item`, `Ui/PanelActionButton.qml:27` and `Ui/Button.qml:20` are
BorderSurfaces, `Ui/BarWidget.qml:12` an `Item`, `Ui/TextField.qml:18` a
Controls `TextField`. Nothing is attached to a Window or a non-Item, so Qt's
refusal path is never triggered. The shape the plugin builds, reproduced in a
plain QQuickWindow on this exact Qt, yields a fully populated 20-node tree.

That is the good news, and it is where the other investigations stopped. The
audit also found six defects that are the plugin's own, and three of them get
**worse**, not better, the moment a bridge starts working.

**(a) Credentials are published as the accessible Value.** For role
`EditableText` Qt publishes the item's `text` as the AT-SPI Value. Measured:
`role=EditableText name="Playlist URL or path" desc="http://prov.example"
value="http://prov.example:8080/get.php?username=joe&password=s3cret"`.
Guide.qml:3150 binds `text:` to `fieldDisplay()`, which returns the raw value
once revealed (Guide.qml:1626-1628). The exposure is wider than first reported:
`Model.fieldMaskable` (Model.js:5555-5561) returns false for anything that is
not a URL field, so the Xtream **username** field has an empty
`Accessible.description` and `echoMode Normal` and publishes the raw login with
no reveal needed; and `Model.maskUrl` (Model.js:4771) is an identity on a
`http://host:port` with no userinfo and no query, so the **server** field is
published too. Only the password is masked, and only because `echoMode` does it.
CLAUDE.md rule 5 lists the sinks that must be redacted and the accessibility bus
is not among them. The comment at Guide.qml:3171 - "A screen reader never gets
the query (UX-SOURCES 6.7)" - is true only while the field is masked.
SRC-A11Y-05 (docs/QA-SOURCES.md:243) "verifies" this rule by grepping for
`Accessible.description` and never looks at the property that leaks.

**(b) The password field has no name, and the doc asks for something Qt will not
give.** `qquickaccessibleattached_p.h:91-96`: `QString name() const { if
(m_state.passwordEdit) return QString(); ... }` - verified here by reading the
installed header. The state bit is set both by Guide.qml:3173 and by the
control itself from `echoMode` (Guide.qml:3154 `password:`, `Ui/TextField.qml:39`).
Either way, the shipping field publishes `name=""`, while
docs/UX-SOURCES.md:1192 mandates the name "Password" **and**
`Accessible.passwordEdit: true` on the same field. Observed once, disputed:
whether deleting Guide.qml:3173 restores the name. One probe said yes; a second,
built on a subclass of the real `Ui/TextField.qml`, measured byte-identical
`name=""` with the line present, deleted, and set to `false`, and measured the
control overwriting the QML value in both directions. The header text supports
the second reading. `Accessible.description` does survive on a passwordEdit
field, so it is the only lever available. **Do not touch line 3173 on the
current evidence** - settle it with one offscreen probe first (it is cheap), and
change the code, the UX row and the QA row together.

**(c) Plain `Text` is not exposed at all.** Measured and reproduced: an item
reaches the tree only if it carries the Accessible attached property or is a
control that sets `isAccessible` itself; an unannotated `Text` or `Rectangle`
does not appear at any depth. Eleven information-bearing Texts in the guide have
no accessible owner other than the card named "IPTV guide": Guide.qml:2755,
:2765, :2777, :2799, :2819, :2832 (the entire empty / first-run / unconfigured
surface), :2085 (the scope and count caption, e.g. "All - 1,204 of 3,335"),
:3399 (footer key hints), :3103, :3299, :3355 (form prose). docs/UX.md section
7.1 has nine rows and covers none of these states. **With a working bridge, a
first-run user would be handed a Dialog called "IPTV guide" containing nothing
readable at all** - no title, no prose, no command to run.

**(d) Virtualisation caps what a reader can reach.** Measured: `model: 3000`
with the guide's cacheBuffer yields `role=List name="Channels in All"
children=13`, one ListItem per realised delegate. Qt Quick exposes no table or
position interface for ListView, so an AT is told "a list of 13". The existing
mitigation - baking ", row N of M" into each name (Model.js:4112-4131) - is the
only available fix and is already in place; docs/UX.md 7.1's promise of one
ListItem per row is not deliverable at 10,000 channels and should be reworded
rather than re-implemented.

**(e) Nothing is ever announced.** Zero `Accessible.announce(` call sites in the
repo; the API exists on this Qt (`Q_REVISION(6, 8) Q_INVOKABLE void announce(...)`,
qquickaccessibleattached_p.h:244). The banner, the form result line, the
numeric-entry chip and the no-match transient fire only a NameChanged that
nothing acts on.

**(f) Smaller items.** Rows carry the `focused` state with no `focusable` bit
(`Accessible.focusable` appears zero times in the repo), and real Qt focus stays
on the key catcher. The numeric-entry chip's name is a hardcoded English literal
(Guide.qml:2631-2632) outside the `root.copy` table (Guide.qml:166-211). One
earlier claim is withdrawn: form field values do **not** outlive the form -
the fields are Repeater-built from `Model.formFields` (Guide.qml:311) and
`Model.closeForm` nulls the form (Model.js:5496), so the delegates are
destroyed. Hidden *screens* do stay in the tree as `invisible+offscreen` nodes.

## 5. What is not established

1. Which bus connection QA read during the live pass. Not recorded, not
   recoverable read-only. This decides the whole case.
2. Whether a Quickshell `PanelWindow`'s backing window is enumerated by
   `QAccessibleApplication`, and what window flags Quickshell sets on it.
3. Why the GTK ATK bridge registered in the shell process at all, given that
   five probes which loaded the same libraries did not register.
4. Whether an AT announces on `object:state-changed:focused` for a ListItem
   without the `focusable` state - i.e. whether adding `Accessible.focusable` is
   a fix or a guess. No screen reader is installed, so nothing here can settle it.
5. Whether the performance budgets (UX 7.6: guide open under 150 ms, typing
   responsive) survive with accessibility active. One cursor jump produced on the
   order of 40 tree events in a probe; nobody has measured the real guide.
6. Whether an AT client filters `invisible+offscreen` nodes in practice, which is
   what decides whether always-present hidden screens are a defect or only untidy.
7. Whether deleting Guide.qml:3173 changes anything (section 4.6b).

## 6. Cause: SETTLED

The three investigations left the cause open between two candidates and
specified an experiment to separate them. **I ran it on 2026-09-15**, plus three
controls the investigations had not specified, and the answer is decisive.

The shell was never restarted (pid 2488126, started 09:15:44, same pid and start
time before and after). The gate was snapshotted `false`, opened for each
measurement, and restored to `false` every time, including on failure, by a
shell trap. Every probe process was killed by pid, never by pattern.

### 6.1 The measurements

With `org.gnome.desktop.interface toolkit-accessibility` true, the bridge
attaches in about a second without a restart. The running shell then has **two**
connections on the bus, both named `quickshell`:

| Connection | ToolkitName | Version | ChildCount |
|---|---|---|---|
| `:1.213` | `gtk` | 3.24.52 | **0** |
| `:1.776` | `Qt` | 6.11.2 | **0** |

This kills candidate A as a complete explanation. The GTK decoy is real, and it
is exactly as misleading as predicted, but reading the correct connection gives
the same answer: **the Qt root genuinely has no children.**

Then the controls, all in the same session, on the same bus, with the same gate
open and the same markup pattern:

| What was run | Window it creates | Mapped as | ChildCount |
|---|---|---|---|
| `qml a11yprobe.qml` | `QtQuick.Window` | 1 xdg-toplevel | **1** |
| `quickshell -p` with `PanelWindow` | Quickshell panel | 1 layer surface | **0** |
| `quickshell -p` with `FloatingWindow` | Quickshell floating | 1 xdg-toplevel | **0** |

Window mapping was confirmed for each from the compositor, not assumed, so no
result is explained by a window that never appeared.

### 6.2 What that establishes

1. **Qt's accessibility bridge on this machine works.** A plain Qt 6.11.2 QML
   window publishes a real tree with a real child object. Everything about the
   build, the bus, the gate and the session is fine.
2. **The break is Quickshell.** Every window Quickshell creates publishes
   nothing.
3. **It is NOT specific to layer-shell surfaces**, which is where both the
   design and the investigations expected it to be. A Quickshell
   `FloatingWindow`, which the compositor confirms is an ordinary xdg-toplevel
   exactly like the working control, publishes zero children just the same. The
   suspect is how Quickshell creates and owns its windows, not the Wayland
   shell protocol they use.
4. **It is not this plugin.** The reproduction contains none of our code. A
   nine-line Quickshell config is enough.
5. **D-GS-3 is not a measurement error.** The original live-pass reading was
   right, even though the connection it read was not recorded and might have
   been the decoy.

### 6.3 The one mechanism that was tested and did not explain it

The investigations found that `QAccessibleApplication::childCount()` filters
top-level windows whose type is `Qt::Popup` (0x9), and measured that an
otherwise identical window with `flags: Qt.Popup` reports 0 while the default
reports 1. I reproduced that result and extended it: `Qt.ToolTip` and
`Qt.FramelessWindowHint` both still report **1**. So the filter is real and
narrow, and whether Quickshell's backing windows trip it is still unproven.
`_backingWindow` is `undefined` in Quickshell 0.3.1, so it cannot be read from
QML; establishing that is a job for someone with the Quickshell source, which is
why the upstream report asks rather than asserts.

## 7. Ownership

I am deliberately hard on this section, because two of the three investigations
concluded "not ours" and both did so from probes that excluded the one layer
under suspicion - a plain `QtQuick.Window` in one case, and
`QAccessible::setActive(true)` in a C++ harness in the other, which bypasses the
only mechanism that can be broken. Worse, docs/STATUS.md:265-271 already said
"It may be an Omarchy or Quickshell defect rather than ours" **before any
probing began**. A conclusion that was never at risk of being wrong is not
evidence for itself.

| Layer | Verdict |
|---|---|
| Qt | Behaving as designed. Gated activation on `org.a11y.Status` is the documented Linux model, and the top-level `Qt::Popup` filter is Qt policy. Nothing to file. |
| Machine configuration | Nothing is misconfigured. No assistive technology is installed, so a dormant bridge is correct. Do **not** recommend setting `QT_LINUX_ACCESSIBILITY_ALWAYS_ON` in the session, and do not file that as an Omarchy bug - the ordinary path (start an AT, gate opens, bridge attaches live) works here. |
| Omarchy | Owns a real, separate defect: zero accessible roles or names in 34,914 lines of shell QML, so the desktop is unusable with a screen reader even once a bridge is live. Also owns the `QT_QPA_PLATFORMTHEME=gtk3` decoy - but the causal mechanism is unproven, so that report is held. |
| Quickshell | Owns one confirmed gap now: `PanelWindow` has no `title`, so a layer-shell window can carry no accessible name (`FloatingWindow` has one). Owns candidate B **if** the settling experiment confirms it. Not exonerated. |
| This project | Owns every item in section 4.6 - three of which are worse with a working tree than without one - and owns the verification practice that let all of this stand for months. **D-GS-3's ownership stays open on our board** until the settling experiment runs. |

Stated plainly: nothing in the *shape* of the plugin's markup causes an empty
tree, and a process containing none of our code reproduces the decoy exactly.
That is real and it is worth knowing. It is not the same as "not our defect",
and it must not be recorded as such yet.

## 8. What this project should change regardless of the root cause

These are independent of where D-GS-3 lands. Items 1-3 are the ones I would ship
first.

**1. Replace the self-confirming tests.** TC-A11Y-01, TC-BAR-11, SRC-A11Y-01 and
SRC-A11Y-05 verify accessibility by grepping the source for the strings the
source was written to contain; they cannot go red. Replace them with an
assertion that observes the real sink. Design constraints, all established
above: it must run on the **wayland** platform (offscreen has no bridge); it can
force a bridge for its own process with `AT_SPI_BUS_ADDRESS` or
`QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1` without touching any global setting; it must
select the connection on `ToolkitName == "Qt"`, never on `Name`; and it must
assert the **Value** as well as the role and name, because a role-and-name check
passes cleanly on the credential leak. Per CLAUDE.md rule 11, mutate one
`Accessible.name` and show it goes red before believing it. Where a full bus
walk is not runnable in CI, a headless `QAccessible` tree dump of the guide's
components is still an enormous improvement over a grep and can run in the same
place `tests/Model.spec.qml` does.

**2. Close the credential exposure (filed as D-A11Y-1, P3, latent).** Three fields publish provider credentials
as their accessible Value: the playlist/EPG URL while revealed, the Xtream
username always, and the Xtream server always. Pick one policy (mask what goes
into `text` and render the revealed characters separately, or set
`Accessible.ignored` while revealed, or an explicit ruling to accept it), apply
it to all three, add **the accessibility bus to CLAUDE.md rule 5's sink list**,
correct the false comment at Guide.qml:3171, and rewrite SRC-A11Y-05 so it
checks the Value.

**3. Give the empty, first-run, loading and error surfaces something to say.**
Today they are a Dialog containing nothing. Compose one name per surface in
`Model.js` so it is unit-testable exactly as `rowAccessibleName` already is
(CLAUDE.md rule 12), attach it to the container, and add the missing rows to
docs/UX.md 7.1: empty and first-run states, the scope and count caption, the
footer hints.

**4. Announce state transitions** with `Accessible.announce()` for the banner,
the form result line and the no-match transient - with the GS5 double-announce
question settled first (open question 6).

**5. Smaller fixes:** move the Guide.qml:2631-2632 literals into `root.copy`;
consider `Accessible.focusable` on rows once question 4 in section 5 can be
answered; reword UX 7.1's per-row promise to acknowledge virtualisation.

**6. Correct the framing in the docs.** docs/UX.md:808-809 says the guide sets a
minimal set "so screen readers and `qmllint` see a coherent surface". On this
machine, as shipped, `qmllint` yes, screen readers never - no claim in UX 7.1 or
UX-SOURCES 7.1 has ever been observed reaching AT-SPI. Say so in both sections,
state the precondition (a live AT-SPI bridge, which requires an assistive
technology to be running), and record it as a known limitation rather than a
delivered feature.

**7. The practice change, which is the real deliverable.** Writing accessibility
rules that nothing has ever verified is not a documentation problem, it is the
same defect class CLAUDE.md constraints 11-13 were written for, and it escaped
because the constraint was never applied to acceptance criteria themselves. I
propose a rule, in the project's own voice:

> An acceptance criterion may not be a grep for the string the implementation
> was written to contain. Every rule is verified either by calling the shipping
> logic or by observing the real sink. A rule that can be verified by neither is
> marked UNVERIFIED in the document that states it, and stays marked until
> something observes it.

Applied retroactively, that single rule would have flagged the accessibility
rows, the privacy row that never reads the leaking property, and the row
announcement that was proven as a string and never as a node - on day one.

## 9. Upstream drafts

Two reports are ready. A third is held.

### Report A (ready to file) - Omarchy: the shell exposes no accessibility information

**What happens.** Omarchy's Quickshell-based shell sets no accessibility roles
or names on any of its surfaces. With an assistive technology running and Qt's
AT-SPI bridge active, the bar, application menu, clipboard picker, emoji picker,
notifications, OSD, lock screen and every panel publish an item tree with no
roles and no names, so a screen-reader user cannot identify or operate any part
of the shell.

**What was expected.** Interactive surfaces carry `Accessible.role` and
`Accessible.name`, so that assistive technology can name them, as Qt Quick
supports out of the box via the `Accessible` attached property.

**How to reproduce.**
1. `/usr/bin/grep -rn 'Accessible\.' /usr/share/omarchy/shell` -> no output
   (exit 1), across 102 `.qml` files and 34,914 lines.
2. Start any assistive technology (or set
   `org.gnome.desktop.interface toolkit-accessibility true`), then inspect the
   shell process on the AT-SPI bus and select its connection whose
   `org.a11y.atspi.Application.ToolkitName` is `Qt`. No named objects.

**Evidence.** The UI kit is hand-built: of 33 components in
`/usr/share/omarchy/shell/Ui/`, only `TextField.qml` and `PanelToolTip.qml`
inherit a Qt Quick Controls type that supplies a default role; `Ui/Button.qml`
is a `BorderSurface` (a Rectangle) plus a MouseArea, so clickable things are not
buttons to AT. `Ui/ConfirmDialog.qml` builds its Cancel and confirm buttons as
bare `BorderSurface` with a `Text` (lines 88, 91, 108) and no accessibility
properties, so a third-party plugin cannot annotate them from outside either.

**Why it is worth fixing at the source.** A plugin can label its own surfaces
and nothing else. Roles and names on the shell's own components - and especially
on the shared `Ui/` kit, where one change covers every consumer - would make
every plugin's surfaces reachable at once.

**System details.** Arch Linux, Hyprland session. quickshell 0.3.1-1,
qt6-base 6.11.2-3, at-spi2-core 2.60.6-1. Shell launched by
`/usr/share/omarchy/bin/omarchy-launch-shell` as
`quickshell -n -p /usr/share/omarchy/shell`.

### Report B (READY TO FILE, and broader than drafted) - Quickshell: no window publishes an accessibility tree

**Part 1, ready now - a panel window cannot carry an accessible name.**
`PanelWindowInterface` exposes no `title` property
(`/usr/lib/qt6/qml/Quickshell/_Window/quickshell-window.qmltypes:134` and
following), while `FloatingWindowInterface` does (:38-47). Qt derives a window's
accessible name from its title, so a full-screen layer-shell surface built with
`PanelWindow` publishes an anonymous window node with no way for the QML author
to name it. Request: a `title` (or an explicit accessible-name) property on
`PanelWindowInterface`, or documentation of the intended alternative.

**Part 2, CONFIRMED on 2026-09-15, and it is not about layer-shell.** The
settling experiment in section 6 ran. Reading the connection whose `ToolkitName`
is `Qt`, and confirming window mapping from the compositor rather than assuming
it, a plain `qml` window reports `ChildCount 1` while BOTH a Quickshell
`PanelWindow` (a layer surface) and a Quickshell `FloatingWindow` (an ordinary
xdg-toplevel) report `0`. The draft below assumed the Wayland shell protocol was
the variable. It is not: the variable is Quickshell itself, and the report
should be filed against all of its windows.

**Part 2, as drafted - the backing window may not be enumerated.**
*What happens:* with a Qt AT-SPI bridge live, the application root of a process
whose only windows are Quickshell layer-shell surfaces reports `ChildCount 0`
and `GetChildren` returns empty, so no QML `Accessible.*` anywhere in those
surfaces is reachable.
*What was expected:* the backing `QQuickWindow` appears as a child of the
application root, and its `contentItem` subtree publishes normally - as it does
for a plain `QtQuick.Window` in the same process, hidden or shown.
*Reproduce:* run a Quickshell config with one `PanelWindow` containing an item
with `Accessible.role` and `Accessible.name`; start an assistive technology (or
`gsettings set org.gnome.desktop.interface toolkit-accessibility true`); on the
AT-SPI bus select the process's connection whose `ToolkitName` is `Qt` (there
may also be a GTK one - see below) and read `ChildCount` on
`/org/a11y/atspi/accessible/root`.
*Evidence to include:* `QAccessibleApplication::childCount()`
(libQt6Gui.so.6.11.2 at 0x616220) calls a helper at 0x615c80 which calls
`QGuiApplication::topLevelWindows()` and compares the window type against
`0x9`; `Qt::Popup == 0x9`. Measured with an otherwise identical hidden window
and a forced bridge: default flags -> root `ChildCount 1`; `flags: Qt.Popup` ->
`ChildCount 0`; `Qt.Tool`, `Qt.ToolTip`, `Qt.SplashScreen`,
`Qt.BypassWindowManagerHint` -> 1. Quickshell imports
`QWindow::setFlag(Qt::WindowType, bool)` and
`QtWaylandClient::QWaylandShellSurface::setWindowFlags(...)`. If the flags on
`ProxyWindowBase::_backingWindow` for a wlr-layer-shell surface include
`Qt::Popup`, that alone explains the symptom.
*Also useful to the maintainer:* in an Omarchy session `QT_QPA_PLATFORMTHEME=gtk3`
puts a second, GTK/ATK connection on the bus for the same pid with zero children
and the same process name, so any diagnosis must select on `ToolkitName`.
*System details:* as Report A.

### Report C - HELD, do not file

"`QT_QPA_PLATFORMTHEME=gtk3` makes every Qt process in the session publish an
empty GTK application root on the accessibility bus." The observation on the
running shell is solid; the causal claim is not. Five bounded headless Qt
processes with libqgtk3, libgtk-3 and libatk-bridge all mapped registered
nothing on the bus. Filing this now would repeat the exact failure mode this
whole investigation is about: a confident claim about host behaviour that was
never actually observed. Reproduce the registration trigger first.

## 10. Open questions for the product owner

**Q1. Does D-GS-3 stay on our board?** ANSWERED by section 6: the cause is outside this project, so the row moves to `accepted, upstream` once Report B is filed, and the link to it goes in the row. It does NOT close: the plugin's own accessibility remains unverifiable until Quickshell changes, and section 8 item 1 is ours regardless.

**Q1 as originally drafted, retained for the reasoning:**
Recommendation: **yes, open, owner unassigned**, until the settling experiment in
section 6 runs. Two investigations concluded "not ours" from probes that
excluded the suspect layer, and the board said the same thing before any probing
started. Moving ownership off now would be recording a preference as a finding.

**Q2. Who runs the settling experiment, and when?** DONE, 2026-09-15, results in section 6. Retained below for what it asked.

**Q2 as originally drafted:**
Recommendation: the display lane, next session, before any accessibility code
changes. It is four commands, needs no restart and no permanent setting, and it
is the difference between a Quickshell bug report and a closed measurement
error. Snapshot and restore the gsettings key per the live-pass rules.

**Q3. The password field: name or `passwordEdit`?**
Qt blanks `Accessible.name` whenever the passwordEdit state is set
(qquickaccessibleattached_p.h:91-96), and the control sets that state from
`echoMode` regardless of QML. docs/UX-SOURCES.md:1165 and :1192 ask for both.
Recommendation: **amend the doc**. Keep `passwordEdit` (it is what actually
protects the value), carry the label in `Accessible.description`, and rewrite
the UX row and docs/QA-SOURCES.md:243 together. Leave Guide.qml:3173 alone until
one offscreen probe settles whether it is inert.

**Q4. The credential Value exposure - which fix?**
Options: (a) keep the masked form in `text` and render revealed characters
separately; (b) `Accessible.ignored` on the field while revealed; (c) accept it
as a ruling. Recommendation: **(a)**, because it also fixes the Xtream username
and server fields, which leak with no reveal at all - and **add the
accessibility bus to CLAUDE.md rule 5's sink list** whichever option is chosen.

**Q5. Do the empty, first-run, loading and error surfaces get accessible names,
and do they get rows in UX 7.1?**
Recommendation: **yes to both**, composed in `Model.js` so they are unit-testable.
As shipped, a first-run user with a working reader is handed an empty dialog.

**Q6. Announcements: where, and does GS5's double-announce concern still apply?**
Recommendation: announce the banner, the form result line and the no-match
transient only, all Polite; do not announce row changes (the row name already
carries the state, and GS5's concern was precisely double-announcement). GS5
stays open until something can be heard.

**Q7. The confirm dialog's two Buttons (UX-SOURCES 7.1), which live in the
host's `Ui/ConfirmDialog.qml`.**
Options: upstream ask, build our own confirm surface, or amend the doc.
Recommendation: **doc amendment plus the upstream ask in Report A** - building a
private confirm dialog to win two accessible names is a poor trade against the
consistency of using the host's component.

**Q8. Adopt the verification rule in section 8.7 as a CLAUDE.md constraint?**
Recommendation: **yes**, as constraint 14, worded as quoted. This is the finding
with the longest reach: the accessibility rules were not wrong, they were
unattached, and nothing in the process could tell the difference.

**Q9. Do we ship an accessibility check that cannot run on a machine with no
assistive technology?**
Recommendation: **yes, but force the bridge inside the test process**
(`AT_SPI_BUS_ADDRESS` or `QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1` on the child only,
wayland platform, never offscreen), so the check asserts rather than skips. A
permanently skipped test is the same decoration as a grep.

**Q10. Do the UX 7.6 performance budgets get re-measured with accessibility
active before accessibility is called done?**
Recommendation: **yes, and make it an explicit gate.** A cursor jump produced on
the order of 40 tree events in a probe, and the guide opens on 10,000 channels.
Nobody has measured what a live bridge costs us.