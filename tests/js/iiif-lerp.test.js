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
import { state, moveSeconds } from '../../assets/js/telar-story/state.js';
import {
  lerpIiifPosition, computeFocalTarget, _deriveCardPlacement,
  animateIiifToPosition, snapIiifToPosition, stopCameraMove,
} from '../../assets/js/telar-story/iiif-card.js';
import { placementTravel } from '../../assets/js/telar-story/camera-travel.js';
import { setMoveSeconds } from '../../assets/js/telar-story/card-height.js';
import { makePlate, FAKE_CONTAINER, FAKE_IMAGE } from './iiif-plate-helpers.js';

let fitBounds;

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
    state.viewerPlates = { 0: makePlate('fig1', 0, { fitBounds }) };
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

// ── Across zoom 1 ───────────────────────────────────────────────────────────

describe('lerpIiifPosition — between an overview and a detail', () => {
  // An overview places the image centre and a detail its focal point, so the
  // viewer is moved between the two settled placements. Traced on motion-check
  // with this pair, placing the interpolated x/y/zoom moved the image 119 px in
  // the one frame where the zoom crossed 1.
  const stepsData = [makeStep('fig1', 0.2, 0.3, 0.8), makeStep('fig1', 0.32, 0.38, 3.2)];

  beforeEach(() => {
    state.viewerPlates = { 0: makePlate('fig1', 0, { fitBounds }) };
    state.stepToScene = { 0: 0, 1: 0 };
  });

  /** The image's top-left corner on screen and its scale, from the last frame. */
  function framedImage() {
    const rect = fitBounds.mock.calls.at(-1)[0];
    const s = FAKE_CONTAINER.width / rect.width;
    return { x: -rect.x * s, y: -rect.y * s, s };
  }

  function frameAt(stepIndex, progress, steps = stepsData) {
    state.viewerPlates[0].settledAt = null;
    lerpIiifPosition(stepIndex, progress, steps);
    return framedImage();
  }

  /** The last frame as a placement anchored at the image's top-left corner. */
  function framedPlacement() {
    const rect = fitBounds.mock.calls.at(-1)[0];
    return {
      s: FAKE_CONTAINER.width / rect.width,
      anchorImg: { x: rect.x, y: rect.y },
      anchorPx: { x: 0, y: 0 },
    };
  }

  /** The reader's uncovered region, as the viewer computes it for these steps. */
  function readerRegion() {
    const mode = _deriveCardPlacement(null, window.innerWidth, window.innerHeight);
    return computeFocalTarget(0.2, 0.3, 0.8, FAKE_IMAGE.width, FAKE_IMAGE.height, null, mode).region;
  }

  // The move runs over its own duration on an ease-out cubic, so the frames a
  // reader sees are the travel sampled at 60 fps on that curve. At the speed
  // limit (1.33 s per unit of travel) the mean is 0.75 S/s and the cubic's
  // peak three times that, 0.0375 S a frame; 0.05 S leaves a third over it,
  // because log zoom is not the geodesic and is not exactly the eased mean.
  // Placing the blended x/y/zoom jumped 119 px in one frame here, 0.27 S.
  // Above the ceiling a frame is S/60 or more, so the pair is one under it.
  it('advances the camera under 0.05 of its travel in any frame at 60 fps, whichever way', () => {
    const region = readerRegion();
    for (const steps of [stepsData, [...stepsData].reverse()]) {
      const framedAt = (t) => { frameAt(0, t, steps); return framedPlacement(); };
      const travel = placementTravel(framedAt(0), framedAt(1), region);
      expect(moveSeconds(travel)).toBeLessThan(3);
      const frames = Math.ceil(60 * moveSeconds(travel));
      let prev = framedAt(0);
      let worst = 0;
      for (let k = 1; k <= frames; k++) {
        const cur = framedAt(1 - (1 - k / frames) ** 3);
        worst = Math.max(worst, placementTravel(prev, cur, region));
        prev = cur;
      }
      expect(worst / travel).toBeLessThan(0.05);
    }
  });

  // The last thousandth of the scroll either side moves the camera by less
  // than one 60 fps frame of the move may, so a step is arrived at, not
  // jumped to.
  it('arrives at each step on the framing the step settles on', () => {
    const region = readerRegion();
    const framedWith = (t, steps) => { frameAt(0, t, steps); return framedPlacement(); };
    const settledA = framedWith(0);
    const settledB = framedWith(0, [stepsData[1], stepsData[1]]);
    const travel = placementTravel(settledA, settledB, region);
    expect(placementTravel(framedWith(0.001), settledA, region) / travel).toBeLessThan(0.05);
    expect(placementTravel(framedWith(0.999), settledB, region) / travel).toBeLessThan(0.05);
  });
});

