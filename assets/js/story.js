/**
 * Telar Story - UniversalViewer + Step-Based Navigation
 * Handles card-stacking interactions for story pages
 */

// Step navigation
let allSteps = [];
let currentStepIndex = -1;
let scrollAccumulator = 0;
const SCROLL_THRESHOLD = window.innerHeight * 0.5; // 50vh
let currentObject = null;

// Scroll acceleration prevention
let lastStepChangeTime = 0;
const STEP_COOLDOWN = 600; // ms - prevent rapid step changes (400ms animation + 200ms buffer)
const MAX_SCROLL_DELTA = 200; // Cap scroll contribution per event
let currentViewerCard = null; // Currently active viewer card
let currentStepNumber = null; // Track current step to prevent duplicate processing
let panelStack = [];
let objectsIndex = {}; // Quick lookup for object data
let isPanelOpen = false; // Track if any panel is open
let scrollLockActive = false; // Track if scroll-lock is active

// Viewer card management
let viewerCards = []; // Array of { objectId, element, uvInstance, osdViewer, isReady, pendingZoom }
let viewerCardCounter = 0;
const MAX_VIEWER_CARDS = 5;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  buildObjectsIndex();
  initializeFirstViewer();
  initializeStepController();
  initializePanels();
  initializeScrollLock();
});

/**
 * Build index of objects for quick lookup
 */
function buildObjectsIndex() {
  const objects = window.objectsData || [];
  objects.forEach(obj => {
    objectsIndex[obj.object_id] = obj;
  });
}

/**
 * Initialize first viewer card on page load
 */
function initializeFirstViewer() {
  const firstObjectId = window.storyData?.firstObject;

  if (!firstObjectId) {
    console.error('No first object specified in story data');
    return;
  }

  console.log('Initializing first viewer for object:', firstObjectId);

  // Find the first step that has this object (skip intro and metadata)
  const steps = window.storyData?.steps || [];
  const firstRealStep = steps.find(step => step.object === firstObjectId);

  const x = firstRealStep ? parseFloat(firstRealStep.x) : undefined;
  const y = firstRealStep ? parseFloat(firstRealStep.y) : undefined;
  const zoom = firstRealStep ? parseFloat(firstRealStep.zoom) : undefined;

  // Create first viewer card with z-index 1 and make it active immediately
  const viewerCard = createViewerCard(firstObjectId, 1, x, y, zoom);

  // Set as current and activate it so it's visible on intro
  if (viewerCard) {
    currentViewerCard = viewerCard;
    viewerCard.element.classList.remove('card-below');
    viewerCard.element.classList.add('card-active');
  }
}

/**
 * Create a new viewer card for an object
 */
