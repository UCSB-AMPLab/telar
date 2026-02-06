"""
Visual Regression Tests

TEST INSTANCE ONLY - DO NOT PORT TO TELAR/

This module captures screenshots of key views and compares them against
baseline images to detect unintended visual changes. These tests are tied
to the specific demo content in this test instance and will fail on user
sites with different content.

Run locally during development only (excluded from CI).

Baseline images are stored in tests/e2e/snapshots/ and should be committed
to the repository.

To update baselines after intentional changes, delete the baseline files
and run the tests again to regenerate them.

Prerequisites:
    - Jekyll site must be running: bundle exec jekyll serve --port 4001

Run tests:
    pytest tests/e2e/test_visual_regression.py -v --base-url http://127.0.0.1:4001/telar

Version: v0.8.0-beta
"""

import os
from pathlib import Path
import pytest


# Snapshot directory
SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
SNAPSHOT_DIR.mkdir(exist_ok=True)

# Test paths
STORY_PATH = "/stories/your-story/"
OBJECTS_PATH = "/objects/"

# Comparison threshold (0-1, lower = stricter)
PIXEL_THRESHOLD = 0.1


def compare_screenshots(actual: bytes, baseline_path: Path, name: str) -> bool:
    """
    Compare screenshot against baseline. Creates baseline if it doesn't exist.
    Returns True if images match (or baseline was created).
    """
    if not baseline_path.exists():
        # Create baseline
        baseline_path.write_bytes(actual)
        print(f"  Created baseline: {baseline_path.name}")
        return True

    baseline = baseline_path.read_bytes()
    if actual == baseline:
        return True

    # Images differ - save actual for comparison
    actual_path = baseline_path.with_suffix(".actual.png")
    actual_path.write_bytes(actual)
    print(f"  Screenshot differs from baseline. Saved to: {actual_path.name}")
    return False


class TestHomepageVisuals:
    """Visual regression tests for the homepage."""

    def test_homepage_above_fold(self, page, base_url):
        """Capture homepage above-the-fold content."""
        # Set desktop viewport
        page.set_viewport_size({"width": 1280, "height": 720})

        page.goto(base_url + "/")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)

        screenshot = page.screenshot(full_page=False)
        baseline_path = SNAPSHOT_DIR / "homepage-above-fold.png"

        assert compare_screenshots(screenshot, baseline_path, "homepage-above-fold"), \
            f"Homepage above-fold screenshot differs from baseline"

    def test_homepage_full(self, page, base_url):
        """Capture full homepage with stories."""
        # Set desktop viewport
        page.set_viewport_size({"width": 1280, "height": 720})

        page.goto(base_url + "/")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)

        screenshot = page.screenshot(full_page=True)
        baseline_path = SNAPSHOT_DIR / "homepage-full.png"

        assert compare_screenshots(screenshot, baseline_path, "homepage-full"), \
            f"Homepage full screenshot differs from baseline"


class TestStoryVisuals:
    """Visual regression tests for story pages."""

    def test_story_initial_view(self, page, base_url):
        """Capture initial story view."""
        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        screenshot = page.screenshot(full_page=False)
        baseline_path = SNAPSHOT_DIR / "story-initial.png"

        assert compare_screenshots(screenshot, baseline_path, "story-initial"), \
            f"Story initial view screenshot differs from baseline"


class TestObjectsVisuals:
    """Visual regression tests for the objects/collection page."""

    def test_objects_page(self, page, base_url):
        """Capture objects page layout."""
        page.goto(f"{base_url}{OBJECTS_PATH}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        screenshot = page.screenshot(full_page=False)
        baseline_path = SNAPSHOT_DIR / "objects-page.png"

        assert compare_screenshots(screenshot, baseline_path, "objects-page"), \
            f"Objects page screenshot differs from baseline"


class TestMobileVisuals:
    """Visual regression tests for mobile viewport."""

    def test_mobile_homepage(self, page, base_url):
        """Capture mobile homepage."""
        # Set mobile viewport BEFORE navigation
        page.set_viewport_size({"width": 375, "height": 667})

        page.goto(base_url + "/")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)

        screenshot = page.screenshot(full_page=False)
        baseline_path = SNAPSHOT_DIR / "mobile-homepage.png"

        assert compare_screenshots(screenshot, baseline_path, "mobile-homepage"), \
            f"Mobile homepage screenshot differs from baseline"

    def test_mobile_story(self, page, base_url):
        """Capture mobile story view."""
        # Set mobile viewport BEFORE navigation
        page.set_viewport_size({"width": 375, "height": 667})

        page.goto(f"{base_url}{STORY_PATH}")
        page.wait_for_load_state("networkidle")

        # Wait for story container
        page.wait_for_selector(".story-container", state="visible", timeout=10000)
        page.wait_for_timeout(2000)

        screenshot = page.screenshot(full_page=False)
        baseline_path = SNAPSHOT_DIR / "mobile-story.png"

        assert compare_screenshots(screenshot, baseline_path, "mobile-story"), \
            f"Mobile story screenshot differs from baseline"
