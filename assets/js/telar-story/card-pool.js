/**
 * Telar Story – Card Pool
 *
 * This module manages the lifecycle of viewer plates and text cards in the
 * card-stack layout. Every card element is created once at init time and
 * persists in the DOM for the lifetime of the page — visibility is
 * controlled entirely by CSS transforms, so slide transitions animate
 * correctly without the jank of DOM insertion and removal.
 *
 * Scene maps — a story step references an object by ID, but the same
 * object can appear in multiple non-contiguous scenes (A → B → A). To
 * handle this, the module builds a set of maps at init: stepToScene,
 * sceneToObject, and sceneFirstStep. All plate lookups are keyed by scene
 * index, not by object ID, so each appearance of an object gets its own
 * plate element.
 *
 * Z-index banding — each scene occupies a band of 100 z-index values.
 * Scene 0 gets 100–199, scene 1 gets 200–299, and so on. The viewer
 * plate sits at the band base; text cards sit at base + 1 + their
 * run position within consecutive steps of the same object. This ensures
 * that newer plates always stack above all cards from the previous scene.
 *
 * Context-sensitive stacking — when the user navigates to a new step,
 * the module decides what to do based on whether the object changed.
 * If it did, both a new viewer plate and a new text card slide up. If
 * the object is the same, only the text card changes — the existing
 * viewer plate stays visible and the IIIF viewer adjusts its position
 * without reloading. A mode change (detail view to full-object view or
 * vice versa on the same object) is treated as an object change.
 *
 * Preloading — after each step change, the module looks ahead and
 * initialises IIIF viewers, video players, or audio players for upcoming
 * scenes. It counts by scene distance, not step offset, so a long
 * sequence of steps on the same object does not waste preload slots.
 * When the pool exceeds its cap (default 8), the instance farthest by
 * scene distance from the current position is evicted. IIIF tiles for
 * scenes beyond the OSD preload range are also prefetched as image
 * link hints.
 *
 * Accessibility — every viewer plate receives an aria-label built from
 * a fallback chain: step-level alt text, then object-level alt text, then
 * the object title, then the object ID, and finally a type-aware generic
 * label ("Image viewer", "Video player", or "Audio player"). The label
 * is refreshed on every step change.
 *
 * Exported pure functions (getObjectZBase, getSceneIndex, computeCardTop,
 * getCardMessiness) are unit-tested. DOM-interacting functions are
 * acceptance-tested against the running site.
 *
 * @version v1.4.0
 */

import { state } from './state.js';
import { detectCardType } from './card-type.js';
import { extractVideoId } from './card-type.js';
import { getManifestUrl, updateObjectCredits } from './viewer.js';
import { getBasePath } from './utils.js';
import { IiifViewer } from './iiif-viewer.js';
import {
  deactivateIiifCard,
  destroyIiifCard,
  animateIiifToPosition,
  snapIiifToPosition,
  computeFocalTarget,
  _deriveCardPlacement,
} from './iiif-card.js';
import { onViewportResize, onLayoutChange, getLayoutMode, isLandscapeSideCard } from './layout-mode.js';
import {
  createTextCard,
  activateTextCard,
  deactivateTextCard,
  isFullObjectMode,
  createFullObjectCard,
} from './text-card.js';
import {
  createVideoPlayer,
  destroyVideoPlayer,
  activateVideoCard,
  deactivateVideoCard,
  updateVideoClip,
  computeVideoLayout,
  applyClipEndDim,
  showVideoPlayOverlay,
} from './video-card.js';
import {
  createAudioPlayer,
  destroyAudioPlayer,
  activateAudioCard,
  deactivateAudioCard,
  updateAudioClip,
  applyAudioClipEndDim,
  removeAudioClipEndDim,
} from './audio-card.js';

/** Normalise truthy loop values from CSV/JSON: "true", "TRUE", "yes", "sí", true → true */
function _isTruthy(val) {
  if (val === true) return true;
  if (typeof val === 'string') {
    const v = val.trim().toLowerCase();
    return v === 'true' || v === 'yes' || v === 'sí';
  }
  return false;
}

// ── Z-index scenes ────────────────────────────────────────────────────────────
//
// A "scene" is a contiguous run of steps sharing the same background object.
// Each object change starts a new scene, even if returning to a previously-
// seen object.  Scenes are numbered from 0.
//
// Each scene gets a z-index band of 100:
//   Scene 0 → viewer plate 100, text cards 101, 102, 103...
//   Scene 1 → viewer plate 200, text cards 201, 202...
//   Scene 2 → viewer plate 300, text cards 301...
//
// Z-indexes 100–9899 are reserved for scenes (up to 98 scenes).
// Fixed UI chrome sits at 9900+; panels at 9910+; share modal at 9950.
//
// computeZIndexPlan() walks the steps at init time and produces per-step
// z-indexes for both viewer plates and text cards.  The plate z-index is
// stored per step (not per object) because the same plate DOM element may
// appear at different scene levels when an object is reused.

/**
 * Walk the step sequence and assign scene-based z-indexes.
 *
 * @param {Array} steps - Story step data
 * @returns {{ plateZ: Object, textCardZ: Object }}
 *   plateZ:    stepIndex → z-index for the viewer plate at that step
 *   textCardZ: stepIndex → z-index for the text card at that step
 */
export function computeZIndexPlan(steps) {
  let scene = -1;
  let runPos = 0;
  let currentObjectId = null;
  let titleCounter = 0;
  const plateZ = {};
  const textCardZ = {};

  for (let i = 0; i < steps.length; i++) {
    const objectId = steps[i].object || steps[i].objectId || '';
    const effectiveId = objectId === '' ? '__title_' + (titleCounter++) + '__' : objectId;
    if (effectiveId !== currentObjectId) {
      scene++;
      runPos = 0;
      currentObjectId = effectiveId;
    }
    const bandBase = (scene + 1) * 100;
    plateZ[i] = bandBase;
    textCardZ[i] = bandBase + 1 + runPos;
    runPos++;
  }

  return { plateZ, textCardZ };
}

// Legacy exports kept for existing tests
export function getObjectZBase(objectIndex) {
  return (objectIndex + 1) * 100;
}
export function getViewerPlateZIndex(objectIndex) {
  return getObjectZBase(objectIndex);
}
export function getTextCardZIndex(objectIndex, runPosition) {
  return getObjectZBase(objectIndex) + 1 + runPosition;
}

// ── Messiness (pure, unit-tested) ─────────────────────────────────────────────

/**
 * Seeded pseudo-random value in the range [0, 1) using a sin-based hash.
 * The same seed always produces the same result (deterministic).
 * Fractional part of (sin(seed * 127.1 + 311.7) * 43758.5453).
 *
 * @param {number} seed
 * @returns {number} Value in [0, 1)
 */
function seededRandom(seed) {
  const n = Math.sin(seed * 127.1 + 311.7) * 43758.5453;
  return n - Math.floor(n);
}

/**
 * Compute the subtle rotation and offset for a card.
 * When messinessPercent is 0, all values are exactly zero.
 * Uses three different seed multipliers for rot/offX/offY so they vary
 * independently per card.
 *
 * @param {number} seed - Stable per-card seed (e.g. step index)
 * @param {number} messinessPercent - 0–100, controls intensity of messiness
 * @returns {{ rot: number, offX: number, offY: number }}
 */
export function getCardMessiness(seed, messinessPercent) {
  if (messinessPercent === 0) return { rot: 0, offX: 0, offY: 0 };

  const factor = messinessPercent / 100;
  const maxRot  = 1.2 * factor;   // degrees
  const maxOffX = 8.0 * factor;   // px
  const maxOffY = 4.0 * factor;   // px

  // Map [0,1) to [-max, max)
  const rot  = seededRandom(seed * 3 + 1) * maxRot  * 2 - maxRot;
  const offX = seededRandom(seed * 3 + 2) * maxOffX * 2 - maxOffX;
  const offY = seededRandom(seed * 3 + 3) * maxOffY * 2 - maxOffY;

  return { rot, offX, offY };
}

// ── Peek positioning (pure, unit-tested) ─────────────────────────────────────

/**
 * Compute the CSS `top` value (px) for a text card within an object run.
 * The first card in the run is vertically centred. Each subsequent
 * card settles peekHeightPx lower to create the peek stack effect.
 *
 * @param {number} viewportH - Viewport height in px
 * @param {number} cardH - Card height in px
 * @param {number} runPosition - Position within this object's step sequence (0-based)
 * @param {number} peekHeightPx - Pixels each successive card settles lower
 * @returns {number} Top offset in px
 */
