"""Unit Tests for the Limits on a Step's Answer

A step's `answer` is prose about the object the reader is looking at, and
it is read on a card that does not scroll. Three rules hold it to that at
build time, all of them applied to the markdown exactly as the author
wrote it, before the glossary pass injects anchors into it.

**Plain prose only.** An answer is sentences, so everything that is not
sentences comes out of it: media and embeds, footnotes, tables, code
blocks and horizontal rules are removed outright, while lists, headings
and blockquotes keep their words and lose their marks. Bold, italics,
inline links, `[[term]]`, inline LaTeX, code spans and paragraph breaks
are prose and stay. Detection knows nothing about code spans, so an
image written inside backticks goes too: the whole set has to be
expressions the Compositor can implement identically, and the answer is
not the place for a markdown tutorial. A bare image URL is text and
stays.

**A hard limit.** `ANSWER_WORD_LIMIT` words, above which the answer is
cut at a word boundary and closed with an ellipsis. The cut never lands
inside markup — a link, a glossary reference, a LaTeX span, a code span,
an HTML tag — so an answer that ends near markup is published shorter
than the limit rather than broken at it. A footnote reference is not on
that list because the prose pass has already taken it out.

Length on its own is never reported: the build speaks where it has
changed the author's words and stays quiet where it has not.

The counting rule is shared with the Compositor and is the whole of what
"a word" means here: trim, split on Unicode whitespace, count the
non-empty tokens. Markup and URLs are words, because they occupy the
card like any other text.

Version: v1.8.0
"""

import ast
import io
import os
import shutil
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar.config as config
import telar.processors.stories as stories
from telar.processors.stories import ANSWER_WORD_LIMIT, process_story

LANGUAGES = os.path.join(os.path.dirname(__file__), '..', '..',
                         '_data', 'languages')

STORIES_MODULE = os.path.join(os.path.dirname(__file__), '..', '..',
                              'scripts', 'telar', 'processors', 'stories.py')

@pytest.fixture
def site(tmp_path, monkeypatch):
    """A site root with the real language files and a chosen `_config.yml`.

    Both caches in `telar.config` are module-level and read the working
    directory, so a test that does not clear them reads whatever the
    previous test left behind: the language of another site, or a
    once-per-build warning another test already spent.
    """
    def _make(config_text='', write_config=True):
        root = tmp_path / ('site%d' % len(list(tmp_path.iterdir())))
        (root / '_data').mkdir(parents=True)
        shutil.copytree(LANGUAGES, root / '_data' / 'languages')
        if write_config:
            (root / '_config.yml').write_text(
                'telar_language: "en"\n' + config_text, encoding='utf-8')
        monkeypatch.chdir(root)
        config._lang_data = None
        return root

    yield _make
    config._lang_data = None


@pytest.fixture(autouse=True)
def no_glossary(monkeypatch):
    """No glossary, so `[[term]]` stays literal and the assertions are about
    the limits rather than about anchors.
    """
    monkeypatch.setattr(stories, 'load_glossary_terms', lambda: {})


def _story_df(rows):
    """A minimal story DataFrame with the columns process_story expects."""
    base = {'question': '', 'answer': '', 'object': '', 'x': '', 'y': '',
            'zoom': ''}
    return pd.DataFrame([{**base, **row} for row in rows])


def _words(count, start=1):
    return ' '.join('word%d' % n for n in range(start, start + count))


def _answer_warnings(out):
    return [w for w in out.attrs['viewer_warnings'] if w['type'] == 'panel']


def _rule_set_docstring():
    """The string literal written under `ANSWER_PROSE_RULES` in the module."""
    tree = ast.parse(io.open(STORIES_MODULE, encoding='utf-8').read())
    for index, node in enumerate(tree.body):
        named = (isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name)
                         and t.id == 'ANSWER_PROSE_RULES'
                         for t in node.targets))
        if not named:
            continue
        following = tree.body[index + 1]
        assert isinstance(following, ast.Expr)
        assert isinstance(following.value, ast.Constant)
        return following.value.value
    raise AssertionError('ANSWER_PROSE_RULES is not assigned in the module')