function createViewerCard(objectId, zIndex, x, y, zoom) {
  const container = document.getElementById('viewer-cards-container');

  // Create card element - stays off-screen initially
  const cardElement = document.createElement('div');
  cardElement.className = 'viewer-card card-below';
  cardElement.style.zIndex = zIndex;
  cardElement.dataset.object = objectId;

  // Create viewer instance container
  const viewerId = `viewer-instance-${viewerCardCounter}`;
  const viewerDiv = document.createElement('div');
  viewerDiv.className = 'viewer-instance';
  viewerDiv.id = viewerId;

  cardElement.appendChild(viewerDiv);
  container.appendChild(cardElement);

  console.log(`Created viewer card for ${objectId} with z-index ${zIndex}, will snap to x=${x}, y=${y}, zoom=${zoom}`);

  // Get manifest URL
  const manifestUrl = getManifestUrl(objectId);
  if (!manifestUrl) {
    console.error('Could not determine manifest URL for:', objectId);
    return null;
  }

  // Initialize UV in this card
  const urlAdaptor = new UV.IIIFURLAdaptor();
  const data = urlAdaptor.getInitialData({
    manifest: manifestUrl,
    embedded: true
  });

  const uvInstance = UV.init(viewerId, data);
  urlAdaptor.bindTo(uvInstance);

  // Track the card with pending position
  const viewerCard = {
    objectId,
    element: cardElement,
    uvInstance,
    osdViewer: null,
    isReady: false,
    pendingZoom: (!isNaN(x) && !isNaN(y) && !isNaN(zoom)) ? { x, y, zoom, snap: true } : null,
    zIndex
  };

  // Listen for UV initialization
  uvInstance.on('created', function() {
    setTimeout(function() {
      if (uvInstance._assignedContentHandler) {
        let newViewer = null;

        // Try direct viewer access FIRST (this path works reliably)
        if (uvInstance._assignedContentHandler.viewer) {
          newViewer = uvInstance._assignedContentHandler.viewer;
          console.log(`Got viewer via direct access for ${objectId}`);
        }
        // Fallback to extension path
        else if (uvInstance._assignedContentHandler.extension) {
          const ext = uvInstance._assignedContentHandler.extension;
          if (ext.centerPanel && ext.centerPanel.viewer) {
            newViewer = ext.centerPanel.viewer;
            console.log(`Got viewer via extension path for ${objectId}`);
          }
        }

        if (newViewer) {
          viewerCard.osdViewer = newViewer;
          viewerCard.isReady = true;
          console.log(`Viewer card for ${objectId} is ready`);

          // Hide UV controls via JavaScript
          setTimeout(() => {
            const leftPanel = cardElement.querySelector('.leftPanel');
            if (leftPanel) {
              leftPanel.style.display = 'none';
              leftPanel.style.visibility = 'hidden';
            }
          }, 100);

          // Execute pending position snap if any
          if (viewerCard.pendingZoom) {
            if (viewerCard.pendingZoom.snap) {
              // Snap immediately (for new object load)
              snapViewerToPosition(viewerCard, viewerCard.pendingZoom.x, viewerCard.pendingZoom.y, viewerCard.pendingZoom.zoom);
            } else {
              // Animate smoothly (for same object)
              animateViewerToPosition(viewerCard, viewerCard.pendingZoom.x, viewerCard.pendingZoom.y, viewerCard.pendingZoom.zoom);
            }
            viewerCard.pendingZoom = null;
          }
        }
      }
    }, 2000);
  });

  viewerCards.push(viewerCard);
  viewerCardCounter++;

  // Cleanup old viewers if we exceed maximum
  if (viewerCards.length > MAX_VIEWER_CARDS) {
    const oldest = viewerCards.shift();
    destroyViewerCard(oldest);
  }

  return viewerCard;
}

/**
 * Get existing viewer card or create new one
 */
function getOrCreateViewerCard(objectId, zIndex, x, y, zoom) {
  // Debug: log current state
  console.log(`getOrCreateViewerCard called for ${objectId}`);
  console.log(`Current viewerCards: ${viewerCards.map(vc => vc.objectId).join(', ')}`);

  // Check if we already have a viewer for this object
  const existing = viewerCards.find(vc => vc.objectId === objectId);

  if (existing) {
    console.log(`Reusing existing viewer card for ${objectId}`);
    // Update z-index if needed
    existing.element.style.zIndex = zIndex;
    existing.zIndex = zIndex;

    // CRITICAL FIX: Reset card state in case it was left in card-below from previous navigation
    // This ensures the card can properly transition when reactivated
    console.log(`Resetting viewer card state for ${objectId}`);
    existing.element.classList.remove('card-below');
    existing.element.style.opacity = ''; // Clear any inline opacity
    existing.element.style.transition = ''; // Clear any disabled transitions

    // For existing viewers, just snap to new position immediately
    if (!isNaN(x) && !isNaN(y) && !isNaN(zoom)) {
      if (existing.isReady) {
        snapViewerToPosition(existing, x, y, zoom);
      } else {
        existing.pendingZoom = { x, y, zoom, snap: true };
      }
    }

    return existing;
  }

  // Create new viewer card
  console.log(`Creating new viewer card for ${objectId}`);
  return createViewerCard(objectId, zIndex, x, y, zoom);
}

/**
 * Destroy a viewer card and clean up resources
 */
function destroyViewerCard(viewerCard) {
  console.log(`Destroying viewer card for ${viewerCard.objectId}`);

  // Remove from DOM
  if (viewerCard.element && viewerCard.element.parentNode) {
    viewerCard.element.parentNode.removeChild(viewerCard.element);
  }

  // TODO: Properly dispose UV instance if API provides method
  // For now, just remove reference
  viewerCard.uvInstance = null;
  viewerCard.osdViewer = null;
}

/**
 * Get manifest URL for an object
 */
