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


class TestTheDescriptionGuess:
    """What the summary did for every change before records carried one.

    Kept because legacy migrations still return bare strings. These tests
    record where it is wrong, so the fallback's limits are written down
    rather than assumed.
    """

    def test_it_reads_the_obvious_cases(self):
        for description, expected in (
                ('Updated _config.yml with new settings', ChangeCategory.CONFIGURATION),
                ('Modified _layouts/default.html', ChangeCategory.LAYOUTS),
                ('Updated _includes/header.html', ChangeCategory.INCLUDES),
                ('Updated main.scss with new variables', ChangeCategory.STYLES),
                ('Modified JavaScript for panels', ChangeCategory.SCRIPTS),
                ('Updated README.md', ChangeCategory.DOCUMENTATION),
                ('Added new feature', ChangeCategory.OTHER),
        ):
            assert _category_from_description(description) == expected, description

    def test_it_matches_case_insensitively(self):
        assert _category_from_description('Updated _CONFIG.YML') == \
            ChangeCategory.CONFIGURATION

    def test_config_beats_the_later_rules(self):
        assert _category_from_description('_config.yml: added new script setting') == \
            ChangeCategory.CONFIGURATION

    def test_it_sees_js_inside_json(self):
        """`.js` is a substring of `.json`, so npm manifests read as scripts."""
        for description in ('Updated package.json — Node.js dependencies',
                            'Updated objects.json endpoint'):
            assert _category_from_description(description) == ChangeCategory.SCRIPTS

    def test_a_python_module_named_config_reads_as_configuration(self):
        assert _category_from_description(
            'Updated scripts/telar/config.py — Language loading') == \
            ChangeCategory.CONFIGURATION

    def test_a_stylesheet_named_layout_reads_as_a_layout(self):
        assert _category_from_description(
            'Updated _sass/_layout.scss — Featured object thumbnail CSS fix') == \
            ChangeCategory.LAYOUTS

    def test_data_files_and_licences_fall_through_to_other(self):
        for description in ('Updated _data/navigation.yml — Updated path references',
                            'Updated NOTICE — Third-party notices',
                            'Updated LICENSE — Updated license'):
            assert _category_from_description(description) == ChangeCategory.OTHER


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

    def test_it_disagrees_with_the_guess_on_a_third_of_the_install_set(self):
        """The measurement this change was made for.

        Not a threshold to tune — a record of how much of an upgrade's
        report was filed by wording, most of it into "Other".
        """
        from migrations.v020_to_v090 import FRAMEWORK_FILES_090

        disagreements = [
            path for path, (description, _) in FRAMEWORK_FILES_090.items()
            if _category_from_description(f'Updated {path} — {description}')
            != category_for_path(path)
        ]

        assert len(disagreements) > 30
        assert len(disagreements) < len(FRAMEWORK_FILES_090) / 2


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
