/**
 * Tests for the order of a window resize: the active IIIF viewer is framed
 * against the card as the resize left it.
 *
 * The card's width follows the window height, and card-pool.js writes it in
 * the resize pass. The viewer is re-framed from state.cardOverlayRect, so the
 * rect the frame is computed from has to be the one measured after that pass.
 * The card's box is modelled as the width the pass published on the document
 * root, which is what the stylesheet reads to size it.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const cardWidth = () =>
  parseFloat(document.documentElement.style.getPropertyValue('--telar-card-side-width'));

function setWindowSize(W, H) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: W });
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: H });
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  window.dispatchEvent(new Event('resize'));
  vi.advanceTimersByTime(200);
  vi.useRealTimers();
}

describe('resize within one layout: the viewer is framed against the resized card', () => {
  let state;
  let framedAgainst;

  beforeEach(async () => {
    vi.resetModules();
    framedAgainst = [];
    vi.stubGlobal('requestAnimationFrame', () => 0);
    Object.defineProperty(document, 'fonts', { configurable: true, value: new EventTarget() });
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1200 });
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 600 });
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
      configurable: true,
      get() { return this.classList.contains('text-card') ? 300 : 0; },
    });
    document.body.innerHTML = '<div class="card-stack"></div>';

    ({ state } = await import('../../assets/js/telar-story/state.js'));
    const { initCardPool } = await import('../../assets/js/telar-story/card-pool.js');
    const { makePlate } = await import('./iiif-plate-helpers.js');
    window.storyData = { steps: [
      { step: '0', object: '', question: 'intro', answer: '' },
      { step: '1', object: 'obj-a', question: 'q', answer: 'a', x: '0.5', y: '0.5', zoom: '2' },
    ] };
    initCardPool(window.storyData, {});

    vi.stubGlobal('OpenSeadragon', {
      Rect: class { constructor(x, y, width, height) { Object.assign(this, { x, y, width, height }); } },
    });
    const fitBounds = vi.fn(() => framedAgainst.push(state.cardOverlayRect?.width));
    state.viewerPlates = { 0: makePlate('obj-a', 0, { fitBounds, active: true }) };

    const card = document.querySelector('.text-card');
    card.classList.add('is-active');
    for (const c of document.querySelectorAll('.text-card')) {
      c.getBoundingClientRect = () => ({
        x: 0, y: 0, left: 0, top: 0, width: cardWidth(), height: 300, right: cardWidth(), bottom: 300 });
    }
    setWindowSize(1200, 600);
    state.cardOverlayRect = card.getBoundingClientRect();
    framedAgainst.length = 0;
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    delete document.fonts;
    delete HTMLElement.prototype.offsetHeight;
    delete window.storyData;
    state.viewerPlates = {};
    state.cardOverlayRect = null;
    document.documentElement.style.removeProperty('--telar-card-side-width');
    document.body.innerHTML = '';
  });

  it('the card is 584 px at 1200x600 and 504 px at 1200x650', () => {
    expect(cardWidth()).toBe(584);
    setWindowSize(1200, 650);
    expect(cardWidth()).toBe(504);
  });

  it('frames against the 504 px card, not the 584 px one', () => {
    setWindowSize(1200, 650);
    expect(framedAgainst.length).toBeGreaterThan(0);
    expect(framedAgainst.at(-1)).toBe(504);
    expect(state.cardOverlayRect.width).toBe(504);
  });
});
