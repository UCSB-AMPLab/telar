/**
 * Telar — HTML escaping.
 *
 * The one implementation for every bundle that builds HTML as a string: the
 * objects gallery filter (its facet options and chips), the story runtime
 * (cards and panels, through `telar-story/utils.js`) and the share panel (the
 * embed code). Each bundle carries its own copy at build time; this source is
 * the only one.
 *
 * The value is routed through a detached element's textContent, which encodes
 * `<`, `>` and `&`, and the two quote characters are then escaped as well, so
 * the result is safe between tags and inside `"..."` or `'...'` attribute
 * values. `null` and `undefined` become an empty string.
 *
 * The document is a parameter with a browser default, so a module that is
 * handed its document, and a test, can escape against their own.
 *
 * Version: v1.8.0
 */

/**
 * Escape a value for HTML text or a quoted attribute.
 *
 * @param {*} text - The value to escape.
 * @param {Document} [doc=document] - The document to build the element in.
 * @returns {string} The escaped string.
 */
export function escapeHtml(text, doc = document) {
  const div = doc.createElement('div');
  div.textContent = text == null ? '' : String(text);
  return div.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
