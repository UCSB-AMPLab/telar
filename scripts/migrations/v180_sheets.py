"""
Spreadsheets Before the First 1.8.0 Build

This module deals with the two things `v170_to_v180` checks in a site's
spreadsheets before regeneration runs: columns that claim one name, which
the build now refuses, and step answers the build will cut or strip.

**Colliding columns** (`repair_colliding_columns`). A sheet headed both
`medium` and `object_type` has two columns the build reads as one field.
Up to 1.7.0 the last one won, silently; from 1.8.0 the conversion refuses
the sheet and exits non-zero, which the engine treats as a hard failure, so
the site would stay at 1.7.0. Where the collision is benign, one column
holding values and the others empty, this repairs it by deleting the empty
ones, and says which column now holds the values. The rule is shared with
the Compositor's import:

  - a column is empty if every data row holds nothing after trimming;
    comment rows and a bilingual second header row are not data, and a
    column whose header starts with `#` is never a candidate;
  - columns collide on the terms `_refuse_colliding_renames` uses: the
    mapped name, or the header lowercased and trimmed;
  - exactly one holds values: keep it, drop the others;
  - none holds values: keep the one spelled as the canonical name, else
    the first in file order;
  - more than one holds values: drop nothing, and report, since only the
    author can say which is meant.

A removal may not change the rows the build reads as data. The build drops
a row whose first cell starts with `#` as a comment, then drops the `#`
columns, then judges whether the first row left is a bilingual header row,
so removing a column, the first above all, can turn a step into a comment
or change which row counts as a header. Each removal is checked against
those rules, over the columns that survive it. An empty first column whose
removal would change the rows is kept, with `#` put before its header, so
the build ignores it after reading the comment rows; any other removal
that would change them is not made, and reported.

Each sheet is read with the scoping the build reads it with: the project
and story sheets with the whole alias map, the objects sheet with the map
scoped to the fields objects have, and the glossary with the whole map
plus the aliases only the glossary reads.

**Step answers** (`report_step_answers`). Nothing is written. The build
holds an answer to prose and to `ANSWER_WORD_LIMIT` words, and this counts
each answer with the build's own functions so the author learns where they
ran the upgrade, rather than on the published site, which answers will be
cut and which will lose widgets, media, footnotes or markup.

Both import the build's rules from `telar` lazily. The engine runs from the
release's tooling, whose `scripts/` holds the matching `telar` package, but
pandas is installed only after migrations run, so an import that fails is a
soft record saying the build will report the same thing.

Version: v1.8.0
"""

import contextlib
import csv
import importlib
import io
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

import yaml

from .messages import get_message
from .records import ChangeCategory, ChangeRecord, ChangeStatus


SPREADSHEETS_DIR = 'telar-content/spreadsheets'

# The sheets the build reads as something other than a story, as the English
# and Spanish filenames `find_csv_with_fallback` looks for, English first.
PROJECT_SHEETS = ('project.csv', 'proyecto.csv')
OBJECTS_SHEETS = ('objects.csv', 'objetos.csv')
GLOSSARY_SHEETS = ('glossary.csv', 'glosario.csv')

_BOM = '﻿'


def _record(lang, key, *args, status=ChangeStatus.APPLIED) -> ChangeRecord:
    return ChangeRecord(description=get_message(lang, key, *args), status=status,
                        severity='soft', category=ChangeCategory.OTHER)


# ---------------------------------------------------------------------- #
# Reading a sheet the way the build does
# ---------------------------------------------------------------------- #

