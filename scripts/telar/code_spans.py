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

Links and images are read as parse_link reads them (parser/kramdown/
link.rb). A link's text is read for spans, counting brackets, to the `]`
that closes it in its paragraph; a `]` inside code, HTML, maths, an
escape, an IAL or an extension is not counted, and inside the text a `[`
opens no link, though an image is still read. After the text comes a
destination in parentheses, which may hold spaces, line breaks and
parentheses nested to any depth, and ends at whitespace before a title;
one in angle brackets; or a reference, which is a link only when a link
definition in the text has its id. Destination, title and id are read for
nothing, and so is a link definition line. Where there is no link, its
opening is text. A footnote marker `[^…]` is never a link. An IAL `{:…}`
after an element, and a `comment` or `nomarkdown` extension, print
nothing, so code inside them is not code; after text, an IAL is text.

Not modelled, all rare in an answer: a definition list's content past its
first paragraph; a `markdown` attribute on an element inside block HTML,
and a link definition there; an IAL over several lines; a setext heading
or abbreviation definition; `~~` strikethrough; autolinks, and a `]` that
emphasis or an autolink hides inside a link's text; a span IAL after
emphasis, an entity or a footnote marker with a definition, and `<<` and
`>>`, with or without an IAL after them; footnote definitions; and what an
`options` extension changes. The answer's prose rules have already
flattened list, quote and heading marks.

In a panel, which reaches the glossary pass as HTML, a backtick is a
character and code is an element: a raw `<code>`, `<pre>`, `<kbd>` or
`<samp>` with its content, which is also what markdown's code spans and
blocks become.

Blocks are read by `telar.kramdown_blocks`.

