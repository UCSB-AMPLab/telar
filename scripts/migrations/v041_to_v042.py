"""
Migration from v0.4.1-beta to v0.4.2-beta.

Changes:
- Smart IIIF change detection with GitHub Actions caching
- Update build.yml workflow with detection and caching logic
- Mobile navbar and font size fixes
- Site title wrapping improvements
- Site description link styling
- No breaking changes - all improvements are automatic
"""

from typing import List, Dict
from .base import BaseMigration


class Migration041to042(BaseMigration):
    """Migration from v0.4.1 to v0.4.2 - smart build and mobile refinements."""

    from_version = "0.4.1-beta"
    to_version = "0.4.2-beta"
    description = "Smart IIIF change detection and mobile UI refinements"

    def check_applicable(self) -> bool:
        """
        Check if migration should run.

        Always returns True since v0.4.2 is purely optimizations and fixes -
        existing sites will continue to work, and this migration adds smart
        IIIF detection and minor mobile improvements.
        """
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # Update framework files from GitHub (build workflow with caching)
        framework_changes = self._update_framework_files()
        changes.extend(framework_changes)

        return changes

    def _update_framework_files(self) -> List[str]:
        """
        Update core framework files from GitHub.

        v0.4.2 includes smart build optimizations and mobile refinements:
        - CRITICAL: Smart IIIF change detection with GitHub Actions caching
        - Prevents IIIF tile deletion when skipping regeneration
        - Mobile navbar title wrapping fixes
        - Mobile font size adjustments
        - Site title and description styling improvements
        """
        changes = []

        framework_files = {
            # Workflows - smart IIIF detection and caching
            '.github/workflows/build.yml': 'Updated build workflow (smart IIIF detection with caching)',

            # Layouts - mobile improvements
            '_layouts/index.html': 'Updated index layout (site description link styling)',

            # Assets - mobile CSS fixes
            'assets/css/telar.scss': 'Updated CSS (mobile navbar, font sizes, title wrapping)',

            # Documentation
            'README.md': 'Updated README (version 0.4.2-beta)',
        }

        for file_path, description in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path}: {description}")

        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """
        Manual steps for users to complete after migration.

        v0.4.2 updates the build.yml workflow file, which requires explicit
        action since GitHub Actions workflows only take effect when committed
        to the repository.
        """
        return [
            {
                'description': 'CRITICAL: The updated build.yml workflow must be merged/committed for IIIF caching to work. If using automated upgrade workflow: Review and MERGE the upgrade pull request - the new build workflow will not take effect until merged. If upgrading locally: COMMIT and PUSH .github/workflows/build.yml - the new workflow is not active until pushed to GitHub. Until the new workflow is active, the IIIF caching protection is not in effect.',
            },
            {
                'description': 'Test the smart IIIF detection: Make a content-only change (edit a story markdown file), push to GitHub, and verify the build workflow completes faster by skipping IIIF regeneration (optional)',
            },
        ]
