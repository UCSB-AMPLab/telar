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
 * - Vertical viewport (matchMedia-derived, see layout-mode.js): button navigation.
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
 * @version v1.4.0
 */

import { state } from './state.js';
import { getLayoutMode, onLayoutChange } from './layout-mode.js';
import {
  buildObjectsIndex,
  prefetchStoryManifests,
  initializeCredits,
  getManifestUrl,
} from './viewer.js';
import { initCardPool, activateCard } from './card-pool.js';
import { IiifViewer } from './iiif-viewer.js';

// Expose the IIIF wrapper class as a window global so inline scripts in
// `_layouts/object.html` can construct it without ESM gymnastics. This
// mirrors the prior `window.Tify = Tify` precedent that lived in the
// layout itself. The `typeof window` guard keeps
// the module safe under jsdom test imports.
if (typeof window !== 'undefined') {
  window.IiifViewer = IiifViewer;
}
import './video-card.js';
import { initializeButtonNavigation } from './navigation.js';
import { initScrollEngine, getScrollEngineState } from './scroll-engine.js';
import {
  initializePanels,
  initializeScrollLock,
  openPanel,
  closeAllPanels,
} from './panels.js';
import { applyDeepLinkOnLoad, navigateToStep, navigateToIntro, writeHash } from './deep-link.js';

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
  // state.isEmbed is set first so layout-mode.js callbacks can read the correct value.
  state.isEmbed = window.telarEmbed?.enabled || false;
  state.layoutMode = getLayoutMode();   // single source of truth — reads CSS vars via layout-mode.js

  // Refresh state.layoutMode + state.cardOverlayRect on every layout flip. Activation-time rect write lives in card-pool.js.
  onLayoutChange(({ to }) => {
    state.layoutMode = to;
    const activeCard = document.querySelector('.text-card.is-active');
    state.cardOverlayRect = activeCard ? activeCard.getBoundingClientRect() : null;
  });

  // iOS Safari uses button-only navigation — no fluid scroll
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);

  if (state.isEmbed) {
    initializeButtonNavigation();
    // Also init scroll engine so button nav can use advanceToStep.
    // In iframes, wheel events are unreliable; the primary input is button
    // presses via advanceToStep → lenis.scrollTo(). The scroll surface
    // provides the DOM overflow Lenis needs for scrollTo() to work.
    const stepCount = (window.storyData?.steps || []).filter(s => !s._metadata).length;
    initScrollEngine(stepCount);
  } else if (state.layoutMode === 'vertical') {
    initializeButtonNavigation();
  } else if (isIOS) {
    // iOS desktop (iPad) — use button nav, Lenis momentum scroll is unreliable
    initializeButtonNavigation();
  } else {
    // Lenis-powered continuous scroll engine
    const stepCount = (window.storyData?.steps || []).filter(s => !s._metadata).length;
    initScrollEngine(stepCount);
  }

  initializePanels();
  applyDeepLinkOnLoad();

  // Wire up nav button (Back to Home on intro, Back to Start elsewhere)
  const btnNav = document.getElementById('btn-nav-back');
  if (btnNav) {
    btnNav.classList.add('is-home');
    const homeUrl = btnNav.dataset.homeUrl;
    const homeText = btnNav.dataset.homeText;
    const startText = btnNav.dataset.startText;
    const textEl = btnNav.querySelector('.btn-nav-text');

    // Switch button mode based on current step
    state.onStepChange = (index) => {
      if (index < 0) {
        // On intro — show Back to Home
        btnNav.classList.remove('is-start');
        btnNav.classList.add('is-home');
        btnNav.href = homeUrl;
        if (textEl) textEl.textContent = homeText;
      } else {
        // Past intro — show Back to Start
        btnNav.classList.remove('is-home');
        btnNav.classList.add('is-start');
        btnNav.removeAttribute('href');
        if (textEl) textEl.textContent = startText;
      }
    };

    btnNav.addEventListener('click', (e) => {
      if (btnNav.classList.contains('is-start')) {
        e.preventDefault();
        navigateToIntro();
      }
      // is-home mode: default <a> link behaviour navigates to home
    });
  }

  // Wire up TOC section links on the intro card
  document.querySelectorAll('.intro-toc-link[data-target-step]').forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const step = parseInt(link.dataset.targetStep, 10);
      if (step) navigateToStep(step);
    });
  });

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
  navigateToStep,
};
