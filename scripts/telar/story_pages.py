"""
Story Page Manifest

The contract between `generate_collections.py`, which writes story
documents, and `encrypt_protected_stories.py`, which has to find each
protected story's rendered page in `_site` afterwards.

The problem this module exists to remove is guessing. A story document is
written to `_jekyll-files/_stories/<identifier>.md`, and its URL comes from
the explicit `permalink` the generator writes into that document's
frontmatter and records here. Left to the collection template
`/stories/:name/`, the URL would be the basename put through Jekyll's
`Utils.slugify` — `my_story` rendering at `/stories/my-story/`, a path
nothing records and the encryptor would have to predict. Prediction has no
way to tell whose page it found: any page declaring `layout: story` and
`data_file: my_story` in its own frontmatter claims that identity, and
frontmatter is author-writable.

The recorded URL equals the one the collection template produces, so no
site's story moves; the destination is declared rather than inferred, and
the encryptor reads the declaration instead of searching for a page willing
to claim an identifier.

Two properties the manifest guarantees, both enforced when it is built:

- **Every identifier appears at most once.** Two records deriving one
  identifier overwrite each other's document, so the second silently
  replaces the first.
- **Every URL appears at most once.** Two identifiers slugifying to one
  path claim a single page, so one story silently has none.

Either is a build that publishes something other than what the site
describes, so both are refused rather than resolved.

A site whose `_config.yml` sets a stories permalink other than the shipped
`/stories/:name/` gets a manifest with no URLs: expanding an arbitrary
permalink template is Jekyll's job, not this module's, and a guess is what
we are removing. The encryptor reports that as the reason it cannot locate
pages, which is what it was already trying to say.

Version: v1.7.0
"""

import json
import unicodedata
from pathlib import Path

# Where the manifest lands, relative to the data directory. Nested so it
# can never collide with `_data/<identifier>.json`, which is keyed by story
# identifier; Jekyll loads it as `site.data['telar-build']`, which no
# template reads.
MANIFEST_RELATIVE_PATH = Path('telar-build') / 'story-pages.json'

MANIFEST_SCHEMA = 1

# The stories permalink this module knows how to reproduce. Anything else
# is recorded verbatim and left unresolved.
DEFAULT_STORIES_PERMALINK = '/stories/:name/'


class ManifestError(Exception):
    """The manifest cannot be built because the site is ambiguous."""


def jekyll_slug(value):
    """Reproduce Jekyll's `Utils.slugify` in its default mode.

    Characters that are marks, letters or decimal digits pass through; every
    other run collapses to a single hyphen; leading and trailing hyphens are
    dropped and the result is lower-cased.
    """
    out = []
    prev_hyphen = False
    for char in value:
        category = unicodedata.category(char)
        if category[0] in ('M', 'L') or category == 'Nd':
            out.append(char)
            prev_hyphen = False
        elif not prev_hyphen:
            out.append('-')
            prev_hyphen = True
    return ''.join(out).strip('-').lower()


def stories_permalink(config):
    """The stories collection permalink a site configures, or the default."""
    collections = (config or {}).get('collections') or {}
    stories = collections.get('stories') or {}
    return stories.get('permalink') or DEFAULT_STORIES_PERMALINK


def story_url(identifier, permalink=DEFAULT_STORIES_PERMALINK):
    """The URL a story renders at, or None when this module cannot say.

    Returns None for a permalink template other than the shipped one, and
    for an identifier that slugifies to nothing — a name made only of
    punctuation would render at `/stories//`, which is not a page.
    """
    if permalink != DEFAULT_STORIES_PERMALINK:
        return None
    slug = jekyll_slug(identifier)
    return f'/stories/{slug}/' if slug else None


def manifest_path(data_dir):
    return Path(data_dir) / MANIFEST_RELATIVE_PATH


def build_manifest(entries, permalink=DEFAULT_STORIES_PERMALINK):
    """Assemble the manifest from (identifier, source_path) pairs.

    Raises ManifestError when an identifier or a URL appears twice — see the
    module docstring for why neither is resolvable here.
    """
    resolvable = permalink == DEFAULT_STORIES_PERMALINK
    stories = {}
    urls = {}
    duplicate_ids = []
    empty_slugs = []
    collisions = {}

    for identifier, source in entries:
        if identifier in stories:
            duplicate_ids.append(identifier)
            continue
        entry = {'source': str(source)}
        url = story_url(identifier, permalink)
        if url:
            entry['url'] = url
            if url in urls:
                collisions.setdefault(url, [urls[url]]).append(identifier)
            else:
                urls[url] = identifier
        elif resolvable:
            # No URL under a permalink we can reproduce means the name
            # slugifies to nothing, which is a broken identifier rather
            # than a limit of this module.
            empty_slugs.append(identifier)
        stories[identifier] = entry

    problems = []
    if duplicate_ids:
        problems.append(
            "Two or more stories share one identifier, so their documents "
            "overwrite each other: " + ', '.join(sorted(set(duplicate_ids)))
            + ". Give each story its own story_id."
        )
    if empty_slugs:
        problems.append(
            "These identifiers slugify to an empty path, so they render at "
            "no page: " + ', '.join(sorted(empty_slugs))
            + ". Give each one at least one letter or digit."
        )
    if collisions:
        problems.extend(
            f"{', '.join(sorted(ids))} all render at {url} — only one of them "
            "gets a page."
            for url, ids in sorted(collisions.items())
        )
    if problems:
        raise ManifestError('\n  '.join(problems))

    manifest = {
        'schema': MANIFEST_SCHEMA,
        'stories_permalink': permalink,
        'stories': stories,
    }
    return manifest


def write_manifest(data_dir, manifest):
    path = manifest_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')
    return path


def remove_manifest(data_dir):
    """Drop a manifest a later build must not inherit."""
    path = manifest_path(data_dir)
    if path.exists():
        path.unlink()


def read_manifest(data_dir):
    """Return the manifest, or None when this build did not write one."""
    path = manifest_path(data_dir)
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