class Sheet:
    """One CSV as the build reads it, and as the bytes it is stored in.

    `rows` are the cells of every record as `csv` reads them, and `skipped`
    says which of them pandas skips as a blank line. The header is the
    first record pandas does not skip, and `body` the records after it that
    it does not skip. `labels` are the column names as pandas gives them to
    the build, suffixes for repeated headers included. `records` holds each
    record's fields as the exact text they were written in, with the
    terminator that ended the record, so a repair can take one field and
    its delimiter out of a record and leave every other byte as it was:
    quoting, spacing, CR, LF or CRLF, a BOM, a skipped line.

    `records` is None when the file cannot be split that way with
    certainty, which is when the split does not read back as the same
    cells `csv` reads. Such a file is never written.
    """

    def __init__(self, path: str, text: Optional[str] = None):
        if text is None:
            with open(path, 'r', encoding='utf-8', newline='') as handle:
                text = handle.read()
        self.path = path
        self.bom = text.startswith(_BOM)
        text = text[len(_BOM):] if self.bom else text
        with _field_limit_lifted():
            self.rows = list(csv.reader(io.StringIO(text, newline='')))
        self.records = split_records(text)
        if self.records is not None and [_cells(f) for f, _ in self.records] != self.rows:
            self.records = None
        if self.records is None:
            self.skipped = [_skipped_row(row) for row in self.rows]
        else:
            self.skipped = [_skipped_fields(fields) for fields, _ in self.records]
        self.header_at = next((index for index, skipped in enumerate(self.skipped)
                               if not skipped), len(self.rows))
        self.labels = pandas_labels(self.header, text)

    @property
    def header(self) -> List[str]:
        return self.rows[self.header_at] if self.header_at < len(self.rows) else []

    @property
    def body(self) -> List[List[str]]:
        """The records after the header that pandas reads as rows."""
        return [row for index, row in enumerate(self.rows)
                if index > self.header_at and not self.skipped[index]]

    def edited(self, indices=(), mark_first=False) -> Optional[str]:
        """The file's text with the fields at *indices* gone from every
        record pandas reads, and with `#` put before the header's first
        field when *mark_first* is set, or None when it cannot be edited
        that safely. A line pandas skips is written back as it was.

        The mark goes inside the quotes of a quoted field, so `"note"`
        becomes `"#note"` and `note` becomes `#note`; no other byte moves.
        """
        if self.records is None or not self.header or (mark_first and 0 in indices):
            return None
        doomed = set(indices)
        records = [(list(fields), ending) for fields, ending in self.records]
        if mark_first:
            first = records[self.header_at][0][0]
            records[self.header_at][0][0] = (
                '"#' + first[1:] if first.startswith('"') else '#' + first)
        body = ''.join(','.join(field for index, field in enumerate(fields)
                                if skipped or index not in doomed) + ending
                       for (fields, ending), skipped in zip(records, self.skipped))
        return (_BOM if self.bom else '') + body

    def write(self, text: str) -> None:
        with open(self.path, 'w', encoding='utf-8', newline='') as handle:
            handle.write(text)


@contextlib.contextmanager
def _field_limit_lifted():
    """Let `csv` read a cell as long as pandas reads, then put the limit back.

    The module refuses a field over 131,072 characters by default; pandas
    has no such limit, so a sheet the build converts would otherwise be
    one this phase cannot read. The largest limit the platform accepts is
    found by halving from `sys.maxsize`.
    """
    previous = csv.field_size_limit()
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            break
        except OverflowError:
            limit //= 2
    try:
        yield
    finally:
        csv.field_size_limit(previous)


# One unquoted field, and what may end a record.
_UNQUOTED = re.compile(r'[^,\r\n]*')
_TERMINATOR = re.compile(r'\r\n|\r|\n|')


def _quoted_end(text: str, start: int) -> Optional[int]:
    """The end of the quoted field opening at *start*, or None when the
    quote never closes or text follows the closing quote."""
    index = start + 1
    while True:
        close = text.find('"', index)
        if close < 0:
            return None
        if text.startswith('"', close + 1):
            index = close + 2
            continue
        end = close + 1
        return end if end == len(text) or text[end] in ',\r\n' else None


