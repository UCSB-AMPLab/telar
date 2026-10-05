/**
 * Entry point for an audio object page.
 *
 * Bundled by esbuild into assets/js/object-audio.js; see assets/js/README.md.
 * An audio page loads this and nothing of the IIIF viewer.
 *
 * Version: v1.8.0
 */

import { onObjectPage } from './boot.js';
import { initAudioPlayer } from './audio-object.js';
import { initClipPanelToggle, initClipCopyButtons } from './clip-panel.js';

onObjectPage((data) => {
  initAudioPlayer(data);
  initClipPanelToggle();
  initClipCopyButtons(data.lang.copied);
});
