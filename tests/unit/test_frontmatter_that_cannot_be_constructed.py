"""Unit Tests for Front Matter That Parses but Cannot Become Values

YAML can parse and still fail to load. `title: 2024-13-45` is read as a
date, and there is no thirteenth month; `title: ! "yes\\n"` sends the text
through the boolean resolver, which matches and then has no value for it;
`!!float abc` hands `abc` to float(). PyYAML raises these as ValueError and
KeyError rather than YAMLError.

A panel file's front matter is read to find its title, so a loader that
caught YAMLError alone let these end the reading of the file, and the panel
was dropped from the story. Front matter that cannot be loaded is treated as
front matter that cannot be parsed: the panel is kept and its title read as
the text on the `title:` line.

Version: v1.8.0
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.markdown import _split_frontmatter, process_inline_content, read_markdown_file
from telar.pages import _parse_page_frontmatter


# The title line as typed, and the title an author expects to see.
UNCONSTRUCTIBLE_TITLES = {
    'a date with no such month': ('title: 2024-13-45', '2024-13-45'),
    'a date with no such day': ('title: 2024-02-30', '2024-02-30'),
    'a year zero': ('title: 0000-01-01', '0000-01-01'),
    # The regex reading trims a closing quote, as it does for any block YAML
    # cannot parse.
    'a non-specific tag on yes': ('title: ! "yes\\n"', '! "yes\\n'),
    'a float tag on a word': ('title: !!float abc', '!!float abc'),
    'a bool tag on a word': ('title: !!bool maybe', '!!bool maybe'),
}


@pytest.fixture
def texts_dir(tmp_path, monkeypatch):
    texts = tmp_path / 'telar-content' / 'texts' / 'stories'
    texts.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return texts


@pytest.mark.parametrize('case', UNCONSTRUCTIBLE_TITLES, ids=list(UNCONSTRUCTIBLE_TITLES))
class TestAPanelWithAnUnconstructibleTitleIsKept:

    def test_the_panel_file_is_read(self, case, texts_dir, capsys):
        line, expected = UNCONSTRUCTIBLE_TITLES[case]
        (texts_dir / 'panel.md').write_text(f'---\n{line}\n---\n\nThe body.\n', encoding='utf-8')

        panel = read_markdown_file('stories/panel.md')

        assert panel is not None
        assert panel['title'] == expected
        assert 'The body.' in panel['content']
        assert 'could not be parsed as YAML' in capsys.readouterr().out

    def test_the_inline_panel_is_read(self, case):
        line, expected = UNCONSTRUCTIBLE_TITLES[case]

        panel = process_inline_content(f'---\n{line}\n---\n\nThe body.')

        assert panel['title'] == expected
        assert 'The body.' in panel['content']


class TestABlockWithoutATitleThatCannotBeLoaded:

    def test_it_is_shown_as_content_not_raised(self):
        title, body = _split_frontmatter('---\ndate: 2024-13-45\n---\nThe body.\n')

        assert title == ''
        assert 'date: 2024-13-45' in body
        assert 'The body.' in body


class TestAPageWithUnconstructibleFrontMatter:

    def test_it_is_reported_like_front_matter_that_does_not_parse(self, tmp_path, capsys):
        page = tmp_path / 'about.md'
        page.write_text('---\ntitle: About\ndate: 2024-13-45\n---\n\nText.\n', encoding='utf-8')

        assert _parse_page_frontmatter(page) is None
        assert 'Invalid YAML frontmatter' in capsys.readouterr().out
