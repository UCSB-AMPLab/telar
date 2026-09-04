"""
Unit Tests for the Jekyll Destination Conflict Gate

Jekyll reports two files claiming one destination as a warning and exits 0.
These tests pin the parser against output captured from Jekyll 4.4.1 —
including the `/stories/x/index.html` spelling that an exact-string
comparison of permalinks does not catch, which is why the gate reads
Jekyll's own report rather than predicting destinations.

Version: v1.7.0
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.build_conflicts import (
    find_conflicts,
    format_failure,
    is_complete_build_log,
    strip_ansi,
)


# Captured verbatim from `jekyll build` on Jekyll 4.4.1: a story document
# at /stories/target/ against a page declaring /stories/target/index.html.
REAL_OUTPUT = """Configuration file: /site/_config.yml
            Source: /site
       Destination: /site/_site
      Generating...
          Conflict: The following destination is shared by multiple files.
                    The written file may end up with unexpected contents.
                    /site/_site/stories/target/index.html
                     - /site/_jekyll-files/_stories/target.md
                     - /site/_jekyll-files/_pages/impostor.md
                    
          Conflict: The following destination is shared by multiple files.
                    The written file may end up with unexpected contents.
                    /site/_site/dup/index.html
                     - /site/_jekyll-files/_pages/q1.md
                     - /site/_jekyll-files/_pages/q2.md
                    
                    done in 0.015 seconds.
 Auto-regeneration: disabled.
"""

CLEAN_OUTPUT = """Configuration file: /site/_config.yml
      Generating... 
                    done in 0.014 seconds.
"""


class TestFindConflicts:
    def test_finds_every_conflict(self):
        assert len(find_conflicts(REAL_OUTPUT)) == 2

    def test_reports_the_destination_and_both_files(self):
        first = find_conflicts(REAL_OUTPUT)[0]
        assert "/site/_site/stories/target/index.html" in first
        assert "_stories/target.md" in first
        assert "_pages/impostor.md" in first

    def test_does_not_run_conflicts_together(self):
        # The second block must not absorb the trailing build lines.
        second = find_conflicts(REAL_OUTPUT)[1]
        assert "done in" not in second
        assert "Auto-regeneration" not in second

    def test_clean_build_has_none(self):
        assert find_conflicts(CLEAN_OUTPUT) == []

    def test_empty_output_has_none(self):
        assert find_conflicts("") == []

    def test_colour_codes_do_not_hide_a_conflict(self):
        # Jekyll colours warnings when stdout is a terminal.
        coloured = REAL_OUTPUT.replace(
            "          Conflict:", "\x1b[33m          Conflict:\x1b[0m"
        )
        assert len(find_conflicts(coloured)) == 2

    def test_strip_ansi_leaves_plain_text_alone(self):
        assert strip_ansi("plain") == "plain"


class TestIsCompleteBuildLog:
    """Absence of the warning is evidence only if the warning would print."""

    def test_a_finished_build_qualifies(self):
        assert is_complete_build_log(CLEAN_OUTPUT)

    def test_an_empty_log_does_not(self):
        assert not is_complete_build_log("")

    def test_a_truncated_log_does_not(self):
        assert not is_complete_build_log("Configuration file: /site/_config.yml\n")

    def test_a_warning_suppressed_log_does_not(self):
        # JEKYLL_LOG_LEVEL=error prints neither the completion line nor the
        # conflict warning, so a conflict-free read of it means nothing.
        assert not is_complete_build_log("Configuration file: /site/_config.yml\n"
                                         "       Destination: /site/_site\n")


class TestFalsePositives:
    def test_a_path_containing_the_word_is_not_a_conflict(self):
        # Jekyll prints Source and Destination on every build; a working
        # directory named `Conflict:` would appear in both.
        output = ("Configuration file: /home/x/Conflict: dir/_config.yml\n"
                  "            Source: /home/x/Conflict: dir\n"
                  "       Destination: /home/x/Conflict: dir/_site\n"
                  "                    done in 0.1 seconds.\n")
        assert find_conflicts(output) == []
        assert is_complete_build_log(output)


class TestFormatFailure:
    def test_names_the_count_and_the_remedy(self):
        message = format_failure(find_conflicts(REAL_OUTPUT))
        assert "2 destination conflicts" in message
        assert "own permalink" in message

    def test_singular_for_one(self):
        message = format_failure(["Conflict: x"])
        assert "1 destination conflict:" in message


class TestGateIsWired:
    """A gate nothing calls is not a gate.

    The parser above is pure, so every test of it stays green if the call
    site disappears. These read the two places that must invoke it.
    """

    ROOT = Path(__file__).resolve().parents[2]

    def test_build_workflow_runs_the_check(self):
        workflow = (self.ROOT / '.github' / 'workflows' / 'build.yml').read_text(
            encoding='utf-8'
        )
        assert 'scripts/check_jekyll_conflicts.py' in workflow
        # The check can only read output the build step kept.
        assert 'tee jekyll-build.log' in workflow
        assert 'set -o pipefail' in workflow

    def test_local_builder_runs_the_check(self):
        builder = (self.ROOT / 'scripts' / 'build_local_site.py').read_text(
            encoding='utf-8'
        )
        assert 'find_conflicts' in builder
        assert 'run_jekyll_build()' in builder
        # The plain runner must not be what builds the site any more.
        assert "run_command(\n            'bundle exec jekyll build'" not in builder
