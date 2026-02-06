"""
Objects Processor

This module deals with converting the objects CSV into validated JSON for
every exhibition object in a Telar story. Objects are the visual artefacts
that appear in the viewer panel — maps, paintings, photographs, manuscripts
— each identified by an `object_id` that links to either an external IIIF
manifest or a local image file in `components/images/`.

`process_objects()` is the main entry point. It receives a pandas DataFrame
from the objects spreadsheet and runs a series of validation and enrichment
steps before returning the cleaned DataFrame for JSON serialisation:

1. **Column normalisation** — ensures both `source_url` and `iiif_manifest`
   columns exist (for backward compatibility across naming transitions).

2. **Object ID cleanup** — strips accidental file extensions (e.g.,
   `my-object.jpg` becomes `my-object`) and warns about spaces.

3. **Thumbnail validation** — checks that thumbnail values are real image
   paths, clears placeholder values like "n/a" or "none", normalises
   duplicate slashes, and verifies the file exists on disk.

4. **IIIF manifest validation** — for each object with a `source_url`,
   fetches the manifest over HTTP, checks that it returns valid JSON with
   IIIF structure (`@context`, `type`), and handles HTTP error codes
   (404, 429, 500, etc.) with localised warning messages. A previous-build
   cache (`_data/objects.json`) lets the validator skip 429 rate-limiting
   errors for manifests that haven't changed.

5. **IIIF metadata extraction** — when a manifest validates successfully,
   extracts title, description, creator, period, location, and credit
   using the functions from the iiif_metadata module, then applies the fallback
   hierarchy (CSV values always win over IIIF values).

6. **Local image fallback** — objects without an external manifest are
   checked for a matching image file in `components/images/`. If no exact
   match is found, `_find_similar_image_filenames()` uses fuzzy string
   matching (via `difflib.SequenceMatcher` at 85% threshold) to suggest
   near-matches like case differences or hyphen/underscore variations.

`inject_christmas_tree_errors()` is a testing helper that appends fake
objects with intentionally broken IIIF URLs (404, 500, 503, 429, invalid)
to exercise every warning code path. These test objects are marked with a
Christmas tree emoji in their titles for easy identification.

Version: v0.8.0-beta
"""

import re
import json
import ssl
import random
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urlparse
from difflib import SequenceMatcher

import pandas as pd
import yaml

from telar.config import get_lang_string, load_site_language
from telar.csv_utils import get_source_url
from telar.iiif_metadata import (
    detect_iiif_version, extract_language_map_value, strip_html_tags,
    clean_metadata_value, find_metadata_field, extract_credit,
    apply_metadata_fallback
)


def _find_similar_image_filenames(object_id, images_dir):
    """
    Find image files that are similar to object_id but not exact matches.

    Checks for common variations:
    - Case differences: "MyObject" vs "myobject"
    - Hyphen/underscore variations: "my-object" vs "my_object" vs "myobject"
    - Extra characters or minor typos

    Args:
        object_id: The object ID to match against
        images_dir: Path object to the images directory

    Returns:
        List of similar filenames (just the filename, not full path)
    """
    if not images_dir.exists():
        return []

    # Normalize object_id for comparison (remove hyphens, underscores, lowercase)
    normalized_id = re.sub(r'[-_\s]', '', object_id.lower())

    similar_files = []
    valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff'}

    for file_path in images_dir.iterdir():
        if not file_path.is_file():
            continue

        # Only check image files
        if file_path.suffix.lower() not in valid_extensions:
            continue

        # Get filename without extension
        basename = file_path.stem
        normalized_file = re.sub(r'[-_\s]', '', basename.lower())

        # Skip if this is the exact object_id (exact matches are checked elsewhere)
        if basename.lower() == object_id.lower():
            continue

        # Calculate similarity ratio
        similarity = SequenceMatcher(None, normalized_id, normalized_file).ratio()

        # Consider similar if > 85% match
        if similarity > 0.85:
            similar_files.append(file_path.name)

    return similar_files


