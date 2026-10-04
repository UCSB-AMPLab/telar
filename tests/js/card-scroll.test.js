/**
 * Tests for Telar Story – A side card that scrolls inside itself
 *
 * The wheel gesture latch on its own, fed explicit timeStamps; then the DOM
 * wiring, with real WheelEvents and touch events dispatched inside a card and
 * a bubble-phase spy on the window standing where Lenis listens. A card-owned
 * event is cancelled and never reaches the spy; a story-owned one reaches it
 * uncancelled.
 *
 * The card is 400px tall over 1000px of content, so it scrolls through 600px.
 * jsdom lays nothing out, so those heights are stubbed and scrollTop is only
 * what was last written; animation frames are run by hand.
 *
 * @version v1.8.0
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../assets/js/telar-story/deep-link.js', () => ({ cancelDeepLinkLadder: vi.fn() }));

import {
  attachCardScroll, cardTakesKey, cardHoldsGesture, createGestureLatch, resetCardScroll,
  WHEEL_GESTURE_GAP_MS,
} from '../../assets/js/telar-story/card-scroll.js';
import { cancelDeepLinkLadder } from '../../assets/js/telar-story/deep-link.js';
import { state } from '../../assets/js/telar-story/state.js';

const MAX = 600;

// ── Clock, frames, reduced motion ────────────────────────────────────────────

// Event timeStamps. Each test starts far from the last so that no gesture
// carries over from one test to the next.
let clock = 1e6;
const atMs = (ms) => clock + ms;

let frames = [];
function advanceFrames(limit = 500) {
  for (let i = 0; i < limit && frames.some(Boolean); i++) {
    const run = frames;
    frames = [];
    for (const cb of run) if (cb) cb();
  }
}

let reduce = false;

// ── The card and its events ──────────────────────────────────────────────────

let card;
let inside;
let image;
let storySpy;

function makeScrollCard() {
  card = document.createElement('div');
  card.className = 'text-card';
  card.dataset.cardFit = 'scroll';
  card.dataset.stepIndex = '0';
  const content = document.createElement('div');
  content.className = 'step-content';
  const answer = document.createElement('div');
  answer.className = 'step-answer';
  answer.style.lineHeight = '25px';
  inside = document.createElement('p');
  answer.append(inside);
  content.append(answer);
  card.append(content);
  image = document.createElement('div');
  image.className = 'viewer-plate';
  document.body.append(image, card);
  Object.defineProperty(card, 'scrollHeight', { configurable: true, get: () => 1000 });
  Object.defineProperty(card, 'clientHeight', { configurable: true, get: () => 400 });
  attachCardScroll(card);
  state.textCards = { 0: card };
  state.currentIndex = 0;
  state.isPanelOpen = false;
  state.lenis = null;
  state.scrollPosition = 1;
}

function fireWheel(target, t, { deltaY = 0, deltaX = 0, deltaMode = 0, ctrlKey = false, metaKey = false } = {}) {
  const ev = new WheelEvent('wheel', {
    deltaY, deltaX, deltaMode, ctrlKey, metaKey, bubbles: true, cancelable: true,
  });
  Object.defineProperty(ev, 'timeStamp', { value: atMs(t) });
  target.dispatchEvent(ev);
  return ev;
}

/** A trace of wheel deltas, `gap` ms apart from `t0`; returns the events. */
function trace(target, t0, deltas, gap = 16) {
  return deltas.map((deltaY, i) => fireWheel(target, t0 + i * gap, { deltaY }));
}

function touch(type, target, t, points) {
  const ev = new Event(type, { bubbles: true, cancelable: true });
  const list = points.map(([clientX, clientY]) => ({ clientX, clientY, target }));
  Object.defineProperty(ev, 'touches', { value: type === 'touchend' ? [] : list });
  Object.defineProperty(ev, 'targetTouches', { value: type === 'touchend' ? [] : list });
  Object.defineProperty(ev, 'changedTouches', { value: list });
  Object.defineProperty(ev, 'timeStamp', { value: atMs(t) });
  target.dispatchEvent(ev);
  return ev;
}

