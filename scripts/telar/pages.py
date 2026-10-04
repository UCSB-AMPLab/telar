"""
User pages for the Jekyll pages collection.

Writes _jekyll-files/_pages/ from telar-content/texts/pages/, through the
widget, image, markdown and glossary pipeline, choosing a localized sister
file where the site's language has one. Also checks each page's `title_key`.
Called by generate_collections.py.

Version: v1.8.0
"""

import shutil
from pathlib import Path

import yaml

from telar.widgets import process_widgets
from telar.images import process_images
from telar.glossary import process_glossary_links, load_glossary_terms
from telar.latex import convert_markdown
from telar.frontmatter import FRONTMATTER_LOAD_ERRORS, FRONTMATTER_PATTERN


# Front-matter keys a page source does not get to decide. A page's URL comes
# from the `pages` collection permalink and its layout from the collection
# default, so a source claiming either takes a decision that belongs to the
# build. Pre-0.9.0 sites carry both — `layout: page` and `permalink: /about/`
# in telar-content/texts/pages/*.md — and the permalink puts the source and
# the page generated from it at the same address, which Jekyll reports as a
# conflict and the build gate then fails on.
#
# Stripping them here is what makes generation authoritative. The migration
# removes them from the source file too, but a site whose pages have been
# through a round trip that preserves unrecognised front matter can have them
# back, so this path must hold regardless of whether the strip ever ran.
GENERATED_PAGE_IGNORED_KEYS = ('layout', 'permalink')


def _strip_generated_page_keys(frontmatter_text):
    """Drop the keys a page source does not get to decide.

    Filters the front-matter text rather than re-serialising the parsed dict,
    so every other key keeps the author's own spelling, ordering and comments.
    A dropped key takes its continuation lines with it.
    """
    kept = []
    dropping = False
    for line in frontmatter_text.split('\n'):
        stripped = line.lstrip()
        indent = line[:len(line) - len(stripped)]

        if dropping:
            # A continuation line is indented under the key it belongs to.
            if indent and stripped:
                continue
            dropping = False

        key = stripped.split(':', 1)[0].strip() if ':' in stripped else None
        if not indent and key in GENERATED_PAGE_IGNORED_KEYS:
            dropping = True
            continue

        kept.append(line)

    return '\n'.join(kept).strip('\n')


def _parse_page_frontmatter(source_file):
    """Parse a page markdown file. Returns (frontmatter_text, frontmatter_dict, body) or None on error."""
    with open(source_file, 'r', encoding='utf-8') as f:
        content = f.read()

    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        print(f"❌ Error: No frontmatter found in {source_file}")
        print("  Pages must have YAML frontmatter (--- at start and end)")
        return None

    frontmatter_text = match.group(1)
    body = match.group(2).strip()

    try:
        frontmatter_dict = yaml.safe_load(frontmatter_text) or {}
    except FRONTMATTER_LOAD_ERRORS as e:
        print(f"❌ Error: Invalid YAML frontmatter in {source_file}: {e}")
        return None

    return frontmatter_text, frontmatter_dict, body


# The one language-file section a page's `title_key` is read from.
# `_layouts/default.html` resolves `title_key: navigation.objects` to the nav
# label, so the browser tab says what the menu says. Held to that section so
# the rest of the language file is the framework's own and can be checked
# for strings nothing reads.
TITLE_KEY_SECTION = 'navigation'

# Where a page with front matter can be: the three built-in pages, and the
# author's pages the pages collection is generated from.
TITLE_KEY_SOURCES = ('index.md', 'pages/*.md', 'telar-content/texts/pages/*.md')


