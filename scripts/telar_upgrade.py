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

This is the engine, not the entry point. A site's `scripts/upgrade.py` is a
launcher that downloads a verified copy of this file for the newest release
and runs it from a temp dir, so the version of this module that runs is
never the one sitting in the site. See scripts/upgrade.py.

Version: v1.8.0

Usage:
    python scripts/telar_upgrade.py              # Normal upgrade
    python scripts/telar_upgrade.py --dry-run    # Preview without applying
"""

import os
import re
import shutil
import sys
import json
import yaml
import argparse
from typing import List, Optional

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from migrations.base import (
    BaseMigration, ChangeCategory, ChangeRecord, ChangeStatus,
    UPGRADE_STATE_FILE, apply_config_version,
    coerce_change,
    is_flagged, is_hard_failure,
)
from migrations.messages import get_message
from migrations.discovery import discover_migrations
from migrations.records import LAUNCHER_MARKER

# The shared helpers, the summary and the data regeneration live in the three
# telar_upgrade_* modules beside this one, which the tooling tarball carries
# with it. Every name is imported back here: main() calls them from this
# module, and tests reach them through it.
from telar_upgrade_common import (  # noqa: F401
    PROTECTED_PREREQUISITE_EXIT, _get_date, _get_lang,
)
from telar_upgrade_report import (  # noqa: F401
    _PATH_IN_DESCRIPTION, _categorize_changes, _category_from_description,
    _visible_manual_steps, generate_checklist,
)
from telar_upgrade_regen import (  # noqa: F401
    _REGENERATION_IMPORTS, _ensure_regeneration_dependencies,
    _missing_regeneration_imports, _regenerate_data_files,
)

# The chain, read off the modules in migrations/ rather than hand-listed.
#
# The chain and LATEST_VERSION both come from discovery, so there is one
# source and no hand-kept list can disagree with what ships. Discovery
# refuses an ambiguous chain instead of running a wrong one; see
# migrations/discovery.py for what it will not accept.
#
# Both names stay module-level and rebindable: run_upgrade.py narrows them to
# run a chain part-way, and the tests substitute short chains of their own.
MIGRATIONS = discover_migrations()

# Where a completed upgrade lands, which is where the chain ends.
LATEST_VERSION = MIGRATIONS[-1].to_version

# And when that release was published. `telar.release_date` is the date of
# the release the site is on, the value the Compositor writes too, so two
# sites on one version agree and the same site upgraded twice produces the
# same file.
#
# None while a release is still being built, since its date is not a fact
# until it is tagged; `_stamp_date` then uses the clock and says so.
LATEST_RELEASE_DATE = getattr(MIGRATIONS[-1], 'release_date', None)


# The exact grammar for a Telar version in _config.yml: an optional single
# git-tag prefix over MAJOR.MINOR.PATCH, with the -beta suffix preserved
# because "0.9.4-beta" and "0.9.4" are distinct chain keys. Components reject
# leading zeros, so "01.6.2" cannot pass as a version that matches nothing.
# The prefix quantifier is `?`, not `*`: repeated prefixes ("vv1.6.2") stay
# outside the grammar rather than collapsing onto a real version.
_VERSION_RE = re.compile(
    r'[vV]?'
    r'(?P<canonical>'
    r'(?:0|[1-9][0-9]*)\.'
    r'(?:0|[1-9][0-9]*)\.'
    r'(?:0|[1-9][0-9]*)'
    r'(?:-beta)?'
    r')'
)


def _canonical_version(value) -> Optional[str]:
    """Canonicalise a version string to the bare form the chain dispatches on.

    An accepted spelling returns its bare form, with any git-tag prefix
    dropped and any -beta suffix kept; anything outside the grammar returns
    None. Matching is fullmatch, not a `^...$` match: `$` also matches before
    a trailing newline, so a version with one would be silently trimmed.

    Non-strings have no canonical form. An unquoted `version: 1.6` decodes to
    a float, which has no .strip()/.lower() and cannot reach the regex.
    """
    if not isinstance(value, str):
        return None
    match = _VERSION_RE.fullmatch(value)
    return match.group('canonical') if match else None


def detect_current_version(repo_root: str) -> Optional[str]:
    """
    Detect current Telar version from _config.yml.

    The value is canonicalised here, at ingestion, so every consumer sees one
    form: main()'s already-up-to-date check runs before get_migration_path, so
    normalising at dispatch would still report a v-prefixed current site as
    unsupported. Values outside the grammar are reported and returned
    unchanged rather than repaired — a repair guesses at intent and can name a
    different real version — and cannot reach a migration or any file on disk,
    since they match no from_version and every writer sits downstream of that.

    Args:
        repo_root: Path to repository root

    Returns:
        One of three things, and callers that only handle two will be wrong
        about the third: the canonical version string (e.g. "0.2.0-beta");
        None when there is no _config.yml to read, which is a precondition
        failure rather than a version; or the raw value unchanged — of any
        type YAML produced — when it is outside the grammar. The annotation
        cannot say this, since the third case is not Optional[str] at all.
    """
    config_path = os.path.join(repo_root, '_config.yml')

    if not os.path.exists(config_path):
        print(get_message(_get_lang(repo_root), 'config_not_found'))
        return None

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Try to get version from telar.version. Guard against a bare `telar:`
        # key (parses to None) or a non-dict telar section, which would otherwise
        # raise TypeError on subscripting rather than falling back cleanly.
        telar_section = config.get('telar') if isinstance(config, dict) else None
        if isinstance(telar_section, dict) and 'version' in telar_section:
            raw_version = telar_section['version']
            canonical = _canonical_version(raw_version)
            if canonical is not None:
                return canonical

            lang = _get_lang(repo_root)
            if isinstance(raw_version, str):
                print(get_message(lang, 'version_unrecognised', raw_version))
            else:
                print(get_message(lang, 'version_not_text', repr(raw_version)))
            print('   ' + get_message(lang, 'version_grammar'))
            return raw_version

        # If no version found, assume 0.2.0-beta (before versioning was added)
        print(get_message(_get_lang(repo_root), 'version_missing'))
        return "0.2.0-beta"

    except (yaml.YAMLError, KeyError, TypeError, AttributeError) as e:
        print(get_message(_get_lang(repo_root), 'config_read_error', e))
        return None


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

        # Strict chaining: a migration joins the chain only when the version
        # reached so far is one it can be entered from, so a version gap (a
        # 0.4.2-beta site, or a v-prefix mismatch) ends in "no path" rather
        # than a wrong chain.
        if current_version in migration.entry_versions:
            # A migration covering several releases is entered from whichever
            # one the site is on; pin it before asking anything of the
            # migration, so both its applicability check and the summary see
            # the real starting version. For a single-hop migration this
            # assigns the value it already had.
            migration.from_version = current_version

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


# The chain runner and any migration that runs other migrations internally
# must classify a change the same way, so the rule lives in base.py.
_coerce_record = coerce_change


def run_migrations(migrations: List[BaseMigration], dry_run: bool = False) -> List[ChangeRecord]:
    """
    Run all migrations in sequence.

    Stops the chain as soon as a migration reports a HARD failure, so a failed
    fetch in one step does not let later steps run against a half-updated tree.

    A SOFT failure does not stop it. That is how a structural fetch failure —
    a path absent from the release the migration pins to — reaches the summary
    without stranding the site on a step no re-run can get past.

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
            print('  ' + get_message(_get_lang(migration.repo_root), 'dry_run_would_apply'))
            continue

        try:
            records = [_coerce_record(c) for c in migration.apply()]
        except Exception as e:
            # An unexpected error (not a handled fetch failure) is a HARD
            # failure: record it and stop the chain so the upgrade fails closed.
            print('  ' + get_message(_get_lang(migration.repo_root), 'migration_error', e))
            all_changes.append(ChangeRecord(
                description=get_message(
                    _get_lang(migration.repo_root), 'record_migration_aborted',
                    migration.from_version, migration.to_version, e),
                status=ChangeStatus.FAILED,
                severity="hard",
            ))
            break

        all_changes.extend(records)

        for record in records:
            mark = "✓" if record.status == ChangeStatus.APPLIED else "✗"
            print(f"  {mark} {record.description}")

        # A HARD failure in this migration stops the chain.
        if any(is_hard_failure(r) for r in records):
            print('  ' + get_message(_get_lang(migration.repo_root), 'migration_stopped'))
            break

    return all_changes


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


