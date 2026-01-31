#!/usr/bin/env python3
"""
Generate IIIF Image Tiles and Manifests

IIIF (International Image Interoperability Framework) is a standard for
serving high-resolution images over the web. Instead of loading one
enormous image file, the image is sliced into small tiles at multiple
zoom levels. The viewer (UniversalViewer, in Telar's case) requests
only the tiles visible on screen, enabling smooth deep-zoom into large
images without overwhelming the browser or network.

Telar supports two ways of serving images: external (the object's
source_url points to an existing IIIF server, e.g. a library's digital
collection — no tile generation needed) and self-hosted (the user
places image files in components/images/ and this script generates
static IIIF Level 0 tiles and a Presentation API v3 manifest for each
one).

The script reads objects.json to find which objects need tiles (those
without an external source URL), locates the source image for each,
and generates a directory of tile files plus a manifest.json that
UniversalViewer can load. It handles format conversion (PNG, HEIC,
WebP, TIFF to JPEG), EXIF orientation correction, and transparency
removal.

The --base-url flag is important: tiles must be generated with the
correct URL prefix so the manifest points to the right location. For
local development, use the localhost URL; for production, use the
site's public URL.

Version: v0.7.0-beta
"""

import os
import sys
import json
import shutil
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        from iiif.static import IIIFStatic
        from PIL import Image, ImageOps
    except ImportError as e:
        print("❌ Missing required dependencies!")
        print("\nPlease install:")
        print("  pip install iiif Pillow")
        print("\nOr use the provided requirements file:")
        print("  pip install -r requirements.txt")
        return False

    # Check for optional HEIC support
    try:
        from pillow_heif import register_heif_opener
    except ImportError:
        print("⚠️  pillow-heif not installed - HEIC/HEIF files will not be supported")
        print("   To enable HEIC support: pip install pillow-heif")
        print()

    return True

def get_base_url_from_config():
    """
    Read url and baseurl from _config.yml and combine them.

    Returns:
        Combined URL (e.g., "https://example.com/baseurl") or None if config can't be read
    """
    try:
        import yaml
        with open('_config.yml', 'r') as f:
            config = yaml.safe_load(f)

        url = config.get('url', '')
        baseurl = config.get('baseurl', '')

        if url:
            return url + baseurl
        return None
    except Exception as e:
        # Silently fail - caller will use fallback
        return None

def generate_iiif_for_image(image_path, output_dir, object_id, base_url):
    """
    Generate IIIF tiles for a single image

    Args:
        image_path: Path to source image
        output_dir: Output directory for tiles (parent of object_id directory)
        object_id: Identifier for this object
        base_url: Base URL for the site
    """
    from iiif.static import IIIFStatic
    from PIL import Image, ImageOps
    import tempfile

    # Register HEIF plugin for HEIC/HEIF support if available
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass  # HEIC support unavailable

    # Preprocess PNG images with transparency (RGBA) to RGB
    # because IIIF library saves as JPEG which doesn't support alpha
    processed_image_path = image_path
    temp_file = None

    try:
        img = Image.open(image_path)

        # Apply EXIF orientation if present (thanks to Tara for reporting)
        # This ensures portrait photos from phones/cameras display correctly
        img_before_exif = img
        img = ImageOps.exif_transpose(img)
        if img is None:
            # No EXIF orientation data, use original
            img = img_before_exif
        elif img != img_before_exif:
            print(f"  ↻ Applied EXIF orientation correction")

        # Check if image has EXIF orientation metadata (any value other than 1 = normal)
        exif = img_before_exif.getexif()
        has_exif_orientation = exif and 274 in exif and exif[274] != 1

        # Convert image to RGB if needed and create JPEG for IIIF processing
        needs_conversion = False
        converted_img = img

        # Handle transparency/alpha channel modes
        if img.mode in ['RGBA', 'LA']:
            print(f"  ⚠️  Converting {img.mode} to RGB (removing transparency)")
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[-1])  # Use alpha channel as mask
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
            temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            converted_img.save(temp_file.name, 'JPEG', quality=95)
            processed_image_path = Path(temp_file.name)
            temp_file.close()
    except Exception as e:
        print(f"  ⚠️  Error preprocessing image: {e}")
        # Continue with original image

    # Note: iiif library creates a subdirectory with the identifier name
    # We pass the parent directory, and it creates parent_dir/object_id/
    parent_dir = output_dir.parent
    tiles_dir = parent_dir / object_id

    try:
        # Create static generator
        # Note: iiif library appends the identifier to the prefix, so we use objects/ not objects/object_id/
        sg = IIIFStatic(
            dst=str(parent_dir),
            prefix=f"{base_url}/iiif/objects",  # iiif library will append /{identifier}
            tilesize=512,
            api_version='3.0'
        )

        # Generate tiles (this creates parent_dir/object_id/)
        sg.generate(src=str(processed_image_path), identifier=object_id)

        # Copy full-resolution image for UniversalViewer BEFORE cleaning up temp file
        # UniversalViewer expects a base image at the path declared in the manifest
        copy_base_image(processed_image_path, tiles_dir, object_id)
    finally:
        # Clean up temporary file if created
        if temp_file and Path(temp_file.name).exists():
            Path(temp_file.name).unlink()

    # Create manifest wrapper for UniversalViewer
    create_manifest(tiles_dir, object_id, image_path, base_url)

