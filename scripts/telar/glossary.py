"""
Glossary Loading and Linking

This module deals with Telar's glossary system, which lets authors link
terms in story panel text to glossary definitions. Glossary terms can be
defined in two ways:

1. **CSV file** (v0.8.0+): `telar-content/spreadsheets/glossary.csv` (or
   `glosario.csv` for Spanish-language spreadsheets) with columns `term_id`,
   `title`, `definition`, and `related_terms`. This is the preferred method
   for spreadsheet-first workflows.

2. **Markdown files** (legacy): Individual `.md` files in
   `telar-content/texts/glossary/`, each with YAML frontmatter containing
   `term_id` and `title`.

If both exist, CSV takes precedence and a warning is shown.

`load_glossary_terms()` checks for CSV first, then falls back to markdown.
It builds a dictionary mapping each `term_id` to its display title. This
dictionary is then passed to `process_glossary_links()`, which runs on
already-converted HTML text (after markdown processing) and replaces
`[[term_id]]` or `[[display text|term_id]]` syntax with clickable links.

If a term ID exists in the glossary, the link is rendered as an `<a>` tag
with `class="glossary-inline-link"`, a `data-term-id` attribute holding the
stored key, and a `data-term-url` attribute holding the path the term's page
is published at. `telar.js` fetches that path when the link is clicked.
Demo glossary terms (those prefixed with `demo-`) get an extra
`data-demo="true"` attribute.

The page path is not the stored key. Jekyll publishes each glossary page at
`/glossary/:name/`, where `:name` is its slugified filename, lowercased: the
page for `IIIF` is at `/glossary/iiif/`. `glossary_term_slug()` reproduces
that rule, and the path is joined to the site's configured baseurl here
because story text reaches the browser through `story.html`'s `jsonify`,
which does not resolve Liquid inside it.

If a term ID is not found in the glossary, the link is rendered as a
visible error indicator with a warning emoji, and a warning is appended
to the `warnings_list` so it appears in the build output and in the
story's intro panel. A site that sets `development-features.hide_warnings`
gets the text as written instead of the indicator.

A glossary callout (`:::glossary` in `telar/widgets.py`) reaches this pass
as a slot, and `process_glossary_links()` resolves its entry the way it
resolves `[[entry]]`: the same case-insensitive lookup, and for an entry the
glossary lacks the same warning and the same error marker. A resolved one is
drawn from `_includes/widgets/glossary.html` with the entry's kind, which the
loaders keep beside each title in `GlossaryTerms.kinds`. The callout carries
the inline link's class and data attributes, so the browser treats it as one.

Term matching is case-insensitive: an author's `[[Term]]` resolves against
the stored key regardless of casing, and the rendered `data-term-id` is the
stored key.

Version: v1.8.1
"""

import bisect
import datetime
import html
import itertools
import math
import re
from html.parser import HTMLParser
from typing import NamedTuple, Optional

import yaml

from telar.config import get_lang_string, warnings_hidden
from telar.widgets import render_widget_html, site_base_url
from telar.glossary_kinds import (default_kind, front_matter_kind, kind_icon,
                                  kind_text, resolve_kind)
from telar.story_pages import jekyll_slug
from telar.csv_utils import (GLOSSARY_COLUMN_ALIASES, ColumnCollisionError, ReservedColumnError,
                             is_header_row, normalize_column_names, read_sheet)


