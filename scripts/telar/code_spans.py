"""
Where the Code Is in Author Text

Text inside code is shown as written: markdown syntax, maths delimiters and
glossary syntax there are not read. The passes that transform author text
need to know where that code is: the glossary link pass, the answer pass
that prepares maths and pipes for kramdown, and the answer word limit,
which does not cut inside code. This module is the one reading of it they
use.

In an answer, which is markdown that kramdown renders, span syntax is read
within a block: a paragraph, which ends at a blank line or at a line that
opens another block (a tag of an element that is not a span element, a
list item, heading, quote, definition, fence, IAL or EOB line), with the
lines kramdown joins back to it (a closing tag, a fence never closed, a
heading with no text). A block that opens with such an element's tag, or
with a comment, is block HTML: its content is raw to the matching close,
across blank lines, or to the end of the text. An indented or fenced code
block, and `$$…$$` opening a block after a blank line and followed by one,
are read for nothing inside.

Code is a backtick span read as kramdown reads one: a run of N backticks
opens it and the next N consecutive backticks close it, even inside a
longer run, whose remainder is text; a run with no such close is literal,
and a span ends with its block. A single backtick with whitespace (ASCII,
as in Ruby) on both sides, or at the start of a block and followed by
whitespace, is literal, and so is a backtick escaped with a backslash. An
HTML comment, CDATA or tag, a link's destination and a `$$…$$` span are
read before code, so backticks inside them open nothing. HTML elements
are read by kramdown's content model (parser/html.rb): the content of a
span- or block-model element (`span`, `em`, `details`…) is read like any
text, and every other element (`code`, `kbd`, `u`, `script`, an unknown
tag) is raw to its own closing tag, or to the end of the block; a
`markdown` attribute changes which. A block that opens with `\\$$`, whose
first `$$` after it ends a line, is maths: kramdown drops that backslash.
Not modelled, all rare in an answer: a definition list's content past its
first paragraph; a `markdown` attribute on an element inside block HTML;
an IAL over several lines; a setext heading, link or abbreviation
definition; `~~` strikethrough; autolinks; and a code span begun in a
link's text and closed in its destination. The answer's prose rules have
already flattened list, quote and heading marks.

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
# A paragraph opening with `\$$` (after up to three spaces) whose first
# `$$` after that is followed only by whitespace to the end of its line:
# kramdown's block maths start, which drops the backslash and leaves the
# rest to the paragraph.
_ESCAPED_BLOCK_MATHS = re.compile(r' {0,3}(\\)\$\$')
_LINE_END = re.compile(r'[ \t\r\f\v]*(?:\n|\Z)')

# kramdown's blocks, as far as they bound span syntax (GFM input, with its
# paragraph_end quirk: parser/kramdown/paragraph.rb, kramdown-parser-gfm).
# A line holding only whitespace.
_BLANK = re.compile(r'[ \t\r\f\v]*(?:\n|\Z)')
# The first line of an indented code block, which holds text.
_INDENTED = re.compile(r'(?:\t| {4})[ \t]*[^ \t\n\r\f\v]')
# An IAL line. kramdown's may run over several lines; one on a line of its
# own is read, which keeps the search to the line.
_IAL = r' {0,3}\{:(?![:/])(?:\\\}|[^}\n])+\}[ \t\r\f\v]*(?:\n|\Z)'
_IAL_LINE = re.compile(_IAL)
_EOB_LINE = re.compile(r'\^[ \t\r\f\v]*(?:\n|\Z)')
# A heading line, and the closing marks its text loses: with no text left,
# it is not a heading.
_ATX_LINE = re.compile(r'#{1,6}[\t ]+([^\n]*)')
_ATX_CLOSE = re.compile(r'[\t ]#+\Z')
_DEFINITION_LINE = re.compile(r' {0,3}:[\t |]')
# A fenced code block (GFM's FENCED_CODEBLOCK_MATCH): three or more of `~`
# and backticks in any mix, closed by the same run followed by any more of
# its last character.
_FENCE = re.compile(rf' {{0,3}}(([~`]){{3,}}){_S}*?(?:[^ \t\n\r\f\v]+?(?:\?[^ \t\n\r\f\v]*)?)?'
                    rf'{_S}*?\n.*?^ {{0,3}}\1\2*{_S}*?(?:\n|\Z)', re.DOTALL | re.MULTILINE)
# The span elements, and script, whose tag opening a line does not end a
# paragraph.
_LAZY_SPAN = '|'.join(sorted(_SPAN_ELEMENTS | {'script'}))
# A line that ends the paragraph above it. A closing tag, or a fence
# never closed, ends it only for a paragraph to follow, which kramdown
# joins to it, so neither is listed.
_PARAGRAPH_END = re.compile(rf'''
    [ \t\r\f\v]*(?:\n|\Z)
  | \^[ \t\r\f\v]*(?:\n|\Z)
  | {_IAL.replace(' {0,3}', '[ ]{0,3}', 1)}
  | [ ]{{0,3}}<(?>(?!(?:{_LAZY_SPAN})\b){_NAME})
  | [ ]{{0,3}}(?:[+*-]|\d+\.)[\t |]
  | \#{{1,6}}[\t ]
  | [ ]{{0,3}}:[\t |]
  | [ ]{{0,3}}>
  | [ ]{{0,3}}[~`]{{3,}}
''', re.VERBOSE)
_PROCESSING_INSTRUCTION = re.compile(r'<\?.*?\?>', re.DOTALL)
_COMMENT_TOKEN = re.compile(r'<!--.*?-->', re.DOTALL)
_CDATA_TOKEN = re.compile(r'<!\[CDATA\[.*?\]\]>', re.DOTALL)
_LEAD = re.compile(r' {0,3}')
_INDENT = re.compile(r'[ \t]*')
_TRAILING = re.compile(r'(?:[ \t]*\n)?')
_FENCE_START = re.compile(r' {0,3}[~`]{3,}')
_FENCE_OPENING = re.compile(rf' {{0,3}}(([~`]){{3,}}){_S}*?(?:[^ \t\n\r\f\v]+?(?:\?[^ \t\n\r\f\v]*)?)?'
                            rf'{_S}*?\n')
# Block maths: kramdown's BLOCK_MATH_START without its backslash, which the
# span reading handles.
# kramdown's text ends with a line break, so the end of an answer ends a line.
_BLOCK_MATHS = re.compile(rf' {{0,3}}(\$\$.*?\$\$)({_S}*?\n|{_S}*\Z)?', re.DOTALL)
_BLOCK_BOUNDARY = re.compile(r'[ \t\r\f\v]*(?:\n|\Z)|\^[ \t\r\f\v]*(?:\n|\Z)'
                             rf'|{_IAL}')
# A line opening with a tag, open or closing, of an element that is not a
# span element: it ends an indented code block.
_HTML_LINE = re.compile(rf' {{0,3}}</?(?>(?!(?:{_LAZY_SPAN})\b){_NAME})')

# The content stops at the next opening of the same element, so an element
# that is never closed does not make the search rescan the rest of the text.
CODE_ELEMENT = re.compile(r'<(code|pre|kbd|samp)\b[^>]*>(?:(?!<\1\b).)*?</\1\s*>',
                          re.DOTALL | re.IGNORECASE)


def _literal_single(text, start, end, block_starts):
    """A lone backtick between whitespace, which kramdown prints as is. The
    start of a block counts as whitespace."""
    return (end - start == 1 and (start in block_starts or text[start - 1] in _SPACE)
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


# The letters Ruby's case-insensitive match folds with a letter outside
# ASCII: the long s and the Kelvin sign. It folds no others with a known
# element's name, which are ASCII, so not the dotted or dotless i, both of
# which Python's own case-insensitive match folds with i.
_RUBY_FOLDS = {'s': 'sS\u017f', 'k': 'kK\u212a'}


@functools.lru_cache(maxsize=256)
def _closing_tag(name, known):
    """The closing tag of the element *name*: for a known one, in any case,
    as Ruby's case-insensitive match reads it."""
    if not known:
        return re.compile(rf'</{re.escape(name)}{_S}*>')
    letters = ''.join(f'[{_RUBY_FOLDS.get(char, char + char.upper())}]' if char.isalpha()
                      else re.escape(char) for char in name)
    return re.compile(rf'</{letters}{_S}*>')


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


