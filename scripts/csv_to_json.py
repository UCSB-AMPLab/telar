#!/usr/bin/env python3
"""
Convert CSV files from Google Sheets to JSON for Jekyll
"""

import pandas as pd
import json
import os
import re
from pathlib import Path
import markdown
import urllib.request
import urllib.error
from urllib.parse import urlparse
import ssl

def read_markdown_file(file_path):
    """
    Read a markdown file and parse frontmatter

    Args:
        file_path: Path to markdown file relative to components/texts/

    Returns:
        dict with 'title' and 'content' keys, or None if file doesn't exist
    """
    full_path = Path('components/texts') / file_path

    if not full_path.exists():
        print(f"Warning: Markdown file not found: {full_path}")
        return None

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse frontmatter
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(frontmatter_pattern, content, re.DOTALL)

        if match:
            frontmatter_text = match.group(1)
            body = match.group(2).strip()

            # Extract title from frontmatter
            title_match = re.search(r'title:\s*["\']?(.*?)["\']?\s*$', frontmatter_text, re.MULTILINE)
            title = title_match.group(1) if title_match else ''

            # Convert markdown to HTML
            html_content = markdown.markdown(body, extensions=['extra', 'nl2br'])

            return {
                'title': title,
                'content': html_content
            }
        else:
            # No frontmatter, just content
            html_content = markdown.markdown(content.strip(), extensions=['extra', 'nl2br'])
            return {
                'title': '',
                'content': html_content
            }

    except Exception as e:
        print(f"Error reading markdown file {full_path}: {e}")
        return None

def csv_to_json(csv_path, json_path, process_func=None):
    """
    Convert CSV file to JSON

    Args:
        csv_path: Path to input CSV file
        json_path: Path to output JSON file
        process_func: Optional function to process the dataframe before conversion
    """
    if not os.path.exists(csv_path):
        print(f"Warning: {csv_path} not found. Skipping.")
        return

    try:
        # Read CSV file and filter out comment lines (starting with #)
        # We can't use pandas' comment parameter because it treats # anywhere as a comment,
        # which breaks hex color codes like #2c3e50
        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = [line for line in f if not line.strip().startswith('#')]

        # Parse filtered CSV content
        from io import StringIO
        csv_content = ''.join(lines)
        df = pd.read_csv(StringIO(csv_content), on_bad_lines='warn')

        # Apply processing function if provided
        if process_func:
            df = process_func(df)

        # Convert to JSON
        data = df.to_dict('records')

        # If dataframe has metadata (e.g., viewer warnings), prepend as first element
        if hasattr(df, 'attrs') and 'viewer_warnings' in df.attrs:
            viewer_warnings = df.attrs['viewer_warnings']
            if viewer_warnings:  # Only add if there are warnings
                metadata = {
                    '_metadata': True,
                    'viewer_warnings': viewer_warnings
                }
                data.insert(0, metadata)

        # Write JSON file
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"✓ Converted {csv_path} to {json_path}")

    except Exception as e:
        print(f"Error converting {csv_path}: {e}")

def process_project_setup(df):
    """
    Process project setup CSV
    Expected columns: key, value, example (optional)
    """
    # Drop example column if it exists
    if 'example' in df.columns:
        df = df.drop(columns=['example'])

    # Convert key-value pairs to dictionary
    project_dict = {}
    stories_list = []

    in_stories_section = False

    for _, row in df.iterrows():
        key = str(row.get('key', '')).strip()
        value = row.get('value', '')

        if key == 'STORIES':
            in_stories_section = True
            continue

        if in_stories_section:
            # Parse story entries
            if pd.notna(value):
                stories_list.append({
                    'number': key,
                    'title': value
                })
        else:
            # Regular project settings
            if key and pd.notna(value):
                project_dict[key] = value

    # Return combined structure
    result = {**project_dict, 'stories': stories_list}
    return pd.DataFrame([result])

