/**
 * Telar Story -- Model Card
 *
 * This module manages the lifecycle of Google <model-viewer> instances for
 * self-hosted 3D objects (GLB / glTF). Model cards follow the same
 * DOM-at-init, visibility-via-transforms pattern as IIIF, video, and audio
 * cards, but instead of a tiled image or waveform the plate hosts a
 * <model-viewer> web component that renders the model with WebGL.
 *
 * Guided playback — unlike the standalone object page (which sets
 * `camera-controls` so a reader can orbit freely), story plates render the
 * model WITHOUT `camera-controls`. The camera is driven entirely by the
 * authored per-step numeric framing columns (azimuth, elevation, distance and
 * optional target_x/y/z); stepCameraStrings() turns those into model-viewer's
 * native camera-orbit/target strings at this boundary. On a step change
 * card-pool calls updateModelCamera() — the 3D analogue of the IIIF viewer
 * animating to a step's x/y/zoom. With controls absent the component never
 * captures touch/drag, so the wheel and vertical drag still belong to the
 * Lenis scroll engine (same posture as IIIF story plates).
 *
 * WebGL lifecycle — each live <model-viewer> holds a three.js WebGL
 * renderer, a parsed glTF scene graph, and GPU buffers. Reassigning `src`
 * on one instance to load a different model is a documented leak, so the
 * card pool builds one element per scene and never re-`src`es it. Eviction
 * is a HARD teardown: destroyModelPlayer() removes the <model-viewer>
 * element from the DOM, whose disconnectedCallback releases the WebGL
 * context. A re-entered scene re-creates a fresh element (the browser HTTP
 * cache makes the GLB re-fetch cheap). Because a static model (no animation,
 * no auto-rotate) renders on demand rather than every frame, a covered but
 * not-yet-evicted instance costs no continuous GPU time.
 *
 * Player pool — at most MAX_MODEL_VIEWERS instances exist at once (lower
 * than IIIF's cap of 8, because each is a full WebGL renderer and browsers
 * cap simultaneous WebGL contexts). When a further one is needed, the
 * instance farthest by scene distance is destroyed. Mirrors the audio-card
 * MAX_AUDIO_PLAYERS pool.
 *
 * Reduced motion — readers who prefer reduced motion get instant camera
 * jumps (jumpCameraToGoal) instead of <model-viewer>'s default
 * interpolation, mirroring how scroll-engine.js disables Lenis smooth-wheel
 * and iiif-card.js snaps the IIIF viewer.
 *
 * Vendored, no CDN — the <model-viewer> UMD build is loaded lazily from
 * assets/vendor/model-viewer/ on first appearance (loadModelViewerAPI),
 * so story pages without a 3D object download nothing extra. The bundle
 * self-registers the <model-viewer> custom element.
 *
 * @version v1.6.0
 */

import { state } from './state.js';
import { getBasePath } from './utils.js';
import { onViewportResize, onLayoutChange } from './layout-mode.js';
import { _deriveCardPlacement, computeUncoveredRegion } from './iiif-card.js';

// ── Module-level player pool ──────────────────────────────────────────────────

/** Active model player wrappers. Capped at MAX_MODEL_VIEWERS. */
const _modelPlayers = [];

/**
 * Maximum concurrent <model-viewer> (WebGL) instances. Lower than the IIIF
 * cap of 8: each instance is a full WebGL renderer, and browsers force-lose
 * the oldest context once ~8-16 are live. 3 = current + one ahead + one
 * behind, matching video-card.js's MAX_VIDEO_PLAYERS.
 */
const MAX_MODEL_VIEWERS = 3;

/** Default orbit applied when a step authors no framing columns. azimuth 0°,
 *  elevation 75°, and `auto` radius = model-viewer's idealCameraDistance (the
 *  "fit the whole model" default), so a 3D step needs no numbers to look sensible. */
const DEFAULT_ORBIT = '0deg 75deg auto';

/** Duration (ms) of the guided camera move on DISCRETE navigation (mobile tap /
 *  nav button / deep-link). A story plate is a static, controls-less, non-animated
 *  <model-viewer>, which does NOT run a continuous interpolation render loop — so
 *  model-viewer's own `interpolation-decay` never plays for us (nothing ticks it;
 *  the camera would only move when an unrelated render is forced, e.g. the
 *  card-settle resize, reading as a snap "at the end"). Instead we drive the move
 *  ourselves with a time-based rAF loop that calls jumpCameraToGoal() every frame —
 *  exactly the mechanism that makes SCROLL navigation smooth (lerpModelCamera),
 *  here driven by elapsed time instead of scroll progress. ~600 ms with an
 *  ease-out cubic matches keyboardNav's 0.8 s scrollTo feel without dragging. */
const MODEL_CAMERA_DURATION = 600;

// ── model-viewer vendored loader ──────────────────────────────────────────────

