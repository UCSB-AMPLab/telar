"""
Migration from v0.3.1-beta to v0.3.2-beta.

Changes:
- Move index.html to _layouts/index.html
- Create editable index.md in root
- Manual step: Update build.yml workflow file
"""

from typing import List, Dict
from .base import BaseMigration


class Migration031to032(BaseMigration):
    """Migration from v0.3.1 to v0.3.2 - index page refactor."""

    from_version = "0.3.1-beta"
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

The homepage can now be customized by editing the `index.md` file in the root folder of your repository. Edit it to remove or replace this message. To learn more, visit the [documentation](https://telar.org/docs/6-customization/3-home-page/).
"""

    def check_applicable(self) -> bool:
        """Check if index.html exists."""
        return self._file_exists('index.html')

    def apply(self) -> List[str]:
        """Apply index refactoring."""
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

        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """Return workflow update and optional customization steps (conditional)."""
        manual_steps = []

        # Check if build.yml still has old cron schedule
        workflow_content = self._read_file('.github/workflows/build.yml')
        if workflow_content and 'schedule:' in workflow_content:
            manual_steps.append({
                'description': 'Update GitHub Actions workflow file (.github/workflows/build.yml) - Replace with latest version from https://github.com/UCSB-AMPLab/telar/blob/main/.github/workflows/build.yml to remove deprecated cron schedule',
                'doc_url': 'https://telar.org/docs/2-workflows/upgrading/'
            })

        # Always include optional customization step
        manual_steps.append({
            'description': '(Optional) Customize index.md content to personalize your site',
            'doc_url': 'https://telar.org/docs/6-customization/3-home-page/'
        })

        return manual_steps
