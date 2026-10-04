/**
 * Telar Story – Scroll Engine
 *
 * This module replaces the old discrete scroll accumulator with a
 * continuous scroll model powered by Lenis. Instead of counting scroll
 * ticks and jumping between steps, the user scrolls fluidly through the
 * story and the system derives a floating-point position from the scroll
 * offset — for example, position 2.3 means step 2 with 30% progress
 * toward step 3.
 *
 * Lenis is an open-source MIT-licensed smooth scroll library maintained
 * by Studio Freight. It provides a virtual scroll model that normalises
 * browser differences in scroll physics, giving Telar a consistent,
 * contemplative feel across platforms. It is bundled into the single
 * telar-story.js file by esbuild — no CDN dependency, no external
 * requests — keeping Telar fully self-contained and aligned with its
 * minimal-computing, zero-dependency hosting philosophy.
 *
 * Magnetic waypoints — the lenis/snap proximity plugin provides snap
 * points at every integer boundary (each story step). Snapping only
 * fires when scroll velocity drops below a threshold, so the user can
 * power through multiple steps with a fast scroll without being caught
 * by each waypoint along the way.
 *
 * Per-frame wiring — every animation frame, the scroll callback computes
 * the current fractional position and drives two visual systems:
 * setCardProgress interpolates the next card's position proportionally,
 * and lerpIiifPosition interpolates the IIIF viewer's
 * x/y/zoom coordinates between same-object step pairs. Smoothness comes
 * from Lenis's animatedScroll value, not from OpenSeadragon animations.
 *
 * Button and keyboard navigation — advanceToStep() triggers a Lenis
 * scrollTo() animation rather than jumping directly, so all navigation
 * paths (scroll, keyboard, buttons) go through the same visual pipeline.
 * On iOS Safari, Lenis is not initialised because its momentum model
 * is unreliable on that platform; the code path falls through to
 * button-only navigation in main.js.
 *
 * @version v1.8.0
 */

import Lenis from 'lenis';
import Snap from 'lenis/snap';
import { state } from './state.js';
import { onViewportResize } from './layout-mode.js';
import { activateCard, setCardProgress, settleCards } from './card-pool.js';
import { writeHash } from './deep-link.js';
import { goToStep, updateViewerInfo } from './navigation.js';
import { initKeyboardNavigation } from './navigation.js';
import { initializeLoadingShimmer } from './viewer.js';
import { lerpIiifPosition } from './iiif-card.js';

// ── Module-level references ───────────────────────────────────────────────────

let lenis;
let snap;
let snapRemovers = [];
let rafId;
let dwellTimer;
let scrubEndTimer;
let cardStackEl;
let totalPositions = 0;
let keyboardNavInFlight = false;

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Initialise the Lenis scroll engine for desktop story navigation.
 *
 * Position model:
 *   scroll position 0 = intro card (title screen)
 *   scroll position 1 = content step 0 (first story card)
 *   scroll position N = content step N-1
 *
 * The scroll surface is (stepCount + 1) viewports tall so the intro
 * occupies position 0 and content steps start at position 1.
 *
 * @param {number} stepCount - Total number of story steps.
 */
