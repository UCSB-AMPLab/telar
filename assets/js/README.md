# Telar JavaScript

This directory mixes hand-maintained source, one build artifact, and one vendored library. This file says which is which, what each script does, and how to rebuild.

## Generated — do not edit

| File | What it is |
|---|---|
| `telar-story.js` | The story viewer, bundled by esbuild from the ES modules in `telar-story/`. Carries a `GENERATED FILE` banner and is marked `linguist-generated` in `.gitattributes`. Any edit made here is lost on the next build. |
| `telar-story.js.map` | Source map for the bundle, for browser devtools. |
| `object-page.js` | The object page, bundled by esbuild from the ES modules in `object-page/`. Same banner, same `.gitattributes` entry, same rule. |
| `object-page.js.map` | Source map for the object-page bundle. |
| `home-page.js` | The home page's card thumbnails, bundled by esbuild from `iiif-thumbnails/home.js`. Same banner, same `.gitattributes` entry, same rule. |
| `home-page.js.map` | Source map for the home-page bundle. |
| `objects-index-page.js` | The objects index's card thumbnails, bundled by esbuild from `iiif-thumbnails/objects-index.js`. Same banner, same `.gitattributes` entry, same rule. |
| `objects-index-page.js.map` | Source map for the objects-index bundle. |
| `iiif-url-warning.js` | The IIIF URL mismatch diagnostic, bundled by esbuild from `iiif-url-warning/main.js`. Same banner, same `.gitattributes` entry, same rule. |
| `iiif-url-warning.js.map` | Source map for the URL-warning bundle. |
| `objects-filter.js` | The objects gallery's browse, filter, search and sort, bundled by esbuild from `objects-filter/main.js`. Same banner, same `.gitattributes` entry, same rule. |
| `objects-filter.js.map` | Source map for the objects-filter bundle. |
| `share-panel.js` | The share-link and embed-code controls, bundled by esbuild from `share-panel/main.js`. Same banner, same `.gitattributes` entry, same rule. |
| `share-panel.js.map` | Source map for the share-panel bundle. |

To change the story viewer, the object page, the index pages' thumbnails, the URL warning, the gallery filter or the share panel, edit the modules in `telar-story/`, `object-page/`, `iiif-thumbnails/`, `iiif-url-warning/`, `objects-filter/` or `share-panel/` and rebuild:

```
npm install        # once, to get esbuild
npm run build:js   # rebuilds every bundle and its source map
npm run test:js    # runs the JS test suite (vitest)
```

The bundle is committed so that Telar sites build without a Node toolchain — GitHub Pages and the standard Jekyll workflow never run esbuild. The cost of that convenience is this directory's biggest reading trap: the bundle looks like source. It is not; the source is `telar-story/`.

## Source — the story viewer (`telar-story/`)

ES modules, one responsibility each, bundled into `telar-story.js`. Loaded only by the story layout. Start reading at `main.js` (entry point and initialization order); each module's header comment explains its role. The scroll engine is Lenis-based (`scroll-engine.js`); cards and viewer plates are managed by `card-pool.js`.

## Source — the object page (`object-page/`)

ES modules bundled into `object-page.js`, loaded only by the object layout. `main.js` reads the JSON block the layout writes (`#telar-object-data`: media type, object id, source URLs, base URL and the language strings) and dispatches on the media type: `image-object.js` (the IIIF viewer, imported from `telar-story/iiif-viewer.js`, and the coordinate panel), `video-object.js` (embed, clip picker, copy-embed button), `audio-object.js` (waveform player and clip region), with `clip-panel.js` and `copy-feedback.js` shared between them. The three helpers the layout still loads as classic scripts — `object-theme.js`, `video-embed.js`, `wavesurfer-loader.js` — publish the globals these modules call.

## Source — the index pages' thumbnails (`iiif-thumbnails/`)

