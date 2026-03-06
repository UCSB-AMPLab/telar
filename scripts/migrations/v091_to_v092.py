"""
Migration from v0.9.1-beta to v0.9.2-beta.

Bug fix release:
- Fix incomplete IIIF sizes array causing tile failures on Windows
- Generate TIFY 96px thumbnail for static Level 0 hosting
- Skip test workflow on user sites

No _config.yml changes beyond version bump. No CSV schema changes.
No new dependencies.

Version: v0.9.2-beta
"""

from typing import List, Dict
from .base import BaseMigration


class Migration091to092(BaseMigration):
    """Migration from v0.9.1 to v0.9.2 - IIIF tile fix, workflow cleanup."""

    from_version = "0.9.1-beta"
    to_version = "0.9.2-beta"
    description = "IIIF tile rendering fix, TIFY thumbnail, test workflow scoping"

    def check_applicable(self) -> bool:
        """Check if migration should run."""
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # Phase 1: Update framework files
        print("  Phase 1: Updating framework files...")
        changes.extend(self._update_framework_files())

        # Phase 2: Update version
        print("  Phase 2: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("0.9.2-beta", today):
            changes.append(f"Updated _config.yml: version 0.9.2-beta ({today})")

        return changes

    def _update_framework_files(self) -> List[str]:
        """Update framework files from GitHub repository."""
        changes = []

        framework_files = {
            'scripts/iiif_utils.py': 'Fix sizes array scanning, add 96px thumbnail',
            'scripts/generate_iiif.py': 'Updated version header',
            'scripts/process_pdf.py': 'Updated version header',
            '.github/workflows/telar-tests.yml': 'Skip on user sites',
            '.github/workflows/build.yml': 'Updated version header',
            'CHANGELOG.md': 'Added v0.9.2-beta changelog entry',
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
        """Manual steps for v0.9.2."""
        return [
            {
                "title": "Update workflow files",
                "description": (
                    "Copy .github/workflows/telar-tests.yml and "
                    ".github/workflows/build.yml from the latest Telar "
                    "release. Workflow files cannot be updated automatically "
                    "by the migration script due to GitHub Actions token "
                    "permissions. The test workflow now only runs on the "
                    "main Telar repos, not on user sites."
                ),
            },
            {
                "title": "Regenerate IIIF tiles",
                "description": (
                    "If your site uses self-hosted images, regenerate tiles "
                    "to fix the info.json sizes array. Run your site's build "
                    "workflow or run generate_iiif.py locally. This fixes "
                    "tile rendering issues on Windows browsers."
                ),
            },
        ]
