#!/usr/bin/env python3
"""
Generate Jekyll Collection Markdown Files from JSON Data

This script is the bridge between Telar's JSON data and Jekyll's
content system. Jekyll requires each page to be a markdown file with
YAML frontmatter in a specific directory (called a "collection"). This
script reads the JSON files produced by csv_to_json.py and generates
those markdown files.

It creates four types of collection files:

- Objects (_jekyll-files/_objects/): One file per exhibition object,
  with metadata like title, creator, period, and IIIF manifest URL in
  the frontmatter.
- Stories (_jekyll-files/_stories/): One file per story, linking to its
  JSON data file, setting the story layout, and declaring the permalink it
  renders at. The same identifier-to-URL mapping is recorded in the story
  page manifest (telar/story_pages.py) so the post-build encryption step
  can find each protected story's page without predicting its URL.
- Glossary (_jekyll-files/_glossary/): Terms from both user markdown
  files (telar-content/texts/glossary/) and demo content, with glossary-
  to-glossary link processing.
- Pages (_jekyll-files/_pages/): User-authored pages from
  telar-content/texts/pages/, processed through the widget and glossary
  pipeline.

Glossary generation is in telar/glossary_pages.py and page generation in
telar/pages.py; this script runs them in order with the rest.

It also derives the theme on-colours (telar/theme_colours.py) into
_data/telar-build/, which the stylesheet reads. That step belongs to the
themes, not to any collection, so it runs whatever the feature flags skip.

The script respects development feature flags (skip_stories,
skip_collections) from _config.yml, which allow developers to
temporarily suppress certain collections during development.
Legacy names (hide_stories, hide_collections) are also supported.

Version: v1.8.0
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

# Import processing functions from telar package
from telar.core import SHEET_REFUSED_EXIT
from telar.csv_utils import (OBJECT_FIELDS, ColumnCollisionError,
                             ReservedColumnError)
from telar.latex import has_latex
from telar.media_type import detect_media_type, AUDIO_EXTENSIONS
from telar import theme_colours
from telar.story_pages import (
    ManifestError, build_manifest, remove_manifest, stories_permalink,
    write_manifest,
)
from telar.frontmatter import _as_text, _frontmatter_block
from telar.glossary_pages import generate_glossary
from telar.pages import check_title_keys, generate_pages

# Defined in the modules above, and importable from here too, because tests
# reach them through this script.
from telar.frontmatter import FRONTMATTER_PATTERN  # noqa: F401
from telar.glossary_pages import (  # noqa: F401
    _generate_glossary_from_csv, _generate_glossary_from_markdown,
)
from telar.pages import (  # noqa: F401
    GENERATED_PAGE_IGNORED_KEYS, TITLE_KEY_SECTION, TITLE_KEY_SOURCES,
    _parse_page_frontmatter, _strip_generated_page_keys,
)

# Fields already handled explicitly in generate_objects() frontmatter.
# Any key NOT in this set is treated as a custom field and written to extra_metadata.
# The object fields the build knows about. Two consumers, one meaning:
# anything outside it is the author's own column and goes to
# extra_metadata, and a bilingual alias is only applied to an objects
# sheet when its canonical name is in here. Defined beside the alias map
# so the scope is derived from the field set rather than listed twice.
KNOWN_OBJECT_FIELDS = OBJECT_FIELDS


def _object_metadata(obj, media_type, source_url):
    """The frontmatter fields that are written only when they have a value.

    Empty strings are truthy in Liquid, so a field written empty would make
    every `{% if %}` guarding it true on a page that has nothing to show.
    """
    medium_value = obj.get('medium', '') or obj.get('object_type', '')
    fields = {
        'alt_text': obj.get('alt_text', ''),
        'creator': obj.get('creator', ''),
        'period': obj.get('period', ''),
        'medium': medium_value,
        'dimensions': obj.get('dimensions', ''),
        'location': obj.get('source', '') or obj.get('location', ''),
        'credit': obj.get('credit', ''),
        'thumbnail': obj.get('thumbnail', ''),
        'iiif_manifest': obj.get('iiif_manifest', ''),
        'source_url': source_url,
        'object_warning': obj.get('object_warning', ''),
        'object_warning_short': obj.get('object_warning_short', ''),
    }
    return {key: _as_text(value) for key, value in fields.items() if value}


def _object_flags(obj, is_demo):
    """The optional scalars and the two booleans, in the order written."""
    flags = {}
    if obj.get('year'):
        flags['year'] = _as_text(obj.get('year'))
    # Frontmatter carries 'medium' only; object_type is not written
    if obj.get('subjects'):
        flags['subjects'] = _as_text(obj.get('subjects'))
    # The only two values on an object page that are genuinely booleans,
    # and the templates test them as booleans.
    if obj.get('is_featured_sample'):
        flags['is_featured_sample'] = True
    if is_demo:
        flags['demo'] = True
    return flags


# The decimal mark a site's language writes. A file size is written into the
# page as text, so it is formatted here rather than by the reader's browser.
DECIMAL_MARK = {'es': ','}


def _audio_file_details(object_id, decimal_mark='.'):
    """Size and format from the first matching file on disk.

    The first match wins: on a case-insensitive filesystem `.mp3` and `.MP3`
    both resolve to the same file, so continuing would write the block twice.
    """
    for ext in AUDIO_EXTENSIONS:
        audio_path = Path(f'telar-content/objects/{object_id}{ext}')
        if not audio_path.exists():
            continue
        size_bytes = audio_path.stat().st_size
        if size_bytes < 1024 * 1024:
            size_str = f'{size_bytes / 1024:.0f} KB'
        else:
            size_str = f'{size_bytes / (1024 * 1024):.1f} MB'.replace('.', decimal_mark)
        return {'audio_filesize': size_str,
                'audio_format': ext.lstrip('.').upper()}
    return {}


def _extra_metadata(obj):
    """Everything the object carries that the known set does not name.

    A CSV round-trip leaves absent cells as the float nan or the string
    'nan'; neither is a value anyone typed, so neither is written.
    """
    extra = {}
    for key, value in obj.items():
        if key in KNOWN_OBJECT_FIELDS:
            continue
        if value is None or (isinstance(value, float) and str(value) == 'nan'):
            continue
        s = str(value).strip()
        if s and s.lower() != 'nan':
            extra[key] = s

    return {'extra_metadata': extra} if extra else {}


def _object_page(obj, decimal_mark='.'):
    """One object's markdown, frontmatter and body."""
    object_id = obj['object_id']
    source_url = obj.get('source_url', '') or ''
    media_type = detect_media_type(source_url, object_id)

    fields = {'object_id': _as_text(object_id),
              'title': _as_text(obj.get('title', ''))}
    fields.update(_object_metadata(obj, media_type, source_url))
    # Always written: the template branches on it for every type.
    fields['media_type'] = _as_text(media_type)
    fields.update(_object_flags(obj, obj.get('_demo', False)))

    if media_type == 'Audio':
        fields.update(_audio_file_details(object_id, decimal_mark))

    fields.update(_extra_metadata(obj))

    content = '---\n' + _frontmatter_block(fields)

    description = obj.get('description', '')
    if description and has_latex(description):
        content += "has_latex: true\n"

    return content + f"""layout: object
---

{description}
"""


