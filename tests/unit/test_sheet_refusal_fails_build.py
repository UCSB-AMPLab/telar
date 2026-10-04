"""Unit Tests for a Refused Sheet Failing the Build

`ColumnCollisionError` and `ReservedColumnError` stop a sheet from
converting: two columns that mean one thing, or a column named
`_metadata`. A build that carried on past either would deploy the site
without that sheet — every object page, for a refused `objects.csv` —
and report success.

So a refused sheet fails the build. Every sheet is converted first, so
one build names every refused sheet, and a refused sheet's earlier output
is deleted so a warm build cannot serve it. Other conversion errors drop
their sheet and exit 0.

Driven through real subprocesses where the subject is an exit code.

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
from telar.core import SHEET_REFUSED_EXIT, PROTECTED_PREREQUISITE_EXIT

PROJECT = 'key,value\nproject_title,Test\n'
OBJECTS = 'object_id,title,medium_genre\nobj-a,A,Map\n'
COLLIDING_OBJECTS = 'object_id,title,medium_genre,medium\nobj-a,A,Map,\n'
STORY = 'step,question,answer,object,x,y,zoom\n1,Q,A,obj-a,0.5,0.5,1\n'
RESERVED_STORY = 'step,question,answer,object,x,y,zoom,_metadata\n1,Q,A,obj-a,0.5,0.5,1,\n'
GLOSSARY = 'term_id,title,definition\nencomienda,Encomienda,A grant.\n'


def _site(root, sheets):
    """A site with only what csv_to_json.py reads."""
    (root / '_config.yml').write_text('title: t\ntelar_language: en\n', encoding='utf-8')
    spreadsheets = root / 'telar-content' / 'spreadsheets'
    spreadsheets.mkdir(parents=True)
    for name, text in sheets.items():
        (spreadsheets / name).write_text(text, encoding='utf-8')
    return root


def _run(root, script='csv_to_json.py'):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script)],
        cwd=root, capture_output=True, text=True, timeout=60,
        env={**os.environ, 'PYTHONPATH': str(SCRIPTS)},
    )


class TestTheExitCode:

    def test_it_is_neither_success_nor_the_protected_code(self):
        assert SHEET_REFUSED_EXIT not in (0, 1, PROTECTED_PREREQUISITE_EXIT)


class TestARefusedObjectsSheet:

    def test_the_build_fails_and_the_other_sheets_still_convert(self, tmp_path):
        site = _site(tmp_path, {'project.csv': PROJECT,
                                'objects.csv': COLLIDING_OBJECTS,
                                'story-one.csv': STORY})
        result = _run(site)

        assert result.returncode == SHEET_REFUSED_EXIT
        assert 'objects.csv' in result.stderr
        assert "'medium' is claimed by" in result.stderr
        assert (site / '_data' / 'project.json').exists()
        assert (site / '_data' / 'story-one.json').exists()
        assert not (site / '_data' / 'objects.json').exists()

    def test_the_output_of_an_earlier_build_is_deleted(self, tmp_path):
        """The stale-data cleanup keeps objects.json whatever its source
        does, so a warm build would otherwise serve the last good copy."""
        site = _site(tmp_path, {'project.csv': PROJECT, 'objects.csv': OBJECTS})
        assert _run(site).returncode == 0
        assert (site / '_data' / 'objects.json').exists()

        (site / 'telar-content' / 'spreadsheets' / 'objects.csv').write_text(
            COLLIDING_OBJECTS, encoding='utf-8')
        result = _run(site)

        assert result.returncode == SHEET_REFUSED_EXIT
        assert not (site / '_data' / 'objects.json').exists()

    def test_a_spanish_filename_is_named_as_it_is(self, tmp_path):
        site = _site(tmp_path, {'proyecto.csv': PROJECT,
                                'objetos.csv': COLLIDING_OBJECTS})
        result = _run(site)

        assert result.returncode == SHEET_REFUSED_EXIT
        assert 'objetos.csv' in result.stderr


class TestARefusedProjectOrStorySheet:

    def test_a_refused_project_sheet_fails_the_build(self, tmp_path):
        site = _site(tmp_path, {'project.csv': 'key,value,_metadata\nproject_title,Test,\n',
                                'objects.csv': OBJECTS})
        result = _run(site)

        assert result.returncode == SHEET_REFUSED_EXIT
        assert 'project.csv' in result.stderr
        assert (site / '_data' / 'objects.json').exists()

    def test_a_refused_story_fails_the_build_and_the_others_convert(self, tmp_path):
        site = _site(tmp_path, {'project.csv': PROJECT, 'objects.csv': OBJECTS,
                                'story-one.csv': STORY,
                                'story-two.csv': RESERVED_STORY})
        result = _run(site)

        assert result.returncode == SHEET_REFUSED_EXIT
        assert 'story-two.csv' in result.stderr
        assert 'story-one.csv' not in result.stderr
        assert (site / '_data' / 'story-one.json').exists()
        assert not (site / '_data' / 'story-two.json').exists()

    def test_two_refused_sheets_are_both_named(self, tmp_path):
        site = _site(tmp_path, {'project.csv': PROJECT,
                                'objects.csv': COLLIDING_OBJECTS,
                                'story-two.csv': RESERVED_STORY})
        result = _run(site)

        assert result.returncode == SHEET_REFUSED_EXIT
        assert 'objects.csv' in result.stderr
        assert 'story-two.csv' in result.stderr


class TestARefusedGlossary:
    """Every story reads the glossary, so a refused glossary surfaces
    inside each story's conversion. The file to change is the glossary."""

    def test_it_is_named_once_as_the_glossary(self, tmp_path):
        site = _site(tmp_path, {'project.csv': PROJECT, 'objects.csv': OBJECTS,
                                'story-one.csv': STORY, 'story-two.csv': STORY,
                                'glossary.csv': 'term_id,title,definition,_metadata\n'
                                                'encomienda,Encomienda,A grant.,\n'})
        result = _run(site)

        assert result.returncode == SHEET_REFUSED_EXIT
        refused = [line for line in result.stderr.splitlines() if line.startswith('❌')]
        assert len(refused) == 1
        assert 'glossary.csv' in refused[0]

    def test_generate_collections_names_it_without_a_traceback(self, tmp_path):
        site = _site(tmp_path, {'glossary.csv': 'term_id,title,definition,Title\n'
                                                'encomienda,Encomienda,A grant.,x\n'})
        result = _run(site, 'generate_collections.py')

        assert result.returncode == SHEET_REFUSED_EXIT
        assert 'glossary.csv' in result.stderr
        assert 'Traceback' not in result.stderr


