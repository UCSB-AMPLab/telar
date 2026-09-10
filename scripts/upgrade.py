#!/usr/bin/env python3
"""
Telar Upgrade Launcher

Downloads the upgrade tooling for the newest Telar release, verifies it
against the release's published checksum, and runs it against this site from
a temporary directory. This file does not upgrade anything itself.

Why a launcher. The engine (`telar_upgrade.py`) carries its migrations as
files sitting beside it, and derives the latest version it knows about from
the last of them. A copy living in a site therefore has no representation of
any release published after that copy was made: a site created at v1.4.0 asks
its own tooling, is told v1.4.0 is current, and stays three releases behind
while reporting success. The workflow never had this problem because it asks
GitHub what is newest and runs that. This makes the local path do the same.

Nothing here imports anything outside the standard library. It has to run on
a site whose dependencies may be exactly what the upgrade is about to install,
and on the oldest interpreter Telar supports.

Usage:
    python3 scripts/upgrade.py
    python3 scripts/upgrade.py --dry-run
    python3 scripts/upgrade.py --target-version v1.7.0
    python3 scripts/upgrade.py --tooling-tarball ./telar-scripts-v1.7.0.tar.gz \
                               --tooling-sha256 <hex>

Version: v1.7.0
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

TELAR_REPO = 'UCSB-AMPLab/telar'
ENGINE = 'scripts/telar_upgrade.py'

# How the engine recognises that a site's scripts/upgrade.py is this
# launcher and not an older copy of the engine itself. It reads the file
# rather than importing it, so the marker has to be findable as text.
LAUNCHER_MARKER = 'telar-upgrade-launcher-v1'

# The same shape upgrade.yml refuses to go past, applied before the value
# reaches a URL.
TAG_PATTERN = re.compile(r'^v[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$')

# A digest is 64 hex characters and nothing else.
SHA256_PATTERN = re.compile(r'^[0-9a-f]{64}$')

# Bounds. curl streams to disk and cannot be made to exhaust memory; urllib
# read() can. The archive is tooling, not content: a few hundred kilobytes.
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 5000
CHUNK = 64 * 1024

MESSAGES = {
    'en': {
        'resolving': 'Resolving the newest Telar release...',
        'resolved': 'Target release: {}',
        'downloading': 'Downloading {} ...',
        'verified': 'Verified {} (sha256 {})',
        'running': 'Running the verified tooling against this site...',
        'bad_tag': "Refusing to proceed: '{}' is not a version tag (expected vX.Y.Z).",
        'no_release': 'Could not work out the newest release of {}. Pass '
                      '--target-version to name one, or run the "Upgrade Telar" '
                      'workflow from the Actions tab instead.',
        'no_asset': 'Release {} has no {}. Releases published before the tooling '
                    'bundle existed do not carry one — name a later release with '
                    '--target-version, or use the "Upgrade Telar" workflow.',
        'no_checksum': 'checksums.txt for {} does not list {} — refusing to run '
                       'unverified code.',
        'many_checksums': 'checksums.txt for {} lists {} more than once — refusing '
                          'to guess which is right.',
        'mismatch': 'Checksum mismatch for {}: expected {}, got {}. Refusing to '
                    'run it.',
        'no_engine': '{} does not contain {} — refusing to run it.',
        'bad_member': '{} contains an entry this launcher will not extract ({}). '
                      'Refusing to run it.',
        'too_big': '{} is larger than this launcher will accept.',
        'not_a_file': 'The extracted {} is not a regular file. Refusing to run it.',
        'need_digest': '--tooling-tarball requires --tooling-sha256. A tarball with '
                       'no digest to check it against is unverified code.',
        'tarball_missing': 'No such file: {}',
    },
    'es': {
        'resolving': 'Buscando la versión más reciente de Telar…',
        'resolved': 'Versión de destino: {}',
        'downloading': 'Descargando {} …',
        'verified': '{} verificado (sha256 {})',
        'running': 'Ejecutando las herramientas verificadas sobre este sitio…',
        'bad_tag': "No se continúa: '{}' no es una etiqueta de versión (se espera vX.Y.Z).",
        'no_release': 'No se pudo averiguar cuál es la versión más reciente de {}. '
                      'Indica una con --target-version o usa el flujo de trabajo '
                      '"Upgrade Telar" desde la pestaña Actions.',
        'no_asset': 'La versión {} no trae {}. Las versiones publicadas antes de '
                    'que existiera este paquete de herramientas no lo tienen: '
                    'indica una versión posterior con --target-version o usa el '
                    'flujo de trabajo "Upgrade Telar".',
        'no_checksum': 'El archivo checksums.txt de {} no incluye {}: no se '
                       'ejecuta código sin verificar.',
        'many_checksums': 'El archivo checksums.txt de {} incluye {} más de una '
                          'vez: no se adivina cuál es el correcto.',
        'mismatch': 'La suma de comprobación de {} no coincide: se esperaba {} y se '
                    'obtuvo {}. No se ejecuta.',
        'no_engine': '{} no contiene {}: no se ejecuta.',
        'bad_member': '{} contiene una entrada que este lanzador no extrae ({}). '
                      'No se ejecuta.',
        'too_big': '{} es más grande de lo que este lanzador acepta.',
        'not_a_file': 'El archivo {} extraído no es un archivo normal. No se ejecuta.',
        'need_digest': '--tooling-tarball necesita --tooling-sha256. Un tarball sin '
                       'una suma con la que compararlo es código sin verificar.',
        'tarball_missing': 'No existe el archivo: {}',
    },
}


def site_language(repo_root):
    """Read telar_language without importing yaml.

    The launcher runs before the upgrade has ensured any dependency, so it
    cannot use the parser the rest of the tooling uses. A top-level scalar is
    within reach of a regex; anything more would not be.
    """
    config = Path(repo_root) / '_config.yml'
    try:
        text = config.read_text(encoding='utf-8')
    except OSError:
        return 'en'
    match = re.search(r'^telar_language:\s*["\']?([A-Za-z-]+)', text, re.M)
    if match and match.group(1).lower().startswith('es'):
        return 'es'
    return 'en'


def say(lang, key, *args):
    template = MESSAGES.get(lang, MESSAGES['en']).get(key, MESSAGES['en'][key])
    return template.format(*args) if args else template


def fail(lang, key, *args):
    print('ERROR: ' + say(lang, key, *args), file=sys.stderr)
    raise SystemExit(1)


def resolve_tag(lang):
    """The newest release tag, by API and then by redirect.

    The API is unauthenticated here, so it is rate-limited per address and a
    busy or shared address can exhaust it. The redirect on
    /releases/latest resolves to /releases/tag/<tag> without a token, which
    covers that case. Both exclude prereleases, so an installable release
    must never be published with that flag.
    """
    url = f'https://api.github.com/repos/{TELAR_REPO}/releases/latest'
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            tag = json.loads(response.read(1024 * 1024).decode('utf-8')).get('tag_name')
        if tag:
            return tag
    except (urllib.error.URLError, ValueError, OSError):
        pass

    class _KeepLocation(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            _KeepLocation.seen = newurl
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    _KeepLocation.seen = None
    opener = urllib.request.build_opener(_KeepLocation)
    try:
        with opener.open(f'https://github.com/{TELAR_REPO}/releases/latest',
                         timeout=30) as response:
            final = getattr(response, 'url', '') or ''
    except (urllib.error.URLError, OSError):
        final = _KeepLocation.seen or ''

    match = re.search(r'/releases/tag/([^/?#]+)$', final or (_KeepLocation.seen or ''))
    if match:
        return match.group(1)
    fail(lang, 'no_release', TELAR_REPO)


def download(url, destination, lang, label):
    """Stream to disk with a ceiling, so a wrong URL cannot exhaust memory."""
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            written = 0
            with open(destination, 'wb') as out:
                while True:
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > MAX_DOWNLOAD_BYTES:
                        fail(lang, 'too_big', label)
                    out.write(chunk)
    except urllib.error.HTTPError:
        return False
    except (urllib.error.URLError, OSError):
        return False
    return True


def expected_digest(checksums_path, asset, tag, lang):
    """The one digest for exactly this filename, or refuse.

    A substring search over a file listing several assets can match a
    similarly named one; two entries for the same name is a broken release
    rather than a choice to make.
    """
    found = []
    for line in checksums_path.read_text(encoding='utf-8').splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip('*') == asset:
            found.append(parts[0].lower())
    if not found:
        fail(lang, 'no_checksum', tag, asset)
    if len(set(found)) > 1 or len(found) > 1:
        fail(lang, 'many_checksums', tag, asset)
    if not SHA256_PATTERN.match(found[0]):
        fail(lang, 'no_checksum', tag, asset)
    return found[0]


def digest_of(path):
    sha = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b''):
            sha.update(chunk)
    return sha.hexdigest()


def safe_members(archive, lang, label):
    """Every member, once each is proven to be a plain file or directory.

    Names alone are not enough. An archive can carry `scripts` as a symlink
    pointing outside the destination and then a regular member at
    `scripts/telar_upgrade.py`, which a lexical check passes and extraction
    writes through the link. Refusing every non-regular member removes the
    capability rather than testing for its uses; a FIFO left where the engine
    should be would also block the run forever.
    """
    total = 0
    members = []
    for member in archive.getmembers():
        if len(members) >= MAX_MEMBERS:
            fail(lang, 'too_big', label)
        if not (member.isfile() or member.isdir()):
            fail(lang, 'bad_member', label, member.name)
        name = member.name
        if name.startswith('/') or name.startswith('\\'):
            fail(lang, 'bad_member', label, name)
        parts = Path(name).parts
        if any(part == '..' for part in parts) or any(':' in part for part in parts):
            fail(lang, 'bad_member', label, name)
        total += max(member.size, 0)
        if total > MAX_EXPANDED_BYTES:
            fail(lang, 'too_big', label)
        members.append(member)
    return members


def extract(tarball, into, lang, label):
    with tarfile.open(tarball, 'r:gz') as archive:
        members = safe_members(archive, lang, label)
        if sys.version_info >= (3, 12):
            archive.extractall(into, members=members, filter='data')
        else:
            archive.extractall(into, members=members)

    engine = Path(into) / ENGINE
    if not engine.exists():
        fail(lang, 'no_engine', label, ENGINE)
    # islink first: exists() follows the link, and a link is what the member
    # check refuses to create but the destination might already hold.
    if engine.is_symlink() or not engine.is_file():
        fail(lang, 'not_a_file', ENGINE)
    return engine


def fetch_tooling(tag, workdir, lang):
    asset = f'telar-scripts-{tag}.tar.gz'
    base = f'https://github.com/{TELAR_REPO}/releases/download/{tag}'
    tarball = workdir / asset
    checksums = workdir / 'checksums.txt'

    print('  ' + say(lang, 'downloading', asset))
    if not download(f'{base}/{asset}', tarball, lang, asset):
        fail(lang, 'no_asset', tag, asset)
    if not download(f'{base}/checksums.txt', checksums, lang, 'checksums.txt'):
        fail(lang, 'no_asset', tag, 'checksums.txt')

    expected = expected_digest(checksums, asset, tag, lang)
    actual = digest_of(tarball)
    if expected != actual:
        fail(lang, 'mismatch', asset, expected, actual)
    print('  ' + say(lang, 'verified', asset, actual))
    return tarball, asset


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Download verified Telar upgrade tooling and run it here.')
    parser.add_argument('--target-version', default=None,
                        help='Release tag to upgrade to (default: the newest)')
    parser.add_argument('--tooling-tarball', default=None,
                        help='Use this tooling tarball instead of downloading one')
    parser.add_argument('--tooling-sha256', default=None,
                        help='Required with --tooling-tarball: its expected digest')
    parser.add_argument('--repo-root', default=None,
                        help='The site to upgrade (default: the current directory)')
    known, passthrough = parser.parse_known_args(argv)

    repo_root = Path(known.repo_root or os.getcwd()).resolve()
    lang = site_language(repo_root)

    with tempfile.TemporaryDirectory(prefix='telar-tooling-') as tmp:
        workdir = Path(tmp)

        if known.tooling_tarball:
            # A local path is not evidence of anything. Without a digest to
            # check it against, running it is arbitrary code execution against
            # the site — which is the one thing the workflow's verified
            # download exists to prevent.
            if not known.tooling_sha256:
                fail(lang, 'need_digest')
            tarball = Path(known.tooling_tarball)
            if not tarball.is_file():
                fail(lang, 'tarball_missing', str(tarball))
            label = tarball.name
            expected = known.tooling_sha256.strip().lower()
            actual = digest_of(tarball)
            if expected != actual:
                fail(lang, 'mismatch', label, expected, actual)
            print('  ' + say(lang, 'verified', label, actual))
        else:
            # Validate a tag the user named before announcing a lookup that
            # is not going to happen.
            if known.target_version:
                tag = known.target_version
            else:
                print(say(lang, 'resolving'))
                tag = resolve_tag(lang)
            if not TAG_PATTERN.match(tag):
                fail(lang, 'bad_tag', tag)
            print('  ' + say(lang, 'resolved', tag))
            tarball, label = fetch_tooling(tag, workdir, lang)

        extracted = workdir / 'tooling'
        extracted.mkdir()
        engine = extract(tarball, extracted, lang, label)

        print(say(lang, 'running'))
        command = [sys.executable, str(engine), '--repo-root', str(repo_root)]
        command.extend(passthrough)
        return subprocess.call(command, cwd=str(repo_root))


if __name__ == '__main__':
    sys.exit(main())