Version: v1.8.0
"""

import bisect
import itertools
import re

from telar.kramdown_blocks import (_BLOCK_ELEMENTS, _CLOSE_TAG, _INDENT, _KNOWN, _OPEN_TAG,
                                   _READ_MODEL, _S, _SPACE, _WITHOUT_BODY, _attributes,
                                   _Blocks, _closing_tag, _link_id)
# Its tests import it from telar.code_spans.
from telar.kramdown_blocks import _FenceCloses  # noqa: F401

# What kramdown reads before a backtick, at the same position: a backslash
# escape (GFM's list of escapable characters, gfm.rb:190), HTML, a link's
# destination, and `$$…$$` within a paragraph.
_ESCAPE = re.compile(r'\\[\\.*_+`<>()\[\]{}#!:|"\'$=~-]')
_NEXT = re.compile(r'[\\<\[\]$`]|!(?=\[)|\{:')
_LT = re.compile('<')
_BACKTICKS = re.compile('`+')

# Links and images, as parse_link reads them (parser/kramdown/link.rb).
# A footnote marker is read before a link, and is text without a
# definition (footnote.rb:37, 40-59; ALD_ID_NAME, ASCII `\w[\w-]*`).
_FOOTNOTE_MARKER = re.compile(r'\[\^[A-Za-z0-9_][A-Za-z0-9_-]*\]')
# A reference's explicit id after the text's `]` (link.rb:55).
_REFERENCE_ID = re.compile(rf'{_S}*?\[([^\]]*)\]')
# The quote opening a title (link.rb:56), and each quote that can close
# one: followed by whitespace and `)`.
_TITLE_OPEN = re.compile(rf'{_S}*(["\'])')
_TITLE_CLOSE = re.compile(rf'(["\']){_S}*\)')
# Whitespace before a quote, which ends a destination in parentheses
# (LINK_PAREN_STOP_RE, link.rb:54).
_SPACE_QUOTE = re.compile(rf'{_S}(?=["\'])')
# The escapes a reference's text loses when it is its own id: kramdown's
# list (escaped_chars.rb:14), not GFM's.
_KRAMDOWN_ESCAPE = re.compile(r'\\([\\.*_+`<>()\[\]{}#!:|"\'$=-])')
_KRAMDOWN_ESCAPABLE = frozenset('\\.*_+`<>()[]{}#!:|"\'$=-')
# Span extensions (extensions.rb:152-153, 187): a start tag's name, a
# stop tag, and the names kramdown knows (96-137).
_EXTENSION_NAME = re.compile(r'\{::([A-Za-z0-9_]+)')
_EXTENSION_STOP = re.compile(r'\{:/([A-Za-z0-9_][A-Za-z0-9_-]*)?\}')
_EXTENSION_STOPS = re.compile(r'\{:/(comment|nomarkdown|options)?\}')
_EXTENSIONS = frozenset({'comment', 'nomarkdown', 'options'})
# A paragraph opening with `\$$` (after up to three spaces) whose first
# `$$` after that is followed only by whitespace to the end of its line:
# kramdown's block maths start, which drops the backslash and leaves the
# rest to the paragraph.
_ESCAPED_BLOCK_MATHS = re.compile(r' {0,3}(\\)\$\$')
_LINE_END = re.compile(r'[ \t\r\f\v]*(?:\n|\Z)')

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


# What a walk's reader returns: go on reading the same frame; and a child
# frame's result not yet known.
_CONTINUE = object()
_PENDING = object()
# What `extension_end` returns when the braces are not an extension tag.
_NOT_EXTENSION = object()


class _Index:
    """Positions in a text, each kind found once when first needed, so a
    search repeated from many starts is a lookup rather than a scan."""

    def __init__(self, text):
        self.text = text
        self.built = {}

    def get(self, name):
        if name not in self.built:
            self.built[name] = getattr(self, 'build_' + name)()
        return self.built[name]

    def build_parentheses(self):
        """The `)` that brings the count from each `(` back to nothing."""
        matching, opened = {}, []
        for match in re.finditer(r'[()]', self.text):
            if match.group() == '(':
                opened.append(match.start())
            elif opened:
                matching[opened.pop()] = match.start()
        return matching

    def build_space_quotes(self):
        return [match.start() for match in _SPACE_QUOTE.finditer(self.text)]

    def build_title_closes(self):
        """For each quote, where each quote followed by whitespace and `)`
        starts, and where that `)` ends."""
        closes = {'"': ([], []), "'": ([], [])}
        for match in _TITLE_CLOSE.finditer(self.text):
            starts, ends = closes[match.group(1)]
            starts.append(match.start())
            ends.append(match.end())
        return closes

    def build_angles(self):
        return ([match.start() for match in re.finditer('>', self.text)],
                [match.start() for match in re.finditer('\n', self.text)])

    def build_braces(self):
        """Every `}`, as a backslash before it leaves it: unescaped, or
        escaped."""
        unescaped, escaped = [], []
        for match in re.finditer('}', self.text):
            k = match.start()
            (escaped if k and self.text[k - 1] == '\\' else unescaped).append(k)
        return unescaped, escaped

    def build_backtick_runs(self):
        """Where each whole run of backticks starts, in order, and a tree of
        the longest run under each node, the runs its leaves."""
        starts, lengths = [], []
        for match in _BACKTICKS.finditer(self.text):
            starts.append(match.start())
            lengths.append(match.end() - match.start())
        size = 1
        while size < len(lengths):
            size *= 2
        longest = [0] * size + lengths + [0] * (size - len(lengths))
        for node in range(size - 1, 0, -1):
            longest[node] = max(longest[2 * node], longest[2 * node + 1])
        return starts, longest, size

    def backtick_run(self, start, length):
        """Where the first *length* backticks in a row at or after *start*
        begin, *start* not being inside a run: the start of the first whole
        run there at least that long, or None."""
        starts, longest, size = self.get('backtick_runs')
        node = bisect.bisect_left(starts, start) + size
        if node - size >= len(starts):
            return None
        while longest[node] < length:
            # Past this subtree: up while it is a right child, then across.
            while node & 1:
                node >>= 1
            if node == 0:
                return None
            node += 1
        while node < size:
            node = 2 * node if longest[2 * node] >= length else 2 * node + 1
        return starts[node - size]

    def build_extension_stops(self):
        stops = {}
        for match in _EXTENSION_STOPS.finditer(self.text):
            stops.setdefault(match.group(1) or '', []).append((match.start(), match.end()))
        return stops

    def build_id_lengths(self):
        """Prefix sums of how a stretch's length changes when it becomes a
        link id: less a whitespace character after another, less each
        backslash kramdown's escapes drop, and one more for each letter
        whose lower case is two (only U+0130)."""
        text = self.text
        change = [0] * (len(text) + 1)
        for match in re.finditer(f'(?<={_S}){_S}|İ', text):
            change[match.start() + 1] += 1 if match.group() == 'İ' else -1
        for match in re.finditer(r'\\+', text):
            start, end = match.span()
            for k in range(start, end - 1, 2):
                change[k + 1] -= 1
            if (end - start) % 2 and end < len(text) and text[end] in _KRAMDOWN_ESCAPABLE:
                change[end] -= 1
        return list(itertools.accumulate(change))


class _Frame:
    """A stretch a walk reads: a link's or image's text, to the `]` that
    ends it, or an HTML element's content, to its closing tag."""

    __slots__ = ('start', 'pos', 'limit', 'last', 'visited', 'waiting', 'key', 'raw',
                 'closing', 'fresh')

    def __init__(self, start, limit, key=None, raw=False, closing=None):
        self.start = self.pos = start
        self.limit = limit
        # The end of the last token read, and whether it made an element:
        # at the start there is none.
        self.last = (start, False)
        # The positions read at this frame's own level, which share its end.
        self.visited = []
        # What a child frame's result is for.
        self.waiting = None
        # An element's frame: its key, whether its content is raw, and its
        # closing tag. A text's frame has no key.
        self.key, self.raw, self.closing = key, raw, closing
        self.fresh = True


