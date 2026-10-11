import QtQuick
import QtQuick.Controls
import QtQuick.Window
Window {
  width: 320; height: 120; visible: true; title: "clip-probe-nofield"
  Rectangle { width: 300; height: 40; color: "gray" }
  Timer { interval: 9000; running: true; onTriggered: Qt.quit() }
}
