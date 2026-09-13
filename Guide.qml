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
// Modeled on the first-party clipboard/emoji pickers: scrim + centered card
// on the [menu] theme surface, search-as-you-type, arrows/PgUp/PgDn, Enter.
// Host contract (shell.qml panel loader): `shell`, `manifest` and `service`
// are injected after load; open(payloadJson)/close()/toggle() are called by
// summon/hide/toggle. Dismiss through shell.hide(manifest.id) so the host's
// open-state stays in sync (same as Emojis.qml).
//
// Payload (JSON string) keys, all optional: {"query": "bbc", "group": "UK"}.
Item {
  id: root

  property var shell: null
  property var manifest: null
  property var service: null

  readonly property string pluginId: manifest && manifest.id ? String(manifest.id) : "io.github.rmcdavid.iptv"
  property bool opened: false
  property string filterText: ""
  property string groupName: ""            // "" = all channels
  property int selectedIndex: 0
  property bool cursorActive: false
  property int totalMatches: 0
  property bool truncated: false
  readonly property int maxRows: Model.MAX_ROWS_DEFAULT

  // Shares the [menu] surface tokens with the clipboard and emoji pickers;
  // every color below is a theme token (PRODUCT.md decision 7).
  property color background: Color.menu.background
  property color foreground: Color.menu.text
  property color border: Color.menu.border
  property var borderSpec: Border.surfaceSpec("menu", "border", border, Math.max(1, Style.space(2)))
  property color scrim: Color.menu.scrim
  property color selectedBackground: Color.menu.selectedBackground
  property color selectedText: Color.menu.selectedText
  readonly property int cornerRadius: Style.cornerRadius
  property string fontFamily: Style.font.menuFamily
  property int contentMargin: Style.spacing.panelPadding
  property int headerHeight: Math.max(Style.space(34), Style.font.title + Style.spacing.controlPaddingY * 2)
  property int contentSpacing: Style.spacing.md
  // TODO(UX): final card geometry, two-pane (groups | channels) vs single list.
  property int cardWidth: Math.min(Style.space(900), panel.width - Style.gapsOut * 2)
  property int cardHeight: Math.min(Style.space(620), panel.height - Style.gapsOut * 2)
  property int rowHeight: Math.max(Style.space(46), Style.font.title + Style.font.caption + Style.spacing.rowPaddingX)

  readonly property bool serviceReady: service !== null
  readonly property bool configured: serviceReady && service.configured === true
  readonly property var playlistError: serviceReady && service.playlistStatus && service.playlistStatus.ok !== true ? service.playlistStatus.error : null
  readonly property bool stale: serviceReady && service.playlistStatus && service.playlistStatus.stale === true
  readonly property string statusLine: {
    if (!root.serviceReady) return "Service not loaded. Run: omarchy restart shell"
    if (!root.configured) return "No playlist configured. Run: omarchy bar set " + root.pluginId + " playlistUrl <url>"
    if (root.playlistError) return String(root.playlistError.message || "Playlist error") + (root.stale ? " (showing cached channels)" : "")
    if (root.service.refreshing) return "Refreshing playlist..."
    var text = root.totalMatches + " channel" + (root.totalMatches === 1 ? "" : "s")
    if (root.truncated) text += ", showing first " + root.maxRows + " - keep typing"
    if (root.stale) text += " (cached)"
    return text
  }

  // ------------------------------------------------------------ lifecycle

  function resolveService() {
    if (!root.service && root.shell && typeof root.shell.serviceFor === "function")
      root.service = root.shell.serviceFor(root.pluginId)
  }

  function open(payloadJson) {
    root.resolveService()
    var payload = Model.parseJsonObject(payloadJson) || {}
    root.filterText = typeof payload.query === "string" ? payload.query : ""
    if (typeof payload.group === "string") root.groupName = payload.group
    root.opened = true
    root.selectedIndex = 0
    root.cursorActive = true
    root.disarmPointer()
    root.rebuildDisplay()
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function close() {
    root.opened = false
  }

  function dismiss() {
    root.opened = false
    if (root.shell && typeof root.shell.hide === "function") root.shell.hide(root.pluginId)
  }

  function toggle() {
    if (root.opened) root.dismiss()
    else root.open("{}")
  }

  // ------------------------------------------------------------ model

  function candidates() {
    if (!root.serviceReady) return []
    return Model.channelsInGroup(root.service.channels, root.groupName, root.service.userState)
  }

  function rebuildDisplay() {
    // The service can be handed over after this overlay loads; resolve lazily.
    root.resolveService()
    var result = Model.filterChannels(root.candidates(), root.filterText, root.maxRows)
    var nowSec = Math.floor(Date.now() / 1000)
    var favorites = root.serviceReady ? root.service.userState.favorites : []
    var epg = root.serviceReady ? root.service.epgNow : ({})
    root.totalMatches = result.total
    root.truncated = result.truncated

    displayModel.clear()
    for (var i = 0; i < result.rows.length; i++) {
      var channel = result.rows[i]
      var id = Model.channelId(channel)
      var tvg = String(channel.tvgId || "")
      var line = Model.formatEpgLine(tvg !== "" ? epg[tvg] : null, nowSec)
      displayModel.append({
        channelId: id,
        name: String(channel.name || ""),
        group: String(channel.group || Model.UNGROUPED),
        favorite: favorites.indexOf(id) !== -1,
        epgNow: line.now,
        epgNext: line.next
      })
    }

    if (displayModel.count === 0) root.selectedIndex = 0
    else if (root.selectedIndex >= displayModel.count) root.selectedIndex = displayModel.count - 1
    else if (root.selectedIndex < 0) root.selectedIndex = 0

    Qt.callLater(function() {
      if (displayModel.count > 0) resultList.positionViewAtIndex(root.selectedIndex, ListView.Contain)
    })
  }

  function select(delta) {
    if (displayModel.count === 0) return
    root.disarmPointer()
    if (!root.cursorActive) {
      root.cursorActive = true
      root.selectedIndex = delta < 0 ? displayModel.count - 1 : 0
    } else {
      root.selectedIndex = Math.max(0, Math.min(displayModel.count - 1, root.selectedIndex + delta))
    }
    resultList.positionViewAtIndex(root.selectedIndex, ListView.Contain)
  }

  function selectAbsolute(index) {
    if (displayModel.count === 0) return
    root.disarmPointer()
    root.cursorActive = true
    root.selectedIndex = Math.max(0, Math.min(index, displayModel.count - 1))
    resultList.positionViewAtIndex(root.selectedIndex, ListView.Contain)
  }

  function pageSize() {
    return Math.max(1, Math.floor(resultList.height / root.rowHeight))
  }

  function setFilter(nextFilter) {
    root.filterText = nextFilter
    root.selectedIndex = 0
    root.cursorActive = true
    root.disarmPointer()
    root.rebuildDisplay()
  }

  function cycleGroup(delta) {
    if (!root.serviceReady) return
    var groups = Model.groupChannels(root.service.channels, root.service.userState)
    var names = [""]
    for (var i = 0; i < groups.length; i++) names.push(groups[i].name)
    var at = names.indexOf(root.groupName)
    if (at === -1) at = 0
    root.groupName = names[(at + delta + names.length) % names.length]
    root.selectedIndex = 0
    root.rebuildDisplay()
  }

  function disarmPointer() {
    pointerGate.reset()
  }

  function selectFromPointer(index, item, mouse) {
    if (!pointerGate.moved(item, mouse)) return
    root.cursorActive = true
    root.selectedIndex = index
  }

  // ------------------------------------------------------------ actions

  function activateIndex(index) {
    if (!root.serviceReady || index < 0 || index >= displayModel.count) return
    var row = displayModel.get(index)
    root.dismiss()
    root.service.playId(row.channelId)
  }

  function toggleFavoriteAt(index) {
    if (!root.serviceReady || index < 0 || index >= displayModel.count) return
    root.service.toggleFavorite(displayModel.get(index).channelId)
    root.rebuildDisplay()
  }

  function refresh() {
    if (root.serviceReady) root.service.refreshPlaylist(true)
  }

  ListModel { id: displayModel }

  PointerMoveGate {
    id: pointerGate
    referenceItem: card
  }

  Connections {
    target: root.service
    function onChannelsChanged() { if (root.opened) root.rebuildDisplay() }
    function onUserStateChanged() { if (root.opened) root.rebuildDisplay() }
    function onEpgNowChanged() { if (root.opened) root.rebuildDisplay() }
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
      Accessible.name: "IPTV channel guide"

      MouseArea { anchors.fill: parent; onClicked: {} }

      Item {
        id: keyCatcher
        anchors.fill: parent
        focus: true

        // Keyboard map (draft, see ARCHITECTURE.md "Open risks" and UX.md):
        // letters filter; arrows / Ctrl+J / Ctrl+K move; PgUp/PgDn/Home/End;
        // Tab / Shift+Tab cycle groups; Enter plays; Ctrl+F favorite;
        // Ctrl+R refresh; Esc clears the filter, then the group, then closes.
        Keys.priority: Keys.BeforeItem
        Keys.onPressed: function(event) {
          var ctrl = (event.modifiers & Qt.ControlModifier) !== 0
          if (event.key === Qt.Key_Escape) {
            if (root.filterText) root.setFilter("")
            else if (root.groupName !== "") { root.groupName = ""; root.rebuildDisplay() }
            else root.dismiss()
            event.accepted = true
          } else if (Util.editsFilter(event, root.filterText)) {
            root.setFilter(Util.editedFilter(event, root.filterText))
            event.accepted = true
          } else if (event.key === Qt.Key_Up || (ctrl && event.key === Qt.Key_K)) {
            root.select(-1)
            event.accepted = true
          } else if (event.key === Qt.Key_Down || (ctrl && event.key === Qt.Key_J)) {
            root.select(1)
            event.accepted = true
          } else if (event.key === Qt.Key_PageUp) {
            root.select(-root.pageSize())
            event.accepted = true
          } else if (event.key === Qt.Key_PageDown) {
            root.select(root.pageSize())
            event.accepted = true
          } else if (event.key === Qt.Key_Home) {
            root.selectAbsolute(0)
            event.accepted = true
          } else if (event.key === Qt.Key_End) {
            root.selectAbsolute(displayModel.count - 1)
            event.accepted = true
          } else if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
            root.cycleGroup(event.key === Qt.Key_Backtab || (event.modifiers & Qt.ShiftModifier) ? -1 : 1)
            event.accepted = true
          } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            if (root.cursorActive) root.activateIndex(root.selectedIndex)
            else if (displayModel.count > 0) root.cursorActive = true
            event.accepted = true
          } else if (ctrl && event.key === Qt.Key_F) {
            root.toggleFavoriteAt(root.selectedIndex)
            event.accepted = true
          } else if (ctrl && event.key === Qt.Key_R) {
            root.refresh()
            event.accepted = true
          } else if (!ctrl && event.text && event.text.length === 1 && event.text.charCodeAt(0) >= 32 && event.text.charCodeAt(0) !== 127) {
            root.setFilter(root.filterText + event.text)
            event.accepted = true
          }
        }
      }

      Column {
        anchors.fill: parent
        anchors.topMargin: card.contentTopInset
        anchors.rightMargin: card.contentRightInset
        anchors.bottomMargin: card.contentBottomInset
        anchors.leftMargin: card.contentLeftInset
        spacing: root.contentSpacing

        // Header: search text (or placeholder) + active group.
        Rectangle {
          width: parent.width
          height: root.headerHeight
          radius: root.cornerRadius
          color: "transparent"

          Text {
            textFormat: Text.PlainText
            anchors.left: parent.left
            anchors.right: groupLabel.left
            anchors.rightMargin: Style.spacing.md
            anchors.verticalCenter: parent.verticalCenter
            text: root.filterText || "Search channels..."
            color: root.foreground
            opacity: root.filterText ? 1 : 0.58
            font.family: root.fontFamily
            font.pixelSize: Style.font.heading
            elide: Text.ElideRight
          }

          Text {
            id: groupLabel
            textFormat: Text.PlainText
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: root.groupName === "" ? "All groups" : root.groupName
            color: root.selectedText
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
          }
        }

        // Status / error line. Real helper error text lands here (US1).
        Text {
          width: parent.width
          textFormat: Text.PlainText
          text: root.statusLine
          color: root.playlistError ? Color.urgent : root.foreground
          opacity: root.playlistError ? 1 : 0.7
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          elide: Text.ElideRight
        }

        Item {
          width: parent.width
          height: parent.height - root.headerHeight - Style.font.caption - root.contentSpacing * 2

          ListView {
            id: resultList
            anchors.fill: parent
            model: displayModel
            clip: true
            spacing: Style.space(2)
            boundsBehavior: Flickable.StopAtBounds

            delegate: Rectangle {
              id: row
              required property int index
              required property string channelId
              required property string name
              required property string group
              required property bool favorite
              required property string epgNow
              required property string epgNext

              readonly property bool hasCursor: root.cursorActive && index === root.selectedIndex

              width: ListView.view.width
              height: root.rowHeight
              radius: root.cornerRadius
              color: hasCursor ? root.selectedBackground : "transparent"
              Accessible.role: Accessible.ListItem
              Accessible.name: row.name + (row.favorite ? ", favorite" : "")

              Column {
                anchors.left: parent.left
                anchors.right: star.left
                anchors.leftMargin: Style.spacing.rowPaddingX
                anchors.rightMargin: Style.spacing.md
                anchors.verticalCenter: parent.verticalCenter
                spacing: Style.spacing.xxs

                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  text: row.name
                  color: row.hasCursor ? root.selectedText : root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.title
                  elide: Text.ElideRight
                }

                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  // TODO(UX): EPG "Now ... until 21:30" and "Next ..." layout.
                  text: row.epgNow !== "" ? row.group + "  -  " + row.epgNow : row.group
                  color: root.foreground
                  opacity: 0.6
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  elide: Text.ElideRight
                }
              }

              Text {
                id: star
                anchors.right: parent.right
                anchors.rightMargin: Style.spacing.rowPaddingX
                anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText
                text: row.favorite ? "󰓎" : ""
                color: root.selectedText
                font.family: root.fontFamily
                font.pixelSize: Style.font.title
              }

              MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onPositionChanged: function(mouse) { root.selectFromPointer(row.index, row, mouse) }
                onClicked: {
                  root.cursorActive = true
                  root.selectedIndex = row.index
                  root.activateIndex(row.index)
                }
              }
            }
          }

          Column {
            anchors.centerIn: parent
            spacing: Style.space(8)
            visible: displayModel.count === 0

            Text {
              text: "󰕧"
              color: root.selectedText
              opacity: 0.8
              font.family: root.fontFamily
              font.pixelSize: Style.font.displayLarge
              horizontalAlignment: Text.AlignHCenter
              width: parent.width
            }

            Text {
              textFormat: Text.PlainText
              text: {
                if (!root.configured || root.playlistError) return root.statusLine
                if (!root.serviceReady || root.service.channels.length === 0) return "No channels yet"
                return "No matches for \"" + root.filterText + "\""
              }
              color: root.foreground
              opacity: 0.7
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              horizontalAlignment: Text.AlignHCenter
              wrapMode: Text.WordWrap
              width: Math.min(root.cardWidth - root.contentMargin * 2, Style.space(600))
            }
          }
        }
      }
    }
  }
}
