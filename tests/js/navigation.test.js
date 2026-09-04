/**
 * Tests for Telar Story – Navigation
 *
 * Keyboard behaviour is exercised by dispatching cancelable KeyboardEvent
 * objects on the document after initKeyboardNavigation(); step and intro
 * behaviour by calling goToStep and initializeButtonNavigation directly.
 * Covered here:
 *   - ArrowDown/Up/PageDown/PageUp/Space call keyboardNav when lenis is set,
 *     and nextStep/prevStep when it is not
 *   - the same keys scroll the topmost panel instead when one is open, and
 *     which of them cancel the event in that state
 *   - auto-repeat is ignored for story navigation and allowed for panel
 *     scrolling
 *   - scrollLockActive blocks step navigation but not panel keys
 *   - ArrowRight opens layer 1, then layer 2 above a single open layer 1
 *   - ArrowLeft and Escape close the topmost panel
 *   - goToStep's bounds, its card activation, and its intro restoration
 *   - the mobile previous button restoring the intro from step 0
 *
 * @version v1.7.0
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Hoisted mocks ─────────────────────────────────────────────────────────────

const mocks = vi.hoisted(() => {
  const mockOpenPanel = vi.fn();
  const mockCloseTopPanel = vi.fn();
  const mockStepHasLayer1Content = vi.fn(() => true);
  const mockStepHasLayer2Content = vi.fn(() => false);
  const mockActivateCard = vi.fn();
  const mockInitializeLoadingShimmer = vi.fn();
  const mockAdvanceToStep = vi.fn();
  const mockKeyboardNav = vi.fn();

  return {
    mockOpenPanel,
    mockCloseTopPanel,
    mockStepHasLayer1Content,
    mockStepHasLayer2Content,
    mockActivateCard,
    mockInitializeLoadingShimmer,
    mockAdvanceToStep,
    mockKeyboardNav,
  };
});

vi.mock('../../assets/js/telar-story/panels.js', () => ({
  openPanel: mocks.mockOpenPanel,
  closeTopPanel: mocks.mockCloseTopPanel,
  stepHasLayer1Content: mocks.mockStepHasLayer1Content,
  stepHasLayer2Content: mocks.mockStepHasLayer2Content,
  activateScrollLock: vi.fn(),
  deactivateScrollLock: vi.fn(),
}));

vi.mock('../../assets/js/telar-story/card-pool.js', () => ({
  activateCard: mocks.mockActivateCard,
  setCardProgress: vi.fn(),
  initCardPool: vi.fn(),
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

vi.mock('../../assets/js/telar-story/scroll-engine.js', () => ({
  advanceToStep: mocks.mockAdvanceToStep,
  keyboardNav: mocks.mockKeyboardNav,
  initScrollEngine: vi.fn(),
  updateScrollPosition: vi.fn(),
  getScrollEngineState: vi.fn(),
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

// ── Imports (after mocks) ─────────────────────────────────────────────────────

import {
  initKeyboardNavigation,
  goToStep,
  initializeButtonNavigation,
} from '../../assets/js/telar-story/navigation.js';
import { state } from '../../assets/js/telar-story/state.js';

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Dispatch a synthetic KeyboardEvent on document.
 *
 * The event is cancelable so that defaultPrevented reports whether the
 * handler claimed the key.
 *
 * @param {string} key - Key value (e.g. 'ArrowDown')
 * @param {object} [extras] - Additional event init properties
 * @returns {KeyboardEvent} The dispatched event
 */
function pressKey(key, extras = {}) {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...extras });
  document.dispatchEvent(event);
  return event;
}

/**
 * Open a panel of a given type, in both the state and the DOM.
 *
 * The keyboard scroll path reaches .offcanvas-body inside #panel-<type> and
 * calls scrollBy on it. jsdom implements no scrolling, so the body carries a
 * spy in its place.
 *
 * @param {string} type - Panel type ('layer1' or 'layer2')
 * @returns {HTMLElement} The panel body, with scrollBy spied
 */
