# Texts

**[Versión en español abajo](#textos)** | **[English version](#texts)**

Markdown files with narrative content for your Telar site — story panels, glossary definitions, and static pages.

## Structure

```
texts/
├── stories/          - Story panel content
│   └── your-story/   - Organized by story (subfolder name = story ID)
│       └── panel.md
├── glossary/         - Glossary definitions
│   └── term.md
└── pages/            - Static pages
    └── about.md
```

## Markdown format

Each file needs YAML frontmatter with a title:

```markdown
---
title: "Your Title Here"
---

Your content here. Supports **bold**, *italic*, [links](https://telar.org),
lists, and other markdown formatting.
```

## How files are referenced

- **Story panels:** Enter the path in the `layer1_content` or `layer2_content` column of your story CSV (e.g., `your-story/panel.md`).
- **Glossary:** Enter the filename in the `definition` column of `glossary.csv` (e.g., `term.md`), or write definitions directly in the CSV.
- **Pages:** Processed automatically by `generate_collections.py`.

## Glossary links in stories

Link to glossary terms from story markdown using wiki syntax:

```markdown
The [[viceroyalty]] was established during the [[colonial-period|colonial era]].
```

- `[[term_id]]` — displays the term ID as link text
- `[[term_id|display text]]` — displays custom text

---
---

# Textos

**[Versión en español](#textos)** | **[English version above](#texts)**

Archivos markdown con contenido narrativo para tu sitio Telar — paneles de historias, definiciones del glosario y páginas estáticas.

## Estructura

```
texts/
├── stories/               - Contenido de paneles de historias
│   └── tu-historia/       - Organizados por historia (nombre de subcarpeta = ID de historia)
│       └── panel.md
├── glossary/              - Definiciones del glosario
│   └── termino.md
└── pages/                 - Páginas estáticas
    └── about.md
```

## Formato markdown

Cada archivo necesita metadatos YAML con un título:

```markdown
---
title: "Tu título aquí"
---

Tu contenido aquí. Admite **negritas**, *cursivas*, [enlaces](https://telar.org),
listas y otros formatos de markdown.
```

## Cómo se referencian los archivos

- **Paneles de historias:** Ingresa la ruta en la columna `contenido_capa1` o `contenido_capa2` de tu CSV de historia (ej. `tu-historia/panel.md`).
- **Glosario:** Ingresa el nombre del archivo en la columna `definición` de `glossary.csv` (ej. `termino.md`), o escribe las definiciones directamente en el CSV.
- **Páginas:** Se procesan automáticamente con `generate_collections.py`.

## Enlaces de glosario en historias

Enlaza a términos del glosario desde el markdown de historias usando sintaxis wiki:

```markdown
El [[virreinato]] se estableció durante la [[periodo-colonial|época colonial]].
```

- `[[id_termino]]` — muestra el ID del término como texto del enlace
- `[[id_termino|texto personalizado]]` — muestra texto personalizado
