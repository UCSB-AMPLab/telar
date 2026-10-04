"""
Story Processor

This module deals with converting a story CSV into the JSON that drives
a Telar narrative. Each row in the spreadsheet represents one "step" in
the story — a combination of a viewer object (the image the reader sees),
a question-and-answer pair, and up to two content layers (panels that
slide in from the side with text, images, or interactive widgets).

`process_story()` is the main entry point. It receives a pandas DataFrame
from one story CSV and performs several passes over the data:

1. **Object validation** — checks that every object ID referenced in the
   `object` column actually exists in `_data/objects.json`. Lookups are
   case-insensitive, so `MyMap` matches `mymap`. Missing references
   produce localised viewer warnings that appear in the story's intro
   panel.

2. **Content processing** — for each content column (`layer1_content`,
   `layer2_content`, and their legacy `_file` equivalents), the function
   determines whether the cell value is a markdown file reference (ending
   in `.md`) or inline text typed directly into the spreadsheet. File
   references are loaded by `read_markdown_file()` from the markdown
   module; inline text is processed by `process_inline_content()`. Both
   paths run through the same pipeline: widgets first, then images, then
   markdown-to-HTML conversion. After HTML conversion, glossary links
   (`[[term_id]]` syntax) are resolved by `process_glossary_links()`. The
   step's `answer` prose is glossary-processed too (the `question` is a
   heading and is left alone), so `[[term]]` works in the main story text,
   not only in layer panels.

3. **Answer limits** — the step's `answer` is prose read on a card that
   does not scroll, so it is held to plain prose and to a length that
   fits. `ANSWER_PROSE_RULES` says what comes out of it and what is
   flattened, and an answer still above `ANSWER_WORD_LIMIT` words is cut
   at a word boundary that does not land inside markup. This pass runs
   on the answer as the author wrote it, before glossary anchors go into
   it.

4. **Coordinates** — empty `x`, `y`, and `zoom` cells get default
   values (0.5, 0.5, 1) so the viewer always has a valid starting
   position. A comma decimal (`0,5`) is read as the number it is. Any
   other cell that is not a number is reported and left as typed.

5. **Warning aggregation** — all warnings (missing objects, missing
   markdown files, broken glossary links, widget errors, answers held to
   the limits, coordinates that are not numbers) are collected
   into a `viewer_warnings` list stored in `df.attrs`, which the core
   module later injects into the JSON output for display in the story's
   intro panel.

In Christmas Tree Mode, `process_story()` appends additional fake
warnings covering every warning type (viewer, panel, glossary) so that
the intro panel's error display can be visually tested.

Version: v1.8.0
"""

import bisect
import html
import itertools
import math
import numbers
import re
import json
from collections import namedtuple
from pathlib import Path

import pandas as pd

from telar.config import get_lang_string
from telar.glossary import load_glossary_terms, process_glossary_links
from telar.markdown import read_markdown_file, process_inline_content
from telar.code_spans import (answer_regions, code_elements, code_spans, overlaps, raw_regions,
                              stray_dollars)
from telar.csv_utils import IMAGE_EXTENSIONS, build_stem_index
from telar.latex import _HTML_TAG, _LATEX_CHARS, has_latex, latex_spans
from telar.media_type import AUDIO_EXTENSIONS


def _warn(msg, warnings):
    """Print a WARN-prefixed message and record it in the warnings list."""
    print(f"  [WARN] {msg}")
    warnings.append(msg)



ANSWER_WORD_LIMIT = 200
"""Words a step's answer may hold before the build cuts it.

Above this the answer is unreadable rather than merely long: on the desktop
layout the side card never scrolls, so everything past the card's edge is
clipped and no reader can reach it. The tightest common laptop cells hold
225 words at 1280x720, 264 at 1366x768 and 275 at 1440x757, and this limit
sits under that floor with a margin for a larger type size.

The Compositor reads this constant by name, from this module, for a parity
test against its own editor-side limit, so the name and the module path are
part of that shared contract and cannot move quietly.
"""

ANSWER_MEDIA = 'media'
ANSWER_WIDGETS = 'widgets'
ANSWER_FOOTNOTES = 'footnotes'
ANSWER_MARKUP = 'markup'

_ProseRule = namedtuple('_ProseRule', 'name kind pattern replacement')

