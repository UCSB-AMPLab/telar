"""
Migration from v0.9.0-beta to v0.9.1-beta.

This is a backward-compatible patch release that adds:
- KaTeX-based LaTeX math rendering with automatic per-page detection
- Case-insensitive file extension matching bug fix
- Encrypted story LaTeX support (post-decryption KaTeX loading)

No structural changes required — framework files are updated automatically.
No _config.yml changes, no file renames, no CSV schema changes.

Version: v0.9.1-beta
"""

from typing import List, Dict
from .base import BaseMigration


class Migration090to091(BaseMigration):
    """Migration from v0.9.0 to v0.9.1 - LaTeX support, extension bug fix."""

    from_version = "0.9.0-beta"
    to_version = "0.9.1-beta"
    description = "LaTeX math rendering (KaTeX), case-insensitive extension fix"

    def check_applicable(self) -> bool:
        """Check if migration should run."""
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # Phase 1: Add new files
        print("  Phase 1: Adding new files...")
        changes.extend(self._add_new_files())

        # Phase 2: Update existing framework files
        print("  Phase 2: Updating framework files...")
        changes.extend(self._update_framework_files())

        # Phase 3: Update version
        print("  Phase 3: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("0.9.1-beta", today):
            changes.append(f"Updated _config.yml: version 0.9.1-beta ({today})")

        return changes

    def _add_new_files(self) -> List[str]:
        """Add new files introduced in v0.9.1."""
        changes = []

        new_files = {
            'scripts/telar/latex.py': 'LaTeX detection module (has_latex, protect/restore)',
            '_includes/katex.html': 'KaTeX CDN loading and delimiter config',
            '_sass/_latex.scss': 'LaTeX styling overrides',
            'tests/unit/test_latex_detection.py': 'LaTeX detection unit tests',
        }

        for file_path, description in new_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(f"Added {file_path} - {description}")
            else:
                changes.append(f"Warning: Could not fetch {file_path}")

        return changes

    def _update_framework_files(self) -> List[str]:
        """Update framework files from GitHub repository."""
        changes = []

        framework_files = {
            'scripts/telar/processors/stories.py': 'LaTeX detection in story content, extension fix',
            'scripts/telar/processors/objects.py': 'LaTeX detection in object descriptions, extension fix',
            'scripts/telar/core.py': 'Include has_latex in story JSON metadata',
            'scripts/generate_collections.py': 'LaTeX detection in objects and glossary',
            'scripts/telar/markdown.py': 'LaTeX protection through markdown processing',
            '_layouts/story.html': 'Dynamic KaTeX loading for stories with LaTeX',
            '_layouts/default.html': 'Conditional KaTeX loading (objects, glossary, custom pages)',
            'assets/css/telar.scss': 'Added LaTeX stylesheet import',
            'assets/js/telar-story/panels.js': 'LaTeX re-rendering after panel content injection',
            'assets/js/telar.js': 'LaTeX re-rendering after glossary content injection',
            'assets/js/story-unlock.js': 'Post-decryption KaTeX loading for encrypted stories',
            'assets/js/telar-story.js': 'Rebuilt JS bundle (includes panels.js LaTeX changes)',
            'assets/js/telar-story.js.map': 'Updated source map',
            'README.md': 'Updated version badge',
            'CHANGELOG.md': 'Added v0.9.1-beta changelog entry',
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
