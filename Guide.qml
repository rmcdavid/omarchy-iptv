import Quickshell
import Quickshell.Wayland
import QtQuick
import qs.Commons
import qs.Ui
import "Model.js" as Model

// Guide.qml -- fullscreen channel guide overlay for io.github.rmcdavid.iptv
// (manifest kind "overlay", keepLoaded so the layer-shell window stays
// mounted between summons and opens in well under 150 ms).
//
// Implements docs/UX.md: scrim + centered card on the [menu] surface, a
// synthetic search line (no TextField), two keyboard modes (search on open;
// Tab or "/" for list mode with j/k/h/l, f, x, s, r, Space, Enter, Esc),
// a left group column (Recent / Favorites / All / GROUPS), rows with EPG
// now/next + progress hairline, banners, empty states and a footer with
// mode-aware hints. Pure decisions live in Model.js (ranking, scope rules,
// the mode state machine); this file only renders and dispatches.
//
// M2-01 Sources (docs/UX-SOURCES.md under the rulings of
// docs/ARCHITECTURE-SOURCES.md): the first-run empty state carries the
// playlist / EPG input, a pinned `Sources` row under the group column and
// the `o` key open the Sources list (switch / add / edit / remove with a
// ConfirmDialog), and the add / edit / Xtream forms are qs.Ui TextFields
// with the PanelKeyCatcher blocked while a field has focus. URLs exist on
// screen only inside a form field, masked (Model.maskUrl) until revealed.
// Every service access for the Sources API is guarded so the guide still
// loads against a service that lacks it.
//
// Host contract (shell.qml panel loader): `shell`, `manifest` and `service`
// are injected after load; open(payloadJson)/close()/toggle() are called by
// summon/hide/toggle. Dismiss through shell.hide(manifest.id) so the host's
// open-state stays in sync (same as Emojis.qml).
//
// Payload (JSON string) keys, all optional:
//   {"query": "bbc", "scope": "favorites" | "all" | "recent" | "g:UK", "group": "UK"}
Item {
  id: root

  property var shell: null
  property var manifest: null
  property var service: null

  readonly property string pluginId: manifest && manifest.id ? String(manifest.id) : "io.github.rmcdavid.iptv"
  property bool opened: false

  // ---- guide state (R8). `guide` is the pure state machine object from
  // Model.js; replaced on every transition so bindings notice.
  property var guide: Model.guideState(Model.SCOPE_ALL)
  readonly property string mode: guide.mode
  readonly property bool searchMode: mode === "search"
  readonly property bool listMode: mode === "list"
  readonly property bool guideMode: searchMode || listMode
  readonly property bool inSources: mode === "sources"
  readonly property bool formActive: mode === "sourceEdit" || mode === "sourceXtream"
  readonly property bool confirmOpen: mode === "confirmRemove"
  // The PanelKeyCatcher is live in the two list-like modes only; search
  // mode, the forms and the confirm dialog block it (UX-SOURCES 2).
  readonly property bool catcherLive: listMode || inSources
  readonly property string query: guide.query
  readonly property string scopeId: guide.scopeId
  readonly property string effectiveScope: Model.effectiveScope(scopeId, query)
  readonly property bool hasQuery: Model.tokenize(query).length > 0
  property int cursorIndex: 0
  property int resultTotal: 0
  // Number of rows in currentRows; the channel ListView's integer model, so
  // an 11k-channel scope costs one property write and the view instantiates
  // only the visible delegates (D-LIVE-01, PERF-02).
  property int rowCount: 0
  property bool truncated: false
  property var scopeList: []
  property string groupSignature: ""
  // The column only needs recomputing when channels or the user state
  // change, not on every keystroke.
  property bool groupsDirty: true
  property string transientText: ""
  property bool enterPending: false
  // Set when a list-mode key switches to search mode: the same key event
  // then propagates to the search handler and must not become query text.
  property bool swallowKey: false
  property int columnWheel: 0
  readonly property int maxRows: Model.MAX_ROWS_DEFAULT

  // ---- channel numbers (M2-03). Root-local, like cursorIndex and
  // transientText, and NOT inside root.guide: Model.onEscape is unchanged,
  // handleEscape checks the buffer here and returns before delegating (2.6).
  //
  // scopeId / query / cursorIndex inside the entry are the snapshot taken
  // when the buffer went from empty to one character. Esc and Backspace on
  // the last character both restore it.
  property var numberEntry: Model.numberEntry()
  property var numberResolution: Model.resolveChno(null, "", -1)
  // The name of the row the preview landed on, for the "(1 of 2)" footer.
  property string numberTargetName: ""
  readonly property bool numberEntryActive: root.numberEntry !== null && root.numberEntry.active === true
  readonly property string numberBuffer: root.numberEntry !== null ? String(root.numberEntry.buffer) : ""
  // Guarded exactly as the Sources API is. Service.qml publishes chnoIndex,
  // and this is the compatibility path for a service that does not: the
  // harness stages an older plugin tree through OMARCHY_IPTV_PLUGIN_ROOT so a
  // scenario can be seen failing against it (CLAUDE.md rule 10), and an
  // undefined read must never invent a value. It builds the same index with
  // the same Model function, once per channel-set change, never per key.
  readonly property bool chnoApi: root.serviceReady && root.service.chnoIndex !== undefined && root.service.chnoIndex !== null
  property var fallbackChnoIndex: Model.buildChnoIndex(null)
  readonly property var chnoIndex: root.chnoApi ? root.service.chnoIndex : root.fallbackChnoIndex
  readonly property bool hasNumbers: root.chnoIndex !== null && root.chnoIndex.hasNumbers === true
  readonly property int numberWidth: root.hasNumbers ? Style.space(Model.chnoColumnUnits(root.chnoIndex.maxLabelLen)) : 0
  // CN2: a setting, not a constant, because the timeout is an accessibility
  // matter. The fallback matches the manifest default.
  readonly property int numberEntryMs: root.serviceReady && root.service.numberEntryMs !== undefined && root.service.numberEntryMs !== null
    ? Model.clampSetting("numberEntryMs", root.service.numberEntryMs)
    : Model.SETTING_RANGES.numberEntryMs.def
  readonly property string cursorChannelId: {
    var row = root.rowAt(root.cursorIndex)
    return row ? Model.channelId(row) : ""
  }

  // ---- microcopy, in one place (UX.md 5.9, section 6). Strings shared with
  // the bar and notifications live in Model.js (footerStatus, footerHints,
  // barTooltip, notifyArgv, rowDetail, scopeLabel, noMatchesTitle).
  readonly property var copy: ({
    searchPlaceholder: "Search channels" + Model.ELLIPSIS,
    serviceTitle: "Service not loaded",
    serviceProse: "Run omarchy restart shell",
    unconfiguredTitle: "No playlist configured",
    unconfiguredProse: "Set your M3U URL or path, then press r to load it:",
    unconfiguredCommand: "omarchy bar set " + root.pluginId + " playlistUrl <url>",
    unconfiguredEpg: "Optional EPG:  omarchy bar set " + root.pluginId + " epgUrl <url>",
    unconfiguredWhere: "Settings live in ~/.config/omarchy/shell.json (entry " + root.pluginId + ")",
    loadingTitle: "Loading playlist" + Model.ELLIPSIS,
    loadingFrom: "Fetching from ",
    loadingProse: "Fetching playlist",
    errorTitle: "Playlist failed to load",
    errorCheck: "check playlistUrl",
    emptyPlaylistTitle: "Playlist has no channels",
    emptyPlaylistProse: "Parsed 0 channels from ",
    emptyPlaylistCheck: "check the URL points at an M3U",
    noFavoritesTitle: "No favorites yet",
    noFavoritesProse: "Press f on any channel to pin it here",
    noMatchesAll: "Esc clears the search",
    noMatchesGroup: "h/l other groups" + Model.SEP + "Home for All",
    emptyScopeTitle: "No channels in ",
    bannerPlaylist: "Playlist refresh failed (",
    bannerCached: "showing cached copy",
    bannerRetry: "r retry",
    bannerEpg: "Guide data unavailable (",
    bannerEpgStill: "channels still work",
    bannerEpgPending: "Guide data loading" + Model.ELLIPSIS,
    transientRefreshing: "Refreshing" + Model.ELLIPSIS,
    transientRefreshed: "Refreshed",
    transientUnconfigured: "Set a playlist first",
    transientStopped: "Stopped",
    transientFavAdded: "Added to Favorites",
    transientFavRemoved: "Removed from Favorites",
    transientRecentRemoved: "Removed from Recent",
    transientCopied: "Copied",
    accessibleCard: "IPTV guide",
    accessibleSearch: "Search channels",
    accessibleGroups: "Groups",
    accessibleChannels: "Channels in ",
    // ---- Sources (UX-SOURCES.md 5.1); codes, transients and row strings
    // come from Model.js (sourceErrorMessage, sourceTransient, sourceDetail).
    sourcesTitle: "Sources",
    addSourceTitle: "Add source",
    editSourceTitle: "Edit source",
    xtreamTitle: "Add Xtream login",
    firstRunProse: "Paste or type your M3U URL or path, then press Enter",
    firstRunTerminal: "Or from a terminal:  omarchy bar set " + root.pluginId + " playlistUrl <url>",
    fieldLabel: "Label",
    fieldPlaylist: "Playlist",
    fieldEpg: "EPG",
    fieldServer: "Server",
    fieldUsername: "Username",
    fieldPassword: "Password",
    placeholderOptional: "optional",
    placeholderPlaylist: "https://host/playlist.m3u or /path/to/list.m3u",
    placeholderEpg: "optional" + Model.SEP + "XMLTV URL, .xml or .xml.gz",
    placeholderServer: "http://host:port",
    linkXtream: "Use Xtream login instead",
    linkSaved: "Saved sources",
    buttonLoad: "Load",
    buttonSave: "Save",
    buttonCancel: "Cancel",
    buttonRemove: "Remove",
    xtreamProse: "Builds the get.php (m3u_plus, ts) and xmltv.php URLs. The password is stored in those URLs and never shown again.",
    rowAdd: "Add source",
    rowXtream: "Add Xtream login",
    tooltipShow: "Show query" + Model.SEP + Model.SOURCE_KEYS.reveal,
    tooltipHide: "Hide query" + Model.SEP + Model.SOURCE_KEYS.reveal,
    tooltipEdit: "Edit",
    tooltipRemove: "Remove",
    accessibleSources: "Sources",
    accessibleFirstRun: "Set up a playlist",
    accessibleLabel: "Label, optional",
    accessiblePlaylist: "Playlist URL or path",
    accessibleEpg: "EPG URL, optional",
    accessibleServer: "Server URL",
    accessibleUsername: "Username",
    accessiblePassword: "Password",
    accessibleShow: "Show query",
    accessibleHide: "Hide query",
    accessibleSaved: "Saved sources, "
  })

  // ---- timing constants, in one place (UX.md 5.9)
  readonly property int bannerFadeMs: 140
  readonly property int transientMs: 3000
  readonly property int filterDebounceMs: 40
  readonly property int filterDebounceThreshold: 2000

  // ---- theme tokens: shares the [menu] surface with the clipboard and
  // emoji pickers (PRODUCT.md decision 7). No literal colors.
  property color background: Color.menu.background
  property color foreground: Color.menu.text
  property color border: Color.menu.border
  property var borderSpec: Border.surfaceSpec("menu", "border", border, Math.max(1, Style.space(2)))
  property var selectedBorderSpec: Border.surfaceSpec("menu", "selected-border", Color.menu.selectedBorder, 0)
  property var noBorderSpec: Border.none()
  property color scrim: Color.menu.scrim
  property color selectedBackground: Color.menu.selectedBackground
  property color selectedText: Color.menu.selectedText
  property color accent: Color.accent
  property color urgent: Color.urgent
  readonly property int cornerRadius: Style.cornerRadius
  property string fontFamily: Style.font.menuFamily

  // ---- metrics (UX.md 5.1 / 5.2)
  property int contentMargin: Style.spacing.panelPadding
  property int contentSpacing: Style.spacing.md
  property int headerHeight: Math.max(Style.space(34), Style.font.title + Style.spacing.controlPaddingY * 2)
  property int bannerHeight: Style.space(28)
  property int columnWidth: Style.space(200)
  property int groupEntryHeight: Math.max(Style.space(32), Style.font.body + Style.spacing.controlPaddingY * 2)
  property int detailRowHeight: Math.max(Style.space(52), Style.font.title + Style.font.bodySmall + Style.space(2) + Style.spacing.rowPaddingX * 2)
  property int singleRowHeight: Math.max(Style.space(38), Style.font.title + Style.spacing.rowPaddingX * 2)
  readonly property int rowHeight: rowsHaveDetail ? detailRowHeight : singleRowHeight
  property int rowSpacing: Style.space(4)
  property int footerHeight: Math.max(Style.space(20), Style.font.caption + Style.space(6))
  property int leadWidth: Style.space(24)
  property int trailWidth: Style.space(20)
  property int cardWidth: Math.min(Style.space(960), panel.width - Style.gapsOut * 2)
  property int cardHeight: Math.min(Style.space(620), panel.height - Style.gapsOut * 2)
  readonly property bool narrow: cardWidth < Style.space(720)

  // ---- derived from the service
  readonly property bool serviceReady: service !== null
  readonly property bool configured: serviceReady && service.configured === true
  // D-LIVE-19: never `service.channels.length` directly. The body renders
  // one surface at a time and Model.guideSurface decides which; an
  // unconfigured guide has no channels, no column and no counts even if the
  // service is still holding the previous source's list for a frame.
  readonly property bool hasChannels: surface.hasChannels
  readonly property bool epgConfigured: serviceReady && service.epgConfigured === true
  readonly property bool epgLoaded: serviceReady && service.epgLoaded === true
  readonly property string serviceStatus: serviceReady ? String(service.status) : "ready"
  readonly property string playingId: serviceReady && service.playing && service.nowPlaying ? String(service.nowPlaying.id) : ""
  readonly property string playingName: serviceReady && service.playing && service.nowPlaying ? String(service.nowPlaying.name) : ""
  readonly property int nowSec: serviceReady ? service.nowSec : Math.floor(Date.now() / 1000)
  readonly property bool showColumn: surface.showColumn
  readonly property bool scopeIsGroup: Model.isGroupScope(effectiveScope)

  // ---- Sources (M2-01). Every access is guarded: the service may lack the
  // Sources API (the harness before Lane 2 merges) and the guide must still
  // load and behave as shipped.
  readonly property bool sourcesApi: serviceReady && service.sources !== undefined && service.sources !== null
  readonly property var sourceList: sourcesApi ? Model.asList(service.sources) : []
  readonly property int sourceCount: sourceList.length
  readonly property string activeSourceId: sourcesApi && service.activeSourceId !== undefined && service.activeSourceId !== null ? String(service.activeSourceId) : ""
  readonly property var activeSource: root.findSourceView(root.activeSourceId)
  readonly property string activeSourceLabel: activeSource ? String(activeSource.label) : ""
  readonly property bool probing: serviceReady && service.probing === true
  readonly property bool switching: serviceReady && service.switching === true
  readonly property var form: guide.form
  readonly property string formFocus: form ? String(form.focus) : ""
  readonly property bool formProbing: form ? form.probing === true : false
  readonly property var formError: form ? form.error : null
  readonly property bool firstRunForm: formActive && form !== null && form.origin === "firstRun"
  readonly property bool firstRunHead: firstRunForm && form.kind === "url"
  readonly property var formFieldIds: form ? Model.formFields(form) : []
  readonly property int sourceCursor: guide.sourceCursor
  readonly property int sourceRowCount: Model.sourcesRowCount(sourceCount)
  readonly property string sourceCursorKind: Model.sourcesRowKind(sourceCursor, sourceCount)
  // Set by the form key handler right before the TextField pastes, so the
  // next text change is trimmed and re-masked as a paste (UX-SOURCES 2.3).
  property bool pasteArmed: false
  property string pendingProbeId: ""
  property string pendingCursorId: ""
  property string switchPendingId: ""
  // D-SRC-04: Enter / Space on a never-fetched source probes first (SR7).
  // `switchPendingLeave` remembers that Enter leaves Sources once the switch
  // happened; while the probe runs the footer's status slot reads
  // `Fetching from <host>...` (derived, so an IPC-started probe shows too)
  // and a failure lands in `sourcesNotice`, the Sources result line, until
  // the next Sources event (SR26).
  property bool switchPendingLeave: false
  property string sourcesNotice: ""
  readonly property string sourcesProbeText: {
    if (!root.inSources || !root.probing || root.formActive) return ""
    var id = root.serviceReady && root.service.probingId !== undefined ? String(root.service.probingId || "") : ""
    var view = root.findSourceView(id)
    return view ? Model.fetchingLine(view.host, view.kind) : ""
  }
  // D-SRC-06: a configured URL the validator refused (CLI, SR8) renders the
  // UX 5.4 sentence alone, no host and no `r` hint (nothing to retry).
  readonly property string invalidSettingsText: {
    if (!root.serviceReady || root.service.settingsInvalid === undefined || !root.service.settingsInvalid) return ""
    return Model.sourceErrorMessage(String(root.service.settingsInvalid.code || "invalid"))
  }
  // D9: Qt's clipboard through the TextField is the paste path. Flip to
  // true only if harness scenario H4 finds the layer-shell surface pastes
  // empty; the service's wl-paste verb (requestClipboard / clipboardText)
  // is then used and guarded here.
  readonly property bool pasteViaProcess: false
  readonly property bool headerShowsSearch: guideMode || firstRunHead
  readonly property string headerTitle: {
    if (root.mode === "sourceEdit") return root.form && root.form.sourceId !== "" ? root.copy.editSourceTitle : root.copy.addSourceTitle
    if (root.mode === "sourceXtream") return root.copy.xtreamTitle
    if (root.inSources || root.confirmOpen) return root.copy.sourcesTitle
    return ""
  }
  readonly property string headerRight: {
    if (root.guideMode) return root.scopeLabelText
    if (root.inSources || root.confirmOpen) return Model.sourcesHeaderCount(root.sourceCount)
    return ""
  }
  readonly property string formAccessibleName: {
    if (root.firstRunHead) return root.copy.accessibleFirstRun
    return root.headerTitle
  }
  readonly property string confirmMessage: {
    var view = root.sourceAt(root.sourceCursor)
    return view ? Model.confirmRemoveMessage(view.label, view.active) : ""
  }

  // The Sources result line lives with the list (Esc, `o`, a form or the
  // confirm dialog all leave it behind).
  onInSourcesChanged: if (!root.inSources) root.sourcesNotice = ""
  onFormFocusChanged: if (root.formActive) Qt.callLater(root.focusFormItem)
  onFormActiveChanged: if (root.opened) root.refocus()
  onFormProbingChanged: if (root.opened && root.formActive) root.refocus()

  // Per-row decorations (star, playing cue, failure notice, EPG now/next)
  // are resolved by each delegate from these lookups, so only the visible
  // rows pay for them and a favorite toggle, a zap or the 30 s EPG tick
  // never rebuilds the list (D-LIVE-01).
  readonly property var favoriteSet: Model.favoriteSet(root.serviceReady ? root.service.userState.favorites : [])
  readonly property var failedMap: root.serviceReady && root.service.failedAt ? root.service.failedAt : ({})
  readonly property var epgMap: root.serviceReady && root.epgLoaded ? root.service.epgNow : ({})
  // Two-line rows whenever the detail line can have content for this list
  // (UX 2.4): a mixed list shows the group, EPG adds now/next, and inside a
  // single group a failed channel still needs its `Failed HH:MM` line.
  readonly property bool rowsHaveDetail: !root.scopeIsGroup || root.epgConfigured || root.anyFailedInScope(root.failedMap, root.effectiveScope)

  // Inside a single group only the (few) failed ids are checked, never the
  // rows: a failed channel of this group means two-line rows.
  function anyFailedInScope(failed, scope) {
    if (!failed || !root.serviceReady || !Model.isGroupScope(scope)) return false
    var name = Model.scopeName(scope)
    var index = root.service.channelIndex
    for (var id in failed) {
      var channel = index ? index[id] : null
      if (channel && Model.primaryGroup(channel) === name) return true
    }
    return false
  }

  // The whole body decision in one object (Model.guideSurface, D-LIVE-19):
  // which empty state, whether rows and the group column exist, and the
  // channel count the footer may show. `sources` rides along so the setup
  // surface knows a cleared playlist still has a history behind it.
  readonly property var surface: Model.guideSurface({
    serviceReady: root.serviceReady,
    configured: root.configured,
    channelCount: root.serviceReady ? root.service.channels.length : 0,
    status: root.serviceStatus,
    rowCount: root.rowCount,
    query: root.query,
    scopeId: root.scopeId,
    narrow: root.narrow,
    sources: root.sourceCount
  })

  // Empty-state kind: "" while rows exist.
  readonly property string emptyKind: surface.empty

  // Banner kind (R8): none | playlistError | epgError | epgPending. An EPG
  // fetch failure shows the banner even while an earlier window is still
  // rendered (UX 6.3, D-LIVE-08); it stays until a fetch succeeds.
  readonly property string bannerKind: {
    if (!root.serviceReady || !root.hasChannels) return "none"
    if (root.serviceStatus === "cached" && root.service.playlistFailed) return "playlistError"
    if (root.epgConfigured && root.service.epgFailed) return "epgError"
    if (root.epgConfigured && root.service.epgPending && root.service.epgRefreshing) return "epgPending"
    return "none"
  }
  readonly property string bannerText: {
    if (root.bannerKind === "playlistError") {
      return root.copy.bannerPlaylist + root.service.statusReason + ")" + Model.SEP + root.copy.bannerCached + (root.service.lastUpdated !== "" ? " from " + root.service.lastUpdated : "") + Model.SEP + root.copy.bannerRetry
    }
    if (root.bannerKind === "epgError") return root.copy.bannerEpg + root.service.epgReason + ")" + Model.SEP + root.copy.bannerEpgStill + Model.SEP + root.copy.bannerRetry
    if (root.bannerKind === "epgPending") return root.copy.bannerEpgPending
    return ""
  }

  readonly property string scopeLabelText: root.hasChannels ? Model.scopeLabel(root.scopeId, root.query, root.resultTotal) : ""

  // Helper warnings of the last load (D-LIVE-18 and its EPG twin): one
  // low-key line in the footer status slot, URL-free (Model.statusWarnings),
  // kept until that helper's next clean load replaces it. Text only, so the
  // list never moves when it appears. The playlist's warnings win; the EPG's
  // read `Guide data warning: ...`. A service without `epgWarnings` (the
  // harness before this lane) simply shows the playlist line as before.
  // Either line is informational and sits near the bottom of the UX 6.3
  // ladder: `stale` below is the R8 `cached` status, and that degraded counts
  // line outranks both warnings, so a warning can never take the footer's
  // only `cached HH:MM - offline` cue away (D-LIVE-22).
  readonly property var epgWarningList: root.serviceReady && root.service.epgWarnings !== undefined ? Model.asList(root.service.epgWarnings) : []
  readonly property string warningText: root.serviceReady ? Model.footerWarning(root.service.playlistWarnings, root.epgWarningList) : ""

  readonly property string footerStatusText: Model.footerStatus({
    transient: root.transientText !== "" ? root.transientText : (root.sourcesProbeText !== "" ? root.sourcesProbeText : root.sourcesNotice),
    configured: root.configured,
    truncated: root.truncated,
    resultTotal: root.resultTotal,
    cap: root.maxRows,
    playingName: root.playingName,
    refreshing: root.serviceReady && root.service.refreshing,
    epgPending: root.serviceReady && root.service.epgPending,
    warning: root.warningText,
    count: root.surface.channelCount,
    lastUpdated: root.serviceReady ? root.service.lastUpdated : "",
    stale: root.serviceStatus === "cached",
    activeLabel: root.activeSourceLabel,
    sourceCount: root.sourceCount,
    // M2-03 6.2: the live buffer sits at the top of the ladder, above the
    // transient, so a three-second toast cannot cover what the digits are
    // doing right now.
    numberEntry: root.numberEntryActive ? {
      active: true,
      buffer: root.numberBuffer,
      kind: root.numberResolution.kind,
      label: root.numberResolution.label,
      name: root.numberTargetName,
      matches: root.numberResolution.matches,
      ordinal: root.numberResolution.ordinal
    } : null
  })

  readonly property string keyColor: Util.alpha(root.foreground, 0.7).toString()
  readonly property string verbColor: Util.alpha(root.foreground, 0.45).toString()
  readonly property string footerHintText: {
    var empty = ""
    if (root.emptyKind === "loading") empty = "loading"
    else if (root.emptyKind === "unconfigured" || root.emptyKind === "error" || root.emptyKind === "service") empty = "error"
    var pairs = Model.footerHints({ mode: root.mode, query: root.query, empty: empty, sourcesExist: root.sourceCount > 0, retry: root.invalidSettingsText === "", cursorKind: root.sourceCursorKind, form: root.form,
      hasNumbers: root.hasNumbers, numberEntry: root.numberEntryActive ? { active: true } : null })
    var out = []
    for (var i = 0; i < pairs.length; i++) {
      out.push("<font color=\"" + root.keyColor + "\">" + pairs[i][0] + "</font> <font color=\"" + root.verbColor + "\">" + pairs[i][1] + "</font>")
    }
    return out.join("<font color=\"" + root.verbColor + "\">" + Model.SEP + "</font>")
  }

  // ------------------------------------------------------------ lifecycle

  function resolveService() {
    if (!root.service && root.shell && typeof root.shell.serviceFor === "function")
      root.service = root.shell.serviceFor(root.pluginId)
  }

  function open(payloadJson) {
    root.resolveService()
    var payload = Model.parseJsonObject(payloadJson) || {}
    var channels = root.serviceReady ? root.service.channels : []
    var userState = root.serviceReady ? root.service.userState : null
    var next = Model.guideState(Model.initialScope(channels, userState))
    if (typeof payload.scope === "string" && payload.scope !== "") next = Model.withScope(next, payload.scope)
    else if (typeof payload.group === "string" && payload.group !== "") next = Model.withScope(next, Model.groupScopeId(payload.group))
    if (typeof payload.query === "string" && payload.query !== "") next = Model.withQuery(next, payload.query)
    // UX-SOURCES 1.2: unconfigured opens straight into the first-run form.
    if (root.serviceReady && !root.configured) next = Model.openFirstRun(next)
    root.guide = next
    root.transientText = ""
    root.enterPending = false
    root.pasteArmed = false
    root.pendingProbeId = ""
    root.pendingCursorId = ""
    root.switchPendingId = ""
    root.switchPendingLeave = false
    root.sourcesNotice = ""
    root.opened = true
    root.disarmPointer()
    root.rebuildDisplay()
    root.cursorIndex = Model.cursorFor(root.currentRows, root.playingId)
    root.scrollToCursor()
    root.refocus()
  }

  function close() {
    root.opened = false
    transientTimer.stop()
    // M2-03 2.6: closing drops the buffer and stops its timer, as this
    // already does for transientTimer. No snapshot is restored -- the guide
    // is going away, and a commit on the way out would fire a transient
    // nobody sees.
    numberTimer.stop()
    root.numberEntry = Model.numberEntry()
    root.numberResolution = Model.resolveChno(null, "", -1)
    root.numberTargetName = ""
    // The form state (the only place a URL lives in this file) is dropped
    // with the overlay (UX-SOURCES 6.9).
    if (root.form !== null || !root.guideMode) root.guide = Model.guideState(root.scopeId)
  }

  function dismiss() {
    root.close()
    if (root.shell && typeof root.shell.hide === "function") root.shell.hide(root.pluginId)
  }

  function toggle() {
    if (root.opened) root.dismiss()
    else root.open("{}")
  }

  // ------------------------------------------------------------ model

  // The rows currently shown (plain channel objects, same order as the
  // ListModel) so actions never re-derive from role data.
  property var currentRows: []

  function candidates() {
    if (!root.serviceReady) return []
    return Model.channelsForScope(root.service.channels, root.effectiveScope, root.service.userState)
  }

  function scheduleRebuild() {
    if (!root.opened) return
    var big = root.serviceReady && root.service.channels.length > root.filterDebounceThreshold
    rebuildTimer.interval = big ? root.filterDebounceMs : 0
    rebuildTimer.restart()
  }

  function rebuildGroups() {
    if (!root.serviceReady) {
      root.scopeList = []
      groupModel.clear()
      root.groupSignature = ""
      root.groupsDirty = true
      return
    }
    if (!root.groupsDirty && root.scopeList.length > 0) return
    root.groupsDirty = false
    // M2-03 1.4, the compatibility path only (see chnoApi): a service that
    // publishes chnoIndex never reaches this. It runs on a channel-set change,
    // never on a keystroke, so digit entry stays on the per-key budget either
    // way.
    if (!root.chnoApi) root.fallbackChnoIndex = Model.buildChnoIndex(root.service.channels)
    var entries = Model.scopeEntries(root.service.channels, root.service.userState)
    var parts = []
    for (var i = 0; i < entries.length; i++) parts.push(entries[i].id + "=" + entries[i].count)
    var signature = parts.join("|")
    root.scopeList = entries
    if (signature === root.groupSignature) return
    root.groupSignature = signature
    groupModel.clear()
    for (var j = 0; j < entries.length; j++) {
      groupModel.append({ scopeId: entries[j].id, label: entries[j].label, count: entries[j].count, kind: entries[j].kind })
    }
  }

  // Recomputes the row set. Rows are the channel objects themselves (the
  // scope array for an empty query, the ranked hits for a search); the
  // ListView reads them by index through its integer model, so no per-row
  // copy is made here and the whole scope is browsable (D-LIVE-01).
  function rebuildDisplay() {
    root.resolveService()
    root.rebuildGroups()
    // The cursor's scope may have left the column (last Recent entry
    // removed, a group gone after a refresh): move to a visible entry
    // before the rows are resolved (UX 2.2, D-LIVE-07).
    var fallback = Model.fallbackScope(root.scopeList, root.scopeId)
    if (fallback !== root.scopeId) root.guide = Model.withScope(root.guide, fallback)
    var favorites = root.serviceReady ? root.service.userState.favorites : []
    // CN5 / 2.8: an all-digit query floats the exact number match to the top
    // of the results, so the feature is reachable from the mode the guide
    // opens in. A head insertion, not a fifth ranking tier.
    var result = Model.filterChannels(root.candidates(), root.query, root.maxRows, favorites, root.chnoIndex)
    root.resultTotal = result.total
    root.truncated = result.truncated
    root.currentRows = result.rows
    root.rowCount = result.rows.length

    if (root.rowCount === 0) root.cursorIndex = 0
    else if (root.cursorIndex >= root.rowCount) root.cursorIndex = root.rowCount - 1
    else if (root.cursorIndex < 0) root.cursorIndex = 0

    Qt.callLater(function() {
      root.scrollToCursor()
      root.positionColumn()
    })
  }

  function applyGuide(next, rebuild) {
    root.guide = next
    root.cursorIndex = 0
    root.disarmPointer()
    if (rebuild) root.rebuildDisplay()
  }

  function setQuery(text) {
    root.applyGuide(Model.withQuery(root.guide, text), false)
    root.scheduleRebuild()
  }

  function setScope(id) {
    root.applyGuide(Model.withScope(root.guide, id), true)
    root.cursorIndex = Model.cursorFor(root.currentRows, root.playingId)
    root.scrollToCursor()
  }

  function moveScopeBy(delta) {
    if (root.scopeList.length === 0) return
    root.setScope(Model.moveScope(root.scopeList, root.scopeId, delta))
  }

  // Column position (UX 2.2 / 2.3, D-LIVE-16): a pinned entry (Recent,
  // Favorites, All) shows the column from the top, a group is brought into
  // view. Only against a laid-out view: on a reopen the layer surface is
  // mapped after open() returns, so a Contain issued then saw a 0-height
  // view and parked All at the top edge with Favorites hidden above it. The
  // views call back in from onHeightChanged once they have their size.
  function positionColumn() {
    if (!root.opened || !root.showColumn || groupList.height <= 0) return
    var anchor = Model.columnAnchor(root.scopeList, root.scopeId)
    if (anchor.index < 0 || anchor.index >= groupModel.count) return
    if (anchor.top) groupList.positionViewAtBeginning()
    else groupList.positionViewAtIndex(anchor.index, ListView.Contain)
  }

  function scrollToCursor() {
    if (root.rowCount > 0 && resultList.height > 0) resultList.positionViewAtIndex(root.cursorIndex, ListView.Contain)
  }

  function moveCursorBy(delta, wrap) {
    if (root.rowCount === 0) return
    root.disarmPointer()
    root.cursorIndex = Model.moveCursor(root.cursorIndex, delta, root.rowCount, wrap)
    root.scrollToCursor()
  }

  function selectAbsolute(index) {
    if (root.rowCount === 0) return
    root.disarmPointer()
    root.cursorIndex = Math.max(0, Math.min(index, root.rowCount - 1))
    root.scrollToCursor()
  }

  function pageSize() {
    return Math.max(1, Math.floor(resultList.height / (root.rowHeight + root.rowSpacing)) - 1)
  }

  function disarmPointer() {
    pointerGate.reset()
  }

  function selectFromPointer(index, item, mouse) {
    if (!pointerGate.moved(item, mouse)) return
    root.cursorIndex = index
  }

  function showTransient(text) {
    // A new event supersedes the Sources result line (D-SRC-04).
    root.sourcesNotice = ""
    root.transientText = text
    transientTimer.restart()
  }

  // ------------------------------------------------------------ actions

  function rowAt(index) {
    if (index < 0 || index >= root.currentRows.length) return null
    return root.currentRows[index]
  }

  // Enter (keepOpen false): play, close, focus mpv. Space (keepOpen true):
  // play and stay (preview / zapping).
  function activate(keepOpen) {
    var channel = root.rowAt(root.cursorIndex)
    if (!channel || !root.serviceReady) return
    var from = Model.launchScope(root.scopeId, root.query, channel)
    if (keepOpen) {
      root.service.play(Model.channelId(channel), true, from)
      root.transientText = ""
      root.rebuildDisplay()
      return
    }
    root.dismiss()
    root.service.play(Model.channelId(channel), false, from)
  }

  function activateIndex(index, keepOpen) {
    root.cursorIndex = index
    root.activate(keepOpen)
  }

  function toggleFavoriteAt(index) {
    var channel = root.rowAt(index)
    if (!channel || !root.serviceReady) return
    var added = root.service.toggleFavorite(Model.channelId(channel))
    root.showTransient(added ? root.copy.transientFavAdded : root.copy.transientFavRemoved)
    root.rebuildDisplay()
  }

  // x / Delete: remove from Recent, or unfavorite in Favorites; no-op elsewhere.
  function removeAt(index) {
    var channel = root.rowAt(index)
    if (!channel || !root.serviceReady) return
    if (root.effectiveScope === Model.SCOPE_RECENT) {
      root.service.removeRecent(Model.channelId(channel))
      root.showTransient(root.copy.transientRecentRemoved)
      root.rebuildDisplay()
    } else if (root.effectiveScope === Model.SCOPE_FAVORITES) {
      root.toggleFavoriteAt(index)
    }
  }

  function stopPlayback() {
    if (!root.serviceReady) return
    root.service.stop()
    root.showTransient(root.copy.transientStopped)
    root.rebuildDisplay()
  }

  // r / middle click: `Refreshing...` while the helper runs, then
  // `Refreshed - N channels` from the service's playlistRefreshed signal
  // (UX 6.1, D-LIVE-05). Nothing to reload without a playlist: a short hint
  // only (D-LIVE-09).
  function refresh() {
    if (!root.serviceReady) return
    if (!root.configured) {
      root.showTransient(root.copy.transientUnconfigured)
      return
    }
    root.service.refresh()
    root.showTransient(root.copy.transientRefreshing)
  }

  function copyCommand(text) {
    Quickshell.execDetached(["wl-copy", String(text)])
    root.showTransient(root.copy.transientCopied)
  }

  // ------------------------------------------------------------ channel numbers (M2-03)
  //
  // The guide owns the timer, the cursor and the chip. Every decision below
  // is a Model.js call; there is no number logic in this file.

  function rowIndexOfId(id) {
    var key = String(id || "")
    if (key === "") return -1
    for (var i = 0; i < root.currentRows.length; i++) {
      if (Model.channelId(root.currentRows[i]) === key) return i
    }
    return -1
  }

  // M2-03 2.3. The cursor follows the buffer live, and the row it lands on is
  // what the footer names. WHAT to resolve, and what to resolve it against,
  // is Model's decision (numberKeyStep); this is the half only the guide can
  // do -- the cursor, the scope hop and the name.
  function applyNumberResolution(hit) {
    if (!hit || hit.kind === "none") {
      // The cursor does not move: the user can Backspace out of a typo
      // without ever having left the row they were on (CN1).
      root.numberTargetName = ""
      return
    }
    var id = Model.chnoIdAt(root.chnoIndex, hit.channelIndex)
    var at = root.rowIndexOfId(id)
    if (at < 0) {
      // Outside the current list: the scope moves to All, clearing a query
      // that is in the way, exactly as a search from Favorites jumps the
      // column (UX 2.7). In All the target's numeric neighbours are the
      // adjacent rows, so j/k right after a jump are channel up and down.
      if (root.hasQuery) root.guide = Model.withQuery(root.guide, "")
      root.setScope(Model.SCOPE_ALL)
      at = root.rowIndexOfId(id)
    }
    if (at >= 0) root.selectAbsolute(at)
    var row = root.rowAt(at >= 0 ? at : root.cursorIndex)
    root.numberTargetName = row ? String(row.name || "") : ""
  }

  function pushNumberEntry(text) {
    var step = Model.numberKeyStep(root.numberEntry, root.chnoIndex, text,
      { scopeId: root.scopeId, query: root.query, cursorIndex: root.cursorIndex, cursorId: root.cursorChannelId })
    // A refused key (the cap, a second separator) must NOT restart the
    // timer: the buffer is already as long as any number can be.
    if (!step.changed) return
    root.numberEntry = step.entry
    root.numberResolution = step.commit ? Model.resolveChno(null, "", -1) : step.resolution
    root.applyNumberResolution(step.resolution)
    root.runNumberTimer(step.timer)
    // 2.5: an exact match no label extends commits on the last digit, which
    // is what makes a three-digit plan feel instant.
    if (step.commit) root.finishNumberCommit(step.commit, step.snapshot)
  }

  // The half of a commit that needs the screen: the status line names the row
  // the preview landed on, which is why Model hands back the decision and not
  // the sentence.
  function finishNumberCommit(commit, snapshot) {
    var status = Model.chnoStatus(commit.kind, commit.label, root.numberTargetName, commit.matches, commit.ordinal, true)
    root.numberTargetName = ""
    if (commit.restore) root.restoreNumberSnapshot(snapshot)
    root.showTransient(status)
    if (commit.play) root.activate(commit.keepOpen)
  }

  function runNumberTimer(what) {
    if (what === "restart") numberTimer.restart()
    else if (what === "stop") numberTimer.stop()
  }

  function popNumberEntry() {
    var step = Model.numberPopStep(root.numberEntry, root.chnoIndex)
    root.numberEntry = step.entry
    root.numberResolution = step.resolution
    root.runNumberTimer(step.timer)
    if (step.cancelled) {
      // 2.6: Backspace on the last character is the same cancel as Esc, and
      // the step still carries the snapshot to restore from.
      root.numberTargetName = ""
      root.restoreNumberSnapshot(step.snapshot)
      return
    }
    root.applyNumberResolution(step.resolution)
  }

  function restoreNumberSnapshot(entry) {
    if (!entry) return
    var next = root.guide
    if (String(entry.query) !== root.query) next = Model.withQuery(next, entry.query)
    if (String(entry.scopeId) !== "" && String(entry.scopeId) !== root.scopeId) next = Model.withScope(next, entry.scopeId)
    if (next !== root.guide) {
      root.guide = next
      root.rebuildDisplay()
    }
    root.selectAbsolute(entry.cursorIndex)
  }

  // M2-03 2.5. Four triggers, one result. A commit NEVER plays by itself:
  // Enter and Space keep exactly the meanings UX 3.1 gives them (CN1), and
  // `play` is set only by the two of them.
  function commitNumberEntry(opts) {
    if (!root.numberEntryActive) return false
    var o = opts || {}
    numberTimer.stop()
    // Playing whatever happened to be under the cursor after a mistyped
    // number is the one genuinely destructive outcome this feature could
    // have, so the decision has a name and a test of its own.
    var done = Model.numberCommitStep(root.numberEntry, root.numberResolution, root.numberTargetName, o)
    root.numberEntry = done.entry
    root.numberResolution = Model.resolveChno(null, "", -1)
    root.numberTargetName = ""
    if (done.plan.restore) root.restoreNumberSnapshot(done.snapshot)
    root.showTransient(done.plan.status)
    if (done.plan.play) root.activate(done.plan.keepOpen)
    return !done.plan.restore
  }

  // CN21. The window an auto-commit left armed, expiring. Whatever ends it -
  // the timer, a key that is not a digit, Esc, Enter, closing the guide - the
  // number is finished and the next digit starts a new one.
  function disarmNumberResume() {
    if (root.numberEntry === null || root.numberEntry.resume !== true) return false
    numberTimer.stop()
    root.numberEntry = Model.numberEntry()
    return true
  }

  function numberTimerFired() {
    if (root.numberEntryActive) { root.commitNumberEntry({ play: false, reason: "timeout" }); return }
    root.disarmNumberResume()
  }

  function cancelNumberEntry() {
    if (!root.numberEntryActive) { root.disarmNumberResume(); return false }
    numberTimer.stop()
    var entry = root.numberEntry
    root.numberEntry = Model.closeNumberEntry(entry, "cancel")
    root.numberResolution = Model.resolveChno(null, "", -1)
    root.numberTargetName = ""
    root.restoreNumberSnapshot(entry)
    return true
  }

  // Any key this feature does not own ends entry first, then does its job.
  function endNumberEntry(commit) {
    if (!root.numberEntryActive) { root.disarmNumberResume(); return }
    if (commit) root.commitNumberEntry({ play: false, reason: "key" })
    else root.cancelNumberEntry()
  }

  // M2-03 2.9 / gate A1. Match on event.text, NEVER on Qt.Key_0..Qt.Key_9.
  // Proven against libxkbcommon with real keymaps (the evidence is in the
  // lane A report): the numeric keypad sends KP_1, whose text is "1", and on
  // AZERTY and bepo the top-row digits sit at shift level 2, so the digit
  // arrives WITH ShiftModifier set. Rejecting Shift would break numeric zap
  // on every French layout, so Shift is deliberately not in the reject mask;
  // Ctrl, Alt and Meta are, because those are chords, not digits. Keypad
  // digits also carry Qt::KeypadModifier, which is likewise not rejected.
  function handleNumberKey(event) {
    var action = Model.numberKeyAction({
      text: event.text,
      modifiers: event.modifiers,
      backspace: event.key === Qt.Key_Backspace,
      active: root.numberEntryActive,
      hasNumbers: root.hasNumbers
    })
    // A key the buffer does not own ends the number, armed window included.
    if (action === "pass") { root.disarmNumberResume(); return false }
    if (action === "backspace") { root.popNumberEntry(); return true }
    if (action === "noNumbers") {
      root.showTransient(Model.chnoStatus("noNumbers", "", "", 0, 0, true))
      return true
    }
    root.pushNumberEntry(event.text)
    return true
  }

  // `configured` rides along so Esc in Sources lands in the first-run form
  // when the guide behind it is unconfigured (UX 1.7: the active source
  // was removed while Sources stayed open).
  //
  // M2-03 2.6: a live number buffer is one step in front of the shipped
  // chain -- cancel it, and do not fall through to clearing the query or
  // closing the guide. Model.onEscape is untouched.
  function handleEscape() {
    if (root.listMode && root.cancelNumberEntry()) return
    root.applyEscapeResult(Model.onEscape(root.guide, { configured: root.configured }))
  }

  // Applies an onEscape / closeForm result: cancels a running probe, closes
  // the overlay, clears the query (shipped path), or changes mode.
  function applyEscapeResult(result) {
    if (result.cancelProbe && root.serviceReady && typeof root.service.cancelProbe === "function") root.service.cancelProbe()
    if (result.close) { root.dismiss(); return }
    if (root.guideMode && result.state.mode === root.mode) { root.applyGuide(result.state, true); return }
    root.setGuide(result.state)
    if (root.guideMode) root.rebuildDisplay()
    root.refocus()
  }

  function switchMode() {
    root.guide = Model.toggleMode(root.guide)
  }

  // Keys both modes share and PanelKeyCatcher does not consume:
  // PgUp/PgDn, Home/End, Delete. In Sources they drive the source cursor.
  function handleSharedKey(event) {
    if (root.inSources) {
      if (event.key === Qt.Key_PageUp) { root.moveSourceCursorBy(-root.sourcePageSize(), false); return true }
      if (event.key === Qt.Key_PageDown) { root.moveSourceCursorBy(root.sourcePageSize(), false); return true }
      if (event.key === Qt.Key_Home) { root.selectSourceAbsolute(0); return true }
      if (event.key === Qt.Key_End) { root.selectSourceAbsolute(root.sourceRowCount - 1); return true }
      if (event.key === Qt.Key_Delete) { root.startRemove(); return true }
      return false
    }
    // M2-03 2.9. The listMode guard is what keeps digits literal in search
    // mode (UX 8 #17): handleSharedKey is also called from handleSearchKey,
    // and the shipped `Qt.Key_Delete && root.listMode` branch below is the
    // precedent. Anything the buffer does not own commits it first.
    if (root.listMode && root.handleNumberKey(event)) return true
    if (root.listMode && root.numberEntryActive) root.endNumberEntry(true)
    if (event.key === Qt.Key_PageUp) { root.moveCursorBy(-root.pageSize(), false); return true }
    if (event.key === Qt.Key_PageDown) { root.moveCursorBy(root.pageSize(), false); return true }
    if (event.key === Qt.Key_Home) {
      // UX 8 #22: Home with a query active in list mode jumps the column to All.
      if (root.listMode && root.hasQuery && root.effectiveScope !== Model.SCOPE_ALL) root.setScope(Model.SCOPE_ALL)
      else root.selectAbsolute(0)
      return true
    }
    if (event.key === Qt.Key_End) { root.selectAbsolute(root.rowCount - 1); return true }
    if (event.key === Qt.Key_Delete && root.listMode) { root.removeAt(root.cursorIndex); return true }
    return false
  }

  // Search mode (UX 3.2): printable keys edit the query; arrows move.
  function handleSearchKey(event) {
    if (event.key === Qt.Key_Escape) { root.handleEscape(); return true }
    if (Util.editsFilter(event, root.query)) { root.setQuery(Util.editedFilter(event, root.query)); return true }
    if (event.key === Qt.Key_Down) { root.moveCursorBy(1, true); return true }
    if (event.key === Qt.Key_Up) { root.moveCursorBy(-1, true); return true }
    if (event.key === Qt.Key_Right) { root.moveScopeBy(1); return true }
    if (event.key === Qt.Key_Left) { root.moveScopeBy(-1); return true }
    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) { root.activate(false); return true }
    if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) { root.switchMode(); return true }
    if (root.handleSharedKey(event)) return true
    if (event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)) return false
    if (event.text && event.text.length === 1 && event.text.charCodeAt(0) >= 32 && event.text.charCodeAt(0) !== 127) {
      root.setQuery(root.query + event.text)
      return true
    }
    return false
  }

  // List-mode single-letter commands delivered by PanelKeyCatcher.textKey.
  function handleListLetter(text) {
    var t = String(text || "")
    if (t === "f" || t === "F") root.toggleFavoriteAt(root.cursorIndex)
    else if (t === "s" || t === "S") root.stopPlayback()
    else if (t === "r" || t === "R") root.refresh()
    else if (t.toLowerCase() === Model.SOURCE_KEYS.open) root.openSources()
    else if (t === "/") {
      root.swallowKey = true
      root.switchMode()
    }
    // Digits, "." and "," never reach here: onTextKey returns early for
    // them and handleSharedKey extends the number buffer instead (M2-03
    // 2.9). Everything else is still ignored.
  }

  // Sources-mode letters (UX-SOURCES 2.2); x / X arrive as deleteRequested.
  function handleSourcesLetter(text) {
    var t = String(text || "").toLowerCase()
    if (t === Model.SOURCE_KEYS.open) root.leaveSources()
    else if (t === Model.SOURCE_KEYS.add) root.openAddForm()
    else if (t === Model.SOURCE_KEYS.xtream) root.openXtreamForm()
    else if (t === Model.SOURCE_KEYS.edit) root.openEditForm()
    else if (t === Model.SOURCE_KEYS.remove) root.startRemove()
    // h / l / Tab / "/" / r / s / f / digits: ignored here (UX-SOURCES 8 #20, #27)
  }

  // ------------------------------------------------------------ sources (M2-01)

  function findSourceView(id) {
    var key = String(id || "")
    if (key === "") return null
    for (var i = 0; i < root.sourceList.length; i++) {
      if (root.sourceList[i] && String(root.sourceList[i].id) === key) return root.sourceList[i]
    }
    return null
  }

  function sourceIndexOf(id) {
    var key = String(id || "")
    if (key === "") return -1
    for (var i = 0; i < root.sourceList.length; i++) {
      if (root.sourceList[i] && String(root.sourceList[i].id) === key) return i
    }
    return -1
  }

  function sourceAt(index) {
    return index >= 0 && index < root.sourceList.length ? root.sourceList[index] : null
  }

  // Replace the state object without the channel-cursor reset of applyGuide.
  function setGuide(next) {
    root.guide = next
    root.disarmPointer()
  }

  // Key focus per mode (UX-SOURCES 7.3): the focused form element, or the
  // key catcher (also while a probe freezes the form, so Esc still cancels).
  function refocus() {
    if (root.formActive && !root.formProbing) Qt.callLater(root.focusFormItem)
    else Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function openSources() {
    if (!root.serviceReady) return
    root.setGuide(Model.openSources(root.guide, root.sourceList))
    root.scrollToSourceCursor()
    root.refocus()
  }

  function leaveSources() {
    root.sourcesNotice = ""
    root.setGuide(Model.closeSources(root.guide, { configured: root.configured }))
    if (root.guideMode) root.rebuildDisplay()
    root.refocus()
  }

  function sourcePageSize() {
    return Math.max(1, Math.floor(sourceListView.height / (root.detailRowHeight + root.rowSpacing)) - 1)
  }

  function scrollToSourceCursor() {
    if (root.sourceRowCount > 0 && sourceListView.height > 0) sourceListView.positionViewAtIndex(root.sourceCursor, ListView.Contain)
  }

  function moveSourceCursorBy(delta, wrap) {
    if (root.sourceRowCount === 0) return
    root.setGuide(Model.withSourceCursor(root.guide, Model.moveCursor(root.sourceCursor, delta, root.sourceRowCount, wrap)))
    root.scrollToSourceCursor()
  }

  function selectSourceAbsolute(index) {
    if (root.sourceRowCount === 0) return
    root.setGuide(Model.withSourceCursor(root.guide, Math.max(0, Math.min(index, root.sourceRowCount - 1))))
    root.scrollToSourceCursor()
  }

  function selectSourceFromPointer(index, item, mouse) {
    if (!pointerGate.moved(item, mouse)) return
    root.guide = Model.withSourceCursor(root.guide, index)
  }

  // Keeps the cursor on a row whose index moved (the list sorts the active
  // source first) and clamps it after a removal.
  function syncSourceCursor() {
    if (!root.opened) return
    if (root.pendingCursorId !== "") {
      var at = root.sourceIndexOf(root.pendingCursorId)
      if (at >= 0) {
        root.pendingCursorId = ""
        root.guide = Model.withSourceCursor(root.guide, at)
      }
    }
    if (root.sourceCursor >= root.sourceRowCount) root.guide = Model.withSourceCursor(root.guide, Math.max(0, root.sourceRowCount - 1))
    root.scrollToSourceCursor()
  }

  // Enter (stay false) / Space (stay true) on a Sources row (UX-SOURCES 1.4).
  function activateSourceRow(index, stay) {
    var kind = Model.sourcesRowKind(index, root.sourceCount)
    root.guide = Model.withSourceCursor(root.guide, index)
    if (kind === "add") root.openAddForm()
    else if (kind === "xtream") root.openXtreamForm()
    else if (kind === "source") root.switchToSource(index, stay)
  }

  function switchToSource(index, stay) {
    var view = root.sourceAt(index)
    if (!view) return
    if (view.active) {
      if (!stay) root.leaveSources()
      return
    }
    if (!root.sourcesApi || typeof root.service.switchSource !== "function") {
      root.showTransient(Model.sourceErrorMessage("not_ready"))
      return
    }
    var result = root.service.switchSource(view.id)
    if (!result || result.ok !== true) {
      root.showTransient(Model.sourceErrorMessage(result ? result.code : "unknown_source"))
      return
    }
    root.switchPendingId = String(view.id)
    root.sourcesNotice = ""
    if (Number(view.channelCount) < 0) {
      // Never fetched: the service probes first and commits the switch only
      // on success (SR7). The footer reads `Fetching from <host>...` meanwhile
      // (sourcesProbeText); showSwitched shows the transient and leaves
      // Sources once the switch happened, onSwitchProbeFinished reports a
      // failure on the result line with the previous source still active
      // (D-SRC-04).
      root.switchPendingLeave = !stay
      return
    }
    root.switchPendingLeave = false
    root.showTransient(Model.sourceTransient("switched", { label: view.label, channelCount: view.channelCount }))
    if (stay) {
      // The check glyph moves at once; the list re-sorts, the cursor follows.
      root.pendingCursorId = String(view.id)
      root.syncSourceCursor()
      return
    }
    root.leaveToGuide()
  }

  // A fresh search-mode view on the initial scope (UX-SOURCES 1.4 step 3).
  function leaveToGuide() {
    var channels = root.serviceReady ? root.service.channels : []
    var userState = root.serviceReady ? root.service.userState : null
    root.guide = Model.afterSwitch(Model.initialScope(channels, userState))
    root.cursorIndex = 0
    root.disarmPointer()
    root.rebuildDisplay()
    root.cursorIndex = Model.cursorFor(root.currentRows, root.playingId)
    root.scrollToCursor()
    root.refocus()
  }

  function showSwitched(id) {
    if (root.switchPendingId === "" || String(id) !== root.switchPendingId) return
    root.switchPendingId = ""
    var leave = root.switchPendingLeave
    root.switchPendingLeave = false
    var view = root.findSourceView(id)
    var count = root.serviceReady ? root.service.channels.length : -1
    root.showTransient(Model.sourceTransient("switched", { label: view ? view.label : root.activeSourceLabel, channelCount: count }))
    // A switch that probed first (D-SRC-04) finishes here: Enter leaves
    // Sources now, Space keeps the cursor on the row the re-sort moved.
    if (!root.inSources) return
    if (leave) { root.leaveToGuide(); return }
    root.pendingCursorId = String(id)
    root.syncSourceCursor()
  }

  // The service's `configured` flipped while the guide is open: the CLI
  // cleared or set the playlist (SR8), or a removal emptied the settings.
  // In Sources (and its confirm dialog / forms) nothing moves: the list stays
  // open (UX 1.7) and the Esc / `o` return reads `configured` at that moment
  // (handleEscape / leaveSources), landing in the first-run form when the
  // guide behind Sources is unconfigured by then.
  function onConfiguredFlip() {
    if (!root.opened || !root.serviceReady) return
    if (!root.configured && root.guideMode) root.enterFirstRun()
    else if (root.configured && root.firstRunHead && !root.formProbing) root.leaveToGuide()
  }

  // ---- forms (UX-SOURCES 1.2, 1.5, 1.6, 1.8)

  function enterFirstRun() {
    root.setGuide(Model.openFirstRun(root.guide))
    root.refocus()
  }

  // SR24: at the cap the add entry points show the `too_many` message
  // instead of opening a form.
  function sourcesFull() {
    if (root.sourceCount < Model.LIMITS.sources) return false
    root.showTransient(Model.sourceErrorMessage("too_many"))
    return true
  }

  function openAddForm() {
    if (root.sourcesFull()) return
    root.setGuide(Model.openAddForm(root.guide))
    root.refocus()
  }

  function openEditForm() {
    var view = root.sourceAt(root.sourceCursor)
    if (!view || !root.sourcesApi || typeof root.service.sourceForEdit !== "function") return
    // The only call that hands a URL to the guide; it goes into the form
    // state and the edit fields, nowhere else.
    var rec = root.service.sourceForEdit(view.id)
    if (!rec) return
    root.setGuide(Model.openEditForm(root.guide, view.id, { label: String(rec.label || ""), playlist: String(rec.playlistUrl || ""), epg: String(rec.epgUrl || "") }))
    root.refocus()
  }

  function openXtreamForm() {
    if (root.sourcesFull()) return
    root.setGuide(Model.openXtreamForm(root.guide, root.form ? root.form.origin : "sources"))
    root.refocus()
  }

  // SR25: a persist failure lands on the result line while a form is open,
  // in the footer otherwise.
  function showPersistFailed() {
    if (!root.opened) return
    if (root.formActive) root.failForm({ code: "persist_failed", field: "", message: Model.sourceErrorMessage("persist_failed") })
    else root.showTransient(Model.sourceErrorMessage("persist_failed"))
  }

  function cancelForm() {
    root.applyEscapeResult(Model.closeForm(root.guide, "cancel"))
  }

  function focusOpts() {
    return { savedSources: root.sourceCount }
  }

  // Enter on the focused element: fields and Save / Load submit, the links
  // and Cancel follow their action.
  function activateFormFocus() {
    var focus = root.formFocus
    if (focus === "cancel") root.cancelForm()
    else if (focus === "xtream") root.openXtreamForm()
    else if (focus === "savedSources") root.openSources()
    else root.submitForm()
  }

  function failForm(error) {
    root.setGuide(Model.withFormError(root.guide, error))
    root.refocus()
  }

  // A synchronous action result -> error line. `duplicate` names the
  // existing source's label; the copy always comes from Model.js.
  function resultError(result, field) {
    var code = result && result.code ? String(result.code) : "not_ready"
    var dup = code === "duplicate" && result ? root.findSourceView(result.id) : null
    return { code: code, field: field, message: Model.sourceErrorMessage(code, { label: dup ? dup.label : "", field: field === "epg" ? "epg" : "" }) }
  }

  // A `duplicate` of a record that never fetched (an earlier add that
  // failed, D8) is retried instead of refused.
  function retryIfUnfetched(result) {
    if (!result || result.code !== "duplicate" || typeof root.service.retrySource !== "function") return result
    var view = root.findSourceView(result.id)
    if (!view || Number(view.channelCount) >= 0) return result
    return root.service.retrySource(result.id)
  }

  function startProbe(id, host, kind) {
    root.pendingProbeId = String(id || "")
    root.setGuide(Model.withFormProbing(root.guide, true, { host: host, kind: kind }))
    root.refocus()
  }

  function submitForm() {
    var f = root.form
    if (!f || f.probing) return
    if (f.kind === "xtream") { root.submitXtream(); return }
    var values = Model.formSubmitValues(f)
    var v = Model.validateUrlForm(values, root.sourceList, f.sourceId)
    if (!v.ok) { root.failForm(v.error); return }
    if (!root.sourcesApi) { root.failForm(root.resultError(null, "playlist")); return }
    var result
    if (f.sourceId !== "") {
      if (typeof root.service.updateSource !== "function") { root.failForm(root.resultError(null, "playlist")); return }
      var changed = Model.normalizeSourceUrl(values.playlist) !== Model.normalizeSourceUrl(f.original.playlist)
      result = root.service.updateSource(f.sourceId, { label: v.label, playlistUrl: v.playlistUrl, epgUrl: v.epgUrl })
      if (!result || result.ok !== true) { root.failForm(root.resultError(result, "playlist")); return }
      if (changed) { root.startProbe(result.id ? result.id : f.sourceId, v.host, v.kind); return }
      root.finishForm("saved", { id: f.sourceId, channelCount: -1, groupCount: 0 })
      return
    }
    if (typeof root.service.addSource !== "function") { root.failForm(root.resultError(null, "playlist")); return }
    result = root.retryIfUnfetched(root.service.addSource({ label: v.label, playlistUrl: v.playlistUrl, epgUrl: v.epgUrl, kind: v.kind }))
    if (!result || result.ok !== true) { root.failForm(root.resultError(result, "playlist")); return }
    root.startProbe(result.id, v.host, v.kind)
  }

  function submitXtream() {
    var f = root.form
    var values = Model.formSubmitValues(f)
    var x = Model.xtreamUrls(values.server, values.username, values.password)
    if (!x.ok) { root.failForm({ code: x.code, field: x.field, message: x.message }); return }
    var lv = Model.validateLabel(values.label, root.sourceList, "")
    if (!lv.ok) { root.failForm({ code: lv.code, field: "label", message: lv.message }); return }
    if (!root.sourcesApi || typeof root.service.buildXtreamSource !== "function") { root.failForm(root.resultError(null, "server")); return }
    var result = root.service.buildXtreamSource({ server: values.server, username: values.username, password: values.password, label: lv.label })
    // UX-SOURCES 6.5: the password leaves the form state as soon as the
    // URLs are built; the form is never shown pre-filled again.
    root.guide = Model.withFormValue(root.guide, "password", "")
    result = root.retryIfUnfetched(result)
    if (!result || result.ok !== true) { root.failForm(root.resultError(result, "server")); return }
    root.startProbe(result.id, x.host, "url")
  }

  // sourceProbeFinished({ ok, id, channelCount, groupCount, reason, host }) (SR3).
  function onProbeFinished(result) {
    var r = result || {}
    if (!root.opened) return
    var id = String(r.id !== undefined && r.id !== null ? r.id : (r.sourceId !== undefined ? r.sourceId : ""))
    var formProbe = root.formActive && root.formProbing && !(root.pendingProbeId !== "" && id !== "" && id !== root.pendingProbeId)
    if (!formProbe) { root.onSwitchProbeFinished(r, id); return }
    if (r.cancelled === true) {
      // UX-SOURCES 5.5: no line, the form thaws with its values.
      root.pendingProbeId = ""
      root.setGuide(Model.withFormProbing(root.guide, false))
      root.refocus()
      return
    }
    if (r.ok === true) {
      var event = root.form.sourceId !== "" ? "saved" : (root.firstRunForm ? "loaded" : "added")
      root.finishForm(event, { id: id, host: String(r.host || root.form.probeHost), channelCount: Number(r.channelCount), groupCount: Number(r.groupCount) })
      return
    }
    var field = root.form.kind === "xtream" ? "server" : "playlist"
    root.failForm({ code: "probe", field: field, message: Model.probeFailureLine(r.reason, String(r.host || root.form.probeHost), root.form.probeKind) })
  }

  // A probe outside a form: Enter / Space on a never-fetched source, or an
  // IPC switch / retry (D-SRC-04). Success continues in showSwitched once
  // the service committed the switch; a failure becomes the Sources result
  // line (`<reason> from <host>`, UX 5.5) while the previous source stays
  // active (SR7, SR26). A cancelled probe leaves no line.
  function onSwitchProbeFinished(r, id) {
    if (r.ok === true) return
    if (root.switchPendingId !== "" && id === root.switchPendingId) {
      root.switchPendingId = ""
      root.switchPendingLeave = false
    }
    if (r.cancelled === true || !root.inSources) return
    var view = root.findSourceView(id)
    root.sourcesNotice = Model.probeFailureLine(r.reason, String(r.host || ""), view ? String(view.kind) : "url")
  }

  // Leave the form after a successful save: first run lands in the guide
  // with the counts transient, Sources lands on the saved row.
  function finishForm(event, info) {
    var result = Model.closeForm(root.guide, "saved")
    root.pendingProbeId = ""
    var counts = { channelCount: isFinite(Number(info.channelCount)) ? Number(info.channelCount) : -1, groupCount: Number(info.groupCount) || 0 }
    if (result.state.mode === "search") {
      root.guide = result.state
      root.cursorIndex = 0
      root.disarmPointer()
      root.rebuildDisplay()
      root.cursorIndex = Model.cursorFor(root.currentRows, root.playingId)
      root.scrollToCursor()
      root.showTransient(Model.sourceTransient("loaded", counts))
      root.refocus()
      return
    }
    root.setGuide(result.state)
    root.pendingCursorId = String(info.id || "")
    root.syncSourceCursor()
    // UX 5.3 / 5.5: `Added <label> - N channels in M groups`; the label is
    // the recorded one (the file name for a path, never `local file`), the
    // probe host only when the record is not in the list yet.
    var added = root.findSourceView(info.id)
    root.showTransient(Model.sourceTransient(event === "saved" ? "saved" : "added", { label: added ? String(added.label) : "", host: info.host, channelCount: counts.channelCount, groupCount: counts.groupCount }))
    root.refocus()
  }

  // ---- removal (UX-SOURCES 1.7)

  function startRemove() {
    if (!root.inSources || root.sourceCursorKind !== "source") return
    removeDialog.selectedIndex = 1
    root.setGuide(Model.startRemove(root.guide, root.sourceCount))
    root.refocus()
  }

  function cancelRemove() {
    root.setGuide(Model.withMode(root.guide, "sources"))
    root.refocus()
  }

  function confirmRemove() {
    var view = root.sourceAt(root.sourceCursor)
    if (!view || !root.sourcesApi || typeof root.service.removeSource !== "function") { root.cancelRemove(); return }
    var result = root.service.removeSource(view.id)
    if (!result || result.ok !== true) {
      root.cancelRemove()
      root.showTransient(Model.sourceErrorMessage(result ? result.code : "not_ready"))
      return
    }
    root.showTransient(Model.sourceTransient("removed", { label: view.label, wasActive: view.active }))
    var remaining = root.findSourceView(view.id) ? root.sourceCount - 1 : root.sourceCount
    root.setGuide(Model.afterRemove(root.guide, remaining))
    root.refocus()
  }

  // ---- fields (UX-SOURCES 2.3, 4.4)

  function formValue(id) {
    return root.form && root.form.values ? String(root.form.values[id] || "") : ""
  }

  function fieldMaskable(id) { return Model.fieldMaskable(root.form, id) }
  function fieldMasked(id) { return Model.fieldMasked(root.form, id) }

  // What the TextField shows: the masked rendering or the raw value.
  function fieldDisplay(id) {
    return root.fieldMasked(id) ? Model.maskUrl(root.formValue(id)) : root.formValue(id)
  }

  function fieldLabelText(id) {
    if (id === "label") return root.copy.fieldLabel
    if (id === "playlist") return root.copy.fieldPlaylist
    if (id === "epg") return root.copy.fieldEpg
    if (id === "server") return root.copy.fieldServer
    if (id === "username") return root.copy.fieldUsername
    if (id === "password") return root.copy.fieldPassword
    return ""
  }

  // The Label placeholder live-updates to the label Model.deriveLabel would
  // give the current Playlist / Server value (UX-SOURCES 1.5, 5.1).
  function fieldPlaceholder(id) {
    if (id === "label") {
      var f = root.form
      var derived = ""
      if (f && f.kind === "xtream") {
        var s = Model.validateSourceUrl(f.values.server)
        if (s.ok && s.kind === "http") derived = Model.deriveLabel(s.url)
      } else if (f) {
        var p = Model.validateSourceUrl(f.values.playlist)
        if (p.ok) derived = Model.deriveLabel(p.url, p.kind)
      }
      return derived !== "" ? derived : root.copy.placeholderOptional
    }
    if (id === "playlist") return root.copy.placeholderPlaylist
    if (id === "epg") return root.copy.placeholderEpg
    if (id === "server") return root.copy.placeholderServer
    return ""
  }

  function fieldAccessibleName(id) {
    if (id === "label") return root.copy.accessibleLabel
    if (id === "playlist") return root.copy.accessiblePlaylist
    if (id === "epg") return root.copy.accessibleEpg
    if (id === "server") return root.copy.accessibleServer
    if (id === "username") return root.copy.accessibleUsername
    if (id === "password") return root.copy.accessiblePassword
    return ""
  }

  function fieldItem(id) {
    for (var i = 0; i < fieldsRepeater.count; i++) {
      var row = fieldsRepeater.itemAt(i)
      if (row && row.fieldId === id) return row.input
    }
    return null
  }

  function focusFormItem() {
    if (!root.formActive || root.formProbing) return
    var focus = root.formFocus
    var item = root.fieldItem(focus)
    if (!item) {
      if (focus === "xtream") item = xtreamLink
      else if (focus === "savedSources") item = savedLink
      else if (focus === "cancel") item = cancelButton
      else item = submitButton
    }
    if (item && item.visible && item.enabled) item.forceActiveFocus()
  }

  // A field or button gained focus (mouse or our own forceActiveFocus):
  // keep the form state in step, which re-masks the element being left.
  function fieldFocused(id) {
    if (root.formActive && root.formFocus !== id) root.guide = Model.withFormFocus(root.guide, id)
  }

  // Text changed inside a TextField (typing, native paste, primary
  // selection): sanitize at the boundary and store it in the form state. A
  // masked field is readOnly, so a change there can only be our binding.
  function fieldEdited(id, text) {
    if (!root.formActive || root.fieldMasked(id)) return
    var value = String(text)
    if (value === root.formValue(id)) return
    var limit = Model.formCapacity(id)
    var typed = true
    var clean
    if (root.pasteArmed) {
      root.pasteArmed = false
      clean = Model.isUrlField(id) ? Model.sanitizeInput(value, limit) : Model.sanitizeTyping(value, limit)
      typed = false
    } else {
      clean = Model.sanitizeTyping(value, limit)
    }
    root.guide = Model.withFormValue(root.guide, id, clean, { typed: typed })
  }

  function setFieldValue(id, value, typed) {
    root.guide = Model.withFormValue(root.guide, id, Model.sanitizeTyping(value, Model.formCapacity(id)), { typed: typed })
  }

  function toggleRevealField(id) {
    if (!root.formActive || !root.fieldMaskable(id)) return
    root.fieldFocused(id)
    root.guide = Model.toggleReveal(root.guide, id)
    root.placeCaretAtEnd()
  }

  function placeCaretAtEnd() {
    Qt.callLater(function() {
      var item = root.fieldItem(root.formFocus)
      if (item && !item.readOnly) {
        item.forceActiveFocus()
        item.cursorPosition = item.length
      }
    })
  }

  function clipboardText() {
    var text = Quickshell.clipboardText
    return text === undefined || text === null ? "" : String(text)
  }

  // Paste into a masked field replaces the whole value and masks it again
  // before the next frame (UX-SOURCES 2.3, 6.6).
  function pasteReplace(id) {
    if (root.pasteViaProcess) { root.pasteInto(id); return }
    root.guide = Model.withFormValue(root.guide, id, Model.sanitizeInput(root.clipboardText(), Model.formCapacity(id)))
  }

  // wl-paste fallback path (D9): asks the service, which answers through a
  // `clipboardText(text)` signal; guarded because the verb may not exist.
  function pasteInto(id) {
    if (root.serviceReady && typeof root.service.requestClipboard === "function") root.service.requestClipboard()
  }

  function pasteFromProcess(text) {
    if (!root.formActive || !Model.isFormField(root.form, root.formFocus)) return
    root.guide = Model.withFormValue(root.guide, root.formFocus, Model.sanitizeInput(text, Model.formCapacity(root.formFocus)))
  }

  // Form keys seen before the focused TextField / Button (Keys.forwardTo):
  // Tab / Shift+Tab / Up / Down, Enter, Esc, Ctrl+U, Ctrl+R, paste and the
  // masked-field replacement rules. Everything else falls through to Qt's
  // native editing (caret, selection, Ctrl+Backspace, Ctrl+A).
  function handleFormKey(event) {
    var f = root.form
    if (!f) return false
    var key = event.key
    var focus = root.formFocus
    var isPaste = event.matches(StandardKey.Paste)
    if (!isPaste) root.pasteArmed = false
    if (key === Qt.Key_Escape) { root.handleEscape(); return true }
    if (f.probing) return true
    // Shift+Tab arrives as Key_Backtab or as Key_Tab with the modifier
    // depending on the input path (the PanelKeyCatcher checks both too).
    var backward = key === Qt.Key_Backtab || (key === Qt.Key_Tab && (event.modifiers & Qt.ShiftModifier)) || key === Qt.Key_Up
    if (backward) { root.setGuide(Model.moveFormFocus(root.guide, -1, root.focusOpts())); return true }
    if (key === Qt.Key_Tab || key === Qt.Key_Down) { root.setGuide(Model.moveFormFocus(root.guide, 1, root.focusOpts())); return true }
    if (key === Qt.Key_Return || key === Qt.Key_Enter) { root.activateFormFocus(); return true }
    if (!Model.isFormField(f, focus)) return false
    var masked = root.fieldMasked(focus)
    if (key === Qt.Key_U && event.modifiers === Qt.ControlModifier) { root.setFieldValue(focus, "", true); return true }
    if (key === Qt.Key_R && event.modifiers === Qt.ControlModifier) {
      if (root.fieldMaskable(focus)) root.toggleRevealField(focus)
      return true
    }
    if (isPaste) {
      if (masked) { root.pasteReplace(focus); return true }
      if (root.pasteViaProcess) { root.pasteInto(focus); return true }
      root.pasteArmed = true
      return false
    }
    if (!masked) return false
    // Masked = fully selected (UX-SOURCES 2.3): typing, Backspace and
    // Ctrl+Backspace replace or clear the whole value; navigation is a no-op.
    if (key === Qt.Key_Backspace || key === Qt.Key_Delete) { root.setFieldValue(focus, "", true); return true }
    if (event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)) return true
    if (event.text && event.text.length === 1 && event.text.charCodeAt(0) >= 32 && event.text.charCodeAt(0) !== 127) {
      root.setFieldValue(focus, event.text, true)
      root.placeCaretAtEnd()
      return true
    }
    return true
  }

  ListModel { id: groupModel }

  PointerMoveGate {
    id: pointerGate
    referenceItem: card
  }

  Timer {
    id: rebuildTimer
    interval: 0
    repeat: false
    onTriggered: root.rebuildDisplay()
  }

  Timer {
    id: transientTimer
    interval: root.transientMs
    repeat: false
    onTriggered: root.transientText = ""
  }

  // M2-03 2.5, the first commit trigger: numberEntryMs since the last
  // accepted key. A commit does not play (CN1).
  Timer {
    id: numberTimer
    interval: root.numberEntryMs
    repeat: false
    onTriggered: root.numberTimerFired()
  }

  // Only the row SET depends on these; decorations (playing, failed, EPG,
  // favorite star) are delegate bindings over the service's maps.
  Connections {
    target: root.service
    // The Sources signals (SR3) may not exist on the service yet.
    ignoreUnknownSignals: true
    function onChannelsChanged() { root.groupsDirty = true; root.scheduleRebuild() }
    function onUserStateChanged() { root.groupsDirty = true; root.scheduleRebuild() }
    // UX 6.1: a manual refresh ends with `Refreshed - N channels` in the
    // status slot for the transient window (D-LIVE-05).
    function onPlaylistRefreshed(channelCount, manual) {
      if (manual && root.opened) root.showTransient(root.copy.transientRefreshed + Model.SEP + Model.pluralChannels(channelCount))
    }
    function onSourceProbeFinished(result) { root.onProbeFinished(result) }
    function onSourcesChanged() { root.syncSourceCursor() }
    function onSourceSwitched(id) { root.showSwitched(id) }
    function onSourcesPersistFailed(reason) { root.showPersistFailed() }
    function onConfiguredChanged() { root.onConfiguredFlip() }
    function onClipboardText(text) { root.pasteFromProcess(text) }
  }

  // Form key handler target (Keys.forwardTo on every field and button).
  Item {
    id: formKeys
    Keys.onPressed: function(event) {
      if (root.formActive && root.handleFormKey(event)) event.accepted = true
    }
  }

  PanelWindow {
    id: panel
    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "omarchy-iptv"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore

    Rectangle {
      anchors.fill: parent
      color: root.scrim
    }

    MouseArea {
      anchors.fill: parent
      onClicked: root.dismiss()
    }

    BorderSurface {
      id: card
      width: root.cardWidth
      height: root.cardHeight
      radius: root.cornerRadius
      anchors.centerIn: parent
      color: root.background
      borderSpec: root.borderSpec
      padding: root.contentMargin
      Accessible.role: Accessible.Dialog
      Accessible.name: root.copy.accessibleCard

      MouseArea { anchors.fill: parent; onClicked: {} }

      // Key host: search-mode keys and the shared extras live here; the
      // PanelKeyCatcher child owns list mode and is blocked in search mode
      // so every key falls through to this handler (UX 3, R1).
      Item {
        id: keyHost
        anchors.fill: parent
        // Above the content while the confirm dialog is open (clipboard precedent).
        z: root.confirmOpen ? 20 : 0

        Keys.onPressed: function(event) {
          if (root.swallowKey) {
            root.swallowKey = false
            event.accepted = true
            return
          }
          if (root.confirmOpen) {
            if (removeDialog.handleKey(event)) event.accepted = true
            return
          }
          if (root.formActive) {
            // Reached only while no field has focus (the form is frozen by a
            // probe): Esc cancels it.
            if (root.handleFormKey(event)) event.accepted = true
            return
          }
          if (root.searchMode) {
            if (root.handleSearchKey(event)) event.accepted = true
            return
          }
          if (root.handleSharedKey(event)) event.accepted = true
        }

        PanelKeyCatcher {
          id: keyCatcher
          anchors.fill: parent
          blocked: !root.catcherLive
          // M2-03 2.9: the five handlers below end the number buffer before
          // doing their own job, so j/k, Tab and x never act on a half-typed
          // number and never leave one live behind them.
          onMoveRequested: function(dx, dy) {
            if (root.inSources) {
              if (dy !== 0) root.moveSourceCursorBy(dy, true)
              return
            }
            root.endNumberEntry(true)
            if (dy !== 0) root.moveCursorBy(dy, true)
            else if (dx !== 0) root.moveScopeBy(dx)
          }
          onReturnRequested: root.enterPending = true
          onActivateRequested: {
            var enter = root.enterPending
            root.enterPending = false
            if (root.inSources) { root.activateSourceRow(root.sourceCursor, !enter); return }
            // CN1: Enter and Space keep exactly the meanings UX 3.1 gives
            // them. The buffer commits first and then they play what the
            // preview selected -- unless the number resolved to nothing, in
            // which case the commit refuses to play and says so.
            if (root.numberEntryActive) {
              root.commitNumberEntry({ play: true, keepOpen: !enter, reason: "enter" })
              return
            }
            root.disarmNumberResume()
            root.activate(!enter)
          }
          onCloseRequested: root.handleEscape()
          onDeleteRequested: {
            if (root.inSources) { root.startRemove(); return }
            root.endNumberEntry(true)
            root.removeAt(root.cursorIndex)
          }
          onTabRequested: function(direction) {
            if (root.inSources) return
            root.endNumberEntry(true)
            root.switchMode()
          }
          onTextKey: function(text) {
            if (root.inSources) { root.handleSourcesLetter(text); return }
            // Backspace and Delete both have a one-character event.text
            // ("\b", "\u007f") and reach this handler, so without the
            // control guard they would commit the buffer before
            // handleSharedKey could see them (2.9).
            if (text.charCodeAt(0) < 32 || text.charCodeAt(0) === 127) return
            // Digits, "." and "," are extended in handleSharedKey; the same
            // event reaches it because PanelKeyCatcher's printable fallback
            // does not accept the event.
            if (Model.isNumberEntryKey(text)) return
            root.endNumberEntry(true)
            root.handleListLetter(text)
          }
        }

        // Remove confirmation (UX-SOURCES 1.7 / 3.5): the kit dialog with
        // the guide's menu tokens, `Remove` preselected as the clipboard
        // preselects `Delete`; its own scrim cancels only the dialog.
        ConfirmDialog {
          id: removeDialog
          anchors.fill: parent
          opened: root.confirmOpen
          z: 10
          message: root.confirmMessage
          cancelText: root.copy.buttonCancel
          confirmText: root.copy.buttonRemove
          background: root.background
          foreground: root.foreground
          scrim: root.scrim
          selectedBackground: root.selectedBackground
          selectedText: root.selectedText
          fontFamily: root.fontFamily
          cornerRadius: root.cornerRadius
          Accessible.role: Accessible.Dialog
          Accessible.name: root.confirmMessage
          onCanceled: root.cancelRemove()
          onConfirmed: root.confirmRemove()
        }
      }

      Column {
        id: layout
        anchors.fill: parent
        anchors.topMargin: card.contentTopInset
        anchors.rightMargin: card.contentRightInset
        anchors.bottomMargin: card.contentBottomInset
        anchors.leftMargin: card.contentLeftInset
        spacing: root.contentSpacing

        // ---- header: synthetic search line + scope label
        Item {
          width: parent.width
          height: root.headerHeight

          Text {
            id: searchLine
            visible: root.headerShowsSearch
            textFormat: Text.PlainText
            anchors.left: parent.left
            anchors.right: scopeLabel.left
            anchors.rightMargin: Style.spacing.md
            anchors.verticalCenter: parent.verticalCenter
            text: root.query !== "" ? root.query : root.copy.searchPlaceholder
            color: root.foreground
            opacity: root.query !== "" ? 1 : 0.58
            font.family: root.fontFamily
            font.pixelSize: Style.font.heading
            elide: Text.ElideRight
            Accessible.role: Accessible.EditableText
            Accessible.name: root.copy.accessibleSearch
            Accessible.description: root.query
          }

          // Screen title for Sources and the forms opened from it (UX-SOURCES 4.2).
          Text {
            id: headerTitle
            visible: !root.headerShowsSearch
            textFormat: Text.PlainText
            anchors.left: parent.left
            anchors.right: scopeLabel.left
            anchors.rightMargin: Style.spacing.md
            anchors.verticalCenter: parent.verticalCenter
            text: root.headerTitle
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.heading
            elide: Text.ElideRight
            Accessible.role: Accessible.Heading
            Accessible.name: root.headerTitle
          }

          Text {
            id: scopeLabel
            textFormat: Text.PlainText
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: root.headerRight
            color: root.foreground
            opacity: 0.52
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        // ---- banner (UX 4.6 / 5.7)
        Rectangle {
          id: banner
          width: parent.width
          height: root.bannerHeight
          radius: root.cornerRadius
          visible: root.bannerKind !== "none"
          // Only the playlist failure is urgent-tinted; the EPG banners are
          // low emphasis (UX 6.3): the alert glyph and the word carry it.
          color: root.bannerKind === "playlistError"
            ? Util.alpha(root.urgent, 0.10)
            : Style.normalFillFor(root.foreground, root.accent)
          opacity: visible ? 1 : 0
          Behavior on opacity { NumberAnimation { duration: root.bannerFadeMs; easing.type: Easing.OutCubic } }
          Accessible.role: Accessible.AlertMessage
          Accessible.name: root.bannerText

          Row {
            anchors.fill: parent
            anchors.leftMargin: Style.space(10)
            anchors.rightMargin: Style.space(10)
            spacing: Style.space(8)

            Text {
              anchors.verticalCenter: parent.verticalCenter
              textFormat: Text.PlainText
              text: root.bannerKind === "epgPending" ? Model.GLYPHS.loading : Model.GLYPHS.alert
              color: root.bannerKind === "epgPending" ? root.foreground : root.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.icon
            }

            Text {
              anchors.verticalCenter: parent.verticalCenter
              width: parent.width - Style.space(28)
              textFormat: Text.PlainText
              text: root.bannerText
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              elide: Text.ElideRight
            }
          }
        }

        // ---- body: group column + channel list (or an empty state)
        Item {
          id: body
          width: parent.width
          height: parent.height - root.headerHeight - root.footerHeight - root.contentSpacing * 2 - (banner.visible ? root.bannerHeight + root.contentSpacing : 0)

          Row {
            id: guideRow
            anchors.fill: parent
            spacing: 0
            visible: root.guideMode

            // Group column (UX 2.2 / 2.3)
            Item {
              id: columnHost
              visible: root.showColumn
              width: visible ? root.columnWidth + Style.normalBorderWidth + root.contentMargin : 0
              height: parent.height

              ListView {
                id: groupList
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: pinnedSeparator.top
                anchors.bottomMargin: Style.space(6)
                width: root.columnWidth
                model: groupModel
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                cacheBuffer: root.groupEntryHeight * 4
                Accessible.role: Accessible.List
                Accessible.name: root.copy.accessibleGroups
                onHeightChanged: root.positionColumn()

                delegate: Item {
                  id: groupRow
                  required property int index
                  required property string scopeId
                  required property string label
                  required property int count
                  required property string kind

                  readonly property bool isHeader: kind === "header"
                  readonly property bool selected: !isHeader && scopeId === root.scopeId

                  width: ListView.view.width
                  height: isHeader ? root.groupEntryHeight + Style.space(10) : root.groupEntryHeight
                  Accessible.role: isHeader ? Accessible.Heading : Accessible.ListItem
                  Accessible.name: isHeader ? label : label + ", " + Model.pluralChannels(count)
                  Accessible.selected: selected

                  PanelSectionHeader {
                    visible: groupRow.isHeader
                    anchors.left: parent.left
                    anchors.leftMargin: Style.space(10)
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: (root.groupEntryHeight - Style.font.caption) / 2
                    text: groupRow.label
                    foreground: root.foreground
                    fontFamily: root.fontFamily
                  }

                  Rectangle {
                    visible: !groupRow.isHeader
                    anchors.fill: parent
                    radius: root.cornerRadius
                    color: groupRow.selected ? root.selectedBackground : "transparent"

                    Text {
                      textFormat: Text.PlainText
                      anchors.left: parent.left
                      anchors.right: countText.left
                      anchors.leftMargin: Style.space(10)
                      anchors.rightMargin: Style.space(6)
                      anchors.verticalCenter: parent.verticalCenter
                      text: groupRow.label
                      color: groupRow.selected ? root.selectedText : root.foreground
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.body
                      elide: Text.ElideRight
                    }

                    Text {
                      id: countText
                      textFormat: Text.PlainText
                      anchors.right: parent.right
                      anchors.rightMargin: Style.space(10)
                      anchors.verticalCenter: parent.verticalCenter
                      text: Model.formatCount(groupRow.count)
                      color: root.foreground
                      opacity: 0.45
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                      horizontalAlignment: Text.AlignRight
                    }

                    MouseArea {
                      anchors.fill: parent
                      cursorShape: Qt.PointingHandCursor
                      onClicked: root.setScope(groupRow.scopeId)
                    }
                  }
                }
              }

              // Wheel over the column moves the selection one entry per tick (UX 7.3).
              MouseArea {
                anchors.fill: groupList
                acceptedButtons: Qt.NoButton
                onWheel: function(wheel) {
                  var step = Util.wheelSteps(root.columnWheel, wheel.angleDelta.y)
                  root.columnWheel = step.remainder
                  if (step.steps !== 0) root.moveScopeBy(step.steps > 0 ? -1 : 1)
                  wheel.accepted = true
                }
              }

              // Pinned `Sources` row (UX-SOURCES 3.7 / 4.5): below the group
              // ListView, never scrolls, a button rather than a scope (h / l
              // never land on it; hover paints the kit hover fill).
              Rectangle {
                id: pinnedSeparator
                anchors.left: parent.left
                anchors.bottom: pinnedSources.top
                anchors.bottomMargin: Style.space(6)
                width: root.columnWidth
                height: Style.normalBorderWidth
                color: Util.alpha(root.border, 0.28)
              }

              Rectangle {
                id: pinnedSources
                anchors.left: parent.left
                anchors.bottom: parent.bottom
                width: root.columnWidth
                height: root.groupEntryHeight
                radius: root.cornerRadius
                color: pinnedMouse.containsMouse ? Style.hoverFillFor(root.foreground, root.accent) : "transparent"
                Behavior on color { ColorAnimation { duration: 60 } }
                Accessible.role: Accessible.Button
                Accessible.name: Model.sourcesRowAccessibleName(root.sourceCount)

                Text {
                  id: pinnedGlyph
                  textFormat: Text.PlainText
                  anchors.left: parent.left
                  anchors.leftMargin: Style.space(10)
                  anchors.verticalCenter: parent.verticalCenter
                  text: Model.GLYPHS.sources
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.iconSmall
                }

                Text {
                  textFormat: Text.PlainText
                  anchors.left: pinnedGlyph.right
                  anchors.leftMargin: Style.spacing.labelGap
                  anchors.right: pinnedCount.left
                  anchors.rightMargin: Style.space(6)
                  anchors.verticalCenter: parent.verticalCenter
                  text: root.copy.sourcesTitle
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  elide: Text.ElideRight
                }

                Text {
                  id: pinnedCount
                  textFormat: Text.PlainText
                  anchors.right: parent.right
                  anchors.rightMargin: Style.space(10)
                  anchors.verticalCenter: parent.verticalCenter
                  text: Model.formatCount(root.sourceCount)
                  color: root.foreground
                  opacity: 0.45
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  horizontalAlignment: Text.AlignRight
                }

                MouseArea {
                  id: pinnedMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.openSources()
                }
              }

              Rectangle {
                anchors.left: groupList.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: Style.normalBorderWidth
                color: Util.alpha(root.border, 0.28)
              }
            }

            // Channel list (UX 2.4 / 4.3 / 5.4 / 5.6)
            Item {
              id: listHost
              width: parent.width - columnHost.width
              height: parent.height
              clip: true

              ListView {
                id: resultList
                anchors.fill: parent
                // Integer model over root.currentRows: setting the count is
                // O(1) for any scope size and only the visible delegates
                // (plus cacheBuffer) are ever created (D-LIVE-01).
                model: root.rowCount
                clip: true
                spacing: root.rowSpacing
                boundsBehavior: Flickable.StopAtBounds
                cacheBuffer: root.rowHeight * 4
                Accessible.role: Accessible.List
                Accessible.name: root.copy.accessibleChannels + Model.scopeName(root.effectiveScope)
                onHeightChanged: root.scrollToCursor()

                delegate: BorderSurface {
                  id: row
                  required property int index

                  // The row's channel and its decorations are resolved here,
                  // per instantiated delegate, from the service's lookups.
                  readonly property var channel: row.index < root.rowCount ? (root.currentRows[row.index] || null) : null
                  readonly property string channelId: row.channel ? Model.channelId(row.channel) : ""
                  readonly property string name: row.channel ? String(row.channel.name || "") : ""
                  readonly property string group: row.channel ? Model.primaryGroup(row.channel) : ""
                  readonly property string tvgId: row.channel ? String(row.channel.tvgId || "") : ""
                  readonly property bool showGroup: !root.scopeIsGroup
                  readonly property bool favorite: row.channelId !== "" && root.favoriteSet[row.channelId] === true
                  readonly property bool playing: row.channelId !== "" && row.channelId === root.playingId
                  readonly property string failedAt: row.channelId !== "" && root.failedMap[row.channelId] ? String(root.failedMap[row.channelId]) : ""
                  readonly property var epg: Model.epgFields(row.tvgId !== "" ? root.epgMap[row.tvgId] : null, root.nowSec)
                  readonly property string nowTitle: row.epg.nowTitle
                  readonly property string nextTitle: row.epg.nextTitle
                  readonly property int nowStart: row.epg.nowStart
                  readonly property int nowStop: row.epg.nowStop
                  readonly property string until: row.epg.until

                  // M2-03 4.2 / CN6: the label prepareChannels derived, and
                  // an empty string for a channel with no usable number --
                  // not "-", not a dimmed 0. A placeholder in a numeric
                  // column reads as a value; the absence is the information.
                  readonly property string chno: row.channel && typeof row.channel.chnoLabel === "string" ? row.channel.chnoLabel : ""
                  readonly property bool hasCursor: index === root.cursorIndex
                  readonly property string detail: Model.rowDetail({ showGroup: showGroup, group: group, failedAt: failedAt, nowTitle: nowTitle, nextTitle: nextTitle })
                  readonly property bool showProgress: nowTitle !== "" && nowStop > nowStart && failedAt === ""
                  readonly property real fraction: showProgress ? Model.epgFraction(root.nowSec, nowStart, nowStop) : 0
                  readonly property color primaryColor: hasCursor ? root.selectedText : root.foreground

                  width: ListView.view.width
                  height: root.rowHeight
                  radius: root.cornerRadius
                  color: hasCursor ? root.selectedBackground : "transparent"
                  borderSpec: hasCursor ? root.selectedBorderSpec : root.noBorderSpec
                  Accessible.role: Accessible.ListItem
                  Accessible.name: Model.rowAccessibleName({ name: name, chno: chno, favorite: favorite, playing: playing, nowTitle: nowTitle, until: until, failedAt: failedAt })
                  Accessible.focused: hasCursor

                  Item {
                    id: rowContent
                    anchors.fill: parent
                    anchors.leftMargin: Style.space(12)
                    anchors.rightMargin: Style.space(12)
                    anchors.topMargin: Style.space(8)
                    anchors.bottomMargin: Style.space(8)

                    // number slot (M2-03 4.2): right-aligned, at the left
                    // edge, BEFORE the favorite slot -- the television and
                    // EPG-grid convention, and it puts the digits flush
                    // against the card's left content margin so the column
                    // scans as a column. Zero width on an unnumbered
                    // playlist, so those rows are drawn exactly as v0.2.0
                    // drew them. Never bold, not even on the playing row:
                    // the name already carries Font.Bold and two bold
                    // elements in one row is noise.
                    Text {
                      id: numberText
                      visible: root.numberWidth > 0
                      width: root.numberWidth
                      anchors.left: parent.left
                      anchors.top: parent.top
                      height: lead.height
                      textFormat: Text.PlainText
                      text: row.chno
                      color: row.hasCursor ? root.selectedText : root.foreground
                      opacity: row.hasCursor ? 0.8 : 0.52
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.body
                      horizontalAlignment: Text.AlignRight
                      verticalAlignment: Text.AlignVCenter
                    }

                    // lead slot: favorite star
                    Text {
                      id: lead
                      width: root.leadWidth
                      anchors.left: numberText.visible ? numberText.right : parent.left
                      anchors.leftMargin: numberText.visible ? Style.spacing.labelGap : 0
                      anchors.top: parent.top
                      height: Style.font.title + Style.space(2)
                      textFormat: Text.PlainText
                      text: row.favorite ? Model.GLYPHS.star : ""
                      color: row.primaryColor
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.icon
                      horizontalAlignment: Text.AlignHCenter
                      verticalAlignment: Text.AlignVCenter
                    }

                    // right meta: until HH:MM
                    Text {
                      id: meta
                      anchors.right: parent.right
                      anchors.top: parent.top
                      height: lead.height
                      textFormat: Text.PlainText
                      text: row.until !== "" && row.failedAt === "" ? "until " + row.until : ""
                      visible: text !== ""
                      // Natural width, no `width: implicitWidth` binding: rows
                      // are reused now (D-LIVE-01), and a live text change
                      // re-entering width through visible -> implicitWidth
                      // is a binding loop. Neighbours anchor on `visible`.
                      color: root.foreground
                      opacity: 0.52
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                      horizontalAlignment: Text.AlignRight
                      verticalAlignment: Text.AlignVCenter
                    }

                    // trail slot: playing or failed glyph
                    Text {
                      id: trail
                      width: root.trailWidth
                      anchors.right: meta.visible ? meta.left : parent.right
                      anchors.rightMargin: meta.visible ? Style.space(8) : 0
                      anchors.top: parent.top
                      height: lead.height
                      textFormat: Text.PlainText
                      text: row.playing ? Model.GLYPHS.play : (row.failedAt !== "" ? Model.GLYPHS.alert : "")
                      color: row.primaryColor
                      opacity: row.failedAt !== "" && !row.playing ? 0.8 : 1
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.icon
                      horizontalAlignment: Text.AlignHCenter
                      verticalAlignment: Text.AlignVCenter
                    }

                    Text {
                      id: nameText
                      anchors.left: lead.right
                      anchors.right: trail.left
                      anchors.rightMargin: Style.space(6)
                      anchors.top: parent.top
                      height: lead.height
                      textFormat: Text.PlainText
                      text: row.name
                      color: row.primaryColor
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.title
                      font.bold: row.playing
                      elide: Text.ElideRight
                      verticalAlignment: Text.AlignVCenter
                    }

                    Text {
                      id: detailText
                      visible: root.rowsHaveDetail
                      anchors.left: lead.right
                      anchors.right: parent.right
                      anchors.top: nameText.bottom
                      textFormat: Text.PlainText
                      text: row.detail
                      color: root.foreground
                      opacity: 0.52
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.bodySmall
                      elide: Text.ElideRight
                    }

                    // EPG progress hairline (UX 5.6)
                    Rectangle {
                      id: track
                      visible: root.rowsHaveDetail && row.showProgress
                      anchors.left: lead.right
                      anchors.right: meta.visible ? meta.left : parent.right
                      anchors.bottom: parent.bottom
                      height: Style.space(2)
                      radius: Math.min(root.cornerRadius, Style.space(1))
                      color: Util.alpha(root.foreground, 0.12)

                      Rectangle {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        width: parent.width * row.fraction
                        radius: parent.radius
                        color: row.hasCursor ? Util.alpha(root.selectedText, 0.7) : Util.alpha(root.accent, 0.55)
                      }
                    }
                  }

                  MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onPositionChanged: function(mouse) { root.selectFromPointer(row.index, row, mouse) }
                    onClicked: root.activateIndex(row.index, false)
                  }

                  // Lead-slot hit target (UX 7.3): toggles favorite without
                  // playing. M2-03 4.2: anchored to `lead`, not to the row's
                  // left edge, or a click on the number column would toggle
                  // the favorite. UX 7.3's Style.space(28) minimum stands.
                  MouseArea {
                    anchors.left: lead.left
                    anchors.leftMargin: -Style.space(12)
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    width: Math.max(Style.space(28), Style.space(12) + root.leadWidth)
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.toggleFavoriteAt(row.index)
                  }
                }
              }

              // Number entry chip (M2-03 4.3). Top right is where a
              // television puts it and the bottom right is the footer's. It
              // sits over the first row's `until HH:MM` by design; the guide
              // gets that back the instant entry ends. The fill is the
              // neutral banner fill of UX 5.7, not Color.urgent: typing a
              // number is not an error state.
              Rectangle {
                id: numberChip
                visible: root.numberEntryActive
                z: 5
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.topMargin: Style.spacing.md
                anchors.rightMargin: Style.spacing.md
                width: chipRow.width + Style.spacing.controlPaddingX * 2
                height: Math.max(Style.space(34), Style.font.heading + Style.spacing.controlPaddingY * 2)
                radius: root.cornerRadius
                color: Style.normalFillFor(root.foreground, root.accent)
                Accessible.role: Accessible.AlertMessage
                Accessible.name: "Entering channel number " + root.numberBuffer
                  + (root.numberResolution.kind === "none" ? ", no match" : "")

                // Each child carries its own height and centres its text in
                // it. No vertical anchor to the Row: the Row's height is
                // derived from its children, so anchoring a child to it
                // would be circular.
                Row {
                  id: chipRow
                  anchors.centerIn: parent
                  spacing: Style.spacing.labelGap
                  readonly property int lineHeight: numberChip.height - Style.spacing.controlPaddingY * 2

                  Text {
                    height: chipRow.lineHeight
                    text: Model.GLYPHS.dialpad
                    textFormat: Text.PlainText
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.icon
                    verticalAlignment: Text.AlignVCenter
                  }

                  Text {
                    height: chipRow.lineHeight
                    text: root.numberBuffer
                    textFormat: Text.PlainText
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.heading
                    verticalAlignment: Text.AlignVCenter
                  }

                  // No colour carries meaning on its own (UX 7.2): the miss
                  // is the word, not a tint.
                  Text {
                    height: chipRow.lineHeight
                    visible: root.numberResolution.kind === "none"
                    text: Model.SEP + "no match"
                    textFormat: Text.PlainText
                    color: root.foreground
                    opacity: 0.52
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    verticalAlignment: Text.AlignVCenter
                  }
                }
              }

              // Scroll edge fades (UX 5.2), strength tracks the hidden distance.
              Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: Math.min(Style.space(28), parent.height / 2)
                visible: opacity > 0
                opacity: resultList.contentHeight > resultList.height
                  ? Math.max(0, Math.min(1, (resultList.contentY - resultList.originY) / height))
                  : 0
                gradient: Gradient {
                  GradientStop { position: 0; color: root.background }
                  GradientStop { position: 1; color: Util.alpha(root.background, 0) }
                }
              }

              Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: Math.min(Style.space(28), parent.height / 2)
                visible: opacity > 0
                opacity: resultList.contentHeight > resultList.height
                  ? Math.max(0, Math.min(1, (resultList.originY + resultList.contentHeight - resultList.height - resultList.contentY) / height))
                  : 0
                gradient: Gradient {
                  GradientStop { position: 0; color: Util.alpha(root.background, 0) }
                  GradientStop { position: 1; color: root.background }
                }
              }
            }
          }

          // ---- empty states (UX 4.4 / 4.5 / 4.6 / 6.3)
          Column {
            id: emptyState
            anchors.centerIn: parent
            width: Math.min(body.width, Style.space(640))
            spacing: Style.space(8)
            // The Sources screens own the body in their modes; the
            // unconfigured state normally shows as the first-run form.
            visible: root.emptyKind !== "" && root.guideMode

            readonly property string glyph: {
              if (root.emptyKind === "loading") return Model.GLYPHS.loading
              if (root.emptyKind === "error" || root.emptyKind === "service") return Model.GLYPHS.tvOff
              return Model.GLYPHS.tv
            }
            readonly property bool emptyPlaylist: root.emptyKind === "error" && root.service.statusReason === root.copy.emptyPlaylistTitle
            readonly property string title: {
              if (root.emptyKind === "service") return root.copy.serviceTitle
              if (root.emptyKind === "unconfigured") return root.copy.unconfiguredTitle
              if (root.emptyKind === "loading") return root.copy.loadingTitle
              if (root.emptyKind === "error") return emptyState.emptyPlaylist ? root.copy.emptyPlaylistTitle : root.copy.errorTitle
              if (root.emptyKind === "noFavorites") return root.copy.noFavoritesTitle
              if (root.emptyKind === "noMatches") return Model.noMatchesTitle(root.query, root.scopeId)
              return root.copy.emptyScopeTitle + Model.scopeName(root.effectiveScope)
            }
            readonly property string prose: {
              if (root.emptyKind === "service") return root.copy.serviceProse
              if (root.emptyKind === "unconfigured") return root.copy.unconfiguredProse
              if (root.emptyKind === "loading") return root.service.sourceHost !== "" ? root.copy.loadingFrom + root.service.sourceHost : root.copy.loadingProse
              if (root.emptyKind === "error") {
                // D-SRC-06: an invalid configured URL shows the UX 5.4
                // sentence alone (no host: nothing was contacted).
                if (root.invalidSettingsText !== "") return root.invalidSettingsText
                if (emptyState.emptyPlaylist) return root.copy.emptyPlaylistProse + root.service.statusHost + Model.SEP + root.copy.emptyPlaylistCheck
                return root.service.statusReason + " from " + root.service.statusHost + Model.SEP + root.copy.errorCheck
              }
              if (root.emptyKind === "noFavorites") return root.copy.noFavoritesProse
              if (root.emptyKind === "noMatches") return root.scopeIsGroup ? root.copy.noMatchesGroup : root.copy.noMatchesAll
              return ""
            }
            readonly property string command: root.copy.unconfiguredCommand

            Text {
              width: parent.width
              text: emptyState.glyph
              color: root.selectedText
              opacity: 0.8
              font.family: root.fontFamily
              font.pixelSize: Style.font.displayLarge
              horizontalAlignment: Text.AlignHCenter
            }

            Text {
              width: parent.width
              textFormat: Text.PlainText
              text: emptyState.title
              color: root.foreground
              opacity: 0.7
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              horizontalAlignment: Text.AlignHCenter
              wrapMode: Text.WordWrap
            }

            Text {
              width: parent.width
              visible: text !== ""
              textFormat: Text.PlainText
              text: emptyState.prose
              color: root.foreground
              opacity: 0.7
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              horizontalAlignment: Text.AlignHCenter
              wrapMode: Text.WordWrap
            }

            // Command box (UX 4.4); click copies with wl-copy.
            Rectangle {
              visible: root.emptyKind === "unconfigured"
              anchors.horizontalCenter: parent.horizontalCenter
              width: Math.min(parent.width, commandText.implicitWidth + Style.space(16))
              height: commandText.implicitHeight + Style.space(16)
              radius: root.cornerRadius
              color: Style.normalFillFor(root.foreground, root.accent)

              Text {
                id: commandText
                anchors.centerIn: parent
                width: parent.width - Style.space(16)
                textFormat: Text.PlainText
                text: emptyState.command
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                elide: Text.ElideMiddle
                horizontalAlignment: Text.AlignHCenter
              }

              MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.copyCommand(emptyState.command)
              }
            }

            Text {
              visible: root.emptyKind === "unconfigured"
              width: parent.width
              textFormat: Text.PlainText
              text: root.copy.unconfiguredEpg
              color: root.foreground
              opacity: 0.7
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              horizontalAlignment: Text.AlignHCenter
              wrapMode: Text.WordWrap
            }

            Text {
              visible: root.emptyKind === "unconfigured"
              width: parent.width
              textFormat: Text.PlainText
              text: root.copy.unconfiguredWhere
              color: root.foreground
              opacity: 0.7
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              horizontalAlignment: Text.AlignHCenter
              wrapMode: Text.WordWrap
            }
          }

          // ---- Sources list (UX-SOURCES 3.2 / 4.1): every saved source as a
          // two-line row, then a separator and the two action rows. Rows
          // render view objects only (label, host, counts); never a URL.
          Item {
            id: sourcesHost
            anchors.fill: parent
            visible: root.inSources || root.confirmOpen
            clip: true

            ListView {
              id: sourceListView
              anchors.fill: parent
              model: root.sourceRowCount
              clip: true
              spacing: root.rowSpacing
              boundsBehavior: Flickable.StopAtBounds
              cacheBuffer: root.detailRowHeight * 4
              Accessible.role: Accessible.List
              Accessible.name: root.copy.accessibleSources
              onHeightChanged: root.scrollToSourceCursor()

              delegate: Item {
                id: srow
                required property int index

                readonly property string rowKind: Model.sourcesRowKind(srow.index, root.sourceCount)
                readonly property bool isSource: srow.rowKind === "source"
                readonly property var source: srow.isSource ? (root.sourceList[srow.index] || null) : null
                readonly property bool hasCursor: srow.index === root.sourceCursor
                readonly property bool active: !!(srow.source && srow.source.active)
                readonly property string label: srow.source ? String(srow.source.label) : (srow.rowKind === "add" ? root.copy.rowAdd : root.copy.rowXtream)
                readonly property string detail: srow.source ? Model.sourceDetail(srow.source, root.narrow) : ""
                readonly property string meta: srow.source && !root.narrow ? String(srow.source.lastUsedText) : ""
                readonly property string leadGlyph: srow.isSource ? (srow.active ? Model.GLYPHS.check : "") : (srow.rowKind === "add" ? Model.GLYPHS.plus : Model.GLYPHS.key)
                // The separator before the action rows travels with the first of them.
                readonly property bool separatorAbove: srow.rowKind === "add"
                readonly property int separatorHeight: srow.separatorAbove ? Style.space(6) * 2 + Style.normalBorderWidth : 0
                readonly property color primaryColor: srow.hasCursor ? root.selectedText : root.foreground

                width: ListView.view.width
                height: (srow.isSource ? root.detailRowHeight : root.singleRowHeight) + srow.separatorHeight
                Accessible.role: Accessible.ListItem
                Accessible.name: srow.source ? Model.sourceAccessibleName(srow.source) : srow.label
                Accessible.focused: srow.hasCursor
                Accessible.selected: srow.active

                Rectangle {
                  visible: srow.separatorAbove
                  anchors.left: parent.left
                  anchors.right: parent.right
                  anchors.leftMargin: Style.space(12)
                  anchors.rightMargin: Style.space(12)
                  anchors.top: parent.top
                  anchors.topMargin: Style.space(6)
                  height: Style.normalBorderWidth
                  color: Util.alpha(root.border, 0.28)
                }

                BorderSurface {
                  id: srowBody
                  anchors.left: parent.left
                  anchors.right: parent.right
                  anchors.top: parent.top
                  anchors.topMargin: srow.separatorHeight
                  height: srow.isSource ? root.detailRowHeight : root.singleRowHeight
                  radius: root.cornerRadius
                  color: srow.hasCursor ? root.selectedBackground : "transparent"
                  borderSpec: srow.hasCursor ? root.selectedBorderSpec : root.noBorderSpec

                  MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onPositionChanged: function(mouse) { root.selectSourceFromPointer(srow.index, srow, mouse) }
                    onClicked: root.activateSourceRow(srow.index, false)
                  }

                  Item {
                    anchors.fill: parent
                    anchors.leftMargin: Style.space(12)
                    anchors.rightMargin: Style.space(12)
                    anchors.topMargin: Style.space(8)
                    anchors.bottomMargin: Style.space(8)

                    Text {
                      id: slead
                      width: root.leadWidth
                      anchors.left: parent.left
                      anchors.top: parent.top
                      height: Style.font.title + Style.space(2)
                      textFormat: Text.PlainText
                      text: srow.leadGlyph
                      color: srow.primaryColor
                      opacity: srow.isSource ? 1 : 0.7
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.icon
                      horizontalAlignment: Text.AlignHCenter
                      verticalAlignment: Text.AlignVCenter
                    }

                    // Edit / remove buttons on the cursor row only (UX-SOURCES 4.1).
                    Row {
                      id: sactions
                      visible: srow.hasCursor && srow.isSource
                      anchors.right: parent.right
                      anchors.verticalCenter: slead.verticalCenter
                      spacing: Style.space(6)

                      PanelActionButton {
                        iconText: Model.GLYPHS.pencil
                        tooltipText: root.copy.tooltipEdit
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                        Accessible.role: Accessible.Button
                        Accessible.name: root.copy.tooltipEdit + " " + srow.label
                        onClicked: root.openEditForm()
                      }

                      PanelActionButton {
                        iconText: Model.GLYPHS.closeCircle
                        tooltipText: root.copy.tooltipRemove
                        foreground: root.foreground
                        hoverColor: root.urgent
                        fontFamily: root.fontFamily
                        Accessible.role: Accessible.Button
                        Accessible.name: root.copy.tooltipRemove + " " + srow.label
                        onClicked: root.startRemove()
                      }
                    }

                    Text {
                      id: smeta
                      anchors.right: sactions.visible ? sactions.left : parent.right
                      anchors.rightMargin: sactions.visible ? Style.space(8) : 0
                      anchors.top: parent.top
                      height: slead.height
                      textFormat: Text.PlainText
                      text: srow.meta
                      visible: text !== ""
                      color: root.foreground
                      opacity: 0.52
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                      horizontalAlignment: Text.AlignRight
                      verticalAlignment: Text.AlignVCenter
                    }

                    Text {
                      id: slabel
                      anchors.left: slead.right
                      anchors.right: smeta.visible ? smeta.left : (sactions.visible ? sactions.left : parent.right)
                      anchors.rightMargin: Style.space(6)
                      anchors.top: parent.top
                      height: slead.height
                      textFormat: Text.PlainText
                      text: srow.label
                      color: srow.primaryColor
                      opacity: srow.isSource ? 1 : 0.7
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.title
                      font.bold: srow.active
                      elide: Text.ElideRight
                      verticalAlignment: Text.AlignVCenter
                    }

                    Text {
                      visible: srow.isSource
                      anchors.left: slead.right
                      anchors.right: parent.right
                      anchors.top: slabel.bottom
                      textFormat: Text.PlainText
                      text: srow.detail
                      color: root.foreground
                      opacity: 0.52
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.bodySmall
                      elide: Text.ElideRight
                    }
                  }
                }
              }
            }

            Rectangle {
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              height: Math.min(Style.space(28), parent.height / 2)
              visible: opacity > 0
              opacity: sourceListView.contentHeight > sourceListView.height
                ? Math.max(0, Math.min(1, (sourceListView.contentY - sourceListView.originY) / height))
                : 0
              gradient: Gradient {
                GradientStop { position: 0; color: root.background }
                GradientStop { position: 1; color: Util.alpha(root.background, 0) }
              }
            }

            Rectangle {
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.bottom: parent.bottom
              height: Math.min(Style.space(28), parent.height / 2)
              visible: opacity > 0
              opacity: sourceListView.contentHeight > sourceListView.height
                ? Math.max(0, Math.min(1, (sourceListView.originY + sourceListView.contentHeight - sourceListView.height - sourceListView.contentY) / height))
                : 0
              gradient: Gradient {
                GradientStop { position: 0; color: Util.alpha(root.background, 0) }
                GradientStop { position: 1; color: root.background }
              }
            }
          }

          // ---- form column (UX-SOURCES 3.1 / 3.3 / 3.4 / 4.2): the first-run
          // input (in the empty-state column's place), the add / edit form
          // and the Xtream form. One Repeater over Model.formFields renders
          // the fields; the form state in Model.js owns values, focus,
          // reveal, error and probing.
          Column {
            id: formColumn
            anchors.centerIn: parent
            width: Math.min(body.width, Style.space(640))
            spacing: Style.spacing.rowGap
            visible: root.formActive
            Accessible.role: Accessible.Dialog
            Accessible.name: root.formAccessibleName

            readonly property int labelWidth: Style.space(96)
            readonly property int eyeSlot: Style.space(22) + Style.spacing.controlGap
            readonly property int fieldX: root.narrow ? 0 : labelWidth + Style.spacing.controlGap
            readonly property int fieldWidth: width - fieldX - eyeSlot

            Text {
              visible: root.firstRunHead
              width: parent.width
              text: Model.GLYPHS.tv
              color: root.selectedText
              opacity: 0.8
              font.family: root.fontFamily
              font.pixelSize: Style.font.displayLarge
              horizontalAlignment: Text.AlignHCenter
            }

            Text {
              visible: root.firstRunHead
              width: parent.width
              textFormat: Text.PlainText
              text: root.copy.unconfiguredTitle
              color: root.foreground
              opacity: 0.7
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              horizontalAlignment: Text.AlignHCenter
              wrapMode: Text.WordWrap
            }

            Text {
              visible: root.firstRunHead
              width: parent.width
              textFormat: Text.PlainText
              text: root.copy.firstRunProse
              color: root.foreground
              opacity: 0.7
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              horizontalAlignment: Text.AlignHCenter
              wrapMode: Text.WordWrap
            }

            Repeater {
              id: fieldsRepeater
              model: root.formFieldIds

              delegate: Item {
                id: fieldRow
                required property int index
                required property string modelData

                readonly property string fieldId: fieldRow.modelData
                readonly property alias input: field
                readonly property bool maskable: root.fieldMaskable(fieldRow.fieldId)
                readonly property bool masked: root.fieldMasked(fieldRow.fieldId)
                readonly property bool hasError: !!(root.formError && root.formError.field === fieldRow.fieldId)

                width: parent.width
                height: root.narrow ? fieldLabel.implicitHeight + Style.spacing.labelGap + field.implicitHeight : field.implicitHeight

                PanelSectionHeader {
                  id: fieldLabel
                  x: 0
                  y: root.narrow ? 0 : Math.round((field.height - height) / 2)
                  width: root.narrow ? parent.width : formColumn.labelWidth
                  text: root.fieldLabelText(fieldRow.fieldId)
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  elide: Text.ElideRight
                }

                TextField {
                  id: field
                  x: formColumn.fieldX
                  y: root.narrow ? fieldLabel.implicitHeight + Style.spacing.labelGap : 0
                  width: formColumn.fieldWidth
                  text: root.fieldDisplay(fieldRow.fieldId)
                  readOnly: fieldRow.masked
                  // A masked field is shown from its start so scheme and host
                  // are always readable (UX-SOURCES 4.4); no caret scrolling.
                  autoScroll: !fieldRow.masked
                  password: fieldRow.fieldId === "password"
                  // Cap plus slack: an over-cap paste is refused with its
                  // error, never cut silently (SR18, SR22).
                  maximumLength: Model.formCapacity(fieldRow.fieldId)
                  placeholderText: root.fieldPlaceholder(fieldRow.fieldId)
                  enabled: !root.formProbing
                  foreground: root.foreground
                  accent: fieldRow.hasError ? root.urgent : root.accent
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  horizontalPadding: Style.spacing.controlPaddingX
                  verticalPadding: Style.spacing.inputPaddingY
                  activeFocusOnTab: false
                  Keys.forwardTo: [formKeys]
                  Accessible.role: Accessible.EditableText
                  Accessible.name: root.fieldAccessibleName(fieldRow.fieldId)
                  // A screen reader never gets the query (UX-SOURCES 6.7).
                  Accessible.description: fieldRow.maskable ? Model.maskUrl(root.formValue(fieldRow.fieldId)) : ""
                  Accessible.passwordEdit: fieldRow.fieldId === "password"
                  onTextChanged: root.fieldEdited(fieldRow.fieldId, text)
                  onActiveFocusChanged: if (activeFocus) root.fieldFocused(fieldRow.fieldId)
                }

                // Eye button in the reserved slot, only when there is something to mask.
                PanelActionButton {
                  visible: fieldRow.maskable
                  anchors.right: parent.right
                  anchors.verticalCenter: field.verticalCenter
                  iconText: fieldRow.masked ? Model.GLYPHS.eye : Model.GLYPHS.eyeOff
                  tooltipText: fieldRow.masked ? root.copy.tooltipShow : root.copy.tooltipHide
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  enabled: !root.formProbing
                  Accessible.role: Accessible.Button
                  Accessible.name: fieldRow.masked ? root.copy.accessibleShow : root.copy.accessibleHide
                  Accessible.checked: !fieldRow.masked
                  onClicked: root.toggleRevealField(fieldRow.fieldId)
                }
              }
            }

            // Result / error line (UX-SOURCES 4.2 / 4.3): the banner's inner
            // row, local to the form, its space reserved so fields never jump.
            Rectangle {
              id: resultLine
              x: formColumn.fieldX
              width: formColumn.fieldWidth
              height: Style.space(28)
              radius: root.cornerRadius

              readonly property bool isError: root.formError !== null
              readonly property string lineText: {
                if (root.formError) return String(root.formError.message)
                if (root.formProbing && root.form) return Model.fetchingLine(root.form.probeHost, root.form.probeKind)
                return ""
              }

              opacity: lineText !== "" ? 1 : 0
              Behavior on opacity { NumberAnimation { duration: root.bannerFadeMs; easing.type: Easing.OutCubic } }
              color: isError ? Util.alpha(root.urgent, 0.10) : Style.normalFillFor(root.foreground, root.accent)
              Accessible.role: Accessible.AlertMessage
              Accessible.name: lineText

              Row {
                anchors.fill: parent
                anchors.leftMargin: Style.space(10)
                anchors.rightMargin: Style.space(10)
                spacing: Style.space(8)

                Text {
                  anchors.verticalCenter: parent.verticalCenter
                  textFormat: Text.PlainText
                  text: resultLine.isError ? Model.GLYPHS.alert : Model.GLYPHS.loading
                  color: resultLine.isError ? root.urgent : root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.icon
                }

                Text {
                  anchors.verticalCenter: parent.verticalCenter
                  width: parent.width - Style.space(28)
                  textFormat: Text.PlainText
                  text: resultLine.lineText
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.bodySmall
                  elide: Text.ElideRight
                }
              }
            }

            // Link rows (UX-SOURCES 1.2, 1.5): Saved sources (n) on first run
            // with a history, Use Xtream login instead while adding. The row's
            // visibility is computed from the same conditions as the links,
            // never from the links' own `visible`: a child's `visible` reads
            // false while its parent is hidden, so a row that once hid (the
            // form is null at start) would never show again.
            Row {
              id: linkRow
              readonly property bool showSaved: root.firstRunHead && root.sourceCount > 0
              readonly property bool showXtream: root.form !== null && root.form.kind === "url" && root.form.sourceId === ""
              x: formColumn.fieldX
              spacing: Style.space(10)
              visible: showSaved || showXtream

              Button {
                id: savedLink
                visible: linkRow.showSaved
                focusable: true
                activeFocusOnTab: false
                bordered: false
                text: root.copy.linkSaved + " (" + Model.formatCount(root.sourceCount) + ")"
                fontSize: Style.font.bodySmall
                fontFamily: root.fontFamily
                foreground: root.foreground
                accent: root.accent
                enabled: !root.formProbing
                Keys.forwardTo: [formKeys]
                Accessible.role: Accessible.Button
                Accessible.name: root.copy.accessibleSaved + Model.formatCount(root.sourceCount)
                onActiveFocusChanged: if (activeFocus) root.fieldFocused("savedSources")
                onClicked: root.openSources()
              }

              Button {
                id: xtreamLink
                visible: linkRow.showXtream
                focusable: true
                activeFocusOnTab: false
                bordered: false
                text: root.copy.linkXtream
                fontSize: Style.font.bodySmall
                fontFamily: root.fontFamily
                foreground: root.foreground
                accent: root.accent
                enabled: !root.formProbing
                Keys.forwardTo: [formKeys]
                Accessible.role: Accessible.Button
                Accessible.name: root.copy.linkXtream
                onActiveFocusChanged: if (activeFocus) root.fieldFocused("xtream")
                onClicked: root.openXtreamForm()
              }
            }

            Text {
              visible: root.form !== null && root.form.kind === "xtream"
              x: formColumn.fieldX
              width: formColumn.fieldWidth
              textFormat: Text.PlainText
              text: root.copy.xtreamProse
              color: root.foreground
              opacity: 0.7
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }

            // Cancel / Save (Load on first run), right-aligned in the field column.
            Row {
              anchors.right: parent.right
              anchors.rightMargin: formColumn.eyeSlot
              spacing: Style.space(10)

              Button {
                id: cancelButton
                visible: !root.firstRunHead
                focusable: true
                activeFocusOnTab: false
                bordered: true
                text: root.copy.buttonCancel
                fontFamily: root.fontFamily
                foreground: root.foreground
                accent: root.accent
                enabled: !root.formProbing
                Keys.forwardTo: [formKeys]
                Accessible.role: Accessible.Button
                Accessible.name: root.copy.buttonCancel
                onActiveFocusChanged: if (activeFocus) root.fieldFocused("cancel")
                onClicked: root.cancelForm()
              }

              Button {
                id: submitButton
                focusable: true
                activeFocusOnTab: false
                bordered: true
                text: root.firstRunHead ? root.copy.buttonLoad : root.copy.buttonSave
                fontFamily: root.fontFamily
                foreground: root.foreground
                accent: root.accent
                enabled: !root.formProbing
                Keys.forwardTo: [formKeys]
                Accessible.role: Accessible.Button
                Accessible.name: text
                onActiveFocusChanged: if (activeFocus) root.fieldFocused(root.firstRunHead ? "load" : "save")
                onClicked: root.submitForm()
              }
            }

            // First run keeps the terminal command (S5 parity); click copies.
            Text {
              id: terminalCaption
              visible: root.firstRunHead
              width: parent.width
              textFormat: Text.PlainText
              text: root.copy.firstRunTerminal
              color: root.foreground
              opacity: 0.7
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              horizontalAlignment: Text.AlignHCenter
              elide: Text.ElideMiddle

              MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.copyCommand(root.copy.unconfiguredCommand)
              }
            }
          }
        }

        // ---- footer (UX 5.7 / 6.1 / 6.2)
        Item {
          width: parent.width
          height: root.footerHeight

          Text {
            id: footerStatus
            textFormat: Text.PlainText
            anchors.left: parent.left
            anchors.right: footerHints.left
            anchors.rightMargin: Style.spacing.md
            anchors.verticalCenter: parent.verticalCenter
            text: root.footerStatusText
            color: root.foreground
            opacity: 0.45
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            elide: Text.ElideRight
            Accessible.role: Accessible.StaticText
            Accessible.name: root.footerStatusText
          }

          Text {
            id: footerHints
            // Our own microcopy only (no user strings), so StyledText is safe.
            textFormat: Text.StyledText
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(implicitWidth, parent.width * 0.7)
            text: root.footerHintText
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            elide: Text.ElideLeft
            horizontalAlignment: Text.AlignRight
          }
        }
      }
    }
  }
}