def process_objects(df):
    """
    Process objects CSV
    Expected columns: object_id, title, creator, date, description, etc.
    """
    # Tracking for summary
    warnings = []

    # Drop example column if it exists
    if 'example' in df.columns:
        df = df.drop(columns=['example'])

    # Clean up NaN values
    df = df.fillna('')

    # Remove rows where object_id is empty
    df = df[df['object_id'].astype(str).str.strip() != '']

    # Validate and clean object_id values
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff', '.bmp', '.svg']
    for idx, row in df.iterrows():
        object_id = str(row.get('object_id', '')).strip()
        original_id = object_id
        modified = False

        # Check for file extensions and strip them
        for ext in valid_extensions:
            if object_id.lower().endswith(ext):
                object_id = object_id[:-len(ext)]
                modified = True
                print(f"  [INFO] Stripped file extension from object_id: '{original_id}' → '{object_id}'")
                break

        # Check for spaces in object_id
        if ' ' in object_id:
            msg = f"Object ID '{object_id}' contains spaces - this may cause issues with file paths"
            print(f"  [WARN] {msg}")
            warnings.append(msg)

        # Update the dataframe if modified
        if modified:
            df.at[idx, 'object_id'] = object_id

    # Add object_warning column for IIIF/image validation
    if 'object_warning' not in df.columns:
        df['object_warning'] = ''

    # Validate thumbnail field
    if 'thumbnail' in df.columns:
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.tif', '.tiff']
        placeholder_values = ['n/a', 'null', 'none', 'placeholder', 'na', 'thumbnail']

        for idx, row in df.iterrows():
            thumbnail = str(row.get('thumbnail', '')).strip()
            object_id = row.get('object_id', 'unknown')

            # Skip if already empty
            if not thumbnail:
                continue

            # Check for placeholder values
            if thumbnail.lower() in placeholder_values:
                df.at[idx, 'thumbnail'] = ''
                msg = f"Cleared invalid thumbnail placeholder '{thumbnail}' for object {object_id}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
                continue

            # Check for valid image extension
            has_valid_extension = any(thumbnail.lower().endswith(ext) for ext in valid_extensions)

            if not has_valid_extension:
                df.at[idx, 'thumbnail'] = ''
                msg = f"Cleared invalid thumbnail '{thumbnail}' for object {object_id} (not an image file)"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
                continue

            # Normalize path to avoid duplicate slashes
            # Accept both /path and path, ensure single leading slash if present
            if thumbnail.startswith('/'):
                # Remove duplicate slashes
                normalized = '/' + '/'.join(filter(None, thumbnail.split('/')))
                if normalized != thumbnail:
                    df.at[idx, 'thumbnail'] = normalized
                    thumbnail = normalized
                    print(f"  [INFO] Normalized thumbnail path for object {object_id}: {normalized}")

            # Check if file exists (remove leading slash for filesystem check)
            file_path = thumbnail.lstrip('/')
            if not Path(file_path).exists():
                msg = f"Thumbnail file not found for object {object_id}: {thumbnail}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
                # Don't clear - file might be added later or exist in different environment

    # Validate IIIF manifest field
    if 'iiif_manifest' in df.columns:
        for idx, row in df.iterrows():
            manifest_url = str(row.get('iiif_manifest', '')).strip()
            object_id = row.get('object_id', 'unknown')

            # Skip if empty
            if not manifest_url:
                continue

            # Check if it's a valid URL
            parsed = urlparse(manifest_url)
            if not parsed.scheme in ['http', 'https']:
                df.at[idx, 'iiif_manifest'] = ''
                df.at[idx, 'object_warning'] = f"the IIIF manifest URL you specified in your configuration CSV or Google Sheet is not valid"
                msg = f"Cleared invalid IIIF manifest for object {object_id}: not a valid URL"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
                continue

            # Try to fetch the manifest (with timeout)
            # Create SSL context that doesn't verify certificates (avoid false positives)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            try:
                req = urllib.request.Request(manifest_url, method='HEAD')
                req.add_header('User-Agent', 'Telar/0.3.0 (IIIF validator)')

                with urllib.request.urlopen(req, timeout=5, context=ssl_context) as response:
                    content_type = response.headers.get('Content-Type', '')

                    # Check if response is JSON
                    if 'json' not in content_type.lower():
                        df.at[idx, 'object_warning'] = f"the IIIF manifest URL you specified in your configuration CSV or Google Sheet does not point to a valid IIIF manifest"
                        msg = f"IIIF manifest for object {object_id} does not return JSON (Content-Type: {content_type})"
                        print(f"  [WARN] {msg}")
                        warnings.append(msg)
                        # Don't clear manifest URL - might still work despite wrong content type
                        continue

                    # Fetch full content to validate structure
                    req_get = urllib.request.Request(manifest_url)
                    req_get.add_header('User-Agent', 'Telar/0.3.0 (IIIF validator)')

                    with urllib.request.urlopen(req_get, timeout=10, context=ssl_context) as resp:
                        try:
                            data = json.loads(resp.read().decode('utf-8'))

                            # Check for basic IIIF structure
                            has_context = '@context' in data
                            has_type = 'type' in data or '@type' in data

                            if not (has_context or has_type):
                                df.at[idx, 'object_warning'] = f"the IIIF manifest you specified in your configuration CSV or Google Sheet is not properly formatted"
                                msg = f"IIIF manifest for object {object_id} missing required fields (@context or type)"
                                print(f"  [WARN] {msg}")
                                warnings.append(msg)
                            else:
                                print(f"  [INFO] Validated IIIF manifest for object {object_id}")

                        except json.JSONDecodeError:
                            df.at[idx, 'object_warning'] = f"the IIIF manifest URL you specified in your configuration CSV or Google Sheet does not point to a valid IIIF manifest"
                            msg = f"IIIF manifest for object {object_id} is not valid JSON"
                            print(f"  [WARN] {msg}")
                            warnings.append(msg)

            except urllib.error.HTTPError as e:
                if e.code == 404:
                    df.at[idx, 'object_warning'] = f"the IIIF manifest URL you specified in your configuration CSV or Google Sheet does not exist (error 404)"
                else:
                    df.at[idx, 'object_warning'] = f"the IIIF manifest URL you specified in your configuration CSV or Google Sheet could not be accessed (error {e.code})"
                msg = f"IIIF manifest for object {object_id} returned HTTP {e.code}: {manifest_url}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
            except urllib.error.URLError as e:
                df.at[idx, 'object_warning'] = f"the IIIF manifest URL you specified in your configuration CSV or Google Sheet could not be reached"
                msg = f"IIIF manifest for object {object_id} could not be reached: {e.reason}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
            except Exception as e:
                df.at[idx, 'object_warning'] = f"the IIIF manifest URL you specified in your configuration CSV or Google Sheet could not be validated"
                msg = f"Error validating IIIF manifest for object {object_id}: {str(e)}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)

    # Validate that objects have either IIIF manifest OR local image file
    for idx, row in df.iterrows():
        object_id = row.get('object_id', 'unknown')
        iiif_manifest = str(row.get('iiif_manifest', '')).strip()

        # Skip if already has a valid IIIF manifest
        if iiif_manifest:
            continue

        # No external IIIF manifest - check for local image file
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff']
        has_local_image = False

        for ext in valid_extensions:
            local_image_path = Path(f'components/images/objects/{object_id}{ext}')
            if local_image_path.exists():
                has_local_image = True
                print(f"  [INFO] Object {object_id} uses local image: {local_image_path}")
                break

        # Warn if object has neither external manifest nor local image
        if not has_local_image:
            error_msg = f"the image file for the object ID you specified ({object_id}) in your configuration CSV or Google Sheet was not found in components/images/objects/"
            df.at[idx, 'object_warning'] = error_msg
            msg = f"Object {object_id} has no IIIF manifest or local image file"
            print(f"  [WARN] {msg}")
            warnings.append(msg)

    # Print summary if there were issues
    if warnings:
        print(f"\n  Objects validation summary: {len(warnings)} warning(s)")

    return df

