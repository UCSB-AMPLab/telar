# Vendored third-party assets

## Why this directory exists

Telar vendors third-party JavaScript bundles instead of loading them
from a CDN. This keeps the framework's runtime aligned with the
minimal-computing principle behind the project: fewer external
dependencies at runtime, no CDN single-point-of-failure, and version
pinning that holds regardless of CDN behaviour.

The convention is: third-party bundles live
under `assets/vendor/`, are loaded via `_layouts/*.html` `<script>`
tags with `relative_url`, and are documented in this README with
package, source URL, download date, and SHA-256 digest.

## Files

| file | package | version | source | download_date (UTC) | sha256 |
|---|---|---|---|---|---|
| `openseadragon.min.js` | [`openseadragon`](https://github.com/openseadragon/openseadragon) | 6.0.2 | [npm tarball](https://registry.npmjs.org/openseadragon/-/openseadragon-6.0.2.tgz), `build/openseadragon/openseadragon.min.js` | 2026-05-24 | `c45c37502ee828c9d68d1c16142b4536fe54814c75c67ab3170f1a095927ed46` |

## Verification procedure

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
