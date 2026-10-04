/**
 * Telar Story – A side card that scrolls inside itself
 *
 * On a horizontal layout a side card whose answer does not fit even at the
 * smallest size card-fit.js allows is written `data-card-fit="scroll"`, and
 * the reader has to be able to reach the rest of it. The card still never
 * becomes a scroller: it keeps `overflow: hidden`, and this module moves it by
 * writing `scrollTop`, which a box that hides its overflow allows. The browser
 * therefore never scrolls the card for a wheel or a touch, and so never
 * chains a scroll from the card's end to the document, where it would bypass
 * the scroll engine and move the story without it.
 *
 * Input reaches the card through listeners on the card itself, in the capture
 * phase and not passive. Lenis listens on the window in the bubble phase, so
 * the card's listeners run first; an event the card takes is cancelled and
 * stopped there, and Lenis never sees it. The same listeners serve the iPad,
 * which runs no Lenis, so the card scrolls there too.
 *
 * One owner per gesture. A wheel gesture is every wheel event on the page up
 * to a gap of WHEEL_GESTURE_GAP_MS, measured by a capture-phase listener on the
 * window that sees all of them; a touch gesture runs from touchstart to
 * touchend. The owner is decided once, at the gesture's start: the card, when
 * it is the active step's card in scroll mode, the story is at rest on it, no
 * panel is open, the gesture starts over the card, it is not a zoom, a
 * horizontal gesture, a multi-finger touch or a drag of a selection handle, and
 * the card's rendered position has room in the gesture's direction; the story
 * otherwise. The owner does not change until the gesture ends, so the gesture
 * that brings the card to its end stops there, and it is the next one that
 * moves the story. A gesture that starts over the image is the story's even
 * where it drifts onto the card, and one the card owns stays the card's where
 * it drifts off it.
 *
 * The keys reach the card through cardTakesKey, which navigation.js asks
 * before it moves a step.
 *
 * A scroll the browser makes on its own (a focused control revealed, find in
 * page, a selection dragged past the edge, a screen reader's reveal) is
 * adopted, never fought: the value read back after each write is recorded, and
 * any other value found on the card cancels the easing and becomes the target.
 *
 * @version v1.8.0
 */

import { state } from './state.js';
import { cancelDeepLinkLadder } from './deep-link.js';

/** The quiet, in ms, after which the next wheel event starts a new gesture. */
export const WHEEL_GESTURE_GAP_MS = 200;

/** Fraction of the remaining distance the easing covers each frame. */
const EASE = 0.25;

/** Touch inertia keeps this share of its velocity from one frame to the next. */
const INERTIA_DECAY = 0.95;

/** The moves before a touchend that set the release velocity, in ms. */
const VELOCITY_WINDOW_MS = 100;

/** One line of a key press, in px: the distance a panel is scrolled by. */
const LINE_PX = 40;

/** A rendered position within this of an edge or a target is at it, in px. */
const EDGE_SLACK = 0.5;

/** How close to a selection end a touch counts as on its handle, in px. */
const HANDLE_RADIUS = 40;

/** One frame at 60Hz, in ms: the unit touch inertia is advanced in. */
const FRAME_MS = 1000 / 60;

// ── The wheel gesture latch (pure, unit-tested) ─────────────────────────────

/**
 * The state a wheel gesture keeps: when the last wheel event arrived, and who
 * owns the gesture it belongs to.
 *
 * `note` is fed every wheel event on the page, by timeStamp, and answers
 * whether the event starts a new gesture; a new gesture has no owner until
 * `claim` decides one, which then holds until the next gap.
 *
 * @param {number} [gapMs]
 */
export function createGestureLatch(gapMs = WHEEL_GESTURE_GAP_MS) {
  return {
    /** @type {'card'|'story'|null} */
    owner: null,
    last: -Infinity,
    note(timeStamp) {
      const isNew = timeStamp - this.last >= gapMs;
      this.last = timeStamp;
      if (isNew) this.owner = null;
      return isNew;
    },
    claim(decide) {
      if (this.owner === null) this.owner = decide();
      return this.owner;
    },
    holds(now) {
      return this.owner === 'card' && now - this.last < gapMs;
    },
  };
}

