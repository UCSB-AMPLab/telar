/**
 * Telar Story – Navigation
 *
 * This module handles how the user moves between story steps. There are three
 * navigation modes, chosen automatically based on layout mode and embed
 * status:
 *
 * - Desktop scroll: In horizontal layout (not embedded, not iOS), the
 *   scroll engine (scroll-engine.js) drives navigation via Lenis smooth
 *   scroll. Keyboard input is handled by initKeyboardNavigation.
 *
 * - Mobile buttons: In vertical layout, previous/next buttons appear at
 *   the bottom of the screen. Each tap advances one step with a short
 *   cooldown to prevent double-taps.
 *
 * - Embed buttons: When the page is loaded inside an iframe (detected by
 *   embed.js), the same button navigation is used regardless of layout
 *   mode, because iframe scroll events do not propagate reliably.
 *
 * The horizontal/vertical layout threshold is not hardcoded here — it lives
 * in _responsive.scss ($telar-vertical-min-width, $telar-vertical-min-aspect)
 * and is read at runtime by layout-mode.js.
 *
 * Keyboard navigation works in all modes: arrow keys and Page Up/Down move
 * between steps, left/right arrows open and close panels, Space advances
 * (Shift+Space goes back), and Escape closes the current panel.
 *
 * All navigation is blocked when a panel is open (the "panel freeze" system
 * managed by panels.js). This prevents accidental step changes while the
 * user is reading panel content.
 *
 * @version v1.7.0
 */

import { state, MOBILE_NAV_COOLDOWN } from './state.js';
import { activateCard } from './card-pool.js';
import { advanceToStep, keyboardNav } from './scroll-engine.js';
import { writeHash } from './deep-link.js';
import { initializeLoadingShimmer, showViewerSkeletonState } from './viewer.js';
import {
  openPanel,
  closeTopPanel,
  stepHasLayer1Content,
  stepHasLayer2Content,
} from './panels.js';

// ── Keyboard navigation ────────────────────────────────────────────────────────

/**
 * Register keyboard event listener for step and panel navigation.
 *
 * Called by scroll-engine.js after Lenis is initialised. Arrow keys navigate
 * between steps through the scroll engine in desktop mode, and through
 * nextStep/prevStep in mobile/embed mode, where there is no Lenis. Panel keys
 * open and close layers, and Escape closes panels.
 */
export function initKeyboardNavigation() {
  document.addEventListener('keydown', handleKeyboard);
}

/**
 * Navigate to a specific step.
 *
 * Delegates all visual transitions to the card pool (activateCard), which
 * handles viewer plate switching, text card sliding, and preloading based
 * on whether the object has changed and whether the zoom mode changed.
 *
 * @param {number} newIndex - Target step index.
 * @param {string} [direction='forward'] - 'forward' or 'backward'.
 */
export function goToStep(newIndex, direction = 'forward') {
  // Allow -1 for intro restoration on backward navigation
  if (newIndex < -1 || newIndex >= state.steps.length) return;

  state.currentIndex = newIndex;

  if (newIndex === -1) {
    _restoreIntro();
    return;
  }

  // Card pool handles all visual transitions, viewer switching, and preloading
  activateCard(newIndex, direction);

  // Panel trigger data update
  updateViewerInfo(newIndex);
  if (state.onStepChange) state.onStepChange(newIndex);
}

/**
 * Restore the intro, the state that sits before step 0.
 *
 * Four things go back: the intro card into view, step 0's text card and the
 * first object's viewer plate off the bottom of the screen, and the step
 * chrome out of sight. A story whose author gave it no intro card still
 * passes through here, and each piece is skipped where it is absent.
 */
function _restoreIntro() {
  _showIntroCard();
  _sendFirstTextCardOffScreen();
  _sendPlateOffScreen(state.viewerPlates?.[window.storyData?.firstObject]);

  state.currentObjectRun = { objectId: null, runPosition: 0 };
  _hideStepChrome();

  if (state.onStepChange) state.onStepChange(-1);
}

