/**
 * Telar Story – Camera travel
 *
 * How far a move takes the reader, measured on the live geometry. The scroll
 * engine and the mobile step navigation time a move by it (moveSeconds in
 * state.js). The measure reads placements from iiif-card.js, which does not
 * import this module.
 *
 * @version v1.8.0
 */

import { state } from './state.js';
import { _livePlacement, _authoredFraming } from './iiif-card.js';

// ── Camera travel ────────────────────────────────────────────────────────────
//
// How far a move takes the reader, measured as van Wijk and Nuij measure a
// pan and zoom: by what the reader's uncovered region shows, the image point
// at its centre and its width in image px, with ρ = √2. A zoom by a ratio r
// about one point is ln r / √2, so a 2× zoom is 0.49; a pan of one region
// width at a fixed zoom is about 1.1. It measures the region the reader has,
// so the same pair of steps measures a little differently on another layout.

const RHO = Math.SQRT2;

/** The image point at the region centre and the region's width, image px. */
function _camera({ s, anchorImg, anchorPx }, region) {
  return {
    u: {
      x: anchorImg.x + (region.x + region.w / 2 - anchorPx.x) / s,
      y: anchorImg.y + (region.y + region.h / 2 - anchorPx.y) / s,
    },
    w: region.w / s,
  };
}

/**
 * The travel between two placements seen through one region (pure).
 *
 * @param {{s:number, anchorImg:{x:number,y:number}, anchorPx:{x:number,y:number}}} from
 * @param {{s:number, anchorImg:{x:number,y:number}, anchorPx:{x:number,y:number}}} to
 * @param {{x:number,y:number,w:number,h:number}} region  Element px.
 * @returns {number} 0 for a region with no area or a placement with no scale.
 */
export function placementTravel(from, to, region) {
  // A container with no width during layout gives a placement with no scale,
  // whose camera cannot be measured: that is no travel.
  if (!(region.w > 0 && region.h > 0 && from.s > 0 && to.s > 0)) return 0;
  const a = _camera(from, region);
  const b = _camera(to, region);
  const pan = RHO * RHO * Math.hypot(b.u.x - a.u.x, b.u.y - a.u.y);
  return Math.acosh(1 + (pan * pan + (b.w - a.w) ** 2) / (2 * a.w * b.w)) / RHO;
}

/**
 * The camera travel from a step to the next, on the live geometry.
 *
 * 0 where the camera does not travel between them: two scenes, a step with no
 * authored framing, or a plate that cannot be placed yet.
 *
 * @param {number} stepIndex
 * @returns {number}
 */
export function stepTravel(stepIndex) {
  const steps = state.stepsData || [];
  const scene = state.stepToScene[stepIndex];
  if (scene === undefined || scene !== state.stepToScene[stepIndex + 1]) return 0;
  const a = steps[stepIndex] && _authoredFraming(steps[stepIndex]);
  const b = steps[stepIndex + 1] && _authoredFraming(steps[stepIndex + 1]);
  const plate = state.viewerPlates[scene];
  if (!a || !b || !plate?.isReady || !plate.osdViewer) return 0;
  const from = _livePlacement(plate, a.x, a.y, a.zoom);
  const to = _livePlacement(plate, b.x, b.y, b.zoom);
  return from && to ? placementTravel(from.placement, to.placement, from.region) : 0;
}

/**
 * The camera travel between two step positions, a part of a step counting
 * for its share of that step's travel. -1 is the intro, which has none.
 *
 * @param {number} from - Step index, possibly between steps
 * @param {number} to
 * @returns {number}
 */
export function travelBetween(from, to) {
  const lo = Math.min(from, to);
  const hi = Math.max(from, to);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return 0;
  let total = 0;
  for (let i = Math.floor(lo); i < hi; i++) {
    total += (Math.min(hi, i + 1) - Math.max(lo, i)) * stepTravel(i);
  }
  return total;
}
