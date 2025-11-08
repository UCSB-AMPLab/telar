# Texts

This folder contains markdown files with the narrative text content for your Telar site.

## Purpose

These markdown files are **content components** that can be referenced and reused throughout your site. Each file contains frontmatter metadata and body content.

## Structure

```
texts/
├── stories/         - Narrative content for story layers/panels
│   └── story1/      - Optional subfolder for organizing files
│       ├── step1-layer1.md
│       ├── step1-layer2.md
│       └── ...
└── glossary/        - Glossary term definitions
    ├── term1.md
    └── term2.md
```

**Note:** Subfolders like `story1/` are **optional**. You can organize your story markdown files however you like - all in the `stories/` folder directly, grouped by story in subfolders, or any other structure that makes sense for your project. Just make sure to reference the correct path (e.g., `story1/step1-layer1.md` or `step1-layer1.md`) in your story spreadsheet or CSV files.

## Markdown File Format

Each markdown file should have frontmatter with a title:

```markdown
---
title: "Your Title Here"
---

Your content text here. This can include multiple paragraphs,
formatting, and will be converted to HTML during build.
```

## Workflow

1. **Write** - Create or edit markdown files with frontmatter
2. **Reference** - In CSV files (components/structures/), reference these files by path
3. **Convert** - Run `python3 scripts/csv_to_json.py` to embed content into JSON (this happens automatically on GitHub)
4. **Build** - Run `bundle exec jekyll build` to generate the site (this happens automatically on GitHub)

## Story Content

Story markdown files are referenced in story CSV files via `layer1_file` and `layer2_file` columns. The CSV-to-JSON script extracts the title and content from these files and embeds them into the story JSON data.

## Glossary Content

Glossary markdown files are processed by `scripts/generate_collections.py` which creates Jekyll collection files in `_jekyll-files/_glossary/` (this happens automatically on GitHub).

### Glossary Functionality

**Basic features:**
- Glossary term pages at `/glossary/{term_id}/`
- Each term page displays the full definition
- Related terms are linked automatically
- Browsable glossary index page
- Clicking terms opens a slide-over panel instead of navigating to new pages

**Auto-linking in story content (v0.4.0+):**

You can link to glossary terms from within your story markdown content using wiki-style syntax:

```markdown
The [[colonial-period|colonial era]] saw significant changes...
The territory was governed by the [[viceroyalty]].
```

**Syntax:**
- `[[term_id]]` - Links to term and displays the term_id as link text
- `[[term_id|display_text]]` - Links to term but shows custom display text

**What happens:**
- Valid terms become clickable links that open the glossary panel
- Invalid term IDs display as highlighted warnings in the browser
- Build-time validation checks all glossary links and reports issues

**Example:**

In your story markdown file (`components/texts/stories/step1-layer1.md`):

```markdown
---
title: "The Founding of Santafé"
---

The city of Santafé de Bogotá was founded in 1537, during the Spanish [[colonial-period|colonial period]]. In the 18th century it became the capital of a new [[viceroyalty]] of New Granada.
```

The glossary link parser automatically converts these wiki-style links to clickable glossary terms during the build process.

## Why Texts?

This folder is called "texts" because it contains the textual narrative content - the words that tell your story and explain your objects.
