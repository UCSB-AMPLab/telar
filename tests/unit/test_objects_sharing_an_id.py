"""
Unit Tests for Objects That Share an ID

An object ID loses an image extension at its end, so `map` and `map.jpg`
are one ID, and two rows can also be written with the same ID. The site's
readers took different rows of such a pair: the object page and the story
viewer the later, the panel's alt text and the homepage thumbnails the
earlier. The build now keeps only the last row of each ID in objects.json,
so every reader shows the same object, and it warns, naming each row.

Version: v1.8.0
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.core import csv_to_json
from telar.csv_utils import OBJECT_FIELDS
from telar.processors.objects import process_objects


@pytest.fixture
def objects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '_config.yml').write_text('title: Test\n', encoding='utf-8')

    def run(csv_text):
        csv = tmp_path / 'objects.csv'
        csv.write_text(csv_text, encoding='utf-8')
        out = tmp_path / 'objects.json'
        assert csv_to_json(str(csv), str(out), process_objects,
                           canonical_fields=OBJECT_FIELDS) is True
        return [row for row in json.loads(out.read_text(encoding='utf-8'))
                if not row.get('_metadata')]
    return run


class TestTheLastRowIsKept:

    def test_an_id_and_the_same_id_with_an_extension(self, objects):
        rows = objects('object_id,title,creator\n'
                       'map,First map,Someone\n'
                       'other,Other,\n'
                       'map.jpg,Second map,Someone else\n')

        assert [(r['object_id'], r['title'], r['creator']) for r in rows] == [
            ('other', 'Other', ''), ('map', 'Second map', 'Someone else')]

    def test_the_same_id_written_twice(self, objects):
        rows = objects('object_id,title\nmap,First map\nmap,Second map\n')

        assert [(r['object_id'], r['title']) for r in rows] == [('map', 'Second map')]

    def test_three_rows(self, objects):
        rows = objects('object_id,title\na.png,A\na,B\na.jpg,C\n')

        assert [(r['object_id'], r['title']) for r in rows] == [('a', 'C')]

    def test_ids_that_differ_are_all_kept_in_order(self, objects):
        rows = objects('object_id,title\nb,B\na.jpg,A\nc,C\n')

        assert [r['object_id'] for r in rows] == ['b', 'a', 'c']


class TestTheWarning:

    def test_names_both_rows_and_the_extension(self, objects, capsys):
        objects('object_id,title\nmap,First map\nmap.jpg,Second map\n')

        assert ("objects.csv has 2 rows with the object ID 'map': 'map' and 'map.jpg', "
                "because an image extension such as .jpg at the end of an ID is ignored. "
                "The site uses the last of them, 'map.jpg', and leaves out the other."
                in capsys.readouterr().out)

    def test_names_the_rows_by_title_where_the_ids_are_the_same(self, objects, capsys):
        objects('object_id,title\nmap,First map\nmap,Second map\n')

        assert ("objects.csv has 2 rows with the object ID 'map': 'map' (First map) and "
                "'map' (Second map). The site uses the last of them, 'map' (Second map), "
                "and leaves out the other." in capsys.readouterr().out)

    def test_says_others_for_more_than_two(self, objects, capsys):
        objects('object_id,title\na.png,A\na,B\na.jpg,C\n')

        assert "'a.png', 'a' and 'a.jpg'" in capsys.readouterr().out

    def test_none_when_every_id_differs(self, objects, capsys):
        objects('object_id,title\nmap,Map\nmap-2,Map 2\n')

        assert 'rows with the object ID' not in capsys.readouterr().out
