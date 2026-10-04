"""
Change Records and Shared Rules for Telar Upgrades

The vocabulary a migration reports in, and the rules the chain applies to
it, none of which needs a migration instance: `ChangeStatus`, `ChangeRecord`
and `ChangeCategory` with the path-to-heading tables, `FetchOutcome` and
`FetchResult` for a fetch that produced nothing, the manual-step audiences,
the launcher marker, the state file's name, `coerce_change` and
`is_hard_failure`, and `apply_config_version`, the one writer of the
`telar.version` stamp.

`base.py` imports all of it back, so a migration, the engine and the tests
import these names from `migrations.base` as they always have. They live
here so that module can be the migration base class alone.

Version: v1.8.0
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union
import re


class ChangeStatus(str, Enum):
    """Outcome of a single change a migration attempted."""

    APPLIED = "applied"
    FAILED = "failed"
    SKIPPED = "skipped"


class FetchOutcome(str, Enum):
    """Why a fetch did not produce content, when it did not.

    The chain acts on this difference. A TRANSIENT failure clears on a
    re-run, so stopping is right and the user's next attempt makes
    progress. A STRUCTURAL failure is identical on every attempt — the
    path is not at the pinned ref, and the ref is a tag — so stopping
    strands the site on that step forever.
    """

    OK = "ok"
    TRANSIENT = "transient"
    STRUCTURAL = "structural"


# HTTP responses that mean the path is not there and will not be on a
# re-run. Everything else — rate limits, 5xx, DNS failures, timeouts — is
# transient by default, and the asymmetry is deliberate: reading a transient
# failure as structural writes a partial install the site never needed,
# while reading a structural one as transient only costs the stalled re-run
# that already happens today.
STRUCTURAL_HTTP_CODES = frozenset({404, 410})


@dataclass
class FetchResult:
    """What one fetch produced, and why it produced nothing when it did not.

    Attributes:
        content: File content as `str`, or `bytes` when it is not valid
            UTF-8, or None on any failure.
        outcome: OK, TRANSIENT or STRUCTURAL.
        detail: The underlying error, for the console line. Empty on OK.
    """

    content: Optional[Union[str, bytes]]
    outcome: FetchOutcome
    detail: str = ""


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
        category: Which UPGRADE_SUMMARY.md heading this belongs under, one
            of ChangeCategory. None leaves the summary to guess from the
            description, which is what it did for every record before this
            field existed — a rephrased description silently moved a change
            to "Other".
    """

    description: str
    status: ChangeStatus = ChangeStatus.APPLIED
    severity: str = "soft"
    category: Optional[str] = None


class ChangeCategory:
    """The UPGRADE_SUMMARY.md headings, as values a record can carry.

    Slugs rather than English titles: the heading a reader sees comes from
    messages.py under `category_<slug>`, so the record names the section
    without naming the language.
    """

    CONFIGURATION = 'configuration'
    LAYOUTS = 'layouts'
    INCLUDES = 'includes'
    STYLES = 'styles'
    SCRIPTS = 'scripts'
    DOCUMENTATION = 'documentation'
    OTHER = 'other'

    # The order the summary prints them in.
    ORDER = (CONFIGURATION, LAYOUTS, INCLUDES, STYLES, SCRIPTS,
             DOCUMENTATION, OTHER)


# Where a framework file belongs, by path. First match wins, so the
# specific prefixes precede the extension rules: assets/css/ is a style
# whatever it is called, and scripts/ is a script even when it holds a .md.
_CATEGORY_BY_PREFIX = (
    ('_config.yml', ChangeCategory.CONFIGURATION),
    ('_data/', ChangeCategory.CONFIGURATION),
    ('_layouts/', ChangeCategory.LAYOUTS),
    ('_includes/', ChangeCategory.INCLUDES),
    ('_sass/', ChangeCategory.STYLES),
    ('assets/css/', ChangeCategory.STYLES),
    ('assets/js/', ChangeCategory.SCRIPTS),
    ('scripts/', ChangeCategory.SCRIPTS),
    ('tests/', ChangeCategory.SCRIPTS),
    ('docs/', ChangeCategory.DOCUMENTATION),
)

_CATEGORY_BY_SUFFIX = (
    ('.scss', ChangeCategory.STYLES),
    ('.css', ChangeCategory.STYLES),
    ('.js', ChangeCategory.SCRIPTS),
    ('.py', ChangeCategory.SCRIPTS),
    ('.yml', ChangeCategory.CONFIGURATION),
    ('.md', ChangeCategory.DOCUMENTATION),
)

