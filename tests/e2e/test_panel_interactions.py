"""
E2E Tests for Panel Interactions

This module tests the layer panel system - the sliding panels that appear
when users click panel buttons. Telar supports up to two layers of panels
per step, each with customizable content.

Panel trigger buttons (.panel-trigger) live inside the cloned story cards
(.text-card) in the card stack; panels themselves are backdrop-less
Bootstrap offcanvas elements (#panel-layer1, #panel-layer2).

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

Version: v1.6.0
"""

import re
import pytest
from playwright.sync_api import expect


def navigate_to_step_with_panel(page, base_url):
    """Navigate to story and advance to a step whose active card has a panel button."""
    page.goto(f"{base_url}/stories/your-story/")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    # Advance until the active card carries a panel trigger
    # (step 2 has layer 1 content in the your-story template)
    for _ in range(5):
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(900)

        panel_btn = page.locator(".text-card.is-active .panel-trigger")
        if panel_btn.count() > 0 and panel_btn.first.is_visible():
            return page

    return page


class TestPanelButtons:
    """Tests for panel button visibility and state."""

    @pytest.fixture
    def story_page_with_panel(self, page, base_url):
        """Navigate to a step with panel content."""
        return navigate_to_step_with_panel(page, base_url)

    def test_panel_button_visible_when_content_exists(self, story_page_with_panel):
        """Should show panel button when step has panel content."""
        page = story_page_with_panel

        # Look for panel trigger button on the active card
        panel_btn = page.locator(".text-card.is-active .panel-trigger")

        # Button should be visible
        expect(panel_btn.first).to_be_visible()

    def test_layer1_button_has_correct_label(self, story_page_with_panel):
        """Should display custom button label from CSV."""
        page = story_page_with_panel

        # Layer 1 button on active card
        layer1_btn = page.locator(".text-card.is-active .panel-trigger[data-panel='layer1']")

        expect(layer1_btn.first).to_be_visible()
        text = layer1_btn.first.text_content()
        assert text and len(text.strip()) > 0


class TestPanelOpening:
    """Tests for opening panels."""

    @pytest.fixture
    def story_page_with_panel(self, page, base_url):
        """Navigate to a step with panel content."""
        return navigate_to_step_with_panel(page, base_url)

    def test_clicking_panel_button_opens_panel(self, story_page_with_panel):
        """Should open panel when button is clicked."""
        page = story_page_with_panel

        panel_btn = page.locator(".text-card.is-active .panel-trigger").first

        expect(panel_btn).to_be_visible()
        panel_btn.click()
        page.wait_for_timeout(500)

        # Panel (Bootstrap offcanvas) should now be visible
        panel = page.locator("#panel-layer1.show, #panel-layer1.showing")
        expect(panel).to_be_visible(timeout=3000)

    def test_panel_has_content(self, story_page_with_panel):
        """Should display content within the panel."""
        page = story_page_with_panel

        panel_btn = page.locator(".text-card.is-active .panel-trigger").first

        expect(panel_btn).to_be_visible()
        panel_btn.click()
        page.wait_for_timeout(500)

        # Panel body should have content
        panel_body = page.locator("#panel-layer1 .offcanvas-body")
        expect(panel_body).to_be_visible()

        text = panel_body.text_content()
        assert text and len(text.strip()) > 0

    def test_panel_slides_in_with_animation(self, story_page_with_panel):
        """Should animate panel sliding in."""
        page = story_page_with_panel

        panel_btn = page.locator(".text-card.is-active .panel-trigger").first

        expect(panel_btn).to_be_visible()

        # Panel should not be open initially
        panel = page.locator("#panel-layer1")
        expect(panel).not_to_have_class(re.compile(r"\bshow\b"))

        # Click to open
        panel_btn.click()

        # Should become visible
        expect(page.locator("#panel-layer1.show")).to_be_visible(timeout=3000)


