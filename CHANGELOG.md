# Changelog

All notable changes to Telar will be documented in this file.

## [0.8.0-beta] - 2026-02-05

Content and access release adding story protection, an enhanced gallery system, and glossary CSV support.

### Added

- **Protected stories**: Stories can now be encrypted with a site-wide key. Add `protected=yes` to a story's row in `project.csv` and set `story_key` in `_config.yml`. Protected stories are encrypted at build time using AES-256-GCM and decrypted in the browser when viewers enter the key. An unlock overlay with session persistence means the key only needs to be entered once per browser session. Share links can optionally include the key for convenient access

- **Browse and search for objects**: The objects page now includes a filter sidebar, full-text search (powered by Lunr.js), and sort controls. Filters use OR within a category and AND across categories. Desktop shows a 250px sidebar on the right; mobile shows a collapsible "Filter by" pill. Disable with `browse_and_search: false` in `_config.yml`

- **Featured objects on homepage**: Optionally display a sample of objects on the homepage with smaller 170px cards. Configure with `show_sample_on_homepage: true` and `featured_count` in `_config.yml`. Objects can be explicitly marked with a `featured` column in `objects.csv`, or selected randomly at build time

- **Glossary CSV support**: Define glossary terms in `components/structures/glossary.csv` as an alternative to individual markdown files. Supports inline definitions and file references. Existing markdown glossaries continue to work unchanged

- **Share panel redesign**: The share panel now uses pill-style tabs ("this story" / "this whole site") with inline copy buttons. For protected stories, a privacy toggle lets you choose whether to include the key in shared links and embed codes, with clear warnings about access implications

### Changed

- **Config setting renames**: `hide_stories` renamed to `skip_stories` and `hide_collections` renamed to `skip_collections` under `development-features`. Old names still work for backward compatibility

- **New config section**: `collection_interface` settings control the objects gallery (browse and search, homepage link, featured objects)

- **Object metadata fields**: Objects CSV now supports `year`, `object_type`, `subjects`, and `featured` columns for richer filtering. The `location` field has been renamed to `source` (old name still supported)

---

**Migration from v0.7.0-beta:**
- Run `python3 scripts/upgrade.py` to upgrade automatically
- **Manual step required**: Copy updated `.github/workflows/build.yml` from the Telar repository (adds search data generation step)
- **For local development**: Install `cryptography` package: `pip install -r requirements.txt`

## [0.7.0-beta] - 2026-01-31

Infrastructure and code quality release focusing on maintainability, testing, and accessibility.

### Added

- **Test infrastructure**: Comprehensive automated testing with 305 tests across three frameworks. Python unit tests (235 tests) cover CSV processing, widget parsing, IIIF metadata extraction, and more. JavaScript unit tests (35 tests) verify viewer, navigation, and panel logic. End-to-end tests (35 tests) use Playwright to test story navigation, embed mode, and panel interactions in a real browser

- **Consolidated CI workflow**: Single `telar-tests.yml` workflow runs both Python and JavaScript tests on push/PR. Supports selective test runs via workflow dispatch for faster iteration

- **Dependabot**: Automatic security updates for GitHub Actions dependencies

### Changed

- **Modular Python scripts**: The 2,750-line `csv_to_json.py` is now a 14-module `telar/` package with clear separation of concerns. Each module has a focused purpose: `csv_utils.py` for CSV handling, `widgets.py` for widget parsing, `iiif_metadata.py` for IIIF extraction, etc. The original script remains as a backward-compatible wrapper

- **Modular JavaScript**: The 1,872-line `story.js` is now 6 ES modules bundled by esbuild. `state.js` centralises all mutable state, `navigation.js` handles all navigation modes, `viewer.js` manages IIIF viewer lifecycle, etc. Consolidated 135 lines of duplicated code into shared utilities

- **SCSS partials**: The 3,374-line `telar.scss` is now 9 focused partials in `_sass/`. Reusable mixins for tab colours and viewer hiding reduce duplication. Each partial has a narrative description explaining its purpose

- **Node.js required**: esbuild is now used to bundle JavaScript. Run `npm install` before building locally. The `build_local_site.py` script handles this automatically

### Fixed

- **Accessibility (WCAG AA)**: Fixed colour contrast on intro hints, added navigation landmark for home button, changed story container to semantic `<main>` element. Verified with axe-core accessibility audit

- **Navigation z-index**: Fixed intro step covering navigation buttons when scrolling back from later steps

- **Pandas 3.0 compatibility**: Fixed emoji sanitisation failing on pandas 3.0 due to StringDtype change

---

**Migration from v0.6.3-beta:**
- Run `python3 scripts/upgrade.py` to upgrade automatically
- **Manual step required**: Copy updated GitHub Actions workflows from the Telar repository (build.yml, upgrade.yml, telar-tests.yml)
- **For local development**: Run `npm install` to install esbuild for JavaScript bundling

## [0.6.3-beta] - 2026-01-24

### Added

- **Inline panel content**: Write panel text directly in your spreadsheet instead of creating separate markdown files. Supports three methods: (1) entering text directly in cells, (2) pasting markdown text with optional YAML frontmatter, or (3) referencing external markdown files for complex content. The `layer1_file` column has been renamed to `layer1_content` (old name still works for backward compatibility)

### Changed

- **Column naming**: `layer1_file`, `layer2_file`, `layer3_file` renamed to `layer1_content`, `layer2_content`, `layer3_content` to reflect their expanded purpose. Spanish equivalents: `contenido_capa1`, `contenido_capa2`, `contenido_capa3`. Old column names remain supported for backward compatibility

### Fixed

- **Empty state messages**: Error messages now reference user-editable locations (spreadsheet, `components/` directory) instead of internal Jekyll directories

---

**Migration from v0.6.2-beta:**
- Run `python3 scripts/upgrade.py` to upgrade automatically
- No breaking changes — existing spreadsheets and markdown files work without modification

## [0.6.2-beta] - 2025-12-03

### Added

- **Improved viewer preloading**: Complete overhaul of how Telar loads IIIF viewers eliminates black screens and speeds up navigation. All IIIF manifests are fetched in parallel when the story page loads, so images are ready before you scroll to them. Hovering over a story card on the homepage begins loading its manifests. A subtle shimmer animation shows when a viewer is initializing. Preloading behavior can be tuned via `development-features.viewer_preloading` in `_config.yml`

