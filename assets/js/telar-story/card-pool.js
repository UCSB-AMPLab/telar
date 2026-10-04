/**
 * Telar Story – Card Pool
 *
 * This module owns two distinct lifecycles in the card-stack layout:
 *
 *   1. The permanent text cards (state.textCards) — step index → element,
 *      built once at init time. Every card element is created up front and
 *      persists in the DOM for the lifetime of the page; nothing is ever
 *      evicted. Visibility is controlled entirely by CSS transforms, so
 *      slide transitions animate correctly without the jank of DOM
 *      insertion and removal. What a card is for — its step, its object, its
 *      place in the run — is written on the element, so there is one answer
 *      to each of those questions rather than a map and a record that can
 *      disagree.
 *
 *   2. The viewer pool (state.viewerCards) — live viewer instances (IIIF,
 *      video, audio) attached to viewer plates. This one genuinely pools:
 *      it is capped at config.maxViewerCards, and when over the cap the
 *      instance farthest by scene distance from the current position is
 *      evicted.
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
 * When the viewer pool exceeds its cap (default 8), the instance farthest
 * by scene distance from the current position is evicted. IIIF tiles for
 * scenes beyond the OSD preload range are also prefetched as image
 * link hints.
 *
 * Accessibility — every viewer plate receives an aria-label built from
 * a fallback chain: step-level alt text, then object-level alt text, then
 * the object title, then the object ID, and finally a type-aware generic
 * label ("Image viewer", "Video player", or "Audio player"). The label
 * is refreshed on every step change.
 *
 * Exported pure functions (computeZIndexPlan, getSceneIndex, computeCardTop,
 * getCardMessiness) are unit-tested. DOM-interacting functions are
 * acceptance-tested against the running site.
 *
 * @version v1.8.0
 */

import { state } from './state.js';
import { detectCardType } from './card-type.js';
import { extractVideoId } from './card-type.js';
import { getManifestUrl, updateObjectCredits } from './viewer.js';
import { getBasePath, escapeHtml } from './utils.js';
import { IiifViewer } from './iiif-viewer.js';
import {
  deactivateIiifCard,
  animateIiifToPosition,
  snapIiifToPosition,
  computeFocalTarget,
  reSnapActiveViewer,
  _deriveCardPlacement,
} from './iiif-card.js';
import { onViewportResize, onLayoutChange, getLayoutMode, isLandscapeSideCard } from './layout-mode.js';
import { isFitHeight, applyCardMotionDuration } from './card-height.js';
import { isFullObjectMode } from './text-card.js';
import {
  createVideoPlayer,
  activateVideoCard,
  deactivateVideoCard,
  updateVideoClip,
  applyClipEndDim,
  showVideoPlayOverlay,
} from './video-card.js';
import {
  createAudioPlayer,
  activateAudioCard,
  deactivateAudioCard,
  updateAudioClip,
  applyAudioClipEndDim,
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
    const objectId = steps[i].object || '';
    const effectiveId = objectId === '' ? '__title_' + (titleCounter++) + '__' : objectId;
    if (effectiveId !== currentObjectId) {
      scene++;
      runPos = 0;
      currentObjectId = effectiveId;
    }
    // Cap the band so stories with >98 unique scenes do not overflow into the
    // fixed-UI / panel chrome z-index reserve. Warn once when the cap engages.
    if (scene === 97) {
      console.warn('[Telar] Story has more than 98 unique scenes; z-index ' +
        'banding is clamped at 9800 and panel/UI chrome layering may overlap.');
    }
    const bandBase = Math.min((scene + 1) * 100, 9800);
    plateZ[i] = bandBase;
    textCardZ[i] = bandBase + 1 + runPos;
    runPos++;
  }

  return { plateZ, textCardZ };
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

/**
 * A card's place in its run, read from the card.
 *
 * `_createTextCards` writes it to the element and `_recomputeCardGeometry`
 * reads it back from there, so the element is where it lives; a parallel copy
 * is a second answer to a question with one.
 *
 * @param {HTMLElement} card
 * @returns {number}
 */
function _cardRunPosition(card) {
  return parseInt(card?.dataset?.runPosition, 10) || 0;
}

// ── Peek positioning (pure, unit-tested) ─────────────────────────────────────
//
// Two words this module uses throughout.
//
// A **run** is an unbroken stretch of steps sharing one object, which is the
// same thing the module elsewhere calls a scene. A story that leaves an object
// and returns to it has two runs on that object, not one. `runPosition` is a
// card's 0-based place inside its own run, so the first card of every run is 0
// — including the first card of a second visit.
//
// **Peek** is how far each later card in a run settles below the one before it,
// leaving a strip of the earlier card visible above: the stack peeks out.
// `peekHeight` is that distance in pixels, from `site.card_peek_height`, and it
// defaults to 1, which is near enough to a flat stack that the effect only
// appears on a site that raises it.

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
  const obj = state.objectsIndex[objectId] || {};
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

// Scenes already prefetched, so _prefetchTilesForScene runs at most once per
// scene — preloadAhead calls it repeatedly, which would otherwise re-fetch
// info.json and append duplicate <link rel=prefetch> nodes to <head> unbounded.
const _prefetchedScenes = new Set();

// Extra writes a build adds to the settle, registered through onCardsSettle.
// Module-level so a hook survives every settle rather than one.
const _settleHooks = [];

// ── Scene maps ────────────────────────────────────────────────────────────────

/**
 * Build step-to-scene and scene-to-object lookup tables.
 * A "scene" is a contiguous run of steps sharing the same object.
 * Called once at initCardPool() time; results stored on state for cross-module
 * access (scroll-engine.js, iiif-card.js can read state.stepToScene).
 *
 * @param {Array} steps - Story step data
 */
