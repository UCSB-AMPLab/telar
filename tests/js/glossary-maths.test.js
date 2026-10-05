/**
 * Tests for the maths in a glossary term fetched into the panel.
 *
 * telar.js fetches the term's page and copies its `.glossary-content` into
 * the panel. With KaTeX on the page it renders the panel. Without it, a term
 * whose page is flagged data-has-latex asks window.telarLoadKatex for KaTeX,
 * which renders the panel once it arrives; a term with no maths asks for
 * nothing. fetch is stubbed with the term page's HTML.
 *
 * @version v1.8.0
 */

import { describe, it, expect, beforeAll, beforeEach, vi } from 'vitest';

class FakeOffcanvas {
  static getInstance() { return null; }
  show() {}
  hide() {}
}

let termPage = '';
globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, text: () => Promise.resolve(termPage) }));

async function clickTermLink(flag) {
  termPage = `<h1>Overlap</h1><div class="glossary-content"${flag ? ' data-has-latex' : ''}>`
    + '<p>Inline $x^4$.</p></div>';
  const host = document.getElementById('host');
  host.innerHTML = '<a href="#" class="glossary-inline-link" data-term-id="overlap" '
    + 'data-term-url="/telar/glossary/overlap/">Overlap</a>';
  host.querySelector('a').click();
  await vi.waitFor(() => expect(document.getElementById('panel-glossary-content').textContent)
    .toContain('Inline'));
}

beforeAll(async () => {
  window.bootstrap = { Offcanvas: FakeOffcanvas };
  document.body.innerHTML = `
    <div id="host"></div>
    <div class="offcanvas" id="panel-glossary">
      <h1 id="panel-glossary-title"></h1><div id="panel-glossary-content"></div>
    </div>`;
  await import('../../assets/js/telar.js');
  document.dispatchEvent(new Event('DOMContentLoaded'));
});

beforeEach(() => {
  delete window.telarRenderLatex;
  window.telarLoadKatex = vi.fn();
});

describe('the maths in a glossary term', () => {
  it('asks for KaTeX when the term holds maths and the page has none', async () => {
    await clickTermLink(true);

    expect(window.telarLoadKatex).toHaveBeenCalledTimes(1);
  });

  it('asks for nothing when the term holds no maths', async () => {
    await clickTermLink(false);

    expect(window.telarLoadKatex).not.toHaveBeenCalled();
  });

  it('renders the panel when the page already has KaTeX', async () => {
    window.telarRenderLatex = vi.fn();
    await clickTermLink(true);

    expect(window.telarRenderLatex).toHaveBeenCalledWith(document.getElementById('panel-glossary-content'));
    expect(window.telarLoadKatex).not.toHaveBeenCalled();
  });
});