/**
 * Navigate to the next step.
 */
export function nextStep() {
  goToStep(state.currentIndex + 1, 'forward');
}

/**
 * Navigate to the previous step.
 */
export function prevStep() {
  goToStep(state.currentIndex - 1, 'backward');
}

// ── Intro card ───────────────────────────────────────────────────────────────

/**
 * Bring the intro card back down into view.
 */
function _showIntroCard() {
  const intro = document.querySelector('.story-intro');
  if (!intro) return;

  intro.style.transition = 'transform 0.5s ease-out';
  intro.style.transform = 'translateY(0)';
}

/**
 * Send step 0's text card off the bottom of the screen.
 *
 * The card carries its authored messiness — a rotation and a small offset —
 * in its transform, so the slide has to restate them or the card would snap
 * square on its way out.
 */
function _sendFirstTextCardOffScreen() {
  const firstCard = state.textCards?.[0];
  if (!firstCard) return;

  firstCard.classList.remove('is-active', 'is-stacked');
  const rot  = parseFloat(firstCard.dataset.messinessRot  || 0);
  const offX = parseFloat(firstCard.dataset.messinessOffX || 0);
  const offY = parseFloat(firstCard.dataset.messinessOffY || 0);
  firstCard.style.transform = `translateY(100vh) rotate(${rot}deg) translate(${offX}px, ${offY}px)`;
}

/**
 * Send a viewer plate off the bottom of the screen.
 *
 * @param {HTMLElement} [plate] - The plate, where the story has one.
 */
function _sendPlateOffScreen(plate) {
  if (!plate) return;

  plate.style.transform = 'translateY(100%)';
  plate.classList.remove('is-active');
}

/**
 * Hide what belongs to a story step rather than to the intro: the step
 * counter and the object credit badge.
 */
function _hideStepChrome() {
  updateViewerInfo(-1);

  const creditBadge = document.getElementById('object-credits-badge');
  if (creditBadge) creditBadge.classList.add('d-none');
}

// ── Button navigation (mobile + embed) ───────────────────────────────────────

/**
 * Create the previous/next navigation button elements.
 *
 * Returns null if buttons already exist (prevents duplicate initialisation).
 *
 * @returns {{ container: HTMLElement, prev: HTMLElement, next: HTMLElement }|null}
 */
function createNavigationButtons() {
  if (document.querySelector('.mobile-nav')) {
    console.warn('Navigation buttons already exist, skipping creation');
    return null;
  }

  const navContainer = document.createElement('div');
  navContainer.className = 'mobile-nav';

  const prevButton = document.createElement('button');
  prevButton.className = 'mobile-prev';
  prevButton.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" height="32" viewBox="0 -960 960 960" width="32" fill="currentColor"><path d="M440-160v-487L216-423l-56-57 320-320 320 320-56 57-224-224v487h-80Z"/></svg>';
  prevButton.setAttribute('aria-label', 'Previous step');

  const nextButton = document.createElement('button');
  nextButton.className = 'mobile-next';
  nextButton.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" height="32" viewBox="0 -960 960 960" width="32" fill="currentColor"><path d="M440-800v487L216-537l-56 57 320 320 320-320-56-57-224 224v-487h-80Z"/></svg>';
  nextButton.setAttribute('aria-label', 'Next step');

  navContainer.appendChild(prevButton);
  navContainer.appendChild(nextButton);
  document.body.appendChild(navContainer);

  return { container: navContainer, prev: prevButton, next: nextButton };
}

/**
 * Set up button-based navigation for mobile or embed mode.
 *
 * Both modes use identical logic — previous/next buttons at the bottom of
 * the screen.
 */
