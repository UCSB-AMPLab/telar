/**
 * Telar Story — Step Framing
 *
 * What a step's authored x, y, zoom and page cells become before a viewer
 * sees them. Two modules frame a step: the IIIF plate, when it builds or moves
 * its viewer, and `iiif-card.js`, when a resize re-snaps the active one. Both
 * read the cells through this, so a blank or unreadable cell falls back the
 * same way on every path.
 *
 * It imports nothing. `iiif-plate.js` imports `iiif-card.js`, so a helper
 * that `iiif-card.js` needs cannot live in the plate.
 *
 * @version v1.8.0
 */

// A step that leaves x, y or zoom blank shows the whole object, and the whole
// object is a framing like any other: the image centre at zoom 1, which the
// focal target resolves to the whole image fit and centred in the region the
// text card leaves uncovered. Without these the viewer keeps whatever OSD's home
// position gives it — the image centred in the VIEWER, so a side card sits over
// one edge of it.
//
// The Compositor's capture path pins this value and reads it by importing
// `plates/iiif-plate.js`, which re-exports it from here.
export const FULL_OBJECT_FRAMING = { x: 0.5, y: 0.5, zoom: 1 };

/**
 * The framing a step asks its viewer for.
 *
 * A blank x, y or zoom falls back to the whole-object framing; page is
 * 1-indexed in the story data and absent unless the object is a multi-page
 * external manifest.
 *
 * @param {Object} step - Step data
 * @returns {{ x: number, y: number, zoom: number, page: number|undefined }}
 */
export function stepFraming(step) {
  const num = (value, fallback) => {
    const n = parseFloat(value);
    return Number.isFinite(n) ? n : fallback;
  };
  return {
    x:    num(step.x,    FULL_OBJECT_FRAMING.x),
    y:    num(step.y,    FULL_OBJECT_FRAMING.y),
    zoom: num(step.zoom, FULL_OBJECT_FRAMING.zoom),
    page: step.page ? parseInt(step.page, 10) : undefined,
  };
}
