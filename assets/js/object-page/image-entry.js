/**
 * Entry point for an image object page.
 *
 * Bundled by esbuild into assets/js/object-image.js; see assets/js/README.md.
 * An image page loads this and nothing of the video or audio players.
 *
 * Version: v1.8.0
 */

import { onObjectPage, publishLanguageGlobals } from './boot.js';
import { initImageViewer, initCoordinatePanel } from './image-object.js';

onObjectPage((data) => {
  publishLanguageGlobals(data);
  initCoordinatePanel();
  initImageViewer(data);
});
