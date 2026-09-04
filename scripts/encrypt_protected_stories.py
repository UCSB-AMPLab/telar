#!/usr/bin/env python3
"""
Post-build encryption for protected stories.

Runs after `jekyll build` (in the build workflow and in build_local_site.py)
and consolidates protected-story rendering into the build-time renderer:
Jekyll renders each protected story's steps through the same include as open
stories, into a standalone fragment page that never deploys; this script
encrypts that rendered HTML together with the steps JSON in one envelope,
injects the envelope into the story page, deletes the fragment, and then
fails the build unless the output is verifiably clean.

Contract with the templates (see _layouts/story-fragment.html and
_layouts/story.html):
- Fragment pages render at _site/telar-protected-fragments/<identifier>/,
  with the steps markup between the markers
  `<!-- telar-fragment-steps-start -->` / `<!-- telar-fragment-steps-end -->`.
- Protected story pages emit a stub envelope whose ciphertext is the
  placeholder token; this script swaps the stub for the real envelope. A page
  that ships with the stub still in place shows the unlock UI and fails
  decryption loudly — never plaintext, never a script crash.

Story pages are located through the manifest generate_collections.py
writes (see telar/story_pages.py), never by predicting a URL. The manifest
names the permalink each identifier was generated with, so the encryptor
opens one path and either finds the page there or fails. It does not ask a
page which story it belongs to: `data_file` is author-writable frontmatter,
so a page claiming an identifier is not evidence that it owns the URL.

What this script trusts, in full — three things, and it is worth naming
them because two earlier versions of this list were wrong:

1. The story page manifest written by this build.
2. The protected-layout stub at the one path the manifest names.
3. The rendered fragment at telar-protected-fragments/<identifier>/, whose
   markers are as public as the stub.

None of 2 or 3 proves ownership on its own: both are literals anyone can
copy into a page of their own, and a page that wins one of those
destinations passes every check here. What makes them sufficient is a
fourth thing, which is not in this file — the build fails on Jekyll's
`Conflict:` warning (scripts/check_jekyll_conflicts.py). Jekyll computes
every destination from every source it renders and already reports every
collision; it just exits 0 afterwards. With that gate, no second document
can claim a story's page or its fragment, so the file found at each of
these paths is the one the generator put there.

What remains outside the argument: anything that reaches `_site` without
passing through Jekyll's destination map — a step that writes into the
output directory after the build, or a copy made outside the pipeline.

Gates (any failure aborts the build with exit code 1):
- Shape: every protected story has a manifest entry, a data file, a
  rendered fragment, and a stub to replace; after injection no placeholder
  token and no fragment survives anywhere in the site output.
- Content: distinctive plaintext substrings from each protected story's
  steps are grepped across the rendered site output; any hit fails the
  build. This catches template reads nobody has written yet. The sweep
  skips _site/telar-content/ — the passthrough copy of the source
  spreadsheets is served by design (story locking is a slight barrier for
  drafts, not privacy, and the docs say so).

Sentinels are derived from plain prose segments of questions, answers, and
layer content (markdown/HTML markup and smart-punctuation candidates are
excluded so the segments survive kramdown rendering verbatim). Story
metadata like the byline is deliberately not used: bylines recur across a
site's open and protected stories, and a shared byline must not fail the
build.

Version: v1.7.0
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from telar.encryption import (  # noqa: E402
    encrypt_story,
    get_protected_stories,
    get_story_key_from_config,
)
from telar.story_pages import (  # noqa: E402
    DEFAULT_STORIES_PERMALINK,
    MANIFEST_RELATIVE_PATH,
    MANIFEST_SCHEMA,
    read_manifest,
)

FRAGMENT_URL_PREFIX = 'telar-protected-fragments'
FRAGMENT_START = '<!-- telar-fragment-steps-start -->'
FRAGMENT_END = '<!-- telar-fragment-steps-end -->'
STUB_TOKEN = '__TELAR_PENDING__'

# The stub assignment emitted by story.html for protected pages. The regex
# targets the whole assignment so the swap leaves valid JS behind.
STUB_PATTERN = re.compile(
    r'window\.storyData\s*=\s*\{[^;]*?' + STUB_TOKEN + r'[^;]*?\};'
)

# File types included in the content sweep.
SWEEP_SUFFIXES = {'.html', '.js', '.json', '.xml', '.txt', '.csv', '.md', '.css'}

# Step fields that hold author prose worth deriving sentinels from.
PROSE_FIELDS = ('question', 'answer', 'layer1_content', 'layer2_content')

# Sentinels must be long enough that a hit means "this story's prose is on
# that page", not a stock phrase collision ('start, end, loop' appears in the
# CHANGELOG). Tags are stripped first so markup vocabulary (class names,
# URLs) can never become a sentinel — those live on every page.
# Dense scripts (CJK, kana, Hangul) carry roughly a word per character, so a
# 20-char bar there demands a whole paragraph where Latin needs a phrase —
# segments that are mostly dense-script characters use the lower bar.
MIN_SENTINEL_LENGTH = 20
MIN_SENTINEL_LENGTH_DENSE = 10
MAX_SENTINEL_LENGTH = 60
MAX_SENTINELS_PER_STORY = 24

# Han (incl. Ext A), kana, Hangul — the scripts where 10 characters already
# form a distinctive phrase.
_DENSE_SCRIPT_RE = re.compile(
    '[぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]'
)


def _min_sentinel_length(segment):
    """The length bar a segment must clear to become a sentinel."""
    compact = segment.replace(' ', '')
    if not compact:
        return MIN_SENTINEL_LENGTH
    dense = len(_DENSE_SCRIPT_RE.findall(compact))
    if dense * 2 >= len(compact):
        return MIN_SENTINEL_LENGTH_DENSE
    return MIN_SENTINEL_LENGTH


class GateFailure(Exception):
    """A verification gate failed; the build must not publish."""


def load_story_key(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return get_story_key_from_config(config)


def load_page_manifest(data_dir):
    """Read the story page manifest, or fail saying how to produce one."""
    path = Path(data_dir) / MANIFEST_RELATIVE_PATH
    manifest = read_manifest(data_dir)
    if manifest is None:
        raise GateFailure(
            f"story page manifest not found ({path}). Run "
            "generate_collections.py before the Jekyll build — the "
            "encryptor locates story pages through it and does not guess "
            "URLs."
        )
    # A manifest this script cannot read is worse than none: read loosely it
    # becomes "no stories were generated", and every lookup then fails
    # blaming the wrong thing. Every shape the reads below depend on is
    # checked here, so nothing downstream raises AttributeError instead of
    # failing the gate.
    schema = manifest.get('schema') if isinstance(manifest, dict) else None
    stories = manifest.get('stories') if isinstance(manifest, dict) else None
    malformed = (
        schema != MANIFEST_SCHEMA
        or not isinstance(stories, dict)
        or not all(isinstance(entry, dict) for entry in stories.values())
    )
    if malformed:
        raise GateFailure(
            f"{path}: not a schema-{MANIFEST_SCHEMA} story page manifest "
            f"(found schema {schema!r}). Either the scripts in this site are "
            "from different releases, or the file has been edited — "
            "regenerate it with generate_collections.py."
        )
    return manifest


def resolve_story_page(site_dir, identifier, manifest):
    """Return the rendered page the generator directed this story to.

    The manifest is authoritative. Nothing here searches candidate paths or
    reads a page's own claim about which story it is: the generator wrote
    the permalink into the document's frontmatter and recorded the same
    value, so exactly one path can be correct and a page that is not at it
    is not this story's.
    """
    entry = manifest.get('stories', {}).get(identifier)
    if entry is None:
        raise GateFailure(
            f"{identifier}: no story page was generated for this story. "
            "Its record in project.json produced no document — check that "
            f"_data/{identifier}.json exists and that the story has both a "
            "number and a title."
        )

    url = entry.get('url')
    if url is not None and not isinstance(url, str):
        raise GateFailure(
            f"{identifier}: the manifest records a non-text URL ({url!r}). "
            "Regenerate it with generate_collections.py."
        )
    if not url:
        permalink = manifest.get('stories_permalink', '(unset)')
        raise GateFailure(
            f"{identifier}: this site sets the stories collection permalink "
            f"to {permalink} rather than {DEFAULT_STORIES_PERMALINK}, so the "
            "generator could not record where its pages render and the "
            "encryptor cannot locate them. Protected stories need the "
            "default stories permalink."
        )

    site_root = Path(site_dir).resolve()
    page = (Path(site_dir) / url.strip('/') / 'index.html')
    # The manifest is this build's own output, but it is a file on disk and
    # a wrong one must not be able to send a write outside the site.
    try:
        page.resolve().relative_to(site_root)
    except ValueError:
        raise GateFailure(
            f"{identifier}: the manifest places this story at {url}, which "
            f"resolves outside {site_root}. Regenerate the manifest with "
            "generate_collections.py."
        )
    if not page.exists():
        raise GateFailure(
            f"{identifier}: story page not found at {page}, where "
            f"{url} was generated to render. Was the Jekyll build run "
            "after generate_collections.py?"
        )
    # A case-insensitive filesystem answers exists() for a directory whose
    # real name differs in case, and Jekyll reports no conflict for that
    # pair because its destination map treats them as distinct. Compare
    # against the name actually on disk.
    directory = page.parent
    siblings = {entry.name for entry in directory.parent.iterdir()}
    if directory.name not in siblings:
        raise GateFailure(
            f"{identifier}: {url} was generated, but the directory on disk "
            f"is named differently — {directory.parent} holds "
            f"{', '.join(sorted(siblings))}. On a case-insensitive "
            "filesystem another page has taken this story's address. Rename "
            "it so the two differ by more than case."
        )
    return page


def check_no_orphan_fragments(site_dir):
    """Refuse a build carrying rendered fragments nothing will encrypt.

    Fragments exist only so this script can read the rendered steps out of
    them; every one is deleted as its story is encrypted. One surviving in a
    build with no protected stories is plaintext with no owner — most often
    a stale page from a run when that story was protected.
    """
    fragment_root = Path(site_dir) / FRAGMENT_URL_PREFIX
    if not fragment_root.exists():
        return
    orphans = sorted(child.name for child in fragment_root.iterdir())
    raise GateFailure(
        f"{fragment_root} holds rendered story fragments but no story in "
        "project.json is marked protected: " + ', '.join(orphans)
        + ". Fragment pages carry the steps as plaintext and are meant to be "
        "consumed and deleted by this script. Re-run "
        "generate_collections.py and rebuild so the stale pages are cleared."
    )


def find_protected_stories(data_dir):
    """Return the set of protected story identifiers from project.json."""
    project_path = Path(data_dir) / 'project.json'
    if not project_path.exists():
        return set()
    with open(project_path, 'r', encoding='utf-8') as f:
        return get_protected_stories(json.load(f))


def derive_sentinels(steps):
    """Extract plain prose segments that must never appear in rendered output.

    Splits each prose field on markup and smart-punctuation candidates
    (anything kramdown might transform) and keeps the longest plain
    segments. Returns a list of strings.
    """
    segments = []
    for step in steps:
        if not isinstance(step, dict) or step.get('_metadata'):
            continue
        for field in PROSE_FIELDS:
            text = step.get(field) or ''
            # Tags are stripped from EVERY prose field, not just answers
            # (answers arrive as rendered HTML; the others may carry inline
            # markup too): markup vocabulary — class names, URLs — lives on
            # every page and must never become a sentinel.
            text = re.sub(r'<[^>]+>', ' ', text)
            # Split on characters that markdown/HTML rendering or smart
            # punctuation could alter; what remains appears verbatim. \w
            # keeps letters and digits of every script (Cyrillic, Greek,
            # Arabic, CJK — not just Latin); underscores split separately
            # because markdown transforms them (emphasis) even though \w
            # matches them.
            for segment in re.split(r"[^\w ,.-]+|_+", text):
                segment = ' '.join(segment.split())
                if len(segment) >= _min_sentinel_length(segment):
                    segments.append(segment[:MAX_SENTINEL_LENGTH].strip())
    # Longest first: most distinctive, least likely to collide.
    segments.sort(key=len, reverse=True)
    return segments[:MAX_SENTINELS_PER_STORY]


def extract_fragment_html(fragment_page):
    """Read the rendered steps markup out of a fragment page."""
    html = fragment_page.read_text(encoding='utf-8')
    start = html.find(FRAGMENT_START)
    end = html.find(FRAGMENT_END)
    if start == -1 or end == -1 or end <= start:
        raise GateFailure(
            f"{fragment_page}: fragment markers not found — "
            "_layouts/story-fragment.html and this script disagree"
        )
    return html[start + len(FRAGMENT_START):end].strip()


def inject_envelope(story_page, envelope):
    """Replace the stub storyData assignment with the real envelope."""
    html = story_page.read_text(encoding='utf-8')
    replacement_json = json.dumps(envelope, ensure_ascii=False)
    new_html, count = STUB_PATTERN.subn(
        lambda _m: f'window.storyData = {replacement_json};', html, count=1
    )
    if count != 1:
        raise GateFailure(
            f"{story_page}: no stub envelope found — the story layout did "
            "not mark this page as protected, so the rendered page may "
            "contain plaintext. Refusing to publish."
        )
    story_page.write_text(new_html, encoding='utf-8')


def sweep_files(site_dir, skip_top=('telar-content',)):
    """Yield text files in the site output, skipping excluded top dirs."""
    site_dir = Path(site_dir)
    for path in site_dir.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in SWEEP_SUFFIXES:
            continue
        relative = path.relative_to(site_dir)
        if relative.parts and relative.parts[0] in skip_top:
            continue
        yield path


def _warn_skipped(skipped, sweep_name):
    """A file the sweep cannot read is a file the gate did not check —
    say so rather than let the final "passed" overstate coverage."""
    if skipped:
        print(f"  WARNING: {sweep_name} could not read {len(skipped)} "
              "file(s) as UTF-8; they were NOT scanned:")
        for path in skipped:
            print(f"    {path}")


def content_sentinel_sweep(site_dir, sentinels_by_story):
    """Grep the rendered output for protected plaintext. Returns hits."""
    hits = []
    skipped = []
    for path in sweep_files(site_dir):
        try:
            text = path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            skipped.append(str(path))
            continue
        for story_id, sentinels in sentinels_by_story.items():
            for sentinel in sentinels:
                if sentinel in text:
                    hits.append((str(path), story_id, sentinel))
    _warn_skipped(skipped, 'content sweep')
    return hits


def shape_sweep(site_dir):
    """Post-injection shape checks: no stub token, no fragment output."""
    problems = []
    skipped = []
    fragment_dir = Path(site_dir) / FRAGMENT_URL_PREFIX
    if fragment_dir.exists():
        problems.append(f"{fragment_dir} still exists after fragment deletion")
    for path in sweep_files(site_dir):
        try:
            if STUB_TOKEN in path.read_text(encoding='utf-8'):
                problems.append(f"{path}: leftover {STUB_TOKEN}")
        except (UnicodeDecodeError, OSError):
            skipped.append(str(path))
            continue
    _warn_skipped(skipped, 'shape sweep')
    return problems


def process_site(site_dir, data_dir, config_path):
    """Encrypt every protected story in the built site. Returns count."""
    site_dir = Path(site_dir)
    data_dir = Path(data_dir)

    protected = find_protected_stories(data_dir)
    if not protected:
        # A fragment page renders the steps in plaintext for this script to
        # consume and delete. If one is in the output while no story claims
        # protection, nothing downstream will remove it and the draft
        # deploys. Checked before the early return, not after it.
        check_no_orphan_fragments(site_dir)
        print("No protected stories — nothing to encrypt.")
        return 0

    story_key = load_story_key(config_path)
    if not story_key:
        raise GateFailure(
            f"{len(protected)} protected story/stories but no story_key in "
            f"{config_path}. Refusing to publish."
        )

    manifest = load_page_manifest(data_dir)

    sentinels_by_story = {}

    for identifier in sorted(protected):
        data_file = data_dir / f"{identifier}.json"
        if not data_file.exists():
            raise GateFailure(f"{identifier}: data file not found ({data_file})")
        with open(data_file, 'r', encoding='utf-8') as f:
            steps = json.load(f)
        if not isinstance(steps, list):
            raise GateFailure(
                f"{identifier}: {data_file} is not a plaintext steps list — "
                "was the data pipeline run with pre-v1.6.0 scripts?"
            )

        # Fragment pages carry an explicit permalink built from the raw
        # identifier, so this path is not slugified — unlike the story page
        # below, whose URL comes from the collection template.
        fragment_page = site_dir / FRAGMENT_URL_PREFIX / identifier / 'index.html'
        if not fragment_page.exists():
            raise GateFailure(
                f"{identifier}: rendered fragment not found ({fragment_page}) — "
                "was generate_collections.py run before the Jekyll build?"
            )
        fragment_html = extract_fragment_html(fragment_page)

        story_page = resolve_story_page(site_dir, identifier, manifest)

        envelope = encrypt_story(
            {'steps': steps, 'html': fragment_html}, story_key, aad=identifier
        )
        inject_envelope(story_page, envelope)

        shutil.rmtree(site_dir / FRAGMENT_URL_PREFIX / identifier)
        sentinels_by_story[identifier] = derive_sentinels(steps)
        print(f"  Encrypted {identifier} (fragment removed, envelope injected)")

    # Remove the (now empty) fragment root if Jekyll created one.
    fragment_root = site_dir / FRAGMENT_URL_PREFIX
    if fragment_root.exists() and not any(fragment_root.iterdir()):
        fragment_root.rmdir()

    problems = shape_sweep(site_dir)
    if problems:
        raise GateFailure("Shape check failed:\n  " + "\n  ".join(problems))

    hits = content_sentinel_sweep(site_dir, sentinels_by_story)
    if hits:
        lines = [f"{path}: {story_id} plaintext ({sentinel!r})"
                 for path, story_id, sentinel in hits]
        raise GateFailure(
            "Protected plaintext found in rendered output:\n  "
            + "\n  ".join(lines)
            + "\nThis text appears both in a protected story and on a page "
              "that publishes openly. The quoted passage is what matched: the "
              "gate compares each protected story's longest plain-prose "
              "segments against every published file. Reword whichever copy "
              "should stay public, or remove the protection from that story."
        )

    # The content gate only checks stories it could derive sentinels FROM.
    # A story whose prose has no run of MIN_SENTINEL_LENGTH sentinel-safe
    # characters (very short steps) yields none — the shape gate still
    # protects it, but the success line must not claim content coverage
    # it doesn't have.
    uncovered = sorted(sid for sid, s in sentinels_by_story.items() if not s)
    if uncovered:
        print(f"  WARNING: no content sentinels could be derived for: "
              f"{', '.join(uncovered)} — the content gate did not check "
              "these stories (shape gates still apply).")
        print(f"✓ {len(protected)} protected story/stories encrypted; "
              f"shape gates passed; content gate covered "
              f"{len(protected) - len(uncovered)} of {len(protected)}.")
    else:
        print(f"✓ {len(protected)} protected story/stories encrypted; "
              "shape and content gates passed.")
    return len(protected)


def _emit_actions_error(failure, title='Protected stories gate'):
    """Record the failure as a GitHub Actions annotation when running in CI.

    A workflow step that simply exits non-zero is reported as "Process
    completed with exit code 1", which says nothing about what went wrong.
    An `::error::` line is attached to the run as a structured annotation
    instead, so the reason travels with the run and tools reading the build
    can report it without scraping the log. Newlines are escaped because a
    workflow command occupies a single line.
    """
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        return
    message = str(failure).replace('%', '%25').replace('\r', '%0D')
    message = message.replace('\n', '%0A')
    print(f"::error title={title}::{message}")


def main():
    parser = argparse.ArgumentParser(
        description='Encrypt protected stories in the built site (post-Jekyll).'
    )
    parser.add_argument('--site-dir', default='_site')
    parser.add_argument('--data-dir', default='_data')
    parser.add_argument('--config', default='_config.yml')
    args = parser.parse_args()

    try:
        process_site(args.site_dir, args.data_dir, args.config)
    except GateFailure as failure:
        print(f"\n❌ {failure}")
        print("The build output must not be published. / "
              "El resultado de este build no se debe publicar.")
        _emit_actions_error(failure)
        raise SystemExit(1)
    except Exception as error:
        # A malformed JSON or YAML file, or an unreadable path, aborts the
        # build exactly as a gate failure does. Without this the run reports
        # only "Process completed with exit code 1" and the traceback stays
        # buried in the step log. Re-raised, so the traceback still prints.
        _emit_actions_error(
            f"{type(error).__name__}: {error}",
            title='Protected stories script error',
        )
        raise


if __name__ == '__main__':
    main()
