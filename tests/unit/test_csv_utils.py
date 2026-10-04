"""
Unit Tests for csv_to_json.py Utility Functions

This module tests the core utility functions used in Telar's CSV processing
pipeline. These functions handle DataFrame sanitization, URL extraction,
HTML stripping, and metadata cleaning — foundational operations that the
rest of the build system relies on.

The tests here ensure backward compatibility (e.g., legacy iiif_manifest
column support) and correct handling of edge cases (empty values, malformed
HTML, Unicode content).

Version: v1.8.0
"""

import sys
import os
import pytest
import pandas as pd

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from csv_to_json import (
    sanitize_dataframe,
    get_source_url,
    strip_html_tags,
    clean_metadata_value,
)

from telar.csv_utils import (normalize_column_names, COLUMN_NAME_MAPPING,
                             OBJECT_FIELDS)


class TestSanitizeDataframe:
    """Tests for sanitize_dataframe function."""

    def test_removes_christmas_tree_emoji(self):
        """Christmas tree emoji should be removed from all string fields."""
        df = pd.DataFrame({
            'title': ['Hello 🎄 World'],
            'description': ['Test 🎄 content 🎄']
        })
        result = sanitize_dataframe(df)
        assert result['title'].iloc[0] == 'Hello  World'
        assert result['description'].iloc[0] == 'Test  content '

    def test_preserves_other_content(self):
        """Non-emoji content should be preserved."""
        df = pd.DataFrame({
            'title': ['Normal Title'],
            'number': [42]
        })
        result = sanitize_dataframe(df)
        assert result['title'].iloc[0] == 'Normal Title'
        assert result['number'].iloc[0] == 42

    def test_handles_nan_values(self):
        """NaN values should not cause errors."""
        df = pd.DataFrame({
            'title': ['Hello', None, 'World']
        })
        result = sanitize_dataframe(df)
        assert result['title'].iloc[0] == 'Hello'
        assert pd.isna(result['title'].iloc[1])
        assert result['title'].iloc[2] == 'World'


class TestGetSourceUrl:
    """Tests for get_source_url function."""

    def test_returns_source_url_when_present(self):
        """source_url should be returned when available."""
        row = {'source_url': 'https://example.com/manifest.json'}
        assert get_source_url(row) == 'https://example.com/manifest.json'

    def test_falls_back_to_iiif_manifest(self):
        """Should fall back to iiif_manifest when source_url is empty."""
        row = {'source_url': '', 'iiif_manifest': 'https://legacy.com/manifest'}
        assert get_source_url(row) == 'https://legacy.com/manifest'

    def test_source_url_takes_priority(self):
        """source_url should take priority over iiif_manifest."""
        row = {
            'source_url': 'https://new.com/manifest',
            'iiif_manifest': 'https://old.com/manifest'
        }
        assert get_source_url(row) == 'https://new.com/manifest'

    def test_returns_empty_when_neither_present(self):
        """Should return empty string when neither field exists."""
        row = {}
        assert get_source_url(row) == ''

    def test_strips_whitespace(self):
        """Whitespace should be stripped from URLs."""
        row = {'source_url': '  https://example.com/manifest  '}
        assert get_source_url(row) == 'https://example.com/manifest'


class TestStripHtmlTags:
    """Tests for strip_html_tags function."""

    def test_removes_html_tags(self):
        """HTML tags should be removed."""
        text = '<p>Hello <strong>World</strong></p>'
        assert strip_html_tags(text) == 'Hello World'

    def test_decodes_html_entities(self):
        """HTML entities should be decoded."""
        text = 'Hello &amp; World &lt;test&gt;'
        assert strip_html_tags(text) == 'Hello & World <test>'

    def test_normalizes_whitespace(self):
        """Extra whitespace should be collapsed."""
        text = 'Hello    World\n\nTest'
        assert strip_html_tags(text) == 'Hello World Test'

    def test_handles_empty_input(self):
        """Empty input should return empty string."""
        assert strip_html_tags('') == ''
        assert strip_html_tags(None) == ''

    def test_handles_nested_tags(self):
        """Nested HTML tags should be removed."""
        text = '<div><p>Nested <span>content</span></p></div>'
        assert strip_html_tags(text) == 'Nested content'


