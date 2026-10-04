"""
Migration from v0.9.1-beta to v0.9.2-beta.

Bug fix release:
- Fix incomplete IIIF sizes array causing tile failures on Windows
- Generate TIFY 96px thumbnail for static Level 0 hosting
- Skip test workflow on user sites

No _config.yml changes beyond version bump. No CSV schema changes.
No new dependencies.

Version: v1.8.0
"""

from typing import List, Dict
from .base import BaseMigration


class Migration091to092(BaseMigration):
    """Migration from v0.9.1 to v0.9.2 - IIIF tile fix, workflow cleanup."""

    from_version = "0.9.1-beta"
    to_version = "0.9.2-beta"
    _TARGET_TAG = "v0.9.2-beta"  # pin framework fetches to the release tag
    description = "IIIF tile rendering fix, TIFY thumbnail, test workflow scoping"

    def check_applicable(self) -> bool:
        """Check if migration should run."""
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # Phase 1: Update framework files
        print("  Phase 1: Updating framework files...")
        changes.extend(self._update_framework_files())

        # Phase 2: Update version
        print("  Phase 2: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("0.9.2-beta", today):
            changes.append(f"Updated _config.yml: version 0.9.2-beta ({today})")

        return changes

    def _update_framework_files(self) -> List[str]:
        """Update framework files from GitHub repository."""
        changes = []

        framework_files = {
            'scripts/iiif_utils.py': 'Fix sizes array scanning, add 96px thumbnail',
            'scripts/generate_iiif.py': 'Updated version header',
            'scripts/process_pdf.py': 'Updated version header',
            'CHANGELOG.md': 'Added v0.9.2-beta changelog entry',
            # .github/workflows/ files cannot be pushed by the GitHub Actions
            # token (requires 'workflows' permission). Listed in manual steps.
        }

        changes.extend(self._install_files_one_by_one(
            framework_files, "Updated {path} - {description}"))

        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        lang = self._detect_language()
        return self._get_manual_steps_es() if lang == 'es' else self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**Update `.github/workflows/telar-tests.yml` and `.github/workflows/build.yml` by hand.** GitHub does not let an automated upgrade change workflow files, so this step is yours: open each file in the Telar repository on GitHub, choose "Copy raw contents", paste it over your copy, and commit. The test workflow now runs only on the main Telar repositories, so on your own site it does nothing.''',
                'audience': 'local',
            },
            {
                'description': '''**Regenerate your IIIF tiles if the site hosts its own images.** The `info.json` files written before this release carry the wrong sizes, which is what makes tiles fail to render in browsers on Windows. Run your site's build workflow, or run `python3 scripts/generate_iiif.py --base-url YOUR_SITE_URL` on your own machine.''',
                'audience': 'all',
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        return [
            {
                'description': '''**Actualiza `.github/workflows/telar-tests.yml` y `.github/workflows/build.yml` a mano.** GitHub no permite que esta actualización modifique archivos de workflow, así que este paso lo haces tú: copia cada archivo actual del repositorio de Telar sobre el tuyo (ábrelo en GitHub, usa «Copy raw contents», reemplaza el archivo completo y confirma el cambio). El workflow de pruebas ahora se ejecuta solo en los repositorios principales de Telar, así que en tu sitio no hace nada.''',
                'audience': 'local',
            },
            {
                'description': '''**Regenera las teselas IIIF si el sitio aloja sus propias imágenes.** Los archivos `info.json` que se escribieron antes de este lanzamiento traen mal los tamaños, y por eso, en Windows, las teselas no se ven en el navegador. Ejecuta el workflow que construye el sitio o, desde tu computador, `python3 scripts/generate_iiif.py --base-url URL_DE_TU_SITIO`.''',
                'audience': 'all',
            },
        ]
