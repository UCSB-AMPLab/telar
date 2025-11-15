# Telar

![Version](https://img.shields.io/badge/version-0.4.2--beta-orange) ![License](https://img.shields.io/badge/license-MIT-blue)

A minimal computing framework for creating visual narrative exhibitions with IIIF images and scrollytelling.

---

**[Full Documentation](https://ampl.clair.ucsb.edu/telar-docs)** | **[Example Site](https://ampl.clair.ucsb.edu/telar)** | **[Report Issues](https://github.com/UCSB-AMPLab/telar/issues)**

---

> **⚠️ Beta Release - v0.4.2-beta**
> This is a beta release for testing and feedback. For detailed documentation, visit **[ampl.clair.ucsb.edu/telar-docs](https://ampl.clair.ucsb.edu/telar-docs)**.

> **Warning:** If upgrading from v0.3.4 or earlier, see the [Upgrading Telar Guide](https://ampl.clair.ucsb.edu/telar-docs/docs/2-workflows/3-upgrading/) for instructions.

## Overview

Telar (Spanish for "loom") is a static site generator built on Jekyll that weaves together IIIF images, narrative text, and layered contextual information into interactive visual narrative exhibitions. It follows minimal computing principles: plain text authoring, static generation, and sustainable hosting.

Telar is developed by Adelaida Ávila, Juan Cobo Betancourt, Santiago Muñoz, and students and scholars at the [UCSB Archives, Memory, and Preservation Lab](https://ampl.clair.ucsb.edu), the UT Archives, Mapping, and Preservation Lab, and [Neogranadina](https://neogranadina.org).

We gratefully acknowledge the support of the [Caribbean Digital Scholarship Collective](https://cdscollective.org), the [Center for Innovative Teaching, Research, and Learning (CITRAL)](https://citral.ucsb.edu/home) at the University of California, Santa Barbara, the [UCSB Library](https://library.ucsb.edu), the [Routes of Enslavement in the Americas University of California MRPI](https://www.humanities.uci.edu/routes-enslavement-americas), and the [Department of History of The University of Texas at Austin](https://liberalarts.utexas.edu/history/).

## Key Features

- **IIIF integration**: Support for both local images (auto-generated tiles) and external IIIF resources with automatic metadata extraction
- **Scrollytelling**: Discrete step-based scrolling with support for multiple IIIF objects in a single story - each object preloaded in its own viewer card
- **Interactive widgets**: Carousel, tabs, and accordion components for rich content presentation
- **Layered panels**: Progressive disclosure with three content layers plus glossary auto-linking
- **Multilingual UI**: Complete interface support for English and Spanish
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

## Upgrading Telar

**Telar v0.3.4+ includes an automated upgrade system** for easy, safe updates to the latest version.

### For Sites Running v0.3.4 or Later

Upgrading is fully automated:

1. Go to your repository on GitHub → **Actions** tab
2. Select **"Upgrade Telar"** workflow
3. Click **Run workflow**
4. Review the automatically created upgrade issue
5. Click the link in the issue to create a pull request
6. Review changes and merge

The upgrade system detects your current version, applies all necessary migrations, and creates a detailed summary with any manual steps you need to complete.

### For Sites Running v0.2.0 through v0.3.3

First-time setup required (one-time only):

1. Add the upgrade workflow file and updated build workflow from the Telar repository
2. Run your first automated upgrade
3. All future upgrades will be automated

**For complete upgrade instructions**, including detailed setup steps, troubleshooting, and version history, see the [Upgrading Telar Guide](https://ampl.clair.ucsb.edu/telar-docs/docs/2-workflows/upgrading/) in the documentation.

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

## Automated Upgrades

Telar v0.3.4+ includes an automated upgrade workflow that migrates your site to the latest version.

> **Note:** The automated upgrade workflow is available for sites running **v0.3.4 or later**. If you're upgrading from an earlier version (v0.2.0-v0.3.3), you'll need to manually copy the upgrade workflow files to your repository first. See the [Upgrade Guide](https://ampl.clair.ucsb.edu/telar-docs/docs/workflows/upgrading) for detailed instructions.

**To upgrade your site (v0.3.4+):**
1. Go to your repository's **Actions** tab on GitHub
2. Select the **"Upgrade Telar"** workflow
3. Click **"Run workflow"**
4. Review the automatically created pull request
5. Merge the PR to complete the upgrade

The upgrade system automatically:
- Detects your current version
- Applies necessary migrations
- Updates framework files and configurations
- Generates an upgrade summary with any manual steps

For detailed instructions, see the [Upgrade Guide](https://ampl.clair.ucsb.edu/telar-docs/docs/workflows/upgrading).

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
