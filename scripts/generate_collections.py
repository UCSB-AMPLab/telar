#!/usr/bin/env python3
"""
Generate Jekyll Collection Markdown Files from JSON Data

This script is the bridge between Telar's JSON data and Jekyll's
content system. Jekyll requires each page to be a markdown file with
YAML frontmatter in a specific directory (called a "collection"). This
script reads the JSON files produced by csv_to_json.py and generates
those markdown files.

It creates four types of collection files:

- Objects (_jekyll-files/_objects/): One file per exhibition object,
  with metadata like title, creator, period, and IIIF manifest URL in
  the frontmatter.
- Stories (_jekyll-files/_stories/): One file per story, linking to its
  JSON data file, setting the story layout, and declaring the permalink it
  renders at. The same identifier-to-URL mapping is recorded in the story
  page manifest (telar/story_pages.py) so the post-build encryption step
  can find each protected story's page without predicting its URL.
- Glossary (_jekyll-files/_glossary/): Terms from both user markdown
  files (telar-content/texts/glossary/) and demo content, with glossary-
  to-glossary link processing.
- Pages (_jekyll-files/_pages/): User-authored pages from
  telar-content/texts/pages/, processed through the widget and glossary
  pipeline.

The script respects development feature flags (skip_stories,
skip_collections) from _config.yml, which allow developers to
temporarily suppress certain collections during development.
Legacy names (hide_stories, hide_collections) are also supported.

Version: v1.7.0
"""

import argparse
import json
import re
import shutil
from pathlib import Path

import markdown
import pandas as pd
import yaml

# Import processing functions from telar package
from telar.widgets import process_widgets
from telar.images import process_images
from telar.glossary import process_glossary_links, load_glossary_terms
from telar.markdown import read_markdown_file, process_inline_content
from telar.core import find_csv_with_fallback
from telar.latex import has_latex
from telar.media_type import detect_media_type, AUDIO_EXTENSIONS
from telar.story_pages import (
    ManifestError, build_manifest, remove_manifest, stories_permalink,
    write_manifest,
)

# Fields already handled explicitly in generate_objects() frontmatter.
# Any key NOT in this set is treated as a custom field and written to extra_metadata.
KNOWN_OBJECT_FIELDS = {
    'object_id', 'title', 'creator', 'period', 'medium', 'dimensions',
    'location', 'credit', 'thumbnail', 'iiif_manifest', 'source_url',
    'source', 'object_warning', 'object_warning_short', 'year',
    'object_type', 'subjects', 'is_featured_sample', '_demo',
    'description', 'featured', 'alt_text',
    # v0.10.0: auto-detected media type and audio metadata
    'media_type', 'audio_duration', 'audio_filesize', 'audio_format',
}


FRONTMATTER_PATTERN = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)$', re.DOTALL)


# Control characters that must not survive into a double-quoted YAML scalar,
# with the escape YAML defines for each. A line break is the dangerous one: the
# scalar would span lines, and frontmatter is located by splitting on a line
# that is exactly `---` before any YAML is parsed, so a value could end the
# block early and spill the rest of the metadata into the page body.
_YAML_CONTROL = {
    '\n': '\\n',
    '\r': '\\r',
    '\t': '\\t',
}


def _yaml_escape(value):
    """Escape a string value for safe inclusion in double-quoted YAML.

    Backslashes first: every other replacement introduces one, and doing it
    later would double them.
    """
    s = str(value)
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    for character, escape in _YAML_CONTROL.items():
        s = s.replace(character, escape)
    return s