class TestCleanMetadataValue:
    """Tests for clean_metadata_value function."""

    def test_cleans_simple_string(self):
        """Simple string should be cleaned."""
        assert clean_metadata_value('  Hello World  ') == 'Hello World'

    def test_handles_list_values(self):
        """List values should be joined with semicolons."""
        value = ['First', 'Second', 'Third']
        assert clean_metadata_value(value) == 'First; Second; Third'

    def test_strips_html_from_values(self):
        """HTML should be stripped from values."""
        value = '<p>Hello</p>'
        assert clean_metadata_value(value) == 'Hello'

    def test_handles_empty_input(self):
        """Empty input should return empty string."""
        assert clean_metadata_value('') == ''
        assert clean_metadata_value(None) == ''
        assert clean_metadata_value([]) == ''

    def test_filters_empty_list_items(self):
        """Empty items in lists should be filtered out."""
        value = ['First', '', '  ', 'Second']
        assert clean_metadata_value(value) == 'First; Second'


class TestNormalizeColumnNamesMediumRename:
    """Tests for object_type -> medium rename with backward compatibility (v0.10.0)."""

    def test_object_type_column_maps_to_medium(self):
        """English backward compat: object_type column must map to medium."""
        df = pd.DataFrame({'object_type': ['Painting', 'Map']})
        result = normalize_column_names(df)
        assert 'medium' in result.columns, "object_type column should be renamed to medium"
        assert 'object_type' not in result.columns, "object_type column should not survive rename"

    def test_tipo_objeto_maps_to_medium(self):
        """Spanish backward compat: tipo_objeto column must map to medium (not object_type)."""
        df = pd.DataFrame({'tipo_objeto': ['Pintura', 'Mapa']})
        result = normalize_column_names(df)
        assert 'medium' in result.columns, "tipo_objeto column should be renamed to medium"
        assert 'object_type' not in result.columns, "tipo_objeto must not create an object_type column"

    def test_medium_column_unchanged(self):
        """A CSV that already uses 'medium' should pass through without change."""
        df = pd.DataFrame({'medium': ['Painting', 'Map']})
        result = normalize_column_names(df)
        assert 'medium' in result.columns
        assert list(result['medium']) == ['Painting', 'Map']

    def test_object_type_and_medium_both_present_medium_wins(self):
        """When both object_type and medium columns are present, medium takes priority.

        normalize_column_names renames object_type -> medium; pandas raises on
        duplicate column names when both exist so the caller must deduplicate.
        This test verifies that the COLUMN_NAME_MAPPING entry maps object_type
        to medium (not to object_type), so calling code can resolve the conflict
        by dropping the renamed duplicate.
        """
        assert COLUMN_NAME_MAPPING.get('object_type') == 'medium', (
            "COLUMN_NAME_MAPPING must map 'object_type' to 'medium' for backward compat"
        )

    def test_medio_maps_to_medium(self):
        """Spanish 'medio' column (already present) still maps to medium."""
        df = pd.DataFrame({'medio': ['Óleo sobre lienzo']})
        result = normalize_column_names(df)
        assert 'medium' in result.columns
        assert list(result['medium']) == ['Óleo sobre lienzo']


