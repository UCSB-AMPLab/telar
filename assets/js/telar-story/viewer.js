/**
 * Telar Story – Viewer Card Management
 *
 * This module manages the IIIF viewer cards that display exhibition objects
 * alongside story steps. Each object gets its own viewer card — a container
 * element that the script creates and adds to the page at runtime, holding
 * a UniversalViewer instance inside it. The cards are not part of the HTML
 * template because the number needed depends on the story's content.
 *
 * UniversalViewer instances are expensive: each one fetches an IIIF manifest
 * over the network, initialises OpenSeadragon (the image viewer library
 * inside UV), and allocates GPU memory for rendering high-resolution tiles.
 * Creating all viewers at page load would exhaust memory on mobile devices
 * and delay the page becoming responsive.
 *
 * To solve this, the module uses a card pool with a configurable maximum
 * (default 10 cards). When the user navigates to a step that needs an object
 * we have already loaded, we reuse the existing card. When we need a new card
 * and the pool is full, we destroy the oldest one — the card least likely to
 * be needed soon. This gives the illusion of instant switching for recently
 * visited objects while keeping memory bounded.
 *
 * Cards that are not currently visible sit off-screen with the CSS class
 * "card-below" and get promoted to "card-active" when their object is needed.
 *
 * The module also handles viewer positioning (converting normalised 0–1
 * coordinates from story step data into the values OpenSeadragon expects),
 * manifest prefetching at page load to warm the browser cache and measure
 * connection speed, loading shimmer states, and the object credits badge.
 *
 * @version v0.7.0-beta
 */

import { state } from './state.js';
import { getBasePath, calculateViewportPosition } from './utils.js';

// ── Object index ─────────────────────────────────────────────────────────────

/**
 * Build a lookup index from the objects data injected by Jekyll.
 * Populates state.objectsIndex for O(1) access by object_id.
 */
export function buildObjectsIndex() {
  const objects = window.objectsData || [];
  objects.forEach(obj => {
    state.objectsIndex[obj.object_id] = obj;
  });
}

// ── Manifest URLs ────────────────────────────────────────────────────────────

/**
 * Get the IIIF manifest URL for an object.
 *
 * Checks for an external source URL first (the source_url or iiif_manifest
 * field from the objects spreadsheet). Falls back to a locally-generated
 * manifest built from the site's base path.
 *
 * @param {string} objectId - The object identifier.
 * @returns {string} The manifest URL.
 */
export function getManifestUrl(objectId) {
  const object = state.objectsIndex[objectId];

  if (!object) {
    console.warn('Object not found:', objectId);
    return buildLocalInfoJsonUrl(objectId);
  }

  const sourceUrl = object.source_url || object.iiif_manifest;
  if (sourceUrl && sourceUrl.trim() !== '') {
    return sourceUrl;
  }

  return buildLocalInfoJsonUrl(objectId);
}

/**
 * Build a local IIIF manifest URL from the site's base path.
 *
 * @param {string} objectId - The object identifier.
 * @returns {string} Full URL to the local manifest.json.
 */
function buildLocalInfoJsonUrl(objectId) {
  const basePath = getBasePath();
  const manifestUrl = `${window.location.origin}${basePath}/iiif/objects/${objectId}/manifest.json`;
  console.log('Building local IIIF manifest URL:', manifestUrl);
  return manifestUrl;
}

// ── Viewer card lifecycle ────────────────────────────────────────────────────

/**
 * @typedef {Object} ViewerCard
 * @property {string} objectId - The object this card displays.
 * @property {HTMLElement} element - The card's container element in the page.
 * @property {Object} uvInstance - The UniversalViewer instance.
 * @property {Object|null} osdViewer - The OpenSeadragon viewer (null until ready).
 * @property {boolean} isReady - Whether the OSD viewer has initialised.
 * @property {Object|null} pendingZoom - Queued position to apply when ready.
 * @property {number} zIndex - The card's stacking order.
 */

/**
 * Create a new viewer card for an object.
 *
 * Builds a container element, initialises a UniversalViewer instance inside
 * it, and begins polling for the OpenSeadragon viewer to become available.
 * Once ready, any pending zoom position is applied.
 *
 * If the card pool exceeds the configured maximum, the oldest card is
 * destroyed to free memory.
 *
 * @param {string} objectId - The object to display.
 * @param {number} zIndex - Stacking order for the card element.
 * @param {number} [x] - Normalised x position (0–1).
 * @param {number} [y] - Normalised y position (0–1).
 * @param {number} [zoom] - Zoom multiplier relative to home zoom.
 * @returns {ViewerCard|null} The created card, or null on error.
 */
