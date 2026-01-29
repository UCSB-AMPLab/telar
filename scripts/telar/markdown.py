"""
Markdown File Processing

This module deals with loading and converting markdown content that
appears in story panels. Panel content can come from two sources: a
markdown file on disk (referenced by filename like `my-panel.md` in the
CSV), or inline text typed directly into the spreadsheet cell. Both
paths converge on the same processing pipeline: widgets are parsed first
(via the widgets module), then images are processed (via the images
module), and finally the standard markdown library converts whatever
remains to HTML.

`read_markdown_file()` handles file-based content. It resolves the file
path with case-insensitive fallback (using `resolve_path_case_insensitive`
from the images module), parses optional YAML frontmatter to extract a
title, and then runs the content through the widget/image/markdown
pipeline. Files are expected under `components/texts/`.

`process_inline_content()` handles text written directly in spreadsheet
cells. It normalises line endings (spreadsheets may use `\\r\\n` or
`\\r`), checks for optional YAML frontmatter (only treated as frontmatter
if it contains a `title:` key, to avoid false matches with `---` used
as horizontal rules), and then runs the same pipeline. The markdown
library's `nl2br` extension is enabled so that single line breaks in
the spreadsheet cell produce `<br>` tags in the output.

Version: v0.7.0-beta
"""

import re
import markdown
from telar.images import process_images, resolve_path_case_insensitive
from telar.widgets import process_widgets


def read_markdown_file(file_path, widget_warnings=None):
    """
    Read a markdown file and parse frontmatter

    Args:
        file_path: Path to markdown file relative to components/texts/
        widget_warnings: Optional list to collect widget warnings

    Returns:
        dict with 'title' and 'content' keys, or None if file doesn't exist
    """
    full_path = resolve_path_case_insensitive('components/texts', file_path)

    if full_path is None:
        print(f"Warning: Markdown file not found: components/texts/{file_path}")
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
        print(f"❌ Error reading markdown file {full_path}: {e}")
        return None


def process_inline_content(text, widget_warnings=None):
    """
    Process inline panel content (text written directly in spreadsheet).

    Handles line breaks by splitting into paragraphs and wrapping in <p> tags.
    Supports markdown formatting (bold, italic, links) and raw HTML.
    Also supports YAML frontmatter if user pastes a complete markdown file.

    Args:
        text: Raw text from spreadsheet cell
        widget_warnings: Optional list to collect widget warnings

    Returns:
        dict with 'title' and 'content' (HTML) keys
    """
    if not text or not text.strip():
        return None

    if widget_warnings is None:
        widget_warnings = []

    # Normalize line endings (spreadsheets may use \r\n or \r)
    content = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    title = ''

    # Check for YAML frontmatter (same pattern as read_markdown_file)
    # Only treat as frontmatter if it contains a title: key to avoid
    # false matches with horizontal rules or other --- usage
    frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(frontmatter_pattern, content, re.DOTALL)

    if match:
        frontmatter_text = match.group(1)
        title_match = re.search(r'title:\s*["\']?(.*?)["\']?\s*$', frontmatter_text, re.MULTILINE)
        if title_match:
            title = title_match.group(1)
            content = match.group(2).strip()
        # else: no title: key found, treat entire content as regular text

    # Process widgets BEFORE markdown conversion
    content = process_widgets(content, 'inline-content', widget_warnings)

    # Process images (sizes and captions) BEFORE markdown conversion
    content = process_images(content)

    # Convert markdown to HTML (nl2br handles single line breaks)
    html_content = markdown.markdown(content, extensions=['extra', 'nl2br'])

    return {
        'title': title,
        'content': html_content
    }
