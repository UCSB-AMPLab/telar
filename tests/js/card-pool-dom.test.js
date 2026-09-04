/**
 * Tests for Telar Story – Card Pool: DOM-driven behaviour
 *
 * The jsdom-safe slice of the module: activateCard guards, initCardPool's
 * build phase (card content escaping, media plate marking), the plate
 * aria-label, the pending framing a not-ready viewer carries, the
 * scrub-time plate handoff, the video-player handoff, the viewer pool cap,
 * and the mode-flip plate re-seat. Paths that need OpenSeadragon or a real
 * browser (preloadAhead, IIIF plate init) are covered by the e2e suites
 * instead. The pure helpers and geometry (z-index banding, messiness, peek
 * positioning, scene maps, tile URLs) live in the sibling file,
 * card-pool.test.js.
 *
 * @version v1.7.0
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  computeZIndexPlan,
  setCardProgress,
  activateCard,
  initCardPool,
} from '../../assets/js/telar-story/card-pool.js';
import { state } from '../../assets/js/telar-story/state.js';
import {
  deactivateVideoCard, updateVideoClip,
} from '../../assets/js/telar-story/video-card.js';

// Video-card is spied, not replaced: every export keeps its real body, and the
// two the card pool routes plate handovers through are wrapped so a test can
// assert the routing. A plate with no player wrapper reaches the same DOM
// whichever branch takes it, so the call is the only evidence there is.
vi.mock('../../assets/js/telar-story/video-card.js', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    deactivateVideoCard: vi.fn(actual.deactivateVideoCard),
    updateVideoClip: vi.fn(actual.updateVideoClip),
  };
});

// ── setCardProgress — title card fallback ────────────────────────────────────
//
// Full DOM integration (is-scrubbing card-stack + private _stepsData) cannot be
// unit-tested here — setCardProgress relies on internal module state that is only
// populated by initCardPool. The title card fallback is verified manually in
// browser testing. This block confirms the export exists and the function
// does not throw when state has no text card at the target index.

describe('setCardProgress — title card fallback', () => {
  beforeEach(() => {
    state.textCards  = {};
    state.titleCards = {};
    state.cardRegistry = [];
  });

  it('is exported and does not throw when progress < 0.001', () => {
    // Early return at progress guard — safe even with empty state
    expect(() => setCardProgress(0, 0)).not.toThrow();
  });

  it('does not throw when state.textCards is empty and state.titleCards has an entry', () => {
    const mockDiv = document.createElement('div');
    state.titleCards = { 1: mockDiv };
    // Will return early at cardStack guard (no .card-stack.is-scrubbing in JSDOM)
    // but must not throw — confirms the title card fallback path is reachable
    expect(() => setCardProgress(0, 0.5)).not.toThrow();
  });
});

// ── cardOverlayRect population ───────────────────────────────────────────────
//
// Tests for the three-branch rect-write logic in _activateTextCard and the
// null-clear in _activateTitleCardStep. The private functions are exercised
// through the exported activateCard entry point (the same activation dispatch
// used in production). Both tests rely on minimal mock state that avoids the
// need for a full initCardPool call.

describe('cardOverlayRect — rect populated in reduced-motion synchronous branch', () => {
  const MOCK_RECT = { top: 100, left: 10, width: 300, height: 400, bottom: 500, right: 310 };

  beforeEach(() => {
    // Reset cardOverlayRect to a known non-null value so we can prove it was written
    state.cardOverlayRect = null;

    // Stub matchMedia — jsdom does not implement it. Return matches: true for
    // prefers-reduced-motion so _activateTextCard takes the synchronous branch.
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query) => ({
      matches: query === '(prefers-reduced-motion: reduce)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })));

    // No title card at index 0 — ensures activateCard routes to text-card path
    state.titleCards = {};

    // Minimal scene maps so preloadAhead returns early
    state.stepToScene  = { 0: 0 };
    state.totalScenes  = 1;
    state.sceneFirstStep = { 0: 0 };

    // No active viewer plates (text-only path skips viewer init)
    state.viewerPlates = {};
    state.viewerCards  = [];

    // Same-object run so activateCard takes the text-only branch (no needsNewViewer)
    state.currentObjectRun = { objectId: 'obj-a', runPosition: 0 };
    state.activeTitleCardIndex = null;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('writes state.cardOverlayRect with the mocked getBoundingClientRect value (synchronous)', () => {
    const mockCard = document.createElement('div');
    // Mock getBoundingClientRect to return a known rect
    mockCard.getBoundingClientRect = vi.fn().mockReturnValue(MOCK_RECT);

    // Wire minimal card-pool state: text card + registry entry for step 0, same object as currentObjectRun
    state.textCards = { 0: mockCard };
    state.cardRegistry = [{ stepIndex: 0, objectId: 'obj-a', runPosition: 0, element: mockCard }];

    activateCard(0, 'forward');

    // Synchronous branch: rect is set immediately (no transitionend needed)
    expect(state.cardOverlayRect).toBe(MOCK_RECT);
    expect(mockCard.getBoundingClientRect).toHaveBeenCalledTimes(1);
  });
});

describe('activateCard — same-object jump re-shows a hidden viewer plate', () => {
  beforeEach(() => {
    // Reduced-motion stub so _activateTextCard takes the synchronous branch.
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query) => ({
      matches: query === '(prefers-reduced-motion: reduce)',
      media: query, onchange: null,
      addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })));
    state.titleCards = {};
    state.stepToScene = { 0: 0 };
    state.totalScenes = 1;
    state.sceneFirstStep = { 0: 0 };
    state.viewerCards = [];
    state.activeTitleCardIndex = null;
    // Same object as the target step → activateCard takes the text-only branch.
    state.currentObjectRun = { objectId: 'obj-a', runPosition: 0 };
    // scroll-driven so the IIIF animate path is skipped, isolating the
    // is-active behaviour under test.
    state.scrollDriven = true;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    state.scrollDriven = false;
  });

  function wireStep0(plate) {
    state.viewerPlates = { 0: plate };
    const card = document.createElement('div');
    card.getBoundingClientRect = vi.fn().mockReturnValue(
      { top: 0, left: 0, width: 1, height: 1, bottom: 1, right: 1 });
    state.textCards = { 0: card };
    state.cardRegistry = [{ stepIndex: 0, objectId: 'obj-a', runPosition: 0, element: card }];
  }

  it('re-adds is-active to the scene plate that a jump had hidden', () => {
    const plate = document.createElement('div'); // plain IIIF plate, no is-active
    wireStep0(plate);

    expect(plate.classList.contains('is-active')).toBe(false);
    activateCard(0, 'forward'); // same-object jump after navigateToStep hid plates
    expect(plate.classList.contains('is-active')).toBe(true);
    expect(plate.style.transform).toMatch(/translateY\(0\)/);
  });

  it('leaves an already-active plate untouched (idempotent during normal scroll)', () => {
    const plate = document.createElement('div');
    plate.classList.add('is-active');
    wireStep0(plate);

    activateCard(0, 'forward');
    expect(plate.classList.contains('is-active')).toBe(true);
  });
});

describe('cardOverlayRect — null on title-card activation', () => {
  beforeEach(() => {
    // Seed a non-null value to confirm it is cleared
    state.cardOverlayRect = { top: 99, left: 5, width: 100, height: 200, bottom: 299, right: 105 };

    // Minimal scene maps
    state.stepToScene   = { 0: 0 };
    state.totalScenes   = 1;
    state.sceneFirstStep = { 0: 0 };

    state.viewerPlates  = {};
    state.viewerCards   = [];
    state.cardRegistry  = [];
    state.textCards     = {};
    state.activeTitleCardIndex = null;
  });

  it('clears state.cardOverlayRect to null when a title card is activated', () => {
    const titleCardEl = document.createElement('div');
    state.titleCards = { 0: titleCardEl };

    activateCard(0, 'forward');

    expect(state.cardOverlayRect).toBeNull();
  });
});

// ── Built card content escapes author text ───────────────────────────────────
// question/answer are documented as plain text; both JS builders must escape
// them identically. Runs the real initCardPool build phase in jsdom: title
// cards exercise _buildTitleCardContent (the live path), and omitting the
// .step-data markup forces the clone miss that exercises buildTextCardContent.

describe('initCardPool — built card content escapes author text', () => {
  const HTMLY = '<b onmouseover="x()">Coleccion</b> & "quotes"';

  beforeEach(() => {
    document.body.innerHTML = '<div class="card-stack"></div>';
    state.objectsIndex = {};
    state.viewerPlates = {};
    state.textCards = {};
    state.cardRegistry = [];
  });

  afterEach(() => {
    document.body.innerHTML = '';
    state.viewerPlates = {};
    state.textCards = {};
    state.cardRegistry = [];
    state.titleCards = {};
  });

  it('escapes question and answer in title cards (live path)', () => {
    initCardPool({ steps: [{ step: '1', object: '', question: HTMLY, answer: HTMLY }] }, {});
    const heading = document.querySelector('.title-card .title-card-heading');
    const body = document.querySelector('.title-card .title-card-body');
    expect(heading).not.toBeNull();
    expect(heading.textContent).toBe(HTMLY);
    expect(heading.querySelector('b')).toBeNull();
    expect(body.textContent).toBe(HTMLY);
    expect(body.querySelector('b')).toBeNull();
  });

  it('escapes question and answer in the fallback text-card builder (clone miss)', () => {
    // Leading title step keeps scene 0 plate-free, so initCardPool's IIIF
    // preload tail (which needs OpenSeadragon) never runs in jsdom.
    initCardPool({ steps: [
      { step: '1', object: '', question: 'intro', answer: '' },
      { step: '2', object: 'obj-a', question: HTMLY, answer: HTMLY },
    ] }, {});
    const q = document.querySelector('.text-card .step-question');
    const a = document.querySelector('.text-card .step-answer');
    expect(q).not.toBeNull();
    expect(q.textContent).toBe(HTMLY);
    expect(q.querySelector('b')).toBeNull();
    expect(a.textContent).toBe(HTMLY);
    expect(a.querySelector('b')).toBeNull();
  });
});

// ── Media plates, labels, pending framing, and the scrubbed handoff ──────────
//
// Four behaviours that a story built from image objects alone never reaches,
// and that a snapshot of tag/class/style/dataset would not record even if it
// did: the class and clip window a player-backed plate is built with, the
// aria-label the plate carries for the step on screen, the framing a viewer
// that is still loading holds until it is ready, and the plate movement a
// scrub drives between two objects.
//
// Fixtures are this repository's own objects: the YouTube and Vimeo entries
// in _data/objects.json, and the cylinder recording in _data/audio_objects.json.

const TEST_VIDEO_URL = 'https://www.youtube.com/watch?v=jNQXAC9IVRw';
const TEST_VIMEO_URL = 'https://vimeo.com/1139902893/e450fba07a';
const TEST_AUDIO_ID  = 'cusb-cyl11337d';

/** A story whose first step is a title card, so scene 0 owns no plate. */
function buildStory(steps, config) {
  document.body.innerHTML = '<div class="card-stack"></div>';
  initCardPool({ steps: [{ step: '0', object: '', question: 'intro', answer: '' },
                         ...steps] }, config || {});
}

