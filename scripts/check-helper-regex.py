#!/usr/bin/env python3
"""Prove every regular expression the helper compiles has been reviewed for
its cost, and say which ones are not linear.

WHY THIS EXISTS (D-EPG-8, ruling R30g, 2026-10-21). The bounds sweep found
`\\s*\\([^()]*\\)\\s*$` applied with .sub() to guide <display-name> text that
nothing folded or capped: no literal prefix, so the engine tried it at every
position, and each position inside a whitespace run of length k scanned the
rest of the run and backed off -- about k*k/2 steps for one run, in a helper
the service stops only after 180 s. F-SINK-11 had found the same shape in
the URL redactor a month earlier and fixed THAT pattern only. A review that
covers one pattern at a time is the review rule 15 says not to do, so this
is the call that makes it every pattern: R30g's rule, "no regex whose cost
is super-linear in its input is applied to provider text", needs to know
every regex there is, and a list written once in a report would be a list a
human is expected to keep copying (rule 13).

THE RULE. Every call `re.compile|search|match|fullmatch|sub|subn|split|
findall|finditer(<pattern>, ...)` in bin/helper/*.py must have its pattern
in REVIEWED below, with what it reads (`provider` text, `user` text, or the
plugin's `own` data) and a verdict: `linear` and why, or `open` and the
defect it is (its board id once the board has numbered it). A pattern that
is new or CHANGED is unreviewed and fails, so editing a pattern is editing
its review. A reviewed pattern no
longer in the helper fails too, so the table cannot keep a verdict for code
that is gone. `from re import ...` and `import re as ...` fail, because a
call through another name would not be seen.

The key is the pattern's own text when it is a string literal, and the
source of the expression (ast.unparse) when it is built, as two are. An
`open` verdict is reported on every run and does not fail the gate: it is a
defect, the board holds defects, and the gate is not the board. Nothing here
runs a pattern on any input longer than one character.

THE SHAPE THE TABLE MISSED (D-EPG-12, ruling R32d, 2026-10-21). The first
table certified `\\[\\s*not\\s*24\\s*[-/]?\\s*7\\s*\\]` linear because "its
`\\s*` runs are separated by literals they cannot hold", and `[-/]?` is not a
literal they cannot hold: it is OPTIONAL, so the two runs were adjacent
repeats over one class and a whitespace run after `[not 24` was retried at
every split, about k*k/2 steps. A verdict a human writes can be wrong for a
reason that reads well, so the shape is now graded by STRUCTURE as well
(`super_linear_pairs`): the parsed pattern is walked, and two unbounded
repeats over single-character atoms whose character sets overlap, with
nothing between them the first run could not have taken (anchors,
assertions, groups and repeats that may match nothing, or single characters
the first class also matches), are reported as super-linear and fail the
gate whatever the table says. That is the D-EPG-12 shape and the old
`_IPV6_LITERAL` shape (`[..]*:[..]*`, the separator inside both classes);
it is NOT every super-linear shape -- a run with no literal prefix searched
from every position (D-EPG-8, F-SINK-11, D-PERF-6) and a nested unbounded
repeat (`(a+)+`) are read by a person and recorded in the table -- and the
walk looks at one sequence at a time, so a run hidden at the START of an
optional group is not paired with the run before the group. Each atom's
character set is read by compiling that atom alone and matching it against
one sample character at a time (the Latin-1 range plus a few others), under
the flags the call names, so IGNORECASE and DOTALL count.
"""
import argparse
import ast
import os
import re
import re._compiler
import re._parser
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALLS = {"compile", "search", "match", "fullmatch", "sub", "subn", "split", "findall", "finditer"}

