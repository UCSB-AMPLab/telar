"""
Unit Tests for Image Processing Functions

This module tests the markdown image processing that converts image syntax
with optional size modifiers and captions into HTML figures. The processing
happens BEFORE standard markdown conversion to allow custom syntax.

Supported syntax:
- ![alt](path) — basic image
- ![alt](path){size} — image with size class (sm, md, lg, full)
- Line after image becomes caption (optional "caption:" prefix stripped)

Version: v1.8.0
"""

import sys
import os
import pytest

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from csv_to_json import process_images


class TestProcessImages:
    """Tests for process_images function."""

    def test_basic_image_conversion(self):
        """Should convert basic image syntax to HTML figure."""
        text = '![Portrait](image.jpg)'
        result = process_images(text)
        assert '<figure class="telar-image-figure">' in result
        assert '<img src=' in result
        assert 'alt="Portrait"' in result

    def test_prepends_default_path(self):
        """Should prepend /telar-content/objects/ to relative paths."""
        text = '![Alt](photo.jpg)'
        result = process_images(text, base_url='')
        assert 'src="/telar-content/objects/photo.jpg"' in result

    def test_relative_path_carries_the_site_base_url(self):
        """A bare file name resolves under the site's baseurl.

        The HTML is published unrewritten on a glossary page, in the glossary
        panel and on a user page, so a path without the baseurl is fetched
        from the host root and 404s on a project site.
        """
        result = process_images('![Alt](photo.jpg)', base_url='/telar')
        assert 'src="/telar/telar-content/objects/photo.jpg"' in result

    def test_base_url_leaves_author_paths_alone(self):
        """A root-absolute path or a URL is the author's, written as given."""
        assert 'src="/custom/image.jpg"' in process_images(
            '![Alt](/custom/image.jpg)', base_url='/telar')
        assert 'src="https://example.com/i.jpg"' in process_images(
            '![Alt](https://example.com/i.jpg)', base_url='/telar')

    def test_alt_text_may_hold_bracketed_text(self):
        """Brackets nested in the alt text, as in a caption carrying a
        bracketed translation, still make an image, with its path resolved."""
        result = process_images(
            '![Framework of a Kogi loom [Marco de un telar kogui]]'
            '(historia/1.3.3.1.jpg){md}', base_url='/telar')
        assert 'src="/telar/telar-content/objects/historia/1.3.3.1.jpg"' in result
        assert 'alt="Framework of a Kogi loom [Marco de un telar kogui]"' in result
        assert 'class="img-md"' in result

    def test_unbalanced_brackets_in_alt_text_are_not_an_image(self):
        """An unclosed bracket makes no image, as the markdown library reads
        it: the text is left for that library, which renders a link."""
        text = '![A [stray bracket](photo.jpg)'
        assert process_images(text, base_url='') == text

    def test_an_entity_in_alt_text_is_the_character_it_names(self):
        """&#91; is how a literal bracket is written; it is published as a
        bracket, not as the text "&#91;"."""
        result = process_images('![Loom &#91;Telar&#93;](a.jpg)', base_url='')
        assert 'alt="Loom [Telar]"' in result

    def test_markup_characters_in_alt_text_are_still_escaped(self):
        result = process_images(
            '![Tom &amp; Jerry & "friends" <b>](a.jpg)', base_url='')
        assert 'alt="Tom &amp; Jerry &amp; &quot;friends&quot; &lt;b&gt;"' in result

    def test_an_inline_image_resolves_its_path_as_a_block_image_does(self):
        """An image inside a sentence stays inline, but a relative path
        still resolves under the site's baseurl, or it 404s."""
        result = process_images('Text ![a](x.jpg) inline', base_url='/telar')
        assert result == 'Text ![a](/telar/telar-content/objects/x.jpg) inline'

    def test_an_inline_image_keeps_author_paths_and_titles(self):
        text = ('See ![a](/custom/x.jpg), ![b](https://e.org/y.jpg) and '
                '![c [d]](z.jpg "Title") here')
        assert process_images(text, base_url='/telar') == (
            'See ![a](/custom/x.jpg), ![b](https://e.org/y.jpg) and '
            '![c [d]](/telar/telar-content/objects/z.jpg "Title") here')

    def test_an_inline_image_renders_in_its_sentence(self):
        from telar.markdown import process_inline_content
        out = process_inline_content('Text ![a](x.jpg) inline', [])
        html = out.get('content') if isinstance(out, dict) else out
        assert '<figure' not in html
        assert 'src="x.jpg"' not in html
        assert '/telar-content/objects/x.jpg"' in html

    def test_base_url_defaults_to_the_site_config(self, tmp_path, monkeypatch):
        from telar import widgets
        (tmp_path / '_config.yml').write_text('baseurl: "/mysite/"\n', encoding='utf-8')
        monkeypatch.chdir(tmp_path)
        widgets.reset_base_url_cache()
        try:
            result = process_images('![Alt](photo.jpg)')
        finally:
            widgets.reset_base_url_cache()
        assert 'src="/mysite/telar-content/objects/photo.jpg"' in result

    def test_inline_panel_and_glossary_content_carries_the_base_url(
            self, tmp_path, monkeypatch):
        """Spreadsheet content, as a story panel or a CSV glossary definition
        is written, reaches process_images with the configured baseurl."""
        from telar import widgets
        from telar.markdown import process_inline_content
        (tmp_path / '_config.yml').write_text('baseurl: "/telar"\n', encoding='utf-8')
        monkeypatch.chdir(tmp_path)
        widgets.reset_base_url_cache()
        try:
            result = process_inline_content('Text.\n\n![Alt](photo.jpg)')
        finally:
            widgets.reset_base_url_cache()
        assert 'src="/telar/telar-content/objects/photo.jpg"' in result['content']

    def test_preserves_absolute_paths(self):
        """Should preserve paths starting with /."""
        text = '![Alt](/custom/path/image.jpg)'
        result = process_images(text)
        assert 'src="/custom/path/image.jpg"' in result

    def test_preserves_http_urls(self):
        """Should preserve HTTP/HTTPS URLs."""
        text = '![Alt](https://example.com/image.jpg)'
        result = process_images(text)
        assert 'src="https://example.com/image.jpg"' in result

    def test_size_small(self):
        """Should apply sm size class."""
        text = '![Alt](image.jpg){sm}'
        result = process_images(text)
        assert 'class="img-sm"' in result

    def test_size_medium(self):
        """Should apply md size class."""
        text = '![Alt](image.jpg){md}'
        result = process_images(text)
        assert 'class="img-md"' in result

    def test_size_large(self):
        """Should apply lg size class."""
        text = '![Alt](image.jpg){lg}'
        result = process_images(text)
        assert 'class="img-lg"' in result

    def test_size_full(self):
        """Should apply full size class."""
        text = '![Alt](image.jpg){full}'
        result = process_images(text)
        assert 'class="img-full"' in result

    def test_size_word_forms(self):
        """Should accept word forms of sizes (small, medium, large)."""
        assert 'class="img-sm"' in process_images('![Alt](i.jpg){small}')
        assert 'class="img-md"' in process_images('![Alt](i.jpg){medium}')
        assert 'class="img-lg"' in process_images('![Alt](i.jpg){large}')

    def test_size_case_insensitive(self):
        """Should handle size modifiers case-insensitively."""
        assert 'class="img-md"' in process_images('![Alt](i.jpg){MD}')
        assert 'class="img-lg"' in process_images('![Alt](i.jpg){LARGE}')

    def test_caption_from_next_line(self):
        """Should use next line as caption."""
        text = """![Portrait](image.jpg)
Francisco Maldonado, colonial figure"""
        result = process_images(text)
        assert '<figcaption class="telar-image-caption">' in result
        assert 'Francisco Maldonado' in result

    def test_caption_with_prefix(self):
        """Should strip 'caption:' prefix from caption."""
        text = """![Portrait](image.jpg)
caption: A historical portrait"""
        result = process_images(text)
        assert 'A historical portrait' in result
        assert 'caption:' not in result.lower() or 'telar-image-caption' in result

    def test_caption_markdown_converted(self):
        """Should convert markdown in captions."""
        text = """![Alt](image.jpg)
*Italic caption* with **bold**"""
        result = process_images(text)
        assert '<em>' in result or '<i>' in result

    def test_no_caption_when_blank_line(self):
        """Should not create caption when next line is blank."""
        text = """![Alt](image.jpg)

Next paragraph"""
        result = process_images(text)
        # Should still have figure but no figcaption with the paragraph content
        assert '<figure' in result
        # The paragraph should be separate, not in figcaption
        assert 'Next paragraph' in result

    def test_no_caption_when_another_image(self):
        """Should not use another image as caption."""
        text = """![First](first.jpg)
![Second](second.jpg)"""
        result = process_images(text)
        # Should have two separate figures
        assert result.count('<figure') == 2

    def test_no_caption_when_widget(self):
        """Should not use widget syntax as caption."""
        text = """![Alt](image.jpg)
:::carousel"""
        result = process_images(text)
        # Widget syntax should not become caption
        assert ':::carousel' in result

    def test_preserves_non_image_content(self):
        """Should preserve text that isn't image syntax."""
        text = """Some text before.

![Alt](image.jpg)

Some text after."""
        result = process_images(text)
        assert 'Some text before.' in result
        assert 'Some text after.' in result

    def test_handles_empty_alt_text(self):
        """Should handle empty alt text."""
        text = '![](image.jpg)'
        result = process_images(text)
        assert 'alt=""' in result

    def test_handles_multiple_images(self):
        """Should process multiple images."""
        text = """![First](first.jpg){sm}
Caption for first

![Second](second.jpg){lg}
Caption for second"""
        result = process_images(text)
        assert result.count('<figure') == 2
        assert 'img-sm' in result
        assert 'img-lg' in result
