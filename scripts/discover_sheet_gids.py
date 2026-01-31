#!/usr/bin/env python3
"""
Discover Google Sheets Tab GIDs

Telar sites can draw their content from Google Sheets spreadsheets.
Each spreadsheet has multiple tabs (sheets) — typically one for the
project setup, one for objects, and one per story. To download a
specific tab as CSV, Google requires a numeric identifier called a GID.

Google Sheets exposes two different URL types, and Telar needs both:
the "shared" URL (from the Share button) contains the Sheet ID, used
to construct CSV export URLs; the "published" URL (from File > Share >
Publish to web) contains an HTML page with tab names and their GIDs
embedded in the markup.

This script parses the published HTML page to discover all tab names
and their GIDs, then tests each GID against the shared Sheet ID to
confirm it works. The result is a mapping of tab names to GIDs that
fetch_google_sheets.py uses to download each tab as a CSV file. It can
also output environment variables for GitHub Actions workflows.

Version: v0.7.0-beta

Usage:
    python scripts/discover_sheet_gids.py <SHARED_URL> <PUBLISHED_URL>

Example:
    python scripts/discover_sheet_gids.py \
      "https://docs.google.com/spreadsheets/d/ABC123.../edit" \
      "https://docs.google.com/spreadsheets/d/e/2PACX-.../pubhtml"
"""

import re
import sys
import urllib.request
import urllib.error
import ssl
import argparse
from html.parser import HTMLParser

class SheetTabParser(HTMLParser):
    """Parse published Google Sheets HTML to extract tab names and GIDs"""
    def __init__(self):
        super().__init__()
        self.tabs = []
        self.current_tab_name = None
        self.in_sheet_button = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        # Look for sheet-button elements (tab buttons in published view)
        if 'id' in attrs_dict and attrs_dict['id'].startswith('sheet-button-'):
            self.in_sheet_button = True
            # Extract GID from the ID (format: sheet-button-123456)
            gid = attrs_dict['id'].replace('sheet-button-', '')
            self.current_gid = gid

        # Also look for links with gid= in href
        if tag == 'a' and 'href' in attrs_dict:
            href = attrs_dict['href']
            gid_match = re.search(r'gid=(\d+)', href)
            if gid_match and self.in_sheet_button:
                self.current_gid = gid_match.group(1)

    def handle_data(self, data):
        if self.in_sheet_button and data.strip():
            # This is the tab name
            tab_name = data.strip()
            if hasattr(self, 'current_gid'):
                # Avoid duplicates
                if not any(t[1] == self.current_gid for t in self.tabs):
                    self.tabs.append((tab_name, self.current_gid))
            self.in_sheet_button = False

def extract_sheet_id(url):
    """Extract the Sheet ID from a Google Sheets URL"""
    # Match /d/ format (shared/edit URLs)
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
    if match:
        return match.group(1)
    return None

def extract_published_id(url):
    """Extract the published ID from a published Google Sheets URL"""
    # Match /d/e/ format (published URLs)
    match = re.search(r'/d/e/([a-zA-Z0-9-_]+)', url)
    if match:
        return match.group(1)
    return None

def discover_gids_from_published(published_url):
    """
    Discover tab names and GIDs by parsing the published HTML
    """
    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(published_url)
        req.add_header('User-Agent', 'Mozilla/5.0')

        with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
            html = response.read().decode('utf-8', errors='ignore')

            # Try parsing JavaScript items.push() calls first
            # Pattern: items.push({name: "TabName", pageUrl: "...", gid: "123456"});
            js_pattern = r'items\.push\(\{name:\s*"([^"]+)"[^}]*gid:\s*"(\d+)"'
            js_matches = re.findall(js_pattern, html)

            if js_matches:
                # Found tab names and GIDs in JavaScript
                return [(name, gid) for name, gid in js_matches]

            # Try parsing with HTMLParser
            parser = SheetTabParser()
            parser.feed(html)

            if parser.tabs:
                return parser.tabs

            # Fallback: regex-based GID extraction only
            # Look for patterns like: gid=123456 in the HTML
            gid_pattern = r'gid=(\d+)'
            gids = list(set(re.findall(gid_pattern, html)))

            # Filter out empty or zero GIDs
            gids = [g for g in gids if g and g != '0']

            # If we found GIDs but no names, create generic names
            if gids:
                tabs = []
                for i, gid in enumerate(sorted(gids, key=int), start=1):
                    tabs.append((f'Tab {i}', gid))

                return tabs

            return None

    except Exception as e:
        print(f"❌ Error fetching published sheet: {e}", file=sys.stderr)
        return None

def test_gid(sheet_id, gid):
    """Test if a GID works by attempting to fetch CSV"""
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?gid={gid}&format=csv'
    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5, context=ssl_context) as response:
            first_line = response.read(100).decode('utf-8', errors='ignore')
            return 'DOCTYPE' not in first_line  # If we get HTML error page, it failed
    except:
        return False

