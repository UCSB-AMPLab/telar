/**
 * Telar Story – Side-card fit
 *
 * The side card on a horizontal layout takes the height its content needs,
 * under a ceiling, and clears the controls at the top of the window. This
 * module holds that geometry, for the fit model (card-height.js) at every
 * window height; the portrait bottom card and the fixed model keep their own,
 * in card-pool.js. A landscape phone's card is placed in the same band, sized
 * by its content and scrolled by the browser.
 *
 * Ceiling. The card's top clears the lowest of the top controls, the embed
 * banner included, by one padding, and its bottom stays one padding above the
 * window's edge. Above the side-card threshold T (the height a landscape
 * phone's card is sized under) the ceiling is also held to 80% of the window,
 * but never below its value at T, so that it cannot fall as the window grows
 * through the threshold (sideCardCeiling).
 *
 * Fit. Where the answer does not fit under the ceiling its text shrinks, from
 * the size the stylesheet gives it down to a floor of 0.75rem; where it does
 * not fit even at the floor, the card stays at the floor and scrolls inside
 * itself, driven by card-scroll.js. Only the answer shrinks: the question,
 * the panel buttons and the viewer warning keep their size. The mode and the
 * size are written on the card as `data-card-fit` and
 * `--telar-answer-fit-size`, which the stylesheet reads.
 *
 * Re-measuring. Anything that changes a card's content height (an image
 * loading, KaTeX rendering, a web font arriving) is seen by one
 * ResizeObserver on each card's content wrapper, and a font that finishes
 * loading invalidates every card's fit whether or not a height changed, since
 * a swap can change which size is the largest that fits with the height the
 * same. The embed banner's arrival and dismissal move the controls the card
 * clears, and embed.js says so with `telar:embed-banner`.
 *
 * @version v1.8.0
 */

import { measureControlsBottom, TOP_CONTROLS } from './media-arrangement.js';
import { mediaPadding, unroundedMediaPadding } from './video-layout.js';
import { getCardLandscapeMaxHeight } from './layout-mode.js';
import { syncCardScroll } from './card-scroll.js';

/** The controls the side card's top clears: the top controls and the embed banner. */
export const SIDE_CARD_CONTROLS = [...TOP_CONTROLS, '.telar-embed-banner'];

/** The size the answer does not shrink below, in rem, so a reader's default font raises it. */
export const FLOOR_REM = 0.75;

/** How close the search comes to the largest size that fits, in px. */
export const FIT_STEP_PX = 0.1;

/** Half the width of the bracket the search tries first around its estimate, in px. */
const SEED_BRACKET_PX = 0.6;

/**
 * How far a content wrapper's reported height may differ from the height
 * recorded after its fit and still be the fit's own write, in px. Exact up to
 * float noise: a change of 0.4px can still change the size that fits.
 */
export const CONTENT_TOLERANCE_PX = 0.01;

/** The custom property the fitted answer size is written to. */
const FIT_SIZE = '--telar-answer-fit-size';

/** The custom property each answer tier's stylesheet size is declared in. */
const BASE_SIZE = '--telar-answer-base-size';

// ── Geometry (pure, unit-tested) ─────────────────────────────────────────────

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

/**
 * The largest answer size that fits, to within `step`.
 *
 * The search tries a bracket of ±SEED_BRACKET_PX around the estimate first,
 * which on a card near its fit takes about four layouts, and widens to the
 * whole range once where the estimate misses.
 *
 * @param {Object} s
 * @param {number} s.base - The stylesheet's size in px
 * @param {number} s.floor - The smallest size allowed in px
 * @param {number} [s.step] - Precision in px
 * @param {(size: number) => boolean} s.fits - Whether the card fits at a size
 * @param {number} [s.seed] - The estimate to start from
 * @param {boolean} [s.baseFits] - The answer at `base`, where already measured
 * @returns {{ mode: 'natural'|'shrunk'|'scroll', size: number }}
 */
export function searchFitSize({ base, floor, step = FIT_STEP_PX, fits, seed, baseFits }) {
  if (baseFits ?? fits(base)) return { mode: 'natural', size: base };
  const lowest = Math.min(floor, base);
  if (lowest >= base) return { mode: 'scroll', size: base };

  const s0 = Math.min(base, Math.max(lowest, Number.isFinite(seed) ? seed : (lowest + base) / 2));
  let lo = Math.max(lowest, s0 - SEED_BRACKET_PX);
  let hi = Math.min(base, s0 + SEED_BRACKET_PX);

  if (!fits(lo)) {
    if (lo === lowest) return { mode: 'scroll', size: lowest };
    hi = lo;
    lo = lowest;
    if (!fits(lo)) return { mode: 'scroll', size: lowest };
  } else if (hi < base && fits(hi)) {
    lo = hi;
    hi = base;
  }

  while (hi - lo > step) {
    const mid = (lo + hi) / 2;
    if (fits(mid)) lo = mid;
    else hi = mid;
  }
  return { mode: 'shrunk', size: Math.floor(lo * 1000) / 1000 };
}

// ── Fitting a card ───────────────────────────────────────────────────────────

const _fitCache = new WeakMap();
const _revisions = new WeakMap();
const _recordedHeights = new WeakMap();

/** The root font size in px, which rem is measured in. */
function _rootPx() {
  return parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
}

/**
 * The answer's stylesheet size in px, whatever the fit has written: the
 * container-query tier declares it in BASE_SIZE, which the fit never touches,
 * so it can be read without undoing the fit first.
 */
