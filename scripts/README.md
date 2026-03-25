# Telar Scripts

Python scripts for processing data and generating IIIF tiles.

## Installation

Install Python dependencies:

```bash
pip install -r scripts/requirements.txt
```

Or install individually:

```bash
pip install iiif Pillow pandas
```

## Data Architecture

Telar uses a **components-based architecture** where content is separated from structure:

- **`telar-content/`** - Source of truth for all content
  - `telar-content/objects/` - Source images and PDFs for IIIF processing
  - `telar-content/texts/` - Markdown files with long-form content
- **CSV files** - Structural data that references component files
  - Story structure (coordinates, objects, file references)
  - Object metadata
  - **Note:** No CSV for glossary - terms are sourced directly from markdown
- **`_data/`** - Generated JSON (intermediate format)
- **`_jekyll-files/`** - Auto-generated Jekyll collections
  - `_jekyll-files/_objects/` - Object collection files
  - `_jekyll-files/_stories/` - Story collection files
  - `_jekyll-files/_glossary/` - Glossary collection files (generated from components)

## IIIF Tile Generation

Generate IIIF tiles and manifests for local images.

### Basic Usage

1. Add images to `telar-content/objects/` directory:
   ```
   telar-content/objects/
   ├── painting-1.jpg
   ├── manuscript-2.tif
   └── map-3.png
   ```

2. Run the generator:
   ```bash
   python scripts/generate_iiif.py
   ```

3. Tiles are created in `iiif/objects/`:
   ```
   iiif/objects/
   ├── painting-1/
   │   ├── info.json
   │   ├── manifest.json
   │   └── [tile directories]
   ├── manuscript-2/
   │   ├── info.json
   │   ├── manifest.json
   │   └── [tile directories]
   └── map-3/
       ├── info.json
       ├── manifest.json
       └── [tile directories]
   ```

### Options

```bash
python scripts/generate_iiif.py --help
```

**Custom source directory:**
```bash
python scripts/generate_iiif.py --source-dir path/to/images
```

**Custom output directory:**
```bash
python scripts/generate_iiif.py --output-dir path/to/output
```

**Specify base URL:**
```bash
python scripts/generate_iiif.py --base-url https://mysite.github.io/project
```

### How It Works

1. **Tile Generation**: Creates IIIF Image API 3.0 tiles using libvips (with Python `iiif` library as fallback)
   - 512x512 pixel tiles
   - Multiple zoom levels
   - Outputs `info.json` with image metadata

2. **Manifest Creation**: Wraps tiles in IIIF Presentation API v3 manifest
   - Adds metadata from `_data/objects.json`
   - Compatible with Tify
   - Outputs `manifest.json`

3. **Object Linking**: Reference in your CSV/JSON:
   ```csv
   object_id,title,...,iiif_manifest
   painting-1,"My Painting",,  # Empty = use local tiles
   ```

### Supported Formats

- JPEG (`.jpg`, `.jpeg`)
- PNG (`.png`)
- TIFF (`.tif`, `.tiff`)

### Notes

- Object ID is derived from filename (without extension)
- Existing tiles are regenerated (deleted and recreated)
- Large images may take several minutes to process
- Default base URL is `http://localhost:4001/telar` (for local testing)

## Data Processing Scripts

### csv_to_json.py

Converts CSV data files to JSON format and embeds content from markdown files.

```bash
python scripts/csv_to_json.py
```

**How it works:**

1. **Reads CSV files** from `_data/` directory
2. **Detects file reference columns** (columns ending with `_file`)
3. **Loads markdown files** from `telar-content/texts/`
4. **Parses frontmatter** to extract title
5. **Embeds content** into JSON output

**File Reference Format:**

For story layers in CSV:
```csv
step,question,answer,layer1_file,layer2_file
1,"Question text","Answer text","story1/step1-layer1.md","story1/step1-layer2.md"
```

The script will:
- Look for `telar-content/texts/stories/story1/step1-layer1.md`
- Extract `title` from frontmatter
- Extract body content
- Create `layer1_title` and `layer1_text` columns in JSON

### generate_collections.py

Generates Jekyll collection markdown files from JSON data and component markdown files.

```bash
python scripts/generate_collections.py
```

**How it works:**

- **Objects**: Reads `_data/objects.json` and generates files in `_jekyll-files/_objects/`
- **Stories**: Reads `_data/project.csv` and generates files in `_jekyll-files/_stories/`
- **Glossary**: Reads markdown files directly from `telar-content/texts/glossary/` and generates files in `_jekyll-files/_glossary/`

**Glossary metadata (in component files):**
```markdown
---
term_id: colonial-period
title: "Colonial Period"
related_terms: encomienda,viceroyalty
---

The Colonial Period in the Americas began with...
```

**Required fields:**
- `term_id` - Unique identifier for lookups
- `title` - Term name
- `related_terms` - Comma-separated list (optional)

## JavaScript Bundling

The story viewer JavaScript is developed as modular files in `assets/js/telar-story/` and bundled into a single file for production. After modifying any file in that directory, rebuild the bundle:

```bash
npx esbuild assets/js/telar-story/main.js --bundle --outfile=assets/js/telar-story.js --format=iife --sourcemap
```

This produces `assets/js/telar-story.js` (the bundled file Jekyll serves) and a source map. Both files should be committed.

**Note:** If you skip this step after editing the modular sources, the site will serve the old bundle and your changes will not take effect.

## Workflow

Complete data processing workflow:

```bash
# 1. Edit content in telar-content/texts/
# 2. Update structure in CSV files (telar-content/spreadsheets/*.csv)
# 3. Convert CSV to JSON (embeds markdown content)
python3 scripts/csv_to_json.py

# 4. Generate Jekyll collection files
python3 scripts/generate_collections.py

# 5. Process audio objects (skip if no audio files)
python3 scripts/process_audio.py

# 6. Generate IIIF tiles for any new images
python3 scripts/generate_iiif.py

# 7. Bundle JavaScript (only if you modified files in assets/js/telar-story/)
npx esbuild assets/js/telar-story/main.js --bundle --outfile=assets/js/telar-story.js --format=iife --sourcemap

# 8. Build Jekyll site
bundle exec jekyll build
```

Or use the build script which runs all steps automatically:

```bash
python3 scripts/build_local_site.py
```

## GitHub Actions Integration

For automated IIIF generation on push:

1. Set `SITE_URL` environment variable in GitHub Actions
2. Add IIIF generation step before Jekyll build
3. Commit generated tiles to repository

Example workflow step:
```yaml
- name: Generate IIIF tiles
  run: |
    pip install -r scripts/requirements.txt
    python scripts/generate_iiif.py --base-url ${{ env.SITE_URL }}
```