def _reset_objects_dir():
    """A fresh directory, so an object removed from the CSV loses its page."""
    objects_dir = Path('_jekyll-files/_objects')
    if objects_dir.exists():
        shutil.rmtree(objects_dir)
        print(f"✓ Cleaned up old object files")
    objects_dir.mkdir(parents=True, exist_ok=True)
    return objects_dir


def generate_objects(telar_language='en'):
    """Generate object markdown files from objects.json"""
    if not Path('_data/objects.json').exists():
        print("No objects.json found — skipping object generation")
        return

    with open('_data/objects.json', 'r') as f:
        objects = json.load(f)

    objects_dir = _reset_objects_dir()

    for obj in objects:
        object_id = obj.get('object_id', '')
        if not object_id:
            continue

        filepath = objects_dir / f"{object_id}.md"
        with open(filepath, 'w') as f:
            f.write(_object_page(obj, DECIMAL_MARK.get(telar_language, '.')))

        demo_label = " [DEMO]" if obj.get('_demo', False) else ""
        print(f"✓ Generated {filepath}{demo_label}")

def generate_theme_colours():
    """Derive a legible text colour for every theme background.

    Writes _data/telar-build/theme-colours.json, which assets/css/telar.scss
    emits as the --color-on-* custom properties. A site with no _data/themes/
    gets no file: the stylesheet's own fallbacks render it as before.
    """
    written = theme_colours.generate('_data')
    if written is None:
        print("Skipping theme colors (no _data/themes/)")
        return
    print(f"✓ Generated {written}")


