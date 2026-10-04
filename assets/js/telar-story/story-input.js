/**
 * Telar Story – Which scroll is the story's
 *
 * The scroll engine reads two things about an input: whether it is the reader
 * scrolling the story, and whether it landed inside an open panel, where the
 * story's scroll stops and the panel's own begins. Lenis is given the panel
 * rule as its `prevent`, and the input test reads the same rule, so the engine
 * has one account of both.
 *
 * @version v1.8.0
 */

/**
 * Whether this node is inside an open panel, where the scroll is the panel's.
 *
 * Lenis is given this as its `prevent`, and the input test below reads the
 * same rule, so there is one account of where the story's scroll stops.
 *
 * @param {HTMLElement} node
 * @returns {boolean}
 */
export function isInsidePanel(node) {
  return node.closest('.offcanvas') !== null ||
         node.closest('[data-telar-panel]') !== null;
}

/**
 * Whether this input is the reader's scroll of the story, rather than one Lenis
 * passes by (a pinch-zoom, a tap, a gesture across the story's axis, a wheel in
 * an open panel), which `virtual-scroll` also reports. Read as a takeover, one
 * of those stands a running move down mid-travel. Conservative: a takeover
 * missed strands the move for the session, one imagined costs a frame.
 *
 * @param {{deltaX?: number, deltaY?: number, event?: Event}} payload
 * @returns {boolean}
 */
export function isStoryInput({ deltaY, event } = {}) {
  if (!event) return true;
  if (event.ctrlKey) return false;                 // pinch or browser zoom
  if (deltaY === 0) return false;                  // a tap, a click, or across the story's axis
  const path = event.composedPath ? event.composedPath() : [];
  return !path.some((node) => node instanceof HTMLElement && isInsidePanel(node));
}
