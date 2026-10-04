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
 * The banner sits over the story's side card, which keeps clear of it, so the window
 * is sent `telar:embed-banner` when the banner is added and again when it is removed.
 *
 * Banner clearance — while the banner shows, `body` carries `embed-banner-shown` and the
 * custom property `--telar-embed-banner-bottom` (px) holds the banner's measured bottom
 * edge, kept current by a ResizeObserver on the banner and a window resize listener.
 * The stylesheet places the previous/next column below that edge; the banner's height varies with the language and the window width, so no fixed
 * offset tracks it. Both go when the banner is dismissed.
 *
 * Compact banner — in a window too short for the full banner and the button column
 * below it, the banner takes the `is-compact` class and shows one line (the stylesheet
 * cuts the text; the link and the close button stay). The decision uses the banner's
 * full height, measured with the class off, so the compact state never feeds back into
 * it; it is taken again whenever the banner or the window changes size. While compact,
 * the published edge is the compact banner's bottom.
 *
 * Its thresholds are those of the column placement in `_embed.scss`.
 *
 * The whole file is an IIFE so none of this leaks into the global scope beyond the
 * single `window.telarEmbed` flag.
 *
 * @version v1.8.0
 */

(function() {
  'use strict';

  // Stops the banner measurement; set while the banner shows
  let stopTracking = null;

  // Sizes of the button column's placement in _embed.scss: it applies in windows up
  // to 480px tall, is a 102px column above 229px and a 45px row from there down; the
  // gap below the banner is 0.75rem and the margin at the bottom of the window 0.5rem.
  const COLUMN_MAX_WINDOW_HEIGHT = 480;
  const ROW_MAX_WINDOW_HEIGHT = 229;
  const COLUMN_HEIGHT = 102;
  const ROW_HEIGHT = 45;

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
    // Get language strings from window.telarLang (set by Jekyll in layout)
    const embedStrings = window.telarLang && window.telarLang.embedBanner;
    if (!embedStrings) return; // layout without telarLang — no banner, no crash

    // Get site name from meta tag, falling back to the localized string from
    // window.telarLang (embedStrings.siteFallback), and finally to the English
    // literal as a last resort if telarLang somehow lacks it. og:site_name is
    // not always present — jekyll-seo-tag is skipped entirely on protected
    // story pages (see _layouts/story.html), so this fallback is a real path,
    // not just defensive code.
    const siteName = document.querySelector('meta[property="og:site_name"]')?.content
      || embedStrings.siteFallback
      || 'the full site';

    // Get full site URL (remove embed parameter)
    const fullSiteUrl = getFullSiteUrl();

    // Replace {site_name} placeholder. Use a function replacement so $-sequences
    // ($&, $$, $', $`) in the site name are inserted literally, not expanded.
    const bannerText = embedStrings.text.replace('{site_name}', () => siteName);

    // Create banner element
    const banner = document.createElement('div');
    banner.className = 'telar-embed-banner';
    banner.innerHTML = `
      <span class="telar-embed-banner-text">
        <svg class="icon" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>
        <span class="telar-embed-banner-message">${bannerText}</span>
        <a href="${fullSiteUrl}" class="telar-embed-banner-link" target="_blank" rel="noopener noreferrer">${embedStrings.link}</a>
      </span>
      <button class="telar-embed-banner-close" aria-label="Close" title="Close">
        <svg class="icon" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
      </button>
    `;

    // Insert at top of body
    document.body.insertBefore(banner, document.body.firstChild);
    // Measured first: the side card refits on the event, against the banner's
    // final height, compact or not.
    trackBannerBottom(banner);
    window.dispatchEvent(new CustomEvent('telar:embed-banner'));

    // Handle dismiss
    const closeButton = banner.querySelector('.telar-embed-banner-close');
    if (closeButton) {
      closeButton.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        banner.remove();
        releaseBannerBottom();
        window.dispatchEvent(new CustomEvent('telar:embed-banner'));
        console.log('[Telar Embed] Banner dismissed');
      });
      console.log('[Telar Embed] Banner created with close button');
    } else {
      console.error('[Telar Embed] Close button not found');
    }
  }

  /**
   * Publish the banner's bottom edge for the stylesheet and keep it current, and
   * make the banner compact where it and the button column do not both fit.
   */
  function trackBannerBottom(banner) {
    const body = document.body;
    const message = banner.querySelector('.telar-embed-banner-message');
    const update = function() {
      banner.classList.remove('is-compact');
      const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
      const windowHeight = window.innerHeight;
      const buttons = windowHeight <= ROW_MAX_WINDOW_HEIGHT ? ROW_HEIGHT : COLUMN_HEIGHT;
      const needed = banner.getBoundingClientRect().bottom + 0.75 * rem + buttons + 0.5 * rem;
      const compact = windowHeight <= COLUMN_MAX_WINDOW_HEIGHT && needed > windowHeight;
      banner.classList.toggle('is-compact', compact);
      if (compact) message.title = message.textContent.trim();
      else message.removeAttribute('title');
      body.style.setProperty('--telar-embed-banner-bottom',
        Math.ceil(banner.getBoundingClientRect().bottom) + 'px');
    };
    update();
    body.classList.add('embed-banner-shown');

    // The window's height alone can change the decision, and it does not resize the banner.
    window.addEventListener('resize', update);
    // Deferred a frame: the update resizes the banner it observes, and a size
    // change delivered in the same frame is reported as a ResizeObserver loop.
    const observer = new ResizeObserver(function() { requestAnimationFrame(update); });
    observer.observe(banner);
    stopTracking = function() {
      window.removeEventListener('resize', update);
      observer.disconnect();
    };
  }

  /**
   * Remove the class and the property, and stop measuring.
   */
  function releaseBannerBottom() {
    if (stopTracking) stopTracking();
    stopTracking = null;
    document.body.classList.remove('embed-banner-shown');
    document.body.style.removeProperty('--telar-embed-banner-bottom');
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
