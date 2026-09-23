"""Mutation proofs for the fidelity guard (CLAUDE.md rule 11).

The guard is new, so there is no "before" to run these against. Rule 11's
other half applies instead: every case here breaks one decision deliberately
and asserts the guard goes red at the NAMED layer, so a test cannot pass on an
unrelated failure. `test_baseline_is_green` is the control -- without it, a
guard that failed everything would pass every other case in this file.

Runs anywhere: pure text over the repo's own Guide.qml through the guard's own
declared transform. No display, no D-Bus, no Qt, no harness tree.

    python3 tests/a11y/test_fidelity.py

Deliberately NOT discoverable by `python3 -m unittest discover -s tests`
(there is no __init__.py here): docs/PLAN-NEXT.md decision 9 keeps the
accessibility work out of scripts/check.sh.

To grade a copy a real generator produced instead of the reference transform:

    A11Y_GENERATED=/path/to/GuideProbe.qml python3 tests/a11y/test_fidelity.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fidelity
import qmlscan

GUIDE = os.path.join(fidelity.REPO, "Guide.qml")
MODEL = os.path.join(fidelity.REPO, "Model.js")

# Floors, in the spirit of scripts/check.sh: a scanner that silently stopped
# finding declarations would make every assertion below vacuous.
MIN_DECLARATIONS = 55
MIN_ELEMENTS = 24


def source():
    with open(GUIDE) as handle:
        return handle.read()


def generated(text=None):
    """The copy under test: the reference transform, or a real generator's."""
    override = os.environ.get("A11Y_GENERATED")
    if override and text is None:
        with open(override) as handle:
            return handle.read()
    return fidelity.apply_transform(text if text is not None else source())


def layers(failures):
    return sorted(set(f.layer for f in failures))


def replace_once(case, text, old, new):
    case.assertEqual(text.count(old), 1,
                     "the anchor this mutation needs occurs %d time(s), not "
                     "once: %r" % (text.count(old), old))
    return text.replace(old, new, 1)


class ScannerFloor(unittest.TestCase):
    def test_the_guide_still_declares_what_the_guard_assumes(self):
        records, _frames = qmlscan.scan(source(), "Guide.qml")
        declared = [r for r in records if r["kind"] == "accessible"]
        elements = set(r["path"] for r in declared)
        self.assertGreaterEqual(len(declared), MIN_DECLARATIONS)
        self.assertGreaterEqual(len(elements), MIN_ELEMENTS)
        siblings = [r for r in records if r["kind"] == "sibling"]
        self.assertTrue(siblings, "no sibling bindings captured: the text: "
                                  "binding the credential leaks from would be "
                                  "invisible to this guard")

    def test_the_scanner_refuses_to_guess(self):
        with self.assertRaises(qmlscan.QmlParseError):
            qmlscan.scan("Item {\n  id: root\n", "broken.qml")


