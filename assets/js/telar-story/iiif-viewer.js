/**
 * Telar Story – IIIF Viewer Wrapper
 *
 * Tify-faithful OpenSeadragon wrapper that replaces the Tify dependency
 * removed in v1.4.0. Tify (a Vue-based IIIF reader) was carrying ~150 KB
 * of framework code and 56 `!important` SCSS overrides whose only purpose
 * was to hide its UI chrome; this class exposes the small subset of
 * Tify's API that Telar actually used — constructor, `.ready`, `.viewer`,
 * `.pages`, `.currentPage`, `.setPage(n)`, `.destroy()` — sitting directly
 * on top of OpenSeadragon 6.0.2.
 *
 * OSD is loaded via the vendored `<script>` tag at `assets/vendor/openseadragon.min.js`
 * and reached at runtime through `window.OpenSeadragon`. The
 * wrapper deliberately does NOT `import` OpenSeadragon: doing so would
 * either fail the esbuild bundle (if OSD is not an npm dep) or silently
 * pull the entire library into `assets/js/telar-story.js`, defeating the
 * vendoring strategy.
 *
 * Destruction — `destroy()` calls OSD's `viewer.destroy()` and removes any
 * injected chrome; it is idempotent via the `_destroyed` flag.
 * The viewer uses the Canvas2D drawer, so there is no WebGL context to
 * release first — OpenSeadragon issue #2693 (GPU memory not reclaimed when
 * the canvas leaves the DOM) applies only to the WebGL drawer.
 *
 * Adapted from the Telar Compositor's IIIF viewer.
 *
 * @version v1.4.0
 */

import { extractAllPages } from './iiif-manifest.js';
import { registerTestViewer, unregisterTestViewer } from './test-hook.js';

// ── Type definition ──────────────────────────────────────────────────────────

/**
 * @typedef {Object} IiifViewerOptions
 * @property {HTMLElement|string} container - Container element or CSS selector.
 * @property {string} manifestUrl - URL of the IIIF Presentation API manifest (v2 or v3).
 * @property {number} [startPage=0] - 0-indexed page to open initially; clamped to manifest length.
 * @property {boolean} [showChrome=false] - When true and the manifest has >1 page, inject prev/page-input/next chrome.
 * @property {boolean} [allowZoomGestures=false] - When true, leave OSD's mouse-wheel-zoom and click-to-zoom enabled. Default false because the wrapper is normally embedded in story plates whose scroll wheel belongs to Lenis (the scroll engine). Pass true on standalone object-viewer pages where there is no Lenis to fight and the reader expects scroll-to-zoom.
 */

// ── Class ────────────────────────────────────────────────────────────────────

export class IiifViewer {
  /**
   * @param {IiifViewerOptions} options
   */
  constructor({ container, manifestUrl, startPage = 0, showChrome = false, allowZoomGestures = false }) {
    if (!window.OpenSeadragon) {
      throw new Error('IiifViewer: window.OpenSeadragon not loaded — vendor <script> ordering issue?');
    }

    // Accept either an element or a selector string — passing the actual
    // element to OSD's `element:` option avoids the selector-lookup race
    // covered by plates whose dimensions resolve asynchronously.
    this.containerEl = typeof container === 'string'
      ? document.querySelector(container)
      : container;
    if (!this.containerEl) {
      throw new Error(`IiifViewer: container ${container} not found`);
    }

    this.manifestUrl = manifestUrl;
    this.startPage = startPage;
    this.showChrome = showChrome;
    this.allowZoomGestures = allowZoomGestures;
    this.pages = [];
    this.currentPage = startPage;
    this.viewer = null;          // OSD instance (populated after .ready resolves)
    this._destroyed = false;
    this._chromeEl = null;       // .telar-iiif-pagination element when injected
    this._pageTransitioning = false; // true while OSD's viewer.open() is in flight

    this.ready = this._init();
  }

