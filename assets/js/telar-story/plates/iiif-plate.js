/**
 * Telar Story — IIIF Plate
 *
 * A scene whose object is an image, served through an Image API endpoint or an
 * external manifest. The default: a step with an object, no video URL and no
 * audio file is this.
 *
 * `iiif-card.js` frames a viewer by taking a record with `element`,
 * `osdViewer`, `isReady` and `pendingZoom` on it, and the plate carries those
 * itself. The plate is the permanent thing; the viewer inside it is the
 * evictable one, and `load` / `unload` are that boundary.
 *
 * `element` is an alias for `container`: the base class and the card stack
 * read `container`, and `iiif-card.js` reads `element`.
 *
 * @version v1.8.0
 */

import { Plate } from './base-plate.js';
import { state } from '../state.js';
import { IiifViewer } from '../iiif-viewer.js';
import { getManifestUrl } from '../viewer.js';
import { snapIiifToPosition, animateIiifToPosition, stopCameraMove } from '../iiif-card.js';
import { FULL_OBJECT_FRAMING, stepFraming } from './framing.js';

/** Unique ids for the div OSD mounts into, one per viewer ever built. */
let _viewerSeq = 0;

// Defined in framing.js, which `iiif-card.js` can import without a cycle.
// Re-exported here because the Compositor's capture path imports this module
// for both, and its parity test resolves them from this path.
export { FULL_OBJECT_FRAMING, stepFraming };

export class IiifPlate extends Plate {

  // The class every viewer plate already carries. Named here so the base
  // constructor has something true to add rather than a class of its own.
  static containerClass = 'viewer-plate';
  static ariaFallback = 'Image viewer';

  constructor(container, objectId, sceneIndex, zIndex, initialStep) {
    super(container, objectId, sceneIndex, zIndex, initialStep);

    /** 1-indexed page, for an external multi-page manifest only. */
    this.page = undefined;
    /** The IIIF viewer wrapper (iiif-viewer.js), null when unloaded. */
    this.osdWrapper = null;
    /** The OpenSeadragon viewer, null until the wrapper reports ready. */
    this.osdViewer = null;
    this.isReady = false;
    /** A framing queued while the viewer was not ready yet. */
    this.pendingZoom = null;
    /** The framing last written at rest, so it is written once per arrival. */
    this.restingAt = null;
  }

  /** The plate element, under the name `iiif-card.js` reads it by. */
  get element() { return this.container; }

  /**
   * Build the viewer for a step, unless this plate already has one.
   *
   * Synchronous rather than the base class's promise: this type has no
   * libraries to fetch, and every caller here builds and moves on.
   *
   * @param {Object} step - The step whose framing and page the viewer opens at
   */
  load(step) {
    if (this.osdWrapper) return;
    this._build(step);
  }

  /** Free the viewer and its GPU memory; the plate element stays in the DOM. */
  unload() {
    // A move animating the viewer being freed would write to the next one.
    stopCameraMove(this);
    this.osdWrapper?.destroy();
    this.osdWrapper = null;
    this.osdViewer = null;
    this.isReady = false;
    this.pendingZoom = null;
    this.restingAt = null;

    // Take the mount point with it, so a later load builds cleanly rather
    // than into the div the dead viewer left.
    this.container.querySelector('.viewer-instance')?.remove();
    delete this.container.dataset.loading;
  }

  /**
   * Bring the plate's viewer to a step, building it if it has none.
   *
   * The card stack has already moved the element; what is left is the viewer
   * inside it. Snapped rather than animated, because a plate arriving is not
   * panning across an image the reader is already looking at.
   *
   * @param {Object} step - Step data
   */
  center(step) {
    if (this.osdWrapper) {
      this.goToStep(step, true);
      return;
    }
    this.load(step);
  }

  /**
   * Frame the viewer on a step.
   *
   * A viewer that is not ready yet is given the framing to apply when it is:
   * the build is asynchronous and a reader can cross several steps before it
   * resolves, so the last framing queued is the one that lands.
   *
   * Nothing is written while the scroll engine is driving, because it moves
   * this viewer itself, frame by frame, through `lerpIiifPosition`. A second
   * writer there would fight it. Snapping is the exception: a plate arriving
   * has to be placed whatever else is happening.
   *
   * @param {Object} step - Step data
   * @param {boolean} [snap=false] - Arrive at it rather than travel to it
   */
  goToStep(step, snap = false) {
    if (state.scrollDriven && !snap) return;

    const { x, y, zoom } = stepFraming(step);

    if (!this.isReady) {
      this.pendingZoom = { x, y, zoom, snap };
      return;
    }
    if (snap) {
      snapIiifToPosition(this, x, y, zoom);
    } else {
      animateIiifToPosition(this, x, y, zoom);
    }
  }

