/**
 * Object page entry point.
 *
 * Reads the JSON block the object layout writes, `#telar-object-data`, and
 * dispatches on the media type it names. The three helper scripts the
 * layout loads as classic scripts -- object-theme.js, video-embed.js and
 * wavesurfer-loader.js -- publish the globals the modules here call.
 *
 * Bundled by esbuild into assets/js/object-page.js; see assets/js/README.md.
 *
 * Version: v1.7.0
 */

import { initImageViewer, initCoordinatePanel } from './image-object.js';
import { initVideoEmbed, initClipPicker, initCopyEmbedUrl } from './video-object.js';
import { initAudioPlayer } from './audio-object.js';
import { initClipPanelToggle, initClipCopyButtons } from './clip-panel.js';

/**
 * Read the page's data block. Null when the layout wrote none, which is
 * how a page that is not an object page stays untouched.
 */
export function readObjectData(doc = document) {
  const block = doc.getElementById('telar-object-data');
  if (!block) return null;
  try {
    return JSON.parse(block.textContent);
  } catch (err) {
    console.error('Object page data block is not valid JSON:', err);
    return null;
  }
}

/**
 * Publish the language strings the IIIF viewer wrapper and the coordinate
 * panel read from `window`, exactly as the image page's module block did.
 */
export function publishLanguageGlobals(data, win = window) {
  win.telarCoordLang = { copied: data.lang.copied };
  win.telarViewerLang = data.lang.viewer;
}

/** Wire the page for its media type; the order is the layout's old order. */
export function initObjectPage(data, doc = document) {
  switch (data.mediaType) {
    case 'Image':
      initCoordinatePanel(doc);
      initImageViewer(data, doc);
      break;
    case 'Video':
      initVideoEmbed(data, doc);
      if (!data.sourceUrl.includes('drive.google.com')) {
        initClipPanelToggle(doc);
        initClipPicker(data, doc);
        initClipCopyButtons(data.lang.copied, doc);
      }
      initCopyEmbedUrl(doc);
      break;
    case 'Audio':
      initAudioPlayer(data, doc);
      initClipPanelToggle(doc);
      initClipCopyButtons(data.lang.copied, doc);
      break;
    default:
      break;
  }
}

const data = readObjectData();
if (data) {
  if (data.mediaType === 'Image') publishLanguageGlobals(data);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initObjectPage(data));
  } else {
    initObjectPage(data);
  }
}
