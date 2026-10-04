"""
The `featured` flag means what the author typed, whatever else is in the column.

pandas infers a column's dtype from the whole column, so a numeric `featured`
column with a blank cell becomes float64 and `1` reaches the featured
vocabulary as "1.0", while the same `1` in a column with no blank reaches it
as "1". One object's flag therefore depended on what other rows held. These
tests pin the cell to the text the author wrote.

Version: v1.8.0
"""

import sys
import os
import json

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.core import csv_to_json
from telar.csv_utils import OBJECT_FIELDS
from telar.processors.objects.featured import _select_featured_objects


SAMPLE_CONFIG = (
    'collection_interface:\n'
    '  show_sample_on_homepage: true\n'
    '  featured_count: 4\n'
)


def _featured_ids(tmp_path, monkeypatch, csv_text):
    """The object ids the build flags for the homepage, read from the JSON."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / '_config.yml').write_text(SAMPLE_CONFIG, encoding='utf-8')
    csv = tmp_path / 'objects.csv'
    csv.write_text(csv_text, encoding='utf-8')
    out = tmp_path / 'objects.json'
    assert csv_to_json(str(csv), str(out), _select_featured_objects,
                       canonical_fields=OBJECT_FIELDS) is True
    records = json.loads(out.read_text(encoding='utf-8'))
    return {r['object_id'] for r in records
            if not r.get('_metadata') and r.get('is_featured_sample')}


class TestFeaturedFlagIsReadAsTyped:
    def test_one_marks_the_object_when_the_column_has_a_blank_cell(
            self, tmp_path, monkeypatch):
        ids = _featured_ids(tmp_path, monkeypatch,
                            'object_id,title,object_warning,featured\n'
                            'photo-1,Photo one,,1\n'
                            'photo-2,Photo two,,\n')
        assert ids == {'photo-1'}

    def test_one_marks_the_object_when_the_column_has_no_blank_cell(
            self, tmp_path, monkeypatch):
        ids = _featured_ids(tmp_path, monkeypatch,
                            'object_id,title,object_warning,featured\n'
                            'photo-1,Photo one,,1\n'
                            'photo-2,Photo two,,0\n')
        assert ids == {'photo-1'}

    def test_the_spanish_header_reads_the_same_way(self, tmp_path, monkeypatch):
        ids = _featured_ids(tmp_path, monkeypatch,
                            'object_id,title,object_warning,destacado\n'
                            'photo-1,Photo one,,1\n'
                            'photo-2,Photo two,,\n')
        assert ids == {'photo-1'}

    def test_the_word_forms_still_mark_the_object(self, tmp_path, monkeypatch):
        ids = _featured_ids(tmp_path, monkeypatch,
                            'object_id,title,object_warning,featured\n'
                            'photo-1,Photo one,,yes\n'
                            'photo-2,Photo two,,\n'
                            'photo-3,Photo three,,true\n'
                            'photo-4,Photo four,,no\n')
        assert ids == {'photo-1', 'photo-3'}

    def test_the_flag_reaches_the_json_as_the_text_it_was(
            self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / '_config.yml').write_text(SAMPLE_CONFIG, encoding='utf-8')
        csv = tmp_path / 'objects.csv'
        csv.write_text('object_id,title,object_warning,featured\n'
                       'photo-1,Photo one,,1\n'
                       'photo-2,Photo two,,\n', encoding='utf-8')
        out = tmp_path / 'objects.json'
        assert csv_to_json(str(csv), str(out), _select_featured_objects,
                           canonical_fields=OBJECT_FIELDS) is True
        records = json.loads(out.read_text(encoding='utf-8'))
        flags = {r['object_id']: r.get('featured') for r in records
                 if not r.get('_metadata')}
        assert flags['photo-1'] == '1'
