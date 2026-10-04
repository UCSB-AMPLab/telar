"""
Site-Owned Text Files the v1.8.0 Migration Edits in Place

This module deals with the four edits `v170_to_v180` makes to files a site
owns rather than receives: one line in each of the two built-in pages, the
`exclude:` list in `_config.yml`, the front matter of the page sources, and
the `related_terms` line of glossary markdown. Each function takes the site
root and its language and returns ChangeRecords; the migration calls them in
order and adds nothing of its own.

All four are text edits, never YAML round trips. A site's comments, key
order, quoting and line endings are its own, and a re-serialised file hands
the owner back a file they did not write. Where an edit touches YAML, the
file is parsed before and after and the edit is written only when the two
agree on every key it did not mean to change; otherwise the file is left
alone and the record says so.

Every function is idempotent: a second run finds nothing left to change.

Version: v1.8.0
"""

import json
import os
import re
from typing import List, Optional, Tuple

import yaml

from .messages import get_message
from .records import ChangeCategory, ChangeRecord, ChangeStatus, category_for_path


# ---------------------------------------------------------------------- #
# Shared text handling
# ---------------------------------------------------------------------- #

def _read_text(path: str) -> str:
    """The file exactly as stored: line endings and any BOM kept."""
    with open(path, 'r', encoding='utf-8', newline='') as handle:
        return handle.read()


def _write_text(path: str, text: str) -> None:
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        handle.write(text)


def _body(line: str) -> str:
    """A line without its line ending."""
    return line.rstrip('\r\n')


def _ending(line: str) -> str:
    return line[len(_body(line)):]


def _newline_of(text: str) -> str:
    return '\r\n' if '\r\n' in text else '\n'


def _record(lang, key, *args, status=ChangeStatus.APPLIED, severity='soft',
            category=ChangeCategory.OTHER) -> ChangeRecord:
    return ChangeRecord(description=get_message(lang, key, *args),
                        status=status, severity=severity, category=category)


def _front_matter_bounds(lines: List[str]) -> Optional[Tuple[int, int]]:
    """Indices of the opening and closing `---` lines, or None.

    The same shape `FRONTMATTER_PATTERN` accepts: `---` on the first line,
    trailing whitespace allowed, closed by the next such line. A BOM before
    the opening line is tolerated, as the editors that write one expect.
    """
    if not lines or _body(lines[0]).lstrip('﻿').rstrip() != '---':
        return None
    for index in range(1, len(lines)):
        if _body(lines[index]).rstrip() == '---':
            return 0, index
    return None


def _load_mapping(lines: List[str]) -> Optional[dict]:
    """The front matter as a mapping, or None when it is not one."""
    try:
        loaded = yaml.safe_load(''.join(lines))
    except (yaml.YAMLError, ValueError, TypeError, KeyError):
        return None
    if loaded is None:
        return {}
    return loaded if isinstance(loaded, dict) else None


def _top_level_key(line: str) -> Optional[str]:
    """The key a top-level `key:` line opens, or None."""
    body = _body(line)
    if not body or body[0].isspace() or body.startswith('#') or ':' not in body:
        return None
    return body.split(':', 1)[0].strip()


def _is_continuation(line: str) -> bool:
    """An indented, non-blank line, which belongs to the key above it."""
    body = _body(line)
    return bool(body.strip()) and body[0].isspace()


def _is_comment(line: str) -> bool:
    return _body(line).strip().startswith('#')


def _without_keys(lines: List[str], keys) -> List[str]:
    """*lines* with each top-level key in *keys* and its continuation lines gone.

    A comment line is the author's, wherever it is indented, so it stays
    even inside the lines of a key that goes.
    """
    kept, dropping = [], False
    for line in lines:
        if dropping and _is_continuation(line):
            if _is_comment(line):
                kept.append(line)
            continue
        dropping = _top_level_key(line) in keys
        if not dropping:
            kept.append(line)
    return kept


# ---------------------------------------------------------------------- #
# Built-in pages: one template line each
# ---------------------------------------------------------------------- #

# Per built-in page: the default-content line a site received from the
# template it was made from, and the line the current template carries. The
# manifest's page-body operations are generated from these, so the two
# routes cannot change a different line.
SITE_PAGE_LINES = (
    ('index.md',
     '{{ lang.index_page.welcome | markdownify }}',
     '{{ lang.index_page.welcome | default: site.data.languages.en.index_page.welcome'
     ' | markdownify }}'),
    ('pages/glossary.md',
     '{{ lang.pages.glossary_intro }}',
     '{% include glossary-intro.html lang=lang %}'),
)