/** A one-finger swipe: y positions of successive touch points, 16ms apart. */
function swipe(target, t0, ys, { x = 50 } = {}) {
  touch('touchstart', target, t0, [[x, ys[0]]]);
  const moves = ys.slice(1).map((y, i) => touch('touchmove', target, t0 + (i + 1) * 16, [[x, y]]));
  const end = touch('touchend', target, t0 + ys.length * 16, [[x, ys.at(-1)]]);
  return { moves, end };
}

beforeEach(() => {
  clock += 1e5;
  frames = [];
  reduce = false;
  vi.stubGlobal('requestAnimationFrame', (cb) => { frames.push(cb); return frames.length; });
  vi.stubGlobal('cancelAnimationFrame', (id) => { frames[id - 1] = null; });
  vi.stubGlobal('matchMedia', (q) => ({ matches: reduce && q.includes('reduce'), media: q }));
  storySpy = vi.fn();
  window.addEventListener('wheel', storySpy);
  window.addEventListener('touchmove', storySpy);
  window.addEventListener('touchend', storySpy);
  vi.mocked(cancelDeepLinkLadder).mockClear();
  makeScrollCard();
});

afterEach(() => {
  window.removeEventListener('wheel', storySpy);
  window.removeEventListener('touchmove', storySpy);
  window.removeEventListener('touchend', storySpy);
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
  delete window.getSelection;
});

// ── The latch ────────────────────────────────────────────────────────────────

describe('createGestureLatch', () => {
  it('holds a decaying trace with jitter as one gesture', () => {
    const latch = createGestureLatch();
    const news = [0, 16, 32, 48, 64].map((t) => latch.note(t));
    expect(news).toEqual([true, false, false, false, false]);
  });

  it('starts a gesture after a gap of 200ms and not before', () => {
    const latch = createGestureLatch();
    latch.note(0);
    expect(latch.note(WHEEL_GESTURE_GAP_MS - 1)).toBe(false);
    expect(latch.note(2 * WHEEL_GESTURE_GAP_MS - 1)).toBe(true);
  });

  it('keeps the owner it was given until the gesture ends', () => {
    const latch = createGestureLatch();
    latch.note(0);
    expect(latch.claim(() => 'card')).toBe('card');
    latch.note(16);
    expect(latch.claim(() => 'story')).toBe('card');
    latch.note(400);
    expect(latch.claim(() => 'story')).toBe('story');
  });
});

// ── Wheel ────────────────────────────────────────────────────────────────────

