/**
 * Telar Story – Panel System
 *
 * This module manages the layered information panels that slide in from the
 * right side of the story page. Panels use Bootstrap 5 Offcanvas components
 * and follow a stacking hierarchy:
 *
 * - Layer 1: The first panel, triggered by a button on a story step. When
 *   open, it freezes story navigation so the user can scroll the panel
 *   content without accidentally changing steps.
 * - Layer 2: A deeper panel that stacks on top of Layer 1, triggered by a
 *   button inside the Layer 1 content.
 * - Glossary: A panel that can open from any context when the user clicks a
 *   glossary link in story or panel content. telar.js opens it, not
 *   openPanel(); it joins the stack here when it shows, so that it is the
 *   topmost panel the keys close. It never adds a layer to the URL fragment;
 *   a glossary link in a layer adds g{n}, its running number in that layer,
 *   which leaves the fragment when the glossary panel closes.
 *
 * The panel stack tracks which panels are open and in what order. Closing
 * always removes the topmost panel. The user can close panels with the back
 * button, Escape key, left arrow key, or by clicking outside the panel. What
 * an open panel covers is made inert by telar.js.
 *
 * When any panel is open, the scroll lock system blocks step navigation
 * (wheel events, keyboard arrows, touch swipes) and shows a subtle backdrop.
 * This is the "panel freeze" system — panels are truly modal and must be
 * explicitly dismissed.
 *
 * @version v1.8.0
 */

import { state } from './state.js';
import { getBasePath, fixImageUrls, escapeHtml } from './utils.js';
import { writeHash, writeHashWithGlossary } from './deep-link.js';

// ── Panel open / close ───────────────────────────────────────────────────────

/** The story's panels, each the element `#panel-{type}`. */
const PANEL_TYPES = ['layer1', 'layer2', 'glossary'];

/**
 * Set up click handlers for panel trigger buttons and back buttons.
 *
 * Both layer 1 and layer 2 triggers use event delegation on the document
 * so that buttons created dynamically by card-pool.js are handled correctly.
 */
export function initializePanels() {
  // Layer 1 triggers (delegated — text card buttons are created dynamically by card-pool.js)
  document.addEventListener('click', function (e) {
    const trigger = e.target.closest('[data-panel="layer1"]');
    if (trigger) {
      const stepNumber = trigger.dataset.step;
      // Hide any already-open panel (layer2/glossary) before rewriting the stack,
      // so a stale offcanvas can't linger over the freshly-opened layer1.
      document.querySelectorAll('.offcanvas.show').forEach(p => {
        const inst = bootstrap.Offcanvas.getInstance(p);
        if (inst) inst.hide();
      });
      state.panelStack = [];
      openPanel('layer1', stepNumber);
    }
  });

  // Layer 2 triggers (delegated)
  document.addEventListener('click', function (e) {
    if (e.target.matches('[data-panel="layer2"]')) {
      const stepNumber = e.target.dataset.step;
      openPanel('layer2', stepNumber);
    }
  });

  // Back buttons
  const layer1Back = document.getElementById('panel-layer1-back');
  if (layer1Back) {
    layer1Back.addEventListener('click', function () {
      closePanel('layer1');
    });
  }

  const layer2Back = document.getElementById('panel-layer2-back');
  if (layer2Back) {
    layer2Back.addEventListener('click', function () {
      closePanel('layer2');
    });
  }

  const glossaryBack = document.getElementById('panel-glossary-back');
  if (glossaryBack) {
    glossaryBack.addEventListener('click', function () {
      closePanel('glossary');
    });
  }

  const glossaryPanel = document.getElementById('panel-glossary');
  if (glossaryPanel) {
    glossaryPanel.addEventListener('show.bs.offcanvas', joinGlossaryToStack);
  }

  // Bootstrap can dismiss a panel without going through closePanel (the
  // offcanvas X button uses data-bs-dismiss), so panel state is reconciled
  // on hidden.bs.offcanvas — the one event every dismissal path fires.
  PANEL_TYPES.forEach((panelType) => {
    const panel = document.getElementById(`panel-${panelType}`);
    if (!panel) return;
    panel.addEventListener('hidden.bs.offcanvas', function () {
      const before = state.panelStack.length;
      state.panelStack = state.panelStack.filter(p => p.type !== panelType);
      if (state.panelStack.length !== before) {
        writeHash();
      }
      if (!anyPanelOpen()) {
        state.isPanelOpen = false;
        deactivateScrollLock();
      }
      // The entry number recorded by writeHashWithGlossary goes with the entry,
      // unless a newer entry has already reopened the panel.
      if (panelType === 'glossary' && !panel.classList.contains('show')) {
        panel.removeAttribute('data-deep-link-n');
      }
      settleFocusTraps();
    });
    panel.addEventListener('shown.bs.offcanvas', settleFocusTraps);
  });

  initializeShareHandoff();
}

