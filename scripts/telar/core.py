"""
Core Build Pipeline

This module deals with the top-level orchestration of Telar's CSV-to-JSON
build pipeline. It is the entry point that ties together all the other
modules in the telar package: reading CSV files, normalising columns,
dispatching to the appropriate processor, and writing the resulting JSON.

`csv_to_json()` is the generic converter that every CSV goes through. It
reads the file with pandas, filters out comment rows (lines starting with
`#`) and instruction columns (headers starting with `#`), detects and
skips duplicate header rows in bilingual spreadsheets, normalises column
names from Spanish to English, sanitises user data, then hands the
DataFrame to a processor function (`process_project_setup`,
`process_objects`, or `process_story`). After processing, it serialises
the result to JSON, prepending a `_metadata` block with viewer warnings
if the processor attached any.

`find_csv_with_fallback()` supports bilingual file naming by checking for
the English filename first (e.g., `project.csv`) and falling back to the
Spanish equivalent (e.g., `proyecto.csv`).

`main()` drives the full build. It fetches demo content if enabled,
checks for Christmas Tree Mode in `_config.yml`, then converts the three
CSV types in order: project setup, objects, and story files. Story files
are discovered dynamically — every CSV in `telar-content/spreadsheets/` that
is not a system file (`project.csv`, `objects.csv`, or their Spanish
equivalents) is treated as a story. The `--story` flag narrows this to a
single CSV by stem name, which speeds up iteration when working on one
story at a time. After all CSVs are converted, demo content is loaded and
merged if available. Protected stories are then encrypted using the
story_key from _config.yml. Finally, `generate_search_data()` builds the
Lunr.js search index and facet counts that power the gallery's
browse-and-search interface.

Before encrypting a protected story (v1.5.1), glossary link markup in the step
answer is reduced to plain text, because the protected-story runtime renderer
escapes the answer and has no glossary panel.

Version: v1.5.1
"""

import os
import json
from pathlib import Path

import pandas as pd
import yaml

from telar.csv_utils import sanitize_dataframe, normalize_column_names, is_header_row
from telar.processors.project import process_project_setup
from telar.processors.objects import process_objects
from telar.processors.stories import process_story
from telar.demo import load_demo_bundle, merge_demo_content, fetch_demo_content_if_enabled
from telar.encryption import encrypt_story, get_protected_stories, get_story_key_from_config
from telar.glossary import strip_glossary_links
from telar.search import generate_search_data


def csv_to_json(csv_path, json_path, process_func=None):
    """
    Convert CSV file to JSON.

    Args:
        csv_path: Path to input CSV file
        json_path: Path to output JSON file
        process_func: Optional function to process the dataframe before conversion

    Returns:
        bool: True if the JSON was written, False on skip (missing input) or error.
        Callers use this to avoid running downstream steps on stale/absent output.
    """
    if not os.path.exists(csv_path):
        print(f"Warning: {csv_path} not found. Skipping.")
        return False

    try:
        # Read CSV file with pandas
        # Note: We can't use pandas' comment parameter because it treats # anywhere as a comment,
        # which breaks hex color codes like #2c3e50 and markdown headers (## Title) in multi-line cells
        df = pd.read_csv(csv_path, on_bad_lines='warn')

        # Filter out comment rows (first column value starts with #)
        # This handles both # and "# patterns while preserving markdown headers in multi-line cells
        first_col = df.columns[0]
        df = df[~df[first_col].astype(str).str.strip().str.startswith('#')]

        # Filter out columns starting with # (instruction columns)
        df = df[[col for col in df.columns if not col.startswith('#')]]

        # Check if first data row is actually a duplicate header row (bilingual CSVs)
        if len(df) > 0:
            first_row = df.iloc[0]
            if is_header_row(first_row.values):
                print(f"  [WARN] Detected duplicate header row - skipping row 2")
                df = df.iloc[1:].reset_index(drop=True)

        # Normalize column names (Spanish -> English) for bilingual support
        df = normalize_column_names(df)

        # Sanitize user data - remove Christmas tree emoji to prevent accidental triggering
        df = sanitize_dataframe(df)

        # Apply processing function if provided
        if process_func:
            df = process_func(df)

        # Convert to JSON
        data = df.to_dict('records')

        # If dataframe has metadata (e.g., viewer warnings, LaTeX flag), prepend as first element
        if hasattr(df, 'attrs') and ('viewer_warnings' in df.attrs or 'has_latex' in df.attrs):
            metadata = {'_metadata': True}
            viewer_warnings = df.attrs.get('viewer_warnings')
            if viewer_warnings:
                metadata['viewer_warnings'] = viewer_warnings
            if df.attrs.get('has_latex'):
                metadata['has_latex'] = True
            if len(metadata) > 1:  # Only add if there's actual metadata beyond the flag
                data.insert(0, metadata)

        # Write JSON file
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"\u2713 Converted {csv_path} to {json_path}")
        return True

    except Exception as e:
        print(f"❌ Error converting {csv_path}: {e}")
        return False