def copy_base_image(source_image_path, output_dir, object_id):
    """
    Copy the full-resolution image to the location expected by UniversalViewer

    UniversalViewer tries to load the base image at {object_id}/{object_id}.jpg
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

def create_manifest(output_dir, object_id, image_path, base_url):
    """
    Create IIIF Presentation API manifest for UniversalViewer

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

def load_objects_needing_tiles():
    """
    Load list of object_ids that need IIIF tiles generated from objects.json

    Returns:
        list: Object IDs that need self-hosted IIIF tiles (have no external source URL)
    """
    try:
        objects_json = Path('_data/objects.json')
        if not objects_json.exists():
            print("⚠️  objects.json not found - run csv_to_json.py first")
            return None

        with open(objects_json, 'r') as f:
            objects = json.load(f)

        # Find objects that need IIIF tiles (no external source URL/IIIF manifest)
        objects_needing_tiles = []
        for obj in objects:
            object_id = obj.get('object_id')

            # Check source_url first (v0.5.0+), fall back to iiif_manifest (v0.4.x)
            source_url = obj.get('source_url', '').strip()
            if not source_url:
                source_url = obj.get('iiif_manifest', '').strip()

            # Skip if no object_id
            if not object_id:
                continue

            # Need tiles if source URL is empty or not a URL
            if not source_url or not source_url.startswith('http'):
                objects_needing_tiles.append(object_id)

        return objects_needing_tiles

    except Exception as e:
        print(f"❌ Error loading objects.json: {e}")
        return None

def find_image_for_object(object_id, source_dir):
    """
    Find image file for a given object_id, checking multiple extensions (case-insensitive)

    Args:
        object_id: Object identifier
        source_dir: Directory to search for images

    Returns:
        Path object if found, None otherwise
    """
    source_path = Path(source_dir)
    # Priority order: Common formats first, then newer/specialized formats
    image_extensions = ['.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp', '.tif', '.tiff']

    for ext in image_extensions:
        # Check both lowercase and uppercase extensions
        for case_ext in [ext, ext.upper()]:
            image_path = source_path / f"{object_id}{case_ext}"
            if image_path.exists():
                return image_path

    return None

