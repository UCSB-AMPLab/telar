/**
 * Tests for Telar Story – Centralised State
 *
 * Verifies the initial state shape that all other modules depend on.
 * This is a contract test, not a logic test — it catches accidental
 * deletions or renames of state keys that would break dependent modules.
 *
 * Updated for v1.0.0-beta: scroll accumulator fields removed,
 * Lenis scroll engine fields added.
 *
 * @version v1.0.0-beta
 */

import { describe, it, expect } from 'vitest';
import { state, MOBILE_NAV_COOLDOWN } from '../../assets/js/telar-story/state.js';

describe('state', () => {
  it('has expected initial structure and constants', () => {
    // Constants — STEP_COOLDOWN and MAX_SCROLL_DELTA removed in v1.0.0-beta
    expect(MOBILE_NAV_COOLDOWN).toBe(400);

    // Navigation group
    expect(state.steps).toEqual([]);
    expect(state.currentIndex).toBe(-1);
    expect(state.currentObject).toBeNull();

    // Scroll engine group (replaces scrollAccumulator)
    expect(state.scrollPosition).toBe(0);
    expect(state.scrollProgress).toBe(0);
    expect(state.isSnapping).toBe(false);
    expect(state.lenis).toBeNull();
    expect(state.snap).toBeNull();

    // Viewer cards group
    expect(state.currentViewerCard).toBeNull();
    expect(state.viewerCards).toEqual([]);
    expect(state.viewerCardCounter).toBe(0);
    expect(state.objectsIndex).toEqual({});

    // Panels group
    expect(state.panelStack).toEqual([]);
    expect(state.isPanelOpen).toBe(false);
    expect(state.scrollLockActive).toBe(false);
    expect(state.creditsDismissed).toBe(false);

    // Autoplay policy group
    expect(state).toHaveProperty('hasUserInteracted', false);

    // Mobile/embed group
    expect(state.isMobileViewport).toBe(false);
    expect(state.currentMobileStep).toBe(0);
    expect(state.mobileNavButtons).toBeNull();
    expect(state.mobileNavigationCooldown).toBe(false);

    // Connection speed
    expect(state.manifestLoadTimes).toEqual([]);

    // Config — maxViewerCards is 8 since the per-scene pool cap change
    expect(state.config).toEqual({
      maxViewerCards: 8,
      preloadSteps: 6,
      loadingThreshold: 5,
      minReadyViewers: 3,
    });
  });

  it('does not have legacy scroll accumulator fields', () => {
    expect(state.scrollAccumulator).toBeUndefined();
    expect(state.scrollThreshold).toBeUndefined();
    expect(state.lastStepChangeTime).toBeUndefined();
    expect(state.touchStartY).toBeUndefined();
    expect(state.touchEndY).toBeUndefined();
  });

  it('does not have legacy hold-gate fields', () => {
    expect(state.holdGateActive).toBeUndefined();
    expect(state.holdGateArmed).toBeUndefined();
    expect(state.holdGateClipDuration).toBeUndefined();
  });
});
