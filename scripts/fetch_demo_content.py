#!/usr/bin/env python3
"""
Fetch Demo Content from content.telar.org

When a new Telar site is first set up, it has no real content yet — no
objects, no stories, no glossary terms. Demo content fills this gap by
providing sample data that shows how the site will look and behave once
real content is added. Users can toggle it on or off with the
include_demo_content setting in _config.yml.

This script downloads a demo content bundle from content.telar.org,
Telar's content distribution server. Each bundle is version-specific
and language-specific (English or Spanish), so the script reads the
site's current version and language from _config.yml and fetches the
matching bundle. If an exact version match is not available, it falls
back to the closest compatible version.

The bundle is saved to _demo_content/ (gitignored, never committed).
The csv_to_json.py build script (telar package) merges demo content
into the JSON data alongside the user's real content, marking demo
items with a _demo flag so the site can style them differently.

Version: v0.7.0-beta
"""

import json
import shutil
import sys
import urllib.request
import urllib.error
from pathlib import Path
import yaml


def load_config():
    """
    Load configuration from _config.yml

    Returns:
        dict: Configuration with keys: enabled, version, language
        None: If config cannot be loaded
    """
    try:
        config_path = Path('_config.yml')
        if not config_path.exists():
            print("❌ Error: _config.yml not found")
            print("   Run this script from your Telar site root directory")
            return None

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Check if demo content is enabled
        story_interface = config.get('story_interface', {})
        enabled = story_interface.get('include_demo_content', False)

        # Get version and strip -beta suffix
        telar = config.get('telar', {})
        version = telar.get('version', '0.6.0')
        # Remove -beta, -alpha suffixes for version matching
        version = version.split('-')[0]

        # Get language
        language = config.get('telar_language', 'en')

        return {
            'enabled': enabled,
            'version': version,
            'language': language
        }

    except Exception as e:
        print(f"❌ Error reading _config.yml: {e}")
        return None


def cleanup_demo_content():
    """
    Remove _demo_content/ directory if it exists

    Returns:
        bool: True if cleanup succeeded, False otherwise
    """
    demo_dir = Path('_demo_content')

    if demo_dir.exists():
        try:
            shutil.rmtree(demo_dir)
            print(f"Cleaned up {demo_dir}/")
            return True
        except Exception as e:
            print(f"⚠️  Warning: Could not remove {demo_dir}/: {e}")
            return False

    return True


def fetch_versions_index():
    """
    Fetch available versions from content.telar.org/demos/versions.json

    Returns:
        list: List of version strings (e.g., ["0.6.0", "0.6.1", "0.7.0"])
        None: If fetch failed
    """
    base_url = "https://content.telar.org"
    versions_url = f"{base_url}/demos/versions.json"

    try:
        with urllib.request.urlopen(versions_url, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('versions', [])

    except Exception:
        # Silently fail - caller will handle fallback
        return None


def find_best_version(site_version, available_versions):
    """
    Find highest available version <= site_version

    Examples:
    - site=0.6.3, available=[0.6.0, 0.6.1, 0.7.0] -> returns 0.6.1
    - site=0.5.9, available=[0.6.0, 0.6.1, 0.7.0] -> returns None (no compatible)
    - site=0.8.0, available=[0.6.0, 0.7.0] -> returns 0.7.0

    Args:
        site_version: Version string from site config (e.g., "0.6.3")
        available_versions: List of available version strings

    Returns:
        str: Best matching version string
        None: If no compatible version exists
    """
    def parse_version(v):
        parts = v.split('.')
        return tuple(int(p) for p in parts)

    try:
        site_v = parse_version(site_version)
    except (ValueError, AttributeError):
        return None

    candidates = []

    for v in available_versions:
        try:
            v_parsed = parse_version(v)
            if v_parsed <= site_v:
                candidates.append((v_parsed, v))
        except (ValueError, AttributeError):
            continue

    if not candidates:
        return None

    # Return the highest compatible version
    return max(candidates, key=lambda x: x[0])[1]


def fetch_bundle(version, language):
    """
    Fetch demo bundle from content.telar.org

    Args:
        version: Version string (e.g., "0.6.0")
        language: Language code (e.g., "en", "es")

    Returns:
        dict: Bundle data
        None: If fetch failed
    """
    base_url = "https://content.telar.org"
    bundle_url = f"{base_url}/demos/v{version}/{language}/telar-demo-bundle.json"

    try:
        print(f"Fetching bundle from {bundle_url}")

        with urllib.request.urlopen(bundle_url, timeout=30) as response:
            bundle = json.loads(response.read().decode('utf-8'))

        meta = bundle.get('_meta', {})
        print(f"Bundle loaded:")
        print(f"   Telar version: {meta.get('telar_version', 'unknown')}")
        print(f"   Language: {meta.get('language', 'unknown')}")
        print(f"   Generated: {meta.get('generated', 'unknown')}")

        return bundle

    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"❌ Error: Demo bundle for v{version}/{language} not found")
            print(f"   URL: {bundle_url}")
        else:
            print(f"❌ HTTP Error {e.code}: {e.reason}")
        return None

    except urllib.error.URLError as e:
        print(f"❌ Network error: {e.reason}")
        print(f"   Could not connect to {base_url}")
        return None

    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid bundle JSON: {e}")
        return None

    except Exception as e:
        print(f"❌ Unexpected error fetching bundle: {e}")
        return None


