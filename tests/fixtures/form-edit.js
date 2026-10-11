// Shared vectors for the plugin's own form editing (D-CLIP-1).
//
// ONE file, run by both JavaScript engines: node requires it
// (tests/Model.test.js) and the Qt engine imports it as a QML script library
// (tests/Model.spec.qml), the arrangement chno-cases.js and pip-cases.js use
// and for the same reason (a QML TestCase cannot read a local file). No
// `.pragma library`: node's parser rejects it. ASCII only; every non-ASCII
// character is a \u escape, generated, so a code point is never retyped.
//
// BOUNDARIES is a TRANSCRIPT, not a derivation: each row is what a QtQuick
// TextInput on Qt 6.11.2 answered to Ctrl+Left (`back`) and Ctrl+Right
// (`fwd`) at every caret position 0..length, read back from cursorPosition
// under QT_QPA_PLATFORM=offscreen on 2026-10-11. The spec re-measures every
// row on the real control on every run, so a Qt that changes its mind goes
// red there; node holds Model.wordBoundary to the same rows. The strings
// cover: words with single, double, leading and trailing spaces; every
// character of Qt's separator set in one string; `_` (a word character);
// NBSP, U+3000, U+2028 and U+0085 (spaces) against U+FEFF, U+200B and U+00AD
// (not spaces); a surrogate pair; the empty string.
//
// WORD_DELETE_TEXTS are driven through Ctrl+Backspace, Ctrl+Delete,
// Backspace and Delete on an EDITABLE TextInput at every position, against
// Model.editDelete, which is the only way to see what Qt deletes.
//
// EDITS are hand-written vectors for Model.editInsert / editDelete, with the
// rule each one states; the ones marked "measured" repeat a value the
// control produced, and the two marked DIVERGES say where the model does
// not follow Qt and why. TYPED is Model.typedText; RANGES is Model.editRange.

