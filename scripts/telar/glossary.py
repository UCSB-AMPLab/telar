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
story's intro panel.

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

Version: v1.8.0
"""

import html
import re
from pathlib import Path
import pandas as pd
from telar.config import get_lang_string
from telar.widgets import render_widget_html, site_base_url
from telar.glossary_kinds import (default_kind, front_matter_kind, kind_icon,
                                  kind_text, resolve_kind)
from telar.story_pages import jekyll_slug
from telar.csv_utils import ColumnCollisionError, ReservedColumnError


class GlossaryTerms(dict):
    """A glossary's term ids mapped to their titles, with each entry's kind
    id in `kinds`, which a glossary callout shows. An entry missing from
    `kinds` is of the default kind, so a plain dict works where no callout
    is drawn."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kinds = {}


def load_glossary_from_csv(csv_path):
    """
    Load glossary terms from a CSV file.

    Args:
        csv_path: Path to glossary.csv

    Returns:
        GlossaryTerms: term_id to term title, with each entry's kind
    """
    glossary_terms = GlossaryTerms()

    try:
        # Every column here is text the author typed. Left to infer, pandas
        # reads a term titled `null` or `NA` as a missing value and the page
        # is written `nan`, and it decides per column, so the same title
        # survives or does not depending on what its neighbours look like.
        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

        # Normalize column names (bilingual mapping). normalize_column_names
        # already lowercases internally for lookup, so pre-lowercasing here was
        # redundant and needlessly mutated the actual header labels, diverging
        # from every other CSV's column-casing behaviour.
        from telar.csv_utils import normalize_column_names, GLOSSARY_COLUMN_ALIASES
        df = normalize_column_names(df, sheet_aliases=GLOSSARY_COLUMN_ALIASES)

        if 'term_id' not in df.columns or 'title' not in df.columns:
            print(f"  ⚠️ glossary.csv missing required columns (term_id, title)")
            return glossary_terms

        for _, row in df.iterrows():
            term_id = str(row.get('term_id', '')).strip()
            title = str(row.get('title', '')).strip()

            # A row whose id begins `#` is a comment the author left for
            # themselves, and the page generator gives it no page. The link
            # map has to exclude it on the same stripped value, or a term
            # resolves to a link with nothing behind it. `strip()` settles
            # every way such a row can arrive -- leading spaces, and the
            # U+0085 a paste into a spreadsheet cell can carry.
            if term_id.startswith('#'):
                continue

            if term_id and title:
                glossary_terms[term_id] = title
                # The page generator reads the same cell and warns about it.
                glossary_terms.kinds[term_id] = resolve_kind(
                    row.get('kind', ''), warn=False)

    except (ColumnCollisionError, ReservedColumnError) as e:
        # The page generator reads this same file and fails the build on
        # these two. A loader that swallowed them handed back an empty link
        # map, so whether the author heard about the sheet at all depended
        # on which path ran first. Both refuse alike. The path goes with the
        # error because it surfaces inside each story's conversion, where
        # the file being converted is the story, not the one to change.
        e.source = str(csv_path)
        raise
    except Exception as e:
        print(f"  ⚠️ Could not load glossary.csv: {e}")

    return glossary_terms


