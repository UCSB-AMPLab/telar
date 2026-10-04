/**
 * Tests for lerpIiifPosition — the IIIF viewer's per-frame scroll interpolation
 *
 * The real function, not a copy of it. OpenSeadragon is faked at the boundary
 * it is reached through — `viewport.fitBounds`, the last call in the chain — so
 * everything between the scroll engine's call and that point is the shipped
 * code: the guards, the interpolation, the resting-write rule, and the focal
 * geometry `snapIiifToPosition` puts them through.
 *
 * `snapIiifToPosition` cannot be mocked from outside: `lerpIiifPosition` calls
 * it inside its own module, where a module mock does not reach. That is what a
 * previous version of this file worked around by reimplementing the function
 * under test, and the copy drifted — it returned at rest where the shipped code
 * writes the authored endpoint, so every case here asserted the opposite of
 * what runs.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { state } from '../../assets/js/telar-story/state.js';
import { lerpIiifPosition } from '../../assets/js/telar-story/iiif-card.js';
import { IiifPlate } from '../../assets/js/telar-story/plates/iiif-plate.js';

// The image the fake viewer holds, in image pixels.
const IMG = { width: 1200, height: 900 };
// The viewer's box on screen.
const CONTAINER = { x: 0, y: 0, width: 1000, height: 800, top: 0, left: 0 };

let fitBounds;

/**
 * A plate whose viewer is fake from `viewport.fitBounds` outwards.
 *
 * `imageToViewportRectangle` is the identity, so the rectangle `fitBounds`
 * receives is still in image pixels and can be read directly. Everything the
 * focal geometry does to reach it is the real code.
 */
function makePlate(objectId, sceneIndex, { isReady = true } = {}) {
  const el = document.createElement('div');
  el.className = 'viewer-plate';
  el.dataset.cardType = 'iiif';

  const plate = new IiifPlate(el, objectId, sceneIndex, 0);
  plate.isReady = isReady;
  plate.osdWrapper = {
    containerEl: { getBoundingClientRect: () => ({ ...CONTAINER }) },
  };
  plate.osdViewer = {
    world: { getItemAt: () => ({ source: { ...IMG } }) },
    viewport: {
      imageToViewportRectangle: (rect) => rect,
      fitBounds,
    },
  };
  return plate;
}

/** The centre of the rectangle the viewer was last asked to frame, in image px. */
function framedCentre() {
  const rect = fitBounds.mock.calls.at(-1)[0];
  return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
}

function makeStep(objectId, x, y, zoom) {
  return { object: objectId, x: String(x), y: String(y), zoom: String(zoom) };
}

beforeEach(() => {
  fitBounds = vi.fn();
  vi.stubGlobal('OpenSeadragon', {
    Rect: class { constructor(x, y, width, height) { Object.assign(this, { x, y, width, height }); } },
  });
  state.viewerPlates = {};
  state.stepToScene = {};
  state.cardOverlayRect = null;
  state.activeTitleCardIndex = null;
});

afterEach(() => {
  vi.unstubAllGlobals();
  state.viewerPlates = {};
});

// ── The interpolation ────────────────────────────────────────────────────────

describe('lerpIiifPosition — moving between two steps on one object', () => {
  const stepsData = [makeStep('fig1', 0.2, 0.2, 3), makeStep('fig1', 0.8, 0.8, 3)];

  beforeEach(() => {
    state.viewerPlates = { 0: makePlate('fig1', 0) };
    state.stepToScene = { 0: 0, 1: 0 };
  });

  it('frames a point between the two steps own', () => {
    lerpIiifPosition(0, 0.5, stepsData);
    expect(fitBounds).toHaveBeenCalledTimes(1);
    const mid = framedCentre();

    fitBounds.mockClear();
    state.viewerPlates[0].settledAt = null;
    lerpIiifPosition(0, 0.999, stepsData);
    const late = framedCentre();

    // Authored x and y both rise from step A to step B, so a frame later in
    // the travel is further along both. Asserted as an ordering rather than a
    // number: what the focal geometry does with a position is its own business
    // and has its own tests.
    expect(late.x).toBeGreaterThan(mid.x);
    expect(late.y).toBeGreaterThan(mid.y);
  });

  it('travels further for a later frame than an earlier one', () => {
    lerpIiifPosition(0, 0.2, stepsData);
    const early = framedCentre();

    fitBounds.mockClear();
    state.viewerPlates[0].settledAt = null;
    lerpIiifPosition(0, 0.8, stepsData);
    const late = framedCentre();

    expect(late.x).toBeGreaterThan(early.x);
  });
});

// ── At rest ──────────────────────────────────────────────────────────────────

