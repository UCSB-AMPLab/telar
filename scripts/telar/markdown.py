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
as horizontal rules), and then runs the same pipeline.

`render_markdown()` is the conversion every whole body of author text goes
through -- panels, step answers, pages and glossary pages: it closes any
HTML container the text leaves open, then converts with
`telar.latex.convert_markdown`, whose extensions (`extra`, `nl2br`,
`smarty`) are the same for every conversion, so a single line break is a
line break and quotes and ellipses are typographic wherever an author
writes them.

Content trust model (raw-HTML pass-through is intentional)
----------------------------------------------------------
Markdown is converted WITHOUT an HTML sanitiser, so raw HTML
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

Version: v1.8.0
"""

import re

import markdown
import yaml
from markdown.extensions.md_in_html import HTMLExtractorExtra

from telar.frontmatter import FRONTMATTER_LOAD_ERRORS
from telar.images import process_images, resolve_path_case_insensitive
from telar.latex import MARKDOWN_EXTENSIONS, convert_markdown, protect_latex
from telar.widgets import process_widgets

FRONTMATTER_PATTERN = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)$', re.DOTALL)
# Anchored, because `subtitle:` ends in `title:` and an unanchored search
# matches inside it. A top-level YAML key sits at column 0, so no leading
# whitespace is allowed either: an indented `title:` belongs to the mapping
# above it, and the parse that reads the value would not find it there.
TITLE_PATTERN = re.compile(r'^title:\s*["\']?(.*?)["\']?\s*$', re.MULTILINE)


def _split_frontmatter(content, source='content'):
    """
    Split optional YAML frontmatter from content, returning (title, body).

    A leading `---` block counts as front matter only when it carries a
    `title:` key. `---` is also the markdown horizontal rule, and a rule at
    the top of a panel is an ordinary thing to write: without the
    condition, everything up to the author's next rule is read as metadata
    and discarded, silently, and the panel still renders — just shorter.

    `title` is the only key anything reads out of these blocks, so a block
    without one has nothing any caller would have used. Of the two ways to
    be wrong, this is the loud one: front matter mistaken for content puts
    visible YAML on the page, where its author can see it, while content
    mistaken for front matter simply disappears.

    A block that does parse as a YAML mapping and still has no title is the
    case that is now shown rather than swallowed, so it is worth saying so
    — otherwise its author sees their metadata on the page and no reason
    for it. Ordinary prose under a rule does not parse as a mapping and so
    says nothing, which is the common case and stays quiet.

    A single prose line containing a colon does parse as a mapping, so it
    is warned about when it was only ever a sentence. That is the right
    direction for the warning to be wrong in: it is advisory, the text is
    kept either way, and the remedy it suggests — separate the block from
    the text below it — is good advice for a line that ambiguous.

    Args:
        content: Raw text that may begin with a `---`-delimited frontmatter block
        source: Name used in the warning, when there is one

    Returns:
        tuple: (title, body) — title is '' when absent, body is stripped
    """
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return '', content.strip()

    frontmatter_text = match.group(1)
    body = match.group(2).strip()
    title_match = TITLE_PATTERN.search(frontmatter_text)

    if not title_match:
        if _looks_like_metadata(frontmatter_text):
            print(f"  Warning: {source} opens with a block that looks like "
                  "front matter but has no title: key, so it is being shown "
                  "as content. Add a title: key, or separate it from the "
                  "text below it.")
        return '', content.strip()

    # TITLE_PATTERN only gates whether this block carries a title: key; the
    # value itself is read by parsing the block as YAML, not by the regex
    # match above. An escape inside a quoted title (`\"`, `\n`, `\N`) is
    # YAML's to interpret, not plain text the regex's quote-stripping can
    # approximate — it only trims the outer quote characters and leaves
    # whatever is between them untouched, backslashes included.
    try:
        parsed = yaml.safe_load(frontmatter_text)
    except FRONTMATTER_LOAD_ERRORS:
        parsed = None

    if isinstance(parsed, dict) and 'title' in parsed:
        title = parsed['title']
        if isinstance(title, str):
            return title, body
        # A title is text, and YAML types it: `yes` is a boolean, `~` and
        # `null` are null, `[a]` a list. `str()` on those puts a Python
        # literal on the page -- `True`, `None`, `['a']` -- which is neither
        # what the author typed nor anything they can search for. The gate
        # has already matched the line, so its reading is the text as typed.
        return title_match.group(1).strip(), body

    print(f"  Warning: {source}'s front matter could not be parsed as "
          "YAML, so the title was read as plain text.")
    return title_match.group(1), body


def _looks_like_metadata(block):
    """Whether a leading block is a YAML mapping rather than prose.

    Prose under a horizontal rule parses as a string, or does not parse at
    all; only a mapping could have been anyone's front matter.
    """
    try:
        return isinstance(yaml.safe_load(block), dict)
    except FRONTMATTER_LOAD_ERRORS:
        return False


def _unclosed_html_blocks(body):
    """Tags the Markdown library's HTML block pass leaves open at the end of *body*.

    The answer comes from the library's own parser, fed the way its
    html_block preprocessor feeds it: after the preprocessors that run
    before it, so a tag inside a fenced code block is code and is not
    counted. The tags come back outermost first. Left open, Python Markdown
    closes only to the nearest tag of the same name, and two nested
    containers of one name lose the outer one's text.

    LaTeX is held out first, as convert_markdown does, so a `<div>` inside
    a formula is not read as a tag.
    """
    protected, _ = protect_latex(body)
    md = markdown.Markdown(extensions=list(MARKDOWN_EXTENSIONS))
    html_block = md.preprocessors['html_block']
    lines = protected.split('\n')
    for preprocessor in md.preprocessors:
        if preprocessor is html_block:
            break
        lines = preprocessor.run(lines)
    parser = HTMLExtractorExtra(md)
    parser.feed('\n'.join(lines))
    return list(parser.mdstack)


def _close_html_blocks(body, source):
    """Append the closing tags *body* is missing, and warn once.

    Author text is never dropped: the result renders as *body* would if its
    author had closed every container at the end, innermost first. Text
    that closes everything it opens is returned as it is.
    """
    unclosed = _unclosed_html_blocks(body)
    if not unclosed:
        return body
    opened = ', '.join(f'<{tag}>' for tag in unclosed)
    closers = ''.join(f'</{tag}>' for tag in reversed(unclosed))
    pronoun = 'it' if len(unclosed) == 1 else 'them'
    where = 'inline content' if source == 'inline-content' else source
    print(f"  Warning: {where} opens {opened} and does not close {pronoun}. "
          f"The build closes {pronoun} at the end of the text; add {closers} "
          f"where the text should end.")
    return body + '\n' + closers


def render_markdown(body, source='inline-content', post_process=None,
                    extra_extensions=()):
    """*body*, a whole piece of author markdown, as HTML.

    Containers *body* leaves open are closed at its end, with a warning
    naming *source*, and the text is converted by `convert_markdown`.
    *post_process* receives the HTML while maths is still a placeholder:
    whatever reads or rewrites the rendered HTML -- glossary links, an
    answer's flattening and cut -- runs there. *extra_extensions* are
    Python Markdown extensions a caller needs beyond the shared ones.

    Raw HTML passes through unsanitised by design (trusted-author model) --
    see the module docstring.
    """
    body = _close_html_blocks(body, source)
    return convert_markdown(body, post_process=post_process,
                            extra_extensions=extra_extensions)


def _process_pipeline(body, widget_source, widget_warnings, post_process=None):
    """
    Run the widget/image/markdown pipeline shared by file-based and inline
    panel content: process_widgets -> process_images -> render_markdown.

    Args:
        body: Markdown text to process
        widget_source: Identifier passed to process_widgets (file_path or 'inline-content')
        widget_warnings: List to collect widget warnings
        post_process: Optional callable given the rendered HTML (see
            render_markdown)

    Returns:
        str: Rendered HTML
    """
    body = process_widgets(body, widget_source, widget_warnings)
    body = process_images(body)
    return render_markdown(body, widget_source, post_process)


def read_markdown_file(file_path, widget_warnings=None, post_process=None):
    """
    Read a markdown file and parse frontmatter

    Args:
        file_path: Path to markdown file relative to telar-content/texts/
        widget_warnings: Optional list to collect widget warnings
        post_process: Optional callable given the rendered HTML (see
            render_markdown)

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

        title, body = _split_frontmatter(content, source=file_path)
        html_content = _process_pipeline(body, file_path, widget_warnings, post_process)

        return {
            'title': title,
            'content': html_content
        }

    except Exception as e:
        print(f"❌ Error reading markdown file {full_path}: {e}")
        return None


def process_inline_content(text, widget_warnings=None, post_process=None):
    """
    Process inline panel content (text written directly in spreadsheet).

    Handles line breaks by splitting into paragraphs and wrapping in <p> tags.
    Supports markdown formatting (bold, italic, links) and raw HTML.
    Also supports YAML frontmatter if user pastes a complete markdown file.

    Args:
        text: Raw text from spreadsheet cell
        widget_warnings: Optional list to collect widget warnings
        post_process: Optional callable given the rendered HTML (see
            render_markdown)

    Returns:
        dict with 'title' and 'content' (HTML) keys
    """
    if not text or not text.strip():
        return None

    if widget_warnings is None:
        widget_warnings = []

    # Normalize line endings (spreadsheets may use \r\n or \r)
    content = text.replace('\r\n', '\n').replace('\r', '\n').strip()

    title, content = _split_frontmatter(content, source='inline content')

    html_content = _process_pipeline(content, 'inline-content', widget_warnings,
                                     post_process)

    return {
        'title': title,
        'content': html_content
    }