describe('a wheel over a card with room', () => {
  it('is the card\'s until the gap, then the story\'s once the card is at its end', () => {
    reduce = true;
    const owned = trace(inside, 0, [300, 300, 300, 300]);
    for (const ev of owned) expect(ev.defaultPrevented).toBe(true);
    expect(storySpy).not.toHaveBeenCalled();
    expect(card.scrollTop).toBe(MAX);

    const next = fireWheel(inside, 48 + 250, { deltaY: 100 });
    expect(next.defaultPrevented).toBe(false);
    expect(storySpy).toHaveBeenCalledTimes(1);
  });

  it('swallows a jitter trace that ends the card, and a second swipe 120ms after it', () => {
    card.scrollTop = MAX - 10;
    const first = trace(inside, 0, [24, 18, 12, 6, 12]);
    advanceFrames();
    const second = trace(inside, 64 + 120, [30, 20, 10]);
    for (const ev of [...first, ...second]) expect(ev.defaultPrevented).toBe(true);
    expect(storySpy).not.toHaveBeenCalled();
    expect(card.scrollTop).toBe(MAX);

    const third = fireWheel(inside, 64 + 120 + 32 + 250, { deltaY: 30 });
    expect(third.defaultPrevented).toBe(false);
    expect(storySpy).toHaveBeenCalledTimes(1);
  });

  it('gives exactly the tick after the end to the story, ticks 300ms apart', () => {
    reduce = true;
    card.scrollTop = MAX - 150;
    const ticks = [0, 300, 600, 900].map((t) => fireWheel(inside, t, { deltaY: 100 }));
    expect(ticks.map((ev) => ev.defaultPrevented)).toEqual([true, true, false, false]);
    expect(card.scrollTop).toBe(MAX);
    expect(storySpy).toHaveBeenCalledTimes(2);
  });

  it('decides the owner from the rendered position, not the target', () => {
    // The first gesture sets the target to the end; nothing has been drawn.
    trace(inside, 0, [700]);
    expect(card.scrollTop).toBe(0);
    const later = fireWheel(inside, 400, { deltaY: 50 });
    expect(later.defaultPrevented).toBe(true);
    expect(storySpy).not.toHaveBeenCalled();
  });

  it('gives an upward wheel at the top to the story', () => {
    const ev = fireWheel(inside, 0, { deltaY: -100 });
    expect(ev.defaultPrevented).toBe(false);
    expect(storySpy).toHaveBeenCalledTimes(1);
  });

  it('moves the card back on a reversal inside its gesture', () => {
    reduce = true;
    trace(inside, 0, [200, -80]);
    expect(card.scrollTop).toBe(120);
  });

  it('reads lines and pages as px', () => {
    reduce = true;
    fireWheel(inside, 0, { deltaY: 3, deltaMode: 1 });
    expect(card.scrollTop).toBe(48);
    fireWheel(inside, 16, { deltaY: 1, deltaMode: 2 });
    expect(card.scrollTop).toBe(448);
  });

  it('cancels a pending deep-link panel on its first event', () => {
    trace(inside, 0, [50, 50]);
    expect(cancelDeepLinkLadder).toHaveBeenCalledTimes(1);
  });

  it('keeps a horizontal event inside a gesture it owns', () => {
    const vertical = fireWheel(inside, 0, { deltaY: 40 });
    const across = fireWheel(inside, 16, { deltaY: 0, deltaX: 60 });
    expect(vertical.defaultPrevented).toBe(true);
    expect(across.defaultPrevented).toBe(true);
    expect(storySpy).not.toHaveBeenCalled();
  });

  it('keeps the events of a gesture it owns that drift off it', () => {
    reduce = true;
    fireWheel(inside, 0, { deltaY: 40 });
    const off = fireWheel(image, 16, { deltaY: 40 });
    expect(off.defaultPrevented).toBe(true);
    expect(storySpy).not.toHaveBeenCalled();
    expect(card.scrollTop).toBe(80);
  });

  it('leaves a gesture that starts over the image to the story when it drifts onto the card', () => {
    const start = fireWheel(image, 0, { deltaY: 40 });
    const onCard = fireWheel(inside, 16, { deltaY: 40 });
    expect(start.defaultPrevented).toBe(false);
    expect(onCard.defaultPrevented).toBe(false);
    expect(storySpy).toHaveBeenCalledTimes(2);
    expect(card.scrollTop).toBe(0);
  });

  it('holds the gesture while it runs, and not after the gap', () => {
    fireWheel(inside, 0, { deltaY: 40 });
    expect(cardHoldsGesture(atMs(50))).toBe(true);
    expect(cardHoldsGesture(atMs(250))).toBe(false);
  });
});

