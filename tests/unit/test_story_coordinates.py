"""Unit Tests for What the Build Does with a Step's Coordinates

A step's `x`, `y` and `zoom` tell the viewer how to frame the object. The
build does three things with them, and they are different acts:

- A **blank** cell expresses no intention, so it is filled with the default
  (0.5, 0.5, 1) and nothing is said.
- A **comma decimal** (`0,5`) is a number written the way a Spanish-speaking
  author writes one, so it is read as that number and nothing is said.
- **Anything else** that does not read as a finite number is reported, to the
  build log and to the story's intro panel, naming the story, the step and
  the cell, and is **left as typed**. Correcting it would make the page look
  right while the sheet stayed wrong. The viewer's own per-axis fallback
  (`stepFraming` in `iiif-plate.js`) keeps the step usable meanwhile.

`n/a`, `NA`, `null` and the other spellings pandas can read as missing are
text a build reads as typed, as the Compositor does, so they are reported
like any other value that is not a number. Only an empty cell is blank.

Version: v1.8.0
"""

import json
import os
import shutil
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar.config as config
import telar.processors.stories as stories
from telar.processors.stories import process_story

LANGUAGES = os.path.join(os.path.dirname(__file__), '..', '..',
                         '_data', 'languages')


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A site root with the real language files, in a chosen language."""
    def _make(language='en'):
        root = tmp_path / language
        (root / '_data').mkdir(parents=True)
        shutil.copytree(LANGUAGES, root / '_data' / 'languages')
        (root / '_config.yml').write_text(
            f'telar_language: "{language}"\n', encoding='utf-8')
        monkeypatch.chdir(root)
        config._lang_data = None
        return root

    yield _make
    config._lang_data = None


@pytest.fixture(autouse=True)
def no_glossary(monkeypatch):
    monkeypatch.setattr(stories, 'load_glossary_terms', lambda: {})


def _story(*coords):
    """One step per (x, y, zoom) triple, numbered from 1."""
    return pd.DataFrame([
        {'step': str(n), 'question': 'Q', 'answer': 'A', 'object': '',
         'x': x, 'y': y, 'zoom': zoom}
        for n, (x, y, zoom) in enumerate(coords, start=1)])


def _coordinate_warnings(out):
    return [w for w in out.attrs.get('viewer_warnings', [])
            if 'not a number' in w['message'] or 'no es un número' in w['message']]


class TestBlankCells:
    def test_a_blank_cell_gets_the_default_and_no_warning(self, site):
        site()
        out = process_story(_story(('', '', '')), story_name='mill')
        assert list(out.loc[0, ['x', 'y', 'zoom']]) == ['0.5', '0.5', '1']
        assert _coordinate_warnings(out) == []


class TestNumbers:
    @pytest.mark.parametrize('value', ['0.25', '1', '-0.5', ' 0.75 ', '1e-1'])
    def test_a_number_is_kept_as_typed_and_not_reported(self, site, value):
        site()
        out = process_story(_story((value, '0.5', '1')), story_name='mill')
        assert out.loc[0, 'x'] == value
        assert _coordinate_warnings(out) == []


class TestCommaDecimals:
    @pytest.mark.parametrize('typed, read', [
        ('0,5', '0.5'), ('0,25', '0.25'), ('-1,25', '-1.25'), (' 2,5 ', '2.5')])
    def test_a_comma_decimal_is_read_as_its_number(self, site, typed, read):
        site()
        out = process_story(_story((typed, typed, typed)), story_name='mill')
        assert list(out.loc[0, ['x', 'y', 'zoom']]) == [read, read, read]
        assert _coordinate_warnings(out) == []

    @pytest.mark.parametrize('value', ['0,5,1', ',5', '5,', '0,5a'])
    def test_anything_more_than_one_comma_between_digits_is_not(self, site, value):
        site()
        out = process_story(_story((value, '0.5', '1')), story_name='mill')
        assert out.loc[0, 'x'] == value
        assert len(_coordinate_warnings(out)) == 1


class TestNotANumber:
    @pytest.mark.parametrize('value', ['n/a', 'N/A', '—', 'centre', '{}',
                                       'inf', 'NaN value', '0.5abc'])
    def test_it_is_reported_and_left_as_typed(self, site, value):
        site()
        out = process_story(_story(('0.5', value, '1')), story_name='mill')
        assert out.loc[0, 'y'] == value
        [warning] = _coordinate_warnings(out)
        assert warning['step'] == '1'
        assert warning['type'] == 'panel'

    def test_the_message_names_the_story_the_step_and_the_cell(self, site, capsys):
        site()
        out = process_story(_story(('0.5', '0.5', '1'), ('0.5', '0.5', 'n/a')),
                            story_name='mill')
        [warning] = _coordinate_warnings(out)
        assert warning['step'] == '2'
        message = warning['message']
        assert '`zoom`' in message
        assert 'step 2' in message
        assert '`mill`' in message
        assert '`n/a`' in message
        assert '[WARN] ' + message in capsys.readouterr().out

    def test_each_bad_cell_is_its_own_report(self, site):
        site()
        out = process_story(_story(('left', 'top', 'far')), story_name='mill')
        assert [w['message'].split('`')[1] for w in _coordinate_warnings(out)] \
            == ['x', 'y', 'zoom']

    def test_the_value_is_escaped_before_it_reaches_the_page(self, site):
        site()
        out = process_story(_story(('<b>`x`</b>', '0.5', '1')), story_name='mill')
        [warning] = _coordinate_warnings(out)
        assert '<b>' not in warning['message']
        assert '&lt;b&gt;' in warning['message']
        assert "'x'" in warning['message']

    def test_the_spanish_message_is_used_on_a_spanish_site(self, site):
        site('es')
        out = process_story(_story(('n/a', '0.5', '1')), story_name='molino')
        [warning] = _coordinate_warnings(out)
        assert 'paso 1' in warning['message']
        assert '`molino`' in warning['message']


class TestThroughTheRealReader:
    """What a build does, which is not what `process_story` alone does.

    `csv_to_json` drops the template's `#` instruction rows and a repeated
    header row before the processor sees the frame, so their cells, which
    say things like "horizontal position 0-1", are never read as
    coordinates.
    """

    def _build(self, tmp_path, rows):
        from telar.core import csv_to_json
        csv = tmp_path / 'mill.csv'
        csv.write_text(
            'step,question,answer,object,x,y,zoom\n'
            'paso,pregunta,respuesta,objeto,x,y,zoom\n'
            '#,the question,the answer,object id,'
            'horizontal position 0-1 (0.5 = center),'
            'vertical position 0-1 (0.5 = center),(1.0 = full image)\n'
            + rows, encoding='utf-8')
        out = tmp_path / 'mill.json'
        csv_to_json(str(csv), str(out),
                    lambda df: process_story(df, story_name='mill'))
        return json.loads(out.read_text(encoding='utf-8'))

    def test_only_the_step_with_the_bad_cell_is_reported(self, site, capsys, tmp_path):
        site()
        steps = self._build(tmp_path, '1,Q,A,,0.5,0.5,1\n2,Q,A,,left,"0,5",1\n')
        printed = [l for l in capsys.readouterr().out.splitlines()
                   if 'not a number' in l]
        assert len(printed) == 1
        assert 'step 2' in printed[0] and '`x`' in printed[0]
        [step2] = [s for s in steps if s.get('step') == '2']
        assert (step2['x'], step2['y']) == ('left', '0.5')

    # pandas would read these as missing; a build reads them as the text
    # an author typed, so they are reported and left as typed.
    @pytest.mark.parametrize('value', ['n/a', 'N/A', 'NA', 'null', 'None', 'nan'])
    def test_a_spelling_pandas_can_read_as_missing_is_reported(self, site, capsys, tmp_path, value):
        site()
        steps = self._build(tmp_path, f'1,Q,A,,{value},0.5,1\n')
        printed = [l for l in capsys.readouterr().out.splitlines()
                   if 'not a number' in l]
        assert len(printed) == 1 and f'`{value}`' in printed[0]
        [step1] = [s for s in steps if s.get('step') == '1']
        assert step1['x'] == value

    def test_an_empty_cell_is_still_a_blank(self, site, capsys, tmp_path):
        site()
        steps = self._build(tmp_path, '1,Q,A,,,0.5,1\n')
        assert not [l for l in capsys.readouterr().out.splitlines()
                    if 'not a number' in l]
        [step1] = [s for s in steps if s.get('step') == '1']
        assert step1['x'] == '0.5'