export function initializeButtonNavigation() {
  state.steps = Array.from(document.querySelectorAll('.story-step'));

  initializeLoadingShimmer();

  state.steps.forEach(step => {
    step.classList.remove('mobile-active');
  });

  if (state.steps.length > 0) {
    state.steps[0].classList.add('mobile-active');
    state.currentMobileStep = 0;
  }

  // The story boots on the intro card, so button navigation starts there:
  // the first "next" dismisses the intro into step 0, and "prev" stays
  // disabled until the intro is dismissed.
  state.mobileInIntro = !!document.querySelector('.story-intro');

  const buttons = createNavigationButtons();
  if (!buttons) return;

  state.mobileNavButtons = { prev: buttons.prev, next: buttons.next };

  buttons.prev.addEventListener('click', goToPreviousMobileStep);
  buttons.next.addEventListener('click', goToNextMobileStep);

  updateMobileButtonStates();
}

/**
 * Navigate to the next step (mobile/embed).
 */
function goToNextMobileStep() {
  // From intro state → step 0
  if (state.mobileInIntro) {
    _dismissMobileIntro();
    return;
  }
  if (state.currentMobileStep >= state.steps.length - 1) {
    return;
  }
  goToMobileStep(state.currentMobileStep + 1);
}

/**
 * Navigate to the previous step (mobile/embed).
 */
function goToPreviousMobileStep() {
  if (state.mobileInIntro) {
    return;
  }
  // From step 0 → intro state
  if (state.currentMobileStep === 0) {
    _restoreMobileIntro();
    return;
  }
  goToMobileStep(state.currentMobileStep - 1);
}

/**
 * Restore the intro card on mobile (backward from step 0).
 *
 * The same four pieces the desktop intro restoration moves, plus the two
 * things button navigation owns: the tap cooldown, and the button states
 * that keep "previous" disabled on the intro. The plate is taken by
 * position rather than by object id, because button navigation tracks steps
 * and not object runs.
 */
function _restoreMobileIntro() {
  if (state.mobileNavigationCooldown) return;

  state.mobileNavigationCooldown = true;
  setTimeout(() => { state.mobileNavigationCooldown = false; }, MOBILE_NAV_COOLDOWN);

  state.mobileInIntro = true;

  _showIntroCard();
  _sendFirstTextCardOffScreen();
  _sendPlateOffScreen(state.viewerPlates?.[0]);

  state.currentObjectRun = { objectId: null, runPosition: 0 };
  _hideStepChrome();

  updateMobileButtonStates();
}

/**
 * Dismiss the intro card and show step 0 (forward from intro).
 */
function _dismissMobileIntro() {
  if (state.mobileNavigationCooldown) return;

  state.mobileNavigationCooldown = true;
  setTimeout(() => { state.mobileNavigationCooldown = false; }, MOBILE_NAV_COOLDOWN);

  state.mobileInIntro = false;

  // Hide intro card
  const intro = document.querySelector('.story-intro');
  if (intro) {
    intro.style.transition = 'transform 0.5s ease-out';
    intro.style.transform = 'translateY(-100%)';
  }

  // Activate step 0
  state.currentMobileStep = 0;
  activateCard(0, 'forward');
  updateViewerInfo(0);
  updateMobileButtonStates();
}

/**
 * Navigate to a specific step (mobile/embed).
 *
 * Handles cooldown, skeleton loading states, step class toggling,
 * and card pool activation.
 *
 * @param {number} newIndex - Target step index.
 */
function goToMobileStep(newIndex) {
  if (newIndex < 0 || newIndex >= state.steps.length) {
    return;
  }

  // Cooldown to prevent rapid tapping
  if (state.mobileNavigationCooldown) {
    return;
  }

  // Check if viewer needs loading
  const newStep = state.steps[newIndex];
  const objectId = newStep.dataset.object;
  const viewerCard = state.viewerCards.find(vc => vc.objectId === objectId);

  if (!viewerCard || !viewerCard.isReady) {
    showViewerSkeletonState();
  }

  // Activate cooldown
  state.mobileNavigationCooldown = true;
  setTimeout(() => {
    state.mobileNavigationCooldown = false;
  }, MOBILE_NAV_COOLDOWN);

  const direction = newIndex > state.currentMobileStep ? 'forward' : 'backward';

  // Swap step visibility
  state.steps[state.currentMobileStep].classList.remove('mobile-active');
  state.steps[newIndex].classList.add('mobile-active');
  state.currentMobileStep = newIndex;

  updateMobileButtonStates();

  // If Lenis is available, use animated scroll
  // transition through the scroll engine. Otherwise fall back to direct
  // activateCard with CSS transition (mobile/iOS without Lenis).
  if (state.lenis) {
    advanceToStep(newIndex);
  } else {
    activateCard(newIndex, direction);
  }

  updateViewerInfo(newIndex);
  writeHash();
}

