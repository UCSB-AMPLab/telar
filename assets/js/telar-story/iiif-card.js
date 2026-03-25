/**
 * Telar Story – IIIF Card Positioning and Lifecycle
 *
 * This module handles the positioning, activation, destruction, and
 * per-frame interpolation of IIIF viewer plates in the card-stack layout.
 * It does NOT create viewer plates or inject Tify instances — that work
 * lives in card-pool.js, which pre-creates all plate DOM elements at init
 * time and injects Tify on demand via its internal _initTifyInPlate().
 *
 * The separation exists because the card-pool module owns the full card
 * lifecycle (creation, ordering, preloading), while this module provides
 * the OSD-specific operations that card-pool and scroll-engine call into:
 *
 *   Positioning — `snapIiifToPosition()` and `animateIiifToPosition()`
 *   convert normalised x/y/zoom coordinates from step data into the values
 *   OpenSeadragon expects, applying a shift to compensate for the text card
 *   overlay. On desktop the card covers ~39% from the left, so the image is
 *   shifted leftward. On mobile the card covers ~40% from the bottom, so the
 *   image is shifted upward. Both shifts move the pan target so the detail
 *   appears centred in the VISIBLE area. Zoom is left unchanged — coordinates
 *   describe image content, not layout.
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
 *   Tify's destroy(). OpenSeadragon holds WebGL render state that the browser
 *   cannot reclaim until the context is explicitly released. Per OSD issue
 *   #2693, the module calls WEBGL_lose_context.loseContext() first, then
 *   Tify.destroy(), then removes the DOM element.
 *
 * @version v1.0.0-beta
 */

import { state } from './state.js';
import { calculateViewportPosition } from './utils.js';

// ── Type definition ──────────────────────────────────────────────────────────

/**
 * @typedef {Object} ViewerCard
 * @property {string} objectId - The object this card displays.
 * @property {number|undefined} page - Page number for multi-page objects.
 * @property {HTMLElement} element - The plate's container element in the DOM.
 * @property {Object|null} tifyInstance - The Tify viewer instance.
 * @property {Object|null} osdViewer - The OpenSeadragon viewer (null until ready).
 * @property {boolean} isReady - Whether the OSD viewer has initialised.
 * @property {Object|null} pendingZoom - Queued position to apply when ready.
 * @property {number} zIndex - The plate's stacking order in the card stack.
 */

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

  console.log(`deactivateIiifCard: ${viewerCard.objectId} (${direction})`);
}

// ── Plate destruction ────────────────────────────────────────────────────────

/**
 * Destroy a viewer card and release its GPU and DOM resources.
 *
 * The destruction order matters — per OpenSeadragon issue #2693, GPU
 * memory is not automatically freed when a canvas element is removed from
 * the DOM. The WebGL context holds references to textures, framebuffers,
 * and shaders that persist until the context itself is lost. On mobile
 * devices with limited GPU memory, failing to release contexts causes
 * visible corruption or crashes after cycling through several objects.
 *
 * Order of operations:
 *   1. Obtain the WebGL rendering context from the OSD drawer's canvas.
 *   2. Call WEBGL_lose_context.loseContext() to release GPU memory.
 *   3. Call Tify.destroy() to clean up the viewer instance.
 *   4. Null out references so the garbage collector can reclaim JS memory.
 *   5. Remove the plate element from the DOM.
 *
 * @param {ViewerCard} viewerCard - The card to destroy.
 */
export function destroyIiifCard(viewerCard) {
  if (!viewerCard) return;

  console.log(`destroyIiifCard: ${viewerCard.objectId}`);

  // Release WebGL GPU memory before Tify destroy (OSD issue #2693)
  if (viewerCard.osdViewer) {
    const canvas = viewerCard.osdViewer.drawer?.canvas;
    if (canvas) {
      const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      if (gl) {
        gl.getExtension('WEBGL_lose_context')?.loseContext();
      }
    }
  }

  if (viewerCard.tifyInstance && typeof viewerCard.tifyInstance.destroy === 'function') {
    viewerCard.tifyInstance.destroy();
  }
  viewerCard.tifyInstance = null;
  viewerCard.osdViewer = null;

  if (viewerCard.element && viewerCard.element.parentNode) {
    viewerCard.element.parentNode.removeChild(viewerCard.element);
  }
}

// ── Viewer positioning ───────────────────────────────────────────────────────

