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
 * (Shift+Space goes back), Home goes to the intro and End to the last step,
 * and Escape closes the current panel. A side card that scrolls inside itself
 * (card-scroll.js) takes the story keys first, after an open panel: a line
 * for an arrow, a page for Page Up/Down and Space, its whole extent for Home
 * and End, and the key moves a step only once the card is at rest at its edge.
 *
 * state.currentIndex is the current step in every mode (-1 on the intro), and
 * everything that asks which step the reader is on reads it: the fragment,
 * the layer keys, the nav button. The scroll engine writes it wherever Lenis
 * runs. Where it does not (vertical layout, iPad), button navigation is the
 * only thing that moves the story and writes it through recordButtonStep.
 * state.currentMobileStep is the step the buttons last moved to. In embed
 * mode every move is the scroll engine's, the buttons' included, and the
 * buttons show only where the engine is: it hands them each step it puts the
 * story on (followEngine), so they carry on from wherever a link, a key or the
 * wheel left the reader, and a move refused or cut short leaves them right.
 *
 * All navigation is blocked when a panel is open (the "panel freeze" system
 * managed by panels.js). This prevents accidental step changes while the
 * user is reading panel content.
 *
 * @version v1.8.0
 */

import { state, MOBILE_NAV_COOLDOWN } from './state.js';
import { activateCard, releaseTitleCardsForIntro } from './card-pool.js';
import { advanceToStep, buttonHeading, keyboardNav } from './scroll-engine.js';
import { writeHash, navigateToIntro, navigateToStep } from './deep-link.js';
import { cardTakesKey } from './card-scroll.js';
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
 * Called by scroll-engine.js after Lenis is initialised, and by
 * initializeButtonNavigation. Embed mode calls both; the listener is one
 * function, so the second registration adds nothing. Arrow keys navigate
 * between steps through the scroll engine wherever Lenis runs, and through
 * the buttons' own moves where it does not. Panel keys open and close
 * layers, and Escape closes panels.
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
 * Five things go back: the intro card into view, step 0's text card, any
 * title card holding the screen and the first object's viewer plate off the
 * bottom of the screen, and the step chrome out of sight. A story whose
 * author gave it no intro card still passes through here, and each piece is
 * skipped where it is absent.
 */
function _restoreIntro() {
  _showIntroCard();
  _sendFirstTextCardOffScreen();
  releaseTitleCardsForIntro();
  _sendPlateOffScreen(state.viewerPlates?.[window.storyData?.firstObject]);

  state.currentObjectRun = { objectId: null, runPosition: 0 };
  _hideStepChrome();

  if (state.onStepChange) state.onStepChange(-1);
}

// ── Intro card ───────────────────────────────────────────────────────────────

/**
 * Bring the intro card back down into view.
 */
function _showIntroCard() {
  const intro = document.querySelector('.story-intro');
  if (!intro) return;

  intro.style.transition = 'transform var(--card-motion-duration) var(--card-motion-easing)';
  intro.style.transform = 'translateY(0)';
}

/**
 * Send step 0's text card off the bottom of the screen.
 *
 * The card carries its authored messiness — a rotation and a small offset —
 * in its transform, so the slide has to restate them or the card would snap
 * square on its way out. A story whose first step is a section has no text
 * card here at all; that first card is a title card, and
 * releaseTitleCardsForIntro sends it away instead.
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

  plate.container.style.transform = 'translateY(100%)';
  plate.container.classList.remove('is-active');
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
 * Record the step button navigation has put the story on, -1 for the intro.
 *
 * Where no scroll engine runs, this is the only writer of state.currentIndex,
 * and it tells the nav button, which the engine does on its own path. Where
 * the engine runs (embed), it writes both as the scroll reaches the step, and
 * this leaves them to it.
 *
 * @param {number} index - Step index, or -1 for the intro.
 */
export function recordButtonStep(index) {
  if (state.lenis) return;
  state.currentIndex = index;
  if (state.onStepChange) state.onStepChange(index);
}

/**
 * Put button navigation on a step it did not walk to: a deep link, or a jump
 * from within the story. That step's element is the one marked active, the
 * buttons are enabled for a step rather than the intro, and the step is
 * recorded as current.
 *
 * @param {number} index - Step index.
 */
export function jumpButtonsTo(index) {
  state.currentMobileStep = index;
  state.mobileInIntro = false;
  state.steps.forEach((step, i) => step.classList.toggle('mobile-active', i === index));
  updateMobileButtonStates();
  recordButtonStep(index);
}

