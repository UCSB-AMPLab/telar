"""
Unit Tests for Upgrade Script Utilities

This module tests utility functions from the upgrade script that are used
to organize and present migration changes to users. The categorization
function groups changes by file type for better readability.

Version: v1.7.0
"""

import sys
import os
import pytest

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar_upgrade import _categorize_changes, _category_from_description
from migrations.base import (
    ChangeCategory, ChangeRecord, category_for_path, coerce_change,
)
from migrations.messages import get_message


class TestCategorizeChanges:
    """Grouping applied changes under the summary's headings.

    A record carrying a category is filed by it. Only a record without one
    is guessed at from its wording, which is what every record was subject
    to before the field existed.
    """

    def _applied(self, *records):
        return _categorize_changes(list(records))

    def test_a_records_own_category_decides(self):
        result = self._applied(
            ChangeRecord(description='Updated _data/languages/en.yml — trama warning',
                         category=ChangeCategory.CONFIGURATION))

        assert result == {ChangeCategory.CONFIGURATION:
                          ['Updated _data/languages/en.yml — trama warning']}

    def test_wording_cannot_move_a_categorised_record(self):
        """The whole point: rephrasing a description changes nothing."""
        first = ChangeRecord(description='Updated the stylesheet',
                             category=ChangeCategory.SCRIPTS)
        second = ChangeRecord(description='Reworked assets/js/telar-story.js',
                              category=ChangeCategory.SCRIPTS)

        assert self._applied(first, second) == {
            ChangeCategory.SCRIPTS: [first.description, second.description]}

    def test_a_record_without_one_is_guessed_at(self):
        result = self._applied(ChangeRecord(description='Updated _config.yml'))

        assert result == {ChangeCategory.CONFIGURATION: ['Updated _config.yml']}

    def test_a_legacy_string_arrives_without_a_category(self):
        """coerce_change wraps a plain string, so the guess still applies."""
        record = coerce_change('Modified _layouts/story.html')

        assert record.category is None
        assert self._applied(record) == {
            ChangeCategory.LAYOUTS: ['Modified _layouts/story.html']}

    def test_an_unknown_category_falls_to_other(self):
        result = self._applied(
            ChangeRecord(description='something', category='invented'))

        assert result == {ChangeCategory.OTHER: ['something']}

    def test_headings_come_out_in_print_order(self):
        result = self._applied(
            ChangeRecord(description='d', category=ChangeCategory.DOCUMENTATION),
            ChangeRecord(description='c', category=ChangeCategory.CONFIGURATION),
            ChangeRecord(description='s', category=ChangeCategory.STYLES))

        assert list(result) == [ChangeCategory.CONFIGURATION,
                               ChangeCategory.STYLES,
                               ChangeCategory.DOCUMENTATION]

    def test_empty_changes_list(self):
        assert _categorize_changes([]) == {}

    def test_empty_categories_are_dropped(self):
        result = self._applied(
            ChangeRecord(description='x', category=ChangeCategory.CONFIGURATION))

        assert list(result) == [ChangeCategory.CONFIGURATION]

    def test_every_category_has_a_heading_in_both_languages(self):
        for category in ChangeCategory.ORDER:
            for lang in ('en', 'es'):
                label = get_message(lang, 'category_' + category)
                assert label != 'category_' + category, (category, lang)


class TestTheDescriptionFallback:
    """Where a record that carries no category of its own is filed.

    Legacy migrations return bare strings, which `coerce_change` wraps
    without a category. The fallback reads the file path out of the
    description and asks `category_for_path`, so the answer is derived from
    the same table an install record answers with, rather than guessed from
    the wording around it.
    """

    def test_it_reads_a_path_out_of_the_sentence(self):
        for description, expected in (
                ('Updated _config.yml with new settings', ChangeCategory.CONFIGURATION),
                ('Modified _layouts/default.html', ChangeCategory.LAYOUTS),
                ('Updated _includes/header.html', ChangeCategory.INCLUDES),
                ('Updated main.scss with new variables', ChangeCategory.STYLES),
                ('Updated README.md', ChangeCategory.DOCUMENTATION),
                ('Skipped .gitignore (entries already present)',
                 ChangeCategory.CONFIGURATION),
        ):
            assert _category_from_description(description) == expected, description

    def test_a_description_naming_no_file_is_other(self):
        """Honest rather than helpful.

        The old fallback matched the word "JavaScript" and filed this under
        Scripts. It read a category out of prose, which is the coupling that
        moved a change to another heading when its sentence was reworded.
        """
        for description in ('Modified JavaScript for panels',
                            'Added new feature',
                            'Upgrade-chain wiring fix (internal)'):
            assert _category_from_description(description) == ChangeCategory.OTHER

    def test_it_reads_a_shouted_path(self):
        assert _category_from_description('Updated _CONFIG.YML') == \
            ChangeCategory.CONFIGURATION

    def test_the_longest_extension_wins(self):
        """`js` ahead of `json` in the alternation matches `package.js`.

        Leftmost-first alternation would take the shorter one and file an
        npm manifest under Scripts, which is what the old substring test did.
        """
        assert _category_from_description('Updated package.json — Node.js dependencies') == \
            ChangeCategory.CONFIGURATION

    def test_an_unrecognised_path_is_other_rather_than_guessed_at(self):
        assert _category_from_description('Updated objects.json endpoint') == \
            ChangeCategory.OTHER

    def test_the_cases_the_old_guess_got_wrong(self):
        """Each of these was filed under the wrong heading by the wording.

        A Python module whose name contains "config" is not configuration; a
        stylesheet whose name contains "layout" is not a layout; and a data
        file is not nothing. All three are settled by the path.
        """
        for description, expected in (
                ('Updated scripts/telar/config.py — Language loading',
                 ChangeCategory.SCRIPTS),
                ('Updated _sass/_layout.scss — Featured object thumbnail CSS fix',
                 ChangeCategory.STYLES),
                ('Updated _data/navigation.yml — Updated path references',
                 ChangeCategory.CONFIGURATION),
                ('Updated NOTICE — Third-party notices',
                 ChangeCategory.DOCUMENTATION),
                ('Updated LICENSE — Updated license',
                 ChangeCategory.DOCUMENTATION),
        ):
            assert _category_from_description(description) == expected, description


