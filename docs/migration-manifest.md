# Migration Manifest Schema — v1

Reference for authors writing `migration.json` files for Telar framework releases. This file is intended for the framework repo (`docs/migration-manifest.md`) so release authors can reference it.

## Purpose

Each Telar framework release includes a `migration.json` file that declares user-content transformations the Telar Compositor applies during upgrades. The compositor already handles framework file replacement via tree-diff — the manifest handles everything else: config changes, CSV column additions, file cleanup, and manual steps.

## File Location

- Attach `migration.json` as a **release asset** on the GitHub Release.
- The compositor fetches it via the GitHub Releases API alongside the release body.

## Schema

```json
{
  "schema_version": 1,
  "from_version": "1.1.0",
  "to_version": "1.2.0",
  "description": "Human-readable summary of this migration",
  "operations": [],
  "manual_steps": {}
}
```

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | integer | Yes | Always `1` for this schema version |
| `from_version` | string | Yes | Version this migration upgrades FROM (without `v` prefix) |
| `to_version` | string | Yes | Version this migration upgrades TO (without `v` prefix) |
| `description` | string | Yes | One-line summary of what changed |
| `operations` | array | Yes | Ordered list of transform operations (can be empty) |
| `manual_steps` | object | Yes | Bilingual manual steps shown after upgrade |

### Version Strings

Use the version number **without** the `v` prefix and **without** `-beta` unless the version genuinely has a prerelease suffix:

- `"1.1.0"` (not `"v1.1.0"`)
- `"0.9.0-beta"` (prerelease suffix preserved)

## Operations

Operations run **sequentially** in array order. Each operation has a `type` field and type-specific parameters.

### config_add_field

Add a new key to `_config.yml`.

```json
{
  "type": "config_add_field",
  "key": "collection_mode",
  "value": "false",
  "after_key": "telar_language",
  "comment": "Set to true for collection-first homepage",
  "skip_if_exists": true
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `key` | string | Yes | The config key to add |
| `value` | string | Yes | The default value |
| `after_key` | string | Yes | Insert after this existing key |
| `comment` | string | No | Appended as `# comment` after the value |
| `skip_if_exists` | boolean | No | Default `true` — no-op if key already present |

### config_update_value

Change an existing config value (only if it still has the old default).

