/**
 * Tests for reSnapActiveViewer — the re-frame after a resize or layout change.
 *
 * It reads the active step's cells and snaps the active viewer to them. What
 * matters is that it reads the cells the way activation does: a blank or
 * unreadable cell falls back to the whole object, through `stepFraming`, and a
 * readable one is used as authored. Each case compares the rectangle the
 * viewer is asked to frame with the one `snapIiifToPosition` frames for the
 * framing the step should get, so the focal geometry is the real code on both
 * sides and the case is about the reading alone.
 *
 * @version v1.8.0
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { state } from '../../assets/js/telar-story/state.js';
import { reSnapActiveViewer, snapIiifToPosition } from '../../assets/js/telar-story/iiif-card.js';
import { makePlate } from './iiif-plate-helpers.js';

let fitBounds;

/** The rectangle the re-snap asks for, with the active step's cells set to `cells`. */
function reSnapped(cells) {
  window.storyData = { steps: [{ _metadata: true }, { object: 'fig1', ...cells }] };
  fitBounds.mockClear();
  reSnapActiveViewer();
  expect(fitBounds).toHaveBeenCalledTimes(1);
  return fitBounds.mock.calls[0][0];
}

/** The rectangle a direct snap to (x, y, zoom) asks for. */
function snappedTo(x, y, zoom) {
  fitBounds.mockClear();
  snapIiifToPosition(state.viewerPlates[0], x, y, zoom);
  return fitBounds.mock.calls[0][0];
}

beforeEach(() => {
  fitBounds = vi.fn();
  vi.stubGlobal('OpenSeadragon', {
    Rect: class { constructor(x, y, width, height) { Object.assign(this, { x, y, width, height }); } },
  });
  state.viewerPlates = { 0: makePlate('fig1', 0, { fitBounds, active: true }) };
  state.cardOverlayRect = null;
  state.activeTitleCardIndex = null;
  document.body.innerHTML = '<div class="text-card is-active" data-step-index="0"></div>';
});

afterEach(() => {
  vi.unstubAllGlobals();
  state.viewerPlates = {};
  delete window.storyData;
  document.body.innerHTML = '';
});

describe('reSnapActiveViewer', () => {
  it('uses cells it can read as authored', () => {
    expect(reSnapped({ x: '0.3', y: '0.7', zoom: '2.5' })).toEqual(snappedTo(0.3, 0.7, 2.5));
  });

  it('frames the whole object for blank cells', () => {
    expect(reSnapped({ x: '', y: '', zoom: '' })).toEqual(snappedTo(0.5, 0.5, 1));
  });

  it('frames the whole object on the axis whose cell it cannot read', () => {
    expect(reSnapped({ x: 'left', y: '0.7', zoom: 'n/a' })).toEqual(snappedTo(0.5, 0.7, 1));
  });

  it('does nothing when no text card is active', () => {
    document.body.innerHTML = '';
    window.storyData = { steps: [{ object: 'fig1', x: '0.3', y: '0.3', zoom: '2' }] };
    reSnapActiveViewer();
    expect(fitBounds).not.toHaveBeenCalled();
  });
});
