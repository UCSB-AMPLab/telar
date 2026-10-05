"""
UPGRADE_SUMMARY.md for the Telar upgrade engine.

Turns the records a chain produced into the summary a site owner reads:
applied changes grouped under their headings, failures in the two sections
that say what a re-run will do, and the manual steps addressed to this site.
Called by telar_upgrade.py.

Ships in the release tooling tarball beside telar_upgrade.py, never in a
site.

Version: v1.8.0
"""

import re
from typing import Dict, List, Optional

from migrations.base import (
    BaseMigration, ChangeCategory, ChangeRecord, ChangeStatus,
    category_for_path, is_author_step, is_flagged, is_hard_failure,
)
from migrations.messages import get_message, get_file_count_suffix
from telar_upgrade_common import _get_date


# A path inside a change description: a dotted filename, or one of the
# dotfiles the chain touches by name. Records that carry no category of
# their own still name the file they changed, and the filename is the part
# of a description that does not move when someone rewords the sentence
# around it.
# Longest extension first: alternation is leftmost-first, so `js` ahead of
# `json` would match `package.js` out of `package.json` and file an npm
# manifest under Scripts.
_PATH_IN_DESCRIPTION = re.compile(
    r'(?:[\w./-]*\.(?:yaml|yml|json|scss|html|lock|css|txt|ini|md|py|js)(?!\w)'
    r'|\.gitignore|\.gitattributes|\.ruby-version'
    r'|\bNOTICE\b|\bLICENSE\b)',
    re.IGNORECASE,
)


def _category_from_description(description: str) -> str:
    """The heading for a record that carries no category of its own.

    Legacy migrations return bare strings, which `coerce_change` wraps
    without a category, so something has to place them. This reads the
    file path out of the description and asks `category_for_path`, which
    is the same function a record with a category answers with.

    The category is derived from the path, not guessed from keywords in the
    prose. A path in the description does not change when the sentence
    around it is reworded.

    A description naming no file falls to Other, which is honest: there is
    no file for the change to be filed under.
    """
    for match in _PATH_IN_DESCRIPTION.finditer(description):
        token = match.group(0).lstrip('`\'"(')
        # Both spellings: the name table is keyed on real filenames, which
        # are cased (README.md, NOTICE), while a description may shout a
        # path it is quoting.
        for candidate in (token, token.lower()):
            category = category_for_path(candidate)
            if category != ChangeCategory.OTHER:
                return category
    return ChangeCategory.OTHER


def _categorize_changes(records: List[ChangeRecord]) -> dict:
    """Group applied changes under the summary headings, in print order.

    A record's own `category` is used when it has one. A record without
    one is placed by the file path in its description, which is what
    `_category_from_description` is for.

    Returns:
        {category slug: [description, ...]}, empty categories dropped.
    """
    grouped = {category: [] for category in ChangeCategory.ORDER}

    for record in records:
        category = record.category or _category_from_description(record.description)
        if category not in grouped:
            category = ChangeCategory.OTHER
        grouped[category].append(record.description)

    return {name: items for name, items in grouped.items() if items}