function getManifestUrl(objectId) {
  const object = objectsIndex[objectId];

  if (!object) {
    console.warn('Object not found:', objectId);
    // Fallback to local IIIF
    return buildLocalInfoJsonUrl(objectId);
  }

  // If object has iiif_manifest field and it's not empty, use it
  if (object.iiif_manifest && object.iiif_manifest.trim() !== '') {
    return object.iiif_manifest;
  }

  // Otherwise use local IIIF
  return buildLocalInfoJsonUrl(objectId);
}

/**
 * Build local IIIF manifest.json URL
 */
function buildLocalInfoJsonUrl(objectId) {
  // Get the site's base URL from the page
  // For /telar/stories/story-1/, we want /telar
  const pathParts = window.location.pathname.split('/').filter(p => p);

  // Find the baseurl by removing the last 2 path segments (stories/story-1)
  let basePath = '';
  if (pathParts.length >= 2) {
    basePath = '/' + pathParts.slice(0, -2).join('/');
  }

  const manifestUrl = `${window.location.origin}${basePath}/iiif/objects/${objectId}/manifest.json`;
  console.log('Building local IIIF manifest URL:', manifestUrl);

  return manifestUrl;
}

/**
 * Initialize Step-Based Navigation Controller
 */
function initializeStepController() {
  // Get all steps and assign z-index for stacking
  allSteps = Array.from(document.querySelectorAll('.story-step'));

  allSteps.forEach((step, index) => {
    step.style.zIndex = index + 1; // Higher index = on top
    step.dataset.stepIndex = index;
  });

  // Start with first step if it exists
  if (allSteps.length > 0) {
    goToStep(0, 'forward');
  }

  // Keyboard navigation
  document.addEventListener('keydown', handleKeyboard);

  // Scroll accumulator
  window.addEventListener('wheel', handleScroll, { passive: false });

  console.log(`Step controller initialized with ${allSteps.length} steps`);
}

/**
 * Navigate to a specific step
 */
function goToStep(newIndex, direction = 'forward') {
  // Bounds check with improved logging
  if (newIndex < 0) {
    console.log(`⚠️ Cannot go to step ${newIndex}: already at first step (0)`);
    return;
  }
  if (newIndex >= allSteps.length) {
    console.log(`⚠️ Cannot go to step ${newIndex}: already at last step (${allSteps.length - 1})`);
    return;
  }

  const oldIndex = currentStepIndex;
  const newStep = allSteps[newIndex];
  const oldStep = oldIndex >= 0 ? allSteps[oldIndex] : null;

  console.log(`goToStep: ${oldIndex} → ${newIndex} (${direction})`);

  // Track step change time for cooldown
  lastStepChangeTime = Date.now();

  // Handle intro slide transitions
  if (oldIndex === 0 && newIndex > 0) {
    // Leaving intro - slide it up out of view and lower z-index
    const intro = allSteps[0];
    if (intro.classList.contains('story-intro')) {
      intro.style.transform = 'translateY(-100%)';
      intro.style.zIndex = '0'; // Lower z-index so it doesn't block viewers
    }
  } else if (newIndex === 0 && oldIndex > 0) {
    // Returning to intro - slide it back down and restore z-index
    const intro = allSteps[0];
    if (intro.classList.contains('story-intro')) {
      intro.style.zIndex = '10000'; // Restore high z-index
      intro.style.transform = 'translateY(0)';
    }
    // Clear current viewer reference so next forward movement triggers fresh switchToObject
    currentViewerCard = null;
    currentObject = null;
  }

  // When going backward, deactivate the old step (slide it down)
  if (direction === 'backward' && oldStep && oldIndex !== 0) {
    oldStep.classList.remove('is-active');
  }

  // Update index
  currentStepIndex = newIndex;

  // Get step data
  const objectId = newStep.dataset.object;
  const x = parseFloat(newStep.dataset.x);
  const y = parseFloat(newStep.dataset.y);
  const zoom = parseFloat(newStep.dataset.zoom);

  // Check if we need to switch objects or just pan/zoom current object
  // Improved detection: check both objectId AND that currentViewerCard matches
  // Special case: always switch when leaving intro (Step 0), even if viewer card exists
  const isLeavingIntro = (oldIndex === 0 && newIndex > 0);

  if (objectId && (!currentViewerCard || currentViewerCard.objectId !== objectId || isLeavingIntro)) {
    // Switching to different object - wait for both to be ready
    console.log(`Switching to new object: ${objectId}${isLeavingIntro ? ' (leaving intro)' : ''}`);
    switchToObject(objectId, newIndex, x, y, zoom, newStep, direction);
    currentObject = objectId;
  } else {
    // Same object - activate text immediately, animate viewer
    console.log(`Same object, activating text and animating viewer`);

    // Defensive fix: ensure viewer card is active when going forward
    // This prevents stuck viewers after backward→forward navigation
    if (direction === 'forward' && currentViewerCard) {
      currentViewerCard.element.classList.remove('card-below');
      currentViewerCard.element.classList.add('card-active');
    }

    // When going backward, don't add is-active (step is already visible underneath)
    // When going forward, force reflow before animating
    if (direction === 'forward') {
      newStep.offsetHeight;
      requestAnimationFrame(() => {
        newStep.classList.add('is-active');
      });
    }
    // If going backward, the step should already be active underneath

    if (currentViewerCard && !isNaN(x) && !isNaN(y) && !isNaN(zoom)) {
      if (currentViewerCard.isReady) {
        animateViewerToPosition(currentViewerCard, x, y, zoom);
      } else {
        console.warn('Viewer not ready, queueing zoom');
        currentViewerCard.pendingZoom = { x, y, zoom, snap: false };
      }
    }
  }

  updateViewerInfo(newIndex);

  // Preload upcoming viewers for smooth transitions
  preloadUpcomingViewers(newIndex);
}

