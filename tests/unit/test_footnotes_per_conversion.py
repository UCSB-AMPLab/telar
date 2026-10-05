"""Unit Tests for Footnote Numbering Confined to Its Own Conversion

A panel with a widget in it is several conversions on one page: each
widget section and each bibliography entry is converted on its own, and
its HTML is then spliced into the panel's text before the panel itself is
converted. Every one of those conversions numbers its notes from 1, in the
order a reader meets them, and none of them may renumber a note that
another conversion produced.

The panel's own notes are the case that shows it. With two sections above
it using notes, a panel's first note must still be 1, its list must say 1
and 2, and the superscripts above that list must agree with it.

Version: v1.8.0
"""

import os
import re
import sys

import pytest

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))

from telar.markdown import process_inline_content


ACCORDION = """:::accordion
## One
X[^s] y[^r].

[^r]: R
[^s]: S

## Two
Z[^s].

[^s]: Other S
:::

Top[^t] and[^u].

[^u]: U
[^t]: T
"""

# A blank line ends a bibliography entry, so each entry's definitions sit
# directly under its text.
BIBLIOGRAPHY = """:::bibliography
Primera entrada[^a].
[^a]: Nota de la primera.

Segunda entrada[^b] con otra[^a].
[^a]: Nota A de la segunda.
[^b]: Nota B de la segunda.
:::

Arriba[^t].

[^t]: T
"""


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch):
    """The widget templates are read from `_includes/widgets` in the cwd."""
    monkeypatch.chdir(REPO_ROOT)


def _render(text):
    return process_inline_content(text)['content']


def _label(anchor):
    """The author's label, without the widget scope a section's anchors carry."""
    return re.sub(r'^widget-\d+-\d+-', '', anchor)


def _references(html):
    """Each reference as (label, printed number), in document order."""
    return [(_label(m.group(1)), m.group(2)) for m in
            re.finditer(r'class="footnote-ref" href="#fn:([^"]+)"[^>]*>(\d+)<',
                        html)]


def _note_lists(html):
    """Each footnote list's items as (label, backlink title number)."""
    lists = re.findall(r'<div class="footnote">.*?<ol>(.*?)</ol>', html,
                       re.DOTALL)
    return [[(_label(m.group(1)), m.group(2)) for m in re.finditer(
                r'<li id="fn:([^"]+)".*?class="footnote-backref"'
                r'[^>]*title="[^"]*?(\d+)[^"]*"', items, re.DOTALL)]
            for items in lists]


class TestAccordionSectionsAndThePanel:

    def test_each_section_and_the_panel_start_at_one(self):
        assert _references(_render(ACCORDION)) == [
            ('s', '1'), ('r', '2'),   # section One
            ('s', '1'),               # section Two
            ('t', '1'), ('u', '2'),   # the panel
        ]

    def test_each_list_follows_its_own_references(self):
        """The item order and the backlink titles match the superscripts."""
        assert _note_lists(_render(ACCORDION)) == [
            [('s', '1'), ('r', '2')],
            [('s', '1')],
            [('t', '1'), ('u', '2')],
        ]

    def test_the_panel_list_agrees_with_the_panel_superscripts(self):
        """An <ol> counts 1, 2 whatever its superscripts say."""
        html = _render(ACCORDION)
        panel_refs = [n for i, n in _references(html) if i in ('t', 'u')]
        panel_list = _note_lists(html)[-1]

        assert panel_refs == [str(k) for k in range(1, len(panel_list) + 1)]


class TestBibliographyEntries:

    def test_each_entry_numbers_only_its_own_notes(self):
        """Entry 2's [^a] is its second note, whatever entry 1 used."""
        assert _references(_render(BIBLIOGRAPHY)) == [
            ('a', '1'),               # entry 1
            ('b', '1'), ('a', '2'),   # entry 2
            ('t', '1'),               # the panel
        ]

    def test_each_entry_list_follows_its_own_references(self):
        assert _note_lists(_render(BIBLIOGRAPHY)) == [
            [('a', '1')],
            [('b', '1'), ('a', '2')],
            [('t', '1')],
        ]


class TestAPanelWithoutWidgets:

    def test_reading_order_numbering_is_unchanged(self):
        html = _render("Uno[^z] dos[^a].\n\n[^a]: A.\n[^z]: Z.\n")

        assert _references(html) == [('z', '1'), ('a', '2')]
        assert _note_lists(html) == [[('z', '1'), ('a', '2')]]