# A line and its ending, where only CR, LF and CRLF end a line. The
# manifest's JavaScript pattern knows no others, and the two routes must
# agree on which lines exist.
_LINE = re.compile(r'[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$')


def replace_template_line(text: str, old: str, new: str) -> Tuple[str, bool]:
    """*text* with every line equal to *old* replaced by *new*.

    Equal means the whole line, byte for byte apart from its line ending.
    A line the owner has edited, indented or extended is theirs and stays.
    """
    lines = _LINE.findall(text)
    changed = False
    for index, line in enumerate(lines):
        if _body(line) == old:
            lines[index] = new + _ending(line)
            changed = True
    return ''.join(lines), changed


def update_site_pages(repo_root: str, lang: str) -> List[ChangeRecord]:
    """Bring each built-in page's default-content line to the v1.8.0 one.

    `index.md` gains a fallback to the English welcome text for a language
    pack that lacks one; `pages/glossary.md` reads its introduction through
    `glossary-intro.html`, which chooses the variant for a glossary with
    primary sources. Both pages belong to the site, so only a line still
    equal to the one the site's template gave it is replaced.
    """
    return [_update_site_page(repo_root, lang, *entry) for entry in SITE_PAGE_LINES]


def _update_site_page(repo_root, lang, rel_path, old, new) -> ChangeRecord:
    category = category_for_path(rel_path)
    path = os.path.join(repo_root, rel_path)
    if not os.path.isfile(path):
        return _record(lang, 'v180_page_absent', rel_path, category=category)
    try:
        text = _read_text(path)
        updated, changed = replace_template_line(text, old, new)
        if changed:
            _write_text(path, updated)
    except (OSError, UnicodeDecodeError) as error:
        return _record(lang, 'v180_file_unreadable', rel_path, error,
                       status=ChangeStatus.FAILED, category=category)
    if changed:
        return _record(lang, 'v180_page_line_updated', rel_path, new, category=category)
    if any(_body(line) == new for line in _LINE.findall(text)):
        return _record(lang, 'v180_page_line_current', rel_path, category=category)
    return _record(lang, 'v180_page_line_own_text', rel_path, new, category=category)


# ---------------------------------------------------------------------- #
# _config.yml: the exclude entries
# ---------------------------------------------------------------------- #

# Each group goes into a block list under the template's own comment when
# none of its entries is present; an entry missing from a group the site
# already has goes in on its own, and a flow list takes the entries alone.
# `hard` marks the group a site cannot build without.
EXCLUDE_GROUPS = (
    {
        'comment': (
            "# Telar's own test suite and the configuration that runs it. Nothing on a",
            "# site links to any of it, and a fixture is content written to be wrong in",
            "# a particular way — published, it is indistinguishable from the site's own.",
        ),
        'entries': ('tests/', 'pytest.ini', 'vitest.config.js'),
        'hard': False,
    },
    {
        'comment': (
            '# Page, story and glossary sources. The build reads them and generates the',
            '# published pages from them; Jekyll rendering them as well puts a raw,',
            '# unprocessed copy of every one at a second URL, and a source that declares',
            '# its own permalink lands on top of the page generated from it.',
        ),
        'entries': ('telar-content/texts/',),
        'hard': True,
    },
)

EXCLUDE_ENTRIES = tuple(entry for group in EXCLUDE_GROUPS for entry in group['entries'])

_EXCLUDE_LINE = re.compile(r'exclude:(?P<rest>.*)$')
_CONFIG = '_config.yml'
_ABSENT = object()


def _normalise_entry(value):
    """The form two entries are compared in: the parsed value, with one
    trailing slash dropped from a string. Nothing else is forgiven, so
    `"telar-content/texts/ "` is not the entry the site needs."""
    if isinstance(value, str) and value.endswith('/'):
        return value[:-1]
    return value


def _block_insertion(lines: List[str], start: int) -> Tuple[int, str]:
    """Where to append to the block list opened at *start*, and the
    indentation its items use (two spaces for a list with no items)."""
    insert_at, indent = start + 1, None
    for index in range(start + 1, len(lines)):
        body = _body(lines[index])
        stripped = body.strip()
        if not stripped or stripped.startswith('#'):
            continue
        lead = body[:len(body) - len(body.lstrip())]
        if stripped.startswith('- ') and (indent is None or lead == indent):
            indent, insert_at = lead, index + 1
        elif indent is not None and len(lead) > len(indent):
            insert_at = index + 1
        else:
            break
    return insert_at, ('  ' if indent is None else indent)


