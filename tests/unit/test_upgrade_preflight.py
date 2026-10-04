"""Unit tests for what the upgrade engine does before it looks at the version.

Two checks run first: a notice when a previous upgrade left a failed-state
marker, and a pause over uncommitted changes in the site, which asks only a
person at a terminal and only on a real run. Each case drives `main()` on a
throwaway site that is already at the latest version, so a run that gets past
the checks stops at "already up to date" and no migration runs.

Version: v1.8.0
"""

import json
import os
import subprocess
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar_upgrade as upgrade
from migrations.messages import get_message


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A site at the latest version, with a git directory unless asked not to."""
    def _make(git=True, dirty=True, failed_state=None):
        (tmp_path / '_config.yml').write_text(
            f'telar:\n  version: "{upgrade.LATEST_VERSION}"\n', encoding='utf-8')
        if git:
            (tmp_path / '.git').mkdir()
        if failed_state:
            (tmp_path / 'UPGRADE_STATE.json').write_text(json.dumps(failed_state))
        calls = []

        def _git(cmd, *args, **kwargs):
            calls.append(cmd)
            return types.SimpleNamespace(stdout=' M index.md\n' if dirty else '',
                                         returncode=0)
        monkeypatch.setattr(subprocess, 'run', _git)
        return tmp_path, calls
    return _make


def _main(monkeypatch, root, *flags, tty=False, answer=None):
    monkeypatch.setattr(sys, 'argv', ['telar_upgrade.py', '--repo-root', str(root), *flags])
    monkeypatch.setattr(sys.stdin, 'isatty', lambda: tty, raising=False)
    asked = []

    def _input(prompt):
        asked.append(prompt)
        return answer
    monkeypatch.setattr('builtins.input', _input)
    return upgrade.main(), asked


class TestUncommittedChanges:

    def test_a_person_who_declines_stops_the_run(self, site, monkeypatch, capsys):
        root, _ = site()
        code, asked = _main(monkeypatch, root, tty=True, answer='n')
        out = capsys.readouterr().out
        assert code == upgrade.EXIT_PRECONDITION
        assert asked == [get_message('en', 'continue_anyway')]
        assert get_message('en', 'upgrade_cancelled') in out
        assert get_message('en', 'already_updated') not in out

    @pytest.mark.parametrize('answer', ['', 'yes', 'N'])
    def test_anything_but_y_stops_the_run(self, site, monkeypatch, answer):
        """The prompt's default is no, so pressing Enter is a no."""
        root, _ = site()
        code, _ = _main(monkeypatch, root, tty=True, answer=answer)
        assert code == upgrade.EXIT_PRECONDITION

    def test_a_person_who_agrees_goes_on(self, site, monkeypatch, capsys):
        root, _ = site()
        code, asked = _main(monkeypatch, root, tty=True, answer='Y')
        assert code == upgrade.EXIT_OK
        assert len(asked) == 1
        assert get_message('en', 'already_updated') in capsys.readouterr().out

    def test_without_a_terminal_nobody_is_asked(self, site, monkeypatch, capsys):
        root, _ = site()
        code, asked = _main(monkeypatch, root, tty=False)
        out = capsys.readouterr().out
        assert code == upgrade.EXIT_OK
        assert asked == []
        assert get_message('en', 'uncommitted_warning') in out
        assert get_message('en', 'no_tty_continue') in out

    def test_a_dry_run_is_not_asked(self, site, monkeypatch, capsys):
        root, _ = site()
        code, asked = _main(monkeypatch, root, '--dry-run', tty=True, answer='n')
        assert code == upgrade.EXIT_OK
        assert asked == []
        assert get_message('en', 'uncommitted_warning') not in capsys.readouterr().out

    def test_a_clean_tree_is_not_asked(self, site, monkeypatch):
        root, calls = site(dirty=False)
        code, asked = _main(monkeypatch, root, tty=True, answer='n')
        assert code == upgrade.EXIT_OK
        assert asked == []
        assert calls == [['git', 'status', '--porcelain']]

    def test_a_site_that_is_not_a_repository_is_not_checked(self, site, monkeypatch):
        root, calls = site(git=False)
        code, _ = _main(monkeypatch, root, tty=True, answer='n')
        assert code == upgrade.EXIT_OK
        assert calls == []

    def test_git_failing_does_not_stop_the_run(self, site, monkeypatch):
        root, _ = site()

        def _broken(*args, **kwargs):
            raise FileNotFoundError('git')
        monkeypatch.setattr(subprocess, 'run', _broken)
        code, asked = _main(monkeypatch, root, tty=True, answer='n')
        assert code == upgrade.EXIT_OK
        assert asked == []


class TestAPreviousFailure:

    def test_it_is_reported_with_the_version_it_was_for(self, site, monkeypatch, capsys):
        root, _ = site(dirty=False, failed_state={'status': 'failed', 'to_version': '1.7.0'})
        _main(monkeypatch, root)
        out = capsys.readouterr().out
        assert get_message('en', 'prev_upgrade_incomplete', '1.7.0') in out
        assert get_message('en', 'prev_upgrade_rerun') in out

    def test_a_marker_that_is_not_a_failure_is_not(self, site, monkeypatch, capsys):
        root, _ = site(dirty=False, failed_state={'status': 'in_progress', 'to_version': '1.7.0'})
        _main(monkeypatch, root)
        assert get_message('en', 'prev_upgrade_rerun') not in capsys.readouterr().out
