#!/usr/bin/env python3
"""
Telar Upgrade Script

When a new version of Telar is released, existing sites need to be
updated to match the new framework. This script automates that process
by detecting the site's current version and applying every migration
needed to reach the latest version.

Each migration is a Python class in scripts/migrations/ that knows how
to transform a site from one specific version to the next. Migrations
can add, modify, or delete files — for example, adding new layout
templates, updating _config.yml with new settings, or renaming
directories. The script chains these together: upgrading from v0.3.0
to v0.6.2 runs every intermediate migration in sequence.

After applying automated changes, the script regenerates all data files
(JSON, collections, IIIF tiles) to apply any new validation or
processing logic introduced in the new version. The output is an
UPGRADE_SUMMARY.md file listing every automated change made and any
manual steps the user still needs to complete. The --dry-run flag
previews what would happen without making changes.

Version: v1.5.3

Usage:
    python scripts/upgrade.py              # Normal upgrade
    python scripts/upgrade.py --dry-run    # Preview changes without applying
"""

import os
import sys
import json
import yaml
import argparse
from typing import List, Optional, Tuple

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from migrations.base import (
    BaseMigration, ChangeRecord, ChangeStatus, UPGRADE_STATE_FILE,
    apply_config_version,
)
from migrations.messages import get_message
from migrations.v020_to_v030 import Migration020to030
from migrations.v030_to_v031 import Migration030to031
from migrations.v031_to_v032 import Migration031to032
from migrations.v032_to_v033 import Migration032to033
from migrations.v033_to_v034 import Migration033to034
from migrations.v034_to_v040 import Migration034to040
from migrations.v040_to_v041 import Migration040to041
from migrations.v041_to_v042 import Migration041to042
from migrations.v042_to_v043 import Migration042to043
from migrations.v043_to_v050 import Migration043to050
from migrations.v050_to_v060 import Migration050to060
from migrations.v060_to_v061 import Migration060to061
from migrations.v061_to_v062 import Migration061to062
from migrations.v062_to_v063 import Migration062to063
from migrations.v063_to_v070 import Migration063to070
from migrations.v070_to_v080 import Migration070to080
from migrations.v080_to_v081 import Migration080to081
from migrations.v081_to_v090 import Migration081to090
from migrations.v090_to_v091 import Migration090to091
from migrations.v091_to_v092 import Migration091to092
from migrations.v092_to_v093 import Migration092to093
from migrations.v093_to_v094 import Migration093to094
from migrations.v094_to_v100 import Migration094to100
from migrations.v100_to_v110 import Migration100to110
from migrations.v110_to_v120 import Migration110to120
from migrations.v120_to_v121 import Migration120to121
from migrations.v121_to_v130 import Migration121to130
from migrations.v130_to_v140 import Migration130to140
from migrations.v140_to_v150 import Migration140to150
from migrations.v150_to_v151 import Migration150to151
from migrations.v151_to_v152 import Migration151to152
from migrations.v152_to_v153 import Migration152to153
from migrations.v153_to_v154 import Migration153to154


# Latest version
LATEST_VERSION = "1.5.4"

# All available migrations in order
MIGRATIONS = [
    Migration020to030,
    Migration030to031,
    Migration031to032,
    Migration032to033,
    Migration033to034,
    Migration034to040,
    Migration040to041,
    Migration041to042,
    Migration042to043,
    Migration043to050,
    Migration050to060,
    Migration060to061,
    Migration061to062,
    Migration062to063,
    Migration063to070,
    Migration070to080,
    Migration080to081,
    Migration081to090,
    Migration090to091,
    Migration091to092,
    Migration092to093,
    Migration093to094,
    Migration094to100,
    Migration100to110,
    Migration110to120,
    Migration120to121,
    Migration121to130,
    Migration130to140,
    Migration140to150,
    Migration150to151,
    Migration151to152,
    Migration152to153,
    Migration153to154,
]


