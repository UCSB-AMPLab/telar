"""
Unit Tests for the v1.8.0 Migration's Spreadsheet Phases

From v1.8.0 the build refuses a sheet in which two columns claim one name,
and the engine treats that refusal as a hard failure: the site stays at
1.7.0. `v180_sheets.repair_colliding_columns` runs before regeneration and
deletes the empty duplicates where the collision is benign. These tests
hold the rule shared with the Compositor's import, sheet by sheet with the
scoping the build uses, and check the repaired sheet against the 1.8.0
conversion itself rather than against a restatement of it.

`report_step_answers` writes nothing. Its tests hold that it counts with
the build's own rules: the limit exactly, the prose rules before the count,
the Spanish column name, and the rows the build does not read.

Every fixture runs against a temporary site directory.

Version: v1.8.0
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations import v180_sheets
from migrations.base import ChangeStatus
from migrations.messages import get_message
from telar.core import csv_to_json
from telar.csv_utils import (GLOSSARY_COLUMN_ALIASES, OBJECT_FIELDS,
                             normalize_column_names)


def _site(tmp_path, sheets=None, config='telar_language: "en"\n'):
    (tmp_path / '_config.yml').write_text(config, encoding='utf-8')
    directory = tmp_path / 'telar-content' / 'spreadsheets'
    directory.mkdir(parents=True)
    for name, text in (sheets or {}).items():
        (directory / name).write_bytes(text.encode('utf-8'))
    return tmp_path


def _sheet(tmp_path, name):
    return (tmp_path / 'telar-content' / 'spreadsheets' / name).read_text(encoding='utf-8')


def _header(tmp_path, name):
    return _sheet(tmp_path, name).lstrip('﻿').splitlines()[0].split(',')


def _raw(tmp_path, name):
    return (tmp_path / 'telar-content' / 'spreadsheets' / name).read_bytes()


def _converts(tmp_path, name, **scope):
    """Whether 1.8.0's conversion accepts the sheet, and what it refused."""
    refusals = []
    ok = csv_to_json(str(tmp_path / 'telar-content' / 'spreadsheets' / name),
                     str(tmp_path / 'out.json'), refusals=refusals, **scope)
    return ok, refusals


def _repair(tmp_path):
    return v180_sheets.repair_colliding_columns(str(tmp_path), 'en')


OBJECTS_EMPTY_OBJECT_TYPE = (
    'object_id,title,medium,object_type\n'
    'map-1,A map,Ink on paper,\n'
    'map-2,Another map,,\n'
    'map-3,A third map,Watercolour,\n'
)


# ---------- The benign collision is repaired ----------

class TestOneColumnHoldsValues:

    def test_the_empty_object_type_goes_and_medium_stays(self, tmp_path):
        site = _site(tmp_path, {'objects.csv': OBJECTS_EMPTY_OBJECT_TYPE})

        records = _repair(site)

        assert _header(site, 'objects.csv') == ['object_id', 'title', 'medium']
        assert [r.description for r in records] == [
            'Removed the empty column `object_type` from `objects.csv`; '
            '`medium` holds your values.']
        assert records[0].status == ChangeStatus.APPLIED
        assert records[0].severity == 'soft'

    def test_the_repaired_sheet_converts(self, tmp_path):
        site = _site(tmp_path, {'objects.csv': OBJECTS_EMPTY_OBJECT_TYPE})
        assert _converts(site, 'objects.csv', canonical_fields=OBJECT_FIELDS)[0] is False

        _repair(site)

        ok, refusals = _converts(site, 'objects.csv', canonical_fields=OBJECT_FIELDS)
        assert ok and refusals == []

    def test_the_values_survive_the_repair(self, tmp_path):
        site = _site(tmp_path, {'objects.csv': OBJECTS_EMPTY_OBJECT_TYPE})

        _repair(site)

        assert _sheet(site, 'objects.csv') == (
            'object_id,title,medium\n'
            'map-1,A map,Ink on paper\n'
            'map-2,Another map,\n'
            'map-3,A third map,Watercolour\n')

    def test_the_reverse_keeps_object_type(self, tmp_path):
        site = _site(tmp_path, {'objects.csv': (
            'object_id,title,medium,object_type\n'
            'map-1,A map,,Ink on paper\n'
            'map-2,Another map,,\n')})

        records = _repair(site)

        assert _header(site, 'objects.csv') == ['object_id', 'title', 'object_type']
        assert '`object_type` holds your values' in records[0].description
        assert _converts(site, 'objects.csv', canonical_fields=OBJECT_FIELDS)[0]


