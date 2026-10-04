"""
Where the Code Is in Author Text

Text inside code is shown as written: markdown syntax, maths delimiters and
glossary syntax there are not read. The passes that transform author text
need to know where that code is: the glossary link pass, the answer pass
that prepares maths and pipes for kramdown, and the answer word limit,
which does not cut inside code. This module is the one reading of it they
use.

In an answer, which is markdown that kramdown renders, code is a backtick
span read as kramdown reads one: a run of N backticks opens it and the next
N consecutive backticks close it, even inside a longer run, whose remainder
is text; a run with no such close is literal, and a span ends with its
paragraph. A single backtick with whitespace (ASCII, as in Ruby) on both
sides, or at the start of the text and followed by whitespace, is literal,
and so is a backtick escaped with a backslash. An HTML comment, CDATA or
tag, a link's destination and a `$$…$$` span are read before code, so
backticks inside them open nothing. HTML elements are read by kramdown's
content model (parser/html.rb): the content of a span- or block-model
element (`span`, `em`, `details`…) is read like any text, and every other
element (`code`, `kbd`, `u`, `script`, an unknown tag) is raw to its own
closing tag, or to the end of the paragraph; a `markdown` attribute changes
which. A paragraph that opens with `\\$$`, whose first `$$` after it ends a
line, is maths: kramdown drops that backslash. A paragraph indented by four
spaces or a tab is a code block. Other block syntax is not read here: the
answer's prose rules have removed it first. Not modelled, all rare in an
answer: `~~` strikethrough; autolinks; and a code span begun in a link's
text and closed in its destination.

In a panel, which reaches the glossary pass as HTML, a backtick is a
character and code is an element: a raw `<code>`, `<pre>`, `<kbd>` or
`<samp>` with its content, which is also what markdown's code spans and
blocks become.

Version: v1.8.0
"""

import bisect
import functools
import itertools
import re

# Whitespace as kramdown's Ruby `\s` has it: ASCII only, so a no-break
# space is not whitespace.
_SPACE = ' \t\n\r\f\v'
_S = r'[ \t\n\r\f\v]'
# An element or attribute name, as REXML's UNAME_STR.
_NAME = r'(?:[^\W\d][-\w.]*:)?[^\W\d][-\w.]*'

# What kramdown reads before a backtick, at the same position: a backslash
# escape (its own list of escapable characters), HTML, a link's
# destination, and `$$…$$` within a paragraph.
_ESCAPE = re.compile(r'\\[\\.*_+`<>()\[\]{}#!:|"\'$=-]')
_OPEN_TAG = re.compile(
    rf'<((?>{_NAME})){_S}*((?>{_S}+{_NAME}(?:{_S}*={_S}*(?:\w+|("|\').*?\3))?)*){_S}*(/)?>',
    re.DOTALL)
_CLOSE_TAG = re.compile(rf'</({_NAME}){_S}*>')
_ATTRIBUTE = re.compile(rf'{_S}*({_NAME})(?:{_S}*={_S}*(?:(\w+)|("|\')(.*?)\3))?', re.DOTALL)
# kramdown's HTML content model. Inside a paragraph, a block element's tag
# is text; a body-less or self-closed tag is only a tag; the content of an
# element of the span or block model is read; every other element, known or
# not, is raw.
_BLOCK_ELEMENTS = frozenset('''
    address article aside applet body blockquote caption col colgroup dd div
    dl dt fieldset figcaption footer form h1 h2 h3 h4 h5 h6 header hgroup hr
    html head iframe legend menu li main map nav ol optgroup p pre section
    summary table tbody td th thead tfoot tr ul'''.split())
_SPAN_ELEMENTS = frozenset('''
    a abbr acronym b big bdo br button cite code del dfn em i img input ins
    kbd label mark option q rb rbc rp rt rtc ruby samp select small span
    strong sub sup time tt u var'''.split())
_WITHOUT_BODY = frozenset('''
    area base br col command embed hr img input keygen link meta param source
    track wbr'''.split())
_READ_MODEL = frozenset('''
    address applet article aside blockquote body dd details div dl fieldset
    figure figcaption footer form header hgroup iframe li main map menu nav
    noscript object section summary td
    a abbr acronym b bdo big button cite caption del dfn dt em h1 h2 h3 h4 h5
    h6 i ins label legend optgroup p q rb rbc rp rt rtc ruby select small span
    strong sub sup th tt'''.split())
