"""
Where the Code Is in Author Text

Text inside code is shown as written: markdown syntax, maths delimiters and
glossary syntax there are not read. Two passes that transform author text
need to know where that code is: the glossary link pass, which runs on
converted HTML for panels and on markdown for step answers, and the answer
maths pass. This module is the one reading of it both use.

A code span is read as `story-step.html` reads one: a run of N backticks,
closed by the next run of exactly N; a run with no closing match is literal.
A code element is a raw `<code>`, `<pre>`, `<kbd>` or `<samp>` with its
content, which is also what markdown's code spans and blocks become.

Version: v1.8.0
"""

import re

_BACKTICK_RUN = re.compile(r'`+')

# The content stops at the next opening of the same element, so an element
# that is never closed does not make the search rescan the rest of the text.
CODE_ELEMENT = re.compile(r'<(code|pre|kbd|samp)\b[^>]*>(?:(?!<\1\b).)*?</\1\s*>',
                          re.DOTALL | re.IGNORECASE)


def code_spans(text):
    """Every backtick code span in *text*, as (start, end) offsets."""
    runs = [(m.start(), m.end()) for m in _BACKTICK_RUN.finditer(text)]
    later = {}
    for index in range(len(runs) - 1, -1, -1):
        later.setdefault(runs[index][1] - runs[index][0], []).append(index)
    spans = []
    i = 0
    while i < len(runs):
        start, end = runs[i]
        same = later[end - start]
        while same and same[-1] <= i:
            same.pop()
        if not same:
            i += 1
            continue
        close = same.pop()
        spans.append((start, runs[close][1]))
        i = close + 1
    return spans


def code_regions(text):
    """Every stretch of *text* that is code: backtick spans and code
    elements, as (start, end) offsets. They may overlap."""
    return code_spans(text) + [m.span() for m in CODE_ELEMENT.finditer(text)]
