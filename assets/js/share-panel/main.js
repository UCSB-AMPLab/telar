/**
 * Telar — share panel.
 *
 * Builds the share link and embed-code controls inside the `#panel-share` offcanvas.
 * The same panel serves two contexts: a story page, where it shares the story you are
 * reading, and the homepage, where a dropdown lets you pick which story to share. The
 * panel detects its context once at init from the body class, layout markers, and URL.
 *
 * Privacy toggle — protected stories carry a decryption key. A single "Without key /
 * With key" toggle governs both the share URL and the embed snippet at once: when on,
 * the key is appended as `?key=` and a warning surfaces. The toggle defaults to off,
 * and the key is only ever known here when `story-unlock.js` has published it on
 * `window.telarStoryKey` after a successful unlock — so the privacy section stays
 * hidden unless both the story is protected and the key is in hand.
 *
 * Embed code — presets (Canvas, Moodle, WordPress, and so on) seed sensible iframe
 * width/height, which the user can then override. The generated `src` is the story URL
 * stripped of viewer state (query and hash) with `?embed=true` added; the story title
 * is escaped before it lands in the iframe's `title` attribute so a stray quote can't
 * break the copied snippet.
 *
 * Copying uses the async Clipboard API, guarded for insecure contexts where it is
 * absent, and swaps the button icon to a checkmark briefly as confirmation.
 *
 * `warnings.js` holds the decision behind the four warning ids and the showing of
 * one, so which pair a branch raises is separable from the panel it sits in.
 *
 * The whole thing is a factory rather than a file-scope closure: the state it keeps
 * (the current story URL, the stories the selector offers, whether the story is
 * protected, the key, and whether the key is being included) belongs to one panel, so
 * a test can build one over its own document and leave no state behind. The document,
 * window, navigator and alert are parameters with browser defaults.
 *
 * Bundled by esbuild into assets/js/share-panel.js; see assets/js/README.md.
 *
 * Version: v1.7.0
 */

import { warningState, setWarning } from './warnings.js';

