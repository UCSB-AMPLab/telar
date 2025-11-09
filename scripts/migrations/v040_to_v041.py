"""
Migration from v0.4.0-beta to v0.4.1-beta.

Changes:
- Restore mobile responsive features (CSS, JS, layouts)
- Add coordinate picker button improvements (language strings)
- Fix object gallery mobile layout
- Update framework files from GitHub
- No breaking changes - all fixes and improvements are automatic
"""

from typing import List, Dict
from .base import BaseMigration


class Migration040to041(BaseMigration):
    """Migration from v0.4.0 to v0.4.1 - mobile fixes and quality of life improvements."""

    from_version = "0.4.0-beta"
    to_version = "0.4.1-beta"
    description = "Restore mobile responsive features and add quality of life improvements"

    def check_applicable(self) -> bool:
        """
        Check if migration should run.

        Always returns True since v0.4.1 is purely fixes and improvements -
        existing sites will continue to work, and this migration restores
        critical mobile features and adds minor enhancements.
        """
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # 1. Update language files with new coordinate picker strings
        lang_changes = self._update_language_files()
        changes.extend(lang_changes)

        # 2. Update framework files from GitHub (critical mobile code restoration)
        framework_changes = self._update_framework_files()
        changes.extend(framework_changes)

        return changes

    def _update_language_files(self) -> List[str]:
        """
        Update language files with new coordinate picker button strings.

        Adds three new strings to both en.yml and es.yml:
        - copy_sheets: "x, y, zoom (Sheets)"
        - copy_csv: "x, y, zoom (CSV)"
        - copied: "Copied!" / "¡Copiado!"
        """
        changes = []

        # English language file
        en_content = self._fetch_from_github('_data/languages/en.yml')
        if en_content:
            self._write_file('_data/languages/en.yml', en_content)
            changes.append("Updated English language file with coordinate picker strings")

        # Spanish language file
        es_content = self._fetch_from_github('_data/languages/es.yml')
        if es_content:
            self._write_file('_data/languages/es.yml', es_content)
            changes.append("Updated Spanish language file with coordinate picker strings")

        return changes

    def _update_framework_files(self) -> List[str]:
        """
        Update core framework files from GitHub.

        v0.4.1 includes critical fixes and improvements:
        - CRITICAL: Restore ~1,300 lines of mobile responsive code
        - Mobile panel UI, transitions, navigation cooldown
        - Height-based responsive design (4-tier system)
        - Coordinate picker CSV/Sheets buttons
        - Object gallery mobile layout fixes
        """
        changes = []

        framework_files = {
            # Layouts - mobile code restoration and coordinate picker
            '_layouts/object.html': 'Updated object layout (coordinate picker buttons)',
            '_layouts/story.html': 'Updated story layout (mobile responsive features restored)',

            # JavaScript - mobile features restored
            'assets/js/story.js': 'Updated story JavaScript (mobile navigation, preloading, transitions)',

            # Styles - mobile responsive code and gallery layout
            'assets/css/telar.scss': 'Updated telar styles (mobile responsive features, gallery layout)',

            # Documentation
            'CHANGELOG.md': 'Updated CHANGELOG',
        }

        for file_path, success_msg in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(success_msg)

        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """
        Manual steps for users to complete after migration.

        v0.4.1 is non-breaking with no manual steps required.
        All changes are automatic bug fixes and improvements.
        """
        return [
            {
                'description': 'Run "bundle exec jekyll build" to test your upgraded site',
            },
            {
                'description': 'Test mobile responsive features on small screens (optional)',
            },
            {
                'description': 'Try the new coordinate picker buttons in object pages (optional)',
            },
        ]

    def __str__(self):
        """String representation for logging."""
        return f"Migration {self.from_version} → {self.to_version}: {self.description}"