/**
 * Load the vendored <model-viewer> UMD build from
 * `assets/vendor/model-viewer/` once, returning a Promise that resolves when
 * the custom element is defined. Subsequent calls return the same Promise
 * (once-guard pattern, mirroring audio-card.js's loadWaveSurferAPI).
 *
 * The bundle is loaded lazily (only when a model card first appears) via an
 * injected <script> tag rather than a static layout tag, so story pages
 * without a 3D object never pay the (~283 KB gz) download. The UMD build
 * self-registers the <model-viewer> custom element; we reach the element
 * through the DOM after `customElements.whenDefined`, not through a window
 * global. Vendored instead of CDN-loaded for the minimal-computing reasons
 * in assets/vendor/README.md.
 *
 * @returns {Promise<void>}
 */
export function loadModelViewerAPI() {
  if (window._mvApiPromise) return window._mvApiPromise;

  window._mvApiPromise = new Promise((resolve, reject) => {
    if (window.customElements && customElements.get('model-viewer')) {
      resolve();
      return;
    }

    const basePath = getBasePath();
    const script = document.createElement('script');
    script.src = `${basePath}/assets/vendor/model-viewer/model-viewer-umd.min.js`;
    script.async = true;
    script.onload = () => {
      // The element registers itself on import; wait for the definition so
      // callers can construct it with confidence.
      customElements.whenDefined('model-viewer').then(() => resolve());
    };
    script.onerror = () => reject(new Error('model-viewer failed to load'));
    document.head.appendChild(script);
  });

  return window._mvApiPromise;
}

// ── Player lifecycle ──────────────────────────────────────────────────────────

/**
 * Create a <model-viewer> instance inside the given plate element.
 *
 * Loads the vendored model-viewer bundle on demand (first call), creates the
 * element with the authored initial camera, sets the GLB source (with a
 * one-shot `.gltf` fallback on error, mirroring the object-page loader), and
 * pushes a wrapper into the module-level _modelPlayers pool (capped at
 * MAX_MODEL_VIEWERS).
 *
 * Guided playback: `camera-controls` is deliberately NOT set, so the camera
 * is driven only by the authored numeric framing columns and the component
 * never captures touch/drag from the Lenis scroll engine.
 *
 * @param {HTMLElement} plateEl - The viewer plate element
 * @param {string} glbUrl - URL to the .glb model (optimistic primary source)
 * @param {string} gltfUrl - URL to the .gltf fallback (tried once on error)
 * @param {Object} options
 * @param {string} [options.cameraOrbit] - Authored initial orbit (model-viewer native format)
 * @param {string} [options.cameraTarget] - Authored initial look-at target ("x y z")
 * @param {number} [options.sceneIndex=0] - For pool eviction ordering
 * @param {string} [options.alt] - Accessible description of the model
 * @param {Function} [options.onLoad] - Called once the model's first frame is presentable
 * @param {Function} [options.onError]
 * @returns {Object} Player wrapper
 */
