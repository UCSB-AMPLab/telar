"""
Unit Tests for migrations/v180_to_v181.py

The layout of test_migration_v180.py, for a hop that only installs framework
files. These tests guard:

  - the delivery set, derived here from the release's own diff against
    v1.8.0, so that a file changed on the release branch and left out of the
    set fails the test until it is added;
  - the exclusions: no workflow, no engine, no migration module, no
    dev-only path;
  - that every delivered path exists at the ref it is fetched from, and that
    the story bundle ships with the modules it is built from;
  - metadata, the one note in each language, and registration at the end of
    the chain.

Network fetches are not exercised here.

Version: v1.8.1
"""

import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations.v180_to_v181 import FRAMEWORK_FILES, Migration180to181
from migrations.v170_to_v180 import Migration170to180
from migrations.base import ChangeRecord, ChangeStatus, MANUAL_STEP_AUDIENCES, MANUAL_STEP_KINDS

import telar_upgrade as upgrade
from migrations.discovery import discover_migrations


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
TAG = Migration180to181._TARGET_TAG


def _git(*args):
    return subprocess.run(['git', '-C', str(REPO_ROOT), *args],
                          capture_output=True, text=True)


def _tag_exists():
    return _git('rev-parse', '--verify', '--quiet', f'{TAG}^{{commit}}').returncode == 0


# Before the tag exists the release is whatever this branch has committed.
RELEASE_REF = TAG if _tag_exists() else 'HEAD'

# What never reaches a site through FRAMEWORK_FILES, whatever changed in it:
# the same set as for v1.8.0.
NOT_DELIVERED_PREFIXES = (
    'telar-content/', 'tests/', 'docs/',
    '.github/', 'scripts/migrations/', 'scripts/telar_upgrade', 'assets/audio/peaks/',
)
NOT_DELIVERED_FILES = {
    '_config.yml', '.gitignore', '.gitattributes', 'index.md', 'pages/glossary.md', 'migration.json',
    'UPGRADE_SUMMARY.md', 'UPGRADE_VERSION.txt', 'pytest.ini', 'vitest.config.js',
}


def _delivered(path):
    return path not in NOT_DELIVERED_FILES and not path.startswith(NOT_DELIVERED_PREFIXES)


def _release_diff():
    """(added or changed, removed) paths between v1.8.0 and the release."""
    out = _git('diff', '--name-status', '-M', 'v1.8.0', RELEASE_REF)
    assert out.returncode == 0, out.stderr
    shipped, removed = set(), set()
    for line in out.stdout.splitlines():
        status, *paths = line.split('\t')
        if status.startswith('D'):
            removed.add(paths[0])
        elif status.startswith('R'):
            removed.add(paths[0])
            shipped.add(paths[1])
        else:
            shipped.add(paths[-1])
    return {p for p in shipped if _delivered(p)}, {p for p in removed if _delivered(p)}


# ---------- Delivery set ----------

class TestFrameworkFilesDeliverySet:

    def test_the_set_is_every_shipped_change_since_v180(self):
        shipped, _removed = _release_diff()

        assert set(FRAMEWORK_FILES) - shipped == set(), 'delivered but not changed'
        assert shipped - set(FRAMEWORK_FILES) == set(), 'changed but not delivered'

    def test_nothing_shipped_is_removed(self):
        _shipped, removed = _release_diff()

        assert removed == set()

    def test_the_diff_is_read_from_a_ref_that_exists(self):
        """A diff against a missing ref is empty, and an empty diff would
        make the first check pass against a set of any size."""
        out = _git('rev-parse', '--verify', '--quiet', 'v1.8.0^{commit}')
        assert out.returncode == 0
        shipped, _removed = _release_diff()
        assert len(shipped) >= len(FRAMEWORK_FILES) > 0

    def test_no_workflow_engine_migration_or_dev_only_path(self):
        from telar.dev_only_files import read_dev_only_files
        dev_only = read_dev_only_files()
        offenders = [p for p in FRAMEWORK_FILES
                     if p.startswith(('.github/', 'scripts/migrations/', 'scripts/telar_upgrade'))
                     or any(p == d or (d.endswith('/') and p.startswith(d)) for d in dev_only)]

        assert offenders == []

    def test_every_delivered_path_exists_at_the_release_ref(self):
        missing = [p for p in sorted(FRAMEWORK_FILES)
                   if _git('cat-file', '-e', f'{RELEASE_REF}:{p}').returncode != 0]

        assert missing == [], f'absent at {RELEASE_REF}: {missing}'

    @pytest.mark.xfail(not _tag_exists(), strict=True,
                       reason='v1.8.1 is not tagged yet; the paths are checked at HEAD until it is')
    def test_the_tag_this_is_checked_against_is_in_the_repository(self):
        assert _tag_exists()

    def test_descriptions_are_nonempty(self):
        assert all(isinstance(d, str) and d.strip() for d in FRAMEWORK_FILES.values())

    def test_the_story_bundle_ships_with_its_map_and_modules(self):
        assert {'assets/js/telar-story.js', 'assets/js/telar-story.js.map'} <= set(FRAMEWORK_FILES)
        assert any(p.startswith('assets/js/telar-story/') for p in FRAMEWORK_FILES)

    def test_the_lockfile_ships_with_package_json(self):
        assert {'package.json', 'package-lock.json'} <= set(FRAMEWORK_FILES)


