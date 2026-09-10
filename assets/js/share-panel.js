/* GENERATED FILE - do not edit. Bundled from assets/js/share-panel/ by esbuild. Rebuild: npm run build:js (see assets/js/README.md). */
(() => {
  // assets/js/share-panel/warnings.js
  function warningState(currentStoryProtected, storyKey, includeKey, currentStoryUrl) {
    return {
      key: Boolean(currentStoryProtected && includeKey && storyKey),
      protectedStory: Boolean(currentStoryProtected && currentStoryUrl)
    };
  }
  function setWarning(element, shown) {
    if (!element) return;
    if (shown) {
      element.classList.remove("d-none");
    } else {
      element.classList.add("d-none");
    }
  }

  // assets/js/share-panel/main.js
  function createSharePanel({
    doc = document,
    win = window,
    navigatorRef = navigator,
    alertFn = alert
  } = {}) {
    let currentStoryUrl = win.location.href;
    let availableStories = [];
    let currentStoryProtected = false;
    let storyKey = null;
    let includeKey = false;
    const sharePanel = doc.getElementById("panel-share");
    const isStoryPage = doc.body.classList.contains("story-page") || doc.querySelector(".story-layout") !== null || win.location.pathname.includes("/stories/");
    function init() {
      if (!sharePanel) return;
      sharePanel.addEventListener("show.bs.modal", handlePanelOpen);
      bindCopyButtons();
      bindEmbedAndKeyControls();
      const shareStorySelect = doc.getElementById("share-story-select");
      if (shareStorySelect) {
        shareStorySelect.addEventListener("change", handleStoryChange);
      }
      loadAvailableStories();
      detectProtectedStory();
      console.log("[Telar Share] Share panel initialized");
    }
    function bindCopyButtons() {
      const shareCopyLinkBtn = doc.getElementById("share-copy-link-btn");
      const shareCopySiteBtn = doc.getElementById("share-copy-site-btn");
      const embedCopyCodeBtn = doc.getElementById("embed-copy-code-btn");
      if (shareCopyLinkBtn) {
        shareCopyLinkBtn.addEventListener("click", function() {
          const input = doc.getElementById("share-url-input");
          if (input) copyToClipboard(input.value, this);
        });
      }
      if (shareCopySiteBtn) {
        shareCopySiteBtn.addEventListener("click", function() {
          const input = doc.getElementById("share-site-url-input");
          if (input) copyToClipboard(input.value, this);
        });
      }
      const shareCopyViewBtn = doc.getElementById("share-copy-view-btn");
      if (shareCopyViewBtn) {
        shareCopyViewBtn.addEventListener("click", function() {
          const input = doc.getElementById("share-view-url-input");
          if (input) copyToClipboard(input.value, this);
        });
      }
      if (embedCopyCodeBtn) {
        embedCopyCodeBtn.addEventListener("click", function() {
          const textarea = doc.getElementById("embed-code-textarea");
          if (textarea) copyToClipboard(textarea.value, this);
        });
      }
    }
    function bindEmbedAndKeyControls() {
      const embedPresetSelect = doc.getElementById("embed-preset-select");
      const embedWidthInput = doc.getElementById("embed-width-input");
      const embedHeightInput = doc.getElementById("embed-height-input");
      const shareKeyWithoutBtn = doc.getElementById("share-key-without");
      const shareKeyWithBtn = doc.getElementById("share-key-with");
      if (embedPresetSelect) {
        embedPresetSelect.addEventListener("change", handlePresetChange);
      }
      if (embedWidthInput) {
        embedWidthInput.addEventListener("input", updateEmbedCode);
      }
      if (embedHeightInput) {
        embedHeightInput.addEventListener("input", updateEmbedCode);
      }
      if (shareKeyWithoutBtn) {
        shareKeyWithoutBtn.addEventListener("click", function() {
          includeKey = false;
          shareKeyWithoutBtn.classList.add("active");
          shareKeyWithBtn.classList.remove("active");
          updateShareUrl();
          updateViewUrl();
          updateEmbedCode();
          updateWarnings();
        });
      }
      if (shareKeyWithBtn) {
        shareKeyWithBtn.addEventListener("click", function() {
          includeKey = true;
          shareKeyWithBtn.classList.add("active");
          shareKeyWithoutBtn.classList.remove("active");
          updateShareUrl();
          updateViewUrl();
          updateEmbedCode();
          updateWarnings();
        });
      }
    }
    function detectProtectedStory() {
      if (win.storyData && win.storyData.encrypted) {
        currentStoryProtected = true;
      } else if (doc.getElementById("story-unlock-overlay")) {
        currentStoryProtected = true;
      }
      if (win.telarStoryKey) {
        storyKey = win.telarStoryKey;
      }
    }
    function handlePanelOpen(event) {
      detectProtectedStory();
      resetKeyToggle();
      if (isStoryPage) {
        openOnStoryPage();
      } else {
        openOnOtherPage();
      }
      updateShareUrl();
      updateViewUrl();
      updateSiteUrl();
      updateEmbedCode();
      updateWarnings();
    }
    function resetKeyToggle() {
      includeKey = false;
      const shareKeyWithoutBtn = doc.getElementById("share-key-without");
      const shareKeyWithBtn = doc.getElementById("share-key-with");
      if (shareKeyWithoutBtn) shareKeyWithoutBtn.classList.add("active");
      if (shareKeyWithBtn) shareKeyWithBtn.classList.remove("active");
    }
    function openOnStoryPage() {
      currentStoryUrl = win.location.href;
      const privacySection = doc.getElementById("story-privacy-section");
      if (privacySection) {
        if (currentStoryProtected && storyKey) {
          privacySection.classList.remove("d-none");
        } else {
          privacySection.classList.add("d-none");
        }
      }
    }
    function openOnOtherPage() {
      currentStoryUrl = "";
      currentStoryProtected = false;
      const shareStorySelect = doc.getElementById("share-story-select");
      const shareUrlInput = doc.getElementById("share-url-input");
      const shareCopyLinkBtn = doc.getElementById("share-copy-link-btn");
      const embedCodeTextarea = doc.getElementById("embed-code-textarea");
      const embedCopyCodeBtn = doc.getElementById("embed-copy-code-btn");
      if (shareStorySelect) {
        shareStorySelect.value = "";
      }
      if (shareUrlInput) {
        shareUrlInput.value = "";
      }
      if (shareCopyLinkBtn) {
        shareCopyLinkBtn.disabled = true;
      }
      if (embedCodeTextarea) {
        embedCodeTextarea.value = "";
      }
      if (embedCopyCodeBtn) {
        embedCopyCodeBtn.disabled = true;
      }
    }
    function loadAvailableStories() {
      const storiesData = doc.getElementById("telar-stories-data");
      if (storiesData) {
        try {
          availableStories = JSON.parse(storiesData.textContent);
          populateStorySelector();
        } catch (e) {
          console.warn("[Telar Share] Could not parse stories data");
        }
      }
    }
    function populateStorySelector() {
      if (availableStories.length === 0) return;
      const shareStorySelect = doc.getElementById("share-story-select");
      if (!shareStorySelect) return;
      const firstOption = shareStorySelect.querySelector('option[value=""]');
      shareStorySelect.innerHTML = "";
      if (firstOption) {
        shareStorySelect.appendChild(firstOption);
      }
      availableStories.forEach((story) => {
        const option = doc.createElement("option");
        option.value = story.url;
        option.dataset.protected = story.protected ? "true" : "false";
        option.textContent = story.protected ? "\u{1F512} " + story.title : story.title;
        shareStorySelect.appendChild(option);
      });
    }
    function handleStoryChange(event) {
      const selectedValue = event.target.value;
      const selectedOption = event.target.options[event.target.selectedIndex];
      currentStoryUrl = selectedValue;
      currentStoryProtected = selectedOption && selectedOption.dataset.protected === "true";
      const hasSelection = currentStoryUrl !== "";
      const shareCopyLinkBtn = doc.getElementById("share-copy-link-btn");
      const embedCopyCodeBtn = doc.getElementById("embed-copy-code-btn");
      if (shareCopyLinkBtn) {
        shareCopyLinkBtn.disabled = !hasSelection;
      }
      if (embedCopyCodeBtn) {
        embedCopyCodeBtn.disabled = !hasSelection;
      }
      updateShareUrl();
      updateEmbedCode();
      updateWarnings();
    }
    function updateShareUrl() {
      const shareUrlInput = doc.getElementById("share-url-input");
      if (!shareUrlInput) return;
      if (currentStoryUrl) {
        try {
          const url = new URL(currentStoryUrl);
          let cleanUrl = url.origin + url.pathname;
          if (includeKey && storyKey) {
            cleanUrl += "?key=" + encodeURIComponent(storyKey);
          }
          shareUrlInput.value = cleanUrl;
        } catch (e) {
          shareUrlInput.value = currentStoryUrl;
        }
      } else {
        shareUrlInput.value = "";
      }
    }
    function updateViewUrl() {
      const shareViewUrlInput = doc.getElementById("share-view-url-input");
      if (!shareViewUrlInput) return;
      if (currentStoryUrl) {
        try {
          const url = new URL(currentStoryUrl);
          let cleanUrl = url.origin + url.pathname;
          if (includeKey && storyKey) {
            cleanUrl += "?key=" + encodeURIComponent(storyKey);
          }
          const currentHash = win.location.hash;
          if (currentHash && currentHash !== "#") {
            cleanUrl += currentHash;
          }
          shareViewUrlInput.value = cleanUrl;
        } catch (e) {
          shareViewUrlInput.value = currentStoryUrl;
        }
      } else {
        shareViewUrlInput.value = "";
      }
    }
    function updateSiteUrl() {
      const shareSiteUrlInput = doc.getElementById("share-site-url-input");
      if (!shareSiteUrlInput) return;
      const pathParts = win.location.pathname.split("/").filter((p) => p);
      const baseUrl = win.location.origin + (pathParts.length > 0 ? "/" + pathParts[0] + "/" : "/");
      shareSiteUrlInput.value = baseUrl;
    }
    function handlePresetChange(event) {
      const preset = event.target.value;
      const embedWidthInput = doc.getElementById("embed-width-input");
      const embedHeightInput = doc.getElementById("embed-height-input");
      const presets = {
        canvas: { width: "100%", height: "800" },
        moodle: { width: "100%", height: "700" },
        wordpress: { width: "100%", height: "600" },
        squarespace: { width: "100%", height: "600" },
        wix: { width: "100%", height: "550" },
        mobile: { width: "375", height: "500" },
        fixed: { width: "800", height: "600" }
      };
      if (presets[preset] && embedWidthInput && embedHeightInput) {
        embedWidthInput.value = presets[preset].width;
        embedHeightInput.value = presets[preset].height;
        updateEmbedCode();
      }
    }
    function escapeAttr(text) {
      const div = doc.createElement("div");
      div.textContent = text == null ? "" : String(text);
      return div.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }
    function generateEmbedCode() {
      if (!currentStoryUrl) {
        return "";
      }
      const embedWidthInput = doc.getElementById("embed-width-input");
      const embedHeightInput = doc.getElementById("embed-height-input");
      const width = embedWidthInput ? embedWidthInput.value.trim() || "100%" : "100%";
      const height = embedHeightInput ? embedHeightInput.value.trim() || "800" : "800";
      const widthAttr = normalizeDimension(width);
      const heightAttr = normalizeDimension(height);
      const embedUrl = addEmbedParameter(currentStoryUrl);
      const storyTitle = escapeAttr(getStoryTitle());
      const iframeCode = `<iframe src="${embedUrl}"
  width="${widthAttr}" height="${heightAttr}" title="${storyTitle}"
  frameborder="0">
</iframe>`;
      return iframeCode;
    }
    function normalizeDimension(value) {
      if (/^\d+$/.test(value)) {
        return value + "px";
      }
      return value;
    }
    function addEmbedParameter(url) {
      try {
        const urlObj = new URL(url);
        urlObj.search = "";
        urlObj.hash = "";
        urlObj.searchParams.set("embed", "true");
        if (includeKey && storyKey) {
          urlObj.searchParams.set("key", storyKey);
        }
        return urlObj.toString();
      } catch (e) {
        const cleanUrl = url.split(/[?#]/)[0];
        let embedUrl = cleanUrl + "?embed=true";
        if (includeKey && storyKey) {
          embedUrl += "&key=" + encodeURIComponent(storyKey);
        }
        return embedUrl;
      }
    }
    function getStoryTitle() {
      const shareStorySelect = doc.getElementById("share-story-select");
      if (shareStorySelect && shareStorySelect.value) {
        const selectedOption = shareStorySelect.options[shareStorySelect.selectedIndex];
        if (selectedOption && selectedOption.value) {
          return selectedOption.textContent.replace(/^🔒\s*/, "");
        }
      }
      if (currentStoryUrl && availableStories.length > 0) {
        const matchingStory = availableStories.find((story) => story.url === currentStoryUrl);
        if (matchingStory) {
          return matchingStory.title;
        }
      }
      const pageTitle = doc.querySelector('meta[property="og:title"]');
      if (pageTitle) {
        return pageTitle.content;
      }
      return doc.title || "Telar Story";
    }
    function updateEmbedCode() {
      const embedCodeTextarea = doc.getElementById("embed-code-textarea");
      if (!embedCodeTextarea) return;
      embedCodeTextarea.value = generateEmbedCode();
    }
    function updateWarnings() {
      const state = warningState(currentStoryProtected, storyKey, includeKey, currentStoryUrl);
      updateKeyWarnings(state.key);
      updateProtectedWarnings(state.protectedStory);
    }
    function updateKeyWarnings(shown) {
      setWarning(doc.getElementById("share-key-warning"), shown);
      setWarning(doc.getElementById("embed-key-warning"), shown);
    }
    function updateProtectedWarnings(shown) {
      setWarning(doc.getElementById("share-protected-warning"), shown);
      setWarning(doc.getElementById("embed-protected-warning"), shown);
    }
    function copyToClipboard(text, triggerButton) {
      if (!text) return;
      if (!navigatorRef.clipboard || typeof navigatorRef.clipboard.writeText !== "function") {
        alertFn("Please manually copy the text");
        return;
      }
      navigatorRef.clipboard.writeText(text).then(() => {
        showSuccessFeedback(triggerButton);
      }).catch((err) => {
        console.error("[Telar Share] Failed to copy:", err);
        alertFn("Please manually copy the text");
      });
    }
    function showSuccessFeedback(triggerButton) {
      const btnIcon = triggerButton.querySelector(".icon");
      if (btnIcon) {
        const originalSvg = btnIcon.outerHTML;
        btnIcon.outerHTML = '<svg class="icon" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>';
        setTimeout(() => {
          const checkIcon = triggerButton.querySelector(".icon");
          if (checkIcon) checkIcon.outerHTML = originalSvg;
        }, 2e3);
      }
    }
    return { init };
  }
  var panel = createSharePanel();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => panel.init());
  } else {
    panel.init();
  }
})();
//# sourceMappingURL=share-panel.js.map