export function computeCardTop(viewportH, cardH, runPosition, peekHeightPx) {
  const centred = (viewportH - cardH) / 2;
  return centred + runPosition * peekHeightPx;
}

// ── Accessibility helpers ─────────────────────────────────────────────────────

/**
 * Build an accessible label for a viewer plate using the fallback chain.
 *
 * Priority: step alt_text > object alt_text > object title > object_id > type-aware generic.
 * Type-aware generics: IIIF → "Image viewer", video → "Video player", audio → "Audio player".
 * No provider prefix on video/audio labels.
 *
 * @param {string} objectId
 * @param {string} [stepAlt] - Per-step alt_text from _stepsData
 * @param {string} [cardType] - 'iiif'|'youtube'|'vimeo'|'google-drive'|'audio'
 * @returns {string}
 */
function _buildAriaLabel(objectId, stepAlt, cardType) {
  if (stepAlt) return stepAlt;
  const obj = state.objectsIndex?.[objectId] || {};
  if (obj.alt_text) return obj.alt_text;
  if (obj.title) return obj.title;
  if (objectId) return objectId;
  // Type-aware final fallback
  if (cardType === 'youtube' || cardType === 'vimeo' || cardType === 'google-drive') return 'Video player';
  if (cardType === 'audio') return 'Audio player';
  return 'Image viewer';
}

// ── Module-level card pool state ──────────────────────────────────────────────

// Lookup tables populated at initCardPool time and used during activateCard.
// These are module-level so activateCard doesn't need to rebuild them each call.
let _stepsData = [];          // All step data objects
let _config = { peekHeight: 1, messiness: 20, preloadSteps: 5 };
let _zPlan = { viewerPlateZ: {}, textCardZ: {} };

// ── Scene maps ────────────────────────────────────────────────────────────────

/**
 * Build step-to-scene and scene-to-object lookup tables.
 * A "scene" is a contiguous run of steps sharing the same object.
 * Called once at initCardPool() time; results stored on state for cross-module
 * access (scroll-engine.js, iiif-card.js can read state.stepToScene).
 *
 * @param {Array} steps - Story step data
 */
export function _buildSceneMaps(steps) {
  let scene = -1;
  let currentObjectId = null;
  let titleCounter = 0;

  state.stepToScene = {};
  state.sceneToObject = {};
  state.sceneFirstStep = {};

  for (let i = 0; i < steps.length; i++) {
    const objectId = steps[i].object || steps[i].objectId || '';
    const effectiveId = objectId === '' ? '__title_' + (titleCounter++) + '__' : objectId;
    if (effectiveId !== currentObjectId) {
      scene++;
      currentObjectId = effectiveId;
      state.sceneToObject[scene] = objectId;  // store real empty string, not sentinel
      state.sceneFirstStep[scene] = i;
    }
    state.stepToScene[i] = scene;
  }
  state.totalScenes = scene + 1;
}

// Exported for unit testing under an alias without underscore
export { _buildSceneMaps as buildSceneMaps };

/**
 * Get the scene index for a given step index.
 *
 * @param {number} stepIndex
 * @returns {number} Scene index, or -1 if out of range
 */
export function getSceneIndex(stepIndex) {
  return state.stepToScene[stepIndex] ?? -1;
}

// ── Card pool DOM management ──────────────────────────────────────────────────

/**
 * Build the transform string for a card's messiness offset.
 *
 * @param {{ rot: number, offX: number, offY: number }} messiness
 * @param {string} baseTranslate - E.g. 'translateY(0)' or 'translateY(100vh)'
 * @returns {string}
 */
function buildTransform(messiness, baseTranslate) {
  return `${baseTranslate} rotate(${messiness.rot}deg) translate(${messiness.offX}px, ${messiness.offY}px)`;
}

// ── Geometry recompute on resize / layout change ─────────────────────────────

/**
 * Recompute the inline top and height of all currently-rendered text cards.
 *
 * Called by onViewportResize and onLayoutChange subscriptions so card geometry
 * stays correct after desktop window resize, device rotation, or layout-mode
 * flip. Iterates `.text-card` DOM nodes (iterating the DOM is the reliable
 * source of all active cards regardless of state.textCards population order).
 * Applies computeCardTop with runPosition=0 for all cards
 * (the same initial value used at initCardPool time) and uses
 * style.setProperty('top', ..., 'important') so the inline value wins the
 * cascade over the `top: auto !important` in the landscape side-card rule.
 *
 * @param {number} viewportW - Current viewport width in px
 * @param {number} viewportH - Current viewport height in px
 */
function _recomputeCardGeometry(viewportW, viewportH) {
  const peekHeight = _config.peekHeight ?? 1;
  const landscapeSideCard = isLandscapeSideCard();

  const cards = document.querySelectorAll('.text-card');
  for (const card of cards) {
    const runPos = parseInt(card.dataset.runPosition, 10) || 0;

    if (landscapeSideCard) {
      // Landscape phone: the CSS rule sets `height: auto !important`, so the card
      // is sized to its content. Clear any stale inline height, measure the real
      // rendered height, and centre by THAT — the portrait `viewportH * 0.80`
      // model oversizes the card and jams it against the top on a short landscape
      // viewport. Inline !important top beats the
      // landscape rule's `top: auto !important`.
      card.style.height = '';
      const cardH = card.offsetHeight;
      const topPx = computeCardTop(viewportH, cardH, runPos, peekHeight);
      card.style.setProperty('top', `${topPx}px`, 'important');
    } else if (getLayoutMode() === 'vertical') {
      // getLayoutMode() reads the live matchMedia (self-initialising), so this is
      // correct even at the init-time call below — before layout-mode.js has
      // written state.layoutMode (which defaults to 'horizontal' and would wrongly
      // pick the desktop branch, jamming the portrait card at the top).
      // Portrait mobile: the card is bottom-anchored by CSS (`top: auto !important`,
      // `max-height: 40vh`). Remove any inline top so the CSS anchor wins — do NOT
      // force an !important top here, or the card detaches from the bottom on resize.
      card.style.removeProperty('top');
      card.style.height = `${viewportH * 0.80}px`;  // capped by the CSS max-height: 40vh
    } else {
      // Desktop horizontal: tall side card sized to 80% of the (tall) viewport,
      // vertically centred. No base CSS `top`, so the inline value drives placement.
      const cardH = viewportH * 0.80;
      const topPx = computeCardTop(viewportH, cardH, runPos, peekHeight);
      card.style.setProperty('top', `${topPx}px`, 'important');
      card.style.height = `${cardH}px`;
    }
  }
}

/**
 * Initialize the card pool: create all DOM elements, apply initial transforms
 * (off-screen below), and append them to .card-stack.
 *
 * Builds the unique objects list from stepsData to assign z-index bands.
 * Tracks run position per object for peek-stacking calculations.
 *
 * @param {Object} storyData - window.storyData
 * @param {Object} storyData.steps - Array of step data objects
 * @param {{ peekHeight: number, messiness: number }} config - Card stack config
 */
