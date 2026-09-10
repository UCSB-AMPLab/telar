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

  // assets/js/iiif-thumbnails/objects-index.js
  function readObjectsIndexData(doc = document) {
    const block = doc.getElementById("telar-objects-index-data");
    if (!block) return null;
    try {
      return JSON.parse(block.textContent);
    } catch (err) {
      console.error("Objects index data block is not valid JSON:", err);
      return null;
    }
  }
  function initLocalThumbnails(data2, doc = document) {
    const localItems = doc.querySelectorAll(".local-iiif-thumbnail[data-info-json]");
    localItems.forEach(function(item) {
      const infoUrl = item.getAttribute("data-info-json");
      resolveInfoJsonThumbnail(infoUrl).then((url) => {
        if (url) {
          const img = doc.createElement("img");
          img.src = url;
          img.alt = item.closest(".collection-item").querySelector("h3").textContent;
          const placeholder = item.querySelector(".manifest-thumbnail-placeholder");
          if (placeholder) {
            placeholder.replaceWith(img);
          }
        }
      }).catch((error) => {
        console.error("Error loading IIIF info.json:", infoUrl, error);
        const placeholder = item.querySelector(".manifest-thumbnail-placeholder");
        if (placeholder) {
          placeholder.innerHTML = '<span class="text-danger">' + data2.lang.thumbnailLoadError + "</span>";
        }
      });
    });
  }
  function initManifestThumbnails(data2, doc = document) {
    const items = doc.querySelectorAll(".collection-item-image[data-iiif-manifest]");
    items.forEach(function(item) {
      const manifestUrl = item.getAttribute("data-iiif-manifest");
      if (manifestUrl.includes("info.json")) {
        return;
      }
      resolveManifestThumbnail(manifestUrl, "!400,400").then((url) => {
        if (url) {
          const img = doc.createElement("img");
          img.src = url;
          img.alt = item.closest(".collection-item").querySelector("h3").textContent;
          img.className = "iiif-thumbnail";
          const placeholder = item.querySelector(".manifest-thumbnail-placeholder");
          if (placeholder) placeholder.replaceWith(img);
        }
      }).catch((error) => {
        const placeholder = item.querySelector(".manifest-thumbnail-placeholder");
        if (error && error.noImage) {
          console.warn("No image found in manifest:", manifestUrl);
          if (placeholder) {
            placeholder.innerHTML = '<span class="text-muted">' + data2.lang.noImage + "</span>";
          }
        } else {
          console.error("Error loading manifest thumbnail:", manifestUrl, error);
          if (placeholder) {
            placeholder.innerHTML = '<span class="text-danger">' + data2.lang.thumbnailLoadError + "</span>";
          }
        }
      });
    });
  }
  function initObjectsIndexPage(data2, doc = document) {
    upgradeExplicitThumbnails(doc);
    initLocalThumbnails(data2, doc);
    initManifestThumbnails(data2, doc);
  }
  var data = readObjectsIndexData();
  if (data) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => initObjectsIndexPage(data));
    } else {
      initObjectsIndexPage(data);
    }
  }
})();
//# sourceMappingURL=objects-index-page.js.map
