"""
A Story's Number Is Read from Its Own Order Cell

The order becomes the story's number, and the number is its address when it
has no `story_id` (`story-2`). pandas types the whole column: one empty cell
made it float, so every other story was numbered `2.0`, and the empty cell
itself was the text `nan`, so the placeholder row the processor means to skip
became a story. Each cell is now read on its own.

Version: v1.8.0
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.core import csv_to_json
from telar.processors.project import process_project_setup


@pytest.fixture
def stories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def run(rows):
        csv = tmp_path / 'project.csv'
        csv.write_text('order,title\n' + rows, encoding='utf-8')
        out = tmp_path / 'project.json'
        assert csv_to_json(str(csv), str(out), process_project_setup) is True
        return [(s['number'], s['title'])
                for s in json.loads(out.read_text(encoding='utf-8'))[0]['stories']]
    return run


def test_a_row_with_an_empty_order_is_skipped(stories):
    assert stories(',Placeholder\n1,First\n2,Second\n') == [('1', 'First'), ('2', 'Second')]


def test_an_empty_order_does_not_change_the_other_numbers(stories):
    assert stories('1,First\n,Placeholder\n2,Second\n') == stories('1,First\n2,Second\n')


# Columns without a blank are read as before: the number names the story's
# data file, so a site that works keeps its addresses.
# Checked against main: a column with no empty cell reads as it did.
COLUMNS = {
    'integers': ('1,First\n02,Second\n+3,Third\n', ['1', '2', '3']),
    'decimals': ('2.0,First\n1.5,Between\n1e3,Far\n', ['2.0', '1.5', '1000.0']),
    'text beside a word': ('1e3,First\n02,Second\nlast,Other\n', ['1e3', '02', 'last']),
}


@pytest.mark.parametrize('rows, numbers', COLUMNS.values(), ids=COLUMNS.keys())
def test_a_column_without_a_blank_is_read_as_before(stories, rows, numbers):
    assert [number for number, _ in stories(rows)] == numbers


@pytest.mark.parametrize('rows, numbers', COLUMNS.values(), ids=COLUMNS.keys())
def test_a_blank_row_changes_no_other_number(stories, rows, numbers):
    assert [number for number, _ in stories(',Placeholder\n' + rows)] == numbers


def test_a_long_integer_without_a_blank_keeps_every_digit(stories):
    assert stories('9007199254740993,First\n') == [('9007199254740993', 'First')]
