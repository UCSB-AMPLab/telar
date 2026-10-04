/**
 * Telar Story — IIIF Plate
 *
 * A scene whose object is an image, served through an Image API endpoint or an
 * external manifest. The default: a step with an object, no video URL and no
 * audio file is this.
 *
 * The instance is the viewer card. `iiif-card.js` frames a viewer by taking a
 * record with `element`, `osdViewer`, `isReady` and `pendingZoom` on it, and
 * this carries those itself rather than holding a second object that does —
 * which is what a separate, capped `viewerCards` array made of it before. The
 * plate is the permanent thing; the viewer inside it is the evictable one, and
 * `load` / `unload` are that boundary.
 *
 * `element` is an alias for `container`. Both names are load-bearing: the base
 * class and the card pool say `container`, and `iiif-card.js` says `element`.
 *
 * @version v1.8.0
 */

import { Plate } from './base-plate.js';
import { state } from '../state.js';
import { IiifViewer } from '../iiif-viewer.js';
import { getManifestUrl } from '../viewer.js';
import { snapIiifToPosition, animateIiifToPosition } from '../iiif-card.js';

/** Unique ids for the div OSD mounts into, one per viewer ever built. */
let _viewerSeq = 0;

// A step that leaves x, y or zoom blank shows the whole object, and the whole
// object is a framing like any other: the image centre at zoom 1, which the
// focal target resolves to the whole image fit and centred in the region the
// text card leaves uncovered. Without these the viewer keeps whatever OSD's home
// position gives it — the image centred in the VIEWER, so a side card sits over
// one edge of it.
const FULL_OBJECT_FRAMING = { x: 0.5, y: 0.5, zoom: 1 };

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
export function stepFraming(step) {
  const num = (value, fallback) => {
    const n = parseFloat(value);
    return Number.isFinite(n) ? n : fallback;
  };
  return {
    x:    num(step.x,    FULL_OBJECT_FRAMING.x),
    y:    num(step.y,    FULL_OBJECT_FRAMING.y),
    zoom: num(step.zoom, FULL_OBJECT_FRAMING.zoom),
    page: step.page ? parseInt(step.page, 10) : undefined,
  };
}

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
    this.settledAt = null;
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
    if (this.osdWrapper && typeof this.osdWrapper.destroy === 'function') {
      this.osdWrapper.destroy();
    }
    this.osdWrapper = null;
    this.osdViewer = null;
    this.isReady = false;
    this.pendingZoom = null;
    this.settledAt = null;

    // Take the mount point with it, so a later load builds cleanly rather
    // than into the div the dead viewer left.
    this.container.querySelector('.viewer-instance')?.remove();
    delete this.container.dataset.loading;
  }

  /**
   * Bring the plate's viewer to a step, building it if it has none.
   *
   * The card pool has already moved the element; what is left is the viewer
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
    if (isNaN(x) || isNaN(y) || isNaN(zoom)) return;

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
   * A plate evicted from the pool keeps its own element but loses this child,
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

  /**
   * The framing a viewer opens at, or null when the step authored none.
   *
   * Snapping rather than animating, because there is nothing yet on screen to
   * animate from.
   *
   * @param {{x: number, y: number, zoom: number}} framing
   * @returns {{ x: number, y: number, zoom: number, snap: boolean }|null}
   */
  static _openingFraming({ x, y, zoom }) {
    if (isNaN(x) || isNaN(y) || isNaN(zoom)) return null;
    return { x, y, zoom, snap: true };
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
    this.pendingZoom = IiifPlate._openingFraming({ x, y, zoom });

    osdWrapper.ready.then(() => {
      this.osdViewer = osdWrapper.viewer;
      this.isReady = true;
      delete plateEl.dataset.loading;

      // Belt-and-braces: the wrapper already sets this in _init(); keeping
      // the line here documents the Telar invariant (wheel events belong to
      // Lenis, not OSD) at the call site too.
      osdWrapper.viewer.gestureSettingsMouse.scrollToZoom = false;

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
   * Belt-and-braces on top of the rAF-deferred `.ready`: a residual race can
   * still leave the viewer at home zoom. One frame after the apply, compare
   * the current zoom against home; matching — with an authored zoom
   * meaningfully above it — means the apply was dropped. Tolerance is 5% of
   * home zoom, and the re-apply happens exactly once.
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