def inject_christmas_tree_errors(df):
    """
    Inject test objects with various error conditions for testing multilingual warnings.
    All test objects have a Christmas tree emoji in their titles for easy identification.

    This "Christmas Tree Mode" lights up all possible warning messages.

    Args:
        df: pandas DataFrame of objects

    Returns:
        pandas DataFrame with test objects appended
    """
    test_objects = [
        {
            'object_id': 'test-iiif-404',
            'title': '\U0001f384 Test - IIIF 404 Error',
            'description': 'Test object to trigger IIIF 404 error warning',
            'iiif_manifest': 'https://example.com/nonexistent/manifest.json',
            'creator': 'Test',
            'period': 'Test',
            'source': '',
            'credit': '',
            'thumbnail': ''
        },
        {
            'object_id': 'test-iiif-503',
            'title': '\U0001f384 Test - IIIF 503 Service Unavailable',
            'description': 'Test object to trigger IIIF 503 error warning',
            'iiif_manifest': 'https://httpstat.us/503',
            'creator': 'Test',
            'period': 'Test',
            'source': '',
            'credit': '',
            'thumbnail': ''
        },
        {
            'object_id': 'test-iiif-invalid',
            'title': '\U0001f384 Test - Invalid IIIF URL',
            'description': 'Test object to trigger invalid URL warning',
            'iiif_manifest': 'not-a-valid-url',
            'creator': 'Test',
            'period': 'Test',
            'source': '',
            'credit': '',
            'thumbnail': ''
        },
        {
            'object_id': 'test-image-missing',
            'title': '\U0001f384 Test - Missing Image Source',
            'description': 'Test object with no IIIF manifest and no local image file',
            'iiif_manifest': '',
            'creator': 'Test',
            'period': 'Test',
            'source': '',
            'credit': '',
            'thumbnail': ''
        },
        {
            'object_id': 'test-iiif-500',
            'title': '\U0001f384 Test - IIIF 500 Internal Server Error',
            'description': 'Test object to trigger IIIF 500 error warning',
            'iiif_manifest': 'https://httpstat.us/500',
            'creator': 'Test',
            'period': 'Test',
            'source': '',
            'credit': '',
            'thumbnail': ''
        },
        {
            'object_id': 'test-iiif-429',
            'title': '\U0001f384 Test - IIIF 429 Rate Limiting',
            'description': 'Test object to trigger IIIF 429 rate limiting warning',
            'iiif_manifest': 'https://httpstat.us/429',
            'creator': 'Test',
            'period': 'Test',
            'source': '',
            'credit': '',
            'thumbnail': ''
        }
    ]

    # Create dataframe from test objects and concatenate with existing data
    test_df = pd.DataFrame(test_objects)
    df = pd.concat([df, test_df], ignore_index=True)

    print("\U0001f384 Christmas Tree Mode activated - injected test objects with various errors")

    return df