def _split_record(text: str, pos: int):
    """(fields, terminator, next position) for the record at *pos*, or None."""
    fields = []
    while True:
        if text.startswith('"', pos):
            end = _quoted_end(text, pos)
            if end is None:
                return None
        else:
            end = _UNQUOTED.match(text, pos).end()
        fields.append(text[pos:end])
        pos = end
        if not text.startswith(',', pos):
            break
        pos += 1
    ending = _TERMINATOR.match(text, pos).group()
    return fields, ending, pos + len(ending)


def split_records(text: str) -> Optional[List[Tuple[List[str], str]]]:
    """Every record as (its fields as written, its terminator)."""
    records, pos = [], 0
    while pos < len(text):
        split = _split_record(text, pos)
        if split is None:
            return None
        fields, ending, pos = split
        records.append((fields, ending))
    return records


def _cells(fields: List[str]) -> List[str]:
    """What `csv` reads *fields* as; a blank record is no cells at all."""
    if fields == ['']:
        return []
    return [f[1:-1].replace('""', '"') if f.startswith('"') else f for f in fields]


# pandas' C tokenizer skips a line of these characters alone as blank;
# a form feed or a vertical tab is a cell.
_BLANK_LINE_CHARACTERS = ' \t'


def _skipped_fields(fields: List[str]) -> bool:
    """Whether pandas skips the record written as *fields*: one unquoted
    field of spaces and tabs, or nothing. A quoted `""` is a cell."""
    return len(fields) == 1 and not fields[0].strip(_BLANK_LINE_CHARACTERS)


def _skipped_row(row: List[str]) -> bool:
    """`_skipped_fields` judged on cells `csv` has read, for a file that
    cannot be split: a quoted `""` or `"  "` line reads as the blank line
    it is not, so a sheet judged this way is only reported on."""
    return len(row) <= 1 and not ''.join(row).strip(_BLANK_LINE_CHARACTERS)


def pandas_labels(header: List[str], text: Optional[str] = None) -> List[str]:
    """The column labels the build's pandas read gives this sheet.

    Read from pandas itself rather than imitated: a repeated header gains
    `.1`, `.2` and a blank one `Unnamed: <position>`, and pandas steps past
    a suffix another header already holds, so `note,note,note.1` is read as
    `note,note.2,note.1`, three names the build does not refuse.

    With *text*, the whole sheet is read as `read_sheet` reads its width,
    past the lines pandas skips and with `index_col=False`, and the labels
    must be as many as the *header* cells. Where pandas cannot read that
    header, as when a later quote never closes, only the header row is
    given to it, so the sheet's columns can still be reported.
    """
    if not header:
        return []
    import pandas as pd
    labels = None
    if text is not None:
        try:
            labels = pd.read_csv(io.StringIO(text, newline=''), nrows=0,
                                 index_col=False).columns
        except ValueError:
            labels = None
    if labels is None:
        line = io.StringIO(newline='')
        csv.writer(line).writerow(header)
        line.seek(0)
        labels = pd.read_csv(line, nrows=0, index_col=False).columns
    labels = [str(label) for label in labels]
    if len(labels) != len(header):
        raise ValueError('pandas reads a different number of columns')
    return labels


def data_rows(sheet: Sheet, rules, sheet_aliases=None) -> List[List[str]]:
    """The rows the build treats as data.

    A line pandas skips as blank is not a row, so a removal that leaves a
    row with nothing but spaces or tabs takes it out of the data. A row
    whose first cell, trimmed, starts with `#` is a comment. The first row
    left is dropped when it is a second, bilingual header row, judged on
    the cells of the columns the build keeps.
    """
    rows = [row for row in sheet.body if not row[0].strip().startswith('#')]
    if _header_row_skipped(sheet, rows, rules, sheet_aliases):
        rows = rows[1:]
    return rows


