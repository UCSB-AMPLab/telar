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

Version: v0.9.1-beta
"""

import re
import hashlib

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
