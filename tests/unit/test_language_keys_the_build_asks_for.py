"""Unit Tests for the Language Catalogues and What Asks For Them

Both directions. A key the build asks for and no catalogue has renders as its
own dotted path to a reader; a key a catalogue has and nothing asks for costs
a translation, gets reviewed, and says nothing. The first is a defect on the
page, the second a slow tax on everyone who maintains the Spanish.

`get_lang_string` returns the key path when it cannot resolve one, so a key
that exists in no catalogue renders as the literal string
`errors.object_warnings.missing_object_id` on the page. Nothing fails; the
build is green and the reader is shown a dotted path.

The parity guards cannot see this. `test_message_catalogue_languages.py`
checks both directions — every English key has Spanish, no Spanish key is
without English — and both hold, because the key is absent from *both*
catalogues and the two agree perfectly about not having it. A parity test
compares the catalogues to each other. Nothing compared them to what the
code asks for.

Read from the syntax tree rather than by searching for quoted strings. A
first sweep by regex reported three missing keys and two were its own fault:
`errors.missing` is a key name inside a docstring example in `config.py`, and
a bare `errors.object_warnings.` came from a pattern boundary rather than
from any call. Only the third survived checking, and a grep-shaped guard
would report the docstring on every run.

A key built at runtime — an f-string, a variable, a concatenation — cannot be
read from the call, and skipping it is how a sweep comes to answer a
confident number about keys it never looked at. Each such family is declared
below with the source its parts come from, that source is read rather than
copied, and every key it can produce is resolved like any other. A call
building a key from anything not declared fails, so a new family is a
deliberate act rather than a silent hole.

@version v1.8.0
"""

import ast
import pathlib
import re

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = REPO / 'scripts'
LANGUAGES = REPO / '_data' / 'languages'

# Call sites building their key at runtime, by file and line, each paired with
# the keys it can produce. Every one is read from the source rather than
# restated here, so a code changing its own set moves this with it.
DYNAMIC_CALLS = {
    ('telar/processors/objects/remote.py', 'iiif_{code}'),
    ('telar/processors/objects/remote.py', 'short_{code}'),
    ('telar/processors/stories.py', 'answer kinds'),
    # kind_text() reads a core glossary kind's panel_label or section_heading,
    # which GLOSSARY_KIND_KEYS below reads from the registry.
    ('telar/glossary_kinds.py', 'glossary kind keys'),
}


def _known_http_codes():
    """The status codes remote.py names its own messages for.

    Read from the `known_codes` tuple in the source, so adding a status there
    without writing its two strings fails here rather than rendering the key
    path to an author.
    """
    tree = ast.parse((SCRIPTS / 'telar/processors/objects/remote.py').read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and any(getattr(t, 'id', None) == 'known_codes' for t in node.targets)):
            return [e.value for e in node.value.elts]
    raise AssertionError('known_codes is no longer a tuple literal in remote.py')


def _answer_kind_keys():
    """The keys `_report_answer` is called with, from the module's own map."""
    import sys
    sys.path.insert(0, str(SCRIPTS))
    from telar.processors.stories import _ANSWER_KIND_KEYS
    return list(_ANSWER_KIND_KEYS.values()) + ['answer_over_hard_limit']


def _dynamic_keys():
    """Every key the runtime-built call sites can produce."""
    keys = []
    for code in _known_http_codes():
        keys.append(f'errors.object_warnings.iiif_{code}')
        keys.append(f'errors.object_warnings.short_{code}')
    for key in _answer_kind_keys():
        keys.append(f'errors.object_warnings.{key}')
    return keys


def _catalogue(code):
    return yaml.safe_load((LANGUAGES / f'{code}.yml').read_text(encoding='utf-8'))


def _resolve(catalogue, key_path):
    """Walk a dotted path, the way get_lang_string does."""
    value = catalogue
    for key in key_path.split('.'):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _lang_string_calls():
    """Every `get_lang_string(...)` call in scripts/, from the syntax tree.

    Yields `(path, lineno, key_or_None)` — the key is None where the first
    argument is not a plain string literal.
    """
    for path in sorted(SCRIPTS.rglob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, 'id', None) or getattr(func, 'attr', None)
            if name != 'get_lang_string' or not node.args:
                continue
            first = node.args[0]
            key = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
            yield path, node.lineno, key


