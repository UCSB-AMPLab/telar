/**
 * Telar Story – Navigation
 *
 * This module handles how the user moves between story steps. There are three
 * navigation modes, chosen automatically based on viewport size and embed
 * status:
 *
 * - Desktop scroll: On viewports 768 px and wider (not embedded,
 *   not iOS), the scroll engine (scroll-engine.js) drives navigation via
 *   Lenis smooth scroll. Keyboard input is handled by initKeyboardNavigation.
 *
 * - Mobile buttons: On viewports narrower than 768 px, previous/next buttons
 *   appear at the bottom of the screen. Each tap advances one step with a
 *   short cooldown to prevent double-taps.
 *
 * - Embed buttons: When the page is loaded inside an iframe (detected by
 *   embed.js), the same button navigation is used regardless of viewport
 *   width, because iframe scroll events do not propagate reliably.
 *
 * Keyboard navigation works in all modes: arrow keys and Page Up/Down move
 * between steps, left/right arrows open and close panels, Space advances
 * (Shift+Space goes back), and Escape closes the current panel.
 *
 * All navigation is blocked when a panel is open (the "panel freeze" system
 * managed by panels.js). This prevents accidental step changes while the
 * user is reading panel content.
 *
 * @version v1.1.0
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
 * between steps via snap.next()/snap.previous() in desktop mode, or fall back
 * to nextStep/prevStep in mobile/embed mode. Panel keys open/close layers.
 * Escape closes panels.
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
    // Restore the intro card (backward from step 0)
    const intro = document.querySelector('.story-intro');
    if (intro) {
      intro.style.transition = 'transform 0.5s ease-out';
      intro.style.transform = 'translateY(0)';
    }
    // Slide step 0's text card back down
    const firstCard = state.textCards?.[0];
    if (firstCard) {
      firstCard.classList.remove('is-active', 'is-stacked');
      const rot  = parseFloat(firstCard.dataset.messinessRot  || 0);
      const offX = parseFloat(firstCard.dataset.messinessOffX || 0);
      const offY = parseFloat(firstCard.dataset.messinessOffY || 0);
      firstCard.style.transform = `translateY(100vh) rotate(${rot}deg) translate(${offX}px, ${offY}px)`;
    }
    // Slide first viewer plate back down
    const firstObject = window.storyData?.firstObject;
    if (firstObject && state.viewerPlates?.[firstObject]) {
      const plate = state.viewerPlates[firstObject];
      plate.style.transform = 'translateY(100%)';
      plate.classList.remove('is-active');
    }
    // Reset object run tracking
    state.currentObjectRun = { objectId: null, runPosition: 0 };
    // Hide step counter and credit overlay on intro
    updateViewerInfo(-1);
    const creditBadge = document.getElementById('object-credits-badge');
    if (creditBadge) creditBadge.classList.add('d-none');
    return;
  }

  // Card pool handles all visual transitions, viewer switching, and preloading
  activateCard(newIndex, direction);

  // Panel trigger data update
  updateViewerInfo(newIndex);
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
 * the screen. The mode parameter is only used in log messages.
 *
 * @param {string} mode - 'mobile' or 'embed' (for logging).
 */
