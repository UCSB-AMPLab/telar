/**
 * Telar — site-wide panel and glossary behaviour.
 *
 * This is the small layer of interactivity that every Telar page loads,
 * independent of the story viewer. It wires up the glossary panel and the
 * click-outside-to-close behaviour shared by all offcanvas panels; the layer1/
 * layer2 story panel triggers themselves are handled by the delegated listener
 * in `telar-story/panels.js`.
 *
 * Glossary flow — glossary terms appear two ways: as entries on the glossary index
 * and as inline `[[term_id]]` links woven into story prose. Rather than navigating
 * away, clicking either kind fetches the term's own page, parses out its title and
 * `.glossary-content`, and injects that into the shared glossary panel. The fetch is
 * deliberate: glossary pages are real, independently linkable URLs, so the panel is
 * just a convenient in-place view of content that also stands on its own. Because the
 * injected content may itself contain glossary links (already covered by delegation)
 * and may contain mathematical notation, we re-run LaTeX rendering on the freshly
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
 * whose cloned nodes would lose a per-element handler.
 *
 * Covered content — what an open panel covers is inert: a layer panel under the
 * panel over it, and the page's <main> under the glossary panel. The panels stack
 * in a fixed order (layer 1, layer 2, glossary: nothing opens a lower panel over
 * a higher one), so the topmost open panel is the last open one in that order.
 * The state is recomputed from Bootstrap's show, hide and hidden events, which
 * every way of opening or closing a panel fires, so no close path can leave
 * content inert.
 *
 * Keys outside stories — on a page with no story, Left arrow and Escape close an
 * open glossary panel and are otherwise left to the page. On a story page the
 * story's own keyboard handler closes the topmost panel, glossary included.
 *
 * The covered-content and key functions are exposed on `window.TelarPanels`.
 *
 * @version v1.8.0
 */

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', function() {
  console.log('Telar initialized');

  // Initialize glossary links via event delegation (one document-level listener
  // that catches clicks on any current or future glossary link — including story
  // cards built or cloned by the viewer at runtime, and panel content loaded later)
  initializeGlossaryDelegation();

  // Initialize glossary back button
  initializeGlossaryBackButton();

  // Initialize click-outside-to-close for glossary panels (works on all pages)
  initializeClickOutsideClose();

  initializeCoveredContent();
  initializeGlossaryKeys();
});

// ── Covered content ──────────────────────────────────────────────────────────

/** The panels, lowest first. */
const PANEL_ORDER = ['layer1', 'layer2', 'glossary'];

/**
 * Whether a panel is open or on its way in, and not on its way out.
 *
 * @param {Element} panel
 * @returns {boolean}
 */
function isPanelOpen(panel) {
  const cls = panel.classList;
  return (cls.contains('show') || cls.contains('showing')) && !cls.contains('hiding');
}

/**
 * The open panels, lowest first.
 *
 * A panel whose show or hide event is being handled has not yet changed its
 * classes, so it is named explicitly.
 *
 * @param {Element|null} opening - A panel about to open.
 * @param {Element|null} closing - A panel about to close.
 * @returns {Element[]}
 */
function openPanelsInOrder(opening, closing) {
  return PANEL_ORDER
    .map((type) => document.getElementById(`panel-${type}`))
    .filter((panel) => panel && panel !== closing && (panel === opening || isPanelOpen(panel)));
}

/**
 * Make inert what the open panels cover, and nothing else.
 *
 * Every open panel below the topmost is inert, and so is the page's <main>
 * while the glossary panel is open.
 *
 * @param {Element|null} [opening=null] - A panel about to open.
 * @param {Element|null} [closing=null] - A panel about to close.
 */
function syncCoveredContent(opening = null, closing = null) {
  const open = openPanelsInOrder(opening, closing);
  const top = open[open.length - 1];
  PANEL_ORDER.forEach((type) => {
    const panel = document.getElementById(`panel-${type}`);
    if (panel) panel.toggleAttribute('inert', open.includes(panel) && panel !== top);
  });
  const main = document.querySelector('main');
  if (main) main.toggleAttribute('inert', open.some((panel) => panel.id === 'panel-glossary'));
}

/**
 * Recompute covered content whenever a Telar panel opens or closes.
 *
 * Bootstrap's offcanvas events bubble, so one document listener per event
 * hears every panel. The share panel is an offcanvas too, and is left out.
 */
function initializeCoveredContent() {
  const isTelarPanel = (e) => e.target.matches?.('[data-telar-panel]') && !e.defaultPrevented;
  document.addEventListener('show.bs.offcanvas', (e) => {
    if (isTelarPanel(e)) syncCoveredContent(e.target, null);
  });
  document.addEventListener('hide.bs.offcanvas', (e) => {
    if (isTelarPanel(e)) syncCoveredContent(null, e.target);
  });
  document.addEventListener('hidden.bs.offcanvas', (e) => {
    if (isTelarPanel(e)) syncCoveredContent();
  });
}

// ── Keys outside stories ─────────────────────────────────────────────────────

/**
 * Close an open glossary panel on Left arrow or Escape.
 *
 * The key is cancelled only when there is a panel to close.
 *
 * @param {KeyboardEvent} e
 */
function closeGlossaryOnKey(e) {
  if (e.key !== 'ArrowLeft' && e.key !== 'Escape') return;
  const panel = document.getElementById('panel-glossary');
  if (!panel || !isPanelOpen(panel)) return;

  e.preventDefault();
  bootstrap.Offcanvas.getInstance(panel)?.hide();
}

/**
 * Wire the glossary keys on pages with no story; a story page's own handler
 * closes the topmost panel there.
 */
function initializeGlossaryKeys() {
  if (document.body.classList.contains('story-page')) return;
  document.addEventListener('keydown', closeGlossaryOnKey);
}

window.TelarPanels = { syncCoveredContent, closeGlossaryOnKey };

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
