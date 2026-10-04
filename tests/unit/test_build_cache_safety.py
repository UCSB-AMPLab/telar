"""Unit Tests for the Build Workflow's Cache Decisions

The workflow decides whether to regenerate IIIF tiles and audio waveforms by
reading the last commit's diff. That answers whether the artefacts need
rebuilding; it does not answer whether any exist to fall back on. GitHub
evicts a cache after seven days without access, so the two questions come
apart on any repository that goes quiet — and when they do, every step
reports success and the site deploys without its images.

These tests hold the two properties that keep the skip path honest: the
decision is re-checked against what the cache actually produced, and the
cache key moves when either input to a tile moves.

They assert on the workflow text because the logic lives in shell inside
YAML, where nothing else can reach it. That makes them a guard against the
shape being removed or renamed, not a proof that the shell is correct.

Version: v1.8.0
"""

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


class TestTheTileCacheKeyMovesWithTheBaseUrl:
    """Tiles bake the site's base URL into each info.json `@id`.

    An Actions cache entry is immutable per key, so a key that hashes the
    images alone can never be overwritten by tiles built for a corrected
    address. The site restores the old ones and reverts the correction.
    """

    def test_both_key_sites_hash_the_config(self, workflow_steps):
        keys = [step['with']['key'] for step in workflow_steps
                if 'with' in step and isinstance(step.get('with'), dict)
                and str(step['with'].get('key', '')).startswith('iiif-tiles-')]

        assert len(keys) == 2, keys
        for key in keys:
            assert "'_config.yml'" in key, key
            assert "'telar-content/objects/**'" in key, key

    def test_the_save_key_matches_the_restore_key(self, workflow_steps):
        """A save under a key nothing restores from is a cache that never hits."""
        keys = {step['with']['key'] for step in workflow_steps
                if 'with' in step and isinstance(step.get('with'), dict)
                and str(step['with'].get('key', '')).startswith('iiif-tiles-')}

        assert len(keys) == 1, keys


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