def _story_has_latex(identifier):
    """Check the story's _data JSON metadata for the has_latex flag.

    Open stories get KaTeX loading decided in-template from the same
    metadata; protected pages cannot do that once the steps ship encrypted,
    so the flag is lifted into frontmatter at generation time.
    """
    data_file = Path(f'_data/{identifier}.json')
    if not data_file.exists():
        return False
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            story_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    if isinstance(story_data, list) and story_data and story_data[0].get('_metadata'):
        return bool(story_data[0].get('has_latex'))
    return False


def generate_protected_fragments(skip=False):
    """Generate steps-only fragment pages for protected stories.

    Each protected story gets a standalone generated page (pages collection,
    reserved permalink prefix /telar-protected-fragments/) whose layout
    renders nothing but the story steps through the same include as open
    stories. The post-build encryption step (encrypt_protected_stories.py)
    reads the rendered fragment from _site, encrypts it into the story's
    envelope, and deletes it — the fragment never deploys.

    Not a collection of its own: that would add _config.yml surface. The
    pages written here are cleaned up by glob on every run, so a story that
    stops being protected leaves no orphan behind.
    """
    pages_dir = Path('_jekyll-files/_pages')
    pages_dir.mkdir(parents=True, exist_ok=True)

    # Clean previous fragment pages first, and unconditionally. A fragment
    # renders the steps as plaintext for the encryption step to consume; one
    # left from a run when a story was protected would otherwise render again
    # with nothing to remove it. generate_pages() only clears this directory
    # when telar-content/texts/pages exists, so this cleanup is our own and
    # must happen before any early return below.
    for stale in pages_dir.glob('telar-fragment-*.md'):
        stale.unlink()

    project_path = Path('_data/project.json')
    if skip or not project_path.exists():
        return

    with open(project_path, 'r', encoding='utf-8') as f:
        project_data = json.load(f)

    stories = []
    if project_data and len(project_data) > 0:
        stories = project_data[0].get('stories', [])

    for story in stories:
        if not story.get('protected'):
            continue
        identifier = _story_identifier(story)
        if not Path(f'_data/{identifier}.json').exists():
            continue

        frontmatter = yaml.safe_dump(
            {
                'layout': 'story-fragment',
                'data_file': identifier,
                'permalink': f'/telar-protected-fragments/{identifier}/',
            },
            default_flow_style=False, allow_unicode=True, sort_keys=False,
        )
        filepath = pages_dir / f'telar-fragment-{identifier}.md'
        with open(filepath, 'w') as f:
            f.write(f"---\n{frontmatter}---\n\n")
        print(f"✓ Generated {filepath} (protected fragment)")


def _story_identifier(story):
    """The name a story's data file, document and URL are all built from."""
    story_id = story.get('story_id', '')  # Optional semantic ID (v0.6.0+)
    # With story_id: "your-story" → files are "your-story.json", "your-story.md"
    # Without story_id: number=1 → files are "story-1.json", "story-1.md"
    return story_id if story_id else f"story-{story.get('number', '')}"


