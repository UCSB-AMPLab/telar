/**
 * Tests for Telar Story – Card Pool (pure functions only)
 *
 * Tests z-index banding, messiness computation, peek positioning, and
 * scene map helpers (buildSceneMaps, getSceneIndex).
 * DOM-interacting functions (initCardPool, activateCard, preloadAhead)
 * are not tested here — they require a real browser environment.
 *
 * @version v1.0.0-beta
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  getObjectZBase,
  getViewerPlateZIndex,
  getTextCardZIndex,
  getCardMessiness,
  computeCardTop,
  getSceneIndex,
  buildSceneMaps,
} from '../../assets/js/telar-story/card-pool.js';
import { state } from '../../assets/js/telar-story/state.js';

// ── Z-index banding ───────────────────────────────────────────────────────────

describe('getObjectZBase', () => {
  it('returns 100 for object 0', () => {
    expect(getObjectZBase(0)).toBe(100);
  });

  it('returns 200 for object 1', () => {
    expect(getObjectZBase(1)).toBe(200);
  });
});

describe('getViewerPlateZIndex', () => {
  it('returns 100 for object 0 (base of band)', () => {
    expect(getViewerPlateZIndex(0)).toBe(100);
  });
});

describe('getTextCardZIndex', () => {
  it('returns 101 for object 0, run position 0', () => {
    expect(getTextCardZIndex(0, 0)).toBe(101);
  });

  it('returns 103 for object 0, run position 2', () => {
    expect(getTextCardZIndex(0, 2)).toBe(103);
  });

  it('returns 201 for object 1, run position 0', () => {
    expect(getTextCardZIndex(1, 0)).toBe(201);
  });
});

// ── Messiness ─────────────────────────────────────────────────────────────────

describe('getCardMessiness', () => {
  it('returns zeros when messiness is 0', () => {
    const result = getCardMessiness(0, 0);
    expect(result).toEqual({ rot: 0, offX: 0, offY: 0 });
  });

  it('returns values within bounds for messiness 20', () => {
    // Test several seeds to ensure bounds are respected
    for (let seed = 0; seed < 20; seed++) {
      const { rot, offX, offY } = getCardMessiness(seed, 20);
      expect(Math.abs(rot)).toBeLessThanOrEqual(0.24);
      expect(Math.abs(offX)).toBeLessThanOrEqual(1.6);
      expect(Math.abs(offY)).toBeLessThanOrEqual(0.8);
    }
  });

  it('returns identical values on repeated calls (deterministic)', () => {
    const a = getCardMessiness(7, 20);
    const b = getCardMessiness(7, 20);
    expect(a).toEqual(b);
  });
});

// ── Peek positioning ──────────────────────────────────────────────────────────

describe('computeCardTop', () => {
  it('returns 75 when centred (viewportH=1000, cardH=850, runPos=0, peekH=1)', () => {
    // (1000 - 850) / 2 = 75
    expect(computeCardTop(1000, 850, 0, 1)).toBe(75);
  });

  it('returns 76 when runPosition=1, peekH=1', () => {
    // 75 + 1 * 1 = 76
    expect(computeCardTop(1000, 850, 1, 1)).toBe(76);
  });

  it('returns 78 when runPosition=3, peekH=1', () => {
    // 75 + 3 * 1 = 78
    expect(computeCardTop(1000, 850, 3, 1)).toBe(78);
  });

  it('returns 75 when peekHeight is 0 (disabled)', () => {
    // 75 + 0 * 0 = 75
    expect(computeCardTop(1000, 850, 0, 0)).toBe(75);
  });
});

// ── Scene maps ────────────────────────────────────────────────────────────────

describe('buildSceneMaps / getSceneIndex', () => {
  beforeEach(() => {
    // Reset state scene maps before each test
    state.stepToScene = {};
    state.sceneToObject = {};
    state.sceneFirstStep = {};
    state.totalScenes = 0;
  });

  it('maps A,A,B,A to 3 scenes', () => {
    buildSceneMaps([{ object: 'A' }, { object: 'A' }, { object: 'B' }, { object: 'A' }]);
    expect(state.totalScenes).toBe(3);
    expect(getSceneIndex(0)).toBe(0);
    expect(getSceneIndex(1)).toBe(0);
    expect(getSceneIndex(2)).toBe(1);
    expect(getSceneIndex(3)).toBe(2);
    expect(state.sceneToObject[0]).toBe('A');
    expect(state.sceneToObject[1]).toBe('B');
    expect(state.sceneToObject[2]).toBe('A');
    expect(state.sceneFirstStep[0]).toBe(0);
    expect(state.sceneFirstStep[1]).toBe(2);
    expect(state.sceneFirstStep[2]).toBe(3);
  });

  it('single-object story has 1 scene', () => {
    buildSceneMaps([{ object: 'X' }, { object: 'X' }, { object: 'X' }]);
    expect(state.totalScenes).toBe(1);
    expect(getSceneIndex(0)).toBe(0);
    expect(getSceneIndex(1)).toBe(0);
    expect(getSceneIndex(2)).toBe(0);
  });

  it('empty steps produces 0 scenes', () => {
    buildSceneMaps([]);
    expect(state.totalScenes).toBe(0);
  });

  it('returns -1 for out-of-range step', () => {
    buildSceneMaps([{ object: 'A' }]);
    expect(getSceneIndex(999)).toBe(-1);
  });
});
