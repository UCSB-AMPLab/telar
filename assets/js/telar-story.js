(() => {
  // assets/js/telar-story/state.js
  var MOBILE_NAV_COOLDOWN = 400;
  var state = {
    // ── Navigation ───────────────────────────────────────────────────────────
    /** @type {HTMLElement[]} All .story-step elements in DOM order. */
    steps: [],
    /** Index of the current desktop step (-1 = none). */
    currentIndex: -1,
    /** Object ID currently displayed in the viewer. */
    currentObject: null,
    // ── Scroll engine ─────────────────────────────────────────────────────────
    /** Continuous float position (e.g. 2.3 = step 2, 30% progress). */
    scrollPosition: 0,
    /** Fractional progress within the current step (0.0–1.0). */
    scrollProgress: 0,
    /** Whether a snap animation is currently in flight. */
    isSnapping: false,
    /** Set true during scroll-driven activateCard calls so card-pool skips the 4s OSD animation. */
    scrollDriven: false,
    /** Lenis instance reference — used by panels.js to stop/start scroll. */
    lenis: null,
    /** Snap plugin instance reference. */
    snap: null,
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
    // ── Autoplay policy ──────────────────────────────────────────────────────
    /** Set true on first play overlay tap; enables autoplay for all subsequent media cards. */
    hasUserInteracted: false,
    // ── Mobile / embed button navigation ─────────────────────────────────────
    /** Whether the viewport is below the mobile breakpoint (768 px). */
    isMobileViewport: false,
    /** Index of the current step in mobile/embed button mode. */
    currentMobileStep: 0,
    /** Whether mobile navigation is showing the intro card (before step 0). */
    mobileInIntro: false,
    /** References to the prev/next button DOM elements. */
    mobileNavButtons: null,
    /** Whether mobile navigation is in its cooldown period. */
    mobileNavigationCooldown: false,
    // ── Connection speed ─────────────────────────────────────────────────────
    /** @type {number[]} Measured manifest fetch times (ms) for threshold tuning. */
    manifestLoadTimes: [],
    // ── Card pool ────────────────────────────────────────────────────────────
    /** @type {Object[]} Pool of active card instances. */
    cardPool: [],
    /** Map of sceneIndex -> viewer plate element (one plate per scene). */
    viewerPlates: {},
    /** Map of stepIndex -> text card element. */
    textCards: {},
    /** Current object run tracking (for peek stack positioning). */
    currentObjectRun: { objectId: null, runPosition: 0 },
    // ── Scene maps (populated at initCardPool time) ───────────────────────────
    /** Map of stepIndex -> sceneIndex. Populated by buildSceneMaps at init. */
    stepToScene: {},
    /** Map of sceneIndex -> objectId. */
    sceneToObject: {},
    /** Map of sceneIndex -> first stepIndex in that scene. */
    sceneFirstStep: {},
    /** Total number of scenes in the story. */
    totalScenes: 0,
    // ── Viewer preloading config (set from telarConfig in main.js) ───────────
    config: {
      /** Maximum Tify instances kept in memory (per-scene pool cap). */
      maxViewerCards: 8,
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
    const VIEWER_INSET = 0.98;
    const actualZoom = homeZoom * zoom * VIEWER_INSET;
    return { point, actualZoom };
  }

  // assets/js/telar-story/viewer.js
  function buildObjectsIndex() {
    const objects = window.objectsData || [];
    objects.forEach((obj) => {
      state.objectsIndex[obj.object_id] = obj;
    });
  }
  function getManifestUrl(objectId, page) {
    const object = state.objectsIndex[objectId];
    if (!object) {
      console.warn("Object not found:", objectId);
      return buildLocalInfoJsonUrl(objectId, page);
    }
    const sourceUrl = object.source_url || object.iiif_manifest;
    if (sourceUrl && sourceUrl.trim() !== "") {
      return sourceUrl;
    }
    return buildLocalInfoJsonUrl(objectId, page);
  }
  function buildLocalInfoJsonUrl(objectId, page) {
    const basePath = getBasePath();
    if (page) {
      const manifestUrl2 = `${window.location.origin}${basePath}/iiif/objects/${objectId}/page-${page}/manifest.json`;
      console.log("Building local IIIF page manifest URL:", manifestUrl2);
      return manifestUrl2;
    }
    const manifestUrl = `${window.location.origin}${basePath}/iiif/objects/${objectId}/manifest.json`;
    console.log("Building local IIIF manifest URL:", manifestUrl);
    return manifestUrl;
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

  // assets/js/telar-story/card-type.js
  var YOUTUBE_RE = /(?:youtube\.com\/(?:watch\?.*v=|embed\/|shorts\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/;
  var VIMEO_RE = /vimeo\.com\/(?:video\/)?(\d+)/;
  var GDRIVE_RE = /drive\.google\.com\/(?:file\/d\/|open\?id=)([A-Za-z0-9_-]+)/;
  var AUDIO_FILE_RE = /\.(mp3|ogg|m4a)$/i;
  function detectCardType(stepData) {
    if (stepData.cardType && stepData.cardType !== "") return stepData.cardType;
    if (!stepData.objectId || stepData.objectId === "") return "text-only";
    const sourceUrl = stepData.source_url || "";
    if (YOUTUBE_RE.test(sourceUrl)) return "youtube";
    if (VIMEO_RE.test(sourceUrl)) return "vimeo";
    if (GDRIVE_RE.test(sourceUrl)) return "google-drive";
    if (AUDIO_FILE_RE.test(stepData.file_path || "")) return "audio";
    return "iiif";
  }
  function extractVideoId(cardType, sourceUrl) {
    const regexMap = { youtube: YOUTUBE_RE, vimeo: VIMEO_RE, "google-drive": GDRIVE_RE };
    const match = (sourceUrl || "").match(regexMap[cardType]);
    return match ? match[1] : null;
  }

  // assets/js/telar-story/iiif-card.js
  function deactivateIiifCard(viewerCard, direction) {
    if (!viewerCard || !viewerCard.element) return;
    viewerCard.element.classList.remove("is-active");
    if (direction === "backward") {
      viewerCard.element.style.transform = "translateY(100%)";
    }
    console.log(`deactivateIiifCard: ${viewerCard.objectId} (${direction})`);
  }
  function _compensateForCardOverlay(viewport, point, actualZoom) {
    if (state.isMobileViewport) {
      const CARD_FRAC_MOBILE = 0.4;
      const viewportWidth2 = 1 / actualZoom;
      const aspectRatio = window.innerHeight / window.innerWidth;
      const viewportHeight = viewportWidth2 * aspectRatio;
      const shiftY = CARD_FRAC_MOBILE / 2 * viewportHeight;
      const visibleFraction = 1 - CARD_FRAC_MOBILE;
      return {
        point: { x: point.x, y: point.y + shiftY },
        actualZoom: actualZoom * visibleFraction
      };
    }
    const viewportWidth = 1 / actualZoom;
    const CARD_FRAC = 0.39;
    const shiftX = CARD_FRAC / 2 * viewportWidth;
    return {
      point: { x: point.x - shiftX, y: point.y },
      actualZoom
    };
  }
  function snapIiifToPosition(viewerCard, x, y, zoom) {
    if (!viewerCard || !viewerCard.osdViewer) {
      console.warn("snapIiifToPosition: viewer not ready for snap");
      return;
    }
    const osdViewer = viewerCard.osdViewer;
    const viewport = osdViewer.viewport;
    let { point, actualZoom } = calculateViewportPosition(viewport, x, y, zoom);
    ({ point, actualZoom } = _compensateForCardOverlay(viewport, point, actualZoom));
    console.log(`snapIiifToPosition: ${viewerCard.objectId} x=${x} y=${y} zoom=${zoom}`);
    viewport.panTo(point, true);
    viewport.zoomTo(actualZoom, point, true);
  }
  function animateIiifToPosition(viewerCard, x, y, zoom) {
    if (!viewerCard || !viewerCard.osdViewer) {
      console.warn("animateIiifToPosition: viewer not ready for animation");
      return;
    }
    const osdViewer = viewerCard.osdViewer;
    const viewport = osdViewer.viewport;
    let { point, actualZoom } = calculateViewportPosition(viewport, x, y, zoom);
    ({ point, actualZoom } = _compensateForCardOverlay(viewport, point, actualZoom));
    console.log(`animateIiifToPosition: ${viewerCard.objectId} x=${x} y=${y} zoom=${zoom} over 4s`);
    osdViewer.gestureSettingsMouse.clickToZoom = false;
    osdViewer.gestureSettingsTouch.clickToZoom = false;
    const originalAnimationTime = osdViewer.animationTime;
    const originalSpringStiffness = osdViewer.springStiffness;
    osdViewer.animationTime = 4;
    osdViewer.springStiffness = 0.8;
    viewport.panTo(point, false);
    viewport.zoomTo(actualZoom, point, false);
    setTimeout(() => {
      osdViewer.animationTime = originalAnimationTime;
      osdViewer.springStiffness = originalSpringStiffness;
    }, 4100);
  }
  function lerpIiifPosition(stepIndex, progress, stepsData) {
    if (progress < 1e-3) return;
    const stepA = stepsData[stepIndex];
    const stepB = stepsData[stepIndex + 1];
    if (!stepA || !stepB) return;
    const objectIdA = stepA.object || stepA.objectId || "";
    const objectIdB = stepB.object || stepB.objectId || "";
    if (objectIdA !== objectIdB) return;
    const xA = parseFloat(stepA.x), yA = parseFloat(stepA.y), zA = parseFloat(stepA.zoom);
    const xB = parseFloat(stepB.x), yB = parseFloat(stepB.y), zB = parseFloat(stepB.zoom);
    if (isNaN(xA) || isNaN(yA) || isNaN(zA)) return;
    if (isNaN(xB) || isNaN(yB) || isNaN(zB)) return;
    const x = xA + (xB - xA) * progress;
    const y = yA + (yB - yA) * progress;
    const zoom = zA + (zB - zA) * progress;
    const sceneIndex = state.stepToScene[stepIndex];
    if (sceneIndex === void 0 || sceneIndex < 0) return;
    const viewerCard = state.viewerCards.find((vc) => vc.sceneIndex === sceneIndex);
    if (!viewerCard || !viewerCard.isReady) return;
    snapIiifToPosition(viewerCard, x, y, zoom);
  }

  // assets/js/telar-story/text-card.js
  function isFullObjectMode(stepData) {
    const zoom = stepData.zoom;
    if (stepData.x === void 0 && stepData.y === void 0 && zoom === void 0) {
      return true;
    }
    if (zoom === void 0 || zoom === "" || zoom === null) return true;
    const zoomNum = parseFloat(zoom);
    if (isNaN(zoomNum) || zoomNum <= 1) return true;
    return false;
  }

  // assets/js/telar-story/video-card.js
  var _videoPlayers = [];
  var MAX_VIDEO_PLAYERS = 3;
  function loadYouTubeAPI() {
    if (window._ytApiPromise) return window._ytApiPromise;
    window._ytApiPromise = new Promise((resolve) => {
      if (window.YT && window.YT.Player) {
        resolve();
        return;
      }
      const script = document.createElement("script");
      script.src = "https://www.youtube.com/iframe_api";
      script.async = true;
      document.head.appendChild(script);
      const prev = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = function() {
        if (typeof prev === "function") prev();
        resolve();
      };
    });
    return window._ytApiPromise;
  }
  function loadVimeoAPI() {
    if (window._vimeoApiPromise) return window._vimeoApiPromise;
    window._vimeoApiPromise = new Promise((resolve, reject) => {
      if (window.Vimeo && window.Vimeo.Player) {
        resolve();
        return;
      }
      const script = document.createElement("script");
      script.src = "https://player.vimeo.com/api/player.js";
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Failed to load Vimeo Player API"));
      document.head.appendChild(script);
    });
    return window._vimeoApiPromise;
  }
  function computeVideoLayout(W, H, aspectRatio) {
    if (W < 768) {
      return _computeStackedLayout(W, H, aspectRatio);
    }
    const pad = Math.max(8, Math.round(Math.min(W, H) * 0.025));
    const cardFracSide = 0.35;
    const sideCardW = Math.round(W * cardFracSide);
    const sideVideoMaxW = W - sideCardW - pad * 3;
    const sideVideoMaxH = H - pad * 2;
    let sideVidW = sideVideoMaxW;
    let sideVidH = sideVidW / aspectRatio;
    if (sideVidH > sideVideoMaxH) {
      sideVidH = sideVideoMaxH;
      sideVidW = sideVidH * aspectRatio;
    }
    const sideVideoArea = sideVidW * sideVidH;
    const stackVideoMaxW = W - pad * 2;
    const stackVideoMaxH = H * 0.58;
    let stackVidW = stackVideoMaxW;
    let stackVidH = stackVidW / aspectRatio;
    if (stackVidH > stackVideoMaxH) {
      stackVidH = stackVideoMaxH;
      stackVidW = stackVidH * aspectRatio;
    }
    const stackVideoArea = stackVidW * stackVidH;
    if (sideVideoArea >= stackVideoArea) {
      return _buildSideBySideResult(W, H, pad, sideCardW, sideVidW, sideVidH);
    } else {
      return _buildStackedResult(W, H, pad, stackVidW, stackVidH);
    }
  }
  function _buildSideBySideResult(W, H, pad, sideCardW, sideVidW, sideVidH) {
    const vidW = Math.round(sideVidW);
    const vidH = Math.round(sideVidH);
    const vidLeft = sideCardW + pad * 2;
    const vidTop = Math.round((H - vidH) / 2);
    const cardW = sideCardW;
    const cardH = Math.round(H - pad * 2);
    const cardLeft = pad;
    const cardTop = pad;
    const cardPad = cardW > 300 ? 24 : cardW > 200 ? 16 : 10;
    return {
      mode: "side-by-side",
      video: { left: vidLeft, top: vidTop, width: vidW, height: vidH },
      card: { left: cardLeft, top: cardTop, width: cardW, height: cardH },
      padding: cardPad
    };
  }
  function _buildStackedResult(W, H, pad, stackVidW, stackVidH) {
    const vidW = Math.round(stackVidW);
    const vidH = Math.round(stackVidH);
    const vidLeft = Math.round((W - vidW) / 2);
    const vidTop = pad;
    const cardTop = vidTop + vidH + pad;
    const cardH = Math.max(60, H - cardTop - pad);
    const cardW = Math.round(W - pad * 2);
    const cardLeft = pad;
    const cardPad = cardH > 200 ? 22 : cardH > 120 ? 14 : 8;
    return {
      mode: "stacked",
      video: { left: vidLeft, top: vidTop, width: vidW, height: vidH },
      card: { left: cardLeft, top: cardTop, width: cardW, height: cardH },
      padding: cardPad
    };
  }
  function _computeStackedLayout(W, H, aspectRatio) {
    const pad = Math.max(8, Math.round(Math.min(W, H) * 0.025));
    const stackVideoMaxW = W - pad * 2;
    const stackVideoMaxH = H * 0.58;
    let stackVidW = stackVideoMaxW;
    let stackVidH = stackVidW / aspectRatio;
    if (stackVidH > stackVideoMaxH) {
      stackVidH = stackVideoMaxH;
      stackVidW = stackVidH * aspectRatio;
    }
    return _buildStackedResult(W, H, pad, stackVidW, stackVidH);
  }
  function buildYouTubeEmbedConfig(videoId, clipStart, clipEnd, loop) {
    return {
      videoId,
      playerVars: {
        start: clipStart || 0,
        autoplay: 0,
        mute: 0,
        // loop/playlist omitted — segment looping handled by rAF polling
        // (YouTube loop playerVar loops the whole video, not the clip)
        controls: 1,
        rel: 0,
        modestbranding: 1
      }
    };
  }
  function buildGDriveEmbedUrl(fileId) {
    return `https://drive.google.com/file/d/${fileId}/preview`;
  }
  function applyClipEndDim(plateEl) {
    let overlay = plateEl.querySelector(".clip-end-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "clip-end-overlay";
      plateEl.appendChild(overlay);
    }
    void overlay.offsetHeight;
    overlay.classList.add("visible");
  }
  function removeClipEndDim(plateEl) {
    const overlay = plateEl.querySelector(".clip-end-overlay");
    if (overlay) {
      overlay.classList.remove("visible");
    }
  }
  function createVideoPlayer(plateEl, cardType, videoId, options = {}) {
    const {
      clipStart = 0,
      clipEnd,
      loop = false,
      onPlay = () => {
      },
      onTimeUpdate = () => {
      },
      onEnded = () => {
      },
      onAutoplayBlocked = () => {
      },
      sceneIndex = 0,
      sourceUrl = ""
    } = options;
    let wrapper;
    if (cardType === "youtube") {
      wrapper = _createYouTubePlayer(plateEl, videoId, {
        clipStart,
        clipEnd,
        loop,
        onPlay,
        onTimeUpdate,
        onEnded,
        onAutoplayBlocked,
        sceneIndex
      });
    } else if (cardType === "vimeo") {
      wrapper = _createVimeoPlayer(plateEl, videoId, {
        clipStart,
        clipEnd,
        loop,
        onPlay,
        onTimeUpdate,
        onEnded,
        onAutoplayBlocked,
        sceneIndex,
        sourceUrl
      });
    } else if (cardType === "google-drive") {
      wrapper = _createGDriveEmbed(plateEl, videoId, sceneIndex);
    } else {
      console.error("createVideoPlayer: unknown cardType", cardType);
      return null;
    }
    _videoPlayers.push(wrapper);
    _enforcePoolLimit(sceneIndex);
    _applyVideoLayout(plateEl);
    return wrapper;
  }
  function destroyVideoPlayer(wrapper) {
    if (!wrapper) return;
    try {
      if (wrapper.type === "youtube" && wrapper.player) {
        if (wrapper._rafId) cancelAnimationFrame(wrapper._rafId);
        if (wrapper._autoplayTimeout) clearTimeout(wrapper._autoplayTimeout);
        wrapper.player.destroy();
      } else if (wrapper.type === "vimeo" && wrapper.player) {
        wrapper.player.destroy();
      } else if (wrapper.type === "google-drive") {
        const iframe = wrapper.element.querySelector("iframe.video-iframe");
        if (iframe) iframe.remove();
      }
    } catch (e) {
      console.warn("destroyVideoPlayer: error during destroy", e);
    }
    const idx = _videoPlayers.indexOf(wrapper);
    if (idx !== -1) _videoPlayers.splice(idx, 1);
  }
  function _showVideoPlayOverlay(plateEl) {
    const existing = plateEl.querySelector(".video-play-overlay");
    if (existing) {
      existing.style.display = "flex";
      return;
    }
    const overlayEl = document.createElement("div");
    overlayEl.className = "video-play-overlay";
    overlayEl.style.cssText = "position:absolute;inset:0;display:flex;align-items:center;justify-content:center;z-index:1;";
    const _vObjectsData = window.objectsData || [];
    const _vObj = _vObjectsData.find((o) => o.object_id === plateEl.dataset.object) || {};
    const _vAlt = _vObj.alt_text || _vObj.title || "video";
    const overlayBtn = document.createElement("button");
    overlayBtn.setAttribute("aria-label", `Play ${_vAlt}`);
    overlayBtn.type = "button";
    overlayBtn.style.cssText = "min-height:44px;padding:0.5rem 1.25rem;border-radius:20px;background:rgba(255,255,255,0.6);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);border:none;cursor:pointer;box-shadow:0 2px 12px rgba(0,0,0,0.2);display:flex;align-items:center;gap:8px;color:#333;font-family:var(--font-body);font-size:0.9rem;";
    overlayBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="var(--color-link)" xmlns="http://www.w3.org/2000/svg"><polygon points="5,3 19,12 5,21"/></svg><span>Play</span>';
    overlayEl.appendChild(overlayBtn);
    plateEl.appendChild(overlayEl);
    overlayBtn.addEventListener("click", () => {
      state.hasUserInteracted = true;
      overlayEl.style.display = "none";
      const wrapper = _getWrapperForPlate(plateEl);
      if (wrapper && wrapper.player) {
        try {
          if (wrapper.type === "youtube") {
            wrapper.player.playVideo();
          } else if (wrapper.type === "vimeo") {
            wrapper.player.play();
          }
        } catch (e) {
        }
      }
    });
  }
  function activateVideoCard(plateEl, sceneIndex) {
    plateEl.style.transform = "translateY(0)";
    plateEl.classList.add("is-active");
    _applyVideoLayout(plateEl);
    const isEmbed = document.body.classList.contains("embed-mode");
    if (state.isMobileViewport || isEmbed) {
      if (!state.hasUserInteracted) {
        _showVideoPlayOverlay(plateEl);
        return;
      }
    }
    const wrapper = _getWrapperForPlate(plateEl);
    if (wrapper) {
      try {
        if (wrapper.type === "youtube" && wrapper.player) {
          wrapper.player.playVideo();
        } else if (wrapper.type === "vimeo" && wrapper.player) {
          wrapper.player.play().catch(() => {
          });
        }
      } catch (e) {
      }
    }
  }
  function deactivateVideoCard(plateEl) {
    plateEl.classList.remove("is-active");
    const wrapper = _getWrapperForPlate(plateEl);
    if (!wrapper) return;
    try {
      if (wrapper.type === "youtube" && wrapper.player) {
        wrapper.player.pauseVideo();
      } else if (wrapper.type === "vimeo" && wrapper.player) {
        wrapper.player.pause();
      }
    } catch (e) {
    }
  }
  function updateVideoClip(plateEl, clipStart, clipEnd, loop) {
    const wrapper = _getWrapperForPlate(plateEl);
    if (!wrapper) return;
    if (wrapper.clipStart === clipStart && wrapper.clipEnd === clipEnd && wrapper.loop === loop) {
      return;
    }
    wrapper.clipStart = clipStart;
    wrapper.clipEnd = clipEnd;
    wrapper.loop = loop;
    plateEl.dataset.clipStart = String(clipStart);
    plateEl.dataset.clipEnd = String(clipEnd);
    plateEl.dataset.loop = String(loop);
    removeClipEndDim(plateEl);
    try {
      if (wrapper.type === "youtube" && wrapper.player) {
        wrapper.player.seekTo(clipStart || 0, true);
        if (!wrapper._rafId) {
          wrapper.player.playVideo();
        }
      } else if (wrapper.type === "vimeo" && wrapper.player) {
        wrapper.player.setCurrentTime(clipStart || 0.01).catch(() => {
        });
        wrapper.player.play().catch(() => {
        });
      }
    } catch (e) {
    }
  }
  function _createYouTubePlayer(plateEl, videoId, opts) {
    const { clipStart, clipEnd, loop, onPlay, onTimeUpdate, onEnded, onAutoplayBlocked, sceneIndex } = opts;
    const container = document.createElement("div");
    container.className = "video-iframe";
    plateEl.appendChild(container);
    const wrapper = {
      type: "youtube",
      element: plateEl,
      player: null,
      sceneIndex,
      clipStart,
      clipEnd,
      loop,
      _rafId: null,
      _autoplayTimeout: null,
      _playReceived: false,
      destroy() {
        destroyVideoPlayer(this);
      }
    };
    loadYouTubeAPI().then(() => {
      const cfg = buildYouTubeEmbedConfig(videoId, clipStart, clipEnd, loop);
      wrapper.player = new window.YT.Player(container, {
        videoId: cfg.videoId,
        playerVars: cfg.playerVars,
        events: {
          onReady: (event) => {
            wrapper._autoplayTimeout = setTimeout(() => {
              if (!wrapper._playReceived) {
                onAutoplayBlocked();
              }
            }, 2e3);
          },
          onStateChange: (event) => {
            if (event.data === window.YT.PlayerState.PLAYING) {
              wrapper._playReceived = true;
              if (wrapper._autoplayTimeout) {
                clearTimeout(wrapper._autoplayTimeout);
                wrapper._autoplayTimeout = null;
              }
              onPlay();
              if (wrapper.clipEnd) {
                _startYouTubePolling(wrapper, onTimeUpdate, onEnded);
              }
            } else if (event.data === window.YT.PlayerState.PAUSED || event.data === window.YT.PlayerState.ENDED) {
              if (wrapper._rafId) {
                cancelAnimationFrame(wrapper._rafId);
                wrapper._rafId = null;
              }
            }
          }
        }
      });
    });
    return wrapper;
  }
  function _startYouTubePolling(wrapper, onTimeUpdate, onEnded) {
    if (wrapper._rafId) cancelAnimationFrame(wrapper._rafId);
    function poll() {
      if (!wrapper.player) return;
      try {
        const currentTime = wrapper.player.getCurrentTime();
        const duration = wrapper.player.getDuration();
        onTimeUpdate(currentTime, duration);
        if (wrapper.clipEnd && currentTime >= wrapper.clipEnd) {
          if (wrapper.loop) {
            wrapper.player.seekTo(wrapper.clipStart || 0, true);
          } else {
            wrapper.player.pauseVideo();
            onEnded();
            return;
          }
        }
      } catch (e) {
        return;
      }
      wrapper._rafId = requestAnimationFrame(poll);
    }
    wrapper._rafId = requestAnimationFrame(poll);
  }
  function _createVimeoPlayer(plateEl, videoId, opts) {
    const { clipStart, clipEnd, loop, onPlay, onTimeUpdate, onEnded, onAutoplayBlocked, sceneIndex, sourceUrl } = opts;
    const container = document.createElement("div");
    container.className = "video-iframe";
    plateEl.appendChild(container);
    const wrapper = {
      type: "vimeo",
      element: plateEl,
      player: null,
      sceneIndex,
      clipStart,
      clipEnd,
      loop,
      destroy() {
        destroyVideoPlayer(this);
      }
    };
    loadVimeoAPI().then(() => {
      const playerOpts = {
        autoplay: false,
        loop: false,
        controls: true
      };
      const hashMatch = sourceUrl && sourceUrl.match(/vimeo\.com\/\d+\/([a-f0-9]+)/i);
      if (hashMatch) {
        playerOpts.url = `https://vimeo.com/${videoId}/${hashMatch[1]}`;
      } else {
        playerOpts.id = parseInt(videoId, 10) || videoId;
      }
      const vimeoPlayer = new window.Vimeo.Player(container, playerOpts);
      wrapper.player = vimeoPlayer;
      vimeoPlayer.ready().then(() => {
        return Promise.all([
          vimeoPlayer.getVideoWidth(),
          vimeoPlayer.getVideoHeight()
        ]).then(([w, h]) => {
          if (w && h) {
            plateEl.dataset.aspectRatio = String(w / h);
            _applyVideoLayout(plateEl);
          }
        });
      }).then(() => {
        if (clipStart) {
          vimeoPlayer.setCurrentTime(clipStart).catch(() => {
          });
        }
      });
      vimeoPlayer.on("play", () => {
        onPlay();
      });
      vimeoPlayer.on("timeupdate", ({ seconds, duration }) => {
        onTimeUpdate(seconds, duration);
        if (wrapper.clipEnd && seconds >= wrapper.clipEnd) {
          if (wrapper.loop) {
            vimeoPlayer.setCurrentTime(wrapper.clipStart || 0.01).catch(() => {
            });
          } else {
            vimeoPlayer.pause().catch(() => {
            });
            onEnded();
          }
        }
      });
      vimeoPlayer.play().catch((err) => {
        if (err && (err.name === "NotAllowedError" || err.name === "PasswordError")) {
          onAutoplayBlocked();
        }
      });
    }).catch((err) => {
      console.error("Failed to load Vimeo API:", err);
    });
    return wrapper;
  }
  function _createGDriveEmbed(plateEl, videoId, sceneIndex) {
    const iframe = document.createElement("iframe");
    iframe.className = "video-iframe";
    iframe.src = buildGDriveEmbedUrl(videoId);
    iframe.allow = "autoplay";
    iframe.allowFullscreen = true;
    iframe.style.cssText = "width:100%;height:100%;border:none;border-radius:4px";
    plateEl.appendChild(iframe);
    return {
      type: "google-drive",
      element: plateEl,
      player: null,
      sceneIndex,
      destroy() {
        destroyVideoPlayer(this);
      }
    };
  }
  function _enforcePoolLimit(currentScene) {
    while (_videoPlayers.length > MAX_VIDEO_PLAYERS) {
      let farthestIdx = 0;
      let maxDist = -1;
      for (let i = 0; i < _videoPlayers.length; i++) {
        const dist = Math.abs(_videoPlayers[i].sceneIndex - currentScene);
        if (dist > maxDist) {
          maxDist = dist;
          farthestIdx = i;
        }
      }
      const evicted = _videoPlayers.splice(farthestIdx, 1)[0];
      _evictPlayer(evicted);
    }
  }
  function _evictPlayer(wrapper) {
    try {
      if (wrapper.type === "youtube" && wrapper.player) {
        if (wrapper._rafId) cancelAnimationFrame(wrapper._rafId);
        if (wrapper._autoplayTimeout) clearTimeout(wrapper._autoplayTimeout);
        wrapper.player.destroy();
      } else if (wrapper.type === "vimeo" && wrapper.player) {
        wrapper.player.destroy();
      } else if (wrapper.type === "google-drive") {
        const iframe = wrapper.element.querySelector("iframe.video-iframe");
        if (iframe) iframe.remove();
      }
    } catch (e) {
      console.warn("_evictPlayer: error during evict", e);
    }
  }
  function _getWrapperForPlate(plateEl) {
    return _videoPlayers.find((w) => w.element === plateEl) || null;
  }
  function _applyVideoLayout(plateEl) {
    const W = window.innerWidth;
    const H = window.innerHeight;
    const aspectRatio = parseFloat(plateEl.dataset.aspectRatio) || 16 / 9;
    const layout = computeVideoLayout(W, H, aspectRatio);
    const videoEl = plateEl.querySelector(".video-iframe");
    if (videoEl) {
      videoEl.style.position = "absolute";
      videoEl.style.left = `${layout.video.left}px`;
      videoEl.style.top = `${layout.video.top}px`;
      videoEl.style.width = `${layout.video.width}px`;
      videoEl.style.height = `${layout.video.height}px`;
    }
  }
  var _resizeDebounceTimer = null;
  window.addEventListener("resize", () => {
    if (_resizeDebounceTimer) clearTimeout(_resizeDebounceTimer);
    _resizeDebounceTimer = setTimeout(() => {
      for (const wrapper of _videoPlayers) {
        if (wrapper.element && wrapper.element.classList.contains("is-active")) {
          _applyVideoLayout(wrapper.element);
        }
      }
    }, 100);
  });

  // assets/js/telar-story/audio-card.js
  var _audioPlayers = [];
  var MAX_AUDIO_PLAYERS = 3;
  var _sharedAudioContext = null;
  function loadWaveSurferAPI() {
    if (window._wsApiPromise) return window._wsApiPromise;
    window._wsApiPromise = new Promise((resolve, reject) => {
      if (window.WaveSurfer) {
        resolve();
        return;
      }
      const script = document.createElement("script");
      script.src = "https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.min.js";
      script.async = true;
      script.onload = () => {
        const rScript = document.createElement("script");
        rScript.src = "https://unpkg.com/wavesurfer.js@7/dist/plugins/regions.min.js";
        rScript.async = true;
        rScript.onload = () => resolve();
        rScript.onerror = () => reject(new Error("WaveSurfer Regions plugin failed to load"));
        document.head.appendChild(rScript);
      };
      script.onerror = () => reject(new Error("WaveSurfer failed to load"));
      document.head.appendChild(script);
    });
    return window._wsApiPromise;
  }
  function formatElapsedTime(seconds) {
    const total = Math.floor(seconds);
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  }
  function deriveThemeColors(accentHex, barHex = "#ffffff") {
    const r = parseInt(accentHex.slice(1, 3), 16);
    const g = parseInt(accentHex.slice(3, 5), 16);
    const b = parseInt(accentHex.slice(5, 7), 16);
    const bgR = Math.round(r * 0.7);
    const bgG = Math.round(g * 0.7);
    const bgB = Math.round(b * 0.7);
    const bR = parseInt(barHex.slice(1, 3), 16);
    const bG = parseInt(barHex.slice(3, 5), 16);
    const bB = parseInt(barHex.slice(5, 7), 16);
    const upR = Math.round(bgR * 0.75 + bR * 0.25);
    const upG = Math.round(bgG * 0.75 + bG * 0.25);
    const upB = Math.round(bgB * 0.75 + bB * 0.25);
    return {
      playedColor: barHex,
      // played bars: theme button text colour
      unplayedColor: `rgb(${upR}, ${upG}, ${upB})`,
      // unplayed bars: opaque blended tint
      backgroundColor: `rgb(${bgR}, ${bgG}, ${bgB})`,
      patternColor: "rgba(255, 255, 255, 0.12)",
      clipRegionColor: "rgba(255, 255, 255, 0.08)"
      // subtle clip region highlight
    };
  }
  function _buildPatternDataUri(fillColor) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 543 380"><path d="M542.955,145.508l-83.257,-0.001l13.365,45.375l-12.615,43.868l82.485,0l-0,10.507l-81.743,0l7.56,40.133l-7.582,38.235l81.765,1.125l-0,10.5l-82.485,0l12.742,44.25l-14.25,0l-13.875,-44.25l-12.375,0l0,44.25l-14.25,0l0,-44.25l-52.492,0l-6.75,44.25l-14.25,0l6.75,-44.25l-41.993,0l6.75,44.25l-14.25,0l-6.75,-44.25l-88.492,0l-0,44.25l-14.25,0l-0,-44.25l-59.993,0l0,44.25l-14.25,0l0,-44.25l-34.492,0l-0,44.25l-13.5,0l-0,-44.25l-70.478,0l0,-10.5l69.368,0l1.125,-1.125l-0,-78.375l-70.493,0l0,-10.5l69.368,0l0.375,-89.25l-69.743,0l0,-10.5l69.743,0l0.75,-79.5l-70.493,0l0,-10.5l69.368,0l1.162,-2.588l-0.037,-42.412l13.5,0l-0.038,42.412l1.163,2.588l33.367,0l0,-44.993l14.25,0.001l0,45l59.993,-0l-0,-45l14.25,-0l-0,45l88.492,-0l6.743,-45l14.25,-0l-6.75,45l41.992,-0l-6.742,-45l14.25,-0l6.75,45l52.492,-0l0,-45l14.25,-0l0.375,45l12.375,-0l13.493,-45l14.25,-0l-12.743,44.992l82.485,0l0,10.508l-81.742,-0l7.522,38.594l-8.272,40.905l82.507,0l0,10.5Zm-424.47,-90l-34.492,0.001l-0,79.499l34.492,0l0,-79.5Zm74.243,0.001l-59.993,-0l0,79.499l59.993,0l-0,-79.5Zm101.242,0.001l-86.992,-0l-0.75,79.499l86.992,0l-5.317,-38.625l6.067,-40.875Zm59.243,79.508l6.48,-40.23l-6.068,-38.565l-45.337,-0.622l-6.105,40.83l5.272,38.595l45.75,-0l0.008,-0.008Zm65.242,-79.507l-50.242,-0l5.842,38.632l-6.592,40.868l50.242,-0l0.75,-79.5Zm13.493,79.5l13.875,-0l9.135,-40.223l-8.385,-39.277l-13.875,-0l-0.75,79.5Zm-313.463,10.5l-34.492,-0l-0,89.25l34.492,-0l0,-89.25Zm14.25,-0l0,89.25l59.993,-0l-0,-89.25l-59.993,-0Zm162.728,89.25l6.375,-44.655l-6.503,-43.35l-1.005,-1.245l-88.117,-0l0.75,89.25l88.5,-0Zm55.5,-89.25l-41.243,-0l6.353,44.602l-6.353,44.648l41.993,-0l-7.418,-46.208l6.668,-43.042Zm66.742,-0l-52.492,-0l-6.593,43.132l7.343,46.118l52.492,-0l-0.75,-89.25Zm27.743,89.25l13.17,-44.61l-14.295,-44.64l-12.375,-0l1.125,89.25l12.375,-0Zm-326.963,10.5l-34.492,-0l-0,79.5l34.492,-0l0,-79.5Zm74.243,-0l-59.993,-0l0,79.5l59.993,-0l-0,-79.5Zm101.242,-0l-86.992,-0l-0,79.5l86.992,-0l-5.917,-40.043l5.917,-39.457Zm14.28,79.462l45.383,-0.66l6.24,-39.345l-6.615,-39.135l-44.97,-0.24l-5.79,39.42l5.745,39.96l0.007,0Zm110.205,-79.462l-50.242,-0l6.022,40.087l-6.022,39.413l50.242,-0l0,-79.5Zm14.243,79.5l13.875,-0l8.542,-40.05l-8.542,-39.45l-13.875,-0l-0,79.5Z" fill="${fillColor}" fill-rule="nonzero"/></svg>`;
    return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
  }
  var _icons = {
    play: '<path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/>',
    pause: '<rect x="14" y="3" width="5" height="18" rx="1"/><rect x="5" y="3" width="5" height="18" rx="1"/>',
    "rotate-ccw": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    "volume-2": '<path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><path d="M16 9a5 5 0 0 1 0 6"/><path d="M19.364 18.364a9 9 0 0 0 0-12.728"/>',
    "volume-x": '<path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><line x1="22" y1="9" x2="16" y2="15"/><line x1="16" y1="9" x2="22" y2="15"/>'
  };
  function _svg(name, size = 24) {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${_icons[name]}</svg>`;
  }
  function buildAudioControlsHTML() {
    return `<div class="audio-controls">
  <button class="audio-btn audio-btn-play" aria-label="Play" type="button">${_svg("play", 22)}</button>
  <button class="audio-btn audio-btn-restart" aria-label="Restart from beginning" type="button">${_svg("rotate-ccw", 20)}</button>
  <button class="audio-btn audio-btn-mute" aria-label="Mute audio" type="button">${_svg("volume-2", 20)}</button>
</div>`;
  }
  function getSharedAudioContext() {
    if (!_sharedAudioContext) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      _sharedAudioContext = new AudioContextClass();
    }
    return _sharedAudioContext;
  }
  function createAudioPlayer(plateEl, audioUrl, peaksUrl, options = {}) {
    const {
      clipStart = 0,
      clipEnd,
      loop = false,
      sceneIndex = 0,
      isEmbed = false,
      onPlay = () => {
      },
      onTimeUpdate = () => {
      },
      onEnded = () => {
      },
      onAutoplayBlocked = () => {
      },
      onError = () => {
      }
    } = options;
    const wrapper = {
      type: "audio",
      element: plateEl,
      ws: null,
      sceneIndex,
      clipStart,
      clipEnd,
      loop,
      isEmbed,
      _lastElapsedSecond: -1,
      destroy() {
        destroyAudioPlayer(this);
      }
    };
    _audioPlayers.push(wrapper);
    _enforceAudioPoolLimit(sceneIndex);
    loadWaveSurferAPI().then(() => {
      const peaksFetch = peaksUrl ? fetch(peaksUrl).then((r) => r.ok ? r.json() : null).catch(() => null) : Promise.resolve(null);
      peaksFetch.then((peaksData) => {
        const styles = getComputedStyle(document.documentElement);
        const accentColor = styles.getPropertyValue("--color-link").trim() || "#883C36";
        const barColor = styles.getPropertyValue("--color-button-text").trim() || "#ffffff";
        const colors = deriveThemeColors(accentColor, barColor);
        const patternUri = _buildPatternDataUri(colors.patternColor);
        plateEl.style.background = `${colors.backgroundColor} ${patternUri} repeat`;
        plateEl.style.backgroundSize = "20px auto";
        let waveContainer = plateEl.querySelector(".waveform-container");
        if (!waveContainer) {
          waveContainer = document.createElement("div");
          waveContainer.className = "waveform-container";
          waveContainer.setAttribute("aria-hidden", "true");
          plateEl.appendChild(waveContainer);
        }
        const regionsPlugin = window.WaveSurfer.Regions.create();
        const ws = window.WaveSurfer.create({
          container: waveContainer,
          url: audioUrl,
          peaks: peaksData ? peaksData.peaks : void 0,
          waveColor: colors.unplayedColor,
          progressColor: colors.playedColor,
          cursorWidth: 0,
          // hide cursor line — progress shown via bar colour change
          barWidth: 4,
          barGap: 5,
          barRadius: 5,
          height: Math.round(window.innerHeight * 0.35),
          interact: false,
          normalize: true,
          backend: "WebAudio",
          audioContext: getSharedAudioContext(),
          plugins: [regionsPlugin]
        });
        wrapper.ws = ws;
        wrapper._regionsPlugin = regionsPlugin;
        wrapper._colors = colors;
        if (plateEl.classList.contains("is-active")) {
          activateAudioCard(plateEl, wrapper.sceneIndex);
        }
        if (clipStart !== void 0 && clipEnd) {
          ws.on("ready", () => {
            regionsPlugin.addRegion({
              start: clipStart,
              end: clipEnd,
              color: colors.clipRegionColor,
              drag: false,
              resize: false
            });
          });
        }
        ws.on("timeupdate", (currentTime) => {
          const elapsedSecond = Math.floor(currentTime);
          if (elapsedSecond !== wrapper._lastElapsedSecond) {
            wrapper._lastElapsedSecond = elapsedSecond;
            onTimeUpdate(currentTime);
            const elapsedEl2 = plateEl.querySelector(".audio-elapsed");
            if (elapsedEl2)
              elapsedEl2.textContent = formatElapsedTime(currentTime);
          }
          if (wrapper.clipEnd && currentTime >= wrapper.clipEnd) {
            if (wrapper.loop) {
              ws.setTime(wrapper.clipStart || 0);
            } else {
              ws.pause();
              applyAudioClipEndDim(plateEl);
              onEnded();
            }
          }
        });
        ws.on("play", () => {
          onPlay();
          removeAudioClipEndDim(plateEl);
          const playBtn = plateEl.querySelector(".audio-btn-play");
          if (playBtn) {
            playBtn.innerHTML = _svg("pause", 22);
            playBtn.setAttribute("aria-label", "Pause");
          }
          const overlay = plateEl.querySelector(".audio-play-overlay");
          if (overlay) overlay.style.display = "none";
        });
        ws.on("pause", () => {
          const playBtn = plateEl.querySelector(".audio-btn-play");
          if (playBtn) {
            playBtn.innerHTML = _svg("play", 22);
            playBtn.setAttribute("aria-label", "Play");
          }
        });
        ws.on("finish", () => {
          if (!wrapper.clipEnd) {
            applyAudioClipEndDim(plateEl);
            onEnded();
          }
        });
        ws.on("error", (err) => {
          console.error("audio-card: WaveSurfer error", err);
          _injectAudioError(plateEl);
          onError(err);
        });
        let elapsedEl = plateEl.querySelector(".audio-elapsed");
        if (!elapsedEl) {
          elapsedEl = document.createElement("div");
          elapsedEl.className = "audio-elapsed";
          elapsedEl.setAttribute("aria-live", "polite");
          elapsedEl.textContent = "0:00";
          elapsedEl.style.cssText = "position:absolute;font-size:0.8rem;color:rgba(0,0,0,0.7);background:rgba(255,255,255,0.6);backdrop-filter:blur(4px);border-radius:20px;padding:0.4rem 0.85rem;pointer-events:none;right:16px;bottom:calc(25% - 48px);z-index:1;";
          plateEl.appendChild(elapsedEl);
        }
        if (!plateEl.querySelector(".audio-controls")) {
          const controlsWrapper = document.createElement("div");
          controlsWrapper.innerHTML = buildAudioControlsHTML();
          const controlsEl = controlsWrapper.firstElementChild;
          plateEl.appendChild(controlsEl);
          const playBtn = controlsEl.querySelector(".audio-btn-play");
          if (playBtn) {
            playBtn.addEventListener("click", () => {
              state.hasUserInteracted = true;
              ws.playPause();
            });
          }
          const restartBtn = controlsEl.querySelector(".audio-btn-restart");
          if (restartBtn) {
            restartBtn.addEventListener("click", () => {
              ws.setTime(wrapper.clipStart || 0);
              ws.play();
              removeAudioClipEndDim(plateEl);
            });
          }
          const muteBtn = controlsEl.querySelector(".audio-btn-mute");
          if (muteBtn) {
            muteBtn.addEventListener("click", () => {
              const nowMuted = !ws.getMuted();
              ws.setMuted(nowMuted);
              if (nowMuted) {
                muteBtn.innerHTML = _svg("volume-x", 20);
                muteBtn.setAttribute("aria-label", "Unmute audio");
              } else {
                muteBtn.innerHTML = _svg("volume-2", 20);
                muteBtn.setAttribute("aria-label", "Mute audio");
              }
            });
          }
        }
        if (!plateEl.querySelector(".audio-play-overlay")) {
          const overlayEl = document.createElement("div");
          overlayEl.className = "audio-play-overlay";
          overlayEl.style.cssText = "position:absolute;inset:0;display:none;align-items:center;justify-content:center;z-index:1;";
          const _aObjectsData = window.objectsData || [];
          const _aObj = _aObjectsData.find((o) => o.object_id === plateEl?.dataset?.object) || {};
          const _aAlt = _aObj.alt_text || _aObj.title || "audio";
          const overlayBtn = document.createElement("button");
          overlayBtn.setAttribute("aria-label", `Play ${_aAlt}`);
          overlayBtn.type = "button";
          overlayBtn.innerHTML = _svg("play", 36);
          overlayBtn.style.cssText = "width:80px;height:80px;border-radius:50%;background:rgba(255,255,255,0.9);border:none;cursor:pointer;box-shadow:0 2px 12px rgba(0,0,0,0.2);display:flex;align-items:center;justify-content:center;color:#333;";
          overlayEl.appendChild(overlayBtn);
          plateEl.appendChild(overlayEl);
          overlayBtn.addEventListener("click", () => {
            state.hasUserInteracted = true;
            const ctx = getSharedAudioContext();
            if (ctx.state === "suspended") {
              ctx.resume().then(() => ws.play());
            } else {
              ws.play();
            }
            overlayEl.style.display = "none";
          });
        }
        if (!plateEl.querySelector(".audio-clip-end-overlay")) {
          const dimEl = document.createElement("div");
          dimEl.className = "audio-clip-end-overlay";
          dimEl.style.cssText = "position:absolute;inset:0;background:rgba(0,0,0,0.25);opacity:0;transition:opacity 300ms ease-in;pointer-events:none;";
          plateEl.appendChild(dimEl);
        }
      });
    }).catch((err) => {
      console.error("audio-card: failed to load WaveSurfer API", err);
      _injectAudioError(plateEl);
      onError(err);
    });
    return wrapper;
  }
  function activateAudioCard(plateEl, sceneIndex) {
    plateEl.style.transform = "translateY(0)";
    plateEl.classList.add("is-active");
    const wrapper = _getAudioWrapperForPlate(plateEl);
    if (!wrapper || !wrapper.ws) return;
    try {
      wrapper.ws.setOptions({ height: Math.round(window.innerHeight * 0.35) });
    } catch (e) {
    }
    if (state.isMobileViewport || wrapper.isEmbed) {
      _showPlayOverlay(plateEl);
      return;
    }
    try {
      const ctx = getSharedAudioContext();
      if (ctx.state === "suspended") {
        ctx.resume().catch(() => {
        });
      }
      wrapper.ws.play().catch((err) => {
        if (err && err.name === "NotAllowedError") {
          _showPlayOverlay(plateEl);
          wrapper.isAutoplayBlocked = true;
        }
      });
    } catch (err) {
      if (err && err.name === "NotAllowedError") {
        _showPlayOverlay(plateEl);
      }
    }
  }
  function deactivateAudioCard(plateEl, fadeMs = 300) {
    plateEl.classList.remove("is-active");
    const wrapper = _getAudioWrapperForPlate(plateEl);
    if (!wrapper || !wrapper.ws) return;
    const steps = Math.ceil(fadeMs / 50);
    let step = 0;
    const startVolume = wrapper.ws.getVolume ? wrapper.ws.getVolume() : 1;
    const timer = setInterval(() => {
      step++;
      const newVolume = startVolume * (1 - step / steps);
      try {
        wrapper.ws.setVolume(Math.max(0, newVolume));
      } catch (e) {
        clearInterval(timer);
        return;
      }
      if (step >= steps) {
        clearInterval(timer);
        try {
          wrapper.ws.pause();
          wrapper.ws.setVolume(1);
        } catch (e) {
        }
      }
    }, 50);
  }
  function destroyAudioPlayer(wrapper) {
    if (!wrapper) return;
    try {
      if (wrapper.ws) {
        wrapper.ws.destroy();
      }
    } catch (e) {
      console.warn("destroyAudioPlayer: error during destroy", e);
    }
    const idx = _audioPlayers.indexOf(wrapper);
    if (idx !== -1) _audioPlayers.splice(idx, 1);
    const plateEl = wrapper.element;
    if (plateEl) {
      [
        ".waveform-container",
        ".audio-controls",
        ".audio-elapsed",
        ".audio-play-overlay",
        ".audio-clip-end-overlay",
        ".telar-alert"
      ].forEach((sel) => {
        const el = plateEl.querySelector(sel);
        if (el) el.remove();
      });
    }
  }
  function updateAudioClip(plateEl, clipStart, clipEnd, loop) {
    const wrapper = _getAudioWrapperForPlate(plateEl);
    if (!wrapper) return;
    if (wrapper.clipStart === clipStart && wrapper.clipEnd === clipEnd && wrapper.loop === loop) {
      return;
    }
    wrapper.clipStart = clipStart;
    wrapper.clipEnd = clipEnd;
    wrapper.loop = loop;
    plateEl.dataset.clipStart = String(clipStart);
    plateEl.dataset.clipEnd = String(clipEnd);
    plateEl.dataset.loop = String(loop);
    removeAudioClipEndDim(plateEl);
    if (wrapper._regionsPlugin) {
      try {
        wrapper._regionsPlugin.clearRegions();
        if (clipStart !== void 0 && clipEnd && wrapper._colors) {
          wrapper._regionsPlugin.addRegion({
            start: clipStart,
            end: clipEnd,
            color: wrapper._colors.clipRegionColor,
            drag: false,
            resize: false
          });
        }
      } catch (e) {
      }
    }
    if (wrapper.ws) {
      try {
        wrapper.ws.setTime(clipStart || 0);
      } catch (e) {
      }
    }
  }
  function applyAudioClipEndDim(plateEl) {
    let overlay = plateEl.querySelector(".audio-clip-end-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "audio-clip-end-overlay";
      overlay.style.cssText = "position:absolute;inset:0;background:rgba(0,0,0,0.25);opacity:0;transition:opacity 300ms ease-in;pointer-events:none;";
      plateEl.appendChild(overlay);
    }
    void overlay.offsetHeight;
    overlay.style.opacity = "1";
  }
  function removeAudioClipEndDim(plateEl) {
    const overlay = plateEl.querySelector(".audio-clip-end-overlay");
    if (overlay) overlay.style.opacity = "0";
  }
  function _enforceAudioPoolLimit(currentScene) {
    while (_audioPlayers.length > MAX_AUDIO_PLAYERS) {
      let farthestIdx = 0;
      let maxDist = -1;
      for (let i = 0; i < _audioPlayers.length; i++) {
        const dist = Math.abs(_audioPlayers[i].sceneIndex - currentScene);
        if (dist > maxDist) {
          maxDist = dist;
          farthestIdx = i;
        }
      }
      const evicted = _audioPlayers.splice(farthestIdx, 1)[0];
      _evictAudioPlayer(evicted);
    }
  }
  function _evictAudioPlayer(wrapper) {
    try {
      if (wrapper.ws) {
        wrapper.ws.destroy();
        wrapper.ws = null;
      }
    } catch (e) {
      console.warn("_evictAudioPlayer: error during evict", e);
    }
  }
  function _getAudioWrapperForPlate(plateEl) {
    return _audioPlayers.find((w) => w.element === plateEl) || null;
  }
  function _showPlayOverlay(plateEl) {
    const overlay = plateEl.querySelector(".audio-play-overlay");
    if (overlay) overlay.style.display = "flex";
  }
  function _injectAudioError(plateEl) {
    if (plateEl.querySelector(".telar-alert")) return;
    const alertEl = document.createElement("div");
    alertEl.className = "alert alert-warning telar-alert";
    alertEl.setAttribute("role", "alert");
    alertEl.innerHTML = `<strong>Audio unavailable</strong>
<p>This audio file could not be loaded. Continue scrolling to read the story.</p>`;
    plateEl.appendChild(alertEl);
  }
  var _audioResizeTimer = null;
  window.addEventListener("resize", () => {
    if (_audioResizeTimer) clearTimeout(_audioResizeTimer);
    _audioResizeTimer = setTimeout(() => {
      const newHeight = Math.round(window.innerHeight * 0.5);
      for (const wrapper of _audioPlayers) {
        if (wrapper.element && wrapper.element.classList.contains("is-active") && wrapper.ws) {
          try {
            wrapper.ws.setOptions({ height: newHeight });
          } catch (e) {
          }
        }
      }
    }, 100);
  });

  // assets/js/telar-story/card-pool.js
  function _isTruthy(val) {
    if (val === true) return true;
    if (typeof val === "string") {
      const v = val.trim().toLowerCase();
      return v === "true" || v === "yes" || v === "s\xED";
    }
    return false;
  }
  function computeZIndexPlan(steps) {
    let scene = -1;
    let runPos = 0;
    let currentObjectId = null;
    let titleCounter = 0;
    const plateZ = {};
    const textCardZ = {};
    for (let i = 0; i < steps.length; i++) {
      const objectId = steps[i].object || steps[i].objectId || "";
      const effectiveId = objectId === "" ? "__title_" + titleCounter++ + "__" : objectId;
      if (effectiveId !== currentObjectId) {
        scene++;
        runPos = 0;
        currentObjectId = effectiveId;
      }
      const bandBase = (scene + 1) * 100;
      plateZ[i] = bandBase;
      textCardZ[i] = bandBase + 1 + runPos;
      runPos++;
    }
    return { plateZ, textCardZ };
  }
  function seededRandom(seed) {
    const n = Math.sin(seed * 127.1 + 311.7) * 43758.5453;
    return n - Math.floor(n);
  }
  function getCardMessiness(seed, messinessPercent) {
    if (messinessPercent === 0) return { rot: 0, offX: 0, offY: 0 };
    const factor = messinessPercent / 100;
    const maxRot = 1.2 * factor;
    const maxOffX = 8 * factor;
    const maxOffY = 4 * factor;
    const rot = seededRandom(seed * 3 + 1) * maxRot * 2 - maxRot;
    const offX = seededRandom(seed * 3 + 2) * maxOffX * 2 - maxOffX;
    const offY = seededRandom(seed * 3 + 3) * maxOffY * 2 - maxOffY;
    return { rot, offX, offY };
  }
  function computeCardTop(viewportH, cardH, runPosition, peekHeightPx) {
    const centred = (viewportH - cardH) / 2;
    return centred + runPosition * peekHeightPx;
  }
  function _buildAriaLabel(objectId, stepAlt, cardType) {
    if (stepAlt) return stepAlt;
    const obj = state.objectsIndex?.[objectId] || {};
    if (obj.alt_text) return obj.alt_text;
    if (obj.title) return obj.title;
    if (objectId) return objectId;
    if (cardType === "youtube" || cardType === "vimeo" || cardType === "google-drive") return "Video player";
    if (cardType === "audio") return "Audio player";
    return "Image viewer";
  }
  var _stepsData = [];
  var _config = { peekHeight: 1, messiness: 20, preloadSteps: 5 };
  var _zPlan = { viewerPlateZ: {}, textCardZ: {} };
  function _buildSceneMaps(steps) {
    let scene = -1;
    let currentObjectId = null;
    let titleCounter = 0;
    state.stepToScene = {};
    state.sceneToObject = {};
    state.sceneFirstStep = {};
    for (let i = 0; i < steps.length; i++) {
      const objectId = steps[i].object || steps[i].objectId || "";
      const effectiveId = objectId === "" ? "__title_" + titleCounter++ + "__" : objectId;
      if (effectiveId !== currentObjectId) {
        scene++;
        currentObjectId = effectiveId;
        state.sceneToObject[scene] = objectId;
        state.sceneFirstStep[scene] = i;
      }
      state.stepToScene[i] = scene;
    }
    state.totalScenes = scene + 1;
  }
  function getSceneIndex(stepIndex) {
    return state.stepToScene[stepIndex] ?? -1;
  }
  function buildTransform(messiness, baseTranslate) {
    return `${baseTranslate} rotate(${messiness.rot}deg) translate(${messiness.offX}px, ${messiness.offY}px)`;
  }
  function initCardPool(storyData, config) {
    const cardStack = document.querySelector(".card-stack");
    if (!cardStack) return;
    const steps = (storyData?.steps || []).filter((s) => !s._metadata);
    const peekHeight = config?.peekHeight ?? 1;
    const messinessPercent = config?.messiness ?? 20;
    _stepsData = steps;
    _config = {
      peekHeight,
      messiness: messinessPercent,
      preloadSteps: state.config.preloadSteps || 5
    };
    const viewportH = window.innerHeight;
    const cardH = viewportH * 0.8;
    _zPlan = computeZIndexPlan(steps);
    _buildSceneMaps(steps);
    state.titleCards = {};
    state.activeTitleCardIndex = null;
    const audioObjects = storyData?.audioObjects || window.audioObjects || {};
    for (let sceneIdx = 0; sceneIdx < state.totalScenes; sceneIdx++) {
      const firstStepIdx = state.sceneFirstStep[sceneIdx];
      const objectId = state.sceneToObject[sceneIdx];
      if (!objectId) continue;
      const firstStep = steps[firstStepIdx] || {};
      const objectData = state.objectsIndex[objectId] || {};
      const audioExt = audioObjects[objectId];
      const sceneCardType = detectCardType({
        objectId,
        cardType: firstStep.cardType,
        source_url: objectData.source_url || objectData.iiif_manifest || "",
        file_path: audioExt ? `objects/${objectId}.${audioExt}` : ""
      });
      const plate = document.createElement("div");
      plate.className = "viewer-plate";
      plate.dataset.object = objectId;
      plate.dataset.scene = String(sceneIdx);
      plate.dataset.cardType = sceneCardType;
      plate.style.zIndex = _zPlan.plateZ[firstStepIdx];
      plate.setAttribute("role", "img");
      plate.setAttribute("aria-label", _buildAriaLabel(objectId, firstStep.alt_text, sceneCardType));
      plate.style.transform = "translateY(100%)";
      if (sceneCardType === "youtube" || sceneCardType === "vimeo" || sceneCardType === "google-drive") {
        plate.classList.add("video-plate");
        plate.dataset.cardType = sceneCardType;
        if (firstStep.clip_start) plate.dataset.clipStart = firstStep.clip_start;
        if (firstStep.clip_end) plate.dataset.clipEnd = firstStep.clip_end;
        if (firstStep.loop) plate.dataset.loop = firstStep.loop;
      }
      if (sceneCardType === "audio") {
        plate.classList.add("audio-plate");
        plate.dataset.cardType = "audio";
        if (firstStep.clip_start) plate.dataset.clipStart = firstStep.clip_start;
        if (firstStep.clip_end) plate.dataset.clipEnd = firstStep.clip_end;
        if (firstStep.loop) plate.dataset.loop = firstStep.loop;
      }
      cardStack.appendChild(plate);
      state.viewerPlates[sceneIdx] = plate;
    }
    const objectRunPosition = {};
    for (let stepIdx = 0; stepIdx < steps.length; stepIdx++) {
      const step = steps[stepIdx];
      const objectId = step.object || step.objectId || "";
      const objectData = state.objectsIndex[objectId] || {};
      const audioExt2 = audioObjects[objectId];
      const cardType = detectCardType({
        objectId,
        cardType: step.cardType,
        source_url: objectData.source_url || objectData.iiif_manifest || "",
        file_path: audioExt2 ? `objects/${objectId}.${audioExt2}` : ""
      });
      if (!objectId) {
        const zIndex = _zPlan.textCardZ[stepIdx];
        const titleCard = document.createElement("div");
        titleCard.className = "title-card";
        titleCard.dataset.stepIndex = String(stepIdx);
        titleCard.dataset.cardType = "title";
        titleCard.style.zIndex = zIndex;
        titleCard.style.transform = "translateY(100vh)";
        titleCard.innerHTML = _buildTitleCardContent(step);
        cardStack.appendChild(titleCard);
        state.titleCards[stepIdx] = titleCard;
        continue;
      }
      if (cardType === "text-only" || objectId) {
        if (!Object.hasOwn(objectRunPosition, objectId)) {
          objectRunPosition[objectId] = 0;
        }
        const runPos = objectRunPosition[objectId];
        objectRunPosition[objectId]++;
        const objectIndex = getSceneIndex(stepIdx);
        const zIndex = _zPlan.textCardZ[stepIdx];
        const topPx = computeCardTop(viewportH, cardH, 0, peekHeight);
        const messiness = getCardMessiness(stepIdx, messinessPercent);
        const card = document.createElement("div");
        card.className = "text-card";
        card.dataset.stepIndex = stepIdx;
        card.dataset.object = objectId;
        card.dataset.runPosition = runPos;
        card.style.zIndex = zIndex;
        card.style.top = `${topPx}px`;
        card.style.height = `${cardH}px`;
        card.style.transform = buildTransform(messiness, "translateY(100vh)");
        card.dataset.messinessRot = messiness.rot;
        card.dataset.messinessOffX = messiness.offX;
        card.dataset.messinessOffY = messiness.offY;
        const hiddenStep = document.querySelector(`.step-data .story-step[data-step="${step.step}"]`);
        if (hiddenStep) {
          const content = hiddenStep.querySelector(".step-content");
          if (content) {
            card.appendChild(content.cloneNode(true));
          } else {
            card.innerHTML = buildTextCardContent(step);
          }
        } else {
          card.innerHTML = buildTextCardContent(step);
        }
        cardStack.appendChild(card);
        state.textCards[stepIdx] = card;
        state.cardPool.push({
          stepIndex: stepIdx,
          objectId,
          cardType,
          runPosition: runPos,
          objectIndex,
          element: card
        });
      }
    }
    if (steps.length > 0) {
      const firstStep = steps[0];
      const firstObjectId = firstStep.object || firstStep.objectId || "";
      if (firstObjectId && state.viewerPlates[0]) {
        const plate = state.viewerPlates[0];
        const zIndex = _zPlan.plateZ[0];
        if (plate.classList.contains("video-plate")) {
          _initVideoInPlate(plate, firstObjectId, 0, zIndex);
        } else if (plate.classList.contains("audio-plate")) {
          _initAudioInPlate(plate, firstObjectId, 0, zIndex);
        } else {
          const x = parseFloat(firstStep.x);
          const y = parseFloat(firstStep.y);
          const zoom = parseFloat(firstStep.zoom);
          const page = firstStep.page ? parseInt(firstStep.page, 10) : void 0;
          _initTifyInPlate(plate, firstObjectId, 0, zIndex, x, y, zoom, page);
        }
      }
    }
  }
  function buildTextCardContent(step) {
    const question = step.question || "";
    const answer = step.answer || "";
    const hasLayer1 = step.layer1_button && step.layer1_button.trim();
    const hasLayer2 = step.layer2_button && step.layer2_button.trim();
    let layerButtons = "";
    if (hasLayer1) {
      layerButtons += `<button class="panel-trigger" data-panel="layer1" data-step="${step.step}">${step.layer1_button}</button>`;
    }
    if (hasLayer2) {
      layerButtons += `<button class="panel-trigger" data-panel="layer2" data-step="${step.step}">${step.layer2_button}</button>`;
    }
    return `
    <div class="step-question">${question}</div>
    <div class="step-answer">${answer}</div>
    ${layerButtons ? `<div class="step-actions">${layerButtons}</div>` : ""}
  `;
  }
  function _buildTitleCardContent(step) {
    const heading = step.question || "";
    const body = step.answer || "";
    return `
    <div class="title-card-inner">
      <h2 class="title-card-heading">${heading}</h2>
      ${body ? '<p class="title-card-body">' + body + "</p>" : ""}
    </div>
  `;
  }
  function activateCard(index2, direction) {
    if (state.titleCards?.[index2]) {
      _activateTitleCardStep(index2, direction);
      return;
    }
    const card = state.textCards[index2];
    if (!card) return;
    const poolEntry = state.cardPool.find((c) => c.stepIndex === index2);
    if (!poolEntry) return;
    const step = _stepsData[index2] || {};
    const prevStep2 = index2 > 0 ? _stepsData[index2 - 1] : null;
    const objectId = poolEntry.objectId;
    const prevObjectId = state.currentObjectRun?.objectId;
    const currentMode = isFullObjectMode(step);
    const prevMode = prevStep2 ? isFullObjectMode(prevStep2) : null;
    const isModeChange = prevMode !== null && currentMode !== prevMode;
    const isObjectChange = objectId !== prevObjectId;
    const needsNewViewer = isObjectChange || isModeChange;
    if (direction === "forward") {
      if (needsNewViewer) {
        _activateNewViewerPlate(objectId, index2, prevObjectId, step, direction);
        state.currentObjectRun = { objectId, runPosition: poolEntry.runPosition };
        _deactivatePreviousTextCard(index2, direction);
        if (state.activeTitleCardIndex != null) {
          const prevTitle = state.titleCards[state.activeTitleCardIndex];
          if (prevTitle) {
            prevTitle.classList.remove("is-active");
            prevTitle.classList.add("is-stacked");
          }
          state.activeTitleCardIndex = null;
        }
        _activateTextCard(card);
        updateObjectCredits(objectId);
      } else {
        state.currentObjectRun.runPosition = poolEntry.runPosition;
        _deactivatePreviousTextCard(index2, direction);
        _activateTextCard(card);
        const sceneIndex = getSceneIndex(index2);
        const plate = sceneIndex >= 0 ? state.viewerPlates[sceneIndex] : null;
        if (plate && plate.classList.contains("video-plate")) {
          const clipStart = parseFloat(step.clip_start) || 0;
          const clipEnd = parseFloat(step.clip_end) || 0;
          const loop = _isTruthy(step.loop);
          updateVideoClip(plate, clipStart, clipEnd || void 0, loop);
        } else if (plate && plate.classList.contains("audio-plate")) {
          const clipStart = parseFloat(step.clip_start) || 0;
          const clipEnd = parseFloat(step.clip_end) || 0;
          const loop = _isTruthy(step.loop);
          updateAudioClip(plate, clipStart, clipEnd || void 0, loop);
        } else if (!state.scrollDriven) {
          _animateViewerToStep(objectId, step, index2);
        }
      }
    } else {
      if (needsNewViewer) {
        const prevSceneIndex = prevObjectId !== null ? getSceneIndex(Math.max(0, index2 + 1)) : -1;
        const currentSceneIndex = getSceneIndex(index2 + 1);
        const currentPlate = currentSceneIndex >= 0 ? state.viewerPlates[currentSceneIndex] : null;
        const prevPlate = state.viewerPlates[getSceneIndex(index2)];
        {
          if (currentPlate) {
            if (currentPlate.classList.contains("video-plate")) {
              currentPlate.style.transition = "none";
              currentPlate.style.transform = "translateY(100%)";
              void currentPlate.offsetHeight;
              currentPlate.style.transition = "";
              deactivateVideoCard(currentPlate);
            } else if (currentPlate.classList.contains("audio-plate")) {
              currentPlate.style.transition = "none";
              currentPlate.style.transform = "translateY(100%)";
              void currentPlate.offsetHeight;
              currentPlate.style.transition = "";
              deactivateAudioCard(currentPlate);
            } else {
              deactivateIiifCard(
                { element: currentPlate, objectId: prevObjectId },
                "backward"
              );
            }
            currentPlate.classList.remove("is-active");
          }
          if (prevPlate) {
            prevPlate.style.zIndex = _zPlan.plateZ[index2];
            prevPlate.style.transition = "none";
            prevPlate.style.transform = "translateY(0)";
            void prevPlate.offsetHeight;
            prevPlate.style.transition = "";
            prevPlate.classList.add("is-active");
            if (prevPlate.classList.contains("video-plate")) {
              activateVideoCard(prevPlate, getSceneIndex(index2));
            } else if (prevPlate.classList.contains("audio-plate")) {
              activateAudioCard(prevPlate, getSceneIndex(index2));
            }
          }
        }
        state.currentObjectRun = { objectId, runPosition: poolEntry.runPosition };
        _deactivatePreviousTextCard(index2, direction);
        if (state.activeTitleCardIndex != null) {
          const prevTitle = state.titleCards[state.activeTitleCardIndex];
          if (prevTitle) {
            prevTitle.classList.remove("is-active");
            prevTitle.style.transform = "translateY(100vh)";
            prevTitle.classList.remove("is-stacked");
          }
          state.activeTitleCardIndex = null;
        }
        _activateTextCard(card);
        updateObjectCredits(objectId);
      } else {
        state.currentObjectRun.runPosition = poolEntry.runPosition;
        _deactivatePreviousTextCard(index2, direction);
        _activateTextCard(card);
        const sceneIndex = getSceneIndex(index2);
        const plate = sceneIndex >= 0 ? state.viewerPlates[sceneIndex] : null;
        if (plate && plate.classList.contains("video-plate")) {
          const clipStart = parseFloat(step.clip_start) || 0;
          const clipEnd = parseFloat(step.clip_end) || 0;
          const loop = _isTruthy(step.loop);
          updateVideoClip(plate, clipStart, clipEnd || void 0, loop);
        } else if (plate && plate.classList.contains("audio-plate")) {
          const clipStart = parseFloat(step.clip_start) || 0;
          const clipEnd = parseFloat(step.clip_end) || 0;
          const loop = _isTruthy(step.loop);
          updateAudioClip(plate, clipStart, clipEnd || void 0, loop);
        } else if (!state.scrollDriven) {
          _animateViewerToStep(objectId, step, index2);
        }
      }
    }
    const _stepData = _stepsData[index2] || {};
    const _stepAlt = _stepData.alt_text || "";
    const _plateForStep = state.viewerPlates?.[state.stepToScene?.[index2]];
    if (_plateForStep) {
      const _cType = _plateForStep.dataset.cardType || "iiif";
      _plateForStep.setAttribute("aria-label", _buildAriaLabel(objectId, _stepAlt, _cType));
    }
    preloadAhead(index2, _config.preloadSteps, 2);
  }
  function setCardProgress(stepIndex, progress) {
    if (progress < 1e-3) return;
    const nextIndex = stepIndex + 1;
    const nextCard = state.textCards[nextIndex] || state.titleCards?.[nextIndex];
    if (!nextCard) return;
    const cardStack = document.querySelector(".card-stack");
    if (!cardStack || !cardStack.classList.contains("is-scrubbing")) return;
    const rot = parseFloat(nextCard.dataset.messinessRot || 0);
    const offX = parseFloat(nextCard.dataset.messinessOffX || 0);
    const offY = parseFloat(nextCard.dataset.messinessOffY || 0);
    const translateY = (1 - progress) * 100;
    nextCard.style.transform = `translateY(${translateY}vh) rotate(${rot}deg) translate(${offX}px, ${offY}px)`;
    const nextStep2 = _stepsData[nextIndex];
    const currentStep = _stepsData[stepIndex];
    if (!nextStep2 || !currentStep) return;
    const nextObjectId = nextStep2.object || nextStep2.objectId || "";
    const currentObjectId = currentStep.object || currentStep.objectId || "";
    if (nextObjectId !== currentObjectId) {
      if (nextObjectId === "") {
        const currentSceneIndex = getSceneIndex(stepIndex);
        const currentPlate = currentSceneIndex >= 0 ? state.viewerPlates[currentSceneIndex] : null;
        if (currentPlate) {
          currentPlate.style.transform = `translateY(-${progress * 100}%)`;
        }
      } else {
        const nextSceneIndex = getSceneIndex(nextIndex);
        const nextPlate = nextSceneIndex >= 0 ? state.viewerPlates[nextSceneIndex] : null;
        if (nextPlate) {
          const plateTranslateY = (1 - progress) * 100;
          nextPlate.style.transform = `translateY(${plateTranslateY}%)`;
        }
      }
    }
  }
  function _activateNewViewerPlate(objectId, stepIndex, prevObjectId, step, direction) {
    const sceneIndex = getSceneIndex(stepIndex);
    const prevSceneIndex = stepIndex > 0 ? getSceneIndex(stepIndex - 1) : -1;
    const prevPlate = prevSceneIndex >= 0 ? state.viewerPlates[prevSceneIndex] : null;
    const newPlate = sceneIndex >= 0 ? state.viewerPlates[sceneIndex] : null;
    if (!newPlate) return;
    newPlate.style.zIndex = _zPlan.plateZ[stepIndex];
    if (direction === "forward") {
      if (sceneIndex === 0) {
        const currentTransform = newPlate.style.transform;
        if (!currentTransform || currentTransform === "translateY(100%)") {
          newPlate.style.transform = "translateY(100%)";
          void newPlate.offsetHeight;
        }
      } else {
        newPlate.style.transform = "translateY(100%)";
        void newPlate.offsetHeight;
      }
      newPlate.style.transform = "translateY(0)";
    } else {
      newPlate.style.transform = "translateY(0)";
      if (prevPlate) {
        prevPlate.style.transform = "translateY(100%)";
      }
    }
    newPlate.classList.add("is-active");
    if (prevPlate) {
      if (prevPlate.classList.contains("video-plate")) {
        deactivateVideoCard(prevPlate);
      } else if (prevPlate.classList.contains("audio-plate")) {
        deactivateAudioCard(prevPlate);
      } else {
        prevPlate.classList.remove("is-active");
      }
    }
    const viewerCard = state.viewerCards.find((vc) => vc.sceneIndex === sceneIndex);
    const x = parseFloat(step.x);
    const y = parseFloat(step.y);
    const zoom = parseFloat(step.zoom);
    const page = step.page ? parseInt(step.page, 10) : void 0;
    if (newPlate.classList.contains("audio-plate")) {
      if (!newPlate.querySelector(".waveform-container")) {
        const zIndex = _zPlan.plateZ[stepIndex];
        _initAudioInPlate(newPlate, objectId, sceneIndex, zIndex);
      }
      activateAudioCard(newPlate, sceneIndex);
    } else if (newPlate.classList.contains("video-plate")) {
      if (!newPlate.querySelector(".video-iframe, iframe")) {
        const zIndex = _zPlan.plateZ[stepIndex];
        _initVideoInPlate(newPlate, objectId, sceneIndex, zIndex);
      }
      activateVideoCard(newPlate, sceneIndex);
    } else if (!viewerCard) {
      const zIndex = _zPlan.plateZ[stepIndex];
      _initTifyInPlate(newPlate, objectId, sceneIndex, zIndex, x, y, zoom, page);
    } else if (viewerCard.isReady && !isNaN(x) && !isNaN(y) && !isNaN(zoom)) {
      snapIiifToPosition(viewerCard, x, y, zoom);
    } else if (!isNaN(x) && !isNaN(y) && !isNaN(zoom)) {
      viewerCard.pendingZoom = { x, y, zoom, snap: true };
    }
  }
  function _initTifyInPlate(plateEl, objectId, sceneIndex, zIndex, x, y, zoom, page) {
    const manifestUrl = getManifestUrl(objectId, page);
    if (!manifestUrl) {
      console.error("_initTifyInPlate: no manifest URL for", objectId);
      return;
    }
    plateEl.dataset.loading = "true";
    const viewerId = `iiif-viewer-${state.viewerCardCounter}`;
    let viewerDiv = plateEl.querySelector(".viewer-instance");
    if (!viewerDiv) {
      viewerDiv = document.createElement("div");
      viewerDiv.className = "viewer-instance";
      viewerDiv.id = viewerId;
      plateEl.appendChild(viewerDiv);
    } else {
      viewerDiv.id = viewerId;
    }
    const tifyInstance = new window.Tify({
      container: "#" + viewerId,
      manifestUrl,
      panels: [],
      urlQueryKey: false
    });
    const viewerCard = {
      sceneIndex,
      // scene this card belongs to
      objectId,
      page: page || void 0,
      element: plateEl,
      tifyInstance,
      osdViewer: null,
      isReady: false,
      pendingZoom: !isNaN(x) && !isNaN(y) && !isNaN(zoom) ? { x, y, zoom, snap: true } : null,
      zIndex
    };
    tifyInstance.ready.then(() => {
      viewerCard.osdViewer = tifyInstance.viewer;
      viewerCard.isReady = true;
      delete plateEl.dataset.loading;
      tifyInstance.viewer.gestureSettingsMouse.scrollToZoom = false;
      if (viewerCard.pendingZoom) {
        if (viewerCard.pendingZoom.snap) {
          snapIiifToPosition(viewerCard, viewerCard.pendingZoom.x, viewerCard.pendingZoom.y, viewerCard.pendingZoom.zoom);
        } else {
          animateIiifToPosition(viewerCard, viewerCard.pendingZoom.x, viewerCard.pendingZoom.y, viewerCard.pendingZoom.zoom);
        }
        viewerCard.pendingZoom = null;
      }
    }).catch((err) => {
      console.error(`_initTifyInPlate: Tify failed for ${objectId}:`, err);
      viewerCard.isReady = true;
      delete plateEl.dataset.loading;
    });
    state.viewerCards.push(viewerCard);
    state.viewerCardCounter++;
    while (state.viewerCards.length > state.config.maxViewerCards) {
      const currentScene = sceneIndex;
      let farthestIdx = 0;
      let maxDist = -1;
      for (let i = 0; i < state.viewerCards.length; i++) {
        const dist = Math.abs(state.viewerCards[i].sceneIndex - currentScene);
        if (dist > maxDist) {
          maxDist = dist;
          farthestIdx = i;
        }
      }
      const evicted = state.viewerCards.splice(farthestIdx, 1)[0];
      _evictTifyInstance(evicted);
    }
  }
  function _evictTifyInstance(viewerCard) {
    if (viewerCard.osdViewer) {
      const canvas = viewerCard.osdViewer.drawer?.canvas;
      if (canvas) {
        const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
        if (gl) {
          gl.getExtension("WEBGL_lose_context")?.loseContext();
        }
      }
    }
    if (viewerCard.tifyInstance && typeof viewerCard.tifyInstance.destroy === "function") {
      viewerCard.tifyInstance.destroy();
    }
    viewerCard.tifyInstance = null;
    viewerCard.osdViewer = null;
    viewerCard.isReady = false;
    const viewerInstance = viewerCard.element.querySelector(".viewer-instance");
    if (viewerInstance) viewerInstance.remove();
  }
  function _initVideoInPlate(plateEl, objectId, sceneIndex, zIndex) {
    const objectData = state.objectsIndex[objectId] || {};
    const sourceUrl = objectData.source_url || objectData.iiif_manifest || "";
    const cardType = plateEl.dataset.cardType;
    const videoId = extractVideoId(cardType, sourceUrl);
    if (!videoId) {
      console.error("_initVideoInPlate: no video ID for", objectId, sourceUrl);
      return;
    }
    const clipStart = parseFloat(plateEl.dataset.clipStart) || 0;
    const clipEnd = parseFloat(plateEl.dataset.clipEnd) || 0;
    const loop = _isTruthy(plateEl.dataset.loop);
    plateEl.style.zIndex = zIndex;
    createVideoPlayer(plateEl, cardType, videoId, {
      clipStart,
      clipEnd: clipEnd || void 0,
      loop,
      sceneIndex,
      sourceUrl,
      onPlay: () => {
      },
      onTimeUpdate: () => {
      },
      onEnded: () => {
        applyClipEndDim(plateEl);
      },
      onAutoplayBlocked: () => {
        _showVideoPlayOverlay(plateEl);
      }
    });
  }
  function _initAudioInPlate(plateEl, objectId, sceneIndex, zIndex) {
    const audioObjects = window.storyData?.audioObjects || window.audioObjects || {};
    const ext = audioObjects[objectId];
    if (!ext) {
      console.error("_initAudioInPlate: no audio extension for", objectId);
      return;
    }
    const basePath = getBasePath();
    const audioUrl = `${basePath}/telar-content/objects/${objectId}.${ext}`;
    const peaksUrl = `${basePath}/assets/audio/peaks/${objectId}.json`;
    const clipStart = parseFloat(plateEl.dataset.clipStart) || 0;
    const clipEnd = parseFloat(plateEl.dataset.clipEnd) || 0;
    const loop = _isTruthy(plateEl.dataset.loop);
    const isEmbed = document.body.classList.contains("embed-mode");
    plateEl.style.zIndex = zIndex;
    createAudioPlayer(plateEl, audioUrl, peaksUrl, {
      clipStart,
      clipEnd: clipEnd || void 0,
      loop,
      sceneIndex,
      isEmbed,
      onPlay: () => {
      },
      onTimeUpdate: () => {
      },
      onEnded: () => {
        applyAudioClipEndDim(plateEl);
      },
      onAutoplayBlocked: () => {
      }
    });
  }
  function _deactivatePreviousTextCard(newIndex, direction) {
    const prevCard = state.cardPool.find((c) => c.element.classList.contains("is-active"));
    if (!prevCard || prevCard.stepIndex === newIndex) return;
    const el = prevCard.element;
    const messiness = {
      rot: parseFloat(el.dataset.messinessRot || 0),
      offX: parseFloat(el.dataset.messinessOffX || 0),
      offY: parseFloat(el.dataset.messinessOffY || 0)
    };
    el.classList.remove("is-active");
    if (direction === "backward") {
      el.style.transform = buildTransform(messiness, "translateY(100vh)");
      el.classList.remove("is-stacked");
    } else {
      el.classList.add("is-stacked");
    }
  }
  function _activateTextCard(cardEl) {
    const messiness = {
      rot: parseFloat(cardEl.dataset.messinessRot || 0),
      offX: parseFloat(cardEl.dataset.messinessOffX || 0),
      offY: parseFloat(cardEl.dataset.messinessOffY || 0)
    };
    cardEl.classList.remove("is-stacked");
    cardEl.classList.add("is-active");
    cardEl.style.transform = buildTransform(messiness, "translateY(0)");
  }
  function _activateTitleCardStep(index2, direction) {
    const titleCard = state.titleCards[index2];
    if (!titleCard) return;
    if (state.activeTitleCardIndex != null && state.activeTitleCardIndex !== index2) {
      const prevTitle = state.titleCards[state.activeTitleCardIndex];
      if (prevTitle) {
        prevTitle.classList.remove("is-active");
        if (direction === "backward") {
          prevTitle.style.transform = "translateY(100vh)";
          prevTitle.classList.remove("is-stacked");
        } else {
          prevTitle.classList.add("is-stacked");
        }
      }
    }
    _deactivatePreviousTextCard(index2, direction);
    const departingStepIndex = direction === "backward" ? index2 + 1 : index2 - 1;
    const departingSceneIndex = departingStepIndex >= 0 ? getSceneIndex(departingStepIndex) : -1;
    const departingPlate = departingSceneIndex >= 0 ? state.viewerPlates[departingSceneIndex] : null;
    if (departingPlate) {
      if (direction === "backward") {
        departingPlate.style.transition = "none";
        departingPlate.style.transform = "translateY(100%)";
        void departingPlate.offsetHeight;
        departingPlate.style.transition = "";
      }
      if (departingPlate.classList.contains("video-plate")) {
        deactivateVideoCard(departingPlate);
      } else if (departingPlate.classList.contains("audio-plate")) {
        deactivateAudioCard(departingPlate);
      } else {
        departingPlate.classList.remove("is-active");
      }
    }
    titleCard.classList.remove("is-stacked");
    titleCard.classList.add("is-active");
    titleCard.style.transform = "translateY(0)";
    state.activeTitleCardIndex = index2;
    state.currentObjectRun = { objectId: "", runPosition: 0 };
    updateObjectCredits("");
    preloadAhead(index2, _config.preloadSteps, 2);
  }
  function _animateViewerToStep(objectId, step, stepIndex) {
    const x = parseFloat(step.x);
    const y = parseFloat(step.y);
    const zoom = parseFloat(step.zoom);
    if (isNaN(x) || isNaN(y) || isNaN(zoom)) return;
    const sceneIndex = getSceneIndex(stepIndex);
    const viewerCard = state.viewerCards.find((vc) => vc.sceneIndex === sceneIndex);
    if (!viewerCard) return;
    if (viewerCard.isReady) {
      animateIiifToPosition(viewerCard, x, y, zoom);
    } else {
      viewerCard.pendingZoom = { x, y, zoom, snap: false };
    }
  }
  function preloadAhead(currentIndex, ahead, behind) {
    const currentScene = getSceneIndex(currentIndex);
    if (currentScene < 0) return;
    for (let offset = 1; offset <= ahead; offset++) {
      const targetScene = currentScene + offset;
      if (targetScene >= state.totalScenes) break;
      const plate = state.viewerPlates[targetScene];
      if (!plate) continue;
      const firstStepIdx = state.sceneFirstStep[targetScene];
      const step = _stepsData[firstStepIdx];
      if (!step) continue;
      const objectId = step.object || step.objectId || "";
      if (!objectId) continue;
      const zIndex = _zPlan.plateZ[firstStepIdx];
      if (plate.classList.contains("audio-plate")) {
        if (!plate.querySelector(".waveform-container")) {
          console.log(`preloadAhead (audio): scene ${targetScene} / ${objectId} (step ${firstStepIdx})`);
          _initAudioInPlate(plate, objectId, targetScene, zIndex);
        }
      } else if (plate.classList.contains("video-plate")) {
        if (!plate.querySelector(".video-iframe, iframe")) {
          console.log(`preloadAhead (video): scene ${targetScene} / ${objectId} (step ${firstStepIdx})`);
          _initVideoInPlate(plate, objectId, targetScene, zIndex);
        }
      } else {
        if (state.viewerCards.find((vc) => vc.sceneIndex === targetScene)) continue;
        const x = parseFloat(step.x);
        const y = parseFloat(step.y);
        const zoom = parseFloat(step.zoom);
        const page = step.page ? parseInt(step.page, 10) : void 0;
        console.log(`preloadAhead: scene ${targetScene} / ${objectId} (step ${firstStepIdx})`);
        _initTifyInPlate(plate, objectId, targetScene, zIndex, x, y, zoom, page);
        _prefetchTilesForScene(targetScene);
      }
    }
    for (let offset = ahead + 1; offset <= ahead + 2; offset++) {
      const tileScene = currentScene + offset;
      if (tileScene >= state.totalScenes) break;
      _prefetchTilesForScene(tileScene);
    }
    for (let offset = 1; offset <= behind; offset++) {
      const targetScene = currentScene - offset;
      if (targetScene < 0) break;
      const plate = state.viewerPlates[targetScene];
      if (!plate) continue;
      const firstStepIdx = state.sceneFirstStep[targetScene];
      const step = _stepsData[firstStepIdx];
      if (!step) continue;
      const objectId = step.object || step.objectId || "";
      if (!objectId) continue;
      const zIndex = _zPlan.plateZ[firstStepIdx];
      if (plate.classList.contains("audio-plate")) {
        if (!plate.querySelector(".waveform-container")) {
          console.log(`preloadAhead (audio): scene ${targetScene} / ${objectId} (step ${firstStepIdx})`);
          _initAudioInPlate(plate, objectId, targetScene, zIndex);
        }
      } else if (plate.classList.contains("video-plate")) {
        if (!plate.querySelector(".video-iframe, iframe")) {
          console.log(`preloadAhead (video): scene ${targetScene} / ${objectId} (step ${firstStepIdx})`);
          _initVideoInPlate(plate, objectId, targetScene, zIndex);
        }
      } else {
        if (state.viewerCards.find((vc) => vc.sceneIndex === targetScene)) continue;
        const x = parseFloat(step.x);
        const y = parseFloat(step.y);
        const zoom = parseFloat(step.zoom);
        const page = step.page ? parseInt(step.page, 10) : void 0;
        console.log(`preloadAhead: scene ${targetScene} / ${objectId} (step ${firstStepIdx})`);
        _initTifyInPlate(plate, objectId, targetScene, zIndex, x, y, zoom, page);
        _prefetchTilesForScene(targetScene);
      }
    }
  }
  function _prefetchTilesForScene(sceneIndex) {
    const objectId = state.sceneToObject[sceneIndex];
    if (!objectId) return;
    const objData = state.objectsIndex?.[objectId];
    if (objData?.iiif_manifest || objData?.source_url) return;
    const basePath = getBasePath();
    const baseUrl = `${window.location.origin}${basePath}/iiif/objects/${objectId}`;
    const infoUrl = `${baseUrl}/info.json`;
    fetch(infoUrl).then((r) => r.json()).then((info) => {
      const firstStepIdx = state.sceneFirstStep[sceneIndex];
      const step = _stepsData[firstStepIdx];
      if (!step) return;
      const x = parseFloat(step.x);
      const y = parseFloat(step.y);
      const zoom = parseFloat(step.zoom);
      if (isNaN(x) || isNaN(y) || isNaN(zoom)) return;
      const urls = _computeTileUrls(baseUrl, info, x, y, zoom);
      for (const url of urls) {
        const link = document.createElement("link");
        link.rel = "prefetch";
        link.as = "image";
        link.href = url;
        document.head.appendChild(link);
      }
    }).catch(() => {
    });
  }
  function _computeTileUrls(baseUrl, info, x, y, zoom) {
    const imageW = info.width;
    const imageH = info.height;
    const tileSize = info.tiles?.[0]?.width || 512;
    const scaleFactors = info.tiles?.[0]?.scaleFactors || [1];
    const centreX = x * imageW;
    const centreY = y * imageH;
    const vpW = window.innerWidth;
    const vpH = window.innerHeight;
    const pixelsPerViewportPx = 1 / (zoom * (vpW / imageW));
    const visibleW = vpW * pixelsPerViewportPx;
    const visibleH = vpH * pixelsPerViewportPx;
    const left = Math.max(0, centreX - visibleW / 2);
    const top = Math.max(0, centreY - visibleH / 2);
    const right = Math.min(imageW, centreX + visibleW / 2);
    const bottom = Math.min(imageH, centreY + visibleH / 2);
    let scaleFactor = scaleFactors[0] || 1;
    for (const sf of scaleFactors) {
      const effectiveTile2 = tileSize * sf;
      const tilesX = Math.ceil((right - left) / effectiveTile2);
      const tilesY = Math.ceil((bottom - top) / effectiveTile2);
      if (tilesX * tilesY <= 9) {
        scaleFactor = sf;
        break;
      }
    }
    const effectiveTile = tileSize * scaleFactor;
    const urls = [];
    for (let tx = Math.floor(left / effectiveTile); tx * effectiveTile < right; tx++) {
      for (let ty = Math.floor(top / effectiveTile); ty * effectiveTile < bottom; ty++) {
        const rx = tx * effectiveTile;
        const ry = ty * effectiveTile;
        const rw = Math.min(effectiveTile, imageW - rx);
        const rh = Math.min(effectiveTile, imageH - ry);
        if (rw <= 0 || rh <= 0) continue;
        const outW = Math.ceil(rw / scaleFactor);
        const outH = Math.ceil(rh / scaleFactor);
        const url = `${baseUrl}/${rx},${ry},${rw},${rh}/${outW},/0/default.jpg`;
        urls.push(url);
        if (urls.length >= 9) return urls;
      }
    }
    return urls;
  }

  // node_modules/lenis/dist/lenis.mjs
  var version = "1.3.21";
  function clamp(min, input, max) {
    return Math.max(min, Math.min(input, max));
  }
  function lerp(x, y, t) {
    return (1 - t) * x + t * y;
  }
  function damp(x, y, lambda, deltaTime) {
    return lerp(x, y, 1 - Math.exp(-lambda * deltaTime));
  }
  function modulo(n, d) {
    return (n % d + d) % d;
  }
  var Animate = class {
    isRunning = false;
    value = 0;
    from = 0;
    to = 0;
    currentTime = 0;
    lerp;
    duration;
    easing;
    onUpdate;
    /**
    * Advance the animation by the given delta time
    *
    * @param deltaTime - The time in seconds to advance the animation
    */
    advance(deltaTime) {
      if (!this.isRunning) return;
      let completed = false;
      if (this.duration && this.easing) {
        this.currentTime += deltaTime;
        const linearProgress = clamp(0, this.currentTime / this.duration, 1);
        completed = linearProgress >= 1;
        const easedProgress = completed ? 1 : this.easing(linearProgress);
        this.value = this.from + (this.to - this.from) * easedProgress;
      } else if (this.lerp) {
        this.value = damp(this.value, this.to, this.lerp * 60, deltaTime);
        if (Math.round(this.value) === this.to) {
          this.value = this.to;
          completed = true;
        }
      } else {
        this.value = this.to;
        completed = true;
      }
      if (completed) this.stop();
      this.onUpdate?.(this.value, completed);
    }
    /** Stop the animation */
    stop() {
      this.isRunning = false;
    }
    /**
    * Set up the animation from a starting value to an ending value
    * with optional parameters for lerping, duration, easing, and onUpdate callback
    *
    * @param from - The starting value
    * @param to - The ending value
    * @param options - Options for the animation
    */
    fromTo(from, to, { lerp: lerp2, duration, easing, onStart, onUpdate }) {
      this.from = this.value = from;
      this.to = to;
      this.lerp = lerp2;
      this.duration = duration;
      this.easing = easing;
      this.currentTime = 0;
      this.isRunning = true;
      onStart?.();
      this.onUpdate = onUpdate;
    }
  };
  function debounce(callback, delay) {
    let timer;
    return function(...args) {
      clearTimeout(timer);
      timer = setTimeout(() => {
        timer = void 0;
        callback.apply(this, args);
      }, delay);
    };
  }
  var Dimensions = class {
    width = 0;
    height = 0;
    scrollHeight = 0;
    scrollWidth = 0;
    debouncedResize;
    wrapperResizeObserver;
    contentResizeObserver;
    constructor(wrapper, content, { autoResize = true, debounce: debounceValue = 250 } = {}) {
      this.wrapper = wrapper;
      this.content = content;
      if (autoResize) {
        this.debouncedResize = debounce(this.resize, debounceValue);
        if (this.wrapper instanceof Window) window.addEventListener("resize", this.debouncedResize);
        else {
          this.wrapperResizeObserver = new ResizeObserver(this.debouncedResize);
          this.wrapperResizeObserver.observe(this.wrapper);
        }
        this.contentResizeObserver = new ResizeObserver(this.debouncedResize);
        this.contentResizeObserver.observe(this.content);
      }
      this.resize();
    }
    destroy() {
      this.wrapperResizeObserver?.disconnect();
      this.contentResizeObserver?.disconnect();
      if (this.wrapper === window && this.debouncedResize) window.removeEventListener("resize", this.debouncedResize);
    }
    resize = () => {
      this.onWrapperResize();
      this.onContentResize();
    };
    onWrapperResize = () => {
      if (this.wrapper instanceof Window) {
        this.width = window.innerWidth;
        this.height = window.innerHeight;
      } else {
        this.width = this.wrapper.clientWidth;
        this.height = this.wrapper.clientHeight;
      }
    };
    onContentResize = () => {
      if (this.wrapper instanceof Window) {
        this.scrollHeight = this.content.scrollHeight;
        this.scrollWidth = this.content.scrollWidth;
      } else {
        this.scrollHeight = this.wrapper.scrollHeight;
        this.scrollWidth = this.wrapper.scrollWidth;
      }
    };
    get limit() {
      return {
        x: this.scrollWidth - this.width,
        y: this.scrollHeight - this.height
      };
    }
  };
  var Emitter = class {
    events = {};
    /**
    * Emit an event with the given data
    * @param event Event name
    * @param args Data to pass to the event handlers
    */
    emit(event, ...args) {
      const callbacks = this.events[event] || [];
      for (let i = 0, length = callbacks.length; i < length; i++) callbacks[i]?.(...args);
    }
    /**
    * Add a callback to the event
    * @param event Event name
    * @param cb Callback function
    * @returns Unsubscribe function
    */
    on(event, cb) {
      if (this.events[event]) this.events[event].push(cb);
      else this.events[event] = [cb];
      return () => {
        this.events[event] = this.events[event]?.filter((i) => cb !== i);
      };
    }
    /**
    * Remove a callback from the event
    * @param event Event name
    * @param callback Callback function
    */
    off(event, callback) {
      this.events[event] = this.events[event]?.filter((i) => callback !== i);
    }
    /**
    * Remove all event listeners and clean up
    */
    destroy() {
      this.events = {};
    }
  };
  var LINE_HEIGHT = 100 / 6;
  var listenerOptions = { passive: false };
  function getDeltaMultiplier(deltaMode, size) {
    if (deltaMode === 1) return LINE_HEIGHT;
    if (deltaMode === 2) return size;
    return 1;
  }
  var VirtualScroll = class {
    touchStart = {
      x: 0,
      y: 0
    };
    lastDelta = {
      x: 0,
      y: 0
    };
    window = {
      width: 0,
      height: 0
    };
    emitter = new Emitter();
    constructor(element, options = {
      wheelMultiplier: 1,
      touchMultiplier: 1
    }) {
      this.element = element;
      this.options = options;
      window.addEventListener("resize", this.onWindowResize);
      this.onWindowResize();
      this.element.addEventListener("wheel", this.onWheel, listenerOptions);
      this.element.addEventListener("touchstart", this.onTouchStart, listenerOptions);
      this.element.addEventListener("touchmove", this.onTouchMove, listenerOptions);
      this.element.addEventListener("touchend", this.onTouchEnd, listenerOptions);
    }
    /**
    * Add an event listener for the given event and callback
    *
    * @param event Event name
    * @param callback Callback function
    */
    on(event, callback) {
      return this.emitter.on(event, callback);
    }
    /** Remove all event listeners and clean up */
    destroy() {
      this.emitter.destroy();
      window.removeEventListener("resize", this.onWindowResize);
      this.element.removeEventListener("wheel", this.onWheel, listenerOptions);
      this.element.removeEventListener("touchstart", this.onTouchStart, listenerOptions);
      this.element.removeEventListener("touchmove", this.onTouchMove, listenerOptions);
      this.element.removeEventListener("touchend", this.onTouchEnd, listenerOptions);
    }
    /**
    * Event handler for 'touchstart' event
    *
    * @param event Touch event
    */
    onTouchStart = (event) => {
      const { clientX, clientY } = event.targetTouches ? event.targetTouches[0] : event;
      this.touchStart.x = clientX;
      this.touchStart.y = clientY;
      this.lastDelta = {
        x: 0,
        y: 0
      };
      this.emitter.emit("scroll", {
        deltaX: 0,
        deltaY: 0,
        event
      });
    };
    /** Event handler for 'touchmove' event */
    onTouchMove = (event) => {
      const { clientX, clientY } = event.targetTouches ? event.targetTouches[0] : event;
      const deltaX = -(clientX - this.touchStart.x) * this.options.touchMultiplier;
      const deltaY = -(clientY - this.touchStart.y) * this.options.touchMultiplier;
      this.touchStart.x = clientX;
      this.touchStart.y = clientY;
      this.lastDelta = {
        x: deltaX,
        y: deltaY
      };
      this.emitter.emit("scroll", {
        deltaX,
        deltaY,
        event
      });
    };
    onTouchEnd = (event) => {
      this.emitter.emit("scroll", {
        deltaX: this.lastDelta.x,
        deltaY: this.lastDelta.y,
        event
      });
    };
    /** Event handler for 'wheel' event */
    onWheel = (event) => {
      let { deltaX, deltaY, deltaMode } = event;
      const multiplierX = getDeltaMultiplier(deltaMode, this.window.width);
      const multiplierY = getDeltaMultiplier(deltaMode, this.window.height);
      deltaX *= multiplierX;
      deltaY *= multiplierY;
      deltaX *= this.options.wheelMultiplier;
      deltaY *= this.options.wheelMultiplier;
      this.emitter.emit("scroll", {
        deltaX,
        deltaY,
        event
      });
    };
    onWindowResize = () => {
      this.window = {
        width: window.innerWidth,
        height: window.innerHeight
      };
    };
  };
  var defaultEasing = (t) => Math.min(1, 1.001 - 2 ** (-10 * t));
  var Lenis = class {
    _isScrolling = false;
    _isStopped = false;
    _isLocked = false;
    _preventNextNativeScrollEvent = false;
    _resetVelocityTimeout = null;
    _rafId = null;
    /**
    * Whether or not the user is touching the screen
    */
    isTouching;
    /**
    * The time in ms since the lenis instance was created
    */
    time = 0;
    /**
    * User data that will be forwarded through the scroll event
    *
    * @example
    * lenis.scrollTo(100, {
    *   userData: {
    *     foo: 'bar'
    *   }
    * })
    */
    userData = {};
    /**
    * The last velocity of the scroll
    */
    lastVelocity = 0;
    /**
    * The current velocity of the scroll
    */
    velocity = 0;
    /**
    * The direction of the scroll
    */
    direction = 0;
    /**
    * The options passed to the lenis instance
    */
    options;
    /**
    * The target scroll value
    */
    targetScroll;
    /**
    * The animated scroll value
    */
    animatedScroll;
    animate = new Animate();
    emitter = new Emitter();
    dimensions;
    virtualScroll;
    constructor({ wrapper = window, content = document.documentElement, eventsTarget = wrapper, smoothWheel = true, syncTouch = false, syncTouchLerp = 0.075, touchInertiaExponent = 1.7, duration, easing, lerp: lerp2 = 0.1, infinite = false, orientation = "vertical", gestureOrientation = orientation === "horizontal" ? "both" : "vertical", touchMultiplier = 1, wheelMultiplier = 1, autoResize = true, prevent, virtualScroll, overscroll = true, autoRaf = false, anchors = false, autoToggle = false, allowNestedScroll = false, __experimental__naiveDimensions = false, naiveDimensions = __experimental__naiveDimensions, stopInertiaOnNavigate = false } = {}) {
      window.lenisVersion = version;
      if (!window.lenis) window.lenis = {};
      window.lenis.version = version;
      if (orientation === "horizontal") window.lenis.horizontal = true;
      if (syncTouch === true) window.lenis.touch = true;
      if (!wrapper || wrapper === document.documentElement) wrapper = window;
      if (typeof duration === "number" && typeof easing !== "function") easing = defaultEasing;
      else if (typeof easing === "function" && typeof duration !== "number") duration = 1;
      this.options = {
        wrapper,
        content,
        eventsTarget,
        smoothWheel,
        syncTouch,
        syncTouchLerp,
        touchInertiaExponent,
        duration,
        easing,
        lerp: lerp2,
        infinite,
        gestureOrientation,
        orientation,
        touchMultiplier,
        wheelMultiplier,
        autoResize,
        prevent,
        virtualScroll,
        overscroll,
        autoRaf,
        anchors,
        autoToggle,
        allowNestedScroll,
        naiveDimensions,
        stopInertiaOnNavigate
      };
      this.dimensions = new Dimensions(wrapper, content, { autoResize });
      this.updateClassName();
      this.targetScroll = this.animatedScroll = this.actualScroll;
      this.options.wrapper.addEventListener("scroll", this.onNativeScroll);
      this.options.wrapper.addEventListener("scrollend", this.onScrollEnd, { capture: true });
      if (this.options.anchors || this.options.stopInertiaOnNavigate) this.options.wrapper.addEventListener("click", this.onClick);
      this.options.wrapper.addEventListener("pointerdown", this.onPointerDown);
      this.virtualScroll = new VirtualScroll(eventsTarget, {
        touchMultiplier,
        wheelMultiplier
      });
      this.virtualScroll.on("scroll", this.onVirtualScroll);
      if (this.options.autoToggle) {
        this.checkOverflow();
        this.rootElement.addEventListener("transitionend", this.onTransitionEnd);
      }
      if (this.options.autoRaf) this._rafId = requestAnimationFrame(this.raf);
    }
    /**
    * Destroy the lenis instance, remove all event listeners and clean up the class name
    */
    destroy() {
      this.emitter.destroy();
      this.options.wrapper.removeEventListener("scroll", this.onNativeScroll);
      this.options.wrapper.removeEventListener("scrollend", this.onScrollEnd, { capture: true });
      this.options.wrapper.removeEventListener("pointerdown", this.onPointerDown);
      if (this.options.anchors || this.options.stopInertiaOnNavigate) this.options.wrapper.removeEventListener("click", this.onClick);
      this.virtualScroll.destroy();
      this.dimensions.destroy();
      this.cleanUpClassName();
      if (this._rafId) cancelAnimationFrame(this._rafId);
    }
    on(event, callback) {
      return this.emitter.on(event, callback);
    }
    off(event, callback) {
      return this.emitter.off(event, callback);
    }
    onScrollEnd = (e) => {
      if (!(e instanceof CustomEvent)) {
        if (this.isScrolling === "smooth" || this.isScrolling === false) e.stopPropagation();
      }
    };
    dispatchScrollendEvent = () => {
      this.options.wrapper.dispatchEvent(new CustomEvent("scrollend", {
        bubbles: this.options.wrapper === window,
        detail: { lenisScrollEnd: true }
      }));
    };
    get overflow() {
      const property = this.isHorizontal ? "overflow-x" : "overflow-y";
      return getComputedStyle(this.rootElement)[property];
    }
    checkOverflow() {
      if (["hidden", "clip"].includes(this.overflow)) this.internalStop();
      else this.internalStart();
    }
    onTransitionEnd = (event) => {
      if (event.propertyName?.includes("overflow") && event.target === this.rootElement) this.checkOverflow();
    };
    setScroll(scroll) {
      if (this.isHorizontal) this.options.wrapper.scrollTo({
        left: scroll,
        behavior: "instant"
      });
      else this.options.wrapper.scrollTo({
        top: scroll,
        behavior: "instant"
      });
    }
    onClick = (event) => {
      const linkElementsUrls = event.composedPath().filter((node) => node instanceof HTMLAnchorElement && node.href).map((element) => new URL(element.href));
      const currentUrl = new URL(window.location.href);
      if (this.options.anchors) {
        const anchorElementUrl = linkElementsUrls.find((targetUrl) => currentUrl.host === targetUrl.host && currentUrl.pathname === targetUrl.pathname && targetUrl.hash);
        if (anchorElementUrl) {
          const options = typeof this.options.anchors === "object" && this.options.anchors ? this.options.anchors : void 0;
          const target = `#${anchorElementUrl.hash.split("#")[1]}`;
          this.scrollTo(target, options);
          return;
        }
      }
      if (this.options.stopInertiaOnNavigate) {
        if (linkElementsUrls.some((targetUrl) => currentUrl.host === targetUrl.host && currentUrl.pathname !== targetUrl.pathname)) {
          this.reset();
          return;
        }
      }
    };
    onPointerDown = (event) => {
      if (event.button === 1) this.reset();
    };
    onVirtualScroll = (data) => {
      if (typeof this.options.virtualScroll === "function" && this.options.virtualScroll(data) === false) return;
      const { deltaX, deltaY, event } = data;
      this.emitter.emit("virtual-scroll", {
        deltaX,
        deltaY,
        event
      });
      if (event.ctrlKey) return;
      if (event.lenisStopPropagation) return;
      const isTouch = event.type.includes("touch");
      const isWheel = event.type.includes("wheel");
      this.isTouching = event.type === "touchstart" || event.type === "touchmove";
      const isClickOrTap = deltaX === 0 && deltaY === 0;
      if (this.options.syncTouch && isTouch && event.type === "touchstart" && isClickOrTap && !this.isStopped && !this.isLocked) {
        this.reset();
        return;
      }
      const isUnknownGesture = this.options.gestureOrientation === "vertical" && deltaY === 0 || this.options.gestureOrientation === "horizontal" && deltaX === 0;
      if (isClickOrTap || isUnknownGesture) return;
      let composedPath = event.composedPath();
      composedPath = composedPath.slice(0, composedPath.indexOf(this.rootElement));
      const prevent = this.options.prevent;
      const gestureOrientation = Math.abs(deltaX) >= Math.abs(deltaY) ? "horizontal" : "vertical";
      if (composedPath.find((node) => node instanceof HTMLElement && (typeof prevent === "function" && prevent?.(node) || node.hasAttribute?.("data-lenis-prevent") || gestureOrientation === "vertical" && node.hasAttribute?.("data-lenis-prevent-vertical") || gestureOrientation === "horizontal" && node.hasAttribute?.("data-lenis-prevent-horizontal") || isTouch && node.hasAttribute?.("data-lenis-prevent-touch") || isWheel && node.hasAttribute?.("data-lenis-prevent-wheel") || this.options.allowNestedScroll && this.hasNestedScroll(node, {
        deltaX,
        deltaY
      })))) return;
      if (this.isStopped || this.isLocked) {
        if (event.cancelable) event.preventDefault();
        return;
      }
      if (!(this.options.syncTouch && isTouch || this.options.smoothWheel && isWheel)) {
        this.isScrolling = "native";
        this.animate.stop();
        event.lenisStopPropagation = true;
        return;
      }
      let delta = deltaY;
      if (this.options.gestureOrientation === "both") delta = Math.abs(deltaY) > Math.abs(deltaX) ? deltaY : deltaX;
      else if (this.options.gestureOrientation === "horizontal") delta = deltaX;
      if (!this.options.overscroll || this.options.infinite || this.options.wrapper !== window && this.limit > 0 && (this.animatedScroll > 0 && this.animatedScroll < this.limit || this.animatedScroll === 0 && deltaY > 0 || this.animatedScroll === this.limit && deltaY < 0)) event.lenisStopPropagation = true;
      if (event.cancelable) event.preventDefault();
      const isSyncTouch = isTouch && this.options.syncTouch;
      const hasTouchInertia = isTouch && event.type === "touchend";
      if (hasTouchInertia) delta = Math.sign(this.velocity) * Math.abs(this.velocity) ** this.options.touchInertiaExponent;
      this.scrollTo(this.targetScroll + delta, {
        programmatic: false,
        ...isSyncTouch ? { lerp: hasTouchInertia ? this.options.syncTouchLerp : 1 } : {
          lerp: this.options.lerp,
          duration: this.options.duration,
          easing: this.options.easing
        }
      });
    };
    /**
    * Force lenis to recalculate the dimensions
    */
    resize() {
      this.dimensions.resize();
      this.animatedScroll = this.targetScroll = this.actualScroll;
      this.emit();
    }
    emit() {
      this.emitter.emit("scroll", this);
    }
    onNativeScroll = () => {
      if (this._resetVelocityTimeout !== null) {
        clearTimeout(this._resetVelocityTimeout);
        this._resetVelocityTimeout = null;
      }
      if (this._preventNextNativeScrollEvent) {
        this._preventNextNativeScrollEvent = false;
        return;
      }
      if (this.isScrolling === false || this.isScrolling === "native") {
        const lastScroll = this.animatedScroll;
        this.animatedScroll = this.targetScroll = this.actualScroll;
        this.lastVelocity = this.velocity;
        this.velocity = this.animatedScroll - lastScroll;
        this.direction = Math.sign(this.animatedScroll - lastScroll);
        if (!this.isStopped) this.isScrolling = "native";
        this.emit();
        if (this.velocity !== 0) this._resetVelocityTimeout = setTimeout(() => {
          this.lastVelocity = this.velocity;
          this.velocity = 0;
          this.isScrolling = false;
          this.emit();
        }, 400);
      }
    };
    reset() {
      this.isLocked = false;
      this.isScrolling = false;
      this.animatedScroll = this.targetScroll = this.actualScroll;
      this.lastVelocity = this.velocity = 0;
      this.animate.stop();
    }
    /**
    * Start lenis scroll after it has been stopped
    */
    start() {
      if (!this.isStopped) return;
      if (this.options.autoToggle) {
        this.rootElement.style.removeProperty("overflow");
        return;
      }
      this.internalStart();
    }
    internalStart() {
      if (!this.isStopped) return;
      this.reset();
      this.isStopped = false;
      this.emit();
    }
    /**
    * Stop lenis scroll
    */
    stop() {
      if (this.isStopped) return;
      if (this.options.autoToggle) {
        this.rootElement.style.setProperty("overflow", "clip");
        return;
      }
      this.internalStop();
    }
    internalStop() {
      if (this.isStopped) return;
      this.reset();
      this.isStopped = true;
      this.emit();
    }
    /**
    * RequestAnimationFrame for lenis
    *
    * @param time The time in ms from an external clock like `requestAnimationFrame` or Tempus
    */
    raf = (time) => {
      const deltaTime = time - (this.time || time);
      this.time = time;
      this.animate.advance(deltaTime * 1e-3);
      if (this.options.autoRaf) this._rafId = requestAnimationFrame(this.raf);
    };
    /**
    * Scroll to a target value
    *
    * @param target The target value to scroll to
    * @param options The options for the scroll
    *
    * @example
    * lenis.scrollTo(100, {
    *   offset: 100,
    *   duration: 1,
    *   easing: (t) => 1 - Math.cos((t * Math.PI) / 2),
    *   lerp: 0.1,
    *   onStart: () => {
    *     console.log('onStart')
    *   },
    *   onComplete: () => {
    *     console.log('onComplete')
    *   },
    * })
    */
    scrollTo(_target, { offset = 0, immediate = false, lock = false, programmatic = true, lerp: lerp2 = programmatic ? this.options.lerp : void 0, duration = programmatic ? this.options.duration : void 0, easing = programmatic ? this.options.easing : void 0, onStart, onComplete, force = false, userData } = {}) {
      if ((this.isStopped || this.isLocked) && !force) return;
      let target = _target;
      let adjustedOffset = offset;
      if (typeof target === "string" && [
        "top",
        "left",
        "start",
        "#"
      ].includes(target)) target = 0;
      else if (typeof target === "string" && [
        "bottom",
        "right",
        "end"
      ].includes(target)) target = this.limit;
      else {
        let node = null;
        if (typeof target === "string") {
          node = document.querySelector(target);
          if (!node) if (target === "#top") target = 0;
          else console.warn("Lenis: Target not found", target);
        } else if (target instanceof HTMLElement && target?.nodeType) node = target;
        if (node) {
          if (this.options.wrapper !== window) {
            const wrapperRect = this.rootElement.getBoundingClientRect();
            adjustedOffset -= this.isHorizontal ? wrapperRect.left : wrapperRect.top;
          }
          const rect = node.getBoundingClientRect();
          const targetStyle = getComputedStyle(node);
          const scrollMargin = this.isHorizontal ? Number.parseFloat(targetStyle.scrollMarginLeft) : Number.parseFloat(targetStyle.scrollMarginTop);
          const containerStyle = getComputedStyle(this.rootElement);
          const scrollPadding = this.isHorizontal ? Number.parseFloat(containerStyle.scrollPaddingLeft) : Number.parseFloat(containerStyle.scrollPaddingTop);
          target = (this.isHorizontal ? rect.left : rect.top) + this.animatedScroll - (Number.isNaN(scrollMargin) ? 0 : scrollMargin) - (Number.isNaN(scrollPadding) ? 0 : scrollPadding);
        }
      }
      if (typeof target !== "number") return;
      target += adjustedOffset;
      target = Math.round(target);
      if (this.options.infinite) {
        if (programmatic) {
          this.targetScroll = this.animatedScroll = this.scroll;
          const distance = target - this.animatedScroll;
          if (distance > this.limit / 2) target -= this.limit;
          else if (distance < -this.limit / 2) target += this.limit;
        }
      } else target = clamp(0, target, this.limit);
      if (target === this.targetScroll) {
        onStart?.(this);
        onComplete?.(this);
        return;
      }
      this.userData = userData ?? {};
      if (immediate) {
        this.animatedScroll = this.targetScroll = target;
        this.setScroll(this.scroll);
        this.reset();
        this.preventNextNativeScrollEvent();
        this.emit();
        onComplete?.(this);
        this.userData = {};
        requestAnimationFrame(() => {
          this.dispatchScrollendEvent();
        });
        return;
      }
      if (!programmatic) this.targetScroll = target;
      if (typeof duration === "number" && typeof easing !== "function") easing = defaultEasing;
      else if (typeof easing === "function" && typeof duration !== "number") duration = 1;
      this.animate.fromTo(this.animatedScroll, target, {
        duration,
        easing,
        lerp: lerp2,
        onStart: () => {
          if (lock) this.isLocked = true;
          this.isScrolling = "smooth";
          onStart?.(this);
        },
        onUpdate: (value, completed) => {
          this.isScrolling = "smooth";
          this.lastVelocity = this.velocity;
          this.velocity = value - this.animatedScroll;
          this.direction = Math.sign(this.velocity);
          this.animatedScroll = value;
          this.setScroll(this.scroll);
          if (programmatic) this.targetScroll = value;
          if (!completed) this.emit();
          if (completed) {
            this.reset();
            this.emit();
            onComplete?.(this);
            this.userData = {};
            requestAnimationFrame(() => {
              this.dispatchScrollendEvent();
            });
            this.preventNextNativeScrollEvent();
          }
        }
      });
    }
    preventNextNativeScrollEvent() {
      this._preventNextNativeScrollEvent = true;
      requestAnimationFrame(() => {
        this._preventNextNativeScrollEvent = false;
      });
    }
    hasNestedScroll(node, { deltaX, deltaY }) {
      const time = Date.now();
      if (!node._lenis) node._lenis = {};
      const cache = node._lenis;
      let hasOverflowX;
      let hasOverflowY;
      let isScrollableX;
      let isScrollableY;
      let hasOverscrollBehaviorX;
      let hasOverscrollBehaviorY;
      let scrollWidth;
      let scrollHeight;
      let clientWidth;
      let clientHeight;
      if (time - (cache.time ?? 0) > 2e3) {
        cache.time = Date.now();
        const computedStyle = window.getComputedStyle(node);
        cache.computedStyle = computedStyle;
        hasOverflowX = [
          "auto",
          "overlay",
          "scroll"
        ].includes(computedStyle.overflowX);
        hasOverflowY = [
          "auto",
          "overlay",
          "scroll"
        ].includes(computedStyle.overflowY);
        hasOverscrollBehaviorX = ["auto"].includes(computedStyle.overscrollBehaviorX);
        hasOverscrollBehaviorY = ["auto"].includes(computedStyle.overscrollBehaviorY);
        cache.hasOverflowX = hasOverflowX;
        cache.hasOverflowY = hasOverflowY;
        if (!(hasOverflowX || hasOverflowY)) return false;
        scrollWidth = node.scrollWidth;
        scrollHeight = node.scrollHeight;
        clientWidth = node.clientWidth;
        clientHeight = node.clientHeight;
        isScrollableX = scrollWidth > clientWidth;
        isScrollableY = scrollHeight > clientHeight;
        cache.isScrollableX = isScrollableX;
        cache.isScrollableY = isScrollableY;
        cache.scrollWidth = scrollWidth;
        cache.scrollHeight = scrollHeight;
        cache.clientWidth = clientWidth;
        cache.clientHeight = clientHeight;
        cache.hasOverscrollBehaviorX = hasOverscrollBehaviorX;
        cache.hasOverscrollBehaviorY = hasOverscrollBehaviorY;
      } else {
        isScrollableX = cache.isScrollableX;
        isScrollableY = cache.isScrollableY;
        hasOverflowX = cache.hasOverflowX;
        hasOverflowY = cache.hasOverflowY;
        scrollWidth = cache.scrollWidth;
        scrollHeight = cache.scrollHeight;
        clientWidth = cache.clientWidth;
        clientHeight = cache.clientHeight;
        hasOverscrollBehaviorX = cache.hasOverscrollBehaviorX;
        hasOverscrollBehaviorY = cache.hasOverscrollBehaviorY;
      }
      if (!(hasOverflowX && isScrollableX || hasOverflowY && isScrollableY)) return false;
      const orientation = Math.abs(deltaX) >= Math.abs(deltaY) ? "horizontal" : "vertical";
      let scroll;
      let maxScroll;
      let delta;
      let hasOverflow;
      let isScrollable;
      let hasOverscrollBehavior;
      if (orientation === "horizontal") {
        scroll = Math.round(node.scrollLeft);
        maxScroll = scrollWidth - clientWidth;
        delta = deltaX;
        hasOverflow = hasOverflowX;
        isScrollable = isScrollableX;
        hasOverscrollBehavior = hasOverscrollBehaviorX;
      } else if (orientation === "vertical") {
        scroll = Math.round(node.scrollTop);
        maxScroll = scrollHeight - clientHeight;
        delta = deltaY;
        hasOverflow = hasOverflowY;
        isScrollable = isScrollableY;
        hasOverscrollBehavior = hasOverscrollBehaviorY;
      } else return false;
      if (!hasOverscrollBehavior && (scroll >= maxScroll || scroll <= 0)) return true;
      return (delta > 0 ? scroll < maxScroll : scroll > 0) && hasOverflow && isScrollable;
    }
    /**
    * The root element on which lenis is instanced
    */
    get rootElement() {
      return this.options.wrapper === window ? document.documentElement : this.options.wrapper;
    }
    /**
    * The limit which is the maximum scroll value
    */
    get limit() {
      if (this.options.naiveDimensions) {
        if (this.isHorizontal) return this.rootElement.scrollWidth - this.rootElement.clientWidth;
        return this.rootElement.scrollHeight - this.rootElement.clientHeight;
      }
      return this.dimensions.limit[this.isHorizontal ? "x" : "y"];
    }
    /**
    * Whether or not the scroll is horizontal
    */
    get isHorizontal() {
      return this.options.orientation === "horizontal";
    }
    /**
    * The actual scroll value
    */
    get actualScroll() {
      const wrapper = this.options.wrapper;
      return this.isHorizontal ? wrapper.scrollX ?? wrapper.scrollLeft : wrapper.scrollY ?? wrapper.scrollTop;
    }
    /**
    * The current scroll value
    */
    get scroll() {
      return this.options.infinite ? modulo(this.animatedScroll, this.limit) : this.animatedScroll;
    }
    /**
    * The progress of the scroll relative to the limit
    */
    get progress() {
      return this.limit === 0 ? 1 : this.scroll / this.limit;
    }
    /**
    * Current scroll state
    */
    get isScrolling() {
      return this._isScrolling;
    }
    set isScrolling(value) {
      if (this._isScrolling !== value) {
        this._isScrolling = value;
        this.updateClassName();
      }
    }
    /**
    * Check if lenis is stopped
    */
    get isStopped() {
      return this._isStopped;
    }
    set isStopped(value) {
      if (this._isStopped !== value) {
        this._isStopped = value;
        this.updateClassName();
      }
    }
    /**
    * Check if lenis is locked
    */
    get isLocked() {
      return this._isLocked;
    }
    set isLocked(value) {
      if (this._isLocked !== value) {
        this._isLocked = value;
        this.updateClassName();
      }
    }
    /**
    * Check if lenis is smooth scrolling
    */
    get isSmooth() {
      return this.isScrolling === "smooth";
    }
    /**
    * The class name applied to the wrapper element
    */
    get className() {
      let className = "lenis";
      if (this.options.autoToggle) className += " lenis-autoToggle";
      if (this.isStopped) className += " lenis-stopped";
      if (this.isLocked) className += " lenis-locked";
      if (this.isScrolling) className += " lenis-scrolling";
      if (this.isScrolling === "smooth") className += " lenis-smooth";
      return className;
    }
    updateClassName() {
      this.cleanUpClassName();
      this.rootElement.className = `${this.rootElement.className} ${this.className}`.trim();
    }
    cleanUpClassName() {
      this.rootElement.className = this.rootElement.className.replace(/lenis(-\w+)?/g, "").trim();
    }
  };

  // node_modules/lenis/dist/lenis-snap.mjs
  function debounce2(callback, delay) {
    let timer;
    return function(...args) {
      clearTimeout(timer);
      timer = setTimeout(() => {
        timer = void 0;
        callback.apply(this, args);
      }, delay);
    };
  }
  function removeParentSticky(element) {
    if (getComputedStyle(element).position === "sticky") {
      element.style.setProperty("position", "static");
      element.dataset.sticky = "true";
    }
    if (element.offsetParent) removeParentSticky(element.offsetParent);
  }
  function addParentSticky(element) {
    if (element?.dataset?.sticky === "true") {
      element.style.removeProperty("position");
      delete element.dataset.sticky;
    }
    if (element.offsetParent) addParentSticky(element.offsetParent);
  }
  function offsetTop(element, accumulator = 0) {
    const top = accumulator + element.offsetTop;
    if (element.offsetParent) return offsetTop(element.offsetParent, top);
    return top;
  }
  function offsetLeft(element, accumulator = 0) {
    const left = accumulator + element.offsetLeft;
    if (element.offsetParent) return offsetLeft(element.offsetParent, left);
    return left;
  }
  function scrollTop(element, accumulator = 0) {
    const top = accumulator + element.scrollTop;
    if (element.offsetParent) return scrollTop(element.offsetParent, top);
    return top + window.scrollY;
  }
  function scrollLeft(element, accumulator = 0) {
    const left = accumulator + element.scrollLeft;
    if (element.offsetParent) return scrollLeft(element.offsetParent, left);
    return left + window.scrollX;
  }
  var SnapElement = class {
    element;
    options;
    align;
    rect = {};
    wrapperResizeObserver;
    resizeObserver;
    debouncedWrapperResize;
    constructor(element, { align = ["start"], ignoreSticky = true, ignoreTransform = false } = {}) {
      this.element = element;
      this.options = {
        align,
        ignoreSticky,
        ignoreTransform
      };
      this.align = [align].flat();
      this.debouncedWrapperResize = debounce2(this.onWrapperResize, 500);
      this.wrapperResizeObserver = new ResizeObserver(this.debouncedWrapperResize);
      this.wrapperResizeObserver.observe(document.body);
      this.onWrapperResize();
      this.resizeObserver = new ResizeObserver(this.onResize);
      this.resizeObserver.observe(this.element);
      this.setRect({
        width: this.element.offsetWidth,
        height: this.element.offsetHeight
      });
    }
    destroy() {
      this.wrapperResizeObserver.disconnect();
      this.resizeObserver.disconnect();
    }
    setRect({ top, left, width, height, element } = {}) {
      top = top ?? this.rect.top;
      left = left ?? this.rect.left;
      width = width ?? this.rect.width;
      height = height ?? this.rect.height;
      element = element ?? this.rect.element;
      if (top === this.rect.top && left === this.rect.left && width === this.rect.width && height === this.rect.height && element === this.rect.element) return;
      this.rect.top = top;
      this.rect.y = top;
      this.rect.width = width;
      this.rect.height = height;
      this.rect.left = left;
      this.rect.x = left;
      this.rect.bottom = top + height;
      this.rect.right = left + width;
    }
    onWrapperResize = () => {
      let top;
      let left;
      if (this.options.ignoreSticky) removeParentSticky(this.element);
      if (this.options.ignoreTransform) {
        top = offsetTop(this.element);
        left = offsetLeft(this.element);
      } else {
        const rect = this.element.getBoundingClientRect();
        top = rect.top + scrollTop(this.element);
        left = rect.left + scrollLeft(this.element);
      }
      if (this.options.ignoreSticky) addParentSticky(this.element);
      this.setRect({
        top,
        left
      });
    };
    onResize = ([entry]) => {
      if (!entry?.borderBoxSize[0]) return;
      const width = entry.borderBoxSize[0].inlineSize;
      const height = entry.borderBoxSize[0].blockSize;
      this.setRect({
        width,
        height
      });
    };
  };
  var index = 0;
  function uid() {
    return index++;
  }
  var Snap = class {
    options;
    elements = /* @__PURE__ */ new Map();
    snaps = /* @__PURE__ */ new Map();
    viewport = {
      width: window.innerWidth,
      height: window.innerHeight
    };
    isStopped = false;
    onSnapDebounced;
    currentSnapIndex;
    constructor(lenis2, { type = "proximity", lerp: lerp2, easing, duration, distanceThreshold = "50%", debounce: debounceDelay = 500, onSnapStart, onSnapComplete } = {}) {
      this.lenis = lenis2;
      if (!window.lenis) window.lenis = {};
      window.lenis.snap = true;
      this.options = {
        type,
        lerp: lerp2,
        easing,
        duration,
        distanceThreshold,
        debounce: debounceDelay,
        onSnapStart,
        onSnapComplete
      };
      this.onWindowResize();
      window.addEventListener("resize", this.onWindowResize);
      this.onSnapDebounced = debounce2(this.onSnap, this.options.debounce);
      this.lenis.on("virtual-scroll", this.onSnapDebounced);
    }
    /**
    * Destroy the snap instance
    */
    destroy() {
      this.lenis.off("virtual-scroll", this.onSnapDebounced);
      window.removeEventListener("resize", this.onWindowResize);
      this.elements.forEach((element) => {
        element.destroy();
      });
    }
    /**
    * Start the snap after it has been stopped
    */
    start() {
      this.isStopped = false;
    }
    /**
    * Stop the snap
    */
    stop() {
      this.isStopped = true;
    }
    /**
    * Add a snap to the snap instance
    *
    * @param value The value to snap to
    * @param userData User data that will be forwarded through the snap event
    * @returns Unsubscribe function
    */
    add(value) {
      const id = uid();
      this.snaps.set(id, { value });
      return () => this.snaps.delete(id);
    }
    /**
    * Add an element to the snap instance
    *
    * @param element The element to add
    * @param options The options for the element
    * @returns Unsubscribe function
    */
    addElement(element, options = {}) {
      const id = uid();
      this.elements.set(id, new SnapElement(element, options));
      return () => this.elements.delete(id);
    }
    addElements(elements, options = {}) {
      const map = [...elements].map((element) => this.addElement(element, options));
      return () => {
        map.forEach((remove) => {
          remove();
        });
      };
    }
    onWindowResize = () => {
      this.viewport.width = window.innerWidth;
      this.viewport.height = window.innerHeight;
    };
    computeSnaps = () => {
      const { isHorizontal } = this.lenis;
      let snaps = [...this.snaps.values()];
      this.elements.forEach(({ rect, align }) => {
        let value;
        align.forEach((align2) => {
          if (align2 === "start") value = rect.top;
          else if (align2 === "center") value = isHorizontal ? rect.left + rect.width / 2 - this.viewport.width / 2 : rect.top + rect.height / 2 - this.viewport.height / 2;
          else if (align2 === "end") value = isHorizontal ? rect.left + rect.width - this.viewport.width : rect.top + rect.height - this.viewport.height;
          if (typeof value === "number") snaps.push({ value: Math.ceil(value) });
        });
      });
      snaps = snaps.sort((a, b) => Math.abs(a.value) - Math.abs(b.value));
      return snaps;
    };
    previous() {
      this.goTo((this.currentSnapIndex ?? 0) - 1);
    }
    next() {
      this.goTo((this.currentSnapIndex ?? 0) + 1);
    }
    goTo(index2) {
      const snaps = this.computeSnaps();
      if (snaps.length === 0) return;
      this.currentSnapIndex = Math.max(0, Math.min(index2, snaps.length - 1));
      const currentSnap = snaps[this.currentSnapIndex];
      if (currentSnap === void 0) return;
      this.lenis.scrollTo(currentSnap.value, {
        duration: this.options.duration,
        easing: this.options.easing,
        lerp: this.options.lerp,
        lock: this.options.type === "lock",
        userData: { initiator: "snap" },
        onStart: () => {
          this.options.onSnapStart?.({
            index: this.currentSnapIndex,
            ...currentSnap
          });
        },
        onComplete: () => {
          this.options.onSnapComplete?.({
            index: this.currentSnapIndex,
            ...currentSnap
          });
        }
      });
    }
    get distanceThreshold() {
      let distanceThreshold = Number.POSITIVE_INFINITY;
      if (this.options.type === "mandatory") return Number.POSITIVE_INFINITY;
      const { isHorizontal } = this.lenis;
      const axis = isHorizontal ? "width" : "height";
      if (typeof this.options.distanceThreshold === "string" && this.options.distanceThreshold.endsWith("%")) distanceThreshold = Number(this.options.distanceThreshold.replace("%", "")) / 100 * this.viewport[axis];
      else if (typeof this.options.distanceThreshold === "number") distanceThreshold = this.options.distanceThreshold;
      else distanceThreshold = this.viewport[axis];
      return distanceThreshold;
    }
    onSnap = (e) => {
      if (this.isStopped) return;
      if (e.event.type === "touchmove") return;
      if (this.options.type === "lock" && this.lenis.userData?.initiator === "snap") return;
      let { scroll, isHorizontal } = this.lenis;
      const delta = isHorizontal ? e.deltaX : e.deltaY;
      scroll = Math.ceil(this.lenis.scroll + delta);
      const snaps = this.computeSnaps();
      if (snaps.length === 0) return;
      let snapIndex;
      const prevSnapIndex = snaps.findLastIndex(({ value }) => value < scroll);
      const nextSnapIndex = snaps.findIndex(({ value }) => value > scroll);
      if (this.options.type === "lock") {
        if (delta > 0) snapIndex = nextSnapIndex;
        else if (delta < 0) snapIndex = prevSnapIndex;
      } else {
        const prevSnap = snaps[prevSnapIndex];
        const distanceToPrevSnap = prevSnap ? Math.abs(scroll - prevSnap.value) : Number.POSITIVE_INFINITY;
        const nextSnap = snaps[nextSnapIndex];
        snapIndex = distanceToPrevSnap < (nextSnap ? Math.abs(scroll - nextSnap.value) : Number.POSITIVE_INFINITY) ? prevSnapIndex : nextSnapIndex;
      }
      if (snapIndex === void 0) return;
      if (snapIndex === -1) return;
      snapIndex = Math.max(0, Math.min(snapIndex, snaps.length - 1));
      const snap2 = snaps[snapIndex];
      if (Math.abs(scroll - snap2.value) <= this.distanceThreshold) this.goTo(snapIndex);
    };
    resize() {
      this.elements.forEach((element) => {
        element.onWrapperResize();
      });
    }
  };

  // assets/js/telar-story/panels.js
  function initializePanels() {
    document.addEventListener("click", function(e) {
      const trigger = e.target.closest('[data-panel="layer1"]');
      if (trigger) {
        const stepNumber = trigger.dataset.step;
        state.panelStack = [];
        openPanel("layer1", stepNumber);
      }
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
      const glossaryLinks = contentElement.querySelectorAll(".glossary-link");
      glossaryLinks.forEach((el, i) => {
        el.dataset.deepLinkN = i + 1;
      });
      glossaryLinks.forEach((el) => {
        el.addEventListener("click", () => {
          writeHashWithGlossary(parseInt(el.dataset.deepLinkN, 10));
        });
      });
      if (window.telarRenderLatex) {
        window.telarRenderLatex(contentElement);
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
      writeHash();
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
    const stackAfterClose = state.panelStack.filter((p) => p.type !== panelType);
    const savedStack = state.panelStack;
    state.panelStack = stackAfterClose;
    writeHash();
    state.panelStack = savedStack;
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
    state.panelStack = [];
    state.isPanelOpen = false;
    writeHash();
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
      }, step.object);
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
        }, step.object),
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
  function formatPanelContent(panelData, objectId) {
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
      const objectsData = window.objectsData || [];
      const panelObj = objectId ? objectsData.find((o) => o.object_id === objectId) || {} : {};
      const panelAlt = panelObj.alt_text || panelObj.title || objectId || "Panel image";
      html += `<img src="${mediaUrl}" alt="${panelAlt}" class="img-fluid">`;
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
    const backdrop = document.createElement("div");
    backdrop.id = "panel-backdrop";
    backdrop.style.cssText = `
    position: fixed;
    inset: -50px;
    background: rgba(0, 0, 0, 0.025);
    z-index: 9900;
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
    if (state.lenis) state.lenis.stop();
    const backdrop = document.getElementById("panel-backdrop");
    if (backdrop) {
      backdrop.style.display = "block";
    }
  }
  function deactivateScrollLock() {
    state.scrollLockActive = false;
    if (state.lenis) state.lenis.start();
    const backdrop = document.getElementById("panel-backdrop");
    if (backdrop) {
      backdrop.style.display = "none";
    }
  }

  // assets/js/telar-story/deep-link.js
  var _isScrollDrivenHashUpdate = false;
  var FRAGMENT_RE = /^#s(\d+)(?:l(\d+)(?:(g|ps)(\d+))?)?$/;
  function parseFragment(hash) {
    if (!hash || hash === "#") return null;
    const m = FRAGMENT_RE.exec(hash);
    if (!m) return null;
    return {
      step: parseInt(m[1], 10),
      // 1-based step number
      layer: m[2] ? parseInt(m[2], 10) : null,
      subType: m[3] || null,
      // 'g' or 'ps'
      subN: m[4] ? parseInt(m[4], 10) : null
    };
  }
  function writeHash() {
    _writeHashFragment(null, null);
  }
  function writeHashWithGlossary(n) {
    _writeHashFragment("g", n);
  }
  function _writeHashFragment(subType, subN) {
    const idx = state.currentIndex;
    let hash = "";
    if (idx >= 0) {
      hash = `#s${idx + 1}`;
      if (state.panelStack.length > 0) {
        for (let i = state.panelStack.length - 1; i >= 0; i--) {
          const layerMatch = state.panelStack[i].type.match(/^layer(\d+)$/);
          if (layerMatch) {
            hash += `l${layerMatch[1]}`;
            if (subType !== null && subN !== null) {
              hash += `${subType}${subN}`;
            }
            break;
          }
        }
      }
    }
    _isScrollDrivenHashUpdate = true;
    if (hash) {
      history.replaceState(null, "", hash);
    } else {
      history.replaceState(null, "", window.location.pathname + window.location.search);
    }
    Promise.resolve().then(() => {
      _isScrollDrivenHashUpdate = false;
    });
  }
  function applyDeepLinkOnLoad() {
    const parsed = parseFragment(window.location.hash);
    if (!parsed) return;
    const targetIndex = Math.min(parsed.step - 1, state.steps.length - 1);
    if (targetIndex < 0) return;
    if (state.lenis) {
      const targetPx = (targetIndex + 1) * window.innerHeight;
      state.lenis.stop();
      document.documentElement.scrollTop = targetPx;
      state.lenis.animatedScroll = targetPx;
      state.lenis.targetScroll = targetPx;
      activateCard(targetIndex, "forward");
      state.currentIndex = targetIndex;
      state.scrollPosition = targetIndex + 1;
      requestAnimationFrame(() => {
        state.lenis.start();
      });
    } else {
      state.currentMobileStep = targetIndex;
      state.mobileInIntro = false;
      activateCard(targetIndex, "forward");
      state.steps.forEach((step, i) => {
        if (i === targetIndex) {
          step.classList.add("mobile-active");
        } else {
          step.classList.remove("mobile-active");
        }
      });
    }
    if (parsed.layer !== null) {
      const stepNumber = state.steps[targetIndex]?.dataset?.step;
      if (stepNumber) {
        setTimeout(() => {
          openPanel("layer" + parsed.layer, stepNumber);
        }, 100);
      }
    }
    if (parsed.layer !== null && parsed.subType === "g" && parsed.subN !== null) {
      const stepNumber = state.steps[targetIndex]?.dataset?.step;
      if (stepNumber) {
        setTimeout(() => {
          const panelContent = document.getElementById("panel-layer" + parsed.layer + "-content");
          if (panelContent) {
            const target = panelContent.querySelector(`[data-deep-link-n="${parsed.subN}"]`);
            if (target) target.click();
          }
        }, 300);
      }
    }
  }

  // assets/js/telar-story/scroll-engine.js
  var lenis;
  var snap;
  var snapRemovers = [];
  var rafId;
  var dwellTimer;
  var totalPositions = 0;
  var keyboardNavInFlight = false;
  function initScrollEngine(stepCount) {
    const surface = document.querySelector(".scroll-surface");
    const cardStack = document.querySelector(".card-stack");
    if (!surface || !cardStack) {
      console.error("scroll-engine: .scroll-surface or .card-stack not found in DOM");
      return;
    }
    state.steps = Array.from(document.querySelectorAll(".story-step"));
    history.scrollRestoration = "manual";
    totalPositions = stepCount + 1;
    surface.style.height = `${totalPositions * window.innerHeight}px`;
    lenis = new Lenis({
      lerp: 0.06,
      // lower = heavier, more contemplative feel
      smoothWheel: true,
      wheelMultiplier: 0.5,
      // scroll sensitivity
      autoRaf: false,
      // we drive the rAF loop manually
      prevent: (node) => node.closest(".offcanvas") !== null || node.closest("[data-telar-panel]") !== null
      // let wheel events pass through inside open panels
    });
    snap = new Snap(lenis, {
      type: "lock",
      velocityThreshold: 0.5,
      debounce: 150,
      distanceThreshold: "20%",
      lerp: 0.08,
      onSnapStart: () => {
        state.isSnapping = true;
      },
      onSnapComplete: () => {
        state.isSnapping = false;
        const finalPosition = lenis.animatedScroll / window.innerHeight;
        updateScrollPosition(finalPosition);
        writeHash();
        lenis.stop();
        dwellTimer = setTimeout(() => {
          if (!state.isPanelOpen) {
            lenis.start();
          }
          dwellTimer = null;
        }, 500);
      }
    });
    registerSnapPoints(totalPositions);
    let scrubEndTimer;
    lenis.on("virtual-scroll", () => {
      cardStack.classList.add("is-scrubbing");
      clearTimeout(scrubEndTimer);
      scrubEndTimer = setTimeout(() => cardStack.classList.remove("is-scrubbing"), 100);
    });
    lenis.on("scroll", (l) => {
      const position = l.animatedScroll / window.innerHeight;
      updateScrollPosition(position);
    });
    rafId = requestAnimationFrame(function raf(time) {
      lenis.raf(time);
      rafId = requestAnimationFrame(raf);
    });
    window.addEventListener("resize", () => {
      surface.style.height = `${totalPositions * window.innerHeight}px`;
      lenis.resize();
      registerSnapPoints(totalPositions);
    });
    state.lenis = lenis;
    state.snap = snap;
    initKeyboardNavigation();
    initializeLoadingShimmer();
  }
  function registerSnapPoints(count) {
    snapRemovers.forEach((fn) => fn());
    snapRemovers = [];
    for (let i = 0; i < count; i++) {
      snapRemovers.push(snap.add(i * window.innerHeight));
    }
  }
  function advanceToStep(targetIndex) {
    if (targetIndex < 0 || targetIndex >= state.steps.length) return;
    const lenisInstance = state.lenis || lenis;
    if (!lenisInstance) return;
    const targetPx = (targetIndex + 1) * window.innerHeight;
    lenisInstance.scrollTo(targetPx, {
      duration: 0.5,
      easing: (t) => 1 - Math.pow(1 - t, 3)
      // ease-out cubic
    });
  }
  function keyboardNav(direction) {
    if (!lenis) return;
    if (dwellTimer) {
      clearTimeout(dwellTimer);
      dwellTimer = null;
      lenis.start();
    }
    const vh = window.innerHeight;
    const position = lenis.animatedScroll / vh;
    const isExact = Math.abs(position - Math.round(position)) < 0.01;
    const rounded = Math.round(position);
    let target;
    if (direction === "forward") {
      target = isExact ? rounded + 1 : Math.ceil(position);
    } else {
      target = isExact ? rounded - 1 : Math.floor(position);
    }
    target = Math.max(0, Math.min(target, totalPositions - 1));
    if (target === rounded && isExact) return;
    if (direction === "backward") {
      const contentStepIndex = Math.floor(Math.max(0, position - 1));
      const scrubCard = state.textCards?.[contentStepIndex + 1];
      if (scrubCard && !scrubCard.classList.contains("is-active")) {
        const rot = parseFloat(scrubCard.dataset.messinessRot || 0);
        const offX = parseFloat(scrubCard.dataset.messinessOffX || 0);
        const offY = parseFloat(scrubCard.dataset.messinessOffY || 0);
        scrubCard.style.transform = `translateY(100vh) rotate(${rot}deg) translate(${offX}px, ${offY}px)`;
      }
    }
    if (snap) snap.currentSnapIndex = target;
    const targetStep = target - 1;
    if (targetStep >= 0 && targetStep !== state.currentIndex) {
      state.scrollDriven = true;
      activateCard(targetStep, direction);
      state.scrollDriven = false;
      state.currentIndex = targetStep;
      updateViewerInfo(targetStep);
    }
    keyboardNavInFlight = true;
    lenis.scrollTo(target * vh, {
      force: true,
      duration: 0.8,
      easing: (t) => 1 - Math.pow(1 - t, 3),
      // ease-out cubic
      onComplete: () => {
        keyboardNavInFlight = false;
        writeHash();
      }
    });
  }
  function getScrollEngineState() {
    return {
      lenis,
      snap,
      position: state.scrollPosition,
      progress: state.scrollProgress
    };
  }
  function updateScrollPosition(position) {
    const contentPos = position - 1;
    const maxContent = state.steps.length - 1;
    state.scrollPosition = position;
    if (position < 1) {
      state.scrollProgress = 0;
      if (state.currentIndex >= 0 && !keyboardNavInFlight) {
        goToStep(-1, "backward");
      }
      const progress2 = position;
      const firstCard = state.textCards?.[0];
      if (firstCard) {
        const rot = parseFloat(firstCard.dataset.messinessRot || 0);
        const offX = parseFloat(firstCard.dataset.messinessOffX || 0);
        const offY = parseFloat(firstCard.dataset.messinessOffY || 0);
        const translateY = (1 - progress2) * 100;
        firstCard.style.transform = `translateY(${translateY}vh) rotate(${rot}deg) translate(${offX}px, ${offY}px)`;
      }
      const firstPlate = state.viewerPlates?.[0];
      if (firstPlate) {
        const plateTranslateY = (1 - progress2) * 100;
        firstPlate.style.transform = `translateY(${plateTranslateY}%)`;
      }
      return;
    }
    const clamped = Math.min(maxContent, contentPos);
    const stepIndex = Math.floor(clamped);
    const progress = clamped - stepIndex;
    state.scrollProgress = progress;
    setCardProgress(stepIndex, progress);
    lerpIiifPosition(stepIndex, progress, window.storyData?.steps || []);
    if (stepIndex !== state.currentIndex && !keyboardNavInFlight) {
      const direction = stepIndex > state.currentIndex ? "forward" : "backward";
      state.scrollDriven = true;
      activateCard(stepIndex, direction);
      state.scrollDriven = false;
      state.currentIndex = stepIndex;
      updateViewerInfo(stepIndex);
    }
  }

  // assets/js/telar-story/navigation.js
  function initKeyboardNavigation() {
    document.addEventListener("keydown", handleKeyboard);
  }
  function goToStep(newIndex, direction = "forward") {
    if (newIndex < -1 || newIndex >= state.steps.length) return;
    state.currentIndex = newIndex;
    if (newIndex === -1) {
      const intro = document.querySelector(".story-intro");
      if (intro) {
        intro.style.transition = "transform 0.5s ease-out";
        intro.style.transform = "translateY(0)";
      }
      const firstCard = state.textCards?.[0];
      if (firstCard) {
        firstCard.classList.remove("is-active", "is-stacked");
        const rot = parseFloat(firstCard.dataset.messinessRot || 0);
        const offX = parseFloat(firstCard.dataset.messinessOffX || 0);
        const offY = parseFloat(firstCard.dataset.messinessOffY || 0);
        firstCard.style.transform = `translateY(100vh) rotate(${rot}deg) translate(${offX}px, ${offY}px)`;
      }
      const firstObject = window.storyData?.firstObject;
      if (firstObject && state.viewerPlates?.[firstObject]) {
        const plate = state.viewerPlates[firstObject];
        plate.style.transform = "translateY(100%)";
        plate.classList.remove("is-active");
      }
      state.currentObjectRun = { objectId: null, runPosition: 0 };
      updateViewerInfo(-1);
      const creditBadge = document.getElementById("object-credits-badge");
      if (creditBadge) creditBadge.classList.add("d-none");
      return;
    }
    activateCard(newIndex, direction);
    updateViewerInfo(newIndex);
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
    if (state.mobileInIntro) {
      _dismissMobileIntro();
      return;
    }
    if (state.currentMobileStep >= state.steps.length - 1) {
      return;
    }
    goToMobileStep(state.currentMobileStep + 1);
  }
  function goToPreviousMobileStep() {
    if (state.mobileInIntro) {
      return;
    }
    if (state.currentMobileStep === 0) {
      _restoreMobileIntro();
      return;
    }
    goToMobileStep(state.currentMobileStep - 1);
  }
  function _restoreMobileIntro() {
    if (state.mobileNavigationCooldown) return;
    state.mobileNavigationCooldown = true;
    setTimeout(() => {
      state.mobileNavigationCooldown = false;
    }, MOBILE_NAV_COOLDOWN);
    state.mobileInIntro = true;
    const intro = document.querySelector(".story-intro");
    if (intro) {
      intro.style.transition = "transform 0.5s ease-out";
      intro.style.transform = "translateY(0)";
    }
    const firstCard = state.textCards?.[0];
    if (firstCard) {
      firstCard.classList.remove("is-active", "is-stacked");
      const rot = parseFloat(firstCard.dataset.messinessRot || 0);
      const offX = parseFloat(firstCard.dataset.messinessOffX || 0);
      const offY = parseFloat(firstCard.dataset.messinessOffY || 0);
      firstCard.style.transform = `translateY(100vh) rotate(${rot}deg) translate(${offX}px, ${offY}px)`;
    }
    const firstPlate = state.viewerPlates?.[0];
    if (firstPlate) {
      firstPlate.style.transform = "translateY(100%)";
      firstPlate.classList.remove("is-active");
    }
    state.currentObjectRun = { objectId: null, runPosition: 0 };
    updateViewerInfo(-1);
    const creditBadge = document.getElementById("object-credits-badge");
    if (creditBadge) creditBadge.classList.add("d-none");
    updateMobileButtonStates();
  }
  function _dismissMobileIntro() {
    if (state.mobileNavigationCooldown) return;
    state.mobileNavigationCooldown = true;
    setTimeout(() => {
      state.mobileNavigationCooldown = false;
    }, MOBILE_NAV_COOLDOWN);
    state.mobileInIntro = false;
    const intro = document.querySelector(".story-intro");
    if (intro) {
      intro.style.transition = "transform 0.5s ease-out";
      intro.style.transform = "translateY(-100%)";
    }
    state.currentMobileStep = 0;
    activateCard(0, "forward");
    updateViewerInfo(0);
    updateMobileButtonStates();
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
    const direction = newIndex > state.currentMobileStep ? "forward" : "backward";
    console.log(`Mobile navigation: ${state.currentMobileStep} \u2192 ${newIndex} (${direction})`);
    state.steps[state.currentMobileStep].classList.remove("mobile-active");
    state.steps[newIndex].classList.add("mobile-active");
    state.currentMobileStep = newIndex;
    updateMobileButtonStates();
    if (state.lenis) {
      advanceToStep(newIndex);
    } else {
      activateCard(newIndex, direction);
    }
    updateViewerInfo(newIndex);
    writeHash();
  }
  function updateMobileButtonStates() {
    if (!state.mobileNavButtons) return;
    state.mobileNavButtons.prev.disabled = !!state.mobileInIntro;
    state.mobileNavButtons.next.disabled = state.currentMobileStep === state.steps.length - 1;
  }
  function handleKeyboard(e) {
    if (e.repeat && !state.isPanelOpen) return;
    switch (e.key) {
      case "ArrowDown":
      case "PageDown":
        if (state.isPanelOpen) {
          scrollOpenPanel(40);
          break;
        }
        e.preventDefault();
        if (!state.scrollLockActive) {
          if (state.lenis) {
            keyboardNav("forward");
          } else {
            nextStep();
          }
        }
        break;
      case "ArrowUp":
      case "PageUp":
        if (state.isPanelOpen) {
          scrollOpenPanel(-40);
          break;
        }
        e.preventDefault();
        if (!state.scrollLockActive) {
          if (state.lenis) {
            keyboardNav("backward");
          } else {
            prevStep();
          }
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
        if (state.isPanelOpen) {
          scrollOpenPanel(e.shiftKey ? -100 : 100);
          e.preventDefault();
          break;
        }
        e.preventDefault();
        if (!state.scrollLockActive) {
          if (e.shiftKey) {
            if (state.lenis) keyboardNav("backward");
            else prevStep();
          } else {
            if (state.lenis) keyboardNav("forward");
            else nextStep();
          }
        }
        break;
    }
  }
  function scrollOpenPanel(delta) {
    const top = state.panelStack[state.panelStack.length - 1];
    if (!top) return;
    const panel = document.getElementById(`panel-${top.type}`);
    const body = panel?.querySelector(".offcanvas-body");
    if (body) body.scrollBy({ top: delta, behavior: "smooth" });
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
  function updateViewerInfo(stepIndex) {
    const counter = document.getElementById("step-counter");
    const infoElement = document.getElementById("current-object-title");
    if (!counter || !infoElement) return;
    if (stepIndex < 0) {
      counter.classList.add("d-none");
      return;
    }
    counter.classList.remove("d-none");
    const total = (window.storyData?.steps || []).filter((s) => !s._metadata).length;
    const stepTemplate = window.telarLang.stepNumber || "Step {{ number }}";
    const display = stepTemplate.replace("{{ number }}", stepIndex + 1);
    infoElement.textContent = total > 0 ? `${display} / ${total}` : display;
  }

  // assets/js/telar-story/main.js
  function initializeStory() {
    const viewerConfig = window.telarConfig?.viewer_preloading || {};
    state.config.maxViewerCards = Math.min(viewerConfig.max_viewer_cards || 10, 15);
    state.config.preloadSteps = Math.min(viewerConfig.preload_steps || 6, state.config.maxViewerCards - 2);
    state.config.loadingThreshold = viewerConfig.loading_threshold || 5;
    state.config.minReadyViewers = Math.min(viewerConfig.min_ready_viewers || 3, state.config.preloadSteps);
    buildObjectsIndex();
    prefetchStoryManifests();
    const cardConfig = {
      peekHeight: window.telarConfig?.cardPeekHeight ?? 1,
      messiness: window.telarConfig?.cardMessiness ?? 20
    };
    initCardPool(window.storyData, cardConfig);
    state.isMobileViewport = window.innerWidth < 768;
    const isEmbedMode = window.telarEmbed?.enabled || false;
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
    if (isEmbedMode) {
      initializeButtonNavigation("embed");
      const stepCount = (window.storyData?.steps || []).filter((s) => !s._metadata).length;
      initScrollEngine(stepCount);
    } else if (state.isMobileViewport) {
      initializeButtonNavigation("mobile");
    } else if (isIOS) {
      initializeButtonNavigation("mobile");
    } else {
      const stepCount = (window.storyData?.steps || []).filter((s) => !s._metadata).length;
      initScrollEngine(stepCount);
    }
    initializePanels();
    applyDeepLinkOnLoad();
    initializeScrollLock();
    initializeCredits();
  }
  document.addEventListener("DOMContentLoaded", function() {
    if (window.storyData?.encrypted) {
      window.addEventListener("telar:story-unlocked", function() {
        initializeStory();
      }, { once: true });
    } else {
      initializeStory();
    }
  });
  window.TelarStory = {
    state,
    activateCard,
    openPanel,
    getManifestUrl,
    closeAllPanels,
    getScrollEngineState
  };
})();
//# sourceMappingURL=telar-story.js.map
