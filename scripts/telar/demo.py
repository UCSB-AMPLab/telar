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

Bundle format compatibility: v0.6.0 bundles use `medium`, `dimensions`, and
`location` object fields; v0.8.0+ bundles use `year`, `object_type`,
`subjects`, `featured`, and `source`. Both formats are supported — new fields
are populated when present, old fields are ignored gracefully.

Version: v1.8.0
"""

import contextlib
import io
import json
from pathlib import Path

import pandas as pd

from telar.images import process_images
from telar.latex import convert_markdown
from telar.widgets import process_widgets
from telar.glossary import (GlossaryTerms, place_demo_terms,
                            process_glossary_links)
from telar.glossary_kinds import resolve_kind
from telar.media_type import detect_media_type
from telar.processors.stories import (_detect_latex, _limit_answers,
                                      _prepare_answer_maths, _resolve_answer_glossary)

# Fields a bundle object or step may carry, copied only when it has a value:
# the step template emits an attribute for any value Liquid finds, and to
# Liquid an empty string is a value.
_DEMO_OBJECT_OPTIONAL = ('alt_text',)
_DEMO_STEP_OPTIONAL = ('alt_text', 'page', 'clip_start', 'clip_end', 'loop')


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

    Each section isolates its own failure and reports it on the console, so a
    broken bundle costs the sections that follow nothing. The order is fixed:
    the story files read the glossary terms the bundle carries, not the file
    the last section writes.

    Args:
        bundle: Demo bundle dict
    """
    data_dir = Path('_data')

    _merge_demo_projects(bundle, data_dir)
    _merge_demo_objects(bundle, data_dir)
    _write_demo_stories(bundle, data_dir)
    _write_demo_glossary(bundle)


def _merge_demo_projects(bundle, data_dir):
    """
    Prepend the bundle's stories to the user's project.json entry.

    Args:
        bundle: Demo bundle dict
        data_dir: Path to the site's _data directory
    """
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


def _merge_demo_objects(bundle, data_dir):
    """
    Append the bundle's objects to the user's objects.json, skipping duplicates.

    Args:
        bundle: Demo bundle dict
        data_dir: Path to the site's _data directory
    """
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
                    # Build object with v0.8.0 fields; fall back for v0.6.0 bundles
                    # where 'location' was the field name and year/object_type/subjects
                    # /featured were absent.
                    demo_obj = {
                        'object_id': obj_id,
                        'title': obj_data.get('title', ''),
                        'description': obj_data.get('description', ''),
                        'source_url': obj_data.get('source_url', ''),
                        'iiif_manifest': obj_data.get('source_url', ''),  # Backward compat
                        'creator': obj_data.get('creator', ''),
                        'period': obj_data.get('period', ''),
                        'year': obj_data.get('year', ''),
                        'object_type': obj_data.get('object_type', ''),
                        'subjects': obj_data.get('subjects', ''),
                        'featured': obj_data.get('featured', ''),
                        'source': obj_data.get('source', obj_data.get('location', '')),
                        'credit': obj_data.get('credit', ''),
                        'thumbnail': obj_data.get('thumbnail', ''),
                        # The gallery's Medium/Genre facet reads `medium`,
                        # which bundles before it was named call object_type.
                        'medium': obj_data.get('medium') or obj_data.get('object_type', ''),
                        '_demo': True
                    }
                    for key in _DEMO_OBJECT_OPTIONAL:
                        if obj_data.get(key) not in (None, ''):
                            demo_obj[key] = obj_data[key]
                    # Classified as a site's own objects are, from the source
                    # URL, so objects.json and the object page agree; the
                    # bundle's media_type is not read.
                    demo_obj['media_type'] = detect_media_type(
                        demo_obj['source_url'], obj_id)
                    user_objects.append(demo_obj)
                    demo_count += 1

            with open(objects_path, 'w', encoding='utf-8') as f:
                json.dump(user_objects, f, indent=2, ensure_ascii=False)

            print(f"  Merged {demo_count} demo object(s) into objects.json")

        except Exception as e:
            print(f"  [WARN] Could not merge demo objects: {e}")


def _write_demo_stories(bundle, data_dir):
    """
    Write one story file per bundle story, one failure isolated per story.

    Args:
        bundle: Demo bundle dict
        data_dir: Path to the site's _data directory
    """
    if bundle.get('stories'):
        for story_id, story_data in bundle['stories'].items():
            try:
                story_path = data_dir / f'{story_id}.json'

                # Convert demo story format to match user format
                steps = []

                glossary_terms = _demo_link_terms(bundle)

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

                    for key in _DEMO_STEP_OPTIONAL:
                        if step.get(key) not in (None, ''):
                            step_data[key] = str(step[key])

                    # Process layers
                    _add_demo_layers(step_data, step, story_id, glossary_terms)

                    steps.append(step_data)

                _process_demo_answers(steps, story_id, glossary_terms)
                if _detect_latex(pd.DataFrame(steps).fillna('')):
                    steps.insert(0, {'_metadata': True, 'has_latex': True})

                with open(story_path, 'w', encoding='utf-8') as f:
                    json.dump(steps, f, indent=2, ensure_ascii=False)

                print(f"  Created demo story: {story_id}.json ({len(steps)} steps)")

            except Exception as e:
                print(f"  [WARN] Could not create demo story {story_id}: {e}")


