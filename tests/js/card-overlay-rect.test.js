/**
 * Tests for Telar Story – Card Pool: the card overlay rect
 *
 * state.cardOverlayRect is what the IIIF framing reads to keep a focal point
 * out from behind the text card. These suites cover when activateCard writes
 * it (the reduced-motion synchronous branch, the transitionend of the card
 * that arrives), that a card which has left does not write it, and that a
 * title card clears it. The rest of the card pool's DOM behaviour lives in
 * card-pool-dom.test.js.
 *
 * @version v1.8.0
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { activateCard } from '../../assets/js/telar-story/card-pool.js';
import { state } from '../../assets/js/telar-story/state.js';

// ── cardOverlayRect population ───────────────────────────────────────────────
//
// Tests for the three-branch rect-write logic in _activateTextCard and the
// null-clear in _activateTitleCardStep. The private functions are exercised
// through the exported activateCard entry point (the same activation dispatch
// used in production). Both tests rely on minimal mock state that avoids the
// need for a full initCardPool call.

describe('cardOverlayRect — rect populated in reduced-motion synchronous branch', () => {
  const MOCK_RECT = { top: 100, left: 10, width: 300, height: 400, bottom: 500, right: 310 };

  beforeEach(() => {
    // Reset cardOverlayRect to a known non-null value so we can prove it was written
    state.cardOverlayRect = null;

    // Stub matchMedia — jsdom does not implement it. Return matches: true for
    // prefers-reduced-motion so _activateTextCard takes the synchronous branch.
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query) => ({
      matches: query === '(prefers-reduced-motion: reduce)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })));

    // No title card at index 0 — ensures activateCard routes to text-card path
    state.titleCards = {};

    // Minimal scene maps so preloadAhead returns early
    state.stepToScene  = { 0: 0 };
    state.totalScenes  = 1;
    state.sceneFirstStep = { 0: 0 };

    // No active viewer plates (text-only path skips viewer init)
    state.viewerPlates = {};
    state.viewerCards  = [];

    // Same-object run so activateCard takes the text-only branch (no needsNewViewer)
    state.currentObjectRun = { objectId: 'obj-a', runPosition: 0 };
    state.activeTitleCardIndex = null;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('writes state.cardOverlayRect with the mocked getBoundingClientRect value (synchronous)', () => {
    const mockCard = document.createElement('div');
    // Mock getBoundingClientRect to return a known rect
    mockCard.getBoundingClientRect = vi.fn().mockReturnValue(MOCK_RECT);

    // Wire minimal card-pool state. The card carries its own step, object and
    // run position, as _createTextCards writes them.
    mockCard.dataset.stepIndex = '0';
    mockCard.dataset.object = 'obj-a';
    mockCard.dataset.runPosition = '0';
    state.textCards = { 0: mockCard };

    activateCard(0, 'forward');

    // Synchronous branch: rect is set immediately (no transitionend needed)
    expect(state.cardOverlayRect).toBe(MOCK_RECT);
    expect(mockCard.getBoundingClientRect).toHaveBeenCalledTimes(1);
  });
});

// A card's measured rect is written when its slide ends, and the camera reads
// that rect on every frame. A card that has left by then is not what the
// reader's region is uncovered around, so its slide ending writes nothing.
describe('cardOverlayRect — a card that has left does not write it', () => {
  const rectOf = (top) => ({ top, left: 10, width: 300, height: 400, bottom: top + 400, right: 310 });

  function card(step, top) {
    const el = document.createElement('div');
    el.className = 'text-card';
    el.dataset.stepIndex = String(step);
    el.dataset.object = 'obj-a';
    el.dataset.runPosition = String(step);
    el.getBoundingClientRect = vi.fn().mockReturnValue(rectOf(top));
    document.body.appendChild(el);
    return el;
  }

  function slideEnds(el) {
    const ev = new Event('transitionend');
    Object.defineProperty(ev, 'propertyName', { value: 'transform' });
    el.dispatchEvent(ev);
  }

  beforeEach(() => {
    document.body.innerHTML = '';
    state.cardOverlayRect = null;
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query) => ({
      matches: false, media: query, onchange: null,
      addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })));
    state.titleCards = {};
    state.stepToScene = { 0: 0, 1: 0 };
    state.totalScenes = 1;
    state.sceneFirstStep = { 0: 0 };
    state.viewerPlates = {};
    state.currentObjectRun = { objectId: 'obj-a', runPosition: 0 };
    state.activeTitleCardIndex = null;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
  });

  it('keeps the active card\'s rect when a departed card\'s slide ends after it', () => {
    const first = card(0, 900);
    const second = card(1, 100);
    state.textCards = { 0: first, 1: second };

    activateCard(0, 'forward');
    activateCard(1, 'forward');
    slideEnds(second);
    expect(state.cardOverlayRect).toEqual(rectOf(100));

    slideEnds(first);
    expect(first.classList.contains('is-active')).toBe(false);
    expect(state.cardOverlayRect).toEqual(rectOf(100));
  });
});

describe('cardOverlayRect — null on title-card activation', () => {
  beforeEach(() => {
    // Seed a non-null value to confirm it is cleared
    state.cardOverlayRect = { top: 99, left: 5, width: 100, height: 200, bottom: 299, right: 105 };

    // Minimal scene maps
    state.stepToScene   = { 0: 0 };
    state.totalScenes   = 1;
    state.sceneFirstStep = { 0: 0 };

    state.viewerPlates  = {};
    state.viewerCards   = [];
    state.textCards     = {};
    state.activeTitleCardIndex = null;
  });

  it('clears state.cardOverlayRect to null when a title card is activated', () => {
    const titleCardEl = document.createElement('div');
    state.titleCards = { 0: titleCardEl };

    activateCard(0, 'forward');

    expect(state.cardOverlayRect).toBeNull();
  });
});
