"""
How Jekyll Names a Page's Address and the File It Writes

The build decides which glossary pages it writes and where links to them
go, and Jekyll decides where each page is published. The two agree only if
the build reads a page's address the way Jekyll does, so this module
reproduces Jekyll 4.4's rules, checked against its source: how a
collection document's `permalink` placeholders are replaced and escaped
(`Jekyll::URL`, `Jekyll::Drops::UrlDrop`, `Document#populate_title` and its
categories), how a URL is sanitized, which file in the output folder a URL
is written to (`Document#destination`), and the address of the site's
glossary page (`Jekyll::Page#template`).

Two pages whose output files differ only in case or in Unicode
normalization are one file on a case- and normalization-insensitive disk
(APFS, the macOS default), so output files are compared by `disk_name`.

What is not reproduced is reported rather than guessed: the date
placeholders, and a value whose printed or escaped form here may not be
Ruby's (`resolve_permalink`'s `unresolved`).

A glossary page is looked for where a Telar site keeps its pages: the
`.md`, `.markdown` and `.html` files directly in the site's root and
anywhere in `pages/`, read as Jekyll's `exclude:`, `include:` and its
underscore and dot rules read them, of the `glossary-index` layout in the
page's own front matter and not `published: false`. Not modelled, none of
them part of a Telar site: a glossary page in a collection or in `_posts`,
a layout or permalink given by `defaults:`, and the `safe:` and
`unpublished:` settings.

Version: v1.8.0
"""

import datetime
import fnmatch
import math
import os
import posixpath
import re
import unicodedata
import urllib.parse
from pathlib import Path

import yaml

from telar.frontmatter import FRONTMATTER_PATTERN
from telar.story_pages import jekyll_slug


# A permalink placeholder as `Jekyll::URL` reads one.
URL_PLACEHOLDER = re.compile(r':([a-z_]+)')


def front_matter_mapping(frontmatter_text):
    """A page's front matter as a YAML reader reads it, or None when it is
    not a mapping."""
    try:
        fields = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError:
        return None
    return fields if isinstance(fields, dict) else None


def sanitize_url(url):
    """`Jekyll::URL#sanitize_url`: a leading slash is supplied, `..` reads
    as `/`, `./` goes, and a run of slashes is one."""
    url = ('/' + url).replace('..', '/').replace('./', '')
    return re.sub(r'/{2,}', '/', url)


def _ruby_downcase(value):
    """Ruby's `downcase`, which lowercases each character on its own."""
    return ''.join(char.lower() for char in value)


def _pretty_slug(value):
    """`Jekyll::Utils.slugify` in pretty mode with case kept: marks,
    letters, decimal digits and `._~!$&'()+,;=@` pass through, every other
    run is one hyphen, and one leading and one trailing hyphen go."""
    out, prev_hyphen = [], False
    for char in value:
        category = unicodedata.category(char)
        if category[0] in ('M', 'L') or category == 'Nd' or char in "._~!$&'()+,;=@":
            out.append(char)
            prev_hyphen = False
        elif not prev_hyphen:
            out.append('-')
            prev_hyphen = True
    slug = ''.join(out)
    slug = slug[1:] if slug.startswith('-') else slug
    return slug[:-1] if slug.endswith('-') else slug


def _unique(values):
    """`values` in order with repeats dropped, as Ruby's `uniq` and Set keep
    them."""
    return list(dict.fromkeys(values))


class _Unreadable(Exception):
    """A front-matter value whose printed form here may not be Ruby's."""


def _ruby_to_s(value):
    """Ruby's `to_s` of a YAML scalar. Raises `_Unreadable` for a list, a
    mapping, a time, or a float Ruby prints in another form."""
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (str, int)):
        return str(value)
    if isinstance(value, float) and math.isfinite(value) and 'e' not in repr(value):
        return repr(value)
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return value.isoformat()
    raise _Unreadable


def _ruby_split(text):
    """Ruby's `String#split` with no pattern: ASCII whitespace and NUL
    separate, and empty fields go."""
    return [part for part in re.split(r'[ \t\n\v\f\r\x00]+', text) if part]


def _singular_category(fields):
    """The `category` key's items as `Utils.pluralized_array_from_hash`
    reads them, or None when it is absent, null or false and `categories`
    is read again in its place."""
    value = fields.get('category')
    if value is None or value is False:
        return None
    items = value if isinstance(value, list) else [value]
    if any(isinstance(item, (list, dict)) for item in items):
        raise _Unreadable
    return [item for item in items if item is not None]


