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

    // Create "View full site" banner when DOM is ready
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', createEmbedBanner);
    } else {
      createEmbedBanner();
    }
  }

  /**
   * Create dismissible "View full site" banner
   */
  function createEmbedBanner() {
    // Check if already dismissed this session
    if (sessionStorage.getItem('telarEmbedBannerDismissed') === 'true') {
      console.log('[Telar Embed] Banner previously dismissed');
      return;
    }

    // Get site name from meta tag or default
    const siteName = document.querySelector('meta[property="og:site_name"]')?.content || 'the full site';

    // Get full site URL (remove embed parameter)
    const fullSiteUrl = getFullSiteUrl();

    // Create banner element
    const banner = document.createElement('div');
    banner.className = 'telar-embed-banner';
    banner.innerHTML = `
      <span class="telar-embed-banner-text">
        <span class="material-symbols-outlined">open_in_new</span>
        <a href="${fullSiteUrl}" target="_blank" rel="noopener noreferrer">View this story on ${siteName}</a>
      </span>
      <button class="telar-embed-banner-close" aria-label="Close" title="Close">
        <span class="material-symbols-outlined">close</span>
      </button>
    `;

    // Insert at top of body
    document.body.insertBefore(banner, document.body.firstChild);

    // Handle dismiss
    const closeButton = banner.querySelector('.telar-embed-banner-close');
    closeButton.addEventListener('click', function() {
      sessionStorage.setItem('telarEmbedBannerDismissed', 'true');
      banner.style.display = 'none';
      console.log('[Telar Embed] Banner dismissed');
    });

    console.log('[Telar Embed] Banner created');
  }

  /**
   * Get full site URL without embed parameter
   */
  function getFullSiteUrl() {
    const url = new URL(window.location.href);
    url.searchParams.delete('embed');
    return url.toString();
  }
})();