_RAW_MODEL = frozenset('script style math option textarea pre code kbd samp var'.split())
# A known name is matched without regard to case, and read in lower case.
_KNOWN = _BLOCK_ELEMENTS | _SPAN_ELEMENTS | _WITHOUT_BODY | _READ_MODEL | _RAW_MODEL
# A link's destination, after the `]` that ends its text; the text holds
# spans like any other.
_DESTINATION = re.compile(r'\((?:[^()\s]|\([^()]*\))*(?:\s+(?:"[^"]*"|\'[^\']*\'))?\)')
_MATHS = re.compile(r'\$\$.*?\$\$', re.DOTALL)
_NEXT = re.compile(r'[\\<\[$`]')
_BLANK_LINE = re.compile(r'\n[ \t]*\n')
# A paragraph opening with `\$$` (after up to three spaces) whose first
# `$$` after that is followed only by whitespace to the end of its line:
# kramdown's block maths start, which drops the backslash and leaves the
# rest to the paragraph.
_ESCAPED_BLOCK_MATHS = re.compile(r'(?m)^ {0,3}(\\)\$\$')
_LINE_END = re.compile(r'[ \t\r\f\v]*(?:\n|\Z)')
# A paragraph whose first line is indented by four spaces or a tab and holds
# text: kramdown's code block.
_INDENTED = re.compile(r'(?:[ \t]*\n)*(?:\t| {4})[ \t]*[^ \t\n\r\f\v]')

# The content stops at the next opening of the same element, so an element
# that is never closed does not make the search rescan the rest of the text.
CODE_ELEMENT = re.compile(r'<(code|pre|kbd|samp)\b[^>]*>(?:(?!<\1\b).)*?</\1\s*>',
                          re.DOTALL | re.IGNORECASE)


def _literal_single(text, start, end):
    """A lone backtick between whitespace, which kramdown prints as is. The
    start of the text counts as whitespace."""
    return (end - start == 1 and (start == 0 or text[start - 1] in _SPACE)
            and end < len(text) and text[end] in _SPACE)


def _read_content(name, attributes, inside_raw):
    """Whether kramdown reads the content of the element *name*, opened with
    *attributes* inside raw content or not."""
    markdown = attributes.get('markdown')
    if markdown == '0':
        return False
    if markdown == 'span':
        return True
    if markdown == '1':
        return name in _READ_MODEL
    return name in _READ_MODEL and not inside_raw


@functools.lru_cache(maxsize=256)
def _closing_tag(name, known):
    """The closing tag of the element *name*: any case for a known one."""
    return re.compile(rf'</{re.escape(name)}{_S}*>', re.IGNORECASE if known else 0)


def _attributes(source, known):
    """The attributes in a tag's *source*, the last of a name winning; a
    known element's attribute names are read in lower case."""
    attributes = {}
    for match in _ATTRIBUTE.finditer(source):
        if not match.group(1):
            continue
        name = match.group(1).lower() if known else match.group(1)
        attributes[name] = match.group(2) or match.group(4) or ''
    return attributes


