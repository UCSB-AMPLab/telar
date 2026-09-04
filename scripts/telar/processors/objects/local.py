"""Resolving an object against the files beside it.

The disk-aware media-type variant that steers validation, the near-match
suggester for a filename that does not quite line up, and the checks for a
local image or audio file. Nothing here reaches the network.

Version: v1.7.0
"""

import re
from difflib import SequenceMatcher
from pathlib import Path

from telar.config import get_lang_string
from telar.csv_utils import IMAGE_EXTENSIONS, build_stem_index, get_source_url
from telar.media_type import AUDIO_EXTENSIONS, VIDEO_URL_PATTERNS


def _detect_media_type(source_url, object_id):
    """Classify an object as Video, Audio, or Image, consulting the disk.

    This is a local, disk-aware variant used to steer validation: it returns
    Video for known video hosts, then probes `telar-content/objects/` for an
    audio file matching `object_id` (so audio objects skip IIIF validation and
    are routed to the local-file checks), and otherwise falls back to Image.

    The canonical media-type detector is `telar.media_type.detect_media_type`
    (imported in this module), which classifies purely from the source URL and
    supplies the `media_type` value persisted into objects.json. This function
    differs only in that it also inspects the filesystem, which the URL-based
    detector deliberately does not.
    """
    url = (source_url or '').strip()
    if any(pat in url for pat in VIDEO_URL_PATTERNS):
        return 'Video'
    objects_dir = Path('telar-content/objects')
    if objects_dir.exists():
        for ext in AUDIO_EXTENSIONS:
            if (objects_dir / f'{object_id}{ext}').exists():
                return 'Audio'
    return 'Image'


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

        # Only an identical stem belongs to the exact-match path. A stem
        # differing in case does not: the stem index is keyed on the exact
        # name, and the site is built on a case-sensitive filesystem even
        # when the author's own machine is not, so nothing else will find it.
        if basename == object_id:
            continue

        # Calculate similarity ratio
        similarity = SequenceMatcher(None, normalized_id, normalized_file).ratio()

        # Consider similar if > 85% match
        if similarity > 0.85:
            similar_files.append(file_path.name)

    return similar_files


def _validate_local_sources(df, warnings):
    """Objects with no manifest must have a file, and audio needs its own.

    The directory is indexed once: a per-object `iterdir` scan is quadratic on
    a site with many objects.
    """
    # Validate that objects have either source URL (IIIF manifest) OR local image file.
    # Index telar-content/objects once so the per-object existence check is an O(1)
    # lookup rather than an iterdir scan per object.
    _obj_file_index = build_stem_index('telar-content/objects')
    for idx, row in df.iterrows():
        object_id = row.get('object_id', 'unknown')
        source_url = get_source_url(row)

        # Skip if already has a valid source URL
        if source_url:
            continue

        # Audio objects need audio files, not images — validate accordingly
        obj_media_type = _detect_media_type('', object_id)
        if obj_media_type == 'Audio':
            _validate_local_audio(df, idx, object_id, warnings)
            continue

        # No external IIIF manifest - check for local image file (O(1) index lookup;
        # the shared extension set covers all image types, including .bmp/.svg)
        has_local_image = False
        for f in _obj_file_index.get(object_id, []):
            if f.suffix.lower() in IMAGE_EXTENSIONS:
                has_local_image = True
                print(f"  [INFO] Object {object_id} uses local image: {f}")
                break

        # Warn if object has neither external manifest nor local image
        if not has_local_image:
            # Check for similar filenames (near-matches)
            similar_files = _find_similar_image_filenames(object_id, Path('telar-content/objects'))

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
    return df


def _validate_local_audio(df, idx, object_id, warnings):
    """An audio object is served from a file beside it, not a manifest.

    The peaks file is optional: without it the player decodes the audio
    itself, which is slower but works, so its absence is said once and
    not counted as a warning.
    """
    # Find which audio extension matches
    audio_dir = Path('telar-content/objects')
    audio_found = None
    if audio_dir.exists():
        for ext in AUDIO_EXTENSIONS:
            audio_path = audio_dir / f'{object_id}{ext}'
            if audio_path.exists():
                audio_found = audio_path
                break
    if audio_found:
        print(f"  [INFO] Object {object_id} uses local audio: {audio_found}")
        # Check for peaks JSON (optional but recommended)
        peaks_path = Path(f'assets/audio/peaks/{object_id}.json')
        if not peaks_path.exists():
            print(f"  [INFO] No peaks file for audio object {object_id} — WaveSurfer will decode on the fly")
    else:
        error_msg = get_lang_string('errors.object_warnings.audio_missing', object_id=object_id)
        df.at[idx, 'object_warning'] = error_msg
        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_audio_missing')
        msg = f"Object {object_id} has no audio file in telar-content/objects/"
        print(f"  [WARN] {msg}")
        warnings.append(msg)
