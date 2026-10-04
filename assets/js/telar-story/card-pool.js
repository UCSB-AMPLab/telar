/**
 * Telar Story – Card Pool
 *
 * This module owns three distinct lifecycles in the card-stack layout:
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
 *   2. The plates (state.viewerPlates) — scene index → Plate, one per scene,
 *      built once and permanent. A Plate is the type its scene's object
 *      asks for, and it owns everything that type knows about itself: what
 *      its player is, how to build it, how to frame it to a step, how to
 *      stand it down. This module says when; the plate says how. Adding an
 *      object type is writing a file in plates/, not finding the places
 *      that branch.
 *
 *   3. The viewers inside the image plates. These genuinely pool: the
 *      number holding a live OpenSeadragon instance is capped at
 *      config.maxViewerCards, and when over the cap the plate farthest by
 *      scene distance from the current position is unloaded. The plate
 *      stays; only the viewer in it goes. The player types pool their own,
 *      inside their own modules, on their own caps.
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
import { updateObjectCredits } from './viewer.js';
import { getBasePath, escapeHtml } from './utils.js';
import {
  computeFocalTarget,
  reSnapActiveViewer,
  _deriveCardPlacement,
  visibleImageRegion,
  framePlacement,
} from './iiif-card.js';
import { onViewportResize, onLayoutChange, getLayoutMode, isLandscapeSideCard } from './layout-mode.js';
import { isFitHeight, applyCardMotionDuration } from './card-height.js';
import { isFullObjectMode } from './text-card.js';
import { arrangeMediaScene, measureTopBand } from './media-arrangement.js';
import { fitSideCards, sideCardBand, sideCardTop, clearAnswerFit, timeGeometryPass, watchCardContent } from './card-fit.js';
import { attachCardScroll, resetCardScroll } from './card-scroll.js';
import { MediaPlate } from './plates/media-plate.js';
import { VideoPlate } from './plates/video-plate.js';
import { AudioPlate } from './plates/audio-plate.js';
import { IiifPlate } from './plates/iiif-plate.js';

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
 * Priority: step alt_text, then object alt_text, then object title, then the
 * object id, and last what the plate type calls itself. That last one is the
 * plate's own, because it is the only step that depends on what the plate
 * holds; there is no provider in it, so a Vimeo plate and a YouTube plate are
 * both a video player.
 *
 * @param {string} objectId
 * @param {string} [stepAlt] - Per-step alt_text from _stepsData
 * @param {typeof Plate} PlateClass - The plate type this scene was built with
 * @returns {string}
 */
