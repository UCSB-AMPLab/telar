"""Unit Tests for config_merge's Notes Reaching the Reader in Their Language

`config_merge` decides what happens to each setting when a site's
`_config.yml` is rewritten from the one the new version ships, and it
returns a note for every case it refused to guess at. Those notes become
lines in the upgrade summary, beside forty-odd others that have been
bilingual since v1.6.2 — and they were the last English ones left, so a
Spanish site read its own configuration report half in English.

The module is pure: it takes two strings and has no site to ask what
language that site is in. So it returns each note as a message key and its
arguments, and the rendering happens at the caller, which has the
migration and therefore the language.

That shape is the thing these tests hold. A note built as a finished
string anywhere in the module is a line that cannot be translated, and it
would look completely normal.

Version: v1.8.0
"""

import ast
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations import config_merge
from migrations.messages import MESSAGES, get_message

MODULE = os.path.join(os.path.dirname(__file__), '..', '..',
                      'scripts', 'migrations', 'config_merge.py')

NOTE_KEYS = [key for key in MESSAGES['en'] if key.startswith('config_note_')]


class TestEveryNoteIsAKeyRatherThanASentence:

    def test_the_module_appends_no_literal_note(self):
        """Read off the syntax, because a literal is invisible at runtime.

        A note only appears when the site's configuration hits that exact
        case, so a suite that never builds such a site would never see the
        English one either.
        """
        tree = ast.parse(open(MODULE, encoding='utf-8').read())

        literals = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == 'append'):
                continue
            if not (isinstance(func.value, ast.Name)
                    and func.value.id == 'notes'):
                continue
            for argument in node.args:
                if isinstance(argument, (ast.Constant, ast.JoinedStr)):
                    literals.append(ast.dump(argument)[:60])

        assert literals == []

    def test_every_note_a_merge_produces_names_a_key_we_have(self):
        """The other half: a key that does not exist renders as its name."""
        template = ("title: Demo\nnav:\n  - one\nplugins:\n  - a\n"
                    "google_sheets:\n  enabled: false\n")
        site = ("title: Mine\nnav: just-a-value\nplugins:\n  - a\n  - b\n"
                "google_sheets:\n  enabled: true\nmi_ajuste: propio\n")

        _, notes = config_merge.merge(template, site)

        assert notes, 'the fixture should provoke at least one note'
        for note in notes:
            assert note[0] in MESSAGES['en'], note

    def test_a_note_is_a_key_and_its_arguments(self):
        """Rendering is `get_message(lang, *note)`, so shape is contract."""
        template = "title: Demo\nnav:\n  - one\n"
        site = "title: Mine\nnav: just-a-value\n"

        _, notes = config_merge.merge(template, site)

        for note in notes:
            assert isinstance(note, tuple), note
            assert all(isinstance(part, str) for part in note), note


@pytest.mark.parametrize('key', NOTE_KEYS)
class TestBothLanguagesCarryEveryNote:

    def test_the_key_exists_in_spanish(self, key):
        assert key in MESSAGES['es'], key

    def test_the_two_languages_take_the_same_arguments(self, key):
        """A placeholder count that differs crashes one language only.

        The Spanish is written from the meaning rather than the words, so
        a rewritten clause can drop a placeholder while reading perfectly.
        """
        assert MESSAGES['en'][key].count('{}') == MESSAGES['es'][key].count('{}')

    def test_neither_language_is_left_as_a_placeholder(self, key):
        for language in ('en', 'es'):
            assert 'DRAFT' not in MESSAGES[language][key], (language, key)

    def test_the_spanish_is_not_the_english(self, key):
        """What English-only looks like from outside: one string for two."""
        assert MESSAGES['es'][key] != MESSAGES['en'][key], key


class TestTheNotesRenderWhereTheLanguageIs:

    def test_the_arguments_reach_the_rendered_line(self):
        rendered = get_message('es', 'config_note_kept_list_entries',
                               'plugins', 'a, b')

        assert 'plugins' in rendered and 'a, b' in rendered

    def test_both_languages_render_without_a_missing_argument(self):
        """Every note, in both languages, with its placeholders filled."""
        for key in NOTE_KEYS:
            for language in ('en', 'es'):
                count = MESSAGES[language][key].count('{}')
                rendered = get_message(language, key,
                                       *['x'] * count)

                assert '{}' not in rendered, (language, key)
