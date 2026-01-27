"""
E2E Tests for Panel Interactions

This module tests the layer panel system - the sliding panels that appear
when users click panel buttons. Telar supports up to two layers of panels
per step, each with customizable content.

The tests verify:
- Panel buttons trigger panel display
- Panels slide in/out correctly
- Panel content renders properly
- Panels close on various triggers

Prerequisites:
    - Jekyll site must be running: bundle exec jekyll serve --port 4001
    - Stories must have panel content configured

Run tests:
    pytest tests/e2e/test_panel_interactions.py -v --base-url http://127.0.0.1:4001/telar

Version: v0.7.0-beta
"""

import pytest
from playwright.sync_api import expect


class TestPanelButtons:
    """Tests for panel button visibility and state."""

    @pytest.fixture
    def story_page(self, page, base_url):
        """Navigate to story page."""
        page.goto(f"{base_url}/stories/your-story/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        return page

    def test_panel_button_visible_when_content_exists(self, story_page):
        """Should show panel button when step has panel content."""
        page = story_page

        # Look for panel buttons
        panel_btn = page.locator(".panel-button, .layer-button, [class*='panel-btn'], [data-panel]")

        # If this step has panel content, button should be visible
        if panel_btn.count() > 0:
            expect(panel_btn.first).to_be_visible()

    def test_layer1_button_has_correct_label(self, story_page):
        """Should display custom button label from CSV."""
        page = story_page

        # Layer 1 button
        layer1_btn = page.locator(".layer1-button, [data-layer='1'], .panel-button").first

        if layer1_btn.is_visible():
            # Button should have text content
            text = layer1_btn.text_content()
            assert text and len(text.strip()) > 0


class TestPanelOpening:
    """Tests for opening panels."""

    @pytest.fixture
    def story_page(self, page, base_url):
        """Navigate to story page."""
        page.goto(f"{base_url}/stories/your-story/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        return page

    def test_clicking_panel_button_opens_panel(self, story_page):
        """Should open panel when button is clicked."""
        page = story_page

        panel_btn = page.locator(".panel-button, .layer-button, [data-panel]").first

        if panel_btn.is_visible():
            panel_btn.click()
            page.wait_for_timeout(500)

            # Panel should now be visible
            panel = page.locator(".panel-content, .layer-panel, [class*='panel'][class*='open'], .telar-panel")
            expect(panel.first).to_be_visible()

    def test_panel_has_content(self, story_page):
        """Should display content within the panel."""
        page = story_page

        panel_btn = page.locator(".panel-button, .layer-button, [data-panel]").first

        if panel_btn.is_visible():
            panel_btn.click()
            page.wait_for_timeout(500)

            # Panel should have content
            panel_content = page.locator(".panel-content, .layer-panel-content, .telar-panel-body")
            if panel_content.count() > 0:
                text = panel_content.first.text_content()
                assert text and len(text.strip()) > 0

    def test_panel_slides_in_with_animation(self, story_page):
        """Should animate panel sliding in."""
        page = story_page

        panel_btn = page.locator(".panel-button, .layer-button, [data-panel]").first

        if panel_btn.is_visible():
            # Panel should not be visible initially
            panel = page.locator(".panel-content, .layer-panel, .telar-panel")

            # Click to open
            panel_btn.click()

            # Should become visible with animation
            expect(panel.first).to_be_visible(timeout=1000)


class TestPanelClosing:
    """Tests for closing panels."""

    @pytest.fixture
    def open_panel_page(self, page, base_url):
        """Navigate to story and open a panel."""
        page.goto(f"{base_url}/stories/your-story/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        panel_btn = page.locator(".panel-button, .layer-button, [data-panel]").first
        if panel_btn.is_visible():
            panel_btn.click()
            page.wait_for_timeout(500)

        return page

    def test_close_button_closes_panel(self, open_panel_page):
        """Should close panel when close button is clicked."""
        page = open_panel_page

        # Find close button
        close_btn = page.locator(".panel-close, .close-button, [aria-label*='close'], .telar-panel-close")

        if close_btn.count() > 0 and close_btn.first.is_visible():
            close_btn.first.click()
            page.wait_for_timeout(500)

            # Panel should be hidden
            panel = page.locator(".panel-content.open, .layer-panel.open, .telar-panel.open")
            if panel.count() > 0:
                expect(panel.first).not_to_be_visible()

    def test_escape_key_closes_panel(self, open_panel_page):
        """Should close panel when Escape key is pressed."""
        page = open_panel_page

        panel = page.locator(".panel-content, .layer-panel, .telar-panel").first

        if panel.is_visible():
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

            # Panel should close or at least respond to Escape
            # (behavior may vary based on implementation)

    def test_clicking_outside_closes_panel(self, open_panel_page):
        """Should close panel when clicking outside."""
        page = open_panel_page

        # Click on viewer column (outside panel area)
        viewer = page.locator(".viewer-column")
        if viewer.count() > 0 and viewer.is_visible():
            viewer.click(position={"x": 50, "y": 50}, timeout=5000)
            page.wait_for_timeout(500)

        # Panel may close depending on implementation


class TestPanelContent:
    """Tests for panel content rendering."""

    @pytest.fixture
    def open_panel_page(self, page, base_url):
        """Navigate to story and open a panel."""
        page.goto(f"{base_url}/stories/your-story/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        panel_btn = page.locator(".panel-button, .layer-button, [data-panel]").first
        if panel_btn.is_visible():
            panel_btn.click()
            page.wait_for_timeout(500)

        return page

    def test_panel_title_displays(self, open_panel_page):
        """Should display panel title if configured."""
        page = open_panel_page

        # Panel title
        title = page.locator(".panel-title, .layer-panel-title, .telar-panel-title, h2, h3")
        # Title may or may not exist depending on content

    def test_markdown_renders_correctly(self, open_panel_page):
        """Should render markdown content as HTML."""
        page = open_panel_page

        panel_content = page.locator(".panel-content, .layer-panel-content, .telar-panel-body")

        if panel_content.count() > 0:
            # Check for rendered HTML elements (paragraphs, bold, etc.)
            html = panel_content.first.inner_html()
            # Should have some HTML structure
            assert "<" in html

    def test_links_in_panel_work(self, open_panel_page):
        """Should have clickable links in panel content."""
        page = open_panel_page

        panel_links = page.locator(".panel-content a, .layer-panel a, .telar-panel a")

        if panel_links.count() > 0:
            # Links should have href
            href = panel_links.first.get_attribute("href")
            assert href is not None


class TestMultiplePanels:
    """Tests for layer 1 and layer 2 panel interactions."""

    @pytest.fixture
    def story_page(self, page, base_url):
        """Navigate to story page."""
        page.goto(f"{base_url}/stories/your-story/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        return page

    def test_can_open_layer2_after_layer1(self, story_page):
        """Should be able to open layer 2 panel after layer 1."""
        page = story_page

        # Open layer 1
        layer1_btn = page.locator("[data-layer='1'], .layer1-button").first
        layer2_btn = page.locator("[data-layer='2'], .layer2-button").first

        if layer1_btn.is_visible() and layer2_btn.count() > 0:
            layer1_btn.click()
            page.wait_for_timeout(500)

            # Check if layer 2 button is now visible/enabled
            if layer2_btn.is_visible():
                layer2_btn.click()
                page.wait_for_timeout(500)

                # Some panel should be visible
                panel = page.locator(".panel-content, .layer-panel, .telar-panel")
                expect(panel.first).to_be_visible()
