"""
Every Workflow Runs the Same Python

The site build, the upgrade, the debt gate and the framework's own tests all
set up Python in GitHub Actions. They name one release, so the tests run on
the Python that builds a site: a standard-library difference between two
releases (html.parser's reading of a malformed character reference, between
3.11 and 3.14) otherwise reaches published sites without a test seeing it.
3.12 is that release because its Unicode tables match Ruby 3.2's, which
Jekyll builds the site with.

Version: v1.8.0
"""

import os
import re

WORKFLOWS = os.path.join(os.path.dirname(__file__), '..', '..', '.github', 'workflows')
PYTHON_VERSION = re.compile(r"^\s*python-version:\s*['\"]?([^'\"\s#]+)", re.MULTILINE)


def _python_versions():
    versions = {}
    for name in sorted(os.listdir(WORKFLOWS)):
        if not name.endswith(('.yml', '.yaml')):
            continue
        with open(os.path.join(WORKFLOWS, name), encoding='utf-8') as f:
            for found in PYTHON_VERSION.findall(f.read()):
                versions.setdefault(found, []).append(name)
    return versions


def test_every_workflow_names_python_3_12():
    versions = _python_versions()
    assert versions, 'no workflow sets up Python'
    assert set(versions) == {'3.12'}, versions


def test_the_site_build_and_the_tests_both_set_up_python():
    names = {name for found in _python_versions().values() for name in found}
    assert {'build.yml', 'telar-tests.yml'} <= names, names
