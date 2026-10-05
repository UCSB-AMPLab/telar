"""
Tests for the Compositor site's dev-only file list.

`scripts/dev-only-files.txt` names the framework's own test infrastructure,
which a Compositor site must not carry and a site build must not install
for. These tests pin its contents, check every entry actually exists in
the template, and check that neither the build workflow nor package.json's
regular dependencies pull in anything the list names.

Version: v1.8.0
"""

import json
import os
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(os.path.dirname(__file__)).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / 'scripts'))

from telar.dev_only_files import DEFAULT_LIST_PATH, read_dev_only_files  # noqa: E402


EXPECTED_ENTRIES = [
    'tests/',
    'vitest.config.js',
    'pytest.ini',
    '.github/workflows/telar-tests.yml',
]


def test_list_parses_to_exactly_the_four_entries():
    assert read_dev_only_files() == EXPECTED_ENTRIES


def test_comments_and_blank_lines_are_ignored():
    # DEFAULT_LIST_PATH is the template's own copy, which carries a header
    # note above the entries — if parsing counted it, the assertion above
    # would already fail, but this pins the reason why it does not.
    raw_lines = DEFAULT_LIST_PATH.read_text().splitlines()
    assert any(line.strip().startswith('#') for line in raw_lines)
    assert any(not line.strip() for line in raw_lines)


def test_every_listed_path_exists_in_the_template():
    for entry in read_dev_only_files():
        target = REPO_ROOT / entry
        if entry.endswith('/'):
            assert target.is_dir(), f"{entry} is listed as a directory but is not one"
        else:
            assert target.is_file(), f"{entry} is listed but does not exist"


def test_build_workflow_does_not_reference_dev_only_files():
    """The site build's own steps never name a file this list deletes.

    If they did, a Compositor site upgraded to 1.8.0 would lose a file its
    build still depends on.
    """
    workflow_path = REPO_ROOT / '.github' / 'workflows' / 'build.yml'
    workflow_text = workflow_path.read_text()

    for entry in read_dev_only_files():
        assert entry not in workflow_text, (
            f"build.yml references {entry!r}, which dev-only-files.txt "
            "deletes from a Compositor site"
        )


def test_build_workflow_installs_without_dev_dependencies():
    workflow_path = REPO_ROOT / '.github' / 'workflows' / 'build.yml'
    with open(workflow_path) as f:
        workflow = yaml.safe_load(f)

    steps = workflow['jobs']['build-and-deploy']['steps']
    js_steps = [s for s in steps if s.get('name') == 'Build JavaScript bundle']
    assert len(js_steps) == 1, (
        "Expected exactly one 'Build JavaScript bundle' step in build.yml."
    )

    run_text = js_steps[0]['run']
    assert 'npm install --omit=dev' in run_text, (
        "The JS bundle step must install with npm install --omit=dev, so a "
        "site build never installs vitest or jsdom."
    )
    # npm ci refuses to install when a site's lockfile is missing or out of
    # step with package.json, which an upgrade can leave behind.
    assert 'npm ci' not in run_text
    # The install has to happen before the build it feeds.
    assert run_text.index('npm install --omit=dev') < run_text.index('npm run build:js')


def test_package_json_dependency_placement():
    package_json = json.loads((REPO_ROOT / 'package.json').read_text())

    dependencies = package_json.get('dependencies', {})
    dev_dependencies = package_json.get('devDependencies', {})

    assert 'esbuild' in dependencies, (
        "esbuild is the one tool a site build runs, so npm install --omit=dev "
        "must still install it."
    )
    assert 'esbuild' not in dev_dependencies

    for dev_only_package in ('vitest', 'jsdom'):
        assert dev_only_package in dev_dependencies, (
            f"{dev_only_package} is test-only tooling and belongs in "
            "devDependencies, which a site build omits."
        )
        assert dev_only_package not in dependencies
