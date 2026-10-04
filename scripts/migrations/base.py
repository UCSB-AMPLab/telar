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
text rather than round-tripping YAML, so the rest of the file keeps its
comments and formatting — the two lines it rewrites are the exception and
are rewritten whole. Both `BaseMigration` (per migration) and `upgrade.py`
(the final stamp) call it so the parsing rules cannot drift between two
copies.

Those types and `apply_config_version()` are defined in `records.py`, with
the other rules that need no migration instance, and imported back here, so
they are still imported from this module.

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

Version: v1.8.0
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Union
import json
import os
import re
import shutil
import time

from .messages import get_message


# The records, the categories and the shared rules live in records.py. Every
# name is imported back here, the same objects rather than copies, so
# `from migrations.base import ChangeRecord` keeps working for the migrations,
# the engine and the tests, and an isinstance check sees one class.
from .records import (  # noqa: F401
    ChangeStatus, FetchOutcome, STRUCTURAL_HTTP_CODES, FetchResult,
    ChangeRecord, ChangeCategory, category_for_path, MANUAL_STEP_AUDIENCES, MANUAL_STEP_KINDS,
    UPGRADE_STATE_FILE, LAUNCHER_MARKER, apply_config_version, coerce_change,
    is_hard_failure,
)


class BaseMigration(ABC):
    """Base class for all Telar version migrations."""

    # Override these in subclasses
    from_version: str = ""
    to_version: str = ""
    description: str = ""

    # Versions this migration can be entered from, when it covers more than
    # one. A consolidated migration standing in for a run of old releases
    # lists every version it absorbs; the dispatcher pins `from_version` to
    # whichever one the site is actually on before calling check_applicable(),
    # so the summary still names the version the user started at. Left empty
    # by an ordinary single-hop migration, which is entered only from its own
    # from_version.
    from_versions: List[str] = []

    # Release tag to pin framework-file fetches to (e.g. "v1.4.0"). When set,
    # the staged-atomic helpers fetch from this immutable tag instead of the
    # moving `main` branch, so an upgrade from version X to version Y always
    # receives version-Y files. Left None for pre-tagging-era betas, which
    # fall back to `main` with a documented historical caveat.
    _TARGET_TAG: Optional[str] = None

    # A commit to pin to when the release was never tagged. Kept separate
    # from _TARGET_TAG so that field stays a git tag whose version must
    # agree with to_version — a contract the tests enforce — instead of
    # being overloaded with a SHA that no version grammar can read.
    _TARGET_COMMIT: Optional[str] = None

    def __init__(self, repo_root: str):
        """
        Initialize migration with repository root path.

        Args:
            repo_root: Absolute path to the Telar repository root
        """
        self.repo_root = repo_root
        self.changes_made = []

    @classmethod
    def entry_version_list(cls) -> List[str]:
        """Every version this migration may be entered from.

        A classmethod as well as a property because callers that only have
        the class — the registry-wide checks, chiefly — need the same answer
        as the dispatcher, and one rule cannot drift from itself.
        """
        return list(cls.from_versions) or [cls.from_version]

    @property
    def entry_versions(self) -> List[str]:
        """Every version this migration may be entered from."""
        return type(self).entry_version_list()

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
            List of dicts with keys: 'description', 'audience', 'kind',
            'doc_url' (optional).

        `audience` says who still has to do the step, and exists because the
        Compositor does some of them for the user. It is required on every
        step: a step that forgets it is shown to everyone, which is the
        behaviour it was added to stop, and a default would hide that.

        The question it answers is narrow — *is this step made unnecessary by
        the Compositor doing it for you?* It is not "who is this step about".
        A step whose prose already says "if you use GitHub Pages" is still
        `all`: every reader sees it and the prose sorts them out.

        `kind` says what the step asks of its reader: `action`, `optional`
        or `note` (see MANUAL_STEP_KINDS). It is required on the same terms:
        the Compositor shows a step without one apart from the others, and
        cannot tell its reader that nothing is left to do.
        """
        return []

    def _file_exists(self, rel_path: str) -> bool:
        """Check if file exists relative to repo root."""
        return os.path.exists(os.path.join(self.repo_root, rel_path))

    def _read_file(self, rel_path: str) -> Optional[Union[str, bytes]]:
        """Read file contents relative to repo root.

        Text as `str`, anything that is not valid UTF-8 as `bytes`, so a
        backup of a binary asset round-trips through `_write_file` instead
        of raising mid-rollback.
        """
        full_path = os.path.join(self.repo_root, rel_path)
        try:
            with open(full_path, 'rb') as f:
                raw = f.read()
        except FileNotFoundError:
            return None
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            return raw

    def _write_file(self, rel_path: str, content: Union[str, bytes]) -> None:
        """Write file contents relative to repo root, text or binary."""
        full_path = os.path.join(self.repo_root, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        if isinstance(content, (bytes, bytearray)):
            with open(full_path, 'wb') as f:
                f.write(content)
        else:
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
            print("  " + get_message(self._detect_language(),
                                     'index_no_frontmatter'))
            return False

        # Find end of front matter (the closing '---')
        front_matter_end = 0
        for i in range(1, len(lines)):
            if re.match(r'^-{3}\s*$', lines[i]):
                front_matter_end = i + 1
                break

        if front_matter_end == 0:
            print("  " + get_message(self._detect_language(),
                                     'index_frontmatter_unclosed'))
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

        Text-based editing, so the file keeps its comments and formatting
        everywhere except the two lines rewritten -- see apply_config_version.

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
        Fetch file content from GitHub telar repository, or None on any failure.

        Callers that need to act on *why* a fetch failed use `_fetch_result`
        instead. This wrapper stays because most of the chain only needs the
        content, and a None here means exactly what it has always meant.

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
            File content as `str`, or as `bytes` when it is not valid UTF-8,
            or None if the fetch fails.

        Framework file maps name images as well as text — `leviathan.jpg`
        among them — and a fetcher that only decoded UTF-8 turned every one
        of those into a failed fetch. Since v1.5.0 a failed fetch is a HARD
        failure (`upgrade.py`), so a single binary asset in a file map
        stopped the whole chain.
        """
        return self._fetch_result(path, branch=branch, timeout=timeout).content

    def _fetch_result(self, path: str, branch: Optional[str] = None,
                      timeout: int = 10) -> FetchResult:
        """Fetch one file and say what happened, not only whether it worked.

        A 404 and a timeout are the same `None` to a caller that only reads
        content, and the chain cannot choose between stopping and continuing
        without telling them apart: one clears on a re-run and the other is
        the same answer forever.

        Args:
            path: Path to file relative to repo root.
            branch: Branch or tag to fetch from; see `_fetch_from_github`.
            timeout: Socket timeout in seconds.

        Returns:
            FetchResult — content on success, otherwise the outcome that
            says whether a re-run could ever produce a different answer.
        """
        import urllib.request
        import urllib.error

        # Resolve the ref: an explicit branch/tag wins; otherwise pin to this
        # migration's release tag; only fall back to the moving 'main' branch
        # when no tag is set (pre-tagging-era betas, documented historical gap).
        ref = branch if branch is not None else self._target_ref()

        url = f"https://raw.githubusercontent.com/UCSB-AMPLab/telar/{ref}/{path}"

        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                raw = response.read()
            try:
                return FetchResult(raw.decode('utf-8'), FetchOutcome.OK)
            except UnicodeDecodeError:
                return FetchResult(raw, FetchOutcome.OK)
        except urllib.error.HTTPError as e:
            # Caught before URLError, which it subclasses — this is the only
            # branch that carries a status code, and the code is the whole
            # basis for the distinction.
            outcome = (FetchOutcome.STRUCTURAL if e.code in STRUCTURAL_HTTP_CODES
                       else FetchOutcome.TRANSIENT)
            print("  " + get_message(self._detect_language(),
                                     'fetch_failed_console', path, e))
            return FetchResult(None, outcome, str(e))
        except urllib.error.URLError as e:
            print("  " + get_message(self._detect_language(),
                                     'fetch_failed_console', path, e))
            return FetchResult(None, FetchOutcome.TRANSIENT, str(e))
        except Exception as e:
            print("  " + get_message(self._detect_language(),
                                     'fetch_error_console', path, e))
            return FetchResult(None, FetchOutcome.TRANSIENT, str(e))

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

    def _target_ref(self) -> str:
        """The ref this migration's fetches pin to.

        A tag when the release has one, the recorded commit when it does
        not, and the moving `main` branch only when neither is declared —
        which means the step installs whatever the framework looks like on
        the day it runs.
        """
        return self._TARGET_COMMIT or self._TARGET_TAG or 'main'

    def _fetch_with_retry(self, path: str, branch: str) -> FetchResult:
        """Fetch one file, retrying a transient failure once with backoff.

        A structural failure is not retried. The ref is a release tag, so
        the second request asks the identical question and waits for the
        identical answer — on a file map with several wrong paths that is
        the whole backoff paid per path, for nothing.
        """
        result = self._fetch_result(path, branch=branch,
                                    timeout=self._STAGED_FETCH_TIMEOUT)
        attempt = 0
        while result.outcome is FetchOutcome.TRANSIENT and attempt < self._FETCH_RETRIES:
            attempt += 1
            time.sleep(min(2 ** attempt, 5))
            result = self._fetch_result(path, branch=branch,
                                        timeout=self._STAGED_FETCH_TIMEOUT)
        return result

    def _fetch_all_staged(
        self, file_map: Dict[str, str], tag: Optional[str] = None
    ) -> Tuple[Dict[str, Tuple[str, str]], List[ChangeRecord], List[ChangeRecord]]:
        """Phase A: fetch every file in file_map into memory without writing.

        Args:
            file_map: {rel_path: description} of framework files to fetch.
            tag: Release tag to pin to. Falls back to 'main' when None.

        Returns:
            (content_map, blocking, flagged). content_map maps
            rel_path -> (content, description) for every successful fetch.
            `blocking` holds a HARD record per transient failure; when it is
            non-empty the caller must write nothing, because a re-run can
            still produce the whole set. `flagged` holds a SOFT record per
            structural failure, which no re-run will change.
        """
        branch = tag if tag else 'main'
        content_map: Dict[str, Tuple[str, str]] = {}
        blocking: List[ChangeRecord] = []
        flagged: List[ChangeRecord] = []

        for rel_path, description in file_map.items():
            result = self._fetch_with_retry(rel_path, branch)
            if result.content is not None:
                content_map[rel_path] = (result.content, description)
            elif result.outcome is FetchOutcome.STRUCTURAL:
                # Not the user's problem to fix and not theirs to retry: the
                # path is absent from the release the migration pins to, so
                # the file map is wrong. Flag it and let the chain go on.
                flagged.append(ChangeRecord(
                    description=get_message(
                        self._detect_language(), 'record_fetch_absent',
                        rel_path, self.to_version),
                    status=ChangeStatus.FAILED,
                    severity="soft",
                    category=category_for_path(rel_path),
                ))
            else:
                # The record names the version, not the ref it was fetched
                # from. A site owner knows which version they upgraded to;
                # `main`, which is what the ref is when no tag is declared,
                # tells them nothing they can act on.
                blocking.append(ChangeRecord(
                    description=get_message(
                        self._detect_language(), 'record_fetch_failed',
                        rel_path, self.to_version),
                    status=ChangeStatus.FAILED,
                    severity="hard",
                ))

        if content_map or not flagged:
            return content_map, blocking, flagged

        # Nothing in the map arrived and every failure was a 404. One wrong
        # path in a file map is a wrong file map; every path wrong at once is
        # a wrong ref, and flagging our way past that would stamp the site
        # with a version whose files it never received. Stop instead.
        #
        # A one-file map whose only file is genuinely absent is caught here
        # too, since it looks identical from inside. That is the stall this
        # issue is about, kept deliberately for the case where continuing
        # cannot be told apart from continuing into nothing.
        return content_map, blocking + [
            ChangeRecord(description=record.description,
                         status=ChangeStatus.FAILED,
                         severity="hard",
                         category=record.category)
            for record in flagged], []

    def _install_files_one_by_one(
        self, file_map: Dict[str, str], template: str,
        branch: Optional[str] = None,
    ) -> List[ChangeRecord]:
        """Fetch and write each file as it arrives, reporting one record each.

        The pre-consolidation shape, kept because those migrations are
        historical and their summary wording is what their users read. It is
        not atomic and was never meant to be: each file is written the moment
        it arrives.

        What it does share with `_apply_framework_files` is the rule for
        deciding whether a failure stops the chain. A structural failure is
        flagged and the chain goes on — unless nothing in the map arrived at
        all, which is a wrong ref rather than a wrong path and has to stop.

        Args:
            file_map: {rel_path: description} of framework files.
            template: Format string for an installed file, taking `path` and
                `description`. Each migration keeps its own wording.
            branch: Ref to fetch from; defaults to the migration's own.

        Returns:
            List[ChangeRecord], one per file in the map.
        """
        installed: List[ChangeRecord] = []
        failures: List[ChangeRecord] = []

        for rel_path, description in file_map.items():
            result = self._fetch_result(rel_path, branch=branch)
            if result.content is not None:
                self._write_file(rel_path, result.content)
                installed.append(ChangeRecord(
                    description=template.format(path=rel_path,
                                                description=description),
                    status=ChangeStatus.APPLIED,
                    severity="soft",
                    category=category_for_path(rel_path),
                ))
            else:
                failures.append(self._record_for_failed_fetch(rel_path, result))

        if not installed and failures:
            failures = [ChangeRecord(description=record.description,
                                     status=ChangeStatus.FAILED,
                                     severity="hard",
                                     category=record.category)
                        for record in failures]

        return installed + failures

    def _record_for_failed_fetch(self, rel_path: str,
                                 result: FetchResult) -> ChangeRecord:
        """The record a failed fetch becomes, classified by why it failed.

        For a migration that writes its files one at a time rather than
        through `_apply_framework_files`. Such a migration has already
        written whatever arrived before this path, so there is no atomic
        install left to protect and the only question the outcome decides
        is whether the chain stops.
        """
        if result.outcome is FetchOutcome.STRUCTURAL:
            return ChangeRecord(
                description=get_message(
                    self._detect_language(), 'record_fetch_absent',
                    rel_path, self.to_version),
                status=ChangeStatus.FAILED,
                severity="soft",
                category=category_for_path(rel_path),
            )
        return ChangeRecord(
            description=get_message(
                self._detect_language(), 'record_fetch_failed',
                rel_path, self.to_version),
            status=ChangeStatus.FAILED,
            severity="hard",
        )

    def _backup_existing(self, rel_paths: List[str]) -> Dict[str, Optional[Union[str, bytes]]]:
        """Read current content of each path for rollback.

        Returns {rel_path: content} where content is None if the file did not
        exist (so a rollback knows to delete a newly created file).
        """
        backups: Dict[str, Optional[Union[str, bytes]]] = {}
        for rel_path in rel_paths:
            backups[rel_path] = self._read_file(rel_path) if self._file_exists(rel_path) else None
        return backups

    def _restore_backups(self, backups: Dict[str, Optional[Union[str, bytes]]]) -> None:
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
        # The file map's annotation documents why a path is in the set, for
        # whoever reads the migration. It stays out of the record: the summary
        # is a file the site commits to its own repository, and a record built
        # by interpolating English prose cannot be localised at render time.
        for rel_path, (content, _annotation) in content_map.items():
            self._write_file(rel_path, content)
            records.append(ChangeRecord(
                description=get_message(self._detect_language(),
                                        'updated_file', rel_path),
                status=ChangeStatus.APPLIED,
                severity="hard",
                # The path decides the summary heading, so the summary reads
                # each record's category off the record itself rather than
                # inferring it from the description's wording.
                category=category_for_path(rel_path),
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
        pinned = tag if tag is not None else self._target_ref()

        content_map, blocking, flagged = self._fetch_all_staged(file_map, tag=pinned)
        if blocking:
            # Fail closed while a re-run could still complete the set. The
            # atomic install is worth keeping for exactly this case, and the
            # structural records ride along so the summary names everything
            # that did not arrive, not only what stopped the chain.
            return blocking + flagged

        paths = list(content_map.keys())
        backups = self._backup_existing(paths)
        self._write_state_file('in_progress', paths, pinned)
        try:
            records = self._commit_staged(content_map)
        except Exception as e:
            self._restore_backups(backups)
            self._clear_state_file()
            return [ChangeRecord(
                description=get_message(self._detect_language(),
                                        'record_write_rolled_back', e),
                status=ChangeStatus.FAILED,
                severity="hard",
            )]

        self._clear_state_file()
        # Writing the files that did arrive is the part of the atomic
        # guarantee this trades away, and only for the failure a re-run
        # cannot clear: the alternative is a site that stops on this step
        # every time it upgrades, forever.
        return records + flagged

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

        # Binary has no lines to normalise, and either side can be bytes:
        # compare the raw content instead of splitting it.
        if isinstance(original_content, (bytes, bytearray)) or \
                isinstance(current_content, (bytes, bytearray)):
            return original_content != current_content

        # Normalize whitespace for comparison
        # Split into lines and strip each line to ignore formatting differences
        original_lines = [line.strip() for line in original_content.split('\n')]
        current_lines = [line.strip() for line in current_content.split('\n')]

        # Compare normalized content
        return original_lines != current_lines

    def __str__(self) -> str:
        return f"Migration {self.from_version} → {self.to_version}: {self.description}"
