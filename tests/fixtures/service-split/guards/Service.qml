// tests/fixtures/service-split/guards/Service.qml -- NOT a service. The
// guards' fixture of a split service (D-REL-14 C2): this file and
// Service-demo.js, its one code-behind, are what tests/split_fixture.py
// copies into a plugin root for each guard's test, and a test replaces the
// `// MUTANT` line of Service-demo.js with the mutant its guard's rule
// names. Clean, every guard reads both files green.
pragma ComponentBehavior: Bound
import QtQuick
import qs.Commons as Commons
import "Model.mjs" as Model
import "Service-demo.js" as ServiceDemo

Item {
  id: root
  property int count: 0
  property string shown: ""
  property color tint: "transparent"
  readonly property string safe: Model.redactUrls(root.shown)

  Text {
    textFormat: Text.PlainText
    text: root.safe
    color: Commons.Color.foreground
  }

  function str(v) { return v === undefined || v === null ? "" : String(v) }

  function demo(item, text) { return ServiceDemo.demo(item, text) }
}