def _demo_link_terms(bundle):
    """The link map a demo story resolves [[term]] against: the bundle's
    glossary and the site's published pages together. Which demo terms
    have pages, and what a skipped demo id links to, is `place_demo_terms`'
    decision, the one the glossary pages are written from. A site term
    without a page is not linked: nothing is published for it, and neither
    is a demo term whose address is the glossary page's own.
    """
    # Imported here: glossary_pages loads the package this module is part of.
    from telar.glossary_pages import site_glossary_pages
    with contextlib.redirect_stdout(io.StringIO()):
        pages = site_glossary_pages()

    glossary = {term_id: term_data
                for term_id, term_data in (bundle.get('glossary') or {}).items() if term_id}
    placements = place_demo_terms(pages, list(glossary))

    terms = GlossaryTerms()
    for placement in placements:
        if placement.reason == 'index':
            # Published at the glossary page's own address: no page of its own.
            continue
        if placement.written:
            term_data = glossary[placement.term_id]
            title = term_data.get('term', placement.term_id)
            kind = resolve_kind(term_data.get('kind', ''), warn=False)
        elif placement.owner_is_site:
            title, kind = pages[placement.owner]
        else:
            owner_data = glossary[placement.owner]
            title = owner_data.get('term', placement.owner)
            kind = resolve_kind(owner_data.get('kind', ''), warn=False)
        terms[placement.term_id], terms.kinds[placement.term_id] = title, kind
        terms.addresses[placement.term_id] = placement.address
    for term_id, (title, kind) in pages.items():
        terms[term_id], terms.kinds[term_id] = title, kind
        if term_id in pages.addresses:
            terms.addresses[term_id] = pages.addresses[term_id]
    return terms


def _process_demo_answers(steps, story_id, glossary_terms):
    """Run a demo story's answers through the passes a site's own answers
    take, in the same order: the text-only rules and word limit, glossary
    links, and the maths kramdown would misread.

    What the passes report is discarded: the demo bundle's text is not
    something a site's author can change.
    """
    frame = pd.DataFrame({
        'step': [str(step.get('step', '')) for step in steps],
        'answer': [step.get('answer') or '' for step in steps],
    })
    with contextlib.redirect_stdout(io.StringIO()):
        frame = _limit_answers(frame, f'demo-{story_id}', [], [])
        frame = _resolve_answer_glossary(frame, glossary_terms, [])
        frame = _prepare_answer_maths(frame)
    for index, step in enumerate(steps):
        step['answer'] = frame.at[index, 'answer']
        if 'answer_kramdown' in frame.columns and frame.at[index, 'answer_kramdown']:
            step['answer_kramdown'] = frame.at[index, 'answer_kramdown']


def _add_demo_layers(step_data, step, story_id, glossary_terms):
    """
    Fill one step's layer fields from the bundle, running layer content through
    the widget, image, markdown and glossary pipeline regular stories use.

    Widgets run before markdown conversion and glossary links after it: the
    widget syntax is markdown's input, the glossary linker's input is HTML.

    Args:
        step_data: Step dict to fill in place
        step: Bundle step dict the layers come from
        story_id: Story identifier, which names the widget source
        glossary_terms: {term_id: term} dict for the glossary linker
    """
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
                content = convert_markdown(content, extensions=['extra', 'nl2br'])

                # Process glossary links AFTER markdown conversion
                content = process_glossary_links(content, glossary_terms)

            step_data[f'{layer_key}_text'] = content
            step_data[f'{layer_key}_demo'] = True  # All demo bundle layers are demo content


def _write_demo_glossary(bundle):
    """
    Write the bundle's glossary terms to _data/demo-glossary.json, which
    generate_collections.py reads to create Jekyll collection files.

    Args:
        bundle: Demo bundle dict
    """
    if bundle.get('glossary'):
        glossary_data = []
        for term_id, term_data in bundle['glossary'].items():
            entry = {
                'term_id': term_id,
                'title': term_data.get('term', term_id),
                'content': term_data.get('content', ''),
                '_demo': True
            }
            # A bundle term without one is a key term, which is what the
            # page generator makes of an entry with no kind.
            if term_data.get('kind'):
                entry['kind'] = term_data['kind']
            related = term_data.get('related_terms')
            if isinstance(related, str):
                related = [term.strip() for term in related.split('|')]
            if related:
                entry['related_terms'] = [str(term) for term in related if str(term).strip()]
            glossary_data.append(entry)

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
