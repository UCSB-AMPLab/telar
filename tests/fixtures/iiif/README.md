# IIIF Manifest Fixtures

These are hand-authored minimal IIIF Presentation API manifests. NOT derived from any
external server. Used by `tests/js/iiif-manifest.test.js` to verify the four
exported parser functions in `assets/js/telar-story/iiif-manifest.js`. URLs use
the reserved `example.invalid` TLD (RFC 2606) so fixtures never accidentally
hit the network.

## Files

| Fixture | Exercises parser branch |
|---------|-------------------------|
| `manifest-v2.json` | `extractV2Pages` → `images[0].resource.service["@id"]` chain on both canvases |
| `manifest-v3.json` | `extractV3Pages` → `body.service[0].id` chain (canvas 1) AND `body.id` Image-API-URL → `deriveInfoJsonFromImageUrl` derive branch (canvas 2) |

Both files contain two canvases each so the parsers' loop behaviour is
exercised (not just a single-page short-circuit).

## Provenance

Authored by hand against the IIIF Presentation API v2 and v3 spec field
chains. Minimal — only the fields that the parsers
index into are present, plus `@context`/`id`/`type`/`label` to keep each
manifest syntactically a valid IIIF document.

`tests/fixtures/iiif/manifest-v2-no-service.json` (a fallback-branch fixture
for `extractV2Pages`'s `resource["@id"]` path) is intentionally NOT created
here — add it only if the parser test enumeration needs it.
