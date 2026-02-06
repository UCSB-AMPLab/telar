"""
IIIF Metadata Extraction

This module deals with extracting metadata from IIIF (International Image
Interoperability Framework) manifests. When a Telar object has a `source_url`
pointing to an external IIIF manifest, the build pipeline fetches that
manifest and extracts structured metadata — title, description, creator,
period, location, and credit — to auto-populate empty fields in the
objects CSV. This saves users from having to copy metadata by hand from
museum and library catalogues.

The module supports both IIIF Presentation API v2.0 and v3.0, which have
significantly different structures. `detect_iiif_version()` reads the
`@context` field to determine the version. The key difference is that v2.0
uses simple string values, while v3.0 wraps everything in language maps —
dictionaries like `{"en": ["A title"], "es": ["Un titulo"]}`.
`extract_language_map_value()` navigates these maps with a fallback chain:
it tries the site's configured language first, then English, then the
`none` key (unlabeled content), and finally the first available language.

Metadata fields are found by `find_metadata_field()`, which searches the
manifest's `metadata` array for entries whose `label` matches any of a
list of search terms (case-insensitive). For example, the creator field
is searched with terms like "Creator", "Artist", "Author", "Maker", etc.,
because different institutions label the same concept differently.

Credit extraction has extra logic: `extract_credit()` checks whether the
attribution text is generic legal boilerplate (detected by
`is_legal_boilerplate()`, which looks for phrases like "rights and
permissions" or URLs). If so, it falls back to the repository or
institution name from the metadata array, which is usually more useful
as a short credit line.

`apply_metadata_fallback()` implements the CSV > IIIF > empty hierarchy:
user-entered CSV values always win; IIIF values fill in only where the
CSV cell is empty.

Helper functions `strip_html_tags()` and `clean_metadata_value()` sanitize
extracted text by removing HTML markup, decoding entities, and normalizing
whitespace. Many IIIF manifests contain HTML-formatted metadata.

Version: v0.8.0-beta
"""

import re
import html
import json
import urllib.request


def detect_iiif_version(manifest):
    """
    Detect IIIF Presentation API version from @context field.

    Args:
        manifest: Parsed JSON manifest dict

    Returns:
        str: '2.0' or '3.0' (defaults to '2.0' if unclear)
    """
    context = manifest.get('@context', '')
    if isinstance(context, str):
        if 'presentation/3' in context:
            return '3.0'
        elif 'presentation/2' in context:
            return '2.0'
    elif isinstance(context, list):
        # Context can be an array in v3
        for ctx in context:
            if isinstance(ctx, str) and 'presentation/3' in ctx:
                return '3.0'

    return '2.0'  # Default to 2.0 (most common)


def extract_language_map_value(language_map, site_language='en'):
    """
    Extract value from IIIF v3.0 language map with fallback logic.

    Fallback order:
    1. Site's telar_language (e.g., 'es' for Spanish sites)
    2. English ('en')
    3. Unlabeled content ('none')
    4. First available language

    Args:
        language_map: Dict with language codes as keys, arrays as values
        site_language: Preferred language code

    Returns:
        str: Extracted value or empty string
    """
    if not isinstance(language_map, dict):
        return ''

    # Try site language
    if site_language in language_map:
        values = language_map[site_language]
        if isinstance(values, list) and len(values) > 0:
            return str(values[0])

    # Try English
    if 'en' in language_map:
        values = language_map['en']
        if isinstance(values, list) and len(values) > 0:
            return str(values[0])

    # Try unlabeled content
    if 'none' in language_map:
        values = language_map['none']
        if isinstance(values, list) and len(values) > 0:
            return str(values[0])

    # Use first available language
    for lang, values in language_map.items():
        if isinstance(values, list) and len(values) > 0:
            return str(values[0])

    return ''