describe('a wheel the card never owns', () => {
  const cases = {
    'a ctrl-wheel (zoom)': { deltaY: 40, ctrlKey: true },
    'a meta-wheel (zoom)': { deltaY: 40, metaKey: true },
    'no vertical delta': { deltaY: 0, deltaX: 0 },
    'mostly across the story': { deltaY: 10, deltaX: 40 },
  };
  for (const [name, init] of Object.entries(cases)) {
    it(`leaves ${name} uncancelled and unstopped`, () => {
      const ev = fireWheel(inside, 0, init);
      expect(ev.defaultPrevented).toBe(false);
      expect(storySpy).toHaveBeenCalledTimes(1);
      expect(card.scrollTop).toBe(0);
    });
  }

  for (const [name, mod] of [['ctrl (a pinch)', { ctrlKey: true }], ['meta', { metaKey: true }]]) {
    it(`ends the card's gesture at a ${name} wheel within the gap, and leaves it to the browser`, () => {
      reduce = true;
      const owned = trace(inside, 0, [40, 40]);
      for (const ev of owned) expect(ev.defaultPrevented).toBe(true);
      expect(card.scrollTop).toBe(80);

      const zoom = fireWheel(inside, 32 + 50, { deltaY: 40, ...mod });
      expect(zoom.defaultPrevented).toBe(false);
      expect(zoom.cancelBubble).toBe(false);
      expect(storySpy).toHaveBeenCalledTimes(1);
      expect(card.scrollTop).toBe(80);
    });
  }

  it('is not the card\'s while a panel is open', () => {
    state.isPanelOpen = true;
    expect(fireWheel(inside, 0, { deltaY: 40 }).defaultPrevented).toBe(false);
  });

  it('is not the card\'s while Lenis is stopped', () => {
    state.lenis = { isStopped: true };
    expect(fireWheel(inside, 0, { deltaY: 40 }).defaultPrevented).toBe(false);
  });

  it('is not the card\'s while the story is between steps', () => {
    state.lenis = { isStopped: false };
    state.scrollPosition = 1.2;
    expect(fireWheel(inside, 0, { deltaY: 40 }).defaultPrevented).toBe(false);
  });

  it('is the card\'s with Lenis at rest on its step', () => {
    state.lenis = { isStopped: false };
    state.scrollPosition = 1;
    expect(fireWheel(inside, 0, { deltaY: 40 }).defaultPrevented).toBe(true);
  });

  it('is the current step\'s card\'s without Lenis', () => {
    expect(state.lenis).toBeNull();
    expect(fireWheel(inside, 0, { deltaY: 40 }).defaultPrevented).toBe(true);
  });

  it('is not a card\'s outside scroll mode', () => {
    card.dataset.cardFit = 'shrunk';
    expect(fireWheel(inside, 0, { deltaY: 40 }).defaultPrevented).toBe(false);
  });

  it('swallows the rest of a gesture whose card stopped being the active one', () => {
    reduce = true;
    fireWheel(inside, 0, { deltaY: 40 });
    state.currentIndex = 1;
    const after = fireWheel(inside, 16, { deltaY: 40 });
    expect(after.defaultPrevented).toBe(true);
    expect(storySpy).not.toHaveBeenCalled();
    expect(card.scrollTop).toBe(40);
  });
});

// ── Touch ────────────────────────────────────────────────────────────────────

describe('a touch over the card', () => {
  it('is decided at the first move and cancelled through its end', () => {
    reduce = true;
    const { moves, end } = swipe(inside, 0, [300, 280, 250, 210]);
    for (const ev of [...moves, end]) expect(ev.defaultPrevented).toBe(true);
    expect(storySpy).not.toHaveBeenCalled();
  });

  it('moves exactly the sum of its moves, the end adding nothing, under reduced motion', () => {
    reduce = true;
    swipe(inside, 0, [300, 280, 250, 210]);
    advanceFrames();
    expect(card.scrollTop).toBe(90);
  });

  it('carries on from the release velocity and stops at the card\'s end', () => {
    card.scrollTop = MAX - 100;
    swipe(inside, 0, [400, 340, 280, 220, 160]);
    advanceFrames();
    expect(card.scrollTop).toBe(MAX);
    expect(storySpy).not.toHaveBeenCalled();
  });

  it('runs no inertia under reduced motion', () => {
    reduce = true;
    swipe(inside, 0, [400, 340, 280]);
    advanceFrames();
    expect(card.scrollTop).toBe(120);
  });

  it('leaves a two-finger touch to the story', () => {
    touch('touchstart', inside, 0, [[50, 300], [90, 300]]);
    const move = touch('touchmove', inside, 16, [[50, 250], [90, 250]]);
    expect(move.defaultPrevented).toBe(false);
    expect(storySpy).toHaveBeenCalled();
  });

  it('leaves a touch on a selection handle to the story', () => {
    window.getSelection = () => ({
      isCollapsed: false, rangeCount: 1,
      getRangeAt: () => ({ getClientRects: () => [{ left: 40, top: 290, right: 200, bottom: 310 }] }),
    });
    const { moves } = swipe(inside, 0, [300, 260, 220], { x: 45 });
    expect(moves.some((ev) => ev.defaultPrevented)).toBe(false);
  });

  it('leaves a sideways first move to the story for the whole touch', () => {
    touch('touchstart', inside, 0, [[50, 300]]);
    const across = touch('touchmove', inside, 16, [[90, 298]]);
    const down = touch('touchmove', inside, 32, [[90, 250]]);
    expect(across.defaultPrevented).toBe(false);
    expect(down.defaultPrevented).toBe(false);
  });
});

