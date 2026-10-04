/**
 * Tests for a glossary callout opening the glossary panel.
 *
 * A callout (the :::glossary widget) is a `.glossary-inline-link` whose text
 * is its kind's label and the entry's title. It opens the panel through the
 * inline link's handler, fetching the URL it carries, and the panel is headed
 * by the title alone until the entry's page replaces it.
 *
 * @version v1.8.0
 */

import { describe, it, expect, beforeAll, vi } from 'vitest';

class FakeOffcanvas {
  static getInstance() { return null; }
  show() {}
  hide() {}
}

const fetchSpy = vi.fn(() => new Promise(() => {}));

beforeAll(async () => {
  window.bootstrap = { Offcanvas: FakeOffcanvas };
  globalThis.fetch = fetchSpy;
  document.body.innerHTML = `
    <div id="host"></div>
    <div class="offcanvas" id="panel-glossary">
      <div class="glossary-term-prefix" data-default-label="Key term">Key term:</div>
      <h1 id="panel-glossary-title"></h1><div id="panel-glossary-content"></div>
    </div>`;
  await import('../../assets/js/telar.js');
  document.dispatchEvent(new Event('DOMContentLoaded'));
});

describe('a glossary callout', () => {
  it('opens the entry it links, headed by the title alone', () => {
    document.getElementById('host').innerHTML = `
      <a href="#" class="glossary-inline-link glossary-callout glossary-callout--right"
         data-term-id="carta" data-term-url="/telar/glossary/carta/" data-glossary-kind="source">
        <svg aria-hidden="true"></svg>
        <span class="glossary-callout-text">
          <span class="glossary-callout-kind">Primary source</span>
          <span class="glossary-callout-title">Carta de 1810</span>
        </span>
        <svg aria-hidden="true"></svg>
      </a>`;
    document.querySelector('.glossary-callout').click();

    expect(fetchSpy.mock.calls.at(-1)[0]).toBe('/telar/glossary/carta/');
    expect(document.getElementById('panel-glossary-title').textContent).toBe('Carta de 1810');
  });
});
