"""Unit tests for retiring a site's own scripts/migrations/.

A site running the launcher never executes the migrations sitting in it, so
the directory is dead weight whose version numbers invite the belief that it
is not. Removing it is easy; removing it safely is three guards, and each
guard is here because without it a site could be left unable to upgrade at
all.

Version: v1.7.0
"""

import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import telar_upgrade as engine
import upgrade as launcher
from migrations.base import ChangeCategory, ChangeStatus


def _site(tmp_path, *, launcher_present=True, migrations_present=True):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    if launcher_present:
        (scripts / 'upgrade.py').write_text(
            f"# {launcher.LAUNCHER_MARKER}\nprint('launcher')\n", encoding='utf-8')
    else:
        # An older copy of the engine, which is what a pre-launcher site holds.
        (scripts / 'upgrade.py').write_text('print("engine")\n', encoding='utf-8')
    if migrations_present:
        migrations = scripts / 'migrations'
        migrations.mkdir()
        (migrations / '__init__.py').write_text('')
        (migrations / 'v161_to_v162.py').write_text('# old\n')
    return tmp_path


class TestTheMarkerIsShared:

    def test_both_sides_agree_on_it(self):
        """The engine matches as text what the launcher writes."""
        assert engine.LAUNCHER_MARKER == launcher.LAUNCHER_MARKER

    def test_the_launcher_carries_it_in_its_own_source(self):
        source = (SCRIPTS / 'upgrade.py').read_text(encoding='utf-8')

        assert launcher.LAUNCHER_MARKER in source

    def test_this_repository_is_recognised_as_a_launcher_site(self):
        """The template is the repo, so its scripts/upgrade.py is the launcher."""
        assert engine._site_runs_the_launcher(str(SCRIPTS.parent))

    def test_an_old_engine_at_that_path_is_not_a_launcher(self, tmp_path):
        (tmp_path / 'scripts').mkdir()
        (tmp_path / 'scripts' / 'upgrade.py').write_text(
            'import argparse\ndef main():\n    pass\n', encoding='utf-8')

        assert not engine._site_runs_the_launcher(str(tmp_path))

    def test_a_site_with_no_scripts_directory_is_not_a_launcher(self, tmp_path):
        assert not engine._site_runs_the_launcher(str(tmp_path))


class TestItRetiresWhenItShould:

    def test_a_launcher_site_loses_the_directory(self, tmp_path):
        site = _site(tmp_path)

        records = engine._retire_local_migrations(str(site), 'en')

        assert not (site / 'scripts' / 'migrations').exists()
        assert len(records) == 1
        assert records[0].status == ChangeStatus.APPLIED
        assert records[0].category == ChangeCategory.SCRIPTS

    def test_it_says_so_in_spanish(self, tmp_path):
        site = _site(tmp_path)

        records = engine._retire_local_migrations(str(site), 'es')

        assert records[0].description.startswith('Se eliminó scripts/migrations/')

    def test_it_is_idempotent(self, tmp_path):
        site = _site(tmp_path)

        first = engine._retire_local_migrations(str(site), 'en')
        second = engine._retire_local_migrations(str(site), 'en')

        assert len(first) == 1
        assert second == []


class TestTheGuards:

    def test_a_site_without_the_launcher_keeps_its_migrations(self, tmp_path):
        """Otherwise the only thing that site can run is deleted."""
        site = _site(tmp_path, launcher_present=False)

        records = engine._retire_local_migrations(str(site), 'en')

        assert (site / 'scripts' / 'migrations').is_dir()
        assert records == []

    def test_a_site_with_no_migrations_directory_is_left_alone(self, tmp_path):
        site = _site(tmp_path, migrations_present=False)

        assert engine._retire_local_migrations(str(site), 'en') == []

    def test_it_refuses_to_delete_the_directory_it_imported(self, monkeypatch,
                                                            tmp_path):
        """Running in place, the site's scripts/ is the engine's own."""
        site = _site(tmp_path)
        monkeypatch.setattr(engine, '__file__',
                            str(site / 'scripts' / 'telar_upgrade.py'))

        records = engine._retire_local_migrations(str(site), 'en')

        assert (site / 'scripts' / 'migrations').is_dir()
        assert records == []

    def test_a_failure_to_delete_is_soft(self, tmp_path, monkeypatch):
        """A tidy-up cannot turn a completed upgrade into a failed one."""
        site = _site(tmp_path)

        def _refuse(path):
            raise OSError('permission denied')

        monkeypatch.setattr(engine.shutil, 'rmtree', _refuse)

        records = engine._retire_local_migrations(str(site), 'en')

        assert len(records) == 1
        assert records[0].status == ChangeStatus.FAILED
        assert records[0].severity == 'soft'
        assert 'permission denied' in records[0].description


class TestItRunsAfterTheWholeUpgrade:

    def test_main_retires_only_past_the_version_stamp(self):
        """Source order is the guarantee here, and it is worth pinning.

        The framework install clears its rollback state when it completes,
        and this directory was never in its backup set. Retiring before the
        stamp would mean a later hard failure could leave a site at its old
        version with no local engine and nothing able to restore one.
        """
        source = (SCRIPTS / 'telar_upgrade.py').read_text(encoding='utf-8')
        body = source[source.index('def main('):]

        stamp = body.index('_update_config_version(repo_root, LATEST_VERSION')
        retire = body.index('_retire_local_migrations(repo_root, lang)')
        summary = body.index('summary = generate_checklist(')

        assert stamp < retire < summary
