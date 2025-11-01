"""
Migration from v0.3.3-beta to v0.3.4-beta.

Changes:
- Remove unused OpenSeadragon configuration section from _config.yml
- Add telar_language configuration field
"""

from typing import List, Dict
import yaml
from .base import BaseMigration


class Migration033to034(BaseMigration):
    """Migration from v0.3.3 to v0.3.4 - remove unused config."""

    from_version = "0.3.3-beta"
    to_version = "0.3.4-beta"
    description = "Remove unused OpenSeadragon configuration"

    def check_applicable(self) -> bool:
        """Check if _config.yml has OpenSeadragon section to remove."""
        content = self._read_file('_config.yml')
        return content and 'openseadragon:' in content

    def apply(self) -> List[str]:
        """Remove OpenSeadragon configuration section and add Python gitignore entries."""
        changes = []

        config_path = '_config.yml'
        content = self._read_file(config_path)

        if content and 'openseadragon:' in content:
            # Remove OpenSeadragon section using text-based approach
            lines = content.split('\n')
            new_lines = []
            in_openseadragon_section = False
            skip_blank_line = False

            for _, line in enumerate(lines):
                stripped = line.strip()

                # Detect OpenSeadragon section header
                if stripped == '# OpenSeadragon Settings':
                    in_openseadragon_section = True
                    skip_blank_line = True
                    continue

                # Detect openseadragon: key
                if line.startswith('openseadragon:'):
                    in_openseadragon_section = True
                    continue

                # Inside OpenSeadragon section
                if in_openseadragon_section:
                    # Exit when we hit a non-indented line that's not blank
                    if line and not line.startswith('  ') and not line.startswith('\t') and stripped:
                        in_openseadragon_section = False
                        # Don't skip this line, add it
                        new_lines.append(line)
                        continue

                    # Skip blank line immediately after section if needed
                    if not stripped and skip_blank_line:
                        skip_blank_line = False
                        continue

                    # Skip all indented lines (the actual config values)
                    if line.startswith('  ') or line.startswith('\t'):
                        continue

                    # Skip blank lines within section
                    if not stripped:
                        continue
                else:
                    new_lines.append(line)

            self._write_file(config_path, '\n'.join(new_lines))
            changes.append("Removed unused OpenSeadragon configuration section from _config.yml")

        # Add Python gitignore entries
        python_entries = ['__pycache__/', '*.py[cod]', '*$py.class']
        if self._ensure_gitignore_entries(python_entries, '# Python'):
            changes.append("Added Python entries to .gitignore")

        # Add telar_language configuration field if not present
        if self._add_language_config():
            changes.append("Added telar_language configuration field to _config.yml")

        # Fetch upgrade-summary layout from GitHub
        if not self._file_exists('_layouts/upgrade-summary.html'):
            summary_layout = self._fetch_from_github('_layouts/upgrade-summary.html')
            if summary_layout:
                self._write_file('_layouts/upgrade-summary.html', summary_layout)
                changes.append("Added _layouts/upgrade-summary.html")

        # Fetch upgrade-alert include from GitHub
        if not self._file_exists('_includes/upgrade-alert.html'):
            alert_include = self._fetch_from_github('_includes/upgrade-alert.html')
            if alert_include:
                self._write_file('_includes/upgrade-alert.html', alert_include)
                changes.append("Added _includes/upgrade-alert.html")

        # Ensure upgrade notice exists in index.md
        if self._ensure_index_upgrade_notice():
            changes.append("Added upgrade notice to index.md")

        # Update core framework files from GitHub
        framework_files = {
            '_layouts/story.html': 'Updated story layout',
            '_layouts/object.html': 'Updated object layout',
            '_layouts/objects-index.html': 'Updated objects index layout',
            '_layouts/default.html': 'Updated default layout',
            '_layouts/glossary.html': 'Updated glossary layout',
            '_layouts/glossary-index.html': 'Updated glossary index layout',
            '_layouts/page.html': 'Updated page layout',
            '_layouts/index.html': 'Updated index layout',
            '_includes/story-step.html': 'Updated story-step include',
            '_includes/panels.html': 'Updated panels include',
            '_includes/viewer.html': 'Updated viewer include',
            '_includes/header.html': 'Updated header include',
            '_includes/footer.html': 'Updated footer include',
            '_includes/iiif-url-warning.html': 'Updated IIIF URL warning',
            'objects.json': 'Added objects.json endpoint',
            'scripts/generate_iiif.py': 'Updated IIIF tile generator',
            'assets/js/story.js': 'Updated story JavaScript',
            'assets/js/telar.js': 'Updated telar JavaScript',
            'assets/css/telar.scss': 'Updated telar styles',
            'README.md': 'Updated README',
            'docs/README.md': 'Updated docs README',
        }

        for file_path, success_msg in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(success_msg)

        return changes

    def _add_language_config(self) -> bool:
        """
        Add telar_language configuration field if not present.
        Inserts after logo field to maintain logical grouping.
        """
        config_path = '_config.yml'
        content = self._read_file(config_path)

        if not content:
            return False

        # Check if field already exists
        try:
            config = yaml.safe_load(content)
            if 'telar_language' in config:
                return False  # Already present
        except yaml.YAMLError:
            return False

        # Insert after logo line
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.startswith('logo:'):
                # Insert after logo line
                lines.insert(i + 1, 'telar_language: "en" # Options: "en" (English), "es" (Español)')
                self._write_file(config_path, '\n'.join(lines))
                return True

        return False

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """No manual steps required for this migration."""
        return []
