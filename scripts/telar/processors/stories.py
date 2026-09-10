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
   (`[[term_id]]` syntax) are resolved by `process_glossary_links()`. The
   step's `answer` prose is glossary-processed too (the `question` is a
   heading and is left alone), so `[[term]]` works in the main story text,
   not only in layer panels.

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

Version: v1.7.0
"""

import re
import json
from pathlib import Path

import pandas as pd

from telar.config import get_lang_string
from telar.glossary import load_glossary_terms, process_glossary_links
from telar.markdown import read_markdown_file, process_inline_content
from telar.csv_utils import IMAGE_EXTENSIONS, build_stem_index
from telar.latex import has_latex
from telar.media_type import AUDIO_EXTENSIONS


def _warn(msg, warnings):
    """Print a WARN-prefixed message and record it in the warnings list."""
    print(f"  [WARN] {msg}")
    warnings.append(msg)



def _normalise_frame(df):
    """The shape every later pass assumes: no example column, no NaN, an
    alt_text column, and no rows that are entirely empty.
    """
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
    return df


def _validate_page_column(df, warnings):
    """A page number is an integer or it is nothing.

    A step that names a page the story does not have would render
    nowhere, so an unusable value is cleared and said out loud rather
    than carried into the JSON.
    """
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
                    _warn(msg, warnings)
                    df.at[idx, 'page'] = ''
    return df


def _load_objects_data():
    """The built objects.json, keyed by id, or None when there is none.

    None and an empty mapping are different answers. A site that has not
    run the objects processor yet, or whose objects.json cannot be read,
    has nothing to check references against, and the reference pass is
    skipped rather than reporting every step as wrong. A site whose
    objects.json holds no objects has been checked and has none, so every
    object a story names is a reference to something absent.
    """
    objects_json_path = Path('_data/objects.json')
    if not objects_json_path.exists():
        return None
    try:
        with open(objects_json_path, 'r', encoding='utf-8') as f:
            objects_list = json.load(f)
            # Create lookup dictionary by object_id
            return {obj['object_id']: obj for obj in objects_list}
    except Exception as e:
        print(f"  [WARN] Could not load objects.json for validation: {e}")
        return None


def _check_object_has_a_source(df, idx, objects_data, actual_object_id,
                               file_index, step_num, warnings):
    """An object a step points at must resolve to something showable.

    A manifest, or a file beside it -- image or audio, since an audio
    object is shown by its player rather than by a picture. Neither is a
    warning on the step, not a failure: the story still renders, with a
    gap where the object would be.
    """
    # Check if object has IIIF manifest or local image
    obj = objects_data[actual_object_id]
    iiif_manifest = obj.get('iiif_manifest', '').strip()

    # If no external IIIF manifest, check for local image file
    if not iiif_manifest:
        # Check for a local image or audio file via the one-time index
        has_local_image = False

        for f in file_index.get(actual_object_id, []):
            suffix = f.suffix.lower()
            if suffix in IMAGE_EXTENSIONS:
                has_local_image = True
                print(f"  [INFO] Object {actual_object_id} uses local image: {f}")
                break
            if suffix in AUDIO_EXTENSIONS:
                has_local_image = True
                print(f"  [INFO] Object {actual_object_id} uses local audio: {f}")
                break

        # Only warn if object has neither external manifest nor local image
        if not has_local_image:
            error_msg = get_lang_string('errors.object_warnings.object_no_source', object_id=actual_object_id)
            df.at[idx, 'viewer_warning'] = error_msg
            msg = f"Story step {step_num} references object without IIIF source: {actual_object_id}"
            _warn(msg, warnings)

def _validate_object_references(df, objects_data, warnings):
    """Every `object` a step names must be one the site has.

    Lookups are case-insensitive and an accidental file extension is
    stripped, because both are what an author actually types. A missing
    reference becomes a viewer warning, which the story shows in its
    intro panel rather than failing the build.
    """
    # Add viewer_warning column if it doesn't exist
    if 'viewer_warning' not in df.columns:
        df['viewer_warning'] = ''

    # Validate object references
    if 'object' in df.columns and objects_data is not None:
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
                _warn(msg, warnings)
                continue

            _check_object_has_a_source(df, idx, objects_data,
                                       actual_object_id, _obj_file_index,
                                       step_num, warnings)
    return df


def _layer_content_for(cell_value, widget_warnings):
    """One layer cell as content, from a file or from the cell itself.

    A value ending in `.md` names a file; anything else is prose typed
    into the spreadsheet. A filename that tries to leave the texts
    directory is not read at all -- it falls through to inline
    processing, so the worst an author can do to themselves is publish
    their own path as text.
    """
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
    return content_data

def _process_content_columns(df, glossary_terms, glossary_warnings, widget_warnings):
    """Turn every layer column into HTML, from a file or from the cell.

    A value ending in `.md` names a file under telar-content/texts;
    anything else is prose typed into the spreadsheet. Both run the same
    pipeline -- widgets, then images, then markdown -- so a panel reads
    the same either way. The legacy `_file` column names are still
    accepted.
    """
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

                    content_data = _layer_content_for(
                        cell_value, widget_warnings)

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

            # Drop the _content/_file column: it is not part of the JSON output
            df = df.drop(columns=[col])
    return df


def _resolve_answer_glossary(df, glossary_terms, glossary_warnings):
    """Resolve [[term]] in the step's answer prose.

    The answer only. The question is the step's heading, and an inline
    link does not belong in one, so [[term]] there is left literal. The
    answer is still markdown at this point -- Liquid renders it later --
    so the transform runs on the markdown string, and the anchor it
    injects passes through markdownify unchanged.
    """
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
    return df


def _apply_coordinate_defaults(df):
    """A viewer needs somewhere to start, so empty coordinates get one."""
    # Set default coordinates for empty values
    coordinate_defaults = {'x': '0.5', 'y': '0.5', 'zoom': '1'}
    for col, default in coordinate_defaults.items():
        if col in df.columns:
            # Convert to string first to handle NaN values
            df[col] = df[col].astype(str)
            # Set defaults for empty or 'nan' values
            df.loc[df[col].isin(['', 'nan']), col] = default
    return df


def _collect_step_warnings(df):
    """Everything the intro panel will show, gathered from the columns.

    These live in df.attrs rather than in a column: they belong to the
    story, not to any one step, and the JSON writer reads them from
    there.
    """
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
    return all_warnings


def _detect_latex(df):
    """Whether any step carries LaTeX, so the page can load the renderer.

    Scans every surface the markdown-syntax docs promise LaTeX works in:
    the question and answer prose, and the resolved layer text.
    """
    # question/answer prose and resolved layer content (*_text columns).
    latex_detected = False
    for idx, row in df.iterrows():
        for col in df.columns:
            if col in ('question', 'answer') or col.endswith('_text'):
                text = str(row.get(col, ''))
                if text and has_latex(text):
                    latex_detected = True
                    break
        if latex_detected:
            break

    return latex_detected


def _add_christmas_tree_warnings(df, all_warnings):
    """Every warning kind at once, so the intro panel can be looked at.

    Appended rather than substituted: the point is to see them beside
    whatever the story really produced.
    """
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
    # One function per pass, in the order the module docstring lists
    # them. Three accumulators are shared, and only as accumulators:
    # `warnings` is what the summary counts, and the other two are
    # filled by passes that cannot reach df.attrs themselves.
    warnings = []
    glossary_terms = load_glossary_terms()
    glossary_warnings = []
    widget_warnings = []

    df = _normalise_frame(df)
    df = _validate_page_column(df, warnings)
    df = _validate_object_references(df, _load_objects_data(), warnings)
    df = _process_content_columns(df, glossary_terms, glossary_warnings,
                                  widget_warnings)
    df = _resolve_answer_glossary(df, glossary_terms, glossary_warnings)
    df = _apply_coordinate_defaults(df)

    all_warnings = _collect_step_warnings(df)
    all_warnings.extend(glossary_warnings)
    all_warnings.extend(widget_warnings)
    df.attrs['viewer_warnings'] = all_warnings

    df.attrs['has_latex'] = _detect_latex(df)

    if christmas_tree:
        _add_christmas_tree_warnings(df, all_warnings)

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