def detect_current_version(repo_root: str) -> Optional[str]:
    """
    Detect current Telar version from _config.yml.

    Args:
        repo_root: Path to repository root

    Returns:
        Version string (e.g., "0.2.0-beta") or None if not found
    """
    config_path = os.path.join(repo_root, '_config.yml')

    if not os.path.exists(config_path):
        print("❌ Error: _config.yml not found. Are you in a Telar repository?")
        return None

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Try to get version from telar.version. Guard against a bare `telar:`
        # key (parses to None) or a non-dict telar section, which would otherwise
        # raise TypeError on subscripting rather than falling back cleanly.
        telar_section = config.get('telar') if isinstance(config, dict) else None
        if isinstance(telar_section, dict) and 'version' in telar_section:
            return telar_section['version']

        # If no version found, assume v0.2.0 (before versioning was added)
        print("Warning: No version found in _config.yml, assuming v0.2.0-beta")
        return "0.2.0-beta"

    except (yaml.YAMLError, KeyError, TypeError, AttributeError) as e:
        print(f"❌ Error reading _config.yml: {e}")
        return None


def _get_lang(repo_root: str) -> str:
    """Read the site's telar_language from _config.yml for console output.

    Defaults to English when the config is missing/unreadable or the key is
    absent. messages.py recognises 'en' and 'es'; anything else falls back to
    English there.
    """
    config_path = os.path.join(repo_root, '_config.yml')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        if isinstance(config, dict):
            lang = config.get('telar_language')
            if isinstance(lang, str) and lang.strip():
                return lang.strip()
    except Exception:
        pass
    return 'en'


def get_migration_path(from_version: str, repo_root: str) -> List[BaseMigration]:
    """
    Get list of migrations to run from current version to latest.

    Args:
        from_version: Current version string
        repo_root: Path to repository root

    Returns:
        List of migration instances to run in order
    """
    migrations_to_run = []
    current_version = from_version

    for MigrationClass in MIGRATIONS:
        migration = MigrationClass(repo_root)

        # Strict chaining: a migration only joins the path when its from_version
        # matches the version reached so far. The old `or migrations_to_run`
        # heuristic ran EVERY later migration once the list was non-empty, so a
        # version gap (e.g. a 0.4.2-beta site, or a v-prefix mismatch) silently
        # produced the wrong chain instead of a clear "no path" signal.
        if migration.from_version == current_version:
            if migration.check_applicable():
                migrations_to_run.append(migration)
            # Advance whether or not the migration still needs applying — its
            # changes cover current_version → to_version either way, so the next
            # link in the chain can match.
            current_version = migration.to_version

    if current_version != LATEST_VERSION:
        lang = _get_lang(repo_root)
        print("\n" + get_message(lang, 'chain_stops', current_version, LATEST_VERSION))
        print(get_message(lang, 'chain_stops_note'))

    return migrations_to_run


