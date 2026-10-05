"""Unit Tests for the Page Value on a Story Step

A step can name which page of a multi-page object it shows. The value
comes from a spreadsheet cell, so it is whatever a person typed, and the
validator's job is to keep a usable number and clear anything else with a
warning rather than carry it into the JSON.

Two defects reached a real build, and a third is a property of this
function that the pipeline happened to be shielding:

  - `int(float('Infinity'))` raises `OverflowError`, a sibling of
    `ValueError` rather than a subclass, so it escaped the handler and
    stopped the build. Reported by the Compositor session;
  - a column pandas read as text, which happens the moment one typo sits
    beside real page numbers, rejected the integer on the way back in, so
    every **valid** page in that column was cleared and reported as
    invalid. A warning that fires on correct data is worse than silence;
  - clearing a bad value writes `''` into a column pandas read as
    numbers, which raises `TypeError` outside the try. `_normalise_frame`
    runs `fillna('')` before this pass and retypes any column with a
    blank in it, so the case that would otherwise reach it -- a `0` from
    someone counting pages from zero -- did not. **Measured on the old
    code through the real call order, after first reporting it as a
    build-stopper from a test that called this function alone.**

All three are one mistake: writing cell by cell into a column whose dtype
pandas chose from what it read. The column is now rebuilt in a single
assignment, which replaces the dtype instead of fighting it, so none of
them depends on what a caller did first.

These tests read their frames through `pd.read_csv`, because the dtype is
the thing under test and building a frame from a dict of Python values
chooses a different one. The class below that runs `_normalise_frame`
first is the production order; the rest hold this function on its own,
which is the contract a future caller relies on.

Version: v1.8.0
"""

import io
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.processors.stories import (
    _normalise_frame, _validate_page_column)


def _run(csv):
    """(page column after validation, warnings), read as the build reads it."""
    frame = pd.read_csv(io.StringIO(csv))
    warnings = []

    result = _validate_page_column(frame, warnings)

    pages = list(result['page']) if 'page' in result.columns else None
    return pages, warnings


class TestValuesThatSurvive:

    def test_a_whole_number_is_kept(self):
        pages, warnings = _run('step,page\n1,3\n2,5\n')

        assert pages == [3, 5] and warnings == []

    def test_a_spreadsheets_float_becomes_an_integer(self):
        """Sheets writes 3 as 3.0, which is why float() is in the
        conversion at all."""
        pages, warnings = _run('step,page\n1,3.0\n2,2\n')

        assert pages == [3, 2] and warnings == []

    def test_blank_cells_stay_blank_and_say_nothing(self):
        """Most steps have no page. Silence is the right answer."""
        pages, warnings = _run('step,page\n1,1\n2,\n3,4\n')

        assert pages == [1, '', 4] and warnings == []

    def test_a_sheet_with_no_page_column_is_left_alone(self):
        pages, warnings = _run('step,object\n1,a\n')

        assert pages is None and warnings == []


class TestValuesThatAreCleared:

    @pytest.mark.parametrize('value', ['abc', 'page 2', '0', '-1'])
    def test_an_unusable_value_is_dropped_and_reported(self, value):
        pages, warnings = _run('step,page\n1,%s\n' % value)

        assert pages == ['']
        assert len(warnings) == 1

    @pytest.mark.parametrize('value', ['Infinity', 'inf', '-inf', '1e400'])
    def test_an_infinite_value_is_dropped_rather_than_raised(self, value):
        """int(float(...)) raises OverflowError here, and OverflowError is
        not a ValueError. Uncaught, one cell took down the build."""
        pages, warnings = _run('step,page\n1,%s\n' % value)

        assert pages == ['']
        assert len(warnings) == 1


