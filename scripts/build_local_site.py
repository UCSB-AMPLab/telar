#!/usr/bin/env python3
"""
Build Telar Site for Local Development

This script orchestrates the full Telar build pipeline on a user's own
computer. The same pipeline also runs as a GitHub Actions workflow —
this script and the workflow are two equally valid ways to build a
Telar site.

The build pipeline has seven steps, each handled by a separate script
or tool:

1. Fetch Google Sheets data as CSV files (fetch_google_sheets.py)
2. Convert CSV to JSON, processing widgets, IIIF metadata, glossary
   links, and demo content (csv_to_json.py / telar package)
3. Generate Jekyll collection markdown files from JSON
   (generate_collections.py)
4. Process audio objects — generate waveform peak data for audio cards
   (process_audio.py)
5. Generate IIIF image tiles for self-hosted objects (generate_iiif.py)
6. Bundle JavaScript modules into story.js (esbuild)
7. Build or serve the Jekyll site

Each step can be skipped with flags (--skip-fetch, --skip-iiif,
--skip-audio, --build-only) for faster iteration when only some data
has changed. The default behaviour is to run all steps and start a
local Jekyll server on port 4001.

Version: v1.6.0

Usage:
    python3 scripts/build_local_site.py              # Build and serve on port 4001
    python3 scripts/build_local_site.py --port 4000  # Use different port
    python3 scripts/build_local_site.py --build-only # Build without serving
    python3 scripts/build_local_site.py --skip-iiif  # Skip IIIF tile generation
    python3 scripts/build_local_site.py --skip-fetch # Skip Google Sheets fetch
    python3 scripts/build_local_site.py --skip-audio # Skip audio processing
"""

import argparse
import subprocess
import sys
import yaml
from pathlib import Path


def _run_command(cmd, description, check, use_shell):
    """Run a command (shell string or argument list) with status output."""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}\n")

    result = subprocess.run(cmd, shell=use_shell)

    if check and result.returncode != 0:
        print(f"\n❌ Error: {description} failed with exit code {result.returncode}")
        sys.exit(result.returncode)

    return result


def run_command(cmd, description, check=True):
    """Run a shell command with status output"""
    return _run_command(cmd, description, check, use_shell=True)


def run_command_list(cmd, description, check=True):
    """Run a command given as an argument list (no shell), with status output.

    Preferred over run_command when any part of the command is interpolated
    (e.g. a base URL from config), so shell metacharacters cannot be injected.
    """
    return _run_command(cmd, description, check, use_shell=False)


def kill_running_jekyll(port):
    """Kill a Jekyll instance serving on the given port (this script's server).

    Scoped to the port and using SIGTERM (pkill's default, not -9/SIGKILL) so an
    unrelated `jekyll serve` on another port is left alone and the targeted
    server can shut down cleanly.
    """
    pattern = f'jekyll serve.*--port {port}'
    result = subprocess.run(
        ['pgrep', '-f', pattern],
        capture_output=True,
        text=True
    )
    if result.stdout.strip():
        print(f"Killing existing Jekyll instance on port {port}...")
        subprocess.run(['pkill', '-f', pattern], stderr=subprocess.DEVNULL)
        print("✓ Killed running Jekyll process")


def main():
    parser = argparse.ArgumentParser(description='Build Telar site for local development')
    parser.add_argument('--build-only', action='store_true', help='Build without starting server')
    parser.add_argument('--port', type=int, default=4001, help='Port for Jekyll server (default: 4001)')
    parser.add_argument('--skip-iiif', action='store_true', help='Skip IIIF tile generation')
    parser.add_argument('--skip-fetch', action='store_true', help='Skip Google Sheets fetch')
    parser.add_argument('--skip-audio', action='store_true', help='Skip audio processing')
    args = parser.parse_args()

    # Serve by default unless --build-only is specified
    serve = not args.build_only

    # Kill any running Jekyll instances first
    kill_running_jekyll(args.port)

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
                    'Step 1/8: Fetching data from Google Sheets'
                )
            else:
                print("\n✓ Step 1/8: Google Sheets disabled - using existing CSV files")
        else:
            print("\n⚠ Step 1/8: No _config.yml found - skipping Google Sheets fetch")
    else:
        print("\n✓ Step 1/8: Skipping Google Sheets fetch (--skip-fetch)")

    # Step 2: Convert CSV to JSON
    run_command(
        'python3 scripts/csv_to_json.py',
        'Step 2/8: Converting CSV to JSON'
    )

    # Step 3: Generate Jekyll collections
    run_command(
        'python3 scripts/generate_collections.py',
        'Step 3/8: Generating Jekyll collections'
    )

    # Step 4: Process audio objects (unless skipped)
    if not args.skip_audio:
        # Check if any audio files exist (skip gracefully if none)
        audio_extensions = ('.mp3', '.ogg', '.m4a')
        objects_dir = Path('telar-content/objects')
        has_audio = objects_dir.exists() and any(
            f for f in objects_dir.iterdir()
            if f.suffix.lower() in audio_extensions
        )
        if has_audio:
            run_command(
                'python3 scripts/process_audio.py --objects-dir telar-content/objects --data-dir _data --output-dir assets/audio',
                'Step 4/8: Processing audio objects (waveform peaks)'
            )
        else:
            print("\n✓ Step 4/8: No audio objects found - skipping audio processing")
    else:
        print("\n✓ Step 4/8: Skipping audio processing (--skip-audio)")

    # Step 5: Generate IIIF tiles (unless skipped)
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

        run_command_list(
            ['python3', 'scripts/generate_iiif.py', '--base-url', base_url],
            f'Step 5/8: Generating IIIF tiles (base URL: {base_url})'
        )
    else:
        print("\n✓ Step 5/8: Skipping IIIF generation (--skip-iiif)")

    # Step 6: Build JavaScript bundle
    run_command(
        'npm run build:js',
        'Step 6/8: Building JavaScript bundle'
    )

    # Step 7: Build or serve Jekyll
    if serve:
        print("\n" + "="*60)
        print(f"  Step 7/8: Starting Jekyll server on port {args.port}")
        print("="*60)
        print(f"\n  Site will be available at: http://127.0.0.1:{args.port}/telar/")
        print("  NOTE: serve mode regenerates _site continuously, so protected")
        print("  stories are NOT encrypted here (local plaintext only). To test")
        print("  them, run a build and serve _site with a static server.")
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
            'Step 7/8: Building Jekyll site'
        )

        # Step 8: Encrypt protected stories in the built output. Same gate as
        # the deploy workflow: a no-op without protected stories, a hard
        # failure rather than plaintext with them. Serve mode cannot hold
        # this guarantee (Jekyll regenerates _site continuously), so
        # protected-story testing uses this build followed by a static
        # server.
        run_command(
            'python3 scripts/encrypt_protected_stories.py',
            'Step 8/8: Encrypting protected stories (post-build gate)'
        )
        print("\n" + "="*60)
        print("  Build complete! Site is in _site/")
        print("="*60 + "\n")


if __name__ == '__main__':
    main()
