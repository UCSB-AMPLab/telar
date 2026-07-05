/**
 * Telar Story – Text Card
 *
 * This module determines which layout mode (detail vs full-object) a text
 * card should use, based on the step's authored zoom/coordinates. Card
 * construction and activation live in card-pool.js — it inlines its own
 * card construction rather than calling into this module.
 *
 * @version v1.6.0
 */

// Note: No imports from card-pool.js to avoid circular dependency.

// ── Full-object mode detection ────────────────────────────────────────────────

/**
 * Determine whether a step should use full-object (zoomed-out) layout.
 *
 * Returns true when the viewer should show the whole object rather than
 * zooming into a specific region. This triggers the layout reversal from
 * detail mode (text left, viewer right) to full-object mode (text left,
 * image right with text background).
 *
 * Rules:
 *   - x and y both undefined → full-object (no coordinates = full object,
 *     regardless of zoom)
 *   - zoom undefined or empty → full-object
 *   - zoom as number <= 1.0 → full-object
 *   - zoom > 1.0 with valid x/y → detail mode
 *
 * @param {Object} stepData - Step data object from window.storyData.steps
 * @param {string|number|undefined} [stepData.zoom]
 * @param {string|number|undefined} [stepData.x]
 * @param {string|number|undefined} [stepData.y]
 * @returns {boolean}
 */
export function isFullObjectMode(stepData) {
  const zoom = stepData.zoom;

  // No coordinates at all → full object, regardless of zoom
  if (stepData.x === undefined && stepData.y === undefined) {
    return true;
  }

  // Zoom absent or blank
  if (zoom === undefined || zoom === '' || zoom === null) return true;

  // Numeric zoom <= 1.0
  const zoomNum = parseFloat(zoom);
  if (isNaN(zoomNum) || zoomNum <= 1.0) return true;

  return false;
}
