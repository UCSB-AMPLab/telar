"""
The homepage sample depends on which objects a site has, not on their order.

Objects have no meaningful row order, so reordering objects.csv changes
nothing about the collection and must not change which objects the homepage
samples when none is marked `featured`.

Version: v1.8.0
"""

import sys
import os

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.processors.objects.featured import _select_featured_objects


SAMPLE_CONFIG = (
    'collection_interface:\n'
    '  show_sample_on_homepage: true\n'
    '  featured_count: 4\n'
)

IDS = [f'object-{n:02d}' for n in range(12)]


def _sample(tmp_path, monkeypatch, ids):
    """The ids flagged for the homepage; every object is valid."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / '_config.yml').write_text(SAMPLE_CONFIG, encoding='utf-8')
    df = pd.DataFrame({'object_id': ids, 'object_warning': [''] * len(ids)})
    df = _select_featured_objects(df)
    chosen = set(df.loc[df['is_featured_sample'], 'object_id'])
    assert len(chosen) == 4
    return chosen


class TestSampleIgnoresRowOrder:
    def test_reversed_rows_sample_the_same_objects(self, tmp_path, monkeypatch):
        forward = _sample(tmp_path, monkeypatch, IDS)
        assert _sample(tmp_path, monkeypatch, list(reversed(IDS))) == forward

    def test_rotated_rows_sample_the_same_objects(self, tmp_path, monkeypatch):
        forward = _sample(tmp_path, monkeypatch, IDS)
        assert _sample(tmp_path, monkeypatch, IDS[5:] + IDS[:5]) == forward

    def test_the_sample_depends_on_the_ids(self, tmp_path, monkeypatch):
        """The seed reads the ids: the same count under other ids differs."""
        renamed = [f'item-{n:02d}' for n in range(12)]
        first = _sample(tmp_path, monkeypatch, IDS)
        second = _sample(tmp_path, monkeypatch, renamed)
        assert {i.split('-')[1] for i in first} != {i.split('-')[1] for i in second}
