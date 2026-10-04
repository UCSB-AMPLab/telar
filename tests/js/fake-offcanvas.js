/**
 * A stand-in for Bootstrap's Offcanvas, for the suites that open and close
 * Telar's panels.
 *
 * It fires the same bubbling show, hide and hidden events, and holds each
 * panel mid-transition until `finishTransitions` ends it, as the real 0.3s
 * slide does. Install it as `window.bootstrap = { Offcanvas: FakeOffcanvas }`.
 *
 * @version v1.8.0
 */

const instances = new Map();
const pending = [];

export class FakeOffcanvas {
  static getInstance(el) { return instances.get(el) || null; }

  constructor(el) {
    this.el = el;
    this.shown = false;
    instances.set(el, this);
  }

  fire(name) {
    const e = new Event(`${name}.bs.offcanvas`, { bubbles: true, cancelable: true });
    this.el.dispatchEvent(e);
    return e;
  }

  show() {
    if (this.shown || this.fire('show').defaultPrevented) return;
    this.shown = true;
    this.el.classList.add('showing');
    pending.push(() => {
      this.el.classList.remove('showing');
      this.el.classList.add('show');
      this.fire('shown');
    });
  }

  hide() {
    if (!this.shown || this.fire('hide').defaultPrevented) return;
    this.shown = false;
    this.el.classList.add('hiding');
    pending.push(() => {
      this.el.classList.remove('show', 'hiding');
      this.fire('hidden');
    });
  }
}

/** End every slide in flight, as Bootstrap's transition end does. */
export function finishTransitions() {
  while (pending.length) pending.shift()();
}

/** End the oldest slide in flight alone, leaving the rest mid-transition. */
export function finishNextTransition() {
  if (pending.length) pending.shift()();
}

/** Forget every panel's shown state and any slide in flight. */
export function resetOffcanvas() {
  instances.forEach((inst) => { inst.shown = false; });
  pending.length = 0;
}