/**
 * Put button navigation on the intro, in the state a first load leaves it in:
 * step 0 is the step "next" leaves the intro for, and "previous" is disabled
 * because there is nothing before the intro. A story with no buttons has
 * nothing to put back.
 */
export function putButtonsOnIntro() {
  if (!state.mobileNavButtons) return;
  state.mobileInIntro = true;
  state.currentMobileStep = 0;
  state.steps.forEach((step, i) => step.classList.toggle('mobile-active', i === 0));
  updateMobileButtonStates();
}

/**
 * Put the buttons on the step the scroll engine has put the story on, -1 for
 * the intro.
 *
 * Only an embed has both. The engine calls this for every step it reaches,
 * whatever started the move, so the next tap goes on from where the reader is
 * and the buttons are disabled for that step. Without buttons (the desktop
 * scroll engine) there is nothing to move.
 *
 * @param {number} index - Step index, or -1 for the intro.
 */
export function followEngine(index) {
  if (!state.mobileNavButtons) return;
  if (index < 0) {
    putButtonsOnIntro();
  } else {
    jumpButtonsTo(index);
  }
}

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
  // The intro's hint is chosen in CSS from this marker, so it has to be set
  // wherever the buttons are the navigation, whatever the layout.
  document.documentElement.dataset.navigation = 'buttons';
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
  initKeyboardNavigation();
}

/**
 * Navigate to the next step (mobile/embed).
 */
function goToNextMobileStep() {
  if (state.lenis) {
    _moveThroughEngine(buttonHeading() + 1);
    return;
  }
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
  if (state.lenis) {
    _moveThroughEngine(buttonHeading() - 1);
    return;
  }
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

  _showIntroCard();
  _sendFirstTextCardOffScreen();
  _sendPlateOffScreen(state.viewerPlates?.[0]);

  state.currentObjectRun = { objectId: null, runPosition: 0 };
  _hideStepChrome();

  putButtonsOnIntro();
  recordButtonStep(-1);
  writeHash();
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
    intro.style.transition = 'transform var(--card-motion-duration) var(--card-motion-easing)';
    intro.style.transform = 'translateY(-100%)';
  }

  // Activate step 0
  state.currentMobileStep = 0;
  activateCard(0, 'forward');
  updateViewerInfo(0);
  updateMobileButtonStates();
  recordButtonStep(0);
  writeHash();
}

/**
 * Move the story by a button tap in embed mode, where the scroll engine
 * carries every move: the cards, the intro, the fragment and the buttons
 * follow its scroll as they do a key press or the wheel. The target is taken
 * from where the engine is going, so a second tap during a move goes on from
 * that move's landing.
 *
 * Nothing here says where the reader is. The counter, the current step and
 * the buttons are the scroll's to write as it reaches the step; a tap that
 * wrote them first would leave them wrong whenever the move is refused or cut
 * short, and would show the count going forwards, back and forwards again on
 * a second tap.
 *
 * @param {number} newIndex - Target step index, or -1 for the intro.
 */
function _moveThroughEngine(newIndex) {
  if (newIndex < -1 || newIndex >= state.steps.length) return;
  if (state.mobileNavigationCooldown) return;
  if (!advanceToStep(newIndex)) return;

  state.mobileNavigationCooldown = true;
  setTimeout(() => { state.mobileNavigationCooldown = false; }, MOBILE_NAV_COOLDOWN);

  if (newIndex >= 0) {
    const plate = state.viewerPlates[state.stepToScene[newIndex]];
    if (!plate || !plate.isReady) showViewerSkeletonState();
  }
}

/**
 * Navigate to a specific step where no scroll engine runs (phones, iPads).
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
  // Keyed by scene: an object appearing in several scenes has a plate for
  // each, and asking by objectId answers for whichever was built first.
  const plate = state.viewerPlates[state.stepToScene[newIndex]];

  if (!plate || !plate.isReady) {
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

  // No scroll engine, so no per-frame writer: this path moves the card itself
  // and is the only thing that can state where the reader now is.
  activateCard(newIndex, direction);
  updateViewerInfo(newIndex);
  recordButtonStep(newIndex);

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
 * itself and nothing inherited can answer for it. Page Down and Page Up move
 * a step as the arrow keys do, and differ only in how far they scroll a side
 * card that scrolls inside itself; every other key the story reads has an
 * action of its own.
 *
 * @type {Map<string, (e: KeyboardEvent) => void>}
 */
