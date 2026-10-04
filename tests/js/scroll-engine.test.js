/**
 * Tests for Telar Story – Scroll Engine
 *
 * Tests the pure logic functions that can be tested without a real DOM or
 * Lenis. DOM-interacting functions (initScrollEngine) are tested via mock.
 *
 * Covers:
 *   - updateScrollPosition: position model, boundary crossings, clamping
 *   - advanceToStep: guard for out-of-range indices
 *   - initScrollEngine: Lenis constructor options, snap configuration
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ── Hoisted mocks ─────────────────────────────────────────────────────────────
// vi.hoisted() runs before vi.mock() factories, ensuring all variables are
// initialized before the factory closures capture them.

const mocks = vi.hoisted(() => {
  // Lenis instance methods
  const lenisOn = vi.fn();
  const lenisRaf = vi.fn();
  const lenisScrollTo = vi.fn();
  const lenisResize = vi.fn();

  // Snap instance methods
  const snapAdd = vi.fn(() => vi.fn()); // returns a remover function
  const snapRemove = vi.fn();
  const snapResize = vi.fn();

  // Track constructor calls
  const lenisConstructorArgs = [];
  const snapConstructorArgs = [];

  // Lenis constructor — must be a regular function to work with `new`
  function MockLenis(opts) {
    lenisConstructorArgs.push(opts);
    this.on = lenisOn;
    this.raf = lenisRaf;
    this.scrollTo = lenisScrollTo;
    this.resize = lenisResize;
    this.stop = vi.fn(function () { this.isStopped = true; });
    this.start = vi.fn(function () { this.isStopped = false; });
    this.isStopped = false;
    this.isScrolling = false;
    this.animatedScroll = 0;
    this.targetScroll = 0;
  }

  // Snap constructor — must be a regular function to work with `new`
  function MockSnap(lenis, opts) {
    snapConstructorArgs.push({ lenis, opts });
    this.add = snapAdd;
    this.remove = snapRemove;
    this.resize = snapResize;
    this.next = vi.fn();
    this.previous = vi.fn();
  }

  const mockActivateCard = vi.fn();
  const mockSettleCards = vi.fn();
  const mockGoToStep = vi.fn();
  const mockInitKeyboardNavigation = vi.fn();
  const mockInitializeLoadingShimmer = vi.fn();

  return {
    MockLenis,
    MockSnap,
    lenisOn,
    lenisScrollTo,
    lenisResize,
    snapAdd,
    snapRemove,
    lenisConstructorArgs,
    snapConstructorArgs,
    mockActivateCard,
    mockSettleCards,
    mockGoToStep,
    mockInitKeyboardNavigation,
    mockInitializeLoadingShimmer,
  };
});

vi.mock('lenis', () => ({ default: mocks.MockLenis }));
vi.mock('lenis/snap', () => ({ default: mocks.MockSnap }));

vi.mock('../../assets/js/telar-story/card-pool.js', () => ({
  activateCard: mocks.mockActivateCard,
  setCardProgress: vi.fn(),
  settleCards: mocks.mockSettleCards,
}));

vi.mock('../../assets/js/telar-story/iiif-card.js', () => ({
  lerpIiifPosition: vi.fn(),
  snapIiifToPosition: vi.fn(),
  animateIiifToPosition: vi.fn(),
  createIiifCard: vi.fn(),
  getOrCreateIiifCard: vi.fn(),
  activateIiifCard: vi.fn(),
  destroyIiifCard: vi.fn(),
}));

vi.mock('../../assets/js/telar-story/navigation.js', () => ({
  goToStep: mocks.mockGoToStep,
  initKeyboardNavigation: mocks.mockInitKeyboardNavigation,
  updateViewerInfo: vi.fn(),
}));

vi.mock('../../assets/js/telar-story/viewer.js', () => ({
  initializeLoadingShimmer: mocks.mockInitializeLoadingShimmer,
  buildObjectsIndex: vi.fn(),
  prefetchStoryManifests: vi.fn(),
  initializeCredits: vi.fn(),
  getManifestUrl: vi.fn(),
  updateObjectCredits: vi.fn(),
  showViewerSkeletonState: vi.fn(),
}));

// ── Imports (after mocks) ─────────────────────────────────────────────────────

import { updateScrollPosition, advanceToStep, initScrollEngine, getScrollEngineState, keyboardNav } from '../../assets/js/telar-story/scroll-engine.js';
import { lerpIiifPosition } from '../../assets/js/telar-story/iiif-card.js';
import { state } from '../../assets/js/telar-story/state.js';

// ── Helpers ────────────────────────────────────────────────────────────────────

function resetState(overrides = {}) {
  state.steps = Array.from({ length: 5 }, (_, i) => ({ index: i }));
  state.currentIndex = -1;
  state.scrollPosition = 0;
  state.scrollProgress = 0;
  state.isSnapping = false;
  state.lenis = null;
  state.snap = null;
  Object.assign(state, overrides);
}

// ── updateScrollPosition: position model ──────────────────────────────────────

describe('updateScrollPosition', () => {
  beforeEach(() => {
    resetState({ currentIndex: 0 });
    mocks.mockActivateCard.mockClear();
    mocks.mockGoToStep.mockClear();
    lerpIiifPosition.mockClear();
  });

  // Position model: raw position P maps to content step P-1.
  // Position 0–1 = intro zone, position 1 = step 0, position 2 = step 1, etc.

  it('position 3.3 (content step 2.3) produces scrollPosition ~3.3 and scrollProgress ~0.3', () => {
    resetState({ currentIndex: 2 });
    updateScrollPosition(3.3);
    expect(state.scrollPosition).toBeCloseTo(3.3);
    expect(state.scrollProgress).toBeCloseTo(0.3);
  });

  it('position 1.0 (content step 0) produces scrollPosition=1 and scrollProgress=0', () => {
    resetState({ currentIndex: 0 });
    updateScrollPosition(1.0);
    expect(state.scrollPosition).toBe(1);
    expect(state.scrollProgress).toBe(0);
  });

  it('negative position enters intro zone — scrollProgress=0', () => {
    resetState({ currentIndex: -1 });
    updateScrollPosition(-1);
    expect(state.scrollPosition).toBe(-1);
    expect(state.scrollProgress).toBe(0);
  });

  it('position above steps.length clamps content to max step', () => {
    resetState({ currentIndex: 4 });
    updateScrollPosition(99);
    // steps.length = 5, max content = 4, so step index clamps to 4
    expect(state.scrollPosition).toBe(99);
    expect(state.currentIndex).toBe(4);
  });

  it('calls activateCard when stepIndex crosses an integer boundary (forward)', () => {
    resetState({ currentIndex: 1 });
    // Position 3.0 = content step 2 (forward from 1)
    updateScrollPosition(3.0);
    expect(mocks.mockActivateCard).toHaveBeenCalledWith(2, 'forward');
    expect(state.currentIndex).toBe(2);
  });

  it('calls activateCard when stepIndex crosses an integer boundary (backward)', () => {
    resetState({ currentIndex: 3 });
    // Position 3.0 = content step 2 (backward from 3)
    updateScrollPosition(3.0);
    expect(mocks.mockActivateCard).toHaveBeenCalledWith(2, 'backward');
    expect(state.currentIndex).toBe(2);
  });

  it('does NOT call activateCard when stepIndex is unchanged', () => {
    resetState({ currentIndex: 2 });
    // Position 3.5 = content step 2 at 50% — same step index
    updateScrollPosition(3.5);
    expect(mocks.mockActivateCard).not.toHaveBeenCalled();
  });

  it('calls activateCard (not goToStep) when scrolling backward from step 1 to step 0', () => {
    // Position 1.01 = content step 0 (backward from step 1).
    // Intro guard checks position < 1; 1.01 >= 1 so guard does NOT fire.
    resetState({ currentIndex: 1 });
    updateScrollPosition(1.01);
    expect(mocks.mockGoToStep).not.toHaveBeenCalled();
    expect(mocks.mockActivateCard).toHaveBeenCalledWith(0, 'backward');
  });

  it('feeds lerpIiifPosition the FILTERED state.stepsData, not unfiltered window.storyData.steps', () => {
    // stepIndex is filtered-space (drives state.stepToScene); passing the
    // unfiltered global would mis-index on stories that carry a _metadata row.
    resetState({ currentIndex: 2 });
    const filtered = [
      { object: 'fig1', x: '0.5',  y: '0.5',  zoom: '1' },
      { object: 'fig1', x: '0.25', y: '0.35', zoom: '2.5' },
      { object: 'fig1', x: '0.75', y: '0.3',  zoom: '3' },
    ];
    state.stepsData = filtered;
    // The unfiltered global has a leading metadata row → indices are offset by 1.
    window.storyData = { steps: [{ _metadata: true }, ...filtered] };

    updateScrollPosition(3.3); // content step 2, progress 0.3

    expect(lerpIiifPosition).toHaveBeenCalled();
    const args = lerpIiifPosition.mock.calls.at(-1);
    expect(args[2]).toBe(filtered);                       // filtered array passed through
    expect(args[2]).not.toBe(window.storyData.steps);     // never the unfiltered global
  });
});

// ── advanceToStep: guards ─────────────────────────────────────────────────────

describe('advanceToStep', () => {
  beforeEach(() => {
    resetState({ currentIndex: 0 });
    // Inject a mock lenis instance with a scrollTo spy
    const mockLenis = { scrollTo: vi.fn() };
    state.lenis = mockLenis;
  });

  it('does nothing if targetIndex < 0', () => {
    advanceToStep(-1);
    expect(state.lenis.scrollTo).not.toHaveBeenCalled();
  });

  it('does nothing if targetIndex >= steps.length', () => {
    advanceToStep(5);
    expect(state.lenis.scrollTo).not.toHaveBeenCalled();
  });

  it('calls lenis.scrollTo with correct pixel target (+1 for intro offset)', () => {
    advanceToStep(2);
    // targetPx = (targetIndex + 1) * vh to account for intro at position 0
    // The pace of the move is tuned as one number for every programmatic
    // path, so this pins the target and leaves the duration to the pace.
    expect(state.lenis.scrollTo).toHaveBeenCalledWith(
      3 * window.innerHeight,
      expect.objectContaining({ duration: expect.any(Number) })
    );
  });

  it('calls lenis.scrollTo with an ease-out cubic easing function', () => {
    advanceToStep(1);
    const [, options] = state.lenis.scrollTo.mock.calls[0];
    expect(typeof options.easing).toBe('function');
    // ease-out cubic: f(0)=0, f(1)=1, f(0.5)>0.5 (concave — fast start, slow end)
    expect(options.easing(0)).toBeCloseTo(0);
    expect(options.easing(1)).toBeCloseTo(1);
    expect(options.easing(0.5)).toBeGreaterThan(0.5);
  });
});

// ── getScrollEngineState ──────────────────────────────────────────────────────

describe('getScrollEngineState', () => {
  it('returns current scroll position and progress', () => {
    state.scrollPosition = 1.5;
    state.scrollProgress = 0.5;
    const result = getScrollEngineState();
    expect(result.position).toBe(1.5);
    expect(result.progress).toBe(0.5);
  });
});

// ── initScrollEngine: Lenis constructor options ───────────────────────────────

describe('initScrollEngine', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div class="scroll-surface"></div>
      <div class="card-stack">
        <div class="story-step"></div>
        <div class="story-step"></div>
        <div class="story-step"></div>
      </div>
    `;
    // Clear constructor arg tracking arrays
    mocks.lenisConstructorArgs.length = 0;
    mocks.snapConstructorArgs.length = 0;
    mocks.snapAdd.mockClear();
    mocks.mockInitKeyboardNavigation.mockClear();
    state.currentIndex = -1;
    state.lenis = null;
    state.snap = null;

    vi.stubGlobal('requestAnimationFrame', vi.fn());

    // Stub window.matchMedia — jsdom does not implement it.
    // Default: prefers-reduced-motion does NOT match (standard user).
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })));

    try {
      Object.defineProperty(history, 'scrollRestoration', {
        writable: true,
        value: 'auto',
        configurable: true,
      });
    } catch (_) {
      // Already writable in this environment
    }
  });

  it('creates Lenis with correct options (lerp, wheelMultiplier, autoRaf)', () => {
    initScrollEngine(3);
    expect(mocks.lenisConstructorArgs.length).toBe(1);
    const opts = mocks.lenisConstructorArgs[0];
    expect(opts.lerp).toBe(0.06);
    expect(opts.smoothWheel).toBe(true);
    expect(opts.wheelMultiplier).toBe(0.5);
    expect(opts.autoRaf).toBe(false);
  });

  it('creates Snap with type lock', () => {
    initScrollEngine(3);
    expect(mocks.snapConstructorArgs.length).toBe(1);
    expect(mocks.snapConstructorArgs[0].opts.type).toBe('lock');
  });

  it('calls snap.add once per position (intro + steps)', () => {
    initScrollEngine(3);
    // totalPositions = stepCount + 1 (intro at position 0)
    expect(mocks.snapAdd).toHaveBeenCalledTimes(4);
  });

  it('stores lenis and snap on state', () => {
    initScrollEngine(3);
    expect(state.lenis).not.toBeNull();
    expect(state.snap).not.toBeNull();
  });

  it('calls initKeyboardNavigation', () => {
    initScrollEngine(3);
    expect(mocks.mockInitKeyboardNavigation).toHaveBeenCalled();
  });

  it('sets scroll surface height to (stepCount + 1) * window.innerHeight (intro + steps)', () => {
    initScrollEngine(3);
    const surface = document.querySelector('.scroll-surface');
    expect(surface.style.height).toBe(`${4 * window.innerHeight}px`);
  });

  it('uses prevent option that guards open-panel descendants', () => {
    initScrollEngine(3);
    // Get the prevent fn from the Lenis constructor call
    const opts = mocks.lenisConstructorArgs[0];
    expect(typeof opts.prevent).toBe('function');

    // Node inside a Bootstrap offcanvas panel — should be prevented
    // (matches the runtime selectors in scroll-engine.js: `.offcanvas` and
    // `[data-telar-panel]`, the real panel markup from _includes/panels.html).
    const offcanvas = document.createElement('div');
    offcanvas.className = 'offcanvas';
    const offcanvasInner = document.createElement('div');
    offcanvas.appendChild(offcanvasInner);
    document.body.appendChild(offcanvas);
    expect(opts.prevent(offcanvasInner)).toBe(true);

    // Node inside a [data-telar-panel] element — should also be prevented
    const telarPanel = document.createElement('div');
    telarPanel.setAttribute('data-telar-panel', '');
    const panelInner = document.createElement('div');
    telarPanel.appendChild(panelInner);
    document.body.appendChild(telarPanel);
    expect(opts.prevent(panelInner)).toBe(true);

    // Node outside any panel — should NOT be prevented
    const regular = document.createElement('div');
    document.body.appendChild(regular);
    expect(opts.prevent(regular)).toBe(false);
  });
});

// ── keyboardNav: the way back to the intro ────────────────────────────────────
//
// Position 0 is the intro; the keyboard's backward target from step 0 is
// therefore position 0, which carries no card to activate. The intro zone in
// updateScrollPosition cannot cover for it: keyboardNavInFlight suppresses that
// path for the whole scroll animation. So the keyboard has to run the intro
// restore itself, through the one call the scroll and button paths both make.

describe('keyboardNav — arriving at the intro', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div class="scroll-surface"></div>
      <div class="card-stack">
        <div class="story-step"></div>
        <div class="story-step"></div>
        <div class="story-step"></div>
      </div>
    `;
    mocks.mockGoToStep.mockClear();
    mocks.mockActivateCard.mockClear();
    mocks.lenisScrollTo.mockClear();
    resetState({ currentIndex: 0 });

    vi.stubGlobal('requestAnimationFrame', vi.fn());
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query) => ({
      matches: false, media: query, onchange: null,
      addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })));
    try {
      Object.defineProperty(history, 'scrollRestoration',
        { writable: true, value: 'auto', configurable: true });
    } catch (_) { /* already writable here */ }

    initScrollEngine(3);
    state.currentIndex = 0;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  /** Park the engine's Lenis at a scroll position, in whole viewport heights. */
  function parkAt(position) {
    const { lenis } = getScrollEngineState();
    lenis.animatedScroll = position * window.innerHeight;
  }

  it('restores the intro when the target is position 0', () => {
    parkAt(1); // step 0
    keyboardNav('backward');
    expect(mocks.mockGoToStep).toHaveBeenCalledWith(-1, 'backward');
  });

  it('scrolls to the top of the surface on the same press', () => {
    parkAt(1);
    keyboardNav('backward');
    expect(mocks.lenisScrollTo).toHaveBeenCalledWith(0, expect.objectContaining({ force: true }));
  });

  it('activates the step rather than the intro when the target is a step', () => {
    parkAt(2); // step 1
    state.currentIndex = 1;
    keyboardNav('backward');
    expect(mocks.mockActivateCard).toHaveBeenCalledWith(0, 'backward');
    expect(mocks.mockGoToStep).not.toHaveBeenCalled();
  });

  it('does not restore the intro a second time once it is the current position', () => {
    parkAt(0);
    state.currentIndex = -1;
    keyboardNav('backward');
    expect(mocks.mockGoToStep).not.toHaveBeenCalled();
  });
});

