"""
Unit Tests for fetch_demo_content.py

Tests version-resolution logic for the demo content fetcher. The fetcher
reads a site's `telar.version` from _config.yml and finds the highest
compatible demo bundle on content.telar.org.

Historical context: an earlier Telar Compositor upgrade flow wrote
v-prefixed version strings (e.g., "v1.2.0") into _config.yml. The
compositor bug is fixed, but bad values persist in sites upgraded before
the fix landed. The framework must therefore tolerate a leading `v` so
those sites are not silently broken.

Version: v1.8.0
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar_upgrade
from fetch_demo_content import (
    _SITE_VERSION_RE, find_best_version, load_config)


class TestFindBestVersionHappyPaths:
    def test_exact_match_returned(self):
        assert find_best_version('0.6.1', ['0.6.0', '0.6.1', '0.7.0']) == '0.6.1'

    def test_highest_compatible_returned_when_no_exact(self):
        assert find_best_version('0.6.3', ['0.6.0', '0.6.1', '0.7.0']) == '0.6.1'

    def test_highest_overall_returned_when_site_newer_than_all(self):
        assert find_best_version('0.8.0', ['0.6.0', '0.7.0']) == '0.7.0'

    def test_none_when_site_older_than_all(self):
        assert find_best_version('0.5.9', ['0.6.0', '0.6.1', '0.7.0']) is None


class TestFindBestVersionWithVPrefix:
    """A leading v/V on the site version must not silently break resolution."""

    def test_lowercase_v_prefix_site_version(self):
        assert find_best_version('v1.2.0', ['1.0.0', '1.1.0', '1.2.0']) == '1.2.0'

    def test_uppercase_v_prefix_site_version(self):
        assert find_best_version('V1.2.0', ['1.0.0', '1.1.0', '1.2.0']) == '1.2.0'

    def test_v_prefix_with_higher_site_than_all_available(self):
        assert find_best_version('v1.5.0', ['1.0.0', '1.1.0']) == '1.1.0'

    def test_v_prefix_in_available_versions_list(self):
        assert find_best_version('1.2.0', ['v1.0.0', 'v1.1.0', 'v1.2.0']) == 'v1.2.0'


class TestFindBestVersionMalformed:
    def test_non_numeric_segment_returns_none(self):
        assert find_best_version('1.x.0', ['1.0.0', '1.1.0']) is None

    def test_empty_string_returns_none(self):
        assert find_best_version('', ['1.0.0']) is None

    def test_malformed_entries_in_available_skipped(self):
        # Garbage entries must not break resolution; valid candidates still win.
        assert find_best_version('1.2.0', ['1.0.0', 'not-a-version', '1.1.0']) == '1.1.0'


class TestLoadConfigVersionNormalisation:
    """
    `load_config` must return a bare numeric version regardless of how it was
    written into `_config.yml`. Otherwise downstream f-strings produce
    `vv1.2.0` in log lines and `https://content.telar.org/demos/vv1.2.0/...`
    in fallback bundle URLs (which 404 if `versions.json` is unreachable).
    """

    def _write_config(self, tmp_path, telar_version):
        config_path = tmp_path / '_config.yml'
        config_path.write_text(
            "telar_language: en\n"
            "story_interface:\n"
            "  include_demo_content: true\n"
            "telar:\n"
            f"  version: \"{telar_version}\"\n",
            encoding='utf-8',
        )
        return config_path

    def test_lowercase_v_prefix_stripped(self, tmp_path, monkeypatch):
        self._write_config(tmp_path, 'v1.2.0')
        monkeypatch.chdir(tmp_path)
        assert load_config()['version'] == '1.2.0'

    def test_uppercase_v_prefix_stripped(self, tmp_path, monkeypatch):
        self._write_config(tmp_path, 'V1.2.0')
        monkeypatch.chdir(tmp_path)
        assert load_config()['version'] == '1.2.0'

    def test_v_prefix_with_beta_suffix_stripped(self, tmp_path, monkeypatch):
        # Both -beta suffix and v prefix should be stripped.
        self._write_config(tmp_path, 'v1.2.0-beta')
        monkeypatch.chdir(tmp_path)
        assert load_config()['version'] == '1.2.0'

    def test_bare_version_unchanged(self, tmp_path, monkeypatch):
        self._write_config(tmp_path, '1.2.0')
        monkeypatch.chdir(tmp_path)
        assert load_config()['version'] == '1.2.0'


# Spellings both readers have an opinion about. Mixed deliberately: a corpus
# of only well-formed versions makes any two grammars agree.
SHARED_CORPUS = [
    '1.2.0', 'v1.2.0', 'V1.2.0', '0.9.4-beta', 'v0.9.4-beta', '0.2.0-beta',
    'vv1.2.0', 'VV1.2.0', '01.2.0', '1.02.0', '1.2.00', '1.2', '1.2.0.1',
    '1.2.0 ', ' 1.2.0', '1.2.0\n', '1.2.0-alpha', '1.2.0-BETA', '1.2.0beta',
    'v', '', 'release-1.2.0', '١.٢.٠', '1.٢.0',
]


class TestTheSiteVersionGrammarRefusesWhatTheEngineRefuses:
    """Two readers of one `_config.yml` key, in two scripts.

    This one decides which demo bundle to fetch; the upgrade engine decides
    which migration chain to run. They do not share code — the engine pulls
    in the whole migration registry, which a build-time fetcher has no
    business importing — so what keeps them honest is that they answer the
    same question the same way.

    They disagreed. `lstrip('vV')` strips every leading v, so this script
    read `vv1.6.2` as 1.6.2 and fetched that bundle, while the engine
    refused the same string as unreadable.
    """

    @pytest.mark.parametrize('value', SHARED_CORPUS)
    def test_both_readers_accept_or_refuse_together(self, value):
        by_fetcher = _SITE_VERSION_RE.fullmatch(value) is not None
        by_engine = telar_upgrade._canonical_version(value) is not None

        assert by_fetcher == by_engine, value

    def test_the_corpus_contains_both_answers(self):
        """A corpus everything passes proves nothing about agreement."""
        accepted = [v for v in SHARED_CORPUS
                    if _SITE_VERSION_RE.fullmatch(v) is not None]

        assert 5 <= len(accepted) < len(SHARED_CORPUS)


class TestVersionsThisScriptWillNotFetchFor:
    """Refusing skips the demo fetch, which is optional. Guessing picks a
    bundle for a version the site does not have."""

    def _write_config(self, tmp_path, telar_version):
        (tmp_path / '_config.yml').write_text(
            "telar_language: en\n"
            "story_interface:\n"
            "  include_demo_content: true\n"
            "telar:\n"
            f'  version: "{telar_version}"\n',
            encoding='utf-8')

    @pytest.mark.parametrize('value', ['vv1.2.0', '01.2.0', '1.2', '1.2.0-alpha'])
    def test_a_version_outside_the_grammar_skips_the_fetch(
            self, tmp_path, monkeypatch, value):
        self._write_config(tmp_path, value)
        monkeypatch.chdir(tmp_path)

        assert load_config() is None

    def test_the_warning_names_what_was_written_not_what_was_left_of_it(
            self, tmp_path, monkeypatch, capsys):
        """The old code reported the value after stripping, so a user was
        told it could not parse a string they had never written."""
        self._write_config(tmp_path, 'vv1.2.0')
        monkeypatch.chdir(tmp_path)

        load_config()

        assert 'vv1.2.0' in capsys.readouterr().out


class TestARemoteIndexRowThatIsNotAVersion:

    def test_a_repeated_prefix_row_is_discarded(self):
        """It used to collapse onto a real version and win the comparison,
        and the returned string is then interpolated into the bundle URL."""
        assert find_best_version('1.6.2', ['1.6.0', 'vv1.6.2']) == '1.6.0'

    def test_a_single_prefix_row_is_still_usable(self):
        assert find_best_version('1.6.2', ['1.0.0', 'v1.6.1']) == 'v1.6.1'
