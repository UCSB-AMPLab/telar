/**
 * Telar — video embed resolution for object pages.
 *
 * A collection object whose media type is Video points at a hosted video —
 * YouTube, Vimeo, or a shared Google Drive file — and the object page shows
 * it inside the provider's player iframe. This module owns the URL work:
 * recognising the provider, extracting its video ID, and building both the
 * embed URL and the player iframe markup that _layouts/object.html injects
 * into the viewer area. The layout keeps only the wiring around the result
 * (author-facing embed-URL display, the Drive load-failure fallback, and the
 * clip-picker player APIs).
 *
 * resolveVideoEmbed(sourceUrl, frameTitle) returns
 *   { provider, embedUrl, iframeHtml }
 * or null when the URL matches no supported provider (the caller leaves the
 * viewer area untouched in that case). `provider` is 'youtube' | 'vimeo' |
 * 'drive'. `embedUrl` doubles as the iframe src and the author-visible embed
 * URL; for Drive it is the /preview URL. `frameTitle` MUST arrive already
 * escaped for an HTML attribute context (the layout passes a Liquid
 * `escape`d title) — it is interpolated into the markup as-is.
 *
 * Provider detection is by hostname substring, checked in this order:
 * youtube.com/youtu.be, vimeo.com, drive.google.com. A matching provider
 * whose ID pattern fails still yields an iframe (with an empty ID), so the
 * provider's own player surfaces the error rather than the page silently
 * showing nothing.
 *
 * Loaded as a classic script and published on window.telarVideoEmbed —
 * object.html mixes classic and module scripts, so no module system can be
 * assumed.
 *
 * @version v1.6.0
 */

(function () {
  'use strict';

  /**
   * Build the player iframe markup. All providers share the id (the clip
   * pickers look up #video-player-iframe), sizing style, and title; the
   * allow list and allowfullscreen flag are per-provider.
   *
   * @param {string} src - Embed URL for the iframe src attribute
   * @param {string} allow - Value for the allow attribute
   * @param {boolean} allowFullscreen - Whether to emit the allowfullscreen attribute
   * @param {string} frameTitle - Attribute-escaped iframe title
   * @returns {string} iframe HTML
   */
  function buildIframeHtml(src, allow, allowFullscreen, frameTitle) {
    return '<iframe id="video-player-iframe" src="' + src + '" ' +
      'style="width:100%;aspect-ratio:16/9;border:none;" ' +
      'allow="' + allow + '" ' +
      (allowFullscreen ? 'allowfullscreen ' : '') +
      'title="' + frameTitle + '"></iframe>';
  }

  /**
   * Resolve a video source URL to its provider embed.
   *
   * @param {string} sourceUrl - The object's source_url (raw, unescaped)
   * @param {string} frameTitle - Attribute-escaped title for the iframe
   * @returns {?{provider: string, embedUrl: string, iframeHtml: string}}
   */
  function resolveVideoEmbed(sourceUrl, frameTitle) {
    if (!sourceUrl) return null;

    if (sourceUrl.indexOf('youtube.com') !== -1 || sourceUrl.indexOf('youtu.be') !== -1) {
      let videoId = '';
      const ytMatch = sourceUrl.match(/(?:youtube\.com\/(?:watch\?v=|embed\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
      if (ytMatch) videoId = ytMatch[1];
      const embedUrl = 'https://www.youtube.com/embed/' + videoId + '?enablejsapi=1';
      return {
        provider: 'youtube',
        embedUrl: embedUrl,
        iframeHtml: buildIframeHtml(
          embedUrl,
          'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture',
          true,
          frameTitle
        ),
      };
    }

    if (sourceUrl.indexOf('vimeo.com') !== -1) {
      let vimeoId = '';
      const vmMatch = sourceUrl.match(/vimeo\.com\/(\d+)/);
      if (vmMatch) vimeoId = vmMatch[1];
      const embedUrl = 'https://player.vimeo.com/video/' + vimeoId;
      return {
        provider: 'vimeo',
        embedUrl: embedUrl,
        iframeHtml: buildIframeHtml(embedUrl, 'autoplay; fullscreen; picture-in-picture', true, frameTitle),
      };
    }

    if (sourceUrl.indexOf('drive.google.com') !== -1) {
      let fileId = '';
      const gdMatch = sourceUrl.match(/\/d\/([a-zA-Z0-9_-]+)/);
      if (gdMatch) fileId = gdMatch[1];
      const embedUrl = 'https://drive.google.com/file/d/' + fileId + '/preview';
      return {
        provider: 'drive',
        embedUrl: embedUrl,
        iframeHtml: buildIframeHtml(embedUrl, 'autoplay', false, frameTitle),
      };
    }

    return null;
  }

  window.telarVideoEmbed = {
    resolveVideoEmbed: resolveVideoEmbed,
  };
})();
