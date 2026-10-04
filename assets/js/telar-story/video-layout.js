/**
 * Telar Story -- Video Layout
 *
 * Where a video plate's player and its text card go, and what the players are
 * given to embed. On a horizontal layout the text card is the stylesheet's
 * side card, so the player goes beside it (side-by-side); on a vertical layout
 * the card is at the bottom, so the player goes above it (stacked). The
 * proportions, the side card's included, are read once, when this module
 * loads, from the CSS custom properties in _sass/_responsive.scss, which the
 * stylesheet builds the card from.
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
const cardSideLeft   = _readFraction('--telar-card-side-left', 0.03);
const cardSideWidth  = _readFraction('--telar-card-side-width', 0.37);

/**
 * A custom property as a fraction of the window: the side card's geometry is
 * declared in percent, because the stylesheet positions the card with it.
 */
function _readFraction(name, fallback) {
  const raw = _cs.getPropertyValue(name).trim();
  const value = parseFloat(raw);
  if (!Number.isFinite(value)) return fallback;
  return raw.endsWith('%') ? value / 100 : value;
}

/** The side text card's right edge, in px, as the stylesheet places it. */
function _sideCardRight(W) {
  return Math.round(W * (cardSideLeft + cardSideWidth));
}

// ── Pure functions (unit-tested) ──────────────────────────────────────────────

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
 *     --telar-card-side-left to --telar-card-side-left + --telar-card-side-width
 *     of W, so the video starts one padding past the card's right edge and
 *     fits the space that leaves. A stacked video would be drawn over the card.
 *
 * @param {number} W - Viewport width in px
 * @param {number} H - Viewport height in px
 * @param {number} aspectRatio - Video width / height (e.g. 16/9)
 * @returns {{ mode: 'side-by-side'|'stacked', video: {left,top,width,height}, card: {left,top,width,height}, padding: number }}
 */
export function computeVideoLayout(W, H, aspectRatio) {
  // Layout mode is determined by state.layoutMode (set by layout-mode.js at boot and on
  // every resize/orientationchange). On vertical layouts, always use stacked.
  if (state.layoutMode === 'vertical') {
    return _computeStackedLayout(W, H, aspectRatio);
  }
  return _computeSideBySideLayout(W, H, aspectRatio);
}

/** Compute the side-by-side layout: the video right of the side card. */
function _computeSideBySideLayout(W, H, aspectRatio) {
  const pad = Math.max(8, Math.round(Math.min(W, H) * videoPadFactor));
  const vidLeft = _sideCardRight(W) + pad;
  const sideVideoMaxW = W - vidLeft - pad;
  const sideVideoMaxH = H - pad * 2;
  let sideVidW = sideVideoMaxW;
  let sideVidH = sideVidW / aspectRatio;
  if (sideVidH > sideVideoMaxH) {
    sideVidH = sideVideoMaxH;
    sideVidW = sideVidH * aspectRatio;
  }
  return _buildSideBySideResult(W, H, pad, vidLeft, sideVidW, sideVidH);
}

/** Build side-by-side layout result object. */
function _buildSideBySideResult(W, H, pad, vidLeft, sideVidW, sideVidH) {
  const vidW = Math.round(sideVidW);
  const vidH = Math.round(sideVidH);
  const vidTop = Math.round((H - vidH) / 2);
  const cardW = Math.round(W * cardSideWidth);
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
 * @returns {{ left: number, top: number, width: number, height: number }}
 */
export function computeVideoLetterboxRegion(W, H) {
  const pad = Math.max(8, Math.round(Math.min(W, H) * videoPadFactor));
  if (state.layoutMode === 'vertical') {
    return {
      left: pad,
      top: pad,
      width: Math.round(W - pad * 2),
      height: Math.round(H * videoStackMaxH),
    };
  }
  const left = _sideCardRight(W) + pad;
  return {
    left,
    top: pad,
    width: W - left - pad,
    height: Math.round(H - pad * 2),
  };
}

/** Compute stacked layout for mobile. */
function _computeStackedLayout(W, H, aspectRatio) {
  const pad = Math.max(8, Math.round(Math.min(W, H) * videoPadFactor));
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
