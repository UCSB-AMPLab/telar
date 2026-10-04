/**
 * What every object page entry does before it knows its type.
 *
 * Each media type has its own bundle so a page downloads one viewer rather
 * than three; this is the part they share. Reading the layout's data block,
 * and waiting for the DOM if the script got there first.
 *
 * Version: v1.8.0
 */

/**
 * Read the page's data block. Null when the layout wrote none, which is how
 * a page that is not an object page stays untouched.
 *
 * @param {Document} [doc]
 * @returns {Object|null}
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
 * panel read from `window` rather than receive as arguments.
 *
 * @param {Object} data
 * @param {Window} [win]
 */
export function publishLanguageGlobals(data, win = window) {
  win.telarCoordLang = { copied: data.lang.copied };
  win.telarViewerLang = data.lang.viewer;
}

/**
 * Run `wire` with the page's data once the DOM is there, or not at all.
 *
 * A bundle is loaded by the layout that also wrote the block, so a missing
 * block means this bundle reached a page it is not for and should do nothing.
 *
 * @param {(data: Object) => void} wire
 */
export function onObjectPage(wire) {
  const data = readObjectData();
  if (!data) return;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => wire(data));
  } else {
    wire(data);
  }
}
