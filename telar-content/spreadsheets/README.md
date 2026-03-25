# Spreadsheets

**[Versión en español abajo](#hojas-de-cálculo)** | **[English version](#spreadsheets)**

CSV files that define the content and structure of your Telar site.

> **Google Sheets users:** If you use the Google Sheets integration, these CSVs are fetched automatically — you do not need to edit them manually.

## Files

| File | Purpose |
|---|---|
| `project.csv` | Site settings and story list |
| `objects.csv` | Object catalog (images, IIIF manifests) |
| `glossary.csv` | Glossary term definitions |
| Story CSVs | Step-by-step narrative structure |

## Workflow

1. Edit CSVs directly, or fetch from Google Sheets
2. Run `python3 scripts/csv_to_json.py` to generate JSON
3. Run `bundle exec jekyll build` to build the site

Steps 2–3 happen automatically on GitHub.

## Story CSV columns

`step`, `object`, `x`, `y`, `zoom`, `page`, `question`, `answer`, `layer1_button`, `layer1_content`, `layer2_button`, `layer2_content`, `clip_start`, `clip_end`, `loop`, `alt_text`

Markdown files referenced in content columns should be stored in `telar-content/texts/stories/`.

---
---

# Hojas de cálculo

**[Versión en español](#hojas-de-cálculo)** | **[English version above](#spreadsheets)**

Archivos CSV que definen el contenido y la estructura de tu sitio Telar.

> **Usuarios de Google Sheets:** Si usas la integración con Google Sheets, estos CSVs se obtienen automáticamente — no necesitas editarlos manualmente.

## Archivos

| Archivo | Propósito |
|---|---|
| `project.csv` | Configuración del sitio y lista de historias |
| `objects.csv` | Catálogo de objetos (imágenes, manifiestos IIIF) |
| `glossary.csv` | Definiciones del glosario |
| CSVs de historias | Estructura narrativa paso a paso |

## Flujo de trabajo

1. Edita los CSVs directamente, o descárgalos de Google Sheets
2. Ejecuta `python3 scripts/csv_to_json.py` para generar JSON
3. Ejecuta `bundle exec jekyll build` para compilar el sitio

Los pasos 2–3 se ejecutan automáticamente en GitHub.

## Columnas del CSV de historias

`paso`, `objeto`, `x`, `y`, `zoom`, `página`, `pregunta`, `respuesta`, `boton_capa1`, `contenido_capa1`, `boton_capa2`, `contenido_capa2`, `inicio_clip`, `fin_clip`, `bucle`, `texto_alt`

Los archivos markdown referenciados en las columnas de contenido deben estar en `telar-content/texts/stories/`.
