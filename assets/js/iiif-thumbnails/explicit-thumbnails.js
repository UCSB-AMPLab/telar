/**
 * Explicit thumbnails: the `<img class="iiif-thumbnail">` a layout writes
 * when an object carries its own thumbnail URL.
 *
 * Both index pages upgrade those to a larger rendition with the original
 * kept as an `onerror` fallback, since a Level 0 server only serves the
 * sizes it pre-generated. The same code served both pages inline; it is
 * shared here.
 *
 * @version v1.7.0
 */

import { upgradeIIIFThumbnailUrl } from './resolve.js';

/** Upgrade explicit IIIF thumbnail URLs to larger sizes (with fallback for Level 0 servers). */
export function upgradeExplicitThumbnails(doc = document) {
  var iiifThumbs = doc.querySelectorAll('img.iiif-thumbnail');
  iiifThumbs.forEach(function(img) {
    var originalSrc = img.src;
    var upgradedSrc = upgradeIIIFThumbnailUrl(originalSrc);
    if (upgradedSrc !== originalSrc) {
      img.dataset.originalSrc = originalSrc;
      img.onerror = function() {
        if (this.dataset.originalSrc) {
          this.src = this.dataset.originalSrc;
          delete this.dataset.originalSrc;
          this.onerror = null;
        }
      };
      img.src = upgradedSrc;
    }
  });
}
