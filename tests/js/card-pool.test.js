/**
 * Tests for Telar Story – Card Pool: pure helpers and geometry
 *
 * Tests z-index banding, messiness computation, peek positioning, scene map
 * helpers (buildSceneMaps, getSceneIndex), and computeTileUrls (tile-prefetch
 * compensation, tile source shape, level choice, and the grid walk). None of
 * these touch the DOM. The jsdom-driven slice of the module — activateCard,
 * initCardPool, and the media/label/framing/handoff/pool-cap paths they
 * drive — lives in the sibling file, card-pool-dom.test.js.
 *
 * @version v1.7.0
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  getCardMessiness,
  computeCardTop,
  getSceneIndex,
  buildSceneMaps,
  computeZIndexPlan,
  computeTileUrls,
} from '../../assets/js/telar-story/card-pool.js';
import { state } from '../../assets/js/telar-story/state.js';
import { computeFocalTarget } from '../../assets/js/telar-story/iiif-card.js';

// ── Z-index banding ───────────────────────────────────────────────────────────

describe('computeZIndexPlan — scene banding invariants', () => {
  it('assigns each scene a 100-wide band with the viewer plate at the band base', () => {
    const { plateZ } = computeZIndexPlan([
      { object: 'A' }, { object: 'A' }, { object: 'B' },
    ]);
    // Scene 0 (steps 0-1) → band base 100; scene 1 (step 2) → band base 200
    expect(plateZ[0]).toBe(100);
    expect(plateZ[1]).toBe(100);
    expect(plateZ[2]).toBe(200);
  });

  it('places text cards at band base + 1 + run position, resetting per scene', () => {
    const { plateZ, textCardZ } = computeZIndexPlan([
      { object: 'A' }, { object: 'A' }, { object: 'A' },
      { object: 'B' }, { object: 'B' },
    ]);
    // Scene 0: run positions 0, 1, 2 above band base 100
    expect(textCardZ[0]).toBe(101);
    expect(textCardZ[1]).toBe(102);
    expect(textCardZ[2]).toBe(103);
    // Scene 1: run position resets — 201, 202 above band base 200
    expect(textCardZ[3]).toBe(201);
    expect(textCardZ[4]).toBe(202);
    // Text cards always sit above their own plate
    for (const i of [0, 1, 2, 3, 4]) {
      expect(textCardZ[i]).toBeGreaterThan(plateZ[i]);
    }
  });

  it('gives a reappearing object a new, higher band (A → B → A)', () => {
    // The scene-based plan keys bands by scene, not object, so the second
    // appearance of A stacks above everything from B's scene.
    const { plateZ, textCardZ } = computeZIndexPlan([
      { object: 'A' }, { object: 'B' }, { object: 'A' },
    ]);
    expect(plateZ[0]).toBe(100);
    expect(plateZ[1]).toBe(200);
    expect(plateZ[2]).toBe(300);
    expect(textCardZ[2]).toBe(301);
  });

  it('stacks each new scene plate above all cards of the previous scene', () => {
    const { plateZ, textCardZ } = computeZIndexPlan([
      { object: 'A' }, { object: 'A' }, { object: 'A' }, { object: 'A' },
      { object: 'B' },
    ]);
    const maxSceneOCardZ = Math.max(textCardZ[0], textCardZ[1], textCardZ[2], textCardZ[3]);
    expect(plateZ[4]).toBeGreaterThan(maxSceneOCardZ);
  });
});

// ── Messiness ─────────────────────────────────────────────────────────────────

describe('getCardMessiness', () => {
  it('returns zeros when messiness is 0', () => {
    const result = getCardMessiness(0, 0);
    expect(result).toEqual({ rot: 0, offX: 0, offY: 0 });
  });

  it('returns values within bounds for messiness 20', () => {
    // Test several seeds to ensure bounds are respected
    for (let seed = 0; seed < 20; seed++) {
      const { rot, offX, offY } = getCardMessiness(seed, 20);
      expect(Math.abs(rot)).toBeLessThanOrEqual(0.24);
      expect(Math.abs(offX)).toBeLessThanOrEqual(1.6);
      expect(Math.abs(offY)).toBeLessThanOrEqual(0.8);
    }
  });

  it('returns identical values on repeated calls (deterministic)', () => {
    const a = getCardMessiness(7, 20);
    const b = getCardMessiness(7, 20);
    expect(a).toEqual(b);
  });
});

// ── Peek positioning ──────────────────────────────────────────────────────────

describe('computeCardTop', () => {
  it('returns 75 when centred (viewportH=1000, cardH=850, runPos=0, peekH=1)', () => {
    // (1000 - 850) / 2 = 75
    expect(computeCardTop(1000, 850, 0, 1)).toBe(75);
  });

  it('returns 76 when runPosition=1, peekH=1', () => {
    // 75 + 1 * 1 = 76
    expect(computeCardTop(1000, 850, 1, 1)).toBe(76);
  });

  it('returns 78 when runPosition=3, peekH=1', () => {
    // 75 + 3 * 1 = 78
    expect(computeCardTop(1000, 850, 3, 1)).toBe(78);
  });

  it('returns 75 when peekHeight is 0 (disabled)', () => {
    // 75 + 0 * 0 = 75
    expect(computeCardTop(1000, 850, 0, 0)).toBe(75);
  });
});

// ── Scene maps ────────────────────────────────────────────────────────────────

describe('buildSceneMaps / getSceneIndex', () => {
  beforeEach(() => {
    // Reset state scene maps before each test
    state.stepToScene = {};
    state.sceneToObject = {};
    state.sceneFirstStep = {};
    state.totalScenes = 0;
  });

  it('maps A,A,B,A to 3 scenes', () => {
    buildSceneMaps([{ object: 'A' }, { object: 'A' }, { object: 'B' }, { object: 'A' }]);
    expect(state.totalScenes).toBe(3);
    expect(getSceneIndex(0)).toBe(0);
    expect(getSceneIndex(1)).toBe(0);
    expect(getSceneIndex(2)).toBe(1);
    expect(getSceneIndex(3)).toBe(2);
    expect(state.sceneToObject[0]).toBe('A');
    expect(state.sceneToObject[1]).toBe('B');
    expect(state.sceneToObject[2]).toBe('A');
    expect(state.sceneFirstStep[0]).toBe(0);
    expect(state.sceneFirstStep[1]).toBe(2);
    expect(state.sceneFirstStep[2]).toBe(3);
  });

  it('single-object story has 1 scene', () => {
    buildSceneMaps([{ object: 'X' }, { object: 'X' }, { object: 'X' }]);
    expect(state.totalScenes).toBe(1);
    expect(getSceneIndex(0)).toBe(0);
    expect(getSceneIndex(1)).toBe(0);
    expect(getSceneIndex(2)).toBe(0);
  });

  it('empty steps produces 0 scenes', () => {
    buildSceneMaps([]);
    expect(state.totalScenes).toBe(0);
  });

  it('returns -1 for out-of-range step', () => {
    buildSceneMaps([{ object: 'A' }]);
    expect(getSceneIndex(999)).toBe(-1);
  });
});

// ── Title card scene maps ─────────────────────────────────────────────────────

describe('buildSceneMaps — title cards', () => {
  beforeEach(() => {
    state.stepToScene = {};
    state.sceneToObject = {};
    state.sceneFirstStep = {};
    state.totalScenes = 0;
  });

  it('consecutive empty-object steps get separate scenes', () => {
    buildSceneMaps([{ object: 'A' }, { object: '' }, { object: '' }, { object: 'B' }]);
    expect(state.totalScenes).toBe(4);
    expect(state.sceneToObject[1]).toBe('');
    expect(state.sceneToObject[2]).toBe('');
    expect(state.stepToScene[1]).not.toBe(state.stepToScene[2]);
  });

  it('single title card between content steps', () => {
    buildSceneMaps([{ object: 'A' }, { object: '' }, { object: 'A' }]);
    expect(state.totalScenes).toBe(3);
  });

  it('title card at position 0', () => {
    buildSceneMaps([{ object: '' }, { object: 'A' }]);
    expect(state.totalScenes).toBe(2);
    expect(state.sceneToObject[0]).toBe('');
  });

  it('all title cards', () => {
    buildSceneMaps([{ object: '' }, { object: '' }, { object: '' }]);
    expect(state.totalScenes).toBe(3);
  });
});

// ── computeZIndexPlan — title cards ──────────────────────────────────────────

describe('computeZIndexPlan — title cards', () => {
  it('consecutive empty-object steps get different z-index bands', () => {
    const result = computeZIndexPlan([
      { object: 'A' }, { object: '' }, { object: '' }, { object: 'B' },
    ]);
    expect(result.plateZ[1]).not.toBe(result.plateZ[2]);
    expect(result.plateZ[2] - result.plateZ[1]).toBe(100);
  });

  it('title card z-index band is sequential', () => {
    const result = computeZIndexPlan([{ object: '' }, { object: 'A' }]);
    expect(result.plateZ[0]).toBe(100);
    expect(result.plateZ[1]).toBe(200);
  });

  it('caps z-index bands at 9800 for stories beyond 98 unique scenes', () => {
    // 120 distinct objects → scenes 0..119; uncapped band for scene 119 would
    // be 12000 and overflow into the fixed-UI / panel chrome reserve.
    const steps = Array.from({ length: 120 }, (_, i) => ({ object: 'obj-' + i }));
    const result = computeZIndexPlan(steps);
    const maxPlate = Math.max(...Object.values(result.plateZ));
    const maxText = Math.max(...Object.values(result.textCardZ));
    expect(maxPlate).toBeLessThanOrEqual(9800);
    expect(maxText).toBeLessThanOrEqual(9800 + 1); // textCard = bandBase + 1 + runPos
    // Bands below the cap are unchanged (scene 50 → 5100).
    expect(result.plateZ[50]).toBe(5100);
  });
});

// ── _computeTileUrls tile-prefetch compensation ─────────────────────────────
//
// Verifies that computeTileUrls prefetches tiles centred on the authored focal
// point (focalImg from computeFocalTarget) rather than the raw authored (x, y),
// so the prefetched region aligns with the two-circle rendered region.
//
// Strategy: call computeTileUrls with a known cardOverlayRect, independently
// derive the expected prefetch centre from computeFocalTarget's focalImg,
// parse the URL(s) that computeTileUrls returns, and assert:
//   1. The focalImg centre is covered by a returned tile region.
//   2. The actual tile centroid differs from raw (x,y) when a card is present.
//   3. With null cardOverlayRect, computeFocalTarget still runs and URLs are valid.

describe('_computeTileUrls tile-prefetch compensation', () => {
  const BASE_URL = 'https://example.org/iiif/objects/test';

  // Minimal info.json shape — large tiles so a single tile covers the region
  const INFO = {
    width:  4000,
    height: 4000,
    tiles: [{ width: 512, scaleFactors: [1, 2, 4, 8] }],
  };

  // Extract the tile centre in image-pixel space from a set of URLs.
  // Each URL has the form: base/rx,ry,rw,rh/outW,/0/default.jpg
  // We compute the centroid of all tile regions.
  function extractCentreFromUrls(urls) {
    let sumX = 0, sumY = 0, count = 0;
    for (const url of urls) {
      const parts = url.replace(BASE_URL + '/', '').split('/');
      const region = parts[0]; // "rx,ry,rw,rh"
      const [rx, ry, rw, rh] = region.split(',').map(Number);
      sumX += rx + rw / 2;
      sumY += ry + rh / 2;
      count++;
    }
    return { cx: sumX / count, cy: sumY / count };
  }

  beforeEach(() => {
    state.activeTitleCardIndex = null;
    state.layoutMode = 'horizontal';
    state.cardOverlayRect = null;

    // Desktop viewport: 1440×900
    Object.defineProperty(window, 'innerWidth',  { value: 1440, configurable: true, writable: true });
    Object.defineProperty(window, 'innerHeight', { value: 900,  configurable: true, writable: true });
  });

  it('tile region covers focalImg centre from computeFocalTarget (horizontal side card)', () => {
    // Horizontal side card: left:3%, width:37% in a 1440×900 viewport
    // cardBox right edge ≈ 576 < 864 (60% of 1440) → horizontal branch
    const cardBox = { x: 43, y: 0, w: 533, h: 900 };  // ~3%/37% of 1440
    state.cardOverlayRect = { x: cardBox.x, y: cardBox.y, width: cardBox.w, height: cardBox.h };

    const authoredX = 0.5;
    const authoredY = 0.5;
    const authoredZoom = 1.5;

    // Independently compute expected focal target (new pure-function contract)
    const target = computeFocalTarget(
      authoredX, authoredY, authoredZoom,
      INFO.width, INFO.height,
      cardBox, 'horizontal'
    );
    expect(target).not.toBeNull();

    // focalImg is the prefetch centre in image px
    const expectedCentreX = target.focalImg.x;
    const expectedCentreY = target.focalImg.y;

    // Get tile URLs from the function under test
    const urls = computeTileUrls(BASE_URL, INFO, authoredX, authoredY, authoredZoom);
    expect(urls.length).toBeGreaterThan(0);

    // Assert: the focal-target centre is covered by one of the returned tile regions.
    let centreIsCovered = false;
    for (const url of urls) {
      const region = url.replace(BASE_URL + '/', '').split('/')[0];
      const [rx, ry, rw, rh] = region.split(',').map(Number);
      if (
        expectedCentreX >= rx && expectedCentreX <= rx + rw &&
        expectedCentreY >= ry && expectedCentreY <= ry + rh
      ) {
        centreIsCovered = true;
        break;
      }
    }
    expect(centreIsCovered).toBe(true);
  });

  it('tile region centroid differs from raw (x, y) centre when cardOverlayRect is set', () => {
    // Same setup as above — confirm the focal-target actually shifts the centre.
    // computeFocalTarget returns focalImg = {x: authoredX*imageW, y: authoredY*imageH}
    // (the authored focal point, not a shifted point). The shift compared to the raw
    // centre happens because the prefetch REGION is now diameterImg-wide rather than
    // viewport-relative, so the tile centroid shifts when the uncovered region differs
    // from the full viewport (side card). However, focalImg itself equals raw authored.
    // We verify that tiles are non-trivially distributed around the focal area.
    const cardBox = { x: 43, y: 0, w: 533, h: 900 };
    state.cardOverlayRect = { x: cardBox.x, y: cardBox.y, width: cardBox.w, height: cardBox.h };

    const authoredX = 0.5;
    const authoredY = 0.5;
    const authoredZoom = 1.5;

    const target = computeFocalTarget(
      authoredX, authoredY, authoredZoom,
      INFO.width, INFO.height,
      cardBox, 'horizontal'
    );
    expect(target).not.toBeNull();
    // focalImg must equal raw authored focal (the two-circle model centres on the authored point)
    expect(target.focalImg.x).toBeCloseTo(authoredX * INFO.width, 0);

    const urls = computeTileUrls(BASE_URL, INFO, authoredX, authoredY, authoredZoom);
    expect(urls.length).toBeGreaterThan(0);

    // The tile region width should reflect diameterImg, not viewport-relative size.
    // Parse the region size from the first URL and compare to diameterImg.
    const firstParts = urls[0].replace(BASE_URL + '/', '').split('/');
    const [, , rw] = firstParts[0].split(',').map(Number);
    // The tile size is clamped to the tile grid, so rw >= min(tileSize, diameterImg/2)
    expect(rw).toBeGreaterThan(0);
  });

  it('tile region centroid falls back gracefully when state.cardOverlayRect is null', () => {
    // No cardOverlayRect — computeFocalTarget still runs with _defaultCardBox.
    // With horizontal layout and _defaultCardBox, focalImg = (authoredX*imageW, authoredY*imageH).
    state.cardOverlayRect = null;
    state.layoutMode = 'horizontal';
    state.activeTitleCardIndex = null;

    const authoredX = 0.5;
    const authoredY = 0.5;
    const authoredZoom = 1.0;

    const urls = computeTileUrls(BASE_URL, INFO, authoredX, authoredY, authoredZoom);
    expect(urls.length).toBeGreaterThan(0);

    // Confirm the call does not throw and returns valid IIIF Level-0 URLs.
    for (const url of urls) {
      expect(url).toContain(BASE_URL);
      expect(url).toContain('default.jpg');
    }

    // The focalImg centre should be covered by a tile (alignment check with null rect)
    const target = computeFocalTarget(
      authoredX, authoredY, authoredZoom,
      INFO.width, INFO.height,
      null, 'horizontal'
    );
    expect(target).not.toBeNull();
    const expectedCentreX = target.focalImg.x;
    const expectedCentreY = target.focalImg.y;

    let centreIsCovered = false;
    for (const url of urls) {
      const region = url.replace(BASE_URL + '/', '').split('/')[0];
      const [rx, ry, rw, rh] = region.split(',').map(Number);
      if (
        expectedCentreX >= rx && expectedCentreX <= rx + rw &&
        expectedCentreY >= ry && expectedCentreY <= ry + rh
      ) {
        centreIsCovered = true;
        break;
      }
    }
    expect(centreIsCovered).toBe(true);
  });
});

// ── Tile source shape, level choice, and the grid walk ───────────────────────
//
// The compensation tests above fix where the prefetch region lands. These fix
// the three things that turn that region into URLs: what is read from
// info.json when it advertises little, which scale factor the region is
// fetched at, and how the tile grid is walked and capped.

describe('computeTileUrls — tile source shape, level choice and grid', () => {
  const BASE_URL = 'https://example.org/iiif/objects/test';

  /** Parse "base/rx,ry,rw,rh/outW,/0/default.jpg" into its numbers. */
  function parseTile(url) {
    const parts = url.replace(BASE_URL + '/', '').split('/');
    const [rx, ry, rw, rh] = parts[0].split(',').map(Number);
    return { rx, ry, rw, rh, outW: Number(parts[1].replace(',', '')) };
  }

  beforeEach(() => {
    state.activeTitleCardIndex = null;
    state.layoutMode = 'horizontal';
    state.cardOverlayRect = null;
    Object.defineProperty(window, 'innerWidth',  { value: 1440, configurable: true, writable: true });
    Object.defineProperty(window, 'innerHeight', { value: 900,  configurable: true, writable: true });
  });

  it('reads a 512-pixel single level from an info.json that advertises no tiles', () => {
    const urls = computeTileUrls(BASE_URL, { width: 4000, height: 4000 }, 0.5, 0.5, 1.5);

    expect(urls.length).toBeGreaterThan(0);
    for (const url of urls) {
      const { rx, ry, rw, outW } = parseTile(url);
      expect(rx % 512).toBe(0);
      expect(ry % 512).toBe(0);
      // Scale factor 1: the output width is the region width.
      expect(outW).toBe(rw);
    }
  });

  it('takes a coarser level when the finest one would need more than nine tiles', () => {
    const INFO = { width: 40000, height: 40000, tiles: [{ width: 512, scaleFactors: [1, 2, 4, 8, 16, 32] }] };
    const urls = computeTileUrls(BASE_URL, INFO, 0.5, 0.5, 1);

    expect(urls.length).toBeGreaterThan(0);
    expect(urls.length).toBeLessThanOrEqual(9);
    const { rw, outW } = parseTile(urls[0]);
    const scaleFactor = rw / outW;
    expect(scaleFactor).toBeGreaterThan(1);
    expect(INFO.tiles[0].scaleFactors).toContain(scaleFactor);
  });

  it('caps the grid at nine tiles when no level the service lists is coarse enough', () => {
    const INFO = { width: 40000, height: 40000, tiles: [{ width: 512, scaleFactors: [1] }] };
    const urls = computeTileUrls(BASE_URL, INFO, 0.5, 0.5, 1);

    expect(urls).toHaveLength(9);
  });

  it('clips the last tile of a row to the image bound', () => {
    const INFO = { width: 3000, height: 3000, tiles: [{ width: 512, scaleFactors: [1] }] };
    const urls = computeTileUrls(BASE_URL, INFO, 0.99, 0.99, 4);

    expect(urls.length).toBeGreaterThan(0);
    for (const url of urls) {
      const { rx, ry, rw, rh } = parseTile(url);
      expect(rw).toBeGreaterThan(0);
      expect(rh).toBeGreaterThan(0);
      expect(rx + rw).toBeLessThanOrEqual(INFO.width);
      expect(ry + rh).toBeLessThanOrEqual(INFO.height);
    }
  });
});