class Baseline(unittest.TestCase):
    def test_baseline_is_green(self):
        found = fidelity.check_pair(source(), generated())
        self.assertEqual(found, [], "\n".join(str(f) for f in found))

    def test_every_declared_rule_matches_the_shipping_file_exactly(self):
        # A rule that stopped matching, or started matching twice, means the
        # shipping file moved under the transform. apply_transform refuses.
        fidelity.apply_transform(source())

    def test_a_rule_that_does_not_fire_is_red(self):
        rules = list(fidelity.TRANSFORM_RULES) + [{
            "id": "T99-stale",
            "why": "a rule left behind after the line it edited was renamed",
            "before": ["    visible: root.neverExisted"],
            "after": ["    visible: false"],
        }]
        found = fidelity.check_pair(source(), generated(), rules=rules)
        self.assertIn("L2", layers(found))
        self.assertTrue(any("T99-stale" in f.summary for f in found))


    def test_a_rule_that_LEGITIMISES_an_accessibility_edit_is_red(self):
        """Poison the table itself, which nothing did before.

        The existing rule test catches a rule that stopped firing. The
        dangerous direction is the other one: a rule that DOES fire and
        declares an edit to an accessibility declaration as legitimate. That is
        how the guard would be talked into grading a copy whose markup the
        transform rewrote -- the exact failure it exists to prevent, arrived at
        through the table rather than through the transform.

        L1 is what must refuse it: no line a rule touches may contain
        `Accessible.` at all, whatever else the rule says about itself.
        """
        line = None
        for candidate in source().split("\n"):
            if "Accessible.role:" in candidate:
                line = candidate
                break
        self.assertIsNotNone(line, "the shipping guide declares no Accessible.role")
        edited = line.replace("Accessible.role:", "Accessible.ignored: true //")
        rules = list(fidelity.TRANSFORM_RULES) + [{
            "id": "T98-poison",
            "why": "a rule that claims editing a declaration is a legitimate transform",
            "before": [line],
            "after": [edited],
        }]
        # The copy is made to ACTUALLY carry the edit, which is the case that
        # matters. With a rule that merely fails to fire, L2 catches it as a
        # stale rule and L1 is never reached -- so a table poisoned in step
        # with the copy would slip past the weaker layer. Here the copy and the
        # table agree with each other and only L1 disagrees with both.
        poisoned_copy = generated().replace(line, edited, 1)
        self.assertIn(edited, poisoned_copy, "the copy must really carry the edit")
        found = fidelity.check_pair(source(), poisoned_copy, rules=rules)
        self.assertIn("L1", layers(found), "a rule touching an Accessible line must be refused")

    def test_the_table_cannot_permit_a_rule_that_matches_many_lines(self):
        """A rule broad enough to match repeatedly is a wildcard in disguise.

        `apply_transform` refuses a rule that does not match exactly once, so a
        table entry cannot be widened into one that quietly covers edits nobody
        declared.
        """
        rules = list(fidelity.TRANSFORM_RULES) + [{
            "id": "T97-wildcard",
            "why": "a rule whose before-block occurs many times over",
            "before": ["    }"],
            "after": ["    }"],
        }]
        with self.assertRaises(Exception):
            fidelity.apply_transform(source(), rules=rules)


class DroppedDeclaration(unittest.TestCase):
    """The failure the whole guard exists for: the transform loses a
    declaration and the harness grades a copy that never had it."""

    def test_a_dropped_accessible_name_is_red(self):
        copy = replace_once(
            self, generated(),
            "      Accessible.name: root.copy.accessibleCard\n", "")
        found = fidelity.check_pair(source(), copy)
        self.assertEqual(layers(found), ["L1", "L2", "L3"])
        detail = "\n".join(f.detail for f in found)
        self.assertIn("BorderSurface#card", detail)
        self.assertIn("Accessible.name", detail)

    def test_a_dropped_whole_element_is_red(self):
        copy = generated()
        start = copy.index("        ConfirmDialog {")
        # Through the block's own closing brace, so the copy still parses and
        # the guard has to notice the loss rather than the syntax.
        end = copy.index("\n", copy.index("        }\n", copy.index(
            "onConfirmed: root.confirmRemove()")))
        copy = copy[:start] + copy[end + 1:]
        found = fidelity.check_pair(source(), copy)
        self.assertIn("L3", layers(found))
        self.assertIn("ConfirmDialog#removeDialog",
                      "\n".join(f.detail for f in found))

    def test_a_declaration_the_transform_never_carried_is_red(self):
        """A NEW declaration in the shipping file that the copy lacks."""
        marker = '          Accessible.description: "FIDELITY PROOF MARKER"\n'
        anchor = "          Accessible.name: root.confirmMessage\n"
        drifted_source = replace_once(self, source(), anchor, anchor + marker)
        # The honest transform carries it: green.
        self.assertEqual(
            fidelity.check_pair(drifted_source,
                                fidelity.apply_transform(drifted_source)), [])
        # A transform that drops it: red, naming it.
        copy = fidelity.apply_transform(drifted_source).replace(marker, "", 1)
        found = fidelity.check_pair(drifted_source, copy)
        self.assertIn("L3", layers(found))
        self.assertIn("FIDELITY PROOF MARKER",
                      "\n".join(f.detail for f in found))


