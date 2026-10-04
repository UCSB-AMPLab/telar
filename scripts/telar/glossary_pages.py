"""
Glossary pages for the Jekyll glossary collection.

Writes _jekyll-files/_glossary/ from the site's glossary.csv (or its legacy
markdown files) and from the demo bundle's glossary, with glossary-to-glossary
links resolved. Called by generate_collections.py.

Version: v1.8.0
"""

import json
import re
import shutil
from pathlib import Path

from telar.images import process_images
from telar.glossary import (load_glossary_terms, markdown_glossary_title,
                            process_glossary_links, read_glossary_sheet)
from telar.markdown import read_markdown_file, process_inline_content
from telar.core import find_csv_with_fallback
from telar.latex import convert_markdown, has_latex
from telar.frontmatter import FRONTMATTER_PATTERN, _as_text, _frontmatter_block
from telar.story_pages import jekyll_slug
from telar.glossary_kinds import front_matter_kind, resolve_kind, write_site_kinds


def _csv_page_rows(csv_path):
    """The rows of glossary.csv that become pages, as (term_id, title, row).

    The one decision of which site terms are published from a CSV: a sheet
    missing a required column publishes none, and a row without an id or a
    title, or whose id starts with `#`, is not a term.
    """
    df = read_glossary_sheet(csv_path)

    for col in ['term_id', 'title', 'definition']:
        if col not in df.columns:
            print(f"  ⚠️ glossary.csv missing required column: {col}")
            return []

    rows = []
    for _, row in df.iterrows():
        term_id = str(row.get('term_id', '')).strip()
        title = str(row.get('title', '')).strip()
        if not term_id or not title or term_id.startswith('#'):
            continue
        rows.append((term_id, title, row))
    return rows


def _split_markdown_term(content):
    """(frontmatter_text, body, term_id) of a legacy glossary file; the
    first is None without front matter, the last without a term_id."""
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return None, None, None
    frontmatter_text = match.group(1)
    term_id_match = re.search(r'term_id:\s*(\S+)', frontmatter_text)
    return (frontmatter_text, match.group(2).strip(),
            term_id_match.group(1) if term_id_match else None)


def site_glossary_pages():
    """The site's own glossary pages as {term_id: (title, kind id)}, the
    title and kind as the page shows them, chosen as `generate_glossary`
    chooses its source: glossary.csv when present, else the legacy markdown
    files. A markdown page without a `title` shows its term id.
    """
    csv_path = Path(find_csv_with_fallback('telar-content/spreadsheets/glossary', 'glosario'))
    md_path = Path('telar-content/texts/glossary')
    pages = {}
    if csv_path.exists():
        for term_id, title, row in _csv_page_rows(csv_path):
            pages[term_id] = (title, resolve_kind(row.get('kind', ''), warn=False))
        return pages
    if md_path.exists():
        for source_file in md_path.glob('*.md'):
            with open(source_file, 'r', encoding='utf-8') as f:
                frontmatter_text, _body, term_id = _split_markdown_term(f.read())
            if term_id:
                pages[term_id] = (markdown_glossary_title(frontmatter_text) or term_id,
                                  resolve_kind(front_matter_kind(frontmatter_text), warn=False))
    return pages


