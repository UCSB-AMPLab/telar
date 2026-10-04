/**
 * Test helpers for IIIF plates.
 *
 * Kept apart from test-helpers.js because importing a plate imports the story
 * runtime, and `iiif-card.js` subscribes to layout events when it loads: the
 * page suites that share the other helpers should not carry that.
 *
 * @version v1.8.0
 */

import { IiifPlate } from '../../assets/js/telar-story/plates/iiif-plate.js';

/** The image the fake viewer holds, in image pixels. */
export const FAKE_IMAGE = { width: 1200, height: 900 };
/** The fake viewer's box on screen. */
export const FAKE_CONTAINER = { x: 0, y: 0, width: 1000, height: 800, top: 0, left: 0 };

/**
 * A plate as `_createViewerPlates` builds one: an instance over an element.
 *
 * Given `fitBounds`, it also carries a viewer that is fake from
 * `viewport.fitBounds` outwards, and is ready unless `isReady` says otherwise.
 * `imageToViewportRectangle` is the identity, so the rectangle `fitBounds`
 * receives is still in image pixels. `active` marks the element `is-active`.
 */
export function makePlate(objectId = 'obj-a', sceneIndex = 0,
                          { fitBounds, isReady, active = false } = {}) {
  const element = document.createElement('div');
  element.className = active ? 'viewer-plate is-active' : 'viewer-plate';
  element.dataset.cardType = 'iiif';
  const plate = new IiifPlate(element, objectId, sceneIndex, 0);
  if (fitBounds) {
    plate.isReady = true;
    plate.osdWrapper = {
      containerEl: { getBoundingClientRect: () => ({ ...FAKE_CONTAINER }) },
    };
    plate.osdViewer = {
      world: { getItemAt: () => ({ source: { ...FAKE_IMAGE } }) },
      viewport: { imageToViewportRectangle: (rect) => rect, fitBounds },
    };
  }
  if (isReady !== undefined) plate.isReady = isReady;
  return plate;
}