def _exclude_lines(missing: List[str], indent: str, newline: str) -> List[str]:
    added = []
    for group in EXCLUDE_GROUPS:
        wanted = [entry for entry in group['entries'] if entry in missing]
        if not wanted:
            continue
        if len(wanted) == len(group['entries']):
            added.extend(indent + line + newline for line in group['comment'])
        added.extend(f'{indent}- {entry}{newline}' for entry in wanted)
    return added


def _ended(lines: List[str], newline: str) -> List[str]:
    if lines and not lines[-1].endswith(('\n', '\r')):
        lines[-1] += newline
    return lines


def _into_block(text: str, start: int, missing: List[str]) -> str:
    lines, newline = text.splitlines(keepends=True), _newline_of(text)
    insert_at, indent = _block_insertion(lines, start)
    if insert_at == len(lines):
        _ended(lines, newline)
    lines[insert_at:insert_at] = _exclude_lines(missing, indent, newline)
    return ''.join(lines)


def _is_comment_start(text: str, index: int) -> bool:
    """Whether a comment starts at *index*: a `#` at a line's start or after
    whitespace."""
    return text[index] == '#' and (index == 0 or text[index - 1].isspace())


def _comment_start(body: str) -> int:
    """Where a comment starts on one line, outside quotes, or -1."""
    quote = None
    for index, char in enumerate(body):
        if quote:
            quote = None if char == quote else quote
        elif char in '\'"':
            quote = char
        elif _is_comment_start(body, index):
            return index
    return -1


def _line_end_from(text: str, index: int) -> int:
    """The index of the line ending at or after *index*, or the text's length."""
    found = re.compile(r'[\r\n]').search(text, index)
    return found.start() if found else len(text)


def _line_start_of(text: str, index: int) -> int:
    return max(text.rfind('\n', 0, index), text.rfind('\r', 0, index)) + 1


def _closing_bracket(text: str, opening: int) -> Optional[int]:
    """The index of the `]` closing the flow sequence opened at *opening*;
    comments are skipped, so a quote or bracket in one does not count."""
    depth, quote, index = 0, None, opening
    while index < len(text):
        char = text[index]
        if quote:
            quote = None if char == quote else quote
        elif char in '\'"':
            quote = char
        elif _is_comment_start(text, index):
            index = _line_end_from(text, index)
            continue
        elif char in '[{':
            depth += 1
        elif char in ']}':
            depth -= 1
            if depth == 0:
                return index if char == ']' else None
        index += 1
    return None


def _before_own_line_bracket(text: str, bracket_line: int, missing: List[str]) -> str:
    """*text* with *missing* on a line of their own before a `]` that has
    its own line, where the last item's line ends in a comment. The last item
    gains a comma before its comment, if it has none; the new line takes
    that item's indentation."""
    lines = text[:bracket_line].splitlines(keepends=True)
    index = len(lines) - 1
    while index > 0 and re.fullmatch(r'\s*(?:#.*)?', _body(lines[index])):
        index -= 1
    body = _body(lines[index])
    cut = _comment_start(body)
    code = (body if cut < 0 else body[:cut]).rstrip()
    opens_list = code.endswith('[')
    if not opens_list and not code.endswith(','):
        lines[index] = code + ',' + lines[index][len(code):]
    source = text[bracket_line:] if opens_list else body
    lead = source[:len(source) - len(source.lstrip())] + ('  ' if opens_list else '')
    return ''.join(lines) + lead + ', '.join(missing) + _newline_of(text) + text[bracket_line:]


def _into_flow(text: str, start: int, missing: List[str]) -> Optional[str]:
    """*text* with *missing* inserted before the closing bracket of the flow
    sequence on line *start*, after its last item. When the last item's
    line ends in a comment they go on a line of their own, which needs the
    `]` on its own line. The Compositor's `yaml_list_add` writes the same
    bytes."""
    offset = sum(len(line) for line in text.splitlines(keepends=True)[:start])
    opening = text.index('[', offset)
    closing = _closing_bracket(text, opening)
    if closing is None:
        return None
    last = len(text[:closing].rstrip())
    if _comment_start(text[_line_start_of(text, last):last]) >= 0:
        bracket_line = _line_start_of(text, closing)
        if text[bracket_line:closing].strip() == '' and bracket_line > opening:
            return _before_own_line_bracket(text, bracket_line, missing)
        return None
    inner = text[opening + 1:last].strip()
    lead = '' if not inner else (' ' if inner.endswith(',') else ', ')
    return text[:last] + lead + ', '.join(missing) + text[last:]


