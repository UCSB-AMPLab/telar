"""Unit Tests for the Audience on a Migration's Manual Steps

A manual step says what the user still has to do by hand. Some of them are
only true for people upgrading outside the Compositor, because the
Compositor does the work itself — the workflow-file recopies exist only
because GitHub will not let an automated upgrade write to
`.github/workflows/`, and the Compositor commits those files directly.

The Compositor implements a filter on `audience` and hides steps marked
`local`. Nothing populated the field, so the filter had nothing to act on
and every user was shown every step: three workflow instructions, and inside
the first of them a sentence telling Compositor users to ignore all three.
The prose was carrying what the data should.

These tests hold the field itself. A step that ships untagged is shown to
everyone, which is the behaviour the field was added to stop, so the gap
must fail here rather than on a user's screen.

They also hold the framework's own half of the filter. The Compositor
reads `audience` on its post-upgrade screen; a site upgrading with this
engine had nothing reading it, so every step reached every summary —
including the spreadsheet steps, on sites with no spreadsheet.

Version: v1.8.0
"""

import os
import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar_upgrade as upgrade
from migrations.base import MANUAL_STEP_AUDIENCES


def _site(tmp_path, lang):
    (tmp_path / '_config.yml').write_text(
        'telar_language: "%s"\n' % lang, encoding='utf-8')
    return str(tmp_path)


def _all_steps(repo_root):
    for cls in upgrade.discover_migrations():
        for step in cls(repo_root).get_manual_steps():
            yield cls.__name__, step


@pytest.mark.parametrize('lang', ['en', 'es'])
class TestEveryStepDeclaresItsAudience:
    """Read off live migration objects, not off the source text.

    One migration builds its steps by interpolating module constants, in a
    shape a text scan misses: a regex sweep reported it as having no steps
    at all. The field is checked where the runner reads it instead.
    """

    def test_no_step_ships_untagged(self, tmp_path, lang):
        untagged = [name for name, step in _all_steps(_site(tmp_path, lang))
                    if 'audience' not in step]

        assert untagged == []

    def test_every_audience_is_one_we_defined(self, tmp_path, lang):
        unknown = [(name, step.get('audience'))
                   for name, step in _all_steps(_site(tmp_path, lang))
                   if step.get('audience') not in MANUAL_STEP_AUDIENCES]

        assert unknown == []

    def test_the_two_languages_tag_the_same_steps(self, tmp_path, lang):
        """A step hidden in one language and shown in the other is worse
        than one shown in both: the site's language would decide whether a
        user is told to edit a workflow file."""
        totals = {}
        for language in ('en', 'es'):
            directory = tmp_path / ('site-' + language)
            directory.mkdir()
            root = _site(directory, language)
            totals[language] = sorted(
                (name, step['audience']) for name, step in _all_steps(root))

        assert totals['en'] == totals['es']


class TestEveryStepIsWrittenInTheSitesLanguage:
    """A step exists to be acted on, so it has to be readable.

    The summary as a whole has been bilingual since v0.9.4; the steps
    inside it were left to each migration, and one module never gained the
    branch. A site in Spanish finished its upgrade and was handed two
    instructions in English, which is the half of the summary that asks
    the reader to do something.

    No assertion here can tell whether the Spanish is Spanish. What it can
    see is a module that returns the same text whichever language it is
    asked for, and from the outside that is exactly what English-only
    looks like.
    """

    def _descriptions(self, tmp_path, lang):
        directory = tmp_path / ('site-' + lang)
        directory.mkdir()
        pairs = {}
        for name, step in _all_steps(_site(directory, lang)):
            pairs.setdefault(name, []).append(step['description'])
        return pairs

    def test_no_migration_returns_the_same_steps_in_both_languages(self, tmp_path):
        english = self._descriptions(tmp_path, 'en')
        spanish = self._descriptions(tmp_path, 'es')

        untranslated = sorted(name for name, steps in english.items()
                              if spanish.get(name) == steps)

        assert untranslated == []

    def test_some_migration_has_steps_to_check(self, tmp_path):
        """Guards the test above against a discovery that finds nothing.

        An empty mapping satisfies "no migration is untranslated" without
        any migration having been looked at.
        """
        assert len(self._descriptions(tmp_path, 'en')) >= 10


