/**
 * Tests for Telar Story – Video Card Pure Functions
 *
 * Verifies pure (no DOM, no player API) functions exported by video-card.js.
 * - computeVideoLayout: auto-layout algorithm
 * - buildYouTubeEmbedConfig: YouTube playerVars builder
 * - buildGDriveEmbedUrl: Google Drive preview URL builder
 * - formatClipTime: M:SS time formatter for ring display
 *
 * @version v1.0.0-beta
 */

import { describe, it, expect } from 'vitest';
import {
  computeVideoLayout,
  buildYouTubeEmbedConfig,
  buildGDriveEmbedUrl,
  formatClipTime,
} from '../../assets/js/telar-story/video-card.js';

// ── computeVideoLayout ────────────────────────────────────────────────────────

describe('computeVideoLayout', () => {
  it('returns side-by-side for a wide window with 16:9 video', () => {
    const layout = computeVideoLayout(1920, 1080, 16 / 9);
    expect(layout.mode).toBe('side-by-side');
  });

  it('returns stacked for a narrow window (600x800) with 16:9 video', () => {
    const layout = computeVideoLayout(600, 800, 16 / 9);
    expect(layout.mode).toBe('stacked');
  });

  it('returns stacked for mobile width (500x800) regardless of area', () => {
    // Mobile override: W < 768 always returns stacked
    const layout = computeVideoLayout(500, 800, 16 / 9);
    expect(layout.mode).toBe('stacked');
  });

  it('returns stacked for W=767 (just below mobile breakpoint)', () => {
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
    const narrow = computeVideoLayout(600, 800, 16 / 9);
    expect(wide.video.width * wide.video.height).toBeGreaterThan(0);
    expect(narrow.video.width * narrow.video.height).toBeGreaterThan(0);
  });

  it('card area is positive in all layout modes', () => {
    const wide = computeVideoLayout(1920, 1080, 16 / 9);
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
