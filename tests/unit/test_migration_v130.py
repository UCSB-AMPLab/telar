"""
Unit Tests for migrations/v121_to_v130.py

Tests the conditional content cleanup behaviour: stale frontmatter keys
removed only when matching v1.2.1 defaults, body replacement only when
unmodified, acerca.md creation only when missing.

Network-dependent steps (framework file fetch from GitHub, version bump)
are not exercised here — those are covered by the upgrade.py
integration tests.

Version: v1.3.0-beta
"""

import sys
import os
import pytest

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from migrations.v121_to_v130 import (
    Migration121to130,
    INDEX_MD_V121_FRONTMATTER_DEFAULTS,
    INDEX_MD_V121_BODY,
    INDEX_MD_NEW_BODY,
    GLOSSARY_MD_V121_BODY,
    GLOSSARY_MD_NEW_BODY,
    OBJECTS_MD_V121_BODY,
    OBJECTS_MD_NEW_BODY,
    ABOUT_MD_V121_BODY,
    ABOUT_MD_NEW_BODY,
    ACERCA_MD_FULL,
    _hash_normalized,
)


# ---------- Frontmatter cleanup ----------

class TestCleanupIndexFrontmatter:
    """_cleanup_index_frontmatter removes only stale-matching defaults."""

    def _make(self, tmp_path, frontmatter_text, body='# Welcome\nDemo body.'):
        index_path = tmp_path / 'index.md'
        index_path.write_text(f"---\n{frontmatter_text}\n---\n\n{body}\n", encoding='utf-8')
        return Migration121to130(str(tmp_path))

    def test_removes_all_three_when_all_defaults(self, tmp_path):
        m = self._make(
            tmp_path,
            'layout: index\ntitle: Home\nstories_heading: "Explore the stories"\n'
            'objects_heading: "See the objects behind the stories"\n'
            'objects_intro: "Browse {count} objects featured in the stories."'
        )
        out = m._cleanup_index_frontmatter()
        assert any('Removed stale frontmatter keys' in c for c in out)
        new_content = (tmp_path / 'index.md').read_text()
        assert 'stories_heading' not in new_content
        assert 'objects_heading' not in new_content
        assert 'objects_intro' not in new_content
        # Other frontmatter preserved
        assert 'layout: index' in new_content
        assert 'title: Home' in new_content

    def test_preserves_customized_values(self, tmp_path):
        m = self._make(
            tmp_path,
            'layout: index\ntitle: Home\nstories_heading: "My custom stories heading"\n'
            'objects_heading: "See the objects behind the stories"'  # default
        )
        out = m._cleanup_index_frontmatter()
        new_content = (tmp_path / 'index.md').read_text()
        # Customized one stayed
        assert 'My custom stories heading' in new_content
        # Default-matching one removed
        assert 'objects_heading' not in new_content

    def test_no_change_when_no_stale_keys_present(self, tmp_path):
        m = self._make(tmp_path, 'layout: index\ntitle: Home')
        out = m._cleanup_index_frontmatter()
        assert out == []

    def test_no_change_when_all_customized(self, tmp_path):
        m = self._make(
            tmp_path,
            'layout: index\ntitle: Home\n'
            'stories_heading: "My stories"\n'
            'objects_heading: "My objects"\n'
            'objects_intro: "My intro"'
        )
        out = m._cleanup_index_frontmatter()
        assert out == []
        new_content = (tmp_path / 'index.md').read_text()
        assert 'My stories' in new_content
        assert 'My objects' in new_content
        assert 'My intro' in new_content

    def test_preserves_body(self, tmp_path):
        m = self._make(
            tmp_path,
            'layout: index\ntitle: Home\nstories_heading: "Explore the stories"',
            body='# Custom welcome\n\nMy custom body content.'
        )
        m._cleanup_index_frontmatter()
        new_content = (tmp_path / 'index.md').read_text()
        assert '# Custom welcome' in new_content
        assert 'My custom body content.' in new_content

    def test_handles_missing_file_gracefully(self, tmp_path):
        m = Migration121to130(str(tmp_path))
        out = m._cleanup_index_frontmatter()
        assert out == []

    def test_warns_on_missing_frontmatter(self, tmp_path):
        (tmp_path / 'index.md').write_text('No frontmatter here\nJust body.\n', encoding='utf-8')
        m = Migration121to130(str(tmp_path))
        out = m._cleanup_index_frontmatter()
        assert any('no frontmatter' in c.lower() for c in out)


