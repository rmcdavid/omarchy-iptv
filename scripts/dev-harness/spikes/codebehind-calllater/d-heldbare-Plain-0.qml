import QtQuick
// D-REL-15 probe driver: shape heldbare, the Service Plain.qml, kept.
Item {
  id: outer
  property var held: null
  Component { id: comp; Plain {} }
  Timer { id: done; interval: 400; onTriggered: { print("END"); Qt.quit() } }
  Timer { id: late; interval: 150; onTriggered: if (outer.held) outer.held("late") }
  Timer {
    id: go; interval: 50
    onTriggered: {
      var b = comp.createObject(outer, { n: 2 })
      outer.held = b.makeHeld("k1")
      late.start()
      done.start()
    }
  }
  Component.onCompleted: go.start()
}
