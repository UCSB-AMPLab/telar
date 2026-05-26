/**
 * Telar Story – IIIF Card Positioning and Lifecycle
 *
 * This module handles the positioning, activation, destruction, and
 * per-frame interpolation of IIIF viewer plates in the card-stack layout.
 * It does NOT create viewer plates or inject viewer instances — that work
 * lives in card-pool.js, which pre-creates all plate DOM elements at init
 * time and injects the IIIF wrapper on demand via its internal
 * _initOsdInPlate() (renamed from _initTifyInPlate in v1.4.0).
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
 *   Smoothness comes from Lenis's animatedScroll, not from OSD animations.
 *   Different-object pairs are skipped — the viewer freezes at its last
 *   position while the new plate slides in on top.
 *
 *   Activation/deactivation — `deactivateIiifCard()` handles direction-aware
 *   plate transitions. Forward: the plate stays in place (covered by the next
 *   plate's higher z-index). Backward: the plate slides back down via
 *   translateY(100%).
 *
 *   Destruction — `destroyIiifCard()` releases GPU memory before calling
 *   the wrapper's destroy(). OpenSeadragon holds WebGL render state that
 *   the browser cannot reclaim until the context is explicitly released.
 *   Per OSD issue #2693, the module calls WEBGL_lose_context.loseContext()
 *   first, then the wrapper's destroy(), then removes the DOM element.
 *
 * @version v1.4.0
 */

import { state } from './state.js';
import { onViewportResize, onLayoutChange, isLandscapeSideCard } from './layout-mode.js';

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
// Shared helpers used by computeFocalTarget and _compensateForCardOverlay.
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
// Runtime constants for the two-circle centring model.
// AUTHORING_ASPECT: canonical authoring-viewport aspect ratio — mean of the
//   Compositor (1.084) and the object-page coord-picker (1.022), giving
//   symmetric worst-case error of ~3%.
// FOCAL_DIAMETER_FRAC: focal circle diameter as a fraction of the authored
//   frame width (0.90 = 90%). Faithful to author framing; low risk of clipping
//   deliberately-included edge subject matter.
// These are NOT author-tunable; they are runtime framework constants.
const AUTHORING_ASPECT    = 1.053;  // canonical authoring-viewport aspect ratio
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
 * Title-card skip is NOT applied here — it lives in _compensateForCardOverlay
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
  // homeZoomAuth  = imageAspect / AUTHORING_ASPECT  (canonical, device-independent)
  // frameWidthImg = imageW / (homeZoomAuth · zoom)   (authored frame width in image px)
  // diameterImg   = FOCAL_DIAMETER_FRAC · frameWidthImg
  const imageAspect    = imageW / imageH;
  const homeZoomAuth   = imageAspect / AUTHORING_ASPECT;
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
 *   - SCALE: s = max(s_tgt, s_cap) — element px per image px, where
 *       s_tgt = min(region.w, region.h) / diameterImg  (radius match, Circle A→B)
 *       s_cap = min(rect.width/imgW, rect.height/imgH) (Rule A: whole-image fit).
 *     No OSD-zoom calibration (no `k`): fitBounds derives the zoom from the rect.
 *   - FOCAL: move the focal image point to the uncovered-region centre, clamped to
 *     image bounds (Rule B, _clampFocalPx) — keep scale, drift focal toward the edge
 *     rather than reveal background. Does NOT rely on OSD's visibilityRatio.
 *   - APPLY: build the image-px rectangle that fills the viewer at scale s with the
 *     focal at the clamped position, then vp.fitBounds(rect, immediate). Because the
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

/**
 * Rule B focal clamp (pure). Given the uncovered `region`, the focal-to-image-edge
 * distances in element px at the applied scale (`edges`), and the `ideal` focal
 * position in element px (the uncovered-region centre), return the focal's target
 * position in element px so the image keeps covering the region.
 *
 * Requiring the image (focal ± edges) to cover the region gives, per axis:
 *   focal − eLeft  ≤ region.x          and   focal + eRight ≥ region.x + region.w
 * ⇒ focal ∈ [region.x + region.w − eRight, region.x + eLeft]
 * We clamp the ideal (centre) position into that interval. When the image is
 * NARROWER than the region on an axis (eLeft + eRight < region.w) the interval
 * inverts — the image cannot cover the region — so we keep the ideal position
 * (focal at the region centre) on that axis instead of clamping.
 *
 * Note: this returns the target focal POSITION (not a pan delta) and reads no live
 * OSD state, so the apply path is independent of the transient (mid-animation) zoom.
 *
 * @param {{x:number,y:number,w:number,h:number}} region  Uncovered region, element px.
 * @param {{eLeft:number,eRight:number,eTop:number,eBottom:number}} edges  Focal→edge px at applied scale.
 * @param {{x:number,y:number}} ideal   Ideal focal position (the region centre), element px.
 * @returns {{x:number,y:number}} The clamped focal position in element px.
 */