export function initCardPool(storyData, config) {
  const cardStack = document.querySelector('.card-stack');
  if (!cardStack) return;

  const steps = (storyData?.steps || []).filter(s => !s._metadata);
  const peekHeight = config?.peekHeight ?? 1;
  const messinessPercent = config?.messiness ?? 20;

  // Store for use by activateCard
  _stepsData = steps;
  _config = {
    peekHeight,
    messiness: messinessPercent,
    preloadSteps: state.config.preloadSteps || 5,
  };

  const viewportH = window.innerHeight;
  const cardH = viewportH * 0.80;

  // Compute scene-based z-indexes — each object change starts a new scene
  // with its own z-index band, even if the object was seen before.
  _zPlan = computeZIndexPlan(steps);

  // Build scene maps (walk steps, identify scene boundaries)
  _buildSceneMaps(steps);

  // Initialise title card state maps
  state.titleCards = {};
  state.activeTitleCardIndex = null;

  // Audio object manifest: maps object_id → file extension (e.g. 'mp3')
  // Injected by story.html as window.audioObjects from _data/audio_objects.json
  const audioObjects = storyData?.audioObjects || window.audioObjects || {};

  // Create viewer plates (one per scene)
  for (let sceneIdx = 0; sceneIdx < state.totalScenes; sceneIdx++) {
    const firstStepIdx = state.sceneFirstStep[sceneIdx];
    const objectId = state.sceneToObject[sceneIdx];
    if (!objectId) continue;  // Title card scene — no viewer plate
    const firstStep = steps[firstStepIdx] || {};
    const objectData = state.objectsIndex[objectId] || {};
    const audioExt = audioObjects[objectId];
    const sceneCardType = detectCardType({
      objectId,
      cardType: firstStep.cardType,
      source_url: objectData.source_url || objectData.iiif_manifest || '',
      file_path: audioExt ? `objects/${objectId}.${audioExt}` : '',
    });

    const plate = document.createElement('div');
    plate.className = 'viewer-plate';
    plate.dataset.object = objectId;
    plate.dataset.scene = String(sceneIdx);
    plate.dataset.cardType = sceneCardType;
    plate.style.zIndex = _zPlan.plateZ[firstStepIdx];
    // Accessible label for viewer plate
    plate.setAttribute('role', 'img');
    plate.setAttribute('aria-label', _buildAriaLabel(objectId, firstStep.alt_text, sceneCardType));
    plate.style.transform = 'translateY(100%)';

    // Mark video plates with additional class and data attributes
    if (sceneCardType === 'youtube' || sceneCardType === 'vimeo' || sceneCardType === 'google-drive') {
      plate.classList.add('video-plate');
      plate.dataset.cardType = sceneCardType;
      // Store clip attributes from the first step — video plates are one-per-scene
      if (firstStep.clip_start) plate.dataset.clipStart = firstStep.clip_start;
      if (firstStep.clip_end) plate.dataset.clipEnd = firstStep.clip_end;
      if (firstStep.loop) plate.dataset.loop = firstStep.loop;
    }

    // Mark audio plates with additional class and data attributes
    if (sceneCardType === 'audio') {
      plate.classList.add('audio-plate');
      plate.dataset.cardType = 'audio';
      if (firstStep.clip_start) plate.dataset.clipStart = firstStep.clip_start;
      if (firstStep.clip_end) plate.dataset.clipEnd = firstStep.clip_end;
      if (firstStep.loop) plate.dataset.loop = firstStep.loop;
    }

    cardStack.appendChild(plate);

    state.viewerPlates[sceneIdx] = plate;
  }

  // Create text cards (one per step) and track run position per object
  const objectRunPosition = {};  // objectId → current run position

  for (let stepIdx = 0; stepIdx < steps.length; stepIdx++) {
    const step = steps[stepIdx];
    const objectId = step.object || step.objectId || '';
    const objectData = state.objectsIndex[objectId] || {};
    const audioExt2 = audioObjects[objectId];
    const cardType = detectCardType({
      objectId,
      cardType: step.cardType,
      source_url: objectData.source_url || objectData.iiif_manifest || '',
      file_path: audioExt2 ? `objects/${objectId}.${audioExt2}` : '',
    });

    if (!objectId) {
      // Title card — full-viewport, no messiness, no viewer plate
      const zIndex = _zPlan.textCardZ[stepIdx];
      const titleCard = document.createElement('div');
      titleCard.className = 'title-card';
      titleCard.dataset.stepIndex = String(stepIdx);
      titleCard.dataset.cardType = 'title';
      titleCard.style.zIndex = zIndex;
      titleCard.style.transform = 'translateY(100vh)';
      titleCard.innerHTML = _buildTitleCardContent(step);
      cardStack.appendChild(titleCard);
      state.titleCards[stepIdx] = titleCard;
      continue;  // skip text card creation for this step
    }

    if (cardType === 'text-only' || objectId) {
      // Track run position within this object's sequence
      if (!Object.hasOwn(objectRunPosition, objectId)) {
        objectRunPosition[objectId] = 0;
      }
      const runPos = objectRunPosition[objectId];
      objectRunPosition[objectId]++;

      const objectIndex = getSceneIndex(stepIdx);
      const zIndex = _zPlan.textCardZ[stepIdx];
      // All cards share the same centred top — peek offset applied via
      // transform when stacking, so the active card always covers the previous
      const topPx = computeCardTop(viewportH, cardH, 0, peekHeight);
      const messiness = getCardMessiness(stepIdx, messinessPercent);

      const card = document.createElement('div');
      card.className = 'text-card';
      card.dataset.stepIndex = stepIdx;
      card.dataset.object = objectId;
      card.dataset.runPosition = runPos;
      card.style.zIndex = zIndex;
      card.style.top = `${topPx}px`;
      card.style.height = `${cardH}px`;
      card.style.transform = buildTransform(messiness, 'translateY(100vh)');
      card.dataset.messinessRot = messiness.rot;
      card.dataset.messinessOffX = messiness.offX;
      card.dataset.messinessOffY = messiness.offY;

      // Clone rendered content from the hidden step-data element (Jekyll has
      // already processed markdownify, panel triggers, layer conditions, etc.)
      const hiddenStep = document.querySelector(`.step-data .story-step[data-step="${step.step}"]`);
      if (hiddenStep) {
        const content = hiddenStep.querySelector('.step-content');
        if (content) {
          card.appendChild(content.cloneNode(true));
        } else {
          card.innerHTML = buildTextCardContent(step);
        }
      } else {
        card.innerHTML = buildTextCardContent(step);
      }

      cardStack.appendChild(card);
      state.textCards[stepIdx] = card;

      state.cardPool.push({
        stepIndex: stepIdx,
        objectId,
        cardType,
        runPosition: runPos,
        objectIndex,
        element: card,
      });
    }
  }

  // Preload the first scene's viewer plate behind the intro card.
  // The plate stays at translateY(100%) — it only slides up when the user
  // scrolls to step 0. But initialising the IIIF wrapper now means the image is
  // ready when the transition happens.
  if (steps.length > 0) {
    const firstStep = steps[0];
    const firstObjectId = firstStep.object || firstStep.objectId || '';
    if (firstObjectId && state.viewerPlates[0]) {
      const plate = state.viewerPlates[0];
      const zIndex = _zPlan.plateZ[0];
      if (plate.classList.contains('video-plate')) {
        _initVideoInPlate(plate, firstObjectId, 0, zIndex);
      } else if (plate.classList.contains('audio-plate')) {
        _initAudioInPlate(plate, firstObjectId, 0, zIndex);
      } else {
        const x    = parseFloat(firstStep.x);
        const y    = parseFloat(firstStep.y);
        const zoom = parseFloat(firstStep.zoom);
        const page = firstStep.page ? parseInt(firstStep.page, 10) : undefined;
        _initOsdInPlate(plate, firstObjectId, 0, zIndex, x, y, zoom, page);
      }
    }
  }

  // Subscribe to layout-mode events so card geometry stays live
  // (no new ad-hoc resize listeners — only layout-mode.js subscriptions).
  // Mirror the video-card.js subscription pattern.
  onViewportResize(({ viewport }) => {
    _recomputeCardGeometry(viewport.w, viewport.h);
  });
  onLayoutChange(({ viewport }) => {
    _recomputeCardGeometry(viewport.w, viewport.h);
  });

  // Apply correct geometry once now so a fresh load gets the right placement —
  // in particular a direct landscape deep link, where no resize/layout event
  // fires to trigger the side-card centring. Cards are
  // built with content above, so offsetHeight is measurable.
  _recomputeCardGeometry(window.innerWidth, window.innerHeight);
}

/**
 * Build the inner HTML for a text card from step data.
 *
 * @param {Object} step - Step data object
 * @returns {string} HTML string
 */
function buildTextCardContent(step) {
  const question = step.question || '';
  const answer   = step.answer   || '';

  const hasLayer1 = step.layer1_button && step.layer1_button.trim();
  const hasLayer2 = step.layer2_button && step.layer2_button.trim();

  let layerButtons = '';
  if (hasLayer1) {
    layerButtons += `<button class="panel-trigger" data-panel="layer1" data-step="${step.step}">${step.layer1_button}</button>`;
  }
  if (hasLayer2) {
    layerButtons += `<button class="panel-trigger" data-panel="layer2" data-step="${step.step}">${step.layer2_button}</button>`;
  }

  return `
    <div class="step-question">${question}</div>
    <div class="step-answer">${answer}</div>
    ${layerButtons ? `<div class="step-actions">${layerButtons}</div>` : ''}
  `;
}

/**
 * Build the inner HTML for a title card from step data.
 *
 * @param {Object} step - Step data object
 * @returns {string} HTML string
 */
function _buildTitleCardContent(step) {
  const heading = step.question || '';
  const body    = step.answer   || '';
  return `
    <div class="title-card-inner">
      <h2 class="title-card-heading">${heading}</h2>
      ${body ? '<p class="title-card-body">' + body + '</p>' : ''}
    </div>
  `;
}