class TestNoColumnHoldsValues:

    def test_the_canonical_spelling_wins_over_file_order(self, tmp_path):
        site = _site(tmp_path, {'objects.csv': (
            'object_id,object_type,title,medium\n'
            'map-1,,A map,\n')})

        _repair(site)

        assert _header(site, 'objects.csv') == ['object_id', 'title', 'medium']

    def test_without_a_canonical_spelling_the_first_wins(self, tmp_path):
        site = _site(tmp_path, {'objects.csv': (
            'object_id,title,tipo_objeto,object_type\n'
            'map-1,A map,,\n')})

        _repair(site)

        assert _header(site, 'objects.csv') == ['object_id', 'title', 'tipo_objeto']
        assert _converts(site, 'objects.csv', canonical_fields=OBJECT_FIELDS)[0]


class TestMoreThanOneColumnHoldsValues:

    def test_nothing_is_dropped_and_the_owner_is_told(self, tmp_path):
        text = ('object_id,title,medium,object_type\n'
                'map-1,A map,Ink,Paper\n')
        site = _site(tmp_path, {'objects.csv': text})

        records = _repair(site)

        assert _sheet(site, 'objects.csv') == text
        assert len(records) == 1
        assert records[0].status == ChangeStatus.FAILED
        assert records[0].severity == 'author'
        assert '`medium`' in records[0].description
        assert '`object_type`' in records[0].description


# ---------- What is not data ----------

class TestRowsThatAreNotData:

    def test_a_value_in_a_comment_row_does_not_count(self, tmp_path):
        site = _site(tmp_path, {'objects.csv': (
            'object_id,title,medium,object_type\n'
            '# instructions,,,write the medium here\n'
            'map-1,A map,Ink,\n')})

        _repair(site)

        assert _sheet(site, 'objects.csv') == (
            'object_id,title,medium\n'
            '# instructions,,\n'
            'map-1,A map,Ink\n')

    def test_a_spanish_header_row_does_not_count(self, tmp_path):
        site = _site(tmp_path, {'objects.csv': (
            'object_id,title,medium,object_type\n'
            'id_objeto,titulo,medio,tipo_objeto\n'
            'map-1,A map,Ink,\n')})

        _repair(site)

        assert _header(site, 'objects.csv') == ['object_id', 'title', 'medium']
        assert _converts(site, 'objects.csv', canonical_fields=OBJECT_FIELDS)[0]

    def test_a_hash_column_is_never_a_candidate(self, tmp_path):
        site = _site(tmp_path, {'objects.csv': (
            'object_id,title,medium,object_type,#medium\n'
            'map-1,A map,Ink,,\n')})

        _repair(site)

        assert _header(site, 'objects.csv') == ['object_id', 'title', 'medium', '#medium']


# ---------- Each sheet with the build's scoping ----------

