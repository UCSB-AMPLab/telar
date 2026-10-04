/**
 * Tests for the URL a glossary link opens.
 *
 * telar.js is a standalone script (not part of the esbuild bundle); it is
 * loaded once as a side-effect import and started with a DOMContentLoaded
 * event. fetch is stubbed so the test reads the URL the click asked for.
 * A link the build wrote carries data-term-url and is fetched as given.
 *
 * @version v1.8.0
 */

import { describe, it, expect, beforeAll, beforeEach, vi } from 'vitest';

class FakeOffcanvas {
  static getInstance() { return null; }
  show() {}
  hide() {}
}

const fetchSpy = vi.fn(() => new Promise(() => {}));

function clickLink(attrs) {
  const host = document.getElementById('host');
  host.innerHTML = `<a href="#" class="glossary-inline-link" ${attrs}>term</a>`;
  host.querySelector('a').click();
  return fetchSpy.mock.calls.at(-1)[0];
}

beforeAll(async () => {
  window.bootstrap = { Offcanvas: FakeOffcanvas };
  globalThis.fetch = fetchSpy;
  document.body.innerHTML = `
    <div id="host"></div>
    <div class="offcanvas" id="panel-glossary">
      <h1 id="panel-glossary-title"></h1><div id="panel-glossary-content"></div>
    </div>`;
  await import('../../assets/js/telar.js');
  document.dispatchEvent(new Event('DOMContentLoaded'));
});

beforeEach(() => {
  fetchSpy.mockClear();
  window.history.replaceState(null, '', '/telar/stories/allegorical-woman/');
});

describe('the URL a glossary link opens', () => {
  it('fetches the URL the build wrote', () => {
    expect(clickLink('data-term-id="IIIF" data-term-url="/telar/glossary/iiif/"'))
      .toBe('/telar/glossary/iiif/');
  });
});