function _buildAriaLabel(objectId, stepAlt, PlateClass) {
  if (stepAlt) return stepAlt;
  const obj = state.objectsIndex[objectId] || {};
  if (obj.alt_text) return obj.alt_text;
  if (obj.title) return obj.title;
  if (objectId) return objectId;
  return PlateClass.ariaFallback;
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

// A viewport's worth of travel clears any card the fit model builds: its
// lower edge rests at most one padding above the viewport's bottom
// (card-fit.js, sideCardTop). The card's own rotation and offset ride along,
// so a lifted card is the same sheet at a different height rather than a
// squared-up one.

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
 * @param {{ band: number, pad: number, ceiling: number }|null} [bandGeo] - The
 *   band under the top controls, for a landscape phone's card: the card is
 *   held under its ceiling and placed below the band
 */
function _sizeCardToContent(card, viewportH, runPos, peekHeight, bandGeo = null) {
  card.style.height = '';
  if (bandGeo) card.style.maxHeight = `${bandGeo.ceiling}px`;
  else card.style.removeProperty('max-height');
  const cardH = card.offsetHeight;
  const topPx = bandGeo
    ? sideCardTop({ H: viewportH, cardH, runPos, peek: peekHeight, band: bandGeo.band, pad: bandGeo.pad })
    : computeCardTop(viewportH, cardH, runPos, peekHeight);
  card.style.setProperty('top', `${topPx}px`, 'important');
}

/**
 * Recompute the inline top and height of all currently-rendered text cards.
 *
 * Called by onViewportResize and onLayoutChange subscriptions so card geometry
 * stays correct after desktop window resize, device rotation, or layout-mode
 * flip, and by the content watch. Iterates `.text-card` DOM nodes (the DOM
 * is the reliable source of all cards regardless of state.textCards
 * population order). Tops are written with style.setProperty('top', ...,
 * 'important') so the inline value wins over the landscape side-card rule's.
 *
 * @param {number} viewportW - Current viewport width in px
 * @param {number} viewportH - Current viewport height in px
 * @param {HTMLElement[]|null} [changed] - The cards to fit; every card if null
 */
function _recomputeCardGeometry(viewportW, viewportH, changed = null) {
  timeGeometryPass(() => _geometryPass(viewportW, viewportH, changed));
}

function _geometryPass(viewportW, viewportH, changed) {
  const peekHeight = _config.peekHeight;
  const landscapeSideCard = isLandscapeSideCard();
  // The fit model governs the side card on a horizontal layout, at any
  // height (card-fit.js). A landscape phone and the portrait bottom card keep
  // their own geometry below.
  const sideFit = isFitHeight() && getLayoutMode() !== 'vertical';

  const cards = document.querySelectorAll('.text-card');
  const side = sideFit ? fitSideCards(changed || cards, { W: viewportW, H: viewportH,
    peek: peekHeight, fraction: SIDE_CARD_VIEWPORT_FRACTION, activeIndex: state.currentIndex }) : null;

  const phoneBand = _phoneBandFor(landscapeSideCard && !sideFit, viewportW, viewportH);

  if (!sideFit) {
    for (const card of cards) {
      _fitCardByLayout(card, viewportH, peekHeight, landscapeSideCard, phoneBand);
    }
  }

  // A media scene's cards can go below its player only where they were just
  // sized to their content on a horizontal layout: the arrangement is decided
  // from those heights.
  const contentSized = (sideFit || landscapeSideCard) && getLayoutMode() !== 'vertical';
  _arrangeMediaScenes(cards, viewportW, viewportH, contentSized, side);
}

/**
 * The band a landscape phone's card clears the top controls by, or null. A
 * short portrait window is not a phone held sideways and keeps the card the
 * CSS rule gives it.
 *
 * @param {boolean} eligible - A landscape side card that the fit model does not govern
 * @param {number} viewportW - Current viewport width in px
 * @param {number} viewportH - Current viewport height in px
 * @returns {{ band: number, pad: number, ceiling: number }|null}
 */
function _phoneBandFor(eligible, viewportW, viewportH) {
  return eligible && getLayoutMode() === 'vertical' && viewportW > viewportH
    ? sideCardBand({ W: viewportW, H: viewportH, fraction: SIDE_CARD_VIEWPORT_FRACTION })
    : null;
}

/**
 * Size and place one text card by the layout it is in: sized to its content
 * for a landscape side card, bottom-anchored by CSS on a portrait layout, or
 * a tall centred side card on a desktop horizontal layout.
 *
 * @param {HTMLElement} card
 * @param {number} viewportH - Current viewport height in px
 * @param {number} peekHeight - Pixels each successive card settles lower
 * @param {boolean} landscapeSideCard - The CSS rule sets the card's height to auto
 * @param {{ band: number, pad: number, ceiling: number }|null} phoneBand
 */
function _fitCardByLayout(card, viewportH, peekHeight, landscapeSideCard, phoneBand) {
  clearAnswerFit(card);
  const runPos = parseInt(card.dataset.runPosition, 10) || 0;

  if (landscapeSideCard) {
    // A landscape phone, a short portrait window, or a short window under the
    // fixed model: the CSS rule sets `height: auto !important` and the
    // ceiling, so the card is sized to its content and centred by the height
    // it renders at. A phone's ceiling and top come from the band under the
    // top controls.
    _sizeCardToContent(card, viewportH, runPos, peekHeight, phoneBand);
  } else if (getLayoutMode() === 'vertical') {
    // getLayoutMode() reads the live matchMedia (self-initialising), so this is
    // correct even when geometry runs at init — before layout-mode.js has
    // written state.layoutMode (which defaults to 'horizontal' and would wrongly
    // pick the desktop branch, jamming the portrait card at the top).
    // Portrait mobile: the card is bottom-anchored by CSS (`top: auto !important`,
    // `max-height: 40vh`). Remove any inline top so the CSS anchor wins — do NOT
    // force an !important top here, or the card detaches from the bottom on resize.
    card.style.removeProperty('top');
    card.style.removeProperty('max-height');
    card.style.height = `${viewportH * SIDE_CARD_VIEWPORT_FRACTION}px`;  // capped by the CSS max-height: 40vh
  } else {
    // Desktop horizontal: tall side card sized to 80% of the (tall) viewport,
    // vertically centred. No base CSS `top`, so the inline value drives placement.
    const cardH = viewportH * SIDE_CARD_VIEWPORT_FRACTION;
    const topPx = computeCardTop(viewportH, cardH, runPos, peekHeight);
    card.style.setProperty('top', `${topPx}px`, 'important');
    card.style.removeProperty('max-height');
    card.style.height = `${cardH}px`;
  }
}

/**
 * Arrange every media scene's cards beside or below its player, then re-place
 * each media plate's player, which reads the arrangement from the plate.
 *
 * The players are re-placed here rather than on their own resize subscription
 * because the arrangement is only known once the cards have been measured.
 *
 * @param {NodeListOf<HTMLElement>} cards - Every text card, already sized
 * @param {number} viewportW - Current viewport width in px
 * @param {number} viewportH - Current viewport height in px
 * @param {boolean} contentSized - Whether the cards were sized to their content
 *   on a horizontal layout
 * @param {{ topOf: (card: HTMLElement) => number }|null} side - The fit's placement
 */
function _arrangeMediaScenes(cards, viewportW, viewportH, contentSized, side) {
  const cardsByScene = {};
  for (const card of cards) {
    const scene = getSceneIndex(parseInt(card.dataset.stepIndex, 10));
    (cardsByScene[scene] ||= []).push(card);
  }
  const besideTop = side?.topOf ?? ((card) => computeCardTop(
    viewportH, card.offsetHeight, _cardRunPosition(card), _config.peekHeight));
  const topBand = measureTopBand(viewportW, viewportH);
  for (const [scene, plate] of Object.entries(state.viewerPlates)) {
    if (!(plate instanceof MediaPlate)) continue;
    arrangeMediaScene(plate.container, cardsByScene[scene] || [], {
      W: viewportW, H: viewportH, eligible: contentSized, besideTop, topBand,
    });
    plate.resize();
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

/** The plate class each card type is built with. */
const _PLATE_TYPES = {
  'youtube':      VideoPlate,
  'vimeo':        VideoPlate,
  'google-drive': VideoPlate,
  'audio':        AudioPlate,
};

/**
 * The plate class for a card type.
 *
 * Every type the detector does not name a player for is an image, which is the
 * default a story reaches without declaring anything.
 *
 * @param {string} cardType
 * @returns {typeof Plate}
 */
function _plateClassFor(cardType) {
  return _PLATE_TYPES[cardType] || IiifPlate;
}

/**
 * Give a plate that holds a player the clip window it opens on.
 *
 * Players are one per scene, so the window written here is the scene's first
 * step's; later steps in the same run re-clip the running player instead of
 * rebuilding it. A plate of any other card type is left alone.
 *
 * @param {HTMLElement} plate
 * @param {string} cardType
 * @param {Object} firstStep - The scene's first step, which owns the clip
 */
function _markMediaPlate(plate, cardType, firstStep) {
  if (!_PLATE_TYPES[cardType]) return;

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
    plate.setAttribute('aria-label',
      _buildAriaLabel(objectId, firstStep.alt_text, _plateClassFor(sceneCardType)));
    plate.style.transform = 'translateY(100%)';

    // Video and audio plates carry the scene's clip window
    _markMediaPlate(plate, sceneCardType, firstStep);

    cardStack.appendChild(plate);

    // A player that learns its video's aspect changes what its scene's
    // arrangement is compared at.
    if (_PLATE_TYPES[sceneCardType]) {
      plate.addEventListener('telar:media-aspect', () => {
        _recomputeCardGeometry(window.innerWidth, window.innerHeight);
      });
    }

    const PlateClass = _plateClassFor(sceneCardType);
    state.viewerPlates[sceneIdx] = new PlateClass(
      plate, objectId, sceneIdx, _zPlan.plateZ[firstStepIdx], firstStep,
    );
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
    attachCardScroll(card);
  }
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

  plate.load(firstStep);
  _evictBeyondPoolCap(0);
}

/** Removes the last init's resize, layout and content subscriptions. */
let _stopGeometryWatch = null;
/** Counts inits, so a font wait from an earlier one can tell it is stale. */
let _geometryGeneration = 0;

function _teardownGeometryWatch() {
  _stopGeometryWatch?.();
  _stopGeometryWatch = null;
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

  // Each call installs its own subscriptions and content watch; the previous
  // call's are removed first so a second init leaves one geometry pass per
  // trigger.
  _teardownGeometryWatch();
  const generation = ++_geometryGeneration;

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

  // Layout-mode events keep card geometry live; the content watch below
  // observes each card's content, never the viewport.
  const stopResize = onViewportResize(({ viewport }) => {
    _recomputeCardGeometry(viewport.w, viewport.h);
  });
  const stopLayout = onLayoutChange(({ viewport }) => {
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
      if (generation !== _geometryGeneration) return;
      _recomputeCardGeometry(window.innerWidth, window.innerHeight);
    });
  }
  const stopWatch = watchCardContent(Object.values(state.textCards), (changed) => {
    _recomputeCardGeometry(window.innerWidth, window.innerHeight, changed);
  });
  _stopGeometryWatch = () => { stopResize(); stopLayout(); stopWatch(); };

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
 * Point a plate the reader already has at this step's framing.
 *
 * Nothing slides: the scene is unchanged, so video and audio are re-clipped
 * where they stand and an IIIF viewer is animated across. The animation is
 * skipped while the scroll engine drives the viewer itself, which it does
 * frame by frame through lerpIiifPosition.
 *
 * @param {Plate|null} plate - The plate for this step's scene
 * @param {string} objectId
 * @param {Object} step - Step data
 * @param {number} stepIndex
 */
function _retargetPlateForStep(plate, objectId, step, stepIndex) {
  plate?.goToStep(step);
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

    const el = plate.container;
    el.style.transition = 'none';
    el.style.transform = 'translateY(100%)';
    plate.deactivate();
    moved.push(el);
  }

  // One forced layout for the whole set, so a story pays for its plates once.
  if (moved.length) {
    void moved[0].offsetHeight;  // force reflow
    for (const el of moved) el.style.transition = '';
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
    if (plate && !plate.container.classList.contains('is-active')) {
      plate.container.style.transform = 'translateY(0)';
      plate.container.classList.add('is-active');
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
 * A plate holding a player snaps rather than transitions, in its own
 * `onSendBack`: an iframe on mobile breaks the compositing a transition needs.
 */
function _swapPlatesBackward(currentPlate, prevPlate, index) {
  // Different DOM elements always — slide the current plate down, reveal the
  // previous one. How a plate leaves is its own: an image plate transitions,
  // a plate holding a player snaps, because an iframe on mobile breaks the
  // compositing a transition needs.
  currentPlate?.sendBack();
  if (prevPlate) {
    const el = prevPlate.container;
    el.style.zIndex = _zPlan.plateZ[index];
    // Snap to position without animation — the plate was offscreen
    // from the forward transition and should appear instantly behind
    // the departing plate.
    el.style.transition = 'none';
    el.style.transform = 'translateY(0)';
    void el.offsetHeight; // force reflow
    el.style.transition = '';
    el.classList.add('is-active');
    // A plate holding a player has to re-lay-out and restart it. An image
    // plate needs nothing: its viewer is kept, and the framing it holds is
    // the one it was left on, which is the step being returned to.
    if (prevPlate instanceof MediaPlate) prevPlate.center();
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

    _swapPlatesBackward(currentPlate, prevPlate, index);

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
  plate.container.setAttribute('aria-label',
    _buildAriaLabel(objectId, stepAlt, plate.constructor));
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
    const el = plate.container;
    const transform = `translateY(${y}%)`;
    if (el.style.transform !== transform) el.style.transform = transform;
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
 * Hand a plate the step it has arrived on.
 *
 * The pool has already moved the element; what the plate does inside it —
 * build a player, start it, frame a viewer, or nothing because it is already
 * where it should be — is the plate's own business.
 *
 * The cap is checked afterwards whatever the type: only plates holding a live
 * viewer count towards it, so a plate that holds a player passes through.
 *
 * @param {Plate} newPlate
 * @param {number} sceneIndex
 * @param {Object} step - Step data
 */
function _wireViewerForPlate(newPlate, sceneIndex, step) {
  newPlate.center(step);
  _evictBeyondPoolCap(sceneIndex);
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
  const el = newPlate.container;
  if (direction === 'forward') {
    // For scene 0: skip the reset-to-offscreen if the plate was already
    // positioned by the intro interpolation (scroll-engine intro zone progressive
    // positioning). Scenes 1+ always start clean at translateY(100%).
    if (sceneIndex === 0) {
      const currentTransform = el.style.transform;
      if (!currentTransform || currentTransform === 'translateY(100%)') {
        el.style.transform = 'translateY(100%)';
        void el.offsetHeight; // Force reflow so CSS transition fires
      }
    } else {
      el.style.transform = 'translateY(100%)';
      void el.offsetHeight; // Force reflow so CSS transition fires
    }
    el.style.transform = 'translateY(0)';
  } else {
    el.style.transform = 'translateY(0)';
    if (prevPlate) {
      prevPlate.container.style.transform = 'translateY(100%)';
    }
  }
}

/**
 * Stop the plate the reader is leaving.
 *
 * The plate stays where it is: forward, the arriving plate covers it, so
 * nothing has to move. A plate holding a player stops it; an image plate only
 * loses the active class, because the viewer inside it is kept and returning
 * to the scene then costs nothing.
 *
 * @param {Plate} plate
 */
function _deactivateDepartingPlate(plate) {
  plate.deactivate();
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
  newPlate.container.style.zIndex = _zPlan.plateZ[stepIndex];

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
    newPlate.container.style.transform = 'translateY(0)';
  } else {
    _slideInNewPlate(newPlate, prevPlate, sceneIndex, direction);
  }

  newPlate.container.classList.add('is-active');
  if (prevPlate && !samePlate) _deactivateDepartingPlate(prevPlate);

  _wireViewerForPlate(newPlate, sceneIndex, step);
}

/**
 * Keep the viewer pool inside its cap.
 *
 * What goes is the viewer farthest in scenes from the one just opened — the
 * scene the reader is least likely to reach next, in either direction. The
 * plate itself is permanent and stays where it is; only the viewer inside it
 * goes, and re-entering the scene builds another.
 *
 * Counted over the plates rather than over a list of viewers, because the
 * plate holding a viewer and the viewer are now one thing.
 *
 * @param {number} currentScene - Scene the newest viewer belongs to
 */
function _evictBeyondPoolCap(currentScene) {
  const loaded = () => Object.values(state.viewerPlates)
    .filter(p => p instanceof IiifPlate && p.osdWrapper);

  let live = loaded();
  while (live.length > state.config.maxViewerCards) {
    let farthest = live[0];
    let maxDist = -1;
    for (const plate of live) {
      const dist = Math.abs(plate.sceneIndex - currentScene);
      if (dist > maxDist) {
        maxDist = dist;
        farthest = plate;
      }
    }
    farthest.unload();
    live = loaded();
  }
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
  resetCardScroll(cardEl);
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
    const el = departingPlate.container;
    el.style.transition = 'none';
    el.style.transform = 'translateY(100%)';
    void el.offsetHeight;
    el.style.transition = '';
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

// ── Preloading ────────────────────────────────────────────────────────────────

/**
 * Get one scene's plate ready before the reader arrives at it.
 *
 * A plate holding a player is asked to load and answers for itself whether
 * there is anything to do. An IIIF plate is not idempotent, so it is skipped
 * when a viewer card already exists for the scene, and its tiles are fetched
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

  plate.load(step);
  _evictBeyondPoolCap(targetScene);

  // Tiles are an image plate's business: a scene holding a player has none to
  // fetch, and asking for its info.json is a 404 nothing reads.
  if (plate instanceof IiifPlate) _prefetchTilesForScene(targetScene);
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

      const urls = _computeTileUrls(baseUrl, info, x, y, zoom, _plateViewerSize(sceneIndex));
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
 * The size a scene's viewer is framed in: its plate's content box, which the
 * viewer fills, or the window while the plate has no layout.
 *
 * @param {number} sceneIndex
 * @returns {{ width: number, height: number }}
 */
function _plateViewerSize(sceneIndex) {
  const el = state.viewerPlates?.[sceneIndex]?.container;
  if (el?.clientWidth > 0 && el.clientHeight > 0) {
    return { width: el.clientWidth, height: el.clientHeight };
  }
  return { width: window.innerWidth, height: window.innerHeight };
}

/**
 * The tiling an image service advertises.
 *
 * A service that names neither a tile size nor a set of scale factors is
 * read as one 512-pixel level, the size a Level 0 static tile set is
 * generated at.
 *
 * @param {Object} info - Parsed info.json
 * @returns {{ imageW: number, imageH: number, tileSize: number, scaleFactors: number[], version: number }}
 */
function _tileSourceShape(info) {
  return {
    imageW:       info.width,
    imageH:       info.height,
    tileSize:     info.tiles?.[0]?.width || 512,
    scaleFactors: info.tiles?.[0]?.scaleFactors || [1],
    version:      _imageApiVersion(info),
  };
}

/**
 * The IIIF Image API version an info.json describes: 3 where its context or
 * type says so, 2 otherwise.
 *
 * @param {Object} info - Parsed info.json
 * @returns {2|3}
 */
function _imageApiVersion(info) {
  const context = [].concat(info['@context'] || []).join(' ');
  return (context.includes('/image/3/') || info.type === 'ImageService3') ? 3 : 2;
}

/**
 * A static tile's URL, named as the viewer names it.
 *
 * A static tile set holds one file per name the viewer asks for, so a
 * prefetch under any other name fetches nothing the viewer will use: it is
 * not found. OpenSeadragon asks for a level narrower and shorter than one tile
 * as the whole image at that level's size; a tile that is the whole image as
 * region `full`; and a tile's size as `w,h` under API 3 and `w,` under API 2,
 * except that the image's own full size is `max` under 3 and `full` under 2
 * (where the width alone matches).
 *
 * @param {string} baseUrl - Image service base URL
 * @param {{ imageW: number, imageH: number, tileSize: number, version: number }} shape
 * @param {{ x: number, y: number, w: number, h: number }} tile - Image px
 * @param {number} scaleFactor
 * @returns {string}
 */
function _tileUrl(baseUrl, { imageW, imageH, tileSize, version }, tile, scaleFactor) {
  const levelW = Math.ceil(imageW / scaleFactor);
  const levelH = Math.ceil(imageH / scaleFactor);
  const oneTile = levelW < tileSize && levelH < tileSize;

  const region = oneTile || (tile.x === 0 && tile.y === 0 && tile.w === imageW && tile.h === imageH)
    ? 'full'
    : `${tile.x},${tile.y},${tile.w},${tile.h}`;

  // Output pixels: the level's own size for a level under one tile, and
  // otherwise the tile's image px at this level's scale.
  const outW = oneTile ? levelW : Math.ceil(tile.w / scaleFactor);
  const outH = oneTile ? levelH : Math.ceil(tile.h / scaleFactor);
  let size;
  if (version === 3) {
    size = (outW === imageW && outH === imageH) ? 'max' : `${outW},${outH}`;
  } else {
    size = outW === imageW ? 'full' : `${outW},`;
  }

  return `${baseUrl}/${region}/${size}/0/default.jpg`;
}

/**
 * The image-pixel box a step's framing puts on screen, and the scale it is
 * shown at.
 *
 * Where the framing can be computed, the box is what the viewer shows at rest:
 * visibleImageRegion is the rectangle the viewer is fitted to, cut to the
 * image, and the scale is the placement's own (viewer px per image px). A step
 * it cannot answer for falls back to the authored point and a viewport-relative
 * estimate, clamped to the image bounds, at the scale that estimate assumes.
 *
 * @param {number} imageW
 * @param {number} imageH
 * @param {number} x - Normalised centre X (0-1)
 * @param {number} y - Normalised centre Y (0-1)
 * @param {number} zoom - OSD zoom multiplier
 * @param {{ width: number, height: number }} [container] - The viewer's size,
 *   the window's where not given.
 * @returns {{ region: { left: number, top: number, right: number, bottom: number },
 *   scale: number }}
 */
function _prefetchFraming(imageW, imageH, x, y, zoom, container) {
  // Derive cardBox and placementMode via the canonical helper in iiif-card.js.
  const vpW = window.innerWidth;
  const vpH = window.innerHeight;
  const r = state.cardOverlayRect;
  const cardBox = r ? { x: r.x, y: r.y, w: r.width, h: r.height } : null;
  const placementMode = _deriveCardPlacement(cardBox, vpW, vpH);
  const viewer = container || { width: vpW, height: vpH };

  const target = computeFocalTarget(x, y, zoom, imageW, imageH, cardBox, placementMode);
  const shown = target && visibleImageRegion(target, zoom, viewer);
  if (shown) return { region: shown, scale: framePlacement(target, zoom, viewer).s };

  // Raw authored (x, y) with a viewport-relative size estimate
  const centreX = x * imageW;
  const centreY = y * imageH;
  const scale = zoom * (vpW / imageW);
  const halfW = vpW / scale / 2;
  const halfH = vpH / scale / 2;

  return {
    region: {
      left:   Math.max(0, centreX - halfW),
      top:    Math.max(0, centreY - halfH),
      right:  Math.min(imageW, centreX + halfW),
      bottom: Math.min(imageH, centreY + halfH),
    },
    scale,
  };
}

/**
 * The image-pixel box a step's framing puts on screen (see _prefetchFraming).
 *
 * @param {number} imageW
 * @param {number} imageH
 * @param {number} x - Normalised centre X (0-1)
 * @param {number} y - Normalised centre Y (0-1)
 * @param {number} zoom - OSD zoom multiplier
 * @param {{ width: number, height: number }} [container]
 * @returns {{ left: number, top: number, right: number, bottom: number }}
 */
function _prefetchRegion(imageW, imageH, x, y, zoom, container) {
  return _prefetchFraming(imageW, imageH, x, y, zoom, container).region;
}

/**
 * The finest level OpenSeadragon draws is the one whose pixels it shows at no
 * less than this many screen pixels each (its minPixelRatio, left at the
 * default by the viewer).
 */
const OSD_MIN_PIXEL_RATIO = 0.5;

/**
 * The scale factor OpenSeadragon draws a tiled IIIF source at once the viewer
 * has settled.
 *
 * Levels are powers of two: the finest is the log2 of the largest scale
 * factor (rounded), and level L has scale factor 2^(max - L). The drawn level
 * is the finest whose pixels are shown at OSD_MIN_PIXEL_RATIO or more screen
 * pixels each, the display's pixel density included:
 * TiledImage._getLevelsInterval takes |floor(log2(ratio at level 0 /
 * minPixelRatio))|, capped at the finest level. The ratio at level L is
 * density x scale x 2^(max - L), scale being viewer px per image px. Scale
 * factors are a set, so only the largest is read. The level is the viewer's
 * whether or not the service lists its scale factor.
 *
 * @param {number[]} scaleFactors - Scale factors the service advertises
 * @param {number} scale - Viewer px per image px at the settled framing
 * @returns {number}
 */
function _drawnScaleFactor(scaleFactors, scale) {
  const maxLevel = Math.round(Math.log(Math.max(...scaleFactors, 1)) * Math.LOG2E);
  const density = Math.max(window.devicePixelRatio || 1, 1);
  const ratioAtLevel0 = density * scale * Math.pow(2, maxLevel);
  const level = Math.min(
    Math.abs(maxLevel),
    Math.abs(Math.floor(Math.log(ratioAtLevel0 / OSD_MIN_PIXEL_RATIO) / Math.log(2))),
  );
  return Math.pow(2, maxLevel - level);
}

/**
 * The cells of a level's tile grid OpenSeadragon walks for a region.
 *
 * Its walk runs from the cell holding the region's top-left corner to the cell
 * holding its bottom-right, both ends inclusive, so an edge that lies exactly
 * on a grid line also takes the cell that starts there. A corner at or past
 * the image's far edge takes the last cell.
 *
 * @param {{ left: number, top: number, right: number, bottom: number }} region
 * @param {number} effectiveTile - Tile width in image pixels at this level
 * @param {number} imageW
 * @param {number} imageH
 * @returns {{ x0: number, x1: number, y0: number, y1: number }} Inclusive-start,
 *   exclusive-end indices
 */
function _cellRange(region, effectiveTile, imageW, imageH) {
  const columns = Math.ceil(imageW / effectiveTile);
  const rows = Math.ceil(imageH / effectiveTile);
  return {
    x0: Math.min(Math.floor(region.left / effectiveTile), columns - 1),
    x1: Math.min(Math.floor(region.right / effectiveTile), columns - 1) + 1,
    y0: Math.min(Math.floor(region.top / effectiveTile), rows - 1),
    y1: Math.min(Math.floor(region.bottom / effectiveTile), rows - 1) + 1,
  };
}

/**
 * The most cells one scene prefetches.
 *
 * The level OpenSeadragon draws shows each of its pixels at no less than
 * OSD_MIN_PIXEL_RATIO screen pixels, so a tile spans at least half its width
 * in viewer px (less the pixel density) and the viewer holds at most
 * ceil(size / that) tiles along an axis, plus one for the grid line it
 * straddles. The bound only bites where the framing is degenerate.
 *
 * @param {number} tileSize - Tile width in level pixels
 * @param {{ width: number, height: number }} viewer
 * @returns {number}
 */
function _cellBound(tileSize, viewer) {
  const density = Math.max(window.devicePixelRatio || 1, 1);
  const smallestTile = (tileSize * OSD_MIN_PIXEL_RATIO) / density;
  return (Math.ceil(viewer.width / smallestTile) + 1) * (Math.ceil(viewer.height / smallestTile) + 1);
}

/**
 * The static tile URLs covering a region at one level.
 *
 * Tiles sit on the level's own grid, so the walk starts at the cell holding
 * the region's edge rather than at the edge itself. A tile the image bound
 * clips to nothing is skipped, and the count is held to `limit`.
 *
 * @param {string} baseUrl - Image service base URL
 * @param {{ left: number, top: number, right: number, bottom: number }} region
 * @param {{ imageW: number, imageH: number, tileSize: number, version: number }} shape
 * @param {number} scaleFactor
 * @param {number} limit - Most tiles to issue
 * @returns {string[]} Array of tile URLs
 */
function _tileUrlsForRegion(baseUrl, region, shape, scaleFactor, limit) {
  const { imageW, imageH, tileSize } = shape;
  const effectiveTile = tileSize * scaleFactor;
  const { x0, x1, y0, y1 } = _cellRange(region, effectiveTile, imageW, imageH);
  const urls = [];

  for (let tx = x0; tx < x1; tx++) {
    for (let ty = y0; ty < y1; ty++) {
      const rx = tx * effectiveTile;
      const ry = ty * effectiveTile;
      const rw = Math.min(effectiveTile, imageW - rx);
      const rh = Math.min(effectiveTile, imageH - ry);
      if (rw <= 0 || rh <= 0) continue;

      urls.push(_tileUrl(baseUrl, shape, { x: rx, y: ry, w: rw, h: rh }, scaleFactor));

      if (urls.length >= limit) return urls;
    }
  }

  return urls;
}

/**
 * IIIF Image API Level 0 tile URLs for the region a step frames.
 *
 * Four questions in order: what the image service advertises, which box of
 * image pixels the step puts on screen and at what scale, the level
 * OpenSeadragon draws at that scale, and which tiles of that level the box
 * meets.
 *
 * @param {string} baseUrl - Image service base URL (e.g. origin + /iiif/objects/leviathan)
 * @param {Object} info - Parsed info.json
 * @param {number} x - Normalised centre X (0-1)
 * @param {number} y - Normalised centre Y (0-1)
 * @param {number} zoom - OSD zoom multiplier
 * @param {{ width: number, height: number }} [container] - The viewer's size,
 *   the window's where not given.
 * @returns {string[]} Array of tile URLs
 */
function _computeTileUrls(baseUrl, info, x, y, zoom, container) {
  const shape = _tileSourceShape(info);
  const viewer = container || { width: window.innerWidth, height: window.innerHeight };
  const { region, scale } = _prefetchFraming(shape.imageW, shape.imageH, x, y, zoom, viewer);
  const scaleFactor = _drawnScaleFactor(shape.scaleFactors, scale);

  return _tileUrlsForRegion(baseUrl, region, shape, scaleFactor, _cellBound(shape.tileSize, viewer));
}

// Exported for unit testing under an alias without underscore (matches the
// _buildSceneMaps as buildSceneMaps pattern above).
export { _computeTileUrls as computeTileUrls, _prefetchRegion as prefetchRegion };
