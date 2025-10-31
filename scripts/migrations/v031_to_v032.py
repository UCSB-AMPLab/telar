"""
Migration from v0.3.1-beta to v0.3.2-beta.

Changes:
- Move index.html to _layouts/index.html
- Create editable index.md in root
- Remove cron schedule from build workflow
"""

from typing import List, Dict
from .base import BaseMigration


class Migration031to032(BaseMigration):
    """Migration from v0.3.0 to v0.3.2 - index page refactor."""

    from_version = "0.3.0-beta"
    to_version = "0.3.2-beta"
    description = "Refactor index page for easier customization"

    # Default index.md template for users upgrading
    INDEX_MD_TEMPLATE = """---
layout: index
title: Home
stories_heading: "Explore the stories"
stories_intro: ""
objects_heading: "See the objects behind the stories"
objects_intro: "Browse {count} objects featured in the stories."
---

{% include upgrade-alert.html %}

The homepage can now be customized by editing the `index.md` file in the root folder of your repository. Edit it to remove or replace this message. To learn more, visit the [documentation](https://ampl.clair.ucsb.edu/telar-docs/docs/6-customization/3-home-page/).
"""

    def check_applicable(self) -> bool:
        """Check if index.html exists or if workflow needs updating."""
        return (self._file_exists('index.html') or
                self._file_exists('.github/workflows/build.yml'))

    def apply(self) -> List[str]:
        """Apply index refactoring and workflow updates."""
        changes = []

        # 1. Replace index.html with new layout version
        # Delete old index.html if it exists (it's outdated)
        import os
        old_index_path = os.path.join(self.repo_root, 'index.html')
        if os.path.exists(old_index_path):
            os.remove(old_index_path)

        # Fetch new index.html layout from GitHub
        index_layout = self._fetch_from_github('_layouts/index.html')
        if index_layout:
            self._write_file('_layouts/index.html', index_layout)
            changes.append("Moved index.html to _layouts/index.html")
        else:
            print("  ⚠️  Warning: Could not fetch index layout from GitHub")

        # 2. Create index.md if it doesn't exist
        if not self._file_exists('index.md'):
            self._write_file('index.md', self.INDEX_MD_TEMPLATE)
            changes.append("Created index.md in root directory")

        # 3. Remove cron schedule from workflow
        workflow_path = '.github/workflows/build.yml'
        content = self._read_file(workflow_path)

        if content and 'schedule:' in content:
            lines = content.split('\n')
            new_lines = []
            skip_schedule = False

            for line in lines:
                # Start skipping at 'schedule:'
                if line.strip().startswith('schedule:'):
                    skip_schedule = True
                    continue

                # Stop skipping when we hit the next top-level key (same indentation as 'schedule:')
                if skip_schedule:
                    # If line is not empty and starts at column 0 or 2 (same as 'schedule:'), stop skipping
                    if line and not line.startswith('  ') and line.strip():
                        skip_schedule = False
                        new_lines.append(line)
                    # Skip cron lines (indented under schedule)
                    continue

                new_lines.append(line)

            new_content = '\n'.join(new_lines)
            self._write_file(workflow_path, new_content)
            changes.append("Removed cron schedule from .github/workflows/build.yml")

        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """Return optional customization step."""
        return [
            {
                'description': '(Optional) Customize index.md content to personalize your site',
                'doc_url': 'https://ampl.clair.ucsb.edu/telar-docs/docs/6-customization/3-home-page/'
            }
        ]
