"""
Migration from v0.9.2-beta to v0.9.3-beta.

Bug fix release:
- Fix empty scaleFactors crash for small images in IIIF tile generation
- Fix edge tile 404s for images larger than 1024px
- Fix coordinate finder column order for multi-page items
- Fix coordinate panel heading colour on dark theme backgrounds
- Fix story viewer page switching for multi-page objects
- Fix page selector text truncation for Tify 0.35
- Fix Page column case normalisation for PDF story steps
- Add coordinate panel SCSS partial (replaces inline styles)
- Add multi-page coordinate panel instructions (bilingual)
- Change object viewer to portrait orientation (4:5 aspect ratio)

No _config.yml changes beyond version bump. No CSV schema changes.
No new dependencies.

Version: v0.9.3-beta
"""

from typing import List, Dict
from .base import BaseMigration


class Migration092to093(BaseMigration):
    """Migration from v0.9.2 to v0.9.3 - IIIF fixes, multi-page bug fixes."""

    from_version = "0.9.2-beta"
    to_version = "0.9.3-beta"
    description = "IIIF tile fixes, coordinate panel restyle, multi-page page switching"

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
        if self._update_config_version("0.9.3-beta", today):
            changes.append(f"Updated _config.yml: version 0.9.3-beta ({today})")

        return changes

    def _update_framework_files(self) -> List[str]:
        """Update framework files from GitHub repository."""
        changes = []

        framework_files = {
            # IIIF fixes
            'scripts/iiif_utils.py': 'Fix scaleFactors, edge tiles, thumbnail generation order',
            # Object page
            '_layouts/object.html': 'Coordinate panel restyle, i18n, multi-page instructions',
            # Homepage and gallery thumbnails
            '_layouts/index.html': 'Smart thumbnail size selection for IIIF sizes array',
            '_layouts/objects-index.html': 'Smart thumbnail size selection for objects gallery',
            '_sass/_coordinate-panel.scss': 'New coordinate panel SCSS partial',
            '_sass/_viewer.scss': 'Portrait aspect ratio, page selector truncation fix',
            'assets/css/telar.scss': 'Add coordinate-panel import',
            # Story viewer
            'assets/js/telar-story.js': 'Rebuilt bundle with page switching fix',
            'assets/js/telar-story.js.map': 'Updated source map',
            'assets/js/telar-story/navigation.js': 'Page change detection in navigation',
            'assets/js/telar-story/viewer.js': 'Card recreation on page change',
            # CSV processing
            'scripts/telar/csv_utils.py': 'Page column case normalisation',
            # Language files
            '_data/languages/en.yml': 'Add multi-page instruction key',
            '_data/languages/es.yml': 'Add multi-page instruction key, fix possessive',
            # Changelog
            'CHANGELOG.md': 'Added v0.9.3-beta changelog entry',
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
        """English manual steps for v0.9.3 migration."""
        return [
            {
                'description': '''**If you use GitHub Pages:**

Your site will automatically regenerate IIIF tiles with the corrected info.json files when it rebuilds. To trigger a rebuild now, go to your repository's Actions tab, select the "Build and Deploy" workflow, and click **Run workflow**.''',
            },
            {
                'description': '''**If you work with your site locally:**

If your site uses self-hosted images, regenerate IIIF tiles to fix the info.json files. This corrects two issues: a crash for small images (under 512px) and incorrect edge tiles for larger images (over 1024px).

`python3 scripts/generate_iiif.py --base-url YOUR_SITE_URL`

(Replace YOUR_SITE_URL with your site's URL, e.g. https://yourusername.github.io/your-repo)''',
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        """Spanish manual steps for v0.9.3 migration."""
        return [
            {
                'description': '''**Si usas GitHub Pages:**

El sitio regenerará automáticamente las teselas IIIF con los archivos info.json corregidos cuando se reconstruya. Para iniciar una reconstrucción ahora, ve a la pestaña Actions del repositorio, selecciona el flujo "Build and Deploy" y haz clic en **Run workflow**.''',
            },
            {
                'description': '''**Si trabajas con tu sitio localmente:**

Si el sitio usa imágenes auto-alojadas, regenera las teselas IIIF para corregir los archivos info.json. Esto soluciona dos problemas: un error con imágenes pequeñas (menos de 512px) y teselas de borde incorrectas en imágenes grandes (más de 1024px).

`python3 scripts/generate_iiif.py --base-url URL_DE_TU_SITIO`

(Reemplaza URL_DE_TU_SITIO con la URL del sitio, ej. https://tuusuario.github.io/tu-repositorio)''',
            },
        ]
