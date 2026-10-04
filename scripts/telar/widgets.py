"""
Widget Parsing and Rendering

This module deals with Telar's widget system, which lets authors embed
interactive components — carousels, tabbed panels, accordions,
bibliographies and glossary callouts — inside story panel content using a fenced-block syntax borrowed from
markdown's code fence pattern: `:::widget_type ... :::`.

Like image processing, widget parsing runs before the markdown library
converts the text to HTML. The main entry point is `process_widgets()`,
which uses a regex to find `:::type ... :::` blocks, identifies the
widget type, parses the content with the appropriate parser, and replaces
the block with rendered HTML from a Jinja2 template in `_includes/widgets/`.

Each widget type has its own parser:

- `parse_carousel_widget()` expects `key: value` blocks separated by `---`,
  where each block defines one slide (image, alt, caption, credit). It
  warns when a slide's image is not in the site, and calls
  `get_image_dimensions()` to calculate aspect ratios.
  The maximum aspect ratio across all slides determines the carousel's
  CSS size class (compact, default, tall, or portrait). It also resolves
  each slide's final `src`: absolute http(s) URLs pass through unchanged,
  while a file in the site is found by `locate_image()` (a path with a
  folder in it from the site root, a bare file name in `assets/images/` and
  then `telar-content/objects/`) and joined to the site's configured
  `baseurl`. The carousel template only ever renders `item.src` — it
  carries no URL logic of its own.

  The base URL is read here rather than left as a Liquid token because the
  two render paths do not treat such a token alike. A widget in a page is
  rendered by Jekyll and would resolve it; a widget in a story reaches the
  browser through `story.html`'s `jsonify`, which serialises strings without
  re-parsing Liquid inside them, so the token arrived at the reader verbatim.
  Resolving in Python is what makes both paths produce the same URL.

- `parse_tabs_widget()` and `parse_accordion_widget()` both use
  `parse_markdown_sections()` to split content on `## ` headers into
  titled sections. Tabs require 2-4 sections; accordions require 2-6.
  Each section's body is converted from markdown to HTML.

The module-level `_widget_counter` integer generates unique IDs for each
widget instance within a build, ensuring that multiple widgets on the
same page don't collide.

- `parse_glossary_widget()` reads `entry:` and `align:`. The callout it
  stands for needs the glossary, which this step does not have, so it
  writes a slot (`glossary-callout-slot`) that `process_glossary_links()`
  in `telar/glossary.py` fills once the text is HTML. Every path that runs
  widgets runs that pass after them, and it resolves the entry exactly as
  it resolves `[[entry]]`, warning and marking an unknown entry the same way.

`parse_key_value_block()` is a simple helper that extracts `key: value`
pairs from a text block, used by the carousel parser.

`render_widget_html()` loads a Jinja2 template from `_includes/widgets/`
and renders it with the parsed widget data. If the template fails, it
returns an error `<div>` instead of crashing the build.

Version: v1.8.0
"""

import html
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from telar.config import get_lang_string
from telar.images import BARE_IMAGE_FOLDERS, get_image_dimensions, locate_image
from telar.latex import convert_markdown


# Widget instance counter for unique IDs within a build
_widget_counter = 0


# Inline tags a caption or credit realistically needs. Everything else
# (script, img, iframe, block elements, …) is dropped to text, and all
# attributes except a safe href/title on links are stripped.
_CAPTION_ALLOWED_TAGS = {'em', 'strong', 'i', 'b', 'a', 'code', 'sup', 'sub', 'br'}
_CAPTION_ALLOWED_ATTRS = {'a': {'href', 'title'}}
_CAPTION_SAFE_URL = re.compile(r'^(https?:|mailto:|/|\.|#)', re.IGNORECASE)


