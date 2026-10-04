"""
Where the Code Is in Author Text

Text inside code is shown as written: markdown syntax, maths delimiters and
glossary syntax there are not read. The passes that transform author text
need to know where that code is: the glossary link pass, and the answer
passes that prepare maths for kramdown. This module is the one reading of
it they use.

In an answer, which is markdown that kramdown renders, code is a backtick
span read as kramdown reads one: a run of N backticks opens it and the next
N consecutive backticks close it, even inside a longer run, whose remainder
is text; a run with no such close is literal, and a span ends with its
paragraph. A single backtick with whitespace (ASCII, as in Ruby) on both
sides, or at the start of the text and followed by whitespace, is literal,
and so is a backtick escaped with a backslash. An HTML comment or tag, a
link's destination and a `$$…$$` span are read before code, so backticks
inside them open nothing. Block syntax is not read here: the answer's prose
rules have removed it first. Not modelled, all rare in an answer: a
backslash directly before `$$`, which kramdown reads as an escaped dollar or
as the start of maths depending on what follows; elements whose content
kramdown leaves raw (`<u>`, `<mark>`, `<script>` and the like); `~~`
strikethrough; autolinks; and a code span begun in a link's text and closed
in its destination.

In a panel, which reaches the glossary pass as HTML, a backtick is a
character and code is an element: a raw `<code>`, `<pre>`, `<kbd>` or
`<samp>` with its content, which is also what markdown's code spans and
blocks become.

Version: v1.8.0
"""

import bisect
import re

# What kramdown reads before a backtick, at the same position: a backslash
# escape (its own list of escapable characters), an HTML comment or tag, a
# link's destination, and `$$…$$` within a paragraph.
_ESCAPE = re.compile(r'\\[\\.*_+`<>()\[\]{}#!:|"\'$=-]')
_TAG = re.compile(r'<!--.*?-->|</?[A-Za-z][\w:.-]*(?:\s(?:[^<>"\']|"[^"]*"|\'[^\']*\')*)?/?>',
                  re.DOTALL)
# A link: its text, which holds spans like any other, then its destination.
_LINK = re.compile(r'\[[^\]]*\](\((?:[^()\s]|\([^()]*\))*(?:\s+(?:"[^"]*"|\'[^\']*\'))?\))')
_MATHS = re.compile(r'\$\$(?:(?!\n[ \t]*\n).)*?\$\$', re.DOTALL)
_OPAQUE = {'\\': _ESCAPE, '<': _TAG, '$': _MATHS}
_NEXT = re.compile(r'[\\<\[$`]')
_BLANK_LINE = re.compile(r'\n[ \t]*\n')
# Whitespace as kramdown's Ruby `\s` has it: ASCII only, so a no-break
# space is not whitespace.
_SPACE = ' \t\n\r\f\v'

# The content stops at the next opening of the same element, so an element
# that is never closed does not make the search rescan the rest of the text.
CODE_ELEMENT = re.compile(r'<(code|pre|kbd|samp)\b[^>]*>(?:(?!<\1\b).)*?</\1\s*>',
                          re.DOTALL | re.IGNORECASE)


def _literal_single(text, start, end):
    """A lone backtick between whitespace, which kramdown prints as is. The
    start of the text counts as whitespace."""
    return (end - start == 1 and (start == 0 or text[start - 1] in _SPACE)
            and end < len(text) and text[end] in _SPACE)


class _Scan:
    """One left-to-right reading of *text*, as kramdown reads span syntax."""

    def __init__(self, text):
        self.text = text
        self.regions = []
        # Where each paragraph ends, found once: a span does not cross one.
        self.ends = ([blank.start() for blank in _BLANK_LINE.finditer(text)]
                     + [len(text)])
        # A close searched for and not found stays not found further on in
        # the same paragraph, so an unmatched run costs one scan per length
        # and paragraph rather than one per run.
        self.unclosed = set()
        # The destination of the link being read, skipped when reached.
        self.destination = None

    def run(self):
        i = 0
        while i is not None:
            i = self.step(i)
        return self.regions

    def step(self, i):
        """Read the next token at or after *i*; where to go on, or None."""
        i = self.past_destination(i)
        found = _NEXT.search(self.text, i)
        if self.destination and (not found or found.start() >= self.destination[0]):
            i, self.destination = self.destination[1], None
            return i
        if not found:
            return None
        i = found.start()
        if self.text[i] == '[':
            return self.link(i)
        if self.text[i] == '`':
            return self.backticks(i)
        return self.opaque(i)

    def past_destination(self, i):
        """*i*, moved past a destination a span begun in the link's text
        ran into."""
        if self.destination and i >= self.destination[0]:
            i, self.destination = max(i, self.destination[1]), None
        return i

    def link(self, i):
        link = _LINK.match(self.text, i)
        if link and not self.destination:
            self.destination = link.span(1)
        return i + 1

    def opaque(self, i):
        match = _OPAQUE[self.text[i]].match(self.text, i)
        if not match:
            return i + 1
        if self.text[i] == '$':
            self.regions.append(('maths', i, match.end()))
        return match.end()

    def backticks(self, i):
        text = self.text
        end = i
        while end < len(text) and text[end] == '`':
            end += 1
        close = self.close(i, end)
        if close is None:
            return end
        self.regions.append(('code', i, close))
        return close

    def close(self, i, end):
        """Where the run from *i* to *end* closes its span, or None."""
        run = end - i
        if _literal_single(self.text, i, end):
            return None
        limit = self.ends[bisect.bisect_left(self.ends, end)]
        if (limit, run) in self.unclosed:
            return None
        close = self.text.find('`' * run, end, limit)
        if close == -1:
            self.unclosed.add((limit, run))
            return None
        return close + run


def _regions(text):
    """Every code span and `$$…$$` span in *text*, in order, as
    (kind, start, end) with kind 'code' or 'maths', read in one pass as
    kramdown reads them."""
    return _Scan(text).run()


def code_spans(text):
    """Every backtick code span in *text*, as (start, end) offsets."""
    return [(start, end) for kind, start, end in _regions(text) if kind == 'code']


def code_and_maths(text):
    """Every code span and `$$…$$` span in *text*, in order, as
    (kind, start, end), kind being 'code' or 'maths'. From the same reading
    as `code_spans`, so a `$$` inside code is code and a backtick inside
    maths is maths."""
    return _regions(text)


def code_elements(text):
    """Every code element in *text*, as (start, end) offsets: in HTML a
    backtick is a character, and code is an element."""
    return [match.span() for match in CODE_ELEMENT.finditer(text)]


def code_regions(text):
    """Every stretch of *text* that is code: backtick spans and code
    elements, as (start, end) offsets. They may overlap."""
    return code_spans(text) + [m.span() for m in CODE_ELEMENT.finditer(text)]
