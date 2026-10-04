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
 * @version v1.8.0
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  computeZIndexPlan,
  setCardProgress,
  activateCard,
  initCardPool,
  reconcilePlatesForJump,
} from '../../assets/js/telar-story/card-pool.js';
import { state } from '../../assets/js/telar-story/state.js';
import {
  deactivateVideoCard, updateVideoClip,
} from '../../assets/js/telar-story/video-card.js';
import { VideoPlate } from '../../assets/js/telar-story/plates/video-plate.js';
import { AudioPlate } from '../../assets/js/telar-story/plates/audio-plate.js';
import { IiifPlate } from '../../assets/js/telar-story/plates/iiif-plate.js';
import { makePlate } from './iiif-plate-helpers.js';

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
    card.dataset.stepIndex = '0';
    card.dataset.object = 'obj-a';
    card.dataset.runPosition = '0';
    state.textCards = { 0: card };
  }

  it('re-adds is-active to the scene plate that a jump had hidden', () => {
    const plate = makePlate();  // no is-active: a jump hid it
    wireStep0(plate);

    expect(plate.container.classList.contains('is-active')).toBe(false);
    activateCard(0, 'forward'); // same-object jump after navigateToStep hid plates
    expect(plate.container.classList.contains('is-active')).toBe(true);
    expect(plate.container.style.transform).toMatch(/translateY\(0\)/);
  });

  it('leaves an already-active plate untouched (idempotent during normal scroll)', () => {
    const plate = makePlate();
    plate.container.classList.add('is-active');
    wireStep0(plate);

    activateCard(0, 'forward');
    expect(plate.container.classList.contains('is-active')).toBe(true);
  });
});

// ── A run starts where a scene starts ────────────────────────────────────────
//
// computeCardTop centres the first card of a run and settles each later card
// peekHeight lower. That contract holds only if the run counter restarts when
// the run does. A story that returns to an object starts a new scene there, so
// keying the counter by object instead carried the count across the gap and
// left the returning card peekHeight lower for every earlier appearance,
// compounding on each return.
//
// Invisible on default settings — card_peek_height defaults to 1 — and plainly
// visible on a site that raises it, which is why it wants a test rather than an
// eye.

describe('initCardPool — a run starts where its scene starts', () => {
  beforeEach(() => {
    resetPoolState();
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation(REDUCED_MOTION));
    // The viewer wrapper wants the vendored global and fetches before using it;
    // a fetch that never settles leaves it suspended, which is enough for the
    // build phase this asserts on.
    vi.stubGlobal('OpenSeadragon', vi.fn());
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
    resetPoolState();
  });

  // A A B A A after the intro — the reader leaves object A and comes back
  const steps = [
    { step: '1', object: 'A', question: 'q', answer: 'a' },
    { step: '2', object: 'A', question: 'q', answer: 'a' },
    { step: '3', object: 'B', question: 'q', answer: 'a' },
    { step: '4', object: 'A', question: 'q', answer: 'a' },
    { step: '5', object: 'A', question: 'q', answer: 'a' },
  ];

  it('restarts the run position when the story returns to an object', () => {
    buildStory(steps);

    const runPositions = Object.keys(state.textCards)
      .map(Number)
      .sort((a, b) => a - b)
      .map((i) => Number(state.textCards[i].dataset.runPosition));

    // not [0, 1, 0, 2, 3], which is what a per-object counter produces
    expect(runPositions).toEqual([0, 1, 0, 0, 1]);
  });

  it('gives every card that begins a scene run position zero', () => {
    buildStory(steps);

    for (const [key, card] of Object.entries(state.textCards)) {
      const stepIndex = Number(key);
      const beginsScene =
        state.sceneFirstStep[state.stepToScene[stepIndex]] === stepIndex;
      if (beginsScene) {
        expect(Number(card.dataset.runPosition),
               `step ${stepIndex} begins its run`).toBe(0);
      }
    }
  });
});

// ── Built card content: escaped question, rendered answer ───────────────────
// The question is plain text and both JS builders escape it; the answer is
// the HTML the build rendered, which both insert as the server-rendered step
// prints it. Runs the real initCardPool build phase in jsdom: title cards
// exercise _buildTitleCardContent (the live path), and omitting the
// .step-data markup forces the clone miss that exercises buildTextCardContent.