function openPanelInDom(type) {
  const panel = document.createElement('div');
  panel.id = `panel-${type}`;
  const body = document.createElement('div');
  body.className = 'offcanvas-body';
  body.scrollBy = vi.fn();
  panel.appendChild(body);
  document.body.appendChild(panel);

  state.isPanelOpen = true;
  state.panelStack.push({ type });
  return body;
}

/**
 * A text card carrying authored messiness offsets.
 *
 * @param {object} messiness - rot, offX and offY, as authored
 * @returns {HTMLElement}
 */
function makeTextCard({ rot = 0, offX = 0, offY = 0 } = {}) {
  const card = document.createElement('div');
  card.className = 'story-text-card is-active is-stacked';
  card.dataset.messinessRot = String(rot);
  card.dataset.messinessOffX = String(offX);
  card.dataset.messinessOffY = String(offY);
  return card;
}

/**
 * A viewer plate sitting in its active position.
 *
 * @returns {HTMLElement}
 */
function makeViewerPlate() {
  const plate = document.createElement('div');
  plate.className = 'viewer-plate is-active';
  return plate;
}

function resetState(overrides = {}) {
  state.steps = Array.from({ length: 5 }, (_, i) => ({ dataset: { step: String(i + 1) } }));
  state.currentIndex = 0;
  state.scrollLockActive = false;
  state.isPanelOpen = false;
  state.panelStack = [];
  state.lenis = {}; // truthy — enables keyboardNav path
  state.textCards = {};
  state.viewerPlates = {};
  state.currentObjectRun = { objectId: null, runPosition: 0 };
  state.onStepChange = null;
  state.mobileInIntro = false;
  state.mobileNavButtons = null;
  state.mobileNavigationCooldown = false;
  state.currentMobileStep = 0;
  Object.assign(state, overrides);
}

// ── Setup: register listener once ────────────────────────────────────────────

// Ensure keyboard listener is registered before all tests run.
// initKeyboardNavigation is idempotent in terms of behaviour — adding a
// second listener would double-call, so we rely on module-level init here.
// We call it once here and let beforeEach reset state only.

beforeEach(() => {
  mocks.mockOpenPanel.mockClear();
  mocks.mockCloseTopPanel.mockClear();
  mocks.mockActivateCard.mockClear();
  mocks.mockKeyboardNav.mockClear();
  mocks.mockStepHasLayer1Content.mockReturnValue(true);
  mocks.mockStepHasLayer2Content.mockReturnValue(false);

  document.body.innerHTML = '';
  window.storyData = { steps: [] };
  resetState();
});

// Register once — module caches the document.addEventListener call.
// (Tests share the same listener; state is reset in beforeEach.)
initKeyboardNavigation();

// ── ArrowDown / PageDown ──────────────────────────────────────────────────────

describe('ArrowDown', () => {
  it('calls keyboardNav forward when lenis is set and scrollLockActive is false', () => {
    pressKey('ArrowDown');
    expect(mocks.mockKeyboardNav).toHaveBeenCalledOnce();
    expect(mocks.mockKeyboardNav).toHaveBeenCalledWith('forward');
  });

  it('does NOT call keyboardNav when scrollLockActive is true', () => {
    state.scrollLockActive = true;
    pressKey('ArrowDown');
    expect(mocks.mockKeyboardNav).not.toHaveBeenCalled();
  });

  it('ignores auto-repeat events (e.repeat=true)', () => {
    pressKey('ArrowDown', { repeat: true });
    expect(mocks.mockKeyboardNav).not.toHaveBeenCalled();
  });
});

describe('PageDown', () => {
  it('calls keyboardNav forward when lenis is set', () => {
    pressKey('PageDown');
    expect(mocks.mockKeyboardNav).toHaveBeenCalledOnce();
    expect(mocks.mockKeyboardNav).toHaveBeenCalledWith('forward');
  });
});

// ── ArrowUp / PageUp ──────────────────────────────────────────────────────────

