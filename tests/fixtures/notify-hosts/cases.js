// Shared vectors for D-SINK-85 (owner, 2026-11-06): a notification body
// the plugin composes, read by BOTH hosts' own code.
//
// ONE file, run by both JavaScript engines: node requires it
// (tests/Model.test.js) and the Qt engine imports it as a QML script library
// (tests/Model.spec.qml), the arrangement chno-cases.js and pip-cases.js use
// and for the same reason (a QML TestCase cannot read a local file). No
// `.pragma library`: node's parser rejects it. ASCII only; every non-ASCII
// character is a \u escape, generated, so a code point is never retyped.
//
// Each case is a channel name and a failure reason a provider (or its
// player's error line) controls. The shapes are the map's (host450,
// notifications lens and skeptic-dsink49): N06, N07, N10 and N20 are the four
// that drew a live link in 0.17.0's failure card on Omarchy 4.5.0; the rest
// are every way that host's Markup.js decodes, restores or links -- decimal,
// hex and named entities, one to four escapes deep, the six tags and `<br>`
// it puts back, mailto, the linker's bare URL, controls that close up into
// an entity -- and the controls: literal URLs the plugin's redaction already
// cuts, plain names, the provider's own joiners (U+2060 and U+034F).
//
// `display` is the stream-failure body as the user is meant to READ it: the
// plugin's sentence with the name and the reason as the provider wrote them,
// after the plugin's own rules (controls dropped, a literal URL cut to its
// host, the S-04 dash rule), with no joiner. It was read and checked by hand
// against each name on 2026-11-06, not computed by the tests that use it.
// Both hosts must draw exactly this with U+034F after each `&` and `<`, and
// nothing else: no link, no tag, no entity decoded twice.
//
// The host code these run through is in this directory, byte copies pinned
// by sha256 in hosts.json (tests/test_notify_hosts.py holds the copies to the
// pins, the 4.5.0 copies to the installed host, and both to the packages).

