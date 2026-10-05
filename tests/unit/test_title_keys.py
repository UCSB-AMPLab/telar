"""Unit Tests for Which title_key a Page May Name

`_layouts/default.html` translates a page's browser-tab title through its
`title_key`, and reads only `navigation.<leaf>`: the nav labels, so the tab
says what the menu says. Everything else in the language file is the
framework's own, which is what lets a test say a key nothing reads is dead.

`generate_collections.check_title_keys` warns about a page naming anything
else, because the layout will ignore it and show the page's `title`.

Version: v1.8.0
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from generate_collections import check_title_keys

LAYOUT = os.path.join(os.path.dirname(__file__), '..', '..', '_layouts', 'default.html')


def _page(root, path, title_key):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    line = f'title_key: {title_key}\n' if title_key is not None else ''
    target.write_text(f'---\ntitle: A page\n{line}---\n\nBody\n', encoding='utf-8')


@pytest.mark.parametrize('path', ['index.md', 'pages/objects.md',
                                  'telar-content/texts/pages/about.md'])
def test_a_navigation_key_is_accepted_wherever_the_page_is(tmp_path, path):
    _page(tmp_path, path, 'navigation.objects')
    assert check_title_keys(tmp_path) == []


def test_a_page_without_a_title_key_says_nothing(tmp_path):
    _page(tmp_path, 'telar-content/texts/pages/about.md', None)
    assert check_title_keys(tmp_path) == []


@pytest.mark.parametrize('value', ['share.copy', 'objects.search_placeholder',
                                   'navigation', 'navigation.', 'navigation.a.b'])
def test_anything_else_is_reported_with_the_file_and_the_value(tmp_path, capsys, value):
    _page(tmp_path, 'telar-content/texts/pages/about.md', value)
    [warning] = check_title_keys(tmp_path)
    assert 'telar-content/texts/pages/about.md' in warning
    assert f"'{value}'" in warning
    assert '[WARN] ' + warning in capsys.readouterr().out


def test_the_layout_reads_only_the_navigation_section():
    layout = open(LAYOUT, encoding='utf-8').read()
    assert "{% if title_key_section == 'navigation' %}" in layout
    assert 'lang[title_key_section]' not in layout
