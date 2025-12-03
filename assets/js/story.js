/**
 * Telar Story - UniversalViewer + Step-Based Navigation
 * Handles card-stacking interactions for story pages
 *
 * @version v0.6.0-beta
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
let creditsDismissed = false; // Track object credits dismissal (per-session)

// Touch navigation for iPad/tablets in desktop mode (v0.4.3)
// Handles swipe gestures to navigate between story steps
// Note: Mobile viewports (<768px) use button navigation instead
let touchStartY = 0;  // Y coordinate where touch started
let touchEndY = 0;    // Y coordinate where touch ended
const TOUCH_THRESHOLD = window.innerHeight * 0.2; // 20vh swipe distance required to trigger step change

// Viewer card management
let viewerCards = []; // Array of { objectId, element, uvInstance, osdViewer, isReady, pendingZoom }
let viewerCardCounter = 0;

// Viewer preloading configuration (set from _config.yml via window.telarConfig)
// Defaults are used if config is missing. Higher values = smoother but more memory.
let MAX_VIEWER_CARDS = 10;    // Max UV instances in memory (default: 10, max: 15)
let PRELOAD_STEPS = 6;        // Steps to preload ahead (default: 6)
let LOADING_THRESHOLD = 5;    // Show shimmer if >= N unique viewers (default: 5)
let MIN_READY_VIEWERS = 3;    // Hide shimmer when N viewers ready (default: 3)

// Connection speed estimation from manifest load times
let manifestLoadTimes = [];

// Mobile navigation state
let isMobileViewport = false;
let currentMobileStep = 0;
let mobileNavButtons = null;
// Graceful panel transitions on mobile (v0.4.0)
let mobileNavigationCooldown = false;
const MOBILE_NAV_COOLDOWN = 400; // ms - prevent rapid clicking

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  // Read viewer preloading config from _config.yml (via window.telarConfig)
  // Apply defaults and validation to prevent misconfiguration
  const viewerConfig = window.telarConfig?.viewer_preloading || {};
  MAX_VIEWER_CARDS = Math.min(viewerConfig.max_viewer_cards || 10, 15);
  PRELOAD_STEPS = Math.min(viewerConfig.preload_steps || 6, MAX_VIEWER_CARDS - 2);
  LOADING_THRESHOLD = viewerConfig.loading_threshold || 5;
  MIN_READY_VIEWERS = Math.min(viewerConfig.min_ready_viewers || 3, PRELOAD_STEPS);

  buildObjectsIndex();

  // Prefetch manifests in background and measure connection speed
  // Runs async - doesn't block page initialization
  prefetchStoryManifests();

  initializeFirstViewer();

  // Determine navigation mode based on viewport and embed status
  // v0.5.0: Separate embed and mobile navigation modes
  isMobileViewport = window.innerWidth < 768;
  const isEmbedMode = window.telarEmbed?.enabled || false;

  if (isEmbedMode) {
    // Embed mode: button navigation for iframe/Canvas LMS compatibility
    initializeEmbedNavigation();
  } else if (isMobileViewport) {
    // Mobile mode: button navigation for mobile viewports
    initializeMobileNavigation();
  } else {
    // Desktop mode: scroll-based navigation
    initializeStepController();
  }

  initializePanels();
  initializeScrollLock();
  initializeCredits();
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
 * Prefetch all story manifests at page load and measure connection speed.
 * Runs in background - doesn't block page initialization.
 * Measures actual fetch times to adjust thresholds for slow connections.
 */
async function prefetchStoryManifests() {
  const objectIds = [...new Set(
    Array.from(document.querySelectorAll('[data-object]'))
      .map(el => el.dataset.object)
      .filter(Boolean)
  )];

  if (objectIds.length === 0) return;

  // Fetch manifests in parallel, timing each one
  await Promise.all(objectIds.map(async (id) => {
    try {
      const objectData = objectsIndex[id];
      if (objectData?.iiif_manifest) {
        const start = performance.now();
        await fetch(objectData.iiif_manifest);
        const elapsed = performance.now() - start;
        manifestLoadTimes.push(elapsed);
      }
    } catch (e) { /* silent fail - network errors handled gracefully */ }
  }));

  // Adjust thresholds based on measured connection speed
  adjustThresholdsForConnection();
}

/**
 * Adjust preloading thresholds based on measured connection speed.
 * Slow connections = frontload waiting by requiring more viewers ready.
 */
