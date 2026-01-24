#!/usr/bin/env python3
"""
Build Telar site for local development

Runs all build scripts in sequence, mimicking the GitHub Actions workflow.
Use this instead of running individual scripts manually.

Version: v0.6.2-beta

Usage:
    python3 scripts/build_local_site.py              # Build and serve on port 4001
    python3 scripts/build_local_site.py --port 4000  # Use different port
    python3 scripts/build_local_site.py --build-only # Build without serving
    python3 scripts/build_local_site.py --skip-iiif  # Skip IIIF tile generation
    python3 scripts/build_local_site.py --skip-fetch # Skip Google Sheets fetch
"""

import argparse
import subprocess
import sys
import yaml
from pathlib import Path


def run_command(cmd, description, check=True):
    """Run a shell command with status output"""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}\n")

    result = subprocess.run(cmd, shell=True)

    if check and result.returncode != 0:
        print(f"\n❌ Error: {description} failed with exit code {result.returncode}")
        sys.exit(result.returncode)

    return result


def kill_running_jekyll():
    """Kill any running Jekyll instances"""
    result = subprocess.run(
        'pgrep -f "jekyll serve"',
        shell=True,
        capture_output=True,
        text=True
    )
    if result.stdout.strip():
        print("Killing existing Jekyll instances...")
        subprocess.run('pkill -9 -f "jekyll serve"', shell=True, stderr=subprocess.DEVNULL)
        print("✓ Killed running Jekyll processes")


def main():
    parser = argparse.ArgumentParser(description='Build Telar site for local development')
    parser.add_argument('--build-only', action='store_true', help='Build without starting server')
    parser.add_argument('--port', type=int, default=4001, help='Port for Jekyll server (default: 4001)')
    parser.add_argument('--skip-iiif', action='store_true', help='Skip IIIF tile generation')
    parser.add_argument('--skip-fetch', action='store_true', help='Skip Google Sheets fetch')
    args = parser.parse_args()

    # Serve by default unless --build-only is specified
    serve = not args.build_only

    # Kill any running Jekyll instances first
    kill_running_jekyll()

    print("\n" + "="*60)
    print("  Telar Local Build")
    print("="*60)

    # Step 1: Fetch Google Sheets (if enabled and not skipped)
    if not args.skip_fetch:
        config_path = Path('_config.yml')
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)

            gs_enabled = config.get('google_sheets', {}).get('enabled', False)

            if gs_enabled:
                run_command(
                    'python3 scripts/fetch_google_sheets.py',
                    'Step 1/5: Fetching data from Google Sheets'
                )
            else:
                print("\n✓ Step 1/5: Google Sheets disabled - using existing CSV files")
        else:
            print("\n⚠ Step 1/5: No _config.yml found - skipping Google Sheets fetch")
    else:
        print("\n✓ Step 1/5: Skipping Google Sheets fetch (--skip-fetch)")

    # Step 2: Convert CSV to JSON
    run_command(
        'python3 scripts/csv_to_json.py',
        'Step 2/5: Converting CSV to JSON'
    )

    # Step 3: Generate Jekyll collections
    run_command(
        'python3 scripts/generate_collections.py',
        'Step 3/5: Generating Jekyll collections'
    )

    # Step 4: Generate IIIF tiles (unless skipped)
    if not args.skip_iiif:
        base_url = f"http://127.0.0.1:{args.port}"

        # Read baseurl from config
        config_path = Path('_config.yml')
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
            baseurl = config.get('baseurl', '')
            if baseurl:
                base_url = f"{base_url}{baseurl}"

        run_command(
            f'python3 scripts/generate_iiif.py --base-url {base_url}',
            f'Step 4/5: Generating IIIF tiles (base URL: {base_url})'
        )
    else:
        print("\n✓ Step 4/5: Skipping IIIF generation (--skip-iiif)")

    # Step 5: Build or serve Jekyll
    if serve:
        print("\n" + "="*60)
        print(f"  Step 5/5: Starting Jekyll server on port {args.port}")
        print("="*60)
        print(f"\n  Site will be available at: http://127.0.0.1:{args.port}/telar/")
        print("  Press Ctrl+C to stop the server\n")

        # Run Jekyll serve (this blocks until Ctrl+C)
        run_command(
            f'bundle exec jekyll serve --port {args.port}',
            'Jekyll server',
            check=False  # Don't exit on Ctrl+C
        )
    else:
        run_command(
            'bundle exec jekyll build',
            'Step 5/5: Building Jekyll site'
        )
        print("\n" + "="*60)
        print("  Build complete! Site is in _site/")
        print("="*60 + "\n")


if __name__ == '__main__':
    main()
