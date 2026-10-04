/**
 * Tests for assets/js/katex-loader.js when a KaTeX script fails to load
 *
 * The first CDN script loads and the second, the auto-renderer, reports an
 * error. The loader stops there: it publishes no renderer, renders
 * nothing, and says so in the console, so the formulas stay as the author
 * wrote them. (The browser tests fail every script, the first included.)
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeAll } from 'vitest';

const appended = [];
const warnings = [];

beforeAll(async () => {
  window.telarKatexConfig = {
    hasLatex: true,
    cssUrl: 'https://cdn.example/katex.min.css',
    urls: ['https://cdn.example/katex.min.js', 'https://cdn.example/auto-render.min.js'],
    delimiters: [{ left: '$', right: '$', display: false }],
  };
  vi.spyOn(console, 'warn').mockImplementation((message) => warnings.push(message));

  // The first script the loader appends loads at once; the second fails.
  const append = document.head.appendChild.bind(document.head);
  vi.spyOn(document.head, 'appendChild').mockImplementation((el) => {
    const out = append(el);
    if (el.tagName === 'SCRIPT') {
      appended.push(el.src);
      const failed = appended.length > 1;
      queueMicrotask(() => (failed ? el.onerror : el.onload)?.());
    }
    return out;
  });

  await import('../../assets/js/katex-loader.js');
});

describe('katex-loader: a KaTeX script that fails to load', () => {
  it('stops loading, publishes no renderer and says why', async () => {
    document.body.innerHTML = '<div class="story-step">$x$</div>';

    document.dispatchEvent(new Event('DOMContentLoaded'));
    await vi.waitFor(() => expect(warnings).toHaveLength(1));

    expect(appended).toEqual(['https://cdn.example/katex.min.js',
      'https://cdn.example/auto-render.min.js']);
    expect(window.telarRenderLatex).toBeUndefined();
    expect(warnings[0]).toContain('https://cdn.example/auto-render.min.js');
    expect(document.querySelector('.story-step').textContent).toBe('$x$');
  });
});