class TestTheColumnTypePandasChose:
    """The two defects that had nothing to do with the value itself."""

    def test_a_zero_beside_a_blank_is_cleared_not_raised(self):
        """Someone counting pages from zero, which is the likely way to
        get a 0 in there. The column reads as numbers, and the empty
        string used to clear the 0 cannot go into one.

        This never reached a build: the pass before this one retypes any
        column with a blank in it. Held anyway, because the shielding is
        a property of the caller and this function should not depend on
        it.
        """
        pages, warnings = _run('step,page\n1,0\n2,\n')

        assert pages == ['', '']
        assert len(warnings) == 1

    def test_one_typo_does_not_take_the_valid_pages_with_it(self):
        """A single non-numeric cell makes pandas read the column as text,
        and the integer could not be written back into it. Every good page
        in the column was cleared, each with a warning calling a perfectly
        valid number invalid."""
        pages, warnings = _run('step,page\n1,abc\n2,3\n3,7\n')

        assert pages == ['', 3, 7]
        assert len(warnings) == 1
        assert 'abc' in warnings[0]

    def test_the_dtype_this_test_depends_on_is_still_what_pandas_picks(self):
        """Guards the two above against a pandas release that infers
        differently: if the column stops being read as text, they would
        pass without exercising anything.
        """
        text = pd.read_csv(io.StringIO('step,page\n1,abc\n2,3\n'))
        numeric = pd.read_csv(io.StringIO('step,page\n1,0\n2,\n'))

        assert text['page'].dtype.kind in ('O', 'T', 'U')
        assert numeric['page'].dtype.kind == 'f'


class TestHowAStepIsNamedBack:

    def test_the_step_is_named_as_its_author_wrote_it(self):
        """A blank anywhere in the page column makes pandas read the step
        numbers as floats too, and the warning said "step 1.0"."""
        _, warnings = _run('step,page\n1,abc\n2,\n')

        assert 'step 1:' in warnings[0]
        assert '1.0' not in warnings[0]

    def test_the_value_is_quoted_as_it_was_read(self):
        """The label is normalised; the value is not. It is the author's
        own data, and showing them something they did not write is how a
        warning stops being findable in their sheet."""
        _, warnings = _run('step,page\n1,later\n')

        assert "'later'" in warnings[0]

    def test_every_bad_row_is_reported_not_only_the_first(self):
        _, warnings = _run('step,page\n1,Infinity\n2,abc\n3,4\n')

        assert len(warnings) == 2


class TestTheOrderTheBuildActuallyRunsThem:
    """`_normalise_frame` runs first and its `fillna('')` retypes any
    column with a blank in it, which is why one of these three defects
    never reached a site and two did.

    Written after reporting all three as build-stoppers from tests that
    called `_validate_page_column` alone. Measuring one path and
    describing it as the path is the error; this class is the second
    path.
    """

    def _through_the_pipeline(self, csv):
        frame = _normalise_frame(pd.read_csv(io.StringIO(csv)))
        warnings = []

        result = _validate_page_column(frame, warnings)

        return list(result['page']), warnings

    def test_a_typo_still_reaches_this_pass_as_text(self):
        """`fillna` does not retype a column that has no blank to fill,
        and a text column stays text either way. This is the one that
        cleared valid pages on a real site."""
        pages, warnings = self._through_the_pipeline(
            'step,page\n1,abc\n2,3\n')

        assert pages == ['', 3]
        assert len(warnings) == 1

    def test_an_infinite_value_still_reaches_this_pass_as_a_number(self):
        """The other one that reached a real site: no blank, so the
        column stays numeric and `int(float(...))` still overflows."""
        pages, warnings = self._through_the_pipeline(
            'step,page\n1,Infinity\n2,3\n')

        assert pages == ['', 3]
        assert len(warnings) == 1

    def test_a_blank_anywhere_retypes_the_column_before_this_pass(self):
        """The shielding itself, asserted rather than assumed."""
        frame = _normalise_frame(pd.read_csv(io.StringIO(
            'step,page\n1,0\n2,\n')))

        assert frame['page'].dtype.kind == 'O'

    def test_the_ordinary_sheet_is_unchanged_through_both_passes(self):
        pages, warnings = self._through_the_pipeline(
            'step,page\n1,1\n2,\n3,4\n')

        assert pages == [1, '', 4] and warnings == []
