/**
 * Telar — object-page theme helpers.
 *
 * Object pages paint the audio waveform from the site's theme colours at
 * runtime, and this file is the home for that colour maths, loaded by
 * _layouts/object.html on audio pages only.
 *
 * Waveform palette — deriveThemeColors() turns the theme's accent and button
 * text colours into the audio waveform palette. It agrees with
 * deriveThemeColors in assets/js/telar-story/audio-card.js (see the
 * matching note there): story pages get theirs from the telar-story.js
 * bundle, which object pages deliberately do not load, so the derivation
 * exists in both files by design. A change to one is a change to the other.
 *
 * Loaded as a classic script before the audio bundle: everything is wrapped
 * in an IIFE and published on window.telarObjectTheme, which audio-object.js
 * reads.
 *
 * @version v1.8.0
 */

(function () {
  'use strict';

  /**
   * Derive waveform theme colours from CSS theme values.
   *
   * Agrees with deriveThemeColors in assets/js/telar-story/audio-card.js
   * — same inputs, same outputs. Object pages cannot import the bundled story
   * module, so the two copies are kept in step by hand.
   *
   * barHex is --color-button-text, not the derived --color-on-button: the bars
   * are drawn on the accent darkened to 70%, not on the button background, so
   * the colour derived to be legible on the button ground does not apply here.
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
    deriveThemeColors: deriveThemeColors,
  };
})();
