---
layout: default
title: Objects in the Stories
permalink: /objects/
---

<div class="container my-5">
  <div class="row">
    <div class="col-12">
      <h1>Objects in the Stories</h1>
      <p class="lead">Browse {{ site.objects.size }} objects featured in the stories.</p>
    </div>
  </div>

  {% if site.objects.size > 0 %}
  <div class="collection-grid">
    {% for object in site.objects %}
    <a href="{{ object.url | relative_url }}" class="collection-item">
      <div class="collection-item-image" {% if object.iiif_manifest %}data-iiif-manifest="{{ object.iiif_manifest }}"{% endif %}>
        {% if object.thumbnail %}
        {%- comment -%}Use explicit thumbnail if provided{%- endcomment -%}
        <img src="{{ object.thumbnail | relative_url }}" alt="{{ object.title }}">
        {% elsif object.iiif_manifest and object.iiif_manifest contains 'info.json' %}
        {%- comment -%}For IIIF Image API, use standard thumbnail pattern{%- endcomment -%}
        <img src="{{ object.iiif_manifest | replace: 'info.json', 'full/!400,400/0/default.jpg' }}" alt="{{ object.title }}" class="iiif-thumbnail">
        {% elsif object.iiif_manifest %}
        {%- comment -%}For IIIF manifests, JavaScript will load thumbnail{%- endcomment -%}
        <div class="manifest-thumbnail-placeholder bg-light d-flex align-items-center justify-content-center" style="height: 250px;">
          <span class="text-muted">Loading...</span>
        </div>
        {% elsif object.object_id %}
        {%- comment -%}For local objects, load thumbnail via info.json{%- endcomment -%}
        <div class="local-iiif-thumbnail" data-info-json="{{ '/iiif/objects/' | append: object.object_id | append: '/info.json' | relative_url }}">
          <div class="manifest-thumbnail-placeholder bg-light d-flex align-items-center justify-content-center" style="height: 250px;">
            <span class="text-muted">Loading...</span>
          </div>
        </div>
        {% else %}
        <div class="placeholder-image bg-secondary d-flex align-items-center justify-content-center" style="height: 250px;">
          <span class="text-white">No image</span>
        </div>
        {% endif %}
      </div>
      <h3>{{ object.title }}</h3>
      {% if object.period %}
      <p class="text-muted mb-0">{{ object.period }}</p>
      {% endif %}
      {% if object.creator %}
      <p class="text-muted mb-0">{{ object.creator }}</p>
      {% endif %}
    </a>
    {% endfor %}
  </div>
  {% else %}
  <div class="row">
    <div class="col-12">
      <div class="alert alert-info">
        <p class="mb-0">No objects in the collection yet. Add object files to the <code>_objects/</code> directory to populate the collection.</p>
      </div>
    </div>
  </div>
  {% endif %}
</div>

<script>
/**
 * Load thumbnails from IIIF manifests and info.json
 */
