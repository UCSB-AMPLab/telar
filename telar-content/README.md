# Telar Content

**[Versión en español abajo](#contenido-telar)** | **[English version](#telar-content)**

This directory contains all the **source content** for your Telar site — objects (images and documents), text content, and data spreadsheets.

## Directory Structure

### objects/

High-resolution images, PDF documents, and audio recordings. Images and PDFs are displayed using IIIF; audio files are rendered as waveforms. Supported formats: JPG, PNG, TIFF, WebP, HEIC, PDF, MP3, OGG, M4A. See [objects/README.md](objects/README.md) for details.

### spreadsheets/

CSV files that define your site's content and structure: `project.csv` (site settings), `objects.csv` (object catalog), and story CSVs (narrative steps). If you use Google Sheets, these are fetched automatically. See [spreadsheets/README.md](spreadsheets/README.md) for details.

### texts/

Markdown files containing narrative text for story panels, glossary definitions, and static pages. Referenced by path in your story and glossary spreadsheets. See [texts/README.md](texts/README.md) for details.

## Workflow

1. **Add content** — Place images, PDFs, or audio in `objects/`, text in `texts/`, update CSVs in `spreadsheets/`
2. **Process** — Run `python3 scripts/csv_to_json.py`
3. **Generate tiles** — Run `python3 scripts/generate_iiif.py`
4. **Process audio** — Run `python3 scripts/process_audio.py` (only if you have audio objects)
5. **Build** — Run `bundle exec jekyll build`

On GitHub, steps 2–4 happen automatically via GitHub Actions.

## More info

- **Documentation:** [telar.org/docs](https://telar.org/docs)
- **Issues:** [GitHub Issues](https://github.com/UCSB-AMPLab/telar/issues)

---
---

# Contenido Telar

**[Versión en español](#contenido-telar)** | **[English version above](#telar-content)**

Esta carpeta contiene todo el **contenido fuente** de tu sitio Telar — objetos (imágenes y documentos), contenido de texto y hojas de cálculo de datos.

## Estructura de carpetas

### objects/

Imágenes en alta resolución, documentos PDF y grabaciones de audio. Las imágenes y PDFs se muestran mediante IIIF; los archivos de audio se visualizan como ondas. Formatos compatibles: JPG, PNG, TIFF, WebP, HEIC, PDF, MP3, OGG, M4A. Consulta [objects/README.md](objects/README.md) para más detalles.

### spreadsheets/

Archivos CSV que definen el contenido y la estructura de tu sitio: `project.csv` (configuración), `objects.csv` (catálogo de objetos) y CSVs de historias (pasos narrativos). Si usas Google Sheets, estos se obtienen automáticamente. Consulta [spreadsheets/README.md](spreadsheets/README.md) para más detalles.

### texts/

Archivos markdown con texto narrativo para los paneles de historias, definiciones del glosario y páginas estáticas. Se referencian por ruta en tus hojas de cálculo de historias y glosario. Consulta [texts/README.md](texts/README.md) para más detalles.

## Flujo de trabajo

1. **Agrega contenido** — Coloca imágenes, PDFs o audio en `objects/`, texto en `texts/`, actualiza los CSVs en `spreadsheets/`
2. **Procesa** — Ejecuta `python3 scripts/csv_to_json.py`
3. **Genera mosaicos** — Ejecuta `python3 scripts/generate_iiif.py`
4. **Procesa audio** — Ejecuta `python3 scripts/process_audio.py` (solo si tienes objetos de audio)
5. **Compila** — Ejecuta `bundle exec jekyll build`

En GitHub, los pasos 2–4 se ejecutan automáticamente mediante GitHub Actions.

## Más información

- **Documentación:** [telar.org/guia](https://telar.org/guia)
- **Problemas:** [GitHub Issues](https://github.com/UCSB-AMPLab/telar/issues)