export function createModelPlayer(plateEl, glbUrl, gltfUrl, options = {}) {
  const {
    cameraOrbit,
    cameraTarget,
    sceneIndex = 0,
    alt = '',
    onLoad = () => {},
    onError = () => {},
  } = options;

  const wrapper = {
    type: 'model',
    element: plateEl,
    mv: null,
    sceneIndex,
    cameraOrbit: cameraOrbit || DEFAULT_ORBIT,
    cameraTarget: cameraTarget || '',
    _triedGltf: false,
    _destroyed: false,
    destroy() {
      destroyModelPlayer(this);
    },
  };

  _modelPlayers.push(wrapper);
  _enforceModelPoolLimit(sceneIndex);

  plateEl.dataset.loading = 'true';
  // B1 race guard: mark the plate as having an init in flight, SYNCHRONOUSLY,
  // before the async loadModelViewerAPI() resolves and appends the element.
  // The card-pool "already initialised?" guards check both this flag and the
  // presence of `.model-instance`, so a second _initModelInPlate in the same
  // microtask batch (common once the bundle is cached) cannot slip past and
  // build a second <model-viewer> / leak a second WebGL context on one plate.
  plateEl.dataset.modelInitPending = 'true';

  loadModelViewerAPI()
    .then(() => {
      // The wrapper may have been evicted/destroyed while the vendored bundle
      // was loading; bail before constructing an element nothing will clean up.
      if (wrapper._destroyed) {
        delete plateEl.dataset.modelInitPending;
        return;
      }

      const mv = document.createElement('model-viewer');
      mv.className = 'model-instance';
      // Apply the authored camera as attributes BEFORE the model loads, so the
      // first presentable frame is already framed correctly (no jump from the
      // component's default framing).
      mv.setAttribute('camera-orbit', wrapper.cameraOrbit);
      if (wrapper.cameraTarget) mv.setAttribute('camera-target', wrapper.cameraTarget);
      // Guided playback: NO camera-controls — the camera is authored, and the
      // wheel/drag belongs to Lenis. Suppress the interaction prompt too.
      mv.setAttribute('interaction-prompt', 'none');
      // No reliance on model-viewer's built-in camera easing. A static,
      // controls-less plate doesn't run a continuous render loop, so
      // interpolation-decay never plays for us (nothing ticks it). BOTH
      // navigation modes instead set the goal and call jumpCameraToGoal() every
      // frame — scroll via lerpModelCamera (scroll progress), discrete via
      // _animateModelCameraDiscrete (elapsed time). decay=0 = land-on-goal, the
      // honest value since our per-frame jumps own all the smoothness.
      mv.setAttribute('interpolation-decay', '0');
      // Allow the authored camera to approach the model closely. model-viewer's
      // default min-camera-orbit keeps the camera well outside a LARGE model's
      // bounding sphere (so a wide mural can't be zoomed past ~half its width).
      // Story cameras are fully authored (no user controls), so we relax the
      // lower radius bound to 0 and let the per-step camera_orbit decide how far
      // to dig in — e.g. a 1.5 m radius onto a single inset photograph. The
      // authored radius (never 0) stays the real limit; this only lifts the clamp.
      mv.setAttribute('min-camera-orbit', 'auto auto 0m');
      // Eager load: card-pool deliberately creates model plates OFF-SCREEN
      // (translateY(100%)) ahead of the reader so the model is ready when the
      // plate slides up. model-viewer's default loading="auto" gates the load
      // on its own IntersectionObserver, which would defer an off-screen plate
      // and defeat that preload — so force eager loading.
      mv.setAttribute('loading', 'eager');
      mv.setAttribute('shadow-intensity', '0.5');
      mv.setAttribute('exposure', '1');
      if (alt) mv.setAttribute('alt', alt);
      // Initial fallback box. frameModelInRegion (called right after append and
      // on load) replaces this with an absolutely-positioned rect sized to the
      // uncovered region; this inline fill just guarantees a non-zero box so
      // WebGL renders even if the framing call were to early-return.
      mv.style.width = '100%';
      mv.style.height = '100%';

      // Optimistic .glb source with a one-shot .gltf fallback (mirrors the
      // object-page loader): no HEAD pre-flight, so a transient dev-server
      // hiccup can't leave the plate blank.
      mv.addEventListener('error', () => {
        // B2: the wrapper may have been evicted (WebGL pool limit) and the
        // plate re-assigned to another scene before this fires. Bail so we
        // don't inject an error notice or retry on a recycled plate.
        if (wrapper._destroyed) return;
        if (!wrapper._triedGltf && gltfUrl) {
          wrapper._triedGltf = true;
          mv.setAttribute('src', gltfUrl);
        } else {
          delete plateEl.dataset.loading;
          _injectModelError(plateEl);
          onError(new Error('model-viewer load error'));
        }
      });

      mv.addEventListener('load', () => {
        if (wrapper._destroyed) return;
        delete plateEl.dataset.loading;
        // Now the bounding box / dimensions are known: frame the model in the
        // uncovered region (the % radius re-resolves for the region aspect).
        frameModelInRegion(plateEl);
        // Reduced-motion readers: settle the authored camera instantly.
        _settle(wrapper);
        onLoad();
      });

      mv.setAttribute('src', glbUrl);
      plateEl.appendChild(mv);
      wrapper.mv = mv;
      // The element now exists in the DOM, so card-pool's `.model-instance`
      // presence guard takes over — clear the in-flight flag.
      delete plateEl.dataset.modelInitPending;
      // Size the element to the uncovered region BEFORE the model loads, so the
      // first presentable frame already frames for ~the region aspect (Fix 2).
      frameModelInRegion(plateEl);
    })
    .catch((err) => {
      console.error('model-card: failed to load model-viewer API', err);
      delete plateEl.dataset.loading;
      delete plateEl.dataset.modelInitPending;
      _injectModelError(plateEl);
      onError(err);
    });

  return wrapper;
}

/**
 * Activate a model card plate: reveal it.
 *
 * model-viewer renders a static model on demand (not every frame), so there
 * is no playback to start — revealing the plate is enough.
 *
 * @param {HTMLElement} plateEl - The model plate element
 * @param {number} sceneIndex - Scene index (reserved; parity with audio/video)
 */
export function activateModelCard(plateEl, sceneIndex) { // eslint-disable-line no-unused-vars
  plateEl.style.transform = 'translateY(0)';
  plateEl.classList.add('is-active');
}

/**
 * Deactivate a model card plate: drop the active class.
 *
 * Does NOT touch transform — the caller decides positioning (same contract as
 * video-card.js / audio-card.js). No render pause is needed: a static model
 * renders on demand, so a covered instance costs no continuous GPU time.
 *
 * @param {HTMLElement} plateEl - The model plate element
 */
export function deactivateModelCard(plateEl) {
  plateEl.classList.remove('is-active');
}

/**
 * Push a new authored camera position to a live model plate. <model-viewer>
 * interpolates the camera to the new orbit/target by itself (the 3D analogue
 * of animateIiifToPosition); for reduced-motion readers the change is jumped
 * instantly.
 *
 * No-op when the camera is unchanged, so a same-object text-only step that
 * carries no new camera does not re-trigger an interpolation.
 *
 * @param {HTMLElement} plateEl
 * @param {string} cameraOrbit - model-viewer native orbit string (may be empty → keep current)
 * @param {string} [cameraTarget] - look-at target "x y z" (empty → model-centered "auto auto auto")
 * @param {Object} [step] - the destination step's raw row (numeric framing columns);
 *   when present, DISCRETE nav eases to it (computed from the columns, not from a
 *   model-viewer read-back). Omitted for scroll boundaries, which always snap.
 */
