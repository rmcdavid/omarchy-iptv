pragma ComponentBehavior: Bound
import QtQuick
import "M.mjs" as Model
import "Service-probe.js" as ServiceProbe
// The probe's Service: a root with the plugin's id, a function the deferred
// call reaches, the root functions of each shape, and one-line forwarders
// into the code-behind.
Item {
  id: root
  property int n: 0
  property var queue: []
  function persistActive(key) { print("PERSIST " + Model.id(key) + " n=" + root.n) }
  function ping() { print("PING n=" + Model.id(root.n)) }
  // Shape root, and the fix's root function (persistActiveLater).
  function persistActiveLater(key) {
      Qt.callLater(function() { root.persistActive(key) })
  }
  // Shape fold: a root method with an argument, twice in one turn.
  function laterWithArg(key) { Qt.callLater(root.persistActive, key) }
  // Shape held, its root-built twin.
  function stashOnRoot(key) {
      root.queue = [{ onDone: function(status) { root.persistActive(key + ":" + status) } }]
  }
  // What calls a stored closure: a root function, from a child of the root,
  // as handleCacheExit calls onDone from cacheProc's Connections.
  function drain() {
      var q = root.queue
      root.queue = []
      for (var i = 0; i < q.length; i++) q[i].onDone("done")
  }
  Timer { id: tick; interval: 100; onTriggered: root.drain() }
  function stashAndTick(key) { ServiceProbe.stash(key); tick.start() }
  function adoptOld(key) { return ServiceProbe.adoptOld(key) }
  function adoptOldAfterRead(key) { return ServiceProbe.adoptOldAfterRead(key) }
  function adoptNew(key) { return ServiceProbe.adoptNew(key) }
  function adoptMethod() { return ServiceProbe.adoptMethod() }
  function stash(key) { return ServiceProbe.stash(key) }
  // Shapes connectroot and bindingroot, the root-built twins.
  function listenOnRoot(target) {
      target.poke.connect(function() { root.persistActive("signal") })
  }
  function bindOnRoot(target) {
      target.label = Qt.binding(function() { return "bound " + target.beat + " " + root.n })
  }
  function listen(target) { return ServiceProbe.listen(target) }
  function bindTo(target) { return ServiceProbe.bindTo(target) }
  function makeHeld(key) { return ServiceProbe.makeHeld(key) }
  function listenAfterRead(target) { return ServiceProbe.listenAfterRead(target) }
}
