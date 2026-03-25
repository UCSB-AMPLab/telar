/**
 * Telar Story -- Audio Card
 *
 * This module manages the lifecycle of WaveSurfer v7 audio players for
 * self-hosted audio objects (MP3, OGG, M4A). Audio cards follow the same
 * DOM-at-init, visibility-via-transforms pattern as IIIF and video cards,
 * but instead of an iframe or tile viewer the entire viewport background
 * becomes a waveform visualisation.
 *
 * Theme colours — the waveform's colour palette is derived at runtime
 * from the site's --color-link CSS custom property. The background is
 * darkened to 70% of the accent colour and overlaid with the telar weave
 * pattern. Waveform bars use 40% of the accent, composited to opaque
 * values because WaveSurfer's clip-path rendering breaks with
 * semi-transparent bar colours.
 *
 * Controls — three frosted-glass circular buttons (44px, matching mobile
 * touch targets) float over the waveform: play/pause, restart from clip
 * start, and mute/unmute. An elapsed time display sits alongside them.
 * All icons are inline Lucide SVGs.
 *
 * Player pool — at most three WaveSurfer instances exist at once. When a
 * fourth is needed, the player farthest by scene distance is destroyed.
 * All players share a single AudioContext (module-level singleton) to
 * respect the browser's limit of roughly six concurrent contexts.
 *
 * Clip control — each step can specify clip_start and clip_end times.
 * WaveSurfer's timeupdate event enforces clip_end (the finish event
 * only fires at end-of-file). A dim overlay fades in when the clip
 * reaches its end. The loop flag restarts from clip_start on completion.
 *
 * Autoplay and crossfade — on desktop the module attempts autoplay and
 * falls back to a circular play overlay (80x80px) if the browser blocks
 * it. Embeds always show the overlay. When a playing audio card is
 * deactivated, its volume ramps to zero over 300ms before pausing, so
 * transitions between cards do not cut abruptly.
 *
 * Peaks — pre-computed peak JSON from process_audio.py is loaded when
 * available, allowing the waveform to render instantly. If no peaks file
 * exists, WaveSurfer falls back to client-side audio decoding, which is
 * slower but still functional. Audio load errors inject a .telar-alert
 * notification into the card area.
 *
 * @version v1.0.0-beta
 */

import { state } from './state.js';

// ── Module-level player pool ──────────────────────────────────────────────────

/** Active audio player wrappers. Capped at MAX_AUDIO_PLAYERS. */
const _audioPlayers = [];

/** Maximum concurrent WaveSurfer instances (AudioContext limit). */
const MAX_AUDIO_PLAYERS = 3;

/** Shared AudioContext singleton — created once on first use. */
let _sharedAudioContext = null;

// ── WaveSurfer CDN loader ─────────────────────────────────────────────────────

/**
 * Load WaveSurfer v7 core + Regions plugin from CDN once, returning a
 * Promise that resolves when both scripts are available.
 * Subsequent calls return the same Promise (once-guard pattern).
 *
 * @returns {Promise<void>}
 */
export function loadWaveSurferAPI() {
  if (window._wsApiPromise) return window._wsApiPromise;

  window._wsApiPromise = new Promise((resolve, reject) => {
    if (window.WaveSurfer) {
      resolve();
      return;
    }

    const script = document.createElement("script");
    script.src = "https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.min.js";
    script.async = true;
    script.onload = () => {
      // Load Regions plugin after core resolves
      const rScript = document.createElement("script");
      rScript.src =
        "https://unpkg.com/wavesurfer.js@7/dist/plugins/regions.min.js";
      rScript.async = true;
      rScript.onload = () => resolve();
      rScript.onerror = () =>
        reject(new Error("WaveSurfer Regions plugin failed to load"));
      document.head.appendChild(rScript);
    };
    script.onerror = () => reject(new Error("WaveSurfer failed to load"));
    document.head.appendChild(script);
  });

  return window._wsApiPromise;
}

// ── Pure functions (exported and unit-tested) ─────────────────────────────────

/**
 * Format a playback position in seconds as 'M:SS'.
 *
 * @param {number} seconds - Elapsed time in seconds (may be fractional)
 * @returns {string} Formatted time, e.g. '0:00', '1:03', '61:01'
 */
