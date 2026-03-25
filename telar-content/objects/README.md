# Objects

**[Versión en español abajo](#objetos)** | **[English version](#objects)**

This folder contains the source files for your Telar objects — images and PDFs displayed via the IIIF protocol.

## Supported formats

JPEG (.jpg, .jpeg), TIFF (.tif, .tiff), PNG (.png), WebP (.webp), HEIC (.heic, .heif), PDF (.pdf), MP3 (.mp3), OGG (.ogg), M4A (.m4a)

High-resolution images work best. PDFs are rendered to page images at build time. Audio files are processed into peak data for waveform rendering.

## Workflow

1. Place high-resolution images or PDFs here
2. Run `python3 scripts/generate_iiif.py` to create IIIF tiles (automatic on GitHub)
3. Reference objects by filename (without extension) in `objects.csv`

## File naming

Source filenames should match the `object_id` in your objects CSV:

```
telar-content/objects/example-map.jpg  →  object_id: example-map
```

---
---

# Objetos

**[Versión en español](#objetos)** | **[English version above](#objects)**

Esta carpeta contiene los archivos fuente de tus objetos Telar — imágenes y PDFs que se muestran mediante el protocolo IIIF.

## Formatos compatibles

JPEG (.jpg, .jpeg), TIFF (.tif, .tiff), PNG (.png), WebP (.webp), HEIC (.heic, .heif), PDF (.pdf), MP3 (.mp3), OGG (.ogg), M4A (.m4a)

Las imágenes en alta resolución funcionan mejor. Los PDFs se renderizan a imágenes de página durante la compilación. Los archivos de audio se procesan para generar datos de picos (*peaks*) para la visualización de ondas.

## Flujo de trabajo

1. Coloca imágenes en alta resolución o PDFs aquí
2. Ejecuta `python3 scripts/generate_iiif.py` para generar mosaicos IIIF (automático en GitHub)
3. Referencia los objetos por nombre de archivo (sin extensión) en `objects.csv`

## Nombres de archivo

Los nombres de archivo deben coincidir con el `object_id` / `id_objeto` en tu CSV de objetos:

```
telar-content/objects/mapa-ejemplo.jpg  →  id_objeto: mapa-ejemplo
```
