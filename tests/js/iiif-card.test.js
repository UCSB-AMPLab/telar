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
 *   6. Sanity-check failures: zoom ≤ 0, NaN zoom, out-of-range x, or zero
 *      image dimensions all return null.
 *   7. Null cardBox fallback: computeFocalTarget falls back to
 *      _defaultCardBox for both layouts, including the CSS-derived vertical
 *      top edge.
 *
 * @version v1.8.0
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { state } from '../../assets/js/telar-story/state.js';
import { computeFocalTarget, _clampFocalPx, overviewPullFraction, OVERVIEW_MIN_FRACTION }
  from '../../assets/js/telar-story/iiif-card.js';

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
// Worked table (portrait — the arm of the home fit that was never in doubt):
//   imageW=7920, imageH=12237
//   imageAspect = 7920/12237 = 0.64722
//   homeZoomAuth = min(1, 0.64722 / 1.053) = 0.6146
//   frameWidthImg = imageW / (homeZoomAuth · zoom) = 12886 / zoom
//   diameterImg = 0.90 · frameWidthImg
//
// A portrait image is narrower than the authoring frame, so it fits by height
// and the `min` does not bind. Every row of this table is the same portrait
// object, which is why nothing here could see the missing arm; the landscape
// suite below is the one that does.

const IMAGE_W = 7920;
const IMAGE_H = 12237;

// Side card — horizontal placement; placed left of the viewer so uncovered region is to the right.
const SIDE_CARD_BOX = { x: 0, y: 0, w: 402, h: 900 };

// ── Test suite 0: the arm of the home fit the worked table cannot reach ───────
//
// Reported by the Compositor session, which had the branch in its own tree the
// whole time: `visitorVisibleRect` draws the author's guide and would have
// looked visibly wrong without it, so theirs was kept honest by being
// rendered. Nothing drew this one.

describe('computeFocalTarget — the home fit has two arms', () => {
  beforeEach(() => { setDesktopViewport(1440, 900); });

  const CARD = { x: 0, y: 0, w: 576, h: 900 };
  const at = (w, h, zoom) =>
    computeFocalTarget(0.5, 0.5, zoom, w, h, CARD, 'horizontal').diameterImg;

  it('a landscape image fits by width, so its frame is its own width', () => {
    // 12237 x 7920, aspect 1.545: wider than the authoring frame, so it fills
    // it edge to edge and the home zoom is 1. frameWidthImg = 12237/2 = 6118.5,
    // diameterImg = 0.90 * 6118.5 = 5506.65.
    expect(at(12237, 7920, 2)).toBeCloseTo(5506.65, 1);
  });

  it('a portrait image fits by height, so the min does not bind', () => {
    // The transpose of the same pixels: aspect 0.647, under the authoring
    // aspect, so the frame comes from the height and the min passes it
    // through. 0.90 * 7920/((0.64722/1.053) * 2).
    expect(at(7920, 12237, 2)).toBeCloseTo(5798.5, 1);
  });

  it('a square image still fits by height while the frame is wider than tall', () => {
    // Aspect 1 is under the authoring aspect of 1.053, so a square image is
    // on the height arm too. The hinge sits at the authoring aspect, not at 1.
    expect(at(4000, 4000, 2)).toBeCloseTo(0.9 * 4000 / ((1 / 1.053) * 2), 1);
  });

  it('the frame never exceeds the image, however wide the image', () => {
    // The defect in one sentence: without the min, a wider image produced a
    // narrower authored frame, without limit. Every one of these is the
    // image's own width at zoom 1, and none is larger.
    for (const [w, h] of [[4000, 3000], [3840, 2160], [8000, 1000]]) {
      expect(at(w, h, 1)).toBeCloseTo(0.9 * w, 6);
    }
  });

  it('two images of one aspect scale together, whatever their pixel size', () => {
    expect(at(3840, 2160, 3) / at(1920, 1080, 3)).toBeCloseTo(2, 6);
  });
});

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

