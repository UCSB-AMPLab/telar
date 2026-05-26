/**
 * Telar Story – Layout-Mode Module
 *
 * This module owns the single window resize and orientationchange listener
 * in the telar-story runtime. No other module may attach its own resize
 * listener — all consumers subscribe through the two surfaces this module
 * exports.
 *
 * Two subscription surfaces:
 *   onLayoutChange — fires only when the layout mode flips between
 *     'horizontal' and 'vertical'. Wired to window.matchMedia() keyed by
 *     the CSS custom properties (--telar-vertical-min-width,
 *     --telar-vertical-min-aspect) declared on :root in _sass/_responsive.scss.
 *     Subscribers receive { from, to, viewport: {w, h}, isEmbed }. Because the
 *     browser's matchMedia fires only on a genuine flip, no JS-side comparison
 *     is needed — JS-vs-CSS formula drift is structurally impossible.
 *   onViewportResize — fires on every settled resize, debounced 100 ms to
 *     match the existing audio-card.js and video-card.js idiom. Subscribers
 *     receive { viewport: {w, h} }.
 *
 * Data flow:
 *   window resize (100 ms debounce) → onViewportResize subscribers
 *                                     (audio-card, video-card, scroll-engine)
 *   window matchMedia 'change'      → onLayoutChange subscribers
 *                                     (main, audio-card, video-card, text-card,
 *                                      iiif-card, card-pool)
 *   window orientationchange        → onLayoutChange then onViewportResize
 *                                     immediately (no debounce — discrete event)
 *
 * Dispatch order on a mode-flipping event is onLayoutChange first so that
 * mode-flip handlers settle branching state (e.g. layoutMode) before
 * geometry handlers re-read viewport dimensions.
 *
 * First-call semantics: getLayoutMode() initialises the listener exactly once
 * (via _initOnce()) and returns a synchronous answer. onLayoutChange does NOT
 * broadcast the initial mode — subscribers that need the current value should
 * call getLayoutMode() at subscribe time.
 *
 * @version v1.4.0
 */

import { state } from './state.js';

// ── Module-scoped private state ───────────────────────────────────────────────

const layoutChangeSubs = new Set();
const viewportResizeSubs = new Set();

let _cachedMode = null;       // 'horizontal' | 'vertical' | null until first _initOnce()
let _breakpoints = null;      // { verticalMinWidth: number, verticalMinAspect: number }
let _modeMql = null;          // MediaQueryList for mode-flip surface
let _resizeTimer = null;
const DEBOUNCE_MS = 100;
let _initialized = false;

// ── Private helpers ───────────────────────────────────────────────────────────

/**
 * Read breakpoint CSS custom properties from :root.
 * Uses parseFloat so the aspect-ratio value (0.75) round-trips correctly.
 *
 * @returns {{ verticalMinWidth: number, verticalMinAspect: number }}
 */
function _readBreakpoints() {
  const cs = getComputedStyle(document.documentElement);
  const minW = parseFloat(cs.getPropertyValue('--telar-vertical-min-width').trim()) || 1024;
  const minA = parseFloat(cs.getPropertyValue('--telar-vertical-min-aspect').trim()) || 0.75;
  return { verticalMinWidth: minW, verticalMinAspect: minA };
}

/**
 * Derive the current layout mode from the matchMedia list.
 * The MediaQueryList matches when the viewport satisfies either the
 * max-width or the max-aspect-ratio clause — that is, "vertical" layout.
 *
 * @returns {'horizontal' | 'vertical'}
 */
function _evaluateMode() {
  return _modeMql.matches ? 'vertical' : 'horizontal';
}

/**
 * Dispatch onLayoutChange subscribers when the matchMedia list fires a
 * 'change' event, or when orientationchange forces an immediate re-evaluation.
 * Fires only on a genuine mode flip (prev !== next and prev is initialised).
 */
function _dispatchLayoutChange() {
  const next = _evaluateMode();
  const prev = _cachedMode;
  _cachedMode = next;
  if (prev !== null && prev !== next) {
    const viewport = { w: window.innerWidth, h: window.innerHeight };
    for (const cb of layoutChangeSubs) {
      try { cb({ from: prev, to: next, viewport, isEmbed: state.isEmbed }); }
      catch (e) { console.error('[layout-mode] onLayoutChange handler threw:', e); }
    }
  }
}

/**
 * Dispatch onViewportResize subscribers with the current viewport dimensions.
 */
function _dispatchViewportResize() {
  const viewport = { w: window.innerWidth, h: window.innerHeight };
  for (const cb of viewportResizeSubs) {
    try { cb({ viewport }); }
    catch (e) { console.error('[layout-mode] onViewportResize handler threw:', e); }
  }
}

