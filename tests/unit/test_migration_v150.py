"""
Unit Tests for migrations/v140_to_v150.py

v1.5.0 is a robustness/security release with no user-content transforms, so
this migration only delivers framework files, re-ensures the vendored-asset
.gitignore negation, and surfaces bilingual manual steps. These tests guard:

  - the delivery set (FRAMEWORK_FILES): no workflow files (the upgrade token
    cannot push them — including one would fail the whole upgrade), the
    delivery-critical files are present, and the build-pipeline import closure
    is satisfied;
  - fail-closed ordering: a failed framework fetch skips the .gitignore phase;
  - .gitignore re-ensure behaviour;
  - metadata + bilingual manual steps.

Network-dependent framework fetches are not exercised here — those are covered
by the upgrade.py integration tests.

Version: v1.5.0
"""

import sys
import os

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations.v140_to_v150 import Migration140to150, FRAMEWORK_FILES
from migrations.base import ChangeRecord, ChangeStatus


# ---------- Delivery set (FRAMEWORK_FILES) ----------

class TestFrameworkFilesDeliverySet:
    """The delivered file set is the heart of this migration; these guards
    encode the decisions made when it was built."""

    def test_no_workflow_files_delivered(self):
        """Workflow files must never be delivered: the upgrade GITHUB_TOKEN has
        no `workflows: write`, so a push touching .github/workflows/* is
        rejected wholesale — it would break the entire upgrade, not just the
        file. upgrade.yml/build.yml are handled as a manual step instead."""
        offenders = [p for p in FRAMEWORK_FILES if p.startswith('.github/workflows/')]
        assert offenders == [], f"workflow files must not be in FRAMEWORK_FILES: {offenders}"

    def test_delivery_critical_files_present(self):
        """Files whose absence breaks a fork after upgrade."""
        required = [
            # Vendored WaveSurfer — the CDN loader is gone; without these,
            # audio cards 404 on the local path.
            'assets/vendor/wavesurfer/wavesurfer.min.js',
            'assets/vendor/wavesurfer/plugins/regions.min.js',
            # Theme-button text fix that missed the v1.4.0 tag — tag-pinned
            # forks are still broken without it.
            '_sass/_layout.scss',
            # Rebuilt story bundle (what story pages actually load).
            'assets/js/telar-story.js',
        ]
        for path in required:
            assert path in FRAMEWORK_FILES, f"missing delivery-critical file: {path}"

    def test_build_pipeline_import_closure(self):
        """Every new cross-module import introduced in v1.5.0 points at a
        delivered file. Delivering an importer without its new dependency would
        break each fork's build (ImportError at build time)."""
        # pipeline_utils is imported by the fetch scripts; media_type by the
        # collection/search/object pipeline. Both are new modules.
        new_shared_modules = [
            'scripts/pipeline_utils.py',
            'scripts/telar/media_type.py',
        ]
        for mod in new_shared_modules:
            assert mod in FRAMEWORK_FILES, f"new shared module not delivered: {mod}"
        # The fetch script that imports both pipeline_utils and
        # discover_sheet_gids — all three must travel together.
        for path in ('scripts/fetch_google_sheets.py', 'scripts/discover_sheet_gids.py'):
            assert path in FRAMEWORK_FILES, f"import-closure file missing: {path}"

    def test_upgrade_engine_not_delivered(self):
        """The migration engine ships via the verified tarball and runs from a
        temp copy, so it is intentionally excluded from the per-file delivery."""
        for path in (
            'scripts/upgrade.py',
            'scripts/migrations/base.py',
            'scripts/migrations/messages.py',
            'scripts/migrations/v140_to_v150.py',
        ):
            assert path not in FRAMEWORK_FILES, f"upgrade-engine file should not be delivered: {path}"

    def test_descriptions_are_nonempty(self):
        for path, desc in FRAMEWORK_FILES.items():
            assert isinstance(desc, str) and desc.strip(), f"empty description for {path}"


# ---------- Fail-closed ordering ----------

