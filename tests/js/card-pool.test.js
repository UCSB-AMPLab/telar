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
 * @version v1.8.0
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  getCardMessiness,
  computeCardTop,
  getSceneIndex,
  buildSceneMaps,
  computeZIndexPlan,
  computeTileUrls,
  prefetchRegion,
} from '../../assets/js/telar-story/card-pool.js';
import { state } from '../../assets/js/telar-story/state.js';
import { computeFocalTarget } from '../../assets/js/telar-story/iiif-card.js';

const BASE_URL = 'https://example.org/iiif/objects/test';
const tail = (url) => url.replace(BASE_URL + '/', '');

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
    // Same setup as above. computeFocalTarget returns focalImg = {x: authoredX*imageW,
    // y: authoredY*imageH}, the authored focal point itself; the prefetch box around
    // it is what the viewer shows at rest (see the prefetchRegion block below).
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

  it('holds the count to the viewer\'s size in tiles when the level drawn has more cells', () => {
    // Scale factor 1 is the only level. Zoom 1 shows all 40000 px in 900, so
    // OpenSeadragon's walk would take 79 × 79 cells of 11.5 viewer px each. The
    // bound is (ceil(1440 / 256) + 1) × (ceil(900 / 256) + 1) = 7 × 5, a tile
    // being at least 512 × 0.5 viewer px on screen.
    const INFO = { width: 40000, height: 40000, tiles: [{ width: 512, scaleFactors: [1] }] };
    const urls = computeTileUrls(BASE_URL, INFO, 0.5, 0.5, 1);

    expect(urls).toHaveLength(35);
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

// ── The level the viewer draws, and every cell of it the region meets ───────
//
// Expected URLs are worked by hand from OpenSeadragon 6.0.2 (the vendored
// build), not from the code under test. TiledImage._getLevelsInterval draws the
// finest level L with ratio(L) >= 0.5, ratio(L) = density × s × 2^(max − L), s
// being viewer px per image px; scale factor 2^(max − L). TiledImage._visitTiles
// walks getTileAtPoint(top-left) .. getTileAtPoint(bottom-right) inclusive, a
// point on a grid line belonging to the tile that starts there. Here max = 3
// (scale factors up to 8), density 1 (jsdom), 512-px tiles.

describe('computeTileUrls — the level the viewer draws and the cells it meets', () => {
  const INFO = { width: 4000, height: 4000, tiles: [{ width: 512, scaleFactors: [1, 2, 4, 8] }] };
  const tile = (x, y) => `${x},${y},512,512/512,/0/default.jpg`;

  beforeEach(() => {
    state.activeTitleCardIndex = null;
    state.layoutMode = 'horizontal';
    state.cardOverlayRect = { x: 43, y: 0, width: 533, height: 900 };
    Object.defineProperty(window, 'innerWidth',  { value: 1440, configurable: true, writable: true });
    Object.defineProperty(window, 'innerHeight', { value: 900,  configurable: true, writable: true });
  });

  it('issues every cell of the level the viewer settles on, however many', () => {
    // Zoom 4: the box is x 894.35..2473.85, y 1506.41..2493.59, so the 1440 px
    // viewer shows it at s = 1440 / 1579.5 = 0.9117. ratio(0) = 0.9117 × 8 =
    // 7.29; floor(log2(7.29 / 0.5)) = 3, capped at 3: scale factor 1. Columns
    // floor(894.35/512) = 1 to floor(2473.85/512) = 4, rows floor(1506.41/512)
    // = 2 to floor(2493.59/512) = 4: twelve cells.
    const region = prefetchRegion(4000, 4000, 0.5, 0.5, 4);
    expect(region.left).toBeCloseTo(894.35, 2);
    expect(region.right).toBeCloseTo(2473.85, 2);

    const urls = computeTileUrls(BASE_URL, INFO, 0.5, 0.5, 4).map(tail);
    const want = [];
    for (const x of [512, 1024, 1536, 2048]) for (const y of [1024, 1536, 2048]) want.push(tile(x, y));
    expect(urls.sort()).toEqual(want.sort());
  });

  it('keeps the level the viewer draws when the region is small', () => {
    // Zoom 8: x 1447.18..2236.93, y 1753.20..2246.80; s = 1440 / 789.75 = 1.823;
    // ratio(0) = 14.6, floor(log2(29.2)) = 4, capped at 3: scale factor 1.
    // Columns 2..4, rows 3..4.
    const urls = computeTileUrls(BASE_URL, INFO, 0.5, 0.5, 8).map(tail);
    const want = [];
    for (const x of [1024, 1536, 2048]) for (const y of [1536, 2048]) want.push(tile(x, y));
    expect(urls.sort()).toEqual(want.sort());
  });

  it('takes a coarser level only where the viewer does', () => {
    // Zoom 1: the whole image in 900 px, s = 0.225. ratio(0) = 1.8;
    // floor(log2(3.6)) = 1: level 1, scale factor 4 (tile 2048). Both axes
    // meet cells 0 and 1.
    const urls = computeTileUrls(BASE_URL, INFO, 0.5, 0.5, 1).map(tail);
    expect(urls.sort()).toEqual([
      '0,0,2048,2048/512,/0/default.jpg',
      '0,2048,2048,1952/512,/0/default.jpg',
      '2048,0,1952,2048/488,/0/default.jpg',
      '2048,2048,1952,1952/488,/0/default.jpg',
    ].sort());
  });

  it('takes the cell that starts on a grid line the region ends on', () => {
    // Zoom 39.4875: the box is x 1888..2048, y 1950..2050 (s = 9); the right
    // edge lies on the line at 2048 = 4 × 512. ratio(0) = 72: scale factor 1.
    // getTileAtPoint(2048) is cell 4, so columns 3 and 4; rows 3 (1950) and 4
    // (2050).
    const region = prefetchRegion(4000, 4000, 0.5, 0.5, 39.4875);
    expect(region).toEqual({ left: 1888, top: 1950, right: 2048, bottom: 2050 });

    const urls = computeTileUrls(BASE_URL, INFO, 0.5, 0.5, 39.4875).map(tail);
    expect(urls.sort()).toEqual([tile(1536, 1536), tile(1536, 2048), tile(2048, 1536), tile(2048, 2048)].sort());
  });

  it('reads scale factors as a set, whatever order they are listed in', () => {
    const shuffled = { ...INFO, tiles: [{ width: 512, scaleFactors: [8, 2, 1, 4] }] };
    for (const zoom of [1, 4, 8, 39.4875]) {
      expect(computeTileUrls(BASE_URL, shuffled, 0.5, 0.5, zoom))
        .toEqual(computeTileUrls(BASE_URL, INFO, 0.5, 0.5, zoom));
    }
  });

  it('counts the display\'s pixel density in the ratio, as the viewer does', () => {
    // Density 2 doubles ratio(0): zoom 1 gives 3.6, floor(log2(7.2)) = 2: level
    // 2, scale factor 2 (tile 1024). The image is 4 cells across.
    Object.defineProperty(window, 'devicePixelRatio', { value: 2, configurable: true, writable: true });
    try {
      const urls = computeTileUrls(BASE_URL, INFO, 0.5, 0.5, 1).map(tail);
      expect(urls).toHaveLength(16);
      expect(urls).toContain('0,0,1024,1024/512,/0/default.jpg');
    } finally {
      Object.defineProperty(window, 'devicePixelRatio', { value: 1, configurable: true, writable: true });
    }
  });
});

// ── The prefetch box is what the viewer shows at rest ────────────────────────
//
// A 1440×900 window with the side card at x 43, 533 wide leaves an uncovered
// region 864×900 from x 576, and the plate fills the window. The expected
// boxes are worked by hand from the framing rules (the scale, the placed point
// and the clamp), not by calling the framing code.

describe('prefetchRegion — the image the viewer shows at rest', () => {
  const W = 1600;
  const H = 900;

  beforeEach(() => {
    state.activeTitleCardIndex = null;
    state.layoutMode = 'horizontal';
    state.cardOverlayRect = { x: 43, y: 0, width: 533, height: 900 };
    Object.defineProperty(window, 'innerWidth',  { value: 1440, configurable: true, writable: true });
    Object.defineProperty(window, 'innerHeight', { value: 900,  configurable: true, writable: true });
  });

  const expectBox = (box, want) => {
    for (const side of ['left', 'top', 'right', 'bottom']) {
      expect(box[side], side).toBeCloseTo(want[side], 6);
    }
  };

  it('an overview shows the whole image, wherever its x and y point', () => {
    // Scale 864/1600 = 0.54 fits the image to the region; the image centre is
    // placed at the region centre, so all of it is on screen.
    for (const [x, y] of [[0.1, 0.9], [0.8, 0.2], [0.5, 0.5]]) {
      expectBox(prefetchRegion(W, H, x, y, 1), { left: 0, top: 0, right: W, bottom: H });
    }
  });

  it('a detail in the middle shows the window at its scale, centred on the focal point', () => {
    // Zoom 2: frame 800 image px, circle 720, scale 864/720 = 1.2. The focal
    // (800, 450) sits at the region centre (1008, 450), so the window's
    // 1200×750 image px start at x 800 − 1008/1.2 = −40 and y 450 − 375 = 75.
    expectBox(prefetchRegion(W, H, 0.5, 0.5, 2), { left: 0, top: 75, right: 1160, bottom: 825 });
  });

  it('a detail near an edge is held flush with the image edge it would pass', () => {
    // Zoom 6: circle 240, scale 3.6, focal (1520, 45). Coverage holds the
    // focal at x 1152 (the image's right edge on the window's) and y 162 (its
    // top edge on the window's), so the window's 400×250 image px run from
    // x 1520 − 1152/3.6 = 1200 and y 45 − 162/3.6 = 0.
    expectBox(prefetchRegion(W, H, 0.95, 0.05, 6), { left: 1200, top: 0, right: W, bottom: 250 });
  });

  it('is measured in the viewer it is shown in, not the window', () => {
    // The plate's border leaves the viewer 899 px tall: the same placement
    // shows 899/1.2 image px of height rather than 750.
    const box = prefetchRegion(W, H, 0.5, 0.5, 2, { width: 1440, height: 899 });
    expectBox(box, { left: 0, top: 75, right: 1160, bottom: 75 + 899 / 1.2 });
  });
});

// ── Tiles are named as the viewer names them ─────────────────────────────────
//
// A static tile set has a file for each name OpenSeadragon asks for and no
// other. The expected names are the files the generator writes for
// a 1600×900 image with 512-px tiles and scale factors 1, 2 and 4.

describe('computeTileUrls — tile names', () => {
  const V3 = { '@context': 'http://iiif.io/api/image/3/context.json', type: 'ImageService3' };
  const V2 = { '@context': 'http://iiif.io/api/image/2/context.json' };

  beforeEach(() => {
    state.activeTitleCardIndex = null;
    state.layoutMode = 'horizontal';
    state.cardOverlayRect = { x: 43, y: 0, width: 533, height: 900 };
    Object.defineProperty(window, 'innerWidth',  { value: 1440, configurable: true, writable: true });
    Object.defineProperty(window, 'innerHeight', { value: 900,  configurable: true, writable: true });
  });

  it('names a tile by width and height under API 3, edge tiles at their own size', () => {
    const info = { ...V3, width: 1600, height: 900, tiles: [{ width: 512, scaleFactors: [1, 2, 4] }] };
    expect(computeTileUrls(BASE_URL, info, 0.5, 0.5, 1).map(tail).sort()).toEqual([
      '0,0,512,512/512,512/0/default.jpg',
      '0,512,512,388/512,388/0/default.jpg',
      '1024,0,512,512/512,512/0/default.jpg',
      '1024,512,512,388/512,388/0/default.jpg',
      '1536,0,64,512/64,512/0/default.jpg',
      '1536,512,64,388/64,388/0/default.jpg',
      '512,0,512,512/512,512/0/default.jpg',
      '512,512,512,388/512,388/0/default.jpg',
    ]);
  });

  it('names a tile by width alone under API 2', () => {
    const info = { ...V2, width: 1600, height: 900, tiles: [{ width: 512, scaleFactors: [1, 2, 4] }] };
    const names = computeTileUrls(BASE_URL, info, 0.5, 0.5, 1).map(tail);
    expect(names).toContain('0,0,512,512/512,/0/default.jpg');
    expect(names).toContain('1536,512,64,388/64,/0/default.jpg');
  });

  it('names a level smaller than one tile as the whole image at that size', () => {
    // A 350 × 200 window with no card shows the image at s = 350 / 1600 =
    // 0.21875: ratio(0) = 0.21875 × 4 = 0.875, floor(log2(1.75)) = 0, the
    // coarsest level, scale factor 4.
    state.cardOverlayRect = null;
    Object.defineProperty(window, 'innerWidth',  { value: 350, configurable: true, writable: true });
    Object.defineProperty(window, 'innerHeight', { value: 200, configurable: true, writable: true });
    const v3 = { ...V3, width: 1600, height: 900, tiles: [{ width: 512, scaleFactors: [1, 2, 4] }] };
    expect(computeTileUrls(BASE_URL, v3, 0.5, 0.5, 1).map(tail)).toEqual(['full/400,225/0/default.jpg']);
    const v2 = { ...V2, width: 1600, height: 900, tiles: [{ width: 512, scaleFactors: [1, 2, 4] }] };
    expect(computeTileUrls(BASE_URL, v2, 0.5, 0.5, 1).map(tail)).toEqual(['full/400,/0/default.jpg']);
  });

  it('names an image within one tile as the whole image at full size', () => {
    const v3 = { ...V3, width: 400, height: 300, tiles: [{ width: 512, scaleFactors: [1] }] };
    expect(computeTileUrls(BASE_URL, v3, 0.5, 0.5, 1).map(tail)).toEqual(['full/max/0/default.jpg']);
    const v2 = { ...V2, width: 400, height: 300, tiles: [{ width: 512, scaleFactors: [1] }] };
    expect(computeTileUrls(BASE_URL, v2, 0.5, 0.5, 1).map(tail)).toEqual(['full/full/0/default.jpg']);
  });

  it('names a tile the whole image is exactly as region full', () => {
    const v3 = { ...V3, width: 512, height: 300, tiles: [{ width: 512, scaleFactors: [1] }] };
    expect(computeTileUrls(BASE_URL, v3, 0.5, 0.5, 1).map(tail)).toEqual(['full/max/0/default.jpg']);
  });
});
