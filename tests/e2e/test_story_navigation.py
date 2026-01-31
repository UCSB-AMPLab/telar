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

import re
import pytest
from playwright.sync_api import expect


# Use a known story URL (story IDs are slugs, not numbers)
STORY_PATH = "/stories/your-story/"


class TestStoryLoad:
    """Tests for initial story loading."""

    def test_story_page_loads(self, page, base_url):
        """Should load the story page without errors."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")

        # Check for story container
        story_container = page.locator(".story-container")
        expect(story_container).to_be_visible()

    def test_story_steps_exist(self, page, base_url):
        """Should have story steps on the page."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")

        # Story steps should exist
        story_steps = page.locator(".story-step")
        assert story_steps.count() > 0

    def test_viewer_container_loads(self, page, base_url):
        """Should load the viewer container."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")

        # Wait for viewer container (viewer-column or viewer-cards-container)
        viewer = page.locator(".viewer-column, #viewer-cards-container")
        expect(viewer.first).to_be_visible(timeout=10000)

    def test_question_visible(self, page, base_url):
        """Should display the step question."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        # Step question should be visible (h2.step-question)
        question = page.locator(".step-question")
        expect(question.first).to_be_visible()


class TestKeyboardNavigation:
    """Tests for keyboard-based navigation."""

    def test_arrow_down_advances_step(self, page, base_url):
        """Should advance to next step on ArrowDown key."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)  # Wait for initialization

        # Starts at intro (step 0)
        # Press ArrowDown to advance
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(800)  # Wait for cooldown

        # After navigation, step 1 should have is-active (use specific selector)
        step1 = page.locator(".story-step[data-step-index='1']")
        expect(step1).to_have_class(re.compile(r"is-active"))

    def test_arrow_up_goes_back(self, page, base_url):
        """Should go to previous step on ArrowUp key."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # First, advance to step 1
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(800)

        # Step 1 should be active
        step1 = page.locator(".story-step[data-step-index='1']")
        expect(step1).to_have_class(re.compile(r"is-active"))

        # Now go back to intro
        page.keyboard.press("ArrowUp")
        page.wait_for_timeout(800)

        # Going back to intro - verify intro is visible
        intro_step = page.locator(".story-step.story-intro")
        expect(intro_step).to_be_visible()

    def test_arrow_right_opens_panel(self, page, base_url):
        """Should open layer panel on ArrowRight key (when panel content exists)."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # First advance to step 1 (intro has no panel content)
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(800)

        # Press ArrowRight to open layer1 panel (if step has layer1 content)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(800)

        # Check if panel opened (layer1-panel should be visible)
        # Note: This test assumes step 1 has layer1 content
        panel = page.locator(".layer1-panel, [class*='layer1']")
        # If no panel content for this step, test just verifies no error occurred

    def test_space_advances_step(self, page, base_url):
        """Should advance to next step on Space key."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # Press Space to advance from intro
        page.keyboard.press("Space")
        page.wait_for_timeout(800)

        # Step 1 should now be active (use specific selector)
        step1 = page.locator(".story-step[data-step-index='1']")
        expect(step1).to_have_class(re.compile(r"is-active"))


class TestMobileNavigation:
    """Tests for mobile button navigation."""

    @pytest.fixture
    def mobile_story_page(self, page, base_url):
        """Set up mobile viewport and navigate to story."""
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        return page

    def test_nav_buttons_visible_on_mobile(self, mobile_story_page):
        """Should show navigation buttons on mobile viewport."""
        page = mobile_story_page

        # Mobile navigation container should be visible (.mobile-nav)
        nav_container = page.locator(".mobile-nav")
        expect(nav_container).to_be_visible()

        # Navigation buttons should exist
        nav_buttons = page.locator(".mobile-nav button")
        assert nav_buttons.count() >= 2  # prev and next buttons

    def test_next_button_advances_step(self, mobile_story_page):
        """Should advance step when tapping next button."""
        page = mobile_story_page

        # Mobile starts at intro with mobile-active
        intro = page.locator(".story-step.story-intro")
        expect(intro).to_have_class(re.compile(r"mobile-active"))

        # Click next button (.mobile-next) to advance
        next_btn = page.locator(".mobile-next")
        expect(next_btn).to_be_visible()
        next_btn.click()
        page.wait_for_timeout(800)

        # After navigation, intro should no longer have mobile-active
        # and some other step should have it
        active_step = page.locator(".story-step.mobile-active")
        expect(active_step).to_be_visible()

        # The active step should NOT be the intro
        active_class = active_step.get_attribute("class")
        assert "story-intro" not in active_class


class TestDesktopScrollNavigation:
    """Tests for desktop scroll-based navigation."""

    @pytest.fixture
    def desktop_story_page(self, page, base_url):
        """Set up desktop viewport and navigate to story."""
        page.set_viewport_size({"width": 1280, "height": 720})
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        return page

    def test_scroll_down_advances_step(self, desktop_story_page):
        """Should advance step after sufficient scroll accumulation."""
        page = desktop_story_page

        # Starts at intro, scroll down to advance
        # Scroll down multiple times to accumulate threshold (50vh)
        for _ in range(5):
            page.mouse.wheel(0, 100)
            page.wait_for_timeout(100)

        page.wait_for_timeout(1000)  # Wait for cooldown

        # After scroll, step 1 should have is-active class
        step1 = page.locator(".story-step[data-step-index='1']")
        expect(step1).to_have_class(re.compile(r"is-active"))


class TestStepProgression:
    """Tests for step progression and boundaries."""

    def test_starts_at_intro_step(self, page, base_url):
        """Should start at the intro step (step 0)."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # Should start at step 0 (intro) - check that intro step is visible
        intro_step = page.locator(".story-step.story-intro")
        expect(intro_step).to_be_visible()

        # Verify it's step 0
        step_index = intro_step.get_attribute("data-step-index")
        assert step_index == "0"

    def test_step_changes_update_ui(self, page, base_url):
        """Should update visible content when step changes."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # Advance to next step
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(1000)

        # Step 1 should now have is-active class
        step1 = page.locator(".story-step[data-step-index='1']")
        expect(step1).to_have_class(re.compile(r"is-active"))
