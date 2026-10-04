"""Unit Tests for LaTeX Surviving Markdown Conversion

Python Markdown rewrites LaTeX it does not recognise as maths. It reads
`\\(` and `\\[` as escaped punctuation and drops the backslash, which
removes the delimiters that mark an expression as maths at all; inside
`$$...$$` it entity-encodes an alignment `&`, collapses `\\\\` to one
backslash, unescapes braces, and turns `*` into emphasis tags in the
middle of a formula.

Panel content is converted through one pipeline that holds the maths out
of the converter's reach. Every other conversion in the build — widget
sections, bibliography entries, carousel captions and credits, image
captions, page bodies, glossary bodies, demo layers — called the library
directly, so the same expression published correctly at the top level of
a panel and was destroyed everywhere else.

These tests read the published text back out of each site. The table is
the one on the issue, extended to the sites it did not name, and every
row is a case that was verified corrupt before the shared helper existed.

Version: v1.8.0
"""

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from telar.demo import _add_demo_layers
from telar.images import process_images
from telar.latex import convert_markdown
from telar.markdown import process_inline_content
from telar.widgets import (
    parse_bibliography_widget,
    parse_carousel_widget,
    parse_markdown_sections,
)


# Every expression Python Markdown was found to rewrite, and the one
# (`\ce{}`) it leaves alone because `\c` is not a Markdown escape. The
# chemistry case is here so a fix that protects by escaping everything
# still has to leave untouched text untouched.
EXPRESSIONS = [
    pytest.param(r'\(E=mc^2\)', id='alternative-inline-delimiters'),
    pytest.param(r'\[E=mc^2\]', id='alternative-display-delimiters'),
    pytest.param(r'\begin{aligned} a &= b \end{aligned}', id='alignment-ampersand'),
    pytest.param(r'$$a \\ b$$', id='latex-line-break'),
    pytest.param(r'$$\{x\}$$', id='escaped-braces'),
    pytest.param(r'$$a*b*c$$', id='asterisks-are-not-emphasis'),
    pytest.param(r'$$x \_ y$$', id='escaped-underscore'),
    pytest.param(r'\ce{H2O}', id='chemistry'),
]


def _panel(source):
    return process_inline_content(source)['content']


def _accordion_section(source):
    return parse_markdown_sections('## Section\n%s' % source)[0]['content_html']


def _bibliography_entry(source):
    parsed = parse_bibliography_widget(source, 'test', [])
    return parsed['entries'][0]['content_html']


def _carousel_field(field, source):
    block = 'image: a.jpg\nalt: an image\n%s: %s\n' % (field, source)
    return parse_carousel_widget(block, 'test', [])['items'][0][field]


def _image_caption(source):
    return process_images('![an image](a.jpg)\n%s\n' % source)


def _demo_layer(source):
    step_data = {}
    _add_demo_layers(step_data, {'layers': {'layer1': {'content': source}}},
                     'probe', {})
    return step_data['layer1_text']


SITES = {
    'panel': _panel,
    'accordion-or-tabs-section': _accordion_section,
    'bibliography-entry': _bibliography_entry,
    'carousel-caption': lambda source: _carousel_field('caption', source),
    'carousel-credit': lambda source: _carousel_field('credit', source),
    'image-caption': _image_caption,
    'demo-layer': _demo_layer,
}


@pytest.mark.parametrize('site', sorted(SITES), ids=sorted(SITES))
@pytest.mark.parametrize('source', EXPRESSIONS)
class TestTheExpressionReachesThePageAsWritten:

    def test_the_published_text_still_contains_it(self, site, source):
        published = SITES[site](source)

        assert source in _as_text(published), published


def _as_text(published):
    """Undo the HTML escaping a sanitised field applies to its text.

    A carousel caption is sanitised, so the maths comes back escaped and
    the browser decodes it before KaTeX reads the text node. Comparing
    against the author's source means reading it back the same way.
    """
    return (published.replace('&lt;', '<')
                     .replace('&gt;', '>')
                     .replace('&amp;', '&'))