describe('initCardPool — built card content', () => {
  const HTMLY = '<b onmouseover="x()">Coleccion</b> & "quotes"';
  const ANSWER = '<p>One <em>rendered</em> answer.</p>\n<p>Two &ldquo;paragraphs&rdquo;.</p>';

  beforeEach(() => {
    document.body.innerHTML = '<div class="card-stack"></div>';
    state.objectsIndex = {};
    state.viewerPlates = {};
    state.textCards = {};
  });

  afterEach(() => {
    document.body.innerHTML = '';
    state.viewerPlates = {};
    state.textCards = {};
    state.titleCards = {};
  });

  it('escapes the question and inserts the rendered answer in title cards (live path)', () => {
    initCardPool({ steps: [{ step: '1', object: '', question: HTMLY, answer: ANSWER }] }, {});
    const heading = document.querySelector('.title-card .title-card-heading');
    const body = document.querySelector('.title-card .title-card-body');
    expect(heading).not.toBeNull();
    expect(heading.textContent).toBe(HTMLY);
    expect(heading.querySelector('b')).toBeNull();
    expect(body.tagName).toBe('DIV');
    expect(body.querySelectorAll('p')).toHaveLength(2);
    expect(body.querySelector('em').textContent).toBe('rendered');
    expect(body.textContent).toBe('One rendered answer.\nTwo \u201cparagraphs\u201d.');
  });

  it('escapes the question and inserts the rendered answer in the fallback text-card builder (clone miss)', () => {
    // Leading title step keeps scene 0 plate-free, so initCardPool's IIIF
    // preload tail (which needs OpenSeadragon) never runs in jsdom.
    initCardPool({ steps: [
      { step: '1', object: '', question: 'intro', answer: '' },
      { step: '2', object: 'obj-a', question: HTMLY, answer: ANSWER },
    ] }, {});
    const q = document.querySelector('.text-card .step-question');
    const a = document.querySelector('.text-card .step-answer');
    expect(q).not.toBeNull();
    expect(q.textContent).toBe(HTMLY);
    expect(q.querySelector('b')).toBeNull();
    expect(a.querySelectorAll('p')).toHaveLength(2);
    expect(a.querySelector('em').textContent).toBe('rendered');
  });

  it('builds no title card body for an empty answer', () => {
    initCardPool({ steps: [{ step: '1', object: '', question: 'Q', answer: '' }] }, {});
    expect(document.querySelector('.title-card .title-card-body')).toBeNull();
  });
});

// ── Re-initialisation ────────────────────────────────────────────────────────