function _buildSceneMaps(steps) {
  let scene = -1;
  let currentObjectId = null;
  let titleCounter = 0;

  state.stepToScene = {};
  state.sceneToObject = {};
  state.sceneFirstStep = {};

  for (let i = 0; i < steps.length; i++) {
    const objectId = steps[i].object || '';
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

/**
 * The viewer plate belonging to a scene, or null when there is none.
 *
 * A scene index of -1 is what getSceneIndex returns for a step outside the
 * story, and a title-card scene never has a plate at all, so both a negative
 * index and a missing entry answer falsy here.
 *
 * @param {number} sceneIndex
 * @returns {HTMLElement|null|undefined}
 */
function _plateForScene(sceneIndex) {
  return sceneIndex >= 0 ? state.viewerPlates[sceneIndex] : null;
}

/**
 * Whether a step is a section card — a step with no object, and so no plate.
 *
 * A step outside the story answers false: the intro below the first step and
 * the void above the last one are not section cards, and the callers that ask
 * about `stepIndex + 1` and `stepIndex + 2` run off the end of every story.
 *
 * @param {number} stepIndex
 * @returns {boolean}
 */
function _isTitleStep(stepIndex) {
  if (stepIndex < 0 || stepIndex >= _stepsData.length) return false;
  return !(_stepsData[stepIndex].object || '');
}

/**
 * The plate standing behind a step.
 *
 * A section card has no plate of its own, and the scene it interrupts is the
 * one whose plate the reader was last looking at. Walking back to the nearest
 * object scene is what lets a position on a section card say where that plate
 * belongs, which is the one plate nothing else names.
 *
 * @param {number} stepIndex
 * @returns {HTMLElement|null}
 */
function _standingPlate(stepIndex) {
  for (let i = Math.min(stepIndex, _stepsData.length - 1); i >= 0; i--) {
    const plate = _plateForScene(getSceneIndex(i));
    if (plate) return plate;
  }
  return null;
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

/**
 * The base translate for a card a fraction of the way along the lift.
 *
 * Zero is written as the settle writes a resting card, not as `-0vh`, so the
 * two statements of a card at rest are the same string and neither undoes the
 * other.
 *
 * @param {number} progress - 0 at rest, 1 lifted clear
 * @returns {string}
 */
function _liftBase(progress) {
  return progress ? `translateY(${-progress * 100}vh)` : 'translateY(0)';
}

// A viewport's worth of travel clears any card the fit model builds: the
// card's top edge rests at (viewportH − cardH) / 2 and its lower edge at
// (viewportH + cardH) / 2, and the ceiling holds cardH to 0.80 of the
// viewport, so the lower edge rests at most 0.9 of the way down. The card's
// own rotation and offset ride along, so a lifted card is the same sheet at a
// different height rather than a squared-up one.

/**
 * How far along the lift the current scroll position stands.
 *
 * The scroll engine writes the fraction of the way from one step to the next
 * into state on every frame, and the lift runs over exactly that interval:
 * the card being covered is clear of the top at the moment the card arriving
 * from below reaches its rest. Away from a scrub the value is whatever the
 * last frame left, which is why only the scrubbing paths read it.
 *
 * @returns {number} 0 at rest, 1 lifted clear
 */
function _liftProgress() {
  const p = state.scrollProgress;
  return Number.isFinite(p) ? Math.min(1, Math.max(0, p)) : 0;
}

/**
 * Whether the card at a step leaves through the top when the step over it
 * arrives.
 *
 * A card belongs to its plate: it moves exactly as its plate moves, and on
 * its own only inside a scene. That gives three cases and one question.
 *
 * The step over it opens a new scene — its plate rises over card and plate
 * together, and the card stays exactly where it is. This is what makes the
 * stack read as plates covering one another.
 *
 * The step over it is a section card — the card's own plate lifts away
 * through the top, and the card goes with it on the same clock.
 *
 * The step over it is in the same scene — no plate moves at all, so the card
 * travels alone. This is the case the lift exists for: once cards take the
 * height their content needs, a short card cannot cover a tall one.
 *
 * A section card has no plate of its own, so it never travels: whatever comes
 * over it covers it, full-viewport against full-viewport.
 *
 * @param {number} stepIndex - The card's step
 * @returns {boolean}
 */
function _coveredCardLifts(stepIndex) {
  if (!isFitHeight()) return false;
  const over = stepIndex + 1;
  if (stepIndex < 0 || over >= _stepsData.length) return false;
  if (getSceneIndex(stepIndex) === getSceneIndex(over)) return true;
  return _isTitleStep(over) && !!_plateForScene(getSceneIndex(stepIndex));
}

/**
 * Write a card's position, unless it already holds it.
 *
 * The only writer of a card's transform outside an activation's own
 * animation, and the reason the skip is safe: every base it is given comes
 * from `cardBaseFor`, so two paths placing one card at one position produce
 * the same string and the second recognises the first's work. A transform
 * written over a transition already running towards it restarts that
 * transition from wherever it has reached, which at the end of a move leaves
 * the last of the travel running for another full duration.
 *
 * @param {HTMLElement} el
 * @param {string} base - A base translate from cardBaseFor
 */
function placeCard(el, base) {
  if (!el) return;
  const transform = buildTransform(_readCardMessiness(el), base);
  if (el.style.transform !== transform) el.style.transform = transform;
}

/**
 * Where a card belongs, for a scroll resting at `stepIndex + progress`.
 *
 * The one statement of the stack's geometry. Four cases and no others: a card
 * above the pair in play waits a full viewport below; the arriving card is
 * that viewport less the progress travelled; the card the position rests on is
 * at rest, or part of the way out through the top where it is the one being
 * covered; and a card under that is parked where a covered card belongs —
 * still, where a plate rises to cover it, and clear of the top where none
 * does.
 *
 * Every path that writes a card's position asks here: the settle each frame,
 * the reconciliation a jump runs, the backstop a backward move keeps, and the
 * two halves of an activation. That is what makes them agree. They used to
 * state the same four positions in their own terms, which is subtler than
 * plain duplication — two paths writing one position as two different strings
 * cannot recognise each other's work, so a redundant write could not be
 * skipped and a settle repeating a position restarted the transition that was
 * already carrying the card there.
 *
 * @param {number} cardIndex - The card being placed
 * @param {number} stepIndex - Step the position rests on; -1 is the intro
 * @param {number} [progress] - Fraction of the way to the next step
 * @returns {string} A base translate for buildTransform
 */
function cardBaseFor(cardIndex, stepIndex, progress = 0) {
  if (cardIndex > stepIndex + 1) return 'translateY(100vh)';
  if (cardIndex === stepIndex + 1) return `translateY(${(1 - progress) * 100}vh)`;
  if (cardIndex === stepIndex) {
    return _liftBase(_coveredCardLifts(cardIndex) ? progress : 0);
  }
  return _liftBase(_coveredCardLifts(cardIndex) ? 1 : 0);
}

/**
 * The step a card was built for.
 *
 * Written onto every text and title card at build time, and the only handle
 * the paths that are handed a card element rather than an index have on which
 * step's covered-card rule applies to it.
 *
 * @param {HTMLElement} el
 * @returns {number} The step index, or -1 on a card that carries none
 */
function _cardStepIndex(el) {
  const i = parseInt(el.dataset.stepIndex, 10);
  return Number.isInteger(i) ? i : -1;
}

/**
 * Read back the messiness a card was built with.
 *
 * The three values are written onto the card's dataset once, at build time,
 * and are the only record of its rotation and offset. A card without them —
 * a title card, or any card built at messiness 0 — reads as all zeros, which
 * is the identity transform.
 *
 * @param {HTMLElement} el
 * @returns {{ rot: number, offX: number, offY: number }}
 */
function _readCardMessiness(el) {
  return {
    rot:  parseFloat(el.dataset.messinessRot  || 0),
    offX: parseFloat(el.dataset.messinessOffX || 0),
    offY: parseFloat(el.dataset.messinessOffY || 0),
  };
}

// ── Geometry recompute on resize / layout change ─────────────────────────────

/**
 * The side card's share of a tall viewport: its height under the fixed model,
 * and its ceiling under the fit model.
 */
const SIDE_CARD_VIEWPORT_FRACTION = 0.80;

/**
 * Size a card to its content and centre it by the height that comes back.
 *
 * The inline height has to go before the measurement, or `offsetHeight`
 * returns the inline figure rather than the content's. An inline `!important`
 * top is what beats the `top: auto !important` the landscape side-card rule
 * carries; a card whose top is driven by CSS instead does not come through
 * here.
 *
 * @param {HTMLElement} card
 * @param {number} viewportH - Current viewport height in px
 * @param {number} runPos - Position within this object's step sequence
 * @param {number} peekHeight - Pixels each successive card settles lower
 * @param {number|null} maxHeightPx - Ceiling in px, or null to leave the cap
 *   to the stylesheet
 */
function _sizeCardToContent(card, viewportH, runPos, peekHeight, maxHeightPx) {
  card.style.height = '';
  if (maxHeightPx == null) card.style.removeProperty('max-height');
  else card.style.maxHeight = `${maxHeightPx}px`;
  const cardH = card.offsetHeight;
  const topPx = computeCardTop(viewportH, cardH, runPos, peekHeight);
  card.style.setProperty('top', `${topPx}px`, 'important');
}

/**
 * Recompute the inline top and height of all currently-rendered text cards.
 *
 * Called by onViewportResize and onLayoutChange subscriptions so card geometry
 * stays correct after desktop window resize, device rotation, or layout-mode
 * flip. Iterates `.text-card` DOM nodes (iterating the DOM is the reliable
 * source of all active cards regardless of state.textCards population order).
 * Applies computeCardTop with runPosition=0 for all cards and uses
 * style.setProperty('top', ..., 'important') so the inline value wins the
 * cascade over the `top: auto !important` in the landscape side-card rule.
 *
 * @param {number} viewportW - Current viewport width in px
 * @param {number} viewportH - Current viewport height in px
 */
function _recomputeCardGeometry(viewportW, viewportH) {
  const peekHeight = _config.peekHeight;
  const landscapeSideCard = isLandscapeSideCard();
  // The fit model governs the desktop side card and nothing else: a landscape
  // phone already sizes its side card to content through the stylesheet, and
  // the portrait bottom card keeps its own geometry.
  const fitSideCard = isFitHeight()
    && !landscapeSideCard
    && getLayoutMode() !== 'vertical';

  const cards = document.querySelectorAll('.text-card');
  for (const card of cards) {
    const runPos = parseInt(card.dataset.runPosition, 10) || 0;

    if (landscapeSideCard) {
      // Landscape phone: the CSS rule sets `height: auto !important`, so the card
      // is sized to its content. Clear any stale inline height, measure the real
      // rendered height, and centre by that — the portrait `viewportH * 0.80`
      // model oversizes the card and jams it against the top on a short landscape
      // viewport. Inline !important top beats the
      // landscape rule's `top: auto !important`.
      _sizeCardToContent(card, viewportH, runPos, peekHeight, null);
    } else if (getLayoutMode() === 'vertical') {
      // getLayoutMode() reads the live matchMedia (self-initialising), so this is
      // correct even at the init-time call below — before layout-mode.js has
      // written state.layoutMode (which defaults to 'horizontal' and would wrongly
      // pick the desktop branch, jamming the portrait card at the top).
      // Portrait mobile: the card is bottom-anchored by CSS (`top: auto !important`,
      // `max-height: 40vh`). Remove any inline top so the CSS anchor wins — do NOT
      // force an !important top here, or the card detaches from the bottom on resize.
      card.style.removeProperty('top');
      card.style.removeProperty('max-height');
      card.style.height = `${viewportH * SIDE_CARD_VIEWPORT_FRACTION}px`;  // capped by the CSS max-height: 40vh
    } else if (fitSideCard) {
      // Desktop horizontal under the fit model: the viewport fraction is a
      // ceiling rather than a height, and the card takes what its content
      // needs below it. At the ceiling the card's own `overflow: hidden` and
      // `margin-block: auto` do the clipping, exactly as at the fixed height.
      _sizeCardToContent(card, viewportH, runPos, peekHeight,
        viewportH * SIDE_CARD_VIEWPORT_FRACTION);
    } else {
      // Desktop horizontal: tall side card sized to 80% of the (tall) viewport,
      // vertically centred. No base CSS `top`, so the inline value drives placement.
      const cardH = viewportH * SIDE_CARD_VIEWPORT_FRACTION;
      const topPx = computeCardTop(viewportH, cardH, runPos, peekHeight);
      card.style.setProperty('top', `${topPx}px`, 'important');
      card.style.height = `${cardH}px`;
    }
  }
}

/**
 * What kind of card a step's object asks for.
 *
 * detectCardType weighs three things, and this is where they are gathered:
 * the type the step declares for itself, the object's URL — an external
 * manifest or a source — and, for audio, the extension the audio manifest
 * records for the file on disk.
 *
 * @param {string} objectId
 * @param {Object} step - Step data
 * @param {Object} audioObjects - object_id → audio file extension
 * @returns {string} 'iiif'|'youtube'|'vimeo'|'google-drive'|'audio'
 */
function _detectStepCardType(objectId, step, audioObjects) {
  const objectData = state.objectsIndex[objectId] || {};
  const audioExt = audioObjects[objectId];
  return detectCardType({
    objectId,
    cardType: step.cardType,
    source_url: objectData.source_url || objectData.iiif_manifest || '',
    file_path: audioExt ? `objects/${objectId}.${audioExt}` : '',
  });
}

/** The plate class each player-backed card type is built with. */
const _MEDIA_PLATE_CLASSES = {
  'youtube':      'video-plate',
  'vimeo':        'video-plate',
  'google-drive': 'video-plate',
  'audio':        'audio-plate',
};

/**
 * Whether a plate holds a video or an audio player.
 *
 * The card type is the data; the `video-plate` and `audio-plate` classes are
 * the styling hook the stylesheet matches on. Asking the class list what kind
 * of object a plate holds makes a CSS rename a behaviour change, so the type
 * test reads `dataset.cardType`, which `_createViewerPlates` writes once.
 *
 * @param {HTMLElement} plate
 * @returns {boolean}
 */
function _isVideoPlate(plate) {
  return _MEDIA_PLATE_CLASSES[plate?.dataset?.cardType] === 'video-plate';
}

/** Counterpart of `_isVideoPlate` for audio. */
function _isAudioPlate(plate) {
  return plate?.dataset?.cardType === 'audio';
}

/**
 * Mark a plate that holds a player rather than an image.
 *
 * Players are one per scene, so the clip window written here is the scene's
 * first step's; later steps in the same run re-clip the running player
 * instead of rebuilding it. A plate of any other card type is left alone.
 *
 * @param {HTMLElement} plate
 * @param {string} cardType
 * @param {Object} firstStep - The scene's first step, which owns the clip
 */
function _markMediaPlate(plate, cardType, firstStep) {
  const mediaClass = _MEDIA_PLATE_CLASSES[cardType];
  if (!mediaClass) return;

  plate.classList.add(mediaClass);
  if (firstStep.clip_start) plate.dataset.clipStart = firstStep.clip_start;
  if (firstStep.clip_end) plate.dataset.clipEnd = firstStep.clip_end;
  if (firstStep.loop) plate.dataset.loop = firstStep.loop;
}

/**
 * One viewer plate per scene, not per step.
 *
 * A scene is an unbroken run of steps on one object: they share a plate, so
 * scrolling within a run never rebuilds the viewer underneath the reader.
 */
function _createViewerPlates(steps, cardStack, audioObjects) {
  // Create viewer plates (one per scene)
  for (let sceneIdx = 0; sceneIdx < state.totalScenes; sceneIdx++) {
    const firstStepIdx = state.sceneFirstStep[sceneIdx];
    const objectId = state.sceneToObject[sceneIdx];
    if (!objectId) continue;  // Title card scene — no viewer plate
    const firstStep = steps[firstStepIdx];
    const sceneCardType = _detectStepCardType(objectId, firstStep, audioObjects);

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

    // Video and audio plates carry a class and the scene's clip window
    _markMediaPlate(plate, sceneCardType, firstStep);

    cardStack.appendChild(plate);

    state.viewerPlates[sceneIdx] = plate;
  }
}

/**
 * One text card per step, stacked with a peek of the card beneath.
 *
 * Each card also records where it sits in its object's run, which is what
 * lets activateCard tell a move within one object from a move between two.
 */
function _createTextCards(steps, cardStack, audioObjects, messinessPercent) {
  // Create text cards (one per step) and track each card's place in its run.
  //
  // A run is the stretch of consecutive steps sharing one object, which is what
  // a scene is, so the counter is keyed by scene rather than by object: a story
  // that returns to an object later starts a fresh run there, and
  // computeCardTop centres the first card of every run. Keying by object would
  // carry the count across the gap and settle that card peekHeight lower for
  // each earlier appearance.
  const sceneRunPosition = {};  // scene index → next run position

  for (let stepIdx = 0; stepIdx < steps.length; stepIdx++) {
    const step = steps[stepIdx];
    const objectId = step.object || '';

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

    const objectIndex = getSceneIndex(stepIdx);

    if (!Object.hasOwn(sceneRunPosition, objectIndex)) {
      sceneRunPosition[objectIndex] = 0;
    }
    const runPos = sceneRunPosition[objectIndex];
    sceneRunPosition[objectIndex]++;
    const zIndex = _zPlan.textCardZ[stepIdx];
    const messiness = getCardMessiness(stepIdx, messinessPercent);

    const card = document.createElement('div');
    card.className = 'text-card';
    card.dataset.stepIndex = stepIdx;
    card.dataset.object = objectId;
    card.dataset.runPosition = runPos;
    card.style.zIndex = zIndex;
    card.style.transform = buildTransform(messiness, 'translateY(100vh)');
    card.dataset.messinessRot = messiness.rot;
    card.dataset.messinessOffX = messiness.offX;
    card.dataset.messinessOffY = messiness.offY;

    // `.step-data` is a hidden block the story layout renders every step into
    // at build time, with markdownify, panel triggers and layer conditions
    // already applied. Cloning out of it is what lets a card carry authored
    // markup the client cannot produce: Liquid has run, and the browser has no
    // markdown renderer. A step with no node there falls back to building the
    // content from the step data, which loses that processing.
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
  }
}

// A step that leaves x, y or zoom blank shows the whole object, and the whole
// object is a framing like any other: the image centre at zoom 1, which the
// focal target resolves to the whole image fit and centred in the region the
// text card leaves uncovered. Without these the viewer keeps whatever OSD's home
// position gives it — the image centred in the VIEWER, so a side card sits over
// one edge of it.
const _FULL_OBJECT_FRAMING = { x: 0.5, y: 0.5, zoom: 1 };

/**
 * The framing a step asks its viewer for.
 *
 * A blank x, y or zoom falls back to the whole-object framing; page is
 * 1-indexed in the story data and absent unless the object is a multi-page
 * external manifest.
 *
 * @param {Object} step - Step data
 * @returns {{ x: number, y: number, zoom: number, page: number|undefined }}
 */
function _stepFraming(step) {
  const num = (value, fallback) => {
    const n = parseFloat(value);
    return Number.isFinite(n) ? n : fallback;
  };
  return {
    x:    num(step.x,    _FULL_OBJECT_FRAMING.x),
    y:    num(step.y,    _FULL_OBJECT_FRAMING.y),
    zoom: num(step.zoom, _FULL_OBJECT_FRAMING.zoom),
    page: step.page ? parseInt(step.page, 10) : undefined,
  };
}

/**
 * The card-stack settings a story runs with.
 *
 * A story that names neither peek nor messiness gets the framework defaults:
 * a one-pixel peek of the card beneath, and a light scatter. preloadSteps is
 * site-wide rather than per-story, so it comes from the site config.
 *
 * @param {{ peekHeight: number, messiness: number }} config - Story card config
 * @returns {{ peekHeight: number, messiness: number, preloadSteps: number }}
 */
function _resolveCardConfig(config) {
  return {
    peekHeight:   config?.peekHeight ?? 1,
    messiness:    config?.messiness ?? 20,
    preloadSteps: state.config.preloadSteps || 5,
  };
}

/**
 * Build the first scene's viewer behind the intro card.
 *
 * The plate stays off-screen at translateY(100%) and only slides up when the
 * reader reaches step 0, but its viewer is created now so the image is
 * already there when the transition runs.
 *
 * @param {Array} steps - Story step data, metadata rows already filtered
 */
function _preloadFirstScenePlate(steps) {
  if (steps.length === 0) return;

  const firstStep = steps[0];
  const firstObjectId = firstStep.object || '';
  const plate = state.viewerPlates[0];
  if (!firstObjectId || !plate) return;

  const zIndex = _zPlan.plateZ[0];
  if (_isVideoPlate(plate)) {
    _initVideoInPlate(plate, firstObjectId, 0, zIndex);
  } else if (_isAudioPlate(plate)) {
    _initAudioInPlate(plate, firstObjectId, 0, zIndex);
  } else {
    const { x, y, zoom, page } = _stepFraming(firstStep);
    _initOsdInPlate(plate, firstObjectId, 0, zIndex, x, y, zoom, page);
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

  // Store for use by activateCard
  _stepsData = steps;
  // Mirror into shared state so scroll-engine can feed lerpIiifPosition the
  // same filtered array its stepIndex is computed against. The unfiltered
  // window.storyData.steps includes metadata rows, which would misalign
  // the index.
  state.stepsData = steps;
  _config = _resolveCardConfig(config);

  // Compute scene-based z-indexes — each object change starts a new scene
  // with its own z-index band, even if the object was seen before.
  _zPlan = computeZIndexPlan(steps);

  // Build scene maps (walk steps, identify scene boundaries)
  _buildSceneMaps(steps);

  // Initialise title card state maps
  state.titleCards = {};
  state.activeTitleCardIndex = null;

  // Audio object manifest: maps object_id → file extension (e.g. 'mp3').
  // Injected by story.html as window.audioObjects from _data/audio_objects.json;
  // storyData never carries it (story.html injects only steps and firstObject).
  const audioObjects = window.audioObjects || {};

  _createViewerPlates(steps, cardStack, audioObjects);

  _createTextCards(steps, cardStack, audioObjects, _config.messiness);

  _preloadFirstScenePlate(steps);

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

  // A card sized to its content is centred by a height read at init time,
  // and at init time the web fonts may still be loading: the content is laid
  // out in the fallback face, measures taller, and the card settles that much
  // below the centre of the viewport, with nothing but a resize to correct it.
  // The measurement the centring uses has to be the one the reader sees, so
  // the geometry is taken again once the fonts are in. Unconditionally: the
  // desktop side card is one card sized to its content and the landscape-phone
  // side card is another, and which of them a page has is not settled at init
  // time — a rotation between the two is a layout change away.
  if (document.fonts?.ready) {
    document.fonts.ready.then(() => {
      _recomputeCardGeometry(window.innerWidth, window.innerHeight);
    });
  }


  applyCardMotionDuration(cardStack);
}

/**
 * Build the inner HTML for a text card from step data — the fallback used
 * only when a step has no server-rendered .story-step/.step-content node to
 * clone (a data/DOM desync; every normal build emits one per step).
 *
 * Must stay selector-compatible with the server-rendered step markup that
 * downstream code keys on: .step-question, .step-answer, and
 * .panel-trigger[data-panel][data-step] (panels.js delegates on [data-panel]).
 * Intentional divergences from the server markup: content renders as escaped
 * flat text (no markdown), headings use div not h2, no viewer-warning block,
 * and layer triggers render only when layer*_button is non-empty (the server
 * falls back to a default label whenever layer content exists).
 *
 * @param {Object} step - Step data object
 * @returns {string} HTML string
 */
function buildTextCardContent(step) {
  const question = escapeHtml(step.question || '');
  const answer   = escapeHtml(step.answer   || '');

  const hasLayer1 = step.layer1_button && step.layer1_button.trim();
  const hasLayer2 = step.layer2_button && step.layer2_button.trim();

  let layerButtons = '';
  if (hasLayer1) {
    layerButtons += `<button class="panel-trigger" data-panel="layer1" data-step="${step.step}">${escapeHtml(step.layer1_button)}</button>`;
  }
  if (hasLayer2) {
    layerButtons += `<button class="panel-trigger" data-panel="layer2" data-step="${step.step}">${escapeHtml(step.layer2_button)}</button>`;
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
 * question/answer carry author CSV text whose documented contract is plain
 * text only, so both are escaped, matching buildTextCardContent. Escaping
 * here is display consistency, not an injection boundary — the same strings
 * flow unescaped through the Liquid intro TOC and the server-rendered step
 * pool.
 *
 * @param {Object} step - Step data object
 * @returns {string} HTML string
 */
function _buildTitleCardContent(step) {
  const heading = escapeHtml(step.question || '');
  const body    = escapeHtml(step.answer   || '');
  return `
    <div class="title-card-inner">
      <h2 class="title-card-heading">${heading}</h2>
      ${body ? '<p class="title-card-body">' + body + '</p>' : ''}
    </div>
  `;
}

// ── Context-sensitive card activation ────────────────────────────────────────

/**
 * The clip window a step asks a media plate for.
 *
 * A missing or unparseable value is 0, which the players read as "from the
 * start" and "to the end" respectively; loop accepts the several spellings
 * of true that reach here from a spreadsheet.
 *
 * @param {Object} step - Step data
 * @returns {{ start: number, end: number, loop: boolean }}
 */
function _stepClip(step) {
  return {
    start: parseFloat(step.clip_start) || 0,
    end:   parseFloat(step.clip_end)   || 0,
    loop:  _isTruthy(step.loop),
  };
}

/**
 * Point a plate the reader already has at this step's framing.
 *
 * Nothing slides: the scene is unchanged, so video and audio are re-clipped
 * where they stand and an IIIF viewer is animated across. The animation is
 * skipped while the scroll engine drives the viewer itself, which it does
 * frame by frame through lerpIiifPosition.
 *
 * @param {HTMLElement|null} plate - The plate for this step's scene
 * @param {string} objectId
 * @param {Object} step - Step data
 * @param {number} stepIndex
 */
function _retargetPlateForStep(plate, objectId, step, stepIndex) {
  if (_isVideoPlate(plate)) {
    const clip = _stepClip(step);
    updateVideoClip(plate, clip.start, clip.end || undefined, clip.loop);
  } else if (_isAudioPlate(plate)) {
    const clip = _stepClip(step);
    updateAudioClip(plate, clip.start, clip.end || undefined, clip.loop);
  } else if (!state.scrollDriven) {
    _animateViewerToStep(objectId, step, stepIndex);
  }
}

/**
 * Take a title card out of the active position.
 *
 * Forward it stays exactly where it is and is only marked stacked, because
 * the card arriving over it covers it completely. Backward it slides back
 * down below the viewport, because the reader is returning to what was
 * underneath it.
 *
 * @param {HTMLElement} titleCard
 * @param {'forward'|'backward'} direction
 */
function _deactivateTitleCard(titleCard, direction) {
  titleCard.classList.remove('is-active');
  if (direction === 'backward') {
    titleCard.style.transform = 'translateY(100vh)';
    titleCard.classList.remove('is-stacked');
  } else {
    titleCard.classList.add('is-stacked');
  }
}

/**
 * Hand the screen from a title card to a content step.
 *
 * A no-op unless a title card is the thing currently showing.
 *
 * @param {'forward'|'backward'} direction
 */
function _clearActiveTitleCard(direction) {
  if (state.activeTitleCardIndex == null) return;
  const prevTitle = state.titleCards[state.activeTitleCardIndex];
  if (prevTitle) _deactivateTitleCard(prevTitle, direction);
  state.activeTitleCardIndex = null;
}

/**
 * Clear the title cards standing between the reader and the intro.
 *
 * The intro sits at z-index 0, under every card in the stack, so it shows
 * only once the cards above it are off screen. A title card is
 * full-viewport, and both of its resting states — `is-active` and
 * `is-stacked` — hold it at translateY(0), so one left behind hides the
 * intro completely. The card at index 0 is the case the intro restore has
 * no other handle on: `state.textCards[0]` is undefined on a story whose
 * first step is a section.
 */
export function releaseTitleCardsForIntro() {
  _clearActiveTitleCard('backward');
  const first = state.titleCards[0];
  if (first) _deactivateTitleCard(first, 'backward');
}

/**
 * Write a card's transform with the animation suppressed.
 *
 * The reflow between killing the transition and handing it back is what makes
 * the write land as a position rather than as a move: without it the browser
 * coalesces both style changes into one and animates to the new transform. The
 * viewer plates are put in place the same way — see `_swapPlatesBackward`.
 *
 * @param {HTMLElement} el
 * @param {string} transform - Full transform string, messiness included
 */
function _snapTransform(el, transform) {
  el.style.transition = 'none';
  el.style.transform = transform;
  void el.offsetHeight;  // force reflow
  el.style.transition = '';
}

/**
 * Put the card stack in the state a walk to this step would have left it in.
 *
 * The invariant, after any navigation: the cards below the active one are
 * stacked in place at translateY(0), the cards above it are off screen below at
 * translateY(100vh), and the active one is at rest. A walk holds the invariant
 * one step at a time — each card left behind is stacked going forward and sent
 * back down going backward. A jump crosses many steps at once and has to
 * restate it for all of them, or the stack keeps the shape the reader's route
 * happened to leave and the next backward move lifts the target card from below
 * the viewport while the departing card falls past it.
 *
 * The target card is the one card this leaves alone: `activateCard` owns it, and
 * its arrival is the movement the reader is meant to see. Everything else is
 * written with the transition suppressed, so a jump stays a jump.
 *
 * @param {number} targetIndex - Step index the jump lands on
 */
export function reconcileStackForJump(targetIndex) {
  // Written in three passes over one reflow rather than a reflow per card: a
  // single forced layout commits every pending write, and a story is as long as
  // its author made it.
  const moved = [];

  for (let i = 0; i < _stepsData.length; i++) {
    if (i === targetIndex) continue;
    const el = state.textCards[i] || state.titleCards[i];
    if (!el) continue;

    const below = i < targetIndex;
    el.classList.remove('is-active');
    el.classList.toggle('is-stacked', below);
    el.style.transition = 'none';
    el.style.transform = buildTransform(
      _readCardMessiness(el),
      cardBaseFor(i, targetIndex),
    );
    moved.push(el);
  }

  if (moved.length) {
    void moved[0].offsetHeight;  // force reflow
    for (const el of moved) el.style.transition = '';
  }

  // A title card below the target is stacked under it and one above is off
  // screen, so neither holds the screen any longer. activateCard writes this
  // again when the step jumped to is itself a title card.
  if (state.activeTitleCardIndex !== targetIndex) state.activeTitleCardIndex = null;
}

/**
 * Put the viewer plates in the state a walk to this step would have left them.
 *
 * The companion to `reconcileStackForJump`, and the same invariant one layer
 * back: every plate but the one the target step is drawn on belongs off screen
 * below at `translateY(100%)`, which is where a walk writes it as the reader
 * leaves it. A jump crosses many steps at once and writes nothing, so a plate
 * the reader walked onto earlier keeps the inline `translateY(0)` that opened
 * it.
 *
 * Dropping `is-active` does not close it. That class carries `translateY(0)`
 * as well, so removing it hands the plate to a rule of lower weight than the
 * inline transform already holding it open, and the plate does not move. What
 * follows depends only on whether the target's plate covers it — which an
 * opaque full-viewport plate above it in the z-plan does, and one below it does
 * not. An audio plate is the case where it shows: its waveform is drawn over
 * the plate's own background, so a jump back across an audio step leaves it
 * across the screen.
 *
 * A plate being closed is also a plate being left, so the media on it is stood
 * down here exactly as `_swapPlatesBackward` stands it down on a walk.
 *
 * @param {number} targetIndex - Step index the jump lands on
 */
export function reconcilePlatesForJump(targetIndex) {
  const targetScene = state.stepToScene[targetIndex];
  const moved = [];

  for (const [sceneIndex, plate] of Object.entries(state.viewerPlates || {})) {
    if (!plate || Number(sceneIndex) === targetScene) continue;

    plate.classList.remove('is-active');
    plate.style.transition = 'none';
    plate.style.transform = 'translateY(100%)';
    if (_isVideoPlate(plate)) deactivateVideoCard(plate);
    else if (_isAudioPlate(plate)) deactivateAudioCard(plate);
    moved.push(plate);
  }

  // One forced layout for the whole set, so a story pays for its plates once.
  if (moved.length) {
    void moved[0].offsetHeight;  // force reflow
    for (const plate of moved) plate.style.transition = '';
  }
}

/**
 * Bring the card a backward move is about to activate into its resting place
 * without animating it.
 *
 * Backward, the card being uncovered is already parked where the covered-card
 * rule puts it and is revealed rather than lifted into place: the departing
 * card is the one that travels. A card that arrives here off screen below
 * would instead rise as the departing card falls, and two cards crossing is a
 * motion the stack never makes. Every path that leaves a card off screen under
 * the active one is meant to be reconciled before it gets here; this is the
 * backstop for one that is not.
 *
 * @param {HTMLElement} cardEl - The card the move is activating
 */
function _restoreBackwardTarget(cardEl) {
  if (!cardEl) return;
  if (cardEl.classList.contains('is-stacked') ||
      cardEl.classList.contains('is-active')) return;

  const idx = _cardStepIndex(cardEl);
  _snapTransform(cardEl, buildTransform(_readCardMessiness(cardEl),
                                        cardBaseFor(idx, idx + 1)));
}

/**
 * Scrolling into a step.
 *
 * A changed object or framing gets a new viewer plate. Anything else moves
 * the text card only and leaves the viewer where it stands, which is what
 * keeps scrolling within a scene from rebuilding the viewer under the reader.
 */
function _activateForward(index, direction, card, step, objectId,
   prevObjectId, needsNewViewer) {
  if (needsNewViewer) {
    // Full card — new viewer plate + new text card
    _activateNewViewerPlate(objectId, index, prevObjectId, step, direction);

    // Reset the object run tracker
    state.currentObjectRun = { objectId, runPosition: _cardRunPosition(card) };

    // Deactivate previous text card (keep stacked, not slide away)
    _deactivatePreviousTextCard(index, direction);

    // Deactivate active title card if transitioning from title → content (forward)
    _clearActiveTitleCard(direction);

    // Activate new text card
    _activateTextCard(card);

    updateObjectCredits(objectId);

  } else {
    // Text-only on same object
    state.currentObjectRun.runPosition = _cardRunPosition(card);

    // Deactivate previous text card (becomes stacked)
    _deactivatePreviousTextCard(index, direction);

    // Activate new text card
    _activateTextCard(card);

    // Update viewer for this step's position
    const plate = _plateForScene(getSceneIndex(index));

    // A TOC/deep-link jump hides every viewer plate before calling
    // activateCard; this same-object branch otherwise assumes the plate is
    // already on-screen and never re-shows it, leaving the viewer blank
    // after a same-object jump. Re-show it here — a no-op during
    // continuous scroll where the plate is already active.
    if (plate && !plate.classList.contains('is-active')) {
      plate.style.transform = 'translateY(0)';
      plate.classList.add('is-active');
    }

    _retargetPlateForStep(plate, objectId, step, index);
  }

}

/**
 * Slide the plate being left off, and bring the one behind it back.
 *
 * Reveal before hide: an intra-scene mode flip resolves both plates to the
 * same node, so hiding first takes it off screen and nothing brings it back.
 * That ordering is also why this is not the forward path reversed — there the
 * plate being left is the one ahead, derived from index + 1 rather than from
 * where the reader now is.
 *
 * Video plates are snapped rather than transitioned: an iframe on mobile
 * breaks the compositing a transition needs.
 */
function _swapPlatesBackward(currentPlate, prevPlate, index, prevObjectId) {
  // Different DOM elements always — slide current plate down, reveal previous
  if (currentPlate) {
    if (_isVideoPlate(currentPlate)) {
      // Snap immediately off-screen. Video/audio iframes on mobile
      // can break CSS transform transitions (compositing layer issues
      // with cross-origin iframes), so bypass the transition entirely.
      currentPlate.style.transition = 'none';
      currentPlate.style.transform = 'translateY(100%)';
      void currentPlate.offsetHeight;  // force reflow
      currentPlate.style.transition = '';
      deactivateVideoCard(currentPlate);
    } else if (_isAudioPlate(currentPlate)) {
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
    if (_isVideoPlate(prevPlate)) {
      activateVideoCard(prevPlate, getSceneIndex(index));
    } else if (_isAudioPlate(prevPlate)) {
      activateAudioCard(prevPlate, getSceneIndex(index));
    }
  }
}

function _activateBackward(index, direction, card, step, objectId,
   prevObjectId, needsNewViewer) {
  // Before anything departs: the card being uncovered has to be in place, so
  // that the only thing the reader sees move is the card leaving.
  _restoreBackwardTarget(card);

  // Backward navigation
  if (needsNewViewer) {
    // Per-scene plates: distinct scenes own distinct DOM elements. (An
    // intra-scene mode change resolves currentPlate === prevPlate; the
    // add-is-active-then-reveal-previous order below leaves the shared plate
    // active, so backward mode flips on one object stay visible.)
    // NOTE: a real backward *jump* (not yet implemented) must derive the
    // departing scene from the actual state.currentIndex, not index + 1.
    const currentSceneIndex = getSceneIndex(index + 1);
    const currentPlate = currentSceneIndex >= 0 ? state.viewerPlates[currentSceneIndex] : null;
    const prevPlate = state.viewerPlates[getSceneIndex(index)];

    _swapPlatesBackward(currentPlate, prevPlate, index, prevObjectId);

    state.currentObjectRun = { objectId, runPosition: _cardRunPosition(card) };

    // Slide current text card back down
    _deactivatePreviousTextCard(index, direction);

    // Deactivate active title card if transitioning from title → content (backward)
    _clearActiveTitleCard(direction);

    // Restore this step's text card to active
    _activateTextCard(card);

    updateObjectCredits(objectId);

  } else {
    // Same object, backward: text card slides down, previous card reactivated
    state.currentObjectRun.runPosition = _cardRunPosition(card);

    _deactivatePreviousTextCard(index, direction);
    _activateTextCard(card);

    // Update viewer for this step's position
    _retargetPlateForStep(_plateForScene(getSceneIndex(index)), objectId, step, index);
  }
}

/**
 * Whether a step needs a viewer plate of its own.
 *
 * A different object always does. So does the same object framed a
 * different way: a flip between full-object and detail is a new view of it,
 * and gets a plate rather than a pan. The first step of a story has no
 * previous framing to differ from, so only its object decides.
 *
 * @param {Object} step - Step being activated
 * @param {Object|null} prevStep - The step before it, or null at the start
 * @param {string} objectId
 * @param {string|null} prevObjectId
 * @returns {boolean}
 */
function _needsNewViewer(step, prevStep, objectId, prevObjectId) {
  const currentMode = isFullObjectMode(step);
  const prevMode = prevStep ? isFullObjectMode(prevStep) : null;
  const isModeChange = prevMode !== null && currentMode !== prevMode;
  const isObjectChange = objectId !== prevObjectId;
  // mode change on same object treated as object change
  return isObjectChange || isModeChange;
}

/**
 * Refresh the label a screen reader announces for the plate on screen.
 *
 * The label is rebuilt per step, not per plate: a step may carry its own alt
 * text for the detail it frames, and several steps share one plate.
 *
 * @param {number} index - Step index
 * @param {string} objectId
 */
function _refreshPlateAriaLabel(index, objectId) {
  const plate = state.viewerPlates[state.stepToScene[index]];
  if (!plate) return;

  const stepAlt = (_stepsData[index] || {}).alt_text || '';
  const cardType = plate.dataset.cardType || 'iiif';
  plate.setAttribute('aria-label', _buildAriaLabel(objectId, stepAlt, cardType));
}

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
  if (state.titleCards[index]) {
    _activateTitleCardStep(index, direction);
    return;
  }

  const card = state.textCards[index];
  if (!card) return;

  const step = _stepsData[index] || {};
  const prevStep = index > 0 ? _stepsData[index - 1] : null;

  const objectId = card.dataset.object;
  const prevObjectId = state.currentObjectRun.objectId;

  const needsNewViewer = _needsNewViewer(step, prevStep, objectId, prevObjectId);

  const args = [index, direction, card, step, objectId,
                prevObjectId, needsNewViewer];
  if (direction === 'forward') {
    _activateForward(...args);
  } else {
    _activateBackward(...args);
  }

  // Update aria-label on the active viewer plate for current step
  _refreshPlateAriaLabel(index, objectId);

  // Preload ahead
  preloadAhead(index, _config.preloadSteps, 2);

  // Full-object mode detection kept for mode-change → new viewer logic
  // but no layout reversal — viewer is always full-viewport, compensation handles positioning
}

// ── Per-frame interpolated positioning ────────────────────────────────────────

/**
 * Put every plate the scroll moves where this position says it belongs.
 *
 * The cards have one statement of where they belong for a position; the
 * plates need the same and for the same reason. A plate moves only across a
 * scene boundary, so nothing restates it for a position that does not cross
 * one, and a scrub that stops short leaves it wherever the last frame put it.
 * The plate behind a section card is the case with no writer at all: resting
 * on the section card, the pair in play is the section and the object after
 * it, which moves the arriving plate, while the plate the section card is
 * covering belongs clear of the top and is never named.
 *
 * Three plates are in play. The standing plate — the one behind the step the
 * position rests on — is clear of the top while a section card holds the
 * screen, on its way there while the position crosses into one, and at rest
 * otherwise. The next scene's plate is the position's own fraction of a
 * viewport up from below. The one after that is a full viewport down, which a
 * crossing would otherwise leave a pixel or two short of home.
 *
 * @param {number} stepIndex - Step the position rests on; -1 is the intro
 * @param {number} progress - Fraction of the way to the next step
 */
function _settlePlates(stepIndex, progress) {
  const place = (plate, y) => {
    if (!plate) return;
    const transform = `translateY(${y}%)`;
    if (plate.style.transform !== transform) plate.style.transform = transform;
  };

  const here  = getSceneIndex(stepIndex);
  const next  = getSceneIndex(stepIndex + 1);
  const after = getSceneIndex(stepIndex + 2);

  const standing = _standingPlate(stepIndex);
  if (_isTitleStep(stepIndex)) place(standing, -100);
  else if (_isTitleStep(stepIndex + 1)) place(standing, -progress * 100);
  else place(standing, 0);

  if (next !== here && !_isTitleStep(stepIndex + 1)) {
    place(_plateForScene(next), (1 - progress) * 100);
  }
  if (after !== next && !_isTitleStep(stepIndex + 2)) {
    place(_plateForScene(after), 100);
  }
}

/**
 * Interpolate the visual progress of a card transition each scroll frame.
 *
 * Called every frame by the scroll engine. Part way through a step this runs
 * only while the reader is scrubbing (`is-scrubbing` is set, which disables the
 * CSS transitions the per-frame writes would otherwise fight); button and
 * keyboard navigation animate on those transitions instead. On a whole step it
 * runs either way, because a step is a resting place and the cards belong on it
 * however the scroll arrived.
 *
 * @param {number} stepIndex - Current step (floor of position)
 * @param {number} progress - Fractional progress 0.0-1.0
 */
export function setCardProgress(stepIndex, progress) {
  // A whole step is a resting place, and the cards belong on it whoever brought
  // them there: the write has to happen off the scrub too, or a scroll that
  // carries on after the scrub flag has lapsed leaves the arriving card
  // wherever the last scrub frame put it.
  const cardStack = document.querySelector('.card-stack');
  const scrubbing = !!cardStack && cardStack.classList.contains('is-scrubbing');
  if (!scrubbing && progress >= 0.001) return;

  settleCards(stepIndex + 1 + progress);
}

/**
 * Put every card the scroll moves where this position says it belongs.
 *
 * One idea of settling, for every path that has to state where the cards are:
 * the scrub frame, the snap that knows its landing before it gets there, the
 * scroll that stops of its own accord, the keyboard move that has a target. The
 * position is the scroll engine's — 0 is the intro, 1 is step 0 — and the cards
 * follow from it. Three cards are in play at any position: the step it rests
 * on, at `translateY(0)` with its messiness; the one card it is part way
 * through, the proportion of a viewport up from below; and the card above that,
 * a full viewport down, which is the card the position has just stopped moving
 * and which a crossing would otherwise leave a pixel or two short of home. On a
 * whole step that is the resting invariant, and on a position between steps it
 * is the same interpolation a scrub frame writes, so a scroll that stops short
 * leaves the cards agreeing with it.
 *
 * Below position 1 the same three are the intro's: no step underneath, the
 * story's first card sliding up over the intro, and the second card waiting a
 * viewport down. The first viewer plate travels with the first card.
 *
 * The plates get the same treatment, in `_settlePlates`: a position states
 * where every plate in play stands, not only the one the step it is leaving
 * happens to move.
 *
 * The transition is left alone, so off the scrub the write is a slide from
 * wherever the card is and under `is-scrubbing` it is a position. That is what
 * makes a settle safe to run from the scrub and from the animation both.
 *
 * A settle states where a thing belongs, and where it already says that it
 * says nothing: a transform written over a transition that is running towards
 * it restarts that transition from wherever it has reached, so a settle that
 * repeats itself leaves the last per cent of a move running for another full
 * duration after the move looked finished.
 *
 * @param {number} position - Scroll position; 0 is the intro, 1 is step 0.
 */
export function settleCards(position) {
  const contentPos = position - 1;
  const stepIndex = Math.floor(contentPos);
  const progress = contentPos - stepIndex;

  // Every card the stack has, not only the pair in motion: a card below the
  // active one is where a covered card belongs, and which position that is
  // depends on whether a plate rises to cover it — so it is not always the
  // place the card was left. Card 0 up to the one waiting below is the whole
  // stack, and placing a card that is already where it belongs writes nothing.
  for (let i = 0; i <= stepIndex + 2; i++) {
    const el = i < 0 ? null : state.textCards?.[i] || state.titleCards?.[i];
    if (!el) continue;
    placeCard(el, cardBaseFor(i, stepIndex, progress));
  }

  _settlePlates(stepIndex, progress);

  for (const hook of _settleHooks) hook(stepIndex, progress);
}

/**
 * Add a settle of your own to the one the engine runs.
 *
 * The base stack moves two cards per position and leaves the rest where they
 * are. A build that moves more of them — cards of their own height, which lift
 * the stack under the active one by the same scrub progress — registers the
 * writes for those here rather than repeating the settle, so every path that
 * settles the stack settles all of it.
 *
 * @param {(stepIndex: number, progress: number) => void} hook
 * @returns {() => void} Removes the hook
 */
export function onCardsSettle(hook) {
  _settleHooks.push(hook);
  return () => {
    const at = _settleHooks.indexOf(hook);
    if (at >= 0) _settleHooks.splice(at, 1);
  };
}

// ── Private helpers ───────────────────────────────────────────────────────────

/**
 * Put a IIIF viewer where a step's framing says, now or when it is ready.
 *
 * A step with no authored position leaves the viewer alone. A viewer still
 * loading cannot be moved, so the position is left on the card for its ready
 * handler to apply, carrying the same snap-or-animate choice with it.
 *
 * @param {Object} viewerCard - The ViewerCard for the scene
 * @param {number} x - Normalised centre X
 * @param {number} y - Normalised centre Y
 * @param {number} zoom - OSD zoom multiplier
 * @param {boolean} snap - True to jump, false to animate across
 */
function _applyFramingToViewer(viewerCard, x, y, zoom, snap) {
  if (isNaN(x) || isNaN(y) || isNaN(zoom)) return;

  if (!viewerCard.isReady) {
    viewerCard.pendingZoom = { x, y, zoom, snap };
    return;
  }
  if (snap) {
    snapIiifToPosition(viewerCard, x, y, zoom);
  } else {
    animateIiifToPosition(viewerCard, x, y, zoom);
  }
}

function _wireViewerForPlate(newPlate, sceneIndex, stepIndex, objectId, step) {
  // Wire up the OSD wrapper if a ViewerCard exists for this scene
  const viewerCard = state.viewerCards.find(vc => vc.sceneIndex === sceneIndex);
  const { x, y, zoom, page } = _stepFraming(step);

  // Route to audio, video, or IIIF initialisation
  if (_isAudioPlate(newPlate)) {
    // Audio plate: initialise player if not already present
    if (!newPlate.querySelector('.waveform-container')) {
      const zIndex = _zPlan.plateZ[stepIndex];
      _initAudioInPlate(newPlate, objectId, sceneIndex, zIndex);
    }
    activateAudioCard(newPlate, sceneIndex);
  } else if (_isVideoPlate(newPlate)) {
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
  } else {
    _applyFramingToViewer(viewerCard, x, y, zoom, true);
  }
}

/**
 * Bring a plate on screen, and move the one it replaces out of the way.
 *
 * Forward, the arriving plate starts below the fold and rises. Scene 0 is
 * the exception: the intro zone may already have positioned it part-way, and
 * resetting it there would make it jump, so it is reset only when it is
 * still where it was built. Backward, the arriving plate is simply in place
 * and the plate ahead of it drops away.
 *
 * @param {HTMLElement} newPlate
 * @param {HTMLElement|null} prevPlate
 * @param {number} sceneIndex - Scene of the arriving plate
 * @param {'forward'|'backward'} direction
 */
function _slideInNewPlate(newPlate, prevPlate, sceneIndex, direction) {
  if (direction === 'forward') {
    // For scene 0: skip the reset-to-offscreen if the plate was already
    // positioned by the intro interpolation (scroll-engine intro zone progressive
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
}

/**
 * Stop the plate the reader is leaving.
 *
 * A player is stopped through its own module, which drops the active class
 * as part of that. A plain IIIF plate only loses the class: the viewer
 * inside it is kept, so returning to the scene costs nothing.
 *
 * @param {HTMLElement} plate
 */
function _deactivateDepartingPlate(plate) {
  if (_isVideoPlate(plate)) {
    deactivateVideoCard(plate);
  } else if (_isAudioPlate(plate)) {
    deactivateAudioCard(plate);
  } else {
    plate.classList.remove('is-active');
  }
}

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

  const prevPlate = _plateForScene(prevSceneIndex);
  const newPlate  = _plateForScene(sceneIndex);

  if (!newPlate) return;

  // Update plate z-index from the scene plan.
  newPlate.style.zIndex = _zPlan.plateZ[stepIndex];

  // Intra-scene mode change: a full-object↔detail flip within one object's run
  // flags needsNewViewer, but the scene — and therefore the plate element — is
  // unchanged, so prevPlate and newPlate resolve to the same node. The plate is
  // already on-screen: keep it visible and skip the slide/deactivate pair, which
  // would otherwise add then immediately strip is-active (add below, remove in
  // the prevPlate block) and blank the viewer. This surfaces on TOC/deep-link
  // jumps and on ordinary forward scroll across a zoom-in→out step on the same
  // object. The wiring below still runs: the plate may hold no viewer yet (a
  // story whose first step is a section card wires none at load), and the step's
  // framing has to reach the viewer whether or not the plate moves.
  const samePlate = prevPlate && prevPlate === newPlate;

  if (samePlate) {
    newPlate.style.transform = 'translateY(0)';
  } else {
    _slideInNewPlate(newPlate, prevPlate, sceneIndex, direction);
  }

  newPlate.classList.add('is-active');
  if (prevPlate && !samePlate) _deactivateDepartingPlate(prevPlate);

  _wireViewerForPlate(newPlate, sceneIndex, stepIndex, objectId, step);
}

/**
 * The div OSD mounts into for a plate.
 *
 * A plate evicted from the pool keeps its own element but loses this child,
 * so re-entering the scene builds a fresh one. A plate that still has one is
 * given the new viewer's id rather than a second div.
 *
 * @param {HTMLElement} plateEl
 * @param {string} viewerId
 * @returns {HTMLElement}
 */
function _viewerInstanceDiv(plateEl, viewerId) {
  const existing = plateEl.querySelector('.viewer-instance');
  if (existing) {
    existing.id = viewerId;
    return existing;
  }

  const viewerDiv = document.createElement('div');
  viewerDiv.className = 'viewer-instance';
  viewerDiv.id = viewerId;
  plateEl.appendChild(viewerDiv);
  return viewerDiv;
}

/**
 * The framing a viewer opens at, or null when the step authored none.
 *
 * Snapping rather than animating, because there is nothing yet on screen to
 * animate from.
 *
 * @param {number} x
 * @param {number} y
 * @param {number} zoom
 * @returns {{ x: number, y: number, zoom: number, snap: boolean }|null}
 */
function _initialPendingZoom(x, y, zoom) {
  if (isNaN(x) || isNaN(y) || isNaN(zoom)) return null;
  return { x, y, zoom, snap: true };
}

/**
 * Keep the viewer pool inside its cap.
 *
 * What goes is the instance farthest in scenes from the one just opened —
 * the scene the reader is least likely to reach next, in either direction.
 * The plate element itself stays in the DOM; only the viewer inside it goes.
 *
 * @param {number} currentScene - Scene the newest viewer belongs to
 */
function _evictBeyondPoolCap(currentScene) {
  while (state.viewerCards.length > state.config.maxViewerCards) {
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
  _viewerInstanceDiv(plateEl, viewerId);

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
    pendingZoom: _initialPendingZoom(x, y, zoom),
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
      // the viewer at home zoom. One frame after
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
  _evictBeyondPoolCap(sceneIndex);
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
  const audioObjects = window.audioObjects || {};
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
  const el = document.querySelector('.text-card.is-active');
  if (!el || Number(el.dataset.stepIndex) === newIndex) return;

  el.classList.remove('is-active');

  // Backward the card is the one above the step being arrived at, and travels
  // away below; forward it is the one under it, and stays where a plate rises
  // to cover it or leaves through the top where none does. Both are the same
  // question — where does this card belong now the position is at newIndex —
  // so both ask the one rule rather than stating an answer of their own. The
  // transform is written here rather than left to the stylesheet because a
  // card's transform is inline and a rule for it would lose the cascade.
  el.classList.toggle('is-stacked', direction !== 'backward');
  placeCard(el, cardBaseFor(Number(el.dataset.stepIndex), newIndex));
}

/**
 * Record the card's measured rect, and re-frame the viewer the first time there
 * is one.
 *
 * With no rect the focal target falls back to the CSS-derived default box — the
 * card's placement rule rather than its rendered geometry — so the first step of
 * a story is framed against a box a few pixels out, and at an overview those
 * pixels are image under the card. One re-snap on the first real measurement
 * puts the opening step on the same geometry every later step is framed in.
 *
 * @param {HTMLElement} cardEl - The text card element
 */
function _writeCardOverlayRect(cardEl) {
  const hadRect = state.cardOverlayRect != null;
  state.cardOverlayRect = cardEl.getBoundingClientRect();
  if (!hadRect) reSnapActiveViewer();
}

/**
 * Activate a text card — slide it up from below.
 *
 * A card that left through the top is arriving backward from above rather
 * than from below, and the transform it is leaving carries that: the
 * uncovered card holds the lifted position until this write, and the write
 * returns it to rest. Both cards in a backward move therefore travel
 * downward and neither crosses the other. A card a plate covered never left,
 * and this write finds it already at rest.
 *
 * @param {HTMLElement} cardEl - The text card element
 */
function _activateTextCard(cardEl) {
  const messiness = _readCardMessiness(cardEl);
  cardEl.classList.remove('is-stacked');
  cardEl.classList.add('is-active');

  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const isScrubbing    = document.querySelector('.card-stack')?.classList.contains('is-scrubbing');

  // Mid-scrub the lift belongs to the scroll position, not to this write: a
  // card uncovered at the boundary is one frame's worth of travel away from
  // rest, and the next frame's setCardProgress carries it the rest of the
  // way. Resting it here instead would put it home for a frame and then lift
  // it again.
  const idx = _cardStepIndex(cardEl);
  cardEl.style.transform = buildTransform(
    messiness, cardBaseFor(idx, idx, isScrubbing ? _liftProgress() : 0));

  // Write final rect to state.cardOverlayRect once the slide-up transition settles.
  // Two cases skip transitionend (it never fires when transition: none is set):
  //   1. prefers-reduced-motion: reduce  (_sass/_responsive.scss:110-126)
  //   2. .card-stack.is-scrubbing        (_sass/_story.scss:50-52)
  // In both cases the imperative style write above forces an immediate layout,
  // so getBoundingClientRect() is correct synchronously.
  if (prefersReduced || isScrubbing) {
    _writeCardOverlayRect(cardEl);
    return;
  }
  // Ensure at most one pending settle listener per card: rapid re-activation
  // would otherwise stack multiple live closures until each transition ends.
  if (cardEl._settleHandler) {
    cardEl.removeEventListener('transitionend', cardEl._settleHandler);
  }
  const onSettled = (ev) => {
    if (ev.target !== cardEl || ev.propertyName !== 'transform') return;
    cardEl.removeEventListener('transitionend', onSettled);
    cardEl._settleHandler = null;
    _writeCardOverlayRect(cardEl);
  };
  cardEl._settleHandler = onSettled;
  cardEl.addEventListener('transitionend', onSettled);
}

/**
 * Stack the title card that another title card is arriving over.
 *
 * Consecutive title cards are separate scenes, so the one being left moves
 * out of the way exactly as it would for a content step. Nothing to do when
 * the arriving card is the one already active.
 *
 * @param {number} index - Step index of the arriving title card
 * @param {'forward'|'backward'} direction
 */
function _stackPreviousTitleCard(index, direction) {
  if (state.activeTitleCardIndex == null ||
      state.activeTitleCardIndex === index) return;

  const prevTitle = state.titleCards[state.activeTitleCardIndex];
  if (prevTitle) _deactivateTitleCard(prevTitle, direction);
}

/**
 * Clear the content scene a title card is covering.
 *
 * The departing step is the one behind the title card in the reader's
 * direction of travel, so it is ahead of the index going backward. Backward
 * the plate is snapped away with the transition suppressed: the title card
 * arrives from above rather than covering it, so a slide would be seen.
 *
 * @param {number} index - Step index of the title card
 * @param {'forward'|'backward'} direction
 */
function _hideDepartingPlateForTitle(index, direction) {
  const departingStepIndex = direction === 'backward' ? index + 1 : index - 1;
  const departingSceneIndex = departingStepIndex >= 0 ? getSceneIndex(departingStepIndex) : -1;
  const departingPlate = _plateForScene(departingSceneIndex);
  if (!departingPlate) return;

  if (direction === 'backward') {
    departingPlate.style.transition = 'none';
    departingPlate.style.transform = 'translateY(100%)';
    void departingPlate.offsetHeight;
    departingPlate.style.transition = '';
  }
  _deactivateDepartingPlate(departingPlate);
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

  // A title card returned to is revealed, not raised: it is already resting
  // under whatever covered it. One that is off screen is put back in place
  // first, so it cannot rise while the departing card falls.
  if (direction === 'backward') _restoreBackwardTarget(titleCard);

  // Deactivate any previously active title card
  _stackPreviousTitleCard(index, direction);

  // Deactivate any previously active text card (content step → title card transition)
  _deactivatePreviousTextCard(index, direction);

  // Deactivate the departing content scene's viewer plate so the title card
  // is fully visible and any playing video/audio is stopped.
  _hideDepartingPlateForTitle(index, direction);

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
  const { x, y, zoom } = _stepFraming(step);

  if (isNaN(x) || isNaN(y) || isNaN(zoom)) return;

  const sceneIndex = getSceneIndex(stepIndex);
  const viewerCard = state.viewerCards.find(vc => vc.sceneIndex === sceneIndex);
  if (!viewerCard) return;

  _applyFramingToViewer(viewerCard, x, y, zoom, false);
}

// ── Preloading ────────────────────────────────────────────────────────────────

/**
 * Get one scene's plate ready before the reader arrives at it.
 *
 * Audio and video plates are cheap and idempotent -- a plate that already
 * has its player is left alone. An IIIF plate is neither, so it is skipped
 * if a viewer card already exists for the scene, and its tiles are fetched
 * alongside.
 *
 * This was written out twice, once for the scenes ahead and once for those
 * behind, in bodies that had not diverged.
 */
function _warmScene(targetScene) {
  const plate = state.viewerPlates[targetScene];
  if (!plate) return;

  const firstStepIdx = state.sceneFirstStep[targetScene];
  const step = _stepsData[firstStepIdx];

  const objectId = step.object || '';
  if (!objectId) return;

  const zIndex = _zPlan.plateZ[firstStepIdx];

  if (_isAudioPlate(plate)) {
    // Audio plate: preload only if no waveform container yet
    if (!plate.querySelector('.waveform-container')) {
      _initAudioInPlate(plate, objectId, targetScene, zIndex);
    }
  } else if (_isVideoPlate(plate)) {
    // Video plate: preload only if no video iframe yet
    if (!plate.querySelector('.video-iframe, iframe')) {
      _initVideoInPlate(plate, objectId, targetScene, zIndex);
    }
  } else {
    // IIIF plate: skip if already has a ViewerCard
    if (state.viewerCards.find(vc => vc.sceneIndex === targetScene)) return;

    const { x, y, zoom, page } = _stepFraming(step);

    _initOsdInPlate(plate, objectId, targetScene, zIndex, x, y, zoom, page);
    _prefetchTilesForScene(targetScene);
  }
}

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

    _warmScene(targetScene);
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

    _warmScene(targetScene);
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
  // De-dup: prefetch each scene at most once (also covers the early-return
  // cases below, so a no-object / external scene isn't re-checked every pass).
  if (_prefetchedScenes.has(sceneIndex)) return;
  _prefetchedScenes.add(sceneIndex);

  const objectId = state.sceneToObject[sceneIndex];
  if (!objectId) return;

  // Skip external manifests — tile URL patterns are server-specific
  const objData = state.objectsIndex[objectId];
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
 * The tiling an image service advertises.
 *
 * A service that names neither a tile size nor a set of scale factors is
 * read as one 512-pixel level, the size a Level 0 static tile set is
 * generated at.
 *
 * @param {Object} info - Parsed info.json
 * @returns {{ imageW: number, imageH: number, tileSize: number, scaleFactors: number[] }}
 */
function _tileSourceShape(info) {
  return {
    imageW:       info.width,
    imageH:       info.height,
    tileSize:     info.tiles?.[0]?.width || 512,
    scaleFactors: info.tiles?.[0]?.scaleFactors || [1],
  };
}

/**
 * The image-pixel box a step's framing puts on screen.
 *
 * The two-circle model answers with the authored focal point as centre and
 * the inscribed-circle diameter as width, so the prefetched region aligns
 * with the rendered one. A step it cannot answer for falls back to the
 * authored point and a viewport-relative estimate. Either way the box is
 * clamped to the image bounds.
 *
 * @param {number} imageW
 * @param {number} imageH
 * @param {number} x - Normalised centre X (0-1)
 * @param {number} y - Normalised centre Y (0-1)
 * @param {number} zoom - OSD zoom multiplier
 * @returns {{ left: number, top: number, right: number, bottom: number }}
 */
function _prefetchRegion(imageW, imageH, x, y, zoom) {
  // Derive cardBox and placementMode via the canonical helper in iiif-card.js.
  const vpW = window.innerWidth;
  const vpH = window.innerHeight;
  const r = state.cardOverlayRect;
  const cardBox = r ? { x: r.x, y: r.y, w: r.width, h: r.height } : null;
  const placementMode = _deriveCardPlacement(cardBox, vpW, vpH);

  const target = computeFocalTarget(x, y, zoom, imageW, imageH, cardBox, placementMode);
  let centreX, centreY, halfW, halfH;

  if (target) {
    // The authored focal circle: centre = focalImg, radius = diameterImg/2
    centreX = target.focalImg.x;
    centreY = target.focalImg.y;
    halfW   = target.diameterImg / 2;
    halfH   = target.diameterImg / 2;
  } else {
    // Raw authored (x, y) with a viewport-relative size estimate
    centreX = x * imageW;
    centreY = y * imageH;
    const pixelsPerViewportPx = 1 / (zoom * (vpW / imageW));
    halfW = (vpW * pixelsPerViewportPx) / 2;
    halfH = (vpH * pixelsPerViewportPx) / 2;
  }

  return {
    left:   Math.max(0, centreX - halfW),
    top:    Math.max(0, centreY - halfH),
    right:  Math.min(imageW, centreX + halfW),
    bottom: Math.min(imageH, centreY + halfH),
  };
}

/**
 * The coarsest level that covers a region in nine tiles or fewer.
 *
 * A higher scale factor is a lower-resolution level and so fewer tiles. The
 * first factor the service lists is the floor: a region needing more than
 * nine tiles at every level takes it anyway, and the grid walk caps what is
 * issued.
 *
 * @param {number[]} scaleFactors - Scale factors the service advertises
 * @param {number} tileSize - Tile width in image pixels at scale factor 1
 * @param {{ left: number, top: number, right: number, bottom: number }} region
 * @returns {number}
 */
function _prefetchScaleFactor(scaleFactors, tileSize, region) {
  let scaleFactor = scaleFactors[0] || 1;
  for (const sf of scaleFactors) {
    const effectiveTile = tileSize * sf;
    const tilesX = Math.ceil((region.right - region.left) / effectiveTile);
    const tilesY = Math.ceil((region.bottom - region.top) / effectiveTile);
    if (tilesX * tilesY <= 9) {
      scaleFactor = sf;
      break;
    }
  }
  return scaleFactor;
}

/**
 * The static tile URLs covering a region at one level.
 *
 * Tiles sit on the level's own grid, so the walk starts at the tile holding
 * the region's edge rather than at the edge itself. A tile the image bound
 * clips to nothing is skipped, and nine is the ceiling on what one scene
 * prefetches.
 *
 * @param {string} baseUrl - Image service base URL
 * @param {{ left: number, top: number, right: number, bottom: number }} region
 * @param {number} imageW
 * @param {number} imageH
 * @param {number} tileSize - Tile width in image pixels at scale factor 1
 * @param {number} scaleFactor
 * @returns {string[]} Array of tile URLs
 */
function _tileUrlsForRegion(baseUrl, region, imageW, imageH, tileSize, scaleFactor) {
  const effectiveTile = tileSize * scaleFactor;
  const urls = [];

  for (let tx = Math.floor(region.left / effectiveTile); tx * effectiveTile < region.right; tx++) {
    for (let ty = Math.floor(region.top / effectiveTile); ty * effectiveTile < region.bottom; ty++) {
      const rx = tx * effectiveTile;
      const ry = ty * effectiveTile;
      const rw = Math.min(effectiveTile, imageW - rx);
      const rh = Math.min(effectiveTile, imageH - ry);
      if (rw <= 0 || rh <= 0) continue;

      // Output tile size: actual pixels / scaleFactor (IIIF Level 0 static tiles)
      const outW = Math.ceil(rw / scaleFactor);

      // IIIF Image API Level 0 URL pattern:
      // {base}/{region_x},{region_y},{region_w},{region_h}/{output_w},/0/default.jpg
      const url = `${baseUrl}/${rx},${ry},${rw},${rh}/${outW},/0/default.jpg`;
      urls.push(url);

      if (urls.length >= 9) return urls; // Cap at 9 tiles
    }
  }

  return urls;
}

/**
 * IIIF Image API Level 0 tile URLs for the region a step frames.
 *
 * Four questions in order: what the image service advertises, which box of
 * image pixels the step puts on screen, the coarsest level that covers that
 * box in nine tiles, and which tiles of that level those are.
 *
 * @param {string} baseUrl - Image service base URL (e.g. origin + /iiif/objects/leviathan)
 * @param {Object} info - Parsed info.json
 * @param {number} x - Normalised centre X (0-1)
 * @param {number} y - Normalised centre Y (0-1)
 * @param {number} zoom - OSD zoom multiplier
 * @returns {string[]} Array of tile URLs
 */
function _computeTileUrls(baseUrl, info, x, y, zoom) {
  const { imageW, imageH, tileSize, scaleFactors } = _tileSourceShape(info);
  const region = _prefetchRegion(imageW, imageH, x, y, zoom);
  const scaleFactor = _prefetchScaleFactor(scaleFactors, tileSize, region);

  return _tileUrlsForRegion(baseUrl, region, imageW, imageH, tileSize, scaleFactor);
}

// Exported for unit testing under an alias without underscore (matches the
// _buildSceneMaps as buildSceneMaps pattern above).
export { _computeTileUrls as computeTileUrls };
