/* GENERATED FILE - do not edit. Bundled from assets/js/iiif-url-warning/ by esbuild. Rebuild: npm run build:js (see assets/js/README.md). */
(() => {
  // assets/js/iiif-url-warning/main.js
  function readWarningData(doc = document) {
    const block = doc.getElementById("telar-iiif-warning-data");
    if (!block) return null;
    try {
      return JSON.parse(block.textContent);
    } catch (err) {
      console.error("IIIF URL warning data block is not valid JSON:", err);
      return null;
    }
  }
  function siteUrlFromLocation(location) {
    const pathParts = location.pathname.split("/").filter((p) => p);
    const baseurl = pathParts.length > 0 ? "/" + pathParts[0] : "";
    return location.origin + baseurl;
  }
  function isLocalDevOrigin(origin) {
    return origin.includes("localhost") || origin.includes("127.0.0.1");
  }
  function manifestBaseFromId(manifestId) {
    return manifestId.split("/iiif/")[0];
  }
  function sameSite(siteUrl, manifestBase) {
    return siteUrl.replace(/\/$/, "") === manifestBase.replace(/\/$/, "");
  }
  function regenerationCommand(siteUrl) {
    return `python3 scripts/generate_iiif.py --base-url ${siteUrl}`;
  }
  function configSuggestion(siteUrl) {
    const urlObj = new URL(siteUrl);
    const urlPart = `${urlObj.protocol}//${urlObj.host}`;
    const baseurlPart = urlObj.pathname || "";
    return `url: "${urlPart}" and baseurl: "${baseurlPart}"`;
  }
  function isLocalObject(obj) {
    return !obj.iiif_manifest || obj.iiif_manifest === "";
  }
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
  async function findAffectedObjects(config, {
    fetch = (url) => globalThis.fetch(url),
    location = globalThis.location
  } = {}) {
    const currentSiteUrl = siteUrlFromLocation(location);
    const isLocalDev = isLocalDevOrigin(location.origin);
    try {
      const objectsResponse = await fetch(config.objectsUrl);
      if (!objectsResponse.ok) return null;
      const objects = await objectsResponse.json();
      const localObjects = objects.filter(isLocalObject);
      const { affectedObjects, manifestBaseUrl } = await collectAffected(config, localObjects, currentSiteUrl, fetch);
      if (affectedObjects.length === 0 || !manifestBaseUrl) return null;
      return { affectedObjects, manifestBaseUrl, currentSiteUrl, isLocalDev };
    } catch (error) {
      console.log("Could not check IIIF URL mismatch:", error);
      return null;
    }
  }
  function renderHeading(count, strings, doc) {
    const template = count === 1 ? strings.affectedImagesSingular : strings.affectedImagesPlural;
    doc.getElementById("affected-images-heading").textContent = template.replace("__COUNT__", count);
  }
  function renderAffectedList(affectedObjects, doc) {
    const affectedList = doc.getElementById("affected-images");
    affectedList.replaceChildren();
    affectedObjects.forEach((obj) => {
      const li = doc.createElement("li");
      const strong = doc.createElement("strong");
      strong.textContent = obj.title;
      li.appendChild(strong);
      li.appendChild(doc.createTextNode(` (${obj.id})`));
      affectedList.appendChild(li);
    });
  }
  function renderFixInstructions(currentSiteUrl, isLocalDev, doc) {
    if (isLocalDev) {
      doc.getElementById("local-fix-instructions").style.display = "block";
      doc.getElementById("local-command").textContent = regenerationCommand(currentSiteUrl);
      return;
    }
    doc.getElementById("production-fix-instructions").style.display = "block";
    doc.getElementById("production-current-url").textContent = currentSiteUrl;
    doc.getElementById("production-config-suggestion").textContent = configSuggestion(currentSiteUrl);
    doc.getElementById("production-local-command").textContent = regenerationCommand(currentSiteUrl);
  }
  function renderWarning(result, strings, doc = document) {
    doc.getElementById("current-url").textContent = result.currentSiteUrl;
    doc.getElementById("manifest-url").textContent = result.manifestBaseUrl;
    renderHeading(result.affectedObjects.length, strings, doc);
    renderAffectedList(result.affectedObjects, doc);
    renderFixInstructions(result.currentSiteUrl, result.isLocalDev, doc);
    doc.getElementById("iiif-url-warning").style.display = "block";
  }
  async function initIIIFUrlWarning(config, { doc = document, fetch, location } = {}) {
    if (!config || !config.objectsUrl || !config.iiifObjectsBase || !config.strings) return;
    const result = await findAffectedObjects(config, { fetch, location });
    if (result) renderWarning(result, config.strings, doc);
  }
  var data = readWarningData();
  if (data) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => initIIIFUrlWarning(data));
    } else {
      initIIIFUrlWarning(data);
    }
  }
})();
//# sourceMappingURL=iiif-url-warning.js.map
