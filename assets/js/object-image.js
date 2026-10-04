/* GENERATED FILE - do not edit. Bundled from assets/js/object-page/ by esbuild. Rebuild: npm run build:js (see assets/js/README.md). @version v1.8.0 */
(() => {
  // assets/js/object-page/boot.js
  function readObjectData(doc = document) {
    const block = doc.getElementById("telar-object-data");
    if (!block) return null;
    try {
      return JSON.parse(block.textContent);
    } catch (err) {
      console.error("Object page data block is not valid JSON:", err);
      return null;
    }
  }
  function publishLanguageGlobals(data, win = window) {
    win.telarCoordLang = { copied: data.lang.copied };
    win.telarViewerLang = data.lang.viewer;
  }
  function onObjectPage(wire) {
    const data = readObjectData();
    if (!data) return;
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => wire(data));
    } else {
      wire(data);
    }
  }

  // assets/js/telar-story/iiif-manifest.js
  function extractAllPages(manifest) {
    const v3Pages = extractV3Pages(manifest);
    if (v3Pages.length > 0) return v3Pages;
    const v2Pages = extractV2Pages(manifest);
    if (v2Pages.length > 0) return v2Pages;
    return [];
  }
  function extractV3Pages(manifest) {
    const pages = [];
    try {
      const items = manifest.items;
      if (!items) return pages;
      for (const canvas of items) {
        const annoPages = canvas.items;
        if (!annoPages?.[0]) continue;
        const annos = annoPages[0].items;
        if (!annos?.[0]) continue;
        const body = annos[0].body;
        if (!body) continue;
        const service = body.service;
        if (service?.[0]?.id) {
          pages.push({ tileSource: service[0].id + "/info.json" });
          continue;
        }
        if (body.id && typeof body.id === "string" && body.type === "Image") {
          const infoUrl = deriveInfoJsonFromImageUrl(body.id);
          if (infoUrl) {
            pages.push({ tileSource: infoUrl });
            continue;
          }
          pages.push({ tileSource: { type: "image", url: body.id } });
        }
      }
    } catch {
    }
    return pages;
  }
  function extractV2Pages(manifest) {
    const pages = [];
    try {
      const sequences = manifest.sequences;
      if (!sequences?.[0]) return pages;
      const canvases = sequences[0].canvases;
      if (!canvases) return pages;
      for (const canvas of canvases) {
        const images = canvas.images;
        if (!images?.[0]) continue;
        const resource = images[0].resource;
        if (!resource) continue;
        const service = resource.service;
        if (service?.["@id"]) {
          pages.push({ tileSource: service["@id"] + "/info.json" });
          continue;
        }
        if (resource["@id"] && typeof resource["@id"] === "string") {
          pages.push({ tileSource: { type: "image", url: resource["@id"] } });
        }
      }
    } catch {
    }
    return pages;
  }
  function deriveInfoJsonFromImageUrl(url) {
    const match = url.match(/^(.+\/iiif\/\d+\/[^/]+)\/[^/]+\/[^/]+\/[^/]+\/[^/]+$/);
    if (match) return match[1] + "/info.json";
    return null;
  }

  // assets/js/telar-story/state.js
  var state = {
    // ── Navigation ───────────────────────────────────────────────────────────
    /** @type {HTMLElement[]} All .story-step elements in DOM order. */
    steps: [],
    /** Index of the current desktop step (-1 = none). */
    currentIndex: -1,
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
    /**
     * Pixels one step occupies on the scroll surface: the viewport height the
     * surface was last laid out for, which trails the window by the resize
     * debounce. Every conversion between a step and a scroll offset uses it;
     * 0 when the scroll engine is not running.
     */
    scrollStepPx: 0,
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
    // ── Layout mode & embed ──────────────────────────────────────────────────
    /** @type {'horizontal' | 'vertical'} Layout mode. Updated by layout-mode.js on every resize/orientationchange. */
    layoutMode: "horizontal",
    /** Page-level boolean, set once at boot from window.telarEmbed.enabled. Orthogonal to layoutMode. */
    isEmbed: false,
    /** @type {DOMRect | null} Active text card's getBoundingClientRect; null when no active text card (title card, full-object mode). Populated by card-pool.js on activation + layout-mode.js on layoutchange. */
    cardOverlayRect: null,
    // ── Mobile button navigation ─────────────────────────────────────────────
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
    /**
     * Map of sceneIndex -> Plate, one per scene, built once and never evicted.
     * `.container` is the element. What a plate holds — a viewer, a player,
     * nothing yet — is the plate's own business; the pool inside an image
     * plate is the only thing here that is capped.
     */
    viewerPlates: {},
    /** Map of stepIndex -> text card element. */
    textCards: {},
    /** Map of stepIndex -> title card element. Populated by initCardPool. */
    titleCards: {},
    /** Index of the currently active title card step, or null when none is active. */
    activeTitleCardIndex: null,
    /** Current object run tracking (for peek stack positioning). */
    currentObjectRun: { objectId: null, runPosition: 0 },
    // ── Scene maps (populated at initCardPool time) ───────────────────────────
    /**
     * Filtered step data (metadata rows removed), in the same index space as
     * stepToScene / the card registry. Populated by initCardPool. The per-frame
     * lerp reads this so its stepIndex (a filtered-space index) lines up with
     * the step objects it interpolates between.
     */
    stepsData: [],
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
      /** Maximum IIIF wrapper instances kept in memory (per-scene pool cap). */
      maxViewerCards: 8,
      /** Steps to preload ahead of the current position. */
      preloadSteps: 6,
      /** Show loading shimmer when story has >= this many unique viewers. */
      loadingThreshold: 5,
      /** Hide shimmer once this many viewers are ready. */
      minReadyViewers: 3
    }
  };

  // assets/js/telar-story/test-hook.js
  function testEnabled() {
    if (typeof window === "undefined") return false;
    if (window.__TELAR_TEST_HOOK__ === true) return true;
    try {
      return /[?&]telartest=1(?:&|$)/.test(window.location.search);
    } catch {
      return false;
    }
  }
  var registry = [];
  var installed = false;
  function registerTestViewer(wrapper) {
    if (!testEnabled() || !wrapper) return;
    if (!registry.includes(wrapper)) registry.push(wrapper);
    installTestHook();
  }
  function unregisterTestViewer(wrapper) {
    const i = registry.indexOf(wrapper);
    if (i >= 0) registry.splice(i, 1);
  }
  function visibleArea(el) {
    const r = el.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const w = Math.max(0, Math.min(vw, r.right) - Math.max(0, r.left));
    const h = Math.max(0, Math.min(vh, r.bottom) - Math.max(0, r.top));
    return w * h;
  }
  function getActiveViewer() {
    const live = registry.filter(
      (w) => w && w.viewer && !w._destroyed && w.containerEl && document.contains(w.containerEl)
    );
    if (live.length === 0) return null;
    const plateOf = (w) => w.containerEl.closest(".viewer-plate");
    const zOf = (w) => {
      const p = plateOf(w);
      const z = p ? parseInt(getComputedStyle(p).zIndex, 10) : NaN;
      return Number.isNaN(z) ? -Infinity : z;
    };
    const isActive = (w) => !!plateOf(w)?.classList.contains("is-active");
    const pool = live.some(isActive) ? live.filter(isActive) : live;
    pool.sort(
      (a, b) => zOf(b) - zOf(a) || visibleArea(b.containerEl) - visibleArea(a.containerEl)
    );
    return pool[0];
  }
  function isSettled() {
    const w = getActiveViewer();
    if (!w || !w.viewer) return false;
    const vp = w.viewer.viewport;
    const zc = vp.getZoom(true), zt = vp.getZoom(false);
    const cc = vp.getCenter(true), ct = vp.getCenter(false);
    return Math.abs(zc - zt) < 1e-4 && Math.abs(cc.x - ct.x) < 1e-4 && Math.abs(cc.y - ct.y) < 1e-4;
  }
  function measure(nx, ny) {
    const w = getActiveViewer();
    if (!w) return { error: "no-active-viewer" };
    const v = w.viewer;
    const OSD = window.OpenSeadragon;
    if (!OSD || !v.world || v.world.getItemCount() === 0) return { error: "world-empty" };
    const item = v.world.getItemAt(0);
    const cs = item.getContentSize();
    const vp = v.viewport;
    const rect = w.containerEl.getBoundingClientRect();
    const elPt = vp.imageToViewerElementCoordinates(new OSD.Point(nx * cs.x, ny * cs.y));
    const focalScreenPx = { x: rect.left + elPt.x, y: rect.top + elPt.y };
    const visImg = vp.viewportToImageRectangle(vp.getBounds(true));
    const homeZoom = vp.getHomeZoom();
    const zoom = vp.getZoom(true);
    const cor = state.cardOverlayRect;
    return {
      ok: true,
      input: { nx, ny },
      viewport: { w: window.innerWidth, h: window.innerHeight, dpr: window.devicePixelRatio || 1 },
      imageSize: { w: cs.x, h: cs.y, aspect: cs.x / cs.y },
      homeZoom,
      zoom,
      effectiveNzoom: zoom / homeZoom,
      // what the runtime actually rendered, vs authored
      osdConfig: {
        visibilityRatio: v.visibilityRatio,
        constrainDuringPan: v.constrainDuringPan,
        minZoomImageRatio: v.minZoomImageRatio,
        homeFillsViewer: v.homeFillsViewer
      },
      viewerRect: { x: rect.left, y: rect.top, w: rect.width, h: rect.height },
      focalScreenPx,
      focalInViewerPx: { x: elPt.x, y: elPt.y },
      visibleImageRect: { x: visImg.x, y: visImg.y, w: visImg.width, h: visImg.height },
      cardOverlayRect: cor ? { x: cor.x, y: cor.y, w: cor.width, h: cor.height } : null,
      layoutMode: state.layoutMode ?? null,
      activeTitleCardIndex: state.activeTitleCardIndex ?? null
    };
  }
  var DEFAULT_SWEEP_STEPS = [
    { step: 1, x: 0.5, y: 0.5, zoom: 1 },
    { step: 2, x: 0.477, y: 0.125, zoom: 8.9 },
    { step: 3, x: 0.486, y: 0.277, zoom: 10 },
    { step: 4, x: 0.504, y: 0.415, zoom: 2.9 },
    { step: 5, x: 0.478, y: 0.883, zoom: 10 },
    { step: 6, x: 0.5, y: 0.5, zoom: 1 },
    { step: 19, x: 0.516, y: 0.974, zoom: 10 },
    { step: 20, x: 0.5, y: 0.5, zoom: 1 }
  ];
  async function settleAndMeasure(nx, ny, timeoutMs = 9e3) {
    const start = Date.now();
    let streak = 0, lastKey = null;
    while (Date.now() - start < timeoutMs) {
      const st = state;
      if (isSettled() && !(st && st.isSnapping)) {
        const m = measure(nx, ny);
        if (m && m.ok) {
          const key = `${Math.round(m.focalScreenPx.x)},${Math.round(m.focalScreenPx.y)},${m.zoom.toFixed(3)}`;
          if (key === lastKey) streak++;
          else {
            lastKey = key;
            streak = 0;
          }
          if (streak >= 3) return m;
        }
      } else {
        streak = 0;
      }
      await new Promise((r) => setTimeout(r, 150));
    }
    return measure(nx, ny);
  }
  async function runSweep(steps) {
    const nav = window.TelarStory && window.TelarStory.navigateToStep;
    const out = [];
    for (const s of steps) {
      if (nav) nav(s.step);
      await new Promise((r) => setTimeout(r, 450));
      const m = await settleAndMeasure(s.x, s.y);
      out.push({ step: s.step, authored: s, m });
    }
    return out;
  }
  function maybeAutoCollect() {
    let params;
    try {
      params = new URLSearchParams(window.location.search);
    } catch {
      return;
    }
    if (!params.has("collect")) return;
    const url = params.get("collect") || "http://127.0.0.1:8899/collect";
    const label = params.get("label") || "device";
    const steps = window.__TELAR_SWEEP_STEPS__ || DEFAULT_SWEEP_STEPS;
    runSweep(steps).then((results) => {
      const payload = {
        label,
        ua: navigator.userAgent,
        viewport: { w: window.innerWidth, h: window.innerHeight, dpr: window.devicePixelRatio || 1 },
        results
      };
      try {
        navigator.sendBeacon(url, new Blob([JSON.stringify(payload)], { type: "text/plain" }));
      } catch (e) {
        fetch(url, { method: "POST", mode: "no-cors", body: JSON.stringify(payload) }).catch(() => {
        });
      }
    });
  }
  function installTestHook() {
    if (installed || !testEnabled()) return;
    installed = true;
    window.__telarTestHook__ = {
      version: "v1.4.0",
      registry,
      getActiveViewer,
      isSettled,
      /** Primary API: exact rendered position + footprint of a focal point. */
      getFocalScreenPosition: measure,
      measure,
      /** Convenience: measure a list of `{nx, ny}` (or `{x, y}`) points in one call. */
      measurePoints(points) {
        return points.map((p) => measure(Number(p.nx ?? p.x), Number(p.ny ?? p.y)));
      },
      runSweep,
      settleAndMeasure
    };
    setTimeout(maybeAutoCollect, 800);
  }

  // assets/js/telar-story/iiif-viewer.js
  function normalizedViewportPosition(viewport) {
    const center = viewport.getCenter();
    const image = viewport.viewer && viewport.viewer.world.getItemAt(0);
    let x, y;
    if (image) {
      const px = image.viewportToImageCoordinates(center);
      const size = image.getContentSize();
      x = px.x / size.x;
      y = px.y / size.y;
    } else {
      const bounds = viewport.getHomeBounds();
      x = (center.x - bounds.x) / bounds.width;
      y = (center.y - bounds.y) / bounds.height;
    }
    const zoom = Math.max(0.1, Math.min(10, viewport.getZoom() / viewport.getHomeZoom()));
    return {
      x: Math.max(0, Math.min(1, x)),
      y: Math.max(0, Math.min(1, y)),
      zoom
    };
  }
  var IiifViewer = class _IiifViewer {
    /**
     * @param {IiifViewerOptions} options
     */
    constructor({ container, manifestUrl, startPage = 0, showChrome = false, allowZoomGestures = false, onPageShown = null }) {
      if (!window.OpenSeadragon) {
        throw new Error("IiifViewer: window.OpenSeadragon not loaded \u2014 vendor <script> ordering issue?");
      }
      this.containerEl = typeof container === "string" ? document.querySelector(container) : container;
      if (!this.containerEl) {
        throw new Error(`IiifViewer: container ${container} not found`);
      }
      this.manifestUrl = manifestUrl;
      this.startPage = startPage;
      this.showChrome = showChrome;
      this.allowZoomGestures = allowZoomGestures;
      this._onPageShown = onPageShown;
      this.pages = [];
      this.currentPage = startPage;
      this.viewer = null;
      this._destroyed = false;
      this._chromeEl = null;
      this._pageTransitioning = false;
      this.ready = this._init();
    }
    /**
     * Fetch the manifest, parse pages, and instantiate OpenSeadragon with
     * Tify-faithful options. Resolves `this.ready` on success; rejects (and
     * appends `.telar-iiif-error` to the container) on any failure.
     */
    async _init() {
      try {
        const res = await fetch(this.manifestUrl);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const manifest = await res.json();
        this.pages = extractAllPages(manifest);
        if (this.pages.length === 0) throw new Error("No pages extracted from manifest");
        this.currentPage = Math.max(0, Math.min(this.startPage, this.pages.length - 1));
        const gestureSettingsMouse = this.allowZoomGestures ? {} : { scrollToZoom: false };
        this.viewer = new window.OpenSeadragon({
          element: this.containerEl,
          tileSources: this.pages[this.currentPage].tileSource,
          animationTime: 0.4,
          drawer: "canvas",
          immediateRender: true,
          placeholderFillStyle: "grey",
          preserveImageSizeOnResize: true,
          preserveViewport: true,
          showNavigationControl: false,
          showZoomControl: false,
          visibilityRatio: 0.2,
          gestureSettingsMouse
        });
        if (!this.allowZoomGestures) {
          this.viewer.innerTracker.scrollHandler = false;
          this.viewer.gestureSettingsMouse.clickToZoom = false;
        }
        await new Promise((resolve, reject) => {
          const onFirstOpen = (event) => {
            this.viewer.removeHandler("open", onFirstOpen);
            this.viewer.removeHandler("open-failed", onOpenFailed);
            this._reportPageShown(event);
            requestAnimationFrame(resolve);
          };
          const onOpenFailed = (event) => {
            this.viewer.removeHandler("open", onFirstOpen);
            this.viewer.removeHandler("open-failed", onOpenFailed);
            reject(new Error("OSD open-failed: " + (event?.message || "unknown")));
          };
          this.viewer.addHandler("open", onFirstOpen);
          this.viewer.addHandler("open-failed", onOpenFailed);
        });
        this.viewer.addHandler("open", (event) => {
          this._pageTransitioning = false;
          this._updateChrome();
          this._reportPageShown(event);
        });
        this.viewer.addHandler("open-failed", () => {
          this._pageTransitioning = false;
          this._updateChrome();
        });
        if (this.showChrome && this.pages.length > 1) {
          this._injectChrome();
        }
        registerTestViewer(this);
      } catch (err) {
        console.error("IiifViewer: failed to initialise", err);
        this._injectErrorUI();
        throw err;
      }
    }
    /**
     * Open a different page of the manifest. Silent no-op when destroyed,
     * out of range, or already on the requested page.
     *
     * @param {number} n - 0-indexed page number.
     */
    setPage(n) {
      if (this._destroyed) return;
      if (n === this.currentPage || n < 0 || n >= this.pages.length) return;
      this.currentPage = n;
      this._pageTransitioning = true;
      this.viewer.open(this.pages[n].tileSource);
      this._updateChrome();
    }
    /**
     * Tell the `onPageShown` caller which page an OSD 'open' event showed.
     *
     * OpenSeadragon 6.0.2 drops an open superseded by a later `setPage`
     * without raising 'open' for it, so after two quick page changes the only
     * 'open' is the later page's. The source check keeps the report tied to
     * the page asked for last should an 'open' arrive for any other source.
     *
     * @param {{source?: *}} [event] - OSD 'open' event.
     */
    _reportPageShown(event) {
      if (!this._onPageShown || this._destroyed) return;
      const page = this.pages[this.currentPage];
      if (!page || !event || event.source !== page.tileSource) return;
      this._onPageShown(this.currentPage);
    }
    /**
     * Tear down the viewer and remove injected chrome.
     *
     * Idempotent — second and later calls return early via the `_destroyed`
     * flag. The viewer uses the Canvas2D drawer, so there is no
     * WebGL context to release before teardown (OpenSeadragon issue #2693
     * applies only to the WebGL drawer); this simply calls `viewer.destroy()`.
     */
    destroy() {
      if (this._destroyed) return;
      this._destroyed = true;
      unregisterTestViewer(this);
      if (this.viewer) {
        this.viewer.destroy();
        this.viewer = null;
      }
      if (this._chromeEl) {
        this._chromeEl.remove();
        this._chromeEl = null;
      }
    }
    // ── Chrome ─────────────────────────────────────────────────────────────────
    // Bootstrap Icons chevron paths (16×16, viewBox 0 0 16 16). Inlined so the
    // wrapper has no SVG-loading dependency; static path data only — no user
    // input ever reaches these strings.
    static _CHEVRON_LEFT = "M11.354 1.646a.5.5 0 0 1 0 .708L5.707 8l5.647 5.646a.5.5 0 0 1-.708.708l-6-6a.5.5 0 0 1 0-.708l6-6a.5.5 0 0 1 .708 0z";
    static _CHEVRON_RIGHT = "M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708z";
    /**
     * Substitute the wrapper's %{current} and %{total} placeholders in a
     * lang-key aria template. Returns '' when the template is missing so
     * a partially-localised installation does not write `undefined` into
     * an aria-label.
     *
     * @param {string|undefined} template
     * @param {number} current
     * @param {number} total
     * @returns {string}
     */
    _formatAriaLabel(template, current, total) {
      if (!template) return "";
      return template.replace("%{current}", String(current)).replace("%{total}", String(total));
    }
    /**
     * Build the `<svg><path/></svg>` chevron used by prev / next buttons.
     * createElementNS keeps the SVG in the SVG namespace; setAttribute
     * carries no XSS risk because the `d` value is a class-level constant.
     */
    _makeChevronSvg(pathData) {
      const NS = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(NS, "svg");
      svg.setAttribute("xmlns", NS);
      svg.setAttribute("width", "16");
      svg.setAttribute("height", "16");
      svg.setAttribute("viewBox", "0 0 16 16");
      svg.setAttribute("fill", "currentColor");
      svg.setAttribute("aria-hidden", "true");
      const path = document.createElementNS(NS, "path");
      path.setAttribute("d", pathData);
      svg.appendChild(path);
      return svg;
    }
    /**
     * Inject the prev / page-input / next pagination pills into the
     * container. Telar-namespaced class names only (no Bootstrap utility
     * classes). The pills float over the OSD canvas; positional
     * styling lives in `_sass/_viewer.scss`.
     */
    _injectChrome() {
      const lang = window.telarViewerLang ?? {};
      const total = this.pages.length;
      const current1 = this.currentPage + 1;
      const wrap = document.createElement("div");
      wrap.className = "telar-iiif-pagination";
      const prevBtn = document.createElement("button");
      prevBtn.type = "button";
      prevBtn.className = "prev-btn";
      prevBtn.setAttribute("aria-label", lang.prev_page ?? "Previous page");
      prevBtn.appendChild(this._makeChevronSvg(_IiifViewer._CHEVRON_LEFT));
      prevBtn.disabled = this.currentPage === 0;
      prevBtn.addEventListener("click", () => {
        if (this.currentPage > 0) this.setPage(this.currentPage - 1);
      });
      const labelEl = document.createElement("label");
      labelEl.className = "visually-hidden";
      labelEl.textContent = lang.page_input_label ?? "Page number";
      const inputId = `telar-iiif-page-${Math.random().toString(36).slice(2, 8)}`;
      labelEl.setAttribute("for", inputId);
      const input = document.createElement("input");
      input.type = "number";
      input.className = "page-input";
      input.id = inputId;
      input.min = "1";
      input.max = String(total);
      input.value = String(current1);
      input.setAttribute(
        "aria-label",
        this._formatAriaLabel(lang.page_input_aria, current1, total)
      );
      input.addEventListener("change", (e) => {
        const parsed = parseInt(e.target.value, 10);
        if (Number.isNaN(parsed)) {
          input.value = String(this.currentPage + 1);
          return;
        }
        const clamped = Math.max(1, Math.min(parsed, this.pages.length));
        this.setPage(clamped - 1);
      });
      const nextBtn = document.createElement("button");
      nextBtn.type = "button";
      nextBtn.className = "next-btn";
      nextBtn.setAttribute("aria-label", lang.next_page ?? "Next page");
      nextBtn.appendChild(this._makeChevronSvg(_IiifViewer._CHEVRON_RIGHT));
      nextBtn.disabled = this.currentPage === total - 1;
      nextBtn.addEventListener("click", () => {
        if (this.currentPage < this.pages.length - 1) this.setPage(this.currentPage + 1);
      });
      wrap.append(prevBtn, labelEl, input, nextBtn);
      this.containerEl.append(wrap);
      this._chromeEl = wrap;
    }
    /**
     * Reflect `currentPage` and `_pageTransitioning` back into the
     * injected chrome (input value, aria-label, prev/next disabled).
     * No-op when chrome has not been injected (`showChrome` false or
     * single-page manifest).
     */
    _updateChrome() {
      if (!this._chromeEl) return;
      const lang = window.telarViewerLang ?? {};
      const total = this.pages.length;
      const current1 = this.currentPage + 1;
      const input = this._chromeEl.querySelector(".page-input");
      if (input) {
        input.value = String(current1);
        input.setAttribute(
          "aria-label",
          this._formatAriaLabel(lang.page_input_aria, current1, total)
        );
      }
      const prevBtn = this._chromeEl.querySelector(".prev-btn");
      if (prevBtn) prevBtn.disabled = this.currentPage === 0 || this._pageTransitioning;
      const nextBtn = this._chromeEl.querySelector(".next-btn");
      if (nextBtn) nextBtn.disabled = this.currentPage === total - 1 || this._pageTransitioning;
    }
    // ── Error UI ───────────────────────────────────────────────────────────────
    /**
     * Append `.telar-iiif-error` to the container when manifest fetch or
     * OSD instantiation fails. Uses `textContent` for every string and
     * never assembles HTML strings; reads localised text from
     * `window.telarViewerLang` with inline English fallbacks so the wrapper
     * degrades gracefully if the lang injection is missing.
     */
    _injectErrorUI() {
      const div = document.createElement("div");
      div.className = "telar-iiif-error";
      div.setAttribute("role", "alert");
      div.setAttribute("aria-live", "polite");
      const lang = window.telarViewerLang ?? {};
      const strong = document.createElement("strong");
      strong.textContent = lang.image_unavailable_title ?? "Image unavailable";
      const p = document.createElement("p");
      p.textContent = lang.image_unavailable_detail ?? "The IIIF image could not be loaded.";
      div.append(strong, p);
      this.containerEl.append(div);
    }
  };

  // assets/js/object-page/copy-feedback.js
  var CHECK_ICON = '<svg class="icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>';
  function copyWithFeedback(text, buttonId, feedbackHtml, doc = document) {
    return navigator.clipboard.writeText(text).then(function() {
      const btn = doc.getElementById(buttonId);
      const originalHTML = btn.innerHTML;
      btn.innerHTML = feedbackHtml;
      setTimeout(function() {
        btn.innerHTML = originalHTML;
      }, 2e3);
    });
  }

  // assets/js/object-page/image-object.js
  function manifestUrlFor(data) {
    if (data.externalSource) return data.externalSource;
    if (data.objectId) return data.baseUrl + "/iiif/objects/" + data.objectId + "/manifest.json";
    return null;
  }
  function requestedPage(search) {
    const value = new URLSearchParams(search).get("page");
    if (value === null || !/^[0-9]+$/.test(value)) return 0;
    const page = parseInt(value, 10);
    return page >= 1 ? page - 1 : 0;
  }
  function addressWithPage(href, page0, total) {
    const url = new URL(href);
    const pieces = url.search.replace(/^\?/, "").split("&");
    const isPage = function(piece) {
      return piece !== "" && Array.from(new URLSearchParams(piece).keys())[0] === "page";
    };
    const named = total > 1 && page0 > 0;
    if (!named && !pieces.some(isPage)) return href;
    const kept = pieces.filter(function(piece) {
      return piece !== "" && !isPage(piece);
    });
    if (named) kept.push("page=" + (page0 + 1));
    url.search = kept.length ? "?" + kept.join("&") : "";
    return url.href;
  }
  async function initImageViewer(data, doc = document) {
    const manifestUrl = manifestUrlFor(data);
    if (!manifestUrl) {
      console.error("No IIIF source specified");
      return;
    }
    const win = doc.defaultView || window;
    function writeAddress(page0) {
      const next = addressWithPage(win.location.href, page0, wrapper.pages.length);
      if (next !== win.location.href) win.history.replaceState(win.history.state, "", next);
    }
    const wrapper = new IiifViewer({
      container: "#object-viewer",
      manifestUrl,
      startPage: requestedPage(win.location.search),
      showChrome: true,
      allowZoomGestures: true,
      onPageShown: writeAddress
    });
    try {
      await wrapper.ready;
    } catch (err) {
      console.error("IiifViewer failed to initialise:", err);
      return;
    }
    const isMultiPage = wrapper.pages.length > 1;
    writeAddress(wrapper.currentPage);
    if (isMultiPage) {
      doc.getElementById("object-viewer").classList.add("multipage");
      const pageRows = doc.querySelectorAll(".coord-page-row");
      pageRows.forEach(function(el) {
        el.style.display = "flex";
      });
      var singleInstr = doc.querySelector(".coord-instructions-single");
      var multiInstr = doc.querySelector(".coord-instructions-multi");
      if (singleInstr) singleInstr.style.display = "none";
      if (multiInstr) multiInstr.style.display = "block";
    }
    const osdViewer = wrapper.viewer;
    if (osdViewer.world.getItemCount() === 0) {
      osdViewer.addHandler("open", function() {
        setTimeout(function() {
          osdViewer.viewport.goHome(true);
        }, 100);
      });
    } else {
      osdViewer.viewport.goHome(true);
    }
    osdViewer.world.addHandler("add-item", function() {
      setTimeout(function() {
        osdViewer.viewport.goHome(true);
      }, 50);
    });
    osdViewer.addHandler("open-failed", function(event) {
      console.error("OpenSeadragon open failed:", event);
    });
    function updateCoordinates() {
      if (!osdViewer || !osdViewer.viewport) return;
      try {
        const pos = normalizedViewportPosition(osdViewer.viewport);
        doc.getElementById("coord-x").textContent = pos.x.toFixed(3);
        doc.getElementById("coord-y").textContent = pos.y.toFixed(3);
        doc.getElementById("coord-zoom").textContent = pos.zoom.toFixed(1);
        if (isMultiPage) {
          const page = wrapper.currentPage + 1;
          doc.getElementById("coord-page").textContent = page;
        }
      } catch (error) {
        console.error("Error updating coordinates:", error);
      }
    }
    osdViewer.addHandler("animation", updateCoordinates);
    osdViewer.addHandler("animation-finish", updateCoordinates);
    osdViewer.addHandler("zoom", updateCoordinates);
    osdViewer.addHandler("pan", updateCoordinates);
    setInterval(updateCoordinates, 500);
    updateCoordinates();
  }
  function initCoordinatePanel(doc = document) {
    const coordinatePanel = doc.getElementById("coordinatePanel");
    const coordinateButton = doc.getElementById("coordinateButton");
    if (coordinatePanel && coordinateButton) {
      coordinatePanel.addEventListener("show.bs.collapse", function() {
        coordinateButton.style.display = "none";
      });
      coordinatePanel.addEventListener("hide.bs.collapse", function() {
        coordinateButton.style.display = "block";
      });
    }
    function copyCoordText(text, btnId) {
      return copyWithFeedback(text, btnId, CHECK_ICON + " " + window.telarCoordLang.copied, doc);
    }
    function copyCoordIconOnly(text, btnId) {
      return copyWithFeedback(text, btnId, CHECK_ICON, doc);
    }
    function coordinateText(separator) {
      const x = doc.getElementById("coord-x").textContent;
      const y = doc.getElementById("coord-y").textContent;
      const zoom = doc.getElementById("coord-zoom").textContent;
      const viewer = doc.getElementById("object-viewer");
      const isMulti = viewer && viewer.classList.contains("multipage");
      const parts = [x, y, zoom];
      if (isMulti) parts.push(doc.getElementById("coord-page").textContent);
      return parts.join(separator);
    }
    doc.getElementById("copy-coords-csv").addEventListener("click", function() {
      copyCoordText(coordinateText(","), "copy-coords-csv");
    });
    doc.getElementById("copy-coords-sheets").addEventListener("click", function() {
      copyCoordText(coordinateText("	"), "copy-coords-sheets");
    });
    const copyManifestBtn = doc.getElementById("copy-manifest");
    if (copyManifestBtn) {
      copyManifestBtn.addEventListener("click", function() {
        const manifestUrl = this.getAttribute("data-manifest");
        copyCoordIconOnly(manifestUrl, "copy-manifest").catch(function(err) {
          console.error("Failed to copy manifest URL:", err);
        });
      });
    }
    const singles = [
      ["copy-x", "coord-x"],
      ["copy-y", "coord-y"],
      ["copy-zoom", "coord-zoom"],
      ["copy-page", "coord-page"]
    ];
    singles.forEach(function(pair) {
      const btn = doc.getElementById(pair[0]);
      if (btn) {
        btn.addEventListener("click", function() {
          copyCoordIconOnly(doc.getElementById(pair[1]).textContent, pair[0]);
        });
      }
    });
  }

  // assets/js/object-page/image-entry.js
  onObjectPage((data) => {
    publishLanguageGlobals(data);
    initCoordinatePanel();
    initImageViewer(data);
  });
})();
//# sourceMappingURL=object-image.js.map