def _scalar_split(rest: str) -> Tuple[str, str]:
    """The scalar written after `exclude:` and the comment that follows it
    on the line, if any. A quoted value ends at its closing quote, where
    `''` inside single quotes and a backslash inside double quotes do not
    close it; after that, a comment starts at a `#` preceded by a space."""
    end = 0
    if rest[:1] in ('"', "'"):
        quote, end = rest[0], len(rest)
        index = 1
        while index < len(rest):
            if quote == '"' and rest[index] == '\\':
                index += 2
            elif rest[index] == quote and quote == "'" and rest[index + 1:index + 2] == "'":
                index += 2
            elif rest[index] == quote:
                end = index + 1
                break
            else:
                index += 1
    comment = re.compile(r'(^|\s)#').search(rest, end)
    if not comment:
        return rest, ''
    return rest[:comment.start()].rstrip(), rest[comment.start():].strip()


def _same_value(one, other) -> bool:
    return type(one) is type(other) and one == other


def _continuation_count(lines: List[str], start: int) -> int:
    """How many lines after *start* continue it: indented ones, and blank
    or comment lines between them. Counting stops at the last indented line
    that is not a comment, so a comment after the value stays in the file."""
    count = 0
    for index in range(start + 1, len(lines)):
        body = _body(lines[index])
        if not body.strip():
            continue
        if not body[:1].isspace():
            break
        if not body.strip().startswith('#'):
            count = index - start
    return count


def _from_scalar(text: str, start: int, value, missing: List[str]) -> Optional[str]:
    """*text* with the scalar *value* under the key on line *start* moved to
    the first item of a block list, followed by *missing*. The key line
    keeps the comment. A value written on the key line alone keeps its text,
    quoting included; one continued onto further lines is written
    double-quoted in place of those lines, and one of those that is not a
    string is not rewritten. The Compositor's `yaml_list_add` writes the
    same bytes."""
    lines, newline = text.splitlines(keepends=True), _newline_of(text)
    ending = _ending(lines[start]) or newline
    rest = _EXCLUDE_LINE.match(_body(lines[start])).group('rest').strip()
    written, comment = _scalar_split(rest)
    try:
        alone = yaml.safe_load(f'exclude: {rest}')
        alone = isinstance(alone, dict) and _same_value(alone.get('exclude'), value)
    except yaml.YAMLError:
        alone = False
    if not alone and not isinstance(value, str):
        return None
    item = written if alone else json.dumps(value, ensure_ascii=False)
    replaced = 1 if alone else 1 + _continuation_count(lines, start)
    key = f'exclude: {comment}' if comment else 'exclude:'
    lines[start:start + replaced] = [f'{key}{ending}', f'  - {item}{ending}']
    return _into_block(''.join(lines), start, missing)


# The plain scalars YAML reads as null; an empty value is one too.
_NULL_TOKENS = frozenset(('', '~', 'null', 'Null', 'NULL'))


def _from_null(text: str, start: int, rest: str, missing: List[str]) -> Optional[str]:
    """*text* with *missing* as a block list under a key that holds null: a
    bare key keeps its line, and a written null is dropped from it, its
    comment kept. Any other null (a tagged one) is not rewritten. The
    Compositor's `yaml_list_add` writes the same bytes."""
    written, comment = _scalar_split(rest)
    if written not in _NULL_TOKENS:
        return None
    if written:
        lines = text.splitlines(keepends=True)
        key = f'exclude: {comment}' if comment else 'exclude:'
        lines[start] = key + _ending(lines[start])
        text = ''.join(lines)
    return _into_block(text, start, missing)


def _new_exclude_key(text: str, missing: List[str]) -> str:
    newline = _newline_of(text)
    lines = _ended(text.splitlines(keepends=True), newline)
    if lines:
        lines.append(newline)
    return ''.join(lines + [f'exclude:{newline}'] + _exclude_lines(missing, '  ', newline))


