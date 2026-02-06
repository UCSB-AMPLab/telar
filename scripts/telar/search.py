"""
Search Data Generator

This module deals with preparing object metadata for client-side search and
filtering. It reads `_data/objects.json` and produces `_data/search-data.json`
— a slimmed-down dataset optimised for the gallery's browse-and-search
interface.

The main entry point is `generate_search_data()`, which extracts the fields
needed for Lunr.js text search (title, creator, period, subjects, description,
object_type) and builds facet counts for the filter sidebar. Facets are
pre-computed here — rather than in the browser — so the filter UI can show
"Maps (3)" or "Unknown (5)" without scanning all objects on every page load.

`build_facets()` handles the counting logic. For most fields it's a simple
tally, but `subjects` requires special handling because it's pipe-separated
(e.g., "colonial|weaving|fragment") — each tag is counted individually.
Facets are sorted by count descending, then alphabetically, so the most
common values appear first in the filter UI.

The search index itself is built client-side by Lunr.js rather than
pre-serialised in Python. This keeps the build simple — no additional
dependencies — and works well for typical collection sizes (well under 500
objects). The trade-off is a brief index-building pause on first page load,
but for most sites this is imperceptible (<100ms).

`is_browse_and_search_enabled()` checks the `collection_interface.browse_and_search`
config setting. When disabled, no search data is generated and any existing
`search-data.json` is removed — the gallery falls back to its simple grid view.

Version: v0.8.0-beta
"""

import json
from pathlib import Path

import yaml


def load_config():
    """Load _config.yml and return relevant settings."""
    config_path = Path('_config.yml')
    if not config_path.exists():
        return {}

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def is_browse_and_search_enabled(config):
    """Check if browse_and_search is enabled in config."""
    collection_interface = config.get('collection_interface', {})
    # Default to True if not specified
    return collection_interface.get('browse_and_search', True)


def build_facets(objects):
    """
    Build facet counts from objects data.

    Returns dict with counts per category:
    {
        "object_type": {"Map": 3, "Document": 2},
        "creator": {"Unknown": 5, "Smith": 2},
        "subjects": {"colonial": 4, "cartography": 2},
        "period": {"18th century": 3, "1650-1700": 2}
    }
    """
    facets = {
        'object_type': {},
        'creator': {},
        'subjects': {},
        'period': {}
    }

    for obj in objects:
        # Object type
        obj_type = str(obj.get('object_type', '')).strip()
        if obj_type:
            facets['object_type'][obj_type] = facets['object_type'].get(obj_type, 0) + 1

        # Creator
        creator = str(obj.get('creator', '')).strip()
        if creator:
            facets['creator'][creator] = facets['creator'].get(creator, 0) + 1

        # Subjects (pipe-separated)
        subjects_str = str(obj.get('subjects', '')).strip()
        if subjects_str:
            for subject in subjects_str.split('|'):
                subject = subject.strip()
                if subject:
                    facets['subjects'][subject] = facets['subjects'].get(subject, 0) + 1

        # Period
        period = str(obj.get('period', '')).strip()
        if period:
            facets['period'][period] = facets['period'].get(period, 0) + 1

    # Sort facets by count (descending), then alphabetically
    for category in facets:
        sorted_items = sorted(
            facets[category].items(),
            key=lambda x: (-x[1], x[0].lower())
        )
        facets[category] = dict(sorted_items)

    return facets


def generate_search_data(objects_path='_data/objects.json', output_path='search-data.json'):
    """
    Generate search data file from objects.json.

    Args:
        objects_path: Path to objects.json
        output_path: Path for output search-data.json

    Returns:
        bool: True if generated, False if skipped (config disabled or no objects)
    """
    # Check config
    config = load_config()
    if not is_browse_and_search_enabled(config):
        print("  [INFO] browse_and_search disabled, skipping search index generation")
        # Clean up existing file if present
        output = Path(output_path)
        if output.exists():
            output.unlink()
            print("  [INFO] Removed existing search-data.json")
        return False

    # Load objects
    objects_file = Path(objects_path)
    if not objects_file.exists():
        print(f"  [WARN] Objects file not found: {objects_path}")
        return False

    with open(objects_file, 'r', encoding='utf-8') as f:
        objects = json.load(f)

    if not objects:
        print("  [INFO] No objects found, skipping search index generation")
        return False

    # Build search data
    # Include fields needed for indexing and display
    search_objects = []
    for obj in objects:
        search_obj = {
            'id': obj.get('object_id', ''),
            'title': obj.get('title', ''),
            'creator': obj.get('creator', ''),
            'period': obj.get('period', ''),
            'description': obj.get('description', ''),
            'object_type': obj.get('object_type', ''),
            'subjects': obj.get('subjects', ''),
            'year': obj.get('year', ''),
            # Include for display in results
            'thumbnail': obj.get('thumbnail', ''),
            'source_url': obj.get('source_url', ''),
            'demo': obj.get('demo', False)
        }
        search_objects.append(search_obj)

    # Build facets
    facets = build_facets(objects)

    # Assemble output
    search_data = {
        'objects': search_objects,
        'facets': facets,
        'total': len(search_objects)
    }

    # Write output
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, 'w', encoding='utf-8') as f:
        json.dump(search_data, f, ensure_ascii=False, indent=2)

    print(f"  [INFO] Generated search data: {len(search_objects)} objects, {sum(len(v) for v in facets.values())} facet values")

    return True


if __name__ == '__main__':
    print("Generating search data...")
    if generate_search_data():
        print("✓ Search data generated successfully")
    else:
        print("  Search data generation skipped")
