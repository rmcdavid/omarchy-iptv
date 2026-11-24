"""scripts/dev-harness/spikes/codebehind-calllater/standin.py -- writes the
shipped-text probe's work folder (D-REL-15): a stand-in Service.qml beside
the plugin's own Service-sources.js and model, and the two drivers.

  python3 -I standin.py ROOT WORK SOURCES_JS SERVICE_QML

ROOT is the plugin tree; SOURCES_JS and SERVICE_QML the Service-sources.js
and Service.qml of the commit probed (the tree's own, or an older commit's
that shipped.sh wrote out with git show). The stand-in holds what
adoptActive reads and writes on the root, stubbed, and a forwarder to it;
when SERVICE_QML has persistActiveLater, the stand-in carries THAT
function's text, read by the service's own readers, so the probe runs the
shipping text and not a copy. Model.mjs and model/ are linked from ROOT.
Python 3 standard library only.
"""
import os
import sys

root, work, sources, service = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
sys.path.insert(0, os.path.join(root, 'scripts'))
import service_files  # noqa: E402

spans = service_files.function_spans(service_files.read_text(service), 'Service.qml')
later = spans.get('persistActiveLater', '')
os.symlink(os.path.join(root, 'Model.mjs'), os.path.join(work, 'Model.mjs'))
os.symlink(os.path.join(root, 'model'), os.path.join(work, 'model'))
with open(sources, encoding='utf-8') as fh:
    text = fh.read()
with open(os.path.join(work, 'Service-sources.js'), 'w', encoding='utf-8') as fh:
    fh.write(text)
STANDIN = '''pragma ComponentBehavior: Bound
import QtQuick
import "Model.mjs" as Model
import "Service-sources.js" as ServiceSources
// The probe's stand-in for Service.qml: what adoptActive reads and writes on
// the root, and its forwarder. persistActive prints which playlist the key
// names, so the run shows both adoptions persisted, in order.
Item {
  id: root
  property var settings: ({ sourceKey: "" })
  property var userState: Model.emptyState()
  property var settingsInvalid: null
  property string migrationAddedKey: ""
  property bool migrationHeldFull: false
  property bool migrationFullTold: false
  property var playlistStatus: null
  property var playlistLoadWarnings: []
  property string lastError: ""
  property bool invalidInputBlocks: false
  function reportEntryInput(setting, reason) { print("REPORT " + setting + " " + reason) }
  function saveState() {}
  function applyInvalidStatus() {}
  function persistActive(key) {
    var s = root.userState.sources.filter(r => r.key === key)
    print("PERSIST " + (s.length === 1 ? s[0].url.split("/").pop() : "?"))
    return true
  }
%s
  function adoptActive(playlist, epg, plan) { return ServiceSources.adoptActive(playlist, epg, plan) }
}
''' % later
with open(os.path.join(work, 'Service.qml'), 'w', encoding='utf-8') as fh:
    fh.write(STANDIN)
for deleted in (1, 0):
    with open(os.path.join(work, 'd-shipped-%d.qml' % deleted), 'w', encoding='utf-8') as fh:
        fh.write('''import QtQuick
Item {
  id: outer
  Component { id: comp; Service {} }
  Timer { id: done; interval: 400; onTriggered: { print("END"); Qt.quit() } }
  Timer {
    id: go; interval: 50
    onTriggered: {
      var b = comp.createObject(outer)
%s      b.adoptActive("http://127.0.0.1/a.m3u", "", { adoptUrl: true, migrating: true })
      b.adoptActive("http://127.0.0.1/b.m3u", "", { adoptUrl: true, migrating: true })
      done.start()
    }
  }
  Component.onCompleted: go.start()
}
''' % ('      b.destroy()\n' if deleted else ''))
print('persistActiveLater: %s' % ('from its Service.qml, %d bytes' % len(later) if later else 'none in its Service.qml'))