describe('initCardPool — called twice', () => {
  let frames;
  let fonts;
  let passes;

  beforeEach(() => {
    document.body.innerHTML = '<div class="card-stack"></div>';
    state.objectsIndex = {};
    state.viewerPlates = {};
    state.textCards = {};
    frames = [];
    vi.stubGlobal('requestAnimationFrame', (cb) => { frames.push(cb); return frames.length; });
    fonts = new EventTarget();
    fonts.ready = new Promise(() => {});
    Object.defineProperty(document, 'fonts', { configurable: true, value: fonts });
    const story = { steps: [
      { step: '1', object: '', question: 'intro', answer: '' },
      { step: '2', object: 'obj-a', question: 'q', answer: 'a' },
    ] };
    initCardPool(story, {});
    document.body.innerHTML = '<div class="card-stack"></div>';
    initCardPool(story, {});
    frames = [];
    passes = vi.spyOn(performance, 'mark');
    passes.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    delete document.fonts;
    document.body.innerHTML = '';
    state.viewerPlates = {};
    state.textCards = {};
    state.titleCards = {};
  });

  const geometryPasses = () => passes.mock.calls
    .filter(([name]) => name === 'telar-card-geometry-start').length;
  const flush = () => { const run = frames; frames = []; for (const cb of run) cb(); };

  it('runs one geometry pass for the embed banner', () => {
    window.dispatchEvent(new Event('telar:embed-banner'));
    flush();
    expect(geometryPasses()).toBe(1);
  });

  it('runs one geometry pass for a font that finishes loading', () => {
    fonts.dispatchEvent(new Event('loadingdone'));
    flush();
    expect(geometryPasses()).toBe(1);
  });

  it('runs one geometry pass for a settled resize', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    try {
      window.dispatchEvent(new Event('resize'));
      vi.advanceTimersByTime(200);
    } finally {
      vi.useRealTimers();
    }
    expect(geometryPasses()).toBe(1);
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

    expect(state.viewerPlates[1]).toBeInstanceOf(VideoPlate);
    const plate = state.viewerPlates[1].container;
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

    expect(state.viewerPlates[1]).toBeInstanceOf(VideoPlate);
    const plate = state.viewerPlates[1].container;
    expect(plate.dataset.cardType).toBe('vimeo');
    expect(plate.dataset.clipStart).toBe('5');
  });

  it('marks an audio scene as an audio plate', () => {
    window.audioObjects = { [TEST_AUDIO_ID]: 'mp3' };
    buildStory([{ step: '1', object: TEST_AUDIO_ID, question: 'Q', answer: 'A' }]);

    expect(state.viewerPlates[1]).toBeInstanceOf(AudioPlate);
    const plate = state.viewerPlates[1].container;
    expect(plate.classList.contains('audio-plate')).toBe(true);
    expect(plate.dataset.cardType).toBe('audio');
  });

  it('leaves an image scene with neither media class', () => {
    buildStory([{ step: '1', object: 'obj-a', question: 'Q', answer: 'A', clip_start: '12' }]);

    expect(state.viewerPlates[1]).toBeInstanceOf(IiifPlate);
    const plate = state.viewerPlates[1].container;
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
    expect(state.viewerPlates[1].container.getAttribute('aria-label')).toBe('The full sheet');

    activateCard(2, 'forward');
    expect(state.viewerPlates[1].container.getAttribute('aria-label')).toBe('The cartouche');

    state.scrollDriven = false;
  });

  it('falls back to the object title when the step carries no alt text', () => {
    state.objectsIndex = { 'obj-a': { title: 'Mapa de la provincia' } };
    buildStory([{ step: '1', object: 'obj-a', question: 'Q1', answer: 'A1' }]);
    state.currentObjectRun = { objectId: 'obj-a', runPosition: 0 };
    state.scrollDriven = true;

    activateCard(1, 'forward');
    expect(state.viewerPlates[1].container.getAttribute('aria-label')).toBe('Mapa de la provincia');

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
    const plate = state.viewerPlates[1];
    plate.osdWrapper = {};   // built, so the step frames it rather than rebuilding
    plate.isReady = false;   // and not ready, so the framing is queued
    state.currentObjectRun = { objectId: 'obj-a', runPosition: 0 };

    activateCard(2, 'forward');

    expect(plate.pendingZoom).toEqual({ x: 0.4, y: 0.6, zoom: 4, snap: false });
  });

  it('queues the whole-object framing for a step that authored none', () => {
    buildStory([
      { step: '1', object: 'obj-a', question: 'Q1', answer: 'A1' },
      { step: '2', object: 'obj-a', question: 'Q2', answer: 'A2' },
    ]);
    const plate = state.viewerPlates[1];
    plate.osdWrapper = {};
    plate.isReady = false;
    state.currentObjectRun = { objectId: 'obj-a', runPosition: 0 };

    activateCard(2, 'forward');

    // The whole object is a framing like any other: image centre, zoom 1, which
    // the focal target resolves to the whole image fit in the uncovered region.
    expect(plate.pendingZoom).toEqual({ x: 0.5, y: 0.5, zoom: 1, snap: false });
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
    expect(state.viewerPlates[2].container.style.transform).toBe('translateY(75%)');

    setCardProgress(1, 0.75);
    expect(state.viewerPlates[2].container.style.transform).toBe('translateY(25%)');
  });

  it('takes the current plate away upward when the next step is a title card', () => {
    buildStory([
      { step: '1', object: 'obj-a', question: 'Q1', answer: 'A1' },
      { step: '2', object: '', question: 'Interlude', answer: '' },
    ]);
    document.querySelector('.card-stack').classList.add('is-scrubbing');

    setCardProgress(1, 0.25);
    expect(state.viewerPlates[1].container.style.transform).toBe('translateY(-25%)');
  });

  it('holds the standing plate at rest while both steps share an object', () => {
    buildStory([
      { step: '1', object: 'obj-a', question: 'Q1', answer: 'A1' },
      { step: '2', object: 'obj-a', question: 'Q2', answer: 'A2' },
    ]);
    document.querySelector('.card-stack').classList.add('is-scrubbing');

    setCardProgress(1, 0.25);
    expect(state.viewerPlates[1].container.style.transform).toBe('translateY(0%)');
  });

  it('states the plate behind a section card as clear of the top', () => {
    // The position rests on the section card, so the pair in play is the
    // section and the object after it. Nothing in that pair is the plate the
    // section card is covering, which is the one the reader sees again on the
    // way back — and which a scrub that stopped short leaves part way up.
    buildStory([
      { step: '1', object: 'obj-a', question: 'Q1', answer: 'A1' },
      { step: '2', object: '',      question: 'Interlude', answer: '' },
      { step: '3', object: 'obj-b', question: 'Q3', answer: 'A3' },
    ]);
    document.querySelector('.card-stack').classList.add('is-scrubbing');
    state.viewerPlates[1].container.style.transform = 'translateY(-34%)';

    setCardProgress(2, 0);
    expect(state.viewerPlates[1].container.style.transform).toBe('translateY(-100%)');
    expect(state.viewerPlates[3].container.style.transform).toBe('translateY(100%)');
  });

  it('brings the next plate up out of a section card', () => {
    buildStory([
      { step: '1', object: 'obj-a', question: 'Q1', answer: 'A1' },
      { step: '2', object: 'obj-b', question: 'Q2', answer: 'A2' },
    ]);
    document.querySelector('.card-stack').classList.add('is-scrubbing');

    // Step 0 is the fixture's own section card, so the position is leaving one.
    setCardProgress(0, 0.25);
    expect(state.viewerPlates[1].container.style.transform).toBe('translateY(75%)');
  });

  it('holds the plates below while the intro gives way to a section card', () => {
    buildStory([
      { step: '1', object: 'obj-a', question: 'Q1', answer: 'A1' },
    ]);
    document.querySelector('.card-stack').classList.add('is-scrubbing');

    // Nothing rises over the intro but the section card itself, which is a
    // card and not a plate; the first object's plate waits a viewport down.
    setCardProgress(-1, 0.25);
    expect(state.viewerPlates[1].container.style.transform).toBe('translateY(100%)');
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

    expect(vi.mocked(deactivateVideoCard)).toHaveBeenCalledWith(state.viewerPlates[1].container);
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
      state.viewerPlates[1].container, 90, 120, true);
  });
});

