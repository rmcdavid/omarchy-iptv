import QtQuick
import QtQuick.Controls
import QtQuick.Window
Window {
  width: 320; height: 120; visible: true; title: "clip-probe-editable"
  TextField { width: 300; readOnly: false; maximumLength: 2048 }
  Timer { interval: 9000; running: true; onTriggered: Qt.quit() }
}
