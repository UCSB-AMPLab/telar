"""Merging a site's own settings into the release's _config.yml.

The chain reaches the current configuration by editing a site's file
twelve times over: insert this key after that one, rename a section, move
a block above a line, retune a default. The anchors are what make it
fragile — one release's insertion deleted every comment above the Google
Sheets block, and the release after it spent two hundred lines putting
them back.

Merging instead of editing removes the anchors. The release's file is the
shape; a site's own values are written into it. Nothing hunts for a line
to insert after, because nothing is inserted.

A site's file is read with a real YAML parser, because it is arbitrary:
it may hold escaped quotes, block scalars, flow mappings, duplicate keys
or a byte-order mark, and a hand-written scanner gets each of those
wrong in a way that ends with a file Jekyll cannot build. The release's
file is scanned line by line, because it is ours and its shape is known,
and because scanning is what keeps its comments and order intact.

A value for a key the release also has is spliced in as the site spelt
it, but only when that text provably parses back to what the parser
read. That check is what makes the two readings agree, and it is what
rejects a scalar the scanner cut short or an alias whose anchor is not
in the fragment. Quoting and spacing survive it, so an upgrade does not
rewrite every line of a file the owner recognises.

A key the release does NOT have is emitted, never copied. Copying its
lines was tried and gave up an alias whose anchor had been retired and
an unquoted key holding a colon — two ways to write a file Jekyll
cannot read. The cost is that a comment a site wrote above its own key
does not survive; its value does.

Three rules decide each key:

- A key the site sets keeps the site's value, spelt exactly as the site
  spelt it. Its comment comes from the release.
- A key the site does not set takes the release's value, which is the
  framework's default — except for the keys that identify a particular
  site. The release file is also the live demo site, so its url, its
  story key and its Google Sheet are in it. Those get an empty value
  rather than the demo's.
- A key the site has that the release does not is carried across whole,
  with whatever comment the site wrote above it.

Version: v1.7.0
"""

import re
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

import yaml

# A mapping key at the start of a line. Comments and blank lines do not
# match, which is what keeps them out of the walk.
KEY_LINE = re.compile(r'^(\s*)([A-Za-z_][A-Za-z0-9_-]*):(.*)$')

# A sequence item. Everything inside one is left alone: the keys within
# repeat across items, so a path cannot name one of them. Reading
# `defaults:` as a mapping gave every entry in it the last entry's layout.
SEQUENCE_ITEM = re.compile(r'^(\s*)-(\s|$)')

# Lists the release names but a site may add to. Its entries are kept and
# the site's own appended: a site excluding its private drafts must go on
# excluding them, and a site with an extra plugin must keep it. Every
# other list — `defaults`, which the release restructures — stays the
# release's, because a site's older one would strip what has been added.
EXTENSIBLE_LISTS = {
    ('exclude',),
    ('plugins',),
}

# Keys naming a particular site rather than a framework default. The
# release file is the demo site's own, so leaving these to it would hand
# every site the demo's URL and the demo's spreadsheet.
NEUTRAL_VALUES = {
    ('title',): '""',
    ('description',): '""',
    ('url',): '""',
    ('baseurl',): '""',
    ('author',): '""',
    ('email',): '""',
    ('logo',): '""',
    ('story_key',): '""',
    ('google_sheets', 'enabled'): 'false',
    ('google_sheets', 'published_url'): '""',
    # v0.8.0 shipped this off; the demo turns it on.
    ('collection_interface', 'show_sample_on_homepage'): 'false',
    # A site that predates demo content has not asked for it, and the
    # release ships it on. The heuristic this replaces reached the same
    # answer in every branch but one: demo stories are only wanted by a
    # site that already had them, unmodified, alongside its own.
    ('story_interface', 'include_demo_content'): 'false',
}

# The version stamp belongs to the migration, which writes it once the
# upgrade has finished. Taking the release's value here would stamp the
# site at the target the moment the config is merged — before the
# framework is installed, and whether or not the rest of the hop
# completes. The site's own version is kept, and the stamp overwrites it
# at the end.
FROZEN_KEYS = set()

# Keys the framework has dropped. A site that still has one is not
# carried across: v0.3.0 emptied the telar section of fields nothing ever
# read, and v0.3.4 removed the OpenSeadragon block outright.
RETIRED_KEYS = {
    ('openseadragon',),
    ('telar', 'project_title'),
    ('telar', 'tagline'),
    ('telar', 'primary_color'),
    ('telar', 'secondary_color'),
    ('telar', 'font_headings'),
    ('telar', 'font_body'),
    ('telar', 'logo'),
    # v0.9.0 took the second Google Sheets URL out; the single
    # published_url replaced it and the release has no line for it.
    ('google_sheets', 'shared_url'),
}

