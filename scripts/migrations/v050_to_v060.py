"""
Migration from v0.5.0-beta to v0.6.0-beta.

Changes:
- Gitignore generated files (_data/*.json, _jekyll-files/)
- Remove tracked generated files from git index
- Add demo content fetch to build workflow
- Multilingual UI support
- Custom pages system (move pages/about.md to components/texts/pages/)
- Data-driven navigation menu (_data/navigation.yml)

Version: v0.6.0-beta
"""

from typing import List, Dict
import os
import subprocess
import glob
from .base import BaseMigration


class Migration050to060(BaseMigration):
    """Migration from v0.5.0 to v0.6.0 - gitignore generated files, multilingual UI, custom pages."""

    from_version = "0.5.0-beta"
    to_version = "0.6.0-beta"
    description = "Gitignore generated files, multilingual UI support, custom pages system"

    def check_applicable(self) -> bool:
        """
        Check if migration should run.

        Returns True since v0.6.0 handles all cases safely.
        """
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # Phase 1: Update .gitignore with generated file patterns
        print("  Phase 1: Updating .gitignore...")
        gitignore_changes = self._update_gitignore()
        changes.extend(gitignore_changes)

        # Phase 2: Remove tracked generated files from git index
        print("  Phase 2: Removing generated files from git tracking...")
        git_changes = self._remove_generated_from_git()
        changes.extend(git_changes)

        # Phase 3: Update framework files from GitHub
        print("  Phase 3: Updating framework files...")
        framework_changes = self._update_framework_files()
        changes.extend(framework_changes)

        # Phase 4: Update _config.yml version
        print("  Phase 4: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("0.6.0-beta", today):
            changes.append(f"Updated _config.yml: version 0.6.0-beta ({today})")

        return changes

    def _update_gitignore(self) -> List[str]:
        """
        Add generated file patterns to .gitignore.

        Returns:
            List of change descriptions
        """
        changes = []

        # Generated JSON files
        # Note: With story_id feature, story files use semantic names (e.g., your-story.json, paisajes-demo.json)
        json_entries = [
            '_data/objects.json',
            '_data/project.json',
            '_data/*.json',
            '!_data/languages/',
        ]

        if self._ensure_gitignore_entries(
            json_entries,
            '# Generated JSON files (from components/structures/*.csv by csv_to_json.py)'
        ):
            changes.append("Added generated JSON patterns to .gitignore")

        # Generated Jekyll collection files
        jekyll_entries = [
            '_jekyll-files/',
        ]

        if self._ensure_gitignore_entries(
            jekyll_entries,
            '# Generated Jekyll collection files (from components/texts/ by generate_collections.py)'
        ):
            changes.append("Added _jekyll-files/ to .gitignore")

        # Demo glossary files
        demo_entries = [
            'components/texts/glossary/_demo_*',
        ]

        if self._ensure_gitignore_entries(
            demo_entries,
            '# Demo glossary files (created by csv_to_json.py from demo bundle)'
        ):
            changes.append("Added demo glossary pattern to .gitignore")

        if not changes:
            changes.append("Gitignore patterns already present")

        return changes

    def _remove_generated_from_git(self) -> List[str]:
        """
        Remove tracked generated files from git index.

        Uses git rm --cached to untrack files without deleting them.
        This is safe and idempotent - runs with check=False.

        Returns:
            List of change descriptions
        """
        changes = []
        removed_count = 0

        # Remove generated JSON files
        json_files = [
            '_data/objects.json',
            '_data/project.json',
        ]

        # Add all story JSON files (includes both story-*.json and semantic names like your-story.json)
        # Exclude demo-glossary.json and languages/ directory
        data_pattern = os.path.join(self.repo_root, '_data/*.json')
        for json_file in glob.glob(data_pattern):
            rel_path = os.path.relpath(json_file, self.repo_root)
            # Exclude demo-glossary.json (handled separately) and any non-story files
            if rel_path not in ['_data/objects.json', '_data/project.json', '_data/demo-glossary.json']:
                json_files.append(rel_path)

        for file_path in json_files:
            full_path = os.path.join(self.repo_root, file_path)
            if os.path.exists(full_path):
                result = subprocess.run(
                    ['git', 'rm', '--cached', file_path],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    removed_count += 1

        # Remove _jekyll-files/ directory from tracking
        jekyll_dir = os.path.join(self.repo_root, '_jekyll-files')
        if os.path.exists(jekyll_dir):
            result = subprocess.run(
                ['git', 'rm', '--cached', '-r', '_jekyll-files/'],
                cwd=self.repo_root,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                removed_count += 1
                changes.append("Removed _jekyll-files/ from git tracking")

        # Remove demo glossary files from tracking
        demo_pattern = os.path.join(self.repo_root, 'components/texts/glossary/_demo_*.md')
        demo_files = glob.glob(demo_pattern)
        for demo_file in demo_files:
            rel_path = os.path.relpath(demo_file, self.repo_root)
            result = subprocess.run(
                ['git', 'rm', '--cached', rel_path],
                cwd=self.repo_root,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                removed_count += 1

        if removed_count > 0:
            changes.append(f"Removed {removed_count} generated file(s) from git tracking")
        else:
            changes.append("No generated files were tracked in git")

        return changes

    def _update_framework_files(self) -> List[str]:
        """
        Update core framework files from GitHub.

        v0.6.0 includes:
        - Demo content feature with fetch_demo_content.py
        - Multilingual UI support
        - Generated files gitignored
        - Build workflow updated for demo content
        """
        changes = []

        framework_files = {
            # Python scripts with v0.6.0 changes
            'scripts/csv_to_json.py': 'Demo content processing with widgets/glossary',
            'scripts/fetch_demo_content.py': 'Demo content bundle fetcher',
            'scripts/generate_collections.py': 'Collection generation',

            # GitHub Actions workflows
            '.github/workflows/build.yml': 'Demo content fetch step added',
            '.github/workflows/upgrade.yml': 'v0.6.0 migration support',

            # Language files - multilingual UI
            '_data/languages/en.yml': 'Multilingual UI strings',
            '_data/languages/es.yml': 'Spanish translations',

            # Layouts and includes
            '_layouts/story.html': 'Multilingual support',
            '_layouts/default.html': 'Multilingual support',

            # JavaScript
            'assets/js/story.js': 'Demo content support',

            # Documentation
            'README.md': 'v0.6.0 documentation',
            'CHANGELOG.md': 'v0.6.0 changelog',

            # Gitignore (updated with generated file patterns)
            '.gitignore': 'Generated files gitignored',
        }

        for file_path, description in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path}: {description}")
            else:
                changes.append(f"⚠️  Warning: Could not fetch {file_path} from GitHub")

        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """
        Manual steps for users to complete after migration.

        Returns:
            List of manual step descriptions
        """
        return [
            {
                'description': 'Run the build scripts to regenerate files: python3 scripts/csv_to_json.py && python3 scripts/generate_collections.py',
            },
            {
                'description': 'Test your site build: bundle exec jekyll build',
            },
            {
                'description': 'Optional: Enable demo content by setting include_demo_content: true in _config.yml under story_interface',
            },
            {
                'description': 'If using demo content, run: python3 scripts/fetch_demo_content.py to download the demo bundle',
            },
        ]