def check_title_keys(root='.'):
    """Warn about a `title_key` the layout will not read.

    The page still builds, and its tab shows its own `title` instead.
    Returns the warnings, for the tests.
    """
    warnings = []
    for pattern in TITLE_KEY_SOURCES:
        for source in sorted(Path(root).glob(pattern)):
            parsed = _parse_page_frontmatter(source)
            if parsed is None:
                continue
            value = parsed[1].get('title_key')
            if value is None:
                continue
            parts = str(value).split('.')
            if len(parts) == 2 and parts[0] == TITLE_KEY_SECTION and parts[1]:
                continue
            message = (f"{source.relative_to(root)}: title_key '{value}' is not "
                       f"a {TITLE_KEY_SECTION}.* key, so the browser tab shows "
                       f"the page's title instead. A page title can only be "
                       f"translated through a {TITLE_KEY_SECTION}.* key.")
            print(f"  [WARN] {message}")
            warnings.append(message)
    return warnings


def generate_pages(telar_language='en', glossary_terms=None):
    """Generate processed page files from user markdown sources.

    Reads from telar-content/texts/pages/*.md, processes widgets and glossary links,
    and outputs to _jekyll-files/_pages/ for the pages collection.

    Localization: a sister file with frontmatter `localized_for: <canonical>.md`
    and `language: <code>` is treated as the localized version of <canonical>.md.
    When `telar_language` matches the sister's `language`, the sister is used
    in place of the canonical file but is output under the canonical filename
    (so the URL is the same in both languages). Sister files for other
    languages are skipped.

    `glossary_terms` is the link map the caller has already loaded
    (`generate_glossary()` returns it); read here when omitted.
    """
    source_dir = Path('telar-content/texts/pages')
    output_dir = Path('_jekyll-files/_pages')

    # Skip if source directory doesn't exist
    if not source_dir.exists():
        print("No telar-content/texts/pages/ directory found - skipping page generation")
        return

    # Clean up old files
    if output_dir.exists():
        shutil.rmtree(output_dir)
        print("✓ Cleaned up old page files")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load glossary terms for link processing
    if glossary_terms is None:
        glossary_terms = load_glossary_terms()

    # Pass 1: separate canonical pages from localized sisters and build a sister map
    canonicals = []  # list of source files
    sisters = {}     # {canonical_filename: {language: source_file}}

    for source_file in source_dir.glob('*.md'):
        parsed = _parse_page_frontmatter(source_file)
        if parsed is None:
            continue
        _, fm, _ = parsed
        if fm.get('localized_for'):
            canonical = fm['localized_for']
            lang = fm.get('language')
            if not lang:
                print(f"  Warning: {source_file.name} has localized_for but no language; skipping")
                continue
            sisters.setdefault(canonical, {})[lang] = source_file
        else:
            canonicals.append(source_file)

    # Pass 2: for each canonical page, pick the active-language source and process
    for canonical_file in canonicals:
        canonical_filename = canonical_file.name

        # If a sister exists for the active language, use it; else use canonical
        active_sister = sisters.get(canonical_filename, {}).get(telar_language)
        if active_sister is not None:
            source_file = active_sister
            print(f"  Using {source_file.name} for {canonical_filename} (telar_language={telar_language})")
        else:
            source_file = canonical_file

        parsed = _parse_page_frontmatter(source_file)
        if parsed is None:
            continue
        frontmatter_text, _, body = parsed

        # Process body through the same pipeline as story layers
        warnings_list = []

        # 1. Process widgets (:::carousel, :::tabs, :::accordion)
        processed = process_widgets(body, str(source_file), warnings_list)

        # 2. Process images (size syntax and captions)
        processed = process_images(processed)

        # 3. Convert markdown to HTML
        processed = convert_markdown(
            processed,
            extensions=['extra', 'nl2br', 'sane_lists']
        )

        # 4. Process glossary links ([[term]] syntax)
        processed = process_glossary_links(processed, glossary_terms, warnings_list)

        # Print any warnings
        for warning in warnings_list:
            print(f"  Warning: {warning}")

        # Write processed file to output directory under the canonical filename,
        # so the URL is stable across languages
        output_file = output_dir / canonical_filename

        output_content = f"""---
{_strip_generated_page_keys(frontmatter_text)}
---

{processed}
"""

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output_content)

        print(f"✓ Generated {output_file}")