// ── _clampFocalPx — keep-circle focal clamp (guard for the off-screen bug) ──
//
// _clampFocalPx returns the focal's target position in element px directly (the apply
// path is transient-zoom-free: it never reads the live OSD zoom). These cases lock the
// rule: the focal lands at the uncovered-region centre where the whole focal circle
// fits there, stays at least the circle's radius from every region edge, clamps to the
// image bound while the circle still fits inside the region, and keeps the ideal
// (region-centre) position where the image is narrower than that on an axis.
describe('_clampFocalPx — keep-circle focal clamp', () => {
  it('keeps the region centre when the focal there covers the region (step-3 regression case)', () => {
    // 1440×900 cell, authored 0.486,0.277,zoom10:
    const region = { x: 576, y: 0, w: 864, h: 900 };       // uncovered, side card on left
    const edges = { eLeft: 2867.7, eRight: 3032.9, eTop: 2525.4, eBottom: 6591.5 };
    const ideal = { x: 1008, y: 450 };                     // region centre (576+432, 0+450)
    const radius = 432;                                    // radius match: min(w, h) / 2
    const F = _clampFocalPx(region, edges, ideal, radius);
    // Every edge is further out than the radius → the centre holds, circle whole.
    expect(F.x).toBeCloseTo(1008, 0);
    expect(F.y).toBeCloseTo(450, 0);
  });

  it('clamps to the image-bounds edge while the circle still fits inside the region', () => {
    // Focal near the image's right edge: little image to its right (eRight small), but
    // still further out than the radius, so the image bound is the binding one.
    const region = { x: 0, y: 0, w: 1000, h: 1000 };
    const edges = { eLeft: 3000, eRight: 200, eTop: 3000, eBottom: 3000 };
    const radius = 150;
    // F.x ∈ [region.x + w − eRight, region.x + eLeft] = [800, 3000]; ideal 500 is below 800.
    const F = _clampFocalPx(region, edges, { x: 500, y: 500 }, radius);
    expect(F.x).toBeCloseTo(800, 1);   // clamped so the right edge still covers the region
    expect(F.y).toBeCloseTo(500, 1);   // y centred (ideal 500 within [−2000, 3000])
    // Image right edge at focal: F.x + eRight = 800 + 200 = 1000 = region right.
    expect(F.x + edges.eRight).toBeCloseTo(region.x + region.w, 0);
    // Circle whole inside the region: 650 → 950.
    expect(F.x - radius).toBeGreaterThanOrEqual(region.x);
    expect(F.x + radius).toBeLessThanOrEqual(region.x + region.w);
  });

  it('keeps the ideal focal when the image is narrower than the region on an axis', () => {
    // Image 600 px wide/tall but region is 2000 — cannot cover, so just keep the ideal.
    const region = { x: 0, y: 0, w: 2000, h: 2000 };
    const edges = { eLeft: 300, eRight: 300, eTop: 300, eBottom: 300 };
    const ideal = { x: 877, y: 1045 };
    const F = _clampFocalPx(region, edges, ideal, 250);
    expect(F.x).toBeCloseTo(877, 5);
    expect(F.y).toBeCloseTo(1045, 5);
  });

  it('keeps the image against the region edge when one axis is nearer (corner step)', () => {
    // Focal near the image's top edge: eTop (120) is smaller than the radius (432),
    // so the two constraints cannot both hold on y. Coverage wins — the focal is
    // held where the image still reaches the region's top, and the circle straddles.
    const region = { x: 576, y: 0, w: 864, h: 900 };
    const edges = { eLeft: 2867.7, eRight: 3032.9, eTop: 120, eBottom: 6591.5 };
    const ideal = { x: 1008, y: 450 };
    const radius = 432;
    const F = _clampFocalPx(region, edges, ideal, radius);
    expect(F.x).toBeCloseTo(1008, 0);   // x untouched: both x edges clear the radius
    expect(F.y).toBeCloseTo(120, 0);    // y held where the image's top edge is flush
    // No background above the image — the thing a reader sees at once.
    expect(F.y - edges.eTop).toBeCloseTo(region.y, 0);
    // And the circle is the side that gives: it now reaches past the region's top.
    expect(F.y - radius).toBeLessThan(region.y);
  });

  it('keeps the image against both region edges at an extreme corner', () => {
    // Bottom card: the uncovered region is the strip above it, and the focal sits near
    // the image's top-left corner — nearer than the radius on both axes, so both give.
    const region = { x: 0, y: 0, w: 900, h: 800 };
    const edges = { eLeft: 150, eRight: 4000, eTop: 90, eBottom: 5000 };
    const ideal = { x: 450, y: 400 };
    const radius = 400;                                    // radius match: min(w, h) / 2
    const F = _clampFocalPx(region, edges, ideal, radius);
    expect(F.x).toBeCloseTo(150, 0);
    expect(F.y).toBeCloseTo(90, 0);
    // Both image edges flush with the region: no background on either axis.
    expect(F.x - edges.eLeft).toBeCloseTo(region.x, 0);
    expect(F.y - edges.eTop).toBeCloseTo(region.y, 0);
  });

  it('leaves the focal alone where the image cannot cover the axis at all', () => {
    // An overview: the whole object stands inside the region with margin, so there is
    // no region edge for it to reach and nothing to hold the focal to.
    const region = { x: 0, y: 0, w: 1000, h: 600 };
    const edges = { eLeft: 120, eRight: 120, eTop: 80, eBottom: 80 };
    const ideal = { x: 500, y: 300 };
    const F = _clampFocalPx(region, edges, ideal, 100);
    expect(F.x).toBeCloseTo(500, 0);
    expect(F.y).toBeCloseTo(300, 0);
  });

  it('honours both constraints where the image is wide enough for both', () => {
    // The ordinary case, and the one that must not change: radius clear of every
    // region edge and the image reaching every one of them.
    const region = { x: 0, y: 0, w: 900, h: 800 };
    const edges = { eLeft: 3000, eRight: 3000, eTop: 2000, eBottom: 2000 };
    const ideal = { x: 450, y: 400 };
    const radius = 200;
    const F = _clampFocalPx(region, edges, ideal, radius);
    expect(F.x).toBeCloseTo(450, 0);
    expect(F.y).toBeCloseTo(400, 0);
    expect(F.x - radius).toBeGreaterThanOrEqual(region.x);
    expect(F.y + radius).toBeLessThanOrEqual(region.y + region.h);
  });

  it('holds the iPad mini landscape step that showed a band of background', () => {
    // The case that found this: 1024x768, a 1600x900 image at zoom 6, focal at
    // y 0.1. eTop 166.7 against a radius of 222.2, so the old bound let the focal
    // sit at the region centre and the image's top edge landed 56.5 px inside it.
    const region = { x: 0, y: 0, w: 1024, h: 443.8 };
    const edges = { eLeft: 2666.6, eRight: 296.3, eTop: 166.7, eBottom: 1500 };
    const F = _clampFocalPx(region, edges, { x: 512, y: 221.9 }, 222.2);
    expect(F.y).toBeCloseTo(166.7, 1);
    expect(F.y - edges.eTop).toBeCloseTo(0, 1);   // flush, no band
    expect(F.x).toBeCloseTo(727.7, 1);            // x was already right, and stays
  });
});

