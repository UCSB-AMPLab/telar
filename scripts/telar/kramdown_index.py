"""
Positions in an Answer, Found Once

`telar.code_spans` reads an answer for links, code and extensions, and
asks again and again where the next `)`, quote, backtick run or `}` after
some offset is. `_Index` finds each kind of position once, when first
needed, and looks it up after, so a search repeated from many starts is a
lookup rather than a scan.

Version: v1.8.0
"""

import bisect
import itertools
import re

from telar.kramdown_blocks import _S

_BACKTICKS = re.compile('`+')
# Each quote that can close a title (link.rb:56): followed by whitespace
# and `)`.
_TITLE_CLOSE = re.compile(rf'(["\']){_S}*\)')
# Whitespace before a quote, which ends a destination in parentheses
# (LINK_PAREN_STOP_RE, link.rb:54).
_SPACE_QUOTE = re.compile(rf'{_S}(?=["\'])')
# The escapes kramdown drops from a link id (escaped_chars.rb:14).
_KRAMDOWN_ESCAPABLE = frozenset('\\.*_+`<>()[]{}#!:|"\'$=-')
# A span extension's stop tag (extensions.rb:187).
_EXTENSION_STOPS = re.compile(r'\{:/(comment|nomarkdown|options)?\}')


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
        size = 1 << max(len(lengths) - 1, 0).bit_length()
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
