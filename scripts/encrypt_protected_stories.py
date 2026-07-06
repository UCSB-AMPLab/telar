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

Gates (any failure aborts the build with exit code 1):
- Shape: every protected story has a data file, a rendered fragment, and a
  stub to replace; after injection no placeholder token and no fragment
  survives anywhere in the site output.
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

Version: v1.6.0
"""

import argparse
import json
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
MIN_SENTINEL_LENGTH = 20
MAX_SENTINEL_LENGTH = 60
MAX_SENTINELS_PER_STORY = 24


class GateFailure(Exception):
    """A verification gate failed; the build must not publish."""


def load_story_key(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return get_story_key_from_config(config)


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
                if len(segment) >= MIN_SENTINEL_LENGTH:
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
        print("No protected stories — nothing to encrypt.")
        return 0

    story_key = load_story_key(config_path)
    if not story_key:
        raise GateFailure(
            f"{len(protected)} protected story/stories but no story_key in "
            f"{config_path}. Refusing to publish."
        )

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

        fragment_page = site_dir / FRAGMENT_URL_PREFIX / identifier / 'index.html'
        if not fragment_page.exists():
            raise GateFailure(
                f"{identifier}: rendered fragment not found ({fragment_page}) — "
                "was generate_collections.py run before the Jekyll build?"
            )
        fragment_html = extract_fragment_html(fragment_page)

        story_page = site_dir / 'stories' / identifier / 'index.html'
        if not story_page.exists():
            raise GateFailure(f"{identifier}: story page not found ({story_page})")

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
        raise SystemExit(1)


if __name__ == '__main__':
    main()
