/**
 * Telar Story -- Video Layout
 *
 * Where a video plate's player and its text card go, and what the players are
 * given to embed. On a horizontal layout the text card is the stylesheet's
 * side card, so the player goes beside it (side-by-side), unless the card is
 * placed below the player (below): the card keeps the side card's left edge
 * and width and sits one padding above the window's bottom edge, and the
 * player fills the width above it. Either way the player stays under the band
 * the top controls occupy.
 * `chooseVideoArrangement` decides between the two; media-arrangement.js
 * calls it with the card's measured height and writes the answer on the
 * plate, where the player and the card both read it. On a vertical layout the
 * card is at the bottom, so the player goes above it (stacked). The
 * proportions are read once, when this module loads, from the CSS custom
 * properties in _sass/_responsive.scss, which the stylesheet builds the card
 * from. The side card's width is read at each call, because card-fit.js
 * publishes it per window on the root element (`--telar-card-side-width`).
 *
 * The embed builders and the clip-time format are here because, like the
 * layout, they are arithmetic on their arguments with nothing to tear down.
 * video-card.js, which owns the players, re-exports all of it, so its
 * importers are unchanged.
 *
 * @version v1.8.0
 */

import { state } from './state.js';

// ── CSS custom property reads (SSOT — sourced from _sass/_responsive.scss :root) ──
const _cs = getComputedStyle(document.documentElement);
const videoPadFactor = parseFloat(_cs.getPropertyValue('--telar-video-pad-factor').trim())  || 0.025;
const videoStackMaxH = parseFloat(_cs.getPropertyValue('--telar-video-stack-max-h').trim()) || 0.58;
const cardSideLeft   = readFraction('--telar-card-side-left', 0.03);
const mediaBelowGain = _readNumber('--telar-media-below-gain', 0.15);

/**
 * The aspect a video is compared at while its own is unknown: an embed whose
 * aspect cannot be read, or one whose detection has not come back yet.
 */
export const COMPARISON_ASPECT = 16 / 9;

/** A unitless custom property, or the fallback where it is unset. */
function _readNumber(name, fallback) {
  const value = parseFloat(_cs.getPropertyValue(name).trim());
  return Number.isFinite(value) ? value : fallback;
}

/**
 * A custom property as a fraction of the window: the side card's geometry is
 * declared in percent, because the stylesheet positions the card with it.
 * audio-layout.js reads the waveform's side geometry through it too.
 */
export function readFraction(name, fallback) {
  const raw = _cs.getPropertyValue(name).trim();
  const value = parseFloat(raw);
  if (!Number.isFinite(value)) return fallback;
  return raw.endsWith('%') ? value / 100 : value;
}

/**
 * The side text card's width, in px: the width card-fit.js publishes for the
 * window on the root element's own style, or the stylesheet's share of W
 * where none is published.
 *
 * @param {number} W - Viewport width in px
 * @returns {number}
 */
export function sideCardWidthPx(W) {
  const published = parseFloat(document.documentElement.style.getPropertyValue('--telar-card-side-width'));
  if (Number.isFinite(published)) return published;
  return W * readFraction('--telar-card-side-width', 0.37);
}

/**
 * The side text card's right edge, in px, as the stylesheet places it.
 *
 * @param {number} W - Viewport width in px
 * @returns {number}
 */
export function sideCardRight(W) {
  return Math.round(W * cardSideLeft + sideCardWidthPx(W));
}

// ── Pure functions (unit-tested) ──────────────────────────────────────────────

/**
 * The padding a media plate keeps between the player, the card and the
 * window's edges.
 *
 * @param {number} W - Viewport width in px
 * @param {number} H - Viewport height in px
 * @returns {number}
 */
export function mediaPadding(W, H) {
  return Math.max(8, Math.round(Math.min(W, H) * videoPadFactor));
}

/**
 * The same padding before rounding, for a bound that must not move by the
 * rounding's half pixel as the window grows.
 *
 * @param {number} W - Viewport width in px
 * @param {number} H - Viewport height in px
 * @returns {number}
 */
export function unroundedMediaPadding(W, H) {
  return Math.max(8, Math.min(W, H) * videoPadFactor);
}

/**
 * Where a card placed below the player has its top: one padding above the
 * window's bottom edge.
 *
 * @param {number} W - Viewport width in px
 * @param {number} H - Viewport height in px
 * @param {number} cardH - The card's rendered height in px
 * @returns {number}
 */
export function computeBelowCardTop(W, H, cardH) {
  return Math.round(H - mediaPadding(W, H) - cardH);
}

/**
 * Whether the player's area below is enough larger than beside to move the
 * card. The margin (--telar-media-below-gain) keeps a window whose two
 * arrangements are close from switching between them.
 *
 * @param {number} besideArea - The player's area with the card beside, px²
 * @param {number} belowArea - The player's area with the card below, px²
 * @returns {boolean}
 */
export function prefersBelow(besideArea, belowArea) {
  return belowArea >= besideArea * (1 + mediaBelowGain);
}

