/**
 * Tests for Telar Story – Side-card fit
 *
 * The width formula against its exact values and its bounds, the width's
 * publication on the root element, the ceiling formula against its exact
 * values and its monotony, the card's
 * placement between the band under the controls and one padding above the
 * window's bottom, and the pass that caps and places a card: it writes a
 * max-height and a top and leaves the answer's text size alone.
 *
 * @version v1.8.0
 */

import { describe, it, expect, afterEach } from 'vitest';
import {
  sideCardCeiling, sideCardTop, fitSideCards, SIDE_CARD_CONTROLS,
  sideCardWidth, publishSideCardWidth, SIDE_CARD_WIDTH,
} from '../../assets/js/telar-story/card-fit.js';
import { readFileSync } from 'fs';
import { resolve } from 'path';
import {
  measureTopBand, measureControlsBottom,
} from '../../assets/js/telar-story/media-arrangement.js';
import { mediaPadding, computeBelowCardTop } from '../../assets/js/telar-story/video-layout.js';

const T = 480;
const FRACTION = 0.8;

/** Put the top controls on the page with these bottom edges, px. */
function controls({ back, share, counter, banner }) {
  document.body.innerHTML = '';
  const placeControl = (cls, bottom) => {
    if (bottom == null) return;
    const el = document.createElement('div');
    el.className = cls;
    el.getBoundingClientRect = () => ({ top: bottom - 34, bottom, left: 20, right: 140, width: 120, height: 34 });
    document.body.append(el);
  };
  placeControl('btn-nav-back', back);
  placeControl('share-button', share);
  placeControl('step-counter', counter);
  placeControl('telar-embed-banner', banner);
  return Math.round(measureControlsBottom(SIDE_CARD_CONTROLS));
}

const CONTROL_SETS = {
  'controls at 40': { back: 40, share: 40, counter: 40 },
  'controls at 54': { back: 54, share: 52, counter: 50 },
  'controls at 54, banner at 110': { back: 54, share: 52, counter: 50, banner: 110 },
};

describe('sideCardWidth', () => {
  it('equals the exact values of the ruling', () => {
    const exact = [
      // 37% of the width where the height's line is lower
      [1920, 1080, 710], [1440, 900, 533], [1280, 720, 474],
      // 1544 − 1.6·H between the shares
      [1280, 600, 584], [1440, 560, 648], [1920, 600, 710], [1600, 640, 592],
      // the line held to 718px in the shortest windows
      [1440, 481, 718], [1920, 500, 718],
      // 52% of the width at most
      [1366, 481, 710], [1025, 601, 533],
    ];
    for (const [W, H, value] of exact) {
      expect(sideCardWidth(W, H), `${W}x${H}`).toBe(value);
    }
  });

  it('stays between 37% and 52% of the width and never grows with the height', () => {
    for (let W = 1025; W <= 1920; W += 15) {
      let previous = Infinity;
      for (let H = 481; H <= 1200; H += 7) {
        const w = sideCardWidth(W, H);
        expect(w).toBeGreaterThanOrEqual(Math.round(0.37 * W));
        expect(w).toBeLessThanOrEqual(Math.round(0.52 * W));
        expect(w, `${W}x${H}`).toBeLessThanOrEqual(previous);
        previous = w;
      }
    }
  });
});

describe('the width terms', () => {
  it('fall back to the stylesheet\'s values, which the :root mirror carries', () => {
    const sheet = readFileSync(resolve(process.cwd(), '_sass/_responsive.scss'), 'utf8');
    const sass = (name) => parseFloat(sheet.match(new RegExp(`\\$telar-card-side-${name}:\\s*([0-9.]+)`))[1]);
    expect(SIDE_CARD_WIDTH).toEqual({
      minShare: sass('min-share'), maxShare: sass('max-share'), base: sass('base'),
      slope: sass('slope'), maxByHeight: sass('max-by-height'),
    });
    for (const name of ['min-share', 'max-share', 'base', 'slope', 'max-by-height']) {
      expect(sheet).toMatch(new RegExp(`--telar-card-side-${name}:\\s+#\\{\\$telar-card-side-${name}\\};`));
    }
  });
});

