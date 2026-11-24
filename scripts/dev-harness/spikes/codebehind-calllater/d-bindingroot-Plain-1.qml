import QtQuick
// D-REL-15 probe driver: shape bindingroot, the Service Plain.qml, deleted before the outside object calls back.
Item {
  id: outer
  signal poke()
  property int beat: 0
  property string label: ""
  onLabelChanged: print("LABEL " + label)
  Component { id: comp; Plain {} }
  Timer { id: done; interval: 400; onTriggered: { print("END"); Qt.quit() } }
  Timer { id: late; interval: 150; onTriggered: { outer.poke(); outer.beat = 1 } }
  Timer {
    id: go; interval: 50
    onTriggered: {
      var b = comp.createObject(outer, { n: 2 })
      b.bindOnRoot(outer)
      b.destroy()
      late.start()
      done.start()
    }
  }
  Component.onCompleted: go.start()
}