class GlossaryTerms(dict):
    """A glossary's term ids mapped to their titles, with each entry's kind
    id in `kinds`, which a glossary callout shows. An entry missing from
    `kinds` is of the default kind, so a plain dict works where no callout
    is drawn."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kinds = {}


def read_glossary_sheet(csv_path):
    """glossary.csv as the build reads it, for every reader of it: the link
    map, the pages, and the conversion that reads it as a story sheet.

    In order: a row whose first cell starts with `#` is a comment and goes;
    instruction columns (`#` in the header) go; the columns take their
    English names, the glossary's own aliases included, and are folded to
    lower case, so a sheet headed `Term_ID` is found; and a first row left
    that is a second, bilingual header row goes, judged with the glossary's
    aliases. A comment row is gone before that judgement, so it can never
    be taken for the header row, or kept as a term when it is not one.

    Every column is text the author typed. Left to infer, pandas reads a
    term titled `null` or `NA` as a missing value, and decides per column.
    A column collision is refused with the sheet's path, as the page
    generator and the link map both refuse it.
    """
    df = read_sheet(csv_path, dtype=str, keep_default_na=False)
    if len(df.columns):
        df = df[~df[df.columns[0]].astype(str).str.strip().str.startswith('#')]
    df = df[[col for col in df.columns if not col.startswith('#')]]
    try:
        df = normalize_column_names(df, sheet_aliases=GLOSSARY_COLUMN_ALIASES)
    except (ColumnCollisionError, ReservedColumnError) as e:
        e.source = str(csv_path)
        raise
    df.columns = df.columns.str.lower().str.strip()
    if len(df) > 0 and is_header_row(df.iloc[0].values, sheet_aliases=GLOSSARY_COLUMN_ALIASES):
        df = df.iloc[1:]
    return df.reset_index(drop=True)


def markdown_glossary_title(frontmatter_text):
    """The `title` of a legacy glossary file's front matter as the page
    generated from it reads it, or None when it has none or the front
    matter is not a YAML mapping. The page copies the front matter
    verbatim, so the title is what a YAML reader makes of it: quotes and a
    trailing comment are not part of it, and `subtitle:` is another key."""
    try:
        fields = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError:
        return None
    if not isinstance(fields, dict) or fields.get('title') is None:
        return None
    # A YAML reader gives `Z` and `+00:00` as the same zone; Ruby prints them
    # differently, so the written form decides.
    zulu = re.search(r'^title:[ \t]*[0-9][^\n#]*[Zz][ \t]*(?:#.*)?$',
                     frontmatter_text, re.MULTILINE) is not None
    return _as_liquid_text(fields['title'], zulu)


def _as_liquid_text(value, zulu=False):
    """A YAML value as the page prints it: Ruby's reading of it, rendered
    by Liquid. Not matched: a sexagesimal number (`12:34`), which the two
    YAML libraries read differently, a `Z` time inside a list, printed with
    its offset, and a mapping inside a list, printed in Python's form."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, float) and math.isinf(value):
        return 'Infinity' if value > 0 else '-Infinity'
    if isinstance(value, float) and math.isnan(value):
        return 'NaN'
    if isinstance(value, datetime.datetime):
        # Ruby prints a time written with `Z` in UTC, one written with an
        # offset at that offset, and one with no zone as UTC moved to the
        # build machine's local time.
        if value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc).astimezone()
        elif value.tzinfo is datetime.timezone.utc and zulu:
            return value.strftime('%Y-%m-%d %H:%M:%S') + ' UTC'
        return value.strftime('%Y-%m-%d %H:%M:%S %z')
    if isinstance(value, list):
        return ''.join(_as_liquid_text(item) for item in value)
    if value is None:
        return ''
    return str(value)


def load_glossary_terms():
    """
    The link map for the site's own glossary: the terms that have a page.

    The map is `site_glossary_pages()`, the decision the page generator
    writes its pages from (glossary.csv or glosario.csv when present, else
    the legacy markdown files), so a term is linkable exactly when a page
    exists for it. A term without a page resolves as missing.

    The generator reports why a sheet publishes no pages (a missing required
    column) when it runs. This reader runs once per story, so it leaves that
    one report to the generator; every other warning the read raises is shown.

    Returns:
        GlossaryTerms: term_id to term title, with each entry's kind; empty
        when the site has no glossary content
    """
    # Imported here: glossary_pages imports this module.
    from telar.glossary_pages import site_glossary_pages

    try:
        pages = site_glossary_pages(warn_missing=False)
    except (ColumnCollisionError, ReservedColumnError):
        raise
    except Exception as e:
        print(f"  ⚠️ Could not load glossary: {e}")
        return GlossaryTerms()
    return glossary_link_map(pages)


def glossary_link_map(pages):
    """The link map of `site_glossary_pages()`'s pages, as `load_glossary_terms`
    returns it."""
    glossary_terms = GlossaryTerms()
    for term_id, (title, kind) in pages.items():
        glossary_terms[term_id] = title
        glossary_terms.kinds[term_id] = kind
    return glossary_terms