class TestCategoryForPath:
    """The path is what the install records carry, so it decides most of it."""

    def test_it_places_the_framework_directories(self):
        for path, expected in (
                ('_config.yml', ChangeCategory.CONFIGURATION),
                ('_data/languages/en.yml', ChangeCategory.CONFIGURATION),
                ('_layouts/story.html', ChangeCategory.LAYOUTS),
                ('_includes/widgets/carousel.html', ChangeCategory.INCLUDES),
                ('_sass/_layout.scss', ChangeCategory.STYLES),
                ('assets/css/telar.css', ChangeCategory.STYLES),
                ('assets/js/widgets.js', ChangeCategory.SCRIPTS),
                ('scripts/telar/config.py', ChangeCategory.SCRIPTS),
                ('tests/unit/test_widget_parsing.py', ChangeCategory.SCRIPTS),
                ('docs/README.md', ChangeCategory.DOCUMENTATION),
                ('README.md', ChangeCategory.DOCUMENTATION),
                ('NOTICE', ChangeCategory.DOCUMENTATION),
                ('LICENSE', ChangeCategory.DOCUMENTATION),
                ('.gitignore', ChangeCategory.CONFIGURATION),
                ('.github/dependabot.yml', ChangeCategory.CONFIGURATION),
                ('package.json', ChangeCategory.CONFIGURATION),
                ('objects.json', ChangeCategory.OTHER),
        ):
            assert category_for_path(path) == expected, path

    def test_a_prefix_beats_the_extension(self):
        """assets/css/ is a style whatever the file is called."""
        assert category_for_path('assets/css/telar.css') == ChangeCategory.STYLES
        assert category_for_path('scripts/README.md') == ChangeCategory.SCRIPTS

    def test_every_installable_path_lands_somewhere(self):
        from migrations.v020_to_v090 import FRAMEWORK_FILES_090

        for path in FRAMEWORK_FILES_090:
            assert category_for_path(path) in ChangeCategory.ORDER, path

    def test_the_fallback_now_agrees_with_it_on_the_whole_install_set(self):
        """The measurement this change was made for, inverted.

        A record that names its file is filed the same way whether or not
        it carries a category of its own. Reading the heading out of the
        wording instead put more than thirty of these under a different
        one, most of them "Other".
        """
        from migrations.v020_to_v090 import FRAMEWORK_FILES_090

        disagreements = [
            path for path, (description, _) in FRAMEWORK_FILES_090.items()
            if _category_from_description(f'Updated {path} — {description}')
            != category_for_path(path)
        ]

        assert disagreements == []


class TestApplyConfigVersion:
    """Single comment-preserving config-version writer (migrations.base)."""

    def _apply(self, content, version="1.5.0", date="2026-06-03"):
        from migrations.base import apply_config_version
        return apply_config_version(content, version, date)

    def test_updates_version_and_release_date_preserving_comments(self):
        cfg = ('telar:\n  # settings\n  version: "1.0.0"\n'
               '  release_date: "2025-01-01"\n  name: Site\ntitle: X\n')
        out, mod = self._apply(cfg)
        assert mod is True
        assert '  version: "1.5.0"' in out
        assert '  release_date: "2026-06-03"' in out
        assert '# settings' in out and 'name: Site' in out and 'title: X' in out

    def test_single_space_indent_is_still_in_section(self):
        # Regression for the old startswith('  ') check that exited on 1-space indent
        cfg = 'telar:\n version: "1.0.0"\n release_date: "2025-01-01"\nother: y\n'
        out, _ = self._apply(cfg)
        assert ' version: "1.5.0"' in out
        assert ' release_date: "2026-06-03"' in out

    def test_inserts_release_date_when_absent(self):
        cfg = 'telar:\n  version: "1.0.0"\n  name: Site\ntitle: X\n'
        out, mod = self._apply(cfg)
        assert mod is True
        lines = out.split('\n')
        vi = next(i for i, l in enumerate(lines) if 'version:' in l)
        assert lines[vi + 1] == '  release_date: "2026-06-03"'

    def test_no_telar_section_is_unchanged(self):
        out, mod = self._apply('title: X\nfoo: bar\n')
        assert mod is False and out == 'title: X\nfoo: bar\n'

    def test_upgrade_wrapper_and_base_method_agree(self, tmp_path):
        import telar_upgrade as up
        from migrations.v130_to_v140 import Migration130to140
        seed = 'telar:\n  version: "1.4.0"\n  release_date: "2026-05-26"\n'
        a = tmp_path / 'a'; a.mkdir(); (a / '_config.yml').write_text(seed)
        b = tmp_path / 'b'; b.mkdir(); (b / '_config.yml').write_text(seed)
        assert up._update_config_version(str(a), "1.5.0", "2026-06-03") is True
        assert Migration130to140(str(b))._update_config_version("1.5.0", "2026-06-03") is True
        assert (a / '_config.yml').read_text() == (b / '_config.yml').read_text()
