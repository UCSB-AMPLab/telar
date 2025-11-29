---
title: "Uso de múltiples imágenes"
---

En este paso pasamos de `atlas-allegory` a `leviathan` en la columna **object**. Puedes usar ambos tipos:

**Imágenes IIIF** (como la alegoría del Atlas):
- `source_url` se llena con la URL del manifiesto IIIF
- La imagen está alojada por la institución (Princeton, British Library, etc.)
- No necesitas archivo local

**Imágenes autoalojadas** (como este frontispicio del Leviatán):
- `source_url` vacío
- Archivo en `components/images/objects/leviathan.jpg`
- Telar genera las teselas automáticamente en el *build*

**Argumentos comparativos:**

Cobo usa la imagen del Leviatán para contrastar: Hobbes representa al gobernante como **contenedor** (el cuerpo del rey contiene a todos los súbditos), mientras que el mapa del imperio español lo muestra como **marginal** (apretado al fondo). La comparación refuerza su tesis sobre conexión frente a territorio.
