import QtQuick
import QtQuick.Window
import "Model.mjs" as Model

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

  readonly property bool wantChannels: host.scenario !== "firstrun" && host.scenario !== "rvfrsrc"
  readonly property int scaleCount: host.scenario === "scale10k" ? 10000 : 3

  // ---- D-SINK-97 / D-SINK-98 (the Sources scenarios) ----------------------
  // The fake credentials are spelled from `q` and `z` alone, so a run of two
  // of either letter anywhere on the bus is a piece of one. `typedPrefix` is
  // a playlist URL typed up to, not including, its `@`; `typedEpg` a whole
  // credentialed EPG URL typed and so revealed on screen; `storedPlaylist` a
  // URL whose userinfo holds an unencoded `#`, opened in the edit form as a
  // saved value; `credLabel` a label that is a credentialed URL the user
  // pasted.
  readonly property bool sourcesScenario: ["addtyped", "editstored", "sourcesrow", "removelabel",
    "srvtyped", "srvpasted", "editlabel", "labelrow", "labelremove", "probing", "probefail",
    "rbcolon", "rbpass", "rbfeffrow", "rbnbsp", "rbfeffguide", "rbdotted", "rbdottedfail",
    "rvpaste", "rvpaste2", "rvparen"].indexOf(host.scenario) !== -1
  readonly property string typedPrefix: "http://qqqqqq:zzzzzz"
  readonly property string typedEpg: "http://qqqqqq:zzzzzz@cdn.test/xmltv.php?password=zzzzzz"
  readonly property string storedPlaylist: "http://qqqqqq:zz#zz@cdn.test/x"
  readonly property string cleanPlaylist: "http://cdn.test/get.php?username=qqqqqq&password=zzzzzz"
  readonly property string credLabel: "http://qqqqqq:zzzzzz@cdn.test/get.php"
  // ---- round 4b (D-SINK-97, -98, -99, D-A11Y-12) ----
  // `srvTyped` a server URL typed up to its `@`; `srvPasted` one pasted with
  // a `#` in its userinfo; `editLabel` a label whose scheme lost a `/`, with
  // `editPlaylist` a URL edited down to a local path and `editEpg` an
  // ordinary local path; `rowLabel` a saved label with no scheme at all;
  // `typoPlaylist` a URL R32a warns about (its RFC host is the username),
  // submitted so its probe runs (and, in probefail, fails).
  readonly property string srvTyped: "http://qqqqqq:zzzzzz"
  readonly property string srvPasted: "http://qqqqqq:zz#zz@cdn.test:8080/get.php"
  readonly property string editLabel: "http:/qqqqqq:zzzzzz@cdn.test/get.php"
  readonly property string editPlaylist: "/cdn.test/live/qqqqqq/zzzzzz/1.ts"
  readonly property string editEpg: "/home/u/epg.xml"
  readonly property string rowLabel: "qqqqqq:zzzzzz@cdn.test"
  readonly property string typoPlaylist: "http://qqqqqq#zzzzzz@cdn.test/x"
  // ---- round 4c (D-SINK-98 E1/E2, D-SINK-99 E4, D-A11Y-12 E6) ----
  // `colonTyped` typed key by key into the Label field and then one
  // Backspace on its `:`; `passPasted` pasted and then the range before
  // `password=` deleted; `feffLabel` and `lineLabel` stored labels holding a
  // U+FEFF, and a U+2028 and a U+00A0, inside the token; `dottedPlaylist` a
  // dotted username before a later `@`, submitted so its probe runs.
  readonly property string colonTyped: "qqqqqq:zzzzzz@cdn.test"
  readonly property string colonEdited: "qqqqqqzzzzzz@cdn.test"
  readonly property string passPasted: "cdn.test/get.php?username=qqqqqq&password=zzzzzz"
  readonly property string passEdited: "password=zzzzzz"
  readonly property string feffLabel: "qqqqqq:zzzzzz" + String.fromCharCode(0xfeff) + "@cdn.test"
  readonly property string lineLabel: "qqqqqq:" + String.fromCharCode(0x2028) + "zzzzzz" + String.fromCharCode(0xa0) + "@cdn.test"
  readonly property string dottedPlaylist: "http://qqqqqq.test:12#zzzzzz@cdn.test/x"
  // ---- round 4d (D-SINK-98 F1/F4, D-A11Y-12 F5/F7), the reviews' scenarios ----
  // `pasteNbsp` and `pasteSpace` whole credentials pasted into the Label
  // field that no stored clause reads (a U+00A0 at the scheme join and a
  // space in the password; a space in the password with no path);
  // `parenLabel` a stored label whose host/path sits inside parentheses;
  // `frPlaylist` and `frEpg` the first-run form's two fields, filled before
  // Sources is opened from its saved-sources link.
  readonly property string pasteNbsp: "http" + String.fromCharCode(0xa0) + "://qqqqqq:zz zz@cdn.test/x"
  readonly property string pasteSpace: "qqqqqq:zz zz@cdn.test"
  readonly property string parenLabel: "Provider (cdn.test:8080/qqqqqq/zzzzzz)"
  readonly property string frPlaylist: "http://qqqqqq:12/zzzzzz@cdn.test/get.php"
  readonly property string frEpg: "http://qqqqqq:zzzzzz@cdn.test/xmltv.php"
  // The record the service would hold, and its view built by the shipping
  // Model.sourceView, so the row reads what the service would hand it. Its
  // URL's RFC host is cdn.test, so what the rows grade is the label. The `#`
  // URL is handed to the EDIT FORM alone (sourceForEdit, below): the state
  // reader drops a record holding it (an invalid url), so no saved row can
  // carry one, and the form's field is the sink the scenario is about.
  readonly property var labelRecord: ({
    key: "k9", url: host.cleanPlaylist,
    epgUrl: "", kind: "http",
    label: (host.scenario === "labelrow" || host.scenario === "labelremove") ? host.rowLabel
      : (host.scenario === "rbfeffrow" || host.scenario === "rbfeffguide") ? host.feffLabel
      : host.scenario === "rbnbsp" ? host.lineLabel
      : host.scenario === "rvparen" ? host.parenLabel : host.credLabel,
    labelCustom: true, origin: "guide",
    addedAt: 1788000000, lastUsed: 1788900000, fetchedAt: 1788900000, channelCount: 3, groupCount: 2
  })

  property var sourceFixture: host.sourcesScenario
    ? [Model.sourceView(host.labelRecord, "k9", 1789000000, "")]
    : [
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
    property string activeSourceId: host.sourcesScenario ? "k9" : ""
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
    // The probing scenarios' add is accepted, so the form's probe starts.
    function addSource() { return ["probing", "probefail", "rbdotted", "rbdottedfail"].indexOf(host.scenario) !== -1 ? { ok: true, id: "k10" } : undefined }
    function removeSource() {}
    function updateSource() {}
    function switchSource() {}
    function retrySource() {}
    function cancelProbe() {}
    function sourceForEdit(id) {
      if (host.scenario === "editlabel")
        return { label: host.editLabel, epgUrl: host.editEpg, playlistUrl: "http://cdn.test/live/qqqqqq/zzzzzz/1.ts" }
      if (host.sourcesScenario)
        return { label: host.labelRecord.label, epgUrl: host.labelRecord.epgUrl,
                 playlistUrl: host.scenario === "editstored" ? host.storedPlaylist : host.labelRecord.url }
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
      // D-SINK-99: whether the label placeholder is the withheld token, and
      // whether it holds a run of the fixture credential -- flags, never the
      // text, as below.
      formProbing: item.formProbing,
      placeholderWithheld: item.formActive ? item.fieldPlaceholder("label") === Model.HOST_WITHHELD : null,
      placeholderHasRun: item.formActive ? /[qz]{2,}/.test(item.fieldPlaceholder("label")) : null,
      // D-SINK-98 round 4c (E1): whether the label field is held.
      labelHeld: item.formActive ? item.form.labelHeld === true : null,
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
    if (host.scenario === "addtyped") expected = { playlist: host.typedPrefix, epg: host.typedEpg }
    else if (host.scenario === "editstored") expected = { label: host.credLabel, playlist: host.storedPlaylist }
    else if (host.scenario === "srvtyped") expected = { server: host.srvTyped }
    else if (host.scenario === "srvpasted") expected = { server: host.srvPasted }
    else if (host.scenario === "editlabel") expected = { label: host.editLabel, playlist: host.editPlaylist, epg: host.editEpg }
    else if (host.scenario === "probing" || host.scenario === "probefail") expected = { playlist: host.typoPlaylist }
    else if (host.scenario === "rbcolon") expected = { label: host.colonEdited }
    else if (host.scenario === "rbpass") expected = { label: host.passEdited }
    else if (host.scenario === "rbdotted" || host.scenario === "rbdottedfail") expected = { playlist: host.dottedPlaylist }
    else if (host.scenario === "rvpaste") expected = { label: host.pasteNbsp }
    else if (host.scenario === "rvpaste2") expected = { label: host.pasteSpace }
    else if (host.scenario === "rvfrsrc") expected = { playlist: host.frPlaylist, epg: host.frEpg }
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
    } else if (which === "addtyped") {
      // D-SINK-97: typed by hand (typed: true, so revealed on screen), the
      // playlist stopped before its `@` and the EPG whole.
      item.openSources()
      item.openAddForm()
      item.setFieldValue("playlist", host.typedPrefix, true)
      item.setFieldValue("epg", host.typedEpg, true)
    } else if (which === "editstored") {
      // D-SINK-97 / D-SINK-98: the edit form over the saved source, its
      // playlist's userinfo holding a `#` and its label a credentialed URL.
      item.openSources()
      item.openEditForm()
    } else if (which === "sourcesrow" || which === "labelrow") {
      item.openSources()
    } else if (which === "removelabel" || which === "labelremove") {
      item.openSources()
      item.startRemove()
    } else if (which === "srvtyped" || which === "srvpasted") {
      // Round 4b: the server typed by hand (typed: true) or pasted (false).
      item.openSources()
      item.openXtreamForm()
      item.setFieldValue("server", which === "srvtyped" ? host.srvTyped : host.srvPasted, which === "srvtyped")
    } else if (which === "editlabel") {
      // Round 4b: the edit form over the label, its playlist edited (typed)
      // down to a local path that holds the credential.
      item.openSources()
      item.openEditForm()
      item.setFieldValue("playlist", host.editPlaylist, true)
    } else if (which === "probing" || which === "probefail") {
      // D-SINK-99: the warned URL typed and submitted; probefail then hears
      // the probe fail with no host of its own, so the form's is named.
      item.openSources()
      item.openAddForm()
      item.setFieldValue("playlist", host.typoPlaylist, true)
      item.submitForm()
      if (which === "probefail") item.onProbeFinished({ ok: false, id: "k10", reason: "Could not resolve host", host: "" })
    } else if (which === "rbcolon" || which === "rbpass") {
      // Round 4c (E1): the Label field through the shipping key and paste
      // paths -- handleFormKey with the events a key press delivers, and
      // pasteFromProcess with the clipboard's answer.
      item.openSources()
      item.openAddForm()
      item.fieldFocused("label")
      var noMatch = function () { return false }
      if (which === "rbcolon") {
        for (var c = 0; c < host.colonTyped.length; c++)
          item.handleFormKey({ key: 0, modifiers: Qt.NoModifier, text: host.colonTyped.charAt(c), matches: noMatch })
        item.fieldItem("label").cursorPosition = host.colonTyped.indexOf(":") + 1
        item.handleFormKey({ key: Qt.Key_Backspace, modifiers: Qt.NoModifier, text: "", matches: noMatch })
      } else {
        item.pasteFromProcess(host.passPasted)
        item.fieldItem("label").select(0, host.passPasted.indexOf("password="))
        item.handleFormKey({ key: Qt.Key_Delete, modifiers: Qt.NoModifier, text: "", matches: noMatch })
      }
    } else if (which === "rbfeffrow" || which === "rbnbsp") {
      // Round 4c (E2): a stored label holding an invisible or a space
      // character inside its token -- its row, the row's buttons and the
      // remove dialog at once.
      item.openSources()
      item.startRemove()
    } else if (which === "rbdotted" || which === "rbdottedfail") {
      // Round 4c (E4): a dotted username before a later `@`, submitted.
      item.openSources()
      item.openAddForm()
      item.setFieldValue("playlist", host.dottedPlaylist, true)
      item.submitForm()
      if (which === "rbdottedfail") item.onProbeFinished({ ok: false, id: "k10", reason: "Could not resolve host", host: "" })
    } else if (which === "rvpaste" || which === "rvpaste2") {
      // Round 4d (F1, the still-on-bus review's scenarios): a whole
      // credential pasted into an empty Label field through the shipping
      // paste path, no typed prefix.
      item.openSources()
      item.openAddForm()
      item.fieldFocused("label")
      item.pasteFromProcess(which === "rvpaste" ? host.pasteNbsp : host.pasteSpace)
    } else if (which === "rvparen") {
      // Round 4d (F4 f): the stored label in parentheses -- its row, the
      // row's buttons and the remove dialog at once.
      item.openSources()
      item.startRemove()
    } else if (which === "rvfrsrc") {
      // Round 4d (F5): the first-run form's fields filled, then Sources
      // opened as its saved-sources link opens it; the form survives in the
      // guide state behind Sources.
      item.setFieldValue("playlist", host.frPlaylist, false)
      item.setFieldValue("epg", host.frEpg, true)
      item.openSources()
    } else if (which === "wall") {
      // Round 4d (F7): the wall view shown, as its key shows it.
      item.toggleWall()
    } else if (which === "query") {
      item.setQuery("bbc")
    } else if (which === "querynomatch") {
      item.setQuery("zzzznothing")
    }
    // rbfeffguide is the plain guide over the stored label (round 4c, E6).
    // firstrun, banner and scale10k need no driving: the fixture above is
    // the state, which is the point -- a scenario poked into place after
    // open() is not the state the user arrives in.
  }

  Timer { running: true; interval: 25000; onTriggered: { console.warn("PROBE_TIMEBOX"); Qt.exit(0) } }
}