ANSWER_PROSE_RULES = (
    _ProseRule(
        'widget', ANSWER_WIDGETS,
        re.compile(r'^[ \t]*:::[A-Za-z0-9_]+[ \t]*\n[\s\S]*?^[ \t]*:::[ \t]*$\n?',
                   re.MULTILINE),
        ''),
    _ProseRule(
        'fenced code block', ANSWER_MARKUP,
        re.compile(r'^[ \t]*(`{3,}|~{3,})[^\n]*\n[\s\S]*?^[ \t]*\1[ \t]*\n?',
                   re.MULTILINE),
        ''),
    _ProseRule(
        'table', ANSWER_MARKUP,
        re.compile(r'^[^\n|]*\|[^\n]*\n'
                   r'[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*'
                   r'(?:\|[ \t]*:?-{2,}:?[ \t]*)*\|?[ \t]*\n'
                   r'(?:[^\n]*\|[^\n]*\n?)*',
                   re.MULTILINE),
        ''),
    _ProseRule(
        'image or embed', ANSWER_MEDIA,
        re.compile(r'!\[(?:[^\[\]]|\[[^\[\]]*\])*\]\([^)]*\)'
                   r'|<(img|iframe|video|audio|embed|object)\b[^>]*>'
                   r'(?:.*?</\1\s*>)?',
                   re.IGNORECASE | re.DOTALL),
        ''),
    _ProseRule(
        'footnote definition', ANSWER_FOOTNOTES,
        re.compile(r'^[ \t]*\[\^[^\]]*\]:.*(?:\n[ \t]+\S.*)*\n?',
                   re.MULTILINE),
        ''),
    _ProseRule(
        'footnote reference', ANSWER_FOOTNOTES,
        re.compile(r'\[\^[^\]]*\]'),
        ''),
    _ProseRule(
        'horizontal rule', ANSWER_MARKUP,
        re.compile(r'^[ \t]{0,3}(?:(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}'
                   r'|(?:_[ \t]*){3,})$\n?',
                   re.MULTILINE),
        ''),
    _ProseRule(
        'blockquote mark', ANSWER_MARKUP,
        re.compile(r'^[ \t]*(?:>[ \t]?)+', re.MULTILINE),
        ''),
    _ProseRule(
        'heading mark', ANSWER_MARKUP,
        re.compile(r'^[ \t]*#{1,6}[ \t]+(.*?)[ \t]*#*[ \t]*$', re.MULTILINE),
        r'\1'),
    _ProseRule(
        'list marker', ANSWER_MARKUP,
        re.compile(r'^[ \t]*(?:[-*+]|[0-9]+[.)])[ \t]+', re.MULTILINE),
        ''),
)
"""Everything a step's answer is not allowed to be, in the order applied.

A step's answer is plain prose. The Compositor mirrors this set on the
editor side and reads this list as the contract, so both the expressions
and their order are part of it.

Removed outright, with the words inside them:

  - **widget** -- a `:::name` line through the next line that is `:::`
    alone, which is the block the widget pass renders in a panel. It runs
    first, so a carousel's images and a callout's lines go with it and
    are reported once, as a widget. Widgets do not go in a step's answer;
    they belong in a layer panel.
  - **fenced code block** -- ``` or ~~~ through its matching fence.
  - **table** -- a pipe-table block: a row carrying a pipe, a delimiter
    row, and the body rows that follow while they carry one.
  - **image or embed** -- markdown image syntax, and the HTML elements
    that bring their own media (img, iframe, video, audio, embed,
    object), opening tag through closing tag where one exists.
  - **footnote definition** -- a line opening `[^n]:`, through the
    indented continuation lines that belong to it.
  - **footnote reference** -- `[^n]` in the prose. It runs after the
    definition rule, which would otherwise be left holding a bare colon.
  - **horizontal rule** -- a line of three or more dashes, asterisks or
    underscores. It runs before the list rule, which would read `* * *`
    as a bullet.

Flattened, losing their marks and keeping their words:

  - **blockquote mark** -- the leading `>`, every level of it. It runs
    before the heading and list rules, so a quoted heading or bullet
    reaches them.
  - **heading mark** -- the ATX `#` marks, leading and closing.
  - **list marker** -- the bullet or number opening a list item.

Untouched, because they are prose: bold, italics, inline links,
`[[term]]`, inline LaTeX, code spans, paragraph breaks.

Detection runs on the raw markdown with no awareness of code spans, so
image syntax inside backticks goes too. The rules have to be expressions
the Compositor can implement identically, and a step's answer is prose
about an object rather than a markdown tutorial. A bare image URL is
text and stays.

Nothing repairs the whitespace a removal leaves behind: each rule takes
out what it matched and nothing else, so an answer carrying none of these
comes back byte for byte and markdown decides what the rest means.
"""

# The order warnings are reported in, one per answer per kind, whatever
# order the rules that fired sit in.
ANSWER_KINDS = (ANSWER_MEDIA, ANSWER_WIDGETS, ANSWER_FOOTNOTES, ANSWER_MARKUP)

# What each kind is called in the message catalogue.
_ANSWER_KIND_KEYS = {
    ANSWER_MEDIA: 'answer_image_dropped',
    ANSWER_WIDGETS: 'answer_widget_dropped',
    ANSWER_FOOTNOTES: 'answer_footnotes_dropped',
    ANSWER_MARKUP: 'answer_markup_flattened',
}

# Markup a cut must not land inside. Each of these is one thing to a reader
# and to the renderer, so half of one publishes as broken syntax rather than
# as a shortened answer. LaTeX comes from telar.latex, which owns the
# question of what maths looks like, and code spans from telar.code_spans,
# which reads them as the template does. A footnote reference is absent
# because the prose rules have already taken it out.
#
# Each is read as the pattern after it matches with `finditer`, finding
# each close once in a sorted list of where that character stands: the
# pattern searches the rest of the text again from every opening that has
# no close.
#   glossary reference  \[\[[^\]]*\]\]
#   markdown link       \[[^\]]*\]\([^)]*\)
#   inline HTML tag     <[^>]+>


class _Closes:
    """Where each closing character stands in a text, and the first of
    one at or after a position, or -1. Each reader asks about later and
    later positions, so a cursor moves forward instead of searching; it
    goes back only when a reader starts again from the beginning."""

    def __init__(self, text):
        self.at = {char: [m.start() for m in re.finditer(re.escape(char), text)]
                   for char in ']>)'}
        self.cursor = dict.fromkeys(self.at, 0)

    def after(self, char, pos):
        positions = self.at[char]
        index = self.cursor[char]
        if index and positions[index - 1] >= pos:
            index = bisect.bisect_left(positions, pos)
        while index < len(positions) and positions[index] < pos:
            index += 1
        self.cursor[char] = index
        return positions[index] if index < len(positions) else -1


