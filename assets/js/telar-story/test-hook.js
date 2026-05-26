/**
 * Telar Story – Centering Measurement Test Hook
 *
 * Measurement instrument for the cross-device centering work. It
 * exposes `window.__telarTestHook__` so an automated sweep (Playwright, the
 * Xcode iOS Simulator, or Chrome MCP) can read — in exact pixels — where an
 * authored focal point ACTUALLY renders and what image footprint ("radius") is
 * visible, across screen sizes and orientations.
 *
 * Design principles:
 *   1. Measure REALITY, not the runtime's prediction. Every reading comes from
 *      OpenSeadragon's own coordinate APIs (`imageToViewerElementCoordinates`,
 *      `viewportToImageRectangle`, `getHomeZoom`) applied to the live viewport —
 *      never from `iiif-card.js`'s `screen = osd·zoom·viewport` formula (the very
 *      math under audit). A hook that trusted that formula would be a self-
 *      consistent oracle, exactly the trap this hook exists to avoid.
 *   2. Never ship active to production. The hook is inert unless the page is
 *      loaded with `?telartest=1` (or `window.__TELAR_TEST_HOOK__ === true` is set
 *      before the viewer initialises). With the flag absent, `registerTestViewer`
 *      and `installTestHook` are no-ops and `window.__telarTestHook__` is never
 *      defined.
 *
 * The OSD viewer instance is otherwise unreachable from page JS (it lives in the
 * `IiifViewer` wrapper's closure), so the wrapper registers itself here on init
 * and unregisters on destroy.
 *
 * @version v1.4.0
 */

import { state } from './state.js';

/**
 * Whether the measurement hook is active for this page load.
 * @returns {boolean}
 */
function testEnabled() {
  if (typeof window === 'undefined') return false;
  if (window.__TELAR_TEST_HOOK__ === true) return true;
  try {
    return /[?&]telartest=1(?:&|$)/.test(window.location.search);
  } catch {
    return false;
  }
}

/** Live registry of IiifViewer wrappers (only populated when enabled). */
const registry = [];
let installed = false;

/**
 * Register an IiifViewer wrapper so the hook can measure it. No-op unless the
 * test flag is set. Idempotent per wrapper.
 * @param {object} wrapper - IiifViewer instance (has `.viewer`, `.containerEl`).
 */
export function registerTestViewer(wrapper) {
  if (!testEnabled() || !wrapper) return;
  if (!registry.includes(wrapper)) registry.push(wrapper);
  installTestHook();
}

/**
 * Remove a wrapper from the registry (called from IiifViewer.destroy()).
 * @param {object} wrapper
 */
export function unregisterTestViewer(wrapper) {
  const i = registry.indexOf(wrapper);
  if (i >= 0) registry.splice(i, 1);
}

/** On-screen area (CSS px²) of an element clipped to the viewport. */
function visibleArea(el) {
  const r = el.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const w = Math.max(0, Math.min(vw, r.right) - Math.max(0, r.left));
  const h = Math.max(0, Math.min(vh, r.bottom) - Math.max(0, r.top));
  return w * h;
}

/**
 * The viewer currently showing to the reader.
 *
 * Story pages stack viewer plates: a fresh deep-zoom plate slides OVER the prior
 * one, and both fill the viewport at once. A pure visible-area ranking is
 * occlusion-blind — the `getBoundingClientRect` areas tie and the sort returns
 * whichever registered first, often the hidden plate behind at home zoom. (That
 * tie was the entire "step-19 collapse" the sweep reported.) Selection here, in
 * order:
 *   1. Prefer plates marked `.is-active` (card-pool's own "visible plate"
 *      signal). Stale `is-active` can linger on more than one stacked plate, so
 *      this only narrows the field; it does not decide on its own.
 *   2. Among those, the highest stacking `z-index` is the one actually painted
 *      on top — the decisive, occlusion-aware tiebreaker.
 *   3. Visible area breaks any remaining tie.
 * All three signals come from the navigation/stacking layer, not from the
 * centering math under audit, so the oracle stays independent. Object pages have
 * no `.viewer-plate` (no is-active, z -Infinity) and fall through to their lone
 * viewer.
 * @returns {object|null}
 */
