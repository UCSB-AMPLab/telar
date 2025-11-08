---
layout: default
title: Upgrade Summary
---

## Upgrade Summary
- **From:** 0.3.4-beta
- **To:** 0.4.0-beta
- **Date:** 2025-11-08
- **Automated changes:** 25
- **Manual steps:** 6

## Automated Changes Applied

### Layouts (8 files)

- [x] Updated story layout (multilingual, widgets)
- [x] Updated object layout (multilingual)
- [x] Updated objects index layout (multilingual)
- [x] Updated default layout (multilingual)
- [x] Updated glossary layout (multilingual)
- [x] Updated glossary index layout (multilingual)
- [x] Updated page layout
- [x] Updated index layout (multilingual)

### Includes (5 files)

- [x] Updated story-step include (multilingual)
- [x] Updated panels include (widgets support)
- [x] Updated viewer include
- [x] Updated header include (multilingual)
- [x] Updated footer include (multilingual, theme attribution)

### Styles (1 file)

- [x] Updated telar styles (widgets, mobile responsive)

### Scripts (3 files)

- [x] Updated story JavaScript (widgets)
- [x] Updated telar JavaScript (glossary auto-linking)
- [x] Updated objects.json endpoint

### Documentation (2 files)

- [x] Updated README
- [x] Updated docs README

### Other (6 files)

- [x] Created _data/lang directory
- [x] Updated IIIF URL warning (multilingual)
- [x] Updated CSV processor (IIIF metadata extraction)
- [x] Updated collection generator (widgets, glossary)
- [x] Updated IIIF tile generator
- [x] Added upgrade notice to index.md

## Manual Steps Required

Please complete these after merging:

1. Review multilingual configuration in _config.yml (telar_language: "en" or "es") ([guide](https://ampl.clair.ucsb.edu/telar-docs/multilingual-setup))
2. Optionally add widgets to your stories (carousel, tabs, accordion) ([guide](https://ampl.clair.ucsb.edu/telar-docs/widgets))
3. Optionally create glossary terms and add [[term]] links to your content ([guide](https://ampl.clair.ucsb.edu/telar-docs/glossary))
4. Test IIIF metadata auto-population by leaving object fields blank in CSV ([guide](https://ampl.clair.ucsb.edu/telar-docs/iiif-metadata))
5. Add theme creator attribution to your theme YAML file (optional) ([guide](https://ampl.clair.ucsb.edu/telar-docs/themes#creator-attribution))
6. Run "bundle exec jekyll build" to test your upgraded site

## Resources

- [Full Documentation](https://ampl.clair.ucsb.edu/telar-docs)
- [CHANGELOG](https://github.com/UCSB-AMPLab/telar/blob/main/CHANGELOG.md)
- [Report Issues](https://github.com/UCSB-AMPLab/telar/issues)
