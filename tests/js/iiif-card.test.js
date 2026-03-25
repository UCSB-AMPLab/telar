/**
 * Tests for _compensateForCardOverlay — mobile and desktop branch
 *
 * Verifies:
 *   - Mobile branch: downward viewport shift (focal point appears above card), zoom-out by visibleFraction (0.60), no X-shift
 *   - Desktop regression: leftward X-shift, no Y-shift, no zoom change
 *
 * Strategy: re-implement the function locally (it is private, not exported).
 * This matches the iiif-lerp.test.js pattern and tests the maths directly.
 *
 * @version v1.0.0-beta
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { state } from '../../assets/js/telar-story/state.js';

// ── Local re-implementation of _compensateForCardOverlay ──────────────────────
//
// Must be a faithful copy of the production function in iiif-card.js.
// Testing the local copy validates the maths; the implementation task then
// replaces the production stub with identical code.

function compensateForCardOverlay(viewport, point, actualZoom) {
  if (state.isMobileViewport) {
    // Mobile: bottom-anchored text card covers up to 40vh.
    // Shift viewport centre downward so the focal point appears in the visible
    // area above the bottom-anchored card, and zoom out proportionally.
    const CARD_FRAC_MOBILE = 0.40;
    const viewportWidth    = 1 / actualZoom;
    const aspectRatio      = window.innerHeight / window.innerWidth;
    const viewportHeight   = viewportWidth * aspectRatio;
    const shiftY           = (CARD_FRAC_MOBILE / 2) * viewportHeight;
    const visibleFraction  = 1 - CARD_FRAC_MOBILE;

    return {
      point:      { x: point.x, y: point.y + shiftY },
      actualZoom: actualZoom * visibleFraction,
    };
  }

  // Desktop: text card covers left ~39% of viewport width.
  const viewportWidth = 1 / actualZoom;
  const CARD_FRAC = 0.39; // right edge of text card (left:4% + width:35%)
  const shiftX = (CARD_FRAC / 2) * viewportWidth;

  return {
    point:      { x: point.x - shiftX, y: point.y },
    actualZoom: actualZoom,
  };
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function setMobileViewport(width = 375, height = 812) {
  state.isMobileViewport = true;
  Object.defineProperty(window, 'innerWidth',  { value: width,  configurable: true, writable: true });
  Object.defineProperty(window, 'innerHeight', { value: height, configurable: true, writable: true });
}

function setDesktopViewport() {
  state.isMobileViewport = false;
}

// ── Tests: mobile branch ──────────────────────────────────────────────────────

describe('compensateForCardOverlay - mobile branch', () => {
  beforeEach(() => {
    setMobileViewport(375, 812);
  });

  it('Test 1: returned point.y is greater than input point.y (viewport shifts down, focal point appears above card)', () => {
    const result = compensateForCardOverlay(null, { x: 0.5, y: 0.5 }, 1.0);
    expect(result.point.y).toBeGreaterThan(0.5);
  });

  it('Test 2: returned point.x equals input point.x (no horizontal shift on mobile)', () => {
    const result = compensateForCardOverlay(null, { x: 0.5, y: 0.5 }, 1.0);
    expect(result.point.x).toBe(0.5);
  });

  it('Test 3: returned actualZoom equals input actualZoom * 0.60 (visibleFraction = 1 - 0.40)', () => {
    const result = compensateForCardOverlay(null, { x: 0.5, y: 0.5 }, 1.0);
    expect(result.actualZoom).toBeCloseTo(1.0 * 0.60, 10);
  });

  it('Test 4: focal point at y=0.5 (centre) produces shifted y greater than 0.5', () => {
    const result = compensateForCardOverlay(null, { x: 0.5, y: 0.5 }, 1.0);
    expect(result.point.y).toBeGreaterThan(0.5);
  });

  it('Test 5: focal point at y=0.0 (top edge) still shifts downward (positive result)', () => {
    const result = compensateForCardOverlay(null, { x: 0.5, y: 0.0 }, 1.0);
    expect(result.point.y).toBeGreaterThan(0.0);
  });

  it('Test 6: focal point at y=1.0 (bottom edge) shifts viewport further down', () => {
    const result = compensateForCardOverlay(null, { x: 0.5, y: 1.0 }, 1.0);
    // Viewport centre shifts below the focal point so it appears above the card
    expect(result.point.y).toBeGreaterThan(1.0);
  });

  it('Test 7: with actualZoom=2.0, shift magnitude differs from actualZoom=1.0 (zoom-dependent)', () => {
    const result1 = compensateForCardOverlay(null, { x: 0.5, y: 0.5 }, 1.0);
    const result2 = compensateForCardOverlay(null, { x: 0.5, y: 0.5 }, 2.0);
    // viewportWidth = 1/zoom, so at zoom=2 the shift is half the shift at zoom=1
    const shift1 = result1.point.y - 0.5;
    const shift2 = result2.point.y - 0.5;
    expect(shift1).not.toBeCloseTo(shift2, 5);
  });
});

// ── Tests: desktop regression ─────────────────────────────────────────────────

describe('compensateForCardOverlay - desktop regression', () => {
  beforeEach(() => {
    setDesktopViewport();
  });

  it('Test 8: returned point.x is less than input point.x (leftward shift)', () => {
    const result = compensateForCardOverlay(null, { x: 0.5, y: 0.5 }, 1.0);
    expect(result.point.x).toBeLessThan(0.5);
  });

  it('Test 9: returned point.y equals input point.y (no vertical shift on desktop)', () => {
    const result = compensateForCardOverlay(null, { x: 0.5, y: 0.5 }, 1.0);
    expect(result.point.y).toBe(0.5);
  });

  it('Test 10: returned actualZoom equals input actualZoom (desktop does not zoom-out)', () => {
    const result = compensateForCardOverlay(null, { x: 0.5, y: 0.5 }, 1.0);
    expect(result.actualZoom).toBe(1.0);
  });
});
