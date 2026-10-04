/**
 * Telar Story — Media Plate
 *
 * What a plate holding a player has in common, whichever player it is.
 *
 * `Plate.load()` caches a promise and answers from it forever after. That is
 * right where the plate owns its player and wrong here: `video-card.js` and
 * `audio-card.js` each keep their own pool, capped at three and evicted from
 * inside themselves, so a player can go without the plate being told. The pool
 * is the only thing that knows, and `_hasPlayer` is where each subclass asks it.
 *
 * The plate also leaves by snapping rather than transitioning. A cross-origin
 * iframe on mobile breaks the compositing a CSS transform transition needs, so
 * the transition is suppressed for the move and restored after it.
 *
 * @version v1.8.0
 */

import { Plate } from './base-plate.js';

/** Normalise truthy loop values from CSV/JSON: "true", "TRUE", "yes", "sí", true → true */
export function isTruthy(val) {
  if (val === true) return true;
  if (typeof val === 'string') {
    const v = val.trim().toLowerCase();
    return v === 'true' || v === 'yes' || v === 'sí';
  }
  return false;
}

/**
 * The clip window a step asks its player for.
 *
 * @param {Object} step - Step data
 * @returns {{ start: number, end: number, loop: boolean }}
 */
export function stepClip(step) {
  return {
    start: parseFloat(step.clip_start) || 0,
    end:   parseFloat(step.clip_end)   || 0,
    loop:  isTruthy(step.loop),
  };
}

export class MediaPlate extends Plate {

  /**
   * Build the player unless one is already there.
   *
   * Synchronous, and not the base class's cached promise: see the module note.
   * Answers true while a build is still in flight, because each module pools
   * its wrapper before the file loads — which is what turns the second of two
   * callers away when a reader crosses several steps at once.
   */
  load() {
    if (this._hasPlayer()) return;
    this._build();
  }

  /** Stand down, and stop the player rather than leaving it running unseen. */
  deactivate() {
    super.deactivate();
    this._deactivatePlayer();
  }

  /**
   * Stand down and go back below the fold.
   *
   * The base class writes the transform and lets the transition carry it;
   * `onSendBack` here does the move instead, so this does not call up.
   */
  sendBack() {
    this.deactivate();
    this.onSendBack();
  }

  /** Off screen in one frame, with the transition suppressed for the move. */
  onSendBack() {
    const el = this.container;
    el.style.transition = 'none';
    el.style.transform = 'translateY(100%)';
    void el.offsetHeight;  // force reflow
    el.style.transition = '';
  }

  /** Whether this plate's module still holds a player for it. */
  _hasPlayer() { return false; }

  /** Stop the player where it stands. */
  _deactivatePlayer() {}
}
