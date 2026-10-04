"""Unit Tests for a Step's Answer as the Build Publishes It

A step's `answer` is prose about the object the reader is looking at, read
on a card that does not scroll. The build renders it to HTML as a panel is
rendered (Python Markdown with `extra`, `nl2br` and `smarty`), and then,
while its maths is still held out of the HTML:

**Prose only.** Widgets, media and embeds, tables, code blocks, horizontal
rules and footnotes come out with what is inside them; headings become
paragraphs, and quotes and lists lose their containers while their words
stay, each list item a paragraph. Emphasis, links, code spans, line breaks
and `[[term]]` are prose and stay.

**The budget.** At most 18 lines and five paragraphs, counted on the
rendered answer at 53 characters a line, with two lines for each paragraph
after the first (`telar.answer_budget`). An answer over it is cut and the
build reports it, naming the story and the step. An answer of more than 15
lines is published as `answer_long`, set in the smaller type.

Length within the budget is never reported: the build speaks where it has
changed the author's words and stays quiet where it has not.

Version: v1.8.0
"""

import os
import shutil
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar.config as config
import telar.processors.stories as stories
from telar.processors.stories import process_story, render_answer

LANGUAGES = os.path.join(os.path.dirname(__file__), '..', '..',
                         '_data', 'languages')


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A site root with the real language files and a chosen language.

    Both caches in `telar.config` are module-level and read the working
    directory, so each test clears them.
    """
    def _make(language='en'):
        root = tmp_path / ('site%d' % len(list(tmp_path.iterdir())))
        (root / '_data').mkdir(parents=True)
        shutil.copytree(LANGUAGES, root / '_data' / 'languages')
        (root / '_config.yml').write_text(f'telar_language: "{language}"\n',
                                          encoding='utf-8')
        monkeypatch.chdir(root)
        config._lang_data = None
        return root

    yield _make
    config._lang_data = None


@pytest.fixture(autouse=True)
def no_glossary(monkeypatch):
    """No glossary, so `[[term]]` stays literal and the assertions are about
    the answer rather than about anchors."""
    monkeypatch.setattr(stories, 'load_glossary_terms', lambda: {})


def _story_df(rows):
    base = {'question': '', 'answer': '', 'object': '', 'x': '', 'y': '',
            'zoom': ''}
    return pd.DataFrame([{**base, **row} for row in rows])


def _words(count, start=1):
    """*count* four-letter words: 5 x count - 1 characters, so 191 of them
    are the 954 characters of 18 full lines."""
    return ' '.join('w%03d' % n for n in range(start, start + count))


def _answer_warnings(out):
    return [w for w in out.attrs['viewer_warnings'] if w['type'] == 'panel']


class TestAnAnswerRendersAsAPanelDoes:

    def test_quotes_ellipses_and_line_breaks_are_typographic(self):
        rendered = render_answer('He said "yes"...\nand it\'s done.')

        assert rendered.html == ('<p>He said &ldquo;yes&rdquo;&hellip;<br />\n'
                                 'and it&rsquo;s done.</p>')
        assert rendered.kinds == []

    def test_maths_is_published_as_written(self):
        rendered = render_answer('Area \\(x^2\\) and $$a <b$$ here.')

        assert rendered.html == '<p>Area \\(x^2\\) and $$a &lt;b$$ here.</p>'

    def test_carriage_returns_are_line_breaks(self):
        assert render_answer('One\r\nTwo').html == '<p>One<br />\nTwo</p>'


class TestAnAnswerIsProse:

    @pytest.mark.parametrize('answer,kind', [
        ('Text.\n\n![a map](map.jpg)', 'media'),
        ('Text. <iframe src="x"></iframe>', 'media'),
        ('Text.\n\n:::carousel\nimage: a.jpg\n:::', 'widgets'),
        ('Text.[^1]\n\n[^1]: A note.', 'footnotes'),
        ('Text.\n\n| a | b |\n|---|---|\n| 1 | 2 |', 'markup'),
        ('Text.\n\n```\ncode\n```', 'markup'),
        ('Text.\n\n---\n\nMore.', 'markup'),
    ], ids=['image', 'embed', 'widget', 'footnote', 'table', 'code-block', 'rule'])
    def test_what_is_removed_takes_its_content(self, answer, kind):
        rendered = render_answer(answer)

        assert rendered.kinds == [kind]
        for gone in ('map', 'iframe', 'carousel', 'note', '<table', 'code', '<hr'):
            assert gone not in rendered.html
        assert rendered.html.startswith('<p>Text.')

    @pytest.mark.parametrize('answer,html', [
        ('# A heading', '<p>A heading</p>'),
        ('> Quoted words.', '<p>Quoted words.</p>'),
        ('- one\n- two', '<p>one</p>\n<p>two</p>'),
        ('1. one\n\n2. two', '<p>one</p>\n<p>two</p>'),
        ('- one\n    - inner', '<p>one</p>\n<p>inner</p>'),
    ], ids=['heading', 'quote', 'list', 'loose-list', 'nested-list'])
    def test_what_is_flattened_keeps_its_words_as_paragraphs(self, answer, html):
        rendered = render_answer(answer)

        assert rendered.kinds == ['markup']
        assert '\n'.join(line for line in rendered.html.split('\n') if line) == html

    def test_prose_markup_stays(self):
        answer = 'Some **bold**, *italic*, `code` and [a link](https://example.org).'

        rendered = render_answer(answer)

        assert rendered.kinds == []
        assert rendered.html == ('<p>Some <strong>bold</strong>, <em>italic</em>, '
                                 '<code>code</code> and '
                                 '<a href="https://example.org">a link</a>.</p>')

    def test_each_kind_is_named_once_in_the_shared_order(self):
        answer = ('![a](a.jpg) ![b](b.jpg)\n\n# Head\n\n- item\n\n'
                  'Note[^1]\n\n[^1]: n\n\n:::tabs\nx\n:::')

        assert render_answer(answer).kinds == ['media', 'widgets', 'footnotes', 'markup']


class TestTheBudget:

    def test_an_answer_within_it_is_published_whole(self):
        answer = _words(191)

        rendered = render_answer(answer)

        assert rendered.html == f'<p>{answer}</p>'
        assert not rendered.cut

    def test_paragraphs_count_against_it(self):
        answer = _words(100) + '\n\n' + _words(100, 101)

        rendered = render_answer(answer)

        assert rendered.measure == (200, 2, 10 + 2 + 10)
        assert rendered.cut
        assert rendered.html == (f'<p>{_words(100)}</p>\n'
                                 f'<p>{_words(63, 101)}…</p>')

    def test_words_that_are_markup_do_not_count(self):
        answer = '[' + _words(191) + '](https://example.org/a/very/long/url)'

        assert not render_answer(answer).cut

    def test_a_link_across_the_cut_is_dropped_whole(self):
        answer = _words(190) + ' [aaa bb](https://example.org) end'

        rendered = render_answer(answer)

        assert rendered.html == f'<p>{_words(190)}…</p>'

    def test_a_formula_is_one_word_and_never_split(self):
        answer = _words(186) + ' $a^2 + b$ ' + _words(5, 900)

        rendered = render_answer(answer)

        assert rendered.html == f'<p>{_words(186)} $a^2 + b$…</p>'

    def test_rendering_a_cut_answer_again_changes_nothing(self):
        once = render_answer(_words(70) + '\n\n' + _words(70) + '\n\n' + _words(70)).html

        assert render_answer(once).html == once

    def test_more_than_fifteen_lines_take_the_smaller_type(self):
        assert not render_answer(_words(159)).long
        assert render_answer(_words(160)).long
        assert render_answer(_words(400)).long


class TestTheReports:

    def test_the_budget_report_names_the_story_the_step_and_the_count(self, site):
        site()
        df = _story_df([{'step': 4, 'answer': _words(100) + '\n\n' + _words(100)}])

        out = process_story(df, story_name='the-weavers')

        assert _answer_warnings(out) == [{
            'step': 4, 'type': 'panel',
            'message': ("The answer to step 4 of `the-weavers` is too long to fit on the "
                        "story's card. An answer may have up to 5 paragraphs and 18 lines, "
                        "counting 53 characters to a line and two lines for each paragraph "
                        "after the first. This one has 22 lines. It was cut to fit, so the text past the cut does not appear in the story. "
                        "Shorten the answer, or move the detail into a layer panel.")}]

    def test_six_short_paragraphs_are_cut_and_reported(self, site):
        site()
        df = _story_df([{'step': 2, 'answer': '\n\n'.join(['one'] * 6)}])

        out = process_story(df, story_name='s')

        assert out.at[0, 'answer'] == '<p>one</p>\n<p>one</p>\n<p>one</p>\n<p>one</p>\n<p>one…</p>'
        assert 'too long to fit' in _answer_warnings(out)[0]['message']

    def test_five_short_paragraphs_are_not_reported(self, site):
        site()
        df = _story_df([{'step': 2, 'answer': '\n\n'.join(['one'] * 5)}])

        assert _answer_warnings(process_story(df, story_name='s')) == []

    def test_the_published_answer_is_the_rendered_one(self, site):
        site()
        df = _story_df([{'step': 1, 'answer': 'A "quoted" word.'}])

        out = process_story(df, story_name='s')

        assert out.at[0, 'answer'] == '<p>A &ldquo;quoted&rdquo; word.</p>'
        assert _answer_warnings(out) == []

    def test_a_removal_is_reported_once_per_kind(self, site):
        site()
        df = _story_df([{'step': 2, 'answer': 'Text.\n\n![a](a.jpg)\n\n![b](b.jpg)'}])

        out = process_story(df, story_name='s')

        messages = [w['message'] for w in _answer_warnings(out)]
        assert len(messages) == 1
        assert 'image or embed' in messages[0] and 'step 2 of `s`' in messages[0]

    def test_the_spanish_report_names_both_limits(self, site):
        site('es')
        df = _story_df([{'step': 1, 'answer': _words(200)}])

        out = process_story(df, story_name='s')

        message = _answer_warnings(out)[0]['message']
        assert '5 párrafos' in message and '18 líneas' in message and '{{' not in message

    def test_an_empty_answer_is_left_empty(self, site):
        site()
        out = process_story(_story_df([{'step': 1, 'answer': ''}]), story_name='s')

        assert out.at[0, 'answer'] == ''
        assert out.to_dict('records')[0]['answer_long'] is False

    def test_the_published_step_says_which_answers_take_the_smaller_type(self, site):
        site()
        df = _story_df([{'step': 1, 'answer': _words(159)}, {'step': 2, 'answer': _words(160)},
                        {'step': 3, 'answer': ''}])

        out = process_story(df, story_name='s')

        assert [step['answer_long'] for step in out.to_dict('records')] == [False, True, False]
