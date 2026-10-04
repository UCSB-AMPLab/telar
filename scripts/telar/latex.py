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


# Python Markdown's footnote extension numbers notes in the order their
# definitions appear, so an author who writes their definitions in a
# different order from their references publishes superscripts out of
# sequence: the first note the reader meets can be numbered 2. These
# rewrite the conversion's output so the numbers follow the reading order
# instead. The markup they match is the extension's own and is stable:
# a reference is an anchor of class footnote-ref pointing at #fn:<id>, a
# backref points at #fnref<n>:<id>, and each note is an <li id="fn:<id>">.
_FOOTNOTE_REFERENCE = re.compile(
    r'(<a class="footnote-ref" href="#fn:([^"]+)"[^>]*>)(\d+)(</a>)')
_FOOTNOTE_BACKREF = re.compile(
    r'(<a class="footnote-backref" href="#fnref\d*:([^"]+)"[^>]*title=")'
    r'([^"]*)(")')
_FOOTNOTE_LIST = re.compile(
    r'(<div class="footnote">.*?<ol>)(.*?)(</ol>)', re.DOTALL)
# Only a note's own item carries id="fn:", so splitting on it cannot be
# confused by a list the author wrote inside a note.
_FOOTNOTE_ITEM = re.compile(r'(?=<li id="fn:)')
_FOOTNOTE_ITEM_ID = re.compile(r'^<li id="fn:([^"]+)"')


def renumber_footnotes_by_reference(html):
    """Renumber footnotes in the order a reader meets them.

    Each conversion is its own footnote namespace -- top-level prose, each
    widget section and each bibliography entry are separate -- so this
    renumbers within the HTML it is given and never across a page.

    A note referenced more than once keeps the number of its first
    reference, which is what the second reference already showed.
    """
    order = []
    for match in _FOOTNOTE_REFERENCE.finditer(html):
        identifier = match.group(2)
        if identifier not in order:
            order.append(identifier)
    if not order:
        return html

    number_for = {identifier: position
                  for position, identifier in enumerate(order, 1)}

    def _reference(match):
        return '%s%d%s' % (match.group(1), number_for[match.group(2)],
                           match.group(4))

    html = _FOOTNOTE_REFERENCE.sub(_reference, html)

    def _backref(match):
        identifier = match.group(2)
        if identifier not in number_for:
            return match.group(0)
        # The title is the extension's own sentence with the old number in
        # it; only the number is ours to change.
        title = re.sub(r'\d+', str(number_for[identifier]), match.group(3))
        return '%s%s%s' % (match.group(1), title, match.group(4))

    html = _FOOTNOTE_BACKREF.sub(_backref, html)

    def _list(match):
        items = [item for item in _FOOTNOTE_ITEM.split(match.group(2)) if item]
        if not items:
            return match.group(0)
        # Whatever precedes the first item is the list's own whitespace.
        lead = '' if _FOOTNOTE_ITEM_ID.match(items[0]) else items.pop(0)

        def position(item):
            found = _FOOTNOTE_ITEM_ID.match(item)
            # An item whose id is not referenced anywhere keeps its place
            # at the end rather than being dropped or crashing the build.
            return number_for.get(found.group(1), len(number_for) + 1) if found else 0

        return '%s%s%s%s' % (match.group(1), lead,
                             ''.join(sorted(items, key=position)),
                             match.group(3))

    return _FOOTNOTE_LIST.sub(_list, html)



def _with_localised_footnotes(extensions):
    """(extensions, extension_configs) with the backlink tooltip translated.

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
    """
    extensions = list(extensions or [])
    if not ({'extra', 'footnotes'} & set(extensions)):
        return extensions, {}

    if 'footnotes' not in extensions:
        extensions.append('footnotes')
    return extensions, {'footnotes': {
        'BACKLINK_TITLE': get_lang_string('footnotes.backlink_title')}}

def convert_markdown(text, extensions=None, post_process=None,
                     restore_as_text=False):
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

    Footnotes are renumbered to the order a reader meets them. Python
    Markdown numbers them in the order their definitions appear, so an
    author who defines a note before the one they reference first
    publishes a superscript 2 above a superscript 1.

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

    Returns:
        str: Rendered HTML with the original LaTeX intact.
    """
    protected, replacements = protect_latex(text)
    extensions, configs = _with_localised_footnotes(extensions)
    html = markdown.markdown(protected, extensions=extensions,
                             extension_configs=configs)
    # Before *post_process*, which may sanitise or unwrap the HTML: the
    # numbers have to be right in what the caller is handed, not in what
    # the converter happened to emit.
    html = renumber_footnotes_by_reference(html)
    if post_process is not None:
        html = post_process(html)
    if restore_as_text:
        replacements = {placeholder: escape(original, quote=False)
                        for placeholder, original in replacements.items()}
    return restore_latex(html, replacements)
