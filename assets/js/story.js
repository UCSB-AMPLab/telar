(() => {
  // assets/js/telar-story/state.js
  var STEP_COOLDOWN = 600;
  var MAX_SCROLL_DELTA = 200;
  var MOBILE_NAV_COOLDOWN = 400;
  var state = {
    // ── Navigation ───────────────────────────────────────────────────────────
    /** @type {HTMLElement[]} All .story-step elements in DOM order. */
    steps: [],
    /** Index of the current desktop step (-1 = none). */
    currentIndex: -1,
    /** Accumulated scroll distance (px) toward the next threshold. */
    scrollAccumulator: 0,
    /** Object ID currently displayed in the viewer. */
    currentObject: null,
    /** Timestamp (ms) of the last step change – used for cooldown. */
    lastStepChangeTime: 0,
    // ── Viewer cards ─────────────────────────────────────────────────────────
    /** The viewer card object currently visible on screen. */
    currentViewerCard: null,
    /** @type {ViewerCard[]} Pool of viewer card objects. */
    viewerCards: [],
    /** Counter for generating unique viewer instance DOM IDs. */
    viewerCardCounter: 0,
    /** Quick lookup: object_id → object data from window.objectsData. */
    objectsIndex: {},
    // ── Panels ───────────────────────────────────────────────────────────────
    /** @type {{ type: string, id: string }[]} Stack of open panels. */
    panelStack: [],
    /** Whether any panel is currently open. */
    isPanelOpen: false,
    /** Whether scroll-lock is active (blocks step navigation). */
    scrollLockActive: false,
    /** Whether the user dismissed the credits badge this session. */
    creditsDismissed: false,
    // ── Touch (iPad/tablet swipe navigation) ─────────────────────────────────
    /** Y coordinate where the current touch started. */
    touchStartY: 0,
    /** Y coordinate where the current touch ended. */
    touchEndY: 0,
    // ── Mobile / embed button navigation ─────────────────────────────────────
    /** Whether the viewport is below the mobile breakpoint (768 px). */
    isMobileViewport: false,
    /** Index of the current step in mobile/embed button mode. */
    currentMobileStep: 0,
    /** References to the prev/next button DOM elements. */
    mobileNavButtons: null,
    /** Whether mobile navigation is in its cooldown period. */
    mobileNavigationCooldown: false,
    // ── Connection speed ─────────────────────────────────────────────────────
    /** @type {number[]} Measured manifest fetch times (ms) for threshold tuning. */
    manifestLoadTimes: [],
    // ── Thresholds (computed in main.js from window.innerHeight) ─────────────
    /** Scroll distance (px) required to trigger a step change (50 vh). */
    scrollThreshold: 0,
    /** Swipe distance (px) required to trigger a step change (20 vh). */
    touchThreshold: 0,
    // ── Viewer preloading config (set from telarConfig in main.js) ───────────
    config: {
      /** Maximum UV instances kept in memory. */
      maxViewerCards: 10,
      /** Steps to preload ahead of the current position. */
      preloadSteps: 6,
      /** Show loading shimmer when story has >= this many unique viewers. */
      loadingThreshold: 5,
      /** Hide shimmer once this many viewers are ready. */
      minReadyViewers: 3
    }
  };

  // assets/js/telar-story/utils.js
  function getBasePath() {
    const pathParts = window.location.pathname.split("/").filter((p) => p);
    if (pathParts.length >= 2) {
      return "/" + pathParts.slice(0, -2).join("/");
    }
    return "";
  }
  function fixImageUrls(htmlContent, basePath) {
    const tempDiv = document.createElement("div");
    tempDiv.innerHTML = htmlContent;
    const images = tempDiv.querySelectorAll("img");
    images.forEach((img) => {
      const src = img.getAttribute("src");
      if (src && src.startsWith("/") && !src.startsWith("//")) {
        img.setAttribute("src", basePath + src);
      }
    });
    return tempDiv.innerHTML;
  }
  function calculateViewportPosition(viewport, x, y, zoom) {
    const homeZoom = viewport.getHomeZoom();
    const imageBounds = viewport.getHomeBounds();
    const point = {
      x: imageBounds.x + x * imageBounds.width,
      y: imageBounds.y + y * imageBounds.height
    };
    const actualZoom = homeZoom * zoom;
    return { point, actualZoom };
  }

  // assets/js/telar-story/viewer.js
  function buildObjectsIndex() {
    const objects = window.objectsData || [];
    objects.forEach((obj) => {
      state.objectsIndex[obj.object_id] = obj;
    });
  }
  function getManifestUrl(objectId) {
    const object = state.objectsIndex[objectId];
    if (!object) {
      console.warn("Object not found:", objectId);
      return buildLocalInfoJsonUrl(objectId);
    }
    const sourceUrl = object.source_url || object.iiif_manifest;
    if (sourceUrl && sourceUrl.trim() !== "") {
      return sourceUrl;
    }
    return buildLocalInfoJsonUrl(objectId);
  }
  function buildLocalInfoJsonUrl(objectId) {
    const basePath = getBasePath();
    const manifestUrl = `${window.location.origin}${basePath}/iiif/objects/${objectId}/manifest.json`;
    console.log("Building local IIIF manifest URL:", manifestUrl);
    return manifestUrl;
  }
  function createViewerCard(objectId, zIndex, x, y, zoom) {
    const container = document.getElementById("viewer-cards-container");
    const cardElement = document.createElement("div");
    cardElement.className = "viewer-card card-below";
    cardElement.style.zIndex = zIndex;
    cardElement.dataset.object = objectId;
    const viewerId = `viewer-instance-${state.viewerCardCounter}`;
    const viewerDiv = document.createElement("div");
    viewerDiv.className = "viewer-instance";
    viewerDiv.id = viewerId;
    cardElement.appendChild(viewerDiv);
    container.appendChild(cardElement);
    console.log(`Created viewer card for ${objectId} with z-index ${zIndex}, will snap to x=${x}, y=${y}, zoom=${zoom}`);
    const manifestUrl = getManifestUrl(objectId);
    if (!manifestUrl) {
      console.error("Could not determine manifest URL for:", objectId);
      return null;
    }
    const urlAdaptor = new UV.IIIFURLAdaptor();
    const data = urlAdaptor.getInitialData({
      manifest: manifestUrl,
      embedded: true
    });
    const uvInstance = UV.init(viewerId, data);
    urlAdaptor.bindTo(uvInstance);
    const viewerCard = {
      objectId,
      element: cardElement,
      uvInstance,
      osdViewer: null,
      isReady: false,
      pendingZoom: !isNaN(x) && !isNaN(y) && !isNaN(zoom) ? { x, y, zoom, snap: true } : null,
      zIndex
    };
    uvInstance.on("created", function() {
      let pollCount = 0;
      const MAX_POLLS = 50;
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
          setTimeout(() => {
            const leftPanel = cardElement.querySelector(".leftPanel");
            if (leftPanel) {
              leftPanel.style.display = "none";
              leftPanel.style.visibility = "hidden";
            }
          }, 100);
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
    if (state.viewerCards.length > state.config.maxViewerCards) {
      const oldest = state.viewerCards.shift();
      destroyViewerCard(oldest);
    }
    return viewerCard;
  }
  function getOrCreateViewerCard(objectId, zIndex, x, y, zoom) {
    console.log(`getOrCreateViewerCard called for ${objectId}`);
    console.log(`Current viewerCards: ${state.viewerCards.map((vc) => vc.objectId).join(", ")}`);
    const existing = state.viewerCards.find((vc) => vc.objectId === objectId);
    if (existing) {
      console.log(`Reusing existing viewer card for ${objectId}`);
      existing.element.style.zIndex = zIndex;
      existing.zIndex = zIndex;
      console.log(`Resetting viewer card state for ${objectId}`);
      existing.element.classList.remove("card-below");
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
  function destroyViewerCard(viewerCard) {
    console.log(`Destroying viewer card for ${viewerCard.objectId}`);
    if (viewerCard.element && viewerCard.element.parentNode) {
      viewerCard.element.parentNode.removeChild(viewerCard.element);
    }
    viewerCard.uvInstance = null;
    viewerCard.osdViewer = null;
  }
  function initializeFirstViewer() {
    const firstObjectId = window.storyData?.firstObject;
    if (!firstObjectId) {
      console.error("No first object specified in story data");
      return;
    }
    console.log("Initializing first viewer for object:", firstObjectId);
    const steps = window.storyData?.steps || [];
    const firstRealStep = steps.find((step) => step.object === firstObjectId);
    const x = firstRealStep ? parseFloat(firstRealStep.x) : void 0;
    const y = firstRealStep ? parseFloat(firstRealStep.y) : void 0;
    const zoom = firstRealStep ? parseFloat(firstRealStep.zoom) : void 0;
    const viewerCard = createViewerCard(firstObjectId, 1, x, y, zoom);
    if (viewerCard) {
      state.currentViewerCard = viewerCard;
      viewerCard.element.classList.remove("card-below");
      viewerCard.element.classList.add("card-active");
      updateObjectCredits(firstObjectId);
    }
  }
  function animateViewerToPosition(viewerCard, x, y, zoom) {
    if (!viewerCard || !viewerCard.osdViewer) {
      console.warn("Viewer card or OpenSeadragon viewer not ready for animation");
      return;
    }
    console.log(`Animating viewer to position: x=${x}, y=${y}, zoom=${zoom} over 4 seconds`);
    const osdViewer = viewerCard.osdViewer;
    const viewport = osdViewer.viewport;
    const { point, actualZoom } = calculateViewportPosition(viewport, x, y, zoom);
    console.log(`OSD coordinates - point: ${point.x}, ${point.y}, zoom: ${actualZoom}, homeZoom: ${viewport.getHomeZoom()}`);
    osdViewer.gestureSettingsMouse.clickToZoom = false;
    osdViewer.gestureSettingsTouch.clickToZoom = false;
    const originalAnimationTime = osdViewer.animationTime;
    const originalSpringStiffness = osdViewer.springStiffness;
    osdViewer.animationTime = 4;
    osdViewer.springStiffness = 0.8;
    console.log(`Set animation time to ${osdViewer.animationTime}s, spring stiffness to ${osdViewer.springStiffness}`);
    viewport.panTo(point, false);
    viewport.zoomTo(actualZoom, point, false);
    setTimeout(() => {
      osdViewer.animationTime = originalAnimationTime;
      osdViewer.springStiffness = originalSpringStiffness;
    }, 4100);
  }
  function snapViewerToPosition(viewerCard, x, y, zoom) {
    if (!viewerCard || !viewerCard.osdViewer) {
      console.warn("Viewer card or OpenSeadragon viewer not ready for snap");
      return;
    }
    const osdViewer = viewerCard.osdViewer;
    const viewport = osdViewer.viewport;
    const { point, actualZoom } = calculateViewportPosition(viewport, x, y, zoom);
    console.log(`Snapping to position immediately: x=${x}, y=${y}, zoom=${zoom}`);
    viewport.panTo(point, true);
    viewport.zoomTo(actualZoom, point, true);
  }
  function activateViewerCard(newViewerCard, objectId, options = {}) {
    const { onReady } = options;
    if (!newViewerCard.isReady) {
      showViewerSkeletonState();
    }
    const startTime = Date.now();
    const MAX_WAIT_TIME = 5e3;
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
        if (state.currentViewerCard && state.currentViewerCard !== newViewerCard) {
          state.currentViewerCard.element.classList.remove("card-active");
          state.currentViewerCard.element.classList.add("card-below");
        }
        newViewerCard.element.classList.remove("card-below");
        newViewerCard.element.classList.add("card-active");
        state.currentViewerCard = newViewerCard;
        updateObjectCredits(objectId);
      } else {
        console.log(`Viewer not ready yet, waiting... (${elapsed}ms elapsed)`);
        setTimeout(checkReady, 100);
      }
    };
    checkReady();
  }
  function switchToObject(objectId, stepNumber, x, y, zoom, stepElement, direction = "forward") {
    console.log(`Switching to object: ${objectId} at step ${stepNumber} with position x=${x}, y=${y}, zoom=${zoom} (${direction})`);
    const newViewerCard = getOrCreateViewerCard(objectId, stepNumber, x, y, zoom);
    activateViewerCard(newViewerCard, objectId, {
      onReady: (card) => {
        if (direction === "forward") {
          if (stepElement) {
            stepElement.offsetHeight;
            requestAnimationFrame(() => {
              stepElement.classList.add("is-active");
            });
          }
          card.element.style.zIndex = card.zIndex;
        }
      }
    });
  }
  function switchToObjectMobile(objectId, stepNumber, x, y, zoom) {
    console.log(`Mobile: Switching to object ${objectId} at step ${stepNumber}`);
    const newViewerCard = getOrCreateViewerCard(objectId, stepNumber, x, y, zoom);
    activateViewerCard(newViewerCard, objectId);
  }
  async function prefetchStoryManifests() {
    const objectIds = [...new Set(
      Array.from(document.querySelectorAll("[data-object]")).map((el) => el.dataset.object).filter(Boolean)
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
      } catch (e) {
      }
    }));
    adjustThresholdsForConnection();
  }
  function adjustThresholdsForConnection() {
    if (state.manifestLoadTimes.length < 2) return;
    const avgTime = state.manifestLoadTimes.reduce((a, b) => a + b, 0) / state.manifestLoadTimes.length;
    if (avgTime > 1e3) {
      state.config.loadingThreshold = 1;
      state.config.minReadyViewers = Math.min(6, state.config.preloadSteps);
      console.log(`Slow connection detected (${Math.round(avgTime)}ms avg), adjusting thresholds`);
    } else if (avgTime > 500) {
      state.config.loadingThreshold = Math.max(3, state.config.loadingThreshold - 2);
      state.config.minReadyViewers = Math.min(state.config.minReadyViewers + 1, state.config.preloadSteps);
      console.log(`Moderate connection detected (${Math.round(avgTime)}ms avg), adjusting thresholds`);
    }
  }
  function initializeLoadingShimmer() {
    const uniqueViewers = new Set(
      state.steps.map((step) => step.dataset.object).filter(Boolean)
    ).size;
    console.log(`Story has ${uniqueViewers} unique viewers (threshold: ${state.config.loadingThreshold})`);
    if (uniqueViewers >= state.config.loadingThreshold) {
      showViewerSkeletonState();
      console.log(`Showing initial load shimmer (${uniqueViewers} >= ${state.config.loadingThreshold})`);
      const checkReadyViewers = () => {
        const readyCount = state.viewerCards.filter((v) => v.isReady).length;
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
  function preloadNearbyViewers(currentIndex, ahead, behind) {
    for (let offset = -behind; offset <= ahead; offset++) {
      if (offset === 0) continue;
      const idx = currentIndex + offset;
      if (idx < 0 || idx >= state.steps.length) continue;
      const step = state.steps[idx];
      const objectId = step.dataset.object;
      if (!objectId) continue;
      if (state.viewerCards.find((vc) => vc.objectId === objectId)) continue;
      const x = parseFloat(step.dataset.x);
      const y = parseFloat(step.dataset.y);
      const zoom = parseFloat(step.dataset.zoom);
      console.log(`Preloading viewer for step ${idx}: ${objectId}`);
      getOrCreateViewerCard(objectId, idx, x, y, zoom);
    }
  }
  function showViewerSkeletonState() {
    const container = document.getElementById("viewer-cards-container");
    if (container) {
      container.classList.add("skeleton-loading");
    }
  }
  function hideViewerSkeletonState() {
    const container = document.getElementById("viewer-cards-container");
    if (container) {
      container.classList.remove("skeleton-loading");
    }
  }
  function initializeCredits() {
    if (!window.telarConfig?.showObjectCredits) return;
    const dismissBtn = document.getElementById("object-credits-dismiss");
    if (dismissBtn) {
      dismissBtn.addEventListener("click", function() {
        const badge = document.getElementById("object-credits-badge");
        if (badge) badge.classList.add("d-none");
        state.creditsDismissed = true;
      });
    }
  }
  function updateObjectCredits(objectId) {
    if (!window.telarConfig?.showObjectCredits) return;
    if (state.creditsDismissed) return;
    const badge = document.getElementById("object-credits-badge");
    const textElement = document.getElementById("object-credits-text");
    if (!badge || !textElement) return;
    const objectData = state.objectsIndex[objectId];
    const credit = objectData?.credit;
    if (credit && credit.trim()) {
      const prefix = window.telarLang?.creditPrefix || "Credit:";
      textElement.textContent = `${prefix} ${credit}`;
      badge.classList.remove("d-none");
    } else {
      badge.classList.add("d-none");
    }
  }

  // assets/js/telar-story/panels.js
  function initializePanels() {
    document.querySelectorAll('[data-panel="layer1"]').forEach((trigger) => {
      trigger.addEventListener("click", function() {
        const stepNumber = this.dataset.step;
        state.panelStack = [];
        openPanel("layer1", stepNumber);
      });
    });
    document.addEventListener("click", function(e) {
      if (e.target.matches('[data-panel="layer2"]')) {
        const stepNumber = e.target.dataset.step;
        openPanel("layer2", stepNumber);
      }
    });
    const layer1Back = document.getElementById("panel-layer1-back");
    if (layer1Back) {
      layer1Back.addEventListener("click", function() {
        closePanel("layer1");
      });
    }
    const layer2Back = document.getElementById("panel-layer2-back");
    if (layer2Back) {
      layer2Back.addEventListener("click", function() {
        closePanel("layer2");
      });
    }
    const glossaryBack = document.getElementById("panel-glossary-back");
    if (glossaryBack) {
      glossaryBack.addEventListener("click", function() {
        closePanel("glossary");
      });
    }
  }
  function openPanel(panelType, contentId) {
    const panelId = `panel-${panelType}`;
    const panel = document.getElementById(panelId);
    if (!panel) return;
    const content = getPanelContent(panelType, contentId);
    if (content) {
      const titleElement = document.getElementById(`${panelId}-title`);
      const demoBadgeText = window.telarLang?.demoPanelBadge || "Demo content";
      const demoBadge = content.demo ? `<span class="demo-badge-inline" style="margin-left: 0.5rem;">${demoBadgeText}</span>` : "";
      titleElement.innerHTML = content.title + demoBadge;
      const contentElement = document.getElementById(`${panelId}-content`);
      contentElement.innerHTML = content.html;
      if (window.Telar && window.Telar.initializeGlossaryLinks) {
        window.Telar.initializeGlossaryLinks(contentElement);
      }
      if (panelType === "layer1") {
        state.panelStack = [{ type: panelType, id: contentId }];
      } else {
        state.panelStack.push({ type: panelType, id: contentId });
      }
      const bsOffcanvas = new bootstrap.Offcanvas(panel);
      bsOffcanvas.show();
      state.isPanelOpen = true;
      activateScrollLock();
    }
  }
  function closePanel(panelType) {
    const panelId = `panel-${panelType}`;
    const panel = document.getElementById(panelId);
    if (!panel) return;
    const bsOffcanvas = bootstrap.Offcanvas.getInstance(panel);
    if (bsOffcanvas) {
      bsOffcanvas.hide();
    }
    setTimeout(() => {
      const anyPanelOpen = document.querySelector(".offcanvas.show");
      if (!anyPanelOpen) {
        state.isPanelOpen = false;
        deactivateScrollLock();
      }
    }, 350);
  }
  function closeTopPanel() {
    if (state.panelStack.length > 0) {
      const top = state.panelStack[state.panelStack.length - 1];
      closePanel(top.type);
      state.panelStack.pop();
    }
  }
  function closeAllPanels() {
    const openPanels = document.querySelectorAll(".offcanvas.show");
    openPanels.forEach((panel) => {
      const bsOffcanvas = bootstrap.Offcanvas.getInstance(panel);
      if (bsOffcanvas) {
        bsOffcanvas.hide();
      }
    });
    state.isPanelOpen = false;
    deactivateScrollLock();
  }
  function getPanelContent(panelType, contentId) {
    const steps = window.storyData?.steps || [];
    const step = steps.find((s) => s.step == contentId);
    if (!step) return null;
    if (panelType === "layer1") {
      let html = formatPanelContent({
        text: step.layer1_text,
        media: step.layer1_media
      });
      if (step.layer2_title && step.layer2_title.trim() !== "" || step.layer2_text && step.layer2_text.trim() !== "") {
        const buttonLabel = step.layer2_button && step.layer2_button.trim() !== "" ? step.layer2_button : window.telarLang.goDeeper;
        html += `<p><button class="panel-trigger" data-panel="layer2" data-step="${contentId}">${buttonLabel} \u2192</button></p>`;
      }
      return {
        title: step.layer1_title || step.layer1_button || "Layer 1",
        html,
        demo: step.layer1_demo || false
      };
    } else if (panelType === "layer2") {
      return {
        title: step.layer2_title || step.layer2_button || "Layer 2",
        html: formatPanelContent({
          text: step.layer2_text,
          media: step.layer2_media
        }),
        demo: step.layer2_demo || false
      };
    } else if (panelType === "glossary") {
      return {
        title: "Glossary Term",
        html: "<p>Glossary content...</p>"
      };
    }
    return null;
  }
  function formatPanelContent(panelData) {
    if (!panelData) return "<p>No content available.</p>";
    let html = "";
    const basePath = getBasePath();
    if (panelData.text) {
      html += fixImageUrls(panelData.text, basePath);
    }
    if (panelData.media && panelData.media.trim() !== "") {
      let mediaUrl = panelData.media;
      if (mediaUrl.startsWith("/") && !mediaUrl.startsWith("//")) {
        mediaUrl = basePath + mediaUrl;
      }
      html += `<img src="${mediaUrl}" alt="Panel image" class="img-fluid">`;
    }
    return html;
  }
  function stepHasLayer1Content(step) {
    if (!step) return false;
    return step.layer1_title && step.layer1_title.trim() !== "" || step.layer1_text && step.layer1_text.trim() !== "";
  }
  function stepHasLayer2Content(step) {
    if (!step) return false;
    return step.layer2_title && step.layer2_title.trim() !== "" || step.layer2_text && step.layer2_text.trim() !== "";
  }
  function initializeScrollLock() {
    const narrativeColumn = document.querySelector(".narrative-column");
    if (!narrativeColumn) return;
    const backdrop = document.createElement("div");
    backdrop.id = "panel-backdrop";
    backdrop.style.cssText = `
    position: fixed;
    inset: -50px;
    background: rgba(0, 0, 0, 0.025);
    z-index: 1040;
    display: none;
    pointer-events: none;
  `;
    document.body.appendChild(backdrop);
    const storyContainer = document.querySelector(".story-container");
    if (storyContainer) {
      storyContainer.addEventListener("click", function(e) {
        if (state.isPanelOpen && !e.target.closest(".offcanvas") && !e.target.closest("[data-panel]") && !e.target.closest(".share-button")) {
          closeTopPanel();
        }
      });
    }
  }
  function activateScrollLock() {
    state.scrollLockActive = true;
    const backdrop = document.getElementById("panel-backdrop");
    if (backdrop) {
      backdrop.style.display = "block";
    }
    const narrativeColumn = document.querySelector(".narrative-column");
    if (narrativeColumn) {
      narrativeColumn.style.overflow = "hidden";
    }
  }
  function deactivateScrollLock() {
    state.scrollLockActive = false;
    const backdrop = document.getElementById("panel-backdrop");
    if (backdrop) {
      backdrop.style.display = "none";
    }
    const narrativeColumn = document.querySelector(".narrative-column");
    if (narrativeColumn) {
      narrativeColumn.style.overflow = "";
    }
  }

  // assets/js/telar-story/navigation.js
  function initializeStepController() {
    state.steps = Array.from(document.querySelectorAll(".story-step"));
    initializeLoadingShimmer();
    state.steps.forEach((step, index) => {
      step.style.zIndex = index + 1;
      step.dataset.stepIndex = index;
    });
    if (state.steps.length > 0) {
      goToStep(0, "forward");
    }
    document.addEventListener("keydown", handleKeyboard);
    window.addEventListener("wheel", handleScroll, { passive: false });
    window.addEventListener("touchstart", handleTouchStart, { passive: true });
    window.addEventListener("touchend", handleTouchEnd, { passive: true });
    console.log(`Step controller initialized with ${state.steps.length} steps`);
  }
  function goToStep(newIndex, direction = "forward") {
    if (newIndex < 0) {
      console.log(`Cannot go to step ${newIndex}: already at first step (0)`);
      return;
    }
    if (newIndex >= state.steps.length) {
      console.log(`Cannot go to step ${newIndex}: already at last step (${state.steps.length - 1})`);
      return;
    }
    const oldIndex = state.currentIndex;
    const newStep = state.steps[newIndex];
    const oldStep = oldIndex >= 0 ? state.steps[oldIndex] : null;
    console.log(`goToStep: ${oldIndex} \u2192 ${newIndex} (${direction})`);
    state.lastStepChangeTime = Date.now();
    if (oldIndex === 0 && newIndex > 0) {
      const intro = state.steps[0];
      if (intro.classList.contains("story-intro")) {
        intro.style.transform = "translateY(-100%)";
        intro.style.zIndex = "0";
      }
    } else if (newIndex === 0 && oldIndex > 0) {
      const intro = state.steps[0];
      if (intro.classList.contains("story-intro")) {
        intro.style.zIndex = "10000";
        intro.style.transform = "translateY(0)";
      }
      state.currentViewerCard = null;
      state.currentObject = null;
    }
    if (direction === "backward" && oldStep && oldIndex !== 0) {
      oldStep.classList.remove("is-active");
    }
    state.currentIndex = newIndex;
    const objectId = newStep.dataset.object;
    const x = parseFloat(newStep.dataset.x);
    const y = parseFloat(newStep.dataset.y);
    const zoom = parseFloat(newStep.dataset.zoom);
    const isLeavingIntro = oldIndex === 0 && newIndex > 0;
    if (objectId && (!state.currentViewerCard || state.currentViewerCard.objectId !== objectId || isLeavingIntro)) {
      console.log(`Switching to new object: ${objectId}${isLeavingIntro ? " (leaving intro)" : ""}`);
      switchToObject(objectId, newIndex, x, y, zoom, newStep, direction);
      state.currentObject = objectId;
    } else {
      console.log(`Same object, activating text and animating viewer`);
      if (direction === "forward" && state.currentViewerCard) {
        state.currentViewerCard.element.classList.remove("card-below");
        state.currentViewerCard.element.classList.add("card-active");
      }
      if (direction === "forward") {
        newStep.offsetHeight;
        requestAnimationFrame(() => {
          newStep.classList.add("is-active");
        });
      }
      if (state.currentViewerCard && !isNaN(x) && !isNaN(y) && !isNaN(zoom)) {
        if (state.currentViewerCard.isReady) {
          animateViewerToPosition(state.currentViewerCard, x, y, zoom);
        } else {
          console.warn("Viewer not ready, queueing zoom");
          state.currentViewerCard.pendingZoom = { x, y, zoom, snap: false };
        }
      }
    }
    updateViewerInfo(newIndex);
    preloadNearbyViewers(newIndex, 3, 2);
  }
  function nextStep() {
    goToStep(state.currentIndex + 1, "forward");
  }
  function prevStep() {
    goToStep(state.currentIndex - 1, "backward");
  }
  function createNavigationButtons() {
    if (document.querySelector(".mobile-nav")) {
      console.warn("Navigation buttons already exist, skipping creation");
      return null;
    }
    const navContainer = document.createElement("div");
    navContainer.className = "mobile-nav";
    const prevButton = document.createElement("button");
    prevButton.className = "mobile-prev";
    prevButton.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" height="32" viewBox="0 -960 960 960" width="32" fill="currentColor"><path d="M440-160v-487L216-423l-56-57 320-320 320 320-56 57-224-224v487h-80Z"/></svg>';
    prevButton.setAttribute("aria-label", "Previous step");
    const nextButton = document.createElement("button");
    nextButton.className = "mobile-next";
    nextButton.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" height="32" viewBox="0 -960 960 960" width="32" fill="currentColor"><path d="M440-800v487L216-537l-56 57 320 320 320-320-56-57-224 224v-487h-80Z"/></svg>';
    nextButton.setAttribute("aria-label", "Next step");
    navContainer.appendChild(prevButton);
    navContainer.appendChild(nextButton);
    document.body.appendChild(navContainer);
    return { container: navContainer, prev: prevButton, next: nextButton };
  }
  function initializeButtonNavigation(mode) {
    console.log(`Initializing ${mode} button navigation`);
    state.steps = Array.from(document.querySelectorAll(".story-step"));
    initializeLoadingShimmer();
    state.steps.forEach((step) => {
      step.classList.remove("mobile-active");
    });
    if (state.steps.length > 0) {
      state.steps[0].classList.add("mobile-active");
      state.currentMobileStep = 0;
    }
    const buttons = createNavigationButtons();
    if (!buttons) return;
    state.mobileNavButtons = { prev: buttons.prev, next: buttons.next };
    buttons.prev.addEventListener("click", goToPreviousMobileStep);
    buttons.next.addEventListener("click", goToNextMobileStep);
    updateMobileButtonStates();
    console.log(`${mode.charAt(0).toUpperCase() + mode.slice(1)} navigation initialized with ${state.steps.length} steps`);
  }
  function goToNextMobileStep() {
    if (state.currentMobileStep >= state.steps.length - 1) {
      console.log("Already at last step");
      return;
    }
    goToMobileStep(state.currentMobileStep + 1);
  }
  function goToPreviousMobileStep() {
    if (state.currentMobileStep <= 0) {
      console.log("Already at first step");
      return;
    }
    goToMobileStep(state.currentMobileStep - 1);
  }
  function goToMobileStep(newIndex) {
    if (newIndex < 0 || newIndex >= state.steps.length) {
      return;
    }
    if (state.mobileNavigationCooldown) {
      console.log("Mobile navigation on cooldown, ignoring tap");
      return;
    }
    const newStep = state.steps[newIndex];
    const objectId = newStep.dataset.object;
    const viewerCard = state.viewerCards.find((vc) => vc.objectId === objectId);
    if (!viewerCard || !viewerCard.isReady) {
      showViewerSkeletonState();
    }
    state.mobileNavigationCooldown = true;
    setTimeout(() => {
      state.mobileNavigationCooldown = false;
    }, MOBILE_NAV_COOLDOWN);
    console.log(`Mobile navigation: ${state.currentMobileStep} \u2192 ${newIndex}`);
    state.steps[state.currentMobileStep].classList.remove("mobile-active");
    state.steps[newIndex].classList.add("mobile-active");
    state.currentMobileStep = newIndex;
    updateMobileButtonStates();
    const x = parseFloat(newStep.dataset.x);
    const y = parseFloat(newStep.dataset.y);
    const zoom = parseFloat(newStep.dataset.zoom);
    if (objectId && (!state.currentViewerCard || state.currentViewerCard.objectId !== objectId)) {
      console.log(`Switching to object: ${objectId}`);
      switchToObjectMobile(objectId, newIndex, x, y, zoom);
      state.currentObject = objectId;
    } else if (state.currentViewerCard && !isNaN(x) && !isNaN(y) && !isNaN(zoom)) {
      if (state.currentViewerCard.isReady) {
        animateViewerToPosition(state.currentViewerCard, x, y, zoom);
      } else {
        state.currentViewerCard.pendingZoom = { x, y, zoom, snap: false };
      }
    }
    updateViewerInfo(newIndex);
    preloadNearbyViewers(newIndex, 2, 2);
  }
  function updateMobileButtonStates() {
    if (!state.mobileNavButtons) return;
    state.mobileNavButtons.prev.disabled = state.currentMobileStep === 0;
    state.mobileNavButtons.next.disabled = state.currentMobileStep === state.steps.length - 1;
  }
  function handleKeyboard(e) {
    switch (e.key) {
      case "ArrowDown":
      case "PageDown":
        e.preventDefault();
        if (!state.scrollLockActive) {
          nextStep();
        }
        break;
      case "ArrowUp":
      case "PageUp":
        e.preventDefault();
        if (!state.scrollLockActive) {
          prevStep();
        }
        break;
      case "ArrowRight":
        e.preventDefault();
        if (!state.isPanelOpen) {
          const stepForL1 = getCurrentStepData();
          const stepNumForL1 = getCurrentStepNumber();
          if (stepForL1 && stepHasLayer1Content(stepForL1)) {
            openPanel("layer1", stepNumForL1);
          }
        } else if (state.panelStack.length === 1 && state.panelStack[0]?.type === "layer1") {
          const stepForL2 = getCurrentStepData();
          const stepNumForL2 = getCurrentStepNumber();
          if (stepForL2 && stepHasLayer2Content(stepForL2)) {
            openPanel("layer2", stepNumForL2);
          }
        }
        break;
      case "ArrowLeft":
        e.preventDefault();
        if (state.isPanelOpen) {
          closeTopPanel();
        }
        break;
      case "Escape":
        if (state.isPanelOpen) {
          e.preventDefault();
          closeTopPanel();
        }
        break;
      case " ":
        e.preventDefault();
        if (!state.scrollLockActive) {
          if (e.shiftKey) {
            prevStep();
          } else {
            nextStep();
          }
        }
        break;
    }
  }
  function handleScroll(e) {
    if (state.scrollLockActive) {
      state.scrollAccumulator = 0;
      return;
    }
    if (e.target.closest(".viewer-column")) {
      return;
    }
    const now = Date.now();
    const timeSinceLastChange = now - state.lastStepChangeTime;
    if (timeSinceLastChange < STEP_COOLDOWN) {
      state.scrollAccumulator *= 0.5;
      return;
    }
    const cappedDelta = Math.max(-MAX_SCROLL_DELTA, Math.min(MAX_SCROLL_DELTA, e.deltaY));
    state.scrollAccumulator += cappedDelta;
    if (state.scrollAccumulator >= state.scrollThreshold) {
      nextStep();
      state.scrollAccumulator = 0;
    } else if (state.scrollAccumulator <= -state.scrollThreshold) {
      prevStep();
      state.scrollAccumulator = 0;
    }
  }
  function handleTouchStart(e) {
    state.touchStartY = e.touches[0].clientY;
  }
  function handleTouchEnd(e) {
    state.touchEndY = e.changedTouches[0].clientY;
    const now = Date.now();
    const timeSinceLastChange = now - state.lastStepChangeTime;
    if (timeSinceLastChange < STEP_COOLDOWN) {
      return;
    }
    if (state.scrollLockActive) {
      return;
    }
    const swipeDistance = state.touchEndY - state.touchStartY;
    if (swipeDistance < -state.touchThreshold) {
      nextStep();
    } else if (swipeDistance > state.touchThreshold) {
      prevStep();
    }
  }
  function getCurrentStepNumber() {
    if (state.currentIndex < 0 || state.currentIndex >= state.steps.length) {
      return null;
    }
    return state.steps[state.currentIndex].dataset.step;
  }
  function getCurrentStepData() {
    const stepNumber = getCurrentStepNumber();
    if (!stepNumber) return null;
    const steps = window.storyData?.steps || [];
    return steps.find((s) => s.step == stepNumber);
  }
  function updateViewerInfo(stepNumber) {
    const infoElement = document.getElementById("current-object-title");
    if (infoElement) {
      const stepTemplate = window.telarLang.stepNumber || "Step {{ number }}";
      infoElement.textContent = stepTemplate.replace("{{ number }}", stepNumber);
    }
  }

  // assets/js/telar-story/main.js
  document.addEventListener("DOMContentLoaded", function() {
    const viewerConfig = window.telarConfig?.viewer_preloading || {};
    state.config.maxViewerCards = Math.min(viewerConfig.max_viewer_cards || 10, 15);
    state.config.preloadSteps = Math.min(viewerConfig.preload_steps || 6, state.config.maxViewerCards - 2);
    state.config.loadingThreshold = viewerConfig.loading_threshold || 5;
    state.config.minReadyViewers = Math.min(viewerConfig.min_ready_viewers || 3, state.config.preloadSteps);
    state.scrollThreshold = window.innerHeight * 0.5;
    state.touchThreshold = window.innerHeight * 0.2;
    buildObjectsIndex();
    prefetchStoryManifests();
    initializeFirstViewer();
    state.isMobileViewport = window.innerWidth < 768;
    const isEmbedMode = window.telarEmbed?.enabled || false;
    if (isEmbedMode) {
      initializeButtonNavigation("embed");
    } else if (state.isMobileViewport) {
      initializeButtonNavigation("mobile");
    } else {
      initializeStepController();
    }
    initializePanels();
    initializeScrollLock();
    initializeCredits();
  });
  window.TelarStory = {
    state,
    switchToObject,
    animateViewerToPosition,
    openPanel,
    getManifestUrl,
    closeAllPanels,
    createViewerCard,
    getOrCreateViewerCard
  };
})();
