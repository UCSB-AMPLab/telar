/**
 * Telar Story -- Media Arrangement
 *
 * Whether a video or audio scene's text cards sit beside its player or below
 * it, decided once per scene and written on the plate, where the player and
 * the cards both read it.
 *
 * The decision needs the cards' rendered heights, so card-pool.js calls
 * `arrangeMediaScene` after it has sized the cards, on every geometry pass.
 * The answer goes on the plate as `data-media-arrangement` ('below' or
 * 'beside'), with the tallest card's top (`data-media-card-top`) and the band
 * kept clear for the top controls (`data-media-top-band`) beside it;
 * video-card.js and audio-card.js place the player from those, and this
 * module places the cards. A scene is arranged by its tallest card, so the
 * player does not move between two steps of the same scene.
 *
 * Only a horizontal layout outside embed mode is arranged, and only where the
 * side card takes the height of its content: the fixed-height model keeps its
 * 80% card beside the player. Embed mode keeps the card beside because its
 * previous and next buttons sit over the bottom of the card's column. Every
 * media plate carries the top band, arranged or not, because the player
 * beside the card keeps it clear too.
 *
 * @version v1.8.0
 */

import { state } from './state.js';
import {
  chooseVideoArrangement, computeBelowCardTop, mediaPadding, COMPARISON_ASPECT,
} from './video-layout.js';
import { chooseAudioArrangement, computeAudioBelowLayout } from './audio-layout.js';

/** The fixed chrome at the top of a story, which the player below has to clear. */
const TOP_CONTROLS = ['.btn-nav-back', '.share-button', '.step-counter'];

/** The card types whose scenes this module arranges. */
const VIDEO_TYPES = new Set(['youtube', 'vimeo', 'google-drive']);

/** Whether the page is an embed; main.js sets the state after the first geometry pass. */
function _isEmbed() {
  return state.isEmbed || Boolean(window.telarEmbed?.enabled);
}

/**
 * The band kept clear for the top controls: their lowest bottom edge plus one
 * padding. A control that is not displayed has an empty box and is skipped.
 *
 * @param {number} W - Viewport width in px
 * @param {number} H - Viewport height in px
 * @returns {number}
 */
export function measureTopBand(W, H) {
  let bottom = 0;
  for (const selector of TOP_CONTROLS) {
    const el = document.querySelector(selector);
    if (!el) continue;
    const box = el.getBoundingClientRect();
    if (box.width > 0 && box.height > 0) bottom = Math.max(bottom, box.bottom);
  }
  return Math.round(bottom) + mediaPadding(W, H);
}

/** The aspect a video plate's player is compared at. */
function _plateAspect(plateEl) {
  if (plateEl.dataset.videoLetterbox === 'true') return COMPARISON_ASPECT;
  return parseFloat(plateEl.dataset.aspectRatio) || COMPARISON_ASPECT;
}

/** Forget an arrangement, on the plate and its cards. */
function _clear(plateEl, cards) {
  delete plateEl.dataset.mediaArrangement;
  delete plateEl.dataset.mediaCardTop;
  delete plateEl.dataset.mediaTopBand;
  for (const card of cards) delete card.dataset.mediaArrangement;
}

/**
 * Decide a media scene's arrangement, write it on the plate and place its cards.
 *
 * The cards must already be sized: their heights are read, not set. With the
 * card below, each card's bottom edge is one padding above the window's; with
 * the card beside, each card keeps the top the geometry pass gave it.
 *
 * @param {HTMLElement} plateEl - The scene's viewer plate
 * @param {HTMLElement[]} cards - The scene's text cards
 * @param {Object} how
 * @param {number} how.W - Viewport width in px
 * @param {number} how.H - Viewport height in px
 * @param {boolean} how.eligible - Whether the geometry pass sized these cards
 *   to their content on a horizontal layout
 * @param {(card: HTMLElement) => number} how.besideTop - A card's top beside the player
 * @returns {'below'|'beside'|null} null where the scene is not arranged
 */
export function arrangeMediaScene(plateEl, cards, { W, H, eligible, besideTop }) {
  const type = plateEl.dataset.cardType;
  const isMedia = VIDEO_TYPES.has(type) || type === 'audio';
  if (!isMedia) {
    _clear(plateEl, cards);
    return null;
  }
  const topBand = measureTopBand(W, H);
  if (!eligible || _isEmbed() || cards.length === 0) {
    _clear(plateEl, cards);
    plateEl.dataset.mediaTopBand = String(topBand);
    return null;
  }

  const cardH = Math.max(...cards.map((card) => card.offsetHeight));
  const arrangement = type === 'audio'
    ? chooseAudioArrangement(W, H, cardH, topBand)
    : chooseVideoArrangement(W, H, _plateAspect(plateEl), cardH, topBand);

  plateEl.dataset.mediaArrangement = arrangement;
  plateEl.dataset.mediaCardTop = String(computeBelowCardTop(W, H, cardH));
  plateEl.dataset.mediaTopBand = String(topBand);

  for (const card of cards) {
    card.dataset.mediaArrangement = arrangement;
    const top = arrangement === 'below'
      ? computeBelowCardTop(W, H, card.offsetHeight)
      : besideTop(card);
    card.style.setProperty('top', `${top}px`, 'important');
  }
  return arrangement;
}

/**
 * The card's top and the top band a plate's player is placed against, when
 * its scene has the card below; null otherwise.
 *
 * @param {HTMLElement} plateEl
 * @returns {{cardTop: number, topBand: number}|null}
 */
export function readBelow(plateEl) {
  if (plateEl.dataset.mediaArrangement !== 'below') return null;
  if (state.layoutMode === 'vertical') return null;
  const cardTop = parseFloat(plateEl.dataset.mediaCardTop);
  const topBand = parseFloat(plateEl.dataset.mediaTopBand);
  if (!Number.isFinite(cardTop) || !Number.isFinite(topBand)) return null;
  return { cardTop, topBand };
}

/**
 * The band a plate's player keeps clear for the top controls, in px from the
 * top; 0 on a vertical layout, or before a geometry pass has measured it.
 *
 * @param {HTMLElement} plateEl
 * @returns {number}
 */
export function readTopBand(plateEl) {
  if (state.layoutMode === 'vertical') return 0;
  const topBand = parseFloat(plateEl.dataset.mediaTopBand);
  return Number.isFinite(topBand) ? topBand : 0;
}

/** The custom properties an audio plate carries while its card is below. */
const AUDIO_BELOW_PROPS = ['--telar-audio-wave-top', '--telar-audio-wave-left',
  '--telar-audio-wave-width', '--telar-audio-controls-bottom'];

/**
 * Place an audio plate's waveform and controls with the card below, through
 * custom properties on the plate that the stylesheet's
 * `[data-media-arrangement="below"]` rules read, and return the waveform's
 * height in px. Where the card is not below, the properties are removed and
 * null is returned, leaving the height to audio-card.js.
 *
 * @param {HTMLElement} plateEl
 * @returns {number|null}
 */
export function placeAudioBelow(plateEl) {
  const below = readBelow(plateEl);
  if (!below) {
    for (const prop of AUDIO_BELOW_PROPS) plateEl.style.removeProperty(prop);
    return null;
  }
  const { wave, controlsBottom } = computeAudioBelowLayout(window.innerWidth, window.innerHeight, below);
  [wave.top, wave.left, wave.width, controlsBottom]
    .forEach((px, i) => plateEl.style.setProperty(AUDIO_BELOW_PROPS[i], `${px}px`));
  return wave.height;
}
