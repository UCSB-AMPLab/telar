/**
 * Telar Embed Mode
 * Handles iframe embedding for Canvas LMS and other platforms
 *
 * @version v0.5.0-beta
 */

(function() {
  'use strict';

  // Parse URL parameters
  const urlParams = new URLSearchParams(window.location.search);
  const embedMode = urlParams.get('embed') === 'true';

  // Store embed state globally for other scripts to access
  window.telarEmbed = {
    enabled: embedMode
  };

  // Apply embed mode if enabled
  if (embedMode) {
    console.log('[Telar Embed] Embed mode enabled');

    // Add embed class to body when DOM is ready
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function() {
        document.body.classList.add('embed-mode');
        createEmbedBanner();
      });
    } else {
      document.body.classList.add('embed-mode');
      createEmbedBanner();
    }
  }

  /**
   * Create dismissible "View full site" banner
   */
  function createEmbedBanner() {
    // Get site name from meta tag or default
    const siteName = document.querySelector('meta[property="og:site_name"]')?.content || 'the full site';

    // Get full site URL (remove embed parameter)
    const fullSiteUrl = getFullSiteUrl();

    // Get language strings from window.telarLang (set by Jekyll in layout)
    const embedStrings = window.telarLang.embedBanner;

    // Replace {site_name} placeholder in banner text
    const bannerText = embedStrings.text.replace('{site_name}', siteName);

    // Create banner element
    const banner = document.createElement('div');
    banner.className = 'telar-embed-banner';
    banner.innerHTML = `
      <span class="telar-embed-banner-text">
        <span class="material-symbols-outlined">open_in_new</span>
        <span>${bannerText}</span>
        <a href="${fullSiteUrl}" class="telar-embed-banner-link" target="_blank" rel="noopener noreferrer">${embedStrings.link}</a>
      </span>
      <button class="telar-embed-banner-close" aria-label="Close" title="Close">
        <span class="material-symbols-outlined">close</span>
      </button>
    `;

    // Insert at top of body
    document.body.insertBefore(banner, document.body.firstChild);

    // Handle dismiss
    const closeButton = banner.querySelector('.telar-embed-banner-close');
    if (closeButton) {
      closeButton.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        banner.remove();
        console.log('[Telar Embed] Banner dismissed');
      });
      console.log('[Telar Embed] Banner created with close button');
    } else {
      console.error('[Telar Embed] Close button not found');
    }
  }

  /**
   * Get site homepage URL
   */
  function getFullSiteUrl() {
    const url = new URL(window.location.href);
    // Get the base path by removing the story path (everything after /stories/)
    const pathname = url.pathname;
    const basePathMatch = pathname.match(/^(.*?\/?)stories\//);
    if (basePathMatch) {
      // Return base URL (origin + path before /stories/)
      return url.origin + basePathMatch[1];
    }
    // Fallback: return origin
    return url.origin + '/';
  }
})();
