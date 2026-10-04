"""
Glossary Entry Kinds

A glossary entry is of one kind: a key term, a primary source, a person or
entity, a place, or a kind the site defines for itself. The core kinds live
in `_data/glossary_kinds.yml`, which the layouts also read: they label the
glossary panel and group the glossary page by the kind id the build writes
into each entry's page as `glossary_kind`. This module is the build's side
of that file. It turns what an author wrote in the glossary sheet's `kind`
column, or in a markdown entry's `kind:` / `tipo:` front matter, into a kind
id.

A value is compared with case, accents, underscores, hyphens and repeated
spaces folded away, so `Fuente primaria`, `fuente_primaria` and
`FUENTE PRIMARIA` are one value. A blank value is the default kind. A value
that names no kind is the default kind too, and the build says so, naming
the entry and the values it accepts: a typo in a cell otherwise files a
source among the key terms and nothing tells the author why.

The core file is read from beside the scripts rather than from the working
directory. It is the framework's own, like the scripts, and a build run
from anywhere else reads the same list the layouts do.

A site's own kinds are read from `glossary: kinds:` in the site's
`_config.yml`. Each has an `id`, a `label` for the panel and a `heading` for
the glossary page, both written in the site's language, and optional
`values`; its id is always a value. A site kind without a label or a
heading, or whose id or values are already a value of a core kind or of an
earlier site kind, is left out with a warning naming it: accepting it would
take entries from the kind that already owns the value. The accepted ones
follow the core kinds, in the order the config gives them, and
`write_site_kinds()` hands them to the layouts in `_data/`, where Liquid can
read them; the config key `glossary` is shadowed there by the glossary
collection.

Version: v1.8.0
"""

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

REGISTRY_PATH = Path(__file__).resolve().parents[2] / '_data' / 'glossary_kinds.yml'
SITE_CONFIG_PATH = Path('_config.yml')
SITE_KINDS_PATH = Path('_data') / 'glossary_site_kinds.json'


@lru_cache(maxsize=None)
def glossary_kinds():
    """The kinds, in the order the glossary page lists them."""
    with open(REGISTRY_PATH, 'r', encoding='utf-8') as f:
        return tuple(yaml.safe_load(f))


def default_kind():
    """The id of the kind a blank or unrecognised value resolves to."""
    return next(kind['id'] for kind in glossary_kinds() if kind.get('default'))


def _fold(value):
    """A value with case, accents and word separators folded away."""
    decomposed = unicodedata.normalize('NFKD', str(value))
    bare = ''.join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r'[\s_-]+', ' ', bare).strip().casefold()


@lru_cache(maxsize=None)
def _core_values():
    """Every folded value of a core kind, mapped to its kind id."""
    values = {}
    for kind in glossary_kinds():
        for value in [kind['id'], *kind.get('values', [])]:
            values[_fold(value)] = kind['id']
    return values


