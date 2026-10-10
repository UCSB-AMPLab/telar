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
 * @version v1.8.1
 */

import Lenis from 'lenis';
import Snap from 'lenis/snap';
import { state, moveSeconds } from './state.js';
import { setMoveSeconds, moveSecondsNow } from './card-height.js';
import { onViewportResize } from './layout-mode.js';
import { activateCard, setCardProgress, settleCards } from './card-pool.js';
import { writeHash } from './deep-link.js';
import { followEngine, goToStep, updateViewerInfo, initKeyboardNavigation } from './navigation.js';
import { initializeLoadingShimmer } from './viewer.js';
import { lerpIiifPosition } from './iiif-card.js';
import { timeMove, keyboardTarget } from './move-plan.js';
import { isInsidePanel, isStoryInput } from './story-input.js';

// ── Module-level references ───────────────────────────────────────────────────

let lenis;
let snap;
let snapRemovers = [];
let rafId;
let dwellTimer;
// The reader's input history, which the post-snap dwell reads (see _endDwell).
let dwellHeld, lastInputAt, recentSizes, runStart, snapRun, snapRef, landedAt;
const _resetInputHistory = () => { dwellHeld = false; snapRun = null; snapRef = Infinity;
  lastInputAt = runStart = -Infinity; recentSizes = []; };
_resetInputHistory();
let scrubEndTimer;
let cardStackEl;
let totalPositions = 0;
let keyboardNavInFlight = false;

// The move the engine is driving itself, or 0 while the scroll belongs to the
// reader. A programmatic move ends exactly on a step and the path that starts
// it states where the cards and plates belong, so the scroll coming to rest at
// the end of one is not a rest that needs settling: settling it there rewrites
// transforms the move's own transitions are still running towards.
//
// A token rather than a flag, because two moves can overlap — a gesture
// carried to the nearer step and then a keyboard press before it lands — and
// Lenis calls onComplete for a move that a later scrollTo has already
// superseded. A boolean would be cleared by the first move finishing and leave
// the second unprotected for the rest of its travel; a token means only the
// move that is still current can clear it.
let navToken = 0;
let navSeq = 0;

// Where the keyboard's own move is going, held beside the token that owns it.
//
// A press arriving mid-move steps from here rather than from the scroll. The
// position mid-move is one this engine is driving towards a landing it already
// chose, so reading it as a place the reader left the scroll makes the press
// re-issue the move already running: the reader presses and nothing happens,
// and nothing ever will. The fractional position is still the right reading
// for a scroll the reader did leave part way.
//
// Held against a token so that only the move that is still current can be
// stepped from. Every other programmatic path takes a token of its own, which
// drops this one without having to say so; the reader's raw input is the one
// takeover that begins no move, so it clears this itself.
let navTarget = null;
let navTargetToken = 0;

// Which way the reader's scroll was last travelling, and where it was. A
// gesture that stops between steps is carried the way it was already going.
let scrollDirection = 1;
let lastPosition = 0;

// Where a move the engine is driving is going, as a scroll position, held
// beside the token of the move that set it. A resize that lands mid-move ends
// the move by jumping, and the jump goes where the move was going.
let moveTarget = null;
let moveTargetToken = 0;

// The token of the move a button tap started. While it is the move in flight,
// a second tap steps on from where it is going. Every path that ends the move
// short of its landing clears it along with the move's own token.
let buttonMoveToken = 0;

// Set while the resize lays the surface out again, so the scroll frames Lenis
// emits on the way are not read as the reader's: each one is an offset in one
// layout divided by a step height from the other.
let remapping = false;

/** Begin a programmatic move; the returned token ends it, if still current. */
function beginNav() {
  navToken = ++navSeq;
  return navToken;
}

/** Record where the move holding this token is going. */
function _recordMoveTarget(token, position) {
  moveTarget = position;
  moveTargetToken = token;
}

/**
 * Pixels one step occupies on the scroll surface. It is the viewport height
 * the surface was last laid out for, not the window's current one: between the
 * browser's resize and the debounced relayout the surface is still in the old
 * layout, and so are its offsets.
 */