# The glossary layouts read the keys each glossary kind names — its panel
# label, section heading and intro — through `_data/glossary_kinds.yml`, as
# `lang[section][key]`, which no pattern over the templates can follow. They
# are read from that file, so a kind added there is held to both directions.
GLOSSARY_KINDS = REPO / '_data' / 'glossary_kinds.yml'
GLOSSARY_KIND_KEY_FIELDS = ('panel_label', 'section_heading', 'intro')


def _glossary_kind_keys():
    kinds = yaml.safe_load(GLOSSARY_KINDS.read_text(encoding='utf-8'))
    return sorted({kind[field] for kind in kinds
                   for field in GLOSSARY_KIND_KEY_FIELDS if kind.get(field)})


ALL_CALLS = list(_lang_string_calls())
LITERAL_CALLS = [(p, n, k) for p, n, k in ALL_CALLS if k is not None]
DYNAMIC_KEYS = _dynamic_keys()
GLOSSARY_KIND_KEYS = _glossary_kind_keys()


def test_the_sweep_finds_the_call_sites():
    # A guard that reads nothing passes for the wrong reason. The floors are
    # well under the real counts and are here to catch a sweep that has
    # stopped seeing, not to be kept in step with the code.
    assert len(ALL_CALLS) > 25
    assert len(DYNAMIC_KEYS) > 10
    assert len(GLOSSARY_KIND_KEYS) >= 6


@pytest.mark.parametrize('code', ['en', 'es'])
def test_every_key_the_build_asks_for_resolves(code):
    catalogue = _catalogue(code)
    missing = [
        f'{path.relative_to(SCRIPTS.parent)}:{lineno} asks for {key!r}'
        for path, lineno, key in LITERAL_CALLS
        if _resolve(catalogue, key) is None
    ]
    assert not missing, (
        f'{len(missing)} key(s) absent from {code}.yml, which get_lang_string '
        f'renders as the key path itself:\n  ' + '\n  '.join(missing)
    )


@pytest.mark.parametrize('code', ['en', 'es'])
def test_every_key_resolves_to_a_string_rather_than_a_branch(code):
    # A path that stops on a dict resolves without raising, and renders as
    # "{'short_404': ...}" on the page. Absent and half-present fail the same
    # way for a reader, so they fail the same way here.
    catalogue = _catalogue(code)
    branches = [
        f'{path.relative_to(SCRIPTS.parent)}:{lineno} asks for {key!r}'
        for path, lineno, key in LITERAL_CALLS
        if isinstance(_resolve(catalogue, key), dict)
    ]
    assert not branches, (
        f'{len(branches)} key(s) in {code}.yml name a group rather than a '
        f'string:\n  ' + '\n  '.join(branches)
    )


@pytest.mark.parametrize('code', ['en', 'es'])
def test_every_key_built_at_runtime_resolves_too(code):
    catalogue = _catalogue(code)
    missing = [key for key in DYNAMIC_KEYS if not isinstance(_resolve(catalogue, key), str)]
    assert not missing, (
        f'{len(missing)} key(s) a runtime-built call can produce are absent '
        f'from {code}.yml:\n  ' + '\n  '.join(missing)
    )


@pytest.mark.parametrize('code', ['en', 'es'])
def test_every_key_a_glossary_kind_names_resolves(code):
    catalogue = _catalogue(code)
    missing = [key for key in GLOSSARY_KIND_KEYS
               if not isinstance(_resolve(catalogue, key), str)]
    assert not missing, (
        f'{len(missing)} key(s) named in _data/glossary_kinds.yml are absent '
        f'from {code}.yml:\n  ' + '\n  '.join(missing)
    )


# ── The other direction: keys no one asks for ───────────────────────────────