describe('ArrowUp', () => {
  it('calls keyboardNav backward when lenis is set and scrollLockActive is false', () => {
    pressKey('ArrowUp');
    expect(mocks.mockKeyboardNav).toHaveBeenCalledOnce();
    expect(mocks.mockKeyboardNav).toHaveBeenCalledWith('backward');
  });

  it('does NOT call keyboardNav when scrollLockActive is true', () => {
    state.scrollLockActive = true;
    pressKey('ArrowUp');
    expect(mocks.mockKeyboardNav).not.toHaveBeenCalled();
  });

  it('ignores auto-repeat events (e.repeat=true)', () => {
    pressKey('ArrowUp', { repeat: true });
    expect(mocks.mockKeyboardNav).not.toHaveBeenCalled();
  });
});

describe('PageUp', () => {
  it('calls keyboardNav backward when lenis is set', () => {
    pressKey('PageUp');
    expect(mocks.mockKeyboardNav).toHaveBeenCalledOnce();
    expect(mocks.mockKeyboardNav).toHaveBeenCalledWith('backward');
  });
});

// ── Space / Shift+Space ───────────────────────────────────────────────────────

describe('Space', () => {
  it('calls keyboardNav forward on Space press', () => {
    pressKey(' ');
    expect(mocks.mockKeyboardNav).toHaveBeenCalledOnce();
    expect(mocks.mockKeyboardNav).toHaveBeenCalledWith('forward');
  });

  it('calls keyboardNav backward on Shift+Space press', () => {
    pressKey(' ', { shiftKey: true });
    expect(mocks.mockKeyboardNav).toHaveBeenCalledOnce();
    expect(mocks.mockKeyboardNav).toHaveBeenCalledWith('backward');
  });

  it('does not navigate when scrollLockActive is true', () => {
    state.scrollLockActive = true;
    pressKey(' ');
    expect(mocks.mockKeyboardNav).not.toHaveBeenCalled();
  });
});

// ── Fallback when snap is null ────────────────────────────────────────────────

describe('fallback to nextStep/prevStep when lenis is null', () => {
  it('ArrowDown calls activateCard (via nextStep) when lenis is null', () => {
    state.lenis = null;
    // nextStep calls goToStep(state.currentIndex + 1, 'forward')
    // which calls activateCard — so mockActivateCard should be invoked
    pressKey('ArrowDown');
    expect(mocks.mockKeyboardNav).not.toHaveBeenCalled();
    // goToStep calls activateCard with target index
    expect(mocks.mockActivateCard).toHaveBeenCalledWith(
      state.currentIndex, // was already advanced; check it was called
      expect.any(String)
    );
  });

  it('ArrowUp calls activateCard (via prevStep) when lenis is null', () => {
    state.lenis = null;
    state.currentIndex = 2;
    pressKey('ArrowUp');
    expect(mocks.mockKeyboardNav).not.toHaveBeenCalled();
    expect(mocks.mockActivateCard).toHaveBeenCalled();
  });
});

// ── Panel keyboard controls ───────────────────────────────────────────────────

describe('ArrowRight — panel open', () => {
  it('calls openPanel("layer1") when panel is not open and step has layer1 content', () => {
    state.isPanelOpen = false;
    state.panelStack = [];
    // Provide minimal step data so getCurrentStepData returns something
    window.storyData = { steps: [{ step: '1', layer1_title: 'Test' }] };
    mocks.mockStepHasLayer1Content.mockReturnValue(true);

    pressKey('ArrowRight');
    expect(mocks.mockOpenPanel).toHaveBeenCalledWith('layer1', expect.anything());
  });
});

describe('ArrowLeft — panel close', () => {
  it('calls closeTopPanel() when panel is open', () => {
    state.isPanelOpen = true;
    pressKey('ArrowLeft');
    expect(mocks.mockCloseTopPanel).toHaveBeenCalledOnce();
  });

  it('does NOT call closeTopPanel() when no panel is open', () => {
    state.isPanelOpen = false;
    pressKey('ArrowLeft');
    expect(mocks.mockCloseTopPanel).not.toHaveBeenCalled();
  });
});

describe('Escape — panel close', () => {
  it('calls closeTopPanel() when panel is open', () => {
    state.isPanelOpen = true;
    pressKey('Escape');
    expect(mocks.mockCloseTopPanel).toHaveBeenCalledOnce();
  });

  it('does NOT call closeTopPanel() when no panel is open', () => {
    state.isPanelOpen = false;
    pressKey('Escape');
    expect(mocks.mockCloseTopPanel).not.toHaveBeenCalled();
  });
});