def glossary_term_address(term_id):
    """The site-relative path (no baseurl) a glossary term's page is
    published at, `/glossary/<slug>/`."""
    return f'/glossary/{glossary_term_slug(term_id)}/'


def first_at_each_address(entries, warn=True):
    """The entries that are written, in order, as [(term_id, item)] of the
    `entries` given as (term_id, item).

    Ids that share a slug share an address, and Jekyll writes one page for
    each; the first is kept and the others are not published or linkable.
    `warn` says whether each dropped entry is reported.
    """
    kept, held = [], {}
    for term_id, item in entries:
        address = glossary_term_address(term_id)
        if address not in held:
            held[address] = term_id
            kept.append((term_id, item))
        elif warn:
            print(f"  ⚠️ Glossary entries '{held[address]}' and '{term_id}' would both "
                  f"be published at {address}. '{held[address]}' keeps that address; "
                  f"'{term_id}' is not published and cannot be linked.")
    return kept


class DemoTermPlacement(NamedTuple):
    """What becomes of one demo glossary term (`place_demo_terms`).

    `written` is True when the term's own page is written at
    `/glossary/<slug>/` in `_glossary/<term_id>.md`. Otherwise `owner` is
    the term whose page holds that address, `owner_is_site` says whose, and
    the demo id links to the owner's page.
    """
    term_id: str
    written: bool
    owner: Optional[str]
    owner_is_site: bool


def place_demo_terms(site_pages, demo_ids):
    """The one decision of which demo glossary terms are written and what
    each demo id links to, as a DemoTermPlacement per id, in order.

    `site_pages` is the site's glossary pages in the order they are written
    (a mapping of term ids), already placed by `first_at_each_address`.
    `demo_ids` is the bundle's glossary ids in order. Only a written page
    holds its address, so a term skipped earlier leaves it free for a later
    one. A skipped id is linked to the page that holds its address.
    """
    held = {}
    for term_id in site_pages:
        held.setdefault(glossary_term_address(term_id), (term_id, True))

    placements = []
    for term_id in demo_ids:
        owner = held.setdefault(glossary_term_address(term_id), (term_id, False))
        if owner == (term_id, False):
            placements.append(DemoTermPlacement(term_id, True, None, False))
        else:
            placements.append(DemoTermPlacement(term_id, False, *owner))
    return placements


def glossary_term_slug(term_id):
    """The path segment a glossary term's page is published at.

    Jekyll's `:name` for a collection document is `Jekyll::Utils.slugify` of
    the file's basename in its default mode, and the build writes each term
    to `<term_id>.md`. The rule is `jekyll_slug`'s, the one the story pages
    and the demo-term collision check use, so every published address is
    computed the same way.
    """
    return jekyll_slug(str(term_id))


def glossary_term_url(term_id, base_url=None):
    """The site-relative URL of a glossary term's page, baseurl included."""
    if base_url is None:
        base_url = site_base_url()
    return base_url + glossary_term_address(term_id)


# Matches the markup that process_glossary_links emits: a resolved inline link
# (<a class="glossary-inline-link">…</a>) or the unresolved-term error span
# (<span class="glossary-link-error">…</span>). The inner text is captured so it
# can be unwrapped. Non-greedy and DOTALL; the inner text is always HTML-escaped
# (so it can never itself contain a closing </a> / </span>), which keeps this safe.
_GLOSSARY_MARKUP_RE = re.compile(
    r'<a\b[^>]*\bclass="glossary-inline-link"[^>]*>(.*?)</a>'
    r'|<span\b[^>]*\bclass="glossary-link-error"[^>]*>(.*?)</span>'
    r'|<a\b[^>]*\bclass="glossary-inline-link glossary-callout[^"]*"[^>]*>.*?'
    r'<span class="glossary-callout-title">(.*?)</span>.*?</a>',
    re.DOTALL,
)


