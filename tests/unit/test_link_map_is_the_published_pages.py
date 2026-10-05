"""
The Site's Link Map Is the Set of Pages the Generator Writes

A story answer links a glossary term only when a page exists for it. The
link map is built from `site_glossary_pages()`, the decision
`generate_glossary` writes its pages from, so a term the generator gives no
page (a sheet without a `definition` column, a row with no title, a `#` id)
resolves as missing instead of linking to a 404.

Version: v1.8.0
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.glossary import load_glossary_terms, process_glossary_links
from telar.glossary_pages import generate_glossary

SPREADSHEETS = 'telar-content/spreadsheets'
LEGACY = 'telar-content/texts/glossary'


def _site(tmp_path, monkeypatch, csv=None):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '_config.yml').write_text('baseurl: ""\n', encoding='utf-8')
    if csv is not None:
        (tmp_path / SPREADSHEETS).mkdir(parents=True)
        (tmp_path / SPREADSHEETS / 'glossary.csv').write_text(csv, encoding='utf-8')


def _legacy_term(tmp_path, name, front_matter):
    folder = tmp_path / LEGACY
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{name}.md').write_text(f'---\n{front_matter}\n---\n\nBody.\n',
                                       encoding='utf-8')


def _answer(term_id):
    warnings = []
    html = process_glossary_links(f'See [[{term_id}]].', load_glossary_terms(),
                                  warnings, base_url='')
    return html, warnings


def _written(tmp_path):
    return {p.stem for p in (tmp_path / '_jekyll-files/_glossary').glob('*.md')}


class TestATermWithoutAPageIsMissing:
    def test_a_sheet_without_a_definition_column_links_nothing(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch, 'term_id,title\nsite-term,Site title\n')

        html, warnings = _answer('site-term')

        assert '/glossary/site-term/' not in html
        capsys.readouterr()
        generate_glossary()
        assert not _written(tmp_path)

    def test_the_missing_column_is_reported_once_by_the_generator(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch, 'term_id,title\nsite-term,Site title\n')
        load_glossary_terms()
        load_glossary_terms()
        generate_glossary()
        out = capsys.readouterr().out
        assert out.count('glossary.csv missing required column: definition') == 1

    def test_the_loader_alone_is_silent_about_the_missing_column(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch, 'term_id,title\nsite-term,Site title\n')
        load_glossary_terms()
        assert capsys.readouterr().out == ''

    def test_the_generator_reports_it_when_the_loader_ran_after_it(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch, 'term_id,title\nsite-term,Site title\n')
        generate_glossary()
        load_glossary_terms()
        out = capsys.readouterr().out
        assert out.count('glossary.csv missing required column: definition') == 1

    def test_other_warnings_of_the_read_are_shown_by_the_loader(
            self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch,
              'term_id,title,definition,kind\nx,X,def,person\n')
        (tmp_path / '_config.yml').write_text(
            'baseurl: ""\nglossary:\n  kinds: wrong\n', encoding='utf-8')
        load_glossary_terms()
        assert 'kinds: in _config.yml is not a list' in capsys.readouterr().out

    def test_a_term_beside_a_page_shows_the_missing_marker(
            self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch,
              'term_id,title,definition\nreal,Real,def\n#hidden,Hidden,def\n')
        html, warnings = _answer('#hidden')
        assert '⚠️' in html
        assert warnings

    @pytest.mark.parametrize('row', [',Nameless,def', 'a-term,,def',
                                     '#note,Comment,def'])
    def test_a_row_the_generator_skips_is_not_linked(
            self, tmp_path, monkeypatch, row):
        _site(tmp_path, monkeypatch,
              f'term_id,title,definition\n{row}\nreal,Real,def\n')
        terms = load_glossary_terms()
        assert list(terms) == ['real']

    def test_a_row_with_an_empty_definition_has_a_page_and_a_link(
            self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch, 'term_id,title,definition\nempty,Empty,\n')
        html, _ = _answer('empty')
        generate_glossary()
        assert '/glossary/empty/' in html
        assert 'empty' in _written(tmp_path)

    def test_a_legacy_term_with_a_term_id_links(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch)
        _legacy_term(tmp_path, 'old', 'term_id: old\ntitle: Old')
        html, _ = _answer('old')
        assert '/glossary/old/' in html

    def test_a_legacy_file_without_a_term_id_does_not(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch)
        _legacy_term(tmp_path, 'other', 'term_id: other\ntitle: Other')
        _legacy_term(tmp_path, 'anon', 'title: Anon')
        html, warnings = _answer('anon')
        assert '/glossary/anon/' not in html
        assert warnings

    def test_the_kinds_map_is_filled(self, tmp_path, monkeypatch):
        _site(tmp_path, monkeypatch,
              'term_id,title,definition,kind\nt,T,def,person\n')
        terms = load_glossary_terms()
        assert 't' in terms.kinds


SHEETS = [
    'term_id,title\na,A\n',
    'term_id,title,definition\na,A,d\n,B,d\nc,,d\n#d,D,d\ne,E,\n',
    'note,term_id,title,definition\n#x,y,Y,d\n,f,F,d\n',
    'term_id,title,definition\nIIIF,IIIF,d\nSome Term,Some,d\n',
]


@pytest.mark.parametrize('csv', SHEETS)
def test_every_linked_term_is_a_page_the_generator_writes(
        csv, tmp_path, monkeypatch):
    _site(tmp_path, monkeypatch, csv)
    linked = set(load_glossary_terms())
    generate_glossary()
    assert linked == _written(tmp_path)
