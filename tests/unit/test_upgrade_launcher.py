"""Unit tests for the upgrade launcher.

`scripts/upgrade.py` downloads the tooling for the newest release, verifies
it, and runs it. Most of these tests are about what it refuses: an archive
that could write outside the temp dir, a checksum file that does not name the
asset exactly, a local tarball with no digest to check it against. The
launcher runs arbitrary Python from the internet by design, so the
verification is the feature and the refusals are the contract.

Version: v1.7.0
"""

import ast
import hashlib
import io
import os
import sys
import tarfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import upgrade as launcher


def _tar(path, members):
    """Build a tarball from (name, type, size/content) triples."""
    with tarfile.open(path, 'w:gz') as archive:
        for entry in members:
            name, kind = entry[0], entry[1]
            info = tarfile.TarInfo(name)
            info.type = kind
            if kind == tarfile.REGTYPE:
                payload = entry[2].encode('utf-8')
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            else:
                if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                    info.linkname = entry[2]
                archive.addfile(info)


ENGINE_MEMBER = ('scripts/telar_upgrade.py', tarfile.REGTYPE, 'print("engine")\n')


class TestTheLauncherIsSelfContained:

    def test_it_imports_only_the_standard_library(self):
        """It runs before the upgrade has installed anything."""
        tree = ast.parse((SCRIPTS / 'upgrade.py').read_text(encoding='utf-8'))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split('.')[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split('.')[0])

        assert imported <= set(sys.stdlib_module_names), \
            imported - set(sys.stdlib_module_names)

    def test_it_does_not_import_the_engine(self):
        """The engine it runs is the verified copy, never the one beside it."""
        source = (SCRIPTS / 'upgrade.py').read_text(encoding='utf-8')

        assert 'import telar_upgrade' not in source
        assert 'from telar_upgrade' not in source


class TestSiteLanguage:

    def test_it_defaults_to_english_without_a_config(self, tmp_path):
        assert launcher.site_language(tmp_path) == 'en'

    def test_it_reads_a_spanish_site(self, tmp_path):
        (tmp_path / '_config.yml').write_text('telar_language: "es"\n')

        assert launcher.site_language(tmp_path) == 'es'

    def test_it_reads_an_unquoted_value(self, tmp_path):
        (tmp_path / '_config.yml').write_text('title: x\ntelar_language: es-CO\n')

        assert launcher.site_language(tmp_path) == 'es'

    def test_an_indented_key_is_not_the_top_level_one(self, tmp_path):
        """`telar.telar_language` is not the key the rest of the tooling reads."""
        (tmp_path / '_config.yml').write_text('telar:\n  telar_language: "es"\n')

        assert launcher.site_language(tmp_path) == 'en'


class TestTagValidation:

    @pytest.mark.parametrize('tag', ['v1.7.0', 'v0.9.0-beta', 'v1.0.0-rc.1'])
    def test_it_accepts_a_version_tag(self, tag):
        assert launcher.TAG_PATTERN.match(tag)

    @pytest.mark.parametrize('tag', [
        '1.7.0', 'vv1.7.0', 'v1.7', 'v1.7.0; rm -rf /', 'main',
        'v1.7.0/../../etc', 'v1.7.0 ', '',
    ])
    def test_it_refuses_anything_else(self, tag):
        assert not launcher.TAG_PATTERN.match(tag)


