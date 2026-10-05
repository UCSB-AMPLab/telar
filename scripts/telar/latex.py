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

import markdown

from telar.config import get_lang_string

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
    if _DISPLAY_MATH_SPAN(text, first=True):
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


def _delimited(opening, closes, gap=0):
    """A finder for the span that opens with *opening* and runs through the
    first of each of *closes* in turn, at least *gap* characters in, as the
    lazy pattern `opening.*?close…` matches: every such span in a text, as
    `finditer` finds them, or with *first* only whether there is one.

    Each close is searched for once. With none after an opening there is
    none after any later opening either, where the pattern would search the
    rest of the text again from each one."""
    def spans(text, first=False):
        found = []
        pos = 0
        while True:
            start = text.find(opening, pos)
            if start == -1:
                return found
            end = start + len(opening) + gap
            for close in closes:
                end = text.find(close, end)
                if end == -1:
                    return found
                end += len(close)
            found.append((start, end))
            if first:
                return found
            pos = end
    return spans


def _pattern(pattern):
    """A finder for the spans *pattern* matches."""
    def spans(text, first=False):
        return [match.span() for match in pattern.finditer(text)]
    return spans


_DISPLAY_MATH_SPAN = _delimited('$$', ['$$'], gap=1)

# LaTeX blocks to protect from markdown processing, each as a finder of
# its spans. Order matters: longer/greedy patterns first to avoid partial
# matches.
_PROTECT_PATTERNS = [
    _DISPLAY_MATH_SPAN,                                    # $$...$$
    _delimited('\\begin{', ['}', '\\end{', '}']),         # \begin{...}...\end{...}
    _delimited('\\[', ['\\]']),                           # \[...\]
    _delimited('\\(', ['\\)']),                           # \(...\)
    _delimited('\\ce{', ['}']),                            # \ce{...}
    _pattern(_INLINE_MATH),                                # $...$
]


def protect_latex(text):
    """Replace LaTeX blocks with placeholders before markdown processing.

    Returns a tuple of (protected_text, replacements) where replacements
    is a dict mapping placeholder strings to original LaTeX blocks. Pass
    the replacements dict to ``restore_latex()`` after markdown conversion.
    """
    if not text or not has_latex(text):
        return text, {}

    replacements = {}

    def _make_placeholder(block):
        # A later pattern can match text that already holds an earlier
        # pattern's placeholder: `$\ce{H2O}$`, or `$x $$y$$ z$`. Each value
        # is kept as the author's text, so one restore pass returns every
        # placeholder and none survives inside another.
        original = restore_latex(block, replacements)
        # Use a hash-based placeholder unlikely to appear in content
        key = f"TLATEX{hashlib.md5(original.encode()).hexdigest()[:12]}END"
        replacements[key] = original
        return key

    for spans in _PROTECT_PATTERNS:
        out = []
        pos = 0
        for start, end in spans(text):
            out.append(text[pos:start] + _make_placeholder(text[start:end]))
            pos = end
        text = ''.join(out) + text[pos:]

    return text, replacements


# A placeholder protect_latex writes.
_PLACEHOLDER = re.compile(r'TLATEX[0-9a-f]{12}END')


# An `&` that does not already start a character reference. Maths that
# reaches a conversion as HTML -- a widget section or a caption rendered
# first -- holds its `<` as `&lt;`, and escaping that again would show the
# entity to the reader.
_BARE_AMPERSAND = re.compile(r'&(?!#\d+;|#[xX][0-9a-fA-F]+;|[A-Za-z][A-Za-z0-9]*;)')


def _escape_maths(original):
    """*original* with `&`, `<` and `>` written as character references,
    leaving any reference it already holds as it is."""
    return _BARE_AMPERSAND.sub('&amp;', original).replace('<', '&lt;').replace('>', '&gt;')


def restore_latex(html, replacements):
    """Restore LaTeX blocks from placeholders after markdown processing, in
    one pass over *html* whatever the number of blocks."""
    if not replacements:
        return html
    return _PLACEHOLDER.sub(lambda match: replacements.get(match.group(0), match.group(0)), html)


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


