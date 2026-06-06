"""
Media-type detection (leaf module)

Single source of truth for the gallery "Type" facet (Video / Audio / Image).
Kept dependency-free (standard library only) so both `generate_collections.py`
and `telar.search` can import it without a circular import — previously each
carried its own hand-copied implementation that could silently diverge.

Version: v1.5.0
"""

from pathlib import Path

# Source-URL substrings that mark an object as video, and the audio file
# extensions probed on disk. Imported by callers so the lists never drift.
VIDEO_URL_PATTERNS = ['youtube.com', 'youtu.be', 'vimeo.com', 'drive.google.com']
AUDIO_EXTENSIONS = ['.mp3', '.ogg', '.m4a', '.MP3', '.OGG', '.M4A']


def detect_media_type(source_url, object_id):
    """Detect an object's media type for the gallery Type filter.

    Checks the source URL for known video hosts first, then looks for an audio
    file matching object_id in telar-content/objects/. Defaults to 'Image'.

    Args:
        source_url: The object's source_url field (may be None or empty).
        object_id:  The object's ID, used to find a matching audio file on disk.

    Returns:
        str: 'Video', 'Audio', or 'Image'.
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
