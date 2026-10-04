/**
 * The scroll engine under test, with Lenis, Snap and the modules it drives
 * replaced by mocks, for the suites that exercise it.
 *
 * A suite registers the mock modules with vi.mock, importing this file inside
 * each factory, and imports the same `mocks` to drive and read them. Both see
 * one instance of this module, so a spy set up here is the one the engine
 * calls.
 *
 * @version v1.8.0
 */

import { vi } from 'vitest';
import { state } from '../../assets/js/telar-story/state.js';

const lenisOn = vi.fn();
const lenisRaf = vi.fn();
const lenisScrollTo = vi.fn();
const lenisResize = vi.fn();

const snapAdd = vi.fn(() => vi.fn()); // returns a remover function
const snapRemove = vi.fn();
const snapResize = vi.fn();

const lenisConstructorArgs = [];
const lenisInstances = [];
const snapConstructorArgs = [];

// Lenis constructor — must be a regular function to work with `new`
function MockLenis(opts) {
  lenisConstructorArgs.push(opts);
  lenisInstances.push(this);
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

export const mocks = {
  MockLenis,
  MockSnap,
  lenisOn,
  lenisScrollTo,
  lenisResize,
  snapAdd,
  snapRemove,
  lenisConstructorArgs,
  snapConstructorArgs,
  mockActivateCard: vi.fn(),
  mockSettleCards: vi.fn(),
  mockGoToStep: vi.fn(),
  mockFollowEngine: vi.fn(),
  mockInitKeyboardNavigation: vi.fn(),
  mockInitializeLoadingShimmer: vi.fn(),
  mockUpdateViewerInfo: vi.fn(),
};

// ── Mock modules, one per vi.mock ────────────────────────────────────────────

export const lenisModule = { default: MockLenis };
export const snapModule = { default: MockSnap };

export const cardPoolModule = {
  activateCard: mocks.mockActivateCard,
  setCardProgress: vi.fn(),
  settleCards: mocks.mockSettleCards,
  reconcileStackForJump: vi.fn(),
  reconcilePlatesForJump: vi.fn(),
};

export const cameraTravelModule = {
  stepTravel: vi.fn(() => 0),
  travelBetween: vi.fn(() => 0),
};

export const iiifCardModule = {
  lerpIiifPosition: vi.fn(),
  snapIiifToPosition: vi.fn(),
  animateIiifToPosition: vi.fn(),
  createIiifCard: vi.fn(),
  getOrCreateIiifCard: vi.fn(),
  activateIiifCard: vi.fn(),
  destroyIiifCard: vi.fn(),
};

export const navigationModule = {
  goToStep: mocks.mockGoToStep,
  followEngine: mocks.mockFollowEngine,
  jumpButtonsTo: vi.fn(),
  putButtonsOnIntro: vi.fn(),
  initKeyboardNavigation: mocks.mockInitKeyboardNavigation,
  updateViewerInfo: mocks.mockUpdateViewerInfo,
};

export const viewerModule = {
  initializeLoadingShimmer: mocks.mockInitializeLoadingShimmer,
  buildObjectsIndex: vi.fn(),
  prefetchStoryManifests: vi.fn(),
  initializeCredits: vi.fn(),
  getManifestUrl: vi.fn(),
  updateObjectCredits: vi.fn(),
  showViewerSkeletonState: vi.fn(),
};

// ── Helpers ──────────────────────────────────────────────────────────────────

/** A story page with this many steps, on the surface initScrollEngine reads. */
export function engineStory(stepCount) {
  document.body.innerHTML = `
    <div class="scroll-surface"></div>
    <div class="card-stack">${'<div class="story-step"></div>'.repeat(stepCount)}</div>
  `;
}

/** The browser globals initScrollEngine reads that jsdom lacks. */
export function stubEngineGlobals() {
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
}

/** The listener Lenis calls the moment raw input arrives. */
export function readerTakesOver(payload) {
  lenisOn.mock.calls.find(([event]) => event === 'virtual-scroll')[1](payload);
}

/** A wheel gesture as Lenis reports one, with the fields the filter reads. */
export const wheelEvent = (over = {}) => ({
  deltaX: 0, deltaY: -120,
  event: { ctrlKey: false, composedPath: () => [] },
  ...over,
});

/** One frame of the engine's Lenis's smoothed output, at `position` viewports. */
export function scrollFrame(position) {
  const lenis = lenisInstances.at(-1);
  lenis.animatedScroll = position * window.innerHeight;
  lenisOn.mock.calls.find(([event]) => event === 'scroll')[1](lenis);
}

/** The engine's Lenis instance: the last one constructed. */
export const engineLenis = () => lenisInstances.at(-1);

function emitScroll(lenis) {
  lenisOn.mock.calls.find(([event]) => event === 'scroll')[1](lenis);
}

/**
 * Give the engine's Lenis the scrolling behaviour of lenis.mjs 1.3, in place
 * of the recording spies: a scrollTo refused while stopped or locked unless
 * forced; a scrollTo to the offset it holds as its target skipped, with its
 * completion called at once; an immediate jump set and emitted; an animated
 * move left in flight, holding as its target the offset it left from, until
 * `landMove` finishes it; and stop and start each ending any move in flight
 * and emitting a frame where the scroll stands.
 */
export function modelLenis() {
  const lenis = engineLenis();
  const reset = () => {
    lenis.isScrolling = false;
    lenis.isLocked = false;
    lenis.targetScroll = lenis.animatedScroll;
    lenis.inFlight = null;
  };
  lenis.targetScroll = lenis.animatedScroll;
  lenis.scrollTo = vi.fn((px, opts = {}) => {
    if ((lenis.isStopped || lenis.isLocked) && !opts.force) return;
    if (px === lenis.targetScroll) {
      opts.onStart?.(lenis);
      opts.onComplete?.(lenis);
      return;
    }
    if (opts.immediate) {
      lenis.animatedScroll = lenis.targetScroll = px;
      reset();
      emitScroll(lenis);
      opts.onComplete?.(lenis);
      return;
    }
    lenis.isScrolling = 'smooth';
    lenis.inFlight = { px, onComplete: opts.onComplete };
  });
  lenis.stop = vi.fn(() => {
    if (lenis.isStopped) return;
    reset();
    lenis.isStopped = true;
    emitScroll(lenis);
  });
  lenis.start = vi.fn(() => {
    if (!lenis.isStopped) return;
    reset();
    lenis.isStopped = false;
    emitScroll(lenis);
  });
  return lenis;
}

/** Run the modelled Lenis's move in flight to its landing, if one is left. */
export function landMove() {
  const lenis = engineLenis();
  const move = lenis.inFlight;
  if (!move) return;
  lenis.animatedScroll = lenis.targetScroll = move.px;
  lenis.isScrolling = false;
  lenis.inFlight = null;
  emitScroll(lenis);
  move.onComplete?.(lenis);
}

/**
 * The reader's own scroll taking over the modelled Lenis and coming to rest at
 * `position`. Lenis answers input it acts on by replacing the move in flight
 * with the reader's scroll, and the replaced move's completion is never
 * called.
 */
export function readerScrollsTo(position) {
  const lenis = engineLenis();
  lenis.inFlight = null;
  lenis.isScrolling = false;
  lenis.animatedScroll = lenis.targetScroll = position * window.innerHeight;
  emitScroll(lenis);
}

/** A scroll frame on the modelled Lenis, which also moves its target. */
export function restAt(position) {
  const lenis = engineLenis();
  lenis.animatedScroll = lenis.targetScroll = position * window.innerHeight;
  emitScroll(lenis);
}

export function resetState(overrides = {}) {
  state.steps = Array.from({ length: 5 }, (_, i) => ({ index: i }));
  state.currentIndex = -1;
  state.scrollPosition = 0;
  state.scrollProgress = 0;
  state.isSnapping = false;
  state.lenis = null;
  state.snap = null;
  Object.assign(state, overrides);
}

/**
 * A wheel over a side card, as Lenis would report one if it reached it: the
 * event's target and path are inside the card.
 */
export const cardWheelEvent = ({ card, deltaY = 120 } = {}) => ({
  deltaX: 0, deltaY,
  event: { type: 'wheel', target: card, ctrlKey: false, composedPath: () => [card, document.body] },
});