// ── keyboardNav: a press arriving while a move is still travelling ────────────
//
// The move takes 1.2 s, so a reader moving at any ordinary pace presses again
// before it lands. The position mid-move is one the engine is driving towards
// a landing it already chose, so reading it as a place the reader left the
// scroll makes the press re-issue the move already running — the reader presses
// and nothing happens, and waiting does not recover it. A press therefore steps
// from the landing while the keyboard owns the move, and from the position
// whenever the scroll is the reader's.
//
// Lenis calls onComplete through the scrollTo mock's own caller, so a move
// started here stays in flight for the rest of the test, which is the state
// these cases are about.

describe('keyboardNav — a press while a move is in flight', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div class="scroll-surface"></div>
      <div class="card-stack">
        <div class="story-step"></div>
        <div class="story-step"></div>
        <div class="story-step"></div>
        <div class="story-step"></div>
        <div class="story-step"></div>
      </div>
    `;
    mocks.lenisScrollTo.mockClear();
    mocks.mockActivateCard.mockClear();
    mocks.mockGoToStep.mockClear();
    resetState({ currentIndex: -1 });

    vi.stubGlobal('requestAnimationFrame', vi.fn());
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query) => ({
      matches: false, media: query, onchange: null,
      addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })));
    try {
      Object.defineProperty(history, 'scrollRestoration',
        { writable: true, value: 'auto', configurable: true });
    } catch (_) { /* already writable here */ }

    initScrollEngine(5);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  /** Where the last scroll the engine asked for was going, in viewports. */
  function lastTarget() {
    const calls = mocks.lenisScrollTo.mock.calls;
    return calls.length ? calls[calls.length - 1][0] / window.innerHeight : null;
  }

  /** Park Lenis part way through a move, as it is when a second press lands. */
  function partWayTo(position) {
    const { lenis } = getScrollEngineState();
    lenis.animatedScroll = (position - 0.02) * window.innerHeight;
  }

  it('ends a post-snap dwell, so the scroll is the reader\'s again at once', () => {
    vi.useFakeTimers();
    try {
      const { lenis } = getScrollEngineState();
      lenis.stop = vi.fn();
      lenis.start = vi.fn();
      // The dwell a snap leaves behind: Lenis stopped, a timer to restart it.
      mocks.snapConstructorArgs.at(-1).opts.onSnapComplete();
      expect(lenis.stop).toHaveBeenCalledTimes(1);

      keyboardNav('forward');
      expect(lenis.start).toHaveBeenCalledTimes(1);

      // The dwell's own restart is cancelled, not left to fire later, and it
      // is over: the next press finds no dwell to end.
      vi.advanceTimersByTime(10_000);
      keyboardNav('forward');
      expect(lenis.start).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('takes the second press to the step after the one in flight', () => {
    keyboardNav('forward');
    expect(lastTarget()).toBe(1);

    partWayTo(1);
    keyboardNav('forward');
    expect(lastTarget()).toBe(2);
  });

  it('counts every press of a burst', () => {
    for (let i = 0; i < 4; i++) {
      keyboardNav('forward');
      partWayTo(i + 1);
    }
    expect(lastTarget()).toBe(4);
  });

  it('activates each step the burst passes, so none is skipped', () => {
    for (let i = 0; i < 4; i++) {
      keyboardNav('forward');
      partWayTo(i + 1);
    }
    const activated = mocks.mockActivateCard.mock.calls.map(([index]) => index);
    expect(activated).toEqual([0, 1, 2, 3]);
  });

  it('turns a burst around from its landing, not from the scroll behind it', () => {
    // Pressed fast enough that the scroll is still most of three steps behind
    // the landing, which is where the two readings part company: back from the
    // landing is step 2, back from the position is the intro.
    keyboardNav('forward');
    keyboardNav('forward');
    keyboardNav('forward');
    expect(lastTarget()).toBe(3);

    const { lenis } = getScrollEngineState();
    lenis.animatedScroll = 0.4 * window.innerHeight;
    keyboardNav('backward');
    expect(lastTarget()).toBe(2);
  });

  it('leaves the move running when the press cannot go further', () => {
    const { lenis } = getScrollEngineState();
    lenis.animatedScroll = 4 * window.innerHeight;
    keyboardNav('forward');          // to position 5, the last
    expect(lastTarget()).toBe(5);

    partWayTo(5);
    const before = mocks.lenisScrollTo.mock.calls.length;
    keyboardNav('forward');
    expect(mocks.lenisScrollTo.mock.calls.length).toBe(before);
  });

  it('reads the position again once the scroll is the reader\'s', () => {
    keyboardNav('forward');
    partWayTo(1);

    // The reader's own input takes the scroll, so the landing the keyboard
    // chose is no longer an account of where the story is going.
    const onVirtualScroll = mocks.lenisOn.mock.calls
      .find(([event]) => event === 'virtual-scroll')[1];
    onVirtualScroll();

    const { lenis } = getScrollEngineState();
    lenis.animatedScroll = 2.4 * window.innerHeight;
    keyboardNav('forward');
    expect(lastTarget()).toBe(3);   // completes the step the reader stopped in
  });
});

// ── The reader taking the scroll back from a move in flight ───────────────────
//
// A keyboard move raises three guards for as long as it travels: the cards are
// activated by the move rather than by the scroll, the intro is not settled,
// and the scrub does not close. All three come down in the move's onComplete,
// which is the only place they can come down from — and Lenis never calls it
// when raw input arrives mid-move. `onVirtualScroll` either stops the running
// animation outright (`animate.stop()`, which calls neither callback) or
// replaces it with the reader's own `scrollTo`, and a superseded animation's
// onComplete is gone with it.
//
// So the engine stands the move down where the takeover is seen, or the guards
// stay up for the rest of the reader's session: cards that never change with
// the scroll, an intro that never settles, and a gesture that stops wherever
// its last frame left it.

describe('a move the reader interrupts with the scroll', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div class="scroll-surface"></div>
      <div class="card-stack">
        <div class="story-step"></div>
        <div class="story-step"></div>
        <div class="story-step"></div>
        <div class="story-step"></div>
        <div class="story-step"></div>
      </div>
    `;
    mocks.lenisScrollTo.mockClear();
    mocks.mockActivateCard.mockClear();
    mocks.mockSettleCards.mockClear();
    mocks.mockGoToStep.mockClear();
    resetState({ currentIndex: -1 });

    vi.stubGlobal('requestAnimationFrame', vi.fn());
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query) => ({
      matches: false, media: query, onchange: null,
      addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })));
    try {
      Object.defineProperty(history, 'scrollRestoration',
        { writable: true, value: 'auto', configurable: true });
    } catch (_) { /* already writable here */ }

    initScrollEngine(5);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  /** The listener Lenis calls the moment raw input arrives. */
  function readerTakesOver(payload) {
    mocks.lenisOn.mock.calls.find(([event]) => event === 'virtual-scroll')[1](payload);
  }

  /** A wheel gesture as Lenis reports one, with the fields the filter reads. */
  const wheelEvent = (over = {}) => ({
    deltaX: 0, deltaY: -120,
    event: { ctrlKey: false, composedPath: () => [] },
    ...over,
  });

  /** One frame of Lenis's smoothed output, at `position` viewports. */
  function scrollFrame(position) {
    const { lenis } = getScrollEngineState();
    lenis.animatedScroll = position * window.innerHeight;
    mocks.lenisOn.mock.calls.find(([event]) => event === 'scroll')[1](lenis);
  }

  it('gives the cards back to the scroll', () => {
    keyboardNav('forward');                 // travelling towards position 1
    const { lenis } = getScrollEngineState();
    lenis.animatedScroll = 0.98 * window.innerHeight;

    readerTakesOver();
    mocks.mockActivateCard.mockClear();
    scrollFrame(3);                         // the reader, two steps further on

    expect(mocks.mockActivateCard).toHaveBeenCalled();
  });

  it('settles the cards when the reader scrolls back into the intro', () => {
    keyboardNav('forward');
    const { lenis } = getScrollEngineState();
    lenis.animatedScroll = 0.98 * window.innerHeight;

    readerTakesOver();
    mocks.mockSettleCards.mockClear();
    scrollFrame(0.4);

    expect(mocks.mockSettleCards).toHaveBeenCalled();
  });

  it('does not start a second carry on top of the one already running', () => {
    // A gesture that stops between steps is carried to the nearer one, and that
    // carry takes a nav token so the next settle leaves it alone. The reader
    // wheeling again during it must not start a second: two moves on one scroll
    // is the thing carryToNearestStep's own guard exists to prevent.
    vi.useFakeTimers();
    const { lenis } = getScrollEngineState();
    lenis.animatedScroll = 1.4 * window.innerHeight;

    readerTakesOver(wheelEvent());
    scrollFrame(1.4);
    vi.advanceTimersByTime(150);          // the settle carries it to step 2
    const afterFirstCarry = mocks.lenisScrollTo.mock.calls.length;
    expect(afterFirstCarry).toBeGreaterThan(0);

    readerTakesOver(wheelEvent());
    vi.advanceTimersByTime(150);

    expect(mocks.lenisScrollTo.mock.calls.length).toBe(afterFirstCarry);
  });

  it('leaves the move running when Lenis passes the input by', () => {
    // Lenis emits virtual-scroll before it decides. A ctrl-wheel is a zoom,
    // which it passes by at lenis.mjs:586 — the keyboard's animation is still
    // travelling, and the reader asked for step 1.
    keyboardNav('forward');
    readerTakesOver(wheelEvent({ event: { ctrlKey: true, composedPath: () => [] } }));
    mocks.mockGoToStep.mockClear();
    scrollFrame(0.5);                       // still short of the step

    expect(mocks.mockGoToStep).not.toHaveBeenCalled();
  });

  it('leaves the move running for a tap, which carries no scroll at all', () => {
    keyboardNav('forward');
    readerTakesOver(wheelEvent({ deltaX: 0, deltaY: 0 }));
    mocks.mockGoToStep.mockClear();
    scrollFrame(0.5);

    expect(mocks.mockGoToStep).not.toHaveBeenCalled();
  });

  it('stands the move down for a wheel, which Lenis does act on', () => {
    // The control for the two above: the same frame, the same position, and
    // the only difference is input Lenis takes the scroll with.
    keyboardNav('forward');
    readerTakesOver(wheelEvent());
    mocks.mockGoToStep.mockClear();
    scrollFrame(0.5);

    expect(mocks.mockGoToStep).toHaveBeenCalled();
  });

  it('closes the scrub on every gesture after the one that took over', () => {
    vi.useFakeTimers();
    keyboardNav('forward');
    // Resting on the step the move was going to, so the settle below has
    // nothing to carry and starts no move of its own — this case is about the
    // move the reader interrupted, and a carry would supply a token for the
    // right reason and hide whether the interrupted one let go of its own.
    const { lenis } = getScrollEngineState();
    lenis.animatedScroll = 1 * window.innerHeight;

    readerTakesOver();
    vi.advanceTimersByTime(150);            // the gesture's own settle
    mocks.mockSettleCards.mockClear();

    // A later gesture, tracked frame by frame. Every frame re-arms the settle,
    // so a scroll that drifts to a stop is settled where it actually stops.
    scrollFrame(2.2);
    scrollFrame(2.6);
    vi.advanceTimersByTime(150);

    expect(mocks.mockSettleCards).toHaveBeenCalled();
  });
});