- **Glossary-to-glossary linking**: You can now use `[[term]]` syntax inside glossary definitions to link to other glossary terms

- **All-in-one build script for local sites**: New `build_local_site.py` runs the complete local build process with a single command. Use `--skip-iiif` for faster rebuilds when images haven't changed, `--skip-fetch` to skip demo content fetching. Serves on port 4001 by default

- **Development feature flags**: New `development-features` section in `_config.yml` with `hide_stories` (temporarily hide stories) and `hide_collections` (hide both objects and stories) for rapid testing

### Fixed

- **Case-insensitive object references**: Object IDs in your story spreadsheet now match regardless of capitalization (e.g., `LEVIATHAN` finds `leviathan`)

- **Case-insensitive file paths**: Markdown file paths work regardless of case, preventing broken links when deploying from Mac to GitHub Pages

- **Index page image overflow**: Large images on the homepage no longer overflow their containers

- **Panel title spacing**: Improved spacing below panel titles for better readability

- **Panel title markup**: Panel titles now use proper `<h1>` elements for accessibility

### Removed

- **Sample glossary entries**: Removed placeholder glossary entries (colonial-period, reduccion, resguardo, viceroyalty, iiif-manifest, markdown) that were not used by the template stories

---

**Migration from v0.6.1-beta:**
- Run `python3 scripts/upgrade.py` to upgrade automatically
- No breaking changes

## [0.6.1-beta] - 2025-11-28

### Added

- **Bilingual README**: Framework README now includes both English and Spanish versions in a single file. Streamlined content removes duplication and directs users to comprehensive documentation at telar.org

### Fixed

- **EXIF orientation in thumbnails**: Fixed thumbnails displaying sideways/upside-down for smartphone photos with EXIF rotation metadata. The IIIF tile generator now correctly detects and applies all EXIF orientations (90°, 180°, 270°). Regenerate IIIF tiles to see correctly oriented thumbnails: `python3 scripts/generate_iiif.py`
- **Migration script template pollution**: Fixed v0.5.0→v0.6.0 migration adding unwanted template files to existing sites. The migration now only adds templates (`your-story/`, `tu-historia/`, demo glossary) to new sites without custom content

## [0.6.0-beta] - 2025-11-28

### Added

#### External Demo Content System
- **Demo content fetching**: New `include_demo_content` configuration option in `_config.yml` allows sites to optionally fetch versioned, multilingual demo content from content.telar.org
- **Automatic demo integration**: Demo stories and glossary entries are automatically merged with your content during the build process
- **Smart cleanup**: Template now ships without bundled demo content - fetch only when needed
- **Bilingual demos**: Demo content adapts to your site language (English or Spanish)
- **Version matching**: Fetches highest compatible demo version for your site

#### Custom Pages System
- **User-editable pages**: Create custom pages in `components/texts/pages/` directory (about, contact, etc.)
- **Configurable navigation menu**: Edit menu items via `_data/navigation.yml` with bilingual support
- **Full Telar features**: Widgets and glossary links work on custom pages
- **Responsive layout**: New `user-page.html` layout provides centered, mobile-friendly content

#### New Telar Website and Documentation
- **New home: telar.org**: Unified website with landing page, documentation, and demo content hosting
- **Comprehensive documentation**: Complete documentation site at telar.org/docs (English) and telar.org/guia (Spanish)
- **Version callouts**: Documentation clearly indicates which features require v0.6.0+
- **Improved structure**: Documentation reorganized with dedicated developer section (Section 8)
- **Backwards-compatible redirects**: Old ampl.clair.ucsb.edu/telar-docs URLs redirect to telar.org/docs

#### Story ID Support (Quality of Life)
- **Semantic story names**: Optional `story_id` column in `project.csv` enables custom story identifiers like "your-story" or "colonial-maps"
- **Better organization**: Story filenames and tab names match your chosen identifiers exactly
- **Fully backward compatible**: Falls back to numbered stories (`story-1`, `story-2`) when `story_id` not provided
- **Automatic discovery**: Scripts process all story CSVs automatically

#### Bilingual CSV Support (Quality of Life)
- **Spanish column headers**: Use Spanish headers in your CSVs (`paso`, `objeto`, `pregunta`, `respuesta`, etc.)
- **Dual header rows**: Support for bilingual header rows with automatic detection
- **Spanish filenames**: Support for Spanish CSV filenames (`proyecto.csv`, `objetos.csv`) with fallback to English
- **Spanish Google Sheets tabs**: Automatically detects Spanish tab names in Google Sheets
- **Fully backward compatible**: English-only CSVs work exactly as before

#### Object Credits Badge
- **Visible attribution**: New dismissable badge displays object credits in bottom-left corner of viewer
- **Configurable**: Enable/disable via `show_object_credits` in `_config.yml`
- **Bilingual**: Supports English "Credit:" and Spanish "Crédito:" prefixes
- **Respectful design**: Matches step number badge styling with subtle transparency

### Fixed

#### Panel Freeze System (Major UX Improvement)
- **Fixed: Scrolling within panels no longer triggers story navigation** - panels now have proper scroll isolation
- **Fixed: Viewer column scroll interference** - Universal Viewer zoom/pan now works without triggering step changes
- **Improved keyboard navigation**: ↑/↓ for steps, ←/→ for panels, Escape to close
- **Click outside to close**: Panels close when clicking on darkened backdrop
- **Better visual feedback**: Subtle dark backdrop extends beyond viewport during panel focus
- Based on initial implementation by Sanjana Bhupathi

#### Objects Page Ordering
- **Fixed: Demo objects now appear after user objects** - prevents demo content from cluttering the top of the objects index page

#### CSV Comment Line Handling
- **Fixed: Quoted comment lines now properly filtered** - handles Google Sheets CSV export format where cells containing commas are quoted

### Changed

#### Generated Files Architecture
- **Gitignore improvements**: Generated files (`_data/*.json`, `_jekyll-files/`) now ignored by git
- **Single source of truth**: Only source files (CSVs, markdown) tracked in version control
- **Cleaner git history**: Build-generated content no longer pollutes commit history
- **Migration handles cleanup**: Upgrade script removes generated files from git index automatically