def _glossary_references(text, closes):
    spans, pos = [], 0
    while (start := text.find('[[', pos)) != -1:
        close = closes.after(']', start + 2)
        if close == -1:
            break
        if text.startswith(']]', close):
            spans.append((start, close + 2))
            pos = close + 2
        else:
            pos = start + 1
    return spans


def _markdown_links(text, closes):
    spans, pos = [], 0
    while (start := text.find('[', pos)) != -1:
        close = closes.after(']', start + 1)
        if close == -1:
            break
        paren = closes.after(')', close + 2) if text.startswith('(', close + 1) else None
        if paren == -1:
            break
        if paren is None:
            pos = start + 1
        else:
            spans.append((start, paren + 1))
            pos = paren + 1
    return spans


def _html_tags(text, closes):
    spans, pos = [], 0
    while (start := text.find('<', pos)) != -1:
        close = closes.after('>', start + 1)
        if close == -1:
            break
        if close == start + 1:
            pos = start + 1
        else:
            spans.append((start, close + 1))
            pos = close + 1
    return spans


_ANSWER_ATOMIC = (_glossary_references, _markdown_links, _html_tags)

# The token that ends a cut answer. One character, so the count of words
# before it stays the count this module reports.
_ANSWER_ELLIPSIS = '…'


def _count_answer_words(text):
    """The number of words in *text*, by the rule the Compositor shares.

    Trim, split on Unicode whitespace, count the non-empty tokens. Markup
    and URLs are words, because they take up the card like any other text,
    and a non-breaking space separates words like any other whitespace.
    """
    return len(str(text).split())


def _reduce_answer_to_prose(text):
    """*text* as plain prose, and the kinds of thing that came out of it.

    Applies ANSWER_PROSE_RULES in order; that constant's docstring is the
    whole of what the rules are and why they run in that order. The kinds
    come back in ANSWER_KINDS order rather than in the order the rules
    fired, so one answer earns one warning per kind and always the same
    sequence of them.
    """
    fired = set()
    for rule in ANSWER_PROSE_RULES:
        text, count = rule.pattern.subn(rule.replacement, text)
        if count:
            fired.add(rule.kind)

    return text, [kind for kind in ANSWER_KINDS if kind in fired]


def _answer_atomic_spans(text):
    """Every span in *text* a cut must fall outside of."""
    closes = _Closes(text)
    spans = [span for markup in _ANSWER_ATOMIC for span in markup(text, closes)]
    spans.extend(latex_spans(text))
    spans.extend(code_spans(text))
    return spans


def _cut_answer(text, limit):
    """*text* shortened to at most *limit* words, closed with an ellipsis.

    The cut lands on a word boundary, and never inside markup. A boundary
    that falls within a link, a glossary or footnote reference, a code
    span, a LaTeX span or an HTML tag moves back to the start of that
    markup and then back to the nearest earlier boundary, repeating until
    it is clear -- so an answer that ends near markup publishes shorter
    than the limit rather than broken at it.

    A token holding no whitespace cannot be split this way, because a word
    boundary never falls inside one.
    """
    boundaries = [match.end() for match in re.finditer(r'\S+', text)]
    if len(boundaries) <= limit:
        return text

    # The spans by start, and the furthest any of the first k reaches: the
    # first whose reach passes the cut is the earliest span over it.
    spans = sorted(_answer_atomic_spans(text))
    starts = [start for start, _ in spans]
    reach = list(itertools.accumulate((end for _, end in spans), max))
    cut = boundaries[limit - 1]
    while True:
        first = bisect.bisect_right(reach, cut)
        if first >= len(spans) or starts[first] >= cut:
            break
        cut = starts[first]
        earlier = bisect.bisect_right(boundaries, cut)
        cut = boundaries[earlier - 1] if earlier else 0

    return text[:cut] + _ANSWER_ELLIPSIS


def _limit_answers(df, story_name, warnings, answer_warnings):
    """Hold every step's answer to text only, and to a readable length.

    Runs on the answer exactly as the author typed it, ahead of the
    glossary pass, so the word count is the author's own words and the
    markup the cut protects is the markup they wrote rather than the
    anchors Telar injects.

    An answer over ANSWER_WORD_LIMIT is cut and reported. Length on its
    own earns no report: the build speaks where it has changed the
    author's words and stays quiet where it has not.

    The prose rules run first, so the count is of the words that survive
    them: a list of two hundred bulleted words is two hundred words, and a
    footnote the rules removed weighs nothing.
    """
    if 'answer' not in df.columns:
        return df

    story = story_name or 'unknown'

    for idx, row in df.iterrows():
        raw = str(row['answer'])
        if not raw.strip():
            continue

        step = row.get('step', 'unknown')
        label = _step_label(step)
        answer = raw

        answer, kinds = _reduce_answer_to_prose(answer)
        for kind in kinds:
            _report_answer(
                _ANSWER_KIND_KEYS[kind], step, answer_warnings, warnings,
                story=story, step_label=label)

        count = _count_answer_words(answer)
        if count > ANSWER_WORD_LIMIT:
            answer = _cut_answer(answer, ANSWER_WORD_LIMIT)
            _report_answer(
                'answer_over_hard_limit', step, answer_warnings, warnings,
                story=story, step_label=label, count=count,
                limit=ANSWER_WORD_LIMIT)

        if answer != raw:
            df.at[idx, 'answer'] = answer

    return df


