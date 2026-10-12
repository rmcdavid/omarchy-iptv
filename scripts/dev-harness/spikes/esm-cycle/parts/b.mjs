import { aLeaf, A_CONST } from "./a.mjs"
var B_CONST = 5
// the hazard the init-locality rule forbids: an initializer reading another
// part of the cycle. Recorded, not relied on.
var B_SEES_A_AT_INIT = typeof A_CONST === "undefined" ? "undefined" : String(A_CONST)
function bFn(x) { return "b" + aLeaf() + x }
export { B_CONST, bFn, B_SEES_A_AT_INIT }
