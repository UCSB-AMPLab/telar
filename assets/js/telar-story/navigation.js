/**
 * Telar Story – Navigation
 *
 * This module handles how the user moves between story steps. There are three
 * navigation modes, chosen automatically based on viewport size and embed
 * status:
 *
 * - Desktop scroll: On viewports 768 px and wider (not embedded), the user
 *   scrolls with a mouse wheel or trackpad. A custom scroll accumulator
 *   collects scroll distance until it crosses a threshold (50 % of viewport
 *   height), then advances or retreats one step. A cooldown prevents rapid
 *   changes during the step transition animation. iPad and tablet users in
 *   this viewport range navigate by swiping vertically.
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
 * @version v0.7.0-beta
 */

import { state, STEP_COOLDOWN, MAX_SCROLL_DELTA, MOBILE_NAV_COOLDOWN } from './state.js';
import {
  switchToObject,
  switchToObjectMobile,
  animateViewerToPosition,
  preloadNearbyViewers,
  initializeLoadingShimmer,
  showViewerSkeletonState,
} from './viewer.js';
import {
  openPanel,
  closeTopPanel,
  stepHasLayer1Content,
  stepHasLayer2Content,
} from './panels.js';

// ── Desktop scroll navigation ────────────────────────────────────────────────

/**
 * Set up desktop scroll-based navigation.
 *
 * Assigns z-index stacking to steps, activates the first step, and registers
 * event listeners for keyboard, wheel, and touch input.
 */
export function initializeStepController() {
  state.steps = Array.from(document.querySelectorAll('.story-step'));

  initializeLoadingShimmer();

  state.steps.forEach((step, index) => {
    step.style.zIndex = index + 1;
    step.dataset.stepIndex = index;
  });

  if (state.steps.length > 0) {
    goToStep(0, 'forward');
  }

  document.addEventListener('keydown', handleKeyboard);
  window.addEventListener('wheel', handleScroll, { passive: false });
  window.addEventListener('touchstart', handleTouchStart, { passive: true });
  window.addEventListener('touchend', handleTouchEnd, { passive: true });

  console.log(`Step controller initialized with ${state.steps.length} steps`);
}

/**
 * Navigate to a specific step (desktop).
 *
 * Handles intro slide transitions, direction-aware CSS class changes,
 * object switching or pan/zoom animation, and viewer preloading.
 *
 * @param {number} newIndex - Target step index.
 * @param {string} [direction='forward'] - 'forward' or 'backward'.
 */
export function goToStep(newIndex, direction = 'forward') {
  if (newIndex < 0) {
    console.log(`Cannot go to step ${newIndex}: already at first step (0)`);
    return;
  }
  if (newIndex >= state.steps.length) {
    console.log(`Cannot go to step ${newIndex}: already at last step (${state.steps.length - 1})`);
    return;
  }

  const oldIndex = state.currentIndex;
  const newStep = state.steps[newIndex];
  const oldStep = oldIndex >= 0 ? state.steps[oldIndex] : null;

  console.log(`goToStep: ${oldIndex} → ${newIndex} (${direction})`);

  state.lastStepChangeTime = Date.now();

  // Intro slide transitions
  if (oldIndex === 0 && newIndex > 0) {
    const intro = state.steps[0];
    if (intro.classList.contains('story-intro')) {
      intro.style.transform = 'translateY(-100%)';
      intro.style.zIndex = '0';
    }
  } else if (newIndex === 0 && oldIndex > 0) {
    const intro = state.steps[0];
    if (intro.classList.contains('story-intro')) {
      intro.style.zIndex = '100'; // Above other steps (1-11) but below fixed buttons (1040)
      intro.style.transform = 'translateY(0)';
    }
    state.currentViewerCard = null;
    state.currentObject = null;
  }

  // Deactivate old step when going backward
  if (direction === 'backward' && oldStep && oldIndex !== 0) {
    oldStep.classList.remove('is-active');
  }

  state.currentIndex = newIndex;

  const objectId = newStep.dataset.object;
  const x = parseFloat(newStep.dataset.x);
  const y = parseFloat(newStep.dataset.y);
  const zoom = parseFloat(newStep.dataset.zoom);

  // Determine if we need to switch objects or just pan/zoom
  const isLeavingIntro = (oldIndex === 0 && newIndex > 0);

  if (objectId && (!state.currentViewerCard || state.currentViewerCard.objectId !== objectId || isLeavingIntro)) {
    console.log(`Switching to new object: ${objectId}${isLeavingIntro ? ' (leaving intro)' : ''}`);
    switchToObject(objectId, newIndex, x, y, zoom, newStep, direction);
    state.currentObject = objectId;
  } else {
    console.log(`Same object, activating text and animating viewer`);

    if (direction === 'forward' && state.currentViewerCard) {
      state.currentViewerCard.element.classList.remove('card-below');
      state.currentViewerCard.element.classList.add('card-active');
    }

    if (direction === 'forward') {
      newStep.offsetHeight;
      requestAnimationFrame(() => {
        newStep.classList.add('is-active');
      });
    }

    if (state.currentViewerCard && !isNaN(x) && !isNaN(y) && !isNaN(zoom)) {
      if (state.currentViewerCard.isReady) {
        animateViewerToPosition(state.currentViewerCard, x, y, zoom);
      } else {
        console.warn('Viewer not ready, queueing zoom');
        state.currentViewerCard.pendingZoom = { x, y, zoom, snap: false };
      }
    }
  }

  updateViewerInfo(newIndex);
  preloadNearbyViewers(newIndex, 3, 2);
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
  if (state.currentMobileStep >= state.steps.length - 1) {
    console.log('Already at last step');
    return;
  }
  goToMobileStep(state.currentMobileStep + 1);
}

