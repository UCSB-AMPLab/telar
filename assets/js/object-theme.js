/**
 * Telar — object-page theme helpers.
 *
 * Object pages paint two kinds of chrome from the site's theme colours at
 * runtime, and this file is the single home for that colour maths, shared by
 * the per-media-type inline scripts in _layouts/object.html.
 *
 * Panel contrast — the collapsible author panels (the image coordinate picker
 * and the video/audio clip pickers) need light text on dark theme colours and
 * dark text on light ones. applyPanelContrastClass() reads --color-button-bg,
 * decodes the sRGB hex into linear light, computes WCAG 2.x relative
 * luminance, and tags the panel `coord-light` or `coord-dark`. The 0.179
 * threshold is the luminance at which black text starts to out-contrast white
 * text under the WCAG contrast formula.
 *
 * Waveform palette — deriveThemeColors() turns the theme's accent and button
 * text colours into the audio waveform palette. It MUST stay in agreement
 * with deriveThemeColors in assets/js/telar-story/audio-card.js (see the
 * matching note there): story pages get theirs from the telar-story.js
 * bundle, which object pages deliberately do not load, so the derivation
 * exists in both files by design. If you change one, change the other.
 *
 * Loaded as a classic script (object.html mixes classic and module scripts,
 * so no module system can be assumed): everything is wrapped in an IIFE and
 * published on window.telarObjectTheme, reachable from both kinds of script.
 *
 * @version v1.6.0
 */

(function () {
  'use strict';

  /**
   * WCAG 2.x relative luminance of a hex colour.
   *
   * @param {string} hexColour - Hex colour, with or without '#', e.g. '#883C36'
   * @returns {number} Relative luminance in 0–1
   */
  function relativeLuminance(hexColour) {
    const hex = hexColour.replace('#', '');
    const r = parseInt(hex.substring(0, 2), 16) / 255;
    const g = parseInt(hex.substring(2, 4), 16) / 255;
    const b = parseInt(hex.substring(4, 6), 16) / 255;
    // sRGB gamma decode, then the WCAG luminance weights
    const linear = function (c) {
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
  }

  /**
   * Tag an author panel `coord-light` or `coord-dark` according to the
   * luminance of the theme's button background (--color-button-bg).
   * No-op when the panel is absent or the CSS variable is unset, so call
   * sites can pass a bare querySelector result.
   *
   * @param {Element|null} panel - The .coordinate-panel / .clip-panel element
   */
  function applyPanelContrastClass(panel) {
    if (!panel) return;
    const bg = getComputedStyle(document.documentElement).getPropertyValue('--color-button-bg').trim();
    if (!bg) return;
    panel.classList.add(relativeLuminance(bg) > 0.179 ? 'coord-light' : 'coord-dark');
  }

  /**
   * Derive waveform theme colours from CSS theme values.
   *
   * MUST agree with deriveThemeColors in assets/js/telar-story/audio-card.js
   * — same inputs, same outputs. Object pages cannot import the bundled story
   * module, so the two copies are kept in step by hand.
   *
   * @param {string} accentHex - CSS hex colour for --color-link, e.g. '#883C36'
   * @param {string} [barHex='#ffffff'] - CSS hex colour for --color-button-text
   * @returns {Object} Theme colour set
   */
  function deriveThemeColors(accentHex, barHex) {
    if (barHex === undefined) barHex = '#ffffff';

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
      unplayedColor: 'rgb(' + upR + ', ' + upG + ', ' + upB + ')', // unplayed bars: opaque blended tint
      backgroundColor: 'rgb(' + bgR + ', ' + bgG + ', ' + bgB + ')',
      patternColor: 'rgba(255, 255, 255, 0.12)',
      clipRegionColor: 'rgba(255, 255, 255, 0.08)', // subtle clip region highlight
    };
  }

  window.telarObjectTheme = {
    relativeLuminance: relativeLuminance,
    applyPanelContrastClass: applyPanelContrastClass,
    deriveThemeColors: deriveThemeColors,
  };
})();
