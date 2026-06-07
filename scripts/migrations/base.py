"""
Base Migration Machinery for Telar Upgrades

This module deals with the shared scaffolding every version-specific
migration builds on — `BaseMigration`, the structured result types it
returns, and the helpers that touch a user's site safely. Each migration
in this package subclasses `BaseMigration`, sets its `from_version` /
`to_version` / `_TARGET_TAG`, and implements `check_applicable()` and
`apply()`; everything else here exists so that those subclasses stay
small and so that a half-finished upgrade never corrupts a live site.

`ChangeStatus` and `ChangeRecord` are the vocabulary a migration uses to
report what happened. A migration returns a list of `ChangeRecord`s, each
carrying a human-readable description, an APPLIED/FAILED/SKIPPED status,
and a `severity` — `hard` means a FAILED record must abort the whole
upgrade (no version stamp, non-zero exit), `soft` means surface it for
attention but keep going. Replacing the old flat list-of-strings lets the
upgrade pipeline tell success from failure instead of rendering every
line as a completed checklist item.

`apply_config_version()` is the single source of truth for rewriting the
`telar.version` / `telar.release_date` stamp in `_config.yml`. It edits
text rather than round-tripping YAML so comments and formatting survive,
and both `BaseMigration` (per migration) and `upgrade.py` (the final
stamp) call it so the parsing rules cannot drift between two copies.

`BaseMigration` itself groups its helpers by concern. File primitives
(`_read_file`, `_write_file`, `_move_file`, `_file_exists`) work relative
to the repo root. Content helpers handle the recurring jobs of an upgrade
— ensuring the upgrade notice in `index.md`, topping up `.gitignore`,
stamping the config version. The staged-atomic block
(`_apply_framework_files` and its `_fetch_all_staged` / `_backup_existing`
/ `_commit_staged` / state-file companions) is the heart of the safety
model: framework files are fetched into memory first and written only if
every fetch succeeds, with backups and an `UPGRADE_STATE.json` marker so a
crash or write error mid-commit rolls back to the prior state. Fetches are
pinned to a release tag (`_TARGET_TAG`) so a re-run after a failure
re-fetches byte-identical content rather than blending across `main`
commits. `_detect_language()` reads the site's configured language for
bilingual summaries, and `_is_file_modified()` compares a file against its
original on a tag so demo cleanup can preserve user customisations.

The single `UPGRADE_STATE.json` file plays two roles — written
`in_progress` during an atomic framework write and removed on success (so
a crash mid-write is detectable), and written `failed` by `upgrade.py`
when an upgrade aborts on a HARD failure (so a re-run can tell the user
they are resuming). A clean success leaves no such file behind.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import json
import os
import re
import shutil
import time


class ChangeStatus(str, Enum):
    """Outcome of a single change a migration attempted."""

    APPLIED = "applied"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ChangeRecord:
    """A structured record of one change a migration attempted.

    Replaces the old flat list-of-strings return value so the upgrade
    pipeline can tell success from failure instead of rendering every
    string as a completed checklist item.

    Attributes:
        description: Human-readable description of the change.
        status: APPLIED, FAILED, or SKIPPED.
        severity: 'hard' if a FAILED status must abort the upgrade
            (no version stamp, non-zero exit), 'soft' if it should be
            surfaced for manual attention but not block the upgrade.
    """

    description: str
    status: ChangeStatus = ChangeStatus.APPLIED
    severity: str = "soft"


# Shared name for the in-progress / failed state marker (see the module
# docstring for the two roles it plays). Lives at the repo root.
UPGRADE_STATE_FILE = "UPGRADE_STATE.json"


def apply_config_version(content, new_version, new_date):
    """Rewrite telar.version / telar.release_date in _config.yml *content*,
    preserving comments and formatting (text edit, not a YAML round-trip).

    Single source of truth for the version stamp — both BaseMigration (per
    migration) and upgrade.py (the final stamp in main()) call this, so the
    parsing rules can no longer drift between two copies.

    Improvements over the old per-copy logic:
      - Indent-agnostic: any indented line is treated as inside the `telar:`
        section; the section ends only at the next non-blank column-0 line. The
        old `startswith('  ')` check wrongly exited on a single-space indent.
      - Inserts a release_date line right after version if the section has a
        version but no release_date.

    Args:
        content: Full text of _config.yml.
        new_version: New version string (e.g. "1.5.0").
        new_date: New release date (e.g. "2026-06-03").

    Returns:
        (new_content, modified): the rewritten text and whether anything changed.
    """
    lines = content.split('\n')
    modified = False
    in_telar_section = False
    version_idx = None
    release_date_seen = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        if not in_telar_section:
            if line.startswith('telar:'):
                in_telar_section = True
            continue

        # Inside the telar section. `telar:` is a top-level key, so the section
        # ends at the next non-blank line back at column 0 (any indentation —
        # one space, two, or a tab — keeps us inside).
        indent_len = len(line) - len(line.lstrip())
        if stripped and indent_len == 0:
            in_telar_section = False
            continue

        if stripped.startswith('version:'):
            lines[i] = f'{line[:indent_len]}version: "{new_version}"'
            version_idx = i
            modified = True
        elif stripped.startswith('release_date:'):
            lines[i] = f'{line[:indent_len]}release_date: "{new_date}"'
            release_date_seen = True
            modified = True

    # Insert a release_date line adjacent to version if the section lacked one.
    if version_idx is not None and not release_date_seen:
        vline = lines[version_idx]
        indent = vline[:len(vline) - len(vline.lstrip())]
        lines.insert(version_idx + 1, f'{indent}release_date: "{new_date}"')
        modified = True

    return '\n'.join(lines), modified


class BaseMigration(ABC):
    """Base class for all Telar version migrations."""

    # Override these in subclasses
    from_version: str = ""
    to_version: str = ""
    description: str = ""

    # Release tag to pin framework-file fetches to (e.g. "v1.4.0"). When set,
    # the staged-atomic helpers fetch from this immutable tag instead of the
    # moving `main` branch, so an upgrade from version X to version Y always
    # receives version-Y files. Left None for pre-tagging-era betas, which
    # fall back to `main` with a documented historical caveat.
    _TARGET_TAG: Optional[str] = None

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
    def apply(self) -> List:
        """
        Execute the migration.

        Returns:
            A list of ChangeRecord objects describing each change attempted.

            Legacy migrations that have not yet been converted may still return
            a list of plain strings; run_migrations() coerces each such string
            to ChangeRecord(status=APPLIED, severity="soft") so the chain keeps
            working during the incremental conversion.
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

        # Refuse to clobber an existing destination. os.rename silently
        # overwrites on POSIX; making this explicit keeps "move" from becoming
        # a surprise "replace" across platforms.
        if os.path.exists(dest_full):
            raise FileExistsError(
                f"_move_file: destination already exists: {dest_rel_path}")

        os.makedirs(os.path.dirname(dest_full), exist_ok=True)
        shutil.move(src_full, dest_full)
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

        # Strip a leading UTF-8 BOM so it does not break frontmatter detection
        # (the BOM would otherwise sit before the opening '---').
        if content.startswith('﻿'):
            content = content[1:]

        # Check if upgrade notice already exists
        if 'upgrade-alert.html' in content or 'Successfully upgraded to Telar v.' in content:
            # Notice already present, Liquid will handle version updates
            return False

        # Notice missing, prepend it
        upgrade_notice = """{% include upgrade-alert.html %}

"""

        # Find where to insert (after front matter)
        lines = content.split('\n')

        # The first line must be a frontmatter opener ('---', optional trailing
        # whitespace). If it is not, the file is not in the shape we expect, so
        # skip rather than blindly prepending the notice into the body.
        if not lines or not re.match(r'^-{3}\s*$', lines[0]):
            print("  [WARN] index.md has no leading frontmatter delimiter — "
                  "skipping upgrade-notice insertion")
            return False

        # Find end of front matter (the closing '---')
        front_matter_end = 0
        for i in range(1, len(lines)):
            if re.match(r'^-{3}\s*$', lines[i]):
                front_matter_end = i + 1
                break

        if front_matter_end == 0:
            print("  [WARN] index.md frontmatter is not closed — "
                  "skipping upgrade-notice insertion")
            return False

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

        new_content, modified = apply_config_version(content, new_version, new_date)
        if modified:
            self._write_file(config_path, new_content)
        return modified

    def _fetch_from_github(self, path: str, branch: Optional[str] = None, timeout: int = 10) -> Optional[str]:
        """
        Fetch file content from GitHub telar repository.

        Args:
            path: Path to file relative to repo root (e.g., "_layouts/story.html")
            branch: Branch or tag to fetch from. When None (the default), the
                fetch is pinned to this migration's _TARGET_TAG so an install
                always pulls the migration's target-version files; if _TARGET_TAG
                is also None it falls back to 'main'. Pass an explicit ref to
                override (e.g. a comparison fetch against the FROM-version tag).
                raw.githubusercontent.com resolves tags and branches identically.
            timeout: Socket timeout in seconds (default: 10). The staging helpers
                raise this for large vendored assets that can exceed 10 s.

        Returns:
            File content as string, or None if fetch fails
        """
        import urllib.request
        import urllib.error

        # Resolve the ref: an explicit branch/tag wins; otherwise pin to this
        # migration's release tag; only fall back to the moving 'main' branch
        # when no tag is set (pre-tagging-era betas, documented historical gap).
        ref = branch if branch is not None else (self._TARGET_TAG or 'main')

        url = f"https://raw.githubusercontent.com/UCSB-AMPLab/telar/{ref}/{path}"

        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.read().decode('utf-8')
        except urllib.error.URLError as e:
            print(f"  ⚠️  Warning: Could not fetch {path} from GitHub: {e}")
            return None
        except Exception as e:
            print(f"  ⚠️  Warning: Error fetching {path}: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Staged-atomic framework-file installation
    #
    # Fetching and writing are split into two phases so that a mid-fetch
    # failure leaves the site completely unchanged instead of half-overwritten:
    #   Phase A (_fetch_all_staged): fetch every file into memory. If any
    #       required fetch fails, nothing is written.
    #   Phase B (_commit_staged, guarded by backup/restore + a state file):
    #       only runs when Phase A fully succeeded.
    # _apply_framework_files ties both phases together and is what migrations
    # call. Fetches are pinned to a release tag so a re-run after a failure
    # re-fetches byte-identical content (no blending across `main` commits).
    # ------------------------------------------------------------------ #

    # One retry per file with a short backoff before declaring a HARD failure.
    _FETCH_RETRIES = 1
    # Larger timeout for staged fetches — vendored assets (e.g. OpenSeadragon)
    # can exceed the default 10 s and a timeout here is a HARD failure.
    _STAGED_FETCH_TIMEOUT = 30

    def _fetch_with_retry(self, path: str, branch: str) -> Optional[str]:
        """Fetch one file, retrying once with backoff before giving up."""
        content = self._fetch_from_github(path, branch=branch, timeout=self._STAGED_FETCH_TIMEOUT)
        attempt = 0
        while content is None and attempt < self._FETCH_RETRIES:
            attempt += 1
            time.sleep(min(2 ** attempt, 5))
            content = self._fetch_from_github(path, branch=branch, timeout=self._STAGED_FETCH_TIMEOUT)
        return content

    def _fetch_all_staged(
        self, file_map: Dict[str, str], tag: Optional[str] = None
    ) -> Tuple[Dict[str, Tuple[str, str]], List[ChangeRecord]]:
        """Phase A: fetch every file in file_map into memory without writing.

        Args:
            file_map: {rel_path: description} of framework files to fetch.
            tag: Release tag to pin to. Falls back to 'main' when None.

        Returns:
            (content_map, failed_records) where content_map maps
            rel_path -> (content, description) for every successful fetch, and
            failed_records is a list of HARD ChangeRecords for every fetch that
            failed. When failed_records is non-empty the caller must write
            nothing (fail closed).
        """
        branch = tag if tag else 'main'
        content_map: Dict[str, Tuple[str, str]] = {}
        failed: List[ChangeRecord] = []

        for rel_path, description in file_map.items():
            content = self._fetch_with_retry(rel_path, branch)
            if content is not None:
                content_map[rel_path] = (content, description)
            else:
                failed.append(ChangeRecord(
                    description=(
                        f"Could not fetch {rel_path} from GitHub ({branch}). "
                        f"Update it manually — {description}"
                    ),
                    status=ChangeStatus.FAILED,
                    severity="hard",
                ))

        return content_map, failed

    def _backup_existing(self, rel_paths: List[str]) -> Dict[str, Optional[str]]:
        """Read current content of each path for rollback.

        Returns {rel_path: content} where content is None if the file did not
        exist (so a rollback knows to delete a newly created file).
        """
        backups: Dict[str, Optional[str]] = {}
        for rel_path in rel_paths:
            backups[rel_path] = self._read_file(rel_path) if self._file_exists(rel_path) else None
        return backups

    def _restore_backups(self, backups: Dict[str, Optional[str]]) -> None:
        """Restore files to their pre-write state after a failed commit."""
        for rel_path, content in backups.items():
            if content is None:
                full_path = os.path.join(self.repo_root, rel_path)
                if os.path.exists(full_path):
                    try:
                        os.remove(full_path)
                    except OSError:
                        pass
            else:
                self._write_file(rel_path, content)

    def _commit_staged(self, content_map: Dict[str, Tuple[str, str]]) -> List[ChangeRecord]:
        """Phase B core: write all staged files. Raises on write error."""
        records: List[ChangeRecord] = []
        for rel_path, (content, description) in content_map.items():
            self._write_file(rel_path, content)
            records.append(ChangeRecord(
                description=f"Updated {rel_path} — {description}",
                status=ChangeStatus.APPLIED,
                severity="hard",
            ))
        return records

    def _state_file_path(self) -> str:
        return os.path.join(self.repo_root, UPGRADE_STATE_FILE)

    def _write_state_file(self, status: str, files: List[str], tag: Optional[str]) -> None:
        """Write the in-progress / failed state marker."""
        data = {
            'from_version': self.from_version,
            'to_version': self.to_version,
            'tag': tag,
            'status': status,
            'files': list(files),
            'timestamp': self._now_iso(),
        }
        try:
            with open(self._state_file_path(), 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def _clear_state_file(self) -> None:
        path = self._state_file_path()
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    @staticmethod
    def _now_iso() -> str:
        from datetime import datetime
        return datetime.now().isoformat(timespec='seconds')

    def _apply_framework_files(
        self, file_map: Dict[str, str], tag: Optional[str] = None
    ) -> List[ChangeRecord]:
        """Atomically fetch and write a set of framework files.

        Phase A fetches all files; if any required fetch fails, nothing is
        written and only the failure records are returned (the site is left
        unchanged). Phase B backs up existing files, writes an in-progress
        state marker, commits the staged content, and restores the backups if
        any write raises.

        Args:
            file_map: {rel_path: description} of framework files.
            tag: Release tag to pin to (defaults to self._TARGET_TAG, then 'main').

        Returns:
            List[ChangeRecord] — APPLIED records on success, or HARD FAILED
            records when Phase A failed or the commit was rolled back.
        """
        pinned = tag if tag is not None else self._TARGET_TAG

        content_map, failed = self._fetch_all_staged(file_map, tag=pinned)
        if failed:
            # Fail closed: a missing required file means write nothing.
            return failed

        paths = list(content_map.keys())
        backups = self._backup_existing(paths)
        self._write_state_file('in_progress', paths, pinned)
        try:
            records = self._commit_staged(content_map)
        except Exception as e:
            self._restore_backups(backups)
            self._clear_state_file()
            return [ChangeRecord(
                description=f"Framework file write failed and was rolled back: {e}",
                status=ChangeStatus.FAILED,
                severity="hard",
            )]

        self._clear_state_file()
        return records

    def _detect_language(self) -> str:
        """
        Detect site language from _config.yml.

        Reads the top-level telar_language setting (added in v0.6.0).
        Useful for providing bilingual migration messages and summaries.

        Returns:
            'es' for Spanish, 'en' for English (default)
        """
        config_path = os.path.join(self.repo_root, '_config.yml')

        try:
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # telar_language is a top-level _config.yml key. The legacy
            # nested form (telar.telar_language) was checked here before
            # but never matched any real site config — kept as a fallback
            # only in case a user manually moved the key.
            lang = config.get('telar_language')
            if lang is None:
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
