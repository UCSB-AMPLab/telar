"""
Unit Tests for migrations/v162_to_v170.py

v1.7.0 delivers the largest framework-file set since the consolidated
pre-0.9.0 hop: the root manifests, three layouts and an include, the rebuilt
JavaScript bundles together with the modules they are built from, and the
build scripts. It also does two things no earlier migration did — it delivers
`scripts/upgrade.py`, which is a launcher rather than the upgrade engine, and
it removes a Python module that a package has replaced. These tests guard:

  - the delivery set, asserted in full rather than sampled, so a path cannot
    quietly join or leave it;
  - the exclusions: no `.github/workflows/` path, no `scripts/telar_upgrade.py`,
    nothing under `scripts/migrations/`;
  - the launcher: `scripts/upgrade.py` is delivered, and the file in this
    repository carries the marker the engine looks for, so a site that
    receives it is recognised as a launcher site;
  - that every delivered path exists in the working tree, so a typo cannot
    ship as a fetch failure on somebody's site;
  - fail-closed ordering: a failed framework record skips both later phases;
  - the deletions: idempotent, recorded, soft on OSError;
  - the `.gitignore` entry: added once, not duplicated on a second run;
  - metadata and bilingual manual steps;
  - registration: discovery finds it, it ends the chain, and the chain walks
    unbroken from its first entry to LATEST_VERSION.

Network-dependent framework fetches are not exercised here — those are
covered by the upgrade.py integration tests.

Version: v1.7.0
"""

import errno
import os
import pathlib
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations.v162_to_v170 import (
    FRAMEWORK_FILES, GITIGNORE_ENTRIES, GITIGNORE_SECTION_COMMENT,
    REMOVED_FILES, Migration162to170,
)
from migrations.base import ChangeRecord, ChangeStatus

import telar_upgrade as upgrade
from migrations.discovery import discover_migrations


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

LAUNCHER_MARKER = 'telar-upgrade-launcher-v1'

# The delivery set, written out rather than derived. A migration that decides
# at run time what to ship delivers whatever the tree happens to hold; this is
# the release's decision, and the test is here to make changing it deliberate.
EXPECTED_FRAMEWORK_FILES = {
    '.gitattributes',
    '.ruby-version',
    'Gemfile',
    'requirements.txt',
    'package.json',
    'package-lock.json',
    'README.md',
    'CHANGELOG.md',

    '_includes/iiif-url-warning.html',
    '_layouts/index.html',
    '_layouts/object.html',
    '_layouts/objects-index.html',

    'assets/js/README.md',
    'assets/js/home-page.js',
    'assets/js/home-page.js.map',
    'assets/js/iiif-thumbnails/resolve.js',
    'assets/js/iiif-thumbnails/explicit-thumbnails.js',
    'assets/js/iiif-thumbnails/home.js',
    'assets/js/iiif-thumbnails/objects-index.js',
    'assets/js/iiif-url-warning.js',
    'assets/js/iiif-url-warning.js.map',
    'assets/js/iiif-url-warning/main.js',
    'assets/js/object-page.js',
    'assets/js/object-page.js.map',
    'assets/js/object-page/main.js',
    'assets/js/object-page/image-object.js',
    'assets/js/object-page/video-object.js',
    'assets/js/object-page/audio-object.js',
    'assets/js/object-page/clip-panel.js',
    'assets/js/object-page/copy-feedback.js',
    'assets/js/objects-filter.js',
    'assets/js/objects-filter.js.map',
    'assets/js/objects-filter/main.js',
    'assets/js/objects-filter/matching.js',
    'assets/js/objects-filter/search-index.js',
    'assets/js/objects-filter/escape.js',
    'assets/js/objects-index-page.js',
    'assets/js/objects-index-page.js.map',
    'assets/js/share-panel.js',
    'assets/js/share-panel.js.map',
    'assets/js/share-panel/main.js',
    'assets/js/share-panel/warnings.js',
    'assets/js/telar-story.js',
    'assets/js/telar-story.js.map',
    'assets/js/telar-story/card-pool.js',
    'assets/js/telar-story/navigation.js',

    'scripts/upgrade.py',
    'scripts/build_local_site.py',
    'scripts/check_jekyll_conflicts.py',
    'scripts/encrypt_protected_stories.py',
    'scripts/generate_collections.py',
    'scripts/generate_iiif.py',
    'scripts/iiif_utils.py',
    'scripts/process_pdf.py',
    'scripts/telar/build_conflicts.py',
    'scripts/telar/demo.py',
    'scripts/telar/story_pages.py',
    'scripts/telar/widgets.py',
    'scripts/telar/processors/stories.py',
    'scripts/telar/processors/objects/__init__.py',
    'scripts/telar/processors/objects/christmas_tree.py',
    'scripts/telar/processors/objects/featured.py',
    'scripts/telar/processors/objects/frame.py',
    'scripts/telar/processors/objects/local.py',
    'scripts/telar/processors/objects/remote.py',
}