// ── Event cancellation ────────────────────────────────────────────────────────
//
// Which keys the handler claims is behaviour of its own: a claimed key stops
// the browser from also scrolling the document, and an unclaimed one has to
// stay available to the page.

describe('event cancellation with no panel open', () => {
  it('claims ArrowDown', () => {
    expect(pressKey('ArrowDown').defaultPrevented).toBe(true);
  });

  it('claims ArrowUp', () => {
    expect(pressKey('ArrowUp').defaultPrevented).toBe(true);
  });

  it('claims PageDown', () => {
    expect(pressKey('PageDown').defaultPrevented).toBe(true);
  });

  it('claims PageUp', () => {
    expect(pressKey('PageUp').defaultPrevented).toBe(true);
  });

  it('claims Space', () => {
    expect(pressKey(' ').defaultPrevented).toBe(true);
  });

  it('claims ArrowRight', () => {
    expect(pressKey('ArrowRight').defaultPrevented).toBe(true);
  });

  it('claims ArrowLeft', () => {
    expect(pressKey('ArrowLeft').defaultPrevented).toBe(true);
  });

  it('leaves Escape to the page', () => {
    expect(pressKey('Escape').defaultPrevented).toBe(false);
  });

  it('claims ArrowDown even under a scroll lock', () => {
    state.scrollLockActive = true;
    expect(pressKey('ArrowDown').defaultPrevented).toBe(true);
  });
});

// ── Panel scrolling ───────────────────────────────────────────────────────────
//
// With a panel open the navigation keys scroll its body rather than moving the
// story. The arrow and page keys stay uncancelled in that state so that a
// panel long enough to need the browser's own scrolling still gets it; Space
// and Escape are cancelled because the page would otherwise act on them.