def _coerce_record(change) -> ChangeRecord:
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
    """
    if isinstance(change, ChangeRecord):
        return change
    text = str(change)
    if "Could not fetch" in text:
        return ChangeRecord(description=text, status=ChangeStatus.FAILED, severity="hard")
    return ChangeRecord(description=text, status=ChangeStatus.APPLIED, severity="soft")


def run_migrations(migrations: List[BaseMigration], dry_run: bool = False) -> List[ChangeRecord]:
    """
    Run all migrations in sequence.

    Stops the chain as soon as a migration reports a HARD failure, so a failed
    fetch in one step does not let later steps run against a half-updated tree.

    Args:
        migrations: List of migration instances
        dry_run: If True, don't actually apply changes

    Returns:
        List of ChangeRecord objects for every change attempted.
    """
    all_changes: List[ChangeRecord] = []

    for migration in migrations:
        print(f"\n{migration}")

        if dry_run:
            print("  [DRY RUN] Would apply this migration")
            continue

        try:
            records = [_coerce_record(c) for c in migration.apply()]
        except Exception as e:
            # An unexpected error (not a handled fetch failure) is a HARD
            # failure: record it and stop the chain so the upgrade fails closed.
            print(f"  ✗ Error: {e}")
            all_changes.append(ChangeRecord(
                description=f"{migration.from_version} → {migration.to_version} aborted: {e}",
                status=ChangeStatus.FAILED,
                severity="hard",
            ))
            break

        all_changes.extend(records)

        for record in records:
            mark = "✓" if record.status == ChangeStatus.APPLIED else "✗"
            print(f"  {mark} {record.description}")

        # A HARD failure in this migration stops the chain.
        if any(r.status == ChangeStatus.FAILED and r.severity == "hard" for r in records):
            print("  ✗ Stopping: this migration did not complete. The site is left unchanged.")
            break

    return all_changes


def _categorize_changes(changes: List[str]) -> dict:
    """
    Categorize changes by file type for better organization.

    Args:
        changes: List of change descriptions

    Returns:
        Dictionary with categories as keys and lists of changes as values
    """
    categories = {
        'Configuration': [],
        'Layouts': [],
        'Includes': [],
        'Styles': [],
        'Scripts': [],
        'Documentation': [],
        'Other': []
    }

    for change in changes:
        change_lower = change.lower()

        # Categorize based on keywords in the change description
        # Check for specific patterns first, then broader patterns
        if '_config.yml' in change_lower or 'configuration' in change_lower or 'config' in change_lower:
            categories['Configuration'].append(change)
        elif 'layout' in change_lower:
            categories['Layouts'].append(change)
        elif 'include' in change_lower:
            categories['Includes'].append(change)
        elif 'style' in change_lower or 'scss' in change_lower or 'css' in change_lower or '.css' in change_lower:
            categories['Styles'].append(change)
        elif 'javascript' in change_lower or 'script' in change_lower or '.js' in change_lower:
            categories['Scripts'].append(change)
        elif 'readme' in change_lower or 'docs' in change_lower or 'documentation' in change_lower:
            categories['Documentation'].append(change)
        else:
            categories['Other'].append(change)

    # Remove empty categories
    return {k: v for k, v in categories.items() if v}


def generate_checklist(
    migrations: List[BaseMigration],
    all_changes: List[ChangeRecord],
    from_version: str,
    to_version: str,
    soft_warnings: Optional[List[str]] = None,
) -> str:
    """
    Generate UPGRADE_SUMMARY.md content (without YAML frontmatter).

    Applied changes render as ticked `- [x]` items and are the only ones
    counted in the automated-changes total. Failed changes render as unticked
    `- [ ]` items under a "Failed / Needs Manual Attention" heading so a
    failure is never reported as completed work.

    Args:
        migrations: List of migrations that were run
        all_changes: ChangeRecords for every change attempted
        from_version: Original version
        to_version: Target version
        soft_warnings: Non-fatal warnings (e.g. IIIF tile regeneration) to
            surface visibly rather than bury.

    Returns:
        Markdown content for summary
    """
    soft_warnings = soft_warnings or []

    applied = [r.description for r in all_changes if r.status == ChangeStatus.APPLIED]
    failed = [r for r in all_changes if r.status == ChangeStatus.FAILED]

    manual_steps = []
    for migration in migrations:
        manual_steps.extend(migration.get_manual_steps())

    # Categorize applied changes
    categorized = _categorize_changes(applied)

    checklist = f"""---
layout: default
title: Upgrade Summary
---

## Upgrade Summary
- **From:** {from_version}
- **To:** {to_version}
- **Date:** {_get_date()}
- **Automated changes:** {len(applied)}
- **Manual steps:** {len(manual_steps)}
"""
    if failed:
        checklist += f"- **Failed / needs attention:** {len(failed)}\n"
    checklist += "\n## Automated Changes Applied\n\n"

    # Output changes by category
    for category, changes in categorized.items():
        checklist += f"### {category} ({len(changes)} file{'s' if len(changes) != 1 else ''})\n\n"
        for change in changes:
            checklist += f"- [x] {change}\n"
        checklist += "\n"

    # Failures are never ticked and never counted as automated changes.
    if failed:
        checklist += "## Failed / Needs Manual Attention\n\n"
        checklist += (
            "The following changes did not complete automatically. The site "
            "was **not** upgraded to the new version. Resolve these (usually a "
            "transient network problem) and run the upgrade again.\n\n"
        )
        for record in failed:
            checklist += f"- [ ] {record.description}\n"
        checklist += "\n"

    if soft_warnings:
        checklist += "## Completed With Warnings\n\n"
        checklist += (
            "These steps are non-fatal and did not block the upgrade, but you "
            "should check them:\n\n"
        )
        for warning in soft_warnings:
            checklist += f"- {warning}\n"
        checklist += "\n"

    if manual_steps:
        checklist += f"""## Manual Steps Required

