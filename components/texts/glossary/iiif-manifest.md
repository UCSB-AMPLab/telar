---
term_id: iiif-manifest
title: "IIIF Manifest"
related_terms: iiif, iiif-tiles
---

A IIIF manifest is a [JSON-LD](https://json-ld.org/) (JavaScript Object Notation for Linked Data) file that describes one or more images and their metadata according to the [IIIF Presentation API](https://iiif.io/api/presentation/) specification. The manifest serves as a "recipe" that tells IIIF-compatible viewers and tools, like Telar, what images are available, how they're organized, and how to display them.

At a technical level, a manifest contains several key components: metadata about the object (title, description, attribution, rights, license), a sequence of "canvases" (each representing a page, view, or surface), and annotations that link these canvases to actual image resources served by a IIIF Image API server. For example, a manifest for a medieval manuscript might describe 200 canvases (pages), each linked to high-resolution images of that page, along with metadata about the manuscript's provenance, date, and current location.

When you provide a manifest URL to Telar (or any IIIF viewer), the application fetches this JSON file, reads its structured data to understand what images are available and their dimensions, and then requests image tiles at appropriate sizes and regions as users pan and zoom. The manifest might look like: `https://example.org/iiif/object123/manifest.json` or follow the pattern `/iiif/2/{identifier}/manifest`.

Manifests can describe complex objects: multi-page books, photograph albums, collections of related images, or even 3D objects represented as image sequences. Because manifests follow a standardized format, any IIIF viewer can consume them, regardless of what institution created them. This interoperability is IIIF's core value proposition—you can display a manifest from the Bodleian Library in the same tool as one from the Smithsonian, compare them side-by-side, or annotate them using the same interface.

**Learn more:**
- [IIIF Presentation API 3.0 specification](https://iiif.io/api/presentation/3.0/)
- [Understanding the IIIF Presentation API](https://iiif.io/api/presentation/3.0/#introduction)
- [IIIF Cookbook - Manifest recipes and examples](https://iiif.io/api/cookbook/)
- [JSON-LD on Wikipedia](https://en.wikipedia.org/wiki/JSON-LD)