# Files whose name is the whole answer.
_CATEGORY_BY_NAME = {
    'README.md': ChangeCategory.DOCUMENTATION,
    'CHANGELOG.md': ChangeCategory.DOCUMENTATION,
    'LICENSE': ChangeCategory.DOCUMENTATION,
    'NOTICE': ChangeCategory.DOCUMENTATION,
    '.gitignore': ChangeCategory.CONFIGURATION,
    'package.json': ChangeCategory.CONFIGURATION,
    'package-lock.json': ChangeCategory.CONFIGURATION,
    'requirements.txt': ChangeCategory.CONFIGURATION,
    'pytest.ini': ChangeCategory.CONFIGURATION,
    'vitest.config.js': ChangeCategory.CONFIGURATION,
}


def category_for_path(path: str) -> str:
    """Which summary heading a change to *path* belongs under."""
    if path in _CATEGORY_BY_NAME:
        return _CATEGORY_BY_NAME[path]
    for prefix, category in _CATEGORY_BY_PREFIX:
        if path == prefix or path.startswith(prefix):
            return category
    for suffix, category in _CATEGORY_BY_SUFFIX:
        if path.endswith(suffix):
            return category
    return ChangeCategory.OTHER


# Who still has to perform a manual step. The set is the Compositor's, not
# ours: its post-upgrade screen filters on this field, so a value it does not
# recognise is a value that does nothing.
#
#   all           — everyone upgrading, whatever route they took.
#   local         — everyone except Compositor users, because the Compositor
#                   does this itself. In practice the workflow-file recopies,
#                   which exist only because GitHub will not let an automated
#                   upgrade write to .github/workflows/ and the Compositor
#                   commits them directly.
#   google-sheets — only sites that pull their content from Google Sheets.
#                   The Compositor shows these when the site has Sheets
#                   enabled and hides them otherwise.
#   compositor    — only Compositor users. Accepted by the filter and
#                   rendered, but it hides nothing from anyone: every reader
#                   of that screen is a Compositor user by definition. It is
#                   documentation, and a step may be left `all` instead.
#
# Two axes, not one. `local` and `compositor` are about the upgrade route;
# `google-sheets` is about how the site gets its content. A step can only
# declare one, so pick the axis that decides whether the reader must act.
MANUAL_STEP_AUDIENCES = ('all', 'local', 'google-sheets', 'compositor')


# What a manual step asks of its reader. The Compositor groups its
# post-upgrade screen by this field, and a step it cannot place is shown
# under a heading of its own, where the screen can no longer say that
# nothing is required.
#
#   action   — something the upgrade left undone that the reader may need
#              to do. A step that applies only in some cases ("if you
#              customized the language packs") is still an action: the
#              reader is the one who can tell.
#   optional — an action that need not be done.
#   note     — what changed, including how to use it.
#
# The question is independent of `audience`: a workflow recopy is `local`
# and an `action`.
MANUAL_STEP_KINDS = ('action', 'optional', 'note')


# What marks a site's scripts/upgrade.py as the launcher rather than an older
# copy of the engine. Defined in the launcher; matched as text, because
# importing the site's copy is the thing the engine must never do. Here
# rather than in the engine because two readers need it: the engine, which
# retires a launcher site's scripts/migrations/, and the v1.8.0 migration,
# which removes a launcher site's stale scripts/telar_upgrade.py and must
# not reach into the engine module for it.
LAUNCHER_MARKER = 'telar-upgrade-launcher-v1'


# Shared name for the in-progress / failed state marker (see the module
# docstring for the two roles it plays). Lives at the repo root.
UPGRADE_STATE_FILE = "UPGRADE_STATE.json"


# What opens the block this writer edits: a top-level `telar:` and nothing
# else on the line but whitespace or a comment. `startswith('telar:')` also
# matched `telar:custom:`, a valid key of its own, and `telar: {version: x}`,
# an inline mapping that cannot take block entries -- writing into either
# produced a file no parser would read.
_TELAR_SECTION = re.compile(r'telar:[ \t]*(#.*)?$')


