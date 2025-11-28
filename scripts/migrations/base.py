"""
Base migration class for Telar upgrades.

All version-specific migrations should inherit from BaseMigration.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import os


class BaseMigration(ABC):
    """Base class for all Telar version migrations."""

    # Override these in subclasses
    from_version: str = ""
    to_version: str = ""
    description: str = ""

    def __init__(self, repo_root: str):
        """
        Initialize migration with repository root path.

        Args:
            repo_root: Absolute path to the Telar repository root
        """
        self.repo_root = repo_root
        self.changes_made = []

    @abstractmethod
    def check_applicable(self) -> bool:
        """
        Check if this migration should run.

        Returns:
            True if migration is applicable, False otherwise
        """
        pass

    @abstractmethod
    def apply(self) -> List[str]:
        """
        Execute the migration.

        Returns:
            List of human-readable descriptions of changes made
        """
        pass

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """
        Get list of manual steps user must complete.

        Returns:
            List of dicts with keys: 'description', 'doc_url' (optional)
        """
        return []

    def _file_exists(self, rel_path: str) -> bool:
        """Check if file exists relative to repo root."""
        return os.path.exists(os.path.join(self.repo_root, rel_path))

    def _read_file(self, rel_path: str) -> Optional[str]:
        """Read file contents relative to repo root."""
        full_path = os.path.join(self.repo_root, rel_path)
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return None

    def _write_file(self, rel_path: str, content: str) -> None:
        """Write file contents relative to repo root."""
        full_path = os.path.join(self.repo_root, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

    def _move_file(self, src_rel_path: str, dest_rel_path: str) -> bool:
        """
        Move file from src to dest (relative to repo root).

        Returns:
            True if file was moved, False if src didn't exist
        """
        src_full = os.path.join(self.repo_root, src_rel_path)
        dest_full = os.path.join(self.repo_root, dest_rel_path)

        if not os.path.exists(src_full):
            return False

        os.makedirs(os.path.dirname(dest_full), exist_ok=True)
        os.rename(src_full, dest_full)
        return True

    def _ensure_index_upgrade_notice(self) -> bool:
        """
        Ensure upgrade notice exists at top of index.md.

        If index.md doesn't exist, does nothing (will be created by earlier migration).
        If upgrade notice already exists, does nothing (Liquid template updates version).
        If notice is missing (user removed or customized), prepends it.

        Returns:
            True if notice was added, False if already present or file doesn't exist
        """
        index_path = 'index.md'
        content = self._read_file(index_path)

        if not content:
            return False

        # Check if upgrade notice already exists
        if 'upgrade-alert.html' in content or 'Successfully upgraded to Telar v.' in content:
            # Notice already present, Liquid will handle version updates
            return False

        # Notice missing, prepend it
        upgrade_notice = """{% include upgrade-alert.html %}

