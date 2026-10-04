/**
 * Entry point for a video object page.
 *
 * Bundled by esbuild into assets/js/object-video.js; see assets/js/README.md.
 *
 * Google Drive gets the embed and the copy button but no clip picker: its
 * player exposes no time API, so there would be nothing to read a clip from.
 *
 * Version: v1.8.0
 */

import { onObjectPage } from './boot.js';
import { initVideoEmbed, initClipPicker, initCopyEmbedUrl } from './video-object.js';
import { initClipPanelToggle, initClipCopyButtons } from './clip-panel.js';

onObjectPage((data) => {
  initVideoEmbed(data);
  if (!data.sourceUrl.includes('drive.google.com')) {
    initClipPanelToggle();
    initClipPicker(data);
    initClipCopyButtons(data.lang.copied);
  }
  initCopyEmbedUrl();
});
