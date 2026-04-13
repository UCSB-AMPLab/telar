"""
Migration from v1.0.0-beta to v1.1.0.

Linking, Layers & Collections release:
- Deep linking — URL fragments addressing steps and panel layers
- Title cards — objectless chapter heading cards for section breaks
- Collection mode — collection-first homepage layout via config flag
- Bibliography styling — hanging-indent widget for scholarly citations
- Share panel "this view" tab for position-aware sharing
- Panel scroll fix — wheel events no longer intercepted by scroll engine
- Keyboard navigation in open panels
- Video/audio deactivation on title card navigation
- IIIF viewer background fix on object pages
- Audio object detection without audiowaveform dependency

~25 framework files fetched from GitHub, 2 language files fetched,
1 config value added (collection_mode), version bumped.

Version: v1.1.0
"""

from typing import List, Dict
import re
from .base import BaseMigration


class Migration100to110(BaseMigration):
    """Migration from v1.0.0-beta to v1.1.0 - Linking, Layers & Collections."""

    from_version = "1.0.0-beta"
    to_version = "1.1.0"
    description = "Deep linking, title cards, collection mode, bibliography styling, panel fixes"

    def check_applicable(self) -> bool:
        """Check if migration should run."""
        return True

    def apply(self) -> List[str]:
        """Apply migration changes."""
        changes = []

        # Phase 1: Update framework files from GitHub
        print("  Phase 1: Updating framework files...")
        changes.extend(self._update_framework_files())

        # Phase 2: Update language files from GitHub
        print("  Phase 2: Updating language files...")
        changes.extend(self._update_language_files())

        # Phase 3: Add collection_mode config flag
        print("  Phase 3: Updating configuration...")
        changes.extend(self._update_configuration())

        # Phase 4: Update version
        print("  Phase 4: Updating version...")
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if self._update_config_version("1.1.0", today):
            changes.append(f"Updated _config.yml: version 1.1.0 ({today})")

        return changes

    def _update_framework_files(self) -> List[str]:
        """Fetch framework files from GitHub main branch."""
        changes = []

        framework_files = {
            # Layouts
            '_layouts/index.html': 'Homepage with collection mode branch',
            # Includes
            '_includes/panels.html': 'Panels with data-telar-panel attributes',
            '_includes/share-panel.html': 'Share panel with "this view" tab',
            '_includes/widgets/bibliography.html': 'Bibliography widget template (new)',
            # Stylesheets
            '_sass/_layout.scss': 'Layout styles (collection mode)',
            '_sass/_panels.scss': 'Panel styles (bibliography max-width)',
            '_sass/_story.scss': 'Story styles (title cards)',
            '_sass/_viewer.scss': 'Viewer styles (Tify background fix)',
            '_sass/_widgets.scss': 'Widget styles (bibliography hanging indent)',
            # JavaScript (standalone)
            'assets/js/share-panel.js': 'Share panel (deep link support)',
            # JavaScript (bundled)
            'assets/js/telar-story.js': 'Bundled story JS',
            'assets/js/telar-story.js.map': 'Source map',
            'assets/js/telar-story/main.js': 'Story entry point (deep link init)',
            'assets/js/telar-story/card-pool.js': 'Card pool (title cards, media deactivation)',
            'assets/js/telar-story/deep-link.js': 'Deep linking module (new)',
            'assets/js/telar-story/navigation.js': 'Navigation (panel keyboard scroll, hash writes)',
            'assets/js/telar-story/panels.js': 'Panels (glossary deep-link numbers, hash writes)',
            'assets/js/telar-story/scroll-engine.js': 'Scroll engine (panel fix, hash writes)',
            # Python scripts
            'scripts/telar/core.py': 'Build pipeline (audio manifest generation)',
            'scripts/telar/widgets.py': 'Widget parser (bibliography support)',
            # Documentation
            'README.md': 'README (v1.1.0 features, bilingual)',
            'CHANGELOG.md': 'CHANGELOG (v1.1.0 release notes)',
            # Tests
            'tests/js/card-pool.test.js': 'Card pool tests (title cards)',
            'tests/unit/test_bibliography_widget.py': 'Bibliography widget tests (new)',
        }

        for file_path, description in framework_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path} - {description}")
            else:
                changes.append(f"Warning: Could not fetch {file_path}")

        return changes

    def _update_language_files(self) -> List[str]:
        """Fetch language files from GitHub (adds collection_mode_heading key)."""
        changes = []

        language_files = {
            '_data/languages/en.yml': 'English strings (collection_mode_heading added)',
            '_data/languages/es.yml': 'Spanish strings (collection_mode_heading added)',
        }

        for file_path, description in language_files.items():
            content = self._fetch_from_github(file_path)
            if content:
                self._write_file(file_path, content)
                changes.append(f"Updated {file_path} - {description}")
            else:
                changes.append(f"Warning: Could not fetch {file_path}")

        return changes

    def _update_configuration(self) -> List[str]:
        """Add collection_mode: false to _config.yml if not already present."""
        changes = []

        content = self._read_file('_config.yml')
        if not content:
            changes.append("Warning: _config.yml not found")
            return changes

        if 'collection_mode' in content:
            changes.append("Note: collection_mode already present in _config.yml, skipped")
            return changes

        # Insert collection_mode after telar_language line (value may be quoted or unquoted)
        new_content, count = re.subn(
            r'(telar_language:\s*[^\n]*\n)',
            r'\1collection_mode: false # Set to true to show objects first with large thumbnails and stories below with small thumbnails (collection-first homepage)\n',
            content,
            count=1
        )

        if count > 0:
            self._write_file('_config.yml', new_content)
            changes.append("Added collection_mode: false to _config.yml (after telar_language)")
        else:
            changes.append("Warning: Could not find telar_language line to insert collection_mode")

        return changes

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """Return manual steps in user's language."""
        lang = self._detect_language()
        if lang == 'es':
            return self._get_manual_steps_es()
        else:
            return self._get_manual_steps_en()

    def _get_manual_steps_en(self) -> List[Dict[str, str]]:
        """English manual steps for v1.1.0 migration."""
        return [
            {
                'description': '''**New features available after upgrade:**

- **Deep linking**: Your story URLs now update as readers scroll. They can copy and share a URL that points to a specific step, optionally with a panel open. No configuration needed — it works automatically.

- **Title cards**: To add a chapter heading between story steps, leave the object column empty for a step row. The question column becomes the heading text. Title cards work with scroll, keyboard, and button navigation.

- **Collection mode**: To flip your homepage to a collection-first layout, add `collection_mode: true` to `_config.yml` (the upgrade script has already added the flag set to `false`). Objects appear first with large thumbnails; stories appear below with smaller thumbnails.

- **Bibliography styling**: To format references with hanging indent in panel content, wrap them in a `:::bibliography` block in your markdown file.

- **Share panel**: The share panel now includes a "this view" tab that copies the current URL with the reader's exact position.''',
                'doc_url': 'https://telar.org/docs'
            },
        ]

    def _get_manual_steps_es(self) -> List[Dict[str, str]]:
        """Spanish manual steps for v1.1.0 migration."""
        return [
            {
                'description': '''**Nuevas funciones disponibles tras la actualización:**

- **Enlaces directos**: Las URLs de las historias ahora se actualizan a medida que se desplaza por ellas. Se puede copiar y compartir una URL que apunte a un paso específico, opcionalmente con un panel abierto. No requiere configuración — funciona automáticamente.

- **Tarjetas de título**: Para agregar un encabezado de capítulo entre los pasos de una historia, deja vacía la columna de objeto en una fila de paso. La columna de pregunta se convierte en el texto del encabezado. Las tarjetas de título funcionan con desplazamiento, teclado y botones de navegación.

- **Modo colección**: Para cambiar la página de inicio a un diseño que prioriza la colección, agrega `collection_mode: true` en `_config.yml` (el script de actualización ya agregó el parámetro con valor `false`). Los objetos aparecen primero con miniaturas grandes; las historias aparecen debajo con miniaturas más pequeñas.

- **Estilo bibliográfico**: Para dar formato de sangría francesa a las referencias en el contenido de los paneles, envuélvelas en un bloque `:::bibliography` en el archivo markdown.

- **Panel de compartir**: El panel de compartir ahora incluye una pestaña "esta vista" que copia la URL actual con la posición exacta del lector.''',
                'doc_url': 'https://telar.org/guia'
            },
        ]