export function createViewerCard(objectId, zIndex, x, y, zoom) {
  const container = document.getElementById('viewer-cards-container');

  const cardElement = document.createElement('div');
  cardElement.className = 'viewer-card card-below';
  cardElement.style.zIndex = zIndex;
  cardElement.dataset.object = objectId;

  const viewerId = `viewer-instance-${state.viewerCardCounter}`;
  const viewerDiv = document.createElement('div');
  viewerDiv.className = 'viewer-instance';
  viewerDiv.id = viewerId;

  cardElement.appendChild(viewerDiv);
  container.appendChild(cardElement);

  console.log(`Created viewer card for ${objectId} with z-index ${zIndex}, will snap to x=${x}, y=${y}, zoom=${zoom}`);

  const manifestUrl = getManifestUrl(objectId);
  if (!manifestUrl) {
    console.error('Could not determine manifest URL for:', objectId);
    return null;
  }

  // Initialise UniversalViewer
  const urlAdaptor = new UV.IIIFURLAdaptor();
  const data = urlAdaptor.getInitialData({
    manifest: manifestUrl,
    embedded: true,
  });

  const uvInstance = UV.init(viewerId, data);
  urlAdaptor.bindTo(uvInstance);

  const viewerCard = {
    objectId,
    element: cardElement,
    uvInstance,
    osdViewer: null,
    isReady: false,
    pendingZoom: (!isNaN(x) && !isNaN(y) && !isNaN(zoom)) ? { x, y, zoom, snap: true } : null,
    zIndex,
  };

  // Poll for OpenSeadragon readiness instead of using a fixed delay
  uvInstance.on('created', function () {
    let pollCount = 0;
    const MAX_POLLS = 50; // 5 seconds max (50 × 100 ms)

    const checkViewerReady = () => {
      pollCount++;
      let newViewer = null;

      if (uvInstance._assignedContentHandler) {
        if (uvInstance._assignedContentHandler.viewer) {
          newViewer = uvInstance._assignedContentHandler.viewer;
          console.log(`Got viewer via direct access for ${objectId} after ${pollCount * 100}ms`);
        } else if (uvInstance._assignedContentHandler.extension) {
          const ext = uvInstance._assignedContentHandler.extension;
          if (ext.centerPanel && ext.centerPanel.viewer) {
            newViewer = ext.centerPanel.viewer;
            console.log(`Got viewer via extension path for ${objectId} after ${pollCount * 100}ms`);
          }
        }
      }

      if (newViewer) {
        viewerCard.osdViewer = newViewer;
        viewerCard.isReady = true;
        console.log(`Viewer card for ${objectId} is ready after ${pollCount * 100}ms`);

        // Hide UV controls
        setTimeout(() => {
          const leftPanel = cardElement.querySelector('.leftPanel');
          if (leftPanel) {
            leftPanel.style.display = 'none';
            leftPanel.style.visibility = 'hidden';
          }
        }, 100);

        // Execute pending position
        if (viewerCard.pendingZoom) {
          if (viewerCard.pendingZoom.snap) {
            snapViewerToPosition(viewerCard, viewerCard.pendingZoom.x, viewerCard.pendingZoom.y, viewerCard.pendingZoom.zoom);
          } else {
            animateViewerToPosition(viewerCard, viewerCard.pendingZoom.x, viewerCard.pendingZoom.y, viewerCard.pendingZoom.zoom);
          }
          viewerCard.pendingZoom = null;
        }
      } else if (pollCount < MAX_POLLS) {
        setTimeout(checkViewerReady, 100);
      } else {
        console.warn(`Viewer for ${objectId} failed to initialize after 5s, allowing transition`);
        viewerCard.isReady = true;
      }
    };

    checkViewerReady();
  });

  state.viewerCards.push(viewerCard);
  state.viewerCardCounter++;

  // Enforce pool size limit
  if (state.viewerCards.length > state.config.maxViewerCards) {
    const oldest = state.viewerCards.shift();
    destroyViewerCard(oldest);
  }

  return viewerCard;
}