/**
 * A panel's or the Share dialog's Bootstrap focus trap, or null.
 *
 * Bootstrap 5.3.0, which the layouts pin, keeps the trap on the component
 * instance as `_focustrap`, with its state in `_isActive`; neither is public,
 * so a change of Bootstrap version has to be checked against this helper. All
 * traps share one set of document listeners: `activate()` replaces whichever
 * trap held them, and `deactivate()` on a trap marked active removes them for
 * every trap. `activate()` does nothing on a trap already marked active, so
 * `hold()` clears the mark first. `release()` reports whether the trap was
 * marked active, that is whether it removed the listeners.
 *
 * @param {Element|null} el - A panel or the Share dialog.
 * @param {Function} Component - `bootstrap.Offcanvas` for a panel, `bootstrap.Modal` for Share.
 * @returns {{isHeld: function(): boolean, hold: function(): void, release: function(): boolean}|null}
 */
function focusTrap(el, Component) {
  const instance = el && Component.getInstance(el);
  const trap = instance?._focustrap;
  if (!trap) return null;
  return {
    isHeld: () => trap._isActive,
    hold: () => { trap.deactivate(); trap.activate(); },
    release: () => {
      const held = trap._isActive;
      trap.deactivate();
      return held;
    },
  };
}

/** Whether the Share dialog is open, from the start of its show to the end of its hide. */
let shareOpen = false;

/** Whether a panel is open and not closing. */
const isSettledOpen = (el) => el.classList.contains('show') && !el.classList.contains('hiding');

/**
 * The topmost panel that is open and not closing, or null.
 *
 * The stack orders the panels; a panel Bootstrap closed without the stack (its
 * X button) leaves it only once hidden, so a closing panel is skipped.
 */
function topmostOpenPanel() {
  const els = state.panelStack.map((p) => document.getElementById(`panel-${p.type}`));
  const fromStack = els.reverse().find((el) => el && isSettledOpen(el));
  if (fromStack) return fromStack;
  const open = PANEL_TYPES.map((t) => document.getElementById(`panel-${t}`))
    .filter((el) => el && isSettledOpen(el));
  return open[open.length - 1] || null;
}

/** Release every panel's trap; true if one of them held the document listeners. */
function releasePanelTraps(except = null) {
  return PANEL_TYPES.map((t) => document.getElementById(`panel-${t}`))
    .filter((el) => el && el !== except)
    .map((el) => focusTrap(el, bootstrap.Offcanvas)?.release())
    .some(Boolean);
}

/**
 * Give the one active focus trap to whatever is on top.
 *
 * Bootstrap activates a panel's trap when the panel finishes opening and
 * deactivates it when the panel starts to close, without regard to the panels
 * below or to the Share dialog. While Share is open it holds focus and no
 * panel's trap may; a panel trap that was active has taken the listeners from
 * Share, which gets them back. Otherwise the topmost open, non-closing panel's
 * trap is the one active, and every other panel's is released.
 */
function settleFocusTraps() {
  if (shareOpen) {
    const share = document.getElementById('panel-share');
    const shareTrap = focusTrap(share, bootstrap.Modal);
    const shareHeld = shareTrap?.isHeld();
    if (releasePanelTraps() && shareHeld) shareTrap.hold();
    return;
  }
  const top = topmostOpenPanel();
  releasePanelTraps(top);
  if (top) focusTrap(top, bootstrap.Offcanvas)?.hold();
}