# Keys that changed name or place. The site's value follows the key.
# These compose: a v0.6.1 site's testing-features.hide_stories is first a
# development-features section, then a skip_stories key inside it.
MOVED_KEYS = {
    ('show_story_steps',): ('story_interface', 'show_story_steps'),
    ('testing-features',): ('development-features',),
    ('development-features', 'hide_stories'):
        ('development-features', 'skip_stories'),
    ('development-features', 'hide_collections'):
        ('development-features', 'skip_collections'),
}

CARRIED_HEADING = '# Settings this site added'


class Entry(NamedTuple):
    """One `key:` line, and where its value sits inside it."""
    index: int
    indent: int
    path: Tuple[str, ...]
    value: str
    span: Optional[Tuple[int, int]]   # value offsets within the line

    @property
    def opens(self) -> bool:
        """True when the key introduces a block rather than a value."""
        return self.span is None


def _value_span(line: str, start: int) -> Optional[Tuple[int, int]]:
    """Where the value sits in a line, or None when there is no value.

    A `#` only begins a comment outside quotes and after whitespace, so a
    URL fragment or a hash inside a description stays part of the value.
    """
    quote = None
    end = len(line)
    for offset in range(start, len(line)):
        character = line[offset]
        if quote:
            if character == quote:
                quote = None
        elif character in '"\'':
            quote = character
        elif character == '#' and (offset == start or line[offset - 1] in ' \t'):
            end = offset
            break

    stripped = line[start:end]
    leading = len(stripped) - len(stripped.lstrip())
    value = stripped.strip()
    if not value:
        return None
    return start + leading, start + leading + len(value)


def parse(text: str) -> List[Entry]:
    """Every key line in a configuration file, with its path."""
    entries = []
    stack: List[Tuple[int, str]] = []
    block_indent = None
    sequence_indent = None

    for index, line in enumerate(text.split('\n')):
        indented = len(line) - len(line.lstrip())

        if block_indent is not None:
            if line.strip() and indented > block_indent:
                continue
            block_indent = None

        if sequence_indent is not None:
            if not line.strip() or indented > sequence_indent:
                continue
            if SEQUENCE_ITEM.match(line) and indented == sequence_indent:
                continue
            sequence_indent = None

        if SEQUENCE_ITEM.match(line):
            sequence_indent = indented
            continue

        match = KEY_LINE.match(line)
        if match is None:
            continue

        indent = len(match.group(1))
        while stack and stack[-1][0] >= indent:
            stack.pop()

        key = match.group(2)
        path = tuple(name for _, name in stack) + (key,)
        span = _value_span(line, match.end(2) + 1)
        entries.append(Entry(index, indent, path, line[span[0]:span[1]]
                             if span else '', span))

        if span is None:
            stack.append((indent, key))
        elif line[span[0]] in '|>':
            block_indent = indent

    return entries


def _block(lines: List[str], entry: Entry, entries: List[Entry]) -> Tuple[int, int]:
    """The lines belonging to one key, comments above it included."""
    start = entry.index
    while start > 0:
        above = lines[start - 1].strip()
        # Not the heading a previous merge wrote: absorbing it would add a
        # second one on the next run, and a third on the one after.
        if above.startswith('#') and above != CARRIED_HEADING:
            start -= 1
            continue
        break

    end = entry.index + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and (len(line) - len(line.lstrip())) <= entry.indent:
            break
        end += 1

    while end > entry.index + 1 and not lines[end - 1].strip():
        end -= 1
    return start, end


def _parent_end(lines: List[str], parent: Entry) -> int:
    """Where a block ends, so a new key can be added to the end of it."""
    end = parent.index + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and (len(line) - len(line.lstrip())) <= parent.indent:
            break
        end += 1
    while end > parent.index + 1 and not lines[end - 1].strip():
        end -= 1
    return end


def read_site(site: str) -> Optional[Dict[Tuple[str, ...], Any]]:
    """Every path in a site's configuration, read by the YAML parser.

    Returns None when the file does not parse. A site whose _config.yml
    is already broken is not one to rewrite: the merge would turn an
    error the owner can see into a file that looks repaired.
    """
    try:
        loaded = yaml.safe_load(site.lstrip('\ufeff'))
    except yaml.YAMLError:
        return None
    if not isinstance(loaded, dict):
        return None
    return _flatten(loaded)


