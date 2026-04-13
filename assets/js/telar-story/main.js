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
 * Navigation mode is chosen automatically based on how the page is being
 * viewed:
 * - Embed mode (inside an iframe, detected by embed.js): button navigation.
 * - Mobile viewport (< 768 px): button navigation.
 * - iOS Safari: button navigation (Lenis momentum scroll is unreliable
 *   on iOS; fluid scroll is deferred to button-only).
 * - Desktop (non-iOS): Lenis-powered scroll engine.
 *
 * For protected stories (v0.8.0+), initialization waits until the story is
 * unlocked via story-unlock.js. The unlock module fires a 'telar:story-unlocked'
 * event when decryption succeeds.
 *
 * This module also sets up window.TelarStory, which exposes internal state
 * and key functions for debugging in the browser console.
 *
 * @version v1.1.0
 */

import { state } from './state.js';
import {
  buildObjectsIndex,
  prefetchStoryManifests,
  initializeCredits,
  getManifestUrl,
} from './viewer.js';
import { initCardPool, activateCard } from './card-pool.js';
import './video-card.js';
import { initializeButtonNavigation } from './navigation.js';
import { initScrollEngine, getScrollEngineState } from './scroll-engine.js';
import {
  initializePanels,
  initializeScrollLock,
  openPanel,
  closeAllPanels,
} from './panels.js';
import { applyDeepLinkOnLoad } from './deep-link.js';

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

  buildObjectsIndex();

  // Prefetch manifests in background (async, does not block)
  prefetchStoryManifests();

  // Read card-stack config and initialize card pool (creates all DOM elements)
  const cardConfig = {
    peekHeight: window.telarConfig?.cardPeekHeight ?? 1,
    messiness: window.telarConfig?.cardMessiness ?? 20,
  };
  initCardPool(window.storyData, cardConfig);

  // Choose navigation mode
  state.isMobileViewport = window.innerWidth < 768;
  const isEmbedMode = window.telarEmbed?.enabled || false;

  // iOS Safari uses button-only navigation — no fluid scroll
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);

  if (isEmbedMode) {
    initializeButtonNavigation('embed');
    // Also init scroll engine so button nav can use advanceToStep.
    // In iframes, wheel events are unreliable; the primary input is button
    // presses via advanceToStep → lenis.scrollTo(). The scroll surface
    // provides the DOM overflow Lenis needs for scrollTo() to work.
    const stepCount = (window.storyData?.steps || []).filter(s => !s._metadata).length;
    initScrollEngine(stepCount);
  } else if (state.isMobileViewport) {
    initializeButtonNavigation('mobile');
  } else if (isIOS) {
    // iOS desktop (iPad) — use button nav, Lenis momentum scroll is unreliable
    initializeButtonNavigation('mobile');
  } else {
    // Lenis-powered continuous scroll engine
    const stepCount = (window.storyData?.steps || []).filter(s => !s._metadata).length;
    initScrollEngine(stepCount);
  }

  initializePanels();
  applyDeepLinkOnLoad();
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
  activateCard,
  openPanel,
  getManifestUrl,
  closeAllPanels,
  getScrollEngineState,
};
