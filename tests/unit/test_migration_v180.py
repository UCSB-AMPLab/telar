"""
Unit Tests for migrations/v170_to_v180.py

The class layout of test_migration_v170.py, for the hop that carries the
most phases any migration has. These tests guard:

  - the delivery set, derived here from the release's own diff against
    v1.7.0 so that a file changed on the release branch and left out of the
    set fails the test until it is added, and the removals the same way;
  - the exclusions: no workflow, no engine, no migration module, no
    dev-only path;
  - that every delivered path exists at the ref it is fetched from, that
    every bundle ships with its sources, and that every `telar` module the
    build imports is in the set or unchanged since v1.7.0;
  - fail-closed ordering: a failed framework install runs no later phase,
    and a successful one runs them all, in order;
  - the removals, the stale manifest, and the stale engine with its two
    guards;
  - metadata, the six manual steps with their `kind` and `audience`, and
    registration at the end of the chain;
  - one run over a whole 1.7.0-shaped site, and a second that changes
    nothing.

The phases' own rules are tested in test_migration_v180_sheets.py,
test_migration_v180_sources.py. Network fetches are not exercised here.

Version: v1.8.0
"""

import ast
import errno
import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations import v170_to_v180
from migrations.v170_to_v180 import (
    ENGINE_FILES, FRAMEWORK_FILES, REMOVED_FILES, STALE_MANIFEST, Migration170to180,
)
from migrations.v162_to_v170 import Migration162to170
from migrations.base import ChangeRecord, ChangeStatus, MANUAL_STEP_AUDIENCES, MANUAL_STEP_KINDS
from migrations.messages import MESSAGES, get_message
from migrations.records import LAUNCHER_MARKER

import telar_upgrade as upgrade
from migrations.discovery import discover_migrations


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
TAG = Migration170to180._TARGET_TAG


def _git(*args):
    return subprocess.run(['git', '-C', str(REPO_ROOT), *args],
                          capture_output=True, text=True)


def _tag_exists():
    return _git('rev-parse', '--verify', '--quiet', f'{TAG}^{{commit}}').returncode == 0


# Before the tag exists the release is whatever this branch has committed.
RELEASE_REF = TAG if _tag_exists() else 'HEAD'

# What never reaches a site through FRAMEWORK_FILES, whatever changed in it:
# content and configuration the site owns, this repository's own tooling
# and tests, the engine, and the files the template carries only because it
# is also the development repository. `index.md` and `pages/glossary.md` are
# the site's; the one line each needs is edited in place. So is the pandas
# line of `requirements.txt`, which a site adds its own packages to.
NOT_DELIVERED_PREFIXES = (
    'telar-content/', 'tests/', 'docs/',
    '.github/', 'scripts/migrations/', 'scripts/telar_upgrade', 'assets/audio/peaks/',
)
NOT_DELIVERED_FILES = {
    '_config.yml', '.gitignore', 'index.md', 'pages/glossary.md', 'migration.json',
    'UPGRADE_SUMMARY.md', 'UPGRADE_VERSION.txt', 'pytest.ini', 'vitest.config.js',
}


def _delivered(path):
    return path not in NOT_DELIVERED_FILES and not path.startswith(NOT_DELIVERED_PREFIXES)


