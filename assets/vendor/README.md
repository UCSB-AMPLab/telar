# Vendored third-party assets

## Why this directory exists

Telar vendors third-party JavaScript bundles instead of loading them
from a CDN. This keeps the framework's runtime aligned with the
minimal-computing principle behind the project: fewer external
dependencies at runtime, no CDN single-point-of-failure, and version
pinning that holds regardless of CDN behaviour.

The convention is: third-party bundles live under `assets/vendor/` and
are documented in this README with package, source URL, download date,
and SHA-256 digest. Most are loaded via `_layouts/*.html` `<script>`
tags with `relative_url` (e.g. OpenSeadragon). WaveSurfer is the
exception: it is loaded lazily at runtime by `loadWaveSurferAPI()`
(in `assets/js/telar-story/audio-card.js`), which injects `<script>`
tags pointing at these vendored paths only when an audio card first
appears, so story pages without audio never download it.

## Files

| file | package | version | source | download_date (UTC) | sha256 |
|---|---|---|---|---|---|
| `openseadragon.min.js` | [`openseadragon`](https://github.com/openseadragon/openseadragon) | 6.0.2 | [npm tarball](https://registry.npmjs.org/openseadragon/-/openseadragon-6.0.2.tgz), `build/openseadragon/openseadragon.min.js` | 2026-05-24 | `c45c37502ee828c9d68d1c16142b4536fe54814c75c67ab3170f1a095927ed46` |
| `wavesurfer/wavesurfer.min.js` | [`wavesurfer.js`](https://github.com/katspaugh/wavesurfer.js) | 7.12.7 | `npm pack wavesurfer.js@7.12.7`, `dist/wavesurfer.min.js` | 2026-06-04 | `e5a6b90136355fee00d54ebc012d28f9f047f4245a56c7fd1e61671575ce1e4f` |
| `wavesurfer/plugins/regions.min.js` | [`wavesurfer.js`](https://github.com/katspaugh/wavesurfer.js) | 7.12.7 | `npm pack wavesurfer.js@7.12.7`, `dist/plugins/regions.min.js` | 2026-06-04 | `175468b540dfbe4d88ca2560b197881648ea41bc509568a5aca2331a19e86145` |

## Verification procedure

### OpenSeadragon

To confirm the vendored bundle has not been tampered with, re-run the
download against the canonical npm artefact and compare digests. From
a clean temporary directory:

1. `npm pack openseadragon@6.0.2`
2. `tar -xzf openseadragon-6.0.2.tgz`
3. `shasum -a 256 package/build/openseadragon/openseadragon.min.js` (macOS)
   or `sha256sum package/build/openseadragon/openseadragon.min.js` (Linux)

The hex digest must match the value recorded in the Files table above
exactly. As an additional sanity check, confirm the vendored file's
first line contains the upstream UMD header:

```
head -c 200 assets/vendor/openseadragon.min.js
# expected to contain: //! openseadragon 6.0.2
```

If the digests do not match, do not deploy — re-vendor from a fresh
`npm pack` invocation and re-record the digest here.

### WaveSurfer

1. `npm pack wavesurfer.js@7.12.7`
2. `tar -xzf wavesurfer.js-7.12.7.tgz`
3. `shasum -a 256 package/dist/wavesurfer.min.js package/dist/plugins/regions.min.js` (macOS)
   or `sha256sum ...` (Linux)

Both hex digests must match the values recorded in the Files table
above exactly. As an additional sanity check, both files are UMD —
confirm the core sets the global and the plugin augments it:

```
head -c 200 assets/vendor/wavesurfer/wavesurfer.min.js
# expected to contain: .WaveSurfer=e()
head -c 320 assets/vendor/wavesurfer/plugins/regions.min.js
# expected to contain: t.WaveSurfer.Regions=e()
```

If the digests do not match, do not deploy — re-vendor from a fresh
`npm pack` invocation and re-record the digest here.
