"""
Unit Tests for migrations/stale_engine.py

These tests guard:

  - that the released copies are every copy of the engine files the release
    tags hold, up to the release before this one, so a release cannot ship
    without the copies the previous one put in sites;
  - removal on a launcher site of every released copy, in both languages;
  - the guards: an edited or unreleased file stays and is reported, a link
    stays, a site without the launcher keeps its engine, and neither the
    site's own scripts/ nor any file the running engine came from is
    touched;
  - soft failure, a silent second run, and that the engine calls it only
    after the version stamp.

Version: v1.8.2
"""

import errno
import os
import pathlib
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations import stale_engine
from migrations.stale_engine import ENGINE_FILES, RELEASED_ENGINE_SHA256, remove_stale_engine
from migrations.base import ChangeStatus
from migrations.messages import get_message
from migrations.records import LAUNCHER_MARKER

import telar_upgrade as upgrade


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / 'scripts'
LAUNCHER = f"LAUNCHER_MARKER = '{LAUNCHER_MARKER}'\n"


def _git(*args, text=True):
    return subprocess.run(['git', '-C', str(REPO_ROOT), *args], capture_output=True, text=text)


def _version(tag):
    return tuple(int(n) for n in re.findall(r'\d+', tag)[:3])


def _released_tags_before(version):
    tags = [t for t in _git('tag').stdout.split() if re.match(r'^v\d+\.\d+\.\d+(-beta)?$', t)]
    assert 'v1.8.1' in tags, 'the release tags are not in this checkout'
    return [t for t in tags if _version(t) < _version(version)]


def _released_copy(rel_path, tag='v1.8.1'):
    return _git('show', f'{tag}:{rel_path}', text=False).stdout


def _launcher_site(root, launcher=LAUNCHER, files=None):
    """A launcher site holding *files* (path -> bytes), by default every
    engine file as v1.8.1 shipped it."""
    root.mkdir(parents=True, exist_ok=True)
    (root / '_config.yml').write_text('telar_language: "en"\n', encoding='utf-8')
    (root / 'scripts').mkdir(exist_ok=True)
    (root / 'scripts' / 'upgrade.py').write_text(launcher, encoding='utf-8')
    if files is None:
        files = {p: _released_copy(p) for p in ENGINE_FILES}
    for rel_path, content in files.items():
        (root / rel_path).write_bytes(content)
    return str(root)


class TestTheReleasedCopies:

    def test_the_files_are_the_engine_and_its_helpers(self):
        assert ENGINE_FILES == ['scripts/telar_upgrade.py', 'scripts/telar_upgrade_common.py',
                                'scripts/telar_upgrade_regen.py', 'scripts/telar_upgrade_report.py']
        assert all((REPO_ROOT / p).is_file() for p in ENGINE_FILES)

    def test_they_are_every_tagged_copy_before_this_release(self):
        """Recomputed from the tags: a release fails here until the copies
        the release before it shipped are listed."""
        import hashlib
        found = {}
        for tag in _released_tags_before(upgrade.LATEST_VERSION):
            for rel_path in ENGINE_FILES:
                blob = _git('show', f'{tag}:{rel_path}', text=False)
                if blob.returncode == 0:
                    found.setdefault(rel_path, set()).add(hashlib.sha256(blob.stdout).hexdigest())

        assert RELEASED_ENGINE_SHA256 == found


class TestRemoval:

    @pytest.mark.parametrize('tag', ['v1.7.0', 'v1.8.0', 'v1.8.1'])
    def test_every_released_copy_goes(self, tmp_path, tag):
        files = {p: _released_copy(p, tag) for p in ENGINE_FILES
                 if _git('cat-file', '-e', f'{tag}:{p}').returncode == 0}
        site = _launcher_site(tmp_path, files=files)

        records = remove_stale_engine(site, 'en')

        assert not any((tmp_path / p).exists() for p in ENGINE_FILES)
        assert [(r.status, r.severity) for r in records] == [(ChangeStatus.APPLIED, 'soft')] * len(files)
        assert all('Removed' in r.description for r in records)

    def test_it_says_so_in_spanish(self, tmp_path):
        site = _launcher_site(tmp_path)

        records = remove_stale_engine(site, 'es')

        assert records[0].description.startswith('Se eliminó scripts/telar_upgrade.py')

    def test_absent_files_and_a_second_run_are_silent(self, tmp_path):
        site = _launcher_site(tmp_path)

        assert len(remove_stale_engine(site, 'en')) == 4
        assert remove_stale_engine(site, 'en') == []

    def test_a_failure_is_soft(self, tmp_path, monkeypatch):
        site = _launcher_site(tmp_path, files={ENGINE_FILES[0]: _released_copy(ENGINE_FILES[0])})

        def _boom(path):
            raise OSError(errno.EACCES, 'Permission denied')
        monkeypatch.setattr(os, 'remove', _boom)

        records = remove_stale_engine(site, 'en')

        assert [(r.status, r.severity) for r in records] == [(ChangeStatus.FAILED, 'soft')]