def _header_row_skipped(sheet: Sheet, rows, rules, sheet_aliases=None) -> bool:
    """Whether the build drops the first of *rows*, the rows left once the
    comment rows are gone, as a second, bilingual header row."""
    if not rows:
        return False
    kept = [index for index, label in enumerate(sheet.labels) if not label.startswith('#')]
    first = [rows[0][index] if index < len(rows[0]) else '' for index in kept]
    return bool(rules.is_header_row(first, sheet_aliases=sheet_aliases))


def _skips_header_row(sheet: Sheet, rules, sheet_aliases=None) -> bool:
    rows = [row for row in sheet.body if not row[0].strip().startswith('#')]
    return _header_row_skipped(sheet, rows, rules, sheet_aliases)


def _holds_values(rows: List[List[str]], index: int) -> bool:
    return any(index < len(row) and row[index].strip() for row in rows)


def claimed_names(labels: List[str], rules, canonical_fields=None,
                  sheet_aliases=None) -> Dict[str, List[int]]:
    """Each name the build would give a column, and the columns claiming it.

    The same terms as `normalize_column_names` followed by
    `_refuse_colliding_renames`: a header the map renames claims the name it
    is renamed to, unless the sheet is scoped and that name is outside its
    fields, and every other header claims itself lowercased and trimmed.
    """
    mapping = {**rules.COLUMN_NAME_MAPPING, **(sheet_aliases or {})}
    claims: Dict[str, List[int]] = {}
    for index, label in enumerate(labels):
        if label.startswith('#'):
            continue
        folded = label.lower().strip()
        target = mapping.get(folded)
        if canonical_fields is not None and target not in canonical_fields:
            target = None
        claims.setdefault(target or folded, []).append(index)
    return claims


# ---------------------------------------------------------------------- #
# Which sheets, read how
# ---------------------------------------------------------------------- #

def _first_present(directory: str, names) -> Optional[str]:
    for name in names:
        if os.path.isfile(os.path.join(directory, name)):
            return name
    return None


def sheets_to_check(repo_root: str, rules) -> List[Tuple[str, dict]]:
    """Every sheet the build converts, with how it scopes the alias map.

    The build converts one project sheet and one objects sheet, preferring
    the English name, and every other CSV as a story, the glossary sheets
    included. The glossary sheet the glossary reader picks is read with its
    own aliases too, and those claims include the story reading's, so that
    reading stands for both.
    """
    directory = os.path.join(repo_root, SPREADSHEETS_DIR)
    if not os.path.isdir(directory):
        return []
    special = {
        _first_present(directory, PROJECT_SHEETS): {},
        _first_present(directory, OBJECTS_SHEETS): {'canonical_fields': rules.OBJECT_FIELDS},
        _first_present(directory, GLOSSARY_SHEETS):
            {'sheet_aliases': rules.GLOSSARY_COLUMN_ALIASES},
    }
    skipped = set(PROJECT_SHEETS + OBJECTS_SHEETS)
    found = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith('.csv'):
            continue
        if name in special:
            found.append((name, special[name]))
        elif name not in skipped:
            found.append((name, {}))
    return found


def _site_reads_google_sheets(repo_root: str) -> bool:
    try:
        with open(os.path.join(repo_root, '_config.yml'), encoding='utf-8') as handle:
            config = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return False
    section = config.get('google_sheets') if isinstance(config, dict) else None
    return bool(isinstance(section, dict) and section.get('enabled'))


def _load_column_rules():
    """`telar.csv_utils`, or the reason it cannot be imported."""
    try:
        return importlib.import_module('telar.csv_utils'), None
    except ImportError as error:
        return None, error


# ---------------------------------------------------------------------- #
# Colliding columns
# ---------------------------------------------------------------------- #

def _resolve(claim: str, indices: List[int], header, rows) -> Tuple[List[int], List[int]]:
    """(kept, dropped) for one colliding group; dropped is empty when more
    than one column holds values."""
    holding = [index for index in indices if _holds_values(rows, index)]
    if len(holding) > 1:
        return holding, []
    if holding:
        keep = holding[0]
    else:
        spelled = [index for index in indices if header[index].lower().strip() == claim]
        keep = (spelled or indices)[0]
    return [keep], [index for index in indices if index != keep]


