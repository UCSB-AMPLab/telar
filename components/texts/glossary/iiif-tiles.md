---
term_id: iiif-tiles
title: "IIIF Tiles"
related_terms: iiif, iiif-manifest
---

IIIF tiles are small, square image segments (typically 256×256 or 512×512 pixels) arranged in a multi-resolution pyramid structure that enables smooth pan and zoom functionality for large, high-resolution images on the web. This approach, commonly called "[deep zoom](https://en.wikipedia.org/wiki/Deep_Zoom)" or "tiled pyramids," addresses a key challenge in web-based image viewing, that high-resolution photograph or manuscript scans can be far too large to download and display at once, especially on mobile devices or slower connections.

The tiling system works by creating multiple versions of the source image at different resolutions (a pyramid) and dividing each resolution level into a grid of small tiles. For example, a 16,000×12,000 pixel image might be stored as: (1) a 1×1 tile showing the entire image at low resolution, (2) a 2×2 grid of tiles at medium resolution, (3) a 4×4 grid at higher resolution, continuing up to (4) perhaps a 64×48 grid of tiles containing the full-resolution pixels. When a viewer displays this image, it only requests the specific tiles needed for the current viewport and zoom level. If you're looking at the whole image, it loads the small low-resolution tiles; when you zoom to read fine details, it loads high-resolution tiles only for that visible region.

This is the same technology used by [Google Maps](https://en.wikipedia.org/wiki/Google_Maps) (you don't download the entire map of the world to view your neighborhood), [Zoomify](https://en.wikipedia.org/wiki/Zoomify), Microsoft's [Deep Zoom](https://en.wikipedia.org/wiki/Deep_Zoom), and other web mapping applications. The IIIF [Image API](https://iiif.io/api/image/) standardizes how to request these tiles: rather than each institution implementing a proprietary tiling scheme, all IIIF image servers respond to the same URL patterns for requesting specific regions, sizes, and zoom levels.

When Telar generates IIIF tiles from your local images using [libvips](https://www.libvips.org/) (a high-performance image processing library), it creates this pyramid structure automatically, typically producing thousands of individual tile images from a single source photograph or scan. These tiles are then stored in your site's assets and served statically—no special image server required. This gives your own materials the same smooth pan-and-zoom experience as images hosted by major museums and libraries.

**Learn more:**
- [IIIF Image API specification](https://iiif.io/api/image/3.0/)
- [Deep Zoom on Wikipedia](https://en.wikipedia.org/wiki/Deep_Zoom)
- [How IIIF Image API works - technical overview](https://iiif.io/api/image/3.0/#image-request-parameters)
- [libvips - the image processing library Telar uses](https://www.libvips.org/)
- [Tiled web map on Wikipedia](https://en.wikipedia.org/wiki/Tiled_web_map)
