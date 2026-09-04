"""
E2E Characterization Tests for Story Locking (Protected Stories)

This module tests protected-story behavior against the locked-fixture story
(telar-content/spreadsheets/locked-fixture.csv).

Two kinds of assertions live here, and the distinction matters:

1. INVARIANTS — leak-freedom properties: no step content, section titles, or
   byline in the locked page or homepage HTML; unlock UI present; keyhole
   shown.

2. UNLOCK RENDERING — the decrypted envelope carries build-rendered step
   HTML, so unlocked stories render through the same clone path as open
   stories (markdown preserved) and a same-session revisit decrypts with the
   cached key. (The served source CSVs under /telar-content/spreadsheets/
   are a third register: accepted by design — see TestPublishedBuildInputs.)

Prerequisites:
    - Data pipeline run: python scripts/csv_to_json.py && python scripts/generate_collections.py
    - _config.yml story_key: "test" (test-instance default)
    - Jekyll site running: bundle exec jekyll serve --port 4001

Run tests:
    pytest tests/e2e/test_story_locking.py -v --base-url http://127.0.0.1:4001/telar

Version: v1.7.0
"""

import json
import re
import pytest
from playwright.sync_api import expect


LOCKED_STORY_PATH = "/stories/locked-fixture/"
STORY_KEY = "test"
WRONG_KEY = "not-the-key"

# Sentinel strings authored into the fixture story. None of these may appear
# in any served HTML while the story is locked. LFIX-ALT-SENTINEL (object
# alt_text) is deliberately NOT in this list: object metadata is public by
# design (objects gallery, objects.json) even when the story is protected.
STEP_CONTENT_SENTINELS = [
    "LFIX-Q1-SENTINEL",
    "LFIX-A1-SENTINEL",
    "LFIX-TOC-SENTINEL",
    "LFIX-Q3-SENTINEL",
    "LFIX-A3-SENTINEL",
    "LFIX-Q4-SENTINEL",
    "LFIX-A4-SENTINEL",
    "LFIX-Q5-SENTINEL",
    "LFIX-A5-SENTINEL",
    "LFIX-LAYER-SENTINEL",
    "LFIX-STEPALT-SENTINEL",
    "LFIX-BYLINE-SENTINEL",
]


def get_page_source(page, base_url, path):
    """Fetch raw HTML for a path without executing scripts."""
    response = page.request.get(f"{base_url}{path}")
    assert response.ok, f"GET {path} returned {response.status}"
    return response.text()


def unlock_story(page, base_url, key=STORY_KEY):
    """Navigate to the locked story and submit the given key."""
    page.goto(f"{base_url}{LOCKED_STORY_PATH}")
    page.wait_for_selector("#story-unlock-overlay", state="visible", timeout=10000)
    page.fill("#unlock-key-input", key)
    page.click("#unlock-form button[type=submit]")


class TestLockedPageLeakFreedom:
    """INVARIANTS: the locked story page must not contain step content."""

    def test_no_step_content_in_page_source(self, page, base_url):
        html = get_page_source(page, base_url, LOCKED_STORY_PATH)
        for sentinel in STEP_CONTENT_SENTINELS:
            assert sentinel not in html, f"Locked page leaks {sentinel}"

    def test_story_data_is_ciphertext_envelope(self, page, base_url):
        html = get_page_source(page, base_url, LOCKED_STORY_PATH)
        assert '"encrypted"' in html and '"ciphertext"' in html

    def test_unlock_ui_present(self, page, base_url):
        page.goto(f"{base_url}{LOCKED_STORY_PATH}")
        expect(page.locator("#story-unlock-overlay")).to_be_visible()
        expect(page.locator("#unlock-key-input")).to_be_visible()

    def test_no_toc_despite_show_sections(self, page, base_url):
        # The fixture sets show_sections: true and contains a section step.
        # Today no TOC renders because the Liquid loop meets a ciphertext
        # dict instead of a steps list. This absence is an invariant: after
        # the consolidation the locked page must STILL carry no TOC.
        html = get_page_source(page, base_url, LOCKED_STORY_PATH)
        assert "intro-toc" not in html
        assert "LFIX-TOC-SENTINEL" not in html

    def test_no_viewer_warnings_block(self, page, base_url):
        # The fixture's step 5 references a missing object, which generates a
        # viewer warning in the story metadata. RECORDED REALITY: the warning
        # block is absent on the locked page because the metadata is inside
        # the ciphertext. (Open stories show these warnings.)
        html = get_page_source(page, base_url, LOCKED_STORY_PATH)
        assert "telar-alert" not in html

    def test_no_byline_on_locked_page(self, page, base_url):
        html = get_page_source(page, base_url, LOCKED_STORY_PATH)
        assert "LFIX-BYLINE-SENTINEL" not in html


