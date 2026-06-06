/**
 * Telar — embed mode.
 *
 * Telar stories are often shown inside an iframe on another platform — a Canvas LMS
 * page, a course module, a blog post — where the surrounding site chrome would be
 * noise. This script detects that situation and trims the experience down to the
 * story itself.
 *
 * Detection — a story is in embed mode when its URL carries `?embed=true`. The result
 * is published on `window.telarEmbed` so other scripts can branch on it, and when
 * active an `embed-mode` class is added to the body for the stylesheet to hide chrome
 * against. The body-class work waits for the DOM if the document is still loading, and
 * runs immediately otherwise.
 *
 * "View full site" banner — embedding hides the way back to the full site, so we add a
 * small dismissible banner offering a link to it. Its wording comes from
 * `window.telarLang` (set by the Jekyll layout) so the banner speaks the site's
 * language; if those strings are absent — a layout that never set them — the banner is
 * simply skipped rather than risking a broken render. The site name fills a
 * `{site_name}` placeholder via a function replacement, so any `$`-sequences in the
 * name are inserted literally. The full-site URL is derived from the current location
 * by stripping everything from `/stories/` onward, falling back to the bare origin.
 *
 * The whole file is an IIFE so none of this leaks into the global scope beyond the
 * single `window.telarEmbed` flag.
 *
 * @version v1.5.0
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
    const embedStrings = window.telarLang && window.telarLang.embedBanner;
    if (!embedStrings) return; // layout without telarLang — no banner, no crash

    // Replace {site_name} placeholder. Use a function replacement so $-sequences
    // ($&, $$, $', $`) in the site name are inserted literally, not expanded.
    const bannerText = embedStrings.text.replace('{site_name}', () => siteName);

    // Create banner element
    const banner = document.createElement('div');
    banner.className = 'telar-embed-banner';
    banner.innerHTML = `
      <span class="telar-embed-banner-text">
        <svg class="icon" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>
        <span>${bannerText}</span>
        <a href="${fullSiteUrl}" class="telar-embed-banner-link" target="_blank" rel="noopener noreferrer">${embedStrings.link}</a>
      </span>
      <button class="telar-embed-banner-close" aria-label="Close" title="Close">
        <svg class="icon" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
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
