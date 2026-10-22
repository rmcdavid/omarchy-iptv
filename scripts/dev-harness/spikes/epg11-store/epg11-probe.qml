import QtQuick
import "Model.mjs" as Model

// epg11-probe.qml -- D-EPG-11 (R31e, R31h): what the shell holds from
// epg-now.json, measured on V4 offscreen, under prlimit, over files the
// SHIPPING HELPER wrote. Run it through run-probe.py in this directory
// (README.md), which copies it beside a tree's Model.mjs and model/ in a
// temporary directory; it is never run from the tree itself. The arguments
// come from probe-args.json beside this file (the qml tool takes no argv of
// its own):
//   file   the epg-now.json to read (an asynchronous XHR over file://; the
//          FileView stands aside, its text is a QString the JS string shares)
//   mode   text   hold the file's text alone (case i)
//          parse  hold the text AND Model.parseEpgNow(text).channels, which
//                 is what Service.qml held before this round (ii)
//          store  hold the text AND Model.parseEpgNowStore(text) (iii)
//          time   no hold: time parseEpgNow and parseEpgNowStore over the
//                 file `reps` times each, print ms per call
//          tick   hold the store; then `reps` ticks of 13 rows (epgEntry +
//                 epgFields) and one panel (programmeDetail) over
//                 consecutive ids, print us per tick
// A hold mode prints "PROBE HOLD" once the state is built, keeps it for
// holdMs (default 2500) so the runner can sample /proc/<pid>/status, then
// exits 0. Timing uses Date.now() (ms), so every timed loop repeats enough
// to be read in whole milliseconds.
Item {
  id: root
  width: 10; height: 10
  property var args: ({})
  property string held: ""
  property var heldParse: null
  property var heldStore: null
  property int count: 0

  function env(name, fallback) { return args[name] !== undefined ? args[name] : fallback }

  function fetch(url, then) {
    var xhr = new XMLHttpRequest()
    xhr.onreadystatechange = function () {
      if (xhr.readyState === XMLHttpRequest.DONE) then(xhr.responseText)
    }
    xhr.open("GET", url)
    xhr.send()
  }

  function idsOf(store, n) {
    var out = []
    for (var k in store.index) { out.push(k); if (out.length >= n) break }
    return out
  }

  function run(text) {
    var mode = env("mode", "text")
    var reps = Number(env("reps", 20))
    console.log("PROBE mode=" + mode + " chars=" + text.length + " hasStore=" + (typeof Model.parseEpgNowStore === "function"))
    if (mode === "text") {
      held = text
      count = 0
    } else if (mode === "parse") {
      held = text
      var t0 = Date.now()
      var parsed = Model.parseEpgNow(text)
      var t1 = Date.now()
      heldParse = parsed.channels
      count = Object.keys(parsed.channels).length
      console.log("PROBE parse_ms=" + (t1 - t0) + " entries=" + count)
    } else if (mode === "store") {
      held = text
      var s0 = Date.now()
      var store = Model.parseEpgNowStore(text)
      var s1 = Date.now()
      heldStore = store
      count = store.count
      console.log("PROBE store_ms=" + (s1 - s0) + " entries=" + count + " legacy=" + store.legacy + " sharesText=" + (store.text === text))
    } else if (mode === "time") {
      var pm = -1, sm = -1
      var a0 = Date.now()
      for (var i = 0; i < reps; i++) { var p = Model.parseEpgNow(text); count = Object.keys(p.channels).length }
      pm = (Date.now() - a0) / reps
      if (typeof Model.parseEpgNowStore === "function") {
        var b0 = Date.now()
        for (var j = 0; j < reps; j++) { var st = Model.parseEpgNowStore(text); count = st.count }
        sm = (Date.now() - b0) / reps
      }
      console.log("PROBE time reps=" + reps + " parseEpgNow_ms=" + pm.toFixed(2) + " parseEpgNowStore_ms=" + sm.toFixed(2) + " entries=" + count)
      Qt.exit(0)
      return
    } else if (mode === "tick") {
      held = text
      heldStore = Model.parseEpgNowStore(text)
      count = heldStore.count
      var ids = idsOf(heldStore, 13)
      var nowSec = Number(env("nowSec", 0)) || Math.floor(Date.now() / 1000)
      var channel = { name: "Row", tvgId: ids[0] }
      var sink = 0
      var c0 = Date.now()
      for (var r = 0; r < reps; r++) {
        for (var k = 0; k < ids.length; k++) {
          var f = Model.epgFields(Model.epgEntry(heldStore, ids[k]), nowSec + r)
          sink += f.nowTitle.length
        }
        var d = Model.programmeDetail({ channel: channel, entry: Model.epgEntry(heldStore, ids[0]), nowSec: nowSec + r })
        if (d) sink += d.title.length
      }
      var c1 = Date.now()
      console.log("PROBE tick reps=" + reps + " rows=" + ids.length + " us_per_tick=" + ((c1 - c0) * 1000 / reps).toFixed(1) + " sink=" + sink)
    }
    console.log("PROBE HOLD entries=" + count)
    holdTimer.interval = Number(env("holdMs", 2500))
    holdTimer.start()
  }

  Component.onCompleted: {
    fetch(Qt.resolvedUrl("probe-args.json"), function (argText) {
      args = JSON.parse(argText)
      fetch("file://" + env("file", ""), run)
    })
  }
  Timer {
    id: holdTimer
    onTriggered: { console.log("PROBE DONE"); Qt.exit(0) }
  }
  Timer { interval: 120000; running: true; onTriggered: { console.log("PROBE TIMEOUT"); Qt.exit(2) } }
}
