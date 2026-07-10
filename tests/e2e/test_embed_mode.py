"""
E2E Tests for Embed Mode

This module tests Telar's embed mode, which allows stories to be embedded
in iframes on external websites. Embed mode hides story chrome (the share
button), shows the embed banner, and always shows navigation buttons (like
mobile mode).

Embed mode is activated by adding ?embed=true to the story URL.

Prerequisites:
    - Jekyll site must be running: bundle exec jekyll serve --port 4001

Run tests:
    pytest tests/e2e/test_embed_mode.py -v --base-url http://127.0.0.1:4001/telar

Version: v1.6.0
"""

import re
import pytest
from playwright.sync_api import expect


# Use a known story URL (story IDs are slugs, not numbers)
STORY_PATH = "/stories/your-story/"

STEP_COUNTER_RE = re.compile(r"Step (\d+) / \d+")


def read_step_counter(page_or_frame):
    """Return the step number shown by #step-counter, or None if hidden/empty."""
    counter = page_or_frame.locator("#step-counter")
    if "d-none" in (counter.get_attribute("class") or ""):
        return None
    match = STEP_COUNTER_RE.search(counter.text_content() or "")
    return int(match.group(1)) if match else None


class TestEmbedModeActivation:
    """Tests for embed mode activation and UI changes."""

    def test_embed_mode_activates_with_param(self, page, base_url):
        """Should activate embed mode when ?embed=true is present."""
        page.goto(f"{base_url}{STORY_PATH}?embed=true")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        # Body should have embed-mode class
        body = page.locator("body")
        expect(body).to_have_class(re.compile(r"embed-mode"))

    def test_share_button_hidden_in_embed_mode(self, page, base_url):
        """Should hide the share button (story chrome) in embed mode."""
        page.goto(f"{base_url}{STORY_PATH}?embed=true")
        page.wait_for_load_state("networkidle")

        share_btn = page.locator(".share-button")
        assert share_btn.count() > 0
        expect(share_btn.first).not_to_be_visible()

    def test_embed_banner_shown_in_embed_mode(self, page, base_url):
        """Should display the embed banner in embed mode."""
        page.goto(f"{base_url}{STORY_PATH}?embed=true")
        page.wait_for_load_state("networkidle")

        banner = page.locator(".telar-embed-banner")
        expect(banner.first).to_be_visible()

    def test_nav_buttons_visible_in_embed_mode(self, page, base_url):
        """Should show navigation buttons in embed mode (like mobile)."""
        page.set_viewport_size({"width": 1280, "height": 720})  # Desktop size
        page.goto(f"{base_url}{STORY_PATH}?embed=true")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # Mobile-style nav buttons should be visible in embed mode
        nav_container = page.locator(".mobile-nav")
        expect(nav_container).to_be_visible()


class TestEmbedModeNavigation:
    """Tests for navigation within embed mode."""

    @pytest.fixture
    def embed_story_page(self, page, base_url):
        """Navigate to story in embed mode."""
        page.goto(f"{base_url}{STORY_PATH}?embed=true")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        return page

    @pytest.mark.skip(reason="Embed mode uses button navigation only, keyboard nav not supported")
    def test_keyboard_navigation_works(self, embed_story_page):
        """Keyboard navigation is not supported in embed mode — use buttons instead."""
        pass

    def test_button_navigation_works(self, embed_story_page):
        """Should support button navigation in embed mode."""
        page = embed_story_page

        # Counter is hidden at the intro
        expect(page.locator("#step-counter")).to_have_class(re.compile(r"d-none"))

        # Embed mode shows mobile-nav buttons; prev is disabled on the intro
        next_btn = page.locator(".mobile-next")
        expect(next_btn).to_be_visible()
        expect(page.locator(".mobile-prev")).to_be_disabled()

        # Click next button
        next_btn.click()
        page.wait_for_timeout(700)  # Nav cooldown is 400ms

        # The first tap dismisses the intro into step 1 — never further
        first_step = read_step_counter(page)
        assert first_step == 1
        expect(page.locator(".card-stack .text-card.is-active")).to_be_visible()

        # A second click advances by exactly one step
        next_btn.click()
        page.wait_for_timeout(700)
        assert read_step_counter(page) == first_step + 1

    def test_nav_buttons_on_screen_in_wide_embed(self, page, base_url):
        """Both nav buttons render inside the viewport at desktop embed widths.

        Desktop-embed placement (centred nav, 20% left offset) applies above
        the vertical-layout boundary (_responsive.scss $telar-vertical-min-width,
        1024px). 1200px is comfortably above that boundary. The desktop-embed
        nav is centred at 20% of the viewport with intrinsic width; if the box
        inherits the vertical-layout right pin it stretches across the
        viewport and the buttons land off-screen."""
        page.set_viewport_size({"width": 1200, "height": 600})
        page.goto(f"{base_url}{STORY_PATH}?embed=true")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        for selector in (".mobile-nav .mobile-prev", ".mobile-nav .mobile-next"):
            box = page.locator(selector).bounding_box()
            assert box is not None, f"{selector} has no box"
            assert box["x"] >= 0, f"{selector} starts off-screen at x={box['x']}"
            assert box["x"] + box["width"] <= 1200, f"{selector} overflows right"


