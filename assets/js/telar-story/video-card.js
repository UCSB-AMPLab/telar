/**
 * Telar Story -- Video Card
 *
 * This module manages the lifecycle of video players embedded in story
 * steps. Telar supports three video providers — YouTube, Vimeo, and
 * Google Drive — each with its own player API and embed mechanism.
 * Video cards follow the same DOM-at-init, visibility-via-transforms
 * pattern as IIIF cards but use iframe embeds instead of Tify viewers.
 *
 * Layout — when a video step activates, the module calculates the optimal
 * arrangement by comparing how many pixels the video would occupy in a
 * side-by-side layout (video left, text right) versus a stacked layout
 * (video top, text below). Whichever arrangement gives the video more
 * screen area wins. On mobile viewports the layout is always stacked,
 * since side-by-side is too narrow to be useful.
 *
 * Player pool — at most three video players exist at once (the current
 * card, plus one or two preloaded ahead). When a fourth is needed, the
 * player farthest from the current scene by index distance is destroyed.
 * This keeps memory use bounded without destroying players the user is
 * likely to scroll back to.
 *
 * Clip control — each step can specify a clip_start and clip_end time in
 * seconds. YouTube clips are enforced by a requestAnimationFrame polling
 * loop (the YouTube ENDED event is unreliable for mid-video clips),
 * while Vimeo uses its timeupdate event. A semi-transparent dim overlay
 * fades in over the video when the clip reaches its end. The loop flag
 * restarts the clip from clip_start when clip_end is reached.
 *
 * Autoplay — on desktop, the module attempts autoplay and catches the
 * browser's NotAllowedError if it fails. YouTube is checked by looking
 * for a PLAYING state within two seconds of the player's onReady event;
 * Vimeo uses player.play().catch(). When autoplay is blocked, a frosted
 * glass play overlay appears over the video. Tapping it sets a session
 * flag (state.hasUserInteracted) that enables autoplay for all subsequent
 * media cards. On mobile and in embeds, the overlay always appears.
 * Google Drive embeds have no player API, so they receive no clip control
 * or autoplay detection.
 *
 * @version v1.0.0-beta
 */

import { state } from './state.js';

// ── Module-level player pool ──────────────────────────────────────────────────

/** Active video player wrappers. Capped at MAX_VIDEO_PLAYERS. */
const _videoPlayers = [];

/** Maximum concurrent video player instances. */
const MAX_VIDEO_PLAYERS = 3;

// ── YouTube API loader ────────────────────────────────────────────────────────

/**
 * Load the YouTube IFrame API once, returning a Promise that resolves when
 * the API is ready. Subsequent calls return the same Promise.
 *
 * Uses window._ytApiPromise as a once-guard so the script tag is only
 * appended once even if loadYouTubeAPI() is called multiple times.
 *
 * @returns {Promise<void>}
 */
export function loadYouTubeAPI() {
  if (window._ytApiPromise) return window._ytApiPromise;

  window._ytApiPromise = new Promise((resolve) => {
    if (window.YT && window.YT.Player) {
      resolve();
      return;
    }

    const script = document.createElement('script');
    script.src = 'https://www.youtube.com/iframe_api';
    script.async = true;
    document.head.appendChild(script);

    // YouTube calls this global when the API is ready
    const prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = function () {
      if (typeof prev === 'function') prev();
      resolve();
    };
  });

  return window._ytApiPromise;
}

/**
 * Load the Vimeo Player API once from CDN, returning a Promise that resolves
 * when window.Vimeo.Player is available. Mirrors loadYouTubeAPI() pattern.
 *
 * @returns {Promise<void>}
 */
export function loadVimeoAPI() {
  if (window._vimeoApiPromise) return window._vimeoApiPromise;

  window._vimeoApiPromise = new Promise((resolve, reject) => {
    if (window.Vimeo && window.Vimeo.Player) {
      resolve();
      return;
    }

    const script = document.createElement('script');
    script.src = 'https://player.vimeo.com/api/player.js';
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Failed to load Vimeo Player API'));
    document.head.appendChild(script);
  });

  return window._vimeoApiPromise;
}