def strip_html_tags(text):
    """
    Remove all HTML tags from text, preserve plain text only.
    Also decodes HTML entities and removes extra whitespace.

    Args:
        text: String that may contain HTML

    Returns:
        str: Plain text with HTML removed
    """
    if not text:
        return ''

    text = str(text)

    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Decode HTML entities
    text = html.unescape(text)

    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def clean_metadata_value(value):
    """
    Clean and normalize metadata value.
    Handles lists, strips HTML, and normalizes whitespace.

    Args:
        value: Metadata value (string, list, or dict)

    Returns:
        str: Cleaned value
    """
    if not value:
        return ''

    # Handle lists (multiple values)
    if isinstance(value, list):
        # Join multiple values with semicolon
        cleaned_values = []
        for v in value:
            cleaned = str(v).strip()
            if cleaned:
                cleaned_values.append(cleaned)
        value = '; '.join(cleaned_values)

    value = str(value).strip()
    value = strip_html_tags(value)

    return value


def find_metadata_field(metadata_array, search_terms, version='2.0', site_language='en'):
    """
    Search metadata array for matching field using fuzzy label matching.

    Args:
        metadata_array: List of {label, value} entries
        search_terms: List of possible label names (case-insensitive)
        version: '2.0' or '3.0'
        site_language: Preferred language for v3.0 extraction

    Returns:
        str: Extracted value or empty string
    """
    if not metadata_array or not isinstance(metadata_array, list):
        return ''

    for entry in metadata_array:
        if not isinstance(entry, dict):
            continue

        label = entry.get('label', '')

        # Handle v3.0 language maps
        if version == '3.0' and isinstance(label, dict):
            label = extract_language_map_value(label, site_language)

        # Case-insensitive search
        label_lower = str(label).lower().strip()

        for term in search_terms:
            if term.lower() in label_lower:
                value = entry.get('value', '')

                # Handle v3.0 language maps
                if version == '3.0' and isinstance(value, dict):
                    value = extract_language_map_value(value, site_language)

                return clean_metadata_value(value)

    return ''


def is_legal_boilerplate(text):
    """
    Detect if attribution text is generic legal boilerplate rather than actual credit.

    Args:
        text: Attribution text to check

    Returns:
        bool: True if text appears to be legal boilerplate
    """
    if not text:
        return False

    boilerplate_indicators = [
        'for information on use',
        'rights and permissions',
        'http://',
        'https://',
        'licensed under',
        'license',
        'see library',
        'please see',
        'for more information'
    ]

    text_lower = str(text).lower()

    # Check if text is mostly URL or starts with URL
    if text_lower.startswith('http'):
        return True

    # Check for multiple boilerplate indicators
    indicator_count = sum(1 for indicator in boilerplate_indicators if indicator in text_lower)

    # If text has 2+ indicators or is very long (>200 chars), likely boilerplate
    if indicator_count >= 2 or len(text) > 200:
        return True

    return False


def extract_credit(manifest, version='2.0', site_language='en'):
    """
    Extract credit/attribution with smart fallback logic.

    v2.0: Use 'attribution' field
    v3.0: Use 'requiredStatement.value' or 'provider.label'

    If attribution is legal boilerplate, fall back to repository/institution name.

    Args:
        manifest: Parsed JSON manifest dict
        version: '2.0' or '3.0'
        site_language: Preferred language

    Returns:
        str: Credit line
    """
    credit = ''

    if version == '2.0':
        credit = manifest.get('attribution', '')
    elif version == '3.0':
        # Try requiredStatement first
        req_stmt = manifest.get('requiredStatement', {})
        if req_stmt and isinstance(req_stmt, dict):
            value = req_stmt.get('value', {})
            if isinstance(value, dict):
                credit = extract_language_map_value(value, site_language)
            else:
                credit = str(value)

        # Try provider as fallback
        if not credit:
            providers = manifest.get('provider', [])
            if providers and isinstance(providers, list) and len(providers) > 0:
                provider = providers[0]
                if isinstance(provider, dict):
                    label = provider.get('label', {})
                    if isinstance(label, dict):
                        credit = extract_language_map_value(label, site_language)
                    else:
                        credit = str(label)

    credit = clean_metadata_value(credit)

    # Check if attribution is just legal boilerplate
    if credit and is_legal_boilerplate(credit):
        # Fall back to repository/institution from metadata
        fallback = find_metadata_field(
            manifest.get('metadata', []),
            ['Repository', 'Holding Institution', 'Institution'],
            version,
            site_language
        )
        if fallback:
            credit = fallback

    return credit