#### Site Logo Feature Improvements
- **Better sizing**: Logo limited to max-height 80px with responsive styling
- **Cleaner homepage**: Logo removed from index page (header only)
- **Documentation**: Updated config comment with recommended dimensions (300x120px)

#### Byline Markdown Support
- **Rich text in bylines**: Project bylines now support markdown formatting (links, emphasis, etc.)
- **Enabled via markdownify filter** in story.html layout

### Developer Improvements

#### Tab Widget Styling
- **Rounded corners**: Tab buttons have rounded top corners (0.5rem)
- **Transparent background**: Only tab buttons visible, cleaner appearance
- **Visual hierarchy**: Inactive tabs dimmed (opacity 0.7), active tabs full opacity
- **Color consistency**: Matches accordion pattern with appropriate layer colors

#### Multilingual UI Infrastructure
- **Language data expansion**: New language strings for credits, updated navigation
- **Improved fallbacks**: Bilingual navigation with graceful degradation

---

**Migration from v0.5.0-beta:**
- Fully automated via `python3 scripts/upgrade.py`
- Zero manual steps for GitHub Pages users (automatic rebuild)
- Local developers: Regenerate data files and test build
- Demo content cleanup uses CSV-smart detection to preserve user-modified content

## [0.5.0-beta] - 2025-11-17

### Added

#### Canvas LMS Embedding Support
- **Complete iframe embedding system** for educational and blog platforms (Canvas, Moodle, Blackboard, WordPress, Squarespace, Wix)
- **Embed mode detection** via `?embed=true` URL parameter with automatic UI adjustments
- **Forced navigation buttons** on all viewports including desktop with custom positioning and responsive typography
- **"View full site" dismissible banner** with multilingual support and frosted glass effect
- **Successfully tested** in production Canvas LMS with cross-browser and mobile testing complete
- **Comprehensive documentation** with educator guide and troubleshooting section

#### Share & Embed UI
- **Share button component** with OS-specific icons and three variants (story page, navbar, icon-only)
- **Share panel modal** with two tabs: Share Links (clean URLs) and Embed Code (8 dimension presets)
- **Platform presets**: Canvas (100% × 800px), Moodle/Blackboard (100% × 700px), WordPress (100% × 600px), Squarespace (100% × 600px), Wix (100% × 550px), Mobile (375px × 500px), Fixed (800 × 600), Custom
- **Copy to clipboard** with visual feedback for both share URLs and embed codes
- **Full multilingual support** (English + Spanish) with platform documentation links

#### Extended Image Format Support
- **Native support** for HEIC (iPhone photos), WebP, and TIFF formats
- **Case-insensitive extension matching** (`.JPG`, `.png`, `.HEIC` all work)
- **Automatic JPEG conversion** during IIIF tile generation with original file preservation
- **Handles transparency** (RGBA, LA modes) and palette modes with proper conversion
- **Eliminates false warnings** for uppercase file extensions

#### Automatic Carousel Height Detection
- **Build-time dimension analysis** using PIL/Pillow with zero runtime cost
- **Four size classes**: Compact (400px), Default (550px), Tall (700px), Portrait (850px)
- **Automatic assignment** based on maximum aspect ratio in carousel
- **Eliminates manual configuration** for carousel heights

#### Responsive Typography for Slide-Over Panels
- **Extended fluid typography** from story steps to all panel contents using CSS `clamp()`
- **Max-width constraints** for panel images on narrow screens
- **Improved readability** across all device sizes

#### Mobile Panel Quality-of-Life Improvements
- **Scrollable story steps** prevent navigation button cutoff (changed `overflow: hidden` to `overflow-y: auto`)
- **Panel image width constraints** force `max-width: 100%` on mobile (≤768px) while preserving desktop sizing

#### Carousel Widget Styling Improvements
- **Captions moved below images** for better accessibility
- **Black container background** for better image contrast
- **Reduced typography** (0.9rem text, 0.8rem credit) with indicators positioned above captions
- **Disabled keyboard navigation** to prevent story navigation interference

#### Future Media Type Directory Structure
- **Placeholder directories** with READMEs: `components/pdfs/` (v0.6.0), `components/audio/` (v0.7.0), `components/3d-models/` (v0.8.0)
- **Prevents incompatible implementations** before official support

#### Version Headers in All Code Files
- **All scripts, styles, and workflows** now include version headers for better tracking
- **Format**: `Version: v0.5.0-beta` (Python/YAML) or `@version v0.5.0-beta` (JS/CSS)

### Changed

#### Flattened Image Directory Structure
- **Removed subdirectories**: `components/images/objects/` and `components/images/additional/` → `components/images/`
- **Updated default paths** in csv_to_json.py, generate_iiif.py, and validation
- **Automated migration** via upgrade script

#### CSV-Driven IIIF Tile Generation
- **Changed from directory-based to CSV-driven**: Only processes objects in `objects.csv` without external manifests
- **Automatic file detection** by `object_id` supporting multiple extensions (case-insensitive)
- **Faster generation** with no orphaned tiles

#### Unified source_url Column Name
- **Renamed `iiif_manifest` → `source_url`** for future media type compatibility (PDFs, videos, 3D, audio)
- **Full backward compatibility**: Both column names work, automatic aliasing in both directions
- **Updated templates** with Liquid fallback pattern

#### CSV-Aware GitHub Actions Monitoring
- **Smart change detection** only triggers IIIF when changed images match object IDs in objects.csv
- **Cache optimization** for more efficient CI/CD pipeline

