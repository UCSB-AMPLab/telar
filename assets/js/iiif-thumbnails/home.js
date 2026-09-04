/**
 * Home page entry point: story-card and featured-object thumbnails.
 *
 * Reads the JSON block the index layout writes, `#telar-home-data` -- the
 * objects array (for manifest lookup by object id) and the one language
 * string it needs -- and wires the resolver from resolve.js into the cards:
 * an explicit thumbnail first, then a remote IIIF manifest, then the local
 * info.json. A story's manifest is also prefetched the first time its card
 * is hovered.
 *
 * Bundled by esbuild into assets/js/home-page.js; see assets/js/README.md.
 *
 * Version: v1.7.0
 */

import { upgradeIIIFThumbnailUrl, resolveManifestThumbnail, resolveInfoJsonThumbnail } from './resolve.js';
import { upgradeExplicitThumbnails } from './explicit-thumbnails.js';

/**
 * Read the page's data block. Null when the layout wrote none, which is
 * how a page that is not the home page stays untouched.
 */
export function readHomeData(doc = document) {
  const block = doc.getElementById('telar-home-data');
  if (!block) return null;
  try {
    return JSON.parse(block.textContent);
  } catch (err) {
    console.error('Home page data block is not valid JSON:', err);
    return null;
  }
}

/** Load story thumbnails from IIIF (remote manifests or local info.json). */
export function initStoryThumbnails(data, doc = document) {
  const objectsData = data.objects;
  const storyThumbnails = doc.querySelectorAll('.story-iiif-thumbnail[data-object-id]');

  storyThumbnails.forEach(function(item) {
    const objectId = item.getAttribute('data-object-id');
    const localInfoUrl = item.getAttribute('data-info-json');

    // Find object in objectsData
    const objectData = objectsData.find(obj => obj.object_id === objectId);

    // First check if object has explicit thumbnail URL (best for level0 IIIF, also works as override)
    if (objectData && objectData.thumbnail && objectData.thumbnail.trim() !== '') {
      const img = doc.createElement('img');
      const originalUrl = objectData.thumbnail;
      const upgradedUrl = upgradeIIIFThumbnailUrl(originalUrl);
      img.src = upgradedUrl;
      // Fall back to original size if upgraded URL fails (level0 servers)
      if (upgradedUrl !== originalUrl) {
        img.onerror = function() {
          this.src = originalUrl;
          this.onerror = null;
        };
      }
      img.alt = item.closest('.story-card').querySelector('h3').textContent;
      img.style.width = '100%';
      img.style.height = '100%';
      img.style.objectFit = 'cover';

      const placeholder = item.querySelector('.manifest-thumbnail-placeholder');
      if (placeholder) {
        placeholder.replaceWith(img);
      }
    }
    // Check if object has remote IIIF manifest (for level2 servers that support dynamic sizing)
    else if (objectData && objectData.iiif_manifest) {
      resolveManifestThumbnail(objectData.iiif_manifest, '!400,400')
        .then(url => {
          if (url) replaceStoryPlaceholder(url);
        })
        .catch(error => {
          console.error('Error loading remote IIIF manifest:', objectData.iiif_manifest, error);
          const placeholder = item.querySelector('.manifest-thumbnail-placeholder');
          if (placeholder) {
            placeholder.innerHTML = '<span class="text-danger">' + data.lang.thumbnailLoadError + '</span>';
          }
        });
    } else {
      // Local IIIF info.json
      resolveInfoJsonThumbnail(localInfoUrl)
        .then(url => {
          if (url) replaceStoryPlaceholder(url);
        })
        .catch(error => {
          console.error('Error loading local IIIF info.json:', localInfoUrl, error);
          const placeholder = item.querySelector('.manifest-thumbnail-placeholder');
          if (placeholder) {
            placeholder.innerHTML = '<span class="text-danger">' + data.lang.thumbnailLoadError + '</span>';
          }
        });
    }

    function replaceStoryPlaceholder(url) {
      const img = doc.createElement('img');
      img.src = url;
      img.alt = item.closest('.story-card').querySelector('h3').textContent;
      img.style.width = '100%';
      img.style.height = '100%';
      img.style.objectFit = 'cover';
      const placeholder = item.querySelector('.manifest-thumbnail-placeholder');
      if (placeholder) placeholder.replaceWith(img);
    }
  });
}

