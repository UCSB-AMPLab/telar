# Objects

This folder contains the source files for your Telar objects — images and PDFs that are served via the IIIF protocol.

## Purpose

This folder stores **visual media** that will be displayed in your stories, including high-resolution images and multi-page PDF documents that are served via the IIIF (International Image Interoperability Framework) protocol.

## Structure

```
objects/
├── object-id-1.jpg     - High-res images for IIIF objects (used in stories or Objects page)
├── object-id-2.tif
├── document.pdf        - Multi-page PDF documents
├── logo.png            - Additional images (logos, team pictures, etc.)
└── ...
```

After running the IIIF generation script, tiled image pyramids will be created in `/iiif/objects/`.

## Workflow

1. **Add** - Place high-resolution images or PDFs in `components/objects/`
2. **Generate** - Run `python3 scripts/generate_iiif.py` to create IIIF tiles (this happens automatically on GitHub)
3. **Reference** - Use the object ID in your story CSV files
4. **View** - Objects are displayed via the Tify viewer with zoom and pan

## Supported Formats

- JPEG (.jpg, .jpeg)
- TIFF (.tif, .tiff)
- PNG (.png)
- WebP (.webp)
- HEIC (.heic, .heif)
- PDF (.pdf) - rendered to page images at build time

High-resolution images work best. The IIIF generation script creates multi-resolution tile pyramids that enable smooth zooming and panning.

## IIIF Generation

The `generate_iiif.py` script:
- Reads source files from `components/objects/`
- Generates tiled image pyramids in `/iiif/objects/{object-id}/`
- Creates `info.json` and `manifest.json` files for IIIF compatibility
- For PDFs: renders each page, tiles them individually, and creates multi-canvas manifests
- Enables deep-zoom functionality in the viewer

## File Naming

Source files should be named with a unique object ID that matches the `object_id` field in your objects CSV:

```
components/objects/example-map-1850.jpg
components/spreadsheets/objects.csv → object_id: example-map-1850
```