def _seen(sheet: Sheet, rules, aliases, columns: List[int]) -> List[List[str]]:
    """The cells of *columns* in each row the build treats as data."""
    return [[_cell(row, index) for index in columns]
            for row in data_rows(sheet, rules, aliases)]


# Why an edit was refused: the file cannot be edited that safely; the
# build would stop taking a row for the bilingual header row and publish
# it; or the data rows would change some other way.
UNSAFE, HEADER_ROW, ROWS_CHANGED = 'unsafe', 'header_row', 'rows_changed'


def _try_edit(sheet: Sheet, rules, aliases, removed, mark) -> Tuple[Optional[str], Optional[str]]:
    """(the edited text, None) when the build would read the same data rows
    from it, over the columns that survive, as from *sheet*; otherwise
    (None, why it was refused)."""
    text = sheet.edited(removed, mark)
    if text is None:
        return None, UNSAFE
    try:
        after = Sheet(sheet.path, text)
    except (csv.Error, ValueError):
        return None, UNSAFE
    if after.header_at != sheet.header_at:
        return None, UNSAFE
    if mark and after.header[:1] != ['#' + sheet.header[0]]:
        return None, UNSAFE
    kept = [index for index in range(len(sheet.header)) if index not in removed]
    seen = [position for position in range(len(kept)) if not (mark and position == 0)]
    before = _seen(sheet, rules, aliases, [kept[position] for position in seen])
    if before == _seen(after, rules, aliases, seen):
        return text, None
    if _skips_header_row(sheet, rules, aliases) and not _skips_header_row(after, rules, aliases):
        return None, HEADER_ROW
    return None, ROWS_CHANGED


def _plan_pass(sheet: Sheet, rules, aliases, groups):
    """(removed, mark, accepted groups, refused (group, reason) pairs) for
    one pass; a refused group carries the reason its last option failed.

    Each group's removal is tried on top of those already accepted in the
    pass. Where removing it would change the rows the build reads, and the
    first column is among those it removes, the first column is kept and
    its header marked with `#` instead: the build drops a `#` column after
    it has read the comment rows, so an empty one changes nothing.
    """
    removed, mark, accepted, refused = set(), False, [], []
    for group in groups:
        dropped = set(group[2])
        if not dropped:
            continue
        options = [(removed | dropped, mark)]
        if 0 in dropped:
            options.append(((removed | dropped) - {0}, True))
        choice, reason = None, None
        for option in options:
            text, reason = _try_edit(sheet, rules, aliases, *option)
            if text is not None:
                choice = option
                break
        if choice is None:
            refused.append((group, reason))
        else:
            removed, mark = choice
            accepted.append(group)
    return removed, mark, accepted, refused