class TestFailClosedOrdering:
    """A failed framework fetch must short-circuit before .gitignore is
    touched, so a half-applied upgrade never edits config it shouldn't."""

    def test_gitignore_skipped_when_framework_fetch_fails(self, tmp_path, monkeypatch):
        m = Migration140to150(str(tmp_path))

        monkeypatch.setattr(m, '_update_framework_files', lambda: [
            ChangeRecord(description='Could not fetch X', status=ChangeStatus.FAILED, severity='hard')
        ])
        gitignore_called = {'hit': False}

        def _spy():
            gitignore_called['hit'] = True
            return []
        monkeypatch.setattr(m, '_update_gitignore', _spy)

        changes = m.apply()
        assert gitignore_called['hit'] is False
        assert any(c.status == ChangeStatus.FAILED for c in changes)

    def test_gitignore_runs_when_framework_fetch_succeeds(self, tmp_path, monkeypatch):
        m = Migration140to150(str(tmp_path))
        monkeypatch.setattr(m, '_update_framework_files', lambda: [
            ChangeRecord(description='Updated something', status=ChangeStatus.APPLIED, severity='hard')
        ])
        gitignore_called = {'hit': False}

        def _spy():
            gitignore_called['hit'] = True
            return []
        monkeypatch.setattr(m, '_update_gitignore', _spy)

        m.apply()
        assert gitignore_called['hit'] is True


# ---------- .gitignore re-ensure ----------

class TestUpdateGitignore:
    def test_adds_vendor_negation_when_missing(self, tmp_path):
        (tmp_path / '.gitignore').write_text('vendor/\n_site/\n', encoding='utf-8')
        m = Migration140to150(str(tmp_path))
        out = m._update_gitignore()
        content = (tmp_path / '.gitignore').read_text()
        assert '!assets/vendor/' in content
        assert any('re-ensured' in c.description for c in out)

    def test_noop_when_negation_present(self, tmp_path):
        (tmp_path / '.gitignore').write_text('vendor/\n!assets/vendor/\n', encoding='utf-8')
        m = Migration140to150(str(tmp_path))
        out = m._update_gitignore()
        # Still exactly one occurrence — not duplicated.
        content = (tmp_path / '.gitignore').read_text()
        assert content.count('!assets/vendor/') == 1
        assert any('already tracked' in c.description for c in out)


# ---------- Metadata + manual steps ----------

class TestMigrationMetadata:
    def test_from_to_versions(self):
        m = Migration140to150('/tmp')
        assert m.from_version == '1.4.0'
        assert m.to_version == '1.5.0'

    def test_pinned_to_release_tag(self):
        assert Migration140to150('/tmp')._TARGET_TAG == 'v1.5.0'

    def test_check_applicable_always_true(self):
        assert Migration140to150('/tmp').check_applicable() is True

    def test_manual_steps_bilingual_count(self):
        m = Migration140to150('/tmp')
        assert len(m._get_manual_steps_en()) == 2
        assert len(m._get_manual_steps_es()) == 2
        for step in m._get_manual_steps_en() + m._get_manual_steps_es():
            assert 'doc_url' in step
            assert step['description'].strip()

    def test_workflow_step_names_both_files_and_does_not_claim_delivery(self):
        """The workflow manual step must name both workflow files and the
        copy-from-Raw action — and must not imply the upgrade delivered them."""
        en = Migration140to150('/tmp')._get_manual_steps_en()[0]['description']
        assert '.github/workflows/upgrade.yml' in en
        assert '.github/workflows/build.yml' in en
        assert 'Raw' in en
        # Honest about what the automated upgrade can/can't do.
        assert 'does not let' in en.lower() or 'cannot' in en.lower()

    def test_language_step_mentions_both_packs(self):
        for desc in (
            Migration140to150('/tmp')._get_manual_steps_en()[1]['description'],
            Migration140to150('/tmp')._get_manual_steps_es()[1]['description'],
        ):
            assert 'en.yml' in desc and 'es.yml' in desc

    def test_spanish_step_uses_tu_imperative(self):
        """Colombian-Spanish styleguide: tú-imperative voice, not usted."""
        es = Migration140to150('/tmp')._get_manual_steps_es()
        joined = ' '.join(s['description'] for s in es)
        # tú-imperative markers present; usted-form 'aplique/actualice' absent.
        assert 'actualiza a mano' in joined
        assert 'vuelve a aplicar' in joined