/**
 * Navigate to next step
 */
function nextStep() {
  goToStep(currentStepIndex + 1, 'forward');
}

/**
 * Navigate to previous step
 */
function prevStep() {
  goToStep(currentStepIndex - 1, 'backward');
}

/**
 * Handle keyboard navigation
 */
function handleKeyboard(e) {
  switch(e.key) {
    case 'ArrowDown':
    case 'ArrowRight':
    case 'PageDown':
      e.preventDefault();
      nextStep();
      break;
    case 'ArrowUp':
    case 'ArrowLeft':
    case 'PageUp':
      e.preventDefault();
      prevStep();
      break;
    case ' ': // Space
      e.preventDefault();
      if (e.shiftKey) {
        prevStep();
      } else {
        nextStep();
      }
      break;
  }
}

/**
 * Handle scroll accumulation with acceleration prevention
 */
function handleScroll(e) {
  const now = Date.now();
  const timeSinceLastChange = now - lastStepChangeTime;

  // If we're in cooldown period, decay the accumulator instead of adding to it
  if (timeSinceLastChange < STEP_COOLDOWN) {
    // Decay accumulator during cooldown to prevent momentum buildup
    scrollAccumulator *= 0.5;
    return;
  }

  // Cap scroll delta to prevent huge jumps from trackpad acceleration
  const cappedDelta = Math.max(-MAX_SCROLL_DELTA, Math.min(MAX_SCROLL_DELTA, e.deltaY));
  scrollAccumulator += cappedDelta;

  if (scrollAccumulator >= SCROLL_THRESHOLD) {
    nextStep();
    scrollAccumulator = 0;
  } else if (scrollAccumulator <= -SCROLL_THRESHOLD) {
    prevStep();
    scrollAccumulator = 0;
  }
}

/**
 * Preload viewers for upcoming steps
 */
