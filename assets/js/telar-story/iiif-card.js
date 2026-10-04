/**
 * Telar Story – IIIF Card Positioning and Lifecycle
 *
 * This module handles the positioning, activation, destruction, and
 * per-frame interpolation of IIIF viewer plates in the card-stack layout.
 * It does NOT create viewer plates or inject viewer instances — that work
 * lives in card-pool.js, which pre-creates all plate DOM elements at init
 * time and injects the IIIF wrapper on demand via its internal
 * _initOsdInPlate().
 *
 * The separation exists because the card-pool module owns the full card
 * lifecycle (creation, ordering, preloading), while this module provides
 * the OSD-specific operations that card-pool and scroll-engine call into:
 *
 *   Positioning — `snapIiifToPosition()` and `animateIiifToPosition()`
 *   convert normalised x/y/zoom coordinates from step data into the values
 *   OpenSeadragon expects, applying a shift to compensate for the text card
 *   overlay. The compensation reads the measured card overlay rect
 *   (state.cardOverlayRect) and derives the card placement geometry to
 *   determine the visible area. The focal point is shifted so it lands
 *   in the visible area, not behind the card. Zoom is rescaled in vertical
 *   layout to fit the authored footprint in the visible region.
 *
 *   Per-frame interpolation — `lerpIiifPosition()` is called every frame by
 *   the scroll engine's rAF loop. For step pairs that share the same object,
 *   it linearly interpolates x/y/zoom between the two steps based on scroll
 *   progress and applies the result via snapIiifToPosition (immediate=true).
 *   A pair either side of zoom 1 is blended between the two steps' settled
 *   placements instead, because an overview and a detail place different
 *   image points at the region centre.
 *   Smoothness comes from Lenis's animatedScroll, not from OSD animations.
 *   Different-object pairs are skipped — the viewer freezes at its last
 *   position while the new plate slides in on top.
 *
 *   Destruction — `destroyIiifCard()` releases GPU memory before calling
 *   the wrapper's destroy(). OpenSeadragon holds WebGL render state that
 *   the browser cannot reclaim until the context is explicitly released.
 *   Per OSD issue #2693, the module calls WEBGL_lose_context.loseContext()
 *   first, then the wrapper's destroy(), then removes the DOM element.
 *
 * @version v1.8.0
 */

import { state } from './state.js';
import { onViewportResize, onLayoutChange, isLandscapeSideCard } from './layout-mode.js';
import { authoringHomeZoom } from './authoring-frame.js';
import { stepFraming } from './plates/framing.js';

// ── Type definition ──────────────────────────────────────────────────────────

/**
 * @typedef {Object} ViewerCard
 * @property {string} objectId - The object this card displays.
 * @property {number|undefined} page - Page number for multi-page objects.
 * @property {HTMLElement} element - The plate's container element in the DOM.
 * @property {Object|null} osdWrapper - The IIIF viewer wrapper (iiif-viewer.js).
 * @property {Object|null} osdViewer - The OpenSeadragon viewer (null until ready).
 * @property {boolean} isReady - Whether the OSD viewer has initialised.
 * @property {Object|null} pendingZoom - Queued position to apply when ready.
 * @property {number} zIndex - The plate's stacking order in the card stack.
 */

// ── Centring compensation — internal helpers ──────────────────────────────────
//
// Shared helpers used by computeFocalTarget and _applyFocalTarget.
// These are pure functions — no DOM or state access.

/**
 * Check that all numeric inputs required by the centring functions are finite
 * and within their allowed ranges.
 *
 * @param {number} imageW
 * @param {number} imageH
 * @param {number} viewportW
 * @param {number} viewportH
 * @param {number} x     authoredX in [0, 1]
 * @param {number} y     authoredY in [0, 1]
 * @param {number} zoom  authoredZoom > 0
 * @returns {boolean}
 */
function _isSane(imageW, imageH, viewportW, viewportH, x, y, zoom) {
  const fin = (v) => typeof v === 'number' && Number.isFinite(v);
  if (!fin(imageW) || imageW <= 0) return false;
  if (!fin(imageH) || imageH <= 0) return false;
  if (!fin(viewportW) || viewportW <= 0) return false;
  if (!fin(viewportH) || viewportH <= 0) return false;
  if (!fin(x) || x < 0 || x > 1) return false;
  if (!fin(y) || y < 0 || y > 1) return false;
  if (!fin(zoom) || zoom <= 0) return false;
  return true;
}

// CSS geometry constants derived from _story.scss card layout rules.
// Horizontal: .text-card { left: 3%; width: 37%; }  → card spans 3–40% of viewport
// Vertical:   bottom card: height 40vh → top edge = viewportH × (100-40)/100
const _CSS_HORIZ_CARD_LEFT    = 3 / 100;    // left:  3%
const _CSS_HORIZ_CARD_WIDTH   = 37 / 100;   // width: 37%
const _CSS_VERT_CARD_H_VH     = 40 / 100;   // height: 40vh
const _CSS_VERT_CARD_TOP_FRAC = 1 - _CSS_VERT_CARD_H_VH;  // top at (100-40)vh/100vh

/**
 * CSS-derived default card box used when state.cardOverlayRect is null.
 *
 * horizontal: _story.scss left:3%, width:37%
 * vertical:   _story.scss bottom 40vh (top edge at 60% viewport height)
 *
 * @param {'horizontal'|'vertical'} placement
 * @param {number} viewportW
 * @param {number} viewportH
 * @returns {{ x: number, y: number, w: number, h: number }}
 */