def generate_checklist(
    migrations: List[BaseMigration],
    all_changes: List[ChangeRecord],
    from_version: str,
    to_version: str,
    soft_warnings: Optional[List[str]] = None,
    lang: str = 'en',
    sheets_enabled: bool = True,
    extra_manual_steps: Optional[List[dict]] = None,
) -> str:
    """
    Generate UPGRADE_SUMMARY.md content (without YAML frontmatter).

    Applied changes render as ticked `- [x]` items and are the only ones
    counted in the automated-changes total. Failed changes render as unticked
    `- [ ]` items so a failure is never reported as completed work, under one
    of two headings: a blocking failure, where the site was not upgraded and
    a re-run is the fix, and a flagged one, where the file is absent from the
    release, the site was upgraded anyway, and a re-run changes nothing. A
    failure that is a step for the site's owner (severity 'author') is
    neither: it is numbered among the manual steps, after the declared ones.

    Args:
        migrations: List of migrations that were run
        all_changes: ChangeRecords for every change attempted
        from_version: Original version
        to_version: Target version
        soft_warnings: Non-fatal warnings (e.g. IIIF tile regeneration) to
            surface visibly rather than bury.
        lang: Language code for the summary text ('en' or 'es'), from the
            site's telar_language setting.
        sheets_enabled: Whether the site pulls content from Google Sheets,
            which decides whether the spreadsheet manual steps are addressed
            to its owner. Defaults to True so a caller that does not know
            shows every step rather than hiding one.
        extra_manual_steps: Steps the run discovered rather than a migration
            declaring them. They are not filtered by audience: the run found
            this site in this state, so the step is addressed to whoever is
            reading this summary.

    Returns:
        Markdown content for summary
    """
    soft_warnings = soft_warnings or []

    applied = [r for r in all_changes if r.status == ChangeStatus.APPLIED]
    # The two kinds of failure get their own sections, because one body
    # cannot be true of both: a blocking failure means the site was not
    # upgraded and a re-run is the fix, and a flagged one means the site was
    # upgraded and a re-run changes nothing.
    failed = [r for r in all_changes if is_hard_failure(r)]
    flagged = [r for r in all_changes if is_flagged(r)]

    # What the run left for the site's owner to do is a manual step, not a
    # flag: the flag's text tells the reader to report a fault in Telar.
    author_steps = [{'description': r.description, 'audience': 'all'}
                    for r in all_changes if is_author_step(r)]
    manual_steps = _visible_manual_steps(migrations, sheets_enabled)
    manual_steps = manual_steps + list(extra_manual_steps or []) + author_steps

    # Categorize applied changes
    categorized = _categorize_changes(applied)

    summary_title = get_message(lang, 'summary_title')
    checklist = f"""---
layout: default
title: {summary_title}
---

## {summary_title}
- **{get_message(lang, 'summary_from')}:** {from_version}
- **{get_message(lang, 'summary_to')}:** {to_version}
- **{get_message(lang, 'summary_date')}:** {_get_date()}
- **{get_message(lang, 'summary_automated_changes')}:** {len(applied)}
- **{get_message(lang, 'summary_manual_steps')}:** {len(manual_steps)}
"""
    if failed:
        checklist += f"- **{get_message(lang, 'summary_failed_count')}:** {len(failed)}\n"
    if flagged:
        checklist += f"- **{get_message(lang, 'summary_flagged_count')}:** {len(flagged)}\n"
    checklist += f"\n## {get_message(lang, 'automated_changes_applied')}\n\n"

    # Output changes by category
    for category, changes in categorized.items():
        category_label = get_message(lang, 'category_' + category)
        file_suffix = get_file_count_suffix(lang, len(changes))
        checklist += f"### {category_label} ({len(changes)} {file_suffix})\n\n"
        for change in changes:
            checklist += f"- [x] {change}\n"
        checklist += "\n"

    # Failures are never ticked and never counted as automated changes.
    checklist += _listed_section(lang, 'failed_needs_attention', 'failed_section_body',
                                 [f"[ ] {record.description}" for record in failed])
    checklist += _listed_section(lang, 'flagged_needs_attention', 'flagged_section_body',
                                 [f"[ ] {record.description}" for record in flagged])
    checklist += _listed_section(lang, 'completed_with_warnings', 'warnings_section_body',
                                 soft_warnings)
    checklist += _manual_steps_section(lang, manual_steps)

    checklist += f"""
## {get_message(lang, 'resources')}

- [{get_message(lang, 'full_documentation')}](https://telar.org/docs)
- [{get_message(lang, 'changelog')}](https://github.com/UCSB-AMPLab/telar/blob/main/CHANGELOG.md)
- [{get_message(lang, 'report_issues')}](https://github.com/UCSB-AMPLab/telar/issues)
"""

    return checklist


def _listed_section(lang: str, heading_key: str, body_key: str,
                    items: List[str]) -> str:
    """A heading, its explanation and a bulleted list, or nothing when empty."""
    if not items:
        return ''
    section = f"## {get_message(lang, heading_key)}\n\n"
    section += get_message(lang, body_key) + "\n\n"
    for item in items:
        section += f"- {item}\n"
    return section + "\n"


def _manual_steps_section(lang: str, manual_steps: List[dict]) -> str:
    """The numbered manual steps, or the note that there are none."""
    if not manual_steps:
        return f"## {get_message(lang, 'no_manual_steps')}\n\n{get_message(lang, 'all_automated')}\n"
    section = f"""## {get_message(lang, 'manual_steps_required')}

{get_message(lang, 'complete_after_merge')}

"""
    for i, step in enumerate(manual_steps, 1):
        section += f"{i}. {step['description']}"
        if 'doc_url' in step:
            section += f" ([{get_message(lang, 'guide')}]({step['doc_url']}))"
        section += "\n"
    return section


def _visible_manual_steps(migrations: List[BaseMigration],
                          sheets_enabled: bool) -> List[Dict[str, str]]:
    """The manual steps this site's owner is actually meant to act on.

    The framework's half of the `audience` contract. The Compositor filters
    the same field on its own screen.

    `local` is not filtered here and cannot be. It means "the Compositor
    does this for you", and a site running this engine is by definition not
    being upgraded by the Compositor, so every `local` step is addressed to
    whoever is reading this summary.

    An unrecognised value shows the step. A step nobody can see is the
    failure the field exists to prevent, so an unknown audience errs
    towards the reader rather than away.
    """
    visible = []
    for migration in migrations:
        for step in migration.get_manual_steps():
            audience = step.get('audience')
            if audience == 'google-sheets' and not sheets_enabled:
                continue
            visible.append(step)
    return visible