describe('overviewPullFraction', () => {
  // The authored zoom at or below an overview says how much of the
  // whole-object fit the step asks for: 1 the whole frame, less than 1 the
  // same object standing back from it. The floor is shared with the
  // Compositor's editor, which has to let an author reach the same framing
  // this allows, so it is exported rather than written down twice.

  it('frames the whole object at 1', () => {
    expect(overviewPullFraction(1)).toBe(1);
  });

  it('stands the object back in proportion below 1', () => {
    expect(overviewPullFraction(0.8)).toBeCloseTo(0.8, 10);
    expect(overviewPullFraction(0.5)).toBeCloseTo(0.5, 10);
    expect(overviewPullFraction(0.25)).toBeCloseTo(0.25, 10);
  });

  it('holds at the floor rather than letting the object become a speck', () => {
    expect(overviewPullFraction(0.01)).toBe(OVERVIEW_MIN_FRACTION);
    expect(overviewPullFraction(0)).toBe(OVERVIEW_MIN_FRACTION);
    expect(overviewPullFraction(-3)).toBe(OVERVIEW_MIN_FRACTION);
  });

  it('never asks for more than the fit, whatever is above it', () => {
    expect(overviewPullFraction(2)).toBe(1);
    expect(overviewPullFraction(9)).toBe(1);
  });

  it('falls back to the whole object when the zoom is not a number', () => {
    expect(overviewPullFraction(NaN)).toBe(1);
    expect(overviewPullFraction(undefined)).toBe(1);
    expect(overviewPullFraction(Infinity)).toBe(1);
  });

  it('is monotonic across the range, so an author gets what they asked for', () => {
    let previous = 0;
    for (const zoom of [0.1, 0.2, 0.35, 0.5, 0.75, 0.9, 1]) {
      const pull = overviewPullFraction(zoom);
      expect(pull).toBeGreaterThanOrEqual(previous);
      previous = pull;
    }
  });
});