def _object_metadata(obj, media_type, source_url):
    """The frontmatter fields that are written only when they have a value.

    Empty strings are truthy in Liquid, so a field written empty would make
    every `{% if %}` guarding it true on a page that has nothing to show.
    """
    medium_value = obj.get('medium', '') or obj.get('object_type', '')
    fields = {
        'alt_text': obj.get('alt_text', ''),
        'creator': obj.get('creator', ''),
        'period': obj.get('period', ''),
        'medium': medium_value,
        'dimensions': obj.get('dimensions', ''),
        'location': obj.get('source', '') or obj.get('location', ''),
        'credit': obj.get('credit', ''),
        'thumbnail': obj.get('thumbnail', ''),
        'iiif_manifest': obj.get('iiif_manifest', ''),
        'source_url': source_url,
        'object_warning': obj.get('object_warning', ''),
        'object_warning_short': obj.get('object_warning_short', ''),
    }
    return ''.join(f'{key}: "{_yaml_escape(str(value))}"\n'
                   for key, value in fields.items() if value)


def _object_flags(obj, is_demo):
    """The optional scalars and the two booleans, in the order written."""
    lines = ''
    if obj.get('year'):
        lines += f'year: "{obj.get("year")}"\n'
    # Frontmatter carries 'medium' only; object_type is not written
    if obj.get('subjects'):
        lines += f'subjects: "{obj.get("subjects")}"\n'
    if obj.get('is_featured_sample'):
        lines += "is_featured_sample: true\n"
    if is_demo:
        lines += "demo: true\n"
    return lines


def _audio_duration(object_id):
    """Duration from the peaks file process_audio.py writes, if it is there."""
    peaks_path = Path(f'assets/audio/peaks/{object_id}.json')
    if not peaks_path.exists():
        return ''
    try:
        with open(peaks_path, 'r') as pf:
            peaks_data = json.load(pf)
        duration = peaks_data.get('duration', 0)
    except (json.JSONDecodeError, KeyError):
        return ''
    return f'audio_duration: {duration}\n' if duration else ''


def _audio_file_details(object_id):
    """Size and format from the first matching file on disk.

    The first match wins: on a case-insensitive filesystem `.mp3` and `.MP3`
    both resolve to the same file, so continuing would write the block twice.
    """
    for ext in AUDIO_EXTENSIONS:
        audio_path = Path(f'telar-content/objects/{object_id}{ext}')
        if not audio_path.exists():
            continue
        size_bytes = audio_path.stat().st_size
        if size_bytes < 1024 * 1024:
            size_str = f'{size_bytes / 1024:.0f} KB'
        else:
            size_str = f'{size_bytes / (1024 * 1024):.1f} MB'
        return (f'audio_filesize: "{size_str}"\n'
                f'audio_format: "{ext.lstrip(".").upper()}"\n')
    return ''


def _extra_metadata(obj):
    """Everything the object carries that the known set does not name.

    A CSV round-trip leaves absent cells as the float nan or the string
    'nan'; neither is a value anyone typed, so neither is written.
    """
    extra = {}
    for key, value in obj.items():
        if key in KNOWN_OBJECT_FIELDS:
            continue
        if value is None or (isinstance(value, float) and str(value) == 'nan'):
            continue
        s = str(value).strip()
        if s and s.lower() != 'nan':
            extra[key] = s

    if not extra:
        return ''
    lines = "extra_metadata:\n"
    for key, value in extra.items():
        lines += f'  {key}: "{_yaml_escape(value)}"\n'
    return lines


def _object_page(obj):
    """One object's markdown, frontmatter and body."""
    object_id = obj['object_id']
    source_url = obj.get('source_url', '') or ''
    media_type = detect_media_type(source_url, object_id)

    content = f'---\nobject_id: {object_id}\n'
    content += f'title: "{_yaml_escape(obj.get("title", ""))}"\n'
    content += _object_metadata(obj, media_type, source_url)
    # Always written: the template branches on it for every type.
    content += f'media_type: "{media_type}"\n'
    content += _object_flags(obj, obj.get('_demo', False))

    if media_type == 'Audio':
        content += _audio_duration(object_id)
        content += _audio_file_details(object_id)

    content += _extra_metadata(obj)

    description = obj.get('description', '')
    if description and has_latex(description):
        content += "has_latex: true\n"

    return content + f"""layout: object
---

{description}
"""


