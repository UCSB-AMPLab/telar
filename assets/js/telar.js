/**
 * Telar - Digital Storytelling Framework
 * Main JavaScript file
 *
 * @version v0.5.0-beta
 */

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', function() {
  console.log('Telar initialized');

  // Initialize panel triggers
  initializePanelTriggers();

  // Initialize glossary links
  initializeGlossaryLinks();

  // Initialize glossary back button
  initializeGlossaryBackButton();
});

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
  PanelStack: new PanelStack()
};

/**
 * Initialize glossary term links to open panel instead of navigating
 */
function initializeGlossaryLinks() {
  const glossaryLinks = document.querySelectorAll('.glossary-term-link');

  glossaryLinks.forEach(link => {
    link.addEventListener('click', function(e) {
      e.preventDefault();
      const termUrl = this.dataset.termUrl;
      const termTitle = this.textContent.trim();

      openGlossaryPanel(termUrl, termTitle);
    });
  });
}

/**
 * Fetch glossary term content and open in panel
 */
function openGlossaryPanel(termUrl, termTitle) {
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
      loadAndShowGlossaryTerm(panel, titleElement, contentElement, termUrl, termTitle, bsOffcanvas);
    }, { once: true });

    bsOffcanvas.hide();
  } else {
    // Panel is closed - just open it
    loadAndShowGlossaryTerm(panel, titleElement, contentElement, termUrl, termTitle, bsOffcanvas);
  }
}

/**
 * Load glossary term content and show panel
 */
function loadAndShowGlossaryTerm(panel, titleElement, contentElement, termUrl, termTitle, bsOffcanvas) {
  // Set title
  titleElement.textContent = termTitle;

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
      const glossaryContent = doc.querySelector('.glossary-content');

      if (glossaryContent) {
        contentElement.innerHTML = glossaryContent.innerHTML;
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
