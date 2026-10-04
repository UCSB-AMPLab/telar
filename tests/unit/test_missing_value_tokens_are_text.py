"""
A Cell Holding `NA`, `null` or `N/A` Is Text

pandas reads a list of tokens (`NA`, `N/A`, `n/a`, `NULL`, `null`, `NaN`,
`nan`, `None`, `#N/A`, `<NA>` and more) as a missing value unless told not
to. The glossary readers and the Compositor read them as text, so the
objects, project and story sheets do too: an object titled `NA` is titled
`NA` on the site as in the Compositor, and the token counts as a cell when
the build decides whether row 2 is a bilingual header row. A blank cell is
still empty.

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
from telar.processors.project import process_project_setup
from telar.processors.stories import process_story, render_answer

TOKENS = ['NA', 'N/A', 'n/a', 'NULL', 'null', 'NaN', 'nan', 'None', '#N/A', '<NA>']


@pytest.fixture
def convert(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '_config.yml').write_text('title: Test\n', encoding='utf-8')

    def run(csv_text, process, **kwargs):
        csv = tmp_path / 'sheet.csv'
        csv.write_text(csv_text, encoding='utf-8')
        out = tmp_path / 'sheet.json'
        assert csv_to_json(str(csv), str(out), process, **kwargs) is True
        written = json.loads(out.read_text(encoding='utf-8'))
        run.reports = [report.get('step') for row in written if row.get('_metadata')
                       for report in row.get('viewer_warnings', [])]
        return [r for r in written if not r.get('_metadata')]
    return run


def _objects(convert, csv_text):
    return convert(csv_text, process_objects, canonical_fields=OBJECT_FIELDS)


class TestTheObjectsSheet:

    @pytest.mark.parametrize('token', TOKENS)
    def test_a_title_is_kept_as_typed(self, convert, token):
        rows = _objects(convert, f'object_id,title,creator\nmap,"{token}",\n')

        assert rows[0]['title'] == token
        assert rows[0]['creator'] == ''

    def test_a_row_under_the_header_holding_a_token_is_data(self, convert):
        # Three of four cells are header names once the `#` column is
        # dropped: under 80%, so the row is an object, as the Compositor
        # imports it.
        rows = _objects(convert,
                        'object_id,title,creator,note,#instruction\n'
                        'id_objeto,titulo,creador,NA,description\n'
                        'map,A map,Someone,,\n')

        assert [r['object_id'] for r in rows] == ['id_objeto', 'map']

    def test_a_blank_cell_in_the_same_row_still_does_not_count(self, convert):
        rows = _objects(convert,
                        'object_id,title,creator,note,#instruction\n'
                        'id_objeto,titulo,creador,,description\n'
                        'map,A map,Someone,,\n')

        assert [r['object_id'] for r in rows] == ['map']


class TestTheProjectSheet:

    def test_a_story_titled_with_a_token_is_listed(self, convert):
        rows = convert('order,story_id,title,subtitle\n'
                       '1,first,None,N/A\n'
                       '2,second,Second,\n', process_project_setup)

        stories = rows[0]['stories']
        assert [(s['title'], s.get('subtitle')) for s in stories] == \
            [('None', 'N/A'), ('Second', None)]


class TestAStorySheet:

    def _steps(self, convert, rows):
        return convert('step,object,x,y,zoom,question,answer\n' + rows,
                       lambda df: process_story(df, story_name='sheet'))

    @pytest.mark.parametrize('token', TOKENS)
    def test_text_columns_keep_the_token(self, convert, token):
        steps = self._steps(convert, f'1,map,0.5,0.5,1,"{token}","{token}"\n')

        # The answer is published rendered, so the token reaches the renderer
        # as the text it is.
        assert (steps[0]['question'], steps[0]['answer']) == (token, render_answer(token).html)

    def test_a_blank_coordinate_still_takes_its_default(self, convert):
        steps = self._steps(convert, '1,map,,,,Q,A\n')

        assert (steps[0]['x'], steps[0]['y'], steps[0]['zoom']) == ('0.5', '0.5', '1')

    @pytest.mark.parametrize('token', ['NA', 'nan'])
    def test_a_token_coordinate_is_reported_and_kept(self, convert, token):
        steps = self._steps(convert, f'1,map,{token},0.5,1,Q,A\n')

        assert steps[0]['x'] == token
        assert convert.reports == [1]


class TestATokenInTheFirstColumn:

    def test_hash_n_a_is_a_comment_row_as_in_the_compositor(self, convert):
        # Text now, so the comment-row rule reads it: a first cell that
        # starts with `#` is an instruction, in the build and in the
        # Compositor's import alike.
        steps = convert('step,object,question,answer\n#N/A,map,Q,A\n1,map,Q,B\n',
                        lambda df: process_story(df, story_name='sheet'))

        assert [s['answer'] for s in steps] == ['<p>B</p>']