def _reset_objects_dir():
    """A fresh directory, so an object removed from the CSV loses its page."""
    objects_dir = Path('_jekyll-files/_objects')
    if objects_dir.exists():
        shutil.rmtree(objects_dir)
        print(f"✓ Cleaned up old object files")
    objects_dir.mkdir(parents=True, exist_ok=True)
    return objects_dir


def generate_objects():
    """Generate object markdown files from objects.json"""
    if not Path('_data/objects.json').exists():
        print("No objects.json found — skipping object generation")
        return

    with open('_data/objects.json', 'r') as f:
        objects = json.load(f)

    objects_dir = _reset_objects_dir()

    for obj in objects:
        object_id = obj.get('object_id', '')
        if not object_id:
            continue

        filepath = objects_dir / f"{object_id}.md"
        with open(filepath, 'w') as f:
            f.write(_object_page(obj))

        demo_label = " [DEMO]" if obj.get('_demo', False) else ""
        print(f"✓ Generated {filepath}{demo_label}")

def _generate_glossary_from_csv(csv_path, glossary_dir, glossary_terms):
    """Generate glossary files from CSV.

    Args:
        csv_path: Path to glossary.csv
        glossary_dir: Output directory for Jekyll files
        glossary_terms: Dict of term_id -> title for link processing
    """
    df = pd.read_csv(csv_path)

    # Normalize column names (lowercase + bilingual mapping)
    df.columns = df.columns.str.lower().str.strip()
    from telar.csv_utils import normalize_column_names, is_header_row
    df = normalize_column_names(df)

    # Filter out instruction columns starting with #
    df = df[[col for col in df.columns if not col.startswith('#')]]

    # Drop duplicate header row (bilingual CSVs have Spanish aliases in row 2)
    if len(df) > 0 and is_header_row(df.iloc[0].values):
        df = df.iloc[1:].reset_index(drop=True)

    required_cols = ['term_id', 'title', 'definition']
    for col in required_cols:
        if col not in df.columns:
            print(f"  ⚠️ glossary.csv missing required column: {col}")
            return

    for _, row in df.iterrows():
        term_id = str(row.get('term_id', '')).strip()
        title = str(row.get('title', '')).strip()
        definition = str(row.get('definition', '')).strip()
        related_terms_raw = str(row.get('related_terms', '')).strip()

        if not term_id or not title:
            continue

        # Skip comment/instruction rows (e.g. "# Make it lower-case...")
        if term_id.startswith('#'):
            continue

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

        # Check definition for LaTeX content
        latex_flag = ""
        if has_latex(processed):
            latex_flag = "\nhas_latex: true"

        # Build related_terms frontmatter
        related_str = ''
        if related_terms:
            related_str = f"\nrelated_terms: {','.join(related_terms)}"

        # Write Jekyll file
        filepath = glossary_dir / f"{term_id}.md"
        output_content = f"""---
term_id: {term_id}
title: "{_yaml_escape(title)}"{related_str}{latex_flag}
layout: glossary
---

{processed}
"""
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

        # Parse frontmatter and body
        match = FRONTMATTER_PATTERN.match(content)

        if not match:
            print(f"Warning: No frontmatter found in {source_file}")
            continue

        frontmatter_text = match.group(1)
        body = match.group(2).strip()

        # Extract term_id to determine output filename
        term_id_match = re.search(r'term_id:\s*(\S+)', frontmatter_text)
        if not term_id_match:
            print(f"Warning: No term_id found in {source_file}")
            continue

        term_id = term_id_match.group(1)
        filepath = glossary_dir / f"{term_id}.md"

        # Process body through the same pipeline as pages
        warnings_list = []

        # 1. Process images (size syntax and captions)
        processed = process_images(body)

        # 2. Convert markdown to HTML
        processed = markdown.markdown(
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
        output_content = f"""---
{frontmatter_text}
layout: glossary{latex_flag}
---

{processed}
"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(output_content)

        print(f"✓ Generated {filepath}")


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

        for term in demo_glossary:
            term_id = term.get('term_id', '')
            if not term_id:
                continue

            filepath = glossary_dir / f"{term_id}.md"

            # Create markdown with frontmatter
            output_content = f"""---
term_id: {term_id}
title: "{_yaml_escape(term.get('title', term_id))}"
layout: glossary
demo: true
---

{term.get('content', '')}
"""

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(output_content)

            print(f"✓ Generated {filepath} [DEMO]")

def _story_has_latex(identifier):
    """Check the story's _data JSON metadata for the has_latex flag.

    Open stories get KaTeX loading decided in-template from the same
    metadata; protected pages cannot do that once the steps ship encrypted,
    so the flag is lifted into frontmatter at generation time.
    """
    data_file = Path(f'_data/{identifier}.json')
    if not data_file.exists():
        return False
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            story_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    if isinstance(story_data, list) and story_data and story_data[0].get('_metadata'):
        return bool(story_data[0].get('has_latex'))
    return False


def generate_protected_fragments(skip=False):
    """Generate steps-only fragment pages for protected stories.

    Each protected story gets a standalone generated page (pages collection,
    reserved permalink prefix /telar-protected-fragments/) whose layout
    renders nothing but the story steps through the same include as open
    stories. The post-build encryption step (encrypt_protected_stories.py)
    reads the rendered fragment from _site, encrypts it into the story's
    envelope, and deletes it — the fragment never deploys.

    Not a collection of its own: that would add _config.yml surface. The
    pages written here are cleaned up by glob on every run, so a story that
    stops being protected leaves no orphan behind.
    """
    pages_dir = Path('_jekyll-files/_pages')
    pages_dir.mkdir(parents=True, exist_ok=True)

    # Clean previous fragment pages first, and unconditionally. A fragment
    # renders the steps as plaintext for the encryption step to consume; one
    # left from a run when a story was protected would otherwise render again
    # with nothing to remove it. generate_pages() only clears this directory
    # when telar-content/texts/pages exists, so this cleanup is our own and
    # must happen before any early return below.
    for stale in pages_dir.glob('telar-fragment-*.md'):
        stale.unlink()

    project_path = Path('_data/project.json')
    if skip or not project_path.exists():
        return

    with open(project_path, 'r', encoding='utf-8') as f:
        project_data = json.load(f)

    stories = []
    if project_data and len(project_data) > 0:
        stories = project_data[0].get('stories', [])

    for story in stories:
        if not story.get('protected'):
            continue
        identifier = _story_identifier(story)
        if not Path(f'_data/{identifier}.json').exists():
            continue

        frontmatter = yaml.safe_dump(
            {
                'layout': 'story-fragment',
                'data_file': identifier,
                'permalink': f'/telar-protected-fragments/{identifier}/',
            },
            default_flow_style=False, allow_unicode=True, sort_keys=False,
        )
        filepath = pages_dir / f'telar-fragment-{identifier}.md'
        with open(filepath, 'w') as f:
            f.write(f"---\n{frontmatter}---\n\n")
        print(f"✓ Generated {filepath} (protected fragment)")


def _story_identifier(story):
    """The name a story's data file, document and URL are all built from."""
    story_id = story.get('story_id', '')  # Optional semantic ID (v0.6.0+)
    # With story_id: "your-story" → files are "your-story.json", "your-story.md"
    # Without story_id: number=1 → files are "story-1.json", "story-1.md"
    return story_id if story_id else f"story-{story.get('number', '')}"


def _publishable_stories(stories):
    """The stories that become documents, paired with their identifier.

    A record with no number or title is not a story, and one whose data
    file is missing has nothing to render — neither reaches Jekyll, so
    neither belongs in the manifest either.
    """
    out = []
    for story in stories:
        if not story.get('number', '') or not story.get('title', ''):
            continue
        identifier = _story_identifier(story)
        if not Path(f'_data/{identifier}.json').exists():
            print(f"Warning: No data file found for {identifier}.json")
            continue
        out.append((identifier, story))
    return out


def generate_stories(config=None):
    """Generate story markdown files based on project.json stories list

    Reads from _data/project.json which includes both user stories and
    merged demo content (when include_demo_content is enabled).

    Each document declares the permalink it renders at, and the same
    mapping is written to the story page manifest. Ambiguity — two records
    deriving one identifier, or two identifiers rendering at one URL — is
    refused before any file is written, so a build that would silently drop
    a story fails instead.
    """

    # Read from project.json (has merged user + demo stories)
    project_path = Path('_data/project.json')
    if not project_path.exists():
        print("Warning: _data/project.json not found")
        # An inventory from an earlier run would describe pages this build
        # cannot vouch for, and the encryption step reads it as authoritative.
        remove_manifest('_data')
        return

    with open(project_path, 'r', encoding='utf-8') as f:
        project_data = json.load(f)

    # Get stories from first project entry
    stories = []
    if project_data and len(project_data) > 0:
        stories = project_data[0].get('stories', [])

    stories_dir = Path('_jekyll-files/_stories')
    publishable = _publishable_stories(stories)
    permalink = stories_permalink(config)

    # Built before anything is written: an ambiguous site must not leave a
    # half-generated collection behind.
    manifest = build_manifest(
        ((identifier, stories_dir / f'{identifier}.md')
         for identifier, _ in publishable),
        permalink,
    )

    # Clean up old files to remove orphaned stories
    if stories_dir.exists():
        shutil.rmtree(stories_dir)
        print(f"✓ Cleaned up old story files")

    stories_dir.mkdir(parents=True, exist_ok=True)

    # Track sort order: demos get 0-999, user stories get 1000+
    demo_index = 0
    user_index = 1000

    for identifier, story in publishable:
        story_title = story.get('title', '')
        story_subtitle = story.get('subtitle', '')
        is_demo = story.get('_demo', False)

        # Assign sort order
        if is_demo:
            sort_order = demo_index
            demo_index += 1
        else:
            sort_order = user_index
            user_index += 1

        # Use identifier for filename (no additional prefix)
        filepath = stories_dir / f"{identifier}.md"
        story_url = manifest['stories'][identifier].get('url')

        # Build frontmatter as a dict and serialise via yaml.safe_dump so that
        # quotes, colons, or newlines in author-supplied title/subtitle/byline
        # cannot break out of their YAML fields. sort_keys=False keeps the
        # human-friendly field order.
        story_byline = story.get('byline', '')
        frontmatter_dict = {'title': story_title}
        if story_subtitle:
            frontmatter_dict['subtitle'] = story_subtitle
        if story_byline:
            frontmatter_dict['byline'] = story_byline
        if is_demo:
            frontmatter_dict['demo'] = True
        if story.get('show_sections'):
            frontmatter_dict['show_sections'] = True
        if story.get('protected'):
            # The _data JSON is plaintext through the build (encryption
            # happens post-build), so templates must key protected
            # behaviour on this flag, never on the data file's shape.
            frontmatter_dict['protected'] = True
            if _story_has_latex(identifier):
                frontmatter_dict['has_latex'] = True
        frontmatter_dict['sort_order'] = sort_order
        frontmatter_dict['layout'] = 'story'
        frontmatter_dict['data_file'] = identifier
        if story_url:
            # Declared, not derived: the collection template would produce
            # this same URL by slugifying the basename, but nothing would
            # record which identifier landed where.
            frontmatter_dict['permalink'] = story_url

        frontmatter_body = yaml.safe_dump(
            frontmatter_dict, default_flow_style=False, allow_unicode=True, sort_keys=False
        )
        content = f"---\n{frontmatter_body}---\n\n"

        with open(filepath, 'w') as f:
            f.write(content)

        demo_label = " [DEMO]" if is_demo else ""
        print(f"✓ Generated {filepath}{demo_label}")

    written = write_manifest('_data', manifest)
    print(f"✓ Generated {written} ({len(manifest['stories'])} story pages)")


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
    except yaml.YAMLError as e:
        print(f"❌ Error: Invalid YAML frontmatter in {source_file}: {e}")
        return None

    return frontmatter_text, frontmatter_dict, body


def generate_pages(telar_language='en'):
    """Generate processed page files from user markdown sources.

    Reads from telar-content/texts/pages/*.md, processes widgets and glossary links,
    and outputs to _jekyll-files/_pages/ for the pages collection.

    Localization: a sister file with frontmatter `localized_for: <canonical>.md`
    and `language: <code>` is treated as the localized version of <canonical>.md.
    When `telar_language` matches the sister's `language`, the sister is used
    in place of the canonical file but is output under the canonical filename
    (so the URL is the same in both languages). Sister files for other
    languages are skipped.
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
        processed = markdown.markdown(
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
{frontmatter_text}
---

{processed}
"""

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output_content)

        print(f"✓ Generated {output_file}")