class AddedOrAlteredDeclaration(unittest.TestCase):
    def test_a_declaration_only_in_the_copy_is_red(self):
        anchor = "      Accessible.name: root.copy.accessibleCard\n"
        copy = replace_once(self, generated(), anchor,
                            anchor + '      Accessible.description: "copy only"\n')
        found = fidelity.check_pair(source(), copy)
        self.assertEqual(layers(found), ["L1", "L2", "L3"])
        self.assertIn("copy only", "\n".join(f.detail for f in found))

    def test_an_altered_value_is_red(self):
        copy = replace_once(self, generated(),
                            "      Accessible.name: root.copy.accessibleCard",
                            '      Accessible.name: "MUTATED CARD"')
        found = fidelity.check_pair(source(), copy)
        self.assertIn("L3", layers(found))
        self.assertIn("MUTATED CARD", "\n".join(f.detail for f in found))

    def test_a_moved_attachment_point_is_red(self):
        """Same declaration, same value, different element. The string still
        composes; the node it lands on is not the one the docs describe."""
        copy = replace_once(self, generated(),
                            "      Accessible.role: Accessible.Dialog\n"
                            "      Accessible.name: root.copy.accessibleCard\n",
                            "      Accessible.role: Accessible.Dialog\n")
        copy = replace_once(
            self, copy,
            "                Accessible.role: Accessible.List\n"
            "                Accessible.name: root.copy.accessibleGroups\n",
            "                Accessible.role: Accessible.List\n"
            "                Accessible.name: root.copy.accessibleGroups\n"
            "                Accessible.description: root.copy.accessibleCard\n")
        found = fidelity.check_pair(source(), copy)
        self.assertIn("L3", layers(found))


class SiblingBindings(unittest.TestCase):
    """Qt derives accessibility from more than the Accessible attached
    property. The prototype harness's own mutation 7 rebinds the field's
    `text:` to the masked rendering, which is where the credential is
    published from -- and which the product owner recorded as silently
    overwriting the user's stored value (docs/PLAN-NEXT.md decision 9). A
    harness may only grade that copy while saying out loud that it is not the
    shipping code."""

    def test_rebinding_the_field_text_is_red(self):
        copy = replace_once(self, generated(),
                            "                  text: root.fieldDisplay(fieldRow.fieldId)",
                            "                  text: Model.maskUrl(root.formValue(fieldRow.fieldId))")
        found = fidelity.check_pair(source(), copy)
        self.assertIn("L3", layers(found))
        detail = "\n".join(f.detail for f in found)
        self.assertIn("text = ", detail)
        self.assertIn("maskUrl", detail)

    def test_flipping_the_password_echo_is_red(self):
        copy = replace_once(self, generated(),
                            '                  password: fieldRow.fieldId === "password"',
                            "                  password: false")
        found = fidelity.check_pair(source(), copy)
        self.assertIn("L3", layers(found))


class UndeclaredChange(unittest.TestCase):
    def test_an_undeclared_line_change_is_red(self):
        copy = replace_once(self, generated(),
                            "    width: 1920", "    width: 1024")
        found = fidelity.check_pair(source(), copy)
        self.assertEqual(layers(found), ["L2"])

    def test_an_added_element_may_not_declare_accessibility(self):
        copy = replace_once(self, generated(),
                            "    id: probeShim\n",
                            "    id: probeShim\n"
                            '    Accessible.name: "probe"\n')
        found = fidelity.check_pair(source(), copy)
        self.assertIn("L4", layers(found))
        self.assertIn("probeShim", "\n".join(f.summary for f in found))


class HonestLimit(unittest.TestCase):
    """What the transform CANNOT carry across has to be red, not quietly
    regraded. An Accessible declaration on the PanelWindow is graded by this
    harness as a plain Window that is never shown, which is a different
    question from the one the shipping code asks."""

    def test_accessibility_on_the_rehosted_window_is_red(self):
        drifted = replace_once(self, source(),
                               "    exclusionMode: ExclusionMode.Ignore\n",
                               "    exclusionMode: ExclusionMode.Ignore\n"
                               '    Accessible.name: "IPTV guide window"\n')
        copy = fidelity.apply_transform(drifted)
        found = fidelity.check_pair(drifted, copy)
        # The copy carries the new line verbatim, so the line-level layers stay
        # silent: L1 and L2 see a legal transform. L5 names the limit, and L3
        # shows why it is one -- the moment that element is accessible, the
        # four layer-shell bindings and the visibility the transform rewrites
        # become part of its accessibility projection and are demonstrably not
        # the ones that ship.
        self.assertEqual(layers(found), ["L3", "L5"])
        self.assertIn("IPTV guide window", "\n".join(f.detail for f in found))
        self.assertIn("WlrLayershell", "\n".join(f.detail for f in found))