// ── Pure functions (unit-tested) ──────────────────────────────────────────────

/**
 * Compute the optimal video + card layout for the given viewport dimensions
 * and video aspect ratio.
 *
 * Algorithm:
 *   Two candidates are computed:
 *   - Side-by-side: card left (35% of W), video right in remaining space.
 *   - Stacked: video top (max 58% of H), card below.
 *   The candidate that gives the video more rendered pixels wins.
 *   Mobile override: W < 768 always returns stacked.
 *
 * @param {number} W - Viewport width in px
 * @param {number} H - Viewport height in px
 * @param {number} aspectRatio - Video width / height (e.g. 16/9)
 * @returns {{ mode: 'side-by-side'|'stacked', video: {left,top,width,height}, card: {left,top,width,height}, padding: number }}
 */
export function computeVideoLayout(W, H, aspectRatio) {
  // Mobile override: always stacked
  if (W < 768) {
    return _computeStackedLayout(W, H, aspectRatio);
  }

  const pad = Math.max(8, Math.round(Math.min(W, H) * 0.025));

  // ── Side-by-side candidate ──
  const cardFracSide = 0.35;
  const sideCardW = Math.round(W * cardFracSide);
  const sideVideoMaxW = W - sideCardW - pad * 3;
  const sideVideoMaxH = H - pad * 2;
  let sideVidW = sideVideoMaxW;
  let sideVidH = sideVidW / aspectRatio;
  if (sideVidH > sideVideoMaxH) {
    sideVidH = sideVideoMaxH;
    sideVidW = sideVidH * aspectRatio;
  }
  const sideVideoArea = sideVidW * sideVidH;

  // ── Stacked candidate ──
  const stackVideoMaxW = W - pad * 2;
  const stackVideoMaxH = H * 0.58;
  let stackVidW = stackVideoMaxW;
  let stackVidH = stackVidW / aspectRatio;
  if (stackVidH > stackVideoMaxH) {
    stackVidH = stackVideoMaxH;
    stackVidW = stackVidH * aspectRatio;
  }
  const stackVideoArea = stackVidW * stackVidH;

  if (sideVideoArea >= stackVideoArea) {
    return _buildSideBySideResult(W, H, pad, sideCardW, sideVidW, sideVidH);
  } else {
    return _buildStackedResult(W, H, pad, stackVidW, stackVidH);
  }
}

/** Build side-by-side layout result object. */
function _buildSideBySideResult(W, H, pad, sideCardW, sideVidW, sideVidH) {
  const vidW = Math.round(sideVidW);
  const vidH = Math.round(sideVidH);
  const vidLeft = sideCardW + pad * 2;
  const vidTop = Math.round((H - vidH) / 2);
  const cardW = sideCardW;
  const cardH = Math.round(H - pad * 2);
  const cardLeft = pad;
  const cardTop = pad;
  const cardPad = cardW > 300 ? 24 : cardW > 200 ? 16 : 10;

  return {
    mode: 'side-by-side',
    video: { left: vidLeft, top: vidTop, width: vidW, height: vidH },
    card: { left: cardLeft, top: cardTop, width: cardW, height: cardH },
    padding: cardPad,
  };
}

/** Build stacked layout result object. */
function _buildStackedResult(W, H, pad, stackVidW, stackVidH) {
  const vidW = Math.round(stackVidW);
  const vidH = Math.round(stackVidH);
  const vidLeft = Math.round((W - vidW) / 2);
  const vidTop = pad;
  const cardTop = vidTop + vidH + pad;
  const cardH = Math.max(60, H - cardTop - pad);
  const cardW = Math.round(W - pad * 2);
  const cardLeft = pad;
  const cardPad = cardH > 200 ? 22 : cardH > 120 ? 14 : 8;

  return {
    mode: 'stacked',
    video: { left: vidLeft, top: vidTop, width: vidW, height: vidH },
    card: { left: cardLeft, top: cardTop, width: cardW, height: cardH },
    padding: cardPad,
  };
}

