"""
Migration from v1.5.2 to v1.5.3.

Internationalization patch. Built-in chrome strings that previously leaked
English on translated sites (telar_language: es) now follow the language
pack: the back-to-collection / back-to-glossary links, the coordinate tool
button and its copy tooltips, the image-viewer-unavailable alerts, the
Google Sheets and theme config-error banners, the thumbnail loading
placeholders, the footer credit, and the upgrade summary message. The
objects and glossary page headings, and the home/objects/glossary
browser-tab titles, now read from the language pack as well.

This is a display/i18n release — the story step schema, CSV formats, and
build pipeline behaviour are unchanged, so there are no user-content
transforms. Existing stories, objects, and configuration keep working
without edits.

What the upgrade does:

Framework files (fetched from the v1.5.3 release tag, not the moving `main`
branch, and written atomically — all or nothing):

  - _data/languages/en.yml, es.yml — three new keys (loading, objects.medium,
    footer.built_with) wired into the templates, and the theme config-error
    strings normalized to a brace-free __THEME__ token. en/es stay at parity.
  - _layouts/default.html — a title_key resolver drives the browser-tab title
    from the language pack, and jekyll-seo-tag no longer emits a second,
    English <title>.
  - _layouts/index.html — Google Sheets and theme config-error banners, and
    the thumbnail loading placeholders, read from the language pack.
  - _layouts/object.html — back-to-collection link, coordinate tool button,
    copy tooltips, and the image-viewer-unavailable alert read from the pack.
  - _layouts/objects-index.html — heading and facet labels read from the pack;
    the media-type facet points at the existing objects.type key.
  - _layouts/glossary-index.html, glossary.html — heading and back link from the pack.
  - _layouts/upgrade-summary.html — the upgrade summary message from the pack.
  - _includes/footer.html — translatable "Built with Telar ..." credit.
  - _includes/story-step.html — image-viewer-unavailable alert and learn-more
    fallback from the pack.
  - _includes/viewer.html — the viewer-overlay loading text from the pack.

The home/objects/glossary browser-tab titles are localized through a new
title_key front-matter field on index.md / pages/objects.md / pages/glossary.md.
Those are scaffold pages that existing sites already own, so the upgrade does
not overwrite them; adding title_key is an optional manual step. Without it,
those three tab titles fall back to their English front-matter title — no
regression — while every other string above already follows the site language.

The version stamp (telar.version -> 1.5.3) is not written here. upgrade.py
applies it once after every migration step succeeds, so a failed fetch can
never leave the site stamped as a version it is not running.

Version: v1.5.3
"""

from typing import Dict, List

from .base import BaseMigration, ChangeRecord


# Framework files fetched from the v1.5.3 release tag and written atomically.
# Only the template/language files that changed in v1.5.3. The scaffold pages
# (index.md, pages/objects.md, pages/glossary.md) are user-owned and are not
# fetched. The _config.yml version stamp is applied by upgrade.py; the CHANGELOG
# and README are not part of a site's runtime. The upgrade engine (upgrade.py,
# migrations/, base.py, messages.py) ships via the verified release tarball.
FRAMEWORK_FILES = {
    '_data/languages/en.yml': 'English language pack (loading, objects.medium, footer.built_with; __THEME__ token)',
    '_data/languages/es.yml': 'Spanish language pack (same three keys at parity; __THEME__ token)',
    '_layouts/default.html': 'Default layout — title_key resolver and seo title=false',
    '_layouts/index.html': 'Home layout — Google Sheets/theme banners and loading placeholders from the pack',
    '_layouts/object.html': 'Object layout — back link, coordinate tool, copy tooltips, viewer alert from the pack',
    '_layouts/objects-index.html': 'Objects index — heading and facet labels from the pack',
    '_layouts/glossary-index.html': 'Glossary index — heading from the pack',
    '_layouts/glossary.html': 'Glossary entry — back link from the pack',
    '_layouts/upgrade-summary.html': 'Upgrade summary — message from the pack',
    '_includes/footer.html': 'Footer — translatable "Built with Telar" credit',
    '_includes/story-step.html': 'Story step — viewer alert and learn-more fallback from the pack',
    '_includes/viewer.html': 'Viewer overlay — loading text from the pack',
}


class Migration152to153(BaseMigration):
    """Migration from v1.5.2 to v1.5.3 — localise built-in chrome strings; display-only."""

    from_version = "1.5.2"
    to_version = "1.5.3"
    description = "Localise built-in chrome strings on translated sites; display-only"

    # Pin framework-file fetches to the v1.5.3 release tag, not the moving
    # `main` branch, so this migration always installs v1.5.3 files.
    _TARGET_TAG = "v1.5.3"

    def check_applicable(self) -> bool:
        return True

    def apply(self) -> List[ChangeRecord]:
        # Install framework files atomically from the pinned tag. There are no
        # other phases: no directory, config, CSV, or cleanup changes. upgrade.py
        # stamps the version once after all steps succeed.
        print("  Phase 1: Updating framework files...")
        return self._update_framework_files()

    def _update_framework_files(self) -> List[ChangeRecord]:
        """Install every changed v1.5.3 framework file from the pinned tag.

        Delegates to the staged-atomic helper: all files are fetched into
        memory first, and nothing is written unless every fetch succeeds.
        """
        return self._apply_framework_files(FRAMEWORK_FILES)

    # ------------------------------------------------------------------ #
    # Manual steps (bilingual)
    # ------------------------------------------------------------------ #

    def get_manual_steps(self) -> List[Dict[str, str]]:
        lang = self._detect_language()
        return self._get_manual_steps_es() if lang == 'es' else self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**No action needed.** This is a display-only fix.

- **If you use GitHub Pages:** your site picks up the translated chrome strings automatically the next time it builds.
- **If you work with your site locally:** just rebuild your site to use them.''',
                'doc_url': 'https://telar.org/docs'
            },
            {
                'description': '''**Optional — fully translated page titles.** This release also translates the browser-tab titles of the home, objects, and glossary pages through a new `title_key` field. New sites get it automatically. To enable it on your existing site, add `title_key: navigation.home` to the front matter of `index.md`, `title_key: navigation.objects` to `pages/objects.md`, and `title_key: navigation.glossary` to `pages/glossary.md`. Without this, only those three browser-tab titles stay in English; every other string, including the page headings, already follows your site language.''',
                'doc_url': 'https://telar.org/docs'
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**No se requiere ninguna acción.** Esta corrección solo afecta los textos que se muestran en pantalla.

- **Si usas GitHub Pages:** tu sitio aplica los textos traducidos automáticamente la próxima vez que se construye.
- **Si trabajas con tu sitio localmente:** solo vuelve a construir el sitio para usarlos.''',
                'doc_url': 'https://telar.org/guia'
            },
            {
                'description': '''**Opcional — títulos de página totalmente traducidos.** Esta versión también traduce los títulos de la pestaña del navegador en las páginas de inicio, objetos y glosario mediante un nuevo campo `title_key`. Los sitios nuevos lo incluyen de forma automática. Para activarlo en tu sitio actual, agrega `title_key: navigation.home` al frontmatter de `index.md`, `title_key: navigation.objects` a `pages/objects.md` y `title_key: navigation.glossary` a `pages/glossary.md`. Sin esto, solo esos tres títulos de pestaña quedan en inglés; todo lo demás, incluidos los encabezados de las páginas, ya sigue el idioma de tu sitio.''',
                'doc_url': 'https://telar.org/guia'
            },
        ]