def _document_categories(fields):
    """A collection document's categories as Jekyll reads them: `categories`
    (a string split on whitespace), then the singular `category` when it is
    set, each printed by Ruby's `to_s` and repeats dropped. Raises
    `_Unreadable` when an item cannot be printed as Ruby prints it."""
    raw = fields.get('categories')
    if raw is None:
        items = []
    elif isinstance(raw, str):
        items = _ruby_split(raw)
    elif isinstance(raw, list):
        items = raw
    else:
        raise _Unreadable
    items = list(items) + (_singular_category(fields) or [])
    return _unique(_ruby_to_s(item) for item in items)


_DATE_FILENAME = re.compile(r'^(\d{2,4}-\d{1,2}-\d{1,2})-([^/]*)(\.[^.]+)$')
_DATELESS_FILENAME = re.compile(r'^(.*)(\.[^.]+)$')


def _document_slug(basename, fields):
    """The `slug` Jekyll's `populate_title` leaves a document written to
    `<basename>.md`: the front matter's when it is set, else the
    file name less its extension and any leading `YYYY-MM-DD-` date, with
    trailing periods dropped. Raises `_Unreadable` for a slug that is not
    a string."""
    slug = fields.get('slug')
    if slug is not None and slug is not False:
        if not isinstance(slug, str):
            raise _Unreadable
        return slug
    filename = f'{basename}.md'
    match = _DATE_FILENAME.match(filename)
    slug = match.group(2) if match else _DATELESS_FILENAME.match(filename).group(1)
    return re.sub(r'\.*\Z', '', slug)


def _url_placeholder_values(basename, fields, collection):
    """The placeholders `Jekyll::Drops::UrlDrop` gives a document written
    to `_<collection>/<basename>.md`, each with its unescaped value. A
    placeholder whose value cannot be read here is absent, as are the date
    placeholders: their value is the front matter's `date`, the file
    name's, or the time of the build."""
    values = {'collection': collection,
              'name': jekyll_slug(str(basename)),
              'path': re.sub(r'\.*\Z', '', '/' + str(basename)),
              'output_ext': '.html'}
    try:
        slug = _document_slug(basename, fields)
        values['slug'], values['title'] = jekyll_slug(slug), _pretty_slug(slug)
    except _Unreadable:
        pass
    try:
        categories = _document_categories(fields)
        values['categories'] = '/'.join(
            _unique(_ruby_downcase(category) for category in categories))
        values['slugified_categories'] = '/'.join(
            _unique(jekyll_slug(category) for category in categories))
    except _Unreadable:
        pass
    return values


# RFC 3986's split of a URI, as Addressable parses one.
_URI_PARTS = re.compile(r'^(([^:/?#]+):)?(//([^/?#]*))?([^?#]*)(\?([^#]*))?(#(.*))?$')
_PCHAR = "-._~!$&'()*+,;=:@"


# Schemes Addressable treats as IP-based (`URI.port_mapping`): one of
# them with no host and no path is refused.
_IP_SCHEMES = frozenset({'http', 'https', 'ftp', 'tftp', 'sftp', 'ssh', 'svn+ssh',
                         'telnet', 'nntp', 'gopher', 'wais', 'ldap', 'prospero'})


def _uri_builds(scheme, path):
    """Whether Addressable builds a URI with no authority from `scheme`
    (None without one) and `path`: a scheme is a letter followed by
    letters, digits, `+`, `-` or `.`, an IP-based scheme needs a path, and
    without a scheme a colon before the first `/` makes the path
    ambiguous."""
    if scheme is None:
        return re.match(r'^(?!/)[^/:]*:', path) is None
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9.+\-]*', scheme):
        return False
    return not (scheme.lower() in _IP_SCHEMES and path == '')