// ── Context-sensitive card activation ────────────────────────────────────────

/**
 * Activate the card at the given step index, orchestrating context-sensitive
 * stacking based on whether the object changed.
 *
 * Object change or mode change:
 *   New viewer plate slides up + text card slides up, covering everything
 *   from the previous object.
 *
 * Same object, same mode:
 *   Only a new text card slides up; the IIIF viewer stays visible and does
 *   not reload. If viewer is ready, animate to the new step's position.
 *
 * Backward navigation:
 *   Reverse the above — current text card slides back down; on object change
 *   the current viewer plate also slides back down.
 *
 * @param {number} index - Step index to activate
 * @param {'forward'|'backward'} direction
 */
export function activateCard(index, direction) {
  // Title card path — no viewer plate, no text card, no IIIF
  if (state.titleCards?.[index]) {
    _activateTitleCardStep(index, direction);
    return;
  }

  const card = state.textCards[index];
  if (!card) return;

  const poolEntry = state.cardPool.find(c => c.stepIndex === index);
  if (!poolEntry) return;

  const step = _stepsData[index] || {};
  const prevStep = index > 0 ? _stepsData[index - 1] : null;

  const objectId = poolEntry.objectId;
  const prevObjectId = state.currentObjectRun?.objectId;

  const currentMode = isFullObjectMode(step);
  const prevMode = prevStep ? isFullObjectMode(prevStep) : null;
  const isModeChange = prevMode !== null && currentMode !== prevMode;
  const isObjectChange = objectId !== prevObjectId;

  // mode change on same object treated as object change
  const needsNewViewer = isObjectChange || isModeChange;

  if (direction === 'forward') {
    if (needsNewViewer) {
      // Full card — new viewer plate + new text card
      _activateNewViewerPlate(objectId, index, prevObjectId, step, direction);

      // Reset the object run tracker
      state.currentObjectRun = { objectId, runPosition: poolEntry.runPosition };

      // Deactivate previous text card (keep stacked, not slide away)
      _deactivatePreviousTextCard(index, direction);

      // Deactivate active title card if transitioning from title → content (forward)
      if (state.activeTitleCardIndex != null) {
        const prevTitle = state.titleCards[state.activeTitleCardIndex];
        if (prevTitle) {
          prevTitle.classList.remove('is-active');
          prevTitle.classList.add('is-stacked');
        }
        state.activeTitleCardIndex = null;
      }

      // Activate new text card
      _activateTextCard(card);

      updateObjectCredits(objectId);

    } else {
      // Text-only on same object
      state.currentObjectRun.runPosition = poolEntry.runPosition;

      // Deactivate previous text card (becomes stacked)
      _deactivatePreviousTextCard(index, direction);

      // Activate new text card
      _activateTextCard(card);

      // Update viewer for this step's position
      const sceneIndex = getSceneIndex(index);
      const plate = sceneIndex >= 0 ? state.viewerPlates[sceneIndex] : null;

      if (plate && plate.classList.contains('video-plate')) {
        // Video: update clip parameters and seek to new clip start
        const clipStart = parseFloat(step.clip_start) || 0;
        const clipEnd = parseFloat(step.clip_end) || 0;
        const loop = _isTruthy(step.loop);
        updateVideoClip(plate, clipStart, clipEnd || undefined, loop);
      } else if (plate && plate.classList.contains('audio-plate')) {
        // Audio: update clip parameters and seek to new clip start
        const clipStart = parseFloat(step.clip_start) || 0;
        const clipEnd = parseFloat(step.clip_end) || 0;
        const loop = _isTruthy(step.loop);
        updateAudioClip(plate, clipStart, clipEnd || undefined, loop);
      } else if (!state.scrollDriven) {
        // IIIF: animate to this step's position — skip if scroll-driven
        // because lerpIiifPosition already positioned the viewer each frame
        _animateViewerToStep(objectId, step, index);
      }
    }

  } else {
    // Backward navigation
    if (needsNewViewer) {
      // Per-scene plates: each scene always has its own DOM element, so
      // currentPlate and prevPlate are always different elements (no identity
      // collision like the old per-object model). No same-element guard needed.
      const prevSceneIndex = prevObjectId !== null
        ? getSceneIndex(Math.max(0, index + 1))
        : -1;
      const currentSceneIndex = getSceneIndex(index + 1);
      const currentPlate = currentSceneIndex >= 0 ? state.viewerPlates[currentSceneIndex] : null;
      const prevPlate = state.viewerPlates[getSceneIndex(index)];

      {
        // Different DOM elements always — slide current plate down, reveal previous
        if (currentPlate) {
          if (currentPlate.classList.contains('video-plate')) {
            // Snap immediately off-screen. Video/audio iframes on mobile
            // can break CSS transform transitions (compositing layer issues
            // with cross-origin iframes), so bypass the transition entirely.
            currentPlate.style.transition = 'none';
            currentPlate.style.transform = 'translateY(100%)';
            void currentPlate.offsetHeight;  // force reflow
            currentPlate.style.transition = '';
            deactivateVideoCard(currentPlate);
          } else if (currentPlate.classList.contains('audio-plate')) {
            currentPlate.style.transition = 'none';
            currentPlate.style.transform = 'translateY(100%)';
            void currentPlate.offsetHeight;
            currentPlate.style.transition = '';
            deactivateAudioCard(currentPlate);
          } else {
            deactivateIiifCard(
              { element: currentPlate, objectId: prevObjectId },
              'backward'
            );
          }
          currentPlate.classList.remove('is-active');
        }
        if (prevPlate) {
          prevPlate.style.zIndex = _zPlan.plateZ[index];
          // Snap to position without animation — the plate was offscreen
          // from the forward transition and should appear instantly behind
          // the departing plate.
          prevPlate.style.transition = 'none';
          prevPlate.style.transform = 'translateY(0)';
          void prevPlate.offsetHeight; // force reflow
          prevPlate.style.transition = '';
          prevPlate.classList.add('is-active');
          // Re-apply video/audio layout when returning to a media plate
          if (prevPlate.classList.contains('video-plate')) {
            activateVideoCard(prevPlate, getSceneIndex(index));
          } else if (prevPlate.classList.contains('audio-plate')) {
            activateAudioCard(prevPlate, getSceneIndex(index));
          }
        }
      }

      state.currentObjectRun = { objectId, runPosition: poolEntry.runPosition };

      // Slide current text card back down
      _deactivatePreviousTextCard(index, direction);

      // Deactivate active title card if transitioning from title → content (backward)
      if (state.activeTitleCardIndex != null) {
        const prevTitle = state.titleCards[state.activeTitleCardIndex];
        if (prevTitle) {
          prevTitle.classList.remove('is-active');
          prevTitle.style.transform = 'translateY(100vh)';
          prevTitle.classList.remove('is-stacked');
        }
        state.activeTitleCardIndex = null;
      }

      // Restore this step's text card to active
      _activateTextCard(card);

      updateObjectCredits(objectId);

    } else {
      // Same object, backward: text card slides down, previous card reactivated
      state.currentObjectRun.runPosition = poolEntry.runPosition;

      _deactivatePreviousTextCard(index, direction);
      _activateTextCard(card);

      // Update viewer for this step's position
      const sceneIndex = getSceneIndex(index);
      const plate = sceneIndex >= 0 ? state.viewerPlates[sceneIndex] : null;

      if (plate && plate.classList.contains('video-plate')) {
        // Video: update clip parameters and seek to new clip start
        const clipStart = parseFloat(step.clip_start) || 0;
        const clipEnd = parseFloat(step.clip_end) || 0;
        const loop = _isTruthy(step.loop);
        updateVideoClip(plate, clipStart, clipEnd || undefined, loop);
      } else if (plate && plate.classList.contains('audio-plate')) {
        // Audio: update clip parameters and seek to new clip start
        const clipStart = parseFloat(step.clip_start) || 0;
        const clipEnd = parseFloat(step.clip_end) || 0;
        const loop = _isTruthy(step.loop);
        updateAudioClip(plate, clipStart, clipEnd || undefined, loop);
      } else if (!state.scrollDriven) {
        // IIIF: animate viewer back to this step's position — skip if scroll-driven
        _animateViewerToStep(objectId, step, index);
      }
    }
  }

  // Update aria-label on the active viewer plate for current step
  const _stepData = _stepsData[index] || {};
  const _stepAlt = _stepData.alt_text || '';
  const _plateForStep = state.viewerPlates?.[state.stepToScene?.[index]];
  if (_plateForStep) {
    const _cType = _plateForStep.dataset.cardType || 'iiif';
    _plateForStep.setAttribute('aria-label', _buildAriaLabel(objectId, _stepAlt, _cType));
  }

  // Preload ahead
  preloadAhead(index, _config.preloadSteps, 2);

  // Full-object mode detection kept for mode-change → new viewer logic
  // but no layout reversal — viewer is always full-viewport, compensation handles positioning
}

