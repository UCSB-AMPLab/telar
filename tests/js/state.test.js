/**
 * Tests for Telar Story – Centralised State
 *
 * Verifies the initial state shape that all other modules depend on.
 * This is a contract test, not a logic test — it catches accidental
 * deletions or renames of state keys that would break dependent modules.
 *
 * @version v1.8.0
 */

import { describe, it, expect, afterEach } from 'vitest';
import { state, MOBILE_NAV_COOLDOWN, moveSeconds } from '../../assets/js/telar-story/state.js';

describe('state', () => {
  it('has expected initial structure and constants', () => {
    // Constants — STEP_COOLDOWN and MAX_SCROLL_DELTA removed in v1.0.0-beta
    expect(MOBILE_NAV_COOLDOWN).toBe(400);

    // Navigation group
    expect(state.steps).toEqual([]);
    expect(state.currentIndex).toBe(-1);

    // Scroll engine group (replaces scrollAccumulator)
    expect(state.scrollPosition).toBe(0);
    expect(state.scrollProgress).toBe(0);
    expect(state.isSnapping).toBe(false);
    expect(state.lenis).toBeNull();
    expect(state.snap).toBeNull();

    expect(state.objectsIndex).toEqual({});

    // Panels group
    expect(state.panelStack).toEqual([]);
    expect(state.isPanelOpen).toBe(false);
    expect(state.scrollLockActive).toBe(false);
    expect(state.creditsDismissed).toBe(false);

    // Autoplay policy group
    expect(state).toHaveProperty('hasUserInteracted', false);

    // Layout mode & embed group
    expect(state.layoutMode).toBe('horizontal');
    expect(state.isEmbed).toBe(false);
    expect(state.cardOverlayRect).toBeNull();
    expect(state).not.toHaveProperty('isMobileViewport');  // layout-mode contract

    // Mobile button navigation group
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
    // currentObject / currentViewerCard: unused single-value viewer tracking
    // fields, superseded by viewerPlates.
    expect(state.currentObject).toBeUndefined();
    expect(state.currentViewerCard).toBeUndefined();
  });

  it('keeps no viewer pool beside the plates', () => {
    // A viewer belongs to the plate that holds it. A second structure listing
    // viewers is the duplication the plate types were built to remove, and the
    // two disagreeing is what it cost.
    expect(state.viewerCards).toBeUndefined();
    expect(state.viewerCardCounter).toBeUndefined();
  });
});

// One duration per move, set by how far the camera travels: 1.33 s per unit of
// travel, never under the 1.2 s base and never over the 3 s ceiling.
describe('moveSeconds', () => {
  afterEach(() => history.replaceState(null, '', '/'));

  it('gives a short move the base', () => {
    expect(moveSeconds(0)).toBe(1.2);
    expect(moveSeconds(0.3)).toBe(1.2);
  });

  it('gives a long move 1.33 s per unit of travel', () => {
    expect(moveSeconds(1.97)).toBeCloseTo(2.62, 2);
  });

  it('holds the longest move at the ceiling', () => {
    expect(moveSeconds(5)).toBe(3);
  });

  it('takes the base, the rate and the ceiling from ?nav=', () => {
    history.replaceState(null, '', '/?nav=1,2,4');
    expect(moveSeconds(0.2)).toBe(1);
    expect(moveSeconds(1.5)).toBe(3);
    expect(moveSeconds(5)).toBe(4);
  });

  it('gives every move the base when ?nav= sets the rate to 0', () => {
    history.replaceState(null, '', '/?nav=1.2,0');
    expect(moveSeconds(5)).toBe(1.2);
  });

  it('keeps the defaults for a value out of range', () => {
    history.replaceState(null, '', '/?nav=99,-1,0');
    expect(moveSeconds(1.97)).toBeCloseTo(2.62, 2);
  });
});
