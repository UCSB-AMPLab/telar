"""
Glossary Loading and Linking

This module deals with Telar's glossary system, which lets authors link
terms in story panel text to glossary definitions. Glossary terms can be
defined in two ways:

1. **CSV file** (v0.8.0+): `components/structures/glossary.csv` with columns
   `term_id`, `title`, `definition`, and `related_terms`. This is the
   preferred method for spreadsheet-first workflows.

2. **Markdown files** (legacy): Individual `.md` files in
   `components/texts/glossary/`, each with YAML frontmatter containing
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

Version: v0.8.0-beta
"""

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

        # Normalize column names (lowercase + bilingual mapping)
        df.columns = df.columns.str.lower().str.strip()
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
        glossary_dir: Path to components/texts/glossary/

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

    Checks for glossary.csv first (preferred), falls back to markdown files.
    If both exist, CSV takes precedence and a warning is shown.

    Returns:
        dict: Dictionary mapping term_id to term title, or empty dict if no glossary found
    """
    csv_path = Path('components/structures/glossary.csv')
    md_path = Path('components/texts/glossary')

    # Check if CSV exists (preferred source)
    if csv_path.exists():
        return load_glossary_from_csv(csv_path)

    # Fall back to markdown files
    elif md_path.exists() and any(md_path.glob('*.md')):
        return load_glossary_from_markdown(md_path)

    # No glossary content
    return {}


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

    # Pattern: [[display|term]] or [[term]] with flexible spacing
    # Captures: (optional_display) | (term_id)
    pattern = r'\[\[\s*([^|\]]+?)(?:\s*\|\s*([^|\]]+?))?\s*\]\]'

    def replace_glossary_link(match):
        # If pipe is present: [[term|display]], else [[term]]
        if match.group(2):  # Has pipe
            term_id = match.group(1).strip()
            display_text = match.group(2).strip()
        else:  # No pipe
            term_id = match.group(1).strip()
            # Use glossary title as display text
            display_text = glossary_terms.get(term_id, term_id)

        # Check if term exists in glossary
        if term_id in glossary_terms:
            # Valid term - create glossary link
            # Note: data-term-url is intentionally omitted; JavaScript fallback in telar.js
            # constructs the URL dynamically from the current page URL, which correctly
            # handles baseurl for all deployment scenarios (GitHub Pages, subpaths, etc.)
            # Add data-demo attribute for demo terms (prefixed with demo-)
            demo_attr = ' data-demo="true"' if term_id.startswith('demo-') else ''
            return f'<a href="#" class="glossary-inline-link" data-term-id="{term_id}"{demo_attr}>{display_text}</a>'
        else:
            # Invalid term - create error indicator
            if warnings_list is not None:
                # Determine layer number for display
                layer_num = layer_name[-1] if layer_name and layer_name.startswith('layer') else ''
                warning_msg = get_lang_string('errors.object_warnings.glossary_term_not_found', term_id=term_id, layer_num=layer_num)
                warnings_list.append({
                    'step': step_num,
                    'type': 'glossary',
                    'term_id': term_id,
                    'layer': layer_name,
                    'message': warning_msg
                })
            return f'<span class="glossary-link-error" data-term-id="{term_id}">\u26a0\ufe0f [[{match.group(1)}]]</span>'

    return re.sub(pattern, replace_glossary_link, text)
