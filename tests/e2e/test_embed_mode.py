"""
E2E Tests for Embed Mode

This module tests Telar's embed mode, which allows stories to be embedded
in iframes on external websites. Embed mode hides certain UI elements and
always shows navigation buttons (like mobile mode).

Embed mode is activated by adding ?embed=true to the story URL.

Prerequisites:
    - Jekyll site must be running: bundle exec jekyll serve --port 4001

Run tests:
    pytest tests/e2e/test_embed_mode.py -v --base-url http://127.0.0.1:4001/telar

Version: v0.7.0-beta
"""

import re
import pytest
from playwright.sync_api import expect


# Use a known story URL (story IDs are slugs, not numbers)
STORY_PATH = "/stories/your-story/"


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

    def test_header_hidden_in_embed_mode(self, page, base_url):
        """Should hide site header in embed mode."""
        page.goto(f"{base_url}{STORY_PATH}?embed=true")
        page.wait_for_load_state("networkidle")

        # Header should be hidden
        header = page.locator("header, .site-header, .telar-header")
        if header.count() > 0:
            expect(header.first).not_to_be_visible()

    def test_footer_hidden_in_embed_mode(self, page, base_url):
        """Should hide site footer in embed mode."""
        page.goto(f"{base_url}{STORY_PATH}?embed=true")
        page.wait_for_load_state("networkidle")

        # Footer should be hidden
        footer = page.locator("footer, .site-footer, .telar-footer")
        if footer.count() > 0:
            expect(footer.first).not_to_be_visible()

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

        # Embed mode shows mobile-nav buttons
        next_btn = page.locator(".mobile-next")
        expect(next_btn).to_be_visible()

        # Click next button
        next_btn.click()
        page.wait_for_timeout(800)

        # Step 1 should now be active (mobile-active class in embed mode)
        step1 = page.locator(".story-step[data-step='1']")
        expect(step1).to_have_class(re.compile(r"mobile-active"))


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
        page.set_content(f"""
            <!DOCTYPE html>
            <html>
            <head><title>Embed Test</title></head>
            <body>
                <iframe
                    id="story-frame"
                    src="{base_url}{STORY_PATH}?embed=true"
                    width="800"
                    height="600">
                </iframe>
            </body>
            </html>
        """)

        frame = page.frame_locator("#story-frame")
        frame.locator(".story-container").wait_for(state="visible", timeout=15000)

        # Verify intro is visible in iframe
        intro = frame.locator(".story-step.story-intro")
        expect(intro).to_be_visible()

        # Use button navigation (keyboard nav not supported in embed mode)
        next_btn = frame.locator(".mobile-next")
        expect(next_btn).to_be_visible()
        next_btn.click()
        page.wait_for_timeout(800)

        # Step 1 should be active now (mobile-active class in embed mode)
        step1 = frame.locator(".story-step[data-step='1']")
        expect(step1).to_have_class(re.compile(r"mobile-active"))


class TestEmbedModeWithoutParam:
    """Tests verifying normal mode when embed param is absent."""

    def test_header_visible_without_embed(self, page, base_url):
        """Should show header in normal mode."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")

        header = page.locator("header, .site-header, .telar-header")
        if header.count() > 0:
            expect(header.first).to_be_visible()

    def test_embed_class_absent(self, page, base_url):
        """Should not have embed class in normal mode."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")

        body = page.locator("body")
        body_class = body.get_attribute("class") or ""

        # Should not have embed-specific class
        assert "embed-mode" not in body_class.lower()
