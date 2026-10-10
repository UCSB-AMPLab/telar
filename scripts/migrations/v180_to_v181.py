"""
Migration from v1.8.0 to v1.8.1.

v1.8.1 is a patch: story navigation, the check a build makes on a IIIF
manifest, two details of how demo content is merged, and a switch that keeps
build warnings off the published site. Only framework files change, so this
migration installs them and does nothing else.

Framework files (FRAMEWORK_FILES, installed atomically from the v1.8.1 tag):
the story bundle with its map and the three modules it is built from that
changed; the layouts and includes that show warnings; the build's config
reader, glossary pass, core, demo merge and remote-object processor; and the
root documents and dependency manifests that carry the version. The story
bundle ships with its sources, as in every release since the bundle was
introduced, so a site that rebuilds it gets the same file.

Not delivered:

  - `tests/` — Telar's own test suite, listed in `scripts/dev-only-files.txt`.
  - `scripts/migrations/` and the engine — they ship only in the verified
    release tarball, which `scripts/upgrade.py` downloads.
  - `_config.yml` — the site's own. The engine writes the version stamp.
    `development-features.hide_warnings` is not added: a site without it
    shows its warnings, as before.

No workflow, configuration key, spreadsheet column or content file changes,
so there are no manual steps beyond a note.

The version stamp (telar.version -> 1.8.1) is not written here. The engine
applies it once after every migration step and the regeneration succeed.

Version: v1.8.1
"""

from typing import Dict, List

from .base import BaseMigration, ChangeRecord


# Fetched from the v1.8.1 tag and written atomically as one set.
FRAMEWORK_FILES = {
    # Root documents and dependency manifests.
    'README.md': 'Project README for v1.8.1',
    'CHANGELOG.md': 'Release history through v1.8.1',
    'package.json': 'The version, and the story bundle banner',
    'package-lock.json': 'Lockfile matching package.json — always ships with it',

    # The story engine.
    'assets/js/telar-story.js': 'Story bundle, rebuilt from the three modules below',
    'assets/js/telar-story.js.map': 'Source map for the story bundle',
    'assets/js/telar-story/deep-link.js': 'Back to Start puts every card and viewer away',
    'assets/js/telar-story/iiif-card.js': 'The camera moves straight between two steps',
    'assets/js/telar-story/scroll-engine.js': 'Fast arrow keys no longer leave cards part-way',

    # Layouts and includes that show build warnings, each behind the switch.
    '_layouts/index.html': 'Home page warnings hidden by development-features.hide_warnings',
    '_layouts/object.html': 'Object page alert hidden by the switch',
    '_layouts/objects-index.html': 'Objects index banner hidden by the switch',
    '_layouts/story.html': 'Story warnings hidden by the switch',
    '_includes/story-step.html': 'Step viewer alert hidden by the switch',
    '_includes/iiif-url-warning.html': 'IIIF address banner hidden by the switch',

    # The build.
    'scripts/telar/config.py': 'Reads development-features.hide_warnings',
    'scripts/telar/glossary.py': 'A missing entry is the text as written when warnings are hidden',
    'scripts/telar/core.py': 'Demo glossary removed when there is no demo glossary to publish',
    'scripts/telar/demo.py': 'A demo story that lists its sections carries the setting',
    'scripts/telar/processors/objects/remote.py': 'A IIIF manifest is judged by its contents, not its Content-Type',
}


class Migration180to181(BaseMigration):
    """Migration from v1.8.0 to v1.8.1 — the framework files the patch changes."""

    from_version = "1.8.0"
    to_version = "1.8.1"
    release_date = "2026-10-09"
    description = ("v1.8.1 framework files: story navigation, IIIF manifest validation, "
                   "the demo content merge, and the switch that hides build warnings")

    _TARGET_TAG = "v1.8.1"

    def check_applicable(self) -> bool:
        return True

    def apply(self) -> List[ChangeRecord]:
        print("  Phase 1: Updating framework files...")
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
                'description': ('**No action needed.** v1.8.1 fixes story navigation and two '
                                'details of the demo content, and no longer reports some valid '
                                'IIIF manifests as invalid. The upgrade installs the Telar files '
                                "that changed; your site's content and settings are left as "
                                'they are.'),
                'audience': 'all',
                'kind': 'note',
                'doc_url': 'https://telar.org/docs/setup/upgrading/',
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        return [
            {
                'description': ('**No se requiere ninguna acción.** La versión 1.8.1 corrige la '
                                'navegación de las historias y dos detalles del contenido de '
                                'demostración, y ya no marca como inválidos algunos manifiestos '
                                'IIIF válidos. La actualización instala los archivos de Telar que '
                                'cambiaron; el contenido y la configuración del sitio quedan como '
                                'estaban.'),
                'audience': 'all',
                'kind': 'note',
                'doc_url': 'https://telar.org/guia/configuracion/actualizacion/',
            },
        ]