export function _clampFocalPx(region, edges, ideal) {
  const loX = region.x + region.w - edges.eRight;  // focal lower bound (cover right edge)
  const hiX = region.x + edges.eLeft;              // focal upper bound (cover left edge)
  const loY = region.y + region.h - edges.eBottom;
  const hiY = region.y + edges.eTop;
  return {
    x: loX <= hiX ? Math.max(loX, Math.min(hiX, ideal.x)) : ideal.x,
    y: loY <= hiY ? Math.max(loY, Math.min(hiY, ideal.y)) : ideal.y,
  };
}

function _applyFocalTarget(viewerCard, x, y, zoom, immediate) {
  const v  = viewerCard.osdViewer;
  const av = viewerCard.osdWrapper;

  // A2 guard: source dims required; leave viewer at home if unavailable
  const source = v.world.getItemAt(0)?.source;
  if (!source?.width || !source?.height) return false;
  const imgW = source.width;
  const imgH = source.height;

  // Title-card skip: when a title card is active, do not apply compensation
  if (state.activeTitleCardIndex != null) return false;

  // Resolve card geometry
  const viewportW = window.innerWidth;
  const viewportH = window.innerHeight;
  const r = state.cardOverlayRect;
  const cardBox = r ? { x: r.x, y: r.y, w: r.width, h: r.height } : null;
  const placementMode = _deriveCardPlacement(cardBox, viewportW, viewportH);

  // Compute focal target (pure — no OSD calls)
  const target = computeFocalTarget(x, y, zoom, imgW, imgH, cardBox, placementMode);
  if (!target) return false;
  const { focalImg, diameterImg, region } = target;

  // ── OSD apply recipe (fitBounds form) ────────────────────────────────────────
  // The target is expressed as a viewport rectangle and applied with fitBounds, so
  // the apply path reads NO live OSD zoom. This is what makes it robust on the
  // animate path (immediate=false): the prior zoomTo + panBy recipe computed the pan
  // from `cur` and `deltaPointsFromPixels` at the TRANSIENT mid-animation zoom, so the
  // focal mis-scaled. fitBounds reaches the identical settled endpoint — scale
  // = max(scaleCircle, scaleFit) (radius match + Rule A) and focal at the clamped
  // region centre (Rule B) — by delegating the scale→zoom and centre conversion to
  // OSD's own coordinate transform, with no transient sample and no hand-rolled `k`.
  const vp   = v.viewport;
  const OSD  = window.OpenSeadragon;
  // Container rect from the wrapper's container element (IiifViewer.containerEl)
  const rect = av.containerEl.getBoundingClientRect();

  // SCALE — radius match (Circle A→B) with the Rule A overview cap. `s` is element px
  // per image px; z_tgt/k reduces to exactly this, so no OSD-zoom calibration is needed.
  const s_tgt = Math.min(region.w, region.h) / diameterImg;     // radius match (Circle A→B)
  const s_cap = Math.min(rect.width / imgW, rect.height / imgH); // Rule A: whole-image fit
  const s     = Math.max(s_tgt, s_cap);                          // applied scale (px / img px)

  // FOCAL POSITION — uncovered-region centre, clamped to image bounds (Rule B). The
  // edges are the focal→image-edge distances at the applied scale `s`; all element px.
  const CB    = { x: region.x + region.w / 2, y: region.y + region.h / 2 };
  const edges = {
    eLeft:   focalImg.x          * s,
    eRight:  (imgW - focalImg.x) * s,
    eTop:    focalImg.y          * s,
    eBottom: (imgH - focalImg.y) * s,
  };
  const F = _clampFocalPx(region, edges, CB);  // focal target position, element px

  // TARGET RECT — the image-px rectangle that fills the viewer at scale `s`, placed so
  // focalImg lands at element px F. Its aspect equals the container's, so fitBounds maps
  // it 1:1 (no letterbox growth). After fitBounds the rect centre maps to the container
  // centre, so focalImg (offset F − centre at scale s) lands exactly at F.
  const visW    = rect.width  / s;   // visible image-px width  at scale s
  const visH    = rect.height / s;   // visible image-px height at scale s
  const topLeft = { x: focalImg.x - F.x / s, y: focalImg.y - F.y / s };
  const targetVp = vp.imageToViewportRectangle(
    new OSD.Rect(topLeft.x, topLeft.y, visW, visH)
  );
  vp.fitBounds(targetVp, immediate);

  return true;
}