# (pattern, what it reads, verdict). Written with the same literal the
# helper uses, so a reader can find the line.
REVIEWED = [
    (r"[A-Z0-9_]{1,64}", "provider",
     "linear: fullmatch of one bounded class run over the TLS error's reason attribute, which is "
     "OpenSSL's token (_SSL_REASON, D-SINK-93)"),
    (r"Tunnel connection failed: ([0-9]{3})(?![0-9])", "provider",
     "linear: matched at the start only; a literal, three digits and a one-character lookahead "
     "(_TUNNEL_REFUSED, D-SINK-93: http.client's text for a proxy that refused a CONNECT)"),
    (r"[a-z][a-z0-9+.-]*://|(?:rtp|udp|rtsp|mms):", "provider",
     "linear: matched at the start only; one class run then `://`, whose `:` and `/` the class cannot "
     "hold, backing off one test per character; the other arm is four literals (_NAME_URL_SHAPE, "
     "D-PLY-63: a cached channel's name and tvg-name)"),
    (r"(?:\[[^\]]*\] )?(?:[A-Za-z0-9_.-]+: )*(?:warning|Warning|WARNING):", "provider",
     "linear: matched at the start only; the bracket run ends at the first `]` and backs off one test "
     "per character; each tag repetition ends with `: `, which its class cannot hold, so every "
     "repetition has one split and giving them up costs one word each (PLAYER_WARNING_RE, D-PLY-29: "
     "mpv's log and stderr lines)"),
    (r"^[0-9a-f]{8}(-[0-9]{1,3})?\Z", "own",
     "linear: anchored, every quantifier bounded (SOURCE_KEY_RE; `\\Z` so a final line feed is not "
     "matched past, D-SRC-77)"),
    ("'[A-Za-z0-9]{%d,}' % EPG_ADDR_MIN_TOKEN", "provider",
     "linear: one class run and nothing after it; finditer resumes past each match, and a run shorter "
     "than EPG_ADDR_MIN_TOKEN is re-counted from each of its own positions, at most 11 steps each "
     "(_EPG_ADDR_TOKEN, stream URLs in build_alias)"),
    (r"^[A-Za-z0-9-]+$", "provider",
     "linear: anchored, one run then $, backing off one test per character (_HEADER_NAME)"),
    (r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$", "provider",
     "linear: anchored, one run then $ (_SAFE_OPTION)"),
    ("([a-z])[\u0300-\u036f]+", "provider",
     "linear: a run of marks is entered only from the letter before it; every position inside the run "
     "is not a letter and fails at once (_LATIN_MARKS, fold_text)"),
    ("'[^' + URL_DELIMITER_CHARS + ']+'", "provider",
     "linear: matched at one given position, one class run and nothing after it; the class is the "
     "six ASCII delimiters, R32a''' (_URL_TAIL_RE, next_url: once a URL, from its mark's end)"),
    ("'[' + URL_DELIMITER_CHARS + ']'", "provider",
     "linear: one character class, no quantifier; the six ASCII delimiters, R32a''' (_URL_DELIMITER: "
     "run_host_parts' provider text, the class that ends a free-text URL's authority; and parse_attrs' "
     "search for where a URL value's run ends, once a value, from its first quote or its end onward, "
     "the walk resuming past the run or stopping, D-SINK-80)"),
    ("'[' + URL_SPACE_CHARS + ']'", "provider",
     "linear: one character class, no quantifier; the enumerated URL whitespace union, R32a'' "
     "(_URL_SPACE: validate_source_url's user text, the class a READER refuses)"),
    (r"(?:.*[^A-Za-z0-9+.\-])?", "provider",
     "linear: D-PERF-6 (R32e), fixed by lane-bounds-s2. The old `[A-Za-z0-9+.\\-]*\\Z` under search() "
     "had no literal prefix, so it tried every start of redact_urls' window and a failed start cost "
     "the distance to the next non-scheme character, about r*r/2 for a scheme-legal run broken once "
     "inside the window (found by lane-bounds-h). This one is used with match(s, lo, j) under DOTALL: "
     "`.*` runs to j once and backs off once to the LAST non-scheme character, so an attempt costs at "
     "most 2*(j - lo), and the doubling windows sum to under 8R + 128 steps for a run of R -- "
     "independent of the text before it (_SCHEME_RUN_RE, _run_start for next_url's scheme walk, D-SINK-95; "
     "the stretches two walks read are disjoint: a walk that finds no scheme sets the bound at its P, and one that finds a scheme ends the search at its URL, whose run the next search starts past. cbd6679 broke that and said otherwise: its redact_urls went on past a URL whose run was empty without moving the bound, so every later walk crossed back to the same letter, quadratic on `a` and `<U+200B><U+2215><U+2215><TAB>` repeated (13 s at 40,001 characters, the review of cbd6679); an empty run is a URL now, and a walk with no letter before it is not taken; cut_free_text asks for one URL a cut)"),
    (r"[:;=&]", "provider",
     "linear: one character class, no quantifier (_RUN_HOST_END, run_host_parts: the port and "
     "parameter delimiters that end a free-text host inside an authority, R32a')"),
    (r"[;=&]", "provider",
     "linear: one character class, no quantifier (_PORT_END, run_host_parts: where the port after "
     "the host's `:` ends, for the non-numeric-port arm, R32a'')"),
    ("'^' + GENERATED_NAME_WORD.lower() + ' [0-9]+$'", "provider",
     "linear: anchored, literal prefix, one digit run then $ (_GENERATED_NAME)"),
    (r"[\s\x00-\x1f\x7f]+", "provider",
     "linear: one class run and nothing after it; sub resumes past each run (_CONTROL_WS)"),
    ("[\x00-\x1f\x7f-\x9f]", "provider",
     "linear: one character class, no quantifier; it reads provider text since player_title_text "
     "(_CONTROL_CHARS)"),
    (":[\x00-\x1f\x7f-\x9f]*/[\x00-\x1f\x7f-\x9f]*/", "provider",
     "linear: a literal `:` first, then two runs of one control class, each ended by a `/` the class "
     "cannot hold, so an attempt backs off at most once over each run and a run is scanned only from "
     "the `:` before it; url_mark_start searches it once a call, and url_mark_any calls that once: once a "
     "cut (cut_free_text), once a group text and once a space-run of it (split_groups' group_parts, over the "
     "run's own slice, so the runs read are disjoint), once a tvg-id (make_channel). parse_attrs (D-SINK-80) searches it once a quoted value, bounded to the value's run "
     "after its last space and begun at the last `:` before that run's first `/`, and a bare value once, "
     "bounded to the value, plus one match at its last `:` when a control ends the value, so a run is "
     "scanned from the `:` before it at most twice; fold_space (D-SINK-79) searches it from each run's end, "
     "so the text is read once"),
    ("[\x00-\x1f\x7f\x85\u2028\u2029]", "provider",
     "linear: one character class, no quantifier; sub resumes past each match, over the part of a URL's "
     "run after its mark, which fold_space hands it once, and replaces each match with U+FFFD "
     "(_RUN_CONTROLS, fold_space, D-SINK-79, the review's F9 and F11)"),
    (r"',[A-Za-z0-9_.\\-]+=[A-Za-z][A-Za-z0-9+.\\-]*' + _URL_MARK.pattern", "provider",
     "linear: a literal `,` first, so search() tries a start only at a comma; then a run of key "
     "characters ended by the `=` it cannot hold, a letter, a run of scheme characters ended by the `:` "
     "it cannot hold, and _URL_MARK's two control runs, each ended by a `/`; no run can hold a `,`, so "
     "the runs two attempts scan are disjoint; once a call over a guide hint or a logo URL, which parse "
     "drops past 2,048 characters (_ABSORBED_URL, absorbed_attribute, the review's F1)"),
    (r"',[' + URL_DELIMITER_CHARS + ']*[A-Za-z][A-Za-z0-9+.\\-]*' + _URL_MARK.pattern", "provider",
     "linear: a literal `,` first, so search() tries a start only at a comma; then a run of the six ASCII "
     "delimiters, a letter, a run of scheme characters and _URL_MARK's two control runs, each run ended by "
     "a character it cannot hold (a letter after the delimiters, a `:` after the scheme run, a `/` after "
     "each control run), so an attempt backs off at most once over each run, and no run can hold a `,`, "
     "so the runs two attempts scan are disjoint; once a call over a guide hint, which parse drops past "
     "2,048 characters (_HINT_LIST_COMMA, hint_first_entry, D-SINK-82)"),
    ("'[' + SLASH_ALIKE_CHARS + ']'", "provider",
     "linear: one character class, no quantifier (_SLASH_ALIKE: redaction_can_change's, parse_attrs' and "
     "group_split_protects' one search a text for a slash look-alike, and slash_alike_cut's over a printed "
     "host, D-SINK-95)"),
    (r"'[^\x00-\x9f' + _SPACE_ABOVE_C1 + SLASH_ALIKE_CHARS + ']'", "provider",
     "linear: one character class, no quantifier, searched over one mark's P at a time, and no two Ps "
     "overlap (_MARK_STAND_IN, next_url, D-SINK-95)"),
    ("'(?:[A-Za-z][0-9+.\\\\-]*+|[0-9+.\\\\-](?<=[^ -~][0-9+.\\\\-])[0-9+.\\\\-]*+|[' + SLASH_ALIKE_CHARS + '](?<=[A-Za-z0-9+.\\\\-\\x00-\\x1f\\x7f-\\x9f][' + SLASH_ALIKE_CHARS + ']))((?=[^ -9;-~' + SLASH_ALIKE_CHARS + '])' + _WIDE_STRETCH + '(?::' + _WIDE_STRETCH + ')*+)[/' + SLASH_ALIKE_CHARS + ']' + _WIDE_STRETCH + '[/' + SLASH_ALIKE_CHARS + ']'", "provider",
     "linear: every branch opens with a one-character class, so search() tries a start only at a lead -- a "
     "letter, a scheme character that is no letter, or a slash look-alike -- and skips the rest natively; the "
     "letter branch's possessive run of scheme non-letters and the digit branch's possessive run end at the "
     "first character they cannot hold, and each lookbehind reads one or two characters; then P's "
     "stretches, each a possessive run of deleted controls and at most one wide FILLER code point, joined by "
     "a `:` no stretch can hold, the first slash, one stretch and the second slash, none backed into; an "
     "attempt at a lead reads the runs after it once, and a start inside a run fails at its first "
     "character, since a `:` or FILLER opens no branch and a look-alike behind a wide code point fails its "
     "lookbehind; next_url resumes a failed candidate's search at its P, so a stretch is read by at most two "
     "attempts, and with `stop` it searches no further than the mark run after it (_URL_CANDIDATE and "
     "_WIDE_STRETCH, next_url, D-SINK-95; the review of 4d13d71 moved the caps into it and took only the "
     "leads a scheme walk can leave with a letter, so a run of rejected candidates is one native search)"),
    ("'[^\\x00-\\x9f' + SLASH_ALIKE_CHARS + '][\\x00-\\x1f\\x7f-\\x9f]*+[^\\x00-\\x9f' + SLASH_ALIKE_CHARS + ']'", "provider",
     "linear: an attempt starts only at a wide FILLER code point, then one possessive run of deleted "
     "controls, never backed into, then one character; searched once a next_url call that has a `stop`, "
     "from `stop` to the end of the mark run after it, so that run is read once (_FILLER_WIDE_PAIR, the end "
     "of next_url's candidate search past its stop, the review of 4d13d71)"),
    ("'.*[' + ''.join((chr(a) + '-' + chr(b) for a, b in SPACELESS_RANGES)) + ']'", "provider",
     "linear: matched under DOTALL over a stretch outside every URL between a credential's `:` and its `@`; "
     "`.*` runs to the end once and backs off to the last code point of a script written without spaces; "
     "asked at most twice a stretch, the second time short of the first's answer, and each `@` is asked "
     "once (_LAST_SPACELESS, _counted_ends, D-SINK-96's cap on the password side, the review of 4d13d71)"),
    (r"(?:.*[ -*,/:-@\[-`{-~])?", "provider",
     "linear: as _SCHEME_RUN_RE, matched with match(s, lo, j) under DOTALL: `.*` runs to j once and backs "
     "off once to the last character that is neither a scheme character nor CROSSABLE, and _run_start's "
     "windows double; asked once a scheme walk that crosses, and "
     "the stretches two walks read are disjoint: a walk that finds no scheme sets the bound at its P, and one that finds a scheme ends the search at its URL, whose run the next search starts past. cbd6679 broke that and said otherwise: its redact_urls went on past a URL whose run was empty without moving the bound, so every later walk crossed back to the same letter, quadratic on `a` and `<U+200B><U+2215><U+2215><TAB>` repeated (13 s at 40,001 characters, the review of cbd6679); an empty run is a URL now, and a walk with no letter before it is not taken (_CROSS_SPAN_RE, _scheme_start, D-SINK-95)"),
    (r".*[A-Za-z]", "provider",
     "linear: matched once a crossing scheme walk over the stretch it may cross, under DOTALL: `.*` runs to "
     "the end once and backs off to the last letter, and "
     "the stretches two walks read are disjoint: a walk that finds no scheme sets the bound at its P, and one that finds a scheme ends the search at its URL, whose run the next search starts past. cbd6679 broke that and said otherwise: its redact_urls went on past a URL whose run was empty without moving the bound, so every later walk crossed back to the same letter, quadratic on `a` and `<U+200B><U+2215><U+2215><TAB>` repeated (13 s at 40,001 characters, the review of cbd6679); an empty run is a URL now, and a walk with no letter before it is not taken (_LAST_LETTER, _scheme_start, D-SINK-95)"),
    (r".*[^ -~]", "provider",
     "linear: matched once a crossing scheme walk over the stretch before its last letter, under DOTALL: "
     "`.*` runs to the end once and backs off to the last CROSSABLE character (_LAST_CROSSABLE, "
     "_scheme_start, D-SINK-95)"),
    (r"[A-Za-z]", "provider",
     "linear: one character class, no quantifier, searched over one scheme segment at a time (_ASCII_LETTER, "
     "next_url and _scheme_start, D-SINK-95); and by next_url from the bound to a candidate's P, which the "
     "bound then moves to when it finds none, and from there to the next letter, where the search goes on, "
     "so each stretch is read once (the review of cbd6679's shortcut)"),
    (r"[^ -~]", "provider",
     "linear: one character class, no quantifier; sub over one URL's scheme and mark (_CROSSABLE, "
     "redact_urls' printed scheme, D-SINK-95)"),
    (r"(?<![^ ])[^ :]*+:[^ @]*+@[^ ]*+", "provider",
     "linear: a one-character lookbehind lets an attempt start only at a token's start (after a space, or "
     "at the text's start), where three possessive runs read the token once, to its first `:`, then to "
     "its next `@` or space, then to its end, none backed into; every start inside a token fails at the "
     "lookbehind; finditer resumes past each match (_CREDENTIAL_TOKEN, credential_spans: the candidate "
     "tokens, D-SINK-96)"),
    ("[^\x00-\x9f][\x00-\x1f\x7f-\x9f]*+[^\x00-\x9f]", "provider",
     "linear: an attempt starts only at a wide code point, then one possessive run of deleted controls, "
     "never backed into, then one character; an attempt at a wide code point reads the control run after "
     "it once, and the starts inside a run fail at their first character. Searched over one mark's P and "
     "between, and once a crossing scheme walk from its last letter to its P, each disjoint as the walks "
     "are (_WIDE_PAIR, next_url and _scheme_start: the caps, the review of cbd6679)"),
    ("[ -*,/:-@\\[-`{-~]|[^\x00-\x9f][\x00-\x1f\x7f-\x9f]*+[^\x00-\x9f]", "provider",
     "linear: two alternatives that part at their first character: a printable character, matched alone, "
     "or _WIDE_PAIR's attempt; searched once a cut, from the limit to the first such barrier "
     "(_WALK_BARRIER, cut_free_text, the review of cbd6679)"),
    ("'.*[^\\x00-\\x9f' + SLASH_ALIKE_CHARS + ']'", "provider",
     "linear: matched under DOTALL over a stretch outside every URL, `.*` runs to the end once and backs "
     "off to the last counted code point; asked at most twice a stretch, the second time short of the "
     "first's answer, and the stretches are between a colon and its `@`, each `@` asked once, or before a "
     "credential's colon, once a credential (_LAST_COUNTED, _counted_ends, D-SINK-96's cap, the review of "
     "cbd6679)"),
    ("[\t\n\x0b\x0c\r]", "provider",
     "linear: one character class, no quantifier; sub over one credential's span (_HELD_DELIMITERS, "
     "_fold_held, the review of cbd6679)"),
    ("[\x00-\x08\x0e-\x1f\x7f\x85]", "provider",
     "linear: one character class, no quantifier; sub over one credential's span (_HELD_CONTROLS, "
     "_fold_held, the review of cbd6679)"),
    ("[\U00002028\U00002029]", "provider",
     "linear: one character class, no quantifier; sub over one URL's scheme and mark (_MARK_SEPARATORS, "
     "fold_space, D-SINK-95)"),
    (r"[^ -.0-9;-~]*", "provider",
     "linear: matched at one given position, one class run and nothing after it, once a bare value that "
     "FILLER ended, over the `:`, FILLER and SLASH run after it (_MARK_REACH, parse_attrs, D-SINK-95); and "
     "once a _stop_end call, from the `stop` (the end of next_url's candidate search, the review of 4d13d71), "
     "which a UrlReading asks once and a next_url call with a `stop` and no `stop_end` once (the review of "
     "2942e41)"),
    (r"[^\x00-\x2c/:-@\[-\^`{-\x7f\s]*", "provider",
     "linear: matched at one given position, one class run and nothing after it, once an `@` a bare value's "
     "gated growth would take, from it, once a token; the class holds no `@`, so the runs read after the "
     "`@`s of one token are disjoint (_HOST_NAME_RUN, host_shaped, last_hosted_at, parse_attrs, the reviews "
     "of 4d13d71 and 2942e41)"),
    ("[(\\[{<\"'`]*", "provider",
     "linear: matched at one given position, one class run and nothing after it, once a "
     "_unnamed_scheme_credential call, from its token's start (_OPENING_RUN, the review of 2942e41)"),
    (r"\[[0-9A-Fa-f:.]+\]", "provider",
     "linear: matched at one given position: a literal `[`, one class run ended by the `]` it cannot hold, "
     "so it backs off at most once; once a host_shaped call (_HOST_IPV6_RUN)"),
    (r":[0-9]+", "provider",
     "linear: matched at one given position, a literal `:` and one class run; once a host_shaped call "
     "(_HOST_PORT_RUN)"),
    (r"^([A-Za-z][A-Za-z0-9+.\-]*):(.*)$", "user",
     "linear: anchored; the scheme run cannot hold ':' so it backs off at most once over its length, "
     "and (.*)$ under DOTALL reaches the end at once (_SCHEME_RE, _SOURCE_SCHEME_RE)"),
    (r"[/?#]", "provider",
     "linear: one character class (_AUTHORITY_END: validate_source_url's user text, and since R32a' "
     "run_host_parts' provider text, the end of a free-text URL's authority)"),
    (r"[:\[\]]", "user", "linear: one character class (_BARE_HOST_CHARS)"),
    (r"^[0-9]+$", "user", "linear: anchored, one run then $ (_ASCII_DIGITS)"),
    (r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", "user",
     "linear: fullmatch from one start; the branches part at the first character, a branch's two digit "
     "runs are split by a `.` the first cannot hold, and the exponent's run by an e or E "
     "(_STORED_DECIMAL, coerce_int over a hand-edited state.json)"),
    ("[\u200b-\u200d\u2060\ufeff]", "user", "linear: one character class (_ZERO_WIDTH)"),
    (r"^\[(?=[0-9A-Fa-f.]*:)[0-9A-Fa-f:.]*(?:%25[A-Za-z0-9._~\-]+)?\]$", "user",
     "linear: fixed by lane-bounds-h (was two adjacent runs over one class, k*k): a lookahead over the "
     "class without ':' and ONE run, which nothing after it can make back off more than once a "
     "character (_IPV6_LITERAL)"),
    (r"%(?![0-9A-Fa-f]{2})", "user",
     "linear: literal prefix '%', fixed-width lookahead (_BAD_ESCAPE)"),
    (r"^(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?\s*(?:([+-])(\d{2})(\d{2})|Z)?$", "provider",
     "linear: anchored match, fixed-width digit groups; the only run is \\s*, which a digit cannot "
     "extend, so it backs off at most once over its length on each of at most 8 ways through the "
     "three optional groups (_XMLTV_TIME)"),
    (r"[\t\n\x0b\x0c\r\x1c-\x20\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000!-/:-@\[-`{-~]+", "provider",
     "linear: one class run and nothing after it (_PUNCT, search_key; its whitespace enumerated by D-ID-5)"),
    (r"[\t\n\x0b\x0c\r\x1c-\x20\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000!-)\,-/:-@\[-`{-~]+", "provider",
     "linear: one class run and nothing after it (_ID_PUNCT, the id and EPG name keys; its whitespace enumerated by D-ID-5)"),
    (r"\((?:\d{3,4}p|sd|hd|fhd|uhd|4k|h\.?26[45])\)"
     r"|\[\s*not\s*24\s*(?:[-/]\s*)?7\s*\]"
     r"|\[\s*geo[\s-]*blocked\s*\]", "provider",
     "linear: every alternative opens with a literal '(' or '['; every two \\s* runs have a "
     "MANDATORY character between them that whitespace cannot be -- `not`, `24`, `7`, `geo`, "
     "`blocked`, or the `[-/]` that opens the optional group the fourth run lives in (D-EPG-12: it "
     "used to be `[-/]?\\s*`, an optional atom between two runs, which this guard now grades "
     "super-linear by structure) -- so each run backs off at most once over its own length, and the "
     "text is a name folded and cut to EPG_MAX_DISPLAY_NAME by epg_name_text (_EPG_NAME_NOISE)"),
    (r'\s*([A-Za-z0-9_.\-]+)="([^"]*)"', "provider",
     "linear: matched at parse_attrs' position only, which moves past each match and stops at the "
     "first failure; the key run cannot hold '=' and the value run cannot hold '\"' (_ATTR_QUOTED). Since "
     "D-SINK-80 a value inside a URL's run may close past the match, and the walk resumes after that close "
     "or stops: it never moves back, so the walk stays one pass. The credential reading behind the bare "
     "branch's growth (token_credential, D-SINK-96) is one UrlReading a line, read as far as a token asks: "
     "this said the reads were bounded while 4d13d71 made one reading a token, each reading the URLs to "
     "the line's end, quadratic in a line of `a=x:y` values before an `@` (42.8 s on a 96,000-character "
     "#EXTINF line; the review of 4d13d71)"),
    (r'\s*([A-Za-z0-9_.\-]+)=([^\s,"]+)', "provider",
     "linear: as _ATTR_QUOTED; the value run has nothing after it (_ATTR_BARE)"),
    (r"^[A-Za-z][A-Za-z0-9+.\-]*://([^/?#]*)", "user",
     "linear: anchored; the scheme run cannot hold ':' and the authority run has nothing after it "
     "(host_port_of)"),
    (r"\s*(-?\d+(?:\.\d+)?)?", "provider",
     "linear: matched at the start of the #EXTINF body, disjoint runs, one optional fraction "
     "(parse_extinf)"),
    (r"[.:]", "user", "linear: one character class (looks_like_host)"),
    (r"[?#].*$", "user",
     "linear: charset prefix, then .* under DOTALL reaches the end and $ holds there; one match "
     "(validate_source_url's file branch)"),
    (r"[0-9]{1,7}", "user", "linear: bounded quantifier (the channel-number override)"),
    (r"^--[a-z0-9][a-z0-9-]*(=.*)?$", "user",
     "linear: anchored; the name run cannot hold '=', and .* stops at a line break and backs off "
     "at most once to $ (MPV_ARG_RE, the user's own mpvArgs)"),
    (r"-(add|append|set|pre|clr|del|remove|toggle)$", "user",
     "linear: literal prefix '-', a fixed set of words then $ at each one (MPV_LIST_SUFFIX_RE)"),
    (r"-[0-9a-f]{8}\Z", "own",
     "linear: a bounded quantifier, so each start search() tries costs at most 9 steps; the text is "
     "a file name in the plugin's own cache folder (_TEMP_SUFFIX, is_stale_temp_name, D-SRC-60)"),
    (r"[0-9a-f]{8}\Z", "own",
     "linear: match() at the start only, a bounded quantifier; a file name in the plugin's own logo "
     "folder (_LOGO_NAME, the ceiling's sweep of unnamed files, D-LOGO-18)"),
]


