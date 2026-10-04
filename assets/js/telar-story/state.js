/**
 * Telar Story – Centralised State
 *
 * This module holds the mutable state for the story page: every value that
 * changes at runtime as the user navigates steps, opens panels, switches
 * viewer objects, and so on. Mutable state is data that starts with one value
 * and gets updated as things happen — the current step index, which viewer
 * card is visible, whether a panel is open.
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

/** Minimum time (ms) between mobile/embed button taps. */
export const MOBILE_NAV_COOLDOWN = 400;

// Seconds a programmatic move to a step takes. This one number is the pace of
// the whole move: Lenis carries the scroll over it, the per-frame interpolation
// follows the scroll and so the viewer pans and zooms over it too, and the card
// slide is written to match. The keyboard is given longer than a button because
// a reader holding an arrow key is reading as they go, where a reader who has
// clicked a section has already chosen where to be.
//
// It lives here rather than beside the scroll because two modules that cannot
// import one another both need it: scroll-engine.js paces the move by it, and
// card-height.js hands it to the stylesheet as the clock the cards and plates
// move on.
const NAV_SECONDS = { keyboard: 1.2, button: 0.75 };

/**
 * Read a tuning override for the pace of a programmatic move.
 *
 * `?nav=1.6` gives the keyboard that many seconds and scales the button move
 * by the same factor, so the two keep their relation. `?nav=1.6,0.9` sets them
 * independently. A value outside the range leaves the defaults, so a mistyped
 * switch cannot strand the reader mid-move. Resolved once, and only for as
 * long as the pace is being settled.
 *
 * @returns {{ keyboard: number, button: number }}
 */
let _navTuning = null;
export function navSeconds() {
  if (_navTuning) return _navTuning;

  _navTuning = { ...NAV_SECONDS };
  try {
    const raw = new URLSearchParams(window.location.search).get('nav');
    if (raw) {
      const [k, btn] = raw.split(',').map(Number);
      if (k >= 0.1 && k <= 20) {
        _navTuning.keyboard = k;
        _navTuning.button = NAV_SECONDS.button * (k / NAV_SECONDS.keyboard);
      }
      if (btn >= 0.1 && btn <= 20) _navTuning.button = btn;
    }
  } catch {
    // A URL we cannot read leaves the defaults standing.
  }
  return _navTuning;
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
  /** Set true during scroll-driven activateCard calls so card-pool skips the 4s OSD animation. */
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

  // ── Mobile button navigation ─────────────────────────────────────────────
  /** Index of the current step in mobile/embed button mode. */
  currentMobileStep: 0,
  /** Whether mobile navigation is showing the intro card (before step 0). */
  mobileInIntro: false,
  /** References to the prev/next button DOM elements. */
  mobileNavButtons: null,
  /** Whether mobile navigation is in its cooldown period. */
  mobileNavigationCooldown: false,

  // ── Connection speed ─────────────────────────────────────────────────────
  /** @type {number[]} Measured manifest fetch times (ms) for threshold tuning. */
  manifestLoadTimes: [],

  /**
   * Map of sceneIndex -> Plate, one per scene, built once and never evicted.
   * `.container` is the element. What a plate holds — a viewer, a player,
   * nothing yet — is the plate's own business; the pool inside an image
   * plate is the only thing here that is capped.
   */
  viewerPlates: {},
  /** Map of stepIndex -> text card element. */
  textCards: {},
  /** Map of stepIndex -> title card element. Populated by initCardPool. */
  titleCards: {},
  /** Index of the currently active title card step, or null when none is active. */
  activeTitleCardIndex: null,
  /** Current object run tracking (for peek stack positioning). */
  currentObjectRun: { objectId: null, runPosition: 0 },

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
    /** Maximum IIIF wrapper instances kept in memory (per-scene pool cap). */
    maxViewerCards: 8,
    /** Steps to preload ahead of the current position. */
    preloadSteps: 6,
    /** Show loading shimmer when story has >= this many unique viewers. */
    loadingThreshold: 5,
    /** Hide shimmer once this many viewers are ready. */
    minReadyViewers: 3,
  },
};
