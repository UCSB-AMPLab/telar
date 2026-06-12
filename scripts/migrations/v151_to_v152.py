"""
Migration from v1.5.1 to v1.5.2.

Validation banner fixes. The warning banner that appears when a story has
content or configuration issues no longer shows a literal {{ file_path }}
placeholder in its glossary message or repeats its heading, and the homepage
warning banners now follow the site language instead of always showing
English. This is a display-only release — the story step schema, CSV
formats, and build pipeline behaviour are unchanged, so there are no
user-content transforms. Existing stories, objects, and configuration keep
working without edits.

What the upgrade does:

Framework files (fetched from the v1.5.2 release tag, not the moving `main`
branch, and written atomically — all or nothing):

  - _data/languages/en.yml — reworded glossary warning (names the missing
    term cleanly, points to the glossary spreadsheet as well as the markdown
    folder); new errors.story_or key for the homepage banner list.
  - _data/languages/es.yml — the same two changes in Spanish.
  - _layouts/story.html — the validation banner shows a proper heading
    instead of repeating its description line.
  - _layouts/index.html — homepage warning banners (headings and the
    "Navigate to ... to see more details." line) read from the language
    pack instead of hardcoded English.
  - scripts/telar/glossary.py — the warning call no longer passes an
    argument the message never used.

There are no workflow, script-behaviour, style, or content changes, so
there are no manual steps — a GitHub Pages site picks up the fix on its
next build, and a local site need only rebuild.

The version stamp (telar.version -> 1.5.2) is not written here. upgrade.py
applies it once after every migration step succeeds, so a failed fetch can
never leave the site stamped as a version it is not running.

Version: v1.5.2
"""

from typing import Dict, List

from .base import BaseMigration, ChangeRecord


# Framework files fetched from the v1.5.2 release tag and written atomically.
# Only the display files that changed in v1.5.2. The _config.yml version stamp
# is applied by upgrade.py; the CHANGELOG is not part of a site's runtime. The
# upgrade engine (upgrade.py, migrations/, base.py, messages.py) ships via the
# verified release tarball.
FRAMEWORK_FILES = {
    '_data/languages/en.yml': 'English language pack (reworded glossary warning; story_or key)',
    '_data/languages/es.yml': 'Spanish language pack (reworded glossary warning; story_or key)',
    '_layouts/story.html': 'Story layout — validation banner heading no longer repeated',
    '_layouts/index.html': 'Home layout — warning banners read from the language pack',
    'scripts/telar/glossary.py': 'Glossary — warning call matches the message template',
}


class Migration151to152(BaseMigration):
    """Migration from v1.5.1 to v1.5.2 — validation banner fixes; display-only."""

    from_version = "1.5.1"
    to_version = "1.5.2"
    description = "Validation banner message fixes and homepage warning localisation; display-only"

    # Pin framework-file fetches to the v1.5.2 release tag, not the moving
    # `main` branch, so this migration always installs v1.5.2 files.
    _TARGET_TAG = "v1.5.2"

    def check_applicable(self) -> bool:
        return True

    def apply(self) -> List[ChangeRecord]:
        # Install framework files atomically from the pinned tag. There are no
        # other phases: no directory, config, CSV, or cleanup changes. upgrade.py
        # stamps the version once after all steps succeed.
        print("  Phase 1: Updating framework files...")
        return self._update_framework_files()

    def _update_framework_files(self) -> List[ChangeRecord]:
        """Install every changed v1.5.2 framework file from the pinned tag.

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

- **If you use GitHub Pages:** your site picks up the fix automatically the next time it builds.
- **If you work with your site locally:** just rebuild your site to use the updated warning messages.''',
                'doc_url': 'https://telar.org/docs'
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**No se requiere ninguna acción.** Esta corrección solo afecta los mensajes que se muestran en pantalla.

- **Si usas GitHub Pages:** tu sitio aplica la corrección automáticamente la próxima vez que se construye.
- **Si trabajas con tu sitio localmente:** solo vuelve a construir el sitio para usar los mensajes de advertencia actualizados.''',
                'doc_url': 'https://telar.org/guia'
            },
        ]