def _escape_path(value):
    """`Jekyll::URL.escape_path`: a value of ASCII letters, digits, `.`, `/`
    and `-` is kept; any other is encoded by `Addressable::URI.encode`, part
    by part (its scheme kept as written), and its first `#` is then
    encoded. None when Addressable refuses the value (`_uri_builds`), which
    stops Jekyll's build, or when it parses with an authority, whose
    encoding is not reproduced here."""
    if value == '' or re.fullmatch(r'[a-zA-Z0-9./-]+', value):
        return value
    parts = _URI_PARTS.match(value)
    if parts is None or parts.group(3) is not None:
        return None
    if not _uri_builds(parts.group(2), parts.group(5)):
        return None
    out = '' if parts.group(2) is None else parts.group(2) + ':'
    out += urllib.parse.quote(parts.group(5), safe=_PCHAR + '/')
    if parts.group(6) is not None:
        out += '?' + urllib.parse.quote(parts.group(7), safe=_PCHAR + '/?')
    if parts.group(8) is not None:
        out += '#' + urllib.parse.quote(parts.group(9), safe=_PCHAR + '/?')
    return out.replace('#', '%23', 1)


def resolve_permalink(permalink, basename, fields, collection):
    """(url, unresolved) of a collection document's `permalink`: the URL
    Jekyll gives the document `_<collection>/<basename>.md` whose front
    matter is `fields`, placeholders replaced and escaped as `Jekyll::URL`
    does.

    Jekyll reads `:` and the lowercase letters and underscores after it as
    a placeholder; a trailing underscore is looked up without it and kept.
    When a placeholder cannot be resolved here, `unresolved` names each
    such one and the address is the permalink as written.
    """
    values = _url_placeholder_values(basename, fields, collection)
    unresolved = []

    def replace_placeholder(match):
        name = match.group(1)
        key = name[:-1] if name.endswith('_') else name
        escaped = _escape_path(values[key]) if key in values else None
        if escaped is None:
            unresolved.append(match.group(0))
            return match.group(0)
        return escaped + name[len(key):]

    resolved = URL_PLACEHOLDER.sub(replace_placeholder, permalink)
    if unresolved:
        return sanitize_url(permalink), _unique(unresolved)
    return sanitize_url(resolved), []


def _site_config():
    """`_config.yml` as a mapping; empty when it is missing or unreadable."""
    config = Path('_config.yml')
    try:
        fields = yaml.safe_load(config.read_text(encoding='utf-8')) if config.exists() else None
    except yaml.YAMLError:
        fields = None
    return fields if isinstance(fields, dict) else {}


def _permalink_style(config):
    """The site's `permalink` setting as `Jekyll::Site#permalink_style`
    reads it; Jekyll's default, `date`, without one."""
    style = config.get('permalink')
    return str(style) if style else 'date'


def _config_list(config, key, default):
    value = config.get(key, default)
    if value is None:
        return []
    return [str(item) for item in (value if isinstance(value, list) else [value])]


class _EntryFilter:
    """Which files and folders Jekyll reads (`Jekyll::EntryFilter`): an
    entry ending in `.`, one matching `exclude:` (Jekyll's own defaults
    added) and not `include:`, and one starting with `.`, `_`, `#` or `~` or
    ending in `~` that `include:` does not name, are not read."""

    _DEFAULT_EXCLUDES = ['.sass-cache', '.jekyll-cache', 'gemfiles', 'Gemfile',
                         'Gemfile.lock', 'node_modules', 'vendor/bundle/',
                         'vendor/cache/', 'vendor/gems/', 'vendor/ruby/']

    def __init__(self, config):
        self.include = _config_list(config, 'include', ['.htaccess'])
        excludes = _config_list(config, 'exclude', []) + self._DEFAULT_EXCLUDES
        self.exclude = [item for item in _unique(excludes) if item not in self.include]

    @staticmethod
    def _matches(patterns, entry):
        """`EntryFilter#glob_include?`: `entry` is a path from the site's
        root; a pattern matches it as `File.fnmatch?` does (a `*` crosses
        `/`), as a prefix of it, or as the folder it names."""
        is_dir = os.path.isdir(entry)
        entry = '/' + entry.lstrip('/')
        return any(fnmatch.fnmatchcase(entry, '/' + pattern.lstrip('/'))
                   or entry.startswith('/' + pattern.lstrip('/'))
                   or (is_dir and '/' + pattern.lstrip('/') == entry + '/')
                   for pattern in patterns)

    def reads(self, folder, name):
        if name.endswith('.'):
            return False
        included = (self._matches(self.include, name)
                    or self._matches(self.include, os.path.basename(name)))
        if not included and self._matches(self.exclude, posixpath.join(folder, name)):
            return False
        return included or not (name[0] in '._#~' or name.endswith('~'))


def _has_front_matter(path):
    """`Utils.has_yaml_header?`: the file's first line is `---`."""
    try:
        with open(path, 'rb') as f:
            return re.match(rb'---\s*\r?\n', f.readline(4096)) is not None
    except OSError:
        return False


