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

Version: v0.8.0-beta

Usage:
    python scripts/upgrade.py              # Normal upgrade
    python scripts/upgrade.py --dry-run    # Preview changes without applying
"""

import os
import sys
import yaml
import argparse
from typing import List, Optional

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from migrations.base import BaseMigration
from migrations.v020_to_v030 import Migration020to030
from migrations.v030_to_v031 import Migration030to031
from migrations.v031_to_v032 import Migration031to032
from migrations.v032_to_v033 import Migration032to033
from migrations.v033_to_v034 import Migration033to034
from migrations.v034_to_v040 import Migration034to040
from migrations.v040_to_v041 import Migration040to041
from migrations.v041_to_v042 import Migration041to042
from migrations.v043_to_v050 import Migration043to050
from migrations.v050_to_v060 import Migration050to060
from migrations.v060_to_v061 import Migration060to061
from migrations.v061_to_v062 import Migration061to062
from migrations.v062_to_v063 import Migration062to063
from migrations.v063_to_v070 import Migration063to070
from migrations.v070_to_v080 import Migration070to080


# Latest version
LATEST_VERSION = "0.8.0-beta"

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
    Migration043to050,
    Migration050to060,
    Migration060to061,
    Migration061to062,
    Migration062to063,
    Migration063to070,
    Migration070to080,
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
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Try to get version from telar.version
        if 'telar' in config and 'version' in config['telar']:
            return config['telar']['version']

        # If no version found, assume v0.2.0 (before versioning was added)
        print("Warning: No version found in _config.yml, assuming v0.2.0-beta")
        return "0.2.0-beta"

    except (yaml.YAMLError, KeyError) as e:
        print(f"❌ Error reading _config.yml: {e}")
        return None


def get_migration_path(from_version: str) -> List[BaseMigration]:
    """
    Get list of migrations to run from current version to latest.

    Args:
        from_version: Current version string

    Returns:
        List of migration instances to run in order
    """
    repo_root = os.getcwd()
    migrations_to_run = []

    for MigrationClass in MIGRATIONS:
        migration = MigrationClass(repo_root)

        # Check if this migration is in the upgrade path
        if migration.from_version == from_version or migrations_to_run:
            if migration.check_applicable():
                migrations_to_run.append(migration)
                # Update from_version for next iteration
                from_version = migration.to_version

    return migrations_to_run


def run_migrations(migrations: List[BaseMigration], dry_run: bool = False) -> List[str]:
    """
    Run all migrations in sequence.

    Args:
        migrations: List of migration instances
        dry_run: If True, don't actually apply changes

    Returns:
        List of all changes made
    """
    all_changes = []

    for migration in migrations:
        print(f"\n{migration}")

        if dry_run:
            print("  [DRY RUN] Would apply this migration")
            continue

        try:
            changes = migration.apply()
            all_changes.extend(changes)

            for change in changes:
                print(f"  ✓ {change}")

        except Exception as e:
            print(f"  ✗ Error: {e}")
            raise

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


def generate_checklist(migrations: List[BaseMigration], all_changes: List[str], from_version: str, to_version: str) -> str:
    """
    Generate UPGRADE_SUMMARY.md content (without YAML frontmatter).

    Args:
        migrations: List of migrations that were run
        all_changes: List of all automated changes made
        from_version: Original version
        to_version: Target version

    Returns:
        Markdown content for summary
    """
    manual_steps = []
    for migration in migrations:
        manual_steps.extend(migration.get_manual_steps())

    # Categorize changes
    categorized = _categorize_changes(all_changes)

    checklist = f"""---
layout: default
title: Upgrade Summary
---

## Upgrade Summary
- **From:** {from_version}
- **To:** {to_version}
- **Date:** {_get_date()}
- **Automated changes:** {len(all_changes)}
- **Manual steps:** {len(manual_steps)}

## Automated Changes Applied

