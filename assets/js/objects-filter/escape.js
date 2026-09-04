/**
 * Telar — HTML escaping for the objects gallery filter.
 *
 * The filter builds its facet options and its chips as HTML strings, so any
 * value coming from the collection's own metadata has to be safe both as text
 * and inside a quoted attribute.
 *
 * The document is a parameter with a browser default so a test can escape
 * against its own document.
 *
 * Version: v1.7.0
 */

/** Escape HTML special characters, quotes included. */
export function escapeHtml(text, doc = document) {
  const div = doc.createElement('div');
  div.textContent = text;
  // textContent -> innerHTML escapes < > &, but NOT quotes; add them so the
  // result is also safe inside double- or single-quoted HTML attributes.
  return div.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