def _repair_sheet(repo_root, lang, name, scope, rules, on_sheets) -> List[ChangeRecord]:
    """Repeated until nothing changes, because a removal can create a
    collision: pandas labels a repeated header `note.1`, and the suffix goes
    when its twin is removed, so a column that claimed a name of its own
    comes to claim the one its twin claimed.

    No pass may change the rows the build reads as data, compared over the
    columns that survive it; a removal that would is not made, and its
    columns are reported as ones to delete by hand."""
    path = os.path.join(repo_root, SPREADSHEETS_DIR, name)
    try:
        sheet = Sheet(path)
    except (OSError, UnicodeDecodeError, csv.Error, ValueError) as error:
        return [_record(lang, 'v180_sheet_unreadable', name, error,
                        status=ChangeStatus.FAILED)]
    records = _reserved_column_records(lang, name, sheet.header, rules)
    writable = _inside(repo_root, path)
    aliases = scope.get('sheet_aliases')
    origin = list(range(len(sheet.header)))
    changes, successor = [], {}
    repaired = None
    while True:
        rows = data_rows(sheet, rules, aliases)
        claims = claimed_names(sheet.labels, rules, **scope)
        groups = [(claim, *_resolve(claim, indices, sheet.header, rows))
                  for claim, indices in claims.items() if len(indices) > 1]
        if writable:
            removed, mark, accepted, refused = _plan_pass(sheet, rules, aliases, groups)
        else:
            removed, mark, accepted, refused = set(), False, [], [(g, UNSAFE) for g in groups if g[2]]
        if not accepted:
            break
        for _claim, kept, dropped in accepted:
            for index in dropped:
                successor[origin[index]] = origin[kept[0]]
                changes.append((sheet.header[index], index in removed, origin[kept[0]],
                                rows, list(origin)))
        repaired = sheet.edited(removed, mark)
        sheet = Sheet(path, repaired)
        origin = [column for index, column in enumerate(origin) if index not in removed]
    if repaired is not None:
        sheet.write(repaired)
    for change in changes:
        records.extend(_change_records(lang, name, change, successor, sheet.header, origin,
                                       on_sheets))
    records.extend(_unrepaired_records(lang, name, sheet.header, groups, refused))
    return records


def _change_records(lang, name, change, successor, header, origin,
                    on_sheets) -> List[ChangeRecord]:
    """The records for one column removed or marked.

    Whether the keeper holds values is judged on the rows of the pass that
    made the change. The keeper named is the column the written file keeps:
    a keeper a later pass removed is followed to the column kept in its
    place, which holds the same data rows, since no pass changes them.
    """
    column, was_removed, keeper, rows, pass_origin = change
    if not was_removed:
        records = [_record(lang, 'v180_column_marked_note', column, name, '#' + column)]
        if on_sheets:
            records.append(_record(lang, 'v180_column_marked_in_sheet', column, name,
                                   '#' + column, status=ChangeStatus.FAILED))
        return records
    while keeper in successor:
        keeper = successor[keeper]
    label = header[origin.index(keeper)]
    if _holds_values(rows, pass_origin.index(keeper)):
        records = [_record(lang, 'v180_column_dropped', column, name, label)]
    else:
        records = [_record(lang, 'v180_column_dropped_all_empty', column, name, label, label)]
    if on_sheets:
        records.append(_record(lang, 'v180_column_in_sheet', column, name,
                               status=ChangeStatus.FAILED))
    return records


def _unrepaired_records(lang, name, header, groups, refused) -> List[ChangeRecord]:
    """The collisions the final pass left: columns it could not remove, and
    groups in which more than one column holds values."""
    records = []
    reasons = dict((id(group), reason) for group, reason in refused)
    for group in groups:
        _claim, kept, dropped = group
        if dropped:
            if id(group) in reasons:
                key = ('v180_column_kept_for_header_row' if reasons[id(group)] == HEADER_ROW
                       else 'v180_column_not_removed')
                records.extend(_record(lang, key, header[index], name,
                                       status=ChangeStatus.FAILED) for index in dropped)
        else:
            named = ', '.join(f'`{header[index]}`' for index in kept)
            records.append(_record(lang, 'v180_columns_hold_values', name, named,
                                   status=ChangeStatus.FAILED))
    return records


def _inside(repo_root: str, path: str) -> bool:
    """Whether *path*, with every link resolved, is still inside the site."""
    root = os.path.realpath(repo_root)
    return os.path.commonpath([root, os.path.realpath(path)]) == root


def _reserved_column_records(lang, name, header, rules) -> List[ChangeRecord]:
    return [_record(lang, 'v180_reserved_column', name, column, status=ChangeStatus.FAILED)
            for column in header
            if column.lower().strip() in rules.RESERVED_COLUMN_NAMES]


