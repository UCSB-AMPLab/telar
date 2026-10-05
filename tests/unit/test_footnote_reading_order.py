"""Unit Tests for Footnotes Numbered in the Order a Reader Meets Them

Python Markdown's footnote extension numbers notes in the order their
definitions appear. An author who writes a definition before the note they
reference first therefore publishes a superscript 2 above a superscript 1,
and a note list ordered by definition rather than by reading.

Ruled on 13 September: the numbers follow the reading order. The cost is
that a panel whose definitions are out of sequence renumbers on its next
build — measured first across every piece of real content available, where
no panel changes, because authors define notes in the order they cite them.

Each conversion is its own footnote namespace: top-level prose, each
widget section and each bibliography entry are separate sequences. A panel
with a widget in it does put them on one page, since the widget's HTML is
spliced into the panel's text before the panel is converted; that case is
tested in test_footnotes_per_conversion.py.

Version: v1.8.0
"""

import os
import re
import sys

import markdown
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.latex import convert_markdown


def _numbers(html):
    """Each reference as (identifier, printed number), in document order."""
    return [(m.group(1), m.group(2)) for m in
            re.finditer(r'href="#fn:([^"]+)"[^>]*>(\d+)', html)]


def _list_order(html):
    return re.findall(r'<li id="fn:([^"]+)"', html)


def _convert(text):
    return convert_markdown(text)


OUT_OF_ORDER = """Primero el zorro[^z] y luego el perro[^old].

[^old]: Nota sobre el perro.
[^z]: Nota sobre el zorro.
"""


class TestTheReaderMeetsNoteOneFirst:

    def test_the_first_reference_is_numbered_one(self):
        assert _numbers(_convert(OUT_OF_ORDER)) == [('z', '1'), ('old', '2')]

    def test_the_note_list_follows_the_same_order(self):
        """A list still in definition order contradicts the superscripts."""
        assert _list_order(_convert(OUT_OF_ORDER)) == ['z', 'old']

    def test_the_backref_title_carries_the_new_number(self):
        """It names the number, so leaving it stale makes it point wrong."""
        html = _convert(OUT_OF_ORDER)

        title = re.search(r'href="#fnref:z"[^>]*title="([^"]*)"', html).group(1)
        assert '1' in title and '2' not in title

    def test_definitions_already_in_order_are_untouched(self):
        """The case every existing site is in, which must not move."""
        text = "Uno[^a] dos[^b].\n\n[^a]: A.\n[^b]: B.\n"

        assert _numbers(_convert(text)) == [('a', '1'), ('b', '2')]
        assert _list_order(_convert(text)) == ['a', 'b']


class TestTheAwkwardShapes:

    def test_a_note_referenced_twice_keeps_its_first_number(self):
        text = "Uno[^b] dos[^a] tres[^b].\n\n[^a]: A.\n[^b]: B.\n"

        assert _numbers(_convert(text)) == [('b', '1'), ('a', '2'), ('b', '1')]

    def test_a_list_inside_a_note_does_not_confuse_the_reordering(self):
        """Only a note's own item carries id="fn:", which is the split."""
        text = ("Uno[^b] dos[^a].\n\n[^a]: A.\n[^b]: B\n\n"
                "    - uno\n    - dos\n")

        html = _convert(text)

        assert _list_order(html) == ['b', 'a']
        assert '<li>uno</li>' in html

    def test_prose_with_no_footnotes_is_returned_unchanged(self):
        html = markdown.markdown("Just prose.", extensions=['extra'])

        assert _convert("Just prose.") == html

    def test_a_defined_but_never_referenced_note_is_not_dropped(self):
        """Python Markdown emits it; losing it here would delete content."""
        text = "Solo uno[^a].\n\n[^a]: A.\n[^huerfana]: Nadie me cita.\n"

        html = _convert(text)

        assert 'Nadie me cita' in html

    def test_an_identifier_with_regex_characters_survives(self):
        text = "Uno[^b.1] dos[^a+2].\n\n[^a+2]: A.\n[^b.1]: B.\n"

        assert _numbers(_convert(text)) == [('b.1', '1'), ('a+2', '2')]


class TestEachConversionIsItsOwnSequence:
    """The namespaces are separate because the build converts separately.

    A widget section that began at 3 because a panel above it used two
    notes would be numbering across a boundary the reader cannot see.
    """

    def test_a_second_conversion_starts_again_at_one(self):
        first = _convert("Uno[^a].\n\n[^a]: A.\n")
        second = _convert("Otro[^b].\n\n[^b]: B.\n")

        assert _numbers(first) == [('a', '1')]
        assert _numbers(second) == [('b', '1')]


class TestItRunsOnEveryConversionSite:

    def test_the_shared_converter_applies_it(self):
        """Wired inside convert_markdown, so no call site can miss it.

        The defect class this release keeps meeting is a fix applied at
        one of two paths; footnotes reach panels, pages, widget sections
        and bibliography entries through this one function.
        """
        raw = markdown.markdown(OUT_OF_ORDER, extensions=['extra'])

        assert _numbers(raw) == [('z', '2'), ('old', '1')]
        assert _numbers(_convert(OUT_OF_ORDER)) == [('z', '1'), ('old', '2')]
