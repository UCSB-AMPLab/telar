"""Shaping the objects frame before anything is validated.

Column normalisation, id cleanup, the alt-text fallback, thumbnail checks,
and the previous build's objects.json -- everything that happens to the frame
itself rather than to what an object points at.

Version: v1.7.0
"""

import json
from pathlib import Path

from telar.csv_utils import IMAGE_EXTENSIONS
from telar.processors.objects.christmas_tree import inject_christmas_tree_errors


def _normalise_frame(df, christmas_tree):
    """The shape every later step assumes: no example column, no NaN, no
    empty ids, and both url column names present.

    Christmas Tree objects are injected before any of it so they flow through
    the aliasing, the alt_text fallback and the id cleanup exactly as real
    objects do.
    """
    # Inject Christmas Tree test errors first, before any normalisation, so the
    # test objects flow through source_url/iiif_manifest aliasing, the alt_text
    # fallback and object_id sanitisation identically to real objects.
    if christmas_tree:
        df = inject_christmas_tree_errors(df)

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
    return df


def _clean_object_ids(df, warnings):
    """Strip an accidental file extension, and warn about spaces.

    An id is a file name in waiting, so `my-object.jpg` means `my-object`.
    """
    # Validate and clean object_id values
    for idx, row in df.iterrows():
        object_id = str(row.get('object_id', '')).strip()
        original_id = object_id
        modified = False

        # Check for file extensions and strip them (shared canonical set)
        for ext in IMAGE_EXTENSIONS:
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
    return df


def _apply_alt_text_fallback(df):
    """An object with no alt text describes itself with its title."""
    # Alt text fallback: use title if alt_text is empty
    if 'alt_text' not in df.columns:
        df['alt_text'] = ''
    for idx, row in df.iterrows():
        if not str(row.get('alt_text', '')).strip():
            df.at[idx, 'alt_text'] = str(row.get('title', '')).strip()
    return df


def _validate_thumbnails(df, warnings):
    """Clear what is not a thumbnail, and check that what is, is there.

    Placeholder values a spreadsheet collects (`n/a`, `none`) are cleared
    rather than warned about; a doubled slash is normalised; a path naming a
    file that is absent is reported but left, because the file may arrive
    before the next build.
    """
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
    return df


def _load_previous_objects():
    """What the last build knew, keyed by object id.

    Only used to forgive a 429: rate limiting is the server's state, not the
    site's, so a manifest that validated last time is not failed for it now.
    An unreadable file is not an error — it means there is no last time.
    """
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
    return previous_objects