function resetPoolState() {
  state.objectsIndex = {};
  state.viewerPlates = {};
  state.viewerCards = [];
  state.textCards = {};
  state.titleCards = {};
  state.cardRegistry = [];
  state.activeTitleCardIndex = null;
  state.currentObjectRun = { objectId: null, runPosition: 0 };
  state.cardOverlayRect = null;
  delete window.audioObjects;
}

const REDUCED_MOTION = (query) => ({
  matches: query === '(prefers-reduced-motion: reduce)',
  media: query, onchange: null,
  addListener: vi.fn(), removeListener: vi.fn(),
  addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
});

describe('initCardPool — media plates carry their class and clip window', () => {
  beforeEach(() => {
    resetPoolState();
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation(REDUCED_MOTION));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
    resetPoolState();
  });

  it('marks a YouTube scene as a video plate and writes the scene clip window', () => {
    state.objectsIndex = { 'test-video': { source_url: TEST_VIDEO_URL, title: 'Test Video' } };
    buildStory([{ step: '1', object: 'test-video', question: 'Q', answer: 'A',
                  clip_start: '12', clip_end: '34', loop: 'true' }]);

    const plate = state.viewerPlates[1];
    expect(plate.classList.contains('video-plate')).toBe(true);
    expect(plate.dataset.cardType).toBe('youtube');
    expect(plate.dataset.clipStart).toBe('12');
    expect(plate.dataset.clipEnd).toBe('34');
    expect(plate.dataset.loop).toBe('true');
  });

  it('takes the clip window from the scene first step, not a later one', () => {
    state.objectsIndex = { 'test-vimeo': { source_url: TEST_VIMEO_URL, title: 'Test Vimeo' } };
    buildStory([
      { step: '1', object: 'test-vimeo', question: 'Q1', answer: 'A1', clip_start: '5' },
      { step: '2', object: 'test-vimeo', question: 'Q2', answer: 'A2', clip_start: '90' },
    ]);

    const plate = state.viewerPlates[1];
    expect(plate.dataset.cardType).toBe('vimeo');
    expect(plate.dataset.clipStart).toBe('5');
  });

  it('marks an audio scene as an audio plate', () => {
    window.audioObjects = { [TEST_AUDIO_ID]: 'mp3' };
    buildStory([{ step: '1', object: TEST_AUDIO_ID, question: 'Q', answer: 'A' }]);

    const plate = state.viewerPlates[1];
    expect(plate.classList.contains('audio-plate')).toBe(true);
    expect(plate.dataset.cardType).toBe('audio');
  });

  it('leaves an image scene with neither media class', () => {
    buildStory([{ step: '1', object: 'obj-a', question: 'Q', answer: 'A', clip_start: '12' }]);

    const plate = state.viewerPlates[1];
    expect(plate.classList.contains('video-plate')).toBe(false);
    expect(plate.classList.contains('audio-plate')).toBe(false);
    expect(plate.dataset.cardType).toBe('iiif');
    expect(plate.dataset.clipStart).toBeUndefined();
  });
});

