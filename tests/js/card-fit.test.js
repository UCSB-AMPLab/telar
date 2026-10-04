/**
 * Tests for Telar Story – Side-card fit
 *
 * The ceiling formula against its exact values and its monotony, the card's
 * placement between the band under the controls and one padding above the
 * window's bottom, the size search, and the fit written on a card whose
 * geometry is modelled (card-fit-model.js): what it writes, what it leaves
 * alone, and when its cache answers.
 *
 * @version v1.8.0
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  sideCardCeiling, sideCardTop, searchFitSize, fitAnswerText, SIDE_CARD_CONTROLS,
} from '../../assets/js/telar-story/card-fit.js';
import {
  measureTopBand, measureControlsBottom,
} from '../../assets/js/telar-story/media-arrangement.js';
import { mediaPadding, computeBelowCardTop } from '../../assets/js/telar-story/video-layout.js';
import { modelCard } from './card-fit-model.js';

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

describe('searchFitSize', () => {
  it('keeps the base size where the answer fits', () => {
    expect(searchFitSize({ base: 16, floor: 12, fits: () => true })).toEqual({ mode: 'natural', size: 16 });
  });

  it('finds the largest size that fits, to 0.1px', () => {
    const r = searchFitSize({ base: 16, floor: 12, seed: 13.5, fits: (s) => s <= 13.37 });
    expect(r.mode).toBe('shrunk');
    expect(r.size).toBeLessThanOrEqual(13.37);
    expect(r.size).toBeGreaterThan(13.27);
  });

  it('scrolls at the floor where even the floor does not fit', () => {
    expect(searchFitSize({ base: 16, floor: 12, seed: 12.5, fits: (s) => s <= 11 }))
      .toEqual({ mode: 'scroll', size: 12 });
  });

  it('widens once where the fit is below the seed bracket', () => {
    const r = searchFitSize({ base: 16, floor: 12, seed: 15.9, fits: (s) => s <= 12.5 });
    expect(r.mode).toBe('shrunk');
    expect(r.size).toBeGreaterThan(12.4);
    expect(r.size).toBeLessThanOrEqual(12.5);
  });

  it('widens once where the fit is above the seed bracket', () => {
    const r = searchFitSize({ base: 16, floor: 12, seed: 12.1, fits: (s) => s <= 15 });
    expect(r.mode).toBe('shrunk');
    expect(r.size).toBeGreaterThan(14.9);
    expect(r.size).toBeLessThanOrEqual(15);
  });
});

describe('fitAnswerText on a modelled card', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.documentElement.style.fontSize = '16px';
  });
  afterEach(() => {
    document.documentElement.style.fontSize = '';
    vi.restoreAllMocks();
  });

  it('leaves an answer that fits at its size, marked natural', () => {
    const { card, size } = modelCard();
    const r = fitAnswerText(card, 500, new WeakMap());
    expect(r.mode).toBe('natural');
    expect(card.dataset.cardFit).toBe('natural');
    expect(size()).toBe(16);
  });

  it('shrinks the answer to the largest size that fits and writes it on the card', () => {
    // 100 + 20·s ≤ 380 holds up to s = 14.
    const { card, question } = modelCard();
    const r = fitAnswerText(card, 380, new WeakMap());
    expect(r.mode).toBe('shrunk');
    expect(card.dataset.cardFit).toBe('shrunk');
    const written = parseFloat(card.style.getPropertyValue('--telar-answer-fit-size'));
    expect(written).toBe(r.size);
    expect(written).toBeGreaterThan(13.9);
    expect(written).toBeLessThanOrEqual(14);
    expect(card.style.maxHeight).toBe('380px');
    expect(question.getAttribute('style')).toBeNull();
    expect(question.dataset.cardFit).toBeUndefined();
  });

  it('scrolls at 0.75rem where the answer does not fit at that size', () => {
    const { card } = modelCard();
    const r = fitAnswerText(card, 300, new WeakMap());
    expect(r).toMatchObject({ mode: 'scroll', size: 12 });
    expect(card.dataset.cardFit).toBe('scroll');
    expect(card.style.getPropertyValue('--telar-answer-fit-size')).toBe('12px');
  });

  it('writes nothing when the cache answers', () => {
    const cache = new WeakMap();
    const { card } = modelCard();
    fitAnswerText(card, 380, cache);
    const style = card.getAttribute('style');
    const set = vi.spyOn(card.style, 'setProperty');
    const remove = vi.spyOn(card.style, 'removeProperty');

    const r = fitAnswerText(card, 380, cache);

    expect(r.mode).toBe('shrunk');
    expect(set).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
    expect(card.getAttribute('style')).toBe(style);
  });

  it('measures again when the answer tier changes at the same width, from 13.6px', () => {
    // A card at most 360px wide takes 0.85rem, 13.6px: 100 + 20 × 13.6 = 372.
    const cache = new WeakMap();
    const { card, answer } = modelCard();
    expect(fitAnswerText(card, 380, cache).mode).toBe('shrunk');

    answer.style.setProperty('--telar-answer-base-size', '0.85rem');
    const r = fitAnswerText(card, 380, cache);

    expect(r).toMatchObject({ mode: 'natural', size: 13.6 });
    expect(card.style.getPropertyValue('--telar-answer-fit-size')).toBe('13.6px');
  });

  it('measures again when the root font size moves the floor at the same width', () => {
    const cache = new WeakMap();
    const { card } = modelCard({ base: '16px' });
    expect(fitAnswerText(card, 300, cache)).toMatchObject({ mode: 'scroll', size: 12 });

    document.documentElement.style.fontSize = '12px';   // the floor is now 9px
    const r = fitAnswerText(card, 300, cache);

    expect(r.mode).toBe('shrunk');
    expect(r.size).toBeGreaterThan(9.9);
    expect(r.size).toBeLessThanOrEqual(10);
  });
});
