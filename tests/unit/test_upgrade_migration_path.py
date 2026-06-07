"""
Unit tests for upgrade.get_migration_path strict version chaining.

A migration only joins the path when its from_version matches the version
reached so far; the old `or migrations_to_run` heuristic ran every later
migration once the list was non-empty, silently producing the wrong chain
across a version gap.

Version: v1.5.0
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import upgrade


def _mig_class(frm, to, applicable=True):
    class _Mig:
        from_version = frm
        to_version = to

        def __init__(self, repo_root):
            self.repo_root = repo_root

        def check_applicable(self):
            return applicable

        def __repr__(self):
            return f"{frm}->{to}"

    return _Mig


@pytest.fixture
def patch_latest(monkeypatch):
    monkeypatch.setattr(upgrade, 'LATEST_VERSION', '1.4.0')


def test_linear_chain_runs_in_order(monkeypatch, patch_latest):
    monkeypatch.setattr(upgrade, 'MIGRATIONS', [
        _mig_class('1.2.0', '1.3.0'),
        _mig_class('1.3.0', '1.4.0'),
    ])
    path = upgrade.get_migration_path('1.2.0', '/tmp')
    assert [m.to_version for m in path] == ['1.3.0', '1.4.0']


def test_start_mid_chain(monkeypatch, patch_latest):
    monkeypatch.setattr(upgrade, 'MIGRATIONS', [
        _mig_class('1.2.0', '1.3.0'),
        _mig_class('1.3.0', '1.4.0'),
    ])
    path = upgrade.get_migration_path('1.3.0', '/tmp')
    assert [m.from_version for m in path] == ['1.3.0']


def test_gap_version_yields_empty_path(monkeypatch, patch_latest, capsys):
    monkeypatch.setattr(upgrade, 'MIGRATIONS', [
        _mig_class('1.2.0', '1.3.0'),
        _mig_class('1.3.0', '1.4.0'),
    ])
    path = upgrade.get_migration_path('0.4.2-beta', '/tmp')
    assert path == []
    out = capsys.readouterr().out
    assert 'stops at 0.4.2-beta' in out


def test_does_not_run_unreachable_migration(monkeypatch, patch_latest):
    # The old `or migrations_to_run` bug would have appended the 9.9.9 migration
    # once the list was non-empty. Strict chaining must skip it.
    monkeypatch.setattr(upgrade, 'MIGRATIONS', [
        _mig_class('1.2.0', '1.3.0'),
        _mig_class('1.3.0', '1.4.0'),
        _mig_class('9.9.9', '9.9.10'),
    ])
    path = upgrade.get_migration_path('1.2.0', '/tmp')
    assert all(m.from_version != '9.9.9' for m in path)
    assert [m.to_version for m in path] == ['1.3.0', '1.4.0']


def test_non_applicable_migration_still_advances_chain(monkeypatch, patch_latest):
    # A middle migration whose changes are already applied is skipped from the
    # run list but must still advance the chain so the next link matches.
    monkeypatch.setattr(upgrade, 'MIGRATIONS', [
        _mig_class('1.2.0', '1.3.0', applicable=False),
        _mig_class('1.3.0', '1.4.0'),
    ])
    path = upgrade.get_migration_path('1.2.0', '/tmp')
    assert [m.to_version for m in path] == ['1.4.0']
