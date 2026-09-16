import QtQuick
import QtQuick.Window
import "Model.js" as Model

// Lane 2 guide host: the states the prototype's host never reached.
//
// Same contract as host_src.qml (it injects `shell`, `manifest` and
// `service` exactly as Guide.qml:30-33 describes and calls open()), but the
// fixture is parameterised by scenario so first run, the banner, an active
// query and 10,000 channels each get the service state that actually
// produces them, instead of being poked at after the fact.
//
// It loads the SAME GuideProbe.qml the shared make_tree.py generates. The
// fidelity of that copy against the repo's Guide.qml is not this file's
// claim to make.
Window {
  id: host
  visible: false
  width: 1
  height: 1

  function scenarioName() {
    var xhr = new XMLHttpRequest()
    xhr.open("GET", Qt.resolvedUrl("scenario2.txt"), false)
    xhr.send()
    return (xhr.status === 200 || xhr.status === 0) ? String(xhr.responseText).trim() : "query"
  }
  property string scenario: host.scenarioName()

  // ---- credential fixture -------------------------------------------------
  // Three tokens that cannot be confused with one another, so a leak names
  // the field it came from. Decision 7's case is the first one: a full
  // provider login string pasted into the Xtream SERVER field, which has no
  // mask and no eye button (Model.js:4491 URL_FIELDS is ["playlist","epg"],
  // so fieldMaskable is false for "server" and "username" forever).
  readonly property string serverPaste: "http://prov.example:8080/get.php?username=joe&password=SRVTOKEN1"
  readonly property string usernameValue: "USERTOKEN2"
  readonly property string passwordValue: "PASSTOKEN3"
  readonly property string playlistUrl: "http://prov.example:8080/get.php?username=joe&password=PLAYTOKEN4"

  readonly property bool wantChannels: host.scenario !== "firstrun"
  readonly property int scaleCount: host.scenario === "scale10k" ? 10000 : 3

  property var sourceFixture: [
    { key: "k1", label: "Provider", kind: "m3u", playlistUrl: host.playlistUrl,
      epgUrl: "", addedAt: 1788000000, lastUsedAt: 1788900000,
      channelCount: host.scaleCount, groupCount: 2 }
  ]

  readonly property var channelFixture: {
    if (!host.wantChannels) return []
    if (host.scaleCount <= 3) return [
      { id: "c1", name: "BBC One HD", group: "UK", chno: 101, url: "http://prov.example/live/1" },
      { id: "c2", name: "ITV 1", group: "UK", chno: 102, url: "http://prov.example/live/2" },
      { id: "c3", name: "Sky Sports Main Event", group: "Sport", chno: 401, url: "http://prov.example/live/3" }
    ]
    var out = []
    for (var i = 0; i < host.scaleCount; i++)
      out.push({ id: "c" + i, name: "Channel " + i, group: "G" + (i % 40),
                 chno: 100 + i, url: "http://prov.example/live/" + i })
    return out
  }

  QtObject {
    id: fakeService
    property var channels: host.channelFixture
    // First run is "a service that loaded and has no playlist", which is
    // what Guide.open() turns into the first-run form (Guide.qml:583).
    property bool configured: host.wantChannels
    property bool epgConfigured: false
    property bool epgLoaded: false
    property var epgNow: ({})
    property bool epgFailed: false
    property bool epgPending: false
    property string epgReason: ""
    property bool epgRefreshing: false
    property var epgWarnings: []
    property var failedAt: ({})
    // The banner scenario: a refresh that failed while a cache is still
    // rendered is bannerKind "playlistError" (Guide.qml:463-468).
    property string status: host.scenario === "banner" ? "cached" : "ready"
    property string statusHost: "prov.example"
    property string statusReason: host.scenario === "banner" ? "connection refused" : ""
    property var lastUpdated: host.scenario === "banner" ? "8 Sep 14:02" : 0
    property bool playlistFailed: host.scenario === "banner"
    property int nowSec: 1789000000
    property bool playing: false
    property var nowPlaying: null
    property var playlistWarnings: []
    property bool pipAvailable: false
    property bool pipOn: false
    property bool probing: false
    property string probingId: ""
    property bool refreshing: false
    property bool switching: false
    property var settingsInvalid: null
    property var sources: host.sourceFixture
    property string activeSourceId: ""
    property string sourceHost: "prov.example"
    property var chnoIndex: null
    property int numberEntryMs: 1200
    property var userState: ({ favorites: ["c2"], recents: [] })
    function play() {}
    function stop() {}
    function refresh() {}
    function toggleFavorite() {}
    function togglePip() {}
    function removeRecent() {}
    function requestClipboard() {}
    function addSource() {}
    function removeSource() {}
    function updateSource() {}
    function switchSource() {}
    function retrySource() {}
    function cancelProbe() {}
    function sourceForEdit(id) {
      return { label: "Provider", playlistUrl: host.playlistUrl, epgUrl: "" }
    }
    function buildXtreamSource() { return null }
  }

  QtObject {
    id: fakeShell
    function hide(id) {}
    function serviceFor(id) { return fakeService }
  }

  Loader {
    id: guideLoader
    source: "GuideProbe.qml"
    onStatusChanged: {
      if (status === Loader.Error) { console.warn("PROBE_LOADER_ERROR"); Qt.exit(3) }
    }
    onLoaded: {
      item.manifest = { id: "io.github.rmcdavid.iptv" }
      item.shell = fakeShell
      item.service = fakeService
      item.open(JSON.stringify({ scope: "all" }))
      host.drive(item)
      console.warn("PROBE_SCENARIO " + host.scenario)
      host.readback(item, "EARLY")
      // The LATE readback is the one that matters. A remedy that rebinds a
      // field's text to a masked rendering feeds that rendering back through
      // onTextChanged into the stored value; it looks clean on the bus and
      // has silently replaced what the user typed. EARLY != LATE is that
      // bug, and the checker fails on it rather than reporting "no secret
      // found, 0 failures".
      lateTimer.start()
    }
  }

  Timer {
    id: lateTimer
    interval: 900
    repeat: false
    onTriggered: {
      host.readback(guideLoader.item, "LATE")
      console.warn("PROBE_READBACK_FINAL")
    }
  }

  function readback(item, tag) {
    if (!item) return
    var out = {
      tag: tag,
      scenario: host.scenario,
      mode: item.mode,
      query: item.query,
      rowCount: item.rowCount,
      resultTotal: item.resultTotal,
      bannerKind: item.bannerKind,
      bannerText: item.bannerText,
      firstRunHead: item.firstRunHead,
      formAccessibleName: item.formAccessibleName,
      footerStatusText: item.footerStatusText,
      // CLAUDE.md rule 5 applies to this harness's own log too. The checker
      // needs to know the stored value is UNCHANGED, not what it is, so the
      // readback publishes a fingerprint (Model.sourceKey, the shipping
      // fnv1a32) plus a match against the value this host itself typed --
      // never the value. A lane debugging with a real provider URL does not
      // leave it in plaintext on disk.
      digest: {},
      intact: {},
      length: {},
      maskable: {},
      masked: {}
    }
    var expected = {
      server: host.serverPaste,
      username: host.usernameValue,
      password: host.passwordValue,
      playlist: host.playlistUrl
    }
    var ids = item.formFieldIds || []
    for (var i = 0; i < ids.length; i++) {
      var id = ids[i]
      var value = item.formValue(id)
      out.digest[id] = Model.sourceKey(value)
      out.length[id] = value.length
      if (expected[id] !== undefined) out.intact[id] = (value === expected[id])
      out.maskable[id] = item.fieldMaskable(id)
      out.masked[id] = item.fieldMasked(id)
    }
    console.warn("PROBE_READBACK " + JSON.stringify(out))
  }

  function drive(item) {
    var which = host.scenario
    console.warn("PROBE_DRIVE " + which)
    if (which === "xtream") {
      item.openSources()
      item.openXtreamForm()
      // No reveal, no eye button, no user action beyond typing: this is the
      // unconsented case in decision 7. setFieldValue is the shipping
      // function the TextField's own onTextChanged path calls.
      item.setFieldValue("server", host.serverPaste, true)
      item.setFieldValue("username", host.usernameValue, true)
      item.setFieldValue("password", host.passwordValue, true)
    } else if (which === "query") {
      item.setQuery("bbc")
    } else if (which === "querynomatch") {
      item.setQuery("zzzznothing")
    }
    // firstrun, banner and scale10k need no driving: the fixture above is
    // the state, which is the point -- a scenario poked into place after
    // open() is not the state the user arrives in.
  }

  Timer { running: true; interval: 25000; onTriggered: { console.warn("PROBE_TIMEBOX"); Qt.exit(0) } }
}
