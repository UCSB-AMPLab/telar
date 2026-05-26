/**
 * Telar Story – IIIF Manifest Parser
 *
 * Four pure synchronous functions that extract the canonical page list
 * from a IIIF Presentation API manifest, supporting both v2 and v3.
 * extractAllPages tries v3 first and falls through to v2; extractV3Pages
 * and extractV2Pages walk the version-specific shapes and return
 * { tileSource } records; deriveInfoJsonFromImageUrl rebuilds an
 * info.json URL from a versioned IIIF Image API URL when a manifest
 * publishes only the raw image URL.
 *
 * The parser is the data layer the wrapper class sits on
 * top of. It is pure — no DOM, no fetch, no module state — so it can
 * be tested with fixtures and reused by any caller. try/catch blocks
 * around each version-specific walker let malformed manifests degrade
 * to partial results rather than throw, which keeps the wrapper's
 * error surface predictable.
 *
 * Ported from the Telar Compositor (TypeScript types stripped; behaviour identical).
 *
 * @version v1.4.0
 */

/**
 * @typedef {{ tileSource: string }} PageInfo
 */

/**
 * Extract page tile sources from a IIIF manifest (v2 or v3).
 * Tries v3 first; falls through to v2; returns [] on garbage input.
 *
 * @param {Record<string, unknown>} manifest
 * @returns {PageInfo[]}
 */
export function extractAllPages(manifest) {
  const v3Pages = extractV3Pages(manifest);
  if (v3Pages.length > 0) return v3Pages;

  const v2Pages = extractV2Pages(manifest);
  if (v2Pages.length > 0) return v2Pages;

  return [];
}

/**
 * Extract pages from a IIIF Presentation API v3 manifest.
 * Walks manifest.items[*].items[0].items[0].body and prefers
 * body.service[0].id; falls back to deriving info.json from body.id
 * when body is a typed Image; final fallback is the raw image URL.
 *
 * @param {Record<string, unknown>} manifest
 * @returns {PageInfo[]}
 */
export function extractV3Pages(manifest) {
  const pages = [];
  try {
    const items = manifest.items;
    if (!items) return pages;

    for (const canvas of items) {
      const annoPages = canvas.items;
      if (!annoPages?.[0]) continue;
      const annos = annoPages[0].items;
      if (!annos?.[0]) continue;
      const body = annos[0].body;
      if (!body) continue;

      // Option 1: body.service array with an Image API endpoint
      const service = body.service;
      if (service?.[0]?.id) {
        pages.push({ tileSource: service[0].id + '/info.json' });
        continue;
      }

      // Option 2: body.id is an Image API URL — derive info.json from it
      if (body.id && typeof body.id === 'string' && body.type === 'Image') {
        const infoUrl = deriveInfoJsonFromImageUrl(body.id);
        if (infoUrl) {
          pages.push({ tileSource: infoUrl });
          continue;
        }
        // Last resort: use the image URL directly
        pages.push({ tileSource: body.id });
      }
    }
  } catch { /* fall through */ }
  return pages;
}

/**
 * Extract pages from a IIIF Presentation API v2 manifest.
 * Walks manifest.sequences[0].canvases[*].images[0].resource and prefers
 * service['@id']; falls back to resource['@id'] as a raw image URL.
 *
 * @param {Record<string, unknown>} manifest
 * @returns {PageInfo[]}
 */
export function extractV2Pages(manifest) {
  const pages = [];
  try {
    const sequences = manifest.sequences;
    if (!sequences?.[0]) return pages;
    const canvases = sequences[0].canvases;
    if (!canvases) return pages;

    for (const canvas of canvases) {
      const images = canvas.images;
      if (!images?.[0]) continue;
      const resource = images[0].resource;
      if (!resource) continue;

      const service = resource.service;
      if (service?.['@id']) {
        pages.push({ tileSource: service['@id'] + '/info.json' });
        continue;
      }

      // Fallback: resource @id
      if (resource['@id'] && typeof resource['@id'] === 'string') {
        pages.push({ tileSource: resource['@id'] });
      }
    }
  } catch { /* fall through */ }
  return pages;
}

/**
 * Derive an info.json URL from a versioned IIIF Image API URL.
 * E.g. ".../iiif/3/{id}/full/max/0/default.jpg" → ".../iiif/3/{id}/info.json".
 * Returns null for non-matching URLs (including unversioned hosts such
 * as older Loris instances — those fall back to the raw image URL in
 * extractV3Pages).
 *
 * @param {string} url
 * @returns {string | null}
 */
export function deriveInfoJsonFromImageUrl(url) {
  const match = url.match(/^(.+\/iiif\/\d+\/[^/]+)\/[^/]+\/[^/]+\/[^/]+\/[^/]+$/);
  if (match) return match[1] + '/info.json';
  return null;
}
