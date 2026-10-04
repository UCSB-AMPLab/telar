/**
 * Tests for the scroll engine and the previous/next buttons beside it.
 *
 * In an embed the engine moves the story for every input, the buttons
 * included, and hands each step it enters to the buttons. These drive the
 * engine with the harness's mocked Lenis and read what it tells the buttons,
 * where a button move is heading, and what a refused or interrupted move
 * leaves behind.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ── Mocks ─────────────────────────────────────────────────────────────────────
// Each factory imports the harness, so the engine and this suite share its spies.

vi.mock('lenis', async () => (await import('./scroll-engine-harness.js')).lenisModule);
vi.mock('lenis/snap', async () => (await import('./scroll-engine-harness.js')).snapModule);
vi.mock('../../assets/js/telar-story/card-pool.js',
  async () => (await import('./scroll-engine-harness.js')).cardPoolModule);
vi.mock('../../assets/js/telar-story/iiif-card.js',
  async () => (await import('./scroll-engine-harness.js')).iiifCardModule);
vi.mock('../../assets/js/telar-story/navigation.js',
  async () => (await import('./scroll-engine-harness.js')).navigationModule);
vi.mock('../../assets/js/telar-story/viewer.js',
  async () => (await import('./scroll-engine-harness.js')).viewerModule);

// ── Imports (after mocks) ─────────────────────────────────────────────────────

import { advanceToStep, initScrollEngine, getScrollEngineState, keyboardNav } from '../../assets/js/telar-story/scroll-engine.js';
import * as engine from '../../assets/js/telar-story/scroll-engine.js';
import { navigateToIntro, navigateToStep } from '../../assets/js/telar-story/deep-link.js';
import { state } from '../../assets/js/telar-story/state.js';
import {
  mocks, engineStory, stubEngineGlobals, readerTakesOver, wheelEvent, scrollFrame, resetState,
  modelLenis, landMove, restAt,
} from './scroll-engine-harness.js';

// ── The buttons beside the engine (embed mode) ───────────────────────────────
//
// Every step the engine puts the story on is handed to the buttons, whatever
// moved it, the buttons' own moves included: they show where the reader is.

describe('the engine tells the buttons where the story is', () => {
  beforeEach(() => {
    engineStory(5);
    mocks.lenisScrollTo.mockClear();
    mocks.mockFollowEngine.mockClear();
    mocks.mockGoToStep.mockClear();
    resetState({ currentIndex: -1 });

    stubEngineGlobals();

    initScrollEngine(5);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('a button move states the step on landing, not at the tap', () => {
    // The counter and the active card say where the reader is, and a tap
    // leaving the intro reaches step 1 only when the scroll lands on it.
    state.lenis = getScrollEngineState().lenis;
    mocks.mockUpdateViewerInfo.mockClear();
    mocks.mockActivateCard.mockClear();
    advanceToStep(0);
    scrollFrame(0.5);
    scrollFrame(0.99);
    expect(mocks.mockUpdateViewerInfo).not.toHaveBeenCalled();
    expect(mocks.mockActivateCard).not.toHaveBeenCalled();
    expect(state.currentIndex).toBe(-1);

    scrollFrame(1);
    expect(mocks.mockUpdateViewerInfo).toHaveBeenLastCalledWith(0);
    expect(mocks.mockActivateCard).toHaveBeenLastCalledWith(0, 'forward');
    expect(state.currentIndex).toBe(0);
  });

  it('on a step the scroll reaches: a deep link, a contents link or the wheel', () => {
    scrollFrame(3);
    expect(mocks.mockFollowEngine).toHaveBeenLastCalledWith(2);
  });

  it('on the intro the scroll returns to', () => {
    scrollFrame(3);
    scrollFrame(0.6);
    expect(mocks.mockGoToStep).toHaveBeenCalledWith(-1, 'backward');
    expect(mocks.mockFollowEngine).toHaveBeenLastCalledWith(-1);
  });

  it('on the step a key press is going to', () => {
    keyboardNav('forward');
    expect(mocks.mockFollowEngine).toHaveBeenLastCalledWith(0);
  });

  it('on the intro a key press is going to', () => {
    scrollFrame(1);
    mocks.mockFollowEngine.mockClear();
    keyboardNav('backward');
    expect(mocks.mockFollowEngine).toHaveBeenLastCalledWith(-1);
  });

  it('on each step a button move crosses, and not before', () => {
    scrollFrame(2);                         // step 1
    mocks.mockFollowEngine.mockClear();
    state.lenis = getScrollEngineState().lenis;
    advanceToStep(3);                       // two taps, heading for step 3
    expect(mocks.mockFollowEngine).not.toHaveBeenCalled();
    scrollFrame(3);                         // passing step 2
    scrollFrame(4);                         // landing on step 3
    expect(mocks.mockFollowEngine.mock.calls).toEqual([[2], [3]]);
  });

  it('again once the reader takes the scroll from a button move', () => {
    state.lenis = getScrollEngineState().lenis;
    advanceToStep(3);
    readerTakesOver(wheelEvent());
    scrollFrame(2);
    expect(mocks.mockFollowEngine).toHaveBeenLastCalledWith(1);
  });
});

// ── A button move the engine cannot make, or does not finish ─────────────────
//
// The buttons show where the engine is, never where a tap hoped to take it, so
// a move that is refused or cut short leaves nothing behind for them to be
// wrong about, and every path that ends a move stands its token down.

describe('a button move refused or cut short', () => {
  const vh = () => window.innerHeight;

  beforeEach(() => {
    engineStory(5);
    mocks.lenisScrollTo.mockReset();
    mocks.mockFollowEngine.mockClear();
    mocks.mockGoToStep.mockClear();
    resetState({ currentIndex: -1, viewerPlates: {} });
    stubEngineGlobals();
    vi.useFakeTimers();
    initScrollEngine(5);
    state.lenis = getScrollEngineState().lenis;
    // An immediate jump emits its scroll frame at once, as Lenis does.
    mocks.lenisScrollTo.mockImplementation((px, opts = {}) => {
      if (opts.immediate) scrollFrame(px / vh());
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  /** Land on a step by the wheel, and let the snap start its dwell. */
  function snapOnto(position) {
    scrollFrame(position);
    mocks.snapConstructorArgs.at(-1).opts.onSnapComplete();
  }

  it('a tap during the post-snap dwell ends the dwell and moves', () => {
    snapOnto(2);                                  // step 1, scroll stopped
    const { lenis } = getScrollEngineState();
    expect(lenis.isStopped).toBe(true);
    let stoppedWhenAsked = null;
    mocks.lenisScrollTo.mockImplementation(() => { stoppedWhenAsked = lenis.isStopped; });

    const moved = advanceToStep(2);
    expect(stoppedWhenAsked, 'Lenis refuses a scrollTo while stopped').toBe(false);
    expect(mocks.lenisScrollTo).toHaveBeenCalledWith(3 * vh(), expect.any(Object));
    expect(moved).toBe(true);
  });

  it('a tap while a panel opened during the dwell is refused', () => {
    snapOnto(2);                                  // step 1, scroll stopped
    state.isPanelOpen = true;                     // a panel opens over it
    const moved = advanceToStep(2);
    expect(mocks.lenisScrollTo).not.toHaveBeenCalled();
    expect(getScrollEngineState().lenis.isStopped).toBe(true);
    expect(moved).toBe(false);
  });

  it('a tap while a panel holds the scroll is refused and leaves nothing in flight', () => {
    scrollFrame(2);
    const { lenis } = getScrollEngineState();
    lenis.stop();                                 // a panel, not a dwell
    const moved = advanceToStep(2);
    expect(mocks.lenisScrollTo).not.toHaveBeenCalled();
    expect(moved).toBe(false);
    expect(engine.buttonHeading()).toBe(1);
  });

  it('a later tap goes on from where a button move is heading', () => {
    scrollFrame(2);
    advanceToStep(2);
    expect(engine.buttonHeading()).toBe(2);
  });

  it('Back to Start before a button move lands, then a contents link, puts the buttons on the step', () => {
    advanceToStep(0);                             // next from the intro, in flight
    navigateToIntro();
    expect(engine.buttonHeading(), 'next after Back to Start leaves for step 1').toBe(-1);
    mocks.mockFollowEngine.mockClear();
    navigateToStep(3);
    expect(mocks.mockFollowEngine).toHaveBeenLastCalledWith(2);
    expect(engine.buttonHeading()).toBe(2);
  });

  it('Back to Start jumps the scroll through Lenis, which the page\'s smooth scrolling cannot delay', () => {
    // A scrollTop write is animated under the page's scroll-behavior: smooth,
    // and WebKit can leave it unfinished, with the story on the intro and the
    // scroll still on the step. Lenis writes with behavior: instant.
    scrollFrame(3);
    navigateToIntro();
    expect(mocks.lenisScrollTo).toHaveBeenCalledWith(0, expect.objectContaining({ immediate: true, force: true }));
    expect(state.currentIndex).toBe(-1);
    expect(state.scrollPosition).toBe(0);
  });

  it('a tap during a key press\'s move takes over from it, and the steps it crosses are entered', () => {
    keyboardNav('forward');                       // heading for step 0
    expect(engine.buttonHeading()).toBe(0);
    advanceToStep(1);
    mocks.mockFollowEngine.mockClear();
    scrollFrame(2);
    expect(state.currentIndex).toBe(1);
    expect(mocks.mockFollowEngine).toHaveBeenLastCalledWith(1);
  });

  it('a contents link during a button move stands the move down', () => {
    scrollFrame(2);
    advanceToStep(2);                             // heading for step 2
    navigateToStep(5);
    expect(state.currentIndex).toBe(4);
    expect(engine.buttonHeading()).toBe(4);
  });

  it('the wheel taking over a button move before it crosses lets the gesture be carried', () => {
    advanceToStep(0);
    readerTakesOver(wheelEvent({ deltaY: 120 }));
    scrollFrame(0.2);
    scrollFrame(0.4);
    mocks.lenisScrollTo.mockClear();
    vi.advanceTimersByTime(150);                  // the gesture's settle
    expect(mocks.lenisScrollTo).toHaveBeenCalledWith(1 * vh(), expect.any(Object));
  });

  it('the wheel taking over a button move leaves the buttons on the engine\'s step', () => {
    advanceToStep(0);
    readerTakesOver(wheelEvent({ deltaY: 120 }));
    scrollFrame(0.4);
    expect(engine.buttonHeading()).toBe(-1);
  });

  it('a resize that lands a button move stands it down', () => {
    scrollFrame(2);
    advanceToStep(2);
    getScrollEngineState().lenis.isScrolling = 'smooth';
    vi.stubGlobal('innerHeight', 700);
    window.dispatchEvent(new Event('resize'));
    vi.advanceTimersByTime(100);
    expect(state.currentIndex).toBe(2);           // landed where the tap was going
    expect(mocks.mockFollowEngine).toHaveBeenLastCalledWith(2);
    getScrollEngineState().lenis.isScrolling = false;
    expect(engine.buttonHeading()).toBe(2);
    expect(advanceToStep(3)).toBe(true);
    expect(engine.buttonHeading()).toBe(3);
  });
});