```json
{
  "type": "config_update_value",
  "key": "max_viewer_cards",
  "old_value": "10",
  "new_value": "8"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `key` | string | Yes | The config key to update |
| `old_value` | string | Yes | Only apply if current value matches this |
| `new_value` | string | Yes | The new value |

### config_rename_field

Rename a config key, preserving its value.

```json
{
  "type": "config_rename_field",
  "old_key": "testing",
  "new_key": "development-features"
}
```

### csv_add_column

Add a column to CSV files. Column names are bilingual — the compositor resolves using `telar_language` from the site's `_config.yml`.

```json
{
  "type": "csv_add_column",
  "file_glob": "**/project.csv",
  "column": { "en": "show_sections", "es": "mostrar_secciones" },
  "default": "",
  "after": { "en": "answer", "es": "respuesta" }
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_glob` | string | Yes | Glob pattern to find the CSV |
| `column` | `{ en, es }` | Yes | Bilingual column name |
| `default` | string | Yes | Value for existing rows (use `""` for blank) |
| `after` | `{ en, es }` | Yes | Bilingual name of column to insert after |

### csv_rename_column

Rename a CSV column header.

```json
{
  "type": "csv_rename_column",
  "file_glob": "**/objects.csv",
  "old_name": { "en": "iiif_manifest", "es": "iiif_manifest" },
  "new_name": { "en": "source_url", "es": "url_fuente" }
}
```

### file_delete

Delete files from the repository.

```json
{
  "type": "file_delete",
  "paths": ["assets/js/scrollama.min.js", "assets/js/openseadragon.min.js"]
}
```

### gitignore_add

Add entries to `.gitignore`.

```json
{
  "type": "gitignore_add",
  "patterns": ["_data/collections/", "_site/"],
  "section_comment": "Generated files"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `patterns` | string[] | Yes | Gitignore patterns to add |
| `section_comment` | string | No | `# comment` header above the patterns |

Patterns are only added if not already present.

### regex_replace

Find-and-replace across files matching a glob.

```json
{
  "type": "regex_replace",
  "file_glob": "**/*.md",
  "search": "components/images/(objects|additional)/",
  "replace": "components/images/"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_glob` | string | Yes | Files to process |
| `search` | string | Yes | JavaScript-flavoured regex pattern |
| `replace` | string | Yes | Replacement string (supports `$1`, `$2` groups) |

### create_directory

Create a directory (and any missing parents).

```json
{
  "type": "create_directory",
  "path": "components/texts/pages"
}
```

## Manual Steps

Bilingual manual steps shown after upgrade. These are informational — they don't block the upgrade.

```json
{
  "manual_steps": {
    "en": [
      {
        "description": "Markdown text describing features and any manual actions",
        "doc_url": "https://telar.org/docs"
      }
    ],
    "es": [
      {
        "description": "Texto en markdown describiendo las novedades",
        "doc_url": "https://telar.org/guia"
      }
    ]
  }
}
```

Both `en` and `es` arrays are required. Each entry has:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | string | Yes | Markdown text (rendered in the compositor post-upgrade UI) |
| `doc_url` | string | No | Link to documentation |

## Example: v1.1.0 to v1.2.0

```json
{
  "schema_version": 1,
  "from_version": "1.1.0",
  "to_version": "1.2.0",
  "description": "Story Structure & UX — title card TOC, section cards, ordinal removal",
  "operations": [
    {
      "type": "csv_add_column",
      "file_glob": "**/project.csv",
      "column": { "en": "show_sections", "es": "mostrar_secciones" },
      "default": "",
      "after": { "en": "answer", "es": "respuesta" }
    }
  ],
  "manual_steps": {
    "en": [
      {
        "description": "**New features available after upgrade:**\n\n- **Title card table of contents**: Add `show_sections: yes` to a story row in project.csv to display a navigable TOC on its title card, linking to each section card in the story.\n\n- **Section cards**: Unchanged from v1.1.0 — leave the object column empty for a step to create a section break.\n\n- **Ordinal numbers removed**: Story cards no longer display auto-generated numbers. The homepage uses the first letter of each story title instead.",
        "doc_url": "https://telar.org/docs"
      }
    ],
    "es": [
      {
        "description": "**Nuevas funciones disponibles tras la actualización:**\n\n- **Tabla de contenidos en tarjeta de título**: Agrega `mostrar_secciones: sí` a una fila de historia en project.csv para mostrar una tabla de contenidos navegable en su tarjeta de título, con enlaces a cada tarjeta de sección en la historia.\n\n- **Tarjetas de sección**: Sin cambios respecto a v1.1.0 — deja vacía la columna de objeto en un paso para crear un salto de sección.\n\n- **Números ordinales eliminados**: Las tarjetas de historia ya no muestran números generados automáticamente. La página de inicio usa la primera letra del título de cada historia.",
        "doc_url": "https://telar.org/guia"
      }
    ]
  }
}
```

## Example: v1.0.0-beta to v1.1.0

```json
{
  "schema_version": 1,
  "from_version": "1.0.0-beta",
  "to_version": "1.1.0",
  "description": "Linking, Layers & Collections — deep linking, title cards, collection mode, bibliography",
  "operations": [
    {
      "type": "config_add_field",
      "key": "collection_mode",
      "value": "false",
      "after_key": "telar_language",
      "comment": "Set to true to show objects first with large thumbnails and stories below with small thumbnails (collection-first homepage)",
      "skip_if_exists": true
    }
  ],
  "manual_steps": {
    "en": [
      {
        "description": "**New features available after upgrade:**\n\n- **Deep linking**: Story URLs now update as readers scroll. Copy and share a URL that points to a specific step, optionally with a panel open.\n\n- **Title cards**: Leave the object column empty for a step row to create a chapter heading card.\n\n- **Collection mode**: Add `collection_mode: true` to `_config.yml` for a collection-first homepage.\n\n- **Bibliography styling**: Wrap references in `:::bibliography` blocks for hanging-indent formatting.\n\n- **Share panel**: The share panel now includes a \"this view\" tab for position-aware sharing.",
        "doc_url": "https://telar.org/docs"
      }
    ],
    "es": [
      {
        "description": "**Nuevas funciones disponibles tras la actualización:**\n\n- **Enlaces directos**: Las URLs de las historias se actualizan al desplazarse. Copia y comparte una URL que apunte a un paso específico.\n\n- **Tarjetas de título**: Deja vacía la columna de objeto en una fila de paso para crear una tarjeta de encabezado de capítulo.\n\n- **Modo colección**: Agrega `collection_mode: true` en `_config.yml` para una página de inicio que prioriza la colección.\n\n- **Estilo bibliográfico**: Envuelve las referencias en bloques `:::bibliography` para formato de sangría francesa.\n\n- **Panel de compartir**: El panel de compartir ahora incluye una pestaña \"esta vista\" para compartir la posición exacta.",
        "doc_url": "https://telar.org/guia"
      }
    ]
  }
}
```

## Validation Rules

The compositor validates manifests before applying. A manifest must:

1. Have `schema_version: 1`
2. Have `from_version` matching the site's current version
3. Have all required fields per operation type
4. Have bilingual variants (`en` + `es`) for all bilingual fields
5. Use only recognised operation types

If validation fails, the compositor shows an error and does not proceed.

## Producing a Manifest

When releasing a new Telar version:

1. Write the Python migration script as usual (`scripts/migrations/vXXX_to_vYYY.py`)
2. Write `migration.json` following this schema — it declares the same user-content transforms
3. The Python script is for CLI/Actions upgrades; the JSON is for compositor upgrades
4. Attach `migration.json` as a release asset when creating the GitHub Release
5. If the release has no user-content transforms (framework files only), the manifest still exists with an empty `operations` array — the manual steps are always useful
