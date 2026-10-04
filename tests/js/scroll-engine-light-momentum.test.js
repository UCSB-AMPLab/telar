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

import { initScrollEngine, getScrollEngineState } from '../../assets/js/telar-story/scroll-engine.js';
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

const decay = (n, first, k, dt) => Array.from({ length: n }, (_, i) => [i * dt, Math.round(first * Math.pow(k, i))]);

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
    const L = state.lenis; console.log('dbg', window instanceof Window, typeof Window, L.dimensions.wrapper === window, L.limit, L.animatedScroll, L.targetScroll, scrollY, L.dimensions.height, L.dimensions.scrollHeight);
    frames(500);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  /** Play a trace, wait out the tail and any carry, and read where the story rests. */
  function rest(trace, idleMs = 6000) {
    play(trace);
    frames(idleMs);
    return state.lenis.animatedScroll / H;
  }

  const raw = (trace) => trace.reduce((a, e) => a + e[1], 0);

  it('a light trace whose total is odd comes to rest on the step it was heading for', () => {
    // 885 raw is a target on a half pixel at a wheel multiplier of 0.5.
    const trace = decay(30, 70, 0.93, 16);
    expect(raw(trace) % 2).toBe(1);
    expect(rest(trace)).toBe(4);
    expect(state.scrollPosition).toBe(4);
    expect(document.querySelector('.card-stack').classList.contains('is-scrubbing')).toBe(false);
  });

  it('a light trace whose total is even comes to rest on the same step', () => {
    const trace = decay(30, 70, 0.93, 16);
    trace[0][1] += 1;
    expect(raw(trace) % 2).toBe(0);
    expect(rest(trace)).toBe(4);
  });

  it('a light trace backwards is carried to the step behind', () => {
    const trace = decay(30, -70, 0.93, 16);
    expect(raw(trace) % 2).toBe(-1);
    expect(rest(trace)).toBe(2);
  });

  it('a trackpad flick lands where the snap takes it', () => {
    expect(rest(decay(110, 90, 0.96, 16))).toBe(5);
  });

  it('a hard flick lands where the snap takes it', () => {
    expect(rest(decay(60, 150, 0.97, 16))).toBe(6);
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
