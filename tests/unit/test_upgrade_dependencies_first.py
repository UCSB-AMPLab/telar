"""Unit tests for when the upgrade engine installs its own dependencies.

The migrations import the `scripts/telar` package, which imports Pillow and
the rest of `requirements.txt`, and the `upgrade.yml` a site carries may
install only some of them (the oldest install only pyyaml and pandas). The
engine therefore installs from the tooling's requirements before the first
migration runs, not only before the data is regenerated.

Version: v1.8.0
"""

import sys

import pytest

sys.path.insert(0, 'scripts')

import telar_upgrade as upgrade


@pytest.fixture
def site(tmp_path):
    """A site one release behind, outside any git repository."""
    (tmp_path / '_config.yml').write_text('telar:\n  version: "1.7.0"\n', encoding='utf-8')
    return tmp_path


def _main(monkeypatch, root, *flags):
    calls = []

    def _ensure(repo_root):
        calls.append('dependencies')
        return True, []

    def _migrate(migrations, dry_run=False):
        calls.append('migrations')
        return []

    monkeypatch.setattr(upgrade, '_ensure_regeneration_dependencies', _ensure)
    monkeypatch.setattr(upgrade, 'run_migrations', _migrate)
    monkeypatch.setattr(upgrade, '_regenerate_data_files', lambda root: (True, True, False))
    monkeypatch.setattr(sys, 'argv', ['telar_upgrade.py', '--repo-root', str(root), *flags])
    monkeypatch.setattr(sys.stdin, 'isatty', lambda: False, raising=False)
    upgrade.main()
    return calls


class TestDependenciesBeforeMigrations:

    def test_they_are_installed_before_the_first_migration(self, site, monkeypatch):
        calls = _main(monkeypatch, site)

        assert 'migrations' in calls
        assert calls.index('dependencies') < calls.index('migrations')

    def test_a_dry_run_installs_them_too(self, site, monkeypatch):
        """A dry run runs the same migration code, which imports the package."""
        calls = _main(monkeypatch, site, '--dry-run')

        assert calls[:2] == ['dependencies', 'migrations']
