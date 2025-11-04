# Changelog

All notable changes to Telar will be documented in this file.

## [0.4.0-beta] - TBD

### Added

- **Glossary auto-linking**: Automatic detection and linking of glossary terms within story narrative text using wiki-style syntax
  - New wiki-style link syntax: `[[term_id]]` or `[[term_id|display_text]]` in markdown content
  - Glossary link parser in `scripts/csv_to_json.py` with `load_glossary_terms()` and `process_glossary_links()` functions
  - Automatic transformation applied to all story layer text fields during build
  - JavaScript handler for opening glossary panel when links are clicked
  - Support for both static and dynamically-loaded panel content
  - Build-time validation with warning messages for invalid term references
  - CSS styling with theme-aware colors for glossary inline links (`.glossary-inline-link`)
  - Error indicators for nonexistent terms (`.glossary-link-error`)
  - Integration with "Christmas Tree Mode" configuration warnings
  - Bilingual error messages (English/Spanish) for glossary loading failures

- **Enhanced glossary panel functionality**: Improved support for dynamic content
  - Modified `initializeGlossaryLinks()` to accept optional container parameter for re-initialization
  - Exported function via `window.Telar.initializeGlossaryLinks` for use in dynamic content
  - Automatic re-initialization of glossary links after panel content loads via AJAX
  - Dynamic URL construction with basePath logic to properly handle `baseurl` configuration
  - Smooth panel transitions when switching between glossary terms from dynamically-loaded content

### Changed

- **Glossary link styling**: Refined visual appearance for inline glossary links
  - Reduced vertical padding from 0.15em to 0.02em for tighter fit around text
  - Increased border-radius from 3px to 6px for more rounded corners
  - Links now blend more naturally within narrative flow

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