/**
 * Compensate the OSD viewport position for the text card overlay.
 *
 * The text card covers ~39% of the viewport from the left (left:4% +
 * width:35%). OSD centres the target point in the full canvas, but the
 * user only sees the right ~61%. This shifts the pan target LEFT so the
 * image detail appears centred in the VISIBLE area.
 *
 * The viewport width in image coordinates is 1/actualZoom, which accounts
 * for both width-constrained and height-constrained image fitting. The
 * shift amount is (CARD_FRAC / 2) * viewportWidth — half the card's
 * fractional width, because we want to offset the visible centre, not
 * the visible edge.
 *
 * Zoom is left unchanged — the author's intended magnification describes
 * image content, not layout geometry.
 *
 * @param {Object} viewport - OSD viewport instance.
 * @param {{ x: number, y: number }} point - Target point in image coords.
 * @param {number} actualZoom - Target zoom level.
 * @returns {{ point: { x: number, y: number }, actualZoom: number }}
 */
function _compensateForCardOverlay(viewport, point, actualZoom) {
  if (state.isMobileViewport) {
    // Mobile: bottom-anchored text card covers up to 40vh.
    // Shift viewport centre downward so the focal point appears in the visible
    // area above the card, and zoom out proportionally.
    const CARD_FRAC_MOBILE = 0.40;          // max-height: 40vh from CSS
    const viewportWidth    = 1 / actualZoom;
    const aspectRatio      = window.innerHeight / window.innerWidth;
    const viewportHeight   = viewportWidth * aspectRatio;
    const shiftY           = (CARD_FRAC_MOBILE / 2) * viewportHeight;
    const visibleFraction  = 1 - CARD_FRAC_MOBILE;  // 0.60

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

/**
 * Snap a viewer plate to a position immediately (no animation).
 *
 * Used on initial load, when switching to a different object, and on every
 * frame during scroll-driven IIIF lerp. The immediate=true flag on panTo
 * and zoomTo tells OSD to skip its spring animation and jump straight to
 * the target — smoothness during scroll comes from Lenis calling this
 * function every frame with interpolated coordinates, not from OSD springs.
 *
 * Applies _compensateForCardOverlay() so the image detail appears centred
 * in the visible area rather than behind the text card.
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

  const osdViewer = viewerCard.osdViewer;
  const viewport = osdViewer.viewport;
  let { point, actualZoom } = calculateViewportPosition(viewport, x, y, zoom);

  ({ point, actualZoom } = _compensateForCardOverlay(viewport, point, actualZoom));

  console.log(`snapIiifToPosition: ${viewerCard.objectId} x=${x} y=${y} zoom=${zoom}`);

  viewport.panTo(point, true);
  viewport.zoomTo(actualZoom, point, true);
}

/**
 * Animate a viewer plate to a position over 4 seconds.
 *
 * Used when the user navigates via keyboard or button to a step with the
 * same object — the viewer pans and zooms smoothly to the new coordinates
 * using OSD's built-in spring animation. The animation time and spring
 * stiffness are temporarily increased from their defaults, then restored
 * after the animation completes.
 *
 * Click-to-zoom is disabled during the animation to prevent the user from
 * accidentally triggering a zoom while the viewer is in motion.
 *
 * Applies _compensateForCardOverlay() so the image detail appears centred
 * in the visible area rather than behind the text card.
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
  const viewport = osdViewer.viewport;
  let { point, actualZoom } = calculateViewportPosition(viewport, x, y, zoom);

  ({ point, actualZoom } = _compensateForCardOverlay(viewport, point, actualZoom));

  console.log(`animateIiifToPosition: ${viewerCard.objectId} x=${x} y=${y} zoom=${zoom} over 4s`);

  osdViewer.gestureSettingsMouse.clickToZoom = false;
  osdViewer.gestureSettingsTouch.clickToZoom = false;

  const originalAnimationTime = osdViewer.animationTime;
  const originalSpringStiffness = osdViewer.springStiffness;

  osdViewer.animationTime = 4.0;
  osdViewer.springStiffness = 0.8;

  viewport.panTo(point, false);
  viewport.zoomTo(actualZoom, point, false);

  setTimeout(() => {
    osdViewer.animationTime = originalAnimationTime;
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
  if (objectIdA !== objectIdB) return; // D-13: different object, freeze

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