def save_bundle(bundle):
    """
    Save bundle to _demo_content/telar-demo-bundle.json

    Args:
        bundle: Bundle dict to save

    Returns:
        bool: True if save succeeded, False otherwise
    """
    demo_dir = Path('_demo_content')
    bundle_path = demo_dir / 'telar-demo-bundle.json'

    try:
        demo_dir.mkdir(parents=True, exist_ok=True)

        with open(bundle_path, 'w', encoding='utf-8') as f:
            json.dump(bundle, f, indent=2, ensure_ascii=False)

        print(f"Saved to {bundle_path}")
        return True

    except Exception as e:
        print(f"❌ Error saving bundle: {e}")
        return False


def main():
    """Main entry point"""
    print("Telar Demo Content Fetcher")
    print("=" * 50)

    # Load configuration
    config = load_config()
    if config is None:
        sys.exit(1)

    # If demo content is disabled, clean up and exit
    if not config['enabled']:
        print("Demo content disabled (include_demo_content: false)")
        cleanup_demo_content()
        print("Done")
        sys.exit(0)

    # Demo content is enabled
    site_version = config['version']
    language = config['language']

    print(f"Demo content enabled for:")
    print(f"   Site version: {site_version}")
    print(f"   Language: {language}")
    print()

    # Clean up old demo content
    cleanup_demo_content()

    # Try to find best matching version
    available_versions = fetch_versions_index()
    target_version = site_version  # Default: exact match

    if available_versions:
        best_version = find_best_version(site_version, available_versions)

        if best_version is None:
            print(f"Warning: No compatible demo content for v{site_version}")
            print(f"   Available versions: {', '.join(available_versions)}")
            print("   Your site will build without demos")
            sys.exit(1)
        elif best_version != site_version:
            print(f"Demo content for v{site_version} not available")
            print(f"   Using compatible version: v{best_version}")
            print()
            target_version = best_version
        # else: exact match found, use site_version
    else:
        # versions.json unavailable, fall back to exact match
        print("Version index unavailable, trying exact match...")
        print()

    # Fetch bundle for target version and language
    bundle = fetch_bundle(target_version, language)
    if bundle is None:
        print("\nFailed to fetch demo content")
        print("   Your site will build without demos")
        sys.exit(1)

    # Save bundle
    if save_bundle(bundle):
        # Print summary
        projects = len(bundle.get('project', []))
        objects = len(bundle.get('objects', {}))
        stories = len(bundle.get('stories', {}))
        glossary = len(bundle.get('glossary', {}))

        print()
        print(f"Demo content ready:")
        print(f"   {projects} project(s)")
        print(f"   {objects} object(s)")
        print(f"   {stories} story/stories")
        print(f"   {glossary} glossary term(s)")
        sys.exit(0)
    else:
        print("\nFailed to save demo content")
        sys.exit(1)


if __name__ == '__main__':
    main()