def _read_site_config():
    try:
        with open(SITE_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as e:
        print(f"  [WARN] Could not read _config.yml for glossary kinds: {e}")
        return {}


def _site_kind_problem(entry, taken):
    """Why a site kind cannot be accepted, or None when it can."""
    if not isinstance(entry, dict):
        return 'it is not a list item with an id, a label and a heading'
    for field in ('label', 'heading'):
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            return f'it has no {field}'
    values = entry.get('values', [])
    if values is None:
        values = []
    if not isinstance(values, list) or not all(isinstance(v, (str, int, float)) for v in values):
        return 'its values are not a list'
    for value in [entry['id'], *values]:
        owner = taken.get(_fold(value))
        if owner is not None:
            return f"'{value}' is already a value of the kind '{owner}'"
    return None


@lru_cache(maxsize=None)
def _site_kinds_for(config_key):
    """The site's accepted kinds, read once per config file state."""
    glossary = _read_site_config().get('glossary')
    if glossary is None:
        return ()
    kinds = glossary.get('kinds') if isinstance(glossary, dict) else None
    if kinds is None:
        return ()
    if not isinstance(kinds, list):
        print("  [WARN] glossary: kinds: in _config.yml is not a list, so "
              "the site's own glossary kinds are ignored.")
        return ()

    taken = dict(_core_values())
    accepted = []
    for entry in kinds:
        kind_id = entry.get('id') if isinstance(entry, dict) else None
        if not isinstance(kind_id, str) or not kind_id.strip():
            print("  [WARN] A glossary kind in _config.yml has no id, so it "
                  "is ignored.")
            continue
        kind_id = kind_id.strip()
        problem = _site_kind_problem({**entry, 'id': kind_id}, taken)
        if problem:
            print(f"  [WARN] The glossary kind '{kind_id}' in _config.yml is "
                  f"ignored: {problem}. Entries of it are listed as "
                  f"'{default_kind()}'.")
            continue
        values = [str(v) for v in (entry.get('values') or [])]
        for value in [kind_id, *values]:
            taken[_fold(value)] = kind_id
        accepted.append({'id': kind_id, 'label': entry['label'].strip(),
                         'heading': entry['heading'].strip(), 'values': values})
    return tuple(accepted)


def site_kinds():
    """The kinds the site defines in _config.yml and the build accepts."""
    try:
        stat = SITE_CONFIG_PATH.resolve().stat()
        key = (str(SITE_CONFIG_PATH.resolve()), stat.st_mtime_ns, stat.st_size)
    except FileNotFoundError:
        key = (str(SITE_CONFIG_PATH.resolve()), None, None)
    return _site_kinds_for(key)


def all_kinds():
    """The core kinds, then the site's, in the order the glossary page lists them."""
    return glossary_kinds() + site_kinds()


def _values():
    """Every folded value an author may write, mapped to its kind id."""
    values = dict(_core_values())
    for kind in site_kinds():
        for value in [kind['id'], *kind['values']]:
            values[_fold(value)] = kind['id']
    return values


def kind_text(kind_id, part):
    """A kind's panel label (`part='label'`) or page heading (`'heading'`),
    in the site's language.

    A core kind's comes from its language key, a site kind's as written.
    Returns None for an id that is no kind.
    """
    from telar.config import get_lang_string
    key_field = {'label': 'panel_label', 'heading': 'section_heading'}[part]
    for kind in all_kinds():
        if kind['id'] == kind_id:
            return kind[part] if part in kind else get_lang_string(kind[key_field])
    return None


def write_site_kinds(path=None):
    """Write the accepted site kinds where the layouts read them."""
    path = Path(path) if path is not None else SITE_KINDS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    kinds = [{'id': k['id'], 'label': k['label'], 'heading': k['heading']}
             for k in site_kinds()]
    path.write_text(json.dumps(kinds, indent=2, ensure_ascii=False) + '\n',
                    encoding='utf-8')
    return kinds


def _is_blank(value):
    # pandas hands a missing cell over as NaN, which is the one value not
    # equal to itself.
    return value is None or value != value or not str(value).strip()


def resolve_kind(value, where=None):
    """The kind id an author's value names.

    Args:
        value: What the author wrote, or None / NaN / '' for nothing.
        where: Which entry the value belongs to, for the warning, e.g.
            "glossary entry 'carta'".

    Returns:
        str: The id of a core kind or of a site kind.
    """
    if _is_blank(value):
        return default_kind()
    kind = _values().get(_fold(value))
    if kind is not None:
        return kind

    accepted = ', '.join(kind['id'] for kind in all_kinds())
    subject = f"{where} has" if where else "A glossary entry has"
    print(f"  [WARN] {subject} kind '{value}', which is not a kind Telar "
          f"knows, so it is listed as '{default_kind()}'. Write one of: "
          f"{accepted}, or leave it blank.")
    return default_kind()
