"""Unit Tests Driving Both Panel Paths With One Body

A panel can be written in a spreadsheet cell or in a markdown file under
`telar-content/texts/`, and the two reach the reader by different
functions: `process_inline_content` and `read_markdown_file`. They are
meant to publish the same text from the same source.

Three times in v1.8.0 they did not, and each time the wrong one was wrong
quietly: a carousel image given as a filename, LaTeX inside a widget, and
a panel opening with `---`. Three separate
fixes do not stop a fourth. This does: one body, both paths, compared.

It cannot assert that either path is *right*. What it asserts is that
they do not disagree, which is the property the three defects broke and
the one neither path can check about itself.

**And it cannot see a change to what they now share.** Measured, not
assumed: restoring the two different front-matter rules fails the `a rule
on the first line` case here, but breaking the single rule they now call
leaves every comparison green, because both paths move together. So this
file guards against the paths drifting apart again, and the behaviour
itself is held by the named tests below. A comparison between two callers
of one function is a weaker instrument the moment the function is one —
which is the shape of fix that made it so.

Version: v1.8.0
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.markdown import read_markdown_file, process_inline_content


# Each is a whole panel body, written the way an author would write it.
BODIES = {
    'plain prose': "Una frase y luego otra.",
    'a rule on the first line': (
        "---\nUna línea bajo una regla.\n---\nEl resto del panel."),
    'a rule in the middle': "Antes.\n\n---\n\nDespués.",
    'front matter with a title': "---\ntitle: Mi panel\n---\nEl cuerpo.",
    'bold and a link': "Un **término** y un [enlace](https://telar.org).",
    'inline maths': r"La masa es $E = mc^2$ en reposo.",
    'display maths': "Antes.\n\n$$a < b$$\n\nDespués.",
    'maths with a less-than': r"Cuando $a <b$ se cumple.",
    'a markdown list': "- uno\n- dos\n- tres",
    'a heading': "## Un título\n\nY su párrafo.",
    'a blockquote': "> Una cita.\n\nY la respuesta.",
    'an html span': 'Un <span class="x">fragmento</span> crudo.',
    'a footnote': "Una nota[^a] aquí.\n\n[^a]: El texto de la nota.",
    'two footnotes out of order': (
        "Zorro[^z] y perro[^p].\n\n[^p]: El perro.\n[^z]: El zorro."),
    'an ampersand': "Uno & dos.",
    'a bare url': "Ver https://telar.org para más.",
    'accented text': "Añoranza, corazón, güiro.",
    'trailing whitespace': "Una frase.   \n\nOtra.   ",
}


@pytest.fixture
def site(tmp_path, monkeypatch):
    """read_markdown_file resolves against telar-content/texts in the CWD."""
    texts = tmp_path / 'telar-content' / 'texts'
    texts.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return texts


class TestTheTwoPathsPublishTheSameText:

    @pytest.mark.parametrize('name', sorted(BODIES), ids=lambda n: n)
    def test_one_body_reaches_the_reader_the_same_way(self, site, name):
        body = BODIES[name]
        (site / 'panel.md').write_text(body, encoding='utf-8')

        from_file = read_markdown_file('panel.md')
        from_cell = process_inline_content(body)

        assert from_file is not None and from_cell is not None
        assert from_file['content'] == from_cell['content'], name
        assert from_file['title'] == from_cell['title'], name

    def test_the_bodies_are_not_all_trivially_equal(self):
        """Guards the comparison against a fixture set that proves nothing.

        Bodies that all render to the same HTML would satisfy every
        assertion above while exercising one shape.
        """
        assert len({body for body in BODIES.values()}) == len(BODIES)
        assert len(BODIES) >= 15


class TestTheDefectsThatMadeThisNecessary:
    """Named, so a regression says which one came back."""

    def test_a_leading_rule_keeps_its_first_block(self, site):
        """The file path read it as front matter and dropped it."""
        body = "---\nUna línea bajo una regla.\n---\nEl resto."
        (site / 'panel.md').write_text(body, encoding='utf-8')

        from_file = read_markdown_file('panel.md')

        assert 'bajo una regla' in from_file['content']

    def test_front_matter_with_a_title_is_still_front_matter(self, site):
        """The other direction, which the fix must not break."""
        body = "---\ntitle: Mi panel\n---\nEl cuerpo."
        (site / 'panel.md').write_text(body, encoding='utf-8')

        from_file = read_markdown_file('panel.md')

        assert from_file['title'] == 'Mi panel'
        assert 'title:' not in from_file['content']

    def test_a_titleless_mapping_is_shown_rather_than_swallowed(self, site, capsys):
        """And says why, or its author sees YAML on the page for no reason."""
        body = "---\nlayout: panel\n---\nEl cuerpo."
        (site / 'panel.md').write_text(body, encoding='utf-8')

        from_file = read_markdown_file('panel.md')

        assert 'layout' in from_file['content']
        assert 'title:' in capsys.readouterr().out

    def test_prose_under_a_rule_says_nothing(self, site, capsys):
        """The common case, which must stay quiet or the warning is noise."""
        body = "---\nUna línea bajo una regla.\n---\nEl resto."
        (site / 'panel.md').write_text(body, encoding='utf-8')

        read_markdown_file('panel.md')

        assert 'Warning' not in capsys.readouterr().out