export function initializeButtonNavigation(mode) {
  console.log(`Initializing ${mode} button navigation`);

  state.steps = Array.from(document.querySelectorAll('.story-step'));

  initializeLoadingShimmer();

  state.steps.forEach(step => {
    step.classList.remove('mobile-active');
  });

  if (state.steps.length > 0) {
    state.steps[0].classList.add('mobile-active');
    state.currentMobileStep = 0;
  }

  const buttons = createNavigationButtons();
  if (!buttons) return;

  state.mobileNavButtons = { prev: buttons.prev, next: buttons.next };

  buttons.prev.addEventListener('click', goToPreviousMobileStep);
  buttons.next.addEventListener('click', goToNextMobileStep);

  updateMobileButtonStates();

  console.log(`${mode.charAt(0).toUpperCase() + mode.slice(1)} navigation initialized with ${state.steps.length} steps`);
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
 * Mirrors the desktop goToStep(-1) handler: slides the first viewer plate
 * off-screen, restores the intro card, and hides the step counter.
 */
function _restoreMobileIntro() {
  if (state.mobileNavigationCooldown) return;

  state.mobileNavigationCooldown = true;
  setTimeout(() => { state.mobileNavigationCooldown = false; }, MOBILE_NAV_COOLDOWN);

  state.mobileInIntro = true;

  // Show intro card
  const intro = document.querySelector('.story-intro');
  if (intro) {
    intro.style.transition = 'transform 0.5s ease-out';
    intro.style.transform = 'translateY(0)';
  }

  // Slide step 0's text card off-screen
  const firstCard = state.textCards?.[0];
  if (firstCard) {
    firstCard.classList.remove('is-active', 'is-stacked');
    const rot  = parseFloat(firstCard.dataset.messinessRot  || 0);
    const offX = parseFloat(firstCard.dataset.messinessOffX || 0);
    const offY = parseFloat(firstCard.dataset.messinessOffY || 0);
    firstCard.style.transform = `translateY(100vh) rotate(${rot}deg) translate(${offX}px, ${offY}px)`;
  }

  // Slide first viewer plate off-screen
  const firstPlate = state.viewerPlates?.[0];
  if (firstPlate) {
    firstPlate.style.transform = 'translateY(100%)';
    firstPlate.classList.remove('is-active');
  }

  // Reset object run tracking
  state.currentObjectRun = { objectId: null, runPosition: 0 };

  // Hide step counter and credits
  updateViewerInfo(-1);
  const creditBadge = document.getElementById('object-credits-badge');
  if (creditBadge) creditBadge.classList.add('d-none');

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
    console.log('Mobile navigation on cooldown, ignoring tap');
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

  console.log(`Mobile navigation: ${state.currentMobileStep} → ${newIndex} (${direction})`);

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
 * Handle keyboard navigation and panel control.
 *
 * Arrow up/down navigate steps via snap.next()/snap.previous() when the
 * Lenis snap plugin is available (desktop), or fall back to nextStep/prevStep
 * in mobile/embed mode (state.snap is null). Arrow left/right open/close
 * panels. Escape closes the current panel. Space advances (Shift+Space goes
 * back).
 *
 * Auto-repeat key events are ignored — each physical key press advances
 * exactly one step.
 *
 * @param {KeyboardEvent} e
 */
function handleKeyboard(e) {
  // Ignore auto-repeat key events for story navigation — each key press = one
  // step only. Allow repeats when a panel is open so held arrow keys scroll.
  if (e.repeat && !state.isPanelOpen) return;

  switch (e.key) {
    case 'ArrowDown':
    case 'PageDown':
      if (state.isPanelOpen) {
        scrollOpenPanel(40);
        break;
      }
      e.preventDefault();
      if (!state.scrollLockActive) {
        if (state.lenis) {
          keyboardNav('forward');
        } else {
          nextStep();
        }
      }
      break;

    case 'ArrowUp':
    case 'PageUp':
      if (state.isPanelOpen) {
        scrollOpenPanel(-40);
        break;
      }
      e.preventDefault();
      if (!state.scrollLockActive) {
        if (state.lenis) {
          keyboardNav('backward');
        } else {
          prevStep();
        }
      }
      break;

    case 'ArrowRight':
      e.preventDefault();
      if (!state.isPanelOpen) {
        const stepForL1 = getCurrentStepData();
        const stepNumForL1 = getCurrentStepNumber();
        if (stepForL1 && stepHasLayer1Content(stepForL1)) {
          openPanel('layer1', stepNumForL1);
        }
      } else if (state.panelStack.length === 1 && state.panelStack[0]?.type === 'layer1') {
        const stepForL2 = getCurrentStepData();
        const stepNumForL2 = getCurrentStepNumber();
        if (stepForL2 && stepHasLayer2Content(stepForL2)) {
          openPanel('layer2', stepNumForL2);
        }
      }
      break;

    case 'ArrowLeft':
      e.preventDefault();
      if (state.isPanelOpen) {
        closeTopPanel();
      }
      break;

    case 'Escape':
      if (state.isPanelOpen) {
        e.preventDefault();
        closeTopPanel();
      }
      break;

    case ' ':
      if (state.isPanelOpen) {
        scrollOpenPanel(e.shiftKey ? -100 : 100);
        e.preventDefault();
        break;
      }
      e.preventDefault();
      if (!state.scrollLockActive) {
        if (e.shiftKey) {
          if (state.lenis) keyboardNav('backward'); else prevStep();
        } else {
          if (state.lenis) keyboardNav('forward'); else nextStep();
        }
      }
      break;
  }
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