export function updateModelCamera(plateEl, cameraOrbit, cameraTarget, step) {
  const wrapper = _getModelWrapperForPlate(plateEl);
  if (!wrapper) return;

  const nextOrbit = cameraOrbit || wrapper.cameraOrbit || DEFAULT_ORBIT;
  const nextTarget = cameraTarget || '';

  if (nextOrbit === wrapper.cameraOrbit && nextTarget === wrapper.cameraTarget) {
    return; // unchanged — don't restart an interpolation
  }
  wrapper.cameraOrbit = nextOrbit;
  wrapper.cameraTarget = nextTarget;

  // Persist onto the plate dataset so a re-init after eviction restores the
  // step's framing (parallel to how video/audio re-read clip dataset attrs).
  plateEl.dataset.cameraOrbit = nextOrbit;
  if (nextTarget) plateEl.dataset.cameraTarget = nextTarget;
  else delete plateEl.dataset.cameraTarget;

  const mv = wrapper.mv;
  if (!mv) return; // still loading — initial attrs already hold the latest values via createModelPlayer

  if (!step || state.scrollDriven || _reduceMotion() || !mv.loaded) {
    // Scroll-driven boundary (the per-frame lerp owns the smooth in-between
    // motion and jumpCameraToGoal lands the exact step), reduced motion, a
    // not-yet-loaded model, or no step row to read columns from: set the goal
    // and snap the rendered camera to it.
    _cancelDiscreteCameraAnim(wrapper); // a snap supersedes any in-flight ease
    mv.cameraOrbit = nextOrbit;
    mv.cameraTarget = nextTarget || 'auto auto auto';
    _jumpModelCameraToGoal(mv);
    return;
  }
  // DISCRETE navigation (mobile tap, nav button, deep-link/TOC jump) with no
  // scroll animation to drive a per-frame lerp. A static, controls-less plate
  // runs no interpolation loop, so we animate the move OURSELVES: a time-based
  // rAF that eases from the live pose to this step's pose, jumping to the goal
  // every frame — the same jumpCameraToGoal-per-frame mechanism that makes
  // scroll smooth, just driven by elapsed time.
  _animateModelCameraDiscrete(wrapper, step, nextOrbit, nextTarget || 'auto auto auto');
}

/**
 * Ease a model plate's camera from its current rendered pose to a step's authored
 * pose over MODEL_CAMERA_DURATION, driven by our own requestAnimationFrame loop.
 *
 * Why not model-viewer's interpolation-decay: a guided story plate is a static,
 * `camera-controls`-less, non-animated <model-viewer>, which does not run a
 * continuous render loop. Setting cameraOrbit only sets a goal; with nothing
 * ticking, the eased interpolation never plays — the camera snaps only when an
 * unrelated render is forced. So we drive the motion explicitly, calling
 * jumpCameraToGoal() each frame (which both moves the camera AND schedules a
 * render), exactly like lerpModelCamera does for scroll.
 *
 * FROM is the LIVE camera (getCameraOrbit/Target — concrete radians/metres of the
 * settled previous step). TO is computed from the destination step's numeric
 * columns (azimuth/elevation/distance/target_x/y/z), NOT read back from
 * model-viewer — a freshly-set cameraOrbit only reaches model-viewer's goal on
 * its next tick, so an immediate read-back returns the STALE goal (≈ FROM) and the
 * ease would have zero motion. Any null column mirrors FROM (no motion on that
 * axis), matching lerpModelCamera's _lerpPair. Azimuth takes the shortest path.
 * A new discrete nav (rapid taps) or a scroll/reduced-motion snap cancels the loop.
 *
 * @param {Object} wrapper - model player wrapper
 * @param {Object} step - destination step row (numeric framing columns)
 * @param {string} fallbackOrbit - the step's resolved orbit string (for the final landing + wrapper sync)
 * @param {string} fallbackTarget - the step's resolved target string ("x y z" / "auto auto auto")
 */
