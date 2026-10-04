"""
A Legacy Glossary Page Is Always Published at /glossary/<slug>/

A glossary term written as its own markdown file is published at
`/glossary/<slug>/`. A `permalink` in its front matter, literal or with
placeholders, is replaced by that address and reported once in the build
output; the link map, read once per story, stays silent.

Version: v1.8.0
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.glossary import load_glossary_terms, process_glossary_links
from telar.glossary_pages import generate_glossary
from telar.widgets import reset_base_url_cache

LEGACY = 'telar-content/texts/glossary'


@pytest.fixture(autouse=True)
def _fresh_base_url():
    reset_base_url_cache()
    yield
    reset_base_url_cache()


def _legacy(tmp_path, monkeypatch, name, front_matter):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '_config.yml').write_text('baseurl: ""\n', encoding='utf-8')
    folder = tmp_path / LEGACY
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(f'---\n{front_matter}\n---\n\nBody.\n', encoding='utf-8')


def _page(tmp_path, term_id):
    return (tmp_path / f'_jekyll-files/_glossary/{term_id}.md').read_text(encoding='utf-8')


def _link(term_id, terms):
    return process_glossary_links(f'See [[{term_id}]].', terms, [])


@pytest.mark.parametrize('permalink', [
    '/other/', 'other/', '"/other/"', '/:path/:title/', '/:categories/:name/',
    '/glossary/:slug/', '/:year/:name/',
])
def test_a_permalink_is_reported_once_and_the_page_is_at_its_slug(
        tmp_path, monkeypatch, capsys, permalink):
    _legacy(tmp_path, monkeypatch, 'old.md',
            f'term_id: Old_Term\ntitle: Old\npermalink: {permalink}')

    load_glossary_terms()
    terms = generate_glossary()
    out = capsys.readouterr().out

    page = _page(tmp_path, 'Old_Term')
    assert page.count('permalink:') == 1
    assert 'permalink: /glossary/old-term/\n' in page
    assert 'data-term-url="/glossary/old-term/"' in _link('Old_Term', terms)
    assert out.count("Glossary entry 'Old_Term' (old.md): its permalink is replaced by "
                     "/glossary/old-term/, where every glossary page is published. "
                     "Remove the permalink line from the file.") == 1


def test_the_link_map_read_per_story_is_silent(tmp_path, monkeypatch, capsys):
    _legacy(tmp_path, monkeypatch, 'old.md', 'term_id: old\ntitle: Old\npermalink: /other/')
    terms = load_glossary_terms()
    assert capsys.readouterr().out == ''
    assert 'data-term-url="/glossary/old/"' in _link('old', terms)


def test_a_permalink_written_across_lines_is_replaced_whole(tmp_path, monkeypatch):
    _legacy(tmp_path, monkeypatch, 'old.md',
            'term_id: old\npermalink: >-\n  /other/\n  more/\ntitle: Old')
    generate_glossary()
    page = _page(tmp_path, 'old')
    assert page.count('permalink:') == 1
    assert 'more/' not in page
    assert 'title: Old' in page


def test_a_page_without_a_permalink_is_silent(tmp_path, monkeypatch, capsys):
    _legacy(tmp_path, monkeypatch, 'plain.md', 'term_id: plain\ntitle: Plain')
    terms = generate_glossary()
    assert 'permalink' not in capsys.readouterr().out
    assert 'permalink' not in _page(tmp_path, 'plain')
    assert 'data-term-url="/glossary/plain/"' in _link('plain', terms)