  /**
   * The div OSD mounts into.
   *
   * A plate whose viewer was evicted keeps its own element but loses this child,
   * so re-entering the scene builds a fresh one. A plate that still has one is
   * given the new viewer's id rather than a second div.
   *
   * @param {string} viewerId
   * @returns {HTMLElement}
   */
  _viewerInstanceDiv(viewerId) {
    const existing = this.container.querySelector('.viewer-instance');
    if (existing) {
      existing.id = viewerId;
      return existing;
    }

    const viewerDiv = document.createElement('div');
    viewerDiv.className = 'viewer-instance';
    viewerDiv.id = viewerId;
    this.container.appendChild(viewerDiv);
    return viewerDiv;
  }

  _build(step) {
    const { x, y, zoom, page } = stepFraming(step);
    const plateEl = this.container;

    const manifestUrl = getManifestUrl(this.objectId, page);
    if (!manifestUrl) {
      console.error('IiifPlate: no manifest URL for', this.objectId);
      return;
    }

    plateEl.dataset.loading = 'true';

    const viewerId = `iiif-viewer-${_viewerSeq++}`;
    this._viewerInstanceDiv(viewerId);

    // External multi-page manifests open at the requested page rather than
    // always starting at page 1.
    const startPage = page && page > 1 ? page - 1 : 0;

    const osdWrapper = new IiifViewer({
      container: '#' + viewerId,
      manifestUrl,
      startPage,
      showChrome: false,
    });

    this.page = page || undefined;
    this.osdWrapper = osdWrapper;
    this.osdViewer = null;
    this.isReady = false;
    // The opening framing snaps rather than animates: nothing is on screen yet
    // to animate from.
    this.pendingZoom = { x, y, zoom, snap: true };

    osdWrapper.ready.then(() => {
      this.osdViewer = osdWrapper.viewer;
      this.isReady = true;
      delete plateEl.dataset.loading;

      // The reader taking the image stops a move animating it, so the two
      // never write the viewer at once.
      const stop = () => stopCameraMove(this);
      osdWrapper.viewer.addHandler('canvas-press', stop);
      osdWrapper.viewer.addHandler('canvas-pinch', stop);

      // An unload while the viewer was building cleared the framing.
      if (!this.pendingZoom) return;

      const pz = this.pendingZoom;
      if (pz.snap) {
        snapIiifToPosition(this, pz.x, pz.y, pz.zoom);
      } else {
        animateIiifToPosition(this, pz.x, pz.y, pz.zoom);
      }
      this._verifyFramingLanded();
    }).catch(err => {
      console.error(`IiifPlate: IiifViewer failed for ${this.objectId}:`, err);
      this.isReady = true;
      delete plateEl.dataset.loading;
    });
  }

  /**
   * Re-apply the opening framing if the viewer's home fit overwrote it.
   *
   * A second check on top of the rAF-deferred `.ready`: the viewer can still
   * end up at home zoom. One frame after the apply, compare the current zoom
   * against home; matching — with an authored zoom meaningfully above it —
   * means the apply was dropped. Tolerance is 5% of home zoom, and the
   * re-apply happens exactly once.
   *
   * `pendingZoom` is cleared only afterwards, so the values are still there
   * for the re-apply if it is needed.
   */
  _verifyFramingLanded() {
    requestAnimationFrame(() => {
      const pz = this.pendingZoom;
      if (pz && this.osdViewer) {
        const vp       = this.osdViewer.viewport;
        const homeZoom = vp.getHomeZoom();
        const curZoom  = vp.getZoom(true);
        const TOL      = 0.05;      // 5% relative tolerance
        const authoredIsZoomed = pz.zoom > 1.1;  // meaningfully above home
        const droppedToHome    = Math.abs(curZoom - homeZoom) < homeZoom * TOL;

        if (authoredIsZoomed && droppedToHome) {
          if (pz.snap) {
            snapIiifToPosition(this, pz.x, pz.y, pz.zoom);
          } else {
            animateIiifToPosition(this, pz.x, pz.y, pz.zoom);
          }
        }
      }
      this.pendingZoom = null;
    });
  }
}
