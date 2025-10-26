# Google Sheets Setup Guide (Local Development)

This guide is for users running Telar locally on their computer.

**If you're using GitHub Pages only** (no local development), you don't need this guide. Simply follow the instructions in the `google_sheets` section of your `_config.yml` file instead.

## Overview

With the Google Sheets integration, you can:
- Edit exhibition content in a familiar spreadsheet interface
- Collaborate with team members in real-time
- Fetch content from Google Sheets before building locally

## Setup Process

### Step 1: Get the Template

Choose one of two options:

**Option A: Duplicate our template**
- Go to https://bit.ly/telar-template
- Click **File > Make a copy**
- Save to your Google Drive

**Option B: Import the Excel file**
1. Download `telar-template.xlsx` from the `docs/google_sheets_integration/` folder
2. Go to [Google Sheets](https://sheets.google.com)
3. Click **File > Import**
4. Upload `telar-template.xlsx`
5. Choose **Replace spreadsheet**

You should see 4 tabs:
- `project` - Site-wide configuration and story list
- `objects` - IIIF objects in your exhibition
- `story-1` - First story's steps and content
- `story-2` - Second story's steps and content

### Step 2: Share and Publish Your Sheet

#### Share Your Sheet

1. Click the **Share** button in the top-right
2. Under "General access", choose **Anyone with the link**
3. Set permission to **Viewer**
4. Click **Done**
5. **Copy the shared URL** from your browser address bar

#### Publish Your Sheet

1. Go to **File > Share > Publish to web**
2. Click **Publish** (use default settings)
3. **Copy the published URL** that Google provides

### Step 3: Configure _config.yml

1. Open `_config.yml` in your repository
2. Find the `google_sheets` section
3. Set `enabled: true`
4. Paste your shared URL into `shared_url`
5. Paste your published URL into `published_url`
6. Save the file

### Step 4: Fetch CSVs Before Building

Before building your site locally, run:

```bash
python3 scripts/fetch_google_sheets.py
```

This script will:
- ✓ Read URLs from your `_config.yml`
- ✓ Automatically discover all tab GIDs
- ✓ Fetch CSVs to `components/structures/`
- ✓ Skip instruction tabs

Then build your site as normal:

```bash
python3 scripts/csv_to_json.py
python3 scripts/generate_collections.py
bundle exec jekyll build
```

## Sheet Structure Reference

### project Sheet

| Column | Description |
|--------|-------------|
| key | Configuration key (e.g., `project_title`, `primary_color`) |
| value | Configuration value |

Special section: After the `STORIES` key, list your stories as:
- Column A: Story number (1, 2, 3...)
- Column B: Story title

### objects Sheet

| Column | Description |
|--------|-------------|
| object_id | Unique identifier (no spaces, no file extensions) |
| title | Display title of the object |
| description | Full text description (supports markdown) |
| iiif_manifest | URL to external IIIF manifest (optional) |
| creator | Artist/creator name |
| period | Time period or date |
| medium | Materials and technique |
| dimensions | Physical dimensions |
| location | Current location/collection |
| credit | Credit line or attribution |
| thumbnail | Path to thumbnail image (optional) |

### story Sheets (story-1, story-2, etc.)

| Column | Description |
|--------|-------------|
| step | Step number (0 for intro) |
| object | Object ID to display (must exist in objects sheet) |
| x | X coordinate (0.000 to 1.000) |
| y | Y coordinate (0.000 to 1.000) |
| zoom | Zoom level (decimal number, typically 1-5) |
| question | Main heading for this step |
| answer | Subheading or short answer text |
| layer1_button | Button text for Layer 1 panel |
| layer1_file | Filename in `components/texts/stories/` (e.g., `step-1-layer1.md`) |
| layer2_button | Button text for Layer 2 panel |
| layer2_file | Filename in `components/texts/stories/` (e.g., `step-1-layer2.md`) |

## Tips and Best Practices

### Using Instruction Rows and Columns

You can add instructions and notes directly in your Google Sheets that will be ignored during processing:

**Instruction Rows** - Entire rows starting with `#` will be skipped:
```
# This entire row will be ignored during processing
# TODO: Add more objects from the XYZ collection
# SECTION: Colonial Period Objects
```

Use instruction rows for:
- Section breaks between groups of items
- TODO reminders and notes
- Temporary comments during editing

**Instruction Columns** - Any column with a name starting with `#` will be ignored:
```
# Instructions    # Notes    # TODO
```

Use instruction columns for:
- Row-by-row guidance (e.g., "Use short title here")
- Field-specific examples and tips
- Tracking which rows need review

The template includes a `# Instructions` column with examples. You can rename it, add more instruction columns, or remove them entirely.

### Coordinate Precision
- Use exactly 3 decimal places for x, y, zoom (e.g., `0.500`, not `0.5`)

### Object IDs
- Use lowercase letters, numbers, hyphens, and underscores only
- No spaces or special characters
- No file extensions (use `map-1`, not `map-1.jpg`)

### Adding More Stories
1. Duplicate one of the existing story tabs
2. Rename it (e.g., `story-3`)
3. Add an entry in the project sheet under the STORIES section
4. The fetch script will automatically discover and fetch the new story tab

### Content Files
- Panel content (layer1_file, layer2_file) still needs to be added to `components/texts/stories/`
- These files are not managed through Google Sheets
- Create markdown files with frontmatter for panel titles

## Troubleshooting

### Invalid object references
- Verify object IDs are spelled exactly the same in both sheets
- Check for extra spaces or capitalization differences
- Make sure the objects sheet has all referenced objects

### Fetch script fails
- Verify the sheet is shared with "Anyone with the link" access
- Verify the sheet is published to the web
- Check that both URLs are correctly pasted in `_config.yml`
- Ensure CSV column headers match exactly

### Coordinates aren't working
- Verify values are between 0.000 and 1.000 for x and y
- Check that zoom values are positive numbers

## Next Steps

Once your Google Sheet is set up:
1. Edit your content directly in the sheet
2. Run `python3 scripts/fetch_google_sheets.py` to update your local CSVs
3. Build and view your changes locally

For more information, see the [main documentation](../README.md).
