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
Relative image paths are resolved to `<baseurl>/telar-content/objects/`,
the site's configured baseurl included. The HTML this module writes reaches
the browser unrewritten on a glossary page, in the glossary panel (which
fetches that page) and on a user page, so the path has to be one the
browser can fetch as written; a site served under a baseurl, as every GitHub
Pages project site is, otherwise asks the host root for the file.

A carousel image can live anywhere in the site. `locate_image()` decides
which file an `image:` value names: a path with a folder in it is read from
the site root, and a bare file name is looked for in `assets/images/` and
then `telar-content/objects/`. `validate_image_path()` and
`get_image_dimensions()` both go through it, so the file checked and
measured is the file the carousel publishes. Lookups allow for letter case
because Telar sites are developed on macOS (case-insensitive filesystem)
but often deployed on Linux (case-sensitive):
`resolve_path_case_insensitive()` tries the exact path, then the lowercase
file name, then the whole path lowercased, and the extension is also tried
in upper and lower case (`.jpg` against `.JPG`). External URLs (http/https)
bypass validation entirely.

`get_image_dimensions()` reads image width and height, used by the
carousel widget to calculate aspect ratios and choose an appropriate
size class. It supports both local files (via Pillow) and remote URLs
(fetched with urllib). Failures are silent — dimension detection is
a nice-to-have, not a build blocker.

Version: v1.8.0
"""

from html import escape as html_escape
import re
from pathlib import Path
import urllib.request
from PIL import Image as PILImage
from io import BytesIO
from telar.latex import convert_markdown


def _unwrap_paragraph(rendered_html):
    """Drop the <p> wrapper Python Markdown puts around a one-line caption.

    Runs as `convert_markdown`'s post-processing step: anything that
    rewrites the converted HTML has to see the maths as a placeholder.
    """
    return re.sub(r'^<p>(.*)</p>$', r'\1', rendered_html.strip())


def process_images(text, base_url=None):
    """
    Process markdown images: handle sizes and captions.

    Must be called BEFORE markdown conversion (works on raw text).

    `base_url` is the site's baseurl with no trailing slash; it defaults to
    the one in _config.yml. A path starting with `/` or `http` is the
    author's and is written as given.

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
    if base_url is None:
        # Imported here: telar.widgets imports this module at load time.
        from telar.widgets import site_base_url
        base_url = site_base_url()

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

            if not src.startswith('/') and not src.startswith('http'):
                src = f'{base_url}/telar-content/objects/{src}'

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
            img_tag = f'<img src="{html_escape(src, quote=True)}" alt="{html_escape(alt, quote=True)}"{class_attr}>'
            if caption:
                # Convert caption markdown to HTML (strip wrapping <p> tags)
                caption_html = convert_markdown(
                    caption, post_process=_unwrap_paragraph)
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
        base_dir: Base directory (e.g., 'telar-content/texts' or 'assets/images')
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


# Where a carousel image given as a bare file name is looked for, in order.
BARE_IMAGE_FOLDERS = ('assets/images', 'telar-content/objects')


def _is_url(image_path):
    return image_path.startswith('http://') or image_path.startswith('https://')


def _find_file(base_dir, relative_path):
    """The file at base_dir/relative_path, allowing for letter case, or None.

    Tries `resolve_path_case_insensitive()`, then the extension in upper and
    in lower case (`.jpg` against `.JPG`). A directory is not a file, so an
    empty name finds nothing.
    """
    resolved = resolve_path_case_insensitive(base_dir, relative_path)
    if resolved and resolved.is_file():
        return resolved
    full_path = Path(base_dir) / relative_path
    if full_path.suffix:
        for candidate in (full_path.with_suffix(full_path.suffix.upper()),
                          full_path.with_suffix(full_path.suffix.lower())):
            if candidate.is_file():
                return candidate
    return None


def locate_image(image_path, base_url=None):
    """Where a carousel image lives, as a path from the site root.

    - A path with a folder in it (`telar-content/objects/x.jpg`) is read
      from the site root. A leading `/` means the same root; if such a path
      already begins with the site's baseurl and the file is found under the
      rest of it, the baseurl is not counted twice. When the site root has
      no such file, the path is tried under each of BARE_IMAGE_FOLDERS, so a
      subfolder written relative to assets/images/ (`historia/x.jpg`), as
      carousels were written before, still resolves.
    - A bare file name is looked for in each of BARE_IMAGE_FOLDERS in turn,
      and the first folder holding it wins. When none does, the answer is
      the first folder, which is where a carousel image was always expected.

    The path returned is the file found on disk, in its own letter case, so
    what is published, validated and measured is one file. The caller
    handles URLs; this is for files in the site.

    Args:
        image_path: The carousel item's `image:` value
        base_url: The site's baseurl; defaults to the one in _config.yml

    Returns:
        tuple: (site_path: str with no leading slash, found: bool)
    """
    if '/' not in image_path:
        for folder in BARE_IMAGE_FOLDERS:
            found = _find_file(folder, image_path)
            if found:
                return found.as_posix(), True
        return f'{BARE_IMAGE_FOLDERS[0]}/{image_path}', False

    relative = image_path.lstrip('/')
    if image_path.startswith('/'):
        if base_url is None:
            # Imported here: telar.widgets imports this module at load time.
            from telar.widgets import site_base_url
            base_url = site_base_url()
        if base_url and image_path.startswith(base_url + '/'):
            without_base = image_path[len(base_url):].lstrip('/')
            if not _find_file('.', relative) and _find_file('.', without_base):
                relative = without_base
    found = _find_file('.', relative)
    if not found:
        for folder in BARE_IMAGE_FOLDERS:
            found = _find_file(folder, relative)
            if found:
                break
    if found:
        return found.as_posix(), True
    return relative, False


def validate_image_path(image_path, file_context):
    """
    Validate that a carousel image exists where `locate_image()` puts it.
    Skips validation for external URLs (http:// or https://).

    Args:
        image_path: The carousel item's `image:` value, or an external URL
        file_context: Context string for error messages (e.g., markdown file name)

    Returns:
        tuple: (exists: bool, path: str) — the path from the site root that
        was found, or the one the published image points at when nothing was
    """
    if _is_url(image_path):
        return (True, image_path)
    site_path, found = locate_image(image_path)
    return (found, site_path)


def get_image_dimensions(image_path):
    """
    Get dimensions of an image (local or remote).

    A local image is read from the file `locate_image()` finds, the one
    the carousel publishes.

    Args:
        image_path: The carousel item's `image:` value, or external URL

    Returns:
        tuple: (width, height) or None if unable to determine
    """
    try:
        if _is_url(image_path):
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
            site_path, found = locate_image(image_path)
            if found:
                with PILImage.open(site_path) as img:
                    return img.size  # Returns (width, height)
            return None
    except Exception:
        # Silently fail - dimension detection is not critical
        return None
