"""Unit tests for the language of upgrade failures.

The records written into the upgrade summary and the dependency-ensure
console output are localised through messages.py, so a site reads its
failures in its own language. These tests hold the keys in both languages
and, more importantly, hold the one invariant translation could break —
that whether a failure is HARD does not depend on what language the site is
in.

Version: v1.8.0
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar_upgrade as upgrade
from migrations.base import (
    BaseMigration, ChangeStatus, FetchOutcome, FetchResult, coerce_change)
from migrations.messages import MESSAGES, get_message

# The phrase coerce_change reads as a hard failure when a migration returns
# a bare string instead of a ChangeRecord.
SENTINEL = 'Could not fetch'

FAILURE_KEYS = (
    'record_deps_missing',
    'record_regeneration_failed',
    'record_migration_aborted',
    'record_fetch_failed',
    'record_fetch_absent',
    'record_write_rolled_back',
    'deps_installing',
    'deps_no_manifest',
    'deps_pip_failed',
    'deps_pip_timeout',
    'upgrade_reached_version',
    'updated_file',
)


class TestEveryChangeDescriptionIsLocalised:
    """The half of the summary that says what happened to the site's content.

    Headings and counts went through `messages.py` from the start; the lines
    under them were built as English f-strings at the point each change was
    made, so a Spanish site read its own file list in English. These hold
    the closure: a description built as a literal reaches the summary in
    whatever language it was written in, and no later pass can find it.
    """

    def _literal_descriptions(self):
        import ast
        import pathlib
        directory = (pathlib.Path(__file__).resolve().parents[2]
                     / 'scripts' / 'migrations')
        offenders = []
        for path in sorted(directory.rglob('*.py')):
            if path.name == 'messages.py':
                continue
            source = path.read_text(encoding='utf-8')
            for node in ast.walk(ast.parse(source, filename=str(path))):
                if not isinstance(node, ast.Call):
                    continue
                called = (getattr(node.func, 'id', None)
                          or getattr(node.func, 'attr', None))
                if called != 'ChangeRecord':
                    continue
                for keyword in node.keywords:
                    if keyword.arg != 'description':
                        continue
                    value = keyword.value
                    # A name is a description built elsewhere and already
                    # localised there; only a literal written here is a leak.
                    if isinstance(value, (ast.Constant, ast.JoinedStr)):
                        offenders.append('%s:%d' % (path.name, node.lineno))
        return offenders

    def test_no_migration_writes_a_description_as_a_literal(self):
        assert self._literal_descriptions() == []

    @pytest.mark.parametrize('lang', ['en', 'es'])
    def test_every_change_key_exists_in_both_languages(self, lang):
        change_keys = [key for key in MESSAGES['en'] if key.startswith('change_')]

        assert len(change_keys) > 30
        for key in change_keys:
            assert key in MESSAGES[lang], (key, lang)

    def test_the_two_languages_take_the_same_arguments(self):
        """A translation with fewer placeholders drops a path silently."""
        mismatched = [key for key in MESSAGES['en']
                      if key.startswith('change_')
                      and MESSAGES['en'][key].count('{}')
                      != MESSAGES['es'][key].count('{}')]

        assert mismatched == []


class TestTheKeysExist:

    @pytest.mark.parametrize('key', FAILURE_KEYS)
    def test_both_languages_have_it(self, key):
        for lang in ('en', 'es'):
            assert key in MESSAGES[lang], (key, lang)
            assert get_message(lang, key) != key

    @pytest.mark.parametrize('key', FAILURE_KEYS)
    def test_the_two_take_the_same_arguments(self, key):
        """A translation with fewer placeholders drops information silently.

        get_message returns the unformatted string rather than raising when
        the arguments do not line up, so a mismatch here would surface as a
        summary full of braces instead of a crash.
        """
        assert MESSAGES['en'][key].count('{}') == MESSAGES['es'][key].count('{}')

    def test_no_spanish_message_carries_the_sentinel(self):
        """The sentinel is English by construction.

        A key defined in both languages with the English half carrying the
        phrase and the Spanish half not would downgrade a failed fetch to a
        soft applied change on Spanish sites only.
        """
        carriers = [key for key, value in MESSAGES['es'].items()
                    if SENTINEL in value]

        assert carriers == []

    def test_the_dead_key_is_gone(self):
        for lang in ('en', 'es'):
            assert 'fetch_warning' not in MESSAGES[lang]


class TestTheFailureMessageSaysWhereTheSiteIs:
    """A chain that stops part-way has still moved the site.

    Each migration stamps its own to_version as it completes, so the version
    in _config.yml after a failed run is the last hop that finished. Telling
    the user nothing changed suppresses the re-run that would finish the job,
    and makes a subsequently failing build look unrelated to the upgrade.
    """

    def _site_at(self, tmp_path, version, lang='en'):
        (tmp_path / '_config.yml').write_text(
            'telar_language: "%s"\ntelar:\n  version: "%s"\n' % (lang, version),
            encoding='utf-8')
        return str(tmp_path)

    def test_it_names_the_version_reached_when_the_chain_progressed(self, tmp_path, capsys):
        repo = self._site_at(tmp_path, '0.6.3-beta')
        upgrade._report_state_after_failure(repo, 'en', '0.2.0-beta')

        out = capsys.readouterr().out
        assert '0.6.3-beta' in out
        assert upgrade.LATEST_VERSION in out
        assert 'NOT upgraded' not in out

    def test_it_says_nothing_changed_when_the_chain_never_moved(self, tmp_path, capsys):
        repo = self._site_at(tmp_path, '0.2.0-beta')
        upgrade._report_state_after_failure(repo, 'en', '0.2.0-beta')

        assert 'NOT upgraded' in capsys.readouterr().out

    def test_a_spanish_site_is_told_in_spanish(self, tmp_path, capsys):
        repo = self._site_at(tmp_path, '0.6.3-beta', lang='es')
        upgrade._report_state_after_failure(repo, 'es', '0.2.0-beta')

        out = capsys.readouterr().out
        assert out.strip() == get_message(
            'es', 'upgrade_reached_version', '0.6.3-beta', upgrade.LATEST_VERSION).strip()

    def test_no_stop_message_claims_the_site_is_unchanged(self):
        # The per-migration stop line is true of that migration and false of
        # the chain, which is where the claim did its damage.
        for lang in ('en', 'es'):
            stopped = get_message(lang, 'migration_stopped')
            assert 'unchanged' not in stopped
            assert 'sin cambios' not in stopped


class TestClassificationIsLanguageIndependent:
    """The invariant translating the records could have broken."""

    def _migration(self, root):
        class _M(BaseMigration):
            from_version = '1.0.0'
            to_version = '1.1.0'
            description = 'test'
            _TARGET_TAG = 'v1.1.0'

            def check_applicable(self):
                return True

            def apply(self):
                return []

            def _fetch_with_retry(self, path, branch):
                # A transient failure: this class is about the record a
                # stop-the-chain failure carries, not about the structural
                # one, which is soft and does not stop anything.
                return FetchResult(None, FetchOutcome.TRANSIENT, 'timed out')

        return _M(str(root))

    @pytest.mark.parametrize('lang,expected_start', [
        ('en', 'Could not fetch'),
        ('es', 'No se pudo descargar'),
    ])
    def test_a_failed_fetch_is_hard_in_either_language(self, tmp_path, lang,
                                                       expected_start):
        (tmp_path / '_config.yml').write_text(f'telar_language: "{lang}"\n',
                                             encoding='utf-8')
        migration = self._migration(tmp_path)

        _, failed, flagged = migration._fetch_all_staged({'README.md': 'Readme'},
                                                         tag='v1.1.0')

        assert flagged == []
        assert len(failed) == 1
        assert failed[0].status == ChangeStatus.FAILED
        assert failed[0].severity == 'hard'
        assert failed[0].description.startswith(expected_start)

    def test_the_record_names_the_version_not_the_ref(self, tmp_path):
        """`main` is what the ref is when a migration declares no tag.

        A site owner can act on a version number. The ref the fetch used is
        a maintainer's detail, and `main` in particular tells them nothing.
        """
        (tmp_path / '_config.yml').write_text('telar_language: "en"\n',
                                              encoding='utf-8')
        migration = self._migration(tmp_path)

        _, failed, _ = migration._fetch_all_staged({'README.md': 'Readme'})

        assert 'main' not in failed[0].description
        assert migration.to_version in failed[0].description

    def test_a_bare_string_is_still_classified_in_english(self):
        """Migrations that return strings keep the English phrase.

        coerce_change has nothing but the text to go on, so the phrase is
        the classification there and cannot be translated.
        """
        record = coerce_change('Warning: Could not fetch README.md from GitHub')

        assert record.status == ChangeStatus.FAILED
        assert record.severity == 'hard'


class TestTheDependencyEnsureStepSpeaksSpanish:

    def _run_on(self, tmp_path, lang, monkeypatch, capsys):
        (tmp_path / '_config.yml').write_text(f'telar_language: "{lang}"\n',
                                             encoding='utf-8')
        # No manifest anywhere, so it takes the branch that cannot install.
        monkeypatch.setattr(upgrade, '_missing_regeneration_imports',
                            lambda: ['nonexistent_pkg'])
        monkeypatch.setattr(upgrade.Path, 'is_file', lambda self: False)

        ok, missing = upgrade._ensure_regeneration_dependencies(str(tmp_path))

        return ok, missing, capsys.readouterr().out

    def test_it_warns_in_spanish(self, tmp_path, monkeypatch, capsys):
        ok, missing, out = self._run_on(tmp_path, 'es', monkeypatch, capsys)

        assert ok is False
        assert missing == ['nonexistent_pkg']
        assert 'no se pueden instalar las dependencias que faltan' in out
        assert 'nonexistent_pkg' in out
        assert 'Warning' not in out

    def test_it_warns_in_english(self, tmp_path, monkeypatch, capsys):
        ok, _, out = self._run_on(tmp_path, 'en', monkeypatch, capsys)

        assert ok is False
        assert 'cannot install the missing dependencies' in out
        assert 'Advertencia' not in out


class TestThePerFileRecordsSpeakSpanish:
    """The summary is a file the site commits to its own repository.

    Its headings and counts were localised; the sixty-odd lines under them
    were not, because each was built by interpolating the English annotation
    from the migration's own file map. A record that carries prose cannot be
    localised at render time, so the prose is gone and only the path remains.
    """

    def _migration_at(self, tmp_path, lang):
        (tmp_path / '_config.yml').write_text(
            'telar_language: "%s"\n' % lang, encoding='utf-8')

        class _M(BaseMigration):
            from_version = '1.0'
            to_version = '2.0'
            description = 'fake'

            def check_applicable(self):
                return True

            def apply(self):
                return []

        return _M(str(tmp_path))

    def test_an_applied_record_is_written_in_spanish(self, tmp_path):
        migration = self._migration_at(tmp_path, 'es')
        records = migration._commit_staged({'Gemfile.lock': ('x', 'Ruby dependencies')})

        assert len(records) == 1
        assert records[0].description == 'Gemfile.lock actualizado'

    def test_an_applied_record_is_written_in_english(self, tmp_path):
        migration = self._migration_at(tmp_path, 'en')
        records = migration._commit_staged({'Gemfile.lock': ('x', 'Ruby dependencies')})

        assert records[0].description == 'Updated Gemfile.lock'

    def test_no_record_carries_the_file_map_annotation(self, tmp_path):
        # The annotation is maintainer documentation. It reached the user's
        # summary in English on every site, whatever language the site was in.
        migration = self._migration_at(tmp_path, 'es')
        records = migration._commit_staged(
            {'Gemfile.lock': ('x', 'Ruby dependencies for the Jekyll build')})

        assert 'Ruby dependencies' not in records[0].description

    def test_the_fetch_failure_record_carries_no_annotation_either(self):
        for lang in ('en', 'es'):
            message = get_message(lang, 'record_fetch_failed', 'Gemfile', 'v1.7.0')
            assert 'Gemfile' in message
            assert '{}' not in message


class TestTheSummaryRecordsSpeakSpanish:

    def test_the_missing_dependency_record_is_translated(self):
        record = get_message('es', 'record_deps_missing', 'pandas, yaml')

        assert record.startswith('La regeneración de datos necesita')
        assert 'pandas, yaml' in record
        assert 'requirements.txt' in record

    def test_the_regeneration_failure_record_is_translated(self):
        record = get_message('es', 'record_regeneration_failed')

        assert 'Falló la regeneración de datos' in record
        assert 'a mano' in record

    def test_the_rollback_record_names_the_framework_in_spanish(self):
        """`archivos del marco` is the term the Spanish docs already use."""
        record = get_message('es', 'record_write_rolled_back', 'disco lleno')

        assert 'archivo del marco' in record
        assert 'framework' not in record
