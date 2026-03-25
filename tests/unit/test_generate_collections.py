"""
Unit Tests for generate_collections.py

Tests focus on the media_type detection logic and the
source_url injection for video objects. The generate_objects()
function is integration-tested via the media_type detection helper.

Version: v1.0.0-beta
"""

import sys
import os
import json
import pytest
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))


class TestDetectMediaType:
    """Tests for detect_media_type() helper function."""

    def test_youtube_url_is_video(self):
        """YouTube source_url produces 'Video' media type."""
        from generate_collections import detect_media_type
        assert detect_media_type('https://www.youtube.com/watch?v=abc123', 'obj1') == 'Video'

    def test_youtu_be_shortlink_is_video(self):
        """Shortened youtu.be URL produces 'Video' media type."""
        from generate_collections import detect_media_type
        assert detect_media_type('https://youtu.be/abc123', 'obj1') == 'Video'

    def test_vimeo_url_is_video(self):
        """Vimeo source_url produces 'Video' media type."""
        from generate_collections import detect_media_type
        assert detect_media_type('https://vimeo.com/123456789', 'obj1') == 'Video'

    def test_google_drive_url_is_video(self):
        """Google Drive source_url produces 'Video' media type."""
        from generate_collections import detect_media_type
        assert detect_media_type('https://drive.google.com/file/d/abc/view', 'obj1') == 'Video'

    def test_iiif_manifest_url_is_image(self):
        """IIIF manifest URL is not a video source — produces 'Image'."""
        from generate_collections import detect_media_type
        assert detect_media_type('https://example.com/manifest.json', 'obj1') == 'Image'

    def test_empty_source_url_is_image(self):
        """Empty source_url produces 'Image' (default)."""
        from generate_collections import detect_media_type
        assert detect_media_type('', 'obj1') == 'Image'

    def test_none_source_url_is_image(self):
        """None source_url produces 'Image' (default)."""
        from generate_collections import detect_media_type
        assert detect_media_type(None, 'obj1') == 'Image'

    def test_audio_file_is_audio(self, tmp_path):
        """Object with matching .mp3 file in telar-content/objects/ produces 'Audio'."""
        from generate_collections import detect_media_type
        # Create audio file in expected location
        objects_dir = tmp_path / 'telar-content' / 'objects'
        objects_dir.mkdir(parents=True)
        (objects_dir / 'audio-obj.mp3').touch()

        orig_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = detect_media_type('', 'audio-obj')
        finally:
            os.chdir(orig_dir)

        assert result == 'Audio'

    def test_ogg_audio_file_is_audio(self, tmp_path):
        """Object with matching .ogg file produces 'Audio'."""
        from generate_collections import detect_media_type
        objects_dir = tmp_path / 'telar-content' / 'objects'
        objects_dir.mkdir(parents=True)
        (objects_dir / 'audio-obj.ogg').touch()

        orig_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = detect_media_type('', 'audio-obj')
        finally:
            os.chdir(orig_dir)

        assert result == 'Audio'

    def test_m4a_audio_file_is_audio(self, tmp_path):
        """Object with matching .m4a file produces 'Audio'."""
        from generate_collections import detect_media_type
        objects_dir = tmp_path / 'telar-content' / 'objects'
        objects_dir.mkdir(parents=True)
        (objects_dir / 'audio-obj.m4a').touch()

        orig_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = detect_media_type('', 'audio-obj')
        finally:
            os.chdir(orig_dir)

        assert result == 'Audio'

    def test_no_audio_file_is_image(self, tmp_path):
        """Object with no matching audio file and no video URL produces 'Image'."""
        from generate_collections import detect_media_type
        # Create objects dir but no matching file
        objects_dir = tmp_path / 'telar-content' / 'objects'
        objects_dir.mkdir(parents=True)

        orig_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = detect_media_type('', 'no-audio-obj')
        finally:
            os.chdir(orig_dir)

        assert result == 'Image'

    def test_video_url_takes_priority_over_audio_file(self, tmp_path):
        """Video source_url takes priority if there's also an audio file (edge case)."""
        from generate_collections import detect_media_type
        objects_dir = tmp_path / 'telar-content' / 'objects'
        objects_dir.mkdir(parents=True)
        (objects_dir / 'hybrid-obj.mp3').touch()

        orig_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = detect_media_type('https://www.youtube.com/watch?v=xyz', 'hybrid-obj')
        finally:
            os.chdir(orig_dir)

        assert result == 'Video'


