"""
Story Processor

This module deals with converting a story CSV into the JSON that drives
a Telar narrative. Each row in the spreadsheet represents one "step" in
the story — a combination of a viewer object (the image the reader sees),
a question-and-answer pair, and up to two content layers (panels that
slide in from the side with text, images, or interactive widgets).

`process_story()` is the main entry point. It receives a pandas DataFrame
from one story CSV and performs several passes over the data:

1. **Object validation** — checks that every object ID referenced in the
   `object` column actually exists in `_data/objects.json`. Lookups are
   case-insensitive, so `MyMap` matches `mymap`. Missing references
   produce localised viewer warnings that appear in the story's intro
   panel.

2. **Content processing** — for each content column (`layer1_content`,
   `layer2_content`, and their legacy `_file` equivalents), the function
   determines whether the cell value is a markdown file reference (ending
   in `.md`) or inline text typed directly into the spreadsheet. File
   references are loaded by `read_markdown_file()` from the markdown
   module; inline text is processed by `process_inline_content()`. Both
   paths run through the same pipeline: widgets first, then images, then
   markdown-to-HTML conversion. After HTML conversion, glossary links
   (`[[term_id]]` syntax) are resolved by `process_glossary_links()`. As of
   v1.5.1 the step's `answer` prose is glossary-processed too (the `question`
   is a heading and is left alone), so `[[term]]` works in the main story
   text, not only in layer panels.

3. **Coordinate defaults** — empty `x`, `y`, and `zoom` cells get default
   values (0.5, 0.5, 1) so the viewer always has a valid starting
   position.

4. **Warning aggregation** — all warnings (missing objects, missing
   markdown files, broken glossary links, widget errors) are collected
   into a `viewer_warnings` list stored in `df.attrs`, which the core
   module later injects into the JSON output for display in the story's
   intro panel.

In Christmas Tree Mode, `process_story()` appends additional fake
warnings covering every warning type (viewer, panel, glossary) so that
the intro panel's error display can be visually tested.

Version: v1.5.1
"""

import re
import json
from pathlib import Path

import pandas as pd

from telar.config import get_lang_string
from telar.glossary import load_glossary_terms, process_glossary_links
from telar.markdown import read_markdown_file, process_inline_content
from telar.csv_utils import IMAGE_EXTENSIONS, build_stem_index, get_source_url
from telar.latex import has_latex


