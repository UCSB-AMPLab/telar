"""
Migration from v0.6.2-beta to v0.6.3-beta.

This is a backward-compatible patch release that adds:
- Inline panel content support (write text directly in spreadsheets)
- CSV comment row filtering fix for multi-line cells
- Panel title fallback to button text

No structural changes required — framework files are updated automatically.

Version: v0.6.3-beta
"""

from typing import List, Dict
from .base import BaseMigration


class Migration062to063(BaseMigration):
    """Migration from v0.6.2 to v0.6.3 - inline panel content support."""

    from_version = "0.6.2-beta"
    to_version = "0.6.3-beta"
    description = "Inline panel content, CSV parsing fix"

    def check_applicable(self) -> bool:
        """Check if migration should run."""
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # Phase 1: Update framework files from GitHub
        print("  Phase 1: Updating framework files...")
        changes.extend(self._update_framework_files())

        # Phase 2: Update version
        print("  Phase 2: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("0.6.3-beta", today):
            changes.append(f"Updated _config.yml: version 0.6.3-beta ({today})")

        return changes

    def _update_framework_files(self) -> List[str]:
        """Update framework files from GitHub repository."""
        changes = []

        framework_files = {
            'scripts/csv_to_json.py': 'Inline content support, CSV parsing fix',
            'assets/js/story.js': 'Panel title fallback to button text',
        }

        for file_path, description in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path} - {description}")
            else:
                changes.append(f"Warning: Could not fetch {file_path}")

        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """No manual steps required for this patch release."""
        return []