def find_csv_with_fallback(base_path, spanish_name):
    """
    Find CSV file with bilingual fallback support.
    Checks for English name first, then Spanish equivalent.

    Args:
        base_path: Base path like 'telar-content/spreadsheets/project'
        spanish_name: Spanish filename like 'proyecto'

    Returns:
        str: Path to found CSV file, or original English path if neither exists
    """
    english_path = f'{base_path}.csv'
    spanish_path = f'{base_path.rsplit("/", 1)[0]}/{spanish_name}.csv'

    if Path(english_path).exists():
        return english_path
    elif Path(spanish_path).exists():
        print(f"  [INFO] Using Spanish file: {spanish_name}.csv")
        return spanish_path
    else:
        # Return English path (will trigger "file not found" warning in csv_to_json)
        return english_path


def _encrypt_protected_stories(data_dir):
    """
    Encrypt story JSON files that are marked as protected.

    Reads project.json to find protected stories, then encrypts their
    corresponding JSON files using the story_key from _config.yml.

    Args:
        data_dir: Path to _data directory containing JSON files
    """
    # Read _config.yml for story_key
    config_path = Path('_config.yml')
    if not config_path.exists():
        return

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"  [WARN] Could not read _config.yml: {e}")
        return

    story_key = get_story_key_from_config(config)

    # Read project.json to find protected stories
    project_path = data_dir / 'project.json'
    if not project_path.exists():
        return

    try:
        with open(project_path, 'r', encoding='utf-8') as f:
            project_data = json.load(f)
    except Exception as e:
        print(f"  [WARN] Could not read project.json: {e}")
        return

    protected_stories = get_protected_stories(project_data)

    if not protected_stories:
        print("No protected stories found.")
        return

    if not story_key:
        # Fail closed: stories are flagged protected but there is no key to
        # encrypt them. Continuing would publish them as plaintext.
        print(f"  ❌ {len(protected_stories)} story/stories are marked protected but "
              f"no story_key is set in _config.yml.")
        print("     Add 'story_key: yourkey' to _config.yml, or remove the 'protected' "
              "flag from those stories. Refusing to publish protected content as plaintext.")
        raise SystemExit(1)

    print(f"Encrypting {len(protected_stories)} protected story/stories...")

    failures = []
    for story_id in protected_stories:
        # Story JSON filename matches the identifier generate_collections used
        # (story_id, or the story-{number} fallback).
        story_json = data_dir / f"{story_id}.json"

        if not story_json.exists():
            failures.append((story_id, f"data file not found ({story_json.name})"))
            continue

        try:
            # Read story data
            with open(story_json, 'r', encoding='utf-8') as f:
                story_data = json.load(f)

            # Reduce glossary link markup in the step answer to plain text before
            # encrypting. Protected stories are rendered by a runtime path that
            # HTML-escapes the answer and offers no glossary panel, so the inline
            # <a class="glossary-inline-link"> injected by process_story would
            # surface as escaped tag-text. Layer panel content is unaffected (it is
            # rendered as trusted HTML at panel-open time), and the question is
            # never glossary-processed, so only the answer needs stripping.
            if isinstance(story_data, list):
                for step in story_data:
                    if isinstance(step, dict) and step.get('answer'):
                        step['answer'] = strip_glossary_links(step['answer'])

            # Encrypt story
            encrypted = encrypt_story(story_data, story_key)

            # Write encrypted data back
            with open(story_json, 'w', encoding='utf-8') as f:
                json.dump(encrypted, f, indent=2, ensure_ascii=False)

            print(f"  🔒 Encrypted {story_json.name}")

        except Exception as e:
            failures.append((story_id, f"encryption failed: {e}"))

    if failures:
        # Fail closed: any protected story we could not encrypt must not ship
        # as plaintext. Abort the build with a clear, actionable message.
        print("\n  ❌ Protected stories could not be encrypted — refusing to publish "
              "them as plaintext:")
        for sid, why in failures:
            print(f"       - {sid}: {why}")
        print("     Fix the story_id / data-file mismatch (or remove the 'protected' "
              "flag), then rebuild.")
        raise SystemExit(1)