def _site_uses_google_sheets(repo_root: str) -> bool:
    """Whether this site pulls its content from a published Google Sheet.

    Read for one purpose: deciding whether a manual step tagged
    `google-sheets` is addressed to this site's owner. A config that cannot
    be read answers False rather than raising, because a summary is not
    worth failing an upgrade over -- and see `_visible_manual_steps` for
    why False is the safe direction here.
    """
    config_path = os.path.join(repo_root, '_config.yml')
    try:
        with open(config_path, 'r', encoding='utf-8') as handle:
            config = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return False
    section = config.get('google_sheets')
    return bool(isinstance(section, dict) and section.get('enabled'))


def _stamp_date(lang: str) -> str:
    """The date to write beside the version in `_config.yml`.

    The release's date, so that both upgrade routes write the same value
    and a site upgraded twice produces the same file. Falls back to the
    clock only for a release that is not tagged yet, and says so.
    """
    if LATEST_RELEASE_DATE:
        return LATEST_RELEASE_DATE
    print('  ' + get_message(lang, 'stamp_date_unknown', LATEST_VERSION))
    return _get_date()


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
    keeps whatever version the last completed migration stamped, so a re-run
    continues from there rather than starting the chain over.
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
EXIT_HARD_FAILURE = 2  # a required step failed; the chain stopped where it stood


