"""Unit Tests for the Version Stamp Actually Landing in _config.yml

The stamp is the last thing an upgrade writes and the first thing the
next one reads. `apply_config_version` rewrites `telar.version` and
`telar.release_date` where they exist, and inserts `release_date` beside
an existing `version` — but it used to do nothing at all with a `telar:`
section that declared neither key, and report `modified=False`.

Upstream, a config with no version reads as 0.2.0-beta, so such a site
ran the whole migration chain, had its content migrated, and finished
with nothing recording that. The next run read 0.2.0-beta again and ran
the chain over content that was already current.

None of the artefacts noticed. The engine wrote `UPGRADE_VERSION.txt` at
the latest version, and the workflow named a branch and wrote a commit
message from it.

Reachable only on a hand-edited file: every framework tag from
v0.1.0-beta on ships a template carrying both keys. The weight is in
what happens afterwards, not in how often.

**What these tests do not cover:** the wiring in `main()` between
reading the stamp back and putting the manual step in the summary. It
needs a whole site to exercise, and it is asserted here only as far as
`generate_checklist` carrying a step it is handed.

Version: v1.8.0
"""

import ast
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar_upgrade as upgrade
from migrations.base import apply_config_version


def _telar(content):
    """The telar section as YAML sees it, which is what every reader sees."""
    return (yaml.safe_load(content) or {}).get('telar')


class TestASectionThatDeclaresNoVersion:

    def test_the_stamp_is_written_into_it(self):
        config = 'title: X\ntelar:\n  story_key: abc\nother: y\n'

        out, modified = apply_config_version(config, '1.8.0', '2026-09-14')

        assert modified is True
        assert _telar(out) == {'version': '1.8.0',
                               'release_date': '2026-09-14',
                               'story_key': 'abc'}

    def test_the_rest_of_the_file_is_untouched(self):
        config = 'title: X\ntelar:\n  story_key: abc\n  # a note\nother: y\n'

        out, _ = apply_config_version(config, '1.8.0', '2026-09-14')

        assert '# a note' in out
        assert out.startswith('title: X\n')
        assert out.rstrip('\n').endswith('other: y')

    @pytest.mark.parametrize('indent', ['  ', '    ', ' '])
    def test_the_sections_own_indent_is_used(self, indent):
        """A stamp at a different indent than its neighbours is still valid
        YAML in some cases and a parse error in others. Follow the file.

        Tabs are not parametrised here: YAML forbids them as indentation
        outright, so a tab-indented section is a file no reader can load,
        with or without a stamp in it. The section detection accepts one
        so that such a file is not silently treated as having no `telar:`
        block, which is a different question from what to write into it.
        """
        config = 'telar:\n%sstory_key: abc\n' % indent

        out, _ = apply_config_version(config, '1.8.0', '2026-09-14')

        assert _telar(out)['version'] == '1.8.0'
        assert ('%sversion: "1.8.0"' % indent) in out

    def test_an_empty_section_gets_the_stamp(self):
        config = 'telar:\nother: y\n'

        out, modified = apply_config_version(config, '1.8.0', '2026-09-14')

        assert modified is True
        assert _telar(out) == {'version': '1.8.0', 'release_date': '2026-09-14'}

    def test_a_release_date_without_a_version_is_not_duplicated(self):
        """The insert is one-directional in the other case, so this one has
        to add the missing half only."""
        config = 'telar:\n  release_date: "2026-01-01"\n  story_key: abc\n'

        out, _ = apply_config_version(config, '1.8.0', '2026-09-14')

        assert out.count('release_date:') == 1
        assert _telar(out) == {'version': '1.8.0',
                               'release_date': '2026-09-14',
                               'story_key': 'abc'}


class TestLinesThatLookLikeTheSectionAndAreNot:
    """`startswith('telar:')` matched three things that are not the section.

    Found by an adversarial review of this change, not by these tests,
    which is why they are written from the inputs rather than from the
    code: each one produced a file no YAML parser would read, and the
    engine reads this file back on the next run.
    """

    def test_an_inline_mapping_is_left_alone(self):
        """`telar: {…}` cannot take block entries below it."""
        config = 'telar: {story_key: abc}\nother: x\n'

        out, modified = apply_config_version(config, '1.8.0', '2026-09-14')

        assert modified is False
        assert out == config

    def test_a_key_that_merely_starts_with_telar_is_not_the_section(self):
        """`telar:custom:` is a valid key of its own."""
        config = 'telar:custom:\n  story_key: abc\n'

        out, modified = apply_config_version(config, '1.8.0', '2026-09-14')

        assert modified is False
        assert out == config

    def test_a_trailing_comment_on_the_header_is_still_the_section(self):
        """The inverse, so the pattern is not tightened into uselessness."""
        config = 'telar:  # the framework block\n  story_key: abc\n'

        _, modified = apply_config_version(config, '1.8.0', '2026-09-14')

        assert modified is True


