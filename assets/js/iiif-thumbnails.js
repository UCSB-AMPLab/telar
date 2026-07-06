/**
 * Telar — IIIF thumbnail resolution.
 *
 * The home page (story cards and featured objects) and the objects index all need the
 * same thing: given an object's IIIF source, find the best image URL for a card-sized
 * thumbnail. This module holds that resolution logic in one place; each layout keeps
 * only its own DOM wiring (which placeholder to swap, what alt text and classes to use,
 * how to surface errors).
 *
 * Three resolution routes, matching the three ways a Telar object can carry images:
 *
 * - `upgradeIIIFThumbnailUrl(url)` — an explicit thumbnail URL that already follows the
 *   IIIF Image API `/full/{size}/0/default.{ext}` pattern is rewritten to request
 *   `!600,600` for a sharper rendition. The size segment sometimes arrives mangled by
 *   spreadsheet escaping (Rumsey's `\!96,96`, or double slashes left by stripped
 *   backslashes), so the pattern tolerates those. Callers should keep the original URL
 *   as an `onerror` fallback: a Level 0 server only serves the sizes it pre-generated,
 *   and the upgraded request may 404 there.
 *
 * - `resolveManifestThumbnail(manifestUrl, sizeParam)` — fetches a IIIF Presentation
 *   manifest (2.1 `sequences[0].canvases` or 3.0 `items` traversal), extracts the first
 *   canvas's image service and full-image URL, and resolves to a thumbnail URL. A
 *   Level 1+ service gets an arbitrary-size request (`sizeParam`, default `!400,400` —
 *   the home page's featured grid passes `!200,200` for its smaller cards). A Level 0
 *   service can't scale on demand, so its `info.json` is fetched and the largest
 *   pre-generated size used. With no usable service the canvas's full image URL is the
 *   fallback. The promise resolves `null` when a Level 0 lookup dead-ends without a
 *   fallback (a silent outcome — callers show nothing), and rejects with an error marked
 *   `noImage: true` when the manifest yields no image at all — callers distinguish that
 *   from a network failure (the objects index shows "no image" rather than an error).
 *
 * - `resolveInfoJsonThumbnail(infoUrl, minWidth)` — for self-hosted objects with local
 *   tiles: fetches `info.json` and picks the smallest pre-generated size at least
 *   `minWidth` (default 400) wide via `pickThumbnailSize`, resolving `null` when the
 *   sizes array is empty.
 *
 * Classic script, not a module — the consuming layouts use plain `<script>` tags, so
 * everything is published on the single `window.TelarIIIF` namespace.
 *
 * @version v1.6.0
 */

