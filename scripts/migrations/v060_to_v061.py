"""
Migration from v0.6.0-beta to v0.6.1-beta.

Changes:
- Fix EXIF orientation bug in IIIF thumbnail generation (scripts/generate_iiif.py)
- Fix template pollution in v0.5.0→v0.6.0 migration script (scripts/migrations/v050_to_v060.py)

Version: v0.6.1-beta
"""

from typing import List, Dict
import os
from .base import BaseMigration


class Migration060to061(BaseMigration):
    """Migration from v0.6.0 to v0.6.1 - fix EXIF thumbnails and migration script template pollution."""

    from_version = "0.6.0-beta"
    to_version = "0.6.1-beta"
    description = "Fix EXIF orientation in thumbnails, fix v0.5.0→v0.6.0 migration template pollution"

    def check_applicable(self) -> bool:
        """
        Check if migration should run.

        Returns True since v0.6.1 applies bug fixes that benefit all users.
        """
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # Phase 1: Update framework files from GitHub
        print("  Phase 1: Updating framework files...")
        framework_changes = self._update_framework_files()
        changes.extend(framework_changes)

        # Phase 2: Update _config.yml version
        print("  Phase 2: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("0.6.1-beta", today):
            changes.append(f"Updated _config.yml: version 0.6.1-beta ({today})")

        return changes

    def _update_framework_files(self) -> List[str]:
        """
        Update framework files from GitHub repository.

        Returns:
            List of change descriptions
        """
        changes = []

        # Files to update from GitHub
        framework_files = {
            # IIIF generation script - Fix EXIF orientation in thumbnails
            'scripts/generate_iiif.py': 'IIIF generation script (EXIF orientation fix)',

            # Migration script - Fix template pollution for existing sites
            'scripts/migrations/v050_to_v060.py': 'v0.5.0→v0.6.0 migration script (template pollution fix)',

            # README - Bilingual version with streamlined content
            'README.md': 'README (bilingual version)',

            # CHANGELOG - v0.6.1 release notes
            'CHANGELOG.md': 'CHANGELOG (v0.6.1 release notes)',
        }

        for file_path, description in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path} - {description}")
            else:
                changes.append(f"Warning: Failed to update {file_path}")

        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """
        Return manual steps in user's language.

        Detects site language and returns appropriate bilingual manual steps.

        Returns:
            List of manual step dicts with 'description' and optional 'doc_url' keys
        """
        lang = self._detect_language()

        if lang == 'es':
            return self._get_manual_steps_es()
        else:
            return self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        """English manual steps for v0.6.1 migration."""
        return [
            {
                'description': '''**If you use GitHub Pages:**

No further actions needed. GitHub Actions will automatically regenerate IIIF tiles with the EXIF orientation fix when your site rebuilds.''',
            },
            {
                'description': '''**If you work with your site locally:**

If you have self-hosted images with EXIF orientation metadata (most smartphone photos taken in portrait mode), regenerate IIIF tiles to fix thumbnail orientation:

`python3 scripts/generate_iiif.py --base-url YOUR_SITE_URL`

(Replace YOUR_SITE_URL with your site's URL)

You will see "Saving rotated image for IIIF processing" in the console output for affected images.''',
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        """Spanish manual steps for v0.6.1 migration."""
        return [
            {
                'description': '''**Si usas GitHub Pages:**

No se requieren acciones adicionales. GitHub Actions regenerará automáticamente las teselas IIIF con la corrección de orientación EXIF cuando se reconstruya tu sitio.''',
            },
            {
                'description': '''**Si trabajas con tu sitio localmente:**

Si tienes imágenes auto-alojadas con metadatos de orientación EXIF (la mayoría de fotos de smartphone tomadas en modo retrato), regenera las teselas IIIF para corregir la orientación de las miniaturas:

`python3 scripts/generate_iiif.py --base-url URL_DE_TU_SITIO`

(Reemplaza URL_DE_TU_SITIO con la URL de tu sitio)

Verás "Saving rotated image for IIIF processing" en la salida de consola para las imágenes afectadas.''',
            },
        ]
