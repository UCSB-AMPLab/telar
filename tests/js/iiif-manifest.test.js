/**
 * Tests for Telar Story – IIIF Manifest Parser
 *
 * Covers the four pure functions exported from iiif-manifest.js:
 * extractAllPages, extractV3Pages, extractV2Pages, deriveInfoJsonFromImageUrl.
 * Loads canonical v2 and v3 manifest fixtures from tests/fixtures/iiif/
 * and exercises the v3-first / v2-fallback / garbage-input paths.
 *
 * The parser is pure — no DOM, no fetch, no state — so jsdom is incidental
 * here; fixtures are read at test time via Node fs + import.meta.url.
 *
 * @version v1.4.0
 */

import { describe, it, expect } from 'vitest';
import {
  extractAllPages,
  extractV3Pages,
  extractV2Pages,
  deriveInfoJsonFromImageUrl,
} from '../../assets/js/telar-story/iiif-manifest.js';
// Vite's native JSON import for the manifest fixtures. Used instead of
// fs + import.meta.url because the jsdom env resolves import.meta.url to a
// non-file URL.
import v2Manifest from '../fixtures/iiif/manifest-v2.json';
import v3Manifest from '../fixtures/iiif/manifest-v3.json';

// ── extractV2Pages ───────────────────────────────────────────────────────────

describe('extractV2Pages', () => {
  it('extracts pages from v2 service-id chain', () => {
    const pages = extractV2Pages(v2Manifest);
    expect(Array.isArray(pages)).toBe(true);
    expect(pages.length).toBeGreaterThanOrEqual(2);
    for (const page of pages) {
      expect(typeof page.tileSource).toBe('string');
      expect(page.tileSource.endsWith('/info.json')).toBe(true);
    }
  });

  it('returns [] for v2 manifest with empty sequences', () => {
    expect(extractV2Pages({ sequences: [] })).toEqual([]);
  });

  it('returns [] for v2 manifest missing canvases', () => {
    expect(extractV2Pages({ sequences: [{}] })).toEqual([]);
  });
});

// ── extractV3Pages ───────────────────────────────────────────────────────────

describe('extractV3Pages', () => {
  it('extracts pages from v3 service-id chain', () => {
    const pages = extractV3Pages(v3Manifest);
    expect(Array.isArray(pages)).toBe(true);
    expect(pages.length).toBeGreaterThan(0);
  });

  it('falls back to Image API URL when service is absent', () => {
    const pages = extractV3Pages(v3Manifest);
    const derived = pages.find((p) => p.tileSource.endsWith('/info.json'));
    expect(derived).toBeDefined();
  });

  it('returns [] for v3 manifest with no items', () => {
    expect(extractV3Pages({ items: [] })).toEqual([]);
  });
});

// ── deriveInfoJsonFromImageUrl ───────────────────────────────────────────────

describe('deriveInfoJsonFromImageUrl', () => {
  it('matches versioned IIIF Image API URLs (v3)', () => {
    expect(
      deriveInfoJsonFromImageUrl('https://example.invalid/iiif/3/abc/full/max/0/default.jpg')
    ).toBe('https://example.invalid/iiif/3/abc/info.json');
  });

  it('matches v2 URLs', () => {
    expect(
      deriveInfoJsonFromImageUrl('https://example.invalid/iiif/2/abc/full/full/0/default.jpg')
    ).toBe('https://example.invalid/iiif/2/abc/info.json');
  });

  it('returns null for unversioned URLs', () => {
    expect(
      deriveInfoJsonFromImageUrl('https://example.invalid/abc/full/full/0/default.jpg')
    ).toBeNull();
  });

  it('returns null for non-IIIF URLs', () => {
    expect(deriveInfoJsonFromImageUrl('https://example.invalid/foo.jpg')).toBeNull();
  });
});

// ── extractAllPages ──────────────────────────────────────────────────────────

describe('extractAllPages', () => {
  it('returns v3 pages when both formats present', () => {
    const both = { ...v3Manifest, sequences: v2Manifest.sequences };
    const result = extractAllPages(both);
    const v3Only = extractV3Pages(v3Manifest);
    expect(result).toEqual(v3Only);
  });

  it('falls through to v2 when v3 extraction yields []', () => {
    const result = extractAllPages(v2Manifest);
    expect(result.length).toBeGreaterThanOrEqual(2);
  });

  it('returns [] for empty-object manifest', () => {
    expect(extractAllPages({})).toEqual([]);
  });

  it('returns [] (does not throw) for null', () => {
    expect(() => extractAllPages(null)).not.toThrow();
    expect(extractAllPages(null)).toEqual([]);
  });

  it('returns [] (does not throw) for a string', () => {
    expect(() => extractAllPages('not-an-object')).not.toThrow();
    expect(extractAllPages('not-an-object')).toEqual([]);
  });

  it('returns [] for manifest with both formats empty', () => {
    expect(extractAllPages({ items: [], sequences: [] })).toEqual([]);
  });
});
