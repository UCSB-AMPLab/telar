"""
LaTeX Detection

This module deals with detecting LaTeX math notation in Telar content
for conditional KaTeX loading. It scans text for display math, inline
math, environments, alternative delimiters, and chemistry notation.

The key challenge is distinguishing genuine inline math like $E = mc^2$
from currency amounts like $50. The heuristic requires that $...$ content
contains at least one LaTeX-like character (backslash, caret, underscore,
or opening brace) and has no space immediately after the opening $ or
before the closing $.

Display math ($$...$$), environments (\\begin{...}), alternative
delimiters (\\(...\\) and \\[...\\]), and chemistry notation (\\ce{...})
are detected unconditionally.

`convert_markdown()` is the only correct way to turn author text into
HTML: Python Markdown rewrites LaTeX it does not recognise as maths, so
every conversion has to hold the maths out of its reach. The helper lives
here rather than in `telar/markdown.py` because that module imports
`telar/widgets.py`, and the widget conversions need the helper too.

Version: v1.8.0
"""

import re
import hashlib
from html import escape

import markdown

from telar.config import get_lang_string

# Display math: $$...$$
_DISPLAY_MATH = re.compile(r'\$\$.+?\$\$', re.DOTALL)

# Inline math: $...$ with heuristics
# - No space after opening $
# - No space before closing $
# - Content must contain at least one LaTeX-like character: \ ^ _ {
_INLINE_MATH = re.compile(r'\$(\S[^$]*?\S|\S)\$')
_LATEX_CHARS = re.compile(r'[\\^_{]')

# \begin{...} environments
_BEGIN_ENV = re.compile(r'\\begin\{')

# Alternative delimiters: \(...\) and \[...\]
_ALT_INLINE = re.compile(r'\\\(')
_ALT_DISPLAY = re.compile(r'\\\[')

# \ce{...} chemistry notation (mhchem)
_CHEM = re.compile(r'\\ce\{')


def has_latex(text):
    """Check whether *text* contains LaTeX math notation.

    Returns ``True`` if the text contains any LaTeX patterns that should
    trigger KaTeX loading.  Uses smart heuristics for ``$...$`` to avoid
    false positives with currency amounts like ``$50``.

    Args:
        text: String to scan for LaTeX patterns.

    Returns:
        bool: ``True`` if LaTeX patterns are detected.
    """
    if not text:
        return False

    # Fast checks first (no heuristics needed)
    if _DISPLAY_MATH.search(text):
        return True
    if _BEGIN_ENV.search(text):
        return True
    if _ALT_INLINE.search(text):
        return True
    if _ALT_DISPLAY.search(text):
        return True
    if _CHEM.search(text):
        return True

    # Inline math with heuristics: $...$ must contain LaTeX-like characters
    for match in _INLINE_MATH.finditer(text):
        content = match.group(1)
        if _LATEX_CHARS.search(content):
            return True

    return False


# Patterns for extracting LaTeX blocks to protect from markdown processing.
# Order matters: longer/greedy patterns first to avoid partial matches.
_PROTECT_PATTERNS = [
    re.compile(r'\$\$.+?\$\$', re.DOTALL),           # $$...$$
    re.compile(r'\\begin\{.*?\}.*?\\end\{.*?\}', re.DOTALL),  # \begin{...}...\end{...}
    re.compile(r'\\\[.*?\\\]', re.DOTALL),            # \[...\]
    re.compile(r'\\\(.*?\\\)', re.DOTALL),            # \(...\)
    re.compile(r'\\ce\{[^}]*\}'),                     # \ce{...}
    _INLINE_MATH,                                      # $...$
]


def latex_spans(text):
    """Every LaTeX block in *text*, as (start, end) character offsets.

    The same patterns `protect_latex` holds out of Python Markdown's
    reach. A caller that must not cut through maths -- the story
    processor, trimming an over-long answer -- asks this module where the
    maths is rather than keeping a second idea of what maths looks like.

    Spans may overlap, because the patterns overlap: `$$a$$` is matched
    both as display math and by the inline pattern. A caller checking
    whether a position sits inside maths wants the union, so the
    duplication costs nothing.
    """
    if not text:
        return []

    return [(match.start(), match.end())
            for pattern in _PROTECT_PATTERNS
            for match in pattern.finditer(text)]


