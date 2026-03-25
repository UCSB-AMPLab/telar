/**
 * Tests for Telar Story – Keyboard Navigation
 *
 * Tests handleKeyboard behaviour by dispatching synthetic KeyboardEvent
 * objects on the document after calling initKeyboardNavigation(). Verifies
 * that:
 *   - ArrowDown/Up/Space dispatch snap.next()/snap.previous() when snap is set
 *   - Auto-repeat (e.repeat=true) is ignored
 *   - scrollLockActive blocks step navigation but not panel keys
 *   - Fallback to nextStep/prevStep when snap is null (mobile/embed)
 *   - Panel keyboard controls (ArrowRight/ArrowLeft/Escape) are preserved
 *
 * @version v1.0.0-beta
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

import { initKeyboardNavigation } from '../../assets/js/telar-story/navigation.js';
import { state } from '../../assets/js/telar-story/state.js';

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Dispatch a synthetic KeyboardEvent on document.
 *
 * @param {string} key - Key value (e.g. 'ArrowDown')
 * @param {object} [extras] - Additional event init properties
 */
function pressKey(key, extras = {}) {
  document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, ...extras }));
}

function resetState(overrides = {}) {
  state.steps = Array.from({ length: 5 }, (_, i) => ({ dataset: { step: String(i + 1) } }));
  state.currentIndex = 0;
  state.scrollLockActive = false;
  state.isPanelOpen = false;
  state.panelStack = [];
  state.lenis = {}; // truthy — enables keyboardNav path
  state.snap = {
    next: vi.fn(),
    previous: vi.fn(),
  };
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
