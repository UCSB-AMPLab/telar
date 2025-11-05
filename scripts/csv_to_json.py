#!/usr/bin/env python3
"""
Convert CSV files from Google Sheets to JSON for Jekyll
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

# Global language data cache
_lang_data = None

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

def process_image_sizes(text):
    """
    Replace ![alt](path){size} with HTML img tags with size classes

    Syntax: ![Description](image.jpg){md} or ![Description](image.jpg){medium}
    Sizes: sm/small, md/medium, lg/large, full

    Default path: /components/images/additional/
    - Relative paths (no leading /) get prepended with default path
    - Absolute paths (starting with /) used as-is
    - URLs (http/https) used as-is
    """
    # Map long form to short form for CSS classes
    size_map = {
        'small': 'sm',
        'medium': 'md',
        'large': 'lg',
        'full': 'full',
        'sm': 'sm',
        'md': 'md',
        'lg': 'lg'
    }

    def replace_image(match):
        alt = match.group(1)
        src = match.group(2)
        size_input = match.group(3).lower()

        # Map to CSS class
        size_class = size_map.get(size_input, 'md')

        # Prepend default path if relative
        if not src.startswith('/') and not src.startswith('http'):
            src = f'/components/images/additional/{src}'

        return f'<img src="{src}" alt="{alt}" class="img-{size_class}">'

    pattern = r'!\[([^\]]*)\]\(([^)]+)\)\{(sm|small|md|medium|lg|large|full)\}'
    return re.sub(pattern, replace_image, text, flags=re.IGNORECASE)


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
            # Valid term - create link (JavaScript will construct full URL with basePath)
            return f'<a href="#" class="glossary-inline-link" data-term-id="{term_id}">{display_text}</a>'
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
    Validate that an image exists at the expected path.

    Args:
        image_path: Path relative to assets/images/
        file_context: Context string for error messages (e.g., markdown file name)

    Returns:
        tuple: (exists: bool, full_path: str)
    """
    full_path = Path('assets/images') / image_path
    return (full_path.exists(), str(full_path))


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
        dict: Parsed carousel data with 'items' list
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

        items.append(data)

    return {'items': items}


