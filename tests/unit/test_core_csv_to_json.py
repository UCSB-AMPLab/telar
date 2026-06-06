"""
Unit tests for telar.core.csv_to_json return-value contract.

csv_to_json must return True only when it actually writes the JSON output, and
False on a skipped (missing input) or failed conversion. main() relies on this
to avoid generating the audio manifest / search index from stale objects.json.

Version: v1.5.0
"""

import sys
import os
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.core import csv_to_json


class TestCsvToJsonReturnValue:
    def test_returns_false_when_input_missing(self, tmp_path):
        out = tmp_path / 'out.json'
        assert csv_to_json(str(tmp_path / 'nope.csv'), str(out)) is False
        assert not out.exists()

    def test_returns_true_on_success(self, tmp_path):
        csv = tmp_path / 'in.csv'
        csv.write_text('object_id,title\nobj-1,Title One\n', encoding='utf-8')
        out = tmp_path / 'out.json'
        assert csv_to_json(str(csv), str(out)) is True
        assert out.exists()
        data = json.loads(out.read_text(encoding='utf-8'))
        assert any(r.get('object_id') == 'obj-1' for r in data)

    def test_returns_false_when_process_func_raises(self, tmp_path):
        csv = tmp_path / 'in.csv'
        csv.write_text('object_id,title\nobj-1,Title One\n', encoding='utf-8')
        out = tmp_path / 'out.json'

        def boom(df):
            raise ValueError('processing failed')

        assert csv_to_json(str(csv), str(out), boom) is False
