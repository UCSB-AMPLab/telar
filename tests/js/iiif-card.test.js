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
 *   8. framePlacement: an overview (zoom ≤ 1) centres the whole image in the
 *      uncovered region whatever its x/y; any zoom above 1 places the authored
 *      focal point exactly, so a settled framing changes at zoom 1; zoom ≥ 2
 *      places it as pinned. blendPlacements moves continuously between two.
 *
 * @version v1.8.0
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { state } from '../../assets/js/telar-story/state.js';
import {
  computeFocalTarget, framePlacement, blendPlacements, _clampFocalPx, overviewPullFraction,
  OVERVIEW_MIN_FRACTION,
} from '../../assets/js/telar-story/iiif-card.js';

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
  const diameterAt = (w, h, zoom) =>
    computeFocalTarget(0.5, 0.5, zoom, w, h, CARD, 'horizontal').diameterImg;

  it('a landscape image fits by width, so its frame is its own width', () => {
    // 12237 x 7920, aspect 1.545: wider than the authoring frame, so it fills
    // it edge to edge and the home zoom is 1. frameWidthImg = 12237/2 = 6118.5,
    // diameterImg = 0.90 * 6118.5 = 5506.65.
    expect(diameterAt(12237, 7920, 2)).toBeCloseTo(5506.65, 1);
  });

  it('a portrait image fits by height, so the min does not bind', () => {
    // The transpose of the same pixels: aspect 0.647, under the authoring
    // aspect, so the frame comes from the height and the min passes it
    // through. 0.90 * 7920/((0.64722/1.053) * 2).
    expect(diameterAt(7920, 12237, 2)).toBeCloseTo(5798.5, 1);
  });

  it('a square image still fits by height while the frame is wider than tall', () => {
    // Aspect 1 is under the authoring aspect of 1.053, so a square image is
    // on the height arm too. The hinge sits at the authoring aspect, not at 1.
    expect(diameterAt(4000, 4000, 2)).toBeCloseTo(0.9 * 4000 / ((1 / 1.053) * 2), 1);
  });

  it('the frame never exceeds the image, however wide the image', () => {
    // The defect in one sentence: without the min, a wider image produced a
    // narrower authored frame, without limit. Every one of these is the
    // image's own width at zoom 1, and none is larger.
    for (const [w, h] of [[4000, 3000], [3840, 2160], [8000, 1000]]) {
      expect(diameterAt(w, h, 1)).toBeCloseTo(0.9 * w, 6);
    }
  });

  it('two images of one aspect scale together, whatever their pixel size', () => {
    expect(diameterAt(3840, 2160, 3) / diameterAt(1920, 1080, 3)).toBeCloseTo(2, 6);
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

// ── _clampFocalPx — an image exactly as long as the region covers it ──────────
//
// At zoom 1 the image is scaled to fit the uncovered region, so on its limiting
// axis its length equals the region's and the two coverage bounds meet. Whether
// the sum of the focal's edge distances comes out a fraction above or below the
// region's length is decided by floating-point rounding; the sweeps below take
// image sizes that land on both sides and require the image's edges to sit on
// the region's edges in every one.
describe('_clampFocalPx — an image that exactly fits the region', () => {
  const region = { x: 576, y: 0, w: 864, h: 757 };   // 1440×757, side card on the left
  const centre = { x: region.x + region.w / 2, y: region.y + region.h / 2 };

  function placeAtFit(fx, fy, imgW, imgH) {
    const s = Math.min(region.w / imgW, region.h / imgH);   // zoom 1: the whole-image fit
    const f = { x: fx * imgW, y: fy * imgH };
    const edges = {
      eLeft: f.x * s, eRight: (imgW - f.x) * s,
      eTop: f.y * s, eBottom: (imgH - f.y) * s,
    };
    const F = _clampFocalPx(region, edges, centre, 0);
    return {
      edges,
      left: F.x - edges.eLeft, right: F.x + edges.eRight,
      top: F.y - edges.eTop, bottom: F.y + edges.eBottom,
    };
  }

  function sweepFitSizes(aspect, fx, fy, axis) {
    let short = 0, long = 0;
    const misplaced = [];
    for (let w = 1000; w <= 6000; w += 7) {
      const h = Math.round(w / aspect);
      const r = placeAtFit(fx, fy, w, h);
      const [near, far, lo, hi, a, b] = axis === 'x'
        ? [r.edges.eLeft, r.edges.eRight, region.x, region.x + region.w, r.left, r.right]
        : [r.edges.eTop, r.edges.eBottom, region.y, region.y + region.h, r.top, r.bottom];
      const len = near + far;
      if (len < hi - lo) short++;
      if (len > hi - lo) long++;
      if (Math.abs(a - lo) > 1e-6 || Math.abs(b - hi) > 1e-6) misplaced.push(`${w}×${h}`);
    }
    return { short, long, misplaced: { count: misplaced.length, first: misplaced.slice(0, 3) } };
  }

  it('puts a landscape image edge to edge across the region at every size', () => {
    const r = sweepFitSizes(1.5, 0.04, 0.5, 'x');
    expect(r.short).toBeGreaterThan(0);   // the sweep reaches both sides of the rounding
    expect(r.long).toBeGreaterThan(0);
    expect(r.misplaced).toEqual({ count: 0, first: [] });
  });

  it('puts a portrait image edge to edge down the region at every size', () => {
    const r = sweepFitSizes(0.5, 0.04, 0.9, 'y');
    expect(r.short).toBeGreaterThan(0);
    expect(r.long).toBeGreaterThan(0);
    expect(r.misplaced).toEqual({ count: 0, first: [] });
  });

  it('places the reported 1000×667 image flush with the region, not at 973.44', () => {
    const r = placeAtFit(0.04, 0.5, 1000, 667);
    expect(r.left).toBeCloseTo(576, 6);
    expect(r.right).toBeCloseTo(1440, 6);
  });

  it('still leaves an image a hundredth of a pixel short at the ideal position', () => {
    // Genuinely smaller than the region, however slightly: the overview rule holds.
    const edges = { eLeft: 100, eRight: 763.99, eTop: 50, eBottom: 50 };
    const F = _clampFocalPx(region, edges, centre, 0);
    expect(F.x).toBe(centre.x);
    expect(F.y).toBe(centre.y);
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

// ── framePlacement: where the image lands ─────────────────────────────────────
//
// An overview step shows the whole object, and it is centred in the uncovered
// region: the authored x/y do not move it (ruled 26 September). Above zoom 1
// the authored focal point is what is placed (ruled 27 September), so a step
// frames exactly the x/y it was authored or captured at. Motion between two
// steps either side of 1 is carried by blendPlacements, not by placing the
// blended x/y/zoom.

const DESKTOP = { vw: 1440, vh: 757, mode: 'horizontal', box: { x: 0, y: 0, w: 576, h: 757 } };
const PHONE   = { vw: 375,  vh: 812, mode: 'vertical',   box: { x: 0, y: 487, w: 375, h: 325 } };

function placeImage(layout, imgW, imgH, x, y, zoom) {
  if (layout.mode === 'horizontal') setDesktopViewport(layout.vw, layout.vh);
  else setMobileViewport(layout.vw, layout.vh);
  const target = computeFocalTarget(x, y, zoom, imgW, imgH, layout.box, layout.mode);
  const p = framePlacement(target, zoom, { width: layout.vw, height: layout.vh });
  const left = p.anchorPx.x - p.anchorImg.x * p.s;
  const top  = p.anchorPx.y - p.anchorImg.y * p.s;
  const r = target.region;
  return {
    ...p,
    left, top, right: left + imgW * p.s, bottom: top + imgH * p.s,
    centre: { x: left + (imgW * p.s) / 2, y: top + (imgH * p.s) / 2 },
    regionCentre: { x: r.x + r.w / 2, y: r.y + r.h / 2 },
  };
}

describe('framePlacement — an overview is centred in the region', () => {
  const IMAGES = { portrait: [1000, 2000], landscape: [3000, 2000], square: [2400, 2400] };
  const FOCALS = [
    [0, 0], [1, 0], [0, 1], [1, 1],            // corners
    [0.04, 0.5], [0.96, 0.5], [0.5, 0.04], [0.5, 0.96],   // edges
    [0.04, 0.9], [0.5, 0.5],
  ];

  for (const [layoutName, layout] of [['desktop side card', DESKTOP], ['phone bottom card', PHONE]]) {
    for (const zoom of [1, 0.6, OVERVIEW_MIN_FRACTION]) {
      it(`centres every image at zoom ${zoom} (${layoutName}), whatever the focal point`, () => {
        const off = [];
        for (const [name, [w, h]] of Object.entries(IMAGES)) {
          for (const [x, y] of FOCALS) {
            const p = placeImage(layout, w, h, x, y, zoom);
            const dx = p.centre.x - p.regionCentre.x;
            const dy = p.centre.y - p.regionCentre.y;
            if (Math.abs(dx) > 1e-6 || Math.abs(dy) > 1e-6) {
              off.push(`${name} (${x}, ${y}): ${dx.toFixed(2)}, ${dy.toFixed(2)}`);
            }
          }
        }
        expect(off).toEqual([]);
      });
    }
  }

  it('places the reported portrait step in the middle of the region, not at 993–1371', () => {
    const p = placeImage(DESKTOP, 1000, 2000, 0.04, 0.5, 1);
    expect(p.left).toBeCloseTo(818.75, 6);
    expect(p.right).toBeCloseTo(1197.25, 6);
    expect(p.top).toBeCloseTo(0, 6);
    expect(p.bottom).toBeCloseTo(757, 6);
  });

  it('keeps a landscape image at a corner focal inside the window at zoom 1', () => {
    // Placed by its focal point, this image ran from 355.46 to 931.46 down a 757 px window.
    const p = placeImage(DESKTOP, 3000, 2000, 0.96, 0.04, 1);
    expect(p.left).toBeCloseTo(576, 6);
    expect(p.right).toBeCloseTo(1440, 6);
    expect(p.top).toBeCloseTo(90.5, 6);
    expect(p.bottom).toBeCloseTo(666.5, 6);
  });

  it('does not change the overview scale', () => {
    const p = placeImage(DESKTOP, 1000, 2000, 0.04, 0.5, 0.6);
    expect(p.s).toBeCloseTo((757 / 2000) * 0.6, 12);
  });
});

describe('framePlacement — above zoom 1 the authored focal point is placed', () => {
  const CASES = [
    ['portrait, left edge', 1000, 2000, 0.04, 0.5],
    ['landscape, top-right corner', 3000, 2000, 0.96, 0.04],
    ['square, bottom-left corner', 2400, 2400, 0.02, 0.98],
    ['landscape, off centre', 3000, 2000, 0.3, 0.35],
  ];

  for (const [name, w, h, x, y] of CASES) {
    for (const zoom of [1.001, 1.5, 1.678, 1.999]) {
      it(`places the focal point exactly at zoom ${zoom} (${name})`, () => {
        expect(placeImage(DESKTOP, w, h, x, y, zoom).anchorImg).toEqual({ x: x * w, y: y * h });
        expect(placeImage(PHONE, w, h, x, y, zoom).anchorImg).toEqual({ x: x * w, y: y * h });
      });
    }

    it(`places the image centre at zoom 1 and below (${name})`, () => {
      for (const zoom of [1, 0.999, 0.6]) {
        expect(placeImage(DESKTOP, w, h, x, y, zoom).anchorImg).toEqual({ x: w / 2, y: h / 2 });
      }
    });

    it(`moves the image by under a pixel from 0.999 to 1 (${name})`, () => {
      const a = placeImage(DESKTOP, w, h, x, y, 0.999);
      const b = placeImage(DESKTOP, w, h, x, y, 1);
      expect(Math.hypot(b.centre.x - a.centre.x, b.centre.y - a.centre.y)).toBeLessThan(1);
    });
  }

  it('puts the Paisajes step that lost its framing back on its x/y', () => {
    // Capítulo 1, step 3 of the Paisajes Coloniales site: obj2 (2586 × 2102) at
    // x 0.2836, y 0.3035, zoom 1.678. Blended towards the image centre, the
    // placed point was 0.678 of the way to the focal point.
    const p = placeImage(DESKTOP, 2586, 2102, 0.2836, 0.3035, 1.678);
    expect(p.anchorImg).toEqual({ x: 0.2836 * 2586, y: 0.3035 * 2102 });
    // The focal point is nearer the image's top-left corner than half the
    // region, so the keep-circle clamp holds the image flush to the region's
    // top-left edges rather than show background there.
    expect(p.left).toBeCloseTo(576, 9);
    expect(p.top).toBeCloseTo(0, 9);
    expect(p.s).toBeCloseTo(0.5486290281000257, 12);
  });

  it('changes a settled framing at zoom 1 by the focal offset where the image does not fill an axis', () => {
    // Ruled 27 September: a focal off centre is placed from just above 1, so
    // the settled framing is not continuous at 1. The portrait image fills the
    // region's height at 1 and not its width, so the jump is horizontal: the
    // focal's offset from centre, 460 image px, at the fit scale 757 / 2000.
    const a = placeImage(DESKTOP, 1000, 2000, 0.04, 0.5, 1);
    const b = placeImage(DESKTOP, 1000, 2000, 0.04, 0.5, 1.001);
    expect(b.centre.x - a.centre.x).toBeGreaterThan(170);
    expect(Math.abs(b.centre.y - a.centre.y)).toBeLessThan(1);
  });
});

describe('blendPlacements — the frames between two settled placements', () => {
  const imageCorner = (p) => ({
    x: p.anchorPx.x - p.anchorImg.x * p.s,
    y: p.anchorPx.y - p.anchorImg.y * p.s,
  });

  it('is each placement exactly at its end', () => {
    const a = placeImage(DESKTOP, 1000, 2000, 0.04, 0.5, 1);
    const b = placeImage(DESKTOP, 1000, 2000, 0.3, 0.7, 3);
    for (const [t, p] of [[0, a], [1, b]]) {
      const m = blendPlacements(a, b, t);
      expect(m.s).toBe(p.s);
      expect(imageCorner(m).x).toBeCloseTo(imageCorner(p).x, 9);
      expect(imageCorner(m).y).toBeCloseTo(imageCorner(p).y, 9);
    }
  });

  it('moves the image continuously between an overview and a detail', () => {
    // Placing the blended x/y/zoom instead jumps where the zoom crosses 1, by
    // the focal's offset at the fit scale; the ArrowDown trace on motion-check
    // showed 119 px in one frame there.
    const pairs = [
      [[0.2, 0.3, 0.8], [0.32, 0.38, 3.2]],
      [[0.2836, 0.3035, 1], [0.2836, 0.3035, 1.678]],
      [[0.04, 0.5, 1], [0.04, 0.5, 1.5]],
    ];
    for (const [A, B] of pairs) {
      const a = placeImage(DESKTOP, 1000, 2000, ...A);
      const b = placeImage(DESKTOP, 1000, 2000, ...B);
      let prev = imageCorner(a);
      let worst = 0;
      for (let i = 1; i <= 1000; i++) {
        const c = imageCorner(blendPlacements(a, b, i / 1000));
        worst = Math.max(worst, Math.hypot(c.x - prev.x, c.y - prev.y));
        prev = c;
      }
      expect(worst, `${JSON.stringify(A)} → ${JSON.stringify(B)}`).toBeLessThan(1);
    }
  });
});

describe('framePlacement — zoom 2 and above place the focal point as before', () => {
  // Pinned from the placement before overview centring; exact, not approximate.
  const PINS = [
    [DESKTOP, 1000, 2000, 0.04, 0.5, 2, 0.7987759839611691, 1008, 378.5],
    [DESKTOP, 3000, 2000, 0.9, 0.1, 3, 0.8411111111111111, 1187.6666666666667, 168.22222222222223],
    [DESKTOP, 1000, 2000, 0.3, 0.7, 6, 2.3963279518835074, 1008, 378.5],
    [DESKTOP, 7920, 12237, 0.05, 0.05, 8, 0.5222037976374401, 782.7927038644262, 319.5103935844677],
    [PHONE, 3000, 2000, 0.2, 0.8, 2.5, 0.3472222222222222, 187.5, 348.1111111111111],
  ];

  for (const [layout, w, h, x, y, zoom, s, fx, fy] of PINS) {
    it(`${w}×${h} at (${x}, ${y}) zoom ${zoom}`, () => {
      const p = placeImage(layout, w, h, x, y, zoom);
      expect(p.anchorImg).toEqual({ x: x * w, y: y * h });
      expect(p.s).toBe(s);
      expect(p.anchorPx).toEqual({ x: fx, y: fy });
    });
  }
});