describe('activateCard — the plate label follows the step', () => {
  beforeEach(() => {
    resetPoolState();
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation(REDUCED_MOTION));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
    resetPoolState();
  });

  it('rewrites the aria-label with each step own alt text', () => {
    buildStory([
      { step: '1', object: 'obj-a', question: 'Q1', answer: 'A1', alt_text: 'The full sheet' },
      { step: '2', object: 'obj-a', question: 'Q2', answer: 'A2', alt_text: 'The cartouche' },
    ]);
    // Already inside the object run, so activation stays on the text-only path.
    state.currentObjectRun = { objectId: 'obj-a', runPosition: 0 };
    state.scrollDriven = true;

    activateCard(1, 'forward');
    expect(state.viewerPlates[1].getAttribute('aria-label')).toBe('The full sheet');

    activateCard(2, 'forward');
    expect(state.viewerPlates[1].getAttribute('aria-label')).toBe('The cartouche');

    state.scrollDriven = false;
  });

  it('falls back to the object title when the step carries no alt text', () => {
    state.objectsIndex = { 'obj-a': { title: 'Mapa de la provincia' } };
    buildStory([{ step: '1', object: 'obj-a', question: 'Q1', answer: 'A1' }]);
    state.currentObjectRun = { objectId: 'obj-a', runPosition: 0 };
    state.scrollDriven = true;

    activateCard(1, 'forward');
    expect(state.viewerPlates[1].getAttribute('aria-label')).toBe('Mapa de la provincia');

    state.scrollDriven = false;
  });
});

