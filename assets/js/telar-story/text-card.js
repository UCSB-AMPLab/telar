/**
 * Telar Story – Text Card
 *
 * This module creates and manages the text overlays that float above
 * viewer plates in the card-stack layout. Each story step gets its own
 * text card element, created once at init and kept in the DOM — visibility
 * is controlled exclusively by CSS transforms, never by display,
 * visibility, or opacity.
 *
 * Two card variants exist depending on the step's zoom level. When a step
 * has specific coordinates (zoom greater than 1.0), the card renders in
 * detail mode: a white card positioned at 4% from the left edge, 42% wide,
 * vertically centred and peek-offset within its object run. When the zoom
 * is undefined, blank, or at most 1.0, the card renders in full-object
 * mode: a reversed layout where a text background fills the left half of
 * the viewport and an image area occupies the right.
 *
 * All cards start offscreen below the viewport and slide up when activated.
 * Deactivation slides them back down. On mobile, cards anchor to the
 * bottom of the screen at full width with a capped height, rather than
 * floating at the left edge.
 *
 * @version v1.0.0-beta
 */

import { state } from './state.js';

// Note: No imports from card-pool.js to avoid circular dependency.
// Positioning values (topPx, zIndex, messiness) are pre-computed by card-pool.js
// and passed into createTextCard/createFullObjectCard as parameters.

// ── Full-object mode detection ────────────────────────────────────────────────

/**
 * Determine whether a step should use full-object (zoomed-out) layout.
 *
 * Returns true when the viewer should show the whole object rather than
 * zooming into a specific region. This triggers the layout reversal from
 * detail mode (text left, viewer right) to full-object mode (text left,
 * image right with text background).
 *
 * Rules:
 *   - zoom undefined or empty → full-object
 *   - zoom as number <= 1.0 → full-object
 *   - x and y both undefined → full-object (no coordinates = full object)
 *   - zoom > 1.0 with valid x/y → detail mode
 *
 * @param {Object} stepData - Step data object from window.storyData.steps
 * @param {string|number|undefined} [stepData.zoom]
 * @param {string|number|undefined} [stepData.x]
 * @param {string|number|undefined} [stepData.y]
 * @returns {boolean}
 */
export function isFullObjectMode(stepData) {
  const zoom = stepData.zoom;

  // No coordinates at all → full object
  if (stepData.x === undefined && stepData.y === undefined && zoom === undefined) {
    return true;
  }

  // Zoom absent or blank
  if (zoom === undefined || zoom === '' || zoom === null) return true;

  // Numeric zoom <= 1.0
  const zoomNum = parseFloat(zoom);
  if (isNaN(zoomNum) || zoomNum <= 1.0) return true;

  return false;
}

// ── Text card (detail mode) ───────────────────────────────────────────────────

/**
 * Create a text card element for detail mode (zoomed-in steps).
 *
 * Accepts pre-computed positioning values (topPx, zIndex, messiness) from
 * card-pool.js to avoid a circular dependency. The card starts at
 * translateY(100vh) (offscreen below) — call activateTextCard() to slide it up.
 *
 * @param {Object} stepData - Step data object
 * @param {number} stepIndex - Zero-based step index
 * @param {number} topPx - Pre-computed top CSS value in pixels
 * @param {number} cardH - Card height in pixels
 * @param {number} zIndex - Pre-computed z-index
 * @param {{ rot: number, offX: number, offY: number }} messiness - Pre-computed messiness
 * @returns {HTMLElement} The created text card element (not yet in DOM)
 */
export function createTextCard(stepData, stepIndex, topPx, cardH, zIndex, messiness) {
  const card = document.createElement('div');
  card.className = 'text-card';
  card.dataset.stepIndex = stepIndex;
  card.style.zIndex = zIndex;
  if (!state.isMobileViewport) {
    card.style.top = `${topPx}px`;
  }
  card.style.height = `${cardH}px`;
  // Start offscreen below — translateY(100vh) — messiness applied as additional transforms
  card.style.transform = _buildOffscreenTransform(messiness);
  card.dataset.messinessRot  = messiness.rot;
  card.dataset.messinessOffX = messiness.offX;
  card.dataset.messinessOffY = messiness.offY;

  card.innerHTML = _buildTextCardContent(stepData);

  return card;
}

/**
 * Create a full-object mode card (layout reversal: text background + image card).
 *
 * Used for steps with zoom <= 1.0 or no coordinates. The card
 * contains a .text-bg (full-viewport background) and an .image-card (image
 * on the right half). Treated as an object change (mode change).
 *
 * Accepts pre-computed zIndex and messiness from card-pool.js.
 *
 * @param {Object} stepData - Step data object
 * @param {number} stepIndex - Zero-based step index
 * @param {number} zIndex - Pre-computed z-index
 * @param {{ rot: number, offX: number, offY: number }} messiness - Pre-computed messiness
 * @returns {HTMLElement} The created full-object card element (not yet in DOM)
 */
