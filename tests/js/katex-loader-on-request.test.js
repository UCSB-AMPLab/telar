/**
 * Tests for loading KaTeX on request, through window.telarLoadKatex.
 *
 * A page whose own content holds no LaTeX loads nothing at DOMContentLoaded.
 * The glossary panel asks for KaTeX when a term it fetched holds maths, and
 * the story's own check asks too, so the first request loads KaTeX and the
 * rest do nothing. A page that already has window.telarRenderLatex, from
 * _includes/katex.html, loads nothing here.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeAll } from 'vitest';

const appended = [];
const rendered = [];

beforeAll(async () => {
  window.telarKatexConfig = {
    hasLatex: false,
    cssUrl: 'https://cdn.example/katex.min.css',
    urls: ['https://cdn.example/katex.min.js', 'https://cdn.example/auto-render.min.js'],
    delimiters: [{ left: '$', right: '$', display: false }],
  };
  globalThis.renderMathInElement = (el) => rendered.push(el);

  // A script the loader appends loads at once.
  const append = document.head.appendChild.bind(document.head);
  vi.spyOn(document.head, 'appendChild').mockImplementation((el) => {
    const out = append(el);
    if (el.tagName === 'SCRIPT') {
      appended.push(el.src);
      queueMicrotask(() => el.onload?.());
    }
    return out;
  });

  await import('../../assets/js/katex-loader.js');
  document.body.innerHTML = '<div id="panel-glossary-content">$x$</div>';
  document.dispatchEvent(new Event('DOMContentLoaded'));
  await new Promise((resolve) => setTimeout(resolve, 0));
});

describe('katex-loader: loading on request', () => {
  it('loads nothing for a page without LaTeX until asked', () => {
    expect(appended).toEqual([]);
    expect(typeof window.telarLoadKatex).toBe('function');
  });

  it('loads nothing when the page already has a renderer', () => {
    window.telarRenderLatex = () => {};
    window.telarLoadKatex();
    delete window.telarRenderLatex;

    expect(appended).toEqual([]);
  });

  it('loads once however often it is asked, and renders the glossary panel', async () => {
    window.telarLoadKatex();
    window.telarLoadKatex();
    await vi.waitFor(() => expect(typeof window.telarRenderLatex).toBe('function'));
    window.telarLoadKatex();

    expect(appended).toEqual(window.telarKatexConfig.urls);
    expect(rendered.map((el) => el.id)).toEqual(['panel-glossary-content']);
  });
});