def process_story(df, christmas_tree=False):
    """
    Process story CSV with panel content (file references or inline text).

    Expected columns: step, question, answer, object, x, y, zoom,
    layer1_content, layer2_content, etc.
    (Also accepts legacy column names: layer1_file, layer2_file)

    Args:
        df: pandas DataFrame from story CSV
        christmas_tree: If True, inject fake warnings for testing

    Returns:
        pandas DataFrame with processed content and aggregated warnings
    """
    # Tracking for summary
    warnings = []

    # Load glossary terms for auto-linking
    glossary_terms = load_glossary_terms()
    glossary_warnings = []

    # Initialize widget warnings list
    widget_warnings = []

    # Drop example column if it exists
    if 'example' in df.columns:
        df = df.drop(columns=['example'])

    # Clean up NaN values
    df = df.fillna('')

    # Ensure alt_text column exists for backward compatibility
    if 'alt_text' not in df.columns:
        df['alt_text'] = ''

    # Remove completely empty rows
    df = df[df.astype(str).apply(lambda x: x.str.strip()).ne('').any(axis=1)]

    # Validate and normalize page column
    if 'page' in df.columns:
        for idx, row in df.iterrows():
            page_val = row.get('page', '')
            step_num = row.get('step', 'unknown')
            if pd.notna(page_val) and str(page_val).strip():
                try:
                    page_int = int(float(str(page_val).strip()))
                    if page_int < 1:
                        raise ValueError
                    df.at[idx, 'page'] = page_int
                except (ValueError, TypeError):
                    msg = f"Story step {step_num}: invalid page value '{page_val}' (must be positive integer)"
                    print(f"  [WARN] {msg}")
                    warnings.append(msg)
                    df.at[idx, 'page'] = ''

    # Load objects data for validation
    objects_data = {}
    objects_json_path = Path('_data/objects.json')
    if objects_json_path.exists():
        try:
            with open(objects_json_path, 'r', encoding='utf-8') as f:
                objects_list = json.load(f)
                # Create lookup dictionary by object_id
                objects_data = {obj['object_id']: obj for obj in objects_list}
        except Exception as e:
            print(f"  [WARN] Could not load objects.json for validation: {e}")

    # Add viewer_warning column if it doesn't exist
    if 'viewer_warning' not in df.columns:
        df['viewer_warning'] = ''

    # Validate object references
    if 'object' in df.columns and objects_data:
        # Build case-insensitive lookup map for objects
        objects_lower_map = {k.lower(): k for k in objects_data.keys()}

        # Shared canonical extension set for stripping object references.
        strippable_extensions = IMAGE_EXTENSIONS

        # Index telar-content/objects once so the per-reference local-file check
        # is an O(1) lookup instead of an iterdir scan per story step.
        _obj_file_index = build_stem_index('telar-content/objects')

        for idx, row in df.iterrows():
            object_id = str(row.get('object', '')).strip()
            step_num = row.get('step', 'unknown')

            # Skip if no object specified
            if not object_id:
                continue

            # Strip file extensions from object references (users may type "photo.jpg" instead of "photo")
            for ext in strippable_extensions:
                if object_id.lower().endswith(ext):
                    stripped_id = object_id[:-len(ext)]
                    print(f"  [INFO] Stripped extension from story object reference: '{object_id}' -> '{stripped_id}'")
                    object_id = stripped_id
                    df.at[idx, 'object'] = object_id
                    break

            # Check if object exists (case-insensitive)
            actual_object_id = None
            if object_id in objects_data:
                # Exact match
                actual_object_id = object_id
            elif object_id.lower() in objects_lower_map:
                # Case-insensitive match - use the correct-case version
                actual_object_id = objects_lower_map[object_id.lower()]
                # Update the DataFrame with correct case
                df.at[idx, 'object'] = actual_object_id

            if actual_object_id is None:
                error_msg = get_lang_string('errors.object_warnings.object_not_found', object_id=object_id)
                df.at[idx, 'viewer_warning'] = error_msg
                msg = f"Story step {step_num} references missing object: {object_id}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
                continue

            # Check if object has IIIF manifest or local image
            obj = objects_data[actual_object_id]
            iiif_manifest = obj.get('iiif_manifest', '').strip()

            # If no external IIIF manifest, check for local image file
            if not iiif_manifest:
                # Check for a local image or audio file via the one-time index
                audio_extensions = {'.mp3', '.ogg', '.m4a'}
                has_local_image = False

                for f in _obj_file_index.get(actual_object_id, []):
                    suffix = f.suffix.lower()
                    if suffix in IMAGE_EXTENSIONS:
                        has_local_image = True
                        print(f"  [INFO] Object {actual_object_id} uses local image: {f}")
                        break
                    if suffix in audio_extensions:
                        has_local_image = True
                        print(f"  [INFO] Object {actual_object_id} uses local audio: {f}")
                        break

                # Only warn if object has neither external manifest nor local image
                if not has_local_image:
                    error_msg = get_lang_string('errors.object_warnings.object_no_source', object_id=actual_object_id)
                    df.at[idx, 'viewer_warning'] = error_msg
                    msg = f"Story step {step_num} references object without IIIF source: {actual_object_id}"
                    print(f"  [WARN] {msg}")
                    warnings.append(msg)

    # Process content columns (layer1_content, layer2_content, etc.)
    # Also handles legacy _file suffix for backward compatibility
    for col in df.columns:
        if col.endswith('_content') or col.endswith('_file'):
            # Determine the base name (e.g., 'layer1' from 'layer1_content' or 'layer1_file')
            if col.endswith('_content'):
                base_name = col.replace('_content', '')
            else:
                base_name = col.replace('_file', '')

            # Create new columns for title and text
            title_col = f'{base_name}_title'
            text_col = f'{base_name}_text'

            # Initialize new columns with empty strings
            if title_col not in df.columns:
                df[title_col] = ''
            if text_col not in df.columns:
                df[text_col] = ''

            # Read markdown files or process inline content
            for idx, row in df.iterrows():
                cell_value = row[col]
                if cell_value and str(cell_value).strip():
                    cell_value = str(cell_value).strip()
                    step_num = row.get('step', 'unknown')
                    content_data = None

                    # Check if this looks like a file reference (.md extension)
                    if cell_value.endswith('.md'):
                        # Reject path-traversal in the author-controlled filename
                        # before joining it onto stories/. A value that tries to
                        # escape the texts directory falls through to inline
                        # processing rather than reading an arbitrary file.
                        if '..' in cell_value or cell_value.startswith('/') or '\\' in cell_value:
                            print(f"  [WARN] Ignoring unsafe layer file reference '{cell_value}' "
                                  f"(path traversal) — treating as inline content")
                        else:
                            # Try to load as markdown file
                            file_path = f"stories/{cell_value}"
                            content_data = read_markdown_file(file_path, widget_warnings)

                    # If not a file reference or file not found, treat as inline content
                    if content_data is None:
                        content_data = process_inline_content(cell_value, widget_warnings)

                    if content_data:
                        df.at[idx, title_col] = content_data['title']
                        # Apply glossary link transformation to content
                        content_with_glossary = process_glossary_links(
                            content_data['content'],
                            glossary_terms,
                            glossary_warnings,
                            step_num,
                            base_name
                        )
                        df.at[idx, text_col] = content_with_glossary

            # Drop the _content/_file column as it's no longer needed in JSON
            df = df.drop(columns=[col])

    # Resolve glossary [[term]] syntax in the step's answer prose. Layer panel
    # content above is converted md->HTML before glossary processing; the answer
    # is stored as markdown and rendered later in Liquid via `markdownify`, so the
    # transform runs on the markdown string here — the injected inline
    # <a class="glossary-inline-link"> passes through markdownify unchanged.
    # Scope is the answer only: the question is the step's title/heading
    # (<h2 class="step-question"> / <h2 class="title-card-heading">), and inline
    # links do not belong in a heading, so [[term]] in the question is left
    # literal. Not alt_text, button labels, or coordinates either. layer_name is
    # None because this is step prose, not a layer panel.
    if 'answer' in df.columns:
        for idx, row in df.iterrows():
            cell_value = row['answer']
            if cell_value and str(cell_value).strip():
                step_num = row.get('step', 'unknown')
                df.at[idx, 'answer'] = process_glossary_links(
                    str(cell_value),
                    glossary_terms,
                    glossary_warnings,
                    step_num,
                    None
                )

    # Set default coordinates for empty values
    coordinate_columns = ['x', 'y', 'zoom']
    for col in coordinate_columns:
        if col in df.columns:
            # Convert to string first to handle NaN values
            df[col] = df[col].astype(str)
            # Set defaults for empty or 'nan' values
            if col == 'x':
                df.loc[df[col].isin(['', 'nan']), col] = '0.5'
            elif col == 'y':
                df.loc[df[col].isin(['', 'nan']), col] = '0.5'
            elif col == 'zoom':
                df.loc[df[col].isin(['', 'nan']), col] = '1'

    # Collect all warnings for intro display
    all_warnings = []
    for idx, row in df.iterrows():
        step_num = row.get('step', 'unknown')

        # Check for viewer warnings (missing object/IIIF)
        viewer_warning = row.get('viewer_warning', '').strip()
        if viewer_warning:
            all_warnings.append({
                'step': step_num,
                'type': 'viewer',
                'message': viewer_warning
            })

        # Check for panel content warnings (missing markdown files)
        # Look for "Content Missing" title which indicates missing files
        content_missing_label = get_lang_string('errors.object_warnings.content_missing_label')
        for layer in ['layer1', 'layer2']:
            title_col = f'{layer}_title'
            if title_col in row and row[title_col] == content_missing_label:
                # Extract the filename from the error HTML in the text column
                text_col = f'{layer}_text'
                text = row.get(text_col, '')
                # Extract filename from the HTML (it's between <strong> tags)
                filename_match = re.search(r'<strong>(.*?)</strong>', text)
                # Get layer number for display (1 or 2)
                layer_num = layer[-1]  # Get '1' or '2' from 'layer1' or 'layer2'
                if filename_match:
                    # Extract content_file_missing message from HTML
                    message = filename_match.group(1)
                    all_warnings.append({
                        'step': step_num,
                        'type': 'panel',
                        'message': message
                    })
                else:
                    # Fallback if regex fails
                    all_warnings.append({
                        'step': step_num,
                        'type': 'panel',
                        'message': get_lang_string('errors.object_warnings.layer_file_missing', layer_num=layer_num)
                    })

    # Add glossary link warnings
    all_warnings.extend(glossary_warnings)

    # Add widget warnings
    all_warnings.extend(widget_warnings)

    # Store warnings in dataframe as metadata (will be added to JSON)
    df.attrs['viewer_warnings'] = all_warnings

    # Check for LaTeX content across all steps
    latex_detected = False
    for idx, row in df.iterrows():
        for col in df.columns:
            if col.endswith('_text'):
                text = str(row.get(col, ''))
                if text and has_latex(text):
                    latex_detected = True
                    break
        if latex_detected:
            break

    df.attrs['has_latex'] = latex_detected

    # Christmas Tree Mode: Inject fake warnings for testing
    if christmas_tree:
        # Inject test warnings for various error types
        fake_warnings = [
            {
                'step': 1,
                'type': 'viewer',
                'message': get_lang_string('errors.object_warnings.missing_object_id')
            },
            {
                'step': 2,
                'type': 'panel',
                'message': get_lang_string('errors.object_warnings.content_file_missing', file_ref='missing-file.md')
            },
            {
                'step': 3,
                'type': 'glossary',
                'term_id': 'nonexistent-term',
                'message': get_lang_string('errors.object_warnings.glossary_term_not_found', term_id='nonexistent-term')
            }
        ]
        # Add fake warnings to existing warnings
        df.attrs['viewer_warnings'] = all_warnings + fake_warnings
        print("\U0001f384 Christmas Tree Mode: Injected test warnings into story")

    # Print summary if there were issues
    if warnings:
        print(f"\n  Story validation summary: {len(warnings)} warning(s)")

    # Order steps by their authored `step` number so the rendered sequence
    # follows the step values, not the spreadsheet's physical row order — a CSV
    # exported out of order (e.g. by an external editor) would otherwise render
    # steps in the wrong sequence. Failsafe: a stable sort keeps rows that share
    # a step value in their original order, blank or non-numeric steps fall to
    # the end, and any unexpected error leaves the original row order untouched
    # rather than breaking the build.
    if 'step' in df.columns:
        try:
            step_order = pd.to_numeric(df['step'], errors='coerce')
            df = (df.assign(_step_order=step_order)
                    .sort_values('_step_order', kind='mergesort', na_position='last')
                    .drop(columns='_step_order')
                    .reset_index(drop=True))
        except Exception as e:
            print(f"  [WARN] Could not order story steps by 'step' value; "
                  f"using spreadsheet row order instead ({e})")

    return df