class TestHomepageLeakFreedom:
    """INVARIANTS: the homepage shows a keyhole, not story content."""

    def test_keyhole_shown_for_protected_story(self, page, base_url):
        page.goto(f"{base_url}/")
        card = page.locator(".story-protected-thumbnail").first
        expect(card).to_be_attached()

    def test_no_byline_or_step_content_on_homepage(self, page, base_url):
        html = get_page_source(page, base_url, "/")
        for sentinel in STEP_CONTENT_SENTINELS:
            assert sentinel not in html, f"Homepage leaks {sentinel}"

    def test_stories_island_marks_story_protected(self, page, base_url):
        html = get_page_source(page, base_url, "/")
        island = re.search(
            r'<script id="telar-stories-data"[^>]*>(.*?)</script>', html, re.S
        )
        assert island, "telar-stories-data island missing"
        stories = json.loads(island.group(1))
        # Island entries carry only title, url, protected — no byline.
        fixture = [
            s for s in stories
            if s.get("url", "").endswith("/stories/locked-fixture/")
        ]
        assert fixture, f"locked-fixture missing from island: {[s.get('url') for s in stories]}"
        assert fixture[0]["protected"] is True


class TestUnlockFlow:
    """Unlocked stories take the clone path: the decrypted envelope's HTML
    (rendered at build time through the same include as open stories) lands
    in the step pool, and card-pool clones it exactly as for open stories."""

    def test_correct_key_reveals_steps(self, page, base_url):
        unlock_story(page, base_url)
        page.wait_for_selector("#story-unlock-overlay", state="hidden", timeout=10000)
        page.wait_for_function(
            "window.storyData && Array.isArray(window.storyData.steps)"
        )
        # Clone path taken: the pool holds build-rendered steps and the
        # card stack is populated from them.
        assert page.locator(".step-data .story-step").count() >= 5
        page.wait_for_selector(".card-stack .text-card", state="attached", timeout=10000)
        # Build-rendered attributes survive: clip attrs and alt text.
        assert page.locator('.step-data .story-step[data-clip-start="5"]').count() == 1
        assert page.locator('.step-data .story-step[data-alt*="LFIX-STEPALT-SENTINEL"]').count() >= 1

    def test_markdown_renders_in_answers(self, page, base_url):
        unlock_story(page, base_url)
        page.wait_for_selector("#story-unlock-overlay", state="hidden", timeout=10000)
        page.locator(".text-card").first.wait_for(state="attached", timeout=10000)
        # Markdown arrives rendered from the build: real <strong>, no
        # surviving asterisks anywhere on the page.
        assert page.locator(".step-data .step-answer strong").count() >= 1
        body_text = page.evaluate("document.body.innerText")
        assert "**bold markdown**" not in body_text

    def test_glossary_links_present_after_unlock(self, page, base_url):
        # Glossary links render at build time like any open story's.
        unlock_story(page, base_url)
        page.wait_for_selector("#story-unlock-overlay", state="hidden", timeout=10000)
        assert page.locator(".glossary-inline-link").count() >= 1

    def test_latex_renders_after_unlock(self, page, base_url):
        # KaTeX loads via the page's has_latex frontmatter; the unlock path
        # renders the injected pool (retrying across the CDN race).
        unlock_story(page, base_url)
        page.wait_for_selector("#story-unlock-overlay", state="hidden", timeout=10000)
        page.wait_for_function("document.querySelectorAll('.katex').length > 0", timeout=15000)

    def test_wrong_key_shows_error(self, page, base_url):
        unlock_story(page, base_url, key=WRONG_KEY)
        error = page.locator("#unlock-error")
        expect(error).to_be_visible(timeout=10000)
        # The message comes from the page's own language strings, so this
        # assertion holds for EN and ES builds alike.
        expected = page.evaluate("window.telarLang.unlock.errorIncorrect")
        assert expected and len(expected) > 5
        expect(error).to_have_text(expected)


class TestCachedKeyReplay:
    """Same-session revisit decrypts with the cached key and takes the same
    apply path as a fresh unlock, unlock event included."""

    def test_cached_replay_shows_story(self, page, base_url):
        unlock_story(page, base_url)
        page.wait_for_selector("#story-unlock-overlay", state="hidden", timeout=10000)
        # Revisit in the same context (sessionStorage carries the cached key).
        page.goto(f"{base_url}{LOCKED_STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector(".step-data .story-step", state="attached", timeout=10000)
        assert not page.locator("#story-unlock-overlay").is_visible()
        page.wait_for_selector(".card-stack .text-card", state="attached", timeout=10000)


class TestPublishedBuildInputs:
    """DOCUMENTED BY DESIGN: Jekyll copies telar-content/ into _site, so the
    source CSVs — including a protected story's plaintext — are fetchable on
    the deployed site. Story locking is a slight barrier for drafts, not
    privacy (the docs say so), and this stays true after the consolidation.
    These tests pin the accepted behavior so the docs claim stays honest."""

    def test_plaintext_csv_is_currently_published(self, page, base_url):
        response = page.request.get(
            f"{base_url}/telar-content/spreadsheets/locked-fixture.csv"
        )
        assert response.ok
        assert "LFIX-A1-SENTINEL" in response.text()

    def test_project_csv_publishes_protected_byline(self, page, base_url):
        # project.csv is served too, and it carries the protected story's
        # byline — same accepted channel through a shared file.
        response = page.request.get(
            f"{base_url}/telar-content/spreadsheets/project.csv"
        )
        assert response.ok
        assert "LFIX-BYLINE-SENTINEL" in response.text()