class TestTheScopingOfEachSheet:

    def test_privado_beside_protected_on_the_project_sheet(self, tmp_path):
        site = _site(tmp_path, {'project.csv': (
            'order,story_id,title,protected,privado\n'
            '1,my-story,My story,yes,\n')})

        _repair(site)

        assert _header(site, 'project.csv') == ['order', 'story_id', 'title', 'protected']
        assert _converts(site, 'project.csv')[1] == []

    def test_tipo_beside_kind_on_the_glossary(self, tmp_path):
        site = _site(tmp_path, {'glossary.csv': (
            'term_id,title,definition,kind,tipo\n'
            'cord,Cord,A cord,term,\n')})

        _repair(site)

        assert _header(site, 'glossary.csv') == ['term_id', 'title', 'definition', 'kind']
        frame = pd.read_csv(tmp_path / 'telar-content' / 'spreadsheets' / 'glossary.csv',
                            dtype=str, keep_default_na=False)
        normalize_column_names(frame, sheet_aliases=GLOSSARY_COLUMN_ALIASES)

    def test_privado_on_the_objects_sheet_is_not_a_collision(self, tmp_path):
        text = ('object_id,title,protected,privado\n'
                'map-1,A map,,\n')
        site = _site(tmp_path, {'objects.csv': text})

        records = _repair(site)

        assert _sheet(site, 'objects.csv') == text
        assert [r.description for r in records] == [
            get_message('en', 'v180_sheets_clean')]

    def test_note_beside_Note_on_a_story_sheet(self, tmp_path):
        site = _site(tmp_path, {'my-story.csv': (
            'step,object,question,answer,note,Note\n'
            '1,map-1,Where?,Here.,A note,\n')})

        _repair(site)

        assert _header(site, 'my-story.csv') == ['step', 'object', 'question', 'answer', 'note']
        assert _converts(site, 'my-story.csv')[1] == []

    def test_two_identical_headers_are_left_alone(self, tmp_path):
        """pandas reads a repeated header as `note.1`, so the build never
        sees these as one name and refuses nothing."""
        text = 'step,object,question,answer,note,note\n1,map-1,Where?,Here.,,\n'
        site = _site(tmp_path, {'my-story.csv': text})

        _repair(site)

        assert _sheet(site, 'my-story.csv') == text


    def test_pandas_own_suffixes_decide_what_collides(self, tmp_path):
        """pandas reads `note,note,note.1` as `note,note.2,note.1`: three
        labels, none shared, so the build refuses nothing and nothing may
        be removed."""
        text = 'step,answer,note,note,note.1\n1,Here.,,,\n'
        site = _site(tmp_path, {'my-story.csv': text})

        records = _repair(site)

        assert _sheet(site, 'my-story.csv') == text
        assert _converts(site, 'my-story.csv')[1] == []
        assert [r.description for r in records] == [get_message('en', 'v180_sheets_clean')]

    def test_a_suffixed_label_that_does_collide_is_repaired(self, tmp_path):
        """`Note` and `note.1` do not collide, but `note` and `Note` do,
        and the build refuses them."""
        site = _site(tmp_path, {'my-story.csv': 'step,answer,note,Note,note\n1,Here.,x,,\n'})
        assert _converts(site, 'my-story.csv')[1] != []

        _repair(site)

        assert _converts(site, 'my-story.csv')[1] == []

    def test_a_removal_that_relabels_a_twin_is_repaired_in_turn(self, tmp_path):
        """Removing `note` turns `note.1` into `note`, which then collides
        with `Note`; each pass removes one more empty twin, until the build
        refuses nothing."""
        site = _site(tmp_path, {'my-story.csv':
                                'step,answer,note,note,note,Note\n1,Here.,,,,y\n'})

        records = _repair(site)

        assert _sheet(site, 'my-story.csv') == 'step,answer,Note\n1,Here.,y\n'
        assert _converts(site, 'my-story.csv')[1] == []
        assert all(r.status is not ChangeStatus.FAILED for r in records)

    def test_the_records_name_the_column_the_file_keeps(self, tmp_path):
        """A column kept in one pass and removed in the next is never named
        as the one holding the values."""
        site = _site(tmp_path, {'my-story.csv':
                                'step,answer,Note,note,note\n1,Here.,,,value\n'})

        records = _repair(site)

        assert _sheet(site, 'my-story.csv') == 'step,answer,note\n1,Here.,value\n'
        assert sorted(r.description for r in records) == sorted([
            get_message('en', 'v180_column_dropped', 'Note', 'my-story.csv', 'note'),
            get_message('en', 'v180_column_dropped', 'note', 'my-story.csv', 'note'),
        ])

    def test_columns_that_are_all_empty_are_reported_as_such(self, tmp_path):
        site = _site(tmp_path, {'my-story.csv': 'step,answer,note,Note\n1,Here.,,\n'})

        records = _repair(site)

        assert _sheet(site, 'my-story.csv') == 'step,answer,note\n1,Here.,\n'
        assert [r.description for r in records] == [get_message(
            'en', 'v180_column_dropped_all_empty', 'Note', 'my-story.csv', 'note', 'note')]

    def test_a_collision_a_removal_creates_is_reported_not_left_to_the_build(
            self, tmp_path):
        """After the empty `note` goes, the other `note` and `Note` both hold
        values: the upgrade says so, rather than reporting only success."""
        site = _site(tmp_path, {'my-story.csv': 'step,answer,note,note,Note\n1,Here.,,x,y\n'})

        records = _repair(site)

        assert _converts(site, 'my-story.csv')[1] != []
        failed = [r.description for r in records if r.status is ChangeStatus.FAILED]
        assert failed == [get_message('en', 'v180_columns_hold_values',
                                      'my-story.csv', '`note`, `Note`')]


# ---------- The rows the build reads survive the repair ----------

COMPOSITOR_CASE = 'note,Note,step,answer\n,#kept,1,Here.\n'


def _published(tmp_path, name):
    ok, refusals = _converts(tmp_path, name)
    assert ok and refusals == []
    import json
    records = json.loads((tmp_path / 'out.json').read_text(encoding='utf-8'))
    return [r for r in records if not r.get('_metadata')]


