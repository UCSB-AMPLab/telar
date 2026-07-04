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
pipeline. Files are expected under `telar-content/texts/`.

`process_inline_content()` handles text written directly in spreadsheet
cells. It normalises line endings (spreadsheets may use `\\r\\n` or
`\\r`), checks for optional YAML frontmatter (only treated as frontmatter
if it contains a `title:` key, to avoid false matches with `---` used
as horizontal rules), and then runs the same pipeline. The markdown
library's `nl2br` extension is enabled so that single line breaks in
the spreadsheet cell produce `<br>` tags in the output.

Content trust model (raw-HTML pass-through is intentional)
----------------------------------------------------------
`markdown.markdown()` is called WITHOUT an HTML sanitiser, so raw HTML
embedded in author markdown/CSV content passes straight through to the
rendered page. This is by design: Telar is a minimal-computing static-site
framework whose content is authored by trusted contributors (the same
people who control the repo), and authors legitimately rely on raw HTML
for layout the markdown syntax cannot express. Adding a sanitiser
(bleach / nh3) would both strip that legitimate HTML and add a runtime
dependency that cuts against the project's no-dependency ethos.

This is a conscious threat-model decision: the trusted-author model.
It holds only while content authorship is trusted.
A multi-author deployment where untrusted users can write story content
(e.g. a future hosted Compositor) must NOT rely on this — it should layer
DOMPurify on the injected panel/glossary HTML in the JS runtime, where the
untrusted boundary actually is.

Version: v1.6.0
"""

import re
import markdown
from telar.images import process_images, resolve_path_case_insensitive
from telar.latex import protect_latex, restore_latex
from telar.widgets import process_widgets

FRONTMATTER_PATTERN = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)$', re.DOTALL)
TITLE_PATTERN = re.compile(r'title:\s*["\']?(.*?)["\']?\s*$', re.MULTILINE)


def _split_frontmatter(content, require_title=False):
    """
    Split optional YAML frontmatter from content, returning (title, body).

    If require_title is True, a frontmatter match is only honored when it
    contains a `title:` key — this avoids false matches with horizontal
    rules or other standalone `---` usage in pasted inline content.

    Args:
        content: Raw text that may begin with a `---`-delimited frontmatter block
        require_title: Whether a `title:` key is required to treat the block as frontmatter

    Returns:
        tuple: (title, body) — title is '' when absent, body is stripped
    """
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return '', content.strip()

    frontmatter_text = match.group(1)
    title_match = TITLE_PATTERN.search(frontmatter_text)

    if require_title and not title_match:
        return '', content.strip()

    title = title_match.group(1) if title_match else ''
    return title, match.group(2).strip()


def _process_pipeline(body, widget_source, widget_warnings):
    """
    Run the widget/image/LaTeX/markdown pipeline shared by file-based and
    inline panel content: process_widgets -> process_images -> protect_latex
    -> markdown.markdown(extensions=['extra', 'nl2br']) -> restore_latex.

    Raw HTML passes through unsanitised by design (trusted-author model) —
    see the module docstring.

    Args:
        body: Markdown text to process
        widget_source: Identifier passed to process_widgets (file_path or 'inline-content')
        widget_warnings: List to collect widget warnings

    Returns:
        str: Rendered HTML
    """
    body = process_widgets(body, widget_source, widget_warnings)
    body = process_images(body)
    body, latex_replacements = protect_latex(body)
    html_content = markdown.markdown(body, extensions=['extra', 'nl2br'])
    html_content = restore_latex(html_content, latex_replacements)
    return html_content


def read_markdown_file(file_path, widget_warnings=None):
    """
    Read a markdown file and parse frontmatter

    Args:
        file_path: Path to markdown file relative to telar-content/texts/
        widget_warnings: Optional list to collect widget warnings

    Returns:
        dict with 'title' and 'content' keys, or None if file doesn't exist
    """
    full_path = resolve_path_case_insensitive('telar-content/texts', file_path)

    if full_path is None:
        print(f"Warning: Markdown file not found: telar-content/texts/{file_path}")
        return None

    # Initialize widget warnings list if not provided
    if widget_warnings is None:
        widget_warnings = []

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()

        title, body = _split_frontmatter(content)
        html_content = _process_pipeline(body, file_path, widget_warnings)

        return {
            'title': title,
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

    # Only treat as frontmatter if it contains a title: key to avoid
    # false matches with horizontal rules or other --- usage
    title, content = _split_frontmatter(content, require_title=True)

    html_content = _process_pipeline(content, 'inline-content', widget_warnings)

    return {
        'title': title,
        'content': html_content
    }
