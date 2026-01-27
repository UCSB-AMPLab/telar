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
 * Constants (thresholds, cooldowns, caps) are exported separately so they
 * cannot be accidentally overwritten.
 *
 * @version v0.7.0-beta
 */

// ── Constants ────────────────────────────────────────────────────────────────

/** Minimum time (ms) between step changes to prevent rapid navigation. */
export const STEP_COOLDOWN = 600;

/** Maximum scroll delta (px) per wheel event – caps trackpad acceleration. */
export const MAX_SCROLL_DELTA = 200;

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
  /** Accumulated scroll distance (px) toward the next threshold. */
  scrollAccumulator: 0,
  /** Object ID currently displayed in the viewer. */
  currentObject: null,
  /** Timestamp (ms) of the last step change – used for cooldown. */
  lastStepChangeTime: 0,

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

  // ── Touch (iPad/tablet swipe navigation) ─────────────────────────────────
  /** Y coordinate where the current touch started. */
  touchStartY: 0,
  /** Y coordinate where the current touch ended. */
  touchEndY: 0,

  // ── Mobile / embed button navigation ─────────────────────────────────────
  /** Whether the viewport is below the mobile breakpoint (768 px). */
  isMobileViewport: false,
  /** Index of the current step in mobile/embed button mode. */
  currentMobileStep: 0,
  /** References to the prev/next button DOM elements. */
  mobileNavButtons: null,
  /** Whether mobile navigation is in its cooldown period. */
  mobileNavigationCooldown: false,

  // ── Connection speed ─────────────────────────────────────────────────────
  /** @type {number[]} Measured manifest fetch times (ms) for threshold tuning. */
  manifestLoadTimes: [],

  // ── Thresholds (computed in main.js from window.innerHeight) ─────────────
  /** Scroll distance (px) required to trigger a step change (50 vh). */
  scrollThreshold: 0,
  /** Swipe distance (px) required to trigger a step change (20 vh). */
  touchThreshold: 0,

  // ── Viewer preloading config (set from telarConfig in main.js) ───────────
  config: {
    /** Maximum UV instances kept in memory. */
    maxViewerCards: 10,
    /** Steps to preload ahead of the current position. */
    preloadSteps: 6,
    /** Show loading shimmer when story has >= this many unique viewers. */
    loadingThreshold: 5,
    /** Hide shimmer once this many viewers are ready. */
    minReadyViewers: 3,
  },
};