export function formatElapsedTime(seconds) {
  const total = Math.floor(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/**
 * Derive waveform theme colours from CSS theme values.
 *
 * Computes colours for the waveform, a solid opaque background, and
 * a telar weave pattern overlay.  The background is a muted tint of
 * the accent colour — light if the accent is dark, or dark if light.
 *
 * Bar colours derive from the button text colour so they adapt to any
 * theme (dark themes get light bars, light themes get dark bars).
 *
 * @param {string} accentHex - CSS hex colour for --color-link, e.g. '#883C36'
 * @param {string} [barHex='#ffffff'] - CSS hex colour for --color-button-text
 * @returns {Object} Theme colour set
 */
export function deriveThemeColors(accentHex, barHex = "#ffffff") {
  const r = parseInt(accentHex.slice(1, 3), 16);
  const g = parseInt(accentHex.slice(3, 5), 16);
  const b = parseInt(accentHex.slice(5, 7), 16);

  // Background: the accent colour itself, darkened slightly
  const bgR = Math.round(r * 0.7);
  const bgG = Math.round(g * 0.7);
  const bgB = Math.round(b * 0.7);

  // Bar colour from theme button text
  const bR = parseInt(barHex.slice(1, 3), 16);
  const bG = parseInt(barHex.slice(3, 5), 16);
  const bB = parseInt(barHex.slice(5, 7), 16);

  // Unplayed bars: alpha-composite bar colour @25% over the background.
  // Must be opaque — WaveSurfer 7.4.1+ clip-path breaks with semi-transparent colours.
  const upR = Math.round(bgR * 0.75 + bR * 0.25);
  const upG = Math.round(bgG * 0.75 + bG * 0.25);
  const upB = Math.round(bgB * 0.75 + bB * 0.25);

  return {
    playedColor: barHex, // played bars: theme button text colour
    unplayedColor: `rgb(${upR}, ${upG}, ${upB})`, // unplayed bars: opaque blended tint
    backgroundColor: `rgb(${bgR}, ${bgG}, ${bgB})`,
    patternColor: "rgba(255, 255, 255, 0.12)",
    clipRegionColor: "rgba(255, 255, 255, 0.08)", // subtle clip region highlight
  };
}

// ── Telar weave pattern SVG ───────────────────────────────────────────────────

/**
 * Build a data URI for the telar weave pattern SVG with a given fill colour.
 * The SVG path is the official telar background pattern (no background rect).
 */
function _buildPatternDataUri(fillColor) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 543 380"><path d="M542.955,145.508l-83.257,-0.001l13.365,45.375l-12.615,43.868l82.485,0l-0,10.507l-81.743,0l7.56,40.133l-7.582,38.235l81.765,1.125l-0,10.5l-82.485,0l12.742,44.25l-14.25,0l-13.875,-44.25l-12.375,0l0,44.25l-14.25,0l0,-44.25l-52.492,0l-6.75,44.25l-14.25,0l6.75,-44.25l-41.993,0l6.75,44.25l-14.25,0l-6.75,-44.25l-88.492,0l-0,44.25l-14.25,0l-0,-44.25l-59.993,0l0,44.25l-14.25,0l0,-44.25l-34.492,0l-0,44.25l-13.5,0l-0,-44.25l-70.478,0l0,-10.5l69.368,0l1.125,-1.125l-0,-78.375l-70.493,0l0,-10.5l69.368,0l0.375,-89.25l-69.743,0l0,-10.5l69.743,0l0.75,-79.5l-70.493,0l0,-10.5l69.368,0l1.162,-2.588l-0.037,-42.412l13.5,0l-0.038,42.412l1.163,2.588l33.367,0l0,-44.993l14.25,0.001l0,45l59.993,-0l-0,-45l14.25,-0l-0,45l88.492,-0l6.743,-45l14.25,-0l-6.75,45l41.992,-0l-6.742,-45l14.25,-0l6.75,45l52.492,-0l0,-45l14.25,-0l0.375,45l12.375,-0l13.493,-45l14.25,-0l-12.743,44.992l82.485,0l0,10.508l-81.742,-0l7.522,38.594l-8.272,40.905l82.507,0l0,10.5Zm-424.47,-90l-34.492,0.001l-0,79.499l34.492,0l0,-79.5Zm74.243,0.001l-59.993,-0l0,79.499l59.993,0l-0,-79.5Zm101.242,0.001l-86.992,-0l-0.75,79.499l86.992,0l-5.317,-38.625l6.067,-40.875Zm59.243,79.508l6.48,-40.23l-6.068,-38.565l-45.337,-0.622l-6.105,40.83l5.272,38.595l45.75,-0l0.008,-0.008Zm65.242,-79.507l-50.242,-0l5.842,38.632l-6.592,40.868l50.242,-0l0.75,-79.5Zm13.493,79.5l13.875,-0l9.135,-40.223l-8.385,-39.277l-13.875,-0l-0.75,79.5Zm-313.463,10.5l-34.492,-0l-0,89.25l34.492,-0l0,-89.25Zm14.25,-0l0,89.25l59.993,-0l-0,-89.25l-59.993,-0Zm162.728,89.25l6.375,-44.655l-6.503,-43.35l-1.005,-1.245l-88.117,-0l0.75,89.25l88.5,-0Zm55.5,-89.25l-41.243,-0l6.353,44.602l-6.353,44.648l41.993,-0l-7.418,-46.208l6.668,-43.042Zm66.742,-0l-52.492,-0l-6.593,43.132l7.343,46.118l52.492,-0l-0.75,-89.25Zm27.743,89.25l13.17,-44.61l-14.295,-44.64l-12.375,-0l1.125,89.25l12.375,-0Zm-326.963,10.5l-34.492,-0l-0,79.5l34.492,-0l0,-79.5Zm74.243,-0l-59.993,-0l0,79.5l59.993,-0l-0,-79.5Zm101.242,-0l-86.992,-0l-0,79.5l86.992,-0l-5.917,-40.043l5.917,-39.457Zm14.28,79.462l45.383,-0.66l6.24,-39.345l-6.615,-39.135l-44.97,-0.24l-5.79,39.42l5.745,39.96l0.007,0Zm110.205,-79.462l-50.242,-0l6.022,40.087l-6.022,39.413l50.242,-0l0,-79.5Zm14.243,79.5l13.875,-0l8.542,-40.05l-8.542,-39.45l-13.875,-0l-0,79.5Z" fill="${fillColor}" fill-rule="nonzero"/></svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}

// ── Lucide icon SVG paths (inline, no CDN dependency) ─────────────────────────

const _icons = {
  play: '<path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/>',
  pause:
    '<rect x="14" y="3" width="5" height="18" rx="1"/><rect x="5" y="3" width="5" height="18" rx="1"/>',
  "rotate-ccw":
    '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
  "volume-2":
    '<path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><path d="M16 9a5 5 0 0 1 0 6"/><path d="M19.364 18.364a9 9 0 0 0 0-12.728"/>',
  "volume-x":
    '<path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><line x1="22" y1="9" x2="16" y2="15"/><line x1="16" y1="9" x2="22" y2="15"/>',
};

function _svg(name, size = 24) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${_icons[name]}</svg>`;
}

/**
 * Build the HTML for audio controls — individual frosted-glass buttons.
 *
 * Three buttons: play/pause, restart, mute — each in its own circle.
 * Uses Lucide inline SVGs (no icon font dependency).
 *
 * @returns {string} HTML string
 */
export function buildAudioControlsHTML() {
  return `<div class="audio-controls">
  <button class="audio-btn audio-btn-play" aria-label="Play" type="button">${_svg("play", 22)}</button>
  <button class="audio-btn audio-btn-restart" aria-label="Restart from beginning" type="button">${_svg("rotate-ccw", 20)}</button>
  <button class="audio-btn audio-btn-mute" aria-label="Mute audio" type="button">${_svg("volume-2", 20)}</button>
</div>`;
}

// ── Shared AudioContext ───────────────────────────────────────────────────────

/**
 * Get (or lazy-create) the shared AudioContext singleton.
 *
 * Browsers cap AudioContext instances (~6). Sharing one instance across
 * all WaveSurfer players prevents that limit from being hit (Pitfall 2).
 * Handles Safari's webkitAudioContext fallback.
 *
 * @returns {AudioContext}
 */
export function getSharedAudioContext() {
  if (!_sharedAudioContext) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    _sharedAudioContext = new AudioContextClass();
  }
  return _sharedAudioContext;
}

// ── Player lifecycle ──────────────────────────────────────────────────────────

/**
 * Create a WaveSurfer audio player inside the given plate element.
 *
 * Loads WaveSurfer from CDN on demand (first call), fetches pre-computed
 * peaks JSON, reads the theme colour from --color-link, creates the
 * WaveSurfer instance, wires clip enforcement, controls, and callbacks.
 *
 * Returns a player wrapper pushed into the module-level _audioPlayers pool.
 * Pool is capped at MAX_AUDIO_PLAYERS.
 *
 * @param {HTMLElement} plateEl - The viewer plate element
 * @param {string} audioUrl - URL to the audio file
 * @param {string} peaksUrl - URL to the Telar peaks JSON (may 404 — falls back to client-side decode)
 * @param {Object} options
 * @param {number} [options.clipStart=0]
 * @param {number} [options.clipEnd] - If set, enforce clip boundary via timeupdate
 * @param {boolean} [options.loop=false] - If true, loop the clip region
 * @param {number} [options.sceneIndex=0] - For pool eviction ordering
 * @param {boolean} [options.isEmbed=false] - Embed context: always manual play
 * @param {Function} [options.onPlay]
 * @param {Function} [options.onTimeUpdate]
 * @param {Function} [options.onEnded]
 * @param {Function} [options.onAutoplayBlocked]
 * @param {Function} [options.onError]
 * @returns {Object} Player wrapper
 */
export function createAudioPlayer(plateEl, audioUrl, peaksUrl, options = {}) {
  const {
    clipStart = 0,
    clipEnd,
    loop = false,
    sceneIndex = 0,
    isEmbed = false,
    onPlay = () => {},
    onTimeUpdate = () => {},
    onEnded = () => {},
    onAutoplayBlocked = () => {},
    onError = () => {},
  } = options;

  const wrapper = {
    type: "audio",
    element: plateEl,
    ws: null,
    sceneIndex,
    clipStart,
    clipEnd,
    loop,
    isEmbed,
    _lastElapsedSecond: -1,
    destroy() {
      destroyAudioPlayer(this);
    },
  };

  _audioPlayers.push(wrapper);
  _enforceAudioPoolLimit(sceneIndex);

  loadWaveSurferAPI()
    .then(() => {
      // Fetch peaks JSON (404 is not an error — WaveSurfer decodes client-side)
      const peaksFetch = peaksUrl
        ? fetch(peaksUrl)
            .then((r) => (r.ok ? r.json() : null))
            .catch(() => null)
        : Promise.resolve(null);

      peaksFetch.then((peaksData) => {
        // Read theme colours from CSS custom properties
        const styles = getComputedStyle(document.documentElement);
        const accentColor =
          styles.getPropertyValue("--color-link").trim() || "#883C36";
        const barColor =
          styles.getPropertyValue("--color-button-text").trim() || "#ffffff";
        const colors = deriveThemeColors(accentColor, barColor);

        // Apply solid opaque background with telar weave pattern
        const patternUri = _buildPatternDataUri(colors.patternColor);
        plateEl.style.background = `${colors.backgroundColor} ${patternUri} repeat`;
        plateEl.style.backgroundSize = "20px auto";

        // Create waveform container (display-only)
        let waveContainer = plateEl.querySelector(".waveform-container");
        if (!waveContainer) {
          waveContainer = document.createElement("div");
          waveContainer.className = "waveform-container";
          // Layout handled by CSS class — mobile media query overrides position
          // Set aria-hidden — decorative, not interactive
          waveContainer.setAttribute("aria-hidden", "true");
          plateEl.appendChild(waveContainer);
        }

        // Create Regions plugin instance
        const regionsPlugin = window.WaveSurfer.Regions.create();

        // Create WaveSurfer instance
        const ws = window.WaveSurfer.create({
          container: waveContainer,
          url: audioUrl,
          peaks: peaksData ? peaksData.peaks : undefined,
          waveColor: colors.unplayedColor,
          progressColor: colors.playedColor,
          cursorWidth: 0, // hide cursor line — progress shown via bar colour change
          barWidth: 4,
          barGap: 5,
          barRadius: 5,
          height: Math.round(window.innerHeight * 0.35),
          interact: false,
          normalize: true,
          backend: "WebAudio",
          audioContext: getSharedAudioContext(),
          plugins: [regionsPlugin],
        });

        wrapper.ws = ws;
        wrapper._regionsPlugin = regionsPlugin;
        wrapper._colors = colors;

        // If activateAudioCard was called before ws was ready, run it now
        if (plateEl.classList.contains("is-active")) {
          activateAudioCard(plateEl, wrapper.sceneIndex);
        }

        // Highlight clip region after waveform is ready
        if (clipStart !== undefined && clipEnd) {
          ws.on("ready", () => {
            regionsPlugin.addRegion({
              start: clipStart,
              end: clipEnd,
              color: colors.clipRegionColor,
              drag: false,
              resize: false,
            });
          });
        }

        // Clip boundary enforcement via timeupdate (Pitfall 5 — not 'finish' event)
        ws.on("timeupdate", (currentTime) => {
          // Call onTimeUpdate at 1-second granularity for aria-live (Accessibility)
          const elapsedSecond = Math.floor(currentTime);
          if (elapsedSecond !== wrapper._lastElapsedSecond) {
            wrapper._lastElapsedSecond = elapsedSecond;
            onTimeUpdate(currentTime);
            // Update elapsed display
            const elapsedEl = plateEl.querySelector(".audio-elapsed");
            if (elapsedEl)
              elapsedEl.textContent = formatElapsedTime(currentTime);
          }

          // Clip end enforcement
          if (wrapper.clipEnd && currentTime >= wrapper.clipEnd) {
            if (wrapper.loop) {
              ws.setTime(wrapper.clipStart || 0);
            } else {
              ws.pause();
              applyAudioClipEndDim(plateEl);
              onEnded();
            }
          }
        });

        ws.on("play", () => {
          onPlay();
          // Remove end-of-playback dim if replaying
          removeAudioClipEndDim(plateEl);
          // Update play/pause button glyph
          const playBtn = plateEl.querySelector(".audio-btn-play");
          if (playBtn) {
            playBtn.innerHTML = _svg("pause", 22);
            playBtn.setAttribute("aria-label", "Pause");
          }
          // Hide play overlay on successful play
          const overlay = plateEl.querySelector(".audio-play-overlay");
          if (overlay) overlay.style.display = "none";
        });

        ws.on("pause", () => {
          // Update play/pause button glyph
          const playBtn = plateEl.querySelector(".audio-btn-play");
          if (playBtn) {
            playBtn.innerHTML = _svg("play", 22);
            playBtn.setAttribute("aria-label", "Play");
          }
        });

        // Non-clip audio end (dim for non-looping)
        ws.on("finish", () => {
          if (!wrapper.clipEnd) {
            applyAudioClipEndDim(plateEl);
            onEnded();
          }
        });

        // Audio load error — inject .telar-alert notification
        ws.on("error", (err) => {
          console.error("audio-card: WaveSurfer error", err);
          _injectAudioError(plateEl);
          onError(err);
        });

        // Elapsed time display
        let elapsedEl = plateEl.querySelector(".audio-elapsed");
        if (!elapsedEl) {
          elapsedEl = document.createElement("div");
          elapsedEl.className = "audio-elapsed";
          elapsedEl.setAttribute("aria-live", "polite");
          elapsedEl.textContent = "0:00";
          elapsedEl.style.cssText =
            "position:absolute;font-size:0.8rem;color:rgba(0,0,0,0.7);background:rgba(255,255,255,0.6);backdrop-filter:blur(4px);border-radius:20px;padding:0.4rem 0.85rem;pointer-events:none;right:16px;bottom:calc(25% - 48px);z-index:1;";
          plateEl.appendChild(elapsedEl);
        }

        // Audio controls pill
        if (!plateEl.querySelector(".audio-controls")) {
          const controlsWrapper = document.createElement("div");
          controlsWrapper.innerHTML = buildAudioControlsHTML();
          const controlsEl = controlsWrapper.firstElementChild;
          plateEl.appendChild(controlsEl);

          // Wire play/pause button
          const playBtn = controlsEl.querySelector(".audio-btn-play");
          if (playBtn) {
            playBtn.addEventListener("click", () => {
              state.hasUserInteracted = true;
              ws.playPause();
            });
          }

          // Wire restart button — seeks to clipStart or 0
          const restartBtn = controlsEl.querySelector(".audio-btn-restart");
          if (restartBtn) {
            restartBtn.addEventListener("click", () => {
              ws.setTime(wrapper.clipStart || 0);
              ws.play();
              removeAudioClipEndDim(plateEl);
            });
          }

          // Wire mute button
          const muteBtn = controlsEl.querySelector(".audio-btn-mute");
          if (muteBtn) {
            muteBtn.addEventListener("click", () => {
              const nowMuted = !ws.getMuted();
              ws.setMuted(nowMuted);
              if (nowMuted) {
                muteBtn.innerHTML = _svg("volume-x", 20);
                muteBtn.setAttribute("aria-label", "Unmute audio");
              } else {
                muteBtn.innerHTML = _svg("volume-2", 20);
                muteBtn.setAttribute("aria-label", "Mute audio");
              }
            });
          }
        }

        // Play overlay for autoplay-blocked state
        if (!plateEl.querySelector(".audio-play-overlay")) {
          const overlayEl = document.createElement("div");
          overlayEl.className = "audio-play-overlay";
          overlayEl.style.cssText =
            "position:absolute;inset:0;display:none;align-items:center;justify-content:center;z-index:1;";
          // Dynamic aria-label using object alt_text/title
          const _aObjectsData = window.objectsData || [];
          const _aObj = _aObjectsData.find(o => o.object_id === plateEl?.dataset?.object) || {};
          const _aAlt = _aObj.alt_text || _aObj.title || 'audio';
          const overlayBtn = document.createElement("button");
          overlayBtn.setAttribute("aria-label", `Play ${_aAlt}`);
          overlayBtn.type = "button";
          overlayBtn.innerHTML = _svg("play", 36);
          overlayBtn.style.cssText =
            "width:80px;height:80px;border-radius:50%;background:rgba(255,255,255,0.9);border:none;cursor:pointer;box-shadow:0 2px 12px rgba(0,0,0,0.2);display:flex;align-items:center;justify-content:center;color:#333;";
          overlayEl.appendChild(overlayBtn);
          plateEl.appendChild(overlayEl);

          // Overlay click: set hasUserInteracted, resume AudioContext and play
          overlayBtn.addEventListener("click", () => {
            state.hasUserInteracted = true; // unlock all subsequent media
            const ctx = getSharedAudioContext();
            if (ctx.state === "suspended") {
              ctx.resume().then(() => ws.play());
            } else {
              ws.play();
            }
            overlayEl.style.display = "none";
          });
        }

        // Clip end dim overlay
        if (!plateEl.querySelector(".audio-clip-end-overlay")) {
          const dimEl = document.createElement("div");
          dimEl.className = "audio-clip-end-overlay";
          dimEl.style.cssText =
            "position:absolute;inset:0;background:rgba(0,0,0,0.25);opacity:0;transition:opacity 300ms ease-in;pointer-events:none;";
          plateEl.appendChild(dimEl);
        }
      });
    })
    .catch((err) => {
      console.error("audio-card: failed to load WaveSurfer API", err);
      _injectAudioError(plateEl);
      onError(err);
    });

  return wrapper;
}

/**
 * Activate an audio card plate: reveal it and attempt autoplay.
 *
 * @param {HTMLElement} plateEl - The audio plate element
 * @param {number} sceneIndex - Scene index (for logging)
 */
export function activateAudioCard(plateEl, sceneIndex) {
  plateEl.style.transform = "translateY(0)";
  plateEl.classList.add("is-active");

  const wrapper = _getAudioWrapperForPlate(plateEl);
  if (!wrapper || !wrapper.ws) return;

  // Re-render waveform to match current viewport (Pitfall 4)
  try {
    wrapper.ws.setOptions({ height: Math.round(window.innerHeight * 0.35) });
  } catch (e) {
    // ws may still be initialising — ignore
  }

  // Unified autoplay policy
  // Mobile and embed: always manual play with overlay shown
  if (state.isMobileViewport || wrapper.isEmbed) {
    _showPlayOverlay(plateEl);
    return;
  }

  // Desktop (non-embed): attempt autoplay — if blocked, overlay fires via catch
  try {
    const ctx = getSharedAudioContext();
    if (ctx.state === "suspended") {
      ctx.resume().catch(() => {});
    }
    wrapper.ws.play().catch((err) => {
      if (err && err.name === "NotAllowedError") {
        _showPlayOverlay(plateEl);
        wrapper.isAutoplayBlocked = true;
      }
    });
  } catch (err) {
    if (err && err.name === "NotAllowedError") {
      _showPlayOverlay(plateEl);
    }
  }
}

/**
 * Deactivate an audio card plate: pause with crossfade and remove active class.
 *
 * Does NOT touch transform — caller decides positioning (same as video-card.js).
 *
 * @param {HTMLElement} plateEl - The audio plate element
 * @param {number} [fadeMs=300] - Crossfade duration in milliseconds */
export function deactivateAudioCard(plateEl, fadeMs = 300) {
  plateEl.classList.remove("is-active");

  const wrapper = _getAudioWrapperForPlate(plateEl);
  if (!wrapper || !wrapper.ws) return;

  // Crossfade out: step volume from current to 0 over fadeMs
  const steps = Math.ceil(fadeMs / 50);
  let step = 0;
  const startVolume = wrapper.ws.getVolume ? wrapper.ws.getVolume() : 1;

  const timer = setInterval(() => {
    step++;
    const newVolume = startVolume * (1 - step / steps);
    try {
      wrapper.ws.setVolume(Math.max(0, newVolume));
    } catch (e) {
      clearInterval(timer);
      return;
    }
    if (step >= steps) {
      clearInterval(timer);
      try {
        wrapper.ws.pause();
        wrapper.ws.setVolume(1); // Reset for next activation
      } catch (e) {
        // ws may have been destroyed
      }
    }
  }, 50);
}

/**
 * Destroy a WaveSurfer player wrapper, releasing its resources.
 *
 * @param {Object} wrapper - Player wrapper returned by createAudioPlayer
 */
export function destroyAudioPlayer(wrapper) {
  if (!wrapper) return;

  try {
    if (wrapper.ws) {
      wrapper.ws.destroy();
    }
  } catch (e) {
    console.warn("destroyAudioPlayer: error during destroy", e);
  }

  // Remove from pool
  const idx = _audioPlayers.indexOf(wrapper);
  if (idx !== -1) _audioPlayers.splice(idx, 1);

  // Clean up DOM elements injected by this module
  const plateEl = wrapper.element;
  if (plateEl) {
    [
      ".waveform-container",
      ".audio-controls",
      ".audio-elapsed",
      ".audio-play-overlay",
      ".audio-clip-end-overlay",
      ".telar-alert",
    ].forEach((sel) => {
      const el = plateEl.querySelector(sel);
      if (el) el.remove();
    });
  }
}

/**
 * Update clip parameters for an existing audio player and seek to new clip start.
 *
 * Parallel to video-card.js updateVideoClip.
 *
 * @param {HTMLElement} plateEl
 * @param {number} clipStart
 * @param {number} clipEnd
 * @param {boolean} loop
 */
export function updateAudioClip(plateEl, clipStart, clipEnd, loop) {
  const wrapper = _getAudioWrapperForPlate(plateEl);
  if (!wrapper) return;

  // No-op if same clip parameters
  if (
    wrapper.clipStart === clipStart &&
    wrapper.clipEnd === clipEnd &&
    wrapper.loop === loop
  ) {
    return;
  }

  wrapper.clipStart = clipStart;
  wrapper.clipEnd = clipEnd;
  wrapper.loop = loop;

  plateEl.dataset.clipStart = String(clipStart);
  plateEl.dataset.clipEnd = String(clipEnd);
  plateEl.dataset.loop = String(loop);

  // Remove previous clip-end dim
  removeAudioClipEndDim(plateEl);

  // Remove and re-add clip region
  if (wrapper._regionsPlugin) {
    try {
      wrapper._regionsPlugin.clearRegions();
      if (clipStart !== undefined && clipEnd && wrapper._colors) {
        wrapper._regionsPlugin.addRegion({
          start: clipStart,
          end: clipEnd,
          color: wrapper._colors.clipRegionColor,
          drag: false,
          resize: false,
        });
      }
    } catch (e) {
      // Plugin may not be ready
    }
  }

  // Seek to new clip start
  if (wrapper.ws) {
    try {
      wrapper.ws.setTime(clipStart || 0);
    } catch (e) {
      // ws not ready yet
    }
  }
}

/**
 * Show the clip-end dim overlay.
 * Mirrors video-card.js applyClipEndDim.
 *
 * @param {HTMLElement} plateEl
 */
export function applyAudioClipEndDim(plateEl) {
  let overlay = plateEl.querySelector(".audio-clip-end-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.className = "audio-clip-end-overlay";
    overlay.style.cssText =
      "position:absolute;inset:0;background:rgba(0,0,0,0.25);opacity:0;transition:opacity 300ms ease-in;pointer-events:none;";
    plateEl.appendChild(overlay);
  }
  // Force reflow so CSS transition fires
  void overlay.offsetHeight;
  overlay.style.opacity = "1";
}

/**
 * Remove the clip-end dim overlay.
 * Mirrors video-card.js removeClipEndDim.
 *
 * @param {HTMLElement} plateEl
 */
export function removeAudioClipEndDim(plateEl) {
  const overlay = plateEl.querySelector(".audio-clip-end-overlay");
  if (overlay) overlay.style.opacity = "0";
}

// ── Private helpers ───────────────────────────────────────────────────────────

/**
 * Enforce the audio player pool size limit.
 * Evicts the farthest player by scene distance when cap is exceeded.
 *
 * @param {number} currentScene
 */
function _enforceAudioPoolLimit(currentScene) {
  while (_audioPlayers.length > MAX_AUDIO_PLAYERS) {
    let farthestIdx = 0;
    let maxDist = -1;
    for (let i = 0; i < _audioPlayers.length; i++) {
      const dist = Math.abs(_audioPlayers[i].sceneIndex - currentScene);
      if (dist > maxDist) {
        maxDist = dist;
        farthestIdx = i;
      }
    }
    const evicted = _audioPlayers.splice(farthestIdx, 1)[0];
    _evictAudioPlayer(evicted);
  }
}

/**
 * Evict a player without removing it from the pool array
 * (splice in _enforceAudioPoolLimit already handles removal).
 */
function _evictAudioPlayer(wrapper) {
  try {
    if (wrapper.ws) {
      wrapper.ws.destroy();
      wrapper.ws = null;
    }
  } catch (e) {
    console.warn("_evictAudioPlayer: error during evict", e);
  }
}

/**
 * Find the audio player wrapper for a given plate element.
 *
 * @param {HTMLElement} plateEl
 * @returns {Object|null}
 */
function _getAudioWrapperForPlate(plateEl) {
  return _audioPlayers.find((w) => w.element === plateEl) || null;
}

/**
 * Show the play overlay on the plate (autoplay blocked or embed context).
 *
 * @param {HTMLElement} plateEl
 */
function _showPlayOverlay(plateEl) {
  const overlay = plateEl.querySelector(".audio-play-overlay");
  if (overlay) overlay.style.display = "flex";
}

/**
 * Inject a .telar-alert error notification into the audio plate.
 * Matches the Bootstrap alert pattern from _includes/iiif-url-warning.html.
 *
 * @param {HTMLElement} plateEl
 */
function _injectAudioError(plateEl) {
  // Don't inject if already present
  if (plateEl.querySelector(".telar-alert")) return;

  const alertEl = document.createElement("div");
  alertEl.className = "alert alert-warning telar-alert";
  alertEl.setAttribute("role", "alert");
  alertEl.innerHTML = `<strong>Audio unavailable</strong>
<p>This audio file could not be loaded. Continue scrolling to read the story.</p>`;
  plateEl.appendChild(alertEl);
}

// ── Resize handler ────────────────────────────────────────────────────────────

let _audioResizeTimer = null;

window.addEventListener("resize", () => {
  if (_audioResizeTimer) clearTimeout(_audioResizeTimer);
  _audioResizeTimer = setTimeout(() => {
    const newHeight = Math.round(window.innerHeight * 0.5);
    for (const wrapper of _audioPlayers) {
      if (
        wrapper.element &&
        wrapper.element.classList.contains("is-active") &&
        wrapper.ws
      ) {
        try {
          wrapper.ws.setOptions({ height: newHeight });
        } catch (e) {
          // Ignore resize errors
        }
      }
    }
  }, 100);
});