def protect_latex(text):
    """Replace LaTeX blocks with placeholders before markdown processing.

    Returns a tuple of (protected_text, replacements) where replacements
    is a dict mapping placeholder strings to original LaTeX blocks. Pass
    the replacements dict to ``restore_latex()`` after markdown conversion.
    """
    if not text or not has_latex(text):
        return text, {}

    replacements = {}

    def _make_placeholder(match):
        original = match.group(0)
        # Use a hash-based placeholder unlikely to appear in content
        key = f"TLATEX{hashlib.md5(original.encode()).hexdigest()[:12]}END"
        replacements[key] = original
        return key

    for pattern in _PROTECT_PATTERNS:
        text = pattern.sub(_make_placeholder, text)

    return text, replacements


def restore_latex(html, replacements):
    """Restore LaTeX blocks from placeholders after markdown processing."""
    if not replacements:
        return html
    for placeholder, original in replacements.items():
        html = html.replace(placeholder, original)
    return html


# An HTML start or end tag, with quoted attribute values read whole so a
# `>` inside one does not end the match. Markdown reads inline HTML within one
# paragraph, so the text is matched a paragraph at a time: a `<b` in prose
# must not pair with a `>` further down the page.
_HTML_TAG = re.compile(r"""<[A-Za-z/][^<>"']*(?:(?:"[^"]*"|'[^']*')[^<>"']*)*>""")
_BLANK_LINE = re.compile(r'(\n[ \t]*\n)')

# Stands for `[^` inside a tag while the converter runs. Letters only, so
# neither Markdown nor an HTML sanitiser has anything in it to rewrite.
_TAG_FOOTNOTE_MARK = 'TFNTAGOPENEND'


def _hold_tag_footnote_marks(text):
    """*text* with every `[^` inside an HTML tag replaced by a placeholder.

    The footnotes extension matches `[^label]` anywhere in inline text,
    including inside a raw tag's attribute values, and the `<sup>` it
    writes there ends the attribute at its first quote. A reference in an
    attribute is not one a reader can follow, so it is kept as text.
    """
    if not text or '[^' not in text:
        return text

    def _hold(match):
        return match.group(0).replace('[^', _TAG_FOOTNOTE_MARK)

    return ''.join(_HTML_TAG.sub(_hold, paragraph)
                   for paragraph in _BLANK_LINE.split(text))


def _with_localised_footnotes(extensions, footnote_scope=None):
    """(extensions, extension_configs) for footnotes: reading order, translated tooltip.

    Every footnote's return arrow carries a `title`, and Python Markdown's
    own English default was the one string in a rendered panel that never
    came from `_data/languages/`. A Spanish site showed an English tooltip
    on every note.

    `footnotes` is named explicitly even when `extra` already loads it,
    because the configuration is keyed on the extension name and `extra`
    does not carry one. Naming it alongside `extra` is not a rendering
    change: the two extension lists were compared over a document with
    notes, emphasis and a table, and produce identical HTML.

    The language is read here rather than threaded through the eight call
    sites. The tooltip is a property of the site, and there is one site per
    build; a parameter at each call site would be eight chances to forget
    one, which is how half of a fix ships.

    A key that is missing, or a string without exactly one %d, is dropped
    by the library without a word and its English default comes back --
    which is today's behaviour, so the failure is the status quo rather
    than a broken page. The test pins both languages for that reason.

    *footnote_scope*, when given, goes into every anchor the conversion
    writes: `fn:<scope>-<label>` and `fnref:<scope>-<label>` in place of
    `fn:<label>` and `fnref:<label>`. It rides on the extension's
    separator, which the extension splits on when it numbers a repeated
    reference `fnref2:`, so a label must not contain `:<scope>-`.
    """
    extensions = list(extensions or [])
    if not ({'extra', 'footnotes'} & set(extensions)):
        return extensions, {}

    if 'footnotes' not in extensions:
        extensions.append('footnotes')
    config = {
        'BACKLINK_TITLE': get_lang_string('footnotes.backlink_title'),
        # Number notes in the order a reader meets them, not the order
        # their definitions appear. The extension numbers within its own
        # document tree, where HTML spliced into the text -- a widget's
        # sections, a bibliography's entries, each already converted and
        # numbered on its own -- is held out as raw HTML, so each
        # conversion numbers only its own notes.
        'USE_DEFINITION_ORDER': False}
    if footnote_scope:
        config['SEPARATOR'] = ':%s-' % footnote_scope
    return extensions, {'footnotes': config}


