"""
Unit Tests for generate_collections.py

Tests focus on the media_type detection logic, source_url injection
for video objects, and (v1.3.0) sister-file localization in
generate_pages().

Version: v1.5.0
"""

import sys
import os
import json
import pytest
import shutil
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


class TestGeneratePagesLocalization:
    """v1.3.0: generate_pages() picks the sister file matching telar_language.

    Convention: a sister file has frontmatter `localized_for: <canonical>.md`
    and `language: <code>`. When the active language matches the sister's
    language, the sister's content is used; output is always written under
    the canonical filename so the URL is stable across languages.
    """

    @pytest.fixture
    def isolated_pages_env(self, tmp_path, monkeypatch):
        """Build an isolated pages source/output environment under tmp_path.

        Returns (source_dir, output_dir). Changes cwd to tmp_path so the
        relative paths used inside generate_pages() resolve into the fixture.
        """
        source_dir = tmp_path / 'telar-content' / 'texts' / 'pages'
        source_dir.mkdir(parents=True)
        output_dir = tmp_path / '_jekyll-files' / '_pages'
        # Provide an empty glossary CSV so load_glossary_terms() returns []
        (tmp_path / 'telar-content' / 'spreadsheets').mkdir(parents=True)
        (tmp_path / 'telar-content' / 'texts' / 'glossary').mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        return source_dir, output_dir

    def _write_page(self, path, frontmatter, body):
        path.write_text(f"---\n{frontmatter.strip()}\n---\n\n{body.strip()}\n", encoding='utf-8')

    def test_canonical_only_uses_canonical(self, isolated_pages_env):
        """No sister file: canonical is used regardless of telar_language."""
        from generate_collections import generate_pages
        source_dir, output_dir = isolated_pages_env

        self._write_page(source_dir / 'about.md', 'title: About', '# About Telar\nEnglish content.')

        generate_pages(telar_language='es')  # no es sister exists

        out = (output_dir / 'about.md').read_text(encoding='utf-8')
        assert '<h1>About Telar</h1>' in out
        assert 'English content' in out

    def test_es_active_picks_sister(self, isolated_pages_env):
        """telar_language='es' + acerca.md sister: sister content wins, output is about.md."""
        from generate_collections import generate_pages
        source_dir, output_dir = isolated_pages_env

        self._write_page(source_dir / 'about.md', 'title: About', '# About Telar\nEnglish content.')
        self._write_page(
            source_dir / 'acerca.md',
            'title: Acerca de Telar\nlocalized_for: about.md\nlanguage: es',
            '# Acerca de Telar\nContenido en español.'
        )

        generate_pages(telar_language='es')

        # Output is under canonical filename
        out_path = output_dir / 'about.md'
        assert out_path.exists()
        # No separate acerca.md output (sister doesn't get its own URL)
        assert not (output_dir / 'acerca.md').exists()
        # Body is the Spanish one
        out = out_path.read_text(encoding='utf-8')
        assert '<h1>Acerca de Telar</h1>' in out
        assert 'Contenido en español' in out
        # Frontmatter is the sister's frontmatter (so the title localizes too)
        assert 'title: Acerca de Telar' in out
        assert 'language: es' in out

    def test_en_active_with_es_sister_uses_canonical(self, isolated_pages_env):
        """telar_language='en' + an es sister exists: canonical is still used; sister is skipped."""
        from generate_collections import generate_pages
        source_dir, output_dir = isolated_pages_env

        self._write_page(source_dir / 'about.md', 'title: About', '# About Telar\nEnglish content.')
        self._write_page(
            source_dir / 'acerca.md',
            'title: Acerca de Telar\nlocalized_for: about.md\nlanguage: es',
            '# Acerca de Telar\nContenido en español.'
        )

        generate_pages(telar_language='en')

        out_path = output_dir / 'about.md'
        assert out_path.exists()
        assert not (output_dir / 'acerca.md').exists()
        out = out_path.read_text(encoding='utf-8')
        assert '<h1>About Telar</h1>' in out
        assert 'English content' in out

    def test_sister_for_other_language_is_ignored(self, isolated_pages_env):
        """telar_language='es' + only fr sister: canonical is used (no es sister to pick)."""
        from generate_collections import generate_pages
        source_dir, output_dir = isolated_pages_env

        self._write_page(source_dir / 'about.md', 'title: About', '# About Telar\nEnglish content.')
        self._write_page(
            source_dir / 'a-propos.md',
            'title: À propos\nlocalized_for: about.md\nlanguage: fr',
            '# À propos\nContenu français.'
        )

        generate_pages(telar_language='es')

        out = (output_dir / 'about.md').read_text(encoding='utf-8')
        assert '<h1>About Telar</h1>' in out  # falls back to canonical EN
        assert 'À propos' not in out
        assert not (output_dir / 'a-propos.md').exists()

    def test_sister_without_language_is_skipped_with_warning(self, isolated_pages_env, capsys):
        """A file with localized_for but no language: skip with warning."""
        from generate_collections import generate_pages
        source_dir, output_dir = isolated_pages_env

        self._write_page(source_dir / 'about.md', 'title: About', '# About Telar\nEN.')
        self._write_page(
            source_dir / 'broken.md',
            'title: Broken\nlocalized_for: about.md',  # no language
            '# Broken\nNo language code.'
        )

        generate_pages(telar_language='es')

        captured = capsys.readouterr()
        assert 'broken.md' in captured.out
        assert 'language' in captured.out.lower()
        # Canonical still produced (sister-without-language ignored, no es sister
        # available)
        assert (output_dir / 'about.md').exists()
        assert not (output_dir / 'broken.md').exists()

    def test_default_language_is_en(self, isolated_pages_env):
        """generate_pages() with no telar_language argument defaults to 'en'."""
        from generate_collections import generate_pages
        source_dir, output_dir = isolated_pages_env

        self._write_page(source_dir / 'about.md', 'title: About', '# About Telar\nEN.')
        self._write_page(
            source_dir / 'acerca.md',
            'title: Acerca\nlocalized_for: about.md\nlanguage: es',
            '# Acerca\nES.'
        )

        generate_pages()  # no argument

        out = (output_dir / 'about.md').read_text(encoding='utf-8')
        assert '<h1>About Telar</h1>' in out  # EN content because default is 'en'