function preloadUpcomingViewers(currentIndex) {
  const PRELOAD_AHEAD = 2; // Preload 2 steps forward
  const PRELOAD_BEHIND = 1; // Preload 1 step backward

  // Preload forward
  for (let i = 1; i <= PRELOAD_AHEAD; i++) {
    const nextIndex = currentIndex + i;
    if (nextIndex >= allSteps.length) break;

    const nextStep = allSteps[nextIndex];
    const objectId = nextStep.dataset.object;

    // Skip if no object or already loaded
    if (!objectId) continue;
    const exists = viewerCards.find(vc => vc.objectId === objectId);
    if (exists) {
      console.log(`Viewer for ${objectId} already loaded`);
      continue;
    }

    // Preload this viewer off-screen
    const x = parseFloat(nextStep.dataset.x);
    const y = parseFloat(nextStep.dataset.y);
    const zoom = parseFloat(nextStep.dataset.zoom);

    console.log(`⏳ Preloading viewer for step ${nextIndex}: ${objectId}`);
    getOrCreateViewerCard(objectId, nextIndex, x, y, zoom);
  }

  // Preload backward (for going back)
  for (let i = 1; i <= PRELOAD_BEHIND; i++) {
    const prevIndex = currentIndex - i;
    if (prevIndex < 0) break;

    const prevStep = allSteps[prevIndex];
    const objectId = prevStep.dataset.object;

    if (!objectId) continue;
    const exists = viewerCards.find(vc => vc.objectId === objectId);
    if (exists) continue;

    const x = parseFloat(prevStep.dataset.x);
    const y = parseFloat(prevStep.dataset.y);
    const zoom = parseFloat(prevStep.dataset.zoom);

    console.log(`⏳ Preloading previous viewer for step ${prevIndex}: ${objectId}`);
    getOrCreateViewerCard(objectId, prevIndex, x, y, zoom);
  }
}

/**
 * Switch to a different IIIF object using viewer cards
 */
function switchToObject(objectId, stepNumber, x, y, zoom, stepElement, direction = 'forward') {
  console.log(`Switching to object: ${objectId} at step ${stepNumber} with position x=${x}, y=${y}, zoom=${zoom} (${direction})`);

  // Get or create viewer card for this object
  const newViewerCard = getOrCreateViewerCard(objectId, stepNumber, x, y, zoom);

  // Wait for viewer to be ready and positioned before sliding up BOTH cards together
  const startTime = Date.now();
  const MAX_WAIT_TIME = 5000; // 5 seconds max

  const slideUpWhenReady = () => {
    const elapsed = Date.now() - startTime;

    if (newViewerCard.isReady) {
      console.log(`Viewer ready, transitioning to ${objectId} (${direction})`);

      if (direction === 'forward') {
        // Going forward - slide up both text and viewer
        // Force a reflow to ensure initial state is rendered before animating
        if (stepElement) {
          stepElement.offsetHeight; // Force reflow
          requestAnimationFrame(() => {
            stepElement.classList.add('is-active');
          });
        }

        // Slide up the viewer card with complete state reset
        // This ensures reused cards are fully visible after backward→forward cycles
        newViewerCard.element.style.transition = ''; // Clear any disabled transitions
        newViewerCard.element.style.opacity = ''; // Clear any inline opacity from backward nav
        newViewerCard.element.classList.remove('card-below');
        newViewerCard.element.classList.add('card-active');

        // CRITICAL: Update z-index to ensure card appears on top
        newViewerCard.element.style.zIndex = newViewerCard.zIndex;

        // Old viewer cards keep card-active class and stay at translateY(0)
        // Z-index handles layering - newer cards appear on top
      } else {
        // Going backward - instantly hide current viewer and move it away
        if (currentViewerCard && currentViewerCard !== newViewerCard) {
          // Instantly hide and move away
          currentViewerCard.element.style.transition = 'none';
          currentViewerCard.element.classList.remove('card-active');
          currentViewerCard.element.classList.add('card-below');
          currentViewerCard.element.style.opacity = '0';

          // Re-enable transitions after moving
          setTimeout(() => {
            if (currentViewerCard) {
              currentViewerCard.element.style.transition = '';
              currentViewerCard.element.style.opacity = '';
            }
          }, 50);
        }

        // Previous viewer should already be visible underneath
        // Just ensure it has card-active
        if (!newViewerCard.element.classList.contains('card-active')) {
          newViewerCard.element.classList.remove('card-below');
          newViewerCard.element.classList.add('card-active');
        }
      }

      // Update current viewer card reference
      currentViewerCard = newViewerCard;
    } else if (elapsed < MAX_WAIT_TIME) {
      console.log(`Viewer not ready yet, waiting... (${elapsed}ms elapsed)`);
      setTimeout(slideUpWhenReady, 100);
    } else {
      console.warn(`Viewer for ${objectId} failed to load after 5 seconds, transitioning anyway`);

      if (direction === 'forward') {
        // Activate text step and slide up viewer card anyway
        if (stepElement) {
          stepElement.offsetHeight; // Force reflow
          requestAnimationFrame(() => {
            stepElement.classList.add('is-active');
          });
        }

        // Slide up anyway to prevent black screen
        newViewerCard.element.classList.remove('card-below');
        newViewerCard.element.classList.add('card-active');

        // Old viewer cards keep card-active and stay at translateY(0)
      } else {
        // Going backward - instantly hide current viewer and move it away
        if (currentViewerCard && currentViewerCard !== newViewerCard) {
          // Instantly hide and move away
          currentViewerCard.element.style.transition = 'none';
          currentViewerCard.element.classList.remove('card-active');
          currentViewerCard.element.classList.add('card-below');
          currentViewerCard.element.style.opacity = '0';

          // Re-enable transitions after moving
          setTimeout(() => {
            if (currentViewerCard) {
              currentViewerCard.element.style.transition = '';
              currentViewerCard.element.style.opacity = '';
            }
          }, 50);
        }

        // Previous viewer should already be visible underneath
        if (!newViewerCard.element.classList.contains('card-active')) {
          newViewerCard.element.classList.remove('card-below');
          newViewerCard.element.classList.add('card-active');
        }
      }

      currentViewerCard = newViewerCard;
    }
  };

  // Start checking if ready
  slideUpWhenReady();
}

