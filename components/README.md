# Components Directory

This directory contains all the **source components** used to build your Telar site - objects (images and documents), text content, data spreadsheets, and other media files.

## Directory Structure

### objects/

High-resolution images and PDF documents displayed using IIIF (International Image Interoperability Framework).

- **Supported formats:** JPG, PNG, TIFF, WebP, HEIC, PDF
- **Processing:** Telar automatically generates IIIF tiles for deep-zoom viewing; PDFs are rendered to page images at build time
- **Usage:** Reference objects by filename (without extension) in `objects.csv`
- See [objects/README.md](objects/README.md) for details

### spreadsheets/

CSV files that define your site's organizational structure and content.

- **project.csv** - Site-wide settings and configuration
- **objects.csv** - Catalog of visual objects (images, IIIF manifests)
- **story-N.csv** / **chapter-N.csv** - Story navigation and step structure

These CSV files are processed by `scripts/csv_to_json.py` to generate JSON data in `_data/`.

See [spreadsheets/README.md](spreadsheets/README.md) for details

### texts/

Markdown files containing narrative text, annotations, and educational content.

- **stories/** - Story step panels and educational content
- **pages/** - Static page content
- **Supports:** Full GitHub-flavored Markdown, HTML embeds, image references

Markdown files are referenced in story CSV files and embedded into the site during build.

See [texts/README.md](texts/README.md) for details

### audio/

**Status:** Planned

Audio files (oral histories, soundscapes, music, field recordings) embedded in story steps.

See [audio/README.md](audio/README.md)

### 3d-models/

**Status:** Planned

3D model files (archaeological artifacts, architectural models, sculptures) displayed in interactive viewers.

See [3d-models/README.md](3d-models/README.md)

## Workflow Overview

1. **Add content** - Place images/PDFs in `objects/`, text in `texts/`, update CSVs in `spreadsheets/`
2. **Process data** - Run `python3 scripts/csv_to_json.py` to convert CSV to JSON
3. **Generate IIIF tiles** - Run `python3 scripts/generate_iiif.py` to create image tiles (automatic on GitHub)
4. **Build site** - Run `bundle exec jekyll build` to generate the final site

On GitHub, steps 2-4 happen automatically via GitHub Actions whenever you push changes.

## Questions?

- **Report issues:** [GitHub Issues](https://github.com/UCSB-AMPLab/telar/issues)
- **Documentation:** [https://telar.org/docs](https://telar.org/docs)