/**
 * Get an existing viewer card for an object, or create a new one.
 *
 * If a card already exists for this object, it is reused: its z-index is
 * updated, its CSS state is reset, and it snaps to the requested position.
 *
 * @param {string} objectId - The object to display.
 * @param {number} zIndex - Stacking order.
 * @param {number} [x] - Normalised x position.
 * @param {number} [y] - Normalised y position.
 * @param {number} [zoom] - Zoom multiplier.
 * @returns {ViewerCard|null}
 */
export function getOrCreateViewerCard(objectId, zIndex, x, y, zoom) {
  console.log(`getOrCreateViewerCard called for ${objectId}`);
  console.log(`Current viewerCards: ${state.viewerCards.map(vc => vc.objectId).join(', ')}`);

  const existing = state.viewerCards.find(vc => vc.objectId === objectId);

  if (existing) {
    console.log(`Reusing existing viewer card for ${objectId}`);
    existing.element.style.zIndex = zIndex;
    existing.zIndex = zIndex;

    console.log(`Resetting viewer card state for ${objectId}`);
    existing.element.classList.remove('card-below');

    if (!isNaN(x) && !isNaN(y) && !isNaN(zoom)) {
      if (existing.isReady) {
        snapViewerToPosition(existing, x, y, zoom);
      } else {
        existing.pendingZoom = { x, y, zoom, snap: true };
      }
    }

    return existing;
  }

  console.log(`Creating new viewer card for ${objectId}`);
  return createViewerCard(objectId, zIndex, x, y, zoom);
}

/**
 * Destroy a viewer card and clean up its resources.
 *
 * @param {ViewerCard} viewerCard - The card to destroy.
 */
export function destroyViewerCard(viewerCard) {
  console.log(`Destroying viewer card for ${viewerCard.objectId}`);

  if (viewerCard.element && viewerCard.element.parentNode) {
    viewerCard.element.parentNode.removeChild(viewerCard.element);
  }

  viewerCard.uvInstance = null;
  viewerCard.osdViewer = null;
}

// ── First viewer ─────────────────────────────────────────────────────────────

/**
 * Create and activate the first viewer card on page load.
 *
 * Reads the first object from window.storyData, creates a viewer card for it,
 * and makes it immediately visible. Also shows the credits badge for the
 * initial object.
 */
export function initializeFirstViewer() {
  const firstObjectId = window.storyData?.firstObject;

  if (!firstObjectId) {
    console.error('No first object specified in story data');
    return;
  }

  console.log('Initializing first viewer for object:', firstObjectId);

  const steps = window.storyData?.steps || [];
  const firstRealStep = steps.find(step => step.object === firstObjectId);

  const x = firstRealStep ? parseFloat(firstRealStep.x) : undefined;
  const y = firstRealStep ? parseFloat(firstRealStep.y) : undefined;
  const zoom = firstRealStep ? parseFloat(firstRealStep.zoom) : undefined;

  const viewerCard = createViewerCard(firstObjectId, 1, x, y, zoom);

  if (viewerCard) {
    state.currentViewerCard = viewerCard;
    viewerCard.element.classList.remove('card-below');
    viewerCard.element.classList.add('card-active');

    updateObjectCredits(firstObjectId);
  }
}

// ── Viewer positioning ───────────────────────────────────────────────────────

/**
 * Animate a viewer card to a position over 4 seconds.
 *
 * Used when the user navigates to a different step that references the same
 * object — the viewer pans and zooms smoothly to the new position.
 *
 * @param {ViewerCard} viewerCard - The card to animate.
 * @param {number} x - Normalised x position (0–1).
 * @param {number} y - Normalised y position (0–1).
 * @param {number} zoom - Zoom multiplier relative to home zoom.
 */