// ── Per-frame scrub positioning ───────────────────────────────────────────────

/**
 * Set the visual progress of card transition during scroll scrubbing.
 *
 * Called every frame by the scroll engine. Positions the NEXT card
 * proportionally — at progress 0.0 it is fully below viewport, at 1.0
 * it is fully in position. The current card stays put (revealed
 * as the next card slides away backward).
 *
 * Only operates during is-scrubbing mode (CSS transitions disabled).
 * During button/keyboard nav, CSS transitions handle the animation.
 *
 * @param {number} stepIndex - Current step (floor of position)
 * @param {number} progress - Fractional progress 0.0-1.0
 */
export function setCardProgress(stepIndex, progress) {
  if (progress < 0.001) return; // At exact integer, no scrub needed

  const nextIndex = stepIndex + 1;
  const nextCard = state.textCards[nextIndex] || state.titleCards?.[nextIndex];
  if (!nextCard) return;

  // Only apply per-frame transforms during scrub mode
  const cardStack = document.querySelector('.card-stack');
  if (!cardStack || !cardStack.classList.contains('is-scrubbing')) return;

  // next card slides from translateY(100vh) to its final position
  // Retrieve the messiness for this card
  const rot  = parseFloat(nextCard.dataset.messinessRot  || 0);
  const offX = parseFloat(nextCard.dataset.messinessOffX || 0);
  const offY = parseFloat(nextCard.dataset.messinessOffY || 0);

  const translateY = (1 - progress) * 100; // vh
  nextCard.style.transform = `translateY(${translateY}vh) rotate(${rot}deg) translate(${offX}px, ${offY}px)`;

  // Also handle next viewer plate for object changes
  const nextStep = _stepsData[nextIndex];
  const currentStep = _stepsData[stepIndex];
  if (!nextStep || !currentStep) return;

  const nextObjectId = nextStep.object || nextStep.objectId || '';
  const currentObjectId = currentStep.object || currentStep.objectId || '';

  if (nextObjectId !== currentObjectId) {
    if (nextObjectId === '') {
      // Next step is a title card — scrub current plate away downward
      const currentSceneIndex = getSceneIndex(stepIndex);
      const currentPlate = currentSceneIndex >= 0 ? state.viewerPlates[currentSceneIndex] : null;
      if (currentPlate) {
        currentPlate.style.transform = `translateY(-${progress * 100}%)`;
      }
    } else {
      // Normal object change — slide next viewer plate proportionally
      const nextSceneIndex = getSceneIndex(nextIndex);
      const nextPlate = nextSceneIndex >= 0 ? state.viewerPlates[nextSceneIndex] : null;
      if (nextPlate) {
        const plateTranslateY = (1 - progress) * 100; // %
        nextPlate.style.transform = `translateY(${plateTranslateY}%)`;
      }
    }
  }
}

// ── Private helpers ───────────────────────────────────────────────────────────

/**
 * Activate a new viewer plate for an object change.
 *
 * Forward: slide new plate up from below. Past plate stays in place,
 * covered by the new plate's higher z-index.
 *
 * @param {string} objectId - New object ID
 * @param {number} stepIndex - Current step index (for z-plan lookup)
 * @param {string|null} prevObjectId - Previous object ID (may be null)
 * @param {Object} step - Current step data
 * @param {'forward'|'backward'} direction
 */
function _activateNewViewerPlate(objectId, stepIndex, prevObjectId, step, direction) {
  const sceneIndex = getSceneIndex(stepIndex);
  const prevSceneIndex = stepIndex > 0 ? getSceneIndex(stepIndex - 1) : -1;

  const prevPlate = prevSceneIndex >= 0 ? state.viewerPlates[prevSceneIndex] : null;
  const newPlate  = sceneIndex >= 0 ? state.viewerPlates[sceneIndex] : null;

  if (!newPlate) return;

  // Update plate z-index from the scene plan.
  newPlate.style.zIndex = _zPlan.plateZ[stepIndex];

  if (direction === 'forward') {
    // For scene 0: skip the reset-to-offscreen if the plate was already
    // positioned by the intro scrub (scroll-engine intro zone progressive
    // positioning). Scenes 1+ always start clean at translateY(100%).
    if (sceneIndex === 0) {
      const currentTransform = newPlate.style.transform;
      if (!currentTransform || currentTransform === 'translateY(100%)') {
        newPlate.style.transform = 'translateY(100%)';
        void newPlate.offsetHeight; // Force reflow so CSS transition fires
      }
    } else {
      newPlate.style.transform = 'translateY(100%)';
      void newPlate.offsetHeight; // Force reflow so CSS transition fires
    }
    newPlate.style.transform = 'translateY(0)';
  } else {
    newPlate.style.transform = 'translateY(0)';
    if (prevPlate) {
      prevPlate.style.transform = 'translateY(100%)';
    }
  }

  newPlate.classList.add('is-active');
  if (prevPlate) {
    if (prevPlate.classList.contains('video-plate')) {
      deactivateVideoCard(prevPlate);
    } else if (prevPlate.classList.contains('audio-plate')) {
      deactivateAudioCard(prevPlate);
    } else {
      prevPlate.classList.remove('is-active');
    }
  }

  // Wire up the OSD wrapper if a ViewerCard exists for this scene
  const viewerCard = state.viewerCards.find(vc => vc.sceneIndex === sceneIndex);
  const x    = parseFloat(step.x);
  const y    = parseFloat(step.y);
  const zoom = parseFloat(step.zoom);
  const page = step.page ? parseInt(step.page, 10) : undefined;

  // Route to audio, video, or IIIF initialisation
  if (newPlate.classList.contains('audio-plate')) {
    // Audio plate: initialise player if not already present
    if (!newPlate.querySelector('.waveform-container')) {
      const zIndex = _zPlan.plateZ[stepIndex];
      _initAudioInPlate(newPlate, objectId, sceneIndex, zIndex);
    }
    activateAudioCard(newPlate, sceneIndex);
  } else if (newPlate.classList.contains('video-plate')) {
    // Video plate: initialise player if not already present
    if (!newPlate.querySelector('.video-iframe, iframe')) {
      const zIndex = _zPlan.plateZ[stepIndex];
      _initVideoInPlate(newPlate, objectId, sceneIndex, zIndex);
    }
    // Always activate — _initVideoInPlate creates .video-iframe container
    // synchronously (YouTube API loads async inside it), so _applyVideoLayout
    // can position the container immediately.
    activateVideoCard(newPlate, sceneIndex);
  } else if (!viewerCard) {
    // No wrapper instance yet — the plate DOM element exists but has no viewer.
    // Create a IIIF card that will initialise the OSD wrapper inside this plate.
    // We adopt the existing plate element rather than creating a new one.
    const zIndex = _zPlan.plateZ[stepIndex];
    _initOsdInPlate(newPlate, objectId, sceneIndex, zIndex, x, y, zoom, page);
  } else if (viewerCard.isReady && !isNaN(x) && !isNaN(y) && !isNaN(zoom)) {
    snapIiifToPosition(viewerCard, x, y, zoom);
  } else if (!isNaN(x) && !isNaN(y) && !isNaN(zoom)) {
    viewerCard.pendingZoom = { x, y, zoom, snap: true };
  }
}

/**
 * Initialise an IIIF viewer inside an existing plate element.
 *
 * This is called when we need a viewer but no ViewerCard has been created
 * yet for the scene. Rather than creating a new plate, we inject the
 * wrapper into the plate that initCardPool already placed in the DOM.
 *
 * @param {HTMLElement} plateEl - The existing viewer-plate element
 * @param {string} objectId
 * @param {number} sceneIndex - The scene this card belongs to
 * @param {number} zIndex
 * @param {number} x
 * @param {number} y
 * @param {number} zoom
 * @param {number|undefined} page - 1-indexed page for external multi-page manifests; mapped to wrapper's 0-indexed `startPage` below
 */