function _defaultCardBox(placement, viewportW, viewportH) {
  if (placement === 'horizontal') {
    return {
      x: viewportW * _CSS_HORIZ_CARD_LEFT,
      y: 0,
      w: viewportW * _CSS_HORIZ_CARD_WIDTH,
      h: viewportH,
    };
  }
  // vertical — bottom card: height 40vh, top edge at (100-40)vh from top
  return {
    x: 0,
    y: viewportH * _CSS_VERT_CARD_TOP_FRAC,
    w: viewportW,
    h: viewportH * _CSS_VERT_CARD_H_VH,
  };
}

/**
 * Derive the card placement mode from the card's measured rect geometry.
 *
 * The centring branch keys off card PLACEMENT, not
 * state.layoutMode. A landscape phone has state.layoutMode='vertical' but
 * its card is placed as a side card; feeding 'vertical' to the algorithm
 * would subtract the card from the top — wrong.
 *
 * Heuristic: if the card's right edge is left of 60% of the viewport width,
 * it is a side card (horizontal placement). The horizontal side card
 * (_story.scss: left:3%, width:37%) always ends at ~40% of viewport width;
 * the bottom card (width:100%) always ends at 100%.
 *
 * @param {{ x: number, y: number, w: number, h: number }|null} cardBox
 * @param {number} viewportW
 * @param {number} viewportH  (reserved for future height-based heuristics)
 * @returns {'horizontal'|'vertical'}
 */
export function _deriveCardPlacement(cardBox, viewportW, viewportH) {
  if (!cardBox) {
    // No measured rect (e.g. focal applied before the card's slide-in transition
    // has settled state.cardOverlayRect). Fall back to the layout mode — but a
    // short landscape viewport renders a SIDE card (the `@media (max-height: …)`
    // rule) even though getLayoutMode() reports 'vertical' (it is
    // < 1024px wide). Without this check the fallback picks a bottom-card region
    // and the focal lands against the wrong (top-strip) frame on landscape phones.
    if (isLandscapeSideCard()) return 'horizontal';
    return state.layoutMode === 'vertical' ? 'vertical' : 'horizontal';
  }
  // Side card: right edge left of 60% of viewport width
  if ((cardBox.x + cardBox.w) < viewportW * 0.6) return 'horizontal';
  return 'vertical';
}

// ── Two-circle focal-target constants ───────────────────────────────────────
//
// FOCAL_DIAMETER_FRAC: focal circle diameter as a fraction of the authored
//   frame width (0.90 = 90%). Faithful to author framing; low risk of clipping
//   deliberately-included edge subject matter.
// Not author-tunable; a runtime framework constant. The authoring aspect the
// frame width is derived against lives in `authoring-frame.js`, because the
// capture side divides by the same number.
const FOCAL_DIAMETER_FRAC = 0.90;   // focal circle diameter as a fraction of authored frame width

/**
 * Compute the two-circle focal target for a IIIF step.
 *
 * Pure function — no DOM reads, no state access, no OSD calls. Viewport
 * dimensions reach it only via the already-screen-px cardBox and viewportW/H
 * (which come from the caller's context). card-pool.js can reuse this directly
 * for tile-prefetch region derivation.
 *
 * Algorithm (two-circle model, steps 1–4 below):
 *   1. Derive the authored frame width in image px from the canonical aspect
 *      ratio (device-independent — no getHomeZoom, no per-mode rescale).
 *   2. The focal circle (Circle A) has diameter = FOCAL_DIAMETER_FRAC × frameWidthImg.
 *   3. The uncovered region (Circle B bounding box) is derived from the card
 *      overlay rect — the screen area the text card does not cover.
 *   4. Return the inputs the OSD apply recipe needs: focal point in
 *      image px and diameter in image px (zoom is computed live in the apply step).
 *
 * Title-card skip is NOT applied here — it lives in _livePlacement
 * so the pure function remains reusable.
 *
 * @param {number} x            Authored focal-point x in [0, 1].
 * @param {number} y            Authored focal-point y in [0, 1].
 * @param {number} zoom         Authored zoom multiplier (> 0).
 * @param {number} imageW       Image width in px (from OSD source).
 * @param {number} imageH       Image height in px (from OSD source).
 * @param {{ x: number, y: number, w: number, h: number }|null} cardBox
 *   Card overlay rect in screen px, or null → _defaultCardBox fallback.
 * @param {'horizontal'|'vertical'} placementMode
 *   Derived by _deriveCardPlacement from rect geometry.
 *
 * @returns {{ focalImg: {x: number, y: number}, diameterImg: number,
 *             region: {x: number, y: number, w: number, h: number},
 *             imageW: number, imageH: number }|null}
 *   Inputs for the OSD apply recipe, or null if inputs are insane.
 */