class TestStoryFrontmatterSerialization:
    """generate_stories() writes injection-safe YAML frontmatter."""

    def test_subtitle_with_yaml_injection_is_neutralised(self, tmp_path):
        import os, json, yaml
        from generate_collections import generate_stories

        (tmp_path / '_data').mkdir()
        # A subtitle crafted to break out of a naive `subtitle: "..."` line.
        evil = 'real" \ninjected_key: true\nbyline: "pwned'
        project = [{
            'stories': [{
                'number': 1,
                'title': 'My Story',
                'subtitle': evil,
                'story_id': 'my-story',
            }]
        }]
        (tmp_path / '_data' / 'project.json').write_text(json.dumps(project), encoding='utf-8')
        (tmp_path / '_data' / 'my-story.json').write_text('[]', encoding='utf-8')

        orig = os.getcwd()
        os.chdir(tmp_path)
        try:
            generate_stories()
            out = (tmp_path / '_jekyll-files' / '_stories' / 'my-story.md').read_text(encoding='utf-8')
        finally:
            os.chdir(orig)

        fm = out.split('---')[1]
        parsed = yaml.safe_load(fm)
        # The whole evil string is a single scalar; no smuggled keys appeared.
        assert parsed['subtitle'] == evil
        assert 'injected_key' not in parsed
        assert parsed.get('byline') != 'pwned'
        assert parsed['title'] == 'My Story'
        assert parsed['layout'] == 'story'
