"""
Unit Tests for migrations/v161_to_v162.py

v1.6.2 carries the site-level pieces of the upgrade-environment repair
(wave 1, already on the release branch) forward to existing sites: the
package.json/package-lock.json pair (fetched atomically as a pair — the
lockfile is meaningless without its manifest) and removal of the now-dead
.github/dependabot.yml (soft-fail, since GitHub's workflow-file write
restriction does not cover this path but a removal failure still shouldn't
sink the upgrade). These tests guard:

  - the delivery set (FRAMEWORK_FILES): exactly the package.json/
    package-lock.json pair, no workflow files, the upgrade engine excluded;
  - fail-closed ordering: a failed framework fetch skips the dependabot.yml
    removal phase;
  - dependabot.yml removal: idempotent when absent, recorded when removed,
    soft (not hard) failure when removal raises;
  - metadata + bilingual manual steps;
  - registration completeness in scripts/upgrade.py (imported, appended to
    MIGRATIONS, chain terminus reaches LATEST_VERSION) — the same "three
    hand-synced places" gap that v1.6.1 itself had to repair.

Network-dependent framework fetches are not exercised here — those are
covered by the upgrade.py integration tests.

Version: v1.6.2
"""

import sys
import os
import errno

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations.v161_to_v162 import Migration161to162, FRAMEWORK_FILES, DEPENDABOT_PATH
from migrations.base import ChangeRecord, ChangeStatus

import upgrade


# ---------- Delivery set (FRAMEWORK_FILES) ----------

class TestFrameworkFilesDeliverySet:
    """The package.json/package-lock.json pair is the heart of this
    migration's file delivery; these guards encode why it looks the way it
    does."""

    def test_exactly_the_package_pair(self):
        assert set(FRAMEWORK_FILES.keys()) == {'package.json', 'package-lock.json'}

    def test_no_workflow_files_delivered(self):
        """Workflow files must never be delivered: the upgrade GITHUB_TOKEN has
        no `workflows: write`, so a push touching .github/workflows/* is
        rejected wholesale. upgrade.yml/telar-tests.yml are manual steps."""
        offenders = [p for p in FRAMEWORK_FILES if p.startswith('.github/workflows/')]
        assert offenders == [], f"workflow files must not be in FRAMEWORK_FILES: {offenders}"

    def test_upgrade_engine_not_delivered(self):
        """The migration engine ships via the verified tarball, not per-file."""
        for path in (
            'scripts/upgrade.py',
            'scripts/migrations/base.py',
            'scripts/migrations/messages.py',
            'scripts/migrations/v161_to_v162.py',
        ):
            assert path not in FRAMEWORK_FILES, f"upgrade-engine file should not be delivered: {path}"

    def test_descriptions_are_nonempty(self):
        for path, desc in FRAMEWORK_FILES.items():
            assert isinstance(desc, str) and desc.strip(), f"empty description for {path}"


# ---------- Fail-closed ordering ----------

class TestFailClosedOrdering:
    """A failed framework fetch must short-circuit before dependabot.yml is
    touched, so a half-applied upgrade never deletes a file it shouldn't."""

    def test_dependabot_removal_skipped_when_framework_fetch_fails(self, tmp_path, monkeypatch):
        m = Migration161to162(str(tmp_path))

        monkeypatch.setattr(m, '_update_framework_files', lambda: [
            ChangeRecord(description='Could not fetch package.json', status=ChangeStatus.FAILED, severity='hard')
        ])
        removal_called = {'hit': False}

        def _spy():
            removal_called['hit'] = True
            return []
        monkeypatch.setattr(m, '_remove_dependabot', _spy)

        changes = m.apply()
        assert removal_called['hit'] is False
        assert any(c.status == ChangeStatus.FAILED for c in changes)

    def test_dependabot_removal_runs_when_framework_fetch_succeeds(self, tmp_path, monkeypatch):
        m = Migration161to162(str(tmp_path))
        monkeypatch.setattr(m, '_update_framework_files', lambda: [
            ChangeRecord(description='Updated package.json', status=ChangeStatus.APPLIED, severity='hard')
        ])
        removal_called = {'hit': False}

        def _spy():
            removal_called['hit'] = True
            return []
        monkeypatch.setattr(m, '_remove_dependabot', _spy)

        m.apply()
        assert removal_called['hit'] is True


# ---------- dependabot.yml removal ----------