Please complete these after merging:

"""
        for i, step in enumerate(manual_steps, 1):
            checklist += f"{i}. {step['description']}"
            if 'doc_url' in step:
                checklist += f" ([guide]({step['doc_url']}))"
            checklist += "\n"
    else:
        checklist += "## No Manual Steps Required\n\nAll changes have been automated!\n"

    checklist += """
## Resources

- [Full Documentation](https://telar.org/docs)
- [CHANGELOG](https://github.com/UCSB-AMPLab/telar/blob/main/CHANGELOG.md)
- [Report Issues](https://github.com/UCSB-AMPLab/telar/issues)
"""

    return checklist


def _regenerate_data_files(repo_root: str) -> Tuple[bool, bool]:
    """
    Regenerate JSON data files and IIIF tiles from CSV sources with validation.

    Runs csv_to_json.py, generate_collections.py, and generate_iiif.py to apply
    validation logic to existing data and regenerate IIIF tiles for local images.

    csv_to_json and generate_collections are HARD: if they fail the derived data
    is stale and the upgrade must not be stamped as complete. generate_iiif is
    SOFT: tile generation can fail (e.g. missing source images) without
    invalidating the upgrade, and is surfaced as a warning instead.

    Args:
        repo_root: Path to repository root

    Returns:
        (csv_ok, iiif_ok). csv_ok is False if the HARD data steps could not be
        run or returned an error. iiif_ok is False if IIIF tile regeneration
        failed (non-fatal). When the scripts are absent, csv_ok is False (the
        caller treats "could not regenerate" as a HARD failure).
    """
    import subprocess

    scripts_dir = os.path.join(repo_root, 'scripts')
    csv_to_json = os.path.join(scripts_dir, 'csv_to_json.py')
    generate_collections = os.path.join(scripts_dir, 'generate_collections.py')

    # Check if scripts exist
    if not os.path.exists(csv_to_json):
        return (False, True)

    try:
        # Run csv_to_json.py (generates objects.json with validation)
        result = subprocess.run(
            ['python3', csv_to_json],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            print(f"  ⚠️  Warning: csv_to_json.py returned error: {result.stderr}")
            return (False, True)

        # Run generate_collections.py (generates story/glossary JSON with validation)
        if os.path.exists(generate_collections):
            result = subprocess.run(
                ['python3', generate_collections],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                print(f"  ⚠️  Warning: generate_collections.py returned error: {result.stderr}")
                return (False, True)

        # Run generate_iiif.py (regenerates IIIF tiles for local images).
        # SOFT: a failure here does not block the upgrade.
        iiif_ok = True
        generate_iiif = os.path.join(scripts_dir, 'generate_iiif.py')
        if os.path.exists(generate_iiif):
            result = subprocess.run(
                ['python3', generate_iiif],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=180  # Longer timeout for tile generation
            )

            if result.returncode != 0:
                print(f"  ⚠️  Warning: generate_iiif.py returned error: {result.stderr}")
                iiif_ok = False

        return (True, iiif_ok)

    except subprocess.TimeoutExpired:
        print("  ⚠️  Warning: Data regeneration timed out")
        return (False, True)
    except Exception as e:
        print(f"  ⚠️  Warning: Data regeneration failed: {e}")
        return (False, True)


def _update_config_version(repo_root: str, new_version: str, new_date: str) -> bool:
    """Stamp telar.version/release_date in _config.yml (the final stamp in
    main()). Thin I/O wrapper over the shared apply_config_version writer in
    migrations.base, so the parsing logic is not duplicated here.

    Returns True if the file was changed, False if it is missing or unchanged.
    """
    config_path = os.path.join(repo_root, '_config.yml')

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        return False

    new_content, modified = apply_config_version(content, new_version, new_date)
    if modified:
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
    return modified


def _get_date() -> str:
    """Get current date in YYYY-MM-DD format."""
    from datetime import datetime
    return datetime.now().strftime('%Y-%m-%d')


def _state_file_path(repo_root: str) -> str:
    return os.path.join(repo_root, UPGRADE_STATE_FILE)


def _read_state_file(repo_root: str) -> Optional[dict]:
    """Read a leftover upgrade state marker, if any."""
    path = _state_file_path(repo_root)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_failed_state(repo_root: str, from_version: str, to_version: str,
                        failed: List[ChangeRecord]) -> None:
    """Write the partial-state marker when an upgrade aborts on HARD failure.

    Records what failed so a re-run can tell the user it is resuming. The site
    was left at the old version (unstamped), so re-running re-applies the same
    pinned migrations from scratch.
    """
    data = {
        'from_version': from_version,
        'to_version': to_version,
        'status': 'failed',
        'failed_files': [r.description for r in failed],
        'timestamp': _get_date(),
    }
    try:
        with open(_state_file_path(repo_root), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def _clear_state_file(repo_root: str) -> None:
    path = _state_file_path(repo_root)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


# Exit codes
EXIT_OK = 0            # upgrade completed (or nothing to do / dry run)
EXIT_PRECONDITION = 1  # could not start (bad repo, cancelled, no migrations)
EXIT_HARD_FAILURE = 2  # a required step failed; site left unchanged/unstamped


def _write_failure_summary(repo_root: str, migrations: List[BaseMigration],
                           all_changes: List[ChangeRecord], from_version: str) -> None:
    """Write UPGRADE_SUMMARY.md and the state marker for a failed upgrade."""
    failed = [r for r in all_changes if r.status == ChangeStatus.FAILED]
    summary = generate_checklist(migrations, all_changes, from_version, LATEST_VERSION)
    summary_path = os.path.join(repo_root, 'UPGRADE_SUMMARY.md')
    with open(summary_path, 'w') as f:
        f.write(summary)
    _write_failed_state(repo_root, from_version, LATEST_VERSION, failed)


def main():
    """Main upgrade orchestrator."""
    parser = argparse.ArgumentParser(description='Upgrade Telar to the latest version')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying them')
    parser.add_argument('--repo-root', default=None,
                        help='Path to the Telar site to upgrade (default: current directory). '
                             'Lets the script run from a separate location, e.g. a CI temp dir.')
    args = parser.parse_args()

    # The site being upgraded — distinct from where this script lives.
    repo_root = os.path.abspath(args.repo_root) if args.repo_root else os.getcwd()
    lang = _get_lang(repo_root)

    print("=" * 60)
    print(get_message(lang, 'upgrade_title'))
    print("=" * 60)

    # Inform the user if a previous upgrade left a failed-state marker.
    prior_state = _read_state_file(repo_root)
    if prior_state and prior_state.get('status') == 'failed':
        print("\n" + get_message(lang, 'prev_upgrade_incomplete', prior_state.get('to_version', '?')))
        print(get_message(lang, 'prev_upgrade_rerun'))

    # Check for uncommitted changes (skip the prompt when there is no terminal,
    # e.g. in CI, to avoid an EOFError; the workflow's branch model is the gate).
    git_dir = os.path.join(repo_root, '.git')
    if os.path.exists(git_dir):
        import subprocess
        try:
            result = subprocess.run(['git', 'status', '--porcelain'],
                                    cwd=repo_root, capture_output=True, text=True)
            if result.stdout.strip() and not args.dry_run:
                print('\n' + get_message(lang, 'uncommitted_warning'))
                print(get_message(lang, 'uncommitted_recommend'))
                if sys.stdin.isatty():
                    response = input(get_message(lang, 'continue_anyway'))
                    if response.lower() != 'y':
                        print(get_message(lang, 'upgrade_cancelled'))
                        return EXIT_PRECONDITION
                else:
                    print(get_message(lang, 'no_tty_continue'))
        except Exception:
            pass  # Git not available or other error, continue anyway

    # Detect current version
    print('\n' + get_message(lang, 'detecting_version'))
    from_version = detect_current_version(repo_root)

    if not from_version:
        return EXIT_PRECONDITION

    print(get_message(lang, 'current_version', from_version))
    print(get_message(lang, 'target_version', LATEST_VERSION))

    # Check if already up to date
    if from_version == LATEST_VERSION:
        print('\n' + get_message(lang, 'already_updated'))
        _clear_state_file(repo_root)
        return EXIT_OK

    # Get migrations to run
    migrations = get_migration_path(from_version, repo_root)

    if not migrations:
        print('\n' + get_message(lang, 'no_migrations', from_version, LATEST_VERSION))
        print(get_message(lang, 'unsupported_note'))
        return EXIT_PRECONDITION

    print('\n' + get_message(lang, 'migrations_to_apply', len(migrations)))
    for migration in migrations:
        print(f"  • {migration}")

    if args.dry_run:
        print('\n' + get_message(lang, 'dry_run_mode'))

    # Run migrations
    print('\n' + get_message(lang, 'applying_migrations'))
    all_changes = run_migrations(migrations, dry_run=args.dry_run)

    if args.dry_run:
        print('\n' + get_message(lang, 'dry_run_complete'))
        print(get_message(lang, 'dry_run_instruction'))
        return EXIT_OK

    # Fail closed: if any framework-file step hard-failed, do NOT stamp the
    # version, do NOT write UPGRADE_VERSION.txt. The site keeps its old version
    # so a re-run retries the same migrations.
    hard_failures = [r for r in all_changes
                     if r.status == ChangeStatus.FAILED and r.severity == "hard"]
    if hard_failures:
        print('\n' + get_message(lang, 'upgrade_failed_steps', len(hard_failures)))
        print(get_message(lang, 'upgrade_not_applied'))
        print(get_message(lang, 'transient_retry'))
        _write_failure_summary(repo_root, migrations, all_changes, from_version)
        print(get_message(lang, 'see_summary_failures'))
        return EXIT_HARD_FAILURE

    # Regenerate data files and IIIF tiles. csv/collections failure is HARD.
    print('\n' + get_message(lang, 'regenerating_data'))
    csv_ok, iiif_ok = _regenerate_data_files(repo_root)
    if not csv_ok:
        print('\n' + get_message(lang, 'upgrade_failed_data'))
        print(get_message(lang, 'upgrade_not_applied'))
        all_changes.append(ChangeRecord(
            description="Data regeneration (csv_to_json / generate_collections) failed. "
                        "Run the data scripts manually and re-run the upgrade.",
            status=ChangeStatus.FAILED,
            severity="hard",
        ))
        _write_failure_summary(repo_root, migrations, all_changes, from_version)
        print(get_message(lang, 'see_summary_details'))
        return EXIT_HARD_FAILURE
    print(get_message(lang, 'data_files_regenerated'))

    soft_warnings = []
    if not iiif_ok:
        soft_warnings.append(
            "IIIF tile regeneration reported an error. Self-hosted object images may "
            "not display until you run scripts/generate_iiif.py successfully. This did "
            "not block the upgrade."
        )

    # All required steps succeeded — stamp the version exactly once.
    print('\n' + get_message(lang, 'updating_config'))
    if _update_config_version(repo_root, LATEST_VERSION, _get_date()):
        print(get_message(lang, 'config_updated', LATEST_VERSION))
    else:
        print(get_message(lang, 'config_update_warning'))

    # Generate and write summary
    summary = generate_checklist(migrations, all_changes, from_version, LATEST_VERSION,
                                 soft_warnings=soft_warnings)
    summary_path = os.path.join(repo_root, 'UPGRADE_SUMMARY.md')
    with open(summary_path, 'w') as f:
        f.write(summary)

    print('\n' + get_message(lang, 'upgrade_complete'))
    print('  ' + get_message(lang, 'created_summary'))

    # Write version for GitHub Actions (only reached on full success).
    version_file = os.path.join(repo_root, 'UPGRADE_VERSION.txt')
    with open(version_file, 'w') as f:
        f.write(LATEST_VERSION)

    # Clear any leftover failed-state marker from a previous attempt.
    _clear_state_file(repo_root)

    print(f"\nPlease review UPGRADE_SUMMARY.md for any manual steps.")

    return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
