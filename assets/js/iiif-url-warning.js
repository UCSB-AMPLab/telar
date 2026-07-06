/**
 * Telar — IIIF URL mismatch diagnostic.
 *
 * A self-diagnosing check for the most common reason locally hosted images fail
 * to appear: the address the site is being viewed at no longer matches the base
 * URL baked into its IIIF manifests when the tiles were generated. This script
 * decides whether to reveal the hidden alert banner defined in
 * `_includes/iiif-url-warning.html`.
 *
 * How it works — on load the script reads the current origin and baseurl,
 * fetches objects.json, and keeps only objects that rely on local IIIF tiles (no
 * external iiif_manifest). For each it fetches the object's manifest.json and
 * extracts the base URL from the manifest's own id, then compares that (trailing
 * slashes normalised) against where the page is actually being served. Any
 * object whose manifest points elsewhere is collected as "affected", and if
 * there are any the banner is shown listing them.
 *
 * Local vs production guidance — the fix differs by environment, so the script
 * branches on whether the origin is localhost/127.0.0.1. Local development gets
 * a ready-to-run generate_iiif.py command targeting the current URL; production
 * gets the suggested url:/baseurl: _config.yml values (parsed from the live
 * address) plus the regenerate-and-push workflow. Detection failures fail
 * silently — the banner stays hidden rather than alarming the user over an
 * unrelated fetch error.
 *
 * Classic script, not a module — loaded by a plain <script> tag from the include,
 * which also sets `window.telarIIIFWarningConfig` immediately beforehand: the
 * objects.json and IIIF manifest base paths (Liquid `relative_url`s, so they
 * carry the site's baseurl), plus the localized singular/plural "affected
 * images" strings from `_data/languages/<telar_language>.yml`. If that global or
 * any of its required fields are missing, the check exits silently — the same
 * fail-silent philosophy as the network-error handling below.
 *
 * @version v1.6.0
 */

(function() {
  var config = window.telarIIIFWarningConfig;
  if (!config || !config.objectsUrl || !config.iiifObjectsBase || !config.strings) return;

  const TelarI18nIIIF = config.strings;

  // Check for IIIF URL mismatch
  async function checkIIIFUrlMismatch() {
    // Get current site URL
    const currentOrigin = window.location.origin;
    const currentPath = window.location.pathname;

    // Extract baseurl (everything up to the last path segment)
    const pathParts = currentPath.split('/').filter(p => p);
    const baseurl = pathParts.length > 0 ? '/' + pathParts[0] : '';
    const currentSiteUrl = currentOrigin + baseurl;

    // Detect if this is local development or production
    const isLocalDev = currentOrigin.includes('localhost') || currentOrigin.includes('127.0.0.1');

    try {
      // Fetch all objects to check for mismatches
      const objectsResponse = await fetch(config.objectsUrl);
      if (!objectsResponse.ok) return;

      const objects = await objectsResponse.json();

      // Find all objects with local IIIF tiles (no external iiif_manifest)
      const localObjects = objects.filter(obj => {
        return (!obj.iiif_manifest || obj.iiif_manifest === '');
      });

      if (localObjects.length === 0) return; // No local objects to check

      // Check all local objects for URL mismatch
      const affectedObjects = [];
      let manifestBaseUrl = null;

      for (const obj of localObjects) {
        try {
          const manifestPath = `${config.iiifObjectsBase}/${obj.object_id}/manifest.json`;
          const manifestResponse = await fetch(manifestPath);
          if (!manifestResponse.ok) continue; // Skip if manifest doesn't exist

          const manifest = await manifestResponse.json();

          // Extract base URL from manifest ID
          const manifestId = manifest.id;
          const extractedBaseUrl = manifestId.split('/iiif/')[0];

          // Store the manifest base URL (should be same for all)
          if (!manifestBaseUrl) {
            manifestBaseUrl = extractedBaseUrl;
          }

          // Compare URLs (normalize trailing slashes)
          const normalizedCurrent = currentSiteUrl.replace(/\/$/, '');
          const normalizedManifest = extractedBaseUrl.replace(/\/$/, '');

          if (normalizedCurrent !== normalizedManifest) {
            affectedObjects.push({
              id: obj.object_id,
              title: obj.title || obj.object_id
            });
          }
        } catch (error) {
          console.log(`Could not check manifest for ${obj.object_id}:`, error);
        }
      }

      // If there are affected objects, show the warning
      if (affectedObjects.length > 0 && manifestBaseUrl) {
        // Populate common elements
        document.getElementById('current-url').textContent = currentSiteUrl;
        document.getElementById('manifest-url').textContent = manifestBaseUrl;

        // Update affected images heading with localized singular/plural template
        const heading = document.getElementById('affected-images-heading');
        const count = affectedObjects.length;
        const template = count === 1
          ? TelarI18nIIIF.affectedImagesSingular
          : TelarI18nIIIF.affectedImagesPlural;
        heading.textContent = template.replace('__COUNT__', count);

        // Populate affected images list. Build each row with DOM nodes so an
        // object title containing markup renders as text, not as HTML.
        const affectedList = document.getElementById('affected-images');
        affectedList.replaceChildren();
        affectedObjects.forEach(obj => {
          const li = document.createElement('li');
          const strong = document.createElement('strong');
          strong.textContent = obj.title;
          li.appendChild(strong);
          li.appendChild(document.createTextNode(` (${obj.id})`));
          affectedList.appendChild(li);
        });

        // Show context-appropriate fix instructions
        if (isLocalDev) {
          // Local development scenario
          document.getElementById('local-fix-instructions').style.display = 'block';
          document.getElementById('local-command').textContent =
            `python3 scripts/generate_iiif.py --base-url ${currentSiteUrl}`;
        } else {
          // Production scenario
          document.getElementById('production-fix-instructions').style.display = 'block';

          // Parse current URL into url and baseurl components
          const urlObj = new URL(currentSiteUrl);
          const urlPart = `${urlObj.protocol}//${urlObj.host}`;
          const baseurlPart = urlObj.pathname || '';

          document.getElementById('production-current-url').textContent = currentSiteUrl;
          document.getElementById('production-config-suggestion').textContent =
            `url: "${urlPart}" and baseurl: "${baseurlPart}"`;
          document.getElementById('production-local-command').textContent =
            `python3 scripts/generate_iiif.py --base-url ${currentSiteUrl}`;
        }

        // Show the warning
        document.getElementById('iiif-url-warning').style.display = 'block';
      }
    } catch (error) {
      // Silently fail - don't show warning if we can't determine mismatch
      console.log('Could not check IIIF URL mismatch:', error);
    }
  }

  // Run check when page loads
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', checkIIIFUrlMismatch);
  } else {
    checkIIIFUrlMismatch();
  }
})();