document.addEventListener('DOMContentLoaded', function() {
  // Handle local IIIF thumbnails from info.json
  const localItems = document.querySelectorAll('.local-iiif-thumbnail[data-info-json]');
  localItems.forEach(function(item) {
    const infoUrl = item.getAttribute('data-info-json');

    fetch(infoUrl)
      .then(response => response.json())
      .then(info => {
        // Get the largest available size from sizes array (first element)
        const sizes = info.sizes || [];
        let thumbnailSize = sizes[0]; // Get largest size (first in array)

        if (thumbnailSize) {
          let baseUrl = info.id || info['@id'];
          // Remove the image identifier from the end if present
          baseUrl = baseUrl.replace(/\/[^\/]+$/, '');
          const thumbnailUrl = `${baseUrl}/full/${thumbnailSize.width},/0/default.jpg`;

          const img = document.createElement('img');
          img.src = thumbnailUrl;
          img.alt = item.closest('.collection-item').querySelector('h3').textContent;

          const placeholder = item.querySelector('.manifest-thumbnail-placeholder');
          if (placeholder) {
            placeholder.replaceWith(img);
          }
        }
      })
      .catch(error => {
        console.error('Error loading IIIF info.json:', infoUrl, error);
        const placeholder = item.querySelector('.manifest-thumbnail-placeholder');
        if (placeholder) {
          placeholder.innerHTML = '<span class="text-danger">Failed to load</span>';
        }
      });
  });

  // Handle external IIIF manifest thumbnails
  const items = document.querySelectorAll('.collection-item-image[data-iiif-manifest]');

  items.forEach(function(item) {
    const manifestUrl = item.getAttribute('data-iiif-manifest');

    // Skip if not a manifest.json (Image API handled in template)
    if (!manifestUrl.includes('manifest.json')) {
      return;
    }

    // Fetch manifest to extract thumbnail
    fetch(manifestUrl)
      .then(response => response.json())
      .then(manifest => {
        let thumbnailUrl = null;

        // Try different IIIF Presentation API versions
        if (manifest.thumbnail) {
          // IIIF Presentation 3.0
          if (Array.isArray(manifest.thumbnail)) {
            thumbnailUrl = manifest.thumbnail[0].id || manifest.thumbnail[0]['@id'];
          } else if (typeof manifest.thumbnail === 'object') {
            thumbnailUrl = manifest.thumbnail.id || manifest.thumbnail['@id'];
          } else if (typeof manifest.thumbnail === 'string') {
            thumbnailUrl = manifest.thumbnail;
          }
        } else if (manifest.sequences && manifest.sequences[0]) {
          // IIIF Presentation 2.0 - check sequences
          const firstCanvas = manifest.sequences[0].canvases && manifest.sequences[0].canvases[0];
          if (firstCanvas && firstCanvas.thumbnail) {
            if (typeof firstCanvas.thumbnail === 'object') {
              thumbnailUrl = firstCanvas.thumbnail['@id'] || firstCanvas.thumbnail.id;
            } else {
              thumbnailUrl = firstCanvas.thumbnail;
            }
          }
        } else if (manifest.items && manifest.items[0]) {
          // IIIF Presentation 3.0 - check items
          const firstCanvas = manifest.items[0];
          if (firstCanvas.thumbnail) {
            if (Array.isArray(firstCanvas.thumbnail)) {
              thumbnailUrl = firstCanvas.thumbnail[0].id;
            } else {
              thumbnailUrl = firstCanvas.thumbnail.id;
            }
          }
        }

        // If no thumbnail found, try to extract image URL from canvas and create thumbnail
        if (!thumbnailUrl) {
          // Try to get the image service URL from canvas resources
          if (manifest.sequences && manifest.sequences[0]) {
            const firstCanvas = manifest.sequences[0].canvases && manifest.sequences[0].canvases[0];
            if (firstCanvas && firstCanvas.images && firstCanvas.images[0]) {
              const resource = firstCanvas.images[0].resource;
              if (resource && resource['@id']) {
                // If it's a full image URL, try to convert to IIIF thumbnail
                const imageUrl = resource['@id'];
                if (imageUrl.includes('/full/full/')) {
                  // Convert full image to thumbnail size
                  thumbnailUrl = imageUrl.replace('/full/full/', '/full/!400,400/');
                } else {
                  // Use the image as-is (will be scaled by CSS)
                  thumbnailUrl = imageUrl;
                }
              }
            }
          }
        }

        // If we found a thumbnail, replace placeholder
        if (thumbnailUrl) {
          const img = document.createElement('img');
          img.src = thumbnailUrl;
          img.alt = item.closest('.collection-item').querySelector('h3').textContent;
          img.className = 'iiif-thumbnail';

          // Replace placeholder
          const placeholder = item.querySelector('.manifest-thumbnail-placeholder');
          if (placeholder) {
            placeholder.replaceWith(img);
          }
        } else {
          console.warn('No thumbnail found in manifest:', manifestUrl);
          // Show "no image" placeholder
          const placeholder = item.querySelector('.manifest-thumbnail-placeholder');
          if (placeholder) {
            placeholder.innerHTML = '<span class="text-muted">No image</span>';
          }
        }
      })
      .catch(error => {
        console.error('Error loading manifest thumbnail:', manifestUrl, error);
        // Show error placeholder
        const placeholder = item.querySelector('.manifest-thumbnail-placeholder');
        if (placeholder) {
          placeholder.innerHTML = '<span class="text-danger">Failed to load</span>';
        }
      });
  });
});
</script>
