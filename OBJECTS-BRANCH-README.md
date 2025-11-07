# Objects for v0.5.0

This branch contains prepared object metadata and renamed images for the full Paisajes Chapter 1 demo content, to be integrated in v0.5.0 when the demo content pipeline is implemented.

## What's here:

### Object Images (components/images/objects/)
All object images renamed from obj* to descriptive names:
- bogota-1614-painting.jpg (was obj2)
- recopilacion-leyes-1681-audiencias.jpg (was obj3)
- maldonado-francisco-portrait-18c.jpg (was obj4)
- recopilacion-leyes-1681-encomiendas.jpg (was obj5)
- guaman-poma-1615-santa-fe.jpg (was obj7)
- kogi-loom-1978.png (was obj8)
- venice-1534-west-indies-map.jpg (was obj9)
- medieval-1262-1300-world-map.jpg (was obj10)
- babylonian-6c-bce-world-map.png (was obj11)
- codex-quetzalecatzin-1593.jpg (was obj12)
- siberian-1860-1870-sealskin-map.jpg (was obj13)
- greenland-inuit-1926-map.jpg (was obj14)
- maldonado-antonio-portrait-18c.jpeg (was obj18)
- maldonado-family-tree-1674.jpg (was obj19)

### Object Metadata
`components/structures/new-objects.csv` contains complete metadata for all 14 objects with titles, descriptions, creators, dates, sources, etc.

### Supporting Images (components/images/additional/paisajes/)
- covarrubias-1611-audiencia.png
- covarrubias-1611-mapa.jpg
- covarrubias-1611-mayorazgo.png
- bogota-savanna-modern-map.jpg

## v0.5.0 Integration Plan

When implementing the demo content pipeline:
1. These objects will be part of the demo content repository
2. IIIF tiles will be hosted externally at neogranadina.org/telar-demo-materials
3. Object metadata will be served from demo repo, not main template
4. Images will use external URLs in iiif_manifest field
5. Demo stories will reference these objects

## v0.4.0 Approach

For v0.4.0 widget testing, we're using simpler approach:
- Widget examples reference external image URLs from paisajescoloniales.com
- Or use the supporting images from components/images/additional/paisajes/
- No IIIF objects needed for basic widget functionality testing
