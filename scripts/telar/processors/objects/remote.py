"""Validating what an object points at over the network.

IIIF manifests, the metadata taken from them, HTTP failures, video hosts and
the SSL context the fetches use. This is the only part of the processor that
reaches outside the site.

Version: v1.7.0
"""

import json
import re
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlparse

from telar.config import get_lang_string, load_site_language
from telar.csv_utils import get_source_url
from telar.iiif_metadata import (
    detect_iiif_version, extract_language_map_value, strip_html_tags,
    clean_metadata_value, find_metadata_field, extract_credit,
    apply_metadata_fallback
)
from telar.media_type import VIDEO_URL_PATTERNS
from telar.processors.objects.local import _detect_media_type


def _validate_source_urls(df, previous_objects, warnings):
    """Fetch each manifest and read what it says, or record why not.

    Media-aware: video objects are checked against the hosts we can embed and
    audio objects are served from local files, so neither is fetched. CSV
    values always win over the manifest's, which is why extraction fills in
    behind them rather than over them.
    """
    # Validate source URL field (checks both source_url and iiif_manifest for backward compatibility)
    if 'source_url' in df.columns or 'iiif_manifest' in df.columns:
        for idx, row in df.iterrows():
            manifest_url = get_source_url(row)
            object_id = row.get('object_id', 'unknown')

            # Skip if empty
            if not manifest_url:
                continue

            # Media-type-aware validation: video/audio objects don't use IIIF
            obj_media_type = _detect_media_type(manifest_url, object_id)
            if obj_media_type == 'Video':
                _check_video_host(manifest_url, object_id, warnings)
                continue
            if obj_media_type == 'Audio':
                print(f"  [INFO] Audio object {object_id} — source URL is not an IIIF manifest, skipping IIIF validation")
                continue

            if _clear_unusable_url(df, idx, manifest_url, object_id,
                                   warnings):
                continue

            ssl_context = _manifest_ssl_context()

            try:
                # Fetch manifest directly with GET (follows redirects automatically)
                req = urllib.request.Request(manifest_url)
                req.add_header('User-Agent', 'Telar/1.0.0-beta (IIIF validator)')

                with urllib.request.urlopen(req, timeout=30, context=ssl_context) as response:
                    content_type = response.headers.get('Content-Type', '')

                    # Check if response is JSON
                    if 'json' not in content_type.lower():
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_not_manifest')
                        msg = f"IIIF manifest for object {object_id} does not return JSON (Content-Type: {content_type})"
                        print(f"  [WARN] {msg}")
                        warnings.append(msg)
                        # Don't clear manifest URL - might still work despite wrong content type
                        continue

                    try:
                        data = json.loads(response.read().decode('utf-8'))

                        # Check for basic IIIF structure
                        has_context = '@context' in data
                        has_type = 'type' in data or '@type' in data

                        if not (has_context or has_type):
                            df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_malformed')
                            msg = f"IIIF manifest for object {object_id} missing required fields (@context or type)"
                            print(f"  [WARN] {msg}")
                            warnings.append(msg)
                        else:
                            _apply_manifest_metadata(
                                df, idx, row, data, object_id)

                    except json.JSONDecodeError:
                        df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_not_manifest')
                        msg = f"IIIF manifest for object {object_id} is not valid JSON"
                        print(f"  [WARN] {msg}")
                        warnings.append(msg)

            except urllib.error.HTTPError as e:
                _record_http_failure(df, idx, e, object_id, manifest_url,
                                     previous_objects, warnings)
            except urllib.error.URLError as e:
                # Network timeout - log for debugging but don't show user-facing warning
                # These are typically transient issues with slow institutional servers
                msg = f"IIIF manifest for object {object_id} slow to respond: {e.reason}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
            except Exception as e:
                df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_validation_failed')
                df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_validation_error')
                msg = f"Error validating IIIF manifest for object {object_id}: {str(e)}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
    return df


