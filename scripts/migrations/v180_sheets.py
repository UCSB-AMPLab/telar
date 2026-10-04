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

    `rows` are the cells as `csv` reads them and `labels` the column names
    as pandas gives them to the build, suffixes for repeated headers
    included. `records` holds each record's fields as the exact text they
    were written in, with the terminator that ended the record, so a repair
    can take one field and its delimiter out of a record and leave every
    other byte as it was: quoting, spacing, CR, LF or CRLF, a BOM.

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
        self.labels = pandas_labels(self.header)
        self.records = split_records(text)
        if self.records is not None and [_cells(f) for f, _ in self.records] != self.rows:
            self.records = None

    @property
    def header(self) -> List[str]:
        return self.rows[0] if self.rows else []

    def without_columns(self, indices) -> Optional[str]:
        """The file's text with the fields at *indices* gone from every
        record, or None when it cannot be edited that safely."""
        if self.records is None:
            return None
        doomed = set(indices)
        body = ''.join(','.join(field for index, field in enumerate(fields)
                                if index not in doomed) + ending
                       for fields, ending in self.records)
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


def pandas_labels(header: List[str]) -> List[str]:
    """The column labels the build's pandas read gives this sheet.

    Read from pandas itself rather than imitated: a repeated header gains
    `.1`, `.2` and a blank one `Unnamed: <position>`, and pandas steps past
    a suffix another header already holds, so `note,note,note.1` is read as
    `note,note.2,note.1`, three names the build does not refuse. Only the
    header row is given to pandas, so a later row it cannot parse does not
    keep the header from being read.
    """
    if not header:
        return []
    import pandas as pd
    line = io.StringIO(newline='')
    csv.writer(line).writerow(header)
    line.seek(0)
    labels = [str(label) for label in pd.read_csv(line, nrows=0).columns]
    if len(labels) != len(header):
        raise ValueError('pandas reads a different number of columns')
    return labels


def data_rows(sheet: Sheet, rules, sheet_aliases=None) -> List[List[str]]:
    """The rows the build treats as data.

    A row whose first cell, trimmed, starts with `#` is a comment. The
    first row left is dropped when it is a second, bilingual header row,
    judged on the cells of the columns the build keeps.
    """
    rows = [row for row in sheet.rows[1:]
            if not (row and row[0].strip().startswith('#'))]
    if rows:
        kept = [index for index, label in enumerate(sheet.labels)
                if not label.startswith('#')]
        first = [rows[0][index] if index < len(rows[0]) else '' for index in kept]
        if rules.is_header_row(first, sheet_aliases=sheet_aliases):
            rows = rows[1:]
    return rows


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


def _repair_sheet(repo_root, lang, name, scope, rules, on_sheets) -> List[ChangeRecord]:
    """Repeated until nothing changes, because a removal can create a
    collision: pandas labels a repeated header `note.1`, and the suffix goes
    when its twin is removed, so a column that claimed a name of its own
    comes to claim the one its twin claimed."""
    path = os.path.join(repo_root, SPREADSHEETS_DIR, name)
    try:
        sheet = Sheet(path)
    except (OSError, UnicodeDecodeError, csv.Error, ValueError) as error:
        return [_record(lang, 'v180_sheet_unreadable', name, error,
                        status=ChangeStatus.FAILED)]
    records = _reserved_column_records(lang, name, sheet.header, rules)
    writable = _inside(repo_root, path)
    repaired = None
    removed = []
    while True:
        header = sheet.header
        rows = data_rows(sheet, rules, scope.get('sheet_aliases'))
        claims = claimed_names(sheet.labels, rules, **scope)
        groups = [(claim, *_resolve(claim, indices, header, rows))
                  for claim, indices in claims.items() if len(indices) > 1]
        doomed = [index for _claim, _kept, dropped in groups for index in dropped]
        text = sheet.without_columns(doomed) if doomed and writable else None
        if text is None:
            break
        removed.extend((header[index], claim) for claim, _kept, dropped in groups
                       for index in dropped)
        repaired = text
        sheet = Sheet(path, text)
    if repaired is not None:
        sheet.write(repaired)
    # Every record describes the file as written, so a keeper is named only
    # once no later pass can remove it.
    for column, claim in removed:
        records.extend(_removal_records(lang, name, column, claims[claim], header, rows,
                                        on_sheets))
    for _claim, kept, dropped in groups:
        if dropped:
            records.extend(_record(lang, 'v180_column_not_removed', header[index], name,
                                   status=ChangeStatus.FAILED) for index in dropped)
        else:
            named = ', '.join(f'`{header[index]}`' for index in kept)
            records.append(_record(lang, 'v180_columns_hold_values', name, named,
                                   status=ChangeStatus.FAILED))
    return records


def _removal_records(lang, name, column, keepers, header, rows, on_sheets) -> List[ChangeRecord]:
    holding = [index for index in keepers if _holds_values(rows, index)]
    keeper = header[(holding or keepers)[0]]
    if holding:
        records = [_record(lang, 'v180_column_dropped', column, name, keeper)]
    else:
        records = [_record(lang, 'v180_column_dropped_all_empty', column, name, keeper, keeper)]
    if on_sheets:
        records.append(_record(lang, 'v180_column_in_sheet', column, name,
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
