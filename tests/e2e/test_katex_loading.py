"""
E2E Tests for KaTeX Arriving Late, or Not at All

Story pages load KaTeX from the CDN after the page itself, so a reader can
open a panel before it arrives: a deep link naming a layer opens it at load.
The loader renders that panel when KaTeX arrives. If a KaTeX script fails to
load, the loader stops, says so in the console, and leaves every formula as
the author wrote it.

The KaTeX scripts are held or failed with page.route, so the order is the
same on every run. The panel is the second layer of the second step of
your-story, whose text holds display maths.

Prerequisites:
    - Data pipeline run: python scripts/csv_to_json.py && python scripts/generate_collections.py
    - Jekyll site running: bundle exec jekyll serve --port 4001

Run tests:
    pytest tests/e2e/test_katex_loading.py -v --base-url http://127.0.0.1:4001/telar

Version: v1.8.0
"""

import re

from playwright.sync_api import expect

PANEL_DEEP_LINK = "/stories/your-story/#s2l2"
KATEX_SCRIPT = re.compile(r"cdn\.jsdelivr\.net/npm/katex@.*\.js$")
SOURCE = "\\begin{align}"


def test_a_panel_opened_before_katex_arrives_is_rendered_when_it_does(page, base_url):
    held = []
    released = {"now": False}

    def hold(route):
        if released["now"]:
            route.continue_()
        else:
            held.append(route)

    page.route(KATEX_SCRIPT, hold)
    # A held script holds the load event too, so the page is taken at
    # DOMContentLoaded.
    page.goto(f"{base_url}{PANEL_DEEP_LINK}", wait_until="domcontentloaded")
    content = page.locator("#panel-layer2-content")
    expect(content).to_contain_text(SOURCE, timeout=15000)
    assert held, "the KaTeX scripts were requested and held"
    assert content.locator(".katex").count() == 0, "held KaTeX cannot have rendered"

    released["now"] = True
    for route in held:
        route.continue_()
    page.wait_for_function("typeof window.telarRenderLatex === 'function'", timeout=30000)
    expect(content.locator(".katex").first).to_be_attached(timeout=10000)
    assert SOURCE not in content.inner_text()


def test_a_failed_katex_script_leaves_the_formulas_as_written(page, base_url):
    page.route(KATEX_SCRIPT, lambda route: route.abort())
    with page.expect_console_message(
            lambda message: "KaTeX could not be loaded" in message.text, timeout=15000):
        page.goto(f"{base_url}{PANEL_DEEP_LINK}")
    content = page.locator("#panel-layer2-content")
    expect(content).to_contain_text(SOURCE, timeout=15000)
    assert content.locator(".katex").count() == 0
    assert page.evaluate("typeof window.telarRenderLatex") == "undefined"