/**
 * Whether a video step's card goes beside the player or below it, on a
 * horizontal layout.
 *
 * @param {number} W - Viewport width in px
 * @param {number} H - Viewport height in px
 * @param {number} aspectRatio - Video width / height; COMPARISON_ASPECT when unknown
 * @param {number} cardH - The card's rendered height in px, at the side card's width
 * @param {number} topBand - The band kept clear for the top controls, in px from the top
 * @returns {'below'|'beside'}
 */
export function chooseVideoArrangement(W, H, aspectRatio, cardH, topBand) {
  const beside = _computeSideBySideLayout(W, H, aspectRatio, topBand).video;
  const below = _computeBelowLayout(W, H, aspectRatio, {
    cardTop: computeBelowCardTop(W, H, cardH), topBand,
  }).video;
  return prefersBelow(beside.width * beside.height, below.width * below.height)
    ? 'below' : 'beside';
}

/**
 * Compute the video + card layout for the given viewport dimensions and video
 * aspect ratio.
 *
 * The arrangement follows the text card, which card-pool.js and the
 * stylesheet place by layout mode:
 *   - Vertical layout (state.layoutMode === 'vertical', which layout-mode.js
 *     sets for a window no wider than --telar-vertical-min-width or no wider
 *     than --telar-vertical-min-aspect of its height): the card is at the
 *     bottom, so the video is stacked above it (max 58% of H).
 *   - Horizontal layout: the card is the side card, from
 *     --telar-card-side-left of W to that plus --telar-card-side-width, so the video starts one padding past the card's right edge and
 *     fits the space that leaves, from the top band (`topBand`) to one padding
 *     above the window's bottom edge. It is centred on the window's height
 *     unless that would put its top above the band. A stacked video would be
 *     drawn over the card.
 *   - Horizontal layout with the card below (`below` given): the video fits
 *     the width less a padding each side, and the height from the top band to
 *     one padding above the card's top, centred in that space.
 *
 * @param {number} W - Viewport width in px
 * @param {number} H - Viewport height in px
 * @param {number} aspectRatio - Video width / height (e.g. 16/9)
 * @param {{cardTop: number, topBand: number}|null} [below] - The card's top and
 *   the top band, when the card is below the player
 * @param {number} [topBand=0] - The band kept clear for the top controls, in px
 *   from the top, when the card is beside the player; one padding at least
 * @returns {{ mode: 'side-by-side'|'below'|'stacked', video: {left,top,width,height}, card: {left,top,width,height}, padding: number }}
 */
export function computeVideoLayout(W, H, aspectRatio, below = null, topBand = 0) {
  // Layout mode is determined by state.layoutMode (set by layout-mode.js at boot and on
  // every resize/orientationchange). On vertical layouts, always use stacked.
  if (state.layoutMode === 'vertical') {
    return _computeStackedLayout(W, H, aspectRatio);
  }
  if (below) return _computeBelowLayout(W, H, aspectRatio, below);
  return _computeSideBySideLayout(W, H, aspectRatio, topBand);
}

/** The space above a card placed below the player: the whole width, under the top band. */
function _belowRegion(W, pad, below) {
  return {
    left: pad,
    top: below.topBand,
    width: W - pad * 2,
    height: Math.max(0, below.cardTop - pad - below.topBand),
  };
}

/** Compute the layout with the card below: the video centred in the space above it. */
function _computeBelowLayout(W, H, aspectRatio, below) {
  const pad = mediaPadding(W, H);
  const region = _belowRegion(W, pad, below);
  let vidW = region.width;
  let vidH = vidW / aspectRatio;
  if (vidH > region.height) {
    vidH = region.height;
    vidW = vidH * aspectRatio;
  }
  vidW = Math.round(vidW);
  vidH = Math.round(vidH);
  const cardW = Math.round(sideCardWidthPx(W));
  return {
    mode: 'below',
    video: {
      left: Math.round(region.left + (region.width - vidW) / 2),
      top: Math.round(region.top + (region.height - vidH) / 2),
      width: vidW,
      height: vidH,
    },
    card: {
      left: Math.round(W * cardSideLeft),
      top: below.cardTop,
      width: cardW,
      height: Math.max(0, H - pad - below.cardTop),
    },
    padding: cardW > 300 ? 24 : cardW > 200 ? 16 : 10,
  };
}

/**
 * The space beside the side card: from one padding past its right edge to one
 * padding inside the window's, and from the top band to one padding above the
 * window's bottom edge.
 */
function _besideRegion(W, H, pad, topBand) {
  const left = sideCardRight(W) + pad;
  const top = Math.max(pad, Math.round(topBand) || 0);
  return {
    left,
    top,
    width: W - left - pad,
    height: Math.max(0, Math.round(H - pad - top)),
  };
}

/** Compute the side-by-side layout: the video right of the side card. */
function _computeSideBySideLayout(W, H, aspectRatio, topBand) {
  const pad = mediaPadding(W, H);
  const region = _besideRegion(W, H, pad, topBand);
  let sideVidW = region.width;
  let sideVidH = sideVidW / aspectRatio;
  if (sideVidH > region.height) {
    sideVidH = region.height;
    sideVidW = sideVidH * aspectRatio;
  }
  return _buildSideBySideResult(W, H, pad, region, sideVidW, sideVidH);
}

