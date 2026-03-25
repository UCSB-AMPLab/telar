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
  JSON data file and setting the story layout.
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

Version: v1.0.0-beta
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

# Fields already handled explicitly in generate_objects() frontmatter.
# Any key NOT in this set is treated as a custom field and written to extra_metadata.
KNOWN_OBJECT_FIELDS = {
    'object_id', 'title', 'creator', 'period', 'medium', 'dimensions',
    'location', 'credit', 'thumbnail', 'iiif_manifest', 'source_url',
    'source', 'object_warning', 'object_warning_short', 'year',
    'object_type', 'subjects', 'is_featured_sample', '_demo',
    'description', 'featured',
    # v0.10.0: auto-detected media type and audio metadata
    'media_type', 'audio_duration', 'audio_filesize', 'audio_format',
}


# Video URL patterns for media type auto-detection
_VIDEO_URL_PATTERNS = ['youtube.com', 'youtu.be', 'vimeo.com', 'drive.google.com']

# Audio file extensions supported (must match audio-card.js in card runtime)
_AUDIO_EXTENSIONS = ['.mp3', '.ogg', '.m4a', '.MP3', '.OGG', '.M4A']


def detect_media_type(source_url, object_id):
    """Auto-detect media type for gallery Type filter.

    Checks source URL for known video hosts first, then looks for an audio
    file matching the object_id in telar-content/objects/. Defaults to 'Image'.

    Args:
        source_url: The object's source_url field (may be None or empty).
        object_id:  The object's ID, used to find matching audio files on disk.

    Returns:
        str: 'Video', 'Audio', or 'Image'.
    """
    url = (source_url or '').strip()

    # Check for video URL patterns first
    if any(pat in url for pat in _VIDEO_URL_PATTERNS):
        return 'Video'

    # Check for audio file in objects content directory
    objects_content_dir = Path('telar-content/objects')
    if objects_content_dir.exists():
        for ext in _AUDIO_EXTENSIONS:
            if (objects_content_dir / f'{object_id}{ext}').exists():
                return 'Audio'

    return 'Image'


def _yaml_escape(value):
    """Escape a string value for safe inclusion in double-quoted YAML."""
    s = str(value)
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    return s