function adjustThresholdsForConnection() {
  if (manifestLoadTimes.length < 2) return; // Need enough samples

  const avgTime = manifestLoadTimes.reduce((a, b) => a + b, 0) / manifestLoadTimes.length;
  // Manifests are ~2KB, so timing reflects latency + minimal transfer

  if (avgTime > 1000) {
    // Slow connection (>1s per manifest): frontload wait
    LOADING_THRESHOLD = 1;        // Always show shimmer
    MIN_READY_VIEWERS = Math.min(6, PRELOAD_STEPS); // Wait for larger buffer
    console.log(`Slow connection detected (${Math.round(avgTime)}ms avg), adjusting thresholds`);
  } else if (avgTime > 500) {
    // Moderate connection (500ms-1s): slightly more cautious
    LOADING_THRESHOLD = Math.max(3, LOADING_THRESHOLD - 2);
    MIN_READY_VIEWERS = Math.min(MIN_READY_VIEWERS + 1, PRELOAD_STEPS);
    console.log(`Moderate connection detected (${Math.round(avgTime)}ms avg), adjusting thresholds`);
  }
  // Fast connection (<500ms): use configured defaults
}

/**
 * Initialize shimmer for stories with many unique viewers (v0.6.2)
 * Shows loading shimmer on intro slide while viewers initialize.
 * Uses LOADING_THRESHOLD and MIN_READY_VIEWERS from config.
 */