describe('lerpIiifPosition — at rest on a step', () => {
  const stepsData = [makeStep('fig1', 0.2, 0.2, 3), makeStep('fig1', 0.8, 0.8, 3)];

  beforeEach(() => {
    state.viewerPlates = { 0: makePlate('fig1', 0) };
    state.stepToScene = { 0: 0, 1: 0 };
  });

  it('states the step own authored framing rather than one just short of it', () => {
    // The interpolation stops a fraction of a step short — the scroll settles
    // and the last frame written is the one before the boundary — so a step
    // reached this way would otherwise keep the framing of a position just
    // outside it. At rest the author's own position is stated exactly.
    lerpIiifPosition(0, 0, stepsData);
    const atRest = framedCentre();

    fitBounds.mockClear();
    state.viewerPlates[0].settledAt = null;
    lerpIiifPosition(0, 0.05, stepsData);
    const justPast = framedCentre();

    expect(atRest.x).toBeLessThan(justPast.x);
  });

  it('records what it settled on', () => {
    lerpIiifPosition(0, 0, stepsData);

    expect(state.viewerPlates[0].settledAt)
      .toEqual({ step: 0, x: 0.2, y: 0.2, zoom: 3 });
  });

  it('writes once per arrival, however long the reader stays', () => {
    // A snap is a forced layout in OSD, and at rest the same framing is true on
    // every frame.
    lerpIiifPosition(0, 0, stepsData);
    lerpIiifPosition(0, 0, stepsData);
    lerpIiifPosition(0, 0, stepsData);

    expect(fitBounds).toHaveBeenCalledTimes(1);
  });

  it('writes again when the reader comes back to the step', () => {
    lerpIiifPosition(0, 0, stepsData);
    lerpIiifPosition(0, 0.5, stepsData);   // moved off: the record is cleared
    fitBounds.mockClear();
    lerpIiifPosition(0, 0, stepsData);     // and back

    expect(fitBounds).toHaveBeenCalledTimes(1);
  });
});

// ── The guards ───────────────────────────────────────────────────────────────

describe('lerpIiifPosition — what it declines to move', () => {
  const pair = [makeStep('fig1', 0.2, 0.2, 3), makeStep('fig1', 0.8, 0.8, 3)];

  beforeEach(() => {
    state.viewerPlates = { 0: makePlate('fig1', 0) };
    state.stepToScene = { 0: 0, 1: 0 };
  });

  it('freezes across an object change', () => {
    // The plate for the next object is the thing that moves, not this viewer.
    lerpIiifPosition(0, 0.5, [makeStep('fig1', 0.2, 0.2, 3), makeStep('fig2', 0.8, 0.8, 3)]);
    expect(fitBounds).not.toHaveBeenCalled();
  });

  it('does nothing on the last step, which has nothing to travel towards', () => {
    lerpIiifPosition(0, 0, [makeStep('fig1', 0.2, 0.2, 3)]);
    expect(fitBounds).not.toHaveBeenCalled();
    expect(state.viewerPlates[0].settledAt).toBeNull();
  });

  // The viewer staying put is defended twice: here, and again in
  // computeFocalTarget, which returns null for anything non-finite. So the
  // call count alone cannot say which guard held. `settledAt` can — it is
  // written before the framing is handed on, so only the guard here keeps it
  // null — and both are asserted, because both are the behaviour owed.
  it('leaves the viewer alone when the step it leaves authored no position', () => {
    lerpIiifPosition(0, 0, [
      { object: 'fig1', x: '', y: '0.2', zoom: '3' },
      makeStep('fig1', 0.8, 0.8, 3),
    ]);
    expect(fitBounds).not.toHaveBeenCalled();
    expect(state.viewerPlates[0].settledAt).toBeNull();
  });

  it('leaves the viewer alone when the step it travels to authored none', () => {
    lerpIiifPosition(0, 0, [
      makeStep('fig1', 0.2, 0.2, 3),
      { object: 'fig1', x: '0.8', y: 'not a number', zoom: '3' },
    ]);
    expect(fitBounds).not.toHaveBeenCalled();
    expect(state.viewerPlates[0].settledAt).toBeNull();
  });

  it('waits for a viewer that is not ready yet', () => {
    state.viewerPlates = { 0: makePlate('fig1', 0, { isReady: false }) };
    lerpIiifPosition(0, 0.5, pair);
    expect(fitBounds).not.toHaveBeenCalled();
  });

  it('does nothing for a scene with no plate', () => {
    state.viewerPlates = {};
    lerpIiifPosition(0, 0.5, pair);
    expect(fitBounds).not.toHaveBeenCalled();
  });

  it('does nothing before the scene maps are built', () => {
    state.stepToScene = {};
    lerpIiifPosition(0, 0.5, pair);
    expect(fitBounds).not.toHaveBeenCalled();
  });
});

// ── Which plate it moves ─────────────────────────────────────────────────────

describe('lerpIiifPosition — a story that returns to an object', () => {
  it('moves the viewer for this scene, not the first one holding the object', () => {
    // fig1 at scenes 0 and 2, with fig2 between. Steps 4 and 5 are the second
    // run on fig1: an objectId lookup would find the scene-0 plate.
    const stepsData = [
      makeStep('fig1', 0, 0, 1), makeStep('fig1', 0, 0, 1),
      makeStep('fig2', 0, 0, 1), makeStep('fig2', 0, 0, 1),
      makeStep('fig1', 0.2, 0.2, 3), makeStep('fig1', 0.8, 0.8, 3),
    ];
    const first = makePlate('fig1', 0);
    const second = makePlate('fig1', 2);
    const firstFitBounds = vi.fn();
    first.osdViewer.viewport.fitBounds = firstFitBounds;

    state.viewerPlates = { 0: first, 1: makePlate('fig2', 1), 2: second };
    state.stepToScene = { 0: 0, 1: 0, 2: 1, 3: 1, 4: 2, 5: 2 };

    lerpIiifPosition(4, 0.5, stepsData);

    expect(fitBounds).toHaveBeenCalledTimes(1);      // the scene-2 plate
    expect(firstFitBounds).not.toHaveBeenCalled();   // not the scene-0 one
  });
});
