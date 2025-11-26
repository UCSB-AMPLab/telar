#!/usr/bin/env python3
"""
Generate Jekyll collection markdown files from JSON data

Version: v0.5.0-beta
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

def generate_glossary():
    """Generate glossary markdown files from user content and demo JSON.

    Reads from:
    - components/texts/glossary/*.md (user content)
    - _data/demo-glossary.json (demo content from bundle)
    """
    import re

    glossary_dir = Path('_jekyll-files/_glossary')

    # Clean up old files to remove orphaned glossary terms
    if glossary_dir.exists():
        shutil.rmtree(glossary_dir)
        print(f"✓ Cleaned up old glossary files")

    glossary_dir.mkdir(parents=True, exist_ok=True)

    # 1. Process user glossary from markdown files
    source_dir = Path('components/texts/glossary')
    if source_dir.exists():
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
        is_demo = story.get('_demo', False)

        # Skip entries without number or title
        if not story_num or not story_title:
            continue

        # Check if story data file exists
        data_file = Path(f'_data/story-{story_num}.json')
        if not data_file.exists():
            print(f"Warning: No data file found for Story {story_num}")
            continue

        # Assign sort order
        if is_demo:
            sort_order = demo_index
            demo_index += 1
        else:
            sort_order = user_index
            user_index += 1

        filepath = stories_dir / f"story-{story_num}.md"

        # Build frontmatter
        frontmatter = f"""---
story_number: "{story_num}"
title: "{story_title}"
"""
        if story_subtitle:
            frontmatter += f'subtitle: "{story_subtitle}"\n'

        if is_demo:
            frontmatter += f'demo: true\n'

        frontmatter += f'sort_order: {sort_order}\n'

        frontmatter += f"""layout: story
data_file: story-{story_num}
---

"""

        content = frontmatter

        with open(filepath, 'w') as f:
            f.write(content)

        demo_label = " [DEMO]" if is_demo else ""
        print(f"✓ Generated {filepath}{demo_label}")

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