class TestTheWorkflowRecopiesAreTheLocalOnes:
    """`local` means the Compositor does this step for you, nothing wider.

    Not "who is this step about". A step whose prose already says "if you
    use GitHub Pages" is still `all`: every reader sees it and the prose
    sorts them out. The distinction matters because tagging by subject
    rather than by who must act would start hiding steps from the people
    who have to perform them.
    """

    def _steps(self, tmp_path):
        return list(_all_steps(_site(tmp_path, 'en')))

    def test_every_local_step_is_about_a_workflow_file(self, tmp_path):
        wrong = [name for name, step in self._steps(tmp_path)
                 if step['audience'] == 'local'
                 and '.github/workflows' not in step['description']]

        assert wrong == []

    def test_every_workflow_recopy_is_local(self, tmp_path):
        """The inverse, which is the direction that hurts a user.

        A workflow step left `all` shows a Compositor user an instruction
        they cannot act on and do not need.
        """
        wrong = [name for name, step in self._steps(tmp_path)
                 if '.github/workflows' in step['description']
                 and 'Copy raw contents' in step['description']
                 and step['audience'] != 'local']

        assert wrong == []

    def test_more_than_one_audience_is_in_use(self, tmp_path):
        """Guards against a sweep that tagged everything one way."""
        audiences = {step['audience'] for _, step in self._steps(tmp_path)}

        assert {'all', 'local'} <= audiences

    def test_the_sheets_steps_are_tagged_for_sheets(self, tmp_path):
        """The Compositor hides these unless the site pulls from Sheets.

        A step that tells someone to add columns to a spreadsheet they do
        not have is noise, and noise in a post-upgrade checklist is what
        makes people stop reading the rest of it.
        """
        wrong = [name for name, step in self._steps(tmp_path)
                 if 'Google Sheets' in step['description']
                 and step['audience'] != 'google-sheets']

        assert wrong == []


class TestTheEngineFiltersItsOwnSummary:
    """`_visible_manual_steps` is the framework's half of the contract.

    Populating the field and leaving only the Compositor to read it ships
    half a feature: the data exists, one of its two consumers uses it, and
    nothing looks wrong.
    """

    def _steps(self, audiences):
        class _M:
            def __init__(self, values):
                self._values = values

            def get_manual_steps(self):
                return [{'description': 'step for %s' % value,
                         'audience': value} for value in self._values]

        return [_M(audiences)]

    def test_a_sheets_step_is_hidden_from_a_site_without_sheets(self):
        visible = upgrade._visible_manual_steps(
            self._steps(['google-sheets']), sheets_enabled=False)

        assert visible == []

    def test_a_sheets_step_is_shown_to_a_site_with_sheets(self):
        visible = upgrade._visible_manual_steps(
            self._steps(['google-sheets']), sheets_enabled=True)

        assert len(visible) == 1

    @pytest.mark.parametrize('audience', ['all', 'local', 'compositor'])
    def test_every_other_value_is_shown_either_way(self, audience):
        """`local` in particular cannot be filtered here.

        It means the Compositor does this step for you, and a site running
        this engine is by definition not being upgraded by the Compositor,
        so every `local` step is addressed to whoever reads this summary.
        """
        for enabled in (True, False):
            visible = upgrade._visible_manual_steps(
                self._steps([audience]), sheets_enabled=enabled)

            assert len(visible) == 1, (audience, enabled)

    def test_an_unknown_audience_errs_towards_the_reader(self):
        """A step nobody can see is the failure the field exists to prevent."""
        visible = upgrade._visible_manual_steps(
            self._steps([None, 'something-new']), sheets_enabled=False)

        assert len(visible) == 2

    def test_the_summary_uses_the_filter(self, tmp_path):
        summary = upgrade.generate_checklist(
            migrations=self._steps(['google-sheets', 'all']),
            all_changes=[], from_version='1.0.0', to_version='1.1.0',
            sheets_enabled=False)

        assert 'step for all' in summary
        assert 'step for google-sheets' not in summary

    def test_a_caller_that_does_not_know_shows_everything(self):
        """The default is the direction that cannot hide a needed step."""
        summary = upgrade.generate_checklist(
            migrations=self._steps(['google-sheets']),
            all_changes=[], from_version='1.0.0', to_version='1.1.0')

        assert 'step for google-sheets' in summary


class TestReadingWhetherTheSiteUsesSheets:

    def _config(self, tmp_path, text):
        (tmp_path / '_config.yml').write_text(text, encoding='utf-8')
        return str(tmp_path)

    def test_enabled_is_true(self, tmp_path):
        root = self._config(tmp_path, 'google_sheets:\n  enabled: true\n')

        assert upgrade._site_uses_google_sheets(root) is True

    def test_disabled_is_false(self, tmp_path):
        root = self._config(tmp_path, 'google_sheets:\n  enabled: false\n')

        assert upgrade._site_uses_google_sheets(root) is False

    def test_absent_section_is_false(self, tmp_path):
        root = self._config(tmp_path, 'telar_language: "en"\n')

        assert upgrade._site_uses_google_sheets(root) is False

    def test_unreadable_config_is_false_rather_than_an_exception(self, tmp_path):
        """A summary is not worth failing a completed upgrade over."""
        root = self._config(tmp_path, 'google_sheets: [unclosed\n')

        assert upgrade._site_uses_google_sheets(root) is False