ES modules with two entry points, one per layout: `home.js` bundles into `home-page.js` for the index layout, `objects-index.js` into `objects-index-page.js` for the objects-index layout. Each reads the JSON block its layout writes (`#telar-home-data`, `#telar-objects-index-data`) and wires the shared resolver, `resolve.js` -- manifest (2.1/3.0) or info.json to best thumbnail URL, plus explicit-URL upgrading -- into that page's cards. `explicit-thumbnails.js` is the upgrade-with-fallback both pages apply to `<img class="iiif-thumbnail">`.

## Source — the IIIF URL warning (`iiif-url-warning/`)

`main.js` bundles into `iiif-url-warning.js`, loaded by `_includes/iiif-url-warning.html` on the home page. It reads the JSON block that include writes (`#telar-iiif-warning-data`: the objects.json and IIIF manifest base paths, plus the singular/plural affected-image strings), compares the base URL baked into each locally tiled object's manifest against the address the page is served at, and reveals the include's hidden banner when they differ -- with the `generate_iiif.py` command for local development, or the suggested `url:`/`baseurl:` values for production. The document, fetch and location are injectable parameters, which is what makes the check testable without stubbing globals.

## Source — the objects gallery filter (`objects-filter/`)

`main.js` bundles into `objects-filter.js`, loaded by the objects-index layout when `collection_interface.browse_and_search` is on, after the vendored `lunr.min.js` it reads as a global. `createObjectsFilter()` builds one gallery's filter over a document: it fetches `search-data.json` (facet counts and object metadata, generated by `scripts/telar/search.py`), fills the sidebar's five facet sections, and shows or hides `.collection-item` cards by their `data-*` attributes -- OR within a facet, AND across facets -- alongside a Lunr query debounced at 250ms and a title/year sort. `matching.js` holds the two predicates one card is judged by, `search-index.js` the base URL and the Lunr index, `escape.js` the escaping the facet options and chips need. The document, fetch, Lunr and location are injectable parameters, which is what makes the gallery testable without stubbing globals.

## Source — the share panel (`share-panel/`)

`main.js` bundles into `share-panel.js`, loaded by the default layout on every page it serves and by the story layout. `createSharePanel()` builds one panel's controls over a document: it fills the share link, the deep-link "this view" link and the whole-site link, generates the embed `<iframe>` from the preset and dimension controls, and drives the story selector `_layouts/index.html` feeds through its `#telar-stories-data` block. `_includes/share-panel.html` renders one of two branches -- the story page's, with the protected-story key toggle, or the one every other page gets, with the selector -- and the panel reads whichever ids are present. `warnings.js` holds the decision behind the four warning ids -- which of the two pairs the current state raises -- and the showing of one. The document, window, navigator and alert are injectable parameters, which is what makes the panel testable without stubbing globals.

## Source — standalone page scripts

Loaded directly by individual layouts via `<script>` tags, not bundled:

| File | What it does | Loaded by |
|---|---|---|
| `telar.js` | Site-wide panels and glossary behavior — the small layer every page loads. | default layout (all pages) |
| `story-unlock.js` | Client-side decryption overlay for protected stories (AES-GCM via Web Crypto). | story layout |
| `embed.js` | Detects iframe embedding and trims site chrome down to the story itself. | story layout |
| `widgets.js` | Carousel initialization for content widgets (tabs and accordions are pure Bootstrap). | story layout |
| `katex-loader.js` | Pulls KaTeX in from the CDN once per page load, and only for a story that carries LaTeX. | story layout |
| `christmas-tree-decorator.js` | Prefixes every rendered warning heading with a tree emoji while Christmas tree mode is on, so the synthetic warnings read as fixtures. | story layout |

## Vendored

| File | What it is |
|---|---|
| `lunr.min.js` | [Lunr](https://lunrjs.com/) client-side search library, used by the objects gallery filter. Vendored rather than CDN-loaded so search works offline. See `NOTICE` for license. |

## Conventions

Every source file opens with a narrative header comment explaining what it is responsible for and why the non-obvious choices were made, and carries an `@version` footer naming the release it last changed in. The generated bundle is exempt — its banner and `.gitattributes` entry are its documentation.
