# Changelog

All notable changes to Telar will be documented in this file.

## [0.5.0-beta] - Unreleased

### Added

#### Version Headers in All Code Files
- All Python scripts now include version headers (`Version: v0.5.0-beta`) in docstrings
- All JavaScript files now include version headers (`@version v0.5.0-beta`) in JSDoc comments
- CSS/SCSS files now include version headers (`@version v0.5.0-beta`) in header comments
- GitHub Actions workflows now include version headers (`Version: v0.5.0-beta`) in YAML comments
- **Files updated**: `generate_iiif.py`, `csv_to_json.py`, `fetch_google_sheets.py`, `generate_collections.py`, `upgrade.py`, `story.js`, `telar.js`, `widgets.js`, `embed.js`, `telar.scss`, and all workflow files
- **Benefit**: Easier tracking of which release a file was last modified in, better version control visibility, improved maintainability

#### Embed Mode Support
- New `embed.js` script for iframe embedding detection via URL parameters
- Support for `?embed=true` URL parameter to enable embed mode
- "View full site" banner in embed mode (dismissible, persists via sessionStorage)
- Material Icons used for banner icons (open_in_new, close)
- Embed mode CSS to hide navigation chrome (home button)
- Navigation buttons always visible in embed mode (same as mobile)

#### Responsive Typography for Slide-Over Panels
- Extended robust width- and height-based responsive typography to panel contents
- **Problem**: Panel text used fixed font sizes, didn't scale with viewport dimensions
- **Solution**: Apply same clamp()-based fluid typography used in story steps
- Added max-width constraints for images in panels to prevent overflow on narrow screens
- **Benefit**: Improved readability across all device sizes, especially mobile and tablets
- **Technical**: Uses CSS `clamp()` for fluid font scaling based on viewport width and height

#### Mobile Panel Quality-of-Life Improvements
- Fixed navigation button cutoff in mobile/embed mode
  - **Problem**: Panel-trigger buttons were cut off when story-step content exceeded 40vh height
  - **Solution**: Changed story steps from `overflow: hidden` to `overflow-y: auto` on mobile
  - **Benefit**: Users can now scroll within step panels to see all content and buttons
- Fixed panel image overflow on mobile devices
  - **Problem**: Images with fixed pixel widths (450px default, sm/md/lg classes) overflowed on narrow screens
  - **Solution**: Added mobile media query to force all panel images to `max-width: 100%` on screens ≤768px
  - **Benefit**: Images now respect panel width constraints on mobile while preserving desktop sizing behavior

#### Automatic Carousel Height Detection
- Carousels now automatically adapt height based on image aspect ratios at build time
- **Feature**: Image dimension analysis during widget processing
  - Added `get_image_dimensions()` function to `csv_to_json.py` using PIL/Pillow
  - Fetches dimensions from both local images and remote URLs
  - Analyzes aspect ratios (height/width) for all images in each carousel
- **Size Classes**: Four automatic height variants based on maximum aspect ratio:
  - **Compact** (400px): Wide panoramas (aspect ratio < 0.6)
  - **Default** (550px): Landscape images (aspect ratio 0.6-1.0)
  - **Tall** (700px): Square to mild portrait (aspect ratio 1.0-1.5)
  - **Portrait** (850px): Strong portrait orientation (aspect ratio > 1.5)
- **Implementation**: Modified `parse_carousel_widget()` to calculate aspect ratios and assign size class, updated carousel template to apply dynamic classes, added CSS variants in `telar.scss`
- **Benefit**: Portrait and tall images display at appropriate heights without manual configuration, eliminating the need for users to specify carousel heights
- **Performance**: Zero runtime cost - all analysis happens at build time

#### Carousel Widget Styling Improvements
- Moved captions strictly below images (removed overlay)
- Added black background to carousel container for better image contrast
- Reduced caption typography for cleaner appearance (0.9rem text, 0.8rem credit, minimal line-height)
- Positioned carousel indicators above caption area (bottom: 90px) to prevent text overlap
- Disabled keyboard arrow navigation on carousels to prevent interference with story navigation
- **Benefit**: Cleaner visual presentation, better accessibility with non-overlaid captions, improved usability

### Changed

#### Flattened Image Directory Structure
- Simplified `components/images/` directory structure by removing subdirectories
- **Old structure**: `components/images/objects/` and `components/images/additional/`
- **New structure**: All images in `components/images/` (with optional project-specific subfolders like `paisajes/`)
- Updated `csv_to_json.py` default path from `/components/images/additional/` to `/components/images/`
- Updated `generate_iiif.py` to use `components/images/` as default source directory
- Updated CSV validation to check for images in flattened structure
- **Benefit**: Simpler structure, easier to manage, fewer nested directories
- **Migration**: Automatic - `generate_iiif.py` now reads `objects.json` to determine which images need tiles

