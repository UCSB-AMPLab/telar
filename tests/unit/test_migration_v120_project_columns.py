"""
Unit Tests for migrations/v110_to_v120.py — the show_sections column

A sheet may carry a second header row repeating the column names in the
other language. The column's name belongs in those header rows and nowhere
else: written into a single-header sheet's second row it lands in the first
story's cell, where the author later reads it as data.

Version: v1.8.1
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations.v110_to_v120 import Migration110to120


HEADER = 'order,title,subtitle,byline'
SPANISH_HEADER = 'orden,titulo,subtitulo,firma'
STORY = '1,The Road Campaign,Automobiles and class politics,'


def _run(tmp_path, csv_text, language='en'):
    spreadsheets = tmp_path / 'telar-content' / 'spreadsheets'
    spreadsheets.mkdir(parents=True)
    (spreadsheets / 'project.csv').write_text(csv_text + '\n', encoding='utf-8')
    (tmp_path / '_config.yml').write_text(f'telar_language: "{language}"\n', encoding='utf-8')
    migration = Migration110to120(str(tmp_path))
    migration._update_project_csv()
    return (spreadsheets / 'project.csv').read_text(encoding='utf-8').splitlines()


class TestShowSectionsColumn:
    def test_single_header_leaves_the_first_story_cell_empty(self, tmp_path):
        lines = _run(tmp_path, f'{HEADER}\n{STORY}')
        assert lines[0].endswith('show_sections')
        assert lines[1] == f'{STORY},'

    def test_bilingual_header_names_the_column_in_both_rows(self, tmp_path):
        lines = _run(tmp_path, f'{HEADER}\n{SPANISH_HEADER}\n{STORY}')
        assert lines[0].endswith('show_sections')
        assert lines[1].endswith('show_sections')
        assert lines[2] == f'{STORY},'

    def test_header_only_sheet_gains_the_column(self, tmp_path):
        lines = _run(tmp_path, HEADER)
        assert lines == [f'{HEADER},show_sections']

    def test_spanish_site_uses_the_spanish_name(self, tmp_path):
        lines = _run(tmp_path, f'{HEADER}\n{STORY}', language='es')
        assert lines[0].endswith('mostrar_secciones')
        assert lines[1] == f'{STORY},'