class TestEachSiteKeepsItsOwnExtensions:
    """A single default in the shared helper would change how a site renders.

    The extension lists genuinely differ — a caption converts with none, a
    panel with `extra` and `nl2br`, a page with `sane_lists` as well — so
    the helper takes the list from the caller.
    """

    def test_a_caption_does_not_get_nl2br(self):
        """`nl2br` in a caption would turn a wrapped line into a <br>."""
        assert '<br' not in _carousel_field('caption', 'one\ntwo')

    def test_a_widget_section_does_get_nl2br(self):
        assert '<br' in _accordion_section('one\ntwo')

    def test_a_caption_still_converts_emphasis(self):
        assert '<em>' in _carousel_field('caption', '*emphasis*')


class TestASanitisedFieldStaysSanitised:
    """Restoring maths after the sanitiser must not carry markup back in.

    The caption sanitiser sees the maths as a placeholder, because an HTML
    parser handed `$$a <b$$` reads the `<` as a tag and drops the rest of
    the field. That leaves the restore as the one way markup could re-enter
    a field the sanitiser has already finished with, so what comes back is
    escaped.
    """

    @pytest.mark.parametrize('field', ['caption', 'credit'])
    @pytest.mark.parametrize('payload', [
        '$$<script>alert(1)</script>$$',
        '$$<img src=x onerror=alert(1)>$$',
    ])
    def test_markup_wrapped_in_maths_does_not_reach_the_page(self, field, payload):
        published = _carousel_field(field, payload)

        assert '<script' not in published
        assert '<img' not in published

    def test_the_sanitiser_still_strips_markup_outside_maths(self):
        published = _carousel_field('caption', '<script>alert(1)</script> $$x^2$$')

        assert '<script' not in published
        assert '$$x^2$$' in published

    def test_a_formula_containing_a_less_than_keeps_the_rest_of_the_caption(self):
        """Fed the formula rather than a placeholder, the parser ate the tail."""
        published = _carousel_field('caption', 'before $$a <b$$ after')

        assert 'after' in published
        assert '$$a &lt;b$$' in published


class TestThePageAndGlossaryBodies:
    """The two conversions in `generate_collections`, driven end to end.

    Both read from fixed relative paths and write Jekyll files, so the test
    builds a small site in a temporary directory and reads the output back.
    """

    def _site(self, tmp_path, body):
        (tmp_path / 'telar-content' / 'texts' / 'pages').mkdir(parents=True)
        (tmp_path / 'telar-content' / 'texts' / 'pages' / 'probe.md').write_text(
            '---\ntitle: Probe\n---\n\n%s\n' % body, encoding='utf-8')
        return tmp_path

    @pytest.mark.parametrize('source', EXPRESSIONS)
    def test_a_page_body_keeps_its_maths(self, tmp_path, monkeypatch, source):
        import generate_collections

        self._site(tmp_path, source)
        monkeypatch.chdir(tmp_path)
        generate_collections.generate_pages()

        published = (tmp_path / '_jekyll-files' / '_pages' / 'probe.md').read_text(
            encoding='utf-8')

        assert source in published, published

    @pytest.mark.parametrize('source', EXPRESSIONS)
    def test_a_glossary_definition_keeps_its_maths(self, tmp_path, monkeypatch,
                                                   source):
        import generate_collections

        glossary = tmp_path / 'telar-content' / 'texts' / 'glossary'
        glossary.mkdir(parents=True)
        (glossary / 'probe.md').write_text(
            '---\nterm_id: probe\ntitle: Probe\n---\n\n%s\n' % source,
            encoding='utf-8')
        monkeypatch.chdir(tmp_path)
        generate_collections.generate_glossary()

        published = (tmp_path / '_jekyll-files' / '_glossary' / 'probe.md').read_text(
            encoding='utf-8')

        assert source in published, published


