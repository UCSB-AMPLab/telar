/**
 * Telar Story — the authoring frame.
 *
 * A story step records where the author left the viewer: a focal point and a
 * zoom. Both are read off one screen and replayed on another, so they cannot
 * be measured against whatever pane happened to be open. x and y are
 * fractions of the image. zoom is a multiple of the whole-object fit in a
 * frame of one canonical aspect, and that is what this module holds: the
 * aspect, and the home zoom it implies for a given image.
 *
 * Replay reconstructs the authored frame from it (`iiif-card.js`,
 * `computeFocalTarget`). A step's zoom means two things there: at or below 1
 * a fraction of the whole-object fit, and from 2 up the width of the framed
 * detail. The two agree for every image only when the zoom was captured in a
 * pane of this aspect, where the pane's own home zoom is `authoringHomeZoom`.
 * That is why a capture surface has to measure in a pane of this shape: the
 * object page's viewer takes it (`_viewer.scss`), and a surface whose pane
 * has another shape measures against a frame of this shape drawn inside it.
 *
 * The value is fixed: every zoom already published replays through it, so
 * changing it would move every square and portrait step on every site.
 *
 * The home fit has two arms and both are needed. An image taller than the
 * frame fits by height and letterboxes at the sides; an image wider than the
 * frame fits by width and letterboxes above and below. OpenSeadragon's own
 * home zoom is `min(1, imageAspect / frameAspect)` for exactly that reason.
 *
 * @version v1.8.0
 */

/**
 * The aspect ratio of the frame an authored zoom is measured against.
 *
 * Not author-tunable. It is the shape a capture pane must have for its zoom
 * to mean what replay reads; see the module note above for why it is fixed.
 */
export const AUTHORING_ASPECT = 1.053;

/**
 * The home zoom an image of this aspect would have in the authoring frame.
 *
 * `min` is the fit: an image wider than the frame fills it edge to edge and
 * its home zoom is 1, while a taller one fits by height and comes in below 1.
 *
 * @param {number} imageAspect - Image width divided by image height.
 * @returns {number} Home zoom in OpenSeadragon's units, 0 < z <= 1.
 */
export function authoringHomeZoom(imageAspect) {
  return Math.min(1, imageAspect / AUTHORING_ASPECT);
}