function _stepPx() {
  return state.scrollStepPx || window.innerHeight;
}

/**
 * State where a move that has just completed landed, if it is still the move
 * current. The scroll handler reads no frame while the layout and the window
 * disagree, so a move completing then leaves the position at the last frame
 * read, and a relayout would put the reader back a step.
 */
function _stateLanding(token, position) {
  if (navToken === token) state.scrollPosition = position;
}

/** End a programmatic move, unless a later one has taken over. */
function endNav(token) {
  if (navToken === token) navToken = 0;
}

/**
 * Hold a scroll position inside the story: 0 is the intro, and the last step
 * is the end of it.
 *
 * @param {number} position
 * @returns {number}
 */
function _clampPosition(position) {
  return Math.max(0, Math.min(position, totalPositions - 1));
}

// How far the scroll must move since it last held `is-scrubbing` open for a frame
// to count as still travelling: the half pixel at which Lenis calls a smoothed
// move complete. Lenis completes a move only when its value rounds to its
// target's rounding, so a target on a half pixel (an odd wheel total under a
// wheel multiplier of 0.5) is approached from below and never completes; its
// frames differ by millionths of a pixel and, read as travel, would hold
// `is-scrubbing` open for good and keep the gesture from being carried to a step.
const SCROLL_MOVING_PX = 0.5;
let armedAt = 0;  // the scroll offset at which a frame last held is-scrubbing open

// How near a whole step counts as resting on it. A scroll lands on fractions
// of a pixel, and a thousandth of a viewport is under a pixel on every cell.
const REST_TOLERANCE = 0.001;

// Past its minimum the post-snap dwell holds while input is the tail of the wheel
// gesture that drove the snap, which would carry it a second step, for MAX_HOLD_MS
// after landing at most: tails run to about 2.6 s (WebKit), and a slow steady
// scroll can stay under the size rule. Momentum only shrinks: a new gesture is a
// touch, an input RISE_PX over the largest of the last three (tail jitter, 24 18
// 12 6 12 wheel px, stays under), one no smaller than the last after a 200 ms
// pause, or, once the snap has landed, than the last before it began.
/** The quiet, in ms, after which the next wheel event starts a new gesture. */
const WHEEL_GESTURE_GAP_MS = 200;
const RISE_PX = 2, MAX_HOLD_MS = 3000;
function _endDwell() {
  const now = performance.now();
  const wait = Math.min(WHEEL_GESTURE_GAP_MS - (now - lastInputAt), landedAt + MAX_HOLD_MS - now);
  dwellHeld = runStart === snapRun && wait > 0;
  dwellTimer = dwellHeld ? setTimeout(_endDwell, wait) : null;
  if (!dwellTimer && !state.isPanelOpen) lenis.start();
}

/** Whether an input of this size begins a new gesture, against the recent history. */
function _beginsGesture(event, now, size) {
  if (event?.type?.startsWith('touch')) return true;
  if (runStart === snapRun && !state.isSnapping && size >= snapRef) return true;
  return now - lastInputAt >= WHEEL_GESTURE_GAP_MS
    ? !(size < (recentSizes.at(-1) ?? 0)) : size > Math.max(0, ...recentSizes) + RISE_PX;
}

