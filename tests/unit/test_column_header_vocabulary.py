"""Unit Tests for the Shared Spreadsheet Header Vocabulary

The framework and the Telar Compositor both decide what a Spanish column
header means, from two independent tables. Three divergences have been
found this way: the `medium` family, the manual-step `audience` values,
and the accented aliases — each one because one side asked the other.
That works and it does not scale, and it stops working the moment neither
side happens to ask.

`tests/fixtures/column-headers.json` is the instrument that replaces
asking. Both sides keep a copy and maintain the union, so a spelling
either side accepts is a spelling both are tested against.

The accent property is the one that found the last divergence. Half the
Compositor's accented forms were present and half were not, and there was
no rule distinguishing them — the signature of a list maintained by hand,
one spelling at a time. A derived property cannot drift that way.

Gender is meaning rather than spelling: `privado` and `privada` are
different words about different things, and a rule that folded them
together would be wrong in the direction that matters. So the derivation
strips diacritics and never touches a final vowel.

Version: v1.8.0
"""

import json
import os
import sys
import unicodedata

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.csv_utils import COLUMN_NAME_MAPPING

FIXTURE = os.path.join(os.path.dirname(__file__), '..', 'fixtures',
                       'column-headers.json')


def _fixture():
    with open(FIXTURE, encoding='utf-8') as handle:
        return json.load(handle)['headers']


def _without_diacritics(text):
    """The same text with its accents removed and nothing else changed."""
    return ''.join(character for character
                   in unicodedata.normalize('NFD', text)
                   if unicodedata.category(character) != 'Mn')


class TestEverySharedSpellingIsAccepted:

    @pytest.mark.parametrize('entry', _fixture(),
                             ids=lambda e: e['header'])
    def test_the_header_normalises_to_the_agreed_name(self, entry):
        assert COLUMN_NAME_MAPPING.get(entry['header']) == entry['canonical']

    def test_the_fixture_is_not_empty(self):
        """A fixture that fails to load satisfies every test above it."""
        assert len(_fixture()) >= 60


class TestTheAccentPropertyHolds:
    """Derived rather than listed, which is the whole point.

    A header's plain spelling has to mean what its accented spelling
    means. Someone types `descripcion` because their keyboard is awkward,
    not because they mean something else.
    """

    def test_every_accented_alias_has_its_plain_form(self):
        missing = sorted(alias for alias in COLUMN_NAME_MAPPING
                         if _without_diacritics(alias) != alias
                         and _without_diacritics(alias) not in COLUMN_NAME_MAPPING)

        assert missing == []

    def test_the_two_spellings_never_disagree(self):
        disagreeing = sorted(
            alias for alias in COLUMN_NAME_MAPPING
            if _without_diacritics(alias) in COLUMN_NAME_MAPPING
            and (COLUMN_NAME_MAPPING[_without_diacritics(alias)]
                 != COLUMN_NAME_MAPPING[alias]))

        assert disagreeing == []

    def test_stripping_accents_leaves_the_final_vowel_alone(self):
        """The guard on the derivation, not on the map.

        `privado` and `privada` differ by gender and mean different
        things. A normalisation that reached the final vowel would fold
        them together, and the fixture's own entries would stop being
        distinguishable.
        """
        assert _without_diacritics('privada') == 'privada'
        assert _without_diacritics('descripción') == 'descripcion'

    def test_both_genders_survive_as_separate_entries(self):
        for spelling in ('privado', 'privada', 'protegido', 'protegida'):
            assert COLUMN_NAME_MAPPING[spelling] == 'protected'

    def test_both_spellings_of_the_acknowledgement_column_are_accepted(self):
        """`citado` and `citada` are the same column, written either way.

        The header carries the protected stories a glossary term quotes on
        purpose. A spelling this table misses leaves the column under the
        author's own name, the acknowledgement goes unread, and the build
        fails on an overlap they already declared.
        """
        for spelling in ('citado_en_historias', 'citada_en_historias'):
            assert COLUMN_NAME_MAPPING[spelling] == 'quoted_in_stories'
