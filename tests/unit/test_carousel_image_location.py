"""
Unit Tests for Where a Carousel Image Is Found

A carousel item's `image:` value can name a file anywhere in the site:

- an http(s) URL is used as given;
- a path with a folder in it is read from the site root, with or without a
  leading `/`, and a leading `/` that already carries the baseurl does not
  get it twice; with no such file at the root, it is tried under
  assets/images/ and then telar-content/objects/;
- a bare file name is looked for in assets/images/ and then in
  telar-content/objects/, and the first folder holding it wins.

The published src, the not-found warning and the aspect-ratio sizing all
answer from the same file. These tests build a small site on disk rather
than mocking the lookup, so the file measured is a real one.

Version: v1.8.0
"""

import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar import widgets
from telar.images import get_image_dimensions, locate_image, validate_image_path
from telar.widgets import parse_carousel_widget


def _png(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', size).save(path)


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A site with images in both folders, one name present in each.

    `both.png` differs in shape between the folders, so the size class says
    which file was measured: wide (compact) in assets/images, tall (portrait)
    in telar-content/objects.
    """
    _png(tmp_path / 'assets/images/both.png', (1600, 400))
    _png(tmp_path / 'telar-content/objects/both.png', (400, 800))
    _png(tmp_path / 'assets/images/only-assets.png', (800, 600))
    _png(tmp_path / 'telar-content/objects/only-objects.png', (400, 800))
    _png(tmp_path / 'assets/images/historia/nested.png', (800, 600))
    _png(tmp_path / 'assets/images/thumbs/thumb.png', (800, 600))
    (tmp_path / '_config.yml').write_text('baseurl: "/telar"\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    widgets.reset_base_url_cache()
    yield tmp_path
    widgets.reset_base_url_cache()


def carousel(image, base_url='/telar', extra=''):
    warnings = []
    result = parse_carousel_widget(
        f'image: {image}\nalt: A slide\n{extra}', 'test.md', warnings, base_url=base_url)
    return result['items'][0]['src'], warnings, result['size_class']


class TestUrls:

    def test_a_url_is_used_as_given(self, site):
        src, warnings, _ = carousel('https://example.org/a.jpg', extra='width: 800\nheight: 600')
        assert src == 'https://example.org/a.jpg'
        assert warnings == []
        assert validate_image_path('https://example.org/a.jpg', 'test.md') == (
            True, 'https://example.org/a.jpg')

    def test_an_iiif_thumbnail_url_is_used_as_given(self, site):
        """The form objects.csv holds in `thumbnail`, which the Compositor
        writes into a carousel when it has no site URL to build one from."""
        url = ('https://iiif-cloud.princeton.edu/iiif/2/a3%2F5c%2F7c%2Fa35c7c70b04342b58dd6116d7390e017'
               '%2Fintermediate_file/full/!200,150/0/default.jpg')
        src, warnings, _ = carousel(url, extra='width: 200\nheight: 150')
        assert src == url
        assert warnings == []

    def test_a_site_iiif_url_is_used_as_given(self, site):
        """The form the Compositor writes when it has the site's URL."""
        url = 'https://user.github.io/site/iiif/objects/figueroa/page-1/full/max/0/default.jpg'
        src, warnings, _ = carousel(url, extra='width: 800\nheight: 600')
        assert src == url
        assert warnings == []


class TestPathsWithAFolder:

    def test_a_path_is_read_from_the_site_root(self, site):
        src, warnings, _ = carousel('telar-content/objects/only-objects.png')
        assert src == '/telar/telar-content/objects/only-objects.png'
        assert warnings == []

    def test_a_subfolder_of_assets_images(self, site):
        src, warnings, _ = carousel('assets/images/historia/nested.png')
        assert src == '/telar/assets/images/historia/nested.png'
        assert warnings == []

    def test_a_subfolder_of_assets_images_written_as_before(self, site):
        """`historia/x.jpg` was a path under assets/images/; with no such
        folder at the site root, it still resolves there."""
        src, warnings, _ = carousel('historia/nested.png')
        assert src == '/telar/assets/images/historia/nested.png'
        assert warnings == []

    def test_a_subfolder_of_telar_content_objects(self, site):
        _png(site / 'telar-content/objects/story1/map.png', (800, 600))
        src, warnings, _ = carousel('story1/map.png')
        assert src == '/telar/telar-content/objects/story1/map.png'
        assert warnings == []

    def test_the_site_root_wins_over_the_image_folders(self, site):
        _png(site / 'historia/nested.png', (800, 600))
        assert carousel('historia/nested.png')[0] == '/telar/historia/nested.png'

    def test_a_leading_slash_is_the_same_site_root(self, site):
        src, warnings, _ = carousel('/telar-content/objects/only-objects.png')
        assert src == '/telar/telar-content/objects/only-objects.png'
        assert warnings == []

    def test_a_leading_slash_that_carries_the_baseurl_gets_it_once(self, site):
        src, warnings, _ = carousel('/telar/telar-content/objects/only-objects.png')
        assert src == '/telar/telar-content/objects/only-objects.png'
        assert warnings == []

    def test_a_thumbnail_path_as_objects_csv_stores_it(self, site):
        """objects.csv `thumbnail` holds a path from the site root, with or
        without a leading slash; the Compositor can write either as is."""
        assert carousel('/assets/images/thumbs/thumb.png')[0] == '/telar/assets/images/thumbs/thumb.png'
        assert carousel('assets/images/thumbs/thumb.png')[0] == '/telar/assets/images/thumbs/thumb.png'

    def test_a_site_at_a_domain_root(self, site):
        src, _, _ = carousel('telar-content/objects/only-objects.png', base_url='')
        assert src == '/telar-content/objects/only-objects.png'

    def test_a_missing_path_warns_with_the_path(self, site):
        src, warnings, _ = carousel('telar-content/objects/nope.png')
        assert src == '/telar/telar-content/objects/nope.png'
        assert [w['message'] for w in warnings] == [
            'Carousel image not found: telar-content/objects/nope.png '
            '(expected at telar-content/objects/nope.png)']

    def test_the_path_is_measured(self, site):
        _, _, size_class = carousel('telar-content/objects/only-objects.png')
        assert size_class == 'portrait'


class TestBareFileNames:

    def test_found_in_assets_images_as_before(self, site):
        src, warnings, _ = carousel('only-assets.png')
        assert src == '/telar/assets/images/only-assets.png'
        assert warnings == []

    def test_found_in_telar_content_objects(self, site):
        src, warnings, size_class = carousel('only-objects.png')
        assert src == '/telar/telar-content/objects/only-objects.png'
        assert warnings == []
        assert size_class == 'portrait'

    def test_assets_images_wins_when_both_hold_the_name(self, site):
        src, warnings, size_class = carousel('both.png')
        assert src == '/telar/assets/images/both.png'
        assert warnings == []
        # Measured from the file published, the wide one.
        assert size_class == 'compact'
        assert get_image_dimensions('both.png') == (1600, 400)

    def test_a_missing_name_points_at_assets_images_and_says_where_it_looked(self, site):
        src, warnings, size_class = carousel('missing.png')
        assert src == '/telar/assets/images/missing.png'
        assert [w['message'] for w in warnings] == [
            'Carousel image not found: missing.png (looked in assets/images/ or '
            'telar-content/objects/; the slide points at assets/images/missing.png)']
        assert size_class == 'default'

    def test_an_empty_value_is_not_found(self, site):
        """A folder is not an image: a blank `image:`, as the Compositor
        writes for an object with no thumbnail, names no file."""
        _, warnings, _ = carousel('')
        assert len(warnings) == 1
        assert 'not found' in warnings[0]['message']


class TestTheSharedLookup:

    def test_validate_and_dimensions_answer_from_the_same_file(self, site):
        assert validate_image_path('only-objects.png', 'test.md') == (
            True, 'telar-content/objects/only-objects.png')
        assert get_image_dimensions('only-objects.png') == (400, 800)
        assert validate_image_path('missing.png', 'test.md') == (
            False, 'assets/images/missing.png')
        assert get_image_dimensions('missing.png') is None

    def test_locate_reads_the_baseurl_from_the_config(self, site):
        assert locate_image('/telar/assets/images/only-assets.png') == (
            'assets/images/only-assets.png', True)
