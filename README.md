# Telar

![Version](https://img.shields.io/badge/version-0.3.2--beta-orange) ![License](https://img.shields.io/badge/license-MIT-blue) [![Trigger Build](https://img.shields.io/badge/▶_Trigger-Build-blue)](https://github.com/UCSB-AMPLab/telar/actions/workflows/build.yml)

A minimal computing framework for creating visual narrative exhibitions with IIIF images and scrollytelling.

---

**[Full Documentation](https://ampl.clair.ucsb.edu/telar-docs)** | **[Example Site](https://ampl.clair.ucsb.edu/telar)** | **[Report Issues](https://github.com/UCSB-AMPLab/telar/issues)**

---

> **⚠️ Beta Release - v0.3.2-beta**
> This is a beta release for testing and feedback. For detailed documentation, visit **[ampl.clair.ucsb.edu/telar-docs](https://ampl.clair.ucsb.edu/telar-docs)**.

> **Warning:** Version 0.3.0 introduced breaking changes. If upgrading from v0.2.0, see [Migration Guide](#migrating-from-v020) below.

## Overview

Telar (Spanish for "loom") is a static site generator built on Jekyll that weaves together IIIF images, narrative text, and layered contextual information into interactive visual narrative exhibitions. It follows minimal computing principles: plain text authoring, static generation, and sustainable hosting.

Telar is developed by Adelaida Ávila, Juan Cobo Betancourt, Santiago Muñoz, and students and scholars at the [UCSB Archives, Memory, and Preservation Lab](https://ampl.clair.ucsb.edu), the UT Archives, Mapping, and Preservation Lab, and [Neogranadina](https://neogranadina.org).

## Key Features

- **IIIF integration**: Support for both local images (auto-generated tiles) and external IIIF resources
- **Scrollytelling**: Discrete step-based scrolling with support for multiple IIIF objects in a single story - each object preloaded in its own viewer card
- **Layered panels**: Progressive disclosure with three content layers plus glossary
- **Objects gallery**: Browsable object grid with detail pages
- **Minimal computing**: Plain text, static generation, GitHub Pages hosting

---

## Quick Start (no installation required!)

**For comprehensive step-by-step guides, see the [full documentation site](https://ampl.clair.ucsb.edu/telar-docs).** This Quick Start provides the essential steps to get your site running—detailed workflows and advanced topics are covered in the docs.

Get started with Telar in just a few steps. Telar narratives combine IIIF images with layered storytelling—each story unfolds through steps that show images alongside brief text, with optional panels for deeper exploration.

### Before You Begin

Plan your narrative structure before building. Sketch out your stories, identify key moments, choose anchor images, and decide what information belongs in brief answers versus deeper layers. Browse the [example site](https://ampl.clair.ucsb.edu/telar) for inspiration.

### Setup Steps

1. **Create your repository**
   - Click the green "Use this template" button above
   - Name your repository and create it

2. **Choose your content management approach**
   - **Google Sheets** (recommended): Use [our template](https://bit.ly/telar-template) to manage content via spreadsheet
   - **CSV files**: Edit CSV files directly in your repository

3. **Add your content**
   - Upload images to `components/images/objects/` or use IIIF manifests from institutions
   - Create markdown files in `components/texts/stories/` for your narrative text
   - Configure your objects and stories in Google Sheets or CSV files

4. **Enable GitHub Pages**
   - Go to repository **Settings** → **Pages**
   - Set source to **GitHub Actions**
   - Save and wait 2-5 minutes for deployment

5. **Configure and customize**
   - Edit `_config.yml` to set your site title and theme
   - For Google Sheets: Add your sheet URLs to the `google_sheets` section
   - View your site at `https://[username].github.io/[repository]/`

### Next Steps

- **Detailed workflows**: See [GitHub Web Interface](https://ampl.clair.ucsb.edu/telar-docs/docs/2-workflows/1-github-web) or [Local Development](https://ampl.clair.ucsb.edu/telar-docs/docs/2-workflows/2-local-dev) guides
- **Content structure**: Learn about [organizing your content](https://ampl.clair.ucsb.edu/telar-docs/docs/3-content-structure)
- **IIIF integration**: Understand [how to work with IIIF images](https://ampl.clair.ucsb.edu/telar-docs/docs/4-iiif-integration)
- **Customization**: Explore [themes and styling options](https://ampl.clair.ucsb.edu/telar-docs/docs/6-customization/)

---

## Migrating from v0.2.0

**⚠️ Important: Breaking Changes**

This release includes breaking changes that require updates to existing projects. See migration instructions below.

### Migration Guide

**1. Update project.csv structure**

Old format (key-value pairs):
```csv
key,value
project_title,Your Exhibition Title
tagline,A brief description
...
STORIES,
1,Story One
2,Story Two
```

New format (columns):
```csv
order,title,subtitle
1,Story One,Optional subtitle
2,Story Two,
```

The `project_title`, `tagline`, `author`, `email`, and `logo` fields are now configured in `_config.yml` instead of project.csv.

**2. Migrate theme customization**

If you had `primary_color`, `secondary_color`, `font_headings`, or `font_body` in project.csv, remove them and configure theming via `_config.yml`:

```yaml
telar_theme: "paisajes"  # or neogranadina, santa-barbara, austin
```

For custom colors/fonts, create `_data/themes/custom.yml` and set `telar_theme: "custom"` in `_config.yml`.

---

## Local Development

For developers who want to run Telar locally:

**Prerequisites:** Ruby 3.0+, Bundler, Python 3.9+

**Quick setup:**
```bash
bundle install
pip install -r requirements.txt
bundle exec jekyll serve
```

For detailed local development instructions, see the [Local Development Guide](https://ampl.clair.ucsb.edu/telar-docs/docs/2-workflows/2-local-dev) in the documentation.

## Content Structure

Telar uses a components-based architecture:
- `components/structures/` - CSV files (or Google Sheets) with site and story data
- `components/images/objects/` - Source images for IIIF processing
- `components/texts/stories/` - Markdown files for narrative content
- `components/texts/glossary/` - Glossary term definitions

For detailed information about organizing your content, see the [Content Structure Guide](https://ampl.clair.ucsb.edu/telar-docs/docs/3-content-structure) in the documentation.

## IIIF Integration

Telar supports both local images (auto-generated IIIF tiles) and external IIIF resources from museums and libraries. Upload images to `components/images/objects/` or reference external IIIF manifests in your object metadata.

For complete details on working with IIIF images, see the [IIIF Integration Guide](https://ampl.clair.ucsb.edu/telar-docs/docs/4-iiif-integration).

## Configuration

Configure your site in `_config.yml` (site title, theme, Google Sheets URLs, etc.). Telar includes 4 preset themes: Paisajes, Neogranadina, Santa Barbara, and Austin.

For all configuration options, see the [Configuration Guide](https://ampl.clair.ucsb.edu/telar-docs/docs/5-configuration).

## Deployment

The build process is fully automated via GitHub Actions. Push changes to the main branch and GitHub Pages automatically rebuilds and deploys your site. To manually trigger a rebuild (e.g., after editing Google Sheets), go to the Actions tab and run the "Build and Deploy" workflow.

For details on the automated workflow, see the [GitHub Actions Reference](https://ampl.clair.ucsb.edu/telar-docs/docs/7-reference/1-github-actions).

## Customization

Telar includes 4 preset themes (Paisajes, Neogranadina, Santa Barbara, Austin) that can be switched via `_config.yml`. You can also create custom themes with your own colors and fonts.

For theme customization and advanced styling, see the [Customization Guide](https://ampl.clair.ucsb.edu/telar-docs/docs/6-customization/).

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

**Note:** This license covers the Telar framework code and documentation. It does NOT cover user-created content (stories, images, object metadata, narrative text) which remains the property of content creators and may have separate licenses.

## Credits

Telar is developed by Adelaida Ávila, Juan Cobo Betancourt, Santiago Muñoz, and students and scholars at the [UCSB Archives, Memory, and Preservation Lab](https://ampl.clair.ucsb.edu), the UT Archives, Mapping, and Preservation Lab, and [Neogranadina](https://neogranadina.org).

Telar is built with:
- [Jekyll](https://jekyllrb.com/) - Static site generator
- [UniversalViewer](https://universalviewer.io/) - IIIF viewer
- [Bootstrap 5](https://getbootstrap.com/) - CSS framework
- [iiif-static](https://github.com/bodleian/iiif-static-choices) - IIIF tile generator

It is based on [Paisajes Coloniales](https://paisajescoloniales.com/), and inspired by:
- [Wax](https://minicomp.github.io/wax/) - Minimal computing for digital exhibitions
- [CollectionBuilder](https://collectionbuilder.github.io/) - Static digital collections

## Support

- **Documentation:** [ampl.clair.ucsb.edu/telar-docs](https://ampl.clair.ucsb.edu/telar-docs)
- **Report Issues:** [GitHub Issues](https://github.com/UCSB-AMPLab/telar/issues)
- **Example Site:** [ampl.clair.ucsb.edu/telar](https://ampl.clair.ucsb.edu/telar)

## Roadmap

### Recently Completed (v0.3.0-beta)

- [x] **Google Sheets integration**: Edit content via spreadsheet interface with automatic CSV fetching
- [x] **Comprehensive error messaging**: User-friendly warnings for configuration issues
- [x] **IIIF manifest copy functionality**: One-click copying of manifest URLs and coordinates
- [x] **Theme system**: 4 preset themes (Paisajes, Neogranadina, Santa Barbara, Austin) with customizable colors and fonts, plus support for custom themes
- [x] **Theme fallback protection**: Multi-tier error detection and automatic fallback to prevent broken styling

### Future Features

- [ ] **Improved documentation**: Video tutorials and examples
- [ ] **Visual story editor**: Point-and-click coordinate selection with live preview
- [ ] **Annotation support**: Clickable markers on IIIF images that open panels with additional information (IIIF annotations)
- [ ] **Glossary auto-linking**: Automatic detection and linking of terms within narrative text
- [ ] **Mobile-optimized responsive design**: Improved mobile and tablet experience
- [ ] **Accessibility improvements**: Comprehensive ARIA labels, keyboard navigation, and color contrast verification
- [ ] **Image lazy loading**: Improved performance for object galleries
- [ ] **Multi-language support**: Internationalization and localization
- [ ] **3D object support**: Integration with 3D viewers
- [ ] **Timeline visualizations**: Temporal navigation for chronological narratives