class _Scan:
    """One left-to-right reading of *text*, as kramdown reads span syntax."""

    def __init__(self, text):
        self.text = text
        self.regions = []
        # Where each paragraph ends, found once: nothing here crosses one.
        self.ends = ([blank.start() for blank in _BLANK_LINE.finditer(text)]
                     + [len(text)])
        # A close searched for and not found stays not found further on in
        # the same paragraph, so an unmatched opening costs one scan per
        # kind and paragraph rather than one per opening.
        self.unclosed = set()
        # The destination of the link being read, skipped when reached; and
        # the next `]`, found once for every `[` before it.
        self.destination = None
        self.bracket = None
        # The elements open in this paragraph, innermost last, as
        # (name, raw, closing tag); and where the raw content began.
        self.open = []
        self.paragraph_end = None
        self.raw_from = None
        self.dropped = self.dropped_backslashes()
        # Indented code blocks, which nothing else here reads inside.
        self.blocks = self.indented_blocks()
        self.regions.extend(('block', start, end) for start, end in self.blocks)

    def dropped_backslashes(self):
        """Every backslash kramdown drops from a paragraph's opening `\\$$`."""
        text = self.text
        dropped = set()
        for match in _ESCAPED_BLOCK_MATHS.finditer(text):
            line = match.start()
            before = text.rfind('\n', 0, max(line - 1, 0)) + 1
            if line and text[before:line - 1].strip(' \t'):
                continue
            close = text.find('$$', match.end())
            if close != -1 and _LINE_END.match(text, close + 2):
                dropped.add(match.start(1))
        return dropped

    def indented_blocks(self):
        """Every paragraph that opens indented by four spaces or a tab,
        which kramdown prints as a code block, lazy lines and all."""
        starts = [0] + [blank.end() for blank in _BLANK_LINE.finditer(self.text)]
        return [(start, self.limit(start)) for start in starts
                if _INDENTED.match(self.text, start)]

    def in_block(self, i):
        """The end of the code block holding *i*, or None."""
        index = bisect.bisect_right(self.blocks, (i, len(self.text))) - 1
        if index >= 0 and self.blocks[index][0] <= i < self.blocks[index][1]:
            return self.blocks[index][1]
        return None

    def limit(self, i):
        """The end of the paragraph holding *i*."""
        return self.ends[bisect.bisect_left(self.ends, i)]

    def run(self):
        i = 0
        while i is not None:
            i = self.step(i)
        self.end_paragraph(len(self.text))
        return self.regions

    def raw(self):
        return bool(self.open) and self.open[-1][1]

    def step(self, i):
        """Read the next token at or after *i*; where to go on, or None."""
        if self.open and i >= self.paragraph_end:
            self.end_paragraph(self.paragraph_end)
        if self.raw():
            return self.raw_step(i)
        i = self.past_destination(i)
        found = _NEXT.search(self.text, i)
        if self.destination and (not found or found.start() >= self.destination[0]):
            i, self.destination = self.destination[1], None
            return i
        if not found:
            return None
        return self.token(found.start())

    def token(self, i):
        """Read the token at *i*, unless an indented code block holds it."""
        block_end = self.in_block(i)
        if block_end is not None:
            return block_end
        if self.open and i >= self.paragraph_end:
            self.end_paragraph(self.paragraph_end)
        char = self.text[i]
        if char == '[':
            return self.link(i)
        if char == '`':
            return self.backticks(i)
        if char == '<':
            return self.html(i)
        if char == '\\':
            return i + 1 if i in self.dropped else self.escape(i)
        return self.dollars(i)

    def raw_step(self, i):
        """In raw content only HTML is read: the next tag, or the end of
        the paragraph, which closes every element still open."""
        lt = self.text.find('<', i, self.paragraph_end)
        if lt == -1:
            self.end_paragraph(self.paragraph_end)
            return self.paragraph_end
        return self.html(lt)

    def end_paragraph(self, end):
        """Close what is open at the end of a paragraph, as kramdown does."""
        if self.raw_from is not None:
            self.regions.append(('raw', self.raw_from, end))
        self.open, self.raw_from = [], None

    def past_destination(self, i):
        """*i*, moved past a destination a span begun in the link's text
        ran into."""
        if self.destination and i >= self.destination[0]:
            i, self.destination = max(i, self.destination[1]), None
        return i

    def link(self, i):
        if self.bracket is None or self.bracket[0] < i:
            end = self.text.find(']', i)
            destination = _DESTINATION.match(self.text, end + 1) if end != -1 else None
            self.bracket = (len(self.text) if end == -1 else end,
                            destination.span() if destination else None)
        if self.bracket[1] and not self.destination:
            self.destination = self.bracket[1]
        return i + 1

    def escape(self, i):
        match = _ESCAPE.match(self.text, i)
        return match.end() if match else i + 1

    def html(self, i):
        """Past the HTML at *i*: the close of the innermost open element, a
        comment, CDATA, a tag read as text, or an opening tag."""
        text = self.text
        limit = self.limit(i)
        if self.open:
            match = self.open[-1][2].match(text, i, limit)
            if match:
                self.close_element(i, match.end())
                return match.end()
        end = text.startswith('<!', i) and (self.delimited(i, '<!--', '-->', limit)
                                           or self.delimited(i, '<![CDATA[', ']]>', limit))
        if end:
            if not self.raw() and text.startswith('<![', i):
                self.regions.append(('cdata', i, end))
            return end
        match = _CLOSE_TAG.match(text, i, limit)
        if match:
            return match.end()
        match = _OPEN_TAG.match(text, i, limit)
        if not match:
            return i + 1
        self.open_element(i, match, limit)
        return match.end()

    def delimited(self, i, opening, closing, limit):
        """The end of a comment or CDATA opened at *i*, or None."""
        if not self.text.startswith(opening, i) or (limit, closing) in self.unclosed:
            return None
        close = self.text.find(closing, i + len(opening), limit)
        if close == -1:
            self.unclosed.add((limit, closing))
            return None
        return close + len(closing)

    def open_element(self, i, match, limit):
        name = match.group(1)
        known = name.lower() in _KNOWN
        name = name.lower() if known else name
        if name in _BLOCK_ELEMENTS or match.group(4) or name in _WITHOUT_BODY:
            return
        source = match.group(2)
        attributes = _attributes(source, known) if 'markdown' in source.lower() else {}
        read = _read_content(name, attributes, self.raw())
        closing = _closing_tag(name, known)
        if not self.open:
            self.paragraph_end = limit
        if self.raw() and read:
            self.regions.append(('raw', self.raw_from, match.end()))
            self.raw_from = None
        elif not self.raw() and not read:
            self.raw_from = i
        self.open.append((name, not read, closing))

    def close_element(self, i, end):
        was_raw = self.open.pop()[1]
        if was_raw and not self.raw():
            self.regions.append(('raw', self.raw_from, end))
            self.raw_from = None
        elif not was_raw and self.raw():
            self.raw_from = i

    def dollars(self, i):
        match = _MATHS.match(self.text, i, self.limit(i))
        if match:
            self.regions.append(('maths', i, match.end()))
            return match.end()
        if self.text.startswith('$$', i):
            # No close in its paragraph, so kramdown prints it as it is,
            # without a backslash it dropped before it.
            self.regions.append(('stray', i - (i - 1 in self.dropped), i + 2))
            return i + 2
        return i + 1

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
        limit = self.limit(end)
        if (limit, run) in self.unclosed:
            return None
        close = self.text.find('`' * run, end, limit)
        if close == -1:
            self.unclosed.add((limit, run))
            return None
        return close + run


