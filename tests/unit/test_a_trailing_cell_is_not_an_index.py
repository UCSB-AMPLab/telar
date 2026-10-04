"""
A Row With One Cell More Than the Header Is Not Read Shifted

A trailing comma gives a row one cell more than the header. When the first
data row has one, pandas' default is to take the first column as the row
index, and every value moves one column left: `o1,My title,` under
`object_id,title` became an object whose id is `My title`. Every reader of
a site sheet reads the columns the header names, so a cell past the last
column is dropped instead, and one that holds a value is reported with the
sheet and row, since the author typed it and it is not published.

Version: v1.8.0
"""

import json
import os
import sys
import warnings

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.core import csv_to_json
from telar.csv_utils import OBJECT_FIELDS, read_sheet
from telar.glossary import load_glossary_terms
from telar.glossary_pages import _generate_glossary_from_csv, generate_glossary
from telar.pages import generate_pages
from telar.processors.objects import process_objects
from telar.processors.stories import process_story


def _convert(tmp_path, monkeypatch, name, text, process, **kwargs):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '_config.yml').write_text('title: Test\n', encoding='utf-8')
    csv = tmp_path / name
    csv.write_text(text, encoding='utf-8')
    out = tmp_path / 'out.json'
    assert csv_to_json(str(csv), str(out), process, **kwargs) is True
    return [r for r in json.loads(out.read_text(encoding='utf-8'))
            if not r.get('_metadata')]


def _objects(tmp_path, monkeypatch, text):
    return _convert(tmp_path, monkeypatch, 'objects.csv', text,
                    process_objects, canonical_fields=OBJECT_FIELDS)


def _glossary(tmp_path, text):
    path = tmp_path / 'glossary.csv'
    path.write_text(text, encoding='utf-8')
    return path


def _terms(tmp_path, monkeypatch, text):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / 'telar-content' / 'spreadsheets'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'glossary.csv').write_text(text, encoding='utf-8')
    return load_glossary_terms()


def _pages(tmp_path, monkeypatch, text):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / 'pages'
    out.mkdir()
    _generate_glossary_from_csv(_glossary(tmp_path, text), out, {})
    return {p.name: p.read_text(encoding='utf-8') for p in out.iterdir()}


STRAY_CELL = 'term_id,title,definition\nencomienda,Encomienda,A grant,extra\n'


def _site(tmp_path, monkeypatch, text):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '_config.yml').write_text('title: Test\n', encoding='utf-8')
    folder = tmp_path / 'telar-content' / 'spreadsheets'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'glossary.csv').write_text(text, encoding='utf-8')


GLOSSARY = ('term_id,title,definition\n'
            'encomienda,Encomienda,A grant of labour,\n'
            'cabildo,Cabildo,A town council,\n')


class TestATrailingCommaInTheFirstRow:

    def test_objects_keep_their_ids_and_titles(self, tmp_path, monkeypatch):
        rows = _objects(tmp_path, monkeypatch,
                        'object_id,title\no1,My title,\no2,Other,\n')

        assert [(r['object_id'], r['title']) for r in rows] == \
            [('o1', 'My title'), ('o2', 'Other')]

    def test_story_steps_keep_their_columns(self, tmp_path, monkeypatch):
        steps = _convert(tmp_path, monkeypatch, 'story.csv',
                         'step,object,question,answer\n'
                         '1,map,Where?,Here,\n'
                         '2,map,When?,Then,\n',
                         lambda df: process_story(df, story_name='story'))

        assert [(s['step'], s['object'], s['answer']) for s in steps] == \
            [(1, 'map', 'Here'), (2, 'map', 'Then')]

    def test_the_glossary_link_map_keys_by_term_id(self, tmp_path, monkeypatch):
        assert _terms(tmp_path, monkeypatch, GLOSSARY) == \
            {'encomienda': 'Encomienda', 'cabildo': 'Cabildo'}

    def test_the_glossary_pages_are_named_by_term_id(self, tmp_path, monkeypatch):
        pages = _pages(tmp_path, monkeypatch, GLOSSARY)

        assert sorted(pages) == ['cabildo.md', 'encomienda.md']
        assert 'title: Encomienda' in pages['encomienda.md']


