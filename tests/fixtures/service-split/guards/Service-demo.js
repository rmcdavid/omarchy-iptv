// tests/fixtures/service-split/guards/Service-demo.js -- the guards' fixture
// code-behind (D-REL-14 C2). Clean, it holds what each guard counts in a
// code-behind: a model member, a regular-expression literal, a colour that
// paints nothing, a metric bound to no number, and a string the guards'
// README fixture quotes. The `// MUTANT` line is where a test puts the one
// line its guard must refuse.

  function demo(item, text) {
    var safe = Model.redactUrls(root.str(text))
    var word = /^[a-z]+$/.test(safe)
    item.color = "transparent"
    item.spacing = root.count
    // MUTANT
    root.shown = word ? safe : ""
    return "Demo notice only the code-behind says"
  }
