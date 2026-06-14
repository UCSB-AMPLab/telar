"""
Media-type detection (leaf module)

Single source of truth for the gallery "Type" facet
(Video / Audio / 3D Model / Image). Kept dependency-free (standard library
only) so both `generate_collections.py` and `telar.search` can import it
without a circular import — previously each carried its own hand-copied
implementation that could silently diverge.

Version: v1.6.0
"""

from pathlib import Path

# Source-URL substrings that mark an object as video, and the audio / 3D-model
# file extensions probed on disk. Imported by callers so the lists never drift.
VIDEO_URL_PATTERNS = ['youtube.com', 'youtu.be', 'vimeo.com', 'drive.google.com']
AUDIO_EXTENSIONS = ['.mp3', '.ogg', '.m4a', '.MP3', '.OGG', '.M4A']
MODEL_EXTENSIONS = ['.glb', '.gltf', '.GLB', '.GLTF']


def detect_media_type(source_url, object_id):
    """Detect an object's media type for the gallery Type filter.

    Checks the source URL for known video hosts first, then probes
    telar-content/objects/ for an audio file, then a 3D model file matching
    object_id. Defaults to 'Image'.

    Args:
        source_url: The object's source_url field (may be None or empty).
        object_id:  The object's ID, used to find a matching local file on disk.

    Returns:
        str: 'Video', 'Audio', 'Model', or 'Image'.
    """
    url = (source_url or '').strip()
    if any(pat in url for pat in VIDEO_URL_PATTERNS):
        return 'Video'

    objects_dir = Path('telar-content/objects')
    if objects_dir.exists():
        for ext in AUDIO_EXTENSIONS:
            if (objects_dir / f'{object_id}{ext}').exists():
                return 'Audio'
        for ext in MODEL_EXTENSIONS:
            if (objects_dir / f'{object_id}{ext}').exists():
                return 'Model'

    return 'Image'
