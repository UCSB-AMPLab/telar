"""
Unit Tests for Glossary Source Loading

This module tests how the glossary link map is read off disk, as opposed to
how the links themselves are rendered (tests/unit/test_glossary_links.py).

The link map and the glossary page generator read the same file. A spreadsheet
Telar refuses to build has to be refused on both paths, or the site publishes
with a link map built from a file the page generator rejected.

Version: v1.8.0
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.csv_utils import ColumnCollisionError, ReservedColumnError
from telar.glossary import load_glossary_terms
from telar.glossary_pages import generate_glossary


def _load(tmp_path, monkeypatch, text, name='glossary.csv'):
    """The link map of a site whose glossary sheet holds `text`."""
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / 'telar-content' / 'spreadsheets'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding='utf-8')
    return load_glossary_terms()


class TestACollidingGlossarySheetIsRefused:
    """The link map and the page generator read the same glossary.csv.

    `generate_collections` fails the build on a sheet whose columns collide.
    If the link map swallowed the same collision and handed back an empty
    map, the two paths would disagree about whether the file is usable, and
    which one the author hears from would depend on which runs first.
    """

    def test_an_alias_beside_the_canonical_name_is_refused(self, tmp_path, monkeypatch):
        with pytest.raises(ColumnCollisionError):
            _load(tmp_path, monkeypatch,
                  'term_id,title,protected,protegido\nencomienda,Encomienda,yes,\n')

    def test_two_aliases_of_one_name_are_refused(self, tmp_path, monkeypatch):
        with pytest.raises(ColumnCollisionError):
            _load(tmp_path, monkeypatch,
                  'term_id,title,privado,protegido\nencomienda,Encomienda,yes,\n')

    def test_a_reserved_column_is_refused(self, tmp_path, monkeypatch):
        with pytest.raises(ReservedColumnError):
            _load(tmp_path, monkeypatch,
                  'term_id,title,_metadata\nencomienda,Encomienda,x\n')

    def test_the_generator_refuses_the_same_sheet(self, tmp_path, monkeypatch):
        _load_ok = 'term_id,title,definition,protected,protegido\nx,X,d,yes,\n'
        monkeypatch.chdir(tmp_path)
        folder = tmp_path / 'telar-content' / 'spreadsheets'
        folder.mkdir(parents=True)
        (folder / 'glossary.csv').write_text(_load_ok, encoding='utf-8')
        with pytest.raises(ColumnCollisionError):
            generate_glossary()


class TestAnOrdinaryGlossarySheetStillLoads:

    def test_terms_are_mapped_to_titles(self, tmp_path, monkeypatch):
        terms = _load(tmp_path, monkeypatch,
                      'term_id,title,definition\nencomienda,Encomienda,A grant of labour.\n')
        assert terms == {'encomienda': 'Encomienda'}

    def test_spanish_headers_are_normalised(self, tmp_path, monkeypatch):
        terms = _load(tmp_path, monkeypatch,
                      'id_termino,titulo,definicion\nencomienda,Encomienda,Una merced de trabajo.\n')
        assert terms == {'encomienda': 'Encomienda'}

    def test_a_spanish_named_sheet_is_read(self, tmp_path, monkeypatch):
        terms = _load(tmp_path, monkeypatch,
                      'id_termino,titulo,definicion\nencomienda,Encomienda,Una merced de trabajo.\n',
                      name='glosario.csv')
        assert terms == {'encomienda': 'Encomienda'}


class TestACommentRowGetsNoLink:
    """A comment row is excluded by both readers, or by neither.

    `generate_collections` skips a row whose stripped id begins `#`, so it
    writes no page for one. A link map that kept every non-empty id turned
    a note an author left themselves into a glossary link with nothing
    behind it.

    The three spellings are the ways such a row actually arrives: typed
    plainly, typed with leading spaces, and pasted into a spreadsheet cell,
    which can carry a U+0085 in front of the text. `strip()` reduces all
    three to the same value, which is why one exclusion covers them.
    """

    NEL = '\u0085'

    @pytest.mark.parametrize("term_id,label", [
        ('#note', 'typed plainly'),
        ('   #note', 'with leading spaces'),
        (NEL + '#note', 'pasted, carrying a U+0085'),
    ])
    def test_a_comment_row_is_not_in_the_link_map(
            self, tmp_path, monkeypatch, term_id, label):
        terms = _load(tmp_path, monkeypatch,
                      'term_id,title,definition\n'
                      f'"{term_id}",Remember to keep these lower-case,\n'
                      'encomienda,Encomienda,A system of labor.\n')
        assert '#note' not in terms, label
        assert terms == {'encomienda': 'Encomienda'}

    def test_the_link_map_and_the_written_pages_agree(self, tmp_path, monkeypatch):
        """Whatever the map keeps, the generator writes a page for."""
        terms = _load(tmp_path, monkeypatch,
                      'term_id,title,definition\n'
                      '#note,Remember to keep these lower-case,\n'
                      f'"{self.NEL}#other",Another note,\n'
                      'encomienda,Encomienda,A system of labor.\n'
                      'loom,Loom,A device used to weave.\n')

        generate_glossary()

        written = {p.stem for p in (tmp_path / '_jekyll-files/_glossary').glob('*.md')}
        assert set(terms) == written == {'encomienda', 'loom'}


class TestAnUnreadableSheetDegrades:
    """A missing or unusable file is not a refusal to build.

    Only the collision and the reserved name say the author has to change
    something; everything else gives an empty map, so a site without a
    glossary still publishes.
    """

    def test_a_missing_file_returns_an_empty_map(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        assert load_glossary_terms() == {}

    def test_a_file_without_the_required_columns_returns_an_empty_map(
            self, tmp_path, monkeypatch, capsys):
        terms = _load(tmp_path, monkeypatch, 'definition\nA grant of labour.\n')

        assert terms == {}
        assert capsys.readouterr().out == ''
