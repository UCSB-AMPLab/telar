"""Unit Tests for the Footnote Backlink Tooltip Speaking the Site's Language

Every footnote's return arrow carries a `title` attribute, which browsers
show on hover. Python Markdown supplies its own English default, and that
sentence was the one string in a rendered panel that never came from
`_data/languages/` — so a Spanish site showed `Jump back to footnote 1 in
the text` on every note.

The option is real but easy to conclude is not. It interpolates with `%d`,
and a format string the library cannot use is discarded without a word,
after which the English default comes back looking exactly like "this
cannot be configured". The first probe on this issue used `{}` and
reported it unconfigurable.

That silent fallback is why both languages are pinned here rather than
only the translated one: the failure mode of this feature is the
behaviour it replaced, so nothing about a broken string looks broken.

Version: v1.8.0
"""

import os
import re
import shutil
import sys

import markdown
import pytest
import yaml

ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

from telar import config
from telar.latex import convert_markdown

LANGUAGES = os.path.join(ROOT, '_data', 'languages')

SOURCE = 'Text[^a] and more[^b].\n\n[^a]: First note.\n[^b]: Second *note*.\n'

# The same notes with their definitions in the opposite order to their
# references, which is the input Telar's renumbering exists for.
REORDERED = 'Text[^b] and more[^a].\n\n[^a]: Second *note*.\n[^b]: First note.\n'

TITLES = re.compile(r'title="([^"]*)"')


def _strings(lang):
    with open(os.path.join(LANGUAGES, '%s.yml' % lang), encoding='utf-8') as f:
        return yaml.safe_load(f)


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A site root with both language files, and the language cache cleared.

    `load_language_data` caches at module level and reads `_config.yml`
    from the working directory, so a test that does not clear it reads
    whichever language the previous test happened to load.
    """
    def _make(language):
        root = tmp_path / language
        (root / '_data').mkdir(parents=True)
        shutil.copytree(LANGUAGES, root / '_data' / 'languages')
        (root / '_config.yml').write_text('telar_language: "%s"\n' % language,
                                          encoding='utf-8')
        monkeypatch.chdir(root)
        config._lang_data = None
        return root

    yield _make
    config._lang_data = None


@pytest.mark.parametrize('language', ['en', 'es'])
class TestBothLanguagesDeclareAUsableString:

    def test_the_key_exists(self, language):
        assert 'backlink_title' in _strings(language).get('footnotes', {})

    def test_it_carries_exactly_one_number_placeholder(self, language):
        """The whole failure mode, checked directly.

        `%d` once and nothing else percent-shaped: a second directive, or
        a `{}` written out of habit, and the library silently keeps its
        own English sentence.
        """
        title = _strings(language)['footnotes']['backlink_title']

        assert title.count('%d') == 1
        assert len(re.findall(r'%[^%]', title)) == 1
        assert '{' not in title

    def test_the_library_accepts_it(self, language):
        """Asked of Python Markdown rather than of the string."""
        title = _strings(language)['footnotes']['backlink_title']

        html = markdown.markdown(
            SOURCE, extensions=['footnotes'],
            extension_configs={'footnotes': {'BACKLINK_TITLE': title}})

        assert TITLES.findall(html) == [title % 1, title % 2]


class TestWhatEachSiteRenders:

    def test_a_spanish_site_gets_spanish(self, site):
        site('es')

        html = convert_markdown(SOURCE)

        assert TITLES.findall(html) == ['Volver a la nota 1',
                                        'Volver a la nota 2']

    def test_an_english_site_renders_exactly_what_it_did_before(self, site):
        """The English string is the library's own default, on purpose.

        Nothing about an English site's published HTML changes, so this
        release does not rewrite a tooltip on every existing page.
        """
        site('en')

        ours = convert_markdown(SOURCE)
        theirs = markdown.markdown(SOURCE, extensions=['extra', 'nl2br', 'smarty'])

        assert ours == theirs

    def test_the_numbers_are_right_when_the_notes_are_reordered(self, site):
        """Renumbering cannot put a wrong number in this tooltip, and the
        reason is worth writing down rather than testing around.

        An adversarial review reported that these tests pass with
        Telar's renumbering disabled, and they do. Measured: the library
        numbers each backlink by its position in the notes list, and the
        renumbering works by reordering that list. So the tooltip on the
        first note says 1 whichever order the definitions were written
        in -- the number is a property of the list, not of the pass that
        rearranges it.

        What reordering changes is which note is first, and that belongs
        to `test_footnote_reading_order.py`. Held here only so the claim
        is on the record where someone would look for it.
        """
        site('es')

        html = convert_markdown(REORDERED)

        assert TITLES.findall(html) == ['Volver a la nota 1',
                                        'Volver a la nota 2']
        assert re.findall(r'<li id="fn:([^"]+)"', html) == ['b', 'a']


class TestTheExtensionListItBuilds:

    def test_naming_it_alongside_extra_changes_nothing_else(self):
        """Measured rather than assumed: the reason this is safe to do."""
        source = (SOURCE + '\n| a | b |\n|---|---|\n| 1 | 2 |\n\n'
                  'Some *emphasis* and `code`.\n')

        assert (markdown.markdown(source, extensions=['extra', 'nl2br'])
                == markdown.markdown(source,
                                     extensions=['extra', 'nl2br', 'footnotes']))
