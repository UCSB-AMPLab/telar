/**
 * Tests for assets/js/katex-loader.js
 *
 * The loader is a classic script that pulls KaTeX from the CDN after
 * DOMContentLoaded and, once the scripts have loaded, renders the LaTeX
 * already on the page. The CDN scripts are not fetched here: a script the
 * loader appends reports itself loaded, and renderMathInElement is a stub
 * that records what it was asked to render.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeAll } from 'vitest';

const rendered = [];

beforeAll(async () => {
  window.telarKatexConfig = {
    hasLatex: true,
    cssUrl: 'https://cdn.example/katex.min.css',
    urls: ['https://cdn.example/katex.min.js', 'https://cdn.example/auto-render.min.js'],
    delimiters: [{ left: '$', right: '$', display: false }],
  };
  globalThis.renderMathInElement = (el) => rendered.push(el);

  // A script the loader appends loads at once.
  const append = document.head.appendChild.bind(document.head);
  vi.spyOn(document.head, 'appendChild').mockImplementation((el) => {
    const out = append(el);
    if (el.tagName === 'SCRIPT') queueMicrotask(() => el.onload?.());
    return out;
  });

  await import('../../assets/js/katex-loader.js');
});

describe('katex-loader: what is rendered once KaTeX has loaded', () => {
  it('renders the step pool and the text cards built from it, not title cards', async () => {
    // The page as it stands when a story was started before KaTeX arrived:
    // the hidden step pool, a text card built from it, and a title card,
    // whose text is plain.
    document.body.innerHTML = `
      <div class="step-data"><div class="story-step" id="pool">$x$</div></div>
      <div class="card-stack">
        <div class="text-card" id="text-card">$x$</div>
        <div class="title-card" id="title-card">$y$</div>
      </div>`;

    document.dispatchEvent(new Event('DOMContentLoaded'));
    await vi.waitFor(() => expect(typeof window.telarRenderLatex).toBe('function'));

    expect(rendered.map((el) => el.id).sort()).toEqual(['pool', 'text-card']);
  });
});
