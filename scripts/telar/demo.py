"""
Demo Content Loading and Merging

This module deals with Telar's demo content system, which lets new users
see a working example story before they create their own. Demo content is
distributed as a JSON bundle hosted at content.telar.org, fetched at build
time, and merged into the site's existing data files so that demo stories
appear alongside user stories.

The pipeline has three stages:

`fetch_demo_content_if_enabled()` runs first, before any CSV processing.
It shells out to `scripts/fetch_demo_content.py` as a subprocess, which
checks `_config.yml` for the `include_demo_content` setting. If enabled,
the subprocess downloads the bundle to `_demo_content/telar-demo-bundle.json`.
If disabled, it cleans up any leftover bundle. A 60-second timeout prevents
the build from hanging on slow networks, and failures are non-fatal — the
rest of the build continues without demo content.

`load_demo_bundle()` reads the bundle JSON from disk if it exists. The
bundle contains a `_meta` key with version and language information, plus
`project`, `objects`, `stories`, and `glossary` sections.

`merge_demo_content()` integrates the bundle into the user's site data.
It prepends demo stories to `_data/project.json`, appends demo objects to
`_data/objects.json` (skipping duplicates by object ID), creates individual
story JSON files in `_data/`, and writes demo glossary terms to
`_data/demo-glossary.json` for `generate_collections.py` to pick up. Each
demo entry is tagged with `_demo: True` so that templates can distinguish
demo content from user content. During story merging, layer content goes
through the same widget, image, markdown, and glossary pipeline that
regular stories use.

Version: v0.7.0-beta
"""

import json
from pathlib import Path

import markdown as md_lib
import pandas as pd

from telar.images import process_images
from telar.widgets import process_widgets
from telar.glossary import process_glossary_links


def load_demo_bundle():
    """
    Load demo content bundle if it exists.

    Returns:
        dict: Demo bundle data, or None if not present
    """
    bundle_path = Path('_demo_content/telar-demo-bundle.json')

    if not bundle_path.exists():
        return None

    try:
        with open(bundle_path, 'r', encoding='utf-8') as f:
            bundle = json.load(f)

        meta = bundle.get('_meta', {})
        print(f"[INFO] Loaded demo bundle v{meta.get('telar_version', 'unknown')} ({meta.get('language', 'unknown')})")
        return bundle

    except Exception as e:
        print(f"[WARN] Could not load demo bundle: {e}")
        return None