def _with_exclude_entries(text: str, value, missing: List[str]) -> Optional[str]:
    """*text* with *missing* added to its `exclude:`, in the shape it is
    written in, or None when the result would not read as intended."""
    if value is _ABSENT:
        updated = _new_exclude_key(text, missing)
    else:
        lines = text.splitlines(keepends=True)
        starts = [index for index, line in enumerate(lines)
                  if _EXCLUDE_LINE.match(_body(line))]
        rest = _EXCLUDE_LINE.match(_body(lines[starts[-1]])).group('rest').strip() \
            if starts else None
        if rest is None:
            return None
        if rest.startswith('['):
            updated = _into_flow(text, starts[-1], missing)
        elif value is None:
            updated = _from_null(text, starts[-1], rest, missing)
        elif not rest or rest.startswith('#'):
            updated = _into_block(text, starts[-1], missing)
        elif not isinstance(value, (list, dict)):
            updated = _from_scalar(text, starts[-1], value, missing)
        else:
            return None
    return updated if updated and _only_exclude_grew(text, updated, missing) else None


def _only_exclude_grew(before: str, after: str, missing: List[str]) -> bool:
    """Whether *after* reads as *before* with *missing* appended to its
    `exclude:` list, a scalar counting as a list of itself, and nothing
    else in the file changed."""
    try:
        old, new = yaml.safe_load(before) or {}, yaml.safe_load(after)
    except yaml.YAMLError:
        return False
    if not isinstance(new, dict) or not isinstance(old, dict):
        return False
    new_list = new.get('exclude')
    if not isinstance(new_list, list):
        return False
    if new_list != _as_list(old.get('exclude')) + missing:
        return False
    return _without_exclude(old) == _without_exclude(new)


def _as_list(value) -> list:
    """The entries `exclude:` holds: a list as written, a scalar as a list
    of itself, and nothing for a missing key, a null or a mapping."""
    if isinstance(value, list):
        return value
    if value is None or value is _ABSENT or isinstance(value, dict):
        return []
    return [value]


def _without_exclude(config: dict) -> dict:
    return {key: value for key, value in config.items() if key != 'exclude'}


def _read_config(path: str):
    """(text, value of `exclude`) or (None, None) when the file cannot be
    read as a mapping. An absent key reads as _ABSENT."""
    try:
        text = _read_text(path)
        config = yaml.safe_load(text)
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None, None
    if config is None:
        return text, _ABSENT
    if not isinstance(config, dict):
        return None, None
    return text, config.get('exclude', _ABSENT)


def add_exclude_entries(repo_root: str, lang: str) -> List[ChangeRecord]:
    """Add the four exclude entries the current template carries.

    `telar-content/texts/` is the one a site cannot do without: Jekyll
    otherwise renders every source the build generates a page from, and a
    pre-0.9.0 source that sets its own permalink lands on the generated
    page, which the conflict gate refuses. Failing to add it is therefore
    hard. The other three keep Telar's own tests out of the published site,
    and failing to add them is soft.

    The same shapes as the Compositor's `yaml_list_add`: a block list gets
    the entries appended at its own indentation, a flow list gets them
    inside its brackets, a missing key is added as a block list, a null
    written out (`~`, `null`) is dropped and filled like a bare key, a
    scalar is rewritten as a block list with the value first (even when it
    is already every entry), and a mapping is left alone and fails. Present means present in the parsed list (a
    scalar reading as a list of itself), with or without a trailing slash,
    so an entry the owner added by hand is not added again and one
    elsewhere in the file does not count.
    """
    path = os.path.join(repo_root, _CONFIG)
    text, value = _read_config(path)
    listed = _as_list(value)
    # An item that is not a string cannot be a path, and cannot be hashed
    # if it is a mapping or list, so it is never one of the entries.
    present = {_normalise_entry(entry) for entry in listed if isinstance(entry, str)}
    missing = [entry for entry in EXCLUDE_ENTRIES if _normalise_entry(entry) not in present]
    # Jekyll refuses an `exclude` that is not a list, so a single value is
    # rewritten as one even when it is already every entry.
    rewrite = value is not _ABSENT and value is not None and not isinstance(value, (list, dict))
    if not missing and not rewrite:
        return [_record(lang, 'v180_exclude_present', ', '.join(EXCLUDE_ENTRIES),
                        category=ChangeCategory.CONFIGURATION)]
    shaped = not isinstance(value, dict)
    updated = _with_exclude_entries(text, value, missing) if text is not None and shaped else None
    if updated is None:
        return _exclude_failures(lang, missing)
    _write_text(path, updated)
    return [_record(lang, 'v180_exclude_added', ', '.join(missing or listed),
                    category=ChangeCategory.CONFIGURATION)]