def process_objects(df, christmas_tree=False):
    """
    Process objects CSV.

    Expected columns: object_id, title, creator, date, description, etc.

    Args:
        df: pandas DataFrame from objects CSV
        christmas_tree: If True, inject test objects with intentional errors

    Returns:
        pandas DataFrame with validated and enriched object data
    """
    # Tracking for summary
    warnings = []

    # Drop example column if it exists
    if 'example' in df.columns:
        df = df.drop(columns=['example'])

    # Clean up NaN values
    df = df.fillna('')

    # Remove rows where object_id is empty
    df = df[df['object_id'].astype(str).str.strip() != '']

    # Normalize source_url and iiif_manifest columns for backward compatibility
    # Ensure both columns exist in the DataFrame so templates can use either during transition
    if 'source_url' not in df.columns and 'iiif_manifest' in df.columns:
        # Old format: only iiif_manifest exists - create source_url as alias
        df['source_url'] = df['iiif_manifest']
    elif 'iiif_manifest' not in df.columns and 'source_url' in df.columns:
        # New format: only source_url exists - create iiif_manifest as alias for backward compat
        df['iiif_manifest'] = df['source_url']
    elif 'source_url' not in df.columns and 'iiif_manifest' not in df.columns:
        # Neither exists - create both as empty columns
        df['source_url'] = ''
        df['iiif_manifest'] = ''
    # If both exist, keep both (user is mid-transition)

    # Inject Christmas Tree test errors if flag is enabled
    if christmas_tree:
        df = inject_christmas_tree_errors(df)

    # Validate and clean object_id values
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff', '.bmp', '.svg']
    for idx, row in df.iterrows():
        object_id = str(row.get('object_id', '')).strip()
        original_id = object_id
        modified = False

        # Check for file extensions and strip them
        for ext in valid_extensions:
            if object_id.lower().endswith(ext):
                object_id = object_id[:-len(ext)]
                modified = True
                print(f"  [INFO] Stripped file extension from object_id: '{original_id}' \u2192 '{object_id}'")
                break

        # Check for spaces in object_id
        if ' ' in object_id:
            msg = f"Object ID '{object_id}' contains spaces - this may cause issues with file paths"
            print(f"  [WARN] {msg}")
            warnings.append(msg)

        # Update the dataframe if modified
        if modified:
            df.at[idx, 'object_id'] = object_id

    # Add object_warning column for IIIF/image validation
    if 'object_warning' not in df.columns:
        df['object_warning'] = ''

    # Validate thumbnail field
    if 'thumbnail' in df.columns:
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.tif', '.tiff']
        placeholder_values = ['n/a', 'null', 'none', 'placeholder', 'na', 'thumbnail']

        for idx, row in df.iterrows():
            thumbnail = str(row.get('thumbnail', '')).strip()
            object_id = row.get('object_id', 'unknown')

            # Skip if already empty
            if not thumbnail:
                continue

            # Check for placeholder values
            if thumbnail.lower() in placeholder_values:
                df.at[idx, 'thumbnail'] = ''
                msg = f"Cleared invalid thumbnail placeholder '{thumbnail}' for object {object_id}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
                continue

            # Check for valid image extension
            has_valid_extension = any(thumbnail.lower().endswith(ext) for ext in valid_extensions)

            if not has_valid_extension:
                df.at[idx, 'thumbnail'] = ''
                msg = f"Cleared invalid thumbnail '{thumbnail}' for object {object_id} (not an image file)"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
                continue

            # Normalize path to avoid duplicate slashes
            # Accept both /path and path, ensure single leading slash if present
            if thumbnail.startswith('/'):
                # Remove duplicate slashes
                normalized = '/' + '/'.join(filter(None, thumbnail.split('/')))
                if normalized != thumbnail:
                    df.at[idx, 'thumbnail'] = normalized
                    thumbnail = normalized
                    print(f"  [INFO] Normalized thumbnail path for object {object_id}: {normalized}")

            # Check if file exists (remove leading slash for filesystem check)
            file_path = thumbnail.lstrip('/')
            if not Path(file_path).exists():
                msg = f"Thumbnail file not found for object {object_id}: {thumbnail}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
                # Don't clear - file might be added later or exist in different environment

    # Load previous objects.json to skip 429 errors for unchanged manifests
    previous_objects = {}
    previous_objects_path = Path('_data/objects.json')
    if previous_objects_path.exists():
        try:
            with open(previous_objects_path, 'r', encoding='utf-8') as f:
                previous_data = json.load(f)
                # Create lookup: object_id -> {manifest_url, had_warning}
                for obj in previous_data:
                    previous_objects[obj.get('object_id')] = {
                        'manifest_url': obj.get('iiif_manifest', ''),
                        'had_warning': bool(obj.get('object_warning'))
                    }
                print(f"[INFO] Loaded {len(previous_objects)} objects from previous build for 429 checking")
        except Exception as e:
            print(f"[INFO] Could not load previous objects.json: {e}")
            previous_objects = {}

    # Validate source URL field (checks both source_url and iiif_manifest for backward compatibility)
    if 'source_url' in df.columns or 'iiif_manifest' in df.columns:
        for idx, row in df.iterrows():
            manifest_url = get_source_url(row)
            object_id = row.get('object_id', 'unknown')

            # Skip if empty
            if not manifest_url:
                continue

            # Check if it's a valid URL
            parsed = urlparse(manifest_url)
            if not parsed.scheme in ['http', 'https']:
                # Clear both columns (whichever exists)
                if 'source_url' in df.columns:
                    df.at[idx, 'source_url'] = ''
                if 'iiif_manifest' in df.columns:
                    df.at[idx, 'iiif_manifest'] = ''
                df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_invalid_url')
                msg = f"Cleared invalid source URL for object {object_id}: not a valid URL"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
                continue

            # Try to fetch the manifest (with timeout)
            # Create SSL context that doesn't verify certificates (avoid false positives)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            try:
                # Fetch manifest directly with GET (follows redirects automatically)
                req = urllib.request.Request(manifest_url)
                req.add_header('User-Agent', 'Telar/0.4.0-beta (IIIF validator)')

                with urllib.request.urlopen(req, timeout=30, context=ssl_context) as response:
                    content_type = response.headers.get('Content-Type', '')

                    # Check if response is JSON
                    if 'json' not in content_type.lower():
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_not_manifest')
                        msg = f"IIIF manifest for object {object_id} does not return JSON (Content-Type: {content_type})"
                        print(f"  [WARN] {msg}")
                        warnings.append(msg)
                        # Don't clear manifest URL - might still work despite wrong content type
                        continue

                    try:
                        data = json.loads(response.read().decode('utf-8'))

                        # Check for basic IIIF structure
                        has_context = '@context' in data
                        has_type = 'type' in data or '@type' in data

                        if not (has_context or has_type):
                            df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_malformed')
                            msg = f"IIIF manifest for object {object_id} missing required fields (@context or type)"
                            print(f"  [WARN] {msg}")
                            warnings.append(msg)
                        else:
                            print(f"  [INFO] Validated IIIF manifest for object {object_id}")

                            # Extract metadata from validated manifest
                            try:
                                site_language = load_site_language()
                                version = detect_iiif_version(data)
                                metadata_array = data.get('metadata', [])

                                extracted = {}

                                # Title
                                if version == '2.0':
                                    extracted['title'] = clean_metadata_value(data.get('label', ''))
                                else:  # v3.0
                                    label = data.get('label', {})
                                    if isinstance(label, dict):
                                        extracted['title'] = clean_metadata_value(
                                            extract_language_map_value(label, site_language)
                                        )
                                    else:
                                        extracted['title'] = clean_metadata_value(label)

                                # Description
                                if version == '2.0':
                                    desc = data.get('description', '')
                                    extracted['description'] = strip_html_tags(desc)
                                else:  # v3.0
                                    summary = data.get('summary', {})
                                    if isinstance(summary, dict):
                                        extracted['description'] = strip_html_tags(
                                            extract_language_map_value(summary, site_language)
                                        )
                                    else:
                                        extracted['description'] = strip_html_tags(summary)

                                # Creator
                                extracted['creator'] = find_metadata_field(
                                    metadata_array,
                                    ['Creator', 'Artist', 'Author', 'Maker', 'Cartographer', 'Contributor', 'Painter', 'Sculptor'],
                                    version,
                                    site_language
                                )

                                # Period
                                extracted['period'] = find_metadata_field(
                                    metadata_array,
                                    ['Date', 'Period', 'Creation Date', 'Created', 'Date Created', 'Date Note', 'Temporal'],
                                    version,
                                    site_language
                                )

                                # Source (Repository/Institution name, not geographic location)
                                # Note: renamed from 'location' to 'source' in v0.8.0
                                extracted['source'] = find_metadata_field(
                                    metadata_array,
                                    ['Repository', 'Holding Institution', 'Institution', 'Source', 'Current Location'],
                                    version,
                                    site_language
                                )

                                # If source not found in metadata, try provider (v3.0)
                                if not extracted['source'] and version == '3.0':
                                    providers = data.get('provider', [])
                                    if providers and isinstance(providers, list) and len(providers) > 0:
                                        provider = providers[0]
                                        if isinstance(provider, dict):
                                            provider_label = provider.get('label', {})
                                            if isinstance(provider_label, dict):
                                                extracted['source'] = extract_language_map_value(provider_label, site_language)
                                            else:
                                                extracted['source'] = str(provider_label).strip()

                                # Year (structured date for filtering/timeline)
                                extracted['year'] = find_metadata_field(
                                    metadata_array,
                                    ['Date', 'Year', 'Date Created', 'Creation Date'],
                                    version,
                                    site_language
                                )

                                # Object type (classification for filtering)
                                extracted['object_type'] = find_metadata_field(
                                    metadata_array,
                                    ['Type', 'Object Type', 'Resource Type', 'Format'],
                                    version,
                                    site_language
                                )

                                # Subjects (tags for filtering)
                                extracted['subjects'] = find_metadata_field(
                                    metadata_array,
                                    ['Subject', 'Subjects', 'Keywords', 'Tags', 'Topic'],
                                    version,
                                    site_language
                                )

                                # Credit
                                extracted['credit'] = extract_credit(data, version, site_language)

                                # Apply fallback hierarchy (CSV > IIIF > empty)
                                row_dict = row.to_dict()
                                apply_metadata_fallback(row_dict, extracted)

                                # Update dataframe with extracted values
                                # Core fields that can be auto-populated from IIIF
                                iiif_fields = ['title', 'description', 'creator', 'period', 'source', 'credit',
                                               'year', 'object_type', 'subjects']
                                for field in iiif_fields:
                                    if field in row_dict:
                                        df.at[idx, field] = row_dict[field]

                                # Log if any fields were auto-populated
                                populated_fields = []
                                for field in iiif_fields:
                                    csv_val = str(row.get(field, '')).strip()
                                    final_val = str(row_dict.get(field, '')).strip()
                                    if not csv_val and final_val:
                                        populated_fields.append(field)

                                if populated_fields:
                                    print(f"  [INFO] Auto-populated from IIIF: {', '.join(populated_fields)}")

                            except Exception as e:
                                # Metadata extraction failed - log but don't block validation
                                print(f"  [WARN] Could not extract metadata from IIIF manifest for {object_id}: {e}")

                    except json.JSONDecodeError:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_not_manifest')
                        msg = f"IIIF manifest for object {object_id} is not valid JSON"
                        print(f"  [WARN] {msg}")
                        warnings.append(msg)

            except urllib.error.HTTPError as e:
                # Check if we should skip this 429 error (unchanged manifest from previous build)
                skip_429 = False
                if e.code == 429 and object_id in previous_objects:
                    prev = previous_objects[object_id]
                    # Skip if: same URL as before AND no warning in previous build
                    if prev['manifest_url'] == manifest_url and not prev['had_warning']:
                        skip_429 = True
                        print(f"  [INFO] Skipping 429 error for unchanged manifest: {object_id} ({manifest_url})")

                # Only process error if not skipping
                if not skip_429:
                    if e.code == 404:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_404')
                        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_404')
                    elif e.code == 429:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_429')
                        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_429')
                    elif e.code == 403:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_403')
                        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_403')
                    elif e.code == 401:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_401')
                        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_401')
                    elif e.code == 500:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_500')
                        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_500')
                    elif e.code == 503:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_503')
                        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_503')
                    elif e.code == 502:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_502')
                        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_502')
                    else:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_error_generic', code=e.code)
                        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_error_generic', code=e.code)
                    msg = f"IIIF manifest for object {object_id} returned HTTP {e.code}: {manifest_url}"
                    print(f"  [WARN] {msg}")
                    warnings.append(msg)
            except urllib.error.URLError as e:
                # Network timeout - log for debugging but don't show user-facing warning
                # These are typically transient issues with slow institutional servers
                msg = f"IIIF manifest for object {object_id} slow to respond: {e.reason}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
            except Exception as e:
                df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_validation_failed')
                df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_validation_error')
                msg = f"Error validating IIIF manifest for object {object_id}: {str(e)}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)

    # Validate that objects have either source URL (IIIF manifest) OR local image file
    for idx, row in df.iterrows():
        object_id = row.get('object_id', 'unknown')
        source_url = get_source_url(row)

        # Skip if already has a valid source URL
        if source_url:
            continue

        # No external IIIF manifest - check for local image file
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff']
        has_local_image = False

        for ext in valid_extensions:
            local_image_path = Path(f'components/images/{object_id}{ext}')
            if local_image_path.exists():
                has_local_image = True
                print(f"  [INFO] Object {object_id} uses local image: {local_image_path}")
                break

        # Warn if object has neither external manifest nor local image
        if not has_local_image:
            # Check for similar filenames (near-matches)
            similar_files = _find_similar_image_filenames(object_id, Path('components/images'))

            if similar_files:
                # Found near-matches - provide helpful suggestion
                if len(similar_files) == 1:
                    similar_file = similar_files[0]
                    file_ext = Path(similar_file).suffix
                    error_msg = get_lang_string('errors.object_warnings.image_similar_single',
                                                 object_id=object_id,
                                                 similar_file=similar_file,
                                                 file_ext=file_ext)
                    df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_filename_mismatch')
                else:
                    file_list = "', '".join(similar_files)
                    error_msg = get_lang_string('errors.object_warnings.image_similar_multiple',
                                                 object_id=object_id,
                                                 file_list=file_list)
                    df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_ambiguous_match')
            else:
                # No similar files found - provide basic error message
                error_msg = get_lang_string('errors.object_warnings.image_missing', object_id=object_id)
                df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_missing_source')

            df.at[idx, 'object_warning'] = error_msg
            msg = f"Object {object_id} has no IIIF manifest or local image file"
            print(f"  [WARN] {msg}")
            warnings.append(msg)

    # Print summary if there were issues
    if warnings:
        print(f"\n  Objects validation summary: {len(warnings)} warning(s)")

    # Final cleanup: ensure no NaN values in output
    # (new columns added via IIIF extraction may leave NaN for objects without IIIF)
    df = df.fillna('')

    # Featured objects selection for homepage display
    # Mark objects with is_featured_sample: true for Liquid to filter
    df = _select_featured_objects(df)

    return df


