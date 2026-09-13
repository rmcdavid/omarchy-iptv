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
  readonly property bool searchMode: mode !== "list"
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
    accessibleChannels: "Channels in "
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
  readonly property bool hasChannels: serviceReady && service.channels.length > 0
  readonly property bool epgConfigured: serviceReady && service.epgConfigured === true
  readonly property bool epgLoaded: serviceReady && service.epgLoaded === true
  readonly property string serviceStatus: serviceReady ? String(service.status) : "ready"
  readonly property string playingId: serviceReady && service.playing && service.nowPlaying ? String(service.nowPlaying.id) : ""
  readonly property string playingName: serviceReady && service.playing && service.nowPlaying ? String(service.nowPlaying.name) : ""
  readonly property int nowSec: serviceReady ? service.nowSec : Math.floor(Date.now() / 1000)
  readonly property bool showColumn: hasChannels && !narrow
  readonly property bool scopeIsGroup: Model.isGroupScope(effectiveScope)

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

  // Empty-state kind: "" while rows exist.
  readonly property string emptyKind: {
    if (!root.serviceReady) return "service"
    if (!root.configured) return "unconfigured"
    if (!root.hasChannels) {
      if (root.serviceStatus === "error") return "error"
      return "loading"
    }
    if (root.rowCount > 0) return ""
    if (root.hasQuery) return "noMatches"
    if (root.effectiveScope === Model.SCOPE_FAVORITES) return "noFavorites"
    return "emptyScope"
  }

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

  // Playlist warnings of the last load (D-LIVE-18): one low-key line in the
  // footer status slot, URL-free (Model.statusWarnings), kept until a clean
  // load replaces it. Text only, so the list never moves when it appears.
  readonly property string warningText: root.serviceReady ? Model.warningLine(root.service.playlistWarnings) : ""

  readonly property string footerStatusText: Model.footerStatus({
    transient: root.transientText,
    configured: root.configured,
    truncated: root.truncated,
    resultTotal: root.resultTotal,
    cap: root.maxRows,
    playingName: root.playingName,
    refreshing: root.serviceReady && root.service.refreshing,
    epgPending: root.serviceReady && root.service.epgPending,
    warning: root.warningText,
    count: root.serviceReady ? root.service.channels.length : 0,
    lastUpdated: root.serviceReady ? root.service.lastUpdated : "",
    stale: root.serviceStatus === "cached"
  })

  readonly property string keyColor: Util.alpha(root.foreground, 0.7).toString()
  readonly property string verbColor: Util.alpha(root.foreground, 0.45).toString()
  readonly property string footerHintText: {
    var empty = ""
    if (root.emptyKind === "loading") empty = "loading"
    else if (root.emptyKind === "unconfigured" || root.emptyKind === "error" || root.emptyKind === "service") empty = "error"
    var pairs = Model.footerHints({ mode: root.mode, query: root.query, empty: empty })
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
    root.guide = next
    root.transientText = ""
    root.enterPending = false
    root.opened = true
    root.disarmPointer()
    root.rebuildDisplay()
    root.cursorIndex = Model.cursorFor(root.currentRows, root.playingId)
    root.scrollToCursor()
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function close() {
    root.opened = false
    transientTimer.stop()
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
    var result = Model.filterChannels(root.candidates(), root.query, root.maxRows, favorites)
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

  function handleEscape() {
    var result = Model.onEscape(root.guide)
    if (result.close) root.dismiss()
    else root.applyGuide(result.state, true)
  }

  function switchMode() {
    root.guide = Model.toggleMode(root.guide)
  }

  // Keys both modes share and PanelKeyCatcher does not consume:
  // PgUp/PgDn, Home/End, Delete.
  function handleSharedKey(event) {
    if (event.key === Qt.Key_PageUp) { root.moveCursorBy(-root.pageSize(), false); return true }
    if (event.key === Qt.Key_PageDown) { root.moveCursorBy(root.pageSize(), false); return true }
    if (event.key === Qt.Key_Home) {
      // UX 8 #22: Home with a query active in list mode jumps the column to All.
      if (!root.searchMode && root.hasQuery && root.effectiveScope !== Model.SCOPE_ALL) root.setScope(Model.SCOPE_ALL)
      else root.selectAbsolute(0)
      return true
    }
    if (event.key === Qt.Key_End) { root.selectAbsolute(root.rowCount - 1); return true }
    if (event.key === Qt.Key_Delete && !root.searchMode) { root.removeAt(root.cursorIndex); return true }
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
    else if (t === "/") {
      root.swallowKey = true
      root.switchMode()
    }
    // digits and everything else: ignored (M2 channel numbers)
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

  // Only the row SET depends on these; decorations (playing, failed, EPG,
  // favorite star) are delegate bindings over the service's maps.
  Connections {
    target: root.service
    function onChannelsChanged() { root.groupsDirty = true; root.scheduleRebuild() }
    function onUserStateChanged() { root.groupsDirty = true; root.scheduleRebuild() }
    // UX 6.1: a manual refresh ends with `Refreshed - N channels` in the
    // status slot for the transient window (D-LIVE-05).
    function onPlaylistRefreshed(channelCount, manual) {
      if (manual && root.opened) root.showTransient(root.copy.transientRefreshed + Model.SEP + Model.pluralChannels(channelCount))
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

        Keys.onPressed: function(event) {
          if (root.swallowKey) {
            root.swallowKey = false
            event.accepted = true
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
          blocked: root.searchMode
          onMoveRequested: function(dx, dy) {
            if (dy !== 0) root.moveCursorBy(dy, true)
            else if (dx !== 0) root.moveScopeBy(dx)
          }
          onReturnRequested: root.enterPending = true
          onActivateRequested: {
            var enter = root.enterPending
            root.enterPending = false
            root.activate(!enter)
          }
          onCloseRequested: root.handleEscape()
          onDeleteRequested: root.removeAt(root.cursorIndex)
          onTabRequested: function(direction) { root.switchMode() }
          onTextKey: function(text) { root.handleListLetter(text) }
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

          Text {
            id: scopeLabel
            textFormat: Text.PlainText
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: root.scopeLabelText
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
            anchors.fill: parent
            spacing: 0

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
                anchors.bottom: parent.bottom
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
                  Accessible.name: Model.rowAccessibleName({ name: name, favorite: favorite, playing: playing, nowTitle: nowTitle, until: until, failedAt: failedAt })
                  Accessible.focused: hasCursor

                  Item {
                    id: rowContent
                    anchors.fill: parent
                    anchors.leftMargin: Style.space(12)
                    anchors.rightMargin: Style.space(12)
                    anchors.topMargin: Style.space(8)
                    anchors.bottomMargin: Style.space(8)

                    // lead slot: favorite star
                    Text {
                      id: lead
                      width: root.leadWidth
                      anchors.left: parent.left
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

                  // Lead-slot hit target (UX 7.3): toggles favorite without playing.
                  MouseArea {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    width: Math.max(Style.space(28), Style.space(12) + root.leadWidth)
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.toggleFavoriteAt(row.index)
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
            visible: root.emptyKind !== ""

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
