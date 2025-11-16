/**
 * Telar Embed Mode
 * Handles iframe embedding for Canvas LMS and other platforms
 */

(function() {
  'use strict';

  // Parse URL parameters
  const urlParams = new URLSearchParams(window.location.search);
  const embedMode = urlParams.get('embed') === 'true';
  const embedSection = urlParams.get('section');
  const embedLang = urlParams.get('lang');

  // Store embed parameters globally for other scripts to access
  window.telarEmbed = {
    enabled: embedMode,
    section: embedSection ? parseInt(embedSection, 10) : null,
    lang: embedLang
  };

  // Apply embed mode if enabled
  if (embedMode) {
    // Add embed class to body for CSS styling
    document.body.classList.add('embed-mode');

    console.log('[Telar Embed] Embed mode enabled');
    if (embedSection) {
      console.log('[Telar Embed] Target section:', embedSection);
    }
    if (embedLang) {
      console.log('[Telar Embed] Language override:', embedLang);
    }
  }
})();
