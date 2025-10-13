# Images

This folder contains the image files and IIIF-generated assets for your Telar site.

## Purpose

This folder stores **visual media** that will be displayed in your stories, including high-resolution images that are served via the IIIF (International Image Interoperability Framework) protocol.

## Structure

```
images/
└── objects/            - Source images for IIIF objects
    ├── object-id-1.jpg
    ├── object-id-2.tif
    └── ...
```

After running the IIIF generation script, additional folders will be created in `/iiif/objects/` with tiled image pyramids.

## Workflow

1. **Add** - Place high-resolution images in `components/images/objects/`
2. **Generate** - Run `python3 scripts/generate_iiif.py` to create IIIF tiles
3. **Reference** - Use the object ID in your story CSV files
4. **View** - Images are displayed via the UniversalViewer with zoom and pan

## Supported Formats

- JPEG (.jpg, .jpeg)
- TIFF (.tif, .tiff)
- PNG (.png)

High-resolution images work best. The IIIF generation script creates multi-resolution tile pyramids that enable smooth zooming and panning.

## IIIF Generation

The `generate_iiif.py` script:
- Reads images from `components/images/objects/`
- Generates tiled image pyramids in `/iiif/objects/{object-id}/`
- Creates `info.json` and `manifest.json` files for IIIF compatibility
- Enables deep-zoom functionality in the viewer

## File Naming

Image files should be named with a unique object ID that matches the `object_id` field in your objects CSV:

```
components/images/objects/example-map-1850.jpg
components/structures/objects.csv → object_id: example-map-1850
```

## Why Images?

This folder is called "images" because it contains the visual media files - the pictures, maps, documents, and artifacts that form the visual core of your digital exhibition.