def generate_objects():
    """Generate object markdown files from objects.json"""
    if not Path('_data/objects.json').exists():
        print("No objects.json found — skipping object generation")
        return

    with open('_data/objects.json', 'r') as f:
        objects = json.load(f)

    objects_dir = Path('_jekyll-files/_objects')

    # Clean up old files to remove orphaned objects
    if objects_dir.exists():
        shutil.rmtree(objects_dir)
        print(f"✓ Cleaned up old object files")

    objects_dir.mkdir(parents=True, exist_ok=True)

    for obj in objects:
        object_id = obj.get('object_id', '')
        if not object_id:
            continue

        is_demo = obj.get('_demo', False)

        # Generate main object page
        filepath = objects_dir / f"{object_id}.md"

        # Build front matter, omitting empty fields so Liquid {% if %}
        # conditionals work correctly (empty strings are truthy in Liquid)
        content = f'---\nobject_id: {object_id}\n'
        content += f'title: "{_yaml_escape(obj.get("title", ""))}"\n'

        # Resolve medium: prefer 'medium' field; fall back to 'object_type' for backward compat
        # (v0.10.0: object_type is renamed to medium in CSV; old sites may still have object_type in JSON)
        medium_value = obj.get('medium', '') or obj.get('object_type', '')

        # Auto-detect media type for gallery Type filter
        source_url = obj.get('source_url', '') or ''
        media_type = detect_media_type(source_url, object_id)

        # Metadata fields — only include if non-empty
        metadata_fields = {
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
        for key, value in metadata_fields.items():
            if value:
                content += f'{key}: "{_yaml_escape(str(value))}"\n'

        # Media type (always written — required for type-conditional template rendering)
        content += f'media_type: "{media_type}"\n'

        # Additional optional fields
        if obj.get('year'):
            content += f'year: "{obj.get("year")}"\n'
        # Note: object_type key is no longer written to frontmatter (v0.10.0 rename to medium above)
        if obj.get('subjects'):
            content += f'subjects: "{obj.get("subjects")}"\n'
        if obj.get('is_featured_sample'):
            content += "is_featured_sample: true\n"

        if is_demo:
            content += "demo: true\n"

        # Audio metadata: duration and file size from disk (v0.10.0)
        if media_type == 'Audio':
            # Duration from peaks JSON (generated by process_audio.py)
            peaks_path = Path(f'assets/audio/peaks/{object_id}.json')
            if peaks_path.exists():
                try:
                    with open(peaks_path, 'r') as pf:
                        peaks_data = json.load(pf)
                    duration = peaks_data.get('duration', 0)
                    if duration:
                        content += f'audio_duration: {duration}\n'
                except (json.JSONDecodeError, KeyError):
                    pass

            # File size and format from disk
            for ext in _AUDIO_EXTENSIONS:
                audio_path = Path(f'telar-content/objects/{object_id}{ext}')
                if audio_path.exists():
                    size_bytes = audio_path.stat().st_size
                    if size_bytes < 1024 * 1024:
                        size_str = f'{size_bytes / 1024:.0f} KB'
                    else:
                        size_str = f'{size_bytes / (1024 * 1024):.1f} MB'
                    content += f'audio_filesize: "{size_str}"\n'
                    content += f'audio_format: "{ext.lstrip(".").upper()}"\n'
                    break

        # Collect custom fields not in the known set
        extra = {}
        for key, value in obj.items():
            if key in KNOWN_OBJECT_FIELDS:
                continue
            if value is None or (isinstance(value, float) and str(value) == 'nan'):
                continue
            s = str(value).strip()
            if s and s.lower() != 'nan':
                extra[key] = s

        if extra:
            content += "extra_metadata:\n"
            for key, value in extra.items():
                content += f'  {key}: "{_yaml_escape(value)}"\n'

        # Check description for LaTeX content
        description = obj.get('description', '')
        if description and has_latex(description):
            content += "has_latex: true\n"

        content += f"""layout: object
---

{description}
"""

        with open(filepath, 'w') as f:
            f.write(content)

        demo_label = " [DEMO]" if is_demo else ""
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
title: "{title}"{related_str}{latex_flag}
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
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(frontmatter_pattern, content, re.DOTALL)

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
title: "{term.get('title', term_id)}"
layout: glossary
demo: true
---

{term.get('content', '')}
"""

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(output_content)

            print(f"✓ Generated {filepath} [DEMO]")

def generate_stories():
    """Generate story markdown files based on project.json stories list

    Reads from _data/project.json which includes both user stories and
    merged demo content (when include_demo_content is enabled).
    """

    # Read from project.json (has merged user + demo stories)
    project_path = Path('_data/project.json')
    if not project_path.exists():
        print("Warning: _data/project.json not found")
        return

    with open(project_path, 'r', encoding='utf-8') as f:
        project_data = json.load(f)

    # Get stories from first project entry
    stories = []
    if project_data and len(project_data) > 0:
        stories = project_data[0].get('stories', [])

    stories_dir = Path('_jekyll-files/_stories')

    # Clean up old files to remove orphaned stories
    if stories_dir.exists():
        shutil.rmtree(stories_dir)
        print(f"✓ Cleaned up old story files")

    stories_dir.mkdir(parents=True, exist_ok=True)

    # Track sort order: demos get 0-999, user stories get 1000+
    demo_index = 0
    user_index = 1000

    for story in stories:
        story_num = story.get('number', '')
        story_title = story.get('title', '')
        story_subtitle = story.get('subtitle', '')
        story_id = story.get('story_id', '')  # Optional semantic ID (v0.6.0+)
        is_demo = story.get('_demo', False)

        # Skip entries without number or title
        if not story_num or not story_title:
            continue

        # Use story_id as-is, or construct story-{order} for fallback
        # With story_id: "your-story" → files are "your-story.json", "your-story.md"
        # Without story_id: order=1 → files are "story-1.json", "story-1.md"
        if story_id:
            identifier = story_id  # No prefix: "your-story"
        else:
            identifier = f'story-{story_num}'  # With prefix: "story-1"

        # Check if story data file exists
        data_file = Path(f'_data/{identifier}.json')
        if not data_file.exists():
            print(f"Warning: No data file found for {identifier}.json")
            continue

        # Assign sort order
        if is_demo:
            sort_order = demo_index
            demo_index += 1
        else:
            sort_order = user_index
            user_index += 1

        # Use identifier for filename (no additional prefix)
        filepath = stories_dir / f"{identifier}.md"

        # Build frontmatter (story_number remains numeric for display)
        frontmatter = f"""---
story_number: "{story_num}"
title: "{story_title}"
"""
        if story_subtitle:
            frontmatter += f'subtitle: "{story_subtitle}"\n'

        story_byline = story.get('byline', '')
        if story_byline:
            frontmatter += f'byline: "{story_byline}"\n'

        if is_demo:
            frontmatter += f'demo: true\n'

        frontmatter += f'sort_order: {sort_order}\n'

        frontmatter += f"""layout: story
data_file: {identifier}
---

"""

        content = frontmatter

        with open(filepath, 'w') as f:
            f.write(content)

        demo_label = " [DEMO]" if is_demo else ""
        print(f"✓ Generated {filepath}{demo_label}")

def generate_pages():
    """Generate processed page files from user markdown sources.

    Reads from telar-content/texts/pages/*.md, processes widgets and glossary links,
    and outputs to _jekyll-files/_pages/ for the pages collection.
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

    # Process each markdown file
    for source_file in source_dir.glob('*.md'):
        filename = source_file.name

        with open(source_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse frontmatter and body
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(frontmatter_pattern, content, re.DOTALL)

        if not match:
            print(f"❌ Error: No frontmatter found in {source_file}")
            print("  Pages must have YAML frontmatter (--- at start and end)")
            continue

        frontmatter_text = match.group(1)
        body = match.group(2).strip()

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

        # Write processed file to output directory
        output_file = output_dir / filename

        output_content = f"""---
{frontmatter_text}
---

{processed}
"""

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output_content)

        print(f"✓ Generated {output_file}")


def load_config():
    """Load _config.yml and return development-features settings"""
    config_path = Path('_config.yml')
    if not config_path.exists():
        return {}

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config.get('development-features', {})


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

    # Load development feature flags
    dev_features = load_config()

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
    else:
        generate_stories()
    print()

    # Always generate pages
    generate_pages()

    print("-" * 50)
    print("Generation complete!")

if __name__ == '__main__':
    main()
