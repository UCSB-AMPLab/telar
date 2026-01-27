"""
Image Processing

This module deals with Telar's extended image syntax and image path
validation. Standard markdown already converts `![alt](path)` into an
`<img>` tag, but Telar adds two features on top: size modifiers
(`{sm}`, `{md}`, `{lg}`, `{full}`) and automatic captions from the
line below the image. Because the markdown library doesn't know about
these extensions, this module runs first — it intercepts the raw text,
replaces image lines with fully formed `<figure>` HTML, and passes the
result onward for normal markdown conversion.

The main function is `process_images()`, which scans text line by line
looking for image declarations in the form `![alt](path){size}`. The
optional `{size}` modifier maps to CSS classes (`img-sm`, `img-md`, etc.)
that control display width in the story panel. If the next line after an
image is non-empty plain text, it is treated as a caption and wrapped in
a `<figcaption>`. The optional "caption: " prefix is stripped if present.
Relative image paths are automatically prepended with
`/components/images/`.

Path validation is handled by `validate_image_path()` and
`resolve_path_case_insensitive()`. These exist because Telar sites are
developed on macOS (case-insensitive filesystem) but often deployed on
Linux (case-sensitive). `resolve_path_case_insensitive()` tries three
fallbacks: the exact path, then lowercase filename only, then the entire
path lowercased. `validate_image_path()` adds a further legacy fallback
that tries swapping the file extension case (e.g., `.jpg` to `.JPG`).
External URLs (http/https) bypass validation entirely.

`get_image_dimensions()` reads image width and height, used by the
carousel widget to calculate aspect ratios and choose an appropriate
size class. It supports both local files (via Pillow) and remote URLs
(fetched with urllib). Failures are silent — dimension detection is
a nice-to-have, not a build blocker.

Version: v0.7.0-beta
"""

import re
from pathlib import Path
import urllib.request
import markdown
from PIL import Image as PILImage
from io import BytesIO


def process_images(text):
    """
    Process markdown images: handle sizes and captions.

    Must be called BEFORE markdown conversion (works on raw text).

    Syntax:
    - ![alt](path) - basic image
    - ![alt](path){size} - image with size (sm, md, lg, full)
    - Caption: line immediately following image becomes caption
    - Optional "caption: " prefix gets stripped

    Example:
        ![Portrait](image.jpg){md}
        Francisco Maldonado, encomendero of Fontibon

    Produces:
        <figure class="telar-image-figure">
          <img src="..." alt="Portrait" class="img-md">
          <figcaption class="telar-image-caption">Francisco Maldonado...</figcaption>
        </figure>
    """
    size_map = {
        'small': 'sm', 'medium': 'md', 'large': 'lg', 'full': 'full',
        'sm': 'sm', 'md': 'md', 'lg': 'lg'
    }

    lines = text.split('\n')
    result = []
    i = 0

    # Pattern for image with optional size
    img_pattern = r'^!\[([^\]]*)\]\(([^)]+)\)(?:\{(sm|small|md|medium|lg|large|full)\})?$'

    while i < len(lines):
        line = lines[i]
        match = re.match(img_pattern, line.strip(), re.IGNORECASE)

        if match:
            alt = match.group(1)
            src = match.group(2)
            size_input = match.group(3)

            # Determine size class
            if size_input:
                size_class = size_map.get(size_input.lower(), 'md')
                class_attr = f' class="img-{size_class}"'
            else:
                class_attr = ''

            # Prepend default path if relative
            if not src.startswith('/') and not src.startswith('http'):
                src = f'/components/images/{src}'

            # Check for caption on next line
            caption = None
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                # Caption exists if next line is non-empty and not another image/widget/blank
                if next_line.strip() and not next_line.strip().startswith('!') and not next_line.strip().startswith(':::'):
                    caption = next_line.strip()
                    # Strip "caption: " prefix if present
                    if caption.lower().startswith('caption:'):
                        caption = caption[8:].strip()
                    i += 1  # Skip the caption line

            # Build HTML
            img_tag = f'<img src="{src}" alt="{alt}"{class_attr}>'
            if caption:
                # Convert caption markdown to HTML (strip wrapping <p> tags)
                caption_html = markdown.markdown(caption)
                caption_html = re.sub(r'^<p>(.*)</p>$', r'\1', caption_html.strip())
                html = f'<figure class="telar-image-figure">{img_tag}<figcaption class="telar-image-caption">{caption_html}</figcaption></figure>'
            else:
                html = f'<figure class="telar-image-figure">{img_tag}</figure>'

            result.append(html)
        else:
            result.append(line)

        i += 1

    return '\n'.join(result)