describe('activateCard — framing waits on a viewer that is not ready', () => {
  beforeEach(() => {
    resetPoolState();
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation(REDUCED_MOTION));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
    resetPoolState();
    state.scrollDriven = false;
  });

  it('stores the step framing on the viewer card as a pending animation', () => {
    // Both steps are details of one object, so the pair is a pan within a
    // scene rather than a mode flip, which would build a plate instead.
    buildStory([
      { step: '1', object: 'obj-a', question: 'Q1', answer: 'A1',
        x: '0.2', y: '0.3', zoom: '2' },
      { step: '2', object: 'obj-a', question: 'Q2', answer: 'A2',
        x: '0.4', y: '0.6', zoom: '4' },
    ]);
    const viewerCard = { sceneIndex: 1, objectId: 'obj-a', element: state.viewerPlates[1],
                         isReady: false, pendingZoom: null };
    state.viewerCards = [viewerCard];
    state.currentObjectRun = { objectId: 'obj-a', runPosition: 0 };

    activateCard(2, 'forward');

    expect(viewerCard.pendingZoom).toEqual({ x: 0.4, y: 0.6, zoom: 4, snap: false });
  });

  it('leaves the viewer alone for a step that authored no framing', () => {
    buildStory([
      { step: '1', object: 'obj-a', question: 'Q1', answer: 'A1' },
      { step: '2', object: 'obj-a', question: 'Q2', answer: 'A2' },
    ]);
    const viewerCard = { sceneIndex: 1, objectId: 'obj-a', element: state.viewerPlates[1],
                         isReady: false, pendingZoom: null };
    state.viewerCards = [viewerCard];
    state.currentObjectRun = { objectId: 'obj-a', runPosition: 0 };

    activateCard(2, 'forward');

    expect(viewerCard.pendingZoom).toBeNull();
  });
});

