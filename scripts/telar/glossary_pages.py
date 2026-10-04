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
from telar.glossary import (first_at_each_address, glossary_link_map, glossary_term_address,
                            markdown_glossary_permalink, place_demo_terms,
                            markdown_glossary_title,
                            process_glossary_links, read_glossary_sheet)
from telar.markdown import read_markdown_file, process_inline_content
from telar.core import find_csv_with_fallback
from telar.latex import convert_markdown, has_latex
from telar.frontmatter import FRONTMATTER_PATTERN, _as_text, _frontmatter_block
from telar.glossary_kinds import front_matter_kind, resolve_kind, write_site_kinds


class GlossaryPages(dict):
    """`site_glossary_pages()`'s {term_id: (title, kind id)}, with the
    site-relative path of each page that is not published at its slug in
    `addresses`."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.addresses = {}


def _csv_page_rows(csv_path, warn_missing=True):
    """The rows of glossary.csv that become pages, as (term_id, title, row).

    The one decision of which site terms are published from a CSV: a sheet
    missing a required column publishes none, a row without an id or a
    title, or whose id starts with `#`, is not a term, and of rows whose ids
    share an address the first keeps it. `warn_missing` says whether a
    missing column and a shared address are reported; the link map reads
    the sheet once per story and leaves the report to the generator.
    """
    df = read_glossary_sheet(csv_path)

    for col in ['term_id', 'title', 'definition']:
        if col not in df.columns:
            if warn_missing:
                print(f"  ⚠️ glossary.csv missing required column: {col}")
            return []

    rows = []
    for _, row in df.iterrows():
        term_id = str(row.get('term_id', '')).strip()
        title = str(row.get('title', '')).strip()
        if not term_id or not title or term_id.startswith('#'):
            continue
        rows.append((term_id, title, row))
    kept = first_at_each_address(
        [(term_id, glossary_term_address(term_id), (term_id, title, row))
         for term_id, title, row in rows], warn_missing)
    return [item for _id, _address, item in kept]


def _csv_pages(rows):
    """The `site_glossary_pages` entries of `_csv_page_rows`' rows."""
    pages = GlossaryPages()
    for term_id, title, row in rows:
        pages[term_id] = (title, resolve_kind(row.get('kind', ''), warn=False))
    return pages


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


def _markdown_terms(md_path, warn=True):
    """The legacy glossary files that become pages, in file-name order, as
    (source_file, frontmatter_text, body, term_id, permalink).

    A file without front matter or a `term_id` is not a term. A page is
    published at its front matter's `permalink` when it has one, so that is
    its address, and of files whose pages share an address the first keeps
    it. `warn` says whether these are reported.
    """
    terms = []
    for source_file in sorted(md_path.glob('*.md')):
        with open(source_file, 'r', encoding='utf-8') as f:
            frontmatter_text, body, term_id = _split_markdown_term(f.read())
        if frontmatter_text is None:
            if warn:
                print(f"Warning: No frontmatter found in {source_file}")
            continue
        if not term_id:
            if warn:
                print(f"Warning: No term_id found in {source_file}")
            continue
        permalink = markdown_glossary_permalink(frontmatter_text)
        terms.append((term_id, glossary_term_address(term_id, permalink),
                      (source_file, frontmatter_text, body, term_id, permalink)))
    return [item for _id, _address, item in first_at_each_address(terms, warn)]


def _markdown_pages(terms):
    """The `site_glossary_pages` entries of `_markdown_terms`' files. A page
    without a `title` shows its term id."""
    pages = GlossaryPages()
    for _source, frontmatter_text, _body, term_id, permalink in terms:
        pages[term_id] = (markdown_glossary_title(frontmatter_text) or term_id,
                          resolve_kind(front_matter_kind(frontmatter_text), warn=False))
        if permalink:
            pages.addresses[term_id] = permalink
    return pages


def site_glossary_pages(warn_missing=True):
    """The site's own glossary pages as {term_id: (title, kind id)}, the
    title and kind as the page shows them, chosen as `generate_glossary`
    chooses its source: glossary.csv when present, else the legacy markdown
    files. The `addresses` of the result holds each page published away
    from its slug. `warn_missing` is passed to `_csv_page_rows` and
    `_markdown_terms`.
    """
    csv_path = Path(find_csv_with_fallback('telar-content/spreadsheets/glossary', 'glosario'))
    md_path = Path('telar-content/texts/glossary')
    if csv_path.exists():
        return _csv_pages(_csv_page_rows(csv_path, warn_missing))
    if md_path.exists():
        return _markdown_pages(_markdown_terms(md_path, warn_missing))
    return GlossaryPages()