def _report_answer(key, step, answer_warnings, warnings, step_label, **fields):
    """One localised report, to the build log and to the intro panel.

    The message is a whole sentence naming its own story and step, because
    the build log prints it with no context around it. It travels as a
    `panel` warning, the type the intro panel renders unprefixed.
    """
    message = get_lang_string('errors.object_warnings.' + key,
                              step=step_label, **fields)
    _warn(message, warnings)
    answer_warnings.append({'step': step, 'type': 'panel',
                            'message': message})


def _normalise_frame(df):
    """The shape every later pass assumes: no example column, no NaN, an
    alt_text column, and no rows that are entirely empty.
    """
    # Drop example column if it exists
    if 'example' in df.columns:
        df = df.drop(columns=['example'])

    # Clean up NaN values
    df = df.fillna('')

    # Ensure alt_text column exists for backward compatibility
    if 'alt_text' not in df.columns:
        df['alt_text'] = ''

    # Remove completely empty rows
    df = df[df.astype(str).apply(lambda x: x.str.strip()).ne('').any(axis=1)]
    return df


def _step_label(step):
    """The step as its author wrote it, not as pandas typed it.

    A page column with a blank in it makes pandas read the whole sheet's
    step numbers as floats, so a warning about step 1 said "step 1.0".
    Only the label is normalised; the offending value is quoted exactly as
    it was read, because that is the author's own data.
    """
    if isinstance(step, float) and step.is_integer():
        return str(int(step))
    return str(step)


def _report_step(step):
    """The step a report carries into the story JSON.

    A report takes its step from the frame, as numpy gives it when read
    with `df.at` (`int64`, which `json.dump` refuses, so the story was not
    written) or as a float when the column has a blank or a fraction (`1.0`,
    which the intro panel prints). A finite whole number becomes an int and
    a finite fraction a float. Anything else numpy or the author can put in
    the column -- `True`, `inf` -- is written as text, which `json.dump`
    takes and which is still valid JSON.
    """
    if (isinstance(step, numbers.Real) and not isinstance(step, bool)
            and math.isfinite(step)):
        return int(step) if float(step).is_integer() else float(step)
    return step if isinstance(step, str) else str(step)


def _page_value(raw, step, warnings):
    """One cell as a page number, or '' with a warning.

    float() runs first because a spreadsheet writes a whole number as
    3.0. OverflowError joins the caught set because it is what
    int(float('Infinity')) raises, and it is a sibling of ValueError
    rather than a subclass -- omitting it crashed the build on a cell a
    person can type by hand.
    """
    if not pd.notna(raw) or not str(raw).strip():
        return ''

    try:
        page = int(float(str(raw).strip()))
        if page < 1:
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        _warn(f"Story step {_step_label(step)}: invalid page value "
              f"'{raw}' (must be positive integer)", warnings)
        return ''

    return page


def _validate_page_column(df, warnings):
    """A page number is an integer or it is nothing.

    A step that names a page the story does not have would render
    nowhere, so an unusable value is cleared and said out loud rather
    than carried into the JSON.

    The column is rebuilt rather than written cell by cell, and that is
    the whole of why this function looks like this. pandas gives a column
    a dtype from what it read, and refuses a value of another type into
    it:

      - a column pandas read as text (one typo beside real page numbers)
        rejected the integer, so every *valid* page in that column was
        cleared and reported as invalid;
      - a column pandas read as numbers (a 0 from someone counting from
        zero, beside a blank) rejected the empty string used to clear it,
        and the TypeError escaped this function and stopped the build.

    Assigning the whole column at once replaces its dtype instead of
    fighting it, so neither case arises.
    """
    if 'page' not in df.columns:
        return df

    df['page'] = [_page_value(row.get('page', ''), row.get('step', 'unknown'),
                              warnings)
                  for _, row in df.iterrows()]
    return df


def _load_objects_data():
    """The built objects.json, keyed by id, or None when there is none.

    None and an empty mapping are different answers. A site that has not
    run the objects processor yet, or whose objects.json cannot be read,
    has nothing to check references against, and the reference pass is
    skipped rather than reporting every step as wrong. A site whose
    objects.json holds no objects has been checked and has none, so every
    object a story names is a reference to something absent.
    """
    objects_json_path = Path('_data/objects.json')
    if not objects_json_path.exists():
        return None
    try:
        with open(objects_json_path, 'r', encoding='utf-8') as f:
            objects_list = json.load(f)
            # Keyed by id, and only by records that have one. The objects
            # build drops a blank id before it writes this file, so its own
            # output never carries a null here; the guard is because this
            # reads a file from disk rather than a frame it produced, and the
            # matcher lowercases every key, which a null does not survive.
            return {obj['object_id']: obj for obj in objects_list
                    if isinstance(obj.get('object_id'), str) and obj['object_id']}
    except Exception as e:
        print(f"  [WARN] Could not load objects.json for validation: {e}")
        return None


