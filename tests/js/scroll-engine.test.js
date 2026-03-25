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
 * @version v1.0.0-beta
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

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
    this.animatedScroll = 0;
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
}));

vi.mock('../../assets/js/telar-story/iiif-card.js', () => ({
  lerpIiifPosition: vi.fn(),
  snapIiifToPosition: vi.fn(),
  animateIiifToPosition: vi.fn(),
  createIiifCard: vi.fn(),
  getOrCreateIiifCard: vi.fn(),
  activateIiifCard: vi.fn(),
  deactivateIiifCard: vi.fn(),
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

import { updateScrollPosition, advanceToStep, initScrollEngine, getScrollEngineState } from '../../assets/js/telar-story/scroll-engine.js';
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
    expect(state.lenis.scrollTo).toHaveBeenCalledWith(
      3 * window.innerHeight,
      expect.objectContaining({ duration: 0.5 })
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

  it('uses prevent option that guards .panel descendants', () => {
    initScrollEngine(3);
    // Get the prevent fn from the Lenis constructor call
    const opts = mocks.lenisConstructorArgs[0];
    expect(typeof opts.prevent).toBe('function');

    // Node inside a panel — should be prevented
    const panel = document.createElement('div');
    panel.className = 'panel';
    const inner = document.createElement('div');
    panel.appendChild(inner);
    document.body.appendChild(panel);
    expect(opts.prevent(inner)).toBe(true);

    // Node outside panel — should NOT be prevented
    const regular = document.createElement('div');
    document.body.appendChild(regular);
    expect(opts.prevent(regular)).toBe(false);
  });
});
