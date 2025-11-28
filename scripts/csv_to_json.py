#!/usr/bin/env python3
"""
Convert CSV files from Google Sheets to JSON for Jekyll

Version: v0.6.0-beta
"""

import pandas as pd
import json
import os
import re
from pathlib import Path
import markdown
import urllib.request
import urllib.error
from urllib.parse import urlparse
import ssl
import yaml
from jinja2 import Template, Environment, FileSystemLoader
from PIL import Image
from io import BytesIO

# Global language data cache
_lang_data = None

# Bilingual column name mapping (Spanish → English)
# Supports bilingual story CSV headers (v0.6.0+)
COLUMN_NAME_MAPPING = {
    # Story step columns (Spanish → English)
    'paso': 'step',
    'objeto': 'object',
    'pregunta': 'question',
    'respuesta': 'answer',
    'boton_capa1': 'layer1_button',
    'archivo_capa1': 'layer1_file',
    'boton_capa2': 'layer2_button',
    'archivo_capa2': 'layer2_file',
    # x, y, zoom are the same in both languages

    # Objects columns (Spanish → English) - for IIIF auto-populator support
    'titulo': 'title',
    'descripcion': 'description',
    'url_fuente': 'source_url',
    'creador': 'creator',
    'periodo': 'period',
    'medio': 'medium',
    'dimensiones': 'dimensions',
    'ubicacion': 'location',
    'credito': 'credit',
    'miniatura': 'thumbnail',

    # Project columns (Spanish → English)
    'orden': 'order',
    'id_historia': 'story_id',
    'subtitulo': 'subtitle',
    'firma': 'byline',
}

def load_language_data():
    """
    Load language strings from _config.yml and corresponding language file.

    Returns:
        dict: Language strings, or None if loading fails
    """
    global _lang_data

    # Return cached data if already loaded
    if _lang_data is not None:
        return _lang_data

    try:
        # Read _config.yml to get telar_language setting
        config_path = Path('_config.yml')
        if not config_path.exists():
            return None

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Get language setting, default to English
        language = config.get('telar_language', 'en')

        # Load language file
        lang_file = Path(f'_data/languages/{language}.yml')

        # Fall back to English if language file doesn't exist
        if not lang_file.exists():
            lang_file = Path('_data/languages/en.yml')

        if not lang_file.exists():
            return None

        with open(lang_file, 'r', encoding='utf-8') as f:
            _lang_data = yaml.safe_load(f)

        return _lang_data

    except Exception as e:
        print(f"  [WARN] Could not load language data: {e}")
        return None

def get_lang_string(key_path, **kwargs):
    """
    Get a language string by key path and optionally interpolate variables.

    Args:
        key_path: Dot-separated path to string (e.g., 'errors.object_warnings.iiif_503')
        **kwargs: Variables to interpolate into the string

    Returns:
        str: Localized string with variables interpolated, or key_path if not found
    """
    lang = load_language_data()

    if lang is None:
        return key_path

    # Navigate through nested dict using key path
    keys = key_path.split('.')
    value = lang

    try:
        for key in keys:
            value = value[key]

        # Interpolate variables if provided
        if kwargs:
            # Replace {{ var }} syntax with Python format strings
            for var_name, var_value in kwargs.items():
                value = value.replace(f'{{{{ {var_name} }}}}', str(var_value))

        return value

    except (KeyError, TypeError):
        # Key not found - return the key path itself as fallback
        return key_path

def sanitize_dataframe(df):
    """
    Remove Christmas tree emoji (🎄) from all string fields in dataframe.
    This prevents accidental Christmas Tree Mode triggering from user data.

    Args:
        df: pandas DataFrame to sanitize

    Returns:
        DataFrame: Sanitized dataframe
    """
    for col in df.columns:
        if df[col].dtype == 'object':  # String columns
            df[col] = df[col].apply(lambda x: str(x).replace('🎄', '') if pd.notna(x) else x)

    return df

def get_source_url(row):
    """
    Get source URL for an object, checking both source_url and iiif_manifest columns.

    Implements backward compatibility:
    - Checks source_url first (new standard, v0.5.0+)
    - Falls back to iiif_manifest (legacy column, v0.4.x)
    - Returns empty string if neither exists or both are empty

    Args:
        row: pandas Series or dict representing a CSV row

    Returns:
        str: Source URL (or empty string)
    """
    # Check source_url first (new standard)
    source_url = str(row.get('source_url', '')).strip()
    if source_url:
        return source_url

    # Fall back to iiif_manifest (legacy)
    iiif_manifest = str(row.get('iiif_manifest', '')).strip()
    if iiif_manifest:
        return iiif_manifest

    return ''

def process_images(text):
    """
    Process markdown images: handle sizes and captions.

    Must be called BEFORE markdown conversion (works on raw text).

    Syntax:
    - ![alt](path) - basic image
    - ![alt](path){size} - image with size (sm, md, lg, full)
    - Caption: line immediately following image becomes caption
    - Optional "caption: " prefix gets stripped

    Example:
        ![Portrait](image.jpg){md}
        Francisco Maldonado, encomendero of Fontibón

    Produces:
        <figure class="telar-image-figure">
          <img src="..." alt="Portrait" class="img-md">
          <figcaption class="telar-image-caption">Francisco Maldonado...</figcaption>
        </figure>
    """
    size_map = {
        'small': 'sm', 'medium': 'md', 'large': 'lg', 'full': 'full',
        'sm': 'sm', 'md': 'md', 'lg': 'lg'
    }

    lines = text.split('\n')
    result = []
    i = 0

    # Pattern for image with optional size
    img_pattern = r'^!\[([^\]]*)\]\(([^)]+)\)(?:\{(sm|small|md|medium|lg|large|full)\})?$'

    while i < len(lines):
        line = lines[i]
        match = re.match(img_pattern, line.strip(), re.IGNORECASE)

        if match:
            alt = match.group(1)
            src = match.group(2)
            size_input = match.group(3)

            # Determine size class
            if size_input:
                size_class = size_map.get(size_input.lower(), 'md')
                class_attr = f' class="img-{size_class}"'
            else:
                class_attr = ''

            # Prepend default path if relative
            if not src.startswith('/') and not src.startswith('http'):
                src = f'/components/images/{src}'

            # Check for caption on next line
            caption = None
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                # Caption exists if next line is non-empty and not another image/widget/blank
                if next_line.strip() and not next_line.strip().startswith('!') and not next_line.strip().startswith(':::'):
                    caption = next_line.strip()
                    # Strip "caption: " prefix if present
                    if caption.lower().startswith('caption:'):
                        caption = caption[8:].strip()
                    i += 1  # Skip the caption line

            # Build HTML
            img_tag = f'<img src="{src}" alt="{alt}"{class_attr}>'
            if caption:
                # Convert caption markdown to HTML (strip wrapping <p> tags)
                caption_html = markdown.markdown(caption)
                caption_html = re.sub(r'^<p>(.*)</p>$', r'\1', caption_html.strip())
                html = f'<figure class="telar-image-figure">{img_tag}<figcaption class="telar-image-caption">{caption_html}</figcaption></figure>'
            else:
                html = f'<figure class="telar-image-figure">{img_tag}</figure>'

            result.append(html)
        else:
            result.append(line)

        i += 1

    return '\n'.join(result)