describe('setCardProgress — the arriving plate slides with the scrub', () => {
  beforeEach(() => {
    resetPoolState();
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation(REDUCED_MOTION));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
    resetPoolState();
  });

  it('brings the next object plate up in proportion to progress', () => {
    buildStory([
      { step: '1', object: 'obj-a', question: 'Q1', answer: 'A1' },
      { step: '2', object: 'obj-b', question: 'Q2', answer: 'A2' },
    ]);
    document.querySelector('.card-stack').classList.add('is-scrubbing');

    setCardProgress(1, 0.25);
    expect(state.viewerPlates[2].style.transform).toBe('translateY(75%)');

    setCardProgress(1, 0.75);
    expect(state.viewerPlates[2].style.transform).toBe('translateY(25%)');
  });

  it('takes the current plate away upward when the next step is a title card', () => {
    buildStory([
      { step: '1', object: 'obj-a', question: 'Q1', answer: 'A1' },
      { step: '2', object: '', question: 'Interlude', answer: '' },
    ]);
    document.querySelector('.card-stack').classList.add('is-scrubbing');

    setCardProgress(1, 0.25);
    expect(state.viewerPlates[1].style.transform).toBe('translateY(-25%)');
  });

  it('moves no plate while both steps share an object', () => {
    buildStory([
      { step: '1', object: 'obj-a', question: 'Q1', answer: 'A1' },
      { step: '2', object: 'obj-a', question: 'Q2', answer: 'A2' },
    ]);
    document.querySelector('.card-stack').classList.add('is-scrubbing');
    state.viewerPlates[1].style.transform = 'translateY(0)';

    setCardProgress(1, 0.25);
    expect(state.viewerPlates[1].style.transform).toBe('translateY(0)');
  });
});

describe('card pool — a video plate is handed over through the video module', () => {
  beforeEach(() => {
    resetPoolState();
    vi.mocked(deactivateVideoCard).mockClear();
    vi.mocked(updateVideoClip).mockClear();
    state.objectsIndex = { 'test-video': { source_url: TEST_VIDEO_URL, title: 'Test Video' } };
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation(REDUCED_MOTION));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
    resetPoolState();
    state.scrollDriven = false;
  });

  it('stops the departing player when a title card covers its scene', () => {
    buildStory([
      { step: '1', object: 'test-video', question: 'Q1', answer: 'A1' },
      { step: '2', object: '', question: 'Interlude', answer: '' },
    ]);

    activateCard(2, 'forward');

    expect(vi.mocked(deactivateVideoCard)).toHaveBeenCalledWith(state.viewerPlates[1]);
  });

  it('re-clips the running player for a later step in the same scene', () => {
    buildStory([
      { step: '1', object: 'test-video', question: 'Q1', answer: 'A1',
        clip_start: '5', clip_end: '20' },
      { step: '2', object: 'test-video', question: 'Q2', answer: 'A2',
        clip_start: '90', clip_end: '120', loop: 'true' },
    ]);
    state.currentObjectRun = { objectId: 'test-video', runPosition: 0 };

    activateCard(2, 'forward');

    expect(vi.mocked(updateVideoClip)).toHaveBeenCalledWith(
      state.viewerPlates[1], 90, 120, true);
  });
});

