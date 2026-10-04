"""
An object id is the key two sheets are matched on, so it means what was typed.

pandas reads `objects.csv` and a story's CSV separately and infers each
column's dtype from that column alone, so a site using numeric object ids
could have `1` become the float 1.0 in one sheet and the integer 1 in the
other, on the strength of a blank cell in one of them. The two sides then
spell the same key differently and a step loses the object it names — the
image simply does not appear, with the story otherwise intact.

An id is not a quantity: `007` and `7` are different objects, and an author
who types a leading zero means it. These tests pin both sides of the match to
the author's text, and pin the reference check that reports a step naming
something the site does not have — the check is what keeps a mismatch from
being silent.

Version: v1.8.0
"""

import sys
import os
import json
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import pandas as pd

import telar.config as config
from telar.core import csv_to_json
from telar.csv_utils import OBJECT_FIELDS
from telar.processors.objects.featured import _select_featured_objects
from telar.processors.stories import process_story


def _build_objects(tmp_path, csv_text):
    """Run the objects sheet through the build, as a story would find it.

    The build reads and writes relative to the working directory, so the
    caller has already moved into the site root.
    """
    (tmp_path / '_data').mkdir(exist_ok=True)
    csv = tmp_path / 'objects.csv'
    csv.write_text(csv_text, encoding='utf-8')
    out = tmp_path / '_data' / 'objects.json'
    assert csv_to_json(str(csv), str(out), _select_featured_objects,
                       canonical_fields=OBJECT_FIELDS) is True
    return json.loads(out.read_text(encoding='utf-8'))


LANGUAGES = os.path.join(os.path.dirname(__file__), '..', '..',
                         '_data', 'languages')


def _story_warnings(tmp_path, monkeypatch, objects_csv, step_object):
    """Warnings a one-step story earns for the object it names.

    The site gets the real language files, so a report reads as a reader
    would see it rather than as the key it falls back to; the language cache
    in `telar.config` is module-level, so it is cleared around the run.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / '_config.yml').write_text('telar_language: "en"\n', encoding='utf-8')
    (tmp_path / '_data').mkdir(exist_ok=True)
    shutil.copytree(LANGUAGES, tmp_path / '_data' / 'languages',
                    dirs_exist_ok=True)
    config._lang_data = None
    _build_objects(tmp_path, objects_csv)
    df = pd.DataFrame([{'step': '1', 'object': step_object, 'question': 'Q',
                        'answer': 'A', 'x': '0.5', 'y': '0.5', 'zoom': '1'}])
    try:
        out = process_story(df, story_name='probe')
        return [str(w.get('message', ''))
                for w in out.attrs.get('viewer_warnings', [])]
    finally:
        config._lang_data = None


class TestAnObjectIdIsReadAsTyped:

    def test_a_numeric_id_survives_a_blank_cell_in_its_column(
            self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        records = _build_objects(tmp_path,
                                 'object_id,title\n'
                                 '1,First\n'
                                 ',Untitled\n'
                                 '2,Second\n')
        ids = {r['object_id'] for r in records if not r.get('_metadata')}
        assert '1' in ids and '2' in ids
        assert '1.0' not in ids

    def test_a_leading_zero_is_not_dropped(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        records = _build_objects(tmp_path,
                                 'object_id,title\n'
                                 '007,Bond\n'
                                 '008,Other\n')
        ids = {r['object_id'] for r in records if not r.get('_metadata')}
        assert '007' in ids
        assert '7' not in ids

    def test_the_spanish_header_reads_the_same_way(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        records = _build_objects(tmp_path,
                                 'id_objeto,titulo\n'
                                 '007,Bond\n'
                                 ',Sin titulo\n')
        ids = {r['object_id'] for r in records if not r.get('_metadata')}
        assert '007' in ids


class TestAStepFindsTheObjectItNames:

    def test_a_numeric_id_matches_across_the_two_sheets(
            self, tmp_path, monkeypatch):
        warnings = _story_warnings(
            tmp_path, monkeypatch,
            'object_id,title\n1,First\n,Untitled\n2,Second\n', '1')
        assert not any('was not found' in w for w in warnings), warnings

    def test_a_leading_zero_id_matches_itself(self, tmp_path, monkeypatch):
        warnings = _story_warnings(
            tmp_path, monkeypatch, 'object_id,title\n007,Bond\n', '007')
        assert not any('was not found' in w for w in warnings), warnings

    def test_a_step_naming_something_absent_is_reported(
            self, tmp_path, monkeypatch):
        """The check that keeps a mismatch from being a silent missing image."""
        warnings = _story_warnings(
            tmp_path, monkeypatch, 'object_id,title\n007,Bond\n', '7')
        assert any('was not found' in w for w in warnings), warnings