def strip_glossary_links(text):
    """Reduce glossary link markup back to its plain visible text.

    `process_glossary_links` injects HTML (`<a class="glossary-inline-link">` or a
    `glossary-link-error` span) into a string. Protected (encrypted) stories are
    rendered at runtime by a path that HTML-escapes the step answer and has no
    glossary panel, so that markup would surface as escaped tag-text instead of a
    link. For those stories we drop the wrapper and keep the visible text: a
    resolved link becomes its title, a glossary callout the entry's title, and an
    unresolved term its `⚠️ [[term]]` indicator text. The captured inner text is HTML-unescaped so that the runtime's
    own escaping pass produces correctly-escaped output (no double-escaping).

    Args:
        text: An already-glossary-processed string (HTML), or falsy.

    Returns:
        The string with glossary wrappers removed, or the input unchanged if falsy.
    """
    if not text:
        return text

    def unwrap(match):
        inner = next(group for group in match.groups() if group is not None)
        return html.unescape(inner)

    return _GLOSSARY_MARKUP_RE.sub(unwrap, text)


# The slot `parse_glossary_widget()` leaves for a glossary callout.
_CALLOUT_SLOT_RE = re.compile(
    r'<div class="glossary-callout-slot" data-entry="([^"]*)"'
    r' data-align="(right|left)"></div>')


def _missing_entry(raw_term_id, shown, warnings_list, step_num, layer_name):
    """The warning and the page marker for an entry the glossary lacks.

    A site that hides warnings gets the text as written in place of the
    marker; the warning is reported all the same.
    """
    if warnings_list is not None:
        warning_msg = get_lang_string('errors.object_warnings.glossary_term_not_found', term_id=raw_term_id)
        warnings_list.append({
            'step': step_num,
            'type': 'glossary',
            'term_id': raw_term_id,
            'layer': layer_name,
            'message': warning_msg
        })
    if warnings_hidden():
        return html.escape(html.unescape(shown))
    return f'<span class="glossary-link-error" data-term-id="{html.escape(raw_term_id, quote=True)}">\u26a0\ufe0f [[{html.escape(html.unescape(shown))}]]</span>'


def _glossary_callout(match, glossary_terms, lower_map, warnings_list,
                      step_num, layer_name, base_url):
    """The callout a slot stands for, or the missing-entry marker.

    A callout names its entry as [[entry]] does, and a missing or unknown
    one is reported and marked as [[entry]] is.
    """
    raw_term_id = html.unescape(match.group(1)).strip()
    term_id = lower_map.get(raw_term_id.lower())
    if term_id is None:
        return _missing_entry(raw_term_id, raw_term_id, warnings_list,
                              step_num, layer_name)
    kind = glossary_terms.kinds.get(term_id, default_kind())
    rendered = render_widget_html('glossary', {
        'term_id': term_id,
        'term_url': glossary_term_url(term_id, base_url),
        'demo': term_id.startswith('demo-'),
        'kind': kind,
        'icon': kind_icon(kind),
        'label': kind_text(kind, 'label'),
        # Decoded as a link's display text is; the template escapes it.
        'title': html.unescape(glossary_terms[term_id]),
        'align': match.group(2),
    }, 'glossary-callout')
    return ' '.join(line.strip() for line in rendered.splitlines() if line.strip())


class GlossaryLink(NamedTuple):
    """One `[[term]]` or `[[term|display]]` in a text: where it starts and
    ends, and its two parts as the syntax reads them, `display` being None
    for a link without a `|`."""
    start: int
    end: int
    term: str
    display: Optional[str]


_LINK_DELIMITER_RE = re.compile(r'[|\]]')


def _link_part(text, start, end):
    """A part of a link, stripped of whitespace; a part that is nothing but
    whitespace is its last character, which the syntax keeps as the part."""
    part = text[start:end]
    return part.strip() or part[-1]


