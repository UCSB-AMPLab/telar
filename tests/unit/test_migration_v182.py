"""
Unit Tests for migrations/v181_to_v182.py

These tests guard:

  - the delivery set, derived from the release's own diff against v1.8.1,
    so that a file changed on the release branch and left out of the set
    fails the test until it is added, and the exclusions: no workflow,
    engine, migration module or dev-only path;
  - that the released texts the migration matches are the ones the tags
    hold, so a typo in a constant cannot make the glossary step a no-op;
  - that the migration deletes nothing: Telar's own test files stay on this
    route, and the engine removes its own released copies after the upgrade;
  - the glossary: each released `telar` entry becomes the site language's
    paragraph, with either line ending; an edited entry and an edited
    instruction stay; a site without a glossary is left alone;
  - metadata, manual steps, and registration at the end of the chain.

Network fetches are not exercised here.

Version: v1.8.2
"""

import csv
import io
import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations import v181_to_v182 as module
from migrations.v181_to_v182 import (
    GLOSSARY, INSTRUCTIONS, TELAR_ENTRY_RELEASED, WORKFLOW, Migration181to182,
)
from migrations.v180_to_v181 import Migration180to181
from migrations.base import ChangeStatus, MANUAL_STEP_AUDIENCES, MANUAL_STEP_KINDS
from migrations.discovery import discover_migrations

import telar_upgrade as upgrade


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _git(*args):
    return subprocess.run(['git', '-C', str(REPO_ROOT), *args], capture_output=True, text=True)


TAG = Migration181to182._TARGET_TAG


def _tag_exists():
    return _git('rev-parse', '--verify', '--quiet', f'refs/tags/{TAG}^{{commit}}').returncode == 0


# Before the tag exists the release is whatever this branch has committed.
RELEASE_REF = TAG if _tag_exists() else 'HEAD'

# What never reaches a site through FRAMEWORK_FILES, whatever changed in it:
# the same set as for v1.8.1. The glossary is the site's, corrected in place.
NOT_DELIVERED_PREFIXES = (
    'telar-content/', 'tests/', 'docs/',
    '.github/', 'scripts/migrations/', 'scripts/telar_upgrade', 'assets/audio/peaks/',
)
NOT_DELIVERED_FILES = {
    '_config.yml', '.gitignore', '.gitattributes', 'index.md', 'pages/glossary.md', 'migration.json',
    'UPGRADE_SUMMARY.md', 'UPGRADE_VERSION.txt', 'pytest.ini', 'vitest.config.js',
}


def _delivered(path):
    return path not in NOT_DELIVERED_FILES and not path.startswith(NOT_DELIVERED_PREFIXES)


def _release_diff():
    """(added or changed, removed) paths between v1.8.1 and the release."""
    out = _git('diff', '--name-status', '-M', 'refs/tags/v1.8.1', RELEASE_REF)
    assert out.returncode == 0, out.stderr
    shipped, removed = set(), set()
    for line in out.stdout.splitlines():
        status, *paths = line.split('\t')
        if status.startswith('D'):
            removed.add(paths[0])
        elif status.startswith('R'):
            removed.add(paths[0])
            shipped.add(paths[1])
        else:
            shipped.add(paths[-1])
    return {p for p in shipped if _delivered(p)}, {p for p in removed if _delivered(p)}


def _released_tags():
    out = _git('tag', '-l', 'v*')
    tags = [t for t in out.stdout.split() if '-rc' not in t]
    assert 'v1.8.1' in tags, 'the released tags are not in this checkout'
    return tags


def _glossary_at(tag):
    out = _git('show', f'{tag}:{GLOSSARY}')
    assert out.returncode == 0, out.stderr
    rows = list(csv.reader(io.StringIO(out.stdout)))
    return rows, rows[0].index('definition')


def _definition(tag, first_cell):
    rows, column = _glossary_at(tag)
    return next(r[column] for r in rows if r and first_cell(r[0]))


# ---------- Delivery set ----------