export function createFullObjectCard(stepData, stepIndex, zIndex, messiness) {
  const card = document.createElement('div');
  card.className = 'text-card text-card--full-object';
  card.dataset.stepIndex = stepIndex;
  card.dataset.runPosition = 0;
  card.style.zIndex = zIndex;
  card.style.transform = `translateY(100vh)`;
  card.dataset.messinessRot  = messiness.rot;
  card.dataset.messinessOffX = messiness.offX;
  card.dataset.messinessOffY = messiness.offY;

  const question = stepData.question || '';
  const answer   = stepData.answer   || '';

  const hasLayer1 = stepData.layer1_button && stepData.layer1_button.trim();
  let layerButtonHtml = '';
  if (hasLayer1) {
    layerButtonHtml = `<p class="mt-3"><button class="panel-trigger" data-panel="layer1" data-step="${stepData.step}">${stepData.layer1_button} →</button></p>`;
  }

  card.innerHTML = `
    <div class="text-bg">
      <div class="text-bg-content">
        <h2 class="step-question">${question}</h2>
        <div class="step-answer">${answer}</div>
        ${layerButtonHtml}
      </div>
    </div>
    <div class="image-card"></div>
  `;

  return card;
}

// ── Text card activation / deactivation ──────────────────────────────────────

/**
 * Activate a text card — slide it up from below into view.
 *
 * @param {HTMLElement} cardEl - The card element to activate
 * @param {{ rot: number, offX: number, offY: number }} messinessTransform - Messiness values
 */
export function activateTextCard(cardEl, messinessTransform) {
  cardEl.style.transform = _buildActiveTransform(messinessTransform);
  cardEl.classList.remove('is-stacked');
  cardEl.classList.add('is-active');
}

/**
 * Deactivate a text card.
 *
 * Forward (card becoming stacked beneath new active card): remove is-active,
 * add is-stacked. Card stays at its current position — do NOT clear top.
 *
 * Backward (card being removed from view): slide back down off-screen, remove
 * is-active. Do NOT clear top.
 *
 * @param {HTMLElement} cardEl - The card element to deactivate
 * @param {'forward'|'backward'} direction - Navigation direction
 * @param {number} [viewportH] - Viewport height (required for backward)
 */
export function deactivateTextCard(cardEl, direction, viewportH) {
  const messiness = {
    rot:  parseFloat(cardEl.dataset.messinessRot  || 0),
    offX: parseFloat(cardEl.dataset.messinessOffX || 0),
    offY: parseFloat(cardEl.dataset.messinessOffY || 0),
  };

  cardEl.classList.remove('is-active');

  if (direction === 'backward') {
    // Slide away below — D-19
    cardEl.style.transform = _buildOffscreenTransform(messiness);
    // is-stacked is not added on backward — card is returning to hidden state
  } else {
    // Forward: card stays at current position, becomes part of peek stack
    cardEl.classList.add('is-stacked');
  }
}

// ── Private helpers ───────────────────────────────────────────────────────────

/**
 * Build the transform for an offscreen (initial/exit) card.
 *
 * @param {{ rot: number, offX: number, offY: number }} messiness
 * @returns {string}
 */
function _buildOffscreenTransform(messiness) {
  return `translateY(100vh) rotate(${messiness.rot}deg) translate(${messiness.offX}px, ${messiness.offY}px)`;
}

/**
 * Build the transform for an active (visible) card.
 *
 * On mobile, the rotation magnitude is halved (max ±0.75deg instead of
 * ±1.5deg) per D-10 — the card metaphor is present but not distracting
 * at full-width bottom-anchored layout.
 *
 * @param {{ rot: number, offX: number, offY: number }} messiness
 * @returns {string}
 */
function _buildActiveTransform(messiness) {
  const rot = state.isMobileViewport ? messiness.rot * 0.5 : messiness.rot;
  return `translateY(0) rotate(${rot}deg) translate(${messiness.offX}px, ${messiness.offY}px)`;
}

/**
 * Build the inner HTML content for a text card.
 *
 * @param {Object} step - Step data object
 * @returns {string} HTML string
 */
function _buildTextCardContent(step) {
  const question = step.question || '';
  const answer   = step.answer   || '';

  const hasLayer1 = (step.layer1_button && step.layer1_button.trim()) ||
                    (step.layer1_title   && step.layer1_title.trim())  ||
                    (step.layer1_text    && step.layer1_text.trim());
  const hasLayer2 = (step.layer2_button && step.layer2_button.trim()) ||
                    (step.layer2_title   && step.layer2_title.trim())  ||
                    (step.layer2_text    && step.layer2_text.trim());

  let layerButtons = '';
  if (hasLayer1) {
    const label = (step.layer1_button && step.layer1_button.trim()) ? step.layer1_button : 'Learn more';
    layerButtons += `<button class="panel-trigger" data-panel="layer1" data-step="${step.step}">${label} →</button>`;
  }
  if (hasLayer2) {
    const label = (step.layer2_button && step.layer2_button.trim()) ? step.layer2_button : 'Learn more';
    layerButtons += `<button class="panel-trigger" data-panel="layer2" data-step="${step.step}">${label} →</button>`;
  }

  return `
    <h2 class="step-question">${question}</h2>
    <div class="step-answer">${answer}</div>
    ${layerButtons ? `<p class="mt-3">${layerButtons}</p>` : ''}
  `;
}
