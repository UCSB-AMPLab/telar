/**
 * The image object page: the IIIF viewer, the coordinate readout that
 * follows it, and the coordinate panel's copy buttons.
 *
 * The viewer wrapper is the story engine's own module, imported here and
 * bundled so the page loads one script. OpenSeadragon is a vendored classic
 * script the layout loads first; the wrapper reads it from `window`.
 *
 * Version: v1.7.0
 */

import { IiifViewer, normalizedViewportPosition } from '../telar-story/iiif-viewer.js';
import { copyWithFeedback, CHECK_ICON } from './copy-feedback.js';

/** The manifest URL the page views: the external source, else the site's own. */
export function manifestUrlFor(data) {
  if (data.externalSource) return data.externalSource;
  if (data.objectId) return data.baseUrl + '/iiif/objects/' + data.objectId + '/manifest.json';
  return null;
}

export async function initImageViewer(data, doc = document) {
  // Coordinate panel theme colouring — object-theme.js picks coord-light /
  // coord-dark from the theme button background's luminance
  window.telarObjectTheme.applyPanelContrastClass(doc.querySelector('.coordinate-panel'));

  const manifestUrl = manifestUrlFor(data);
  if (!manifestUrl) {
    console.error('No IIIF source specified');
    return;
  }

  // Initialise the IIIF wrapper. showChrome:true gives multi-page
  // manifests the prev / page-input / next pills the reader needs;
  // single-page manifests render no chrome regardless.
  // allowZoomGestures:true restores OSD's native scroll-to-zoom and
  // click-to-zoom on this standalone page (story plates leave them
  // disabled because Lenis owns the wheel there; the object viewer
  // has no Lenis to fight).
  const wrapper = new IiifViewer({
    container: '#object-viewer',
    manifestUrl: manifestUrl,
    showChrome: true,
    allowZoomGestures: true,
  });

  // Wait for the wrapper to initialise (manifest fetch + parse + OSD spin-up).
  try {
    await wrapper.ready;
  } catch (err) {
    console.error('IiifViewer failed to initialise:', err);
    return;
  }

  // Multi-page detection reads the wrapper's parsed page list, which
  // spares a second manifest fetch.
  const isMultiPage = wrapper.pages.length > 1;
  if (isMultiPage) {
    doc.getElementById('object-viewer').classList.add('multipage');
    const pageRows = doc.querySelectorAll('.coord-page-row');
    pageRows.forEach(function(el) {
      el.style.display = 'flex';
    });
    var singleInstr = doc.querySelector('.coord-instructions-single');
    var multiInstr = doc.querySelector('.coord-instructions-multi');
    if (singleInstr) singleInstr.style.display = 'none';
    if (multiInstr) multiInstr.style.display = 'block';
  }

  // Access the OSD instance directly via the wrapper's public API.
  const osdViewer = wrapper.viewer;

  // If no items loaded yet, set up viewport for when image loads
  if (osdViewer.world.getItemCount() === 0) {
    osdViewer.addHandler('open', function() {
      setTimeout(function() {
        osdViewer.viewport.goHome(true);
      }, 100);
    });
  } else {
    osdViewer.viewport.goHome(true);
  }

  // Listen for 'add-item' event to reset after tiles load
  osdViewer.world.addHandler('add-item', function() {
    setTimeout(function() {
      osdViewer.viewport.goHome(true);
    }, 50);
  });

  // Listen for 'open-failed' to catch any errors
  osdViewer.addHandler('open-failed', function(event) {
    console.error('OpenSeadragon open failed:', event);
  });

  // Coordinate tracking
  function updateCoordinates() {
    if (!osdViewer || !osdViewer.viewport) return;

    try {
      const pos = normalizedViewportPosition(osdViewer.viewport);

      // Update display
      doc.getElementById('coord-x').textContent = pos.x.toFixed(3);
      doc.getElementById('coord-y').textContent = pos.y.toFixed(3);
      doc.getElementById('coord-zoom').textContent = pos.zoom.toFixed(1);

      // Update page number for multi-page objects
      if (isMultiPage) {
        const page = wrapper.currentPage + 1;
        doc.getElementById('coord-page').textContent = page;
      }
    } catch (error) {
      console.error('Error updating coordinates:', error);
    }
  }

  // Add viewport change handlers
  osdViewer.addHandler('animation', updateCoordinates);
  osdViewer.addHandler('animation-finish', updateCoordinates);
  osdViewer.addHandler('zoom', updateCoordinates);
  osdViewer.addHandler('pan', updateCoordinates);

  // Update periodically
  setInterval(updateCoordinates, 500);

  // Initial update
  updateCoordinates();
}