"""

    # Output changes by category
    for category, changes in categorized.items():
        checklist += f"### {category} ({len(changes)} file{'s' if len(changes) != 1 else ''})\n\n"
        for change in changes:
            checklist += f"- [x] {change}\n"
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


def _regenerate_data_files(repo_root: str) -> bool:
    """
    Regenerate JSON data files and IIIF tiles from CSV sources with validation.

    Runs csv_to_json.py, generate_collections.py, and generate_iiif.py to apply
    validation logic to existing data and regenerate IIIF tiles for local images.

    Args:
        repo_root: Path to repository root

    Returns:
        True if regeneration succeeded, False if scripts not found or failed
    """
    import subprocess

    scripts_dir = os.path.join(repo_root, 'scripts')
    csv_to_json = os.path.join(scripts_dir, 'csv_to_json.py')
    generate_collections = os.path.join(scripts_dir, 'generate_collections.py')

    # Check if scripts exist
    if not os.path.exists(csv_to_json):
        return False

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
            return False

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
                return False

        # Run generate_iiif.py (regenerates IIIF tiles for local images)
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
                # Don't return False - IIIF generation failure shouldn't stop upgrade

        return True

    except subprocess.TimeoutExpired:
        print("  ⚠️  Warning: Data regeneration timed out")
        return False
    except Exception as e:
        print(f"  ⚠️  Warning: Data regeneration failed: {e}")
        return False


def _update_config_version(repo_root: str, new_version: str, new_date: str) -> bool:
    """
    Update telar.version and telar.release_date in _config.yml.

    Uses text-based editing to preserve formatting and comments.

    Args:
        repo_root: Path to repository root
        new_version: New version string (e.g., "0.3.4-beta")
        new_date: New release date (e.g., "2025-10-29")

    Returns:
        True if config was updated, False if file doesn't exist or telar section not found
    """
    config_path = os.path.join(repo_root, '_config.yml')

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        return False

    lines = content.split('\n')
    modified = False
    in_telar_section = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detect telar section start
        if line.startswith('telar:'):
            in_telar_section = True
            continue

        # Inside telar section
        if in_telar_section:
            # Exit when we hit a non-indented line that's not blank
            if line and not line.startswith('  ') and not line.startswith('\t') and stripped:
                in_telar_section = False
                continue

            # Update version line
            if stripped.startswith('version:'):
                # Preserve indentation
                indent = line[:len(line) - len(line.lstrip())]
                lines[i] = f'{indent}version: "{new_version}"'
                modified = True

            # Update release_date line
            if stripped.startswith('release_date:'):
                # Preserve indentation
                indent = line[:len(line) - len(line.lstrip())]
                lines[i] = f'{indent}release_date: "{new_date}"'
                modified = True

    if modified:
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return True

    return False


def _get_date() -> str:
    """Get current date in YYYY-MM-DD format."""
    from datetime import datetime
    return datetime.now().strftime('%Y-%m-%d')


def main():
    """Main upgrade orchestrator."""
    parser = argparse.ArgumentParser(description='Upgrade Telar to the latest version')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying them')
    args = parser.parse_args()

    print("=" * 60)
    print("Telar Upgrade Script")
    print("=" * 60)

    # Get repository root (where script is being run from)
    repo_root = os.getcwd()

    # Check for uncommitted changes
    if os.path.exists('.git'):
        import subprocess
        try:
            result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
            if result.stdout.strip() and not args.dry_run:
                print("\n⚠️  Warning: You have uncommitted changes.")
                print("It's recommended to commit or stash your changes before upgrading.")
                response = input("Continue anyway? (y/N): ")
                if response.lower() != 'y':
                    print("Upgrade cancelled.")
                    return 1
        except:
            pass  # Git not available or other error, continue anyway

    # Detect current version
    print(f"\nDetecting current version...")
    from_version = detect_current_version(repo_root)

    if not from_version:
        return 1

    print(f"Current version: {from_version}")
    print(f"Target version:  {LATEST_VERSION}")

    # Check if already up to date
    if from_version == LATEST_VERSION:
        print("\n✓ Already at latest version!")
        return 0

    # Get migrations to run
    migrations = get_migration_path(from_version)

    if not migrations:
        print(f"\nNo migrations found from {from_version} to {LATEST_VERSION}")
        print("This might indicate an unsupported version or that you're already up to date.")
        return 1

    print(f"\nMigrations to apply: {len(migrations)}")
    for migration in migrations:
        print(f"  • {migration}")

    if args.dry_run:
        print("\n[DRY RUN MODE - No changes will be made]")

    # Run migrations
    print("\nApplying migrations...")
    all_changes = run_migrations(migrations, dry_run=args.dry_run)

    if args.dry_run:
        print("\n[DRY RUN COMPLETE]")
        print("Run without --dry-run to apply these changes.")
        return 0

    # Update _config.yml version
    print("\nUpdating _config.yml with new version...")
    if _update_config_version(repo_root, LATEST_VERSION, _get_date()):
        print(f"✓ Updated _config.yml to version {LATEST_VERSION}")
    else:
        print("⚠️  Warning: Could not update _config.yml version")

    # Regenerate data files and IIIF tiles
    print("\nRegenerating data files and IIIF tiles...")
    if _regenerate_data_files(repo_root):
        print("✓ Regenerated data files and IIIF tiles")
    else:
        print("⚠️  Warning: Could not regenerate data files (scripts may not exist)")

    # Generate summary
    summary = generate_checklist(migrations, all_changes, from_version, LATEST_VERSION)

    # Write summary
    summary_path = os.path.join(repo_root, 'UPGRADE_SUMMARY.md')
    with open(summary_path, 'w') as f:
        f.write(summary)

    print(f"\n✓ Upgrade complete!")
    print(f"  Created: UPGRADE_SUMMARY.md")

    # Write version for GitHub Actions
    version_file = os.path.join(repo_root, 'UPGRADE_VERSION.txt')
    with open(version_file, 'w') as f:
        f.write(LATEST_VERSION)

    print(f"\nPlease review UPGRADE_SUMMARY.md for any manual steps.")

    return 0


if __name__ == '__main__':
    sys.exit(main())
