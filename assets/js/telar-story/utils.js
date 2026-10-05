/**
 * Telar Story – Shared Utilities
 *
 * This module contains small helper functions used by more than one other
 * module. Each does one thing: compute the site's base URL path, or fix image
 * URLs inside HTML content. It also re-exports the shared HTML escaping.
 *
 * These helpers exist because the same logic was needed in multiple places —
 * base path extraction in both manifest URL building and panel content
 * formatting.
 *
 * @version v1.8.0
 */

// Escaping has one implementation for every bundle, in objects-filter/escape.js.
// Re-exported here so the story modules import it from their own utilities.
export { escapeHtml } from '../objects-filter/escape.js';

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
 * Panel content arrives as pre-rendered HTML from the build pipeline. The
 * build already resolves a bare file name and a carousel slide against the
 * site's baseurl, so a src that starts with the base path is left alone:
 * prefixing it again would ask for /telar/telar/…. Any other root-absolute
 * src is the author's own path and gets the base path prepended.
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
    const alreadyUnderBase = basePath !== '' && src && src.startsWith(basePath + '/');
    if (src && src.startsWith('/') && !src.startsWith('//') && !alreadyUnderBase) {
      img.setAttribute('src', basePath + src);
    }
  });

  return tempDiv.innerHTML;
}