# A phrase unique to each kind's message, so a test can say which warning
# it got without repeating the whole sentence.
KEY_BY_KIND = {
    'media': 'image or embed',
    'widgets': 'widgets (blocks that start with',
    'footnotes': 'footnotes in the answer',
    'markup': 'markup in the answer',
}


class TestTheCountingRule:
    """Trim, split on Unicode whitespace, count non-empty tokens."""

    def test_unicode_whitespace_separates_words(self):
        assert stories._count_answer_words(
            'one\u00a0two\tthree\nfour  five') == 5

    def test_surrounding_whitespace_counts_for_nothing(self):
        assert stories._count_answer_words('   one two   ') == 2
        assert stories._count_answer_words('   ') == 0

    def test_markup_and_urls_count_as_words(self):
        assert stories._count_answer_words(
            '[a link](https://example.org/x) https://example.org/y') == 3

    def test_removed_markup_counts_for_nothing(self):
        text, kinds = stories._reduce_answer_to_prose(
            'one ![alt text here](plate.jpg) two')
        assert kinds == ['media']
        assert stories._count_answer_words(text) == 2


# Every form the prose pass takes out of an answer, as (kind, before,
# after). The kind is the warning it is reported under: one answer earns
# one warning per kind, however many forms of that kind it holds.
REMOVED = [
    ('media', 'Before <img src="plate.jpg" alt="Plate"> after.',
     'Before  after.'),
    ('media', 'Before <iframe src="https://example.org/map"></iframe> after.',
     'Before  after.'),
    ('media', 'Before <video controls><source src="mill.mp4"></video> after.',
     'Before  after.'),
    ('media', 'Before <audio src="song.mp3"></audio> after.',
     'Before  after.'),
    ('media', 'Before <embed src="folio.pdf"> after.', 'Before  after.'),
    ('media', 'Before <object data="folio.pdf"></object> after.',
     'Before  after.'),
    ('media', 'Before ![The plate](plate.jpg) after.', 'Before  after.'),
    ('widgets', 'Before.\n\n:::glossary\nentry: carta\nalign: left\n:::\n\nAfter.',
     'Before.\n\n\nAfter.'),
    ('widgets', 'Before.\n\n:::carousel\nimage: a.jpg\n---\nimage: b.jpg\n:::\nAfter.',
     'Before.\n\nAfter.'),
    ('media', 'Before ![The plate [La lámina]](plate.jpg) after.',
     'Before  after.'),
    ('footnotes', 'The mill ran on water.[^1]', 'The mill ran on water.'),
    ('footnotes', 'Water.\n\n[^1]: Guaman Poma, folio 1157.\n', 'Water.\n\n'),
    ('footnotes', 'Water.\n\n[^1]: Guaman Poma,\n    folio 1157.\nAfter.\n',
     'Water.\n\nAfter.\n'),
    ('markup', 'Before\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\nAfter.\n',
     'Before\n\n\nAfter.\n'),
    ('markup', 'Before\n\n```\ncode here\n```\n\nAfter.\n',
     'Before\n\n\nAfter.\n'),
    ('markup', 'Before\n\n---\n\nAfter.\n', 'Before\n\n\nAfter.\n'),
    ('markup', 'Before\n\n* * *\n\nAfter.\n', 'Before\n\n\nAfter.\n'),
]