class TestSearchFacetsMediumKey:
    """Tests for search.py medium facet (replaces object_type facet)."""

    def test_build_facets_uses_medium_key(self):
        """build_facets() must return 'medium' key, not 'object_type'."""
        from telar.search import build_facets
        objects = [
            {'medium': 'Painting', 'creator': 'Unknown'},
            {'medium': 'Map', 'creator': 'Unknown'},
            {'medium': 'Painting', 'creator': 'Smith'},
        ]
        facets = build_facets(objects)
        assert 'medium' in facets, "facets dict must have 'medium' key"
        assert 'object_type' not in facets, "facets dict must NOT have 'object_type' key"

    def test_build_facets_counts_medium_values(self):
        """build_facets() counts are correct for medium field."""
        from telar.search import build_facets
        objects = [
            {'medium': 'Painting'},
            {'medium': 'Map'},
            {'medium': 'Painting'},
        ]
        facets = build_facets(objects)
        assert facets['medium']['Painting'] == 2
        assert facets['medium']['Map'] == 1

    def test_generate_search_data_medium_field_in_objects(self, tmp_path):
        """generate_search_data() must emit 'medium' field, not 'object_type', in search objects."""
        from telar.search import generate_search_data
        import json

        objects_json = tmp_path / 'objects.json'
        output_json = tmp_path / 'search-data.json'
        config_yml = tmp_path / '_config.yml'

        objects_json.write_text(json.dumps([
            {'object_id': 'obj1', 'title': 'Test', 'medium': 'Painting',
             'creator': '', 'period': '', 'description': '', 'subjects': '',
             'year': '', 'thumbnail': '', 'source_url': '', 'demo': False}
        ]))
        config_yml.write_text('collection_interface:\n  browse_and_search: true\n')

        import os
        orig_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            generate_search_data(str(objects_json), str(output_json))
        finally:
            os.chdir(orig_dir)

        result = json.loads(output_json.read_text())
        first_obj = result['objects'][0]
        assert 'medium' in first_obj, "search object must have 'medium' field"
        assert 'object_type' not in first_obj, "search object must NOT have 'object_type' field"
        assert first_obj['medium'] == 'Painting'


class TestImageExtensionsAndStemIndex:
    """Tests for the shared IMAGE_EXTENSIONS constant and the stem->path index."""

    def test_image_extensions_includes_bmp_svg_pdf(self):
        from telar.csv_utils import IMAGE_EXTENSIONS
        # The historical existence-check set omitted these; the shared set must
        # include them so .bmp/.svg/.pdf objects are not falsely flagged missing.
        for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif',
                    '.tiff', '.bmp', '.svg', '.pdf'):
            assert ext in IMAGE_EXTENSIONS

    def test_every_recognised_extension_has_a_renderer_that_can_open_it(self):
        """Membership is a claim about the decoders present, so ask them.

        Asserting the list against itself proves nothing, and the list has been
        wrong in both directions: .heic was tiled while the processors did not
        recognise it, and .svg was recognised for releases while nothing could
        read it. The falsifiable question is whether a renderer exists for each.
        """
        from PIL import Image
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError:
            pass
        Image.init()  # plugin registration is lazy; without this every format looks unsupported

        import pymupdf
        from telar.csv_utils import IMAGE_EXTENSIONS_ORDERED

        PYMUPDF_EXTENSIONS = {'.pdf', '.svg'}

        for ext in IMAGE_EXTENSIONS_ORDERED:
            if ext in PYMUPDF_EXTENSIONS:
                assert pymupdf is not None  # rendered, not decoded; exercised below
                continue
            assert ext in Image.EXTENSION, f"{ext} is searched for but no decoder can open it"

    @pytest.mark.parametrize('view_w,view_h,expect_w,expect_h', [
        (200, 100, 4000, 2000),   # landscape: width is the long side
        (100, 200, 2000, 4000),   # portrait: height is, which is the case that
                                  # tells scaling-by-long-side apart from
                                  # scaling-by-width. A landscape fixture alone
                                  # cannot see the difference.
        (150, 150, 4000, 4000),   # square
    ])
    def test_an_svg_rasterises_at_its_authored_proportions(
        self, tmp_path, view_w, view_h, expect_w, expect_h
    ):
        """The SVG path end to end, because a membership list cannot show it works.

        An SVG carrying only a viewBox is the case that matters: a browser gives
        it no intrinsic size and falls back to 300x150, while MuPDF reads the
        viewBox and keeps the authored proportions.
        """
        from iiif_utils import _rasterise_svg, SVG_TARGET_LONG_SIDE_PX

        svg = tmp_path / 'map.svg'
        svg.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {view_w} {view_h}">'
            f'<rect width="{view_w}" height="{view_h}" fill="#204060"/></svg>'
        )

        img = _rasterise_svg(svg)
        assert img is not None, "a well-formed SVG must rasterise"
        assert img.mode == 'RGB'
        assert max(img.size) == SVG_TARGET_LONG_SIDE_PX
        assert img.size == (expect_w, expect_h), \
            "the viewBox proportions must survive, not a browser's 300x150 default"

    def test_a_malformed_svg_is_reported_rather_than_raising(self, tmp_path):
        """A bad file must skip its object, not stop the run part way through."""
        from iiif_utils import _rasterise_svg

        broken = tmp_path / 'broken.svg'
        broken.write_text('this is not an svg at all')
        assert _rasterise_svg(broken) is None

    def test_build_stem_index_groups_files_by_stem(self, tmp_path):
        from telar.csv_utils import build_stem_index
        (tmp_path / 'photo.png').write_text('x')
        (tmp_path / 'photo.svg').write_text('x')
        (tmp_path / 'map.jpg').write_text('x')
        (tmp_path / 'sub').mkdir()  # directories are ignored
        idx = build_stem_index(tmp_path)
        assert set(idx.keys()) == {'photo', 'map'}
        assert {p.suffix.lower() for p in idx['photo']} == {'.png', '.svg'}
        assert len(idx['map']) == 1

    def test_build_stem_index_missing_dir_returns_empty(self, tmp_path):
        from telar.csv_utils import build_stem_index
        assert build_stem_index(tmp_path / 'does-not-exist') == {}


