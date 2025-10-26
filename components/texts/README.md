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

### Glossary Functionality in v0.1.0-beta

**What works:**
- Glossary term pages at `/glossary/{term_id}/`
- Each term page displays the full definition
- Related terms are linked automatically
- Browsable glossary index page

**What's planned for v0.2:**
- Automatic detection and linking of glossary terms within story narrative text
- Terms mentioned in layer content would automatically become clickable
- Hovering or clicking would open glossary panel overlay

For now, glossary terms function as standalone reference pages that readers can navigate to from the glossary index.

## Why Texts?

This folder is called "texts" because it contains the textual narrative content - the words that tell your story and explain your objects.
