"""
Migration from v0.3.2-beta to v0.3.3-beta.

Changes:
- Manual step: Update build.yml workflow file to remove git push step
"""

from typing import List, Dict
from .base import BaseMigration


class Migration032to033(BaseMigration):
    """Migration from v0.3.2 to v0.3.3 - workflow fix."""

    from_version = "0.3.2-beta"
    to_version = "0.3.3-beta"
    description = "Fix workflow branch protection conflict"

    def check_applicable(self) -> bool:
        """This migration only provides manual steps, no automated changes."""
        return False  # No automated changes, only manual workflow update

    def apply(self) -> List[str]:
        """No automated changes for this migration."""
        return []

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """Return workflow update step (conditional)."""
        # Check if build.yml still has old git push step
        workflow_content = self._read_file('.github/workflows/build.yml')
        if workflow_content and '- name: Commit generated files' in workflow_content:
            return [
                {
                    'description': 'Update GitHub Actions workflow file (.github/workflows/build.yml) - Replace with latest version from https://github.com/UCSB-AMPLab/telar/blob/main/.github/workflows/build.yml to remove deprecated git push step',
                    'doc_url': 'https://telar.org/docs/2-workflows/upgrading/'
                }
            ]
        return []
