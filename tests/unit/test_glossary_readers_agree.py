"""
Every Reader of glossary.csv Takes the Same Rows

glossary.csv is read by the link map, by the page generator, by the
conversion that reads it as a story sheet, and by the upgrade's model of
what the build reads. All four take the same rows, dropping in order:
comment rows (a first cell starting with `#`), instruction columns, and a
second, bilingual header row judged with the glossary's aliases. Of those
rows, the link map and the pages then make a term of each with an id and a
title whose id does not start with `#`. A comment row has to be gone before
that judgement: judged as a possible header row, and found not to be one, it
is kept as a term, and publishes a page named after its second cell.

Version: v1.8.0
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations import v180_sheets
from telar import csv_utils
from telar.core import csv_to_json
from telar.glossary import load_glossary_from_csv, read_glossary_sheet
from telar.glossary_pages import _generate_glossary_from_csv

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'

SHEETS = {
    # A comment row whose other cells read as a header row.
    'comment-row-like-a-header': ('note,term_id,title,definition,tipo\n'
                                  '#c,term_id,title,,kind\n'
                                  ',t1,Uno,def uno,k\n'),
    # The Spanish header row, told from a term only by the glossary's alias.
    'bilingual-row-by-alias': ('term_id,title,definition,kind\n'
                               'id_termino,titulo,definicion,tipo\n'
                               't1,Uno,def uno,\n'),
    # A comment row, then the bilingual row.
    'comment-then-bilingual-row': ('term_id,title,definition\n'
                                   '# a note,,,\n'
                                   'id_termino,titulo,definicion\n'
                                   't1,Uno,def uno\n'),
    # The first column is an instruction column, and holds the comments.
    'first-column-for-comments': ('#note,term_id,title,definition\n'
                                  '# about this sheet,term_id,title,definition\n'
                                  ',t1,Uno,def uno\n'
                                  ',t2,Dos,def dos\n'),
    # An id starting with `#` outside the first column: a row all four
    # take, which the link map and the pages make no term of.
    'hash-id-in-a-later-column': ('note,term_id,title,definition\n'
                                  ',#ghost,Ghost,def\n'
                                  ',t1,Uno,def uno\n'),
    # A header cased as nobody's alias.
    'term-id-cased': ('Term_ID,Title,Definition\n'
                      't1,Uno,def uno\n'),
}


@pytest.fixture(params=sorted(SHEETS))
def sheet(request, tmp_path):
    path = tmp_path / 'glossary.csv'
    path.write_text(SHEETS[request.param], encoding='utf-8')
    return path


def _model_term_ids(path):
    model = v180_sheets.Sheet(str(path))
    kept = [label for label in model.labels if not label.startswith('#')]
    index = [label.lower() for label in kept].index('term_id')
    columns = [i for i, label in enumerate(model.labels) if not label.startswith('#')]
    rows = v180_sheets.data_rows(model, csv_utils,
                                 sheet_aliases=csv_utils.GLOSSARY_COLUMN_ALIASES)
    return [row[columns[index]] for row in rows]


def test_the_shared_reading_and_the_upgrade_model_take_the_same_rows(sheet):
    assert list(read_glossary_sheet(sheet)['term_id']) == _model_term_ids(sheet)


def test_the_story_conversion_takes_the_same_rows(sheet, tmp_path):
    out = tmp_path / 'glossary.json'
    assert csv_to_json(str(sheet), str(out),
                       sheet_aliases=csv_utils.GLOSSARY_COLUMN_ALIASES) is True
    rows = json.loads(out.read_text(encoding='utf-8'))
    shared = read_glossary_sheet(sheet)
    key = next(k for k in rows[0] if k.lower() == 'term_id')
    assert [row[key] for row in rows] == list(shared['term_id'])


def test_the_link_map_and_the_pages_hold_only_the_terms(sheet, tmp_path, monkeypatch):
    expected = {'t1', 't2'} if 't2' in sheet.read_text(encoding='utf-8') else {'t1'}
    assert set(load_glossary_from_csv(sheet)) == expected

    monkeypatch.chdir(tmp_path)
    out = tmp_path / 'pages'
    out.mkdir()
    _generate_glossary_from_csv(sheet, out, {})
    assert {page.stem for page in out.glob('*.md')} == expected


def test_the_build_reads_the_glossary_sheet_with_its_aliases(tmp_path):
    """csv_to_json.py converts every sheet but the project and objects as a
    story; the glossary sheet the glossary readers take is read with the
    glossary's aliases, so its bilingual row is judged as they judge it."""
    (tmp_path / '_config.yml').write_text('title: t\ntelar_language: en\n', encoding='utf-8')
    spreadsheets = tmp_path / 'telar-content' / 'spreadsheets'
    spreadsheets.mkdir(parents=True)
    (spreadsheets / 'glossary.csv').write_text(SHEETS['bilingual-row-by-alias'], encoding='utf-8')
    subprocess.run([sys.executable, str(SCRIPTS / 'csv_to_json.py')], cwd=tmp_path,
                   capture_output=True, text=True, timeout=120,
                   env={**os.environ, 'PYTHONPATH': str(SCRIPTS)})

    rows = json.loads((tmp_path / '_data' / 'glossary.json').read_text(encoding='utf-8'))
    assert [row.get('term_id') for row in rows if not row.get('_metadata')] == ['t1']
