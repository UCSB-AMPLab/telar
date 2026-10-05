"""Unit Tests for Footnote Anchors That Are Unique on the Page

Each widget section and each bibliography entry is converted on its own,
so two of them may use the same label for two different notes. Their
anchors must still differ: a page holding `id="fn:s"` twice sends the
second reference, and the second note's return arrow, to the first.

A section's anchors carry its widget's id and its position in the widget.
The panel's own anchors keep the extension's plain form, so a panel
without widgets publishes exactly what it did before.

Version: v1.8.0
"""

import os
import re
import sys
from collections import Counter

import pytest

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))

import telar.widgets
from telar.markdown import process_inline_content


ACCORDION = """:::accordion
## One
X[^s] y[^r] and again[^s].

[^r]: R
[^s]: S

## Two
Z[^s].

[^s]: Other S
:::

Top[^s].

[^s]: Panel S
"""

# A blank line ends a bibliography entry, so each entry's definitions sit
# directly under its text.
BIBLIOGRAPHY = """:::bibliography
Primera entrada[^a].
[^a]: Nota de la primera.

Segunda entrada[^a].
[^a]: Nota de la segunda.
:::
"""


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch):
    """The widget templates are read from `_includes/widgets` in the cwd."""
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr(telar.widgets, '_widget_counter', 0)


def _render(text):
    return process_inline_content(text)['content']


def _anchor_ids(html):
    return re.findall(r'id="(fn(?:ref\d*)?:[^"]+)"', html)


def _references(html):
    """Each reference as (its own id, the note id it points at)."""
    return re.findall(
        r'<sup id="([^"]+)"><a class="footnote-ref" href="#([^"]+)"', html)


def _notes(html):
    """Each note id -> (its text, the reference ids its arrows point at)."""
    notes = {}
    for match in re.finditer(r'<li id="([^"]+)">(.*?)</li>', html, re.DOTALL):
        body = match.group(2)
        text = re.sub(r'<[^>]+>|&#160;|&#8617;', '', body).strip()
        backrefs = re.findall(r'class="footnote-backref" href="#([^"]+)"', body)
        notes.setdefault(match.group(1), []).append((text, backrefs))
    return notes


def _assert_every_link_meets_its_partner(html):
    notes = _notes(html)
    for ref_id, note_id in _references(html):
        assert len(notes[note_id]) == 1, note_id
        _, backrefs = notes[note_id][0]
        assert ref_id in backrefs, (ref_id, note_id)


class TestAccordionSections:

    def test_no_anchor_id_appears_twice(self):
        counts = Counter(_anchor_ids(_render(ACCORDION)))

        assert [i for i, n in counts.items() if n > 1] == []

    def test_each_reference_reaches_its_own_note(self):
        html = _render(ACCORDION)
        notes = _notes(html)
        texts = [notes[note_id][0][0] for _, note_id in _references(html)]

        assert texts == ['S', 'R', 'S', 'Other S', 'Panel S']

    def test_each_backlink_returns_to_its_own_reference(self):
        _assert_every_link_meets_its_partner(_render(ACCORDION))

    def test_the_panel_keeps_the_plain_anchor_form(self):
        """A panel without widgets must publish the same ids as before."""
        html = _render(ACCORDION)

        assert ('fnref:s', 'fn:s') in _references(html)

    def test_a_second_reference_in_a_section_keeps_its_own_return(self):
        """The extension's fnref2 for a repeated note survives the scope."""
        html = _render(ACCORDION)
        first_section = _notes(html)
        s_notes = [(k, v) for k, v in first_section.items()
                   if v[0][0] == 'S']

        assert len(s_notes) == 1
        assert len(s_notes[0][1][0][1]) == 2


class TestBibliographyEntries:

    def test_no_anchor_id_appears_twice(self):
        counts = Counter(_anchor_ids(_render(BIBLIOGRAPHY)))

        assert [i for i, n in counts.items() if n > 1] == []

    def test_each_reference_reaches_its_own_note(self):
        html = _render(BIBLIOGRAPHY)
        notes = _notes(html)
        texts = [notes[note_id][0][0] for _, note_id in _references(html)]

        assert texts == ['Nota de la primera.', 'Nota de la segunda.']

    def test_each_backlink_returns_to_its_own_reference(self):
        _assert_every_link_meets_its_partner(_render(BIBLIOGRAPHY))


class TestAPanelWithoutWidgets:

    def test_anchor_ids_are_unchanged(self):
        html = _render("Uno[^a] dos[^a].\n\n[^a]: A.\n")

        assert _anchor_ids(html) == ['fnref:a', 'fnref2:a', 'fn:a']