/**
 * Hand focus and keys to the Share dialog while it is open over a panel, and
 * back to the topmost panel when it closes.
 *
 * Share opens over panels that stay open. A panel's focus trap sends focus
 * that leaves the panel back into it, so the panels' traps stay off while
 * Share shows, including one that finishes opening meanwhile. On close the
 * topmost open panel's trap is restored and focus goes to that panel, after
 * Bootstrap has returned it to the Share button, which sits outside the panel.
 */
function initializeShareHandoff() {
  const share = document.getElementById('panel-share');
  if (!share) return;

  share.addEventListener('show.bs.modal', () => {
    shareOpen = true;
    releasePanelTraps();
  });
  share.addEventListener('hidden.bs.modal', () => {
    shareOpen = false;
    settleFocusTraps();
    // Bootstrap's own return of focus to the Share button runs after this
    // listener; the move into the panel has to come after it.
    setTimeout(() => topmostOpenPanel()?.focus(), 0);
  });
}

/**
 * Whether any of the story's panels is open, opening or still closing, so the
 * story stays frozen.
 *
 * The stack holds a panel from its open until its close is asked for, so one
 * that has begun to slide in while another slides out keeps the story frozen
 * when the other's close completes. A panel whose close has been asked for
 * leaves the stack at once but keeps `show` until its slide out ends. Only the
 * story's own panels count: another offcanvas on the page has no close that
 * would lift the lock.
 */
function anyPanelOpen() {
  return state.panelStack.length > 0
    || PANEL_TYPES.some((t) => document.getElementById(`panel-${t}`)?.classList.contains('show'));
}

/**
 * Put the glossary panel on top of the panel stack as it shows.
 *
 * The panel freezes the story as a layer does. The URL fragment is not
 * rewritten: it names layers only, and a glossary link writes its own g{n}.
 */
function joinGlossaryToStack() {
  const top = state.panelStack[state.panelStack.length - 1];
  if (top?.type !== 'glossary') {
    state.panelStack.push({ type: 'glossary', id: null });
  }
  state.isPanelOpen = true;
  activateScrollLock();
}

/**
 * Open a panel with content for a specific step.
 *
 * @param {string} panelType - 'layer1', 'layer2', or 'glossary'.
 * @param {string} contentId - The step number whose content to show.
 */
export function openPanel(panelType, contentId) {
  const panelId = `panel-${panelType}`;
  const panel = document.getElementById(panelId);

  if (!panel) return;

  const content = getPanelContent(panelType, contentId);

  if (content) {
    const titleElement = document.getElementById(`${panelId}-title`);
    // Author-supplied title via textContent (no HTML interpretation); demo badge
    // appended as a built element. content.html below stays innerHTML — it is
    // intentionally markdownified HTML.
    titleElement.textContent = content.title;
    if (content.demo) {
      const demoBadgeText = window.telarLang?.demoPanelBadge || 'Demo content';
      const badge = document.createElement('span');
      badge.className = 'demo-badge-inline';
      badge.style.marginLeft = '0.5rem';
      badge.textContent = demoBadgeText;
      titleElement.appendChild(badge);
    }
    const contentElement = document.getElementById(`${panelId}-content`);
    contentElement.innerHTML = content.html;

    // Assign deep-link running numbers to glossary links. The class is the one
    // scripts/telar/glossary.py writes for a resolved term; an unresolved term
    // is a span that opens nothing, so it takes no number.
    const glossaryLinks = contentElement.querySelectorAll('.glossary-inline-link');
    glossaryLinks.forEach((el, i) => {
      el.dataset.deepLinkN = i + 1;
    });

    // Update hash when a glossary link is clicked
    glossaryLinks.forEach((el) => {
      el.addEventListener('click', () => {
        writeHashWithGlossary(parseInt(el.dataset.deepLinkN, 10));
      });
    });

    // Re-render LaTeX in dynamically loaded panel content
    if (window.telarRenderLatex) {
      window.telarRenderLatex(contentElement);
    }

    // Update panel stack
    if (panelType === 'layer1') {
      state.panelStack = [{ type: panelType, id: contentId }];
    } else {
      state.panelStack.push({ type: panelType, id: contentId });
    }

    const bsOffcanvas = bootstrap.Offcanvas.getInstance(panel) || new bootstrap.Offcanvas(panel);
    bsOffcanvas.show();

    state.isPanelOpen = true;
    activateScrollLock();
    writeHash();
  }
}

