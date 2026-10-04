"""
Answer Budget

The length rule a step's answer is held to, so that it fits the smallest
side card without scrolling. The Compositor implements the same rule from
this docstring and from the shared fixture `tests/fixtures/answer-budget.json`
(answer HTML -> words, paragraphs, cost, cut HTML), so the rule is stated
here in full and nothing below adds to it.

**Input.** The answer as the build renders it: HTML, after widgets, media,
tables, code blocks, rules and footnotes are removed and headings, quotes
and lists are made paragraphs. Maths is held out of the HTML as a
placeholder with no whitespace in it (`telar.latex.convert_markdown` passes
the HTML to its `post_process` that way), so a formula counts as part of
one word, and a cut never lands inside one.

**Words.** The answer's text is every text node in document order, with
character references decoded, joined with nothing between them, except
that each `<p>`, `</p>` and `<br>` tag stands for a space. A word is a
maximal run of characters that are not whitespace, as Python's `str.split`
reads whitespace (the no-break space is whitespace).

**Paragraphs.** The number of `<p>` start tags.

**Cost.** words + PARAGRAPH_COST x (paragraphs - 1), and just the words when
there is one paragraph or none. Read along the answer, each word costs 1 and
each `<p>` after the first costs PARAGRAPH_COST where it opens. The answer
fits when its cost is at most ANSWER_BUDGET and it has at most
MAX_PARAGRAPHS paragraphs.

**Cut.** An answer that does not fit keeps the longest run of words from its
start whose running cost -- every word, and every paragraph opened, up to
and including the last word kept -- is at most ANSWER_BUDGET, and which
lies within the first MAX_PARAGRAPHS paragraphs (no word of the sixth
`<p>` or any later one is kept; words before the first `<p>` are kept):
whole paragraphs while they fit, then words of the next while they fit. The cut
never lands inside an `<a>` element: when a word after the last one kept
has text inside an `<a>` still open at the cut, the cut moves back to the
end of the last word before that element, and this repeats until it holds.
The result is the HTML from the start of the answer to the end of the last
word kept, then any end tags that directly follow that word other than
`</p>`, then ELLIPSIS, then an end tag for each element still open,
innermost first. An answer in which no word can be kept becomes ELLIPSIS
alone. The ellipsis joins the last word kept, so a cut answer fits, and
cutting it again changes nothing.

Tags are read as written: a quoted attribute value may hold `>`, a comment
is not markup, and the void elements of HTML (and any tag written `/>`) open
nothing.

Version: v1.8.0
"""

import bisect
import html
import re
from typing import NamedTuple

ANSWER_BUDGET = 85
"""The most an answer may cost and still fit the smallest side card."""

PARAGRAPH_COST = 15
"""What each paragraph after the first costs, in words."""

MAX_PARAGRAPHS = 5
"""The most paragraphs an answer may have and still fit, however short."""

ELLIPSIS = '…'

