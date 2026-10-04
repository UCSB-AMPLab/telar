/**
 * Telar Story — the authoring frame.
 *
 * A story step records where the author left the viewer: a focal point and a
 * zoom. Both are read off one screen and replayed on another, so the zoom
 * cannot mean "a multiple of the home fit on whatever pane happened to be
 * open". It means a multiple of the home fit in a viewport of one canonical
 * aspect, and that is what this module holds: the aspect, and the home zoom
 * it implies for a given image.
 *
 * Both ends of the round trip use it. `iiif-viewer.js` divides by it when it
 * reads a position out of a live viewer, and `iiif-card.js` multiplies by it
 * when it reconstructs the authored frame. Because both use the same number,
 * it cancels: a value captured at one aspect replays as the same framing at
 * any other, and the constant could be anything without changing a published
 * story. It is 1 because that is the one value an author can hold in mind —
 * zoom 1 is the whole object in a square frame.
 *
 * The home fit has two arms and both are needed. An image taller than the
 * frame fits by height and letterboxes at the sides; an image wider than the
 * frame fits by width and letterboxes above and below. OpenSeadragon's own
 * home zoom is `min(1, imageAspect / frameAspect)` for exactly that reason,
 * and a derivation that keeps only the first arm is correct for portrait
 * images and wrong for every landscape one.
 *
 * @version v1.8.0
 */

/**
 * The aspect ratio of the frame an authored zoom is measured against.
 *
 * Not author-tunable, and not a property of any real screen: it is the unit
 * both ends agree to divide by. See the module note above for why it is 1.
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