var BOUNDARIES = [
  {
    "text": "foo bar baz",
    "back": [
      0,
      0,
      0,
      0,
      0,
      4,
      4,
      4,
      4,
      8,
      8,
      8
    ],
    "fwd": [
      4,
      4,
      4,
      4,
      8,
      8,
      8,
      8,
      11,
      11,
      11,
      11
    ]
  },
  {
    "text": "http://host.example/path?a=b&c=d",
    "back": [
      0,
      0,
      0,
      0,
      0,
      4,
      4,
      4,
      7,
      7,
      7,
      7,
      11,
      12,
      12,
      12,
      12,
      12,
      12,
      12,
      19,
      20,
      20,
      20,
      20,
      24,
      25,
      26,
      27,
      28,
      29,
      30,
      31
    ],
    "fwd": [
      4,
      4,
      4,
      4,
      7,
      7,
      7,
      11,
      11,
      11,
      11,
      12,
      19,
      19,
      19,
      19,
      19,
      19,
      19,
      20,
      24,
      24,
      24,
      24,
      25,
      26,
      27,
      28,
      29,
      30,
      31,
      32,
      32
    ]
  },
  {
    "text": "foo  bar",
    "back": [
      0,
      0,
      0,
      0,
      0,
      0,
      5,
      5,
      5
    ],
    "fwd": [
      5,
      5,
      5,
      5,
      5,
      8,
      8,
      8,
      8
    ]
  },
  {
    "text": "foo   ",
    "back": [
      0,
      0,
      0,
      0,
      0,
      0,
      0
    ],
    "fwd": [
      6,
      6,
      6,
      6,
      6,
      6,
      6
    ]
  },
  {
    "text": "   foo",
    "back": [
      0,
      0,
      0,
      0,
      3,
      3,
      3
    ],
    "fwd": [
      3,
      3,
      3,
      6,
      6,
      6,
      6
    ]
  },
  {
    "text": "a.b",
    "back": [
      0,
      0,
      1,
      2
    ],
    "fwd": [
      1,
      2,
      3,
      3
    ]
  },
  {
    "text": "user:p@ss@h",
    "back": [
      0,
      0,
      0,
      0,
      0,
      4,
      5,
      6,
      7,
      7,
      9,
      10
    ],
    "fwd": [
      4,
      4,
      4,
      4,
      5,
      6,
      7,
      9,
      9,
      10,
      11,
      11
    ]
  },
  {
    "text": "caf\u00e9 b\u00e4r",
    "back": [
      0,
      0,
      0,
      0,
      0,
      0,
      5,
      5,
      5
    ],
    "fwd": [
      5,
      5,
      5,
      5,
      5,
      8,
      8,
      8,
      8
    ]
  },
  {
    "text": "x\ud83d\ude00y z",
    "back": [
      0,
      0,
      0,
      0,
      0,
      0,
      5
    ],
    "fwd": [
      5,
      5,
      5,
      5,
      5,
      6,
      6
    ]
  },
  {
    "text": "a-b_c",
    "back": [
      0,
      0,
      1,
      2,
      2,
      2
    ],
    "fwd": [
      1,
      2,
      5,
      5,
      5,
      5
    ]
  },
  {
    "text": "one\u00a0two",
    "back": [
      0,
      0,
      0,
      0,
      0,
      4,
      4,
      4
    ],
    "fwd": [
      4,
      4,
      4,
      4,
      7,
      7,
      7,
      7
    ]
  },
  {
    "text": "a.b,c?d!e@f#g$h:i;j-k<l>m[n]o(p)q{r}s=t/u+v%w^x*y'z\"0`1~2|3\\4",
    "back": [
      0,
      0,
      1,
      2,
      3,
      4,
      5,
      6,
      7,
      8,
      9,
      10,
      11,
      12,
      13,
      14,
      15,
      16,
      17,
      18,
      19,
      20,
      21,
      22,
      23,
      24,
      25,
      26,
      27,
      28,
      29,
      30,
      31,
      32,
      33,
      34,
      35,
      36,
      37,
      38,
      39,
      40,
      41,
      42,
      43,
      44,
      45,
      46,
      47,
      48,
      49,
      50,
      51,
      52,
      53,
      54,
      55,
      56,
      57,
      58,
      59,
      60
    ],
    "fwd": [
      1,
      2,
      3,
      4,
      5,
      6,
      7,
      8,
      9,
      10,
      11,
      12,
      13,
      14,
      15,
      16,
      17,
      18,
      19,
      20,
      21,
      22,
      23,
      24,
      25,
      26,
      27,
      28,
      29,
      30,
      31,
      32,
      33,
      34,
      35,
      36,
      37,
      38,
      39,
      40,
      41,
      42,
      43,
      44,
      45,
      46,
      47,
      48,
      49,
      50,
      51,
      52,
      53,
      54,
      55,
      56,
      57,
      58,
      59,
      60,
      61,
      61
    ]
  },
  {
    "text": "a::b",
    "back": [
      0,
      0,
      1,
      1,
      3
    ],
    "fwd": [
      1,
      3,
      3,
      4,
      4
    ]
  },
  {
    "text": "x=1&y=2",
    "back": [
      0,
      0,
      1,
      2,
      3,
      4,
      5,
      6
    ],
    "fwd": [
      1,
      2,
      3,
      4,
      5,
      6,
      7,
      7
    ]
  },
  {
    "text": "--",
    "back": [
      0,
      0,
      0
    ],
    "fwd": [
      2,
      2,
      2
    ]
  },
  {
    "text": "foo.bar_baz-qux",
    "back": [
      0,
      0,
      0,
      0,
      3,
      4,
      4,
      4,
      4,
      4,
      4,
      4,
      11,
      12,
      12,
      12
    ],
    "fwd": [
      3,
      3,
      3,
      4,
      11,
      11,
      11,
      11,
      11,
      11,
      11,
      12,
      15,
      15,
      15,
      15
    ]
  },
  {
    "text": "x\u3000y",
    "back": [
      0,
      0,
      0,
      2
    ],
    "fwd": [
      2,
      2,
      3,
      3
    ]
  },
  {
    "text": "k\u2028l",
    "back": [
      0,
      0,
      0,
      2
    ],
    "fwd": [
      2,
      2,
      3,
      3
    ]
  },
  {
    "text": "x\u0085y",
    "back": [
      0,
      0,
      0,
      2
    ],
    "fwd": [
      2,
      2,
      3,
      3
    ]
  },
  {
    "text": "x\ufeffy",
    "back": [
      0,
      0,
      0,
      0
    ],
    "fwd": [
      3,
      3,
      3,
      3
    ]
  },
  {
    "text": "x\u200by",
    "back": [
      0,
      0,
      0,
      0
    ],
    "fwd": [
      3,
      3,
      3,
      3
    ]
  },
  {
    "text": "x\u00ady",
    "back": [
      0,
      0,
      0,
      0
    ],
    "fwd": [
      3,
      3,
      3,
      3
    ]
  },
  {
    "text": "",
    "back": [
      0
    ],
    "fwd": [
      0
    ]
  },
  {
    "text": "one",
    "back": [
      0,
      0,
      0,
      0
    ],
    "fwd": [
      3,
      3,
      3,
      3
    ]
  }
]