class TestTheRowsTheBuildReads:
    """Removing the first column moves the second cell of every row into
    first place, where the build reads a `#` as the start of a comment row,
    and can change which row it takes for a bilingual header row."""

    def test_an_empty_first_column_is_marked_rather_than_removed(self, tmp_path):
        site = _site(tmp_path, {'story1.csv': COMPOSITOR_CASE})

        records = _repair(site)

        assert _sheet(site, 'story1.csv') == '#note,Note,step,answer\n,#kept,1,Here.\n'
        assert [r.description for r in records] == [get_message(
            'en', 'v180_column_marked_note', 'note', 'story1.csv', '#note')]
        assert records[0].status == ChangeStatus.APPLIED
        steps = _published(site, 'story1.csv')
        assert [(s['step'], s['Note']) for s in steps] == [(1, '#kept')]

    def test_a_google_sheets_site_is_told_to_rename_the_column_in_the_sheet(self, tmp_path):
        site = _site(tmp_path, {'story1.csv': COMPOSITOR_CASE},
                     config='telar_language: "en"\ngoogle_sheets:\n  enabled: true\n')

        records = _repair(site)

        assert [(r.description, r.status) for r in records] == [
            (get_message('en', 'v180_column_marked_note', 'note', 'story1.csv', '#note'),
             ChangeStatus.APPLIED),
            (get_message('en', 'v180_column_marked_in_sheet', 'note', 'story1.csv', '#note'),
             ChangeStatus.FAILED),
        ]

    def test_the_marked_column_is_not_reported_as_both_empty(self, tmp_path):
        site = _site(tmp_path, {'story1.csv': COMPOSITOR_CASE})

        records = _repair(site)

        assert not any('both were empty' in r.description for r in records)

    def test_a_quoted_first_header_is_marked_byte_for_byte(self, tmp_path):
        site = _site(tmp_path, {'story1.csv':
                                '﻿"note",Note,step,answer\r\n,#kept,1,"Here, now."\r\n'})

        records = _repair(site)

        assert _raw(site, 'story1.csv') == (
            '﻿"#note",Note,step,answer\r\n,#kept,1,"Here, now."\r\n').encode('utf-8')
        assert [r.description for r in records] == [get_message(
            'en', 'v180_column_marked_note', 'note', 'story1.csv', '#note')]
        assert [s['step'] for s in _published(site, 'story1.csv')] == [1]

    def test_a_first_column_the_header_row_judgement_needs_is_not_removed(self, tmp_path):
        """The second row is a bilingual header row on five names, four of
        them known. Without the first column, or with it marked, it is
        three of four and the build would publish it as a step."""
        text = ('note,Note,step,answer,object,extra\n'
                'pregunta,,paso,respuesta,objeto,libre\n'
                ',x,1,Here.,map-1,e\n')
        site = _site(tmp_path, {'story1.csv': text})

        records = _repair(site)

        assert _sheet(site, 'story1.csv') == text
        assert [(r.description, r.status) for r in records] == [(get_message(
            'en', 'v180_column_kept_for_header_row', 'note', 'story1.csv'), ChangeStatus.FAILED)]

    def test_a_later_column_the_header_row_judgement_needs_is_not_removed(self, tmp_path):
        text = ('step,answer,object,note,Note,extra\n'
                'paso,respuesta,objeto,pregunta,,libre\n'
                '1,Here.,map-1,,x,e\n')
        site = _site(tmp_path, {'story1.csv': text})

        records = _repair(site)

        assert _sheet(site, 'story1.csv') == text
        assert [(r.description, r.status) for r in records] == [(get_message(
            'en', 'v180_column_kept_for_header_row', 'note', 'story1.csv'), ChangeStatus.FAILED)]

    def test_a_later_column_is_still_removed(self, tmp_path):
        site = _site(tmp_path, {'story1.csv': 'step,answer,note,Note\n1,Here.,,#kept\n'})

        records = _repair(site)

        assert _sheet(site, 'story1.csv') == 'step,answer,Note\n1,Here.,#kept\n'
        assert [r.description for r in records] == [get_message(
            'en', 'v180_column_dropped', 'note', 'story1.csv', 'Note')]
        assert [s['step'] for s in _published(site, 'story1.csv')] == [1]

# ---------- The file as it was written ----------