class TestCommentsInsideTheSection:
    """A comment can sit at any column without being wrong, which is what
    made both of these produce unparseable output."""

    def test_the_indent_comes_from_an_entry_not_a_comment(self):
        config = 'telar:\n    # note\n  story_key: abc\n'

        out, _ = apply_config_version(config, '1.8.0', '2026-09-14')

        assert _telar(out) == {'version': '1.8.0',
                               'release_date': '2026-09-14',
                               'story_key': 'abc'}

    def test_a_comment_at_column_zero_does_not_end_the_section(self):
        """YAML does not close a block mapping on one, and treating it as
        the end put the stamp outside the section."""
        config = 'telar:\n# note\n    story_key: abc\n'

        out, _ = apply_config_version(config, '1.8.0', '2026-09-14')

        assert _telar(out) == {'version': '1.8.0',
                               'release_date': '2026-09-14',
                               'story_key': 'abc'}


class TestTwoSectionsNamedTelar:
    """Duplicate top-level keys are legal input and PyYAML keeps the last,
    so the last section is the one a reader sees."""

    def test_the_section_that_wins_is_the_one_stamped(self):
        config = 'telar:\n  story_key: a\ntelar:\n  story_key: b\n'

        out, _ = apply_config_version(config, '1.8.0', '2026-09-14')

        assert _telar(out) == {'version': '1.8.0',
                               'release_date': '2026-09-14',
                               'story_key': 'b'}

    def test_the_first_sections_indent_is_not_carried_to_the_second(self):
        config = ('telar:\n    story_key: a\nother: x\n'
                  'telar:\n  story_key: b\n')

        out, _ = apply_config_version(config, '1.8.0', '2026-09-14')

        assert _telar(out)['version'] == '1.8.0'
        assert '  version: "1.8.0"' in out
        assert '    version: "1.8.0"' not in out


class TestWhatTheWriterStillRefusesToDo:

    def test_a_file_with_no_telar_section_is_left_alone(self):
        """Deliberate, and the reason the manual step exists.

        Creating the section means deciding where it goes and what else
        belongs in it, in a file this writer only ever edits in place.
        """
        config = 'title: X\nfoo: bar\n'

        out, modified = apply_config_version(config, '1.8.0', '2026-09-14')

        assert modified is False
        assert out == config


class TestTheSummaryCarriesAStepTheRunFound:
    """The manual steps section is what the Actions route copies into the
    issue the site's owner reads, so it is where a stamp that did not land
    has to appear."""

    def _step(self):
        return [{'description': 'add the telar section', 'audience': 'all'}]

    def test_the_step_reaches_the_summary(self):
        summary = upgrade.generate_checklist(
            migrations=[], all_changes=[], from_version='0.2.0-beta',
            to_version='1.8.0', extra_manual_steps=self._step())

        assert 'add the telar section' in summary

    def test_it_is_counted_as_a_manual_step(self):
        summary = upgrade.generate_checklist(
            migrations=[], all_changes=[], from_version='0.2.0-beta',
            to_version='1.8.0', extra_manual_steps=self._step())

        assert 'Manual steps:** 1' in summary

    def test_without_one_the_summary_counts_none(self):
        """Counted, not searched for by phrase.

        Asserting only that a particular sentence is absent passes when
        the count is wrong in the other direction, which an adversarial
        review demonstrated by making the renderer report one step where
        there were none.
        """
        summary = upgrade.generate_checklist(
            migrations=[], all_changes=[], from_version='0.2.0-beta',
            to_version='1.8.0')

        assert 'Manual steps:** 0' in summary
        assert 'add the telar section' not in summary


class TestTheRunHandsItsStepToTheSummary:
    """The wiring the tests above cannot reach.

    They pass a step straight to `generate_checklist`, so every one of
    them still passes if `main()` stops passing its own. Exercising it
    properly needs a whole site and a completed upgrade; read off the
    source instead, which is the same thing this suite does for the
    `ChangeRecord` literals.
    """

    def _main_source(self):
        path = os.path.join(os.path.dirname(__file__), '..', '..',
                            'scripts', 'telar_upgrade.py')
        tree = ast.parse(open(path, encoding='utf-8').read())
        return next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == 'main')

    def test_main_passes_the_steps_it_collected(self):
        calls = [node for node in ast.walk(self._main_source())
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)
                 and node.func.id == 'generate_checklist']

        assert calls, 'main() should still build a summary'
        assert any(keyword.arg == 'extra_manual_steps'
                   for call in calls for keyword in call.keywords)

    def test_main_reads_the_stamp_back(self):
        """The other half: the step list is only ever non-empty because
        something checked what the file says after writing it."""
        names = {node.func.id for node in ast.walk(self._main_source())
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)}

        assert 'detect_current_version' in names

    def test_an_extra_step_is_not_filtered_by_audience(self):
        """The run found this site in this state; there is no one else the
        step could be addressed to."""
        step = [{'description': 'add the telar section',
                 'audience': 'google-sheets'}]

        summary = upgrade.generate_checklist(
            migrations=[], all_changes=[], from_version='0.2.0-beta',
            to_version='1.8.0', sheets_enabled=False, extra_manual_steps=step)

        assert 'add the telar section' in summary
