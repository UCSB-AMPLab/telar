#!/usr/bin/env python3
"""
Convert CSV files from Google Sheets to JSON for Jekyll

Thin wrapper that delegates to the telar package. All functionality
has been modularised into telar.config, telar.csv_utils, telar.images,
telar.iiif_metadata, telar.glossary, telar.widgets, telar.markdown,
telar.processors.*, telar.demo, and telar.core.

This file exists for backward compatibility: existing imports like
`from csv_to_json import process_images` continue to work, and the
script remains callable as `python3 scripts/csv_to_json.py`.

Version: v0.7.0-beta
"""

# Re-export full public API from telar package for backward compatibility
from telar.config import _lang_data, load_language_data, get_lang_string, load_site_language
from telar.csv_utils import (
    COLUMN_NAME_MAPPING, sanitize_dataframe, get_source_url,
    normalize_column_names, is_header_row
)
from telar.images import (
    process_images, resolve_path_case_insensitive,
    validate_image_path, get_image_dimensions
)
from telar.iiif_metadata import (
    detect_iiif_version, extract_language_map_value, strip_html_tags,
    clean_metadata_value, find_metadata_field, is_legal_boilerplate,
    extract_credit, extract_manifest_metadata, apply_metadata_fallback
)
from telar.glossary import load_glossary_terms, process_glossary_links
from telar.widgets import (
    _widget_counter, get_widget_id, parse_key_value_block,
    parse_carousel_widget, parse_markdown_sections, parse_tabs_widget,
    parse_accordion_widget, render_widget_html, process_widgets
)
from telar.markdown import read_markdown_file, process_inline_content
from telar.processors.project import process_project_setup
from telar.processors.objects import (
    _find_similar_image_filenames, inject_christmas_tree_errors, process_objects
)
from telar.processors.stories import process_story
from telar.demo import (
    load_demo_bundle, merge_demo_content, fetch_demo_content_if_enabled
)
from telar.core import csv_to_json, find_csv_with_fallback, main

# Re-export third-party names that tests may patch on this module
from jinja2 import Environment

if __name__ == '__main__':
    main()