AUDIO_EXTENSIONS = ('.mp3', '.ogg', '.m4a')


def _generate_audio_manifest(data_dir):
    """Generate _data/audio_objects.json from objects.json and local audio files.

    Scans telar-content/objects/ for audio files matching object IDs in
    objects.json, then writes a simple {object_id: extension} manifest.
    This manifest is consumed by story.html to inject window.audioObjects,
    which the JS card-type detector needs to distinguish audio objects from
    IIIF objects.

    Runs as part of the normal csv_to_json pipeline — no external tools
    required (unlike process_audio.py which needs audiowaveform for peak
    generation).
    """
    objects_json = data_dir / 'objects.json'
    if not objects_json.exists():
        return

    with open(objects_json, 'r', encoding='utf-8') as f:
        objects = json.load(f)

    objects_dir = Path('telar-content/objects')
    if not objects_dir.exists():
        return

    manifest = {}
    for obj in objects:
        object_id = obj.get('object_id', '').strip()
        if not object_id:
            continue
        for ext in AUDIO_EXTENSIONS:
            if (objects_dir / f'{object_id}{ext}').exists():
                manifest[object_id] = ext.lstrip('.')
                break

    manifest_path = data_dir / 'audio_objects.json'
    if manifest:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)
        print(f"  [INFO] Audio manifest: {len(manifest)} audio object(s) → {manifest_path}")
    elif manifest_path.exists():
        # No audio objects — remove stale manifest
        manifest_path.unlink()
        print(f"  [INFO] No audio objects found — removed stale {manifest_path}")