def _extracted_from_manifest(data):
    """Everything a manifest offers, read once, by field.

    Presentation API 2 and 3 disagree about where a title and a
    description live, and about whether a value is a string or a language
    map, so each field is read for the version the manifest declares. What
    comes back is a plain dict; nothing here decides whether it is used.
    """
    site_language = load_site_language()
    version = detect_iiif_version(data)
    metadata_array = data.get('metadata', [])

    extracted = {}

    # Title
    if version == '2.0':
        extracted['title'] = clean_metadata_value(data.get('label', ''))
    else:  # v3.0
        label = data.get('label', {})
        if isinstance(label, dict):
            extracted['title'] = clean_metadata_value(
                extract_language_map_value(label, site_language)
            )
        else:
            extracted['title'] = clean_metadata_value(label)

    # Description
    if version == '2.0':
        desc = data.get('description', '')
        extracted['description'] = strip_html_tags(desc)
    else:  # v3.0
        summary = data.get('summary', {})
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

    # Source (Repository/Institution name, not geographic location)
    extracted['source'] = find_metadata_field(
        metadata_array,
        ['Repository', 'Holding Institution', 'Institution', 'Source', 'Current Location'],
        version,
        site_language
    )

    # If source not found in metadata, try provider (v3.0)
    if not extracted['source'] and version == '3.0':
        providers = data.get('provider', [])
        if providers and isinstance(providers, list) and len(providers) > 0:
            provider = providers[0]
            if isinstance(provider, dict):
                provider_label = provider.get('label', {})
                if isinstance(provider_label, dict):
                    extracted['source'] = extract_language_map_value(provider_label, site_language)
                else:
                    extracted['source'] = str(provider_label).strip()

    # Year (structured date for filtering/timeline).
    # Prefer an explicit 'Year' label, then fall back
    # to date fields. The raw value is often prose
    # ("circa 1580-1600"), so pull the first 4-digit
    # sequence for a parseable facet value; if none is
    # present, keep the prose value (graceful degradation).
    extracted['year'] = find_metadata_field(
        metadata_array,
        ['Year', 'Date', 'Date Created', 'Creation Date'],
        version,
        site_language
    )
    if extracted['year']:
        year_match = re.search(r'\d{4}', str(extracted['year']))
        if year_match:
            extracted['year'] = year_match.group(0)
        else:
            print(f"  [INFO] Year value '{extracted['year']}' has no "
                  f"4-digit year — leaving as-is")

    # Medium/Genre: classification for filtering
    extracted['medium'] = find_metadata_field(
        metadata_array,
        ['Type', 'Object Type', 'Resource Type', 'Format'],
        version,
        site_language
    )

    # Subjects (tags for filtering)
    extracted['subjects'] = find_metadata_field(
        metadata_array,
        ['Subject', 'Subjects', 'Keywords', 'Tags', 'Topic'],
        version,
        site_language
    )

    # Credit
    extracted['credit'] = extract_credit(data, version, site_language)
    return extracted


def _apply_manifest_metadata(df, idx, row, data, object_id):
    """Write what the manifest says into the row, behind what the CSV says.

    A site's own spreadsheet is the authority: extraction fills the fields
    the author left empty and never overwrites one they filled. Failure to
    read a manifest we have already accepted is logged and not fatal --
    the object is valid, only its metadata is thinner.
    """
    print(f"  [INFO] Validated IIIF manifest for object {object_id}")

    # Extract metadata from validated manifest
    try:
        extracted = _extracted_from_manifest(data)

        # Apply fallback hierarchy (CSV > IIIF > empty)
        row_dict = row.to_dict()
        apply_metadata_fallback(row_dict, extracted)

        # Update dataframe with extracted values
        # Core fields that can be auto-populated from IIIF
        iiif_fields = ['title', 'description', 'creator', 'period', 'source', 'credit',
                       'year', 'medium', 'subjects']
        for field in iiif_fields:
            if field in row_dict:
                df.at[idx, field] = row_dict[field]

        # Log if any fields were auto-populated
        populated_fields = []
        for field in iiif_fields:
            csv_val = str(row.get(field, '')).strip()
            final_val = str(row_dict.get(field, '')).strip()
            if not csv_val and final_val:
                populated_fields.append(field)

        if populated_fields:
            print(f"  [INFO] Auto-populated from IIIF: {', '.join(populated_fields)}")

    except Exception as e:
        # Metadata extraction failed - log but don't block validation
        print(f"  [WARN] Could not extract metadata from IIIF manifest for {object_id}: {e}")


