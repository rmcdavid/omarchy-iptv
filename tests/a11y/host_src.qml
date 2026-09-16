import QtQuick
import QtQuick.Window

// Throwaway probe host. Stands in for shell.qml's plugin loader: it injects
// `shell`, `manifest` and `service` exactly as the host contract at
// Guide.qml:30-33 describes, then calls open().
Window {
  id: host
  // Never shown. The qml runner wraps an Item root in its OWN visible
  // window, which maps on the compositor; a Window root with visible:false
  // maps nothing, and Qt enumerates it for accessibility all the same.
  visible: false
  width: 1; height: 1

  // A URL shaped exactly like a provider playlist: userinfo-free, but with
  // the credentials in the query, which is how Xtream-style providers ship.
  property string secretUrl: "http://prov.example:8080/get.php?username=joe&password=s3cret"
  property var sourceFixture: [
    { key: "k1", label: "Provider", kind: "m3u", playlistUrl: secretUrl,
      epgUrl: "", addedAt: 1788000000, lastUsedAt: 1788900000,
      channelCount: 3, groupCount: 2 }
  ]

  property int scaleCount: 3
  property var channelFixture: {
    if (scaleCount <= 3) return [
      { id: "c1", name: "BBC One HD", group: "UK", chno: 101, url: "http://prov.example/live/1" },
      { id: "c2", name: "ITV 1", group: "UK", chno: 102, url: "http://prov.example/live/2" },
      { id: "c3", name: "Sky Sports Main Event", group: "Sport", chno: 401, url: "http://prov.example/live/3" }
    ]
    var out = []
    for (var i = 0; i < scaleCount; i++)
      out.push({ id: "c" + i, name: "Channel " + i, group: "G" + (i % 40),
                 chno: 100 + i, url: "http://prov.example/live/" + i })
    return out
  }

  QtObject {
    id: fakeService
    property var channels: host.channelFixture
    property bool configured: true
    property bool epgConfigured: false
    property bool epgLoaded: false
    property var epgNow: ({})
    property bool epgFailed: false
    property bool epgPending: false
    property string epgReason: ""
    property bool epgRefreshing: false
    property var epgWarnings: []
    property var failedAt: ({})
    property string status: "ready"
    property string statusHost: "prov.example"
    property string statusReason: ""
    property var lastUpdated: 0
    property int nowSec: 1789000000
    property bool playing: false
    property var nowPlaying: null
    property bool playlistFailed: false
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
      return { label: "Provider", playlistUrl: host.secretUrl, epgUrl: "" }
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
      console.warn("PROBE_HOST_READY")
    }
  }

  // Scenario name comes from a plain file so one generated tree serves
  // every scenario without regenerating it.
  function driveScript() {
    var xhr = new XMLHttpRequest()
    xhr.open("GET", Qt.resolvedUrl("scenario.txt"), false)
    xhr.send()
    return xhr.status === 200 || xhr.status === 0 ? String(xhr.responseText).trim() : "guide"
  }

  function drive(item) {
    var which = driveScript()
    console.warn("PROBE_SCENARIO " + which)
    if (which === "sources") {
      item.openSources()
    } else if (which === "editform" || which === "editform_revealed") {
      item.openSources()
      console.warn("PROBE mode after openSources = " + item.mode + " sourceCount=" + item.sourceCount + " sourcesApi=" + item.sourcesApi)
      item.openEditForm()
      console.warn("PROBE mode after openEditForm = " + item.mode)
      if (which === "editform_revealed") item.toggleRevealField("playlist")
    } else if (which === "xtream") {
      item.openSources()
      item.openAddForm()
      item.openXtreamForm()
    } else if (which === "scale10k") {
      host.scaleCount = 10000
    } else if (which === "firstrun") {
      item.service = null
    }
  }

  Timer {
    running: true
    interval: 25000
    onTriggered: { console.warn("PROBE_TIMEBOX"); Qt.exit(0) }
  }
}
