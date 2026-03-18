"""
Migration from v0.9.3-beta to v0.9.4-beta.

Bug fix release:
- Add PyMuPDF dependency to requirements.txt for PDF object support

CI was skipping IIIF tile generation for PDF objects because PyMuPDF
was not listed in requirements.txt.

No _config.yml changes beyond version bump. No CSV schema changes.

Version: v0.9.4-beta
"""

from typing import List, Dict
from .base import BaseMigration


class Migration093to094(BaseMigration):
    """Migration from v0.9.3 to v0.9.4 - PyMuPDF dependency fix."""

    from_version = "0.9.3-beta"
    to_version = "0.9.4-beta"
    description = "Add PyMuPDF dependency for PDF object support"

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
        if self._update_config_version("0.9.4-beta", today):
            changes.append(f"Updated _config.yml: version 0.9.4-beta ({today})")

        return changes

    def _update_framework_files(self) -> List[str]:
        """Update framework files from GitHub repository."""
        changes = []

        framework_files = {
            # Dependency fix
            'requirements.txt': 'Add PyMuPDF for PDF IIIF tile generation',
            # Changelog
            'CHANGELOG.md': 'Added v0.9.4-beta changelog entry',
        }

        for file_path, description in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path} - {description}")
            else:
                changes.append(f"Warning: Could not fetch {file_path}")

        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """Return manual steps in user's language."""
        lang = self._detect_language()
        if lang == 'es':
            return self._get_manual_steps_es()
        else:
            return self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        """English manual steps for v0.9.4 migration."""
        return [
            {
                'description': '''**If you use GitHub Pages:**

No action needed. The updated requirements.txt will be picked up automatically on the next build. If your site has PDF objects, trigger a rebuild to generate their IIIF tiles: go to your repository's Actions tab, select the "Build and Deploy" workflow, and click **Run workflow**.''',
            },
            {
                'description': '''**If you work with your site locally:**

Install the new dependency:

`pip install PyMuPDF`

If your site has PDF objects and their IIIF tiles were not previously generated, regenerate them:

`python3 scripts/generate_iiif.py --base-url YOUR_SITE_URL`

(Replace YOUR_SITE_URL with your site's URL, e.g. https://yourusername.github.io/your-repo)''',
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        """Spanish manual steps for v0.9.4 migration."""
        return [
            {
                'description': '''**Si usas GitHub Pages:**

No se requiere ninguna acción. El archivo requirements.txt actualizado se aplicará automáticamente en la proxima construccion. Si el sitio tiene objetos PDF, inicia una reconstruccion para generar sus teselas IIIF: ve a la pestana Actions del repositorio, selecciona el flujo "Build and Deploy" y haz clic en **Run workflow**.''',
            },
            {
                'description': '''**Si trabajas con tu sitio localmente:**

Instala la nueva dependencia:

`pip install PyMuPDF`

Si el sitio tiene objetos PDF y sus teselas IIIF no se generaron previamente, regeneralas:

`python3 scripts/generate_iiif.py --base-url URL_DE_TU_SITIO`

(Reemplaza URL_DE_TU_SITIO con la URL del sitio, ej. https://tuusuario.github.io/tu-repositorio)''',
            },
        ]