# Liquid reaches a string two ways, and both are matchable: `lang.a.b` in a
# layout, `include.lang.a.b` in an include that was handed the catalogue.
# The left boundary keeps a variable whose name ends in `lang` — `iiif_lang.heading` —
# from reading as `lang.heading`.
LIQUID_ACCESS = re.compile(r'(?<![\w.])(?:include\.)?lang\.([a-z_][a-z_0-9]*(?:\.[a-z_0-9]+)*)')

# Where Liquid can read a catalogue: the layouts and includes, and any other
# file Jekyll renders, which is one that opens with front matter. Not
# `scripts/` — Python asks through get_lang_string, which the forward direction
# above already reads. A file without front matter is copied as it is, so a
# `lang.` in it — CHANGELOG.md naming a key it removed — is prose, not a read.
TEMPLATE_ROOTS = ('_layouts', '_includes')
RENDERED_ROOTS = ('_sass', 'assets', 'pages', '.')
TEMPLATE_SUFFIXES = {'.html', '.md', '.js', '.scss', '.liquid'}

# Liquid runs only inside its own delimiters. Outside them, `lang.` is page
# text or, in a script, a JavaScript property: `data.lang.play` reads the
# object the layout built, and that layout's own `lang.object.…` is the read.
LIQUID_TAGS = re.compile(r'{{.*?}}|{%.*?%}', re.S)

# `{% assign iiif_lang = lang.errors.iiif_mismatch %}` names a section, and the
# file then reads strings through the alias. Counting the assign as a read of
# the section would mark every string under it as read, dead or not.
LIQUID_ALIAS = re.compile(
    r'{%-?\s*assign\s+([a-z_][a-z_0-9]*)\s*=\s*(?:include\.)?lang\.'
    r'([a-z_][a-z_0-9]*(?:\.[a-z_0-9]+)*)\s*-?%}')

# Keys deliberately kept without a reader. Empty, and it should stay that way:
# a string nobody reads is either wanted by something not yet written, in which
# case it belongs in that change, or it is dead. An entry here needs a reason
# beside it saying which.
KEPT_WITHOUT_A_READER = set()


