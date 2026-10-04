"""
Dev-Only File List

This module deals with reading `scripts/dev-only-files.txt`, the single list
naming the files a site made through the Compositor does not carry — the
framework's own test infrastructure, present in the template only because
the template is also the framework's development repository.

Two callers read the list through this module: the unit test that pins its
contents against the template, and the release tooling that turns it into
`migration.json` delete operations when a release ships, so an existing
Compositor site loses the same files on upgrade that a new one never
receives. The command-line migration does not use it — that route leaves
the files in place, and a local user keeps the complete template.

`read_dev_only_files()` is the only function. It parses the list's format:
one repository-relative path per line, a line starting with `#` is a note
and is skipped, blank lines are skipped, and a path ending in `/` names a
directory. Paths come back in file order, exactly as written — the function
does not check that they exist, sort them, or strip a trailing slash, since
a caller building a delete operation needs to know a directory was written
as one.

Version: v1.8.0
"""

from pathlib import Path

# scripts/dev-only-files.txt, alongside this module's scripts/telar/ parent.
DEFAULT_LIST_PATH = Path(__file__).resolve().parent.parent / 'dev-only-files.txt'


def read_dev_only_files(list_path=None):
    """Return the paths listed in dev-only-files.txt, in file order.

    `list_path` defaults to the template's own `scripts/dev-only-files.txt`;
    a caller reading a different checkout (a cloned site, a Compositor-side
    fetch of the file) passes its own path.
    """
    path = Path(list_path) if list_path is not None else DEFAULT_LIST_PATH
    paths = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        paths.append(stripped)
    return paths