def pattern_key(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ast.unparse(node)


# Where each re.<call> takes its flags positionally: compile(pattern, flags),
# search/match/fullmatch/findall/finditer(pattern, string, flags),
# split(pattern, string, maxsplit, flags), sub/subn(pattern, repl, string,
# count, flags).
FLAGS_AT = {"compile": 1, "search": 2, "match": 2, "fullmatch": 2, "findall": 2, "finditer": 2,
            "split": 3, "sub": 4, "subn": 4}


def call_flags(node):
    """The re.X flags a call names, positionally (FLAGS_AT) or as `flags=`,
    as an int; 0 when it names none, None when it is an expression this
    reader cannot evaluate (which the guard reports, so the walk never runs
    under the wrong flags in silence)."""
    expr = None
    at = FLAGS_AT[node.func.attr]
    if len(node.args) > at:
        expr = node.args[at]
    for keyword in node.keywords:
        if keyword.arg == "flags":
            expr = keyword.value
    if expr is None:
        return 0

    def value(e):
        if isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name) and e.value.id == "re":
            flag = getattr(re, e.attr, None)
            return int(flag) if isinstance(flag, re.RegexFlag) else None
        if isinstance(e, ast.BinOp) and isinstance(e.op, ast.BitOr):
            left, right = value(e.left), value(e.right)
            return None if left is None or right is None else left | right
        if isinstance(e, ast.Constant) and isinstance(e.value, int):
            return e.value
        return None

    return value(expr)


