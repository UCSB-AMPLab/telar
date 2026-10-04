/**
 * Tests for camera travel
 *
 * stepTravel measures the travel between a step and the next on the live
 * geometry; placementTravel measures it between two placements through one
 * region, and is no travel for a placement with no scale.
 *
 * @version v1.8.0
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { state, moveSeconds } from '../../assets/js/telar-story/state.js';
import { stepTravel, placementTravel } from '../../assets/js/telar-story/camera-travel.js';
import { makePlate } from './iiif-plate-helpers.js';

// ── How far a pair of steps moves the camera ────────────────────────────────
//
// Travel is van Wijk and Nuij's distance between what the reader's region shows
// at each step: the image point at its centre and its width. A zoom by a ratio
// r about one point is ln r / √2, whatever the image or the zoom it starts at.

describe('stepTravel — the travel between a step and the next', () => {
  const step = (object, x, y, zoom) => ({ object, x: String(x), y: String(y), zoom: String(zoom) });

  beforeEach(() => {
    state.layoutMode = 'horizontal';
    Object.defineProperty(window, 'innerWidth',  { value: 1440, configurable: true, writable: true });
    Object.defineProperty(window, 'innerHeight', { value: 900, configurable: true, writable: true });
    state.cardOverlayRect = null;
    state.activeTitleCardIndex = null;
    state.stepsData = [step('fig1', 0.5, 0.5, 3), step('fig1', 0.5, 0.5, 12), step('fig2', 0.5, 0.5, 3)];
    state.stepToScene = { 0: 0, 1: 0, 2: 1 };
    state.viewerPlates = { 0: makePlate('fig1', 0, { fitBounds: () => {} }) };
  });

  it('measures a zoom by four about one point as ln 4 / √2', () => {
    expect(stepTravel(0)).toBeCloseTo(Math.log(4) / Math.SQRT2, 3);
  });

  it('is nothing between two objects', () => {
    expect(stepTravel(1)).toBe(0);
  });

  it('is nothing while the plate is not ready', () => {
    state.viewerPlates[0].isReady = false;
    expect(stepTravel(0)).toBe(0);
  });

  it('is nothing before the first step and after the last', () => {
    expect(stepTravel(-1)).toBe(0);
    expect(stepTravel(2)).toBe(0);
  });
});

// A container with no width during layout gives a placement with no scale, and
// a camera that cannot be measured. That is no travel, not a number nobody can
// time a move by.
describe('placementTravel — a placement with no scale', () => {
  const region = { x: 0, y: 0, w: 800, h: 600 };
  const placed = (s) => ({ s, anchorImg: { x: 0, y: 0 }, anchorPx: { x: 0, y: 0 } });

  it('is no travel, never NaN', () => {
    expect(placementTravel(placed(0), placed(0.5), region)).toBe(0);
    expect(placementTravel(placed(0.5), placed(0), region)).toBe(0);
    expect(placementTravel(placed(NaN), placed(0.5), region)).toBe(0);
  });

  it('times a move with no measurable travel at the base', () => {
    expect(moveSeconds(placementTravel(placed(0), placed(0.5), region))).toBe(1.2);
  });
});
