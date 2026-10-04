"""
A Story's Reports Reach Its JSON

Every report the intro panel shows about a step travels in the story JSON's metadata row,
with the step it names. The step comes from the frame, so it has whatever
type pandas gave the column: numpy's `int64`, which `json.dump` refuses (the
story was then not written at all), or a float such as `1.0`, which the
panel prints. Each report is converted here through `csv_to_json` and read
back, with whole-number steps and with a step column pandas reads as float.

Version: v1.8.0
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.core import csv_to_json
from telar.processors.stories import process_story

HEADER = 'step,object,x,y,zoom,question,answer,layer1_button,layer1_content\n'

# One row per report path, each giving step 2 the report.
REPORTS = {
    'coordinate': '2,map,abc,0.5,1,Q,A,,\n',
    'answer over the limit': '2,map,0.5,0.5,1,Q,' + ' '.join(['word'] * 400) + ',,\n',
    'object not found': '2,missing-object,0.5,0.5,1,Q,A,,\n',
    'glossary term in the answer': '2,map,0.5,0.5,1,Q,See [[no-such-term]].,,\n',
    'glossary term in a panel': '2,map,0.5,0.5,1,Q,A,More,See [[no-such-term]] here.\n',
}


@pytest.fixture
def convert(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '_config.yml').write_text('title: Test\n', encoding='utf-8')
    data = tmp_path / '_data'
    data.mkdir()
    (data / 'objects.json').write_text(
        json.dumps([{'object_id': 'map',
                     'iiif_manifest': 'https://example.org/iiif/map/manifest.json'}]),
        encoding='utf-8')
    # A glossary with one entry: with none, glossary syntax is not read.
    sheets = tmp_path / 'telar-content' / 'spreadsheets'
    sheets.mkdir(parents=True)
    (sheets / 'glossary.csv').write_text(
        'term_id,title,definition\nloom,Loom,A frame for weaving.\n', encoding='utf-8')

    def run(rows):
        csv = tmp_path / 'story.csv'
        csv.write_text(HEADER + rows, encoding='utf-8')
        out = tmp_path / 'story.json'
        assert csv_to_json(str(csv), str(out),
                           lambda df: process_story(df, story_name='story')) is True
        return json.loads(out.read_text(encoding='utf-8'))
    return run


def _report_steps(written):
    assert written[0].get('_metadata'), 'no metadata row: nothing was reported'
    return {report['step'] for report in written[0]['viewer_warnings']}


@pytest.mark.parametrize('row', REPORTS.values(), ids=REPORTS.keys())
class TestEachReport:

    def test_whole_number_steps(self, convert, row):
        written = convert('1,map,0.5,0.5,1,Q,A,,\n' + row)

        assert _report_steps(written) == {2}

    def test_a_step_column_read_as_float(self, convert, row):
        # 1.5 makes the column float, so step 2 is 2.0 in the frame.
        written = convert('1.5,map,0.5,0.5,1,Q,A,,\n' + row)

        steps = _report_steps(written)
        assert steps == {2}
        assert all(type(step) is int for step in steps)


def test_a_fractional_step_is_kept(convert):
    written = convert('1,map,0.5,0.5,1,Q,A,,\n2.5,map,abc,0.5,1,Q,A,,\n')

    assert _report_steps(written) == {2.5}


@pytest.mark.parametrize('step', ['True', 'inf'])
def test_a_step_that_is_not_a_finite_number_is_written_as_text(convert, step):
    # A column of `True` is read as numpy's bool, and `inf` as a float that
    # json.dump writes as `Infinity`, which is not JSON.
    written = convert(f'{step},map,abc,0.5,1,Q,A,,\n')

    assert _report_steps(written) == {step}
    json.dumps(written[0], allow_nan=False)