/** Compute stacked layout for mobile. */
function _computeStackedLayout(W, H, aspectRatio) {
  const pad = Math.max(8, Math.round(Math.min(W, H) * 0.025));
  const stackVideoMaxW = W - pad * 2;
  const stackVideoMaxH = H * 0.58;
  let stackVidW = stackVideoMaxW;
  let stackVidH = stackVidW / aspectRatio;
  if (stackVidH > stackVideoMaxH) {
    stackVidH = stackVideoMaxH;
    stackVidW = stackVidH * aspectRatio;
  }
  return _buildStackedResult(W, H, pad, stackVidW, stackVidH);
}

/**
 * Build the YouTube playerVars config object.
 *
 * @param {string} videoId - YouTube video ID
 * @param {number} clipStart - Start time in seconds (0 = no restriction)
 * @param {number} clipEnd - End time in seconds (0 = no restriction, unused in playerVars)
 * @param {boolean} loop - Whether the clip should loop
 * @returns {{ videoId: string, playerVars: Object }}
 */
export function buildYouTubeEmbedConfig(videoId, clipStart, clipEnd, loop) {
  return {
    videoId,
    playerVars: {
      start: clipStart || 0,
      autoplay: 0,
      mute: 0,
      // loop/playlist omitted — segment looping handled by rAF polling
      // (YouTube loop playerVar loops the whole video, not the clip)
      controls: 1,
      rel: 0,
      modestbranding: 1,
    },
  };
}

/**
 * Build the Google Drive embed preview URL for a file ID.
 *
 * @param {string} fileId - Google Drive file ID
 * @returns {string} Preview URL
 */
export function buildGDriveEmbedUrl(fileId) {
  return `https://drive.google.com/file/d/${fileId}/preview`;
}

/**
 * Format a time in seconds as 'M:SS' for the progress ring display.
 *
 * @param {number} seconds - Time in seconds (may be fractional, will be floored)
 * @returns {string} Formatted time, e.g. '0:42', '1:07'
 */
