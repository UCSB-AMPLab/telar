---
term_id: iiif-manifest
title: "IIIF Manifest"
related_terms: iiif, iiif-tiles
layout: glossary
---

<p>A IIIF manifest is a <a href="https://json-ld.org/">JSON-LD</a> (JavaScript Object Notation for Linked Data) file that describes one or more images and their metadata according to the <a href="https://iiif.io/api/presentation/">IIIF Presentation API</a> specification. The manifest serves as a "recipe" that tells IIIF-compatible viewers and tools, like Telar, what images are available, how they're organized, and how to display them.</p>
<p>At a technical level, a manifest contains several key components: metadata about the object (title, description, attribution, rights, license), a sequence of "canvases" (each representing a page, view, or surface), and annotations that link these canvases to actual image resources served by a IIIF Image API server. For example, a manifest for a medieval manuscript might describe 200 canvases (pages), each linked to high-resolution images of that page, along with metadata about the manuscript's provenance, date, and current location.</p>
<p>When you provide a manifest URL to Telar (or any IIIF viewer), the application fetches this JSON file, reads its structured data to understand what images are available and their dimensions, and then requests image tiles at appropriate sizes and regions as users pan and zoom. The manifest might look like: <code>https://example.org/iiif/object123/manifest.json</code> or follow the pattern <code>/iiif/2/{identifier}/manifest</code>.</p>
<p>Manifests can describe complex objects: multi-page books, photograph albums, collections of related images, or even 3D objects represented as image sequences. Because manifests follow a standardized format, any IIIF viewer can consume them, regardless of what institution created them. This interoperability is IIIF's core value proposition—you can display a manifest from the Bodleian Library in the same tool as one from the Smithsonian, compare them side-by-side, or annotate them using the same interface.</p>
<p><strong>Learn more:</strong><br />
- <a href="https://iiif.io/api/presentation/3.0/">IIIF Presentation API 3.0 specification</a><br />
- <a href="https://iiif.io/api/presentation/3.0/#introduction">Understanding the IIIF Presentation API</a><br />
- <a href="https://iiif.io/api/cookbook/">IIIF Cookbook - Manifest recipes and examples</a><br />
- <a href="https://en.wikipedia.org/wiki/JSON-LD">JSON-LD on Wikipedia</a></p>
