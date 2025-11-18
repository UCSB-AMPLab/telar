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
  let currentStoryUrl = window.location.href;
  let availableStories = [];

  // DOM elements
  const sharePanel = document.getElementById('panel-share');

  // Share Link tab elements
  const shareUrlInput = document.getElementById('share-url-input');
  const shareCopyLinkBtn = document.getElementById('share-copy-link-btn');
  const shareSiteUrlInput = document.getElementById('share-site-url-input');
  const shareCopySiteBtn = document.getElementById('share-copy-site-btn');
  const shareStorySelect = document.getElementById('share-story-select');

  // Embed Code tab elements
  const embedPresetSelect = document.getElementById('embed-preset-select');
  const embedWidthInput = document.getElementById('embed-width-input');
  const embedHeightInput = document.getElementById('embed-height-input');
  const embedCodeTextarea = document.getElementById('embed-code-textarea');
  const embedCopyCodeBtn = document.getElementById('embed-copy-code-btn');
  const embedStorySelect = document.getElementById('embed-story-select');

  /**
   * Initialize share panel
   */
  function init() {
    if (!sharePanel) return;

    // Initialize URLs on panel open
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

    // Load available stories for homepage context (if selectors exist)
    loadAvailableStories();

    console.log('[Telar Share] Share panel initialized');
  }

  /**
   * Handle panel opening - initialize URLs
   */
  function handlePanelOpen(event) {
    // Check if we're on a story page or homepage by checking if story selectors exist
    const isHomepage = shareStorySelect !== null;

    if (isHomepage) {
      // Homepage: Clear story URL and disable copy buttons until story selected
      currentStoryUrl = '';

      // Reset story selectors to default option
      if (shareStorySelect) {
        shareStorySelect.value = '';
      }
      if (embedStorySelect) {
        embedStorySelect.value = '';
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
    } else {
      // Story page: Set current story URL
      currentStoryUrl = window.location.href;
    }

    // Update share URL
    updateShareUrl();

    // Update embed code
    updateEmbedCode();
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

      // Clear existing options but preserve the default "Select" option
      select.innerHTML = '';

      // Add default "Select" option
      const defaultOption = document.createElement('option');
      defaultOption.value = '';
      // Get the select option text from the first option if it exists, or use a fallback
      const langData = document.documentElement.dataset.lang;
      if (langData) {
        try {
          const lang = JSON.parse(langData);
          defaultOption.textContent = lang.share.select_option || 'Select';
        } catch (e) {
          defaultOption.textContent = 'Select';
        }
      } else {
        defaultOption.textContent = 'Select';
      }
      select.appendChild(defaultOption);

      // Add story options
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
    const selectedValue = event.target.value;

    // Update currentStoryUrl based on selection
    currentStoryUrl = selectedValue;

    // Sync both dropdowns if they exist
    if (event.target.id === 'share-story-select' && embedStorySelect) {
      embedStorySelect.value = selectedValue;
    } else if (event.target.id === 'embed-story-select' && shareStorySelect) {
      shareStorySelect.value = selectedValue;
    }

    // Enable/disable copy buttons based on whether a story is selected
    const hasSelection = currentStoryUrl !== '';

    if (shareCopyLinkBtn) {
      shareCopyLinkBtn.disabled = !hasSelection;
    }
    if (embedCopyCodeBtn) {
      embedCopyCodeBtn.disabled = !hasSelection;
    }

    // Update URLs and embed code
    updateShareUrl();
    updateEmbedCode();
  }

  /**
   * Update share URL input
   */
  function updateShareUrl() {
    // Always populate site URL
    if (shareSiteUrlInput) {
      const pathParts = window.location.pathname.split('/').filter(p => p);
      const baseUrl = window.location.origin + (pathParts.length > 0 ? '/' + pathParts[0] + '/' : '/');
      shareSiteUrlInput.value = baseUrl;
    }

    // For story URL: only populate if we have a current story URL
    if (shareUrlInput) {
      if (currentStoryUrl) {
        // Clean the story URL - remove hash and query parameters (viewer state)
        try {
          const url = new URL(currentStoryUrl);
          const cleanUrl = url.origin + url.pathname;
          shareUrlInput.value = cleanUrl;
        } catch (e) {
          shareUrlInput.value = currentStoryUrl;
        }
      } else {
        shareUrlInput.value = '';
      }
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
    // Don't generate code if no story selected
    if (!currentStoryUrl) {
      return '';
    }

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
    // Try to get from selected story in dropdown
    // Check both dropdowns (they should be synced, but check both to be safe)
    if (shareStorySelect && shareStorySelect.value) {
      const selectedOption = shareStorySelect.options[shareStorySelect.selectedIndex];
      if (selectedOption && selectedOption.value) {
        return selectedOption.textContent;
      }
    }

    if (embedStorySelect && embedStorySelect.value) {
      const selectedOption = embedStorySelect.options[embedStorySelect.selectedIndex];
      if (selectedOption && selectedOption.value) {
        return selectedOption.textContent;
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