/**
 * Compensate the OSD viewport position for the text card overlay.
 *
 * Reads state.cardOverlayRect (DOMRect from card-pool.js activation, or null)
 * and window.innerWidth/innerHeight. Derives the card placement mode from
 * rect geometry. Returns the focal-target result from computeFocalTarget.
 *
 * Returns null when:
 *   - A title card is currently active (state.activeTitleCardIndex != null)
 *   - Inputs are insane (out-of-range x/y/zoom or non-positive dims)
 *
 * @param {number} x        Authored focal-point x in [0, 1].
 * @param {number} y        Authored focal-point y in [0, 1].
 * @param {number} zoom     Authored zoom multiplier (> 0).
 * @param {number} imageW   Image width in px (from OSD TiledImage source).
 * @param {number} imageH   Image height in px (from OSD TiledImage source).
 * @returns {{ focalImg: {x: number, y: number}, diameterImg: number,
 *             region: {x: number, y: number, w: number, h: number},
 *             imageW: number, imageH: number }|null}
 */
export function _compensateForCardOverlay(x, y, zoom, imageW, imageH) {
  // Title-card skip: no text card overlay when title card is active
  if (state.activeTitleCardIndex != null) return null;

  const viewportW = window.innerWidth;
  const viewportH = window.innerHeight;

  // Map DOMRect to { x, y, w, h } shape, or null for CSS default
  const r = state.cardOverlayRect;
  const cardBox = r ? { x: r.x, y: r.y, w: r.width, h: r.height } : null;

  // Derive placement from measured rect geometry
  const placementMode = _deriveCardPlacement(cardBox, viewportW, viewportH);

  return computeFocalTarget(x, y, zoom, imageW, imageH, cardBox, placementMode);
}

// ── Plate activation and deactivation ────────────────────────────────────────

/**
 * Deactivate a viewer plate.
 *
 * Direction determines the visual transition:
 *
 *   Forward — the plate stays at translateY(0). It is not visible because
 *   the incoming plate has a higher z-index and covers it. We only remove
 *   the is-active class so CSS knows the plate is no longer current.
 *
 *   Backward — the plate slides back down via translateY(100%), reversing
 *   the slide-up animation that brought it into view. The plate below it
 *   (which was already at translateY(0)) becomes visible again.
 *
 * @param {ViewerCard} viewerCard - The card to deactivate.
 * @param {'forward'|'backward'} direction - Navigation direction.
 */
export function deactivateIiifCard(viewerCard, direction) {
  if (!viewerCard || !viewerCard.element) return;

  viewerCard.element.classList.remove('is-active');

  if (direction === 'backward') {
    viewerCard.element.style.transform = 'translateY(100%)';
  }
  // Forward: plate stays at translateY(0) — covered by newer higher-z plate
}

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
 * vp.fitBounds. Rule A and Rule B are enforced inside _applyFocalTarget.
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

