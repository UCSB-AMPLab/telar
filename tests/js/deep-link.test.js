/**
 * Tests for Telar Story – Deep Linking
 *
 * Covers the panel-open timer ladder in applyDeepLinkOnLoad and its
 * cancellation on user interaction. The heavy sibling modules
 * (card-pool, navigation, panels, state) are mocked so the module imports
 * cleanly in jsdom and the timing behaviour can be driven with fake timers.
 *
 * @version v1.5.0
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ── Mocks for the heavy sibling modules ──────────────────────────────────────
// The `state` object is shared by reference with the module under test, so the
// test can read the index the function assigns and mutate it to simulate the
// user navigating away mid-ladder.
vi.mock('../../assets/js/telar-story/state.js', () => ({
  state: {
    steps: [],
    currentIndex: -1,
    currentMobileStep: -1,
    scrollPosition: 0,
    lenis: null,
    snap: null,
  },
}));
vi.mock('../../assets/js/telar-story/card-pool.js', () => ({ activateCard: vi.fn() }));
vi.mock('../../assets/js/telar-story/navigation.js', () => ({ goToStep: vi.fn() }));
vi.mock('../../assets/js/telar-story/panels.js', () => ({ openPanel: vi.fn() }));

import { applyDeepLinkOnLoad } from '../../assets/js/telar-story/deep-link.js';
import { state } from '../../assets/js/telar-story/state.js';
import { openPanel } from '../../assets/js/telar-story/panels.js';

function makeSteps(n) {
  return Array.from({ length: n }, (_, i) => ({ dataset: { step: String(i + 1) } }));
}

describe('applyDeepLinkOnLoad — panel-open timer ladder', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    openPanel.mockClear();
    state.steps = makeSteps(5);
    state.currentIndex = -1;
    state.currentMobileStep = -1;
    state.lenis = { scrollTo: vi.fn() }; // desktop path
    state.snap = null;
    window.location.hash = '';
  });

  afterEach(() => {
    // Flush any armed interaction listeners so they don't leak across tests,
    // then drop fake timers.
    window.dispatchEvent(new Event('wheel'));
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it('opens the target layer after its delay when the user does not interact', () => {
    window.location.hash = '#s3l1';
    applyDeepLinkOnLoad();
    expect(state.currentIndex).toBe(2);        // jumped to step 3 (0-based 2)
    expect(openPanel).not.toHaveBeenCalled();  // not yet — still in the ladder
    vi.advanceTimersByTime(100);
    expect(openPanel).toHaveBeenCalledWith('layer1', '3');
  });

  it('opens layer1 then layer2 in order for a deeper deep-link', () => {
    window.location.hash = '#s2l2';
    applyDeepLinkOnLoad();
    vi.advanceTimersByTime(100);
    expect(openPanel).toHaveBeenCalledWith('layer1', '2'); // parent first
    vi.advanceTimersByTime(200);
    expect(openPanel).toHaveBeenCalledWith('layer2', '2'); // target second
    expect(openPanel).toHaveBeenCalledTimes(2);
  });

  it('cancels the ladder when the user scrolls (wheel) before it fires', () => {
    window.location.hash = '#s3l1';
    applyDeepLinkOnLoad();
    window.dispatchEvent(new Event('wheel')); // user starts scrolling
    vi.advanceTimersByTime(500);
    expect(openPanel).not.toHaveBeenCalled();
  });

  it('cancels the ladder on a keydown before it fires', () => {
    window.location.hash = '#s3l1';
    applyDeepLinkOnLoad();
    window.dispatchEvent(new Event('keydown'));
    vi.advanceTimersByTime(500);
    expect(openPanel).not.toHaveBeenCalled();
  });

  it('does not open the panel if the user navigated to a different step (on-target backstop)', () => {
    window.location.hash = '#s3l1';
    applyDeepLinkOnLoad();
    state.currentIndex = 4; // user moved away without firing wheel/keydown
    vi.advanceTimersByTime(100);
    expect(openPanel).not.toHaveBeenCalled();
  });

  it('schedules nothing when the fragment has no layer', () => {
    window.location.hash = '#s3';
    applyDeepLinkOnLoad();
    vi.advanceTimersByTime(500);
    expect(openPanel).not.toHaveBeenCalled();
  });
});
