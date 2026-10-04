/**
 * Tests for Telar Story – Video Card Pure Functions
 *
 * Verifies pure (no DOM, no player API) functions exported by video-card.js.
 * - computeVideoLayout: auto-layout algorithm
 * - buildYouTubeEmbedConfig: YouTube playerVars builder
 * - buildGDriveEmbedUrl: Google Drive preview URL builder
 * - formatClipTime: M:SS time formatter for ring display
 *
 * @version v1.8.0
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import {
  computeVideoLayout,
  computeVideoLetterboxRegion,
  buildYouTubeEmbedConfig,
  buildGDriveEmbedUrl,
  formatClipTime,
} from '../../assets/js/telar-story/video-card.js';
import { state } from '../../assets/js/telar-story/state.js';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// ── computeVideoLetterboxRegion ───────────────────────────────────────────────

describe('computeVideoLetterboxRegion (unknown-aspect dark frame)', () => {
  afterEach(() => { delete state.layoutMode; });

  it('returns the side region beside the card on a wide (landscape) layout', () => {
    delete state.layoutMode; // non-vertical → side-by-side region
    const r = computeVideoLetterboxRegion(1920, 1080);
    // pad=27; the text card spans 3% to 40% of the window, so ends at 768
    expect(r).toEqual({ left: 795, top: 27, width: 1098, height: 1026 });
  });

  it('does not overlap the card column (left clears the card\'s right edge)', () => {
    delete state.layoutMode;
    const W = 1920;
    const r = computeVideoLetterboxRegion(W, 1080);
    const cardRight = Math.round(W * 0.40);
    expect(r.left).toBeGreaterThan(cardRight); // starts past the card
    expect(r.left + r.width).toBeLessThanOrEqual(W); // stays in viewport
  });

  it('returns a full-width top region on a vertical layout', () => {
    state.layoutMode = 'vertical';
    const r = computeVideoLetterboxRegion(1080, 1920);
    // pad=27, full width minus padding, height = round(1920*0.58)
    expect(r.left).toBe(27);
    expect(r.top).toBe(27);
    expect(r.width).toBe(1026);
    expect(r.height).toBe(1114);
  });

  it('always returns the four region keys', () => {
    const r = computeVideoLetterboxRegion(1280, 720);
    expect(r).toHaveProperty('left');
    expect(r).toHaveProperty('top');
    expect(r).toHaveProperty('width');
    expect(r).toHaveProperty('height');
  });
});

// ── computeVideoLayout ────────────────────────────────────────────────────────

describe('computeVideoLayout', () => {
  afterEach(() => { delete state.layoutMode; });

  it('returns side-by-side for a wide window with 16:9 video', () => {
    const layout = computeVideoLayout(1920, 1080, 16 / 9);
    expect(layout.mode).toBe('side-by-side');
  });

  it('returns stacked for a narrow window (600x800) with 16:9 video', () => {
    state.layoutMode = 'vertical';
    const layout = computeVideoLayout(600, 800, 16 / 9);
    expect(layout.mode).toBe('stacked');
  });

  it('returns stacked on a vertical layout regardless of area', () => {
    state.layoutMode = 'vertical';
    const layout = computeVideoLayout(500, 800, 16 / 9);
    expect(layout.mode).toBe('stacked');
  });

  it('returns stacked on a vertical layout at W=767', () => {
    state.layoutMode = 'vertical';
    const layout = computeVideoLayout(767, 1024, 16 / 9);
    expect(layout.mode).toBe('stacked');
  });

  it('returns side-by-side layout with expected structure', () => {
    const layout = computeVideoLayout(1920, 1080, 16 / 9);
    expect(layout).toHaveProperty('mode');
    expect(layout).toHaveProperty('video');
    expect(layout).toHaveProperty('card');
    expect(layout).toHaveProperty('padding');
    expect(layout.video).toHaveProperty('left');
    expect(layout.video).toHaveProperty('top');
    expect(layout.video).toHaveProperty('width');
    expect(layout.video).toHaveProperty('height');
    expect(layout.card).toHaveProperty('left');
    expect(layout.card).toHaveProperty('top');
    expect(layout.card).toHaveProperty('width');
    expect(layout.card).toHaveProperty('height');
  });

  it('video area is positive in all layout modes', () => {
    const wide = computeVideoLayout(1920, 1080, 16 / 9);
    state.layoutMode = 'vertical';
    const narrow = computeVideoLayout(600, 800, 16 / 9);
    expect(wide.video.width * wide.video.height).toBeGreaterThan(0);
    expect(narrow.video.width * narrow.video.height).toBeGreaterThan(0);
  });

  it('card area is positive in all layout modes', () => {
    const wide = computeVideoLayout(1920, 1080, 16 / 9);
    state.layoutMode = 'vertical';
    const narrow = computeVideoLayout(600, 800, 16 / 9);
    expect(wide.card.width * wide.card.height).toBeGreaterThan(0);
    expect(narrow.card.width * narrow.card.height).toBeGreaterThan(0);
  });

  it('padding is at least 8px', () => {
    // Even at very small viewports, padding should be >= 8
    const layout = computeVideoLayout(100, 100, 16 / 9);
    expect(layout.padding).toBeGreaterThanOrEqual(8);
  });

  it('handles 4:3 aspect ratio', () => {
    const layout = computeVideoLayout(1024, 768, 4 / 3);
    expect(['side-by-side', 'stacked']).toContain(layout.mode);
  });
});

// ── The player beside the side text card ─────────────────────────────────────

describe('the player beside the side text card', () => {
  // The text card is the stylesheet's side card, 3% from the left and 37% wide,
  // so its right edge is 40% of the window.
  const cardRight = (W) => Math.round(W * 0.40);
  const pad = (W, H) => Math.max(8, Math.round(Math.min(W, H) * 0.025));

  afterEach(() => { delete state.layoutMode; });

  it('starts one padding past the card at 1440x757', () => {
    const { video } = computeVideoLayout(1440, 757, 16 / 9);
    expect(video.left).toBe(576 + 19);
    expect(video.left + video.width).toBeLessThanOrEqual(1440 - 19);
  });

  it('reports the card slot the stylesheet gives the text card', () => {
    const { card } = computeVideoLayout(1440, 757, 16 / 9);
    expect(card.left).toBe(Math.round(1440 * 0.03));
    expect(card.width).toBe(Math.round(1440 * 0.37));
  });

  const SIZES = [[1025, 800], [1100, 900], [1280, 720], [1440, 757], [1920, 1080], [3440, 1440]];
  const ASPECTS = [16 / 9, 4 / 3, 1.4786, 1, 9 / 16];

  it.each(SIZES)('is beside the card, never over it, at %ix%i on a horizontal layout', (W, H) => {
    for (const aspect of ASPECTS) {
      const { mode, video } = computeVideoLayout(W, H, aspect);
      expect(mode, `aspect ${aspect}`).toBe('side-by-side');
      expect(video.left, `aspect ${aspect}`).toBe(cardRight(W) + pad(W, H));
      expect(video.left + video.width, `aspect ${aspect}`).toBeLessThanOrEqual(W - pad(W, H));
    }
    const region = computeVideoLetterboxRegion(W, H);
    expect(region.left).toBe(cardRight(W) + pad(W, H));
    expect(region.left + region.width).toBe(W - pad(W, H));
  });

  it('takes the card geometry from the stylesheet', async () => {
    const sheet = document.createElement('style');
    sheet.textContent = ':root { --telar-card-side-left: 10%; --telar-card-side-width: 30%; }';
    document.head.appendChild(sheet);
    try {
      vi.resetModules();
      const fresh = await import('../../assets/js/telar-story/video-layout.js');
      // pad = round(800 * 0.025) = 20; the card ends at 40% of 1000
      expect(fresh.computeVideoLetterboxRegion(1000, 800).left).toBe(400 + 20);
      expect(fresh.computeVideoLayout(1000, 800, 16 / 9).card).toMatchObject({ left: 100, width: 300 });
    } finally {
      sheet.remove();
    }
  });
});

// The stylesheet cannot share a constant with the script, so this holds the
// text card's rule to the variables whose :root mirror video-layout.js reads.
describe('the side card geometry in the stylesheet', () => {
  const read = (f) => readFileSync(resolve(process.cwd(), f), 'utf8');

  it('builds the text card from the side-card variables', () => {
    const rule = read('_sass/_story.scss').match(/\n\.text-card \{([^}]*)\}/);
    expect(rule, 'the base .text-card rule').not.toBeNull();
    expect(rule[1]).toMatch(/\n\s*left: \$telar-card-side-left;/);
    expect(rule[1]).toMatch(/\n\s*width: \$telar-card-side-width;/);
  });

  it('mirrors those variables on :root', () => {
    const scss = read('_sass/_responsive.scss');
    expect(scss).toMatch(/--telar-card-side-left:\s*#\{\$telar-card-side-left\};/);
    expect(scss).toMatch(/--telar-card-side-width:\s*#\{\$telar-card-side-width\};/);
  });
});

// ── buildYouTubeEmbedConfig ───────────────────────────────────────────────────

describe('buildYouTubeEmbedConfig', () => {
  it('returns videoId in the config object', () => {
    const cfg = buildYouTubeEmbedConfig('dQw4w9WgXcQ', 0, 0, false);
    expect(cfg.videoId).toBe('dQw4w9WgXcQ');
  });

  it('returns playerVars with start set to clipStart', () => {
    const cfg = buildYouTubeEmbedConfig('abc123', 30, 90, false);
    expect(cfg.playerVars.start).toBe(30);
  });

  it('returns playerVars with autoplay disabled', () => {
    const cfg = buildYouTubeEmbedConfig('abc123', 0, 0, false);
    expect(cfg.playerVars.autoplay).toBe(0);
  });

  it('omits loop/playlist playerVars (segment looping handled by rAF polling)', () => {
    const cfg = buildYouTubeEmbedConfig('dQw4w9WgXcQ', 0, 0, true);
    expect(cfg.playerVars.loop).toBeUndefined();
    expect(cfg.playerVars.playlist).toBeUndefined();
  });

  it('sets rel=0 and modestbranding=1', () => {
    const cfg = buildYouTubeEmbedConfig('abc', 0, 0, false);
    expect(cfg.playerVars.rel).toBe(0);
    expect(cfg.playerVars.modestbranding).toBe(1);
  });

  it('sets controls=1', () => {
    const cfg = buildYouTubeEmbedConfig('abc', 0, 0, false);
    expect(cfg.playerVars.controls).toBe(1);
  });
});

// ── buildGDriveEmbedUrl ───────────────────────────────────────────────────────

describe('buildGDriveEmbedUrl', () => {
  it('returns correct preview URL for a file ID', () => {
    expect(buildGDriveEmbedUrl('abc123XYZ')).toBe(
      'https://drive.google.com/file/d/abc123XYZ/preview'
    );
  });

  it('URL contains /preview suffix', () => {
    const url = buildGDriveEmbedUrl('someFileId');
    expect(url).toMatch(/\/preview$/);
  });
});

// ── formatClipTime ────────────────────────────────────────────────────────────

describe('formatClipTime', () => {
  it('formats 0 as 0:00', () => {
    expect(formatClipTime(0)).toBe('0:00');
  });

  it('formats 42 seconds as 0:42', () => {
    expect(formatClipTime(42)).toBe('0:42');
  });

  it('formats 67 seconds as 1:07', () => {
    expect(formatClipTime(67)).toBe('1:07');
  });

  it('formats 60 seconds as 1:00', () => {
    expect(formatClipTime(60)).toBe('1:00');
  });

  it('formats 3600 seconds as 60:00', () => {
    expect(formatClipTime(3600)).toBe('60:00');
  });

  it('pads single-digit seconds with leading zero', () => {
    expect(formatClipTime(65)).toBe('1:05');
  });

  it('handles fractional seconds (floors)', () => {
    expect(formatClipTime(42.9)).toBe('0:42');
  });
});