/**
 * Animate a viewer card to specific position using OpenSeadragon
 */
function animateViewerToPosition(viewerCard, x, y, zoom) {
  if (!viewerCard || !viewerCard.osdViewer) {
    console.warn('Viewer card or OpenSeadragon viewer not ready for animation');
    return;
  }

  console.log(`Animating viewer to position: x=${x}, y=${y}, zoom=${zoom} over 36 seconds`);

  const osdViewer = viewerCard.osdViewer;
  const viewport = osdViewer.viewport;

  // Get home zoom for reference
  const homeZoom = viewport.getHomeZoom();

  // Get image aspect ratio
  const imageBounds = viewport.getHomeBounds();

  // OpenSeadragon viewport coordinates: image bounds give us the frame
  // We need to position within that frame using our 0-1 coordinates
  const point = {
    x: imageBounds.x + (x * imageBounds.width),
    y: imageBounds.y + (y * imageBounds.height)
  };

  // Calculate the actual zoom level
  // Our zoom values (1, 2.5, 3, etc.) are relative to home zoom
  const actualZoom = homeZoom * zoom;

  console.log(`OSD coordinates - point: ${point.x}, ${point.y}, zoom: ${actualZoom}, homeZoom: ${homeZoom}`);

  // Configure OpenSeadragon viewer for smooth animations
  osdViewer.gestureSettingsMouse.clickToZoom = false;
  osdViewer.gestureSettingsTouch.clickToZoom = false;

  // Set animation parameters directly on the viewer
  const originalAnimationTime = osdViewer.animationTime;
  const originalSpringStiffness = osdViewer.springStiffness;

  osdViewer.animationTime = 4.0;  // Seconds for animation - smooth and cinematic
  osdViewer.springStiffness = 0.8;  // Lower = smoother, less bouncy

  console.log(`Set animation time to ${osdViewer.animationTime}s, spring stiffness to ${osdViewer.springStiffness}`);

  // Use viewport methods with immediate flag set to false for smooth animation
  viewport.panTo(point, false);
  viewport.zoomTo(actualZoom, point, false);

  // Reset after animation
  setTimeout(() => {
    osdViewer.animationTime = originalAnimationTime;
    osdViewer.springStiffness = originalSpringStiffness;
  }, 4100);
}

/**
 * Snap viewer to position immediately (no animation) - for initial load
 */
function snapViewerToPosition(viewerCard, x, y, zoom) {
  if (!viewerCard || !viewerCard.osdViewer) {
    console.warn('Viewer card or OpenSeadragon viewer not ready for snap');
    return;
  }

  const osdViewer = viewerCard.osdViewer;
  const viewport = osdViewer.viewport;

  // Get home zoom for reference
  const homeZoom = viewport.getHomeZoom();

  // Get image aspect ratio
  const imageBounds = viewport.getHomeBounds();

  // Calculate point
  const point = {
    x: imageBounds.x + (x * imageBounds.width),
    y: imageBounds.y + (y * imageBounds.height)
  };

  // Calculate zoom
  const actualZoom = homeZoom * zoom;

  console.log(`Snapping to position immediately: x=${x}, y=${y}, zoom=${zoom}`);

  // Use immediate flag (true) to snap instantly
  viewport.panTo(point, true);
  viewport.zoomTo(actualZoom, point, true);
}