def _release_diff():
    """(added or changed, removed) paths between v1.7.0 and the release."""
    out = _git('diff', '--name-status', '-M', 'v1.7.0', RELEASE_REF)
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

    def test_the_set_is_every_shipped_change_since_v170(self):
        shipped, _removed = _release_diff()

        assert set(FRAMEWORK_FILES) - shipped == set(), 'delivered but not changed'
        assert shipped - set(FRAMEWORK_FILES) == set(), 'changed but not delivered'

    def test_the_removals_are_every_shipped_deletion(self):
        _shipped, removed = _release_diff()

        assert set(REMOVED_FILES) == removed

    def test_the_diff_is_read_from_a_ref_that_exists(self):
        """A diff against a missing ref is empty, and an empty diff would
        make both checks above pass against a set of any size."""
        shipped, _removed = _release_diff()

        assert len(shipped) > 100

    def test_the_stale_manifest_is_the_1_5_4_one(self):
        blob = _git('show', f'v1.7.0:{STALE_MANIFEST}')
        assert '"to_version": "1.5.4"' in blob.stdout

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
                       reason='v1.8.0 is not tagged yet; the paths are checked at HEAD until it is')
    def test_the_tag_this_is_checked_against_is_in_the_repository(self):
        assert _tag_exists()

    def test_descriptions_are_nonempty(self):
        assert all(isinstance(d, str) and d.strip() for d in FRAMEWORK_FILES.values())

    @pytest.mark.parametrize('bundle, entry', [
        ('assets/js/object-audio.js', 'assets/js/object-page/audio-entry.js'),
        ('assets/js/object-image.js', 'assets/js/object-page/image-entry.js'),
        ('assets/js/object-video.js', 'assets/js/object-page/video-entry.js'),
    ])
    def test_the_three_split_bundles_ship_with_map_and_entry(self, bundle, entry):
        assert {bundle, bundle + '.map', entry, 'assets/js/object-page/boot.js'} <= set(FRAMEWORK_FILES)

    @pytest.mark.parametrize('bundle, directory', [
        ('assets/js/objects-filter.js', 'assets/js/objects-filter/'),
        ('assets/js/share-panel.js', 'assets/js/share-panel/'),
        ('assets/js/telar-story.js', 'assets/js/telar-story/'),
    ])
    def test_bundles_ship_with_the_modules_they_are_built_from(self, bundle, directory):
        assert bundle in FRAMEWORK_FILES
        assert any(p.startswith(directory) for p in FRAMEWORK_FILES)

    def test_what_a_build_reads_at_a_fixed_path_is_delivered(self):
        assert {'scripts/telar/frontmatter.py', 'scripts/telar/glossary_pages.py',
                'scripts/telar/pages.py', '_data/glossary_kinds.yml'} <= set(FRAMEWORK_FILES)

    def test_every_telar_module_the_build_imports_is_current(self):
        """Walked from the two scripts a site's build runs, through every
        `telar` import. A module left at v1.7.0 beside a new one that calls
        into it fails the build on import."""
        imports = _telar_imports()
        assert {'scripts/telar/pages.py', 'scripts/telar/glossary_pages.py',
                'scripts/telar/frontmatter.py', 'scripts/telar/core.py'} <= imports
        stale = [module for module in sorted(imports)
                 if module not in FRAMEWORK_FILES
                 and _git('diff', '--quiet', 'v1.7.0', RELEASE_REF, '--', module).returncode != 0]

        assert stale == []


