"""
Tests for process_audio.py — Build-time audio processing script.

Covers pure functions:
  - convert_audiowaveform_to_peaks: format conversion + normalisation
  - is_audio_file: extension detection
  - compute_cache_key: SHA256 hashing for skip-if-unchanged caching
  - check_audio_dependencies: system tool detection
  - find_audio_objects: objects.json filtering for audio files
  - build_clip_filename: clip output filename construction
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Import target module
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts'))
from process_audio import (
    convert_audiowaveform_to_peaks,
    is_audio_file,
    compute_cache_key,
    check_audio_dependencies,
    find_audio_objects,
    build_clip_filename,
)


# ---------------------------------------------------------------------------
# Test 1: convert_audiowaveform_to_peaks — 16-bit mono
# ---------------------------------------------------------------------------

def test_convert_audiowaveform_to_peaks_16bit_mono():
    """16-bit mono input returns normalised floats in [0,1] range with correct structure."""
    aw_data = {
        'data': [-10000, 20000, -5000, 32767, 0, 16384],
        'bits': 16,
        'channels': 1,
        'length': 3,
    }
    result = convert_audiowaveform_to_peaks(aw_data)

    assert 'peaks' in result
    assert 'length' in result
    assert result['length'] == 3
    assert isinstance(result['peaks'], list)
    assert len(result['peaks']) == 1  # 1 channel
    channel_peaks = result['peaks'][0]
    assert len(channel_peaks) == 3  # 3 pixel-pairs

    # Values should be max values normalised by 32767
    # Sample 0: max = 20000, normalised = 20000/32767 ≈ 0.6105
    assert abs(channel_peaks[0] - 20000 / 32767) < 0.001
    # Sample 1: max = 32767, normalised = 1.0
    assert abs(channel_peaks[1] - 32767 / 32767) < 0.001
    # Sample 2: max = 16384, normalised = 16384/32767 ≈ 0.5
    assert abs(channel_peaks[2] - 16384 / 32767) < 0.001

    # All values must be in [0, 1]
    for v in channel_peaks:
        assert 0.0 <= v <= 1.0, f"Value {v} out of [0,1] range"


# ---------------------------------------------------------------------------
# Test 2: convert_audiowaveform_to_peaks — 8-bit stereo
# ---------------------------------------------------------------------------

def test_convert_audiowaveform_to_peaks_8bit_stereo():
    """8-bit stereo input correctly splits channels and normalises by 127."""
    # Interleaved: [min_ch0, max_ch0, min_ch1, max_ch1, ...]
    # One sample, 2 channels: ch0_max=100, ch1_max=64
    aw_data = {
        'data': [-50, 100, -30, 64],
        'bits': 8,
        'channels': 2,
        'length': 1,
    }
    result = convert_audiowaveform_to_peaks(aw_data)

    assert len(result['peaks']) == 2  # 2 channels
    assert result['length'] == 1

    # Channel 0: max=100, normalised by 127
    assert abs(result['peaks'][0][0] - 100 / 127) < 0.001
    # Channel 1: max=64, normalised by 127
    assert abs(result['peaks'][1][0] - 64 / 127) < 0.001


# ---------------------------------------------------------------------------
# Test 3: convert_audiowaveform_to_peaks — empty data
# ---------------------------------------------------------------------------

def test_convert_audiowaveform_to_peaks_empty():
    """Empty data array returns {'peaks': [[]], 'length': 0}."""
    aw_data = {
        'data': [],
        'bits': 16,
        'channels': 1,
        'length': 0,
    }
    result = convert_audiowaveform_to_peaks(aw_data)

    assert result == {'peaks': [[]], 'length': 0}


# ---------------------------------------------------------------------------
# Test 4: is_audio_file — extension detection
# ---------------------------------------------------------------------------

def test_is_audio_file():
    """Returns True for audio extensions (case-insensitive), False for others."""
    # True cases
    assert is_audio_file('interview.mp3') is True
    assert is_audio_file('music.ogg') is True
    assert is_audio_file('recording.m4a') is True
    assert is_audio_file('INTERVIEW.MP3') is True
    assert is_audio_file('track.OGG') is True
    assert is_audio_file('clip.M4A') is True

    # False cases
    assert is_audio_file('photo.jpg') is False
    assert is_audio_file('document.pdf') is False
    assert is_audio_file('notes.txt') is False
    assert is_audio_file('audio') is False  # no extension
    assert is_audio_file('') is False


# ---------------------------------------------------------------------------
# Test 5: compute_cache_key — different inputs produce different keys
# ---------------------------------------------------------------------------

def test_compute_cache_key_different_inputs():
    """Different file content or different clip params produce different hashes."""
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f1:
        f1.write(b'audio content A')
        path1 = f1.name

    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f2:
        f2.write(b'audio content B')
        path2 = f2.name

    key1 = compute_cache_key(path1)
    key2 = compute_cache_key(path2)
    assert key1 != key2

    # Same file, different clip params
    key3 = compute_cache_key(path1, clip_start=0, clip_end=30)
    key4 = compute_cache_key(path1, clip_start=30, clip_end=60)
    assert key3 != key4

    # Clip params vs no clip params
    key5 = compute_cache_key(path1)
    key6 = compute_cache_key(path1, clip_start=0, clip_end=30)
    assert key5 != key6


# ---------------------------------------------------------------------------
# Test 6: compute_cache_key — same inputs produce same key
# ---------------------------------------------------------------------------

def test_compute_cache_key_same_inputs():
    """Same file content and clip params produce the same hash."""
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
        f.write(b'stable audio content')
        path = f.name

    key1 = compute_cache_key(path, clip_start=10, clip_end=40)
    key2 = compute_cache_key(path, clip_start=10, clip_end=40)
    assert key1 == key2

    # Hex digest format (SHA256 = 64 hex chars)
    assert len(key1) == 64
    assert all(c in '0123456789abcdef' for c in key1)


# ---------------------------------------------------------------------------
# Test 7: check_audio_dependencies — audiowaveform missing
# ---------------------------------------------------------------------------

def test_check_audio_dependencies_missing_audiowaveform():
    """Raises SystemExit with message containing 'audiowaveform' when not found."""
    with patch('shutil.which', side_effect=lambda tool: None if tool == 'audiowaveform' else '/usr/bin/ffmpeg'):
        with pytest.raises(SystemExit):
            check_audio_dependencies()


def test_check_audio_dependencies_missing_audiowaveform_message(capsys):
    """Error message must contain 'audiowaveform'."""
    with patch('shutil.which', side_effect=lambda tool: None if tool == 'audiowaveform' else '/usr/bin/ffmpeg'):
        with pytest.raises(SystemExit):
            check_audio_dependencies()
        captured = capsys.readouterr()
        assert 'audiowaveform' in captured.out or 'audiowaveform' in captured.err


# ---------------------------------------------------------------------------
# Test 8: check_audio_dependencies — ffmpeg missing
# ---------------------------------------------------------------------------

def test_check_audio_dependencies_missing_ffmpeg():
    """Raises SystemExit with message containing 'ffmpeg' when not found."""
    with patch('shutil.which', side_effect=lambda tool: None if tool == 'ffmpeg' else '/usr/local/bin/audiowaveform'):
        with pytest.raises(SystemExit):
            check_audio_dependencies()


def test_check_audio_dependencies_missing_ffmpeg_message(capsys):
    """Error message must contain 'ffmpeg'."""
    with patch('shutil.which', side_effect=lambda tool: None if tool == 'ffmpeg' else '/usr/local/bin/audiowaveform'):
        with pytest.raises(SystemExit):
            check_audio_dependencies()
        captured = capsys.readouterr()
        assert 'ffmpeg' in captured.out or 'ffmpeg' in captured.err


# ---------------------------------------------------------------------------
# Test 9: find_audio_objects — filters to audio files only
# ---------------------------------------------------------------------------

def test_find_audio_objects():
    """Filters objects.json to only those with audio files present in objects/."""
    objects_data = [
        {'object_id': 'interview-hernandez'},
        {'object_id': 'landscape-bogota', 'source_url': ''},
        {'object_id': 'document-carta'},
        {'object_id': 'song-cumbia'},
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        objects_dir = tmpdir / 'objects'
        objects_dir.mkdir()
        data_dir = tmpdir / '_data'
        data_dir.mkdir()

        # Create audio files for two objects
        (objects_dir / 'interview-hernandez.mp3').write_bytes(b'fake mp3')
        (objects_dir / 'song-cumbia.ogg').write_bytes(b'fake ogg')
        # landscape-bogota and document-carta have no audio files

        objects_json_path = data_dir / 'objects.json'
        objects_json_path.write_text(json.dumps(objects_data))

        results = find_audio_objects(objects_json_path, objects_dir)

    assert len(results) == 2
    result_ids = {r['object_id'] for r in results}
    assert 'interview-hernandez' in result_ids
    assert 'song-cumbia' in result_ids
    assert 'landscape-bogota' not in result_ids
    assert 'document-carta' not in result_ids

    # Each result must have object_id, file_path, extension
    for r in results:
        assert 'object_id' in r
        assert 'file_path' in r
        assert 'extension' in r


# ---------------------------------------------------------------------------
# Test 10: build_clip_filename — output filename format
# ---------------------------------------------------------------------------

def test_build_clip_filename():
    """Returns '{object_id}-{clip_start}-{clip_end}.{extension}' format."""
    result = build_clip_filename('interview-hernandez', 330, 435, 'mp3')
    assert result == 'interview-hernandez-330-435.mp3'

    result2 = build_clip_filename('song-cumbia', 0, 60, 'ogg')
    assert result2 == 'song-cumbia-0-60.ogg'

    result3 = build_clip_filename('track', 10, 20, 'm4a')
    assert result3 == 'track-10-20.m4a'
