"""Unit tests for the language of upgrade failures.

The records written into the upgrade summary and the dependency-ensure
console output are localised through messages.py, so a site reads its
failures in its own language. These tests hold the keys in both languages
and, more importantly, hold the one invariant translation could break —
that whether a failure is HARD does not depend on what language the site is
in.

Version: v1.7.0
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar_upgrade as upgrade
from migrations.base import BaseMigration, ChangeStatus, coerce_change
from migrations.messages import MESSAGES, get_message

# The phrase coerce_change reads as a hard failure when a migration returns
# a bare string instead of a ChangeRecord.
SENTINEL = 'Could not fetch'

FAILURE_KEYS = (
    'record_deps_missing',
    'record_regeneration_failed',
    'record_migration_aborted',
    'record_fetch_failed',
    'record_write_rolled_back',
    'deps_installing',
    'deps_no_manifest',
    'deps_pip_failed',
    'deps_pip_timeout',
)


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
                return None

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

        _, failed = migration._fetch_all_staged({'README.md': 'Readme'},
                                                tag='v1.1.0')

        assert len(failed) == 1
        assert failed[0].status == ChangeStatus.FAILED
        assert failed[0].severity == 'hard'
        assert failed[0].description.startswith(expected_start)

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