def _telar_imports():
    seen, pending = set(), ['scripts/generate_collections.py', 'scripts/csv_to_json.py']
    while pending:
        path = pending.pop()
        tree = ast.parse((REPO_ROOT / path).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            names = ([node.module] if isinstance(node, ast.ImportFrom) and node.module
                     else [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            for name in names:
                if name == 'telar' or name.startswith('telar.'):
                    for module in _module_paths(name, node):
                        if module not in seen:
                            seen.add(module)
                            pending.append(module)
    return seen


def _module_paths(name, node):
    base = 'scripts/' + name.replace('.', '/')
    candidates = [base + '.py', base + '/__init__.py']
    if isinstance(node, ast.ImportFrom):
        candidates += [f'{base}/{a.name}.py' for a in node.names]
    return [c for c in candidates if (REPO_ROOT / c).is_file()]


# ---------- Fail-closed ordering ----------

PHASES = ('update_site_pages', 'repair_colliding_columns', 'add_exclude_entries',
          'strip_page_sources', 'list_related_terms', 'report_step_answers')


def _instrumented(tmp_path, monkeypatch, framework_status):
    (tmp_path / '_config.yml').write_text('telar_language: "en"\n', encoding='utf-8')
    m = Migration170to180(str(tmp_path))
    monkeypatch.setattr(m, '_update_framework_files', lambda: [
        ChangeRecord(description='Updated _layouts/object.html',
                     status=framework_status, severity='hard')])
    calls = []
    for module in (v170_to_v180.v180_sources, v170_to_v180.v180_sheets):
        for name in PHASES:
            if hasattr(module, name):
                monkeypatch.setattr(module, name,
                                    lambda root, lang, name=name: calls.append(name) or [])
    for name in ('_remove_superseded_files', '_remove_stale_manifest', '_remove_stale_engine'):
        monkeypatch.setattr(m, name, lambda *a, name=name: calls.append(name) or [])
    return m, calls


class TestFailClosedOrdering:

    def test_no_later_phase_runs_when_the_framework_install_fails(self, tmp_path, monkeypatch):
        m, calls = _instrumented(tmp_path, monkeypatch, ChangeStatus.FAILED)

        changes = m.apply()

        assert calls == []
        assert [c.status for c in changes] == [ChangeStatus.FAILED]

    def test_every_phase_runs_in_order_when_it_succeeds(self, tmp_path, monkeypatch):
        m, calls = _instrumented(tmp_path, monkeypatch, ChangeStatus.APPLIED)

        m.apply()

        assert calls == ['_remove_superseded_files', '_remove_stale_manifest',
                         *PHASES, '_remove_stale_engine']


# ---------- Phase 2: removals ----------

def _touch(root, rel_path, text='// superseded\n'):
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


class TestRemovals:

    def test_the_list_is_the_single_object_page_bundle(self):
        assert REMOVED_FILES == ['assets/js/object-page.js', 'assets/js/object-page.js.map',
                                 'assets/js/object-page/main.js']

    def test_present_is_removed_and_absent_is_a_noop(self, tmp_path):
        _touch(tmp_path, REMOVED_FILES[0])
        m = Migration170to180(str(tmp_path))

        first = m._remove_superseded_files(REMOVED_FILES)
        second = m._remove_superseded_files(REMOVED_FILES)

        assert not (tmp_path / REMOVED_FILES[0]).exists()
        assert 'Removed' in first[0].description and 'already absent' in first[1].description
        assert all('already absent' in r.description for r in second)
        assert all(r.status == ChangeStatus.APPLIED for r in first + second)

    def test_removal_failure_is_soft(self, tmp_path, monkeypatch):
        _touch(tmp_path, REMOVED_FILES[0])

        def _boom(path):
            raise OSError(errno.EACCES, 'Permission denied')
        monkeypatch.setattr(os, 'remove', _boom)

        out = Migration170to180(str(tmp_path))._remove_superseded_files(REMOVED_FILES[:1])

        assert [(r.status, r.severity) for r in out] == [(ChangeStatus.FAILED, 'soft')]

    def test_the_stale_manifest_goes(self, tmp_path):
        _touch(tmp_path, STALE_MANIFEST, '{"to_version": "1.5.4"}\n')
        m = Migration170to180(str(tmp_path))

        records = m._remove_stale_manifest()

        assert not (tmp_path / STALE_MANIFEST).exists()
        assert [r.description for r in records] == [
            get_message('en', 'v180_removed_stale_manifest')]
        assert m._remove_stale_manifest() == []


# ---------- Phase 7: the stale engine ----------

RELEASED_ENGINE = _git('show', 'v1.7.0:scripts/telar_upgrade.py').stdout
LAUNCHER = f"LAUNCHER_MARKER = '{LAUNCHER_MARKER}'\n"


def _launcher_site(tmp_path, launcher=LAUNCHER, engine=RELEASED_ENGINE, helpers=False):
    (tmp_path / '_config.yml').write_text('telar_language: "en"\n', encoding='utf-8')
    _touch(tmp_path, 'scripts/upgrade.py', launcher)
    _touch(tmp_path, ENGINE_FILES[0], engine)
    if helpers:
        for rel_path in ENGINE_FILES[1:]:
            _touch(tmp_path, rel_path, '# a helper\n')
    return Migration170to180(str(tmp_path))


def _released_engine_hashes():
    """sha256 of every engine file at every release tag that shipped it."""
    import hashlib
    tags = [t for t in _git('tag').stdout.split()
            if __import__('re').match(r'^v\d+\.\d+\.\d+(-beta)?$', t)]
    found = {}
    for rel_path in ENGINE_FILES:
        for tag in tags:
            blob = subprocess.run(['git', '-C', str(REPO_ROOT), 'show', f'{tag}:{rel_path}'],
                                  capture_output=True)
            if blob.returncode == 0:
                found.setdefault(rel_path, set()).add(hashlib.sha256(blob.stdout).hexdigest())
    return found


class TestStaleEngine:

    def test_the_engine_and_the_launcher_share_the_marker(self):
        assert upgrade.LAUNCHER_MARKER is LAUNCHER_MARKER
        assert LAUNCHER in (REPO_ROOT / 'scripts' / 'upgrade.py').read_text(encoding='utf-8')

    def test_the_files_are_the_engine_and_its_helpers(self):
        assert ENGINE_FILES == ['scripts/telar_upgrade.py', 'scripts/telar_upgrade_common.py',
                                'scripts/telar_upgrade_regen.py', 'scripts/telar_upgrade_report.py']
        assert all((REPO_ROOT / p).is_file() for p in ENGINE_FILES)

    def test_the_released_copies_are_every_tagged_copy(self):
        """Recomputed from the tags: only v1.7.0 shipped the engine to a
        site, and no release shipped the helpers."""
        assert v170_to_v180.RELEASED_ENGINE_SHA256 == _released_engine_hashes()
        assert set(v170_to_v180.RELEASED_ENGINE_SHA256) == {'scripts/telar_upgrade.py'}

    def test_a_launcher_site_loses_the_released_engine(self, tmp_path):
        m = _launcher_site(tmp_path)

        records = m._remove_stale_engine()

        assert not (tmp_path / ENGINE_FILES[0]).exists()
        assert [(r.status, r.severity) for r in records] == [(ChangeStatus.APPLIED, 'soft')]
        assert 'Removed' in records[0].description

    @pytest.mark.parametrize('engine', [RELEASED_ENGINE + '# mine\n', '# my own engine\n',
                                        RELEASED_ENGINE.replace('\n', '\r\n')],
                             ids=['edited', 'own', 'crlf'])
    def test_a_file_that_is_not_a_released_copy_stays_and_is_reported(self, tmp_path, engine):
        m = _launcher_site(tmp_path, engine=engine)

        records = m._remove_stale_engine()

        assert (tmp_path / ENGINE_FILES[0]).read_bytes() == engine.encode('utf-8')
        assert [r.severity for r in records] == ['soft']
        assert 'not a copy Telar released' in records[0].description

    def test_helpers_no_release_shipped_stay_and_are_reported(self, tmp_path):
        m = _launcher_site(tmp_path, helpers=True)

        records = m._remove_stale_engine()

        assert all((tmp_path / p).exists() for p in ENGINE_FILES[1:])
        assert len(records) == 4
        assert sum('not a copy Telar released' in r.description for r in records) == 3

    def test_a_link_with_the_released_bytes_behind_it_stays(self, tmp_path):
        """A link is something the site set up, whatever it points at."""
        m = _launcher_site(tmp_path)
        engine = tmp_path / ENGINE_FILES[0]
        target = tmp_path / 'kept-engine.py'
        engine.rename(target)
        engine.symlink_to(target)

        records = m._remove_stale_engine()

        assert engine.is_symlink() and target.exists()
        assert [r.description for r in records] == [
            get_message('en', 'v180_engine_kept', ENGINE_FILES[0])]

    @pytest.mark.parametrize('launcher', [
        f'# {LAUNCHER_MARKER}\n',
        f'print("{LAUNCHER_MARKER}")\n',
        f"OTHER = '{LAUNCHER_MARKER}'\n",
        f"def f():\n    LAUNCHER_MARKER = '{LAUNCHER_MARKER}'\n",
        f"LAUNCHER_MARKER = '{LAUNCHER_MARKER}'  (\n",
        '# the engine itself\n',
    ], ids=['comment', 'string', 'other-name', 'not-module-level', 'syntax-error', 'absent'])
    def test_only_the_marker_assignment_makes_a_launcher_site(self, tmp_path, launcher):
        m = _launcher_site(tmp_path, launcher=launcher)

        assert m._remove_stale_engine() == []
        assert (tmp_path / ENGINE_FILES[0]).exists()

    def test_an_engine_running_from_the_site_keeps_them(self, tmp_path, monkeypatch):
        m = _launcher_site(tmp_path)
        monkeypatch.setattr(v170_to_v180, '_ENGINE_SCRIPTS_DIR', str(tmp_path / 'scripts'))

        assert m._remove_stale_engine() == []
        assert (tmp_path / ENGINE_FILES[0]).exists()

    def test_the_file_the_process_was_started_from_is_kept(self, tmp_path, monkeypatch):
        m = _launcher_site(tmp_path)
        monkeypatch.setattr(sys, 'argv', [str(tmp_path / 'scripts' / '..' / ENGINE_FILES[0])])

        assert m._remove_stale_engine() == []
        assert (tmp_path / ENGINE_FILES[0]).exists()

    def test_the_file_the_engine_module_was_loaded_from_is_kept(self, tmp_path, monkeypatch):
        """Compared resolved: the site is reached through a link, and the
        engine was loaded through its real path."""
        site = tmp_path / 'site'
        site.mkdir()
        _launcher_site(site)
        (tmp_path / 'link').symlink_to(site)
        m = Migration170to180(str(tmp_path / 'link'))
        running = type(sys)('telar_upgrade')
        running.__file__ = str(site.resolve() / ENGINE_FILES[0])
        monkeypatch.setitem(sys.modules, 'telar_upgrade', running)

        assert m._remove_stale_engine() == []
        assert (site / ENGINE_FILES[0]).exists()

    def test_absent_files_and_a_second_run_are_silent(self, tmp_path):
        m = _launcher_site(tmp_path)

        assert len(m._remove_stale_engine()) == 1
        assert m._remove_stale_engine() == []

    def test_a_failure_is_soft(self, tmp_path, monkeypatch):
        m = _launcher_site(tmp_path)

        def _boom(path):
            raise OSError(errno.EACCES, 'Permission denied')
        monkeypatch.setattr(os, 'remove', _boom)

        records = m._remove_stale_engine()

        assert [(r.status, r.severity) for r in records] == [(ChangeStatus.FAILED, 'soft')]


# ---------- Metadata ----------

class TestMigrationMetadata:

    def test_versions_and_pin(self):
        assert Migration170to180.from_version == '1.7.0'
        assert Migration170to180.to_version == '1.8.0'
        assert TAG == 'v1.8.0'
        assert Migration170to180('/tmp').check_applicable() is True

    @pytest.mark.xfail(Migration170to180.release_date is None, strict=True,
                       reason='release_date is filled from the v1.8.0 tag at Phase 4')
    def test_the_release_date_is_the_tags(self):
        dated = _git('log', '-1', '--format=%cs', TAG).stdout.strip()
        assert Migration170to180.release_date == dated


# ---------- Manual steps ----------

EXPECTED_STEPS = [('local', 'action'), ('local', 'optional'), ('local', 'optional'),
                  ('all', 'action'), ('google-sheets', 'action'), ('all', 'note')]


def _steps(lang):
    m = Migration170to180('/tmp')
    return m._get_manual_steps_es() if lang == 'es' else m._get_manual_steps_en()


class TestManualSteps:

    @pytest.mark.parametrize('lang', ['en', 'es'])
    def test_six_steps_with_the_ruled_audience_and_kind(self, lang):
        steps = _steps(lang)

        assert [(s['audience'], s['kind']) for s in steps] == EXPECTED_STEPS
        assert all(s['audience'] in MANUAL_STEP_AUDIENCES and s['kind'] in MANUAL_STEP_KINDS
                   for s in steps)
        assert all(s['doc_url'].startswith('https://telar.org/') for s in steps)

    def test_the_workflow_steps_name_their_files(self):
        en = _steps('en')
        for step, name in zip(en, ('build.yml', 'upgrade.yml', 'telar-tests.yml')):
            assert f'`.github/workflows/{name}`' in step['description']

    def test_the_build_step_says_why(self):
        text = _steps('en')[0]['description']
        assert 'seven days' in text and 'Node 22' in text

    def test_the_sheets_step_names_the_example_columns(self):
        text = _steps('en')[4]['description']
        assert '`medium`' in text and '`object_type`' in text

    def test_the_private_column_step_reads_as_approved(self):
        text = _steps('en')[3]['description']
        assert ('and a story marked with one of the two it did not accept was published '
                'unencrypted, with no warning, because the build never recognized it as '
                'protected.') in text
        assert '—' not in text

    def test_no_tracker_references_or_emojis(self):
        joined = ' '.join(s['description'] for s in _steps('en') + _steps('es'))
        assert 'TEL-' not in joined
        assert all(ord(ch) < 0x2190 for ch in joined)

    @pytest.mark.xfail(strict=True, reason='Pending the approved 1.8.0 CHANGELOG')
    def test_the_content_note_is_written(self):
        assert 'PENDING' not in _steps('en')[5]['description']
        assert 'PENDIENTE' not in _steps('es')[5]['description']

    def test_the_spanish_steps_are_written(self):
        assert all('ES-PENDIENTE' not in s['description'] for s in _steps('es')[:5])

    def test_spanish_uses_the_tu_imperative(self):
        joined = ' '.join(s['description'] for s in _steps('es'))
        assert 'Actualiza' in joined
        assert 'usted' not in joined.lower()

    def test_the_spanish_records_are_written(self):
        pending = [k for k, v in MESSAGES['es'].items() if 'ES-PENDIENTE' in v]
        assert pending == []

    def test_spanish_records_keep_the_english_placeholders(self):
        mismatched = [k for k, v in MESSAGES['en'].items() if k.startswith('v180_')
                      and v.count('{}') != MESSAGES['es'][k].count('{}')]
        assert mismatched == []


# ---------- Registration ----------

class TestRegistrationCompleteness:

    def test_discovery_finds_it_and_it_ends_the_chain(self):
        assert Migration170to180 in discover_migrations()
        assert upgrade.MIGRATIONS[-1] is Migration170to180

    def test_latest_version_matches_chain_terminus(self):
        assert upgrade.LATEST_VERSION == Migration170to180.to_version == '1.8.0'

    def test_it_follows_the_v170_hop(self):
        chain = list(upgrade.MIGRATIONS)
        assert chain[chain.index(Migration162to170) + 1] is Migration170to180

    def test_the_helper_modules_are_not_migrations(self):
        names = {cls.__module__ for cls in discover_migrations()}
        assert not any(n.endswith(('v180_sheets', 'v180_sources')) for n in names)

    def test_full_chain_resolves_to_latest_version(self):
        current = upgrade.MIGRATIONS[0].from_version
        for MigrationClass in upgrade.MIGRATIONS:
            assert MigrationClass.from_version == current
            current = MigrationClass.to_version
        assert current == upgrade.LATEST_VERSION


# ---------- One run over a whole site ----------

SITE = {
    '_config.yml': ('title: Site\ntelar_language: "en"\nexclude:\n  - Gemfile\n  - scripts/\n\n'
                    'telar:\n  version: "1.7.0"\n'),
    'index.md': '---\nlayout: index\n---\n\n{{ lang.index_page.welcome | markdownify }}\n',
    'pages/glossary.md': '---\nlayout: glossary-index\n---\n\n{{ lang.pages.glossary_intro }}\n',
    'migration.json': '{"to_version": "1.5.4"}\n',
    'assets/js/object-page.js': '// old bundle\n',
    'scripts/upgrade.py': LAUNCHER,
    'scripts/telar_upgrade.py': RELEASED_ENGINE,
    'telar-content/spreadsheets/objects.csv': 'object_id,title,medium,object_type\nm,M,Ink,\n',
    'telar-content/spreadsheets/my-story.csv': ('step,object,question,answer\n'
                                                '1,m,Q?,' + ' '.join(['w'] * 201) + '\n'),
    'telar-content/texts/pages/about.md': '---\ntitle: About\nlayout: page\npermalink: /about/\n---\nB\n',
    'telar-content/texts/glossary/cord.md': '---\nterm_id: cord\nrelated_terms: a, b\n---\nC\n',
}


def _snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob('*')) if p.is_file()}


class TestOneRunOverASite:

    def _run(self, tmp_path, monkeypatch):
        m = Migration170to180(str(tmp_path))
        monkeypatch.setattr(m, '_update_framework_files', lambda: [])
        return m.apply()

    def test_every_phase_lands_and_a_second_run_changes_nothing(self, tmp_path, monkeypatch):
        for rel_path, text in SITE.items():
            _touch(tmp_path, rel_path, text)

        records = self._run(tmp_path, monkeypatch)
        after = _snapshot(tmp_path)

        assert not any(r.status == ChangeStatus.FAILED for r in records)
        assert 'migration.json' not in after and 'assets/js/object-page.js' not in after
        assert 'scripts/telar_upgrade.py' not in after
        assert b'default: site.data' in after['index.md']
        assert b'glossary-intro.html' in after['pages/glossary.md']
        assert after['telar-content/spreadsheets/objects.csv'].startswith(b'object_id,title,medium\n')
        assert b'telar-content/texts/' in after['_config.yml']
        assert b'layout' not in after['telar-content/texts/pages/about.md']
        assert b'["a", "b"]' in after['telar-content/texts/glossary/cord.md']
        assert any('201 words' in r.description for r in records)

        self._run(tmp_path, monkeypatch)

        assert _snapshot(tmp_path) == after
