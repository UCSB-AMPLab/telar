/**
 * Telar Story – Card height and card motion
 *
 * Two switches, read once per page load, for the two figures the desktop card
 * stack is built around. Both exist while the release cycle settles them and
 * neither is meant to outlive it; with no switch a page gets what the
 * framework ships.
 *
 *   height — the desktop side card takes the height its content needs, with
 *            80% of the viewport as its ceiling rather than its height.
 *            `?cardheight=fixed`, or `window.__TELAR_CARD_HEIGHT__` set to
 *            'fixed' before the bundle runs, returns the stack to the fixed
 *            80% box, so a site can be held against the old geometry while
 *            the new one is in the field.
 *
 *   motion — how long a card's slide, a covered card's lift and a plate's
 *            travel take. They are one movement seen from three places and
 *            take one duration, which the stylesheet holds as
 *            `--card-motion-duration`. With no switch that duration is the
 *            pace of a programmatic move to a step, which scroll-engine.js
 *            owns: the card is part of the same movement and follows it
 *            rather than keeping a second copy of the figure.
 *            `?cardmotion=0.9` gives the card a duration of its own, for
 *            trying one deliberately out of step with the move.
 *
 * Each switch is resolved on the first call and held, so a history write or a
 * hash change cannot move the card stack between two models mid-read.
 *
 * @version v1.8.0
 */

import { navSeconds } from './state.js';

/** @type {'fit'|'fixed'|null} */
let _height = null;

/** @type {number|null|undefined} */
let _motion = undefined;

/**
 * The card duration the switch will accept, in seconds. Below the floor the
 * slide is a jump and the cards arrive with no motion to read; above the
 * ceiling a reader moving at any pace outruns them.
 */
const MOTION_MIN = 0.1;
const MOTION_MAX = 20;

/**
 * The query string, or null where the page will not give us one.
 *
 * @returns {URLSearchParams|null}
 */
function _params() {
  if (typeof window === 'undefined') return null;
  try {
    return new URLSearchParams(window.location.search);
  } catch {
    return null;
  }
}

/**
 * Read the height switch from the two places it may be written.
 *
 * @returns {'fit'|'fixed'}
 */
function _readHeight() {
  if (typeof window === 'undefined') return 'fit';

  const global = window.__TELAR_CARD_HEIGHT__;
  if (global != null) {
    const v = typeof global === 'object' ? global.height : global;
    return String(v || '').toLowerCase() === 'fixed' ? 'fixed' : 'fit';
  }

  const params = _params();
  if (!params) return 'fit';
  return String(params.get('cardheight') || '').toLowerCase() === 'fixed' ? 'fixed' : 'fit';
}

/**
 * Read the card-motion switch.
 *
 * @returns {number|null} A duration in seconds, or null to follow the move
 */
function _readMotion() {
  const params = _params();
  if (!params || !params.has('cardmotion')) return null;

  const seconds = parseFloat(params.get('cardmotion'));
  if (!Number.isFinite(seconds)) return null;
  if (seconds < MOTION_MIN || seconds > MOTION_MAX) return null;
  return seconds;
}

/**
 * Whether the side card takes the height its content needs.
 *
 * @returns {boolean}
 */
export function isFitHeight() {
  if (_height === null) _height = _readHeight();
  return _height === 'fit';
}

/**
 * How long a card's motion runs, in seconds.
 *
 * The pace of a programmatic move to a step unless the switch says otherwise:
 * a keyboard move carries the scroll, the viewer's pan and zoom follows the
 * scroll, and the card is the third face of that one movement. Reading the
 * pace rather than restating it is what keeps the three from drifting apart
 * when the pace changes.
 *
 * @returns {number}
 */
export function cardMotionSeconds() {
  if (_motion === undefined) _motion = _readMotion();
  return _motion === null ? navSeconds().keyboard : _motion;
}

/**
 * Hand the card stack the duration its motion runs on.
 *
 * The stylesheet declares `--card-motion-duration` on the stack and every
 * transition for a card or a plate reads it there, so one write moves all of
 * them together. The figure the stylesheet declares is only what stands until
 * this runs.
 *
 * @param {HTMLElement|null} cardStack
 */
export function applyCardMotionDuration(cardStack) {
  if (!cardStack) return;
  cardStack.style.setProperty('--card-motion-duration', `${cardMotionSeconds()}s`);
}