def process_glossary(df):
    """
    Process glossary CSV with file references
    Expected columns: term_id, title, short_definition, definition_file, etc.
    """
    # Drop example column if it exists
    if 'example' in df.columns:
        df = df.drop(columns=['example'])

    # Clean up NaN values
    df = df.fillna('')

    # Remove rows where term_id is empty
    df = df[df['term_id'].astype(str).str.strip() != '']

    # Process definition_file column
    if 'definition_file' in df.columns:
        for idx, row in df.iterrows():
            file_ref = row['definition_file']
            if file_ref and file_ref.strip():
                # For glossary, files are directly in glossary/ folder
                file_path = f"glossary/{file_ref.strip()}"
                markdown_data = read_markdown_file(file_path)
                if markdown_data:
                    # Store the full definition text
                    df.at[idx, 'definition'] = markdown_data['content']
                else:
                    df.at[idx, 'definition'] = ''

    return df

def process_story(df):
    """
    Process story CSV with file references
    Expected columns: step, question, answer, object, x, y, zoom, layer1_file, layer2_file, etc.
    """
    # Tracking for summary
    warnings = []

    # Drop example column if it exists
    if 'example' in df.columns:
        df = df.drop(columns=['example'])

    # Clean up NaN values
    df = df.fillna('')

    # Remove completely empty rows
    df = df[df.astype(str).apply(lambda x: x.str.strip()).ne('').any(axis=1)]

    # Load objects data for validation
    objects_data = {}
    objects_json_path = Path('_data/objects.json')
    if objects_json_path.exists():
        try:
            with open(objects_json_path, 'r', encoding='utf-8') as f:
                objects_list = json.load(f)
                # Create lookup dictionary by object_id
                objects_data = {obj['object_id']: obj for obj in objects_list}
        except Exception as e:
            print(f"  [WARN] Could not load objects.json for validation: {e}")

    # Add viewer_warning column if it doesn't exist
    if 'viewer_warning' not in df.columns:
        df['viewer_warning'] = ''

    # Validate object references
    if 'object' in df.columns and objects_data:
        for idx, row in df.iterrows():
            object_id = str(row.get('object', '')).strip()
            step_num = row.get('step', 'unknown')

            # Skip if no object specified
            if not object_id:
                continue

            # Check if object exists
            if object_id not in objects_data:
                error_msg = f"the object <code>{object_id}</code> was not found in <code>objects.csv</code>"
                df.at[idx, 'viewer_warning'] = error_msg
                msg = f"Story step {step_num} references missing object: {object_id}"
                print(f"  [WARN] {msg}")
                warnings.append(msg)
                continue

            # Check if object has IIIF manifest or local image
            obj = objects_data[object_id]
            iiif_manifest = obj.get('iiif_manifest', '').strip()

            # If no external IIIF manifest, check for local image file
            if not iiif_manifest:
                # Check for local image in components/images/objects/
                valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff']
                has_local_image = False

                for ext in valid_extensions:
                    local_image_path = Path(f'components/images/objects/{object_id}{ext}')
                    if local_image_path.exists():
                        has_local_image = True
                        print(f"  [INFO] Object {object_id} uses local image: {local_image_path}")
                        break

                # Only warn if object has neither external manifest nor local image
                if not has_local_image:
                    error_msg = f"the object <code>{object_id}</code> has no IIIF manifest or local image file"
                    df.at[idx, 'viewer_warning'] = error_msg
                    msg = f"Story step {step_num} references object without IIIF source: {object_id}"
                    print(f"  [WARN] {msg}")
                    warnings.append(msg)

    # Process file reference columns
    for col in df.columns:
        if col.endswith('_file'):
            # Determine the base name (e.g., 'layer1' from 'layer1_file')
            base_name = col.replace('_file', '')

            # Create new columns for title and text
            title_col = f'{base_name}_title'
            text_col = f'{base_name}_text'

            # Initialize new columns with empty strings
            if title_col not in df.columns:
                df[title_col] = ''
            if text_col not in df.columns:
                df[text_col] = ''

            # Read markdown files and populate columns
            for idx, row in df.iterrows():
                file_ref = row[col]
                if file_ref and file_ref.strip():
                    # Prepend 'stories/' to the path for story files
                    file_path = f"stories/{file_ref.strip()}"
                    markdown_data = read_markdown_file(file_path)
                    if markdown_data:
                        df.at[idx, title_col] = markdown_data['title']
                        df.at[idx, text_col] = markdown_data['content']
                    else:
                        # Insert error message for missing file
                        step_num = row.get('step', 'unknown')
                        df.at[idx, title_col] = 'Content Missing'
                        error_html = f'''<div class="alert alert-warning" role="alert">
    <strong>Content file missing:</strong> <code>{file_ref.strip()}</code><br>
    Please add this file to <code>components/texts/stories/</code> or remove the reference from the CSV.
</div>'''
                        df.at[idx, text_col] = error_html
                        msg = f"Missing markdown file for story step {step_num}, {base_name}: {file_ref.strip()}"
                        print(f"  [WARN] {msg}")
                        warnings.append(msg)

            # Drop the _file column as it's no longer needed in JSON
            df = df.drop(columns=[col])

    # Set default coordinates for empty values
    coordinate_columns = ['x', 'y', 'zoom']
    for col in coordinate_columns:
        if col in df.columns:
            # Convert to string first to handle NaN values
            df[col] = df[col].astype(str)
            # Set defaults for empty or 'nan' values
            if col == 'x':
                df.loc[df[col].isin(['', 'nan']), col] = '0.5'
            elif col == 'y':
                df.loc[df[col].isin(['', 'nan']), col] = '0.5'
            elif col == 'zoom':
                df.loc[df[col].isin(['', 'nan']), col] = '1'

    # Collect all warnings for intro display
    all_warnings = []
    for idx, row in df.iterrows():
        step_num = row.get('step', 'unknown')

        # Check for viewer warnings (missing object/IIIF)
        viewer_warning = row.get('viewer_warning', '').strip()
        if viewer_warning:
            all_warnings.append({
                'step': step_num,
                'type': 'viewer',
                'message': viewer_warning
            })

        # Check for panel content warnings (missing markdown files)
        # Look for "Content Missing" title which indicates missing files
        for layer in ['layer1', 'layer2']:
            title_col = f'{layer}_title'
            if title_col in row and row[title_col] == 'Content Missing':
                # Extract the filename from the error HTML in the text column
                text_col = f'{layer}_text'
                text = row.get(text_col, '')
                # Extract filename from the HTML (it's between <code> tags)
                import re
                filename_match = re.search(r'<code>(.*?)</code>', text)
                # Get layer number for display (1 or 2)
                layer_num = layer[-1]  # Get '1' or '2' from 'layer1' or 'layer2'
                if filename_match:
                    filename = filename_match.group(1)
                    all_warnings.append({
                        'step': step_num,
                        'type': 'panel',
                        'message': f'the file for the layer {layer_num} panel, <code>{filename}</code>, was not found'
                    })
                else:
                    # Fallback if regex fails
                    all_warnings.append({
                        'step': step_num,
                        'type': 'panel',
                        'message': f'the file for the layer {layer_num} panel was not found'
                    })

    # Store warnings in dataframe as metadata (will be added to JSON)
    df.attrs['viewer_warnings'] = all_warnings

    # Print summary if there were issues
    if warnings:
        print(f"\n  Story validation summary: {len(warnings)} warning(s)")

    return df

def main():
    """Main conversion process"""
    data_dir = Path('_data')
    data_dir.mkdir(exist_ok=True)

    structures_dir = Path('components/structures')

    print("Converting CSV files to JSON...")
    print("-" * 50)

    # Convert project setup
    csv_to_json(
        'components/structures/project.csv',
        '_data/project.json',
        process_project_setup
    )

    # Convert objects
    csv_to_json(
        'components/structures/objects.csv',
        '_data/objects.json',
        process_objects
    )

    # Note: Glossary is now sourced directly from components/texts/glossary/
    # and processed by generate_collections.py

    # Convert story files
    # Look for any CSV files that start with "story-" or "chapter-"
    for csv_file in structures_dir.glob('story-*.csv'):
        json_filename = csv_file.stem + '.json'
        json_file = data_dir / json_filename
        csv_to_json(
            str(csv_file),
            str(json_file),
            process_story
        )

    for csv_file in structures_dir.glob('chapter-*.csv'):
        json_filename = csv_file.stem + '.json'
        json_file = data_dir / json_filename
        csv_to_json(
            str(csv_file),
            str(json_file),
            process_story
        )

    print("-" * 50)
    print("Conversion complete!")

if __name__ == '__main__':
    main()
