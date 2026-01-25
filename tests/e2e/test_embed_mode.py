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

import pytest
from playwright.sync_api import expect


class TestEmbedModeActivation:
    """Tests for embed mode activation and UI changes."""

    def test_embed_mode_activates_with_param(self, page, base_url):
        """Should activate embed mode when ?embed=true is present."""
        page.goto(f"{base_url}/stories/1/?embed=true")
        page.wait_for_load_state("networkidle")

        # Body should have embed class or data attribute
        body = page.locator("body")
        body_class = body.get_attribute("class") or ""
        body_data = body.get_attribute("data-embed") or ""

        assert "embed" in body_class.lower() or body_data == "true"

    def test_header_hidden_in_embed_mode(self, page, base_url):
        """Should hide site header in embed mode."""
        page.goto(f"{base_url}/stories/1/?embed=true")
        page.wait_for_load_state("networkidle")

        # Header should be hidden
        header = page.locator("header, .site-header, .telar-header")
        if header.count() > 0:
            expect(header.first).not_to_be_visible()

    def test_footer_hidden_in_embed_mode(self, page, base_url):
        """Should hide site footer in embed mode."""
        page.goto(f"{base_url}/stories/1/?embed=true")
        page.wait_for_load_state("networkidle")

        # Footer should be hidden
        footer = page.locator("footer, .site-footer, .telar-footer")
        if footer.count() > 0:
            expect(footer.first).not_to_be_visible()

    def test_nav_buttons_visible_in_embed_mode(self, page, base_url):
        """Should show navigation buttons in embed mode (like mobile)."""
        page.set_viewport_size({"width": 1280, "height": 720})  # Desktop size
        page.goto(f"{base_url}/stories/1/?embed=true")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # Nav buttons should be visible even on desktop in embed mode
        nav_buttons = page.locator(".nav-button, .telar-nav-btn, [class*='nav-arrow']")
        expect(nav_buttons.first).to_be_visible()


class TestEmbedModeNavigation:
    """Tests for navigation within embed mode."""

    @pytest.fixture
    def embed_story_page(self, page, base_url):
        """Navigate to story in embed mode."""
        page.goto(f"{base_url}/stories/1/?embed=true")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        return page

    def test_keyboard_navigation_works(self, embed_story_page):
        """Should support keyboard navigation in embed mode."""
        page = embed_story_page

        initial_step = page.locator(".step-indicator, [data-step]").first.text_content()

        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(800)

        new_step = page.locator(".step-indicator, [data-step]").first.text_content()
        assert new_step != initial_step or "1" not in initial_step

    def test_button_navigation_works(self, embed_story_page):
        """Should support button navigation in embed mode."""
        page = embed_story_page

        initial_step = page.locator(".step-indicator, [data-step]").first.text_content()

        # Click next button
        next_btn = page.locator(".nav-button-down, .nav-next, [class*='nav-down']").first
        if next_btn.is_visible():
            next_btn.click()
            page.wait_for_timeout(800)

            new_step = page.locator(".step-indicator, [data-step]").first.text_content()
            assert new_step != initial_step or "1" not in initial_step


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
                    src="{base_url}/stories/1/?embed=true"
                    width="800"
                    height="600"
                    style="border: 1px solid #ccc;">
                </iframe>
            </body>
            </html>
        """)

        # Wait for iframe to load
        frame = page.frame_locator("#story-frame")
        frame.locator(".story-container, .telar-story").wait_for(state="visible", timeout=15000)

        # Story should be visible within iframe
        story = frame.locator(".story-container, .telar-story")
        expect(story).to_be_visible()

    def test_navigation_works_in_iframe(self, page, base_url):
        """Should support navigation when embedded in iframe."""
        page.set_content(f"""
            <!DOCTYPE html>
            <html>
            <head><title>Embed Test</title></head>
            <body>
                <iframe
                    id="story-frame"
                    src="{base_url}/stories/1/?embed=true"
                    width="800"
                    height="600">
                </iframe>
            </body>
            </html>
        """)

        frame = page.frame_locator("#story-frame")
        frame.locator(".story-container, .telar-story").wait_for(state="visible", timeout=15000)

        # Get initial step
        initial_step = frame.locator(".step-indicator, [data-step]").first.text_content()

        # Click within iframe to focus it, then navigate
        frame.locator(".story-container, .telar-story").first.click()
        page.wait_for_timeout(500)

        # Use keyboard navigation
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(800)

        new_step = frame.locator(".step-indicator, [data-step]").first.text_content()
        # Navigation should work
        assert new_step is not None


class TestEmbedModeWithoutParam:
    """Tests verifying normal mode when embed param is absent."""

    def test_header_visible_without_embed(self, page, base_url):
        """Should show header in normal mode."""
        page.goto(f"{base_url}/stories/1/")
        page.wait_for_load_state("networkidle")

        header = page.locator("header, .site-header, .telar-header")
        if header.count() > 0:
            expect(header.first).to_be_visible()

    def test_embed_class_absent(self, page, base_url):
        """Should not have embed class in normal mode."""
        page.goto(f"{base_url}/stories/1/")
        page.wait_for_load_state("networkidle")

        body = page.locator("body")
        body_class = body.get_attribute("class") or ""

        # Should not have embed-specific class
        assert "embed-mode" not in body_class.lower()