def apply_config_version(content, new_version, new_date):
    """Rewrite telar.version / telar.release_date in _config.yml *content*,
    a text edit rather than a YAML round-trip, so the rest of the file keeps
    its comments, ordering and spacing exactly.

    The two lines it rewrites are the exception, and they are rewritten
    whole: a trailing comment on `version` or `release_date` does not
    survive, and the value comes back double-quoted whatever quoting it had.
    Both are measured, not intended -- worth knowing before anyone relies on
    a note written on those lines.

    Single source of truth for the version stamp — both BaseMigration (per
    migration) and upgrade.py (the final stamp in main()) call this, so the
    parsing rules cannot drift between copies.

    What the parsing guarantees:
      - Indent-agnostic: any indented line is treated as inside the `telar:`
        section; the section ends only at the next non-blank column-0 line, so
        a single-space indent does not truncate it.
      - Inserts a release_date line right after version if the section has a
        version but no release_date.
      - Writes both lines at the top of the section if it declares neither.
        A `telar:` section with no version reads as 0.2.0-beta upstream, so
        the site runs the whole chain; leaving the stamp unwritten sends it
        through the chain again on the next run. A section that does not
        exist is still left alone -- inventing it would guess at a file
        this writer cannot see the shape of.

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
    telar_idx = None
    section_indent = None
    version_idx = None
    release_date_seen = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # A top-level key closes any open section; `telar:` then opens one.
        # Both are decided on the same line, because a second `telar:`
        # header does both at once -- checking only while outside a section
        # meant the header that closed one was never seen as opening the
        # next, and a file with two sections had the first one stamped
        # while PyYAML read the second.
        indent_len = len(line) - len(line.lstrip())
        at_top_level = bool(stripped) and indent_len == 0

        # A comment at column 0 is not the end of the section: YAML does not
        # close a block mapping on one, and treating it as the end left the
        # stamp outside the section it belongs to.
        if at_top_level and not stripped.startswith('#'):
            in_telar_section = False
            if _TELAR_SECTION.match(line):
                # A new header resets what was learned from an earlier one.
                # Duplicate top-level keys are legal input and PyYAML keeps
                # the last, so the last section is the one a reader sees and
                # the one worth stamping.
                in_telar_section = True
                telar_idx = i
                section_indent = None
                version_idx = None
                release_date_seen = False
            continue

        if not in_telar_section:
            continue

        # Indentation is learned from a real entry. A comment can sit at any
        # column without being wrong, so taking the indent from one produced
        # a stamp that did not line up with the section's own keys.
        if stripped and not stripped.startswith('#') and section_indent is None:
            section_indent = line[:indent_len]

        if stripped.startswith('version:'):
            lines[i] = f'{line[:indent_len]}version: "{new_version}"'
            version_idx = i
            modified = True
        elif stripped.startswith('release_date:'):
            lines[i] = f'{line[:indent_len]}release_date: "{new_date}"'
            release_date_seen = True
            modified = True

    if _add_missing_stamp_lines(lines, telar_idx, section_indent, version_idx,
                                release_date_seen, new_version, new_date):
        modified = True

    return '\n'.join(lines), modified


def _add_missing_stamp_lines(lines, telar_idx, section_indent, version_idx,
                             release_date_seen, new_version, new_date):
    """Insert whichever stamp lines the last `telar:` section lacks.

    Edits *lines* in place, from what `apply_config_version` learned about
    the section, and returns whether it inserted anything.
    """
    # Insert a release_date line adjacent to version if the section lacked one.
    if version_idx is not None and not release_date_seen:
        vline = lines[version_idx]
        indent = vline[:len(vline) - len(vline.lstrip())]
        lines.insert(version_idx + 1, f'{indent}release_date: "{new_date}"')
        return True
    if version_idx is None and telar_idx is not None:
        # The section is there but never says which version the site is on.
        # Written at the top rather than the end because the section ends at
        # the next column-0 line, and a trailing blank line inside it would
        # put the stamp outside the block it belongs to.
        indent = section_indent if section_indent else '  '
        stamp = [f'{indent}version: "{new_version}"']
        if not release_date_seen:
            stamp.append(f'{indent}release_date: "{new_date}"')
        lines[telar_idx + 1:telar_idx + 1] = stamp
        return True
    return False


def coerce_change(change) -> ChangeRecord:
    """Coerce a migration's return element to a ChangeRecord.

    Migrations converted to the structured contract return ChangeRecord
    objects directly. Legacy migrations still return plain strings; treat each
    such string as a soft, already-applied change so the chain keeps working
    during the incremental conversion.

    One exception: legacy migrations report a failed framework-file fetch as a
    string containing "Could not fetch". That phrase appears only on fetch
    failures (other warnings say "Could not move/create/remove/read/update"),
    so it is safe to map it to a HARD failure — which makes even unconverted
    migrations fail closed instead of reporting a missing file as done.

    This lives here rather than in upgrade.py because two callers need the
    same rule: the chain runner, and any migration that runs other migrations
    internally. A second copy of the "Could not fetch" test would be a rule
    that can drift.
    """
    if isinstance(change, ChangeRecord):
        return change
    text = str(change)
    if "Could not fetch" in text:
        return ChangeRecord(description=text, status=ChangeStatus.FAILED, severity="hard")
    return ChangeRecord(description=text, status=ChangeStatus.APPLIED, severity="soft")


def is_hard_failure(record: ChangeRecord) -> bool:
    """True when this record must abort the upgrade."""
    return record.status == ChangeStatus.FAILED and record.severity == "hard"