class TestRemoveDependabot:
    def test_absent_is_a_noop(self, tmp_path):
        m = Migration161to162(str(tmp_path))
        out = m._remove_dependabot()
        assert len(out) == 1
        assert out[0].status == ChangeStatus.APPLIED
        assert 'already absent' in out[0].description

    def test_present_is_removed_and_recorded(self, tmp_path):
        gh_dir = tmp_path / '.github'
        gh_dir.mkdir()
        (gh_dir / 'dependabot.yml').write_text('version: 2\n', encoding='utf-8')

        m = Migration161to162(str(tmp_path))
        out = m._remove_dependabot()

        assert not (gh_dir / 'dependabot.yml').exists()
        assert len(out) == 1
        assert out[0].status == ChangeStatus.APPLIED
        assert 'Removed' in out[0].description
        assert DEPENDABOT_PATH in out[0].description

    def test_removal_failure_is_soft_not_hard(self, tmp_path, monkeypatch):
        gh_dir = tmp_path / '.github'
        gh_dir.mkdir()
        (gh_dir / 'dependabot.yml').write_text('version: 2\n', encoding='utf-8')

        def _boom(path):
            raise OSError(errno.EACCES, 'Permission denied')
        monkeypatch.setattr(os, 'remove', _boom)

        m = Migration161to162(str(tmp_path))
        out = m._remove_dependabot()

        assert len(out) == 1
        assert out[0].status == ChangeStatus.FAILED
        assert out[0].severity == 'soft'
        assert 'Non-fatal' in out[0].description


# ---------- Metadata + manual steps ----------

class TestMigrationMetadata:
    def test_from_to_versions(self):
        m = Migration161to162('/tmp')
        assert m.from_version == '1.6.1'
        assert m.to_version == '1.6.2'

    def test_pinned_to_release_tag(self):
        assert Migration161to162('/tmp')._TARGET_TAG == 'v1.6.2'

    def test_check_applicable_always_true(self):
        assert Migration161to162('/tmp').check_applicable() is True

    def test_manual_steps_bilingual_count(self):
        m = Migration161to162('/tmp')
        assert len(m._get_manual_steps_en()) == 3
        assert len(m._get_manual_steps_es()) == 3
        for step in m._get_manual_steps_en() + m._get_manual_steps_es():
            assert 'doc_url' in step
            assert step['description'].strip()

    def test_workflow_steps_name_both_files_and_frame_as_recommended(self):
        """The upgrade.yml step must be framed as recommended (not urgent),
        since future upgrades keep working without it."""
        en = Migration161to162('/tmp')._get_manual_steps_en()
        upgrade_step = en[0]['description']
        tests_step = en[1]['description']
        assert '.github/workflows/upgrade.yml' in upgrade_step
        assert '.github/workflows/telar-tests.yml' in tests_step
        assert 'recommended' in upgrade_step.lower()
        assert 'not urgent' in upgrade_step.lower()

    def test_dependabot_step_is_informational(self):
        for desc in (
            Migration161to162('/tmp')._get_manual_steps_en()[2]['description'],
            Migration161to162('/tmp')._get_manual_steps_es()[2]['description'],
        ):
            assert 'dependabot.yml' in desc

    def test_spanish_step_uses_tu_imperative(self):
        """Colombian-Spanish styleguide: tu-imperative voice, not usted."""
        es = Migration161to162('/tmp')._get_manual_steps_es()
        joined = ' '.join(s['description'] for s in es)
        # Tu-imperative markers from the approved strings; usted forms are absent.
        assert 'Actualiza' in joined
        assert 'copia el' in joined
        assert 'usted' not in joined.lower()


# ---------- Registration completeness (upgrade.py) ----------

class TestRegistrationCompleteness:
    """v1.6.1 itself exists to repair a registration gap in v1.6.0 — these
    guards make sure v1.6.2 doesn't reintroduce that class of bug across the
    three hand-synced places (import block, MIGRATIONS, LATEST_VERSION)."""

    def test_imported_in_upgrade_module(self):
        assert hasattr(upgrade, 'Migration161to162')
        assert upgrade.Migration161to162 is Migration161to162

    def test_appended_to_migrations_list(self):
        assert Migration161to162 in upgrade.MIGRATIONS

    def test_is_last_in_migrations_list(self):
        assert upgrade.MIGRATIONS[-1] is Migration161to162

    def test_latest_version_matches_chain_terminus(self):
        assert upgrade.LATEST_VERSION == Migration161to162.to_version == '1.6.2'

    def test_full_chain_resolves_to_latest_version(self):
        """Walking every migration's from_version -> to_version link from the
        very first entry must land exactly on LATEST_VERSION, with no gaps."""
        current = upgrade.MIGRATIONS[0].from_version
        for MigrationClass in upgrade.MIGRATIONS:
            assert MigrationClass.from_version == current, (
                f"chain gap: expected a migration from {current}, "
                f"found one from {MigrationClass.from_version}"
            )
            current = MigrationClass.to_version
        assert current == upgrade.LATEST_VERSION
