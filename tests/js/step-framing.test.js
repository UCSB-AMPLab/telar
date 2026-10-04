/**
 * Tests for stepFraming — what an authored cell becomes before OSD sees it.
 *
 * This is the normalisation boundary between a spreadsheet and the viewer.
 * Cells arrive as whatever the sheet held: a number, a number someone quoted,
 * `n/a`, or a shape no author typed on purpose. Everything past this point does
 * arithmetic on x, y and zoom, so each has to leave here as a finite number or
 * the viewer is positioned by a string.
 *
 * A blank cell does not arrive blank: `_apply_coordinate_defaults` fills an
 * empty or `nan` cell with 0.5, 0.5, 1 while writing the story JSON, so the
 * blank case below is a guard on a path the build already closes rather than
 * the one a published site takes. The cell that does reach here unhandled is
 * the one that holds something — a label, a dash, `n/a` — which the build's
 * emptiness test does not match and nothing checks is a number.
 *
 * The three axes fall back independently: a step with a real zoom and a blank
 * x keeps the zoom and centres horizontally. Pinned per-axis for that reason.
 *
 * The Compositor's capture path pins FULL_OBJECT_FRAMING by name and cites it
 * in its editor, so the value is part of a cross-repo contract rather than an
 * implementation detail.
 *
 * @version v1.8.0
 */

import { describe, it, expect } from 'vitest';
import { stepFraming, FULL_OBJECT_FRAMING } from '../../assets/js/telar-story/plates/iiif-plate.js';

/** What an unreadable cell means: the whole object, centred, at zoom 1. */
const WHOLE_OBJECT = { x: 0.5, y: 0.5, zoom: 1 };

describe('FULL_OBJECT_FRAMING', () => {
  it('is the value the Compositor pins', () => {
    expect(FULL_OBJECT_FRAMING).toEqual(WHOLE_OBJECT);
  });
});

describe('stepFraming', () => {
  it('returns finite numbers whatever the cells held', () => {
    const shapes = [
      { x: '0.4', y: '0.6', zoom: '0.2' },
      { x: 0.4, y: 0.6, zoom: 2 },
      { x: 0.4, y: 0.6, zoom: '' },
      { x: 0.4, y: 0.6, zoom: 'n/a' },
      { x: 0.4, y: 0.6, zoom: {} },
      { x: 0.4, y: 0.6 },
      {},
    ];
    for (const step of shapes) {
      const { x, y, zoom } = stepFraming(step);
      expect(Number.isFinite(x), `x from ${JSON.stringify(step)}`).toBe(true);
      expect(Number.isFinite(y), `y from ${JSON.stringify(step)}`).toBe(true);
      expect(Number.isFinite(zoom), `zoom from ${JSON.stringify(step)}`).toBe(true);
    }
  });

  it('reads a quoted numeric as the number it spells', () => {
    // Google Sheets emits these readily, so it is the ordinary case rather
    // than the odd one.
    expect(stepFraming({ x: '0.4', y: '0.6', zoom: '0.2' }))
      .toMatchObject({ x: 0.4, y: 0.6, zoom: 0.2 });
  });

  it('passes a real number through unchanged', () => {
    expect(stepFraming({ x: 0.4, y: 0.6, zoom: 2 }))
      .toMatchObject({ x: 0.4, y: 0.6, zoom: 2 });
  });

  it('shows the whole object when a step authored no framing at all', () => {
    expect(stepFraming({})).toMatchObject(WHOLE_OBJECT);
    expect(stepFraming({ x: '', y: '', zoom: '' })).toMatchObject(WHOLE_OBJECT);
  });

  it('falls back per axis, so one blank cell does not discard the others', () => {
    expect(stepFraming({ x: '', y: 0.6, zoom: 2 }))
      .toMatchObject({ x: WHOLE_OBJECT.x, y: 0.6, zoom: 2 });
    expect(stepFraming({ x: 0.4, y: 0.6, zoom: '' }))
      .toMatchObject({ x: 0.4, y: 0.6, zoom: WHOLE_OBJECT.zoom });
  });

  it('falls back on a cell that spells no number', () => {
    for (const junk of ['n/a', 'none', {}, [], null, undefined, NaN]) {
      expect(stepFraming({ x: 0.4, y: 0.6, zoom: junk }).zoom).toBe(WHOLE_OBJECT.zoom);
    }
  });

  it('reads the leading number out of a cell that trails text', () => {
    // parseFloat's own rule, pinned because it is a choice: `0.2x` frames at
    // 0.2 rather than falling back to the whole object.
    expect(stepFraming({ x: 0.4, y: 0.6, zoom: '0.2x' }).zoom).toBe(0.2);
    // A one-element array stringifies to its element, so it reads as that
    // number rather than as junk. An empty one spells nothing and falls back.
    expect(stepFraming({ x: 0.4, y: 0.6, zoom: [0.2] }).zoom).toBe(0.2);
    expect(stepFraming({ x: 0.4, y: 0.6, zoom: [] }).zoom).toBe(WHOLE_OBJECT.zoom);
  });

  it('parses page as an integer, and leaves it absent when the step has none', () => {
    expect(stepFraming({ page: '3' }).page).toBe(3);
    expect(stepFraming({ page: 3 }).page).toBe(3);
    expect(stepFraming({}).page).toBeUndefined();
    expect(stepFraming({ page: '' }).page).toBeUndefined();
    // Page is 1-indexed in the story data, so 0 is not a page.
    expect(stepFraming({ page: 0 }).page).toBeUndefined();
  });
});