# Every form flattened rather than removed: the marks go, the words stay.
FLATTENED = [
    ('markup', '- first\n- second\n', 'first\nsecond\n'),
    ('markup', '* first\n+ second\n', 'first\nsecond\n'),
    ('markup', '1. first\n2) second\n', 'first\nsecond\n'),
    ('markup', '## The plate\n', 'The plate\n'),
    ('markup', '## The plate ##\n', 'The plate\n'),
    ('markup', '> Noted at the archive.\n', 'Noted at the archive.\n'),
    ('markup', '>> Noted twice.\n', 'Noted twice.\n'),
    ('markup', '> - quoted point\n', 'quoted point\n'),
]

# Prose, which the pass has no business touching.
KEPT = [
    '**Bold** and *italic* and _more_.',
    'See [the catalogue](https://example.org/x) for the plate.',
    'A [[woodcut]] of the mill.',
    r'The area is $\pi r^2$ exactly.',
    'Type `folio 1157` to find it.',
    'First paragraph.\n\nSecond paragraph.\n',
    'See https://example.org/plate.jpg for the plate.',
]

KINDS = ['media', 'widgets', 'footnotes', 'markup']


class TestAnAnswerIsPlainProse:

    @pytest.mark.parametrize('kind,before,after', REMOVED)
    def test_each_removed_form_comes_out(self, site, kind, before, after):
        site()
        df = _story_df([{'step': '3', 'answer': before}])
        out = process_story(df, story_name='mill')
        assert out.iloc[0]['answer'] == after

    @pytest.mark.parametrize('kind,before,after', FLATTENED)
    def test_each_flattened_form_keeps_its_words(self, site, kind, before,
                                                 after):
        site()
        df = _story_df([{'step': '3', 'answer': before}])
        out = process_story(df, story_name='mill')
        assert out.iloc[0]['answer'] == after

    @pytest.mark.parametrize('kind,before,after', REMOVED + FLATTENED)
    def test_each_form_is_reported_under_its_kind(self, site, kind, before,
                                                  after):
        site()
        df = _story_df([{'step': '3', 'answer': before}])
        out = process_story(df, story_name='mill')
        warnings = _answer_warnings(out)
        assert len(warnings) == 1
        assert KEY_BY_KIND[kind] in warnings[0]['message']

    @pytest.mark.parametrize('answer', KEPT)
    def test_prose_comes_back_byte_for_byte(self, site, answer):
        site()
        df = _story_df([{'step': '1', 'answer': answer}])
        out = process_story(df, story_name='mill')
        assert out.iloc[0]['answer'] == answer
        assert _answer_warnings(out) == []

    def test_an_image_inside_a_code_span_comes_out_too(self, site):
        """No code-span awareness: the rule is one expression, not a parser."""
        site()
        df = _story_df([{'step': '1',
                         'answer': 'Type `![alt](x.jpg)` to embed.'}])
        out = process_story(df, story_name='mill')
        assert out.iloc[0]['answer'] == 'Type `` to embed.'

    def test_one_kind_earns_one_warning_however_many_forms(self, site):
        """A heading, a list, a quote and a rule are all `markup`."""
        site()
        answer = '# Title\n\n- one\n- two\n\n> quoted\n\n---\n'
        df = _story_df([{'step': '1', 'answer': answer}])
        out = process_story(df, story_name='mill')
        assert len(_answer_warnings(out)) == 1

    def test_each_kind_earns_its_own_warning(self, site):
        site()
        answer = ('# Title\n\nWater.[^1] ![plate](p.jpg)\n\n'
                  ':::glossary\nentry: carta\n:::\n')
        df = _story_df([{'step': '1', 'answer': answer}])
        out = process_story(df, story_name='mill')
        messages = [w['message'] for w in _answer_warnings(out)]
        assert len(messages) == 4
        for message, kind in zip(messages, KINDS):
            assert KEY_BY_KIND[kind] in message

    def test_the_media_warning_says_what_happened_and_what_to_do(self, site):
        site()
        df = _story_df([{'step': '3',
                         'answer': 'Before ![The plate](plate.jpg) after.'}])
        out = process_story(df, story_name='mill')
        assert _answer_warnings(out)[0]['message'] == (
            "An image or embed in the answer to step 3 of `mill` was "
            "removed. A step's answer is plain prose: put the image in a "
            "layer panel, or make it the step's object."
        )

    def test_the_footnote_warning_says_what_happened_and_what_to_do(self, site):
        site()
        df = _story_df([{'step': '3', 'answer': 'Water.[^1]'}])
        out = process_story(df, story_name='mill')
        assert _answer_warnings(out)[0]['message'] == (
            "A step's answer is plain prose, so the footnotes in the answer "
            "to step 3 of `mill` came out, references and definitions alike. "
            "Move the note into a layer panel, or fold what it says into the "
            "sentence."
        )

    def test_the_markup_warning_says_what_went_and_what_stayed(self, site):
        site()
        df = _story_df([{'step': '3', 'answer': '# Title\n'}])
        out = process_story(df, story_name='mill')
        assert _answer_warnings(out)[0]['message'] == (
            "A step's answer is plain prose, so markup in the answer to step "
            "3 of `mill` was flattened: lists, headings and quotes kept "
            "their words and lost their marks, and tables, code blocks and "
            "horizontal rules came out altogether. Move that material into "
            "a layer panel, where it renders as written."
        )

    def test_the_warning_carries_the_step_it_belongs_to(self, site):
        site()
        df = _story_df([{'step': '3',
                         'answer': 'Before ![The plate](plate.jpg) after.'}])
        out = process_story(df, story_name='mill')
        assert _answer_warnings(out)[0]['step'] == '3'

    def test_the_rule_set_names_every_form_in_its_docstring(self):
        """The docstring beside the rule set is the contract the Compositor
        reads, so every rule in the set has to be findable in it by name.

        Read off the syntax, because a constant's docstring is a bare
        string expression that no attribute exposes at runtime.
        """
        described = _rule_set_docstring()
        for rule in stories.ANSWER_PROSE_RULES:
            assert rule.name in described, rule.name

    def test_every_rule_carries_a_kind_that_has_a_warning(self):
        for rule in stories.ANSWER_PROSE_RULES:
            assert rule.kind in KINDS


