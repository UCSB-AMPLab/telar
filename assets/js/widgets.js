/**
 * Telar Widget System JavaScript
 * Handles initialization and interactivity for widgets
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
