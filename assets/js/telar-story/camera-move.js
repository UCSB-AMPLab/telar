/**
 * Telar Story – Camera move
 *
 * What a camera move that no scroll paces (iiif-card.js animateIiifToPosition)
 * holds on the viewer while it runs, how it eases, and when it has nothing to
 * travel.
 *
 * @version v1.8.0
 */

// ── Click-to-zoom ────────────────────────────────────────────────────────────
//
// A tap on the image during a move must not zoom it, so the move turns the
// viewer's two click-to-zoom settings off. They are the reader's to have back
// when it ends. A viewer built without zoom gestures has the mouse one off to
// begin with, and the record keeps it off.

/**
 * Turn click-to-zoom off on a plate's viewer, recording the two settings the
 * first time. The record is kept while it exists, so a second hold never
 * records the values the first one wrote.
 *
 * @param {Object} plate  Has osdViewer, and gets heldClickToZoom.
 */
export function holdClickToZoom(plate) {
  const { gestureSettingsMouse: mouse, gestureSettingsTouch: touch } = plate.osdViewer;
  if (!plate.heldClickToZoom) {
    plate.heldClickToZoom = { mouse: mouse.clickToZoom, touch: touch.clickToZoom };
  }
  mouse.clickToZoom = false;
  touch.clickToZoom = false;
}

/**
 * Give a plate's viewer the click-to-zoom settings recorded by holdClickToZoom.
 * Does nothing where nothing is held; a viewer already freed only loses the
 * record.
 *
 * @param {Object} plate
 */
export function releaseClickToZoom(plate) {
  const held = plate.heldClickToZoom;
  if (!held) return;
  plate.heldClickToZoom = null;
  if (!plate.osdViewer) return;
  plate.osdViewer.gestureSettingsMouse.clickToZoom = held.mouse;
  plate.osdViewer.gestureSettingsTouch.clickToZoom = held.touch;
}

// ── Placements that coincide ─────────────────────────────────────────────────

/** Half a screen pixel: a move smaller than this is not seen. */
const UNSEEN_PX = 0.5;

/**
 * Whether two placements show the image the same way to within half a screen
 * pixel (pure): the image's top-left corner differs by less than that on each axis,
 * and so does the point at the container's far edge, where a difference of
 * scale moves the image most.
 *
 * @param {{s:number, anchorImg:{x:number,y:number}, anchorPx:{x:number,y:number}}} a
 * @param {{s:number, anchorImg:{x:number,y:number}, anchorPx:{x:number,y:number}}} b
 * @param {{width:number,height:number}} container  Element px.
 * @returns {boolean}
 */
export function placementsCoincide(a, b, container) {
  const topLeft = (p) => ({
    x: p.anchorPx.x - p.anchorImg.x * p.s,
    y: p.anchorPx.y - p.anchorImg.y * p.s,
  });
  const ca = topLeft(a);
  const cb = topLeft(b);
  const edge = Math.abs(a.s / b.s - 1);
  return Math.abs(ca.x - cb.x) < UNSEEN_PX &&
    Math.abs(ca.y - cb.y) < UNSEEN_PX &&
    edge * container.width < UNSEEN_PX &&
    edge * container.height < UNSEEN_PX;
}

// ── The move's own curve and start ────────────────────────────────────────────

/** The ease-out cubic every move to a step runs on. */
export const easeOut = (t) => 1 - (1 - t) ** 3;

/**
 * The placement the viewer shows now, anchored at the image's top-left corner.
 *
 * @returns {{s:number, anchorImg:{x:number,y:number}, anchorPx:{x:number,y:number}}}
 */
export function shownPlacement(plate, rect) {
  const vp = plate.osdViewer.viewport;
  const shown = vp.viewportToImageRectangle(vp.getBounds(true));
  return {
    s: rect.width / shown.width,
    anchorImg: { x: shown.x, y: shown.y },
    anchorPx: { x: 0, y: 0 },
  };
}