export function computeFocalTarget(x, y, zoom, imageW, imageH, cardBox, placementMode) {
  const viewportW = window.innerWidth;
  const viewportH = window.innerHeight;

  // Sanity check — reuse existing _isSane guard
  if (!_isSane(imageW, imageH, viewportW, viewportH, x, y, zoom)) {
    return null;
  }

  // Resolve card geometry: null cardBox → CSS-derived default
  const box = (cardBox !== null && cardBox !== undefined)
    ? cardBox
    : _defaultCardBox(placementMode, viewportW, viewportH);

  // Derive the uncovered region in screen px (the area the card does not cover)
  let region;
  if (placementMode === 'horizontal') {
    const visX = box.x + box.w;
    region = { x: visX, y: 0, w: viewportW - visX, h: viewportH };
  } else {
    // vertical / embed: card anchored at bottom; visible area is above card top edge
    region = { x: 0, y: 0, w: viewportW, h: box.y };
  }

  // ── Circle A radius derivation ──────────────────────────────────────────────
  // imageAspect   = imageW / imageH
  // homeZoomAuth  = authoringHomeZoom(imageAspect)   (canonical, device-independent)
  // frameWidthImg = imageW / (homeZoomAuth · zoom)   (authored frame width in image px)
  // diameterImg   = FOCAL_DIAMETER_FRAC · frameWidthImg
  //
  // The home fit has two arms: an image taller than the authoring frame fits
  // by height, and a wider one fits by width and cannot zoom out past its own
  // edges. Keeping only the first arm made every landscape image's authored
  // frame narrower than it was, by AUTHORING_ASPECT / imageAspect, and so
  // published it over-zoomed.
  const imageAspect    = imageW / imageH;
  const homeZoomAuth   = authoringHomeZoom(imageAspect);
  const frameWidthImg  = imageW / (homeZoomAuth * zoom);
  const diameterImg    = FOCAL_DIAMETER_FRAC * frameWidthImg;

  // Focal point in image px (Circle A centre)
  const focalImg = { x: x * imageW, y: y * imageH };

  return { focalImg, diameterImg, region, imageW, imageH };
}

/**
 * Apply the two-circle target to position a IIIF viewer plate (fitBounds form).
 *
 * Implements the two-circle model via a transient-zoom-free
 * OSD-unit conversion:
 *   - SCALE: s = max(s_tgt, s_fit) at zoom ≥ 2 — element px per image px, where
 *       s_tgt = min(region.w, region.h) / diameterImg  (radius match, Circle A→B)
 *       s_fit = min(region.w/imgW, region.h/imgH)      (Rule A: whole-image fit in
 *       the uncovered region). At an overview (zoom ≤ 1) s is s_fit scaled by the
 *       authored zoom: at 1 the whole object fits and is centred in the region,
 *       and below 1 the same object stands back from the frame by that fraction.
 *       Between 1 and 2, interpolate linearly from the whole-object fit at 1 to
 *       the detail scale at 2. This keeps scale continuous without changing
 *       either overview or zoom ≥ 2 framing.
 *     No OSD-zoom calibration (no `k`): fitBounds derives the zoom from the rect.
 *   - FOCAL: move the anchor to the uncovered-region centre, clamped to the
 *     keep-circle bound (_clampFocalPx) — keep scale, hold the anchor at least the
 *     circle's radius from every region edge. Does NOT rely on OSD's visibilityRatio.
 *     The anchor is the image centre at zoom ≤ 1 (an overview is centred whatever
 *     its x/y) and the authored focal point at every zoom above 1.
 *   - APPLY: build the image-px rectangle that fills the viewer at scale s with the
 *     anchor at the clamped position, then vp.fitBounds(rect, immediate). Because the
 *     target is a rectangle (not a delta off the live zoom), it is correct even on the
 *     animate path where the zoom is still springing — the fix for the mid-animation
 *     mis-scaling bug.
 *
 * Skip guards:
 *   - Title-card active: return false immediately (caller leaves viewer at home).
 *   - Full-object mode: state.cardOverlayRect is null → the null-rect
 *     path → _defaultCardBox gives a full-viewer region → focal centred in viewer.
 *     No dedicated full-object branch needed.
 *
 * @param {ViewerCard} viewerCard - The card to position.
 * @param {number} x    Authored focal-point x in [0, 1].
 * @param {number} y    Authored focal-point y in [0, 1].
 * @param {number} zoom Authored zoom multiplier (> 0).
 * @param {boolean} immediate - true = snap, false = OSD spring animation.
 * @returns {boolean} false if skipped (title-card or source dims unavailable), true otherwise.
 */

// The smallest fraction of the whole-object fit an authored zoom can ask for.
// A tenth of the frame is a long way back and still an object a reader can
// recognise; below that the step says nothing a reader can act on, and the
// rectangle handed to OSD approaches degenerate.
//
// The Compositor's editor has to let an author reach the same floor, or the
// range is composable in a spreadsheet and not in the tool most authors use.
// It is exported with the clamp below so that end can drive this one rather
// than copy the number out of here.
export const OVERVIEW_MIN_FRACTION = 0.1;

/**
 * How much of the whole-object fit an authored zoom at or below an overview
 * asks for.
 *
 * 1 is the whole object filling the frame, and below it the same object
 * standing back with margin around it, down to the floor. Above 1 the
 * question does not arise: the scale transitions toward the detail rule,
 * reaching the diameter match (or fit floor) at 2.
 *
 * @param {number} zoom - The authored zoom.
 * @returns {number} A fraction of the whole-object fit, within the floor and 1.
 */
export function overviewPullFraction(zoom) {
  if (!Number.isFinite(zoom)) return 1;
  return Math.min(1, Math.max(OVERVIEW_MIN_FRACTION, zoom));
}