/**
 * Animate a viewer plate to a position over 4 seconds.
 *
 * Used when the user navigates via keyboard or button to a step with the
 * same object — the viewer pans and zooms smoothly to the new coordinates
 * using OSD's built-in spring animation. Animation time and spring stiffness
 * are temporarily increased from their defaults, then restored after 4.1 s.
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

  // Reduced-motion users: bypass OSD spring animation; snap immediately.
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  osdViewer.gestureSettingsMouse.clickToZoom = false;
  osdViewer.gestureSettingsTouch.clickToZoom = false;

  const originalAnimationTime    = osdViewer.animationTime;
  const originalSpringStiffness  = osdViewer.springStiffness;

  osdViewer.animationTime   = 4.0;
  osdViewer.springStiffness = 0.8;

  // Apply the recipe: immediate=true for reduced-motion, false for spring animation
  _applyFocalTarget(viewerCard, x, y, zoom, prefersReduced);

  setTimeout(() => {
    osdViewer.animationTime   = originalAnimationTime;
    osdViewer.springStiffness = originalSpringStiffness;
  }, 4100);
}

// ── Per-frame IIIF interpolation ─────────────────────────────────────────────

/**
 * Interpolate IIIF viewer position between two steps based on scroll progress.
 *
 * Called every frame by the scroll engine's rAF loop. For step pairs that
 * share the same object, linearly interpolates x/y/zoom between step A and
 * step B based on the fractional scroll progress (0.0 = at step A, 1.0 =
 * at step B). Applies the interpolated position via snapIiifToPosition
 * with immediate=true, so OSD does not add its own spring animation on top
 * of the per-frame updates.
 *
 * Different-object pairs are skipped entirely (the viewer freezes at
 * its last position while the new plate slides in on top). Progress values
 * below 0.001 are also skipped — at exact integer positions the viewer is
 * already at the correct coordinates and does not need interpolation.
 *
 * @param {number} stepIndex - Current step index (floor of scroll position).
 * @param {number} progress - Fractional progress 0.0–1.0 toward next step.
 * @param {Array} stepsData - All step data objects from window.storyData.
 */
export function lerpIiifPosition(stepIndex, progress, stepsData) {
  if (progress < 0.001) return; // At exact integer, no interpolation needed

  const stepA = stepsData[stepIndex];
  const stepB = stepsData[stepIndex + 1];
  if (!stepA || !stepB) return;

  const objectIdA = stepA.object || stepA.objectId || '';
  const objectIdB = stepB.object || stepB.objectId || '';
  if (objectIdA !== objectIdB) return; // different object, freeze

  const xA = parseFloat(stepA.x), yA = parseFloat(stepA.y), zA = parseFloat(stepA.zoom);
  const xB = parseFloat(stepB.x), yB = parseFloat(stepB.y), zB = parseFloat(stepB.zoom);

  if (isNaN(xA) || isNaN(yA) || isNaN(zA)) return;
  if (isNaN(xB) || isNaN(yB) || isNaN(zB)) return;

  const x    = xA + (xB - xA) * progress;
  const y    = yA + (yB - yA) * progress;
  const zoom = zA + (zB - zA) * progress;

  // Find the active viewer card for this scene (not by objectId — repeated objects have
  // multiple scenes and objectId lookup would find the wrong one on backward nav).
  const sceneIndex = state.stepToScene[stepIndex];
  if (sceneIndex === undefined || sceneIndex < 0) return;
  const viewerCard = state.viewerCards.find(vc => vc.sceneIndex === sceneIndex);
  if (!viewerCard || !viewerCard.isReady) return;

  snapIiifToPosition(viewerCard, x, y, zoom);
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
 * Called by the onViewportResize and onLayoutChange subscribers below.
 */
function _reSnapActiveViewer() {
  // Find the active viewer card by its plate element's is-active class.
  // (Do not use state.currentObjectRun.objectId — it is not unique when the
  // same object appears in multiple scenes; use the element flag instead.)
  const viewerCard = state.viewerCards.find(
    vc => vc.element && vc.element.classList.contains('is-active')
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

  const x    = parseFloat(step.x);
  const y    = parseFloat(step.y);
  const zoom = parseFloat(step.zoom);
  if (isNaN(x) || isNaN(y) || isNaN(zoom)) return;

  snapIiifToPosition(viewerCard, x, y, zoom);
}

// Subscribe to layout-mode events (no new ad-hoc resize listeners).
//
// onViewportResize: 100ms-debounced, fires on desktop resize + orientationchange.
// Re-snaps the active viewer so the compensation is recalculated with the new
// viewport dimensions and (if card-pool has already recomputed) the updated
// state.cardOverlayRect.
onViewportResize(() => {
  _reSnapActiveViewer();
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
    _reSnapActiveViewer();
  });
});