describe('card pool — the viewer pool stays inside its cap', () => {
  let savedCap;

  /** The plates holding a live viewer, which is what the cap counts. */
  const loadedViewers = () => Object.values(state.viewerPlates)
    .filter(plate => plate instanceof IiifPlate && plate.osdWrapper);

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

    expect(loadedViewers().length).toBe(2);
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
    const scenes = loadedViewers().map(plate => plate.sceneIndex).sort((a, b) => a - b);
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
    expect(state.viewerPlates[0].container.style.zIndex).toBe(expected);
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

  it('keeps the shared plate on screen and sends it the step framing', () => {
    buildStory([
      { step: '1', object: 'obj-a', question: 'Q1', answer: 'A1' },
      { step: '2', object: 'obj-a', question: 'Q2', answer: 'A2',
        x: '0.4', y: '0.6', zoom: '4' },
    ]);
    const viewerCard = state.viewerPlates[1];
    viewerCard.osdWrapper = {};
    viewerCard.isReady = false;
    const plate = viewerCard.container;
    state.currentObjectRun = { objectId: 'obj-a', runPosition: 0 };

    activateCard(2, 'forward');

    expect(plate.classList.contains('is-active')).toBe(true);
    expect(plate.style.transform).toBe('translateY(0)');
    // The plate stays put, and the step's framing still reaches the viewer —
    // queued here because this viewer card is not ready yet.
    expect(viewerCard.pendingZoom).toEqual({ x: 0.4, y: 0.6, zoom: 4, snap: true });
  });
});