describe('navigation keys with a panel open', () => {
  it('ArrowDown scrolls the panel body down and moves no step', () => {
    const body = openPanelInDom('layer1');
    const event = pressKey('ArrowDown');

    expect(body.scrollBy).toHaveBeenCalledWith({ top: 40, behavior: 'smooth' });
    expect(mocks.mockKeyboardNav).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it('ArrowUp scrolls the panel body up and moves no step', () => {
    const body = openPanelInDom('layer1');
    const event = pressKey('ArrowUp');

    expect(body.scrollBy).toHaveBeenCalledWith({ top: -40, behavior: 'smooth' });
    expect(mocks.mockKeyboardNav).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it('PageDown scrolls the panel body down', () => {
    const body = openPanelInDom('layer1');
    const event = pressKey('PageDown');

    expect(body.scrollBy).toHaveBeenCalledWith({ top: 40, behavior: 'smooth' });
    expect(event.defaultPrevented).toBe(false);
  });

  it('PageUp scrolls the panel body up', () => {
    const body = openPanelInDom('layer1');
    const event = pressKey('PageUp');

    expect(body.scrollBy).toHaveBeenCalledWith({ top: -40, behavior: 'smooth' });
    expect(event.defaultPrevented).toBe(false);
  });

  it('Space scrolls the panel body a page down and claims the key', () => {
    const body = openPanelInDom('layer1');
    const event = pressKey(' ');

    expect(body.scrollBy).toHaveBeenCalledWith({ top: 100, behavior: 'smooth' });
    expect(mocks.mockKeyboardNav).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(true);
  });

  it('Shift+Space scrolls the panel body a page up and claims the key', () => {
    const body = openPanelInDom('layer1');
    const event = pressKey(' ', { shiftKey: true });

    expect(body.scrollBy).toHaveBeenCalledWith({ top: -100, behavior: 'smooth' });
    expect(mocks.mockKeyboardNav).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(true);
  });

  it('scrolls on auto-repeat, so a held key keeps the panel moving', () => {
    const body = openPanelInDom('layer1');
    pressKey('ArrowDown', { repeat: true });

    expect(body.scrollBy).toHaveBeenCalledWith({ top: 40, behavior: 'smooth' });
  });

  it('scrolls under a scroll lock, which only holds the story still', () => {
    const body = openPanelInDom('layer1');
    state.scrollLockActive = true;
    pressKey('ArrowDown');

    expect(body.scrollBy).toHaveBeenCalledOnce();
  });

  it('scrolls the topmost panel of a stack of two', () => {
    const first = openPanelInDom('layer1');
    const second = openPanelInDom('layer2');
    pressKey('ArrowDown');

    expect(second.scrollBy).toHaveBeenCalledWith({ top: 40, behavior: 'smooth' });
    expect(first.scrollBy).not.toHaveBeenCalled();
  });

  it('does nothing when the panel state and the stack disagree', () => {
    state.isPanelOpen = true;
    state.panelStack = [];

    expect(() => pressKey('ArrowDown')).not.toThrow();
    expect(mocks.mockKeyboardNav).not.toHaveBeenCalled();
  });
});

// ── Fallback with no scroll engine ────────────────────────────────────────────

describe('Space with no scroll engine', () => {
  it('advances a step through activateCard', () => {
    state.lenis = null;
    pressKey(' ');

    expect(mocks.mockKeyboardNav).not.toHaveBeenCalled();
    expect(mocks.mockActivateCard).toHaveBeenCalledWith(1, 'forward');
  });

  it('goes back a step on Shift+Space', () => {
    state.lenis = null;
    state.currentIndex = 2;
    pressKey(' ', { shiftKey: true });

    expect(mocks.mockActivateCard).toHaveBeenCalledWith(1, 'backward');
  });
});

// ── ArrowRight — layer opening ────────────────────────────────────────────────

describe('ArrowRight — opening a layer', () => {
  beforeEach(() => {
    window.storyData = { steps: [{ step: '1', layer1_title: 'First', layer2_title: 'Second' }] };
  });

  it('opens layer2 above a single open layer1 when the step has layer2 content', () => {
    state.isPanelOpen = true;
    state.panelStack = [{ type: 'layer1' }];
    mocks.mockStepHasLayer2Content.mockReturnValue(true);

    pressKey('ArrowRight');

    expect(mocks.mockOpenPanel).toHaveBeenCalledWith('layer2', '1');
  });

  it('opens nothing above a layer1 when the step has no layer2 content', () => {
    state.isPanelOpen = true;
    state.panelStack = [{ type: 'layer1' }];
    mocks.mockStepHasLayer2Content.mockReturnValue(false);

    pressKey('ArrowRight');

    expect(mocks.mockOpenPanel).not.toHaveBeenCalled();
  });

  it('opens nothing above two stacked panels', () => {
    state.isPanelOpen = true;
    state.panelStack = [{ type: 'layer1' }, { type: 'layer2' }];
    mocks.mockStepHasLayer2Content.mockReturnValue(true);

    pressKey('ArrowRight');

    expect(mocks.mockOpenPanel).not.toHaveBeenCalled();
  });

  it('opens nothing above a panel that is not a layer1', () => {
    state.isPanelOpen = true;
    state.panelStack = [{ type: 'layer2' }];
    mocks.mockStepHasLayer2Content.mockReturnValue(true);

    pressKey('ArrowRight');

    expect(mocks.mockOpenPanel).not.toHaveBeenCalled();
  });

  it('opens nothing when the step has no layer1 content', () => {
    mocks.mockStepHasLayer1Content.mockReturnValue(false);

    pressKey('ArrowRight');

    expect(mocks.mockOpenPanel).not.toHaveBeenCalled();
  });

  it('opens nothing on the intro, which is no step', () => {
    state.currentIndex = -1;

    pressKey('ArrowRight');

    expect(mocks.mockOpenPanel).not.toHaveBeenCalled();
  });

  it('opens nothing when the current step is absent from the story data', () => {
    window.storyData = { steps: [{ step: '4' }] };

    pressKey('ArrowRight');

    expect(mocks.mockOpenPanel).not.toHaveBeenCalled();
  });

  it('passes the current step number to the panel it opens', () => {
    state.currentIndex = 0;
    pressKey('ArrowRight');

    expect(mocks.mockOpenPanel).toHaveBeenCalledWith('layer1', '1');
  });
});

// ── goToStep ──────────────────────────────────────────────────────────────────

describe('goToStep — bounds', () => {
  it('ignores an index below the intro', () => {
    goToStep(-2);

    expect(state.currentIndex).toBe(0);
    expect(mocks.mockActivateCard).not.toHaveBeenCalled();
  });

  it('ignores an index past the last step', () => {
    goToStep(state.steps.length);

    expect(state.currentIndex).toBe(0);
    expect(mocks.mockActivateCard).not.toHaveBeenCalled();
  });

  it('accepts the last step', () => {
    goToStep(state.steps.length - 1);

    expect(state.currentIndex).toBe(4);
    expect(mocks.mockActivateCard).toHaveBeenCalledWith(4, 'forward');
  });
});

describe('goToStep — a story step', () => {
  it('activates the card in the direction given', () => {
    goToStep(2, 'backward');

    expect(state.currentIndex).toBe(2);
    expect(mocks.mockActivateCard).toHaveBeenCalledWith(2, 'backward');
  });

  it('treats an unstated direction as forward', () => {
    goToStep(1);

    expect(mocks.mockActivateCard).toHaveBeenCalledWith(1, 'forward');
  });

  it('reports the new step to the listener', () => {
    const onStepChange = vi.fn();
    state.onStepChange = onStepChange;

    goToStep(3);

    expect(onStepChange).toHaveBeenCalledWith(3);
  });

  it('moves without a listener', () => {
    state.onStepChange = null;

    expect(() => goToStep(1)).not.toThrow();
    expect(state.currentIndex).toBe(1);
  });
});

describe('goToStep(-1) — intro restoration', () => {
  let intro;
  let firstCard;
  let plate;
  let creditBadge;

  beforeEach(() => {
    intro = document.createElement('div');
    intro.className = 'story-intro';
    document.body.appendChild(intro);

    creditBadge = document.createElement('div');
    creditBadge.id = 'object-credits-badge';
    document.body.appendChild(creditBadge);

    firstCard = makeTextCard({ rot: 2, offX: 3, offY: -4 });
    state.textCards = { 0: firstCard };

    plate = makeViewerPlate();
    state.viewerPlates = { leviathan: plate };
    window.storyData = { steps: [], firstObject: 'leviathan' };

    state.currentObjectRun = { objectId: 'leviathan', runPosition: 2 };
  });

  it('slides the intro card back into view', () => {
    goToStep(-1, 'backward');

    expect(state.currentIndex).toBe(-1);
    expect(intro.style.transform).toBe('translateY(0)');
    expect(intro.style.transition).toBe('transform 0.5s ease-out');
  });

  it('sends the first text card off the bottom carrying its authored messiness', () => {
    goToStep(-1, 'backward');

    expect(firstCard.classList.contains('is-active')).toBe(false);
    expect(firstCard.classList.contains('is-stacked')).toBe(false);
    expect(firstCard.style.transform).toBe('translateY(100vh) rotate(2deg) translate(3px, -4px)');
  });

  it('slides the first object plate down and deactivates it', () => {
    goToStep(-1, 'backward');

    expect(plate.style.transform).toBe('translateY(100%)');
    expect(plate.classList.contains('is-active')).toBe(false);
  });

  it('resets the object run and hides the credit badge', () => {
    goToStep(-1, 'backward');

    expect(state.currentObjectRun).toEqual({ objectId: null, runPosition: 0 });
    expect(creditBadge.classList.contains('d-none')).toBe(true);
  });

  it('reports the intro to the listener as step -1', () => {
    const onStepChange = vi.fn();
    state.onStepChange = onStepChange;

    goToStep(-1, 'backward');

    expect(onStepChange).toHaveBeenCalledWith(-1);
  });

  it('activates no card', () => {
    goToStep(-1, 'backward');

    expect(mocks.mockActivateCard).not.toHaveBeenCalled();
  });

  it('leaves the plates alone when the story names no first object', () => {
    window.storyData = { steps: [] };

    goToStep(-1, 'backward');

    expect(plate.style.transform).toBe('');
    expect(plate.classList.contains('is-active')).toBe(true);
  });

  it('restores a story that has no intro card, no text cards and no plates', () => {
    document.body.innerHTML = '';
    state.textCards = {};
    state.viewerPlates = {};

    expect(() => goToStep(-1, 'backward')).not.toThrow();
    expect(state.currentIndex).toBe(-1);
  });
});

// ── Mobile intro restoration ──────────────────────────────────────────────────
//
// The previous button on step 0 restores the intro. It is reached through
// initializeButtonNavigation, which builds the buttons and binds them.

describe('mobile previous button — restoring the intro', () => {
  let intro;
  let firstCard;
  let plate;
  let creditBadge;

  /** Build the story DOM the button navigation reads, then initialise it. */
  function buildMobileStory({ withIntro = true } = {}) {
    for (let i = 0; i < 3; i++) {
      const step = document.createElement('div');
      step.className = 'story-step';
      step.dataset.step = String(i + 1);
      document.body.appendChild(step);
    }

    if (withIntro) {
      intro = document.createElement('div');
      intro.className = 'story-intro';
      document.body.appendChild(intro);
    }

    creditBadge = document.createElement('div');
    creditBadge.id = 'object-credits-badge';
    document.body.appendChild(creditBadge);

    initializeButtonNavigation();

    // The story boots on the intro; these tests start from step 0 instead.
    state.mobileInIntro = false;
    state.currentMobileStep = 0;
    state.mobileNavButtons.prev.disabled = false;
  }

  beforeEach(() => {
    firstCard = makeTextCard({ rot: -1, offX: 5, offY: 6 });
    state.textCards = { 0: firstCard };

    plate = makeViewerPlate();
    state.viewerPlates = { 0: plate };
  });

  it('slides the intro card back into view', () => {
    buildMobileStory();
    state.mobileNavButtons.prev.click();

    expect(state.mobileInIntro).toBe(true);
    expect(intro.style.transform).toBe('translateY(0)');
  });

  it('sends the first text card off the bottom carrying its authored messiness', () => {
    buildMobileStory();
    state.mobileNavButtons.prev.click();

    expect(firstCard.classList.contains('is-active')).toBe(false);
    expect(firstCard.style.transform).toBe('translateY(100vh) rotate(-1deg) translate(5px, 6px)');
  });

  it('slides the first plate down and deactivates it', () => {
    buildMobileStory();
    state.mobileNavButtons.prev.click();

    expect(plate.style.transform).toBe('translateY(100%)');
    expect(plate.classList.contains('is-active')).toBe(false);
  });

  it('resets the object run, hides the credit badge and disables itself', () => {
    buildMobileStory();
    state.currentObjectRun = { objectId: 'leviathan', runPosition: 1 };

    state.mobileNavButtons.prev.click();

    expect(state.currentObjectRun).toEqual({ objectId: null, runPosition: 0 });
    expect(creditBadge.classList.contains('d-none')).toBe(true);
    expect(state.mobileNavButtons.prev.disabled).toBe(true);
  });

  it('does nothing while the navigation cooldown is running', () => {
    buildMobileStory();
    state.mobileNavigationCooldown = true;

    state.mobileNavButtons.prev.click();

    expect(state.mobileInIntro).toBe(false);
    expect(intro.style.transform).toBe('');
  });

  it('does nothing when the intro is already showing', () => {
    buildMobileStory();
    state.mobileInIntro = true;

    state.mobileNavButtons.prev.click();

    expect(intro.style.transform).toBe('');
    expect(plate.style.transform).toBe('');
  });

  it('restores a story that has no intro card, no text cards and no plates', () => {
    state.textCards = {};
    state.viewerPlates = {};
    buildMobileStory({ withIntro: false });

    expect(() => state.mobileNavButtons.prev.click()).not.toThrow();
    expect(state.mobileInIntro).toBe(true);
  });

  it('activates no card, because the intro is not a step', () => {
    buildMobileStory();
    mocks.mockActivateCard.mockClear();

    state.mobileNavButtons.prev.click();

    expect(mocks.mockActivateCard).not.toHaveBeenCalled();
  });
});
