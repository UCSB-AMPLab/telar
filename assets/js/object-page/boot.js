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
 * Read the page's data block, which the layout that loads the bundle always
 * writes: a page without it throws. Null when the block is not valid JSON,
 * after logging the error.
 *
 * @param {Document} [doc]
 * @returns {Object|null}
 */
export function readObjectData(doc = document) {
  const text = doc.getElementById('telar-object-data').textContent;
  try {
    return JSON.parse(text);
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
 * Run `wire` with the page's data once the DOM is there, or not at all when
 * the block is unreadable (readObjectData has logged why).
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