class TestACellPastTheHeaderHoldingAValue:

    def test_the_objects_conversion_names_the_sheet_and_row(
            self, tmp_path, monkeypatch, capsys):
        rows = _objects(tmp_path, monkeypatch,
                        'object_id,title\no1,My title,\no2,Other,stray note\n')

        out = capsys.readouterr().out
        assert [r['object_id'] for r in rows] == ['o1', 'o2']
        assert '[WARN] objects.csv row 3' in out
        assert 'stray note' in out
        assert 'row 2' not in out

    def test_a_value_in_the_first_row_is_reported(self, tmp_path, monkeypatch, capsys):
        _objects(tmp_path, monkeypatch, 'object_id,title\no1,My title,lost\no2,Other\n')

        assert '[WARN] objects.csv row 2' in capsys.readouterr().out

    def test_the_glossary_link_map_reports_it(self, tmp_path, monkeypatch, capsys):
        _terms(tmp_path, monkeypatch,
               'term_id,title,definition\nencomienda,Encomienda,A grant,\n'
               'cabildo,Cabildo,A council,extra\n')

        assert '[WARN] glossary.csv row 3' in capsys.readouterr().out

    def test_the_glossary_pages_report_it(self, tmp_path, monkeypatch, capsys):
        _pages(tmp_path, monkeypatch,
               'term_id,title,definition\nencomienda,Encomienda,A grant,\n'
            'cabildo,Cabildo,A council,extra\n')

        assert '[WARN] glossary.csv row 3' in capsys.readouterr().out

    def test_the_link_map_reports_it_once(self, tmp_path, monkeypatch, capsys):
        _terms(tmp_path, monkeypatch, STRAY_CELL)

        assert capsys.readouterr().out.count('[WARN] glossary.csv row 2') == 1

    def test_the_generator_reports_it_once(self, tmp_path, monkeypatch, capsys):
        _site(tmp_path, monkeypatch, STRAY_CELL)

        generate_glossary()

        out = capsys.readouterr().out
        assert out.count('[WARN] glossary.csv row 2') == 1
        assert (tmp_path / '_jekyll-files' / '_glossary' / 'encomienda.md').exists()

    def test_a_build_reports_it_once(self, tmp_path, monkeypatch, capsys):
        # generate_collections.py runs the generator and then the pages in
        # one process, and hands the pages the generator's link map.
        _site(tmp_path, monkeypatch, STRAY_CELL)
        pages = tmp_path / 'telar-content' / 'texts' / 'pages'
        pages.mkdir(parents=True)
        (pages / 'about.md').write_text('---\ntitle: About\n---\n[[encomienda]]\n',
                                        encoding='utf-8')

        glossary_terms = generate_glossary()
        generate_pages(glossary_terms=glossary_terms)

        out = capsys.readouterr().out
        assert out.count('[WARN] glossary.csv row 2') == 1
        assert 'glossary-inline-link' in (
            tmp_path / '_jekyll-files' / '_pages' / 'about.md').read_text(encoding='utf-8')

    def test_pandas_does_not_report_an_empty_one_as_lost_data(self, tmp_path, monkeypatch):
        # The glossary readers keep an empty cell as text, so pandas counts a
        # trailing comma as data it dropped. The link map swallows a read
        # error, so the terms are what shows the warning was not raised.
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            terms = _terms(tmp_path, monkeypatch, GLOSSARY)

        assert terms == {'encomienda': 'Encomienda', 'cabildo': 'Cabildo'}

    def test_an_empty_trailing_cell_is_not_reported(self, tmp_path, monkeypatch, capsys):
        _objects(tmp_path, monkeypatch, 'object_id,title\no1,My title,\no2,Other,\n')

        assert '.csv row' not in capsys.readouterr().out


class TestASheetWithoutExtraCells:

    SHEET = 'object_id,title,creator\no1,My title,Someone\no2,"Other, quoted",\n'

    def test_is_read_as_before(self, tmp_path, monkeypatch, capsys):
        rows = _objects(tmp_path, monkeypatch, self.SHEET)

        assert [(r['object_id'], r['title'], r['creator']) for r in rows] == \
            [('o1', 'My title', 'Someone'), ('o2', 'Other, quoted', '')]
        assert '.csv row' not in capsys.readouterr().out

    def test_the_glossary_readers_are_unchanged(self, tmp_path, monkeypatch, capsys):
        sheet = 'term_id,title,definition\nencomienda,Encomienda,"A grant, of labour"\n'

        assert _terms(tmp_path, monkeypatch, sheet) == {'encomienda': 'Encomienda'}
        assert sorted(_pages(tmp_path, monkeypatch, sheet)) == ['encomienda.md']
        assert '.csv row' not in capsys.readouterr().out


