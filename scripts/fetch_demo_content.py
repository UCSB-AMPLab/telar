#!/usr/bin/env python3
"""
Fetch demo content from content.telar.org

Downloads demo stories and glossary content based on site version and language.
Demo content is stored in _demo_content/ (gitignored, never committed).

When include_demo_content is false, cleans up _demo_content/ directory.

Version: v0.6.0-beta
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
            print(f"🗑️  Cleaned up {demo_dir}/")
            return True
        except Exception as e:
            print(f"⚠️  Warning: Could not remove {demo_dir}/: {e}")
            return False

    return True


def fetch_manifest(version):
    """
    Fetch demo manifest from content.telar.org

    Args:
        version: Version string (e.g., "0.6.0")

    Returns:
        dict: Manifest data
        None: If fetch failed
    """
    base_url = "https://content.telar.org"
    manifest_url = f"{base_url}/demos/v{version}/manifest.json"

    try:
        print(f"📡 Fetching manifest from {manifest_url}")

        with urllib.request.urlopen(manifest_url, timeout=10) as response:
            manifest = json.loads(response.read().decode('utf-8'))

        print(f"✅ Manifest loaded (version {manifest.get('version', 'unknown')})")
        return manifest

    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"❌ Error: Demo content for version {version} not found")
            print(f"   Available versions at: {base_url}/demos/")
        else:
            print(f"❌ HTTP Error {e.code}: {e.reason}")
        return None

    except urllib.error.URLError as e:
        print(f"❌ Network error: {e.reason}")
        print(f"   Could not connect to {base_url}")
        return None

    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid manifest JSON: {e}")
        return None

    except Exception as e:
        print(f"❌ Unexpected error fetching manifest: {e}")
        return None


def download_file(url, dest_path):
    """
    Download a file from URL to destination path

    Args:
        url: Source URL
        dest_path: Destination Path object

    Returns:
        bool: True if download succeeded, False otherwise
    """
    try:
        # Create parent directory if it doesn't exist
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        with urllib.request.urlopen(url, timeout=10) as response:
            dest_path.write_bytes(response.read())

        return True

    except Exception as e:
        print(f"  ⚠️  Failed to download {url}: {e}")
        return False


def fetch_demo_files(manifest, version, language):
    """
    Download all demo files for the specified language

    Args:
        manifest: Manifest dict
        version: Version string
        language: Language code (en, es)

    Returns:
        bool: True if all downloads succeeded, False if any failed
    """
    base_url = "https://content.telar.org"

    # Check if language exists in manifest
    if language not in manifest.get('languages', {}):
        print(f"❌ Error: Language '{language}' not found in manifest")
        available = list(manifest.get('languages', {}).keys())
        if available:
            print(f"   Available languages: {', '.join(available)}")
        return False

    lang_data = manifest['languages'][language]
    stories = lang_data.get('stories', {})
    glossary_files = lang_data.get('glossary', [])

    if not stories:
        print(f"⚠️  Warning: No stories found for language '{language}'")
        return True

    print(f"\n📥 Downloading {len(stories)} story/stories for language '{language}'")
    print("-" * 50)

    total_files = 0
    failed_files = 0
    demo_dir = Path('_demo_content')

    # Download shared files (demo-project.csv, demo-objects.csv)
    shared_files = lang_data.get('files', {})
    for file_type, filename in shared_files.items():
        url = f"{base_url}/demos/v{version}/{language}/{filename}"
        dest = demo_dir / 'structures' / filename

        print(f"  {filename}...", end=' ')
        if download_file(url, dest):
            print("✓")
            total_files += 1
        else:
            print("✗")
            failed_files += 1

    # Download each story's files
    for story_id, story_info in stories.items():
        print(f"\n  {story_info.get('title', story_id)}:")

        # Download story CSV
        story_csv = story_info.get('csv', f"{story_id}.csv")
        url = f"{base_url}/demos/v{version}/{language}/{story_csv}"
        dest = demo_dir / 'structures' / story_csv

        print(f"    {story_csv}...", end=' ')
        if download_file(url, dest):
            print("✓")
            total_files += 1
        else:
            print("✗")
            failed_files += 1

        # Download story texts
        story_texts = story_info.get('texts', [])
        for text_file in story_texts:
            url = f"{base_url}/demos/v{version}/{language}/texts/stories/{story_id}/{text_file}"
            dest = demo_dir / 'texts' / 'stories' / story_id / text_file

            if download_file(url, dest):
                total_files += 1
            else:
                failed_files += 1

        if story_texts:
            print(f"    {len(story_texts)} story text(s) ✓")

    # Download shared glossary files
    if glossary_files:
        print(f"\n  Shared glossary:")
        for glossary_file in glossary_files:
            url = f"{base_url}/demos/v{version}/{language}/texts/glossary/{glossary_file}"
            dest = demo_dir / 'texts' / 'glossary' / glossary_file

            if download_file(url, dest):
                total_files += 1
            else:
                failed_files += 1

        print(f"    {len(glossary_files)} glossary term(s) ✓")

    print("-" * 50)
    print(f"✅ Downloaded {total_files} file(s) to _demo_content/")

    if failed_files > 0:
        print(f"⚠️  {failed_files} file(s) failed to download")
        return False

    return True


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
        print("ℹ️  Demo content disabled (include_demo_content: false)")
        cleanup_demo_content()
        print("✅ Done")
        sys.exit(0)

    # Demo content is enabled
    print(f"ℹ️  Demo content enabled for:")
    print(f"   Version: {config['version']}")
    print(f"   Language: {config['language']}")
    print()

    # Clean up old demo content
    cleanup_demo_content()

    # Fetch manifest
    manifest = fetch_manifest(config['version'])
    if manifest is None:
        print("\n❌ Failed to fetch demo content")
        print("   Your site will build without demos")
        sys.exit(1)

    # Download demo files
    success = fetch_demo_files(manifest, config['version'], config['language'])

    if success:
        print("\n✅ Demo content ready")
        sys.exit(0)
    else:
        print("\n⚠️  Demo content partially downloaded")
        print("   Your site may be missing some demos")
        sys.exit(1)


if __name__ == '__main__':
    main()
