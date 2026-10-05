/**
 * Regression guard — the IIIF viewer must use the Canvas2D drawer.
 *
 * OpenSeadragon 6 defaults to the WebGL drawer. WebGL's texImage2D() throws a
 * SecurityError for cross-origin <img> tiles loaded without CORS, so OSD's
 * createTexture() returns null, logs "Error creating texture in WebGL.", and
 * falls back to Canvas2D — leaving the viewer blank until the first zoom/pan.
 * Telar sites pull IIIF from arbitrary (cross-origin) servers, so the wrapper
 * pins `drawer: 'canvas'` (iiif-viewer.js) to avoid the WebGL path entirely.
 *
 * This test fails if that explicit drawer option is ever dropped or changed,
 * which would re-expose the blank-on-first-load defect for external IIIF.
 *
 * The onPageShown cases pin when the wrapper reports a page as shown: on
 * OSD's 'open' for the current page, never on 'open-failed', and never for
 * an open whose source is another page's. The object page writes its
 * address from that report.
 *
 * @version v1.8.0
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// extractAllPages has its own coverage (iiif-manifest.test.js); stub it so this
// spec depends only on the OSD constructor options, not on manifest parsing.
// The page list is swappable so the onPageShown cases can use several pages.
const manifestPages = vi.hoisted(() => ({
  list: [{ tileSource: 'https://example.test/iiif/info.json' }],
}));
vi.mock('../../assets/js/telar-story/iiif-manifest.js', () => ({
  extractAllPages: () => manifestPages.list,
}));

// test-hook only acts under ?telartest=1; stub it to keep the spec isolated.
vi.mock('../../assets/js/telar-story/test-hook.js', () => ({
  registerTestViewer: () => {},
  unregisterTestViewer: () => {},
}));

import { IiifViewer } from '../../assets/js/telar-story/iiif-viewer.js';

// Minimal OpenSeadragon stub: records the constructor options and fires the
// first 'open' handler so IiifViewer._init's `.ready` promise resolves.
function makeOsdMock() {
  // Regular function (not arrow) so it is constructable via `new`.
  return vi.fn(function () {
    let firstOpenFired = false;
    return {
      innerTracker: {},
      gestureSettingsMouse: {},
      addHandler(event, cb) {
        if (event === 'open' && !firstOpenFired) {
          firstOpenFired = true;
          setTimeout(cb, 0);
        }
      },
      removeHandler() {},
      open() {},
      destroy() {},
    };
  });
}

describe('IiifViewer OSD drawer (regression guard)', () => {
  let container;
  let originalOSD;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    originalOSD = window.OpenSeadragon;
    window.OpenSeadragon = makeOsdMock();
    // Deterministic rAF (IiifViewer defers .ready resolution one frame).
    vi.stubGlobal('requestAnimationFrame', (cb) => setTimeout(() => cb(0), 0));
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({}) })));
  });

  afterEach(() => {
    container.remove();
    window.OpenSeadragon = originalOSD;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('instantiates OpenSeadragon with drawer "canvas" (never the WebGL default)', async () => {
    const viewer = new IiifViewer({
      container,
      manifestUrl: 'https://example.test/iiif/manifest.json',
    });
    await viewer.ready;

    expect(window.OpenSeadragon).toHaveBeenCalledTimes(1);
    const opts = window.OpenSeadragon.mock.calls[0][0];
    expect(opts.drawer).toBe('canvas');
  });
});

// An OpenSeadragon stub that keeps its handlers so a case can raise 'open'
// and 'open-failed' the way OSD does, with the source it opened.
function makeEventOsdMock() {
  return vi.fn(function (options) {
    const handlers = {};
    const osd = {
      innerTracker: {},
      gestureSettingsMouse: {},
      addHandler(event, cb) { (handlers[event] = handlers[event] || []).push(cb); },
      removeHandler(event, cb) { handlers[event] = (handlers[event] || []).filter((h) => h !== cb); },
      raise(event, data) { (handlers[event] || []).slice().forEach((h) => h(data)); },
      open() {},
      destroy() {},
    };
    setTimeout(() => osd.raise('open', { source: options.tileSources }), 0);
    return osd;
  });
}

describe('IiifViewer onPageShown', () => {
  const pages = [
    { tileSource: 'https://example.test/iiif/p1/info.json' },
    { tileSource: 'https://example.test/iiif/p2/info.json' },
    { tileSource: { type: 'image', url: 'https://example.test/p3.jpg' } },
  ];
  let container;
  let originalOSD;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    originalOSD = window.OpenSeadragon;
    window.OpenSeadragon = makeEventOsdMock();
    manifestPages.list = pages;
    vi.stubGlobal('requestAnimationFrame', (cb) => setTimeout(() => cb(0), 0));
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({}) })));
  });

  afterEach(() => {
    container.remove();
    window.OpenSeadragon = originalOSD;
    manifestPages.list = [{ tileSource: 'https://example.test/iiif/info.json' }];
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  async function openViewer(startPage) {
    const shown = [];
    const viewer = new IiifViewer({
      container,
      manifestUrl: 'https://example.test/iiif/manifest.json',
      startPage,
      onPageShown: (page0) => shown.push(page0),
    });
    await viewer.ready;
    return { viewer, shown };
  }

  it('reports the first page once its image opens', async () => {
    const { shown } = await openViewer(1);
    expect(shown).toEqual([1]);
  });

  it('reports a later page on open, and nothing on open-failed', async () => {
    const { viewer, shown } = await openViewer(0);
    viewer.setPage(2);
    expect(shown).toEqual([0]);
    viewer.viewer.raise('open-failed', { message: 'no tiles' });
    expect(shown).toEqual([0]);
    viewer.setPage(1);
    viewer.viewer.raise('open', { source: pages[1].tileSource });
    expect(shown).toEqual([0, 1]);
    viewer.setPage(2);
    viewer.viewer.raise('open', { source: pages[2].tileSource });
    expect(shown).toEqual([0, 1, 2]);
  });

  it('ignores an open for a page other than the one asked for last', async () => {
    const { viewer, shown } = await openViewer(0);
    viewer.setPage(1);
    viewer.setPage(2);
    viewer.viewer.raise('open', { source: pages[2].tileSource });
    viewer.viewer.raise('open', { source: pages[1].tileSource });
    expect(shown).toEqual([0, 2]);
  });
});