# One sample character at a time is the only input a pattern is ever run on
# here: the Latin-1 range, and a few beyond it that `\s`, `\w` and a
# case fold treat differently from ASCII.
_SAMPLE = [chr(code) for code in range(0x100)] + list("\u0085\u2003\u2028\u2029\u3000\uff12\u0301\U0001f600")
_REPEATS = (re._parser.MAX_REPEAT, re._parser.MIN_REPEAT, re._parser.POSSESSIVE_REPEAT)
_SINGLE = (re._parser.LITERAL, re._parser.NOT_LITERAL, re._parser.IN, re._parser.ANY, re._parser.CATEGORY)


def _unwrap(item):
    """A group holding exactly one item stands for that item."""
    op, av = item
    while op == re._parser.SUBPATTERN and len(av[3]) == 1:
        op, av = av[3][0]
    return op, av


def _matched(state, flags, item):
    """The sample characters one single-character atom matches, read by
    compiling that atom alone under the pattern's flags."""
    compiled = re._compiler.compile(re._parser.SubPattern(state, [item]), flags)
    return frozenset(ch for ch in _SAMPLE if compiled.match(ch))


def _unbounded_class(state, flags, item):
    """The character set of an unbounded repeat over one single-character
    atom, else None."""
    op, av = _unwrap(item)
    if op not in _REPEATS or av[1] != re._parser.MAXREPEAT or len(av[2]) != 1:
        return None
    body = _unwrap(av[2][0])
    if body[0] not in _SINGLE:
        return None
    return _matched(state, flags, body)