/**
 * Update mobile button enabled/disabled states at step boundaries.
 */
function updateMobileButtonStates() {
  if (!state.mobileNavButtons) return;
  state.mobileNavButtons.prev.disabled = !!state.mobileInIntro;
  state.mobileNavButtons.next.disabled = (state.currentMobileStep === state.steps.length - 1);
}

// ── Keyboard input ─────────────────────────────────────────────────────────

/**
 * What each navigation key does.
 *
 * A Map rather than an object literal, so that a key value is looked up as
 * itself and nothing inherited can answer for it. Page Down and Page Up are
 * the arrow keys under another name; every other key the story reads has an
 * action of its own.
 *
 * @type {Map<string, (e: KeyboardEvent) => void>}
 */
const KEY_ACTIONS = new Map([
  ['ArrowDown',  (e) => _stepKey(e, 'forward')],
  ['PageDown',   (e) => _stepKey(e, 'forward')],
  ['ArrowUp',    (e) => _stepKey(e, 'backward')],
  ['PageUp',     (e) => _stepKey(e, 'backward')],
  ['ArrowRight', (e) => { e.preventDefault(); _openNextLayer(); }],
  ['ArrowLeft',  (e) => { e.preventDefault(); _closeTopmostPanel(e); }],
  ['Escape',     (e) => _closeTopmostPanel(e)],
  [' ',          (e) => _spaceKey(e)],
]);

/**
 * Handle keyboard navigation and panel control.
 *
 * Auto-repeat key events are ignored for story navigation — each physical key
 * press advances exactly one step — but allowed through while a panel is
 * open, so that a held arrow key keeps the panel scrolling.
 *
 * @param {KeyboardEvent} e
 */
function handleKeyboard(e) {
  if (e.repeat && !state.isPanelOpen) return;

  KEY_ACTIONS.get(e.key)?.(e);
}

/**
 * Move one step, or scroll the open panel instead.
 *
 * A panel takes the key first, and the event stays uncancelled in that
 * state so that a panel too long for its own scrolling still gets the
 * browser's. With no panel open the key belongs to the story and is
 * cancelled whether or not a scroll lock lets the step through.
 *
 * @param {KeyboardEvent} e
 * @param {string} direction - 'forward' or 'backward'.
 */
function _stepKey(e, direction) {
  if (_panelTookScroll(direction === 'forward' ? 40 : -40)) return;

  e.preventDefault();
  _navigateStep(direction);
}

/**
 * Page through the story, or through the open panel instead.
 *
 * Space carries the page's own scrolling, so it is cancelled in both states.
 * Shift reverses it.
 *
 * @param {KeyboardEvent} e
 */
function _spaceKey(e) {
  e.preventDefault();
  if (_panelTookScroll(e.shiftKey ? -100 : 100)) return;

  _navigateStep(e.shiftKey ? 'backward' : 'forward');
}

/**
 * Give a scroll to the open panel, if there is one.
 *
 * @param {number} delta - Pixels to scroll (positive = down, negative = up).
 * @returns {boolean} Whether a panel took the scroll.
 */
function _panelTookScroll(delta) {
  if (!state.isPanelOpen) return false;

  scrollOpenPanel(delta);
  return true;
}