def merge_demo_content(bundle):
    """
    Merge demo bundle content with user content.

    Merges:
    - Demo projects into _data/project.json
    - Demo objects into _data/objects.json
    - Demo stories as additional story files
    - Demo glossary files (written to _data/demo-glossary.json)

    Args:
        bundle: Demo bundle dict
    """
    data_dir = Path('_data')

    # Merge projects
    project_path = data_dir / 'project.json'
    if project_path.exists() and bundle.get('project'):
        try:
            with open(project_path, 'r', encoding='utf-8') as f:
                user_project = json.load(f)

            # Convert demo project format to match user format
            # Use order for number field, story_id for identifier (v0.6.0+)
            demo_stories = []
            for proj in bundle['project']:
                demo_stories.append({
                    'number': str(proj.get('order', '')),
                    'story_id': proj.get('story_id', ''),
                    'title': proj.get('title', ''),
                    'subtitle': proj.get('subtitle', ''),
                    'byline': proj.get('byline', ''),
                    '_demo': True  # Mark as demo content
                })

            # Merge: demo stories first, then user stories
            if 'stories' in user_project[0]:
                user_project[0]['stories'] = demo_stories + user_project[0]['stories']
            else:
                user_project[0]['stories'] = demo_stories

            with open(project_path, 'w', encoding='utf-8') as f:
                json.dump(user_project, f, indent=2, ensure_ascii=False)

            print(f"  Merged {len(demo_stories)} demo project(s) into project.json")

        except Exception as e:
            print(f"  [WARN] Could not merge demo projects: {e}")

    # Merge objects
    objects_path = data_dir / 'objects.json'
    if objects_path.exists() and bundle.get('objects'):
        try:
            with open(objects_path, 'r', encoding='utf-8') as f:
                user_objects = json.load(f)

            # Get existing object IDs to avoid duplicates
            existing_ids = {obj.get('object_id') for obj in user_objects if not obj.get('_metadata')}

            # Convert demo objects format and add new ones
            demo_count = 0
            for obj_id, obj_data in bundle['objects'].items():
                if obj_id not in existing_ids:
                    demo_obj = {
                        'object_id': obj_id,
                        'title': obj_data.get('title', ''),
                        'description': obj_data.get('description', ''),
                        'source_url': obj_data.get('source_url', ''),
                        'iiif_manifest': obj_data.get('source_url', ''),  # Backward compat
                        'creator': obj_data.get('creator', ''),
                        'period': obj_data.get('period', ''),
                        'medium': obj_data.get('medium', ''),
                        'dimensions': obj_data.get('dimensions', ''),
                        'location': obj_data.get('location', ''),
                        'credit': obj_data.get('credit', ''),
                        'thumbnail': obj_data.get('thumbnail', ''),
                        '_demo': True
                    }
                    user_objects.append(demo_obj)
                    demo_count += 1

            with open(objects_path, 'w', encoding='utf-8') as f:
                json.dump(user_objects, f, indent=2, ensure_ascii=False)

            print(f"  Merged {demo_count} demo object(s) into objects.json")

        except Exception as e:
            print(f"  [WARN] Could not merge demo objects: {e}")

    # Create demo story files
    if bundle.get('stories'):
        for story_id, story_data in bundle['stories'].items():
            try:
                story_path = data_dir / f'{story_id}.json'

                # Convert demo story format to match user format
                steps = []
                for step in story_data.get('steps', []):
                    step_data = {
                        'step': step.get('step'),
                        'object': step.get('object', ''),
                        'x': str(step.get('x', '0.5')),
                        'y': str(step.get('y', '0.5')),
                        'zoom': str(step.get('zoom', '1')),
                        'question': step.get('question', ''),
                        'answer': step.get('answer', ''),
                        '_demo': True
                    }

                    # Build glossary terms dict from bundle for link processing
                    glossary_terms = {}
                    if bundle.get('glossary'):
                        for term_id, term_data in bundle['glossary'].items():
                            glossary_terms[term_id] = term_data.get('term', term_id)

                    # Process layers
                    layers = step.get('layers', {})
                    for layer_key in ['layer1', 'layer2']:
                        layer = layers.get(layer_key, {})
                        if layer:
                            step_data[f'{layer_key}_button'] = layer.get('button', '')
                            # Use explicit title if provided, fall back to button text
                            step_data[f'{layer_key}_title'] = layer.get('title', layer.get('button', ''))

                            content = layer.get('content', '')
                            if content:
                                # Initialize warnings list for widget processing
                                widget_warnings = []

                                # Process widgets BEFORE markdown conversion
                                content = process_widgets(content, f'demo-{story_id}', widget_warnings)

                                # Process images (sizes and captions) BEFORE markdown conversion
                                content = process_images(content)

                                # Convert markdown to HTML
                                content = md_lib.markdown(content, extensions=['extra', 'nl2br'])

                                # Process glossary links AFTER markdown conversion
                                content = process_glossary_links(content, glossary_terms)

                            step_data[f'{layer_key}_text'] = content
                            step_data[f'{layer_key}_demo'] = True  # All demo bundle layers are demo content

                    steps.append(step_data)

                with open(story_path, 'w', encoding='utf-8') as f:
                    json.dump(steps, f, indent=2, ensure_ascii=False)

                print(f"  Created demo story: {story_id}.json ({len(steps)} steps)")

            except Exception as e:
                print(f"  [WARN] Could not create demo story {story_id}: {e}")

    # Write demo glossary to _data/demo-glossary.json
    # (generate_collections.py will read this and create Jekyll collection files)
    if bundle.get('glossary'):
        glossary_data = []
        for term_id, term_data in bundle['glossary'].items():
            glossary_data.append({
                'term_id': term_id,
                'title': term_data.get('term', term_id),
                'content': term_data.get('content', ''),
                '_demo': True
            })

        glossary_json_path = Path('_data/demo-glossary.json')
        with open(glossary_json_path, 'w', encoding='utf-8') as f:
            json.dump(glossary_data, f, indent=2, ensure_ascii=False)

        print(f"  Created _data/demo-glossary.json ({len(glossary_data)} demo terms)")


def fetch_demo_content_if_enabled():
    """
    Automatically fetch demo content bundle before processing CSVs.

    Runs fetch_demo_content.py as a subprocess to ensure the demo bundle
    is available before csv_to_json.py attempts to load and merge it.

    Returns:
        None
    """
    import subprocess

    try:
        # Run fetch_demo_content.py to ensure bundle exists
        # This checks config and either fetches, cleans up, or no-ops accordingly
        result = subprocess.run(
            ['python3', 'scripts/fetch_demo_content.py'],
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout for network fetch
        )

        # Print output so users see what happened
        if result.stdout:
            print(result.stdout)

    except subprocess.TimeoutExpired:
        # Network fetch took too long - continue without demo content
        print("[WARN] Demo content fetch timed out (skipping)")
        print("[WARN] Your site will build without demo content")

    except Exception as e:
        # Unexpected error (subprocess not found, permission denied, etc.)
        print(f"[WARN] Could not fetch demo content: {e}")
        print("[WARN] Your site will build without demo content")
