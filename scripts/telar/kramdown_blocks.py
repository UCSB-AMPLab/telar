"""
Kramdown's Blocks in an Answer

kramdown reads span syntax, code among it, within a block, and none inside
some blocks. `telar.code_spans` needs to know which stretches of an answer
are which before it reads spans; this module is that reading of blocks.

A paragraph ends at a blank line or at a line that opens another block (a
tag of an element that is not a span element, a list item, heading, quote,
definition, fence, IAL or EOB line), and takes back the lines kramdown
joins to it (a closing tag, a fence never closed, a heading with no text).
A block that opens with such an element's tag, or with a comment, is block
HTML: its content is raw to the matching close, across blank lines, or to
the end of the text, as parse_raw_html reads it. An indented or fenced
code block, `$$…$$` opening a block after a blank line and followed by
one, an IAL or EOB line, and a link definition line are read for no spans.
A link definition does not end a paragraph, so it is read only at a
block's start; its id applies to the whole text.

The names and tags of HTML, and kramdown's content model for its elements,
are here too, since both the blocks and the spans read them.

Version: v1.8.0
"""

import functools
import re

# Whitespace as kramdown's Ruby `\s` has it: ASCII only, so a no-break
# space is not whitespace.
_SPACE = ' \t\n\r\f\v'
_S = r'[ \t\n\r\f\v]'
# An element or attribute name, as REXML's UNAME_STR.
_NAME = r'(?:[^\W\d][-\w.]*:)?[^\W\d][-\w.]*'

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

# A footnote definition line, which is not a link definition (footnote.rb:18).
_FOOTNOTE_DEFINITION = re.compile(r' {0,3}\[\^[A-Za-z0-9_][A-Za-z0-9_-]*\]:')

# The start of a link definition line, to its URL (link.rb:21); the rest is
# read by `_link_definition`. A URL holding whitespace and then a quote is
# refused (link.rb:25).
_LINK_DEFINITION = re.compile(r' {0,3}\[([^\n\]]+)\]:[ \t]*')
_REFUSED_URL = re.compile(r'[ \t]+["\']')
_SPACE_BEFORE_QUOTE = re.compile(r'[ \t]+(?=["\'])')
_NOT_SPACE = re.compile(r'[^ \t\n\r\f\v]')
# A definition line ends at `\n`, at `\r\n`, or at a lone `\r`: kramdown turns
# each into a line break on input (parser/base.rb:102), so a `\r` before a
# `\r\n` is a break of its own.
_LINE_BREAK = re.compile(r'\r\n|[\r\n]')

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
  | [ ]{{0,3}}(?:[+*-]|[0-9]+\.)[\t |]
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
# A line that could close a fence: its run alone, then whitespace.
_FENCE_CLOSE_LINE = re.compile(rf'(?m)^ {{0,3}}([~`]{{3,}}){_S}*?(?:\n|\Z)')
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
        self.fence_closes = None
        # The normalized id of every link definition, which applies to the
        # whole text.
        self.definitions = set()
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
                       self.block_maths, self.link_definition):
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
        """The fenced code block opening at *pos*, or None. The fence is
        searched for only when a line after it could close it. The fence's
        run may be any start of three or more of the opening's, the rest
        being read as its info string."""
        opening = _FENCE_OPENING.match(self.text, pos)
        if not opening:
            return None
        if not self.closes().close_after(opening.group(1), opening.end()):
            return None
        return _FENCE.match(self.text, pos)

    def closes(self):
        if self.fence_closes is None:
            self.fence_closes = _FenceCloses(self.text)
        return self.fence_closes

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

    def link_definition(self, pos):
        """A link definition, which prints nothing. It does not end a
        paragraph, so it is read only at a block's start, and the block
        after it is not after a boundary."""
        if _FOOTNOTE_DEFINITION.match(self.text, pos):
            return None
        definition = _link_definition(self.text, pos)
        if definition is None:
            return None
        self.definitions.add(_link_id(definition[0]))
        self.skip(pos, definition[1])
        return definition[1]

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


