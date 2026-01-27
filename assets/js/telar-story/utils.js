/**
 * Telar Story – Shared Utilities
 *
 * This module contains small helper functions used by more than one other
 * module. Each function does one thing: compute the site's base URL path,
 * fix image URLs inside HTML content, or convert normalised coordinates
 * into the values OpenSeadragon expects for viewport positioning.
 *
 * These helpers exist because the same logic was needed in multiple places —
 * base path extraction in both manifest URL building and panel content
 * formatting, viewport coordinate calculation in both animated and instant
 * positioning. Extracting them avoids the duplication.
 *
 * @version v0.7.0-beta
 */

/**
 * Get the site's base URL path from the current page URL.
 *
 * For a page at /telar/stories/story-1/, this returns /telar.
 * For a page at /stories/story-1/, this returns an empty string.
 *
 * The logic strips the last two path segments (the collection name and
 * the page slug), leaving only the Jekyll baseurl prefix.
 *
 * @returns {string} The base URL path, or empty string if at root.
 */
export function getBasePath() {
  const pathParts = window.location.pathname.split('/').filter(p => p);
  if (pathParts.length >= 2) {
    return '/' + pathParts.slice(0, -2).join('/');
  }
  return '';
}

/**
 * Fix image URLs in HTML content by prepending the base path.
 *
 * Panel content arrives as pre-rendered HTML from the build pipeline.
 * Image src attributes use site-relative paths (starting with /)
 * that need the Jekyll baseurl prepended to resolve correctly.
 *
 * @param {string} htmlContent - HTML string that may contain img tags.
 * @param {string} basePath - The base URL path to prepend.
 * @returns {string} The HTML with corrected image URLs.
 */
export function fixImageUrls(htmlContent, basePath) {
  const tempDiv = document.createElement('div');
  tempDiv.innerHTML = htmlContent;

  const images = tempDiv.querySelectorAll('img');
  images.forEach(img => {
    const src = img.getAttribute('src');
    if (src && src.startsWith('/') && !src.startsWith('//')) {
      img.setAttribute('src', basePath + src);
    }
  });

  return tempDiv.innerHTML;
}

/**
 * Convert normalised coordinates (0–1) into OpenSeadragon viewport values.
 *
 * Story steps store viewer positions as normalised x, y, zoom values where
 * x and y are fractions of the image dimensions (0 = top/left, 1 =
 * bottom/right) and zoom is a multiplier relative to the home zoom level.
 *
 * This function translates those into the absolute coordinates and zoom
 * level that OpenSeadragon's viewport.panTo() and viewport.zoomTo() expect.
 *
 * @param {Object} viewport - The OpenSeadragon viewport instance.
 * @param {number} x - Normalised horizontal position (0–1).
 * @param {number} y - Normalised vertical position (0–1).
 * @param {number} zoom - Zoom multiplier relative to home zoom.
 * @returns {{ point: { x: number, y: number }, actualZoom: number }}
 */
export function calculateViewportPosition(viewport, x, y, zoom) {
  const homeZoom = viewport.getHomeZoom();
  const imageBounds = viewport.getHomeBounds();

  const point = {
    x: imageBounds.x + (x * imageBounds.width),
    y: imageBounds.y + (y * imageBounds.height),
  };

  const actualZoom = homeZoom * zoom;

  return { point, actualZoom };
}