class _Blocks:
    """kramdown's blocks in *text*, as far as span syntax needs them: the
    stretches it reads span syntax in (a paragraph with the lines kramdown
    joins to it, a heading, a list item or quote read as one, each term of
    a definition list), and the stretches it reads none in (a code block,
    a block HTML element with what it holds, a comment opening a block, an
    IAL or EOB line)."""

    def __init__(self, text):
        self.text = text
        # (start, end) of each stretch read for spans; the starts of those
        # that open after a block boundary, where `\\$$` opens block maths.
        self.units = []
        self.boundary_starts = []
        # (start, end) of each stretch read for no spans, and the regions
        # they hold, as (kind, start, end).
        self.skips = []
        self.regions = []
        self.no_comment_close = False
        self.open_fences = set()
        # Whether the block before ended at a blank line, an EOB or IAL
        # line, or is the start of the text.
        self.boundary = True
        pos = 0
        while pos is not None and pos < len(text):
            pos = self.block(pos)

    def skip(self, start, end, kind=None):
        self.skips.append((start, end))
        if kind:
            self.regions.append((kind, start, end))

    def line_end(self, pos):
        end = self.text.find('\n', pos)
        return len(self.text) if end == -1 else end

    def block(self, pos):
        """Read the block at *pos*; where the next one starts, or None."""
        blank = _BLANK.match(self.text, pos)
        if blank:
            self.boundary = True
            return blank.end() if blank.end() > pos else None
        for reader in (self.code_block, self.fenced, self.marker_line, self.block_html,
                       self.block_maths):
            end = reader(pos)
            if end is not None:
                # An EOB line is a boundary; an IAL line leaves it as it was,
                # since it belongs to the block before it or after it.
                self.boundary = (reader == self.marker_line
                                 and (self.boundary or _EOB_LINE.match(self.text, pos)))
                return end
        end = self.paragraph(pos)
        self.boundary = False
        return end

    def code_block(self, pos):
        """An indented code block: its lines, and lazy lines after them, to
        a blank line or a line that ends it."""
        text = self.text
        if not _INDENTED.match(text, pos):
            return None
        end = self.line_end(pos)
        while end < len(text):
            line = end + 1
            if (_BLANK.match(text, line) or _IAL_LINE.match(text, line)
                    or _EOB_LINE.match(text, line) or _HTML_LINE.match(text, line)):
                break
            end = self.line_end(line)
        self.skip(pos, end, 'block')
        return end

    def fenced(self, pos):
        match = self.fence(pos)
        if not match:
            return None
        self.skip(pos, match.end(), 'block')
        return match.end()

    def fence(self, pos):
        """The fenced code block opening at *pos*, or None. A fence left open
        stays open for every later one of its character and length, whose
        close would close it, so that search is made once."""
        opening = _FENCE_OPENING.match(self.text, pos)
        if not opening or opening.group(1) in self.open_fences:
            return None
        match = _FENCE.match(self.text, pos)
        if not match:
            self.open_fences.add(opening.group(1))
        return match

    def marker_line(self, pos):
        """An EOB or IAL line, which prints nothing."""
        match = _EOB_LINE.match(self.text, pos) or _IAL_LINE.match(self.text, pos)
        if not match:
            return None
        self.skip(pos, match.end())
        return match.end()

    def block_html(self, pos):
        """A comment, or an element that is not a span element, opening the
        block, as kramdown's parse_block_html reads them."""
        text = self.text
        tag = _LEAD.match(text, pos).end()
        if text.startswith('<!--', tag):
            return self.block_comment(pos, tag)
        match = _OPEN_TAG.match(text, tag)
        if not match or match.group(1).lower() in _SPAN_ELEMENTS:
            return None
        end = _html_element_end(text, match)
        if end is None:
            # Its content is read: only the tag is skipped.
            return match.end()
        self.skip(pos, end, 'raw')
        name = match.group(1).lower()
        if match.group(4) or name in _WITHOUT_BODY or name in ('script', 'style'):
            # The line break after it is left, and reads as a blank line.
            return end
        return _TRAILING.match(text, end).end()

    def block_comment(self, pos, tag):
        close = -1 if self.no_comment_close else self.text.find('-->', tag + 4)
        if close == -1:
            self.no_comment_close = True
            return None
        end = _TRAILING.match(self.text, close + 3).end()
        self.skip(pos, end)
        return end

    def block_maths(self, pos):
        """`$$…$$` opening a block after a boundary and followed by one:
        maths of its own, which may hold blank lines."""
        text = self.text
        match = _BLOCK_MATHS.match(text, pos)
        if not (self.boundary and match and match.group(2) is not None):
            return None
        if not (match.end() == len(text) or _BLOCK_BOUNDARY.match(text, match.end())):
            return None
        self.skip(pos, match.end())
        self.regions.append(('maths', match.start(1), match.end(1)))
        return match.end()

    def paragraph(self, pos):
        """A paragraph, heading, list item, quote or definition, read for
        spans to the line that ends it."""
        text = self.text
        if self.boundary:
            self.boundary_starts.append(pos)
        end = self.line_end(pos)
        if _heading(text, pos):
            self.units.append((pos, end))
            return end + 1
        while end < len(text):
            line = end + 1
            if _PARAGRAPH_END.match(text, line) and not self.joins(line):
                break
            end = self.line_end(line)
        if end < len(text) and _DEFINITION_LINE.match(text, end + 1):
            # Each line above a definition is a term of its own.
            start = pos
            newline = text.find('\n', start, end)
            while newline != -1:
                self.units.append((start, newline))
                start = newline + 1
                newline = text.find('\n', start, end)
            self.units.append((start, end))
        else:
            self.units.append((pos, end))
        return end + 1 if end < len(text) else None

    def joins(self, line):
        """Whether the line at *line*, which ends a paragraph, opens one that
        kramdown joins to it: a fence never closed, or a tag that does not
        open block HTML."""
        text = self.text
        lead = _LEAD.match(text, line).end()
        if _FENCE_START.match(text, line):
            return not self.fence(line)
        if _ATX_LINE.match(text, line):
            return not _heading(text, line)
        if text.startswith('<', lead) and not _BLANK.match(text, line):
            match = _OPEN_TAG.match(text, lead)
            return not match or match.group(1).lower() in _SPAN_ELEMENTS
        return False