def main():
    """Main conversion process."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Convert Telar CSV files to JSON for Jekyll'
    )
    parser.add_argument(
        '--story',
        default=None,
        help='Story ID (CSV stem) to process; skips all other story CSVs (system CSVs always processed)'
    )
    args = parser.parse_args()

    # Fetch demo content FIRST (before any CSV processing)
    fetch_demo_content_if_enabled()

    # Check if Christmas Tree Mode is enabled in _config.yml
    christmas_tree_mode = False
    try:
        config_path = Path('_config.yml')
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                # Check development-features (v0.6.2+) or testing-features (legacy)
                dev_features = config.get('development-features', config.get('testing-features', {}))
                christmas_tree_mode = dev_features.get('christmas_tree_mode', False)

                if christmas_tree_mode:
                    print("\U0001f384 Christmas Tree Mode enabled - injecting test objects with errors")
                else:
                    # Clean up test object files when Christmas Tree Mode is disabled
                    objects_dir = Path('_jekyll-files/_objects')
                    if objects_dir.exists():
                        test_files = list(objects_dir.glob('test-*.md'))
                        if test_files:
                            print("  [INFO] Cleaning up test object files from previous Christmas Tree Mode session")
                            for test_file in test_files:
                                test_file.unlink()
                                print(f"  [INFO] Removed {test_file.name}")
    except Exception as e:
        print(f"  [WARN] Could not read Christmas Tree Mode setting: {e}")

    data_dir = Path('_data')
    data_dir.mkdir(exist_ok=True)

    structures_dir = Path('telar-content/spreadsheets')
    if not structures_dir.exists():
        old_dir = Path('telar-content/structures')
        if old_dir.exists():
            print(f"⚠️  Found '{old_dir}' — please rename to '{structures_dir}'")
            print(f"   Run: mv {old_dir} {structures_dir}")
            structures_dir = old_dir

    print("Converting CSV files to JSON...")
    print("-" * 50)

    # Convert project setup (with bilingual fallback: project.csv or proyecto.csv)
    project_path = find_csv_with_fallback('telar-content/spreadsheets/project', 'proyecto')
    csv_to_json(
        project_path,
        '_data/project.json',
        process_project_setup
    )

    # Convert objects (with bilingual fallback: objects.csv or objetos.csv)
    objects_path = find_csv_with_fallback('telar-content/spreadsheets/objects', 'objetos')
    if christmas_tree_mode:
        objects_ok = csv_to_json(
            objects_path,
            '_data/objects.json',
            lambda df: process_objects(df, christmas_tree=True)
        )
    else:
        objects_ok = csv_to_json(
            objects_path,
            '_data/objects.json',
            process_objects
        )

    # The audio manifest and search index both read _data/objects.json. If the
    # objects conversion was skipped or failed, that file is missing or stale, so
    # skip the downstream steps rather than build them from out-of-date data.
    if objects_ok:
        # Generate audio_objects.json manifest for client-side audio detection.
        # Maps object_id → file extension (e.g. {"cusb-cyl11337d": "mp3"}).
        # Without this file, story.html cannot inject window.audioObjects and
        # the JS card-type detector falls through to IIIF for audio objects.
        _generate_audio_manifest(data_dir)

        # Generate search data for gallery filtering (if enabled in config)
        generate_search_data()
    else:
        print("⚠️  Skipping audio manifest and search data: objects conversion did not succeed.")

    # Convert story files (with optional Christmas Tree mode)
    # v0.6.0+: Process ALL CSVs except system files
    system_csvs = {'project.csv', 'proyecto.csv', 'objects.csv', 'objetos.csv'}

    if christmas_tree_mode:
        for csv_file in structures_dir.glob('*.csv'):
            if csv_file.name not in system_csvs:
                # --story flag: skip all story CSVs except the requested one
                if args.story and csv_file.stem != args.story:
                    continue
                json_filename = csv_file.stem + '.json'
                json_file = data_dir / json_filename
                csv_to_json(
                    str(csv_file),
                    str(json_file),
                    lambda df: process_story(df, christmas_tree=True)
                )
    else:
        for csv_file in structures_dir.glob('*.csv'):
            if csv_file.name not in system_csvs:
                # --story flag: skip all story CSVs except the requested one
                if args.story and csv_file.stem != args.story:
                    continue
                json_filename = csv_file.stem + '.json'
                json_file = data_dir / json_filename
                csv_to_json(
                    str(csv_file),
                    str(json_file),
                    process_story
                )

    # Merge demo content if available
    print("-" * 50)
    demo_bundle = load_demo_bundle()
    if demo_bundle:
        print("Merging demo content...")
        merge_demo_content(demo_bundle)

    # Encrypt protected stories (v0.8.0+)
    print("-" * 50)
    _encrypt_protected_stories(data_dir)

    print("-" * 50)
    print("Conversion complete!")
