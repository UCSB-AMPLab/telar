"""
Which Fences Can Close

A fence is searched for only when a line after its opening could close it.
The reader answers that from a trie of the close lines, walked once along
the opening run. These tests hold that answer to the plain one, every start
of the run three or more long tried against every close line after it, on
seeded random runs and close lines.

Version: v1.8.0
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.code_spans import _FenceCloses


def _closes_plainly(close_runs, run):
    """Whether a close line with a run in *close_runs* closes a fence opened
    with *run* or with a start of it three or more long: the close is that
    start followed by more of its last character."""
    for length in range(3, len(run) + 1):
        start = run[:length]
        for close in close_runs:
            if close.startswith(start) and set(close[length:]) <= {start[-1]}:
                return True
    return False


def _random_run(rng, low, high):
    return ''.join(rng.choice('~`') for _ in range(rng.randint(low, high)))


def test_the_trie_answers_as_every_start_against_every_close():
    rng = random.Random(582)
    for _ in range(3000):
        closes = [_random_run(rng, 3, 7) for _ in range(rng.randint(0, 4))]
        text = 'a\n' + ''.join(close + '\n' for close in closes)
        index = _FenceCloses(text)
        run = _random_run(rng, 3, 9)
        assert index.close_after(run, 0) == _closes_plainly(closes, run), (closes, run)


def test_only_a_line_after_the_opening_counts():
    text = '~~~\na\n~~~x\n'
    index = _FenceCloses(text)

    assert index.close_after('~~~', 0)
    assert not index.close_after('~~~', text.index('a'))