describe('card pool — the viewer pool stays inside its cap', () => {
  let savedCap;

  beforeEach(() => {
    resetPoolState();
    savedCap = state.config.maxViewerCards;
    state.config.maxViewerCards = 2;
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation(REDUCED_MOTION));
    // The viewer wrapper needs the vendored global to exist, and fetches its
    // manifest before it touches it. A fetch that never settles leaves the
    // wrapper suspended there, so what runs is the synchronous tail: the
    // push onto the pool and the eviction that follows it.
    vi.stubGlobal('OpenSeadragon', vi.fn());
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
  });

  afterEach(() => {
    state.config.maxViewerCards = savedCap;
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
    resetPoolState();
  });

  it('keeps at most maxViewerCards viewers once preloading has warmed more scenes', () => {
    buildStory([
      { step: '1', object: 'obj-a', question: 'Q1', answer: 'A1' },
      { step: '2', object: 'obj-b', question: 'Q2', answer: 'A2' },
      { step: '3', object: 'obj-c', question: 'Q3', answer: 'A3' },
      { step: '4', object: 'obj-d', question: 'Q4', answer: 'A4' },
    ]);
    state.currentObjectRun = { objectId: 'obj-a', runPosition: 0 };
    state.scrollDriven = true;

    activateCard(1, 'forward');

    expect(state.viewerCards.length).toBe(2);
    state.scrollDriven = false;
  });

  it('drops the viewer farthest in scenes from the one just opened', () => {
    buildStory([
      { step: '1', object: 'obj-a', question: 'Q1', answer: 'A1' },
      { step: '2', object: 'obj-b', question: 'Q2', answer: 'A2' },
      { step: '3', object: 'obj-c', question: 'Q3', answer: 'A3' },
      { step: '4', object: 'obj-d', question: 'Q4', answer: 'A4' },
    ]);
    state.currentObjectRun = { objectId: 'obj-a', runPosition: 0 };
    state.scrollDriven = true;

    activateCard(1, 'forward');

    // Warming runs outward from the active scene, so the survivors are the
    // last two opened and the pool never holds a scene farther than those.
    const scenes = state.viewerCards.map(vc => vc.sceneIndex).sort((a, b) => a - b);
    expect(scenes).toEqual([3, 4]);
    state.scrollDriven = false;
  });
});

describe('initCardPool — the first scene player opens at its scene z-index', () => {
  beforeEach(() => {
    resetPoolState();
    state.objectsIndex = { 'test-video': { source_url: TEST_VIDEO_URL, title: 'Test Video' } };
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation(REDUCED_MOTION));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
    resetPoolState();
  });

  it('leaves the preloaded video plate at the z-index the scene plan gives it', () => {
    const steps = [
      { step: '1', object: 'test-video', question: 'Q1', answer: 'A1' },
      { step: '2', object: 'obj-b', question: 'Q2', answer: 'A2' },
    ];
    document.body.innerHTML = '<div class="card-stack"></div>';
    initCardPool({ steps }, {});

    const expected = String(computeZIndexPlan(steps).plateZ[0]);
    expect(state.viewerPlates[0].style.zIndex).toBe(expected);
  });
});

describe('activateCard — a mode flip on one object re-seats the plate it shares', () => {
  beforeEach(() => {
    resetPoolState();
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation(REDUCED_MOTION));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
    resetPoolState();
  });

  it('shows the shared plate rather than panning the viewer inside it', () => {
    buildStory([
      { step: '1', object: 'obj-a', question: 'Q1', answer: 'A1' },
      { step: '2', object: 'obj-a', question: 'Q2', answer: 'A2',
        x: '0.4', y: '0.6', zoom: '4' },
    ]);
    const plate = state.viewerPlates[1];
    const viewerCard = { sceneIndex: 1, objectId: 'obj-a', element: plate,
                         isReady: false, pendingZoom: null };
    state.viewerCards = [viewerCard];
    state.currentObjectRun = { objectId: 'obj-a', runPosition: 0 };

    activateCard(2, 'forward');

    expect(plate.classList.contains('is-active')).toBe(true);
    expect(plate.style.transform).toBe('translateY(0)');
    expect(viewerCard.pendingZoom).toBeNull();
  });
});
