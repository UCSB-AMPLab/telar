"""Unit Tests for a Core Sheet That Fails to Convert

Every page depends on `project.csv` and `objects.csv`: the project sheet
lists the stories, and the objects sheet is what every step frames. So a
build that cannot convert either one stops, naming the file and the error,
rather than deploying a site without it. A story sheet that fails to
convert drops only that story, and the build goes on.

A missing sheet is not a failure: a site may have no objects.

Driven through real subprocesses with sheets pandas cannot parse, since the
subject is an exit code and a parse error is how a sheet actually breaks.

Version: v1.8.0
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from telar import core
from telar.core import SHEET_REFUSED_EXIT

PROJECT = ('order,story_id,title\n'
           '1,story-one,One\n'
           '2,story-two,Two\n')
OBJECTS = 'object_id,title\nobj-a,A\n'
STORY = 'step,question,answer,object,x,y,zoom\n1,Q,A,obj-a,0.5,0.5,1\n'
# An opened quote that never closes: pandas raises rather than warns.
UNPARSEABLE = 'object_id,title\nobj-a,"A\n'


def _site(root, sheets):
    (root / '_config.yml').write_text('title: t\ntelar_language: en\n', encoding='utf-8')
    spreadsheets = root / 'telar-content' / 'spreadsheets'
    spreadsheets.mkdir(parents=True)
    for name, text in sheets.items():
        (spreadsheets / name).write_text(text, encoding='utf-8')
    return root


def _run(root):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / 'csv_to_json.py')],
        cwd=root, capture_output=True, text=True, timeout=60,
        env={**os.environ, 'PYTHONPATH': str(SCRIPTS)},
    )


def _stops_on(result, name):
    refused = [line for line in result.stderr.splitlines() if line.startswith('❌')]
    return any(name in line for line in refused)


class TestAnObjectsSheetThatCannotBeRead:

    def test_the_build_stops_and_names_it(self, tmp_path):
        site = _site(tmp_path, {'project.csv': PROJECT, 'objects.csv': UNPARSEABLE,
                                'story-one.csv': STORY})
        result = _run(site)

        assert result.returncode == SHEET_REFUSED_EXIT
        assert _stops_on(result, 'objects.csv')
        assert (site / '_data' / 'project.json').exists()
        assert (site / '_data' / 'story-one.json').exists()

    def test_the_output_of_an_earlier_build_is_deleted(self, tmp_path):
        site = _site(tmp_path, {'project.csv': PROJECT, 'objects.csv': OBJECTS})
        assert _run(site).returncode == 0
        assert (site / '_data' / 'objects.json').exists()

        (site / 'telar-content' / 'spreadsheets' / 'objects.csv').write_text(
            UNPARSEABLE, encoding='utf-8')
        result = _run(site)

        assert result.returncode == SHEET_REFUSED_EXIT
        assert not (site / '_data' / 'objects.json').exists()


class TestAProjectSheetThatCannotBeRead:

    def test_an_empty_file_stops_the_build(self, tmp_path):
        site = _site(tmp_path, {'project.csv': '', 'objects.csv': OBJECTS})
        result = _run(site)

        assert result.returncode == SHEET_REFUSED_EXIT
        assert _stops_on(result, 'project.csv')
        assert (site / '_data' / 'objects.json').exists()


class TestAStoryThatCannotBeRead:

    def test_only_that_story_is_dropped(self, tmp_path):
        site = _site(tmp_path, {'project.csv': PROJECT, 'objects.csv': OBJECTS,
                                'story-one.csv': STORY,
                                'story-two.csv': 'step,question\n1,"Q\n'})
        result = _run(site)

        assert result.returncode == 0
        assert 'story-two.csv' in result.stdout
        assert (site / '_data' / 'story-one.json').exists()
        assert not (site / '_data' / 'story-two.json').exists()


class TestAMissingSheetIsNotAFailure:

    def test_a_site_with_no_objects_sheet_builds(self, tmp_path):
        site = _site(tmp_path, {'project.csv': PROJECT, 'story-one.csv': STORY})
        assert _run(site).returncode == 0


class TestTheProtectedCheckStillSpeaks:

    def test_a_core_failure_and_a_protected_block_are_both_printed(self, tmp_path):
        site = _site(tmp_path, {
            'project.csv': 'order,story_id,title,protected\n1,locked,Locked,yes\n',
            'objects.csv': UNPARSEABLE,
            'locked.csv': STORY,
        })
        result = _run(site)

        assert result.returncode == SHEET_REFUSED_EXIT
        assert _stops_on(result, 'objects.csv')
        assert 'story_key' in result.stdout


class TestAFailureDoesNotOutliveItsRun:

    def test_a_clean_run_after_a_failed_one_exits_zero(self, tmp_path, monkeypatch):
        site = _site(tmp_path, {'project.csv': PROJECT, 'objects.csv': UNPARSEABLE})
        monkeypatch.chdir(site)
        monkeypatch.setattr(sys, 'argv', ['csv_to_json.py'])

        with pytest.raises(SystemExit) as failed:
            core.main()
        assert failed.value.code == SHEET_REFUSED_EXIT

        (site / 'telar-content' / 'spreadsheets' / 'objects.csv').write_text(
            OBJECTS, encoding='utf-8')
        core.main()

        assert (site / '_data' / 'objects.json').exists()


class TestTheUpgradeSeesWhy:

    def test_regeneration_fails_and_names_the_sheet(self, tmp_path, capsys):
        import telar_upgrade_regen as regen

        site = _site(tmp_path, {'project.csv': PROJECT, 'objects.csv': UNPARSEABLE})
        (site / 'scripts').symlink_to(SCRIPTS)

        csv_ok, _, protected_blocked = regen._regenerate_data_files(str(site))

        assert csv_ok is False
        assert protected_blocked is False
        printed = capsys.readouterr().out
        assert 'objects.csv' in printed
        assert 'EOF inside string' in printed or 'Error tokenizing' in printed
