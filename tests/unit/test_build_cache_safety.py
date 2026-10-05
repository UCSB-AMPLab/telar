"""Unit Tests for the Build Workflow's Cache Decisions

The workflow decides whether to regenerate IIIF tiles and audio waveforms by
reading the last commit's diff. That answers whether the artefacts need
rebuilding; it does not answer whether any exist to fall back on. GitHub
evicts a cache after seven days without access, so the two questions come
apart on any repository that goes quiet — and when they do, every step
reports success and the site deploys without its images.

These tests hold the two properties that keep the skip path honest: the
decision is re-checked against what the cache actually produced, and the
cache key moves when any input to a tile moves.

The decisions are asserted on the workflow text, because that logic lives
in shell inside YAML, where nothing else can reach it; that makes them a
guard against the shape being removed or renamed, not a proof that the
shell is correct. The tile key is computed by a step of its own, which the
tests run.

Version: v1.8.0
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github' / 'workflows' / 'build.yml'


@pytest.fixture(scope='module')
def workflow_text():
    return WORKFLOW.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def workflow_steps(workflow_text):
    parsed = yaml.safe_load(workflow_text)
    steps = []
    for job in parsed['jobs'].values():
        steps.extend(job.get('steps', []))
    return steps


def _step(steps, name_fragment):
    matches = [s for s in steps if name_fragment in s.get('name', '')]
    assert len(matches) == 1, (name_fragment, [s.get('name') for s in matches])
    return matches[0]


def _tile_key_steps(steps):
    return [step for step in steps
            if isinstance(step.get('with'), dict)
            and str(step['with'].get('key', '')).startswith('iiif-tiles-')]


class TestTheTileCacheKey:
    """An Actions cache entry is immutable per key, so the key has to move
    whenever the tiles would differ, or a push that skips regeneration
    restores tiles built for the old input. The tiles depend on each image's
    bytes and name (a tile directory is named by object ID), on the objects
    sheet (which objects are self-hosted), and on _config.yml (the base URL
    is baked into each info.json `@id`)."""

    def test_the_restore_and_the_save_use_the_one_computed_hash(self, workflow_steps):
        """A save under a key nothing restores from is a cache that never hits."""
        keys = [step['with']['key'] for step in _tile_key_steps(workflow_steps)]

        assert keys == ['iiif-tiles-${{ steps.tile-inputs.outputs.hash }}'] * 2

    def test_the_hash_is_computed_after_the_fetch_and_before_the_restore(self, workflow_steps):
        """A Google Sheets site has its objects sheet on disk only after the fetch."""
        names = [step.get('name', '') for step in workflow_steps]
        hashing = _step(workflow_steps, 'Hash the IIIF tile inputs')

        assert hashing['id'] == 'tile-inputs'
        assert names.index(_step(workflow_steps, 'Fetch data from Google Sheets')['name']) \
            < names.index(hashing['name'])
        assert all(names.index(hashing['name']) < names.index(step['name'])
                   for step in _tile_key_steps(workflow_steps))

    @pytest.fixture
    def key(self, workflow_steps, tmp_path):
        run = _step(workflow_steps, 'Hash the IIIF tile inputs')['run']

        def compute(site):
            output = tmp_path / 'github-output'
            output.write_text('', encoding='utf-8')
            subprocess.run(['bash', '-e', '-c', run], cwd=site, check=True,
                           env={**os.environ, 'GITHUB_OUTPUT': str(output)})
            lines = output.read_text(encoding='utf-8').splitlines()
            assert len(lines) == 1 and lines[0].startswith('hash='), lines
            return lines[0][len('hash='):]
        return compute

    @pytest.fixture
    def site(self, tmp_path):
        root = tmp_path / 'site'
        objects = root / 'telar-content' / 'objects'
        sheets = root / 'telar-content' / 'spreadsheets'
        objects.mkdir(parents=True)
        sheets.mkdir()
        (objects / 'map.jpg').write_bytes(b'map image')
        (sheets / 'objects.csv').write_text('object_id,title\nmap,Map\n', encoding='utf-8')
        (sheets / 'story-one.csv').write_text('step,question,answer,object\n1,Q,A,map\n',
                                              encoding='utf-8')
        (root / '_config.yml').write_text('url: https://example.org\n', encoding='utf-8')
        return root

    def test_it_is_the_same_for_the_same_site(self, key, site):
        assert key(site) == key(site)

    def test_a_rename_with_the_same_bytes_moves_it(self, key, site):
        before = key(site)
        objects = site / 'telar-content' / 'objects'
        (objects / 'map.jpg').rename(objects / 'plan.jpg')

        assert key(site) != before

    def test_an_image_edit_moves_it(self, key, site):
        before = key(site)
        (site / 'telar-content' / 'objects' / 'map.jpg').write_bytes(b'another image')

        assert key(site) != before

    @pytest.mark.parametrize('sheet', ['objects.csv', 'objetos.csv'])
    def test_an_objects_sheet_edit_moves_it(self, key, site, sheet):
        sheets = site / 'telar-content' / 'spreadsheets'
        (sheets / 'objects.csv').rename(sheets / sheet)
        before = key(site)
        (sheets / sheet).write_text('object_id,title\nplan,Map\n', encoding='utf-8')

        assert key(site) != before

    def test_a_config_edit_moves_it(self, key, site):
        before = key(site)
        (site / '_config.yml').write_text('url: https://example.com\n', encoding='utf-8')

        assert key(site) != before

    def test_a_story_edit_leaves_it(self, key, site):
        before = key(site)
        (site / 'telar-content' / 'spreadsheets' / 'story-one.csv').write_text(
            'step,question,answer,object\n1,Q,Another answer,map\n', encoding='utf-8')

        assert key(site) == before

    def test_a_site_without_objects_has_a_key(self, key, site):
        shutil.rmtree(site / 'telar-content' / 'objects')

        assert key(site)


class TestASkipIsVerifiedAgainstTheCache:
    """The decision to skip has to survive the cache not answering."""

    def test_the_tile_decision_rechecks_the_cache_directory(self, workflow_steps):
        detect = _step(workflow_steps, 'Detect if IIIF regeneration is needed')

        # The re-check must run after the diff has had its say, and must be
        # able to overturn it — a read-only check would report the problem
        # and still deploy the broken site.
        assert 'cached-iiif' in detect['run']
        assert detect['run'].index('cached-iiif') > detect['run'].index('CHANGED_FILES')
        assert 'NEEDS_IIIF="true"' in detect['run'].split('cached-iiif')[-1]

    def test_the_audio_decision_rechecks_the_cache_directory(self, workflow_steps):
        detect = _step(workflow_steps, 'Detect if audio regeneration is needed')

        assert 'cached-audio' in detect['run']
        assert 'NEEDS_AUDIO="true"' in detect['run'].split('cached-audio')[-1]

    def test_the_audio_recheck_knows_a_site_can_have_no_audio(self, workflow_steps):
        """An empty cache is correct for a site with no audio objects.

        Without that distinction the re-check would reprocess on every build
        of every site that has never had audio, which is most of them.
        """
        detect = _step(workflow_steps, 'Detect if audio regeneration is needed')

        assert 'HAVE_AUDIO' in detect['run']

    def test_the_tile_recheck_knows_a_site_can_have_no_objects(self, workflow_steps):
        detect = _step(workflow_steps, 'Detect if IIIF regeneration is needed')
        recheck = detect['run'].split('cached-iiif')[0].rsplit('NEEDS_IIIF="false"', 1)[-1]

        assert 'telar-content/objects' in recheck


class TestTheSkipPathNoLongerPromisesToWarn:
    """The warning was the whole of the old safety story, and it was not one.

    `Warning: No cached IIIF tiles found. Site may have missing images.`
    printed on a green run that deployed a broken site. With the decision
    re-checked upstream, that branch is now reachable only when there is
    genuinely nothing to restore, so it must not read like a failure.
    """

    def test_no_step_warns_about_missing_tiles_and_continues(self, workflow_text):
        assert 'Site may have missing images' not in workflow_text
