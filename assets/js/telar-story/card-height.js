/**
 * Telar Story – Card motion
 *
 * How long the move under way takes, held where every face of it reads it. A
 * card's slide, a covered card's lift, a plate's travel, the intro's slide,
 * the scroll and the camera are one movement, so they run for one duration:
 * the stylesheet reads it as `--card-motion-duration` on the card stack, and
 * the scroll engine and the phone's camera read it here.
 *
 * It is set once per move, by the path that starts the move, before the move
 * starts any transition. A card transition already running keeps the
 * duration it started with; the active card's measured rect is replaced when
 * its transition ends, and the camera reads that rect on every frame, so a
 * camera that outlasted its card would re-frame part way through.
 *
 * @version v1.8.0
 */

import { moveSeconds } from './state.js';

/** The duration of the move under way, in seconds. */
let _seconds = moveSeconds(0);

/**
 * State the duration of the move about to start.
 *
 * @param {number} seconds
 * @param {HTMLElement|null} [cardStack] - The stack the stylesheet reads it on
 */
export function setMoveSeconds(seconds, cardStack = document.querySelector('.card-stack')) {
  _seconds = seconds;
  cardStack?.style.setProperty('--card-motion-duration', `${seconds}s`);
}

/**
 * The duration of the move under way, in seconds.
 *
 * @returns {number}
 */
export function moveSecondsNow() {
  return _seconds;
}
