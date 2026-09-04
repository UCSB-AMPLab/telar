"""
Unit Tests for version canonicalisation in scripts/upgrade.py

Migrations declare bare from_version literals ("0.9.4-beta", "1.6.2") and
get_migration_path dispatches on exact string equality, so a site whose
_config.yml holds a v-prefixed spelling matches no migration and is told its
version is unsupported. A site upgraded by an earlier Telar Compositor flow
carried `version: "v0.9.4-beta"` in its `_config.yml`. The same mismatch
defeats the already-up-to-date check in main(), which compares
the detected value against LATEST_VERSION before any migration lookup runs —
a current site spelled "v1.6.2" is reported unsupported too.

The value is therefore canonicalised at ingestion, inside
detect_current_version, so every downstream consumer (the equality check, the
migration chain, UPGRADE_SUMMARY.md, UPGRADE_STATE.json) sees one form. The
grammar is exact and finite: an optional single git-tag prefix over
MAJOR.MINOR.PATCH with the -beta suffix preserved, since "0.9.4-beta" and
"0.9.4" are distinct chain keys. Anything outside the grammar is reported and
passed through unchanged, never repaired — repair guesses at intent and can
silently name a different real version.

Version: v1.7.0
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar_upgrade as upgrade
from migrations.base import BaseMigration


# Every version literal the migration chain dispatches on, read off the live
# registry so the corpus grows with the chain rather than being retyped here.
# Every version the chain can be entered from or land on. A migration that
# covers several releases contributes all of them, so consolidating the
# registry does not quietly shrink what these tests cover.
CHAIN_VERSIONS = sorted(
    {v for M in upgrade.MIGRATIONS for v in M.entry_version_list()}
    | {M.to_version for M in upgrade.MIGRATIONS}
)


def _spellings(version):
    """The three spellings the grammar accepts for one version."""
    return [version, f"v{version}", f"V{version}"]


def _write_config(tmp_path, body):
    """Write a minimal Telar _config.yml and return the repo root as a string."""
    (tmp_path / '_config.yml').write_text(body, encoding='utf-8')
    return str(tmp_path)


def _config_with_version(tmp_path, raw_version):
    return _write_config(tmp_path, (
        "telar_language: en\n"
        "telar:\n"
        f"  version: {raw_version}\n"
        '  release_date: "2026-07-11"\n'
    ))


def _mig_class(frm, to, applicable=True):
    # Subclasses BaseMigration so the double carries the same contract the
    # dispatcher relies on, rather than a hand-copied subset of it.
    class _Mig(BaseMigration):
        from_version = frm
        to_version = to

        def check_applicable(self):
            return applicable

        def apply(self):
            return []

        def __repr__(self):
            return f"{frm}->{to}"

    return _Mig


class TestGrammarAccepts:
    """Accepted spellings canonicalise to the bare chain literal."""

    def test_bare_stable_version_unchanged(self):
        assert upgrade._canonical_version('1.6.2') == '1.6.2'

    def test_bare_beta_version_keeps_suffix(self):
        # "0.9.4-beta" and "0.9.4" are distinct chain keys; the suffix survives.
        assert upgrade._canonical_version('0.9.4-beta') == '0.9.4-beta'

    def test_lowercase_v_prefix_stripped(self):
        assert upgrade._canonical_version('v0.9.4-beta') == '0.9.4-beta'

    def test_uppercase_v_prefix_stripped(self):
        assert upgrade._canonical_version('V0.9.4-beta') == '0.9.4-beta'

    def test_v_prefixed_current_version(self):
        assert upgrade._canonical_version('v1.6.2') == '1.6.2'

    def test_chain_head_and_fallback_literal(self):
        assert upgrade._canonical_version('0.2.0-beta') == '0.2.0-beta'

    def test_beta_stable_boundary_literal(self):
        assert upgrade._canonical_version('1.0.0-beta') == '1.0.0-beta'


class TestGrammarRejects:
    """Everything outside the grammar is rejected rather than repaired."""

    @pytest.mark.parametrize('value', ['vv1.6.2', 'VV1.6.2', 'vV1.6.2'])
    def test_repeated_prefix_rejected(self, value):
        # lstrip('vV') would collapse these onto the live version 1.6.2.
        assert upgrade._canonical_version(value) is None

    def test_trailing_newline_rejected(self):
        # re.match(r'^...$') accepts this and silently trims the newline,
        # because $ matches before a final newline. Only fullmatch rejects it.
        assert upgrade._canonical_version('1.6.2\n') is None

    def test_leading_zero_component_rejected(self):
        # A \d+ component would accept this and canonicalise it to itself —
        # an "accepted" string that can never match a chain literal.
        assert upgrade._canonical_version('01.6.2') is None

    @pytest.mark.parametrize('value', ['1.6.2 ', ' 1.6.2', '1.6.2\t', '0.2.0-beta '])
    def test_whitespace_padding_rejected(self, value):
        assert upgrade._canonical_version(value) is None

    def test_empty_string_rejected(self):
        assert upgrade._canonical_version('') is None

    @pytest.mark.parametrize('value', ['v', 'V'])
    def test_prefix_without_body_rejected(self, value):
        assert upgrade._canonical_version(value) is None

    @pytest.mark.parametrize('value', ['1.6', 'v1.6', '1'])
    def test_short_forms_rejected(self, value):
        # A chain key is exactly three components; no padding, unlike the
        # demo-content fetcher's comparison helper.
        assert upgrade._canonical_version(value) is None

    def test_four_components_rejected(self):
        assert upgrade._canonical_version('1.6.2.1') is None

    @pytest.mark.parametrize('value', ['1.6.2-BETA', '1.6.2-Beta'])
    def test_suffix_case_variants_rejected(self, value):
        assert upgrade._canonical_version(value) is None

    @pytest.mark.parametrize('value', ['1.6.2beta', '1.6.2-beta1', '1.6.2-beta-beta', '-beta'])
    def test_malformed_suffix_rejected(self, value):
        assert upgrade._canonical_version(value) is None

    @pytest.mark.parametrize('value', ['1.6.2-rc1', '1.6.2-alpha'])
    def test_unused_prerelease_suffixes_rejected(self, value):
        # Telar has never shipped these. Widening the grammar is a deliberate
        # act that changes this test alongside the pattern.
        assert upgrade._canonical_version(value) is None

    @pytest.mark.parametrize('value', ['1.6.2+build', 'release-1.6.2', 'x1.6.2', 'None'])
    def test_foreign_shapes_rejected(self, value):
        assert upgrade._canonical_version(value) is None


class TestNonStringInput:
    """YAML decodes unquoted values to non-strings; the regex never sees them."""

    def test_float_rejected(self):
        # Unquoted `version: 1.6` decodes to a float.
        assert upgrade._canonical_version(1.6) is None

    def test_none_rejected(self):
        assert upgrade._canonical_version(None) is None

    def test_int_rejected(self):
        assert upgrade._canonical_version(162) is None


class TestIdempotence:
    """Canonicalising a canonical value must return it unchanged."""

    @pytest.mark.parametrize('version', CHAIN_VERSIONS)
    def test_idempotent_over_every_accepted_spelling(self, version):
        for spelling in _spellings(version):
            once = upgrade._canonical_version(spelling)
            assert once is not None
            assert upgrade._canonical_version(once) == once


class TestChainCoverage:
    """The grammar must accept, unchanged, everything the chain dispatches on."""

    @pytest.mark.parametrize('version', CHAIN_VERSIONS)
    def test_every_chain_literal_is_already_canonical(self, version):
        assert upgrade._canonical_version(version) == version

    def test_every_migration_endpoint_is_canonical(self):
        for MigrationClass in upgrade.MIGRATIONS:
            for entry in MigrationClass.entry_version_list():
                assert upgrade._canonical_version(entry) == entry
            assert upgrade._canonical_version(MigrationClass.to_version) == MigrationClass.to_version

    def test_latest_version_is_canonical(self):
        # main() compares the detected value against LATEST_VERSION directly;
        # a non-canonical constant would stop an up-to-date site short-circuiting.
        assert upgrade._canonical_version(upgrade.LATEST_VERSION) == upgrade.LATEST_VERSION

    def test_target_tags_canonicalise_to_their_chain_version(self):
        # The codebase keeps two spellings on purpose: v-prefixed git tags and
        # bare chain versions. The grammar is the bridge between them.
        tagged = [M for M in upgrade.MIGRATIONS if getattr(M, '_TARGET_TAG', None)]
        assert tagged
        for MigrationClass in tagged:
            assert upgrade._canonical_version(MigrationClass._TARGET_TAG) == MigrationClass.to_version

    def test_no_two_chain_versions_collide(self):
        canonical = {v: upgrade._canonical_version(v) for v in CHAIN_VERSIONS}
        assert len(set(canonical.values())) == len(CHAIN_VERSIONS)

    def test_spellings_group_one_class_per_version(self):
        # The only many-to-one behaviour in the grammar is three spellings of
        # one version collapsing onto that version.
        groups = {}
        for version in CHAIN_VERSIONS:
            for spelling in _spellings(version):
                groups.setdefault(upgrade._canonical_version(spelling), set()).add(spelling)
        assert len(groups) == len(CHAIN_VERSIONS)
        for version, spellings in groups.items():
            assert spellings == set(_spellings(version))


class TestDetectCurrentVersion:
    """Canonicalisation happens at ingestion, so every consumer sees one form."""

    def test_v_prefixed_beta_config_canonicalised(self, tmp_path):
        root = _config_with_version(tmp_path, '"v0.9.4-beta"')
        assert upgrade.detect_current_version(root) == '0.9.4-beta'

    def test_uppercase_prefixed_config_canonicalised(self, tmp_path):
        root = _config_with_version(tmp_path, '"V1.6.2"')
        assert upgrade.detect_current_version(root) == '1.6.2'

    def test_bare_config_value_unchanged(self, tmp_path):
        root = _config_with_version(tmp_path, '"1.6.2"')
        assert upgrade.detect_current_version(root) == '1.6.2'

    def test_v_prefixed_latest_version_reads_as_current(self, tmp_path):
        # main() short-circuits on `from_version == LATEST_VERSION` before any
        # migration lookup; a v-prefixed current site must reach that branch
        # rather than falling through to "no migrations found".
        root = _config_with_version(tmp_path, f'"v{upgrade.LATEST_VERSION}"')
        assert upgrade.detect_current_version(root) == upgrade.LATEST_VERSION

    def test_unrecognized_value_passed_through_with_diagnostic(self, tmp_path, capsys):
        root = _config_with_version(tmp_path, '"vv1.6.2"')
        assert upgrade.detect_current_version(root) == 'vv1.6.2'
        out = capsys.readouterr().out
        assert 'vv1.6.2' in out
        assert 'Unrecognized version' in out

    def test_non_string_value_passed_through_with_diagnostic(self, tmp_path, capsys):
        root = _config_with_version(tmp_path, '1.6')
        assert upgrade.detect_current_version(root) == 1.6
        out = capsys.readouterr().out
        assert 'quote' in out.lower()

    def test_missing_version_key_falls_back(self, tmp_path, capsys):
        root = _write_config(tmp_path, (
            "telar_language: en\n"
            "telar:\n"
            '  release_date: "2026-07-11"\n'
        ))
        assert upgrade.detect_current_version(root) == '0.2.0-beta'
        out = capsys.readouterr().out
        assert 'No version found' in out
        # The warning names the value actually returned, which is bare.
        assert 'v0.2.0-beta' not in out

    def test_missing_config_returns_none(self, tmp_path):
        # A genuine precondition failure must stay distinguishable from a
        # grammar rejection, which shares its exit code but not its meaning.
        assert upgrade.detect_current_version(str(tmp_path)) is None


class TestGetMigrationPathBoundary:
    """get_migration_path stays a plain matcher; normalisation lives upstream."""

    @pytest.fixture
    def patched_chain(self, monkeypatch):
        monkeypatch.setattr(upgrade, 'MIGRATIONS', [
            _mig_class('0.9.4-beta', '1.0.0-beta'),
            _mig_class('1.0.0-beta', '1.1.0'),
        ])
        monkeypatch.setattr(upgrade, 'LATEST_VERSION', '1.1.0')

    def test_canonical_beta_seed_chains(self, patched_chain):
        path = upgrade.get_migration_path('0.9.4-beta', '/tmp')
        assert [m.to_version for m in path] == ['1.0.0-beta', '1.1.0']

    def test_prefixed_seed_finds_no_path(self, patched_chain, capsys):
        # Deliberate: get_migration_path receives an already-canonical string in
        # production because detect_current_version canonicalises at ingestion.
        # A second normalisation here would make two sources of truth.
        path = upgrade.get_migration_path('v0.9.4-beta', '/tmp')
        assert path == []
        assert 'stops at v0.9.4-beta' in capsys.readouterr().out
