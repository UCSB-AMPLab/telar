/**
 * Telar — IIIF URL mismatch diagnostic.
 *
 * A self-diagnosing check for the most common reason locally hosted images fail
 * to appear: the address the site is being viewed at differs from the base URL
 * baked into its IIIF manifests when the tiles were generated. This module
 * decides whether to reveal the hidden alert banner defined in
 * `_includes/iiif-url-warning.html`.
 *
 * Two halves, deliberately separate. `findAffectedObjects` is the detection: it
 * reads the current origin and baseurl, fetches objects.json, keeps only the
 * objects that rely on local IIIF tiles (no external iiif_manifest), fetches
 * each one's manifest.json and compares the base URL in the manifest's own id
 * (trailing slashes normalised) against where the page is being served. It
 * returns what the banner would have to say, or null when there is nothing to
 * say. `renderWarning` is the other half and touches no network: given that
 * result it fills the banner in and shows it.
 *
 * Local vs production guidance — the fix differs by environment, so the banner
 * branches on whether the origin is localhost/127.0.0.1. Local development gets
 * a ready-to-run generate_iiif.py command targeting the current URL; production
 * gets the suggested url:/baseurl: _config.yml values (parsed from the live
 * address) plus the regenerate-and-push workflow. Detection failures fail
 * silently — the banner stays hidden rather than alarming the user over an
 * unrelated fetch error, and a manifest that cannot be read is skipped rather
 * than counted as a mismatch.
 *
 * The Liquid-dependent configuration arrives in the JSON block the include
 * writes, `#telar-iiif-warning-data`: the objects.json and IIIF manifest base
 * paths (`relative_url`s, so they carry the site's baseurl), plus the localized
 * singular/plural "affected images" strings from
 * `_data/languages/<telar_language>.yml`. If that block or any of its required
 * fields is missing, the check exits silently.
 *
 * The document, fetch and location are parameters with browser defaults so a
 * test can drive the check without stubbing globals.
 *
 * Bundled by esbuild into assets/js/iiif-url-warning.js; see assets/js/README.md.
 *
 * Version: v1.7.0
 */

/**
 * Read the include's data block. Null when the page does not carry the
 * banner, which is how a page without the include stays untouched.
 */
export function readWarningData(doc = document) {
  const block = doc.getElementById('telar-iiif-warning-data');
  if (!block) return null;
  try {
    return JSON.parse(block.textContent);
  } catch (err) {
    console.error('IIIF URL warning data block is not valid JSON:', err);
    return null;
  }
}

/** The site URL a page is served at: its origin plus the first path segment. */
export function siteUrlFromLocation(location) {
  const pathParts = location.pathname.split('/').filter(p => p);
  const baseurl = pathParts.length > 0 ? '/' + pathParts[0] : '';
  return location.origin + baseurl;
}

/** Local development, where the fix is to regenerate the tiles in place. */
export function isLocalDevOrigin(origin) {
  return origin.includes('localhost') || origin.includes('127.0.0.1');
}

/** The site a manifest was generated for: everything before its /iiif/ segment. */
export function manifestBaseFromId(manifestId) {
  return manifestId.split('/iiif/')[0];
}

/** Two addresses for the same site, a trailing slash being no difference. */
export function sameSite(siteUrl, manifestBase) {
  return siteUrl.replace(/\/$/, '') === manifestBase.replace(/\/$/, '');
}

/** The command that regenerates the tiles for an address. */
export function regenerationCommand(siteUrl) {
  return `python3 scripts/generate_iiif.py --base-url ${siteUrl}`;
}

/** The _config.yml values an address implies. */
export function configSuggestion(siteUrl) {
  const urlObj = new URL(siteUrl);
  const urlPart = `${urlObj.protocol}//${urlObj.host}`;
  const baseurlPart = urlObj.pathname || '';
  return `url: "${urlPart}" and baseurl: "${baseurlPart}"`;
}

/** An object relying on local tiles, so its manifest is ours to compare. */
function isLocalObject(obj) {
  return !obj.iiif_manifest || obj.iiif_manifest === '';
}

/**
 * The base URL one object's manifest was generated for, or null when the
 * manifest cannot be read — absent, unreachable, or not the shape expected.
 * A manifest nobody can read is not evidence of a mismatch.
 */
async function readManifestBase(config, objectId, fetch) {
  try {
    const manifestPath = `${config.iiifObjectsBase}/${objectId}/manifest.json`;
    const manifestResponse = await fetch(manifestPath);
    if (!manifestResponse.ok) return null;

    const manifest = await manifestResponse.json();
    return manifestBaseFromId(manifest.id);
  } catch (error) {
    console.log(`Could not check manifest for ${objectId}:`, error);
    return null;
  }
}