class TestTheHardLimit:

    def test_the_constant_is_the_number_the_compositor_expects(self):
        assert ANSWER_WORD_LIMIT == 200

    def test_exactly_the_limit_is_left_alone(self, site):
        site()
        answer = _words(200)
        df = _story_df([{'step': '1', 'answer': answer}])
        out = process_story(df, story_name='mill')
        assert out.iloc[0]['answer'] == answer
        assert _answer_warnings(out) == []

    def test_one_word_over_is_cut_to_the_limit(self, site):
        site()
        df = _story_df([{'step': '1', 'answer': _words(201)}])
        out = process_story(df, story_name='mill')
        assert out.iloc[0]['answer'] == _words(200) + '…'

    def test_the_cut_closes_with_one_ellipsis_character(self, site):
        site()
        df = _story_df([{'step': '1', 'answer': _words(400)}])
        out = process_story(df, story_name='mill')
        answer = out.iloc[0]['answer']
        assert answer.endswith('…')
        assert '...' not in answer

    def test_the_warning_names_the_count_and_the_limit(self, site):
        site()
        df = _story_df([{'step': '4', 'answer': _words(201)}])
        out = process_story(df, story_name='mill')
        assert _answer_warnings(out)[0]['message'] == (
            'The answer to step 4 of `mill` runs to 201 words and was cut '
            'at 200. The text past the cut does not appear in the story. '
            'Shorten the answer, or move the detail into a layer panel.'
        )


STRADDLING_MARKUP = [
    '[the catalogue](https://example.org/x)',
    '[[Colonial Period|colonial-period]]',
    '`code and more`',
    '``code and more``',
    '``code with ` inside``',
    '`code and more``',
    '```code and more```',
    '<em class="title">Mill</em>',
    '$a + b$',
    '$$a + b$$',
    r'\[a + b\]',
    r'\(a + b\)',
    r'\begin{align} a &= b \end{align}',
]