class TestTheFileKeepsItsForm:

    def test_crlf_with_bom(self, tmp_path):
        site = _site(tmp_path, {'objects.csv': (
            '﻿object_id,title,medium,object_type\r\n'
            'map-1,"A map, folded",Ink,\r\n')})

        _repair(site)

        raw = (tmp_path / 'telar-content' / 'spreadsheets' / 'objects.csv').read_bytes()
        assert raw == ('﻿object_id,title,medium\r\n'
                       'map-1,"A map, folded",Ink\r\n').encode('utf-8')
        assert _converts(site, 'objects.csv', canonical_fields=OBJECT_FIELDS)[0]

    def test_a_cell_holding_a_newline_survives(self, tmp_path):
        site = _site(tmp_path, {'my-story.csv': (
            'step,object,question,answer,note,Note\n'
            '1,map-1,Where?,"Two\nlines",,\n')})

        _repair(site)

        assert _sheet(site, 'my-story.csv') == (
            'step,object,question,answer,note\n'
            '1,map-1,Where?,"Two\nlines",\n')

    @pytest.mark.parametrize('newline', ['\r', '\r\n', '\n'], ids=['cr', 'crlf', 'lf'])
    def test_every_terminator_is_kept(self, tmp_path, newline):
        text = newline.join(['object_id,title,medium,object_type', 'm,M,Ink,', ''])
        site = _site(tmp_path, {'objects.csv': text})

        _repair(site)

        assert _raw(site, 'objects.csv') == newline.join(
            ['object_id,title,medium', 'm,M,Ink', '']).encode()

    def test_mixed_terminators_are_each_kept(self, tmp_path):
        site = _site(tmp_path, {'objects.csv': (
            'object_id,title,medium,object_type\r\nm,M,Ink,\nn,N,Oil,\rp,P,,')})

        _repair(site)

        assert _raw(site, 'objects.csv') == (
            b'object_id,title,medium\r\nm,M,Ink\nn,N,Oil\rp,P,')

    def test_surviving_fields_keep_their_bytes(self, tmp_path):
        """Quoting the author chose, spaces, and an unneeded quote all stay:
        only the dropped field and one delimiter go."""
        site = _site(tmp_path, {'objects.csv': (
            'object_id,"title",object_type,medium\n'
            '"m",  spaced  ,,"Ink ""wet"", on\npaper"\n'
            'n,"N",  ,\n')})

        _repair(site)

        assert _raw(site, 'objects.csv') == (
            b'object_id,"title",medium\n'
            b'"m",  spaced  ,"Ink ""wet"", on\npaper"\n'
            b'n,"N",\n')

    def test_the_first_column_can_go(self, tmp_path):
        site = _site(tmp_path, {'my-story.csv': 'Note,step,answer,note\n,1,Here.,x\n'})

        _repair(site)

        assert _raw(site, 'my-story.csv') == b'step,answer,note\n1,Here.,x\n'

    def test_a_short_row_and_a_blank_line(self, tmp_path):
        site = _site(tmp_path, {'objects.csv': (
            'object_id,title,medium,object_type\nm,M\n\nn,N,Ink,\n')})

        _repair(site)

        assert _raw(site, 'objects.csv') == b'object_id,title,medium\nm,M\n\nn,N,Ink\n'

    @pytest.mark.parametrize('text', [
        'object_id,title,medium,object_type\nm,"M"x,Ink,\n',
        'object_id,title,medium,object_type\nm,"M,Ink,\n',
    ], ids=['text-after-closing-quote', 'unclosed-quote'])
    def test_a_file_that_cannot_be_split_safely_is_not_written(self, tmp_path, text):
        site = _site(tmp_path, {'objects.csv': text})

        records = _repair(site)

        assert _sheet(site, 'objects.csv') == text
        assert [(r.status, r.severity) for r in records] == [(ChangeStatus.FAILED, 'author')]
        assert '`object_type`' in records[0].description
        assert 'by hand' in records[0].description

    @pytest.mark.parametrize('text', ['a,"b"c\n', 'a,"b\n', '"a"" ,b\n'])
    def test_the_splitter_refuses_what_it_cannot_split_exactly(self, text):
        assert v180_sheets.split_records(text) is None

    def test_a_split_that_reads_back_differently_is_never_written(self, tmp_path, monkeypatch):
        """The second guard: whatever the splitter returns must read as the
        cells `csv` reads, or the file is treated as one it cannot edit."""
        site = _site(tmp_path, {'objects.csv': OBJECTS_EMPTY_OBJECT_TYPE})
        split = v180_sheets.split_records
        monkeypatch.setattr(v180_sheets, 'split_records',
                            lambda text: [(f[:-1] + ['x'], e) for f, e in split(text)])

        records = _repair(site)

        assert _sheet(site, 'objects.csv') == OBJECTS_EMPTY_OBJECT_TYPE
        assert [(r.status, r.severity) for r in records] == [(ChangeStatus.FAILED, 'author')]

    def test_a_field_over_the_csv_modules_default_limit_is_read(self, tmp_path):
        """pandas reads a cell of any length; the repair must read what it
        reads, and keep the cell's bytes."""
        long_cell = 'x' * 200_000
        site = _site(tmp_path, {'objects.csv': (
            f'object_id,title,medium,object_type\nm,"{long_cell}",Ink,\n')})

        records = _repair(site)

        assert _sheet(site, 'objects.csv') == (
            f'object_id,title,medium\nm,"{long_cell}",Ink\n')
        assert [r.status for r in records] == [ChangeStatus.APPLIED]

    def test_the_process_keeps_its_own_field_limit(self, tmp_path):
        import csv
        original = csv.field_size_limit(131_072)
        try:
            site = _site(tmp_path, {'objects.csv': OBJECTS_EMPTY_OBJECT_TYPE})

            _repair(site)

            assert csv.field_size_limit() == 131_072
        finally:
            csv.field_size_limit(original)

    def test_a_long_answer_is_counted(self, tmp_path):
        answer = ' '.join(['word'] * 30_000)
        site = _site(tmp_path, {'my-story.csv': f'step,answer\n1,"{answer}"\n'})

        records = v180_sheets.report_step_answers(str(site), 'en')

        assert any('too long' in r.description for r in records)

    def test_a_symlink_inside_the_site_is_repaired(self, tmp_path):
        site = _site(tmp_path)
        real = tmp_path / 'telar-content' / 'real.csv'
        real.write_text(OBJECTS_EMPTY_OBJECT_TYPE, encoding='utf-8')
        (tmp_path / 'telar-content' / 'spreadsheets' / 'objects.csv').symlink_to(real)

        _repair(site)

        assert real.read_text(encoding='utf-8').startswith('object_id,title,medium\n')

    def test_a_symlink_out_of_the_site_is_not_written_through(self, tmp_path):
        outside = tmp_path / 'outside.csv'
        outside.write_text(OBJECTS_EMPTY_OBJECT_TYPE, encoding='utf-8')
        (tmp_path / 'site').mkdir()
        site = _site(tmp_path / 'site')
        (site / 'telar-content' / 'spreadsheets' / 'objects.csv').symlink_to(outside)

        records = _repair(site)

        assert outside.read_text(encoding='utf-8') == OBJECTS_EMPTY_OBJECT_TYPE
        assert [(r.status, r.severity) for r in records] == [(ChangeStatus.FAILED, 'author')]
        assert '`object_type`' in records[0].description

    def test_a_second_run_changes_nothing(self, tmp_path):
        site = _site(tmp_path, {'objects.csv': OBJECTS_EMPTY_OBJECT_TYPE})
        _repair(site)
        first = _sheet(site, 'objects.csv')

        records = _repair(site)

        assert _sheet(site, 'objects.csv') == first
        assert [r.description for r in records] == [
            get_message('en', 'v180_sheets_clean')]