/**
 * Move one step in the given direction.
 *
 * The scroll engine drives the move wherever Lenis is running; mobile and
 * embed modes, which have no Lenis, move the card pool directly. A scroll
 * lock — an interactive card holding the viewport — blocks both.
 *
 * @param {string} direction - 'forward' or 'backward'.
 */
function _navigateStep(direction) {
  if (state.scrollLockActive) return;

  if (state.lenis) {
    keyboardNav(direction);
    return;
  }
  if (direction === 'forward') {
    nextStep();
  } else {
    prevStep();
  }
}

/**
 * Open the next layer of panels above what is already open.
 *
 * With nothing open that is layer 1; above a single open layer 1 it is
 * layer 2. Layer 2 is the top of the stack, so a deeper stack, or a stack
 * whose one panel is not a layer 1, opens nothing.
 */
function _openNextLayer() {
  if (!state.isPanelOpen) {
    _openLayerWithContent('layer1', stepHasLayer1Content);
    return;
  }
  if (state.panelStack.length === 1 && state.panelStack[0]?.type === 'layer1') {
    _openLayerWithContent('layer2', stepHasLayer2Content);
  }
}

/**
 * Open a panel layer for the current step, if that step has content for it.
 *
 * @param {string} type - Panel type ('layer1' or 'layer2').
 * @param {Function} hasContent - Content test for that layer, from panels.js.
 */
function _openLayerWithContent(type, hasContent) {
  const step = getCurrentStepData();
  const stepNumber = getCurrentStepNumber();
  if (step && hasContent(step)) {
    openPanel(type, stepNumber);
  }
}

/**
 * Close the topmost open panel.
 *
 * The event is cancelled only when there is a panel to close, which leaves
 * Escape to the page in every other state.
 *
 * @param {KeyboardEvent} e
 */
function _closeTopmostPanel(e) {
  if (!state.isPanelOpen) return;

  e.preventDefault();
  closeTopPanel();
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Scroll the topmost open panel's body by a given pixel delta.
 *
 * The Bootstrap Offcanvas root receives focus (tabindex="-1") but the
 * scrollable area is .offcanvas-body inside it. Native arrow keys on
 * the focused root don't propagate to the child, so we scroll it
 * programmatically.
 *
 * @param {number} delta - Pixels to scroll (positive = down, negative = up).
 */
function scrollOpenPanel(delta) {
  const top = state.panelStack[state.panelStack.length - 1];
  if (!top) return;
  const panel = document.getElementById(`panel-${top.type}`);
  const body = panel?.querySelector('.offcanvas-body');
  if (body) body.scrollBy({ top: delta, behavior: 'smooth' });
}

/**
 * Get the current step's number from its data attribute.
 *
 * @returns {string|null}
 */
function getCurrentStepNumber() {
  if (state.currentIndex < 0 || state.currentIndex >= state.steps.length) {
    return null;
  }
  return state.steps[state.currentIndex].dataset.step;
}

/**
 * Get the current step's data from the story data.
 *
 * @returns {Object|null}
 */
function getCurrentStepData() {
  const stepNumber = getCurrentStepNumber();
  if (!stepNumber) return null;
  const steps = window.storyData?.steps || [];
  return steps.find(s => s.step == stepNumber);
}

/**
 * Update the step number display in the viewer info overlay.
 *
 * @param {number} stepIndex - The step index to display.
 */
export function updateViewerInfo(stepIndex) {
  const counter = document.getElementById('step-counter');
  const infoElement = document.getElementById('current-object-title');
  if (!counter || !infoElement) return;

  // Hide on intro (index -1), show on all story steps
  if (stepIndex < 0) {
    counter.classList.add('d-none');
    return;
  }
  counter.classList.remove('d-none');

  const total = (window.storyData?.steps || []).filter(s => !s._metadata).length;
  const stepTemplate = window.telarLang.stepNumber || "Step {{ number }}";
  const display = stepTemplate.replace("{{ number }}", stepIndex + 1);
  infoElement.textContent = total > 0 ? `${display} / ${total}` : display;
}
