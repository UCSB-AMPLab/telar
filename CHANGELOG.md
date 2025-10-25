# Changelog

All notable changes to Telar will be documented in this file.

## [0.3.0-beta] - [Unreleased]

### Added

- **Comprehensive error messaging system**: User-friendly warnings displayed on index, objects, and story pages when configuration issues are detected
- **Object ID validation**: Automatic stripping of file extensions from object IDs and warnings for spaces in filenames
- **IIIF manifest validation**: Full validation of external IIIF manifests with detailed error messages
- **Thumbnail validation**: Automatic detection and clearing of invalid thumbnail values (placeholders, non-image files)
- **Build-time warnings**: Console logging with structured [INFO] and [WARN] messages during CSV to JSON conversion
- **Index page issue summary**: Context-aware warnings that link directly to affected objects or stories
- **Objects gallery warnings**: Summary of all objects with configuration issues with links to details
- **Story intro warnings**: Display of configuration issues before users scroll, preventing confusion
- **Panel error handling**: JavaScript-based detection and display of missing images in panel content

### Fixed

- **Orphaned file cleanup**: generate_collections.py now properly removes old files before generating new ones, preventing stale content

### Changed

- **Error message clarity**: All user-facing errors reference "configuration CSV or Google Sheet" for clarity
- **Object warning field**: Added object_warning to Jekyll collection frontmatter for template access
- **Objects CSV column order**: Moved iiif_manifest to position 4 (after description) for better visibility and logical grouping
- **Story CSV column order**: Reordered columns to group related fields - object and coordinates (x, y, zoom) now appear at start after step number, followed by question/answer, then panel configuration

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