# ---------- Body replacement ----------

class TestReplaceBodyIfDefault:
    """_replace_body_if_default only replaces unmodified bodies."""

    def _make(self, tmp_path, rel_path, frontmatter, body):
        full = tmp_path / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding='utf-8')
        return Migration121to130(str(tmp_path))

    def test_replaces_when_body_matches_v121(self, tmp_path):
        m = self._make(tmp_path, 'pages/glossary.md', 'title: Glossary\npermalink: /glossary/',
                       GLOSSARY_MD_V121_BODY)
        out = m._replace_body_if_default(
            'pages/glossary.md', GLOSSARY_MD_V121_BODY, GLOSSARY_MD_NEW_BODY, 'glossary intro'
        )
        assert any('Updated glossary intro' in c for c in out)
        new_content = (tmp_path / 'pages/glossary.md').read_text()
        assert 'lang.pages.glossary_intro' in new_content
        assert 'Key terms and concepts used in these stories.' not in new_content

    def test_preserves_when_body_customized(self, tmp_path):
        m = self._make(tmp_path, 'pages/glossary.md', 'title: Glossary\npermalink: /glossary/',
                       'My custom glossary intro that I rewrote.')
        out = m._replace_body_if_default(
            'pages/glossary.md', GLOSSARY_MD_V121_BODY, GLOSSARY_MD_NEW_BODY, 'glossary intro'
        )
        assert any('Skipped' in c for c in out)
        new_content = (tmp_path / 'pages/glossary.md').read_text()
        assert 'My custom glossary intro' in new_content
        assert 'lang.pages.glossary_intro' not in new_content

    def test_preserves_frontmatter_during_replacement(self, tmp_path):
        m = self._make(
            tmp_path, 'pages/glossary.md',
            'layout: glossary-index\ntitle: My Glossary Page\npermalink: /my-glossary/\n'
            'extra_key: extra_value',
            GLOSSARY_MD_V121_BODY
        )
        m._replace_body_if_default(
            'pages/glossary.md', GLOSSARY_MD_V121_BODY, GLOSSARY_MD_NEW_BODY, 'glossary intro'
        )
        new_content = (tmp_path / 'pages/glossary.md').read_text()
        assert 'title: My Glossary Page' in new_content
        assert 'permalink: /my-glossary/' in new_content
        assert 'extra_key: extra_value' in new_content
        assert 'lang.pages.glossary_intro' in new_content

    def test_handles_missing_file(self, tmp_path):
        m = Migration121to130(str(tmp_path))
        out = m._replace_body_if_default(
            'pages/glossary.md', GLOSSARY_MD_V121_BODY, GLOSSARY_MD_NEW_BODY, 'glossary intro'
        )
        assert any('file missing' in c.lower() for c in out)

    def test_normalises_whitespace(self, tmp_path):
        """Trailing whitespace / extra newlines shouldn't block replacement."""
        m = self._make(tmp_path, 'pages/glossary.md', 'title: Glossary',
                       GLOSSARY_MD_V121_BODY + '\n\n\n  ')  # extra trailing whitespace
        out = m._replace_body_if_default(
            'pages/glossary.md', GLOSSARY_MD_V121_BODY, GLOSSARY_MD_NEW_BODY, 'glossary intro'
        )
        assert any('Updated' in c for c in out)

    def test_about_md_replacement(self, tmp_path):
        """Substantive about.md body still detected as v1.2.1 default."""
        m = self._make(
            tmp_path, 'telar-content/texts/pages/about.md',
            'title: About', ABOUT_MD_V121_BODY
        )
        out = m._replace_body_if_default(
            'telar-content/texts/pages/about.md',
            ABOUT_MD_V121_BODY, ABOUT_MD_NEW_BODY, 'about page'
        )
        assert any('Updated about page' in c for c in out)
        new_content = (tmp_path / 'telar-content/texts/pages/about.md').read_text()
        # New content has the multimedia framing
        assert 'video, audio' in new_content
        assert 'Telar Compositor' in new_content
        # Old content gone
        assert 'International Image Interoperability Framework' not in new_content


