"""Unit Tests for the Upgrade Report Being the Same Twice

`UPGRADE_SUMMARY.md` is committed to a site's own repository, so its
contents are a diff its owner reads. A summary whose lines move between
runs makes every re-run look like a change, and makes two rehearsals of one
release impossible to compare — which is how the equivalence harness found
this: the same upgrade, on identical code, listed its removals in a
different order each time, because the set it iterated was a set.

Python randomises string hashing per process, so a single process cannot
see this. These tests run the chain in two subprocesses with different
`PYTHONHASHSEED` values and compare.

Version: v1.8.0
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Collect every record description, in order, for one migration — printed as
# JSON so the parent compares values rather than formatting.
PROBE = '''
import json, sys, tempfile, pathlib, io, contextlib
sys.path.insert(0, {scripts!r})
import telar_upgrade as upgrade
from migrations.base import FetchResult, FetchOutcome, coerce_change

out = []
for cls in upgrade.discover_migrations():
    root = tempfile.mkdtemp()
    pathlib.Path(root, '_config.yml').write_text(
        'telar_language: "en"\\ntelar:\\n  version: "%s"\\n' % cls.from_version,
        encoding='utf-8')
    migration = cls(root)
    migration._fetch_result = (
        lambda p, branch=None, timeout=10: FetchResult('x', FetchOutcome.OK))
    migration._fetch_from_github = lambda p, branch=None, timeout=10: 'x'
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            records = [coerce_change(c) for c in migration.apply()]
    except Exception as error:
        out.append([cls.__name__, 'RAISED ' + type(error).__name__])
        continue
    for record in records:
        out.append([cls.__name__, record.description])
print(json.dumps(out))
'''


def _records_under(seed):
    environment = dict(os.environ, PYTHONHASHSEED=str(seed))
    result = subprocess.run(
        [sys.executable, '-c', PROBE.format(scripts=str(ROOT / 'scripts'))],
        capture_output=True, text=True, env=environment, cwd=str(ROOT))
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.strip().split('\n')[-1])


@pytest.fixture(scope='module')
def two_runs():
    return _records_under(0), _records_under(12345)


class TestTheSameUpgradeReportsTheSameThing:

    def test_the_records_are_identical_in_order(self, two_runs):
        first, second = two_runs

        assert first == second

    def test_the_probe_actually_collected_something(self, two_runs):
        """Guards the failure mode this test is itself exposed to.

        A probe that produced nothing compares equal to another probe that
        produced nothing, which is a green run that measured no records at
        all — the same shape as a filter whose input never arrived.
        """
        first, _ = two_runs

        assert len(first) > 100

    def test_no_migration_raised(self, two_runs):
        """A migration that raises contributes one line instead of many.

        Two runs would still agree, so the comparison above would pass while
        most of the chain went unmeasured.
        """
        first, _ = two_runs
        raised = [row for row in first if row[1].startswith('RAISED ')]

        assert raised == []
