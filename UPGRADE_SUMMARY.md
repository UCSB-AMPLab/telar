---
layout: default
title: Upgrade Summary
---

## Upgrade Summary
- **From:** 0.4.0-beta
- **To:** 0.4.2-beta
- **Date:** 2025-11-14
- **Automated changes:** 13
- **Manual steps:** 6

## Automated Changes Applied

### Layouts (5 files)

- [x] Updated index layout (site description link styling)
- [x] Updated object layout (coordinate picker buttons)
- [x] Updated story layout (mobile responsive features restored)
- [x] Updated telar styles (mobile responsive features, gallery layout)
- [x] Updated _layouts/index.html: Updated index layout (site description link styling)

### Styles (1 file)

- [x] Updated assets/css/telar.scss: Updated CSS (mobile navbar, font sizes, title wrapping)

### Scripts (1 file)

- [x] Updated story JavaScript (mobile navigation, preloading, transitions)

### Documentation (2 files)

- [x] Updated README (supporter acknowledgments)
- [x] Updated README.md: Updated README (version 0.4.2-beta)

### Other (4 files)

- [x] Updated English language file with coordinate picker strings
- [x] Updated Spanish language file with coordinate picker strings
- [x] Updated CHANGELOG
- [x] Updated .github/workflows/build.yml: Updated build workflow (smart IIIF detection with caching)

## Manual Steps Required

Please complete these after merging:

1. Update your upgrade workflow file (one-time fix to prevent config comment deletion): (1) Go to https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/upgrade.yml (2) Select all (Ctrl/Cmd+A) and copy (3) In your repository, navigate to .github/workflows/upgrade.yml (4) Click the pencil icon to edit (5) Select all existing content and delete it (6) Paste the new content (7) Scroll to bottom and click "Commit changes". This fixes a bug that was stripping documentation comments from your _config.yml file during upgrades. ([guide](https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/upgrade.yml))
2. Run "bundle exec jekyll build" to test your upgraded site
3. Test mobile responsive features on small screens (optional)
4. Try the new coordinate picker buttons in object pages (optional)
5. CRITICAL: The updated build.yml workflow must be merged/committed for IIIF caching to work. If using automated upgrade workflow: Review and MERGE the upgrade pull request - the new build workflow will not take effect until merged. If upgrading locally: COMMIT and PUSH .github/workflows/build.yml - the new workflow is not active until pushed to GitHub. Until the new workflow is active, the IIIF caching protection is not in effect.
6. Test the smart IIIF detection: Make a content-only change (edit a story markdown file), push to GitHub, and verify the build workflow completes faster by skipping IIIF regeneration (optional)

## Resources

- [Full Documentation](https://telar.org/docs)
- [CHANGELOG](https://github.com/UCSB-AMPLab/telar/blob/main/CHANGELOG.md)
- [Report Issues](https://github.com/UCSB-AMPLab/telar/issues)