/**
 * Keep-circle focal clamp (pure). Given the uncovered `region`, the focal-to-image-edge
 * distances in element px at the applied scale (`edges`), the `ideal` focal position in
 * element px (the uncovered-region centre) and the focal circle's `radius` in element px,
 * return the focal's target position in element px.
 *
 * Two constraints act on each axis, and they pull opposite ways.
 *
 *   Coverage. The focal must sit within the image's own edge distance of the region
 *   edge, or the image does not reach it and the page background shows beside it:
 *     focal ≤ region.x + eLeft        and    focal ≥ region.x + region.w − eRight
 *
 *   Circle. The focal must sit at least the circle's radius inside, or the framed
 *   detail straddles the region boundary and part of it goes under the text card:
 *     focal ≥ region.x + radius       and    focal ≤ region.x + region.w − radius
 *
 * Both hold together whenever the image is wide enough, which is the ordinary case.
 * Where they cannot both hold — a focal nearer an image edge than the radius —
 * **coverage wins**: the focal is held where the image still reaches the region edge,
 * and the circle is allowed to straddle it.
 *
 * That reverses the trade this function was written with, which kept the circle intact
 * and accepted background at the region edge. Ruled by Juan on 19 September, on the
 * plain ground that a reader sees a band of background beside the image at once and
 * does not see a framed detail sitting nearer the region edge than intended.
 *
 * Where the image is shorter than the region on an axis, it cannot cover it, and the
 * two coverage bounds cross: between them lie the positions that keep the whole image
 * inside the region. The focal is held there, as near the ideal as that allows, so
 * the image never hangs past a region edge under the text card or off the window.
 * At the length where the image starts to cover the axis the crossed bounds meet
 * the covering ones at the same point, so the placement changes continuously as the
 * scale grows through it. An overview is centred and so already inside the region;
 * it is not moved. An image exactly as long as the region (zoom 1, on its limiting
 * axis) covers it, and is placed edge to edge.
 *
 * Note: this returns the target focal POSITION (not a pan delta) and reads no live
 * OSD state, so the apply path is independent of the transient (mid-animation) zoom.
 *
 * @param {{x:number,y:number,w:number,h:number}} region  Uncovered region, element px.
 * @param {{eLeft:number,eRight:number,eTop:number,eBottom:number}} edges  Focal→edge px at applied scale.
 * @param {{x:number,y:number}} ideal   Ideal focal position (the region centre), element px.
 * @param {number} radius  Focal-circle radius in element px at the applied scale.
 * @returns {{x:number,y:number}} The clamped focal position in element px.
 */
export function _clampFocalPx(region, edges, ideal, radius) {
  // Bounds that cross by no more than this still count as meeting. At zoom 1 the
  // image fits the region, so on its limiting axis its length equals the region's
  // and the two coverage bounds coincide; rounding leaves them apart by about
  // 1e-13 px at these magnitudes, on either side. A thousandth of a pixel is nine
  // orders above that and far below a device pixel, so it absorbs the rounding
  // without letting an image visibly smaller than the region be pinned to one edge.
  const MEET_PX = 1e-3;
  const into = (lo, hi, want) =>
    (lo <= hi + MEET_PX ? Math.max(lo, Math.min(hi, want)) : null);

  const axis = (start, extent, near, far, want) => {
    const coverLo = start + extent - far;   // the image still reaches the far edge
    const coverHi = start + near;           // the image still reaches the near edge

    const both = into(Math.max(coverLo, start + radius),
                      Math.min(coverHi, start + extent - radius), want);
    if (both !== null) return both;

    const covered = into(coverLo, coverHi, want);
    if (covered !== null) return covered;

    return Math.max(coverHi, Math.min(coverLo, want));   // shorter: kept inside
  };

  return {
    x: axis(region.x, region.w, edges.eLeft, edges.eRight, ideal.x),
    y: axis(region.y, region.h, edges.eTop, edges.eBottom, ideal.y),
  };
}

/**
 * Where a step puts the image (pure): the applied scale, the image point that is
 * placed, and the element-px position it is placed at.
 *
 * @param {{focalImg:{x:number,y:number}, diameterImg:number,
 *          region:{x:number,y:number,w:number,h:number},
 *          imageW:number, imageH:number}} target  From computeFocalTarget.
 * @param {number} zoom  Authored zoom (> 0).
 * @param {{width:number,height:number}} container  Viewer container size, element px.
 * @returns {{s:number, anchorImg:{x:number,y:number}, anchorPx:{x:number,y:number}}}
 *   `s` in element px per image px; `anchorImg` (image px) lands at `anchorPx`.
 */