var CASES = [
 {"id": "H01", "why": "N06: an anchor whose scheme colon is a decimal entity", "name": "<a href=\"https&#58;//evil.example/renew?u=1\">Renew</a>", "reason": "HTTP 403", "display": "\u201c<a href=\"https&#58;//evil.example/renew?u=1\">Renew</a>\u201d did not play \u00b7 HTTP 403"},
 {"id": "H02", "why": "N07: the same with a hex entity", "name": "<a href=\"https&#x3a;//evil.example/p/q\">Renew</a>", "reason": "HTTP 403", "display": "\u201c<a href=\"https&#x3a;//evil.example/p/q\">Renew</a>\u201d did not play \u00b7 HTTP 403"},
 {"id": "H03", "why": "an upper-case hex entity (the host's hex rule is case-blind)", "name": "<a href=\"https&#X3A;//evil.example/p\">Go</a>", "reason": "HTTP 403", "display": "\u201c<a href=\"https&#X3A;//evil.example/p\">Go</a>\u201d did not play \u00b7 HTTP 403"},
 {"id": "H04", "why": "N10: a mailto anchor, no entity needed", "name": "<a href=\"mailto:help@evil.example\">Support</a>", "reason": "HTTP 403", "display": "\u201c<a href=\"mailto:help@evil.example\">Support</a>\u201d did not play \u00b7 HTTP 403"},
 {"id": "H05", "why": "a mailto anchor with an entity colon", "name": "<a href=\"mailto&#58;help@evil.example\">Support</a>", "reason": "HTTP 403", "display": "\u201c<a href=\"mailto&#58;help@evil.example\">Support</a>\u201d did not play \u00b7 HTTP 403"},
 {"id": "H06", "why": "N20: a bare URL with an entity colon, for the linker", "name": "News https&#58;//evil.example/renew?acct=1 HD", "reason": "HTTP 403", "display": "\u201cNews https&#58;//evil.example/renew?acct=1 HD\u201d did not play \u00b7 HTTP 403"},
 {"id": "H07", "why": "a bare URL with entity slashes", "name": "News https:&#47;&#47;evil.example/renew HD", "reason": "HTTP 403", "display": "\u201cNews https:&#47;&#47;evil.example/renew HD\u201d did not play \u00b7 HTTP 403"},
 {"id": "H08", "why": "a named colon the host does not know (&colon; stays)", "name": "News https&colon;//evil.example/x HD", "reason": "HTTP 403", "display": "\u201cNews https&colon;//evil.example/x HD\u201d did not play \u00b7 HTTP 403"},
 {"id": "H09", "why": "an anchor the provider escaped once, scheme colon an entity", "name": "&lt;a href=\"https&#58;//evil.example/x\"&gt;Go&lt;/a&gt;", "reason": "HTTP 403", "display": "\u201c&lt;a href=\"https&#58;//evil.example/x\"&gt;Go&lt;/a&gt;\u201d did not play \u00b7 HTTP 403"},
 {"id": "H10", "why": "a bare URL escaped twice", "name": "News https&amp;#58;//evil.example/y HD", "reason": "HTTP 403", "display": "\u201cNews https&amp;#58;//evil.example/y HD\u201d did not play \u00b7 HTTP 403"},
 {"id": "H11", "why": "a bare URL escaped three times", "name": "News https&amp;amp;#58;//evil.example/z HD", "reason": "HTTP 403", "display": "\u201cNews https&amp;amp;#58;//evil.example/z HD\u201d did not play \u00b7 HTTP 403"},
 {"id": "H12", "why": "a bare URL escaped four times, past the host's three passes", "name": "News https&amp;amp;amp;#58;//evil.example/q HD", "reason": "HTTP 403", "display": "\u201cNews https&amp;amp;amp;#58;//evil.example/q HD\u201d did not play \u00b7 HTTP 403"},
 {"id": "H13", "why": "N22: every tag the host restores", "name": "<b>B</b> <i>i</i> <u>u</u> <s>s</s> <em>e</em> <strong>S</strong>", "reason": "HTTP 403", "display": "\u201c<b>B</b> <i>i</i> <u>u</u> <s>s</s> <em>e</em> <strong>S</strong>\u201d did not play \u00b7 HTTP 403"},
 {"id": "H14", "why": "upper-case tags (the host's tag rule is case-blind)", "name": "<B>B</B> <EM>e</EM>", "reason": "HTTP 403", "display": "\u201c<B>B</B> <EM>e</EM>\u201d did not play \u00b7 HTTP 403"},
 {"id": "H15", "why": "N23: line breaks in three spellings", "name": "Line1<br>Line2<br/>Line3<BR />4", "reason": "HTTP 403", "display": "\u201cLine1<br>Line2<br/>Line3<BR />4\u201d did not play \u00b7 HTTP 403"},
 {"id": "H16", "why": "tags the provider escaped once", "name": "&lt;b&gt;B&lt;/b&gt; L&lt;br&gt;M", "reason": "HTTP 403", "display": "\u201c&lt;b&gt;B&lt;/b&gt; L&lt;br&gt;M\u201d did not play \u00b7 HTTP 403"},
 {"id": "H17", "why": "the 4.0.6 renderer's own tags: font and an image", "name": "<font color=\"#f00\" size=\"+4\">X</font><img src=\"https&#58;//evil.example/i.png\">", "reason": "HTTP 403", "display": "\u201c<font color=\"#f00\" size=\"+4\">X</font><img src=\"https&#58;//evil.example/i.png\">\u201d did not play \u00b7 HTTP 403"},
 {"id": "H18", "why": "a javascript anchor", "name": "<a href=\"javascript:alert(1)\">x</a>", "reason": "HTTP 403", "display": "\u201c<a href=\"javascript:alert(1)\">x</a>\u201d did not play \u00b7 HTTP 403"},
 {"id": "H19", "why": "a literal https anchor (redaction breaks it)", "name": "<a href=\"https://evil.example/renew\">Renew</a>", "reason": "HTTP 403", "display": "\u201c<a href=\"evil.example>\u201d did not play \u00b7 HTTP 403"},
 {"id": "H20", "why": "a bare literal URL (redacted to its host)", "name": "Promo https://evil.example/renew?acct=1", "reason": "HTTP 403", "display": "\u201cPromo evil.example\u201d did not play \u00b7 HTTP 403"},
 {"id": "H21", "why": "a credentialed literal URL", "name": "News http://user:secret@cdn.example/live/1.ts HD", "reason": "HTTP 403", "display": "\u201cNews cdn.example HD\u201d did not play \u00b7 HTTP 403"},
 {"id": "H22", "why": "N19: a credentialed URL with an entity colon", "name": "News http&#58;//user:secret@cdn.example/live/1.ts HD", "reason": "HTTP 403", "display": "\u201cNews http&#58;//user:secret@cdn.example/live/1.ts HD\u201d did not play \u00b7 HTTP 403"},
 {"id": "H23", "why": "bare ampersands", "name": "AT&T Sports & Q&A Sky&Co", "reason": "HTTP 403", "display": "\u201cAT&T Sports & Q&A Sky&Co\u201d did not play \u00b7 HTTP 403"},
 {"id": "H24", "why": "entity words written out", "name": "Tom &amp; Jerry x &lt; y a&nbsp;b &quot;c&quot; &apos;d&apos;", "reason": "HTTP 403", "display": "\u201cTom &amp; Jerry x &lt; y a&nbsp;b &quot;c&quot; &apos;d&apos;\u201d did not play \u00b7 HTTP 403"},
 {"id": "H25", "why": "comparisons and a heart", "name": "5 > 3 < 4 <3 <-", "reason": "HTTP 403", "display": "\u201c5 > 3 < 4 <3 <-\u201d did not play \u00b7 HTTP 403"},
 {"id": "H26", "why": "numeric entities of letters, zero and past the last code point", "name": "&#72;&#x49; &#0; &#1114112; &#x110000;", "reason": "HTTP 403", "display": "\u201c&#72;&#x49; &#0; &#1114112; &#x110000;\u201d did not play \u00b7 HTTP 403"},
 {"id": "H27", "why": "the provider's own word joiners around & and <", "name": "A\u2060&\u2060B <\u2060b> &\u2060#58;", "reason": "HTTP 403", "display": "\u201cA\u2060&\u2060B <\u2060b> &\u2060#58;\u201d did not play \u00b7 HTTP 403"},
 {"id": "H28", "why": "controls that close up into an entity and a tag once dropped", "name": "News\t<b>\u0085X</b>\u009b&\u0007#58;", "reason": "HTTP 403", "display": "\u201cNews<b>X</b>&#58;\u201d did not play \u00b7 HTTP 403"},
 {"id": "H29", "why": "straight and typographic quotes", "name": "it's \"quoted\" \u201cq\u201d", "reason": "HTTP 403", "display": "\u201cit's \"quoted\" \u201cq\u201d\u201d did not play \u00b7 HTTP 403"},
 {"id": "H30", "why": "Greek, Japanese and Cyrillic with markup", "name": "\u0395\u03bb\u03bb\u03b7\u03bd\u03b9\u03ba\u03ac & \u65e5\u672c <\u0422\u0412>", "reason": "HTTP 403", "display": "\u201c\u0395\u03bb\u03bb\u03b7\u03bd\u03b9\u03ba\u03ac & \u65e5\u672c <\u0422\u0412>\u201d did not play \u00b7 HTTP 403"},
 {"id": "H31", "why": "an upper-case literal scheme", "name": "HTTPS://EVIL.EXAMPLE/x", "reason": "HTTP 403", "display": "\u201cEVIL.EXAMPLE\u201d did not play \u00b7 HTTP 403"},
 {"id": "H32", "why": "an ampersand and a < at the very end", "name": "R& L<", "reason": "HTTP 403", "display": "\u201cR& L<\u201d did not play \u00b7 HTTP 403"},
 {"id": "H33", "why": "a decimal-escaped ampersand that chains to a colon in three passes", "name": "News https&#38;#58;//evil.example/w HD", "reason": "HTTP 403", "display": "\u201cNews https&#38;#58;//evil.example/w HD\u201d did not play \u00b7 HTTP 403"},
 {"id": "H34", "why": "an anchor in the REASON, not the name", "name": "BBC One HD", "reason": "<a href=\"https&#58;//evil.example/r\">why</a> <b>HTTP 403</b>", "display": "\u201cBBC One HD\u201d did not play \u00b7 <a href=\"https&#58;//evil.example/r\">why</a> <b>HTTP 403</b>"},
 {"id": "H35", "why": "a bare entity-spelled URL in the reason", "name": "BBC One HD", "reason": "Failed to open https&#58;//evil.example/live/1.ts", "display": "\u201cBBC One HD\u201d did not play \u00b7 Failed to open https&#58;//evil.example/live/1.ts"},
 {"id": "H36", "why": "a plain name, the control", "name": "BBC One HD", "reason": "HTTP 403", "display": "\u201cBBC One HD\u201d did not play \u00b7 HTTP 403"},
 {"id": "H37", "why": "the provider's own grapheme joiners around & and <, the plugin's own joiner", "name": "A\u034f&\u034fB <\u034fb> &\u034f#58;", "reason": "HTTP 403", "display": "\u201cA\u034f&\u034fB <\u034fb> &\u034f#58;\u201d did not play \u00b7 HTTP 403"}
]

// Every notice the plugin posts (Model.notifyArgv), with the parameters each
// reads; the name and the reason come from the case.
var EVENTS = ["streamFailed", "localPlayFailure", "playerStopped", "outputFailed", "playlistRefreshed",
              "playlistError", "epgError", "mpvMissing", "entryInputRefused", "stateUnreadable"]

function params(c) {
  return { name: c.name, reason: c.reason, output: "video", channelCount: 2, groupCount: 1,
           setting: "playlistUrl", path: "/p/state.json", cachedAt: "" }
}

if (typeof module !== "undefined") {
  module.exports = { CASES: CASES, EVENTS: EVENTS, params: params }
}