#### CSV-Driven IIIF Tile Generation
- `generate_iiif.py` now processes only objects listed in `objects.csv` (via `objects.json`)
- Skips objects with external IIIF manifests (only generates tiles for self-hosted images)
- Automatically finds image files by `object_id` (supports multiple extensions: jpg, jpeg, png, tif, tiff)
- **Before**: Processed all images in `components/images/objects/` directory
- **After**: Processes only objects referenced in CSV without external manifests
- **Benefit**: Faster generation, no orphaned tiles, explicit control over which images get processed

#### CSV-Aware GitHub Actions Monitoring
- GitHub Actions workflow now intelligently detects if changed images need IIIF processing
- **Smart change detection**: Only triggers IIIF regeneration when changed images match `object_id` entries in `objects.csv`
- **Logic**: Compares changed image filenames (without extension) against object IDs from CSV
- **Always regenerates** when `objects.csv` or `_config.yml` changes
- **Skips regeneration** when only non-image files change or images don't match any object IDs
- **Cache optimization**: Updated cache keys to monitor all of `components/images/**` instead of subdirectory
- **Benefit**: More efficient CI/CD pipeline, avoids unnecessary IIIF generation for unrelated image changes

#### Removed Unused JavaScript Dependencies
- Removed `assets/js/scrollama.min.js` - Telar uses custom scroll accumulator system, not Scrollama
- Removed `assets/js/openseadragon.min.js` - UniversalViewer bundles OpenSeadragon internally
- Removed `assets/images/openseadragon/` directory - empty placeholder
- Removed Scrollama script tag from `_layouts/story.html`
- **Impact**: Smaller bundle size, cleaner codebase, no functionality change
- **Note**: Telar's custom scroll system handles wheel events, touch swipes, button navigation, and keyboard navigation

### Fixed

#### Layer 2 Panel Heading Colors
- Fixed h2, h3, and h4 elements in layer 2 panels not inheriting panel text color
- **Problem**: Headings appeared in default blue color instead of white on dark purple background
- **Solution**: Added explicit color inheritance for all heading levels in `#panel-layer2 .offcanvas-body`
- **Impact**: Improved readability and visual consistency in layer 2 panels

#### CRITICAL: v0.4.0 Feature Restoration - Widget Processing and Data Pipeline
- **MAJOR BUG FIX**: Restored all v0.4.0 features accidentally deleted in commit f62acee (Nov 8, 2025)
- **Root cause**: Commit f62acee ("Complete v0.4.0-beta development") accidentally deleted 1,382 lines from `scripts/csv_to_json.py`, removing core v0.4.0 functionality
- **Discovery**: Widgets (accordion, carousel, tabs) not displaying; `:::widget` syntax converting to plain `<p>:::widget</p>` HTML instead of Bootstrap components

**What Was Deleted:**
- Widget system processing (~350 lines): `process_widgets()`, `parse_accordion_widget()`, `parse_carousel_widget()`, `parse_tabs_widget()`, `render_widget_html()`, `validate_image_path()`
- IIIF metadata auto-population (~400 lines): `extract_manifest_metadata()`, `detect_iiif_version()`, `extract_language_map_value()`, `find_metadata_field()`, `extract_credit()`, plus 9 helper functions
- Glossary auto-linking (~150 lines): `load_glossary_terms()`, `process_glossary_links()` for `[[term_id]]` syntax
- Multilingual support (~100 lines): `load_language_data()`, `get_lang_string()`, `load_site_language()`
- Testing features: `sanitize_dataframe()`, `inject_christmas_tree_errors()`
- Required imports: `import yaml`, `from jinja2 import Template, Environment, FileSystemLoader`

**Restoration Process:**
1. Extracted complete `csv_to_json.py` from commit 8620a96 (last working version before deletion)
2. Applied v0.5.0 updates to restored file:
   - Added version header: `Version: v0.5.0-beta`
   - Updated image paths: `/components/images/additional/` → `/components/images/` (Phase 4.1 flatten structure)
   - Updated validation paths to use flattened directory structure
3. Preserved backup of broken version: `scripts/csv_to_json.py.backup-broken`

**Impact - Features Restored:**
- **Widget processing**: Accordion, carousel, and tabs widgets now generate correct Bootstrap HTML
  - `:::accordion` → `<div class="telar-widget telar-widget-accordion">` with Bootstrap accordion structure
  - `:::carousel` → `<div class="telar-widget telar-widget-carousel">` with Bootstrap carousel structure
  - `:::tabs` → `<div class="telar-widget telar-widget-tabs">` with Bootstrap tabs structure
- **IIIF metadata extraction**: Auto-population of object metadata (title, creator, period, location, credit) from IIIF manifests
- **Glossary auto-linking**: `[[term_id]]` and `[[term_id|display text]]` syntax processing in markdown
- **Multilingual support**: Language string loading and interpolation for build-time processing
- **Build-time validation**: Widget error checking, image path validation, accessibility warnings