def _exclude_failures(lang: str, missing: List[str]) -> List[ChangeRecord]:
    records = []
    others = [entry for entry in missing if entry != 'telar-content/texts/']
    if 'telar-content/texts/' in missing:
        records.append(_record(lang, 'v180_exclude_texts_failed',
                               status=ChangeStatus.FAILED, severity='hard',
                               category=ChangeCategory.CONFIGURATION))
    if others:
        records.append(_record(lang, 'v180_exclude_others_failed', ', '.join(others),
                               status=ChangeStatus.FAILED,
                               category=ChangeCategory.CONFIGURATION))
    return records


# ---------------------------------------------------------------------- #
# Page sources: the layout and permalink the build supplies
# ---------------------------------------------------------------------- #

PAGES_DIR = 'telar-content/texts/pages'

# The values a page source may carry that say nothing the build does not
# already say. Any other value is the owner's, and is reported rather than
# removed: the build ignores it, and the report says where the page is.
_GENERATED_LAYOUTS = ('page', 'user-page')


def _redundant_keys(front: dict, stem: str) -> List[str]:
    keys = []
    if front.get('layout') in _GENERATED_LAYOUTS:
        keys.append('layout')
    if front.get('permalink') in (f'/{stem}/', f'/{stem}'):
        keys.append('permalink')
    return keys


def _published_at(front: dict, stem: str) -> str:
    """The address the build publishes a page source at.

    A localized sister is published under the name of the page it is
    localized for, so both languages share one address.
    """
    canonical = front.get('localized_for')
    if isinstance(canonical, str) and canonical.strip():
        stem = os.path.splitext(os.path.basename(canonical.strip()))[0]
    return f'/{stem}/'


def strip_page_sources(repo_root: str, lang: str) -> List[ChangeRecord]:
    """Remove the `layout` and `permalink` a page source repeats from the build.

    Soft throughout. The build ignores both keys whatever their value, so
    this is tidiness rather than safety: a source that keeps them builds
    correctly, and one whose keys come back through a round trip does too.
    """
    directory = os.path.join(repo_root, PAGES_DIR)
    if not os.path.isdir(directory):
        return [_record(lang, 'v180_pages_clean')]
    records = []
    for name in sorted(os.listdir(directory)):
        if name.endswith('.md'):
            records.extend(_strip_page_source(repo_root, lang, f'{PAGES_DIR}/{name}'))
    return records or [_record(lang, 'v180_pages_clean')]


def _strip_page_source(repo_root: str, lang: str, rel_path: str) -> List[ChangeRecord]:
    path = os.path.join(repo_root, rel_path)
    try:
        lines = _read_text(path).splitlines(keepends=True)
    except (OSError, UnicodeDecodeError) as error:
        return [_record(lang, 'v180_file_unreadable', rel_path, error,
                        status=ChangeStatus.FAILED)]
    bounds = _front_matter_bounds(lines)
    front = _load_mapping(lines[bounds[0] + 1:bounds[1]]) if bounds else None
    if front is None:
        return []
    stem = os.path.splitext(os.path.basename(rel_path))[0]
    records = _kept_page_keys(lang, rel_path, front, stem)
    drop = _redundant_keys(front, stem)
    if drop:
        records.append(_drop_page_keys(path, lang, rel_path, lines, bounds, front, drop))
    return records


def _kept_page_keys(lang, rel_path, front, stem) -> List[ChangeRecord]:
    redundant = _redundant_keys(front, stem)
    return [_record(lang, 'v180_page_key_kept', rel_path, key, front[key],
                    _published_at(front, stem))
            for key in ('layout', 'permalink')
            if key in front and key not in redundant]


def _drop_page_keys(path, lang, rel_path, lines, bounds, front, drop) -> ChangeRecord:
    start, end = bounds
    kept = _without_keys(lines[start + 1:end], drop)
    expected = {key: value for key, value in front.items() if key not in drop}
    named = ', '.join(f'`{key}`' for key in drop)
    if _load_mapping(kept) != expected:
        return _record(lang, 'v180_page_source_refused', rel_path, named,
                       status=ChangeStatus.FAILED)
    try:
        _write_text(path, ''.join(lines[:start + 1] + kept + lines[end:]))
    except OSError as error:
        return _record(lang, 'v180_file_unreadable', rel_path, error,
                       status=ChangeStatus.FAILED)
    return _record(lang, 'v180_page_keys_removed', named, rel_path)


