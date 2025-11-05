/**
 * Telar Widget System JavaScript
 * Handles initialization and interactivity for widgets
 */

(function() {
  'use strict';

  /**
   * Initialize all widgets when DOM is ready
   */
  function initWidgets() {
    initCarousels();
    initComparisonSliders();
    // Tabs and accordions are handled by Bootstrap automatically
  }

  /**
   * Initialize Bootstrap carousels with manual navigation
   */
  function initCarousels() {
    const carousels = document.querySelectorAll('.telar-widget-carousel .carousel');

    carousels.forEach(function(carouselElement) {
      // Initialize Bootstrap carousel with manual navigation only
      const carousel = new bootstrap.Carousel(carouselElement, {
        interval: false,  // No auto-advance
        wrap: true,       // Allow wrapping from last to first
        keyboard: true,   // Enable keyboard navigation
        touch: true       // Enable touch/swipe
      });
    });
  }

  /**
   * Initialize comparison sliders (before/after widgets)
   */
  function initComparisonSliders() {
    const sliders = document.querySelectorAll('.comparison-slider');

    sliders.forEach(function(slider) {
      const input = slider.querySelector('.comparison-slider-input');
      const afterDiv = slider.querySelector('.comparison-after');
      const divider = slider.querySelector('.comparison-divider');

      if (!input || !afterDiv || !divider) {
        console.warn('Comparison slider missing required elements');
        return;
      }

      /**
       * Update slider position
       */
      function updateSliderPosition(value) {
        const percentage = value + '%';
        afterDiv.style.width = percentage;
        divider.style.left = percentage;
      }

      // Listen for slider input
      input.addEventListener('input', function() {
        updateSliderPosition(this.value);
      });

      // Set initial position
      updateSliderPosition(input.value || 50);

      // Add keyboard support for better accessibility
      input.addEventListener('keydown', function(e) {
        const step = e.shiftKey ? 10 : 1;
        let newValue = parseInt(this.value);

        if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
          newValue = Math.max(0, newValue - step);
          this.value = newValue;
          updateSliderPosition(newValue);
          e.preventDefault();
        } else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
          newValue = Math.min(100, newValue + step);
          this.value = newValue;
          updateSliderPosition(newValue);
          e.preventDefault();
        }
      });

      // Add touch support for mobile
      let isDragging = false;

      function handleTouchMove(e) {
        if (!isDragging) return;

        const rect = slider.getBoundingClientRect();
        const touchX = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
        const percentage = Math.max(0, Math.min(100, (touchX / rect.width) * 100));

        input.value = percentage;
        updateSliderPosition(percentage);

        e.preventDefault();
      }

      function handleTouchEnd() {
        isDragging = false;
        document.removeEventListener('mousemove', handleTouchMove);
        document.removeEventListener('mouseup', handleTouchEnd);
        document.removeEventListener('touchmove', handleTouchMove);
        document.removeEventListener('touchend', handleTouchEnd);
      }

      slider.addEventListener('mousedown', function(e) {
        if (e.target === input || input.contains(e.target)) {
          isDragging = true;
          handleTouchMove(e);
          document.addEventListener('mousemove', handleTouchMove);
          document.addEventListener('mouseup', handleTouchEnd);
        }
      });

      slider.addEventListener('touchstart', function(e) {
        if (e.target === input || input.contains(e.target)) {
          isDragging = true;
          handleTouchMove(e);
          document.addEventListener('touchmove', handleTouchMove, { passive: false });
          document.addEventListener('touchend', handleTouchEnd);
        }
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
