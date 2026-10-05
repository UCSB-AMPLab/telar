"""
Contract Test for the pandas Behaviour the 1.8.0 Sheet Repair Relies On

`migrations.v180_sheets` decides which columns collide, and which lines are
rows, by predicting how the build's pandas reads a sheet. Each test here
sets the repair's prediction beside what the installed pandas does with the
same bytes, read as the build reads them (`telar.csv_utils.read_sheet`), and
names the assumption in its failure message. requirements.txt bounds pandas
to the release these hold for; a newer one that changes any of them fails
here first.

Version: v1.8.0
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations.v180_sheets import Sheet, pandas_labels
from telar.csv_utils import read_sheet


def _built_labels(tmp_path, raw):
    path = tmp_path / 'sheet.csv'
    path.write_bytes(raw)
    return [str(label) for label in read_sheet(str(path)).columns]


def _predicted_labels(tmp_path, raw):
    path = tmp_path / 'sheet.csv'
    path.write_bytes(raw)
    return Sheet(str(path)).labels


def _assumption(text, built, predicted):
    return (f'pandas assumption broken: {text}. The build reads {built}; '
            f'the 1.8.0 sheet repair predicts {predicted}. '
            f'Re-check scripts/migrations/v180_sheets.py before raising the pandas bound.')


LABEL_CASES = [
    ('a repeated header gains .1',
     'step,note,note\n1,,\n', ['step', 'note', 'note.1']),
    ('a header repeated three times gains .1 then .2',
     'note,note,note\n,,\n', ['note', 'note.1', 'note.2']),
    ('a suffix another header already holds is stepped past (.2, not .1)',
     'note,note,note.1\n,,\n', ['note', 'note.2', 'note.1']),
    ('the twin is suffixed even when the suffixed header comes first',
     'note,note.1,note\n,,\n', ['note', 'note.1', 'note.2']),
    ('a blank header cell is Unnamed: <position>',
     'step,,note\n1,,\n', ['step', 'Unnamed: 1', 'note']),
    ('labels are compared case-sensitively, so Note and note are two labels',
     'note,Note\n,\n', ['note', 'Note']),
    ('a quoted header repeated is suffixed as an unquoted one is',
     '"note",note\n,\n', ['note', 'note.1']),
]


@pytest.mark.parametrize('assumption, text, expected', LABEL_CASES,
                         ids=[case[0] for case in LABEL_CASES])
def test_repeated_headers_are_labelled_as_the_repair_predicts(
        tmp_path, assumption, text, expected):
    raw = text.encode('utf-8')
    built = _built_labels(tmp_path, raw)
    predicted = _predicted_labels(tmp_path, raw)

    assert built == expected, _assumption(assumption, built, expected)
    assert predicted == built, _assumption(assumption, built, predicted)


def test_the_header_alone_gives_the_labels_the_whole_sheet_does(tmp_path):
    """pandas_labels falls back to reading the header row alone where the
    sheet cannot be read whole; the two must agree on the labels."""
    header = ['note', 'note', 'note.1', '', 'note']
    text = 'note,note,note.1,,note\n,,,,\n'
    whole = pandas_labels(header, text)
    alone = pandas_labels(header)

    assert whole == alone, _assumption(
        'a header row read alone labels its columns as the whole sheet does',
        whole, alone)


@pytest.mark.parametrize('line, description', [
    ('', 'an empty line'),
    (' ', 'a line of one space'),
    ('   ', 'a line of several spaces'),
    ('\t', 'a line of one tab'),
    (' \t ', 'a line of spaces and tabs'),
    ('\f', 'a form feed is a cell, not a blank line'),
    ('\v', 'a vertical tab is a cell, not a blank line'),
    ('""', 'a quoted empty field is a cell'),
    ('"  "', 'a quoted field of spaces is a cell'),
    (' ,', 'two fields are a row even when both are blank'),
])
@pytest.mark.parametrize('position', ['before the header', 'between rows'])
def test_the_lines_pandas_skips_are_the_ones_the_repair_skips(
        tmp_path, line, description, position):
    if position == 'before the header':
        raw = f'{line}\na,b\n1,2\n'.encode('utf-8')
    else:
        raw = f'a,b\n1,2\n{line}\n3,4\n'.encode('utf-8')
    path = tmp_path / 'sheet.csv'
    path.write_bytes(raw)

    sheet = Sheet(str(path))
    frame = read_sheet(str(path))
    header_labels = [str(label) for label in frame.columns]

    assert header_labels[:2] == sheet.labels[:2], _assumption(
        f'{description}, {position}: which line is the header',
        header_labels, sheet.labels)
    assert len(frame) == len(sheet.body), _assumption(
        f'{description}, {position}: how many rows follow the header',
        len(frame), len(sheet.body))


def test_a_leading_bom_is_not_part_of_the_first_label(tmp_path):
    raw = '﻿note,note\n,\n'.encode('utf-8')
    built = _built_labels(tmp_path, raw)
    predicted = _predicted_labels(tmp_path, raw)

    assert built == ['note', 'note.1'], _assumption(
        'a leading BOM is stripped from the first header', built, ['note', 'note.1'])
    assert predicted == built, _assumption(
        'a leading BOM is stripped from the first header', built, predicted)


def test_a_bom_before_a_blank_line_leaves_the_blank_line_skipped(tmp_path):
    raw = '﻿\nnote,note\n,\n'.encode('utf-8')
    built = _built_labels(tmp_path, raw)
    predicted = _predicted_labels(tmp_path, raw)

    assert built == ['note', 'note.1'], _assumption(
        'a BOM alone on the first line leaves that line skipped', built, ['note', 'note.1'])
    assert predicted == built, _assumption(
        'a BOM alone on the first line leaves that line skipped', built, predicted)


def test_the_installed_pandas_is_the_one_the_requirement_names():
    """The contract above was written against pandas 3.0.x."""
    assert pd.__version__.startswith('3.0.'), (
        f'pandas {pd.__version__} is installed; the sheet repair was checked '
        f'against 3.0.x. Run this file, then move the bound in requirements.txt.')
