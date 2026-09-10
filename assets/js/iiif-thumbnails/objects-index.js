/**
 * Objects index entry point: gallery card thumbnails.
 *
 * Reads the JSON block the objects-index layout writes,
 * `#telar-objects-index-data` -- the two language strings it needs -- and
 * wires the resolver from resolve.js into the gallery cards: local
 * info.json for self-hosted objects, a remote IIIF manifest otherwise, with
 * an imageless manifest shown as a content gap rather than an error.
 *
 * Bundled by esbuild into assets/js/objects-index-page.js; see
 * assets/js/README.md.
 *
 * Version: v1.7.0
 */

import { resolveManifestThumbnail, resolveInfoJsonThumbnail } from './resolve.js';
import { upgradeExplicitThumbnails } from './explicit-thumbnails.js';

/**
 * Read the page's data block. Null when the layout wrote none, which is
 * how a page that is not the objects index stays untouched.
 */
export function readObjectsIndexData(doc = document) {
  const block = doc.getElementById('telar-objects-index-data');
  if (!block) return null;
  try {
    return JSON.parse(block.textContent);
  } catch (err) {
    console.error('Objects index data block is not valid JSON:', err);
    return null;
  }
}

/** Handle local IIIF thumbnails from info.json. */
export function initLocalThumbnails(data, doc = document) {
  const localItems = doc.querySelectorAll('.local-iiif-thumbnail[data-info-json]');
  localItems.forEach(function(item) {
    const infoUrl = item.getAttribute('data-info-json');

    resolveInfoJsonThumbnail(infoUrl)
      .then(url => {
        if (url) {
          const img = doc.createElement('img');
          img.src = url;
          img.alt = item.closest('.collection-item').querySelector('h3').textContent;

          const placeholder = item.querySelector('.manifest-thumbnail-placeholder');
          if (placeholder) {
            placeholder.replaceWith(img);
          }
        }
      })
      .catch(error => {
        console.error('Error loading IIIF info.json:', infoUrl, error);
        const placeholder = item.querySelector('.manifest-thumbnail-placeholder');
        if (placeholder) {
          placeholder.innerHTML = '<span class="text-danger">' + data.lang.thumbnailLoadError + '</span>';
        }
      });
  });
}

/** Handle external IIIF manifest thumbnails. */
export function initManifestThumbnails(data, doc = document) {
  const items = doc.querySelectorAll('.collection-item-image[data-iiif-manifest]');

  items.forEach(function(item) {
    const manifestUrl = item.getAttribute('data-iiif-manifest');

    // Skip if it's an Image API info.json (handled in template)
    if (manifestUrl.includes('info.json')) {
      return;
    }

    // Resolve manifest to a thumbnail URL and swap it into the card
    resolveManifestThumbnail(manifestUrl, '!400,400')
      .then(url => {
        if (url) {
          const img = doc.createElement('img');
          img.src = url;
          img.alt = item.closest('.collection-item').querySelector('h3').textContent;
          img.className = 'iiif-thumbnail';
          const placeholder = item.querySelector('.manifest-thumbnail-placeholder');
          if (placeholder) placeholder.replaceWith(img);
        }
      })
      .catch(error => {
        const placeholder = item.querySelector('.manifest-thumbnail-placeholder');
        // An imageless manifest is a content gap, not a failure: show the
        // muted "no image" note rather than the error state.
        if (error && error.noImage) {
          console.warn('No image found in manifest:', manifestUrl);
          if (placeholder) {
            placeholder.innerHTML = '<span class="text-muted">' + data.lang.noImage + '</span>';
          }
        } else {
          console.error('Error loading manifest thumbnail:', manifestUrl, error);
          if (placeholder) {
            placeholder.innerHTML = '<span class="text-danger">' + data.lang.thumbnailLoadError + '</span>';
          }
        }
      });
  });
}

/** Wire the whole page. */
export function initObjectsIndexPage(data, doc = document) {
  upgradeExplicitThumbnails(doc);
  initLocalThumbnails(data, doc);
  initManifestThumbnails(data, doc);
}

const data = readObjectsIndexData();
if (data) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initObjectsIndexPage(data));
  } else {
    initObjectsIndexPage(data);
  }
}