def _report_state_after_failure(repo_root: str, lang: str, from_version: str) -> None:
    """Say where the site actually stands, which is not always where it started.

    Each migration stamps its own to_version as it completes, so a chain that
    stops part-way leaves the site at the last hop that finished rather than at
    the version it began on. Telling the user nothing changed suppresses the
    re-run that would carry it the rest of the way, and leaves a subsequently
    failing build looking unrelated to the upgrade.
    """
    reached = detect_current_version(repo_root)
    if reached and reached != from_version:
        print(get_message(lang, 'upgrade_reached_version', reached, LATEST_VERSION))
    else:
        print(get_message(lang, 'upgrade_not_applied'))


def _write_failure_summary(repo_root: str, migrations: List[BaseMigration],
                           all_changes: List[ChangeRecord], from_version: str) -> None:
    """Write UPGRADE_SUMMARY.md and the state marker for a failed upgrade."""
    failed = [r for r in all_changes if r.status == ChangeStatus.FAILED]
    summary = generate_checklist(migrations, all_changes, from_version, LATEST_VERSION,
                                 lang=_get_lang(repo_root))
    summary_path = os.path.join(repo_root, 'UPGRADE_SUMMARY.md')
    with open(summary_path, 'w') as f:
        f.write(summary)
    _write_failed_state(repo_root, from_version, LATEST_VERSION, failed)


def _site_runs_the_launcher(repo_root: str) -> bool:
    """Whether the site's own scripts/upgrade.py carries LAUNCHER_MARKER."""
    path = os.path.join(repo_root, 'scripts', 'upgrade.py')
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            return LAUNCHER_MARKER in handle.read()
    except OSError:
        return False


def _retire_local_migrations(repo_root: str, lang: str) -> List[ChangeRecord]:
    """Remove the site's own scripts/migrations/, once nothing needs it.

    A site that runs the launcher never executes the migrations sitting in it:
    the launcher downloads a verified engine and its migrations into a temp
    dir. What is left in the site is a directory of modules that cannot run,
    and whose version numbers invite the belief that they can.

    Three conditions, each of which has a failure behind it.

    Deleting only after the whole upgrade has succeeded: the framework install
    clears its rollback state as soon as it completes, and this directory was
    never among the paths it backed up. A deletion inside a migration, followed
    by a hard failure in dependency ensure or data regeneration, would leave a
    site stamped at its old version with no local engine and nothing able to
    put it back.

    Deleting only when the site holds the launcher: without it, the site's
    scripts/upgrade.py is an older copy of this engine and the directory is
    the only thing it can run. Removing it would strand the site rather than
    tidy it.

    Deleting only when this engine is running from outside the site: otherwise
    it removes the modules it imported moments ago, which is survivable in the
    running process and indefensible in a file tree.

    Soft-fail throughout. A tidy-up that has to happen cannot be a reason a
    completed upgrade reports failure.
    """
    directory = os.path.join(repo_root, 'scripts', 'migrations')
    if not os.path.isdir(directory):
        return []
    if not _site_runs_the_launcher(repo_root):
        return []
    engine_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.abspath(os.path.join(repo_root, 'scripts')) == engine_dir:
        return []

    try:
        shutil.rmtree(directory)
    except OSError as error:
        print('  ' + get_message(lang, 'retire_migrations_warning', error))
        return [ChangeRecord(
            description=get_message(lang, 'retire_migrations_warning', error),
            status=ChangeStatus.FAILED,
            severity='soft',
            category=ChangeCategory.SCRIPTS,
        )]

    print('  ' + get_message(lang, 'retired_migrations'))
    return [ChangeRecord(
        description=get_message(lang, 'retired_migrations'),
        status=ChangeStatus.APPLIED,
        severity='soft',
        category=ChangeCategory.SCRIPTS,
    )]


