#!/usr/bin/env python3
"""
IIIF Shared Utilities for Tile Generation and Manifest Creation

IIIF tile generation in Telar has two entry points: generate_iiif.py
handles regular images (one image per object), and process_pdf.py
handles PDF documents (one image per page, many pages per object).
Both need the same core operations — detecting the tile backend,
preprocessing images into clean JPEGs, running libvips to slice them
into tiles, patching the resulting info.json, generating the full-size
canonical image, copying a base image for the viewer, creating IIIF
Presentation v3 manifests, and loading object metadata from
objects.json.

This module holds all of those shared functions. It was extracted from
generate_iiif.py when PDF support was added, so that the two scripts
could share the same tile-generation and manifest-creation code
without duplicating it.

None of these functions are meant to be run directly. They are
imported by the two entry-point scripts.

Version: v0.9.2-beta
"""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

def detect_tile_backend():
    """Detect available IIIF tile generation backend.

    Prefers libvips (28x faster) over the Python iiif library.
    Returns 'libvips', 'iiif', or None.
    """
    if shutil.which('vips'):
        return 'libvips'
    try:
        from iiif.static import IIIFStatic
        return 'iiif'
    except ImportError:
        return None


def check_dependencies():
    """Check if required dependencies are installed.

    Returns:
        Backend name ('libvips' or 'iiif') if ready, None if not.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        print("❌ Missing required dependency: Pillow")
        print("   pip install Pillow")
        return None

    backend = detect_tile_backend()
    if backend is None:
        print("❌ No IIIF tile generation backend found!")
        print("\nInstall one of:")
        print("  libvips (recommended): brew install vips  (macOS)")
        print("                         sudo apt-get install libvips-dev  (Linux)")
        print("  Python iiif library:   pip install iiif")
        return None

    # Check for optional HEIC support
    try:
        from pillow_heif import register_heif_opener
    except ImportError:
        print("⚠️  pillow-heif not installed - HEIC/HEIF files will not be supported")
        print("   To enable HEIC support: pip install pillow-heif")
        print()

    # Check for optional PDF support
    try:
        import fitz
    except ImportError:
        print("⚠️  PyMuPDF not installed - PDF files will not be supported")
        print("   To enable PDF support: pip install PyMuPDF")
        print()

    return backend


# ---------------------------------------------------------------------------
# Image preprocessing (shared by both backends)
# ---------------------------------------------------------------------------

def preprocess_image(image_path):
    """Preprocess an image for IIIF tile generation.

    Handles EXIF orientation, transparency removal, palette mode conversion,
    and format conversion to JPEG. Both backends need a clean JPEG input.

    Args:
        image_path: Path to source image

    Returns:
        (processed_path, temp_file_path_or_None)
        If a temp file was created, caller must delete it after use.
    """
    from PIL import Image, ImageOps

    # Register HEIF plugin if available
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass

    processed_path = image_path
    temp_path = None

    try:
        img = Image.open(image_path)

        # Apply EXIF orientation if present
        img_before_exif = img
        img = ImageOps.exif_transpose(img)
        if img is None:
            img = img_before_exif
        elif img != img_before_exif:
            print(f"  ↻ Applied EXIF orientation correction")

        # Check if image has EXIF orientation metadata (any value other than 1 = normal)
        exif = img_before_exif.getexif()
        has_exif_orientation = exif and 274 in exif and exif[274] != 1

        # Convert image to RGB if needed
        needs_conversion = False
        converted_img = img

        # Handle transparency/alpha channel modes
        if img.mode in ['RGBA', 'LA']:
            print(f"  ⚠️  Converting {img.mode} to RGB (removing transparency)")
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[-1])
            converted_img = rgb_img
            needs_conversion = True

        # Handle palette mode (GIF, some PNGs)
        elif img.mode == 'P':
            print(f"  ⚠️  Converting palette mode to RGB")
            converted_img = img.convert('RGB')
            needs_conversion = True

        # Handle other uncommon modes
        elif img.mode not in ['RGB', 'L']:
            print(f"  ⚠️  Converting {img.mode} mode to RGB")
            converted_img = img.convert('RGB')
            needs_conversion = True

        # Check if we need to convert to JPEG (for non-JPEG formats)
        # OR if EXIF orientation metadata present (need to save the transposed image)
        file_ext = image_path.suffix.lower()
        if has_exif_orientation or needs_conversion or file_ext not in ['.jpg', '.jpeg']:
            # Show format-specific message
            if has_exif_orientation and file_ext in ['.jpg', '.jpeg'] and not needs_conversion:
                print(f"  💾 Saving rotated image for IIIF processing")
            elif file_ext in ['.heic', '.heif']:
                print(f"  ⚠️  Converting HEIC to JPEG for IIIF processing")
            elif file_ext == '.webp':
                print(f"  ⚠️  Converting WebP to JPEG for IIIF processing")
            elif file_ext in ['.tif', '.tiff']:
                print(f"  ⚠️  Converting TIFF to JPEG for IIIF processing")
            elif file_ext == '.png' and not needs_conversion:
                print(f"  ⚠️  Converting PNG to JPEG for IIIF processing")

            # Save to temporary JPEG file
            tf = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            converted_img.save(tf.name, 'JPEG', quality=95)
            processed_path = Path(tf.name)
            temp_path = tf.name
            tf.close()
    except Exception as e:
        print(f"  ⚠️  Error preprocessing image: {e}")

    return processed_path, temp_path


# ---------------------------------------------------------------------------
# libvips backend
# ---------------------------------------------------------------------------

def generate_tiles_libvips(processed_path, tiles_dir, object_id, base_url):
    """Generate IIIF tiles using libvips (vips dzsave).

    Args:
        processed_path: Path to preprocessed JPEG
        tiles_dir: Output directory for this object's tiles
        object_id: Object identifier
        base_url: Base URL for the site
    """
    parent_dir = tiles_dir.parent

    # vips dzsave creates output at the specified path
    cmd = [
        'vips', 'dzsave',
        str(processed_path),
        str(parent_dir / object_id),
        '--layout', 'iiif3',
        '--tile-size', '512',
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"vips dzsave failed: {result.stderr}")

    # Clean up vips-properties.xml (created alongside the output directory)
    vips_props = parent_dir / 'vips-properties.xml'
    if vips_props.exists():
        vips_props.unlink()

    # Post-process: patch info.json and generate full/max image
    patch_info_json(tiles_dir, object_id, base_url)
    generate_full_max(processed_path, tiles_dir)


def patch_info_json(tiles_dir, object_id, base_url):
    """Patch libvips-generated info.json with correct id and sizes.

    libvips writes a placeholder id and omits the sizes array.
    We fix the id to the production URL and populate sizes by
    scanning the full/ directory for available thumbnail files.
    """
    info_path = tiles_dir / 'info.json'
    if not info_path.exists():
        return

    with open(info_path, 'r') as f:
        info = json.load(f)

    # Set correct id URL
    info['id'] = f"{base_url}/iiif/objects/{object_id}"

    # Populate sizes array from full/ directory.
    # libvips generates both "w,h" and "w," (width-only) directories;
    # we need to scan for both patterns so the sizes array is complete.
    full_dir = tiles_dir / 'full'
    img_w = info.get('width', 0)
    img_h = info.get('height', 0)
    sizes = []
    if full_dir.exists():
        for entry in full_dir.iterdir():
            if not entry.is_dir() or entry.name == 'max':
                continue
            # "w,h" — both dimensions explicit
            match = re.match(r'^(\d+),(\d+)$', entry.name)
            if match:
                sizes.append({
                    'width': int(match.group(1)),
                    'height': int(match.group(2)),
                })
                continue
            # "w," — width-only, compute height from aspect ratio
            match = re.match(r'^(\d+),$', entry.name)
            if match and img_w and img_h:
                sw = int(match.group(1))
                sh = int(round(img_h * sw / img_w))
                sizes.append({'width': sw, 'height': sh})

    # Fallback: if no thumbnail directories found (libvips <8.17 doesn't
    # create them), compute a single size from the image dimensions
    # already present in info.json.
    if not sizes:
        if img_w and img_h:
            sizes.append({'width': img_w, 'height': img_h})

    if sizes:
        sizes.sort(key=lambda s: s['width'])
        info['sizes'] = sizes

    # Ensure scaleFactors is never empty — OpenSeadragon (inside Tify)
    # crashes with RangeError when it encounters an empty array. This
    # happens for images smaller than the tile size (512px), where libvips
    # produces no downscale levels.
    tiles = info.get('tiles', [])
    for tile in tiles:
        if not tile.get('scaleFactors'):
            tile['scaleFactors'] = [1]
    if tiles:
        info['tiles'] = tiles

    # Add extraFormats and extraQualities for spec compliance
    info['extraFormats'] = ['jpg']
    info['extraQualities'] = ['default']

    with open(info_path, 'w') as f:
        json.dump(info, f, indent=2)


def generate_full_max(processed_path, tiles_dir):
    """Generate the full/max/0/default.jpg image.

    IIIF 3.0 viewers request the full-size image at this canonical path.
    libvips doesn't generate it, so we create it from the preprocessed source.
    """
    from PIL import Image

    max_dir = tiles_dir / 'full' / 'max' / '0'
    max_dir.mkdir(parents=True, exist_ok=True)
    dest = max_dir / 'default.jpg'

    img = Image.open(processed_path)
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    img.save(dest, 'JPEG', quality=95)

    # Also create full/{w},{h}/0/default.jpg for Level 0 thumbnail support.
    # Older libvips versions (<8.17) don't create this directory, but the
    # homepage thumbnail JS constructs URLs using the {w},{h} path.
    w, h = img.size
    wh_dir = tiles_dir / 'full' / f'{w},{h}' / '0'
    if not wh_dir.exists():
        wh_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, wh_dir / 'default.jpg')

    # Generate width-only thumbnails for sizes that IIIF viewers request
    # but that don't exist in the static Level 0 tile pyramid. TIFY v0.35
    # always requests full/96,/0/default.jpg for its page thumbnail
    # regardless of the service profile level, causing 404s on static
    # tiles that break rendering on Windows browsers.
    VIEWER_THUMB_WIDTHS = [96]
    for tw in VIEWER_THUMB_WIDTHS:
        if tw >= w:
            continue
        th = int(round(h * tw / w))
        thumb_dir = tiles_dir / 'full' / f'{tw},' / '0'
        if not thumb_dir.exists():
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumb = img.resize((tw, th), Image.LANCZOS)
            thumb.save(thumb_dir / 'default.jpg', 'JPEG', quality=85)



# ---------------------------------------------------------------------------
# Shared post-generation
# ---------------------------------------------------------------------------

def copy_base_image(source_image_path, output_dir, object_id):
    """
    Copy the full-resolution image to the location expected by the viewer.

    The viewer tries to load the base image at {object_id}/{object_id}.jpg
    which is declared in the manifest body.id. IIIF Level 0 doesn't automatically
    create this file, so we copy it manually.

    Args:
        source_image_path: Path to the processed source image
        output_dir: Output directory for IIIF tiles
        object_id: Object identifier
    """
    from PIL import Image, ImageOps

    dest_path = output_dir / f"{object_id}.jpg"

    try:
        # Open and save as JPEG (in case source was PNG or other format)
        img = Image.open(source_image_path)

        # Apply EXIF orientation if present
        img_before_exif = img
        img = ImageOps.exif_transpose(img)
        if img is None:
            # No EXIF orientation data, use original
            img = img_before_exif

        if img.mode in ('RGBA', 'LA', 'P'):
            # Convert to RGB if necessary
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                rgb_img.paste(img, mask=img.split()[-1])  # Use alpha channel as mask
            img = rgb_img

        img.save(dest_path, 'JPEG', quality=95)
        print(f"  ✓ Copied base image to {object_id}.jpg")
    except Exception as e:
        print(f"  ⚠️  Error copying base image: {e}")


def create_single_canvas_manifest(output_dir, object_id, image_path, base_url):
    """
    Create IIIF Presentation API v3 single-canvas manifest.

    Args:
        output_dir: Directory containing info.json
        object_id: Object identifier
        image_path: Original image path
        base_url: Base URL for the site
    """
    from PIL import Image

    # Read info.json to get image dimensions
    info_path = output_dir / 'info.json'
    if not info_path.exists():
        print(f"  ⚠️  info.json not found, skipping manifest creation")
        return

    with open(info_path, 'r') as f:
        info = json.load(f)

    width = info.get('width', 0)
    height = info.get('height', 0)

    # Load metadata from objects.json if available
    metadata = load_object_metadata(object_id)

    # Create IIIF Presentation v3 manifest
    manifest = {
        "@context": "http://iiif.io/api/presentation/3/context.json",
        "id": f"{base_url}/iiif/objects/{object_id}/manifest.json",
        "type": "Manifest",
        "label": {
            "en": [metadata.get('title', object_id)]
        },
        "metadata": [],
        "summary": {
            "en": [metadata.get('description', '')]
        } if metadata.get('description') else None,
        "items": [
            {
                "id": f"{base_url}/iiif/objects/{object_id}/canvas",
                "type": "Canvas",
                "label": {
                    "en": [metadata.get('title', object_id)]
                },
                "height": height,
                "width": width,
                "items": [
                    {
                        "id": f"{base_url}/iiif/objects/{object_id}/page",
                        "type": "AnnotationPage",
                        "items": [
                            {
                                "id": f"{base_url}/iiif/objects/{object_id}/annotation",
                                "type": "Annotation",
                                "motivation": "painting",
                                "body": {
                                    "id": f"{base_url}/iiif/objects/{object_id}/{object_id}.jpg",
                                    "type": "Image",
                                    "format": "image/jpeg",
                                    "height": height,
                                    "width": width,
                                    "service": [
                                        {
                                            "id": f"{base_url}/iiif/objects/{object_id}",
                                            "type": "ImageService3",
                                            "profile": "level0"
                                        }
                                    ]
                                },
                                "target": f"{base_url}/iiif/objects/{object_id}/canvas"
                            }
                        ]
                    }
                ]
            }
        ]
    }

    # Add metadata fields
    if metadata.get('creator'):
        manifest['metadata'].append({
            "label": {"en": ["Creator"]},
            "value": {"en": [metadata['creator']]}
        })
    if metadata.get('period'):
        manifest['metadata'].append({
            "label": {"en": ["Period"]},
            "value": {"en": [metadata['period']]}
        })

    # Write manifest
    manifest_path = output_dir / 'manifest.json'
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"  ✓ Created manifest.json")


def load_object_metadata(object_id):
    """Load metadata for an object from objects.json"""
    try:
        objects_json = Path('_data/objects.json')
        if objects_json.exists():
            with open(objects_json, 'r') as f:
                objects = json.load(f)
                for obj in objects:
                    if obj.get('object_id') == object_id:
                        return obj
    except Exception as e:
        print(f"  ⚠️  Could not load metadata: {e}")
    return {}