def find_glossary_links(text):
    """The glossary links in *text*, in order and without overlap.

    The links are exactly the matches of
    `\\[\\[\\s*([^|\\]]+?)(?:\\s*\\|\\s*([^|\\]]+?))?\\s*\\]\\]` under
    `re.finditer`, which is how the Compositor reads the syntax, so the
    two agree on every text: `[[[term]]]` is the entry `[term`, and
    `[[term [note]]]` the entry `term [note`. Neither part can hold `|` or
    `]`, so a link opened at `[[` ends at the first `]]` or `|` after it,
    and a link with a `|` at the first `]]` after that. Each is found by
    one search, reused for every opening that shares it, so the text is
    read in linear time, where the expression's backtracking is quadratic
    on a run of `[` and worse on whitespace before a `|`.
    """
    length = len(text)

    def delimiter_from(index):
        match = _LINK_DELIMITER_RE.search(text, index)
        return match.start() if match else length

    # The first delimiter at or after `searched_from` is `bar`; every
    # opening whose term starts in that range shares it.
    searched_from = bar = -1
    # The delimiter after the `|` at `after_bar`, which ends the display.
    after_bar = close = -1

    start = text.find('[[')
    while start != -1:
        term_start = start + 2
        if not searched_from <= term_start <= bar:
            searched_from, bar = term_start, delimiter_from(term_start)
        link = None
        if term_start < bar < length:
            if text[bar] == ']':
                if text.startswith(']]', bar):
                    link = GlossaryLink(start, bar + 2, _link_part(text, term_start, bar), None)
            else:
                if after_bar != bar:
                    after_bar, close = bar, delimiter_from(bar + 1)
                if close > bar + 1 and text.startswith(']]', close):
                    link = GlossaryLink(start, close + 2, _link_part(text, term_start, bar),
                                        _link_part(text, bar + 1, close))
        if link is None:
            start = text.find('[[', start + 1)
        else:
            yield link
            start = text.find('[[', link.end)


class _PanelHTML(HTMLParser):
    """A panel's HTML read by Python's HTML tokenizer, for two kinds of
    stretch, as (start, end) offsets.

    `regions` holds the content of each `<a>` element: a tag inside a
    comment, another tag's attribute or text-only content is not a tag,
    and one whose offset *skip* (a test of an offset range) holds is not
    one either. As a browser keeps them, an element ends at its `</a>` or
    where the next `<a>` opens, `<a/>` opens one, and one never closed runs
    to the end of the text.

    `raw_texts` holds the content of each element whose content is text
    only (`script`, `style`, `textarea` and the others the tokenizer reads
    so), to its closing tag or the end of the text: markup written there is
    not markup."""

    def __init__(self, text, skip):
        super().__init__(convert_charrefs=False)
        self.skip = skip
        self.text_only = (self.CDATA_CONTENT_ELEMENTS
                          + getattr(self, 'RCDATA_CONTENT_ELEMENTS', ()))
        self.line_starts = [0] + [match.end() for match in re.finditer('\n', text)]
        self.regions, self.content = [], None
        self.raw_texts, self.raw_text = [], None
        # A character reference never starts or ends a tag, and how the
        # tokenizer reads a malformed one (`&#`, `&#5a`) differs between
        # Python versions and moves the positions it reports. Each `&` is
        # read as a space, which keeps every offset and the same tags in
        # every version the build may run.
        self.feed(text.replace('&', ' '))
        self.close()
        if self.content is not None:
            self.regions.append((self.content, len(text)))
        if self.raw_text is not None:
            self.raw_texts.append((self.raw_text[1], len(text)))

    def tag_offset(self):
        """The offset of the tag being read."""
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag in self.text_only:
            self.raw_text = (tag, self.tag_offset() + len(self.get_starttag_text()))
        elif tag == 'a':
            self.open_anchor()

    def handle_startendtag(self, tag, attrs):
        if tag == 'a':
            self.open_anchor()

    def open_anchor(self):
        start = self.tag_offset()
        end = start + len(self.get_starttag_text())
        if self.skip(start, end):
            return
        if self.content is not None:
            self.regions.append((self.content, start))
        self.content = end

    def handle_endtag(self, tag):
        if self.raw_text is not None and tag == self.raw_text[0]:
            self.raw_texts.append((self.raw_text[1], self.tag_offset()))
            self.raw_text = None
        elif tag == 'a' and self.content is not None:
            start = self.tag_offset()
            if not self.skip(start, start + 1):
                self.regions.append((self.content, start))
                self.content = None


# A start tag of an element whose content `_PanelHTML` reads as text, as
# the tokenizer finds one: no such tag, no such content.
_TEXT_ONLY_TAG_RE = re.compile(
    '<(?:' + '|'.join(HTMLParser.CDATA_CONTENT_ELEMENTS
                      + getattr(HTMLParser, 'RCDATA_CONTENT_ELEMENTS', ())) + r')(?![a-z0-9-])',
    re.IGNORECASE | re.ASCII)