class TestFrameworkFilesDeliverySet:

    def test_the_set_is_every_shipped_change_since_v181(self):
        shipped, _removed = _release_diff()

        assert set(module.FRAMEWORK_FILES) - shipped == set(), 'delivered but not changed'
        assert shipped - set(module.FRAMEWORK_FILES) == set(), 'changed but not delivered'

    def test_nothing_shipped_is_removed(self):
        _shipped, removed = _release_diff()

        assert removed == set()

    def test_the_diff_is_read_from_a_ref_that_exists(self):
        """A diff against a missing ref is empty, and an empty diff would
        make the first check pass against a set of any size."""
        assert _git('rev-parse', '--verify', '--quiet', 'refs/tags/v1.8.1^{commit}').returncode == 0
        shipped, _removed = _release_diff()
        assert len(shipped) >= len(module.FRAMEWORK_FILES) > 0

    def test_no_workflow_engine_or_migration_module(self):
        offenders = [p for p in module.FRAMEWORK_FILES
                     if p.startswith(('.github/', 'scripts/migrations/', 'scripts/telar_upgrade'))]

        assert offenders == []

    def test_no_dev_only_path(self):
        from telar.dev_only_files import read_dev_only_files
        dev_only = read_dev_only_files()
        offenders = [p for p in module.FRAMEWORK_FILES
                     if any(p == d or (d.endswith('/') and p.startswith(d)) for d in dev_only)]

        assert offenders == []

    def test_every_delivered_path_exists_at_the_release_ref(self):
        missing = [p for p in sorted(module.FRAMEWORK_FILES)
                   if _git('cat-file', '-e', f'{RELEASE_REF}:{p}').returncode != 0]

        assert missing == [], f'absent at {RELEASE_REF}: {missing}'

    @pytest.mark.xfail(not _tag_exists(), strict=True,
                       reason='v1.8.2 is not tagged yet; the paths are checked at HEAD until it is')
    def test_the_tag_this_is_checked_against_is_in_the_repository(self):
        assert _tag_exists()

    def test_the_lockfile_ships_with_package_json(self):
        assert {'package.json', 'package-lock.json'} <= set(module.FRAMEWORK_FILES)


# ---------- The released texts ----------

class TestTheReleasedTexts:

    @pytest.mark.parametrize('tag, index', [('v0.9.0-beta', 0), ('v1.5.0', 0),
                                            ('v1.5.1', 1), ('v1.8.1', 1)])
    def test_each_telar_entry_is_the_tags(self, tag, index):
        english, spanish = TELAR_ENTRY_RELEASED[index]

        assert _definition(tag, lambda c: c == 'telar') == english + '\n\n' + spanish

    @pytest.mark.parametrize('prefix, index', [('# Make it', 0), ('# Escr', 1)])
    def test_each_instruction_is_the_tags(self, prefix, index):
        assert _definition('v1.8.1', lambda c: c.startswith(prefix)) == INSTRUCTIONS[index][0]

    def test_no_other_wording_was_released(self):
        entries = {_definition(t, lambda c: c == 'telar') for t in _released_tags()
                   if _git('cat-file', '-e', f'{t}:{GLOSSARY}').returncode == 0}

        assert entries == {e + '\n\n' + s for e, s in TELAR_ENTRY_RELEASED}

    def test_the_template_carries_the_corrected_instructions(self):
        text = (REPO_ROOT / GLOSSARY).read_text(encoding='utf-8')

        for released, current in INSTRUCTIONS:
            assert released not in text
            assert current in text


# ---------- Sites ----------

def _site(tmp_path, lang='en', files=()):
    (tmp_path / '_config.yml').write_text(f'telar_language: "{lang}"\n', encoding='utf-8')
    for rel in files:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('x', encoding='utf-8')
    return Migration181to182(str(tmp_path))


# ---------- Phase 2: the glossary ----------

def _glossary(tmp_path, definition, newline='\n', lang='en', extra_rows=()):
    migration = _site(tmp_path, lang=lang)
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator='\n')
    writer.writerow(['term_id', 'title', 'definition', 'kind'])
    writer.writerow(['# Make it lower-case and avoid spaces.', '# Please provide a title.',
                     INSTRUCTIONS[0][0], '# Optional.'])
    writer.writerow(['# Escríbelo en minúsculas.', '# Incluye un título.',
                     INSTRUCTIONS[1][0], '# Opcional.'])
    writer.writerow(['telar', 'Telar', definition.replace('\n', newline), ''])
    for row in extra_rows:
        writer.writerow(row)
    path = tmp_path / GLOSSARY
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.getvalue().encode('utf-8'))
    return migration, path


def _telar_definition(path):
    rows = list(csv.reader(io.StringIO(path.read_bytes().decode('utf-8'), newline='')))
    return next(r for r in rows if r[0] == 'telar')[2], rows