def _record_http_failure(df, idx, e, object_id, manifest_url,
                         previous_objects, warnings):
    """What an HTTP status from a manifest server means for the object.

    A 429 on a manifest the last build accepted unchanged is the server
    rate-limiting us, not the site being wrong, so it is forgiven. Every
    other status the site can act on has its own message; the rest share a
    generic one carrying the code.
    """
    # Check if we should skip this 429 error (unchanged manifest from previous build)
    skip_429 = False
    if e.code == 429 and object_id in previous_objects:
        prev = previous_objects[object_id]
        # Skip if: same URL as before AND no warning in previous build
        if prev['manifest_url'] == manifest_url and not prev['had_warning']:
            skip_429 = True
            print(f"  [INFO] Skipping 429 error for unchanged manifest: {object_id} ({manifest_url})")

    # Only process error if not skipping
    if not skip_429:
        known_codes = (404, 429, 403, 401, 500, 503, 502)
        if e.code in known_codes:
            df.at[idx, 'object_warning'] = get_lang_string(f'errors.object_warnings.iiif_{e.code}')
            df.at[idx, 'object_warning_short'] = get_lang_string(f'errors.object_warnings.short_{e.code}')
        else:
            df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_error_generic', code=e.code)
            df.at[idx, 'object_warning_short'] = get_lang_string('errors.object_warnings.short_error_generic', code=e.code)
        msg = f"IIIF manifest for object {object_id} returned HTTP {e.code}: {manifest_url}"
        print(f"  [WARN] {msg}")
        warnings.append(msg)


def _check_video_host(manifest_url, object_id, warnings):
    """A video is embedded, not fetched, so only its host is checked.

    An unrecognised host is a warning rather than a failure: the URL may
    still play, we simply cannot promise the embed.
    """
    # Validate video source URL — check it's a recognised host
    recognised = any(host in manifest_url for host in VIDEO_URL_PATTERNS)
    if recognised:
        host = next(h for h in VIDEO_URL_PATTERNS if h in manifest_url)
        print(f"  [INFO] Video object {object_id} uses {host}")
    else:
        msg = f"Video object {object_id} uses unrecognised video host: {manifest_url}"
        print(f"  [WARN] {msg}")
        warnings.append(msg)


def _manifest_ssl_context():
    """Verify certificates, so a substituted manifest cannot rewrite the
    metadata that goes into the site.

    certifi's bundle when it is installed: python.org's macOS builds do
    not link the system trust store, and the default context there
    verifies nothing it can find.
    """
    try:
        import certifi
        ssl_context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ssl_context = ssl.create_default_context()
    return ssl_context


def _clear_unusable_url(df, idx, manifest_url, object_id, warnings):
    """Refuse anything that is not http(s), and clear it.

    Left in place it would be fetched on every build and fail every time.
    Both column names are cleared, because either may be the one the site
    writes into. Returns whether it did so.
    """
    parsed = urlparse(manifest_url)
    if parsed.scheme in ['http', 'https']:
        return False

    # Clear both columns (whichever exists)
    if 'source_url' in df.columns:
        df.at[idx, 'source_url'] = ''
    if 'iiif_manifest' in df.columns:
        df.at[idx, 'iiif_manifest'] = ''
    df.at[idx, 'object_warning'] = get_lang_string('errors.object_warnings.iiif_invalid_url')
    msg = f"Cleared invalid source URL for object {object_id}: not a valid URL"
    print(f"  [WARN] {msg}")
    warnings.append(msg)
    return True