/**
 * Animate viewer card to named region using OpenSeadragon
 * Region format: "x,y,width,height" (normalized 0-1 coordinates)
 */
function animateViewerToRegion(viewerCard, region) {
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

  const [x, y, width, height] = parts;
  const rect = { x: x, y: y, width: width, height: height };

  viewerCard.osdViewer.viewport.fitBounds(rect, true);
}

/**
 * Update viewer info overlay
 */
function updateViewerInfo(stepNumber) {
  const infoElement = document.getElementById('current-object-title');
  if (infoElement) {
    infoElement.textContent = `Step ${stepNumber}`;
  }
}

/**
 * Initialize panel system
 */
function initializePanels() {
  // Layer 1 panel triggers
  document.querySelectorAll('[data-panel="layer1"]').forEach(trigger => {
    trigger.addEventListener('click', function() {
      const stepNumber = this.dataset.step;
      // Clear stack and open layer1
      panelStack = [];
      openPanel('layer1', stepNumber);
    });
  });

  // Layer 2 panel triggers (using delegation since buttons are added dynamically)
  document.addEventListener('click', function(e) {
    if (e.target.matches('[data-panel="layer2"]')) {
      const stepNumber = e.target.dataset.step;
      // Open layer2 on top of layer1
      openPanel('layer2', stepNumber);
    }
  });

  // Layer 1 back button - closes the panel
  const layer1Back = document.getElementById('panel-layer1-back');
  if (layer1Back) {
    layer1Back.addEventListener('click', function() {
      closePanel('layer1');
    });
  }

  // Layer 2 back button - goes back to layer1
  const layer2Back = document.getElementById('panel-layer2-back');
  if (layer2Back) {
    layer2Back.addEventListener('click', function() {
      closePanel('layer2');
      // Layer 1 should still be visible underneath
    });
  }

  // Glossary back button
  const glossaryBack = document.getElementById('panel-glossary-back');
  if (glossaryBack) {
    glossaryBack.addEventListener('click', function() {
      closePanel('glossary');
      // Return to previous panel if exists
      if (panelStack.length > 0) {
        const previous = panelStack[panelStack.length - 1];
        // Panel should still be open
      }
    });
  }
}

/**
 * Open a panel with content
 */
function openPanel(panelType, contentId) {
  const panelId = `panel-${panelType}`;
  const panel = document.getElementById(panelId);

  if (!panel) return;

  // Get content from story data
  const content = getPanelContent(panelType, contentId);

  if (content) {
    // Update panel content
    document.getElementById(`${panelId}-title`).textContent = content.title;
    document.getElementById(`${panelId}-content`).innerHTML = content.html;

    // Track current panel
    if (panelType === 'layer1') {
      panelStack = [{ type: panelType, id: contentId }];
    } else {
      // Layer 2 or glossary - keep layer1 in stack
      panelStack.push({ type: panelType, id: contentId });
    }

    // Open panel
    const bsOffcanvas = new bootstrap.Offcanvas(panel);
    bsOffcanvas.show();

    // Activate scroll lock
    isPanelOpen = true;
    activateScrollLock();
  }
}

/**
 * Close a panel
 */
function closePanel(panelType) {
  const panelId = `panel-${panelType}`;
  const panel = document.getElementById(panelId);

  if (!panel) return;

  const bsOffcanvas = bootstrap.Offcanvas.getInstance(panel);
  if (bsOffcanvas) {
    bsOffcanvas.hide();
  }

  // Check if all panels are closed
  setTimeout(() => {
    const anyPanelOpen = document.querySelector('.offcanvas.show');
    if (!anyPanelOpen) {
      isPanelOpen = false;
      deactivateScrollLock();
    }
  }, 350); // Wait for Bootstrap animation to complete
}

/**
 * Get panel content from story data
 */