def _flatten(value: Any, prefix: Tuple[str, ...] = ()) -> Dict[Tuple[str, ...], Any]:
    """Path-to-value for every key, however the file spelt it."""
    found = {}
    if isinstance(value, dict):
        for key, child in value.items():
            path = prefix + (str(key),)
            found[path] = child
            found.update(_flatten(child, path))
    return found


def _emit(value: Any) -> str:
    """One value as YAML text, safe to put on a key's line.

    Always one line. A string holding newlines dumps by default as a
    multi-line scalar, and splicing that into a line of the release's
    file puts its continuation where the next key belongs.
    """
    def dump(**style):
        text = yaml.safe_dump(value, default_flow_style=True,
                              allow_unicode=True, width=10 ** 9,
                              **style).strip()
        return text[:-3].strip() if text.endswith('...') else text

    text = dump()
    if '\n' in text:
        text = dump(default_style='"')
    return text


def _emitted(value: Any) -> Optional[str]:
    """One value as YAML text, or None when it will not survive the trip."""
    try:
        text = _emit(value)
    except yaml.YAMLError:
        return None
    try:
        return text if yaml.safe_load(f'value: {text}') == {'value': value} \
            else None
    except yaml.YAMLError:
        return None


def _as_written(raw: Optional[Entry], value: Any) -> Optional[str]:
    """The site's own text when it means what the parser read.

    Raw text that does not parse back to the same value is text the line
    scan misread — an escaped quote it cut short, a block scalar whose
    body it never saw, an alias whose anchor is not in the fragment.
    Emitting is then the only honest answer.
    """
    if raw is not None and not raw.opens:
        try:
            if yaml.safe_load(f'value: {raw.value}') == {'value': value}:
                return raw.value
        except yaml.YAMLError:
            pass
    return _emitted(value)


def _write_release_keys(lines: List[str], template_entries: List[Entry],
                        values: Dict[Tuple[str, ...], Any],
                        raw_by_path: Dict[Tuple[str, ...], Entry]) -> List[str]:
    """Rules one and two, in place: each key the release names takes the
    site's value, the framework's default, or nothing of the demo site's.

    A key the site sets but whose value is a section, or whose text will not
    parse back to what the parser read, keeps the release's value and earns a
    note. Both are refusals to guess.
    """
    notes = []
    for entry in template_entries:
        if entry.opens or entry.path in FROZEN_KEYS:
            continue

        named = ".".join(entry.path)
        if entry.path in values:
            held = values[entry.path]
            if isinstance(held, (dict, list)):
                notes.append(f'{named} is a section on this site and a single '
                             'value in the release — left as the release has it')
                continue
            replacement = _as_written(raw_by_path.get(entry.path), held)
            if replacement is None:
                notes.append(f'{named} could not be written back as YAML — '
                             'left as the release has it')
                continue
        elif entry.path in NEUTRAL_VALUES:
            replacement = NEUTRAL_VALUES[entry.path]
        else:
            continue

        if replacement == entry.value:
            continue
        start, end = entry.span
        lines[entry.index] = lines[entry.index][:start] + replacement + \
            lines[entry.index][end:]
    return notes


def _extend_lists(lines: List[str], template_entries: List[Entry],
                  values: Dict[Tuple[str, ...], Any],
                  ) -> Tuple[Dict[int, List[str]], List[str]]:
    """The lists a site may extend keep the release's entries and gain the
    site's; the rest stay the release's.

    A site's older `defaults` would strip the collections added since, which
    is why extending is allowed by name rather than in general.
    """
    insertions: Dict[int, List[str]] = {}
    notes = []
    for entry in template_entries:
        if not entry.opens or entry.path not in values:
            continue
        held = values[entry.path]
        if not isinstance(held, list):
            continue

        named = ".".join(entry.path)
        if entry.path not in EXTENSIBLE_LISTS:
            notes.append(f'{named} is a list the release owns; this site'
                         "'s own is not carried across")
            continue

        release_list = _flatten_template_list(lines, entry)
        added = [item for item in held if item not in release_list]
        if not added:
            continue
        emitted = [_emitted(item) for item in added]
        if any(text is None for text in emitted):
            notes.append(f'{named} holds something that could not be written '
                         'back as YAML — left as the release has it')
            continue
        indent = ' ' * entry.indent
        insertions.setdefault(_parent_end(lines, entry), []).extend(
            f'{indent}  - {text}' for text in emitted)
        notes.append(f'Kept this site\'s own {named} entries: '
                     + ', '.join(str(item) for item in added))
    return insertions, notes


