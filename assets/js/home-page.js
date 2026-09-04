/* GENERATED FILE - do not edit. Bundled from assets/js/iiif-thumbnails/ by esbuild. Rebuild: npm run build:js (see assets/js/README.md). */
(() => {
  // assets/js/iiif-thumbnails/resolve.js
  function pickThumbnailSize(sizes, minWidth) {
    if (!sizes || sizes.length === 0) return null;
    minWidth = minWidth || 400;
    var sorted = sizes.slice().sort(function(a, b) {
      return a.width - b.width;
    });
    for (var i = 0; i < sorted.length; i++) {
      if (sorted[i].width >= minWidth) return sorted[i];
    }
    return sorted[sorted.length - 1];
  }
  function upgradeIIIFThumbnailUrl(url) {
    var match = url.match(/^(.*\/full\/)[\\\/]*([^/]+)(\/0\/default\.\w+)$/);
    if (match) {
      return match[1] + "!600,600" + match[3];
    }
    return url;
  }
  function extractManifestImageV2(manifest) {
    var imageServiceUrl = null;
    var imageServiceProfile = null;
    var fallbackImageUrl = null;
    var firstCanvas = manifest.sequences[0] && manifest.sequences[0].canvases ? manifest.sequences[0].canvases[0] : null;
    if (firstCanvas && firstCanvas.images && firstCanvas.images[0]) {
      var resource = firstCanvas.images[0].resource;
      if (resource.service) {
        var service = Array.isArray(resource.service) ? resource.service[0] : resource.service;
        imageServiceUrl = service["@id"] || service.id;
        imageServiceProfile = service.profile;
      }
      if (resource["@id"]) {
        fallbackImageUrl = resource["@id"];
      }
    }
    return {
      imageServiceUrl,
      imageServiceProfile,
      fallbackImageUrl
    };
  }
  function extractManifestImageV3(manifest) {
    var imageServiceUrl = null;
    var imageServiceProfile = null;
    var fallbackImageUrl = null;
    var v3Canvas = manifest.items[0];
    if (v3Canvas.items && v3Canvas.items[0] && v3Canvas.items[0].items) {
      var annotationBody = v3Canvas.items[0].items[0].body;
      if (annotationBody.service && annotationBody.service.length > 0) {
        imageServiceUrl = annotationBody.service[0].id || annotationBody.service[0]["@id"];
        imageServiceProfile = annotationBody.service[0].profile;
      }
      if (annotationBody.id) {
        fallbackImageUrl = annotationBody.id;
      }
    }
    return {
      imageServiceUrl,
      imageServiceProfile,
      fallbackImageUrl
    };
  }
  function extractManifestImage(manifest) {
    if (manifest.sequences && manifest.sequences[0] && manifest.sequences[0].canvases) {
      return extractManifestImageV2(manifest);
    }
    if (manifest.items && manifest.items[0]) {
      return extractManifestImageV3(manifest);
    }
    return { imageServiceUrl: null, imageServiceProfile: null, fallbackImageUrl: null };
  }
  function isLevel0Profile(profile) {
    var entries = Array.isArray(profile) ? profile : [profile];
    for (var i = 0; i < entries.length; i++) {
      if (typeof entries[i] === "string" && entries[i].toLowerCase().indexOf("level0") !== -1) {
        return true;
      }
    }
    return false;
  }
  function resolveManifestThumbnail(manifestUrl, sizeParam) {
    sizeParam = sizeParam || "!400,400";
    return fetch(manifestUrl).then(function(response) {
      return response.json();
    }).then(function(manifest) {
      var image = extractManifestImage(manifest);
      var imageServiceUrl = image.imageServiceUrl;
      var fallbackImageUrl = image.fallbackImageUrl;
      if (imageServiceUrl && isLevel0Profile(image.imageServiceProfile)) {
        imageServiceUrl = imageServiceUrl.replace(/\/$/, "");
        return fetch(imageServiceUrl + "/info.json").then(function(r) {
          return r.json();
        }).then(function(info) {
          var size = pickThumbnailSize(info.sizes, 400);
          return size ? imageServiceUrl + "/full/" + size.width + "," + size.height + "/0/default.jpg" : fallbackImageUrl || null;
        }).catch(function() {
          return fallbackImageUrl || null;
        });
      }
      if (imageServiceUrl) {
        imageServiceUrl = imageServiceUrl.replace(/\/$/, "");
        return imageServiceUrl + "/full/" + sizeParam + "/0/default.jpg";
      }
      if (fallbackImageUrl) {
        return fallbackImageUrl;
      }
      var error = new Error("No image found in manifest");
      error.noImage = true;
      throw error;
    });
  }
  function resolveInfoJsonThumbnail(infoUrl, minWidth) {
    return fetch(infoUrl).then(function(response) {
      return response.json();
    }).then(function(info) {
      var thumbnailSize = pickThumbnailSize(info.sizes || [], minWidth);
      if (!thumbnailSize) return null;
      var baseUrl = info.id || info["@id"];
      return baseUrl + "/full/" + thumbnailSize.width + "," + thumbnailSize.height + "/0/default.jpg";
    });
  }

  // assets/js/iiif-thumbnails/explicit-thumbnails.js
  function upgradeExplicitThumbnails(doc = document) {
    var iiifThumbs = doc.querySelectorAll("img.iiif-thumbnail");
    iiifThumbs.forEach(function(img) {
      var originalSrc = img.src;
      var upgradedSrc = upgradeIIIFThumbnailUrl(originalSrc);
      if (upgradedSrc !== originalSrc) {
        img.dataset.originalSrc = originalSrc;
        img.onerror = function() {
          if (this.dataset.originalSrc) {
            this.src = this.dataset.originalSrc;
            delete this.dataset.originalSrc;
            this.onerror = null;
          }
        };
        img.src = upgradedSrc;
      }
    });
  }

  // assets/js/iiif-thumbnails/home.js
  function readHomeData(doc = document) {
    const block = doc.getElementById("telar-home-data");
    if (!block) return null;
    try {
      return JSON.parse(block.textContent);
    } catch (err) {
      console.error("Home page data block is not valid JSON:", err);
      return null;
    }
  }
  function initStoryThumbnails(data2, doc = document) {
    const objectsData = data2.objects;
    const storyThumbnails = doc.querySelectorAll(".story-iiif-thumbnail[data-object-id]");
    storyThumbnails.forEach(function(item) {
      const objectId = item.getAttribute("data-object-id");
      const localInfoUrl = item.getAttribute("data-info-json");
      const objectData = objectsData.find((obj) => obj.object_id === objectId);
      if (objectData && objectData.thumbnail && objectData.thumbnail.trim() !== "") {
        const img = doc.createElement("img");
        const originalUrl = objectData.thumbnail;
        const upgradedUrl = upgradeIIIFThumbnailUrl(originalUrl);
        img.src = upgradedUrl;
        if (upgradedUrl !== originalUrl) {
          img.onerror = function() {
            this.src = originalUrl;
            this.onerror = null;
          };
        }
        img.alt = item.closest(".story-card").querySelector("h3").textContent;
        img.style.width = "100%";
        img.style.height = "100%";
        img.style.objectFit = "cover";
        const placeholder = item.querySelector(".manifest-thumbnail-placeholder");
        if (placeholder) {
          placeholder.replaceWith(img);
        }
      } else if (objectData && objectData.iiif_manifest) {
        resolveManifestThumbnail(objectData.iiif_manifest, "!400,400").then((url) => {
          if (url) replaceStoryPlaceholder(url);
        }).catch((error) => {
          console.error("Error loading remote IIIF manifest:", objectData.iiif_manifest, error);
          const placeholder = item.querySelector(".manifest-thumbnail-placeholder");
          if (placeholder) {
            placeholder.innerHTML = '<span class="text-danger">' + data2.lang.thumbnailLoadError + "</span>";
          }
        });
      } else {
        resolveInfoJsonThumbnail(localInfoUrl).then((url) => {
          if (url) replaceStoryPlaceholder(url);
        }).catch((error) => {
          console.error("Error loading local IIIF info.json:", localInfoUrl, error);
          const placeholder = item.querySelector(".manifest-thumbnail-placeholder");
          if (placeholder) {
            placeholder.innerHTML = '<span class="text-danger">' + data2.lang.thumbnailLoadError + "</span>";
          }
        });
      }
      function replaceStoryPlaceholder(url) {
        const img = doc.createElement("img");
        img.src = url;
        img.alt = item.closest(".story-card").querySelector("h3").textContent;
        img.style.width = "100%";
        img.style.height = "100%";
        img.style.objectFit = "cover";
        const placeholder = item.querySelector(".manifest-thumbnail-placeholder");
        if (placeholder) placeholder.replaceWith(img);
      }
    });
  }
  function initFeaturedThumbnails(data2, doc = document) {
    const objectsData = data2.objects;
    const featuredThumbnails = doc.querySelectorAll(".featured-iiif-thumbnail[data-object-id]");
    featuredThumbnails.forEach(function(item) {
      const objectId = item.getAttribute("data-object-id");
      const localInfoUrl = item.getAttribute("data-info-json");
      const objectData = objectsData.find((obj) => obj.object_id === objectId);
      if (objectData && objectData.thumbnail && objectData.thumbnail.trim() !== "") {
        const img = doc.createElement("img");
        const originalUrl = objectData.thumbnail;
        const upgradedUrl = upgradeIIIFThumbnailUrl(originalUrl);
        img.src = upgradedUrl;
        if (upgradedUrl !== originalUrl) {
          img.onerror = function() {
            this.src = originalUrl;
            this.onerror = null;
          };
        }
        img.alt = item.closest(".collection-item").querySelector(".collection-title").textContent;
        img.style.width = "100%";
        img.style.height = "100%";
        img.style.objectFit = "cover";
        item.innerHTML = "";
        item.appendChild(img);
      } else if (objectData && objectData.iiif_manifest) {
        resolveManifestThumbnail(objectData.iiif_manifest, "!200,200").then((url) => {
          if (url) replaceFeaturedImg(url);
        }).catch((error) => {
          if (error && error.noImage) return;
          console.error("Error loading featured object manifest:", objectData.iiif_manifest, error);
        });
      } else {
        resolveInfoJsonThumbnail(localInfoUrl).then((url) => {
          if (url) replaceFeaturedImg(url);
        }).catch((error) => {
          console.error("Error loading featured object info.json:", localInfoUrl, error);
        });
      }
      function replaceFeaturedImg(url) {
        const img = doc.createElement("img");
        img.src = url;
        img.alt = item.closest(".collection-item").querySelector(".collection-title").textContent;
        img.style.width = "100%";
        img.style.height = "100%";
        img.style.objectFit = "cover";
        item.innerHTML = "";
        item.appendChild(img);
      }
    });
  }
  function initManifestPrefetch(data2, doc = document) {
    const objectsData = data2.objects;
    const prefetchedManifests = /* @__PURE__ */ new Set();
    doc.querySelectorAll(".story-card").forEach(function(card) {
      card.addEventListener("mouseenter", function() {
        const storyUrl = this.getAttribute("href");
        if (!storyUrl) return;
        const thumbnailEl = this.querySelector(".story-iiif-thumbnail[data-object-id]");
        if (!thumbnailEl) return;
        const objectId = thumbnailEl.getAttribute("data-object-id");
        if (!objectId) return;
        const objectData = objectsData.find((obj) => obj.object_id === objectId);
        if (objectData && objectData.iiif_manifest && !prefetchedManifests.has(objectData.iiif_manifest)) {
          prefetchedManifests.add(objectData.iiif_manifest);
          const prefetchLink = doc.createElement("link");
          prefetchLink.rel = "prefetch";
          prefetchLink.href = objectData.iiif_manifest;
          doc.head.appendChild(prefetchLink);
          console.log(`Prefetching manifest for ${objectId} on hover`);
        }
      }, { once: true });
    });
  }
  function initHomePage(data2, doc = document) {
    upgradeExplicitThumbnails(doc);
    initStoryThumbnails(data2, doc);
    initFeaturedThumbnails(data2, doc);
    initManifestPrefetch(data2, doc);
  }
  var data = readHomeData();
  if (data) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => initHomePage(data));
    } else {
      initHomePage(data);
    }
  }
})();
//# sourceMappingURL=home-page.js.map
