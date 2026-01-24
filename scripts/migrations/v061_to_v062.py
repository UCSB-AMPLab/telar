"""
Migration from v0.6.1-beta to v0.6.2-beta.

Changes:
- Improved viewer preloading with manifest prefetching
- Case-insensitive object ID and file path matching
- Glossary-to-glossary linking support
- Development feature flags (hide_stories, hide_collections)
- All-in-one build_local_site.py script
- Panel semantic markup fix (h5→h1)
- Removed deprecated sample glossary entries

Version: v0.6.2-beta
"""

from typing import List, Dict
import os
import re
from .base import BaseMigration


class Migration061to062(BaseMigration):
    """Migration from v0.6.1 to v0.6.2 - viewer preloading, case sensitivity, dev features."""

    from_version = "0.6.1-beta"
    to_version = "0.6.2-beta"
    description = "Improved viewer preloading, case-insensitive matching, development features"

    def check_applicable(self) -> bool:
        """
        Check if migration should run.

        Returns True since v0.6.2 applies improvements that benefit all users.
        """
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # Phase 1: Rename config section (testing-features → development-features)
        print("  Phase 1: Updating configuration...")
        config_changes = self._update_config_section()
        changes.extend(config_changes)

        # Phase 2: Update framework files from GitHub
        print("  Phase 2: Updating framework files...")
        framework_changes = self._update_framework_files()
        changes.extend(framework_changes)

        # Phase 3: Clean up deprecated glossary files
        print("  Phase 3: Cleaning up deprecated glossary files...")
        glossary_changes = self._cleanup_deprecated_glossary()
        changes.extend(glossary_changes)

        # Phase 4: Update _config.yml version
        print("  Phase 4: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("0.6.2-beta", today):
            changes.append(f"Updated _config.yml: version 0.6.2-beta ({today})")

        return changes

    def _update_config_section(self) -> List[str]:
        """
        Update development-features section in _config.yml.

        - Rename testing-features to development-features
        - Add viewer_preloading section if missing
        - Add hide_stories and hide_collections flags if missing

        Returns:
            List of change descriptions
        """
        changes = []
        config_path = os.path.join(self.repo_root, '_config.yml')

        if not os.path.exists(config_path):
            return changes

        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()

        modified = False

        # Check if rename is needed
        if 'testing-features:' in content and 'development-features:' not in content:
            content = content.replace('testing-features:', 'development-features:')
            modified = True
            changes.append("Renamed config section: testing-features → development-features")

        # Add viewer_preloading section if missing
        if 'viewer_preloading:' not in content and 'development-features:' in content:
            viewer_preloading_block = '''
  # Viewer preloading configuration
  # Controls how story viewers are preloaded for smoother navigation.
  # Higher values = smoother scrolling but more memory usage.
  # Lower values = less memory but may show loading shimmer during navigation.
  # These defaults work well for most sites. Only adjust if experiencing issues.
  viewer_preloading:
    max_viewer_cards: 10    # Max viewers in memory. Higher = smoother, more memory. (default: 10, max: 15)
    preload_steps: 6        # Steps to preload ahead. Higher = smoother, more memory. (default: 6)
    loading_threshold: 5    # Show shimmer on intro if story has >= N viewers. (default: 5)
    min_ready_viewers: 3    # Hide shimmer when N viewers ready. (default: 3)
'''
            # Insert after development-features: line
            content = content.replace('development-features:', 'development-features:' + viewer_preloading_block)
            modified = True
            changes.append("Added viewer_preloading configuration section")

        # Add hide_stories if missing
        if 'hide_stories:' not in content and 'development-features:' in content:
            hide_stories_block = '''
  # Hide stories - skips story generation and hides stories section from index
  # Objects remain visible and accessible
  hide_stories: false
'''
            # Find the end of development-features section and insert before next top-level key
            lines = content.split('\n')
            in_dev_features = False
            insert_index = -1
            for i, line in enumerate(lines):
                if line.startswith('development-features:'):
                    in_dev_features = True
                elif in_dev_features and line and not line.startswith(' ') and not line.startswith('\t') and not line.startswith('#'):
                    insert_index = i
                    break
            if insert_index > 0:
                lines.insert(insert_index, hide_stories_block.rstrip())
                content = '\n'.join(lines)
                modified = True
                changes.append("Added hide_stories flag")

        # Add hide_collections if missing
        if 'hide_collections:' not in content and 'development-features:' in content:
            hide_collections_block = '''
  # Hide collections - skips both object AND story generation
  # Hides stories section, objects teaser, and /objects/ nav link
  # Use this when building a site with only custom pages (no stories or objects)
  hide_collections: false
'''
            # Find the end of development-features section and insert before next top-level key
            lines = content.split('\n')
            in_dev_features = False
            insert_index = -1
            for i, line in enumerate(lines):
                if line.startswith('development-features:'):
                    in_dev_features = True
                elif in_dev_features and line and not line.startswith(' ') and not line.startswith('\t') and not line.startswith('#'):
                    insert_index = i
                    break
            if insert_index > 0:
                lines.insert(insert_index, hide_collections_block.rstrip())
                content = '\n'.join(lines)
                modified = True
                changes.append("Added hide_collections flag")

        if modified:
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(content)

        return changes

    def _update_framework_files(self) -> List[str]:
        """
        Update framework files from GitHub repository.

        Returns:
            List of change descriptions
        """
        changes = []

        # Files to update from GitHub
        framework_files = {
            # Layouts
            '_layouts/story.html': 'Story layout (viewer preloading config)',
            '_layouts/index.html': 'Index layout (hover prefetch, hide flags)',
            '_layouts/objects-index.html': 'Objects index (hide_collections flag)',

            # Includes
            '_includes/viewer.html': 'Viewer include (removed inline transition styles)',
            '_includes/header.html': 'Header (hide_collections nav flag)',
            '_includes/panels.html': 'Panels (h5→h1 semantic fix)',

            # JavaScript
            'assets/js/story.js': 'Story JS (viewer preloading overhaul)',
            'assets/js/telar.js': 'Telar JS (glossary-to-glossary linking)',

            # CSS
            'assets/css/telar.scss': 'Stylesheet (image overflow, h1 spacing, fade transitions)',

            # Python scripts
            'scripts/csv_to_json.py': 'CSV converter (case-insensitive matching)',
            'scripts/generate_collections.py': 'Collections generator (glossary links, hide flags)',
            'scripts/build_local_site.py': 'NEW: All-in-one local build script',

            # Documentation
            'README.md': 'README (version update)',
            'CHANGELOG.md': 'CHANGELOG (v0.6.2 release notes)',
        }

        for file_path, description in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                # Ensure parent directory exists for new files
                full_path = os.path.join(self.repo_root, file_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path} - {description}")
            else:
                changes.append(f"Warning: Failed to update {file_path}")

        return changes

    def _cleanup_deprecated_glossary(self) -> List[str]:
        """
        Remove deprecated sample glossary files only if unmodified.

        Compares current content against original template content.
        Files modified by users are preserved.

        Returns:
            List of change descriptions
        """
        changes = []

        # Deprecated files to potentially remove
        deprecated_files = [
            'components/texts/glossary/colonial-period.md',
            'components/texts/glossary/reduccion.md',
            'components/texts/glossary/resguardo.md',
            'components/texts/glossary/viceroyalty.md',
            'components/texts/glossary/iiif-manifest.md',
            'components/texts/glossary/markdown.md',
        ]

        for rel_path in deprecated_files:
            full_path = os.path.join(self.repo_root, rel_path)
            if os.path.exists(full_path):
                # Fetch original from GitHub v0.6.1 to compare
                original = self._fetch_from_github(rel_path, branch='v0.6.1-beta')

                if original:
                    current = self._read_file(rel_path)
                    if current and current.strip() == original.strip():
                        # Unmodified - safe to delete
                        try:
                            os.remove(full_path)
                            changes.append(f"Removed deprecated: {rel_path}")
                        except Exception as e:
                            changes.append(f"Warning: Could not remove {rel_path}: {e}")
                    else:
                        # Modified by user - keep it
                        changes.append(f"Kept (user modified): {rel_path}")
                else:
                    # Couldn't fetch original - keep to be safe
                    changes.append(f"Kept (could not verify): {rel_path}")

        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """
        Return manual steps in user's language.

        Detects site language and returns appropriate bilingual manual steps.

        Returns:
            List of manual step dicts with 'description' and optional 'doc_url' keys
        """
        lang = self._detect_language()

        if lang == 'es':
            return self._get_manual_steps_es()
        else:
            return self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        """English manual steps for v0.6.2 migration."""
        return [
            {
                'description': '''**If you use GitHub Pages:**

No further actions needed. Your site will automatically use the improved viewer preloading when it rebuilds.''',
            },
            {
                'description': '''**If you work with your site locally:**

A new all-in-one build script is now available:

`python3 scripts/build_local_site.py`

This runs all build steps (CSV conversion, collections, IIIF, Jekyll) with a single command. Use `--skip-iiif` for faster rebuilds when images haven't changed.''',
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        """Spanish manual steps for v0.6.2 migration."""
        return [
            {
                'description': '''**Si usas GitHub Pages:**

No se requieren acciones adicionales. Tu sitio usará automáticamente la precarga mejorada del visor cuando se reconstruya.''',
            },
            {
                'description': '''**Si trabajas con tu sitio localmente:**

Un nuevo script de construcción todo-en-uno está disponible:

`python3 scripts/build_local_site.py`

Esto ejecuta todos los pasos de construcción (conversión CSV, colecciones, IIIF, Jekyll) con un solo comando. Usa `--skip-iiif` para reconstrucciones más rápidas cuando las imágenes no han cambiado.''',
            },
        ]