class _Scan:
    """One left-to-right reading of *text*, as kramdown reads span syntax.

    At a `[` or `![`, whether a link or image begins is settled by a walk: a
    reading of its text that records nothing, to the `]` that ends it, then
    of its destination or reference. The main reading then goes on inside
    the text, and at that `]` jumps past the destination, which holds no
    span syntax."""

    def __init__(self, text):
        self.text = text
        self.regions = []
        # The stretches read for spans, and where each ends: nothing here
        # crosses one. What kramdown reads none of is skipped.
        blocks = _Blocks(text)
        self.ends = sorted(end for _, end in blocks.units) + [len(text)]
        self.blocks = sorted(blocks.skips)
        self.regions.extend(blocks.regions)
        self.definitions = blocks.definitions
        self.definition_lengths = {len(key) for key in self.definitions}
        # For each needle and paragraph, the lowest start from which the
        # needle has been searched for and not found.
        self.no_close = {}
        # The elements open in this paragraph, innermost last, as
        # (name, raw, closing tag); and where the raw content began.
        self.open = []
        self.paragraph_end = None
        self.raw_from = None
        # The links and images whose text is being read, innermost last, as
        # (the `]` ending the text, where the link ends, how many elements
        # were open when it began); and the text of each image.
        self.links = []
        self.images = []
        # The end of the last token read, and whether it made an element,
        # which a span IAL needs just before it.
        self.last = (0, False)
        # The walks' memos: where a text read from a position ends, and
        # where an element opened at a position ends.
        self.closes = {}
        self.element_ends = {}
        self.index = _Index(text)
        self.dropped = self.dropped_backslashes(blocks.boundary_starts)
        # Where each stretch's text starts, leading spaces off, as kramdown
        # reads it.
        self.block_starts = {0} | {_INDENT.match(text, start).end() for start, _ in blocks.units}
        self.readers = {'[': self.bracket, '!': self.bang, ']': self.close_bracket,
                        '{': self.brace, '`': self.backticks, '<': self.html,
                        '\\': self.backslash, '$': self.dollars}

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

    # The main reading, which records regions.

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
        found = _NEXT.search(self.text, i)
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
        return self.readers[self.text[i]](i)

    def mark(self, end, element):
        """Note the token just read, ending at *end*; where to go on."""
        self.last = (end, element)
        return end

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

    def bracket(self, i):
        """A footnote marker, which is text; a `[` in a link's or image's
        text, or before `^`, which is text; or a link."""
        marker = _FOOTNOTE_MARKER.match(self.text, i, self.limit(i))
        if marker:
            return self.mark(marker.end(), False)
        if self.links or self.text.startswith('[^', i):
            return self.mark(i + 1, False)
        return self.attempt(i + 1, image=False)

    def bang(self, i):
        """An image, or before `[^` a `!` that is text."""
        if self.text.startswith('![^', i):
            return self.mark(i + 1, False)
        return self.attempt(i + 2, image=True)

    def attempt(self, start, image):
        """A link or image whose text starts at *start*: read on inside it,
        or, when it is not one, read its opening as text."""
        close = self.text_end(start)
        end = None if close is None else self.link_end(close, start)
        if end is None:
            return self.mark(start, False)
        self.links.append((close, end, len(self.open)))
        if image:
            self.images.append((start, close))
        return self.mark(start, False)

    def close_bracket(self, i):
        """The `]` ending the innermost link's text, past which its
        destination or reference is skipped; or a `]` that is text."""
        if self.links and self.links[-1][0] == i:
            end = self.links.pop()[1]
            return self.mark(end, True)
        return self.mark(i + 1, False)

    def brace(self, i):
        read = self.brace_end(i, self.element_before(i, self.last), self.limit(i))
        if read is None:
            return self.mark(i + 1, False)
        return self.mark(*read)

    def backslash(self, i):
        if i in self.dropped:
            return i + 1
        return self.mark(self.escape_end(i), False)

    def backticks(self, i):
        end, span = self.code_end(i)
        if span:
            self.regions.append(('code', i, end))
        return self.mark(end, span)

    def dollars(self, i):
        end, kind = self.maths_end(i)
        if kind == 'maths':
            self.regions.append(('maths', i, end))
        elif kind == 'stray':
            # No close in its paragraph, so kramdown prints it as it is,
            # without a backslash it dropped before it.
            self.regions.append(('stray', i - (i - 1 in self.dropped), end))
        return self.mark(end, kind == 'maths')

    def html(self, i):
        """Past the HTML at *i*: the close of the innermost open element,
        unless it was opened before the link whose text this is, where
        its closing tag is text; a comment, CDATA, a tag read as text, or
        an opening tag."""
        text = self.text
        limit = self.limit(i)
        depth = self.links[-1][2] if self.links else 0
        if len(self.open) > depth:
            match = self.open[-1][2].match(text, i, limit)
            if match:
                self.close_element(i, match.end())
                return self.mark(match.end(), True)
        kind, end, match = self.markup(i, limit)
        if kind == 'cdata' and not self.raw():
            self.regions.append(('cdata', i, end))
        if kind == 'open':
            self.open_element(i, match, limit)
        return self.mark(end, kind in ('comment', 'tag'))

    def open_element(self, i, match, limit):
        name, known = _tag_name(match)
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

    # Tokens, read the same by the main reading and by walks.

    def find_close(self, needle, start, limit):
        """The first *needle* at or after *start* that ends by *limit*, or
        -1. Where none is found is remembered as the lowest start from
        which there is none, so a search from an earlier start stops
        there."""
        key = (needle, limit)
        none_from = self.no_close.get(key)
        if none_from is not None and start >= none_from:
            return -1
        end = limit if none_from is None else min(limit, none_from + len(needle) - 1)
        found = self.text.find(needle, start, end)
        if found == -1:
            self.no_close[key] = start
        return found

    def code_end(self, i):
        """Past the backtick run at *i*, and whether it opens a code span."""
        end = _BACKTICKS.match(self.text, i).end()
        if _literal_single(self.text, i, end, self.block_starts):
            return end, False
        run = end - i
        close = self.index.backtick_run(end, run)
        if close is None or close + run > self.limit(end):
            return end, False
        return close + run, True

    def escape_end(self, i):
        match = _ESCAPE.match(self.text, i)
        return match.end() if match else i + 1

    def maths_end(self, i):
        """Past the `$` at *i*, and what it is: 'maths' for a `$$…$$` span,
        'stray' for a `$$` with no close in its paragraph, or None."""
        if not self.text.startswith('$$', i):
            return i + 1, None
        close = self.find_close('$$', i + 2, self.limit(i))
        return (i + 2, 'stray') if close == -1 else (close + 2, 'maths')

    def markup(self, i, limit):
        """What the `<` at *i* begins, as span HTML: (kind, end, match),
        the kind being 'comment' or 'tag' (an element with no body),
        'open' (an element whose content follows), 'cdata' or 'text'."""
        text = self.text
        for opening, closing, kind in (('<!--', '-->', 'comment'), ('<![CDATA[', ']]>', 'cdata')):
            if text.startswith(opening, i):
                close = self.find_close(closing, i + len(opening), limit)
                if close != -1:
                    return kind, close + len(closing), None
        match = _CLOSE_TAG.match(text, i, limit)
        if match:
            return 'text', match.end(), None
        match = _OPEN_TAG.match(text, i, limit)
        if not match:
            return 'text', i + 1, None
        name, _ = _tag_name(match)
        if name in _BLOCK_ELEMENTS:
            return 'text', match.end(), match
        if match.group(4) or name in _WITHOUT_BODY:
            return 'tag', match.end(), match
        return 'open', match.end(), match

    def element_before(self, i, last):
        """Whether an element ends just before the `{` at *i*, *last* being
        the last token's end and whether it made one: that token, or in
        the text after it a smart quote, or a run of `-` or `.` that
        typographic symbols end (`---` and `--`; `...`)."""
        end, element = last
        if end == i:
            return element
        char = self.text[i - 1]
        if char in '"\'':
            return True
        if char not in '-.':
            return False
        run = i - 1
        while run > end and self.text[run - 1] == char:
            run -= 1
        length = i - run
        return length % 3 == 0 if char == '.' else length % 3 != 1

    def brace_end(self, i, before, limit):
        """Past the `{:` at *i*, and whether an element is then the last
        thing read, *before* saying whether one was just before it; or
        None when the `{` is text. An extension tag or an IAL, read as
        parse_span_extensions reads them (extensions.rb:54-94, 187-210)."""
        text = self.text
        if text.startswith('{::', i):
            read = self.extension_end(i, before, limit)
            if read is not _NOT_EXTENSION:
                return read
        elif _EXTENSION_STOP.match(text, i, limit):
            return None
        if not before:
            return None
        close = self.brace_close(i + 2, limit)
        return None if close is None else (close + 1, True)

    def extension_end(self, i, before, limit):
        """An extension start tag at *i*: past it and its body, with what is
        then last (`comment` and `nomarkdown` make an element, `options`
        nothing); None for a name kramdown does not know or a tag with no
        stop tag, whose `{` is text; or _NOT_EXTENSION."""
        text = self.text
        name = _EXTENSION_NAME.match(text, i, limit)
        if not name:
            return _NOT_EXTENSION
        after = name.end()
        if after < limit and text[after] in _SPACE:
            close = self.brace_close(after + 1, limit, empty=True)
            if close is None:
                return _NOT_EXTENSION
            closing = close > after + 1 and text[close - 1] == '/'
        elif text.startswith('}', after):
            close, closing = after, False
        elif text.startswith('/}', after):
            close, closing = after + 1, True
        else:
            return _NOT_EXTENSION
        if name.group(1) not in _EXTENSIONS:
            return None
        if closing:
            return close + 1, before
        stop = self.extension_stop(name.group(1), close + 1, limit)
        if stop is None:
            return None
        return stop, True if name.group(1) != 'options' else before

    def brace_close(self, start, limit, empty=False):
        """The `}` closing attributes that start at *start*, as
        `(?:\\\\\\}|[^}])+\\}` finds it: the first `}` with no backslash
        before it or, with none, by backtracking the last with one; the
        attributes may be empty only if *empty*."""
        if not empty and self.text.startswith('}', start):
            return None
        unescaped, escaped = self.index.get('braces')
        found = bisect.bisect_left(unescaped, start)
        if found < len(unescaped) and unescaped[found] < limit:
            return unescaped[found]
        found = bisect.bisect_left(escaped, limit) - 1
        if found >= 0 and escaped[found] > start:
            return escaped[found]
        return None

    def extension_stop(self, name, start, limit):
        """Past the first `{:/}` or `{:/name}` at or after *start* in the
        paragraph, or None."""
        stops = self.index.get('extension_stops')
        ends = []
        for key in ('', name):
            found = stops.get(key, [])
            k = bisect.bisect_left(found, (start, 0))
            if k < len(found) and found[k][1] <= limit:
                ends.append(found[k])
        return min(ends)[1] if ends else None

    # Where a link or image ends, once its text has.

    def link_end(self, close, start):
        """Where the link or image whose text runs from *start* to the `]`
        at *close* ends, or None when it is not one (link.rb:88-143)."""
        after = close + 1
        limit = self.limit(close)
        if after < limit and self.text[after] == '(':
            return self.destination_end(after, limit)
        if not self.definitions:
            return None
        return self.reference_end(close, start, limit)

    def reference_end(self, close, start, limit):
        """Past a reference link's id, or its text when the text is the id,
        if that id is defined."""
        match = _REFERENCE_ID.match(self.text, close + 1, limit)
        if match and match.group(1):
            key = _link_id(match.group(1))
        else:
            lengths = self.index.get('id_lengths')
            if close - start + lengths[close] - lengths[start] not in self.definition_lengths:
                return None
            key = _link_id(_KRAMDOWN_ESCAPE.sub(r'\1', self.text[start:close]))
        if key not in self.definitions:
            return None
        return match.end() if match else close + 1

    def destination_end(self, at, limit):
        """Past the destination in parentheses at *at*, and its title if it
        has one, or None."""
        text = self.text
        if text.startswith('(<', at):
            gts, newlines = self.index.get('angles')
            gt = _next(gts, at + 2)
            newline = _next(newlines, at + 2)
            if gt is not None and gt < limit and (newline is None or gt < newline):
                if text.startswith(')', gt + 1) and gt + 1 < limit:
                    return gt + 2
                return self.title_end(gt + 1, limit)
        close = self.index.get('parentheses').get(at)
        space = _next(self.index.get('space_quotes'), at)
        if space is not None and space + 1 < limit and (close is None or space < close):
            return self.title_end(space + 1, limit)
        if close is not None and close < limit:
            return close + 1
        return None

    def title_end(self, pos, limit):
        """Past a title at *pos* and the `)` after it, or None."""
        opening = _TITLE_OPEN.match(self.text, pos, limit)
        if not opening:
            return None
        starts, ends = self.index.get('title_closes')[opening.group(1)]
        found = bisect.bisect_left(starts, opening.end() + 1)
        if found < len(starts) and ends[found] <= limit:
            return ends[found]
        return None

    # Walks: a reading of a text or an element that records nothing, on a
    # stack of frames, memoized so that no stretch is read again.

    def text_end(self, start):
        """The `]` ending a link's or image's text that starts at *start*,
        or None."""
        if start in self.closes:
            return self.closes[start]
        stack = [_Frame(start, self.limit(start))]
        value = _PENDING
        while True:
            frame = stack[-1]
            if value is not _PENDING:
                value = self.resume(frame, value)
            if value is _PENDING:
                value = self.read(frame)
                if isinstance(value, _Frame):
                    stack.append(value)
                    value = _PENDING
                    continue
            self.settle(frame, value)
            stack.pop()
            if not stack:
                return value

    def settle(self, frame, value):
        if frame.key is not None:
            self.element_ends[frame.key] = value
            return
        self.closes[frame.start] = value
        for position in frame.visited:
            self.closes[position] = value

    def read(self, frame):
        """Read *frame* on to its end, as a position or None, or to a child
        frame to read first."""
        if frame.fresh:
            frame.fresh = False
            memo = self.closes if frame.key is None else self.element_ends
            key = frame.start if frame.key is None else frame.key
            if key in memo:
                return memo[key]
        text, limit = self.text, frame.limit
        pattern = _LT if frame.raw else _NEXT
        while True:
            found = pattern.search(text, frame.pos, limit)
            if not found:
                return None
            i = found.start()
            if frame.key is None:
                outcome = self.text_token(frame, i)
            else:
                outcome = self.element_token(frame, i)
            if outcome is not _CONTINUE:
                return outcome

    def text_token(self, frame, i):
        """Read the token at *i* in a text: a `]` ends it; a `[` or a
        footnote marker opens a text inside it, as does the `!` of `![^`;
        and `![` an image."""
        text = self.text
        if text[i] != '{':
            if i in self.closes:
                return self.closes[i]
            frame.visited.append(i)
        char = text[i]
        if char == ']':
            return i
        if char == '[':
            marker = _FOOTNOTE_MARKER.match(text, i, frame.limit)
            return self.child(frame, marker.end() if marker else i + 1, 'bracket')
        if char == '!':
            if text.startswith('![^', i):
                return self.child(frame, i + 1, 'bracket')
            return self.child(frame, i + 2, i)
        return self.common_token(frame, i)

    def element_token(self, frame, i):
        """Read the token at *i* in an element's content, which its closing
        tag ends. Brackets are text there, and images are read."""
        text = self.text
        if text[i] == '<':
            close = frame.closing.match(text, i, frame.limit)
            if close:
                return close.end()
        if frame.raw:
            return self.markup_token(frame, i)
        char = text[i]
        if char == '[':
            marker = _FOOTNOTE_MARKER.match(text, i, frame.limit)
            return self.advance(frame, marker.end() if marker else i + 1, False)
        if char == ']' or text.startswith('![^', i):
            return self.advance(frame, i + 1, False)
        if char == '!':
            return self.child(frame, i + 2, i)
        return self.common_token(frame, i)

    def common_token(self, frame, i):
        char = self.text[i]
        if char == '`':
            return self.advance(frame, *self.code_end(i))
        if char == '\\':
            return self.advance(frame, i + 1 if i in self.dropped else self.escape_end(i), False)
        if char == '$':
            end, kind = self.maths_end(i)
            return self.advance(frame, end, kind == 'maths')
        if char == '{':
            read = self.brace_end(i, self.element_before(i, frame.last), frame.limit)
            return self.advance(frame, *(read or (i + 1, False)))
        return self.markup_token(frame, i)

    def markup_token(self, frame, i):
        kind, end, match = self.markup(i, frame.limit)
        if kind != 'open':
            return self.advance(frame, end, kind in ('comment', 'tag'))
        name, known = _tag_name(match)
        source = match.group(2)
        attributes = _attributes(source, known) if 'markdown' in source.lower() else {}
        read = _read_content(name, attributes, frame.raw)
        child = _Frame(end, frame.limit, key=(i, frame.raw), raw=not read,
                       closing=_closing_tag(name, known))
        frame.waiting = 'element'
        return child

    def advance(self, frame, end, element):
        frame.pos, frame.last = end, (end, element)
        return _CONTINUE

    def child(self, frame, start, waiting):
        """A text inside *frame* starting at *start*: a bracket's, or, with
        *waiting* the position of its `![`, an image's."""
        frame.waiting = waiting
        return _Frame(start, frame.limit)

    def resume(self, frame, value):
        """Go on reading *frame* after a child frame that ended at *value*,
        or failed with None; or end *frame*, as None."""
        waiting = frame.waiting
        if waiting in ('element', 'bracket'):
            if value is None:
                return None
            if waiting == 'element':
                self.advance(frame, value, True)
            else:
                self.advance(frame, value + 1, False)
            return _PENDING
        end = None if value is None else self.link_end(value, waiting + 2)
        if end is not None:
            self.advance(frame, end, True)
        elif frame.key is not None:
            # An image that is not one is its `![` as text, and what follows
            # it is read as the element's content.
            self.advance(frame, waiting + 2, False)
        elif value is None:
            return None
        else:
            self.advance(frame, value + 1, False)
        return _PENDING


def _next(positions, start):
    """The first of sorted *positions* at or after *start*, or None."""
    found = bisect.bisect_left(positions, start)
    return positions[found] if found < len(positions) else None


def _tag_name(match):
    """The name of the tag *match* found, in lower case if it is known, and
    whether it is."""
    name = match.group(1)
    known = name.lower() in _KNOWN
    return (name.lower() if known else name), known


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
