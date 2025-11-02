#!/usr/bin/env python3
"""
Generate Jekyll collection markdown files from JSON data
"""

import json
import shutil
from pathlib import Path

def generate_objects():
    """Generate object markdown files from objects.json"""
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

        # Generate main object page
        filepath = objects_dir / f"{object_id}.md"

        # Escape quotes in warning fields for YAML
        object_warning = str(obj.get('object_warning', '')).replace('"', '\\"')
        object_warning_short = str(obj.get('object_warning_short', '')).replace('"', '\\"')

        content = f"""---
object_id: "{obj.get('object_id', '')}"
title: "{obj.get('title', '')}"
creator: "{obj.get('creator', '')}"
period: "{obj.get('period', '')}"
medium: "{obj.get('medium', '')}"
dimensions: "{obj.get('dimensions', '')}"
location: "{obj.get('location', '')}"
credit: "{obj.get('credit', '')}"
thumbnail: "{obj.get('thumbnail', '')}"
iiif_manifest: "{obj.get('iiif_manifest', '')}"
object_warning: "{object_warning}"
object_warning_short: "{object_warning_short}"
layout: object
---

{obj.get('description', '')}
"""

        with open(filepath, 'w') as f:
            f.write(content)

        print(f"✓ Generated {filepath}")

def generate_glossary():
    """Generate glossary markdown files from components/texts/glossary/"""
    import re

    source_dir = Path('components/texts/glossary')
    if not source_dir.exists():
        print("Warning: components/texts/glossary/ directory not found")
        return

    glossary_dir = Path('_jekyll-files/_glossary')

    # Clean up old files to remove orphaned glossary terms
    if glossary_dir.exists():
        shutil.rmtree(glossary_dir)
        print(f"✓ Cleaned up old glossary files")

    glossary_dir.mkdir(parents=True, exist_ok=True)

    for source_file in source_dir.glob('*.md'):
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

        # Write to collection with layout added
        output_content = f"""---
{frontmatter_text}
layout: glossary
---

{body}
"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(output_content)

        print(f"✓ Generated {filepath}")

def generate_stories():
    """Generate story markdown files based on project.csv stories list"""

    import csv

    # Parse project.csv to get stories (now with order, title, subtitle columns)
    stories = []
    with open('components/structures/project.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            order = row.get('order', '').strip() if row.get('order') else ''
            title = row.get('title', '').strip() if row.get('title') else ''
            subtitle = row.get('subtitle', '').strip() if row.get('subtitle') else ''

            # Skip rows with empty order or title
            if not order or not title:
                continue

            story_entry = {
                'number': order,
                'title': title
            }

            # Add subtitle if present
            if subtitle:
                story_entry['subtitle'] = subtitle

            stories.append(story_entry)

    stories_dir = Path('_jekyll-files/_stories')

    # Clean up old files to remove orphaned stories
    if stories_dir.exists():
        shutil.rmtree(stories_dir)
        print(f"✓ Cleaned up old story files")

    stories_dir.mkdir(parents=True, exist_ok=True)

    for story in stories:
        story_num = story['number']
        story_title = story['title']
        story_subtitle = story.get('subtitle', '')

        # Check if story data file exists
        data_file = Path(f'_data/story-{story_num}.json')
        if not data_file.exists():
            print(f"Warning: No data file found for Story {story_num}")
            continue

        filepath = stories_dir / f"story-{story_num}.md"

        # Build frontmatter
        frontmatter = f"""---
story_number: {story_num}
title: "{story_title}"
"""
        if story_subtitle:
            frontmatter += f'subtitle: "{story_subtitle}"\n'

        frontmatter += f"""layout: story
data_file: story-{story_num}
---

"""

        content = frontmatter

        with open(filepath, 'w') as f:
            f.write(content)

        print(f"✓ Generated {filepath}")

def main():
    """Generate all collection files"""
    print("Generating Jekyll collection files...")
    print("-" * 50)

    generate_objects()
    print()

    generate_glossary()
    print()

    generate_stories()

    print("-" * 50)
    print("Generation complete!")

if __name__ == '__main__':
    main()
