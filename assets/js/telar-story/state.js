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
 * @version v1.0.0-beta
 */

// ── Constants ────────────────────────────────────────────────────────────────

/** Minimum time (ms) between mobile/embed button taps. */
export const MOBILE_NAV_COOLDOWN = 400;

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
  /** Object ID currently displayed in the viewer. */
  currentObject: null,

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

  // ── Viewer cards ─────────────────────────────────────────────────────────
  /** The viewer card object currently visible on screen. */
  currentViewerCard: null,
  /** @type {ViewerCard[]} Pool of viewer card objects. */
  viewerCards: [],
  /** Counter for generating unique viewer instance DOM IDs. */
  viewerCardCounter: 0,
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

  // ── Mobile / embed button navigation ─────────────────────────────────────
  /** Whether the viewport is below the mobile breakpoint (768 px). */
  isMobileViewport: false,
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

  // ── Card pool ────────────────────────────────────────────────────────────
  /** @type {Object[]} Pool of active card instances. */
  cardPool: [],
  /** Map of sceneIndex -> viewer plate element (one plate per scene). */
  viewerPlates: {},
  /** Map of stepIndex -> text card element. */
  textCards: {},
  /** Current object run tracking (for peek stack positioning). */
  currentObjectRun: { objectId: null, runPosition: 0 },

  // ── Scene maps (populated at initCardPool time) ───────────────────────────
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
    /** Maximum Tify instances kept in memory (per-scene pool cap). */
    maxViewerCards: 8,
    /** Steps to preload ahead of the current position. */
    preloadSteps: 6,
    /** Show loading shimmer when story has >= this many unique viewers. */
    loadingThreshold: 5,
    /** Hide shimmer once this many viewers are ready. */
    minReadyViewers: 3,
  },
};
