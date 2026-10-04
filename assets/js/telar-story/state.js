/**
 * Telar Story – Centralised State
 *
 * This module holds the mutable state for the story page: every value that
 * changes at runtime as the user navigates steps, opens panels, switches
 * viewer objects, and so on. Mutable state is data that starts with one value
 * and gets updated as things happen — the current step index, which plate
 * is visible, whether a panel is open.
 *
 * Keeping all mutable state in a single object makes it clear what the
 * application is tracking and prevents values from being scattered across
 * unrelated parts of the code. Every other module imports `state` and
 * reads or writes its fields directly.
 *
 * Constants (cooldowns, caps) are exported separately so they cannot be
 * accidentally overwritten.
 *
 * Scroll engine model:
 *   Scroll state is a continuous float position derived from Lenis's
 *   animatedScroll value. `scrollPosition` is a continuous float
 *   (0.0 – stepCount-1). `scrollProgress` is the fractional part within
 *   the current step (0.0–1.0). `isSnapping` tracks in-flight snap
 *   animations from the lenis/snap plugin.
 *
 * @version v1.8.0
 */

// ── Constants ────────────────────────────────────────────────────────────────

/** Minimum time (ms) between button-navigation taps. */
export const BUTTON_NAV_COOLDOWN = 400;

// How long a move to a step takes, from how far it moves the camera. Travel is
// measured in units of path length (camera-travel.js, placementTravel): a 2×
// zoom is about 0.5. A move runs 1.33 s per unit, never under the base, which
// is the pace of a move the camera barely takes part in, and never over
// maxSeconds, past which a reader is waiting on the image rather than
// watching it.
const MOVE = { base: 1.2, perUnit: 1.33, maxSeconds: 3 };

/**
 * The pace `?nav=base,perUnit,maxSeconds` asks for, field by field, with a value
 * out of range leaving that field's default. `?nav=1.2,0` gives every move the
 * base whatever it travels, for comparing the two. Read again only when the
 * query string changes.
 */
let _moveTuning = null;
let _moveSearch = null;
function _moveTuningNow() {
  const search = window.location.search;
  if (_moveTuning && search === _moveSearch) return _moveTuning;
  _moveSearch = search;
  _moveTuning = { ...MOVE };
  const raw = new URLSearchParams(search).get('nav');
  const [base, perUnit, maxSeconds] = (raw || '').split(',').map(Number);
  if (base >= 0.1 && base <= 20) _moveTuning.base = base;
  if (perUnit >= 0 && perUnit <= 20) _moveTuning.perUnit = perUnit;
  if (maxSeconds >= 0.1 && maxSeconds <= 20) _moveTuning.maxSeconds = maxSeconds;
  return _moveTuning;
}

/**
 * Seconds a move takes for the camera travel it carries. The scroll, the
 * camera, the cards and the plates all move over this one duration.
 *
 * @param {number} travel - Camera travel in units of path length (camera-travel.js); 0 for none
 * @returns {number}
 */
export function moveSeconds(travel) {
  const { base, perUnit, maxSeconds } = _moveTuningNow();
  return Math.max(base, Math.min(maxSeconds, perUnit * travel));
}

// ── Mutable state ────────────────────────────────────────────────────────────

/**
 * Centralised runtime state for the story page.
 *
 * Grouped by concern so related values are easy to find.
 */
