/**
 * Telar — site-wide panel and glossary behaviour.
 *
 * This is the small layer of interactivity that every Telar page loads,
 * independent of the story viewer. It wires up the slide-in offcanvas panels and
 * the glossary that those panels can host.
 *
 * Panel triggers — any element marked as a `.panel-trigger` opens the offcanvas
 * panel named in its `data-panel` attribute, using Bootstrap's Offcanvas component
 * (the same toolkit that powers the rest of the layout's modals and navigation).
 *
 * Glossary flow — glossary terms appear two ways: as entries on the glossary index
 * and as inline `[[term_id]]` links woven into story prose. Rather than navigating
 * away, clicking either kind fetches the term's own page, parses out its title and
 * `.glossary-content`, and injects that into the shared glossary panel. The fetch is
 * deliberate: glossary pages are real, independently linkable URLs, so the panel is
 * just a convenient in-place view of content that also stands on its own. Because the
 * injected content may itself contain glossary links — and may contain mathematical
 * notation — we re-initialise glossary links and re-run LaTeX rendering on the freshly
 * loaded fragment. Re-opening an already-open panel waits for it to finish hiding
 * before loading the new term, so the swap reads as a clean transition.
 *
 * Click-outside-to-close — registered globally so the glossary panel dismisses on an
 * outside click on any page, while clicks on panels, glossary links and triggers are
 * left alone so they can do their own work.
 *
 * Glossary clicks are wired with a single delegated document listener
 * (`initializeGlossaryDelegation`), so any glossary link works no matter when it
 * enters the DOM — including story cards the viewer builds and clones at runtime,
 * whose cloned nodes would lose a per-element handler. `initializeGlossaryLinks`
 * is retained as a no-op for callers that still invoke it.
 *
 * PanelStack — a tiny last-in-first-out record of which panels are layered (for
 * example Layer 1 to Layer 2 to glossary), exposed on `window.Telar`.
 *
 * @version v1.5.1
 */

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', function() {
  console.log('Telar initialized');

  // Initialize panel triggers
  initializePanelTriggers();

  // Initialize glossary links via event delegation (one document-level listener
  // that catches clicks on any current or future glossary link — including story
  // cards built or cloned by the viewer at runtime, and panel content loaded later)
  initializeGlossaryDelegation();

  // Initialize glossary back button
  initializeGlossaryBackButton();

  // Initialize click-outside-to-close for glossary panels (works on all pages)
  initializeClickOutsideClose();
});

/**
 * Initialize click-outside-to-close behavior for glossary panels
 * Works on all pages including glossary index, user pages, etc.
 */
function initializeClickOutsideClose() {
  document.addEventListener('click', function(e) {
    const glossaryPanel = document.getElementById('panel-glossary');
    if (!glossaryPanel) return;

    // Check if glossary panel is open
    if (!glossaryPanel.classList.contains('show')) return;

    // Don't close if clicking inside any panel
    if (e.target.closest('.offcanvas')) return;

    // Don't close if clicking on glossary links or triggers
    if (e.target.closest('.glossary-term-link')) return;
    if (e.target.closest('.glossary-inline-link')) return;
    if (e.target.closest('[data-panel]')) return;

    // Close the glossary panel
    const bsOffcanvas = bootstrap.Offcanvas.getInstance(glossaryPanel);
    if (bsOffcanvas) {
      bsOffcanvas.hide();
    }
  });
}

/**
 * Initialize panel trigger buttons
 */
function initializePanelTriggers() {
  const triggers = document.querySelectorAll('.panel-trigger');

  triggers.forEach(trigger => {
    trigger.addEventListener('click', function(e) {
      e.preventDefault();
      const panelId = this.dataset.panel;
      const panel = document.getElementById(panelId);

      if (panel) {
        const bsOffcanvas = new bootstrap.Offcanvas(panel);
        bsOffcanvas.show();
      }
    });
  });
}

/**
 * Panel stacking system
 * Handles multiple panel layers (Layer 1 -> Layer 2 -> Glossary)
 */
class PanelStack {
  constructor() {
    this.stack = [];
  }

  push(panelId) {
    this.stack.push(panelId);
  }

  pop() {
    return this.stack.pop();
  }

  getCurrent() {
    return this.stack[this.stack.length - 1];
  }
}

// Export for use in chapter pages
window.Telar = {
  PanelStack: new PanelStack(),
  initializeGlossaryLinks: initializeGlossaryLinks // Retained no-op; clicks are delegated
};

/**
 * Register a single delegated click listener for glossary links.
 *
 * Glossary links open the glossary panel instead of navigating. Rather than
 * binding each link individually, one document-level listener catches clicks on
 * any `.glossary-term-link` (glossary index) or `.glossary-inline-link` (inline
 * [[term_id]] / [[term_id|display]] links in story prose and panels). Delegation
 * is essential because the story viewer builds and clones cards at runtime —
 * cloned nodes lose per-element handlers, but a delegated listener catches their
 * clicks regardless of when they enter the DOM. Registered once at startup.
 */
function initializeGlossaryDelegation() {
  document.addEventListener('click', function(e) {
    const link = e.target.closest('.glossary-term-link, .glossary-inline-link');
    if (!link) return;
    handleGlossaryLinkClick(e, link);
  });
}