# ---------- acerca.md conditional create ----------

class TestCreateAcercaForEsWithDefaultAbout:
    """_create_acerca_for_es_with_default_about creates the Spanish sister
    of about.md only when ALL of these are true:
      - site has telar_language: es
      - about.md exists and matches the v1.2.1 default (hash-checked)
      - acerca.md does not already exist

    Any guard fails -> no creation. This prevents shadowing customised
    about.md content with our default Spanish at build time.
    """

    def _write_config(self, tmp_path, telar_language='en'):
        (tmp_path / '_config.yml').write_text(
            f"telar:\n  telar_language: {telar_language}\n", encoding='utf-8'
        )

    def _write_about(self, tmp_path, body):
        about_path = tmp_path / 'telar-content/texts/pages/about.md'
        about_path.parent.mkdir(parents=True, exist_ok=True)
        about_path.write_text(f"---\ntitle: About\n---\n\n{body}\n", encoding='utf-8')

    def test_creates_when_all_conditions_met(self, tmp_path):
        """es + default about.md + no acerca.md => create acerca.md"""
        self._write_config(tmp_path, 'es')
        self._write_about(tmp_path, ABOUT_MD_V121_BODY)

        m = Migration121to130(str(tmp_path))
        out = m._create_acerca_for_es_with_default_about()

        acerca_path = tmp_path / 'telar-content/texts/pages/acerca.md'
        assert acerca_path.exists(), 'acerca.md should have been created'
        content = acerca_path.read_text(encoding='utf-8')
        assert 'localized_for: about.md' in content
        assert 'language: es' in content
        assert '# Acerca de Telar' in content
        assert any('Created' in c for c in out)

    def test_skips_when_language_is_en(self, tmp_path):
        """en + default about.md + no acerca.md => skip (would sit unused)"""
        self._write_config(tmp_path, 'en')
        self._write_about(tmp_path, ABOUT_MD_V121_BODY)

        m = Migration121to130(str(tmp_path))
        out = m._create_acerca_for_es_with_default_about()

        assert not (tmp_path / 'telar-content/texts/pages/acerca.md').exists()
        assert out == []  # no message either; we just no-op silently

    def test_skips_when_about_md_customised(self, tmp_path):
        """es + customised about.md + no acerca.md => skip (would shadow customisation)"""
        self._write_config(tmp_path, 'es')
        self._write_about(tmp_path, '# My Custom About\n\nWith my own text.')

        m = Migration121to130(str(tmp_path))
        out = m._create_acerca_for_es_with_default_about()

        assert not (tmp_path / 'telar-content/texts/pages/acerca.md').exists()
        assert any('customised' in c.lower() for c in out)

    def test_skips_when_acerca_already_exists(self, tmp_path):
        """es + default about.md + existing acerca.md => skip (don't overwrite)"""
        self._write_config(tmp_path, 'es')
        self._write_about(tmp_path, ABOUT_MD_V121_BODY)
        # Pre-create user's own acerca.md
        acerca_path = tmp_path / 'telar-content/texts/pages/acerca.md'
        acerca_path.parent.mkdir(parents=True, exist_ok=True)
        acerca_path.write_text(
            '---\ntitle: Mi acerca propio\nlocalized_for: about.md\nlanguage: es\n---\n\nMi contenido propio.\n',
            encoding='utf-8'
        )

        m = Migration121to130(str(tmp_path))
        out = m._create_acerca_for_es_with_default_about()

        # Existing acerca.md preserved
        content = acerca_path.read_text(encoding='utf-8')
        assert 'Mi contenido propio.' in content
        assert any('already exists' in c.lower() for c in out)

    def test_skips_when_about_md_missing(self, tmp_path):
        """es + no about.md => skip (nothing to mirror)"""
        self._write_config(tmp_path, 'es')
        # no about.md written

        m = Migration121to130(str(tmp_path))
        out = m._create_acerca_for_es_with_default_about()

        assert not (tmp_path / 'telar-content/texts/pages/acerca.md').exists()
        assert any('no about.md' in c.lower() for c in out)


