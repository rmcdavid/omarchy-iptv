// The probe's code-behind: a classic JavaScript file imported by Plain.qml and
// Bound.qml with no .import and no .pragma, so it runs in the importing
// component's own scope, as each Service-<domain>.js of the plugin does.

  // Shape old: the closure made HERE and handed to Qt.callLater, as C3's
  // adoptActive did (D-REL-15).
  function adoptOld(key) {
      Qt.callLater(function() { root.persistActive(key) })
  }

  // Shape oldread: the same, after a read of the root, as adoptActive reads
  // the root before it makes its closure.
  function adoptOldAfterRead(key) {
      var seen = root.n
      Qt.callLater(function() { root.persistActive(key) })
  }

  // Shape new: the closure made by a root function this calls, as the fix's
  // adoptActive does through persistActiveLater.
  function adoptNew(key) {
      root.persistActiveLater(key)
  }

  // Shape method: a root method handed to Qt.callLater from here.
  function adoptMethod() {
      Qt.callLater(root.ping)
  }

  // Shapes stored and held: a closure made HERE and stored on the root, as
  // startCacheLayout's onDone is stored in cacheQueue.
  function stash(key) {
      root.queue = [{ onDone: function(status) { root.persistActive(key + ":" + status) } }]
  }

  // Shapes connect and binding: a closure made HERE and given to an object
  // outside the Service, as a signal's handler and as a binding.
  function listen(target) {
      target.poke.connect(function() { root.persistActive("signal") })
  }
  function bindTo(target) {
      target.label = Qt.binding(function() { return "bound " + target.beat + " " + root.n })
  }
