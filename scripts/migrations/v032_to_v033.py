"""
Migration from v0.3.2-beta to v0.3.3-beta.

Changes:
- Remove git push step from GitHub Actions workflow that conflicts with branch protection
"""

from typing import List, Dict
from .base import BaseMigration


class Migration032to033(BaseMigration):
    """Migration from v0.3.2 to v0.3.3 - workflow fix."""

    from_version = "0.3.2-beta"
    to_version = "0.3.3-beta"
    description = "Fix workflow branch protection conflict"

    def check_applicable(self) -> bool:
        """Check if workflow file exists."""
        return self._file_exists('.github/workflows/build.yml')

    def apply(self) -> List[str]:
        """Remove git push step from workflow."""
        changes = []

        workflow_path = '.github/workflows/build.yml'
        content = self._read_file(workflow_path)

        if not content:
            return changes

        # Check if the problematic section exists
        if '- name: Commit generated files' in content:
            # Remove the entire "Commit generated files" step
            lines = content.split('\n')
            new_lines = []
            skip_until_next_step = False
            in_commit_step = False

            for i, line in enumerate(lines):
                # Detect start of Commit generated files step
                if '- name: Commit generated files' in line:
                    in_commit_step = True
                    skip_until_next_step = True
                    continue

                # If we're skipping and hit another step or end of file, stop skipping
                if skip_until_next_step:
                    # Check if this is a new step (starts with '      - name:' at same indentation)
                    if line.strip().startswith('- name:') and not line.startswith('       '):
                        skip_until_next_step = False
                        new_lines.append(line)
                    # Also stop if we hit end of steps (lower indentation)
                    elif line and not line.startswith('      ') and not line.startswith('        '):
                        skip_until_next_step = False
                        new_lines.append(line)
                    # Skip this line (it's part of the commit step)
                    continue

                new_lines.append(line)

            new_content = '\n'.join(new_lines)
            self._write_file(workflow_path, new_content)
            changes.append("Removed git push step from .github/workflows/build.yml")

        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """No manual steps required."""
        return []