class TestTheProtectedCheckStillSpeaks:

    def test_a_refusal_and_a_protected_block_are_both_printed(self, tmp_path):
        protected_story = ('step,question,answer,object,x,y,zoom\n'
                           '1,Q,A,obj-a,0.5,0.5,1\n')
        site = _site(tmp_path, {
            'project.csv': 'order,story_id,title,protected\n1,locked,Locked,yes\n',
            'objects.csv': COLLIDING_OBJECTS,
            'locked.csv': protected_story,
        })
        result = _run(site)

        assert result.returncode == SHEET_REFUSED_EXIT
        assert 'objects.csv' in result.stderr
        assert 'story_key' in result.stdout


class TestOnlyTheTwoRefusalsFailTheBuild:

    def test_another_conversion_error_still_exits_zero(self, tmp_path, monkeypatch):
        """Any other conversion error drops its sheet and exits 0, as before."""
        site = _site(tmp_path, {'project.csv': PROJECT, 'objects.csv': OBJECTS,
                                'story-one.csv': STORY})
        monkeypatch.chdir(site)
        monkeypatch.setattr(sys, 'argv', ['csv_to_json.py'])

        def broken(*args, **kwargs):
            raise RuntimeError('not a refusal')
        monkeypatch.setattr(core, 'process_story', broken)

        core.main()

        assert not (site / '_data' / 'story-one.json').exists()

    def test_a_refusal_does_not_outlive_its_run(self, tmp_path, monkeypatch):
        site = _site(tmp_path, {'project.csv': PROJECT,
                                'objects.csv': COLLIDING_OBJECTS})
        monkeypatch.chdir(site)
        monkeypatch.setattr(sys, 'argv', ['csv_to_json.py'])

        with pytest.raises(SystemExit) as refused:
            core.main()
        assert refused.value.code == SHEET_REFUSED_EXIT

        (site / 'telar-content' / 'spreadsheets' / 'objects.csv').write_text(
            OBJECTS, encoding='utf-8')
        core.main()

        assert (site / '_data' / 'objects.json').exists()


class TestTheUpgradeSeesWhy:
    """The upgrade's regeneration is HARD, so a refusal stops it and a
    re-run after the fix completes. What it prints is the script's stderr."""

    def test_regeneration_fails_and_prints_the_refusal(self, tmp_path, capsys):
        import telar_upgrade_regen as regen

        site = _site(tmp_path, {'project.csv': PROJECT,
                                'objects.csv': COLLIDING_OBJECTS})
        (site / 'scripts').symlink_to(SCRIPTS)

        csv_ok, _, protected_blocked = regen._regenerate_data_files(str(site))

        assert csv_ok is False
        assert protected_blocked is False
        assert "'medium' is claimed by" in capsys.readouterr().out