def _generate_glossary_from_csv(csv_path, glossary_dir, glossary_terms):
    """Generate glossary files from CSV.

    Args:
        csv_path: Path to glossary.csv
        glossary_dir: Output directory for Jekyll files
        glossary_terms: Dict of term_id -> title for link processing
    """
    for term_id, title, row in _csv_page_rows(csv_path):
        definition = str(row.get('definition', '')).strip()
        related_terms_raw = str(row.get('related_terms', '')).strip()

        # Parse related_terms (pipe-separated)
        related_terms = []
        if related_terms_raw and related_terms_raw != 'nan':
            related_terms = [t.strip() for t in related_terms_raw.split('|') if t.strip()]

        # Process definition: file reference or inline content
        # If definition looks like a filename (short, no spaces/newlines), try as file first
        looks_like_filename = ('\n' not in definition and ' ' not in definition
                               and len(definition) <= 200)
        if looks_like_filename:
            file_def = definition if definition.endswith('.md') else f'{definition}.md'
            glossary_path = file_def if file_def.startswith('glossary/') else f'glossary/{file_def}'
            content_data = read_markdown_file(glossary_path)
        else:
            content_data = None

        if content_data:
            body = content_data['content']
        else:
            # No file found or inline content — treat as inline
            content_data = process_inline_content(definition)
            body = content_data['content'] if content_data else ''

        # Process glossary-to-glossary links
        warnings_list = []
        processed = process_glossary_links(body, glossary_terms, warnings_list)

        for warning in warnings_list:
            print(f"  Warning: {warning}")

        fields = {'term_id': _as_text(term_id),
                  'title': _as_text(title)}
        # A sequence, not a joined string: the layout iterates this, and
        # Liquid walks a string as a single item, so two related terms
        # written as one scalar are looked up as one id that matches no
        # term and the section renders empty.
        if related_terms:
            fields['related_terms'] = [_as_text(term) for term in related_terms]
        if has_latex(processed):
            fields['has_latex'] = True
        fields['glossary_kind'] = resolve_kind(
            row.get('kind', ''), where=f"Glossary entry '{term_id}'")
        fields['layout'] = 'glossary'

        # Write Jekyll file
        filepath = glossary_dir / f"{term_id}.md"
        output_content = ('---\n' + _frontmatter_block(fields)
                          + '---\n\n' + processed + '\n')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(output_content)

        print(f"✓ Generated {filepath}")


