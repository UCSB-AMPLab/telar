"""Unit Tests for Values Surviving the Frontmatter They Are Written Into

Every object, story and glossary page the build generates carries its
metadata as YAML frontmatter, and the values in it are the author's: a
title, a byline, a catalogue number, a credit line. A value that changes
type or breaks its own document on the way through is the author's content
lost between their spreadsheet and their site.

Two properties, and the second is the one that is easy to state loosely
and get wrong. The frontmatter must parse; and every value must come back
out as the same string that went in — not merely as something equal to it,
because YAML will hand back `True` for `'true'` and `1234` for `'1234'`,
and both compare equal to nothing the author wrote.

The corpus is shared with the Telar Compositor, which serialises the same
fields on its own publish path. Its three additions are the ones a list
written from scratch tends to miss: sexagesimals and dates, which are YAML
1.1 types a byline can plausibly contain; alternate number bases, which
look like catalogue numbers; and the float specials, which a scientific
caption can produce.

It lives in `tests/fixtures/frontmatter-scalars.json` rather than here,
so the two sides pin against one file instead of two lists neither can
see. Each entry carries the text as written in the sheet, the type the
author meant, and the scalar this side writes it as.

Version: v1.8.0
"""

import csv
import json
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import generate_collections
from generate_collections import _object_page


FIXTURE = os.path.join(os.path.dirname(__file__), '..', 'fixtures',
                       'frontmatter-scalars.json')


def _scalars():
    with open(FIXTURE, encoding='utf-8') as handle:
        return json.load(handle)['scalars']


# Every one of these is a string an author could type into a cell, and
# every one of them must come back a string.
AWKWARD = [entry['source'] for entry in _scalars()]


def _frontmatter(page):
    """The parsed frontmatter of a generated page."""
    assert page.startswith('---\n'), page[:40]
    body = page[4:]
    end = body.index('\n---')
    return yaml.safe_load(body[:end])


class TestAnObjectPageSurvivesItsOwnMetadata:

    @pytest.mark.parametrize('value', AWKWARD, ids=repr)
    def test_a_title_comes_back_as_the_string_it_went_in_as(self, value):
        page = _object_page({'object_id': 'an-object', 'title': value})

        title = _frontmatter(page)['title']

        assert isinstance(title, str), (value, type(title))
        assert title == value

    @pytest.mark.parametrize('value', AWKWARD, ids=repr)
    def test_an_identifier_does_not_break_the_document(self, value):
        """`object_id` was written unquoted, so `*star` made it an alias.

        The failure is not a wrong value — it is a page whose frontmatter
        does not parse at all, which takes the whole build with it.
        """
        page = _object_page({'object_id': value or 'x', 'title': 'a title'})

        parsed = _frontmatter(page)

        assert isinstance(parsed['object_id'], str)

    @pytest.mark.parametrize('field', ['creator', 'credit', 'period',
                                       'dimensions', 'location', 'year',
                                       'subjects', 'alt_text'])
    def test_every_written_field_survives_a_quote_and_a_boolean(self, field):
        """`year` and `subjects` were quoted but never escaped.

        A quote in either ended the scalar early and left the rest of the
        frontmatter as malformed YAML.
        """
        for value in ('a "quoted" value', 'true', '1234'):
            page = _object_page({'object_id': 'an-object', 'title': 't',
                                 field: value})

            got = _frontmatter(page)[field]

            assert isinstance(got, str), (field, value, type(got))
            assert got == value

    def test_a_custom_field_survives_too(self):
        """Anything the known set does not name lands in extra_metadata."""
        page = _object_page({'object_id': 'an-object', 'title': 't',
                             'shelfmark': 'MS 0x1F "A"'})

        assert _frontmatter(page)['extra_metadata']['shelfmark'] == 'MS 0x1F "A"'


class TestTheTypeIsTheAuthorsType:
    """The clause that stops both sides being wrong together.

    A property stated only as "the two publish paths agree" is satisfied by
    both of them turning 'true' into a boolean. What the author typed is a
    string, so what comes back has to be one.
    """

    @pytest.mark.parametrize('value', ['true', 'false', 'null', '1234',
                                       '3.14', '0x1F', '.inf', '12:30',
                                       '2026-09-13'])
    def test_a_value_that_looks_like_another_type_stays_a_string(self, value):
        page = _object_page({'object_id': 'an-object', 'title': value,
                             'creator': value})
        parsed = _frontmatter(page)

        assert isinstance(parsed['title'], str), (value, parsed['title'])
        assert isinstance(parsed['creator'], str), (value, parsed['creator'])

    def test_a_number_from_the_spreadsheet_is_written_as_text(self):
        """Pandas hands over numpy scalars, not Python strings.

        A dict serialised without forcing text emits the value's type, which
        is the defect in the other direction: the page would carry a number
        where every template expects a string.
        """
        page = _object_page({'object_id': 'an-object', 'title': 'a title',
                             'year': 1890})

        assert _frontmatter(page)['year'] == '1890'