def load_glossary_from_markdown(glossary_dir):
    """
    Load glossary terms from markdown files (legacy method).

    Args:
        glossary_dir: Path to telar-content/texts/glossary/

    Returns:
        GlossaryTerms: term_id to term title, with each entry's kind
    """
    glossary_terms = GlossaryTerms()

    try:
        for glossary_file in glossary_dir.glob('*.md'):
            with open(glossary_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse frontmatter
            frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n'
            match = re.match(frontmatter_pattern, content, re.DOTALL)

            if match:
                frontmatter_text = match.group(1)

                # Extract term_id and title
                term_id_match = re.search(r'term_id:\s*(\S+)', frontmatter_text)
                title_match = re.search(r'title:\s*["\']?(.*?)["\']?\s*$', frontmatter_text, re.MULTILINE)

                if term_id_match and title_match:
                    term_id = term_id_match.group(1)
                    title = title_match.group(1)
                    glossary_terms[term_id] = title
                    glossary_terms.kinds[term_id] = resolve_kind(
                        front_matter_kind(frontmatter_text), warn=False)

    except Exception as e:
        print(f"  ⚠️ Could not load glossary markdown files: {e}")

    return glossary_terms


def load_glossary_terms():
    """
    Load glossary terms from CSV or markdown files.

    Checks for glossary.csv first, then glosario.csv (Spanish-language
    spreadsheet support), then falls back to markdown files.
    If both CSV and markdown exist, CSV takes precedence and a warning is shown.

    Returns:
        dict: Dictionary mapping term_id to term title, or empty dict if no glossary found
    """
    csv_path = Path('telar-content/spreadsheets/glossary.csv')
    if not csv_path.exists():
        fallback = Path('telar-content/spreadsheets/glosario.csv')
        if fallback.exists():
            csv_path = fallback
    md_path = Path('telar-content/texts/glossary')

    # Check if CSV exists (preferred source)
    if csv_path.exists():
        return load_glossary_from_csv(csv_path)

    # Fall back to markdown files
    elif md_path.exists() and any(md_path.glob('*.md')):
        return load_glossary_from_markdown(md_path)

    # No glossary content
    return {}


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
    return f'{base_url}/glossary/{glossary_term_slug(term_id)}/'


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
    """The warning and the page marker for an entry the glossary lacks."""
    if warnings_list is not None:
        warning_msg = get_lang_string('errors.object_warnings.glossary_term_not_found', term_id=raw_term_id)
        warnings_list.append({
            'step': step_num,
            'type': 'glossary',
            'term_id': raw_term_id,
            'layer': layer_name,
            'message': warning_msg
        })
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
    kind = getattr(glossary_terms, 'kinds', {}).get(term_id, default_kind())
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


def process_glossary_links(text, glossary_terms, warnings_list=None, step_num=None, layer_name=None,
                           base_url=None):
    """
    Transform [[term]] or [[display|term]] syntax into glossary link HTML.

    Args:
        text: HTML text to process (already converted from markdown)
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
    # casing) to the ACTUAL stored key. Glossary loaders store term_id verbatim
    # — load_glossary_from_csv, load_glossary_from_markdown, and the demo bundle
    # do not lowercase keys (e.g. the demo glossary stores 'IIIF'). Resolving to
    # the stored key (rather than a lowercased copy) keeps the rendered
    # data-term-id and title lookup on the key the glossary holds. Mirrors the
    # objects_lower_map pattern in stories.py.
    # If two keys differ only by case, the last one wins — acceptable because the
    # glossary page system would already collide on such keys.
    glossary_lower_map = {key.lower(): key for key in (glossary_terms or {})}

    # Pattern: [[display|term]] or [[term]] with flexible spacing
    # Captures: (optional_display) | (term_id)
    pattern = r'\[\[\s*([^|\]]+?)(?:\s*\|\s*([^|\]]+?))?\s*\]\]'

    def replace_glossary_link(match):
        # If pipe is present: [[term|display]], else [[term]]
        if match.group(2):  # Has pipe
            raw_term_id = match.group(1).strip()
            display_text = match.group(2).strip()
            has_custom_display = True
        else:  # No pipe
            raw_term_id = match.group(1).strip()
            display_text = None
            has_custom_display = False

        # Authors type whatever casing reads naturally, e.g. [[KCSB]] or
        # [[Colonial-Period]], while the stored key may be lowercase (the common
        # compositor case) or not (hand-authored CSV / demo bundle, e.g. 'IIIF').
        # Match case-insensitively and resolve to the actual stored key so the
        # title lookup succeeds; the page URL is derived from that key.
        canonical_id = glossary_lower_map.get(raw_term_id.lower())

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
            return _missing_entry(raw_term_id, match.group(1), warnings_list,
                                  step_num, layer_name)

    # Text is linked, a tag never: [[term]] inside an attribute (an image's
    # alt text) stays literal, or the link it made would end the attribute.
    # A quoted attribute value may hold '>', so it does not end the tag.
    tags = [m.span() for m in re.finditer(
        r'<[A-Za-z/!](?:[^<>"\']|"[^"]*"|\'[^\']*\')*>', text)]

    def link_outside_tags(match):
        start = match.start()
        if any(a < start < b for a, b in tags):
            return match.group(0)
        return replace_glossary_link(match)

    if glossary_terms:
        text = re.sub(pattern, link_outside_tags, text)
    # After the links: the marker an unknown callout leaves reads as
    # [[entry]], which the link pass would report a second time.
    return _CALLOUT_SLOT_RE.sub(
        lambda match: _glossary_callout(match, glossary_terms, glossary_lower_map,
                                        warnings_list, step_num, layer_name, base_url),
        text)
