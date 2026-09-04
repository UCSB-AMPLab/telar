"""
Unit Tests for Fetched-Content Edge Cases in Migrations

Framework file maps name images alongside text — `leviathan.jpg` in the
v0.6.0 demo template among them. A failed fetch is a HARD failure, so a
binary asset the fetcher cannot read stops the whole upgrade chain for
every site entering below that version.

An empty file is the same defect from the other side: `_fetch_from_github`
returns `''` for a legitimately empty file, and a caller testing truthiness
reads that as a failed fetch. Three `__init__.py` files in the v0.7.0
framework map are 0 bytes.

These tests cover the round trip a fetched file makes: fetched, written,
read back for a rollback backup, and compared for user modification.

Version: v1.7.0
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations.base import BaseMigration

# A real JPEG opens with these bytes, and 0xFF is not a valid UTF-8 start
# byte — which is exactly where the old fetcher raised.
JPEG_HEADER = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01'
JPEG = JPEG_HEADER + bytes(range(256)) * 4


class _Migration(BaseMigration):
    from_version = '0.5.0-beta'
    to_version = '0.6.0-beta'
    description = 'test double'

    def check_applicable(self):
        return True

    def apply(self):
        return []


@pytest.fixture
def migration(tmp_path):
    return _Migration(str(tmp_path))


class TestWriteFile:
    def test_writes_binary_unchanged(self, migration, tmp_path):
        migration._write_file('components/images/leviathan.jpg', JPEG)
        assert (tmp_path / 'components/images/leviathan.jpg').read_bytes() == JPEG

    def test_still_writes_text_as_utf8(self, migration, tmp_path):
        migration._write_file('a.md', '# Título\n\nprosa\n')
        assert (tmp_path / 'a.md').read_text(encoding='utf-8') == '# Título\n\nprosa\n'

    def test_creates_missing_directories_for_binary(self, migration, tmp_path):
        migration._write_file('deep/nested/img.png', JPEG)
        assert (tmp_path / 'deep/nested/img.png').exists()


class TestReadFile:
    def test_binary_comes_back_as_bytes(self, migration, tmp_path):
        (tmp_path / 'img.jpg').write_bytes(JPEG)
        assert migration._read_file('img.jpg') == JPEG

    def test_text_comes_back_as_str(self, migration, tmp_path):
        (tmp_path / 'a.md').write_text('prosa\n', encoding='utf-8')
        assert migration._read_file('a.md') == 'prosa\n'

    def test_a_missing_file_is_still_none(self, migration):
        assert migration._read_file('absent.md') is None


class TestBackupRoundTrip:
    def test_a_binary_file_survives_a_rollback(self, migration, tmp_path):
        # The rollback path reads every file it is about to overwrite, and
        # it runs mid-commit, with the tree already half-written. A read
        # that raises on a binary asset there leaves no way back.
        (tmp_path / 'img.jpg').write_bytes(JPEG)
        backups = migration._backup_existing(['img.jpg'])
        migration._write_file('img.jpg', b'clobbered')
        migration._restore_backups(backups)
        assert (tmp_path / 'img.jpg').read_bytes() == JPEG

    def test_a_file_that_did_not_exist_is_removed_on_rollback(self, migration, tmp_path):
        backups = migration._backup_existing(['new.jpg'])
        migration._write_file('new.jpg', JPEG)
        migration._restore_backups(backups)
        assert not (tmp_path / 'new.jpg').exists()


class TestFetchDecoding:
    def _fetch(self, migration, monkeypatch, payload):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self): return payload

        import urllib.request
        monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: Response())
        return migration._fetch_from_github('components/images/leviathan.jpg')

    def test_binary_is_returned_as_bytes_not_dropped(self, migration, monkeypatch):
        assert self._fetch(migration, monkeypatch, JPEG) == JPEG

    def test_text_is_still_returned_as_str(self, migration, monkeypatch):
        assert self._fetch(migration, monkeypatch, 'telar:\n'.encode('utf-8')) == 'telar:\n'


class TestModificationCheck:
    def _pin(self, migration, monkeypatch, original):
        monkeypatch.setattr(type(migration), '_fetch_from_github',
                            lambda self, path, branch=None, timeout=10: original)

    def test_identical_binary_is_not_modified(self, migration, monkeypatch, tmp_path):
        (tmp_path / 'img.jpg').write_bytes(JPEG)
        self._pin(migration, monkeypatch, JPEG)
        assert migration._is_file_modified('img.jpg') is False

    def test_changed_binary_is_modified(self, migration, monkeypatch, tmp_path):
        (tmp_path / 'img.jpg').write_bytes(JPEG + b'edited')
        self._pin(migration, monkeypatch, JPEG)
        assert migration._is_file_modified('img.jpg') is True

    def test_text_comparison_still_ignores_whitespace(self, migration, monkeypatch,
                                                     tmp_path):
        (tmp_path / 'a.md').write_text('  line one  \nline two\n', encoding='utf-8')
        self._pin(migration, monkeypatch, 'line one\nline two\n')
        assert migration._is_file_modified('a.md') is False


class TestEmptyContent:
    """An empty file is content, not a failed fetch.

    `tests/__init__.py`, `tests/unit/__init__.py` and `tests/e2e/__init__.py`
    are 0 bytes at v0.7.0-beta. A caller testing `if content:` reads the
    empty string as failure, and a failed fetch is a HARD failure.
    """

    def _fetch(self, migration, monkeypatch, payload):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self): return payload

        import urllib.request
        monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: Response())
        return migration._fetch_from_github('tests/__init__.py')

    def test_an_empty_fetch_is_distinguishable_from_a_failure(self, migration,
                                                              monkeypatch):
        fetched = self._fetch(migration, monkeypatch, b'')
        assert fetched == ''
        assert fetched is not None

    def test_an_empty_file_is_written(self, migration, tmp_path):
        migration._write_file('tests/__init__.py', '')
        written = tmp_path / 'tests/__init__.py'
        assert written.exists() and written.read_bytes() == b''

    def test_no_migration_tests_a_fetch_result_for_truthiness(self):
        # The whole class, closed at every call site rather than at the one
        # that happens to be reachable today.
        import pathlib
        import re
        root = pathlib.Path(__file__).resolve().parents[2] / 'scripts' / 'migrations'
        offenders = []
        for path in sorted(root.glob('*.py')):
            lines = path.read_text(encoding='utf-8').splitlines()
            for i, line in enumerate(lines):
                if line.strip() == 'if content:':
                    preceding = '\n'.join(lines[max(0, i - 3):i])
                    if '_fetch_from_github' in preceding:
                        offenders.append(f'{path.name}:{i + 1}')
        assert offenders == [], (
            'these read an empty fetch as a failure: ' + ', '.join(offenders))


def _migration_sources():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2] / 'scripts' / 'migrations'
    return sorted(path for path in root.glob('v*.py'))


class TestFetchFailuresAreReportedAsFailures:
    """upgrade.py classifies a legacy migration's change string as a HARD
    failure only when it contains "Could not fetch". Two migrations said
    "Failed to update" instead, so a 404 was recorded as an applied change
    and the upgrade reported success having not delivered the file."""

    def test_every_failed_fetch_branch_says_could_not_fetch(self):
        offenders = []
        for path in _migration_sources():
            lines = path.read_text(encoding='utf-8').splitlines()
            for i, line in enumerate(lines):
                if line.strip() != 'if content is not None:':
                    continue
                indent = len(line) - len(line.lstrip())
                for j in range(i + 1, min(i + 40, len(lines))):
                    stripped = lines[j].strip()
                    current = len(lines[j]) - len(lines[j].lstrip())
                    if stripped and current <= indent and stripped != 'else:':
                        break
                    if stripped == 'else:':
                        branch = '\n'.join(lines[j + 1:j + 5])
                        if 'changes.append' in branch and 'Could not fetch' not in branch:
                            offenders.append(f'{path.name}:{j + 2}')
                        break
        assert offenders == [], (
            'these report a failed fetch in wording upgrade.py reads as '
            'success: ' + ', '.join(offenders))


class TestFetchingMigrationsPinTheirRef:
    """A migration with neither pin fetches from the moving main branch,
    so what it installs changes as the framework moves and a file deleted
    upstream becomes a fetch failure years later."""

    def test_every_fetching_migration_declares_a_target_tag(self):
        import re
        offenders = []
        for path in _migration_sources():
            text = path.read_text(encoding='utf-8')
            if '_fetch_from_github' not in text and '_apply_framework_files' not in text:
                continue
            pinned = False
            for field in ('_TARGET_TAG', '_TARGET_COMMIT'):
                m = re.search(r"^\s*%s\s*=\s*(.+)$" % field, text, re.M)
                if m and not m.group(1).strip().startswith('None'):
                    pinned = True
            if not pinned:
                offenders.append(path.name)
        assert offenders == [], (
            'these fetch from the moving main branch: ' + ', '.join(offenders))