class VerbatimCopies(unittest.TestCase):
    def test_a_modified_model_copy_is_red(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as out:
            with open(MODEL) as handle:
                out.write(handle.read())
            out.write("\n// drift\n")
            path = out.name
        try:
            found = fidelity.check_copy(MODEL, path)
            self.assertEqual(layers(found), ["L6"])
        finally:
            os.unlink(path)

    def test_an_identical_model_copy_is_green(self):
        self.assertEqual(fidelity.check_copy(MODEL, MODEL), [])


class TreeGate(unittest.TestCase):
    """The one-call entry point the harness is meant to gate itself on."""

    def _tree(self, guide_text, model_text=None):
        import tempfile
        work = tempfile.mkdtemp(prefix="a11y-tree-")
        with open(os.path.join(work, "GuideProbe.qml"), "w") as out:
            out.write(guide_text)
        with open(MODEL) as handle:
            model = handle.read()
        with open(os.path.join(work, "Model.js"), "w") as out:
            out.write(model if model_text is None else model_text)
        return work

    def test_a_faithful_tree_passes(self):
        """kit=False is REQUIRED here, and that is the point.

        This fixture has no host kit, so the gate refuses to call itself
        satisfied unless the caller says that is deliberate. Before that was
        enforced, guard_tree ran four of its eight layers while its own
        docstring told the harness to gate on it, and a reviewer swapped the
        host kit underneath a copy and turned a real credential failure green.
        """
        import shutil
        work = self._tree(fidelity.apply_transform(source()))
        try:
            self.assertEqual(fidelity.guard_tree(work, kit=False), [])
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_a_tree_with_no_kit_is_a_finding_unless_you_say_so(self):
        """Silence is the failure mode; an unstated missing kit is red."""
        import shutil
        work = self._tree(fidelity.apply_transform(source()))
        try:
            found = fidelity.guard_tree(work)
            self.assertTrue(found, "a missing host kit must not pass quietly")
            self.assertTrue(any(f.layer == "L8" for f in found),
                            "the missing kit must be reported as L8, got %s"
                            % [f.layer for f in found])
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_gate_runs_every_layer_it_has(self):
        """The reviewer's finding, pinned.

        guard_tree is documented as the one call a harness gates itself on. It
        called check_pair and check_copy only; check_kit (L8) and
        ungraded_surfaces (L7) were reachable from the command line alone. A
        thing named as the complete check was not the complete check, and only
        the name said otherwise, which is CLAUDE.md rule 13 inside the guard
        written to stop exactly that.
        """
        import inspect
        body = inspect.getsource(fidelity.guard_tree)
        for layer in ("check_pair", "check_copy", "check_kit",
                      "ungraded_surfaces"):
            self.assertIn(layer, body,
                          "guard_tree must call %s; a layer reachable only "
                          "from the CLI is a layer the harness never runs"
                          % layer)

    def test_an_accepted_ungraded_surface_needs_a_stated_reason(self):
        """The L7 allow-list may not become a silent dumping ground."""
        self.assertIn("BarWidget.qml", fidelity.UNGRADED_ACCEPTED)
        for name, why in fidelity.UNGRADED_ACCEPTED.items():
            self.assertTrue(len(why) > 30,
                            "%s is allow-listed with no real reason" % name)

    def test_a_drifted_tree_is_reported(self):
        import shutil
        copy = replace_once(self, fidelity.apply_transform(source()),
                            "      Accessible.name: root.copy.accessibleCard\n",
                            "")
        work = self._tree(copy)
        try:
            self.assertIn("L3", layers(fidelity.guard_tree(work)))
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_a_missing_copy_is_reported(self):
        import shutil
        work = self._tree(fidelity.apply_transform(source()))
        try:
            os.unlink(os.path.join(work, "GuideProbe.qml"))
            self.assertEqual(layers(fidelity.guard_tree(work)), ["L0"])
        finally:
            shutil.rmtree(work, ignore_errors=True)


class HostKit(unittest.TestCase):
    """The guide's fields ARE host components. `Ui/TextField.qml` is a
    Controls TextField and the credential is published by that control's own
    accessibility, so a guard that watched only Guide.qml would let the kit be
    swapped underneath it."""

    def setUp(self):
        import shutil
        import tempfile
        self.work = tempfile.mkdtemp(prefix="a11y-kit-")
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)
        self.src = os.path.join(self.work, "Ui")
        self.copy = os.path.join(self.work, "copy", "Ui")
        os.makedirs(self.src)
        os.makedirs(self.copy)

    def write(self, where, name, text):
        with open(os.path.join(where, name), "w") as out:
            out.write(text)

    def both(self, name, text):
        self.write(self.src, name, text)
        self.write(self.copy, name, text)

    def test_an_identical_kit_passes(self):
        self.both("TextField.qml", "TextField {\n  id: field\n}\n")
        self.assertEqual(fidelity.check_kit(self.src, self.copy, {}), [])

    def test_an_undeclared_difference_is_red(self):
        self.both("TextField.qml", "TextField {\n  id: field\n}\n")
        self.write(self.copy, "TextField.qml", "TextField {\n  id: other\n}\n")
        found = fidelity.check_kit(self.src, self.copy, {})
        self.assertEqual(layers(found), ["L8"])
        self.assertIn("TextField.qml", found[0].summary)

    def test_a_declared_patch_passes(self):
        self.both("Util.qml", "QtObject {\n  property int x: 1\n}\n")
        self.write(self.copy, "Util.qml", "QtObject {\n  property int x: 2\n}\n")
        self.assertEqual(
            fidelity.check_kit(self.src, self.copy, {"Ui/Util.qml": "why"}), [])

    def test_a_patch_that_touches_accessibility_is_red(self):
        self.both("Util.qml", "QtObject {\n  Accessible.name: \"kit\"\n}\n")
        self.write(self.copy, "Util.qml", "QtObject {\n}\n")
        found = fidelity.check_kit(self.src, self.copy, {"Ui/Util.qml": "why"})
        self.assertEqual(layers(found), ["L8"])
        self.assertIn("touches accessibility", found[0].summary)

    def test_a_stale_patch_declaration_is_red(self):
        self.both("Util.qml", "QtObject {\n}\n")
        found = fidelity.check_kit(self.src, self.copy, {"Ui/Util.qml": "why"})
        self.assertEqual(layers(found), ["L8"])
        self.assertIn("stale", found[0].summary)

    def test_a_missing_or_extra_file_is_red(self):
        self.both("TextField.qml", "TextField {\n}\n")
        self.write(self.src, "Button.qml", "Button {\n}\n")
        self.write(self.copy, "Invented.qml", "Invented {\n}\n")
        found = fidelity.check_kit(self.src, self.copy, {})
        self.assertEqual(layers(found), ["L8"])
        self.assertEqual(len(found), 2, "missing and extra are separate findings")
        detail = "\n".join(f.detail for f in found)
        self.assertIn("Button.qml", detail)
        self.assertIn("Invented.qml", detail)


class Inventory(unittest.TestCase):
    def test_a_surface_nobody_grades_is_named(self):
        gaps = dict(fidelity.ungraded_surfaces(fidelity.REPO, {"Guide.qml"}))
        self.assertIn("BarWidget.qml", gaps)
        self.assertGreaterEqual(gaps["BarWidget.qml"], 2)

    def test_a_graded_surface_is_not_named(self):
        gaps = dict(fidelity.ungraded_surfaces(fidelity.REPO,
                                               {"Guide.qml", "BarWidget.qml"}))
        self.assertEqual(gaps, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
