"""
Migration from v1.5.0 to v1.5.1.

Glossary auto-linking fixes. The [[term]] syntax now resolves in a story
step's answer text (not only in layer panels), and glossary terms match
case-insensitively. This is a runtime/pipeline release — the story step
schema, CSV formats, and the (x, y, zoom) capture contract are unchanged,
so there are no user-content transforms. Existing stories, objects, and
configuration keep working without edits.

What the upgrade does:

Framework files (fetched from the v1.5.1 release tag, not the moving `main`
branch, and written atomically — all or nothing):

  - scripts/telar/glossary.py — case-insensitive term matching (resolved to
    the stored key) plus a helper that reduces glossary markup to plain text.
  - scripts/telar/processors/stories.py — resolve [[term]] in the step answer.
  - scripts/telar/core.py — strip glossary markup from protected-story answers
    before encryption (their runtime renderer escapes the answer).
  - assets/js/telar.js — glossary links open via a single delegated click
    handler, so links work in the story cards built at runtime.

There are no workflow, language-pack, layout, style, or content changes, so
there are no manual steps — a GitHub Pages site picks up the fix on its next
build, and a local site need only rebuild.

The version stamp (telar.version -> 1.5.1) is not written here. upgrade.py
applies it once after every migration step succeeds, so a failed fetch can
never leave the site stamped as a version it is not running.

Version: v1.5.1
"""

from typing import Dict, List

from .base import BaseMigration, ChangeRecord


# Framework files fetched from the v1.5.1 release tag and written atomically.
# Only the runtime/pipeline files that changed in v1.5.1. Tests are not shipped
# to user sites; the _config.yml version stamp is applied by upgrade.py; the
# CHANGELOG is not part of a site's runtime. The upgrade engine (upgrade.py,
# migrations/, base.py, messages.py) ships via the verified release tarball.
FRAMEWORK_FILES = {
    'scripts/telar/glossary.py': 'Glossary — case-insensitive matching + plain-text strip helper',
    'scripts/telar/processors/stories.py': 'Story processor — resolve [[term]] in the step answer',
    'scripts/telar/core.py': 'Pipeline core — strip glossary markup from protected-story answers',
    'assets/js/telar.js': 'Site JS — delegated glossary-link click handling',
}


class Migration150to151(BaseMigration):
    """Migration from v1.5.0 to v1.5.1 — glossary in step text + case-insensitive matching; runtime-only."""

    from_version = "1.5.0"
    to_version = "1.5.1"
    description = "Glossary links in story step text and case-insensitive term matching; runtime-only"

    # Pin framework-file fetches to the v1.5.1 release tag, not the moving
    # `main` branch, so this migration always installs v1.5.1 files.
    _TARGET_TAG = "v1.5.1"

    def check_applicable(self) -> bool:
        return True

    def apply(self) -> List[ChangeRecord]:
        # Install framework files atomically from the pinned tag. There are no
        # other phases: no directory, config, CSV, or cleanup changes. upgrade.py
        # stamps the version once after all steps succeed.
        print("  Phase 1: Updating framework files...")
        return self._update_framework_files()

    def _update_framework_files(self) -> List[ChangeRecord]:
        """Install every changed v1.5.1 framework file from the pinned tag.

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
                'description': '''**No action needed.** This is a runtime-only fix.

- **If you use GitHub Pages:** your site picks up the fix automatically the next time it builds.
- **If you work with your site locally:** just rebuild your site to use the updated glossary linking.''',
                'doc_url': 'https://telar.org/docs'
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**No se requiere ninguna acción.** Esta corrección solo afecta el funcionamiento del sitio.

- **Si usas GitHub Pages:** tu sitio aplica la corrección automáticamente la próxima vez que se construye.
- **Si trabajas con tu sitio localmente:** solo vuelve a construir el sitio para usar los enlaces de glosario actualizados.''',
                'doc_url': 'https://telar.org/guia'
            },
        ]
