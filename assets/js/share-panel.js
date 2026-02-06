/**
 * Share Panel Functionality
 * @version v0.8.0-beta
 *
 * Handles share link and embed code generation for Telar stories.
 * Redesigned with pill-style tabs and unified privacy toggle.
 * Supports both story-specific and site-wide sharing contexts.
 */

(function() {
  'use strict';

  // State
  let currentStoryUrl = window.location.href;
  let availableStories = [];
  let currentStoryProtected = false;
  let storyKey = null; // Will be set from config if available
  let includeKey = false; // Single toggle controls both share and embed

  // DOM elements
  const sharePanel = document.getElementById('panel-share');

  // Check if we're on a story page or homepage
  const isStoryPage = document.body.classList.contains('story-page') ||
                      document.querySelector('.story-layout') !== null ||
                      window.location.pathname.includes('/stories/');

  /**
   * Initialize share panel
   */
  function init() {
    if (!sharePanel) return;

    // Initialize URLs on panel open
    sharePanel.addEventListener('show.bs.modal', handlePanelOpen);

    // Get DOM elements after panel structure is known
    const shareUrlInput = document.getElementById('share-url-input');
    const shareCopyLinkBtn = document.getElementById('share-copy-link-btn');
    const shareSiteUrlInput = document.getElementById('share-site-url-input');
    const shareCopySiteBtn = document.getElementById('share-copy-site-btn');
    const shareStorySelect = document.getElementById('share-story-select');
    const embedPresetSelect = document.getElementById('embed-preset-select');
    const embedWidthInput = document.getElementById('embed-width-input');
    const embedHeightInput = document.getElementById('embed-height-input');
    const embedCodeTextarea = document.getElementById('embed-code-textarea');
    const embedCopyCodeBtn = document.getElementById('embed-copy-code-btn');

    // Story page: Privacy toggle
    const shareKeyWithoutBtn = document.getElementById('share-key-without');
    const shareKeyWithBtn = document.getElementById('share-key-with');

    // Event listeners for copy buttons
    if (shareCopyLinkBtn) {
      shareCopyLinkBtn.addEventListener('click', function() {
        const input = document.getElementById('share-url-input');
        if (input) copyToClipboard(input.value, this);
      });
    }

    if (shareCopySiteBtn) {
      shareCopySiteBtn.addEventListener('click', function() {
        const input = document.getElementById('share-site-url-input');
        if (input) copyToClipboard(input.value, this);
      });
    }

    if (embedCopyCodeBtn) {
      embedCopyCodeBtn.addEventListener('click', function() {
        const textarea = document.getElementById('embed-code-textarea');
        if (textarea) copyToClipboard(textarea.value, this);
      });
    }

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
        updateEmbedCode();
        updateWarnings();
      });
    }

    // Homepage: Story selector
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
   * Detect if the current story is protected and get the key
   */
  function detectProtectedStory() {
    // Check if we're on a story page with encrypted data
    if (window.storyData && window.storyData.encrypted) {
      currentStoryProtected = true;
    } else if (document.getElementById('story-unlock-overlay')) {
      // Overlay exists = this is a protected story page (even after unlock)
      currentStoryProtected = true;
    }

    // Try to get story key from config (set by story-unlock.js after successful unlock)
    if (window.telarStoryKey) {
      storyKey = window.telarStoryKey;
    }
  }

  /**
   * Handle panel opening - initialize URLs
   */
  function handlePanelOpen(event) {
    // Refresh protected story detection (key may have been set after init)
    detectProtectedStory();

    // Reset include key state
    includeKey = false;
    const shareKeyWithoutBtn = document.getElementById('share-key-without');
    const shareKeyWithBtn = document.getElementById('share-key-with');
    if (shareKeyWithoutBtn) shareKeyWithoutBtn.classList.add('active');
    if (shareKeyWithBtn) shareKeyWithBtn.classList.remove('active');

    if (isStoryPage) {
      // Story page: Set current story URL
      currentStoryUrl = window.location.href;

      // Show Story Privacy section if story is protected and we have the key
      const privacySection = document.getElementById('story-privacy-section');
      if (privacySection) {
        if (currentStoryProtected && storyKey) {
          privacySection.classList.remove('d-none');
        } else {
          privacySection.classList.add('d-none');
        }
      }
    } else {
      // Homepage: Clear story URL and disable copy buttons until story selected
      currentStoryUrl = '';
      currentStoryProtected = false;

      const shareStorySelect = document.getElementById('share-story-select');
      const shareUrlInput = document.getElementById('share-url-input');
      const shareCopyLinkBtn = document.getElementById('share-copy-link-btn');
      const embedCodeTextarea = document.getElementById('embed-code-textarea');
      const embedCopyCodeBtn = document.getElementById('embed-copy-code-btn');

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

    // Update URLs
    updateShareUrl();
    updateSiteUrl();
    updateEmbedCode();
    updateWarnings();
  }

  /**
   * Load available stories from Jekyll data
   */
  function loadAvailableStories() {
    const storiesData = document.getElementById('telar-stories-data');
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

    const shareStorySelect = document.getElementById('share-story-select');
    if (!shareStorySelect) return;

    // Clear existing options but preserve the default "Select" option
    const firstOption = shareStorySelect.querySelector('option[value=""]');
    shareStorySelect.innerHTML = '';
    if (firstOption) {
      shareStorySelect.appendChild(firstOption);
    }

    // Add story options with lock icon for protected stories
    availableStories.forEach(story => {
      const option = document.createElement('option');
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
    const shareCopyLinkBtn = document.getElementById('share-copy-link-btn');
    const embedCopyCodeBtn = document.getElementById('embed-copy-code-btn');

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
    const shareUrlInput = document.getElementById('share-url-input');
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
   * Update site URL input
   */
  function updateSiteUrl() {
    const shareSiteUrlInput = document.getElementById('share-site-url-input');
    if (!shareSiteUrlInput) return;

    const pathParts = window.location.pathname.split('/').filter(p => p);
    const baseUrl = window.location.origin + (pathParts.length > 0 ? '/' + pathParts[0] + '/' : '/');
    shareSiteUrlInput.value = baseUrl;
  }

  /**
   * Handle embed preset change
   */
  function handlePresetChange(event) {
    const preset = event.target.value;
    const embedWidthInput = document.getElementById('embed-width-input');
    const embedHeightInput = document.getElementById('embed-height-input');

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

  /**
   * Generate embed code
   */
  function generateEmbedCode() {
    // Don't generate code if no story selected
    if (!currentStoryUrl) {
      return '';
    }

    const embedWidthInput = document.getElementById('embed-width-input');
    const embedHeightInput = document.getElementById('embed-height-input');

    const width = embedWidthInput ? embedWidthInput.value.trim() || '100%' : '100%';
    const height = embedHeightInput ? embedHeightInput.value.trim() || '800' : '800';

    // Normalize dimension values
    const widthAttr = normalizeDimension(width);
    const heightAttr = normalizeDimension(height);

    // Build embed URL with ?embed=true parameter
    const embedUrl = addEmbedParameter(currentStoryUrl);

    // Get story title for iframe title attribute
    const storyTitle = getStoryTitle();

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

      // Add key parameter if toggle is set to "With key" and we have a key
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
    const shareStorySelect = document.getElementById('share-story-select');
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
    const pageTitle = document.querySelector('meta[property="og:title"]');
    if (pageTitle) {
      return pageTitle.content;
    }

    return document.title || 'Telar Story';
  }

  /**
   * Update embed code textarea
   */
  function updateEmbedCode() {
    const embedCodeTextarea = document.getElementById('embed-code-textarea');
    if (!embedCodeTextarea) return;
    embedCodeTextarea.value = generateEmbedCode();
  }

  /**
   * Update warning messages based on protection status and key inclusion
   */
  function updateWarnings() {
    // Story page warnings (shown when "With key" is selected)
    const shareKeyWarning = document.getElementById('share-key-warning');
    const embedKeyWarning = document.getElementById('embed-key-warning');

    if (shareKeyWarning) {
      if (currentStoryProtected && includeKey && storyKey) {
        shareKeyWarning.classList.remove('d-none');
      } else {
        shareKeyWarning.classList.add('d-none');
      }
    }

    if (embedKeyWarning) {
      if (currentStoryProtected && includeKey && storyKey) {
        embedKeyWarning.classList.remove('d-none');
      } else {
        embedKeyWarning.classList.add('d-none');
      }
    }

    // Homepage warnings (shown when protected story is selected)
    const shareProtectedWarning = document.getElementById('share-protected-warning');
    const embedProtectedWarning = document.getElementById('embed-protected-warning');

    if (shareProtectedWarning) {
      if (currentStoryProtected && currentStoryUrl) {
        shareProtectedWarning.classList.remove('d-none');
      } else {
        shareProtectedWarning.classList.add('d-none');
      }
    }

    if (embedProtectedWarning) {
      if (currentStoryProtected && currentStoryUrl) {
        embedProtectedWarning.classList.remove('d-none');
      } else {
        embedProtectedWarning.classList.add('d-none');
      }
    }
  }

  /**
   * Copy text to clipboard and show success feedback
   */
  function copyToClipboard(text, triggerButton) {
    if (!text) return;

    navigator.clipboard.writeText(text).then(() => {
      showSuccessFeedback(triggerButton);
    }).catch(err => {
      console.error('[Telar Share] Failed to copy:', err);
      alert('Please manually copy the text');
    });
  }

  /**
   * Show success feedback
   */
  function showSuccessFeedback(triggerButton) {
    // Update button icon temporarily
    const btnIcon = triggerButton.querySelector('.material-symbols-outlined');
    if (btnIcon) {
      const originalIcon = btnIcon.textContent;
      btnIcon.textContent = 'check_circle';

      setTimeout(() => {
        btnIcon.textContent = originalIcon;
      }, 2000);
    }
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