def load_config():
    """Load _config.yml and return the full config dict (empty dict if missing)."""
    config_path = Path('_config.yml')
    if not config_path.exists():
        return {}

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def main():
    """Generate all collection files"""
    parser = argparse.ArgumentParser(
        description='Generate Jekyll collection files from Telar JSON data'
    )
    parser.add_argument(
        '--skip-objects',
        action='store_true',
        help='Skip object collection generation'
    )
    parser.add_argument(
        '--skip-stories',
        action='store_true',
        help='Skip story collection generation'
    )
    cli_args = parser.parse_args()

    print("Generating Jekyll collection files...")
    print("-" * 50)

    # Load site config; extract development feature flags and active language
    config = load_config()
    dev_features = config.get('development-features', {}) or {}
    telar_language = config.get('telar_language', 'en') or 'en'

    # Support both old names (hide_*) and new names (skip_*), new takes precedence
    # CLI flags also apply (union of CLI and config flags)
    skip_stories = (
        cli_args.skip_stories
        or dev_features.get('skip_stories', dev_features.get('hide_stories', False))
    )
    skip_collections = dev_features.get('skip_collections', dev_features.get('hide_collections', False))

    # skip_collections implies skip_stories
    if skip_collections:
        skip_stories = True

    # --skip-objects CLI flag (independent of skip_collections)
    skip_objects_flag = cli_args.skip_objects

    # Generate objects (skip if skip_collections or --skip-objects)
    if skip_collections:
        print("Skipping objects (skip_collections enabled)")
        objects_dir = Path('_jekyll-files/_objects')
        if objects_dir.exists():
            shutil.rmtree(objects_dir)
            print("✓ Cleaned up object files")
    elif skip_objects_flag:
        print("Skipping objects (--skip-objects)")
    else:
        generate_objects()
    print()

    # Always generate glossary
    generate_glossary()
    print()

    # Generate stories (skip and clean up if skip_stories or skip_collections)
    if skip_stories:
        print("Skipping stories (skip_stories enabled)" if not skip_collections else "Skipping stories (skip_collections enabled)")
        stories_dir = Path('_jekyll-files/_stories')
        if stories_dir.exists():
            shutil.rmtree(stories_dir)
            print("✓ Cleaned up story files")
        # A manifest left from an earlier run would describe pages this
        # build does not produce.
        remove_manifest('_data')
    else:
        generate_stories(config)
    print()

    # Always generate pages (passes active language so localized sister files
    # like acerca.md/about.md can be selected at build time)
    generate_pages(telar_language=telar_language)

    # After generate_pages: it may clean _jekyll-files/_pages/, where the
    # fragment pages live
    # Always called: even when stories are skipped, a fragment page left
    # from an earlier run must be cleared, or it renders plaintext steps that
    # nothing will encrypt. The function returns after that cleanup when
    # there is nothing to generate.
    generate_protected_fragments(skip=skip_stories)

    print("-" * 50)
    print("Generation complete!")


if __name__ == '__main__':
    try:
        main()
    except ManifestError as error:
        print(f"\n❌ This site cannot be generated as described:\n  {error}")
        raise SystemExit(1)
