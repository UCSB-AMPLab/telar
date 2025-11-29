# Components Directory

This directory contains all the **source components** used to build your Telar site - images, text content, data structures, and other media files.

## Directory Structure

### images/

High-resolution images (maps, photographs, documents, artifacts) displayed using IIIF (International Image Interoperability Framework).

- **Supported formats:** JPG, PNG, TIFF, WebP, HEIC (v0.5.0+)
- **Processing:** Telar automatically generates IIIF tiles for deep-zoom viewing
- **Usage:** Reference images by filename in `objects.csv`
- See [images/README.md](images/README.md) for details

### structures/

CSV files that define your site's organizational structure and content.

- **project.csv** - Site-wide settings and configuration
- **objects.csv** - Catalog of visual objects (images, IIIF manifests)
- **story-N.csv** / **chapter-N.csv** - Story navigation and step structure

These CSV files are processed by `scripts/csv_to_json.py` to generate JSON data in `_data/`.

See [structures/README.md](structures/README.md) for details

### texts/

Markdown files containing narrative text, annotations, and educational content.

- **stories/** - Story step panels and educational content
- **pages/** - Static page content
- **Supports:** Full GitHub-flavored Markdown, HTML embeds, image references

Markdown files are referenced in story CSV files and embedded into the site during build.

See [texts/README.md](texts/README.md) for details

### pdfs/

**Status:** Coming in v0.6.0

Multi-page PDF documents displayed using IIIF Presentation API 3.0.

**Planned features:**
- Multi-page IIIF support with page navigation
- Page-specific zoom and coordinates
- Automatic IIIF manifest generation

See [pdfs/README.md](pdfs/README.md)

### audio/

**Status:** Coming in v0.7.0

Audio files (oral histories, soundscapes, music, field recordings) embedded in story steps.

**Planned features:**
- HTML5 audio player with custom styling
- Waveform visualization
- Time-coded navigation
- Transcript synchronization

See [audio/README.md](audio/README.md)

### 3d-models/

**Status:** Coming in v0.8.0

3D model files (archaeological artifacts, architectural models, sculptures) displayed in interactive viewers.

**Planned features:**
- Interactive 3D viewer with rotation and zoom
- Model annotations and hotspots
- Multiple format support (glTF, OBJ, PLY, STL)
- AR/VR compatibility

See [3d-models/README.md](3d-models/README.md)

## Workflow Overview

1. **Add content** - Place images in `images/`, text in `texts/`, update CSVs in `structures/`
2. **Process data** - Run `python3 scripts/csv_to_json.py` to convert CSV to JSON
3. **Generate IIIF tiles** - Run `python3 scripts/generate_iiif.py` to create image tiles (automatic on GitHub)
4. **Build site** - Run `bundle exec jekyll build` to generate the final site

On GitHub, steps 2-4 happen automatically via GitHub Actions whenever you push changes.

## Questions?

- **Report issues:** [GitHub Issues](https://github.com/UCSB-AMPLab/telar/issues)
- **Documentation:** [https://telar.org/docs](https://telar.org/docs)