def _publishable_stories(stories):
    """The stories that become documents, paired with their identifier.

    A record with no number or title is not a story, and one whose data
    file is missing has nothing to render — neither reaches Jekyll, so
    neither belongs in the manifest either.
    """
    out = []
    for story in stories:
        if not story.get('number', '') or not story.get('title', ''):
            continue
        identifier = _story_identifier(story)
        if not Path(f'_data/{identifier}.json').exists():
            print(f"Warning: No data file found for {identifier}.json")
            continue
        out.append((identifier, story))
    return out


def generate_stories(config=None):
    """Generate story markdown files based on project.json stories list

    Reads from _data/project.json which includes both user stories and
    merged demo content (when include_demo_content is enabled).

    Each document declares the permalink it renders at, and the same
    mapping is written to the story page manifest. Ambiguity — two records
    deriving one identifier, or two identifiers rendering at one URL — is
    refused before any file is written, so a build that would silently drop
    a story fails instead.
    """

    # Read from project.json (has merged user + demo stories)
    project_path = Path('_data/project.json')
    if not project_path.exists():
        print("Warning: _data/project.json not found")
        # An inventory from an earlier run would describe pages this build
        # cannot vouch for, and the encryption step reads it as authoritative.
        remove_manifest('_data')
        return

    with open(project_path, 'r', encoding='utf-8') as f:
        project_data = json.load(f)

    # Get stories from first project entry
    stories = []
    if project_data and len(project_data) > 0:
        stories = project_data[0].get('stories', [])

    stories_dir = Path('_jekyll-files/_stories')
    publishable = _publishable_stories(stories)
    permalink = stories_permalink(config)

    # Built before anything is written: an ambiguous site must not leave a
    # half-generated collection behind.
    manifest = build_manifest(
        ((identifier, stories_dir / f'{identifier}.md')
         for identifier, _ in publishable),
        permalink,
    )

    # Clean up old files to remove orphaned stories
    if stories_dir.exists():
        shutil.rmtree(stories_dir)
        print(f"✓ Cleaned up old story files")

    stories_dir.mkdir(parents=True, exist_ok=True)

    # Track sort order: demos get 0-999, user stories get 1000+
    demo_index = 0
    user_index = 1000

    for identifier, story in publishable:
        story_title = story.get('title', '')
        story_subtitle = story.get('subtitle', '')
        is_demo = story.get('_demo', False)

        # Assign sort order
        if is_demo:
            sort_order = demo_index
            demo_index += 1
        else:
            sort_order = user_index
            user_index += 1

        # Use identifier for filename (no additional prefix)
        filepath = stories_dir / f"{identifier}.md"
        story_url = manifest['stories'][identifier].get('url')

        # Build frontmatter as a dict and serialise via yaml.safe_dump so that
        # quotes, colons, or newlines in author-supplied title/subtitle/byline
        # cannot break out of their YAML fields. sort_keys=False keeps the
        # human-friendly field order.
        story_byline = story.get('byline', '')
        frontmatter_dict = {'title': story_title}
        if story_subtitle:
            frontmatter_dict['subtitle'] = story_subtitle
        if story_byline:
            frontmatter_dict['byline'] = story_byline
        if is_demo:
            frontmatter_dict['demo'] = True
        if story.get('show_sections'):
            frontmatter_dict['show_sections'] = True
        if story.get('protected'):
            # The _data JSON is plaintext through the build (encryption
            # happens post-build), so templates must key protected
            # behaviour on this flag, never on the data file's shape.
            frontmatter_dict['protected'] = True
            if _story_has_latex(identifier):
                frontmatter_dict['has_latex'] = True
        frontmatter_dict['sort_order'] = sort_order
        frontmatter_dict['layout'] = 'story'
        frontmatter_dict['data_file'] = identifier
        if story_url:
            # Declared, not derived: the collection template would produce
            # this same URL by slugifying the basename, but nothing would
            # record which identifier landed where.
            frontmatter_dict['permalink'] = story_url

        frontmatter_body = yaml.safe_dump(
            frontmatter_dict, default_flow_style=False, allow_unicode=True, sort_keys=False
        )
        content = f"---\n{frontmatter_body}---\n\n"

        with open(filepath, 'w') as f:
            f.write(content)

        demo_label = " [DEMO]" if is_demo else ""
        print(f"✓ Generated {filepath}{demo_label}")

    written = write_manifest('_data', manifest)
    print(f"✓ Generated {written} ({len(manifest['stories'])} story pages)")


