/* GENERATED FILE - do not edit. Bundled from assets/js/object-page/ by esbuild. Rebuild: npm run build:js (see assets/js/README.md). @version v1.8.0 */
(() => {
  // assets/js/object-page/boot.js
  function readObjectData(doc = document) {
    const text = doc.getElementById("telar-object-data").textContent;
    try {
      return JSON.parse(text);
    } catch (err) {
      console.error("Object page data block is not valid JSON:", err);
      return null;
    }
  }
  function onObjectPage(wire) {
    const data = readObjectData();
    if (!data) return;
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => wire(data));
    } else {
      wire(data);
    }
  }

  // assets/js/object-page/copy-feedback.js
  var CHECK_ICON = '<svg class="icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>';
  function copyWithFeedback(text, buttonId, feedbackHtml, doc = document) {
    return navigator.clipboard.writeText(text).then(function() {
      const btn = doc.getElementById(buttonId);
      const originalHTML = btn.innerHTML;
      btn.innerHTML = feedbackHtml;
      setTimeout(function() {
        btn.innerHTML = originalHTML;
      }, 2e3);
    });
  }

  // assets/js/object-page/video-object.js
  function videoProvider(sourceUrl) {
    if (sourceUrl.includes("youtube.com") || sourceUrl.includes("youtu.be")) return "youtube";
    if (sourceUrl.includes("vimeo.com")) return "vimeo";
    if (sourceUrl.includes("drive.google.com")) return "gdrive";
    return null;
  }
  function initVideoEmbed(data, doc = document) {
    const viewer = doc.getElementById("object-viewer");
    const sourceUrl = data.sourceUrl;
    const embed = window.telarVideoEmbed.resolveVideoEmbed(sourceUrl, data.videoFrameTitle);
    if (!embed) return;
    viewer.innerHTML = embed.iframeHtml;
    if (videoProvider(sourceUrl) !== "gdrive") {
      const embedDisplay = doc.getElementById("embed-url-display");
      if (embedDisplay) embedDisplay.textContent = embed.embedUrl;
    } else {
      const iframe = doc.getElementById("video-player-iframe");
      let loadTimer = setTimeout(function() {
        const warn = doc.createElement("div");
        warn.className = "alert alert-warning";
        const p = doc.createElement("p");
        p.textContent = data.lang.embedUnavailable + " ";
        if (/^https?:/i.test(sourceUrl)) {
          const a = doc.createElement("a");
          a.href = sourceUrl;
          a.target = "_blank";
          a.rel = "noopener";
          a.textContent = data.lang.openOnDrive;
          p.appendChild(a);
        }
        warn.appendChild(p);
        viewer.replaceChildren(warn);
      }, 1e4);
      iframe.addEventListener("load", function() {
        clearTimeout(loadTimer);
      });
    }
  }
  function enableClipButtons(doc) {
    var startBtn = doc.getElementById("set-clip-start");
    var endBtn = doc.getElementById("set-clip-end");
    if (startBtn) startBtn.disabled = false;
    if (endBtn) endBtn.disabled = false;
  }
  function initClipPicker(data, doc = document) {
    const provider = videoProvider(data.sourceUrl);
    if (provider === "youtube") {
      var tag = doc.createElement("script");
      tag.src = "https://www.youtube.com/iframe_api";
      doc.head.appendChild(tag);
      window.onYouTubeIframeAPIReady = function() {
        window.ytPlayer = new YT.Player("video-player-iframe", {
          events: {
            onReady: function() {
              enableClipButtons(doc);
            }
          }
        });
      };
    } else if (provider === "vimeo") {
      var vScript = doc.createElement("script");
      vScript.src = "https://player.vimeo.com/api/player.js";
      vScript.onload = function() {
        var vPlayer = new Vimeo.Player("video-player-iframe");
        vPlayer.ready().then(function() {
          enableClipButtons(doc);
        });
        window._vimeoPlayer = vPlayer;
        var vimeoIframe = doc.getElementById("video-player-iframe");
        Promise.all([vPlayer.getVideoWidth(), vPlayer.getVideoHeight()]).then(function(dims) {
          if (vimeoIframe) vimeoIframe.style.aspectRatio = dims[0] + "/" + dims[1];
        }).catch(function() {
          if (vimeoIframe) vimeoIframe.style.aspectRatio = "16/9";
        });
      };
      doc.head.appendChild(vScript);
    }
    function getPlayerCurrentTime() {
      if (provider === "youtube" && window.ytPlayer) return Promise.resolve(window.ytPlayer.getCurrentTime());
      if (provider === "vimeo" && window._vimeoPlayer) return window._vimeoPlayer.getCurrentTime();
      return Promise.resolve(0);
    }
    var setStartBtn = doc.getElementById("set-clip-start");
    if (setStartBtn) {
      setStartBtn.addEventListener("click", function() {
        getPlayerCurrentTime().then(function(time) {
          doc.getElementById("clip-start-display").textContent = time.toFixed(3);
        });
      });
    }
    var setEndBtn = doc.getElementById("set-clip-end");
    if (setEndBtn) {
      setEndBtn.addEventListener("click", function() {
        getPlayerCurrentTime().then(function(time) {
          doc.getElementById("clip-end-display").textContent = time.toFixed(3);
        });
      });
    }
  }
  function initCopyEmbedUrl(doc = document) {
    const copyEmbedBtn = doc.getElementById("copy-embed-url");
    if (copyEmbedBtn) {
      copyEmbedBtn.addEventListener("click", function() {
        const url = doc.getElementById("embed-url-display").textContent;
        copyWithFeedback(url, "copy-embed-url", CHECK_ICON, doc);
      });
    }
  }

  // assets/js/object-page/clip-panel.js
  function initClipPanelToggle(doc = document) {
    var clipPanel = doc.getElementById("clipPanel");
    var clipButton = doc.getElementById("clipPickerButton");
    if (clipPanel && clipButton) {
      clipPanel.addEventListener("show.bs.collapse", function() {
        clipButton.style.display = "none";
      });
      clipPanel.addEventListener("hide.bs.collapse", function() {
        clipButton.style.display = "block";
      });
    }
  }
  function initClipCopyButtons(copiedLang, doc = document) {
    function copyClipText(text, btnId) {
      copyWithFeedback(text, btnId, CHECK_ICON + " " + copiedLang, doc);
    }
    var copyClipCsv = doc.getElementById("copy-clip-csv");
    if (copyClipCsv) {
      copyClipCsv.addEventListener("click", function() {
        var start = doc.getElementById("clip-start-display").textContent;
        var end = doc.getElementById("clip-end-display").textContent;
        copyClipText(start + "," + end, "copy-clip-csv");
      });
    }
    var copyClipSheets = doc.getElementById("copy-clip-sheets");
    if (copyClipSheets) {
      copyClipSheets.addEventListener("click", function() {
        var start = doc.getElementById("clip-start-display").textContent;
        var end = doc.getElementById("clip-end-display").textContent;
        copyClipText(start + "	" + end, "copy-clip-sheets");
      });
    }
  }

  // assets/js/object-page/video-entry.js
  onObjectPage((data) => {
    initVideoEmbed(data);
    if (!data.sourceUrl.includes("drive.google.com")) {
      initClipPanelToggle();
      initClipPicker(data);
      initClipCopyButtons(data.lang.copied);
    }
    initCopyEmbedUrl();
  });
})();
//# sourceMappingURL=object-video.js.map