var WORD_DELETE_TEXTS = [
  "foo bar baz",
  "http://host.example/path?a=b",
  "foo  bar",
  "foo   ",
  "a-b_c",
  "user:p@ss@h"
]

var EDITS = [
  {
    "why": "insert at the caret",
    "op": "insert",
    "value": "abc",
    "sel": [
      1,
      1
    ],
    "text": "X",
    "cap": 10,
    "expect": {
      "value": "aXbc",
      "caret": 2,
      "changed": true
    }
  },
  {
    "why": "insert over a selection replaces it (measured: Qt gives 'foo x baz', caret 5)",
    "op": "insert",
    "value": "foo bar baz",
    "sel": [
      4,
      7
    ],
    "text": "x",
    "cap": 100,
    "expect": {
      "value": "foo x baz",
      "caret": 5,
      "changed": true
    }
  },
  {
    "why": "a reversed range is the same range",
    "op": "insert",
    "value": "foo bar baz",
    "sel": [
      7,
      4
    ],
    "text": "x",
    "cap": 100,
    "expect": {
      "value": "foo x baz",
      "caret": 5,
      "changed": true
    }
  },
  {
    "why": "one key at the cap is refused and nothing is cut (measured: Qt leaves 'abcde', caret 2)",
    "op": "insert",
    "value": "abcde",
    "sel": [
      2,
      2
    ],
    "text": "x",
    "cap": 5,
    "expect": {
      "value": "abcde",
      "caret": 2,
      "changed": false
    }
  },
  {
    "why": "a long insert keeps what fits (measured: Qt insert(1, 'XYZW') on 'abc' at cap 5 gives 'aXYbc', caret 3)",
    "op": "insert",
    "value": "abc",
    "sel": [
      1,
      1
    ],
    "text": "XYZW",
    "cap": 5,
    "expect": {
      "value": "aXYbc",
      "caret": 3,
      "changed": true
    }
  },
  {
    "why": "a selection makes room before the cap applies",
    "op": "insert",
    "value": "abcde",
    "sel": [
      1,
      3
    ],
    "text": "xy",
    "cap": 5,
    "expect": {
      "value": "axyde",
      "caret": 3,
      "changed": true
    }
  },
  {
    "why": "control characters never enter (sanitizeTyping's rule)",
    "op": "insert",
    "value": "ab",
    "sel": [
      1,
      1
    ],
    "text": "x\ty\n",
    "cap": 10,
    "expect": {
      "value": "axyb",
      "caret": 3,
      "changed": true
    }
  },
  {
    "why": "an insert of only controls is no insert",
    "op": "insert",
    "value": "ab",
    "sel": [
      1,
      1
    ],
    "text": "\u0007",
    "cap": 10,
    "expect": {
      "value": "ab",
      "caret": 1,
      "changed": false
    }
  },
  {
    "why": "empty text is no insert, even over a selection",
    "op": "insert",
    "value": "abc",
    "sel": [
      0,
      2
    ],
    "text": "",
    "cap": 10,
    "expect": {
      "value": "abc",
      "caret": 0,
      "changed": false
    }
  },
  {
    "why": "a range past the end is clamped",
    "op": "insert",
    "value": "ab",
    "sel": [
      5,
      9
    ],
    "text": "x",
    "cap": 10,
    "expect": {
      "value": "abx",
      "caret": 3,
      "changed": true
    }
  },
  {
    "why": "a surrogate pair inserts as two units and the caret lands after both",
    "op": "insert",
    "value": "ab",
    "sel": [
      2,
      2
    ],
    "text": "\ud83d\ude00",
    "cap": 10,
    "expect": {
      "value": "ab\ud83d\ude00",
      "caret": 4,
      "changed": true
    }
  },
  {
    "why": "the cap counts UTF-16 units and cuts blindly, as Qt's left(remaining) does: a half pair at the cap is Qt's behaviour, recorded, not a feature",
    "op": "insert",
    "value": "ab",
    "sel": [
      2,
      2
    ],
    "text": "\ud83d\ude00",
    "cap": 3,
    "expect": {
      "value": "ab\ud83d",
      "caret": 3,
      "changed": true
    }
  },
  {
    "why": "a zero-width joiner is formatting, not control, and types (Qt accepts Other_Format)",
    "op": "insert",
    "value": "ab",
    "sel": [
      1,
      1
    ],
    "text": "\u200d",
    "cap": 10,
    "expect": {
      "value": "a\u200db",
      "caret": 2,
      "changed": true
    }
  },
  {
    "why": "cap 0 means the URL limit, like capLength",
    "op": "insert",
    "value": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "sel": [
      2047,
      2047
    ],
    "text": "xy",
    "cap": 0,
    "expect": {
      "value": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaax",
      "caret": 2048,
      "changed": true
    }
  },
  {
    "why": "masked field = fully selected: typing replaces the whole value",
    "op": "insert",
    "value": "http://u:p@h/x",
    "sel": [
      0,
      14
    ],
    "text": "z",
    "cap": 100,
    "expect": {
      "value": "z",
      "caret": 1,
      "changed": true
    }
  },
  {
    "why": "Backspace at 0 is nothing",
    "op": "delete",
    "value": "abc",
    "sel": [
      0,
      0
    ],
    "direction": -1,
    "word": false,
    "opaque": false,
    "expect": {
      "value": "abc",
      "caret": 0,
      "changed": false
    }
  },
  {
    "why": "Backspace takes the code point before the caret",
    "op": "delete",
    "value": "abc",
    "sel": [
      2,
      2
    ],
    "direction": -1,
    "word": false,
    "opaque": false,
    "expect": {
      "value": "ac",
      "caret": 1,
      "changed": true
    }
  },
  {
    "why": "Delete at the end is nothing",
    "op": "delete",
    "value": "abc",
    "sel": [
      3,
      3
    ],
    "direction": 1,
    "word": false,
    "opaque": false,
    "expect": {
      "value": "abc",
      "caret": 3,
      "changed": false
    }
  },
  {
    "why": "Delete takes the code point after the caret",
    "op": "delete",
    "value": "abc",
    "sel": [
      1,
      1
    ],
    "direction": 1,
    "word": false,
    "opaque": false,
    "expect": {
      "value": "ac",
      "caret": 1,
      "changed": true
    }
  },
  {
    "why": "Backspace over a selection deletes it (measured)",
    "op": "delete",
    "value": "foo bar baz",
    "sel": [
      4,
      7
    ],
    "direction": -1,
    "word": false,
    "opaque": false,
    "expect": {
      "value": "foo  baz",
      "caret": 4,
      "changed": true
    }
  },
  {
    "why": "Delete over a selection deletes it (measured)",
    "op": "delete",
    "value": "foo bar baz",
    "sel": [
      4,
      7
    ],
    "direction": 1,
    "word": false,
    "opaque": false,
    "expect": {
      "value": "foo  baz",
      "caret": 4,
      "changed": true
    }
  },
  {
    "why": "Ctrl+Backspace over a selection deletes the selection alone (measured: Qt does the same)",
    "op": "delete",
    "value": "foo bar baz",
    "sel": [
      4,
      7
    ],
    "direction": -1,
    "word": true,
    "opaque": false,
    "expect": {
      "value": "foo  baz",
      "caret": 4,
      "changed": true
    }
  },
  {
    "why": "Ctrl+Delete over a selection deletes the selection alone. DIVERGES from Qt, which also eats to the next boundary ('foo baz'); the spec pins both sides",
    "op": "delete",
    "value": "foo bar baz",
    "sel": [
      4,
      7
    ],
    "direction": 1,
    "word": true,
    "opaque": false,
    "expect": {
      "value": "foo  baz",
      "caret": 4,
      "changed": true
    }
  },
  {
    "why": "a reversed selection deletes the same range",
    "op": "delete",
    "value": "foo bar baz",
    "sel": [
      7,
      4
    ],
    "direction": -1,
    "word": false,
    "opaque": false,
    "expect": {
      "value": "foo  baz",
      "caret": 4,
      "changed": true
    }
  },
  {
    "why": "Backspace takes a surrogate pair whole (measured)",
    "op": "delete",
    "value": "a\ud83d\ude00b",
    "sel": [
      3,
      3
    ],
    "direction": -1,
    "word": false,
    "opaque": false,
    "expect": {
      "value": "ab",
      "caret": 1,
      "changed": true
    }
  },
  {
    "why": "Delete takes a surrogate pair whole (measured)",
    "op": "delete",
    "value": "a\ud83d\ude00b",
    "sel": [
      1,
      1
    ],
    "direction": 1,
    "word": false,
    "opaque": false,
    "expect": {
      "value": "ab",
      "caret": 1,
      "changed": true
    }
  },
  {
    "why": "Backspace takes a combining mark alone (measured: Qt agrees)",
    "op": "delete",
    "value": "e\u0301x",
    "sel": [
      2,
      2
    ],
    "direction": -1,
    "word": false,
    "opaque": false,
    "expect": {
      "value": "ex",
      "caret": 1,
      "changed": true
    }
  },
  {
    "why": "Delete takes one unit of a combining sequence. DIVERGES from Qt, whose del() eats the grapheme ('x')",
    "op": "delete",
    "value": "e\u0301x",
    "sel": [
      0,
      0
    ],
    "direction": 1,
    "word": false,
    "opaque": false,
    "expect": {
      "value": "\u0301x",
      "caret": 0,
      "changed": true
    }
  },
  {
    "why": "Ctrl+Backspace at the end of 'foo bar baz' (measured: 'foo bar ', caret 8)",
    "op": "delete",
    "value": "foo bar baz",
    "sel": [
      11,
      11
    ],
    "direction": -1,
    "word": true,
    "opaque": false,
    "expect": {
      "value": "foo bar ",
      "caret": 8,
      "changed": true
    }
  },
  {
    "why": "Ctrl+Backspace after a space crosses it and the word (measured)",
    "op": "delete",
    "value": "foo bar baz",
    "sel": [
      4,
      4
    ],
    "direction": -1,
    "word": true,
    "opaque": false,
    "expect": {
      "value": "bar baz",
      "caret": 0,
      "changed": true
    }
  },
  {
    "why": "Ctrl+Delete at 0 takes the word and the space after it (measured)",
    "op": "delete",
    "value": "foo bar baz",
    "sel": [
      0,
      0
    ],
    "direction": 1,
    "word": true,
    "opaque": false,
    "expect": {
      "value": "bar baz",
      "caret": 0,
      "changed": true
    }
  },
  {
    "why": "Ctrl+Delete inside a word takes its rest and the space (measured)",
    "op": "delete",
    "value": "foo bar baz",
    "sel": [
      3,
      3
    ],
    "direction": 1,
    "word": true,
    "opaque": false,
    "expect": {
      "value": "foobar baz",
      "caret": 3,
      "changed": true
    }
  },
  {
    "why": "Ctrl+Backspace in a URL takes a run of separators (measured: caret 7 -> 'httphost.example/path?a=b', caret 4)",
    "op": "delete",
    "value": "http://host.example/path?a=b",
    "sel": [
      7,
      7
    ],
    "direction": -1,
    "word": true,
    "opaque": false,
    "expect": {
      "value": "httphost.example/path?a=b",
      "caret": 4,
      "changed": true
    }
  },
  {
    "why": "Ctrl+Delete in a URL likewise (measured)",
    "op": "delete",
    "value": "http://host.example/path?a=b",
    "sel": [
      4,
      4
    ],
    "direction": 1,
    "word": true,
    "opaque": false,
    "expect": {
      "value": "httphost.example/path?a=b",
      "caret": 4,
      "changed": true
    }
  },
  {
    "why": "a Password field's word is the whole line backward (measured: ' baz', caret 0)",
    "op": "delete",
    "value": "foo bar baz",
    "sel": [
      7,
      7
    ],
    "direction": -1,
    "word": true,
    "opaque": true,
    "expect": {
      "value": " baz",
      "caret": 0,
      "changed": true
    }
  },
  {
    "why": "and forward (measured: 'foo ', caret 4)",
    "op": "delete",
    "value": "foo bar baz",
    "sel": [
      4,
      4
    ],
    "direction": 1,
    "word": true,
    "opaque": true,
    "expect": {
      "value": "foo ",
      "caret": 4,
      "changed": true
    }
  },
  {
    "why": "opaque without word is one unit",
    "op": "delete",
    "value": "foo bar baz",
    "sel": [
      7,
      7
    ],
    "direction": -1,
    "word": false,
    "opaque": true,
    "expect": {
      "value": "foo ba baz",
      "caret": 6,
      "changed": true
    }
  },
  {
    "why": "masked field = fully selected: Backspace clears",
    "op": "delete",
    "value": "http://u:p@h/x",
    "sel": [
      0,
      14
    ],
    "direction": -1,
    "word": false,
    "opaque": false,
    "expect": {
      "value": "",
      "caret": 0,
      "changed": true
    }
  },
  {
    "why": "masked field = fully selected: Ctrl+Backspace clears too",
    "op": "delete",
    "value": "http://u:p@h/x",
    "sel": [
      0,
      14
    ],
    "direction": -1,
    "word": true,
    "opaque": false,
    "expect": {
      "value": "",
      "caret": 0,
      "changed": true
    }
  },
  {
    "why": "masked field = fully selected: Delete clears",
    "op": "delete",
    "value": "http://u:p@h/x",
    "sel": [
      0,
      14
    ],
    "direction": 1,
    "word": false,
    "opaque": false,
    "expect": {
      "value": "",
      "caret": 0,
      "changed": true
    }
  },
  {
    "why": "Backspace on the empty value",
    "op": "delete",
    "value": "",
    "sel": [
      0,
      0
    ],
    "direction": -1,
    "word": false,
    "opaque": false,
    "expect": {
      "value": "",
      "caret": 0,
      "changed": false
    }
  },
  {
    "why": "Ctrl+Backspace on the empty value",
    "op": "delete",
    "value": "",
    "sel": [
      0,
      0
    ],
    "direction": -1,
    "word": true,
    "opaque": false,
    "expect": {
      "value": "",
      "caret": 0,
      "changed": false
    }
  },
  {
    "why": "a range past the end is clamped before deleting",
    "op": "delete",
    "value": "abc",
    "sel": [
      9,
      9
    ],
    "direction": -1,
    "word": false,
    "opaque": false,
    "expect": {
      "value": "ab",
      "caret": 2,
      "changed": true
    }
  }
]

