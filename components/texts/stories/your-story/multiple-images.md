---
title: "Using Multiple Images"
---

This step switches from `atlas-allegory` to `leviathan` in the **object** column. You can use both:

**IIIF images** (like the Atlas allegory):
- `source_url` populated with IIIF manifest URL
- Image hosted by institution (Princeton, British Library, etc.)
- No local file needed

**Self-hosted images** (like this Hobbes frontispiece):
- `source_url` empty
- Image file in `components/images/objects/leviathan.jpg`
- Telar generates tiles automatically at build time

**Comparative arguments:**

Cobo uses the Leviathan image to show contrast: Hobbes depicts the ruler as **container** (the king's body contains all subjects), while the Spanish empire map depicts the ruler as **marginal** (squeezed into the bottom). The comparison strengthens her thesis about connection vs territory.
