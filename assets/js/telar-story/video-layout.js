/**
 * Telar Story -- Video Layout
 *
 * Where a video plate's player and its text card go, and what the players are
 * given to embed. When a video step activates, the side-by-side arrangement
 * (card left, video right) and the stacked one (video top, card below) are
 * both worked out, and whichever gives the video more rendered pixels wins; a
 * vertical layout is always stacked. The proportions are read once, when this
 * module loads, from the CSS custom properties in _sass/_responsive.scss.
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
const videoPadFactor    = parseFloat(_cs.getPropertyValue('--telar-video-pad-factor').trim())    || 0.025;
const videoStackMaxH    = parseFloat(_cs.getPropertyValue('--telar-video-stack-max-h').trim())   || 0.58;
const videoCardFracSide = parseFloat(_cs.getPropertyValue('--telar-video-card-frac-side').trim()) || 0.35;

// ── Pure functions (unit-tested) ──────────────────────────────────────────────

/**
 * Compute the optimal video + card layout for the given viewport dimensions
 * and video aspect ratio.
 *
 * Algorithm:
 *   Two candidates are computed:
 *   - Side-by-side: card left (35% of W), video right in remaining space.
 *   - Stacked: video top (max 58% of H), card below.
 *   The candidate that gives the video more rendered pixels wins.
 *   Mobile override: W < --telar-vertical-min-width always returns stacked.
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

  const pad = Math.max(8, Math.round(Math.min(W, H) * videoPadFactor));

  // ── Side-by-side candidate ──
  const cardFracSide = videoCardFracSide;
  const sideCardW = Math.round(W * cardFracSide);
  const sideVideoMaxW = W - sideCardW - pad * 3;
  const sideVideoMaxH = H - pad * 2;
  let sideVidW = sideVideoMaxW;
  let sideVidH = sideVidW / aspectRatio;
  if (sideVidH > sideVideoMaxH) {
    sideVidH = sideVideoMaxH;
    sideVidW = sideVidH * aspectRatio;
  }
  const sideVideoArea = sideVidW * sideVidH;

  // ── Stacked candidate ──
  const stackVideoMaxW = W - pad * 2;
  const stackVideoMaxH = H * videoStackMaxH;
  let stackVidW = stackVideoMaxW;
  let stackVidH = stackVidW / aspectRatio;
  if (stackVidH > stackVideoMaxH) {
    stackVidH = stackVideoMaxH;
    stackVidW = stackVidH * aspectRatio;
  }
  const stackVideoArea = stackVidW * stackVidH;

  if (sideVideoArea >= stackVideoArea) {
    return _buildSideBySideResult(W, H, pad, sideCardW, sideVidW, sideVidH);
  } else {
    return _buildStackedResult(W, H, pad, stackVidW, stackVidH);
  }
}

/** Build side-by-side layout result object. */
function _buildSideBySideResult(W, H, pad, sideCardW, sideVidW, sideVidH) {
  const vidW = Math.round(sideVidW);
  const vidH = Math.round(sideVidH);
  const vidLeft = sideCardW + pad * 2;
  const vidTop = Math.round((H - vidH) / 2);
  const cardW = sideCardW;
  const cardH = Math.round(H - pad * 2);
  const cardLeft = pad;
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
 * "cinematic frame" instead of a small mis-proportioned box. Mirrors
 * computeVideoLayout's mode choice but returns the un-fitted bounding region.
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
  const cardW = Math.round(W * videoCardFracSide);
  return {
    left: cardW + pad * 2,
    top: pad,
    width: Math.round(W - cardW - pad * 3),
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
