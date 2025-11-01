"""
Migration from v0.2.0-beta to v0.3.0-beta.

Major changes:
- Restructure project.csv from key-value pairs to columns
- Move project metadata to _config.yml
- Add theme configuration
- Update CSV column orders
"""

from typing import List, Dict
import csv
import io
import yaml
from .base import BaseMigration


class Migration020to030(BaseMigration):
    """Migration from v0.2.0 to v0.3.0 - major restructuring."""

    from_version = "0.2.0-beta"
    to_version = "0.3.0-beta"
    description = "Restructure project.csv and move metadata to _config.yml"

    def check_applicable(self) -> bool:
        """Check if project.csv exists and has old format."""
        content = self._read_file('components/structures/project.csv')
        if not content:
            return False

        # Check if it has old key-value format
        return 'key,value' in content or 'project_title' in content

    def apply(self) -> List[str]:
        """Apply major restructuring from v0.2.0 to v0.3.0."""
        changes = []

        # 1. Delete old compiled CSS (replaced by SCSS in v0.3.0)
        import os
        old_css_path = os.path.join(self.repo_root, 'assets/css/telar.css')
        if os.path.exists(old_css_path):
            os.remove(old_css_path)
            changes.append("Removed old assets/css/telar.css (now using SCSS)")

        # 2. Parse old project.csv
        old_project = self._read_file('components/structures/project.csv')
        if not old_project:
            return changes

        stories = self._parse_stories_from_csv(old_project)

        # 3. Write new project.csv (only stories, metadata was never used)
        if stories:
            self._write_new_project_csv(stories)
            changes.append("Restructured components/structures/project.csv to new column format")

        # 4. Add new config fields to _config.yml (without touching existing values)
        if self._add_new_config_fields():
            changes.append("Added new configuration fields to _config.yml")

        # 5. Add Google Sheets config to _config.yml if not present
        if self._add_google_sheets_config():
            changes.append("Added Google Sheets configuration section to _config.yml")

        # 6. Add theme files (introduced in v0.3.0)
        themes_added = self._add_theme_files()
        if themes_added:
            changes.append(f"Added theme system with {themes_added} theme files")

        # 7. Update Python scripts (includes validation logic introduced in v0.3.0)
        scripts_updated = self._update_python_scripts()
        for script_name in scripts_updated:
            changes.append(f"Updated {script_name}")

        return changes

    def _parse_stories_from_csv(self, content: str) -> List[Dict]:
        """
        Parse stories from old key-value format project.csv.

        NOTE: Metadata in old project.csv was never actually used by templates,
        so we only extract the stories list.

        Returns:
            stories_list
        """
        stories = []
        reader = csv.reader(io.StringIO(content))
        in_stories_section = False

        for row in reader:
            if not row or len(row) < 2:
                continue

            key = row[0].strip()
            value = row[1].strip() if len(row) > 1 else ""

            # Check for STORIES section
            if key == 'STORIES':
                in_stories_section = True
                continue

            if in_stories_section:
                # Story entries: order, title
                if key.isdigit():
                    stories.append({
                        'order': key,
                        'title': value,
                        'subtitle': ''
                    })

        return stories

    def _add_new_config_fields(self) -> bool:
        """
        Add new config fields introduced in v0.3.0 using text-based insertion
        to preserve comments and formatting.

        New fields:
        - telar_theme: Theme selection (if not present)
        - logo: Logo path at root level (if not present)

        Also cleans up telar section to only have version and release_date.
        """
        config_path = '_config.yml'
        content = self._read_file(config_path)

        if not content:
            return False

        # Check if fields already exist (use yaml for checking only)
        try:
            config = yaml.safe_load(content)
        except yaml.YAMLError:
            return False

        modified = False
        lines = content.split('\n')

        # Add telar_theme and logo after email field if not present
        if 'telar_theme' not in config or 'logo' not in config:
            # Find the line with "email:"
            for i, line in enumerate(lines):
                if line.startswith('email:'):
                    insert_lines = []

                    if 'telar_theme' not in config:
                        insert_lines.append('telar_theme: "paisajes" # Options: paisajes, neogranadina, santa-barbara, austin, or custom')
                        modified = True

                    if 'logo' not in config:
                        insert_lines.append('logo: "" # Path to logo image (optional)')
                        modified = True

                    if insert_lines:
                        # Insert after email line
                        lines = lines[:i+1] + insert_lines + lines[i+1:]
                    break

        # Clean up telar section - remove redundant fields that were never used
        # Keep only version and release_date
        if 'telar' in config:
            in_telar_section = False
            new_lines = []

            for line in lines:
                stripped = line.strip()

                # Detect telar section start
                if line.strip() == '# Telar Settings':
                    in_telar_section = False  # Will be set to True on next line
                    new_lines.append(line)
                    continue

                if line.startswith('telar:'):
                    in_telar_section = True
                    new_lines.append(line)
                    continue

                # Inside telar section
                if in_telar_section:
                    # Exit telar section when we hit a line that's not indented or is a new section
                    if line and not line.startswith('  ') and not line.startswith('\t'):
                        in_telar_section = False
                        new_lines.append(line)
                        continue

                    # Keep version and release_date lines
                    if stripped.startswith('version:') or stripped.startswith('release_date:'):
                        new_lines.append(line)
                    # Skip redundant fields (anything else in telar section)
                    elif line.startswith('  ') or line.startswith('\t'):
                        if stripped.startswith(('project_title:', 'tagline:', 'primary_color:', 'secondary_color:',
                                              'font_headings:', 'font_body:', 'logo:')):
                            modified = True
                            # Skip this line - don't add to new_lines
                        else:
                            # Some other field we don't know about - keep it
                            new_lines.append(line)
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)

            lines = new_lines

        if modified:
            self._write_file(config_path, '\n'.join(lines))
            return True

        return False

    def _write_new_project_csv(self, stories: List[Dict]) -> None:
        """Write new format project.csv with just story data."""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=['order', 'title', 'subtitle'])
        writer.writeheader()

        for story in stories:
            writer.writerow(story)

        self._write_file('components/structures/project.csv', output.getvalue())

    def _add_google_sheets_config(self) -> bool:
        """Add Google Sheets configuration section with comments if not present."""
        config_path = '_config.yml'
        content = self._read_file(config_path)

        if not content:
            return False

        # Check if google_sheets config already exists
        if 'google_sheets:' in content:
            return False

        # Google Sheets config block with full documentation
        google_sheets_block = '''
# Google Sheets Integration (optional)
# Manage content via Google Sheets instead of editing CSV files directly.
# See docs/google_sheets_integration/README.md for detailed setup instructions.
#
# Setup:
# 1. Get the template:
#    - Option A: Duplicate our template at https://bit.ly/telar-template
#    - Option B: Import docs/google_sheets_integration/telar-template.xlsx to Google Sheets yourself
# 2. Share your sheet: Anyone with the link (Viewer access)
# 3. Publish your sheet: File > Share > Publish to web
# 4. Paste both URLs below
# 5. Set enabled: true
# 6. Commit changes
#    - If using GitHub Pages: GitHub Actions will automatically discover tab GIDs and fetch CSVs
#    - If running locally: Run `python3 scripts/fetch_google_sheets.py` before building
google_sheets:
  enabled: false
  shared_url: ""
  published_url: ""
'''

        lines = content.split('\n')

        # Find insertion point after logo field
        for i, line in enumerate(lines):
            if line.startswith('logo:'):
                # Insert blank line then google_sheets block after logo
                lines = lines[:i+1] + [''] + google_sheets_block.strip().split('\n') + lines[i+1:]
                self._write_file(config_path, '\n'.join(lines))
                return True

        return False

    def _add_theme_files(self) -> int:
        """
        Add theme files from GitHub.

        Returns the number of theme files added.
        """
        import os

        # Create themes directory if it doesn't exist
        themes_dir = os.path.join(self.repo_root, '_data/themes')
        if not os.path.exists(themes_dir):
            os.makedirs(themes_dir)

        theme_files = ['paisajes.yml', 'neogranadina.yml', 'santa-barbara.yml', 'austin.yml']
        added_count = 0

        for theme_file in theme_files:
            # Check if theme file already exists
            theme_path = f'_data/themes/{theme_file}'
            if self._file_exists(theme_path):
                continue

            # Fetch from GitHub
            content = self._fetch_from_github(theme_path)
            if content:
                self._write_file(theme_path, content)
                added_count += 1

        return added_count

    def _update_python_scripts(self) -> List[str]:
        """
        Update Python scripts from GitHub to get validation logic introduced in v0.3.0.

        This includes:
        - csv_to_json.py: Added IIIF validation, thumbnail validation, object reference validation
        - generate_collections.py: Updated to work with new validation system
        - discover_sheet_gids.py: New script for Google Sheets integration
        - fetch_google_sheets.py: New script for Google Sheets integration

        Returns list of script names that were updated.
        """
        import os

        # Create scripts directory if it doesn't exist
        scripts_dir = os.path.join(self.repo_root, 'scripts')
        if not os.path.exists(scripts_dir):
            os.makedirs(scripts_dir)

        # Define scripts to update
        scripts = {
            'scripts/csv_to_json.py': 'csv_to_json.py with validation logic',
            'scripts/generate_collections.py': 'generate_collections.py',
            'scripts/discover_sheet_gids.py': 'discover_sheet_gids.py (Google Sheets)',
            'scripts/fetch_google_sheets.py': 'fetch_google_sheets.py (Google Sheets)',
        }

        updated_scripts = []

        for script_path, description in scripts.items():
            # Fetch from GitHub (will overwrite existing files to get latest validation logic)
            content = self._fetch_from_github(script_path)
            if content:
                self._write_file(script_path, content)
                updated_scripts.append(description)

        return updated_scripts

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """No manual steps required for this migration."""
        return []