def _generate_glossary_from_csv(csv_path, glossary_dir, glossary_terms, rows=None):
    """Generate glossary files from CSV.

    Args:
        csv_path: Path to glossary.csv
        glossary_dir: Output directory for Jekyll files
        glossary_terms: Dict of term_id -> title for link processing
        rows: `_csv_page_rows(csv_path)` when the caller has already read
            the sheet; read here otherwise
    """
    if rows is None:
        rows = _csv_page_rows(csv_path)
    for term_id, title, row in rows:
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


def _generate_glossary_from_markdown(md_path, glossary_dir, glossary_terms, terms=None):
    """Generate glossary files from markdown (legacy method).

    Args:
        md_path: Path to telar-content/texts/glossary/
        glossary_dir: Output directory for Jekyll files
        glossary_terms: Dict of term_id -> title for link processing
        terms: `_markdown_terms(md_path)` when the caller has already read
            the files; read here otherwise
    """
    if terms is None:
        terms = _markdown_terms(md_path)
    for source_file, frontmatter_text, body, term_id, _permalink in terms:
        # The front matter is copied verbatim. Normalising it means cutting
        # lines out of the author's text or reading their frontmatter and
        # writing it back, and both decide what a file means: a cut is
        # truncated by a blank line or a comment and hands the remainder to
        # the key above it, and a rewrite unquotes a date the author quoted,
        # which Ruby then reads as a Date. So a list-valued key such as
        # `related_terms` reaches the page exactly as the author typed it,
        # and has to be a YAML list: the layout iterates it, and Liquid
        # walks a scalar string as one item, so `a,b` is looked up as a
        # single id matching no term.
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

    Returns the site's link map (`load_glossary_terms()`'s), so the pages
    that run after it need not read the sheet again: each warning the read
    raises is printed once per run.
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

    csv_path = Path(find_csv_with_fallback('telar-content/spreadsheets/glossary', 'glosario'))
    md_path = Path('telar-content/texts/glossary')

    # The link map and the pages come from one read of the sheet, so a
    # warning that read raises is printed once.
    csv_rows = None
    markdown_terms = None
    if csv_path.exists():
        csv_rows = _csv_page_rows(csv_path)
        site_pages = _csv_pages(csv_rows)
    elif md_path.exists() and any(md_path.glob('*.md')):
        markdown_terms = _markdown_terms(md_path)
        site_pages = _markdown_pages(markdown_terms)
    else:
        site_pages = GlossaryPages()
    glossary_terms = glossary_link_map(site_pages)

    # 1. Process user glossary from CSV (preferred) or markdown (legacy)
    if csv_rows is not None:
        # Warn if markdown files also exist
        if md_path.exists() and any(md_path.glob('*.md')):
            print(f"  ⚠️ Found both glossary.csv and markdown files. Using CSV.")

        _generate_glossary_from_csv(csv_path, glossary_dir, glossary_terms, csv_rows)

    elif markdown_terms is not None:
        _generate_glossary_from_markdown(md_path, glossary_dir, glossary_terms, markdown_terms)

    # 2. Process demo glossary from JSON
    demo_glossary_path = Path('_data/demo-glossary.json')
    if demo_glossary_path.exists():
        with open(demo_glossary_path, 'r', encoding='utf-8') as f:
            demo_glossary = json.load(f)

        # Jekyll publishes `Viewer.md` and `viewer.md` both at
        # /glossary/viewer/, a legacy page may sit at a permalink of its
        # own, and a case-insensitive disk holds `Viewer.md` and
        # `viewer.md` as one file. `place_demo_terms` decides which demo
        # terms are written, as the demo stories' link map does.
        demo_terms = [term for term in demo_glossary if term.get('term_id', '')]
        placements = place_demo_terms(site_pages,
                                      [term['term_id'] for term in demo_terms])

        for term, placement in zip(demo_terms, placements):
            term_id = placement.term_id
            if placement.reason == 'address':
                print(f"  ⚠️ Demo glossary term '{term_id}' skipped: another "
                      f"glossary term is published at {placement.address}, "
                      f"which is kept.")
                continue
            if placement.reason == 'file':
                whose = "site's" if placement.owner_is_site else 'demo'
                print(f"  ⚠️ Demo glossary term '{term_id}' skipped: the "
                      f"{whose} glossary term '{placement.owner}' is written to "
                      f"the same file, _glossary/{placement.owner}.md, which is kept.")
                continue
            filepath = glossary_dir / f"{term_id}.md"

            fields = _demo_glossary_fields(term, term_id)
            output_content = ('---\n' + _frontmatter_block(fields)
                              + '---\n\n' + term.get('content', '') + '\n')

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(output_content)

            print(f"✓ Generated {filepath} [DEMO]")

    return glossary_terms