// ── Zoom on one side of 1 ───────────────────────────────────────────────────

describe('lerpIiifPosition — zooming between two details', () => {
  // Zoom changes by equal ratios over equal parts of the move, so a zoom from
  // 2 to 8 is at 4 half way, not at 5: a linear zoom does most of a zoom-in in
  // the first part of the move.
  beforeEach(() => {
    state.viewerPlates = { 0: makePlate('fig1', 0, { fitBounds }) };
    state.stepToScene = { 0: 0, 1: 0 };
  });

  const width = () => fitBounds.mock.calls.at(-1)[0].width;

  it('frames zoom 4 half way from zoom 2 to zoom 8', () => {
    lerpIiifPosition(0, 0.5, [makeStep('fig1', 0.4, 0.4, 2), makeStep('fig1', 0.6, 0.6, 8)]);
    const halfWay = width();
    state.viewerPlates[0].settledAt = null;
    lerpIiifPosition(0, 0, [makeStep('fig1', 0.5, 0.5, 4)]);
    expect(halfWay).toBeCloseTo(width(), 6);
  });
});

// ── At rest ──────────────────────────────────────────────────────────────────

describe('lerpIiifPosition — at rest on a step', () => {
  const stepsData = [makeStep('fig1', 0.2, 0.2, 3), makeStep('fig1', 0.8, 0.8, 3)];

  beforeEach(() => {
    state.viewerPlates = { 0: makePlate('fig1', 0, { fitBounds }) };
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

  // A scene's last step is a resting place like any other. Without the write a
  // contents jump to it springs from the framing the reader left, and an
  // immediate move to it under reduced motion leaves that framing standing.
  it('states the authored framing on the last step of the story', () => {
    lerpIiifPosition(0, 0, [makeStep('fig1', 0.2, 0.2, 3)]);
    expect(fitBounds).toHaveBeenCalledTimes(1);
    expect(state.viewerPlates[0].settledAt).toEqual({ step: 0, x: 0.2, y: 0.2, zoom: 3 });
  });

  it('states the authored framing on the last step before another object', () => {
    lerpIiifPosition(0, 0, [makeStep('fig1', 0.2, 0.2, 3), makeStep('fig2', 0.8, 0.8, 3)]);
    expect(fitBounds).toHaveBeenCalledTimes(1);
    expect(state.viewerPlates[0].settledAt).toEqual({ step: 0, x: 0.2, y: 0.2, zoom: 3 });
  });

  // A title card still active at the arrival refuses the write. The step is
  // not settled until a write has reached the viewer, so the next frame at
  // rest makes it.
  it('writes on the next frame when the first write at rest is refused', () => {
    state.activeTitleCardIndex = 0;
    lerpIiifPosition(0, 0, [makeStep('fig1', 0.2, 0.2, 3)]);
    expect(fitBounds).not.toHaveBeenCalled();
    expect(state.viewerPlates[0].settledAt).toBeNull();

    state.activeTitleCardIndex = null;
    lerpIiifPosition(0, 0, [makeStep('fig1', 0.2, 0.2, 3)]);
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
    state.viewerPlates = { 0: makePlate('fig1', 0, { fitBounds }) };
    state.stepToScene = { 0: 0, 1: 0 };
  });

  it('freezes across an object change', () => {
    // The plate for the next object is the thing that moves, not this viewer.
    lerpIiifPosition(0, 0.5, [makeStep('fig1', 0.2, 0.2, 3), makeStep('fig2', 0.8, 0.8, 3)]);
    expect(fitBounds).not.toHaveBeenCalled();
  });

  it('moves nothing past the last step, which has nothing to travel towards', () => {
    lerpIiifPosition(0, 0.5, [makeStep('fig1', 0.2, 0.2, 3)]);
    expect(fitBounds).not.toHaveBeenCalled();
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
    state.viewerPlates = { 0: makePlate('fig1', 0, { fitBounds, isReady: false }) };
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
    const first = makePlate('fig1', 0, { fitBounds });
    const second = makePlate('fig1', 2, { fitBounds });
    const firstFitBounds = vi.fn();
    first.osdViewer.viewport.fitBounds = firstFitBounds;

    state.viewerPlates = { 0: first, 1: makePlate('fig2', 1, { fitBounds }), 2: second };
    state.stepToScene = { 0: 0, 1: 0, 2: 1, 3: 1, 4: 2, 5: 2 };

    lerpIiifPosition(4, 0.5, stepsData);

    expect(fitBounds).toHaveBeenCalledTimes(1);      // the scene-2 plate
    expect(firstFitBounds).not.toHaveBeenCalled();   // not the scene-0 one
  });
});

// ── A move with no scroll to pace it ─────────────────────────────────────────
//
// On a phone, and on a contents jump's second activation, nothing scrolls, so
// the camera is moved by an animation of its own: the same interpolation and
// easing as the scroll's, over the duration of the move the cards are making.
// OpenSeadragon's springs are left alone, because the reader's own gestures
// on the image run on them.

describe('animateIiifToPosition — the camera moved without a scroll', () => {
  let frames;
  let plate;

  /** Run the frame the animation asked for, at `ms`. */
  function runFrame(ms) {
    const queued = frames;
    frames = [];
    queued.forEach((cb) => cb(ms));
  }

  beforeEach(() => {
    frames = [];
    vi.stubGlobal('requestAnimationFrame', (cb) => { frames.push(cb); return frames.length; });
    plate = makePlate('fig1', 0, { fitBounds });
    plate.osdViewer.animationTime = 0.4;
    plate.osdViewer.springStiffness = 6.5;
    plate.osdViewer.gestureSettingsMouse = {};
    plate.osdViewer.gestureSettingsTouch = {};
    plate.osdViewer.viewport.getBounds = () => ({ x: 0, y: 0, width: 1200, height: 960 });
    plate.osdViewer.viewport.viewportToImageRectangle = (rect) => rect;
    setMoveSeconds(2);
  });

  afterEach(() => setMoveSeconds(1.2));

  /** The rectangle a snap to this framing asks for. */
  function snapRect(x, y, zoom) {
    const other = makePlate('fig1', 0, { fitBounds: vi.fn() });
    snapIiifToPosition(other, x, y, zoom);
    return other.osdViewer.viewport.fitBounds.mock.calls[0][0];
  }

  it('writes every frame at once and lands on the framing at the duration of the move', () => {
    animateIiifToPosition(plate, 0.3, 0.4, 3);
    runFrame(1000);
    runFrame(1500);
    runFrame(2999);
    expect(frames.length).toBe(1);
    runFrame(3000);

    expect(fitBounds.mock.calls.length).toBe(4);
    expect(fitBounds.mock.calls.every(([, immediate]) => immediate === true)).toBe(true);
    const last = fitBounds.mock.calls.at(-1)[0];
    const want = snapRect(0.3, 0.4, 3);
    for (const k of ['x', 'y', 'width', 'height']) expect(last[k]).toBeCloseTo(want[k], 6);
    expect(frames.length).toBe(0);
  });

  it('leaves the viewer\'s spring settings as they are', () => {
    animateIiifToPosition(plate, 0.3, 0.4, 3);
    runFrame(0);
    runFrame(2000);
    expect(plate.osdViewer.animationTime).toBe(0.4);
    expect(plate.osdViewer.springStiffness).toBe(6.5);
  });

  it('stops a move when a newer one starts', () => {
    animateIiifToPosition(plate, 0.3, 0.4, 3);
    runFrame(0);
    const older = frames;
    frames = [];
    animateIiifToPosition(plate, 0.6, 0.6, 2);
    const newer = frames;
    fitBounds.mockClear();
    older.forEach((cb) => cb(500));
    expect(fitBounds).not.toHaveBeenCalled();
    frames = newer;
    runFrame(500);
    expect(fitBounds).toHaveBeenCalledTimes(1);
  });

  it('stops when the reader takes the image, and when the scroll writes it', () => {
    animateIiifToPosition(plate, 0.3, 0.4, 3);
    runFrame(0);
    stopCameraMove(plate);
    fitBounds.mockClear();
    runFrame(500);
    expect(fitBounds).not.toHaveBeenCalled();

    animateIiifToPosition(plate, 0.3, 0.4, 3);
    runFrame(0);
    snapIiifToPosition(plate, 0.5, 0.5, 1);
    fitBounds.mockClear();
    runFrame(500);
    expect(fitBounds).not.toHaveBeenCalled();
  });
});

// ── Reduced motion ───────────────────────────────────────────────────────────
//
// Under reduced motion the cards do not slide (their transitions are none) and
// Lenis makes every programmatic scroll immediate, so the camera follows: it
// is written at once, wherever it is written from.

describe('animateIiifToPosition — under reduced motion', () => {
  beforeEach(() => {
    vi.stubGlobal('requestAnimationFrame', vi.fn());
    vi.spyOn(window, 'matchMedia').mockImplementation((query) => ({
      matches: query === '(prefers-reduced-motion: reduce)', media: query,
      addEventListener() {}, removeEventListener() {},
    }));
  });

  afterEach(() => vi.restoreAllMocks());

  it('writes the framing at once, with no frames to follow', () => {
    const plate = makePlate('fig1', 0, { fitBounds });
    plate.osdViewer.gestureSettingsMouse = {};
    plate.osdViewer.gestureSettingsTouch = {};
    animateIiifToPosition(plate, 0.3, 0.4, 3);
    expect(fitBounds).toHaveBeenCalledTimes(1);
    expect(fitBounds.mock.calls[0][1]).toBe(true);
    expect(requestAnimationFrame).not.toHaveBeenCalled();
  });
});

// ── A viewer the plate lets go of ────────────────────────────────────────────

describe('animateIiifToPosition — across an unload', () => {
  it('writes nothing to the viewer that replaces the one it was moving', () => {
    const frames = [];
    vi.stubGlobal('requestAnimationFrame', (cb) => { frames.push(cb); return frames.length; });
    const plate = makePlate('fig1', 0, { fitBounds });
    plate.osdViewer.gestureSettingsMouse = {};
    plate.osdViewer.gestureSettingsTouch = {};
    plate.osdViewer.viewport.getBounds = () => ({ x: 0, y: 0, width: 1200, height: 960 });
    plate.osdViewer.viewport.viewportToImageRectangle = (rect) => rect;
    plate.container.innerHTML = '';

    animateIiifToPosition(plate, 0.3, 0.4, 3);
    plate.unload();

    // The same plate is loaded again before the old move's frame runs.
    const replacement = vi.fn();
    const again = makePlate('fig1', 0, { fitBounds: replacement });
    Object.assign(plate, { isReady: true, osdWrapper: again.osdWrapper, osdViewer: again.osdViewer });
    plate.osdViewer.viewport.getBounds = () => ({ x: 0, y: 0, width: 1200, height: 960 });
    plate.osdViewer.viewport.viewportToImageRectangle = (rect) => rect;

    frames.forEach((cb) => cb(0));
    expect(replacement).not.toHaveBeenCalled();
  });
});
