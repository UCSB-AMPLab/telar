/**
 * Tests for Telar Story – Audio Card
 *
 * Unit tests for pure (DOM-free) functions exported from audio-card.js.
 * WaveSurfer lifecycle functions require browser context and are covered
 * by acceptance testing.
 *
 * @version v1.5.0
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
  formatElapsedTime,
  deriveThemeColors,
  buildAudioControlsHTML,
  loadWaveSurferAPI,
} from '../../assets/js/telar-story/audio-card.js';

describe('formatElapsedTime', () => {
  it('formats 0 seconds as "0:00"', () => {
    expect(formatElapsedTime(0)).toBe('0:00');
  });

  it('formats 63 seconds as "1:03"', () => {
    expect(formatElapsedTime(63)).toBe('1:03');
  });

  it('formats 3661.7 seconds as "61:01"', () => {
    expect(formatElapsedTime(3661.7)).toBe('61:01');
  });

  it('pads single-digit seconds with leading zero', () => {
    expect(formatElapsedTime(65)).toBe('1:05');
  });

  it('handles fractional seconds by flooring', () => {
    expect(formatElapsedTime(59.9)).toBe('0:59');
  });
});

describe('deriveThemeColors', () => {
  it('returns an object with playedColor, unplayedColor, backgroundColor, clipRegionColor keys', () => {
    const colors = deriveThemeColors('#883C36');
    expect(colors).toHaveProperty('playedColor');
    expect(colors).toHaveProperty('unplayedColor');
    expect(colors).toHaveProperty('backgroundColor');
    expect(colors).toHaveProperty('clipRegionColor');
  });

  it('playedColor equals the barHex parameter (defaults to #ffffff)', () => {
    expect(deriveThemeColors('#883C36').playedColor).toBe('#ffffff');
  });

  it('unplayedColor contains "rgb" (opaque blended tint)', () => {
    expect(deriveThemeColors('#883C36').unplayedColor).toContain('rgb(');
  });

  it('backgroundColor contains "rgb" (opaque darkened accent)', () => {
    expect(deriveThemeColors('#883C36').backgroundColor).toContain('rgb(');
  });

  it('clipRegionColor contains "rgba" (opacity-based)', () => {
    expect(deriveThemeColors('#883C36').clipRegionColor).toContain('rgba');
  });

  it('correctly blends hex #000000 to opaque rgb result', () => {
    const colors = deriveThemeColors('#000000');
    // bg is darkened: r=0*0.7=0, blended with barHex #ffffff @25%: 0*0.75+255*0.25=63
    expect(colors.unplayedColor).toBe('rgb(64, 64, 64)');
  });

  it('correctly blends hex #ffffff to opaque rgb result', () => {
    const colors = deriveThemeColors('#ffffff');
    // bg is darkened: r=Math.round(255*0.7)=179, blended with barHex #ffffff @25%: 179*0.75+255*0.25=198
    expect(colors.unplayedColor).toBe('rgb(198, 198, 198)');
  });
});

describe('buildAudioControlsHTML', () => {
  it('returns a string containing "audio-controls" class', () => {
    expect(buildAudioControlsHTML()).toContain('audio-controls');
  });

  it('returns a string containing three button elements', () => {
    const html = buildAudioControlsHTML();
    const matches = html.match(/<button/g);
    expect(matches).not.toBeNull();
    expect(matches.length).toBe(3);
  });

  it('contains aria-label attributes on all buttons', () => {
    const html = buildAudioControlsHTML();
    const matches = html.match(/aria-label/g);
    expect(matches).not.toBeNull();
    expect(matches.length).toBe(3);
  });

  it('play button has class "audio-btn-play"', () => {
    expect(buildAudioControlsHTML()).toContain('audio-btn-play');
  });

  it('restart button has class "audio-btn-restart"', () => {
    expect(buildAudioControlsHTML()).toContain('audio-btn-restart');
  });

  it('mute button has class "audio-btn-mute"', () => {
    expect(buildAudioControlsHTML()).toContain('audio-btn-mute');
  });
});

describe('loadWaveSurferAPI (vendored, not CDN)', () => {
  let injected;

  beforeEach(() => {
    delete window._wsApiPromise;
    delete window.WaveSurfer;
    document.head.innerHTML = '';
    // Capture every <script> appended to <head> and stop jsdom from fetching it.
    injected = [];
    const realAppend = document.head.appendChild.bind(document.head);
    document.head.appendChild = (node) => {
      if (node.tagName === 'SCRIPT') injected.push(node);
      return realAppend(node);
    };
  });

  afterEach(() => {
    delete document.head.appendChild; // restore prototype method
    delete window._wsApiPromise;
    delete window.WaveSurfer;
  });

  it('injects the vendored core bundle, never a CDN URL', () => {
    loadWaveSurferAPI();
    expect(injected).toHaveLength(1);
    expect(injected[0].src).toContain('/assets/vendor/wavesurfer/wavesurfer.min.js');
    expect(injected[0].src).not.toContain('unpkg');
    expect(injected[0].src).not.toContain('cdn');
  });

  it('loads the Regions plugin from vendor only after the core resolves', () => {
    loadWaveSurferAPI();
    // Core injected first; plugin not injected until core.onload fires.
    expect(injected).toHaveLength(1);
    injected[0].onload();
    expect(injected).toHaveLength(2);
    expect(injected[1].src).toContain('/assets/vendor/wavesurfer/plugins/regions.min.js');
    expect(injected[1].src).not.toContain('unpkg');
  });

  it('resolves the promise once both core and plugin have loaded', async () => {
    const p = loadWaveSurferAPI();
    injected[0].onload();      // core ready
    injected[1].onload();      // regions ready
    await expect(p).resolves.toBeUndefined();
  });

  it('is a once-guard: repeat calls return the same Promise without re-injecting', () => {
    const first = loadWaveSurferAPI();
    const second = loadWaveSurferAPI();
    expect(second).toBe(first);
    expect(injected).toHaveLength(1);
  });
});
