import QtQuick
// D-REL-15 probe driver: shape connect, the Service Bound.qml, kept.
Item {
  id: outer
  signal poke()
  property int beat: 0
  property string label: ""
  onLabelChanged: print("LABEL " + label)
  Component { id: comp; Bound {} }
  Timer { id: done; interval: 400; onTriggered: { print("END"); Qt.quit() } }
  Timer { id: late; interval: 150; onTriggered: { outer.poke(); outer.beat = 1 } }
  Timer {
    id: go; interval: 50
    onTriggered: {
      var b = comp.createObject(outer, { n: 2 })
      b.listen(outer)

      late.start()
      done.start()
    }
  }
  Component.onCompleted: go.start()
}
