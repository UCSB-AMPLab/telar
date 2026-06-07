"""
Unit Tests for Story Step Ordering

This module tests that `process_story` renders steps in the order given by
their authored `step` value rather than the spreadsheet's physical row order.
A story CSV can arrive with its rows out of sequence (for example, exported
by an external editor that does not preserve order); the build must still
present the steps in step-number order.

The ordering is deliberately failsafe: a stable sort keeps rows that share a
step value in their original order, blank or non-numeric steps fall to the end
instead of breaking the sort, and any unexpected error leaves the original row
order untouched rather than failing the build.

Version: v1.5.0
"""

import sys
import os

import pandas as pd

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.processors.stories import process_story


def _story_df(rows):
    """Build a minimal story DataFrame with the columns process_story expects."""
    base = {'question': '', 'answer': '', 'object': '', 'x': '', 'y': '', 'zoom': ''}
    return pd.DataFrame([{**base, **row} for row in rows])


class TestStoryStepOrdering:
    """process_story should order steps by their numeric `step` value."""

    def test_sorts_out_of_order_steps(self):
        """Rows out of sequence are returned in step-number order."""
        df = _story_df([{'step': '3'}, {'step': '1'}, {'step': '2'}])
        out = process_story(df)
        assert list(out['step']) == ['1', '2', '3']

    def test_double_digit_steps_sort_numerically_not_lexically(self):
        """Step 10 sorts after step 2, not between 1 and 2 (numeric, not string)."""
        df = _story_df([{'step': '10'}, {'step': '2'}, {'step': '1'}])
        out = process_story(df)
        assert list(out['step']) == ['1', '2', '10']

    def test_duplicate_steps_keep_original_order(self):
        """A stable sort preserves the relative order of rows sharing a step."""
        df = _story_df([
            {'step': '2', 'question': 'first2'},
            {'step': '1', 'question': 'one'},
            {'step': '2', 'question': 'second2'},
        ])
        out = process_story(df)
        assert list(out['step']) == ['1', '2', '2']
        assert list(out['question']) == ['one', 'first2', 'second2']

    def test_blank_and_nonnumeric_steps_fall_to_end(self):
        """Failsafe: invalid step values do not crash and sort to the end."""
        df = _story_df([
            {'step': '2', 'question': 'two'},
            {'step': '', 'question': 'blank'},
            {'step': '1', 'question': 'one'},
            {'step': 'foo', 'question': 'foo'},
        ])
        out = process_story(df)
        assert list(out['question'])[:2] == ['one', 'two']      # valid steps sorted first
        assert set(list(out['question'])[2:]) == {'blank', 'foo'}  # invalid ones at the end

    def test_missing_step_column_is_safe(self):
        """A DataFrame without a `step` column is left untouched, not errored."""
        df = pd.DataFrame([
            {'question': 'a', 'answer': '', 'object': '', 'x': '', 'y': '', 'zoom': ''},
            {'question': 'b', 'answer': '', 'object': '', 'x': '', 'y': '', 'zoom': ''},
        ])
        out = process_story(df)
        assert list(out['question']) == ['a', 'b']