def _sequences(seq):
    """Every sequence inside a parsed pattern, the top one included."""
    yield seq
    for op, av in seq:
        if op == re._parser.SUBPATTERN:
            yield from _sequences(av[3])
        elif op in _REPEATS:
            yield from _sequences(av[2])
        elif op == re._parser.BRANCH:
            for alternative in av[1]:
                yield from _sequences(alternative)
        elif op in (re._parser.ASSERT, re._parser.ASSERT_NOT):
            yield from _sequences(av[1])
        elif op == re._parser.ATOMIC_GROUP:
            yield from _sequences(av)
        elif op == re._parser.GROUPREF_EXISTS:
            for alternative in av[1:]:
                if alternative is not None:
                    yield from _sequences(alternative)


def _absorbable(state, flags, item, first):
    """Could the FIRST run have taken this item's text? Yes for anything
    that may match nothing (an anchor, an assertion, a group or a repeat
    with minimum width 0) and for one character the first class matches."""
    op, av = _unwrap(item)
    if re._parser.SubPattern(state, [(op, av)]).getwidth()[0] == 0:
        return True
    if op in _SINGLE:
        return bool(_matched(state, flags, (op, av)) & first)
    return False


def super_linear_pairs(pattern, flags=0):
    """The super-linear pairs in `pattern`: two unbounded repeats over
    overlapping single-character classes with nothing between them the first
    run could not have taken. Each is (the first atom's source text, the
    second's). Empty for a pattern this shape is absent from; see the module
    docstring for what that does and does not say."""
    parsed = re._parser.parse(pattern, flags)
    flags |= parsed.state.flags
    state = parsed.state
    found = []
    for seq in _sequences(parsed):
        items = list(seq)
        for i, item in enumerate(items):
            first = _unbounded_class(state, flags, item)
            if first is None:
                continue
            for j in range(i + 1, len(items)):
                second = _unbounded_class(state, flags, items[j])
                if second is not None:
                    if first & second:
                        found.append((_atom_text(items[i]), _atom_text(items[j])))
                    break
                if not _absorbable(state, flags, items[j], first):
                    break
    return found


