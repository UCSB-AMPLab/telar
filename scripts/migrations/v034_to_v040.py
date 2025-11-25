"""
Migration from v0.3.4-beta to v0.4.0-beta.

Changes:
- Add show_story_steps configuration field (optional)
- Ensure language files exist (_data/lang/en.yml and es.yml)
- Update all framework files from GitHub (layouts, includes, scripts, styles)
- No breaking changes - all new features are additive
"""

from typing import List, Dict
import yaml
from .base import BaseMigration


class Migration034to040(BaseMigration):
    """Migration from v0.3.4 to v0.4.0 - multilingual UI support."""

    from_version = "0.3.4-beta"
    to_version = "0.4.0-beta"
    description = "Add multilingual UI support and new features"

    def check_applicable(self) -> bool:
        """
        Check if migration should run.

        Always returns True since v0.4.0 is purely additive - existing sites
        will continue to work, and this migration just adds new features.
        """
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # 1. Ensure Google Sheets integration comments are present
        if self._ensure_google_sheets_comments():
            changes.append("Added Google Sheets integration comments to _config.yml")

        # 2. Add story_interface configuration if not present
        if self._add_show_story_steps_config():
            changes.append("Added story_interface configuration section to _config.yml")

        # 3. Ensure language files exist (required for multilingual UI)
        lang_changes = self._ensure_language_files()
        changes.extend(lang_changes)

        # 4. Ensure _data directory exists
        if self._ensure_data_directory():
            changes.append("Created _data directory")

        # 5. Update framework files from GitHub
        framework_changes = self._update_framework_files()
        changes.extend(framework_changes)

        # 6. Fetch upgrade-summary layout if missing
        if not self._file_exists('_layouts/upgrade-summary.html'):
            summary_layout = self._fetch_from_github('_layouts/upgrade-summary.html')
            if summary_layout:
                self._write_file('_layouts/upgrade-summary.html', summary_layout)
                changes.append("Added _layouts/upgrade-summary.html")

        # 7. Fetch upgrade-alert include if missing
        if not self._file_exists('_includes/upgrade-alert.html'):
            alert_include = self._fetch_from_github('_includes/upgrade-alert.html')
            if alert_include:
                self._write_file('_includes/upgrade-alert.html', alert_include)
                changes.append("Added _includes/upgrade-alert.html")

        # 8. Ensure upgrade notice in index.md
        if self._ensure_index_upgrade_notice():
            changes.append("Added upgrade notice to index.md")

        return changes

    def _ensure_google_sheets_comments(self) -> bool:
        """
        Ensure Google Sheets integration section has full comments.

        Users upgrading from earlier versions may be missing the detailed
        setup instructions that were added in later releases.

        IMPORTANT: This method NEVER removes existing comments - it only adds
        missing Google Sheets documentation if not already present.
        """
        config_path = '_config.yml'
        content = self._read_file(config_path)

        if not content:
            return False

        # Check if google_sheets section exists
        if 'google_sheets:' not in content:
            return False

        # Check if the full comment block is already present
        if '# Google Sheets Integration (optional)' in content and \
           '# See docs/google_sheets_integration/README.md' in content:
            return False

        lines = content.split('\n')
        new_lines = []
        comment_added = False

        for i, line in enumerate(lines):
            # If we find google_sheets: without the full comment block above it
            if 'google_sheets:' in line and not comment_added:
                # NEVER remove existing content - only add comments above
                # Insert full comment block before google_sheets: line
                new_lines.append('')
                new_lines.append('# Google Sheets Integration (optional)')
                new_lines.append('# Manage content via Google Sheets instead of editing CSV files directly.')
                new_lines.append('# See docs/google_sheets_integration/README.md for detailed setup instructions.')
                new_lines.append('#')
                new_lines.append('# Setup:')
                new_lines.append('# 1. Get the template:')
                new_lines.append('#    - Option A: Duplicate our template at https://bit.ly/telar-template')
                new_lines.append('#    - Option B: Import docs/google_sheets_integration/telar-template.xlsx to Google Sheets yourself')
                new_lines.append('# 2. Share your sheet: Anyone with the link (Viewer access)')
                new_lines.append('# 3. Publish your sheet: File > Share > Publish to web')
                new_lines.append('# 4. Paste both URLs below')
                new_lines.append('# 5. Set enabled: true')
                new_lines.append('# 6. Commit changes')
                new_lines.append('#    - If using GitHub Pages: GitHub Actions will automatically discover tab GIDs and fetch CSVs')
                new_lines.append('#    - If running locally: Run `python3 scripts/fetch_google_sheets.py` before building')
                new_lines.append(line)
                comment_added = True
            else:
                new_lines.append(line)

        if comment_added:
            self._write_file(config_path, '\n'.join(new_lines))
            return True

        return False

    def _add_show_story_steps_config(self) -> bool:
        """
        Add show_story_steps configuration field if not present.

        NOTE: This field is now deprecated in favor of story_interface.show_story_steps
        but we keep this method for backward compatibility with the v0.3.x structure.
        The _ensure_story_interface_section() method handles the v0.4.0 structure.
        """
        config_path = '_config.yml'
        content = self._read_file(config_path)

        if not content:
            return False

        # Check if already has show_story_steps or story_interface
        if 'show_story_steps:' in content or 'story_interface:' in content:
            return False

        lines = content.split('\n')
        new_lines = []
        added = False

        for i, line in enumerate(lines):
            new_lines.append(line)

            # Insert after telar_language line
            if 'telar_language:' in line and not added:
                # Add blank line first
                new_lines.append('')
                # Add Story Interface Settings section
                new_lines.append('# Story Interface Settings')
                new_lines.append('story_interface:')
                new_lines.append('  show_story_steps: true # Set to false to hide "Step X" overlay in stories')
                new_lines.append('  include_demo_content: false # v0.5.0 feature - demo stories from external repository')
                added = True

        if added:
            self._write_file(config_path, '\n'.join(new_lines))
            return True

        return False

    def _ensure_data_directory(self) -> bool:
        """Ensure _data directory exists."""
        import os
        data_dir = os.path.join(self.repo_root, '_data')
        if not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
            return True
        return False

    def _ensure_language_files(self) -> List[str]:
        """
        Ensure language files exist with minimal required strings.
        Fetches from GitHub if missing.
        """
        changes = []

        # Ensure _data/languages directory exists
        import os
        lang_dir = os.path.join(self.repo_root, '_data', 'languages')
        if not os.path.exists(lang_dir):
            os.makedirs(lang_dir, exist_ok=True)
            changes.append("Created _data/languages directory")

        # Check for en.yml
        if not self._file_exists('_data/languages/en.yml'):
            en_content = self._fetch_from_github('_data/languages/en.yml')
            if en_content:
                self._write_file('_data/languages/en.yml', en_content)
                changes.append("Added English language file (_data/languages/en.yml)")

        # Check for es.yml
        if not self._file_exists('_data/languages/es.yml'):
            es_content = self._fetch_from_github('_data/languages/es.yml')
            if es_content:
                self._write_file('_data/languages/es.yml', es_content)
                changes.append("Added Spanish language file (_data/languages/es.yml)")

        return changes

    def _update_framework_files(self) -> List[str]:
        """
        Update core framework files from GitHub.

        v0.4.0 includes many framework updates:
        - Multilingual UI strings in all templates
        - Widget system support
        - Glossary auto-linking
        - IIIF metadata extraction
        - Mobile responsiveness improvements
        """
        changes = []

        framework_files = {
            # Layouts
            '_layouts/story.html': 'Updated story layout (multilingual, widgets)',
            '_layouts/object.html': 'Updated object layout (multilingual)',
            '_layouts/objects-index.html': 'Updated objects index layout (multilingual)',
            '_layouts/default.html': 'Updated default layout (multilingual)',
            '_layouts/glossary.html': 'Updated glossary layout (multilingual)',
            '_layouts/glossary-index.html': 'Updated glossary index layout (multilingual)',
            '_layouts/page.html': 'Updated page layout',
            '_layouts/index.html': 'Updated index layout (multilingual)',

            # Includes
            '_includes/story-step.html': 'Updated story-step include (multilingual)',
            '_includes/panels.html': 'Updated panels include (widgets support)',
            '_includes/viewer.html': 'Updated viewer include',
            '_includes/header.html': 'Updated header include (multilingual)',
            '_includes/footer.html': 'Updated footer include (multilingual, theme attribution)',
            '_includes/iiif-url-warning.html': 'Updated IIIF URL warning (multilingual)',
            '_includes/widgets/accordion.html': 'Added accordion widget template',
            '_includes/widgets/carousel.html': 'Added carousel widget template',
            '_includes/widgets/tabs.html': 'Added tabs widget template',

            # Scripts
            'scripts/csv_to_json.py': 'Updated CSV processor (IIIF metadata extraction)',
            'scripts/generate_collections.py': 'Updated collection generator (widgets, glossary)',
            'scripts/generate_iiif.py': 'Updated IIIF tile generator',

            # JavaScript
            'assets/js/story.js': 'Updated story JavaScript',
            'assets/js/telar.js': 'Updated telar JavaScript (glossary auto-linking)',
            'assets/js/widgets.js': 'Added widgets JavaScript (carousel, tabs, accordion)',

            # Styles
            'assets/css/telar.scss': 'Updated telar styles (widgets, mobile responsive, site description links)',

            # Documentation
            'README.md': 'Updated README',
            'docs/google_sheets_integration/README.md': 'Updated Google Sheets integration docs',
            'requirements.txt': 'Updated Python requirements',

            # Theme files
            '_data/themes/austin.yml': 'Updated Austin theme (creator attribution)',
            '_data/themes/neogranadina.yml': 'Updated Neogranadina theme (creator attribution)',
            '_data/themes/paisajes.yml': 'Updated Paisajes theme (creator attribution)',
            '_data/themes/santa-barbara.yml': 'Updated Santa Barbara theme (creator attribution)',

            # Endpoints
            'objects.json': 'Updated objects.json endpoint',
        }

        for file_path, success_msg in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(success_msg)

        return changes

    def _ensure_index_upgrade_notice(self) -> bool:
        """
        Ensure index.md has an upgrade notice include at the top.

        This helps users see upgrade information prominently on their homepage.
        """
        index_path = 'index.md'
        content = self._read_file(index_path)

        if not content:
            return False

        # Check if upgrade notice is already present
        if '{% include upgrade-alert.html %}' in content:
            return False

        lines = content.split('\n')
        new_lines = []
        added = False

        for i, line in enumerate(lines):
            new_lines.append(line)

            # Insert after front matter closes
            if line.strip() == '---' and i > 0 and not added:
                new_lines.append('')
                new_lines.append('{% include upgrade-alert.html %}')
                new_lines.append('')
                added = True

        if added:
            self._write_file(index_path, '\n'.join(new_lines))
            return True

        return False

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """
        Manual steps for users to complete after migration.

        v0.4.0 is non-breaking, so these are all optional enhancements.
        """
        return [
            {
                'description': 'Review multilingual configuration in _config.yml (telar_language: "en" or "es")',
                'doc_url': 'https://telar.org/docs/multilingual-setup'
            },
            {
                'description': 'Optionally add widgets to your stories (carousel, tabs, accordion)',
                'doc_url': 'https://telar.org/docs/widgets'
            },
            {
                'description': 'Optionally create glossary terms and add [[term]] links to your content',
                'doc_url': 'https://telar.org/docs/glossary'
            },
            {
                'description': 'Test IIIF metadata auto-population by leaving object fields blank in CSV',
                'doc_url': 'https://telar.org/docs/iiif-metadata'
            },
            {
                'description': 'Add theme creator attribution to your theme YAML file (optional)',
                'doc_url': 'https://telar.org/docs/themes#creator-attribution'
            },
            {
                'description': 'Run "bundle exec jekyll build" to test your upgraded site',
            },
        ]

    def __str__(self):
        """String representation for logging."""
        return f"Migration {self.from_version} → {self.to_version}: {self.description}"