class TestTheCutNeverSplitsMarkup:

    @pytest.mark.parametrize('markup', STRADDLING_MARKUP)
    def test_markup_across_the_boundary_moves_the_cut_back(self, site, markup):
        """The markup starts at word 200, so the boundary falls inside it.

        Every form here holds whitespace, which is the only way a word
        boundary can land in the middle of one.
        """
        site()
        answer = _words(199) + ' ' + markup + ' ' + _words(5, start=500)
        df = _story_df([{'step': '1', 'answer': answer}])
        out = process_story(df, story_name='mill')
        assert out.iloc[0]['answer'] == _words(199) + '…'

    def test_a_stray_backtick_does_not_hide_a_boundary(self, site):
        """A backtick with no closing run of its length is literal, as the
        template reads it, so it pairs with nothing and the cut stays at
        the limit.
        """
        site()
        answer = "It`s " + _words(199) + ' ' + _words(5, start=500)
        df = _story_df([{'step': '1', 'answer': answer}])
        out = process_story(df, story_name='mill')
        assert out.iloc[0]['answer'] == "It`s " + _words(199) + '…'

    def test_backticks_in_a_tag_open_nothing(self, site):
        """kramdown reads the tag before code, so the backticks in its
        attribute do not pair with a later run and pull the cut back."""
        site()
        # The tag is two words, so the limit falls after word 198.
        answer = '<br title="``"> ' + _words(198) + ' ' + _words(5, start=500) + '``'
        df = _story_df([{'step': '1', 'answer': answer}])
        out = process_story(df, story_name='mill')
        assert out.iloc[0]['answer'] == '<br title="``"> ' + _words(198) + '…'

    def test_markup_holding_no_whitespace_survives_whole(self, site):
        """A word boundary never falls inside a token, so markup written
        without whitespace in it cannot be straddled.
        """
        site()
        link = '[x](https://example.org/x)'
        answer = _words(199) + ' ' + link + ' ' + _words(5, start=500)
        df = _story_df([{'step': '1', 'answer': answer}])
        out = process_story(df, story_name='mill')
        assert out.iloc[0]['answer'] == _words(199) + ' ' + link + '…'


class TestLengthOnItsOwnIsSilent:

    def test_a_long_answer_under_the_hard_limit_earns_no_report(self, site):
        site()
        answer = _words(199)
        df = _story_df([{'step': '2', 'answer': answer}])
        out = process_story(df, story_name='mill')
        assert _answer_warnings(out) == []
        assert out.iloc[0]['answer'] == answer

    def test_the_site_cannot_ask_for_a_length_warning(self, site):
        """A leftover setting from an older site is inert, not an error."""
        site('story_content:\n  answer_word_limit: 50\n')
        answer = _words(120)
        df = _story_df([{'step': '1', 'answer': answer}])
        out = process_story(df, story_name='mill')
        assert _answer_warnings(out) == []
        assert out.iloc[0]['answer'] == answer


class TestWhatTheseRulesLeaveAlone:

    def test_an_answer_under_both_limits_comes_back_byte_for_byte(self, site):
        site()
        answer = ('The mill at [Huarochirí](https://example.org/h) is a '
                  '[[woodcut]], described in the catalogue. Compare '
                  'https://example.org/copy and `folio 1157`.\n\n'
                  'The area is $\\pi r^2$ exactly, **and no more**.\n')
        df = _story_df([{'step': '1', 'answer': answer}])
        out = process_story(df, story_name='mill')
        assert out.iloc[0]['answer'] == answer
        assert _answer_warnings(out) == []

    def test_the_question_is_never_counted_or_cut(self, site):
        site()
        question = _words(300)
        df = _story_df([{'step': '1', 'question': question,
                         'answer': 'Short enough.'}])
        out = process_story(df, story_name='mill')
        assert out.iloc[0]['question'] == question
        assert _answer_warnings(out) == []

    def test_an_image_in_the_question_is_left_alone(self, site):
        site()
        question = 'What is ![this](plate.jpg)?'
        df = _story_df([{'step': '1', 'question': question,
                         'answer': 'Short enough.'}])
        out = process_story(df, story_name='mill')
        assert out.iloc[0]['question'] == question
        assert _answer_warnings(out) == []