/**
 * Close a panel by type.
 *
 * After the Bootstrap close animation completes, checks whether any panels
 * remain open. If none do, deactivates the scroll lock.
 *
 * @param {string} panelType - 'layer1', 'layer2', or 'glossary'.
 */
export function closePanel(panelType) {
  const panelId = `panel-${panelType}`;
  const panel = document.getElementById(panelId);

  if (!panel) return;

  const bsOffcanvas = bootstrap.Offcanvas.getInstance(panel);
  if (bsOffcanvas) {
    bsOffcanvas.hide();
  }

  // closePanel is the single owner of stack mutation on close: drop the closing
  // panel from the stack, then write the hash from the updated stack. The URL
  // reverts to step-only (or the panel below) immediately, without waiting for
  // the Bootstrap close animation (350ms). There is no temporary shared-state
  // swap here, so this is exception-safe — nothing to leak if writeHash throws.
  state.panelStack = state.panelStack.filter(p => p.type !== panelType);
  writeHash();

  // Wait for Bootstrap animation before checking panel state
  setTimeout(() => {
    if (!anyPanelOpen()) {
      state.isPanelOpen = false;
      deactivateScrollLock();
    }
  }, 350);
}

/**
 * Close the topmost panel in the stack.
 */
export function closeTopPanel() {
  if (state.panelStack.length > 0) {
    const top = state.panelStack[state.panelStack.length - 1];
    // closePanel removes `top` from the stack itself; closeTopPanel must not
    // also pop it, or the stack mutation double-counts.
    closePanel(top.type);
  }
}

/**
 * Close every open panel, topmost first, each as its own back button closes
 * it.
 *
 * The stack, the fragment and the scroll lock go as they do for any close, so
 * the story stays frozen until the last panel has gone. A control that moves
 * the story while panels are open (Back to Start, a contents link) closes them
 * here before it moves.
 */
export function closeAllPanels() {
  [...state.panelStack].reverse().forEach((p) => closePanel(p.type));
}

// ── Panel content ────────────────────────────────────────────────────────────

/**
 * Get panel content for a step from the story data.
 *
 * Only 'layer1' and 'layer2' are handled here — the glossary panel is
 * driven separately by telar.js writing directly into
 * #panel-glossary-content, not through openPanel()/getPanelContent().
 *
 * A panel with no title of its own is headed by the label of the button that
 * opened it, and a blank button carries the site language's default label, so
 * the fallback is that same translated string. The heading is not left empty:
 * an empty <h1> is still announced as a heading, with nothing to read.
 *
 * @param {string} panelType - 'layer1' or 'layer2'.
 * @param {string} contentId - The step number.
 * @returns {{ title: string, html: string, demo?: boolean }|null}
 */
function getPanelContent(panelType, contentId) {
  const steps = window.storyData?.steps || [];
  const step = steps.find(s => s.step == contentId);

  if (!step) return null;

  if (panelType === 'layer1') {
    let html = formatPanelContent({
      text: step.layer1_text,
      media: step.layer1_media,
    }, step.object);

    // Add Layer 2 button if content exists
    if ((step.layer2_title && step.layer2_title.trim() !== '') || (step.layer2_text && step.layer2_text.trim() !== '')) {
      const buttonLabel = (step.layer2_button && step.layer2_button.trim() !== '') ? step.layer2_button : window.telarLang.goDeeper;
      html += `<p><button class="panel-trigger" data-panel="layer2" data-step="${contentId}">${escapeHtml(buttonLabel)} →</button></p>`;
    }

    return {
      title: step.layer1_title || step.layer1_button || window.telarLang.learnMore,
      html: html,
      demo: step.layer1_demo || false,
    };
  } else if (panelType === 'layer2') {
    return {
      title: step.layer2_title || step.layer2_button || window.telarLang.goDeeper,
      html: formatPanelContent({
        text: step.layer2_text,
        media: step.layer2_media,
      }, step.object),
      demo: step.layer2_demo || false,
    };
  }

  return null;
}