function getPanelContent(panelType, contentId) {
  // This will be populated from the story's YAML/JSON data
  const steps = window.storyData?.steps || [];
  const step = steps.find(s => s.step == contentId);

  if (!step) return null;

  if (panelType === 'layer1') {
    let html = formatPanelContent({
      text: step.layer1_text,
      media: step.layer1_media
    });

    // Add layer2 button if layer2 has content
    if ((step.layer2_title && step.layer2_title.trim() !== '') || (step.layer2_text && step.layer2_text.trim() !== '')) {
      const buttonLabel = (step.layer2_button && step.layer2_button.trim() !== '') ? step.layer2_button : 'Go deeper';
      html += `<p><button class="panel-trigger" data-panel="layer2" data-step="${contentId}">${buttonLabel} →</button></p>`;
    }

    return {
      title: step.layer1_title || 'Layer 1',
      html: html
    };
  } else if (panelType === 'layer2') {
    return {
      title: step.layer2_title || 'Layer 2',
      html: formatPanelContent({
        text: step.layer2_text,
        media: step.layer2_media
      })
    };
  } else if (panelType === 'glossary') {
    // Fetch from glossary data
    return {
      title: 'Glossary Term',
      html: '<p>Glossary content...</p>'
    };
  }

  return null;
}

/**
 * Format panel content (text + media)
 */
function formatPanelContent(panelData) {
  if (!panelData) return '<p>No content available.</p>';

  let html = '';

  // Get the base URL from the current path
  const pathParts = window.location.pathname.split('/').filter(p => p);
  let basePath = '';
  
  // Extract baseurl similar to buildLocalInfoJsonUrl logic
  if (pathParts.length >= 2) {
    basePath = '/' + pathParts.slice(0, -2).join('/');
  }

  if (panelData.text) {
    // Text is already HTML from markdown conversion
    // Fix image URLs within the text content
    html += fixImageUrls(panelData.text, basePath);
  }

  if (panelData.media && panelData.media.trim() !== '') {
    // Check if the media URL starts with "/" (site-relative)
    let mediaUrl = panelData.media;
    if (mediaUrl.startsWith('/') && !mediaUrl.startsWith('//')) {
      // Prepend the base path
      mediaUrl = basePath + mediaUrl;
    }
    
    html += `<img src="${mediaUrl}" alt="Panel image" class="img-fluid">`;
  }

  return html;
}

/**
 * Fix image URLs in HTML content to include baseurl
 */
function fixImageUrls(htmlContent, basePath) {
  // Create a temporary div to parse HTML
  const tempDiv = document.createElement('div');
  tempDiv.innerHTML = htmlContent;
  
  // Find all img tags
  const images = tempDiv.querySelectorAll('img');
  images.forEach(img => {
    const src = img.getAttribute('src');
    if (src && src.startsWith('/') && !src.startsWith('//')) {
      // Prepend the base path to site-relative URLs
      img.setAttribute('src', basePath + src);
    }
  });
  
  return tempDiv.innerHTML;
}

/**
 * Initialize scroll-lock system
 * Auto-closes panels when user continues scrolling
 */
function initializeScrollLock() {
  const narrativeColumn = document.querySelector('.narrative-column');
  if (!narrativeColumn) return;

  let scrollTimeout;

  narrativeColumn.addEventListener('scroll', function() {
    if (!isPanelOpen) return;

    // Clear existing timeout
    clearTimeout(scrollTimeout);

    // Set timeout to close panels if scrolling continues
    scrollTimeout = setTimeout(() => {
      if (isPanelOpen) {
        closeAllPanels();
      }
    }, 300); // Close after 300ms of scrolling
  });
}

/**
 * Activate scroll lock
 * Prevents step changes while panel is open
 */
function activateScrollLock() {
  scrollLockActive = true;
}

/**
 * Deactivate scroll lock
 * Allows step changes when panel is closed
 */
function deactivateScrollLock() {
  scrollLockActive = false;
}

/**
 * Close all open panels
 */
function closeAllPanels() {
  const openPanels = document.querySelectorAll('.offcanvas.show');
  openPanels.forEach(panel => {
    const bsOffcanvas = bootstrap.Offcanvas.getInstance(panel);
    if (bsOffcanvas) {
      bsOffcanvas.hide();
    }
  });

  isPanelOpen = false;
  deactivateScrollLock();
}

// Export for debugging
window.TelarStory = {
  viewerCards,
  currentViewerCard,
  scroller,
  switchToObject,
  animateViewerToPosition,
  openPanel,
  getManifestUrl,
  closeAllPanels,
  createViewerCard,
  getOrCreateViewerCard
};