def _check_object_has_a_source(df, idx, objects_data, actual_object_id,
                               file_index, step_num, warnings):
    """An object a step points at must resolve to something showable.

    A manifest, or a file beside it -- image or audio, since an audio
    object is shown by its player rather than by a picture. Neither is a
    warning on the step, not a failure: the story still renders, with a
    gap where the object would be.
    """
    # Check if object has IIIF manifest or local image
    obj = objects_data[actual_object_id]
    iiif_manifest = obj.get('iiif_manifest', '').strip()

    # If no external IIIF manifest, check for local image file
    if not iiif_manifest:
        # Check for a local image or audio file via the one-time index
        has_local_image = False

        for f in file_index.get(actual_object_id, []):
            suffix = f.suffix.lower()
            if suffix in IMAGE_EXTENSIONS:
                has_local_image = True
                print(f"  [INFO] Object {actual_object_id} uses local image: {f}")
                break
            if suffix in AUDIO_EXTENSIONS:
                has_local_image = True
                print(f"  [INFO] Object {actual_object_id} uses local audio: {f}")
                break

        # Only warn if object has neither external manifest nor local image
        if not has_local_image:
            error_msg = get_lang_string('errors.object_warnings.object_no_source', object_id=actual_object_id)
            df.at[idx, 'viewer_warning'] = error_msg
            msg = f"Story step {step_num} references object without IIIF source: {actual_object_id}"
            _warn(msg, warnings)

def _validate_object_references(df, objects_data, warnings):
    """Every `object` a step names must be one the site has.

    Lookups are case-insensitive and an accidental file extension is
    stripped, because both are what an author actually types. A missing
    reference becomes a viewer warning, which the story shows in its
    intro panel rather than failing the build.
    """
    # Add viewer_warning column if it doesn't exist
    if 'viewer_warning' not in df.columns:
        df['viewer_warning'] = ''

    # Validate object references
    if 'object' in df.columns and objects_data is not None:
        # Build case-insensitive lookup map for objects
        objects_lower_map = {k.lower(): k for k in objects_data.keys()}

        # Shared canonical extension set for stripping object references.
        strippable_extensions = IMAGE_EXTENSIONS

        # Index telar-content/objects once so the per-reference local-file check
        # is an O(1) lookup instead of an iterdir scan per story step.
        _obj_file_index = build_stem_index('telar-content/objects')

        for idx, row in df.iterrows():
            object_id = str(row.get('object', '')).strip()
            step_num = row.get('step', 'unknown')

            # Skip if no object specified
            if not object_id:
                continue

            # Strip file extensions from object references (users may type "photo.jpg" instead of "photo")
            for ext in strippable_extensions:
                if object_id.lower().endswith(ext):
                    stripped_id = object_id[:-len(ext)]
                    print(f"  [INFO] Stripped extension from story object reference: '{object_id}' -> '{stripped_id}'")
                    object_id = stripped_id
                    df.at[idx, 'object'] = object_id
                    break

            # Check if object exists (case-insensitive)
            actual_object_id = None
            if object_id in objects_data:
                # Exact match
                actual_object_id = object_id
            elif object_id.lower() in objects_lower_map:
                # Case-insensitive match - use the correct-case version
                actual_object_id = objects_lower_map[object_id.lower()]
                # Update the DataFrame with correct case
                df.at[idx, 'object'] = actual_object_id

            if actual_object_id is None:
                error_msg = get_lang_string('errors.object_warnings.object_not_found', object_id=object_id)
                df.at[idx, 'viewer_warning'] = error_msg
                msg = f"Story step {step_num} references missing object: {object_id}"
                _warn(msg, warnings)
                continue

            _check_object_has_a_source(df, idx, objects_data,
                                       actual_object_id, _obj_file_index,
                                       step_num, warnings)
    return df


def _layer_content_for(cell_value, widget_warnings):
    """One layer cell as content, from a file or from the cell itself.

    A value ending in `.md` names a file; anything else is prose typed
    into the spreadsheet. A filename that tries to leave the texts
    directory is not read at all -- it falls through to inline
    processing, so the worst an author can do to themselves is publish
    their own path as text.
    """
    content_data = None
    # Check if this looks like a file reference (.md extension)
    if cell_value.endswith('.md'):
        # Reject path-traversal in the author-controlled filename
        # before joining it onto stories/. A value that tries to
        # escape the texts directory falls through to inline
        # processing rather than reading an arbitrary file.
        if '..' in cell_value or cell_value.startswith('/') or '\\' in cell_value:
            print(f"  [WARN] Ignoring unsafe layer file reference '{cell_value}' "
                  f"(path traversal) — treating as inline content")
        else:
            # Try to load as markdown file
            file_path = f"stories/{cell_value}"
            content_data = read_markdown_file(file_path, widget_warnings)

    # If not a file reference or file not found, treat as inline content
    if content_data is None:
        content_data = process_inline_content(cell_value, widget_warnings)
    return content_data

def _process_content_columns(df, glossary_terms, glossary_warnings, widget_warnings):
    """Turn every layer column into HTML, from a file or from the cell.

    A value ending in `.md` names a file under telar-content/texts;
    anything else is prose typed into the spreadsheet. Both run the same
    pipeline -- widgets, then images, then markdown -- so a panel reads
    the same either way. The legacy `_file` column names are still
    accepted.
    """
    # Also handles legacy _file suffix for backward compatibility
    for col in df.columns:
        if col.endswith('_content') or col.endswith('_file'):
            # Determine the base name (e.g., 'layer1' from 'layer1_content' or 'layer1_file')
            if col.endswith('_content'):
                base_name = col.replace('_content', '')
            else:
                base_name = col.replace('_file', '')

            # Create new columns for title and text
            title_col = f'{base_name}_title'
            text_col = f'{base_name}_text'

            # Initialize new columns with empty strings
            if title_col not in df.columns:
                df[title_col] = ''
            if text_col not in df.columns:
                df[text_col] = ''

            # Read markdown files or process inline content
            for idx, row in df.iterrows():
                cell_value = row[col]
                if cell_value and str(cell_value).strip():
                    cell_value = str(cell_value).strip()
                    step_num = row.get('step', 'unknown')

                    content_data = _layer_content_for(
                        cell_value, widget_warnings)

                    if content_data:
                        df.at[idx, title_col] = content_data['title']
                        # Apply glossary link transformation to content
                        content_with_glossary = process_glossary_links(
                            content_data['content'],
                            glossary_terms,
                            glossary_warnings,
                            step_num,
                            base_name
                        )
                        df.at[idx, text_col] = content_with_glossary

            # Drop the _content/_file column: it is not part of the JSON output
            df = df.drop(columns=[col])
    return df