_TOKEN = re.compile(r"""<!--.*?-->|<[A-Za-z/!?](?:[^<>"']|"[^"]*"|'[^']*')*>""", re.DOTALL)
_TAG_NAME = re.compile(r'</?([A-Za-z][A-Za-z0-9-]*)')
_UNIT = re.compile(r'&(?:#[0-9]+|#[xX][0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]*);|[\s\S]')
_VOID = frozenset({'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                   'link', 'meta', 'param', 'source', 'track', 'wbr'})
_BREAKS = frozenset({'p', 'br'})


class Token(NamedTuple):
    """One piece of an answer's HTML: `kind` is 'text', 'start', 'end',
    'void' or 'other' (a comment or declaration), `name` the lowercase tag
    name of a tag, and `raw` the piece as written."""
    kind: str
    raw: str
    name: str


class Measure(NamedTuple):
    """An answer's words, paragraphs and cost, as the module docstring
    defines them."""
    words: int
    paragraphs: int
    cost: int


def html_tokens(text):
    """*text* as a list of Tokens, in order; joined, their `raw` is *text*."""
    tokens, pos = [], 0
    for match in _TOKEN.finditer(text):
        if match.start() > pos:
            tokens.append(Token('text', text[pos:match.start()], ''))
        tokens.append(_tag_token(match.group()))
        pos = match.end()
    if pos < len(text):
        tokens.append(Token('text', text[pos:], ''))
    return tokens


def _tag_token(raw):
    named = _TAG_NAME.match(raw)
    if not named:
        return Token('other', raw, '')
    name = named.group(1).lower()
    if raw.startswith('</'):
        return Token('end', raw, name)
    if name in _VOID or raw.endswith('/>'):
        return Token('void', raw, name)
    return Token('start', raw, name)


class _Word(NamedTuple):
    token: int
    end: int
    cost: int
    anchors: tuple


class _Reading:
    """An answer read once for its words: where each ends, its running
    cost, and the `<a>` elements open at its end; and for each `<a>`, the
    first and last word with text inside it."""

    def __init__(self, text):
        self.tokens = html_tokens(text)
        self.words = []
        self.paragraphs = 0
        self.words_in_paragraph_limit = None
        self.cost = 0
        self.first_in, self.last_in = {}, {}
        self._anchors, self._next_anchor, self._in_word = [], 0, False
        for index, token in enumerate(self.tokens):
            if token.kind == 'text':
                self._read_text(index, token.raw)
            else:
                self._read_tag(token)

    def _read_tag(self, token):
        if token.name in _BREAKS:
            self._in_word = False
        if token.kind == 'start' and token.name == 'p':
            self.paragraphs += 1
            if self.paragraphs == MAX_PARAGRAPHS + 1:
                self.words_in_paragraph_limit = len(self.words)
            if self.paragraphs > 1:
                self.cost += PARAGRAPH_COST
        if token.name == 'a' and token.kind == 'start':
            self._anchors.append(self._next_anchor)
            self._next_anchor += 1
        elif token.name == 'a' and token.kind == 'end' and self._anchors:
            self._anchors.pop()

    def _read_text(self, index, raw):
        for unit in _UNIT.finditer(raw):
            if html.unescape(unit.group()).isspace():
                self._in_word = False
                continue
            if not self._in_word:
                self._in_word = True
                self.cost += 1
                self.words.append(None)
            number = len(self.words) - 1
            self.words[number] = _Word(index, unit.end(), self.cost, tuple(self._anchors))
            for anchor in self._anchors:
                self.first_in.setdefault(anchor, number)
                self.last_in[anchor] = number

    def measure(self):
        return Measure(len(self.words), self.paragraphs, self.cost)

    def last_word_to_keep(self):
        """The index of the last word a cut keeps, or -1 for none."""
        kept = bisect.bisect_right([word.cost for word in self.words], ANSWER_BUDGET) - 1
        if self.words_in_paragraph_limit is not None:
            kept = min(kept, self.words_in_paragraph_limit - 1)
        while kept >= 0:
            open_later = [anchor for anchor in self.words[kept].anchors
                          if self.last_in[anchor] > kept]
            if not open_later:
                break
            kept = min(self.first_in[anchor] for anchor in open_later) - 1
        return kept


def measure_answer(text):
    """The Measure of answer HTML *text*."""
    return _Reading(text).measure()


def within_budget(measure):
    """Whether a Measure is within ANSWER_BUDGET and MAX_PARAGRAPHS."""
    return measure.cost <= ANSWER_BUDGET and measure.paragraphs <= MAX_PARAGRAPHS


def fits(text):
    """Whether answer HTML *text* is within the budget."""
    return within_budget(measure_answer(text))


def _open_elements(tokens):
    """The names of the elements *tokens* leave open, outermost first."""
    stack = []
    for token in tokens:
        if token.kind == 'start':
            stack.append(token.name)
        elif token.kind == 'end' and token.name in stack:
            del stack[len(stack) - 1 - stack[::-1].index(token.name):]
    return stack


def cut_to_budget(text):
    """Answer HTML *text* cut to ANSWER_BUDGET as the module docstring
    describes; *text* itself when it fits."""
    reading = _Reading(text)
    if within_budget(reading.measure()):
        return text
    kept = reading.last_word_to_keep()
    if kept < 0:
        return ELLIPSIS
    word = reading.words[kept]
    tokens = reading.tokens
    pieces = [token.raw for token in tokens[:word.token]]
    pieces.append(tokens[word.token].raw[:word.end])
    following = word.token + 1
    if word.end == len(tokens[word.token].raw):
        while (following < len(tokens) and tokens[following].kind == 'end'
               and tokens[following].name != 'p'):
            pieces.append(tokens[following].raw)
            following += 1
    used = tokens[:following]
    closers = ''.join(f'</{name}>' for name in reversed(_open_elements(used)))
    return ''.join(pieces) + ELLIPSIS + closers
