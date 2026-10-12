import { aLeaf } from "./a.mjs"
import { bFn } from "./b.mjs"
var C_CONST = 7
function cFn() { return "c" + C_CONST + aLeaf() + bFn("z") }
export { C_CONST, cFn }
