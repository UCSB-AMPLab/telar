"""
Unit Tests for migrations/v182_to_v183.py

These tests guard:

  - the delivery set, derived from the release's own diff against v1.8.2,
    so that a file changed on the release branch and left out of the set
    fails the test until it is added, and the exclusions: no workflow,
    engine, migration module or dev-only path;
  - that `Gemfile.lock` ships, with every rebuilt bundle, its source map and
    the module it is built from, and the story layout that carries the
    `baseurl` meta tag;
  - that the lock names the `x86_64-linux` platform the build runners need;
  - that the migration only installs framework files: it deletes nothing and
    has no manual steps;
  - metadata, and registration at the end of the chain.

Network fetches are not exercised here.

Version: v1.8.3
"""

import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations import v182_to_v183 as module
from migrations.v182_to_v183 import Migration182to183
from migrations.v181_to_v182 import Migration181to182
from migrations.base import ChangeRecord, ChangeStatus
from migrations.discovery import discover_migrations

import telar_upgrade as upgrade


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _git(*args):
    return subprocess.run(['git', '-C', str(REPO_ROOT), *args], capture_output=True, text=True)


TAG = Migration182to183._TARGET_TAG
PREVIOUS_TAG = 'v' + Migration182to183.from_version


def _tag_exists(tag):
    return _git('rev-parse', '--verify', '--quiet', f'refs/tags/{tag}^{{commit}}').returncode == 0


# Once the tag exists the release is the diff between the two tags. Before it
# does, the release is this working tree against v1.8.2. A checkout that also
# holds files of its own adds them to that diff, so before the tag an added
# file counts only under the directories a framework file is added to.
RELEASED = _tag_exists(TAG)
DIFF_REFS = (PREVIOUS_TAG, TAG) if RELEASED else (PREVIOUS_TAG,)
FRAMEWORK_DIRS = ('_layouts/', '_includes/', '_sass/', '_data/', 'assets/js/', 'assets/css/', 'scripts/telar/')

# What never reaches a site through FRAMEWORK_FILES, whatever changed in it:
# the same set as for v1.8.2, and `audit/`, the instance's own tooling, which
# is never ported.
NOT_DELIVERED_PREFIXES = (
    'telar-content/', 'tests/', 'docs/', 'audit/',
    '.github/', 'scripts/migrations/', 'scripts/telar_upgrade', 'assets/audio/peaks/',
)
NOT_DELIVERED_FILES = {
    '_config.yml', '.gitignore', '.gitattributes', 'index.md', 'pages/glossary.md', 'migration.json',
    'UPGRADE_SUMMARY.md', 'UPGRADE_VERSION.txt', 'pytest.ini', 'vitest.config.js',
}

# The bundles this release rebuilds, with the module each is built from.
REBUILT_BUNDLES = {
    'assets/js/telar-story.js': 'assets/js/telar-story/utils.js',
    'assets/js/share-panel.js': 'assets/js/share-panel/main.js',
    'assets/js/iiif-url-warning.js': 'assets/js/iiif-url-warning/main.js',
}


def _delivered(path):
    return path not in NOT_DELIVERED_FILES and not path.startswith(NOT_DELIVERED_PREFIXES)


def _release_diff():
    """(added or changed, removed) paths between v1.8.2 and the release."""
    out = _git('diff', '--name-status', '-M', *DIFF_REFS)
    assert out.returncode == 0, out.stderr
    shipped, removed = set(), set()
    for line in out.stdout.splitlines():
        status, *paths = line.split('\t')
        if status.startswith('D'):
            removed.add(paths[0])
        elif status.startswith('R'):
            removed.add(paths[0])
            shipped.add(paths[1])
        elif status.startswith('A') and not RELEASED and not paths[-1].startswith(FRAMEWORK_DIRS):
            continue
        else:
            shipped.add(paths[-1])
    return {p for p in shipped if _delivered(p)}, {p for p in removed if _delivered(p)}


def _exists_in_release(path):
    if RELEASED:
        return _git('cat-file', '-e', f'{TAG}:{path}').returncode == 0
    return (REPO_ROOT / path).is_file()


# ---------- Delivery set ----------

