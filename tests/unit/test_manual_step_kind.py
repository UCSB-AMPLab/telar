"""Unit Tests for the Kind of a Migration's Manual Steps

A manual step is one of three things: something the upgrade left undone
that the reader may need to do, something they may do if they want, or an
account of what changed. The prose has always said which ("No action
required", "Optional —"), and nothing could read it, so the Compositor's
post-upgrade screen listed every step of every release under a heading
telling the reader to complete them all.

The Compositor now groups that screen by `kind` and holds its own table for
the releases published before the field existed. From 1.8.0 the framework
declares the field itself. A step without it is shown apart from the
others, and while one is shown the screen cannot tell its reader that
nothing is left to do, so the gap must fail here rather than on that screen.

The classification pinned below is the one approved for the Compositor's
table, on the same steps, so the two routes describe each step alike.

Version: v1.8.0
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar_upgrade as upgrade
from migrations.base import MANUAL_STEP_KINDS


def _site(directory, lang):
    (directory / '_config.yml').write_text(
        'telar_language: "%s"\n' % lang, encoding='utf-8')
    return str(directory)


def _steps_by_migration(repo_root):
    return {cls.__module__.rsplit('.', 1)[-1]: cls(repo_root).get_manual_steps()
            for cls in upgrade.discover_migrations()}


A, O, N = 'action', 'optional', 'note'

# Steps a migration adds only when the site calls for them are not listed:
# v154_to_v160's `.gitattributes` step is optional, and is checked below.
APPROVED = {
    'v020_to_v090': [A, A, A, A, O],
    'v091_to_v092': [A, A],
    'v092_to_v093': [N, A],
    'v093_to_v094': [N, A],
    'v094_to_v100': [A, A],
    'v100_to_v110': [N],
    'v110_to_v120': [N],
    'v120_to_v121': [N],
    'v121_to_v130': [N],
    'v130_to_v140': [A],
    'v140_to_v150': [A, A],
    'v150_to_v151': [N],
    'v151_to_v152': [N],
    'v152_to_v153': [N, N],
    'v153_to_v154': [N, A],
    'v154_to_v160': [A, A],
    'v160_to_v161': [N],
    'v161_to_v162': [A, A, N],
    'v162_to_v170': [A, A, O, A, N],
    'v170_to_v180': [A, O, O, A, A, N],
}


@pytest.mark.parametrize('lang', ['en', 'es'])
class TestEveryStepDeclaresItsKind:
    """Read off live migration objects, as the audience tests are: some
    migrations build their steps from module constants a text scan misses."""

    def test_every_step_carries_a_kind_we_defined(self, tmp_path, lang):
        wrong = [(name, step.get('kind'))
                 for name, steps in _steps_by_migration(_site(tmp_path, lang)).items()
                 for step in steps if step.get('kind') not in MANUAL_STEP_KINDS]

        assert wrong == []

    def test_the_classification_is_the_approved_one(self, tmp_path, lang):
        kinds = {name: [step['kind'] for step in steps]
                 for name, steps in _steps_by_migration(_site(tmp_path, lang)).items()
                 if steps}

        assert kinds == APPROVED


def test_the_conditional_gitattributes_step_is_optional(tmp_path):
    """v154_to_v160 adds a third step only when the upgrade left a site's
    own `.gitattributes` alone, which it records while applying; the
    fixture above never applies, so it never sees the step."""
    for lang in ('en', 'es'):
        directory = tmp_path / lang
        directory.mkdir()
        root = _site(directory, lang)
        migration = next(cls for cls in upgrade.discover_migrations()
                         if cls.__module__.endswith('v154_to_v160'))(root)
        migration._gitattributes_skipped = True
        steps = migration.get_manual_steps()

        assert [step['kind'] for step in steps] == [A, A, O], lang


def test_all_three_kinds_are_in_use(tmp_path):
    """Guards against a sweep that tagged every step the same way."""
    used = {step['kind']
            for steps in _steps_by_migration(_site(tmp_path, 'en')).values()
            for step in steps}

    assert used == set(MANUAL_STEP_KINDS)