function _initOsdInPlate(plateEl, objectId, sceneIndex, zIndex, x, y, zoom, page) {
  const manifestUrl = getManifestUrl(objectId, page);
  if (!manifestUrl) {
    console.error('_initOsdInPlate: no manifest URL for', objectId);
    return;
  }

  plateEl.dataset.loading = 'true';

  const viewerId = `iiif-viewer-${state.viewerCardCounter}`;
  let viewerDiv = plateEl.querySelector('.viewer-instance');
  if (!viewerDiv) {
    viewerDiv = document.createElement('div');
    viewerDiv.className = 'viewer-instance';
    viewerDiv.id = viewerId;
    plateEl.appendChild(viewerDiv);
  } else {
    viewerDiv.id = viewerId;
  }

  // External multi-page manifests now open at the requested page rather
  // than always starting at page 1.
  const startPage = page && page > 1 ? page - 1 : 0;

  const osdWrapper = new IiifViewer({
    container: '#' + viewerId,
    manifestUrl,
    startPage,
    showChrome: false,
  });

  const viewerCard = {
    sceneIndex,    // scene this card belongs to
    objectId,
    page: page || undefined,
    element: plateEl,
    osdWrapper,
    osdViewer: null,
    isReady: false,
    pendingZoom: (!isNaN(x) && !isNaN(y) && !isNaN(zoom)) ? { x, y, zoom, snap: true } : null,
    zIndex,
  };

  osdWrapper.ready.then(() => {
    viewerCard.osdViewer = osdWrapper.viewer;
    viewerCard.isReady = true;
    delete plateEl.dataset.loading;

    // Belt-and-braces: the wrapper already sets this in _init(); keeping
    // the line here documents the Telar invariant (wheel events belong to
    // Lenis, not OSD) at the call site too.
    osdWrapper.viewer.gestureSettingsMouse.scrollToZoom = false;

    if (viewerCard.pendingZoom) {
      const pz = viewerCard.pendingZoom;

      if (pz.snap) {
        snapIiifToPosition(viewerCard, pz.x, pz.y, pz.zoom);
      } else {
        animateIiifToPosition(viewerCard, pz.x, pz.y, pz.zoom);
      }

      // Verify-and-retry (belt-and-braces on top of the rAF-deferred
      // .ready). Even after the rAF settle, a residual race can leave
      // the viewer at home zoom (measured: step 19, authored 10×). One frame after
      // applying the snap, read the current OSD zoom and compare against home zoom.
      // If they match — and the authored zoom was meaningfully > 1 — the apply
      // was dropped; re-apply exactly once. Tolerance: 5% of homeZoom.
      //
      // `pendingZoom` is cleared only after the verify/retry so the values
      // remain available for the re-apply if needed.
      requestAnimationFrame(() => {
        const pzAfter = viewerCard.pendingZoom; // still holds pz at this point
        if (pzAfter && viewerCard.osdViewer) {
          const vp       = viewerCard.osdViewer.viewport;
          const homeZoom = vp.getHomeZoom();
          const curZoom  = vp.getZoom(true);
          const TOL      = 0.05; // 5% relative tolerance
          const authoredIsZoomed = pzAfter.zoom > 1.1; // authored multiplier meaningfully above home
          const droppedToHome    = Math.abs(curZoom - homeZoom) < homeZoom * TOL;

          if (authoredIsZoomed && droppedToHome) {
            // Home-fit overwrote the snap — re-apply the authored position once.
            if (pzAfter.snap) {
              snapIiifToPosition(viewerCard, pzAfter.x, pzAfter.y, pzAfter.zoom);
            } else {
              animateIiifToPosition(viewerCard, pzAfter.x, pzAfter.y, pzAfter.zoom);
            }
          }
        }
        viewerCard.pendingZoom = null;
      });
    } else {
      // No pending zoom — nothing to verify.
      viewerCard.pendingZoom = null;
    }

  }).catch(err => {
    console.error(`_initOsdInPlate: IiifViewer failed for ${objectId}:`, err);
    viewerCard.isReady = true;
    delete plateEl.dataset.loading;
  });

  state.viewerCards.push(viewerCard);
  state.viewerCardCounter++;

  // Enforce pool size limit — evict farthest scene
  while (state.viewerCards.length > state.config.maxViewerCards) {
    const currentScene = sceneIndex;
    let farthestIdx = 0;
    let maxDist = -1;
    for (let i = 0; i < state.viewerCards.length; i++) {
      const dist = Math.abs(state.viewerCards[i].sceneIndex - currentScene);
      if (dist > maxDist) {
        maxDist = dist;
        farthestIdx = i;
      }
    }
    const evicted = state.viewerCards.splice(farthestIdx, 1)[0];
    _evictOsdInstance(evicted);
  }
}

/**
 * Evict an OSD viewer wrapper from a plate without removing the plate
 * DOM element. Calls the wrapper's destroy() and keeps the plate div for
 * re-entry. The viewer uses the Canvas2D drawer, so there is no WebGL
 * context to release first (OSD #2693 applies only to the WebGL drawer).
 *
 * @param {Object} viewerCard - The ViewerCard to evict
 */
function _evictOsdInstance(viewerCard) {
  if (viewerCard.osdWrapper && typeof viewerCard.osdWrapper.destroy === 'function') {
    viewerCard.osdWrapper.destroy();
  }
  viewerCard.osdWrapper = null;
  viewerCard.osdViewer = null;
  viewerCard.isReady = false;

  // Remove viewer-instance child so _initOsdInPlate can recreate cleanly on re-entry
  const viewerInstance = viewerCard.element.querySelector('.viewer-instance');
  if (viewerInstance) viewerInstance.remove();
  // Note: viewerCard.element (the plate div) is NOT removed from DOM
}

/**
 * Initialise a video player inside an existing video-plate element.
 *
 * Parallel to _initOsdInPlate — called by activateCard and preloadAhead
 * for 'youtube', 'vimeo', and 'google-drive' card types. Video iframes load
 * content immediately on insertion, so player creation is deferred to here
 * (not at initCardPool time).
 *
 * @param {HTMLElement} plateEl - The existing video-plate element
 * @param {string} objectId
 * @param {number} sceneIndex - The scene this card belongs to
 * @param {number} zIndex
 */
function _initVideoInPlate(plateEl, objectId, sceneIndex, zIndex) {
  const objectData = state.objectsIndex[objectId] || {};
  const sourceUrl = objectData.source_url || objectData.iiif_manifest || '';
  const cardType = plateEl.dataset.cardType;
  const videoId = extractVideoId(cardType, sourceUrl);

  if (!videoId) {
    console.error('_initVideoInPlate: no video ID for', objectId, sourceUrl);
    return;
  }

  const clipStart = parseFloat(plateEl.dataset.clipStart) || 0;
  const clipEnd = parseFloat(plateEl.dataset.clipEnd) || 0;
  const loop = _isTruthy(plateEl.dataset.loop);

  plateEl.style.zIndex = zIndex;

  createVideoPlayer(plateEl, cardType, videoId, {
    clipStart,
    clipEnd: clipEnd || undefined,
    loop,
    sceneIndex,
    sourceUrl,
    onPlay: () => {},
    onTimeUpdate: () => {},
    onEnded: () => {
      applyClipEndDim(plateEl);
    },
    onAutoplayBlocked: () => {
      showVideoPlayOverlay(plateEl);
    },
  });
}

/**
 * Initialise a WaveSurfer audio player inside an existing audio-plate element.
 *
 * Parallel to _initVideoInPlate — called by activateCard and preloadAhead
 * for 'audio' card types.
 *
 * @param {HTMLElement} plateEl - The existing audio-plate element
 * @param {string} objectId
 * @param {number} sceneIndex - The scene this card belongs to
 * @param {number} zIndex
 */
function _initAudioInPlate(plateEl, objectId, sceneIndex, zIndex) {
  const audioObjects = window.storyData?.audioObjects || window.audioObjects || {};
  const ext = audioObjects[objectId];
  if (!ext) {
    console.error('_initAudioInPlate: no audio extension for', objectId);
    return;
  }

  const basePath = getBasePath();
  const audioUrl = `${basePath}/telar-content/objects/${objectId}.${ext}`;
  const peaksUrl = `${basePath}/assets/audio/peaks/${objectId}.json`;

  const clipStart = parseFloat(plateEl.dataset.clipStart) || 0;
  const clipEnd = parseFloat(plateEl.dataset.clipEnd) || 0;
  const loop = _isTruthy(plateEl.dataset.loop);
  const isEmbed = document.body.classList.contains('embed-mode');

  plateEl.style.zIndex = zIndex;

  createAudioPlayer(plateEl, audioUrl, peaksUrl, {
    clipStart,
    clipEnd: clipEnd || undefined,
    loop,
    sceneIndex,
    isEmbed,
    onPlay: () => {
      // Audio hold gate not implemented (audio has no hold gate)
    },
    onTimeUpdate: () => {
      // Progress update handled internally by audio-card.js
    },
    onEnded: () => {
      applyAudioClipEndDim(plateEl);
    },
    onAutoplayBlocked: () => {
      // Play overlay shown by audio-card.js internally
    },
  });
}