/**
 * Retained for API compatibility.
 *
 * Click handling is now delegated at the document level by
 * initializeGlossaryDelegation(), so per-element binding is no longer needed.
 * This is a deliberate no-op, kept because panels.js and the panel content loader
 * (and possibly user/site code) still call window.Telar.initializeGlossaryLinks()
 * after injecting dynamic content — delegation already covers that content.
 *
 * @param {Element} container - Ignored.
 */
function initializeGlossaryLinks(container) {
  // No-op: glossary clicks are handled via delegation. See initializeGlossaryDelegation().
}

/**
 * Handle a glossary link click.
 *
 * Opens the glossary panel with the term content fetched from the term's URL.
 * Constructs the URL dynamically to properly handle baseurl configuration.
 *
 * @param {Event} e - Click event
 * @param {Element} link - The glossary link element (resolved via event delegation)
 */
function handleGlossaryLinkClick(e, link) {
  e.preventDefault();
  const termId = link.dataset.termId;
  const termTitle = link.textContent.trim();
  const isDemo = link.dataset.demo === 'true';

  // Use the pre-computed URL from the data attribute if available
  let termUrl = link.dataset.termUrl;
  if (!termUrl) {
    // Fallback: construct URL (for inline links that may not have data-term-url)
    const pathParts = window.location.pathname.split('/').filter(p => p);
    let basePath = '';
    if (pathParts.length >= 2) {
      basePath = '/' + pathParts.slice(0, -2).join('/');
    }
    termUrl = basePath + '/glossary/' + encodeURIComponent(termId) + '/';
  }

  openGlossaryPanel(termUrl, termTitle, isDemo);
}

/**
 * Fetch glossary term content and open in panel
 */
function openGlossaryPanel(termUrl, termTitle, isDemo = false) {
  const panel = document.getElementById('panel-glossary');
  const titleElement = document.getElementById('panel-glossary-title');
  const contentElement = document.getElementById('panel-glossary-content');

  if (!panel || !titleElement || !contentElement) {
    console.error('Glossary panel elements not found');
    return;
  }

  const bsOffcanvas = bootstrap.Offcanvas.getInstance(panel) || new bootstrap.Offcanvas(panel);

  // Check if panel is already open
  if (panel.classList.contains('show')) {
    // Panel is open - close it first, then reopen with new content
    panel.addEventListener('hidden.bs.offcanvas', function onHidden() {
      // Remove this listener so it doesn't fire again
      panel.removeEventListener('hidden.bs.offcanvas', onHidden);

      // Now open with new content
      loadAndShowGlossaryTerm(panel, titleElement, contentElement, termUrl, termTitle, bsOffcanvas, isDemo);
    }, { once: true });

    bsOffcanvas.hide();
  } else {
    // Panel is closed - just open it
    loadAndShowGlossaryTerm(panel, titleElement, contentElement, termUrl, termTitle, bsOffcanvas, isDemo);
  }
}

/**
 * Load glossary term content and show panel
 */
function loadAndShowGlossaryTerm(panel, titleElement, contentElement, termUrl, termTitle, bsOffcanvas, isDemo = false) {
  // Set temporary title from link text (will be replaced with actual title from page).
  // Use textContent for the author-supplied term title (no HTML interpretation),
  // and append the demo badge as a built element rather than an HTML string.
  titleElement.textContent = termTitle;
  if (isDemo) {
    const demoBadgeText = window.telarLang?.demoPanelBadge || 'Demo content';
    const badge = document.createElement('span');
    badge.className = 'demo-badge-inline';
    badge.style.marginLeft = '0.5rem';
    badge.textContent = demoBadgeText;
    titleElement.appendChild(badge);
  }

  // Show loading state
  contentElement.innerHTML = '<p class="text-muted">Loading...</p>';

  // Open panel
  bsOffcanvas.show();

  // Fetch term content
  fetch(termUrl)
    .then(response => {
      if (!response.ok) throw new Error('Failed to load glossary term');
      return response.text();
    })
    .then(html => {
      // Parse HTML and extract content
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');

      // Extract the actual title from the page's h1 tag (includes demo badge if present)
      const pageTitle = doc.querySelector('h1');
      if (pageTitle) {
        titleElement.innerHTML = pageTitle.innerHTML;
      }

      const glossaryContent = doc.querySelector('.glossary-content');

      if (glossaryContent) {
        contentElement.innerHTML = glossaryContent.innerHTML;
        // Initialize glossary links within the loaded content (enables glossary-to-glossary linking)
        initializeGlossaryLinks(contentElement);

        // Re-render LaTeX in fetched glossary content
        if (window.telarRenderLatex) {
          window.telarRenderLatex(contentElement);
        }
      } else {
        throw new Error('Glossary content not found');
      }
    })
    .catch(error => {
      console.error('Error loading glossary term:', error);
      contentElement.innerHTML = '<div class="alert alert-danger">Failed to load glossary term. Please try again.</div>';
    });
}

/**
 * Initialize glossary back button
 */
function initializeGlossaryBackButton() {
  const glossaryBack = document.getElementById('panel-glossary-back');
  if (glossaryBack) {
    glossaryBack.addEventListener('click', function() {
      const panel = document.getElementById('panel-glossary');
      if (panel) {
        const bsOffcanvas = bootstrap.Offcanvas.getInstance(panel);
        if (bsOffcanvas) {
          bsOffcanvas.hide();
        }
      }
    });
  }
}