def _resolve_answer_glossary(df, glossary_terms, glossary_warnings):
    """Resolve [[term]] in the step's answer prose.

    The answer only. The question is the step's heading, and an inline
    link does not belong in one, so [[term]] there is left literal. The
    answer is still markdown at this point -- Liquid renders it later --
    so the transform runs on the markdown string, and the anchor it
    injects passes through markdownify unchanged.
    """
    # None because this is step prose, not a layer panel.
    if 'answer' in df.columns:
        for idx, row in df.iterrows():
            cell_value = row['answer']
            if cell_value and str(cell_value).strip():
                step_num = row.get('step', 'unknown')
                df.at[idx, 'answer'] = process_glossary_links(
                    str(cell_value),
                    glossary_terms,
                    glossary_warnings,
                    step_num,
                    None,
                    markdown=True
                )
    return df


# Maths in an answer, in the forms KaTeX draws, and whether each keeps its
# delimiters. kramdown, which renders the answer, eats the backslash of
# \( \) \[ \] and reads `*` and `_` inside $...$ as emphasis; its own $$...$$
# is the one form whose content it prints as written, as \(...\) inside a
# paragraph and \[...\] as a paragraph of its own. Earliest match wins, and at
# one position the first pattern listed. Single $ follows `has_latex`: a
# LaTeX character inside, no space inside either dollar, neither escaped.
_ANSWER_MATHS = (
    (re.compile(r'\$\$.+?\$\$', re.DOTALL), None),
    # An opening that is never closed must not pair with a later formula, and
    # stopping at the next opening keeps the search linear in the answer.
    (re.compile(r'\\begin\{(align\*?|cases|pmatrix|bmatrix|equation\*?)\}'
                r'(?:(?!\\begin\{\1\}).)*?\\end\{\1\}', re.DOTALL), 0),
    (re.compile(r'\\\[((?:(?!\\\[).)+?)\\\]', re.DOTALL), 1),
    (re.compile(r'\\\(((?:(?!\\\().)+?)\\\)', re.DOTALL), 1),
    (re.compile(r'(?<![\\$])\$(?!\$)(\S(?:[^$]*?[^\s\\])?)\$(?!\$)'), 1),
)
# A destination may hold one level of balanced parentheses, as kramdown allows.
_LINK_DESTINATION = re.compile(r'\]\((?:[^()]|\([^()]*\))*\)')


def _escape_stray_dollars(text):
    """*text* with each `$$` kramdown prints as it is written `\\$\\$`, which
    it still prints as `$$` but which cannot pair with a formula written as
    `$$…$$` after it in the same paragraph. A backslash kramdown drops
    before one goes with it."""
    out = []
    pos = 0
    for start, end in stray_dollars(text):
        out.append(text[pos:start] + '\\$\\$')
        pos = end
    out.append(text[pos:])
    return ''.join(out)


def _answer_maths_for_kramdown(text):
    """*text* with each maths span written as kramdown's $$...$$.

    Left as written: maths inside a code span, a code element, an HTML
    element kramdown leaves raw, an HTML tag or a link destination, since
    none of those is maths on the page; a
    $...$ with no LaTeX character, which is currency; and a span holding
    another dollar, which is one formula inside another and has no single
    reading.
    """
    text = _escape_stray_dollars(text)
    guarded = overlaps(raw_regions(text) + code_elements(text)
                       + [(m.start(), m.end()) for m in _HTML_TAG.finditer(text)]
                       + [(m.start(), m.end()) for m in _LINK_DESTINATION.finditer(text)])
    # Each pattern's next match from the current position, searched again
    # only once the position passes it, so a long answer is scanned once
    # per pattern rather than once per formula.
    upcoming = [pattern.search(text) for pattern, _ in _ANSWER_MATHS]
    out = []
    pos = 0
    while True:
        for order, (pattern, _) in enumerate(_ANSWER_MATHS):
            if upcoming[order] is not None and upcoming[order].start() < pos:
                upcoming[order] = pattern.search(text, pos)
        found = [(match.start(), order) for order, match in enumerate(upcoming) if match]
        if not found:
            break
        _, order = min(found)
        match, group = upcoming[order], _ANSWER_MATHS[order][1]
        start, end = match.span()
        out.append(text[pos:start])
        span = text[start:end]
        if group is not None and not guarded(start, end):
            inner = match.group(group)
            if '$' not in inner and (group == 0 or not span.startswith('$')
                                     or _LATEX_CHARS.search(inner)):
                span = f'$${inner}$$'
        out.append(span)
        pos = end
    out.append(text[pos:])
    return ''.join(out)


def _maths_pipes(maths):
    """A `$$…$$` span with each `|` as `\\vert `, which KaTeX draws as the
    same glyph; TeX's double bar `\\|` stays."""
    return '\\|'.join(part.replace('|', '\\vert ') for part in maths.split('\\|'))


_REGION_PIPES = {
    'maths': _maths_pipes,
    'cdata': lambda cdata: cdata.replace('|', ']]>&#124;<![CDATA['),
}