# ---------- Delivery set (FRAMEWORK_FILES) ----------

class TestFrameworkFilesDeliverySet:

    def test_the_set_is_exactly_the_release_decision(self):
        assert set(FRAMEWORK_FILES) == EXPECTED_FRAMEWORK_FILES

    def test_no_workflow_files_delivered(self):
        """The upgrade GITHUB_TOKEN has no `workflows: write`, so a push
        touching .github/workflows/* is rejected wholesale. All three changed
        workflow files are manual steps."""
        offenders = [p for p in FRAMEWORK_FILES if p.startswith('.github/workflows/')]
        assert offenders == [], f"workflow files must not be in FRAMEWORK_FILES: {offenders}"

    def test_the_engine_and_its_migrations_are_not_delivered(self):
        """The engine ships in the verified release tarball. The launcher
        downloads it; a site never keeps a copy, and the engine retires the
        site's own scripts/migrations/ once the upgrade is done."""
        assert 'scripts/telar_upgrade.py' not in FRAMEWORK_FILES
        offenders = [p for p in FRAMEWORK_FILES if p.startswith('scripts/migrations/')]
        assert offenders == [], f"migration modules must not be delivered: {offenders}"

    def test_the_launcher_is_delivered(self):
        """The one departure from the exclusion convention, and the point of
        this hop: delivering it is what makes a site a launcher site."""
        assert 'scripts/upgrade.py' in FRAMEWORK_FILES

    def test_the_delivered_launcher_carries_the_marker_the_engine_reads(self):
        """`_site_runs_the_launcher` reads scripts/upgrade.py as text and looks
        for this string. Without it the engine takes a launcher site for one
        running an old engine, and never retires its dead migrations."""
        source = (REPO_ROOT / 'scripts' / 'upgrade.py').read_text(encoding='utf-8')

        assert LAUNCHER_MARKER in source
        assert upgrade.LAUNCHER_MARKER == LAUNCHER_MARKER

    def test_every_delivered_path_exists_in_this_repository(self):
        """A path that is not in the tree is a 404 on somebody's site, and a
        404 is a HARD failure that stops the whole upgrade."""
        missing = [p for p in sorted(FRAMEWORK_FILES) if not (REPO_ROOT / p).is_file()]
        assert missing == [], f"delivered paths absent from the repository: {missing}"

    def test_descriptions_are_nonempty(self):
        for path, desc in FRAMEWORK_FILES.items():
            assert isinstance(desc, str) and desc.strip(), f"empty description for {path}"

    def test_bundles_ship_with_the_modules_they_are_built_from(self):
        """A bundle without its sources rebuilds into last release's
        behaviour; sources without their bundle never reach a reader."""
        for bundle, directory in (
            ('assets/js/home-page.js', 'assets/js/iiif-thumbnails/'),
            ('assets/js/iiif-url-warning.js', 'assets/js/iiif-url-warning/'),
            ('assets/js/object-page.js', 'assets/js/object-page/'),
            ('assets/js/objects-filter.js', 'assets/js/objects-filter/'),
            ('assets/js/share-panel.js', 'assets/js/share-panel/'),
            ('assets/js/telar-story.js', 'assets/js/telar-story/'),
        ):
            assert bundle in FRAMEWORK_FILES
            assert any(p.startswith(directory) for p in FRAMEWORK_FILES), directory


# ---------- Fail-closed ordering ----------

