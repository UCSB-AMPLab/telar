"""
Playwright E2E Test Configuration

This module configures pytest-playwright for end-to-end testing of Telar sites.
It provides fixtures for browser setup, page navigation, and a local Jekyll server.

The tests require a pre-built Jekyll site. Before running E2E tests:
1. Build the site: bundle exec jekyll build
2. Run tests: pytest tests/e2e/ -v

For development with live server:
    pytest tests/e2e/ -v --base-url http://127.0.0.1:4001/telar

Version: v0.7.0-beta
"""

import pytest
import time


# Default test configuration
DEFAULT_BASE_URL = "http://127.0.0.1:4001/telar"
DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
MOBILE_VIEWPORT = {"width": 375, "height": 667}
TABLET_VIEWPORT = {"width": 768, "height": 1024}


# Note: --base-url is provided by pytest-playwright
# Use: pytest tests/e2e/ --base-url http://127.0.0.1:4001/telar


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, request):
    """Configure browser context with viewport and other settings."""
    return {
        **browser_context_args,
        "viewport": DEFAULT_VIEWPORT,
        "ignore_https_errors": True,
    }


@pytest.fixture
def desktop_page(page):
    """Page fixture with desktop viewport."""
    page.set_viewport_size(DEFAULT_VIEWPORT)
    return page


@pytest.fixture
def mobile_page(page):
    """Page fixture with mobile viewport."""
    page.set_viewport_size(MOBILE_VIEWPORT)
    return page


@pytest.fixture
def tablet_page(page):
    """Page fixture with tablet viewport."""
    page.set_viewport_size(TABLET_VIEWPORT)
    return page


@pytest.fixture
def story_page(page, base_url):
    """Navigate to the first story and wait for it to load."""
    # Navigate to home page first
    page.goto(base_url)
    page.wait_for_load_state("networkidle")

    # Click on first story link (if on catalog page)
    story_link = page.locator("a.story-link, .story-card a, [data-story-id] a").first
    if story_link.count() > 0:
        story_link.click()
        page.wait_for_load_state("networkidle")

    # Wait for story container to be visible
    page.wait_for_selector(".story-container, .telar-story", state="visible", timeout=10000)

    return page


@pytest.fixture
def embed_page(page, base_url):
    """Navigate to embed mode version of the story."""
    # Append embed=true parameter
    embed_url = f"{base_url}/stories/1/?embed=true"
    page.goto(embed_url)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(".story-container, .telar-story", state="visible", timeout=10000)
    return page


# Helper functions for tests

def wait_for_step_change(page, current_step: int, direction: str = "forward", timeout: int = 5000):
    """Wait for step indicator to change after navigation."""
    expected_step = current_step + 1 if direction == "forward" else current_step - 1
    page.wait_for_function(
        f"document.querySelector('.step-indicator, [data-current-step]')?.textContent?.includes('{expected_step}')",
        timeout=timeout
    )


def get_current_step(page) -> int:
    """Get the current step number from the UI."""
    step_text = page.locator(".step-indicator, [data-current-step]").first.text_content()
    # Extract number from text like "Step 2 of 5" or just "2"
    import re
    match = re.search(r'\d+', step_text or "1")
    return int(match.group()) if match else 1


def scroll_to_next_step(page, scroll_amount: int = 300):
    """Simulate scroll event to trigger step navigation."""
    page.mouse.wheel(0, scroll_amount)
    time.sleep(0.7)  # Wait for cooldown


def scroll_to_prev_step(page, scroll_amount: int = 300):
    """Simulate scroll event to go to previous step."""
    page.mouse.wheel(0, -scroll_amount)
    time.sleep(0.7)  # Wait for cooldown