const KEY_ACTIONS = new Map([
  ['ArrowDown',  (e) => _stepKey(e, 'forward', 'line')],
  ['PageDown',   (e) => _stepKey(e, 'forward', 'page')],
  ['ArrowUp',    (e) => _stepKey(e, 'backward', 'line')],
  ['PageUp',     (e) => _stepKey(e, 'backward', 'page')],
  ['ArrowRight', (e) => _rightKey(e)],
  ['ArrowLeft',  (e) => _leftKey(e)],
  ['Escape',     (e) => _escapeKey(e)],
  [' ',          (e) => _spaceKey(e)],
  ['Home',       (e) => _edgeKey(e, 'start')],
  ['End',        (e) => _edgeKey(e, 'end')],
]);

/**
 * The direction and reach of a story key, or null for any other key.
 *
 * @type {Map<string, ['forward'|'backward', 'line'|'page']>}
 */
const STORY_KEYS = new Map([
  ['ArrowDown', ['forward', 'line']],
  ['PageDown',  ['forward', 'page']],
  ['ArrowUp',   ['backward', 'line']],
  ['PageUp',    ['backward', 'page']],
]);

/**
 * The keys that go to an end of the story, with the direction and reach they
 * ask a side card for.
 *
 * @type {Map<string, ['forward'|'backward', 'full']>}
 */
const EDGE_KEYS = new Map([
  ['Home', ['backward', 'full']],
  ['End',  ['forward', 'full']],
]);

/**
 * Handle keyboard navigation and panel control.
 *
 * Auto-repeat key events never step the story — each physical key press
 * advances exactly one step — but allowed through while a panel is open, so
 * that a held arrow key keeps the panel scrolling. Outside a panel a repeated
 * story key is cancelled, so the browser does not scroll the document under
 * Lenis, unless it comes from a control or an open dialog, which keep it. Over
 * a side card that scrolls inside itself a repeat also scrolls the card, to
 * its end and no further. Home and End go to the intro and the last step on
 * the first press; their repeats are cancelled and take no step. Every key this
 * reads is left to an open dialog when it comes from inside one: the step
 * keys, Space, Home and End, ArrowLeft, ArrowRight and Escape.
 *
 * @param {KeyboardEvent} e
 */
function handleKeyboard(e) {
  if (e.repeat && !state.isPanelOpen) {
    _repeatKey(e);
    return;
  }

  KEY_ACTIONS.get(e.key)?.(e);
}

/**
 * Cancel an auto-repeated story key, and give it to a side card that scrolls
 * inside itself.
 *
 * The browser scrolls the document for every one of these keys, and a story's
 * position belongs to the scroll engine, so a repeat that reaches the browser
 * moves the page by an amount no step accounts for. A repeat from inside an
 * open dialog, or of Space from a control Space activates, is that element's
 * own and is left alone. A field outside a dialog is not exempt: at its edge a
 * held arrow or Page key passes to the document and scrolls it, and a story
 * page's fields all sit in the Share dialog.
 *
 * @param {KeyboardEvent} e
 */
function _repeatKey(e) {
  if (_isInOpenDialog(e)) return;
  if (e.key === ' ' && _isSpaceControl(e)) return;
  if (EDGE_KEYS.has(e.key)) {
    e.preventDefault();
    cardTakesKey(...EDGE_KEYS.get(e.key));
    return;
  }

  let motion = STORY_KEYS.get(e.key);
  if (e.key === ' ') motion = [e.shiftKey ? 'backward' : 'forward', 'page'];
  if (!motion) return;
  e.preventDefault();
  cardTakesKey(...motion);
}

/**
 * Move one step, or scroll the open panel or the side card instead.
 *
 * A panel takes the key first, and the event stays uncancelled in that
 * state so that a panel too long for its own scrolling still gets the
 * browser's. With no panel open the key belongs to the story and is
 * cancelled whether or not a scroll lock lets the step through; from inside
 * an open dialog the key is the dialog's and is left uncancelled; a side card
 * that scrolls inside itself takes it before the step, until it is at rest
 * at its edge.
 *
 * @param {KeyboardEvent} e
 * @param {string} direction - 'forward' or 'backward'.
 * @param {'line'|'page'} kind - How far the key scrolls a side card.
 */
function _stepKey(e, direction, kind) {
  if (_isInOpenDialog(e)) return;
  if (_panelTookScroll(direction === 'forward' ? 40 : -40)) return;

  e.preventDefault();
  if (cardTakesKey(direction, kind) === 'scrolled') return;
  _navigateStep(direction);
}