/** Build side-by-side layout result object. */
function _buildSideBySideResult(W, H, pad, region, sideVidW, sideVidH) {
  const vidW = Math.round(sideVidW);
  const vidH = Math.round(sideVidH);
  const vidLeft = region.left;
  const vidTop = Math.max(region.top, Math.round((H - vidH) / 2));
  const cardW = Math.round(sideCardWidthPx(W));
  const cardH = Math.round(H - pad * 2);
  const cardLeft = Math.round(W * cardSideLeft);
  const cardTop = pad;
  const cardPad = cardW > 300 ? 24 : cardW > 200 ? 16 : 10;

  return {
    mode: 'side-by-side',
    video: { left: vidLeft, top: vidTop, width: vidW, height: vidH },
    card: { left: cardLeft, top: cardTop, width: cardW, height: cardH },
    padding: cardPad,
  };
}

/** Build stacked layout result object. */
function _buildStackedResult(W, H, pad, stackVidW, stackVidH) {
  const vidW = Math.round(stackVidW);
  const vidH = Math.round(stackVidH);
  const vidLeft = Math.round((W - vidW) / 2);
  const vidTop = pad;
  const cardTop = vidTop + vidH + pad;
  const cardH = Math.max(60, H - cardTop - pad);
  const cardW = Math.round(W - pad * 2);
  const cardLeft = pad;
  const cardPad = cardH > 200 ? 22 : cardH > 120 ? 14 : 8;

  return {
    mode: 'stacked',
    video: { left: vidLeft, top: vidTop, width: vidW, height: vidH },
    card: { left: cardLeft, top: cardTop, width: cardW, height: cardH },
    padding: cardPad,
  };
}

/**
 * Compute the iframe region for a video whose true aspect ratio is unknown
 * (old YouTube videos with no maxres thumbnail; all Google Drive embeds, which
 * expose no dimensions API). Rather than guess an aspect and letterbox inside a
 * mis-shaped box, we fill the whole available region and let the provider's own
 * player letterbox the video centred on its black background — a cohesive dark
 * "cinematic frame" instead of a small mis-proportioned box. Follows
 * computeVideoLayout's arrangement but returns the un-fitted bounding region.
 *
 * @param {number} W - Viewport width in px
 * @param {number} H - Viewport height in px
 * @param {{cardTop: number, topBand: number}|null} [below] - As computeVideoLayout
 * @param {number} [topBand=0] - As computeVideoLayout
 * @returns {{ left: number, top: number, width: number, height: number }}
 */
export function computeVideoLetterboxRegion(W, H, below = null, topBand = 0) {
  const pad = mediaPadding(W, H);
  if (state.layoutMode === 'vertical') {
    return {
      left: pad,
      top: pad,
      width: Math.round(W - pad * 2),
      height: Math.round(H * videoStackMaxH),
    };
  }
  if (below) return _belowRegion(W, pad, below);
  return _besideRegion(W, H, pad, topBand);
}

/** Compute stacked layout for mobile. */
function _computeStackedLayout(W, H, aspectRatio) {
  const pad = mediaPadding(W, H);
  const stackVideoMaxW = W - pad * 2;
  const stackVideoMaxH = H * videoStackMaxH;
  let stackVidW = stackVideoMaxW;
  let stackVidH = stackVidW / aspectRatio;
  if (stackVidH > stackVideoMaxH) {
    stackVidH = stackVideoMaxH;
    stackVidW = stackVidH * aspectRatio;
  }
  return _buildStackedResult(W, H, pad, stackVidW, stackVidH);
}

/**
 * Build the YouTube playerVars config object.
 *
 * @param {string} videoId - YouTube video ID
 * @param {number} clipStart - Start time in seconds (0 = no restriction)
 * @param {number} clipEnd - End time in seconds (0 = no restriction, unused in playerVars)
 * @param {boolean} loop - Whether the clip should loop
 * @returns {{ videoId: string, playerVars: Object }}
 */
export function buildYouTubeEmbedConfig(videoId, clipStart, clipEnd, loop) {
  return {
    videoId,
    playerVars: {
      start: clipStart || 0,
      autoplay: 0,
      mute: 0,
      // loop/playlist omitted — segment looping handled by rAF polling
      // (YouTube loop playerVar loops the whole video, not the clip)
      controls: 1,
      rel: 0,
      modestbranding: 1,
    },
  };
}

/**
 * Build the Google Drive embed preview URL for a file ID.
 *
 * @param {string} fileId - Google Drive file ID
 * @returns {string} Preview URL
 */
export function buildGDriveEmbedUrl(fileId) {
  return `https://drive.google.com/file/d/${fileId}/preview`;
}

/**
 * Format a time in seconds as 'M:SS' for the progress ring display.
 *
 * @param {number} seconds - Time in seconds (may be fractional, will be floored)
 * @returns {string} Formatted time, e.g. '0:42', '1:07'
 */
export function formatClipTime(seconds) {
  const total = Math.floor(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}