def _text_only_regions(text):
    """The content of each element in *text* whose content a browser takes
    as text (`script`, `style`, `textarea` and the others `_PanelHTML`
    reads so), as (start, end) offsets."""
    if not _TEXT_ONLY_TAG_RE.search(text):
        return []
    return _PanelHTML(text, _no_range).raw_texts


def _no_range(start, end):
    """A test of an offset range that holds no range."""
    return False


def _merged(regions):
    """*regions* sorted, with those that overlap made one."""
    merged = []
    for start, end in sorted(regions):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


# A code element: its content stops at the next opening of the same
# element, so one that is never closed does not make the search rescan the
# rest of the text.
_CODE_ELEMENT = re.compile(r'<(code|pre|kbd|samp)\b[^>]*>(?:(?!<\1\b).)*?</\1\s*>',
                           re.DOTALL | re.IGNORECASE)


def code_elements(text):
    """Every code element in HTML *text*, as (start, end) offsets."""
    return [match.span() for match in _CODE_ELEMENT.finditer(text)]


def overlaps(regions):
    """A test of whether (start, end) overlaps any of *regions*, which may
    overlap each other: a search, not a pass over every region."""
    ordered = sorted(regions)
    starts = [start for start, _ in ordered]
    reach = list(itertools.accumulate((end for _, end in ordered), max))

    def test(start, end):
        count = bisect.bisect_left(starts, end)
        return count > 0 and reach[count - 1] > start
    return test


def _link_text_regions(text):
    """Where the text of a link is in HTML *text*, as sorted,
    non-overlapping (start, end) offsets: the content of each `<a>`
    element as an HTML tokenizer reads it, outside code elements."""
    return _merged(_PanelHTML(text, overlaps(code_elements(text))).regions)


def _region_around(regions, starts, start):
    """The (start, end) region of *regions*, whose starts are *starts*,
    holding offset *start*, or the one whose text begins just after it: a
    `[` that opens a link's text counts as inside it. None when there is
    none."""
    after = bisect.bisect_right(starts, start + 1)
    for number in (after - 2, after - 1):
        if number >= 0 and regions[number][0] - 1 <= start < regions[number][1]:
            return regions[number]
    return None


def _term_in_link_text(link, text, regions, starts):
    """The glossary link to replace when *link* lies in a link's text, as
    (link, True); (link, False) when it does not lie in one; or
    (None, True) when there is nothing to replace.

    Where a link's text is `[[term]]` with a bracket before it, the
    syntax reads `[term` as the term; the term is the inner link there.
    """
    region = _region_around(regions, starts, link.start)
    if region is None:
        return link, False
    if not link.term.startswith('['):
        return link, link.start >= region[0]
    inner = next(find_glossary_links(text[link.start + 1:link.end]), None)
    if inner is None or inner.start != 0:
        return None, True
    return GlossaryLink(link.start + 1, link.start + 1 + inner.end, inner.term,
                        inner.display), True


def _plain_term(raw_term_id, display_text, canonical_id, glossary_terms,
                warnings_list, step_num, layer_name):
    """A term inside the text of a link, as the plain text it shows.

    A link cannot hold a link, so the term is not linked: it shows its
    display text, or its title, or, when the glossary has no such entry,
    the text as written. The build says so either way.
    """
    if canonical_id is None:
        message = get_lang_string('errors.object_warnings.glossary_term_not_found',
                                  term_id=raw_term_id)
        shown = display_text or raw_term_id
    else:
        message = get_lang_string('errors.object_warnings.glossary_term_in_link_text',
                                  term_id=raw_term_id)
        shown = display_text or glossary_terms[canonical_id]
    if warnings_list is not None:
        warnings_list.append({
            'step': step_num,
            'type': 'glossary',
            'term_id': raw_term_id,
            'layer': layer_name,
            'message': message,
        })
    return html.escape(html.unescape(shown))