export function framePlacement(target, zoom, container) {
  const { focalImg, diameterImg, region, imageW: imgW, imageH: imgH } = target;
  const rect = container;

  // SCALE — radius match (Circle A→B) with the Rule A overview cap. `s` is element px
  // per image px; z_tgt/k reduces to exactly this, so no OSD-zoom calibration is needed.
  // Rule A's whole-image fit is measured against the UNCOVERED REGION, the frame every
  // step is composed into, not the container: an image fit to the container is wider
  // than the region by the width of the text card, so a quarter of it would sit under
  // the card. At an overview (zoom ≤ 1, the full-object framing) that fit is also the
  // ceiling — the whole object is what the step shows, so the image is never scaled
  // past the size at which all of it fits the region.
  // A region with no area — a card box that covers the viewport — leaves nothing to
  // compose into, and both region-derived scales collapse to zero; the container fit
  // keeps the viewer showing the image rather than a degenerate rectangle.
  const hasRegion = region.w > 0 && region.h > 0;
  const isOverview = zoom <= 1;
  const s_tgt = Math.min(region.w, region.h) / diameterImg;         // radius match (Circle A→B)
  const s_fit = hasRegion
    ? Math.min(region.w / imgW, region.h / imgH)                    // Rule A: whole-image fit
    : Math.min(rect.width / imgW, rect.height / imgH);
  // At and below an overview the authored zoom is a fraction of the fit, so 1
  // is the whole object filling the region and anything under it is the same
  // object standing back from the frame with margin around it. 1 therefore
  // means exactly what it has always meant, and the range below it — which
  // used to give the same framing whatever was typed in it — reads as the
  // pull-back an author writing 0.6 is asking for. The floor keeps the object
  // recognisable rather than a speck, and keeps the rectangle handed to OSD
  // away from degenerate.
  //
  // Bridge the different overview/detail scales across 1 < zoom < 2. Joining
  // at 2 uses the widest band that preserves every zoom >= 2 detail. A straight
  // segment is monotone, has no overshoot, and preserves the original endpoints
  // exactly; slope continuity is not required. Since s_tgt is proportional to
  // zoom, s_tgt * (2 / zoom) is the authored-circle scale at the join.
  // If the circle fits at zoom 1 (s_fit <= s_tgt there), it fits throughout
  // this band: the segment never exceeds the circle-match line. Otherwise a
  // whole circle and the unchanged overview fit are geometrically incompatible
  // near 1; the existing overview semantics take precedence.
  const pull  = overviewPullFraction(zoom);
  const s     = isOverview ? s_fit * pull
    : zoom < 2
      ? s_fit + (zoom - 1) * (Math.max(s_tgt * (2 / zoom), s_fit) - s_fit)
      : Math.max(s_tgt, s_fit);  // applied scale (px / img px)

  // ANCHOR — the image point placed at the uncovered-region centre. An overview
  // shows the whole object, so it is centred in the region and the authored x/y
  // do not move it: the anchor is the image centre at zoom ≤ 1. Above 1 a step
  // frames a detail, and the anchor is exactly the authored focal point, so
  // the x/y an author captured is the point the reader sees at the centre,
  // unless the clamp below has to move it to keep background out of the
  // region or the image inside it.
  // The settled framing of a focal off centre therefore changes at zoom 1.
  // Motion between two steps on either side of 1 does not pass through this
  // function at intermediate zooms: lerpIiifPosition blends the two settled
  // placements instead (blendPlacements).
  const anchorImg = _placedPoint(focalImg, imgW, imgH, zoom);

  // FOCAL POSITION — uncovered-region centre, clamped by the keep-circle rule. The
  // edges are the anchor→image-edge distances at the applied scale `s`; all element px.
  const CB    = { x: region.x + region.w / 2, y: region.y + region.h / 2 };
  const edges = {
    eLeft:   anchorImg.x          * s,
    eRight:  (imgW - anchorImg.x) * s,
    eTop:    anchorImg.y          * s,
    eBottom: (imgH - anchorImg.y) * s,
  };
  // The circle stands for the detail the author framed, and detail only exists
  // where there is image. A focal near a corner carries a circle that reaches
  // past the image's own edge — at x 0.05 on a 1200 px-wide image the radius is
  // 106.6 image px against 60 to the edge — and the part that overhangs holds
  // nothing. Reserving room for it put background on screen; requiring it on
  // screen asked for the impossible. Capped at the largest circle centred on
  // the anchor that lies inside the image, which is scale-free: the overhang
  // is a property of where the focal sits, not of how far in the viewer is.
  const radiusPx = Math.min(
    (diameterImg * s) / 2,
    edges.eLeft, edges.eRight, edges.eTop, edges.eBottom,
  );
  const F = _clampFocalPx(region, edges, CB, radiusPx);  // focal target position, element px

  return { s, anchorImg, anchorPx: F };
}

/**
 * The image point a step places at the region centre (pure): the image centre
 * at zoom ≤ 1, the authored focal point, as given, at any zoom above 1.
 *
 * @param {{x:number,y:number}} focalImg  Authored focal point, image px.
 * @param {number} imgW
 * @param {number} imgH
 * @param {number} zoom
 * @returns {{x:number,y:number}} Image px.
 */
function _placedPoint(focalImg, imgW, imgH, zoom) {
  return zoom <= 1 ? { x: imgW / 2, y: imgH / 2 } : focalImg;
}

/**
 * A placement part of the way from one settled placement to another (pure).
 *
 * The scale and the image's top-left corner on screen each move in a straight
 * line, so t = 0 and t = 1 are the two placements exactly and every frame
 * between is continuous in t whatever the two steps' zooms. The conditions
 * that matter on screen — the image covering the region on an axis, or lying
 * inside it — are linear in the corner and the scale, so a condition both
 * placements meet is met on every frame between them.
 *
 * @param {{s:number, anchorImg:{x:number,y:number}, anchorPx:{x:number,y:number}}} from
 * @param {{s:number, anchorImg:{x:number,y:number}, anchorPx:{x:number,y:number}}} to
 * @param {number} t  0 at `from`, 1 at `to`.
 * @returns {{s:number, anchorImg:{x:number,y:number}, anchorPx:{x:number,y:number}}}
 *   Anchored at the image's top-left corner.
 */
export function blendPlacements(from, to, t) {
  const corner = (p) => ({
    x: p.anchorPx.x - p.anchorImg.x * p.s,
    y: p.anchorPx.y - p.anchorImg.y * p.s,
  });
  const a = corner(from);
  const b = corner(to);
  const mix = (u, v) => u + (v - u) * t;
  return {
    s: mix(from.s, to.s),
    anchorImg: { x: 0, y: 0 },
    anchorPx: { x: mix(a.x, b.x), y: mix(a.y, b.y) },
  };
}

/**
 * Where a live viewer puts the image for a framing: the viewer's container
 * rect and the placement framePlacement gives for it there, or null when the
 * viewer is to be left where it is (no source size yet, a title card active,
 * or a framing that computeFocalTarget refuses).
 *
 * @returns {{rect: DOMRect, placement: {s:number, anchorImg:{x:number,y:number}, anchorPx:{x:number,y:number}}}|null}
 */
