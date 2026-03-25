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
 * setCardProgress positions the next card proportionally during the
 * scroll scrub, and lerpIiifPosition interpolates the IIIF viewer's
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
 * @version v1.0.0-beta
 */

import Lenis from 'lenis';
import Snap from 'lenis/snap';
import { state } from './state.js';
import { activateCard, setCardProgress } from './card-pool.js';
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

  // Build steps array (navigation.js initializeStepController normally does this)
  state.steps = Array.from(document.querySelectorAll('.story-step'));

  // Prevent browser from restoring scroll position on back/forward nav
  history.scrollRestoration = 'manual';

  // Total positions = intro + stepCount content steps
  totalPositions = stepCount + 1;

  // Set scroll surface height so browser has real scrollable overflow
  surface.style.height = `${totalPositions * window.innerHeight}px`;

  // Create Lenis instance — owns scroll physics
  lenis = new Lenis({
    lerp: 0.06,              // lower = heavier, more contemplative feel
    smoothWheel: true,
    wheelMultiplier: 0.5,    // scroll sensitivity
    autoRaf: false,          // we drive the rAF loop manually
    prevent: (node) => node.closest('.panel') !== null,  // scroll anywhere except inside open panels
  });

  // Create Snap plugin with lock mode — directional snapping (forward on
  // scroll-down, backward on scroll-up).  Lerp-only (no fixed duration) for
  // a gradual settle.  2s dwell on complete absorbs residual scroll input.
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
      lenis.stop();
      dwellTimer = setTimeout(() => { lenis.start(); dwellTimer = null; }, 500);
    },
  });

  // Register snap points: 0 = intro, 1..stepCount = content steps
  registerSnapPoints(totalPositions);

  // Wire scrub mode toggle
  // virtual-scroll fires on raw wheel/touch input before Lenis smoothing
  let scrubEndTimer;
  lenis.on('virtual-scroll', () => {
    cardStack.classList.add('is-scrubbing');
    clearTimeout(scrubEndTimer);
    scrubEndTimer = setTimeout(() => cardStack.classList.remove('is-scrubbing'), 100);
  });

  // Per-frame position update from smoothed scroll output
  lenis.on('scroll', (l) => {
    const position = l.animatedScroll / window.innerHeight;
    updateScrollPosition(position);
  });

  // Start rAF loop — drives Lenis physics every frame
  rafId = requestAnimationFrame(function raf(time) {
    lenis.raf(time);
    rafId = requestAnimationFrame(raf);
  });

  // Resize handler: recalculate heights and snap points
  window.addEventListener('resize', () => {
    surface.style.height = `${totalPositions * window.innerHeight}px`;
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

/**
 * Programmatically navigate to a step (button/keyboard nav — COMPAT-03/04).
 *
 * Uses lenis.scrollTo so the same physics engine drives the animation.
 * Does NOT add is-scrubbing so CSS transitions play at full duration.
 *
 * @param {number} targetIndex - Target step index.
 */
export function advanceToStep(targetIndex) {
  if (targetIndex < 0 || targetIndex >= state.steps.length) return;

  // Use state.lenis (set during initScrollEngine) — allows test injection
  const lenisInstance = state.lenis || lenis;
  if (!lenisInstance) return;

  // +1 to account for intro at position 0
  const targetPx = (targetIndex + 1) * window.innerHeight;
  lenisInstance.scrollTo(targetPx, {
    duration: 0.5,
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

  // Backward only: reset any mid-scrub card that setCardProgress left
  // partially positioned.  Forward leaves it — the CSS transition from
  // activateCard will smoothly complete the slide from wherever it is.
  if (direction === 'backward') {
    const contentStepIndex = Math.floor(Math.max(0, position - 1));
    const scrubCard = state.textCards?.[contentStepIndex + 1];
    if (scrubCard && !scrubCard.classList.contains('is-active')) {
      const rot  = parseFloat(scrubCard.dataset.messinessRot  || 0);
      const offX = parseFloat(scrubCard.dataset.messinessOffX || 0);
      const offY = parseFloat(scrubCard.dataset.messinessOffY || 0);
      scrubCard.style.transform = `translateY(100vh) rotate(${rot}deg) translate(${offX}px, ${offY}px)`;
    }
  }

  // Sync snap.currentSnapIndex so wheel-triggered snaps stay aligned
  if (snap) snap.currentSnapIndex = target;

  // Activate card immediately so it swaps on keypress — the IIIF lerp
  // then runs during the 0.8s scroll animation for simultaneous effect.
  // target is scroll position (intro=0, step0=1, step1=2…); stepIndex
  // is target-1.  Skip for intro (target 0) since there's no card.
  const targetStep = target - 1;
  if (targetStep >= 0 && targetStep !== state.currentIndex) {
    state.scrollDriven = true;
    activateCard(targetStep, direction);
    state.scrollDriven = false;
    state.currentIndex = targetStep;
    updateViewerInfo(targetStep);
  }

  // Suppress the activateCard guard in updateScrollPosition while Lenis
  // animates toward the target — otherwise the first scroll frame sees
  // the old stepIndex and fires activateCard(oldStep, 'backward'),
  // undoing the immediate activation above.
  keyboardNavInFlight = true;

  lenis.scrollTo(target * vh, {
    force: true,
    duration: 0.8,
    easing: (t) => 1 - Math.pow(1 - t, 3),  // ease-out cubic
    onComplete: () => { keyboardNavInFlight = false; },
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

    // Crossed from content back to intro
    if (state.currentIndex >= 0) {
      goToStep(-1, 'backward');
    }

    // Scrub the first card + viewer plate proportionally during intro→step0
    const progress = position; // 0 at top, 1 at step 0
    const firstCard = state.textCards?.[0];
    if (firstCard) {
      const rot  = parseFloat(firstCard.dataset.messinessRot  || 0);
      const offX = parseFloat(firstCard.dataset.messinessOffX || 0);
      const offY = parseFloat(firstCard.dataset.messinessOffY || 0);
      const translateY = (1 - progress) * 100; // vh
      firstCard.style.transform = `translateY(${translateY}vh) rotate(${rot}deg) translate(${offX}px, ${offY}px)`;
    }
    // Scene 0 is always the first scene — use index directly, no objectId lookup needed.
    const firstPlate = state.viewerPlates?.[0];
    if (firstPlate) {
      const plateTranslateY = (1 - progress) * 100; // %
      firstPlate.style.transform = `translateY(${plateTranslateY}%)`;
    }
    return;
  }

  const clamped = Math.min(maxContent, contentPos);
  const stepIndex = Math.floor(clamped);
  const progress = clamped - stepIndex;

  state.scrollProgress = progress;

  // Per-frame scrub updates
  setCardProgress(stepIndex, progress);
  lerpIiifPosition(stepIndex, progress, window.storyData?.steps || []);

  // Integer boundary crossings — activateCard  // Mark as scroll-driven so activateCard skips the 4s OSD spring animation
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
  }
}
