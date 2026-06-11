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
with `class="glossary-inline-link"` and a `data-term-id` attribute.
JavaScript in `telar.js` handles the click event and constructs the URL
dynamically (to correctly handle baseurl across deployment scenarios).
Demo glossary terms (those prefixed with `demo-`) get an extra
`data-demo="true"` attribute.

If a term ID is not found in the glossary, the link is rendered as a
visible error indicator with a warning emoji, and a warning is appended
to the `warnings_list` so it appears in the build output and in the
story's intro panel.

Term matching is case-insensitive (v1.5.1): an author's `[[Term]]` resolves
against the stored key regardless of casing, and the rendered `data-term-id`
uses the stored key so it matches the published glossary page slug.

Version: v1.5.2
"""

import html
import re
from pathlib import Path
import pandas as pd
from telar.config import get_lang_string


def load_glossary_from_csv(csv_path):
    """
    Load glossary terms from a CSV file.

    Args:
        csv_path: Path to glossary.csv

    Returns:
        dict: Dictionary mapping term_id to term title
    """
    glossary_terms = {}

    try:
        df = pd.read_csv(csv_path)

        # Normalize column names (bilingual mapping). normalize_column_names
        # already lowercases internally for lookup, so pre-lowercasing here was
        # redundant and needlessly mutated the actual header labels, diverging
        # from every other CSV's column-casing behaviour.
        from telar.csv_utils import normalize_column_names
        df = normalize_column_names(df)

        if 'term_id' not in df.columns or 'title' not in df.columns:
            print(f"  ⚠️ glossary.csv missing required columns (term_id, title)")
            return glossary_terms

        for _, row in df.iterrows():
            term_id = str(row.get('term_id', '')).strip()
            title = str(row.get('title', '')).strip()

            if term_id and title:
                glossary_terms[term_id] = title

    except Exception as e:
        print(f"  ⚠️ Could not load glossary.csv: {e}")

    return glossary_terms


def load_glossary_from_markdown(glossary_dir):
    """
    Load glossary terms from markdown files (legacy method).

    Args:
        glossary_dir: Path to telar-content/texts/glossary/

    Returns:
        dict: Dictionary mapping term_id to term title
    """
    glossary_terms = {}

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


# Matches the markup that process_glossary_links emits: a resolved inline link
# (<a class="glossary-inline-link">…</a>) or the unresolved-term error span
# (<span class="glossary-link-error">…</span>). The inner text is captured so it
# can be unwrapped. Non-greedy and DOTALL; the inner text is always HTML-escaped
# (so it can never itself contain a closing </a> / </span>), which keeps this safe.
_GLOSSARY_MARKUP_RE = re.compile(
    r'<a\b[^>]*\bclass="glossary-inline-link"[^>]*>(.*?)</a>'
    r'|<span\b[^>]*\bclass="glossary-link-error"[^>]*>(.*?)</span>',
    re.DOTALL,
)


def strip_glossary_links(text):
    """Reduce glossary link markup back to its plain visible text.

    `process_glossary_links` injects HTML (`<a class="glossary-inline-link">` or a
    `glossary-link-error` span) into a string. Protected (encrypted) stories are
    rendered at runtime by a path that HTML-escapes the step answer and has no
    glossary panel, so that markup would surface as escaped tag-text instead of a
    link. For those stories we drop the wrapper and keep the visible text: a
    resolved link becomes its title, an unresolved term becomes its `⚠️ [[term]]`
    indicator text. The captured inner text is HTML-unescaped so that the runtime's
    own escaping pass produces correctly-escaped output (no double-escaping).

    Args:
        text: An already-glossary-processed string (HTML), or falsy.

    Returns:
        The string with glossary wrappers removed, or the input unchanged if falsy.
    """
    if not text:
        return text

    def unwrap(match):
        inner = match.group(1) if match.group(1) is not None else match.group(2)
        return html.unescape(inner)

    return _GLOSSARY_MARKUP_RE.sub(unwrap, text)


def process_glossary_links(text, glossary_terms, warnings_list=None, step_num=None, layer_name=None):
    """
    Transform [[term]] or [[display|term]] syntax into glossary link HTML.

    Args:
        text: HTML text to process (already converted from markdown)
        glossary_terms: Dictionary mapping term_id to term title
        warnings_list: Optional list to append warning messages
        step_num: Optional step number for warning messages
        layer_name: Optional layer name (e.g., 'layer1', 'layer2') for warning context

    Returns:
        str: Text with glossary links transformed to HTML
    """
    if not text or not glossary_terms:
        return text

    # Build a case-insensitive lookup that resolves an author's [[term]] (any
    # casing) to the ACTUAL stored key. Glossary loaders store term_id verbatim
    # — load_glossary_from_csv, load_glossary_from_markdown, and the demo bundle
    # do not lowercase keys (e.g. the demo glossary stores 'IIIF'). Resolving to
    # the stored key (rather than a lowercased copy) keeps the rendered
    # data-term-id equal to the published glossary page slug, which telar.js
    # fetches on click. Mirrors the objects_lower_map pattern in stories.py.
    # If two keys differ only by case, the last one wins — acceptable because the
    # glossary page system would already collide on such keys.
    glossary_lower_map = {key.lower(): key for key in glossary_terms}

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
        # title lookup succeeds and the rendered data-term-id matches the glossary
        # page slug telar.js fetches to open the panel.
        canonical_id = glossary_lower_map.get(raw_term_id.lower())

        # Check if term exists in glossary (case-insensitive)
        if canonical_id is not None:
            term_id = canonical_id
            if not has_custom_display:
                # Use the glossary title as display text
                display_text = glossary_terms[term_id]
            # Valid term - create glossary link
            # Note: data-term-url is intentionally omitted; JavaScript fallback in telar.js
            # constructs the URL dynamically from the current page URL, which correctly
            # handles baseurl for all deployment scenarios (GitHub Pages, subpaths, etc.)
            # Add data-demo attribute for demo terms (prefixed with demo-)
            demo_attr = ' data-demo="true"' if term_id.startswith('demo-') else ''
            # Escape the canonical term id (attribute) and display text so a
            # quote or angle bracket in either cannot break out of the link markup.
            return f'<a href="#" class="glossary-inline-link" data-term-id="{html.escape(term_id, quote=True)}"{demo_attr}>{html.escape(display_text)}</a>'
        else:
            # Invalid term - create error indicator (author's original casing preserved)
            if warnings_list is not None:
                warning_msg = get_lang_string('errors.object_warnings.glossary_term_not_found', term_id=raw_term_id)
                warnings_list.append({
                    'step': step_num,
                    'type': 'glossary',
                    'term_id': raw_term_id,
                    'layer': layer_name,
                    'message': warning_msg
                })
            return f'<span class="glossary-link-error" data-term-id="{html.escape(raw_term_id, quote=True)}">\u26a0\ufe0f [[{html.escape(match.group(1))}]]</span>'

    return re.sub(pattern, replace_glossary_link, text)