def convert_markdown(text, extensions=None, post_process=None,
                     restore_as_text=False, footnote_scope=None):
    """Convert *text* to HTML with its LaTeX held out of the converter's reach.

    Every conversion of author text goes through here. Python Markdown
    treats ``\\(`` and ``\\[`` as escaped punctuation and strips the
    backslash, which removes the delimiters that mark an expression as
    maths; inside ``$$...$$`` it also entity-encodes ``&``, collapses
    ``\\\\`` to one backslash, unescapes braces and turns ``*`` into
    emphasis tags.

    *extensions* is the caller's own list, passed through unchanged. The
    sites differ — a carousel caption converts with none, a panel with
    ``extra`` and ``nl2br``, a page with ``sane_lists`` as well — and a
    single default here would change how one of them renders.

    Footnotes are numbered in the order a reader meets them, and only
    within this conversion. Python Markdown's default follows the order
    the definitions appear, so an author who defines a note before the
    one they reference first would publish a superscript 2 above a
    superscript 1. Notes in HTML already present in *text* -- a widget
    converted before this call -- keep the numbers their own conversion
    gave them.

    A footnote reference written inside an HTML tag -- `<span
    title="[^b]">` -- stays literal text, and the tag stays intact.

    *footnote_scope* keeps this conversion's note anchors apart from any
    other conversion's on the same page. Two widget sections may both
    define `[^s]`; without a scope each writes `id="fn:s"`, and the second
    reference and the second return arrow both land on the first note.

    *post_process* receives the HTML while the maths is still a
    placeholder, and anything that re-parses or rewrites the HTML belongs
    there: fed a restored formula, an HTML parser reads the ``<`` in
    ``$$a <b$$`` as the start of a tag and drops the rest of the field.

    *restore_as_text* escapes the maths on the way back in. A field whose
    *post_process* sanitises — the carousel caption and credit — must set
    it, or ``$$<script>alert(1)</script>$$`` returns to the page after the
    sanitiser has finished and reaches the reader as markup. Escaping is
    invisible to the maths: the browser decodes the entity, so KaTeX still
    reads ``<`` from the text node.

    Args:
        text: Markdown text to convert.
        extensions: Python Markdown extension names, or None for none.
        post_process: Optional callable applied to the converted HTML
            before the LaTeX is restored.
        restore_as_text: Whether to HTML-escape the restored LaTeX.
        footnote_scope: Optional string placed in this conversion's
            footnote anchor ids, unique to the conversion on its page.

    Returns:
        str: Rendered HTML with the original LaTeX intact.
    """
    protected, replacements = protect_latex(text)
    protected = _hold_tag_footnote_marks(protected)
    extensions, configs = _with_localised_footnotes(extensions, footnote_scope)
    html = markdown.markdown(protected, extensions=extensions,
                             extension_configs=configs)
    html = html.replace(_TAG_FOOTNOTE_MARK, '[^')
    if post_process is not None:
        html = post_process(html)
    if restore_as_text:
        replacements = {placeholder: escape(original, quote=False)
                        for placeholder, original in replacements.items()}
    return restore_latex(html, replacements)