// ── Module state ─────────────────────────────────────────────────────────────

const _attached = new WeakSet();
const _engines = new WeakMap();
const _wheel = createGestureLatch();
let _wheelCard = null;
let _touch = null;
let _inertiaCard = null;
let _windowRecorder = false;

// ── The card's position ─────────────────────────────────────────────────────

/** A card's scroll record: where it is going, and what was last written. */
function _engine(card) {
  let e = _engines.get(card);
  if (!e) {
    e = { target: card.scrollTop, written: card.scrollTop, frame: 0, velocity: 0 };
    _engines.set(card, e);
  }
  return e;
}

function _max(card) {
  return Math.max(0, card.scrollHeight - card.clientHeight);
}

function _clamp(card, value) {
  return Math.min(_max(card), Math.max(0, value));
}

function _reducedMotion() {
  return !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

/** Write a position and record what the browser made of it. */
function _write(card, e, value) {
  card.scrollTop = value;
  e.written = card.scrollTop;
}

/** End the easing and any inertia, leaving the card where it is. */
function _stop(e) {
  if (e.frame) cancelAnimationFrame(e.frame);
  e.frame = 0;
  e.velocity = 0;
}

/**
 * Take over a position the browser wrote, if it wrote one.
 *
 * @returns {boolean} Whether the card was somewhere this module did not put it
 */
function _adoptBrowserScroll(card, e) {
  if (card.scrollTop === e.written) return false;
  _stop(e);
  e.target = e.written = card.scrollTop;
  return true;
}

/**
 * One frame of the easing, and of touch inertia where it runs.
 *
 * A write the browser rounds back to where the card already is would leave
 * the easing a fraction short of its target forever, so a frame that moves
 * nothing goes the rest of the way at once.
 */
function _tick(card) {
  const e = _engine(card);
  e.frame = 0;
  if (_adoptBrowserScroll(card, e)) return;

  if (e.velocity) {
    e.target = _clamp(card, e.target + e.velocity);
    e.velocity *= INERTIA_DECAY;
    if (Math.abs(e.velocity) < 0.1 || e.target <= 0 || e.target >= _max(card)) e.velocity = 0;
  }

  const from = card.scrollTop;
  const gap = e.target - from;
  if (Math.abs(gap) <= EDGE_SLACK) {
    _write(card, e, e.target);
    e.target = e.written;
    if (!e.velocity) return;
  } else {
    _write(card, e, from + gap * EASE);
    if (e.written === from) {
      _write(card, e, e.target);
      e.target = e.written;
    }
  }
  e.frame = requestAnimationFrame(() => _tick(card));
}

/** Carry the card toward its target: at once under reduced motion. */
function _run(card, e) {
  if (_reducedMotion()) {
    _stop(e);
    _write(card, e, e.target);
    e.target = e.written;
    return;
  }
  if (!e.frame) e.frame = requestAnimationFrame(() => _tick(card));
}

/** End the touch inertia still running on any card. */
function _endInertia() {
  if (!_inertiaCard) return;
  const e = _engines.get(_inertiaCard);
  if (e) e.velocity = 0;
  _inertiaCard = null;
}

/** Whether the card is the current step's, in scroll mode. */
function _isActiveScrollCard(card) {
  return !!card && state.textCards?.[state.currentIndex] === card
    && card.dataset.cardFit === 'scroll';
}

/**
 * Move a card's target by `delta` px, clamped to its content. A card that has
 * stopped being the active one takes nothing: the gesture it owned is
 * swallowed to its end.
 */
function _scrollBy(card, delta) {
  if (!_isActiveScrollCard(card)) return;
  const e = _engine(card);
  _adoptBrowserScroll(card, e);
  e.target = _clamp(card, e.target + delta);
  _run(card, e);
}

// ── Who owns a gesture ───────────────────────────────────────────────────────

/**
 * Whether the card can own a gesture that starts on `target`.
 *
 * With Lenis the story has to be at rest on the card's step and not stopped,
 * which rules out the dwell after a snap and an open panel's hold. Without
 * Lenis (the iPad) a button move replaces the current step at once, so there
 * is no story scroll for the card's to meet.
 */
function _cardCanOwn(card, target) {
  if (!_isActiveScrollCard(card) || !card.contains(target)) return false;
  if (state.isPanelOpen) return false;
  const lenis = state.lenis;
  if (!lenis) return true;
  return !lenis.isStopped
    && Math.abs(state.scrollPosition - (state.currentIndex + 1)) < 0.001;
}

/** Whether the card's rendered position can move in the direction of `dy`. */
function _hasRoom(card, dy) {
  const top = card.scrollTop;
  return dy > 0 ? top < _max(card) - EDGE_SLACK : top > EDGE_SLACK;
}

/** Cancel an event and keep it from every listener after this one. */
function _swallow(ev) {
  if (ev.cancelable) ev.preventDefault();
  ev.stopPropagation();
}

// ── Wheel ────────────────────────────────────────────────────────────────────

/** A wheel's vertical delta in px, whatever unit the event reports it in. */
function _wheelDelta(ev, card) {
  if (ev.deltaMode === 1) return ev.deltaY * 16;
  if (ev.deltaMode === 2) return ev.deltaY * card.clientHeight;
  return ev.deltaY;
}

/** A zoom, a gesture with no vertical part, or one mostly across the story. */
function _wheelExcluded(ev) {
  return ev.ctrlKey || ev.metaKey || ev.deltaY === 0
    || Math.abs(ev.deltaX) > Math.abs(ev.deltaY);
}

/** The attached card an event landed in, if any. */
function _cardAt(target) {
  const card = target instanceof Element ? target.closest('.text-card') : null;
  return card && _attached.has(card) ? card : null;
}

/**
 * Every wheel event on the page, before any card or Lenis sees it.
 *
 * It measures the gap that ends a gesture, gives the story a gesture whose
 * first event lands outside a card, ends the card's hold on a gesture at a
 * zoom, and takes for the card the events of a gesture it owns that have
 * drifted off it. It is not passive for that last case alone; every other
 * event passes it untouched.
 */
function _onWindowWheel(ev) {
  if (_wheel.note(ev.timeStamp)) {
    _wheelCard = null;
    _endInertia();
  }
  if (ev.ctrlKey || ev.metaKey) {
    // A zoom is the browser's, wherever the gesture stood: it ends the card's
    // hold on the gesture and is neither cancelled nor scrolled into the card.
    _wheel.owner = 'story';
    _wheelCard = null;
    _endInertia();
    return;
  }
  const card = _cardAt(ev.target);
  if (_wheel.owner === null && !card) _wheel.owner = 'story';
  if (_wheel.owner === 'card' && card !== _wheelCard) {
    _swallow(ev);
    _scrollBy(_wheelCard, _wheelDelta(ev, _wheelCard));
  }
}

function _onCardWheel(ev) {
  const card = ev.currentTarget;
  const owner = _wheel.claim(() => (
    !_wheelExcluded(ev) && _cardCanOwn(card, ev.target) && _hasRoom(card, ev.deltaY)
      ? 'card' : 'story'));
  if (owner !== 'card') return;
  if (_wheelCard === null) {
    _wheelCard = card;
    cancelDeepLinkLadder();
  }
  if (card !== _wheelCard) return;
  _swallow(ev);
  _scrollBy(card, _wheelDelta(ev, card));
}

function _installWindowRecorder() {
  if (_windowRecorder) return;
  _windowRecorder = true;
  window.addEventListener('wheel', _onWindowWheel, { passive: false, capture: true });
}

// ── Touch ────────────────────────────────────────────────────────────────────

/**
 * Whether a touch starts on one of the handles of the current selection: the
 * geometry Lenis uses for the same question (lenis.mjs, isTouchOnSelectionHandle),
 * applied on every platform.
 */
function _touchOnSelectionHandle(ev) {
  const selection = window.getSelection?.();
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return false;
  const touch = ev.targetTouches?.[0] ?? ev.changedTouches?.[0];
  if (!touch) return false;
  const rects = selection.getRangeAt(0).getClientRects();
  if (!rects || rects.length === 0) return false;
  const first = rects[0];
  const last = rects[rects.length - 1];
  return Math.hypot(touch.clientX - first.left, touch.clientY - first.top) <= HANDLE_RADIUS
    || Math.hypot(touch.clientX - last.right, touch.clientY - last.bottom) <= HANDLE_RADIUS;
}

function _onCardTouchStart(ev) {
  _endInertia();
  const t = ev.touches?.[0];
  _touch = {
    card: ev.currentTarget,
    active: true,
    owner: null,
    excluded: (ev.touches?.length || 0) > 1 || _touchOnSelectionHandle(ev),
    x: t ? t.clientX : 0,
    y: t ? t.clientY : 0,
    moves: [],
  };
}

function _onCardTouchMove(ev) {
  const g = _touch;
  const card = ev.currentTarget;
  if (!g || g.card !== card || g.excluded) return;
  const t = ev.touches?.[0];
  if (!t) return;
  const dx = -(t.clientX - g.x);
  const dy = -(t.clientY - g.y);
  g.x = t.clientX;
  g.y = t.clientY;

  if (g.owner === null) {
    if (dx === 0 && dy === 0) return;
    const own = dy !== 0 && Math.abs(dx) <= Math.abs(dy) && ev.touches.length === 1
      && _cardCanOwn(card, ev.target) && _hasRoom(card, dy);
    g.owner = own ? 'card' : 'story';
    if (own) cancelDeepLinkLadder();
  }
  if (g.owner !== 'card') return;
  _swallow(ev);
  g.moves.push({ t: ev.timeStamp, dy });
  _scrollBy(card, dy);
}

/**
 * The end of a touch the card owns gives inertia its velocity, from the moves
 * of the last VELOCITY_WINDOW_MS, and no displacement of its own.
 */
function _onCardTouchEnd(ev) {
  const g = _touch;
  const card = ev.currentTarget;
  if (!g || g.card !== card) return;
  if (ev.touches?.length) return;
  g.active = false;
  if (g.owner !== 'card') return;
  _swallow(ev);
  if (_reducedMotion() || !_isActiveScrollCard(card)) return;

  const recent = g.moves.filter((m) => ev.timeStamp - m.t <= VELOCITY_WINDOW_MS);
  if (!recent.length) return;
  const distance = recent.reduce((sum, m) => sum + m.dy, 0);
  const span = Math.max(FRAME_MS, ev.timeStamp - recent[0].t);
  const e = _engine(card);
  e.velocity = (distance / span) * FRAME_MS;
  _inertiaCard = card;
  if (!e.frame) e.frame = requestAnimationFrame(() => _tick(card));
}

function _onCardTouchCancel() {
  _touch = null;
}

function _onCardScroll(ev) {
  const card = ev.currentTarget;
  const e = _engines.get(card);
  if (e) _adoptBrowserScroll(card, e);
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Give a text card the engine that scrolls it. card-pool.js calls this once
 * for each text card it builds; a card is only ever scrolled while it is the
 * active one and in scroll mode, so attaching every card costs nothing else.
 *
 * @param {HTMLElement} card
 */
export function attachCardScroll(card) {
  if (!card || _attached.has(card)) return;
  _attached.add(card);
  _installWindowRecorder();
  const own = { passive: false, capture: true };
  card.addEventListener('wheel', _onCardWheel, own);
  card.addEventListener('touchstart', _onCardTouchStart, own);
  card.addEventListener('touchmove', _onCardTouchMove, own);
  card.addEventListener('touchend', _onCardTouchEnd, own);
  card.addEventListener('touchcancel', _onCardTouchCancel, { passive: true, capture: true });
  card.addEventListener('scroll', _onCardScroll, { passive: true });
}

/**
 * Put a card back at its question, with nothing left running: a card arrives
 * at its top on every activation.
 *
 * @param {HTMLElement} card
 */
export function resetCardScroll(card) {
  if (!card) return;
  const e = _engines.get(card);
  if (e) _stop(e);
  if (_inertiaCard === card) _inertiaCard = null;
  if (card.scrollTop !== 0) card.scrollTop = 0;
  if (e) e.target = e.written = card.scrollTop;
}

/**
 * Bring a card's position into line with its fit after a geometry pass: a
 * card outside scroll mode goes back to its top, and one in it is held inside
 * its new extent.
 *
 * @param {HTMLElement} card
 */
export function syncCardScroll(card) {
  if (!card) return;
  if (card.dataset.cardFit !== 'scroll') {
    if (card.scrollTop !== 0 || _engines.has(card)) resetCardScroll(card);
    return;
  }
  const e = _engines.get(card);
  const max = _max(card);
  if (e) e.target = _clamp(card, e.target);
  if (card.scrollTop > max) {
    card.scrollTop = max;
    if (e) e.written = card.scrollTop;
  }
}

/**
 * Offer a story key to the active card before it moves a step.
 *
 * Judged from the rendered position. A card easing toward the edge in the
 * key's direction is taken there at once, and the key does not step; a card
 * already at rest at that edge hands the key back to the story.
 *
 * @param {'forward'|'backward'} direction
 * @param {'line'|'page'|'full'} kind - A line is LINE_PX; a page is the card's
 *   height less one line of its answer; full is the card's whole extent, so the
 *   target is its top or its end
 * @returns {'scrolled'|'at-edge'|'none'} 'none' where no scroll-mode card is active
 */
export function cardTakesKey(direction, kind) {
  const card = state.textCards?.[state.currentIndex];
  if (!_isActiveScrollCard(card)) return 'none';

  const e = _engine(card);
  _adoptBrowserScroll(card, e);
  const sign = direction === 'forward' ? 1 : -1;
  const max = _max(card);
  const edge = sign > 0 ? max : 0;
  const rendered = card.scrollTop;
  const moving = Math.abs(e.target - rendered) > EDGE_SLACK;
  const amount = _keyAmount(card, kind, max);

  if (moving && Math.sign(e.target - rendered) === sign) {
    if (Math.abs(e.target - edge) <= EDGE_SLACK) {
      _stop(e);
      _write(card, e, e.target);
      e.target = e.written;
      return 'scrolled';
    }
    return _stepTarget(card, e, e.target + sign * amount);
  }

  const atEdge = sign > 0 ? rendered >= max - EDGE_SLACK : rendered <= EDGE_SLACK;
  if (!moving && atEdge) return 'at-edge';

  return _stepTarget(card, e, (moving ? rendered : e.target) + sign * amount);
}

/** How far a key of this kind moves the card: a line, a page, or the whole extent. */
function _keyAmount(card, kind, max) {
  if (kind === 'full') return max;
  return kind === 'page' ? _pageAmount(card) : LINE_PX;
}

/** Aim the card's eased scroll at `to`, from rest, and run it. */
function _stepTarget(card, e, to) {
  e.velocity = 0;
  e.target = _clamp(card, to);
  _run(card, e);
  return 'scrolled';
}

/** A page of the card: its height less one line of the answer. */
function _pageAmount(card) {
  const answer = card.querySelector('.step-answer');
  const line = answer ? parseFloat(getComputedStyle(answer).lineHeight) || 0 : 0;
  return Math.max(LINE_PX, card.clientHeight - line);
}

/**
 * Whether a gesture the card owns is under way. Read by the scroll engine's
 * takeover test, so the two cannot disagree about whose input it is; reading
 * it changes nothing.
 *
 * @param {number} [now] - On the clock event timeStamps are read against
 * @returns {boolean}
 */
export function cardHoldsGesture(now = performance.now()) {
  if (_touch?.active && _touch.owner === 'card') return true;
  return _wheel.holds(now);
}