def _select_featured_objects(df):
    """
    Select objects to feature on the homepage.

    If any objects have featured=yes, those are selected.
    Otherwise, randomly select objects (count from config, default 4).
    Selected objects are marked with is_featured_sample=true.

    Args:
        df: pandas DataFrame of objects

    Returns:
        pandas DataFrame with is_featured_sample column added
    """
    # Read config for settings
    config = {}
    config_path = Path('_config.yml')
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"  [WARN] Could not read _config.yml for featured objects: {e}")

    # Get settings from collection_interface
    collection_config = config.get('collection_interface', {})
    show_sample = collection_config.get('show_sample_on_homepage', False)
    featured_count = collection_config.get('featured_count', 4)

    # Initialize column
    df['is_featured_sample'] = False

    # Skip if show_sample_on_homepage is disabled
    if not show_sample:
        return df

    # Check for explicitly featured objects (case-insensitive yes/true/si)
    featured_values = {'yes', 'true', 'si', 'sí', '1'}
    if 'featured' in df.columns:
        featured_mask = df['featured'].astype(str).str.lower().str.strip().isin(featured_values)
        featured_objects = df[featured_mask]

        if len(featured_objects) > 0:
            # Use explicitly featured objects
            df.loc[featured_mask, 'is_featured_sample'] = True
            print(f"  [INFO] Selected {len(featured_objects)} explicitly featured object(s) for homepage")
            return df

    # No explicit featured objects — select randomly
    # Filter to objects without warnings (only show good objects on homepage)
    valid_objects = df[df['object_warning'].astype(str).str.strip() == '']

    if len(valid_objects) == 0:
        print("  [INFO] No valid objects available for homepage sample")
        return df

    # Select up to featured_count random objects
    sample_size = min(featured_count, len(valid_objects))
    sample_indices = random.sample(list(valid_objects.index), sample_size)

    df.loc[sample_indices, 'is_featured_sample'] = True
    print(f"  [INFO] Randomly selected {sample_size} object(s) for homepage sample")

    return df