"""

        # Find where to insert (after front matter)
        lines = content.split('\n')

        # Find end of front matter
        in_front_matter = False
        front_matter_end = 0

        for i, line in enumerate(lines):
            if i == 0 and line.strip() == '---':
                in_front_matter = True
                continue
            if in_front_matter and line.strip() == '---':
                front_matter_end = i + 1
                break

        # Insert notice after front matter
        new_content = '\n'.join(lines[:front_matter_end]) + '\n\n' + upgrade_notice + '\n'.join(lines[front_matter_end:])
        self._write_file(index_path, new_content)

        return True

    def _ensure_gitignore_entries(self, entries: List[str], section_comment: str = None) -> bool:
        """
        Ensure entries exist in .gitignore file.

        Args:
            entries: List of gitignore patterns to add (e.g., ["__pycache__/", "*.py[cod]"])
            section_comment: Optional comment line to add before entries (e.g., "# Python")

        Returns:
            True if any entries were added, False if all already present or .gitignore doesn't exist
        """
        gitignore_path = '.gitignore'
        content = self._read_file(gitignore_path)

        if not content:
            return False

        lines = content.split('\n')
        added_any = False
        entries_to_add = []

        # Check which entries are missing
        for entry in entries:
            # Check if entry already exists (exact match or as part of a line)
            if not any(entry in line for line in lines):
                entries_to_add.append(entry)

        if not entries_to_add:
            return False

        # Find if section comment already exists
        section_exists = False
        insert_index = len(lines)

        if section_comment:
            for i, line in enumerate(lines):
                if line.strip() == section_comment:
                    section_exists = True
                    insert_index = i + 1
                    break

        # Add section comment if needed
        if not section_exists and section_comment:
            # Add section at the end with blank line before if file isn't empty
            if lines and lines[-1].strip():
                lines.append('')
            lines.append(section_comment)
            insert_index = len(lines)

        # Add missing entries
        for entry in entries_to_add:
            lines.insert(insert_index, entry)
            insert_index += 1
            added_any = True

        if added_any:
            # Ensure file ends with newline
            new_content = '\n'.join(lines)
            if not new_content.endswith('\n'):
                new_content += '\n'
            self._write_file(gitignore_path, new_content)

        return added_any

    def _update_config_version(self, new_version: str, new_date: str) -> bool:
        """
        Update telar.version and telar.release_date in _config.yml.

        Uses text-based editing to preserve formatting and comments.

        Args:
            new_version: New version string (e.g., "0.3.4-beta")
            new_date: New release date (e.g., "2025-10-29")

        Returns:
            True if config was updated, False if file doesn't exist or telar section not found
        """
        config_path = '_config.yml'
        content = self._read_file(config_path)

        if not content:
            return False

        lines = content.split('\n')
        modified = False
        in_telar_section = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Detect telar section start
            if line.startswith('telar:'):
                in_telar_section = True
                continue

            # Inside telar section
            if in_telar_section:
                # Exit when we hit a non-indented line that's not blank
                if line and not line.startswith('  ') and not line.startswith('\t') and stripped:
                    in_telar_section = False
                    continue

                # Update version line
                if stripped.startswith('version:'):
                    # Preserve indentation
                    indent = line[:len(line) - len(line.lstrip())]
                    lines[i] = f'{indent}version: "{new_version}"'
                    modified = True

                # Update release_date line
                if stripped.startswith('release_date:'):
                    # Preserve indentation
                    indent = line[:len(line) - len(line.lstrip())]
                    lines[i] = f'{indent}release_date: "{new_date}"'
                    modified = True

        if modified:
            self._write_file(config_path, '\n'.join(lines))
            return True

        return False

    def _fetch_from_github(self, path: str, branch: str = 'main') -> Optional[str]:
        """
        Fetch file content from GitHub telar repository.

        Args:
            path: Path to file relative to repo root (e.g., "_layouts/story.html")
            branch: Branch to fetch from (default: 'main')

        Returns:
            File content as string, or None if fetch fails
        """
        import urllib.request
        import urllib.error

        url = f"https://raw.githubusercontent.com/UCSB-AMPLab/telar/{branch}/{path}"

        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                return response.read().decode('utf-8')
        except urllib.error.URLError as e:
            print(f"  ⚠️  Warning: Could not fetch {path} from GitHub: {e}")
            return None
        except Exception as e:
            print(f"  ⚠️  Warning: Error fetching {path}: {e}")
            return None

    def _detect_language(self) -> str:
        """
        Detect site language from _config.yml.

        Reads telar.telar_language setting (added in v0.6.0).
        Useful for providing bilingual migration messages and summaries.

        Returns:
            'es' for Spanish, 'en' for English (default)
        """
        config_path = os.path.join(self.repo_root, '_config.yml')

        try:
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # Get telar_language setting (added in v0.6.0)
            lang = config.get('telar', {}).get('telar_language', 'en')

            # Normalize to 'en' or 'es'
            return 'es' if lang.lower().startswith('es') else 'en'

        except Exception:
            # Safe default if config can't be read
            return 'en'

    def _is_file_modified(self, rel_path: str, compare_tag: str = 'v0.5.0-beta') -> bool:
        """
        Check if user modified a file compared to original version.

        Compares user's current file with original from GitHub tag.
        Useful for safely cleaning up demo content without losing user customizations.

        Args:
            rel_path: Path relative to repo root (e.g., 'components/texts/stories/story1/file.md')
            compare_tag: Git tag to compare against (default: 'v0.5.0-beta')

        Returns:
            True if file was modified by user, False if identical to original

        Example:
            >>> self._is_file_modified('components/texts/stories/story1/intro.md')
            True  # User customized the demo story
        """
        # Fetch original from GitHub
        original_content = self._fetch_from_github(rel_path, branch=compare_tag)

        if not original_content:
            # Can't fetch original, assume modified (safe default)
            return True

        # Read user's current file
        current_content = self._read_file(rel_path)

        if not current_content:
            # File doesn't exist, not modified
            return False

        # Normalize whitespace for comparison
        # Split into lines and strip each line to ignore formatting differences
        original_lines = [line.strip() for line in original_content.split('\n')]
        current_lines = [line.strip() for line in current_content.split('\n')]

        # Compare normalized content
        return original_lines != current_lines

    def __str__(self) -> str:
        return f"Migration {self.from_version} → {self.to_version}: {self.description}"