/** One share panel's link and embed controls over the page it is given. */
export function createSharePanel({
  doc = document,
  win = window,
  navigatorRef = navigator,
  alertFn = alert,
} = {}) {
  // State
  let currentStoryUrl = win.location.href;
  let availableStories = [];
  let currentStoryProtected = false;
  let storyKey = null; // Will be set from config if available
  let includeKey = false; // Single toggle controls both share and embed

  // DOM elements
  const sharePanel = doc.getElementById('panel-share');

  // Check if we're on a story page or homepage
  const isStoryPage = doc.body.classList.contains('story-page') ||
                      doc.querySelector('.story-layout') !== null ||
                      win.location.pathname.includes('/stories/');

  /**
   * Initialize share panel
   */
  function init() {
    if (!sharePanel) return;

    // Initialize URLs on panel open
    sharePanel.addEventListener('show.bs.modal', handlePanelOpen);

    // Get DOM elements after panel structure is known
    bindCopyButtons();
    bindEmbedAndKeyControls();

    // Homepage: Story selector
    const shareStorySelect = doc.getElementById('share-story-select');
    if (shareStorySelect) {
      shareStorySelect.addEventListener('change', handleStoryChange);
    }

    // Load available stories for homepage context
    loadAvailableStories();

    // Check if current story is protected (for story pages)
    detectProtectedStory();

    console.log('[Telar Share] Share panel initialized');
  }

  /**
   * Bind the four buttons that put a field on the clipboard
   */
  function bindCopyButtons() {
    const shareCopyLinkBtn = doc.getElementById('share-copy-link-btn');
    const shareCopySiteBtn = doc.getElementById('share-copy-site-btn');
    const embedCopyCodeBtn = doc.getElementById('embed-copy-code-btn');

    // Event listeners for copy buttons
    if (shareCopyLinkBtn) {
      shareCopyLinkBtn.addEventListener('click', function() {
        const input = doc.getElementById('share-url-input');
        if (input) copyToClipboard(input.value, this);
      });
    }

    if (shareCopySiteBtn) {
      shareCopySiteBtn.addEventListener('click', function() {
        const input = doc.getElementById('share-site-url-input');
        if (input) copyToClipboard(input.value, this);
      });
    }

    const shareCopyViewBtn = doc.getElementById('share-copy-view-btn');
    if (shareCopyViewBtn) {
      shareCopyViewBtn.addEventListener('click', function() {
        const input = doc.getElementById('share-view-url-input');
        if (input) copyToClipboard(input.value, this);
      });
    }

    if (embedCopyCodeBtn) {
      embedCopyCodeBtn.addEventListener('click', function() {
        const textarea = doc.getElementById('embed-code-textarea');
        if (textarea) copyToClipboard(textarea.value, this);
      });
    }
  }

  /**
   * Bind the embed size controls and the story page's privacy toggle
   */
  function bindEmbedAndKeyControls() {
    const embedPresetSelect = doc.getElementById('embed-preset-select');
    const embedWidthInput = doc.getElementById('embed-width-input');
    const embedHeightInput = doc.getElementById('embed-height-input');

    // Story page: Privacy toggle
    const shareKeyWithoutBtn = doc.getElementById('share-key-without');
    const shareKeyWithBtn = doc.getElementById('share-key-with');

    // Embed preset/dimension changes
    if (embedPresetSelect) {
      embedPresetSelect.addEventListener('change', handlePresetChange);
    }

    if (embedWidthInput) {
      embedWidthInput.addEventListener('input', updateEmbedCode);
    }

    if (embedHeightInput) {
      embedHeightInput.addEventListener('input', updateEmbedCode);
    }

    // Story page: Key toggle (single toggle controls both share and embed)
    if (shareKeyWithoutBtn) {
      shareKeyWithoutBtn.addEventListener('click', function() {
        includeKey = false;
        shareKeyWithoutBtn.classList.add('active');
        shareKeyWithBtn.classList.remove('active');
        updateShareUrl();
        updateViewUrl();
        updateEmbedCode();
        updateWarnings();
      });
    }

    if (shareKeyWithBtn) {
      shareKeyWithBtn.addEventListener('click', function() {
        includeKey = true;
        shareKeyWithBtn.classList.add('active');
        shareKeyWithoutBtn.classList.remove('active');
        updateShareUrl();
        updateViewUrl();
        updateEmbedCode();
        updateWarnings();
      });
    }
  }

  /**
   * Detect if the current story is protected and get the key
   */
  function detectProtectedStory() {
    // Check if we're on a story page with encrypted data
    if (win.storyData && win.storyData.encrypted) {
      currentStoryProtected = true;
    } else if (doc.getElementById('story-unlock-overlay')) {
      // Overlay exists = this is a protected story page (even after unlock)
      currentStoryProtected = true;
    }

    // Try to get story key from config (set by story-unlock.js after successful unlock)
    if (win.telarStoryKey) {
      storyKey = win.telarStoryKey;
    }
  }

  /**
   * Handle panel opening - initialize URLs
   */
  function handlePanelOpen(event) {
    // Refresh protected story detection (key may have been set after init)
    detectProtectedStory();

    resetKeyToggle();

    if (isStoryPage) {
      openOnStoryPage();
    } else {
      openOnOtherPage();
    }

    // Update URLs
    updateShareUrl();
    updateViewUrl();
    updateSiteUrl();
    updateEmbedCode();
    updateWarnings();
  }

  /**
   * Reset include key state
   */
  function resetKeyToggle() {
    includeKey = false;
    const shareKeyWithoutBtn = doc.getElementById('share-key-without');
    const shareKeyWithBtn = doc.getElementById('share-key-with');
    if (shareKeyWithoutBtn) shareKeyWithoutBtn.classList.add('active');
    if (shareKeyWithBtn) shareKeyWithBtn.classList.remove('active');
  }

  /**
   * Story page: Set current story URL
   */
  function openOnStoryPage() {
    currentStoryUrl = win.location.href;

    // Show Story Privacy section if story is protected and we have the key
    const privacySection = doc.getElementById('story-privacy-section');
    if (privacySection) {
      if (currentStoryProtected && storyKey) {
        privacySection.classList.remove('d-none');
      } else {
        privacySection.classList.add('d-none');
      }
    }
  }

  /**
   * Homepage: Clear story URL and disable copy buttons until story selected
   */
  function openOnOtherPage() {
    currentStoryUrl = '';
    currentStoryProtected = false;

    const shareStorySelect = doc.getElementById('share-story-select');
    const shareUrlInput = doc.getElementById('share-url-input');
    const shareCopyLinkBtn = doc.getElementById('share-copy-link-btn');
    const embedCodeTextarea = doc.getElementById('embed-code-textarea');
    const embedCopyCodeBtn = doc.getElementById('embed-copy-code-btn');

    // Reset story selector
    if (shareStorySelect) {
      shareStorySelect.value = '';
    }

    if (shareUrlInput) {
      shareUrlInput.value = '';
    }
    if (shareCopyLinkBtn) {
      shareCopyLinkBtn.disabled = true;
    }
    if (embedCodeTextarea) {
      embedCodeTextarea.value = '';
    }
    if (embedCopyCodeBtn) {
      embedCopyCodeBtn.disabled = true;
    }
  }

  /**
   * Load available stories from Jekyll data
   */
  function loadAvailableStories() {
    const storiesData = doc.getElementById('telar-stories-data');
    if (storiesData) {
      try {
        availableStories = JSON.parse(storiesData.textContent);
        populateStorySelector();
      } catch (e) {
        console.warn('[Telar Share] Could not parse stories data');
      }
    }
  }

  /**
   * Populate story dropdown selector
   */
  function populateStorySelector() {
    if (availableStories.length === 0) return;

    const shareStorySelect = doc.getElementById('share-story-select');
    if (!shareStorySelect) return;

    // Clear existing options but preserve the default "Select" option
    const firstOption = shareStorySelect.querySelector('option[value=""]');
    shareStorySelect.innerHTML = '';
    if (firstOption) {
      shareStorySelect.appendChild(firstOption);
    }

    // Add story options with lock icon for protected stories
    availableStories.forEach(story => {
      const option = doc.createElement('option');
      option.value = story.url;
      option.dataset.protected = story.protected ? 'true' : 'false';
      // Add lock symbol for protected stories
      option.textContent = story.protected ? '🔒 ' + story.title : story.title;
      shareStorySelect.appendChild(option);
    });
  }

  /**
   * Handle story selection change (homepage)
   */
  function handleStoryChange(event) {
    const selectedValue = event.target.value;
    const selectedOption = event.target.options[event.target.selectedIndex];

    // Update currentStoryUrl based on selection
    currentStoryUrl = selectedValue;

    // Check if selected story is protected
    currentStoryProtected = selectedOption && selectedOption.dataset.protected === 'true';

    // Enable/disable copy buttons based on whether a story is selected
    const hasSelection = currentStoryUrl !== '';
    const shareCopyLinkBtn = doc.getElementById('share-copy-link-btn');
    const embedCopyCodeBtn = doc.getElementById('embed-copy-code-btn');

    if (shareCopyLinkBtn) {
      shareCopyLinkBtn.disabled = !hasSelection;
    }
    if (embedCopyCodeBtn) {
      embedCopyCodeBtn.disabled = !hasSelection;
    }

    // Update URLs and embed code
    updateShareUrl();
    updateEmbedCode();
    updateWarnings();
  }

  /**
   * Update share URL input
   */
  function updateShareUrl() {
    const shareUrlInput = doc.getElementById('share-url-input');
    if (!shareUrlInput) return;

    if (currentStoryUrl) {
      // Clean the story URL - remove hash and query parameters (viewer state)
      try {
        const url = new URL(currentStoryUrl);
        let cleanUrl = url.origin + url.pathname;

        // Add key parameter if toggle is set to "With key" and we have a key
        if (includeKey && storyKey) {
          cleanUrl += '?key=' + encodeURIComponent(storyKey);
        }

        shareUrlInput.value = cleanUrl;
      } catch (e) {
        shareUrlInput.value = currentStoryUrl;
      }
    } else {
      shareUrlInput.value = '';
    }
  }

  /**
   * Update view URL input (story URL with deep-link fragment)
   */
  function updateViewUrl() {
    const shareViewUrlInput = doc.getElementById('share-view-url-input');
    if (!shareViewUrlInput) return;

    if (currentStoryUrl) {
      try {
        const url = new URL(currentStoryUrl);
        let cleanUrl = url.origin + url.pathname;

        if (includeKey && storyKey) {
          cleanUrl += '?key=' + encodeURIComponent(storyKey);
        }

        // Append current fragment for deep-link
        const currentHash = win.location.hash;
        if (currentHash && currentHash !== '#') {
          cleanUrl += currentHash;
        }

        shareViewUrlInput.value = cleanUrl;
      } catch (e) {
        shareViewUrlInput.value = currentStoryUrl;
      }
    } else {
      shareViewUrlInput.value = '';
    }
  }

  /**
   * Update site URL input
   */
  function updateSiteUrl() {
    const shareSiteUrlInput = doc.getElementById('share-site-url-input');
    if (!shareSiteUrlInput) return;

    const pathParts = win.location.pathname.split('/').filter(p => p);
    const baseUrl = win.location.origin + (pathParts.length > 0 ? '/' + pathParts[0] + '/' : '/');
    shareSiteUrlInput.value = baseUrl;
  }

  /**
   * Handle embed preset change
   */
  function handlePresetChange(event) {
    const preset = event.target.value;
    const embedWidthInput = doc.getElementById('embed-width-input');
    const embedHeightInput = doc.getElementById('embed-height-input');

    const presets = {
      canvas: { width: '100%', height: '800' },
      moodle: { width: '100%', height: '700' },
      wordpress: { width: '100%', height: '600' },
      squarespace: { width: '100%', height: '600' },
      wix: { width: '100%', height: '550' },
      mobile: { width: '375', height: '500' },
      fixed: { width: '800', height: '600' }
    };

    if (presets[preset] && embedWidthInput && embedHeightInput) {
      embedWidthInput.value = presets[preset].width;
      embedHeightInput.value = presets[preset].height;
      updateEmbedCode();
    }
  }

  // Escape a value for safe inclusion in a double-quoted HTML attribute.
  // Twin of escapeHtml in objects-filter/escape.js, which the objects gallery's
  // own bundle holds; the two bundles are separate, so keep them in sync.
  function escapeAttr(text) {
    const div = doc.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  /**
   * Generate embed code
   */
  function generateEmbedCode() {
    // Don't generate code if no story selected
    if (!currentStoryUrl) {
      return '';
    }

    const embedWidthInput = doc.getElementById('embed-width-input');
    const embedHeightInput = doc.getElementById('embed-height-input');

    const width = embedWidthInput ? embedWidthInput.value.trim() || '100%' : '100%';
    const height = embedHeightInput ? embedHeightInput.value.trim() || '800' : '800';

    // Normalize dimension values
    const widthAttr = normalizeDimension(width);
    const heightAttr = normalizeDimension(height);

    // Build embed URL with ?embed=true parameter
    const embedUrl = addEmbedParameter(currentStoryUrl);

    // Get story title for iframe title attribute (escaped for the attribute so a
    // quote in the title can't break the copied embed snippet)
    const storyTitle = escapeAttr(getStoryTitle());

    // Generate iframe code
    const iframeCode = `<iframe src="${embedUrl}"
  width="${widthAttr}" height="${heightAttr}" title="${storyTitle}"
  frameborder="0">
</iframe>`;

    return iframeCode;
  }

  /**
   * Normalize dimension value (add px if just a number)
   */
  function normalizeDimension(value) {
    if (/^\d+$/.test(value)) {
      return value + 'px';
    }
    return value;
  }

  /**
   * Add ?embed=true parameter to URL (strips existing query params and hash)
   * Optionally includes key parameter for protected stories
   */
  function addEmbedParameter(url) {
    try {
      const urlObj = new URL(url);
      // Clear existing query params and hash (viewer state)
      urlObj.search = '';
      urlObj.hash = '';
      // Add clean embed parameter
      urlObj.searchParams.set('embed', 'true');

      // Add key parameter if toggle is set to "With key" and we have a key.
      //
      // The key is included deliberately: a key-bearing URL is the intended way
      // to share access to a protected story, and the toggle defaults to
      // "Without key" so it is never added unless the user explicitly opts in
      // (which surfaces embed-key-warning). This is a
      // deliberate, documented risk: protected stories are a deterrent, not
      // real encryption, so a shared key is not a confidentiality boundary. The
      // user-facing warning is the mitigation — an embed pasted into a public
      // page exposes the key in that page's source to anyone who reads it.
      if (includeKey && storyKey) {
        urlObj.searchParams.set('key', storyKey);
      }

      return urlObj.toString();
    } catch (e) {
      // Fallback if URL parsing fails
      const cleanUrl = url.split(/[?#]/)[0];
      let embedUrl = cleanUrl + '?embed=true';
      if (includeKey && storyKey) {
        embedUrl += '&key=' + encodeURIComponent(storyKey);
      }
      return embedUrl;
    }
  }

  /**
   * Get story title for iframe title attribute
   */
  function getStoryTitle() {
    // Try to get from selected story in dropdown
    const shareStorySelect = doc.getElementById('share-story-select');
    if (shareStorySelect && shareStorySelect.value) {
      const selectedOption = shareStorySelect.options[shareStorySelect.selectedIndex];
      if (selectedOption && selectedOption.value) {
        // Remove lock emoji if present
        return selectedOption.textContent.replace(/^🔒\s*/, '');
      }
    }

    // Fallback: search availableStories array for matching URL
    if (currentStoryUrl && availableStories.length > 0) {
      const matchingStory = availableStories.find(story => story.url === currentStoryUrl);
      if (matchingStory) {
        return matchingStory.title;
      }
    }

    // Try to get from page title
    const pageTitle = doc.querySelector('meta[property="og:title"]');
    if (pageTitle) {
      return pageTitle.content;
    }

    return doc.title || 'Telar Story';
  }

  /**
   * Update embed code textarea
   */
  function updateEmbedCode() {
    const embedCodeTextarea = doc.getElementById('embed-code-textarea');
    if (!embedCodeTextarea) return;
    embedCodeTextarea.value = generateEmbedCode();
  }

  /**
   * Update warning messages based on protection status and key inclusion
   */
  function updateWarnings() {
    const state = warningState(currentStoryProtected, storyKey, includeKey, currentStoryUrl);
    updateKeyWarnings(state.key);
    updateProtectedWarnings(state.protectedStory);
  }

  /**
   * Story page warnings (shown when "With key" is selected)
   *
   * Story-branch half of the four-id warning namespace in
   * _includes/share-panel.html: #share-key-warning / #embed-key-warning here
   * vs #share-protected-warning / #embed-protected-warning on the homepage
   * branch (updateProtectedWarnings below). The two halves differ on purpose —
   * a story page can append the live decryption key, so its warnings speak to
   * exposing the key; the homepage never holds the key. Edits to either half's
   * ids or markup must be checked against the other and against
   * share-panel.html's paired warning comments.
   */
  function updateKeyWarnings(shown) {
    setWarning(doc.getElementById('share-key-warning'), shown);
    setWarning(doc.getElementById('embed-key-warning'), shown);
  }

  /**
   * Homepage warnings (shown when protected story is selected)
   *
   * Homepage-branch half of the four-id warning namespace in
   * _includes/share-panel.html: #share-protected-warning /
   * #embed-protected-warning here vs #share-key-warning / #embed-key-warning
   * on the story branch (updateKeyWarnings above). The homepage never holds
   * the decryption key, so these only flag that the selected story is
   * protected. Edits to either half's ids or markup must be checked against
   * the other and against share-panel.html's paired warning comments.
   */
  function updateProtectedWarnings(shown) {
    setWarning(doc.getElementById('share-protected-warning'), shown);
    setWarning(doc.getElementById('embed-protected-warning'), shown);
  }

  /**
   * Copy text to clipboard and show success feedback
   */
  function copyToClipboard(text, triggerButton) {
    if (!text) return;

    // Insecure contexts (and older browsers) have no navigator.clipboard, so
    // calling writeText would throw synchronously — before the .catch below
    // could handle it. Guard that case explicitly.
    if (!navigatorRef.clipboard || typeof navigatorRef.clipboard.writeText !== 'function') {
      alertFn('Please manually copy the text');
      return;
    }

    navigatorRef.clipboard.writeText(text).then(() => {
      showSuccessFeedback(triggerButton);
    }).catch(err => {
      console.error('[Telar Share] Failed to copy:', err);
      alertFn('Please manually copy the text');
    });
  }

  /**
   * Show success feedback
   */
  function showSuccessFeedback(triggerButton) {
    // Update button icon temporarily
    const btnIcon = triggerButton.querySelector('.icon');
    if (btnIcon) {
      const originalSvg = btnIcon.outerHTML;
      btnIcon.outerHTML = '<svg class="icon" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>';

      setTimeout(() => {
        const checkIcon = triggerButton.querySelector('.icon');
        if (checkIcon) checkIcon.outerHTML = originalSvg;
      }, 2000);
    }
  }

  return { init };
}

// Initialize on DOM ready
const panel = createSharePanel();
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => panel.init());
} else {
  panel.init();
}
