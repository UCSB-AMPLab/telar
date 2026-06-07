/**
 * Telar — widget client behaviour.
 *
 * Telar's content widgets — tabs, accordions, carousels — are built on Bootstrap.
 * Most of them need no custom code: Bootstrap's data attributes drive tabs and
 * accordions on their own. The one exception is the carousel, which is initialised
 * here so we can override its defaults to suit a storytelling context.
 *
 * Carousels — each `.telar-widget-carousel` is set up for manual navigation only.
 * Auto-advance is off (`interval: false`) because a slideshow that moves on its own
 * fights the reader's pace; keyboard control is off because arrow keys belong to
 * Telar's own story navigation and a focused carousel must not steal them; wrapping
 * and touch/swipe stay on so the carousel feels natural to page through by hand.
 *
 * Re-initialisation — widgets can arrive after first paint when Telar's story
 * navigation loads panel content dynamically, so initialisation runs both on the
 * initial DOM-ready (or immediately, if the document is already parsed) and again
 * whenever a `panelLoaded` event fires, ensuring any newly injected carousels are
 * wired up.
 *
 * Wrapped in an IIFE to keep its helpers out of the global scope.
 *
 * @version v0.5.0-beta
 */

(function() {
  'use strict';

  /**
   * Initialize all widgets when DOM is ready
   */
  function initWidgets() {
    initCarousels();
    // Tabs and accordions are handled by Bootstrap automatically
  }

  /**
   * Initialize Bootstrap carousels with manual navigation
   */
  function initCarousels() {
    const carouselWidgets = document.querySelectorAll('.telar-widget-carousel');

    carouselWidgets.forEach(function(widget) {
      const carouselElement = widget.querySelector('.carousel');

      if (!carouselElement) return;

      // Initialize Bootstrap carousel with manual navigation only
      const carousel = new bootstrap.Carousel(carouselElement, {
        interval: false,  // No auto-advance
        wrap: true,       // Allow wrapping from last to first
        keyboard: false,  // Disable keyboard navigation (interferes with story navigation)
        touch: true       // Enable touch/swipe
      });
    });
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initWidgets);
  } else {
    // DOM is already ready
    initWidgets();
  }

  // Re-initialize when panels are dynamically loaded
  // (for Telar's story navigation system)
  document.addEventListener('panelLoaded', initWidgets);
})();
