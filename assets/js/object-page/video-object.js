/**
 * The video object page: the embed, the Google Drive fallback, the clip
 * picker driven by the YouTube or Vimeo player API, and the copy-embed
 * button. The provider is read from the source URL here.
 *
 * Version: v1.7.0
 */

import { copyWithFeedback, CHECK_ICON } from './copy-feedback.js';

export function videoProvider(sourceUrl) {
  if (sourceUrl.includes('youtube.com') || sourceUrl.includes('youtu.be')) return 'youtube';
  if (sourceUrl.includes('vimeo.com')) return 'vimeo';
  if (sourceUrl.includes('drive.google.com')) return 'gdrive';
  return null;
}

export function initVideoEmbed(data, doc = document) {
  const viewer = doc.getElementById('object-viewer');
  const sourceUrl = data.sourceUrl;

  // Provider detection, video-ID extraction, and iframe construction live in
  // video-embed.js (loaded by the layout); this injects the result and wires
  // the page around it. The frame title is Liquid-escaped for attribute
  // context, which resolveVideoEmbed requires.
  const embed = window.telarVideoEmbed.resolveVideoEmbed(sourceUrl, data.videoFrameTitle);
  if (!embed) return;
  viewer.innerHTML = embed.iframeHtml;

  if (videoProvider(sourceUrl) !== 'gdrive') {
    // Set embed URL display (YouTube/Vimeo; the Drive sidebar has no display)
    const embedDisplay = doc.getElementById('embed-url-display');
    if (embedDisplay) embedDisplay.textContent = embed.embedUrl;
  } else {
    // Google Drive: embed URL load error fallback
    const iframe = doc.getElementById('video-player-iframe');
    let loadTimer = setTimeout(function() {
      // Build the fallback with DOM nodes and only render a clickable link for
      // http(s) URLs, so a javascript:/data: source_url cannot become a live link.
      const warn = doc.createElement('div');
      warn.className = 'alert alert-warning';
      const p = doc.createElement('p');
      p.textContent = data.lang.embedUnavailable + ' ';
      if (/^https?:/i.test(sourceUrl)) {
        const a = doc.createElement('a');
        a.href = sourceUrl;
        a.target = '_blank';
        a.rel = 'noopener';
        a.textContent = data.lang.openOnDrive;
        p.appendChild(a);
      }
      warn.appendChild(p);
      viewer.replaceChildren(warn);
    }, 10000);
    iframe.addEventListener('load', function() { clearTimeout(loadTimer); });
  }
}

function enableClipButtons(doc) {
  var startBtn = doc.getElementById('set-clip-start');
  var endBtn = doc.getElementById('set-clip-end');
  if (startBtn) startBtn.disabled = false;
  if (endBtn) endBtn.disabled = false;
}

export function initClipPicker(data, doc = document) {
  const provider = videoProvider(data.sourceUrl);

  if (provider === 'youtube') {
    // Load YouTube IFrame API for clip picker
    var tag = doc.createElement('script');
    tag.src = 'https://www.youtube.com/iframe_api';
    doc.head.appendChild(tag);

    window.onYouTubeIframeAPIReady = function() {
      window.ytPlayer = new YT.Player('video-player-iframe', {
        events: {
          onReady: function() { enableClipButtons(doc); }
        }
      });
    };
  } else if (provider === 'vimeo') {
    // Load Vimeo player.js for clip picker
    var vScript = doc.createElement('script');
    vScript.src = 'https://player.vimeo.com/api/player.js';
    vScript.onload = function() {
      var vPlayer = new Vimeo.Player('video-player-iframe');
      vPlayer.ready().then(function() { enableClipButtons(doc); });
      window._vimeoPlayer = vPlayer;

      // Detect actual video dimensions and set aspect ratio
      var vimeoIframe = doc.getElementById('video-player-iframe');
      Promise.all([vPlayer.getVideoWidth(), vPlayer.getVideoHeight()]).then(function(dims) {
        if (vimeoIframe) vimeoIframe.style.aspectRatio = dims[0] + '/' + dims[1];
      }).catch(function() {
        if (vimeoIframe) vimeoIframe.style.aspectRatio = '16/9';
      });
    };
    doc.head.appendChild(vScript);
  }

  // "Set to current time" handlers
  function getPlayerCurrentTime() {
    if (provider === 'youtube' && window.ytPlayer) return Promise.resolve(window.ytPlayer.getCurrentTime());
    if (provider === 'vimeo' && window._vimeoPlayer) return window._vimeoPlayer.getCurrentTime();
    return Promise.resolve(0);
  }

  var setStartBtn = doc.getElementById('set-clip-start');
  if (setStartBtn) {
    setStartBtn.addEventListener('click', function() {
      getPlayerCurrentTime().then(function(time) {
        doc.getElementById('clip-start-display').textContent = time.toFixed(3);
      });
    });
  }

  var setEndBtn = doc.getElementById('set-clip-end');
  if (setEndBtn) {
    setEndBtn.addEventListener('click', function() {
      getPlayerCurrentTime().then(function(time) {
        doc.getElementById('clip-end-display').textContent = time.toFixed(3);
      });
    });
  }
}

export function initCopyEmbedUrl(doc = document) {
  const copyEmbedBtn = doc.getElementById('copy-embed-url');
  if (copyEmbedBtn) {
    copyEmbedBtn.addEventListener('click', function() {
      const url = doc.getElementById('embed-url-display').textContent;
      copyWithFeedback(url, 'copy-embed-url', CHECK_ICON, doc);
    });
  }
}