class TestEmbedModeIframe:
    """Tests for embed mode within an iframe context."""

    def test_story_loads_in_iframe(self, page, base_url):
        """Should load story correctly within an iframe."""
        # Create a simple HTML page with an iframe
        page.set_content(f"""
            <!DOCTYPE html>
            <html>
            <head><title>Embed Test</title></head>
            <body>
                <h1>Embedded Story</h1>
                <iframe
                    id="story-frame"
                    src="{base_url}{STORY_PATH}?embed=true"
                    width="800"
                    height="600"
                    style="border: 1px solid #ccc;">
                </iframe>
            </body>
            </html>
        """)

        # Wait for iframe to load
        frame = page.frame_locator("#story-frame")
        frame.locator(".story-container").wait_for(state="visible", timeout=15000)

        # Story should be visible within iframe
        story = frame.locator(".story-container")
        expect(story).to_be_visible()

    def test_navigation_works_in_iframe(self, page, base_url):
        """Should support button navigation when embedded in iframe."""
        # Embeds at or below the vertical-layout boundary (_responsive.scss
        # $telar-vertical-min-width, 1024px) use the right-edge stacked nav
        # placement, which keeps the buttons on-screen. 768px is below that
        # boundary.
        page.set_content(f"""
            <!DOCTYPE html>
            <html>
            <head><title>Embed Test</title></head>
            <body>
                <iframe
                    id="story-frame"
                    src="{base_url}{STORY_PATH}?embed=true"
                    width="768"
                    height="600">
                </iframe>
            </body>
            </html>
        """)

        frame = page.frame_locator("#story-frame")
        frame.locator(".story-container").wait_for(state="visible", timeout=15000)
        page.wait_for_timeout(1000)

        # Verify intro card is visible in iframe, counter hidden
        intro = frame.locator(".card-stack .story-intro")
        expect(intro).to_be_visible()
        expect(frame.locator("#step-counter")).to_have_class(re.compile(r"d-none"))

        # Right-edge stacked nav keeps both buttons on-screen at this width
        for selector in (".mobile-nav .mobile-prev", ".mobile-nav .mobile-next"):
            box = frame.locator(selector).bounding_box()
            assert box is not None, f"{selector} has no box"
            assert box["x"] >= 0, f"{selector} starts off-screen at x={box['x']}"
            assert box["x"] + box["width"] <= 768, f"{selector} overflows right"

        # Use button navigation (keyboard nav not supported in embed mode)
        next_btn = frame.locator(".mobile-next")
        expect(next_btn).to_be_visible()
        next_btn.click()
        page.wait_for_timeout(700)

        # Counter appears with a step number and an active card shows
        assert read_step_counter(frame) is not None
        expect(frame.locator(".card-stack .text-card.is-active")).to_be_visible()


class TestEmbedModeWithoutParam:
    """Tests verifying normal mode when embed param is absent."""

    def test_share_button_visible_without_embed(self, page, base_url):
        """Should show the share button (story chrome) in normal mode."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")

        share_btn = page.locator(".share-button")
        expect(share_btn.first).to_be_visible()

    def test_embed_class_absent(self, page, base_url):
        """Should not have embed class in normal mode."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")

        body = page.locator("body")
        body_class = body.get_attribute("class") or ""

        # Should not have embed-specific class
        assert "embed-mode" not in body_class.lower()
