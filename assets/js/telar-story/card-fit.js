/**
 * Telar Story – Side-card fit
 *
 * The side card on a horizontal layout takes the height its content needs,
 * under a ceiling, and clears the controls at the top of the window. This
 * module holds that geometry at every window height; the portrait bottom
 * card keeps its own, in card-pool.js. A landscape phone's card is placed in the same band, sized
 * by its content and scrolled by the browser.
 *
 * Width. The card is sized from both window dimensions: the larger of 37% of
 * the width and 1544 − 1.6·H px, that line held to 718px, and never more than
 * 52% of the width. The terms are declared in _sass/_responsive.scss, which
 * also generates the vertical layout's short-window clauses from them, and
 * read here from their :root mirror. A shorter window gets a wider card, so its answer
 * keeps the room it needs on fewer lines. The width is published once per
 * pass as `--telar-card-side-width` on the root element, where the stylesheet
 * and every placement beside the card read it (sideCardWidth).
 *
 * Ceiling. The card's top clears the lowest of the top controls, the embed
 * banner included, by one padding, and its bottom stays one padding above the
 * window's edge. Above the side-card threshold T (the height a landscape
 * phone's card is sized under) the ceiling is also held to 80% of the window,
 * but never below its value at T, so that it cannot fall as the window grows
 * through the threshold (sideCardCeiling).
 *
 * Content only. The card is sized by its content and the answer keeps the
 * size the stylesheet gives it; the card never scrolls and its text is never
 * shrunk. Under the ceiling the card shows all of its content; past it the
 * card's max-height clips.
 *
 * Re-measuring. Anything that changes a card's content height (an image
 * loading, KaTeX rendering, a web font arriving) is seen by one
 * ResizeObserver on each card's content wrapper, and a font that finishes
 * loading re-places every card whether or not a height changed. The embed banner's arrival and dismissal move the controls the card
 * clears, and embed.js says so with `telar:embed-banner`.
 *
 * @version v1.8.0
 */

import { measureControlsBottom, TOP_CONTROLS } from './media-arrangement.js';
import { mediaPadding, unroundedMediaPadding } from './video-layout.js';
import { getCardLandscapeMaxHeight } from './layout-mode.js';

/** The controls the side card's top clears: the top controls and the embed banner. */
export const SIDE_CARD_CONTROLS = [...TOP_CONTROLS, '.telar-embed-banner'];

/**
 * How far a content wrapper's reported height may differ from the height
 * recorded after its placement and still be the pass's own write, in px. Exact
 * up to float noise.
 */
export const CONTENT_TOLERANCE_PX = 0.01;

// ── Geometry (pure, unit-tested) ─────────────────────────────────────────────

/**
 * The side card's width terms, from the :root mirror of _sass/_responsive.scss:
 * its share of the window's width at least and at most, and the line in the
 * window's height it follows between them, with that line's largest value.
 * The fallbacks stand where the stylesheet is absent; the unit tests hold
 * them to the stylesheet's values.
 */
export const SIDE_CARD_WIDTH = _readWidthTerms();

function _readWidthTerms() {
  const cs = getComputedStyle(document.documentElement);
  const term = (name, fallback) => {
    const value = parseFloat(cs.getPropertyValue(`--telar-card-side-${name}`));
    return Number.isFinite(value) ? value : fallback;
  };
  return {
    minShare: term('min-share', 0.37),
    maxShare: term('max-share', 0.52),
    base: term('base', 1544),
    slope: term('slope', 1.6),
    maxByHeight: term('max-by-height', 718),
  };
}

/**
 * The side card's width, in px:
 *
 *   min( maxShare·W,  max( minShare·W,  min( maxByHeight,  base − slope·H ) ) )
 *
 * The vertical layout's short-window clauses (_sass/_responsive.scss) take
 * the windows where the line would pass the cap.
 *
 * @param {number} W - Viewport width in px
 * @param {number} H - Viewport height in px
 * @returns {number}
 */
export function sideCardWidth(W, H) {
  const { minShare, maxShare, base, slope, maxByHeight } = SIDE_CARD_WIDTH;
  const byHeight = Math.min(maxByHeight, base - slope * H);
  return Math.round(Math.min(maxShare * W, Math.max(minShare * W, byHeight)));
}

/**
 * Publish the side card's width for this window on the root element, or
 * clear it, so the stylesheet's 37% holds, on a vertical layout, whose side
 * card (a landscape phone's) keeps that share.
 *
 * @param {number} W - Viewport width in px
 * @param {number} H - Viewport height in px
 * @param {boolean} horizontal - The window is a horizontal layout
 */
export function publishSideCardWidth(W, H, horizontal) {
  const root = document.documentElement.style;
  if (horizontal) root.setProperty('--telar-card-side-width', `${sideCardWidth(W, H)}px`);
  else root.removeProperty('--telar-card-side-width');
}

