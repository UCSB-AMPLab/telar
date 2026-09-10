"""
Objects Processor

This module deals with converting the objects CSV into validated JSON for
every exhibition object in a Telar story. Objects are the visual artefacts
that appear in the viewer panel — maps, paintings, photographs, manuscripts
— each identified by an `object_id` that links to either an external IIIF
manifest or a local image file in `telar-content/objects/`.

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
   errors for manifests that haven't changed. This step is media-aware:
   objects classified as Video or Audio (see step 7) skip IIIF validation
   entirely — video objects are instead checked against a list of
   recognised hosts (YouTube, Vimeo, Google Drive), and audio objects are
   served from local files rather than manifests.

5. **IIIF metadata extraction** — when a manifest validates successfully,
   extracts title, description, creator, period, source, and credit — plus the
   structured facets year, medium, and subjects — using the functions from the
   iiif_metadata module, then applies the fallback hierarchy (CSV values always
   win over IIIF values).

6. **Local source fallback** — objects without an external manifest are
   checked for a matching file in `telar-content/objects/`. Audio objects
   look for an audio file (`.mp3`, `.ogg`, `.m4a`) and optionally a
   precomputed waveform peaks file under `assets/audio/peaks/`; everything
   else looks for a matching image. If no exact image match is found,
   `_find_similar_image_filenames()` uses fuzzy string matching (via
   `difflib.SequenceMatcher` at 85% threshold) to suggest near-matches like
   case differences or hyphen/underscore variations.

7. **Media-type classification** — every object is tagged with a
   `media_type` of Video, Audio, or Image, written into `objects.json` so
   that downstream consumers (search indexing, Liquid templates) read the
   type directly instead of re-detecting it from disk on every build pass.
   The persisted value comes from the canonical URL-based detector in
   `telar.media_type`; an earlier, disk-aware local variant
   (`_detect_media_type()`) drives the validation branching in steps 4 and 6.

8. **Featured-object selection** — `_select_featured_objects()` decides
   which objects appear in the homepage sample by setting an
   `is_featured_sample` flag for Liquid to filter on. When the site config
   enables the homepage sample, any objects explicitly flagged `featured`
   win; otherwise the function draws a random sample (size from
   `featured_count`, default 4) from the objects that validated cleanly. The
   draw is reproducible across builds of unchanged content: the RNG is
   seeded from a SHA-256 hash of the sorted object indices rather than the
   process-salted built-in `hash()`, so the same content always yields the
   same featured set.

`inject_christmas_tree_errors()` is a testing helper that appends fake
objects with intentionally broken IIIF URLs (404, 500, 503, 429, invalid)
to exercise every warning code path. These test objects are marked with a
Christmas tree emoji in their titles for easy identification.

Version: v1.7.0
"""

from telar.media_type import detect_media_type

from telar.processors.objects.christmas_tree import inject_christmas_tree_errors
from telar.processors.objects.featured import _select_featured_objects
from telar.processors.objects.frame import (
    _apply_alt_text_fallback, _clean_object_ids, _load_previous_objects,
    _normalise_frame, _validate_thumbnails,
)
from telar.processors.objects.local import (
    _find_similar_image_filenames, _validate_local_sources,
)
from telar.processors.objects.remote import _validate_source_urls

# Re-exported: csv_to_json imports the near-match suggester by name, and
# the package has to keep the surface objects.py had.
__all__ = [
    'process_objects', 'inject_christmas_tree_errors',
    '_find_similar_image_filenames',
]


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
    # One function per step, in the order the module docstring lists
    # them. Only `warnings` is shared, and only as an accumulator: it is
    # what the summary at the end counts.
    warnings = []

    df = _normalise_frame(df, christmas_tree)
    df = _apply_alt_text_fallback(df)
    df = _clean_object_ids(df, warnings)
    df = _validate_thumbnails(df, warnings)
    df = _validate_source_urls(df, _load_previous_objects(), warnings)
    df = _validate_local_sources(df, warnings)

    # Print summary if there were issues
    if warnings:
        print(f"\n  Objects validation summary: {len(warnings)} warning(s)")

    # Final cleanup: ensure no NaN values in output
    # (new columns added via IIIF extraction may leave NaN for objects without IIIF)
    df = df.fillna('')

    # Persist the gallery media type (Video/Audio/Image) into objects.json so
    # search.py and templates read it directly instead of re-detecting it from
    # disk on every build pass. Uses the shared telar.media_type leaf module.
    df['media_type'] = [
        detect_media_type(row.get('source_url', ''), row.get('object_id', ''))
        for _, row in df.iterrows()
    ]

    # Featured objects selection for homepage display
    # Mark objects with is_featured_sample: true for Liquid to filter
    df = _select_featured_objects(df)

    return df
