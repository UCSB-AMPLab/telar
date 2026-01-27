"""
Telar Data Processing Package

Modular package for processing Telar story data from CSV/Google Sheets
into JSON format for the Jekyll-based storytelling framework.

Version: v0.7.0-beta
"""

# Public API re-exports
from telar.config import load_language_data, get_lang_string, load_site_language
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
    get_widget_id, parse_key_value_block, parse_carousel_widget,
    parse_markdown_sections, parse_tabs_widget, parse_accordion_widget,
    render_widget_html, process_widgets
)
from telar.markdown import read_markdown_file, process_inline_content
from telar.processors.project import process_project_setup
from telar.processors.objects import (
    process_objects, inject_christmas_tree_errors
)
from telar.processors.stories import process_story
from telar.demo import (
    load_demo_bundle, merge_demo_content, fetch_demo_content_if_enabled
)
from telar.core import csv_to_json, find_csv_with_fallback, main
