"""
Widget Parsing and Rendering

This module deals with Telar's widget system, which lets authors embed
interactive components — carousels, tabbed panels, accordions, and
bibliographies — inside story panel content using a fenced-block syntax borrowed from
markdown's code fence pattern: `:::widget_type ... :::`.

Like image processing, widget parsing runs before the markdown library
converts the text to HTML. The main entry point is `process_widgets()`,
which uses a regex to find `:::type ... :::` blocks, identifies the
widget type, parses the content with the appropriate parser, and replaces
the block with rendered HTML from a Jinja2 template in `_includes/widgets/`.

Each widget type has its own parser:

- `parse_carousel_widget()` expects `key: value` blocks separated by `---`,
  where each block defines one slide (image, alt, caption, credit). It
  validates that images exist using `validate_image_path()` from the images
  module, and calls `get_image_dimensions()` to calculate aspect ratios.
  The maximum aspect ratio across all slides determines the carousel's
  CSS size class (compact, default, tall, or portrait).

- `parse_tabs_widget()` and `parse_accordion_widget()` both use
  `parse_markdown_sections()` to split content on `## ` headers into
  titled sections. Tabs require 2-4 sections; accordions require 2-6.
  Each section's body is converted from markdown to HTML.

The module-level `_widget_counter` integer generates unique IDs for each
widget instance within a build, ensuring that multiple widgets on the
same page don't collide.

`parse_key_value_block()` is a simple helper that extracts `key: value`
pairs from a text block, used by the carousel parser.

`render_widget_html()` loads a Jinja2 template from `_includes/widgets/`
and renders it with the parsed widget data. If the template fails, it
returns an error `<div>` instead of crashing the build.

Version: v1.5.0
"""

import html
import re
import markdown
from html.parser import HTMLParser
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from telar.images import validate_image_path, get_image_dimensions


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


def parse_carousel_widget(content, file_path, warnings_list):
    """
    Parse carousel widget content.

    Expected format:
    :::carousel
    image: path.jpg
    alt: Description
    caption: Caption text
    credit: Attribution

    ---

    image: path2.jpg
    :::

    Returns:
        dict: Parsed carousel data with 'items' list and 'size_class'
    """
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

        # Validate image exists
        image_exists, full_path = validate_image_path(data['image'], file_path)
        if not image_exists:
            warnings_list.append({
                'type': 'widget',
                'widget_type': 'carousel',
                'message': f'Carousel image not found: {data["image"]} (expected at {full_path})'
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
        if 'caption' in data:
            caption_html = markdown.markdown(data['caption'])
            stripped = re.sub(r'^<p>(.*)</p>$', r'\1', caption_html.strip())
            data['caption'] = sanitize_caption_html(stripped)
        if 'credit' in data:
            credit_html = markdown.markdown(data['credit'])
            stripped = re.sub(r'^<p>(.*)</p>$', r'\1', credit_html.strip())
            data['credit'] = sanitize_caption_html(stripped)

        items.append(data)

    # Analyze aspect ratios to determine optimal carousel height
    aspect_ratios = []
    for item in items:
        dimensions = get_image_dimensions(item['image'])
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

    return {'items': items, 'size_class': size_class}


def parse_markdown_sections(content):
    """
    Parse content into sections based on ## headers.

    Args:
        content: Markdown text with ## headers

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
    for section in sections:
        content_text = '\n'.join(section['content']).strip()
        # Convert markdown to HTML
        section['content_html'] = markdown.markdown(content_text, extensions=['extra', 'nl2br'])

    return sections


def parse_tabs_widget(content, file_path, warnings_list):
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
    sections = parse_markdown_sections(content)

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


def parse_accordion_widget(content, file_path, warnings_list):
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
    sections = parse_markdown_sections(content)

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


def parse_bibliography_widget(content, file_path, warnings_list):
    """Parse bibliography widget content.

    Expected format:
    :::bibliography
    Author, A. (2020). *Title of work*. Publisher.

    Author, B. (2019). Title with [link](url). Journal, 1(2), 3-4.
    :::

    Each blank-line-separated block becomes one entry with hanging indent.

    Returns:
        dict: Parsed bibliography data with 'entries' list
    """
    entries = []
    for block in content.split('\n\n'):
        block = block.strip()
        if not block:
            continue
        html = markdown.markdown(block, extensions=['extra', 'nl2br'])
        entries.append({'content_html': html})

    if not entries:
        warnings_list.append({
            'type': 'widget',
            'widget_type': 'bibliography',
            'message': 'Bibliography block contains no entries'
        })

    return {'entries': entries}


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

        # Render with data
        rendered = template.render(
            widget_id=widget_id,
            base_url='{{ site.baseurl }}',  # Will be processed by Jekyll
            **widget_data
        )

        return rendered

    except Exception as e:
        # Return error HTML if template rendering fails
        return (f'<div class="telar-widget-error">Widget rendering error '
                f'({html.escape(str(widget_type))}): {html.escape(str(e))}</div>')


def process_widgets(text, file_path, warnings_list):
    """
    Find and process :::widget::: blocks in markdown text.
    Must be called BEFORE markdown.markdown() conversion.

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
            'bibliography': parse_bibliography_widget
        }

        if widget_type not in widget_parsers:
            warnings_list.append({
                'type': 'widget',
                'widget_type': widget_type,
                'message': f'Unknown widget type: {widget_type}'
            })
            return f'<div class="telar-widget-error">Unknown widget type: {widget_type}</div>'

        # Parse widget content
        parser = widget_parsers[widget_type]
        widget_data = parser(content, file_path, warnings_list)

        # Render HTML
        html = render_widget_html(widget_type, widget_data, widget_id)

        return html

    return re.sub(pattern, replace_widget, text, flags=re.DOTALL)