function _livePlacement(viewerCard, x, y, zoom) {
  // Source dims required; leave viewer at home if unavailable
  const source = viewerCard.osdViewer.world.getItemAt(0)?.source;
  if (!source?.width || !source?.height) return null;

  // Title-card skip: when a title card is active, do not apply compensation
  if (state.activeTitleCardIndex != null) return null;

  // Resolve card geometry
  const r = state.cardOverlayRect;
  const cardBox = r ? { x: r.x, y: r.y, w: r.width, h: r.height } : null;
  const placementMode = _deriveCardPlacement(cardBox, window.innerWidth, window.innerHeight);

  // Compute focal target (pure — no OSD calls)
  const target = computeFocalTarget(x, y, zoom, source.width, source.height, cardBox, placementMode);
  if (!target) return null;

  // Container rect from the wrapper's container element (IiifViewer.containerEl)
  const rect = viewerCard.osdWrapper.containerEl.getBoundingClientRect();
  return { rect, placement: framePlacement(target, zoom, rect) };
}

/**
 * Put a placement on the viewer.
 *
 * The target is expressed as a viewport rectangle and applied with fitBounds, so
 * the apply path reads NO live OSD zoom. This is what makes it robust on the
 * animate path (immediate=false): a pan computed from the live zoom is taken at
 * the TRANSIENT mid-animation zoom and mis-scales. fitBounds reaches the requested
 * settled endpoint by delegating the scale→zoom and centre conversion to OSD's own
 * coordinate transform, with no transient sample and no hand-rolled `k`.
 */
function _applyPlacement(viewerCard, rect, { s, anchorImg, anchorPx: F }, immediate) {
  const vp  = viewerCard.osdViewer.viewport;
  const OSD = window.OpenSeadragon;

  // TARGET RECT — the image-px rectangle that fills the viewer at scale `s`, placed so
  // anchorImg lands at element px F. Its aspect equals the container's, so fitBounds maps
  // it 1:1 (no letterbox growth). After fitBounds the rect centre maps to the container
  // centre, so anchorImg (offset F − centre at scale s) lands exactly at F.
  const visW    = rect.width  / s;   // visible image-px width  at scale s
  const visH    = rect.height / s;   // visible image-px height at scale s
  const topLeft = { x: anchorImg.x - F.x / s, y: anchorImg.y - F.y / s };
  const targetVp = vp.imageToViewportRectangle(
    new OSD.Rect(topLeft.x, topLeft.y, visW, visH)
  );
  vp.fitBounds(targetVp, immediate);
}

function _applyFocalTarget(viewerCard, x, y, zoom, immediate) {
  const live = _livePlacement(viewerCard, x, y, zoom);
  if (!live) return false;
  _applyPlacement(viewerCard, live.rect, live.placement, immediate);
  return true;
}

/**
 * Put a viewer part of the way between two steps' settled placements.
 *
 * Used where the two steps sit either side of zoom 1. An overview places the
 * image centre and a detail places its focal point, so interpolating x/y/zoom
 * and placing each frame would move the image by the focal's offset from
 * centre in the one frame the zoom crosses 1. Both placements are computed
 * from the live geometry, so t = 0 and t = 1 are what each step settles on.
 *
 * @returns {boolean} false when either step cannot be placed.
 */
function _applyBetween(viewerCard, a, b, t) {
  const from = _livePlacement(viewerCard, a.x, a.y, a.zoom);
  const to   = _livePlacement(viewerCard, b.x, b.y, b.zoom);
  if (!from || !to) return false;
  _applyPlacement(viewerCard, to.rect, blendPlacements(from.placement, to.placement, t), true);
  return true;
}

// ── Plate activation and deactivation ────────────────────────────────────────

// ── Plate destruction ────────────────────────────────────────────────────────

/**
 * Destroy a viewer card and release its DOM resources.
 *
 * The IIIF viewer uses the Canvas2D drawer (see iiif-viewer.js), not WebGL,
 * so there is no WebGL context or GPU texture memory to release first — the
 * OpenSeadragon #2693 GPU-leak concern applies only to the WebGL drawer.
 * `osdWrapper.destroy()` (which calls OSD's `viewer.destroy()`) tears down
 * the canvas-drawer viewer; this function then nulls references so the GC
 * can reclaim JS memory and removes the plate element from the DOM.
 *
 * @param {ViewerCard} viewerCard - The card to destroy.
 */
export function destroyIiifCard(viewerCard) {
  if (!viewerCard) return;

  if (viewerCard.osdWrapper && typeof viewerCard.osdWrapper.destroy === 'function') {
    viewerCard.osdWrapper.destroy();
  }
  viewerCard.osdWrapper = null;
  viewerCard.osdViewer = null;

  if (viewerCard.element && viewerCard.element.parentNode) {
    viewerCard.element.parentNode.removeChild(viewerCard.element);
  }
}

// ── Viewer positioning ───────────────────────────────────────────────────────

/**
 * Snap a viewer plate to a position immediately (no animation).
 *
 * Used on initial load, when switching to a different object, and on every
 * frame during scroll-driven IIIF lerp (immediate=true so OSD skips its
 * spring — smoothness comes from Lenis calling every frame, not OSD springs).
 *
 * Applies the two-circle target via _applyFocalTarget: the focal circle is
 * inscribed in the uncovered region (scale = max(scaleCircle, scaleFit)) and placed
 * at the clamped region centre by fitting the corresponding image-px rectangle with
 * vp.fitBounds. Rule A and the keep-circle clamp are enforced inside _applyFocalTarget.
 *
 * @param {ViewerCard} viewerCard - The card to position.
 * @param {number} x - Normalised horizontal position (0–1).
 * @param {number} y - Normalised vertical position (0–1).
 * @param {number} zoom - Zoom multiplier relative to home zoom.
 */
