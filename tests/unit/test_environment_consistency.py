"""
Static consistency tests between what workflows/manifests declare and what
the code they run actually needs.

An upgrade workflow step that installs an ad-hoc package list instead of the
full manifest silently drifts as scripts/ grows new imports. A third-party
import added to scripts/ without a matching requirements.txt entry works
locally (already installed) and fails only in a clean CI/user environment.
A workflow `if:` guard that scopes framework tests to the framework's own
repos can be dropped in a rewrite without any test noticing. A migration
that ships package.json without package-lock.json (or vice versa) leaves
npm free to re-resolve versions instead of installing the pinned tree.
These tests turn each of those mismatches into a CI failure at PR time.

Version: v1.6.2
"""

import ast
import importlib
import os
import re
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(os.path.dirname(__file__)).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / 'scripts'))

import migrations  # noqa: E402  (sys.path must be set up first)


# ---------------------------------------------------------------------------
# Test 1: upgrade workflow installs the full manifest
# ---------------------------------------------------------------------------

def test_upgrade_workflow_installs_full_requirements_manifest():
    """The upgrade job's dependency step must run the full requirements.txt.

    Data regeneration during an upgrade imports scripts/telar, which
    transitively pulls in every third-party package the build pipeline
    needs (pandas, PyYAML, markdown, jinja2, cryptography, Pillow, ...). An
    ad-hoc `pip install pkg1 pkg2` step only tracks what someone remembered
    to list by hand and rots the moment scripts/ gains a new import.
    """
    workflow_path = REPO_ROOT / '.github' / 'workflows' / 'upgrade.yml'
    with open(workflow_path) as f:
        workflow = yaml.safe_load(f)

    steps = workflow['jobs']['upgrade']['steps']
    install_steps = [s for s in steps if s.get('name') == 'Install dependencies']
    assert len(install_steps) == 1, (
        "Expected exactly one 'Install dependencies' step in the upgrade job."
    )

    run = install_steps[0].get('run', '').strip()
    assert run == 'pip install -r requirements.txt', (
        "The upgrade job's 'Install dependencies' step must install the full "
        f"requirements.txt, not an ad-hoc package list. Found: {run!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: every third-party import in scripts/ is declared in requirements.txt
# ---------------------------------------------------------------------------

# Import name -> requirements.txt distribution name, for the imports whose
# import name does not match their distribution name.
IMPORT_TO_DISTRIBUTION = {
    'PIL': 'Pillow',
    'yaml': 'pyyaml',
    'fitz': 'PyMuPDF',
    'pillow_heif': 'pillow-heif',
}

# Imports that are allowed to be undeclared in requirements.txt because every
# call site guards them with try/except ImportError and degrades gracefully
# when the package is absent, rather than requiring it for the pipeline to
# run. Each entry must be verified against the actual guard, not assumed.
#
# certifi: supplies a TLS context with its own CA bundle on platforms whose
# Python build has no linked system trust store (e.g. python.org macOS
# builds); every import site falls back to ssl's default context when it is
# missing.
OPTIONAL_UNDECLARED_IMPORTS = {'certifi'}


def _discover_local_module_names(scripts_dir):
    """Top-level names under scripts/ that resolve as sibling imports.

    scripts/ is added to sys.path wholesale (as this test file and the
    pipeline scripts themselves do), so any top-level module or package
    living there — not just the ones referenced today — is a local import,
    never a third-party one.
    """
    local_names = set()
    for entry in os.listdir(scripts_dir):
        if entry.startswith('__') or entry == '__pycache__':
            continue
        full = scripts_dir / entry
        if full.is_dir():
            if (full / '__init__.py').exists():
                local_names.add(entry)
        elif entry.endswith('.py'):
            local_names.add(entry[:-3])
    return local_names


def _collect_top_level_import_names(py_file):
    """Top-level names imported anywhere in a module (any nesting depth).

    A deferred import inside a function still needs its package declared —
    it only runs later, not never — so this walks the whole tree rather
    than just the module body. Relative imports (`from .base import ...`)
    are skipped; they resolve within the package, not via requirements.txt.
    """
    with open(py_file, encoding='utf-8') as f:
        tree = ast.parse(f.read(), filename=str(py_file))

    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            if node.module:
                names.add(node.module.split('.')[0])
    return names


def _normalize_distribution_name(name):
    """PyPI distribution names are compared case- and separator-insensitively
    (pillow-heif == pillow_heif == Pillow-Heif)."""
    return name.lower().replace('_', '-')


def _parse_requirements(requirements_path):
    """Distribution names declared in a requirements.txt, normalized."""
    declared = set()
    with open(requirements_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            name = re.split(r'[<>=!~\[;]', line, maxsplit=1)[0].strip()
            if name:
                declared.add(_normalize_distribution_name(name))
    return declared


def test_scripts_third_party_imports_declared_in_requirements():
    """Every third-party import reachable from scripts/ is in requirements.txt.

    A script that imports a package already installed on a developer's
    machine passes locally and fails only in a clean environment (CI, a
    freshly upgraded user site) where nothing but requirements.txt gets
    installed.
    """
    scripts_dir = REPO_ROOT / 'scripts'
    local_names = _discover_local_module_names(scripts_dir)
    declared = _parse_requirements(REPO_ROOT / 'requirements.txt')
    stdlib_names = set(sys.stdlib_module_names)

    missing = []
    for py_file in sorted(scripts_dir.rglob('*.py')):
        if '__pycache__' in py_file.parts:
            continue
        for name in _collect_top_level_import_names(py_file):
            if name in stdlib_names or name in local_names:
                continue
            if name in OPTIONAL_UNDECLARED_IMPORTS:
                continue
            distribution = IMPORT_TO_DISTRIBUTION.get(name, name)
            if _normalize_distribution_name(distribution) not in declared:
                missing.append(
                    f"{py_file.relative_to(REPO_ROOT)}: imports '{name}' "
                    f"(needs '{distribution}' in requirements.txt)"
                )

    assert not missing, (
        "Third-party imports in scripts/ without a matching requirements.txt "
        "entry:\n" + "\n".join(missing)
    )


# ---------------------------------------------------------------------------
# Test 3: telar-tests.yml carries the user-site guard
# ---------------------------------------------------------------------------

def test_telar_tests_workflow_guards_every_job_to_framework_repos():
    """Every job's `if:` must scope it to the framework's own repos.

    telar-tests.yml runs on pull_request; a site cloned from the Telar
    template inherits this workflow file too. Without the repository guard,
    framework unit tests would run against user site content on every user
    PR. The guard must survive workflow rewrites as new jobs are added.
    """
    workflow_path = REPO_ROOT / '.github' / 'workflows' / 'telar-tests.yml'
    with open(workflow_path) as f:
        workflow = yaml.safe_load(f)

    jobs = workflow['jobs']
    assert jobs, "telar-tests.yml declares no jobs to check."

    unguarded = []
    for job_name, job in jobs.items():
        condition = job.get('if', '')
        if "github.repository == 'UCSB-AMPLab/telar'" not in condition or \
                "github.repository == 'juancobo/telar'" not in condition:
            unguarded.append(job_name)

    assert not unguarded, (
        "Framework tests must not run on user sites built from the Telar "
        "template. These jobs in telar-tests.yml are missing the "
        "github.repository guard for UCSB-AMPLab/telar and juancobo/telar: "
        + ", ".join(unguarded)
    )


# ---------------------------------------------------------------------------
# Test 4: migration manifests ship package.json and package-lock.json as a pair
# ---------------------------------------------------------------------------

# Migrations frozen at their current state: each ships package.json without
# package-lock.json. The pairing rule below applies to every migration
# written from here on; these predate it and are not retroactively fixed.
FROZEN_LOCKFILE_PAIRING_VIOLATIONS = {
    'v154_to_v160',
}


def _discover_migration_modules(migrations_dir):
    """Migration module stems, matching the vFROM_to_vTO naming convention."""
    pattern = re.compile(r'^v\d+_to_v?\d+.*$')
    stems = []
    for py_file in sorted(migrations_dir.glob('v*_to_*.py')):
        stem = py_file.stem
        if pattern.match(stem):
            stems.append(stem)
    return stems


def test_migration_manifests_ship_lockfile_pairs():
    """FRAMEWORK_FILES must ship package.json and package-lock.json together.

    A migration that installs package.json alone leaves npm free to
    re-resolve the dependency tree instead of installing the pinned
    versions the release was built and tested against. Only FRAMEWORK_FILES
    is checked here (the manifest dict every migration in this package
    uses); there is no other manifest shape to check alongside it.
    """
    migrations_dir = REPO_ROOT / 'scripts' / 'migrations'
    violations = []

    for stem in _discover_migration_modules(migrations_dir):
        module = importlib.import_module(f'migrations.{stem}')
        framework_files = getattr(module, 'FRAMEWORK_FILES', None)
        if not framework_files:
            continue

        has_package_json = 'package.json' in framework_files
        has_lockfile = 'package-lock.json' in framework_files
        if has_package_json != has_lockfile:
            if stem in FROZEN_LOCKFILE_PAIRING_VIOLATIONS:
                continue
            violations.append(
                f"{stem}: package.json={has_package_json}, "
                f"package-lock.json={has_lockfile}"
            )

    assert not violations, (
        "FRAMEWORK_FILES must ship package.json and package-lock.json as a "
        "pair (both present or both absent):\n" + "\n".join(violations)
    )