# ---------- Apply ----------

class TestApply:

    def test_apply_installs_the_set_and_nothing_else(self, tmp_path, monkeypatch):
        seen = []
        record = ChangeRecord(description='installed', status=ChangeStatus.APPLIED)

        def fake_apply(self, files):
            seen.append(files)
            return [record]

        monkeypatch.setattr(Migration180to181, '_apply_framework_files', fake_apply)

        assert Migration180to181(str(tmp_path)).apply() == [record]
        assert seen == [FRAMEWORK_FILES]


# ---------- Metadata ----------

class TestMigrationMetadata:

    def test_versions_and_pin(self):
        assert Migration180to181.from_version == '1.8.0'
        assert Migration180to181.to_version == '1.8.1'
        assert TAG == 'v1.8.1'
        assert Migration180to181('/tmp').check_applicable() is True

    @pytest.mark.xfail(Migration180to181.release_date is None or not _tag_exists(), strict=True,
                       reason='v1.8.1 is tagged after its release candidate is rehearsed')
    def test_the_release_date_is_the_tags(self):
        dated = _git('log', '-1', '--format=%cs', TAG).stdout.strip()
        assert Migration180to181.release_date == dated


# ---------- Manual steps ----------

def _steps(tmp_path, lang):
    (tmp_path / '_config.yml').write_text(f'telar_language: "{lang}"\n', encoding='utf-8')
    return Migration180to181(str(tmp_path)).get_manual_steps()


class TestManualSteps:

    @pytest.mark.parametrize('lang', ['en', 'es'])
    def test_one_note_for_everyone(self, tmp_path, lang):
        steps = _steps(tmp_path, lang)

        assert [(s['audience'], s['kind']) for s in steps] == [('all', 'note')]
        assert steps[0]['audience'] in MANUAL_STEP_AUDIENCES
        assert steps[0]['kind'] in MANUAL_STEP_KINDS
        assert steps[0]['doc_url'].startswith('https://telar.org/')

    def test_each_language_gets_its_own_note(self, tmp_path):
        (tmp_path / 'en').mkdir()
        (tmp_path / 'es').mkdir()
        en = _steps(tmp_path / 'en', 'en')
        es = _steps(tmp_path / 'es', 'es')

        assert en[0]['description'].startswith('**No action needed.**')
        assert es[0]['description'].startswith('**No se requiere ninguna acción.**')


# ---------- Registration ----------

class TestRegistrationCompleteness:

    def test_discovery_finds_it_and_it_ends_the_chain(self):
        assert Migration180to181 in discover_migrations()
        assert upgrade.MIGRATIONS[-1] is Migration180to181

    def test_latest_version_matches_chain_terminus(self):
        assert upgrade.LATEST_VERSION == Migration180to181.to_version == '1.8.1'

    def test_it_follows_the_v180_hop(self):
        chain = list(upgrade.MIGRATIONS)
        assert chain[chain.index(Migration170to180) + 1] is Migration180to181

    def test_full_chain_resolves_to_latest_version(self):
        current = upgrade.MIGRATIONS[0].from_version
        for MigrationClass in upgrade.MIGRATIONS:
            assert MigrationClass.from_version == current
            current = MigrationClass.to_version
        assert current == upgrade.LATEST_VERSION
