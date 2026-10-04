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
   markdown-to-HTML conversion, during which glossary links (`[[term_id]]`
   syntax) are resolved by `process_glossary_links()`.

3. **Answers** -- the step's `answer` is rendered to the HTML the story
   publishes, by `render_answer()`: it renders as panels do, is made prose
   (widgets, media, tables, code blocks, rules and footnotes come out;
   headings, quotes and lists become paragraphs), gets glossary links, and
   is held to the budget in `telar.answer_budget`, the length that fits the
   side card without scrolling. An answer over it is cut. The `question`
   is a heading and is left as written.

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

import html
import math
import numbers
import re
import json
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from telar.answer_budget import (ANSWER_BUDGET, MAX_PARAGRAPHS, PARAGRAPH_COST, Measure,
                                 cut_to_budget, html_tokens, measure_answer, within_budget)
from telar.config import get_lang_string
from telar.glossary import load_glossary_terms, process_glossary_links
from telar.markdown import process_inline_content, read_markdown_file, render_markdown
from telar.csv_utils import IMAGE_EXTENSIONS, build_stem_index
from telar.latex import has_latex
from telar.media_type import AUDIO_EXTENSIONS


def _warn(msg, warnings):
    """Print a WARN-prefixed message and record it in the warnings list."""
    print(f"  [WARN] {msg}")
    warnings.append(msg)



ANSWER_MEDIA = 'media'
ANSWER_WIDGETS = 'widgets'
ANSWER_FOOTNOTES = 'footnotes'
ANSWER_MARKUP = 'markup'

# The order warnings are reported in, one per answer per kind.
ANSWER_KINDS = (ANSWER_MEDIA, ANSWER_WIDGETS, ANSWER_FOOTNOTES, ANSWER_MARKUP)

# What each kind is called in the message catalogue.
_ANSWER_KIND_KEYS = {
    ANSWER_MEDIA: 'answer_image_dropped',
    ANSWER_WIDGETS: 'answer_widget_dropped',
    ANSWER_FOOTNOTES: 'answer_footnotes_dropped',
    ANSWER_MARKUP: 'answer_markup_flattened',
}


def _line_starts(text):
    """The index at which each line of *text* begins."""
    starts = [0]
    pos = text.find('\n')
    while pos != -1:
        starts.append(pos + 1)
        pos = text.find('\n', pos + 1)
    return starts



_WIDGET_OPEN = re.compile(r'[ \t]*:::[A-Za-z0-9_]+[ \t]*\n')
_WIDGET_CLOSE = re.compile(r'[ \t]*:::[ \t]*(?=\n|\Z)')


def _remove_widget_blocks(text):
    """*text* without its widget blocks, and how many were removed.

    An opening is a line of optional blanks, `:::`, a name of letters,
    digits and underscores, and optional blanks. The block ends after the
    first later line that is `:::` alone between optional blanks, and one
    optional newline. An opening with no such line after it opens nothing.
    Reading resumes on the first line start after the block.
    """
    starts = _line_starts(text)
    total = len(starts)
    # next_close[i] is the first line from i on that is `:::` alone.
    next_close = [total] * (total + 1)
    for i in range(total - 1, -1, -1):
        next_close[i] = i if _WIDGET_CLOSE.match(text, starts[i]) \
            else next_close[i + 1]

    pieces = []
    kept = 0
    removed = 0
    i = 0
    while i < total - 1:
        if _WIDGET_OPEN.match(text, starts[i]) and next_close[i + 1] < total:
            j = next_close[i + 1]
            end = _WIDGET_CLOSE.match(text, starts[j]).end()
            if text[end:end + 1] == '\n':
                end += 1
            pieces.append(text[kept:starts[i]])
            kept = end
            removed += 1
            i = j + 1
        else:
            i += 1
    pieces.append(text[kept:])
    return ''.join(pieces), removed