  /**
   * Fetch the manifest, parse pages, and instantiate OpenSeadragon with
   * Tify-faithful options. Resolves `this.ready` on success; rejects (and
   * appends `.telar-iiif-error` to the container) on any failure.
   */
  async _init() {
    try {
      // No `credentials` option — defaults to `same-origin`, avoiding a
      // cross-origin cookie leak.
      const res = await fetch(this.manifestUrl);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const manifest = await res.json();
      this.pages = extractAllPages(manifest);
      if (this.pages.length === 0) throw new Error('No pages extracted from manifest');

      this.currentPage = Math.max(0, Math.min(this.startPage, this.pages.length - 1));

      // Tify-faithful OSD config, matching Tify 0.35.0's OSD options.
      // Drawer is explicitly 'canvas' (Tify forces it; OSD 6.x defaults to
      // 'webgl', which breaks drop-shadow and changes loseContext semantics).
      // `preserveImageSizeOnResize: true` is also explicit
      // (Tify sets it; OSD default is false).
      // `gestureSettingsMouse.scrollToZoom` defaults true in OSD. The
      // wrapper kills it when `allowZoomGestures` is false (the normal
      // story-plate case — wheel events belong to Lenis). Standalone
      // object pages opt in by passing `allowZoomGestures: true` so the
      // reader can scroll-zoom the way they could under Tify.
      const gestureSettingsMouse = this.allowZoomGestures
        ? {}
        : { scrollToZoom: false };

      this.viewer = new window.OpenSeadragon({
        element: this.containerEl,
        tileSources: this.pages[this.currentPage].tileSource,
        animationTime: 0.4,
        drawer: 'canvas',
        immediateRender: true,
        placeholderFillStyle: 'grey',
        preserveImageSizeOnResize: true,
        preserveViewport: true,
        showNavigationControl: false,
        showZoomControl: false,
        visibilityRatio: 0.2,
        gestureSettingsMouse,
      });

      if (!this.allowZoomGestures) {
        // Belt-and-braces — protects against any OSD path that
        // re-enables scroll handling internally.
        this.viewer.innerTracker.scrollHandler = false;
        // Tify sets this post-construction; replicate so click-to-zoom
        // is also disabled (the upstream Tify call lives in
        // ViewMedia.vue immediately after the OSD constructor).
        this.viewer.gestureSettingsMouse.clickToZoom = false;
      }

      // Wait for the first 'open' event before resolving .ready, so that
      // callers (notably card-pool's snapIiifToPosition / object.html's
      // coord-picker) can position the viewport with confidence that the
      // tile source has loaded into the world. Mirrors Tify.ready
      // semantics — without this, world.getItemCount() is 0 when .ready
      // resolves, snapIiifToPosition runs against an empty world, and
      // the image briefly shows at OSD's default-centered home position
      // before snapping to the step's coordinates.
      //
      // Timing fix: `preserveViewport: true` protects the
      // viewport only across PAGE opens — not the very first open. OSD's
      // initial home-fit can land AFTER a synchronous zoomTo/panTo in
      // ready.then, resetting the viewer to home zoom. Deferring via one
      // requestAnimationFrame after the first 'open' event lets the home-fit
      // settle before .ready resolves, so any authored position applied in
      // ready.then arrives AFTER the home-fit rather than racing it.
      //
      // 'open-failed' rejects so the catch below renders the error UI.
      await new Promise((resolve, reject) => {
        const onFirstOpen = () => {
          this.viewer.removeHandler('open', onFirstOpen);
          this.viewer.removeHandler('open-failed', onOpenFailed);
          // Defer resolution one frame so OSD's initial home-fit (which runs
          // asynchronously after the 'open' event) has settled before callers
          // apply authored pan/zoom. A single rAF is the documented minimal
          // shape (a single rAF after ready).
          requestAnimationFrame(resolve);
        };
        const onOpenFailed = (event) => {
          this.viewer.removeHandler('open', onFirstOpen);
          this.viewer.removeHandler('open-failed', onOpenFailed);
          reject(new Error('OSD open-failed: ' + (event?.message || 'unknown')));
        };
        this.viewer.addHandler('open', onFirstOpen);
        this.viewer.addHandler('open-failed', onOpenFailed);
      });

      // Race guard for subsequent setPage() transitions.
      // `viewer.open()` is async (fetches info.json then tiles); the 'open'
      // event fires once the new tile source is fully loaded. We register
      // this handler AFTER the initial-open await above so it only fires
      // for page-change opens, not the first load. viewer.destroy() tears
      // down its own handlers, so no explicit cleanup is needed.
      this.viewer.addHandler('open', () => {
        this._pageTransitioning = false;
        this._updateChrome();
      });

      if (this.showChrome && this.pages.length > 1) {
        this._injectChrome();
      }

      // Register with the centering measurement hook. No-op unless
      // the page is loaded with ?telartest=1 — never active in production.
      registerTestViewer(this);
    } catch (err) {
      console.error('IiifViewer: failed to initialise', err);
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
  static _CHEVRON_LEFT = 'M11.354 1.646a.5.5 0 0 1 0 .708L5.707 8l5.647 5.646a.5.5 0 0 1-.708.708l-6-6a.5.5 0 0 1 0-.708l6-6a.5.5 0 0 1 .708 0z';
  static _CHEVRON_RIGHT = 'M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708z';

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
    if (!template) return '';
    return template.replace('%{current}', String(current)).replace('%{total}', String(total));
  }

  /**
   * Build the `<svg><path/></svg>` chevron used by prev / next buttons.
   * createElementNS keeps the SVG in the SVG namespace; setAttribute
   * carries no XSS risk because the `d` value is a class-level constant.
   */
  _makeChevronSvg(pathData) {
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('xmlns', NS);
    svg.setAttribute('width', '16');
    svg.setAttribute('height', '16');
    svg.setAttribute('viewBox', '0 0 16 16');
    svg.setAttribute('fill', 'currentColor');
    svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS(NS, 'path');
    path.setAttribute('d', pathData);
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

    const wrap = document.createElement('div');
    wrap.className = 'telar-iiif-pagination';

    // Prev button
    const prevBtn = document.createElement('button');
    prevBtn.type = 'button';
    prevBtn.className = 'prev-btn';
    prevBtn.setAttribute('aria-label', lang.prev_page ?? 'Previous page');
    prevBtn.appendChild(this._makeChevronSvg(IiifViewer._CHEVRON_LEFT));
    prevBtn.disabled = this.currentPage === 0;
    prevBtn.addEventListener('click', () => {
      if (this.currentPage > 0) this.setPage(this.currentPage - 1);
    });

    // Page input — visually-hidden label for AT users; aria-label carries
    // the dynamic "Page X of Y" message so screen readers announce it on
    // focus. Enter/blur (input's `change` event) commits the new value;
    // chose this over a 300ms debounce because the handler stays simple
    // and there is nothing to clean up in destroy().
    const labelEl = document.createElement('label');
    labelEl.className = 'visually-hidden';
    labelEl.textContent = lang.page_input_label ?? 'Page number';
    const inputId = `telar-iiif-page-${Math.random().toString(36).slice(2, 8)}`;
    labelEl.setAttribute('for', inputId);

    const input = document.createElement('input');
    input.type = 'number';
    input.className = 'page-input';
    input.id = inputId;
    input.min = '1';
    input.max = String(total);
    input.value = String(current1);
    input.setAttribute(
      'aria-label',
      this._formatAriaLabel(lang.page_input_aria, current1, total)
    );
    input.addEventListener('change', (e) => {
      const parsed = parseInt(e.target.value, 10);
      if (Number.isNaN(parsed)) {
        input.value = String(this.currentPage + 1);
        return;
      }
      const clamped = Math.max(1, Math.min(parsed, this.pages.length));
      this.setPage(clamped - 1);
    });

    // Next button
    const nextBtn = document.createElement('button');
    nextBtn.type = 'button';
    nextBtn.className = 'next-btn';
    nextBtn.setAttribute('aria-label', lang.next_page ?? 'Next page');
    nextBtn.appendChild(this._makeChevronSvg(IiifViewer._CHEVRON_RIGHT));
    nextBtn.disabled = this.currentPage === total - 1;
    nextBtn.addEventListener('click', () => {
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

    const input = this._chromeEl.querySelector('.page-input');
    if (input) {
      input.value = String(current1);
      input.setAttribute(
        'aria-label',
        this._formatAriaLabel(lang.page_input_aria, current1, total)
      );
    }

    const prevBtn = this._chromeEl.querySelector('.prev-btn');
    if (prevBtn) prevBtn.disabled = this.currentPage === 0 || this._pageTransitioning;
    const nextBtn = this._chromeEl.querySelector('.next-btn');
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
    const div = document.createElement('div');
    div.className = 'telar-iiif-error';
    div.setAttribute('role', 'alert');
    div.setAttribute('aria-live', 'polite');
    const lang = window.telarViewerLang ?? {};
    const strong = document.createElement('strong');
    strong.textContent = lang.image_unavailable_title ?? 'Image unavailable';
    const p = document.createElement('p');
    p.textContent = lang.image_unavailable_detail ?? 'The IIIF image could not be loaded.';
    div.append(strong, p);
    this.containerEl.append(div);
  }
}
