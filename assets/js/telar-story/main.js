/**
 * Telar Story – Entry Point
 *
 * This is the entry point for the story page JavaScript — the first module
 * that esbuild processes when bundling. It runs when the page has finished
 * loading its HTML structure (the DOMContentLoaded event) and orchestrates
 * the startup sequence: reading configuration, building data indexes, and
 * initialising each subsystem in the correct order.
 *
 * Configuration comes from two sources injected by Jekyll templates:
 * - window.telarConfig: site-level settings from _config.yml, including
 *   viewer preloading thresholds and feature flags like showObjectCredits.
 * - window.storyData: the current story's step data, object references,
 *   and first object identifier.
 *
 * After reading configuration, the module computes viewport-dependent
 * thresholds (scroll distance and swipe distance required to trigger a step
 * change) and then initialises the subsystems: object index, manifest
 * prefetching, first viewer card, navigation, panels, scroll lock, and
 * credits.
 *
 * Navigation mode is chosen automatically based on how the page is being
 * viewed. Embed mode (inside an iframe, detected by embed.js) and mobile
 * viewports (narrower than 768 px) both use button navigation. Desktop
 * viewports use scroll-based navigation with keyboard and touch support.
 *
 * For protected stories (v0.8.0+), initialization waits until the story is
 * unlocked via story-unlock.js. The unlock module fires a 'telar:story-unlocked'
 * event when decryption succeeds.
 *
 * This module also sets up window.TelarStory, which exposes internal state
 * and key functions for debugging in the browser console.
 *
 * @version v0.8.0-beta
 */

import { state } from './state.js';
import {
  buildObjectsIndex,
  initializeFirstViewer,
  prefetchStoryManifests,
  initializeCredits,
  switchToObject,
  animateViewerToPosition,
  getManifestUrl,
  createViewerCard,
  getOrCreateViewerCard,
} from './viewer.js';
import {
  initializeStepController,
  initializeButtonNavigation,
} from './navigation.js';
import {
  initializePanels,
  initializeScrollLock,
  openPanel,
  closeAllPanels,
} from './panels.js';

// ── Initialisation ───────────────────────────────────────────────────────────

/**
 * Initialize the story viewer and navigation.
 * Called on DOMContentLoaded for unencrypted stories,
 * or after unlock for encrypted stories.
 */
function initializeStory() {
  // Read viewer preloading config from _config.yml (via window.telarConfig)
  const viewerConfig = window.telarConfig?.viewer_preloading || {};
  state.config.maxViewerCards = Math.min(viewerConfig.max_viewer_cards || 10, 15);
  state.config.preloadSteps = Math.min(viewerConfig.preload_steps || 6, state.config.maxViewerCards - 2);
  state.config.loadingThreshold = viewerConfig.loading_threshold || 5;
  state.config.minReadyViewers = Math.min(viewerConfig.min_ready_viewers || 3, state.config.preloadSteps);

  // Compute viewport-dependent thresholds
  state.scrollThreshold = window.innerHeight * 0.5;  // 50vh
  state.touchThreshold = window.innerHeight * 0.2;   // 20vh

  buildObjectsIndex();

  // Prefetch manifests in background (async, does not block)
  prefetchStoryManifests();

  initializeFirstViewer();

  // Choose navigation mode
  state.isMobileViewport = window.innerWidth < 768;
  const isEmbedMode = window.telarEmbed?.enabled || false;

  if (isEmbedMode) {
    initializeButtonNavigation('embed');
  } else if (state.isMobileViewport) {
    initializeButtonNavigation('mobile');
  } else {
    initializeStepController();
  }

  initializePanels();
  initializeScrollLock();
  initializeCredits();
}

document.addEventListener('DOMContentLoaded', function () {
  // Check if story is encrypted and blocked
  if (window.storyData?.encrypted) {
    // Story is encrypted - wait for unlock event
    window.addEventListener('telar:story-unlocked', function () {
      initializeStory();
    }, { once: true });
  } else {
    // Story is not encrypted - initialize immediately
    initializeStory();
  }
});

// ── Debugging export ─────────────────────────────────────────────────────────

window.TelarStory = {
  state,
  switchToObject,
  animateViewerToPosition,
  openPanel,
  getManifestUrl,
  closeAllPanels,
  createViewerCard,
  getOrCreateViewerCard,
};
