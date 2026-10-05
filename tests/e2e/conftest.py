"""
Playwright E2E Test Configuration

This module configures pytest-playwright for end-to-end testing of Telar sites.
It provides fixtures for browser setup, page navigation, and a local Jekyll server.

The tests need the site built with its data and tiles, served under the
/telar baseurl, with its protected stories encrypted. A plain `jekyll serve`
leaves the locked fixture in the clear, and the six unlock tests in
test_story_locking.py then fail on an overlay with nothing to decrypt.

    python scripts/csv_to_json.py
    python scripts/generate_collections.py
    python scripts/generate_iiif.py --base-url http://127.0.0.1:4001/telar
    bundle exec jekyll serve --port 4001 --no-watch
    python scripts/encrypt_protected_stories.py    # once the server is up
    pytest tests/e2e/ -v --base-url http://127.0.0.1:4001/telar

--no-watch keeps Jekyll from regenerating _site over the encrypted page. The
alternative is `python scripts/build_local_site.py --build-only`, which builds
and encrypts, with _site then served statically under /telar on port 4001.

Version: v1.8.0
"""

import pathlib

import pytest
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent


# Default test configuration
DEFAULT_BASE_URL = "http://127.0.0.1:4001/telar"
DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
MOBILE_VIEWPORT = {"width": 375, "height": 667}
TABLET_VIEWPORT = {"width": 768, "height": 1024}


# Note: --base-url is provided by pytest-playwright
# Use: pytest tests/e2e/ --base-url http://127.0.0.1:4001/telar


def _server_is_up(url, timeout=1.5):
    """Whether anything is answering at *url* — not whether that path exists.

    An HTTPError means a server replied, so it counts as up. The base URL is
    the site root without a trailing slash and Jekyll answers it 404, which an
    earlier version read as "no server" and skipped the whole suite with a
    server running in front of it.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 500
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def pytest_collection_modifyitems(config, items):
    """Mark everything here `e2e`, and skip it all when no site is served.

    These tests need a built site on a running server, and without one all of
    them fail. A suite that is red whenever nobody happens to have a server up
    is a suite whose red means nothing: 36 standing failures are exactly the
    cover a real regression hides behind, and they are why a broken import and
    a stale gate both sat unnoticed in this repository for a week.

    Skipped rather than deselected. A skip says in the log which server was
    looked for and was not there, so the coverage that did not run is visible;
    `-m "not e2e"` in the shared options would have hidden it, and would have
    applied to `pytest tests/e2e/` as well, since pytest's `addopts` are not
    scoped to the default run.
    """
    # THIS directory only. A conftest hook in a subdirectory is still handed
    # every collected item in the run, not just the ones beneath it — a first
    # version of this marked and skipped all 3,229.
    mine = [item for item in items
            if HERE in pathlib.Path(str(item.fspath)).resolve().parents]
    if not mine:
        return

    base = config.getoption("base_url", None) or DEFAULT_BASE_URL
    reachable = _server_is_up(base)
    skip = pytest.mark.skip(
        reason=f"no site served at {base} — build it and run "
               f"`bundle exec jekyll serve --port 4001`")
    for item in mine:
        item.add_marker(pytest.mark.e2e)
        if not reachable:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def base_url(base_url):
    """Fall back to the documented local server when none is passed.

    `pytest-base-url` leaves this None unless `--base-url` is given, and the
    tests interpolate it into a request URL, so a plain `pytest` invocation
    failed every one of them with "Invalid URL" rather than saying what was
    missing. The default is the address this module's own docstring tells
    people to serve on.
    """
    return base_url or DEFAULT_BASE_URL


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
    embed_url = f"{base_url}/stories/your-story/?embed=true"
    page.goto(embed_url)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(".story-container, .telar-story", state="visible", timeout=10000)
    return page


# Helper functions for tests

def wait_for_step_change(page, current_step: int, direction: str = "forward", timeout: int = 5000):
    """Wait for the step counter to show the expected step after navigation."""
    expected_step = current_step + 1 if direction == "forward" else current_step - 1
    page.wait_for_function(
        f"document.querySelector('#step-counter')?.textContent?.includes('Step {expected_step} ')",
        timeout=timeout
    )


def get_current_step(page) -> int:
    """Get the current step number from the step counter (0 = intro, counter hidden)."""
    import re
    counter = page.locator("#step-counter")
    if counter.count() == 0:
        return 0
    cls = counter.get_attribute("class") or ""
    if "d-none" in cls:
        return 0
    match = re.search(r'Step (\d+)', counter.text_content() or "")
    return int(match.group(1)) if match else 0


def scroll_to_next_step(page, scroll_amount: int = 300):
    """Simulate scroll event to trigger step navigation."""
    page.mouse.wheel(0, scroll_amount)
    time.sleep(0.7)  # Wait for cooldown


def scroll_to_prev_step(page, scroll_amount: int = 300):
    """Simulate scroll event to go to previous step."""
    page.mouse.wheel(0, -scroll_amount)
    time.sleep(0.7)  # Wait for cooldown