class TestChecksumParsing:

    def _checksums(self, tmp_path, text):
        path = tmp_path / 'checksums.txt'
        path.write_text(text, encoding='utf-8')
        return path

    def test_it_takes_the_digest_for_the_exact_asset(self, tmp_path):
        digest = 'a' * 64
        path = self._checksums(tmp_path,
                               f'{"b" * 64}  other.tar.gz\n{digest}  wanted.tar.gz\n')

        assert launcher.expected_digest(path, 'wanted.tar.gz', 'v1.7.0', 'en') == digest

    def test_it_accepts_the_binary_marker(self, tmp_path):
        digest = 'c' * 64
        path = self._checksums(tmp_path, f'{digest} *wanted.tar.gz\n')

        assert launcher.expected_digest(path, 'wanted.tar.gz', 'v1.7.0', 'en') == digest

    def test_a_similar_name_is_not_a_match(self, tmp_path):
        """A substring search would take the digest of the wrong asset."""
        path = self._checksums(tmp_path, f'{"d" * 64}  wanted.tar.gz.sig\n')

        with pytest.raises(SystemExit):
            launcher.expected_digest(path, 'wanted.tar.gz', 'v1.7.0', 'en')

    def test_two_entries_for_one_asset_are_refused(self, tmp_path):
        path = self._checksums(tmp_path,
                               f'{"e" * 64}  wanted.tar.gz\n{"f" * 64}  wanted.tar.gz\n')

        with pytest.raises(SystemExit):
            launcher.expected_digest(path, 'wanted.tar.gz', 'v1.7.0', 'en')

    def test_a_non_digest_is_refused(self, tmp_path):
        path = self._checksums(tmp_path, 'not-a-digest  wanted.tar.gz\n')

        with pytest.raises(SystemExit):
            launcher.expected_digest(path, 'wanted.tar.gz', 'v1.7.0', 'en')


class TestTheExtractionContract:
    """Names alone are not enough, which is what the first design got wrong."""

    def _extract(self, tmp_path, members):
        tarball = tmp_path / 'tooling.tar.gz'
        _tar(tarball, members)
        into = tmp_path / 'out'
        into.mkdir()
        return launcher.extract(tarball, into, 'en', 'tooling.tar.gz')

    def test_a_plain_tooling_archive_extracts(self, tmp_path):
        engine = self._extract(tmp_path, [
            ('scripts', tarfile.DIRTYPE),
            ENGINE_MEMBER,
        ])

        assert engine.is_file()
        assert engine.read_text() == 'print("engine")\n'

    def test_a_symlink_member_is_refused(self, tmp_path):
        """The attack: `scripts` as a link out, then a write through it."""
        with pytest.raises(SystemExit):
            self._extract(tmp_path, [
                ('scripts', tarfile.SYMTYPE, '/tmp'),
                ENGINE_MEMBER,
            ])

    def test_a_hardlink_member_is_refused(self, tmp_path):
        with pytest.raises(SystemExit):
            self._extract(tmp_path, [
                ENGINE_MEMBER,
                ('scripts/other.py', tarfile.LNKTYPE, 'scripts/telar_upgrade.py'),
            ])

    def test_a_fifo_member_is_refused(self, tmp_path):
        """A FIFO where the engine should be would block the run forever."""
        with pytest.raises(SystemExit):
            self._extract(tmp_path, [('scripts/telar_upgrade.py', tarfile.FIFOTYPE)])

    def test_a_device_member_is_refused(self, tmp_path):
        with pytest.raises(SystemExit):
            self._extract(tmp_path, [
                ENGINE_MEMBER,
                ('scripts/dev', tarfile.CHRTYPE),
            ])

    def test_an_absolute_path_is_refused(self, tmp_path):
        with pytest.raises(SystemExit):
            self._extract(tmp_path, [
                ('/etc/passwd', tarfile.REGTYPE, 'x'),
                ENGINE_MEMBER,
            ])

    def test_a_parent_traversal_is_refused(self, tmp_path):
        with pytest.raises(SystemExit):
            self._extract(tmp_path, [
                ('../escaped.py', tarfile.REGTYPE, 'x'),
                ENGINE_MEMBER,
            ])

    def test_an_archive_without_the_engine_is_refused(self, tmp_path):
        with pytest.raises(SystemExit):
            self._extract(tmp_path, [('scripts/other.py', tarfile.REGTYPE, 'x')])

    def test_too_many_members_are_refused(self, tmp_path):
        members = [(f'scripts/f{i}.py', tarfile.REGTYPE, 'x')
                   for i in range(launcher.MAX_MEMBERS + 1)]

        with pytest.raises(SystemExit):
            self._extract(tmp_path, members)