# ---------- The lines pandas skips ----------

def _scope(site, name):
    """The `canonical_fields` the build converts *name* with, as
    `sheets_to_check` scopes it."""
    from telar import csv_utils
    scope = dict(v180_sheets.sheets_to_check(str(site), csv_utils))[name]
    return {key: value for key, value in scope.items() if key == 'canonical_fields'}


def _built(site, name):
    """The records the build publishes from *name*, which it must accept."""
    ok, refusals = _converts(site, name, **_scope(site, name))
    assert ok and refusals == []
    import json
    records = json.loads((site / 'out.json').read_text(encoding='utf-8'))
    return [r for r in records if not r.get('_metadata')]


def _rows_read(path):
    """How many rows the build's reader takes from the file at *path*."""
    from telar.csv_utils import read_sheet
    return len(read_sheet(str(path), dtype=str, keep_default_na=False))


class TestTheLinesPandasSkips:
    """pandas skips a line holding nothing but spaces or tabs, before the
    header and between rows alike, so the header is the first line it does
    not skip, and a line it skips is not a row."""

    @pytest.mark.parametrize('lead', ['\n', '  \t\n'], ids=['blank', 'whitespace'])
    def test_a_skipped_first_line_before_a_colliding_header(self, tmp_path, lead):
        site = _site(tmp_path, {'story1.csv': lead + 'note,Note,step\n,v,1\n'})
        assert _converts(site, 'story1.csv')[1] != []

        records = _repair(site)

        assert _sheet(site, 'story1.csv') == lead + 'Note,step\nv,1\n'
        assert [r.description for r in records] == [get_message(
            'en', 'v180_column_dropped', 'note', 'story1.csv', 'Note')]
        assert [(s['step'], s['Note']) for s in _built(site, 'story1.csv')] == [(1, 'v')]

    def test_a_bom_and_a_blank_line(self, tmp_path):
        site = _site(tmp_path, {'objects.csv':
                                '﻿\nobject_id,title,medium,object_type\nm,M,Ink,\n'})

        _repair(site)

        assert _raw(site, 'objects.csv') == (
            '﻿\nobject_id,title,medium\nm,M,Ink\n').encode('utf-8')
        assert [(o['object_id'], o['medium']) for o in _built(site, 'objects.csv')] == [
            ('m', 'Ink')]

    def test_crlf_with_skipped_lines_before_and_between_rows(self, tmp_path):
        """The first column goes, and the line of a space and a tab between
        the rows keeps its bytes rather than losing its only field."""
        site = _site(tmp_path, {'story1.csv':
                                '\r\n\r\nnote,Note,step\r\n,v,1\r\n \t\r\n,w,2\r\n'})

        _repair(site)

        assert _raw(site, 'story1.csv') == (
            b'\r\n\r\nNote,step\r\nv,1\r\n \t\r\nw,2\r\n')
        assert [(s['step'], s['Note']) for s in _built(site, 'story1.csv')] == [
            (1, 'v'), (2, 'w')]

    def test_a_removal_that_empties_a_row_is_not_made(self, tmp_path):
        """Without `paso` the row `,` is an empty line, which pandas skips:
        the build would read one row fewer, so the column stays."""
        text = 'step,paso\n1,\n,\n'
        site = _site(tmp_path, {'story1.csv': text})
        edit = tmp_path / 'edit.csv'
        edit.write_text('step\n1\n\n', encoding='utf-8')
        assert _rows_read(site / 'telar-content' / 'spreadsheets' / 'story1.csv') == 2
        assert _rows_read(edit) == 1

        records = _repair(site)

        assert _sheet(site, 'story1.csv') == text
        assert [(r.description, r.status) for r in records] == [(get_message(
            'en', 'v180_column_not_removed', 'paso', 'story1.csv'), ChangeStatus.FAILED)]

    def test_a_first_column_whose_removal_empties_a_row_is_marked(self, tmp_path):
        site = _site(tmp_path, {'story1.csv': 'paso,step\n,1\n,\n'})

        records = _repair(site)

        assert _sheet(site, 'story1.csv') == '#paso,step\n,1\n,\n'
        assert [r.description for r in records] == [get_message(
            'en', 'v180_column_marked_note', 'paso', 'story1.csv', '#paso')]
        assert len(_built(site, 'story1.csv')) == 2

    def test_a_row_wider_than_the_header_keeps_its_extra_cell(self, tmp_path):
        site = _site(tmp_path, {'story1.csv': '\nstep,answer,note,Note\n1,Here.,,x,extra\n'})

        _repair(site)

        assert _sheet(site, 'story1.csv') == '\nstep,answer,Note\n1,Here.,x,extra\n'
        assert [(s['step'], s['Note']) for s in _built(site, 'story1.csv')] == [(1, 'x')]

    def test_a_wider_first_row_in_a_repaired_sheet(self, tmp_path):
        site = _site(tmp_path, {'story1.csv': 'step,answer,note,Note\n1,Here.,,x,extra\n'})

        _repair(site)

        assert _sheet(site, 'story1.csv') == 'step,answer,Note\n1,Here.,x,extra\n'
        assert [(s['step'], s['Note']) for s in _built(site, 'story1.csv')] == [(1, 'x')]

    def test_a_row_left_as_a_quoted_empty_cell_is_still_a_row(self, tmp_path):
        """`""` is a quoted empty cell, which pandas reads as a row, not a
        blank line, so the removal leaves the rows the build reads as they
        were."""
        site = _site(tmp_path, {'story1.csv': 'step,paso\n1,\n"",\n'})

        _repair(site)

        assert _sheet(site, 'story1.csv') == 'step\n1\n""\n'
        assert len(_built(site, 'story1.csv')) == 2

    def test_a_removal_that_would_blank_the_header_is_not_made(self, tmp_path):
        """Without its second column the header is a line of one space,
        which pandas skips, and the file would have no header at all."""
        text = ' ,\t\n'
        site = _site(tmp_path, {'story1.csv': text})
        assert _converts(site, 'story1.csv')[1] != []

        records = _repair(site)

        assert _sheet(site, 'story1.csv') == text
        assert [(r.description, r.status) for r in records] == [(get_message(
            'en', 'v180_column_not_removed', '\t', 'story1.csv'), ChangeStatus.FAILED)]

    def test_a_header_pandas_does_not_read_as_the_sheets_is_never_written(
            self, tmp_path, monkeypatch):
        """The labels are pandas' own read of the whole sheet, and must be
        as many as the cells taken for the header: had the skipped lines
        been judged differently from pandas, the sheet is only reported."""
        text = '  \t\nnote,Note,step\n,v,1\n'
        site = _site(tmp_path, {'story1.csv': text})
        monkeypatch.setattr(v180_sheets, '_skipped_fields', lambda fields: False)

        records = _repair(site)

        assert _sheet(site, 'story1.csv') == text
        assert [r.status for r in records] == [ChangeStatus.FAILED]
        assert 'story1.csv' in records[0].description