function _animateModelCameraDiscrete(wrapper, step, fallbackOrbit, fallbackTarget) {
  const mv = wrapper.mv;
  if (!mv) return;
  _cancelDiscreteCameraAnim(wrapper);

  const DEG = 180 / Math.PI;
  // FROM: current rendered pose, converted to degrees / metres.
  const fO = mv.getCameraOrbit();
  const fT = mv.getCameraTarget();
  const fromTh = fO.theta * DEG, fromPh = fO.phi * DEG, fromR = fO.radius;
  const fromT = [fT.x, fT.y, fT.z];

  // TO: from the step's numeric columns; a null column keeps FROM on that axis.
  const az = _num(step.azimuth), el = _num(step.elevation), dist = _num(step.distance);
  const toTh = az == null ? fromTh : az;
  const toPh = el == null ? fromPh : el;
  const toR  = dist == null ? fromR : dist;
  const stepT = _stepTarget(step);
  const toT = stepT || fromT.slice();

  // Shortest-path azimuth: wrap Δθ into [−180°, 180°].
  let dth = toTh - fromTh;
  dth = ((dth + 180) % 360 + 360) % 360 - 180;

  const ease = (t) => 1 - Math.pow(1 - t, 3); // ease-out cubic (matches keyboardNav scrollTo)
  const start = (typeof performance !== 'undefined' ? performance.now() : Date.now());
  const tick = (now) => {
    const elapsed = now - start;
    const p = elapsed >= MODEL_CAMERA_DURATION ? 1 : elapsed / MODEL_CAMERA_DURATION;
    const e = ease(p);
    const th = fromTh + dth * e;
    const ph = fromPh + (toPh - fromPh) * e;
    const r  = fromR  + (toR  - fromR)  * e;
    const tx = fromT[0] + (toT[0] - fromT[0]) * e;
    const ty = fromT[1] + (toT[1] - fromT[1]) * e;
    const tz = fromT[2] + (toT[2] - fromT[2]) * e;
    mv.cameraOrbit = `${th}deg ${ph}deg ${r}m`;
    mv.cameraTarget = `${tx}m ${ty}m ${tz}m`;
    _jumpModelCameraToGoal(mv);
    if (p < 1) {
      wrapper._cameraRAF = requestAnimationFrame(tick);
    } else {
      // Land exactly on the authored goal. model-viewer applies a freshly-set
      // cameraOrbit to its goal on the NEXT tick, so jumpCameraToGoal here is one
      // tick behind; a second jump next frame settles the rendered camera onto it.
      mv.cameraOrbit = fallbackOrbit;
      mv.cameraTarget = fallbackTarget;
      _jumpModelCameraToGoal(mv);
      wrapper._cameraRAF = requestAnimationFrame(() => {
        _jumpModelCameraToGoal(mv);
        wrapper._cameraRAF = null;
      });
    }
  };
  wrapper._cameraRAF = requestAnimationFrame(tick);
}

/**
 * Cancel any in-flight discrete camera animation on a wrapper.
 * @param {Object} wrapper
 */
function _cancelDiscreteCameraAnim(wrapper) {
  if (wrapper && wrapper._cameraRAF) {
    cancelAnimationFrame(wrapper._cameraRAF);
    wrapper._cameraRAF = null;
  }
}

/**
 * Interpolate a model plate's camera between two steps based on scroll progress.
 *
 * The 3D analogue of iiif-card.js:lerpIiifPosition, and the fix for D1 (the
 * camera "jumping at a threshold"). Called every frame by the scroll engine's
 * rAF loop. For step pairs that share the same object it linearly interpolates
 * the camera orbit (θ, φ, radius) and target between step A and step B by the
 * fractional scroll `progress`, then assigns the result with the cameraOrbit /
 * cameraTarget property setters. Because the element carries
 * `interpolation-decay="0"`, each assignment applies instantly — smoothness
 * comes from Lenis calling this every frame, exactly like snapIiifToPosition.
 *
 * Different-object pairs are frozen (the new plate slides in on top, same as
 * IIIF). Progress below 0.001 is skipped (already at the integer step); at
 * progress ≥ 0.999 the camera snaps exactly to step B so the boundary always
 * lands even on a fast scroll or snap.
 *
 * Azimuth uses shortest-path interpolation so an orbit across the front of the
 * object does not take the long way round. Every component is a plain number in
 * one unit (degrees for angles, metres for distance/target), so this is a
 * straight numeric lerp. An empty target on one side resolves to the model's
 * bounding-box centre once loaded; while the model is still loading the target
 * lerp is skipped for that frame.
 *
 * @param {number} stepIndex - Current step index (floor of scroll position).
 * @param {number} progress - Fractional progress 0.0–1.0 toward the next step.
 * @param {Array} stepsData - Filtered step data (same index space as state.stepToScene).
 */