class TestTheLocalTarballPath:

    def _tarball(self, tmp_path):
        tarball = tmp_path / 'telar-scripts-v1.7.0.tar.gz'
        _tar(tarball, [('scripts', tarfile.DIRTYPE), ENGINE_MEMBER])
        digest = hashlib.sha256(tarball.read_bytes()).hexdigest()
        return tarball, digest

    def test_a_tarball_without_a_digest_is_refused(self, tmp_path, capsys):
        tarball, _ = self._tarball(tmp_path)

        with pytest.raises(SystemExit):
            launcher.main(['--repo-root', str(tmp_path),
                           '--tooling-tarball', str(tarball)])

        assert '--tooling-sha256' in capsys.readouterr().err

    def test_a_wrong_digest_is_refused(self, tmp_path):
        tarball, _ = self._tarball(tmp_path)

        with pytest.raises(SystemExit):
            launcher.main(['--repo-root', str(tmp_path),
                           '--tooling-tarball', str(tarball),
                           '--tooling-sha256', '0' * 64])

    def test_a_missing_tarball_is_refused(self, tmp_path):
        with pytest.raises(SystemExit):
            launcher.main(['--repo-root', str(tmp_path),
                           '--tooling-tarball', str(tmp_path / 'nope.tar.gz'),
                           '--tooling-sha256', '0' * 64])

    def test_the_verified_engine_runs_with_the_flags_passed_through(
            self, tmp_path, monkeypatch):
        tarball, digest = self._tarball(tmp_path)
        seen = {}

        def _fake_call(command, cwd=None):
            seen['command'] = command
            seen['cwd'] = cwd
            return 0

        monkeypatch.setattr(launcher.subprocess, 'call', _fake_call)

        assert launcher.main(['--repo-root', str(tmp_path),
                              '--tooling-tarball', str(tarball),
                              '--tooling-sha256', digest,
                              '--dry-run']) == 0
        assert seen['command'][1].endswith('scripts/telar_upgrade.py')
        assert '--dry-run' in seen['command']
        assert seen['cwd'] == str(tmp_path)

    def test_it_returns_the_engines_exit_code(self, tmp_path, monkeypatch):
        tarball, digest = self._tarball(tmp_path)
        monkeypatch.setattr(launcher.subprocess, 'call',
                            lambda command, cwd=None: 3)

        assert launcher.main(['--repo-root', str(tmp_path),
                              '--tooling-tarball', str(tarball),
                              '--tooling-sha256', digest]) == 3

    def test_the_engine_it_runs_is_not_the_one_in_the_site(self, tmp_path,
                                                           monkeypatch):
        """The temp copy is what runs, whatever the site happens to hold."""
        tarball, digest = self._tarball(tmp_path)
        (tmp_path / 'scripts').mkdir()
        (tmp_path / 'scripts' / 'telar_upgrade.py').write_text('raise SystemExit(9)')
        seen = {}
        monkeypatch.setattr(launcher.subprocess, 'call',
                            lambda command, cwd=None: seen.setdefault('c', command) and 0)

        launcher.main(['--repo-root', str(tmp_path),
                       '--tooling-tarball', str(tarball),
                       '--tooling-sha256', digest])

        assert str(tmp_path / 'scripts') not in seen['c'][1]


class TestBadTagsNeverReachAUrl:

    def test_a_shell_shaped_tag_is_refused_before_any_request(self, tmp_path,
                                                             monkeypatch):
        def _explode(*args, **kwargs):
            raise AssertionError('the launcher made a request')

        monkeypatch.setattr(launcher.urllib.request, 'urlopen', _explode)

        with pytest.raises(SystemExit):
            launcher.main(['--repo-root', str(tmp_path),
                           '--target-version', 'v1.7.0; curl evil.example'])