**Testing:**
- `python3 scripts/csv_to_json.py` runs successfully
- Widget HTML generation confirmed in `_data/story-1.json`:
  - Accordion widget found in step 4 (Mayorazgo content)
  - Carousel widget found in step 2 (Bogotá Savanna content)
- All v0.4.0 data processing features functional

**Note**: Additional restoration work needed for:
- Widget styling (panel-specific CSS in `telar.scss`) - to be addressed in follow-up commit
- Glossary link functionality (enhanced JS in `telar.js`) - to be addressed in follow-up commit
- Widget initialization (loading `widgets.js` in `story.html`) - to be addressed in follow-up commit

**Files Modified:**
- `scripts/csv_to_json.py` - 1,382 lines restored (746 lines total)
- `scripts/csv_to_json.py.backup-broken` - Preserved for reference

#### CRITICAL: v0.4.0 Feature Restoration - Widget Display and Glossary Links (Phase 2)
- **Continuation of Phase 1**: Restored remaining v0.4.0 features deleted in commit f62acee
- **Focus**: Frontend display components (CSS, JavaScript, HTML) for widgets and glossary functionality

**What Was Restored:**

1. **Widget Panel-Specific Styling** (assets/css/telar.scss) - ~60 lines
   - Panel-specific widget backgrounds: Layer 1 widgets use Layer 2 panel colors for visual contrast
   - Carousel caption panel colors: Layer 1 captions use Layer 2 bg/text, Layer 2 captions use Layer 1 bg/text
   - Tabs panel-specific styling: Tab navigation and content colored according to parent panel
   - Accordion panel-specific styling: Accordion items, buttons, and bodies inherit panel colors

2. **Enhanced Glossary Link Functionality** (assets/js/telar.js) - ~40 lines
   - Support for both `.glossary-term-link` (glossary index) and `.glossary-inline-link` (story content) selectors
   - Container parameter for `initializeGlossaryLinks()` to support dynamic content re-initialization
   - Extracted `handleGlossaryLinkClick()` function for proper event listener cleanup
   - Export to `window.Telar.initializeGlossaryLinks` for use in dynamically loaded panels
   - **Title extraction fix**: Glossary panels now show proper term title from metadata instead of link text
     - JavaScript extracts `<h1>` content from fetched glossary page
     - Replaces temporary link text with actual term title

3. **Widget Initialization** (_layouts/story.html)
   - Added `<script src="{{ '/assets/js/widgets.js' | relative_url }}"></script>` after story.js
   - Enables Bootstrap carousel initialization for carousel widgets

4. **Glossary Panel Language Integration** (_includes/panels.html) - ~15 lines
   - Restored "Key term:" prefix with language support (`{{ lang.panels.glossary_term_prefix }}`)
   - Replaced all hardcoded English strings with Liquid variables:
     - Back buttons: `← Back` → `{{ lang.buttons.back }}`
     - Panel titles: `Panel Title` → `{{ lang.panels.default_title }}`
     - Glossary title: `Glossary Term` → `{{ lang.panels.glossary_term_title }}`
   - Restored CSS for `.glossary-term-prefix` (opacity: 0.5, margin-bottom: 0.25rem)
   - **Multilingual support**: Works with existing English/Spanish language files

**Impact - Features Restored:**
- **Widget visual integration**: Widgets now properly themed with opposite panel colors
  - Example: Dark purple widget backgrounds on white Layer 1 panels
  - Example: White widget backgrounds on dark purple Layer 2 panels
- **Carousel functionality**: Carousel navigation (prev/next/indicators) now works correctly
- **Glossary link clicking**: Both glossary index links and inline `[[term]]` links open glossary panel
- **Proper glossary titles**: Panels show "Livestock" instead of link text "cattle"
- **Multilingual UI**: Panel labels display in configured language (English or Spanish)

**Testing:**
- Build successful: `bundle exec jekyll build` completes without errors
- Language strings verified in built HTML:
  - English (en): "Key term:", "← Back"
  - Spanish (es): "Palabra clave:", "← Atrás"
- Widget HTML structure validated in `_data/story-1.json`
- Glossary inline links found with correct `data-term-id` attributes

**Files Modified:**
- `assets/css/telar.scss` - ~60 lines added (panel-specific widget styling)
- `assets/js/telar.js` - ~40 lines added/modified (enhanced glossary links, title extraction)
- `_layouts/story.html` - 1 line added (widgets.js script tag)
- `_includes/panels.html` - ~15 lines modified (language strings, glossary prefix)
- `_data/*.json` - Regenerated with restored widget HTML

**Historical Reference:**
The pre-restoration broken state is preserved in git commit f62acee (2025-11-08)

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