def _renders(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read(3) == '---'


def _template_files():
    for name in TEMPLATE_ROOTS:
        for path in (REPO / name).rglob('*'):
            if path.is_file() and path.suffix in TEMPLATE_SUFFIXES:
                yield path
    for name in RENDERED_ROOTS:
        root = REPO / name
        paths = root.glob('*') if name == '.' else root.rglob('*')
        for path in paths:
            if (path.is_file() and path.suffix in TEMPLATE_SUFFIXES
                    and _renders(path)):
                yield path


# Comments name keys without reading them, and one of them names a namespace
# with a wildcard — `lang.share.* / lang.buttons.*` in share-panel.html's
# header, which yields the bare paths `share` and `buttons` and, through the
# ancestor rule below, marks every string under both as read. That single line
# hid fourteen dead `share.*` keys from the first version of this sweep.
COMMENTS = re.compile(r'<!--.*?-->|{%-?\s*comment\s*-?%}.*?{%-?\s*endcomment\s*-?%}', re.S)


def _reads_in(text):
    """The catalogue paths one template's Liquid reads."""
    text = COMMENTS.sub(' ', text)
    tags = LIQUID_TAGS.findall(text)
    aliases = {}
    for tag in tags:
        alias = LIQUID_ALIAS.fullmatch(tag.strip())
        if alias:
            aliases[alias.group(1)] = alias.group(2)
    found = set()
    for tag in tags:
        if LIQUID_ALIAS.fullmatch(tag.strip()):
            continue
        found.update(m.group(1) for m in LIQUID_ACCESS.finditer(tag))
        for name, section in aliases.items():
            for m in re.finditer(rf'(?<![\w.]){name}(\.[a-z_][a-z_0-9.]*|\s*\[|)', tag):
                rest = m.group(1)
                # `iiif_lang.heading` reads one string; `iiif_lang[key]` or the
                # bare name handed on reads the whole section.
                found.add(section + rest if rest.startswith('.') else section)
    return found


def _paths_liquid_asks_for():
    found = set()
    for path in _template_files():
        found |= _reads_in(path.read_text(encoding='utf-8', errors='replace'))
    return found


def _is_open_domain(key_path):
    """True where a page's front matter can name this key and we cannot see it.

    `_layouts/default.html` resolves a browser-tab title from a page's
    `title_key`, which is author-supplied, so a site this repository has never
    seen can name a key the framework does not. The layout reads only
    `navigation.<leaf>`, and `generate_collections.py` warns about any other
    value, so `navigation.*` is the one open section. Everything else in the
    catalogue is the framework's own, and a key nothing here reads is dead.
    """
    parts = key_path.split('.')
    return len(parts) == 2 and parts[0] == 'navigation'


def _leaf_paths(node, prefix=''):
    """Every dotted path in a catalogue that ends at a string."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaf_paths(value, f'{prefix}.{key}' if prefix else str(key))
    else:
        yield prefix


def _asked_for():
    """Every path anything asks for, by any of the four routes."""
    literal = {key for _path, _lineno, key in LITERAL_CALLS}
    return (_paths_liquid_asks_for() | literal | set(DYNAMIC_KEYS)
            | set(GLOSSARY_KIND_KEYS))


ASKED_FOR = _asked_for()


def _is_reached(key_path):
    """True when this key, or a group containing it, is asked for.

    A template that hands JavaScript a whole branch — `lang.object.viewer` into
    the object page's data block — reaches every string under it, so an
    ancestor counts.
    """
    if key_path in ASKED_FOR:
        return True
    parts = key_path.split('.')
    return any('.'.join(parts[:i]) in ASKED_FOR for i in range(1, len(parts)))


def test_the_liquid_sweep_finds_the_templates_reading_the_catalogue():
    """A regex that has stopped matching reports every key as unused, which
    reads as a large cleanup rather than as a broken sweep. The floor is well
    under the real count and is here to catch that, not to track it."""
    assert len(_paths_liquid_asks_for()) > 100


def _resolves(catalogue, key_path):
    node = catalogue
    for part in key_path.split('.'):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


@pytest.mark.parametrize('code', ['en', 'es'])
def test_every_key_a_template_reads_is_in_the_catalogue(code):
    """A Liquid read of a missing key renders its `| default:` or nothing.

    Where the default is English, a Spanish site shows English and no build
    says so. The Python calls are held to this above; this is the templates.
    """
    catalogue = _catalogue(code)
    missing = sorted(key for key in _paths_liquid_asks_for()
                     if not _resolves(catalogue, key))
    assert not missing, (
        f'{len(missing)} key(s) a template reads are not in {code}.yml:\n  '
        + '\n  '.join(missing))


def test_the_sweep_matches_the_whole_path_rather_than_the_leaf_name():
    """`errors.no_image` is read by two templates and `object.no_image` by
    nothing. A sweep keyed on the leaf name clears both, and deleting a string
    a reader sees is the way this guard does damage."""
    assert 'errors.no_image' in ASKED_FOR
    assert 'object.no_image' not in ASKED_FOR


@pytest.mark.parametrize('code', ['en', 'es'])
def test_no_catalogue_key_goes_unread(code):
    catalogue = _catalogue(code)
    unread = sorted(
        key for key in _leaf_paths(catalogue)
        if not _is_reached(key)
        and not _is_open_domain(key)
        and key not in KEPT_WITHOUT_A_READER
    )
    assert not unread, (
        f'{len(unread)} key(s) in {code}.yml are reached by no template and no '
        f'call. Each costs a translation and a review and shows nobody '
        f'anything:\n  ' + '\n  '.join(unread)
    )


def test_no_call_builds_a_key_this_guard_cannot_follow():
    # A family not in DYNAMIC_CALLS is a set of keys nothing checks. Declaring
    # one means teaching _dynamic_keys where its parts come from.
    undeclared = sorted({
        str(path.relative_to(SCRIPTS))
        for path, _lineno, key in ALL_CALLS if key is None
    } - {f for f, _ in DYNAMIC_CALLS})
    assert not undeclared, (
        'call(s) build their key at runtime in files this guard does not '
        'follow:\n  ' + '\n  '.join(undeclared)
    )