def _answer_pipes_for_kramdown(text):
    """*text* with every pipe kramdown would read as a table cell escaped.

    kramdown reads a line holding a `|` as a table row. So a pipe in prose,
    and an author's `\\|`, becomes `&#124;`, which prints a bare pipe. Code
    and `$$…$$` are printed as written, so an entity there would reach the
    reader as text: a pipe in code is left alone, and one in maths becomes
    `\\vert `. kramdown does not look for a table row inside an HTML
    element, and an element it leaves raw is printed as written, so a pipe
    there is left alone too: in a `<script>` an entity would change the
    code. CDATA is the exception: its text counts as the line's, and it
    prints an entity as written, so the CDATA is closed around the pipe
    and the entity put between. All of these are found as kramdown finds
    them (`telar.code_spans`).
    """
    if '|' not in text:
        return text
    out = []
    pos = 0
    for kind, start, end in answer_regions(text):
        out.append(text[pos:start].replace('\\|', '&#124;').replace('|', '&#124;'))
        out.append(_REGION_PIPES.get(kind, str)(text[start:end]))
        pos = end
    out.append(text[pos:].replace('\\|', '&#124;').replace('|', '&#124;'))
    return ''.join(out)


def _prepare_answer_maths(df):
    """Add `answer_kramdown` where an answer needs rewriting for kramdown.

    Two rewrites, in order: each formula as `$$…$$`, then each pipe
    escaped for its place (prose, code or maths). `answer` stays the
    build's reading of the cell: title cards and the card fallback show it
    as text, and the Compositor mirrors it. Only story-step.html renders the
    rewritten form. The column is added only to a story where some answer
    changes, so a story without maths or pipes publishes the same data as
    before.
    """
    if 'answer' not in df.columns:
        return df
    answers = [value if isinstance(value, str) else '' for value in df['answer']]
    rewritten = [_answer_pipes_for_kramdown(_answer_maths_for_kramdown(answer))
                 for answer in answers]
    if rewritten != answers:
        df['answer_kramdown'] = [new if new != answer else ''
                                 for new, answer in zip(rewritten, answers)]
    return df


def _apply_coordinate_defaults(df):
    """A viewer needs somewhere to start, so empty coordinates get one."""
    # Set default coordinates for empty values
    coordinate_defaults = {'x': '0.5', 'y': '0.5', 'zoom': '1'}
    for col, default in coordinate_defaults.items():
        if col in df.columns:
            # Blank cells are '' by now. A typed `nan` is text like `NA`,
            # and is reported by the coordinate check, not defaulted.
            df[col] = df[col].astype(str)
            df.loc[df[col] == '', col] = default
    return df


# A decimal typed with a comma, the way a Spanish-speaking author writes one:
# `0,5` or `-1,25`. One comma between digits, nothing else.
_COMMA_DECIMAL = re.compile(r'^\s*(-?\d+),(\d+)\s*$')


def _check_coordinates(df, story_name, warnings, coordinate_warnings):
    """Read a comma decimal as a number, and report a cell that is neither.

    Runs after the defaults, so every blank already holds one and what is
    left is what the author typed. A comma decimal says a number plainly,
    so it is rewritten with a point and nothing is reported. Anything else
    that does not read as a finite number is reported and left as typed:
    rewriting it would make the page look right while the sheet stayed
    wrong, and the viewer's own fallback keeps the step usable meanwhile.
    """
    story = story_name or 'unknown'
    for col in ('x', 'y', 'zoom'):
        if col not in df.columns:
            continue
        for idx, raw in df[col].items():
            value = str(raw)
            comma = _COMMA_DECIMAL.match(value)
            if comma:
                df.at[idx, col] = f'{comma.group(1)}.{comma.group(2)}'
                continue
            try:
                if math.isfinite(float(value)):
                    continue
            except ValueError:
                pass
            step = df.at[idx, 'step'] if 'step' in df.columns else 'unknown'
            message = get_lang_string(
                'errors.object_warnings.coordinate_not_a_number',
                column=col, step=_step_label(step), story=story,
                value=html.escape(value.strip()).replace('`', "'"))
            _warn(message, warnings)
            coordinate_warnings.append({'step': step, 'type': 'panel',
                                        'message': message})
    return df


def _collect_step_warnings(df):
    """Everything the intro panel will show, gathered from the columns.

    These live in df.attrs rather than in a column: they belong to the
    story, not to any one step, and the JSON writer reads them from
    there.
    """
    # Collect all warnings for intro display
    all_warnings = []
    for idx, row in df.iterrows():
        step_num = row.get('step', 'unknown')

        # Check for viewer warnings (missing object/IIIF)
        viewer_warning = row.get('viewer_warning', '').strip()
        if viewer_warning:
            all_warnings.append({
                'step': step_num,
                'type': 'viewer',
                'message': viewer_warning
            })

        # Check for panel content warnings (missing markdown files)
        # Look for "Content Missing" title which indicates missing files
        content_missing_label = get_lang_string('errors.object_warnings.content_missing_label')
        for layer in ['layer1', 'layer2']:
            title_col = f'{layer}_title'
            if title_col in row and row[title_col] == content_missing_label:
                # Extract the filename from the error HTML in the text column
                text_col = f'{layer}_text'
                text = row.get(text_col, '')
                # Extract filename from the HTML (it's between <strong> tags)
                filename_match = re.search(r'<strong>(.*?)</strong>', text)
                # Get layer number for display (1 or 2)
                layer_num = layer[-1]  # Get '1' or '2' from 'layer1' or 'layer2'
                if filename_match:
                    # Extract content_file_missing message from HTML
                    message = filename_match.group(1)
                    all_warnings.append({
                        'step': step_num,
                        'type': 'panel',
                        'message': message
                    })
                else:
                    # Fallback if regex fails
                    all_warnings.append({
                        'step': step_num,
                        'type': 'panel',
                        'message': get_lang_string('errors.object_warnings.layer_file_missing', layer_num=layer_num)
                    })
    return all_warnings