def resolve_path_case_insensitive(base_dir, relative_path):
    """
    Resolve a path with case-insensitive fallback.

    Cascading fallback order:
    1. Try exact path as specified
    2. Try lowercase filename only (preserve directory case)
    3. Try lowercase entire path (directory + filename)

    This handles macOS vs Linux case sensitivity differences.

    Args:
        base_dir: Base directory (e.g., 'components/texts' or 'assets/images')
        relative_path: Path relative to base_dir

    Returns:
        Path object if found, None otherwise
    """
    full_path = Path(base_dir) / relative_path

    # 1. Try exact path
    if full_path.exists():
        return full_path

    # 2. Try lowercase filename only (preserve directory case)
    lowercase_filename = full_path.parent / full_path.name.lower()
    if lowercase_filename.exists():
        return lowercase_filename

    # 3. Try lowercase entire path
    lowercase_path = Path(base_dir) / relative_path.lower()
    if lowercase_path.exists():
        return lowercase_path

    return None


def validate_image_path(image_path, file_context):
    """
    Validate that an image exists at the expected path with case-insensitive fallback.
    Skips validation for external URLs (http:// or https://).

    Uses resolve_path_case_insensitive() for cascading fallback, plus legacy
    extension-only matching for backwards compatibility.

    Args:
        image_path: Path relative to assets/images/, or external URL
        file_context: Context string for error messages (e.g., markdown file name)

    Returns:
        tuple: (exists: bool, actual_path: str)
    """
    # Skip validation for external URLs
    if image_path.startswith('http://') or image_path.startswith('https://'):
        return (True, image_path)

    # Use centralized case-insensitive path resolution
    resolved = resolve_path_case_insensitive('assets/images', image_path)
    if resolved:
        return (True, str(resolved))

    # Legacy fallback: case-insensitive extension match only
    # e.g., if looking for image.jpg, also try image.JPG
    full_path = Path('assets/images') / image_path
    if full_path.suffix:
        # Try with uppercase extension
        path_with_upper = full_path.with_suffix(full_path.suffix.upper())
        if path_with_upper.exists():
            return (True, str(path_with_upper))

        # Try with lowercase extension
        path_with_lower = full_path.with_suffix(full_path.suffix.lower())
        if path_with_lower.exists():
            return (True, str(path_with_lower))

    return (False, str(full_path))


def get_image_dimensions(image_path):
    """
    Get dimensions of an image (local or remote).

    Args:
        image_path: Path relative to assets/images/, or external URL

    Returns:
        tuple: (width, height) or None if unable to determine
    """
    try:
        if image_path.startswith('http://') or image_path.startswith('https://'):
            # Fetch remote image
            request = urllib.request.Request(
                image_path,
                headers={'User-Agent': 'Telar/1.0'}
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                image_data = response.read()
                img = PILImage.open(BytesIO(image_data))
                return img.size  # Returns (width, height)
        else:
            # Load local image
            full_path = Path('assets/images') / image_path
            if full_path.exists():
                with PILImage.open(full_path) as img:
                    return img.size  # Returns (width, height)
            return None
    except Exception:
        # Silently fail - dimension detection is not critical
        return None