def _heading(text, pos):
    """Whether the line at *pos* is a heading that holds text."""
    match = _ATX_LINE.match(text, pos)
    return bool(match) and bool(_ATX_CLOSE.sub('', match.group(1).strip(_SPACE)).rstrip(_SPACE))


def _html_element_end(text, match):
    """Where the block HTML element opened by *match* ends, or None when
    kramdown reads its content: past its closing tag, or the end of the
    text. Its content is raw, as parse_raw_html reads it."""
    name = match.group(1)
    known = name.lower() in _KNOWN
    name = name.lower() if known else name
    if match.group(4) or name in _WITHOUT_BODY:
        return match.end()
    if name in ('script', 'style'):
        close = _closing_tag(name, True).search(text, match.end())
        return close.end() if close else len(text)
    source = match.group(2)
    if 'markdown' in source.lower():
        markdown = _attributes(source, known).get('markdown')
        if markdown in ('span', 'block') or markdown == '1' and name in _READ_MODEL:
            return None
    return _raw_html_end(text, match.end(), [(name, known)])


def _raw_html_end(text, pos, open_names):
    """Past the closing tag of the innermost of *open_names*, reading the
    raw HTML from *pos* as parse_raw_html does, or the end of the text."""
    while open_names:
        lt = text.find('<', pos)
        if lt == -1:
            return len(text)
        pos = lt + 1
        for token in (_COMMENT_TOKEN, _PROCESSING_INSTRUCTION, _CDATA_TOKEN):
            match = token.match(text, lt)
            if match:
                pos = match.end()
                break
        else:
            pos = _raw_html_tag(text, lt, open_names) or pos
    return pos