_PAGE_EXTENSIONS = ('.md', '.markdown', '.html')


def _glossary_page_files(config):
    """The files that can be a Telar site's glossary page, as paths from the
    site's root: the `.md`, `.markdown` and `.html` files with front matter
    directly in the root and anywhere in `pages/`, each in a folder
    `_EntryFilter` lets Jekyll read."""
    entries = _EntryFilter(config)
    files, pending = [], [('', False)]
    while pending:
        folder, recurse = pending.pop()
        for name in sorted(os.listdir(folder or '.')):
            path = posixpath.join(folder, name)
            if not entries.reads(folder, name):
                continue
            if os.path.isdir(path):
                if recurse or path == 'pages':
                    pending.append((path, True))
            elif (posixpath.splitext(name)[1] in _PAGE_EXTENSIONS
                  and _has_front_matter(path)):
                files.append(path)
    return files


_HTML_EXTENSIONS = ('.html', '.xhtml', '.htm')


def _page_url(path, fields, config):
    """The URL Jekyll gives the page at `path` (`Jekyll::Page#url`): its
    front matter's `permalink` with `:path`, `:basename` and `:output_ext`
    replaced in that order, else the template `Page#template` picks for the
    site's permalink style."""
    folder, name = posixpath.split(path)
    ext = posixpath.splitext(name)[1]
    basename = re.sub(r'\.*\Z', '', name[:len(name) - len(ext)])
    markdown = ['.' + item.strip().lower() for item in
                str(config.get('markdown_ext') or 'markdown,mkdown,mkdn,mkd,md').split(',')]
    output_ext = '.html' if ext.lower() in markdown else ext
    permalink = fields.get('permalink')
    if permalink is not None and str(permalink).strip():
        template = str(permalink).strip()
    elif output_ext not in _HTML_EXTENSIONS:
        template = '/:path/:basename:output_ext'
    elif basename == 'index':
        template = '/:path/'
    else:
        template = '/:path/:basename' + _permalink_suffix(_permalink_style(config))
    for key, value in (('path', '/' + folder if folder else ''), ('basename', basename),
                       ('output_ext', output_ext)):
        if ':' not in template:
            break
        template = template.replace(':' + key, _escape_path(value) or value)
    return sanitize_url(template)


def _permalink_suffix(style):
    """`Utils.add_permalink_suffix`'s ending for a permalink style."""
    if style == 'pretty':
        return '/'
    if style in ('date', 'ordinal', 'none'):
        return ':output_ext'
    return (('/' if style.endswith('/') else '')
            + (':output_ext' if style.endswith(':output_ext') else ''))


def glossary_index_addresses():
    """The addresses the site's glossary pages are published at, which no
    entry's page can take: each file of `_glossary_page_files` whose own
    front matter gives the `glossary-index` layout and does not set
    `published: false`, at the URL Jekyll gives it (`_page_url`). Empty
    when the site has none."""
    config = _site_config()
    addresses = []
    for path in _glossary_page_files(config):
        with open(path, encoding='utf-8', errors='replace') as f:
            match = FRONTMATTER_PATTERN.match(f.read())
        fields = front_matter_mapping(match.group(1)) if match else None
        if (fields and fields.get('layout') == 'glossary-index'
                and fields.get('published') is not False):
            addresses.append(_page_url(path, fields, config))
    return addresses


def disk_name(path):
    """`path` as a case- and normalization-insensitive disk (APFS) names
    it: names equal under canonical caseless matching are one file."""
    return unicodedata.normalize(
        'NFC', unicodedata.normalize('NFD', path).casefold())


def glossary_output_file(address):
    """The file Jekyll writes the page published at `address` to, relative
    to the site's output folder, as a case- and normalization-insensitive
    disk names it (`disk_name`).

    As `Document#destination`: the URL is unescaped, then read as a path
    from the root, so `..` and `.` resolve; an address ending in `/` is
    written to `index.html` inside it, and any other gets `.html` unless
    it ends so."""
    path = urllib.parse.unquote(address) if '%' in address else address
    if path.startswith('~'):
        path = '/' + path
    path = re.sub(r'/{2,}', '/', posixpath.normpath('/' + path))
    if address.endswith('/'):
        path = posixpath.join(path, 'index.html')
    elif not path.endswith('.html'):
        path += '.html'
    return disk_name(path.lstrip('/'))