// ── A resize keeps the reader on their step ──────────────────────────────────

describe('a window that changes height', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div class="scroll-surface"></div>
      <div class="card-stack">
        <div class="story-step"></div>
        <div class="story-step"></div>
        <div class="story-step"></div>
        <div class="story-step"></div>
        <div class="story-step"></div>
      </div>
    `;
    mocks.lenisScrollTo.mockClear();
    mocks.mockActivateCard.mockClear();
    resetState({ currentIndex: -1 });

    vi.useFakeTimers();
    vi.stubGlobal('innerHeight', 900);
    vi.stubGlobal('requestAnimationFrame', vi.fn());
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query) => ({
      matches: false, media: query, onchange: null,
      addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })));
    try {
      Object.defineProperty(history, 'scrollRestoration',
        { writable: true, value: 'auto', configurable: true });
    } catch (_) { /* already writable here */ }

    initScrollEngine(5);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  /** One frame of Lenis's output, at `px` pixels down the surface. */
  function scrollFrameAt(px) {
    const { lenis } = getScrollEngineState();
    lenis.animatedScroll = px;
    mocks.lenisOn.mock.calls.findLast(([event]) => event === 'scroll')[1](lenis);
  }

  /** Change the window's height and let the resize settle. */
  function resizeTo(height) {
    vi.stubGlobal('innerHeight', height);
    window.dispatchEvent(new Event('resize'));
    vi.advanceTimersByTime(100);
  }

  /** The immediate jump the relayout made, if any. */
  const relayoutJump = () => mocks.lenisScrollTo.mock.calls.find(
    ([, opts]) => opts?.immediate === true && opts?.force === true);

  it('puts the scroll at the same step in the new height', () => {
    scrollFrameAt(4 * 900);                 // step index 3
    expect(state.currentIndex).toBe(3);
    mocks.mockActivateCard.mockClear();

    resizeTo(720);

    expect(relayoutJump()?.[0]).toBe(4 * 720);
    expect(state.currentIndex).toBe(3);
    expect(mocks.mockActivateCard).not.toHaveBeenCalled();
    expect(document.querySelector('.scroll-surface').style.height).toBe(`${6 * 720}px`);
  });

  it('reads nothing from a frame reported before the layout catches up', () => {
    // The browser clamps the offset to the resized window, and Lenis reports
    // the clamp, before the debounced relayout has run.
    scrollFrameAt(5 * 900);                 // the last step
    mocks.mockActivateCard.mockClear();
    vi.stubGlobal('innerHeight', 1000);
    scrollFrameAt(5 * 900 - 100);

    expect(state.scrollPosition).toBe(5);
    expect(mocks.mockActivateCard).not.toHaveBeenCalled();

    window.dispatchEvent(new Event('resize'));
    vi.advanceTimersByTime(100);
    expect(relayoutJump()?.[0]).toBe(5 * 1000);
    expect(state.currentIndex).toBe(4);
  });

  it('lands a keyboard move under way where it was going, and stands it down', () => {
    scrollFrameAt(2 * 900);                 // step index 1
    keyboardNav('forward');                 // towards position 3
    const { lenis } = getScrollEngineState();
    lenis.isScrolling = 'smooth';           // the move is travelling
    lenis.animatedScroll = 2.3 * 900;
    mocks.lenisScrollTo.mockClear();

    resizeTo(720);

    expect(relayoutJump()?.[0]).toBe(3 * 720);
    expect(state.currentIndex).toBe(2);

    // Stood down: the move's completion will never run, so nothing may still
    // hold the cards for it. The reader's next scroll moves the story.
    lenis.isScrolling = false;
    mocks.mockActivateCard.mockClear();
    scrollFrameAt(4 * 720);
    expect(mocks.mockActivateCard).toHaveBeenCalled();
    expect(state.currentIndex).toBe(3);
  });

  it('leaves the scroll alone when only the width changes', () => {
    scrollFrameAt(4 * 900);
    mocks.lenisScrollTo.mockClear();
    window.dispatchEvent(new Event('resize'));
    vi.advanceTimersByTime(100);

    expect(relayoutJump()).toBeUndefined();
    expect(state.currentIndex).toBe(3);
  });
});