def _raw_html_tag(text, lt, open_names):
    """Past the tag at *lt* in raw block HTML, opening or closing an element
    of *open_names*; None when there is no tag there."""
    match = _OPEN_TAG.match(text, lt)
    if match:
        name = match.group(1)
        known = name.lower() in _KNOWN
        name = name.lower() if known else name
        if name in ('script', 'style'):
            close = _closing_tag(name, True).search(text, match.end())
            return close.end() if close else len(text)
        if not (match.group(4) or name in _WITHOUT_BODY):
            open_names.append((name, known))
        return match.end()
    match = _CLOSE_TAG.match(text, lt)
    if not match:
        return None
    innermost, known = open_names[-1]
    closing = match.group(1).lower() if known else match.group(1)
    if closing == innermost:
        open_names.pop()
    return match.end()


class _Scan:
    """One left-to-right reading of *text*, as kramdown reads span syntax."""

    def __init__(self, text):
        self.text = text
        self.regions = []
        # The stretches read for spans, and where each ends: nothing here
        # crosses one. What kramdown reads none of is skipped.
        blocks = _Blocks(text)
        self.ends = sorted(end for _, end in blocks.units) + [len(text)]
        self.blocks = sorted(blocks.skips)
        self.regions.extend(blocks.regions)
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
        self.dropped = self.dropped_backslashes(blocks.boundary_starts)
        # Where each stretch's text starts, leading spaces off, as kramdown
        # reads it.
        self.block_starts = {0} | {_INDENT.match(text, start).end() for start, _ in blocks.units}

    def dropped_backslashes(self, starts):
        """Every backslash kramdown drops from a block's opening `\\$$`."""
        text = self.text
        dropped = set()
        for start in starts:
            match = _ESCAPED_BLOCK_MATHS.match(text, start)
            if not match:
                continue
            close = text.find('$$', match.end())
            if close != -1 and _LINE_END.match(text, close + 2):
                dropped.add(match.start(1))
        return dropped

    def in_block(self, i):
        """The end of the stretch kramdown reads no spans in holding *i*, or
        None."""
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
        """Read the token at *i*, unless a block that is not read holds it."""
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
        if _literal_single(self.text, i, end, self.block_starts):
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
