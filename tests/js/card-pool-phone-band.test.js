/**
 * Tests for Telar Story – Card Pool: a landscape phone's card under the top controls
 *
 * The phone's card is sized by its content, scrolled by the browser, and placed
 * in the band under the top controls that the desktop side card uses. The
 * card's height is modelled as its content's (600px) held to the max-height the
 * pass writes, and the controls are boxes at the lowest edge Back to Start
 * reaches on a phone.
 *
 * @version v1.8.0
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { mediaPadding } from '../../assets/js/telar-story/video-layout.js';

const CONTENT_H = 600;
const CONTROLS_BOTTOM = 60;

// Evaluates the width, height and aspect-ratio clauses against the window's
// live size, so a resize changes what matches.
function queryMatches(query) {
  if (query.includes('prefers-reduced-motion')) return false;
  return query.split(',').some((clause) => {
    const w = window.innerWidth;
    const h = window.innerHeight;
    return [...clause.matchAll(/\((max|min)-(width|height|aspect-ratio):\s*([\d.]+)(px)?\)/g)]
      .every(([, bound, dim, raw]) => {
        const v = parseFloat(raw);
        const actual = dim === 'width' ? w : dim === 'height' ? h : w / h;
        return bound === 'max' ? actual <= v : actual >= v;
      });
  });
}

const phoneMedia = (query) => ({
  get matches() { return queryMatches(query); },
  media: query, onchange: null,
  addListener: vi.fn(), removeListener: vi.fn(),
  addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
});

function resizeViewport(W, H) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: W });
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: H });
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  window.dispatchEvent(new Event('orientationchange'));
  window.dispatchEvent(new Event('resize'));
  vi.advanceTimersByTime(200);
  vi.useRealTimers();
}

async function openPhone(W, H, contentH) {
  vi.resetModules();
  vi.stubGlobal('matchMedia', vi.fn().mockImplementation(phoneMedia));
  vi.stubGlobal('requestAnimationFrame', () => 0);
  Object.defineProperty(document, 'fonts', { configurable: true, value: new EventTarget() });
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: W });
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: H });
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get() {
      if (!this.classList.contains('text-card')) return 0;
      const cap = parseFloat(this.style.maxHeight);
      return Number.isFinite(cap) ? Math.min(contentH, cap) : contentH;
    },
  });
  document.body.innerHTML = '<div class="card-stack"></div>';
  const back = document.createElement('a');
  back.className = 'btn-nav-back';
  back.getBoundingClientRect = () => ({
    top: 20, bottom: CONTROLS_BOTTOM, left: 20, right: 60, width: 40, height: 40 });
  document.body.append(back);

  const { initCardPool } = await import('../../assets/js/telar-story/card-pool.js');
  initCardPool({ steps: [
    { step: '0', object: '', question: 'intro', answer: '' },
    { step: '1', object: 'obj-a', question: 'q', answer: 'a' },
  ] }, {});
  resizeViewport(W, H);
  return document.querySelector('.text-card');
}

describe('a landscape phone card under the top controls', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    delete document.fonts;
    delete HTMLElement.prototype.offsetHeight;
    document.body.innerHTML = '';
  });

  for (const [W, H] of [[932, 430], [844, 390]]) {
    for (const [name, contentH] of [['a long card', CONTENT_H], ['a short card', 120]]) {
      it(`clears Back to Start and stays inside the window, ${name} at ${W}x${H}`, async () => {
        const card = await openPhone(W, H, contentH);
        const pad = mediaPadding(W, H);
        const top = parseFloat(card.style.top);
        const height = card.offsetHeight;
        expect(top).toBeGreaterThanOrEqual(CONTROLS_BOTTOM + pad);
        expect(top + height).toBeLessThanOrEqual(H - pad);
      });
    }
  }

  it('a portrait 320x480 window keeps the unbanded side card of main', async () => {
    const card = await openPhone(320, 480, CONTENT_H);
    expect(card.style.maxHeight).toBe('');
    expect(parseFloat(card.style.top)).toBeCloseTo((480 - CONTENT_H) / 2, 0);
  });

  it('the phone ceiling does not survive a resize into a desktop window', async () => {
    const card = await openPhone(932, 430, CONTENT_H);
    const phoneCeiling = card.style.maxHeight;
    expect(phoneCeiling).not.toBe('');
    resizeViewport(1280, 800);
    expect(card.style.maxHeight).toBe('640px');
    expect(card.style.maxHeight).not.toBe(phoneCeiling);
    expect(card.style.height).toBe('');
  });
});
