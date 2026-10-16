"""
The Stale Engine

A site made from the template carries a copy of the upgrade engine:
`scripts/telar_upgrade.py` and its three helpers. A site that runs the
launcher never executes that copy, since `scripts/upgrade.py` downloads a
verified engine for each run, so on such a site the files are dead copies
whose version numbers suggest otherwise. `remove_stale_engine()` deletes
them. The engine calls it once an upgrade has succeeded, next to the
removal of the site's `scripts/migrations/`, so every upgrade clears the
copies whichever release the site was made from.

Four guards, each against a way the deletion could cost the site something:

  - The site's `scripts/upgrade.py` must assign the launcher marker at
    module level. Without the launcher, the site's copy of the engine is the
    only thing it can upgrade with. A comment or string carrying the
    marker's text does not make a file a launcher.
  - Nothing is touched when this module was loaded from the site's own
    `scripts/`, and no file the running engine was started or loaded from
    is deleted.
  - A file goes only when its bytes are a copy a release shipped
    (RELEASED_ENGINE_SHA256). Any other is the site's own: it stays, and the
    report says so.
  - A link stays whatever it points at: it is something the site set up.

Soft throughout: a tidy-up cannot be the reason a completed upgrade reports
failure. Absent files are a no-op, so a second run reports nothing.

Version: v1.8.2
"""

import ast
import hashlib
import os
import sys
from typing import List

from .base import ChangeRecord, ChangeStatus, LAUNCHER_MARKER
from .messages import get_message
from .records import ChangeCategory

ENGINE_FILES = [
    'scripts/telar_upgrade.py',
    'scripts/telar_upgrade_common.py',
    'scripts/telar_upgrade_regen.py',
    'scripts/telar_upgrade_report.py',
]

# The sha256 of every copy of those files a release put in a site, computed
# from the release tags and recomputed from them by the tests, which fail
# until every released copy is here. The comment on each hash names the
# tags that hold it.
RELEASED_ENGINE_SHA256 = {
    'scripts/telar_upgrade.py': {
        '046378e5f279fedc646f7e158a206689ac98838775c3779d13ec0160d792f18e',  # v1.7.0
        'dd0821da5131ce12f0d4a7b3ea73b464e56ec8eae91fa9a131cad289796824db',  # v1.8.0, v1.8.1
    },
    'scripts/telar_upgrade_common.py': {
        'eb0ddd903f51d587827da298f55afcd37b11f2e929a813f5dc34ec263513ccb2',  # v1.8.0, v1.8.1
    },
    'scripts/telar_upgrade_regen.py': {
        '194b99fa14c5978170e9e4e7147ff765fcd624c9c890be69868c8256f15e5e6f',  # v1.8.0, v1.8.1
    },
    'scripts/telar_upgrade_report.py': {
        '1c970f55131349028c1335b20826d93bba93415f23d19a2038ed369446cdfaac',  # v1.8.0, v1.8.1
    },
}

# The modules the engine runs as. A file any of them was loaded from is the
# engine that is running, and is never deleted.
_ENGINE_MODULES = ('__main__', 'telar_upgrade', 'telar_upgrade_common',
                   'telar_upgrade_regen', 'telar_upgrade_report')

# The scripts directory this module was imported from, compared with the
# site's own before anything is deleted.
_ENGINE_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def remove_stale_engine(repo_root: str, lang: str) -> List[ChangeRecord]:
    """Delete a launcher site's released copies of the engine; a record per
    file found."""
    if not _site_runs_the_launcher(repo_root) or _running_from_the_site(repo_root):
        return []
    running = _running_engine_files()
    records = []
    for rel_path in ENGINE_FILES:
        path = os.path.join(repo_root, rel_path)
        if os.path.isfile(path) and os.path.realpath(path) not in running:
            records.append(_record(lang, rel_path, path))
    return records


def _record(lang: str, rel_path: str, path: str) -> ChangeRecord:
    if os.path.islink(path) or _sha256(path) not in RELEASED_ENGINE_SHA256.get(rel_path, set()):
        description = get_message(lang, 'v180_engine_kept', rel_path)
        status = ChangeStatus.APPLIED
    else:
        try:
            os.remove(path)
            description = get_message(lang, 'v180_engine_removed', rel_path)
            status = ChangeStatus.APPLIED
        except OSError as error:
            description = get_message(lang, 'v180_engine_not_removed', rel_path, error)
            status = ChangeStatus.FAILED
    return ChangeRecord(description=description, status=status, severity='soft',
                        category=ChangeCategory.SCRIPTS)


def _site_runs_the_launcher(repo_root: str) -> bool:
    """Whether the site's scripts/upgrade.py assigns LAUNCHER_MARKER to the
    name LAUNCHER_MARKER at module level. Parsed, never run."""
    try:
        with open(os.path.join(repo_root, 'scripts', 'upgrade.py'), encoding='utf-8') as handle:
            tree = ast.parse(handle.read())
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return False
    return any(isinstance(node, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'LAUNCHER_MARKER'
                       for t in node.targets)
               and isinstance(node.value, ast.Constant)
               and node.value.value == LAUNCHER_MARKER
               for node in tree.body)


def _running_from_the_site(repo_root: str) -> bool:
    site_scripts = os.path.realpath(os.path.join(repo_root, 'scripts'))
    return site_scripts == os.path.realpath(_ENGINE_SCRIPTS_DIR)


def _running_engine_files() -> set:
    """Every file, resolved, the running engine was started or loaded from."""
    paths = [sys.argv[0]] if sys.argv and sys.argv[0] else []
    for name in _ENGINE_MODULES:
        loaded = getattr(sys.modules.get(name), '__file__', None)
        if loaded:
            paths.append(loaded)
    return {os.path.realpath(path) for path in paths}


def _sha256(path: str) -> str:
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()