class TestTheAliasMapIsScopedToTheSheetItRunsOn:
    """One table serves every spreadsheet the build reads.

    So a rule written for the project sheet renamed a column on the
    objects sheet: an author's own `privado` column — a note that a piece
    is in a private collection — became `protected`, the name the project
    sheet uses to mean "encrypt this story". Nothing reads `protected` on
    an object, so it reached `extra_metadata`, where the object layout
    prints the key as the label. A Spanish site showed an English heading
    the author never wrote.

    The scope is the canonical names that sheet's own consumer reads, so
    it cannot drift from the thing it describes.
    """

    def _columns(self, headers, **kwargs):
        return list(normalize_column_names(
            pd.DataFrame({h: ['x'] for h in headers}), **kwargs).columns)

    def test_an_objects_sheet_keeps_the_authors_own_column(self):
        columns = self._columns(['id_objeto', 'privado'],
                                canonical_fields=OBJECT_FIELDS)

        assert columns == ['object_id', 'privado']

    def test_a_story_sheet_still_reads_it_as_the_protection_flag(self):
        """The rename is right where the canonical name means something."""
        assert self._columns(['paso', 'privado']) == ['step', 'protected']

    @pytest.mark.parametrize('alias,canonical', [
        ('titulo', 'title'), ('fuente', 'source'), ('medio', 'medium'),
        ('creador', 'creator'), ('a\u00f1o', 'year'),
        ('descripcion', 'description'), ('cr\u00e9dito', 'credit'),
    ])
    def test_the_aliases_an_objects_sheet_needs_still_apply(self, alias, canonical):
        """The danger in scoping is silently refusing a header that works.

        Every one of these has been accepted since v0.6.0, and a site
        using it would lose the column with no message.
        """
        assert self._columns([alias], canonical_fields=OBJECT_FIELDS) == [canonical]

    def test_nothing_the_objects_path_reads_is_left_out_of_the_scope(self):
        """The set is the scope, so a field missing from it is dropped.

        Read off the frontmatter writer rather than listed here: a second
        list would be the drift this change exists to remove.
        """
        from generate_collections import KNOWN_OBJECT_FIELDS

        assert KNOWN_OBJECT_FIELDS is OBJECT_FIELDS

    def test_an_unscoped_call_is_unchanged(self):
        """Every sheet but objects still gets the whole map."""
        assert self._columns(['id_termino', 'definicion']) == ['term_id',
                                                               'definition']
