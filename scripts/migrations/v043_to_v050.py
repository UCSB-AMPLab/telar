"""
Migration from v0.4.3-beta to v0.5.0-beta.

Changes:
- Flattens image directory structure (objects/ and additional/ → flat images/)
- Updates all image path references in .md files
- Renames iiif_manifest column to source_url in objects.csv
- Removes unused dependencies (scrollama, standalone openseadragon)
- Adds share/embed UI components
- Extends image format support (HEIC, WebP, TIFF)

Version: v0.5.0-beta
"""

from typing import List, Dict, Set, Optional
import os
import re
import csv
import shutil
from .base import BaseMigration


class Migration043to050(BaseMigration):
    """Migration from v0.4.3 to v0.5.0 - flattened images and share/embed UI."""

    from_version = "0.4.3-beta"
    to_version = "0.5.0-beta"
    description = "Flattened image structure, share/embed UI, extended formats"

    def check_applicable(self) -> bool:
        """
        Check if migration should run.

        Always returns True since v0.5.0 handles both old and new structures.
        Migration is safe and idempotent.
        """
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # Phase 1: Discovery - identify CSV images and scan .md files
        print("  Phase 1: Discovering images and references...")
        csv_images = self._discover_csv_images()
        md_references = self._discover_md_references()
        changes.append(f"Discovered {len(csv_images)} CSV-referenced images")
        changes.append(f"Found {len(md_references)} image references in .md files")

        # Phase 2: Migrate images with smart conflict resolution
        print("  Phase 2: Migrating images...")
        migration_changes = self._migrate_images(csv_images)
        changes.extend(migration_changes)

        # Phase 3: Update all image path references in .md files
        print("  Phase 3: Updating image paths in .md files...")
        path_changes = self._update_md_references()
        changes.extend(path_changes)

        # Phase 4: Update objects.csv column header
        print("  Phase 4: Updating objects.csv...")
        csv_changes = self._update_csv_column()
        changes.extend(csv_changes)

        # Phase 5: Cleanup operations
        print("  Phase 5: Cleaning up unused files...")
        cleanup_changes = self._cleanup_unused_files()
        changes.extend(cleanup_changes)

        # Phase 6: Create future media directories
        print("  Phase 6: Creating future media directories...")
        directory_changes = self._create_future_media_directories()
        changes.extend(directory_changes)

        # Phase 7: Update framework files from GitHub
        print("  Phase 7: Updating framework files...")
        framework_changes = self._update_framework_files()
        changes.extend(framework_changes)

        # Phase 8: Update _config.yml version
        print("  Phase 8: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("0.5.0-beta", today):
            changes.append(f"Updated _config.yml: version 0.5.0-beta ({today})")

        return changes

    def _discover_csv_images(self) -> Set[str]:
        """
        Read objects.csv and identify which images are actively used.

        Returns:
            Set of image filenames (without directory path)
        """
        csv_images = set()
        csv_path = os.path.join(self.repo_root, 'components/structures/objects.csv')

        if not os.path.exists(csv_path):
            return csv_images

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Check both old and new column names
                    manifest = row.get('iiif_manifest') or row.get('source_url')
                    if manifest and not manifest.startswith('http'):
                        # It's a local file reference, extract filename
                        filename = os.path.basename(manifest)
                        csv_images.add(filename)
        except Exception as e:
            print(f"  ⚠️  Warning: Could not read objects.csv: {e}")

        return csv_images

    def _discover_md_references(self) -> Dict[str, List[tuple]]:
        """
        Scan all .md files for image references.

        Returns:
            Dict mapping file paths to list of (old_path, line_number) tuples
        """
        references = {}
        stories_dir = os.path.join(self.repo_root, '_stories')

        # Pattern to match image paths in markdown and HTML
        # Matches: ![alt](path), <img src="path">, background-image: url(path)
        # Supports relative paths, absolute paths, and full URLs
        img_pattern = re.compile(
            r'(?:!\[.*?\]\(|<img[^>]+src=["\']|url\(["\']?)'
            r'((?:https?://[^/\s]+(?:/[^\s]*?)?)?(?:\.\./|/)?components/images/(?:objects|additional)/[^)\s"\']+)',
            re.IGNORECASE
        )

        # Scan _stories directory
        if os.path.exists(stories_dir):
            for filename in os.listdir(stories_dir):
                if filename.endswith('.md'):
                    file_path = os.path.join(stories_dir, filename)
                    refs = self._scan_file_for_images(file_path, img_pattern)
                    if refs:
                        references[file_path] = refs

        # Scan root directory for .md files
        for filename in os.listdir(self.repo_root):
            if filename.endswith('.md'):
                file_path = os.path.join(self.repo_root, filename)
                refs = self._scan_file_for_images(file_path, img_pattern)
                if refs:
                    references[file_path] = refs

        return references

    def _scan_file_for_images(self, file_path: str, pattern: re.Pattern) -> List[tuple]:
        """
        Scan a single file for image references.

        Args:
            file_path: Absolute path to file
            pattern: Compiled regex pattern to match image paths

        Returns:
            List of (image_path, line_number) tuples
        """
        references = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    matches = pattern.findall(line)
                    for match in matches:
                        references.append((match, line_num))
        except Exception as e:
            print(f"  ⚠️  Warning: Could not scan {file_path}: {e}")

        return references

    def _migrate_images(self, csv_images: Set[str]) -> List[str]:
        """
        Migrate images from subdirectories to flat structure.

        Priority: CSV-referenced images keep their names, additional/ images
        get renamed if conflicts exist.

        Args:
            csv_images: Set of filenames referenced in objects.csv

        Returns:
            List of change descriptions
        """
        changes = []
        objects_dir = os.path.join(self.repo_root, 'components/images/objects')
        additional_dir = os.path.join(self.repo_root, 'components/images/additional')
        target_dir = os.path.join(self.repo_root, 'components/images')

        # Track moved files to detect actual files moved
        moved_count = 0
        renamed_count = 0
        conflicts = []

        # Phase 1: Move CSV-referenced images from objects/ (these get priority)
        if os.path.exists(objects_dir):
            for filename in os.listdir(objects_dir):
                src = os.path.join(objects_dir, filename)
                if not os.path.isfile(src):
                    continue

                dest = os.path.join(target_dir, filename)

                # Check if already exists in target
                if os.path.exists(dest):
                    # Already migrated, skip
                    continue

                # Move the file
                try:
                    os.rename(src, dest)
                    moved_count += 1
                except Exception as e:
                    changes.append(f"⚠️  Warning: Could not move {filename}: {e}")

        # Phase 2: Move additional/ images (rename if conflicts)
        if os.path.exists(additional_dir):
            for filename in os.listdir(additional_dir):
                src = os.path.join(additional_dir, filename)
                if not os.path.isfile(src):
                    continue

                dest = os.path.join(target_dir, filename)

                # Check for conflict
                if os.path.exists(dest):
                    # Conflict! Rename with suffix
                    base, ext = os.path.splitext(filename)
                    new_filename = f"{base}-2{ext}"
                    dest = os.path.join(target_dir, new_filename)

                    # Track the rename for path updates
                    conflicts.append((filename, new_filename))

                    try:
                        os.rename(src, dest)
                        renamed_count += 1
                        changes.append(f"Renamed and moved: {filename} → {new_filename} (conflict resolution)")
                    except Exception as e:
                        changes.append(f"⚠️  Warning: Could not move {filename}: {e}")
                else:
                    # No conflict, move as-is
                    try:
                        os.rename(src, dest)
                        moved_count += 1
                    except Exception as e:
                        changes.append(f"⚠️  Warning: Could not move {filename}: {e}")

        # Clean up empty directories
        for old_dir in [objects_dir, additional_dir]:
            if os.path.exists(old_dir):
                try:
                    # Check if empty
                    if not os.listdir(old_dir):
                        os.rmdir(old_dir)
                        changes.append(f"Removed empty directory: {os.path.relpath(old_dir, self.repo_root)}")
                except Exception as e:
                    pass  # Don't fail if directory not empty or can't be removed

        # Summary
        if moved_count > 0 or renamed_count > 0:
            changes.append(f"Migrated {moved_count} images to flat structure")
            if renamed_count > 0:
                changes.append(f"Renamed {renamed_count} images to resolve conflicts")
        else:
            changes.append("No images to migrate (already using flat structure)")

        # Store conflicts for path updates
        self._conflict_map = {old: new for old, new in conflicts}

        return changes

    def _update_md_references(self) -> List[str]:
        """
        Update all image path references in .md files.

        Updates both:
        - components/images/objects/foo.jpg → components/images/foo.jpg
        - components/images/additional/bar.png → components/images/bar-2.png (if renamed)

        Returns:
            List of detailed change descriptions
        """
        changes = []
        stories_dir = os.path.join(self.repo_root, '_stories')
        target_dir = os.path.join(self.repo_root, 'components/images')

        # Files to scan
        files_to_scan = []

        # Add _stories/*.md
        if os.path.exists(stories_dir):
            for filename in os.listdir(stories_dir):
                if filename.endswith('.md'):
                    files_to_scan.append(os.path.join(stories_dir, filename))

        # Add root *.md
        for filename in os.listdir(self.repo_root):
            if filename.endswith('.md'):
                files_to_scan.append(os.path.join(self.repo_root, filename))

        total_files_updated = 0
        total_paths_updated = 0

        for file_path in files_to_scan:
            file_changes, paths_changed = self._update_file_paths(file_path, target_dir)
            if paths_changed > 0:
                total_files_updated += 1
                total_paths_updated += paths_changed
                # Report file-by-file details
                rel_path = os.path.relpath(file_path, self.repo_root)
                changes.append(f"Updated {rel_path}: {paths_changed} path(s) changed")
                for change in file_changes:
                    changes.append(f"  {change}")

        if total_paths_updated > 0:
            changes.append(f"Total: Updated {total_paths_updated} image path(s) across {total_files_updated} file(s)")
        else:
            changes.append("No image path updates needed")

        return changes

    def _update_file_paths(self, file_path: str, target_dir: str) -> tuple:
        """
        Update image paths in a single file.

        Args:
            file_path: Absolute path to file
            target_dir: Absolute path to target images directory

        Returns:
            Tuple of (list of change descriptions, count of paths changed)
        """
        file_changes = []
        paths_changed = 0

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            original_content = content
            warnings = []

            # Pattern to match and replace image paths
            # Matches: ![alt](path), <img src="path">, url(path)
            def replace_path(match):
                nonlocal paths_changed
                full_match = match.group(0)
                old_path = match.group(2)  # Group 2 is the path, group 1 is the prefix

                # Extract the filename and subdirectory
                path_match = re.search(r'components/images/(objects|additional)/(.+)$', old_path, re.IGNORECASE)
                if not path_match:
                    return full_match

                subdir = path_match.group(1)
                filename = path_match.group(2)

                # Check if this file was renamed due to conflict
                if hasattr(self, '_conflict_map') and filename in self._conflict_map:
                    new_filename = self._conflict_map[filename]
                else:
                    new_filename = filename

                # Build new path (flattened)
                # Check if it's a full URL (preserve protocol and domain)
                url_match = re.match(r'(https?://[^/]+(?:/[^/]*?)?)/components/images/(?:objects|additional)/', old_path)
                if url_match:
                    # Full URL - preserve everything before /components/images/
                    url_prefix = url_match.group(1)
                    new_path = f"{url_prefix}/components/images/{new_filename}"
                elif old_path.startswith('../'):
                    new_path = f"../components/images/{new_filename}"
                elif old_path.startswith('/'):
                    new_path = f"/components/images/{new_filename}"
                else:
                    new_path = f"components/images/{new_filename}"

                # Check if file actually exists
                check_filename = new_filename
                file_exists = os.path.exists(os.path.join(target_dir, check_filename))

                if not file_exists:
                    # Warn but still update for consistency
                    warnings.append(f"⚠️  Path updated but file not found: {new_path}")

                # Replace the path in the match
                new_match = full_match.replace(old_path, new_path)
                paths_changed += 1

                file_changes.append(f"{old_path} → {new_path}")

                return new_match

            # Apply replacements
            # Supports relative paths, absolute paths, and full URLs
            pattern = re.compile(
                r'(!\[.*?\]\(|<img[^>]+src=["\']|url\(["\']?)'
                r'((?:https?://[^/\s]+(?:/[^\s]*?)?)?(?:\.\./|/)?components/images/(?:objects|additional)/[^)\s"\']+)',
                re.IGNORECASE
            )

            content = pattern.sub(replace_path, content)

            # Write back if changed
            if content != original_content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                # Add warnings to file changes
                file_changes.extend(warnings)

        except Exception as e:
            file_changes.append(f"⚠️  Error updating file: {e}")

        return file_changes, paths_changed

    def _update_csv_column(self) -> List[str]:
        """
        Update iiif_manifest column to source_url in objects.csv.

        Returns:
            List of change descriptions
        """
        changes = []
        csv_path = os.path.join(self.repo_root, 'components/structures/objects.csv')

        if not os.path.exists(csv_path):
            changes.append("No objects.csv found (skipping CSV update)")
            return changes

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Check current state
            if 'iiif_manifest' in content and 'source_url' not in content:
                # Update header (only first occurrence)
                lines = content.split('\n')
                if lines and 'iiif_manifest' in lines[0]:
                    lines[0] = lines[0].replace('iiif_manifest', 'source_url')
                    updated_content = '\n'.join(lines)

                    with open(csv_path, 'w', encoding='utf-8') as f:
                        f.write(updated_content)

                    changes.append("Updated objects.csv: Renamed 'iiif_manifest' column to 'source_url'")
            elif 'source_url' in content:
                changes.append("objects.csv already uses 'source_url' column")
            else:
                changes.append("objects.csv does not use manifest columns (no update needed)")

        except Exception as e:
            changes.append(f"⚠️  Warning: Could not update objects.csv: {e}")

        return changes

    def _cleanup_unused_files(self) -> List[str]:
        """
        Remove unused dependencies and files.

        Returns:
            List of change descriptions
        """
        changes = []

        files_to_remove = [
            'assets/js/scrollama.min.js',
            'assets/js/openseadragon.min.js',
        ]

        for rel_path in files_to_remove:
            full_path = os.path.join(self.repo_root, rel_path)
            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                    changes.append(f"Removed unused file: {rel_path}")
                except Exception as e:
                    changes.append(f"⚠️  Warning: Could not remove {rel_path}: {e}")

        # Remove empty openseadragon directory
        osd_dir = os.path.join(self.repo_root, 'assets/images/openseadragon')
        if os.path.exists(osd_dir):
            try:
                # Only remove if empty
                if not os.listdir(osd_dir):
                    os.rmdir(osd_dir)
                    changes.append("Removed empty directory: assets/images/openseadragon")
            except Exception:
                pass  # Silently fail if directory not empty

        # Remove deprecated Google Sheets integration documentation folder
        docs_gs_dir = os.path.join(self.repo_root, 'docs/google_sheets_integration')
        if os.path.exists(docs_gs_dir):
            try:
                shutil.rmtree(docs_gs_dir)
                changes.append("Removed deprecated directory: docs/google_sheets_integration")
            except Exception as e:
                changes.append(f"⚠️  Warning: Could not remove docs/google_sheets_integration: {e}")

        return changes

    def _create_future_media_directories(self) -> List[str]:
        """
        Create placeholder directories for future media type support.

        v0.5.0 creates directory structure for:
        - PDFs (planned for v0.6.0)
        - Audio (planned for v0.7.0)
        - 3D models (planned for v0.8.0)

        Returns:
            List of change descriptions
        """
        changes = []

        directories = [
            'components/pdfs',
            'components/audio',
            'components/3d-models',
        ]

        for dir_path in directories:
            full_path = os.path.join(self.repo_root, dir_path)
            if not os.path.exists(full_path):
                try:
                    os.makedirs(full_path, exist_ok=True)
                    changes.append(f"Created directory: {dir_path}")
                except Exception as e:
                    changes.append(f"⚠️  Warning: Could not create {dir_path}: {e}")

        return changes

    def _update_framework_files(self) -> List[str]:
        """
        Update core framework files from GitHub.

        v0.5.0 includes:
        - CSV-driven processing with flattened paths
        - Extended format support (HEIC, WebP, TIFF)
        - Share/embed UI components
        - Embed mode support
        - Various bug fixes and improvements
        """
        changes = []

        framework_files = {
            # Python scripts with v0.5.0 changes
            'scripts/csv_to_json.py': 'CSV-driven processing, flattened paths',
            'scripts/generate_iiif.py': 'Extended format support, case-insensitive',

            # Layouts - embed mode support
            '_layouts/story.html': 'Embed mode support, share button',
            '_layouts/index.html': 'Share button in navbar',
            '_layouts/default.html': 'Share panel modal',

            # Includes - new share/embed UI
            '_includes/share-button.html': 'Share button component',
            '_includes/share-panel.html': 'Share/embed modal',
            '_includes/header.html': 'Navbar share button',
            '_includes/panels.html': 'Mobile image width fix',

            # JavaScript - new features
            'assets/js/embed.js': 'Embed mode detection and banner',
            'assets/js/share-panel.js': 'Share/embed functionality',
            'assets/js/story.js': 'Embed navigation, panel fixes',

            # Styles - all v0.5.0 features
            'assets/css/telar.scss': 'Embed mode, share UI, carousel, mobile fixes',

            # Language files
            '_data/languages/en.yml': 'Share/embed strings, updated error messages',
            '_data/languages/es.yml': 'Spanish translations',

            # Documentation
            'README.md': 'v0.5.0 documentation',
            'CHANGELOG.md': 'v0.5.0 changelog',

            # Component directories
            'components/README.md': 'Updated directory structure',
            'components/images/README.md': 'Flattened structure documentation',
            'components/pdfs/README.md': 'Future v0.6.0 placeholder',
            'components/audio/README.md': 'Future v0.7.0 placeholder',
            'components/3d-models/README.md': 'Future v0.8.0 placeholder',
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
                'description': '''⚠️ **CRITICAL: Update Your GitHub Actions Workflows** ⚠️

**Without this step, images will NOT display on your published site.**

The upgrade changed where images are stored, but your GitHub Actions workflows still point to the old location. You must update two files: `build.yml` and `upgrade.yml`.

---

**Option 1: Using the GitHub Website**

1. Go to the Telar repository workflows: https://github.com/UCSB-AMPLab/telar/tree/main/.github/workflows
2. Click on `build.yml`, then click the "Raw" button, and copy all the text
3. In **your** repository on GitHub, go to `.github/workflows/build.yml`
4. Click the pencil icon (✏️) to edit, delete everything, and paste the new content
5. Click "Commit changes" at the bottom
6. Repeat steps 2-5 for `upgrade.yml`

---

**Option 2: Using the Command Line** (if you've been syncing your repository to your machine and are comfortable with git)

Run these commands in your repository:

```bash
# Download the updated workflows
curl -o .github/workflows/build.yml https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/build.yml
curl -o .github/workflows/upgrade.yml https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/upgrade.yml

# Commit the changes
git add .github/workflows/
git commit -m "Update workflows for v0.5.0 image structure"
git push
```

**That's it!** Your next build will use the correct image locations.''',
                'doc_url': 'https://github.com/UCSB-AMPLab/telar/tree/main/.github/workflows',
                'critical': True
            },
            {
                'description': 'Regenerate IIIF tiles to ensure images work with new structure: python3 scripts/generate_iiif.py',
            },
            {
                'description': 'Test your site build: bundle exec jekyll build',
            },
            {
                'description': 'Test embed mode: Add ?embed=true to any story URL to see the embed mode UI with navigation banner',
            },
            {
                'description': 'Explore new share/embed UI: Click the share button (icon with arrow) on stories or homepage to access share links and embed code',
            },
            {
                'description': 'Optional: Install pillow-heif for HEIC/HEIF support (iPhone photos). Run: pip install pillow-heif. The framework gracefully degrades if not installed, converting HEIC to standard formats.',
            },
        ]