# ---------- What the repair cannot do ----------

class TestReportsWithoutRepair:

    def test_a_reserved_column_is_named(self, tmp_path):
        site = _site(tmp_path, {'my-story.csv': (
            'step,object,question,answer,_metadata\n1,map-1,Where?,Here.,x\n')})

        records = _repair(site)

        assert len(records) == 1
        assert records[0].status == ChangeStatus.FAILED
        assert records[0].severity == 'author'
        assert '`my-story.csv`' in records[0].description
        assert '`_metadata`' in records[0].description

    def test_a_google_sheets_site_is_told_which_column_to_delete(self, tmp_path):
        site = _site(tmp_path, {'objects.csv': OBJECTS_EMPTY_OBJECT_TYPE},
                     config='telar_language: "en"\ngoogle_sheets:\n  enabled: true\n')

        records = _repair(site)

        assert _header(site, 'objects.csv') == ['object_id', 'title', 'medium']
        flagged = [r for r in records if r.status == ChangeStatus.FAILED]
        assert len(flagged) == 1
        assert flagged[0].severity == 'author'
        assert 'Google Sheet' in flagged[0].description
        assert '`object_type`' in flagged[0].description

    def test_a_site_without_sheets_is_not_told_to_edit_one(self, tmp_path):
        site = _site(tmp_path, {'objects.csv': OBJECTS_EMPTY_OBJECT_TYPE})

        records = _repair(site)

        assert all(r.status == ChangeStatus.APPLIED for r in records)

    def test_without_the_build_rules_one_soft_failure(self, tmp_path, monkeypatch):
        site = _site(tmp_path, {'objects.csv': OBJECTS_EMPTY_OBJECT_TYPE})
        monkeypatch.setitem(sys.modules, 'telar.csv_utils', None)

        records = _repair(site)

        assert len(records) == 1
        assert records[0].status == ChangeStatus.FAILED
        assert records[0].severity == 'soft'
        assert _sheet(site, 'objects.csv') == OBJECTS_EMPTY_OBJECT_TYPE

    def test_a_site_without_spreadsheets(self, tmp_path):
        (tmp_path / '_config.yml').write_text('telar_language: "en"\n', encoding='utf-8')

        records = _repair(tmp_path)

        assert [r.status for r in records] == [ChangeStatus.APPLIED]