def main():
    parser = argparse.ArgumentParser(
        description='Discover Google Sheets tab GIDs automatically',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Example:
  python scripts/discover_sheet_gids.py \\
    "https://docs.google.com/spreadsheets/d/ABC123.../edit" \\
    "https://docs.google.com/spreadsheets/d/e/2PACX-.../pubhtml"

  # Output as environment variables for GitHub Actions
  python scripts/discover_sheet_gids.py --output-env \\
    "SHARED_URL" "PUBLISHED_URL"
        '''
    )
    parser.add_argument('shared_url', help='Shared Google Sheets URL (from Share button)')
    parser.add_argument('published_url', help='Published Google Sheets URL (from Publish to web)')
    parser.add_argument('--output-env', action='store_true',
                        help='Output as environment variables (for GitHub Actions)')

    args = parser.parse_args()

    shared_url = args.shared_url
    published_url = args.published_url
    output_env = args.output_env

    if not output_env:
        print("=" * 70)
        print("Google Sheets GID Discovery Tool")
        print("=" * 70)
        print()

    # Extract Sheet ID from shared URL
    sheet_id = extract_sheet_id(shared_url)
    if not sheet_id:
        print("ERROR: Could not extract Sheet ID from shared URL", file=sys.stderr)
        print(f"Shared URL provided: {shared_url}", file=sys.stderr)
        print("\nMake sure your shared URL looks like:", file=sys.stderr)
        print("  https://docs.google.com/spreadsheets/d/SHEET_ID/edit", file=sys.stderr)
        sys.exit(1)

    if not output_env:
        print(f"✓ Sheet ID: {sheet_id}")

        # Extract published ID
        published_id = extract_published_id(published_url)
        if not published_id:
            print("WARNING: Could not extract published ID from URL")
            print(f"Published URL provided: {published_url}")
            print("This may still work if the URL is valid...")
        else:
            print(f"✓ Published ID: {published_id}")

        print()
        print("Discovering tabs from published sheet...")

    # Discover GIDs from published HTML
    tabs = discover_gids_from_published(published_url)

    if not tabs:
        print("ERROR: Could not discover sheet tabs from published URL", file=sys.stderr)
        if not output_env:
            print("\nPlease ensure:", file=sys.stderr)
            print("  1. You have published the sheet (File > Share > Publish to web)", file=sys.stderr)
            print("  2. The published URL is accessible", file=sys.stderr)
        sys.exit(1)

    if not output_env:
        print(f"✓ Found {len(tabs)} tab(s)")
        print()
        print("-" * 70)
        print("Testing tabs with shared Sheet ID:")
        print("-" * 70)

    working_tabs = []
    for tab_name, gid in tabs:
        works = test_gid(sheet_id, gid)
        if not output_env:
            status = "✓" if works else "✗"
            print(f"{status} {tab_name:20s} → gid={gid}")
        if works:
            working_tabs.append((tab_name, gid))

    if not working_tabs:
        print("\nERROR: None of the discovered GIDs work with the shared Sheet ID", file=sys.stderr)
        if not output_env:
            print("This usually means the sheet is not properly shared.", file=sys.stderr)
            print("\nPlease ensure:", file=sys.stderr)
            print("  1. The sheet is shared with 'Anyone with the link' (Viewer access)", file=sys.stderr)
            print("  2. Both URLs are from the SAME Google Sheet", file=sys.stderr)
        sys.exit(1)

    # Map tab names/numbers to environment variable names
    # System tabs
    system_tabs = {'project', 'objects', 'instructions', 'tab 1', 'tab 2', 'tab 3'}

    tab_mapping = {
        'project': 'PROJECT_GID',
        'objects': 'OBJECTS_GID',
        'tab 1': 'PROJECT_GID',  # Fallback for generic tab names
        'tab 2': 'PROJECT_GID',
        'tab 3': 'OBJECTS_GID',
    }

    # Dynamically add story tabs discovered in the sheet (v0.6.0+)
    # Supports both semantic (your-story, tu-historia) and traditional (story-1, story-2) identifiers
    for tab_name, _ in working_tabs:
        tab_lower = tab_name.lower()
        # Any tab that's not a system tab is a story/chapter tab
        if tab_lower not in system_tabs and not tab_lower.startswith('#'):
            # Create environment variable name from tab name
            # your-story → YOUR_STORY_GID, story-1 → STORY_1_GID
            safe_name = re.sub(r'[^A-Z0-9_]', '_', tab_name.upper())
            tab_mapping[tab_lower] = f'{safe_name}_GID'

    if output_env:
        # Output environment variables for GitHub Actions
        print(f"SHEET_ID={sheet_id}")
        for tab_name, gid in working_tabs:
            var_name = tab_mapping.get(tab_name.lower())
            if var_name:
                print(f"{var_name}={gid}")
            else:
                # For unknown tabs, create a safe variable name
                safe_name = re.sub(r'[^A-Z0-9_]', '_', tab_name.upper())
                print(f"{safe_name}_GID={gid}")
    else:
        # Human-readable output
        print()
        print("-" * 70)
        print("Discovered Tabs:")
        print("-" * 70)
        print()
        for tab_name, gid in working_tabs:
            print(f"✓ {tab_name:20s} (gid={gid})")

        print()
        print("-" * 70)
        print("Quick Test URLs:")
        print("-" * 70)
        print()
        for tab_name, gid in working_tabs:
            url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?gid={gid}&format=csv"
            print(f"{tab_name}:")
            print(f"  {url}")
            print()

        print("-" * 70)
        print("✓ Discovery complete!")
        print("-" * 70)
        print()
        print("Your Google Sheets URLs are already configured in _config.yml")
        print("No additional setup needed for GitHub Actions.")

if __name__ == '__main__':
    main()
