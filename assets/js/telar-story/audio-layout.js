/**
 * Telar Story -- Audio Layout
 *
 * Where an audio plate's waveform and controls go on a horizontal layout.
 * Beside the card, the waveform is the stylesheet's: from
 * --telar-audio-wave-side-gap of the window past the side card's right edge
 * to the window's right edge, --telar-audio-height-resize of its height tall,
 * centred. With the card
 * below, the waveform spans the width less a padding each side, above the
 * controls row, which sits above the card; it keeps the same height unless
 * the space above the card is shorter. `chooseAudioArrangement` decides
 * between the two by the same rule as a video: below when the waveform's area
 * there is at least --telar-media-below-gain larger. Because the waveform
 * below is about 1.6 times as wide, that keeps the card below while the
 * waveform keeps about 70% of its height beside the card.
 *
 * Arithmetic on its arguments only; audio-card.js applies it, and
 * media-arrangement.js calls the choice with the card's measured height.
 *
 * @version v1.8.0
 */

import {
  mediaPadding, prefersBelow, computeBelowCardTop, readFraction, sideCardRight,
} from './video-layout.js';

const _cs = getComputedStyle(document.documentElement);
const audioHeightResize = parseFloat(_cs.getPropertyValue('--telar-audio-height-resize').trim()) || 0.5;
const waveSideGap = readFraction('--telar-audio-wave-side-gap', 0.01);

/**
 * The controls row under the waveform: its buttons' height (.audio-btn) and
 * the gap the stylesheet leaves between the waveform's bottom edge and the
 * row beside the card, `bottom: calc(25% - 48px)` under a waveform ending at
 * 75% of the window.
 */
export const AUDIO_CONTROLS_HEIGHT = 44;
export const AUDIO_CONTROLS_GAP = 4;

/**
 * The waveform beside the card, as the stylesheet draws it.
 *
 * @param {number} W - Viewport width in px
 * @param {number} H - Viewport height in px
 * @returns {{ width: number, height: number }}
 */
export function computeAudioBesideWave(W, H) {
  return {
    width: Math.round(W - sideCardRight(W) - W * waveSideGap),
    height: Math.round(H * audioHeightResize),
  };
}

/**
 * The waveform and the controls row with the card below.
 *
 * The waveform and the row under it are centred between the top band and one
 * padding above the card's top. The waveform is as tall as beside the card
 * while that space allows, and shrinks to what it leaves otherwise.
 *
 * @param {number} W - Viewport width in px
 * @param {number} H - Viewport height in px
 * @param {{cardTop: number, topBand: number}} below - The card's top and the top band
 * @returns {{ wave: {left,top,width,height}, controlsBottom: number }}
 *   controlsBottom is the distance from the window's bottom edge to the
 *   controls row's bottom edge, which is how the stylesheet anchors the row.
 */
export function computeAudioBelowLayout(W, H, below) {
  const pad = mediaPadding(W, H);
  const row = AUDIO_CONTROLS_GAP + AUDIO_CONTROLS_HEIGHT;
  const space = Math.max(0, below.cardTop - pad - below.topBand);
  const height = Math.max(0, Math.min(Math.round(H * audioHeightResize), space - row));
  const top = Math.round(below.topBand + (space - height - row) / 2);
  return {
    wave: { left: pad, top, width: W - pad * 2, height },
    controlsBottom: Math.round(H - (top + height + row)),
  };
}

/**
 * Whether an audio step's card goes beside the waveform or below it, on a
 * horizontal layout.
 *
 * @param {number} W - Viewport width in px
 * @param {number} H - Viewport height in px
 * @param {number} cardH - The card's rendered height in px, at the side card's width
 * @param {number} topBand - The band kept clear for the top controls, in px from the top
 * @returns {'below'|'beside'}
 */
export function chooseAudioArrangement(W, H, cardH, topBand) {
  const beside = computeAudioBesideWave(W, H);
  const below = computeAudioBelowLayout(W, H, {
    cardTop: computeBelowCardTop(W, H, cardH), topBand,
  }).wave;
  return prefersBelow(beside.width * beside.height, below.width * below.height)
    ? 'below' : 'beside';
}