class TestFrameworkFilesDeliverySet:

    def test_the_set_is_every_shipped_change_since_v182(self):
        shipped, _removed = _release_diff()

        assert set(module.FRAMEWORK_FILES) - shipped == set(), 'delivered but not changed'
        assert shipped - set(module.FRAMEWORK_FILES) == set(), 'changed but not delivered'

    def test_nothing_shipped_is_removed(self):
        _shipped, removed = _release_diff()

        assert removed == set()

    def test_the_diff_is_read_from_refs_that_exist(self):
        """A diff against a missing ref is empty, and an empty diff would
        make the first check pass against a set of any size."""
        for ref in DIFF_REFS:
            assert _git('rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}').returncode == 0, ref
        shipped, _removed = _release_diff()
        assert len(shipped) >= len(module.FRAMEWORK_FILES) > 0

    def test_no_workflow_engine_or_migration_module(self):
        offenders = [p for p in module.FRAMEWORK_FILES
                     if p.startswith(('.github/', 'scripts/migrations/', 'scripts/telar_upgrade'))]

        assert offenders == []

    def test_no_dev_only_path(self):
        from telar.dev_only_files import read_dev_only_files
        dev_only = read_dev_only_files()
        offenders = [p for p in module.FRAMEWORK_FILES
                     if any(p == d or (d.endswith('/') and p.startswith(d)) for d in dev_only)]

        assert offenders == []

    def test_every_delivered_path_exists_in_the_release(self):
        missing = [p for p in sorted(module.FRAMEWORK_FILES) if not _exists_in_release(p)]

        assert missing == [], f'absent from the release: {missing}'

    @pytest.mark.xfail(not RELEASED, strict=True,
                       reason='v1.8.3 is not tagged yet; the release is the working tree until it is')
    def test_the_tag_this_is_checked_against_is_in_the_repository(self):
        assert _tag_exists(TAG)

    def test_the_lockfile_ships_with_package_json(self):
        assert {'package.json', 'package-lock.json'} <= set(module.FRAMEWORK_FILES)

    def test_the_gem_lock_ships(self):
        assert 'Gemfile.lock' in module.FRAMEWORK_FILES

    def test_the_root_documents_ship(self):
        assert {'README.md', 'CHANGELOG.md'} <= set(module.FRAMEWORK_FILES)

    @pytest.mark.parametrize('bundle, source', sorted(REBUILT_BUNDLES.items()))
    def test_each_rebuilt_bundle_ships_with_its_map_and_source(self, bundle, source):
        assert {bundle, bundle + '.map', source} <= set(module.FRAMEWORK_FILES)

    def test_the_story_layout_ships_with_the_bundles_that_read_its_meta_tag(self):
        assert '_layouts/story.html' in module.FRAMEWORK_FILES


# ---------- The release's content ----------

class TestTheReleaseContent:

    def test_the_gem_lock_names_the_linux_build_platform(self):
        lines = (REPO_ROOT / 'Gemfile.lock').read_text(encoding='utf-8').splitlines()
        platforms = lines[lines.index('PLATFORMS') + 1:]
        platforms = [p.strip() for p in platforms[:platforms.index('')]]

        assert 'x86_64-linux' in platforms

    def test_the_story_layout_carries_the_baseurl_meta_tag(self):
        layout = (REPO_ROOT / '_layouts/story.html').read_text(encoding='utf-8')

        assert '<meta name="baseurl" content="{{ site.baseurl }}">' in layout


# ---------- Apply ----------

class TestApply:

    def test_it_installs_the_set_and_nothing_else(self, tmp_path, monkeypatch):
        seen = []
        monkeypatch.setattr(Migration182to183, '_apply_framework_files',
                            lambda self, files: seen.append(files) or [])

        assert Migration182to183(str(tmp_path)).apply() == []
        assert seen == [module.FRAMEWORK_FILES]

    def test_it_deletes_nothing(self, tmp_path, monkeypatch):
        (tmp_path / '_config.yml').write_text('telar_language: "en"\n', encoding='utf-8')
        kept = ['tests/unit/test_csv_utils.py', 'pytest.ini', 'scripts/telar_upgrade.py',
                'telar-content/spreadsheets/glossary.csv', '.github/workflows/telar-tests.yml']
        for rel in kept:
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('x', encoding='utf-8')
        monkeypatch.setattr(Migration182to183, '_apply_framework_files', lambda self, files: [])

        Migration182to183(str(tmp_path)).apply()

        assert all((tmp_path / p).is_file() for p in kept)

    def test_a_hard_failure_installing_files_is_returned(self, tmp_path, monkeypatch):
        failed = ChangeRecord(description='fetch failed', status=ChangeStatus.FAILED,
                              severity='hard')
        monkeypatch.setattr(Migration182to183, '_apply_framework_files', lambda self, files: [failed])

        assert Migration182to183(str(tmp_path)).apply() == [failed]


# ---------- Metadata, steps, registration ----------

class TestMetadataAndSteps:

    def test_versions_and_pin(self):
        assert (Migration182to183.from_version, Migration182to183.to_version) == ('1.8.2', '1.8.3')
        assert Migration182to183._TARGET_TAG == 'v1.8.3'

    @pytest.mark.parametrize('lang', ['en', 'es'])
    def test_there_are_no_manual_steps(self, tmp_path, lang):
        (tmp_path / '_config.yml').write_text(f'telar_language: "{lang}"\n', encoding='utf-8')

        assert Migration182to183(str(tmp_path)).get_manual_steps() == []

    def test_every_description_says_what_the_file_is_for(self):
        assert all(isinstance(d, str) and len(d) > 10 for d in module.FRAMEWORK_FILES.values())


class TestRegistration:

    def test_discovery_finds_it_and_it_ends_the_chain(self):
        assert Migration182to183 in discover_migrations()
        assert upgrade.MIGRATIONS[-1] is Migration182to183

    def test_it_follows_the_v182_hop(self):
        chain = list(upgrade.MIGRATIONS)
        assert chain[chain.index(Migration181to182) + 1] is Migration182to183

    def test_latest_version_matches_chain_terminus(self):
        assert upgrade.LATEST_VERSION == '1.8.3'