def load_glossary_terms():
    """
    Load glossary terms from components/texts/glossary/*.md files.

    Returns:
        dict: Dictionary mapping term_id to term title, or empty dict if loading fails
    """
    glossary_terms = {}
    glossary_dir = Path('components/texts/glossary')

    if not glossary_dir.exists():
        return glossary_terms

    try:
        for glossary_file in glossary_dir.glob('*.md'):
            with open(glossary_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse frontmatter
            frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n'
            match = re.match(frontmatter_pattern, content, re.DOTALL)

            if match:
                frontmatter_text = match.group(1)

                # Extract term_id and title
                term_id_match = re.search(r'term_id:\s*(\S+)', frontmatter_text)
                title_match = re.search(r'title:\s*["\']?(.*?)["\']?\s*$', frontmatter_text, re.MULTILINE)

                if term_id_match and title_match:
                    term_id = term_id_match.group(1)
                    title = title_match.group(1)
                    glossary_terms[term_id] = title

    except Exception as e:
        print(f"  [WARN] Could not load glossary terms: {e}")

    return glossary_terms


def process_glossary_links(text, glossary_terms, warnings_list=None, step_num=None, layer_name=None):
    """
    Transform [[term]] or [[display|term]] syntax into glossary link HTML.

    Args:
        text: HTML text to process (already converted from markdown)
        glossary_terms: Dictionary mapping term_id to term title
        warnings_list: Optional list to append warning messages
        step_num: Optional step number for warning messages
        layer_name: Optional layer name (e.g., 'layer1', 'layer2') for warning context

    Returns:
        str: Text with glossary links transformed to HTML
    """
    if not text or not glossary_terms:
        return text

    # Pattern: [[display|term]] or [[term]] with flexible spacing
    # Captures: (optional_display) | (term_id)
    pattern = r'\[\[\s*([^|\]]+?)(?:\s*\|\s*([^|\]]+?))?\s*\]\]'

    def replace_glossary_link(match):
        # If pipe is present: [[term|display]], else [[term]]
        if match.group(2):  # Has pipe
            term_id = match.group(1).strip()
            display_text = match.group(2).strip()
        else:  # No pipe
            term_id = match.group(1).strip()
            # Use glossary title as display text
            display_text = glossary_terms.get(term_id, term_id)

        # Check if term exists in glossary
        if term_id in glossary_terms:
            # Valid term - create glossary link
            # Note: data-term-url is intentionally omitted; JavaScript fallback in telar.js
            # constructs the URL dynamically from the current page URL, which correctly
            # handles baseurl for all deployment scenarios (GitHub Pages, subpaths, etc.)
            # Add data-demo attribute for demo terms (prefixed with demo-)
            demo_attr = ' data-demo="true"' if term_id.startswith('demo-') else ''
            return f'<a href="#" class="glossary-inline-link" data-term-id="{term_id}"{demo_attr}>{display_text}</a>'
        else:
            # Invalid term - create error indicator
            if warnings_list is not None:
                # Determine layer number for display
                layer_num = layer_name[-1] if layer_name and layer_name.startswith('layer') else ''
                warning_msg = get_lang_string('errors.object_warnings.glossary_term_not_found', term_id=term_id, layer_num=layer_num)
                warnings_list.append({
                    'step': step_num,
                    'type': 'glossary',
                    'term_id': term_id,
                    'layer': layer_name,
                    'message': warning_msg
                })
            return f'<span class="glossary-link-error" data-term-id="{term_id}">⚠️ [[{match.group(1)}]]</span>'

    return re.sub(pattern, replace_glossary_link, text)


# Widget processing functions
_widget_counter = 0

def get_widget_id():
    """Generate unique widget ID for this build"""
    global _widget_counter
    _widget_counter += 1
    return f"widget-{_widget_counter}"


def validate_image_path(image_path, file_context):
    """
    Validate that an image exists at the expected path (case-insensitive for extensions).
    Skips validation for external URLs (http:// or https://).

    Args:
        image_path: Path relative to assets/images/, or external URL
        file_context: Context string for error messages (e.g., markdown file name)

    Returns:
        tuple: (exists: bool, full_path: str)
    """
    # Skip validation for external URLs
    if image_path.startswith('http://') or image_path.startswith('https://'):
        return (True, image_path)

    full_path = Path('assets/images') / image_path

    # Check exact path first
    if full_path.exists():
        return (True, str(full_path))

    # If not found, try case-insensitive extension match
    # e.g., if looking for image.jpg, also try image.JPG
    if full_path.suffix:
        # Try with uppercase extension
        path_with_upper = full_path.with_suffix(full_path.suffix.upper())
        if path_with_upper.exists():
            return (True, str(path_with_upper))

        # Try with lowercase extension
        path_with_lower = full_path.with_suffix(full_path.suffix.lower())
        if path_with_lower.exists():
            return (True, str(path_with_lower))

    return (False, str(full_path))


def get_image_dimensions(image_path):
    """
    Get dimensions of an image (local or remote).

    Args:
        image_path: Path relative to assets/images/, or external URL

    Returns:
        tuple: (width, height) or None if unable to determine
    """
    try:
        if image_path.startswith('http://') or image_path.startswith('https://'):
            # Fetch remote image
            request = urllib.request.Request(
                image_path,
                headers={'User-Agent': 'Telar/1.0'}
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                image_data = response.read()
                img = Image.open(BytesIO(image_data))
                return img.size  # Returns (width, height)
        else:
            # Load local image
            full_path = Path('assets/images') / image_path
            if full_path.exists():
                with Image.open(full_path) as img:
                    return img.size  # Returns (width, height)
            return None
    except Exception as e:
        # Silently fail - dimension detection is not critical
        return None


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

        # Process caption/credit through markdown (for italics, etc.)
        if 'caption' in data:
            caption_html = markdown.markdown(data['caption'])
            data['caption'] = re.sub(r'^<p>(.*)</p>$', r'\1', caption_html.strip())
        if 'credit' in data:
            credit_html = markdown.markdown(data['credit'])
            data['credit'] = re.sub(r'^<p>(.*)</p>$', r'\1', credit_html.strip())

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


def render_widget_html(widget_type, widget_data, widget_id):
    """
    Render widget HTML using Jinja2 template.

    Args:
        widget_type: Type of widget (carousel, comparison, tabs, accordion)
        widget_data: Parsed widget data
        widget_id: Unique widget ID

    Returns:
        str: Rendered HTML
    """
    try:
        # Load template from _includes/widgets/
        template_path = Path('_includes/widgets')
        env = Environment(loader=FileSystemLoader(str(template_path)))
        template = env.get_template(f'{widget_type}.html')

        # Render with data
        html = template.render(
            widget_id=widget_id,
            base_url='{{ site.baseurl }}',  # Will be processed by Jekyll
            **widget_data
        )

        return html

    except Exception as e:
        # Return error HTML if template rendering fails
        return f'<div class="telar-widget-error">Widget rendering error ({widget_type}): {str(e)}</div>'


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
            'accordion': parse_accordion_widget
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


def read_markdown_file(file_path, widget_warnings=None):
    """
    Read a markdown file and parse frontmatter

    Args:
        file_path: Path to markdown file relative to components/texts/
        widget_warnings: Optional list to collect widget warnings

    Returns:
        dict with 'title' and 'content' keys, or None if file doesn't exist
    """
    full_path = Path('components/texts') / file_path

    if not full_path.exists():
        print(f"Warning: Markdown file not found: {full_path}")
        return None

    # Initialize widget warnings list if not provided
    if widget_warnings is None:
        widget_warnings = []

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse frontmatter
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(frontmatter_pattern, content, re.DOTALL)

        if match:
            frontmatter_text = match.group(1)
            body = match.group(2).strip()

            # Extract title from frontmatter
            title_match = re.search(r'title:\s*["\']?(.*?)["\']?\s*$', frontmatter_text, re.MULTILINE)
            title = title_match.group(1) if title_match else ''

            # Process widgets BEFORE markdown conversion
            body = process_widgets(body, file_path, widget_warnings)

            # Process images (sizes and captions) BEFORE markdown conversion
            body = process_images(body)

            # Convert markdown to HTML
            html_content = markdown.markdown(body, extensions=['extra', 'nl2br'])

            return {
                'title': title,
                'content': html_content
            }
        else:
            # No frontmatter, just content
            content_body = content.strip()

            # Process widgets BEFORE markdown conversion
            content_body = process_widgets(content_body, file_path, widget_warnings)

            # Process images (sizes and captions) BEFORE markdown conversion
            content_body = process_images(content_body)

            # Convert markdown to HTML
            html_content = markdown.markdown(content_body, extensions=['extra', 'nl2br'])
            return {
                'title': '',
                'content': html_content
            }

    except Exception as e:
        print(f"Error reading markdown file {full_path}: {e}")
        return None

def normalize_column_names(df):
    """
    Normalize column names to English using bilingual mapping.
    Supports both English and Spanish column headers (v0.6.0+).

    Args:
        df: pandas DataFrame with potentially Spanish column names

    Returns:
        DataFrame: DataFrame with normalized (English) column names
    """
    # Create a mapping for this dataframe's columns
    rename_map = {}
    for col in df.columns:
        col_lower = col.lower().strip()
        if col_lower in COLUMN_NAME_MAPPING:
            rename_map[col] = COLUMN_NAME_MAPPING[col_lower]
            print(f"  [INFO] Normalized column '{col}' → '{COLUMN_NAME_MAPPING[col_lower]}'")

    # Rename columns if any mappings found
    if rename_map:
        df = df.rename(columns=rename_map)

    return df

def is_header_row(row_values):
    """
    Check if a row contains header names (English or Spanish).

    Args:
        row_values: List of cell values from a row

    Returns:
        bool: True if row appears to be a header row
    """
    # Get all valid column names (English and Spanish)
    valid_names = set(COLUMN_NAME_MAPPING.keys()) | set(COLUMN_NAME_MAPPING.values())

    # Also include common column names not in the mapping
    valid_names.update(['x', 'y', 'zoom', 'order', 'story_id', 'title', 'subtitle',
                        'byline', 'object_id', 'description', 'source_url', 'creator',
                        'period', 'medium', 'dimensions', 'location', 'credit', 'thumbnail'])

    # Count how many cells match known column names
    matches = 0
    total = 0
    for val in row_values:
        if pd.notna(val):
            val_lower = str(val).lower().strip()
            total += 1
            if val_lower in valid_names:
                matches += 1

    # If 80%+ of non-empty cells are column names, it's a header row
    return total > 0 and (matches / total) >= 0.8

def csv_to_json(csv_path, json_path, process_func=None):
    """
    Convert CSV file to JSON

    Args:
        csv_path: Path to input CSV file
        json_path: Path to output JSON file
        process_func: Optional function to process the dataframe before conversion
    """
    if not os.path.exists(csv_path):
        print(f"Warning: {csv_path} not found. Skipping.")
        return

    try:
        # Read CSV file and filter out comment lines (starting with #)
        # We can't use pandas' comment parameter because it treats # anywhere as a comment,
        # which breaks hex color codes like #2c3e50
        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = [line for line in f if not line.strip().startswith('#')]

        # Parse filtered CSV content
        from io import StringIO
        csv_content = ''.join(lines)
        df = pd.read_csv(StringIO(csv_content), on_bad_lines='warn')

        # Filter out columns starting with # (instruction columns)
        df = df[[col for col in df.columns if not col.startswith('#')]]

        # Check if first data row is actually a duplicate header row (bilingual CSVs)
        if len(df) > 0:
            first_row = df.iloc[0]
            if is_header_row(first_row.values):
                print(f"  [INFO] Detected duplicate header row - skipping row 2")
                df = df.iloc[1:].reset_index(drop=True)

        # Normalize column names (Spanish → English) for bilingual support
        df = normalize_column_names(df)

        # Sanitize user data - remove 🎄 emoji to prevent accidental Christmas Tree Mode triggering
        df = sanitize_dataframe(df)

        # Apply processing function if provided
        if process_func:
            df = process_func(df)

        # Convert to JSON
        data = df.to_dict('records')

        # If dataframe has metadata (e.g., viewer warnings), prepend as first element
        if hasattr(df, 'attrs') and 'viewer_warnings' in df.attrs:
            viewer_warnings = df.attrs['viewer_warnings']
            if viewer_warnings:  # Only add if there are warnings
                metadata = {
                    '_metadata': True,
                    'viewer_warnings': viewer_warnings
                }
                data.insert(0, metadata)

        # Write JSON file
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"✓ Converted {csv_path} to {json_path}")

    except Exception as e:
        print(f"Error converting {csv_path}: {e}")

def process_project_setup(df):
    """
    Process project setup CSV
    Expected columns: order, title, subtitle (optional), byline (optional), story_id (optional)

    story_id: Optional semantic identifier for stories (e.g., "your-story", "tutorial")
              If not provided, system falls back to using order number
    """
    stories_list = []
    seen_ids = set()  # Track duplicate story_ids

    for _, row in df.iterrows():
        order = str(row.get('order', '')).strip()
        title = row.get('title', '')
        subtitle = row.get('subtitle', '')
        byline = row.get('byline', '')

        # Check if story_id column exists and extract value (v0.6.0+)
        story_id = ''
        if 'story_id' in df.columns:
            story_id_raw = row.get('story_id', '')
            if pd.notna(story_id_raw):
                story_id = str(story_id_raw).strip()

        # Skip rows with empty order (placeholder rows)
        if not order or not pd.notna(title):
            continue

        # Validate story_id if provided
        if story_id:
            # Check for invalid characters (must be lowercase, numbers, hyphens, underscores)
            import re
            if not re.match(r'^[a-z0-9\-_]+$', story_id):
                print(f"  Warning: story_id '{story_id}' contains invalid characters. Use lowercase letters, numbers, hyphens, underscores only.")

            # Check for duplicates
            if story_id in seen_ids:
                print(f"  Warning: Duplicate story_id '{story_id}' found in project.csv")
            seen_ids.add(story_id)

        story_entry = {
            'number': order,
            'title': title
        }

        # Add story_id to JSON only if it exists and is non-empty
        if story_id:
            story_entry['story_id'] = story_id

        # Add subtitle if present
        if pd.notna(subtitle) and str(subtitle).strip():
            story_entry['subtitle'] = str(subtitle).strip()

        # Add byline if present
        if pd.notna(byline) and str(byline).strip():
            story_entry['byline'] = str(byline).strip()

        stories_list.append(story_entry)

    # Return stories list structure
    result = {'stories': stories_list}
    return pd.DataFrame([result])

def _find_similar_image_filenames(object_id, images_dir):
    """
    Find image files that are similar to object_id but not exact matches.

    Checks for common variations:
    - Case differences: "MyObject" vs "myobject"
    - Hyphen/underscore variations: "my-object" vs "my_object" vs "myobject"
    - Extra characters or minor typos

    Args:
        object_id: The object ID to match against
        images_dir: Path object to the images directory

    Returns:
        List of similar filenames (just the filename, not full path)
    """
    import re
    from difflib import SequenceMatcher

    if not images_dir.exists():
        return []

    # Normalize object_id for comparison (remove hyphens, underscores, lowercase)
    normalized_id = re.sub(r'[-_\s]', '', object_id.lower())

    similar_files = []
    valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff'}

    for file_path in images_dir.iterdir():
        if not file_path.is_file():
            continue

        # Only check image files
        if file_path.suffix.lower() not in valid_extensions:
            continue

        # Get filename without extension
        basename = file_path.stem
        normalized_file = re.sub(r'[-_\s]', '', basename.lower())

        # Skip if this is the exact object_id (exact matches are checked elsewhere)
        if basename.lower() == object_id.lower():
            continue

        # Calculate similarity ratio
        similarity = SequenceMatcher(None, normalized_id, normalized_file).ratio()

        # Consider similar if > 85% match
        if similarity > 0.85:
            similar_files.append(file_path.name)

    return similar_files

# ==============================================================================
# IIIF Metadata Extraction Functions (Phase 8 - v0.4.0)
# ==============================================================================

def detect_iiif_version(manifest):
    """
    Detect IIIF Presentation API version from @context field.

    Args:
        manifest: Parsed JSON manifest dict

    Returns:
        str: '2.0' or '3.0' (defaults to '2.0' if unclear)
    """
    context = manifest.get('@context', '')
    if isinstance(context, str):
        if 'presentation/3' in context:
            return '3.0'
        elif 'presentation/2' in context:
            return '2.0'
    elif isinstance(context, list):
        # Context can be an array in v3
        for ctx in context:
            if isinstance(ctx, str) and 'presentation/3' in ctx:
                return '3.0'

    return '2.0'  # Default to 2.0 (most common)

def extract_language_map_value(language_map, site_language='en'):
    """
    Extract value from IIIF v3.0 language map with fallback logic.

    Fallback order:
    1. Site's telar_language (e.g., 'es' for Spanish sites)
    2. English ('en')
    3. Unlabeled content ('none')
    4. First available language

    Args:
        language_map: Dict with language codes as keys, arrays as values
        site_language: Preferred language code

    Returns:
        str: Extracted value or empty string
    """
    if not isinstance(language_map, dict):
        return ''

    # Try site language
    if site_language in language_map:
        values = language_map[site_language]
        if isinstance(values, list) and len(values) > 0:
            return str(values[0])

    # Try English
    if 'en' in language_map:
        values = language_map['en']
        if isinstance(values, list) and len(values) > 0:
            return str(values[0])

    # Try unlabeled content
    if 'none' in language_map:
        values = language_map['none']
        if isinstance(values, list) and len(values) > 0:
            return str(values[0])

    # Use first available language
    for lang, values in language_map.items():
        if isinstance(values, list) and len(values) > 0:
            return str(values[0])

    return ''

def strip_html_tags(text):
    """
    Remove all HTML tags from text, preserve plain text only.
    Also decodes HTML entities and removes extra whitespace.

    Args:
        text: String that may contain HTML

    Returns:
        str: Plain text with HTML removed
    """
    import re
    import html

    if not text:
        return ''

    text = str(text)

    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Decode HTML entities
    text = html.unescape(text)

    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text

def clean_metadata_value(value):
    """
    Clean and normalize metadata value.
    Handles lists, strips HTML, and normalizes whitespace.

    Args:
        value: Metadata value (string, list, or dict)

    Returns:
        str: Cleaned value
    """
    if not value:
        return ''

    # Handle lists (multiple values)
    if isinstance(value, list):
        # Join multiple values with semicolon
        cleaned_values = []
        for v in value:
            cleaned = str(v).strip()
            if cleaned:
                cleaned_values.append(cleaned)
        value = '; '.join(cleaned_values)

    value = str(value).strip()
    value = strip_html_tags(value)

    return value

def find_metadata_field(metadata_array, search_terms, version='2.0', site_language='en'):
    """
    Search metadata array for matching field using fuzzy label matching.

    Args:
        metadata_array: List of {label, value} entries
        search_terms: List of possible label names (case-insensitive)
        version: '2.0' or '3.0'
        site_language: Preferred language for v3.0 extraction

    Returns:
        str: Extracted value or empty string
    """
    if not metadata_array or not isinstance(metadata_array, list):
        return ''

    for entry in metadata_array:
        if not isinstance(entry, dict):
            continue

        label = entry.get('label', '')

        # Handle v3.0 language maps
        if version == '3.0' and isinstance(label, dict):
            label = extract_language_map_value(label, site_language)

        # Case-insensitive search
        label_lower = str(label).lower().strip()

        for term in search_terms:
            if term.lower() in label_lower:
                value = entry.get('value', '')

                # Handle v3.0 language maps
                if version == '3.0' and isinstance(value, dict):
                    value = extract_language_map_value(value, site_language)

                return clean_metadata_value(value)

    return ''

def is_legal_boilerplate(text):
    """
    Detect if attribution text is generic legal boilerplate rather than actual credit.

    Args:
        text: Attribution text to check

    Returns:
        bool: True if text appears to be legal boilerplate
    """
    if not text:
        return False

    boilerplate_indicators = [
        'for information on use',
        'rights and permissions',
        'http://',
        'https://',
        'licensed under',
        'license',
        'see library',
        'please see',
        'for more information'
    ]

    text_lower = str(text).lower()

    # Check if text is mostly URL or starts with URL
    if text_lower.startswith('http'):
        return True

    # Check for multiple boilerplate indicators
    indicator_count = sum(1 for indicator in boilerplate_indicators if indicator in text_lower)

    # If text has 2+ indicators or is very long (>200 chars), likely boilerplate
    if indicator_count >= 2 or len(text) > 200:
        return True

    return False

def extract_credit(manifest, version='2.0', site_language='en'):
    """
    Extract credit/attribution with smart fallback logic.

    v2.0: Use 'attribution' field
    v3.0: Use 'requiredStatement.value' or 'provider.label'

    If attribution is legal boilerplate, fall back to repository/institution name.

    Args:
        manifest: Parsed JSON manifest dict
        version: '2.0' or '3.0'
        site_language: Preferred language

    Returns:
        str: Credit line
    """
    credit = ''

    if version == '2.0':
        credit = manifest.get('attribution', '')
    elif version == '3.0':
        # Try requiredStatement first
        req_stmt = manifest.get('requiredStatement', {})
        if req_stmt and isinstance(req_stmt, dict):
            value = req_stmt.get('value', {})
            if isinstance(value, dict):
                credit = extract_language_map_value(value, site_language)
            else:
                credit = str(value)

        # Try provider as fallback
        if not credit:
            providers = manifest.get('provider', [])
            if providers and isinstance(providers, list) and len(providers) > 0:
                provider = providers[0]
                if isinstance(provider, dict):
                    label = provider.get('label', {})
                    if isinstance(label, dict):
                        credit = extract_language_map_value(label, site_language)
                    else:
                        credit = str(label)

    credit = clean_metadata_value(credit)

    # Check if attribution is just legal boilerplate
    if credit and is_legal_boilerplate(credit):
        # Fall back to repository/institution from metadata
        fallback = find_metadata_field(
            manifest.get('metadata', []),
            ['Repository', 'Holding Institution', 'Institution'],
            version,
            site_language
        )
        if fallback:
            credit = fallback

    return credit

def extract_manifest_metadata(manifest_url, site_language='en'):
    """
    Extract all metadata fields from IIIF manifest.

    Extracts: title, description, creator, period, location, credit

    Args:
        manifest_url: URL of IIIF manifest
        site_language: Preferred language for extraction

    Returns:
        dict: Extracted metadata with keys: title, description, creator, period, location, credit
              Returns empty dict on error
    """
    try:
        # Fetch manifest (reuse existing request pattern)
        import urllib.request
        import json

        response = urllib.request.urlopen(manifest_url, timeout=10)
        manifest = json.loads(response.read())

        version = detect_iiif_version(manifest)
        metadata_array = manifest.get('metadata', [])

        extracted = {}

        # Title
        if version == '2.0':
            extracted['title'] = clean_metadata_value(manifest.get('label', ''))
        else:  # v3.0
            label = manifest.get('label', {})
            if isinstance(label, dict):
                extracted['title'] = clean_metadata_value(
                    extract_language_map_value(label, site_language)
                )
            else:
                extracted['title'] = clean_metadata_value(label)

        # Description
        if version == '2.0':
            desc = manifest.get('description', '')
            extracted['description'] = strip_html_tags(desc)
        else:  # v3.0
            summary = manifest.get('summary', {})
            if isinstance(summary, dict):
                extracted['description'] = strip_html_tags(
                    extract_language_map_value(summary, site_language)
                )
            else:
                extracted['description'] = strip_html_tags(summary)

        # Creator
        extracted['creator'] = find_metadata_field(
            metadata_array,
            ['Creator', 'Artist', 'Author', 'Maker', 'Cartographer', 'Contributor', 'Painter', 'Sculptor'],
            version,
            site_language
        )

        # Period
        extracted['period'] = find_metadata_field(
            metadata_array,
            ['Date', 'Period', 'Creation Date', 'Created', 'Date Created', 'Date Note', 'Temporal'],
            version,
            site_language
        )

        # Location (Repository/Institution name, not geographic location)
        extracted['location'] = find_metadata_field(
            metadata_array,
            ['Repository', 'Holding Institution', 'Institution', 'Current Location'],
            version,
            site_language
        )

        # If location not found in metadata, try provider (v3.0)
        if not extracted['location'] and version == '3.0':
            providers = manifest.get('provider', [])
            if providers and isinstance(providers, list) and len(providers) > 0:
                provider = providers[0]
                if isinstance(provider, dict):
                    label = provider.get('label', {})
                    if isinstance(label, dict):
                        extracted['location'] = extract_language_map_value(label, site_language)
                    else:
                        extracted['location'] = str(label).strip()

        # Credit
        extracted['credit'] = extract_credit(manifest, version, site_language)

        return extracted

    except Exception as e:
        # Silently fail - return empty dict
        # Errors will be caught and logged by calling function
        return {}

def apply_metadata_fallback(row_dict, iiif_metadata):
    """
    Apply fallback hierarchy: CSV > IIIF > empty.

    Modifies row_dict in place, adding IIIF values only for empty CSV fields.

    Args:
        row_dict: Dictionary of object data from CSV
        iiif_metadata: Dictionary of extracted IIIF metadata
    """
    fields = ['title', 'description', 'creator', 'period', 'location', 'credit']

    for field in fields:
        csv_value = str(row_dict.get(field, '')).strip()
        iiif_value = str(iiif_metadata.get(field, '')).strip()

        # CSV override: if user entered value, keep it
        if csv_value:
            continue

        # Auto-populate: if CSV empty but IIIF has value, use IIIF
        if iiif_value:
            row_dict[field] = iiif_value

def load_site_language():
    """
    Load telar_language setting from _config.yml.

    Returns:
        str: Language code (default: 'en')
    """
    try:
        config_path = Path('_config.yml')
        if not config_path.exists():
            return 'en'

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        return config.get('telar_language', 'en')
    except Exception:
        return 'en'

def inject_christmas_tree_errors(df):
    """
    Inject test objects with various error conditions for testing multilingual warnings.
    All test objects have 🎄 emoji in their titles for easy identification.

    This "Christmas Tree Mode" lights up all possible warning messages.
    """
    test_objects = [
        {
            'object_id': 'test-iiif-404',
            'title': '🎄 Test - IIIF 404 Error',
            'description': 'Test object to trigger IIIF 404 error warning',
            'iiif_manifest': 'https://example.com/nonexistent/manifest.json',
            'creator': 'Test',
            'period': 'Test',
            'medium': '',
            'dimensions': '',
            'location': '',
            'credit': '',
            'thumbnail': ''
        },
        {
            'object_id': 'test-iiif-503',
            'title': '🎄 Test - IIIF 503 Service Unavailable',
            'description': 'Test object to trigger IIIF 503 error warning',
            'iiif_manifest': 'https://httpstat.us/503',
            'creator': 'Test',
            'period': 'Test',
            'medium': '',
            'dimensions': '',
            'location': '',
            'credit': '',
            'thumbnail': ''
        },
        {
            'object_id': 'test-iiif-invalid',
            'title': '🎄 Test - Invalid IIIF URL',
            'description': 'Test object to trigger invalid URL warning',
            'iiif_manifest': 'not-a-valid-url',
            'creator': 'Test',
            'period': 'Test',
            'medium': '',
            'dimensions': '',
            'location': '',
            'credit': '',
            'thumbnail': ''
        },
        {
            'object_id': 'test-image-missing',
            'title': '🎄 Test - Missing Image Source',
            'description': 'Test object with no IIIF manifest and no local image file',
            'iiif_manifest': '',
            'creator': 'Test',
            'period': 'Test',
            'medium': '',
            'dimensions': '',
            'location': '',
            'credit': '',
            'thumbnail': ''
        },
        {
            'object_id': 'test-iiif-500',
            'title': '🎄 Test - IIIF 500 Internal Server Error',
            'description': 'Test object to trigger IIIF 500 error warning',
            'iiif_manifest': 'https://httpstat.us/500',
            'creator': 'Test',
            'period': 'Test',
            'medium': '',
            'dimensions': '',
            'location': '',
            'credit': '',
            'thumbnail': ''
        },
        {
            'object_id': 'test-iiif-429',
            'title': '🎄 Test - IIIF 429 Rate Limiting',
            'description': 'Test object to trigger IIIF 429 rate limiting warning',
            'iiif_manifest': 'https://httpstat.us/429',
            'creator': 'Test',
            'period': 'Test',
            'medium': '',
            'dimensions': '',
            'location': '',
            'credit': '',
            'thumbnail': ''
        }
    ]

    # Create dataframe from test objects and concatenate with existing data
    test_df = pd.DataFrame(test_objects)
    df = pd.concat([df, test_df], ignore_index=True)

    print("🎄 Christmas Tree Mode activated - injected test objects with various errors")

    return df

def process_objects(df, christmas_tree=False):
    """
    Process objects CSV
    Expected columns: object_id, title, creator, date, description, etc.
    """
    # Tracking for summary
    warnings = []

    # Drop example column if it exists
    if 'example' in df.columns:
        df = df.drop(columns=['example'])

    # Clean up NaN values
    df = df.fillna('')

    # Remove rows where object_id is empty
    df = df[df['object_id'].astype(str).str.strip() != '']

    # Normalize source_url and iiif_manifest columns for backward compatibility
    # Ensure both columns exist in the DataFrame so templates can use either during transition
    if 'source_url' not in df.columns and 'iiif_manifest' in df.columns:
        # Old format: only iiif_manifest exists - create source_url as alias
        df['source_url'] = df['iiif_manifest']
    elif 'iiif_manifest' not in df.columns and 'source_url' in df.columns:
        # New format: only source_url exists - create iiif_manifest as alias for backward compat
        df['iiif_manifest'] = df['source_url']
    elif 'source_url' not in df.columns and 'iiif_manifest' not in df.columns:
        # Neither exists - create both as empty columns
        df['source_url'] = ''
        df['iiif_manifest'] = ''
    # If both exist, keep both (user is mid-transition)

    # Inject Christmas Tree test errors if flag is enabled
    if christmas_tree:
        df = inject_christmas_tree_errors(df)

    # Validate and clean object_id values
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff', '.bmp', '.svg']
    for idx, row in df.iterrows():
        object_id = str(row.get('object_id', '')).strip()
        original_id = object_id
        modified = False

        # Check for file extensions and strip them
        for ext in valid_extensions:
            if object_id.lower().endswith(ext):
                object_id = object_id[:-len(ext)]
                modified = True
                print(f"  [INFO] Stripped file extension from object_id: '{original_id}' → '{object_id}'")
                break

        # Check for spaces in object_id
        if ' ' in object_id:
            msg = f"Object ID '{object_id}' contains spaces - this may cause issues with file paths"
            print(f"  [WARN] {msg}")
            warnings.append(msg)

        # Update the dataframe if modified
        if modified:
            df.at[idx, 'object_id'] = object_id

    # Add object_warning column for IIIF/image validation
    if 'object_warning' not in df.columns:
        df['object_warning'] = ''

    # Validate thumbnail field
    if 'thumbnail' in df.columns:
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.tif', '.tiff']
        placeholder_values = ['n/a', 'null', 'none', 'placeholder', 'na', 'thumbnail']

        for idx, row in df.iterrows():
            thumbnail = str(row.get('thumbnail', '')).strip()
            object_id = row.get('object_id', 'unknown')

            # Skip if already empty
            if not thumbnail:
                continue

            # Check for placeholder values
            if thumbnail.lower() in placeholder_values:
                df.at[idx, 'thumbnail'] = ''
                msg = f"Cleared invalid thumbnail placeholder '{thumbnail}' for object {object_id}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
                continue

            # Check for valid image extension
            has_valid_extension = any(thumbnail.lower().endswith(ext) for ext in valid_extensions)

            if not has_valid_extension:
                df.at[idx, 'thumbnail'] = ''
                msg = f"Cleared invalid thumbnail '{thumbnail}' for object {object_id} (not an image file)"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
                continue

            # Normalize path to avoid duplicate slashes
            # Accept both /path and path, ensure single leading slash if present
            if thumbnail.startswith('/'):
                # Remove duplicate slashes
                normalized = '/' + '/'.join(filter(None, thumbnail.split('/')))
                if normalized != thumbnail:
                    df.at[idx, 'thumbnail'] = normalized
                    thumbnail = normalized
                    print(f"  [INFO] Normalized thumbnail path for object {object_id}: {normalized}")

            # Check if file exists (remove leading slash for filesystem check)
            file_path = thumbnail.lstrip('/')
            if not Path(file_path).exists():
                msg = f"Thumbnail file not found for object {object_id}: {thumbnail}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
                # Don't clear - file might be added later or exist in different environment

    # Load previous objects.json to skip 429 errors for unchanged manifests
    previous_objects = {}
    previous_objects_path = Path('_data/objects.json')
    if previous_objects_path.exists():
        try:
            with open(previous_objects_path, 'r', encoding='utf-8') as f:
                previous_data = json.load(f)
                # Create lookup: object_id -> {manifest_url, had_warning}
                for obj in previous_data:
                    previous_objects[obj.get('object_id')] = {
                        'manifest_url': obj.get('iiif_manifest', ''),
                        'had_warning': bool(obj.get('object_warning'))
                    }
                print(f"[INFO] Loaded {len(previous_objects)} objects from previous build for 429 checking")
        except Exception as e:
            print(f"[INFO] Could not load previous objects.json: {e}")
            previous_objects = {}

    # Validate source URL field (checks both source_url and iiif_manifest for backward compatibility)
    if 'source_url' in df.columns or 'iiif_manifest' in df.columns:
        for idx, row in df.iterrows():
            manifest_url = get_source_url(row)
            object_id = row.get('object_id', 'unknown')

            # Skip if empty
            if not manifest_url:
                continue

            # Check if it's a valid URL
            parsed = urlparse(manifest_url)
            if not parsed.scheme in ['http', 'https']:
                # Clear both columns (whichever exists)
                if 'source_url' in df.columns:
                    df.at[idx, 'source_url'] = ''
                if 'iiif_manifest' in df.columns:
                    df.at[idx, 'iiif_manifest'] = ''
                df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_invalid_url')
                msg = f"Cleared invalid source URL for object {object_id}: not a valid URL"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
                continue

            # Try to fetch the manifest (with timeout)
            # Create SSL context that doesn't verify certificates (avoid false positives)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            try:
                # Fetch manifest directly with GET (follows redirects automatically)
                req = urllib.request.Request(manifest_url)
                req.add_header('User-Agent', 'Telar/0.4.0-beta (IIIF validator)')

                with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
                    content_type = response.headers.get('Content-Type', '')

                    # Check if response is JSON
                    if 'json' not in content_type.lower():
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_not_manifest')
                        msg = f"IIIF manifest for object {object_id} does not return JSON (Content-Type: {content_type})"
                        print(f"  [WARN] {msg}")
                        warnings.append(msg)
                        # Don't clear manifest URL - might still work despite wrong content type
                        continue

                    try:
                        data = json.loads(response.read().decode('utf-8'))

                        # Check for basic IIIF structure
                        has_context = '@context' in data
                        has_type = 'type' in data or '@type' in data

                        if not (has_context or has_type):
                            df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_malformed')
                            msg = f"IIIF manifest for object {object_id} missing required fields (@context or type)"
                            print(f"  [WARN] {msg}")
                            warnings.append(msg)
                        else:
                            print(f"  [INFO] Validated IIIF manifest for object {object_id}")

                            # PHASE 8: Extract metadata from validated manifest
                            try:
                                site_language = load_site_language()
                                version = detect_iiif_version(data)
                                metadata_array = data.get('metadata', [])

                                extracted = {}

                                # Title
                                if version == '2.0':
                                    extracted['title'] = clean_metadata_value(data.get('label', ''))
                                else:  # v3.0
                                    label = data.get('label', {})
                                    if isinstance(label, dict):
                                        extracted['title'] = clean_metadata_value(
                                            extract_language_map_value(label, site_language)
                                        )
                                    else:
                                        extracted['title'] = clean_metadata_value(label)

                                # Description
                                if version == '2.0':
                                    desc = data.get('description', '')
                                    extracted['description'] = strip_html_tags(desc)
                                else:  # v3.0
                                    summary = data.get('summary', {})
                                    if isinstance(summary, dict):
                                        extracted['description'] = strip_html_tags(
                                            extract_language_map_value(summary, site_language)
                                        )
                                    else:
                                        extracted['description'] = strip_html_tags(summary)

                                # Creator
                                extracted['creator'] = find_metadata_field(
                                    metadata_array,
                                    ['Creator', 'Artist', 'Author', 'Maker', 'Cartographer', 'Contributor', 'Painter', 'Sculptor'],
                                    version,
                                    site_language
                                )

                                # Period
                                extracted['period'] = find_metadata_field(
                                    metadata_array,
                                    ['Date', 'Period', 'Creation Date', 'Created', 'Date Created', 'Date Note', 'Temporal'],
                                    version,
                                    site_language
                                )

                                # Location (Repository/Institution name, not geographic location)
                                extracted['location'] = find_metadata_field(
                                    metadata_array,
                                    ['Repository', 'Holding Institution', 'Institution', 'Current Location'],
                                    version,
                                    site_language
                                )

                                # If location not found in metadata, try provider (v3.0)
                                if not extracted['location'] and version == '3.0':
                                    providers = data.get('provider', [])
                                    if providers and isinstance(providers, list) and len(providers) > 0:
                                        provider = providers[0]
                                        if isinstance(provider, dict):
                                            provider_label = provider.get('label', {})
                                            if isinstance(provider_label, dict):
                                                extracted['location'] = extract_language_map_value(provider_label, site_language)
                                            else:
                                                extracted['location'] = str(provider_label).strip()

                                # Credit
                                extracted['credit'] = extract_credit(data, version, site_language)

                                # Apply fallback hierarchy (CSV > IIIF > empty)
                                row_dict = row.to_dict()
                                apply_metadata_fallback(row_dict, extracted)

                                # Update dataframe with extracted values
                                for field in ['title', 'description', 'creator', 'period', 'location', 'credit']:
                                    df.at[idx, field] = row_dict[field]

                                # Log if any fields were auto-populated
                                populated_fields = []
                                for field in ['title', 'description', 'creator', 'period', 'location', 'credit']:
                                    csv_val = str(row.get(field, '')).strip()
                                    final_val = str(row_dict.get(field, '')).strip()
                                    if not csv_val and final_val:
                                        populated_fields.append(field)

                                if populated_fields:
                                    print(f"  [INFO] Auto-populated from IIIF: {', '.join(populated_fields)}")

                            except Exception as e:
                                # Metadata extraction failed - log but don't block validation
                                print(f"  [WARN] Could not extract metadata from IIIF manifest for {object_id}: {e}")

                    except json.JSONDecodeError:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_not_manifest')
                        msg = f"IIIF manifest for object {object_id} is not valid JSON"
                        print(f"  [WARN] {msg}")
                        warnings.append(msg)

            except urllib.error.HTTPError as e:
                # Check if we should skip this 429 error (unchanged manifest from previous build)
                skip_429 = False
                if e.code == 429 and object_id in previous_objects:
                    prev = previous_objects[object_id]
                    # Skip if: same URL as before AND no warning in previous build
                    if prev['manifest_url'] == manifest_url and not prev['had_warning']:
                        skip_429 = True
                        print(f"  [INFO] Skipping 429 error for unchanged manifest: {object_id} ({manifest_url})")

                # Only process error if not skipping
                if not skip_429:
                    if e.code == 404:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_404')
                        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_404')
                    elif e.code == 429:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_429')
                        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_429')
                    elif e.code == 403:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_403')
                        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_403')
                    elif e.code == 401:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_401')
                        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_401')
                    elif e.code == 500:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_500')
                        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_500')
                    elif e.code == 503:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_503')
                        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_503')
                    elif e.code == 502:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_502')
                        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_502')
                    else:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_error_generic', code=e.code)
                        df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_error_generic', code=e.code)
                    msg = f"IIIF manifest for object {object_id} returned HTTP {e.code}: {manifest_url}"
                    print(f"  [WARN] {msg}")
                    warnings.append(msg)
            except urllib.error.URLError as e:
                df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_unreachable')
                df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_network_error')
                msg = f"IIIF manifest for object {object_id} could not be reached: {e.reason}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
            except Exception as e:
                df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_validation_failed')
                df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_validation_error')
                msg = f"Error validating IIIF manifest for object {object_id}: {str(e)}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)

    # Validate that objects have either source URL (IIIF manifest) OR local image file
    for idx, row in df.iterrows():
        object_id = row.get('object_id', 'unknown')
        source_url = get_source_url(row)

        # Skip if already has a valid source URL
        if source_url:
            continue

        # No external IIIF manifest - check for local image file
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff']
        has_local_image = False

        for ext in valid_extensions:
            local_image_path = Path(f'components/images/{object_id}{ext}')
            if local_image_path.exists():
                has_local_image = True
                print(f"  [INFO] Object {object_id} uses local image: {local_image_path}")
                break

        # Warn if object has neither external manifest nor local image
        if not has_local_image:
            # Check for similar filenames (near-matches)
            similar_files = _find_similar_image_filenames(object_id, Path('components/images'))

            if similar_files:
                # Found near-matches - provide helpful suggestion
                if len(similar_files) == 1:
                    similar_file = similar_files[0]
                    file_ext = Path(similar_file).suffix
                    error_msg = get_lang_string('errors.object_warnings.image_similar_single',
                                                 object_id=object_id,
                                                 similar_file=similar_file,
                                                 file_ext=file_ext)
                    df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_filename_mismatch')
                else:
                    file_list = "', '".join(similar_files)
                    error_msg = get_lang_string('errors.object_warnings.image_similar_multiple',
                                                 object_id=object_id,
                                                 file_list=file_list)
                    df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_ambiguous_match')
            else:
                # No similar files found - provide basic error message
                error_msg = get_lang_string('errors.object_warnings.image_missing', object_id=object_id)
                df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_missing_source')

            df.at[idx, 'object_warning'] = error_msg
            msg = f"Object {object_id} has no IIIF manifest or local image file"
            print(f"  [WARN] {msg}")
            warnings.append(msg)

    # Print summary if there were issues
    if warnings:
        print(f"\n  Objects validation summary: {len(warnings)} warning(s)")

    return df

def process_story(df, christmas_tree=False):
    """
    Process story CSV with file references
    Expected columns: step, question, answer, object, x, y, zoom, layer1_file, layer2_file, etc.
    """
    # Tracking for summary
    warnings = []

    # Load glossary terms for auto-linking
    glossary_terms = load_glossary_terms()
    glossary_warnings = []

    # Initialize widget warnings list
    widget_warnings = []

    # Drop example column if it exists
    if 'example' in df.columns:
        df = df.drop(columns=['example'])

    # Clean up NaN values
    df = df.fillna('')

    # Remove completely empty rows
    df = df[df.astype(str).apply(lambda x: x.str.strip()).ne('').any(axis=1)]

    # Load objects data for validation
    objects_data = {}
    objects_json_path = Path('_data/objects.json')
    if objects_json_path.exists():
        try:
            with open(objects_json_path, 'r', encoding='utf-8') as f:
                objects_list = json.load(f)
                # Create lookup dictionary by object_id
                objects_data = {obj['object_id']: obj for obj in objects_list}
        except Exception as e:
            print(f"  [WARN] Could not load objects.json for validation: {e}")

    # Add viewer_warning column if it doesn't exist
    if 'viewer_warning' not in df.columns:
        df['viewer_warning'] = ''

    # Validate object references
    if 'object' in df.columns and objects_data:
        for idx, row in df.iterrows():
            object_id = str(row.get('object', '')).strip()
            step_num = row.get('step', 'unknown')

            # Skip if no object specified
            if not object_id:
                continue

            # Check if object exists
            if object_id not in objects_data:
                error_msg = get_lang_string('errors.object_warnings.object_not_found', object_id=object_id)
                df.at[idx, 'viewer_warning'] = error_msg
                msg = f"Story step {step_num} references missing object: {object_id}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
                continue

            # Check if object has IIIF manifest or local image
            obj = objects_data[object_id]
            iiif_manifest = obj.get('iiif_manifest', '').strip()

            # If no external IIIF manifest, check for local image file
            if not iiif_manifest:
                # Check for local image in components/images/
                valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff']
                has_local_image = False

                for ext in valid_extensions:
                    local_image_path = Path(f'components/images/{object_id}{ext}')
                    if local_image_path.exists():
                        has_local_image = True
                        print(f"  [INFO] Object {object_id} uses local image: {local_image_path}")
                        break

                # Only warn if object has neither external manifest nor local image
                if not has_local_image:
                    error_msg = get_lang_string('errors.object_warnings.object_no_source', object_id=object_id)
                    df.at[idx, 'viewer_warning'] = error_msg
                    msg = f"Story step {step_num} references object without IIIF source: {object_id}"
                    print(f"  [WARN] {msg}")
                    warnings.append(msg)

    # Process file reference columns
    for col in df.columns:
        if col.endswith('_file'):
            # Determine the base name (e.g., 'layer1' from 'layer1_file')
            base_name = col.replace('_file', '')

            # Create new columns for title and text
            title_col = f'{base_name}_title'
            text_col = f'{base_name}_text'

            # Initialize new columns with empty strings
            if title_col not in df.columns:
                df[title_col] = ''
            if text_col not in df.columns:
                df[text_col] = ''

            # Read markdown files and populate columns
            for idx, row in df.iterrows():
                file_ref = row[col]
                if file_ref and file_ref.strip():
                    # Prepend 'stories/' to the path for story files
                    file_path = f"stories/{file_ref.strip()}"
                    markdown_data = read_markdown_file(file_path, widget_warnings)
                    if markdown_data:
                        step_num = row.get('step', 'unknown')
                        df.at[idx, title_col] = markdown_data['title']
                        # Apply glossary link transformation to content
                        content_with_glossary = process_glossary_links(
                            markdown_data['content'],
                            glossary_terms,
                            glossary_warnings,
                            step_num,
                            base_name
                        )
                        df.at[idx, text_col] = content_with_glossary
                    else:
                        # Insert error message for missing file
                        step_num = row.get('step', 'unknown')
                        df.at[idx, title_col] = get_lang_string('errors.object_warnings.content_missing_label')
                        error_html = f'''<div class="alert alert-warning" role="alert">
    <strong>{get_lang_string('errors.object_warnings.content_file_missing', file_ref=file_ref.strip())}</strong>
</div>'''
                        df.at[idx, text_col] = error_html
                        msg = f"Missing markdown file for story step {step_num}, {base_name}: {file_ref.strip()}"
                        print(f"  [WARN] {msg}")
                        warnings.append(msg)

            # Drop the _file column as it's no longer needed in JSON
            df = df.drop(columns=[col])

    # Set default coordinates for empty values
    coordinate_columns = ['x', 'y', 'zoom']
    for col in coordinate_columns:
        if col in df.columns:
            # Convert to string first to handle NaN values
            df[col] = df[col].astype(str)
            # Set defaults for empty or 'nan' values
            if col == 'x':
                df.loc[df[col].isin(['', 'nan']), col] = '0.5'
            elif col == 'y':
                df.loc[df[col].isin(['', 'nan']), col] = '0.5'
            elif col == 'zoom':
                df.loc[df[col].isin(['', 'nan']), col] = '1'

    # Collect all warnings for intro display
    all_warnings = []
    for idx, row in df.iterrows():
        step_num = row.get('step', 'unknown')

        # Check for viewer warnings (missing object/IIIF)
        viewer_warning = row.get('viewer_warning', '').strip()
        if viewer_warning:
            all_warnings.append({
                'step': step_num,
                'type': 'viewer',
                'message': viewer_warning
            })

        # Check for panel content warnings (missing markdown files)
        # Look for "Content Missing" title which indicates missing files
        content_missing_label = get_lang_string('errors.object_warnings.content_missing_label')
        for layer in ['layer1', 'layer2']:
            title_col = f'{layer}_title'
            if title_col in row and row[title_col] == content_missing_label:
                # Extract the filename from the error HTML in the text column
                text_col = f'{layer}_text'
                text = row.get(text_col, '')
                # Extract filename from the HTML (it's between <strong> tags)
                import re
                filename_match = re.search(r'<strong>(.*?)</strong>', text)
                # Get layer number for display (1 or 2)
                layer_num = layer[-1]  # Get '1' or '2' from 'layer1' or 'layer2'
                if filename_match:
                    # Extract content_file_missing message from HTML
                    message = filename_match.group(1)
                    all_warnings.append({
                        'step': step_num,
                        'type': 'panel',
                        'message': message
                    })
                else:
                    # Fallback if regex fails
                    all_warnings.append({
                        'step': step_num,
                        'type': 'panel',
                        'message': get_lang_string('errors.object_warnings.layer_file_missing', layer_num=layer_num)
                    })

    # Add glossary link warnings
    all_warnings.extend(glossary_warnings)

    # Add widget warnings
    all_warnings.extend(widget_warnings)

    # Store warnings in dataframe as metadata (will be added to JSON)
    df.attrs['viewer_warnings'] = all_warnings

    # Christmas Tree Mode: Inject fake warnings for testing
    if christmas_tree:
        # Inject test warnings for various error types
        fake_warnings = [
            {
                'step': 1,
                'type': 'viewer',
                'message': get_lang_string('errors.object_warnings.missing_object_id')
            },
            {
                'step': 2,
                'type': 'panel',
                'message': get_lang_string('errors.object_warnings.content_file_missing', file_ref='missing-file.md')
            },
            {
                'step': 3,
                'type': 'glossary',
                'term_id': 'nonexistent-term',
                'message': get_lang_string('errors.object_warnings.glossary_term_not_found', term_id='nonexistent-term')
            }
        ]
        # Add fake warnings to existing warnings
        df.attrs['viewer_warnings'] = all_warnings + fake_warnings
        print("🎄 Christmas Tree Mode: Injected test warnings into story")

    # Print summary if there were issues
    if warnings:
        print(f"\n  Story validation summary: {len(warnings)} warning(s)")

    return df

def load_demo_bundle():
    """
    Load demo content bundle if it exists.

    Returns:
        dict: Demo bundle data, or None if not present
    """
    bundle_path = Path('_demo_content/telar-demo-bundle.json')

    if not bundle_path.exists():
        return None

    try:
        with open(bundle_path, 'r', encoding='utf-8') as f:
            bundle = json.load(f)

        meta = bundle.get('_meta', {})
        print(f"[INFO] Loaded demo bundle v{meta.get('telar_version', 'unknown')} ({meta.get('language', 'unknown')})")
        return bundle

    except Exception as e:
        print(f"[WARN] Could not load demo bundle: {e}")
        return None


def merge_demo_content(bundle):
    """
    Merge demo bundle content with user content.

    Merges:
    - Demo projects into _data/project.json
    - Demo objects into _data/objects.json
    - Demo stories as additional story files
    - Demo glossary files (written to components/texts/glossary/_demo_*.md)

    Args:
        bundle: Demo bundle dict
    """
    data_dir = Path('_data')

    # Merge projects
    project_path = data_dir / 'project.json'
    if project_path.exists() and bundle.get('project'):
        try:
            with open(project_path, 'r', encoding='utf-8') as f:
                user_project = json.load(f)

            # Convert demo project format to match user format
            # Use order for number field, story_id for identifier (v0.6.0+)
            demo_stories = []
            for proj in bundle['project']:
                demo_stories.append({
                    'number': str(proj.get('order', '')),
                    'story_id': proj.get('story_id', ''),
                    'title': proj.get('title', ''),
                    'subtitle': proj.get('subtitle', ''),
                    'byline': proj.get('byline', ''),
                    '_demo': True  # Mark as demo content
                })

            # Merge: demo stories first, then user stories
            if 'stories' in user_project[0]:
                user_project[0]['stories'] = demo_stories + user_project[0]['stories']
            else:
                user_project[0]['stories'] = demo_stories

            with open(project_path, 'w', encoding='utf-8') as f:
                json.dump(user_project, f, indent=2, ensure_ascii=False)

            print(f"  Merged {len(demo_stories)} demo project(s) into project.json")

        except Exception as e:
            print(f"  [WARN] Could not merge demo projects: {e}")

    # Merge objects
    objects_path = data_dir / 'objects.json'
    if objects_path.exists() and bundle.get('objects'):
        try:
            with open(objects_path, 'r', encoding='utf-8') as f:
                user_objects = json.load(f)

            # Get existing object IDs to avoid duplicates
            existing_ids = {obj.get('object_id') for obj in user_objects if not obj.get('_metadata')}

            # Convert demo objects format and add new ones
            demo_count = 0
            for obj_id, obj_data in bundle['objects'].items():
                if obj_id not in existing_ids:
                    demo_obj = {
                        'object_id': obj_id,
                        'title': obj_data.get('title', ''),
                        'description': obj_data.get('description', ''),
                        'source_url': obj_data.get('source_url', ''),
                        'iiif_manifest': obj_data.get('source_url', ''),  # Backward compat
                        'creator': obj_data.get('creator', ''),
                        'period': obj_data.get('period', ''),
                        'medium': obj_data.get('medium', ''),
                        'dimensions': obj_data.get('dimensions', ''),
                        'location': obj_data.get('location', ''),
                        'credit': obj_data.get('credit', ''),
                        'thumbnail': obj_data.get('thumbnail', ''),
                        '_demo': True
                    }
                    user_objects.append(demo_obj)
                    demo_count += 1

            with open(objects_path, 'w', encoding='utf-8') as f:
                json.dump(user_objects, f, indent=2, ensure_ascii=False)

            print(f"  Merged {demo_count} demo object(s) into objects.json")

        except Exception as e:
            print(f"  [WARN] Could not merge demo objects: {e}")

    # Create demo story files
    if bundle.get('stories'):
        for story_id, story_data in bundle['stories'].items():
            try:
                story_path = data_dir / f'{story_id}.json'

                # Convert demo story format to match user format
                steps = []
                for step in story_data.get('steps', []):
                    step_data = {
                        'step': step.get('step'),
                        'object': step.get('object', ''),
                        'x': str(step.get('x', '0.5')),
                        'y': str(step.get('y', '0.5')),
                        'zoom': str(step.get('zoom', '1')),
                        'question': step.get('question', ''),
                        'answer': step.get('answer', ''),
                        '_demo': True
                    }

                    # Build glossary terms dict from bundle for link processing
                    glossary_terms = {}
                    if bundle.get('glossary'):
                        for term_id, term_data in bundle['glossary'].items():
                            glossary_terms[term_id] = term_data.get('term', term_id)

                    # Process layers
                    layers = step.get('layers', {})
                    for layer_key in ['layer1', 'layer2']:
                        layer = layers.get(layer_key, {})
                        if layer:
                            step_data[f'{layer_key}_button'] = layer.get('button', '')
                            # Use explicit title if provided, fall back to button text
                            step_data[f'{layer_key}_title'] = layer.get('title', layer.get('button', ''))

                            content = layer.get('content', '')
                            if content:
                                # Initialize warnings list for widget processing
                                widget_warnings = []

                                # Process widgets BEFORE markdown conversion
                                content = process_widgets(content, f'demo-{story_id}', widget_warnings)

                                # Process images (sizes and captions) BEFORE markdown conversion
                                content = process_images(content)

                                # Convert markdown to HTML
                                content = markdown.markdown(content, extensions=['extra', 'nl2br'])

                                # Process glossary links AFTER markdown conversion
                                content = process_glossary_links(content, glossary_terms)

                            step_data[f'{layer_key}_text'] = content
                            step_data[f'{layer_key}_demo'] = True  # All demo bundle layers are demo content

                    steps.append(step_data)

                with open(story_path, 'w', encoding='utf-8') as f:
                    json.dump(steps, f, indent=2, ensure_ascii=False)

                print(f"  Created demo story: {story_id}.json ({len(steps)} steps)")

            except Exception as e:
                print(f"  [WARN] Could not create demo story {story_id}: {e}")

    # Write demo glossary to _data/demo-glossary.json
    # (generate_collections.py will read this and create Jekyll collection files)
    if bundle.get('glossary'):
        glossary_data = []
        for term_id, term_data in bundle['glossary'].items():
            glossary_data.append({
                'term_id': term_id,
                'title': term_data.get('term', term_id),
                'content': term_data.get('content', ''),
                '_demo': True
            })

        glossary_json_path = Path('_data/demo-glossary.json')
        with open(glossary_json_path, 'w', encoding='utf-8') as f:
            json.dump(glossary_data, f, indent=2, ensure_ascii=False)

        print(f"  Created _data/demo-glossary.json ({len(glossary_data)} demo terms)")


def find_csv_with_fallback(base_path, spanish_name):
    """
    Find CSV file with bilingual fallback support.
    Checks for English name first, then Spanish equivalent.

    Args:
        base_path: Base path like 'components/structures/project'
        spanish_name: Spanish filename like 'proyecto'

    Returns:
        str: Path to found CSV file, or original English path if neither exists

    Example:
        find_csv_with_fallback('components/structures/project', 'proyecto')
        Returns: 'components/structures/project.csv' or
                 'components/structures/proyecto.csv' (fallback)
    """
    english_path = f'{base_path}.csv'
    spanish_path = f'{base_path.rsplit("/", 1)[0]}/{spanish_name}.csv'

    if Path(english_path).exists():
        return english_path
    elif Path(spanish_path).exists():
        print(f"  [INFO] Using Spanish file: {spanish_name}.csv")
        return spanish_path
    else:
        # Return English path (will trigger "file not found" warning in csv_to_json)
        return english_path

def main():
    """Main conversion process"""
    # Check if Christmas Tree Mode is enabled in _config.yml
    christmas_tree_mode = False
    try:
        config_path = Path('_config.yml')
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                testing_features = config.get('testing-features', {})
                christmas_tree_mode = testing_features.get('christmas_tree_mode', False)

                if christmas_tree_mode:
                    print("🎄 Christmas Tree Mode enabled - injecting test objects with errors")
                else:
                    # Clean up test object files when Christmas Tree Mode is disabled
                    objects_dir = Path('_jekyll-files/_objects')
                    if objects_dir.exists():
                        test_files = list(objects_dir.glob('test-*.md'))
                        if test_files:
                            print("  [INFO] Cleaning up test object files from previous Christmas Tree Mode session")
                            for test_file in test_files:
                                test_file.unlink()
                                print(f"  [INFO] Removed {test_file.name}")
    except Exception as e:
        print(f"  [WARN] Could not read Christmas Tree Mode setting: {e}")

    data_dir = Path('_data')
    data_dir.mkdir(exist_ok=True)

    structures_dir = Path('components/structures')

    print("Converting CSV files to JSON...")
    print("-" * 50)

    # Convert project setup (with bilingual fallback: project.csv or proyecto.csv)
    project_path = find_csv_with_fallback('components/structures/project', 'proyecto')
    csv_to_json(
        project_path,
        '_data/project.json',
        process_project_setup
    )

    # Convert objects (with bilingual fallback: objects.csv or objetos.csv)
    objects_path = find_csv_with_fallback('components/structures/objects', 'objetos')
    if christmas_tree_mode:
        csv_to_json(
            objects_path,
            '_data/objects.json',
            lambda df: process_objects(df, christmas_tree=True)
        )
    else:
        csv_to_json(
            objects_path,
            '_data/objects.json',
            process_objects
        )

    # Note: Glossary is now sourced directly from components/texts/glossary/
    # and processed by generate_collections.py

    # Convert story files (with optional Christmas Tree mode)
    # v0.6.0+: Process ALL CSVs except system files (supports both semantic and traditional naming)
    # System files: project.csv/proyecto.csv, objects.csv/objetos.csv
    # Story files: your-story.csv, tu-historia.csv, story-1.csv, story-2.csv, etc.
    system_csvs = {'project.csv', 'proyecto.csv', 'objects.csv', 'objetos.csv'}

    if christmas_tree_mode:
        for csv_file in structures_dir.glob('*.csv'):
            if csv_file.name not in system_csvs:
                json_filename = csv_file.stem + '.json'
                json_file = data_dir / json_filename
                csv_to_json(
                    str(csv_file),
                    str(json_file),
                    lambda df: process_story(df, christmas_tree=True)
                )
    else:
        for csv_file in structures_dir.glob('*.csv'):
            if csv_file.name not in system_csvs:
                json_filename = csv_file.stem + '.json'
                json_file = data_dir / json_filename
                csv_to_json(
                    str(csv_file),
                    str(json_file),
                    process_story
                )

    # Merge demo content if available
    print("-" * 50)
    demo_bundle = load_demo_bundle()
    if demo_bundle:
        print("Merging demo content...")
        merge_demo_content(demo_bundle)

    print("-" * 50)
    print("Conversion complete!")

if __name__ == '__main__':
    main()