def _regions(text):
    """Every code span, raw stretch, `$$…$$` span and stray `$$` in *text*,
    in order of their start, as (kind, start, end) with kind 'code', 'raw',
    'maths' or 'stray', read in one pass as kramdown reads them."""
    return sorted(_Scan(text).run(), key=lambda region: region[1])


def code_spans(text):
    """Every backtick code span in *text*, as (start, end) offsets."""
    return [(start, end) for kind, start, end in _regions(text) if kind == 'code']


def answer_regions(text):
    """Every stretch of an answer kramdown does not read as prose, in order,
    as (kind, start, end): 'code' for a code span, 'block' for an indented
    code block, 'raw' for an HTML element kramdown leaves raw (its tags
    included), 'cdata' for CDATA, and 'maths' for a `$$…$$` span. From one
    reading, so a `$$` inside code is code and a backtick inside maths is
    maths."""
    return [region for region in _regions(text) if region[0] != 'stray']


def raw_regions(text):
    """Every stretch of an answer that kramdown prints as written: code
    spans and blocks, raw HTML elements and CDATA, as (start, end)
    offsets."""
    return [(start, end) for kind, start, end in _regions(text)
            if kind in ('code', 'block', 'raw', 'cdata')]


def stray_dollars(text):
    """Every `$$` in *text* that kramdown prints as it is, having no close
    in its paragraph, as (start, end) offsets. Outside code, maths and raw
    HTML, as `answer_regions` reads them."""
    return [(start, end) for kind, start, end in _regions(text) if kind == 'stray']


def code_elements(text):
    """Every code element in *text*, as (start, end) offsets: in HTML a
    backtick is a character, and code is an element."""
    return [match.span() for match in CODE_ELEMENT.finditer(text)]


def code_regions(text):
    """Every stretch of markdown *text* that is code: backtick spans,
    indented code blocks and code elements, as (start, end) offsets. They
    may overlap."""
    return ([(start, end) for kind, start, end in _regions(text) if kind in ('code', 'block')]
            + code_elements(text))


def overlaps(regions):
    """A test of whether (start, end) overlaps any of *regions*, which may
    overlap each other: a search, not a pass over every region."""
    ordered = sorted(regions)
    starts = [start for start, _ in ordered]
    reach = list(itertools.accumulate((end for _, end in ordered), max))

    def test(start, end):
        count = bisect.bisect_left(starts, end)
        return count > 0 and reach[count - 1] > start
    return test