def _detect_latex(df):
    """Whether any step carries LaTeX, so the page can load the renderer.

    Scans every surface the markdown-syntax docs promise LaTeX works in:
    the question and answer prose, and the resolved layer text.
    """
    # question/answer prose and resolved layer content (*_text columns).
    latex_detected = False
    for idx, row in df.iterrows():
        for col in df.columns:
            if col in ('question', 'answer') or col.endswith('_text'):
                text = str(row.get(col, ''))
                if text and has_latex(text):
                    latex_detected = True
                    break
        if latex_detected:
            break

    return latex_detected


def _add_christmas_tree_warnings(df, all_warnings):
    """Every warning kind at once, so the intro panel can be looked at.

    Appended rather than substituted: the point is to see them beside
    whatever the story really produced.
    """
    # Every message here is one the build really emits, because the point of
    # this mode is to look at the warnings as an author would see them. A
    # message written only for the demonstration shows something no story can
    # produce, and is a string nothing else keeps honest.
    fake_warnings = [
        {
            'step': 1,
            'type': 'viewer',
            'message': get_lang_string('errors.object_warnings.object_not_found',
                                       object_id='an-object-not-in-objects-csv')
        },
        {
            'step': 2,
            'type': 'panel',
            'message': get_lang_string('errors.object_warnings.content_file_missing', file_ref='missing-file.md')
        },
        {
            'step': 3,
            'type': 'glossary',
            'term_id': 'nonexistent-term',
            'message': get_lang_string('errors.object_warnings.glossary_term_not_found', term_id='nonexistent-term')
        }
    ]
    # Add fake warnings to existing warnings
    df.attrs['viewer_warnings'] = all_warnings + fake_warnings
    print("\U0001f384 Christmas Tree Mode: Injected test warnings into story")

def process_story(df, christmas_tree=False, story_name=''):
    """
    Process story CSV with panel content (file references or inline text).

    Expected columns: step, question, answer, object, x, y, zoom,
    layer1_content, layer2_content, etc.
    (Also accepts legacy column names: layer1_file, layer2_file)

    Args:
        df: pandas DataFrame from story CSV
        christmas_tree: If True, inject fake warnings for testing
        story_name: The story's name, for warnings that have to say which
            story they are about. A DataFrame carries no such name, so the
            caller supplies it; a caller that has none gets warnings that
            say 'unknown', which is the step column's own fallback.

    Returns:
        pandas DataFrame with processed content and aggregated warnings
    """
    # One function per pass, in the order the module docstring lists
    # them. Three accumulators are shared, and only as accumulators:
    # `warnings` is what the summary counts, and the other two are
    # filled by passes that cannot reach df.attrs themselves.
    warnings = []
    glossary_terms = load_glossary_terms()
    glossary_warnings = []
    widget_warnings = []
    answer_warnings = []

    df = _normalise_frame(df)
    df = _limit_answers(df, story_name, warnings, answer_warnings)
    df = _validate_page_column(df, warnings)
    df = _validate_object_references(df, _load_objects_data(), warnings)
    df = _process_content_columns(df, glossary_terms, glossary_warnings,
                                  widget_warnings)
    df = _resolve_answer_glossary(df, glossary_terms, glossary_warnings)
    df = _prepare_answer_maths(df)
    df = _apply_coordinate_defaults(df)
    coordinate_warnings = []
    df = _check_coordinates(df, story_name, warnings, coordinate_warnings)

    all_warnings = _collect_step_warnings(df)
    all_warnings.extend(coordinate_warnings)
    all_warnings.extend(glossary_warnings)
    all_warnings.extend(widget_warnings)
    all_warnings.extend(answer_warnings)
    for report in all_warnings:
        if 'step' in report:
            report['step'] = _report_step(report['step'])
    df.attrs['viewer_warnings'] = all_warnings

    df.attrs['has_latex'] = _detect_latex(df)

    if christmas_tree:
        _add_christmas_tree_warnings(df, all_warnings)

    # Print summary if there were issues
    if warnings:
        print(f"\n  Story validation summary: {len(warnings)} warning(s)")

    # Order steps by their authored `step` number so the rendered sequence
    # follows the step values, not the spreadsheet's physical row order — a CSV
    # exported out of order (e.g. by an external editor) would otherwise render
    # steps in the wrong sequence. Failsafe: a stable sort keeps rows that share
    # a step value in their original order, blank or non-numeric steps fall to
    # the end, and any unexpected error leaves the original row order untouched
    # rather than breaking the build.
    if 'step' in df.columns:
        try:
            step_order = pd.to_numeric(df['step'], errors='coerce')
            df = (df.assign(_step_order=step_order)
                    .sort_values('_step_order', kind='mergesort', na_position='last')
                    .drop(columns='_step_order')
                    .reset_index(drop=True))
        except Exception as e:
            print(f"  [WARN] Could not order story steps by 'step' value; "
                  f"using spreadsheet row order instead ({e})")

    return df

