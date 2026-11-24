// tests/fixtures/service-split/Service-demo.js -- the one code-behind of
// the service readers' fixture (D-REL-14): each moved function with the
// comment block that sat directly above it, at the root's two-space
// indent, run in the scope of the component that imports it.

  // The first moved function. Its comment block moves with it,
  // both lines of it.
  function bump(by) {
    root.count += by
    if (root.count > 3) tick.stop()
    return root.count
  }

  function quoted(a, b) {
    // A brace in a string, a template or a block comment opens no block.
    var s = "}" + '{' + `${a}}` /* } */
    return s + b
  }

  // ---- a banner the next function carries, directly attached
  function pattern(text) {
    var re = /[}{]\/+/g
    // CLOSURE-EXCEPTION: replace's callback, called before replace returns (D-REL-15)
    function count(m) { return "{" + m.length + "}" }
    return text.replace(re, count)
  }

  function last() { return root.str(root.label) }