# Elements a step's answer loses with everything inside them, by the kind
# each is reported as. A void element among them has nothing inside.
_ANSWER_DROPPED = {
    'img': ANSWER_MEDIA, 'iframe': ANSWER_MEDIA, 'video': ANSWER_MEDIA,
    'audio': ANSWER_MEDIA, 'embed': ANSWER_MEDIA, 'object': ANSWER_MEDIA,
    'table': ANSWER_MARKUP, 'pre': ANSWER_MARKUP, 'hr': ANSWER_MARKUP,
}
_ANSWER_HEADINGS = frozenset(f'h{level}' for level in range(1, 7))
_ANSWER_UNWRAPPED = frozenset({'blockquote', 'ul', 'ol'})
# The two pieces the footnotes extension writes: a reference's `<sup>` and
# the notes' `<div>`.
_FOOTNOTE_PART = re.compile(r'<(?:sup\b[^>]*\bid="fnref|div\b[^>]*\bclass="footnote")')
_EMPTY_PARAGRAPH = re.compile(r'<p\b[^>]*>\s*</p>\n?')


class _AnswerProse:
    """A step's rendered answer as prose: `html`, and the `kinds` of thing
    that came out of it.

    Media, tables, code blocks, horizontal rules and footnotes are removed
    with what is inside them. A heading becomes a paragraph, a quote and a
    list lose their container, and each list item becomes a paragraph, so
    their words stay. A paragraph left empty is removed. Everything else --
    emphasis, links, code spans, line breaks, raw inline HTML -- is kept as
    rendered.
    """

    def __init__(self, rendered):
        self.out, self.kinds = [], set()
        self._dropping = None
        self._items = []
        for token in html_tokens(rendered):
            self._take(token)
        self.html = _EMPTY_PARAGRAPH.sub('', ''.join(self.out))

    def _take(self, token):
        if self._dropping:
            self._skip(token)
        elif self._drops(token):
            return
        elif token.name in _ANSWER_HEADINGS:
            self.kinds.add(ANSWER_MARKUP)
            self._end_item()
            self.out.append('<p>' if token.kind == 'start' else '</p>')
        elif token.name in _ANSWER_UNWRAPPED:
            self.kinds.add(ANSWER_MARKUP)
            self._end_item()
        elif token.name == 'li':
            self._list_item(token)
        else:
            if token.name == 'p' and token.kind == 'start':
                self._end_item()
            self.out.append(token.raw)

    def _drops(self, token):
        """Whether *token* opens or is something the answer loses."""
        if token.kind not in ('start', 'void', 'end'):
            return False
        kind = _ANSWER_DROPPED.get(token.name)
        if kind is None and token.kind == 'start' and _FOOTNOTE_PART.match(token.raw):
            kind = ANSWER_FOOTNOTES
        if kind is None:
            return False
        self.kinds.add(kind)
        if token.kind == 'start':
            self._dropping = [token.name, 1]
        return True

    def _skip(self, token):
        name, depth = self._dropping
        if token.name != name:
            return
        depth += 1 if token.kind == 'start' else -1 if token.kind == 'end' else 0
        self._dropping = [name, depth] if depth else None

    def _list_item(self, token):
        self.kinds.add(ANSWER_MARKUP)
        if token.kind == 'start':
            self._end_item()
            self.out.append('<p>')
            self._items.append(True)
        elif self._items and self._items.pop():
            self.out.append('</p>')

    def _end_item(self):
        """Close the paragraph a list item opened, before a block inside it."""
        if self._items and self._items[-1]:
            self.out.append('</p>')
            self._items[-1] = False


class RenderedAnswer(NamedTuple):
    """A step's answer as the build publishes it (`render_answer`).

    `html` is the published answer. `kinds` names what came out of it, in
    ANSWER_KINDS order. `measure` is the answer's words, paragraphs and
    cost before any cut (`telar.answer_budget`), and `cut` says whether it
    was over ANSWER_BUDGET and so cut.
    """
    html: str
    kinds: list
    measure: Measure
    cut: bool