// ── A scroll the browser makes ───────────────────────────────────────────────

describe('a scroll the browser makes on its own', () => {
  it('cancels the easing and becomes the target', () => {
    fireWheel(inside, 0, { deltaY: 500 });
    const first = frames.shift();
    first();
    expect(card.scrollTop).toBeGreaterThan(0);
    expect(card.scrollTop).toBeLessThan(500);

    card.scrollTop = 37;                    // a focused link revealed
    advanceFrames();

    expect(card.scrollTop).toBe(37);
    reduce = true;
    cardTakesKey('forward', 'line');
    expect(card.scrollTop).toBe(77);
  });
});

// ── Keys ─────────────────────────────────────────────────────────────────────

describe('cardTakesKey', () => {
  beforeEach(() => { reduce = true; });

  it('scrolls a line by 40px and a page by the card less one answer line', () => {
    expect(cardTakesKey('forward', 'line')).toBe('scrolled');
    expect(card.scrollTop).toBe(40);
    expect(cardTakesKey('forward', 'page')).toBe('scrolled');
    expect(card.scrollTop).toBe(40 + 375);
  });

  it('answers at-edge only at rest at the edge in the key\'s direction', () => {
    expect(cardTakesKey('backward', 'line')).toBe('at-edge');
    card.scrollTop = MAX;
    expect(cardTakesKey('forward', 'line')).toBe('at-edge');
    expect(cardTakesKey('backward', 'line')).toBe('scrolled');
  });

  it('takes a card easing to its edge there at once, without stepping', () => {
    reduce = false;
    card.scrollTop = MAX - 300;
    expect(cardTakesKey('forward', 'page')).toBe('scrolled');   // the target is the end
    expect(card.scrollTop).toBe(MAX - 300);                     // nothing drawn yet
    expect(cardTakesKey('forward', 'page')).toBe('scrolled');   // finishes the easing
    expect(card.scrollTop).toBe(MAX);
    expect(cardTakesKey('forward', 'page')).toBe('at-edge');
  });

  it('takes the whole extent for a full move, to the end going forward and to the top going back', () => {
    card.scrollTop = 100;
    expect(cardTakesKey('forward', 'full')).toBe('scrolled');
    expect(card.scrollTop).toBe(MAX);
    expect(cardTakesKey('forward', 'full')).toBe('at-edge');
    expect(cardTakesKey('backward', 'full')).toBe('scrolled');
    expect(card.scrollTop).toBe(0);
    expect(cardTakesKey('backward', 'full')).toBe('at-edge');
  });

  it('eases a full move, drawing nothing on the key and reaching the edge over the frames', () => {
    reduce = false;
    expect(cardTakesKey('forward', 'full')).toBe('scrolled');
    expect(card.scrollTop).toBe(0);
    advanceFrames();
    expect(card.scrollTop).toBe(MAX);
  });

  it('answers none where no card is in scroll mode', () => {
    card.dataset.cardFit = 'natural';
    expect(cardTakesKey('forward', 'line')).toBe('none');
  });

  it('starts the card at its top on activation', () => {
    cardTakesKey('forward', 'page');
    resetCardScroll(card);
    expect(card.scrollTop).toBe(0);
    expect(cardTakesKey('backward', 'line')).toBe('at-edge');
  });
});