// ── reconcilePlatesForJump ───────────────────────────────────────────────────
//
// A jump used to close the plates it crossed by removing `is-active`. That
// class carries `translateY(0)`, and so does the inline style every path
// writes when it opens a plate — so removing the class left the inline
// transform holding the plate open, and the plate stayed exactly where the
// walk had put it. Invisible wherever the target's plate covered it, and
// across the whole screen where it did not.

describe('reconcilePlatesForJump — closing the plates a jump crossed', () => {
  // A plate as _createViewerPlates builds one: an instance of the class its
  // card type selects, over an element carrying that type. What decides
  // whether a plate holds a player is the class of the instance, so a fixture
  // that is only a styled element is a plate the framework never produces.
  const CARD_TYPE_FOR = new Map([
    [AudioPlate, 'audio'],
    [VideoPlate, 'youtube'],
    [IiifPlate,  'iiif'],
  ]);

  function plate(PlateClass = IiifPlate) {
    const el = document.createElement('div');
    el.className = 'viewer-plate';
    el.dataset.cardType = CARD_TYPE_FOR.get(PlateClass);
    const p = new PlateClass(el, 'obj', 0, 0);
    el.classList.add('is-active');
    el.style.transform = 'translateY(0)';   // as a walk onto it left it
    return p;
  }

  beforeEach(() => {
    state.stepToScene = { 0: 0, 1: 1, 2: 2 };
    state.viewerPlates = {};
  });

  it('sends a plate the reader walked onto off screen, not just inactive', () => {
    const crossed = plate();
    state.viewerPlates = { 0: crossed, 1: plate() };

    reconcilePlatesForJump(1);

    expect(crossed.container.style.transform).toBe('translateY(100%)');
    expect(crossed.container.classList.contains('is-active')).toBe(false);
  });

  it('leaves the target step own plate alone for activateCard to place', () => {
    const target = plate();
    state.viewerPlates = { 0: plate(), 1: target };

    reconcilePlatesForJump(1);

    expect(target.container.style.transform).toBe('translateY(0)');
    expect(target.container.classList.contains('is-active')).toBe(true);
  });

  it('closes an audio plate the jump goes back across', () => {
    // The case this was filed for: step 9 is audio, the reader jumps to step 5.
    const audio = plate(AudioPlate);
    state.stepToScene = { 4: 1, 8: 2 };
    state.viewerPlates = { 1: plate(), 2: audio };

    reconcilePlatesForJump(4);

    expect(audio.container.style.transform).toBe('translateY(100%)');
  });

  it('stands the media down, as the walk it stands in for does', () => {
    const video = plate(VideoPlate);
    state.stepToScene = { 0: 0, 1: 1 };
    state.viewerPlates = { 0: plate(), 1: video };
    deactivateVideoCard.mockClear();

    reconcilePlatesForJump(0);

    expect(deactivateVideoCard).toHaveBeenCalledWith(video.container);
  });

  it('puts the transitions back, so the next move animates', () => {
    const crossed = plate();
    state.viewerPlates = { 0: crossed, 1: plate() };

    reconcilePlatesForJump(1);

    expect(crossed.container.style.transition).toBe('');
  });
});

// ── The side card's placement and its scroll ─────────────────────────────────
// The geometry itself is card-fit.test.js's; here, only that an activated
// card arrives at its question.

describe('card pool — an activated card arrives at its top', () => {
  beforeEach(() => {
    resetPoolState();
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation(REDUCED_MOTION));
    vi.stubGlobal('OpenSeadragon', vi.fn());
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
    resetPoolState();
  });

  const steps = [
    { step: '1', object: 'A', question: 'q', answer: 'a' },
    { step: '2', object: 'A', question: 'q', answer: 'a' },
  ];

  it('puts a card back at its question when it is activated', () => {
    buildStory(steps);
    const card = state.textCards[1];
    card.scrollTop = 240;
    state.currentObjectRun = { objectId: 'A', runPosition: 0 };

    activateCard(1, 'forward');

    expect(card.scrollTop).toBe(0);
  });
});