export function lerpModelCamera(stepIndex, progress, stepsData) {
  if (progress < 0.001) return; // at exact integer step, no interpolation needed

  const stepA = stepsData[stepIndex];
  const stepB = stepsData[stepIndex + 1];
  if (!stepA || !stepB) return;

  const objectIdA = stepA.object || stepA.objectId || '';
  const objectIdB = stepB.object || stepB.objectId || '';
  if (objectIdA !== objectIdB) return; // different object → freeze

  // Resolve the active model wrapper by SCENE (not object id — a repeated
  // object has multiple scenes, mirroring lerpIiifPosition's lookup).
  const sceneIndex = state.stepToScene?.[stepIndex];
  if (sceneIndex === undefined || sceneIndex < 0) return;
  const plate = state.viewerPlates?.[sceneIndex];
  if (!plate || !plate.classList.contains('model-plate')) return;
  const wrapper = _getModelWrapperForPlate(plate);
  if (!wrapper) return;
  _cancelDiscreteCameraAnim(wrapper); // a scroll frame supersedes any discrete ease

  // Snap exactly to step B at the boundary so the endpoint always lands.
  const p = progress >= 0.999 ? 1 : progress;

  // ── Orbit (numeric columns) ─────────────────────────────────────────────────
  // azimuth / elevation / distance are plain numbers. A missing endpoint mirrors
  // the other (no movement on that axis); both azimuth/elevation missing default
  // to 0°/75°; both distance missing → 'auto' radius (idealCameraDistance). One
  // unit throughout (degrees / metres), so this is a straight numeric lerp.
  const azP   = _lerpPair(_num(stepA.azimuth),   _num(stepB.azimuth),   0);
  const elP   = _lerpPair(_num(stepA.elevation), _num(stepB.elevation), 75);
  const distP = _lerpPair(_num(stepA.distance),  _num(stepB.distance),  null);

  // Shortest-path azimuth: wrap Δθ into [−180°, 180°].
  let dTheta = azP.to - azP.from;
  dTheta = ((dTheta + 180) % 360 + 360) % 360 - 180;
  const theta = azP.from + dTheta * p;
  const phi   = elP.from + (elP.to - elP.from) * p;
  const radiusPart = distP.from == null
    ? 'auto'
    : `${distP.from + (distP.to - distP.from) * p}m`;
  const orbitStr = `${theta}deg ${phi}deg ${radiusPart}`;

  const mv = wrapper.mv;
  wrapper.cameraOrbit = orbitStr; // keep wrapper in sync so post-scrub updateModelCamera isn't a stale no-op
  if (mv) mv.cameraOrbit = orbitStr;

  // ── Target (numeric columns) ─────────────────────────────────────────────────
  const tA = _stepTarget(stepA);
  const tB = _stepTarget(stepB);
  if (!tA && !tB) {
    // Both model-centred — nothing to interpolate; leave target at its default.
    wrapper.cameraTarget = '';
    if (mv) mv.cameraTarget = 'auto auto auto';
  } else {
    let from = tA, to = tB;
    if (!from || !to) {
      // One side is model-centred: resolve it to the bounding-box centre, but
      // only once the model is loaded (getBoundingBoxCenter needs the scene).
      if (mv && mv.loaded && typeof mv.getBoundingBoxCenter === 'function') {
        const c = mv.getBoundingBoxCenter();
        const centre = [c.x, c.y, c.z];
        from = from || centre;
        to = to || centre;
      } else {
        _jumpModelCameraToGoal(mv); // orbit applied; force the static renderer to it
        return; // skip the target lerp this frame
      }
    }
    const tx = from[0] + (to[0] - from[0]) * p;
    const ty = from[1] + (to[1] - from[1]) * p;
    const tz = from[2] + (to[2] - from[2]) * p;
    const targetStr = `${tx}m ${ty}m ${tz}m`;
    wrapper.cameraTarget = targetStr;
    if (mv) mv.cameraTarget = targetStr;
  }

  // A static (non-animating) model renders on demand, so with interpolation-decay=0
  // the camera GOAL is updated but the rendered camera never ticks toward it until
  // a render is forced. jumpCameraToGoal() forces that snap every frame; smoothness
  // still comes from the per-frame lerp above (Lenis), exactly like snapIiifToPosition.
  _jumpModelCameraToGoal(mv);
}

/**
 * Force a <model-viewer>'s rendered camera to its current goal.
 *
 * Guided story plates carry no `camera-controls`, no auto-rotate and no
 * animation, so model-viewer renders on demand. Assigning cameraOrbit /
 * cameraTarget only updates the GOAL; with interpolation-decay=0 the camera is
 * meant to land instantly, but without a running render loop the on-demand
 * renderer never ticks, so the goal is silently never reached. Calling
 * jumpCameraToGoal() snaps the camera to the goal AND schedules a render.
 *
 * @param {HTMLElement|null} mv
 */
function _jumpModelCameraToGoal(mv) {
  if (mv && typeof mv.jumpCameraToGoal === 'function') mv.jumpCameraToGoal();
}

/**
 * Size a model plate's <model-viewer> element to the uncovered region — the
 * part of the viewport the text card does not cover — so the model centres
 * beside (horizontal card) or above (vertical card) the text instead of behind
 * it. The fix for D2 (model centred on screen, ignoring the overlay-aware
 * centring algorithm). The plate keeps its full-viewport weave backdrop.
 *
 * Uses the same computeUncoveredRegion + _deriveCardPlacement that IIIF uses,
 * so the framing is identical to the IIIF focal region.
 *
 * Only the ELEMENT is resized here — the camera is left untouched. Distance is
 * authored in metres (absolute), so it does not re-resolve against the element
 * aspect the way the old `%` radius did, and model-viewer both preserves the
 * camera orbit across a resize and re-renders on it. Crucially, NOT touching the
 * camera lets an in-progress discrete-nav ease (updateModelCamera) run to its
 * goal — this hook fires when the step's card finishes sliding, so re-asserting /
 * jumping the camera here would snap it and cut the animation short.
 *
 * Eased reframe — when `animate` is set (the step-settle path), the element box
 * eases to the new region via a CSS transition instead of snapping. A step whose
 * text card differs in height from the previous one changes the uncovered region,
 * which would otherwise jerk the model sideways/scale at the end of the slide.
 * The FIRST framing, scroll-scrub reframes, and reduced-motion stay instant: the
 * first would animate from the 100%×100% fallback, and a scrub wants the region
 * to track immediately. A reframe smaller than 1px is skipped (no spurious
 * model-viewer canvas re-render).
 *
 * @param {HTMLElement} plateEl
 * @param {boolean} [animate=false] - Ease the box to the new region (settle path only)
 */