/**
 * Every local object whose manifest disagrees with `currentSiteUrl`, and the
 * base of the first readable local manifest, matching or not — with one
 * generator run behind them they all carry the same base. Objects whose
 * manifest cannot be read are skipped, not counted.
 */
async function collectAffected(config, localObjects, currentSiteUrl, fetch) {
  const affectedObjects = [];
  let manifestBaseUrl = null;

  for (const obj of localObjects) {
    const extractedBaseUrl = await readManifestBase(config, obj.object_id, fetch);
    if (extractedBaseUrl === null) continue;

    if (!manifestBaseUrl) manifestBaseUrl = extractedBaseUrl;

    if (!sameSite(currentSiteUrl, extractedBaseUrl)) {
      affectedObjects.push({ id: obj.object_id, title: obj.title || obj.object_id });
    }
  }

  return { affectedObjects, manifestBaseUrl };
}

/**
 * The objects whose manifests point somewhere other than this address, with
 * the context the banner needs. Null when there is nothing to show: the
 * objects list is unreadable, no object uses local tiles, every manifest
 * agrees with the address, or no manifest could be read at all.
 */
export async function findAffectedObjects(config, {
  fetch = (url) => globalThis.fetch(url),
  location = globalThis.location,
} = {}) {
  const currentSiteUrl = siteUrlFromLocation(location);
  const isLocalDev = isLocalDevOrigin(location.origin);

  try {
    const objectsResponse = await fetch(config.objectsUrl);
    if (!objectsResponse.ok) return null;

    const objects = await objectsResponse.json();
    const localObjects = objects.filter(isLocalObject);
    const { affectedObjects, manifestBaseUrl } =
      await collectAffected(config, localObjects, currentSiteUrl, fetch);

    if (affectedObjects.length === 0 || !manifestBaseUrl) return null;
    return { affectedObjects, manifestBaseUrl, currentSiteUrl, isLocalDev };
  } catch (error) {
    // Silently fail - don't show warning if we can't determine mismatch
    console.log('Could not check IIIF URL mismatch:', error);
    return null;
  }
}

/** The localized heading, its __COUNT__ placeholder filled in. */
function renderHeading(count, strings, doc) {
  const template = count === 1 ? strings.affectedImagesSingular : strings.affectedImagesPlural;
  doc.getElementById('affected-images-heading').textContent = template.replace('__COUNT__', count);
}

/**
 * The list of affected objects, replacing whatever the list holds. Each row is
 * built from DOM nodes so an object title containing markup renders as text,
 * not as HTML.
 */
function renderAffectedList(affectedObjects, doc) {
  const affectedList = doc.getElementById('affected-images');
  affectedList.replaceChildren();
  affectedObjects.forEach(obj => {
    const li = doc.createElement('li');
    const strong = doc.createElement('strong');
    strong.textContent = obj.title;
    li.appendChild(strong);
    li.appendChild(doc.createTextNode(` (${obj.id})`));
    affectedList.appendChild(li);
  });
}

/** Whichever of the two hidden instruction blocks fits this environment. */
function renderFixInstructions(currentSiteUrl, isLocalDev, doc) {
  if (isLocalDev) {
    doc.getElementById('local-fix-instructions').style.display = 'block';
    doc.getElementById('local-command').textContent = regenerationCommand(currentSiteUrl);
    return;
  }

  doc.getElementById('production-fix-instructions').style.display = 'block';
  doc.getElementById('production-current-url').textContent = currentSiteUrl;
  doc.getElementById('production-config-suggestion').textContent = configSuggestion(currentSiteUrl);
  doc.getElementById('production-local-command').textContent = regenerationCommand(currentSiteUrl);
}

/** Fill the banner in from a detection result and reveal it. */
export function renderWarning(result, strings, doc = document) {
  doc.getElementById('current-url').textContent = result.currentSiteUrl;
  doc.getElementById('manifest-url').textContent = result.manifestBaseUrl;
  renderHeading(result.affectedObjects.length, strings, doc);
  renderAffectedList(result.affectedObjects, doc);
  renderFixInstructions(result.currentSiteUrl, result.isLocalDev, doc);
  doc.getElementById('iiif-url-warning').style.display = 'block';
}

/** Detect a mismatch and, if there is one, show the banner. */
export async function initIIIFUrlWarning(config, { doc = document, fetch, location } = {}) {
  if (!config || !config.objectsUrl || !config.iiifObjectsBase || !config.strings) return;

  const result = await findAffectedObjects(config, { fetch, location });
  if (result) renderWarning(result, config.strings, doc);
}

const data = readWarningData();
if (data) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initIIIFUrlWarning(data));
  } else {
    initIIIFUrlWarning(data);
  }
}