class TestTheGlossary:

    @pytest.mark.parametrize('index', [0, 1])
    @pytest.mark.parametrize('lang, keep', [('en', 0), ('es', 1)])
    def test_a_released_entry_keeps_the_sites_language(self, tmp_path, index, lang, keep):
        released = TELAR_ENTRY_RELEASED[index]
        migration, path = _glossary(tmp_path, '\n\n'.join(released), lang=lang)

        records = migration._correct_glossary()

        assert _telar_definition(path)[0] == released[keep]
        assert len(records) == 2

    def test_a_crlf_entry_is_matched_and_keeps_its_line_endings(self, tmp_path):
        released = TELAR_ENTRY_RELEASED[1]
        migration, path = _glossary(tmp_path, '\n\n'.join(released), newline='\r\n')

        migration._correct_glossary()

        assert _telar_definition(path)[0] == released[0]

    def test_an_edited_entry_is_left_alone(self, tmp_path):
        edited = TELAR_ENTRY_RELEASED[1][0] + '\n\nOur own note.'
        migration, path = _glossary(tmp_path, edited)

        migration._correct_glossary()

        assert _telar_definition(path)[0] == edited

    def test_the_instructions_are_corrected_and_nothing_else_moves(self, tmp_path):
        extra = [['loom', 'Loom', 'A frame, with "quotes", and commas', '']]
        migration, path = _glossary(tmp_path, 'Already one language.', extra_rows=extra)
        before = path.read_bytes().decode('utf-8')

        migration._correct_glossary()

        after = path.read_bytes().decode('utf-8')
        expected = before
        for released, current in INSTRUCTIONS:
            expected = expected.replace(released, current)
        assert after == expected != before

    def test_an_edited_instruction_is_left_alone(self, tmp_path):
        migration, path = _glossary(tmp_path, 'Already one language.')
        text = path.read_text(encoding='utf-8').replace(INSTRUCTIONS[0][0], 'My own instruction')
        path.write_text(text, encoding='utf-8')

        migration._correct_glossary()

        after = path.read_text(encoding='utf-8')
        assert 'My own instruction' in after
        assert INSTRUCTIONS[1][1] in after

    def test_a_site_without_a_glossary_is_left_alone(self, tmp_path):
        assert _site(tmp_path)._correct_glossary() == []
        assert not (tmp_path / GLOSSARY).exists()


# ---------- Apply ----------

class TestApply:

    def test_it_deletes_nothing(self, tmp_path):
        """Telar's own test files and the engine's copies stay through it."""
        kept = ['tests/unit/test_csv_utils.py', 'pytest.ini', 'vitest.config.js', WORKFLOW,
                'scripts/telar_upgrade.py', 'scripts/migrations/base.py']
        migration = _site(tmp_path, files=kept)
        migration._apply_framework_files = lambda files: []

        migration.apply()

        assert all((tmp_path / p).is_file() for p in kept)

    def test_the_phases_run_in_order(self, tmp_path, monkeypatch):
        seen = []
        monkeypatch.setattr(Migration181to182, '_apply_framework_files',
                            lambda self, files: seen.append(('files', files)) or [])
        monkeypatch.setattr(Migration181to182, '_correct_glossary',
                            lambda self: seen.append('glossary') or [])

        Migration181to182(str(tmp_path)).apply()

        assert seen == [('files', module.FRAMEWORK_FILES), 'glossary']

    def test_a_hard_failure_installing_files_stops_it(self, tmp_path, monkeypatch):
        from migrations.base import ChangeRecord
        failed = ChangeRecord(description='fetch failed', status=ChangeStatus.FAILED,
                              severity='hard')
        monkeypatch.setattr(Migration181to182, '_apply_framework_files', lambda self, files: [failed])
        monkeypatch.setattr(Migration181to182, '_correct_glossary',
                            lambda self: pytest.fail('ran after a hard failure'))

        assert Migration181to182(str(tmp_path)).apply() == [failed]


# ---------- Metadata, steps, registration ----------

class TestMetadataAndSteps:

    def test_versions_and_pin(self):
        assert (Migration181to182.from_version, Migration181to182.to_version) == ('1.8.1', '1.8.2')
        assert Migration181to182._TARGET_TAG == 'v1.8.2'

    @pytest.mark.parametrize('lang', ['en', 'es'])
    def test_the_steps_before_it_runs(self, tmp_path, lang):
        """What the manifest is built from: the Compositor does not trim the
        entry, so it is not told to make the same edit in a sheet."""
        steps = _site(tmp_path, lang=lang).get_manual_steps()

        assert [(s['audience'], s['kind']) for s in steps] == [('local', 'optional')]
        assert WORKFLOW in steps[0]['description']

    @pytest.mark.parametrize('lang', ['en', 'es'])
    def test_the_sheets_step_follows_a_trim(self, tmp_path, lang):
        migration, _path = _glossary(tmp_path, '\n\n'.join(TELAR_ENTRY_RELEASED[1]), lang=lang)

        migration._correct_glossary()
        steps = migration.get_manual_steps()

        assert [(s['audience'], s['kind']) for s in steps] == [('local', 'optional'),
                                                               ('google-sheets', 'action')]
        assert all(s['audience'] in MANUAL_STEP_AUDIENCES for s in steps)
        assert all(s['kind'] in MANUAL_STEP_KINDS for s in steps)

    def test_no_sheets_step_when_the_entry_was_already_one_language(self, tmp_path):
        migration, _path = _glossary(tmp_path, 'Already one language.')

        migration._correct_glossary()

        assert [s['audience'] for s in migration.get_manual_steps()] == ['local']


class TestRegistration:

    def test_discovery_finds_it_and_it_ends_the_chain(self):
        assert Migration181to182 in discover_migrations()
        assert upgrade.MIGRATIONS[-1] is Migration181to182

    def test_it_follows_the_v181_hop(self):
        chain = list(upgrade.MIGRATIONS)
        assert chain[chain.index(Migration180to181) + 1] is Migration181to182

    def test_latest_version_matches_chain_terminus(self):
        assert upgrade.LATEST_VERSION == '1.8.2'