/**
 * The side card's ceiling, in px.
 *
 *   floor( min( H − C − 2·p̃(H) − 1,  max( fraction·H,  T − C − 2·p̃(T) − 1 ) ) )
 *
 * `H − C − 2·p̃(H) − 1` is the room between the band under the controls and
 * one padding above the window's bottom, less a pixel's reserve; p̃ is the
 * padding before rounding, so the bound grows with H at slope 0.95 or 1 and
 * never steps down by a rounding. The second term keeps the ceiling above the
 * threshold at no less than its value at the threshold. For a fixed C and W
 * the result never decreases as H grows.
 *
 * @param {Object} g
 * @param {number} g.H - Viewport height in px
 * @param {number} g.W - Viewport width in px
 * @param {number} g.C - The controls' lowest bottom edge, rounded, in px
 * @param {number} g.T - The side-card height threshold in px
 * @param {number} g.fraction - The side card's share of a tall viewport
 * @param {(W: number, H: number) => number} [g.pad] - The unrounded padding
 * @returns {number}
 */
export function sideCardCeiling({ H, W, C, T, fraction, pad = unroundedMediaPadding }) {
  const room = (h) => h - C - 2 * pad(W, h) - 1;
  return Math.floor(Math.min(room(H), Math.max(fraction * H, room(T))));
}

/**
 * The side card's top, in px: centred with its run's peek, and held between
 * the band under the controls and one padding above the window's bottom.
 * Where the two bounds cross, the band wins, so the question is never under
 * the controls; a card no taller than the ceiling never meets that case.
 *
 * @param {Object} g
 * @param {number} g.H - Viewport height in px
 * @param {number} g.cardH - The card's rendered height in px
 * @param {number} g.runPos - Position within the card's run
 * @param {number} g.peek - Pixels each later card in a run settles lower
 * @param {number} g.band - The controls' bottom plus one padding, in px
 * @param {number} g.pad - The padding, rounded, in px
 * @returns {number}
 */
export function sideCardTop({ H, cardH, runPos, peek, band, pad }) {
  const centred = (H - cardH) / 2 + runPos * peek;
  return Math.max(band, Math.min(centred, H - pad - cardH));
}

// ── Placing a card ───────────────────────────────────────────────────────────

/**
 * Cap a card at the ceiling and let its content set the height under it.
 *
 * @param {HTMLElement} card
 * @param {number} ceilingPx
 */
function _capCard(card, ceilingPx) {
  card.style.height = '';
  card.style.maxHeight = `${ceilingPx}px`;
}

/**
 * The cards a pass places first: the active one and two either side, which a
 * reader can reach before the rest could be placed.
 *
 * @param {Iterable<HTMLElement>} cards
 * @param {number} activeIndex
 * @returns {HTMLElement[]}
 */
export function fitOrder(cards, activeIndex) {
  const near = [];
  const rest = [];
  for (const card of cards) {
    const i = parseInt(card.dataset.stepIndex, 10);
    (Math.abs(i - activeIndex) <= 2 ? near : rest).push(card);
  }
  return near.concat(rest);
}

/**
 * Cap and place the side cards for one geometry pass.
 *
 * @param {Iterable<HTMLElement>} cards - The cards to place: every card, or the
 *   ones whose content changed
 * @param {Object} how
 * @param {number} how.W - Viewport width in px
 * @param {number} how.H - Viewport height in px
 * @param {number} how.peek - Pixels each later card in a run settles lower
 * @param {number} how.fraction - The side card's share of a tall viewport
 * @param {number} how.activeIndex - The current step
 * @returns {{ band: number, pad: number, ceiling: number,
 *   topOf: (card: HTMLElement) => number }} The pass's geometry, and a card's
 *   top under it, which a media scene's card beside its player keeps
 */
export function fitSideCards(cards, { W, H, peek, fraction, activeIndex }) {
  const { band, pad, ceiling } = sideCardBand({ W, H, fraction });

  const topOf = (card) => sideCardTop({
    H, cardH: card.offsetHeight, runPos: parseInt(card.dataset.runPosition, 10) || 0,
    peek, band, pad,
  });
  for (const card of fitOrder(cards, activeIndex)) {
    _capCard(card, ceiling);
    recordContentHeight(card);
    card.style.setProperty('top', `${topOf(card)}px`, 'important');
  }
  return { band, pad, ceiling, topOf };
}

/**
 * The band under the top controls and the ceiling above it, for one window.
 * The side card and a landscape phone's card, which is sized by its content
 * and scrolled by the browser, are placed by the same band.
 *
 * @param {Object} g
 * @param {number} g.W - Viewport width in px
 * @param {number} g.H - Viewport height in px
 * @param {number} g.fraction - The side card's share of a tall viewport
 * @returns {{ C: number, pad: number, band: number, ceiling: number }}
 */
export function sideCardBand({ W, H, fraction }) {
  const C = Math.round(measureControlsBottom(SIDE_CARD_CONTROLS));
  const pad = mediaPadding(W, H);
  const ceiling = sideCardCeiling({ H, W, C, T: getCardLandscapeMaxHeight(), fraction });
  return { C, pad, band: C + pad, ceiling };
}

