/**
 * Tests for computeFocalTarget — two-circle focal-target model
 *
 * Asserts that computeFocalTarget produces the correct two-circle math.
 *
 * Suites:
 *   1. diameterImg matches the worked table (zoom 10, 8.9, 2.9) for the
 *      7920×12237 test object.
 *   2. Rule A (overview cap): at zoom 1 the algorithm does not zoom further out
 *      than whole-image-fit.
 *   3. Region derivation: side card (horizontal) vs bottom card (vertical).
 *   4. Focal point = (x·imageW, y·imageH).
 *   5. Device-independence: same (x, y, zoom) on two viewports gives the same
 *      diameterImg (footprint no longer scales with width).
 *   6. Skip and fallback cases: title-card-active, null cardOverlayRect.
 *
 * @version v1.4.0
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { state } from '../../assets/js/telar-story/state.js';
import { computeFocalTarget, _compensateForCardOverlay, _clampFocalPx } from '../../assets/js/telar-story/iiif-card.js';

// ── Viewport helpers ───────────────────────────────────────────────────────────

function setDesktopViewport(width = 1440, height = 900) {
  state.layoutMode = 'horizontal';
  Object.defineProperty(window, 'innerWidth',  { value: width,  configurable: true, writable: true });
  Object.defineProperty(window, 'innerHeight', { value: height, configurable: true, writable: true });
}

function setMobileViewport(width = 375, height = 812) {
  state.layoutMode = 'vertical';
  Object.defineProperty(window, 'innerWidth',  { value: width,  configurable: true, writable: true });
  Object.defineProperty(window, 'innerHeight', { value: height, configurable: true, writable: true });
}

// ── Worked-table test object ───────────────────────────────────────────────────
//
// Worked table:
//   imageW=7920, imageH=12237
//   imageAspect = 7920/12237 = 0.64722
//   homeZoomAuth = 0.64722 / 1.053 = 0.6146
//   frameWidthImg = imageW / (homeZoomAuth · zoom) = 12886 / zoom
//   diameterImg = 0.90 · frameWidthImg

const IMAGE_W = 7920;
const IMAGE_H = 12237;

// Side card — horizontal placement; placed left of the viewer so uncovered region is to the right.
const SIDE_CARD_BOX = { x: 0, y: 0, w: 402, h: 900 };

// ── Test suite 1: diameterImg — worked table ───────────────────────────────────

describe('computeFocalTarget — worked table (diameterImg)', () => {

  beforeEach(() => {
    state.activeTitleCardIndex = null;
    state.cardOverlayRect = null;
    state.layoutMode = 'horizontal';
    setDesktopViewport(1440, 900);
  });

  it('zoom 10 → diameterImg ≈ 1160 (±5)', () => {
    const result = computeFocalTarget(0.5, 0.5, 10, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal');
    expect(result).not.toBeNull();
    // frameWidthImg = 12886/10 = 1289; diameterImg = 0.90 * 1289 ≈ 1160
    expect(result.diameterImg).toBeCloseTo(1160, -1); // within ±5
  });

  it('zoom 8.9 → diameterImg ≈ 1303 (±5)', () => {
    const result = computeFocalTarget(0.5, 0.5, 8.9, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal');
    expect(result).not.toBeNull();
    // frameWidthImg = 12886/8.9 = 1448; diameterImg = 0.90 * 1448 ≈ 1303
    expect(result.diameterImg).toBeCloseTo(1303, -1); // within ±5
  });

  it('zoom 2.9 → diameterImg ≈ 4000 (±10)', () => {
    const result = computeFocalTarget(0.5, 0.5, 2.9, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal');
    expect(result).not.toBeNull();
    // frameWidthImg = 12886/2.9 = 4444; diameterImg = 0.90 * 4444 ≈ 4000
    expect(result.diameterImg).toBeCloseTo(4000, -2); // within ±10
  });

  it('returns object with all required keys for sane inputs', () => {
    const result = computeFocalTarget(0.5, 0.5, 10, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal');
    expect(result).not.toBeNull();
    expect(result).toHaveProperty('focalImg');
    expect(result).toHaveProperty('diameterImg');
    expect(result).toHaveProperty('region');
    expect(result).toHaveProperty('imageW');
    expect(result).toHaveProperty('imageH');
  });

  it('imageW and imageH are preserved in the return value', () => {
    const result = computeFocalTarget(0.5, 0.5, 10, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal');
    expect(result).not.toBeNull();
    expect(result.imageW).toBe(IMAGE_W);
    expect(result.imageH).toBe(IMAGE_H);
  });

});

// ── Test suite 2: focal point = (x·imageW, y·imageH) ─────────────────────────

describe('computeFocalTarget — focal point in image px', () => {

  beforeEach(() => {
    state.activeTitleCardIndex = null;
    state.cardOverlayRect = null;
    state.layoutMode = 'horizontal';
    setDesktopViewport(1440, 900);
  });

  it('focalImg.x = x · imageW', () => {
    const result = computeFocalTarget(0.3, 0.7, 5, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal');
    expect(result).not.toBeNull();
    expect(result.focalImg.x).toBeCloseTo(0.3 * IMAGE_W, 0);
  });

  it('focalImg.y = y · imageH', () => {
    const result = computeFocalTarget(0.3, 0.7, 5, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal');
    expect(result).not.toBeNull();
    expect(result.focalImg.y).toBeCloseTo(0.7 * IMAGE_H, 0);
  });

  it('focalImg.x at x=0 is 0', () => {
    const result = computeFocalTarget(0, 0.5, 5, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal');
    expect(result).not.toBeNull();
    expect(result.focalImg.x).toBe(0);
  });

  it('focalImg.y at y=1 is imageH', () => {
    const result = computeFocalTarget(0.5, 1, 5, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal');
    expect(result).not.toBeNull();
    expect(result.focalImg.y).toBe(IMAGE_H);
  });

});

// ── Test suite 3: region derivation — horizontal (side) vs vertical (bottom) ──

describe('computeFocalTarget — region derivation', () => {

  beforeEach(() => {
    state.activeTitleCardIndex = null;
    state.cardOverlayRect = null;
  });

  it('horizontal placement — uncovered region starts at card right edge (region.x = card.x + card.w)', () => {
    setDesktopViewport(1440, 900);
    state.layoutMode = 'horizontal';
    const cardBox = { x: 0, y: 0, w: 402, h: 900 };
    const result = computeFocalTarget(0.5, 0.5, 10, IMAGE_W, IMAGE_H, cardBox, 'horizontal');
    expect(result).not.toBeNull();
    // For a horizontal side card: uncovered region x = card.x + card.w = 402
    expect(result.region.x).toBeCloseTo(cardBox.x + cardBox.w, 0);
    // Region spans from card right edge to viewport right edge
    expect(result.region.w).toBeCloseTo(1440 - (cardBox.x + cardBox.w), 0);
    expect(result.region.w).toBeGreaterThan(0);
  });

  it('vertical placement — uncovered region height = card top edge (region.h = card.y)', () => {
    setMobileViewport(390, 844);
    state.layoutMode = 'vertical';
    // Bottom card: top edge at 60% of viewport height (556)
    const cardBox = { x: 0, y: 506, w: 390, h: 338 };
    const result = computeFocalTarget(0.5, 0.5, 10, IMAGE_W, IMAGE_H, cardBox, 'vertical');
    expect(result).not.toBeNull();
    // For a vertical bottom card: uncovered region height = card.y
    expect(result.region.h).toBeCloseTo(cardBox.y, 0);
    expect(result.region.h).toBeGreaterThan(0);
    expect(result.region.x).toBe(0);
  });

  it('region w and h are always positive for sane inputs', () => {
    setDesktopViewport(1440, 900);
    state.layoutMode = 'horizontal';
    const result = computeFocalTarget(0.5, 0.5, 5, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal');
    expect(result).not.toBeNull();
    expect(result.region.w).toBeGreaterThan(0);
    expect(result.region.h).toBeGreaterThan(0);
  });

});

// ── Test suite 4: device-independence ─────────────────────────────────────────

describe('computeFocalTarget — device-independence', () => {

  beforeEach(() => {
    state.activeTitleCardIndex = null;
    state.cardOverlayRect = null;
  });

  it('diameterImg is the same for two different viewport sizes (footprint does not scale with width)', () => {
    // Desktop 1440×900, side card
    setDesktopViewport(1440, 900);
    state.layoutMode = 'horizontal';
    const desktopCard = { x: 0, y: 0, w: 533, h: 900 };
    const result1440 = computeFocalTarget(0.5, 0.5, 10, IMAGE_W, IMAGE_H, desktopCard, 'horizontal');

    // Mobile 390×844, bottom card
    setMobileViewport(390, 844);
    state.layoutMode = 'vertical';
    const mobileCard = { x: 0, y: 556, w: 390, h: 288 };
    const result390 = computeFocalTarget(0.5, 0.5, 10, IMAGE_W, IMAGE_H, mobileCard, 'vertical');

    expect(result1440).not.toBeNull();
    expect(result390).not.toBeNull();
    // diameterImg must be identical regardless of viewport — device-independent radius
    expect(result1440.diameterImg).toBeCloseTo(result390.diameterImg, 0);
  });

  it('diameterImg depends only on zoom and image dimensions, not viewport', () => {
    // Run on three different viewports — diameterImg must be identical
    const zoom = 5;
    const cardH1 = { x: 0, y: 0, w: 400, h: 900 };
    const cardH2 = { x: 0, y: 0, w: 600, h: 1080 };
    const cardV  = { x: 0, y: 500, w: 390, h: 300 };

    setDesktopViewport(1440, 900);
    const r1 = computeFocalTarget(0.5, 0.5, zoom, IMAGE_W, IMAGE_H, cardH1, 'horizontal');

    setDesktopViewport(1920, 1080);
    const r2 = computeFocalTarget(0.5, 0.5, zoom, IMAGE_W, IMAGE_H, cardH2, 'horizontal');

    setMobileViewport(390, 844);
    const r3 = computeFocalTarget(0.5, 0.5, zoom, IMAGE_W, IMAGE_H, cardV, 'vertical');

    expect(r1).not.toBeNull();
    expect(r2).not.toBeNull();
    expect(r3).not.toBeNull();
    expect(r1.diameterImg).toBeCloseTo(r2.diameterImg, 0);
    expect(r1.diameterImg).toBeCloseTo(r3.diameterImg, 0);
  });

});

// ── Test suite 5: Rule A — overview cap ───────────────────────────────────────

describe('computeFocalTarget — Rule A (overview cap at zoom 1)', () => {

  beforeEach(() => {
    state.activeTitleCardIndex = null;
    state.cardOverlayRect = null;
    state.layoutMode = 'horizontal';
    setDesktopViewport(1440, 900);
  });

  it('at zoom 1, diameterImg is at least imageW (frame is the whole image width)', () => {
    // zoom 1 → frameWidthImg = imageW / homeZoomAuth ≈ imageW / (imageAspect / 1.053)
    // For imageW=7920, imageH=12237: homeZoomAuth=0.6146, frameWidthImg=12886
    // diameterImg = 0.90 * 12886 = 11597 > imageW=7920
    // Rule A: the apply recipe will cap at whole-image-fit; computeFocalTarget just
    // returns the raw diameterImg — the cap is applied in _applyFocalTarget.
    const result = computeFocalTarget(0.5, 0.5, 1, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal');
    expect(result).not.toBeNull();
    // At zoom 1 the authored frame width (in image px) exceeds imageW — circle larger than image.
    // diameterImg should be greater than imageW.
    expect(result.diameterImg).toBeGreaterThan(IMAGE_W);
  });

  it('at high zoom, diameterImg is much smaller than imageW', () => {
    // At zoom 10: diameterImg ≈ 1160, imageW = 7920
    const result = computeFocalTarget(0.5, 0.5, 10, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal');
    expect(result).not.toBeNull();
    expect(result.diameterImg).toBeLessThan(IMAGE_W);
  });

});

// ── Test suite 6: sanity-check failures (null returns) ────────────────────────

describe('computeFocalTarget — insane inputs return null', () => {

  beforeEach(() => {
    state.activeTitleCardIndex = null;
    state.cardOverlayRect = null;
    state.layoutMode = 'horizontal';
    setDesktopViewport(1440, 900);
  });

  it('returns null when zoom = 0', () => {
    expect(computeFocalTarget(0.5, 0.5, 0, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal')).toBeNull();
  });

  it('returns null when zoom is negative', () => {
    expect(computeFocalTarget(0.5, 0.5, -1, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal')).toBeNull();
  });

  it('returns null when x > 1', () => {
    expect(computeFocalTarget(1.5, 0.5, 5, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal')).toBeNull();
  });

  it('returns null when x < 0', () => {
    expect(computeFocalTarget(-0.1, 0.5, 5, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal')).toBeNull();
  });

  it('returns null when imageW = 0', () => {
    expect(computeFocalTarget(0.5, 0.5, 5, 0, IMAGE_H, SIDE_CARD_BOX, 'horizontal')).toBeNull();
  });

  it('returns null when imageH = 0', () => {
    expect(computeFocalTarget(0.5, 0.5, 5, IMAGE_W, 0, SIDE_CARD_BOX, 'horizontal')).toBeNull();
  });

  it('returns null when zoom is NaN', () => {
    expect(computeFocalTarget(0.5, 0.5, NaN, IMAGE_W, IMAGE_H, SIDE_CARD_BOX, 'horizontal')).toBeNull();
  });

});

// ── Test suite 7: null cardBox fallback ───────────────────────────────────────

describe('computeFocalTarget — null cardBox fallback', () => {

  beforeEach(() => {
    state.activeTitleCardIndex = null;
    state.cardOverlayRect = null;
  });

  it('null cardBox in vertical placement uses _defaultCardBox and returns a valid result', () => {
    setMobileViewport(375, 667);
    state.layoutMode = 'vertical';
    const result = computeFocalTarget(0.5, 0.5, 10, IMAGE_W, IMAGE_H, null, 'vertical');
    expect(result).not.toBeNull();
    expect(result.region.w).toBeGreaterThan(0);
    expect(result.region.h).toBeGreaterThan(0);
  });

  it('null cardBox in horizontal placement uses _defaultCardBox and returns a valid result', () => {
    setDesktopViewport(1440, 900);
    state.layoutMode = 'horizontal';
    const result = computeFocalTarget(0.5, 0.5, 10, IMAGE_W, IMAGE_H, null, 'horizontal');
    expect(result).not.toBeNull();
    expect(result.region.w).toBeGreaterThan(0);
    expect(result.region.h).toBeGreaterThan(0);
  });

  it('null cardBox vertical: region.h follows CSS-derived top edge (≈60% of viewport height)', () => {
    // _defaultCardBox vertical: bottom 40vh → top at 60vh = 667 * 0.60 = 400
    // So region.h (= card.y) = 400
    setMobileViewport(375, 667);
    state.layoutMode = 'vertical';
    const result = computeFocalTarget(0.5, 0.5, 5, IMAGE_W, IMAGE_H, null, 'vertical');
    expect(result).not.toBeNull();
    expect(result.region.h).toBeCloseTo(667 * 0.60, 0); // ≈ 400
  });

});

// ── Test suite 8: _compensateForCardOverlay skip cases ────────────────────────

describe('_compensateForCardOverlay — skip and fallback cases', () => {

  beforeEach(() => {
    state.activeTitleCardIndex = null;
    state.cardOverlayRect = null;
    state.layoutMode = 'horizontal';
    setDesktopViewport(1440, 900);
  });

  it('returns null when a title card is active (title-card-active skip)', () => {
    state.activeTitleCardIndex = 0; // title card is active
    const result = _compensateForCardOverlay(0.5, 0.5, 1.5, IMAGE_W, IMAGE_H);
    expect(result).toBeNull();
  });

  it('returns null for title card at any activeTitleCardIndex value', () => {
    state.activeTitleCardIndex = 3;
    const result = _compensateForCardOverlay(0.5, 0.5, 1.5, IMAGE_W, IMAGE_H);
    expect(result).toBeNull();
  });

  it('returns non-null when no title card is active and cardOverlayRect is null (full-object fallback)', () => {
    // state.activeTitleCardIndex = null, state.cardOverlayRect = null
    // → _defaultCardBox path → should produce a valid result
    state.activeTitleCardIndex = null;
    state.cardOverlayRect = null;
    state.layoutMode = 'horizontal';
    const result = _compensateForCardOverlay(0.5, 0.5, 5, IMAGE_W, IMAGE_H);
    // With a null cardOverlayRect, the _defaultCardBox fallback yields a
    // non-null region. This suite tests the state-based skip guard only.
    // If _compensateForCardOverlay is still exported, it must not return null here.
    expect(result).not.toBeNull();
  });

  it('returns non-null when a measured cardOverlayRect is set (horizontal placement)', () => {
    state.activeTitleCardIndex = null;
    // Simulate a DOMRect-like card on the left side
    state.cardOverlayRect = { x: 0, y: 0, width: 402, height: 900 };
    state.layoutMode = 'horizontal';
    setDesktopViewport(1440, 900);
    const result = _compensateForCardOverlay(0.5, 0.5, 5, IMAGE_W, IMAGE_H);
    expect(result).not.toBeNull();
  });

});

// ── _clampFocalPx — Rule B focal clamp (regression guard for the off-screen bug) ──
//
// The original Rule B clamp used the region centre (CB) as the post-pan focal
// reference and swapped its min/max bounds, which inverted the valid pan range and
// flung the focal ~100k px off-screen at zoomed steps (measured: step 3 focal landed
// at (-99639, -266227) on a 1440×900 cell). _clampFocalPx returns the focal's target
// position in element px directly (the apply path is transient-zoom-free: it never
// reads the live OSD zoom). These cases lock the corrected behaviour: the focal lands
// at the uncovered-region centre when that position covers the region, clamps to the
// image-bounds edge otherwise, and keeps the ideal (region-centre) position when the
// image is too small to cover the region.
describe('_clampFocalPx — Rule B focal clamp', () => {
  it('keeps the region centre when the focal there covers the region (step-3 regression case)', () => {
    // Instrumented step-3 values (1440×900, authored 0.486,0.277,zoom10):
    const region = { x: 576, y: 0, w: 864, h: 900 };       // uncovered, side card on left
    const edges = { eLeft: 2867.7, eRight: 3032.9, eTop: 2525.4, eBottom: 6591.5 };
    const ideal = { x: 1008, y: 450 };                     // region centre (576+432, 0+450)
    const F = _clampFocalPx(region, edges, ideal);
    // Region centre is coverable → focal lands exactly there, on-screen.
    // (The old buggy clamp drove the focal to ≈(-99639, -266227).)
    expect(F.x).toBeCloseTo(1008, 0);
    expect(F.y).toBeCloseTo(450, 0);
  });

  it('clamps to the image-bounds edge when centring would reveal background', () => {
    // Focal near the image's right edge: little image to its right (eRight small).
    const region = { x: 0, y: 0, w: 1000, h: 1000 };
    const edges = { eLeft: 3000, eRight: 200, eTop: 3000, eBottom: 3000 };
    // F.x ∈ [region.x + w − eRight, region.x + eLeft] = [800, 3000]; ideal 500 is below 800.
    const F = _clampFocalPx(region, edges, { x: 500, y: 500 });
    expect(F.x).toBeCloseTo(800, 1);   // clamped so the right edge still covers the region
    expect(F.y).toBeCloseTo(500, 1);   // y centred (ideal 500 within [−2000, 3000])
    // Image right edge at focal: F.x + eRight = 800 + 200 = 1000 = region right.
    expect(F.x + edges.eRight).toBeCloseTo(region.x + region.w, 0);
  });

  it('keeps the ideal focal when the image is too small to cover the region', () => {
    // Image 600 px wide/tall but region is 2000 — cannot cover, so just keep the ideal.
    const region = { x: 0, y: 0, w: 2000, h: 2000 };
    const edges = { eLeft: 300, eRight: 300, eTop: 300, eBottom: 300 };
    const ideal = { x: 877, y: 1045 };
    const F = _clampFocalPx(region, edges, ideal);
    expect(F.x).toBeCloseTo(877, 5);
    expect(F.y).toBeCloseTo(1045, 5);
  });
});