export function animateViewerToPosition(viewerCard, x, y, zoom) {
  if (!viewerCard || !viewerCard.osdViewer) {
    console.warn('Viewer card or OpenSeadragon viewer not ready for animation');
    return;
  }

  console.log(`Animating viewer to position: x=${x}, y=${y}, zoom=${zoom} over 4 seconds`);

  const osdViewer = viewerCard.osdViewer;
  const viewport = osdViewer.viewport;
  const { point, actualZoom } = calculateViewportPosition(viewport, x, y, zoom);

  console.log(`OSD coordinates - point: ${point.x}, ${point.y}, zoom: ${actualZoom}, homeZoom: ${viewport.getHomeZoom()}`);

  // Disable click-to-zoom during animation
  osdViewer.gestureSettingsMouse.clickToZoom = false;
  osdViewer.gestureSettingsTouch.clickToZoom = false;

  // Set smooth animation parameters
  const originalAnimationTime = osdViewer.animationTime;
  const originalSpringStiffness = osdViewer.springStiffness;

  osdViewer.animationTime = 4.0;
  osdViewer.springStiffness = 0.8;

  console.log(`Set animation time to ${osdViewer.animationTime}s, spring stiffness to ${osdViewer.springStiffness}`);

  viewport.panTo(point, false);
  viewport.zoomTo(actualZoom, point, false);

  // Restore original values after animation
  setTimeout(() => {
    osdViewer.animationTime = originalAnimationTime;
    osdViewer.springStiffness = originalSpringStiffness;
  }, 4100);
}

/**
 * Snap a viewer card to a position immediately (no animation).
 *
 * Used on initial load or when switching to a different object — the viewer
 * jumps straight to the target position.
 *
 * @param {ViewerCard} viewerCard - The card to position.
 * @param {number} x - Normalised x position (0–1).
 * @param {number} y - Normalised y position (0–1).
 * @param {number} zoom - Zoom multiplier relative to home zoom.
 */
export function snapViewerToPosition(viewerCard, x, y, zoom) {
  if (!viewerCard || !viewerCard.osdViewer) {
    console.warn('Viewer card or OpenSeadragon viewer not ready for snap');
    return;
  }

  const osdViewer = viewerCard.osdViewer;
  const viewport = osdViewer.viewport;
  const { point, actualZoom } = calculateViewportPosition(viewport, x, y, zoom);

  console.log(`Snapping to position immediately: x=${x}, y=${y}, zoom=${zoom}`);

  viewport.panTo(point, true);
  viewport.zoomTo(actualZoom, point, true);
}

/**
 * Animate a viewer card to a named region.
 *
 * @param {ViewerCard} viewerCard - The card to animate.
 * @param {string} region - Region string in "x,y,width,height" format (normalised 0–1).
 */
export function animateViewerToRegion(viewerCard, region) {
  if (!viewerCard || !viewerCard.osdViewer) {
    console.warn('Viewer card or OpenSeadragon viewer not ready');
    return;
  }

  console.log('Animating to region:', region);

  const parts = region.split(',').map(parseFloat);
  if (parts.length !== 4) {
    console.warn('Invalid region format, expected x,y,width,height');
    return;
  }

  const [rx, ry, width, height] = parts;
  const rect = { x: rx, y: ry, width: width, height: height };

  viewerCard.osdViewer.viewport.fitBounds(rect, true);
}

// ── Object switching ─────────────────────────────────────────────────────────

/**
 * Poll a viewer card until ready (or timeout), then activate it.
 *
 * This is the shared core of switchToObject and switchToObjectMobile. It
 * handles the loading shimmer, polls the card's isReady flag, and once ready
 * (or after 5 seconds) swaps the CSS classes and updates the credits badge.
 * An optional onReady callback lets the caller perform direction-specific
 * work such as activating a text step element.
 *
 * @param {ViewerCard} newViewerCard - The card to activate.
 * @param {string} objectId - The object ID (for logging and credits).
 * @param {Object} [options]
 * @param {function} [options.onReady] - Called just before the card class swap.
 */
function activateViewerCard(newViewerCard, objectId, options = {}) {
  const { onReady } = options;

  if (!newViewerCard.isReady) {
    showViewerSkeletonState();
  }

  const startTime = Date.now();
  const MAX_WAIT_TIME = 5000;

  const checkReady = () => {
    const elapsed = Date.now() - startTime;
    const ready = newViewerCard.isReady;
    const timedOut = elapsed >= MAX_WAIT_TIME;

    if (ready || timedOut) {
      if (timedOut && !ready) {
        console.warn(`Viewer for ${objectId} failed to load after 5 seconds, transitioning anyway`);
      } else {
        console.log(`Viewer ready for ${objectId}`);
      }

      hideViewerSkeletonState();

      if (onReady) {
        onReady(newViewerCard);
      }

      // Swap viewer cards
      if (state.currentViewerCard && state.currentViewerCard !== newViewerCard) {
        state.currentViewerCard.element.classList.remove('card-active');
        state.currentViewerCard.element.classList.add('card-below');
      }
      newViewerCard.element.classList.remove('card-below');
      newViewerCard.element.classList.add('card-active');

      state.currentViewerCard = newViewerCard;
      updateObjectCredits(objectId);
    } else {
      console.log(`Viewer not ready yet, waiting... (${elapsed}ms elapsed)`);
      setTimeout(checkReady, 100);
    }
  };

  checkReady();
}

