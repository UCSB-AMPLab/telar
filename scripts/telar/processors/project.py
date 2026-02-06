"""
Project Setup Processor

This module deals with converting the project CSV into the JSON structure
that tells Telar which stories exist and in what order they appear. The
project spreadsheet is the simplest of the three CSVs — each row defines
one story with an order number, a title, and optional fields for subtitle,
byline, story ID, and protected status.

`process_project_setup()` iterates over the DataFrame rows and builds a
list of story entries. It skips rows with empty order numbers (placeholder
rows that authors sometimes leave in the spreadsheet). For each valid row,
it constructs a dictionary with `number`, `title`, and any optional fields
that are present.

The story_id field (added in v0.6.0) lets authors assign semantic
identifiers like "your-story" or "tutorial" instead of relying on order
numbers. The function validates that story IDs contain only lowercase
letters, numbers, hyphens, and underscores, and flags duplicates. If no
story_id is provided, the system falls back to the order number.

The protected field (added in v0.8.0) marks stories for client-side
encryption. Stories with protected=yes will have their content encrypted
at build time, requiring a key to view.

The function returns a pandas DataFrame wrapping a single dictionary with
a `stories` key, which `csv_to_json()` in the core module serialises to
`_data/project.json`.

Version: v0.8.0-beta
"""

import re
import pandas as pd


def process_project_setup(df):
    """
    Process project setup CSV.

    Expected columns: order, title, subtitle (optional), byline (optional),
    story_id (optional), protected (optional)

    Args:
        df: pandas DataFrame from project CSV

    Returns:
        pandas DataFrame with single row containing {'stories': [...]}
    """
    stories_list = []
    seen_ids = set()  # Track duplicate story_ids

    for _, row in df.iterrows():
        order = str(row.get('order', '')).strip()
        title = row.get('title', '')
        subtitle = row.get('subtitle', '')
        byline = row.get('byline', '')
        protected = row.get('protected', '')

        # Check if story_id column exists and extract value (v0.6.0+)
        story_id = ''
        if 'story_id' in df.columns:
            story_id_raw = row.get('story_id', '')
            if pd.notna(story_id_raw):
                story_id = str(story_id_raw).strip()

        # Skip rows with empty order (placeholder rows)
        if not order or not pd.notna(title):
            continue

        # Validate story_id if provided
        if story_id:
            # Check for invalid characters (must be lowercase, numbers, hyphens, underscores)
            if not re.match(r'^[a-z0-9\-_]+$', story_id):
                print(f"  Warning: story_id '{story_id}' contains invalid characters. Use lowercase letters, numbers, hyphens, underscores only.")

            # Check for duplicates
            if story_id in seen_ids:
                print(f"  Warning: Duplicate story_id '{story_id}' found in project.csv")
            seen_ids.add(story_id)

        story_entry = {
            'number': order,
            'title': title
        }

        # Add story_id to JSON only if it exists and is non-empty
        if story_id:
            story_entry['story_id'] = story_id

        # Add subtitle if present
        if pd.notna(subtitle) and str(subtitle).strip():
            story_entry['subtitle'] = str(subtitle).strip()

        # Add byline if present
        if pd.notna(byline) and str(byline).strip():
            story_entry['byline'] = str(byline).strip()

        # Add protected flag if set to yes/true/sí/si (v0.8.0+)
        if pd.notna(protected) and str(protected).strip().lower() in ('yes', 'true', 'sí', 'si'):
            story_entry['protected'] = True

        stories_list.append(story_entry)

    # Return stories list structure
    result = {'stories': stories_list}
    return pd.DataFrame([result])