export function frameModelInRegion(plateEl, animate = false) {
  if (!plateEl) return;
  const wrapper = _getModelWrapperForPlate(plateEl);
  const mv = (wrapper && wrapper.mv) || plateEl.querySelector('.model-instance');
  if (!mv) return; // element not created yet — createModelPlayer frames on append

  const region = _computeModelRegion();
  if (!region || region.w <= 0 || region.h <= 0) return;

  const x = Math.round(region.x), y = Math.round(region.y);
  const w = Math.round(region.w), h = Math.round(region.h);

  // Skip a no-op / sub-pixel reframe so an unchanged region doesn't re-render.
  if (mv.dataset.framed === 'true' &&
      Math.abs((parseFloat(mv.style.left) || 0) - x) < 1 &&
      Math.abs((parseFloat(mv.style.top) || 0) - y) < 1 &&
      Math.abs((parseFloat(mv.style.width) || 0) - w) < 1 &&
      Math.abs((parseFloat(mv.style.height) || 0) - h) < 1) {
    return;
  }

  const firstFrame = mv.dataset.framed !== 'true';
  const scrubbing = !!document.querySelector('.card-stack')?.classList.contains('is-scrubbing');
  const ease = animate && !firstFrame && !scrubbing && !_reduceMotion();
  mv.style.transition = ease
    ? ['left', 'top', 'width', 'height']
        .map((p) => `${p} ${MODEL_CAMERA_DURATION}ms cubic-bezier(0,0,0.2,1)`).join(', ')
    : 'none';
  mv.dataset.framed = 'true';

  mv.style.position = 'absolute';
  mv.style.left = `${x}px`;
  mv.style.top = `${y}px`;
  mv.style.width = `${w}px`;
  mv.style.height = `${h}px`;
}

/**
 * Destroy a model player wrapper, releasing its WebGL context.
 *
 * Removes the <model-viewer> element from the DOM (its disconnectedCallback
 * disposes the three.js renderer and releases the GPU context) rather than
 * nulling `src` — nulling/reassigning src is the documented model-viewer
 * leak. The plate div itself is kept for re-entry.
 *
 * @param {Object} wrapper - Player wrapper returned by createModelPlayer
 */
export function destroyModelPlayer(wrapper) {
  if (!wrapper) return;

  // Mark destroyed first so any in-flight createModelPlayer continuation bails.
  wrapper._destroyed = true;
  _cancelDiscreteCameraAnim(wrapper); // stop any running discrete camera ease

  const mv = wrapper.mv;
  if (mv) {
    try {
      mv.remove(); // disconnectedCallback releases the WebGL context
    } catch (e) {
      console.warn('destroyModelPlayer: error removing element', e);
    }
    wrapper.mv = null;
  }

  // Remove from pool
  const idx = _modelPlayers.indexOf(wrapper);
  if (idx !== -1) _modelPlayers.splice(idx, 1);

  // Clean up any error notice this module injected
  const plateEl = wrapper.element;
  if (plateEl) {
    const alert = plateEl.querySelector('.telar-alert');
    if (alert) alert.remove();
    delete plateEl.dataset.loading;
  }
}

// ── Private helpers ───────────────────────────────────────────────────────────

/**
 * Snap the rendered camera to its goal once the model's first frame loads, so
 * the plate appears already framed at the authored camera (no opening drift from
 * model-viewer's default framing). Step-to-step motion is handled separately by
 * lerpModelCamera (scroll) and updateModelCamera (discrete nav).
 *
 * @param {Object} wrapper
 */
function _settle(wrapper) {
  _jumpModelCameraToGoal(wrapper && wrapper.mv);
}

/**
 * Whether the reader prefers reduced motion. Reduced-motion readers get instant
 * camera snaps on discrete navigation instead of an eased interpolation.
 *
 * @returns {boolean}
 */