export const state = {
  // ── Navigation ───────────────────────────────────────────────────────────
  /** @type {HTMLElement[]} All .story-step elements in DOM order. */
  steps: [],
  /** Index of the current desktop step (-1 = none). */
  currentIndex: -1,

  // ── Scroll engine ─────────────────────────────────────────────────────────
  /** Continuous float position (e.g. 2.3 = step 2, 30% progress). */
  scrollPosition: 0,
  /** Fractional progress within the current step (0.0–1.0). */
  scrollProgress: 0,
  /** Whether a snap animation is currently in flight. */
  isSnapping: false,
  /** Set true during scroll-driven activateCard calls, so the plate does not animate the camera the scroll is placing. */
  scrollDriven: false,
  /** Lenis instance reference — used by panels.js to stop/start scroll. */
  lenis: null,
  /** Snap plugin instance reference. */
  snap: null,
  /**
   * Pixels one step occupies on the scroll surface: the viewport height the
   * surface was last laid out for, which trails the window by the resize
   * debounce. Every conversion between a step and a scroll offset uses it;
   * 0 when the scroll engine is not running.
   */
  scrollStepPx: 0,

  /** Quick lookup: object_id → object data from window.objectsData. */
  objectsIndex: {},

  // ── Panels ───────────────────────────────────────────────────────────────
  /** @type {{ type: string, id: string }[]} Stack of open panels. */
  panelStack: [],
  /** Whether any panel is currently open. */
  isPanelOpen: false,
  /** Whether scroll-lock is active (blocks step navigation). */
  scrollLockActive: false,
  /** Whether the user dismissed the credits badge this session. */
  creditsDismissed: false,

  // ── Autoplay policy ──────────────────────────────────────────────────────
  /** Set true on first play overlay tap; enables autoplay for all subsequent media cards. */
  hasUserInteracted: false,

  // ── Layout mode & embed ──────────────────────────────────────────────────
  /** @type {'horizontal' | 'vertical'} Layout mode. Updated by layout-mode.js on every resize/orientationchange. */
  layoutMode: 'horizontal',
  /** Page-level boolean, set once at boot from window.telarEmbed.enabled. Orthogonal to layoutMode. */
  isEmbed: false,
  /** @type {DOMRect | null} Active text card's getBoundingClientRect; null when no active text card (title card, full-object mode). Populated by card-pool.js on activation + layout-mode.js on layoutchange. */
  cardOverlayRect: null,

  // ── Button navigation ────────────────────────────────────────────────────
  /** Index of the current step in button navigation. */
  currentButtonStep: 0,
  /** Whether button navigation is showing the intro card (before step 0). */
  buttonInIntro: false,
  /** References to the prev/next button DOM elements. */
  buttonNavButtons: null,
  /** Whether button navigation is in its cooldown period. */
  buttonNavCooldown: false,

  // ── Connection speed ─────────────────────────────────────────────────────
  /** @type {number[]} Measured manifest fetch times (ms) for threshold tuning. */
  manifestLoadTimes: [],

  /**
   * Map of sceneIndex -> Plate, one per scene, built once and never evicted.
   * `.container` is the element. What a plate holds — a viewer, a player,
   * nothing yet — is the plate's own business; the viewer pool inside an image
   * plate is the only thing here that is capped.
   */
  viewerPlates: {},
  /** Map of stepIndex -> text card element. */
  textCards: {},
  /** Map of stepIndex -> title card element. Populated by initCardPool. */
  titleCards: {},
  /** Index of the currently active title card step, or null when none is active. */
  activeTitleCardIndex: null,
  /** The scene of the current object, and the card's position in it (for peek stack positioning). */
  currentObjectScene: { objectId: null, scenePosition: 0 },

  // ── Scene maps (populated at initCardPool time) ───────────────────────────
  /**
   * Filtered step data (metadata rows removed), in the same index space as
   * stepToScene / the card registry. Populated by initCardPool. The per-frame
   * lerp reads this so its stepIndex (a filtered-space index) lines up with
   * the step objects it interpolates between.
   */
  stepsData: [],
  /** Map of stepIndex -> sceneIndex. Populated by buildSceneMaps at init. */
  stepToScene: {},
  /** Map of sceneIndex -> objectId. */
  sceneToObject: {},
  /** Map of sceneIndex -> first stepIndex in that scene. */
  sceneFirstStep: {},
  /** Total number of scenes in the story. */
  totalScenes: 0,

  // ── Viewer preloading config (set from telarConfig in main.js) ───────────
  config: {
    /** Maximum IIIF wrapper instances kept in memory (viewer pool cap). */
    maxViewerCards: 8,
    /** Steps to preload ahead of the current position. */
    preloadSteps: 6,
    /** Show loading shimmer when story has >= this many unique viewers. */
    loadingThreshold: 5,
    /** Hide shimmer once this many viewers are ready. */
    minReadyViewers: 3,
  },
};