#### Removed Unused Dependencies
- **Deleted scrollama.min.js and openseadragon.min.js** (~47KB savings) - Telar uses custom scroll system and UniversalViewer's bundled OpenSeadragon
- **Deleted docs/google_sheets_integration/** folder - fully documented in official docs site

### Fixed

#### CRITICAL: v0.4.0 Feature Restoration (Phase 1 - Data Pipeline)
- **Restored 1,382 lines** accidentally deleted from `csv_to_json.py` in commit f62acee (Nov 8, 2025)
- **Root cause**: Commit overwrote file, removing core v0.4.0 functionality
- **Features restored**:
  - Widget processing (~350 lines): accordion, carousel, tabs with Bootstrap HTML generation
  - IIIF metadata auto-population (~400 lines): extracts title, creator, period, location, credit
  - Glossary auto-linking (~150 lines): `[[term_id]]` syntax processing
  - Multilingual support (~100 lines): language string loading and interpolation
- **Applied v0.5.0 updates** to restored code (version header, flattened image paths)

#### CRITICAL: v0.4.0 Feature Restoration (Phase 2 - Display Components)
- **Restored frontend components** for widgets and glossary (~115 lines total)
- **Widget panel-specific styling**: Layer 1 widgets use Layer 2 colors and vice versa
- **Enhanced glossary functionality**: Proper title extraction, both inline and index links work
- **Widget initialization**: Added widgets.js script tag
- **Glossary multilingual support**: Language-aware panel labels and "Key term:" prefix

#### Layer 2 Panel Heading Colors
- **Fixed h2, h3, h4 color inheritance** in layer 2 panels (white on dark purple background)

#### Glossary Warning Message Clarity
- **Improved error message formatting** for missing glossary terms with quoted, bold term IDs
- **Added file path context** showing exactly which markdown file contains the broken reference
- **Natural sentence structure** replaces technical phrasing for better readability
- **Example**: "In the file stories/story2/step4-layer2.md, you reference the glossary term 'term', but this term does not exist in components/texts/glossary/"
- Files modified: `scripts/csv_to_json.py`, `_data/languages/en.yml`, `_data/languages/es.yml`

### Migration

- **Automated v0.4.x → v0.5.0 migration**:
  - File relocation: old subdirectories → `components/images/`
  - CSV column update: `iiif_manifest` → `source_url`
  - Name conflict detection and empty directory cleanup
- **Full backward compatibility**: No breaking changes for existing sites

---

## [0.4.3-beta] - 2025-11-15

### Fixed

#### v0.4.1 Migration Script Comment Restoration
- **Complete framework comments restored**: Migration now restores all missing comments in _config.yml
- **Top header comments**: Framework title and GitHub URL now restored at file beginning
- **Complete testing-features section**: Entire section created if missing (not just comments)
- **Impact**: Sites upgrading from v0.3.4 through multiple versions now have complete config structure
- Files modified: `scripts/migrations/v040_to_v041.py`

#### iPad Touch Scrolling for Story Navigation
- **Touch navigation support**: iPad and touch devices can now navigate stories using swipe gestures
- **Desktop viewport mode**: Fixes issue where touch scrolling didn't trigger story step changes
- **Swipe to navigate**: Swipe up for next step, swipe down for previous step
- **Respects cooldowns**: Same 600ms cooldown as mouse/trackpad scrolling
- Files modified: `assets/js/story.js` (added touch event handlers)

#### IIIF Regeneration on Config Changes
- **Automatic regeneration**: IIIF tiles now regenerate when _config.yml changes
- **Prevents broken images**: Fixes issue where baseurl changes caused image serving failures
- **Smart detection**: Added _config.yml to change detection pattern in build workflow
- Thanks to Tara for reporting this issue
- Files modified: `.github/workflows/build.yml` (updated change detection pattern)

#### EXIF Orientation Handling in IIIF Generation
- **Portrait photos now display correctly**: Images from phones/cameras no longer appear rotated 90 degrees
- **EXIF metadata respected**: Script now applies EXIF orientation data before generating IIIF tiles
- **User experience**: Students can upload phone photos directly without manual rotation
- **Visual feedback**: Console displays "↻ Applied EXIF orientation correction" when rotation is applied
- Thanks to Tara for helping spot this issue
- Files modified: `scripts/generate_iiif.py` (both `generate_iiif_for_image()` and `copy_base_image()`)

---

## [0.4.2-beta] - 2025-11-09

### Added

#### Smart IIIF Change Detection
- **Automatic optimization**: Build workflow now intelligently detects when IIIF tile regeneration is needed
- **Git diff-based detection**: Compares changed files between commits to determine if images or objects.csv changed
- **Manual override**: Workflow dispatch includes "Force IIIF tile regeneration" checkbox (default: checked for safety)
- **Multiple failsafes**: Defaults to full build on first commit, detection errors, or uncertain cases
- **GitHub Actions caching**: IIIF tiles cached between builds to prevent deletion when skipping regeneration
- **Cache key strategy**: Automatically invalidates cache when image files change using hash-based keys
- **Time savings**: Faster deployments for content-only changes (stories, text, metadata)
- **User experience**: Silent optimization for automatic builds, explicit control for manual triggers

**How it works**:
- Automatic builds (push to main): Detects file changes, skips IIIF if only content changed
- Manual builds: User checkbox to skip IIIF regeneration (safe default always regenerates)
- Cache system: Tiles saved after generation, restored when skipping, automatically invalidated on image changes

**Technical details**:
- Detection step runs before IIIF generation
- Checks `git diff --name-only HEAD~1 HEAD` for changed files
- Triggers IIIF when: images in `components/images/objects/` or `objects.csv` changed
- Skips IIIF when: Only content files changed (stories, glossary, configs, layouts, etc.)
- Cache operations: restore → generate (if needed) → save → restore to _site (if skipped)

### Fixed

#### CRITICAL: IIIF Tile Deletion When Skipping Regeneration
- **Root cause identified**: GitHub Actions workflows are ephemeral - each run starts fresh with no IIIF tiles
- **Problem**: Skipping IIIF generation left `_site/iiif/objects/` empty, deployment replaced entire site, deleting live tiles
- **Solution**: GitHub Actions cache system preserves tiles between workflow runs
- **Cache strategy**:
  - Restore cache after Jekyll build
  - Generate and cache tiles (if needed)
  - Restore cached tiles to `_site/` when skipping regeneration
  - Cache key based on image directory hash for automatic invalidation
- **Safety features**: Warns if cache unavailable, logs all cache operations, fails gracefully
- **Testing**: Confirmed working on demo site (ampl.clair.ucsb.edu/telar)
- **Impact**: Critical fix prevents tile deletion, enables safe optimization

#### Mobile Navbar Title Wrapping
- Long site titles now wrap naturally on mobile devices instead of overflowing or being cut off
- Hamburger menu right-aligned for better mobile UX
- Flexbox properties adjusted for proper text flow on small screens

#### Mobile Font Size Adjustments
- Added `white-space: normal` to allow proper text wrapping
- Reduced display-4 font size on mobile for better readability
- Works in conjunction with existing height-based responsive design

#### Site Title Wrapping on Mobile
- CSS rules added to enable proper text wrapping for site titles
- Ensures titles display cleanly across all mobile screen sizes
- Tested with various title lengths on different devices

#### Site Description Link Styling
- Fixed link styling on home page for consistent appearance
- Proper theme color application to site description links

### Changed
- Build workflow now includes smart IIIF detection and caching (4 new steps, ~76 lines added)
- Migration framework updated with `README.md` and `index.html` for complete v0.4.1 upgrades

---

## [0.4.1-beta] - 2025-11-08

### Fixed

#### CRITICAL: Upgrade Script Comment Deletion
- **Migration script bug fixed**: v0.3.4→v0.4.0 migration was deleting ALL comments from `_config.yml`
- **GitHub Actions workflow bug fixed**: Workflow was using `yaml.dump()` which stripped all comments after migration
- **Comment restoration added**: v0.4.0→v0.4.1 migration now detects and restores 13 types of missing comments
- **Comments restored**: Site Settings, Story Interface, PLEASE DO NOT EDIT warning, Collections, Build Settings, Defaults, Telar Settings, Plugins, WEBrick, Development & Testing, Christmas Tree Mode, and all setup instructions
- Root cause: `_ensure_google_sheets_comments()` in v034_to_v040.py used destructive `while loop + pop()` pattern
- Secondary cause: Workflow step "Update version in _config.yml" used `yaml.safe_load()` + `yaml.dump()` after migrations
- Impact: Users upgrading from v0.3.4 to v0.4.0 lost all documentation in their config files
- **Note for users**: After upgrading to v0.4.1, you need to update your `.github/workflows/upgrade.yml` file ONCE (see upgrade instructions)

#### CRITICAL: Mobile Responsive Features Restored
- **Complete mobile code recovery**: Restored ~1,300 lines of mobile responsive code accidentally lost in v0.4.0 release
- **Height-based responsive design**: 4-tier progressive system for small screens (Tiers 1-3: 700px, 667px, 600px height breakpoints)
- **Mobile panel UI**: Fixed-size panels with stacking visibility and proper viewport positioning
- **Graceful panel transitions**: Navigation cooldown, skeleton shimmer loading, fade-only transitions on mobile
- **Mobile preloading**: Aggressive ±2 step preloading on mobile, enhanced 3/2 forward/backward on desktop
- **Offcanvas adjustments**: Progressive typography and spacing reductions for small screens
- **Site-wide scaling**: Consistent mobile experience across all pages
- Root cause: Upstream merge in commit f62acee overwrote local mobile development
- Impact: Major regression fix - restores complete mobile UX from v0.4.0

### Added

#### Object Gallery Mobile Layout
- **Responsive breakpoints**: Single column layout up to 441px width, two columns from 442px-768px
- **Explicit column control**: Replaced auto-fill grid behavior with explicit column counts for predictable mobile layout
- **iPhone Pro Max optimization**: 440px width devices display single column for optimal readability
- **Removed conflicting rules**: Fixed 576px media query that was overriding mobile breakpoints

#### Coordinate Picker Improvements
- **Sheets copy button**: New button in coordinate picker that copies tab-separated values (x\ty\tzoom) for direct pasting into Google Sheets
- **CSV copy button**: Renamed existing button to "x, y, zoom (CSV)" for clarity
- **Button order**: Sheets button first (primary workflow), CSV button second
- **Multilingual support**: Button labels and "Copied!" feedback respect `telar_language` setting
- Both buttons provide visual feedback ("Copied!" / "¡Copiado!")

### Changed
- Coordinate picker now has two copy buttons instead of one, with clear labels indicating format
- Coordinate picker buttons are now fully multilingual (English/Spanish)

---

## [0.4.0-beta] - 2025-11-07

### Added

#### Multilingual UI Support
- **Complete interface internationalization** for English and Spanish
  - Language files: `_data/lang/en.yml` and `_data/lang/es.yml` with 300+ UI strings
  - Language-aware templates: All layouts and includes updated with multilingual string lookups
  - Configuration: `telar_language` setting in `_config.yml` (supports `en` and `es`)
  - Automatic language detection and fallback logic
  - All navigation, buttons, labels, error messages, and instructions translated
  - Warning messages and IIIF error explanations (~40 detailed error messages) fully multilingual

#### Interactive Widgets System
- **Three widget types** for rich content presentation in story panels:
  - **Carousel widget**: Image carousel with navigation controls, captions, and credit attribution
  - **Tabs widget**: Tabbed content panels for organizing multi-perspective information (2-4 tabs)
  - **Accordion widget**: Collapsible content sections for hierarchical information (2-6 panels)
- **CommonMark-style syntax**: `:::widget_type ... :::` for clear block boundaries
- **Python widget parser**: Build-time processing with Jinja2 templates (~350 lines)
- **Bootstrap 5 integration**: Responsive widgets that match site theme
- **External URL support**: Images can be referenced from http:// and https:// URLs
- **Build-time validation**: Comprehensive error checking with accessibility warnings
- **Opposite panel colors**: Widgets use contrasting colors for visual hierarchy (Layer 1 widgets use Layer 2 colors and vice versa)

#### Glossary Auto-Linking
- **Wiki-style inline syntax**: `[[term_id]]` for automatic term references in narrative text
- **Custom display text**: `[[term_id|display text]]` for flexible grammar
- **Automatic link generation**: Links open glossary slide-over panels
- **Build-time validation**: Warns about broken term references
- **CSS styling**: Theme-colored links with visual distinction
- **Full multilingual support**: Works seamlessly in both English and Spanish

#### IIIF Metadata Auto-Population
- **Automatic extraction** of object metadata from IIIF manifests
- **Supports both API versions**: IIIF Presentation API v2.0 and v3.0
- **Six auto-populated fields**: title, description, creator, period, location, credit
- **Language-aware extraction**: Uses site's `telar_language` setting with fallback to English
- **Smart credit detection**: Filters legal boilerplate, prefers actual attribution
- **Fallback hierarchy**: CSV values → IIIF manifest → empty (user control maintained)
- **HTML stripping**: Ensures YAML safety
- **Refined field matching**: Prioritizes specific field names to avoid false matches
- **9 extraction helper functions**: ~400 lines of comprehensive IIIF metadata handling

#### Mobile Responsiveness Enhancements
- **Mobile story navigation**: Graceful panel transitions with skeleton shimmer loading indicator
  - 400ms navigation cooldown to prevent rapid clicking
  - Subtle animated gradient during viewer initialization
  - Faster transitions (fade only, no slide animations)
  - Aggressive preloading (±2 steps on mobile)
- **Height-based responsive design**: 4-tier progressive system for small screens
  - Tier 1 (≤700px): 10-15% typography reduction
  - Tier 2 (≤667px - iPhone SE): 20-25% reduction, 55vh:45vh viewer:panel ratio
  - Tier 3 (≤600px): 30-35% reduction for very small Android devices
  - Dual-axis media queries prevent triggering on short desktop windows
- **Site-wide mobile optimizations**:
  - Offcanvas panels: Reduced padding, font sizes, and spacing
  - Object gallery: Single column layout on mobile (≤767px)
  - Glossary index: Optimized spacing (33-50% reduction in margins)
  - Collection grid: Reduced gaps and image heights
  - Navbar brand: Smaller font size on small screens
- **Mobile panel refinements**:
  - Glossary panel: 6vw left offset, 8vh top position, 76vh height, 94vw width
  - Navigation buttons: Reduced to 45px on small screens
  - Enhanced touch interactions and viewport handling

#### Story Interface Controls
- **Configurable step indicators**: New `story_interface` section in `_config.yml`
  - `show_story_steps`: Toggle "Step X" overlay visibility (CSS-based)
  - `include_demo_content`: Preparation for v0.5.0 demo content feature

#### Theme System Enhancements
- **Theme creator attribution**: Optional `creator` and `creator_url` fields in theme YAML files
  - Displayed in site footer when present
  - Recognizes theme contributions while maintaining clean footer design
  - All 5 preset themes updated with attribution
- **Google Fonts documentation**: Inline comments in theme files explaining how to use custom fonts
  - Direct link to Google Fonts
  - Format examples and syntax guidance
  - Fallback font requirements

#### Story Byline Feature
- **Optional author/creator attribution** for stories
  - New `byline` column in `project.csv`
  - Displays on homepage story cards (beneath title, smaller font, muted color)
  - Displays on story intro slide (as h3 between subtitle and description)
  - Fully optional and responsive

#### Development & Testing Tools
- **Christmas Tree Mode**: Comprehensive testing tool for multilingual warnings (displays all warnings at once, lighting site up like a Christmas tree)
  - `--christmas-tree` flag in `csv_to_json.py` or config-based in `_config.yml`
  - Injects test objects with various intentional error conditions
  - All test objects marked with 🎄 emoji for easy identification
  - Triggers all warning message types for verification
  - Automated cleanup system removes test files when disabled

### Changed

- **Enhanced preloading**: Desktop preloads 3 steps ahead and 2 behind (vs 2/1 previously) for smoother navigation
- **Footer enhancements**: Multilingual footer with theme attribution support, language-aware copyright and navigation strings
- **Story back button**: Desktop shows text only (icon hidden), mobile shows icon only (text hidden) for cleaner design
- **Carousel captions**: Moved below images instead of overlaid for better readability
- **Carousel image display**: Centered with equal widths using flexbox
- **Widget visual contrast**: Widgets use opposite panel colors (Layer 1 widgets use Layer 2 colors, Layer 2 widgets use Layer 1 colors)

### Fixed

#### Critical Data Handling
- **Numeric object_id YAML parsing**: Added quotes around object_id values to prevent YAML parsers from treating numeric filenames as integers. Gracias, Adelaida!
- **Google Sheets quotation marks**: Created `escape_yaml()` helper function to handle quotation marks in all user-editable fields (dimensions, titles, etc.). Thanks, Jeff!

#### IIIF Issues
- **IIIF manifest 429 rate-limit false positives**: Skip 429 errors for unchanged manifests between builds
- **IIIF mismatch localhost/127.0.0.1**: Normalize both URLs to prevent false positive warnings
- **IIIF manifest validation with redirects**: Changed from HEAD to GET request to properly follow 301/302 redirects
- **IIIF field matching precision**: Improved metadata extraction to avoid false matches (e.g., "Repository" vs "Location Depicted")

#### UI and Styling
- **Panel heading colors**: Fixed h1-h6 elements in panel bodies to use correct theme text colors instead of wrong CSS variables
- **Hyperlink colors in panels**: All links (footnotes and general hyperlinks) now use theme link color via `var(--color-link)`
- **Glossary popup title**: Fixed bug where popup displayed link text instead of actual glossary term title; now correctly extracts title from h1 tag
- **Carousel display bug**: Fixed all slides showing simultaneously by adding explicit display:none/flex rules

#### Mobile Layout
- **Mobile panel heights**: Fixed viewer/narrative split and panel positioning on mobile devices
- **Mobile layout issues**: Resolved various mobile-specific layout problems with panel stacking and viewport calculations

#### Multilingual
- **Step number localization**: Fixed Spanish sites showing "Step X" instead of "Paso X" by using language file lookups in JavaScript

### Migration

- **v034_to_v040 migration script**: Automated upgrade from v0.3.4 to v0.4.0
  - Adds `story_interface` configuration section with full comments to `_config.yml`
  - Ensures Google Sheets integration comments are present for users upgrading from earlier versions
  - Creates `_data/lang/` directory and fetches English/Spanish language files from GitHub
  - Updates all framework files (layouts, includes, scripts, styles, JavaScript)
  - Adds upgrade notification system (`_layouts/upgrade-summary.html`, `_includes/upgrade-alert.html`)
  - Fetches framework documentation files (README.md, docs/README.md)
  - Non-breaking migration: all new features are additive, existing sites continue to work
  - 6 optional manual steps for users to explore new features

## [0.3.4-beta] - 2025-10-31

### Added

- **Automated upgrade system**: Issue-based automated upgrade workflow to migrate sites from older Telar versions
  - GitHub Actions workflow (`.github/workflows/upgrade.yml`) for one-click upgrades
  - Python-based migration framework (`scripts/upgrade.py`) with modular version-specific migrations
  - Automatic version detection from `_config.yml`
  - Incremental migration support (v0.2.0 → v0.3.0 → v0.3.1 → v0.3.2 → v0.3.3 → v0.3.4)
  - Automatic upgrade branch and issue creation with categorized summary
  - User creates pull request manually from issue link when ready to merge
  - Conditional manual steps section (only shown if steps required)
  - Verification checklist for post-upgrade testing
  - **v020_to_v030 migration**: Fetches Python scripts from GitHub to ensure sites receive validation logic for IIIF manifests, thumbnails, and object references
  - **v033_to_v034 migration**: Adds missing framework files (`README.md`, `docs/README.md`, layouts, includes, scripts) to ensure all sites receive updated files

- **Language configuration (WIP)**: New `telar_language` setting in `_config.yml` for future internationalization support
  - Currently supports: `en` (English), `es` (Spanish)
  - Default value: `en`
  - Migration script automatically adds this field when upgrading from earlier versions
  - **Note**: Internationalization features are work in progress; this configuration prepares sites for future multi-language support

### Fixed

- **Validation alert styling**: Fixed inconsistent styling between IIIF URL warning and upgrade success alert
  - Added `font-weight: 400 !important` to `.telar-alert` CSS class to prevent lighter font weight inheritance from `.page-content` wrapper
  - Ensures all validation warnings (theme, Google Sheets, objects, stories, IIIF URL, upgrade) display with consistent typography regardless of HTML placement

## [0.3.3-beta] - 2025-10-28

### Fixed

- **GitHub Actions workflow**: Removed git push step that conflicted with branch protection rules. The workflow was attempting to commit generated files back to the protected main branch, causing deployment failures. Generated files are build artifacts that don't need to be committed to the repository.

## [0.3.2-beta] - 2025-10-28

### Added

- **Image sizing in panel markdown**: New syntax `![alt](path){size}` for controlling image sizes in panel content
  - Supports both short (`sm`, `md`, `lg`, `full`) and long (`small`, `medium`, `large`) size names
  - Default path for relative images: `/components/images/additional/`
  - Sizes: small (250px), medium (450px, default), large (700px), full-width (100%)
  - Absolute paths and URLs work as expected
  - Example: `![Description](image.jpg){large}` or `![Photo](/assets/photo.jpg){sm}`
- **Markdown syntax documentation**: Comprehensive reference guide added to documentation site covering all markdown features, image sizing, rich media embeds, code blocks, footnotes, and best practices

### Changed

- **Default panel image size**: Increased from 300px to 450px max-width for better visibility
- **Scheduled builds removed**: Removed daily midnight cron job from build workflow. Builds now only trigger on push to main or manual workflow dispatch.
- **Index page refactored for easier customization**: Moved `index.html` to `_layouts/index.html` and created editable `index.md` in root directory
  - Users can now customize welcome message, stories heading, and objects section text in simple markdown
  - Demo site notice is now in markdown and easily removable
  - Support for `{count}` placeholder in objects intro text
  - Customizable via frontmatter: `stories_heading`, `stories_intro`, `objects_heading`, `objects_intro`

## [0.3.1-beta] - 2025-10-26

### Fixed

- **Critical thumbnail loading bug**: Fixed thumbnails not displaying on objects page due to empty string handling in Liquid templates. Objects with empty `thumbnail` or `iiif_manifest` values now properly fall through to appropriate fallback logic.
- **Local image viewer bug**: Fixed local images (self-hosted IIIF) not loading in object detail pages due to empty `iiif_manifest` string being treated as truthy in Liquid conditionals.
- **Objects gallery thumbnails**: Fixed local image thumbnails not loading in objects gallery by adding non-empty string checks to all `iiif_manifest` conditionals.

## [0.3.0-beta] - 2025-10-25

### Added

- **Google Sheets integration**: Config-based workflow supporting both GitHub Pages and local development. Users paste shared and published URLs into `_config.yml` for automatic GID discovery and CSV fetching. No GitHub Secrets required.
  - `fetch_google_sheets.py` script for local CSV fetching
  - `discover_sheet_gids.py` for automatic tab GID discovery from published sheets
  - Excel template with demo data at `docs/google_sheets_integration/telar-template.xlsx`
  - Google Sheets Template available and can easily be duplicated, at https://bit.ly/telar-template
  - Local development guide at `docs/google_sheets_integration/README.md`
  - **Instruction rows and columns**: Add notes and instructions directly in Google Sheets or CSVs that are automatically filtered out during processing
    - Rows starting with `#` are skipped (useful for section breaks, TODOs, and temporary comments)
    - Columns with names starting with `#` (e.g., `# Instructions`, `# Notes`) are ignored during JSON conversion
    - Template includes `# Instructions` column with examples for user guidance
- **Comprehensive error messaging system**: User-friendly warnings displayed on index, objects, and story pages when configuration issues are detected
- **Object ID validation**: Automatic stripping of file extensions from object IDs and warnings for spaces in filenames
- **IIIF manifest validation**: Full validation of external IIIF manifests with detailed error messages
- **Thumbnail validation**: Automatic detection and clearing of invalid thumbnail values (placeholders, non-image files)
- **Build-time warnings**: Console logging with structured [INFO] and [WARN] messages during CSV to JSON conversion
- **Index page issue summary**: Context-aware warnings that link directly to affected objects or stories
- **Objects gallery warnings**: Summary of all objects with configuration issues with links to details
- **Story intro warnings**: Display of configuration issues before users scroll, preventing confusion
- **Panel error handling**: JavaScript-based detection and display of missing images in panel content
- **IIIF manifest copy button**: Object pages now display the full IIIF manifest URL in a copyable code box with one-click copy functionality
- **Individual coordinate copy buttons**: Each coordinate (X, Y, Zoom) in the coordinate identification panel now has its own copy button for quick copying of individual values
- **Theme system**: Flexible theming system with 4 preset themes and support for custom themes
  - Preset themes: Paisajes Coloniales (default), Neogranadina, Santa Barbara, and Austin
  - Easy theme switching via `_config.yml` with single-line configuration
  - Customizable colors (primary, secondary, panel backgrounds) and fonts (headings, body)
  - Advanced users can create `_data/themes/custom.yml` for fully custom themes (gitignored by default)
  - Dynamic CSS generation using SCSS with Liquid templating

### Fixed

- **Orphaned file cleanup**: generate_collections.py now properly removes old files before generating new ones, preventing stale content

### Changed

- **Default content management**: Google Sheets is now the recommended default workflow, with CSV files as an optional alternative for users who prefer direct file editing
- **Error message clarity**: All user-facing errors reference "configuration CSV or Google Sheet" for clarity
- **Object warning field**: Added object_warning to Jekyll collection frontmatter for template access
- **Objects CSV column order**: Moved iiif_manifest to position 4 (after description) for better visibility and logical grouping
- **Story CSV column order**: Reordered columns to group related fields - object and coordinates (x, y, zoom) now appear at start after step number, followed by question/answer, then panel configuration
- **Story intro layout**: Intro slide now appears in the narrative column (left side) instead of full-screen, with step 1's viewer visible immediately on the right for a cleaner, more consistent experience
- **Glossary page styling**: Glossary term links now use theme link colors and body font for consistent theming
- **Glossary navigation**: Clicking glossary terms on the glossary index page now opens a slide-over panel instead of navigating to separate pages, providing a smoother browsing experience
  - Panels slide away and then back in when switching between terms for smooth transitions
  - Glossary panels are narrower than story layer 2 panels (45% vs 55%) for clear visual hierarchy
  - Back button added to glossary panel header for easy dismissal, matching story panel design
- **Theme fallback system**: Multi-tier protection against theme configuration errors
  - Three types of error detection: missing theme, malformed YAML, or critical system failure
  - Automatic fallback to paisajes (default) theme when configured theme is unavailable
  - Protected fallback copy in `scripts/defaults/themes/` as ultimate backup
  - Hardcoded CSS defaults ensure site functions even if all theme files are damaged
  - User-friendly warning messages on index page explain issues and suggest fixes

### Removed

- **Deprecated glossary CSV workflow**: Glossary feature now sources content exclusively from markdown files in `_glossary/`. CSV-based glossary input has been removed.
- **Non-functional project.csv fields**: Removed `primary_color`, `secondary_color`, `font_headings`, and `font_body` from `project.csv` (these values were not being used by templates). Theme customization now handled via the new theme system in `_data/themes/`.

## [0.2.0-beta] - 2025-10-20

### Changed

- **Scrolling system overhaul**: Replaced Scrollama library with custom discrete step-based card stacking architecture to enable **multiple IIIF objects within a single story**. Each object gets its own preloaded viewer card that slides up/down as users navigate through steps.
- **Animation timing**: Reduced viewer pan/zoom animation duration from 36 seconds to 4 seconds for more natural pacing
- **Cleaner viewer UI**: Hidden UniversalViewer color picker and adjustment panels for distraction-free viewing

### Fixed

- **Critical navigation bug**: Fixed viewer cards getting stuck or invisible after backward→forward navigation cycles
- **Z-index layering**: Resolved issue where reused viewer cards appeared behind currently visible cards
- **State management**: Added complete state reset when reusing viewer cards (clears inline styles, transitions, opacity)
- **Intro handling**: Improved viewer reference management when navigating to/from story intro

### Added

- **Story 2 showcase**: Added comprehensive demo story with rich media examples (images, videos, markdown formatting)
- **Enhanced logging**: Improved console debugging messages for bounds checking and state transitions

## [0.1.1-beta] - 2025-10-16

### Fixed

- Fixed IIIF thumbnails loading at low resolution on home and objects pages by extracting 400px canvas images instead of tiny thumbnail properties
- Fixed markdown syntax not rendering in panels by adding markdown-to-HTML conversion in csv_to_json.py script
- Added comprehensive footnote styling for both panel layers with proper contrast and visual hierarchy
- Added markdown module to requirements.txt for GitHub Actions CI/CD compatibility
- Fixed image URLs in slide-over panels not working when site is deployed to subdirectories by automatically detecting and prepending the base URL

## [0.1.0-beta] - 2025-10-14

### Current Features (Working)

- **IIIF integration** - Local images with auto-generated tiles
- **External IIIF** - Support for remote IIIF Image API
- **Scrollytelling** - Coordinate-based navigation with UniversalViewer
- **Layered panels** - Two content layers (Layer 1 and Layer 2)
- **Glossary pages** - Standalone term definition pages at `/glossary/{term_id}/`
- **Object gallery** - Browsable grid with detail pages
- **Coordinate identification tool** - Interactive tool to find x,y,zoom values on object pages
- **Components architecture** - CSV files + markdown content separation
- **CSV to JSON workflow** - Python scripts for data processing
- **IIIF tile generation** - Automated image pyramid creation with iiif-static
- **GitHub Actions ready** - Automated builds and deployment pipeline

### Planned Features (Not Yet Implemented)

**Planned for v0.2:**
- **Glossary auto-linking** - Automatic detection and linking of terms within narrative text
- **Google Sheets integration** - Edit content via web interface without CSV files
- **Visual story editor** - Point-and-click coordinate selection

**Future versions:**
- **Annotation support** - Clickable markers on IIIF images that open panels with additional information
- **Multi-language support** - Internationalization and localization
- **3D object support** - Integration with 3D viewers
- **Timeline visualizations** - Temporal navigation for chronological narratives
- **Advanced theming options** - Customizable design templates

### Known Limitations

- Content must be edited as CSV files and markdown (no web interface yet)
- Local development requires Python 3.9+ and Ruby 3.0+ setup
- Coordinate identification tool requires running Jekyll locally or on published site
- Story coordinates must be manually entered in CSV files

### Technical Details

- **Framework**: Jekyll 4.3+ static site generator
- **IIIF Viewer**: UniversalViewer 4.0
- **Scrollytelling**: Custom discrete step-based card stacking system
- **Styling**: Bootstrap 5
- **Image Processing**: Python iiif-static library

### Notes

This is a beta release for testing. The framework is feature-complete for CSV-based workflows but has not been extensively tested with real-world projects. We welcome feedback and bug reports via [GitHub Issues](https://github.com/UCSB-AMPLab/telar/issues).

### Getting Started

See [README.md](README.md) for installation and usage instructions.