_CATEGORY_TEXT = {re._parser.CATEGORY_SPACE: "\\s", re._parser.CATEGORY_NOT_SPACE: "\\S",
                  re._parser.CATEGORY_DIGIT: "\\d", re._parser.CATEGORY_NOT_DIGIT: "\\D",
                  re._parser.CATEGORY_WORD: "\\w", re._parser.CATEGORY_NOT_WORD: "\\W"}


def _atom_text(item):
    """A short spelling of one unbounded class repeat, for the report."""
    op, av = _unwrap(item)
    kind, body = av[0], _unwrap(av[2][0])
    if body[0] == re._parser.LITERAL:
        text = chr(body[1])
    elif body[0] == re._parser.ANY:
        text = "."
    elif body[0] == re._parser.IN and len(body[1]) == 1 and body[1][0][0] == re._parser.CATEGORY:
        text = _CATEGORY_TEXT.get(body[1][0][1], str(body[1][0][1]))
    elif body[0] == re._parser.CATEGORY:
        text = _CATEGORY_TEXT.get(body[1], str(body[1]))
    else:
        text = "[" + " ".join(str(part) for part in body[1]) + "]" if body[0] == re._parser.IN else str(body)
    return "%s{%d,}" % (text, kind)


def scan(paths):
    """-> (sites, problems): every regex call as (path, line, key)."""
    sites, problems = [], []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        tree = ast.parse(source, filename=path)
        rel = os.path.relpath(path, ROOT)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "re":
                problems.append("%s:%d: `from re import` hides a regex call from this guard" % (rel, node.lineno))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "re" and alias.asname not in (None, "re"):
                        problems.append("%s:%d: `import re as %s` hides a regex call from this guard"
                                        % (rel, node.lineno, alias.asname))
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and isinstance(node.func.value, ast.Name) and node.func.value.id == "re"
                  and node.func.attr in CALLS):
                if not node.args:
                    problems.append("%s:%d: re.%s with no positional pattern" % (rel, node.lineno, node.func.attr))
                    continue
                key = pattern_key(node.args[0])
                sites.append((rel, node.lineno, key))
                if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    flags = call_flags(node)
                    if flags is None:
                        problems.append("%s:%d: flags this guard cannot read; name them as re.X or re.X | re.Y"
                                        % (rel, node.lineno))
                        continue
                    try:
                        pairs = super_linear_pairs(key, flags)
                    except (re.error, ValueError, TypeError, AttributeError, IndexError) as error:
                        problems.append("%s:%d: the guard could not walk %r (%s)" % (rel, node.lineno, key, error))
                        continue
                    for first, second in pairs:
                        problems.append("%s:%d: super-linear shape in %r: %s and %s are two unbounded repeats "
                                        "over overlapping classes with nothing between them the first could not "
                                        "take, so a run of k costs about k*k/2 (D-EPG-12); put a mandatory "
                                        "character the first class cannot hold between them"
                                        % (rel, node.lineno, key, first, second))
    return sites, problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--helper-dir", default=os.path.join(ROOT, "bin", "helper"),
                        help="the directory of helper parts to scan (default: bin/helper)")
    args = parser.parse_args(argv)
    paths = sorted(os.path.join(args.helper_dir, name) for name in os.listdir(args.helper_dir)
                   if name.endswith(".py") and not name.startswith("."))
    if not paths:
        print("helper regex guard: no helper parts under %s" % args.helper_dir)
        return 1
    sites, problems = scan(paths)
    reviewed = {}
    for pattern, reads, verdict in REVIEWED:
        if pattern in reviewed:
            problems.append("REVIEWED lists %r twice" % pattern)
        if reads not in ("provider", "user", "own"):
            problems.append("REVIEWED %r: what it reads must be provider, user or own" % pattern)
        if not (verdict.startswith("linear: ") or verdict.startswith("constant: ")
                or verdict.startswith("open: ")):
            problems.append("REVIEWED %r: a verdict is `linear: why`, `constant: why` or `open: what and its id`" % pattern)
        reviewed[pattern] = (reads, verdict)
    found = set()
    for rel, line, key in sites:
        if key not in reviewed:
            problems.append("%s:%d: unreviewed regex %r -- add it to REVIEWED in scripts/check-helper-regex.py "
                            "with what it reads and why its cost is linear (or the defect id that holds it)"
                            % (rel, line, key))
        found.add(key)
    for pattern in reviewed:
        if pattern not in found:
            problems.append("REVIEWED holds %r, which no helper part compiles any more" % pattern)
    opened = [(pattern, reads, verdict) for pattern, (reads, verdict) in reviewed.items()
              if verdict.startswith("open") and pattern in found]
    for pattern, reads, verdict in opened:
        print("helper regex guard: OPEN on %s text: %r -- %s" % (reads, pattern, verdict))
    for problem in problems:
        print("helper regex guard: %s" % problem)
    print("helper regex guard: %d regex call(s) in %d part(s), %d pattern(s) reviewed, %d open, %d problem(s)"
          % (len(sites), len(paths), len(found & set(reviewed)), len(opened), len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
