/**
 * Telar Story – Shared Utilities
 *
 * This module contains small helper functions used by more than one other
 * module. Each function does one thing: escape text for safe HTML/attribute
 * inclusion, compute the site's base URL path, or fix image URLs inside
 * HTML content.
 *
 * These helpers exist because the same logic was needed in multiple places —
 * base path extraction in both manifest URL building and panel content
 * formatting.
 *
 * @version v1.6.0
 */

/**
 * Escape a value for safe inclusion as HTML text or inside a double-quoted
 * (or single-quoted) HTML attribute.
 *
 * The value is routed through a detached element's textContent, which encodes
 * `<`, `>`, and `&`, and the two quote characters are then escaped as well, so
 * the result is safe both between tags and inside `"..."` / `'...'` attribute
 * values.
 *
 * This is the canonical copy for the bundled story runtime. Two standalone
 * scripts outside this esbuild bundle keep their own copies because they
 * cannot share the import: objects-filter.js has a byte-compatible
 * `escapeHtml`, and share-panel.js has an `escapeAttr` variant of the same
 * body — keep all three in sync.
 *
 * @param {*} text - The value to escape (null/undefined become an empty string).
 * @returns {string} The escaped string.
 */
export function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text == null ? '' : String(text);
  return div.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

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
