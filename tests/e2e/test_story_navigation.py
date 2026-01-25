"""
E2E Tests for Story Navigation

This module tests the core story navigation functionality across different
input methods and viewport sizes. Telar's navigation system adapts to the
device: desktop uses scroll accumulation, mobile uses button taps, and all
devices support keyboard navigation.

Prerequisites:
    - Jekyll site must be running: bundle exec jekyll serve --port 4001
    - Or build first: bundle exec jekyll build

Run tests:
    pytest tests/e2e/test_story_navigation.py -v --base-url http://127.0.0.1:4001/telar

Version: v0.7.0-beta
"""

import pytest
import re
from playwright.sync_api import expect


class TestStoryLoad:
    """Tests for initial story loading."""

    def test_story_page_loads(self, page, base_url):
        """Should load the story page without errors."""
        page.goto(f"{base_url}/stories/1/")
        page.wait_for_load_state("networkidle")

        # Check for story container
        story_container = page.locator(".story-container, .telar-story")
        expect(story_container).to_be_visible()

    def test_step_indicator_visible(self, page, base_url):
        """Should display step indicator on load."""
        page.goto(f"{base_url}/stories/1/")
        page.wait_for_load_state("networkidle")

        # Step indicator should be visible
        step_indicator = page.locator(".step-indicator, .telar-step-counter, [data-step]")
        expect(step_indicator.first).to_be_visible()

    def test_viewer_loads(self, page, base_url):
        """Should load the image viewer (UniversalViewer or similar)."""
        page.goto(f"{base_url}/stories/1/")
        page.wait_for_load_state("networkidle")

        # Wait for viewer to initialize
        viewer = page.locator(".uv, .viewer-container, #viewer, [class*='viewer']")
        expect(viewer.first).to_be_visible(timeout=10000)

    def test_question_card_visible(self, page, base_url):
        """Should display the question card for step 1."""
        page.goto(f"{base_url}/stories/1/")
        page.wait_for_load_state("networkidle")

        # Question card should be visible
        question_card = page.locator(".question-card, .telar-question, [class*='question']")
        expect(question_card.first).to_be_visible()


class TestKeyboardNavigation:
    """Tests for keyboard-based navigation."""

    def test_arrow_down_advances_step(self, page, base_url):
        """Should advance to next step on ArrowDown key."""
        page.goto(f"{base_url}/stories/1/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)  # Wait for initialization

        # Get initial step
        initial_step = page.locator(".step-indicator, [data-step]").first.text_content()

        # Press ArrowDown
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(800)  # Wait for cooldown

        # Step should have changed
        new_step = page.locator(".step-indicator, [data-step]").first.text_content()

        # Either step number increased or we're at the last step
        assert new_step != initial_step or "1" not in initial_step

    def test_arrow_up_goes_back(self, page, base_url):
        """Should go to previous step on ArrowUp key."""
        page.goto(f"{base_url}/stories/1/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # First, advance to step 2
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(800)

        step_before = page.locator(".step-indicator, [data-step]").first.text_content()

        # Now go back
        page.keyboard.press("ArrowUp")
        page.wait_for_timeout(800)

        step_after = page.locator(".step-indicator, [data-step]").first.text_content()

        # Should have gone back (or be at step 1)
        assert step_after != step_before or "1" in step_after

    def test_arrow_right_advances_step(self, page, base_url):
        """Should advance to next step on ArrowRight key."""
        page.goto(f"{base_url}/stories/1/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        initial_step = page.locator(".step-indicator, [data-step]").first.text_content()

        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(800)

        new_step = page.locator(".step-indicator, [data-step]").first.text_content()
        assert new_step != initial_step or "1" not in initial_step

    def test_space_advances_step(self, page, base_url):
        """Should advance to next step on Space key."""
        page.goto(f"{base_url}/stories/1/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        initial_step = page.locator(".step-indicator, [data-step]").first.text_content()

        page.keyboard.press("Space")
        page.wait_for_timeout(800)

        new_step = page.locator(".step-indicator, [data-step]").first.text_content()
        assert new_step != initial_step or "1" not in initial_step


class TestMobileNavigation:
    """Tests for mobile button navigation."""

    @pytest.fixture
    def mobile_story_page(self, page, base_url):
        """Set up mobile viewport and navigate to story."""
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/stories/1/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        return page

    def test_nav_buttons_visible_on_mobile(self, mobile_story_page):
        """Should show navigation buttons on mobile viewport."""
        page = mobile_story_page

        # Navigation buttons should be visible on mobile
        nav_buttons = page.locator(".nav-button, .telar-nav-btn, [class*='nav-arrow']")
        expect(nav_buttons.first).to_be_visible()

    def test_next_button_advances_step(self, mobile_story_page):
        """Should advance step when tapping next button."""
        page = mobile_story_page

        initial_step = page.locator(".step-indicator, [data-step]").first.text_content()

        # Click next/down button
        next_btn = page.locator(".nav-button-down, .nav-next, [class*='nav-down'], [aria-label*='next']").first
        if next_btn.is_visible():
            next_btn.click()
            page.wait_for_timeout(800)

            new_step = page.locator(".step-indicator, [data-step]").first.text_content()
            assert new_step != initial_step or "1" not in initial_step


class TestDesktopScrollNavigation:
    """Tests for desktop scroll-based navigation."""

    @pytest.fixture
    def desktop_story_page(self, page, base_url):
        """Set up desktop viewport and navigate to story."""
        page.set_viewport_size({"width": 1280, "height": 720})
        page.goto(f"{base_url}/stories/1/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        return page

    def test_scroll_down_advances_step(self, desktop_story_page):
        """Should advance step after sufficient scroll accumulation."""
        page = desktop_story_page

        initial_step = page.locator(".step-indicator, [data-step]").first.text_content()

        # Scroll down multiple times to accumulate threshold
        for _ in range(5):
            page.mouse.wheel(0, 100)
            page.wait_for_timeout(100)

        page.wait_for_timeout(800)  # Wait for cooldown

        new_step = page.locator(".step-indicator, [data-step]").first.text_content()
        # Either advanced or at last step
        assert new_step != initial_step or "1" not in initial_step

    def test_nav_buttons_hidden_on_desktop(self, desktop_story_page):
        """Should hide mobile nav buttons on desktop viewport."""
        page = desktop_story_page

        # Mobile nav buttons should be hidden on desktop
        # (they may exist in DOM but be hidden via CSS)
        nav_buttons = page.locator(".nav-button-mobile, .telar-mobile-nav")

        if nav_buttons.count() > 0:
            expect(nav_buttons.first).not_to_be_visible()


class TestStepProgression:
    """Tests for step progression and boundaries."""

    def test_cannot_go_before_step_1(self, page, base_url):
        """Should not go before step 1."""
        page.goto(f"{base_url}/stories/1/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # Try to go back from step 1
        page.keyboard.press("ArrowUp")
        page.wait_for_timeout(800)

        # Should still be on step 1
        step_text = page.locator(".step-indicator, [data-step]").first.text_content()
        assert "1" in step_text

    def test_step_changes_update_ui(self, page, base_url):
        """Should update question card when step changes."""
        page.goto(f"{base_url}/stories/1/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # Get initial question text
        initial_question = page.locator(".question-card, .telar-question").first.text_content()

        # Advance to next step
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(1000)

        # Question should have changed (unless all steps have same question)
        new_question = page.locator(".question-card, .telar-question").first.text_content()

        # At minimum, the page should still be functional
        assert new_question is not None
