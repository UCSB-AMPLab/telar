"""
Unit Tests for the Story Page Manifest

The manifest is the contract that lets encrypt_protected_stories.py find a
protected story's rendered page without predicting its URL. These tests pin
the slug rule it is built from, the two ambiguities it refuses, and the
one case it honestly cannot resolve.

Version: v1.7.0
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.story_pages import (
    DEFAULT_STORIES_PERMALINK,
    MANIFEST_SCHEMA,
    ManifestError,
    build_manifest,
    jekyll_slug,
    manifest_path,
    read_manifest,
    remove_manifest,
    stories_permalink,
    story_url,
    write_manifest,
)


class TestJekyllSlug:
    """The rule Jekyll applies to `:name` when it builds a story's URL."""

    @pytest.mark.parametrize("raw,expected", [
        ("blank_template", "blank-template"),
        ("plantilla_en_blanco", "plantilla-en-blanco"),
        ("already-fine", "already-fine"),
        ("Mixed_Case", "mixed-case"),
        ("spaces and punctuation!", "spaces-and-punctuation"),
        ("__leading_and_trailing__", "leading-and-trailing"),
        ("multiple___underscores", "multiple-underscores"),
        ("story-1", "story-1"),
        ("café-años", "café-años"),
        ("___", ""),
    ])
    def test_matches_jekyll_default_mode(self, raw, expected):
        assert jekyll_slug(raw) == expected


class TestStoriesPermalink:
    def test_default_when_unconfigured(self):
        assert stories_permalink({}) == DEFAULT_STORIES_PERMALINK
        assert stories_permalink(None) == DEFAULT_STORIES_PERMALINK

    def test_default_when_the_collection_omits_it(self):
        config = {'collections': {'stories': {'output': True}}}
        assert stories_permalink(config) == DEFAULT_STORIES_PERMALINK

    def test_reads_a_configured_value(self):
        config = {'collections': {'stories': {'permalink': '/relatos/:name/'}}}
        assert stories_permalink(config) == '/relatos/:name/'


class TestStoryUrl:
    def test_slugifies_under_the_default_permalink(self):
        assert story_url("blank_template") == "/stories/blank-template/"

    def test_no_url_under_a_custom_permalink(self):
        # Expanding an arbitrary template is Jekyll's job. Saying nothing is
        # correct; guessing is the failure this module exists to remove.
        assert story_url("a", "/relatos/:name/") is None

    def test_no_url_for_an_empty_slug(self):
        assert story_url("___") is None


class TestBuildManifest:
    def test_records_identifier_source_and_url(self):
        manifest = build_manifest([("my_story", "_stories/my_story.md")])
        assert manifest['schema'] == MANIFEST_SCHEMA
        assert manifest['stories_permalink'] == DEFAULT_STORIES_PERMALINK
        assert manifest['stories']['my_story'] == {
            'source': '_stories/my_story.md',
            'url': '/stories/my-story/',
        }

    def test_two_identifiers_one_url_is_refused(self):
        # Only one of them gets a page; which one is not something to resolve.
        with pytest.raises(ManifestError, match="all render at"):
            build_manifest([("my_story", "a"), ("my-story", "b")])

    def test_repeated_identifier_is_refused(self):
        # The second document overwrites the first before Jekyll sees either.
        with pytest.raises(ManifestError, match="share one identifier"):
            build_manifest([("story-1", "a"), ("story-1", "b")])

    def test_empty_slug_is_refused(self):
        with pytest.raises(ManifestError, match="empty path"):
            build_manifest([("___", "a")])

    def test_every_problem_is_reported_at_once(self):
        # A site with two faults should learn about both in one run.
        with pytest.raises(ManifestError) as excinfo:
            build_manifest([("___", "a"), ("my_story", "b"), ("my-story", "c")])
        message = str(excinfo.value)
        assert "empty path" in message and "all render at" in message

    def test_custom_permalink_yields_entries_without_urls(self):
        manifest = build_manifest([("a", "x"), ("___", "y")], "/relatos/:name/")
        assert manifest['stories_permalink'] == "/relatos/:name/"
        assert 'url' not in manifest['stories']['a']
        # Under a permalink this module cannot reproduce, an empty slug is
        # not knowably broken either — there is nothing to slugify into.
        assert 'url' not in manifest['stories']['___']

    def test_distinct_identifiers_pass(self):
        manifest = build_manifest(
            [("one", "a"), ("two_three", "b"), ("story-1", "c")]
        )
        assert len(manifest['stories']) == 3


class TestManifestIO:
    def test_round_trips(self, tmp_path):
        manifest = build_manifest([("café", "_stories/café.md")])
        path = write_manifest(tmp_path, manifest)
        assert path == manifest_path(tmp_path)
        assert read_manifest(tmp_path) == manifest
        # Written as UTF-8 text, not escaped, so it stays readable.
        assert "café" in path.read_text(encoding='utf-8')

    def test_absent_manifest_reads_as_none(self, tmp_path):
        assert read_manifest(tmp_path) is None

    def test_remove_is_idempotent(self, tmp_path):
        write_manifest(tmp_path, build_manifest([("a", "b")]))
        remove_manifest(tmp_path)
        remove_manifest(tmp_path)
        assert read_manifest(tmp_path) is None

    def test_nests_below_the_data_directory(self, tmp_path):
        # Nested so it can never be mistaken for `_data/<identifier>.json`,
        # which is keyed by story identifier.
        path = manifest_path(tmp_path)
        assert path.parent != tmp_path
        assert path.suffix == '.json'