function initializeLoadingShimmer() {
  // Count unique viewers in the story
  const uniqueViewers = new Set(
    allSteps.map(step => step.dataset.object).filter(Boolean)
  ).size;

  console.log(`Story has ${uniqueViewers} unique viewers (threshold: ${LOADING_THRESHOLD})`);

  if (uniqueViewers >= LOADING_THRESHOLD) {
    showViewerSkeletonState();
    console.log(`Showing initial load shimmer (${uniqueViewers} >= ${LOADING_THRESHOLD})`);

    // Check periodically for enough ready viewers
    const checkReadyViewers = () => {
      const readyCount = viewerCards.filter(v => v.isReady).length;
      const targetReady = Math.min(MIN_READY_VIEWERS, uniqueViewers);

      if (readyCount >= targetReady) {
        hideViewerSkeletonState();
        console.log(`Hiding shimmer: ${readyCount} viewers ready (target: ${targetReady})`);
      } else {
        // Keep checking every 200ms
        setTimeout(checkReadyViewers, 200);
      }
    };

    // Start checking after a short delay (give preload time to start)
    setTimeout(checkReadyViewers, 500);
  }
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

    // Show credits badge for initial object
    updateObjectCredits(firstObjectId);
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

  // Listen for UV initialization - poll for OSD readiness instead of fixed delay
  uvInstance.on('created', function() {
    let pollCount = 0;
    const MAX_POLLS = 50; // 5 seconds max (50 × 100ms)

    const checkViewerReady = () => {
      pollCount++;
      let newViewer = null;

      if (uvInstance._assignedContentHandler) {
        // Try direct viewer access FIRST (this path works reliably)
        if (uvInstance._assignedContentHandler.viewer) {
          newViewer = uvInstance._assignedContentHandler.viewer;
          console.log(`Got viewer via direct access for ${objectId} after ${pollCount * 100}ms`);
        }
        // Fallback to extension path
        else if (uvInstance._assignedContentHandler.extension) {
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
      } else if (pollCount < MAX_POLLS) {
        // Keep polling
        setTimeout(checkViewerReady, 100);
      } else {
        // Timeout - allow transition anyway to prevent permanent black screen
        console.warn(`Viewer for ${objectId} failed to initialize after 5s, allowing transition`);
        viewerCard.isReady = true;
      }
    };

    // Start polling immediately
    checkViewerReady();
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

  // UniversalViewer doesn't provide a disposal API
  // Remove reference and let garbage collection handle cleanup
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

  // Check for external source URL (source_url or iiif_manifest for backward compatibility)
  const sourceUrl = object.source_url || object.iiif_manifest;
  if (sourceUrl && sourceUrl.trim() !== '') {
    return sourceUrl;
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
 * Create navigation button DOM elements
 * Shared by mobile and embed modes
 * @returns {Object|null} { container, prev, next } DOM elements, or null if already exists
 */
function createNavigationButtons() {
  // Guard against duplicate initialization
  if (document.querySelector('.mobile-nav')) {
    console.warn('Navigation buttons already exist, skipping creation');
    return null;
  }

  const navContainer = document.createElement('div');
  navContainer.className = 'mobile-nav';

  const prevButton = document.createElement('button');
  prevButton.className = 'mobile-prev';
  prevButton.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" height="32" viewBox="0 -960 960 960" width="32" fill="currentColor"><path d="M440-160v-487L216-423l-56-57 320-320 320 320-56 57-224-224v487h-80Z"/></svg>';
  prevButton.setAttribute('aria-label', 'Previous step');

  const nextButton = document.createElement('button');
  nextButton.className = 'mobile-next';
  nextButton.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" height="32" viewBox="0 -960 960 960" width="32" fill="currentColor"><path d="M440-800v487L216-537l-56 57 320 320 320-320-56-57-224 224v-487h-80Z"/></svg>';
  nextButton.setAttribute('aria-label', 'Next step');

  navContainer.appendChild(prevButton);
  navContainer.appendChild(nextButton);
  document.body.appendChild(navContainer);

  return { container: navContainer, prev: prevButton, next: nextButton };
}

/**
 * Initialize button navigation for embed mode
 * Uses mobile-style button navigation for iframe/Canvas LMS compatibility
 * Preserves desktop-style layout and vertical centering
 * v0.5.0: Canvas LMS / iframe embedding
 */
function initializeEmbedNavigation() {
  console.log('Initializing embed button navigation');

  // Get all story steps
  allSteps = Array.from(document.querySelectorAll('.story-step'));

  // Initialize shimmer for long stories (v0.6.2)
  initializeLoadingShimmer();

  // Hide all steps initially
  allSteps.forEach(step => {
    step.classList.remove('mobile-active');
  });

  // Show first step (intro)
  if (allSteps.length > 0) {
    allSteps[0].classList.add('mobile-active');
    currentMobileStep = 0;
  }

  // Create navigation buttons (shared helper)
  const buttons = createNavigationButtons();
  if (!buttons) return; // Already initialized

  mobileNavButtons = { prev: buttons.prev, next: buttons.next };

  // Add click handlers
  buttons.prev.addEventListener('click', goToPreviousMobileStep);
  buttons.next.addEventListener('click', goToNextMobileStep);

  // Initialize button states
  updateMobileButtonStates();

  console.log(`Embed navigation initialized with ${allSteps.length} steps`);
}

/**
 * Initialize Mobile Button Navigation
 * For mobile viewports (<768px), uses button-based navigation instead of scroll
 */
function initializeMobileNavigation() {
  console.log('Initializing mobile button navigation');

  // Get all story steps
  allSteps = Array.from(document.querySelectorAll('.story-step'));

  // Initialize shimmer for long stories (v0.6.2)
  initializeLoadingShimmer();

  // Hide all steps initially
  allSteps.forEach(step => {
    step.classList.remove('mobile-active');
  });

  // Show first step (intro)
  if (allSteps.length > 0) {
    allSteps[0].classList.add('mobile-active');
    currentMobileStep = 0;
  }

  // Create navigation buttons (shared helper)
  const buttons = createNavigationButtons();
  if (!buttons) return; // Already initialized

  mobileNavButtons = { prev: buttons.prev, next: buttons.next };

  // Add click handlers
  buttons.prev.addEventListener('click', goToPreviousMobileStep);
  buttons.next.addEventListener('click', goToNextMobileStep);

  // Initialize button states
  updateMobileButtonStates();

  console.log(`Mobile navigation initialized with ${allSteps.length} steps`);
}

/**
 * Go to next step (mobile)
 */
function goToNextMobileStep() {
  if (currentMobileStep >= allSteps.length - 1) {
    console.log('Already at last step');
    return;
  }

  const nextIndex = currentMobileStep + 1;
  goToMobileStep(nextIndex);
}

/**
 * Go to previous step (mobile)
 */
function goToPreviousMobileStep() {
  if (currentMobileStep <= 0) {
    console.log('Already at first step');
    return;
  }

  const prevIndex = currentMobileStep - 1;
  goToMobileStep(prevIndex);
}

/**
 * Navigate to a specific step (mobile)
 */
function goToMobileStep(newIndex) {
  if (newIndex < 0 || newIndex >= allSteps.length) {
    return;
  }

  // ====== Graceful panel transitions on mobile (v0.4.0) ======
  // Prevent rapid clicking
  if (mobileNavigationCooldown) {
    console.log('Mobile navigation on cooldown, ignoring tap');
    return;
  }

  // Check if viewer needs loading - show skeleton if not ready
  const newStep = allSteps[newIndex];
  const objectId = newStep.dataset.object;
  const viewerCard = viewerCards.find(vc => vc.objectId === objectId);

  if (!viewerCard || !viewerCard.isReady) {
    showViewerSkeletonState();
  }

  // Activate cooldown to prevent rapid clicking
  mobileNavigationCooldown = true;
  setTimeout(() => {
    mobileNavigationCooldown = false;
  }, MOBILE_NAV_COOLDOWN);
  // ====== End graceful transitions ======

  console.log(`Mobile navigation: ${currentMobileStep} → ${newIndex}`);

  // Hide current step
  allSteps[currentMobileStep].classList.remove('mobile-active');

  // Show new step
  allSteps[newIndex].classList.add('mobile-active');

  // Update current index
  currentMobileStep = newIndex;

  // Update button states
  updateMobileButtonStates();

  // Handle viewer updates (same as desktop)
  // Note: newStep and objectId already declared above for skeleton check
  const x = parseFloat(newStep.dataset.x);
  const y = parseFloat(newStep.dataset.y);
  const zoom = parseFloat(newStep.dataset.zoom);

  // Switch to object if different from current
  if (objectId && (!currentViewerCard || currentViewerCard.objectId !== objectId)) {
    console.log(`Switching to object: ${objectId}`);
    switchToObjectMobile(objectId, newIndex, x, y, zoom);
    currentObject = objectId;
  } else if (currentViewerCard && !isNaN(x) && !isNaN(y) && !isNaN(zoom)) {
    // Same object, just pan/zoom
    if (currentViewerCard.isReady) {
      animateViewerToPosition(currentViewerCard, x, y, zoom);
    } else {
      currentViewerCard.pendingZoom = { x, y, zoom, snap: false };
    }
  }

  updateViewerInfo(newIndex);

  // Graceful transitions: Preload upcoming viewers aggressively
  preloadMobileViewers(newIndex);
}

/**
 * Update mobile button states (enable/disable at boundaries)
 */
function updateMobileButtonStates() {
  if (!mobileNavButtons) return;

  // Disable prev at first step
  mobileNavButtons.prev.disabled = (currentMobileStep === 0);

  // Disable next at last step
  mobileNavButtons.next.disabled = (currentMobileStep === allSteps.length - 1);
}

/**
 * Switch to different object (mobile version)
 * Simplified without forward/backward animations
 */
function switchToObjectMobile(objectId, stepNumber, x, y, zoom) {
  console.log(`Mobile: Switching to object ${objectId} at step ${stepNumber}`);

  // Get or create viewer card
  const newViewerCard = getOrCreateViewerCard(objectId, stepNumber, x, y, zoom);

  // Wait for viewer to be ready
  const startTime = Date.now();
  const MAX_WAIT_TIME = 5000;

  const activateWhenReady = () => {
    const elapsed = Date.now() - startTime;

    if (newViewerCard.isReady) {
      console.log(`Mobile: Viewer ready for ${objectId}`);

      // Graceful transitions: Hide skeleton loading state
      hideViewerSkeletonState();

      // Hide old viewer if exists
      if (currentViewerCard && currentViewerCard !== newViewerCard) {
        currentViewerCard.element.classList.remove('card-active');
        currentViewerCard.element.classList.add('card-below');
      }

      // Show new viewer
      newViewerCard.element.classList.remove('card-below');
      newViewerCard.element.classList.add('card-active');

      // Update reference
      currentViewerCard = newViewerCard;

      // Update object credits badge
      updateObjectCredits(objectId);
    } else if (elapsed < MAX_WAIT_TIME) {
      setTimeout(activateWhenReady, 100);
    } else {
      console.warn(`Mobile: Viewer timeout for ${objectId}, showing anyway`);

      // Graceful transitions: Hide skeleton even on timeout
      hideViewerSkeletonState();

      // Show anyway to prevent black screen
      if (currentViewerCard && currentViewerCard !== newViewerCard) {
        currentViewerCard.element.classList.remove('card-active');
        currentViewerCard.element.classList.add('card-below');
      }

      newViewerCard.element.classList.remove('card-below');
      newViewerCard.element.classList.add('card-active');
      currentViewerCard = newViewerCard;

      // Update object credits badge
      updateObjectCredits(objectId);
    }
  };

  activateWhenReady();
}

/**
 * Initialize Step-Based Navigation Controller
 */
function initializeStepController() {
  // Get all steps and assign z-index for stacking
  allSteps = Array.from(document.querySelectorAll('.story-step'));

  // Initialize shimmer for long stories (v0.6.2)
  initializeLoadingShimmer();

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

  // Scroll accumulator for mouse/trackpad
  window.addEventListener('wheel', handleScroll, { passive: false });

  // Touch navigation for iPad/tablets in desktop mode (v0.4.3)
  // Enables swipe-to-navigate on touch devices that don't trigger 'wheel' events
  // Uses passive listeners for better scroll performance
  window.addEventListener('touchstart', handleTouchStart, { passive: true });
  window.addEventListener('touchend', handleTouchEnd, { passive: true });

  console.log(`Step controller initialized with ${allSteps.length} steps`);
}

/**
 * Navigate to a specific step
 */
function goToStep(newIndex, direction = 'forward') {
  // Bounds check with improved logging
  if (newIndex < 0) {
    console.log(`Cannot go to step ${newIndex}: already at first step (0)`);
    return;
  }
  if (newIndex >= allSteps.length) {
    console.log(`Cannot go to step ${newIndex}: already at last step (${allSteps.length - 1})`);
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

/* ============================================================
   PANEL FREEZE SYSTEM & SCROLL ISOLATION (v0.6.0)
   ============================================================
   When panels are open, story navigation is frozen to allow users
   to scroll panel content without triggering step changes.

   Panel hierarchy:
   - Layer 1: Freezes story navigation
   - Layer 2: Stacked on Layer 1
   - Glossary: Can open from any context

   Keyboard navigation:
   - ↑/↓: Step navigation (blocked when panel open)
   - ←: Close current panel
   - →: Open next panel level (L1 if none, L2 if L1 open)
   - Escape: Close current panel

   Scroll isolation zones:
   - Viewer column: Wheel events ignored (UV handles zoom/pan)
   - Narrative column: Normal step navigation
   - Open panels: Blocked by scrollLockActive flag

   Click outside: Closes topmost panel
   Backdrop: Subtle 2.5% dark overlay when panels open

   Based on initial work by Sanjana Bhupathi.
   ============================================================ */

/**
 * Handle keyboard navigation
 * PANEL FREEZE: ←/→ control panels, ↑/↓ control steps (blocked when panel open)
 */
function handleKeyboard(e) {
  switch(e.key) {
    case 'ArrowDown':
    case 'PageDown':
      e.preventDefault();
      if (!scrollLockActive) {
        nextStep();
      }
      break;

    case 'ArrowUp':
    case 'PageUp':
      e.preventDefault();
      if (!scrollLockActive) {
        prevStep();
      }
      break;

    case 'ArrowRight':
      e.preventDefault();
      if (!isPanelOpen) {
        // No panel open - try to open L1
        const stepForL1 = getCurrentStepData();
        const stepNumForL1 = getCurrentStepNumber();
        if (stepForL1 && stepHasLayer1Content(stepForL1)) {
          openPanel('layer1', stepNumForL1);
        }
      } else if (panelStack.length === 1 && panelStack[0]?.type === 'layer1') {
        // L1 is open - try to open L2
        const stepForL2 = getCurrentStepData();
        const stepNumForL2 = getCurrentStepNumber();
        if (stepForL2 && stepHasLayer2Content(stepForL2)) {
          openPanel('layer2', stepNumForL2);
        }
      }
      // If L2 or glossary is open, do nothing
      break;

    case 'ArrowLeft':
      e.preventDefault();
      if (isPanelOpen) {
        closeTopPanel();  // Close only the topmost panel
      }
      // If no panel open, do nothing
      break;

    case 'Escape':
      if (isPanelOpen) {
        e.preventDefault();
        closeTopPanel();
      }
      break;

    case ' ': // Space
      e.preventDefault();
      if (!scrollLockActive) {
        if (e.shiftKey) {
          prevStep();
        } else {
          nextStep();
        }
      }
      break;
  }
}

/**
 * Get current step number from the DOM element
 * Helper for keyboard panel navigation
 */
function getCurrentStepNumber() {
  if (currentStepIndex < 0 || currentStepIndex >= allSteps.length) {
    return null;
  }
  // Get step number from the step element's data attribute
  return allSteps[currentStepIndex].dataset.step;
}

/**
 * Get current step data from story data
 * Helper for keyboard panel navigation
 */
function getCurrentStepData() {
  const stepNumber = getCurrentStepNumber();
  if (!stepNumber) return null;
  const steps = window.storyData?.steps || [];
  return steps.find(s => s.step == stepNumber);
}

/**
 * Check if step has Layer 1 content
 */
function stepHasLayer1Content(step) {
  if (!step) return false;
  return (step.layer1_title && step.layer1_title.trim() !== '') ||
         (step.layer1_text && step.layer1_text.trim() !== '');
}

/**
 * Check if step has Layer 2 content
 */
function stepHasLayer2Content(step) {
  if (!step) return false;
  return (step.layer2_title && step.layer2_title.trim() !== '') ||
         (step.layer2_text && step.layer2_text.trim() !== '');
}

/**
 * Close only the topmost panel in the stack
 */
function closeTopPanel() {
  if (panelStack.length > 0) {
    const top = panelStack[panelStack.length - 1];
    closePanel(top.type);
    panelStack.pop();
  }
}

/**
 * Handle scroll accumulation with acceleration prevention
 */
function handleScroll(e) {
  // PANEL FREEZE: Skip scroll processing when any panel is open
  if (scrollLockActive) {
    scrollAccumulator = 0;  // Reset to prevent momentum buildup
    return;
  }

  // VIEWER SCROLL ISOLATION: Ignore wheel events from the viewer column
  // Users should be able to zoom/pan in the UV without triggering step changes
  if (e.target.closest('.viewer-column')) {
    return;
  }

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
 * Handle touch start for iPad/tablet swipe navigation (v0.4.3)
 *
 * Records the Y coordinate where the touch began. This coordinate is later
 * compared with the touch end position to determine swipe direction and distance.
 *
 * Context: The 'wheel' event works for mouse/trackpad but doesn't fire on iPad
 * when users scroll with touch. This touch handler enables natural swipe navigation
 * on touch devices in desktop viewport mode.
 *
 * @param {TouchEvent} e - Touch start event
 */
function handleTouchStart(e) {
  touchStartY = e.touches[0].clientY;
}

/**
 * Handle touch end for iPad/tablet swipe navigation (v0.4.3)
 *
 * Calculates swipe distance and direction to trigger step navigation:
 * - Swipe UP (like scrolling down) → advances to next step
 * - Swipe DOWN (like scrolling up) → returns to previous step
 *
 * Respects the same cooldown period as wheel scrolling to prevent rapid
 * step changes during animations. Requires minimum 20vh swipe distance
 * to distinguish intentional navigation from small touch movements.
 *
 * Note: Touch events are only active in desktop viewport mode. Mobile
 * viewports (<768px) use button-based navigation instead.
 *
 * Thanks to Makoto for revealing this issue on iPad.
 *
 * @param {TouchEvent} e - Touch end event
 */
function handleTouchEnd(e) {
  touchEndY = e.changedTouches[0].clientY;

  const now = Date.now();
  const timeSinceLastChange = now - lastStepChangeTime;

  // Respect cooldown period to prevent rapid step changes during animations
  if (timeSinceLastChange < STEP_COOLDOWN) {
    return;
  }

  // PANEL FREEZE: Skip swipe processing when any panel is open
  if (scrollLockActive) {
    return;
  }

  // Calculate swipe distance (positive = swipe down, negative = swipe up)
  const swipeDistance = touchEndY - touchStartY;

  // Swipe up (negative distance) = next step (mimics scroll down behavior)
  if (swipeDistance < -TOUCH_THRESHOLD) {
    nextStep();
  }
  // Swipe down (positive distance) = previous step (mimics scroll up behavior)
  else if (swipeDistance > TOUCH_THRESHOLD) {
    prevStep();
  }
}

/**
 * Preload viewers for upcoming steps
 * Enhanced preloading (v0.4.0) - more aggressive on desktop due to better resources
 */
function preloadUpcomingViewers(currentIndex) {
  const PRELOAD_AHEAD = 3; // Preload 3 steps forward (increased from 2)
  const PRELOAD_BEHIND = 2; // Preload 2 steps backward (increased from 1)

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

    console.log(`Preloading viewer for step ${nextIndex}: ${objectId}`);
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

    console.log(`Preloading previous viewer for step ${prevIndex}: ${objectId}`);
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

  // Show shimmer if viewer not ready yet (v0.6.2 - matches mobile behavior)
  if (!newViewerCard.isReady) {
    showViewerSkeletonState();
  }

  // Wait for viewer to be ready and positioned before sliding up BOTH cards together
  const startTime = Date.now();
  const MAX_WAIT_TIME = 5000; // 5 seconds max

  const slideUpWhenReady = () => {
    const elapsed = Date.now() - startTime;

    if (newViewerCard.isReady) {
      hideViewerSkeletonState();
      console.log(`Viewer ready, transitioning to ${objectId} (${direction})`);

      if (direction === 'forward') {
        // Going forward - activate text step
        if (stepElement) {
          stepElement.offsetHeight; // Force reflow
          requestAnimationFrame(() => {
            stepElement.classList.add('is-active');
          });
        }

        // Activate viewer card (matches mobile - simple class changes only)
        newViewerCard.element.classList.remove('card-below');
        newViewerCard.element.classList.add('card-active');
        newViewerCard.element.style.zIndex = newViewerCard.zIndex;
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

      // Update object credits badge
      updateObjectCredits(objectId);
    } else if (elapsed < MAX_WAIT_TIME) {
      console.log(`Viewer not ready yet, waiting... (${elapsed}ms elapsed)`);
      setTimeout(slideUpWhenReady, 100);
    } else {
      console.warn(`Viewer for ${objectId} failed to load after 5 seconds, transitioning anyway`);
      hideViewerSkeletonState();

      if (direction === 'forward') {
        // Activate text step and slide up viewer card anyway
        if (stepElement) {
          stepElement.offsetHeight; // Force reflow
          requestAnimationFrame(() => {
            stepElement.classList.add('is-active');
          });
        }

        // Show viewer anyway to prevent black screen
        newViewerCard.element.classList.remove('card-below');
        newViewerCard.element.classList.add('card-active');
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

      // Update object credits badge
      updateObjectCredits(objectId);
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

  console.log(`Animating viewer to position: x=${x}, y=${y}, zoom=${zoom} over 4 seconds`);

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
    // Use language string from Jekyll with fallback to English
    const stepTemplate = window.telarLang.stepNumber || "Step {{ number }}";
    infoElement.textContent = stepTemplate.replace("{{ number }}", stepNumber);
  }
}

/**
 * Initialize object credits badge
 */
function initializeCredits() {
  // Check config flag
  if (!window.telarConfig?.showObjectCredits) return;

  // Set up dismiss handler
  const dismissBtn = document.getElementById('object-credits-dismiss');
  if (dismissBtn) {
    dismissBtn.addEventListener('click', function() {
      const badge = document.getElementById('object-credits-badge');
      if (badge) badge.classList.add('d-none');
      creditsDismissed = true;
    });
  }
}

/**
 * Update object credits badge when object changes
 */
function updateObjectCredits(objectId) {
  if (!window.telarConfig?.showObjectCredits) return;
  if (creditsDismissed) return;

  const badge = document.getElementById('object-credits-badge');
  const textElement = document.getElementById('object-credits-text');

  if (!badge || !textElement) return;

  // Get credit from objects data
  const objectData = objectsIndex[objectId];
  const credit = objectData?.credit;

  if (credit && credit.trim()) {
    const prefix = window.telarLang?.creditPrefix || 'Credit:';
    textElement.textContent = `${prefix} ${credit}`;
    badge.classList.remove('d-none');
  } else {
    badge.classList.add('d-none');
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
    const titleElement = document.getElementById(`${panelId}-title`);
    const demoBadgeText = window.telarLang?.demoPanelBadge || 'Demo content';
    const demoBadge = content.demo ? `<span class="demo-badge-inline" style="margin-left: 0.5rem;">${demoBadgeText}</span>` : '';
    titleElement.innerHTML = content.title + demoBadge;
    const contentElement = document.getElementById(`${panelId}-content`);
    contentElement.innerHTML = content.html;

    // v0.4.0: Re-initialize glossary links in the dynamically loaded content
    // This enables the [[term_id]] inline glossary links to work in panel content
    if (window.Telar && window.Telar.initializeGlossaryLinks) {
      window.Telar.initializeGlossaryLinks(contentElement);
    }

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
      const buttonLabel = (step.layer2_button && step.layer2_button.trim() !== '') ? step.layer2_button : window.telarLang.goDeeper;
      html += `<p><button class="panel-trigger" data-panel="layer2" data-step="${contentId}">${buttonLabel} →</button></p>`;
    }

    return {
      title: step.layer1_title || 'Layer 1',
      html: html,
      demo: step.layer1_demo || false
    };
  } else if (panelType === 'layer2') {
    return {
      title: step.layer2_title || 'Layer 2',
      html: formatPanelContent({
        text: step.layer2_text,
        media: step.layer2_media
      }),
      demo: step.layer2_demo || false
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

  // Create the dark backdrop element (PANEL FREEZE SYSTEM)
  const backdrop = document.createElement('div');
  backdrop.id = 'panel-backdrop';
  backdrop.style.cssText = `
    position: fixed;
    inset: -50px;
    background: rgba(0, 0, 0, 0.025);
    z-index: 1040;
    display: none;
    pointer-events: none;
  `;
  document.body.appendChild(backdrop);

  // Click outside to close panels (PANEL FREEZE SYSTEM)
  const storyContainer = document.querySelector('.story-container');
  if (storyContainer) {
    storyContainer.addEventListener('click', function(e) {
      // Don't close if clicking on panel, panel triggers, or share button
      if (isPanelOpen &&
          !e.target.closest('.offcanvas') &&
          !e.target.closest('[data-panel]') &&
          !e.target.closest('.share-button')) {
        closeTopPanel();
      }
    });
  }

  // Note: Auto-close on scroll was removed in v0.6.0 (Panel Freeze System).
  // Panels are now truly modal - users must explicitly dismiss via X, Escape,
  // Left arrow, or click outside.
}

/**
 * Activate scroll lock
 * Prevents step changes while panel is open
 * Shows subtle dark backdrop behind panels
 * Locks native scroll on background elements
 */
function activateScrollLock() {
  scrollLockActive = true;
  const backdrop = document.getElementById('panel-backdrop');
  if (backdrop) {
    backdrop.style.display = 'block';
  }
  // Lock native scroll on narrative column to prevent background scrolling
  const narrativeColumn = document.querySelector('.narrative-column');
  if (narrativeColumn) {
    narrativeColumn.style.overflow = 'hidden';
  }
}

/**
 * Deactivate scroll lock
 * Allows step changes when panel is closed
 * Hides the dark backdrop
 * Restores native scroll on background elements
 */
function deactivateScrollLock() {
  scrollLockActive = false;
  const backdrop = document.getElementById('panel-backdrop');
  if (backdrop) {
    backdrop.style.display = 'none';
  }
  // Restore native scroll on narrative column
  const narrativeColumn = document.querySelector('.narrative-column');
  if (narrativeColumn) {
    narrativeColumn.style.overflow = '';
  }
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

// ============================================================================
// GRACEFUL PANEL TRANSITIONS ON MOBILE (v0.4.0)
//
// Helper functions for mobile story navigation coordination
// ============================================================================

/**
 * Show skeleton loading state on viewer
 * Displays subtle shimmer animation to indicate viewer initialization
 */
function showViewerSkeletonState() {
  const container = document.getElementById('viewer-cards-container');
  if (container) {
    container.classList.add('skeleton-loading');
  }
}

/**
 * Hide skeleton loading state on viewer
 * Removes shimmer animation when viewer is ready
 */
function hideViewerSkeletonState() {
  const container = document.getElementById('viewer-cards-container');
  if (container) {
    container.classList.remove('skeleton-loading');
  }
}

/**
 * Preload viewers for mobile navigation (MOBILE ONLY)
 * More aggressive than desktop: ±2 steps instead of ±1
 * Reduces loading delays during rapid navigation
 */
function preloadMobileViewers(currentIndex) {
  const MOBILE_PRELOAD_RANGE = 2;

  for (let offset = -MOBILE_PRELOAD_RANGE; offset <= MOBILE_PRELOAD_RANGE; offset++) {
    if (offset === 0) continue; // Skip current step

    const idx = currentIndex + offset;
    if (idx < 0 || idx >= allSteps.length) continue;

    const step = allSteps[idx];
    const objectId = step.dataset.object;
    if (!objectId) continue;

    // Skip if already loaded
    const exists = viewerCards.find(vc => vc.objectId === objectId);
    if (exists) continue;

    // Preload this viewer
    const x = parseFloat(step.dataset.x);
    const y = parseFloat(step.dataset.y);
    const zoom = parseFloat(step.dataset.zoom);

    console.log(`Mobile preloading step ${idx}: ${objectId}`);
    getOrCreateViewerCard(objectId, idx, x, y, zoom);
  }
}

// Export for debugging
window.TelarStory = {
  viewerCards,
  currentViewerCard,
  switchToObject,
  animateViewerToPosition,
  openPanel,
  getManifestUrl,
  closeAllPanels,
  createViewerCard,
  getOrCreateViewerCard
};