def render_answer(text, glossary_terms=None, glossary_warnings=None, step=None,
                  source='answer'):
    """A step's answer, as written, rendered to the HTML the build publishes.

    Widget blocks are removed from the text. The rest renders as every
    piece of author markdown does (`render_markdown`), and then, while its
    maths is still held out of the HTML: it is made prose (`_AnswerProse`),
    `[[term]]` becomes a glossary link as in a panel, and an answer over
    ANSWER_BUDGET is cut (`telar.answer_budget`). The cut runs last, so it
    counts the words a reader sees and never splits a glossary link.

    Args:
        text: The answer as the author wrote it.
        glossary_terms: The glossary's term ids and titles, or None.
        glossary_warnings: A list for glossary reports, or None.
        step: The step, for glossary reports.
        source: What a warning about unclosed HTML calls the answer.

    Returns:
        RenderedAnswer
    """
    text = str(text).replace('\r\n', '\n').replace('\r', '\n').strip()
    text, widgets = _remove_widget_blocks(text)
    found = {}

    def to_prose(rendered):
        prose = _AnswerProse(rendered)
        linked = process_glossary_links(prose.html, glossary_terms,
                                        glossary_warnings, step, None)
        found['kinds'], found['measure'] = prose.kinds, measure_answer(linked)
        return cut_to_budget(linked)

    published = render_markdown(text, source, post_process=to_prose)
    kinds = found['kinds'] | ({ANSWER_WIDGETS} if widgets else set())
    return RenderedAnswer(published, [kind for kind in ANSWER_KINDS if kind in kinds],
                          found['measure'], not within_budget(found['measure']))


def _render_answers(df, story_name, glossary_terms, glossary_warnings, warnings,
                    answer_warnings):
    """Every step's answer rendered to the HTML published in its `answer`.

    What `render_answer` took out of an answer is reported once per kind,
    and an answer over the budget is reported with its count, naming the
    story and step: the build speaks where it has changed the author's
    words and stays quiet where it has not.
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
        rendered = render_answer(raw, glossary_terms, glossary_warnings, step,
                                 source=f'the answer to step {label} of {story}')
        for kind in rendered.kinds:
            _report_answer(_ANSWER_KIND_KEYS[kind], step, answer_warnings, warnings,
                           story=story, step_label=label)
        if rendered.cut:
            counted = rendered.measure
            _report_answer('answer_over_hard_limit', step, answer_warnings, warnings,
                           story=story, step_label=label, count=counted.cost,
                           limit=ANSWER_BUDGET, max_paragraphs=MAX_PARAGRAPHS, words=counted.words,
                           paragraphs=counted.paragraphs, paragraph_cost=PARAGRAPH_COST)
        df.at[idx, 'answer'] = rendered.html
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


def _layer_content_for(cell_value, widget_warnings, post_process=None):
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
            content_data = read_markdown_file(file_path, widget_warnings, post_process)

    # If not a file reference or file not found, treat as inline content
    if content_data is None:
        content_data = process_inline_content(cell_value, widget_warnings, post_process)
    return content_data

def _glossary_linker(glossary_terms, glossary_warnings, step_num, layer):
    """The pass that makes a panel's glossary links, given its rendered
    HTML while the maths is still held out of it."""
    return lambda rendered: process_glossary_links(
        rendered, glossary_terms, glossary_warnings, step_num, layer)


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
                        cell_value, widget_warnings,
                        _glossary_linker(glossary_terms, glossary_warnings,
                                         step_num, base_name))

                    if content_data:
                        df.at[idx, title_col] = content_data['title']
                        df.at[idx, text_col] = content_data['content']

            # Drop the _content/_file column: it is not part of the JSON output
            df = df.drop(columns=[col])
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
    df = _validate_page_column(df, warnings)
    df = _validate_object_references(df, _load_objects_data(), warnings)
    df = _process_content_columns(df, glossary_terms, glossary_warnings,
                                  widget_warnings)
    df = _render_answers(df, story_name, glossary_terms, glossary_warnings,
                         warnings, answer_warnings)
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