class _CaptionSanitizer(HTMLParser):
    """Allowlist sanitiser for markdown-rendered caption/credit HTML.

    Keeps a fixed set of inline tags, drops every other tag (its text content
    is preserved), removes all event-handler and unknown attributes, and only
    keeps href/title on links when the URL uses a safe scheme. Stdlib only —
    no third-party sanitiser dependency.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag not in _CAPTION_ALLOWED_TAGS:
            return
        if tag == 'br':
            self._parts.append('<br>')
            return
        allowed = _CAPTION_ALLOWED_ATTRS.get(tag, set())
        kept = []
        for name, value in attrs:
            if name not in allowed:
                continue
            if name in ('href', 'src') and not (value and _CAPTION_SAFE_URL.match(value)):
                continue
            kept.append((name, value))
        attr_str = ''.join(
            f' {name}="{html.escape(value or "", quote=True)}"' for name, value in kept
        )
        self._parts.append(f'<{tag}{attr_str}>')

    def handle_startendtag(self, tag, attrs):
        # Self-closing form, e.g. <br/> — treat like a start tag.
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in _CAPTION_ALLOWED_TAGS and tag != 'br':
            self._parts.append(f'</{tag}>')

    def handle_data(self, data):
        self._parts.append(html.escape(data, quote=False))

    def get_html(self):
        return ''.join(self._parts)


def sanitize_caption_html(rendered_html):
    """Strip unsafe tags/attributes from markdown-rendered caption/credit HTML."""
    parser = _CaptionSanitizer()
    parser.feed(rendered_html)
    parser.close()
    return parser.get_html()


def _caption_html(rendered_html):
    """Unwrap a one-paragraph caption and sanitise what is left.

    Runs as `convert_markdown`'s post-processing step, so it sees LaTeX as
    a placeholder rather than as a formula the sanitiser would re-parse.
    """
    stripped = re.sub(r'^<p>(.*)</p>$', r'\1', rendered_html.strip())
    return sanitize_caption_html(stripped)


def get_widget_id():
    """Generate unique widget ID for this build"""
    global _widget_counter
    _widget_counter += 1
    return f"widget-{_widget_counter}"


def parse_key_value_block(content):
    """
    Parse key: value pairs from a text block.

    Args:
        content: Text containing key: value pairs

    Returns:
        dict: Parsed key-value pairs
    """
    data = {}
    for line in content.strip().split('\n'):
        line = line.strip()
        if ':' in line and not line.startswith('#'):
            key, value = line.split(':', 1)
            data[key.strip()] = value.strip()
    return data


def declared_dimensions(item):
    """The `width` and `height` an item declares, or None if it declares
    neither, either, or something that is not a positive whole number.

    A remote image is otherwise downloaded in full to read its size, on
    every build, and silently sized as default when the download fails.
    Declaring the dimensions is how content that lives elsewhere -- the
    demo bundles above all -- keeps the build off the network.
    """
    try:
        width, height = int(item['width']), int(item['height'])
    except (KeyError, ValueError, TypeError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


# The site's own prefix, for turning an author's bare filename into a path a
# browser can fetch. Read from _config.yml rather than emitted as a Liquid
# token: a widget in a page is rendered by Jekyll and would resolve such a
# token, but a widget in a story reaches the browser through story.html's
# `jsonify`, which serialises strings without re-parsing Liquid inside them.
# The same carousel therefore worked in one place and published a literal
# "{{ site.baseurl }}" in the other. Resolving here is what makes the two
# paths the same path.
_BASE_URL_UNSET = object()
_cached_base_url = _BASE_URL_UNSET


def site_base_url():
    """The site's baseurl, as configured, with no trailing slash.

    Empty string for a site served at a domain root, which is a valid answer
    and not a missing one — hence the sentinel rather than a falsy check.
    """
    global _cached_base_url
    if _cached_base_url is _BASE_URL_UNSET:
        _cached_base_url = _read_base_url_from_config()
    return _cached_base_url


def _read_base_url_from_config():
    config_path = Path('_config.yml')
    if not config_path.exists():
        return ''
    try:
        with open(config_path, 'r', encoding='utf-8') as handle:
            config = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return ''
    return str(config.get('baseurl') or '').rstrip('/')


def reset_base_url_cache():
    """Forget the cached baseurl. For tests, and for a build that rewrites
    _config.yml mid-run."""
    global _cached_base_url
    _cached_base_url = _BASE_URL_UNSET


def _missing_image_message(image, site_path):
    if '/' in image:
        return f'Carousel image not found: {image} (expected at {site_path})'
    folders = ' or '.join(f'{folder}/' for folder in BARE_IMAGE_FOLDERS)
    return (f'Carousel image not found: {image} (looked in {folders}; '
            f'the slide points at {site_path})')


def parse_carousel_widget(content, file_path, warnings_list, base_url=None):
    """
    Parse carousel widget content.

    Expected format:
    :::carousel
    image: path.jpg
    alt: Description
    caption: Caption text
    credit: Attribution
    width: 1200
    height: 800

    ---

    image: path2.jpg
    :::

    `width` and `height` are optional. When both are given the image is not
    opened to measure it; see `declared_dimensions`.

    Returns:
        dict: Parsed carousel data with 'items' list and 'size_class'
    """
    if base_url is None:
        base_url = site_base_url()

    items = []
    blocks = content.split('---')

    for block_num, block in enumerate(blocks, 1):
        block = block.strip()
        if not block:
            continue

        data = parse_key_value_block(block)

        # Validate required fields
        if 'image' not in data:
            warnings_list.append({
                'type': 'widget',
                'widget_type': 'carousel',
                'message': f'Carousel item {block_num} missing required field: image'
            })
            continue

        # Resolve the final image src here rather than in the template.
        # Absolute http(s) URLs are used as given; a file in the site is
        # joined to the site's configured baseurl, so the value that reaches
        # the browser is a path it can fetch by whichever route the widget
        # travelled.
        image = data['image']
        if image.startswith('http://') or image.startswith('https://'):
            data['src'] = image
        else:
            site_path, found = locate_image(image, base_url)
            data['src'] = '%s/%s' % (base_url, site_path)
            if not found:
                warnings_list.append({
                    'type': 'widget',
                    'widget_type': 'carousel',
                    'message': _missing_image_message(image, site_path)
                })

        # Warn if alt text missing
        if 'alt' not in data:
            warnings_list.append({
                'type': 'widget',
                'widget_type': 'carousel',
                'message': f'Carousel item {block_num} missing alt text (accessibility concern)'
            })
            data['alt'] = ''

        # Process caption/credit through markdown (for italics, etc.), then
        # sanitise the result so an author-supplied <script>/<img onerror>/etc.
        # cannot reach the rendered page through these fields.
        for field in ('caption', 'credit'):
            if field in data:
                data[field] = convert_markdown(
                    data[field], post_process=_caption_html,
                    restore_as_text=True)

        items.append(data)

    return {'items': items, 'size_class': _carousel_size_class(items)}


def _carousel_size_class(items):
    """The carousel's height class, from the tallest image in it.

    An image whose size cannot be read, or whose width is zero, does not
    count; a carousel with none that can be read is 'default'.
    """
    aspect_ratios = []
    for item in items:
        dimensions = declared_dimensions(item) or get_image_dimensions(item['image'])
        if dimensions:
            width, height = dimensions
            if width > 0:  # Avoid division by zero
                aspect_ratio = height / width
                aspect_ratios.append(aspect_ratio)

    # Determine size class based on maximum aspect ratio
    size_class = 'default'  # Default fallback
    if aspect_ratios:
        max_aspect_ratio = max(aspect_ratios)
        if max_aspect_ratio < 0.6:
            size_class = 'compact'  # Wide panoramas
        elif max_aspect_ratio < 1.0:
            size_class = 'default'  # Landscape
        elif max_aspect_ratio < 1.5:
            size_class = 'tall'  # Square to mild portrait
        else:
            size_class = 'portrait'  # Strong portrait
    return size_class


def parse_markdown_sections(content, footnote_scope=None):
    """
    Parse content into sections based on ## headers.

    Each section is its own conversion. With *footnote_scope*, section n's
    footnote anchors carry `<footnote_scope>-<n>`, so two sections that
    use the same label still link each reference to its own note.

    Args:
        content: Markdown text with ## headers
        footnote_scope: Optional widget id for the sections' note anchors

    Returns:
        list: List of dicts with 'title' and 'content' keys
    """
    sections = []
    current_section = None

    for line in content.split('\n'):
        if line.startswith('## '):
            # Start new section
            if current_section:
                sections.append(current_section)
            current_section = {
                'title': line[3:].strip(),
                'content': []
            }
        elif current_section:
            current_section['content'].append(line)

    # Add last section
    if current_section:
        sections.append(current_section)

    # Convert content lists to strings and process markdown
    for number, section in enumerate(sections, 1):
        content_text = '\n'.join(section['content']).strip()
        section['content_html'] = convert_markdown(
            content_text, extensions=['extra', 'nl2br'],
            footnote_scope=_section_scope(footnote_scope, number))

    return sections


def _section_scope(widget_id, number):
    """The footnote scope for the *number*th conversion inside a widget."""
    return '%s-%d' % (widget_id, number) if widget_id else None


def parse_tabs_widget(content, file_path, warnings_list, widget_id=None):
    """
    Parse tabs widget content.

    Expected format:
    :::tabs
    ## Tab 1 Title
    Content here...

    ## Tab 2 Title
    More content...
    :::

    Returns:
        dict: Parsed tabs data with 'tabs' list
    """
    sections = parse_markdown_sections(content, widget_id)

    # Validate tab count
    if len(sections) < 2:
        warnings_list.append({
            'type': 'widget',
            'widget_type': 'tabs',
            'message': f'Tabs widget must have at least 2 tabs (found {len(sections)})'
        })
    elif len(sections) > 4:
        warnings_list.append({
            'type': 'widget',
            'widget_type': 'tabs',
            'message': f'Tabs widget should have maximum 4 tabs (found {len(sections)})'
        })

    # Validate each tab has content
    for i, section in enumerate(sections, 1):
        if not section.get('content_html', '').strip():
            warnings_list.append({
                'type': 'widget',
                'widget_type': 'tabs',
                'message': f'Tab {i} "{section["title"]}" has no content'
            })

    return {'tabs': sections}


def parse_accordion_widget(content, file_path, warnings_list, widget_id=None):
    """
    Parse accordion widget content.

    Expected format:
    :::accordion
    ## Panel 1 Title
    Content here...

    ## Panel 2 Title
    More content...
    :::

    Returns:
        dict: Parsed accordion data with 'panels' list
    """
    sections = parse_markdown_sections(content, widget_id)

    # Validate panel count
    if len(sections) < 2:
        warnings_list.append({
            'type': 'widget',
            'widget_type': 'accordion',
            'message': f'Accordion widget must have at least 2 panels (found {len(sections)})'
        })
    elif len(sections) > 6:
        warnings_list.append({
            'type': 'widget',
            'widget_type': 'accordion',
            'message': f'Accordion widget should have maximum 6 panels (found {len(sections)})'
        })

    # Validate each panel has content
    for i, section in enumerate(sections, 1):
        if not section.get('content_html', '').strip():
            warnings_list.append({
                'type': 'widget',
                'widget_type': 'accordion',
                'message': f'Accordion panel {i} "{section["title"]}" has no content'
            })

    return {'panels': sections}


def parse_bibliography_widget(content, file_path, warnings_list, widget_id=None):
    """Parse bibliography widget content.

    Expected format:
    :::bibliography
    Author, A. (2020). *Title of work*. Publisher.

    Author, B. (2019). Title with [link](url). Journal, 1(2), 3-4.
    :::

    Each blank-line-separated block becomes one entry with hanging indent,
    converted on its own; with *widget_id*, entry n's footnote anchors
    carry `<widget_id>-<n>`.

    Returns:
        dict: Parsed bibliography data with 'entries' list
    """
    entries = []
    for block in content.split('\n\n'):
        block = block.strip()
        if not block:
            continue
        html = convert_markdown(
            block, extensions=['extra', 'nl2br'],
            footnote_scope=_section_scope(widget_id, len(entries) + 1))
        entries.append({'content_html': html})

    if not entries:
        warnings_list.append({
            'type': 'widget',
            'widget_type': 'bibliography',
            'message': 'Bibliography block contains no entries'
        })

    return {'entries': entries}


# What `align:` accepts, folded to lower case and without accents. Right
# is the default.
GLOSSARY_CALLOUT_ALIGN = {
    'right': 'right', 'derecha': 'right',
    'left': 'left', 'izquierda': 'left',
}


def parse_glossary_widget(content, file_path, warnings_list, widget_id=None):
    """Parse a glossary callout into the slot the glossary pass fills.

    Expected format:
    :::glossary
    entry: term_id
    align: left
    :::

    `entry` is resolved later, by `process_glossary_links()`; a missing one
    reaches it as an empty id and is reported as a missing entry is.
    `align` is `right` (the default) or `left`, `derecha` or `izquierda`;
    any other value is reported and falls back to right.

    Returns:
        str: The slot, as a block of HTML on its own lines.
    """
    data = parse_key_value_block(content)
    entry = data.get('entry', '').strip()
    raw_align = data.get('align', '').strip()
    align = 'right'
    if raw_align:
        folded = ''.join(ch for ch in unicodedata.normalize('NFKD', raw_align)
                         if not unicodedata.combining(ch)).casefold()
        align = GLOSSARY_CALLOUT_ALIGN.get(folded)
        if align is None:
            warnings_list.append({
                'type': 'widget',
                'widget_type': 'glossary',
                'message': (f"Glossary callout for '{entry}' has align "
                            f"'{raw_align}', which is not right or left, so "
                            f"it is placed on the right")
            })
            align = 'right'
    return ('\n\n<div class="glossary-callout-slot"'
            f' data-entry="{html.escape(entry, quote=True)}"'
            f' data-align="{align}"></div>\n\n')


def render_widget_html(widget_type, widget_data, widget_id):
    """
    Render widget HTML using Jinja2 template.

    Args:
        widget_type: Type of widget (carousel, tabs, accordion, bibliography)
        widget_data: Parsed widget data
        widget_id: Unique widget ID

    Returns:
        str: Rendered HTML
    """
    try:
        # Load template from _includes/widgets/
        template_path = Path('_includes/widgets')
        # Autoescape by default so raw-text fields (titles, alt text, image
        # paths) cannot inject markup. Fields that are already rendered/sanitised
        # HTML (content_html, and caption/credit which pass through
        # sanitize_caption_html) are marked "| safe" in the templates.
        env = Environment(
            loader=FileSystemLoader(str(template_path)),
            autoescape=select_autoescape(['html', 'xml']),
        )
        template = env.get_template(f'{widget_type}.html')

        # Render with data. Control labels are resolved from the language pack
        # here (templates are Jinja2, not Liquid, so they cannot reach lang
        # directly); slide_label keeps its {{ number }} token, which the
        # carousel template substitutes per slide.
        rendered = template.render(
            widget_id=widget_id,
            slide_label=get_lang_string('widgets.slide_label'),
            prev_label=get_lang_string('widgets.prev'),
            next_label=get_lang_string('widgets.next'),
            **widget_data
        )

        return rendered

    except Exception as e:
        # Return error HTML if template rendering fails
        error_text = get_lang_string(
            'errors.widgets.rendering_error',
            widget_type=html.escape(str(widget_type)),
            error=html.escape(str(e)),
        )
        return f'<div class="telar-widget-error">{error_text}</div>'


def process_widgets(text, file_path, warnings_list):
    """
    Find and process :::widget::: blocks in markdown text.
    Must be called BEFORE the text is converted to HTML.

    Args:
        text: Raw markdown text
        file_path: Path to markdown file (for error context)
        warnings_list: List to append widget warnings

    Returns:
        str: Text with widgets replaced by rendered HTML
    """
    # Pattern to match :::type ... :::
    pattern = r':::(\w+)\s*\n(.*?)\n:::'

    def replace_widget(match):
        widget_type = match.group(1).lower()
        content = match.group(2)
        widget_id = get_widget_id()

        # Parse based on widget type
        widget_parsers = {
            'carousel': parse_carousel_widget,
            'tabs': parse_tabs_widget,
            'accordion': parse_accordion_widget,
            'bibliography': parse_bibliography_widget,
            'glossary': parse_glossary_widget,
        }

        if widget_type not in widget_parsers:
            # widget_type is regex-constrained to \w+, so it is safe to embed
            # in the returned HTML without escaping.
            unknown_msg = get_lang_string('errors.widgets.unknown_type',
                                          widget_type=widget_type)
            warnings_list.append({
                'type': 'widget',
                'widget_type': widget_type,
                'message': unknown_msg
            })
            return f'<div class="telar-widget-error">{unknown_msg}</div>'

        # Parse widget content
        parser = widget_parsers[widget_type]
        if widget_type == 'glossary':
            # A slot, rendered by the glossary pass rather than here.
            return parser(content, file_path, warnings_list)
        if widget_type == 'carousel':
            widget_data = parser(content, file_path, warnings_list)
        else:
            # Sections and entries are converted one by one and share the
            # page; the widget id keeps their footnote anchors apart.
            widget_data = parser(content, file_path, warnings_list,
                                 widget_id=widget_id)

        # Render HTML
        html = render_widget_html(widget_type, widget_data, widget_id)

        return html

    return re.sub(pattern, replace_widget, text, flags=re.DOTALL)
