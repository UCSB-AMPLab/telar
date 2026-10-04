/**
 * Telar Story — Base Plate
 *
 * One viewer for a scene. The instance is permanent; its player loads/unloads.
 *
 * Two axes:
 *   load / unload      — the player (libraries + file + GPU)
 *   center / sendBack  — the visual position
 *
 * A plate type says what its player is and how to build, frame and free it;
 * the card pool says when. Everything a type knows about itself lives in its
 * subclass, so adding one is writing a file rather than finding the places
 * that branch.
 *
 * Written by Ana María Cárdenas Gasca on the `telar_refactoring_proposal`
 * branch, commit 016462b, alongside the 3D plate that motivated it. Ported
 * with one addition: `deactivate`, because the card pool has two ways of
 * standing a plate down and her interface has one. Forward, the plate the
 * reader leaves stays exactly where it is and is covered by the plate
 * arriving over it, so it is stood down without moving. `sendBack` is the
 * other way — stood down *and* put back below the fold — and is now defined
 * in terms of it.
 *
 * @version v1.8.0
 */

export class Plate {

  static containerClass = 'base-plate';
  /** What a screen reader is told this is, when the object says nothing. */
  static ariaFallback = 'Viewer';
  static deps = () => Promise.resolve();   // libraries this type needs (subclass overrides)

  constructor(container, objectId, sceneIndex, zIndex, initialStep) {
    this.container = container;
    this.objectId = objectId;
    this.sceneIndex = sceneIndex;
    this.zIndex = zIndex;
    this._currentStep = initialStep;
    this._loaded = null;          // the load promise; truthy means loaded or loading
    container.classList.add(this.constructor.containerClass);
  }

  /** Idempotent: load libraries + build the player once. Safe to call repeatedly. */
  load() {
    if (this._loaded) return this._loaded;
    this._loaded = this.constructor.deps().then(() => this._build());
    return this._loaded;
  }

  /** Tear down the player + free GPU; a later load() rebuilds. */
  unload() {
    if (!this._loaded) return;
    this._teardown();
    this._loaded = null;
    this.container.querySelector('.telar-alert')?.remove();
    delete this.container.dataset.loading;
  }

  /** Bring to the front and frame to a step (loads if needed; camera catches up on load). */
  center(step) {
    this.load();
    this.container.style.zIndex = this.zIndex;
    this.container.style.transform = 'translateY(0)';
    this.container.classList.add('is-active');
    this.goToStep(step, false);
  }

  /** Stand down where it stands: the plate covering it is what hides it. */
  deactivate() {
    this.container.classList.remove('is-active');
  }

  /** Slide off / behind, and stop any in-flight animation. */
  sendBack() {
    this.deactivate();
    this.container.style.transform = 'translateY(100%)';
    this.onSendBack();
  }

  /** Move the camera to a step (snap, or ease when animate). */
  goToStep(step, animate = false) {}

  /** Per-frame scroll interpolation between two steps. */
  scroll(progress, stepA, stepB) {}

  /** React to a viewport resize. */
  resize() {}

  /** Build the player (libraries are loaded by now). */
  _build() {}

  /** Free the player + GPU. */
  _teardown() {}
  
  /** Cleanup when sent back (e.g. stop the ease). */
  onSendBack() {}
}
