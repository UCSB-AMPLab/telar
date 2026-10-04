/**
 * The scroll engine on the real Lenis and Snap, driven with wheel traces.
 *
 * A gesture the snap does not take is carried to a step once the scroll has
 * stopped. These run the traces through Lenis's own smoothing, because whether
 * the scroll ever reports having stopped is a property of Lenis that the mocked
 * harness cannot model.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../../assets/js/telar-story/card-pool.js',
  async () => (await import('./scroll-engine-harness.js')).cardPoolModule);
vi.mock('../../assets/js/telar-story/iiif-card.js',
  async () => (await import('./scroll-engine-harness.js')).iiifCardModule);
vi.mock('../../assets/js/telar-story/navigation.js',
  async () => (await import('./scroll-engine-harness.js')).navigationModule);
vi.mock('../../assets/js/telar-story/viewer.js',
  async () => (await import('./scroll-engine-harness.js')).viewerModule);

import { initScrollEngine, getScrollEngineState, keyboardNav } from '../../assets/js/telar-story/scroll-engine.js';
import { state } from '../../assets/js/telar-story/state.js';
import { engineStory, resetState, mocks } from './scroll-engine-harness.js';

const STEPS = 6;
const H = 720;
let now;
let scrollY;

function frames(ms) {
  for (let t = 0; t < ms; t += 16) {
    now += 16;
    vi.advanceTimersByTime(16);
    getScrollEngineState().lenis.raf(now);
  }
}

/** Play [atMs, deltaY] events, one 16 ms frame at a time. */
function play(trace) {
  let i = 0;
  const t0 = now;
  while (i < trace.length) {
    while (i < trace.length && trace[i][0] <= now - t0) {
      window.dispatchEvent(new WheelEvent('wheel', { deltaY: trace[i][1], bubbles: true, cancelable: true }));
      i++;
    }
    frames(16);
  }
}

const decayingTrace = (n, first, k, dt) => Array.from({ length: n }, (_, i) => [i * dt, Math.round(first * Math.pow(k, i))]);

