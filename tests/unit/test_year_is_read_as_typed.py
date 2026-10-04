"""
A year reaches the published site as the author typed it.

pandas infers a column's dtype from the whole column, so a `year` column with
a blank cell in any row becomes float64 and every year in it arrives as
"1890.0". That value is published: `generate_collections.py` writes it into
object-page front matter and into the search facets, so a blank cell in one
row corrupts the date shown for every other object.

Unlike the featured flag, nothing matches a year against a vocabulary — it is
carried through and displayed — which is why the damage is visible on the
site rather than a flag that quietly fails to take.

Version: v1.8.0
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.core import csv_to_json
from telar.csv_utils import OBJECT_FIELDS
from telar.processors.objects.featured import _select_featured_objects


def _years(tmp_path, monkeypatch, csv_text):
    """The year of each object as the build writes it into the JSON."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / '_config.yml').write_text('', encoding='utf-8')
    csv = tmp_path / 'objects.csv'
    csv.write_text(csv_text, encoding='utf-8')
    out = tmp_path / 'objects.json'
    assert csv_to_json(str(csv), str(out), _select_featured_objects,
                       canonical_fields=OBJECT_FIELDS) is True
    records = json.loads(out.read_text(encoding='utf-8'))
    return {r['object_id']: r.get('year') for r in records
            if not r.get('_metadata')}


class TestAYearIsReadAsTyped:

    def test_a_blank_cell_elsewhere_does_not_add_a_decimal(
            self, tmp_path, monkeypatch):
        years = _years(tmp_path, monkeypatch,
                       'object_id,title,year\n'
                       'atlas,Atlas,1890\n'
                       'leviathan,Leviathan,\n'
                       'figueroa,Figueroa,1651\n')
        assert years['atlas'] == '1890'
        assert years['figueroa'] == '1651'

    def test_a_column_with_no_blank_cell_reads_the_same_way(
            self, tmp_path, monkeypatch):
        years = _years(tmp_path, monkeypatch,
                       'object_id,title,year\n'
                       'atlas,Atlas,1890\n'
                       'figueroa,Figueroa,1651\n')
        assert years['atlas'] == '1890'
        assert years['figueroa'] == '1651'

    def test_the_spanish_header_reads_the_same_way(self, tmp_path, monkeypatch):
        years = _years(tmp_path, monkeypatch,
                       'id_objeto,titulo,año\n'
                       'atlas,Atlas,1890\n'
                       'leviathan,Leviathan,\n')
        assert years['atlas'] == '1890'

    def test_a_date_that_is_not_a_number_is_carried_through(
            self, tmp_path, monkeypatch):
        """Authors write circa dates and ranges; a year is not a quantity."""
        years = _years(tmp_path, monkeypatch,
                       'object_id,title,year\n'
                       'atlas,Atlas,c. 1890\n'
                       'leviathan,Leviathan,1651-1660\n'
                       'figueroa,Figueroa,\n')
        assert years['atlas'] == 'c. 1890'
        assert years['leviathan'] == '1651-1660'