(function() {
  'use strict';

  /**
   * Pick a thumbnail size from the IIIF sizes array.
   * Returns the smallest size >= minWidth, or the largest available.
   */
  function pickThumbnailSize(sizes, minWidth) {
    if (!sizes || sizes.length === 0) return null;
    minWidth = minWidth || 400;
    var sorted = sizes.slice().sort(function(a, b) { return a.width - b.width; });
    for (var i = 0; i < sorted.length; i++) {
      if (sorted[i].width >= minWidth) return sorted[i];
    }
    return sorted[sorted.length - 1];
  }

  /**
   * Upgrade IIIF Image API thumbnail URLs to a larger size.
   * Detects URLs with /full/{size}/0/default.{ext} pattern and replaces
   * the size segment with !600,600 for sharper thumbnails.
   */
  function upgradeIIIFThumbnailUrl(url) {
    // Match IIIF Image API pattern: .../full/{size}/0/default.{ext}
    // The size segment may contain backslash-escaped ! (e.g. Rumsey \!96,96)
    // or double slashes from stripped backslashes. Handle all variants.
    var match = url.match(/^(.*\/full\/)[\\\/]*([^/]+)(\/0\/default\.\w+)$/);
    if (match) {
      return match[1] + '!600,600' + match[3];
    }
    return url;
  }

  /**
   * Walk a IIIF Presentation manifest (2.1 or 3.0) to the first canvas's image.
   * Returns { imageServiceUrl, imageServiceProfile, fallbackImageUrl }, any of
   * which may be null.
   */
  function extractManifestImage(manifest) {
    var imageServiceUrl = null;
    var imageServiceProfile = null;
    var fallbackImageUrl = null;

    // IIIF Presentation API 2.1
    if (manifest.sequences && manifest.sequences[0] && manifest.sequences[0].canvases) {
      var firstCanvas = manifest.sequences[0].canvases[0];
      if (firstCanvas && firstCanvas.images && firstCanvas.images[0]) {
        var resource = firstCanvas.images[0].resource;

        // Try to get image service for resizing
        if (resource.service) {
          var service = Array.isArray(resource.service) ? resource.service[0] : resource.service;
          imageServiceUrl = service['@id'] || service.id;
          imageServiceProfile = service.profile;
        }

        // Fallback to full image URL
        if (!imageServiceUrl && resource['@id']) {
          fallbackImageUrl = resource['@id'];
        }
      }
    }
    // IIIF Presentation API 3.0
    else if (manifest.items && manifest.items[0]) {
      var v3Canvas = manifest.items[0];
      if (v3Canvas.items && v3Canvas.items[0] && v3Canvas.items[0].items) {
        var annotationBody = v3Canvas.items[0].items[0].body;

        // Try to get image service for resizing
        if (annotationBody.service && annotationBody.service.length > 0) {
          imageServiceUrl = annotationBody.service[0].id || annotationBody.service[0]['@id'];
          imageServiceProfile = annotationBody.service[0].profile;
        }

        // Fallback to full image URL
        if (!imageServiceUrl && annotationBody.id) {
          fallbackImageUrl = annotationBody.id;
        }
      }
    }

    return {
      imageServiceUrl: imageServiceUrl,
      imageServiceProfile: imageServiceProfile,
      fallbackImageUrl: fallbackImageUrl
    };
  }

  /**
   * A Level 0 service serves only pre-generated sizes — no arbitrary scaling.
   */
  function isLevel0Profile(profile) {
    return !!(profile && (
      profile === 'level0' ||
      profile === 'http://iiif.io/api/image/2/level0.json'
    ));
  }

  /**
   * Resolve a IIIF Presentation manifest URL to a thumbnail image URL.
   *
   * Resolves to a URL string, or null when a Level 0 lookup fails without a
   * fallback image (a silent outcome for callers). Rejects on fetch/parse
   * failure, or — when the manifest contains no image at all — with an Error
   * carrying `noImage: true` so callers can tell the two apart.
   */
  function resolveManifestThumbnail(manifestUrl, sizeParam) {
    sizeParam = sizeParam || '!400,400';
    return fetch(manifestUrl)
      .then(function(response) { return response.json(); })
      .then(function(manifest) {
        var image = extractManifestImage(manifest);
        var imageServiceUrl = image.imageServiceUrl;
        var fallbackImageUrl = image.fallbackImageUrl;

        // Level 0: fetch info.json to get available sizes
        if (imageServiceUrl && isLevel0Profile(image.imageServiceProfile)) {
          imageServiceUrl = imageServiceUrl.replace(/\/$/, '');
          return fetch(imageServiceUrl + '/info.json')
            .then(function(r) { return r.json(); })
            .then(function(info) {
              var sizes = info.sizes || [];
              var largest = sizes.length > 0 ? sizes[sizes.length - 1] : null;
              return largest
                ? imageServiceUrl + '/full/' + largest.width + ',' + largest.height + '/0/default.jpg'
                : (fallbackImageUrl || null);
            })
            .catch(function() { return fallbackImageUrl || null; });
        }
        // Level 1+: request arbitrary size
        if (imageServiceUrl) {
          imageServiceUrl = imageServiceUrl.replace(/\/$/, '');
          return imageServiceUrl + '/full/' + sizeParam + '/0/default.jpg';
        }
        if (fallbackImageUrl) {
          return fallbackImageUrl;
        }
        var error = new Error('No image found in manifest');
        error.noImage = true;
        throw error;
      });
  }

  /**
   * Resolve a local IIIF info.json URL to a thumbnail image URL.
   * Resolves to a URL string, or null when no sizes are available.
   * Rejects on fetch/parse failure.
   */
  function resolveInfoJsonThumbnail(infoUrl, minWidth) {
    return fetch(infoUrl)
      .then(function(response) { return response.json(); })
      .then(function(info) {
        var thumbnailSize = pickThumbnailSize(info.sizes || [], minWidth);
        if (!thumbnailSize) return null;
        var baseUrl = info.id || info['@id'];
        return baseUrl + '/full/' + thumbnailSize.width + ',' + thumbnailSize.height + '/0/default.jpg';
      });
  }

  window.TelarIIIF = {
    pickThumbnailSize: pickThumbnailSize,
    upgradeIIIFThumbnailUrl: upgradeIIIFThumbnailUrl,
    extractManifestImage: extractManifestImage,
    isLevel0Profile: isLevel0Profile,
    resolveManifestThumbnail: resolveManifestThumbnail,
    resolveInfoJsonThumbnail: resolveInfoJsonThumbnail
  };
})();