export function initCoordinatePanel(doc = document) {
  // Hide/show button when panel opens/closes
  const coordinatePanel = doc.getElementById('coordinatePanel');
  const coordinateButton = doc.getElementById('coordinateButton');

  if (coordinatePanel && coordinateButton) {
    coordinatePanel.addEventListener('show.bs.collapse', function() {
      coordinateButton.style.display = 'none';
    });

    coordinatePanel.addEventListener('hide.bs.collapse', function() {
      coordinateButton.style.display = 'block';
    });
  }

  // Two idioms coexist here: the csv/sheets buttons show a checkmark plus
  // window.telarCoordLang.copied text; the manifest/x/y/zoom/page buttons
  // show the checkmark alone (no text). Each helper returns the clipboard
  // promise so callers that need to chain a .catch (manifest) still can.
  function copyCoordText(text, btnId) {
    return copyWithFeedback(text, btnId, CHECK_ICON + ' ' + window.telarCoordLang.copied, doc);
  }

  function copyCoordIconOnly(text, btnId) {
    return copyWithFeedback(text, btnId, CHECK_ICON, doc);
  }

  // The page joins the coordinates only for a multi-page object, which the
  // viewer marks on its container once the manifest is parsed. The page row
  // is hidden by a stylesheet class, so reading its inline style, as the
  // layout once did, said "shown" for every object and copied a page
  // number single-page objects do not have.
  function coordinateText(separator) {
    const x = doc.getElementById('coord-x').textContent;
    const y = doc.getElementById('coord-y').textContent;
    const zoom = doc.getElementById('coord-zoom').textContent;
    const viewer = doc.getElementById('object-viewer');
    const isMulti = viewer && viewer.classList.contains('multipage');
    const parts = [x, y, zoom];
    if (isMulti) parts.push(doc.getElementById('coord-page').textContent);
    return parts.join(separator);
  }

  // CSV format copy button (comma-separated)
  doc.getElementById('copy-coords-csv').addEventListener('click', function() {
    copyCoordText(coordinateText(','), 'copy-coords-csv');
  });

  // Sheets format copy button (tab-separated)
  doc.getElementById('copy-coords-sheets').addEventListener('click', function() {
    copyCoordText(coordinateText('\t'), 'copy-coords-sheets');
  });

  // Copy manifest URL button
  const copyManifestBtn = doc.getElementById('copy-manifest');
  if (copyManifestBtn) {
    copyManifestBtn.addEventListener('click', function() {
      const manifestUrl = this.getAttribute('data-manifest');

      copyCoordIconOnly(manifestUrl, 'copy-manifest').catch(function(err) {
        console.error('Failed to copy manifest URL:', err);
      });
    });
  }

  // Individual coordinate copy buttons
  const singles = [['copy-x', 'coord-x'], ['copy-y', 'coord-y'],
                   ['copy-zoom', 'coord-zoom'], ['copy-page', 'coord-page']];
  singles.forEach(function(pair) {
    const btn = doc.getElementById(pair[0]);
    if (btn) {
      btn.addEventListener('click', function() {
        copyCoordIconOnly(doc.getElementById(pair[1]).textContent, pair[0]);
      });
    }
  });
}