# ---------- Step answers ----------

def _words(count, word='word'):
    return ' '.join([word] * count)


def _story(answer, header='step,object,question,answer'):
    return f'{header}\n1,map-1,Where?,"{answer}"\n'


def _answers(tmp_path, lang='en'):
    return v180_sheets.report_step_answers(str(tmp_path), lang)


class TestStepAnswers:

    def test_an_answer_at_the_budget_is_not_reported(self, tmp_path):
        site = _site(tmp_path, {'my-story.csv': _story(_words(191))})

        records = _answers(site)

        assert [r.description for r in records] == [get_message('en', 'v180_answers_clean')]

    def test_an_answer_over_the_budget_is(self, tmp_path):
        site = _site(tmp_path, {'my-story.csv': _story(_words(200))})

        records = _answers(site)

        assert [r.description for r in records] == [
            get_message('en', 'v180_answer_over_limit', 'my-story', '1', 5, 18)]
        assert records[0].status == ChangeStatus.APPLIED
        assert records[0].severity == 'soft'

    def test_the_flattening_is_reported_on_its_own(self, tmp_path):
        """A short bulleted answer is within the budget: the flattening of
        its list is reported, and no cut."""
        bullets = '\n'.join(f'- word{index}' for index in range(3))
        site = _site(tmp_path, {'my-story.csv': _story(bullets)})

        records = _answers(site)

        assert len(records) == 1
        assert 'marks of lists' in records[0].description
        assert 'limit' not in records[0].description

    def test_content_the_answer_cannot_show_is_reported_whatever_the_length(self, tmp_path):
        site = _site(tmp_path, {'my-story.csv': _story('Short. ![map](map.jpg)')})

        records = _answers(site)

        assert len(records) == 1
        assert 'images and media' in records[0].description

    def test_comment_rows_and_the_spanish_header_row_are_not_answers(self, tmp_path):
        site = _site(tmp_path, {'my-story.csv': (
            'step,object,question,answer\n'
            'paso,objeto,pregunta,respuesta\n'
            f'# a comment,,,"{_words(300)}"\n'
            '1,map-1,Where?,Here.\n')})

        assert [r.description for r in _answers(site)] == [
            get_message('en', 'v180_answers_clean')]

    def test_respuesta_is_the_answer(self, tmp_path):
        site = _site(tmp_path, {'mi-historia.csv': _story(
            _words(200), header='paso,objeto,pregunta,respuesta')})

        records = _answers(site)

        assert [r.description for r in records] == [
            get_message('en', 'v180_answer_over_limit', 'mi-historia', '1', 5, 18)]

    def test_the_system_sheets_are_not_stories(self, tmp_path):
        site = _site(tmp_path, {'project.csv': (
            'order,story_id,title,answer\n' f'1,s,S,"{_words(300)}"\n')})

        assert [r.description for r in _answers(site)] == [
            get_message('en', 'v180_answers_clean')]

    def test_a_google_sheets_site_is_told_the_counts_are_local(self, tmp_path):
        site = _site(tmp_path, {'my-story.csv': _story(_words(201))},
                     config='telar_language: "en"\ngoogle_sheets:\n  enabled: true\n')

        records = _answers(site)

        assert records[-1].description == get_message('en', 'v180_answers_from_local_copies')

    def test_nothing_is_written(self, tmp_path):
        text = _story(_words(250))
        site = _site(tmp_path, {'my-story.csv': text})

        _answers(site)

        assert _sheet(site, 'my-story.csv') == text

    def test_without_the_build_rules_one_soft_record(self, tmp_path, monkeypatch):
        site = _site(tmp_path, {'my-story.csv': _story(_words(250))})
        monkeypatch.setitem(sys.modules, 'telar.processors.stories', None)

        records = _answers(site)

        assert len(records) == 1
        assert records[0].severity == 'soft'
        assert 'names every answer it cuts' in records[0].description

    @pytest.mark.parametrize('count', [191, 192])
    def test_the_report_agrees_with_the_build(self, tmp_path, count):
        """The build's own rendering of the same answer: reported if and
        only if the build cuts it."""
        from telar.processors import stories
        site = _site(tmp_path, {'my-story.csv': _story(_words(count))})

        cut = stories.render_answer(_words(count)).cut

        reported = [r for r in _answers(site) if 'too long' in r.description]
        assert bool(reported) == cut
