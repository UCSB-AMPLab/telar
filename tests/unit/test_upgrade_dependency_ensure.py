"""
Unit tests for upgrade._ensure_regeneration_dependencies.

Data regeneration subprocess-runs scripts that import the scripts/telar package,
which transitively needs markdown, PIL, jinja2, cryptography, yaml, and pandas.
The upgrade script ensures those are importable before regeneration, installing
from a requirements manifest only when something is missing — preferring the
tooling copy beside the script and falling back to the site's own copy.

Version: v1.6.2
"""

import sys
import os
import types
import importlib.util
import subprocess

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import upgrade


def _install_find_spec(monkeypatch, state):
    """Patch importlib.util.find_spec to report names in state['missing'] as absent."""
    def _stub(name, *args, **kwargs):
        return None if name in state['missing'] else object()
    monkeypatch.setattr(importlib.util, 'find_spec', _stub)


def _install_run(monkeypatch, returncode=0, stderr='', on_call=None):
    """Patch subprocess.run to record invocations and return a canned result."""
    calls = []

    def _run(cmd, *args, **kwargs):
        calls.append(cmd)
        if on_call is not None:
            on_call()
        return types.SimpleNamespace(returncode=returncode, stderr=stderr, stdout='')

    monkeypatch.setattr(subprocess, 'run', _run)
    return calls


def _point_tooling_at(monkeypatch, tmp_path):
    """Make Path(__file__).resolve().parent.parent the given dir by faking __file__."""
    fake_scripts = tmp_path / 'scripts'
    fake_scripts.mkdir(parents=True, exist_ok=True)
    fake_file = fake_scripts / 'upgrade.py'
    fake_file.write_text('# fake\n')
    monkeypatch.setattr(upgrade, '__file__', str(fake_file))


def test_all_imports_present_skips_pip(monkeypatch):
    """When every module resolves, return (True, []) with no pip call."""
    _install_find_spec(monkeypatch, {'missing': set()})

    def _boom(*a, **k):
        raise AssertionError("pip must not be called when all imports are present")

    monkeypatch.setattr(subprocess, 'run', _boom)

    ok, missing = upgrade._ensure_regeneration_dependencies('/tmp/site')
    assert ok is True
    assert missing == []


def test_missing_import_uses_tooling_manifest(monkeypatch, tmp_path):
    """A missing import with a tooling manifest present installs from that path."""
    tooling = tmp_path / 'tooling'
    site = tmp_path / 'site'
    site.mkdir()
    _point_tooling_at(monkeypatch, tooling)
    (tooling / 'requirements.txt').write_text('markdown\n')
    (site / 'requirements.txt').write_text('markdown\n')

    state = {'missing': {'markdown'}}
    _install_find_spec(monkeypatch, state)
    # A successful install makes the module resolvable on re-check.
    calls = _install_run(monkeypatch, returncode=0,
                         on_call=lambda: state.__setitem__('missing', set()))

    ok, missing = upgrade._ensure_regeneration_dependencies(str(site))
    assert ok is True
    assert missing == []
    assert len(calls) == 1
    assert calls[0][-1] == str(tooling / 'requirements.txt')
    assert calls[0][:5] == [sys.executable, '-m', 'pip', 'install', '-r']


def test_missing_import_falls_back_to_site_manifest(monkeypatch, tmp_path):
    """With no tooling manifest, install from the site's own requirements.txt."""
    tooling = tmp_path / 'tooling'  # no requirements.txt created here
    site = tmp_path / 'site'
    site.mkdir()
    _point_tooling_at(monkeypatch, tooling)
    (site / 'requirements.txt').write_text('markdown\n')

    state = {'missing': {'markdown'}}
    _install_find_spec(monkeypatch, state)
    calls = _install_run(monkeypatch, returncode=0,
                         on_call=lambda: state.__setitem__('missing', set()))

    ok, missing = upgrade._ensure_regeneration_dependencies(str(site))
    assert ok is True
    assert missing == []
    assert len(calls) == 1
    assert calls[0][-1] == str(site / 'requirements.txt')


def test_pip_failure_returns_failure_without_raising(monkeypatch, tmp_path):
    """A pip failure that leaves modules missing returns (False, [...]) and does not raise."""
    tooling = tmp_path / 'tooling'
    site = tmp_path / 'site'
    site.mkdir()
    _point_tooling_at(monkeypatch, tooling)
    (tooling / 'requirements.txt').write_text('markdown\n')

    state = {'missing': {'markdown', 'PIL'}}
    _install_find_spec(monkeypatch, state)
    # pip fails and the modules stay missing.
    calls = _install_run(monkeypatch, returncode=1, stderr='boom: could not install')

    ok, missing = upgrade._ensure_regeneration_dependencies(str(site))
    assert ok is False
    assert set(missing) == {'markdown', 'PIL'}
    assert len(calls) == 1


def test_no_manifest_anywhere_returns_failure_no_pip(monkeypatch, tmp_path):
    """With no manifest in either location, return failure without calling pip."""
    tooling = tmp_path / 'tooling'  # no requirements.txt
    site = tmp_path / 'site'
    site.mkdir()  # no requirements.txt
    _point_tooling_at(monkeypatch, tooling)

    state = {'missing': {'jinja2'}}
    _install_find_spec(monkeypatch, state)

    def _boom(*a, **k):
        raise AssertionError("pip must not be called when no manifest exists")

    monkeypatch.setattr(subprocess, 'run', _boom)

    ok, missing = upgrade._ensure_regeneration_dependencies(str(site))
    assert ok is False
    assert missing == ['jinja2']