def generate_iiif_tiles(source_dir='components/images', output_dir='iiif/objects', base_url=None):
    """
    Generate IIIF tiles for objects listed in objects.json

    Args:
        source_dir: Directory containing source images (default: components/images)
        output_dir: Directory to output IIIF tiles and manifests (default: iiif/objects)
        base_url: Base URL for the site
    """
    if not check_dependencies():
        return False

    source_path = Path(source_dir)
    output_path = Path(output_dir)

    if not source_path.exists():
        print(f"❌ Source directory {source_dir} does not exist.")
        print(f"   Please create it and add images, or use --source-dir to specify a different location.")
        return False

    # Get base URL from config or environment
    # Priority: --base-url flag > _config.yml > SITE_URL env var > localhost default
    if not base_url:
        base_url = (get_base_url_from_config() or
                    os.environ.get('SITE_URL') or
                    'http://localhost:4000')

    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("IIIF Tile Generator for Telar")
    print("=" * 60)
    print(f"Source: {source_dir}")
    print(f"Output: {output_dir}")
    print(f"Base URL: {base_url}")

    # Show helpful message for local development
    if base_url and ('github.io' in base_url or base_url.startswith('https://')):
        # Extract baseurl from full URL for the hint
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        path = parsed.path if parsed.path != '/' else ''
        print(f"\nℹ️  Generating tiles for production URL")
        print(f"   For local development, use: --base-url http://localhost:4000{path}")

    print("=" * 60)
    print()

    # Load objects from objects.json (CSV-driven approach)
    print("📋 Loading objects from objects.json...")
    objects_needing_tiles = load_objects_needing_tiles()

    if objects_needing_tiles is None:
        print("❌ Could not load objects.json")
        return False

    if not objects_needing_tiles:
        print("ℹ️  No objects need IIIF tiles (all use external manifests)")
        return True

    print(f"✓ Found {len(objects_needing_tiles)} objects needing tiles\n")

    # Process each object
    processed_count = 0
    skipped_count = 0

    for i, object_id in enumerate(objects_needing_tiles, 1):
        print(f"[{i}/{len(objects_needing_tiles)}] Processing {object_id}...")

        # Find image file for this object
        image_file = find_image_for_object(object_id, source_dir)

        if not image_file:
            print(f"  ⚠️  No image file found for {object_id}")
            print(f"      Checked: {object_id}.jpg, .jpeg, .png, .heic, .heif, .webp, .tif, .tiff (case-insensitive)")
            skipped_count += 1
            print()
            continue

        print(f"  Found: {image_file.name}")

        # Output directory for this object
        object_output = output_path / object_id

        try:
            # Remove existing output if present
            if object_output.exists():
                shutil.rmtree(object_output)

            object_output.mkdir(parents=True, exist_ok=True)

            # Generate IIIF tiles and manifest
            generate_iiif_for_image(image_file, object_output, object_id, base_url)

            print(f"  ✓ Generated tiles for {object_id}")
            processed_count += 1
            print()

        except Exception as e:
            print(f"  ❌ Error processing {image_file.name}: {e}")
            import traceback
            traceback.print_exc()
            skipped_count += 1
            print()
            continue

    print("=" * 60)
    print("✓ IIIF generation complete!")
    print(f"  Processed: {processed_count} objects")
    if skipped_count > 0:
        print(f"  Skipped: {skipped_count} objects (missing images or errors)")
    print(f"  Output directory: {output_dir}")
    print("=" * 60)
    return True

def main():
    """Main generation process"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate IIIF tiles and manifests for Telar objects (CSV-driven)'
    )
    parser.add_argument(
        '--source-dir',
        default='components/images',
        help='Source directory containing images (default: components/images)'
    )
    parser.add_argument(
        '--output-dir',
        default='iiif/objects',
        help='Output directory for IIIF tiles (default: iiif/objects)'
    )
    parser.add_argument(
        '--base-url',
        help='Base URL for the site (default: from _config.yml or http://localhost:4000)'
    )

    args = parser.parse_args()

    success = generate_iiif_tiles(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        base_url=args.base_url
    )

    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