MARKDOWN_EXTENSIONS = ('extra', 'nl2br', 'smarty')
"""The Python Markdown extensions every conversion of author text uses:
answers, panels, the widgets inside them, pages and glossary pages, so a
line break, a quotation mark and an ellipsis read the same everywhere."""


def _footnote_configs(footnote_scope=None):
    """The footnotes extension's configuration: reading order, translated tooltip.

    Every footnote's return arrow carries a `title`, and Python Markdown's
    own English default would be the one string in a rendered panel that
    does not come from `_data/languages/`.

    The language is read here rather than threaded through the call sites.
    The tooltip is a property of the site, and there is one site per build.

    A key that is missing, or a string without exactly one %d, is dropped
    by the library without a word and its English default comes back.

    *footnote_scope*, when given, goes into every anchor the conversion
    writes: `fn:<scope>-<label>` and `fnref:<scope>-<label>` in place of
    `fn:<label>` and `fnref:<label>`. It rides on the extension's
    separator, which the extension splits on when it numbers a repeated
    reference `fnref2:`, so a label must not contain `:<scope>-`.
    """
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
    return {'footnotes': config}


def convert_markdown(text, post_process=None,
                     footnote_scope=None, extra_extensions=()):
    """Convert *text* to HTML with its LaTeX held out of the converter's reach.

    Every conversion of author text goes through here, with
    MARKDOWN_EXTENSIONS. Python Markdown treats ``\\(`` and ``\\[`` as
    escaped punctuation and strips the backslash, which removes the
    delimiters that mark an expression as maths; inside ``$$...$$`` it also
    entity-encodes ``&``, collapses ``\\\\`` to one backslash, unescapes
    braces and turns ``*`` into emphasis tags.

    *extra_extensions* are added to MARKDOWN_EXTENSIONS for a caller that
    needs more: pages and glossary pages read lists with ``sane_lists``.

    Footnotes are numbered in the order a reader meets them, and only
    within this conversion. Notes in HTML already present in *text* -- a
    widget converted before this call -- keep the numbers their own
    conversion gave them.

    A footnote reference written inside an HTML tag -- `<span
    title="[^b]">` -- stays literal text, and the tag stays intact.

    *footnote_scope* keeps this conversion's note anchors apart from any
    other conversion's on the same page.

    *post_process* receives the HTML while the maths is still a
    placeholder, and anything that re-parses or rewrites the HTML belongs
    there: fed a restored formula, an HTML parser reads the ``<`` in
    ``$$a <b$$`` as the start of a tag and drops the rest of the field.

    The maths is HTML-escaped on the way back in, so a ``<`` or ``&`` in a
    formula is never read as markup, in a field a sanitiser has already
    passed or anywhere else. Escaping is invisible to the maths: the browser
    decodes the entity, so KaTeX still reads ``<`` from the text node.

    Args:
        text: Markdown text to convert.
        post_process: Optional callable applied to the converted HTML
            before the LaTeX is restored.
        footnote_scope: Optional string placed in this conversion's
            footnote anchor ids, unique to the conversion on its page.
        extra_extensions: Python Markdown extension names to use as well.

    Returns:
        str: Rendered HTML with the original LaTeX intact.
    """
    protected, replacements = protect_latex(text)
    protected = _hold_tag_footnote_marks(protected)
    # `footnotes` is named although `extra` loads it: the configuration is
    # keyed on the extension's own name, which `extra` does not carry.
    extensions = list(MARKDOWN_EXTENSIONS) + ['footnotes'] + list(extra_extensions)
    html = markdown.markdown(protected, extensions=extensions,
                             extension_configs=_footnote_configs(footnote_scope))
    html = html.replace(_TAG_FOOTNOTE_MARK, '[^')
    if post_process is not None:
        html = post_process(html)
    replacements = {placeholder: _escape_maths(original)
                    for placeholder, original in replacements.items()}
    return restore_latex(html, replacements)