export function formatClipTime(seconds) {
  const total = Math.floor(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

// ── DOM helpers ───────────────────────────────────────────────────────────────

/**
 * Apply a semi-transparent dim overlay over the video iframe at clip_end.
 * Creates a div.clip-end-overlay absolutely positioned over the iframe.
 * Fades in over 300ms.
 *
 * @param {HTMLElement} plateEl - The video plate element
 */
export function applyClipEndDim(plateEl) {
  let overlay = plateEl.querySelector('.clip-end-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.className = 'clip-end-overlay';
    plateEl.appendChild(overlay);
  }
  // Force reflow so transition fires
  void overlay.offsetHeight;
  overlay.classList.add('visible');
}

/**
 * Remove the clip-end dim overlay from a plate.
 *
 * @param {HTMLElement} plateEl - The video plate element
 */
export function removeClipEndDim(plateEl) {
  const overlay = plateEl.querySelector('.clip-end-overlay');
  if (overlay) {
    overlay.classList.remove('visible');
  }
}

// ── Player lifecycle ──────────────────────────────────────────────────────────

/**
 * Create a video player inside the given plate element.
 *
 * Returns a player wrapper object { type, element, player, sceneIndex, destroy() }.
 * The wrapper is also pushed into the module-level _videoPlayers pool.
 *
 * Pool management: when the pool exceeds MAX_VIDEO_PLAYERS, the farthest player
 * by scene distance is evicted.
 *
 * @param {HTMLElement} plateEl - The viewer plate to host the player
 * @param {'youtube'|'vimeo'|'google-drive'} cardType
 * @param {string} videoId - Provider-specific video ID
 * @param {Object} options
 * @param {number} [options.clipStart=0]
 * @param {number} [options.clipEnd] - If set, pause at this time
 * @param {boolean} [options.loop=false]
 * @param {Function} [options.onPlay] - Called when playback starts
 * @param {Function} [options.onTimeUpdate] - Called each frame with (currentTime, duration)
 * @param {Function} [options.onEnded] - Called when clip ends (clipEnd reached)
 * @param {Function} [options.onAutoplayBlocked] - Called when autoplay is blocked
 * @param {number} [options.sceneIndex=0] - Scene index (used for pool eviction ordering)
 * @returns {Object} Player wrapper
 */
export function createVideoPlayer(plateEl, cardType, videoId, options = {}) {
  const {
    clipStart = 0,
    clipEnd,
    loop = false,
    onPlay = () => {},
    onTimeUpdate = () => {},
    onEnded = () => {},
    onAutoplayBlocked = () => {},
    sceneIndex = 0,
    sourceUrl = '',
  } = options;

  let wrapper;

  if (cardType === 'youtube') {
    wrapper = _createYouTubePlayer(plateEl, videoId, {
      clipStart, clipEnd, loop, onPlay, onTimeUpdate, onEnded, onAutoplayBlocked, sceneIndex,
    });
  } else if (cardType === 'vimeo') {
    wrapper = _createVimeoPlayer(plateEl, videoId, {
      clipStart, clipEnd, loop, onPlay, onTimeUpdate, onEnded, onAutoplayBlocked, sceneIndex, sourceUrl,
    });
  } else if (cardType === 'google-drive') {
    wrapper = _createGDriveEmbed(plateEl, videoId, sceneIndex);
  } else {
    console.error('createVideoPlayer: unknown cardType', cardType);
    return null;
  }

  _videoPlayers.push(wrapper);

  // Enforce pool size limit
  _enforcePoolLimit(sceneIndex);

  // Apply layout immediately so the iframe is positioned correctly
  // during scroll-driven slide-up (before activateVideoCard is called)
  _applyVideoLayout(plateEl);

  return wrapper;
}

/**
 * Destroy a video player wrapper, releasing its resources.
 *
 * @param {Object} wrapper - Player wrapper returned by createVideoPlayer
 */
export function destroyVideoPlayer(wrapper) {
  if (!wrapper) return;

  try {
    if (wrapper.type === 'youtube' && wrapper.player) {
      if (wrapper._rafId) cancelAnimationFrame(wrapper._rafId);
      if (wrapper._autoplayTimeout) clearTimeout(wrapper._autoplayTimeout);
      wrapper.player.destroy();
    } else if (wrapper.type === 'vimeo' && wrapper.player) {
      wrapper.player.destroy();
    } else if (wrapper.type === 'google-drive') {
      const iframe = wrapper.element.querySelector('iframe.video-iframe');
      if (iframe) iframe.remove();
    }
  } catch (e) {
    console.warn('destroyVideoPlayer: error during destroy', e);
  }

  // Remove from pool
  const idx = _videoPlayers.indexOf(wrapper);
  if (idx !== -1) _videoPlayers.splice(idx, 1);
}

/**
 * Activate a video card plate: position it using auto-layout and reveal it.
 *
 * @param {HTMLElement} plateEl - The video plate element
 * @param {number} sceneIndex - Scene index (used for layout and z-index)
 */
/**
 * Show the frosted glass pill play overlay on a video plate.
 *
 * Creates the overlay on first call; subsequent calls just make it visible.
 * Overlay click sets state.hasUserInteracted = true and resumes playback.
 *
 * @param {HTMLElement} plateEl - The video plate element
 */
function _showVideoPlayOverlay(plateEl) {
  const existing = plateEl.querySelector('.video-play-overlay');
  if (existing) {
    existing.style.display = 'flex';
    return;
  }

  const overlayEl = document.createElement('div');
  overlayEl.className = 'video-play-overlay';
  overlayEl.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;z-index:1;';

  // Dynamic aria-label using object alt_text/title
  const _vObjectsData = window.objectsData || [];
  const _vObj = _vObjectsData.find(o => o.object_id === plateEl.dataset.object) || {};
  const _vAlt = _vObj.alt_text || _vObj.title || 'video';
  const overlayBtn = document.createElement('button');
  overlayBtn.setAttribute('aria-label', `Play ${_vAlt}`);
  overlayBtn.type = 'button';
  // Frosted glass pill variant
  overlayBtn.style.cssText = 'min-height:44px;padding:0.5rem 1.25rem;border-radius:20px;background:rgba(255,255,255,0.6);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);border:none;cursor:pointer;box-shadow:0 2px 12px rgba(0,0,0,0.2);display:flex;align-items:center;gap:8px;color:#333;font-family:var(--font-body);font-size:0.9rem;';
  overlayBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="var(--color-link)" xmlns="http://www.w3.org/2000/svg"><polygon points="5,3 19,12 5,21"/></svg><span>Play</span>';
  overlayEl.appendChild(overlayBtn);
  plateEl.appendChild(overlayEl);

  overlayBtn.addEventListener('click', () => {
    state.hasUserInteracted = true; // unlock all subsequent media
    overlayEl.style.display = 'none';
    // Resume video playback
    const wrapper = _getWrapperForPlate(plateEl);
    if (wrapper && wrapper.player) {
      try {
        if (wrapper.type === 'youtube') {
          wrapper.player.playVideo();
        } else if (wrapper.type === 'vimeo') {
          wrapper.player.play();
        }
      } catch (e) {
        // Ignore — player may not be ready
      }
    }
  });
}

/** @public Exposed so card-pool.js can call it from the onAutoplayBlocked callback. */
export { _showVideoPlayOverlay as showVideoPlayOverlay };

export function activateVideoCard(plateEl, sceneIndex) {
  // Bring plate into view
  plateEl.style.transform = 'translateY(0)';
  plateEl.classList.add('is-active');

  // Apply auto-layout
  _applyVideoLayout(plateEl);

  const isEmbed = document.body.classList.contains('embed-mode');
  // Autoplay policy — always manual on mobile and embed
  if (state.isMobileViewport || isEmbed) {
    if (!state.hasUserInteracted) {
      _showVideoPlayOverlay(plateEl);
      return;
    }
  }

  // Trigger playback — autoplay is off so we play on activation
  const wrapper = _getWrapperForPlate(plateEl);
  if (wrapper) {
    try {
      if (wrapper.type === 'youtube' && wrapper.player) {
        wrapper.player.playVideo();
      } else if (wrapper.type === 'vimeo' && wrapper.player) {
        wrapper.player.play().catch(() => {});
      }
    } catch (e) {
      // Ignore — player may not be ready yet
    }
  }
}

/**
 * Deactivate a video card plate: pause playback and hide the plate.
 *
 * @param {HTMLElement} plateEl - The video plate element
 */
export function deactivateVideoCard(plateEl) {
  plateEl.classList.remove('is-active');
  // NOTE: does NOT touch transform — caller decides positioning
  // (forward nav: plate stays put, covered by incoming plate;
  //  backward nav: caller sets translateY(100%) to slide it away)

  // Pause the player if one exists
  const wrapper = _getWrapperForPlate(plateEl);
  if (!wrapper) return;

  try {
    if (wrapper.type === 'youtube' && wrapper.player) {
      wrapper.player.pauseVideo();
    } else if (wrapper.type === 'vimeo' && wrapper.player) {
      wrapper.player.pause();
    }
    // Google Drive: no API available
  } catch (e) {
    // Ignore — player may have been destroyed
  }
}

/**
 * Update clip parameters for an existing video player and seek to the new
 * clip start. Used when navigating between steps on the same video object
 * (same scene, different clip range).
 *
 * @param {HTMLElement} plateEl - The video plate element
 * @param {number} clipStart - New clip start in seconds
 * @param {number} clipEnd - New clip end in seconds (0 = no restriction)
 * @param {boolean} loop - Whether the new clip should loop
 */
export function updateVideoClip(plateEl, clipStart, clipEnd, loop) {
  const wrapper = _getWrapperForPlate(plateEl);
  if (!wrapper) return;

  // Same clip params — let the video keep playing uninterrupted
  if (wrapper.clipStart === clipStart && wrapper.clipEnd === clipEnd && wrapper.loop === loop) {
    return;
  }

  // Update wrapper state (polling reads from these)
  wrapper.clipStart = clipStart;
  wrapper.clipEnd = clipEnd;
  wrapper.loop = loop;

  // Update plate dataset for consistency
  plateEl.dataset.clipStart = String(clipStart);
  plateEl.dataset.clipEnd = String(clipEnd);
  plateEl.dataset.loop = String(loop);

  // Remove any clip-end dim from previous clip
  removeClipEndDim(plateEl);

  // Seek to new clip start
  try {
    if (wrapper.type === 'youtube' && wrapper.player) {
      wrapper.player.seekTo(clipStart || 0, true);
      // Restart polling if it was stopped (previous clip ended without loop)
      if (!wrapper._rafId) {
        wrapper.player.playVideo();
      }
    } else if (wrapper.type === 'vimeo' && wrapper.player) {
      wrapper.player.setCurrentTime(clipStart || 0.01).catch(() => {});
      // Resume if paused from previous clip end
      wrapper.player.play().catch(() => {});
    }
  } catch (e) {
    // Player may not be ready yet
  }
}

// ── Private helpers ───────────────────────────────────────────────────────────

/**
 * Create a YouTube player wrapper.
 */
function _createYouTubePlayer(plateEl, videoId, opts) {
  const { clipStart, clipEnd, loop, onPlay, onTimeUpdate, onEnded, onAutoplayBlocked, sceneIndex } = opts;

  const container = document.createElement('div');
  container.className = 'video-iframe';
  plateEl.appendChild(container);

  const wrapper = {
    type: 'youtube',
    element: plateEl,
    player: null,
    sceneIndex,
    clipStart,
    clipEnd,
    loop,
    _rafId: null,
    _autoplayTimeout: null,
    _playReceived: false,
    destroy() { destroyVideoPlayer(this); },
  };

  loadYouTubeAPI().then(() => {
    const cfg = buildYouTubeEmbedConfig(videoId, clipStart, clipEnd, loop);

    wrapper.player = new window.YT.Player(container, {
      videoId: cfg.videoId,
      playerVars: cfg.playerVars,
      events: {
        onReady: (event) => {
          // Autoplay block detection: if PLAYING state not received within 2s, assume blocked
          wrapper._autoplayTimeout = setTimeout(() => {
            if (!wrapper._playReceived) {
              onAutoplayBlocked();
            }
          }, 2000);
        },
        onStateChange: (event) => {
          if (event.data === window.YT.PlayerState.PLAYING) {
            wrapper._playReceived = true;
            if (wrapper._autoplayTimeout) {
              clearTimeout(wrapper._autoplayTimeout);
              wrapper._autoplayTimeout = null;
            }
            onPlay();

            // Start rAF polling for clip_end and timeUpdate
            if (wrapper.clipEnd) {
              _startYouTubePolling(wrapper, onTimeUpdate, onEnded);
            }
          } else if (event.data === window.YT.PlayerState.PAUSED ||
                     event.data === window.YT.PlayerState.ENDED) {
            if (wrapper._rafId) {
              cancelAnimationFrame(wrapper._rafId);
              wrapper._rafId = null;
            }
          }
        },
      },
    });
  });

  return wrapper;
}

/**
 * Start rAF polling loop for YouTube clip_end enforcement and time updates.
 * We use polling (not the ENDED state) because the YouTube end event is
 * unreliable for clip_end mid-video.
 *
 * Reads clipStart/clipEnd/loop from wrapper so values stay current when
 * clip parameters change mid-scene (same-object multi-step navigation).
 */
function _startYouTubePolling(wrapper, onTimeUpdate, onEnded) {
  if (wrapper._rafId) cancelAnimationFrame(wrapper._rafId);

  function poll() {
    if (!wrapper.player) return;
    try {
      const currentTime = wrapper.player.getCurrentTime();
      const duration = wrapper.player.getDuration();
      onTimeUpdate(currentTime, duration);

      if (wrapper.clipEnd && currentTime >= wrapper.clipEnd) {
        if (wrapper.loop) {
          // Segment loop: seek back to clipStart instead of pausing
          wrapper.player.seekTo(wrapper.clipStart || 0, true);
        } else {
          wrapper.player.pauseVideo();
          onEnded();
          return; // stop polling
        }
      }
    } catch (e) {
      return; // player destroyed
    }
    wrapper._rafId = requestAnimationFrame(poll);
  }

  wrapper._rafId = requestAnimationFrame(poll);
}

/**
 * Create a Vimeo player wrapper.
 */
function _createVimeoPlayer(plateEl, videoId, opts) {
  const { clipStart, clipEnd, loop, onPlay, onTimeUpdate, onEnded, onAutoplayBlocked, sceneIndex, sourceUrl } = opts;

  const container = document.createElement('div');
  container.className = 'video-iframe';
  plateEl.appendChild(container);

  const wrapper = {
    type: 'vimeo',
    element: plateEl,
    player: null,
    sceneIndex,
    clipStart,
    clipEnd,
    loop,
    destroy() { destroyVideoPlayer(this); },
  };

  // Load Vimeo API from CDN on demand, then create the player
  loadVimeoAPI().then(() => {
    // For unlisted videos, pass the full player URL (contains the privacy
    // hash as ?h= parameter). For public videos, pass the numeric ID.
    const playerOpts = {
      autoplay: false,
      loop: false,
      controls: true,
    };
    const hashMatch = sourceUrl && sourceUrl.match(/vimeo\.com\/\d+\/([a-f0-9]+)/i);
    if (hashMatch) {
      // Unlisted: construct the player URL with hash
      playerOpts.url = `https://vimeo.com/${videoId}/${hashMatch[1]}`;
    } else {
      playerOpts.id = parseInt(videoId, 10) || videoId;
    }

    const vimeoPlayer = new window.Vimeo.Player(container, playerOpts);

    wrapper.player = vimeoPlayer;

    // On ready: query real dimensions for layout, then seek to clip start
    vimeoPlayer.ready().then(() => {
      return Promise.all([
        vimeoPlayer.getVideoWidth(),
        vimeoPlayer.getVideoHeight(),
      ]).then(([w, h]) => {
        if (w && h) {
          plateEl.dataset.aspectRatio = String(w / h);
          _applyVideoLayout(plateEl);
        }
      });
    }).then(() => {
      if (clipStart) {
        vimeoPlayer.setCurrentTime(clipStart).catch(() => {});
      }
    });

    vimeoPlayer.on('play', () => {
      onPlay();
    });

    vimeoPlayer.on('timeupdate', ({ seconds, duration }) => {
      onTimeUpdate(seconds, duration);
      if (wrapper.clipEnd && seconds >= wrapper.clipEnd) {
        if (wrapper.loop) {
          // Segment loop: seek back to clipStart
          vimeoPlayer.setCurrentTime(wrapper.clipStart || 0.01).catch(() => {});
        } else {
          vimeoPlayer.pause().catch(() => {});
          onEnded();
        }
      }
    });

    // Detect autoplay block
    vimeoPlayer.play().catch(err => {
      if (err && (err.name === 'NotAllowedError' || err.name === 'PasswordError')) {
        onAutoplayBlocked();
      }
    });
  }).catch(err => {
    console.error('Failed to load Vimeo API:', err);
  });

  return wrapper;
}

/**
 * Create a Google Drive static iframe embed.
 * No API available for clip control or playback events.
 */
function _createGDriveEmbed(plateEl, videoId, sceneIndex) {
  const iframe = document.createElement('iframe');
  iframe.className = 'video-iframe';
  iframe.src = buildGDriveEmbedUrl(videoId);
  iframe.allow = 'autoplay';
  iframe.allowFullscreen = true;
  iframe.style.cssText = 'width:100%;height:100%;border:none;border-radius:4px';

  plateEl.appendChild(iframe);

  return {
    type: 'google-drive',
    element: plateEl,
    player: null,
    sceneIndex,
    destroy() { destroyVideoPlayer(this); },
  };
}

/**
 * Enforce the player pool size limit.
 * Evicts the farthest player by scene distance when cap is exceeded.
 *
 * @param {number} currentScene - The currently active scene index
 */
function _enforcePoolLimit(currentScene) {
  while (_videoPlayers.length > MAX_VIDEO_PLAYERS) {
    let farthestIdx = 0;
    let maxDist = -1;
    for (let i = 0; i < _videoPlayers.length; i++) {
      const dist = Math.abs(_videoPlayers[i].sceneIndex - currentScene);
      if (dist > maxDist) {
        maxDist = dist;
        farthestIdx = i;
      }
    }
    const evicted = _videoPlayers.splice(farthestIdx, 1)[0];
    _evictPlayer(evicted);
  }
}

/**
 * Evict a player without removing it from the _videoPlayers array
 * (used during pool enforcement where the splice already handles removal).
 */
function _evictPlayer(wrapper) {
  try {
    if (wrapper.type === 'youtube' && wrapper.player) {
      if (wrapper._rafId) cancelAnimationFrame(wrapper._rafId);
      if (wrapper._autoplayTimeout) clearTimeout(wrapper._autoplayTimeout);
      wrapper.player.destroy();
    } else if (wrapper.type === 'vimeo' && wrapper.player) {
      wrapper.player.destroy();
    } else if (wrapper.type === 'google-drive') {
      const iframe = wrapper.element.querySelector('iframe.video-iframe');
      if (iframe) iframe.remove();
    }
  } catch (e) {
    console.warn('_evictPlayer: error during evict', e);
  }
}

/**
 * Find the player wrapper for a given plate element.
 *
 * @param {HTMLElement} plateEl
 * @returns {Object|null}
 */
function _getWrapperForPlate(plateEl) {
  return _videoPlayers.find(w => w.element === plateEl) || null;
}

/**
 * Apply the auto-layout algorithm to a video plate.
 * Positions the iframe and (if present) the text card within the plate.
 *
 * @param {HTMLElement} plateEl - The video plate element
 */
function _applyVideoLayout(plateEl) {
  const W = window.innerWidth;
  const H = window.innerHeight;
  const aspectRatio = parseFloat(plateEl.dataset.aspectRatio) || 16 / 9;

  const layout = computeVideoLayout(W, H, aspectRatio);

  // Position the video iframe
  const videoEl = plateEl.querySelector('.video-iframe');
  if (videoEl) {
    videoEl.style.position = 'absolute';
    videoEl.style.left = `${layout.video.left}px`;
    videoEl.style.top = `${layout.video.top}px`;
    videoEl.style.width = `${layout.video.width}px`;
    videoEl.style.height = `${layout.video.height}px`;
  }
}

// ── Resize handler ────────────────────────────────────────────────────────────

let _resizeDebounceTimer = null;

window.addEventListener('resize', () => {
  if (_resizeDebounceTimer) clearTimeout(_resizeDebounceTimer);
  _resizeDebounceTimer = setTimeout(() => {
    // Recompute layout for all active video plates
    for (const wrapper of _videoPlayers) {
      if (wrapper.element && wrapper.element.classList.contains('is-active')) {
        _applyVideoLayout(wrapper.element);
      }
    }
  }, 100);
});