PROSE_FIXTURE = (
    '# The plate\n'
    '\n'
    'A [[woodcut]] of the [mill](https://example.org/m).[^1]\n'
    '\n'
    '> Noted at the archive.\n'
    '\n'
    '- first point\n'
    '- second point\n'
    '\n'
    '| a | b |\n'
    '| --- | --- |\n'
    '| 1 | 2 |\n'
    '\n'
    '---\n'
    '\n'
    '```\n'
    'code here\n'
    '```\n'
    '\n'
    '![The plate](/assets/plate.jpg)\n'
    '\n'
    '[^1]: Guaman Poma, folio 1157.\n'
)

# The blank lines the removals leave behind are not repaired: each rule
# takes out what it matched and nothing else, and markdown decides later
# what the whitespace means.
PROSE_FIXTURE_OUTPUT = (
    'The plate\n'
    '\n'
    'A [[woodcut]] of the [mill](https://example.org/m).\n'
    '\n'
    'Noted at the archive.\n'
    '\n'
    'first point\n'
    'second point\n'
    '\n\n\n\n\n\n'
)


class TestAnAnswerCarryingEverythingAtOnce:
    """One answer with a heading, a glossary reference, an inline link, a
    footnote reference and its definition, a quote, a list, a table, a
    horizontal rule, a fenced code block and an image.
    """

    def test_the_output_is_exactly_the_prose(self, site):
        site()
        df = _story_df([{'step': '7', 'answer': PROSE_FIXTURE}])
        out = process_story(df, story_name='mill')
        assert out.iloc[0]['answer'] == PROSE_FIXTURE_OUTPUT

    def test_all_three_kinds_are_reported_once_each(self, site):
        site()
        df = _story_df([{'step': '7', 'answer': PROSE_FIXTURE}])
        out = process_story(df, story_name='mill')
        messages = [w['message'] for w in _answer_warnings(out)]
        assert len(messages) == 3
        for message, kind in zip(messages, ['media', 'footnotes', 'markup']):
            assert KEY_BY_KIND[kind] in message

    def test_the_prose_inside_it_is_untouched(self, site):
        site()
        df = _story_df([{'step': '7', 'answer': PROSE_FIXTURE}])
        out = process_story(df, story_name='mill')
        answer = out.iloc[0]['answer']
        assert '[[woodcut]]' in answer
        assert '[mill](https://example.org/m)' in answer
        assert '[^1]' not in answer
        assert '|' not in answer
        assert '#' not in answer


class TestTheProseRulesRunBeforeTheCount:

    def test_flattened_marks_do_not_count_towards_the_limit(self, site):
        """200 words behind list markers is 200 words, not 400."""
        site()
        answer = ''.join('- word%d\n' % n for n in range(1, 201))
        df = _story_df([{'step': '1', 'answer': answer}])
        out = process_story(df, story_name='mill')
        answer_out = out.iloc[0]['answer']
        assert '…' not in answer_out
        assert stories._count_answer_words(answer_out) == 200

    def test_removed_footnotes_do_not_count_towards_the_limit(self, site):
        site()
        answer = (_words(200)
                  + '\n\n[^1]: Guaman Poma, folio 1157, and more words.\n')
        df = _story_df([{'step': '1', 'answer': answer}])
        out = process_story(df, story_name='mill')
        assert out.iloc[0]['answer'] == _words(200) + '\n\n'
