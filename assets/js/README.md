# Telar JavaScript

This directory mixes hand-maintained source, one build artifact, and one vendored library. This file says which is which, what each script does, and how to rebuild.

## Generated — do not edit

| File | What it is |
|---|---|
| `telar-story.js` | The story viewer, bundled by esbuild from the ES modules in `telar-story/`. Carries a `GENERATED FILE` banner and is marked `linguist-generated` in `.gitattributes`. Any edit made here is lost on the next build. |
| `telar-story.js.map` | Source map for the bundle, for browser devtools. |

To change the story viewer, edit the modules in `telar-story/` and rebuild:

```
npm install        # once, to get esbuild
npm run build:js   # rebuilds telar-story.js and its source map
npm run test:js    # runs the JS test suite (vitest)
```

The bundle is committed so that Telar sites build without a Node toolchain — GitHub Pages and the standard Jekyll workflow never run esbuild. The cost of that convenience is this directory's biggest reading trap: the bundle looks like source. It is not; the source is `telar-story/`.

## Source — the story viewer (`telar-story/`)

ES modules, one responsibility each, bundled into `telar-story.js`. Loaded only by the story layout. Start reading at `main.js` (entry point and initialization order); each module's header comment explains its role. The scroll engine is Lenis-based (`scroll-engine.js`); cards and viewer plates are managed by `card-pool.js`.

## Source — standalone page scripts

Loaded directly by individual layouts via `<script>` tags, not bundled:

| File | What it does | Loaded by |
|---|---|---|
| `telar.js` | Site-wide panels and glossary behavior — the small layer every page loads. | default layout (all pages) |
| `objects-filter.js` | Browse, facet filtering, and lunr search on the objects index page. | objects-index layout |
| `share-panel.js` | Share-link and embed-code controls in the share panel, for stories and the homepage. | story and default layouts |
| `story-unlock.js` | Client-side decryption overlay for protected stories (AES-GCM via Web Crypto). | story layout |
| `embed.js` | Detects iframe embedding and trims site chrome down to the story itself. | story layout |
| `widgets.js` | Carousel initialization for content widgets (tabs and accordions are pure Bootstrap). | story layout |
| `telar-icons.js` | Runtime inline-SVG icon helper (Lucide paths). Currently loaded by no layout — the icons it served are now inlined directly in templates. Candidate for removal. | nothing |

## Vendored

| File | What it is |
|---|---|
| `lunr.min.js` | [Lunr](https://lunrjs.com/) client-side search library, used by `objects-filter.js`. Vendored rather than CDN-loaded so search works offline. See `NOTICE` for license. |

## Conventions

Every source file opens with a narrative header comment explaining what it is responsible for and why the non-obvious choices were made, and carries an `@version` footer naming the release it last changed in. The generated bundle is exempt — its banner and `.gitattributes` entry are its documentation.