/**
 * Run one geometry pass between the marks the timing check reads.
 *
 * @param {() => void} pass
 */
export function timeGeometryPass(pass) {
  const perf = typeof performance !== 'undefined' ? performance : null;
  perf?.mark?.('telar-card-geometry-start');
  pass();
  if (!perf?.mark || !perf.measure) return;
  perf.mark('telar-card-geometry-end');
  try {
    perf.measure('telar-card-geometry', 'telar-card-geometry-start', 'telar-card-geometry-end');
  } catch {
    // A page whose performance timeline refuses the measure still gets its pass.
  }
}

// ── Watching card content ────────────────────────────────────────────────────

const _recordedHeights = new WeakMap();

/**
 * The card's content wrapper: the cloned `.step-content`, the card's only
 * child. It is a flex item and not a scroll container, so its height is its
 * content's and the card's max-height does not shrink it.
 */
function _contentWrapper(card) {
  return card.children.length === 1 ? card.firstElementChild : null;
}

/** An element's content-box height, as a ResizeObserver reports it. */
function _contentHeight(el) {
  const cs = getComputedStyle(el);
  let h = parseFloat(cs.height);
  if (cs.boxSizing === 'border-box') {
    for (const side of ['paddingTop', 'paddingBottom', 'borderTopWidth', 'borderBottomWidth']) {
      h -= parseFloat(cs[side]) || 0;
    }
  }
  return h;
}

/**
 * Record a card's content height after its placement, so the observer can tell
 * the pass's own write from a change of content.
 *
 * @param {HTMLElement} card
 */
export function recordContentHeight(card) {
  const wrapper = _contentWrapper(card);
  if (wrapper) _recordedHeights.set(wrapper, _contentHeight(wrapper));
}

/**
 * Re-place the cards whose content changes, at most once per animation frame.
 *
 * An entry at the height recorded after the card's last placement, within
 * CONTENT_TOLERANCE_PX, is the pass's own write, or the entry every element
 * gets when first observed, and starts nothing. Any other schedules a pass for
 * the changed cards. A font that finishes loading schedules a pass for all of
 * them; so does the embed banner's arrival or dismissal.
 *
 * jsdom has no ResizeObserver, and a browser without one keeps the other two
 * triggers.
 *
 * @param {Iterable<HTMLElement>} cards
 * @param {(changed: HTMLElement[]|null) => void} refit - Called with the
 *   changed cards, or null for every card
 * @param {{ raf?: (cb: FrameRequestCallback) => number }} [opts]
 * @returns {() => void} Teardown: disconnects the observer, removes both
 *   listeners, and drops a pass already scheduled
 */
export function watchCardContent(cards, refit, { raf = (cb) => requestAnimationFrame(cb) } = {}) {
  const list = [...cards];
  const pending = new Set();
  let all = false;
  let frame = 0;
  let stopped = false;

  const schedule = () => {
    if (frame || stopped) return;
    frame = raf(() => {
      frame = 0;
      if (stopped) return;
      const changed = all ? null : [...pending];
      all = false;
      pending.clear();
      refit(changed);
    });
  };

  const RO = typeof window !== 'undefined' ? window.ResizeObserver : undefined;
  let observer = null;
  if (typeof RO === 'function') {
    observer = new RO((entries) => {
      for (const entry of entries) {
        const recorded = _recordedHeights.get(entry.target);
        if (recorded === undefined) continue;
        if (Math.abs(entry.contentRect.height - recorded) <= CONTENT_TOLERANCE_PX) continue;
        const card = entry.target.parentElement;
        pending.add(card);
      }
      if (pending.size) schedule();
    });
    for (const card of list) {
      const wrapper = _contentWrapper(card);
      if (wrapper) observer.observe(wrapper);
    }
  }

  // A load is re-placed once, by whichever of `loadingdone` and `fonts.ready`
  // comes first: WebKit settles `ready` but never fires `loadingdone`, and
  // the other browsers fire both for the same load.
  let loadOpen = false;
  const onFonts = () => {
    loadOpen = false;
    all = true;
    schedule();
  };
  const onFontsLoading = () => {
    loadOpen = true;
    Promise.resolve(fonts?.ready).then(() => { if (loadOpen) onFonts(); });
  };
  const onBanner = () => {
    all = true;
    schedule();
  };
  const fonts = document.fonts;
  fonts?.addEventListener?.('loading', onFontsLoading);
  fonts?.addEventListener?.('loadingdone', onFonts);
  window.addEventListener('telar:embed-banner', onBanner);

  return () => {
    stopped = true;
    observer?.disconnect();
    fonts?.removeEventListener?.('loading', onFontsLoading);
    fonts?.removeEventListener?.('loadingdone', onFonts);
    window.removeEventListener('telar:embed-banner', onBanner);
  };
}