/**
 * Format panel content (text + media) into HTML.
 *
 * Text arrives pre-rendered as HTML from the build pipeline. Image URLs
 * may need the base path prepended. Media fields add an image element.
 *
 * @param {{ text?: string, media?: string }} panelData
 * @param {string} [objectId] - Object ID for dynamic alt text lookup
 * @returns {string} Formatted HTML.
 */
function formatPanelContent(panelData, objectId) {
  let html = '';
  const basePath = getBasePath();

  if (panelData.text) {
    html += fixImageUrls(panelData.text, basePath);
  }

  if (panelData.media && panelData.media.trim() !== '') {
    let mediaUrl = panelData.media;
    if (mediaUrl.startsWith('/') && !mediaUrl.startsWith('//')) {
      mediaUrl = basePath + mediaUrl;
    }
    // Dynamic alt text from object data
    const objectsData = window.objectsData || [];
    const panelObj = objectId ? (objectsData.find(o => o.object_id === objectId) || {}) : {};
    const panelAlt = panelObj.alt_text || panelObj.title || objectId || 'Panel image';
    // Escape author-supplied attribute values so a quote in alt_text (or the
    // media path) cannot break out of the attribute. The surrounding markup is
    // fixed, so string assembly with escaped values is equivalent DOM output.
    html += `<img src="${escapeHtml(mediaUrl)}" alt="${escapeHtml(panelAlt)}" class="img-fluid">`;
  }

  return html;
}

// ── Panel content checks (for keyboard navigation) ──────────────────────────

/**
 * Check if a step has Layer 1 content.
 *
 * @param {Object} step - Step data from window.storyData.
 * @returns {boolean}
 */
export function stepHasLayer1Content(step) {
  if (!step) return false;
  return (step.layer1_title && step.layer1_title.trim() !== '') ||
         (step.layer1_text && step.layer1_text.trim() !== '');
}

/**
 * Check if a step has Layer 2 content.
 *
 * @param {Object} step - Step data from window.storyData.
 * @returns {boolean}
 */
export function stepHasLayer2Content(step) {
  if (!step) return false;
  return (step.layer2_title && step.layer2_title.trim() !== '') ||
         (step.layer2_text && step.layer2_text.trim() !== '');
}

// ── Scroll lock ──────────────────────────────────────────────────────────────

/**
 * Set up the scroll lock system.
 *
 * Creates a subtle backdrop element and registers a click handler on the
 * story container to close the topmost panel when the user clicks outside it.
 *
 * The card-stack layout has no scrollable narrative column to toggle overflow
 * on, so the backdrop and click-outside listener are wired unconditionally.
 */
export function initializeScrollLock() {
  const backdrop = document.createElement('div');
  backdrop.id = 'panel-backdrop';
  backdrop.style.cssText = `
    position: fixed;
    inset: -50px;
    background: var(--color-panel-backdrop);
    z-index: var(--z-panel-backdrop);
    display: none;
    pointer-events: none;
  `;
  document.body.appendChild(backdrop);

  // Click outside to close panels
  const storyContainer = document.querySelector('.story-container');
  if (storyContainer) {
    storyContainer.addEventListener('click', function (e) {
      if (state.isPanelOpen &&
          !e.target.closest('.offcanvas') &&
          !e.target.closest('[data-panel]') &&
          !e.target.closest('.share-button')) {
        closeTopPanel();
      }
    });
  }
}

/**
 * Activate scroll lock — blocks step navigation and shows backdrop.
 *
 * Also stops Lenis so wheel events do not cause scroll position changes
 * while a panel is open. Safe to call when Lenis is not initialised
 * (button navigation) — the call is skipped.
 */
export function activateScrollLock() {
  state.scrollLockActive = true;
  if (state.lenis) state.lenis.stop();
  const backdrop = document.getElementById('panel-backdrop');
  if (backdrop) {
    backdrop.style.display = 'block';
  }
}

/**
 * Deactivate scroll lock — allows step navigation and hides backdrop.
 *
 * Also resumes Lenis after a panel closes. Safe to call when Lenis is
 * not initialised (button navigation).
 */
export function deactivateScrollLock() {
  state.scrollLockActive = false;
  if (state.lenis) state.lenis.start();
  const backdrop = document.getElementById('panel-backdrop');
  if (backdrop) {
    backdrop.style.display = 'none';
  }
}