class TestGenerateObjectsMediaTypeInFrontmatter:
    """Integration tests: generated .md files contain media_type frontmatter."""

    def _run_generate_objects(self, tmp_path, objects_data):
        """Helper: write objects.json, run generate_objects(), return dict of {filename: content}."""
        import shutil

        data_dir = tmp_path / '_data'
        data_dir.mkdir()
        (data_dir / 'objects.json').write_text(json.dumps(objects_data))

        orig_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            from generate_collections import generate_objects
            generate_objects()
        finally:
            os.chdir(orig_dir)

        results = {}
        objects_dir = tmp_path / '_jekyll-files' / '_objects'
        if objects_dir.exists():
            for md_file in objects_dir.glob('*.md'):
                results[md_file.name] = md_file.read_text()
        return results

    def test_image_object_has_media_type_image(self, tmp_path):
        """IIIF/image object gets media_type: \"Image\" in frontmatter."""
        objects_data = [
            {'object_id': 'img-obj', 'title': 'An Image', 'source_url': 'https://example.com/manifest.json'}
        ]
        files = self._run_generate_objects(tmp_path, objects_data)
        content = files.get('img-obj.md', '')
        assert 'media_type: "Image"' in content

    def test_youtube_object_has_media_type_video(self, tmp_path):
        """YouTube object gets media_type: \"Video\" in frontmatter."""
        objects_data = [
            {'object_id': 'vid-obj', 'title': 'A Video', 'source_url': 'https://www.youtube.com/watch?v=abc'}
        ]
        files = self._run_generate_objects(tmp_path, objects_data)
        content = files.get('vid-obj.md', '')
        assert 'media_type: "Video"' in content

    def test_audio_object_has_media_type_audio(self, tmp_path):
        """Object with .mp3 file gets media_type: \"Audio\" in frontmatter."""
        # Create the audio file
        objects_dir = tmp_path / 'telar-content' / 'objects'
        objects_dir.mkdir(parents=True)
        (objects_dir / 'aud-obj.mp3').touch()

        objects_data = [
            {'object_id': 'aud-obj', 'title': 'An Audio'}
        ]
        files = self._run_generate_objects(tmp_path, objects_data)
        content = files.get('aud-obj.md', '')
        assert 'media_type: "Audio"' in content

    def test_audio_object_has_source_url(self, tmp_path):
        """Video object gets source_url in frontmatter for sidebar rendering."""
        objects_data = [
            {'object_id': 'vid-obj2', 'title': 'A Video',
             'source_url': 'https://vimeo.com/123456'}
        ]
        files = self._run_generate_objects(tmp_path, objects_data)
        content = files.get('vid-obj2.md', '')
        assert 'source_url:' in content
        assert 'vimeo.com' in content


class TestKnownObjectFieldsUpdated:
    """KNOWN_OBJECT_FIELDS must include the new v1.0.0-beta fields."""

    def test_media_type_in_known_fields(self):
        from generate_collections import KNOWN_OBJECT_FIELDS
        assert 'media_type' in KNOWN_OBJECT_FIELDS

    def test_audio_duration_in_known_fields(self):
        from generate_collections import KNOWN_OBJECT_FIELDS
        assert 'audio_duration' in KNOWN_OBJECT_FIELDS

    def test_audio_filesize_in_known_fields(self):
        from generate_collections import KNOWN_OBJECT_FIELDS
        assert 'audio_filesize' in KNOWN_OBJECT_FIELDS

    def test_audio_format_in_known_fields(self):
        from generate_collections import KNOWN_OBJECT_FIELDS
        assert 'audio_format' in KNOWN_OBJECT_FIELDS