/**
 * Deactivate the currently active text card (the one with is-active).
 *
 * @param {number} newIndex - The step index we are moving TO (skip it)
 * @param {'forward'|'backward'} direction
 */
function _deactivatePreviousTextCard(newIndex, direction) {
  const prevCard = state.cardPool.find(c => c.element.classList.contains('is-active'));
  if (!prevCard || prevCard.stepIndex === newIndex) return;

  const el = prevCard.element;
  const messiness = {
    rot:  parseFloat(el.dataset.messinessRot  || 0),
    offX: parseFloat(el.dataset.messinessOffX || 0),
    offY: parseFloat(el.dataset.messinessOffY || 0),
  };
  el.classList.remove('is-active');

  if (direction === 'backward') {
    // Slide away below
    el.style.transform = buildTransform(messiness, 'translateY(100vh)');
    el.classList.remove('is-stacked');
  } else {
    // Forward: card stays completely still — don't touch transform or top.
    // The new card slides up over it and covers it fully.
    el.classList.add('is-stacked');
  }
}

/**
 * Activate a text card — slide it up from below.
 *
 * @param {HTMLElement} cardEl - The text card element
 */
function _activateTextCard(cardEl) {
  const messiness = {
    rot:  parseFloat(cardEl.dataset.messinessRot  || 0),
    offX: parseFloat(cardEl.dataset.messinessOffX || 0),
    offY: parseFloat(cardEl.dataset.messinessOffY || 0),
  };
  cardEl.classList.remove('is-stacked');
  cardEl.classList.add('is-active');
  cardEl.style.transform = buildTransform(messiness, 'translateY(0)');

  // Write final rect to state.cardOverlayRect once the slide-up transition settles.
  // Two cases skip transitionend (it never fires when transition: none is set):
  //   1. prefers-reduced-motion: reduce  (_sass/_responsive.scss:110-126)
  //   2. .card-stack.is-scrubbing        (_sass/_story.scss:50-52)
  // In both cases the imperative style write above forces an immediate layout,
  // so getBoundingClientRect() is correct synchronously.
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const isScrubbing    = document.querySelector('.card-stack')?.classList.contains('is-scrubbing');
  if (prefersReduced || isScrubbing) {
    state.cardOverlayRect = cardEl.getBoundingClientRect();
    return;
  }
  const onSettled = (ev) => {
    if (ev.target !== cardEl || ev.propertyName !== 'transform') return;
    cardEl.removeEventListener('transitionend', onSettled);
    state.cardOverlayRect = cardEl.getBoundingClientRect();
  };
  cardEl.addEventListener('transitionend', onSettled);
}

/**
 * Activate a title card step — slide it up from below (forward) or restore it
 * (backward), hide the credits bar, and update activeTitleCardIndex.
 *
 * @param {number} index - Step index of the title card
 * @param {'forward'|'backward'} direction
 */
function _activateTitleCardStep(index, direction) {
  const titleCard = state.titleCards[index];
  if (!titleCard) return;

  // Deactivate any previously active title card
  if (state.activeTitleCardIndex != null && state.activeTitleCardIndex !== index) {
    const prevTitle = state.titleCards[state.activeTitleCardIndex];
    if (prevTitle) {
      prevTitle.classList.remove('is-active');
      if (direction === 'backward') {
        prevTitle.style.transform = 'translateY(100vh)';
        prevTitle.classList.remove('is-stacked');
      } else {
        prevTitle.classList.add('is-stacked');
      }
    }
  }

  // Deactivate any previously active text card (content step → title card transition)
  _deactivatePreviousTextCard(index, direction);

  // Deactivate the departing content scene's viewer plate so the title card
  // is fully visible and any playing video/audio is stopped.
  const departingStepIndex = direction === 'backward' ? index + 1 : index - 1;
  const departingSceneIndex = departingStepIndex >= 0 ? getSceneIndex(departingStepIndex) : -1;
  const departingPlate = departingSceneIndex >= 0 ? state.viewerPlates[departingSceneIndex] : null;
  if (departingPlate) {
    if (direction === 'backward') {
      departingPlate.style.transition = 'none';
      departingPlate.style.transform = 'translateY(100%)';
      void departingPlate.offsetHeight;
      departingPlate.style.transition = '';
    }
    if (departingPlate.classList.contains('video-plate')) {
      deactivateVideoCard(departingPlate);
    } else if (departingPlate.classList.contains('audio-plate')) {
      deactivateAudioCard(departingPlate);
    } else {
      departingPlate.classList.remove('is-active');
    }
  }

  // Activate this title card
  titleCard.classList.remove('is-stacked');
  titleCard.classList.add('is-active');
  titleCard.style.transform = 'translateY(0)';

  state.activeTitleCardIndex = index;
  state.currentObjectRun = { objectId: '', runPosition: 0 };

  // No text card active on a title step.
  state.cardOverlayRect = null;

  // Hide credits bar — no object to attribute
  updateObjectCredits('');

  // Preload ahead (title card scenes have no viewer to init, preloadAhead guards internally)
  preloadAhead(index, _config.preloadSteps, 2);
}

/**
 * Animate the IIIF viewer for the current scene to the given step's position.
 *
 * @param {string} objectId
 * @param {Object} step - Step data with x, y, zoom properties
 * @param {number} stepIndex - Step index (used to resolve scene index)
 */
function _animateViewerToStep(objectId, step, stepIndex) {
  const x    = parseFloat(step.x);
  const y    = parseFloat(step.y);
  const zoom = parseFloat(step.zoom);

  if (isNaN(x) || isNaN(y) || isNaN(zoom)) return;

  const sceneIndex = getSceneIndex(stepIndex);
  const viewerCard = state.viewerCards.find(vc => vc.sceneIndex === sceneIndex);
  if (!viewerCard) return;

  if (viewerCard.isReady) {
    animateIiifToPosition(viewerCard, x, y, zoom);
  } else {
    viewerCard.pendingZoom = { x, y, zoom, snap: false };
  }
}

// ── Preloading ────────────────────────────────────────────────────────────────

/**
 * Preload viewer cards for nearby scenes.
 * Respects the maxViewerCards pool limit from state.config.
 *
 * Creates IIIF wrapper instances for scenes near the current scene so they are
 * initialised and ready when the user navigates to them.
 * Scene-based: counts distinct scenes, not step offsets, so a long
 * run of same-object steps doesn't count as multiple preload slots.
 *
 * @param {number} currentIndex - Current step index
 * @param {number} ahead - Scenes to preload ahead
 * @param {number} behind - Scenes to keep behind
 */