/** Load featured object thumbnails from local IIIF tiles. */
export function initFeaturedThumbnails(data, doc = document) {
  const objectsData = data.objects;
  const featuredThumbnails = doc.querySelectorAll('.featured-iiif-thumbnail[data-object-id]');
  featuredThumbnails.forEach(function(item) {
    const objectId = item.getAttribute('data-object-id');
    const localInfoUrl = item.getAttribute('data-info-json');

    // Find object in objectsData for potential remote manifest
    const objectData = objectsData.find(obj => obj.object_id === objectId);

    // Check for explicit thumbnail first
    if (objectData && objectData.thumbnail && objectData.thumbnail.trim() !== '') {
      const img = doc.createElement('img');
      const originalUrl = objectData.thumbnail;
      const upgradedUrl = upgradeIIIFThumbnailUrl(originalUrl);
      img.src = upgradedUrl;
      // Fall back to original size if upgraded URL fails (level0 servers)
      if (upgradedUrl !== originalUrl) {
        img.onerror = function() {
          this.src = originalUrl;
          this.onerror = null;
        };
      }
      img.alt = item.closest('.collection-item').querySelector('.collection-title').textContent;
      img.style.width = '100%';
      img.style.height = '100%';
      img.style.objectFit = 'cover';
      item.innerHTML = '';
      item.appendChild(img);
    }
    // Check for remote IIIF manifest
    else if (objectData && objectData.iiif_manifest) {
      resolveManifestThumbnail(objectData.iiif_manifest, '!200,200')
        .then(url => {
          if (url) replaceFeaturedImg(url);
        })
        .catch(error => {
          // A manifest with no image is a silent no-op on featured cards;
          // only network/parse failures are logged.
          if (error && error.noImage) return;
          console.error('Error loading featured object manifest:', objectData.iiif_manifest, error);
        });
    }
    // Local IIIF info.json
    else {
      resolveInfoJsonThumbnail(localInfoUrl)
        .then(url => {
          if (url) replaceFeaturedImg(url);
        })
        .catch(error => {
          console.error('Error loading featured object info.json:', localInfoUrl, error);
        });
    }

    function replaceFeaturedImg(url) {
      const img = doc.createElement('img');
      img.src = url;
      img.alt = item.closest('.collection-item').querySelector('.collection-title').textContent;
      img.style.width = '100%';
      img.style.height = '100%';
      img.style.objectFit = 'cover';
      item.innerHTML = '';
      item.appendChild(img);
    }
  });
}

/**
 * Prefetch story manifests on hover. When the user hovers over a story
 * card, prefetch its IIIF manifest to reduce loading time when they enter
 * the story.
 */
export function initManifestPrefetch(data, doc = document) {
  const objectsData = data.objects;
  // Manifests already prefetched — O(1) dedup with no selector built from the
  // (author-controlled) manifest URL, which avoids CSS-selector injection.
  const prefetchedManifests = new Set();
  doc.querySelectorAll('.story-card').forEach(function(card) {
    card.addEventListener('mouseenter', function() {
      // Find all objects used in this story by looking at its data
      const storyUrl = this.getAttribute('href');
      if (!storyUrl) return;

      // Get the story's first object from the thumbnail element
      const thumbnailEl = this.querySelector('.story-iiif-thumbnail[data-object-id]');
      if (!thumbnailEl) return;

      const objectId = thumbnailEl.getAttribute('data-object-id');
      if (!objectId) return;

      // Find object data and prefetch its manifest
      const objectData = objectsData.find(obj => obj.object_id === objectId);
      if (objectData && objectData.iiif_manifest &&
          !prefetchedManifests.has(objectData.iiif_manifest)) {
        prefetchedManifests.add(objectData.iiif_manifest);
        const prefetchLink = doc.createElement('link');
        prefetchLink.rel = 'prefetch';
        prefetchLink.href = objectData.iiif_manifest;
        doc.head.appendChild(prefetchLink);
        console.log(`Prefetching manifest for ${objectId} on hover`);
      }
    }, { once: true }); // Only prefetch once per story card
  });
}

/** Wire the whole page. */
export function initHomePage(data, doc = document) {
  upgradeExplicitThumbnails(doc);
  initStoryThumbnails(data, doc);
  initFeaturedThumbnails(data, doc);
  initManifestPrefetch(data, doc);
}

const data = readHomeData();
if (data) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initHomePage(data));
  } else {
    initHomePage(data);
  }
}