def parse_comparison_widget(content, file_path, warnings_list):
    """
    Parse comparison widget content.

    Expected format:
    :::comparison
    image_before: path1.jpg
    alt_before: Description
    caption_before: Before caption
    credit_before: Source

    image_after: path2.jpg
    alt_after: Description
    caption_after: After caption
    credit_after: Source
    :::

    Returns:
        dict: Parsed comparison data with 'before' and 'after' dicts
    """
    data = parse_key_value_block(content)

    # Validate exactly 2 images
    before_image = data.get('image_before')
    after_image = data.get('image_after')

    if not before_image:
        warnings_list.append({
            'type': 'widget',
            'widget_type': 'comparison',
            'message': 'Comparison widget missing required field: image_before'
        })

    if not after_image:
        warnings_list.append({
            'type': 'widget',
            'widget_type': 'comparison',
            'message': 'Comparison widget missing required field: image_after'
        })

    # Validate images exist
    if before_image:
        exists, full_path = validate_image_path(before_image, file_path)
        if not exists:
            warnings_list.append({
                'type': 'widget',
                'widget_type': 'comparison',
                'message': f'Comparison before image not found: {before_image} (expected at {full_path})'
            })

    if after_image:
        exists, full_path = validate_image_path(after_image, file_path)
        if not exists:
            warnings_list.append({
                'type': 'widget',
                'widget_type': 'comparison',
                'message': f'Comparison after image not found: {after_image} (expected at {full_path})'
            })

    # Warn if alt text missing
    if before_image and 'alt_before' not in data:
        warnings_list.append({
            'type': 'widget',
            'widget_type': 'comparison',
            'message': 'Comparison before image missing alt text (accessibility concern)'
        })

    if after_image and 'alt_after' not in data:
        warnings_list.append({
            'type': 'widget',
            'widget_type': 'comparison',
            'message': 'Comparison after image missing alt text (accessibility concern)'
        })

    # Structure data
    before_data = {
        'image': before_image or '',
        'alt': data.get('alt_before', ''),
        'caption': data.get('caption_before', ''),
        'credit': data.get('credit_before', '')
    }

    after_data = {
        'image': after_image or '',
        'alt': data.get('alt_after', ''),
        'caption': data.get('caption_after', ''),
        'credit': data.get('credit_after', '')
    }

    return {'before': before_data, 'after': after_data}


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
            'comparison': parse_comparison_widget,
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

            # Process image size syntax before markdown conversion
            body = process_image_sizes(body)

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

            # Process image sizes
            content_body = process_image_sizes(content_body)

            # Convert markdown to HTML
            html_content = markdown.markdown(content_body, extensions=['extra', 'nl2br'])
            return {
                'title': '',
                'content': html_content
            }

    except Exception as e:
        print(f"Error reading markdown file {full_path}: {e}")
        return None

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
    Expected columns: order, title, subtitle (optional), byline (optional)
    """
    stories_list = []

    for _, row in df.iterrows():
        order = str(row.get('order', '')).strip()
        title = row.get('title', '')
        subtitle = row.get('subtitle', '')
        byline = row.get('byline', '')

        # Skip rows with empty order (placeholder rows)
        if not order or not pd.notna(title):
            continue

        story_entry = {
            'number': order,
            'title': title
        }

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

    # Validate IIIF manifest field
    if 'iiif_manifest' in df.columns:
        for idx, row in df.iterrows():
            manifest_url = str(row.get('iiif_manifest', '')).strip()
            object_id = row.get('object_id', 'unknown')

            # Skip if empty
            if not manifest_url:
                continue

            # Check if it's a valid URL
            parsed = urlparse(manifest_url)
            if not parsed.scheme in ['http', 'https']:
                df.at[idx, 'iiif_manifest'] = ''
                df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_invalid_url')
                msg = f"Cleared invalid IIIF manifest for object {object_id}: not a valid URL"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
                continue

            # Try to fetch the manifest (with timeout)
            # Create SSL context that doesn't verify certificates (avoid false positives)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            try:
                req = urllib.request.Request(manifest_url, method='HEAD')
                req.add_header('User-Agent', 'Telar/0.3.3-beta (IIIF validator)')

                with urllib.request.urlopen(req, timeout=5, context=ssl_context) as response:
                    content_type = response.headers.get('Content-Type', '')

                    # Check if response is JSON
                    if 'json' not in content_type.lower():
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_not_manifest')
                        msg = f"IIIF manifest for object {object_id} does not return JSON (Content-Type: {content_type})"
                        print(f"  [WARN] {msg}")
                        warnings.append(msg)
                        # Don't clear manifest URL - might still work despite wrong content type
                        continue

                    # Fetch full content to validate structure
                    req_get = urllib.request.Request(manifest_url)
                    req_get.add_header('User-Agent', 'Telar/0.3.3-beta (IIIF validator)')

                    with urllib.request.urlopen(req_get, timeout=10, context=ssl_context) as resp:
                        try:
                            data = json.loads(resp.read().decode('utf-8'))

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

    # Validate that objects have either IIIF manifest OR local image file
    for idx, row in df.iterrows():
        object_id = row.get('object_id', 'unknown')
        iiif_manifest = str(row.get('iiif_manifest', '')).strip()

        # Skip if already has a valid IIIF manifest
        if iiif_manifest:
            continue

        # No external IIIF manifest - check for local image file
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff']
        has_local_image = False

        for ext in valid_extensions:
            local_image_path = Path(f'components/images/objects/{object_id}{ext}')
            if local_image_path.exists():
                has_local_image = True
                print(f"  [INFO] Object {object_id} uses local image: {local_image_path}")
                break

        # Warn if object has neither external manifest nor local image
        if not has_local_image:
            # Check for similar filenames (near-matches)
            similar_files = _find_similar_image_filenames(object_id, Path('components/images/objects'))

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
                # Check for local image in components/images/objects/
                valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff']
                has_local_image = False

                for ext in valid_extensions:
                    local_image_path = Path(f'components/images/objects/{object_id}{ext}')
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

    # Convert project setup
    csv_to_json(
        'components/structures/project.csv',
        '_data/project.json',
        process_project_setup
    )

    # Convert objects (with optional Christmas Tree mode)
    if christmas_tree_mode:
        csv_to_json(
            'components/structures/objects.csv',
            '_data/objects.json',
            lambda df: process_objects(df, christmas_tree=True)
        )
    else:
        csv_to_json(
            'components/structures/objects.csv',
            '_data/objects.json',
            process_objects
        )

    # Note: Glossary is now sourced directly from components/texts/glossary/
    # and processed by generate_collections.py

    # Convert story files (with optional Christmas Tree mode)
    # Look for any CSV files that start with "story-" or "chapter-"
    if christmas_tree_mode:
        for csv_file in structures_dir.glob('story-*.csv'):
            json_filename = csv_file.stem + '.json'
            json_file = data_dir / json_filename
            csv_to_json(
                str(csv_file),
                str(json_file),
                lambda df: process_story(df, christmas_tree=True)
            )

        for csv_file in structures_dir.glob('chapter-*.csv'):
            json_filename = csv_file.stem + '.json'
            json_file = data_dir / json_filename
            csv_to_json(
                str(csv_file),
                str(json_file),
                lambda df: process_story(df, christmas_tree=True)
            )
    else:
        for csv_file in structures_dir.glob('story-*.csv'):
            json_filename = csv_file.stem + '.json'
            json_file = data_dir / json_filename
            csv_to_json(
                str(csv_file),
                str(json_file),
                process_story
            )

        for csv_file in structures_dir.glob('chapter-*.csv'):
            json_filename = csv_file.stem + '.json'
            json_file = data_dir / json_filename
            csv_to_json(
                str(csv_file),
                str(json_file),
                process_story
            )

    print("-" * 50)
    print("Conversion complete!")

if __name__ == '__main__':
    main()