/**
 * Open the next layer panel on ArrowRight.
 *
 * From inside an open dialog the key is the dialog's, to move a caret or an
 * option, and is left uncancelled with no panel opened behind it.
 *
 * @param {KeyboardEvent} e
 */
function _rightKey(e) {
  if (_isInOpenDialog(e)) return;

  e.preventDefault();
  _openNextLayer();
}

/**
 * Close the topmost panel on ArrowLeft.
 *
 * From inside an open dialog the key is the dialog's, to move a caret or an
 * option, and is left uncancelled with no panel closed behind it.
 *
 * @param {KeyboardEvent} e
 */
function _leftKey(e) {
  if (_isInOpenDialog(e)) return;

  e.preventDefault();
  _closeTopmostPanel(e);
}

/**
 * Close the topmost panel on Escape.
 *
 * The Share dialog can be opened over an open panel, which stays open under
 * it. Escape from inside the dialog closes the dialog alone, so the key is
 * left to the dialog and the panel behind it is not closed.
 *
 * @param {KeyboardEvent} e
 */
function _escapeKey(e) {
  if (_isInOpenDialog(e)) return;

  _closeTopmostPanel(e);
}

/**
 * Selector for elements that act on Space themselves. A link is not one:
 * Space on a link scrolls the page, which in a story is a step.
 *
 * @type {string}
 */
const SPACE_CONTROLS =
  'button, summary, [role="button"], input, select, textarea, [contenteditable]:not([contenteditable="false"])';

/**
 * Whether the key event came from a control that Space activates.
 *
 * @param {KeyboardEvent} e
 * @returns {boolean}
 */
function _isSpaceControl(e) {
  const target = e.target;
  return !!(target && target.closest && target.closest(SPACE_CONTROLS));
}

/**
 * Whether the key event came from inside a modal dialog, which reads the arrow
 * keys itself and sits over the story without opening a panel.
 *
 * The dialog counts while it closes: Escape hides it before the key reaches
 * the document, so a test for `.show` would pass the key on to the story.
 *
 * @param {KeyboardEvent} e
 * @returns {boolean}
 */
function _isInOpenDialog(e) {
  const target = e.target;
  return !!(target && target.closest && target.closest('.modal, dialog[open]'));
}

/**
 * Go to the intro (Home) or the last step (End), by the moves Back to Start
 * and a contents link make, and cancel the browser's own jump, which would
 * scroll the document under the scroll engine.
 *
 * An open panel and an open dialog keep the key, uncancelled. A scroll lock
 * holds the story where it is, so the key is cancelled and moves nothing. A
 * side card that scrolls inside itself takes the key first, to its own top or
 * end, and the story moves only once the card is at rest at that edge.
 *
 * @param {KeyboardEvent} e
 * @param {'start'|'end'} edge
 */
function _edgeKey(e, edge) {
  if (state.isPanelOpen || _isInOpenDialog(e)) return;

  e.preventDefault();
  if (state.scrollLockActive) return;
  if (cardTakesKey(edge === 'start' ? 'backward' : 'forward', 'full') === 'scrolled') return;

  if (edge === 'start') {
    navigateToIntro();
  } else {
    navigateToStep(state.steps.length);
  }
}

/**
 * Page through the story, or through the open panel or the side card instead.
 *
 * Space carries the page's own scrolling, so it is cancelled in both states.
 * Shift reverses it. On a focused control the key belongs to the control and
 * is left to the browser, uncancelled, with no step moved; so is it inside an
 * open dialog. A side card that
 * scrolls inside itself takes a page after an open panel and before the step.
 *
 * @param {KeyboardEvent} e
 */
function _spaceKey(e) {
  if (_isSpaceControl(e) || _isInOpenDialog(e)) return;

  e.preventDefault();
  if (_panelTookScroll(e.shiftKey ? -100 : 100)) return;

  const direction = e.shiftKey ? 'backward' : 'forward';
  if (cardTakesKey(direction, 'page') === 'scrolled') return;
  _navigateStep(direction);
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
 * The scroll engine drives the move wherever Lenis is running. Where it is
 * not, the key makes the same move as the matching button, so the buttons,
 * the intro and the fragment follow it. A scroll lock — an interactive card
 * holding the viewport — blocks both.
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
    goToNextMobileStep();
  } else {
    goToPreviousMobileStep();
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