describe('publishSideCardWidth', () => {
  const readPublished = () => document.documentElement.style.getPropertyValue('--telar-card-side-width');
  afterEach(() => { document.documentElement.style.removeProperty('--telar-card-side-width'); });

  it('writes the width on a horizontal layout and clears it on a vertical one', () => {
    publishSideCardWidth(1280, 600, true);
    expect(readPublished()).toBe('584px');
    publishSideCardWidth(1440, 900, true);
    expect(readPublished()).toBe('533px');
    publishSideCardWidth(900, 400, false);
    expect(readPublished()).toBe('');
  });
});

describe('sideCardCeiling', () => {
  afterEach(() => { document.body.innerHTML = ''; });

  it('equals the exact values at W = 1280, C = 54', () => {
    const C = controls(CONTROL_SETS['controls at 54']);
    expect(C).toBe(54);
    const exact = { 400: 325, 450: 372, 480: 401, 481: 401, 500: 401, 502: 401, 505: 404, 560: 448, 720: 576 };
    for (const [H, value] of Object.entries(exact)) {
      expect(sideCardCeiling({ H: Number(H), W: 1280, C, T, fraction: FRACTION }), `H = ${H}`).toBe(value);
    }
  });

  it('keeps 1 to 2px below the room under the band', () => {
    const C = controls(CONTROL_SETS['controls at 54']);
    for (const [H, room] of [[400, 326], [450, 374], [480, 402]]) {
      const pad = mediaPadding(1280, H);
      expect(H - (C + pad) - pad, `room at ${H}`).toBe(room);
      const ceiling = sideCardCeiling({ H, W: 1280, C, T, fraction: FRACTION });
      expect(room - ceiling).toBeGreaterThanOrEqual(1);
      expect(room - ceiling).toBeLessThanOrEqual(2);
    }
  });

  for (const [name, set] of Object.entries(CONTROL_SETS)) {
    for (const W of [900, 1280, 1920]) {
      it(`never decreases as H grows, ${name}, W = ${W}`, () => {
        const C = controls(set);
        let previous = -Infinity;
        for (let H = 300; H <= 1200; H++) {
          const ceiling = sideCardCeiling({ H, W, C, T, fraction: FRACTION });
          expect(ceiling, `H = ${H}`).toBeGreaterThanOrEqual(previous);
          previous = ceiling;
        }
      });

      it(`places the card between the band and one padding above the bottom, ${name}, W = ${W}`, () => {
        const C = controls(set);
        for (let H = 300; H <= 1200; H++) {
          const ceiling = sideCardCeiling({ H, W, C, T, fraction: FRACTION });
          const pad = mediaPadding(W, H);
          const band = C + pad;
          const playerBand = measureTopBand(W, H);
          for (const cardH of [ceiling, ceiling - 50]) {
            for (const peek of [0, 1, 20]) {
              for (const runPos of [0, 3]) {
                const top = sideCardTop({ H, cardH, runPos, peek, band, pad });
                const at = `H ${H}, cardH ${cardH}, peek ${peek}, run ${runPos}`;
                expect(top, at).toBeGreaterThanOrEqual(band);
                expect(top, at).toBeGreaterThanOrEqual(playerBand);
                expect(top + cardH, at).toBeLessThanOrEqual(H - pad);
              }
            }
          }
          expect(computeBelowCardTop(W, H, ceiling), `below, H ${H}`).toBeGreaterThanOrEqual(band);
        }
      });
    }
  }
});

describe('fitSideCards', () => {
  afterEach(() => { document.body.innerHTML = ''; });

  it('caps the card at the ceiling and places it, leaving its text size alone', () => {
    const C = controls(CONTROL_SETS['controls at 54']);
    const card = document.createElement('div');
    card.className = 'text-card';
    card.dataset.stepIndex = '0';
    card.style.height = '500px';
    document.body.append(card);

    const { ceiling } = fitSideCards([card], {
      W: 1280, H: 800, peek: 1, fraction: FRACTION, activeIndex: 0,
    });

    expect(ceiling).toBe(sideCardCeiling({ H: 800, W: 1280, C, T, fraction: FRACTION }));
    expect(card.style.maxHeight).toBe(`${ceiling}px`);
    expect(card.style.height).toBe('');
    expect(card.style.getPropertyValue('top')).not.toBe('');
    expect(card.dataset.cardFit).toBeUndefined();
    expect(card.style.getPropertyValue('--telar-answer-fit-size')).toBe('');
  });
});
