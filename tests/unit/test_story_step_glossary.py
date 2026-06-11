"""
Unit Tests for Glossary Links in Story Step Text

This module tests that `process_story` resolves wiki-style [[term]] glossary
syntax in a story step's `answer` prose — not just in layer panels. Authors write
[[term]] in the main scrolling text of a step and expect it to become a clickable
glossary link, exactly as it does in layer panels. Earlier versions only processed
layer content, so brackets in the step text published literally.

Scope is the `answer` only. The `question` is the step's title/heading (rendered in
an <h2>), and inline links do not belong in a heading, so a [[term]] left in the
question is intentionally not linked. The `answer` is rendered later through Liquid's
`markdownify`, so the glossary transform runs on the raw markdown string; the injected
inline <a class="glossary-inline-link"> survives markdownify unchanged. Unknown terms
in the step text produce the same glossary build warning as unknown terms in layer
panels.

Version: v1.5.1
"""

import sys
import os

import pandas as pd

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar.processors.stories as stories
from telar.processors.stories import process_story


GLOSSARY = {
    'kcsb': 'KCSB',
    'colonial-period': 'Colonial Period',
}


def _story_df(rows):
    """Build a minimal story DataFrame with the columns process_story expects."""
    base = {'question': '', 'answer': '', 'object': '', 'x': '', 'y': '', 'zoom': ''}
    return pd.DataFrame([{**base, **row} for row in rows])


class TestStepGlossaryLinks:
    """process_story should resolve [[term]] in a step's answer prose only."""

    def test_answer_term_becomes_glossary_link(self, monkeypatch):
        """A [[term]] in the answer column becomes a glossary-inline-link."""
        monkeypatch.setattr(stories, 'load_glossary_terms', lambda: GLOSSARY)
        df = _story_df([
            {'step': '1', 'answer': 'Tune in to [[kcsb]] tonight.'},
        ])
        out = process_story(df)
        answer = out.iloc[0]['answer']
        assert 'glossary-inline-link' in answer
        assert 'data-term-id="kcsb"' in answer
        assert '[[kcsb]]' not in answer

    def test_answer_term_matches_case_insensitively(self, monkeypatch):
        """Mixed-case [[KCSB]] in the answer resolves to the canonical id."""
        monkeypatch.setattr(stories, 'load_glossary_terms', lambda: GLOSSARY)
        df = _story_df([
            {'step': '1', 'answer': 'Tune in to [[KCSB]] tonight.'},
        ])
        out = process_story(df)
        answer = out.iloc[0]['answer']
        assert 'data-term-id="kcsb"' in answer

    def test_question_term_is_left_literal(self, monkeypatch):
        """A [[term]] in the question (the step's heading) is NOT linked."""
        monkeypatch.setattr(stories, 'load_glossary_terms', lambda: GLOSSARY)
        df = _story_df([
            {'step': '1', 'question': 'What was the [[colonial-period]]?'},
        ])
        out = process_story(df)
        question = out.iloc[0]['question']
        assert 'glossary-inline-link' not in question
        assert '[[colonial-period]]' in question  # left exactly as authored

    def test_unknown_answer_term_produces_warning(self, monkeypatch):
        """An unknown [[term]] in the answer produces a glossary warning."""
        monkeypatch.setattr(stories, 'load_glossary_terms', lambda: GLOSSARY)
        df = _story_df([
            {'step': '1', 'answer': 'See [[no-such-term]] for details.'},
        ])
        out = process_story(df)
        warnings = out.attrs['viewer_warnings']
        glossary_warnings = [w for w in warnings if w.get('type') == 'glossary']
        assert len(glossary_warnings) == 1
        assert glossary_warnings[0]['term_id'] == 'no-such-term'

    def test_unknown_question_term_does_not_warn(self, monkeypatch):
        """A [[term]] in the question is not processed, so it raises no warning."""
        monkeypatch.setattr(stories, 'load_glossary_terms', lambda: GLOSSARY)
        df = _story_df([
            {'step': '1', 'question': 'About [[no-such-term]]?', 'answer': 'Plain.'},
        ])
        out = process_story(df)
        warnings = out.attrs['viewer_warnings']
        assert [w for w in warnings if w.get('type') == 'glossary'] == []

    def test_answer_without_terms_is_unchanged(self, monkeypatch):
        """Prose with no [[term]] syntax passes through untouched."""
        monkeypatch.setattr(stories, 'load_glossary_terms', lambda: GLOSSARY)
        df = _story_df([
            {'step': '1', 'question': 'A plain question', 'answer': 'A plain answer.'},
        ])
        out = process_story(df)
        assert out.iloc[0]['question'] == 'A plain question'
        assert out.iloc[0]['answer'] == 'A plain answer.'
