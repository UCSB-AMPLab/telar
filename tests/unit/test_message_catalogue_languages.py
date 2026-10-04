"""Unit Tests for Each Message Sitting in the Dictionary of Its Own Language

`messages.py` holds the two languages as two dictionaries under one key
space, so putting a string in the wrong one is a single misplaced line
rather than an error. It happened while the `config_merge` notes were
being localised: two keys were inserted at line indices, and the Spanish
of one landed in the English dictionary while its English landed in the
Spanish. Both dictionaries had every key, both rendered, both filled
their placeholders, and each language read one line of the other.

The existing guards could not see it. A key present in both languages was
present in both. A Spanish string that differs from its English differed
from it — a crossed pair differs in both directions. Everything those
tests ask stayed true of a catalogue that was wrong.

What is left is the writing itself. Spanish orthography is the one
mechanical trace: the accented vowels, the eñe, the opening marks. Over
the whole catalogue it found exactly the misplaced string and nothing
else, so it is precise enough to hold.

**The other direction needs a different instrument.** English leaking
into Spanish leaves no orthographic trace — 62 of the Spanish strings are
legitimately unaccented, so their plainness proves nothing, and a word
list would be guessing at vocabulary. What does catch it is that the two
values for one key are almost never the same string: only five keys in
the catalogue are identical in both languages, and all five are proper
nouns or a symbol. Those are pinned by name, so a sixth has to be
declared rather than discovered.

An adversarial review found this half missing and it was half right: the
assertion existed, in `test_config_merge_notes_localised.py`, but only
over keys beginning `config_note_`. A key outside that prefix crossed the
same way was caught by nothing. It is catalogue-wide here.

Version: v1.8.0
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations.messages import MESSAGES

# Characters Spanish writes and English does not. Deliberately narrow: the
# catalogue's English uses em dashes, checkmarks and ellipses, and those are
# not evidence of anything.
SPANISH_ORTHOGRAPHY = re.compile(r'[áéíóúüñÁÉÍÓÚÜÑ¿¡]')


class TestNoSpanishSitsInTheEnglishDictionary:

    def test_no_english_string_is_written_in_spanish(self):
        spanish = sorted(key for key, value in MESSAGES['en'].items()
                         if isinstance(value, str)
                         and SPANISH_ORTHOGRAPHY.search(value))

        assert spanish == []

    def test_the_probe_finds_spanish_when_there_is_some(self):
        """Guards the assertion above against a pattern that matches nothing.

        A regex that had stopped matching would report a clean English
        dictionary for the same reason a clean one does.
        """
        found = [key for key, value in MESSAGES['es'].items()
                 if isinstance(value, str)
                 and SPANISH_ORTHOGRAPHY.search(value)]

        assert len(found) > 50


# Keys whose two languages are legitimately the same string: directory
# names Telar does not translate, a file every repository has, and a line
# that is only a symbol and a placeholder. Named rather than derived, so a
# sixth is a decision someone makes and not a silence.
IDENTICAL_BY_DESIGN = {
    'category_includes', 'category_layouts', 'category_scripts',
    'changelog', 'migration_error',
}


class TestNoKeyCarriesOneStringForTwoLanguages:
    """What English-in-Spanish looks like from outside.

    A value copied from the other dictionary, or never translated, leaves
    one string doing the work of two — which is the shape both halves of a
    crossed pair take once one of them is corrected.
    """

    def test_the_two_languages_differ_wherever_they_should(self):
        same = sorted(key for key, value in MESSAGES['en'].items()
                      if MESSAGES['es'].get(key) == value
                      and key not in IDENTICAL_BY_DESIGN)

        assert same == []

    def test_every_exception_is_still_an_exception(self):
        """The allowlist is not a place to quietly retire a key.

        A name left here after its string was translated would silence
        the check for that key permanently.
        """
        stale = sorted(key for key in IDENTICAL_BY_DESIGN
                       if MESSAGES['es'].get(key) != MESSAGES['en'].get(key))

        assert stale == []


class TestBothDictionariesHoldTheSameKeys:
    """Not language, but the other half of a misplaced insertion.

    A string put in one dictionary and not the other renders as its own
    key name to half the users, which is the visible failure; this is the
    cheap check that was never written down.
    """

    def test_every_english_key_has_spanish(self):
        missing = sorted(set(MESSAGES['en']) - set(MESSAGES['es']))

        assert missing == []

    def test_no_spanish_key_is_without_english(self):
        """The direction that produces a key nobody can reach.

        `get_message` falls back to English, so a Spanish-only key is dead
        weight rather than a crash — and dead weight is what nobody finds.
        """
        orphans = sorted(set(MESSAGES['es']) - set(MESSAGES['en']))

        assert orphans == []

    @pytest.mark.parametrize('language', ['en', 'es'])
    def test_every_value_is_a_string(self, language):
        wrong = sorted(key for key, value in MESSAGES[language].items()
                       if not isinstance(value, str))

        assert wrong == []