class _FenceCloses:
    """Every line in a text that could close a fence, found once: a run of
    three or more tildes and backticks alone on its line. A run closes a
    fence opened by the same run followed by more of its last character, so
    each is filed in a trie under its stem, the run without the repeats of
    its last character at its end, and then under that character."""

    def __init__(self, text):
        self.root = ({}, {})
        for match in _FENCE_CLOSE_LINE.finditer(text):
            run = match.group(1)
            stem = run.rstrip(run[-1])
            node = self.root
            for char in stem:
                node = node[0].setdefault(char, ({}, {}))
            node[1].setdefault(run[-1], []).append(match.start())

    def close_after(self, run, pos):
        """Whether a line starting at or after *pos* closes a fence opened with
        *run*, or with any start of it three or more long, the rest of which
        GFM then reads as the info string.

        Each stretch of one character in *run*, from j to e, is where such a
        start with the stem `run[:j]` ends. Any close line under that stem
        and character closes one of them when e is at least three, since a
        close line is itself at least three long. So the trie is walked once
        along the run."""
        node, start = self.root, 0
        while start < len(run):
            char = run[start]
            end = start
            while end < len(run) and run[end] == char:
                end += 1
            lines = node[1].get(char)
            if end >= 3 and lines and lines[-1] >= pos:
                return True
            for step in run[start:end]:
                node = node[0].get(step)
                if node is None:
                    return False
            start = end
        return False


def _link_definition(text, pos):
    """The link definition at *pos*, as (id, end), or None: LINK_DEFINITION_START
    (link.rb:21) read in one pass over its line rather than by backtracking.
    The URL is in angle brackets, to the first `>` after which the line
    holds only a title or nothing; or it runs to the first whitespace
    before a title that ends the line, or to the line's end. A title on the
    next line alone is read after a URL that ends its line."""
    start = _LINK_DEFINITION.match(text, pos)
    if not start:
        return None
    url = start.end()
    line_end, end = _line_bounds(text, url)
    last = url + len(text[url:line_end].rstrip(' \t')) - 1
    if last < url:
        return None
    if text.startswith('<', url):
        gt = text.find('>', url + 1, line_end)
        while gt != -1:
            if gt == last:
                return start.group(1), _after_url(text, line_end, end)
            if _title_to(text, gt + 1, last):
                return start.group(1), end
            gt = text.find('>', gt + 1, line_end)
    for space in _SPACE_BEFORE_QUOTE.finditer(text, url + 1, last):
        if _title_to(text, space.start(), last):
            refused = _REFUSED_URL.search(text, url, space.start())
            return None if refused else (start.group(1), end)
    if _REFUSED_URL.search(text, url, last + 1) or not _NOT_SPACE.search(text, url, last + 1):
        return None
    return start.group(1), _after_url(text, line_end, end)


def _line_bounds(text, pos):
    """Where the line holding *pos* ends, and where the next begins: past
    its break, or both at the end of the text."""
    match = _LINE_BREAK.search(text, pos)
    return (match.start(), match.end()) if match else (len(text), len(text))


def _title_to(text, space, last):
    """Whether whitespace at *space*, then a quote, begins a title whose
    closing quote is the line's *last* character but spaces."""
    quote = space
    while quote < last and text[quote] in ' \t':
        quote += 1
    return (quote > space and text[quote] in '"\'' and last >= quote + 2
            and text[last] == text[quote])


def _after_url(text, line_end, end):
    """Where a definition whose URL ends its line ends: past the next line
    if that line is a title alone, or at *end*, past its own."""
    if line_end == len(text):
        return end
    line = end
    next_end, after = _line_bounds(text, line)
    lead = line + len(text[line:next_end]) - len(text[line:next_end].lstrip(' \t'))
    last = line + len(text[line:next_end].rstrip(' \t')) - 1
    if lead < next_end and text[lead] in '"\'' and last >= lead + 2 and text[last] == text[lead]:
        return after
    return end


def _link_id(text):
    """A link id as kramdown normalizes it: each whitespace run one space,
    then lower case letter by letter, as Ruby's `downcase`, which has no
    final sigma."""
    return ''.join(char.lower() for char in re.sub(f'{_S}+', ' ', text))


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