class TestFailClosedOrdering:
    """A site that could not receive the new layouts must not lose the script
    the old ones load."""

    def test_later_phases_are_skipped_when_the_framework_install_fails(self, tmp_path, monkeypatch):
        m = Migration162to170(str(tmp_path))
        monkeypatch.setattr(m, '_update_framework_files', lambda: [
            ChangeRecord(description='Could not fetch _layouts/index.html',
                         status=ChangeStatus.FAILED, severity='hard')
        ])
        hits = {'remove': False, 'gitignore': False}
        monkeypatch.setattr(m, '_remove_superseded_files',
                            lambda paths: hits.__setitem__('remove', True) or [])
        monkeypatch.setattr(m, '_update_gitignore',
                            lambda: hits.__setitem__('gitignore', True) or [])

        changes = m.apply()

        assert hits == {'remove': False, 'gitignore': False}
        assert any(c.status == ChangeStatus.FAILED for c in changes)

    def test_later_phases_run_when_the_framework_install_succeeds(self, tmp_path, monkeypatch):
        m = Migration162to170(str(tmp_path))
        monkeypatch.setattr(m, '_update_framework_files', lambda: [
            ChangeRecord(description='Updated _layouts/index.html',
                         status=ChangeStatus.APPLIED, severity='hard')
        ])
        hits = {'remove': False, 'gitignore': False}
        monkeypatch.setattr(m, '_remove_superseded_files',
                            lambda paths: hits.__setitem__('remove', True) or [])
        monkeypatch.setattr(m, '_update_gitignore',
                            lambda: hits.__setitem__('gitignore', True) or [])

        m.apply()

        assert hits == {'remove': True, 'gitignore': True}


# ---------- Phase 2: superseded file removal ----------

class TestRemoveSupersededFiles:

    def test_the_list_is_the_two_superseded_files(self):
        assert REMOVED_FILES == [
            'assets/js/iiif-thumbnails.js',
            'scripts/telar/processors/objects.py',
        ]

    def test_absent_is_a_noop(self, tmp_path):
        out = Migration162to170(str(tmp_path))._remove_superseded_files(REMOVED_FILES)

        assert len(out) == len(REMOVED_FILES)
        for record in out:
            assert record.status == ChangeStatus.APPLIED
            assert 'already absent' in record.description

    def test_present_is_removed_and_recorded(self, tmp_path):
        for rel_path in REMOVED_FILES:
            target = tmp_path / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('// superseded\n', encoding='utf-8')

        out = Migration162to170(str(tmp_path))._remove_superseded_files(REMOVED_FILES)

        assert len(out) == len(REMOVED_FILES)
        for rel_path, record in zip(REMOVED_FILES, out):
            assert not (tmp_path / rel_path).exists()
            assert record.status == ChangeStatus.APPLIED
            assert 'Removed' in record.description
            assert rel_path in record.description

    def test_a_second_run_is_a_noop(self, tmp_path):
        target = tmp_path / REMOVED_FILES[0]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('// superseded\n', encoding='utf-8')

        m = Migration162to170(str(tmp_path))
        m._remove_superseded_files(REMOVED_FILES)
        second = m._remove_superseded_files(REMOVED_FILES)

        assert all(r.status == ChangeStatus.APPLIED for r in second)
        assert all('already absent' in r.description for r in second)

    def test_removal_failure_is_soft_not_hard(self, tmp_path, monkeypatch):
        for rel_path in REMOVED_FILES:
            target = tmp_path / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('// superseded\n', encoding='utf-8')

        def _boom(path):
            raise OSError(errno.EACCES, 'Permission denied')
        monkeypatch.setattr(os, 'remove', _boom)

        out = Migration162to170(str(tmp_path))._remove_superseded_files(REMOVED_FILES)

        assert len(out) == len(REMOVED_FILES)
        for record in out:
            assert record.status == ChangeStatus.FAILED
            assert record.severity == 'soft'
            assert 'Non-fatal' in record.description


# ---------- Phase 3: .gitignore ----------