def repair_colliding_columns(repo_root: str, lang: str) -> List[ChangeRecord]:
    """Delete the empty duplicates of a column the build would refuse.

    Runs before regeneration, which would otherwise fail on the collision
    and leave the site at 1.7.0. A Google Sheets site has its local copies
    repaired, so that regeneration completes, and is told which column to
    delete in the sheet, because the next build fetches the sheet again.
    """
    rules, error = _load_column_rules()
    if rules is None:
        return [_record(lang, 'v180_sheets_unchecked', error, status=ChangeStatus.FAILED)]
    on_sheets = _site_reads_google_sheets(repo_root)
    records = []
    for name, scope in sheets_to_check(repo_root, rules):
        records.extend(_repair_sheet(repo_root, lang, name, scope, rules, on_sheets))
    return records or [_record(lang, 'v180_sheets_clean')]


# ---------------------------------------------------------------------- #
# Step answers
# ---------------------------------------------------------------------- #

_KIND_KEYS = {
    'media': 'v180_answer_kind_media',
    'widgets': 'v180_answer_kind_widgets',
    'footnotes': 'v180_answer_kind_footnotes',
    'markup': 'v180_answer_kind_markup',
}


def _load_answer_rules():
    """`telar.processors.stories` and `telar.csv_utils`, or the import error."""
    try:
        stories = importlib.import_module('telar.processors.stories')
        csv_utils = importlib.import_module('telar.csv_utils')
    except ImportError as error:
        return None, error
    return (stories, csv_utils), None


def _column_for(labels, rules, name: str) -> Optional[int]:
    indices = claimed_names(labels, rules).get(name)
    return indices[0] if indices else None


def _answer_records(lang, story, step, answer, stories) -> List[ChangeRecord]:
    if not answer.strip():
        return []
    prose, kinds = stories._reduce_answer_to_prose(answer)
    records = []
    if kinds:
        removed = ', '.join(get_message(lang, _KIND_KEYS[kind]) for kind in kinds)
        records.append(_record(lang, 'v180_answer_content_removed', story, step, removed))
    count = stories._count_answer_words(prose)
    if count > stories.ANSWER_WORD_LIMIT:
        records.append(_record(lang, 'v180_answer_over_limit', story, step, count,
                               stories.ANSWER_WORD_LIMIT))
    return records


def _story_answer_records(repo_root, lang, name, rules) -> List[ChangeRecord]:
    stories, csv_utils = rules
    try:
        sheet = Sheet(os.path.join(repo_root, SPREADSHEETS_DIR, name))
    except (OSError, UnicodeDecodeError, csv.Error, ValueError):
        return []
    answer = _column_for(sheet.labels, csv_utils, 'answer')
    if answer is None:
        return []
    step = _column_for(sheet.labels, csv_utils, 'step')
    story = os.path.splitext(name)[0]
    records = []
    for row in data_rows(sheet, csv_utils):
        label = _cell(row, step).strip() if step is not None else 'unknown'
        records.extend(_answer_records(lang, story, label, _cell(row, answer), stories))
    return records


def _cell(row: List[str], index: Optional[int]) -> str:
    return row[index] if index is not None and index < len(row) else ''


def report_step_answers(repo_root: str, lang: str) -> List[ChangeRecord]:
    """One record per answer the build will cut or strip, and nothing written.

    Counted with the build's own prose rules, word count and limit, so the
    report and the build cannot disagree. A Google Sheets site is counted
    from its local copies, with a note that the build reads the sheet again.
    """
    rules, error = _load_answer_rules()
    if rules is None:
        return [_record(lang, 'v180_answers_unchecked', error)]
    records = []
    for name, _scope in sheets_to_check(repo_root, rules[1]):
        if name in PROJECT_SHEETS or name in OBJECTS_SHEETS:
            continue
        records.extend(_story_answer_records(repo_root, lang, name, rules))
    if not records:
        return [_record(lang, 'v180_answers_clean')]
    if _site_reads_google_sheets(repo_root):
        records.append(_record(lang, 'v180_answers_from_local_copies'))
    return records
