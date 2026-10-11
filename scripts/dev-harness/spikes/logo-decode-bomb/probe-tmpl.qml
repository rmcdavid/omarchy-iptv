import QtQuick

// The SINK, observed: an Image declared exactly as Guide.qml declares the row
// logo slot (asynchronous, cache, sourceSize twice the 22 px draw width,
// PreserveAspectFit, mipmap). Nothing here is the plugin's code. run.sh and
// logo-scenario.sh substitute __PATH__ with the file under test and
// __SOURCE_SIZE__ with 44 (the row slot) or 223 (the wall tile, whose only
// difference is that number). Exit status is the verdict: 0 Image.Ready,
// 1 Image.Error, 2 the 20 s timer fired; a SIGKILL from the memory cap
// arrives as -9 in the reporter's line.
Item {
  width: 200; height: 200
  Image {
    id: logo
    width: 22
    height: 22
    asynchronous: true
    cache: true
    sourceSize.width: __SOURCE_SIZE__
    sourceSize.height: __SOURCE_SIZE__
    fillMode: Image.PreserveAspectFit
    mipmap: true
    source: "file://__PATH__"
    onStatusChanged: {
      if (status === Image.Ready) {
        console.log("PROBE ready implicit=" + implicitWidth + "x" + implicitHeight
                    + " sourceSize=" + sourceSize.width + "x" + sourceSize.height);
        Qt.exit(0);
      } else if (status === Image.Error) {
        console.log("PROBE error");
        Qt.exit(1);
      }
    }
  }
  Timer { interval: 20000; running: true; onTriggered: { console.log("PROBE timeout status=" + logo.status); Qt.exit(2) } }
}