class TestGitignore:

    def _gitignore(self, tmp_path, text='# Jekyll\n_site/\n'):
        (tmp_path / '.gitignore').write_text(text, encoding='utf-8')
        return tmp_path / '.gitignore'

    def test_the_entry_is_the_generated_manifest_directory(self):
        assert GITIGNORE_ENTRIES == ['_data/telar-build/']
        assert GITIGNORE_SECTION_COMMENT.startswith('#')
        assert 'generate_collections.py' in GITIGNORE_SECTION_COMMENT
        # One line: _ensure_gitignore_entries matches a section by exact
        # line equality, so a wrapped comment would be appended every run.
        assert '\n' not in GITIGNORE_SECTION_COMMENT

    def test_entry_is_added_and_recorded(self, tmp_path):
        path = self._gitignore(tmp_path)

        out = Migration162to170(str(tmp_path))._update_gitignore()

        text = path.read_text(encoding='utf-8')
        assert '_data/telar-build/' in text
        assert GITIGNORE_SECTION_COMMENT in text
        assert len(out) == 1
        assert out[0].status == ChangeStatus.APPLIED
        assert out[0].severity == 'soft'

    def test_a_second_run_does_not_duplicate_the_entry(self, tmp_path):
        path = self._gitignore(tmp_path)
        m = Migration162to170(str(tmp_path))
        m._update_gitignore()
        first = path.read_text(encoding='utf-8')

        out = m._update_gitignore()

        text = path.read_text(encoding='utf-8')
        assert text == first
        assert text.count('_data/telar-build/') == 1
        assert text.count(GITIGNORE_SECTION_COMMENT) == 1
        assert out[0].status == ChangeStatus.APPLIED

    def test_a_site_with_no_gitignore_is_recorded_not_failed(self, tmp_path):
        out = Migration162to170(str(tmp_path))._update_gitignore()

        assert len(out) == 1
        assert out[0].status == ChangeStatus.APPLIED
        assert out[0].severity == 'soft'


# ---------- Metadata + manual steps ----------

class TestMigrationMetadata:

    def test_from_to_versions(self):
        m = Migration162to170('/tmp')
        assert m.from_version == '1.6.2'
        assert m.to_version == '1.7.0'

    def test_pinned_to_release_tag(self):
        assert Migration162to170('/tmp')._TARGET_TAG == 'v1.7.0'

    def test_check_applicable_always_true(self):
        assert Migration162to170('/tmp').check_applicable() is True

    def test_manual_steps_bilingual_count(self):
        m = Migration162to170('/tmp')
        en, es = m._get_manual_steps_en(), m._get_manual_steps_es()

        assert len(en) == 5
        assert len(es) == len(en)
        for step in en + es:
            assert step.get('doc_url', '').startswith('https://telar.org/')
            assert step['description'].strip()

    def test_the_three_workflow_steps_name_their_files(self):
        for steps in (Migration162to170('/tmp')._get_manual_steps_en(),
                      Migration162to170('/tmp')._get_manual_steps_es()):
            assert '.github/workflows/build.yml' in steps[0]['description']
            assert '.github/workflows/upgrade.yml' in steps[1]['description']
            assert '.github/workflows/telar-tests.yml' in steps[2]['description']

    def test_the_local_step_names_ruby_and_the_launcher(self):
        en = Migration162to170('/tmp')._get_manual_steps_en()[3]['description']
        es = Migration162to170('/tmp')._get_manual_steps_es()[3]['description']

        for desc in (en, es):
            assert 'Ruby 3.2' in desc
            assert '.ruby-version' in desc
            assert 'scripts/upgrade.py' in desc

    def test_the_content_step_is_last_and_points_at_the_docs_home(self):
        en = Migration162to170('/tmp')._get_manual_steps_en()[4]
        es = Migration162to170('/tmp')._get_manual_steps_es()[4]

        assert en['doc_url'] == 'https://telar.org/docs'
        assert es['doc_url'] == 'https://telar.org/guia'
        assert 'width' in en['description'] and 'height' in en['description']
        assert 'width' in es['description'] and 'height' in es['description']

    def test_no_emojis_in_manual_steps(self):
        m = Migration162to170('/tmp')
        joined = ' '.join(s['description']
                          for s in m._get_manual_steps_en() + m._get_manual_steps_es())
        assert all(ord(ch) < 0x2190 for ch in joined), 'manual steps must carry no emojis'

    def test_spanish_step_uses_tu_imperative(self):
        """Colombian-Spanish styleguide: tu-imperative voice, not usted."""
        es = Migration162to170('/tmp')._get_manual_steps_es()
        joined = ' '.join(s['description'] for s in es)

        assert 'Actualiza' in joined
        assert 'copia el' in joined
        assert 'usted' not in joined.lower()


# ---------- Registration completeness ----------

class TestRegistrationCompleteness:
    """Registration is derived from the package, so what these check is that
    the derivation sees this migration and puts it where the chain ends."""

    def test_discovery_finds_it(self):
        assert Migration162to170 in discover_migrations()

    def test_is_last_in_migrations_list(self):
        assert upgrade.MIGRATIONS[-1] is Migration162to170

    def test_latest_version_matches_chain_terminus(self):
        assert upgrade.LATEST_VERSION == Migration162to170.to_version == '1.7.0'

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