/**
 * Switch to a different IIIF object (desktop navigation).
 *
 * Handles direction-aware transitions: in forward mode, activates the text
 * step element and sets the card's z-index. In backward mode, just swaps
 * the viewer cards.
 *
 * @param {string} objectId - The object to switch to.
 * @param {number} stepNumber - Current step number (for z-index).
 * @param {number} x - Normalised x position.
 * @param {number} y - Normalised y position.
 * @param {number} zoom - Zoom multiplier.
 * @param {HTMLElement} stepElement - The text step element in the page.
 * @param {string} [direction='forward'] - Navigation direction.
 */
export function switchToObject(objectId, stepNumber, x, y, zoom, stepElement, direction = 'forward') {
  console.log(`Switching to object: ${objectId} at step ${stepNumber} with position x=${x}, y=${y}, zoom=${zoom} (${direction})`);

  const newViewerCard = getOrCreateViewerCard(objectId, stepNumber, x, y, zoom);

  activateViewerCard(newViewerCard, objectId, {
    onReady: (card) => {
      if (direction === 'forward') {
        if (stepElement) {
          stepElement.offsetHeight; // Force reflow for CSS transition
          requestAnimationFrame(() => {
            stepElement.classList.add('is-active');
          });
        }
        card.element.style.zIndex = card.zIndex;
      }
    },
  });
}

/**
 * Switch to a different IIIF object (mobile/embed navigation).
 *
 * Simplified version without direction or text step activation.
 *
 * @param {string} objectId - The object to switch to.
 * @param {number} stepNumber - Current step number.
 * @param {number} x - Normalised x position.
 * @param {number} y - Normalised y position.
 * @param {number} zoom - Zoom multiplier.
 */
export function switchToObjectMobile(objectId, stepNumber, x, y, zoom) {
  console.log(`Mobile: Switching to object ${objectId} at step ${stepNumber}`);

  const newViewerCard = getOrCreateViewerCard(objectId, stepNumber, x, y, zoom);
  activateViewerCard(newViewerCard, objectId);
}

// ── Preloading ───────────────────────────────────────────────────────────────

/**
 * Prefetch all story manifests at page load and measure connection speed.
 *
 * Runs in the background — does not block page initialisation. Measures
 * fetch times to adjust loading thresholds for slow connections.
 */
export async function prefetchStoryManifests() {
  const objectIds = [...new Set(
    Array.from(document.querySelectorAll('[data-object]'))
      .map(el => el.dataset.object)
      .filter(Boolean)
  )];

  if (objectIds.length === 0) return;

  await Promise.all(objectIds.map(async (id) => {
    try {
      const objectData = state.objectsIndex[id];
      if (objectData?.iiif_manifest) {
        const start = performance.now();
        await fetch(objectData.iiif_manifest);
        const elapsed = performance.now() - start;
        state.manifestLoadTimes.push(elapsed);
      }
    } catch (e) { /* silent fail - network errors handled gracefully */ }
  }));

  adjustThresholdsForConnection();
}

/**
 * Adjust preloading thresholds based on measured connection speed.
 *
 * Slow connections get lower thresholds (show shimmer sooner) and higher
 * ready requirements (wait for more viewers before hiding shimmer).
 */
function adjustThresholdsForConnection() {
  if (state.manifestLoadTimes.length < 2) return;

  const avgTime = state.manifestLoadTimes.reduce((a, b) => a + b, 0) / state.manifestLoadTimes.length;

  if (avgTime > 1000) {
    state.config.loadingThreshold = 1;
    state.config.minReadyViewers = Math.min(6, state.config.preloadSteps);
    console.log(`Slow connection detected (${Math.round(avgTime)}ms avg), adjusting thresholds`);
  } else if (avgTime > 500) {
    state.config.loadingThreshold = Math.max(3, state.config.loadingThreshold - 2);
    state.config.minReadyViewers = Math.min(state.config.minReadyViewers + 1, state.config.preloadSteps);
    console.log(`Moderate connection detected (${Math.round(avgTime)}ms avg), adjusting thresholds`);
  }
}

