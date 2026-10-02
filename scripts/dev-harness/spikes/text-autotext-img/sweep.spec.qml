// scripts/dev-harness/spikes/text-autotext-img/sweep.spec.qml -- the
// measurement D-TEXT-1 rests on, kept so "measured" means "re-runnable":
//
//   scripts/dev-harness/spikes/text-autotext-img/run.sh
//
// One Text element per case, each with its own probe path on a logging
// server (probe_server.py) whose port run.sh substitutes for __PORT__ into a
// scratch copy of this file. The question per case is whether laying the
// text out makes the process GET the path. Hosted by qmltestrunner so the
// per-element report (declared format, contentWidth, truncated) reaches the
// console; the fetch itself is read from the server's log, never from here.
// run.sh's header carries the result table.
//
// The report label is "RPT", not "REPORT": the first runner substituted the
// port with a bare `s/PORT/.../` and rewrote every REPORT line to RE<port>.
import QtQuick
import QtTest

TestCase {
  id: tc0
  name: "TextAutoTextImg"
  width: 800; height: 600; when: windowShown
  property string base: "http://127.0.0.1:__PORT__/"

  Column {
    spacing: 4
    // a. the default (AutoText), tag first
    Text { id: ca; text: '<img src="' + tc0.base + 'a.png">BBC One' }
    // b. the default, name first and the tag last
    Text { id: cb; text: 'BBC One <img src="' + tc0.base + 'b.png">' }
    // c. the wall caption's shape: width-bound, elided, centred, off the bus
    Text { id: cc; width: 60; elide: Text.ElideRight; horizontalAlignment: Text.AlignHCenter
           Accessible.ignored: true
           text: '<img src="' + tc0.base + 'c.png">BBC One' }
    // d. never shown: visible false from creation
    Text { id: cd; visible: false; text: '<img src="' + tc0.base + 'd.png">BBC One' }
    // e. the control: PlainText, same string as a
    Text { id: ce; textFormat: Text.PlainText; text: '<img src="' + tc0.base + 'e.png">BBC One' }
    // f. StyledText declared
    Text { id: cf; textFormat: Text.StyledText; text: '<img src="' + tc0.base + 'f.png">BBC One' }
    // g. RichText declared
    Text { id: cg; textFormat: Text.RichText; text: '<img src="' + tc0.base + 'g.png">BBC One' }
    // h. a <b> and no image, with a PlainText twin: does the tag get CONSUMED?
    Text { id: ch; text: 'BBC <b>One</b>' }
    Text { id: chPlain; textFormat: Text.PlainText; text: 'BBC <b>One</b>' }
    // i. entity-escaped tag, with a PlainText twin: is escaping a closure?
    Text { id: ci; text: 'BBC &amp; One &lt;img src="' + tc0.base + 'i.png"&gt;' }
    Text { id: ciPlain; textFormat: Text.PlainText; text: 'BBC &amp; One &lt;img src="' + tc0.base + 'i.png"&gt;' }
  }

  function fmt(f) {
    return f === Text.PlainText ? "PlainText" : f === Text.RichText ? "RichText"
         : f === Text.StyledText ? "StyledText" : f === Text.AutoText ? "AutoText" : String(f)
  }
  function report(label, t) {
    console.warn("RPT " + label + " declared=" + fmt(t.textFormat)
                 + " contentWidth=" + t.contentWidth.toFixed(1)
                 + " truncated=" + t.truncated)
  }
  function test_sweep() {
    // Every element above is laid out at creation; three seconds is many
    // times the loopback round trip, so a request that has not arrived by
    // now is not coming.
    wait(3000)
    report("a", ca); report("b", cb); report("c", cc); report("d", cd); report("e", ce)
    report("f", cf); report("g", cg); report("h", ch); report("hPlain", chPlain)
    report("i", ci); report("iPlain", ciPlain)
    verify(true)
  }
}
