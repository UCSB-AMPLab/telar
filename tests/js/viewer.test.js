/**
 * Tests for Telar Story – Viewer Card Management (unit-testable functions)
 *
 * Tests getManifestUrl and buildObjectsIndex, which handle IIIF manifest
 * URL resolution and object data indexing. These functions depend on
 * state.objectsIndex and window globals but do not require a live viewer
 * instance or real DOM elements.
 *
 * @version v1.5.0
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { state } from '../../assets/js/telar-story/state.js';
import { getManifestUrl, buildObjectsIndex, prefetchStoryManifests } from '../../assets/js/telar-story/viewer.js';

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

// ── prefetchStoryManifests ───────────────────────────────────────────────────

describe('prefetchStoryManifests', () => {
  let fetchMock;
  beforeEach(() => {
    state.objectsIndex = {};
    state.manifestLoadTimes = [];
    document.body.innerHTML = '';
    fetchMock = vi.fn(() => Promise.resolve({ text: () => Promise.resolve('{}') }));
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  function addObject(id) {
    const el = document.createElement('div');
    el.dataset.object = id;
    document.body.appendChild(el);
  }

  it('resolves source_url || iiif_manifest, skips video hosts, uses force-cache', async () => {
    state.objectsIndex = {
      a: { object_id: 'a', source_url: 'https://example.org/a/manifest.json' },
      b: { object_id: 'b', iiif_manifest: 'https://example.org/b/manifest.json' },
      v: { object_id: 'v', source_url: 'https://youtube.com/watch?v=x' },
    };
    addObject('a'); addObject('b'); addObject('v');

    await prefetchStoryManifests();

    const urls = fetchMock.mock.calls.map(c => c[0]);
    expect(urls).toContain('https://example.org/a/manifest.json'); // source_url
    expect(urls).toContain('https://example.org/b/manifest.json'); // legacy iiif_manifest
    expect(urls.some(u => u.includes('youtube'))).toBe(false);     // video skipped
    expect(fetchMock.mock.calls.every(c => c[1] && c[1].cache === 'force-cache')).toBe(true);
    expect(state.manifestLoadTimes.length).toBe(2);
  });

  it('bounds concurrency to 3 simultaneous fetches', async () => {
    for (let i = 0; i < 8; i++) {
      state.objectsIndex['o' + i] = { object_id: 'o' + i, source_url: `https://ex.org/${i}/manifest.json` };
      addObject('o' + i);
    }
    let inFlight = 0, maxInFlight = 0;
    fetchMock.mockImplementation(() => {
      inFlight++; maxInFlight = Math.max(maxInFlight, inFlight);
      return new Promise(res => setTimeout(() => { inFlight--; res({ text: () => Promise.resolve('') }); }, 5));
    });
    await prefetchStoryManifests();
    expect(maxInFlight).toBeLessThanOrEqual(3);
    expect(fetchMock).toHaveBeenCalledTimes(8);
  });

  it('no objects → no fetches', async () => {
    await prefetchStoryManifests();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
