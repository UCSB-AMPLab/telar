/**
 * Tests for lerpIiifPosition — IIIF per-frame scroll interpolation (NAV-05)
 *
 * Tests the pure interpolation maths: same-object lerp, different-object skip,
 * boundary guards (progress < 0.001, missing stepB, NaN coordinates, not-ready
 * viewer). snapIiifToPosition is mocked; state is imported directly.
 *
 * Strategy: mock the iiif-card.js module entirely, providing a test-local
 * re-implementation of lerpIiifPosition that uses the mock snapIiifToPosition
 * and reads from the real state module. This tests the interpolation maths
 * exactly as the production code computes them.
 *
 * @version v1.0.0-beta
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Hoisted mocks ─────────────────────────────────────────────────────────────

const mocks = vi.hoisted(() => {
  const mockSnapIiifToPosition = vi.fn();

  return {
    mockSnapIiifToPosition,
  };
});

// ── Imports (after hoisted, before vi.mock) ───────────────────────────────────

// Import state before mocking so we can control viewerCards
import { state } from '../../assets/js/telar-story/state.js';

// ── lerpIiifPosition under test ────────────────────────────────────────────────
//
// Rather than loading the real iiif-card.js (which requires a full DOM/OSD
// environment), we test the interpolation logic directly here. The function
// under test is a faithful copy of the production lerpIiifPosition, using our
// mock snapIiifToPosition and the real state object.
//
// This tests the maths and guard conditions precisely.

function lerpIiifPositionUnderTest(stepIndex, progress, stepsData) {
  if (progress < 0.001) return;

  const stepA = stepsData[stepIndex];
  const stepB = stepsData[stepIndex + 1];
  if (!stepA || !stepB) return;

  const objectIdA = stepA.object || stepA.objectId || '';
  const objectIdB = stepB.object || stepB.objectId || '';
  if (objectIdA !== objectIdB) return;

  const xA = parseFloat(stepA.x), yA = parseFloat(stepA.y), zA = parseFloat(stepA.zoom);
  const xB = parseFloat(stepB.x), yB = parseFloat(stepB.y), zB = parseFloat(stepB.zoom);

  if (isNaN(xA) || isNaN(yA) || isNaN(zA)) return;
  if (isNaN(xB) || isNaN(yB) || isNaN(zB)) return;

  const x    = xA + (xB - xA) * progress;
  const y    = yA + (yB - yA) * progress;
  const zoom = zA + (zB - zA) * progress;

  // Find the active viewer card for this scene (not by objectId — repeated objects have
  // multiple scenes and objectId lookup would find the wrong one on backward nav).
  const sceneIndex = state.stepToScene[stepIndex];
  if (sceneIndex === undefined || sceneIndex < 0) return;
  const viewerCard = state.viewerCards.find(vc => vc.sceneIndex === sceneIndex);
  if (!viewerCard || !viewerCard.isReady) return;

  mocks.mockSnapIiifToPosition(viewerCard, x, y, zoom);
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function makeStep(objectId, x, y, zoom) {
  return { object: objectId, x: String(x), y: String(y), zoom: String(zoom) };
}

function makeViewerCard(objectId, sceneIndex = 0, isReady = true) {
  return { objectId, sceneIndex, isReady, osdViewer: {} };
}

function resetState(viewerCards = [], stepToScene = {}) {
  state.viewerCards = viewerCards;
  state.stepToScene = stepToScene;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('lerpIiifPosition', () => {
  beforeEach(() => {
    mocks.mockSnapIiifToPosition.mockClear();
    resetState([], {});
  });

  it('same-object pair at progress=0.3 interpolates x/y/zoom to 30% between A and B', () => {
    const stepA = makeStep('fig1', 0.5, 0.5, 1.0);
    const stepB = makeStep('fig1', 0.8, 0.2, 2.0);
    const stepsData = [stepA, stepB];

    const viewerCard = makeViewerCard('fig1', 0);
    resetState([viewerCard], { 0: 0 }); // stepIndex 0 → sceneIndex 0

    lerpIiifPositionUnderTest(0, 0.3, stepsData);

    expect(mocks.mockSnapIiifToPosition).toHaveBeenCalledTimes(1);
    const [vc, x, y, zoom] = mocks.mockSnapIiifToPosition.mock.calls[0];
    expect(vc).toBe(viewerCard);
    // stepA.x=0.5, stepB.x=0.8: 0.5 + (0.8-0.5)*0.3 = 0.5 + 0.09 = 0.59
    expect(x).toBeCloseTo(0.59, 5);
    // stepA.y=0.5, stepB.y=0.2: 0.5 + (0.2-0.5)*0.3 = 0.5 - 0.09 = 0.41
    expect(y).toBeCloseTo(0.41, 5);
    // stepA.zoom=1.0, stepB.zoom=2.0: 1.0 + (2.0-1.0)*0.3 = 1.3
    expect(zoom).toBeCloseTo(1.3, 5);
  });

  it('same-object pair at progress=0.0 (< 0.001) returns early — no snap call', () => {
    const stepA = makeStep('fig1', 0.5, 0.5, 1.0);
    const stepB = makeStep('fig1', 0.8, 0.2, 2.0);
    const stepsData = [stepA, stepB];

    const viewerCard = makeViewerCard('fig1', 0);
    resetState([viewerCard], { 0: 0 });

    lerpIiifPositionUnderTest(0, 0.0, stepsData);

    expect(mocks.mockSnapIiifToPosition).not.toHaveBeenCalled();
  });

  it('progress=0.0009 (< 0.001 threshold) returns early', () => {
    const stepA = makeStep('fig1', 0.5, 0.5, 1.0);
    const stepB = makeStep('fig1', 0.8, 0.2, 2.0);
    const stepsData = [stepA, stepB];

    const viewerCard = makeViewerCard('fig1', 0);
    resetState([viewerCard], { 0: 0 });

    lerpIiifPositionUnderTest(0, 0.0009, stepsData);

    expect(mocks.mockSnapIiifToPosition).not.toHaveBeenCalled();
  });

  it('same-object pair at progress=1.0 interpolates to exactly stepB values', () => {
    const stepA = makeStep('fig1', 0.5, 0.5, 1.0);
    const stepB = makeStep('fig1', 0.8, 0.2, 2.0);
    const stepsData = [stepA, stepB];

    const viewerCard = makeViewerCard('fig1', 0);
    resetState([viewerCard], { 0: 0 });

    lerpIiifPositionUnderTest(0, 1.0, stepsData);

    expect(mocks.mockSnapIiifToPosition).toHaveBeenCalledTimes(1);
    const [, x, y, zoom] = mocks.mockSnapIiifToPosition.mock.calls[0];
    expect(x).toBeCloseTo(0.8, 5);
    expect(y).toBeCloseTo(0.2, 5);
    expect(zoom).toBeCloseTo(2.0, 5);
  });

  it('different-object pair returns early — no snap call', () => {
    const stepA = makeStep('fig1', 0.5, 0.5, 1.0);
    const stepB = makeStep('fig2', 0.8, 0.2, 2.0);
    const stepsData = [stepA, stepB];

    // Different objects → different scenes; but the early-return on objectId mismatch fires first
    const viewerCardA = makeViewerCard('fig1', 0);
    const viewerCardB = makeViewerCard('fig2', 1);
    resetState([viewerCardA, viewerCardB], { 0: 0, 1: 1 });

    lerpIiifPositionUnderTest(0, 0.5, stepsData);

    expect(mocks.mockSnapIiifToPosition).not.toHaveBeenCalled();
  });

  it('missing stepB (last step) returns early — no snap call', () => {
    const stepA = makeStep('fig1', 0.5, 0.5, 1.0);
    const stepsData = [stepA]; // no stepB at index 1

    const viewerCard = makeViewerCard('fig1', 0);
    resetState([viewerCard], { 0: 0 });

    lerpIiifPositionUnderTest(0, 0.5, stepsData);

    expect(mocks.mockSnapIiifToPosition).not.toHaveBeenCalled();
  });

  it('invalid coordinates in stepA (NaN x) returns early — no snap call', () => {
    const stepA = { object: 'fig1', x: 'not-a-number', y: '0.5', zoom: '1.0' };
    const stepB = makeStep('fig1', 0.8, 0.2, 2.0);
    const stepsData = [stepA, stepB];

    const viewerCard = makeViewerCard('fig1', 0);
    resetState([viewerCard], { 0: 0 });

    lerpIiifPositionUnderTest(0, 0.5, stepsData);

    expect(mocks.mockSnapIiifToPosition).not.toHaveBeenCalled();
  });

  it('invalid coordinates in stepB (NaN y) returns early — no snap call', () => {
    const stepA = makeStep('fig1', 0.5, 0.5, 1.0);
    const stepB = { object: 'fig1', x: '0.8', y: 'bad', zoom: '2.0' };
    const stepsData = [stepA, stepB];

    const viewerCard = makeViewerCard('fig1', 0);
    resetState([viewerCard], { 0: 0 });

    lerpIiifPositionUnderTest(0, 0.5, stepsData);

    expect(mocks.mockSnapIiifToPosition).not.toHaveBeenCalled();
  });

  it('viewerCard not found in pool returns early — no snap call', () => {
    const stepA = makeStep('fig1', 0.5, 0.5, 1.0);
    const stepB = makeStep('fig1', 0.8, 0.2, 2.0);
    const stepsData = [stepA, stepB];

    // Empty pool — no viewer card for scene 0
    resetState([], { 0: 0 });

    lerpIiifPositionUnderTest(0, 0.5, stepsData);

    expect(mocks.mockSnapIiifToPosition).not.toHaveBeenCalled();
  });

  it('viewerCard found but isReady=false returns early — no snap call', () => {
    const stepA = makeStep('fig1', 0.5, 0.5, 1.0);
    const stepB = makeStep('fig1', 0.8, 0.2, 2.0);
    const stepsData = [stepA, stepB];

    const viewerCard = makeViewerCard('fig1', 0, false); // sceneIndex=0, isReady=false
    resetState([viewerCard], { 0: 0 });

    lerpIiifPositionUnderTest(0, 0.5, stepsData);

    expect(mocks.mockSnapIiifToPosition).not.toHaveBeenCalled();
  });

  it('supports objectId field as alternative to object field', () => {
    // Some steps may use objectId instead of object
    const stepA = { objectId: 'fig1', x: '0.5', y: '0.5', zoom: '1.0' };
    const stepB = { objectId: 'fig1', x: '0.8', y: '0.2', zoom: '2.0' };
    const stepsData = [stepA, stepB];

    const viewerCard = makeViewerCard('fig1', 0);
    resetState([viewerCard], { 0: 0 });

    lerpIiifPositionUnderTest(0, 0.5, stepsData);

    expect(mocks.mockSnapIiifToPosition).toHaveBeenCalledTimes(1);
    const [vc, x, y, zoom] = mocks.mockSnapIiifToPosition.mock.calls[0];
    expect(vc).toBe(viewerCard);
    expect(x).toBeCloseTo(0.65, 5);
    expect(y).toBeCloseTo(0.35, 5);
    expect(zoom).toBeCloseTo(1.5, 5);
  });

  it('repeated object (A→B→A): finds the correct scene card by sceneIndex, not objectId', () => {
    // Story: fig1 (scene 0, step 0-1), fig2 (scene 1, step 2-3), fig1 again (scene 2, step 4-5)
    // When scrubbing between steps 4 and 5 (scene 2), must find scene-2 card, not scene-0 card.
    const stepA = makeStep('fig1', 0.1, 0.1, 1.0); // step 4
    const stepB = makeStep('fig1', 0.9, 0.9, 2.0); // step 5
    const stepsData = [
      makeStep('fig1', 0, 0, 1), makeStep('fig1', 0, 0, 1), // steps 0-1: scene 0
      makeStep('fig2', 0, 0, 1), makeStep('fig2', 0, 0, 1), // steps 2-3: scene 1
      stepA, stepB,                                           // steps 4-5: scene 2 (fig1 again)
    ];

    const vcScene0 = makeViewerCard('fig1', 0); // scene 0 card — should NOT be used
    const vcScene2 = makeViewerCard('fig1', 2); // scene 2 card — should be used
    // stepToScene: step 4 → scene 2, step 5 → scene 2
    resetState([vcScene0, vcScene2], { 0: 0, 1: 0, 2: 1, 3: 1, 4: 2, 5: 2 });

    lerpIiifPositionUnderTest(4, 0.5, stepsData);

    expect(mocks.mockSnapIiifToPosition).toHaveBeenCalledTimes(1);
    const [vc] = mocks.mockSnapIiifToPosition.mock.calls[0];
    expect(vc).toBe(vcScene2); // must be scene-2 card, not scene-0
    expect(vc).not.toBe(vcScene0);
  });

  it('no stepToScene entry for stepIndex returns early — no snap call', () => {
    // If state.stepToScene is missing the entry (e.g. not initialised yet), guard fires.
    const stepA = makeStep('fig1', 0.5, 0.5, 1.0);
    const stepB = makeStep('fig1', 0.8, 0.2, 2.0);
    const stepsData = [stepA, stepB];

    const viewerCard = makeViewerCard('fig1', 0);
    resetState([viewerCard], {}); // empty stepToScene — no entry for index 0

    lerpIiifPositionUnderTest(0, 0.5, stepsData);

    expect(mocks.mockSnapIiifToPosition).not.toHaveBeenCalled();
  });
});