class TestALaterRowWiderThanTheFirst:
    """pandas accepts the first data row's width and skips a wider row whole,
    or refuses the sheet where `on_bad_lines` is left at `error`. Every row
    is read to the header's width instead."""

    def test_a_story_row_with_a_trailing_comma_is_kept(self, tmp_path, monkeypatch, capsys):
        steps = _convert(tmp_path, monkeypatch, 'story.csv',
                         'step,object,question,answer\n'
                         '1,map,Where?,Here\n'
                         '2,map,When?,Then,\n',
                         lambda df: process_story(df, story_name='story'))

        assert [(s['step'], s['answer']) for s in steps] == [(1, 'Here'), (2, 'Then')]
        assert '.csv row' not in capsys.readouterr().out

    def test_a_row_with_a_value_past_the_header_is_kept_and_reported(
            self, tmp_path, monkeypatch, capsys):
        rows = _objects(tmp_path, monkeypatch,
                        'object_id,title\no1,My title\no2,Other,stray note\n')

        out = capsys.readouterr().out
        assert [(r['object_id'], r['title']) for r in rows] == \
            [('o1', 'My title'), ('o2', 'Other')]
        assert '[WARN] objects.csv row 3' in out
        assert 'stray note' in out

    SHEET = ('term_id,title,definition\n'
             'encomienda,Encomienda,A grant of labour\n'
             'cabildo,Cabildo,A town council,\n')

    def test_the_glossary_link_map_keeps_the_term(self, tmp_path, monkeypatch):
        assert _terms(tmp_path, monkeypatch, self.SHEET) == \
            {'encomienda': 'Encomienda', 'cabildo': 'Cabildo'}

    def test_the_glossary_pages_keep_the_term(self, tmp_path, monkeypatch):
        assert sorted(_pages(tmp_path, monkeypatch, self.SHEET)) == \
            ['cabildo.md', 'encomienda.md']


class TestAWhitespaceLineAboveTheHeader:
    """pandas skips a line holding only spaces or tabs and reads the next as
    the header, so the header's width is the one pandas reads."""

    CASES = {
        'space': (' \n', '\n', ''),
        'tab and a trailing comma': ('\t\n', '\n', ','),
        'byte order mark and CRLF': ('\ufeff \r\n', '\r\n', ''),
    }

    def _write(self, tmp_path, name, case, lines):
        prefix, eol, tail = self.CASES[case]
        text = prefix + lines[0] + eol + ''.join(line + tail + eol for line in lines[1:])
        path = tmp_path / name
        path.write_bytes(text.encode('utf-8'))
        return path

    @pytest.mark.parametrize('case', CASES)
    def test_the_build_reads_every_column(self, tmp_path, monkeypatch, capsys, case):
        monkeypatch.chdir(tmp_path)
        (tmp_path / '_config.yml').write_text('title: Test\n', encoding='utf-8')
        path = self._write(tmp_path, 'objects.csv', case,
                           ['object_id,title,creator', 'o1,My title,Someone'])
        out = tmp_path / 'out.json'
        assert csv_to_json(str(path), str(out), process_objects,
                           canonical_fields=OBJECT_FIELDS) is True
        rows = [r for r in json.loads(out.read_text(encoding='utf-8'))
                if not r.get('_metadata')]

        assert [(r['object_id'], r['title'], r['creator']) for r in rows] == \
            [('o1', 'My title', 'Someone')]
        assert '.csv row' not in capsys.readouterr().out

    @pytest.mark.parametrize('case', CASES)
    def test_the_build_reads_a_plain_sheet(self, tmp_path, monkeypatch, case):
        monkeypatch.chdir(tmp_path)
        path = self._write(tmp_path, 'sheet.csv', case, ['a,b,c', '1,2,3'])
        out = tmp_path / 'out.json'
        assert csv_to_json(str(path), str(out)) is True
        rows = json.loads(out.read_text(encoding='utf-8'))

        assert [{k: str(v) for k, v in r.items()} for r in rows] == \
            [{'a': '1', 'b': '2', 'c': '3'}]

    GLOSSARY = ['term_id,title,definition', 'encomienda,Encomienda,A grant of labour']

    @pytest.mark.parametrize('case', CASES)
    def test_the_glossary_link_map_reads_the_term(self, tmp_path, monkeypatch, case):
        monkeypatch.chdir(tmp_path)
        folder = tmp_path / 'telar-content' / 'spreadsheets'
        folder.mkdir(parents=True)
        self._write(folder, 'glossary.csv', case, self.GLOSSARY)

        assert load_glossary_terms() == {'encomienda': 'Encomienda'}

    @pytest.mark.parametrize('case', CASES)
    def test_the_glossary_pages_read_the_term(self, tmp_path, monkeypatch, case):
        monkeypatch.chdir(tmp_path)
        path = self._write(tmp_path, 'glossary.csv', case, self.GLOSSARY)
        out = tmp_path / 'pages'
        out.mkdir()
        _generate_glossary_from_csv(path, out, {})

        page = (out / 'encomienda.md').read_text(encoding='utf-8')
        assert 'A grant of labour' in page


