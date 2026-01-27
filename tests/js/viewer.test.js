/**
 * Tests for Telar Story – Viewer Card Management (unit-testable functions)
 *
 * Tests getManifestUrl and buildObjectsIndex, which handle IIIF manifest
 * URL resolution and object data indexing. These functions depend on
 * state.objectsIndex and window globals but do not require UniversalViewer
 * or real DOM elements.
 *
 * @version v0.7.0-beta
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { state } from '../../assets/js/telar-story/state.js';
import { getManifestUrl, buildObjectsIndex } from '../../assets/js/telar-story/viewer.js';

// ── buildObjectsIndex ────────────────────────────────────────────────────────

describe('buildObjectsIndex', () => {
  afterEach(() => {
    state.objectsIndex = {};
    delete window.objectsData;
  });

  it('indexes objects by object_id', () => {
    window.objectsData = [
      { object_id: 'obj-1', title: 'Object One' },
      { object_id: 'obj-2', title: 'Object Two' },
    ];
    buildObjectsIndex();
    expect(state.objectsIndex['obj-1'].title).toBe('Object One');
    expect(state.objectsIndex['obj-2'].title).toBe('Object Two');
  });

  it('handles empty objectsData', () => {
    window.objectsData = [];
    buildObjectsIndex();
    expect(Object.keys(state.objectsIndex)).toHaveLength(0);
  });

  it('handles missing objectsData', () => {
    delete window.objectsData;
    buildObjectsIndex();
    expect(Object.keys(state.objectsIndex)).toHaveLength(0);
  });
});

// ── getManifestUrl ───────────────────────────────────────────────────────────

describe('getManifestUrl', () => {
  beforeEach(() => {
    state.objectsIndex = {};
    delete window.location;
    window.location = {
      pathname: '/telar/stories/story-1/',
      origin: 'https://example.com',
    };
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'log').mockImplementation(() => {});
  });

  afterEach(() => {
    state.objectsIndex = {};
    vi.restoreAllMocks();
  });

  it('returns source_url when present', () => {
    state.objectsIndex['obj-1'] = { source_url: 'https://ext.com/manifest.json' };
    expect(getManifestUrl('obj-1')).toBe('https://ext.com/manifest.json');
  });

  it('returns iiif_manifest when source_url is absent', () => {
    state.objectsIndex['obj-1'] = { iiif_manifest: 'https://ext.com/m.json' };
    expect(getManifestUrl('obj-1')).toBe('https://ext.com/m.json');
  });

  it('prefers source_url over iiif_manifest', () => {
    state.objectsIndex['obj-1'] = {
      source_url: 'https://primary.com/manifest.json',
      iiif_manifest: 'https://fallback.com/manifest.json',
    };
    expect(getManifestUrl('obj-1')).toBe('https://primary.com/manifest.json');
  });

  it('falls back to local URL when no external manifest', () => {
    state.objectsIndex['obj-1'] = { title: 'Local Object' };
    const result = getManifestUrl('obj-1');
    expect(result).toBe('https://example.com/telar/iiif/objects/obj-1/manifest.json');
  });

  it('falls back to local URL for unknown object and warns', () => {
    const result = getManifestUrl('unknown-obj');
    expect(result).toBe('https://example.com/telar/iiif/objects/unknown-obj/manifest.json');
    expect(console.warn).toHaveBeenCalledWith('Object not found:', 'unknown-obj');
  });

  it('ignores whitespace-only source_url', () => {
    state.objectsIndex['obj-1'] = { source_url: '   ' };
    const result = getManifestUrl('obj-1');
    expect(result).toBe('https://example.com/telar/iiif/objects/obj-1/manifest.json');
  });

  it('ignores empty string source_url', () => {
    state.objectsIndex['obj-1'] = { source_url: '' };
    const result = getManifestUrl('obj-1');
    expect(result).toBe('https://example.com/telar/iiif/objects/obj-1/manifest.json');
  });
});
