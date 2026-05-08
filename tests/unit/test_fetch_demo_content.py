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

Version: v1.2.1-beta
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from fetch_demo_content import find_best_version, load_config


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
