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

        # 0. Restore critical _config.yml comments deleted by v0.3.4->v0.4.0 migration
        # This fixes repos damaged by the comment-deletion bug in v034_to_v040.py
        comment_changes = self._restore_config_comments()
        changes.extend(comment_changes)

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
            '_layouts/index.html': 'Updated index layout (site description link styling)',
            '_layouts/object.html': 'Updated object layout (coordinate picker buttons)',
            '_layouts/story.html': 'Updated story layout (mobile responsive features restored)',

            # JavaScript - mobile features restored
            'assets/js/story.js': 'Updated story JavaScript (mobile navigation, preloading, transitions)',

            # Styles - mobile responsive code and gallery layout
            'assets/css/telar.scss': 'Updated telar styles (mobile responsive features, gallery layout)',

            # Documentation
            'CHANGELOG.md': 'Updated CHANGELOG',
            'README.md': 'Updated README (supporter acknowledgments)',
        }

        for file_path, success_msg in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(success_msg)

        return changes

    def _restore_config_comments(self) -> List[str]:
        """
        Restore critical comments to _config.yml that were deleted by v034_to_v040 migration.

        The v0.3.4->v0.4.0 migration had a bug in _ensure_google_sheets_comments() that
        removed ALL comments before the google_sheets: section, including the critical
        "PLEASE DO NOT EDIT BELOW THIS LINE" warning and all section headers.

        This method detects missing comments and restores them.
        """
        changes = []
        config_path = '_config.yml'
        content = self._read_file(config_path)

        if not content:
            return changes

        lines = content.split('\n')
        modified = False

        # Check if critical comments are missing and restore them

        # 0. Restore top header comments if missing
        if '# Telar - Digital Storytelling Framework' not in content:
            # Add header at the very top if not present
            if not (lines[0].startswith('# Telar') or lines[0].startswith('title:')):
                lines.insert(0, '# Telar - Digital Storytelling Framework')
                lines.insert(1, '# https://github.com/UCSB-AMPLab/telar')
                lines.insert(2, '')
                modified = True
                changes.append("Restored top header comments")

        # 1. Restore "Site Settings" header if missing
        if '# Site Settings' not in content and 'title:' in content:
            for i, line in enumerate(lines):
                if line.strip().startswith('title:') and i > 0:
                    # Check if there's no "Site Settings" comment above
                    if i < 5 or '# Site Settings' not in '\n'.join(lines[max(0, i-5):i]):
                        lines.insert(i, '# Site Settings')
                        modified = True
                        changes.append("Restored '# Site Settings' header comment")
                        break

        # 2. Restore "Story Interface Settings" header if missing
        if '# Story Interface Settings' not in content and 'story_interface:' in content:
            for i, line in enumerate(lines):
                if 'story_interface:' in line:
                    # Check if comment is missing right above
                    if i == 0 or '# Story Interface Settings' not in lines[i-1]:
                        # Insert blank line and comment
                        lines.insert(i, '# Story Interface Settings')
                        if i == 0 or lines[i-1].strip() != '':
                            lines.insert(i, '')
                        modified = True
                        changes.append("Restored '# Story Interface Settings' header comment")
                        break

        # 3. Restore "PLEASE DO NOT EDIT BELOW THIS LINE" warning if missing
        if '# PLEASE DO NOT EDIT BELOW THIS LINE' not in content and 'collections:' in content:
            for i, line in enumerate(lines):
                if line.strip().startswith('collections:'):
                    # Check if warning is missing above
                    found_warning = False
                    for j in range(max(0, i-10), i):
                        if '# PLEASE DO NOT EDIT BELOW THIS LINE' in lines[j]:
                            found_warning = True
                            break

                    if not found_warning:
                        # Insert warning section before collections
                        warning_lines = [
                            '',
                            '',
                            '#',
                            '#',
                            '#',
                            '# PLEASE DO NOT EDIT BELOW THIS LINE UNLESS YOU KNOW WHAT YOU ARE DOING',
                            '#',
                            '#',
                            '#',
                            ''
                        ]
                        for idx, warning_line in enumerate(warning_lines):
                            lines.insert(i + idx, warning_line)
                        modified = True
                        changes.append("Restored 'PLEASE DO NOT EDIT BELOW THIS LINE' warning")
                        break

        # 4. Restore "Collections" header if missing
        if '# Collections' not in content and 'collections:' in content:
            for i, line in enumerate(lines):
                if line.strip().startswith('collections:'):
                    # Check if comment exists right above
                    if i == 0 or '# Collections' not in lines[i-1]:
                        lines.insert(i, '# Collections')
                        modified = True
                        changes.append("Restored '# Collections' header comment")
                        break

        # 5. Restore "Collections Directory" comment if missing
        if '# Collections Directory' not in content and 'collections_dir:' in content:
            for i, line in enumerate(lines):
                if 'collections_dir:' in line:
                    if i == 0 or '# Collections Directory' not in lines[i-1]:
                        lines.insert(i, '')
                        lines.insert(i+1, '# Collections Directory (a folder where Jekyll and the Telar scripts will put all auto-generated object and story working files)')
                        modified = True
                        changes.append("Restored 'Collections Directory' comment")
                        break

        # 6. Restore "Build Settings" header if missing
        if '# Build Settings' not in content and 'markdown:' in content:
            for i, line in enumerate(lines):
                if line.strip().startswith('markdown:'):
                    if i == 0 or '# Build Settings' not in lines[i-1]:
                        lines.insert(i, '')
                        lines.insert(i+1, '# Build Settings')
                        modified = True
                        changes.append("Restored '# Build Settings' header comment")
                        break

        # 7. Restore "Defaults" header if missing
        if '# Defaults' not in content and 'defaults:' in content:
            for i, line in enumerate(lines):
                if line.strip().startswith('defaults:'):
                    if i == 0 or '# Defaults' not in lines[i-1]:
                        lines.insert(i, '')
                        lines.insert(i+1, '# Defaults')
                        modified = True
                        changes.append("Restored '# Defaults' header comment")
                        break

        # 8. Restore Jekyll dates comment if missing
        if '# Tell Jekyll not to expect dates' not in content and 'future:' in content:
            for i, line in enumerate(lines):
                if line.strip().startswith('future:'):
                    if i == 0 or '# Tell Jekyll not to expect dates' not in lines[i-1]:
                        lines.insert(i, '')
                        lines.insert(i+1, '# Tell Jekyll not to expect dates for these collections')
                        modified = True
                        changes.append("Restored Jekyll dates comment")
                        break

        # 9. Restore "Telar Settings" comment if missing
        if '# Telar Settings' not in content and 'telar:' in content:
            for i, line in enumerate(lines):
                if line.strip() == 'telar:':
                    if i == 0 or '# Telar Settings' not in lines[i-1]:
                        lines.insert(i, '')
                        lines.insert(i+1, '# Telar Settings (version information)')
                        modified = True
                        changes.append("Restored 'Telar Settings' comment")
                        break

        # 10. Restore "Plugins" header if missing
        if '# Plugins' not in content and 'plugins:' in content:
            for i, line in enumerate(lines):
                if line.strip().startswith('plugins:'):
                    if i == 0 or '# Plugins' not in lines[i-1]:
                        lines.insert(i, '')
                        lines.insert(i+1, '# Plugins')
                        modified = True
                        changes.append("Restored '# Plugins' header comment")
                        break

        # 11. Restore "WEBrick" comment if missing
        if '# WEBrick server configuration' not in content and 'webrick:' in content:
            for i, line in enumerate(lines):
                if line.strip().startswith('webrick:'):
                    if i == 0 or '# WEBrick' not in lines[i-1]:
                        lines.insert(i, '')
                        lines.insert(i+1, '# WEBrick server configuration for development (enables CORS for IIIF)')
                        modified = True
                        changes.append("Restored WEBrick configuration comment")
                        break

        # 12. Restore "Development & Testing" section if missing
        if 'testing-features:' not in content:
            # Section doesn't exist at all - add it after webrick section
            for i, line in enumerate(lines):
                if line.strip().startswith('Access-Control-Allow-Headers:'):
                    # Find end of webrick section, add testing-features
                    lines.insert(i+1, '')
                    lines.insert(i+2, '# Development & Testing')
                    lines.insert(i+3, '# Set to false or remove for production use')
                    lines.insert(i+4, 'testing-features:')
                    lines.insert(i+5, '  # Christmas Tree Mode - Displays all warning messages for testing multilingual support')
                    lines.insert(i+6, '  # Set to true to light up the site with test warnings (test objects, fake errors, etc.)')
                    lines.insert(i+7, '  christmas_tree_mode: false')
                    modified = True
                    changes.append("Added 'Development & Testing' section with testing-features")
                    break
        else:
            # Section exists, just restore comments if missing
            if '# Development & Testing' not in content:
                for i, line in enumerate(lines):
                    if 'testing-features:' in line:
                        if i == 0 or '# Development & Testing' not in lines[i-1]:
                            lines.insert(i, '')
                            lines.insert(i+1, '# Development & Testing')
                            lines.insert(i+2, '# Set to false or remove for production use')
                            modified = True
                            changes.append("Restored 'Development & Testing' header comment")
                            break

            # 13. Restore "Christmas Tree Mode" comment if missing
            if '# Christmas Tree Mode' not in content and 'christmas_tree_mode:' in content:
                for i, line in enumerate(lines):
                    if 'christmas_tree_mode:' in line:
                        # Check previous lines for the comment
                        has_comment = False
                        for j in range(max(0, i-3), i):
                            if '# Christmas Tree Mode' in lines[j]:
                                has_comment = True
                                break

                        if not has_comment:
                            lines.insert(i, '  # Christmas Tree Mode - Displays all warning messages for testing multilingual support')
                            lines.insert(i+1, '  # Set to true to light up the site with test warnings (test objects, fake errors, etc.)')
                            modified = True
                            changes.append("Restored Christmas Tree Mode comment")
                            break

        if modified:
            self._write_file(config_path, '\n'.join(lines))

        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """
        Manual steps for users to complete after migration.

        v0.4.1 requires one manual step to update the GitHub Actions workflow
        to prevent future comment deletion in _config.yml.
        """
        return [
            {
                'description': 'Update your upgrade workflow file (one-time fix to prevent config comment deletion): (1) Go to https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/upgrade.yml (2) Select all (Ctrl/Cmd+A) and copy (3) In your repository, navigate to .github/workflows/upgrade.yml (4) Click the pencil icon to edit (5) Select all existing content and delete it (6) Paste the new content (7) Scroll to bottom and click "Commit changes". This fixes a bug that was stripping documentation comments from your _config.yml file during upgrades.',
                'doc_url': 'https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/upgrade.yml'
            },
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