/**
 * Navigate to the previous step (mobile/embed).
 */
function goToPreviousMobileStep() {
  if (state.currentMobileStep <= 0) {
    console.log('Already at first step');
    return;
  }
  goToMobileStep(state.currentMobileStep - 1);
}

/**
 * Navigate to a specific step (mobile/embed).
 *
 * Handles cooldown, skeleton loading states, step class toggling,
 * object switching or pan/zoom, and preloading.
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

  console.log(`Mobile navigation: ${state.currentMobileStep} → ${newIndex}`);

  // Swap step visibility
  state.steps[state.currentMobileStep].classList.remove('mobile-active');
  state.steps[newIndex].classList.add('mobile-active');
  state.currentMobileStep = newIndex;

  updateMobileButtonStates();

  // Handle viewer updates
  const x = parseFloat(newStep.dataset.x);
  const y = parseFloat(newStep.dataset.y);
  const zoom = parseFloat(newStep.dataset.zoom);

  if (objectId && (!state.currentViewerCard || state.currentViewerCard.objectId !== objectId)) {
    console.log(`Switching to object: ${objectId}`);
    switchToObjectMobile(objectId, newIndex, x, y, zoom);
    state.currentObject = objectId;
  } else if (state.currentViewerCard && !isNaN(x) && !isNaN(y) && !isNaN(zoom)) {
    if (state.currentViewerCard.isReady) {
      animateViewerToPosition(state.currentViewerCard, x, y, zoom);
    } else {
      state.currentViewerCard.pendingZoom = { x, y, zoom, snap: false };
    }
  }

  updateViewerInfo(newIndex);
  preloadNearbyViewers(newIndex, 2, 2);
}

/**
 * Update mobile button enabled/disabled states at step boundaries.
 */
function updateMobileButtonStates() {
  if (!state.mobileNavButtons) return;
  state.mobileNavButtons.prev.disabled = (state.currentMobileStep === 0);
  state.mobileNavButtons.next.disabled = (state.currentMobileStep === state.steps.length - 1);
}

// ── Keyboard input ───────────────────────────────────────────────────────────

/**
 * Handle keyboard navigation and panel control.
 *
 * @param {KeyboardEvent} e
 */
function handleKeyboard(e) {
  switch (e.key) {
    case 'ArrowDown':
    case 'PageDown':
      e.preventDefault();
      if (!state.scrollLockActive) {
        nextStep();
      }
      break;

    case 'ArrowUp':
    case 'PageUp':
      e.preventDefault();
      if (!state.scrollLockActive) {
        prevStep();
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
      e.preventDefault();
      if (!state.scrollLockActive) {
        if (e.shiftKey) {
          prevStep();
        } else {
          nextStep();
        }
      }
      break;
  }
}

// ── Scroll input ─────────────────────────────────────────────────────────────

/**
 * Handle wheel events with scroll accumulation.
 *
 * Collects scroll distance until the threshold is reached, then triggers
 * a step change. Respects panel freeze and viewer scroll isolation.
 *
 * @param {WheelEvent} e
 */
function handleScroll(e) {
  if (state.scrollLockActive) {
    state.scrollAccumulator = 0;
    return;
  }

  // Ignore wheel events from the viewer column (UV handles zoom/pan)
  if (e.target.closest('.viewer-column')) {
    return;
  }

  const now = Date.now();
  const timeSinceLastChange = now - state.lastStepChangeTime;

  if (timeSinceLastChange < STEP_COOLDOWN) {
    state.scrollAccumulator *= 0.5;
    return;
  }

  const cappedDelta = Math.max(-MAX_SCROLL_DELTA, Math.min(MAX_SCROLL_DELTA, e.deltaY));
  state.scrollAccumulator += cappedDelta;

  if (state.scrollAccumulator >= state.scrollThreshold) {
    nextStep();
    state.scrollAccumulator = 0;
  } else if (state.scrollAccumulator <= -state.scrollThreshold) {
    prevStep();
    state.scrollAccumulator = 0;
  }
}

// ── Touch input (iPad/tablet swipe) ──────────────────────────────────────────

/**
 * Record touch start position for swipe detection.
 *
 * @param {TouchEvent} e
 */
function handleTouchStart(e) {
  state.touchStartY = e.touches[0].clientY;
}

/**
 * Detect swipe direction and trigger step navigation.
 *
 * Swipe up (finger moves toward top of screen) → next step.
 * Swipe down (finger moves toward bottom) → previous step.
 * Requires a minimum swipe distance of 20 % of viewport height.
 *
 * @param {TouchEvent} e
 */
function handleTouchEnd(e) {
  state.touchEndY = e.changedTouches[0].clientY;

  const now = Date.now();
  const timeSinceLastChange = now - state.lastStepChangeTime;

  if (timeSinceLastChange < STEP_COOLDOWN) {
    return;
  }

  if (state.scrollLockActive) {
    return;
  }

  const swipeDistance = state.touchEndY - state.touchStartY;

  if (swipeDistance < -state.touchThreshold) {
    nextStep();
  } else if (swipeDistance > state.touchThreshold) {
    prevStep();
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────

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
 * @param {number} stepNumber - The step number to display.
 */
function updateViewerInfo(stepNumber) {
  const infoElement = document.getElementById('current-object-title');
  if (infoElement) {
    const stepTemplate = window.telarLang.stepNumber || "Step {{ number }}";
    infoElement.textContent = stepTemplate.replace("{{ number }}", stepNumber);
  }
}