def _carry_unknown_keys(lines: List[str],
                        values: Dict[Tuple[str, ...], Any],
                        template_paths: set,
                        template_by_path: Dict[Tuple[str, ...], Entry],
                        ) -> Tuple[Dict[int, List[str]], List[str], List[str]]:
    """Rule three: keys the site has and the release does not.

    Returns the insertions to make, the block to append at the end, and the
    notes. A key whose parent section the release does have goes inside it;
    without that it would land at the top level, and the section it was
    reported as joining would not contain it.
    """
    insertions: Dict[int, List[str]] = {}
    notes = []
    trailing: List[str] = []

    # A key inside a section the release does not have travels with the
    # section, not on its own.
    unknown_sections = {path for path, value in values.items()
                        if isinstance(value, dict)
                        and path not in template_paths}
    carried = [
        path for path in values
        if path not in template_paths
        and not any(path[:depth] in unknown_sections
                    for depth in range(1, len(path)))
    ]

    for path in carried:
        emitted = _emitted({path[-1]: values[path]})
        if emitted is None:
            notes.append(f'{".".join(path)} could not be written back as '
                         'YAML and was not carried across')
            continue
        block = [emitted[1:-1].strip() if emitted.startswith('{')
                 else emitted]
        parent_path = path[:-1]
        parent = template_by_path.get(parent_path) if parent_path else None
        if parent_path and parent is not None and parent.opens:
            indent = ' ' * (parent.indent + 2)
            insertions.setdefault(_parent_end(lines, parent), []).extend(
                f'{indent}{line}' for line in block)
            notes.append(f'Carried {".".join(path)} across into '
                         f'{".".join(parent_path)}')
        else:
            trailing.extend(block)
            notes.append(f'Carried {".".join(path)} across — the release does '
                         'not have it')
    return insertions, trailing, notes


def merge(template: str, site: str) -> Tuple[str, List[str]]:
    """Write a site's settings into the release's configuration file.

    Returns the merged text and a description of what was carried across
    that the release does not itself have.

    The three rules are one function each, in the order they run. Only
    `lines` is shared: it is the document being built, and the two later
    rules read it to find where a section ends.
    """
    values = read_site(site)
    if values is None:
        return site, ['Kept _config.yml as it is — it could not be read as '
                      'YAML, so nothing could be moved across safely']

    values = {_moved(path): value for path, value in values.items()
              if not _retired(_moved(path))}

    template_entries = parse(template)
    site_entries = [entry._replace(path=_moved(entry.path))
                    for entry in parse(site)]
    raw_by_path = {entry.path: entry for entry in site_entries}
    template_paths = {entry.path for entry in template_entries}
    template_by_path = {entry.path: entry for entry in template_entries}

    lines = template.split('\n')

    notes = _write_release_keys(lines, template_entries, values, raw_by_path)

    list_insertions, list_notes = _extend_lists(lines, template_entries, values)
    notes += list_notes

    key_insertions, trailing, key_notes = _carry_unknown_keys(
        lines, values, template_paths, template_by_path)
    notes += key_notes

    # Every insertion is applied at the end, in descending order. Inserting
    # as we go would leave every later entry.index pointing a few lines above
    # where its key had moved to.
    insertions: Dict[int, List[str]] = {}
    for source in (list_insertions, key_insertions):
        for index, block in source.items():
            insertions.setdefault(index, []).extend(block)
    for index in sorted(insertions, reverse=True):
        lines[index:index] = insertions[index]

    if trailing:
        while lines and not lines[-1].strip():
            lines.pop()
        lines.extend(['', CARRIED_HEADING] + trailing)

    return '\n'.join(lines), notes



def _moved(path: Tuple[str, ...]) -> Tuple[str, ...]:
    """Where a key lives now, following renames until none applies."""
    for _ in range(len(MOVED_KEYS) + 1):
        for old, new in MOVED_KEYS.items():
            if path[:len(old)] == old:
                path = new + path[len(old):]
                break
        else:
            break
    return path


def _retired(path: Tuple[str, ...]) -> bool:
    """True when the framework no longer has this key, at any depth."""
    return any(path[:depth] in RETIRED_KEYS
               for depth in range(1, len(path) + 1))


def _flatten_template_list(lines: List[str], entry: Entry) -> List[Any]:
    """The release's own value for a list key."""
    end = _parent_end(lines, entry)
    text = '\n'.join(lines[entry.index:end])
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    if isinstance(loaded, dict):
        value = loaded.get(entry.path[-1])
        return value if isinstance(value, list) else []
    return []