/** Record a story input; one that begins a new gesture ends a held dwell. */
function _noteInput({ deltaY = 0, event } = {}) {
  const now = performance.now(), size = Math.abs(deltaY);
  if (_beginsGesture(event, now, size)) [runStart, recentSizes] = [now, []];
  [recentSizes, lastInputAt] = [[...recentSizes.slice(-2), size], now];
  if (dwellHeld && runStart !== snapRun) _clearDwell();
}

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

  // Idempotent re-init: a second initScrollEngine() (e.g. a layout-mode switch)
  // must not leave a second rAF loop driving Lenis or an orphaned timer firing.
  // A move in flight belongs to the engine being replaced, on a Lenis this one
  // does not own: the token that would stand it down never arrives, so a target
  // left here would be stepped from by the next press, a settle stay suppressed.
  if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
  if (dwellTimer) { clearTimeout(dwellTimer); dwellTimer = null; }
  if (scrubEndTimer) { clearTimeout(scrubEndTimer); scrubEndTimer = null; }
  _resetInputHistory();
  armedAt = navToken = navTargetToken = moveTargetToken = buttonMoveToken = 0;
  navTarget = moveTarget = null;
  remapping = keyboardNavInFlight = false;

  // Build steps array (navigation.js initializeStepController normally does this)
  state.steps = Array.from(document.querySelectorAll('.story-step'));

  // Prevent browser from restoring scroll position on back/forward nav
  history.scrollRestoration = 'manual';

  totalPositions = stepCount + 1;

  // Set scroll surface height so browser has real scrollable overflow
  state.scrollStepPx = window.innerHeight;
  surface.style.height = `${totalPositions * state.scrollStepPx}px`;

  // Lenis owns scroll physics. Reduced-motion users: skip Lenis smooth-wheel interpolation; snap to native scroll.
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  lenis = new Lenis({
    lerp: 0.06,              // lower = heavier, more contemplative feel
    smoothWheel: !prefersReduced,
    wheelMultiplier: 0.5,    // scroll sensitivity
    autoRaf: false,          // we drive the rAF loop manually
    prevent: isInsidePanel,  // let wheel events pass through inside open panels
  });

  // Create Snap plugin with lock mode — directional snapping (forward on
  // scroll-down, backward on scroll-up).  Lerp-only (no fixed duration) for
  // a gradual approach.  The dwell on complete (see dwellTimer below) absorbs
  // residual scroll input while the cards arrive.
  snap = new Snap(lenis, {
    type: 'lock',
    velocityThreshold: 0.5,
    debounce: 150,
    distanceThreshold: '20%',
    lerp: 0.08,
    onSnapStart: () => {
      state.isSnapping = true;
      [snapRun, snapRef] = [runStart, recentSizes.at(-1) ?? Infinity];
    },
    onSnapComplete: () => {
      state.isSnapping = false;
      // Force a final position update — the last scroll callback may have
      // fired just before the snap landed (e.g. position 0.99 instead of
      // 1.0), so state.currentIndex would not yet reflect the snapped step.
      // Between the window's resize and the relayout the offset is read
      // against a surface laid out for another height, and the browser has
      // clamped it: the step the snap was heading for is the landing then.
      const layoutStale = remapping || window.innerHeight !== _stepPx();
      const finalPosition = layoutStale && Number.isInteger(snap.currentSnapIndex)
        ? snap.currentSnapIndex : lenis.animatedScroll / _stepPx();
      updateScrollPosition(finalPosition);
      writeHash();
      lenis.stop();
      // The dwell holds the scroll still while the cards finish arriving, so
      // it is the duration of the move rather than a number of its own: a
      // dwell shorter than the motion hands the reader back a scroll that can
      // be pushed while the stack is still settling into the step behind it.
      landedAt = performance.now();
      dwellTimer = setTimeout(_endDwell, moveSecondsNow() * 1000);
    },
  });

  // Register snap points: 0 = intro, 1..stepCount = content steps
  registerSnapPoints(totalPositions);

  // The is-scrubbing flag spans the reader's own scroll, from the first raw
  // input to the frame the scroll stops on: the scroll outlives the input by
  // the smoothing tail and the snap's lerp, and the cards track it throughout,
  // so input and frames re-arm one timer that lapses 100 ms after the last.
  cardStackEl = cardStack;
  lenis.on('virtual-scroll', (payload) => {
    const readerInput = isStoryInput(payload);
    if (readerInput) _noteInput(payload);
    cardStack.classList.add('is-scrubbing');
    if (readerInput && !(payload?.event && (lenis.isStopped || lenis.isLocked))) {
      // A scroll the reader is driving has no landing the keyboard chose, so
      // the next press reads the position. Every other takeover begins a move,
      // whose token drops the target on its own; raw input begins none, so it
      // says so.
      navTarget = null;
      // The same takeover stands the move itself down, because the move cannot.
      // Lenis answers input it acts on either by stopping the running
      // animation, which calls neither of its callbacks, or by replacing it
      // with the reader's own scroll, which carries the callbacks away with it
      // — so the onComplete holding these is unreachable from the moment this
      // fires, and the guards it would lower stay up for the rest of the
      // reader's session.
      keyboardNavInFlight = false;
      // Every move stands down with its guards, a carry included: the reader's
      // scroll replaces it, and a token kept past here would refuse this
      // gesture's carry and every carry after it until another move took one.
      navToken = 0;
      buttonMoveToken = 0;
      // The reader's scroll paces the camera itself, so what is left to time
      // is the cards' last settle and the dwell after a snap: the base.
      setMoveSeconds(moveSeconds(0));
    }
    armScrubEnd();
  });

  // Per-frame position update from smoothed scroll output
  lenis.on('scroll', (l) => {
    // Nothing is read from the scroll while its layout and the window
    // disagree. The browser clamps the offset to the resized window before the
    // surface is laid out again, and Lenis reports the clamped offset: read,
    // it moves the reader to a step they never scrolled to, and it overwrites
    // the position the relayout needs to put them back where they were.
    if (remapping || window.innerHeight !== _stepPx()) return;
    const position = l.animatedScroll / _stepPx();
    if (position !== lastPosition) {
      scrollDirection = position > lastPosition ? 1 : -1;
      lastPosition = position;
    }
    updateScrollPosition(position);
    // Armed on every frame of the reader's own scroll, flagged or not: a
    // scroll outlives its flag — the smoothing tail and the snap lerp both run
    // past it — and the frames after it lapses are exactly the ones no other
    // path states a position for, so a gesture that drifts to a stop away from
    // a waypoint would leave the stack at whatever position the flag happened
    // to lapse on.
    if (!navToken && Math.abs(l.animatedScroll - armedAt) >= SCROLL_MOVING_PX) {
      armedAt = l.animatedScroll;
      armScrubEnd();
    }
  });

  // Start rAF loop — drives Lenis physics every frame
  rafId = requestAnimationFrame(function raf(time) {
    lenis.raf(time);
    rafId = requestAnimationFrame(raf);
  });

  // Viewport-resize subscription: lay the surface out again at the new height
  // with the reader on the same step.
  onViewportResize(({ viewport }) => {
    if (viewport.h === _stepPx()) {
      surface.style.height = `${totalPositions * viewport.h}px`;
      lenis.resize();
      registerSnapPoints(totalPositions);
      return;
    }
    _remapToHeight(surface, viewport.h);
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
 * Hold `is-scrubbing` for another 100 ms.
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
 * End scrubbing: the cards go back on their CSS transitions, and the position
 * they were tracking frame by frame is stated once more as the place they rest.
 *
 * Also the handover to programmatic navigation. A keyboard or button move is
 * not the reader's scroll and animates on the transitions `is-scrubbing`
 * suppresses, so a move made mid-gesture ends scrubbing before it starts rather
 * than inheriting a window that would turn its slide into a jump. A move that
 * states its own landing ends scrubbing without the settle.
 */
function endScrub({ carry = true, settle = true } = {}) {
  clearTimeout(scrubEndTimer);
  scrubEndTimer = null;
  if (!cardStackEl) return;
  cardStackEl.classList.remove('is-scrubbing');
  if (!lenis) return;

  const position = lenis.animatedScroll / _stepPx();
  if (settle) settleCards(position);
  // Only a reader's own gesture coming to rest is carried to the nearer step.
  // A programmatic move ends scrubbing on its way past and already knows its
  // landing, so carrying it as well would put two moves on one scroll.
  if (carry) carryToNearestStep(position);
}

/**
 * Carry a gesture that has come to rest between two steps to the nearer one.
 *
 * The snap engages only for a gesture that carries the scroll across a
 * waypoint; one that stops short of that is left where it stopped, and a
 * story is a sequence of steps rather than a continuous surface — the reader
 * would be between two panels, the viewer between two framings, and the
 * fragment still naming the step last crossed, so a link shared from there
 * points at a step the page is not on.
 *
 * Runs only for the reader's own scroll coming to rest: a move the engine
 * drives itself ends on a step by construction, and the snap's own landing
 * is already a step.
 *
 * @param {number} position - Where the scroll came to rest; 0 is the intro.
 */
function carryToNearestStep(position) {
  if (navToken || state.isSnapping) return;

  // The step the gesture was heading for, not the one it happens to be
  // nearest. A reader scrolling back who stops nine tenths of the way to the
  // step behind them meant to go back; carrying them to the step in front
  // because it is a tenth nearer takes the story somewhere they were leaving.
  const target = scrollDirection < 0 ? Math.floor(position) : Math.ceil(position);
  if (Math.abs(position - target) < REST_TOLERANCE) return;
  if (target < 0 || target >= totalPositions) return;
  const nearest = target;

  const token = beginNav();
  _recordMoveTarget(token, nearest);
  const seconds = timeMove(position, nearest);
  lenis.scrollTo(nearest * _stepPx(), {
    duration: seconds,
    easing: (t) => 1 - Math.pow(1 - t, 3),  // ease-out cubic
    onComplete: () => {
      _stateLanding(token, nearest);
      endNav(token);
      writeHash();
    },
  });
}

/**
 * Where the reader is on the story, as a scroll position, for a relayout to
 * put them back on.
 *
 * A move still travelling is read as the place it is going: a press or a
 * button asked for that step, and a snap or a carry was already taking the
 * reader to it. A gesture still gliding is read as where the wheel sent it.
 * Otherwise it is the position the story last stated: the scroll handler
 * stops stating one as soon as the window and the layout disagree, so the
 * browser's clamp to the new window cannot move it, while a jump to a step by
 * its link states its own. A position within the rest tolerance of a step is
 * that step.
 *
 * @returns {{position: number, moving: boolean}}
 */
function _positionToKeep() {
  const px = _stepPx();
  let position = state.scrollPosition;
  let moving = false;
  if (lenis.isScrolling === 'smooth') {
    moving = true;
    if (navToken && moveTargetToken === navToken && moveTarget !== null) {
      position = moveTarget;
    } else if (state.isSnapping && Number.isInteger(snap.currentSnapIndex)) {
      position = snap.currentSnapIndex;
    } else {
      position = lenis.targetScroll / px;
    }
  }
  const rounded = Math.round(position);
  if (Math.abs(position - rounded) < REST_TOLERANCE) position = rounded;
  return { position: _clampPosition(position), moving };
}

/**
 * Lay the scroll surface out at a new step height, keeping the reader on the
 * step they were on.
 *
 * A step is one viewport tall, so an offset in pixels names a different step
 * once the height changes; the reader's place is carried across as a position
 * instead. The jump is immediate, which ends any move under way: Lenis stops
 * the animation without calling its completion, so what that completion would
 * have done — standing the move down, stating the step, writing the fragment —
 * is done here, in that order.
 *
 * @param {HTMLElement} surface - The scroll surface.
 * @param {number} height - The new viewport height, in px.
 */
function _remapToHeight(surface, height) {
  const { position, moving } = _positionToKeep();
  const enteredFrom = state.currentIndex;

  remapping = true;
  // Stop the move outright rather than trusting the jump to: Lenis skips a
  // jump to the offset it already holds, and would leave the move running on
  // to its old-layout offset. A scroll a panel or the post-snap dwell has
  // stopped has no move to end and stays stopped.
  if (moving && !lenis.isStopped) {
    lenis.stop();
    lenis.start();
  }
  state.scrollStepPx = height;
  surface.style.height = `${totalPositions * height}px`;
  lenis.resize();
  lenis.scrollTo(position * height, { immediate: true, force: true });
  remapping = false;
  registerSnapPoints(totalPositions);

  if (moving) {
    navToken = 0;
    navTarget = null;
    navTargetToken = 0;
    buttonMoveToken = 0;
    keyboardNavInFlight = false;
    state.isSnapping = false;
    if (Number.isInteger(position)) snap.currentSnapIndex = position;
  }

  lastPosition = position;
  updateScrollPosition(position);
  // Settles the cards at the kept position, and carries a gesture that was
  // stopped between steps on to the step it was heading for.
  armScrubEnd();
  // A move that landed while the window and the layout disagreed states its
  // step here, so the fragment is written here too.
  if (moving || state.currentIndex !== enteredFrom) writeHash();
}

/**
 * Register snap points at each viewport boundary.
 * @param {number} count - Total positions (intro + content steps).
 */
function registerSnapPoints(count) {
  snapRemovers.forEach(fn => fn());
  snapRemovers = [];
  for (let i = 0; i < count; i++) {
    snapRemovers.push(snap.add(i * _stepPx()));
  }
}

/**
 * Move to a step for a button tap (embed mode).
 *
 * Uses lenis.scrollTo so the same physics engine drives the animation, and the
 * cards, the intro, the step and the buttons follow the scroll as they do the
 * wheel. Programmatic navigation is not user scrubbing, so is-scrubbing is
 * never added: per-frame card interpolation stays inert and CSS transitions
 * animate the slide at full duration.
 *
 * A tap ends the post-snap dwell, as a key press does: the dwell holds back
 * the wheel's momentum, and a tap is a request of its own. A scroll stopped
 * for any other reason (an open panel) refuses the move, and nothing is left
 * in flight.
 *
 * @param {number} targetIndex - Target step index, or -1 for the intro.
 * @returns {boolean} Whether the move started.
 */
export function advanceToStep(targetIndex) {
  if (targetIndex < -1 || targetIndex >= state.steps.length) return false;

  // Use state.lenis (set during initScrollEngine) — allows test injection
  const lenisInstance = state.lenis || lenis;
  if (!lenisInstance) return false;

  _clearDwell();
  if (lenisInstance.isStopped || lenisInstance.isLocked) return false;

  const token = beginNav();
  buttonMoveToken = token;
  // A key press's move this replaces never completes, so its guard against
  // the scroll's own crossings would stay up for this move and after it.
  keyboardNavInFlight = false;
  navTarget = null;
  _recordMoveTarget(token, targetIndex + 1);
  const seconds = timeMove(lenisInstance.animatedScroll / _stepPx(), targetIndex + 1);
  endScrub({ carry: false });

  // +1 to account for intro at position 0
  const targetPx = (targetIndex + 1) * _stepPx();
  _endMoveHeldAt(lenisInstance, targetPx);
  lenisInstance.scrollTo(targetPx, {
    duration: seconds,
    easing: (t) => 1 - Math.pow(1 - t, 3),  // ease-out cubic
    onComplete: () => {
      _stateLanding(token, targetIndex + 1);
      if (buttonMoveToken === token) buttonMoveToken = 0;
      endNav(token);
      followEngine(state.currentIndex);
      writeHash();
    },
  });
  return true;
}

/**
 * The step a button tap moves on from: where the buttons' or the keyboard's
 * move in flight is going, or else the step the story is on (-1 the intro).
 *
 * @returns {number}
 */
export function buttonHeading() {
  const ownMove = navToken && (navToken === buttonMoveToken || navToken === navTargetToken);
  if (ownMove && moveTargetToken === navToken && moveTarget !== null) return moveTarget - 1;
  return state.currentIndex;
}

/**
 * Stop a move in flight that Lenis would leave running under a scrollTo to px.
 *
 * Lenis skips a scrollTo to the offset it holds as its target, calling the
 * completion at once, and a programmatic move holds as its target the offset
 * it has reached — before its first frame, the one it left. A tap, a key press
 * or a link back to that offset would report success while the earlier move
 * ran on to its own landing. Stopping the move leaves the scroll where it
 * stands, which is the offset asked for, and the frame Lenis emits on stopping
 * enters it.
 * A key press's guard against that frame is lowered first, since its move is
 * the one being ended.
 *
 * @param {Lenis} lenisInstance
 * @param {number} px - The offset about to be scrolled to.
 */
function _endMoveHeldAt(lenisInstance, px) {
  if (px !== lenisInstance.targetScroll || lenisInstance.isScrolling !== 'smooth') return;
  keyboardNavInFlight = false;
  lenisInstance.stop();
  lenisInstance.start();
}

/**
 * Jump the scroll to an offset for Back to Start or a contents link: every
 * move in flight is stood down, including one Lenis would leave running
 * because the jump is to the offset it holds as its target.
 *
 * @param {number} px
 */
export function jumpScrollTo(px) {
  standDownMoves();
  _endMoveHeldAt(state.lenis, px);
  state.lenis.scrollTo(px, { immediate: true, force: true });
}

/**
 * Whether the engine is driving a move: a keyboard or button move, a snap or a
 * carry. A fragment change on the step the story shows must still stand it down.
 *
 * @returns {boolean}
 */
export function isMoveInFlight() {
  return navToken !== 0 || keyboardNavInFlight || state.isSnapping === true;
}

/**
 * Stand down any move in flight, for a jump that replaces it: Back to Start or
 * a contents link. The jump stops Lenis's animation without
 * calling its completion, so what the completion would have cleared is
 * cleared here, before the jump's own scroll frame is read.
 */
function standDownMoves() {
  navToken = 0;
  navTarget = null;
  navTargetToken = 0;
  moveTarget = null;
  moveTargetToken = 0;
  buttonMoveToken = 0;
  keyboardNavInFlight = false;
  state.isSnapping = false;
}

/**
 * Stop a post-snap dwell, if one is running, and give Lenis back its input —
 * unless a panel has opened during the dwell and holds the scroll, as the
 * dwell's own timer leaves it.
 */
function _clearDwell() {
  dwellHeld = false;
  if (dwellTimer) {
    clearTimeout(dwellTimer);
    dwellTimer = null;
    if (!state.isPanelOpen) lenis.start();
  }
}

/**
 * Show the card a key press is moving to, before the scroll gets there.
 *
 * The target is a scroll position (intro=0, step0=1, step1=2…), so its step
 * index is target-1. Target 0 is the intro, which carries no card. The intro
 * zone's own restore is suppressed by keyboardNavInFlight for the whole
 * animation, so the restore runs here — the same call the scroll zone and the
 * Back to Start button make, so index, fragment and nav button end up where
 * those paths leave them.
 */
function _activateKeyboardTarget(target, direction) {
  const targetStep = target - 1;
  if (targetStep >= 0 && targetStep !== state.currentIndex) {
    _enterStep(targetStep, direction);
  } else if (targetStep < 0 && state.currentIndex >= 0) {
    _enterStep(-1, 'backward');
  }
}

/**
 * Put the story on a step the engine has reached, or is taking a key press
 * to: its card, the current step, the counter and the nav button, and in an
 * embed the previous/next buttons, which show only where the engine is.
 * -1 restores the intro.
 *
 * The card is marked scroll-driven so activateCard does not animate the
 * camera: lerpIiifPosition places the viewer frame by frame.
 *
 * @param {number} stepIndex - Step index, or -1 for the intro.
 * @param {'forward'|'backward'} direction
 */
function _enterStep(stepIndex, direction) {
  if (stepIndex < 0) {
    goToStep(-1, 'backward');
  } else {
    state.scrollDriven = true;
    activateCard(stepIndex, direction);
    state.scrollDriven = false;
    state.currentIndex = stepIndex;
    updateViewerInfo(stepIndex);
    if (state.onStepChange) state.onStepChange(stepIndex);
  }
  followEngine(stepIndex);
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
 * The animated scroll drives lerpIiifPosition every frame for the IIIF
 * pan and zoom, over the duration the camera travel asks for (timeMove).
 * activateCard runs with scrollDriven=true so the plate does not move the
 * viewer a second time (the lerp already positions it).
 *
 * @param {'forward'|'backward'} direction
 */
export function keyboardNav(direction) {
  if (!lenis) return;

  // The move begins here, not at the scroll that ends it. Ending scrubbing and
  // clearing the dwell below both call into Lenis, which emits a scroll frame
  // of its own as it starts again — and a frame arriving while the scroll still
  // looks like the reader's arms the settle, which then fires part way through
  // this move and states a position the move has already left behind.

  // Read before beginNav takes a token of its own, which would drop it.
  const inFlight = navTargetToken === navToken ? navTarget : null;

  // A press that cannot take an in-flight move any further leaves it running,
  // and returns before anything below is touched. Restarting it would settle
  // its cards a second time — a transform written over a transition running
  // towards it restarts that transition from wherever it has reached — and
  // would orphan the token its completion clears.
  if (inFlight !== null &&
      _clampPosition(inFlight + (direction === 'forward' ? 1 : -1)) === inFlight) {
    return;
  }

  const token = beginNav();
  navTargetToken = token;

  // The keyboard is not the reader's scroll: end scrubbing if it is still on so the
  // move animates on the CSS transitions rather than being written per frame,
  // and without the carry — this move already knows where it is going, so a
  // carry to the nearer step would put two moves on one scroll. Nor the settle:
  // the landing is stated below, and in a burst the scroll is several steps
  // behind it, so a settle at the scroll's position places every card between
  // the two for a step the story is leaving, where nothing later reaches them.
  endScrub({ carry: false, settle: false });

  // Clear any active dwell — keyboard overrides scroll dwell
  _clearDwell();

  const vh = _stepPx();
  const position = lenis.animatedScroll / vh;
  const isExact = Math.abs(position - Math.round(position)) < 0.01;
  const rounded = Math.round(position);

  const target = _clampPosition(keyboardTarget(direction, inFlight, position));
  if (inFlight === null && target === rounded && isExact) {
    endNav(token);   // nothing to move; the scroll is the reader's again
    return;
  }

  // Where the next press steps from, for as long as this move owns the token.
  navTarget = target;
  _recordMoveTarget(token, target);

  // Timed from where the scroll is, so a press during a move is given the
  // travel still ahead of it: the rest of the step in flight and the next.
  const seconds = timeMove(position, target);

  // State the target before the scroll starts for it: the keyboard knows its
  // landing, so the cards can slide to it on their own transitions over the
  // same move, whatever scrubbing left half-placed on the way in. Both directions
  // go through it — a backward move's departing card is the card the target
  // position puts a viewport down.
  settleCards(target);

  // Sync snap.currentSnapIndex so wheel-triggered snaps stay aligned
  snap.currentSnapIndex = target;

  // Activate card immediately so it swaps on keypress — the IIIF lerp
  // then runs during the scroll animation for simultaneous effect.
  _activateKeyboardTarget(target, direction);

  // Suppress the activateCard guard in updateScrollPosition while Lenis
  // animates toward the target — otherwise the first scroll frame sees
  // the old stepIndex and fires activateCard(oldStep, 'backward'),
  // undoing the immediate activation above.
  keyboardNavInFlight = true;

  _endMoveHeldAt(lenis, target * vh);
  lenis.scrollTo(target * vh, {
    force: true,
    duration: seconds,
    easing: (t) => 1 - Math.pow(1 - t, 3),  // ease-out cubic
    onComplete: () => {
      // Only the move still current may stand itself down. Lenis calls this
      // straight away for a scrollTo whose target it is already holding, so a
      // superseded move can reach here while a later one is still travelling.
      _stateLanding(token, target);
      if (navToken === token) {
        keyboardNavInFlight = false;
        navTarget = null;
      }
      endNav(token);
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
      _enterStep(-1, 'backward');
    }

    // The first card and the first viewer plate slide up over the intro in
    // proportion to the position, which is the settle's own intro branch —
    // the same writes, and the same place any other path states them.
    //
    // Except under the keyboard, which states its own landing and animates to
    // it on the cards' transitions. A move from the intro to any step past the
    // first passes through here, and settling these frames from the position
    // the scroll has reached would put the arriving card back at the foot of
    // the screen, a viewport below where the move has already sent it.
    if (!keyboardNavInFlight) settleCards(position);
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
  // Feed the filtered steps (state.stepsData) — stepIndex is a filtered-space
  // index (it drives state.stepToScene), so the unfiltered window.storyData
  // .steps would mis-index on stories that contain metadata rows.
  lerpIiifPosition(stepIndex, progress, state.stepsData);

  // Integer boundary crossings. Skipped during keyboard nav: keyboardNav()
  // already entered the step and the scroll position hasn't caught up yet.
  if (stepIndex !== state.currentIndex && !keyboardNavInFlight) {
    _enterStep(stepIndex, stepIndex > state.currentIndex ? 'forward' : 'backward');
  }
}