/**
 * Show loading shimmer for stories with many unique viewers.
 *
 * Checks whether the story has enough unique viewers to warrant a loading
 * state, then polls until enough viewers are ready before hiding the shimmer.
 */
export function initializeLoadingShimmer() {
  const uniqueViewers = new Set(
    state.steps.map(step => step.dataset.object).filter(Boolean)
  ).size;

  console.log(`Story has ${uniqueViewers} unique viewers (threshold: ${state.config.loadingThreshold})`);

  if (uniqueViewers >= state.config.loadingThreshold) {
    showViewerSkeletonState();
    console.log(`Showing initial load shimmer (${uniqueViewers} >= ${state.config.loadingThreshold})`);

    const checkReadyViewers = () => {
      const readyCount = state.viewerCards.filter(v => v.isReady).length;
      const targetReady = Math.min(state.config.minReadyViewers, uniqueViewers);

      if (readyCount >= targetReady) {
        hideViewerSkeletonState();
        console.log(`Hiding shimmer: ${readyCount} viewers ready (target: ${targetReady})`);
      } else {
        setTimeout(checkReadyViewers, 200);
      }
    };

    setTimeout(checkReadyViewers, 500);
  }
}

/**
 * Preload viewer cards for steps near the current position.
 *
 * Creates viewer cards for upcoming and previous steps so they are ready
 * when the user navigates to them. Skips objects that already have cards.
 *
 * @param {number} currentIndex - The current step index.
 * @param {number} ahead - Number of steps to preload forward.
 * @param {number} behind - Number of steps to preload backward.
 */
export function preloadNearbyViewers(currentIndex, ahead, behind) {
  for (let offset = -behind; offset <= ahead; offset++) {
    if (offset === 0) continue;

    const idx = currentIndex + offset;
    if (idx < 0 || idx >= state.steps.length) continue;

    const step = state.steps[idx];
    const objectId = step.dataset.object;
    if (!objectId) continue;

    if (state.viewerCards.find(vc => vc.objectId === objectId)) continue;

    const x = parseFloat(step.dataset.x);
    const y = parseFloat(step.dataset.y);
    const zoom = parseFloat(step.dataset.zoom);

    console.log(`Preloading viewer for step ${idx}: ${objectId}`);
    getOrCreateViewerCard(objectId, idx, x, y, zoom);
  }
}

// ── Shimmer (loading skeleton) ───────────────────────────────────────────────

/**
 * Show the skeleton loading shimmer on the viewer container.
 */
export function showViewerSkeletonState() {
  const container = document.getElementById('viewer-cards-container');
  if (container) {
    container.classList.add('skeleton-loading');
  }
}

/**
 * Hide the skeleton loading shimmer on the viewer container.
 */
export function hideViewerSkeletonState() {
  const container = document.getElementById('viewer-cards-container');
  if (container) {
    container.classList.remove('skeleton-loading');
  }
}

// ── Object credits badge ─────────────────────────────────────────────────────

/**
 * Set up the credits badge dismiss button.
 *
 * The credits badge shows the attribution for the current object. Once
 * dismissed, it stays hidden for the rest of the session.
 */
export function initializeCredits() {
  if (!window.telarConfig?.showObjectCredits) return;

  const dismissBtn = document.getElementById('object-credits-dismiss');
  if (dismissBtn) {
    dismissBtn.addEventListener('click', function () {
      const badge = document.getElementById('object-credits-badge');
      if (badge) badge.classList.add('d-none');
      state.creditsDismissed = true;
    });
  }
}

/**
 * Update the credits badge to show the current object's attribution.
 *
 * @param {string} objectId - The object whose credit to display.
 */
export function updateObjectCredits(objectId) {
  if (!window.telarConfig?.showObjectCredits) return;
  if (state.creditsDismissed) return;

  const badge = document.getElementById('object-credits-badge');
  const textElement = document.getElementById('object-credits-text');

  if (!badge || !textElement) return;

  const objectData = state.objectsIndex[objectId];
  const credit = objectData?.credit;

  if (credit && credit.trim()) {
    const prefix = window.telarLang?.creditPrefix || 'Credit:';
    textElement.textContent = `${prefix} ${credit}`;
    badge.classList.remove('d-none');
  } else {
    badge.classList.add('d-none');
  }
}