export function snapIiifToPosition(viewerCard, x, y, zoom) {
  if (!viewerCard || !viewerCard.osdViewer) {
    console.warn('snapIiifToPosition: viewer not ready for snap');
    return;
  }
  // Apply the recipe with immediate=true (snap, no OSD spring)
  _applyFocalTarget(viewerCard, x, y, zoom, true);
}

// Seconds the viewer takes to pan and zoom, and the spring's approach to it.
// This spring drives the viewer only where the per-frame interpolation does
// not: across an object change, which is the one move the interpolation bails
// out of. Everywhere else the scroll paces the viewer and this is written
// over each frame. It matches the pace of a move for that reason — a scene
// change is a move like any other, and a reader should not be able to tell
// which of the two carried the image.
// Restoring OSD's own values has to outlast the spring, so the restore is
// derived from the duration in force rather than stated as a second number
// that has to be kept in step with it by hand.
const PAN_ZOOM_SECONDS = 1.2;
const PAN_ZOOM_STIFFNESS = 0.8;

/**
 * Read a tuning override for the pan and zoom from the query string.
 *
 * `?panzoom=6` gives a six-second travel, `?panzoom=6,0.5` a six-second
 * travel on a gentler spring. A value outside the range leaves the default,
 * so a mistyped switch cannot stall the viewer for a minute or snap it in a
 * frame. Resolved once, and only for as long as the duration is being
 * settled — it goes when the number does, the same standing as the
 * card-height switch.
 *
 * @returns {{ seconds: number, stiffness: number }}
 */
let _panZoomTuning = null;
function _panZoomSettings() {
  if (_panZoomTuning) return _panZoomTuning;

  _panZoomTuning = { seconds: PAN_ZOOM_SECONDS, stiffness: PAN_ZOOM_STIFFNESS };
  try {
    const raw = new URLSearchParams(window.location.search).get('panzoom');
    if (raw) {
      const [s, k] = raw.split(',').map(Number);
      if (s >= 0.2 && s <= 20) _panZoomTuning.seconds = s;
      if (k > 0 && k <= 10) _panZoomTuning.stiffness = k;
    }
  } catch {
    // A URL we cannot read leaves the defaults standing.
  }
  return _panZoomTuning;
}

/**
 * Animate a viewer plate to a position.
 *
 * Used when the user navigates via keyboard or button to a step with the
 * same object — the viewer pans and zooms smoothly to the new coordinates
 * using OSD's built-in spring animation. Animation time and spring stiffness
 * are temporarily raised from OSD's defaults and restored once the spring
 * has settled.
 *
 * Click-to-zoom is disabled during the animation to prevent accidental zooms.
 *
 * Applies the validated two-circle OSD recipe via _applyFocalTarget.
 * Reduced-motion: passes immediate=true to bypass OSD spring (snap immediately).
 *
 * @param {ViewerCard} viewerCard - The card to animate.
 * @param {number} x - Normalised horizontal position (0–1).
 * @param {number} y - Normalised vertical position (0–1).
 * @param {number} zoom - Zoom multiplier relative to home zoom.
 */
export function animateIiifToPosition(viewerCard, x, y, zoom) {
  if (!viewerCard || !viewerCard.osdViewer) {
    console.warn('animateIiifToPosition: viewer not ready for animation');
    return;
  }

  const osdViewer = viewerCard.osdViewer;
  const { seconds, stiffness } = _panZoomSettings();

  // Reduced-motion users: bypass OSD spring animation; snap immediately.
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  osdViewer.gestureSettingsMouse.clickToZoom = false;
  osdViewer.gestureSettingsTouch.clickToZoom = false;

  const originalAnimationTime    = osdViewer.animationTime;
  const originalSpringStiffness  = osdViewer.springStiffness;

  osdViewer.animationTime   = seconds;
  osdViewer.springStiffness = stiffness;

  // Apply the recipe: immediate=true for reduced-motion, false for spring animation
  _applyFocalTarget(viewerCard, x, y, zoom, prefersReduced);

  setTimeout(() => {
    osdViewer.animationTime   = originalAnimationTime;
    osdViewer.springStiffness = originalSpringStiffness;
  }, seconds * 1000 + 100);
}

// ── Per-frame IIIF interpolation ─────────────────────────────────────────────

/** The object a step shows, under either of the names step data carries it by. */
function _objectOf(step) {
  return step.object || step.objectId || '';
}

/**
 * A step's x, y and zoom as numbers, or null when any of them is not one.
 *
 * Not `stepFraming`, which falls back to the whole object per axis: a pair of
 * steps with a cell that is not a number is not interpolated at all, and the
 * viewer keeps the framing the step's own activation gave it.
 */
function _authoredFraming(step) {
  const x = parseFloat(step.x), y = parseFloat(step.y), zoom = parseFloat(step.zoom);
  if (isNaN(x) || isNaN(y) || isNaN(zoom)) return null;
  return { x, y, zoom };
}

/** Whether a viewer already rests at this framing for this step. */
function _restsAt(settled, stepIndex, x, y, zoom) {
  return Boolean(settled) && settled.step === stepIndex &&
    settled.x === x && settled.y === y && settled.zoom === zoom;
}