describe('a wheel gesture on the real Lenis and Snap', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    now = 1000;
    scrollY = 0;
    engineStory(STEPS);
    resetState({ currentIndex: -1 });
    vi.stubGlobal('Window', class { static [Symbol.hasInstance](o) { return o === window; } });
    vi.stubGlobal('innerHeight', H);
    vi.stubGlobal('innerWidth', 1280);
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} unobserve() {} });
    vi.stubGlobal('requestAnimationFrame', () => 0);
    vi.stubGlobal('scrollTo', (o) => { scrollY = typeof o === 'object' ? o.top : o; });
    Object.defineProperty(window, 'scrollY', { get: () => scrollY, configurable: true });
    Object.defineProperty(document.documentElement, 'scrollHeight', { get: () => (STEPS + 1) * H, configurable: true });
    Object.defineProperty(document.documentElement, 'clientHeight', { get: () => H, configurable: true });
    Object.defineProperty(document.documentElement, 'clientWidth', { get: () => 1280, configurable: true });
    initScrollEngine(STEPS);
    state.lenis = getScrollEngineState().lenis;
    state.lenis.scrollTo(3 * H, { immediate: true });
    frames(500);
  });

  afterEach(() => {
    // Each test's Lenis listens on the window; one left running hears the next
    // test's input and reports it to the engine a second time.
    getScrollEngineState().lenis.destroy();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  /** Play a trace, wait out the tail and any carry, and read where the story rests. */
  function settledStep(trace, idleMs = 6000) {
    play(trace);
    frames(idleMs);
    return state.lenis.animatedScroll / H;
  }

  const raw = (trace) => trace.reduce((a, e) => a + e[1], 0);

  it('a light trace whose total is odd comes to rest on the step it was heading for', () => {
    // 885 raw is a target on a half pixel at a wheel multiplier of 0.5.
    const trace = decayingTrace(30, 70, 0.93, 16);
    expect(raw(trace) % 2).toBe(1);
    expect(settledStep(trace)).toBe(4);
    expect(state.scrollPosition).toBe(4);
    expect(document.querySelector('.card-stack').classList.contains('is-scrubbing')).toBe(false);
  });

  it('a light trace whose total is even comes to rest on the same step', () => {
    const trace = decayingTrace(30, 70, 0.93, 16);
    trace[0][1] += 1;
    expect(raw(trace) % 2).toBe(0);
    expect(settledStep(trace)).toBe(4);
  });

  it('a light trace backwards is carried to the step behind', () => {
    const trace = decayingTrace(30, -70, 0.93, 16);
    expect(raw(trace) % 2).toBe(-1);
    expect(settledStep(trace)).toBe(2);
  });

  it('a trackpad flick lands where the snap takes it', () => {
    expect(settledStep(decayingTrace(110, 90, 0.96, 16))).toBe(5);
  });

  it('a hard flick lands where the snap takes it', () => {
    expect(settledStep(decayingTrace(60, 150, 0.97, 16))).toBe(6);
  });

  // Fourteen ticks of 100 every 100 ms snap to the next step (Lenis stops at
  // about 2.6 s, and the dwell's minimum runs to about 3.8 s); the tail, 300 ms
  // later, decays at the same pace until 4.0 s and so outlasts the minimum.
  const flick = Array.from({ length: 14 }, (_, i) => [i * 100, 100]);
  const tail = Array.from({ length: 24 }, (_, i) => [1700 + i * 100, Math.max(1, Math.round(40 * 0.88 ** i))]);
  const byTime = (trace) => trace.sort((x, y) => x[0] - y[0]);

  it('a momentum tail that runs on past a snap and its dwell is swallowed whole', () => {
    expect(settledStep([...flick, ...tail])).toBe(4);
    expect(state.scrollPosition).toBe(4);
  });

  it('a push rising out of the tail, with no pause, moves the story on', () => {
    const push = Array.from({ length: 5 }, (_, i) => [3850 + i * 100, 100]);
    expect(settledStep(byTime([...flick, ...tail, ...push]))).toBe(5);
  });

  it('input after the tail has paused moves the story on', () => {
    // No larger than the tail's last events, so only the pause can let it in.
    const after = [[4500, 1], [4600, 1], [4700, 1]];
    expect(settledStep([...flick, ...tail, ...after])).toBe(5);
  });

  it('the scroll is the reader\'s again once the tail has gone quiet', () => {
    const t = now;
    play([...flick, ...tail]);
    while (now - t < 4000 + 250) frames(16);
    expect(state.lenis.isStopped).toBe(false);
  });

  it('a gesture begun after the tail has gone quiet moves the story on', () => {
    expect(settledStep([...flick, ...tail])).toBe(4);
    expect(settledStep(flick)).toBe(5);
  });

  it('a key pressed while the tail holds the dwell moves at once', () => {
    const t0 = now;
    play(tail.filter(([t]) => t < 0).concat(flick, tail.filter(([t]) => t < 3850)));
    while (now - t0 < 3850) frames(16);
    expect(state.lenis.isStopped).toBe(true);
    keyboardNav('forward');
    play(tail.filter(([t]) => t >= 3850).map(([t, d]) => [t - 3850, d]));
    while (now - t0 < 3850 + 1300) frames(16);
    expect(state.lenis.animatedScroll / H).toBe(5);
    frames(6000);
    expect(state.lenis.animatedScroll / H).toBe(5);
  });

  /** Play the flick and run frames until its snap stops the scroll; the time it did. */
  function snapped(trace = flick) {
    play(trace);
    const t = now;
    while (!state.lenis.isStopped && now - t < 10000) frames(16);
    expect(state.lenis.isStopped, 'the snap stopped the scroll').toBe(true);
    return now;
  }

  /** Run frames until `ms` after `t`, dispatching each [atMs, dispatch] as it falls due. */
  function runUntil(t, ms, events) {
    const due = [...events];
    while (now - t < ms) {
      while (due.length && due[0][0] <= now - t) due.shift()[1]();
      frames(16);
    }
  }

  const wheelDispatch = (deltaY) => () => window.dispatchEvent(new WheelEvent('wheel', { deltaY, bubbles: true, cancelable: true }));

  it('equal notches after a pause are a new gesture, let in at the dwell\'s minimum', () => {
    const t = snapped();
    const notches = Array.from({ length: 30 }, (_, i) => [950 + i * 100, wheelDispatch(100)]);
    runUntil(t, 1300, notches);
    expect(state.lenis.isStopped).toBe(false);
    runUntil(t, 3950, notches.filter(([at]) => at >= 1300));
    frames(6000);
    expect(state.lenis.animatedScroll / H).toBeGreaterThan(4);
  });

  it('a touch during the dwell is a new gesture, though the wheel tail runs on', () => {
    // The tail runs unbroken across the snap (2.6 s) and past the dwell's
    // minimum (3.8 s) to 4.0 s; only the touch can end the hold.
    // A finger's first moves are a pixel each, no larger than the tail.
    const finger = (type, clientY) => () => {
      const e = new Event(type, { bubbles: true, cancelable: true });
      Object.defineProperty(e, 'targetTouches', { value: [{ clientX: 640, clientY }] });
      window.dispatchEvent(e);
    };
    const events = [...flick, ...tail].map(([at, d]) => [at, wheelDispatch(d)]);
    events.push([3000, finger('touchstart', 300)], [3016, finger('touchmove', 299)],
      [3032, finger('touchmove', 298)]);
    runUntil(now, 3850, events.sort((x, y) => x[0] - y[0]));
    expect(state.lenis.isStopped).toBe(false);
  });

  it('a run begun after a pause, just before the snap lands, is not held as its tail', () => {
    // The flick's snap starts at 1.47 s and lands at 2.59 s; equal notches
    // begin 50 ms before it lands, after a pause, and never stop.
    const t = now;
    const events = [...flick.map(([at, d]) => [at, wheelDispatch(d)]),
      ...Array.from({ length: 40 }, (_, i) => [2542 + i * 100, wheelDispatch(100)])];
    runUntil(t, 2542 + 40 * 100, events);
    frames(6000);
    expect(state.lenis.animatedScroll / H).toBeGreaterThan(4);
  });

  it('a snap after the engine is set up again keeps its whole minimum dwell', () => {
    // A long, slow tail holds snap A's dwell past its minimum (3.8 s) when the
    // engine is set up again at 3.9 s. The tail runs on into the new engine
    // without a pause; its last events come 180 ms apart, long enough for the
    // snap to start (150 ms) and short of a pause (200 ms), so snap B is taken
    // by the same gesture.
    const slow = Array.from({ length: 52 }, (_, i) => [1700 + i * 100, Math.round(60 * 0.99 ** i)]);
    const spaced = Array.from({ length: 6 }, (_, i) => [6880 + i * 180, 30 - i]);
    const t = now;
    const events = [...flick, ...slow, ...spaced].map(([at, d]) => [at, wheelDispatch(d)]);
    runUntil(t, 3900, events);
    expect(state.lenis.isStopped, 'the tail holds snap A').toBe(true);
    getScrollEngineState().lenis.destroy();
    initScrollEngine(STEPS);
    state.lenis = getScrollEngineState().lenis;
    state.lenis.scrollTo(4 * H, { immediate: true });
    const last = spaced[spaced.length - 1][0];
    runUntil(t, last + 16, events.filter(([at]) => at >= 3900));
    while (!state.lenis.isStopped && now - t < last + 3000) frames(16);
    expect(state.lenis.isStopped, 'snap B stopped the scroll').toBe(true);
    // A notch after a pause, no smaller than the last, inside B's minimum.
    const landed = now;
    runUntil(landed, 400, [[250, wheelDispatch(100)]]);
    expect(state.lenis.isStopped).toBe(true);
  });

  it('steady notches the snap takes in its stride are a new gesture, not its tail', () => {
    // 100 every 100 ms to 1.3 s, then 100 every 180 ms: long enough for the snap
    // to start (150 ms), short of a pause (200 ms), and never smaller.
    const steady = Array.from({ length: 30 }, (_, i) => [1480 + i * 180, 100]);
    const t = now;
    runUntil(t, 1480 + 30 * 180, [...flick, ...steady].map(([at, d]) => [at, wheelDispatch(d)]));
    frames(6000);
    expect(state.lenis.animatedScroll / H).toBeGreaterThan(4);
  });

  it('a flick whose last notches arrive while its snap travels keeps its tail', () => {
    // WebKit's spacing of spec h: fourteen notches 155 ms apart, so the snap
    // starts before the last of them, then a decaying tail after a pause.
    const slowFlick = Array.from({ length: 14 }, (_, i) => [i * 155, 100]);
    const lateTail = Array.from({ length: 24 }, (_, i) => [2470 + i * 150, Math.max(1, Math.round(40 * 0.88 ** i))]);
    let startedAt = null;
    const t = now;
    const events = [...slowFlick, ...lateTail].map(([at, d]) => [at, () => {
      wheelDispatch(d)();
      if (startedAt === null && state.isSnapping) startedAt = at;
    }]);
    runUntil(t, 2470 + 24 * 150, events);
    expect(startedAt, 'a notch of the flick arrives after its snap starts').toBeLessThan(2015 + 1);
    frames(6000);
    expect(state.lenis.animatedScroll / H).toBe(4);
  });

  it('a slow steady scroll just under the size rule is the reader\'s 3 s after landing', () => {
    // 100 every 100 ms to 1.3 s, then 99 every 180 ms, then 99.5: never smaller
    // than a tail would be by more than half a pixel, never a pause, never a rise.
    const under = Array.from({ length: 40 }, (_, i) => [1480 + i * 180, i < 20 ? 99 : 99.5]);
    const t = now;
    const due = [...flick, ...under].map(([at, d]) => [at, wheelDispatch(d)]);
    const runTo = (ms) => {
      while (now - t < ms) {
        while (due.length && due[0][0] <= now - t) due.shift()[1]();
        frames(16);
      }
    };
    while (!state.lenis.isStopped && now - t < 5000) runTo(now - t + 16);
    expect(state.lenis.isStopped, 'the snap landed').toBe(true);
    const landed = now - t;
    runTo(landed + 2900);
    expect(state.lenis.isStopped, 'held within the cap').toBe(true);
    runTo(landed + 3050);
    expect(state.lenis.isStopped, 'the reader\'s at the cap').toBe(false);
  });

  it('slow ticks are carried one step forward once the wheel has been idle', () => {
    for (let i = 0; i < 6; i++) {
      play([[0, 100]]);
      frames(300);
    }
    expect(state.lenis.animatedScroll / H).toBeLessThan(4);
    frames(6000);
    expect(state.lenis.animatedScroll / H).toBe(4);
  });
});