export function preloadAhead(currentIndex, ahead, behind) {
  const currentScene = getSceneIndex(currentIndex);
  if (currentScene < 0) return;

  // Scan scenes by proximity: forward scenes first, then behind
  for (let offset = 1; offset <= ahead; offset++) {
    const targetScene = currentScene + offset;
    if (targetScene >= state.totalScenes) break;

    const plate = state.viewerPlates[targetScene];
    if (!plate) continue;

    const firstStepIdx = state.sceneFirstStep[targetScene];
    const step = _stepsData[firstStepIdx];
    if (!step) continue;

    const objectId = step.object || step.objectId || '';
    if (!objectId) continue;

    const zIndex = _zPlan.plateZ[firstStepIdx];

    if (plate.classList.contains('audio-plate')) {
      // Audio plate: preload only if no waveform container yet
      if (!plate.querySelector('.waveform-container')) {
        _initAudioInPlate(plate, objectId, targetScene, zIndex);
      }
    } else if (plate.classList.contains('video-plate')) {
      // Video plate: preload only if no video iframe yet
      if (!plate.querySelector('.video-iframe, iframe')) {
        _initVideoInPlate(plate, objectId, targetScene, zIndex);
      }
    } else {
      // IIIF plate: skip if already has a ViewerCard
      if (state.viewerCards.find(vc => vc.sceneIndex === targetScene)) continue;

      const x    = parseFloat(step.x);
      const y    = parseFloat(step.y);
      const zoom = parseFloat(step.zoom);
      const page = step.page ? parseInt(step.page, 10) : undefined;

      _initOsdInPlate(plate, objectId, targetScene, zIndex, x, y, zoom, page);
      _prefetchTilesForScene(targetScene);
    }
  }

  // Tile-only prefetch for scenes beyond the wrapper preload range
  for (let offset = ahead + 1; offset <= ahead + 2; offset++) {
    const tileScene = currentScene + offset;
    if (tileScene >= state.totalScenes) break;
    _prefetchTilesForScene(tileScene);
  }

  // Behind: keep nearby scenes warm
  for (let offset = 1; offset <= behind; offset++) {
    const targetScene = currentScene - offset;
    if (targetScene < 0) break;

    const plate = state.viewerPlates[targetScene];
    if (!plate) continue;

    const firstStepIdx = state.sceneFirstStep[targetScene];
    const step = _stepsData[firstStepIdx];
    if (!step) continue;

    const objectId = step.object || step.objectId || '';
    if (!objectId) continue;

    const zIndex = _zPlan.plateZ[firstStepIdx];

    if (plate.classList.contains('audio-plate')) {
      // Audio plate: preload only if no waveform container yet
      if (!plate.querySelector('.waveform-container')) {
        _initAudioInPlate(plate, objectId, targetScene, zIndex);
      }
    } else if (plate.classList.contains('video-plate')) {
      // Video plate: preload only if no video iframe yet
      if (!plate.querySelector('.video-iframe, iframe')) {
        _initVideoInPlate(plate, objectId, targetScene, zIndex);
      }
    } else {
      // IIIF plate: skip if already has a ViewerCard
      if (state.viewerCards.find(vc => vc.sceneIndex === targetScene)) continue;

      const x    = parseFloat(step.x);
      const y    = parseFloat(step.y);
      const zoom = parseFloat(step.zoom);
      const page = step.page ? parseInt(step.page, 10) : undefined;

      _initOsdInPlate(plate, objectId, targetScene, zIndex, x, y, zoom, page);
      _prefetchTilesForScene(targetScene);
    }
  }
}

// ── IIIF tile prefetching ─────────────────────────────────────────────────────

/**
 * Prefetch IIIF tiles for a scene's first step viewport.
 *
 * Only prefetches self-hosted objects (no iiif_manifest or source_url).
 * Fetches info.json to get image dimensions and tile size, then computes
 * tile URLs covering the step's viewport and issues <link rel="prefetch">
 * to warm the browser cache.
 *
 * @param {number} sceneIndex - Scene to prefetch tiles for
 */
function _prefetchTilesForScene(sceneIndex) {
  const objectId = state.sceneToObject[sceneIndex];
  if (!objectId) return;

  // Skip external manifests — tile URL patterns are server-specific
  const objData = state.objectsIndex?.[objectId];
  if (objData?.iiif_manifest || objData?.source_url) return;

  // Construct base URL from origin, not from info.json id field
  const basePath = getBasePath();
  const baseUrl = `${window.location.origin}${basePath}/iiif/objects/${objectId}`;
  const infoUrl = `${baseUrl}/info.json`;

  fetch(infoUrl)
    .then(r => r.json())
    .then(info => {
      const firstStepIdx = state.sceneFirstStep[sceneIndex];
      const step = _stepsData[firstStepIdx];
      if (!step) return;

      const x    = parseFloat(step.x);
      const y    = parseFloat(step.y);
      const zoom = parseFloat(step.zoom);

      if (isNaN(x) || isNaN(y) || isNaN(zoom)) return;

      const urls = _computeTileUrls(baseUrl, info, x, y, zoom);
      for (const url of urls) {
        const link = document.createElement('link');
        link.rel = 'prefetch';
        link.as = 'image';
        link.href = url;
        document.head.appendChild(link);
      }
    })
    .catch(() => {}); // Silent — prefetch is opportunistic
}

/**
 * Compute IIIF Image API Level 0 tile URLs for a viewport.
 *
 * Maps normalised x/y/zoom step coordinates to image pixel space,
 * determines the appropriate scale factor, enumerates the tile grid
 * covering the visible area, and returns static tile URLs.
 *
 * Uses `computeFocalTarget` (the two-circle model)
 * to derive the prefetch centre from the authored focal point and the
 * inscribed-circle diameter, so prefetched tiles align with the rendered region.
 * The authored diameterImg from the focal circle defines the prefetch
 * width rather than the old viewport-relative estimate.
 *
 * Caps at 9 tiles (3x3 grid) to avoid excessive prefetch requests.
 *
 * @param {string} baseUrl - Image service base URL (e.g. origin + /iiif/objects/leviathan)
 * @param {Object} info - Parsed info.json
 * @param {number} x - Normalised centre X (0-1)
 * @param {number} y - Normalised centre Y (0-1)
 * @param {number} zoom - OSD zoom multiplier
 * @returns {string[]} Array of tile URLs
 */
function _computeTileUrls(baseUrl, info, x, y, zoom) {
  const imageW = info.width;
  const imageH = info.height;
  const tileSize = info.tiles?.[0]?.width || 512;
  const scaleFactors = info.tiles?.[0]?.scaleFactors || [1];

  // Derive cardBox and placementMode via the canonical helper in iiif-card.js.
  const vpW = window.innerWidth;
  const vpH = window.innerHeight;
  const r = state.cardOverlayRect;
  const cardBox = r ? { x: r.x, y: r.y, w: r.width, h: r.height } : null;
  const placementMode = _deriveCardPlacement(cardBox, vpW, vpH);

  // Compute the focal target using the two-circle model.
  // focalImg is the prefetch centre in image px; diameterImg defines the prefetch width.
  const target = computeFocalTarget(x, y, zoom, imageW, imageH, cardBox, placementMode);
  let centreX, centreY, halfW, halfH;

  if (target) {
    // Use the authored focal circle: centre = focalImg, radius = diameterImg/2
    centreX = target.focalImg.x;
    centreY = target.focalImg.y;
    halfW   = target.diameterImg / 2;
    halfH   = target.diameterImg / 2;
  } else {
    // Fallback: use raw authored (x, y) with a viewport-relative size estimate
    const vpH = window.innerHeight;
    centreX = x * imageW;
    centreY = y * imageH;
    const pixelsPerViewportPx = 1 / (zoom * (vpW / imageW));
    halfW = (vpW * pixelsPerViewportPx) / 2;
    halfH = (vpH * pixelsPerViewportPx) / 2;
  }

  // Region in pixel space (clamped to image bounds)
  const left   = Math.max(0, centreX - halfW);
  const top    = Math.max(0, centreY - halfH);
  const right  = Math.min(imageW, centreX + halfW);
  const bottom = Math.min(imageH, centreY + halfH);

  // Choose scale factor — smallest that keeps tile count reasonable
  // Higher scale factor = lower resolution = fewer tiles
  let scaleFactor = scaleFactors[0] || 1;
  for (const sf of scaleFactors) {
    const effectiveTile = tileSize * sf;
    const tilesX = Math.ceil((right - left) / effectiveTile);
    const tilesY = Math.ceil((bottom - top) / effectiveTile);
    if (tilesX * tilesY <= 9) {
      scaleFactor = sf;
      break;
    }
  }

  const effectiveTile = tileSize * scaleFactor;
  const urls = [];

  for (let tx = Math.floor(left / effectiveTile); tx * effectiveTile < right; tx++) {
    for (let ty = Math.floor(top / effectiveTile); ty * effectiveTile < bottom; ty++) {
      const rx = tx * effectiveTile;
      const ry = ty * effectiveTile;
      const rw = Math.min(effectiveTile, imageW - rx);
      const rh = Math.min(effectiveTile, imageH - ry);
      if (rw <= 0 || rh <= 0) continue;

      // Output tile size: actual pixels / scaleFactor (IIIF Level 0 static tiles)
      const outW = Math.ceil(rw / scaleFactor);
      const outH = Math.ceil(rh / scaleFactor);

      // IIIF Image API Level 0 URL pattern:
      // {base}/{region_x},{region_y},{region_w},{region_h}/{output_w},/0/default.jpg
      const url = `${baseUrl}/${rx},${ry},${rw},${rh}/${outW},/0/default.jpg`;
      urls.push(url);

      if (urls.length >= 9) return urls; // Cap at 9 tiles
    }
  }

  return urls;
}

// Exported for unit testing under an alias without underscore (matches the
// _buildSceneMaps as buildSceneMaps pattern above).
export { _computeTileUrls as computeTileUrls };
