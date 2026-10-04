/**
 * Telar Story – Move planning
 *
 * Where a key press sends the scroll and how long a move between two scroll
 * positions takes. Both are functions of their arguments and the story's
 * camera travel, with no scroll-engine state, which is why the engine imports
 * them rather than holding them.
 *
 * @version v1.8.0
 */

import { moveSeconds } from './state.js';
import { setMoveSeconds } from './card-height.js';
import { travelBetween } from './camera-travel.js';

/**
 * Time a move between two scroll positions by the camera travel it carries,
 * and state that duration for the cards and the camera before the move starts
 * either. The position is one viewport per step with the intro at 0, so step
 * indices are one less.
 *
 * @param {number} from - Scroll position the move leaves
 * @param {number} to - Scroll position it lands on
 * @returns {number} Seconds
 */
export function timeMove(from, to) {
  const seconds = moveSeconds(travelBetween(from - 1, to - 1));
  setMoveSeconds(seconds);
  return seconds;
}

/**
 * The scroll position a key press moves to, before clamping.
 *
 * A move of the keyboard's own is stepped from where it is going, not from
 * where it has reached. Anything else — a scroll at rest, or one the reader
 * left part way — is read from the position, which is the only account of it
 * there is: a position on a step moves a whole step, and one between steps
 * moves to the next step in the direction of the press.
 *
 * @param {'forward'|'backward'} direction
 * @param {number|null} inFlight - The target of the keyboard move under way, if any.
 * @param {number} position - The scroll position, in viewports.
 */
export function keyboardTarget(direction, inFlight, position) {
  const step = direction === 'forward' ? 1 : -1;
  if (inFlight !== null) return inFlight + step;
  const rounded = Math.round(position);
  if (Math.abs(position - rounded) < 0.01) return rounded + step;
  return direction === 'forward' ? Math.ceil(position) : Math.floor(position);
}