function _baseSize(answer, rootPx) {
  const raw = getComputedStyle(answer).getPropertyValue(BASE_SIZE).trim();
  const m = /^(-?[\d.]+)(rem|px)?$/.exec(raw);
  if (!m) return rootPx;
  const n = parseFloat(m[1]);
  return m[2] === 'rem' ? n * rootPx : n;
}

/** Raise a card's content revision, so its cached fit is measured again. */
export function bumpContentRevision(card) {
  _revisions.set(card, (_revisions.get(card) || 0) + 1);
}

/** Whether the card fits at its current settings. */
function _fits(card) {
  return card.scrollHeight <= card.clientHeight;
}

/**
 * Fit a card's answer under a ceiling, and write the result on the card.
 *
 * Cached by card width, ceiling, the answer's stylesheet size, the floor and
 * the card's content revision: the stylesheet size and the floor change
 * without the width where the answer's tier or the root font size does. A
 * cache hit writes nothing.
 *
 * @param {HTMLElement} card
 * @param {number} ceilingPx
 * @param {WeakMap} [cache]
 * @returns {{ mode: 'natural'|'shrunk'|'scroll', size: number }}
 */
export function fitAnswerText(card, ceilingPx, cache = _fitCache) {
  const answer = card.querySelector('.step-answer');
  const rootPx = _rootPx();
  const floor = FLOOR_REM * rootPx;
  const base = answer ? _baseSize(answer, rootPx) : rootPx;
  const key = [card.offsetWidth, ceilingPx, base, floor, _revisions.get(card) || 0].join('|');
  const hit = cache.get(card);
  if (hit && hit.key === key) return hit;

  // With the attribute present and the property cleared, the answer's
  // font-size would inherit rather than take its tier's size, so both go.
  delete card.dataset.cardFit;
  card.style.removeProperty(FIT_SIZE);
  card.style.height = '';
  card.style.maxHeight = `${ceilingPx}px`;

  const naturalH = card.scrollHeight;
  let result;
  if (!answer || naturalH <= card.clientHeight) {
    result = { mode: 'natural', size: base };
  } else {
    const fixedPart = naturalH - answer.offsetHeight;
    const seed = base * Math.sqrt(Math.max(0, ceilingPx - fixedPart)
      / Math.max(1, naturalH - fixedPart));
    card.dataset.cardFit = 'shrunk';
    result = searchFitSize({
      base, floor, seed, baseFits: false,
      fits: (size) => {
        card.style.setProperty(FIT_SIZE, `${size}px`);
        return _fits(card);
      },
    });
  }

  card.dataset.cardFit = result.mode;
  card.style.setProperty(FIT_SIZE, `${result.size}px`);
  const entry = { key, ...result };
  cache.set(card, entry);
  return entry;
}

/**
 * Take a card out of the fit: the layouts that do not fit it (the vertical
 * layout, the fixed model) give the answer its stylesheet size back.
 *
 * @param {HTMLElement} card
 * @param {WeakMap} [cache]
 */
export function clearAnswerFit(card, cache = _fitCache) {
  cache.delete(card);
  if (card.dataset.cardFit === undefined && !card.style.getPropertyValue(FIT_SIZE)) return;
  delete card.dataset.cardFit;
  card.style.removeProperty(FIT_SIZE);
  syncCardScroll(card);
}

/**
 * The cards a pass fits first: the active one and two either side, which a
 * reader can reach before the rest could be fitted.
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
 * Fit and place the side cards for one geometry pass.
 *
 * @param {Iterable<HTMLElement>} cards - The cards to fit: every card, or the
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
    fitAnswerText(card, ceiling);
    recordContentHeight(card);
    syncCardScroll(card);
    card.style.setProperty('top', `${topOf(card)}px`, 'important');
  }
  return { band, pad, ceiling, topOf };
}

/**
 * The band under the top controls and the ceiling above it, for one window.
 * The fit model and a landscape phone's card, which is sized by its content
 * and scrolls itself, are placed by the same band.
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
 * Record a card's content height after its fit, so the observer can tell the
 * fit's own write from a change of content.
 *
 * @param {HTMLElement} card
 */
export function recordContentHeight(card) {
  const wrapper = _contentWrapper(card);
  if (wrapper) _recordedHeights.set(wrapper, _contentHeight(wrapper));
}

/**
 * Re-fit the cards whose content changes, at most once per animation frame.
 *
 * An entry at the height recorded after the card's last fit, within
 * CONTENT_TOLERANCE_PX, is the fit's own write, or the entry every element
 * gets when first observed, and starts nothing. Any other raises that card's
 * content revision and schedules a pass for the changed cards. A font that
 * finishes loading raises every card's revision and schedules a pass for all
 * of them; so does the embed banner's arrival or dismissal.
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
        bumpContentRevision(card);
        pending.add(card);
      }
      if (pending.size) schedule();
    });
    for (const card of list) {
      const wrapper = _contentWrapper(card);
      if (wrapper) observer.observe(wrapper);
    }
  }

  const onFonts = () => {
    for (const card of list) bumpContentRevision(card);
    all = true;
    schedule();
  };
  const onBanner = () => {
    all = true;
    schedule();
  };
  const fonts = document.fonts;
  fonts?.addEventListener?.('loadingdone', onFonts);
  window.addEventListener('telar:embed-banner', onBanner);

  return () => {
    stopped = true;
    observer?.disconnect();
    fonts?.removeEventListener?.('loadingdone', onFonts);
    window.removeEventListener('telar:embed-banner', onBanner);
  };
}
