/**
 * Share Panel Functionality
 * @version v0.5.0-beta
 *
 * Handles share link and embed code generation for Telar stories.
 * Supports both story-specific and site-wide sharing contexts.
 */

(function() {
  'use strict';

  // State
  let currentContext = 'story'; // 'story' or 'site'
  let currentStoryUrl = window.location.href;
  let availableStories = [];

  // DOM elements
  const sharePanel = document.getElementById('panel-share');
  const sharePanelTitle = document.getElementById('panel-share-title');

  // Share Link tab elements
  const shareUrlInput = document.getElementById('share-url-input');
  const shareCopyLinkBtn = document.getElementById('share-copy-link-btn');
  const shareSiteUrlInput = document.getElementById('share-site-url-input');
  const shareCopySiteBtn = document.getElementById('share-copy-site-btn');
  const shareStorySelectors = document.querySelectorAll('.share-story-selector');
  const shareStorySelect = document.getElementById('share-story-select');

  // Embed Code tab elements
  const embedPresetSelect = document.getElementById('embed-preset-select');
  const embedWidthInput = document.getElementById('embed-width-input');
  const embedHeightInput = document.getElementById('embed-height-input');
  const embedCodeTextarea = document.getElementById('embed-code-textarea');
  const embedCopyCodeBtn = document.getElementById('embed-copy-code-btn');
  const embedStorySelect = document.getElementById('embed-story-select');

  // Success messages
  const successMessages = document.querySelectorAll('.share-success-message');

  /**
   * Initialize share panel
   */
  function init() {
    if (!sharePanel) return;

    // Detect context from share button click
    sharePanel.addEventListener('show.bs.modal', handlePanelOpen);

    // Event listeners
    if (shareCopyLinkBtn) {
      shareCopyLinkBtn.addEventListener('click', copyShareLink);
    }

    if (shareCopySiteBtn) {
      shareCopySiteBtn.addEventListener('click', copySiteLink);
    }

    if (embedCopyCodeBtn) {
      embedCopyCodeBtn.addEventListener('click', copyEmbedCode);
    }

    if (embedPresetSelect) {
      embedPresetSelect.addEventListener('change', handlePresetChange);
    }

    if (embedWidthInput) {
      embedWidthInput.addEventListener('input', updateEmbedCode);
    }

    if (embedHeightInput) {
      embedHeightInput.addEventListener('input', updateEmbedCode);
    }

    if (shareStorySelect) {
      shareStorySelect.addEventListener('change', handleStoryChange);
    }

    if (embedStorySelect) {
      embedStorySelect.addEventListener('change', handleStoryChange);
    }

    // Load available stories for homepage context
    loadAvailableStories();

    console.log('[Telar Share] Share panel initialized');
  }

  /**
   * Handle panel opening - detect context and update UI
   */
  function handlePanelOpen(event) {
    // Get context from triggering button
    const trigger = event.relatedTarget;
    if (trigger) {
      currentContext = trigger.dataset.shareContext || 'story';
    }

    // Update panel based on context
    if (currentContext === 'site') {
      showStorySelectors();
      updatePanelTitle('title_site');

      // Set to first story if available
      if (availableStories.length > 0) {
        currentStoryUrl = availableStories[0].url;
      } else {
        currentStoryUrl = window.location.origin + window.location.pathname;
      }
    } else {
      hideStorySelectors();
      updatePanelTitle('title');
      currentStoryUrl = window.location.href;
    }

    // Update share URL
    updateShareUrl();

    // Update embed code
    updateEmbedCode();
  }

  /**
   * Update panel title based on context
   */
  function updatePanelTitle(key) {
    if (!sharePanelTitle) return;

    // Get language strings from data attribute or fallback
    const langData = document.documentElement.dataset.lang;
    if (langData) {
      try {
        const lang = JSON.parse(langData);
        sharePanelTitle.textContent = lang.share[key] || lang.share.title;
      } catch (e) {
        console.warn('[Telar Share] Could not parse language data');
      }
    }
  }

  /**
   * Show story selectors for site context
   */
  function showStorySelectors() {
    shareStorySelectors.forEach(selector => {
      selector.style.display = 'block';
    });
  }

  /**
   * Hide story selectors for story context
   */
  function hideStorySelectors() {
    shareStorySelectors.forEach(selector => {
      selector.style.display = 'none';
    });
  }

  /**
   * Load available stories from Jekyll data
   */
  function loadAvailableStories() {
    // Try to get stories from page data
    const storiesData = document.getElementById('telar-stories-data');
    if (storiesData) {
      try {
        availableStories = JSON.parse(storiesData.textContent);
        populateStorySelectors();
      } catch (e) {
        console.warn('[Telar Share] Could not parse stories data');
      }
    }
  }

  /**
   * Populate story dropdown selectors
   */
  function populateStorySelectors() {
    if (availableStories.length === 0) return;

    [shareStorySelect, embedStorySelect].forEach(select => {
      if (!select) return;

      select.innerHTML = '';

      availableStories.forEach(story => {
        const option = document.createElement('option');
        option.value = story.url;
        option.textContent = story.title;
        select.appendChild(option);
      });
    });
  }

  /**
   * Handle story selection change
   */
  function handleStoryChange(event) {
    currentStoryUrl = event.target.value;
    updateShareUrl();
    updateEmbedCode();
  }

  /**
   * Update share URL input
   */
  function updateShareUrl() {
    if (!shareUrlInput) return;

    // Clean the story URL - remove hash and query parameters (viewer state)
    const cleanUrl = window.location.origin + window.location.pathname;
    shareUrlInput.value = cleanUrl;

    // Also populate site URL (base URL - just the first path segment)
    if (shareSiteUrlInput) {
      const pathParts = window.location.pathname.split('/').filter(p => p);
      const baseUrl = window.location.origin + (pathParts.length > 0 ? '/' + pathParts[0] + '/' : '/');
      shareSiteUrlInput.value = baseUrl;
    }
  }

  /**
   * Copy share link to clipboard
   */
  function copyShareLink() {
    if (!shareUrlInput) return;

    copyToClipboard(shareUrlInput.value, shareCopyLinkBtn);
  }

  /**
   * Copy site link to clipboard
   */
  function copySiteLink() {
    if (!shareSiteUrlInput) return;

    copyToClipboard(shareSiteUrlInput.value, shareCopySiteBtn);
  }

  /**
   * Handle embed preset change
   */
  function handlePresetChange(event) {
    const preset = event.target.value;

    const presets = {
      canvas: { width: '100%', height: '800' },
      moodle: { width: '100%', height: '700' },
      wordpress: { width: '100%', height: '600' },
      squarespace: { width: '100%', height: '600' },
      wix: { width: '100%', height: '550' },
      mobile: { width: '375', height: '500' },
      fixed: { width: '800', height: '600' }
    };

    if (presets[preset]) {
      embedWidthInput.value = presets[preset].width;
      embedHeightInput.value = presets[preset].height;
      updateEmbedCode();
    }
  }

  /**
   * Generate embed code
   */
  function generateEmbedCode() {
    const width = embedWidthInput.value.trim() || '100%';
    const height = embedHeightInput.value.trim() || '800';

    // Normalize dimension values
    const widthAttr = normalizeDimension(width);
    const heightAttr = normalizeDimension(height);

    // Build embed URL with ?embed=true parameter
    const embedUrl = addEmbedParameter(currentStoryUrl);

    // Get story title for iframe title attribute
    const storyTitle = getStoryTitle();

    // Generate iframe code
    const iframeCode = `<iframe src="${embedUrl}"
  width="${widthAttr}"
  height="${heightAttr}"
  title="${storyTitle}"
  frameborder="0">
</iframe>`;

    return iframeCode;
  }

  /**
   * Normalize dimension value (add px if just a number)
   */
  function normalizeDimension(value) {
    // If it's just a number, add 'px'
    if (/^\d+$/.test(value)) {
      return value + 'px';
    }
    return value;
  }

  /**
   * Add ?embed=true parameter to URL (strips existing query params and hash)
   */
  function addEmbedParameter(url) {
    try {
      const urlObj = new URL(url);
      // Clear existing query params and hash (viewer state)
      urlObj.search = '';
      urlObj.hash = '';
      // Add clean embed parameter
      urlObj.searchParams.set('embed', 'true');
      return urlObj.toString();
    } catch (e) {
      // Fallback if URL parsing fails - strip everything after ? or #
      const cleanUrl = url.split(/[?#]/)[0];
      return cleanUrl + '?embed=true';
    }
  }

  /**
   * Get story title for iframe title attribute
   */
  function getStoryTitle() {
    // Try to get from selected story
    if (currentContext === 'site' && shareStorySelect) {
      const selectedOption = shareStorySelect.options[shareStorySelect.selectedIndex];
      if (selectedOption) {
        return selectedOption.textContent;
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
    if (!embedCodeTextarea) return;
    embedCodeTextarea.value = generateEmbedCode();
  }

  /**
   * Copy embed code to clipboard
   */
  function copyEmbedCode() {
    if (!embedCodeTextarea) return;
    copyToClipboard(embedCodeTextarea.value, embedCopyCodeBtn);
  }

  /**
   * Copy text to clipboard and show success feedback
   */
  function copyToClipboard(text, triggerButton) {
    navigator.clipboard.writeText(text).then(() => {
      showSuccessFeedback(triggerButton);
    }).catch(err => {
      console.error('[Telar Share] Failed to copy:', err);

      // Fallback: select text for manual copy
      if (text) {
        alert('Please manually copy the text');
      }
    });
  }

  /**
   * Show success feedback
   */
  function showSuccessFeedback(triggerButton) {
    // Find the success message in the same tab
    const tab = triggerButton.closest('.tab-pane');
    const successMessage = tab ? tab.querySelector('.share-success-message') : null;

    if (successMessage) {
      successMessage.style.display = 'block';

      // Hide after 3 seconds
      setTimeout(() => {
        successMessage.style.display = 'none';
      }, 3000);
    }

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
