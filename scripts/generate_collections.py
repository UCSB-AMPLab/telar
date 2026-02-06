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
  files (components/texts/glossary/) and demo content, with glossary-
  to-glossary link processing.
- Pages (_jekyll-files/_pages/): User-authored pages from
  components/texts/pages/, processed through the widget and glossary
  pipeline.

The script respects development feature flags (skip_stories,
skip_collections) from _config.yml, which allow developers to
temporarily suppress certain collections during development.
Legacy names (hide_stories, hide_collections) are also supported.

Version: v0.8.0-beta
"""

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

        content = f"""---
object_id: {obj.get('object_id', '')}
title: "{obj.get('title', '')}"
creator: "{obj.get('creator', '')}"
period: "{obj.get('period', '')}"
medium: "{obj.get('medium', '')}"
dimensions: "{obj.get('dimensions', '')}"
location: "{obj.get('location', '')}"
credit: "{obj.get('credit', '')}"
thumbnail: "{obj.get('thumbnail', '')}"
iiif_manifest: "{obj.get('iiif_manifest', '')}"
object_warning: "{obj.get('object_warning', '')}"
object_warning_short: "{obj.get('object_warning_short', '')}"
"""
        # Add optional fields only if they have values
        if obj.get('year'):
            content += f'year: "{obj.get("year")}"\n'
        if obj.get('object_type'):
            content += f'object_type: "{obj.get("object_type")}"\n'
        if obj.get('subjects'):
            content += f'subjects: "{obj.get("subjects")}"\n'
        if obj.get('is_featured_sample'):
            content += "is_featured_sample: true\n"

        if is_demo:
            content += "demo: true\n"

        content += f"""layout: object
---

{obj.get('description', '')}
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

        # Build related_terms frontmatter
        related_str = ''
        if related_terms:
            related_str = f"\nrelated_terms: {','.join(related_terms)}"

        # Write Jekyll file
        filepath = glossary_dir / f"{term_id}.md"
        output_content = f"""---
term_id: {term_id}
title: "{title}"{related_str}
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
        md_path: Path to components/texts/glossary/
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

        # Write to collection with layout added
        output_content = f"""---
{frontmatter_text}
layout: glossary
---

{processed}
"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(output_content)

        print(f"✓ Generated {filepath}")


def generate_glossary():
    """Generate glossary markdown files from user content and demo JSON.

    Reads from (in order of precedence):
    - components/structures/glossary.csv (v0.8.0+ preferred)
    - components/texts/glossary/*.md (legacy markdown files)
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

    csv_path = Path('components/structures/glossary.csv')
    md_path = Path('components/texts/glossary')

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

    Reads from components/texts/pages/*.md, processes widgets and glossary links,
    and outputs to _jekyll-files/_pages/ for the pages collection.
    """
    source_dir = Path('components/texts/pages')
    output_dir = Path('_jekyll-files/_pages')

    # Skip if source directory doesn't exist
    if not source_dir.exists():
        print("No components/texts/pages/ directory found - skipping page generation")
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
    print("Generating Jekyll collection files...")
    print("-" * 50)

    # Load development feature flags
    dev_features = load_config()

    # Support both old names (hide_*) and new names (skip_*), new takes precedence
    skip_stories = dev_features.get('skip_stories', dev_features.get('hide_stories', False))
    skip_collections = dev_features.get('skip_collections', dev_features.get('hide_collections', False))

    # skip_collections implies skip_stories
    if skip_collections:
        skip_stories = True

    # Generate objects (skip and clean up if skip_collections)
    if skip_collections:
        print("Skipping objects (skip_collections enabled)")
        objects_dir = Path('_jekyll-files/_objects')
        if objects_dir.exists():
            shutil.rmtree(objects_dir)
            print("✓ Cleaned up object files")
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