class TestTheGuards:

    @pytest.mark.parametrize('edit', [lambda b: b + b'# mine\n', lambda b: b'# my own engine\n',
                                      lambda b: b.replace(b'\n', b'\r\n')],
                             ids=['edited', 'own', 'crlf'])
    def test_a_file_that_is_not_a_released_copy_stays_and_is_reported(self, tmp_path, edit):
        content = edit(_released_copy(ENGINE_FILES[1]))
        site = _launcher_site(tmp_path, files={ENGINE_FILES[1]: content})

        records = remove_stale_engine(site, 'en')

        assert (tmp_path / ENGINE_FILES[1]).read_bytes() == content
        assert [r.description for r in records] == [
            get_message('en', 'v180_engine_kept', ENGINE_FILES[1])]

    def test_a_link_with_the_released_bytes_behind_it_stays(self, tmp_path):
        site = _launcher_site(tmp_path, files={ENGINE_FILES[0]: _released_copy(ENGINE_FILES[0])})
        engine = tmp_path / ENGINE_FILES[0]
        target = tmp_path / 'kept-engine.py'
        engine.rename(target)
        engine.symlink_to(target)

        records = remove_stale_engine(site, 'en')

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
        site = _launcher_site(tmp_path, launcher=launcher)

        assert remove_stale_engine(site, 'en') == []
        assert all((tmp_path / p).exists() for p in ENGINE_FILES)

    def test_the_template_is_a_launcher_site(self):
        assert stale_engine._site_runs_the_launcher(str(REPO_ROOT))

    def test_an_engine_running_from_the_site_keeps_them(self, tmp_path, monkeypatch):
        site = _launcher_site(tmp_path)
        monkeypatch.setattr(stale_engine, '_ENGINE_SCRIPTS_DIR', str(tmp_path / 'scripts'))

        assert remove_stale_engine(site, 'en') == []
        assert all((tmp_path / p).exists() for p in ENGINE_FILES)

    def test_the_file_the_process_was_started_from_is_kept(self, tmp_path, monkeypatch):
        site = _launcher_site(tmp_path)
        monkeypatch.setattr(sys, 'argv', [str(tmp_path / 'scripts' / '..' / ENGINE_FILES[0])])

        remove_stale_engine(site, 'en')

        assert (tmp_path / ENGINE_FILES[0]).exists()
        assert not (tmp_path / ENGINE_FILES[1]).exists()

    def test_the_file_the_engine_module_was_loaded_from_is_kept(self, tmp_path, monkeypatch):
        """Compared resolved: the site is reached through a link, and the
        engine was loaded through its real path."""
        site = tmp_path / 'site'
        _launcher_site(site)
        (tmp_path / 'link').symlink_to(site)
        running = type(sys)('telar_upgrade')
        running.__file__ = str(site.resolve() / ENGINE_FILES[0])
        monkeypatch.setitem(sys.modules, 'telar_upgrade', running)

        remove_stale_engine(str(tmp_path / 'link'), 'en')

        assert (site / ENGINE_FILES[0]).exists()


class TestItRunsAfterTheWholeUpgrade:

    def test_main_removes_the_engine_only_past_the_version_stamp(self):
        """As with scripts/migrations/: before the stamp, a later hard
        failure could leave a site at its old version with its engine gone."""
        source = (SCRIPTS / 'telar_upgrade.py').read_text(encoding='utf-8')
        body = source[source.index('def main('):]

        stamp = body.index('_update_config_version(repo_root, LATEST_VERSION')
        remove = body.index('remove_stale_engine(repo_root, lang)')
        summary = body.index('summary = generate_checklist(')

        assert stamp < remove < summary

    def test_no_migration_removes_the_engine(self):
        """The engine is the only caller, so no removal runs mid-upgrade."""
        callers = [p.name for p in (SCRIPTS / 'migrations').glob('*.py')
                   if 'remove_stale_engine' in p.read_text(encoding='utf-8')]

        assert callers == ['stale_engine.py']