class TestACommentRow:

    def test_is_not_reported(self, tmp_path, monkeypatch, capsys):
        rows = _objects(tmp_path, monkeypatch,
                        'object_id,title\n'
                        '# note, with, many, commas\n'
                        '  #indented, note, too\n'
                        'o1,My title\n')

        assert [r['object_id'] for r in rows] == ['o1']
        assert '.csv row' not in capsys.readouterr().out


class TestACellPastTheCsvFieldLimit:

    def test_a_later_wide_row_is_still_kept_and_reported(
            self, tmp_path, monkeypatch, capsys):
        # The csv module refuses a field over 131,072 characters by default;
        # pandas reads it.
        long_text = 'x' * 200_000
        rows = _objects(tmp_path, monkeypatch,
                        'object_id,title,description\n'
                        f'o1,My title,{long_text}\n'
                        'o2,Other,Short,stray note\n')

        assert [r['object_id'] for r in rows] == ['o1', 'o2']
        assert '[WARN] objects.csv row 3' in capsys.readouterr().out

    def test_a_trailing_comma_in_the_first_row_does_not_shift_it(
            self, tmp_path, monkeypatch):
        long_text = 'x' * 200_000
        rows = _objects(tmp_path, monkeypatch,
                        f'object_id,title,description\no1,My title,{long_text},\n')

        assert (rows[0]['object_id'], rows[0]['title']) == ('o1', 'My title')


class TestReadSheetArguments:
    """The width is read from the header before the sheet is, so an argument
    that moves the header or changes how a line splits would read the sheet
    against the wrong header. Those are refused rather than half-applied."""

    @pytest.mark.parametrize('argument, value', [
        ('skiprows', 1), ('header', None), ('sep', ';'), ('delimiter', ';'),
        ('quotechar', "'"), ('comment', '#'), ('usecols', [0]), ('names', ['x', 'y']),
    ])
    def test_an_argument_that_moves_the_header_is_refused(self, tmp_path, argument, value):
        path = tmp_path / 'sheet.csv'
        path.write_text('note\na,b\n1,x\n', encoding='utf-8')

        with pytest.raises(TypeError, match=rf'does not accept {argument}:'):
            read_sheet(path, **{argument: value})

    def test_the_callers_arguments_are_accepted(self, tmp_path):
        path = tmp_path / 'sheet.csv'
        path.write_text('a,b\n1,x\n', encoding='utf-8')

        df = read_sheet(path, on_bad_lines='warn', dtype=str, keep_default_na=False,
                        na_values=[''], encoding='utf-8', encoding_errors='strict')
        assert df.to_dict('records') == [{'a': '1', 'b': 'x'}]

    def test_the_report_decodes_as_pandas_does(self, tmp_path, capsys):
        path = tmp_path / 'sheet.csv'
        path.write_bytes(b'a,b\n1,\xff\n2,ok,lost\n')

        df = read_sheet(path, dtype=str, keep_default_na=False, encoding_errors='replace')

        assert df['a'].tolist() == ['1', '2']
        out = capsys.readouterr().out
        assert '[WARN] sheet.csv row 3' in out
        assert 'lost' in out
