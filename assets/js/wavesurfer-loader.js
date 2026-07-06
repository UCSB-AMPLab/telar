/**
 * Telar — vendored WaveSurfer loader for object pages.
 *
 * Loads the vendored WaveSurfer UMD bundle (core + Regions plugin) once, from
 * the repo's assets/vendor/, so audio object pages render their waveform with
 * no CDN dependency. The UMD builds expose window.WaveSurfer and
 * window.WaveSurfer.Regions.
 *
 * MUST agree with loadWaveSurferAPI in assets/js/telar-story/audio-card.js —
 * same vendored bundles, same load-once-and-cache strategy. That file's
 * loader is an ES module used by the telar-story.js bundle; object pages
 * don't load that bundle, so this file carries the twin copy as a classic
 * script. Two copies by design (module vs classic-script contexts); if you
 * change one, change the other. Phase 4 may unify them.
 *
 * Base path — object.html has no access to the bundle's getBasePath(), so
 * the caller passes the site's base path (Jekyll's site.baseurl, rendered at
 * template time) as the `base` argument.
 *
 * Loaded as a classic script (object.html mixes classic and module scripts,
 * so no module system can be assumed): wrapped in an IIFE and published on
 * window.telarLoadWaveSurfer, reachable from the object-page inline scripts.
 *
 * @version v1.6.0
 */

(function () {
  'use strict';

  /**
   * Load WaveSurfer v7 core + Regions plugin from the vendored bundles under
   * assets/vendor/wavesurfer/. Cached on window._wsApiPromise so repeat calls
   * on the same page return the in-flight or resolved promise instead of
   * re-injecting the scripts.
   *
   * @param {string} base - Site base path (site.baseurl), prefixed to the
   *   vendored script URLs.
   * @returns {Promise<void>}
   */
  function telarLoadWaveSurfer(base) {
    if (window._wsApiPromise) return window._wsApiPromise;
    window._wsApiPromise = new Promise((resolve, reject) => {
      const core = document.createElement('script');
      core.src = base + '/assets/vendor/wavesurfer/wavesurfer.min.js';
      core.onload = () => {
        const regions = document.createElement('script');
        regions.src = base + '/assets/vendor/wavesurfer/plugins/regions.min.js';
        regions.onload = () => resolve();
        regions.onerror = reject;
        document.head.appendChild(regions);
      };
      core.onerror = reject;
      document.head.appendChild(core);
    });
    return window._wsApiPromise;
  }

  window.telarLoadWaveSurfer = telarLoadWaveSurfer;
})();