/**
 * Interpolate IIIF viewer position between two steps based on scroll progress.
 *
 * Called every frame by the scroll engine's rAF loop. For step pairs that
 * share the same object, linearly interpolates x/y/zoom between step A and
 * step B based on the fractional scroll progress (0.0 = at step A, 1.0 =
 * at step B). Applies the interpolated position via snapIiifToPosition
 * with immediate=true, so OSD does not add its own spring animation on top
 * of the per-frame updates. Where one step is at zoom 1 or below and the
 * other above it, the frame is the two settled placements blended
 * (blendPlacements), applied the same way.
 *
 * Different-object pairs are skipped entirely (the viewer freezes at
 * its last position while the new plate slides in on top). Progress values
 * below 0.001 are also skipped — at exact integer positions the viewer is
 * already at the correct coordinates and does not need interpolation.
 *
 * @param {number} stepIndex - Current step index (floor of scroll position).
 * @param {number} progress - Fractional progress 0.0–1.0 toward next step.
 * @param {Array} stepsData - Filtered step data (metadata rows removed), in the
 *   same index space as stepIndex / state.stepToScene (i.e. state.stepsData).
 */
export function lerpIiifPosition(stepIndex, progress, stepsData) {
  const stepA = stepsData[stepIndex];
  const stepB = stepsData[stepIndex + 1];
  if (!stepA || !stepB) return;

  if (_objectOf(stepA) !== _objectOf(stepB)) return; // different object, freeze

  const a = _authoredFraming(stepA);
  const b = _authoredFraming(stepB);
  if (!a || !b) return;

  // A whole step is a resting place, and the framing there is the author's
  // own, stated rather than approached. The interpolation stops a fraction of
  // a step short — the scroll settles and the last frame written is the one
  // before the boundary — so a step reached this way would otherwise keep the
  // framing of a position just outside it. Stating the authored endpoint
  // exactly is what a reader resting on a step is owed.
  const atRest = progress < 0.001;

  // Keyed by scene, not by objectId: an object appearing in several scenes has
  // a plate for each, and an objectId lookup finds the wrong one on backward
  // navigation. `isReady` is the image plate's own flag, so a plate holding a
  // player answers undefined and is passed over.
  const viewerCard = state.viewerPlates[state.stepToScene[stepIndex]];
  if (!viewerCard || !viewerCard.isReady) return;

  // At rest the same framing is true on every frame, and a snap is a forced
  // layout in OSD, so the resting write happens once per arrival rather than
  // for as long as the reader stays on the step.
  if (atRest) {
    if (_restsAt(viewerCard.settledAt, stepIndex, a.x, a.y, a.zoom)) return;
    viewerCard.settledAt = { step: stepIndex, ...a };
    snapIiifToPosition(viewerCard, a.x, a.y, a.zoom);
    return;
  }

  viewerCard.settledAt = null;
  _travel(viewerCard, a, b, progress);
}

/**
 * Put a viewer part of the way from one step's framing to the next.
 *
 * Either side of zoom 1 the two steps place different image points (the
 * centre and the focal point), so the frame is the two settled placements
 * blended rather than a placement of the blended x/y/zoom.
 */
function _travel(viewerCard, a, b, t) {
  if ((a.zoom <= 1) !== (b.zoom <= 1)) {
    _applyBetween(viewerCard, a, b, t);
    return;
  }
  const along = (from, to) => from + (to - from) * t;
  snapIiifToPosition(viewerCard, along(a.x, b.x), along(a.y, b.y), along(a.zoom, b.zoom));
}

// ── Recompute on resize / layout change ──────────────────────────────────────

/**
 * Re-snap the currently active IIIF viewer to its authored position.
 *
 * Looks up the active viewer card (the one whose plate element carries
 * is-active), reads the active step's authored x/y/zoom from
 * window.storyData.steps, and calls snapIiifToPosition so the
 * compensation runs again with the current (post-resize) cardOverlayRect
 * and viewport dimensions.
 *
 * Called by the onViewportResize and onLayoutChange subscribers below, and by
 * card-pool.js when the active card's overlay rect is measured for the first
 * time (until then the focal target works from the CSS-derived default box).
 */
export function reSnapActiveViewer() {
  // Found by the plate element's is-active class, not by
  // state.currentObjectRun.objectId, which is not unique when the same object
  // appears in several scenes.
  const viewerCard = Object.values(state.viewerPlates).find(
    plate => plate.container?.classList.contains('is-active')
  );
  if (!viewerCard || !viewerCard.isReady) return;

  // Find the active text card to retrieve its step index
  const activeTextCard = document.querySelector('.text-card.is-active');
  if (!activeTextCard) return;

  const stepIndex = parseInt(activeTextCard.dataset.stepIndex, 10);
  if (isNaN(stepIndex)) return;

  // Retrieve authored x/y/zoom from the global story data
  const steps = (window.storyData?.steps || []).filter(s => !s._metadata);
  const step = steps[stepIndex];
  if (!step) return;

  // A cell left blank falls back as it does on activation: to the whole object.
  const { x, y, zoom } = stepFraming(step);
  snapIiifToPosition(viewerCard, x, y, zoom);
}

// Subscribe to layout-mode events (no new ad-hoc resize listeners).
//
// onViewportResize: 100ms-debounced, fires on desktop resize + orientationchange.
// Re-snaps the active viewer so the compensation is recalculated with the new
// viewport dimensions and (if card-pool has already recomputed) the updated
// state.cardOverlayRect.
onViewportResize(() => {
  reSnapActiveViewer();
});

// onLayoutChange: fires on horizontal↔vertical mode flip, BEFORE onViewportResize.
// main.js's onLayoutChange handler updates state.cardOverlayRect first.
// Wrap the re-snap in requestAnimationFrame so CSS reflows before we read the rect,
// guaranteeing the post-reflow geometry.
onLayoutChange(() => {
  requestAnimationFrame(() => {
    // Re-read the active card rect after the CSS reflow has settled.
    const activeCard = document.querySelector('.text-card.is-active');
    state.cardOverlayRect = activeCard ? activeCard.getBoundingClientRect() : null;
    reSnapActiveViewer();
  });
});