export function initScrollEngine(stepCount) {
  const surface = document.querySelector('.scroll-surface');
  const cardStack = document.querySelector('.card-stack');

  if (!surface || !cardStack) {
    console.error('scroll-engine: .scroll-surface or .card-stack not found in DOM');
    return;
  }

  // Idempotent re-init: cancel any prior rAF loop and pending dwell-restart
  // timer so a second initScrollEngine() (e.g. a layout-mode switch) cannot
  // leave a second rAF loop double-driving Lenis or an orphaned timer firing.
  // (The dwell-restart itself is already guarded by `if (!state.isPanelOpen)`.)
  if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
  if (dwellTimer) { clearTimeout(dwellTimer); dwellTimer = null; }
  if (scrubEndTimer) { clearTimeout(scrubEndTimer); scrubEndTimer = null; }

  // Build steps array (navigation.js initializeStepController normally does this)
  state.steps = Array.from(document.querySelectorAll('.story-step'));

  // Prevent browser from restoring scroll position on back/forward nav
  history.scrollRestoration = 'manual';

  // Total positions = intro + stepCount content steps
  totalPositions = stepCount + 1;

  // Set scroll surface height so browser has real scrollable overflow
  surface.style.height = `${totalPositions * window.innerHeight}px`;

  // Create Lenis instance — owns scroll physics
  // Reduced-motion users: skip Lenis smooth-wheel interpolation; snap to native scroll.
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  lenis = new Lenis({
    lerp: 0.06,              // lower = heavier, more contemplative feel
    smoothWheel: !prefersReduced,
    wheelMultiplier: 0.5,    // scroll sensitivity
    autoRaf: false,          // we drive the rAF loop manually
    prevent: (node) => node.closest('.offcanvas') !== null || node.closest('[data-telar-panel]') !== null,  // let wheel events pass through inside open panels
  });

  // Create Snap plugin with lock mode — directional snapping (forward on
  // scroll-down, backward on scroll-up).  Lerp-only (no fixed duration) for
  // a gradual settle.  500ms dwell on complete (see dwellTimer below) absorbs
  // residual scroll input.
  snap = new Snap(lenis, {
    type: 'lock',
    velocityThreshold: 0.5,
    debounce: 150,
    distanceThreshold: '20%',
    lerp: 0.08,
    onSnapStart: () => {
      state.isSnapping = true;
    },
    onSnapComplete: () => {
      state.isSnapping = false;
      // Force a final position update — the last scroll callback may have
      // fired just before the snap landed (e.g. position 0.99 instead of
      // 1.0), so state.currentIndex would not yet reflect the snapped step.
      const finalPosition = lenis.animatedScroll / window.innerHeight;
      updateScrollPosition(finalPosition);
      writeHash();
      lenis.stop();
      dwellTimer = setTimeout(() => {
        if (!state.isPanelOpen) {
          lenis.start();
        }
        dwellTimer = null;
      }, 500);
    },
  });

  // Register snap points: 0 = intro, 1..stepCount = content steps
  registerSnapPoints(totalPositions);

  // Wire the is-scrubbing flag — the reader's own scroll, from the first raw
  // wheel or touch event to the frame the scroll finally stops on.
  // virtual-scroll fires on raw input before Lenis smoothing; the scroll it
  // starts outlives it by the smoothing tail and then by the snap's lerp, and
  // the cards have to keep tracking it for all of that or they hold a position
  // the scroll has long left. Both events therefore re-arm the same timer, so
  // the flag lapses 100 ms after the last frame rather than the last gesture.
  cardStackEl = cardStack;
  lenis.on('virtual-scroll', () => {
    cardStack.classList.add('is-scrubbing');
    armScrubEnd();
  });

  // Per-frame position update from smoothed scroll output
  lenis.on('scroll', (l) => {
    const position = l.animatedScroll / window.innerHeight;
    updateScrollPosition(position);
    if (cardStack.classList.contains('is-scrubbing')) armScrubEnd();
  });

  // Start rAF loop — drives Lenis physics every frame
  rafId = requestAnimationFrame(function raf(time) {
    lenis.raf(time);
    rafId = requestAnimationFrame(raf);
  });

  // Viewport-resize subscription: recalculate heights and snap points
  onViewportResize(({ viewport }) => {
    surface.style.height = `${totalPositions * viewport.h}px`;
    lenis.resize();
    registerSnapPoints(totalPositions);
  });

  // Store instances on state for external access (panels.js stop/start)
  state.lenis = lenis;
  state.snap = snap;

  // Wire keyboard navigation
  initKeyboardNavigation();

  // Initialise loading shimmer
  initializeLoadingShimmer();
}

/**
 * Hold the scrub open for another 100 ms.
 *
 * Re-armed by raw input and by every scroll frame the reader's scroll produces,
 * so the window covers the whole gesture — wheel, smoothing tail, snap lerp —
 * and closes only once the scroll has actually stopped.
 */
function armScrubEnd() {
  clearTimeout(scrubEndTimer);
  scrubEndTimer = setTimeout(endScrub, 100);
}

/**
 * Close the scrub: the cards go back on their CSS transitions, and the position
 * they were tracking frame by frame is stated once more as the place they rest.
 *
 * Also the handover to programmatic navigation. A keyboard or button move is
 * not the reader's scroll and animates on the transitions the scrub suppresses,
 * so a move made mid-gesture closes the scrub before it starts rather than
 * inheriting a window that would turn its slide into a jump.
 */
function endScrub() {
  clearTimeout(scrubEndTimer);
  scrubEndTimer = null;
  if (!cardStackEl) return;
  cardStackEl.classList.remove('is-scrubbing');
  if (lenis) settleCards(lenis.animatedScroll / window.innerHeight);
}

