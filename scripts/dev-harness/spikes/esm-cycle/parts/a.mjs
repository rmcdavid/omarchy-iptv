import { bFn, B_CONST } from "./b.mjs"
import { cFn } from "./c.mjs"
var A_CONST = 3
function aFn(x) { return "a" + bFn(x) + B_CONST + cFn() }
function aLeaf() { return A_CONST }
export { A_CONST, aFn, aLeaf }
