/**
 * Tests for Telar Story – Centralised State
 *
 * Verifies the initial state shape that all other modules depend on.
 * This is a contract test, not a logic test — it catches accidental
 * deletions or renames of state keys that would break dependent modules.
 *
 * @version v0.7.0-beta
 */

import { describe, it, expect } from 'vitest';
import { state, STEP_COOLDOWN, MAX_SCROLL_DELTA, MOBILE_NAV_COOLDOWN } from '../../assets/js/telar-story/state.js';

describe('state', () => {
  it('has expected initial structure and constants', () => {
    // Constants
    expect(STEP_COOLDOWN).toBe(600);
    expect(MAX_SCROLL_DELTA).toBe(200);
    expect(MOBILE_NAV_COOLDOWN).toBe(400);

    // Navigation group
    expect(state.steps).toEqual([]);
    expect(state.currentIndex).toBe(-1);
    expect(state.scrollAccumulator).toBe(0);
    expect(state.currentObject).toBeNull();
    expect(state.lastStepChangeTime).toBe(0);

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

    // Touch group
    expect(state.touchStartY).toBe(0);
    expect(state.touchEndY).toBe(0);

    // Mobile/embed group
    expect(state.isMobileViewport).toBe(false);
    expect(state.currentMobileStep).toBe(0);
    expect(state.mobileNavButtons).toBeNull();
    expect(state.mobileNavigationCooldown).toBe(false);

    // Connection speed
    expect(state.manifestLoadTimes).toEqual([]);

    // Thresholds (computed at runtime, initially zero)
    expect(state.scrollThreshold).toBe(0);
    expect(state.touchThreshold).toBe(0);

    // Config
    expect(state.config).toEqual({
      maxViewerCards: 10,
      preloadSteps: 6,
      loadingThreshold: 5,
      minReadyViewers: 3,
    });
  });
});