function getActiveViewer() {
  const live = registry.filter(
    (w) => w && w.viewer && !w._destroyed && w.containerEl && document.contains(w.containerEl)
  );
  if (live.length === 0) return null;
  const plateOf = (w) => w.containerEl.closest('.viewer-plate');
  const zOf = (w) => {
    const p = plateOf(w);
    const z = p ? parseInt(getComputedStyle(p).zIndex, 10) : NaN;
    return Number.isNaN(z) ? -Infinity : z;
  };
  const isActive = (w) => !!plateOf(w)?.classList.contains('is-active');
  const pool = live.some(isActive) ? live.filter(isActive) : live;
  pool.sort((a, b) =>
    (zOf(b) - zOf(a)) ||
    (visibleArea(b.containerEl) - visibleArea(a.containerEl))
  );
  return pool[0];
}

/**
 * Whether the active viewer has finished animating — OSD's current zoom/centre
 * have reached their target (no in-flight pan/zoom). Used by the sweep to wait
 * for a step transition to fully settle before measuring, so mid-animation
 * frames are never recorded.
 * @returns {boolean}
 */
function isSettled() {
  const w = getActiveViewer();
  if (!w || !w.viewer) return false;
  const vp = w.viewer.viewport;
  const zc = vp.getZoom(true), zt = vp.getZoom(false);
  const cc = vp.getCenter(true), ct = vp.getCenter(false);
  return Math.abs(zc - zt) < 1e-4
    && Math.abs(cc.x - ct.x) < 1e-4
    && Math.abs(cc.y - ct.y) < 1e-4;
}

/**
 * Measure where the authored focal point `(nx, ny)` (image-normalised, 0–1)
 * actually renders, plus every variable needed to compare against intent.
 *
 * All positions are CSS px in viewport (screen) coordinates unless noted.
 * `visibleImageRect` is in image pixels — the footprint / "radius".
 *
 * @param {number} nx - Authored focal x in [0, 1].
 * @param {number} ny - Authored focal y in [0, 1].
 * @returns {object} measurement record, or `{ error }` if no viewer is ready.
 */
function measure(nx, ny) {
  const w = getActiveViewer();
  if (!w) return { error: 'no-active-viewer' };
  const v = w.viewer;
  const OSD = window.OpenSeadragon;
  if (!OSD || !v.world || v.world.getItemCount() === 0) return { error: 'world-empty' };

  const item = v.world.getItemAt(0);
  const cs = item.getContentSize(); // image px
  const vp = v.viewport;
  const rect = w.containerEl.getBoundingClientRect();

  // Actual rendered focal point → screen px (OSD ground truth).
  const elPt = vp.imageToViewerElementCoordinates(new OSD.Point(nx * cs.x, ny * cs.y));
  const focalScreenPx = { x: rect.left + elPt.x, y: rect.top + elPt.y };

  // Visible image footprint (the "radius"), in image px.
  const visImg = vp.viewportToImageRectangle(vp.getBounds(true));

  const homeZoom = vp.getHomeZoom();
  const zoom = vp.getZoom(true);
  const cor = state.cardOverlayRect;

  return {
    ok: true,
    input: { nx, ny },
    viewport: { w: window.innerWidth, h: window.innerHeight, dpr: window.devicePixelRatio || 1 },
    imageSize: { w: cs.x, h: cs.y, aspect: cs.x / cs.y },
    homeZoom,
    zoom,
    effectiveNzoom: zoom / homeZoom, // what the runtime actually rendered, vs authored
    osdConfig: {
      visibilityRatio: v.visibilityRatio,
      constrainDuringPan: v.constrainDuringPan,
      minZoomImageRatio: v.minZoomImageRatio,
      homeFillsViewer: v.homeFillsViewer,
    },
    viewerRect: { x: rect.left, y: rect.top, w: rect.width, h: rect.height },
    focalScreenPx,
    focalInViewerPx: { x: elPt.x, y: elPt.y },
    visibleImageRect: { x: visImg.x, y: visImg.y, w: visImg.width, h: visImg.height },
    cardOverlayRect: cor ? { x: cor.x, y: cor.y, w: cor.width, h: cor.height } : null,
    layoutMode: state.layoutMode ?? null,
    activeTitleCardIndex: state.activeTitleCardIndex ?? null,
  };
}