def _generate_glossary_from_markdown(md_path, glossary_dir, glossary_terms):
    """Generate glossary files from markdown (legacy method).

    Args:
        md_path: Path to telar-content/texts/glossary/
        glossary_dir: Output directory for Jekyll files
        glossary_terms: Dict of term_id -> title for link processing
    """
    for source_file in md_path.glob('*.md'):
        # Read the source markdown file
        with open(source_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Verbatim. Normalising it means cutting lines out of the author's
        # text or reading their frontmatter and writing it back, and both
        # decide what a file means: a cut is truncated by a blank line or a
        # comment and hands the remainder to the key above it, and a
        # rewrite unquotes a date the author quoted, which Ruby then reads
        # as a Date. So a list-valued key such as `related_terms` reaches
        # the page exactly as the author typed it, and has to be a YAML
        # list: the layout iterates it, and Liquid walks a scalar string as
        # one item, so `a,b` is looked up as a single id matching no term.
        frontmatter_text, body, term_id = _split_markdown_term(content)

        if frontmatter_text is None:
            print(f"Warning: No frontmatter found in {source_file}")
            continue

        if not term_id:
            print(f"Warning: No term_id found in {source_file}")
            continue

        filepath = glossary_dir / f"{term_id}.md"

        # Written as a key of its own after the author's front matter, which
        # is copied verbatim and may spell the kind in either language.
        glossary_kind = resolve_kind(
            front_matter_kind(frontmatter_text),
            where=f"Glossary entry '{term_id}' ({source_file.name})")

        # Process body through the same pipeline as pages
        warnings_list = []

        # 1. Process images (size syntax and captions)
        processed = process_images(body)

        # 2. Convert markdown to HTML
        processed = convert_markdown(
            processed,
            extensions=['extra', 'nl2br', 'sane_lists']
        )

        # 3. Process glossary links ([[term]] syntax)
        processed = process_glossary_links(processed, glossary_terms, warnings_list)

        # Print any warnings
        for warning in warnings_list:
            print(f"  Warning: {warning}")

        # Check definition for LaTeX content
        latex_flag = ""
        if has_latex(processed):
            latex_flag = "\nhas_latex: true"

        # Write to collection with layout added
        # Quoted as front matter: a site kind's id is whatever its config
        # gives.
        kind_line = _frontmatter_block({'glossary_kind': _as_text(glossary_kind)}).rstrip('\n')
        output_content = f"""---
{frontmatter_text}
{kind_line}
layout: glossary{latex_flag}
---

{processed}
"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(output_content)

        print(f"✓ Generated {filepath}")


def _demo_glossary_fields(term, term_id):
    """The front matter of a demo glossary entry's page."""
    fields = {'term_id': _as_text(term_id),
              'title': _as_text(term.get('title', term_id)),
              'glossary_kind': resolve_kind(
                  term.get('kind', ''),
                  where=f"Demo glossary entry '{term_id}'"),
              'layout': 'glossary',
              # The layout tests this as a boolean.
              'demo': True}
    # A sequence, as a site's entry writes it: the layout iterates it.
    if term.get('related_terms'):
        fields['related_terms'] = [_as_text(related)
                                   for related in term['related_terms']]
    if has_latex(term.get('content', '')):
        fields['has_latex'] = True
    return fields


def generate_glossary():
    """Generate glossary markdown files from user content and demo JSON.

    Reads from (in order of precedence):
    - telar-content/spreadsheets/glossary.csv or glosario.csv (v0.8.0+ preferred)
    - telar-content/texts/glossary/*.md (legacy markdown files)
    - _data/demo-glossary.json (demo content from bundle)

    If both CSV and markdown exist, CSV takes precedence and a warning is shown.
    """
    glossary_dir = Path('_jekyll-files/_glossary')

    # Clean up old files to remove orphaned glossary terms
    if glossary_dir.exists():
        shutil.rmtree(glossary_dir)
        print(f"✓ Cleaned up old glossary files")

    glossary_dir.mkdir(parents=True, exist_ok=True)

    # The site's own kinds, for the layouts; written whether or not it has any,
    # so a kind removed from _config.yml leaves the page with the rest.
    write_site_kinds()

    # Load glossary terms for link processing (enables glossary-to-glossary linking)
    glossary_terms = load_glossary_terms()

    csv_path = Path(find_csv_with_fallback('telar-content/spreadsheets/glossary', 'glosario'))
    md_path = Path('telar-content/texts/glossary')

    # 1. Process user glossary from CSV (preferred) or markdown (legacy)
    if csv_path.exists():
        # Warn if markdown files also exist
        if md_path.exists() and any(md_path.glob('*.md')):
            print(f"  ⚠️ Found both glossary.csv and markdown files. Using CSV.")

        _generate_glossary_from_csv(csv_path, glossary_dir, glossary_terms)

    elif md_path.exists() and any(md_path.glob('*.md')):
        _generate_glossary_from_markdown(md_path, glossary_dir, glossary_terms)

    # 2. Process demo glossary from JSON
    demo_glossary_path = Path('_data/demo-glossary.json')
    if demo_glossary_path.exists():
        with open(demo_glossary_path, 'r', encoding='utf-8') as f:
            demo_glossary = json.load(f)

        # The directory was emptied above, so what it holds now is the
        # site's own glossary. Compared by slug, not file name: Jekyll
        # publishes `Viewer.md` and `viewer.md` both at /glossary/viewer/,
        # and a case-insensitive disk holds them as one file.
        site_slugs = {jekyll_slug(path.stem)
                      for path in glossary_dir.glob('*.md')}

        for term in demo_glossary:
            term_id = term.get('term_id', '')
            if not term_id:
                continue

            if jekyll_slug(term_id) in site_slugs:
                print(f"  ⚠️ Demo glossary term '{term_id}' skipped: the "
                      f"site's glossary has a term at the same address, "
                      f"which is kept.")
                continue

            filepath = glossary_dir / f"{term_id}.md"

            fields = _demo_glossary_fields(term, term_id)
            output_content = ('---\n' + _frontmatter_block(fields)
                              + '---\n\n' + term.get('content', '') + '\n')

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(output_content)

            print(f"✓ Generated {filepath} [DEMO]")