function _reduceMotion() {
  return typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Enforce the model player pool size limit.
 * Evicts the farthest player by scene distance when the cap is exceeded.
 *
 * @param {number} currentScene
 */
function _enforceModelPoolLimit(currentScene) {
  while (_modelPlayers.length > MAX_MODEL_VIEWERS) {
    let farthestIdx = 0;
    let maxDist = -1;
    for (let i = 0; i < _modelPlayers.length; i++) {
      const dist = Math.abs(_modelPlayers[i].sceneIndex - currentScene);
      if (dist > maxDist) {
        maxDist = dist;
        farthestIdx = i;
      }
    }
    const evicted = _modelPlayers[farthestIdx];
    // destroyModelPlayer splices the pool itself, so don't double-remove.
    destroyModelPlayer(evicted);
  }
}

/**
 * Find the model player wrapper for a given plate element.
 *
 * @param {HTMLElement} plateEl
 * @returns {Object|null}
 */
function _getModelWrapperForPlate(plateEl) {
  return _modelPlayers.find((w) => w.element === plateEl) || null;
}

/**
 * Coerce a story-step framing cell to a number. Empty / "nan" / unparseable → null
 * (so the caller can apply a per-component default). Story JSON carries these as
 * strings ("0", "1.45") or null.
 *
 * @param {*} v
 * @returns {number|null}
 */
function _num(v) {
  if (v === undefined || v === null) return null;
  const s = String(v).trim();
  if (s === '' || s.toLowerCase() === 'nan') return null;
  const n = parseFloat(s);
  return Number.isNaN(n) ? null : n;
}

/**
 * Resolve a numeric component pair for interpolation. A null endpoint mirrors the
 * other (constant on that axis); both null → the supplied default on each side
 * (or null/null when `dflt` is null, which the distance lerp reads as "auto").
 *
 * @param {number|null} a
 * @param {number|null} b
 * @param {number|null} dflt
 * @returns {{ from: number|null, to: number|null }}
 */
function _lerpPair(a, b, dflt) {
  if (a == null && b == null) return { from: dflt, to: dflt };
  return { from: a == null ? b : a, to: b == null ? a : b };
}

/**
 * Read a step's numeric look-at target columns into [x, y, z] metres.
 * All three empty → null (model-centred). A partial target fills missing axes
 * with 0 (origin on that axis).
 *
 * @param {Object} step
 * @returns {number[]|null}
 */
function _stepTarget(step) {
  const x = _num(step.target_x), y = _num(step.target_y), z = _num(step.target_z);
  if (x == null && y == null && z == null) return null;
  return [x || 0, y || 0, z || 0];
}

/**
 * Build a model-viewer camera-orbit string from a step's numeric framing columns.
 * Empty azimuth/elevation fall back to 0°/75°; empty distance → 'auto' radius
 * (model-viewer's idealCameraDistance — the fit-the-model default).
 *
 * @param {Object} step
 * @returns {string} e.g. "0deg 90deg 1.2m" or "0deg 75deg auto"
 */
function _stepToOrbitString(step) {
  const az = _num(step.azimuth);
  const el = _num(step.elevation);
  const dist = _num(step.distance);
  const a = (az == null ? 0 : az) + 'deg';
  const e = (el == null ? 75 : el) + 'deg';
  const r = dist == null ? 'auto' : dist + 'm';
  return `${a} ${e} ${r}`;
}

/**
 * Build a model-viewer camera-target string from a step's numeric target columns.
 * All empty → '' (model-centred; the caller passes this through to "auto auto auto").
 *
 * @param {Object} step
 * @returns {string} e.g. "0m 1.45m 0m" or ""
 */
function _stepToTargetString(step) {
  const t = _stepTarget(step);
  return t ? `${t[0]}m ${t[1]}m ${t[2]}m` : '';
}

/**
 * Convert a story step's numeric framing columns (azimuth, elevation, distance,
 * target_x/y/z) into the model-viewer native { orbit, target } strings the player
 * consumes. The numeric columns are the authoring/storage form; these strings are
 * the internal model-viewer boundary. Exported for card-pool's discrete updates
 * and plate initialisation.
 *
 * @param {Object} step
 * @returns {{ orbit: string, target: string }}
 */
export function stepCameraStrings(step) {
  return { orbit: _stepToOrbitString(step), target: _stepToTargetString(step) };
}

/**
 * Compute the uncovered region (screen px) for the current card overlay, using
 * the SAME helper IIIF uses so model framing matches the IIIF focal region.
 *
 * @returns {{ x: number, y: number, w: number, h: number }}
 */
function _computeModelRegion() {
  const vpW = window.innerWidth;
  const vpH = window.innerHeight;
  const r = state.cardOverlayRect;
  const cardBox = r ? { x: r.x, y: r.y, w: r.width, h: r.height } : null;
  const placement = _deriveCardPlacement(cardBox, vpW, vpH);
  return computeUncoveredRegion(cardBox, placement, vpW, vpH);
}

/**
 * Re-frame the currently active model plate. Hooked to viewport-resize and
 * layout-mode flips (the model analogue of iiif-card.js:_reSnapActiveViewer);
 * card-pool also calls frameModelInRegion directly from the cardOverlayRect
 * settle write so first-entry framing uses the measured rect.
 */
function _reframeActiveModelPlate() {
  // state.viewerPlates is an OBJECT keyed by scene index (a repeated object owns
  // multiple scenes), not an array — iterate its values, not Array.prototype.find.
  const plates = Object.values(state.viewerPlates || {});
  const plate = plates.find(
    (p) => p && p.classList && p.classList.contains('model-plate') && p.classList.contains('is-active')
  );
  if (plate) frameModelInRegion(plate);
}

// Re-frame on viewport resize (debounced) and on layout-mode flip — mirrors the
// IIIF re-snap subscriptions. onLayoutChange fires before onViewportResize and
// main.js updates state.cardOverlayRect first; wrap in rAF so the CSS reflow
// settles before we read the region.
onViewportResize(() => _reframeActiveModelPlate());
onLayoutChange(() => requestAnimationFrame(() => _reframeActiveModelPlate()));

/**
 * Inject a .telar-alert error notification into the model plate.
 * Matches the audio-card / iiif-url-warning alert pattern.
 *
 * @param {HTMLElement} plateEl
 */
function _injectModelError(plateEl) {
  if (plateEl.querySelector('.telar-alert')) return;

  const alertEl = document.createElement('div');
  alertEl.className = 'alert alert-warning telar-alert';
  alertEl.setAttribute('role', 'alert');
  alertEl.innerHTML = `<strong>3D model unavailable</strong>
<p>This 3D model could not be loaded. Continue scrolling to read the story.</p>`;
  plateEl.appendChild(alertEl);
}

// Test seam: expose the pool length for acceptance checks without leaking the
// array reference. Mirrors the spirit of other modules' test hooks.
export function _modelPoolSize() {
  return _modelPlayers.length;
}
