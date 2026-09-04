"""
Jekyll Destination Conflict Gate

Jekyll permits two documents to claim one destination. It prints a
`Conflict:` warning naming the destination and the files that share it,
writes whichever one it processed last, and exits 0. The build succeeds
and the losing document is simply absent from the site.

For protected stories that is not a cosmetic problem. If a page wins a
protected story's URL, the story's own page never renders, and the stub
the encryption step looks for is a public literal in `_layouts/story.html`
— so a page carrying a copy of it satisfies every check downstream and
receives the story's envelope. Nothing reading `_site` afterwards can
separate the two, because by then only one file exists.

Detecting the collision is not the hard part; Jekyll already does it, from
every source it renders — collections, pages, static files, whatever
permalink shape produced the path. What was missing is that nobody read
the warning. This module reads it and turns it into a failed build, which
is why the check lives here rather than in the generator: reimplementing
Jekyll's permalink-to-destination rule to predict collisions means
reproducing behaviour that only Jekyll knows, in a second place, and
getting the corners wrong.

Version: v1.7.0
"""

import re

CONFLICT_MARKER = 'Conflict:'

# Jekyll formats every log line as a right-aligned topic, then the message.
# Anchoring to that shape keeps a path that merely contains the word — a
# working directory named `Conflict:`, which appears in the Source and
# Destination lines of every build — from reading as a conflict.
_CONFLICT_LINE_RE = re.compile(r'^\s*Conflict:\s')

# Jekyll prints this when a build finishes, at the default log level. Its
# absence means the log is not a completed build at warning level, so the
# gate has no evidence either way and must not report success.
_BUILD_COMPLETE_RE = re.compile(r'^\s*done in .* seconds\.', re.MULTILINE)

# Jekyll colours its warnings when stdout is a terminal.
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def strip_ansi(text):
    return _ANSI_RE.sub('', text)


def find_conflicts(build_output):
    """Return each conflict Jekyll reported, as a block of text.

    A conflict is the `Conflict:` line plus the indented lines that follow
    it — the destination and the files claiming it. Reported verbatim:
    Jekyll's own wording names both sides, and paraphrasing it would be one
    more place for this to drift.
    """
    lines = strip_ansi(build_output).splitlines()
    blocks = []
    index = 0
    while index < len(lines):
        if _CONFLICT_LINE_RE.match(lines[index]):
            block = [lines[index].strip()]
            index += 1
            while index < len(lines):
                stripped = lines[index].strip()
                # The block ends at the first line that is not indented
                # continuation. Jekyll pads a trailing blank line.
                if not lines[index][:1].isspace() or not stripped:
                    if not stripped:
                        index += 1
                    break
                block.append(stripped)
                index += 1
            blocks.append('\n  '.join(block))
        else:
            index += 1
    return blocks


def is_complete_build_log(build_output):
    """Whether this log is a finished Jekyll build that could report conflicts.

    Absence of the warning is only evidence when the warning would have been
    printed. An empty log, a truncated one, or a build run under
    JEKYLL_LOG_LEVEL=error all contain no `Conflict:` line and mean nothing.
    """
    return bool(_BUILD_COMPLETE_RE.search(strip_ansi(build_output)))


def format_failure(blocks):
    """The message a failed build should carry."""
    return (
        f"Jekyll reported {len(blocks)} destination conflict"
        f"{'s' if len(blocks) != 1 else ''}:\n\n  "
        + "\n\n  ".join(blocks)
        + "\n\nTwo files cannot publish at one address: Jekyll keeps one and "
          "drops the other, so the site would be missing a page it claims to "
          "have. If one of these is a story, the drop is silent and the "
          "protected-story encryption step can end up writing to the wrong "
          "page. Give each file its own permalink."
    )