def load_config():
    """Load _config.yml and return the full config dict (empty dict if missing)."""
    config_path = Path('_config.yml')
    if not config_path.exists():
        return {}

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def main():
    """Generate all collection files"""
    parser = argparse.ArgumentParser(
        description='Generate Jekyll collection files from Telar JSON data'
    )
    parser.add_argument(
        '--skip-objects',
        action='store_true',
        help='Skip object collection generation'
    )
    parser.add_argument(
        '--skip-stories',
        action='store_true',
        help='Skip story collection generation'
    )
    cli_args = parser.parse_args()

    print("Generating Jekyll collection files...")
    print("-" * 50)

    # Load site config; extract development feature flags and active language
    config = load_config()
    dev_features = config.get('development-features', {}) or {}
    telar_language = config.get('telar_language', 'en') or 'en'

    # Support both old names (hide_*) and new names (skip_*), new takes precedence
    # CLI flags also apply (union of CLI and config flags)
    skip_stories = (
        cli_args.skip_stories
        or dev_features.get('skip_stories', dev_features.get('hide_stories', False))
    )
    skip_collections = dev_features.get('skip_collections', dev_features.get('hide_collections', False))

    # skip_collections implies skip_stories
    if skip_collections:
        skip_stories = True

    # --skip-objects CLI flag (independent of skip_collections)
    skip_objects_flag = cli_args.skip_objects

    # Generate objects (skip if skip_collections or --skip-objects)
    if skip_collections:
        print("Skipping objects (skip_collections enabled)")
        objects_dir = Path('_jekyll-files/_objects')
        if objects_dir.exists():
            shutil.rmtree(objects_dir)
            print("✓ Cleaned up object files")
    elif skip_objects_flag:
        print("Skipping objects (--skip-objects)")
    else:
        generate_objects(telar_language=telar_language)
    print()

    # Always generate glossary
    generate_glossary()
    print()

    # Always derive theme on-colours: the stylesheet reads them whichever
    # collections a flag suppresses, and a site can switch themes in
    # _config.yml without a content change, so every theme file is covered
    # rather than the active one.
    generate_theme_colours()
    print()

    # Generate stories (skip and clean up if skip_stories or skip_collections)
    if skip_stories:
        print("Skipping stories (skip_stories enabled)" if not skip_collections else "Skipping stories (skip_collections enabled)")
        stories_dir = Path('_jekyll-files/_stories')
        if stories_dir.exists():
            shutil.rmtree(stories_dir)
            print("✓ Cleaned up story files")
        # A manifest left from an earlier run would describe pages this
        # build does not produce.
        remove_manifest('_data')
    else:
        generate_stories(config)
    print()

    # Always generate pages (passes active language so localized sister files
    # like acerca.md/about.md can be selected at build time)
    generate_pages(telar_language=telar_language)
    check_title_keys()

    # Must follow generate_pages, which can clear _jekyll-files/_pages/ where
    # the fragment pages live, and must run even when stories are skipped: a
    # fragment page left from an earlier run renders plaintext steps that
    # nothing will encrypt.
    generate_protected_fragments(skip=skip_stories)

    print("-" * 50)
    print("Generation complete!")


if __name__ == '__main__':
    try:
        main()
    except ManifestError as error:
        print(f"\n❌ This site cannot be generated as described:\n  {error}")
        raise SystemExit(1)
    except (ColumnCollisionError, ReservedColumnError) as error:
        # Stderr, where the upgrade reads a failed step's reason.
        source = getattr(error, 'source', None)
        prefix = f"{source}: " if source else ""
        print(f"\n❌ {prefix}{error}", file=sys.stderr)
        raise SystemExit(SHEET_REFUSED_EXIT)