var TYPED = [
  {
    "why": "a letter types",
    "text": "a",
    "ctrlOnly": false,
    "expect": "a"
  },
  {
    "why": "a space types",
    "text": " ",
    "ctrlOnly": false,
    "expect": " "
  },
  {
    "why": "Control alone never types (Qt's rule, QTBUG-35734)",
    "text": "a",
    "ctrlOnly": true,
    "expect": ""
  },
  {
    "why": "Enter's text is a control",
    "text": "\r",
    "ctrlOnly": false,
    "expect": ""
  },
  {
    "why": "Escape's text is a control",
    "text": "\u001b",
    "ctrlOnly": false,
    "expect": ""
  },
  {
    "why": "Delete's text is a control",
    "text": "\u007f",
    "ctrlOnly": false,
    "expect": ""
  },
  {
    "why": "Backspace's text is a control",
    "text": "\b",
    "ctrlOnly": false,
    "expect": ""
  },
  {
    "why": "a surrogate pair types whole",
    "text": "\ud83d\ude00",
    "ctrlOnly": false,
    "expect": "\ud83d\ude00"
  },
  {
    "why": "a zero-width joiner types (Other_Format)",
    "text": "\u200d",
    "ctrlOnly": false,
    "expect": "\u200d"
  },
  {
    "why": "no text, no insert",
    "text": "",
    "ctrlOnly": false,
    "expect": ""
  },
  {
    "why": "a C1 control is stripped",
    "text": "a\u0085b",
    "ctrlOnly": false,
    "expect": "ab"
  }
]

var RANGES = [
  {
    "why": "a selection is the range",
    "cursor": 5,
    "selStart": 2,
    "selEnd": 4,
    "hasSelection": true,
    "expect": {
      "start": 2,
      "end": 4
    }
  },
  {
    "why": "no selection is the caret twice, whatever selectionStart says",
    "cursor": 5,
    "selStart": 2,
    "selEnd": 4,
    "hasSelection": false,
    "expect": {
      "start": 5,
      "end": 5
    }
  },
  {
    "why": "a reversed selection is ordered",
    "cursor": 3,
    "selStart": 7,
    "selEnd": 4,
    "hasSelection": true,
    "expect": {
      "start": 4,
      "end": 7
    }
  },
  {
    "why": "garbage is zero",
    "cursor": null,
    "selStart": null,
    "selEnd": null,
    "hasSelection": false,
    "expect": {
      "start": 0,
      "end": 0
    }
  }
]

if (typeof module !== "undefined") {
  module.exports = {
    BOUNDARIES: BOUNDARIES,
    WORD_DELETE_TEXTS: WORD_DELETE_TEXTS,
    EDITS: EDITS,
    TYPED: TYPED,
    RANGES: RANGES
  }
}
