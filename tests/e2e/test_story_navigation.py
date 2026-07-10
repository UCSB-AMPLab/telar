"""
E2E Tests for Story Navigation

This module tests the core story navigation functionality across different
input methods and viewport sizes. Telar's navigation system adapts to the
device: desktop uses Lenis-driven wheel/keyboard navigation over a card
stack, mobile and embed mode use button taps.

The story renders as a card stack: the original step nodes live hidden in a
.step-data pool, and the visible story is cloned cards (.text-card,
.title-card) plus viewer plates inside .card-stack. The current step is
reported by the #step-counter element ("Step N / M"), which is hidden
(d-none) while the intro card (.story-intro) is showing, and the active
card carries the is-active class.

Prerequisites:
    - Jekyll site must be running: bundle exec jekyll serve --port 4001
    - Or build first: bundle exec jekyll build

Run tests:
    pytest tests/e2e/test_story_navigation.py -v --base-url http://127.0.0.1:4001/telar

Version: v1.6.0
"""

import re
import pytest
from playwright.sync_api import expect


# Use a known story URL (story IDs are slugs, not numbers)
STORY_PATH = "/stories/your-story/"

STEP_COUNTER_RE = re.compile(r"Step (\d+) / \d+")


def read_step_counter(page):
    """Return the step number shown by #step-counter, or None if hidden/empty."""
    counter = page.locator("#step-counter")
    if "d-none" in (counter.get_attribute("class") or ""):
        return None
    match = STEP_COUNTER_RE.search(counter.text_content() or "")
    return int(match.group(1)) if match else None


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
        """Should have story step data on the page."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")

        # Step nodes live hidden in the .step-data pool
        story_steps = page.locator(".step-data .story-step")
        assert story_steps.count() > 0

    def test_viewer_container_loads(self, page, base_url):
        """Should load the viewer plates in the card stack."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")

        viewer = page.locator(".card-stack .viewer-plate")
        expect(viewer.first).to_be_visible(timeout=10000)

    def test_question_visible(self, page, base_url):
        """Should render step questions in the cloned text cards."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        question = page.locator(".text-card .step-question")
        expect(question.first).to_be_visible()
        text = question.first.text_content()
        assert text and len(text.strip()) > 0


class TestKeyboardNavigation:
    """Tests for keyboard-based navigation."""

    def test_arrow_down_advances_step(self, page, base_url):
        """Should advance to step 1 on ArrowDown key."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)  # Wait for initialization

        # Starts at intro (counter hidden); ArrowDown advances to step 1
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(900)  # Wait for scroll animation + cooldown

        counter = page.locator("#step-counter")
        expect(counter).to_be_visible()
        expect(counter).to_contain_text("Step 1 /")
        expect(page.locator(".card-stack .text-card.is-active")).to_be_visible()

    def test_arrow_up_goes_back(self, page, base_url):
        """Should go to previous step on ArrowUp key."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # Advance to step 2
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(900)
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(900)
        expect(page.locator("#step-counter")).to_contain_text("Step 2 /")

        # Go back one step
        page.keyboard.press("ArrowUp")
        page.wait_for_timeout(900)
        expect(page.locator("#step-counter")).to_contain_text("Step 1 /")

    def test_arrow_right_opens_panel(self, page, base_url):
        """Should open the layer 1 panel on ArrowRight when the step has panel content."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # Step 2 of the demo story carries layer 1 content
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(900)
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(900)
        expect(page.locator("#step-counter")).to_contain_text("Step 2 /")

        page.keyboard.press("ArrowRight")
        expect(page.locator("#panel-layer1.show")).to_be_visible(timeout=3000)

    def test_space_advances_step(self, page, base_url):
        """Should advance to next step on Space key."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # Press Space to advance from intro
        page.keyboard.press("Space")
        page.wait_for_timeout(900)

        counter = page.locator("#step-counter")
        expect(counter).to_be_visible()
        expect(counter).to_contain_text("Step 1 /")


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

        # Starts at intro: counter hidden, intro card showing
        expect(page.locator("#step-counter")).to_have_class(re.compile(r"d-none"))
        expect(page.locator(".story-intro")).to_be_visible()

        next_btn = page.locator(".mobile-next")
        expect(next_btn).to_be_visible()
        next_btn.click()
        page.wait_for_timeout(700)  # Mobile nav cooldown is 400ms

        # Counter appears with a step number and an active card shows
        first_step = read_step_counter(page)
        assert first_step is not None
        expect(page.locator(".card-stack .text-card.is-active")).to_be_visible()

        # A second tap advances by exactly one step
        next_btn.click()
        page.wait_for_timeout(700)
        assert read_step_counter(page) == first_step + 1


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
        """Should advance from intro to step 1 on wheel scroll."""
        page = desktop_story_page

        # Scroll down past the intro; Lenis snaps to the first step
        for _ in range(6):
            page.mouse.wheel(0, 250)
            page.wait_for_timeout(120)

        # Counter becomes visible once the scroll settles on a step
        page.wait_for_function(
            "!document.querySelector('#step-counter').classList.contains('d-none')",
            timeout=8000,
        )
        expect(page.locator("#step-counter")).to_contain_text("Step 1 /")
        expect(page.locator(".card-stack .text-card.is-active")).to_be_visible()


class TestStepProgression:
    """Tests for step progression and boundaries."""

    def test_starts_at_intro_step(self, page, base_url):
        """Should start at the intro card with the step counter hidden."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # Intro is its own card at the top of the card stack
        intro = page.locator(".card-stack .story-intro")
        expect(intro).to_be_visible()

        # Step counter stays hidden while the intro is showing
        expect(page.locator("#step-counter")).to_have_class(re.compile(r"d-none"))

    def test_step_changes_update_ui(self, page, base_url):
        """Should update visible content when step changes."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # Advance to next step
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(1000)

        # Counter shows step 1 and the active card displays its question
        expect(page.locator("#step-counter")).to_contain_text("Step 1 /")
        active_card = page.locator(".card-stack .text-card.is-active")
        expect(active_card).to_be_visible()
        question = active_card.locator(".step-question")
        text = question.text_content()
        assert text and len(text.strip()) > 0
