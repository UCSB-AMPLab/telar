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
 *   glossary link in story or panel content.
 *
 * The panel stack tracks which panels are open and in what order. Closing
 * always removes the topmost panel. The user can close panels with the back
 * button, Escape key, left arrow key, or by clicking outside the panel.
 *
 * When any panel is open, the scroll lock system blocks step navigation
 * (wheel events, keyboard arrows, touch swipes) and shows a subtle backdrop.
 * This is the "panel freeze" system introduced in v0.6.0 — panels are truly
 * modal and must be explicitly dismissed.
 *
 * @version v0.7.0-beta
 */

import { state } from './state.js';
import { getBasePath, fixImageUrls } from './utils.js';

// ── Panel open / close ───────────────────────────────────────────────────────

/**
 * Set up click handlers for panel trigger buttons and back buttons.
 *
 * Layer 1 triggers are static elements with [data-panel="layer1"].
 * Layer 2 triggers are dynamic (added inside Layer 1 content), so they use
 * event delegation on the document.
 */
export function initializePanels() {
  // Layer 1 triggers
  document.querySelectorAll('[data-panel="layer1"]').forEach(trigger => {
    trigger.addEventListener('click', function () {
      const stepNumber = this.dataset.step;
      state.panelStack = [];
      openPanel('layer1', stepNumber);
    });
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
    const demoBadgeText = window.telarLang?.demoPanelBadge || 'Demo content';
    const demoBadge = content.demo ? `<span class="demo-badge-inline" style="margin-left: 0.5rem;">${demoBadgeText}</span>` : '';
    titleElement.innerHTML = content.title + demoBadge;
    const contentElement = document.getElementById(`${panelId}-content`);
    contentElement.innerHTML = content.html;

    // Re-initialise glossary links in dynamically loaded content
    if (window.Telar && window.Telar.initializeGlossaryLinks) {
      window.Telar.initializeGlossaryLinks(contentElement);
    }

    // Update panel stack
    if (panelType === 'layer1') {
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

  // Wait for Bootstrap animation before checking panel state
  setTimeout(() => {
    const anyPanelOpen = document.querySelector('.offcanvas.show');
    if (!anyPanelOpen) {
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
    closePanel(top.type);
    state.panelStack.pop();
  }
}

/**
 * Close all open panels and deactivate scroll lock.
 */
export function closeAllPanels() {
  const openPanels = document.querySelectorAll('.offcanvas.show');
  openPanels.forEach(panel => {
    const bsOffcanvas = bootstrap.Offcanvas.getInstance(panel);
    if (bsOffcanvas) {
      bsOffcanvas.hide();
    }
  });

  state.isPanelOpen = false;
  deactivateScrollLock();
}

// ── Panel content ────────────────────────────────────────────────────────────

/**
 * Get panel content for a step from the story data.
 *
 * @param {string} panelType - 'layer1', 'layer2', or 'glossary'.
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
    });

    // Add Layer 2 button if content exists
    if ((step.layer2_title && step.layer2_title.trim() !== '') || (step.layer2_text && step.layer2_text.trim() !== '')) {
      const buttonLabel = (step.layer2_button && step.layer2_button.trim() !== '') ? step.layer2_button : window.telarLang.goDeeper;
      html += `<p><button class="panel-trigger" data-panel="layer2" data-step="${contentId}">${buttonLabel} →</button></p>`;
    }

    return {
      title: step.layer1_title || step.layer1_button || 'Layer 1',
      html: html,
      demo: step.layer1_demo || false,
    };
  } else if (panelType === 'layer2') {
    return {
      title: step.layer2_title || step.layer2_button || 'Layer 2',
      html: formatPanelContent({
        text: step.layer2_text,
        media: step.layer2_media,
      }),
      demo: step.layer2_demo || false,
    };
  } else if (panelType === 'glossary') {
    return {
      title: 'Glossary Term',
      html: '<p>Glossary content...</p>',
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
 * @returns {string} Formatted HTML.
 */
function formatPanelContent(panelData) {
  if (!panelData) return '<p>No content available.</p>';

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
    html += `<img src="${mediaUrl}" alt="Panel image" class="img-fluid">`;
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
 */
export function initializeScrollLock() {
  const narrativeColumn = document.querySelector('.narrative-column');
  if (!narrativeColumn) return;

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
 */
export function activateScrollLock() {
  state.scrollLockActive = true;
  const backdrop = document.getElementById('panel-backdrop');
  if (backdrop) {
    backdrop.style.display = 'block';
  }
  const narrativeColumn = document.querySelector('.narrative-column');
  if (narrativeColumn) {
    narrativeColumn.style.overflow = 'hidden';
  }
}

/**
 * Deactivate scroll lock — allows step navigation and hides backdrop.
 */
export function deactivateScrollLock() {
  state.scrollLockActive = false;
  const backdrop = document.getElementById('panel-backdrop');
  if (backdrop) {
    backdrop.style.display = 'none';
  }
  const narrativeColumn = document.querySelector('.narrative-column');
  if (narrativeColumn) {
    narrativeColumn.style.overflow = '';
  }
}
