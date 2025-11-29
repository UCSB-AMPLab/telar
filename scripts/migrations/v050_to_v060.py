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

        # Phase 1: Create new directories
        print("  Phase 1: Creating directories...")
        changes.extend(self._create_directories())

        # Phase 2: Move about page
        print("  Phase 2: Moving about page...")
        changes.extend(self._move_about_page())

        # Phase 3: Update .gitignore with generated file patterns
        print("  Phase 3: Updating .gitignore...")
        changes.extend(self._update_gitignore())

        # Phase 4: Remove tracked generated files from git index
        print("  Phase 4: Removing generated files from git tracking...")
        changes.extend(self._remove_generated_from_git())

        # Phase 5: Update configuration structure
        print("  Phase 5: Updating configuration...")
        changes.extend(self._update_config_structure())

        # Phase 6: Cleanup old demo content
        print("  Phase 6: Cleaning up old demo content...")
        changes.extend(self._cleanup_old_demo_content())

        # Phase 7: Update framework files from GitHub
        print("  Phase 7: Updating framework files...")
        changes.extend(self._update_framework_files())

        # Phase 8: Update _config.yml version
        print("  Phase 8: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("0.6.0-beta", today):
            changes.append(f"Updated _config.yml: version 0.6.0-beta ({today})")

        return changes

    def _create_directories(self) -> List[str]:
        """
        Create new directories for v0.6.0 features.

        Creates:
        - components/texts/pages/ for custom user pages (always)
        - components/texts/stories/your-story/ for English template (only if new site)
        - components/texts/stories/tu-historia/ for Spanish template (only if new site)

        Returns:
            List of change descriptions
        """
        changes = []

        # Always create pages directory
        directories = ['components/texts/pages']

        # Only add template directories for new sites (no custom stories)
        if not self._has_custom_stories():
            directories.extend([
                'components/texts/stories/your-story',
                'components/texts/stories/tu-historia',
            ])

        for dir_path in directories:
            full_path = os.path.join(self.repo_root, dir_path)
            if not os.path.exists(full_path):
                try:
                    os.makedirs(full_path, exist_ok=True)
                    changes.append(f"Created directory: {dir_path}/")
                except Exception as e:
                    changes.append(f"⚠️  Warning: Could not create {dir_path}: {e}")
            else:
                changes.append(f"Directory already exists: {dir_path}/")

        return changes

    def _move_about_page(self) -> List[str]:
        """
        Move about.md from pages/ to components/texts/pages/.

        Strategy:
        - If pages/about.md exists: Move it (preserves user customizations)
        - If already moved: Do nothing
        - If no about.md anywhere: Fetch default from GitHub

        Safely removes empty pages/ directory after move.

        Returns:
            List of change descriptions
        """
        changes = []

        old_path = 'pages/about.md'
        new_path = 'components/texts/pages/about.md'

        # Check if old file exists
        if self._file_exists(old_path):
            # Move existing file (preserves user customizations)
            if self._move_file(old_path, new_path):
                changes.append(f"Moved {old_path} → {new_path}")

                # Try to remove old pages/ directory if empty
                old_dir = os.path.join(self.repo_root, 'pages')
                if os.path.exists(old_dir):
                    try:
                        if not os.listdir(old_dir):
                            os.rmdir(old_dir)
                            changes.append("Removed empty pages/ directory")
                    except:
                        pass  # Directory not empty or can't remove
            else:
                changes.append(f"⚠️  Warning: Could not move {old_path}")

        elif not self._file_exists(new_path):
            # No existing about.md, fetch default from GitHub
            content = self._fetch_from_github(new_path)
            if content:
                self._write_file(new_path, content)
                changes.append(f"Created default {new_path} from GitHub")
            else:
                changes.append(f"⚠️  Warning: Could not fetch {new_path}")

        else:
            # Already in new location
            changes.append(f"{new_path} already exists")

        return changes

    def _update_config_structure(self) -> List[str]:
        """
        Update _config.yml structure for v0.6.0.

        Changes:
        1. Move story_interface section ABOVE Google Sheets/DO NOT EDIT line
        2. Add show_object_credits flag to story_interface
        3. Intelligently set include_demo_content based on user's demo usage
        4. Update Google Sheets comment block URL to telar.org
        5. Update logo comment to include recommended dimensions

        Uses text-based editing to preserve formatting and comments.

        Returns:
            List of change descriptions
        """
        changes = []
        config_path = '_config.yml'
        content = self._read_file(config_path)

        if not content:
            changes.append("⚠️  Warning: Could not read _config.yml")
            return changes

        lines = content.split('\n')

        # Step 1: Find and extract existing story_interface settings
        show_story_steps = True  # Default
        old_story_interface_start = -1
        old_story_interface_end = -1

        for i, line in enumerate(lines):
            if line.startswith('story_interface:'):
                old_story_interface_start = i
                # Find the header comment line before it (if any)
                if i > 0 and lines[i-1].strip().startswith('#'):
                    old_story_interface_start = i - 1
                continue

            if old_story_interface_start != -1 and old_story_interface_end == -1:
                # Check if we've exited the story_interface section
                if line and not line.startswith('  ') and not line.startswith('\t') and not line.startswith('#'):
                    old_story_interface_end = i
                    # Extract show_story_steps value
                    section_lines = lines[old_story_interface_start:old_story_interface_end]
                    for sl in section_lines:
                        if 'show_story_steps' in sl:
                            show_story_steps = 'false' not in sl.lower()
                    break

        # Step 2: Determine include_demo_content value
        should_enable_demos = self._should_enable_demo_content()
        demo_value = "true" if should_enable_demos else "false"

        # Step 3: Build new story_interface section
        new_story_interface = [
            '# Story Interface Settings',
            'story_interface:',
            f'  show_story_steps: {"true" if show_story_steps else "false"} # Set to false to hide "Step X" overlay in stories',
            '  show_object_credits: true # Set to true to display object credits badge (bottom-left corner, dismissable)',
            f'  include_demo_content: {demo_value} # Fetch demo stories from content.telar.org. Switch this off to hide demo stories and their content.',
            ''
        ]

        # Step 4: Remove old story_interface section
        if old_story_interface_start != -1:
            del lines[old_story_interface_start:old_story_interface_end]
            changes.append("Removed old story_interface section")

        # Step 5: Find insertion point (before Google Sheets or DO NOT EDIT)
        insert_index = -1
        for i, line in enumerate(lines):
            if 'google_sheets:' in line.lower() or 'DO NOT EDIT' in line:
                insert_index = i
                # Skip back over any comment lines
                while insert_index > 0 and lines[insert_index-1].strip().startswith('#'):
                    insert_index -= 1
                break

        if insert_index == -1:
            changes.append("⚠️  Warning: Could not find insertion point for story_interface")
            return changes

        # Step 6: Insert new story_interface section
        for j, new_line in enumerate(new_story_interface):
            lines.insert(insert_index + j, new_line)

        changes.append(f"Added story_interface section with include_demo_content: {demo_value}")
        if demo_value == "true":
            changes.append("  ℹ️  Enabled demo content (user had unmodified v0.5.0 demos + custom stories)")
        else:
            changes.append("  ℹ️  Demo content disabled (user has only demos or customized them)")

        # Step 7: Update Google Sheets comment URL
        for i, line in enumerate(lines):
            if 'ampl.clair.ucsb.edu/telar-docs/docs/workflows/google-sheets/' in line:
                lines[i] = line.replace(
                    'ampl.clair.ucsb.edu/telar-docs/docs/workflows/google-sheets/',
                    'telar.org/docs/workflows/google-sheets/'
                )
                changes.append("Updated Google Sheets docs URL to telar.org")
                break

        # Step 7b: Update Google Sheets comment format (remove Option A/Option B)
        # Old format had:
        #    - Option A: Duplicate our template at https://bit.ly/telar-template
        #    - Option B: Import docs/google_sheets_integration/telar-template.xlsx to Google Sheets yourself
        # New format just has:
        # 1. Get the template: Duplicate our template at https://bit.ly/telar-template
        for i, line in enumerate(lines):
            if '# 1. Get the template:' in line:
                # Check if next lines have Option A/Option B format
                if i + 2 < len(lines) and '#    - Option A:' in lines[i + 1]:
                    # Found old format - replace 3 lines with 1 line
                    lines[i] = '# 1. Get the template: Duplicate our template at https://bit.ly/telar-template'
                    # Delete the next 2 lines (Option A and Option B)
                    del lines[i + 1:i + 3]
                    changes.append("Updated Google Sheets comment format (removed Option A/B)")
                break

        # Step 8: Update logo comment to include recommended dimensions
        for i, line in enumerate(lines):
            if 'logo:' in line and 'Path to logo image (optional)' in line:
                if '200-300px wide recommended' not in line:
                    lines[i] = 'logo: "" # Path to logo image (optional, max 80px tall, 200-300px wide recommended)'
                    changes.append("Updated logo comment with recommended dimensions")
                break

        # Step 9: Write updated config
        self._write_file(config_path, '\n'.join(lines))

        return changes

    def _has_custom_stories(self) -> bool:
        """
        Check if user has any custom (non-demo) stories.

        Returns:
            bool: True if user has custom story CSVs beyond system/demo files
        """
        structures_dir = os.path.join(self.repo_root, 'components/structures')
        if not os.path.exists(structures_dir):
            return False

        # System files and old demo files to exclude
        system_csvs = {
            'objects.csv', 'new-objects.csv', 'project.csv',
            'objetos.csv', 'proyecto.csv',
            'story-1.csv', 'story-2.csv'  # Old v0.5.0 demos
        }

        for filename in os.listdir(structures_dir):
            if filename.endswith('.csv') and filename not in system_csvs:
                return True  # Found a custom story

        return False

    def _should_enable_demo_content(self) -> bool:
        """
        Detect if user should use new v0.6.0 demo system.

        Logic:
        - If never had v0.5.0 demos: False
        - If modified v0.5.0 demos: False (now user content)
        - If only has demos (no custom stories): False (site would break)
        - If has unmodified demos AND custom stories: True (enable new system)

        Returns:
            bool: True if include_demo_content should be set to true
        """
        # Check if v0.5.0 demo CSVs exist
        old_demo_csvs = ['story-1.csv', 'story-2.csv']
        has_old_demos = any(
            self._file_exists(f'components/structures/{csv}')
            for csv in old_demo_csvs
        )

        if not has_old_demos:
            return False  # Never had demos

        # Check if demos were modified
        for csv in old_demo_csvs:
            csv_path = f'components/structures/{csv}'
            if self._file_exists(csv_path):
                if self._is_file_modified(csv_path, compare_tag='v0.5.0-beta'):
                    return False  # User customized demos = user content now

        # Unmodified demos exist - but do they have other stories?
        if not self._has_custom_stories():
            return False  # Only has demos, can't remove them (site would break)

        # Has unmodified demos AND has other stories → enable new demo system
        return True

    def _get_referenced_files(self) -> set:
        """
        Parse user's CSV files to find which old demo files are still being used.

        This reads the CSVs synced from Google Sheets to determine the source of truth
        for what content is actively in use. Returns CSVs, markdown files, and images
        that are actively referenced.

        Returns:
            Set of relative file paths that are actively referenced
        """
        import csv
        import re

        referenced = set()

        # System CSV files to exclude from story scanning
        system_csvs = {'objects.csv', 'new-objects.csv', 'project.csv',
                       'objetos.csv', 'proyecto.csv'}  # Include Spanish names

        # 1. Check objects.csv AND new-objects.csv for local image references
        for obj_csv in ['objects.csv', 'new-objects.csv']:
            csv_path = os.path.join(self.repo_root, 'components/structures', obj_csv)
            if not os.path.exists(csv_path):
                continue

            try:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Skip comment rows
                        object_id = row.get('object_id', '')
                        if object_id.startswith('#'):
                            continue

                        source_url = row.get('source_url', '').strip()

                        # Empty source_url OR local path = local image
                        if not source_url or not source_url.startswith('http'):
                            # Try common image extensions
                            for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff']:
                                img_path = f'components/images/{object_id}{ext}'
                                if self._file_exists(img_path):
                                    referenced.add(img_path)
                                    break
            except Exception as e:
                # Don't fail migration if CSV can't be read
                print(f"  Warning: Could not read {obj_csv}: {e}")
                continue

        # 2. Check story CSVs for markdown file references
        structures_dir = os.path.join(self.repo_root, 'components/structures')
        if os.path.exists(structures_dir):
            for filename in os.listdir(structures_dir):
                if not filename.endswith('.csv'):
                    continue
                if filename in system_csvs:
                    continue

                csv_path = os.path.join(structures_dir, filename)

                # Also keep the CSV itself if it exists
                csv_rel_path = f'components/structures/{filename}'
                if self._file_exists(csv_rel_path):
                    referenced.add(csv_rel_path)

                try:
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            # Skip comment rows
                            step = str(row.get('step', '')).strip()
                            if step.startswith('#') or not step:
                                continue

                            # Check layer columns
                            for col in ['layer1_file', 'layer2_file', 'layer3_file']:
                                file_ref = row.get(col, '').strip()
                                if file_ref:
                                    # Normalize path (story1/file.md → components/texts/stories/story1/file.md)
                                    if '/' in file_ref:
                                        # Already has directory
                                        md_path = f'components/texts/stories/{file_ref}'
                                    else:
                                        # Just filename, skip
                                        continue

                                    referenced.add(md_path)
                except Exception as e:
                    print(f"  Warning: Could not read {filename}: {e}")
                    continue

        # 3. Parse referenced markdown files for embedded images
        for md_file in [f for f in referenced if f.endswith('.md')]:
            full_path = os.path.join(self.repo_root, md_file)
            if not os.path.exists(full_path):
                continue

            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Extract image paths from markdown
                # Matches: ![alt](path), <img src="path">, url(path)
                patterns = [
                    r'!\[.*?\]\(([^)]+)\)',  # Markdown images
                    r'<img[^>]+src=["\']([^"\']+)["\']',  # HTML images
                    r'url\(["\']?([^)"\' ]+)["\']?\)',  # CSS background images
                ]

                for pattern in patterns:
                    for match in re.finditer(pattern, content):
                        img_path = match.group(1)

                        # Normalize path (../components/images/foo.jpg → components/images/foo.jpg)
                        img_path = img_path.replace('../', '').lstrip('/')

                        # Only care about components/images/ references
                        if 'components/images/' in img_path:
                            referenced.add(img_path)

            except Exception as e:
                print(f"  Warning: Could not parse {md_file}: {e}")
                continue

        return referenced

    def _cleanup_old_demo_content(self) -> List[str]:
        """
        Remove old demo content that is NOT being used by user's current Google Sheet.

        Strategy:
        1. Get CSV-referenced files (source of truth from Google Sheets)
        2. For each old demo file:
           a. If CSV-referenced → KEEP (user is using it)
           b. If not referenced but modified → KEEP (user customized)
           c. If not referenced and unmodified → DELETE (safe to remove)

        Returns:
            List of change descriptions
        """
        import shutil

        changes = []

        # Get what's currently in use from CSVs (source of truth)
        referenced_files = self._get_referenced_files()

        # Complete list of old demo files to consider (v0.5.0 demo content)
        old_demo_files = {
            # story1 markdown files (6 files)
            'components/texts/stories/story1/bogota_savanna.md',
            'components/texts/stories/story1/encomendero_biography.md',
            'components/texts/stories/story1/legal_painting.md',
            'components/texts/stories/story1/legal_proceeding.md',
            'components/texts/stories/story1/maldonado_lineage.md',
            'components/texts/stories/story1/ways_of_mapping.md',

            # story2 markdown files (9 files)
            'components/texts/stories/story2/step1-layer1-test.md',
            'components/texts/stories/story2/step1-layer1.md',
            'components/texts/stories/story2/step10-layer1.md',
            'components/texts/stories/story2/step2-layer1.md',
            'components/texts/stories/story2/step3-layer1.md',
            'components/texts/stories/story2/step4-layer1.md',
            'components/texts/stories/story2/step4-layer2.md',
            'components/texts/stories/story2/step5-layer1.md',
            'components/texts/stories/story2/step8-layer1.md',

            # CSV files (3 files)
            'components/structures/story-1.csv',
            'components/structures/story-2.csv',
            'components/structures/new-objects.csv',

            # Demo images (18 files)
            'components/images/ampl-logo.png',
            'components/images/babylonian-6c-bce-world-map.png',
            'components/images/bogota-1614-painting.jpg',
            'components/images/codex-quetzalecatzin-1593.jpg',
            'components/images/greenland-inuit-1926-map.jpg',
            'components/images/guaman-poma-1615-santa-fe.jpg',
            'components/images/kogi-loom-1978.png',
            'components/images/maldonado-antonio-portrait-18c.jpeg',
            'components/images/maldonado-family-tree-1674.jpg',
            'components/images/maldonado-francisco-portrait-18c.jpg',
            'components/images/medieval-1262-1300-world-map.jpg',
            'components/images/recopilacion-leyes-1681-audiencias.jpg',
            'components/images/recopilacion-leyes-1681-encomiendas.jpg',
            'components/images/siberian-1860-1870-sealskin-map.jpg',
            'components/images/venice-1534-west-indies-map.jpg',
            'components/images/example-bogota-1614.png',
            'components/images/example-ceramic-figure.png',
            'components/images/example-muisca-goldwork.jpg',
        }

        kept_in_use = []
        kept_modified = []
        removed_count = 0

        for file_path in old_demo_files:
            if not self._file_exists(file_path):
                continue

            # Is user actively using this file?
            if file_path in referenced_files:
                kept_in_use.append(file_path)
                continue  # KEEP IT - CSV says it's in use

            # Not referenced - check if user modified text files
            if file_path.endswith(('.md', '.csv')):
                if self._is_file_modified(file_path, compare_tag='v0.5.0-beta'):
                    kept_modified.append(file_path)
                    continue  # KEEP IT - user customized

            # Not in use, not modified - safe to delete
            full_path = os.path.join(self.repo_root, file_path)
            try:
                os.remove(full_path)
                removed_count += 1
                changes.append(f"Removed v0.5.0 example file: {file_path}")
            except Exception as e:
                changes.append(f"⚠️  Warning: Could not remove {file_path}: {e}")

        # Remove directories ONLY if empty (after individual file cleanup above)
        # CRITICAL: Don't use shutil.rmtree() - it would delete kept files!
        old_dirs = [
            'components/texts/stories/story1',
            'components/texts/stories/story2',
            'components/images/paisajes',
        ]

        for rel_path in old_dirs:
            full_path = os.path.join(self.repo_root, rel_path)
            if os.path.exists(full_path):
                try:
                    # Only remove if directory is actually empty
                    if not os.listdir(full_path):
                        os.rmdir(full_path)
                        changes.append(f"Removed empty directory: {rel_path}/")
                    # If not empty, it contains files we decided to keep - leave it alone
                except:
                    pass  # Can't remove or permission issue

        # Report what was kept and why (bilingual)
        lang = self._detect_language()

        if kept_in_use:
            if lang == 'es':
                msg = f"ℹ️  Se mantuvieron {len(kept_in_use)} archivos de ejemplo v0.5.0 (aún referenciados en Google Sheet)"
            else:
                msg = f"ℹ️  Kept {len(kept_in_use)} v0.5.0 example files (still referenced in Google Sheet)"
            changes.append(msg)

            for f in kept_in_use[:5]:  # Show first 5
                changes.append(f"  • {f}")
            if len(kept_in_use) > 5:
                changes.append(f"  ... and {len(kept_in_use) - 5} more")

        if kept_modified:
            if lang == 'es':
                msg = f"⚠️  Se mantuvieron {len(kept_modified)} archivos de ejemplo v0.5.0 (los modificaste)"
            else:
                msg = f"⚠️  Kept {len(kept_modified)} v0.5.0 example files (you modified them)"
            changes.append(msg)

            for f in kept_modified:
                changes.append(f"  • {f}")

        if removed_count > 0:
            if lang == 'es':
                msg = f"✓ Eliminados {removed_count} archivos de ejemplo v0.5.0 (no en uso)"
            else:
                msg = f"✓ Removed {removed_count} v0.5.0 example files (not in use)"
            changes.append(msg)

            # Add reassurance that custom content is safe
            if lang == 'es':
                changes.append("ℹ️  Tu contenido personalizado está preservado")
            else:
                changes.append("ℹ️  Your custom content is preserved")

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
            # Python scripts
            'scripts/csv_to_json.py': 'Demo content processing, bilingual CSV support, story_id',
            'scripts/fetch_demo_content.py': 'Demo content bundle fetcher (NEW)',
            'scripts/generate_collections.py': 'Custom pages support, demo glossary',
            'scripts/fetch_google_sheets.py': 'Bilingual tab support, story_id support',
            'scripts/discover_sheet_gids.py': 'Story_id support',
            'scripts/generate_iiif.py': 'Version header update',

            # Language files - multilingual UI
            '_data/languages/en.yml': 'Credit prefix, updated strings',
            '_data/languages/es.yml': 'Spanish translations, credit prefix',

            # Data files
            '_data/navigation.yml': 'Bilingual navigation menu configuration (NEW)',

            # Layouts
            '_layouts/story.html': 'Credit prefix exposure, byline markdown support',
            '_layouts/default.html': 'Multilingual support',
            '_layouts/user-page.html': 'Custom pages layout (NEW)',
            '_layouts/objects-index.html': 'Object ordering bug fix',
            '_layouts/index.html': 'Logo display removed',
            '_layouts/glossary.html': 'Demo badge text fix',

            # Includes
            '_includes/header.html': 'Data-driven navigation, logo CSS',
            '_includes/viewer.html': 'Object credits badge HTML/CSS',

            # Stylesheets
            'assets/css/telar.scss': 'Logo, panel freeze, tab widget, glossary, credits badge',

            # JavaScript
            'assets/js/story.js': 'Panel freeze system, credits badge, viewer scroll isolation',
            'assets/js/telar.js': 'Glossary link handling, click-outside-to-close',

            # Documentation
            'README.md': 'v0.6.0 documentation',
            'CHANGELOG.md': 'v0.6.0 changelog',

            # Gitignore
            '.gitignore': 'Generated files gitignored',

            # Note: components/texts/pages/about.md is handled by _move_about_page()
            # Note: .github/workflows/*.yml files CANNOT be auto-updated (security restriction)
            #       They are included in manual steps instead
        }

        # Template files - only add for new sites (no custom stories)
        if not self._has_custom_stories():
            template_files = {
                # Glossary entries - English
                'components/texts/glossary/story.md': 'Story glossary entry',
                'components/texts/glossary/step.md': 'Step glossary entry',
                'components/texts/glossary/viewer.md': 'Viewer glossary entry',
                'components/texts/glossary/panel.md': 'Panel glossary entry',

                # Glossary entries - Spanish
                'components/texts/glossary/historia.md': 'Historia glossary entry',
                'components/texts/glossary/paso.md': 'Paso glossary entry',
                'components/texts/glossary/visor.md': 'Visor glossary entry',
                'components/texts/glossary/panel-es.md': 'Panel-es glossary entry',

                # Template tutorial stories - English
                'components/texts/stories/your-story/about-coordinates.md': 'Coordinate system explanation',
                'components/texts/stories/your-story/guiding-attention.md': 'Question/Answer/Invitation pattern',
                'components/texts/stories/your-story/building-argument.md': 'Coordinate sequences as argument',
                'components/texts/stories/your-story/visual-rhetoric.md': 'Visual contrast analysis',
                'components/texts/stories/your-story/the-reveal.md': 'Full view synthesis',
                'components/texts/stories/your-story/progressive-disclosure.md': 'Layer 2 panel explanation',
                'components/texts/stories/your-story/ruler-place.md': 'Charles III marginalized position',
                'components/texts/stories/your-story/multiple-images.md': 'IIIF vs self-hosted comparison',
                'components/texts/stories/your-story/whats-next.md': 'Template overview',

                # Template tutorial stories - Spanish
                'components/texts/stories/tu-historia/acerca-de-coordenadas.md': 'Sistema de coordenadas',
                'components/texts/stories/tu-historia/guiar-atencion.md': 'Patrón Pregunta/Respuesta/Invitación',
                'components/texts/stories/tu-historia/construir-argumento.md': 'Secuencias como argumento',
                'components/texts/stories/tu-historia/retorica-visual.md': 'Análisis de contraste visual',
                'components/texts/stories/tu-historia/la-revelacion.md': 'Síntesis de vista completa',
                'components/texts/stories/tu-historia/divulgacion-progresiva.md': 'Explicación de panel capa 2',
                'components/texts/stories/tu-historia/lugar-gobernante.md': 'Posición marginalizada',
                'components/texts/stories/tu-historia/multiples-imagenes.md': 'Comparación IIIF vs autoalojadas',
                'components/texts/stories/tu-historia/que-sigue.md': 'Resumen de plantilla',

                # Template tutorial image (used in your-story/tu-historia)
                'components/images/leviathan.jpg': 'Hobbes Leviathan frontispiece (self-hosted demo)',
            }
            framework_files.update(template_files)

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
        """English manual steps for v0.6.0 migration."""
        return [
            {
                'description': '''**If you use GitHub Pages:**

No further actions needed. GitHub Actions will automatically rebuild your site with the upgraded framework.''',
            },
            {
                'description': '''**If you work with your site locally:**

1. Regenerate data files: `python3 scripts/csv_to_json.py && python3 scripts/generate_collections.py`
2. Test your site build: `bundle exec jekyll build`''',
            },
            {
                'description': '''**Optional (all users):**

Enable demo content by setting `include_demo_content: true` in `_config.yml` under `story_interface`. Demo content will be automatically fetched during the build process.''',
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        """Spanish manual steps for v0.6.0 migration."""
        return [
            {
                'description': '''**Si usas GitHub Pages:**

No se requieren más acciones. GitHub Actions reconstruirá automáticamente tu sitio con el framework actualizado.''',
            },
            {
                'description': '''**Si trabajas con tu sitio localmente:**

1. Regenera los archivos de datos: `python3 scripts/csv_to_json.py && python3 scripts/generate_collections.py`
2. Prueba la compilación de tu sitio: `bundle exec jekyll build`''',
            },
            {
                'description': '''**Opcional (todos los usuarios):**

Habilita el contenido demo configurando `include_demo_content: true` en `_config.yml` bajo `story_interface`. El contenido demo se descargará automáticamente durante el proceso de compilación.''',
            },
        ]