/** The atlas-allegory IIIF focal steps of the "Your Story" demo (CSV order). */
const DEFAULT_SWEEP_STEPS = [
  { step: 1, x: 0.5, y: 0.5, zoom: 1 },
  { step: 2, x: 0.477, y: 0.125, zoom: 8.9 },
  { step: 3, x: 0.486, y: 0.277, zoom: 10 },
  { step: 4, x: 0.504, y: 0.415, zoom: 2.9 },
  { step: 5, x: 0.478, y: 0.883, zoom: 10 },
  { step: 6, x: 0.5, y: 0.5, zoom: 1 },
  { step: 19, x: 0.516, y: 0.974, zoom: 10 },
  { step: 20, x: 0.5, y: 0.5, zoom: 1 },
];

/** Wait for the active viewer to settle on a step, then return a measurement. */
async function settleAndMeasure(nx, ny, timeoutMs = 9000) {
  const start = Date.now();
  let streak = 0, lastKey = null;
  while (Date.now() - start < timeoutMs) {
    const st = state;
    if (isSettled() && !(st && st.isSnapping)) {
      const m = measure(nx, ny);
      if (m && m.ok) {
        const key = `${Math.round(m.focalScreenPx.x)},${Math.round(m.focalScreenPx.y)},${m.zoom.toFixed(3)}`;
        if (key === lastKey) streak++; else { lastKey = key; streak = 0; }
        if (streak >= 3) return m;
      }
    } else {
      streak = 0;
    }
    await new Promise((r) => setTimeout(r, 150));
  }
  return measure(nx, ny); // best effort
}

/**
 * Navigate each focal step, settle, and measure. Used by the collector so a
 * device (iOS Simulator Mobile Safari) can self-report measurements.
 */
async function runSweep(steps) {
  const nav = window.TelarStory && window.TelarStory.navigateToStep;
  const out = [];
  for (const s of steps) {
    if (nav) nav(s.step);
    await new Promise((r) => setTimeout(r, 450));
    const m = await settleAndMeasure(s.x, s.y);
    out.push({ step: s.step, authored: s, m });
  }
  return out;
}

/**
 * If the page was loaded with `&collect[=<url>]`, auto-run the sweep once the
 * viewer is ready and POST the results via sendBeacon (a "simple" cross-origin
 * request — no CORS preflight) to the collector. This is how the iOS Simulator
 * reports back: `xcrun simctl openurl <udid> "<story>?telartest=1&collect&label=..."`.
 */
function maybeAutoCollect() {
  let params;
  try { params = new URLSearchParams(window.location.search); } catch { return; }
  if (!params.has('collect')) return;
  const url = params.get('collect') || 'http://127.0.0.1:8899/collect';
  const label = params.get('label') || 'device';
  const steps = window.__TELAR_SWEEP_STEPS__ || DEFAULT_SWEEP_STEPS;
  runSweep(steps).then((results) => {
    const payload = {
      label,
      ua: navigator.userAgent,
      viewport: { w: window.innerWidth, h: window.innerHeight, dpr: window.devicePixelRatio || 1 },
      results,
    };
    try {
      navigator.sendBeacon(url, new Blob([JSON.stringify(payload)], { type: 'text/plain' }));
    } catch (e) {
      // Fallback: fire-and-forget fetch (may be CORS-opaque, that's fine).
      fetch(url, { method: 'POST', mode: 'no-cors', body: JSON.stringify(payload) }).catch(() => {});
    }
  });
}

/**
 * Install `window.__telarTestHook__` once. No-op unless the test flag is set.
 */
export function installTestHook() {
  if (installed || !testEnabled()) return;
  installed = true;
  window.__telarTestHook__ = {
    version: 'v1.4.0',
    registry,
    getActiveViewer,
    isSettled,
    /** Primary API: exact rendered position + footprint of a focal point. */
    getFocalScreenPosition: measure,
    measure,
    /** Convenience: measure a list of `{nx, ny}` (or `{x, y}`) points in one call. */
    measurePoints(points) {
      return points.map((p) => measure(Number(p.nx ?? p.x), Number(p.ny ?? p.y)));
    },
    runSweep,
    settleAndMeasure,
  };
  // Kick off auto-collection if requested (after a beat so the first viewer
  // has registered and the story has bootstrapped).
  setTimeout(maybeAutoCollect, 800);
}