class TestAGlossaryTermSurvivesItsOwnMetadata:
    """The glossary writes three fields and iterates one of them.

    `related_terms` is read by the layout as a sequence. Written as a
    comma-joined scalar it parsed back as one string, and Liquid walks a
    string as a single item, so a term naming two related terms looked up
    one id that matches nothing: the heading rendered with an empty list
    under it. A term naming exactly one was correct by accident, which is
    why the field looked like it worked.
    """

    def _terms(self, tmp_path, rows):
        source = tmp_path / 'glossary.csv'
        with open(source, 'w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['term_id', 'title', 'definition', 'related_terms'])
            writer.writerows(rows)

        out = tmp_path / 'out'
        out.mkdir()
        generate_collections._generate_glossary_from_csv(str(source), out, {})

        return {path.stem: _frontmatter(path.read_text(encoding='utf-8'))
                for path in out.glob('*.md')}

    @pytest.mark.parametrize('value', AWKWARD, ids=repr)
    def test_a_term_title_comes_back_as_the_string_it_went_in_as(self, tmp_path, value):
        if not value.strip():
            pytest.skip('a term with no title is skipped before it is written')

        terms = self._terms(tmp_path, [['a-term', value, 'a definition here', '']])

        # Stripped on the way in: padding in a spreadsheet cell is an
        # accident of typing, and this path reads cells rather than a dict.
        assert terms['a-term']['title'] == value.strip()

    def test_two_related_terms_come_back_as_two(self, tmp_path):
        terms = self._terms(
            tmp_path, [['a-term', 'A term', 'a definition here', 'one|two']])

        assert terms['a-term']['related_terms'] == ['one', 'two']

    def test_one_related_term_still_comes_back_as_a_sequence(self, tmp_path):
        """The case that was right by accident has to stay right on purpose."""
        terms = self._terms(
            tmp_path, [['a-term', 'A term', 'a definition here', 'only-one']])

        assert terms['a-term']['related_terms'] == ['only-one']

    def test_a_term_with_none_does_not_write_the_field(self, tmp_path):
        """The layout branches on its presence to draw the whole section."""
        terms = self._terms(
            tmp_path, [['a-term', 'A term', 'a definition here', '']])

        assert 'related_terms' not in terms['a-term']

    def test_an_identifier_does_not_break_the_document(self, tmp_path):
        terms = self._terms(
            tmp_path, [['*star', 'A term', 'a definition here', '']])

        assert terms['*star']['term_id'] == '*star'


class TestTheSharedCorpusIsWhatThisSideWrites:
    """The fixture is the contract, so it is pinned as one.

    A corpus both sides read is only worth having if each side is tested
    against what it actually writes: a fixture nobody checks the serialised
    form against records an agreement that may not hold.
    """

    @pytest.mark.parametrize('entry', _scalars(),
                             ids=lambda e: repr(e['source']))
    def test_the_scalar_is_written_as_the_fixture_says(self, entry):
        block = generate_collections._frontmatter_block({'title': entry['source']})

        scalar = block[len('title:'):].rstrip('\n')
        assert scalar.lstrip(' ') == entry['expected_yaml']

    @pytest.mark.parametrize('entry', _scalars(),
                             ids=lambda e: repr(e['source']))
    def test_it_round_trips_to_the_type_the_author_meant(self, entry):
        block = generate_collections._frontmatter_block({'title': entry['source']})

        title = yaml.safe_load(block)['title']

        assert entry['intended_type'] == 'string', entry
        assert isinstance(title, str), (entry, type(title))
        assert title == entry['source']

    def test_the_corpus_is_not_empty(self):
        """A fixture that fails to load satisfies every test above it."""
        assert len(_scalars()) >= 40


class TestACarriageReturnIsWrittenBackAsTyped:
    """The two cases the shared corpus cannot hold, pinned on this side alone.

    The fixture's own comment says why they are not in it: the Compositor
    normalises a bare CR and a CRLF pair to a single LF on its publish path,
    and the framework writes back what the author typed. The two sides have
    different correct values for one source, so the union has no entry they
    could agree on.

    That is a reason to keep them out of the corpus, not a reason to leave
    the behaviour unpinned. A CR reaches a cell from any spreadsheet edited
    on Windows, `_YAML_1_1_LINE_BREAKS` exists to force these into an escape
    rather than a raw character, and nothing else in the suite would notice
    if that stopped happening.
    """

    CASES = [('a bare carriage return', 'A\rreturn', '"A\\rreturn"'),
             ('a CRLF pair', 'Two\r\nlines', '"Two\\r\\nlines"')]

    @pytest.mark.parametrize('label,source,expected', CASES,
                             ids=[label for label, _, _ in CASES])
    def test_it_is_written_as_an_escape(self, label, source, expected):
        block = generate_collections._frontmatter_block({'title': source})

        assert block[len('title:'):].rstrip('\n').lstrip(' ') == expected

    @pytest.mark.parametrize('label,source,expected', CASES,
                             ids=[label for label, _, _ in CASES])
    def test_it_comes_back_as_the_string_it_went_in_as(self, label, source,
                                                       expected):
        block = generate_collections._frontmatter_block({'title': source})

        assert yaml.safe_load(block)['title'] == source

    @pytest.mark.parametrize('label,source,expected', CASES,
                             ids=[label for label, _, _ in CASES])
    def test_the_block_it_is_in_is_not_truncated(self, label, source, expected):
        """A raw CR would end the scalar and drop the keys after it."""
        page = '---\n' + generate_collections._frontmatter_block(
            {'title': source, 'layout': 'object'}) + '---\n\nbody\n'

        assert _frontmatter(page)['layout'] == 'object'
