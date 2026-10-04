"""
Unit Tests for Glossary Source Loading

This module tests how the glossary link map is read off disk, as opposed to
how the links themselves are rendered (tests/unit/test_glossary_links.py).

The loader and the glossary page generator read the same file. A spreadsheet
Telar refuses to build has to be refused on both paths, or the site publishes
with a link map built from a file the page generator rejected.

Version: v1.8.0
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.csv_utils import ColumnCollisionError, ReservedColumnError
from telar.glossary import load_glossary_from_csv


class TestACollidingGlossarySheetIsRefused:
    """The loader and the page generator read the same glossary.csv.

    `generate_collections` fails the build on a sheet whose columns collide.
    If the loader swallows the same collision and hands back an empty map,
    the two paths disagree about whether the file is usable, and which one
    the author hears from depends on which runs first.
    """

    def test_an_alias_beside_the_canonical_name_is_refused(self, tmp_path):
        csv_path = tmp_path / 'glossary.csv'
        csv_path.write_text(
            'term_id,title,protected,protegido\n'
            'encomienda,Encomienda,yes,\n',
            encoding='utf-8')

        with pytest.raises(ColumnCollisionError):
            load_glossary_from_csv(csv_path)

    def test_two_aliases_of_one_name_are_refused(self, tmp_path):
        csv_path = tmp_path / 'glossary.csv'
        csv_path.write_text(
            'term_id,title,privado,protegido\n'
            'encomienda,Encomienda,yes,\n',
            encoding='utf-8')

        with pytest.raises(ColumnCollisionError):
            load_glossary_from_csv(csv_path)

    def test_a_reserved_column_is_refused(self, tmp_path):
        csv_path = tmp_path / 'glossary.csv'
        csv_path.write_text(
            'term_id,title,_metadata\n'
            'encomienda,Encomienda,x\n',
            encoding='utf-8')

        with pytest.raises(ReservedColumnError):
            load_glossary_from_csv(csv_path)


class TestAnOrdinaryGlossarySheetStillLoads:

    def test_terms_are_mapped_to_titles(self, tmp_path):
        csv_path = tmp_path / 'glossary.csv'
        csv_path.write_text(
            'term_id,title,definition\n'
            'encomienda,Encomienda,A grant of labour.\n',
            encoding='utf-8')

        assert load_glossary_from_csv(csv_path) == {'encomienda': 'Encomienda'}

    def test_spanish_headers_are_normalised(self, tmp_path):
        csv_path = tmp_path / 'glossary.csv'
        csv_path.write_text(
            'id_termino,titulo,definicion\n'
            'encomienda,Encomienda,Una merced de trabajo.\n',
            encoding='utf-8')

        assert load_glossary_from_csv(csv_path) == {'encomienda': 'Encomienda'}


class TestAnUnreadableFileStillDegrades:
    """A missing or malformed file is not a refusal to build.

    Only the collision and the reserved name say the author has to change
    something; everything else keeps the old behaviour of warning and
    returning an empty map, so a site without a glossary still publishes.
    """

    def test_a_missing_file_returns_an_empty_map(self, tmp_path, capsys):
        result = load_glossary_from_csv(tmp_path / 'absent.csv')

        assert result == {}
        assert 'Could not load glossary.csv' in capsys.readouterr().out

    def test_a_file_without_the_required_columns_returns_an_empty_map(
            self, tmp_path, capsys):
        csv_path = tmp_path / 'glossary.csv'
        csv_path.write_text('definition\nA grant of labour.\n', encoding='utf-8')

        assert load_glossary_from_csv(csv_path) == {}
        assert 'missing required columns' in capsys.readouterr().out
