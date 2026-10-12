import QtQuick
import Quickshell
import "Agg.mjs" as Agg
ShellRoot {
    Component.onCompleted: {
        var ok = Agg.aFn(1) === "ab315c73b3z" && Agg.cFn() === "c73b3z" && (Agg.A_CONST + Agg.B_CONST + Agg.C_CONST) === 15
        console.log("QS-CYCLE " + (ok ? "PASS" : "FAIL") + " aFn=" + Agg.aFn(1) + " cFn=" + Agg.cFn() + " B_SEES_A_AT_INIT=" + Agg.B_SEES_A_AT_INIT + " keys=" + Object.keys(Agg).sort().join(","))
        Qt.quit()
    }
}
