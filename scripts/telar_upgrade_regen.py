"""
Data regeneration for the Telar upgrade engine.

After the migrations have run, the site's JSON, collections and IIIF tiles
are regenerated so the new release's validation applies to existing content,
and the modules that needs are installed first if this interpreter lacks
them. Called by telar_upgrade.py.

Ships in the release tooling tarball beside telar_upgrade.py, never in a
site: the requirements manifest it prefers is the tarball's own, found
beside the scripts/ directory this module sits in.

Version: v1.8.0
"""

import os
import sys
from pathlib import Path
from typing import List, Tuple

from migrations.messages import get_message
from telar_upgrade_common import PROTECTED_PREREQUISITE_EXIT, _get_lang


def _regenerate_data_files(repo_root: str) -> Tuple[bool, bool, bool]:
    """
    Regenerate JSON data files and IIIF tiles from CSV sources with validation.

    Runs csv_to_json.py, generate_collections.py, and generate_iiif.py to apply
    validation logic to existing data and regenerate IIIF tiles for local images.

    csv_to_json and generate_collections are HARD: if they fail the derived data
    is stale and the upgrade must not be stamped as complete. generate_iiif is
    SOFT: tile generation can fail (e.g. missing source images) without
    invalidating the upgrade, and is surfaced as a warning instead.

    Precondition: the modules in _REGENERATION_IMPORTS must be importable in
    this interpreter — main() runs _ensure_regeneration_dependencies() first.

    Args:
        repo_root: Path to repository root

    One cause is carved out of the HARD rule. `csv_to_json.py` exits
    PROTECTED_PREREQUISITE_EXIT when the site has a protected story that
    the build workflow cannot encrypt, and it does so *after* writing every
    JSON file — the regeneration succeeded, and what failed is a check on a
    future build. Treating that as a hard failure aborts the upgrade and
    leaves a working site at its old version, while preventing nothing: the
    build runs `csv_to_json.py` too, so the same refusal stops publication
    whether or not this upgrade completes. The site is left needing a
    workflow edit either way; the only question is whether it also loses
    the upgrade.

    Returns:
        (csv_ok, iiif_ok, protected_blocked). csv_ok is False if the HARD
        data steps could not be run or returned an error. iiif_ok is False
        if IIIF tile regeneration failed (non-fatal). protected_blocked is
        True when the data was regenerated but a protected story has no way
        to be encrypted; csv_ok is True in that case. When the scripts are
        absent, csv_ok is False (the caller treats "could not regenerate"
        as a HARD failure).
    """
    import subprocess

    lang = _get_lang(repo_root)
    scripts_dir = os.path.join(repo_root, 'scripts')
    csv_to_json = os.path.join(scripts_dir, 'csv_to_json.py')
    generate_collections = os.path.join(scripts_dir, 'generate_collections.py')

    # Check if scripts exist
    if not os.path.exists(csv_to_json):
        return (False, True, False)

    try:
        # Run csv_to_json.py (generates objects.json with validation)
        result = subprocess.run(
            [sys.executable, csv_to_json],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30
        )

        protected_blocked = result.returncode == PROTECTED_PREREQUISITE_EXIT
        if result.returncode != 0 and not protected_blocked:
            print('  ' + get_message(lang, 'regeneration_script_error',
                                     'csv_to_json.py', result.stderr))
            return (False, True, False)
        if protected_blocked:
            # The refusal is the engine's own, and it prints both languages.
            print(result.stdout.rstrip())

        # Run generate_collections.py (generates story/glossary JSON with validation)
        if os.path.exists(generate_collections):
            result = subprocess.run(
                [sys.executable, generate_collections],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                print('  ' + get_message(lang, 'regeneration_script_error',
                                         'generate_collections.py', result.stderr))
                return (False, True, False)

        # Run generate_iiif.py (regenerates IIIF tiles for local images).
        # SOFT: a failure here does not block the upgrade.
        iiif_ok = True
        generate_iiif = os.path.join(scripts_dir, 'generate_iiif.py')
        if os.path.exists(generate_iiif):
            result = subprocess.run(
                [sys.executable, generate_iiif],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=180  # Longer timeout for tile generation
            )

            if result.returncode != 0:
                print('  ' + get_message(lang, 'regeneration_script_error',
                                         'generate_iiif.py', result.stderr))
                iiif_ok = False

        return (True, iiif_ok, protected_blocked)

    except subprocess.TimeoutExpired:
        print('  ' + get_message(lang, 'regeneration_timeout'))
        return (False, True, False)
    except Exception as e:
        print('  ' + get_message(lang, 'regeneration_failed', e))
        return (False, True, False)


# Import names that data regeneration transitively requires. csv_to_json.py and
# generate_collections.py load the scripts/telar package, which eagerly imports
# these; regeneration cannot run unless every one resolves. These are import
# names, not pip package names — requirements.txt lists the packages that
# provide them (PIL comes from Pillow, yaml from pyyaml).
_REGENERATION_IMPORTS = ["markdown", "PIL", "jinja2", "cryptography", "yaml", "pandas"]


def _missing_regeneration_imports() -> List[str]:
    """Return the subset of _REGENERATION_IMPORTS that cannot currently be imported."""
    import importlib.util
    return [name for name in _REGENERATION_IMPORTS
            if importlib.util.find_spec(name) is None]


def _ensure_regeneration_dependencies(repo_root: str) -> Tuple[bool, List[str]]:
    """Ensure the modules data regeneration needs are importable.

    _regenerate_data_files() subprocess-runs csv_to_json.py and
    generate_collections.py, which transitively import the modules in
    _REGENERATION_IMPORTS through the scripts/telar package. This script is
    fetched fresh from the release tooling tarball on every run, so it ensures
    its own dependencies here rather than relying on the site's CI workflow — a
    copy the migrations cannot update.

    When every required module already resolves, this returns immediately with no
    pip call. Otherwise it installs from a requirements manifest, preferring the
    tooling copy shipped beside this script (the tarball places requirements.txt
    as a sibling of scripts/) and falling back to the site's own requirements.txt.

    Args:
        repo_root: Path to the site being upgraded (source of the fallback manifest).

    Returns:
        (ok, missing). ok is True when every required module is importable after
        the ensure step. missing lists the import names still unresolved.
    """
    import importlib
    import subprocess

    lang = _get_lang(repo_root)
    missing = _missing_regeneration_imports()
    if not missing:
        return (True, [])

    # Manifest search order: the tooling copy beside this script first (tarball
    # layout: requirements.txt sibling of scripts/), then the site's own copy —
    # the fallback that is the only manifest present when the tooling tarball
    # carries no requirements.txt.
    candidates = [
        Path(__file__).resolve().parent.parent / 'requirements.txt',
        Path(repo_root) / 'requirements.txt',
    ]
    manifest = next((p for p in candidates if p.is_file()), None)

    if manifest is None:
        print(get_message(lang, 'deps_no_manifest', ', '.join(missing)))
        return (False, missing)

    print(get_message(lang, 'deps_installing', manifest))
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '-r', str(manifest)],
            capture_output=True,
            text=True,
            # pip resolves over the network; without a bound, a hung fetch
            # stalls the CI job until the runner's own multi-hour timeout.
            timeout=600,
        )
        if result.returncode != 0:
            stderr_tail = '\n'.join((result.stderr or '').strip().splitlines()[-10:])
            print(get_message(lang, 'deps_pip_failed', manifest, stderr_tail))
    except subprocess.TimeoutExpired:
        print(get_message(lang, 'deps_pip_timeout', manifest))

    # A fresh install may not be visible to find_spec until import caches are cleared.
    importlib.invalidate_caches()
    still_missing = _missing_regeneration_imports()
    return (not still_missing, still_missing)
