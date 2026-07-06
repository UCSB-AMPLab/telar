#!/usr/bin/env python3
"""
Process Audio Objects for Story Cards

Some exhibition objects are not images but audio recordings — an oral
history, a musical performance, a field recording. When these appear in
a Telar story, the viewer background becomes a full-viewport waveform
visualisation powered by WaveSurfer.

WaveSurfer is an open-source MIT-licensed audio waveform library that
renders interactive waveforms from peak data in a canvas element. It
was chosen because it is lightweight, has no runtime dependencies, and
can render a waveform instantly from pre-computed peaks without decoding
the audio file in the browser. Like Lenis (the scroll engine), it is
bundled by esbuild into the single telar-story.js file — no CDN, no
external requests — keeping Telar fully self-contained and aligned with
its minimal-computing, zero-dependency hosting model.

To make waveform rendering instant, the browser needs pre-computed peak
data rather than decoding the entire audio file at load time. This
script handles that preparation. It scans the objects directory for
audio files (MP3, OGG, M4A), generates peak data using bbc/audiowaveform
(an open-source tool that reads audio samples and outputs amplitude
values at a given resolution), and converts the output into the JSON
format that WaveSurfer v7 consumes directly. Clip boundaries (clip_start /
clip_end) are enforced client-side — the browser loads the full peak data
and audio file, and WaveSurfer's timeupdate event confines playback to the
requested region (see assets/js/telar-story/audio-card.js). This script
does not pre-extract clip segments.

The output structure mirrors the IIIF tile pipeline: peak JSON files go
to assets/audio/peaks/, and cache files sit alongside them so that
unchanged audio is not reprocessed on subsequent builds. Like the IIIF
tile generator, this script is optional — sites without audio objects
skip it entirely, and the CI workflow detects this automatically.

audiowaveform is required only for sites that include audio objects. It
is not a Python package — it is a system-level tool installed via the
platform's package manager (brew on macOS, apt on Linux). The CI
workflow installs it conditionally when audio files are detected.

The _data/audio_objects.json manifest (object_id -> file extension,
consumed by story.html to inject window.audioObjects) is written by
telar.core._generate_audio_manifest, not by this script. That function
runs unconditionally as part of every csv_to_json.py build, including
builds that skip this script entirely (no audio files, or cached/
unchanged audio), so it is the single source of truth for the manifest
and owns its stale-entry cleanup.

Version: v1.6.0
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from telar.media_type import AUDIO_EXTENSIONS


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# object_id is interpolated into filesystem write paths (peaks, cache),
# so it must be a bare slug. Anything with a path separator or ".." is rejected
# at ingest so a crafted object_id cannot write outside the audio output dirs.
_SAFE_OBJECT_ID = re.compile(r'^[A-Za-z0-9_-]+$')


def is_safe_object_id(object_id):
    """Return True if object_id is a bare slug safe to use in a file path."""
    return bool(_SAFE_OBJECT_ID.match(object_id))


# ---------------------------------------------------------------------------
# Pure functions (unit-tested)
# ---------------------------------------------------------------------------

def convert_audiowaveform_to_peaks(aw_data):
    """
    Convert audiowaveform JSON to Telar peaks format (WaveSurfer v7 compatible).

    audiowaveform produces interleaved min/max integer pairs per channel:
        [min_ch0, max_ch0, min_ch1, max_ch1, ...]

    WaveSurfer v7 expects one float array per channel, values normalised to [0, 1]:
        {"peaks": [[float, float, ...], [float, float, ...]], "length": N}

    We extract the max values only (positive peak per pixel) and normalise by
    32767 (16-bit) or 127 (8-bit). WaveSurfer mirrors the waveform above and
    below the axis from these positive peaks.

    Args:
        aw_data (dict): audiowaveform JSON output with keys: data, bits,
                        channels, length.

    Returns:
        dict: {"peaks": [[float, ...], ...], "length": int}
    """
    data = aw_data.get('data', [])
    bits = aw_data.get('bits', 16)
    channels = aw_data.get('channels', 1)
    length = aw_data.get('length', 0)
    divisor = 32767 if bits == 16 else 127

    channel_peaks = [[] for _ in range(channels)]
    step = channels * 2  # min + max per channel

    for i in range(0, len(data), step):
        for ch in range(channels):
            offset = i + ch * 2
            # max value is at offset+1 (the second of the min/max pair)
            raw_max = data[offset + 1] if offset + 1 < len(data) else 0
            channel_peaks[ch].append(raw_max / divisor)

    return {'peaks': channel_peaks, 'length': length}


def compute_cache_key(audio_path):
    """
    Compute a SHA256 cache key from the audio file content.

    The cache key changes when the source file changes, ensuring
    re-processing happens only when necessary.

    Args:
        audio_path (str | Path): Path to the source audio file.

    Returns:
        str: 64-character hex SHA256 digest.
    """
    h = hashlib.sha256()

    with open(audio_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)

    return h.hexdigest()


def check_audio_dependencies():
    """
    Check that audiowaveform is installed and accessible.

    Exits with a clear error message if it is missing, with install
    instructions. audiowaveform is the only external tool this script
    invokes. It decodes MP3 and Ogg natively; for M4A it fails, which
    generate_peaks treats as a per-file skip — the player falls back to
    client-side decoding, so M4A objects play without pre-computed peaks.

    Raises:
        SystemExit: If audiowaveform is not found.
    """
    for tool in ('audiowaveform',):
        if shutil.which(tool) is None:
            print(
                f"Error: {tool} is not installed. "
                f"Install with: brew install {tool} (macOS) or "
                f"apt-get install {tool} (Linux)"
            )
            sys.exit(1)


def find_audio_objects(objects_json_path, objects_dir):
    """
    Load objects.json and filter to objects that have an audio source file.

    For each object, checks whether a file named {object_id} plus a supported
    audio extension (.mp3, .ogg, .m4a — lower or upper case) exists in
    objects_dir. Lowercase extensions take precedence when both exist.

    Args:
        objects_json_path (str | Path): Path to _data/objects.json.
        objects_dir (str | Path): Directory containing source audio files.

    Returns:
        list[dict]: List of dicts with keys: object_id (str), file_path (Path),
                    extension (str).
    """
    objects_json_path = Path(objects_json_path)
    objects_dir = Path(objects_dir)

    with open(objects_json_path, 'r', encoding='utf-8') as f:
        objects = json.load(f)

    results = []
    for obj in objects:
        object_id = obj.get('object_id', '').strip()
        if not object_id:
            continue

        # Guard every downstream write path (peaks/cache) at the single
        # point of ingest: a non-slug object_id is skipped, not processed.
        if not is_safe_object_id(object_id):
            print(f"  [WARN] Skipping object with unsafe object_id "
                  f"(allowed: letters, digits, hyphen, underscore): {object_id!r}")
            continue

        for ext in AUDIO_EXTENSIONS:
            candidate = objects_dir / f'{object_id}{ext}'
            if candidate.exists():
                results.append({
                    'object_id': object_id,
                    'file_path': candidate,
                    'extension': ext.lstrip('.'),
                })
                break  # First match wins; don't add duplicate entries

    return results


# ---------------------------------------------------------------------------
# Processing functions (integration — require audiowaveform)
# ---------------------------------------------------------------------------

def generate_peaks(audio_path, output_path, pixels_per_second=100):
    """
    Generate a WaveSurfer-compatible peaks JSON file for an audio file.

    Runs audiowaveform CLI to produce raw peak data, converts the output to
    Telar peaks format, and writes the result to output_path.

    Args:
        audio_path (Path): Source audio file.
        output_path (Path): Destination JSON path (assets/audio/peaks/{id}.json).
        pixels_per_second (int): Waveform resolution (default: 100).

    Returns:
        bool: True on success, False on failure.
    """
    audio_path = Path(audio_path)
    output_path = Path(output_path)

    stem = audio_path.stem
    with tempfile.NamedTemporaryFile(suffix='-raw.json', prefix=f'{stem}-', delete=False) as tmp:
        raw_json_path = tmp.name

    try:
        result = subprocess.run(
            [
                'audiowaveform',
                '-i', str(audio_path),
                '-o', raw_json_path,
                '--pixels-per-second', str(pixels_per_second),
                '--bits', '16',
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        with open(raw_json_path, 'r', encoding='utf-8') as f:
            aw_data = json.load(f)

        peaks_data = convert_audiowaveform_to_peaks(aw_data)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(peaks_data, f)

        return True

    except subprocess.CalledProcessError as e:
        print(f'  Error running audiowaveform: {e.stderr}')
        return False
    except Exception as e:
        print(f'  Error generating peaks: {e}')
        return False
    finally:
        try:
            os.unlink(raw_json_path)
        except OSError:
            pass


def process_audio_objects(objects_dir, data_dir, output_dir,
                          pixels_per_second=100, filter_objects=None):
    """
    Batch-process all audio objects: generate peaks.

    For each audio object found in objects_dir:
    1. Check cache (skip if source file unchanged and output exists).
    2. Generate peaks JSON via audiowaveform.
    3. Write cache key file.

    Args:
        objects_dir (str | Path): Directory containing source audio files.
        data_dir (str | Path): Directory containing objects.json.
        output_dir (str | Path): Output base directory (assets/audio/).
        pixels_per_second (int): Waveform resolution passed to audiowaveform.
        filter_objects (str | None): Comma-separated object IDs to restrict processing.

    Returns:
        bool: True on completion (partial failures are logged but don't abort).
    """
    objects_dir = Path(objects_dir)
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    peaks_dir = output_dir / 'peaks'

    peaks_dir.mkdir(parents=True, exist_ok=True)

    objects_json_path = data_dir / 'objects.json'
    if not objects_json_path.exists():
        print(f'Error: objects.json not found at {objects_json_path}')
        print('Run csv_to_json.py first to generate it.')
        return False

    audio_objects = find_audio_objects(objects_json_path, objects_dir)

    if not audio_objects:
        print('No audio objects found in objects/')
        return True

    # Apply filter if specified
    if filter_objects:
        requested = {o.strip() for o in filter_objects.split(',')}
        audio_objects = [o for o in audio_objects if o['object_id'] in requested]
        if not audio_objects:
            print(f'No matching audio objects for filter: {filter_objects}')
            return True

    print('=' * 60)
    print('Audio Processor for Telar')
    print('=' * 60)
    print(f'Objects dir: {objects_dir}')
    print(f'Output dir: {output_dir}')
    print(f'Audio objects found: {len(audio_objects)}')
    print('=' * 60)
    print()

    processed_count = 0
    skipped_count = 0

    for i, obj in enumerate(audio_objects, 1):
        object_id = obj['object_id']
        audio_path = obj['file_path']

        print(f'[{i}/{len(audio_objects)}] {object_id}...')

        # --- Cache check ---
        cache_path = peaks_dir / f'{object_id}.cache'
        peaks_path = peaks_dir / f'{object_id}.json'
        current_key = compute_cache_key(audio_path)

        if cache_path.exists() and peaks_path.exists():
            cached_key = cache_path.read_text(encoding='utf-8').strip()
            if cached_key == current_key:
                print(f'  Skipped (unchanged)')
                skipped_count += 1
                print()
                continue

        # --- Generate peaks ---
        print(f'  Generating peaks from {audio_path.name}...')
        success = generate_peaks(audio_path, peaks_path, pixels_per_second)
        if not success:
            print(f'  Failed to generate peaks for {object_id}')
            print()
            continue

        # Write cache key
        cache_path.write_text(current_key, encoding='utf-8')
        print(f'  Peaks written to {peaks_path}')

        processed_count += 1
        print()

    # _data/audio_objects.json is written by telar.core._generate_audio_manifest
    # as part of the csv_to_json.py build step, not here (see module docstring).

    print('=' * 60)
    print('Audio processing complete!')
    print(f'  Processed: {processed_count} objects')
    if skipped_count > 0:
        print(f'  Skipped (cached): {skipped_count} objects')
    print(f'  Peaks directory: {peaks_dir}')
    print('=' * 60)

    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Main entry point — parse arguments and run audio processing."""
    parser = argparse.ArgumentParser(
        description=(
            'Generate WaveSurfer peak data for Telar audio cards. '
            'Requires audiowaveform to be installed.'
        )
    )
    parser.add_argument(
        '--objects-dir',
        default='objects',
        help='Directory containing source audio files (default: objects/)',
    )
    parser.add_argument(
        '--data-dir',
        default='_data',
        help='Directory containing objects.json (default: _data/)',
    )
    parser.add_argument(
        '--output-dir',
        default='assets/audio',
        help='Output base directory for peaks/ (default: assets/audio/)',
    )
    parser.add_argument(
        '--pixels-per-second',
        type=int,
        default=100,
        help='Waveform resolution: samples per second of audio (default: 100)',
    )
    parser.add_argument(
        '--filter-objects',
        default=None,
        help='Comma-separated object IDs to process (default: all audio objects)',
    )

    args = parser.parse_args()

    check_audio_dependencies()

    success = process_audio_objects(
        objects_dir=args.objects_dir,
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        pixels_per_second=args.pixels_per_second,
        filter_objects=args.filter_objects,
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
