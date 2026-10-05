/**
 * Tests for the click-to-zoom hold of animateIiifToPosition, and for a move
 * that starts where it ends.
 *
 * A move turns the viewer's two click-to-zoom settings off so a tap during it
 * does not zoom; the settings are the viewer's own and come back when the
 * move ends or is stopped. OpenSeadragon is faked at `viewport.fitBounds`, as
 * in iiif-lerp.test.js.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { state } from '../../assets/js/telar-story/state.js';
import {
  animateIiifToPosition, snapIiifToPosition, stopCameraMove,
} from '../../assets/js/telar-story/iiif-card.js';
import { setMoveSeconds } from '../../assets/js/telar-story/card-height.js';
import { makePlate } from './iiif-plate-helpers.js';

let fitBounds;
let frames;
let plate;

/** Run the frames the move asked for, at `ms`. */
function runQueuedFrames(ms) {
  const queued = frames;
  frames = [];
  queued.forEach((cb) => cb(ms));
}

/** A plate whose viewer shows a rectangle that is not any framing's. */
function gesturePlate(mouse = true, touch = true) {
  const p = makePlate('fig1', 0, { fitBounds });
  p.osdViewer.gestureSettingsMouse = { clickToZoom: mouse };
  p.osdViewer.gestureSettingsTouch = { clickToZoom: touch };
  p.osdViewer.viewport.getBounds = () => ({ x: 0, y: 0, width: 1200, height: 960 });
  p.osdViewer.viewport.viewportToImageRectangle = (rect) => rect;
  return p;
}

const clicks = () => [
  plate.osdViewer.gestureSettingsMouse.clickToZoom,
  plate.osdViewer.gestureSettingsTouch.clickToZoom,
];

beforeEach(() => {
  fitBounds = vi.fn();
  frames = [];
  vi.stubGlobal('OpenSeadragon', {
    Rect: class { constructor(x, y, width, height) { Object.assign(this, { x, y, width, height }); } },
  });
  vi.stubGlobal('requestAnimationFrame', (cb) => { frames.push(cb); return frames.length; });
  state.viewerPlates = {};
  state.stepToScene = {};
  state.cardOverlayRect = null;
  state.activeTitleCardIndex = null;
  setMoveSeconds(2);
  plate = gesturePlate();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  setMoveSeconds(1.2);
});

describe('animateIiifToPosition — click-to-zoom', () => {
  it('is off during a move and back after the last frame', () => {
    animateIiifToPosition(plate, 0.3, 0.4, 3);
    expect(clicks()).toEqual([false, false]);
    runQueuedFrames(0);
    runQueuedFrames(1000);
    expect(clicks()).toEqual([false, false]);
    runQueuedFrames(2000);
    expect(frames.length).toBe(0);
    expect(clicks()).toEqual([true, true]);
  });

  it('is back when the move is stopped', () => {
    animateIiifToPosition(plate, 0.3, 0.4, 3);
    runQueuedFrames(0);
    stopCameraMove(plate);
    expect(clicks()).toEqual([true, true]);
  });

  it('is back when a snap takes the viewer', () => {
    animateIiifToPosition(plate, 0.3, 0.4, 3);
    runQueuedFrames(0);
    snapIiifToPosition(plate, 0.5, 0.5, 1);
    expect(clicks()).toEqual([true, true]);
  });

  it('is back after the single write under reduced motion', () => {
    vi.spyOn(window, 'matchMedia').mockImplementation((query) => ({
      matches: query === '(prefers-reduced-motion: reduce)', media: query,
      addEventListener() {}, removeEventListener() {},
    }));
    animateIiifToPosition(plate, 0.3, 0.4, 3);
    expect(fitBounds).toHaveBeenCalledTimes(1);
    expect(clicks()).toEqual([true, true]);
  });

  it('keeps the mouse setting off on a viewer built without zoom gestures', () => {
    plate = gesturePlate(false, true);
    animateIiifToPosition(plate, 0.3, 0.4, 3);
    runQueuedFrames(0);
    runQueuedFrames(2000);
    expect(clicks()).toEqual([false, true]);
  });

  it('restores the original values when a second move replaces the first', () => {
    animateIiifToPosition(plate, 0.3, 0.4, 3);
    runQueuedFrames(0);
    animateIiifToPosition(plate, 0.6, 0.6, 2);
    expect(clicks()).toEqual([false, false]);
    runQueuedFrames(0);
    runQueuedFrames(2000);
    expect(frames.length).toBe(0);
    expect(clicks()).toEqual([true, true]);
  });
});

describe('animateIiifToPosition — a camera already at the framing', () => {
  /** Show exactly the rectangle a snap to this framing asks for. */
  function showFraming(x, y, zoom) {
    const other = gesturePlate();
    other.osdViewer.viewport.fitBounds = vi.fn();
    snapIiifToPosition(other, x, y, zoom);
    const r = other.osdViewer.viewport.fitBounds.mock.calls[0][0];
    plate.osdViewer.viewport.getBounds = () => ({ ...r });
  }

  it('writes once, schedules no second frame and gives click-to-zoom back', () => {
    showFraming(0.3, 0.4, 3);
    animateIiifToPosition(plate, 0.3, 0.4, 3);
    runQueuedFrames(0);
    expect(fitBounds).toHaveBeenCalledTimes(1);
    expect(frames.length).toBe(0);
    expect(clicks()).toEqual([true, true]);
  });

  it('still travels from a framing that is somewhere else', () => {
    showFraming(0.6, 0.6, 2);
    animateIiifToPosition(plate, 0.3, 0.4, 3);
    runQueuedFrames(0);
    expect(frames.length).toBe(1);
  });
});