# ---------------------------------------------------------------------- #
# Glossary markdown: `related_terms` written as one scalar
# ---------------------------------------------------------------------- #

GLOSSARY_DIR = 'telar-content/texts/glossary'

# A value opening with one of these is a flow collection, a block scalar,
# an anchor, an alias or a tag: YAML that a one-line rewrite cannot carry.
_UNREWRITABLE_OPENERS = ('[', '|', '>', '&', '*', '!')


def _related_terms_line(lines: List[str]) -> Optional[int]:
    """The index of the one `related_terms` line a rewrite may replace.

    None when the key is written twice, or continues onto indented lines,
    or holds YAML syntax a single line cannot carry, or a comment.
    """
    found = [index for index, line in enumerate(lines)
             if _top_level_key(line) == 'related_terms']
    if len(found) != 1:
        return None
    index = found[0]
    raw = _body(lines[index]).split(':', 1)[1].strip()
    if raw.startswith(_UNREWRITABLE_OPENERS) or ' #' in raw or '\t#' in raw:
        return None
    if index + 1 < len(lines) and _is_continuation(lines[index + 1]):
        return None
    return index


def split_related_terms(value: str) -> List[str]:
    """Split a scalar list of term ids on commas or pipes."""
    return [term.strip() for term in re.split(r'[,|]', value) if term.strip()]


def list_related_terms(repo_root: str, lang: str) -> List[ChangeRecord]:
    """Rewrite a scalar `related_terms` in glossary markdown as a flow list.

    The glossary layout iterates the value, and Liquid walks a string as a
    single item, so `primary-cord, subsidiary-cord` is looked up as one id
    that matches no term and the related-terms section renders empty. One
    line becomes one line; a value a single line cannot carry is refused
    and reported, since rewriting it is how a front matter is corrupted.
    Soft throughout.
    """
    directory = os.path.join(repo_root, GLOSSARY_DIR)
    records = []
    if os.path.isdir(directory):
        for name in sorted(os.listdir(directory)):
            if name.endswith('.md'):
                record = _list_related_terms_in(repo_root, lang, f'{GLOSSARY_DIR}/{name}')
                if record is not None:
                    records.append(record)
    return records or [_record(lang, 'v180_glossary_clean')]


def _list_related_terms_in(repo_root, lang, rel_path) -> Optional[ChangeRecord]:
    path = os.path.join(repo_root, rel_path)
    try:
        lines = _read_text(path).splitlines(keepends=True)
    except (OSError, UnicodeDecodeError) as error:
        return _record(lang, 'v180_file_unreadable', rel_path, error,
                       status=ChangeStatus.FAILED)
    bounds = _front_matter_bounds(lines)
    front = _load_mapping(lines[bounds[0] + 1:bounds[1]]) if bounds else None
    if not front or 'related_terms' not in front:
        return None
    value = front['related_terms']
    if isinstance(value, list) or value is None or value == '':
        return None
    rewritten = _rewrite_related_terms(lines, bounds, front, value)
    if rewritten is None:
        return _record(lang, 'v180_related_terms_refused', rel_path,
                       status=ChangeStatus.FAILED)
    try:
        _write_text(path, rewritten)
    except OSError as error:
        return _record(lang, 'v180_file_unreadable', rel_path, error,
                       status=ChangeStatus.FAILED)
    return _record(lang, 'v180_related_terms_listed', rel_path)


def _rewrite_related_terms(lines, bounds, front, value) -> Optional[str]:
    """The file with `related_terms` as a flow list, or None if refused."""
    if not isinstance(value, str):
        return None
    start, end = bounds
    body = lines[start + 1:end]
    index = _related_terms_line(body)
    terms = split_related_terms(value)
    if index is None or not terms:
        return None
    key = _body(body[index]).split(':', 1)[0]
    listed = ', '.join(json.dumps(term, ensure_ascii=False) for term in terms)
    body[index] = f'{key}: [{listed}]' + _ending(body[index])
    if _load_mapping(body) != dict(front, related_terms=terms):
        return None
    return ''.join(lines[:start + 1] + body + lines[end:])
