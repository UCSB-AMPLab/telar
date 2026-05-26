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
 * @version v1.4.0
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// extractAllPages has its own coverage (iiif-manifest.test.js); stub it so this
// spec depends only on the OSD constructor options, not on manifest parsing.
vi.mock('../../assets/js/telar-story/iiif-manifest.js', () => ({
  extractAllPages: () => [{ tileSource: 'https://example.test/iiif/info.json' }],
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