def extract_manifest_metadata(manifest_url, site_language='en'):
    """
    Extract all metadata fields from IIIF manifest.

    Extracts: title, description, creator, period, location, credit

    Args:
        manifest_url: URL of IIIF manifest
        site_language: Preferred language for extraction

    Returns:
        dict: Extracted metadata with keys: title, description, creator, period, location, credit
              Returns empty dict on error
    """
    try:
        # Fetch manifest
        response = urllib.request.urlopen(manifest_url, timeout=10)
        manifest = json.loads(response.read())

        version = detect_iiif_version(manifest)
        metadata_array = manifest.get('metadata', [])

        extracted = {}

        # Title
        if version == '2.0':
            extracted['title'] = clean_metadata_value(manifest.get('label', ''))
        else:  # v3.0
            label = manifest.get('label', {})
            if isinstance(label, dict):
                extracted['title'] = clean_metadata_value(
                    extract_language_map_value(label, site_language)
                )
            else:
                extracted['title'] = clean_metadata_value(label)

        # Description
        if version == '2.0':
            desc = manifest.get('description', '')
            extracted['description'] = strip_html_tags(desc)
        else:  # v3.0
            summary = manifest.get('summary', {})
            if isinstance(summary, dict):
                extracted['description'] = strip_html_tags(
                    extract_language_map_value(summary, site_language)
                )
            else:
                extracted['description'] = strip_html_tags(summary)

        # Creator
        extracted['creator'] = find_metadata_field(
            metadata_array,
            ['Creator', 'Artist', 'Author', 'Maker', 'Cartographer', 'Contributor', 'Painter', 'Sculptor'],
            version,
            site_language
        )

        # Period
        extracted['period'] = find_metadata_field(
            metadata_array,
            ['Date', 'Period', 'Creation Date', 'Created', 'Date Created', 'Date Note', 'Temporal'],
            version,
            site_language
        )

        # Location (Repository/Institution name, not geographic location)
        extracted['location'] = find_metadata_field(
            metadata_array,
            ['Repository', 'Holding Institution', 'Institution', 'Current Location'],
            version,
            site_language
        )

        # If location not found in metadata, try provider (v3.0)
        if not extracted['location'] and version == '3.0':
            providers = manifest.get('provider', [])
            if providers and isinstance(providers, list) and len(providers) > 0:
                provider = providers[0]
                if isinstance(provider, dict):
                    label = provider.get('label', {})
                    if isinstance(label, dict):
                        extracted['location'] = extract_language_map_value(label, site_language)
                    else:
                        extracted['location'] = str(label).strip()

        # Credit
        extracted['credit'] = extract_credit(manifest, version, site_language)

        return extracted

    except Exception:
        # Silently fail - return empty dict
        # Errors will be caught and logged by calling function
        return {}


def apply_metadata_fallback(row_dict, iiif_metadata):
    """
    Apply fallback hierarchy: CSV > IIIF > empty.

    Modifies row_dict in place, adding IIIF values only for empty CSV fields.

    Args:
        row_dict: Dictionary of object data from CSV
        iiif_metadata: Dictionary of extracted IIIF metadata
    """
    # Core fields that can be auto-populated from IIIF
    # Note: 'location' renamed to 'source' in v0.8.0
    fields = ['title', 'description', 'creator', 'period', 'source', 'credit',
              'year', 'object_type', 'subjects']

    for field in fields:
        csv_value = str(row_dict.get(field, '')).strip()
        iiif_value = str(iiif_metadata.get(field, '')).strip()

        # CSV override: if user entered value, keep it
        if csv_value:
            continue

        # Auto-populate: if CSV empty but IIIF has value, use IIIF
        if iiif_value:
            row_dict[field] = iiif_value
