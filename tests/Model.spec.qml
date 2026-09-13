import QtQuick
import QtTest
import "../Model.js" as Model

// Proves Model.js loads inside the Qt QML engine (no ES module syntax, no
// node-only globals) and that the QML-side results match the node tests.
// Run: QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml
TestCase {
  name: "IptvModel"

  function test_searchKey() {
    compare(Model.searchKey("BBC-One HD", "UK: News"), "bbc one hd uk news")
    compare(Model.searchKey("Télé Québec", ""), "tele quebec")
  }

  function test_fnv1a32() {
    compare(Model.fnv1a32(""), "811c9dc5")
    compare(Model.fnv1a32("a"), "e40c292c")
    compare(Model.fnv1a32("foobar"), "bf9cf968")
  }

  function test_channelId() {
    compare(Model.channelId({ tvgId: "bbc1.uk", url: "http://a" }), "t:bbc1.uk")
    compare(Model.channelId({ url: "foobar" }), "u:bf9cf968")
  }

  function test_filterChannels() {
    var channels = [
      { id: "1", name: "BBC One HD", group: "UK", searchKey: "bbc one hd uk" },
      { id: "2", name: "One America", group: "US", searchKey: "one america us" }
    ]
    var result = Model.filterChannels(channels, "one", 10)
    compare(result.total, 2)
    compare(result.rows[0].id, "2")
    compare(result.rows[1].id, "1")
  }

  function test_state() {
    compare(Model.toggleFavorite(["a"], "b"), ["a", "b"])
    compare(Model.pushRecent([], { id: "x", name: "X" }, 10, 5), [{ id: "x", name: "X", at: 5 }])
  }

  function test_mpvArgv() {
    var argv = Model.buildMpvArgv({ socketPath: "/tmp/s", name: "N", url: "http://u", extraArgs: [] })
    compare(argv[0], "mpv")
    compare(argv[argv.length - 2], "--")
    compare(argv[argv.length - 1], "http://u")
  }
}