# ---------- Hash check (modification detection) ----------

class TestHashNormalized:
    """The SHA-256 hash check is the safety mechanism that prevents
    overwriting user-modified content. Equal-after-normalisation inputs
    must hash to the same value; any meaningful change must differ."""

    def test_identical_text_hashes_equal(self):
        assert _hash_normalized('hello world') == _hash_normalized('hello world')

    def test_whitespace_normalisation_hashes_equal(self):
        # Trailing whitespace and CRLF differences shouldn't bump the hash
        assert _hash_normalized('hello\nworld') == _hash_normalized('hello\nworld\n\n  ')
        assert _hash_normalized('hello\r\nworld') == _hash_normalized('hello\nworld')

    def test_meaningful_edit_changes_hash(self):
        assert _hash_normalized('hello world') != _hash_normalized('hello world!')
        assert _hash_normalized('hello world') != _hash_normalized('hello  world')  # extra mid-line space

    def test_returns_hex_string(self):
        h = _hash_normalized('anything')
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex digest length
        int(h, 16)  # parses as hex without raising


# ---------- Normalisation helper ----------

class TestNormalise:
    def test_strips_leading_trailing_whitespace(self):
        m = Migration121to130('/tmp')
        assert m._normalize('  hello  \n\n') == 'hello'

    def test_normalises_line_endings(self):
        m = Migration121to130('/tmp')
        assert m._normalize('a\r\nb\r\nc') == 'a\nb\nc'


# ---------- Migration metadata sanity checks ----------

class TestMigrationMetadata:
    def test_from_to_versions(self):
        m = Migration121to130('/tmp')
        assert m.from_version == '1.2.1'
        assert m.to_version == '1.3.0'

    def test_check_applicable_always_true(self):
        m = Migration121to130('/tmp')
        assert m.check_applicable() is True

    def test_manual_steps_bilingual(self):
        m = Migration121to130('/tmp')
        en = m._get_manual_steps_en()
        es = m._get_manual_steps_es()
        assert len(en) == 1
        assert len(es) == 1
        assert 'doc_url' in en[0]
        assert 'doc_url' in es[0]
        assert 'i18n' in en[0]['description'].lower()
        assert 'i18n' in es[0]['description'].lower()
        # Each describes the sister-file convention
        assert 'acerca.md' in en[0]['description']
        assert 'acerca.md' in es[0]['description']
        # And explains the conditional create + skip-when-customised semantics
        assert 'creates `acerca.md`' in en[0]['description']
        assert 'skips the create' in en[0]['description']
        assert 'crea `acerca.md`' in es[0]['description']
        assert 'no lo crea' in es[0]['description']

    def test_v121_frontmatter_defaults_constants(self):
        """The three keys we drop must be exactly these."""
        assert set(INDEX_MD_V121_FRONTMATTER_DEFAULTS.keys()) == {
            'stories_heading',
            'objects_heading',
            'objects_intro',
        }
        assert INDEX_MD_V121_FRONTMATTER_DEFAULTS['stories_heading'] == 'Explore the stories'