class TestPanelClosing:
    """Tests for closing panels."""

    @pytest.fixture
    def open_panel_page(self, page, base_url):
        """Navigate to story, advance to panel step, and open a panel."""
        page = navigate_to_step_with_panel(page, base_url)

        panel_btn = page.locator(".text-card.is-active .panel-trigger").first
        if panel_btn.is_visible():
            panel_btn.click()
            page.wait_for_timeout(500)

        return page

    def test_close_button_closes_panel(self, open_panel_page):
        """Should close panel when close button is clicked."""
        page = open_panel_page

        # Verify panel is open
        panel = page.locator("#panel-layer1.show")
        expect(panel).to_be_visible()

        # Find and click close button
        close_btn = page.locator("#panel-layer1 .btn-close")
        expect(close_btn).to_be_visible()
        close_btn.click()
        page.wait_for_timeout(500)

        # Panel should be hidden
        expect(page.locator("#panel-layer1.show")).not_to_be_visible()

    def test_keyboard_reopens_after_close_button(self, open_panel_page):
        """ArrowRight reopens the panel after the offcanvas X closed it.

        The X goes through Bootstrap's own dismiss, not closePanel(), so
        panel state must be reconciled on hidden.bs.offcanvas or the
        keyboard path thinks a panel is still open."""
        page = open_panel_page

        page.locator("#panel-layer1 .btn-close").click()
        page.wait_for_timeout(600)
        expect(page.locator("#panel-layer1.show")).not_to_be_visible()

        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(600)
        expect(page.locator("#panel-layer1")).to_have_class(re.compile(r"\bshow\b"))

    def test_escape_key_closes_panel(self, open_panel_page):
        """Should close panel when Escape key is pressed."""
        page = open_panel_page

        # Verify panel is open
        panel = page.locator("#panel-layer1.show")
        expect(panel).to_be_visible()

        # Press Escape
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # Panel should close
        expect(page.locator("#panel-layer1.show")).not_to_be_visible()


class TestPanelContent:
    """Tests for panel content rendering."""

    @pytest.fixture
    def open_panel_page(self, page, base_url):
        """Navigate to story, advance to panel step, and open a panel."""
        page = navigate_to_step_with_panel(page, base_url)

        panel_btn = page.locator(".text-card.is-active .panel-trigger").first
        if panel_btn.is_visible():
            panel_btn.click()
            page.wait_for_timeout(500)

        return page

    def test_panel_title_displays(self, open_panel_page):
        """Should display panel title if configured."""
        page = open_panel_page

        # Panel title heading
        title = page.locator("#panel-layer1 .offcanvas-title")
        expect(title).to_be_visible()

        text = title.text_content()
        assert text and len(text.strip()) > 0

    def test_markdown_renders_correctly(self, open_panel_page):
        """Should render markdown content as HTML."""
        page = open_panel_page

        panel_body = page.locator("#panel-layer1 .offcanvas-body")
        expect(panel_body).to_be_visible()

        # Check for rendered HTML elements (paragraphs, etc.)
        html = panel_body.inner_html()
        assert "<p>" in html or "<" in html

    def test_links_in_panel_work(self, open_panel_page):
        """Should have clickable links in panel content."""
        page = open_panel_page

        panel_links = page.locator("#panel-layer1 .offcanvas-body a")

        if panel_links.count() > 0:
            # Links should have href
            href = panel_links.first.get_attribute("href")
            assert href is not None


class TestMultiplePanels:
    """Tests for layer 1 and layer 2 panel interactions."""

    @pytest.fixture
    def story_page_with_panel(self, page, base_url):
        """Navigate to a step with panel content."""
        return navigate_to_step_with_panel(page, base_url)

    def test_can_open_layer2_after_layer1(self, story_page_with_panel):
        """Should be able to open layer 2 panel after layer 1."""
        page = story_page_with_panel

        # Check if this step has both layer 1 and layer 2 buttons
        layer1_btn = page.locator(".text-card.is-active .panel-trigger[data-panel='layer1']")
        layer2_btn = page.locator(".text-card.is-active .panel-trigger[data-panel='layer2']")

        if layer1_btn.count() > 0 and layer2_btn.count() > 0:
            # Open layer 1
            layer1_btn.first.click()
            page.wait_for_timeout(500)

            # Check if layer 2 button is visible inside layer 1 panel
            layer2_in_panel = page.locator("#panel-layer1 .panel-trigger[data-panel='layer2']")

            if layer2_in_panel.count() > 0 and layer2_in_panel.is_visible():
                layer2_in_panel.click()
                page.wait_for_timeout(500)

                # Layer 2 panel should be visible
                expect(page.locator("#panel-layer2.show")).to_be_visible()