def _report_prior_failure(repo_root: str, lang: str) -> None:
    """Say so if a previous upgrade left a failed-state marker."""
    prior_state = _read_state_file(repo_root)
    if prior_state and prior_state.get('status') == 'failed':
        print("\n" + get_message(lang, 'prev_upgrade_incomplete', prior_state.get('to_version', '?')))
        print(get_message(lang, 'prev_upgrade_rerun'))


def _uncommitted_changes_accepted(repo_root: str, lang: str, dry_run: bool) -> bool:
    """Whether the run may go ahead over uncommitted changes in the site.

    False only when a person at a terminal was asked and declined. Without a
    terminal, e.g. in CI, there is no prompt, since `input` would raise
    EOFError, and the workflow's branch model is the gate. A dry run changes
    nothing, so it is not asked. Git missing or failing is not a reason to
    stop.
    """
    if not os.path.exists(os.path.join(repo_root, '.git')):
        return True
    import subprocess
    try:
        result = subprocess.run(['git', 'status', '--porcelain'],
                                cwd=repo_root, capture_output=True, text=True)
        if result.stdout.strip() and not dry_run:
            print('\n' + get_message(lang, 'uncommitted_warning'))
            print(get_message(lang, 'uncommitted_recommend'))
            if sys.stdin.isatty():
                response = input(get_message(lang, 'continue_anyway'))
                if response.lower() != 'y':
                    print(get_message(lang, 'upgrade_cancelled'))
                    return False
            else:
                print(get_message(lang, 'no_tty_continue'))
    except Exception:
        pass  # Git not available or other error, continue anyway
    return True


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

    _report_prior_failure(repo_root, lang)
    if not _uncommitted_changes_accepted(repo_root, lang, args.dry_run):
        return EXIT_PRECONDITION

    # Detect current version
    print('\n' + get_message(lang, 'detecting_version'))
    from_version = detect_current_version(repo_root)

    if not from_version:
        return EXIT_PRECONDITION

    # from_version is canonical, or it is a value outside the grammar passed
    # through unchanged. The second case is deliberate and is not repaired
    # here: it matches no migration's entry version and no LATEST_VERSION, so
    # it reaches `no_migrations` below, which names the value and stops. The
    # alternative -- guessing at what the site meant -- can name a different
    # real version and upgrade a site along a chain it is not on.

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

    # Migrations import the scripts/telar package, and the upgrade.yml a site
    # carries may install only part of requirements.txt, so the dependencies
    # are ensured before the first migration as well as before regeneration.
    # A failure here is not final: the check before regeneration repeats it
    # and stops the run there.
    _ensure_regeneration_dependencies(repo_root)

    # Run migrations
    print('\n' + get_message(lang, 'applying_migrations'))
    all_changes = run_migrations(migrations, dry_run=args.dry_run)

    if args.dry_run:
        print('\n' + get_message(lang, 'dry_run_complete'))
        print(get_message(lang, 'dry_run_instruction'))
        return EXIT_OK

    # Fail closed: if any framework-file step hard-failed, the version is not
    # stamped and UPGRADE_VERSION.txt is not written. The site keeps its old
    # version, so a re-run retries the same migrations.
    hard_failures = [r for r in all_changes if is_hard_failure(r)]
    if hard_failures:
        print('\n' + get_message(lang, 'upgrade_failed_steps', len(hard_failures)))
        _report_state_after_failure(repo_root, lang, from_version)
        print(get_message(lang, 'transient_retry'))
        _write_failure_summary(repo_root, migrations, all_changes, from_version)
        print(get_message(lang, 'see_summary_failures'))
        return EXIT_HARD_FAILURE

    # Regenerate data files and IIIF tiles. csv/collections failure is HARD.
    print('\n' + get_message(lang, 'regenerating_data'))

    # Regeneration subprocess-runs scripts that import the scripts/telar package;
    # its dependencies must be importable first or those scripts fail closed.
    # Treat still-missing modules as the same HARD failure as a regeneration error:
    # returning here leaves the version unstamped so a re-run retries.
    deps_ok, missing_deps = _ensure_regeneration_dependencies(repo_root)
    if not deps_ok:
        print('\n' + get_message(lang, 'upgrade_failed_data'))
        _report_state_after_failure(repo_root, lang, from_version)
        all_changes.append(ChangeRecord(
            description=get_message(lang, 'record_deps_missing',
                                    ", ".join(missing_deps)),
            status=ChangeStatus.FAILED,
            severity="hard",
        ))
        _write_failure_summary(repo_root, migrations, all_changes, from_version)
        print(get_message(lang, 'see_summary_details'))
        return EXIT_HARD_FAILURE

    csv_ok, iiif_ok, protected_blocked = _regenerate_data_files(repo_root)
    if not csv_ok:
        print('\n' + get_message(lang, 'upgrade_failed_data'))
        _report_state_after_failure(repo_root, lang, from_version)
        all_changes.append(ChangeRecord(
            description=get_message(lang, 'record_regeneration_failed'),
            status=ChangeStatus.FAILED,
            severity="hard",
        ))
        _write_failure_summary(repo_root, migrations, all_changes, from_version)
        print(get_message(lang, 'see_summary_details'))
        return EXIT_HARD_FAILURE
    print(get_message(lang, 'data_files_regenerated'))

    if protected_blocked:
        # Flagged, not failed: the data regenerated, and the thing left
        # undone is a workflow file this tool is not permitted to write.
        # Aborting here would leave the site on its old version and stop
        # nothing, because the build refuses on the same grounds.
        all_changes.append(ChangeRecord(
            description=get_message(lang, 'record_protected_unencryptable'),
            status=ChangeStatus.FAILED,
            severity="author",
        ))

    soft_warnings = []
    if not iiif_ok:
        soft_warnings.append(
            "IIIF tile regeneration reported an error. Self-hosted object images may "
            "not display until you run scripts/generate_iiif.py successfully. This did "
            "not block the upgrade."
        )

    # All required steps succeeded — stamp the version exactly once.
    print('\n' + get_message(lang, 'updating_config'))
    stamp_date = _stamp_date(lang)
    _update_config_version(repo_root, LATEST_VERSION, stamp_date)

    # Read the stamp back rather than trusting the writer's return value.
    # The writer reports whether it changed the file, which is not the same
    # question: a _config.yml with no `telar:` section is left alone by
    # design, and every artefact below signs the run as complete at
    # LATEST_VERSION whether or not the file says so.
    stamp_steps = []
    if detect_current_version(repo_root) == LATEST_VERSION:
        print(get_message(lang, 'config_updated', LATEST_VERSION))
    else:
        print(get_message(lang, 'config_update_warning'))
        # A manual step rather than a failure: the content is upgraded and a
        # re-run would redo all of it. Manual steps are also the part of the
        # summary the Actions route copies into the issue the user reads.
        stamp_steps.append({
            'description': get_message(lang, 'manual_step_record_version',
                                       LATEST_VERSION, stamp_date),
            'audience': 'all',
        })

    # Only now, with the whole upgrade behind us. See _retire_local_migrations.
    all_changes.extend(_retire_local_migrations(repo_root, lang))

    # Generate and write summary
    summary = generate_checklist(
        migrations, all_changes, from_version, LATEST_VERSION,
        soft_warnings=soft_warnings, lang=lang,
        sheets_enabled=_site_uses_google_sheets(repo_root),
        extra_manual_steps=stamp_steps)
    summary_path = os.path.join(repo_root, 'UPGRADE_SUMMARY.md')
    with open(summary_path, 'w') as f:
        f.write(summary)

    print('\n' + get_message(lang, 'upgrade_complete'))
    print('  ' + get_message(lang, 'created_summary'))

    # A structural fetch failure does not stop the chain, so this is the only
    # place the run says it happened. Printed after 'upgrade_complete' because
    # the upgrade did complete — the site is at the latest version, carrying a
    # flag — and printing it before would read as the abort it is not.
    flagged = [r for r in all_changes if is_flagged(r)]
    if flagged:
        print('\n' + get_message(lang, 'upgrade_completed_with_flags',
                                 len(flagged), LATEST_VERSION))

    # Write version for GitHub Actions (only reached on full success).
    version_file = os.path.join(repo_root, 'UPGRADE_VERSION.txt')
    with open(version_file, 'w') as f:
        f.write(LATEST_VERSION)

    # Clear any leftover failed-state marker from a previous attempt.
    _clear_state_file(repo_root)

    print('\n' + get_message(lang, 'review_summary'))

    return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
