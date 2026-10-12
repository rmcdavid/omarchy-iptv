import QtQuick
import QtTest
import "Agg.mjs" as Agg
TestCase {
    name: "Cycle"
    function test_cycle() {
        compare(Agg.aFn(1), "ab315c73b3z");
        compare(Agg.cFn(), "c73b3z");
        compare(Agg.A_CONST + Agg.B_CONST + Agg.C_CONST, 15);
        console.log("CYCLE B_SEES_A_AT_INIT=" + Agg.B_SEES_A_AT_INIT + " keys=" + Object.keys(Agg).sort().join(","));
    }
}