def process_glossary_links(text, glossary_terms, warnings_list=None, step_num=None, layer_name=None,
                           base_url=None):
    """
    Transform [[term]] or [[display|term]] syntax into glossary link HTML.

    Args:
        text: HTML text to process (already converted from markdown, with
            its maths still held out as placeholders)
        glossary_terms: Dictionary mapping term_id to term title
        warnings_list: Optional list to append warning messages
        step_num: Optional step number for warning messages
        layer_name: Optional layer name (e.g., 'layer1', 'layer2') for warning context
        base_url: The site's baseurl for the term page URL; read from
            _config.yml when omitted

    Returns:
        str: Text with glossary links transformed to HTML
    """
    if not text or not (glossary_terms or _CALLOUT_SLOT_RE.search(text)):
        return text

    # Build a case-insensitive lookup that resolves an author's [[term]] (any
    # casing) to the stored key. The glossary sources store term_id verbatim
    # (the demo glossary stores 'IIIF'), and resolving to the stored key
    # rather than a lowercased copy keeps the rendered data-term-id and title
    # lookup on the key the glossary holds.
    # If two keys differ only by case, the last one wins — acceptable because the
    # glossary page system would already collide on such keys.
    glossary_lower_map = {key.lower(): key for key in (glossary_terms or {})}

    def replace_glossary_link(link, in_link_text=False):
        # If pipe is present: [[term|display]], else [[term]]
        if link.display:  # Has pipe
            raw_term_id = link.term.strip()
            display_text = link.display.strip()
            has_custom_display = True
        else:  # No pipe
            raw_term_id = link.term.strip()
            display_text = None
            has_custom_display = False

        # Authors type whatever casing reads naturally, e.g. [[KCSB]] or
        # [[Colonial-Period]], while the stored key may be lowercase (the common
        # compositor case) or not (hand-authored CSV / demo bundle, e.g. 'IIIF').
        # Match case-insensitively and resolve to the actual stored key so the
        # title lookup succeeds; the page URL is derived from that key.
        canonical_id = glossary_lower_map.get(raw_term_id.lower())

        if in_link_text:
            return _plain_term(raw_term_id, display_text, canonical_id, glossary_terms,
                               warnings_list, step_num, layer_name)

        # Check if term exists in glossary (case-insensitive)
        if canonical_id is not None:
            term_id = canonical_id
            if not has_custom_display:
                # Use the glossary title as display text
                display_text = glossary_terms[term_id]
            demo_attr = ' data-demo="true"' if term_id.startswith('demo-') else ''
            term_url = glossary_term_url(term_id, base_url)
            # Escape the canonical term id, the URL and the display text so a
            # quote or angle bracket in any of them cannot break out of the
            # link markup. The display text is decoded first: an entity the
            # author wrote (&#93; for a bracket) is the character it names,
            # and in a panel markdown has already turned & into &amp;.
            return (f'<a href="#" class="glossary-inline-link"'
                    f' data-term-id="{html.escape(term_id, quote=True)}"'
                    f' data-term-url="{html.escape(term_url, quote=True)}"{demo_attr}>'
                    f'{html.escape(html.unescape(display_text))}</a>')
        else:
            # Invalid term - create error indicator (author's original casing preserved)
            return _missing_entry(raw_term_id, link.term, warnings_list,
                                  step_num, layer_name)

    # Text is linked, a tag never: [[term]] inside an attribute (an image's
    # alt text) stays literal, or the link it made would end the attribute.
    # A quoted attribute value may hold '>', so it does not end the tag.
    # Code is shown as written, so [[term]] in a code element is the syntax,
    # not a link. So is the content of a `script`, `style` or other element
    # whose content is text only.
    tags = [m.span() for m in re.finditer(
        r'<[A-Za-z/!](?:[^<>"\']|"[^"]*"|\'[^\']*\')*>', text)]
    literal = overlaps(tags + code_elements(text) + _text_only_regions(text))

    # A link cannot hold a link: a term in a link's text is shown, not linked.
    link_regions = _link_text_regions(text)
    link_starts = [start for start, _ in link_regions]

    if glossary_terms:
        pieces, written = [], 0
        for found in find_glossary_links(text):
            if literal(found.start, found.start + 1):
                continue
            link, in_link_text = _term_in_link_text(found, text, link_regions, link_starts)
            if link is None:
                continue
            pieces += [text[written:link.start], replace_glossary_link(link, in_link_text)]
            written = link.end
        text = ''.join(pieces) + text[written:]
    # After the links: the marker an unknown callout leaves reads as
    # [[entry]], which the link pass would report a second time.
    return _CALLOUT_SLOT_RE.sub(
        lambda match: _glossary_callout(match, glossary_terms, glossary_lower_map,
                                        warnings_list, step_num, layer_name, base_url),
        text)
