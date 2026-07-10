/**
 * Tests for text-card.js — isFullObjectMode
 *
 * Verifies the zoom-aware layout detection logic:
 *   - zoom undefined / blank / null / <= 1.0 → full-object mode
 *   - zoom > 1.0 with coordinates → detail mode
 *   - no coordinates at all → full-object mode, regardless of zoom
 *
 * @version v1.6.0
 */

import { describe, it, expect } from 'vitest';
import { isFullObjectMode } from '../../assets/js/telar-story/text-card.js';

describe('isFullObjectMode', () => {
  it('returns true when zoom is undefined', () => {
    expect(isFullObjectMode({ zoom: undefined })).toBe(true);
  });

  it('returns true when zoom is empty string', () => {
    expect(isFullObjectMode({ zoom: '' })).toBe(true);
  });

  it('returns true when zoom is "1.0"', () => {
    expect(isFullObjectMode({ zoom: '1.0' })).toBe(true);
  });

  it('returns true when zoom is "0.5"', () => {
    expect(isFullObjectMode({ zoom: '0.5' })).toBe(true);
  });

  it('returns false when zoom is "2.5" with valid x and y coordinates', () => {
    expect(isFullObjectMode({ zoom: '2.5', x: '0.5', y: '0.3' })).toBe(false);
  });

  it('returns false when zoom is "1.5" with valid x and y coordinates', () => {
    expect(isFullObjectMode({ zoom: '1.5', x: '0.5', y: '0.3' })).toBe(false);
  });

  it('returns true when x, y, and zoom are all undefined (no coordinates)', () => {
    expect(isFullObjectMode({ x: undefined, y: undefined, zoom: undefined })).toBe(true);
  });

  it('returns true when zoom is "1" (integer boundary)', () => {
    expect(isFullObjectMode({ zoom: '1' })).toBe(true);
  });

  it('returns false when zoom is "1.01" (just above boundary) with valid x and y coordinates', () => {
    expect(isFullObjectMode({ zoom: '1.01', x: '0.5', y: '0.3' })).toBe(false);
  });

  it('returns true when zoom is null', () => {
    expect(isFullObjectMode({ zoom: null })).toBe(true);
  });

  it('returns true when zoom is "2.5" but x and y are both undefined (no coordinates overrides zoom)', () => {
    expect(isFullObjectMode({ zoom: '2.5', x: undefined, y: undefined })).toBe(true);
  });
});