// ── A move to the offset Lenis already holds as its target ───────────────────
//
// Lenis skips a scrollTo to its current target and calls the completion at
// once, without stopping a move in flight. Before a programmatic move's first
// frame its target is still the offset it left, so a tap or a link back there
// would report success while the earlier move ran on to its own landing.

describe('a move back to where a move in flight left from', () => {
  beforeEach(() => {
    engineStory(5);
    mocks.mockFollowEngine.mockClear();
    resetState({ currentIndex: -1 });
    stubEngineGlobals();
    initScrollEngine(5);
    state.lenis = modelLenis();
    restAt(2);                                    // on step 1
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('a tap back from a key press before its first frame lands where the tap asked', () => {
    keyboardNav('forward');                       // the story and buttons on step 2
    expect(state.currentIndex).toBe(2);
    expect(advanceToStep(engine.buttonHeading() - 1)).toBe(true);
    landMove();
    expect(state.currentIndex).toBe(1);
    expect(mocks.mockFollowEngine).toHaveBeenLastCalledWith(1);
    expect(getScrollEngineState().lenis.animatedScroll).toBe(2 * window.innerHeight);
  });

  it('a contents link to the step a key press is leaving lands on it', () => {
    keyboardNav('forward');
    navigateToStep(2);                            // step index 1, at the offset left from
    landMove();
    expect(state.currentIndex).toBe(1);
    expect(mocks.mockFollowEngine).toHaveBeenLastCalledWith(1);
  });

  it('a tap to a new offset during a key press still replaces its move', () => {
    keyboardNav('forward');
    advanceToStep(3);
    landMove();
    expect(state.currentIndex).toBe(3);
  });
});