/**
 * Debounced resize handler — feeds the continuous-geometry surface.
 * Mode flips fire via matchMedia independently; this timer only feeds
 * onViewportResize subscribers.
 */
function _onResize() {
  if (_resizeTimer) clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(_dispatchViewportResize, DEBOUNCE_MS);
}

/**
 * Immediate orientationchange handler — no debounce.
 * Clears any pending resize timer, re-evaluates mode (in case the matchMedia
 * 'change' event lags on some engines), then flushes both subscription
 * surfaces. onLayoutChange fires FIRST so branching state settles before
 * geometry handlers run.
 */
function _onOrientationChange() {
  if (_resizeTimer) clearTimeout(_resizeTimer);
  _dispatchLayoutChange();
  _dispatchViewportResize();
}

/**
 * Initialise the module's listeners exactly once.
 * Reads breakpoints from CSS custom properties, builds the matchMedia query
 * string (both clauses of the @mixin vertical-layout), attaches the
 * matchMedia change listener for mode flips, and attaches the resize and
 * orientationchange listeners for continuous geometry.
 */
function _initOnce() {
  if (_initialized) return;
  _initialized = true;
  _breakpoints = _readBreakpoints();
  const { verticalMinWidth: minW, verticalMinAspect: minA } = _breakpoints;
  // Query string mirrors _sass/_responsive.scss @mixin vertical-layout.
  // Building it from the same CSS vars at runtime makes JS-vs-CSS formula drift
  // structurally impossible.
  _modeMql = window.matchMedia(`(max-width: ${minW}px), (max-aspect-ratio: ${minA})`);
  // Initialise cached mode synchronously from the current matchMedia state.
  _cachedMode = _evaluateMode();
  _modeMql.addEventListener('change', _dispatchLayoutChange);
  window.addEventListener('resize', _onResize, { passive: true });
  window.addEventListener('orientationchange', _onOrientationChange, { passive: true });
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Return the current layout mode, initialising the listener on the first call.
 *
 * @returns {'horizontal' | 'vertical'}
 */
export function getLayoutMode() {
  _initOnce();
  return _cachedMode;
}

/**
 * Subscribe to layout-mode flip events.
 * The callback fires only when the mode genuinely transitions — not on the
 * initial call. To read the current mode at subscribe time, call
 * getLayoutMode() first.
 *
 * @param {(ev: { from: string, to: string, viewport: { w: number, h: number }, isEmbed: boolean }) => void} cb
 * @returns {() => void} Unsubscribe function
 */
export function onLayoutChange(cb) {
  _initOnce();
  layoutChangeSubs.add(cb);
  return () => layoutChangeSubs.delete(cb);
}

/**
 * Subscribe to every debounced viewport resize.
 * Fires on every resize event that has settled for 100 ms. Also fires
 * immediately on orientationchange (no debounce — discrete event).
 *
 * @param {(ev: { viewport: { w: number, h: number } }) => void} cb
 * @returns {() => void} Unsubscribe function
 */
export function onViewportResize(cb) {
  _initOnce();
  viewportResizeSubs.add(cb);
  return () => viewportResizeSubs.delete(cb);
}

/**
 * Return a defensive copy of the cached breakpoint values.
 * Reads from CSS custom properties on first call; cached thereafter.
 *
 * @returns {{ verticalMinWidth: number, verticalMinAspect: number }}
 */
export function getBreakpoints() {
  if (!_breakpoints) _breakpoints = _readBreakpoints();
  return { ..._breakpoints };
}

/**
 * Return whether the current page is loaded in embed mode.
 * Reads state.isEmbed which is set once at boot by main.js from
 * window.telarEmbed.enabled. Does not change at runtime.
 *
 * @returns {boolean}
 */
export function getIsEmbed() {
  return state.isEmbed;
}

/**
 * True when the viewport is short enough that the landscape side-card rule in
 * `_story.scss` (`@media (max-height: …)`) is active — i.e. the text card is a
 * side card even though getLayoutMode() may report 'vertical' (a landscape phone
 * is < 1024px wide). The threshold is read from the
 * `--telar-card-landscape-max-height` custom property so JS and CSS share one
 * source of truth — no hardcoded 480 in JS (same anti-drift pattern as the
 * breakpoint matchMedia above).
 *
 * Consumers: card-pool.js (`_recomputeCardGeometry`) and iiif-card.js
 * (`_deriveCardPlacement` null-rect fallback) — both must agree that a short
 * landscape viewport is side-card, not bottom-card.
 *
 * @returns {boolean}
 */
export function isLandscapeSideCard() {
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue('--telar-card-landscape-max-height');
  const maxH = parseFloat(raw) || 480;
  return window.matchMedia(`(max-height: ${maxH}px)`).matches;
}