/**
 * Register snap points at each viewport boundary.
 * @param {number} count - Total positions (intro + content steps).
 */
function registerSnapPoints(count) {
  snapRemovers.forEach(fn => fn());
  snapRemovers = [];
  for (let i = 0; i < count; i++) {
    snapRemovers.push(snap.add(i * window.innerHeight));
  }
}

// Seconds a programmatic move to a step takes. This one number is the pace of
// the whole move: Lenis carries the scroll over it, the per-frame interpolation
// follows the scroll and so the viewer pans and zooms over it too, and the card
// slide is written to match. The keyboard is given longer than a button because
// a reader holding an arrow key is reading as they go, where a reader who has
// clicked a section has already chosen where to be.
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
function navSeconds() {
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

/**
 * Programmatically navigate to a step (button/keyboard nav).
 *
 * Uses lenis.scrollTo so the same physics engine drives the animation.
 * Programmatic navigation is not user scrubbing, so is-scrubbing is never
 * added: per-frame card interpolation stays inert and CSS transitions
 * animate the slide at full duration.
 *
 * @param {number} targetIndex - Target step index.
 */
export function advanceToStep(targetIndex) {
  if (targetIndex < 0 || targetIndex >= state.steps.length) return;

  // Use state.lenis (set during initScrollEngine) — allows test injection
  const lenisInstance = state.lenis || lenis;
  if (!lenisInstance) return;

  endScrub();

  // +1 to account for intro at position 0
  const targetPx = (targetIndex + 1) * window.innerHeight;
  lenisInstance.scrollTo(targetPx, {
    duration: navSeconds().button,
    easing: (t) => 1 - Math.pow(1 - t, 3),  // ease-out cubic
  });
}

/**
 * Keyboard-driven step navigation.
 *
 * Reads the true scroll position from Lenis and navigates to the
 * correct target step:
 *   forward  — complete a partial step, or advance to next if at integer
 *   backward — revert a partial step, or go back if at integer
 *
 * Bypasses the Snap plugin entirely to avoid its currentSnapIndex desync
 * bug (goTo sets the index before scrollTo, which silently fails when
 * isLocked is true).  Uses lenis.scrollTo with force:true so it works
 * even during dwell or mid-snap animation.
 *
 * The 0.3s animated scroll drives lerpIiifPosition every frame for
 * smooth IIIF pan.  activateCard fires at the integer boundary with
 * scrollDriven=true so it skips the redundant 4s OSD spring animation
 * (the lerp already positioned the viewer correctly).
 *
 * @param {'forward'|'backward'} direction
 */
export function keyboardNav(direction) {
  if (!lenis) return;

  // The keyboard is not the reader's scroll: close any scrub still open so the
  // move animates on the CSS transitions rather than being written per frame.
  endScrub();

  // Clear any active dwell — keyboard overrides scroll dwell
  if (dwellTimer) {
    clearTimeout(dwellTimer);
    dwellTimer = null;
    lenis.start();
  }

  const vh = window.innerHeight;
  const position = lenis.animatedScroll / vh;
  const isExact = Math.abs(position - Math.round(position)) < 0.01;
  const rounded = Math.round(position);

  let target;
  if (direction === 'forward') {
    target = isExact ? rounded + 1 : Math.ceil(position);
  } else {
    target = isExact ? rounded - 1 : Math.floor(position);
  }

  // Clamp to valid range
  target = Math.max(0, Math.min(target, totalPositions - 1));
  if (target === rounded && isExact) return; // at boundary, no-op

  // State the target before the scroll starts for it: the keyboard knows its
  // landing, so the cards can slide to it on their own transitions over the
  // same 0.8s, whatever a scrub left half-placed on the way in. Both directions
  // go through it — a backward move's departing card is the card the target
  // position puts a viewport down.
  settleCards(target);

  // Sync snap.currentSnapIndex so wheel-triggered snaps stay aligned
  snap.currentSnapIndex = target;

  // Activate card immediately so it swaps on keypress — the IIIF lerp
  // then runs during the 0.8s scroll animation for simultaneous effect.
  // target is scroll position (intro=0, step0=1, step1=2…); stepIndex
  // is target-1.
  const targetStep = target - 1;
  if (targetStep >= 0 && targetStep !== state.currentIndex) {
    state.scrollDriven = true;
    activateCard(targetStep, direction);
    state.scrollDriven = false;
    state.currentIndex = targetStep;
    updateViewerInfo(targetStep);
    if (state.onStepChange) state.onStepChange(targetStep);
  } else if (targetStep < 0 && state.currentIndex >= 0) {
    // Target 0 is the intro, which carries no card. The intro zone's own
    // restore below is suppressed by keyboardNavInFlight for the whole
    // animation, so the restore runs here — the same call the scroll zone and
    // the Back to Start button make, so index, fragment and nav button end up
    // where those paths leave them.
    goToStep(-1, 'backward');
  }

  // Suppress the activateCard guard in updateScrollPosition while Lenis
  // animates toward the target — otherwise the first scroll frame sees
  // the old stepIndex and fires activateCard(oldStep, 'backward'),
  // undoing the immediate activation above.
  keyboardNavInFlight = true;

  lenis.scrollTo(target * vh, {
    force: true,
    duration: navSeconds().keyboard,
    easing: (t) => 1 - Math.pow(1 - t, 3),  // ease-out cubic
    onComplete: () => {
      keyboardNavInFlight = false;
      writeHash();
    },
  });
}

/**
 * Return current scroll engine state for debugging.
 *
 * @returns {{ lenis: Lenis, snap: Snap, position: number, progress: number }}
 */
export function getScrollEngineState() {
  return {
    lenis,
    snap,
    position: state.scrollPosition,
    progress: state.scrollProgress,
  };
}

// ── Internal ──────────────────────────────────────────────────────────────────

/**
 * Derive step index and fractional progress from continuous scroll position.
 *
 * Position model (intro offset):
 *   raw position 0   = intro card      → contentIndex = -1
 *   raw position 0.5 = halfway intro→step0
 *   raw position 1   = content step 0  → contentIndex = 0
 *   raw position 2.3 = step 1, 30%     → contentIndex = 1
 *
 * @param {number} position - Raw float position from Lenis (0 = intro).
 */
export function updateScrollPosition(position) {
  // Content index: subtract 1 so intro = -1, first content step = 0
  const contentPos = position - 1;
  const maxContent = state.steps.length - 1;

  // Store raw position on state
  state.scrollPosition = position;

  // ── Intro zone (position < 1) ──
  // The intro stays put — the first scene (viewer plate + text card) slides
  // up over it as the user scrolls from position 0 to 1.
  if (position < 1) {
    state.scrollProgress = 0;

    // Crossed from content back to intro — but not during a keyboard-triggered
    // scroll animation, which passes through the intro zone on its way to step 1
    if (state.currentIndex >= 0 && !keyboardNavInFlight) {
      goToStep(-1, 'backward');
    }

    // The first card and the first viewer plate slide up over the intro in
    // proportion to the position, which is the settle's own intro branch —
    // the same writes, and the same place any other path states them.
    settleCards(position);
    return;
  }

  const clamped = Math.min(maxContent, contentPos);
  const stepIndex = Math.floor(clamped);
  const progress = clamped - stepIndex;

  state.scrollProgress = progress;

  // Per-frame interpolation updates. A keyboard move has already settled its
  // own target, and passes over whole steps on the way there; restating the
  // rest of one of those would push the arriving card back down mid-flight.
  if (!keyboardNavInFlight || progress >= 0.001) setCardProgress(stepIndex, progress);
  // Feed the FILTERED steps (state.stepsData) — stepIndex is a filtered-space
  // index (it drives state.stepToScene), so the unfiltered window.storyData
  // .steps would mis-index on stories that contain metadata rows.
  lerpIiifPosition(stepIndex, progress, state.stepsData || []);

  // Integer boundary crossings — activateCard
  // Mark as scroll-driven so activateCard skips the 4s OSD spring animation
  // (lerpIiifPosition already positioned the viewer correctly each frame).
  // Skip during keyboard nav — keyboardNav() already activated the card
  // and the scroll position hasn't caught up yet.
  if (stepIndex !== state.currentIndex && !keyboardNavInFlight) {
    const direction = stepIndex > state.currentIndex ? 'forward' : 'backward';
    state.scrollDriven = true;
    activateCard(stepIndex, direction);
    state.scrollDriven = false;
    state.currentIndex = stepIndex;
    updateViewerInfo(stepIndex);
    if (state.onStepChange) state.onStepChange(stepIndex);
  }
}
