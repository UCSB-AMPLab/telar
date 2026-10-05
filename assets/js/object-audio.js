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

  // assets/js/object-page/audio-object.js
  var PLAY_ICON = '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/></svg>';
  var PAUSE_ICON = '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="14" y="3" width="5" height="18" rx="1"/><rect x="5" y="3" width="5" height="18" rx="1"/></svg>';
  var RESTART_ICON = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>';
  var VOLUME_ON_ICON = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><path d="M16 9a5 5 0 0 1 0 6"/><path d="M19.364 18.364a9 9 0 0 0 0-12.728"/></svg>';
  var VOLUME_OFF_ICON = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><line x1="22" y1="9" x2="16" y2="15"/><line x1="16" y1="9" x2="22" y2="15"/></svg>';
  function formatTime(secs) {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return m + ":" + (s < 10 ? "0" : "") + s;
  }
  function controlsMarkup(data) {
    return '<div id="audio-waveform" role="img" aria-label="' + data.waveformLabel + '" style="width:100%;height:100%;padding:0 3%;box-sizing:border-box;position:relative;z-index:0;"></div><div class="audio-object-controls"><button class="audio-object-btn" id="audio-play-btn" aria-label="' + data.lang.play + '" type="button">' + PLAY_ICON + '</button><button class="audio-object-btn" id="audio-restart-btn" aria-label="' + data.lang.restart + '" type="button">' + RESTART_ICON + '</button><button class="audio-object-btn" id="audio-mute-btn" aria-label="' + data.lang.mute + '" type="button">' + VOLUME_ON_ICON + '</button></div><span class="audio-object-time" id="audio-time-display">0:00 / --:--</span>';
  }
  async function initAudioPlayer(data, doc = document) {
    const viewer = doc.getElementById("object-viewer");
    const baseUrl = data.baseUrl;
    const audioUrl = data.audioUrl;
    if (!audioUrl) {
      viewer.innerHTML = '<div class="alert alert-warning">' + data.lang.audioNotFound + "</div>";
      return;
    }
    viewer.innerHTML = controlsMarkup(data);
    await window.telarLoadWaveSurfer(baseUrl);
    const WaveSurfer = window.WaveSurfer;
    const themeColors = window.telarObjectTheme.deriveThemeColors(
      getComputedStyle(doc.documentElement).getPropertyValue("--color-link").trim() || "#883C36",
      getComputedStyle(doc.documentElement).getPropertyValue("--color-button-text").trim() || "#ffffff"
    );
    const playedColor = themeColors.playedColor;
    const unplayedColor = themeColors.unplayedColor;
    const bgColor = themeColors.backgroundColor;
    viewer.style.background = bgColor;
    let peaksData = null;
    if (data.peaksUrl) {
      try {
        const peaksResp = await fetch(data.peaksUrl);
        if (peaksResp.ok) peaksData = await peaksResp.json();
      } catch (e) {
      }
    }
    const wsOptions = {
      container: "#audio-waveform",
      url: audioUrl,
      interact: true,
      waveColor: unplayedColor,
      progressColor: playedColor,
      cursorWidth: 0,
      barWidth: 3,
      barGap: 2,
      barRadius: 2,
      barHeight: 0.6,
      normalize: true,
      height: "auto"
    };
    if (peaksData && peaksData.peaks) {
      wsOptions.peaks = peaksData.peaks;
    }
    const ws = WaveSurfer.create(wsOptions);
    window._objectPageWaveSurfer = ws;
    const playBtn = doc.getElementById("audio-play-btn");
    playBtn.addEventListener("click", function() {
      ws.playPause();
    });
    ws.on("play", function() {
      playBtn.innerHTML = PAUSE_ICON;
      playBtn.setAttribute("aria-label", data.lang.pause);
    });
    ws.on("pause", function() {
      playBtn.innerHTML = PLAY_ICON;
      playBtn.setAttribute("aria-label", data.lang.play);
    });
    var audioReady = false;
    ws.on("ready", function() {
      audioReady = true;
    });
    const restartBtn = doc.getElementById("audio-restart-btn");
    restartBtn.addEventListener("click", function() {
      if (!audioReady) return;
      const region = window._clipRegion;
      const start = region ? region.start : 0;
      ws.setTime(start);
      ws.play();
    });
    ws.on("timeupdate", function(t) {
      if (!audioReady) return;
      const region = window._clipRegion;
      if (region && region.end < ws.getDuration() && t >= region.end && ws.isPlaying()) {
        ws.pause();
      }
    });
    const muteBtn = doc.getElementById("audio-mute-btn");
    muteBtn.addEventListener("click", function() {
      const nowMuted = !ws.getMuted();
      ws.setMuted(nowMuted);
      muteBtn.innerHTML = nowMuted ? VOLUME_OFF_ICON : VOLUME_ON_ICON;
      muteBtn.setAttribute("aria-label", nowMuted ? data.lang.unmute : data.lang.mute);
    });
    const timeDisplay = doc.getElementById("audio-time-display");
    ws.on("ready", function() {
      const dur = ws.getDuration();
      timeDisplay.textContent = "0:00 / " + formatTime(dur);
      const durDisplay = doc.getElementById("audio-duration-display");
      if (durDisplay) durDisplay.textContent = formatTime(dur);
    });
    ws.on("timeupdate", function(currentTime) {
      const dur = ws.getDuration();
      timeDisplay.textContent = formatTime(currentTime) + " / " + formatTime(dur);
    });
    const RegionsPlugin = window.WaveSurfer.Regions;
    const regionsPlugin = ws.registerPlugin(RegionsPlugin.create());
    ws.on("ready", function() {
      const dur = ws.getDuration();
      const region = regionsPlugin.addRegion({
        start: 0,
        end: dur,
        color: "rgba(255, 255, 255, 0.08)",
        drag: true,
        resize: true
      });
      var startDisp = doc.getElementById("clip-start-display");
      var endDisp = doc.getElementById("clip-end-display");
      if (startDisp) startDisp.textContent = region.start.toFixed(3);
      if (endDisp) endDisp.textContent = region.end.toFixed(3);
      region.on("update-end", function() {
        if (startDisp) startDisp.textContent = region.start.toFixed(3);
        if (endDisp) endDisp.textContent = region.end.toFixed(3);
      });
      window._clipRegion = region;
      const regionEl = region.element;
      if (regionEl) {
        regionEl.style.borderLeft = "3px solid rgba(255, 255, 255, 0.8)";
        regionEl.style.borderRight = "3px solid rgba(255, 255, 255, 0.8)";
        regionEl.style.cursor = "move";
      }
    });
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

  // assets/js/object-page/audio-entry.js
  onObjectPage((data) => {
    initAudioPlayer(data);
    initClipPanelToggle();
    initClipCopyButtons(data.lang.copied);
  });
})();
//# sourceMappingURL=object-audio.js.map