class TestNothingConvertsMarkdownOnItsOwn:
    """The guard that makes the helper the default rather than a convention.

    A conversion added later without protection reintroduces the whole
    defect silently, in whichever context it was added. `latex.py` is the
    one place allowed to call the library, because it is where the
    protection lives.
    """

    def test_only_the_helper_calls_python_markdown(self):
        """Read as syntax, not as text: prose naming the library is not a call."""
        offenders = []
        for path in sorted((ROOT / 'scripts').rglob('*.py')):
            if path.name == 'latex.py':
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if (isinstance(func, ast.Attribute)
                        and func.attr == 'markdown'
                        and isinstance(func.value, ast.Name)):
                    offenders.append('%s:%d' % (path.relative_to(ROOT), node.lineno))

        assert offenders == []


class TestTheHelperItself:

    def test_text_without_maths_is_converted_unchanged(self):
        assert convert_markdown('*hello*') == '<p><em>hello</em></p>'

    def test_the_post_processing_step_sees_a_placeholder(self):
        seen = []

        convert_markdown('$$x^2$$', post_process=lambda html: seen.append(html) or html)

        assert '$$x^2$$' not in seen[0]

    def test_restore_as_text_escapes_and_the_default_does_not(self):
        source = '$$a <b$$'

        assert '<b' in convert_markdown(source)
        assert '&lt;b' in convert_markdown(source, restore_as_text=True)


# Maths written inside other maths. The patterns hold the maths out one
# delimiter kind at a time, so an expression a later pattern matches can
# already contain the placeholder an earlier one left, and that inner
# placeholder has to come back as the author's text too.
NESTED = [
    pytest.param(r'Price $x $$y$$ z$ end', id='display-in-inline'),
    pytest.param(r'Water $\ce{H2O}$ here', id='chemistry-in-inline'),
    pytest.param(r'Sum $$a $b^2$ c$$ end', id='inline-in-display'),
    pytest.param(r'Then \( a $$b^2$$ \) end', id='display-in-alternative-inline'),
    pytest.param(r'Then \[ a + \ce{H2O} \] end', id='chemistry-in-alternative-display'),
    pytest.param(r'Env \begin{aligned} $$a$$ \end{aligned} end',
                 id='display-in-environment'),
    pytest.param(r'Deep $\( a $$b^2$$ \)$ end', id='three-levels'),
    pytest.param(r'Two $\ce{A}$ and $x $$y$$ z$ end', id='two-nests-in-one-field'),
    pytest.param(r'Once $$y$$ and again $x $$y$$ z$ end',
                 id='the-inner-formula-also-standing-alone'),
]


@pytest.mark.parametrize('site', sorted(SITES), ids=sorted(SITES))
@pytest.mark.parametrize('source', NESTED)
class TestNestedMathsReachesThePageAsWritten:

    def test_no_placeholder_reaches_the_page(self, site, source):
        published = SITES[site](source)

        assert 'TLATEX' not in published, published

    def test_the_published_text_is_the_authors(self, site, source):
        published = SITES[site](source)

        assert source in _as_text(published), published


class TestNestedMathsFromTheHelper:

    def test_the_issue_case_publishes_the_source(self):
        assert (convert_markdown('Price $x $$y$$ z$ end', extensions=['extra'])
                == '<p>Price $x $$y$$ z$ end</p>')

    def test_restored_as_text_the_inner_maths_is_escaped_once(self):
        published = convert_markdown(r'$\ce{A<B}$ and $x $$a<b$$ z$',
                                     restore_as_text=True)

        assert published == r'<p>$\ce{A&lt;B}$ and $x $$a&lt;b$$ z$</p>'

    def test_the_same_formula_twice_restores_both(self):
        """One placeholder stands for both, so the restore replaces all."""
        published = convert_markdown(r'$x $$y$$ z$ or $x $$y$$ z$')

        assert published == r'<p>$x $$y$$ z$ or $x $$y$$ z$</p>'
